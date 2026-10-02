using System.Buffers.Text;
using System.Security.Cryptography;

namespace Cat.Aplicacao.Trabalhos;

/// <summary>
/// O que um tíquete autoriza — e é só isto que a rota serve.
///
/// Cada campo faz parte do que o arquivo **é**: trocar o formato ou o recorte
/// muda o arquivo entregue. Por isso o tíquete carrega todos, e a rota de
/// download serve o que ele descreve, nunca o que a URL pedir. Sem isso, quem
/// tivesse um tíquete de um CSV pequeno pediria o xlsx inteiro com ele.
/// </summary>
public sealed record AutorizacaoDeDownload(
    int UsuarioId,
    int ExecucaoId,
    string Etapa,
    string Qual,
    string Formato,
    string? Modelos,
    string? Classificacoes);

/// <summary>
/// Tíquetes de download: autorização de vida curta para baixar por navegação.
///
/// ## Por que existe
///
/// O front baixava com <c>fetch</c> e <c>blob</c> — o arquivo inteiro na memória
/// da aba antes de gravar. Numa lista de 2,93 milhões de linhas isso não passa,
/// e a API já fazia a parte dela certo: serve do disco em fluxo. Todo o
/// desperdício estava no navegador.
///
/// A saída é deixar o **navegador** baixar, por navegação: o gerenciador dele
/// grava direto no disco, mostra progresso, não tem teto de tamanho e funciona
/// em qualquer navegador, com ou sem contexto seguro. Mas navegação não manda
/// cabeçalho <c>Authorization</c> — e é essa lacuna que o tíquete fecha.
///
/// ## O prazo é a proteção
///
/// Dois minutos, amarrado a um usuário e a um arquivo. Um tíquete que vaze no
/// histórico do navegador ou num log é inútil depois disso.
///
/// **Uso único seria mais apertado no papel e hostil na prática:** o gerenciador
/// de download do navegador repete a requisição — queda de rede,
/// redirecionamento, às vezes um <c>HEAD</c> antes do <c>GET</c> —, e recusar a
/// repetição transforma um soluço de rede em "o link morreu". Por isso
/// <c>usado_em</c> é auditoria, não trava.
///
/// E porque não há trava, não há corrida a proteger: duas instâncias resgatando
/// o mesmo tíquete chegam ao mesmo resultado.
/// </summary>
public interface ITiquetesDeDownload
{
    /// <summary>Emite um tíquete e devolve o segredo que vai na URL.</summary>
    Task<string> Emitir(AutorizacaoDeDownload autorizacao, DateTimeOffset agora,
        CancellationToken cancelar);

    /// <summary>
    /// O que este tíquete autoriza, ou nulo se não existe ou venceu.
    ///
    /// **A validade vale no início da requisição, não durante.** Um xlsx de
    /// dezesseis minutos é autorizado quando o download começa; o prazo não
    /// interrompe transferência em curso.
    /// </summary>
    Task<AutorizacaoDeDownload?> Resgatar(string tiquete, DateTimeOffset agora,
        CancellationToken cancelar);
}

public static class Tiquete
{
    /// <summary>
    /// Quanto tempo o tíquete vale.
    ///
    /// Dois minutos: a navegação acontece no mesmo instante do clique, e o resto
    /// é folga para uma página lenta. Mais que isso aumenta a janela de um
    /// segredo que anda na URL sem comprar nada.
    /// </summary>
    public static readonly TimeSpan Validade = TimeSpan.FromMinutes(2);

    /// <summary>
    /// O nome do parâmetro na URL. Curto porque anda em endereço de download.
    /// </summary>
    public const string Parametro = "t";

    /// <summary>
    /// Trinta e dois bytes aleatórios em base64url.
    ///
    /// <c>RandomNumberGenerator</c> e não <c>Random</c>: este valor é a
    /// credencial, e `Random` é previsível a partir de amostras. Base64url
    /// porque o valor anda em URL — sem <c>+</c>, <c>/</c> nem <c>=</c> para
    /// alguém escapar errado no caminho.
    /// </summary>
    public static string NovoSegredo() =>
        Base64Url.EncodeToString(RandomNumberGenerator.GetBytes(32));
}
