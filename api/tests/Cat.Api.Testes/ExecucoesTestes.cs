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
    public Func<int, JsonElement, Task<IResult>> AoCancelar { get; set; } = (_, _) => Task.FromResult(Results.StatusCode(500));
    public Func<JsonElement, IResult> AoPedirLinhas { get; set; } = _ => Results.StatusCode(500);
    public Func<string, JsonElement, IResult> AoPedirRazao { get; set; } = (_, _) => Results.StatusCode(500);
    public Func<string, JsonElement, IResult> AoPedirRazaoContabil { get; set; } = (_, _) => Results.StatusCode(500);
    public Func<JsonElement, IResult> AoPedirCompetencias { get; set; } = _ => Results.StatusCode(500);
    public Func<string, JsonElement, IResult> AoPedirArquivoDigital { get; set; } = (_, _) => Results.StatusCode(500);

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
        _app.MapPost("/interno/execucoes/{id:int}/cancelar", async (int id, HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.StatusCode(403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            Pedidos.Enqueue(pedido);
            return await AoCancelar(id, pedido);
        });
        _app.MapPost("/interno/suportado/linhas", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.StatusCode(403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            Pedidos.Enqueue(pedido);
            return AoPedirLinhas(pedido);
        });
        _app.MapPost("/interno/apuracao/competencias", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.StatusCode(403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            Pedidos.Enqueue(pedido);
            return AoPedirCompetencias(pedido);
        });
        foreach (var rota in new[] { "arquivo_digital/arquivos", "arquivo_digital/ocorrencias", "pre_validacao/arquivos",
                     "entrega/estabelecimentos" })
            _app.MapPost($"/interno/{rota}", async (HttpContext http) =>
            {
                if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                    return Results.StatusCode(403);
                var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
                Pedidos.Enqueue(pedido);
                return AoPedirArquivoDigital(rota, pedido);
            });
        foreach (var rota in new[] { "fichas", "ficha" })
            _app.MapPost($"/interno/razao/{rota}", async (HttpContext http) =>
            {
                if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                    return Results.StatusCode(403);
                var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
                Pedidos.Enqueue(pedido);
                return AoPedirRazao(rota, pedido);
            });
        foreach (var rota in new[] { "contas", "lancamentos", "estabelecimentos" })
            _app.MapPost($"/interno/razao-contabil/{rota}", async (HttpContext http) =>
            {
                if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                    return Results.StatusCode(403);
                var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
                Pedidos.Enqueue(pedido);
                return AoPedirRazaoContabil(rota, pedido);
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
    [InlineData("suportado", "st_suportado")]
    [InlineData("razao", "razao")]
    [InlineData("apuracao", "apuracao")]
    [InlineData("arquivo-digital", "arquivo_digital")]
    [InlineData("pre-validacao", "pre_validacao")]
    [InlineData("entrega", "entrega")]
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
                      "documentos", "erro", "iniciada_em", "terminada_em", "resumo", "aprovada_por", "aprovada_em"], d.EnumerateObject().Select(x => x.Name));
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

    // ------------------------------------------------------------------ cancelar
    [Fact]
    public async Task Cancelar_repassa_quem_pediu_e_devolve_a_execucao_como_ficou()
    {
        var (quem, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "st_suportado", "rodando", null);
        motor.AoCancelar = async (execucao, _) =>
        {
            await banco.Comando($"UPDATE execucao SET situacao = 'cancelando' WHERE id = {execucao}");
            return Results.Json(new { id = execucao });
        };

        var r = await c.PostAsync($"/api/suportado/{id}/cancelar", null);

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("cancelando", (await Json(r)).GetProperty("situacao").GetString());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("usuario_id", out _) && !x.TryGetProperty("etapa", out _));
        Assert.Equal(quem, pedido.GetProperty("usuario_id").GetInt32());
    }

    [Fact]
    public async Task Cancelar_exige_permissao_e_a_rota_da_etapa_certa()
    {
        var (_, _, dono) = await Pessoa("dev");
        var (empresa, projeto) = await Trabalho(dono);
        var (_, _, leitor) = await Pessoa("leitura", [empresa]);
        var id = await Execucao(projeto, "st_suportado", "rodando", null);
        var movimentos = await Execucao(projeto, "movimentos", "rodando", null);
        motor.AoCancelar = (_, _) => Task.FromResult(Results.Json(new { detail = "Esta rodada já terminou." }, statusCode: 409));

        var doLeitor = await leitor.PostAsync($"/api/suportado/{id}/cancelar", null);
        Assert.Equal(HttpStatusCode.Forbidden, doLeitor.StatusCode);
        Assert.Equal("Você não tem permissão para apurar o ICMS suportado.", await Detalhe(doLeitor));
        // pela rota do suportado, só execução do suportado
        Assert.Equal(HttpStatusCode.NotFound, (await dono.PostAsync($"/api/suportado/{movimentos}/cancelar", null)).StatusCode);
        var recusa = await dono.PostAsync($"/api/suportado/{id}/cancelar", null);
        Assert.Equal(HttpStatusCode.Conflict, recusa.StatusCode);
        Assert.Equal("Esta rodada já terminou.", await Detalhe(recusa));
    }

    // ------------------------------------------------------------------ analítico do suportado
    [Fact]
    public async Task Linhas_repassam_filtro_e_pagina_e_devolvem_o_que_o_motor_montou()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "st_suportado");
        motor.AoPedirLinhas = p => Results.Json(new { escopo = p.GetProperty("escopo").GetString(), pagina = 2, por_pagina = 25, total = 1, linhas = new[] { new { chave = "4" } } });

        var r = await c.GetAsync($"/api/suportado/{id}/linhas?escopo=item&fonte=nao_apuravel&busca=alface&pagina=2&por_pagina=25");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var d = await Json(r);
        Assert.Equal("item", d.GetProperty("escopo").GetString());
        Assert.Equal(1, d.GetProperty("total").GetInt32());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("escopo", out _));
        Assert.Equal((id, "item", "nao_apuravel", "alface", 2, 25),
            (pedido.GetProperty("execucao_id").GetInt32(), pedido.GetProperty("escopo").GetString(), pedido.GetProperty("fonte").GetString(),
             pedido.GetProperty("busca").GetString(), pedido.GetProperty("pagina").GetInt32(), pedido.GetProperty("por_pagina").GetInt32()));
    }

    [Fact]
    public async Task Linhas_sem_filtro_usam_o_padrao_e_de_outra_etapa_nao_existem()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "st_suportado");
        var conferencia = await Execucao(projeto, "conferencia");
        motor.AoPedirLinhas = _ => Results.Json(new { total = 0, linhas = Array.Empty<object>() });

        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync($"/api/suportado/{id}/linhas?pagina=abc")).StatusCode);
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("escopo", out _));
        Assert.Equal(("documento", 1, 50), (pedido.GetProperty("escopo").GetString(), pedido.GetProperty("pagina").GetInt32(), pedido.GetProperty("por_pagina").GetInt32()));
        Assert.Equal(JsonValueKind.Null, pedido.GetProperty("fonte").ValueKind);
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/suportado/{conferencia}/linhas")).StatusCode);
    }

    [Fact]
    public async Task Recusa_das_linhas_chega_com_o_texto_do_motor()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "st_suportado");
        motor.AoPedirLinhas = _ => Results.Json(new { detail = "Escopo desconhecido: tudo. Vale documento ou item." }, statusCode: 422);

        var r = await c.GetAsync($"/api/suportado/{id}/linhas?escopo=tudo");

        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal("Escopo desconhecido: tudo. Vale documento ou item.", await Detalhe(r));
    }

    // ------------------------------------------------------------------ razão
    [Fact]
    public async Task Fichas_do_razao_repassam_busca_recorte_e_pagina()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "razao");
        motor.AoPedirRazao = (rota, _) => Results.Json(new { rota, total = 1, linhas = new[] { new { codigo = "X" } } });

        var r = await c.GetAsync($"/api/razao/{id}/fichas?busca=cola&so=negativas&pagina=3&por_pagina=20");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("fichas", (await Json(r)).GetProperty("rota").GetString());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("so", out _));
        Assert.Equal((id, "cola", "negativas", 3, 20),
            (pedido.GetProperty("execucao_id").GetInt32(), pedido.GetProperty("busca").GetString(),
             pedido.GetProperty("so").GetString(), pedido.GetProperty("pagina").GetInt32(), pedido.GetProperty("por_pagina").GetInt32()));
    }

    [Fact]
    public async Task Linhas_da_ficha_exigem_estabelecimento_e_mercadoria()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "razao");
        var suportado = await Execucao(projeto, "st_suportado");
        motor.AoPedirRazao = (rota, p) => Results.Json(new { rota, cnpj = p.GetProperty("cnpj").GetString(), total = 0, linhas = Array.Empty<object>() });

        var r = await c.GetAsync($"/api/razao/{id}/ficha?cnpj=11111111000191&codigo=X");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("11111111000191", (await Json(r)).GetProperty("cnpj").GetString());

        var sem = await c.GetAsync($"/api/razao/{id}/ficha?codigo=X");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, sem.StatusCode);
        Assert.Equal("Informe o estabelecimento e a mercadoria da ficha.", await Detalhe(sem));
        // pela rota do razão, só execução do razão
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/razao/{suportado}/fichas")).StatusCode);
    }

    // --------------------------------------------------- razão contábil da ECD
    [Fact]
    public async Task Contas_do_razao_contabil_repassam_busca_estabelecimento_e_recorte()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "apuracao_piscofins");
        motor.AoPedirRazaoContabil = (rota, _) => Results.Json(new { rota, total = 2, linhas = new[] { new { conta = "3.1.1" } } });

        var r = await c.GetAsync($"/api/apuracao-piscofins/{id}/contas?busca=caixa&cnpj=11111111000191&so=devedoras&pagina=2&por_pagina=30");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("contas", (await Json(r)).GetProperty("rota").GetString());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("so", out _));
        Assert.Equal((id, "caixa", "11111111000191", "devedoras", 2, 30),
            (pedido.GetProperty("execucao_id").GetInt32(), pedido.GetProperty("busca").GetString(),
             pedido.GetProperty("cnpj").GetString(), pedido.GetProperty("so").GetString(),
             pedido.GetProperty("pagina").GetInt32(), pedido.GetProperty("por_pagina").GetInt32()));
    }

    [Fact]
    public async Task Lancamentos_exigem_estabelecimento_e_conta_e_repassam_o_periodo()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "apuracao_piscofins");
        var razao = await Execucao(projeto, "razao");
        motor.AoPedirRazaoContabil = (rota, p) => Results.Json(new { rota, conta = p.GetProperty("conta").GetString(), total = 0, linhas = Array.Empty<object>() });

        var r = await c.GetAsync($"/api/apuracao-piscofins/{id}/lancamentos?cnpj=11111111000191&conta=3.1.1&de=2021-06-01&ate=2021-06-30");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("3.1.1", (await Json(r)).GetProperty("conta").GetString());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("conta", out _));
        Assert.Equal(("2021-06-01", "2021-06-30"),
            (pedido.GetProperty("de").GetString(), pedido.GetProperty("ate").GetString()));

        var sem = await c.GetAsync($"/api/apuracao-piscofins/{id}/lancamentos?conta=3.1.1");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, sem.StatusCode);
        Assert.Equal("Informe o estabelecimento e a conta do razão.", await Detalhe(sem));
        // o razão da CAT 42 é outra etapa: pela rota da quebra, só execução da quebra
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/apuracao-piscofins/{razao}/contas")).StatusCode);
    }

    [Fact]
    public async Task Estabelecimentos_do_razao_contabil_saem_para_o_filtro()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "apuracao_piscofins");
        motor.AoPedirRazaoContabil = (rota, _) => Results.Json(new { rota, linhas = new[] { new { cnpj = "11111111000191", contas = 4 } } });

        var r = await c.GetAsync($"/api/apuracao-piscofins/{id}/estabelecimentos");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("estabelecimentos", (await Json(r)).GetProperty("rota").GetString());
    }

    // ------------------------------------------------------------------ apuração do período
    [Fact]
    public async Task Competencias_repassam_recorte_e_busca_e_so_valem_na_rota_da_apuracao()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "apuracao");
        var razao = await Execucao(projeto, "razao");
        motor.AoPedirCompetencias = p => Results.Json(new { total = 1, linhas = new[] { new { cnpj = "1", apta = true } }, so = p.GetProperty("so").GetString() });

        var r = await c.GetAsync($"/api/apuracao/{id}/competencias?so=aptas&busca=2021-05&pagina=2&por_pagina=10");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("aptas", (await Json(r)).GetProperty("so").GetString());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("so", out _));
        Assert.Equal((id, "aptas", "2021-05", 2, 10),
            (pedido.GetProperty("execucao_id").GetInt32(), pedido.GetProperty("so").GetString(),
             pedido.GetProperty("busca").GetString(), pedido.GetProperty("pagina").GetInt32(), pedido.GetProperty("por_pagina").GetInt32()));
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/apuracao/{razao}/competencias")).StatusCode);
    }

    // ------------------------------------------------------------------ arquivo digital
    [Fact]
    public async Task Arquivos_e_ocorrencias_repassam_e_so_valem_na_rota_do_arquivo_digital()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = await Execucao(projeto, "arquivo_digital");
        var apuracao = await Execucao(projeto, "apuracao");
        motor.AoPedirArquivoDigital = (rota, p) => Results.Json(new { rota, total = 1 });

        var r = await c.GetAsync($"/api/arquivo-digital/{id}/arquivos?so=previa&busca=2021&pagina=3&por_pagina=20");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("arquivo_digital/arquivos", (await Json(r)).GetProperty("rota").GetString());
        var pedido = motor.Pedidos.Last(x => x.TryGetProperty("so", out _));
        Assert.Equal((id, "previa", "2021", 3, 20),
            (pedido.GetProperty("execucao_id").GetInt32(), pedido.GetProperty("so").GetString(),
             pedido.GetProperty("busca").GetString(), pedido.GetProperty("pagina").GetInt32(), pedido.GetProperty("por_pagina").GetInt32()));

        r = await c.GetAsync($"/api/arquivo-digital/{id}/ocorrencias?arquivo=CAT5_SP_1_2021.txt");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("CAT5_SP_1_2021.txt", motor.Pedidos.Last(x => x.TryGetProperty("nome", out _)).GetProperty("nome").GetString());
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await c.GetAsync($"/api/arquivo-digital/{id}/ocorrencias")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/arquivo-digital/{apuracao}/arquivos")).StatusCode);
    }

    [Fact]
    public async Task Pre_validacao_do_cliente_tem_rotas_proprias_e_nao_se_mistura_com_a_etapa_7()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var pre = await Execucao(projeto, "pre_validacao");
        var gerado = await Execucao(projeto, "arquivo_digital");
        motor.AoPedirArquivoDigital = (rota, p) => Results.Json(new { rota, total = 3 });

        var r = await c.GetAsync($"/api/pre-validacao/{pre}/arquivos?so=com_erro");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("pre_validacao/arquivos", (await Json(r)).GetProperty("rota").GetString());
        r = await c.GetAsync($"/api/pre-validacao/{pre}/ocorrencias?arquivo=CAT5_SP_1_2021.txt");
        Assert.Equal("arquivo_digital/ocorrencias", (await Json(r)).GetProperty("rota").GetString());

        // cada rota só com a sua execução
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/pre-validacao/{gerado}/arquivos")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/arquivo-digital/{pre}/ocorrencias?arquivo=x")).StatusCode);

        // e ela não entra no roteiro do trabalho
        var etapas = (await Json(await c.GetAsync($"/api/projetos/{projeto}"))).GetProperty("etapas");
        Assert.DoesNotContain("pre_validacao", etapas.EnumerateArray().Select(e => e.GetProperty("chave").GetString()));
    }

    // ------------------------------------------------------------------ entrega (etapa 8)
    private Task<int> Entrega(int projeto, int arquivoDigital, string situacao = "concluida") =>
        Execucao(projeto, "entrega", situacao,
            $"{{\"arquivo_digital_execucao_id\": {arquivoDigital}, \"para_envio\": 2, \"ressarcimento_para_envio\": \"10.00\"}}");

    private static async Task<string?> SituacaoDaEtapa(HttpClient c, int projeto, string chave) =>
        (await Json(await c.GetAsync($"/api/projetos/{projeto}"))).GetProperty("etapas").EnumerateArray()
            .Single(e => e.GetProperty("chave").GetString() == chave).GetProperty("situacao").GetString();

    [Fact]
    public async Task Estabelecimentos_da_entrega_repassam_e_so_valem_na_rota_da_entrega()
    {
        var (_, _, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var arquivo = await Execucao(projeto, "arquivo_digital");
        var entrega = await Entrega(projeto, arquivo);
        motor.AoPedirArquivoDigital = (rota, p) => Results.Json(new { rota, so = p.GetProperty("so").GetString(), total = 1 });

        var r = await c.GetAsync($"/api/entrega/{entrega}/estabelecimentos?so=no_dossie&pagina=2");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var corpo = await Json(r);
        Assert.Equal("entrega/estabelecimentos", corpo.GetProperty("rota").GetString());
        Assert.Equal("no_dossie", corpo.GetProperty("so").GetString());
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/entrega/{arquivo}/estabelecimentos")).StatusCode);
    }

    [Fact]
    public async Task Entrega_so_conclui_a_etapa_com_a_aprovacao_de_revisor_ou_gestor()
    {
        var (_, _, dev) = await Pessoa("dev");
        var (empresa, projeto) = await Trabalho(dev);
        var arquivo = await Execucao(projeto, "arquivo_digital");
        var entrega = await Entrega(projeto, arquivo);

        // montada e sem aprovação: a etapa anda, não conclui
        Assert.Equal("em_andamento", await SituacaoDaEtapa(dev, projeto, "entrega"));

        // quem monta não aprova; a conta técnica também não
        var (_, _, analista) = await Pessoa("analista", [empresa]);
        Assert.Equal(HttpStatusCode.Forbidden, (await analista.PostAsync($"/api/entrega/{entrega}/aprovar", null)).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await dev.PostAsync($"/api/entrega/{entrega}/aprovar", null)).StatusCode);

        var (revisorId, _, revisor) = await Pessoa("revisor", [empresa]);
        var r = await revisor.PostAsJsonAsync($"/api/entrega/{entrega}/aprovar", new { observacao = "Conferido com o cliente" });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var aprovada = await Json(r);
        Assert.False(string.IsNullOrEmpty(aprovada.GetProperty("aprovada_por").GetString()));
        Assert.False(string.IsNullOrEmpty(aprovada.GetProperty("aprovada_em").GetString()));
        Assert.Equal(revisorId, await banco.Escalar<int>($"SELECT aprovada_por FROM execucao WHERE id = {entrega}"));

        Assert.Equal("concluida", await SituacaoDaEtapa(dev, projeto, "entrega"));
        var evento = await banco.Escalar<string>(
            $"SELECT texto FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'entrega_aprovada'");
        Assert.Contains("Conferido com o cliente", evento);

        // de novo não
        r = await revisor.PostAsync($"/api/entrega/{entrega}/aprovar", null);
        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
        Assert.Contains("já foi aprovada", await Detalhe(r));
    }

    [Fact]
    public async Task Aprovacao_recusa_entrega_superada_de_arquivo_velho_ou_em_curso()
    {
        var (_, _, gestor) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(gestor);
        var arquivo = await Execucao(projeto, "arquivo_digital");
        var velha = await Entrega(projeto, arquivo);
        var nova = await Entrega(projeto, arquivo);

        var r = await gestor.PostAsync($"/api/entrega/{velha}/aprovar", null);
        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
        Assert.Contains($"#{nova}", await Detalhe(r));

        await Execucao(projeto, "arquivo_digital");      // gerado de novo depois da entrega
        r = await gestor.PostAsync($"/api/entrega/{nova}/aprovar", null);
        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
        Assert.Contains("Monte a entrega de novo", await Detalhe(r));

        var rodando = await Entrega(projeto, arquivo, situacao: "rodando");
        Assert.Equal(HttpStatusCode.Conflict, (await gestor.PostAsync($"/api/entrega/{rodando}/aprovar", null)).StatusCode);
        Assert.Equal("em_andamento", await SituacaoDaEtapa(gestor, projeto, "entrega"));
    }

    [Fact]
    public async Task Aprovacao_com_observacao_longa_demais_e_recusada()
    {
        var (_, _, gestor) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(gestor);
        var entrega = await Entrega(projeto, await Execucao(projeto, "arquivo_digital"));
        var r = await gestor.PostAsJsonAsync($"/api/entrega/{entrega}/aprovar", new { observacao = new string('x', 501) });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal(0L, await banco.Escalar<long>($"SELECT count(*) FROM execucao WHERE id = {entrega} AND aprovada_em IS NOT NULL"));
    }
}
