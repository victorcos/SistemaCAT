using System.Text.Json;
using Cat.Api.Infra;
using Cat.Api.Rotas;
using Cat.Aplicacao.Acesso;
using Cat.Infraestrutura.Auth;
using Cat.Infraestrutura.Banco;
using Cat.Infraestrutura.Configuracao;
using Microsoft.EntityFrameworkCore;
using Cat.Aplicacao.Log;
using Cat.Infraestrutura.Log;
using Microsoft.AspNetCore.Cors.Infrastructure;
using Microsoft.Extensions.Logging.Console;
using Yarp.ReverseProxy.Configuration;

var builder = WebApplication.CreateBuilder(args);

// Lida uma vez aqui só para o que precisa existir antes do host: porta e
// nível de log. O resto do programa usa a instância do contêiner, montada
// depois que toda a configuração — inclusive a dos testes — já foi aplicada.
var inicial = ConfigCat.Carregar(builder.Configuration);
builder.WebHost.UseUrls($"http://0.0.0.0:{inicial.PortaApi}");

builder.Logging.ClearProviders();
builder.Logging.AddConsole(o => o.FormatterName = FormatadorJson.Nome);
builder.Logging.AddConsoleFormatter<FormatadorJson, ConsoleFormatterOptions>();
builder.Logging.SetMinimumLevel(FormatadorJson.ParaNivel(inicial.LogNivel));
// o ASP.NET e o YARP narram cada requisição; a nossa linha já diz o que importa
builder.Logging.AddFilter("Microsoft", LogLevel.Warning);
builder.Logging.AddFilter("Yarp", LogLevel.Warning);

builder.Services.AddSingleton(sp => ConfigCat.Carregar(sp.GetRequiredService<IConfiguration>()));
builder.Services.ConfigureHttpJsonOptions(o =>
{
    // o front espera snake_case: é o que o FastAPI sempre entregou
    o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
    o.SerializerOptions.Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping;
});
builder.Services.AddHttpClient(SaudeRotas.ClienteDoMotor, c => c.Timeout = TimeSpan.FromSeconds(3));

// ---------- acesso ----------
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddDbContext<CatDbContext>((sp, o) =>
    o.UseNpgsql(ConexaoPostgres.DeUrl(sp.GetRequiredService<ConfigCat>().BancoUrl)));
builder.Services.AddSingleton<IConferidorDeSenha>(sp => new SenhasArgon2(
    sp.GetRequiredService<ConfigCat>().SenhaPimenta, sp.GetRequiredService<ILogger<SenhasArgon2>>()));
builder.Services.AddSingleton<IEmissorDeToken>(sp =>
{
    var c = sp.GetRequiredService<ConfigCat>();
    return new TokensJwt(c.JwtSegredo, c.JwtMinutos, sp.GetRequiredService<TimeProvider>());
});
builder.Services.AddScoped<IRepositorioDeUsuario, UsuarioRepositorio>();
builder.Services.AddScoped<Autenticar>();

builder.Services.AddCors();
builder.Services.AddOptions<CorsOptions>().Configure<ConfigCat>((opcoes, config) =>
    opcoes.AddDefaultPolicy(p => p
        .WithOrigins([.. config.Origens])
        .AllowCredentials()
        .AllowAnyMethod()
        .AllowAnyHeader()
        .WithExposedHeaders(RequisicaoMiddleware.Cabecalho)));

builder.Services.AddSingleton<IProxyConfigProvider, RepasseAoMotor>();
builder.Services.AddReverseProxy();

var app = builder.Build();

var config = app.Services.GetRequiredService<ConfigCat>();
var log = app.Services.GetRequiredService<ILogger<Program>>();
// A pasta de trabalho e o motor vão no log de subida de propósito: um servidor
// antigo que sobrevive a um reinício só se denuncia pelo que diz ao subir.
log.Info("API no ar", new
{
    api = "csharp",
    versao = config.Versao,
    porta = config.PortaApi,
    motor = config.MotorUrl.ToString(),
    origens = config.Origens,
    banco = ConexaoPostgres.Mascarar(config.BancoUrl),
    pasta_de_trabalho = config.PastaDeTrabalho,
    raiz_backend = config.RaizBackend,
});

if (config.SegredoEPadrao)
    log.Erro("CAT_JWT_SEGREDO está com o valor padrão. Qualquer um pode forjar um token. " +
             "Definir a variável antes de expor o serviço.", new { acao = "definir CAT_JWT_SEGREDO" });
if (System.Text.Encoding.UTF8.GetByteCount(config.JwtSegredo) < 32)
    // abaixo de 256 bits a biblioteca de token recusa a chave e nenhum login funciona
    throw new InvalidOperationException("CAT_JWT_SEGREDO precisa de pelo menos 32 bytes para HS256.");
if (config.JwtAlgoritmo != "HS256")
    throw new InvalidOperationException($"CAT_JWT_ALGORITMO={config.JwtAlgoritmo}: a API em C# só emite HS256.");
if (config.SemPimenta)
    log.Aviso("CAT_SENHA_PIMENTA não definida. As senhas seguem protegidas por Argon2id com sal, " +
              "mas um vazamento do banco não teria a barreira extra do segredo de servidor.",
        new { acao = "definir CAT_SENHA_PIMENTA" });

app.UseMiddleware<RequisicaoMiddleware>();
app.UseCors();

app.MapearSaude();
app.MapearAuth();
app.MapReverseProxy(repasse =>
{
    repasse.Use(RepasseAoMotor.TraduzirFalha);
    repasse.UseLoadBalancing();
});

app.Run();

// visível para os testes de integração
public partial class Program;
