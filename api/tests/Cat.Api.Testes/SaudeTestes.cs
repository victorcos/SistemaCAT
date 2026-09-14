using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Cat.Infraestrutura.Motor;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;

namespace Cat.Api.Testes;

/// <summary>
/// Um motor falso escutando num socket de verdade, com a saúde no canal
/// interno. Conta tudo o que chega a ele: desde a fatia 7, pedido de
/// <c>/api</c> nenhum pode atravessar.
/// </summary>
public sealed class MotorFalso : IAsyncLifetime
{
    public const string Segredo = "segredo-do-motor-falso";

    private WebApplication? _app;
    private int _pedidos;
    public Uri Endereco { get; private set; } = null!;
    public int Pedidos => _pedidos;

    public async Task InitializeAsync()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();

        _app.Use(async (http, proximo) =>
        {
            Interlocked.Increment(ref _pedidos);
            await proximo(http);
        });
        _app.MapGet("/interno/saude", (HttpContext http) =>
            http.Request.Headers[MotorHttp.CabecalhoSegredo] == Segredo
                ? Results.Json(new { status = "ok", versao = "9.9.9" })
                : Results.Json(new { detail = "Canal interno: segredo ausente ou errado." }, statusCode: 403));
        // se o repasse voltasse, é aqui que o pedido chegaria
        _app.Map("/{**resto}", () => Results.Json(new { detail = "o motor atendeu" }));

        await _app.StartAsync();
        var endereco = _app.Services.GetRequiredService<IServer>()
            .Features.Get<IServerAddressesFeature>()!.Addresses.First();
        Endereco = new Uri(endereco);
    }

    public async Task DisposeAsync()
    {
        if (_app is not null)
            await _app.DisposeAsync();
    }
}

public sealed class SaudeTestes(MotorFalso motor) : IClassFixture<MotorFalso>, IDisposable
{
    // repositório de mentira: VERSAO na raiz, backend/ dentro dela
    private readonly string _raiz = CriarRaizFalsa();
    private readonly List<WebApplicationFactory<Program>> _fabricas = [];

    private string Backend => Path.Combine(_raiz, "backend");

    public void Dispose()
    {
        foreach (var f in _fabricas)
            f.Dispose();
        Directory.Delete(_raiz, recursive: true);
    }

    private static string CriarRaizFalsa()
    {
        var raiz = Directory.CreateTempSubdirectory("cat-api-").FullName;
        var backend = Directory.CreateDirectory(Path.Combine(raiz, "backend")).FullName;
        File.WriteAllText(Path.Combine(raiz, "VERSAO"), "1.2.3\n");
        File.WriteAllText(Path.Combine(backend, "pyproject.toml"), "[project]\n");
        // pasta própria: os testes nunca leem o .env real da máquina
        File.WriteAllText(Path.Combine(backend, ".env"), "CAT_ORIGENS_PERMITIDAS=http://localhost:5173\n");
        return raiz;
    }

