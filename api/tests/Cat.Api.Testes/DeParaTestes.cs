using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;

namespace Cat.Api.Testes;

/// <summary>O canal do de-para, de mentira: devolve o que o teste mandar e guarda o pedido.</summary>
public sealed class MotorDeDeParaFalso : IAsyncLifetime
{
    public const string Segredo = "segredo-do-canal-do-depara";
    private WebApplication? _app;
    public Uri Endereco { get; private set; } = null!;
    public ConcurrentQueue<JsonElement> Pedidos { get; } = new();
    public Func<JsonElement, IResult> AoPedirCandidatos { get; set; } = _ => Results.StatusCode(500);

    public async Task InitializeAsync()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();
        _app.MapPost("/interno/depara/candidatos", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.StatusCode(403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            Pedidos.Enqueue(pedido);
            return AoPedirCandidatos(pedido);
        });
        await _app.StartAsync();
        Endereco = new Uri(_app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First());
    }

    public async Task DisposeAsync()
    {
        if (_app is not null)
            await _app.DisposeAsync();
    }
}

[Collection(ColecaoDoBanco.Nome)]
public sealed class DeParaTestes(BancoDeTeste banco, MotorDeDeParaFalso motor) : IDisposable, IClassFixture<MotorDeDeParaFalso>
{
    private readonly string _backend = CriarBackendFalso();
    private readonly List<WebApplicationFactory<Program>> _fabricas = [];
    private readonly TokensJwt _tokens = new(BancoDeTeste.Segredo, 480, TimeProvider.System);

    public void Dispose()
    {
        foreach (var f in _fabricas)
            f.Dispose();
        Directory.Delete(_backend, recursive: true);
    }

    private static string CriarBackendFalso()
    {
        var pasta = Directory.CreateTempSubdirectory("cat-depara-").FullName;
        File.WriteAllText(Path.Combine(pasta, "pyproject.toml"), "version = \"1.2.3\"\n");
        File.WriteAllText(Path.Combine(pasta, ".env"), "");
        return pasta;
    }

