using Cat.Dominio.Acesso;

namespace Cat.Dominio.Projeto;

/// <summary>O que a aprovação precisa saber da entrega e do trabalho, lido pelo caso de uso.</summary>
/// <param name="ArquivoDigitalUsado">a geração do arquivo digital que a entrega empacotou</param>
/// <param name="UltimoArquivoDigital">a última geração do arquivo digital que concluiu no trabalho</param>
public sealed record EntregaParaAprovar(
    int ExecucaoId,
    string Situacao,
    DateTimeOffset? AprovadaEm,
    string? AprovadaPor,
    int UltimaEntrega,
    int? ArquivoDigitalUsado,
    int? UltimoArquivoDigital,
    DefinicaoDeStatus StatusDoTrabalho);

public sealed class EntregaNaoMontada()
    : RecusaDeRegra("A entrega ainda não foi montada: espere a rodada terminar sem falha.");

public sealed class EntregaJaAprovada(string? por, DateTimeOffset em)
    : RecusaDeRegra($"Esta entrega já foi aprovada{(string.IsNullOrEmpty(por) ? "" : " por " + por)} em {em.ToLocalTime():dd/MM/yyyy HH:mm}.");

public sealed class EntregaSuperada(int maisNova)
    : RecusaDeRegra($"Há uma entrega mais nova (#{maisNova}). Confira e aprove a mais recente.");

public sealed class EntregaDesatualizada(int arquivoNovo)
    : RecusaDeRegra($"O arquivo digital foi gerado de novo (#{arquivoNovo}) depois desta entrega. " +
                    "Monte a entrega de novo antes de aprovar.");

public sealed class TrabalhoParadoNaoEntrega(DefinicaoDeStatus status)
    : RecusaDeRegra($"O trabalho está {status.Rotulo.ToLowerInvariant()}: volte a andar com ele antes de aprovar a entrega.");

public sealed class ObservacaoDaEntregaLongaDemais()
    : RecusaDeRegra($"A observação da aprovação passa de {Entrega.TamanhoMaximoDaObservacao} caracteres.");

/// <summary>
/// A aprovação da etapa 8. Gerar o pacote não é entregar: um revisor ou gestor
/// confere e aprova, e é a aprovação que conclui a etapa (decisão do Victor,
/// 16/09/2026). Quem pode aprovar é capacidade do papel
/// (<see cref="Capacidades.PodeAprovarEntrega"/>); aqui é o que a entrega
/// precisa estar para ser aprovada.
/// </summary>
public static class Entrega
{
    public const int TamanhoMaximoDaObservacao = 500;

    /// <summary>
    /// A ordem das recusas é a de quem vai resolver: primeiro o trabalho, depois
    /// a rodada, depois se ela ainda é a que vale.
    /// </summary>
    public static void ValidarAprovacao(EntregaParaAprovar e)
    {
        if (!e.StatusDoTrabalho.AceitaProcessamento)
            throw new TrabalhoParadoNaoEntrega(e.StatusDoTrabalho);
        if (e.Situacao != "concluida")
            throw new EntregaNaoMontada();
        if (e.AprovadaEm is { } em)
            throw new EntregaJaAprovada(e.AprovadaPor, em);
        if (e.UltimaEntrega != e.ExecucaoId)
            throw new EntregaSuperada(e.UltimaEntrega);
        // um pacote que leva o arquivo digital velho não pode virar a entrega do trabalho
        if (e.UltimoArquivoDigital is { } ultimo && ultimo != e.ArquivoDigitalUsado)
            throw new EntregaDesatualizada(ultimo);
    }

    /// <summary>Vazia é nenhuma; longa demais é recusa, não corte calado.</summary>
    public static string? ValidarObservacao(string? texto)
    {
        var limpo = (texto ?? "").Trim();
        if (limpo.Length == 0)
            return null;
        if (limpo.EnumerateRunes().Count() > TamanhoMaximoDaObservacao)
            throw new ObservacaoDaEntregaLongaDemais();
        return limpo;
    }
}
