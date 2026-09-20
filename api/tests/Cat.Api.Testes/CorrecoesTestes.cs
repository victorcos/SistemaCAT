using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Cat.Api.Testes;

/// <summary>
/// As correções à mão pela porta: gravar, listar, desfazer — e o histórico
/// mostrando o antes e o depois de cada uma, que é o que a auditoria lê.
/// </summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class CorrecoesTestes(BancoDeTeste banco) : IDisposable
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
        var pasta = Directory.CreateTempSubdirectory("cat-correcoes-").FullName;
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
        });
        _fabricas.Add(fabrica);
        var c = fabrica.CreateClient();
        if (token is not null)
            c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    private async Task<(int Id, HttpClient Cliente)> Pessoa(string papel)
    {
        var nome = "c" + Guid.NewGuid().ToString("N")[..10];
        var id = await banco.CriarUsuario(nome, papel: papel);
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario
        {
            Id = id, NomeDeUsuario = nome, Email = "x@y.zz", NomeExibicao = "Ana da Correção", Papel = p,
        });
        return (id, Cliente(token));
    }

    private static async Task<(int Empresa, int Projeto)> Trabalho(HttpClient c)
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var doze = raiz + "0001";
        var r = await c.PostAsJsonAsync("/api/empresas", new
        {
            cnpj_raiz = raiz, cnpj_matriz = doze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(doze),
            razao_social = "DISTRIBUIDORA DA CORREÇÃO", uf = "SP",
        });
        var empresa = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        r = await c.PostAsJsonAsync("/api/projetos", new
        {
            empresa_id = empresa, frente = "cat42", nome = "Correções " + Guid.NewGuid().ToString("N")[..6],
            competencia_ini = "2022-08-01", competencia_fim = "2024-06-01",
        });
        return (empresa, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32());
    }

    private static async Task<string> Detalhe(HttpResponseMessage r) =>
        (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString()!;

    [Fact]
    public async Task Grava_lista_e_substitui_a_correcao_do_mesmo_alvo()
    {
        var (quem, c) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(c);

        var r = await c.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new
        {
            correcoes = new object[]
            {
                new { campo = "aliquota", valor = "25", motivo = "Sem 0200; NCM 3305.90.00, art. 55, IV",
                      codigo = "4002", valor_anterior = "18" },
                new { campo = "enquadramento", valor = "1", motivo = "Venda a consumidor confirmada pelo cliente",
                      documento = "35240643112531000421550030000717821739478490", numero_item = 2,
                      valor_anterior = "indefinido" },
            },
        });

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(2, (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("gravadas").GetInt32());
        Assert.Equal(2L, await banco.Escalar<long>($"SELECT count(*) FROM correcao WHERE projeto_id = {projeto}"));
        Assert.Equal(quem, await banco.Escalar<int>(
            $"SELECT criada_por FROM correcao WHERE projeto_id = {projeto} AND campo = 'aliquota'"));

        // a mesma mercadoria e campo de novo: atualiza, não duplica
        r = await c.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new
        {
            correcoes = new[] { new { campo = "aliquota", valor = "18", motivo = "revisto com o cliente",
                                      codigo = "4002", valor_anterior = "25.0000" } },
        });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(2L, await banco.Escalar<long>($"SELECT count(*) FROM correcao WHERE projeto_id = {projeto}"));
        Assert.Equal("18.0000", await banco.Escalar<string>(
            $"SELECT valor FROM correcao WHERE projeto_id = {projeto} AND campo = 'aliquota'"));

        var lista = await (await c.GetAsync($"/api/projetos/{projeto}/correcoes")).Content
            .ReadFromJsonAsync<JsonElement>();
        var correcoes = lista.GetProperty("correcoes");
        Assert.Equal(2, correcoes.GetArrayLength());
        Assert.Contains("Alíquota interna (mercadoria 4002): 25.0000 → 18.0000",
            correcoes.EnumerateArray().Select(x => x.GetProperty("frase").GetString()));
        Assert.Equal(7, lista.GetProperty("campos").GetArrayLength());
    }

    [Fact]
    public async Task O_historico_mostra_o_antes_e_o_depois()
    {
        var (_, c) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(c);

        await c.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new
        {
            correcoes = new[] { new { campo = "aliquota", valor = "25", motivo = "Sem 0200 para a mercadoria",
                                      codigo = "4002", valor_anterior = "18" } },
        });

        var historico = await (await c.GetAsync($"/api/projetos/{projeto}/historico")).Content
            .ReadFromJsonAsync<JsonElement>();
        var evento = historico.GetProperty("eventos").EnumerateArray()
            .First(e => e.GetProperty("tipo").GetString() == "correcao_aplicada");
        Assert.Equal("Correção à mão", evento.GetProperty("rotulo_do_tipo").GetString());
        Assert.Equal("Alíquota interna (mercadoria 4002): 18 → 25.0000", evento.GetProperty("texto").GetString());
        var mudanca = evento.GetProperty("dados").GetProperty("mudancas")[0];
        Assert.Equal("18", mudanca.GetProperty("de").GetString());
        Assert.Equal("25.0000", mudanca.GetProperty("para").GetString());
        Assert.Equal("Sem 0200 para a mercadoria", mudanca.GetProperty("motivo").GetString());
    }

    [Fact]
    public async Task Desfazer_nao_apaga_e_registra_o_caminho_de_volta()
    {
        var (_, c) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(c);
        await c.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new
        {
            correcoes = new[] { new { campo = "quantidade", valor = "3", motivo = "ERP escriturou 2 por engano",
                                      documento = "71782", numero_item = 1, valor_anterior = "2" } },
        });
        var id = await banco.Escalar<int>($"SELECT id FROM correcao WHERE projeto_id = {projeto}");

        var r = await c.DeleteAsync($"/api/projetos/{projeto}/correcoes/{id}");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("desfeita", await banco.Escalar<string>($"SELECT situacao FROM correcao WHERE id = {id}"));
        Assert.Equal(1L, await banco.Escalar<long>($"SELECT count(*) FROM correcao WHERE projeto_id = {projeto}"));

        // some da lista de ativas, mas continua no histórico e na lista completa
        var ativas = await (await c.GetAsync($"/api/projetos/{projeto}/correcoes")).Content
            .ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, ativas.GetProperty("correcoes").GetArrayLength());
        var todas = await (await c.GetAsync($"/api/projetos/{projeto}/correcoes?todas=true")).Content
            .ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, todas.GetProperty("correcoes").GetArrayLength());

        var historico = await (await c.GetAsync($"/api/projetos/{projeto}/historico")).Content
            .ReadFromJsonAsync<JsonElement>();
        var evento = historico.GetProperty("eventos").EnumerateArray()
            .First(e => e.GetProperty("tipo").GetString() == "correcao_desfeita");
        Assert.Contains("volta ao que era: 3.000000 → 2", evento.GetProperty("texto").GetString());

        // desfazer de novo é recusado, e com explicação
        Assert.Equal(HttpStatusCode.UnprocessableEntity,
            (await c.DeleteAsync($"/api/projetos/{projeto}/correcoes/{id}")).StatusCode);
    }

    [Fact]
    public async Task Recusa_o_que_o_dominio_nao_aceita()
    {
        var (_, c) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(c);

        var semMotivo = await c.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new
        {
            correcoes = new[] { new { campo = "aliquota", valor = "25", motivo = "", codigo = "4002" } },
        });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, semMotivo.StatusCode);
        Assert.Contains("motivo escrito", await Detalhe(semMotivo));

        var vazio = await c.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new { correcoes = Array.Empty<object>() });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, vazio.StatusCode);
        Assert.Equal(0L, await banco.Escalar<long>($"SELECT count(*) FROM correcao WHERE projeto_id = {projeto}"));
    }

    [Fact]
    public async Task Quem_nao_escreve_nao_corrige_e_quem_nao_enxerga_nao_le()
    {
        var (_, dono) = await Pessoa("gestor");
        var (_, projeto) = await Trabalho(dono);
        var (_, deFora) = await Pessoa("analista");
        var (_, leitor) = await Pessoa("leitor");

        Assert.Equal(HttpStatusCode.Forbidden, (await deFora.GetAsync($"/api/projetos/{projeto}/correcoes")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await leitor.PostAsJsonAsync($"/api/projetos/{projeto}/correcoes", new
        {
            correcoes = new[] { new { campo = "aliquota", valor = "25", motivo = "motivo bom", codigo = "4002" } },
        })).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await dono.GetAsync("/api/projetos/999999/correcoes")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Cliente().GetAsync($"/api/projetos/{projeto}/correcoes")).StatusCode);
    }
}
