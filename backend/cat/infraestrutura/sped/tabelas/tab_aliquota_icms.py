"""A alíquota de ICMS aplicável a uma operação — a parte que é regra.

Serve ao **ICMS-ST presumido** do relatório 839: como a revenda de mercadoria
com ST já retido não destaca imposto nenhum, o ST que se exclui da base do
PIS/COFINS precisa ser reconstruído, e a alíquota é metade dessa reconstrução.

## O que é regra e o que é cadastro

**Regra, e mora aqui:**

* na operação **interestadual**, a alíquota é a da Resolução 22/1989 do Senado
  — 7% do Sul/Sudeste para o Norte, Nordeste, Centro-Oeste e Espírito Santo,
  12% no resto;
* na operação **interna**, a alíquota padrão do estado.

**Cadastro, e mora no banco:** a alíquota interna de um *produto específico*,
quando ele foge do padrão — cesta básica a 12%, supérfluo a 25%, isento a 0%,
importado a 4%. Isso é classificação fiscal de mercadoria, muda de item para
item, e **não está no SPED**: o `ALIQ_ICMS` do registro 0200 é facultativo e
veio vazio nos 8.061 cadastros do arquivo de referência. Por ser dado do
cliente, fica na tabela `aliquota_de_item` e nunca no repositório.

## Por que a separação importa

Medido no gabarito do 839 (463.212 linhas, 30/09/2026): a **regra sozinha
acerta 98,66%** das linhas, e as exceções são 556 pares de (estabelecimento,
UF, item), que valem R$ 12.785,29 de um total de R$ 2,67 milhões.

Podia-se copiar as 7.276 alíquotas do relatório do MA e fechar 100% sem pensar.
Não se fez: o que é lei fica escrito como lei, auditável por quem assina, e o
que é cadastro fica identificado como cadastro — de outro modo o relatório
inteiro seria uma cópia da classificação alheia, com aparência de cálculo.
"""

from __future__ import annotations

from decimal import Decimal

# Resolução 22/1989 do Senado: 7% nas saídas do Sul/Sudeste para o Norte,
# Nordeste, Centro-Oeste e Espírito Santo; 12% nas demais interestaduais
SUL_SUDESTE = frozenset({"MG", "PR", "RJ", "RS", "SC", "SP"})
NORTE_NORDESTE_CENTRO_OESTE = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO",
})

SETE = Decimal(7)
DOZE = Decimal(12)

# A alíquota interna padrão de cada estado. É a geral, a que se aplica quando o
# produto não tem tratamento próprio — e é por isso que a exceção por item
# existe. Fonte: legislação estadual vigente em 30/09/2026.
#
# **Só MG está conferida contra dado real**, no gabarito do 839 da DMINAS. As
# demais entram do conhecimento público e merecem conferência antes do primeiro
# trabalho em cada estado: alíquota interna mudou em vários deles entre 2023 e
# 2025, e errar aqui erra o pedido inteiro daquele cliente.
INTERNA: dict[str, Decimal] = {
    "AC": Decimal(19), "AL": Decimal(20), "AM": Decimal(20), "AP": Decimal(18),
    "BA": Decimal(20), "CE": Decimal(20), "DF": Decimal(20), "ES": Decimal(17),
    "GO": Decimal(19), "MA": Decimal(22), "MG": Decimal(18), "MS": Decimal(17),
    "MT": Decimal(17), "PA": Decimal(19), "PB": Decimal(20), "PE": Decimal("20.5"),
    "PI": Decimal(21), "PR": Decimal("19.5"), "RJ": Decimal(20), "RN": Decimal(20),
    "RO": Decimal("19.5"), "RR": Decimal(20), "RS": Decimal(17), "SC": Decimal(17),
    "SE": Decimal(19), "SP": Decimal(18), "TO": Decimal(20),
}


class AliquotaDesconhecida(LookupError):
    """Pediram a alíquota interna de um estado que a tabela não tem."""


def da_regra(origem: str, destino: str) -> Decimal:
    """A alíquota que a lei manda, sem olhar o produto.

    `origem` e `destino` são siglas de UF. Interestadual segue a Resolução do
    Senado; interna, a alíquota padrão do estado.

    Levanta `AliquotaDesconhecida` quando o estado não está na tabela, em vez
    de devolver um palpite: alíquota errada aqui não aparece em lugar nenhum do
    relatório — vira só um número menor.
    """
    origem, destino = (origem or "").strip().upper(), (destino or "").strip().upper()
    if origem and destino and origem != destino:
        return (SETE if origem in SUL_SUDESTE
                and destino in NORTE_NORDESTE_CENTRO_OESTE else DOZE)
    interna = INTERNA.get(destino or origem)
    if interna is None:
        raise AliquotaDesconhecida(
            f"A alíquota interna de {destino or origem or '(sem UF)'} não está em "
            "`tab_aliquota_icms.INTERNA`. Acrescente-a antes de apurar o ICMS-ST "
            "deste estado.")
    return interna


def aplicavel(origem: str, destino: str, cnpj: str, codigo_do_item: str,
              excecoes: dict[tuple[str, str, str, str], Decimal] | None = None,
              ) -> Decimal:
    """A alíquota do produto nesta operação: a exceção, se houver; senão a regra.

    `excecoes` vem do banco (`aliquota_de_item`), com a classificação fiscal dos
    produtos que fogem do padrão. Vazio significa "nenhum produto foge" — o que
    é a verdade em quase todo estabelecimento e em 98,66% das linhas medidas.
    """
    if excecoes:
        chave = (cnpj, (origem or "").upper(), (destino or "").upper(), codigo_do_item)
        if (achada := excecoes.get(chave)) is not None:
            return achada
    return da_regra(origem, destino)
