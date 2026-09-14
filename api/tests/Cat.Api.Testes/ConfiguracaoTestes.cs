using Cat.Infraestrutura.Configuracao;
using Microsoft.Extensions.Configuration;

namespace Cat.Api.Testes;

public sealed class ArquivoEnvTestes
{
    [Fact]
    public void Le_o_formato_que_o_instalador_grava()
    {
        // BOM, CRLF, comentário e linha em branco: o que o instalar.ps1 produz
        var conteudo = "\uFEFF# Ambiente do Sistema CAT\r\n\r\nCAT_BANCO_URL=postgresql+psycopg://cat:cat@localhost:55432/cat\r\n" +
                       "CAT_JWT_SEGREDO=abc=def==\r\n  CAT_LOG_NIVEL = WARNING  \r\nCAT_ORIGENS_PERMITIDAS=\"http://a,http://b\"\r\n";

        var valores = ArquivoEnv.Interpretar(conteudo);

        Assert.Equal("postgresql+psycopg://cat:cat@localhost:55432/cat", valores["CAT_BANCO_URL"]);
        // só o primeiro "=" separa: segredo em base64 termina em "="
        Assert.Equal("abc=def==", valores["CAT_JWT_SEGREDO"]);
        Assert.Equal("WARNING", valores["CAT_LOG_NIVEL"]);
        Assert.Equal("http://a,http://b", valores["CAT_ORIGENS_PERMITIDAS"]);
        Assert.Equal(4, valores.Count);
    }

    [Fact]
    public void Arquivo_ausente_nao_derruba()
    {
        Assert.Empty(ArquivoEnv.Ler(Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"), ".env")));
    }
}

public sealed class ConfigCatTestes : IDisposable
{
    // repositório de mentira: VERSAO na raiz, backend/ dentro dela
    private readonly string _raiz = Directory.CreateTempSubdirectory("cat-config-").FullName;
    private readonly string _backend;

    public ConfigCatTestes() => Directory.CreateDirectory(_backend = Path.Combine(_raiz, "backend"));

    public void Dispose() => Directory.Delete(_raiz, recursive: true);

    private ConfigCat Carregar(Dictionary<string, string?> ambiente)
    {
        ambiente["CAT_RAIZ_BACKEND"] = _backend;
        return ConfigCat.Carregar(new ConfigurationBuilder().AddInMemoryCollection(ambiente).Build());
    }

    [Fact]
    public void Ambiente_vence_o_arquivo_que_vence_o_padrao()
    {
        File.WriteAllText(Path.Combine(_backend, ".env"),
            "CAT_LOG_NIVEL=WARNING\nCAT_MEMORIA_ANALITICA=8GB\n");

        var config = Carregar(new() { ["CAT_LOG_NIVEL"] = "ERROR" });

        Assert.Equal("ERROR", config.LogNivel);               // do ambiente
        Assert.Equal("8GB", config.MemoriaAnalitica);         // do arquivo
        Assert.Equal(4, config.ThreadsAnaliticas);            // padrão
        Assert.Equal(new Uri("http://127.0.0.1:8020"), config.MotorUrl);
        Assert.Equal(8010, config.PortaApi);
    }

    [Fact]
    public void Pasta_de_trabalho_relativa_resolve_contra_o_backend_e_nao_contra_o_processo()
    {
        var config = Carregar(new());

        Assert.Equal(Path.Combine(_backend, "data", "trabalho"), config.PastaDeTrabalho);
    }

    [Theory]
    [InlineData("1.2.3\n", "1.2.3")]
    [InlineData("\uFEFF1.2.3\r\n", "1.2.3")]     // gravado pelo Windows
    [InlineData("0.35.0-rc.1", "0.35.0-rc.1")]
    public void Versao_vem_do_arquivo_VERSAO_na_raiz(string conteudo, string esperada)
    {
        File.WriteAllText(Path.Combine(_raiz, "VERSAO"), conteudo);
        // o pyproject deixou de ser a fonte: um número velho nele não conta
        File.WriteAllText(Path.Combine(_backend, "pyproject.toml"), "version = \"0.0.1\"\n");

        Assert.Equal(esperada, Carregar(new()).Versao);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("version = \"1.2.3\"")]
    [InlineData("1.2.3\n4.5.6\n")]
    public void Sem_VERSAO_legivel_a_versao_diz_que_nao_sabe_em_vez_de_inventar(string? conteudo)
    {
        if (conteudo is not null)
            File.WriteAllText(Path.Combine(_raiz, "VERSAO"), conteudo);

        Assert.Equal("desconhecida", Carregar(new()).Versao);
    }
}
