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

/// <summary>
/// O canal interno do motor, de mentira: registra o pedido de apagar pastas e
/// só responde com o segredo certo, como o <c>interno_router.py</c>.
/// </summary>
public sealed class MotorInternoFalso : IAsyncLifetime
{
    public const string Segredo = "segredo-do-canal-de-teste";
    private WebApplication? _app;
    public Uri Endereco { get; private set; } = null!;
    public ConcurrentQueue<string[]> Pedidos { get; } = new();

    public async Task InitializeAsync()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        _app = builder.Build();
        _app.MapPost("/interno/pastas/apagar", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.Json(new { detail = "Segredo do canal interno não confere." }, statusCode: 403);
            var corpo = await http.Request.ReadFromJsonAsync<JsonElement>();
            var pastas = corpo.GetProperty("pastas").EnumerateArray().Select(p => p.GetString()!).ToArray();
            Pedidos.Enqueue(pastas);
            return Results.Json(new
            {
                apagadas = pastas.Where(p => !p.Contains("fora")).ToArray(),
                recusadas = pastas.Where(p => p.Contains("fora")).ToArray(),
            });
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

/// <summary>
/// Portados de tests/integracao/test_exclusao_api.py (a exclusão de trabalho)
/// e das rotas de empresa e projeto de importacao_router.py.
/// </summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class TrabalhosTestes(BancoDeTeste banco, MotorInternoFalso _motor) : IDisposable, IClassFixture<MotorInternoFalso>
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
        var pasta = Directory.CreateTempSubdirectory("cat-trabalhos-").FullName;
        File.WriteAllText(Path.Combine(pasta, "pyproject.toml"), "version = \"1.2.3\"\n");
        File.WriteAllText(Path.Combine(pasta, ".env"), "");
        return pasta;
    }

