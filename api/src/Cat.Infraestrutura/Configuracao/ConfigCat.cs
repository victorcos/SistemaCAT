using System.Text.RegularExpressions;
using Microsoft.Extensions.Configuration;

namespace Cat.Infraestrutura.Configuracao;

/// <summary>
/// Configuração por variável de ambiente, com o mesmo prefixo <c>CAT_</c> do
/// Python. Nenhum segredo no código.
///
/// Precedência igual à do pydantic-settings: variável de ambiente, depois o
/// <c>backend/.env</c>, depois o padrão escrito aqui.
/// </summary>
public sealed partial class ConfigCat
{
    public required string RaizBackend { get; init; }
    public required string LogNivel { get; init; }
    public required IReadOnlyList<string> Origens { get; init; }
    public required string PastaDeTrabalho { get; init; }
    public required string MemoriaAnalitica { get; init; }
    public required int ThreadsAnaliticas { get; init; }
    public required int PortaApi { get; init; }
    public required Uri MotorUrl { get; init; }
    public required string Versao { get; init; }

    // ---------- segredos: nunca vão para log nem para o /api/saude ----------
    public required string BancoUrl { get; init; }
    public required string JwtSegredo { get; init; }
    public required string JwtAlgoritmo { get; init; }
    public required int JwtMinutos { get; init; }
    public required string SenhaPimenta { get; init; }

    /// <summary>
    /// Segredo do canal interno com o motor. Quem chega à porta do motor sem
    /// ele não apaga pasta nem lê disco, mesmo estando na própria máquina.
    /// </summary>
    public required string MotorSegredo { get; init; }

    public const string SegredoPadrao = "trocar-em-producao-isto-nao-e-segredo";
    public bool SegredoEPadrao => JwtSegredo.StartsWith("trocar-em-producao", StringComparison.Ordinal);
    public bool SemPimenta => SenhaPimenta.Length == 0;

    /// <param name="config">
    /// Configuração do host. Já traz as variáveis de ambiente, e é por ela que
    /// os testes trocam um valor sem mexer no ambiente do processo inteiro.
    /// </param>
    public static ConfigCat Carregar(IConfiguration config)
    {
        var raiz = config["CAT_RAIZ_BACKEND"] is { Length: > 0 } explicita
            ? Path.GetFullPath(explicita)
            : LocalizarBackend();

        var arquivo = config["CAT_ENV_ARQUIVO"] is { Length: > 0 } envExplicito
            ? envExplicito
            : Path.Combine(raiz, ".env");
        var env = ArquivoEnv.Ler(arquivo);

        string Valor(string chave, string padrao) =>
            config[chave] is { Length: > 0 } doAmbiente ? doAmbiente
            : env.TryGetValue(chave, out var doArquivo) && doArquivo.Length > 0 ? doArquivo
            : padrao;

        return new ConfigCat
        {
            RaizBackend = raiz,
            LogNivel = Valor("CAT_LOG_NIVEL", "INFO").ToUpperInvariant(),
            Origens = Valor("CAT_ORIGENS_PERMITIDAS", "http://localhost:5173")
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries),
            // Relativo ao backend, não ao diretório de onde o processo subiu. O
            // Python resolve contra o diretório corrente, que é sempre backend/
            // quando sobe pelo subir.ps1; aqui o diretório corrente é outro, e
            // dois processos gravando em pastas diferentes sem ninguém perceber
            // é exatamente o defeito que o /api/saude existe para denunciar.
            PastaDeTrabalho = Path.GetFullPath(Valor("CAT_PASTA_DE_TRABALHO", "data/trabalho"), raiz),
            MemoriaAnalitica = Valor("CAT_MEMORIA_ANALITICA", "4GB"),
            ThreadsAnaliticas = int.Parse(Valor("CAT_THREADS_ANALITICAS", "4")),
            PortaApi = int.Parse(Valor("CAT_API_PORTA", "8010")),
            // 127.0.0.1 e não localhost: no Windows "localhost" tenta ::1
            // primeiro, e o motor escuta só em IPv4 — cada chamada pagaria a
            // tentativa frustrada antes de acertar.
            MotorUrl = new Uri(Valor("CAT_MOTOR_URL", "http://127.0.0.1:8020")),
            Versao = LerVersao(Path.Combine(raiz, "..", "VERSAO")),
            // os padrões são os do config.py: só existem para o dev subir
            BancoUrl = Valor("CAT_BANCO_URL", "postgresql+psycopg://cat:cat@localhost:55432/cat"),
            JwtSegredo = Valor("CAT_JWT_SEGREDO", SegredoPadrao),
            JwtAlgoritmo = Valor("CAT_JWT_ALGORITMO", "HS256"),
            JwtMinutos = int.Parse(Valor("CAT_JWT_MINUTOS", "480")),
            SenhaPimenta = Valor("CAT_SENHA_PIMENTA", ""),
            MotorSegredo = Valor("CAT_MOTOR_SEGREDO", ""),
        };
    }

    /// <summary>
    /// A versão vem do arquivo <c>VERSAO</c> na raiz do repositório, lido
    /// também pelo motor: dois programas, um número. Escrever o número aqui
    /// repetiria o defeito de quando a API dizia 0.3.0 com as etiquetas do git
    /// em v0.15.2.
    /// </summary>
    public static string LerVersao(string arquivo)
    {
        if (!File.Exists(arquivo))
            return "desconhecida";
        var achado = NumeroDeVersao().Match(File.ReadAllText(arquivo));
        return achado.Success ? achado.Groups[1].Value : "desconhecida";
    }

    /// <summary>
    /// Sobe a partir de onde o programa está até achar <c>backend/pyproject.toml</c>.
    /// Assim a API acha o .env tanto por <c>dotnet run</c> quanto pelo binário
    /// compilado, sem caminho escrito à mão.
    /// </summary>
    private static string LocalizarBackend()
    {
        foreach (var partida in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
        {
            for (var pasta = new DirectoryInfo(partida); pasta is not null; pasta = pasta.Parent)
            {
                var candidato = Path.Combine(pasta.FullName, "backend");
                if (File.Exists(Path.Combine(candidato, "pyproject.toml")))
                    return candidato;
            }
        }
        throw new InvalidOperationException(
            "Não achei a pasta backend/ com o pyproject.toml subindo a partir de " +
            $"{AppContext.BaseDirectory}. Defina CAT_RAIZ_BACKEND.");
    }

    // o número sozinho no arquivo: "0.35.0"; qualquer outra coisa é não saber.
    // O BOM que o Windows grava o File.ReadAllText já descarta.
    [GeneratedRegex("""\A\s*(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s*\z""")]
    private static partial Regex NumeroDeVersao();
}
