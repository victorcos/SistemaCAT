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
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.DependencyInjection;

namespace Cat.Api.Testes;

/// <summary>
/// O canal interno do motor para lote e remessa, de mentira. A pasta pedida
/// escolhe o cenário, como uma pasta de verdade escolheria o que o classificador acha.
/// </summary>
public sealed class MotorDeLotesFalso : IAsyncLifetime
{
    public const string Segredo = "segredo-do-canal-de-lotes";
    private WebApplication? _app;
    public Uri Endereco { get; private set; } = null!;
    public ConcurrentQueue<long> BytesDeRemessa { get; } = new();

    /// <summary>
    /// Como o motor devolve um arquivo. `alimenta` sai de lá pronto, medido
    /// contra o módulo do trabalho — aqui o do lote, que é ICMS salvo quando o
    /// teste pede outro.
    /// </summary>
    public static object Arquivo(string nome, string tipo, string? competencia = "2025-01-01", bool ja = false,
        bool retificadora = false, string? hash = null, long tamanho = 100, string? noTrabalho = null,
        string modulo = "icms") => new
    {
        nome, caminho = $"Z:/base/{nome}", tamanho, tipo, cnpj = "77665544000105", competencia, uf = "SP",
        detalhe = tipo == "xml_compactado" ? "3577 XML" : "", motivo = tipo == "desconhecido" ? "sem cabeçalho" : "",
        retificadora, hash_conteudo = hash, ja_no_trabalho = ja || noTrabalho is not null, tipo_no_trabalho = noTrabalho,
        alimenta = Cat.Dominio.Lote.TiposDeArquivo.Buscar(tipo).Alimenta(modulo),
    };

    public async Task InitializeAsync()
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.WebHost.ConfigureKestrel(k => k.Limits.MaxRequestBodySize = null);
        _app = builder.Build();

