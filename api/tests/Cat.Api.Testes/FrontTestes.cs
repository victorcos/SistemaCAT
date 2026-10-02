using System.Net;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Cat.Api.Testes;

/// <summary>
/// A API servindo o front na mesma origem.
///
/// **Por que a API serve o front.** Os funcionários abriam o dev server do Vite
/// pela rede, e `http://&lt;ip&gt;:5173` não é contexto seguro — sem ele o
/// navegador não tem seletor de pasta, e o download antigo segurava o arquivo
/// inteiro na memória da aba. Na mesma origem não há proxy no caminho dos bytes,
/// não há CORS, não há `allowedHosts`, e o contexto é seguro para todo mundo.
///
/// **O que estes testes guardam** é a fronteira entre as duas coisas que a API
/// passou a servir. O desvio do SPA atende qualquer caminho: se ele ganhar de
/// `/api/{**resto}`, uma rota de API inexistente devolve `index.html` com 200, e
/// a tela recebe HTML onde esperava JSON — "erro" na cara da pessoa, sem dizer
/// qual. E o cabeçalho de cache separa o que pode ficar guardado para sempre do
/// que nunca pode: `index.html` em cache deixa a pessoa numa versão que já não
/// existe, pedindo arquivos que foram embora.
/// </summary>
public sealed class FrontTestes(MotorFalso motor) : IClassFixture<MotorFalso>, IDisposable
{
    private readonly string _raiz = Directory.CreateTempSubdirectory("cat-front-").FullName;
    private readonly List<WebApplicationFactory<Program>> _fabricas = [];

    private string Backend => Path.Combine(_raiz, "backend");
    private string Dist => Path.Combine(_raiz, "dist");

    public void Dispose()
    {
        foreach (var f in _fabricas)
            f.Dispose();
        Directory.Delete(_raiz, recursive: true);
    }

    /// <summary>Um `dist` de mentira, com a forma que o Vite produz.</summary>
    private void Construir()
    {
        Directory.CreateDirectory(Path.Combine(Backend));
        File.WriteAllText(Path.Combine(_raiz, "VERSAO"), "1.2.3\n");
        File.WriteAllText(Path.Combine(Backend, "pyproject.toml"), "[project]\n");
        File.WriteAllText(Path.Combine(Backend, ".env"), "\n");
        var assets = Directory.CreateDirectory(Path.Combine(Dist, "assets")).FullName;
        File.WriteAllText(Path.Combine(Dist, "index.html"), "<!doctype html><title>CAT</title>");
        // nome com resumo do conteúdo, como o Vite escreve
        File.WriteAllText(Path.Combine(assets, "index-A1b2C3d4.js"), "console.log(1)");
    }

    private HttpClient Cliente(string? front)
    {
        Construir();
        var fabrica = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", Backend);
            b.UseSetting("CAT_MOTOR_URL", motor.Endereco.ToString());
            b.UseSetting("CAT_MOTOR_SEGREDO", MotorFalso.Segredo);
            if (front is not null)
                b.UseSetting("CAT_PASTA_DO_FRONT", front);
        });
        _fabricas.Add(fabrica);
        return fabrica.CreateClient();
    }

    [Fact]
    public async Task Rota_de_api_que_nao_existe_devolve_JSON_e_nao_o_index()
    {
        // o teste mais importante deste arquivo: se o desvio do SPA ganhar
        // daqui, toda falha de API passa a chegar à tela como HTML
        var c = Cliente(Dist);

        var r = await c.GetAsync("/api/nao-existe");

        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        Assert.StartsWith("application/json", r.Content.Headers.ContentType!.ToString());
        Assert.Contains("Esta rota não existe na API", await r.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task A_api_continua_respondendo_com_o_front_servido()
    {
        var c = Cliente(Dist);

        var r = await c.GetAsync("/api/saude");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.StartsWith("application/json", r.Content.Headers.ContentType!.ToString());
    }

    [Theory]
    [InlineData("/")]
    [InlineData("/index.html")]
    [InlineData("/projetos/1")]
    [InlineData("/qualquer/rota/do/spa")]
    public async Task Caminho_do_spa_devolve_o_index_sem_cache(string caminho)
    {
        // **sem cache em todos eles, e não só em `/index.html`.** O
        // `MapFallbackToFile` tem opções próprias: quando elas divergiam das do
        // `UseStaticFiles`, o mesmo arquivo saía com `no-cache` pedido como
        // `/index.html` e sem cabeçalho nenhum pedido como `/`
        var c = Cliente(Dist);

        var r = await c.GetAsync(caminho);

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.StartsWith("text/html", r.Content.Headers.ContentType!.ToString());
        Assert.Equal("no-cache", r.Headers.CacheControl!.ToString());
    }

    [Fact]
    public async Task Arquivo_com_resumo_no_nome_fica_em_cache_para_sempre()
    {
        // nome igual é conteúdo igual: o Vite garante isso pelo resumo no nome
        var c = Cliente(Dist);

        var r = await c.GetAsync("/assets/index-A1b2C3d4.js");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var cache = r.Headers.CacheControl!;
        Assert.True(cache.Public);
        Assert.Equal(TimeSpan.FromDays(365), cache.MaxAge);
        Assert.Contains("immutable", cache.ToString());
    }

    [Fact]
    public async Task Sem_a_pasta_configurada_a_api_nao_serve_front_nenhum()
    {
        // é o padrão, e serve ao desenvolvimento: quem roda o Vite não quer a
        // API servindo uma cópia velha do front por cima
        var c = Cliente(front: null);

        var r = await c.GetAsync("/projetos/1");

        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
    }

    [Fact]
    public async Task Pasta_configurada_que_nao_existe_nao_derruba_a_api()
    {
        // quem esqueceu o `npm run build` tem de ver a API no ar e um aviso no
        // log, não um processo que morre na subida
        var c = Cliente(Path.Combine(_raiz, "dist-que-nao-existe"));

        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/saude")).StatusCode);
    }
}