    private HttpClient Cliente(Uri? motor = null, string? token = null)
    {
        var fabrica = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", _backend);
            b.UseSetting("CAT_BANCO_URL", banco.Url);
            b.UseSetting("CAT_SENHA_PIMENTA", BancoDeTeste.Pimenta);
            b.UseSetting("CAT_JWT_SEGREDO", BancoDeTeste.Segredo);
            b.UseSetting("CAT_MOTOR_URL", (motor ?? _motor.Endereco).ToString());
            b.UseSetting("CAT_MOTOR_SEGREDO", MotorInternoFalso.Segredo);
        });
        _fabricas.Add(fabrica);
        var cliente = fabrica.CreateClient();
        if (token is not null)
            cliente.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return cliente;
    }

    private async Task<(int Id, string Nome, string Token)> Pessoa(string papel, int[]? empresasIds = null)
    {
        var nome = "t" + Guid.NewGuid().ToString("N")[..10];
        var id = await banco.CriarUsuario(nome, papel: papel);
        foreach (var empresa in empresasIds ?? [])
            await banco.Comando($"INSERT INTO alocacao (usuario_id, empresa_id, papel_projeto, inicio) VALUES ({id}, {empresa}, 'executor', now())");
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario { Id = id, NomeDeUsuario = nome, Email = "x@y.zz", NomeExibicao = nome.ToUpperInvariant(), Papel = p });
        return (id, nome, token);
    }

    /// <summary>Um CNPJ matriz válido e ainda não usado neste banco.</summary>
    private static (string Raiz, string Cnpj) CnpjNovo()
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var doze = raiz + "0001";
        return (raiz, doze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(doze));
    }

    private static async Task<JsonElement> Json(HttpResponseMessage r) => await r.Content.ReadFromJsonAsync<JsonElement>();
    private static async Task<string> Detalhe(HttpResponseMessage r) => (await Json(r)).GetProperty("detail").GetString()!;

    private async Task<int> Empresa(HttpClient c, string? razao = null)
    {
        var (raiz, cnpj) = CnpjNovo();
        var r = await c.PostAsJsonAsync("/api/empresas", new
        {
            cnpj_raiz = raiz, cnpj_matriz = cnpj, razao_social = razao ?? $"EMPRESA {raiz}", uf = "sp", inscricao_estadual = "",
        });
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        return (await Json(r)).GetProperty("id").GetInt32();
    }

    private static async Task<int> Projeto(HttpClient c, int empresa, string? nome = null)
    {
        var r = await c.PostAsJsonAsync("/api/projetos", new
        {
            empresa_id = empresa, frente = "cat42", nome = nome ?? "Trabalho " + Guid.NewGuid().ToString("N")[..6],
            competencia_ini = "2021-05-01", competencia_fim = "2021-05-01", observacao = (string?)null,
        });
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        return (await Json(r)).GetProperty("id").GetInt32();
    }

    // ------------------------------------------------------------------ empresas
    [Fact]
    public async Task Cadastrar_empresa_aloca_quem_cadastrou_e_grava_a_matriz()
    {
        var (id, _, token) = await Pessoa("analista");
        var c = Cliente(token: token);
        var (raiz, cnpj) = CnpjNovo();

        var r = await c.PostAsJsonAsync("/api/empresas", new
            { cnpj_raiz = raiz, cnpj_matriz = cnpj.Insert(2, "."), razao_social = "  EMPRESA NOVA  ", uf = "sp", inscricao_estadual = "" });

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var e = await Json(r);
        Assert.Equal(["id", "cnpj_raiz", "cnpj_matriz", "cnpj_matriz_formatado", "razao_social", "uf", "inscricao_estadual", "pre_cadastro", "projetos"],
            e.EnumerateObject().Select(p => p.Name));
        Assert.Equal(cnpj, e.GetProperty("cnpj_matriz").GetString());
        Assert.Equal("EMPRESA NOVA", e.GetProperty("razao_social").GetString());
        Assert.Equal("SP", e.GetProperty("uf").GetString());
        Assert.Equal(JsonValueKind.Null, e.GetProperty("inscricao_estadual").ValueKind);
        Assert.True(e.GetProperty("pre_cadastro").GetBoolean());
        var empresa = e.GetProperty("id").GetInt32();
        Assert.Equal("responsavel", await banco.Escalar<string>($"SELECT papel_projeto FROM alocacao WHERE usuario_id = {id} AND empresa_id = {empresa} AND fim IS NULL"));
        Assert.True(await banco.Escalar<bool>($"SELECT e_matriz FROM estabelecimento WHERE empresa_id = {empresa} AND cnpj = '{cnpj}'"));

        // e em seguida enxerga o que cadastrou
        var lista = (await Json(await c.GetAsync("/api/empresas"))).EnumerateArray().Select(x => x.GetProperty("id").GetInt32());
        Assert.Contains(empresa, lista);
    }

    [Fact]
    public async Task Empresa_recusa_cnpj_invalido_raiz_errada_e_repetida()
    {
        var (_, _, token) = await Pessoa("analista");
        var c = Cliente(token: token);
        var (raiz, cnpj) = CnpjNovo();

        var invalido = await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = raiz + "000100", razao_social = "X X", uf = "SP" });
        var raizErrada = await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = "12345678", cnpj_matriz = cnpj, razao_social = "X X", uf = "SP" });
        await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = cnpj, razao_social = "X X", uf = "SP" });
        var repetida = await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = cnpj, razao_social = "X X", uf = "SP" });

        Assert.Equal(HttpStatusCode.UnprocessableEntity, invalido.StatusCode);
        Assert.Contains("dígito verificador", await Detalhe(invalido));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, raizErrada.StatusCode);
        Assert.Equal("A raiz informada não é a do CNPJ da matriz.", await Detalhe(raizErrada));
        Assert.Equal(HttpStatusCode.Conflict, repetida.StatusCode);
        Assert.Equal($"A empresa de raiz {raiz} já está cadastrada.", await Detalhe(repetida));
    }

    [Fact]
    public async Task Leitura_nao_cadastra_e_lista_de_empresas_respeita_o_escopo()
    {
        var (_, _, tokenGestor) = await Pessoa("gestor");
        var gestor = Cliente(token: tokenGestor);
        var alcancada = await Empresa(gestor);
        var outra = await Empresa(gestor);
        var (_, _, tokenLeitura) = await Pessoa("leitura", [alcancada]);
        var leitura = Cliente(token: tokenLeitura);

        var (raiz, cnpj) = CnpjNovo();
        var cria = await leitura.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = cnpj, razao_social = "X X", uf = "SP" });
        var ids = (await Json(await leitura.GetAsync("/api/empresas"))).EnumerateArray().Select(x => x.GetProperty("id").GetInt32()).ToList();

        Assert.Equal(HttpStatusCode.Forbidden, cria.StatusCode);
        Assert.Equal("Você não tem permissão para importar arquivos.", await Detalhe(cria));
        Assert.Contains(alcancada, ids);
        Assert.DoesNotContain(outra, ids);
    }

    [Fact]
    public async Task Frentes_sao_abertas_e_na_ordem()
    {
        var r = await Cliente().GetAsync("/api/frentes");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(["cat42", "depara", "sped", "notafiscal"], (await Json(r)).EnumerateObject().Select(p => p.Name));
    }

    // ------------------------------------------------------------------ projetos
    [Fact]
    public async Task Criar_projeto_grava_quem_responde_o_evento_e_devolve_o_cartao()
    {
        var (id, nome, token) = await Pessoa("analista");
        var c = Cliente(token: token);
        var empresa = await Empresa(c, "EMPRESA DO CARTAO");

        var r = await c.PostAsJsonAsync("/api/projetos", new
            { empresa_id = empresa, frente = "cat42", nome = "  Trabalho com história ", competencia_ini = "2021-05-01", competencia_fim = "2021-05-31" });

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var p = await Json(r);
        Assert.Equal(
            ["id", "empresa_id", "empresa", "cnpj_matriz", "cnpj_matriz_formatado", "uf", "frente", "frente_rotulo", "nome",
             "competencia_ini", "competencia_fim", "status", "status_rotulo", "pre_cadastro", "etapas_feitas", "etapas_totais",
             "criado_por", "criado_por_id", "responsavel", "responsavel_id", "comentarios"],
            p.EnumerateObject().Select(x => x.Name));
        Assert.Equal("Trabalho com história", p.GetProperty("nome").GetString());
        Assert.Equal("EMPRESA DO CARTAO", p.GetProperty("empresa").GetString());
        Assert.Equal("CAT 42 — ressarcimento de ICMS-ST", p.GetProperty("frente_rotulo").GetString());
        Assert.Equal("2021-05-31", p.GetProperty("competencia_fim").GetString());
        Assert.Equal("Em andamento", p.GetProperty("status_rotulo").GetString());
        Assert.Equal(nome.ToUpperInvariant(), p.GetProperty("criado_por").GetString());
        Assert.Equal(id, p.GetProperty("responsavel_id").GetInt32());
        Assert.Equal(0, p.GetProperty("etapas_feitas").GetInt32());
        Assert.Equal(6, p.GetProperty("etapas_totais").GetInt32());

        // o evento "criado" no formato que o histórico em Python lê
        var projeto = p.GetProperty("id").GetInt32();
        Assert.Equal("criado", await banco.Escalar<string>($"SELECT tipo FROM evento_do_projeto WHERE projeto_id = {projeto}"));
        Assert.Equal("CAT 42 — ressarcimento de ICMS-ST · Trabalho com história",
            await banco.Escalar<string>($"SELECT texto FROM evento_do_projeto WHERE projeto_id = {projeto}"));
        Assert.Equal("2021-05-31", await banco.Escalar<string>($"SELECT dados->>'competencia_fim' FROM evento_do_projeto WHERE projeto_id = {projeto}"));
        Assert.Equal(nome.ToUpperInvariant(), await banco.Escalar<string>($"SELECT autor_nome FROM evento_do_projeto WHERE projeto_id = {projeto}"));
    }

    [Theory]
    [InlineData("""{"frente":"cat99","nome":"Trabalho","competencia_ini":"2021-05-01","competencia_fim":"2021-05-01"}""", 422, "Frente desconhecida. Use uma de: cat42, depara, sped, notafiscal.")]
    [InlineData("""{"frente":"cat42","nome":"Trabalho","competencia_ini":"2021-06-01","competencia_fim":"2021-05-01"}""", 422, "A competência final não pode ser anterior à inicial.")]
    [InlineData("""{"frente":"cat42","nome":"T","competencia_ini":"2021-05-01","competencia_fim":"2021-05-01"}""", 422, "2 caracteres")]
    [InlineData("""{"frente":"cat42","nome":"Trabalho","competencia_ini":"05/2021","competencia_fim":"2021-05-01"}""", 422, "AAAA-MM-DD")]
    public async Task Projeto_invalido_e_recusado(string corpoSemEmpresa, int status, string pedaco)
    {
        var (_, _, token) = await Pessoa("gestor");
        var c = Cliente(token: token);
        var empresa = await Empresa(c);
        var corpo = corpoSemEmpresa.Insert(1, $"\"empresa_id\":{empresa},");

        var r = await c.PostAsync("/api/projetos", new StringContent(corpo, System.Text.Encoding.UTF8, "application/json"));

        Assert.Equal(status, (int)r.StatusCode);
        Assert.Contains(pedaco, await Detalhe(r));
    }

    [Fact]
    public async Task Projeto_repetido_ou_de_empresa_inexistente()
    {
        var (_, _, token) = await Pessoa("gestor");
        var c = Cliente(token: token);
        var empresa = await Empresa(c);
        await Projeto(c, empresa, "Mesmo nome");

        var repetido = await c.PostAsJsonAsync("/api/projetos", new { empresa_id = empresa, frente = "cat42", nome = " Mesmo nome ", competencia_ini = "2021-05-01", competencia_fim = "2021-05-01" });
        var semEmpresa = await c.PostAsJsonAsync("/api/projetos", new { empresa_id = 999999, frente = "cat42", nome = "Outro", competencia_ini = "2021-05-01", competencia_fim = "2021-05-01" });

        Assert.Equal(HttpStatusCode.Conflict, repetido.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, semEmpresa.StatusCode);
        Assert.Equal("Empresa não encontrada.", await Detalhe(semEmpresa));
    }

    [Fact]
    public async Task Nao_cria_projeto_em_empresa_que_nao_enxerga()
    {
        // o Python deixava; em seguida a pessoa não via o que acabara de criar
        var (_, _, tokenGestor) = await Pessoa("gestor");
        var empresa = await Empresa(Cliente(token: tokenGestor));
        var (_, _, tokenAnalista) = await Pessoa("analista");

        var r = await Cliente(token: tokenAnalista).PostAsJsonAsync("/api/projetos",
            new { empresa_id = empresa, frente = "cat42", nome = "Intruso", competencia_ini = "2021-05-01", competencia_fim = "2021-05-01" });

        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("Você não tem acesso a esta empresa.", await Detalhe(r));
    }

    [Fact]
    public async Task Detalhe_calcula_as_etapas_pelo_que_o_motor_gravou()
    {
        var (_, _, token) = await Pessoa("gestor");
        var c = Cliente(token: token);
        var projeto = await Projeto(c, await Empresa(c));
        async Task<Dictionary<string, string>> Etapas()
        {
            var d = await Json(await c.GetAsync($"/api/projetos/{projeto}"));
            return d.GetProperty("etapas").EnumerateArray().ToDictionary(e => e.GetProperty("chave").GetString()!, e => e.GetProperty("situacao").GetString()!);
        }

        Assert.Equal("pendente", (await Etapas())["importar"]);

        // lote sem arquivo útil não conta como base
        await banco.Comando($"INSERT INTO lote (projeto_id, pasta, total_arquivos, arquivos_uteis, bytes_totais) VALUES ({projeto}, 'Z:/vazio', 3, 0, 0)");
        Assert.Equal("pendente", (await Etapas())["importar"]);

        await banco.Comando($"INSERT INTO lote (projeto_id, pasta, total_arquivos, arquivos_uteis, bytes_totais) VALUES ({projeto}, 'Z:/base', 3, 2, 10)");
        await banco.Comando($"INSERT INTO execucao (projeto_id, etapa, situacao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos) VALUES ({projeto}, 'conferencia', 'rodando', 0, 0, 0, 0)");
        var e = await Etapas();
        Assert.Equal("concluida", e["importar"]);
        Assert.Equal("em_andamento", e["conferencia"]);
        Assert.Equal("bloqueada", e["movimentos"]);

        // vale a ÚLTIMA rodada: uma concluída depois de uma que falhou conclui
        await banco.Comando($"UPDATE execucao SET situacao = 'falhou' WHERE projeto_id = {projeto}");
        await banco.Comando($"INSERT INTO execucao (projeto_id, etapa, situacao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos) VALUES ({projeto}, 'conferencia', 'concluida', 0, 0, 0, 0)");
        e = await Etapas();
        Assert.Equal("concluida", e["conferencia"]);
        Assert.Equal("pendente", e["movimentos"]);

        // a apuração do suportado entra no roteiro; "cancelando" ainda é andamento
        await banco.Comando($"INSERT INTO execucao (projeto_id, etapa, situacao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos) VALUES ({projeto}, 'movimentos', 'concluida', 0, 0, 0, 0)");
        await banco.Comando($"INSERT INTO execucao (projeto_id, etapa, situacao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos) VALUES ({projeto}, 'st_suportado', 'cancelando', 0, 0, 0, 0)");
        e = await Etapas();
        Assert.Equal("em_andamento", e["st_suportado"]);
        await banco.Comando($"UPDATE execucao SET situacao = 'concluida' WHERE projeto_id = {projeto} AND etapa = 'st_suportado'");
        Assert.Equal("concluida", (await Etapas())["st_suportado"]);
        await banco.Comando($"DELETE FROM execucao WHERE projeto_id = {projeto} AND etapa IN ('movimentos', 'st_suportado')");

        var cartao = (await Json(await c.GetAsync($"/api/projetos/{projeto}"))).GetProperty("projeto");
        Assert.Equal(2, cartao.GetProperty("etapas_feitas").GetInt32());
        var etapa = (await Json(await c.GetAsync($"/api/projetos/{projeto}"))).GetProperty("etapas")[0];
        Assert.Equal(["chave", "nome", "descricao", "situacao", "situacao_rotulo", "implementada", "acessivel"], etapa.EnumerateObject().Select(p => p.Name));
    }

    [Fact]
    public async Task Listagem_e_detalhe_respeitam_o_escopo_e_contam_comentarios()
    {
        var (_, _, tokenGestor) = await Pessoa("gestor");
        var gestor = Cliente(token: tokenGestor);
        var empresa = await Empresa(gestor);
        var projeto = await Projeto(gestor, empresa);
        await banco.Comando($"INSERT INTO evento_do_projeto (projeto_id, tipo, texto, autor_nome, criado_em) VALUES ({projeto}, 'comentario', 'oi', 'X', now())");
        var (_, _, tokenFora) = await Pessoa("analista");
        var fora = Cliente(token: tokenFora);

        var doGestor = (await Json(await gestor.GetAsync("/api/projetos"))).EnumerateArray().Single(p => p.GetProperty("id").GetInt32() == projeto);
        var listaFora = (await Json(await fora.GetAsync("/api/projetos"))).EnumerateArray().Select(p => p.GetProperty("id").GetInt32());
        var detalheFora = await fora.GetAsync($"/api/projetos/{projeto}");

        Assert.Equal(1, doGestor.GetProperty("comentarios").GetInt32());
        Assert.DoesNotContain(projeto, listaFora);
        Assert.Equal(HttpStatusCode.Forbidden, detalheFora.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await gestor.GetAsync("/api/projetos/999999")).StatusCode);
    }

    // ------------------------------------------------------------------ exclusão
    /// <summary>Um trabalho com um lote de um arquivo e uma conferência que gravou pasta.</summary>
    private async Task<(int Projeto, int Empresa, string Pasta)> TrabalhoComBase(HttpClient c)
    {
        var empresa = await Empresa(c, "EMPRESA DA EXCLUSAO");
        var projeto = await Projeto(c, empresa);
        var pasta = Path.Combine(Path.GetTempPath(), "cat-trabalho", $"execucao-{projeto}");
        await banco.Comando($"INSERT INTO lote (projeto_id, pasta, total_arquivos, arquivos_uteis, bytes_totais) VALUES ({projeto}, 'Z:/base', 1, 1, 10)");
        await banco.Comando($"INSERT INTO arquivo_do_lote (lote_id, caminho, nome, tamanho, tipo) SELECT id, 'Z:/base/efd.txt', 'efd.txt', 10, 'efd_icms' FROM lote WHERE projeto_id = {projeto}");
        await banco.Comando($"INSERT INTO execucao (projeto_id, etapa, situacao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos, pasta_de_trabalho) VALUES ({projeto}, 'conferencia', 'concluida', 1, 1, 10, 2, '{pasta}')");
        return (projeto, empresa, pasta);
    }

    private static HttpRequestMessage Apagar(int projeto, object corpo) =>
        new(HttpMethod.Delete, $"/api/projetos/{projeto}") { Content = JsonContent.Create(corpo) };

    [Fact]
    public async Task Analista_nao_apaga_nem_ve_a_previa_e_sem_token_nao_entra()
    {
        var (_, _, tokenGestor) = await Pessoa("gestor");
        var (projeto, empresa, _) = await TrabalhoComBase(Cliente(token: tokenGestor));
        var (_, _, tokenAnalista) = await Pessoa("analista", [empresa]);
        var analista = Cliente(token: tokenAnalista);

        var apaga = await analista.SendAsync(Apagar(projeto, new { senha = BancoDeTeste.SenhaPadrao }));
        var previa = await analista.GetAsync($"/api/projetos/{projeto}/exclusao");
        var semToken = await Cliente().SendAsync(Apagar(projeto, new { senha = BancoDeTeste.SenhaPadrao }));

        Assert.Equal(HttpStatusCode.Forbidden, apaga.StatusCode);
        Assert.Contains("permissão", await Detalhe(apaga));
        Assert.Equal(HttpStatusCode.Forbidden, previa.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, semToken.StatusCode);
        // e o trabalho continua lá, visível para quem tem a empresa
        Assert.Equal(HttpStatusCode.OK, (await analista.GetAsync($"/api/projetos/{projeto}")).StatusCode);
    }

    [Fact]
    public async Task Senha_errada_nao_apaga_nao_chama_o_motor_e_nao_bloqueia_o_login()
    {
        var (dono, _, token) = await Pessoa("dev");
        var c = Cliente(token: token);
        var (projeto, _, pasta) = await TrabalhoComBase(c);

        for (var i = 0; i < 6; i++)
        {
            var r = await c.SendAsync(Apagar(projeto, new { senha = "senha errada" }));
            Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
            Assert.Equal("Senha incorreta. O trabalho não foi apagado.", await Detalhe(r));
        }
        var vazia = await c.SendAsync(Apagar(projeto, new { senha = "" }));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, vazia.StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync($"/api/projetos/{projeto}")).StatusCode);
        Assert.DoesNotContain(_motor.Pedidos, p => p.Contains(pasta));
        // errar a confirmação não pode trancar a pessoa fora do sistema
        Assert.Equal(0, await banco.Escalar<int>($"SELECT tentativas_falhas FROM usuario WHERE id = {dono}"));
    }

    [Fact]
    public async Task Previa_diz_o_que_some_e_apagar_leva_tudo_menos_a_empresa()
    {
        var (_, _, token) = await Pessoa("gestor");
        var c = Cliente(token: token);
        var (projeto, empresa, pasta) = await TrabalhoComBase(c);

        var previa = await Json(await c.GetAsync($"/api/projetos/{projeto}/exclusao"));
        Assert.Equal(["projeto", "empresa", "lotes", "arquivos", "execucoes"], previa.EnumerateObject().Select(p => p.Name));
        Assert.Equal("EMPRESA DA EXCLUSAO", previa.GetProperty("empresa").GetString());
        Assert.Equal((1, 1, 1), (previa.GetProperty("lotes").GetInt32(), previa.GetProperty("arquivos").GetInt32(), previa.GetProperty("execucoes").GetInt32()));

        var r = await c.SendAsync(Apagar(projeto, new { senha = BancoDeTeste.SenhaPadrao }));

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(1, (await Json(r)).GetProperty("lotes").GetInt32());
        // a pasta de trabalho foi pedida ao motor, com o segredo
        Assert.Contains(_motor.Pedidos, p => p.SequenceEqual([pasta]));
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync($"/api/projetos/{projeto}")).StatusCode);
        foreach (var tabela in new[] { "projeto WHERE id", "lote WHERE projeto_id", "execucao WHERE projeto_id", "evento_do_projeto WHERE projeto_id" })
            Assert.Equal(0, await banco.Escalar<long>($"SELECT count(*) FROM {tabela} = {projeto}"));
        Assert.Equal(0, await banco.Escalar<long>("SELECT count(*) FROM arquivo_do_lote WHERE lote_id NOT IN (SELECT id FROM lote)"));
        // outros trabalhos da mesma empresa não podem ser levados junto
        Assert.Equal(1, await banco.Escalar<long>($"SELECT count(*) FROM empresa WHERE id = {empresa}"));
    }

    [Fact]
    public async Task Motor_fora_do_ar_nao_apaga_nada()
    {
        var (_, _, token) = await Pessoa("gestor");
        var c = Cliente(token: token);
        var (projeto, _, _) = await TrabalhoComBase(c);

        var r = await Cliente(motor: new Uri("http://127.0.0.1:9"), token: token)
            .SendAsync(Apagar(projeto, new { senha = BancoDeTeste.SenhaPadrao }));

        Assert.Equal(HttpStatusCode.BadGateway, r.StatusCode);
        Assert.Equal("O motor do sistema não respondeu. O trabalho não foi apagado.", await Detalhe(r));
        Assert.Equal(1, await banco.Escalar<long>($"SELECT count(*) FROM projeto WHERE id = {projeto}"));
    }

    [Fact]
    public async Task Trabalho_sem_execucao_apaga_sem_precisar_do_motor()
    {
        var (_, _, token) = await Pessoa("gestor");
        var projeto = await Projeto(Cliente(token: token), await Empresa(Cliente(token: token)));

        var r = await Cliente(motor: new Uri("http://127.0.0.1:9"), token: token)
            .SendAsync(Apagar(projeto, new { senha = BancoDeTeste.SenhaPadrao }));

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
    }

    [Fact]
    public async Task Trabalho_inexistente_da_404()
    {
        var (_, _, token) = await Pessoa("gestor");
        var r = await Cliente(token: token).SendAsync(Apagar(999999, new { senha = BancoDeTeste.SenhaPadrao }));
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        Assert.Equal("Trabalho não encontrado.", await Detalhe(r));
    }
}