    private HttpClient Cliente(string? token = null)
    {
        var fabrica = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", _backend);
            b.UseSetting("CAT_BANCO_URL", banco.Url);
            b.UseSetting("CAT_SENHA_PIMENTA", BancoDeTeste.Pimenta);
            b.UseSetting("CAT_JWT_SEGREDO", BancoDeTeste.Segredo);
            b.UseSetting("CAT_MOTOR_URL", motor.Endereco.ToString());
            b.UseSetting("CAT_MOTOR_SEGREDO", MotorDeDeParaFalso.Segredo);
        });
        _fabricas.Add(fabrica);
        var c = fabrica.CreateClient();
        if (token is not null)
            c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    private async Task<(int Id, HttpClient Cliente)> Pessoa(string papel, int[]? empresas = null)
    {
        var nome = "d" + Guid.NewGuid().ToString("N")[..10];
        var id = await banco.CriarUsuario(nome, papel: papel);
        foreach (var e in empresas ?? [])
            await banco.Comando($"INSERT INTO alocacao (usuario_id, empresa_id, papel_projeto, inicio) VALUES ({id}, {e}, 'executor', now())");
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario { Id = id, NomeDeUsuario = nome, Email = "x@y.zz", NomeExibicao = "Ana", Papel = p });
        return (id, Cliente(token));
    }

    private static async Task<(int Empresa, int Projeto)> Trabalho(HttpClient c)
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var doze = raiz + "0001";
        var r = await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = doze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(doze), razao_social = "DISTRIBUIDORA DO DE-PARA", uf = "SP" });
        var empresa = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        r = await c.PostAsJsonAsync("/api/projetos", new { empresa_id = empresa, frente = "cat42", nome = "De-para " + Guid.NewGuid().ToString("N")[..6], competencia_ini = "2022-08-01", competencia_fim = "2024-06-01" });
        return (empresa, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32());
    }

    private static async Task<string> Detalhe(HttpResponseMessage r) =>
        (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString()!;

    [Fact]
    public async Task Listar_repassa_o_trabalho_ao_motor_e_devolve_o_que_ele_diz()
    {
        var (_, c) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(c);
        motor.AoPedirCandidatos = p => Results.Json(new
        {
            resumo = new { pares = 1, pendentes = 1 },
            pares = new[] { new { cnpj = "44000001000454", origem = "101208", destino = "1012", fator = "1", situacao = "pendente" } },
        });

        var r = await c.GetAsync($"/api/projetos/{projeto}/depara");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var d = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("1012", d.GetProperty("pares")[0].GetProperty("destino").GetString());
        Assert.Equal(projeto, motor.Pedidos.Last().GetProperty("projeto_id").GetInt32());
    }

    [Fact]
    public async Task Recusa_do_motor_e_escopo_chegam_a_tela()
    {
        var (_, dono) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(dono);
        var (_, deFora) = await Pessoa("analista");
        motor.AoPedirCandidatos = _ => Results.Json(new { detail = "Conclua a extração de movimentos antes." }, statusCode: 422);

        var r = await dono.GetAsync($"/api/projetos/{projeto}/depara");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal("Conclua a extração de movimentos antes.", await Detalhe(r));
        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.GetAsync($"/api/projetos/{projeto}/depara")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await dono.GetAsync("/api/projetos/999999/depara")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Cliente().GetAsync($"/api/projetos/{projeto}/depara")).StatusCode);
    }

    [Fact]
    public async Task Decidir_grava_por_empresa_atualiza_a_mesma_origem_e_registra_no_historico()
    {
        var (quem, c) = await Pessoa("gestor");
        var (empresa, projeto) = await Trabalho(c);

        var r = await c.PostAsJsonAsync($"/api/projetos/{projeto}/depara", new
        {
            decisoes = new object[]
            {
                new { cnpj = "44000001000454", origem = "1111K308", destino = "1111", fator = "3", motivo = "kit", situacao = "aprovado", confianca = "alta", explicacao = "kit de 3 unidades" },
                new { cnpj = "", origem = "X0046E1FBP", destino = "3130", fator = "1", motivo = "cliente", situacao = "aprovado" },
                new { cnpj = "44000001000454", origem = "400108", destino = "4001", motivo = "sufixo", situacao = "recusado" },
            },
        });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(3, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("gravadas").GetInt32());
        Assert.Equal(3L, await banco.Escalar<long>($"SELECT count(*) FROM depara_item WHERE empresa_id = {empresa}"));
        Assert.Equal(3m, await banco.Escalar<decimal>($"SELECT fator FROM depara_item WHERE empresa_id = {empresa} AND codigo_origem = '1111K308'"));
        Assert.Equal(quem, await banco.Escalar<int>($"SELECT decidido_por FROM depara_item WHERE empresa_id = {empresa} AND codigo_origem = '400108'"));

        // decidir de novo a mesma origem atualiza, não duplica
        r = await c.PostAsJsonAsync($"/api/projetos/{projeto}/depara", new
        {
            decisoes = new[] { new { cnpj = "44000001000454", origem = "400108", destino = "4001", fator = "1", motivo = "sufixo", situacao = "aprovado" } },
        });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(3L, await banco.Escalar<long>($"SELECT count(*) FROM depara_item WHERE empresa_id = {empresa}"));
        Assert.Equal("aprovado", await banco.Escalar<string>($"SELECT situacao FROM depara_item WHERE empresa_id = {empresa} AND codigo_origem = '400108'"));

        var textos = await banco.Escalar<string>(
            $"SELECT string_agg(texto, ' | ' ORDER BY id) FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'parametro_alterado'");
        Assert.Equal("De-para de códigos · 2 pares aprovados, 1 par recusado | De-para de códigos · 1 par aprovado", textos);
        Assert.Contains("\"parametro\":\"depara\"", await banco.Escalar<string>(
            $"SELECT dados::text FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'parametro_alterado' ORDER BY id LIMIT 1"));
    }

    [Fact]
    public async Task Decidir_recusa_pedido_invalido_e_quem_so_le()
    {
        var (_, gestor) = await Pessoa("gestor");
        var (empresa, projeto) = await Trabalho(gestor);
        var (_, leitura) = await Pessoa("leitura", [empresa]);
        var boa = new { cnpj = "", origem = "A", destino = "B", fator = "1", motivo = "analista", situacao = "aprovado" };

        Assert.Equal(HttpStatusCode.Forbidden,
            (await leitura.PostAsJsonAsync($"/api/projetos/{projeto}/depara", new { decisoes = new[] { boa } })).StatusCode);
        var r = await gestor.PostAsJsonAsync($"/api/projetos/{projeto}/depara", new { decisoes = Array.Empty<object>() });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal("Nenhuma decisão no pedido.", await Detalhe(r));
        r = await gestor.PostAsJsonAsync($"/api/projetos/{projeto}/depara", new { decisoes = new[] { boa, boa } });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Contains("mais de uma vez", await Detalhe(r));
        r = await gestor.PostAsJsonAsync($"/api/projetos/{projeto}/depara",
            new { decisoes = new[] { new { cnpj = "", origem = "A", destino = "A", fator = "1", motivo = "analista", situacao = "aprovado" } } });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal(0L, await banco.Escalar<long>($"SELECT count(*) FROM depara_item WHERE empresa_id = {empresa}"));
    }
}
