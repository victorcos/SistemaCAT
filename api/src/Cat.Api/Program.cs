using System.Text.Json;
using Cat.Api.Infra;
using Cat.Api.Rotas;
using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Trabalhos;
using Cat.Infraestrutura.Motor;
using Cat.Infraestrutura.Auth;
using Cat.Infraestrutura.Banco;
using Cat.Infraestrutura.Configuracao;
using Microsoft.EntityFrameworkCore;
using Cat.Aplicacao.Log;
using Cat.Infraestrutura.Log;
using Microsoft.AspNetCore.Cors.Infrastructure;
using Microsoft.Extensions.Logging.Console;
using Microsoft.Extensions.FileProviders;

var builder = WebApplication.CreateBuilder(args);

// Lida uma vez aqui só para o que precisa existir antes do host: porta e
// nível de log. O resto do programa usa a instância do contêiner, montada
// depois que toda a configuração — inclusive a dos testes — já foi aplicada.
var inicial = ConfigCat.Carregar(builder.Configuration);

// HTTPS quando houver par PEM configurado, HTTP quando não houver. **Uma porta,
// um esquema**: dois esquemas na mesma porta não existem, e inventar uma segunda
// porta para manter o endereço antigo vivo seria duas verdades sobre onde o
// sistema está. Quem liga o TLS avisa o pessoal que o endereço passa a `https`.
builder.WebHost.UseUrls(
    $"{(inicial.TemTls ? "https" : "http")}://0.0.0.0:{inicial.PortaApi}");
if (inicial.TemTls)
    builder.WebHost.ConfigureKestrel(k => k.ConfigureHttpsDefaults(
        o => o.ServerCertificate = Tls.Carregar(inicial)));

builder.Logging.ClearProviders();
builder.Logging.AddConsole(o => o.FormatterName = FormatadorJson.Nome);
builder.Logging.AddConsoleFormatter<FormatadorJson, ConsoleFormatterOptions>();
builder.Logging.SetMinimumLevel(FormatadorJson.ParaNivel(inicial.LogNivel));
// o ASP.NET narra cada requisição; a nossa linha já diz o que importa
builder.Logging.AddFilter("Microsoft", LogLevel.Warning);

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
builder.Services.AddScoped<IRepositorioDeAcesso, AcessoRepositorio>();
builder.Services.AddScoped<Autenticar>();
builder.Services.AddScoped<GerirUsuarios>();
builder.Services.AddScoped<AcessoAEmpresas>();

// ---------- trabalhos ----------
builder.Services.AddScoped<IRepositorioDeTrabalhos, TrabalhoRepositorio>();
builder.Services.AddScoped<Trabalhos>();
builder.Services.AddScoped<ExcluirTrabalho>();
builder.Services.AddScoped<IRepositorioDeHistorico, HistoricoRepositorio>();
builder.Services.AddScoped<HistoricoDoProjeto>();
builder.Services.AddScoped<IRepositorioDeLotes, LoteRepositorio>();
builder.Services.AddScoped<Lotes>();
builder.Services.AddScoped<IRepositorioDeExecucoes, ExecucaoRepositorio>();
builder.Services.AddScoped<Execucoes>();
builder.Services.AddScoped<IRepositorioDeDePara, DeParaRepositorio>();
builder.Services.AddScoped<DeParaDoTrabalho>();
builder.Services.AddScoped<IRepositorioDeCorrecoes, CorrecaoRepositorio>();
// tíquetes de download no banco, e não em memória: haverá mais de uma instância
// da API, e tíquete emitido numa tem de ser resgatável na outra
builder.Services.AddScoped<ITiquetesDeDownload, TiqueteRepositorio>();
builder.Services.AddScoped<CorrecoesDoTrabalho>();
// canal interno com o motor: apagar pasta de trabalho grande leva tempo
// sem prazo no cliente: cada chamada ao motor tem o seu, porque inspecionar
// milhares de arquivos na rede leva minutos e apagar uma pasta, segundos
builder.Services.AddHttpClient<IMotor, MotorHttp>(c => c.Timeout = Timeout.InfiniteTimeSpan);