        _app.MapPost("/interno/lotes/inspecionar", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.Json(new { detail = "Segredo do canal interno não confere." }, statusCode: 403);
            var pedido = await http.Request.ReadFromJsonAsync<JsonElement>();
            var pasta = pedido.GetProperty("pasta").GetString()!;
            if (pedido.GetProperty("projeto_id").GetInt32() == 999999)
                return Results.Json(new { detail = "Trabalho não encontrado." }, statusCode: 404);

            object[] arquivos = pasta switch
            {
                "Z:/nao-existe" => [],
                "Z:/so-copias" => [],
                "Z:/sem-cat" => [Arquivo("contribuicoes.txt", "sped_contribuicoes")],
                // a MESMA Contribuições, num trabalho de PIS/COFINS: ali ela alimenta
                "Z:/piscofins" => [Arquivo("contribuicoes.txt", "sped_contribuicoes", modulo: "piscofins")],
                "Z:/ja-no-trabalho" => [Arquivo("efd.txt", "sped_icms_ipi", ja: true)],
                "Z:/metade" => [Arquivo("efd.txt", "sped_icms_ipi", ja: true), Arquivo("junho.txt", "sped_icms_ipi", "2025-06-01")],
                "Z:/grande" => Enumerable.Range(0, 1500).Select(i => Arquivo($"nota{i:0000}.xml", "xml_nfe", tamanho: 10)).ToArray(),
                // antes da v0.54: o zip era só compactado
                "Z:/antes" => [Arquivo("efd.txt", "sped_icms_ipi"), Arquivo("portal.zip", "compactado", null)],
                // a mesma pasta lida hoje: o zip é de XML, e a EFD não mudou
                "Z:/hoje" => [Arquivo("efd.txt", "sped_icms_ipi", noTrabalho: "sped_icms_ipi"),
                              Arquivo("portal.zip", "xml_compactado", null, noTrabalho: "compactado")],
                "Z:/hoje-com-novo" => [Arquivo("efd.txt", "sped_icms_ipi", noTrabalho: "sped_icms_ipi"),
                                       Arquivo("portal.zip", "xml_compactado", null, noTrabalho: "compactado"),
                                       Arquivo("fevereiro.txt", "sped_icms_ipi", "2025-02-01")],
                _ => [
                    Arquivo("efd_jan.txt", "sped_icms_ipi", "2025-01-01", hash: "abc123"),
                    Arquivo("efd_mar_retif.txt", "sped_icms_ipi", "2025-03-01", retificadora: true),
                    Arquivo("contribuicoes_2021.txt", "sped_contribuicoes", "2021-06-01"),
                    Arquivo("lixo.bin", "desconhecido", null),
                ],
            };
            if (pasta == "Z:/nao-existe")
                return Results.Json(new { detail = "'Z:/nao-existe' não existe ou não está acessível desta máquina." }, statusCode: 422);
            var serve = pasta is not ("Z:/sem-cat" or "Z:/so-copias");
            var modulo = pasta == "Z:/piscofins" ? "piscofins" : "icms";
            return Results.Json(new
            {
                pasta, modulo, arquivos, de_outra_empresa = pasta == "Z:/base" ? 1 : 0, copias = pasta == "Z:/so-copias" ? 3 : 0,
                serve, competencias = serve ? new[] { "2025-01-01", "2025-03-01" } : [], cnpjs = new[] { "77665544000105" },
                avisos = new[] { "1 arquivo(s) são de outra empresa (11222333000181) e ficaram de fora." },
            });
        });

        _app.MapPost("/interno/remessas/analisar", async (HttpContext http) =>
        {
            if (http.Request.Headers["X-Cat-Motor-Segredo"] != Segredo)
                return Results.Json(new { detail = "Segredo do canal interno não confere." }, statusCode: 403);
            var formulario = await http.Request.ReadFormAsync();
            var arquivo = formulario.Files["arquivo"]!;
            await using var fluxo = arquivo.OpenReadStream();
            var bytes = 0L;
            var buffer = new byte[81920];
            for (int lidos; (lidos = await fluxo.ReadAsync(buffer)) > 0;)
                bytes += lidos;
            BytesDeRemessa.Enqueue(bytes);
            if (arquivo.FileName == "nada.txt")
                return Results.Json(new { detail = "Nenhum arquivo da remessa foi reconhecido como SPED." }, statusCode: 422);
            var raiz = Path.GetFileNameWithoutExtension(arquivo.FileName);
            return Results.Json(new
            {
                razao_social = "EMPRESA DA REMESSA", cnpj_raiz = raiz, total_arquivos = 1, avisos = Array.Empty<string>(),
                matriz = new { cnpj = raiz + "000100", e_matriz = true }, bytes,
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

/// <summary>Portados de test_lote_api.py, test_duplicidade_api.py e da remoção de lote de test_exclusao_api.py.</summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class LotesTestes(BancoDeTeste banco, MotorDeLotesFalso motor) : IDisposable, IClassFixture<MotorDeLotesFalso>
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
        var pasta = Directory.CreateTempSubdirectory("cat-lotes-").FullName;
        File.WriteAllText(Path.Combine(pasta, "pyproject.toml"), "version = \"1.2.3\"\n");
        File.WriteAllText(Path.Combine(pasta, ".env"), "");
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
            b.UseSetting("CAT_MOTOR_SEGREDO", MotorDeLotesFalso.Segredo);
        });
        _fabricas.Add(fabrica);
        var c = fabrica.CreateClient();
        c.Timeout = TimeSpan.FromMinutes(5);
        if (token is not null)
            c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    private async Task<(int Id, HttpClient Cliente)> Pessoa(string papel, int[]? empresas = null)
    {
        var nome = "l" + Guid.NewGuid().ToString("N")[..10];
        var id = await banco.CriarUsuario(nome, papel: papel);
        foreach (var e in empresas ?? [])
            await banco.Comando($"INSERT INTO alocacao (usuario_id, empresa_id, papel_projeto, inicio) VALUES ({id}, {e}, 'executor', now())");
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario { Id = id, NomeDeUsuario = nome, Email = "x@y.zz", NomeExibicao = "Analista do Lote", Papel = p });
        return (id, Cliente(token));
    }

    private static async Task<(int Empresa, int Projeto)> Trabalho(HttpClient c, string modulo = "icms")
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var doze = raiz + "0001";
        var r = await c.PostAsJsonAsync("/api/empresas", new { cnpj_raiz = raiz, cnpj_matriz = doze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(doze), razao_social = "EMPRESA DO LOTE", uf = "SP" });
        var empresa = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        r = await c.PostAsJsonAsync("/api/projetos", new { empresa_id = empresa, frente = "cat42", modulo, nome = "Lote " + Guid.NewGuid().ToString("N")[..6], competencia_ini = "2025-01-01", competencia_fim = "2025-12-01" });
        return (empresa, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32());
    }

    private static async Task<JsonElement> Json(HttpResponseMessage r) => await r.Content.ReadFromJsonAsync<JsonElement>();
    private static async Task<string> Detalhe(HttpResponseMessage r) => (await Json(r)).GetProperty("detail").GetString()!;
    private static Task<HttpResponseMessage> Inspecionar(HttpClient c, int projeto, string pasta) =>
        c.PostAsJsonAsync($"/api/projetos/{projeto}/lotes/inspecionar", new { pasta });
    private static Task<HttpResponseMessage> Registrar(HttpClient c, int projeto, string pasta, string? observacao = null) =>
        c.PostAsJsonAsync($"/api/projetos/{projeto}/lotes", new { pasta, observacao });

    // ------------------------------------------------------------------ o trabalho decide o que é útil
    [Fact]
    public async Task Pasta_de_contribuicoes_entra_no_trabalho_de_piscofins()
    {
        // a MESMA pasta que a CAT 42 recusa: num trabalho de PIS/COFINS ela é a base.
        // Antes o sistema media tudo pela CAT e recusava a importação inteira.
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c, "piscofins");

        var inspecao = await Json(await Inspecionar(c, projeto, "Z:/piscofins"));
        Assert.True(inspecao.GetProperty("serve").GetBoolean());
        Assert.Equal(1, inspecao.GetProperty("arquivos_uteis").GetInt32());
        Assert.True(inspecao.GetProperty("contagens")[0].GetProperty("alimenta").GetBoolean());

        var r = await Registrar(c, projeto, "Z:/piscofins");
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var lote = await Json(r);
        Assert.Equal(1, lote.GetProperty("arquivos_uteis").GetInt32());
        // o período do lote é o do arquivo que ESTE trabalho lê
        Assert.Equal("2025-01-01", lote.GetProperty("competencia_ini").GetString());
    }

    [Fact]
    public async Task A_mesma_pasta_continua_recusada_no_trabalho_de_icms()
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);

        var r = await Registrar(c, projeto, "Z:/sem-cat");

        Assert.Equal(HttpStatusCode.UnprocessableContent, r.StatusCode);
        var detalhe = await Detalhe(r);
        Assert.Contains("alimenta o trabalho de ICMS", detalhe);
        Assert.Contains("EFD ICMS/IPI", detalhe);
    }

    // ------------------------------------------------------------------ inspecionar
    [Fact]
    public async Task Inspecao_diz_o_que_ha_no_formato_da_tela_sem_gravar_nada()
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);

        var r = await Inspecionar(c, projeto, "Z:/base");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var corpo = await Json(r);
        Assert.Equal(["pasta", "total_arquivos", "arquivos_uteis", "bytes_totais", "de_outra_empresa", "serve", "competencia_ini",
                      "competencia_fim", "cnpjs", "contagens", "avisos", "amostra", "ja_no_trabalho", "copias", "reclassificados"],
            corpo.EnumerateObject().Select(p => p.Name));
        Assert.Equal(4, corpo.GetProperty("total_arquivos").GetInt32());
        Assert.Equal(2, corpo.GetProperty("arquivos_uteis").GetInt32());
        Assert.Equal(400, corpo.GetProperty("bytes_totais").GetInt64());
        Assert.Equal(1, corpo.GetProperty("de_outra_empresa").GetInt32());
        Assert.Equal("2025-01-01", corpo.GetProperty("competencia_ini").GetString());
        Assert.Equal("2025-03-01", corpo.GetProperty("competencia_fim").GetString());
        Assert.Contains("outra empresa", corpo.GetProperty("avisos")[0].GetString());

        // o que serve primeiro, e dentro disso o mais numeroso
        var contagens = corpo.GetProperty("contagens").EnumerateArray().ToList();
        Assert.Equal(["sped_icms_ipi", "sped_contribuicoes", "desconhecido"], contagens.Select(x => x.GetProperty("tipo").GetString()));
        Assert.Equal(["tipo", "rotulo", "grupo", "alimenta", "quantidade"], contagens[0].EnumerateObject().Select(p => p.Name));
        Assert.Equal("EFD ICMS/IPI", contagens[0].GetProperty("rotulo").GetString());
        Assert.Equal(2, contagens[0].GetProperty("quantidade").GetInt32());

        // a amostra mostra primeiro o que NÃO entrou: é o que a pessoa precisa ver
        var amostra = corpo.GetProperty("amostra").EnumerateArray().ToList();
        Assert.Equal(["contribuicoes_2021.txt", "lixo.bin", "efd_jan.txt", "efd_mar_retif.txt"], amostra.Select(a => a.GetProperty("nome").GetString()));
        Assert.Equal(["nome", "caminho", "tamanho", "tipo", "tipo_rotulo", "grupo", "alimenta", "cnpj", "competencia", "uf", "detalhe", "motivo"],
            amostra[0].EnumerateObject().Select(p => p.Name));
        Assert.Equal("sem cabeçalho", amostra[1].GetProperty("motivo").GetString());

        Assert.Equal(0, await banco.Escalar<long>($"SELECT count(*) FROM lote WHERE projeto_id = {projeto}"));
    }

    [Fact]
    public async Task Inspecao_recusa_de_quem_nao_pode_de_fora_do_escopo_e_repassa_a_recusa_do_motor()
    {
        var (_, dono) = await Pessoa("dev");
        var (empresa, projeto) = await Trabalho(dono);
        var (_, leitor) = await Pessoa("leitura", [empresa]);
        var (_, deFora) = await Pessoa("analista");

        var doLeitor = await Inspecionar(leitor, projeto, "Z:/base");
        Assert.Equal(HttpStatusCode.Forbidden, doLeitor.StatusCode);
        Assert.Equal("Você não tem permissão para importar lote de arquivos.", await Detalhe(doLeitor));
        Assert.Equal(HttpStatusCode.Forbidden, (await Inspecionar(deFora, projeto, "Z:/base")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Inspecionar(Cliente(), projeto, "Z:/base")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Inspecionar(dono, 999999, "Z:/base")).StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await Inspecionar(dono, projeto, "")).StatusCode);

        var inexistente = await Inspecionar(dono, projeto, "Z:/nao-existe");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, inexistente.StatusCode);
        Assert.Contains("não existe", await Detalhe(inexistente));

        var semMotor = await Inspecionar(Cliente(await Token(dono), new Uri("http://127.0.0.1:9")), projeto, "Z:/base");
        Assert.Equal(HttpStatusCode.BadGateway, semMotor.StatusCode);
    }

    private static Task<string> Token(HttpClient c) => Task.FromResult(c.DefaultRequestHeaders.Authorization!.Parameter!);

    // ------------------------------------------------------------------ registrar
    [Fact]
    public async Task Registrar_grava_lote_arquivos_e_evento_e_aparece_na_lista()
    {
        var (quem, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);

        var r = await Registrar(c, projeto, "Z:/base", "primeira remessa da empresa");

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var lote = await Json(r);
        Assert.Equal(["id", "projeto_id", "pasta", "total_arquivos", "arquivos_uteis", "bytes_totais", "competencia_ini",
                      "competencia_fim", "observacao", "criado_em", "contagens", "criado", "reclassificados"],
            lote.EnumerateObject().Select(p => p.Name));
        Assert.True(lote.GetProperty("criado").GetBoolean());
        Assert.Equal(0, lote.GetProperty("reclassificados").GetInt32());
        Assert.Equal(4, lote.GetProperty("total_arquivos").GetInt32());
        Assert.Equal(2, lote.GetProperty("arquivos_uteis").GetInt32());
        // o período é o do que a CAT lê: a Contribuições de 2021 na pasta não conta
        Assert.Equal("2025-01-01", lote.GetProperty("competencia_ini").GetString());
        Assert.Equal("2025-03-01", lote.GetProperty("competencia_fim").GetString());
        Assert.Equal("primeira remessa da empresa", lote.GetProperty("observacao").GetString());
        Assert.EndsWith("+00:00", lote.GetProperty("criado_em").GetString());

        var id = lote.GetProperty("id").GetInt32();
        Assert.Equal(4, await banco.Escalar<long>($"SELECT count(*) FROM arquivo_do_lote WHERE lote_id = {id}"));
        Assert.Equal("abc123", await banco.Escalar<string>($"SELECT hash_conteudo FROM arquivo_do_lote WHERE lote_id = {id} AND nome = 'efd_jan.txt'"));
        Assert.True(await banco.Escalar<bool>($"SELECT retificadora FROM arquivo_do_lote WHERE lote_id = {id} AND nome = 'efd_mar_retif.txt'"));
        Assert.Equal(quem, await banco.Escalar<int>($"SELECT criado_por FROM lote WHERE id = {id}"));
        Assert.Equal("4 arquivo(s) de Z:/base", await banco.Escalar<string>($"SELECT texto FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_importado'"));
        Assert.Equal(2, await banco.Escalar<int>($"SELECT (dados->>'uteis')::int FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_importado'"));

        var lista = (await Json(await c.GetAsync($"/api/projetos/{projeto}/lotes"))).EnumerateArray().ToList();
        Assert.Equal([id], lista.Select(l => l.GetProperty("id").GetInt32()));
        Assert.Equal("sped_icms_ipi", lista[0].GetProperty("contagens")[0].GetProperty("tipo").GetString());

        // e a etapa de importar concluiu
        var etapas = (await Json(await c.GetAsync($"/api/projetos/{projeto}"))).GetProperty("etapas");
        Assert.Equal("concluida", etapas[0].GetProperty("situacao").GetString());
    }

    [Theory]
    [InlineData("Z:/so-copias", 409, "Os 3 arquivo(s) desta pasta são cópias exatas")]
    [InlineData("Z:/sem-cat", 422, "Nenhum arquivo desta pasta alimenta o trabalho de ICMS")]
    [InlineData("Z:/ja-no-trabalho", 409, "Todos os arquivos desta pasta já estão neste trabalho.")]
    public async Task Registrar_recusa_com_a_mensagem_certa(string pasta, int status, string pedaco)
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);

        var r = await Registrar(c, projeto, pasta);

        Assert.Equal(status, (int)r.StatusCode);
        Assert.Contains(pedaco, await Detalhe(r));
        Assert.Equal(0, await banco.Escalar<long>($"SELECT count(*) FROM lote WHERE projeto_id = {projeto}"));
    }

    [Fact]
    public async Task So_o_que_e_novo_entra_e_o_evento_conta_o_que_ficou_de_fora()
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);

        var lote = await Json(await Registrar(c, projeto, "Z:/metade"));

        Assert.Equal(1, lote.GetProperty("total_arquivos").GetInt32());
        Assert.Equal(1, await banco.Escalar<int>($"SELECT (dados->>'repetidos_ignorados')::int FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_importado'"));
    }

    [Fact]
    public async Task Arquivo_ja_no_trabalho_com_outro_tipo_e_atualizado_sem_lote_novo()
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var antes = await Json(await Registrar(c, projeto, "Z:/antes"));
        var id = antes.GetProperty("id").GetInt32();
        Assert.Equal(1, antes.GetProperty("arquivos_uteis").GetInt32());

        var inspecao = await Json(await Inspecionar(c, projeto, "Z:/hoje"));
        Assert.Equal(2, inspecao.GetProperty("ja_no_trabalho").GetInt32());
        Assert.Equal(1, inspecao.GetProperty("reclassificados").GetInt32());

        var r = await Registrar(c, projeto, "Z:/hoje");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var lote = await Json(r);
        Assert.Equal(id, lote.GetProperty("id").GetInt32());
        Assert.False(lote.GetProperty("criado").GetBoolean());
        Assert.Equal(1, lote.GetProperty("reclassificados").GetInt32());
        Assert.Equal(2, lote.GetProperty("arquivos_uteis").GetInt32());
        Assert.Equal(1, await banco.Escalar<long>($"SELECT count(*) FROM lote WHERE projeto_id = {projeto}"));
        Assert.Equal("xml_compactado", await banco.Escalar<string>($"SELECT tipo FROM arquivo_do_lote WHERE lote_id = {id} AND nome = 'portal.zip'"));
        Assert.Equal("3577 XML", await banco.Escalar<string>($"SELECT detalhe FROM arquivo_do_lote WHERE lote_id = {id} AND nome = 'portal.zip'"));
        Assert.Equal("1 arquivo(s) de Z:/hoje", await banco.Escalar<string>($"SELECT texto FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_reclassificado'"));
        Assert.Equal("compactado", await banco.Escalar<string>($"SELECT dados->'trocas'->0->>'de' FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_reclassificado'"));
    }

    [Fact]
    public async Task Com_arquivo_novo_o_lote_e_criado_e_o_antigo_atualizado_junto()
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);
        var id = (await Json(await Registrar(c, projeto, "Z:/antes"))).GetProperty("id").GetInt32();

        var r = await Registrar(c, projeto, "Z:/hoje-com-novo");

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var lote = await Json(r);
        Assert.NotEqual(id, lote.GetProperty("id").GetInt32());
        Assert.True(lote.GetProperty("criado").GetBoolean());
        Assert.Equal(1, lote.GetProperty("reclassificados").GetInt32());
        Assert.Equal(1, lote.GetProperty("total_arquivos").GetInt32());
        Assert.Equal("xml_compactado", await banco.Escalar<string>($"SELECT tipo FROM arquivo_do_lote WHERE lote_id = {id} AND nome = 'portal.zip'"));
    }

    [Fact]
    public async Task Lote_grande_grava_tudo_e_escreve_o_numero_com_ponto_de_milhar()
    {
        var (_, c) = await Pessoa("dev");
        var (_, projeto) = await Trabalho(c);

        var r = await Registrar(c, projeto, "Z:/grande");

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        Assert.Equal(1500, await banco.Escalar<long>($"SELECT count(*) FROM arquivo_do_lote a JOIN lote l ON l.id = a.lote_id WHERE l.projeto_id = {projeto}"));
        Assert.Equal("1.500 arquivo(s) de Z:/grande", await banco.Escalar<string>($"SELECT texto FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_importado'"));
    }

    // ------------------------------------------------------------------ remover
    [Fact]
    public async Task Remover_tira_o_lote_conta_as_conferencias_e_registra()
    {
        var (_, dono) = await Pessoa("dev");
        var (empresa, projeto) = await Trabalho(dono);
        var id = (await Json(await Registrar(dono, projeto, "Z:/base"))).GetProperty("id").GetInt32();
        await banco.Comando($"INSERT INTO execucao (projeto_id, etapa, situacao, arquivos_totais, arquivos_lidos, bytes_lidos, documentos) VALUES ({projeto}, 'conferencia', 'concluida', 0, 0, 0, 0)");
        // desfazer uma importação não é apagar meses de trabalho: analista também pode
        var (_, analista) = await Pessoa("analista", [empresa]);

        var r = await analista.DeleteAsync($"/api/projetos/{projeto}/lotes/{id}");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("""{"pasta":"Z:/base","arquivos":4,"conferencias_invalidadas":1}""", await r.Content.ReadAsStringAsync());
        Assert.Equal(0, await banco.Escalar<long>($"SELECT count(*) FROM arquivo_do_lote WHERE lote_id = {id}"));
        Assert.Empty((await Json(await dono.GetAsync($"/api/projetos/{projeto}/lotes"))).EnumerateArray());
        Assert.Equal("Z:/base", await banco.Escalar<string>($"SELECT texto FROM evento_do_projeto WHERE projeto_id = {projeto} AND tipo = 'lote_removido'"));
        var etapas = (await Json(await dono.GetAsync($"/api/projetos/{projeto}"))).GetProperty("etapas");
        Assert.Equal("pendente", etapas[0].GetProperty("situacao").GetString());
    }

    [Fact]
    public async Task Lote_de_outro_trabalho_da_404_e_quem_so_le_nao_remove()
    {
        var (_, dono) = await Pessoa("dev");
        var (empresa, projeto) = await Trabalho(dono);
        var (_, outro) = await Trabalho(dono);
        var id = (await Json(await Registrar(dono, projeto, "Z:/base"))).GetProperty("id").GetInt32();
        var (_, leitor) = await Pessoa("leitura", [empresa]);

        var deOutro = await dono.DeleteAsync($"/api/projetos/{outro}/lotes/{id}");
        Assert.Equal(HttpStatusCode.NotFound, deOutro.StatusCode);
        Assert.Equal("Lote não encontrado neste trabalho.", await Detalhe(deOutro));
        Assert.Equal(HttpStatusCode.Forbidden, (await leitor.DeleteAsync($"/api/projetos/{projeto}/lotes/{id}")).StatusCode);
        // quem só lê, lê
        Assert.Equal(HttpStatusCode.OK, (await leitor.GetAsync($"/api/projetos/{projeto}/lotes")).StatusCode);
    }

    // ------------------------------------------------------------------ remessa
    private static MultipartFormDataContent Remessa(string nome, int bytes)
    {
        var formulario = new MultipartFormDataContent();
        var conteudo = new ByteArrayContent(new byte[bytes]);
        conteudo.Headers.ContentType = new MediaTypeHeaderValue("application/zip");
        formulario.Add(conteudo, "arquivo", nome);
        return formulario;
    }

    [Fact]
    public async Task Remessa_diz_se_a_empresa_ja_esta_cadastrada()
    {
        var (_, c) = await Pessoa("dev");
        var raizNova = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var (empresa, _) = await Trabalho(c);
        var raizExistente = await banco.Escalar<string>($"SELECT cnpj_raiz FROM empresa WHERE id = {empresa}");

        var nova = await Json(await c.PostAsync("/api/importacoes/analisar", Remessa($"{raizNova}.zip", 1000)));
        var existente = await Json(await c.PostAsync("/api/importacoes/analisar", Remessa($"{raizExistente}.zip", 1000)));

        Assert.False(nova.GetProperty("ja_cadastrada").GetBoolean());
        Assert.Equal(JsonValueKind.Null, nova.GetProperty("empresa_id").ValueKind);
        Assert.True(existente.GetProperty("ja_cadastrada").GetBoolean());
        Assert.Equal(empresa, existente.GetProperty("empresa_id").GetInt32());
        // os dois campos do banco antes da matriz, como no FastAPI
        var campos = existente.EnumerateObject().Select(p => p.Name).ToList();
        Assert.Equal(campos.IndexOf("matriz") - 2, campos.IndexOf("ja_cadastrada"));
    }

    [Fact]
    public async Task Remessa_de_40_mb_passa_inteira_ate_o_motor()
    {
        // o limite de 30 MB do Kestrel cortava a remessa grande desde a fundação
        var (_, c) = await Pessoa("dev");
        const int tamanho = 40 * 1024 * 1024;

        var r = await c.PostAsync("/api/importacoes/analisar", Remessa("12345678.zip", tamanho));

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(tamanho, (await Json(r)).GetProperty("bytes").GetInt64());
    }

    [Fact]
    public async Task Remessa_sem_sped_sem_arquivo_ou_de_quem_so_le_e_recusada()
    {
        var (_, c) = await Pessoa("dev");
        var (_, leitor) = await Pessoa("leitura");

        var semSped = await c.PostAsync("/api/importacoes/analisar", Remessa("nada.txt", 10));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, semSped.StatusCode);
        Assert.Contains("reconhecido como SPED", await Detalhe(semSped));
        Assert.Equal(HttpStatusCode.UnprocessableEntity,
            (await c.PostAsync("/api/importacoes/analisar", JsonContent.Create(new { arquivo = "x" }))).StatusCode);
        var doLeitor = await leitor.PostAsync("/api/importacoes/analisar", Remessa("12345678.zip", 10));
        Assert.Equal(HttpStatusCode.Forbidden, doLeitor.StatusCode);
        Assert.Equal("Você não tem permissão para importar arquivos.", await Detalhe(doLeitor));
    }
}
