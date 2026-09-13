using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;

namespace Cat.Api.Testes;

/// <summary>
/// Um motor falso escutando num socket de verdade. O repasse do YARP usa o
/// próprio cliente HTTP e não enxerga servidor em memória; testar contra um
/// processo de mentira em porta real é o que prova que o pedido atravessa.
/// </summary>
public sealed class MotorFalso : IAsyncLifetime
{
    private WebApplication? _app;
    public Uri Endereco { get; private set; } = null!;

    public async Task InitializeAsync()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();

        _app.MapGet("/api/saude", () => Results.Json(new { status = "ok", versao = "9.9.9" }));
        _app.Map("/api/eco/{**resto}", async (HttpContext http) =>
        {
            using var leitor = new StreamReader(http.Request.Body);
            return Results.Json(new
            {
                metodo = http.Request.Method,
                caminho = http.Request.Path.Value,
                consulta = http.Request.QueryString.Value,
                requisicao = http.Request.Headers["X-Request-Id"].ToString(),
                tem_origin = http.Request.Headers.ContainsKey("Origin"),
                autorizacao = http.Request.Headers.Authorization.ToString(),
                corpo = await leitor.ReadToEndAsync(),
            });
        });
        // o FastAPI recusando uma regra: o repasse não pode reescrever isto
        _app.MapPost("/api/projetos/{id}/conferencias", () => Results.Json(
            new { detail = "Já existe uma conferência em andamento neste trabalho." }, statusCode: 409));

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

public sealed class RepasseTestes(MotorFalso motor) : IClassFixture<MotorFalso>, IDisposable
{
    private readonly string _backend = CriarBackendFalso();
    private readonly List<WebApplicationFactory<Program>> _fabricas = [];

    public void Dispose()
    {
        foreach (var f in _fabricas)
            f.Dispose();
        Directory.Delete(_backend, recursive: true);
    }

    private static string CriarBackendFalso()
    {
        var pasta = Directory.CreateTempSubdirectory("cat-api-").FullName;
        File.WriteAllText(Path.Combine(pasta, "pyproject.toml"), "version = \"1.2.3\"\n");
        // pasta própria: os testes nunca leem o .env real da máquina
        File.WriteAllText(Path.Combine(pasta, ".env"), "CAT_ORIGENS_PERMITIDAS=http://localhost:5173\n");
        return pasta;
    }

    private HttpClient Cliente(Uri? motorUrl = null)
    {
        var fabrica = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", _backend);
            b.UseSetting("CAT_MOTOR_URL", (motorUrl ?? motor.Endereco).ToString());
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
        Assert.Equal(Path.Combine(_backend, "data", "trabalho"),
            resposta.GetProperty("pasta_de_trabalho").GetString());
        Assert.Equal("ok", resposta.GetProperty("motor").GetProperty("situacao").GetString());
        Assert.Equal("9.9.9", resposta.GetProperty("motor").GetProperty("versao").GetString());
    }

    [Fact]
    public async Task Saude_responde_mesmo_com_o_motor_fora()
    {
        var resposta = await Cliente(PortaFechada()).GetAsync("/api/saude");

        Assert.Equal(HttpStatusCode.OK, resposta.StatusCode);
        var corpo = await resposta.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("fora do ar", corpo.GetProperty("motor").GetProperty("situacao").GetString());
    }

    [Fact]
    public async Task Rota_nao_portada_chega_ao_motor_com_caminho_consulta_corpo_e_token()
    {
        var pedido = new HttpRequestMessage(HttpMethod.Post, "/api/eco/projetos/7?formato=csv&modelos=55,65")
        {
            Content = new StringContent("{\"pasta\":\"Z:\\\\clientes\"}", System.Text.Encoding.UTF8, "application/json"),
        };
        pedido.Headers.Authorization = new("Bearer", "abc.def.ghi");

        var resposta = await Cliente().SendAsync(pedido);
        var eco = await resposta.Content.ReadFromJsonAsync<JsonElement>();

        Assert.Equal(HttpStatusCode.OK, resposta.StatusCode);
        Assert.Equal("POST", eco.GetProperty("metodo").GetString());
        Assert.Equal("/api/eco/projetos/7", eco.GetProperty("caminho").GetString());
        Assert.Equal("?formato=csv&modelos=55,65", eco.GetProperty("consulta").GetString());
        Assert.Equal("{\"pasta\":\"Z:\\\\clientes\"}", eco.GetProperty("corpo").GetString());
        Assert.Equal("Bearer abc.def.ghi", eco.GetProperty("autorizacao").GetString());
    }

    [Fact]
    public async Task Identificador_da_requisicao_e_o_mesmo_no_csharp_e_no_motor()
    {
        var pedido = new HttpRequestMessage(HttpMethod.Get, "/api/eco/x");
        pedido.Headers.Add("X-Request-Id", "pedido-42");

        var resposta = await Cliente().SendAsync(pedido);
        var eco = await resposta.Content.ReadFromJsonAsync<JsonElement>();

        Assert.Equal("pedido-42", eco.GetProperty("requisicao").GetString());
        Assert.Equal("pedido-42", resposta.Headers.GetValues("X-Request-Id").Single());
    }

    [Fact]
    public async Task Sem_identificador_a_api_cria_um_e_o_motor_recebe_o_mesmo()
    {
        var resposta = await Cliente().GetAsync("/api/eco/x");
        var eco = await resposta.Content.ReadFromJsonAsync<JsonElement>();

        var criado = resposta.Headers.GetValues("X-Request-Id").Single();
        Assert.Matches("^[0-9a-f]{12}$", criado);
        Assert.Equal(criado, eco.GetProperty("requisicao").GetString());
    }

    [Fact]
    public async Task Recusa_do_motor_passa_intacta()
    {
        var resposta = await Cliente().PostAsync("/api/projetos/7/conferencias", null);

        Assert.Equal(HttpStatusCode.Conflict, resposta.StatusCode);
        var corpo = await resposta.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Já existe uma conferência em andamento neste trabalho.", corpo.GetProperty("detail").GetString());
    }

    [Fact]
    public async Task Motor_fora_do_ar_vira_detail_que_o_front_sabe_mostrar()
    {
        var resposta = await Cliente(PortaFechada()).GetAsync("/api/projetos");

        Assert.Equal(HttpStatusCode.BadGateway, resposta.StatusCode);
        var corpo = await resposta.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Contains("motor", corpo.GetProperty("detail").GetString());
        Assert.True(resposta.Headers.Contains("X-Request-Id"));
    }

    [Fact]
    public async Task Cors_e_respondido_aqui_e_o_origin_nao_segue_para_o_motor()
    {
        var cliente = Cliente();

        var previa = new HttpRequestMessage(HttpMethod.Options, "/api/eco/x");
        previa.Headers.Add("Origin", "http://localhost:5173");
        previa.Headers.Add("Access-Control-Request-Method", "POST");
        var respostaPrevia = await cliente.SendAsync(previa);
        Assert.Equal("http://localhost:5173",
            respostaPrevia.Headers.GetValues("Access-Control-Allow-Origin").Single());

        var pedido = new HttpRequestMessage(HttpMethod.Get, "/api/eco/x");
        pedido.Headers.Add("Origin", "http://localhost:5173");
        var resposta = await cliente.SendAsync(pedido);
        var eco = await resposta.Content.ReadFromJsonAsync<JsonElement>();
        Assert.False(eco.GetProperty("tem_origin").GetBoolean());
        Assert.Equal("http://localhost:5173",
            resposta.Headers.GetValues("Access-Control-Allow-Origin").Single());
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
