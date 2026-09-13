using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Cat.Api.Testes;

/// <summary>
/// Portados de tests/integracao/test_historico_api.py. O trabalho nasce com um
/// evento, cada coisa entra na linha do tempo com o nome de quem fez, e passar
/// o trabalho adiante é de gestor.
/// </summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class HistoricoTestes(BancoDeTeste banco) : IDisposable
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
        var pasta = Directory.CreateTempSubdirectory("cat-historico-").FullName;
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
            b.UseSetting("CAT_MOTOR_URL", "http://127.0.0.1:9");
        });
        _fabricas.Add(fabrica);
        var c = fabrica.CreateClient();
        if (token is not null)
            c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    private sealed record Pessoa(int Id, string Usuario, string Nome, HttpClient Cliente);

    private async Task<Pessoa> Criar(string papel, string nome, bool ativo = true)
    {
        var usuario = "h" + Guid.NewGuid().ToString("N")[..10];
        var id = await banco.CriarUsuario(usuario, papel: papel, ativo: ativo);
        await banco.Comando($"UPDATE usuario SET nome_exibicao = '{nome}' WHERE id = {id}");
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario { Id = id, NomeDeUsuario = usuario, Email = "x@y.zz", NomeExibicao = nome, Papel = p });
        return new Pessoa(id, usuario, nome, Cliente(token));
    }

    private async Task Alocar(int usuarioId, int empresaId, bool encerrada = false) =>
        await banco.Comando($"INSERT INTO alocacao (usuario_id, empresa_id, papel_projeto, inicio, fim) VALUES ({usuarioId}, {empresaId}, 'executor', now() - interval '1 day', {(encerrada ? "now()" : "NULL")})");

    /// <summary>Empresa e trabalho criados pelas rotas de verdade, por esta pessoa.</summary>
    private static async Task<(int Empresa, int Projeto)> Trabalho(Pessoa dono)
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var doze = raiz + "0001";
        var r = await dono.Cliente.PostAsJsonAsync("/api/empresas", new
            { cnpj_raiz = raiz, cnpj_matriz = doze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(doze), razao_social = "EMPRESA DO HISTORICO", uf = "SP" });
        var empresa = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        r = await dono.Cliente.PostAsJsonAsync("/api/projetos", new
            { empresa_id = empresa, frente = "cat42", nome = "Trabalho com história", competencia_ini = "2021-05-01", competencia_fim = "2021-05-31" });
        return (empresa, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32());
    }

    private static async Task<JsonElement> Json(HttpResponseMessage r) => await r.Content.ReadFromJsonAsync<JsonElement>();
    private static async Task<string> Detalhe(HttpResponseMessage r) => (await Json(r)).GetProperty("detail").GetString()!;

    private static async Task<JsonElement> Pagina(HttpClient c, int projeto, string consulta = "")
    {
        var r = await c.GetAsync($"/api/projetos/{projeto}/historico{consulta}");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        return await Json(r);
    }

    private static async Task<JsonElement> Topo(HttpClient c, int projeto) => (await Pagina(c, projeto)).GetProperty("eventos")[0];

    // ------------------------------------------------------------------ nascimento e comentário
    [Fact]
    public async Task O_trabalho_nasce_com_um_evento_no_formato_da_tela()
    {
        var gestora = await Criar("dev", "Gestora do Histórico");
        var (_, projeto) = await Trabalho(gestora);

        var pagina = await Pagina(gestora.Cliente, projeto);

        Assert.Equal(["eventos", "tem_mais", "proximo_cursor"], pagina.EnumerateObject().Select(p => p.Name));
        var e = Assert.Single(pagina.GetProperty("eventos").EnumerateArray());
        Assert.Equal(["id", "tipo", "rotulo_do_tipo", "texto", "dados", "autor", "autor_id", "quando", "e_comentario"],
            e.EnumerateObject().Select(p => p.Name));
        Assert.Equal("criado", e.GetProperty("tipo").GetString());
        Assert.Equal("Trabalho criado", e.GetProperty("rotulo_do_tipo").GetString());
        Assert.Equal("Gestora do Histórico", e.GetProperty("autor").GetString());
        Assert.Contains("Trabalho com história", e.GetProperty("texto").GetString());
        Assert.Equal("cat42", e.GetProperty("dados").GetProperty("frente").GetString());
        Assert.EndsWith("+00:00", e.GetProperty("quando").GetString());
        Assert.False(e.GetProperty("e_comentario").GetBoolean());
        Assert.False(pagina.GetProperty("tem_mais").GetBoolean());
        Assert.Equal(JsonValueKind.Null, pagina.GetProperty("proximo_cursor").ValueKind);
    }

    [Fact]
    public async Task Comenta_aparado_aparece_no_topo_e_conta_no_cartao()
    {
        var gestora = await Criar("dev", "Gestora do Histórico");
        var analista = await Criar("analista", "Analista do Histórico");
        var (empresa, projeto) = await Trabalho(gestora);
        await Alocar(analista.Id, empresa);

        var r = await analista.Cliente.PostAsJsonAsync($"/api/projetos/{projeto}/historico/comentarios",
            new { texto = "  Falei com o cliente: manda o que falta na sexta.  " });

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var c = await Json(r);
        Assert.Equal("Analista do Histórico", c.GetProperty("autor").GetString());
        Assert.Equal("Falei com o cliente: manda o que falta na sexta.", c.GetProperty("texto").GetString());
        Assert.True(c.GetProperty("e_comentario").GetBoolean());
        Assert.Equal(JsonValueKind.Object, c.GetProperty("dados").ValueKind);
        Assert.Equal("comentario", (await Topo(gestora.Cliente, projeto)).GetProperty("tipo").GetString());
        var cartao = (await Json(await gestora.Cliente.GetAsync($"/api/projetos/{projeto}"))).GetProperty("projeto");
        Assert.Equal(1, cartao.GetProperty("comentarios").GetInt32());
    }

    [Fact]
    public async Task Comentario_vazio_e_de_quem_so_le_sao_recusados()
    {
        var gestora = await Criar("dev", "Gestora");
        var leitor = await Criar("leitura", "Leitor");
        var (empresa, projeto) = await Trabalho(gestora);
        await Alocar(leitor.Id, empresa);

        var vazio = await gestora.Cliente.PostAsJsonAsync($"/api/projetos/{projeto}/historico/comentarios", new { texto = "   " });
        var doLeitor = await leitor.Cliente.PostAsJsonAsync($"/api/projetos/{projeto}/historico/comentarios", new { texto = "oi" });

        Assert.Equal(HttpStatusCode.UnprocessableEntity, vazio.StatusCode);
        Assert.Equal("O comentário não pode ficar vazio.", await Detalhe(vazio));
        Assert.Equal(HttpStatusCode.Forbidden, doLeitor.StatusCode);
        Assert.Equal("Você não tem permissão para mexer no trabalho.", await Detalhe(doLeitor));
        // quem só lê, lê
        Assert.Equal(HttpStatusCode.OK, (await leitor.Cliente.GetAsync($"/api/projetos/{projeto}/historico")).StatusCode);
    }

    [Fact]
    public async Task Filtro_so_comentarios_e_paginacao_para_tras_sem_repetir()
    {
        var gestora = await Criar("dev", "Gestora");
        var (_, projeto) = await Trabalho(gestora);
        for (var i = 0; i < 6; i++)
            await gestora.Cliente.PostAsJsonAsync($"/api/projetos/{projeto}/historico/comentarios", new { texto = $"nota {i}" });

        var so = await Pagina(gestora.Cliente, projeto, "?so_comentarios=true");
        Assert.Equal(6, so.GetProperty("eventos").GetArrayLength());
        Assert.All(so.GetProperty("eventos").EnumerateArray(), e => Assert.Equal("comentario", e.GetProperty("tipo").GetString()));

        var primeira = await Pagina(gestora.Cliente, projeto, "?quantos=3");
        Assert.Equal(3, primeira.GetProperty("eventos").GetArrayLength());
        Assert.True(primeira.GetProperty("tem_mais").GetBoolean());
        var cursor = primeira.GetProperty("proximo_cursor").GetInt32();
        Assert.Equal(primeira.GetProperty("eventos")[2].GetProperty("id").GetInt32(), cursor);

        var segunda = await Pagina(gestora.Cliente, projeto, $"?quantos=3&antes_de={cursor}");
        var idsPrimeira = primeira.GetProperty("eventos").EnumerateArray().Select(e => e.GetProperty("id").GetInt32()).ToList();
        var idsSegunda = segunda.GetProperty("eventos").EnumerateArray().Select(e => e.GetProperty("id").GetInt32()).ToList();
        Assert.Empty(idsPrimeira.Intersect(idsSegunda));
        Assert.True(idsSegunda.Max() < idsPrimeira.Min());
        Assert.Equal(idsSegunda.OrderDescending(), idsSegunda);

        // o sétimo evento, o de criação, é o último e não tem próxima página
        var terceira = await Pagina(gestora.Cliente, projeto, $"?quantos=3&antes_de={idsSegunda.Min()}");
        Assert.Single(terceira.GetProperty("eventos").EnumerateArray());
        Assert.False(terceira.GetProperty("tem_mais").GetBoolean());
    }

    [Fact]
    public async Task Tipo_do_futuro_e_dados_ilegiveis_nao_derrubam_a_linha_do_tempo()
    {
        var gestora = await Criar("dev", "Gestora");
        var (_, projeto) = await Trabalho(gestora);
        await banco.Comando($"INSERT INTO evento_do_projeto (projeto_id, tipo, texto, dados, autor_nome, criado_em) VALUES ({projeto}, 'tipo_do_futuro', 'algo', NULL, 'Sistema', now())");

        var topo = await Topo(gestora.Cliente, projeto);

        Assert.Equal("comentario", topo.GetProperty("tipo").GetString());
        Assert.Equal(JsonValueKind.Object, topo.GetProperty("dados").ValueKind);
    }

    // ------------------------------------------------------------------ status
    [Fact]
    public async Task Catalogo_de_status_e_aberto_e_traz_rotulo_e_explicacao()
    {
        var lista = await Json(await Cliente().GetAsync("/api/status-de-projeto"));
        var porValor = lista.EnumerateArray().ToDictionary(s => s.GetProperty("valor").GetString()!);
        Assert.Equal(["valor", "rotulo", "explicacao", "exige_motivo"], porValor["pausado"].EnumerateObject().Select(p => p.Name));
        Assert.Equal("Pausado", porValor["pausado"].GetProperty("rotulo").GetString());
        Assert.True(porValor["pausado"].GetProperty("exige_motivo").GetBoolean());
        Assert.False(porValor["em_andamento"].GetProperty("exige_motivo").GetBoolean());
    }

    [Fact]
    public async Task Pausar_pede_motivo_registra_e_nao_aceita_o_mesmo_status_de_novo()
    {
        var gestora = await Criar("dev", "Gestora do Histórico");
        var (_, projeto) = await Trabalho(gestora);
        Task<HttpResponseMessage> Mudar(object corpo) =>
            gestora.Cliente.PatchAsync($"/api/projetos/{projeto}/status", JsonContent.Create(corpo));

        var semMotivo = await Mudar(new { status = "pausado", motivo = "  " });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, semMotivo.StatusCode);
        Assert.Contains("Diga por que", await Detalhe(semMotivo));

        var pausa = await Mudar(new { status = "pausado", motivo = "  Esperando o XML de 2023. " });
        Assert.Equal(HttpStatusCode.OK, pausa.StatusCode);
        Assert.Equal("""{"status":"pausado","rotulo":"Pausado"}""", await pausa.Content.ReadAsStringAsync());
        var topo = await Topo(gestora.Cliente, projeto);
        Assert.Equal("status", topo.GetProperty("tipo").GetString());
        Assert.Equal("Esperando o XML de 2023.", topo.GetProperty("texto").GetString());
        Assert.Equal("Em andamento → Pausado", topo.GetProperty("dados").GetProperty("frase").GetString());
        Assert.Equal("Gestora do Histórico", topo.GetProperty("autor").GetString());
        Assert.Equal("pausado", await banco.Escalar<string>($"SELECT status FROM projeto WHERE id = {projeto}"));

        var deNovo = await Mudar(new { status = "pausado", motivo = "de novo" });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, deNovo.StatusCode);
        Assert.Contains("já está", await Detalhe(deNovo));

        // retomar não exige motivo
        Assert.Equal(HttpStatusCode.OK, (await Mudar(new { status = "em_andamento", motivo = "" })).StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await Mudar(new { status = "arquivado" })).StatusCode);
    }

    // ------------------------------------------------------------------ sucessão
    [Fact]
    public async Task Quem_pode_receber_escreve_esta_ativo_e_vem_marcado_se_precisa_de_acesso()
    {
        var gestora = await Criar("dev", "Gestora");
        var (empresa, projeto) = await Trabalho(gestora);
        var alocada = await Criar("analista", "Analista Alocada");
        var semAcesso = await Criar("analista", "Analista Sem Acesso");
        var encerrada = await Criar("analista", "Analista Com Acesso Encerrado");
        var leitor = await Criar("leitura", "Só Lê");
        var inativa = await Criar("analista", "Desligada", ativo: false);
        var gerente = await Criar("gestor", "Gerente Sem Alocação");
        await Alocar(alocada.Id, empresa);
        await Alocar(encerrada.Id, empresa, encerrada: true);

        var lista = (await Json(await gestora.Cliente.GetAsync($"/api/projetos/{projeto}/sucessores"))).EnumerateArray()
            .ToDictionary(p => p.GetProperty("usuario").GetString()!);

        Assert.Equal(["id", "nome_exibicao", "usuario", "papel", "cargo", "precisa_de_acesso"], lista[alocada.Usuario].EnumerateObject().Select(p => p.Name));
        Assert.False(lista[alocada.Usuario].GetProperty("precisa_de_acesso").GetBoolean());
        Assert.True(lista[semAcesso.Usuario].GetProperty("precisa_de_acesso").GetBoolean());
        // o Python contava a alocação encerrada como acesso
        Assert.True(lista[encerrada.Usuario].GetProperty("precisa_de_acesso").GetBoolean());
        Assert.False(lista[gerente.Usuario].GetProperty("precisa_de_acesso").GetBoolean());
        Assert.DoesNotContain(leitor.Usuario, lista.Keys);
        Assert.DoesNotContain(inativa.Usuario, lista.Keys);
        var nomes = lista.Values.Select(p => p.GetProperty("nome_exibicao").GetString()).ToList();
        Assert.Contains(gestora.Usuario, lista.Keys);
        Assert.True(nomes.Count > 0);
    }

    [Fact]
    public async Task Analista_nao_passa_trabalho()
    {
        var gestora = await Criar("dev", "Gestora");
        var analista = await Criar("analista", "Analista");
        var (empresa, projeto) = await Trabalho(gestora);
        await Alocar(analista.Id, empresa);

        var r = await analista.Cliente.PatchAsync($"/api/projetos/{projeto}/responsavel",
            JsonContent.Create(new { responsavel_id = analista.Id, motivo = "quero para mim" }));

        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Contains("Só gestor", await Detalhe(r));
    }

    [Fact]
    public async Task Gestor_passa_registra_e_recusa_quem_ja_responde_ou_esta_desativado()
    {
        var gestora = await Criar("dev", "Gestora do Histórico");
        var analista = await Criar("analista", "Analista do Histórico");
        var desligada = await Criar("analista", "Fulano Desligado", ativo: false);
        var (empresa, projeto) = await Trabalho(gestora);
        await Alocar(analista.Id, empresa);
        Task<HttpResponseMessage> Passar(int para, string motivo) => gestora.Cliente.PatchAsync(
            $"/api/projetos/{projeto}/responsavel", JsonContent.Create(new { responsavel_id = para, motivo }));

        var r = await Passar(analista.Id, " Férias da gestora. ");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal($$"""{"responsavel_id":{{analista.Id}},"responsavel":"Analista do Histórico"}""", await r.Content.ReadAsStringAsync());
        var topo = await Topo(gestora.Cliente, projeto);
        Assert.Equal("sucessao", topo.GetProperty("tipo").GetString());
        Assert.Equal("Gestora do Histórico → Analista do Histórico", topo.GetProperty("dados").GetProperty("frase").GetString());
        Assert.Equal("Férias da gestora.", topo.GetProperty("texto").GetString());
        Assert.False(topo.GetProperty("dados").GetProperty("alocou_na_empresa").GetBoolean());
        var cartao = (await Json(await gestora.Cliente.GetAsync($"/api/projetos/{projeto}"))).GetProperty("projeto");
        Assert.Equal("Analista do Histórico", cartao.GetProperty("responsavel").GetString());
        // quem criou não muda: são coisas diferentes
        Assert.Equal("Gestora do Histórico", cartao.GetProperty("criado_por").GetString());

        var deNovo = await Passar(analista.Id, "");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, deNovo.StatusCode);
        Assert.Contains("já responde", await Detalhe(deNovo));

        var paraDesligada = await Passar(desligada.Id, "");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, paraDesligada.StatusCode);
        Assert.Contains("desativado", await Detalhe(paraDesligada));

        var paraNinguem = await Passar(999999, "");
        Assert.Equal("A pessoa escolhida não existe.", await Detalhe(paraNinguem));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]   // acesso encerrado: o Python não realocava, e a pessoa recebia trabalho que não via
    public async Task Transferir_da_acesso_a_empresa_a_quem_nao_alcanca(bool comAlocacaoEncerrada)
    {
        var gestora = await Criar("dev", "Gestora");
        var outra = await Criar("analista", "Analista de Outra Carteira");
        var (empresa, projeto) = await Trabalho(gestora);
        if (comAlocacaoEncerrada)
            await Alocar(outra.Id, empresa, encerrada: true);

        var r = await gestora.Cliente.PatchAsync($"/api/projetos/{projeto}/responsavel",
            JsonContent.Create(new { responsavel_id = outra.Id, motivo = "Carteira nova." }));

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.True((await Topo(gestora.Cliente, projeto)).GetProperty("dados").GetProperty("alocou_na_empresa").GetBoolean());
        // quem recebeu passa a enxergar o trabalho, que é o ponto — com um token novo, que relê as alocações
        var (token, _) = _tokens.Emitir(new Usuario { Id = outra.Id, NomeDeUsuario = outra.Usuario, Email = "x@y.zz", NomeExibicao = outra.Nome, Papel = Papel.Analista });
        var d = await Cliente(token).GetAsync($"/api/projetos/{projeto}");
        Assert.Equal(HttpStatusCode.OK, d.StatusCode);
        Assert.Equal("Analista de Outra Carteira", (await Json(d)).GetProperty("projeto").GetProperty("responsavel").GetString());
        Assert.Equal("responsavel", await banco.Escalar<string>(
            $"SELECT papel_projeto FROM alocacao WHERE usuario_id = {outra.Id} AND empresa_id = {empresa} AND fim IS NULL"));
    }

    // ------------------------------------------------------------------ escopo
    [Fact]
    public async Task Escopo_de_empresa_vale_para_o_historico()
    {
        var gestora = await Criar("dev", "Gestora");
        var (_, projeto) = await Trabalho(gestora);
        var gerente = await Criar("gestor", "Gerente sem Alocação");
        var deFora = await Criar("analista", "Analista de Fora");

        Assert.Equal(HttpStatusCode.NotFound, (await gestora.Cliente.GetAsync("/api/projetos/999999/historico")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Cliente().GetAsync($"/api/projetos/{projeto}/historico")).StatusCode);
        // gestor responde pela carteira inteira: ninguém o aloca em empresa
        Assert.NotEmpty((await Pagina(gerente.Cliente, projeto)).GetProperty("eventos").EnumerateArray());
        // o escopo não caiu — só não vale para quem coordena
        var r = await deFora.Cliente.GetAsync($"/api/projetos/{projeto}/historico");
        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("Você não tem acesso a esta empresa.", await Detalhe(r));
        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.Cliente.GetAsync($"/api/projetos/{projeto}/sucessores")).StatusCode);
    }
}