    private HttpClient Cliente(Uri? motorUrl = null, string segredo = MotorFalso.Segredo)
    {
        var fabrica = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", Backend);
            b.UseSetting("CAT_MOTOR_URL", (motorUrl ?? motor.Endereco).ToString());
            b.UseSetting("CAT_MOTOR_SEGREDO", segredo);
        });
        _fabricas.Add(fabrica);
        return fabrica.CreateClient();
    }

    private static Uri PortaFechada()
    {
        using var ouvinte = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
        ouvinte.Start();
        var porta = ((IPEndPoint)ouvinte.LocalEndpoint).Port;
        ouvinte.Stop();
        return new Uri($"http://127.0.0.1:{porta}");
    }

    [Fact]
    public async Task Saude_diz_quem_respondeu_e_a_versao_dos_dois_lados()
    {
        var resposta = await Cliente().GetFromJsonAsync<JsonElement>("/api/saude");

        Assert.Equal("ok", resposta.GetProperty("status").GetString());
        Assert.Equal("1.2.3", resposta.GetProperty("versao").GetString());
        Assert.Equal("csharp", resposta.GetProperty("api").GetString());
        Assert.Equal(Path.Combine(Backend, "data", "trabalho"),
            resposta.GetProperty("pasta_de_trabalho").GetString());
        Assert.Equal("ok", resposta.GetProperty("motor").GetProperty("situacao").GetString());
        Assert.Equal("9.9.9", resposta.GetProperty("motor").GetProperty("versao").GetString());
    }

    [Fact]
    public async Task Saude_do_motor_vai_pelo_canal_interno_e_segredo_errado_aparece()
    {
        var resposta = await Cliente(segredo: "outro").GetFromJsonAsync<JsonElement>("/api/saude");

        Assert.Equal("ok", resposta.GetProperty("status").GetString());
        Assert.Equal("http 403", resposta.GetProperty("motor").GetProperty("situacao").GetString());
    }

    [Fact]
    public async Task Saude_responde_mesmo_com_o_motor_fora()
    {
        var resposta = await Cliente(PortaFechada()).GetAsync("/api/saude");

        Assert.Equal(HttpStatusCode.OK, resposta.StatusCode);
        var corpo = await resposta.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("fora do ar", corpo.GetProperty("motor").GetProperty("situacao").GetString());
    }

    [Theory]
    [InlineData("GET", "/api/rota-que-nao-existe")]
    [InlineData("POST", "/api/conferencias/7/cancelar")]
    [InlineData("DELETE", "/api/eco/projetos/7?formato=csv")]
    public async Task Rota_desconhecida_responde_aqui_com_detail_e_nao_chega_ao_motor(string metodo, string caminho)
    {
        var cliente = Cliente();
        var antes = motor.Pedidos;
        var pedido = new HttpRequestMessage(new HttpMethod(metodo), caminho);
        pedido.Headers.Add("X-Request-Id", "pedido-42");

        var resposta = await cliente.SendAsync(pedido);

        Assert.Equal(HttpStatusCode.NotFound, resposta.StatusCode);
        var corpo = await resposta.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Esta rota não existe na API.", corpo.GetProperty("detail").GetString());
        Assert.Equal("pedido-42", resposta.Headers.GetValues("X-Request-Id").Single());
        Assert.Equal(antes, motor.Pedidos);
    }

    [Theory]
    [InlineData("/docs")]
    [InlineData("/openapi.json")]
    public async Task Documentacao_do_fastapi_nao_e_mais_repassada(string caminho)
    {
        var antes = motor.Pedidos;

        var resposta = await Cliente().GetAsync(caminho);

        Assert.Equal(HttpStatusCode.NotFound, resposta.StatusCode);
        Assert.Equal(antes, motor.Pedidos);
    }

    [Fact]
    public async Task Sem_identificador_a_api_cria_um()
    {
        var resposta = await Cliente().GetAsync("/api/saude");

        Assert.Matches("^[0-9a-f]{12}$", resposta.Headers.GetValues("X-Request-Id").Single());
    }

    [Fact]
    public async Task Cors_da_lista_e_respondido()
    {
        var previa = new HttpRequestMessage(HttpMethod.Options, "/api/saude");
        previa.Headers.Add("Origin", "http://localhost:5173");
        previa.Headers.Add("Access-Control-Request-Method", "GET");

        var resposta = await Cliente().SendAsync(previa);

        Assert.Equal("http://localhost:5173", resposta.Headers.GetValues("Access-Control-Allow-Origin").Single());
    }

    [Fact]
    public async Task Origem_fora_da_lista_nao_ganha_cabecalho_de_cors()
    {
        var pedido = new HttpRequestMessage(HttpMethod.Get, "/api/saude");
        pedido.Headers.Add("Origin", "http://intruso.example");

        var resposta = await Cliente().SendAsync(pedido);

        Assert.False(resposta.Headers.Contains("Access-Control-Allow-Origin"));
    }
}
