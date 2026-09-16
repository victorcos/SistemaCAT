using Cat.Dominio.Acesso;

namespace Cat.Dominio.Projeto;

public sealed record DefinicaoDeStatus(string Valor, string Rotulo, string Explicacao, bool ExigeMotivo, bool AceitaProcessamento);

/// <summary>
/// Em que pé o trabalho está, portado de <c>dominio/projeto/historico.py</c>.
///
/// São quatro e não mais: status demais vira campo que ninguém mantém. A
/// diferença que importa é entre trabalhando, parado por uma razão e acabou — e
/// "acabou" tem dois finais possíveis, o bom e o outro.
///
/// <see cref="DefinicaoDeStatus.AceitaProcessamento"/> vale também no motor, que
/// barra etapa em trabalho parado; a regra de lá (<c>exigir_que_ande</c>) lê o
/// mesmo valor gravado.
/// </summary>
public static class StatusDoProjeto
{
    public const string EmAndamento = "em_andamento";
    public const string Pausado = "pausado";
    public const string Cancelado = "cancelado";
    public const string Concluido = "concluido";

    public static readonly IReadOnlyList<DefinicaoDeStatus> Todos =
    [
        new(EmAndamento, "Em andamento", "O trabalho está correndo.", ExigeMotivo: false, AceitaProcessamento: true),
        new(Pausado, "Pausado",
            "Parado por ora — em geral esperando o cliente. Volta a andar " +
            "sem perder nada do que já foi feito.",
            // parar sem dizer por quê é o que gera a pergunta de três meses depois
            ExigeMotivo: true, AceitaProcessamento: false),
        new(Cancelado, "Cancelado",
            "Não vai seguir. Fica no sistema com o histórico inteiro; " +
            "cancelar não é apagar.",
            ExigeMotivo: true, AceitaProcessamento: false),
        new(Concluido, "Concluído", "Entregue.", ExigeMotivo: false, AceitaProcessamento: true),
    ];

    public static DefinicaoDeStatus? Buscar(string? valor) => Todos.FirstOrDefault(s => s.Valor == valor);

    /// <summary>Status gravado que não se conhece vale como em andamento, como no Python.</summary>
    public static DefinicaoDeStatus DoBanco(string? valor) => Buscar(valor) ?? Todos[0];

    /// <summary>Status desconhecido aparece como gravado, em vez de derrubar a listagem.</summary>
    public static string Rotulo(string valor) => Buscar(valor)?.Rotulo ?? valor;
}

/// <summary>
/// O que pode entrar na linha do tempo. O valor é gravado no banco: mudar um
/// destes textos reescreve o passado, então só se acrescenta.
/// </summary>
public static class TipoDeEvento
{
    public const string Criado = "criado";
    public const string Comentario = "comentario";
    public const string Status = "status";
    public const string Sucessao = "sucessao";
    public const string LoteImportado = "lote_importado";
    public const string LoteRemovido = "lote_removido";
    public const string EtapaIniciada = "etapa_iniciada";
    public const string EtapaConcluida = "etapa_concluida";
    public const string EtapaFalhou = "etapa_falhou";
    public const string PlanilhaBaixada = "planilha_baixada";
    public const string ParametroAlterado = "parametro_alterado";
    public const string EntregaAprovada = "entrega_aprovada";

    private static readonly Dictionary<string, string> Rotulos = new()
    {
        [Criado] = "Trabalho criado",
        [Comentario] = "Comentário",
        [Status] = "Status alterado",
        [Sucessao] = "Responsável alterado",
        [LoteImportado] = "Arquivos importados",
        [LoteRemovido] = "Lote removido",
        [EtapaIniciada] = "Etapa iniciada",
        [EtapaConcluida] = "Etapa concluída",
        [EtapaFalhou] = "Etapa falhou",
        [PlanilhaBaixada] = "Planilha baixada",
        [ParametroAlterado] = "Parâmetro do trabalho alterado",
        [EntregaAprovada] = "Entrega aprovada",
    };

    /// <summary>
    /// Tipo gravado por uma versão mais nova do motor aparece como comentário,
    /// em vez de sumir da linha do tempo — o mesmo que o Python fazia.
    /// </summary>
    public static string Conhecido(string tipo) => Rotulos.ContainsKey(tipo) ? tipo : Comentario;

    public static string Rotulo(string tipo) => Rotulos.GetValueOrDefault(tipo, tipo);
}

public sealed class ComentarioVazio() : RecusaDeRegra("O comentário não pode ficar vazio.");

public sealed class ComentarioLongoDemais() : RecusaDeRegra(
    $"O comentário passa de {Historico.TamanhoMaximoDoComentario} caracteres. " +
    "Se precisa de tudo isso, provavelmente é um documento — anexe o " +
    "arquivo no lote e comente o essencial.");

public sealed class MesmoStatus(DefinicaoDeStatus status)
    : RecusaDeRegra($"O trabalho já está como {status.Rotulo.ToLowerInvariant()}.");

public sealed class MotivoObrigatorio(DefinicaoDeStatus status) : RecusaDeRegra(
    $"Diga por que o trabalho está sendo {status.Rotulo.ToLowerInvariant()}. " +
    "Sem o motivo, daqui a três meses ninguém sabe responder.");

/// <summary>
/// As regras da linha do tempo. Evento não se apaga nem se edita: é registro,
/// não anotação. Comentário errado se corrige com outro comentário.
/// </summary>
public static class Historico
{
    public const int TamanhoMaximoDoComentario = 2000;

    public static string ValidarComentario(string texto)
    {
        var limpo = texto.Trim();
        if (limpo.Length == 0)
            throw new ComentarioVazio();
        if (limpo.EnumerateRunes().Count() > TamanhoMaximoDoComentario)
            throw new ComentarioLongoDemais();
        return limpo;
    }

    public static void ValidarMudancaDeStatus(DefinicaoDeStatus atual, DefinicaoDeStatus novo, string motivo)
    {
        if (atual.Valor == novo.Valor)
            throw new MesmoStatus(novo);
        if (novo.ExigeMotivo && motivo.Trim().Length == 0)
            throw new MotivoObrigatorio(novo);
    }

    // As frases ficam no domínio, e não na tela: a mesma frase vale para a
    // tela, para o log e para um relatório futuro.
    public static string FraseDeStatus(DefinicaoDeStatus de, DefinicaoDeStatus para) => $"{de.Rotulo} → {para.Rotulo}";

    public static string FraseDeSucessao(string? de, string para) =>
        de is null ? $"Responsável definido: {para}" : $"{de} → {para}";
}
