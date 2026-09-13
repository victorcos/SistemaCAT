using System.Text.Json;
using Cat.Api.Infra;
using Cat.Api.Rotas;
using Cat.Infraestrutura.Configuracao;
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
    pasta_de_trabalho = config.PastaDeTrabalho,
    raiz_backend = config.RaizBackend,
});

app.UseMiddleware<RequisicaoMiddleware>();
app.UseCors();

app.MapearSaude();
app.MapReverseProxy(repasse =>
{
    repasse.Use(RepasseAoMotor.TraduzirFalha);
    repasse.UseLoadBalancing();
});

app.Run();

// visível para os testes de integração
public partial class Program;
