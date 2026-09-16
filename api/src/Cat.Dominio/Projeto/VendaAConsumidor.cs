using Cat.Dominio.Acesso;

namespace Cat.Dominio.Projeto;

public sealed record DefinicaoDeVendaAConsumidor(string Valor, string Rotulo, string Explicacao);

/// <summary>
/// Como o trabalho enquadra a venda a consumidor final, espelho de
/// <c>VendaAConsumidor</c> em <c>dominio/cat42/enquadramento.py</c>. É escolha de
/// cada trabalho (decisão do Victor, 16/09/2026), porque muda o valor do pedido.
///
/// O manual põe a venda a consumidor no enquadramento 1: ressarcimento quando se
/// vendeu abaixo da base presumida, complemento quando acima. A IRMAOS BOA
/// transmitiu o cupom no 0, e só a perda (5.927) gerou ressarcimento.
/// </summary>
public static class VendaAConsumidor
{
    public const string Enquadramento1 = "enquadramento_1";
    public const string DemaisSaidas = "demais_saidas";

    public static readonly IReadOnlyList<DefinicaoDeVendaAConsumidor> Todas =
    [
        new(Enquadramento1, "Enquadramento 1: pede ressarcimento e recolhe complemento",
            "Como diz o manual. A venda a consumidor final confronta o ICMS suportado com a alíquota " +
            "vezes o preço: abaixo da base presumida gera ressarcimento, acima gera complemento."),
        new(DemaisSaidas, "Demais saídas (0): só as perdas e as interestaduais",
            "Como a BOA transmitiu. O cupom vai com enquadramento 0 e não há complemento; o " +
            "ressarcimento vem da baixa de estoque (5.927) e da venda para outro estado."),
    ];

    public static DefinicaoDeVendaAConsumidor? Buscar(string? valor) => Todas.FirstOrDefault(v => v.Valor == valor);

    /// <summary>Vazio é o padrão do manual, que é como todo trabalho antigo foi montado.</summary>
    public static DefinicaoDeVendaAConsumidor DoBanco(string? valor) => Buscar(valor) ?? Todas[0];
}

public sealed class VendaAConsumidorDesconhecida(string valor) : RecusaDeRegra(
    $"Escolha desconhecida para a venda a consumidor: {valor}. Use uma de: " +
    $"{string.Join(", ", VendaAConsumidor.Todas.Select(v => v.Valor))}.");

public sealed class MesmaVendaAConsumidor(DefinicaoDeVendaAConsumidor atual)
    : RecusaDeRegra($"O trabalho já está assim: {atual.Rotulo.ToLowerInvariant()}.");