builder.Services.AddCors();
builder.Services.AddOptions<CorsOptions>().Configure<ConfigCat>((opcoes, config) =>
    opcoes.AddDefaultPolicy(p => p
        .WithOrigins([.. config.Origens])
        .AllowCredentials()
        .AllowAnyMethod()
        .AllowAnyHeader()
        .WithExposedHeaders(RequisicaoMiddleware.Cabecalho)));

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
    esquema = config.TemTls ? "https" : "http",
    front = config.ServeOFront ? config.PastaDoFront : "(servido pelo Vite)",
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
if (string.IsNullOrEmpty(config.MotorSegredo))
    log.Erro("CAT_MOTOR_SEGREDO não definido. O canal interno com o motor fica fechado: apagar trabalho " +
             "com execuções vai falhar. Rodar scripts\\instalar.ps1 acrescenta o segredo ao backend/.env.",
        new { acao = "definir CAT_MOTOR_SEGREDO" });
if (config.SemPimenta)
    log.Aviso("CAT_SENHA_PIMENTA não definida. As senhas seguem protegidas por Argon2id com sal, " +
              "mas um vazamento do banco não teria a barreira extra do segredo de servidor.",
        new { acao = "definir CAT_SENHA_PIMENTA" });

app.UseMiddleware<RequisicaoMiddleware>();
app.UseCors();

app.MapearSaude();
app.MapearAuth();
app.MapearUsuarios();
app.MapearSegmentos();
app.MapearTrabalhos();
app.MapearHistorico();
app.MapearLotes();
app.MapearExecucoes();
app.MapearDePara();
app.MapearCorrecoes();
// Desde a fatia 7 nada de /api segue ao motor. Rota que não existe responde
// aqui, com texto em "detail" — o ASP.NET sozinho devolveria 404 de corpo
// vazio, e a tela mostraria só "erro".
app.MapFallback("/api/{**resto}", () =>
    CorpoJson.Recusar("Esta rota não existe na API.", StatusCodes.Status404NotFound));

// ---------- o front, na mesma origem ----------
//
// Serve o que o `npm run build` deixou em `frontend/dist`, quando configurado.
// Na mesma origem não há proxy do Vite no caminho dos bytes — um salto menos num
// download de centenas de megabytes —, não há CORS, não há `allowedHosts`, e o
// contexto é seguro para todo mundo em vez de só para quem abre por `localhost`.
//
// **O desvio do `/api` vem antes de propósito.** O `MapFallbackToFile` atende
// qualquer caminho, e sem o `MapFallback("/api/...")` acima uma rota de API
// inexistente devolveria o `index.html` com 200 — a tela receberia HTML onde
// esperava JSON e diria "erro" sem dizer qual. O ASP.NET resolve pela
// especificidade do padrão: `/api/{**resto}` tem segmento literal e ganha.
if (config.ServeOFront && Directory.Exists(config.PastaDoFront))
{
    var arquivos = new PhysicalFileProvider(config.PastaDoFront);

    // **uma configuração, usada nos dois lugares.** O `MapFallbackToFile` tem
    // opções próprias, e quando elas divergem das do `UseStaticFiles` o mesmo
    // `index.html` sai com cabeçalho diferente conforme quem o serviu: pedido
    // como `/index.html` vinha com `no-cache`, e como `/` ou `/projetos/1`
    // vinha sem nada. Era o caso que o cabeçalho existe para cobrir
    var estaticos = new StaticFileOptions
    {
        FileProvider = arquivos,
        OnPrepareResponse = ctx =>
        {
            // o Vite põe o resumo do conteúdo no nome dos arquivos de `assets`:
            // nome igual é conteúdo igual, e pode ficar em cache para sempre. O
            // `index.html` é o oposto — tem nome fixo e aponta para os resumos
            // novos, e em cache ele deixaria a pessoa numa versão que já não
            // existe, pedindo arquivos que foram embora
            var caminho = ctx.Context.Request.Path.Value ?? "";
            ctx.Context.Response.Headers.CacheControl =
                caminho.StartsWith("/assets/", StringComparison.Ordinal)
                    ? "public, max-age=31536000, immutable"
                    : "no-cache";
        },
    };
    app.UseDefaultFiles(new DefaultFilesOptions { FileProvider = arquivos });
    app.UseStaticFiles(estaticos);
    app.MapFallbackToFile("index.html", estaticos);
    log.Info("front servido pela API", new { pasta = config.PastaDoFront });
}
else if (config.ServeOFront)
{
    log.Aviso("CAT_PASTA_DO_FRONT aponta para pasta que não existe; o front não será servido",
        new { pasta = config.PastaDoFront, acao = "cd frontend && npm run build" });
}

app.Run();

// visível para os testes de integração
public partial class Program;
