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

/// <summary>O canal interno de execução e planilha, de mentira: cada teste diz o que ele responde.</summary>
public sealed class MotorDeExecucoesFalso : IAsyncLifetime
{
    public const string Segredo = "segredo-do-canal-de-execucoes";
    private WebApplication? _app;
    public Uri Endereco { get; private set; } = null!;
    public ConcurrentQueue<JsonElement> Pedidos { get; } = new();
    public Func<JsonElement, Task<IResult>> AoPedirExecucao { get; set; } = _ => Task.FromResult(Results.StatusCode(500));
    public Func<JsonElement, IResult> AoPedirPlanilha { get; set; } = _ => Results.StatusCode(500);

    public async Task InitializeAsync()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();
        _app.MapPost("/interno/execucoes", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.StatusCode(403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            Pedidos.Enqueue(pedido);
            return await AoPedirExecucao(pedido);
        });
        _app.MapPost("/interno/planilhas", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.StatusCode(403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            Pedidos.Enqueue(pedido);
            return AoPedirPlanilha(pedido);
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

/// <summary>Portados das rotas de conferencia_router.py e movimentos_router.py.</summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class ExecucoesTestes(BancoDeTeste banco, MotorDeExecucoesFalso motor) : IDisposable, IClassFixture<MotorDeExecucoesFalso>
{
    private readonly string _backend = CriarBackendFalso();
    private readonly List<WebApplicationFactory<Program>> _fabricas = [];
    private readonly TokensJwt _tokens = new(BancoDeTeste.Segredo, 480, TimeProvider.System);
    private string Trabalho_ => Path.Combine(_backend, "trabalho");

    public void Dispose()
    {
        foreach (var f in _fabricas)
            f.Dispose();
        Directory.Delete(_backend, recursive: true);
    }

    private static string CriarBackendFalso()
    {
        var pasta = Directory.CreateTempSubdirectory("cat-execucoes-").FullName;
        File.WriteAllText(Path.Combine(pasta, "pyproject.toml"), "version = \"1.2.3\"\n");
        File.WriteAllText(Path.Combine(pasta, ".env"), "");
        Directory.CreateDirectory(Path.Combine(pasta, "trabalho"));
        return pasta;
    }

    private HttpClient Cliente(string? token = null, Uri? motorUrl = null)
    {
        var fabrica = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", _backend);
            b.UseSetting("CAT_BANCO_URL", banco.Url);
            b.UseSetting("CAT_SENHA_PIMENTA", BancoDeTeste.Pimenta);
            b.UseSetting("CAT_JWT_SEGREDO", BancoDeTeste.Segredo);
            b.UseSetting("CAT_MOTOR_URL", (motorUrl ?? motor.Endereco).ToString());
            b.UseSetting("CAT_MOTOR_SEGREDO", MotorDeExecucoesFalso.Segredo);
            b.UseSetting("CAT_PASTA_DE_TRABALHO", Trabalho_);
        });
        _fabricas.Add(fabrica);
        var c = fabrica.CreateClient();
        if (token is not null)
            c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    private async Task<(int Id, string Token, HttpClient Cliente)> Pessoa(string papel, int[]? empresas = null)
    {
        var nome = "e" + Guid.NewGuid().ToString("N")[..10];
        var id = await banco.CriarUsuario(nome, papel: papel);
        foreach (var e in empresas ?? [])
            await banco.Comando($"INSERT INTO alocacao (usuario_id, empresa_id, papel_projeto, inicio) VALUES ({id}, {e}, 'executor', now())");
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario { Id = id, NomeDeUsuario = nome, Email = "x@y.zz", NomeExibicao = "X", Papel = p });
        return (id, token, Cliente(token));
    }

    private static async Task<(int Empresa, int Projeto)> Trabalho(HttpClient c)
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var doze = raiz + "0001";
        var r = await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = doze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(doze), razao_social = "EMPRESA DA EXECUCAO", uf = "SP" });
        var empresa = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        r = await c.PostAsJsonAsync("/api/projetos", new { empresa_id = empresa, frente = "cat42", nome = "Exec " + Guid.NewGuid().ToString("N")[..6], competencia_ini = "2021-05-01", competencia_fim = "2021-05-01" });
        return (empresa, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32());
    }

    private Task<int> Execucao(int projeto, string etapa, string situacao = "concluida", string? resumo = "{\"escriturados\": 2, \"avisos\": [\"a\"]}") =>
        banco.Escalar<int>($"""
            INSERT INTO execucao (projeto_id, etapa, situacao, passo, fracao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos, resumo, iniciada_em, terminada_em)
            VALUES ({projeto}, '{etapa}', '{situacao}', 'Pronto', 1, 3, 3, 300, 2, {(resumo is null ? "NULL" : $"'{resumo}'")}, now(), {(situacao == "concluida" ? "now()" : "NULL")})
            RETURNING id
            """);

    private static async Task<JsonElement> Json(HttpResponseMessage r) => await r.Content.ReadFromJsonAsync<JsonElement>();
    private static async Task<string> Detalhe(HttpResponseMessage r) => (await Json(r)).GetProperty("detail").GetString()!;

    // ------------------------------------------------------------------ pedir a rodada
    [Theory]
    [InlineData("conferencias", "conferencia")]
    [InlineData("movimentos", "movimentos")]
    public async Task Pedir_repassa_ao_motor_e_devolve_a_execucao_da_fila(string segmento, string etapa)
    {
        var (quem, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        motor.AoPedirExecucao = async p =>
        {
            var id = await Execucao(p.GetProperty("projeto_id").GetInt32(), p.GetProperty("etapa").GetString()!, "na_fila", null);
            return Results.Json(new { id }, statusCode: 202);
        };

        var r = await c.PostAsync($"/api/projetos/{projeto}/{segmento}", null);

        Assert.Equal(HttpStatusCode.Accepted, r.StatusCode);
        var d = await Json(r);
        Assert.Equal(["id", "projeto_id", "etapa", "situacao", "passo", "fracao", "arquivos_totais", "arquivos_lidos", "bytes_lidos",
                      "documentos", "erro", "iniciada_em", "terminada_em", "resumo"], d.EnumerateObject().Select(x => x.Name));
        Assert.Equal("na_fila", d.GetProperty("situacao").GetString());
        Assert.Equal(etapa, d.GetProperty("etapa").GetString());
        Assert.EndsWith("+00:00", d.GetProperty("iniciada_em").GetString());
        Assert.Equal(JsonValueKind.Null, d.GetProperty("resumo").ValueKind);
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("usuario_id", out _));
        Assert.Equal(quem, pedido.GetProperty("usuario_id").GetInt32());
        Assert.Equal(etapa, pedido.GetProperty("etapa").GetString());
    }

    [Theory]
    [InlineData(422, "Este trabalho está pausado e não é possível conferir documentos. Retome-o no histórico para seguir.")]
    [InlineData(409, "Já existe uma conferência em andamento neste trabalho.")]
    public async Task Recusa_do_motor_chega_a_tela_com_o_texto_dele(int status, string detalhe)
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        motor.AoPedirExecucao = _ => Task.FromResult(Results.Json(new { detail = detalhe }, statusCode: status));

        var r = await c.PostAsync($"/api/projetos/{projeto}/conferencias", null);

        Assert.Equal(status, (int)r.StatusCode);
        Assert.Equal(detalhe, await Detalhe(r));
    }

    [Fact]
    public async Task Pedir_exige_permissao_escopo_e_motor_no_ar()
    {
        var (_, tokenDono, dono) = await Pessoa("dev");
        var (empresa, projeto) = await Trabalho(dono);
        var (_, _, leitor) = await Pessoa("leitura", [empresa]);
        var (_, _, deFora) = await Pessoa("analista");

        var doLeitor = await leitor.PostAsync($"/api/projetos/{projeto}/conferencias", null);
        Assert.Equal(HttpStatusCode.Forbidden, doLeitor.StatusCode);
        Assert.Equal("Você não tem permissão para conferir documentos.", await Detalhe(doLeitor));
        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.PostAsync($"/api/projetos/{projeto}/movimentos", null)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Cliente().PostAsync($"/api/projetos/{projeto}/conferencias", null)).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await dono.PostAsync("/api/projetos/999999/conferencias", null)).StatusCode);
        Assert.Equal(HttpStatusCode.BadGateway,
            (await Cliente(tokenDono, new Uri("http://127.0.0.1:9")).PostAsync($"/api/projetos/{projeto}/conferencias", null)).StatusCode);
    }

    // ------------------------------------------------------------------ acompanhar
    [Fact]
    public async Task Lista_so_da_etapa_mais_recente_primeiro_e_detalha_com_o_resumo()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var primeira = await Execucao(projeto, "conferencia");
        var segunda = await Execucao(projeto, "conferencia", "rodando", null);
        var movimentos = await Execucao(projeto, "movimentos");

        var lista = (await Json(await c.GetAsync($"/api/projetos/{projeto}/conferencias"))).EnumerateArray()
            .Select(e => e.GetProperty("id").GetInt32()).ToList();
        var detalhe = await Json(await c.GetAsync($"/api/conferencias/{primeira}"));

        Assert.Equal([segunda, primeira], lista);
        Assert.Equal(2, detalhe.GetProperty("resumo").GetProperty("escriturados").GetInt32());
        Assert.Equal("a", detalhe.GetProperty("resumo").GetProperty("avisos")[0].GetString());
        Assert.EndsWith("+00:00", detalhe.GetProperty("terminada_em").GetString());
        // pela rota de conferência, qualquer execução; pela de movimentos, só as dela
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync($"/api/conferencias/{movimentos}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/movimentos/{primeira}")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync($"/api/movimentos/{movimentos}")).StatusCode);
        Assert.Equal("Execução não encontrada.", await Detalhe(await c.GetAsync("/api/conferencias/999999")));
    }

    [Fact]
    public async Task Execucao_de_empresa_que_nao_enxerga_nao_aparece()
    {
        var (_, _, dono) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(dono);
        var id = await Execucao(projeto, "conferencia");
        var (_, _, deFora) = await Pessoa("analista");

        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.GetAsync($"/api/conferencias/{id}")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.GetAsync($"/api/projetos/{projeto}/conferencias")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.GetAsync($"/api/conferencias/{id}/planilhas/a-cobrar")).StatusCode);
    }

    // ------------------------------------------------------------------ planilhas
    [Fact]
    public async Task Planilha_sai_em_fluxo_do_disco_com_tipo_nome_e_o_recorte_pedido()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "conferencia");
        var arquivo = Path.Combine(Trabalho_, $"execucao-{id}", "notas_a_cobrar-59.csv");
        Directory.CreateDirectory(Path.GetDirectoryName(arquivo)!);
        await File.WriteAllBytesAsync(arquivo, [0xEF, 0xBB, 0xBF, (byte)'c', (byte)'h']);
        motor.AoPedirPlanilha = _ => Results.Json(new { caminho = arquivo, nome = "notas_a_cobrar-59.csv", tipo = "text/csv; charset=utf-8" });

        var r = await c.GetAsync($"/api/conferencias/{id}/planilhas/a-cobrar?modelos=59&formato=csv");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.StartsWith("text/csv", r.Content.Headers.ContentType!.ToString());
        Assert.Equal([0xEF, 0xBB, 0xBF, (byte)'c', (byte)'h'], await r.Content.ReadAsByteArrayAsync());
        // a tela tira o nome com filename="?([^";]+)"?
        var disposicao = r.Content.Headers.ContentDisposition!.ToString();
        Assert.Matches("filename=\"?notas_a_cobrar-59.csv\"?(;|$)", disposicao);
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("qual", out _));
        Assert.Equal((id, "conferencia", "a-cobrar", "59", "csv"),
            (pedido.GetProperty("execucao_id").GetInt32(), pedido.GetProperty("etapa").GetString(), pedido.GetProperty("qual").GetString(),
             pedido.GetProperty("modelos").GetString(), pedido.GetProperty("formato").GetString()));
        Assert.Equal(JsonValueKind.Null, pedido.GetProperty("classificacoes").ValueKind);
    }

    [Fact]
    public async Task Formato_padrao_e_xlsx_e_movimentos_manda_a_etapa_da_rota()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "movimentos");
        var arquivo = Path.Combine(Trabalho_, $"execucao-{id}", "movimentos-pendente.xlsx");
        Directory.CreateDirectory(Path.GetDirectoryName(arquivo)!);
        await File.WriteAllBytesAsync(arquivo, "PK"u8.ToArray());
        motor.AoPedirPlanilha = _ => Results.Json(new { caminho = arquivo, nome = "movimentos-pendente.xlsx", tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

        var r = await c.GetAsync($"/api/movimentos/{id}/planilhas/movimentos?classificacoes=pendente");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("qual", out _));
        Assert.Equal("xlsx", pedido.GetProperty("formato").GetString());
        Assert.Equal("movimentos", pedido.GetProperty("etapa").GetString());
        Assert.Equal("pendente", pedido.GetProperty("classificacoes").GetString());
    }

    [Theory]
    [InlineData(409, "A conferência ainda não terminou.")]
    [InlineData(410, "Os arquivos desta conferência não estão mais em disco. Rode a conferência de novo.")]
    [InlineData(404, "Formato desconhecido: ods. Vale xlsx ou csv.")]
    public async Task Recusa_da_planilha_chega_com_o_codigo_e_o_texto_do_motor(int status, string detalhe)
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "conferencia");
        motor.AoPedirPlanilha = _ => Results.Json(new { detail = detalhe }, statusCode: status);

        var r = await c.GetAsync($"/api/conferencias/{id}/planilhas/a-cobrar");

        Assert.Equal(status, (int)r.StatusCode);
        Assert.Equal(detalhe, await Detalhe(r));
    }

    [Fact]
    public async Task Api_nao_serve_arquivo_fora_da_pasta_de_trabalho_nem_se_o_motor_pedir()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "conferencia");
        var fora = Path.Combine(_backend, ".env");
        motor.AoPedirPlanilha = _ => Results.Json(new { caminho = fora, nome = "notas.xlsx", tipo = "text/plain" });

        var r = await c.GetAsync($"/api/conferencias/{id}/planilhas/a-cobrar");

        Assert.Equal(HttpStatusCode.BadGateway, r.StatusCode);
        Assert.DoesNotContain("CAT_", await r.Content.ReadAsStringAsync());
    }
}
