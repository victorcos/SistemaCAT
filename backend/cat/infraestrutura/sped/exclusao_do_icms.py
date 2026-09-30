"""A exclusão do ICMS da base do PIS/COFINS — o Tema 69, item a item.

Equivalente à consulta **903 — C100, C170 — Detalhado por Nota Fiscal e Itens**
do Sistema MA, gerada só a partir da EFD-Contribuições. É o detalhe que instrui
o pedido de restituição: uma linha por item de nota, com a base original, a base
sem o ICMS, a diferença de cada contribuição e a correção pela Selic.

Conferido contra o gabarito do MA — 138.358 linhas, 57 competências — em
30/09/2026. Ver `tools/validar_903.py`.

## Quem entra

Dois filtros, e os dois são fiscais, não técnicos:

```
CFOP de venda (5102, 5405, 6102…) ou de devolução de venda (1202, 1411, 2202…)
    E   ICMS destacado maior que zero
    E   base de cálculo do PIS/COFINS maior que zero
    E   PIS ou COFINS efetivamente pago
```

**O segundo filtro é o que não se adivinha.** Numa devolução de 21 itens do
arquivo de referência, vinte são substituição tributária — CST de ICMS 060, sem
ICMS próprio — e só um tem ICMS destacado. Sem o filtro, os vinte entrariam com
diferença zero e o relatório encheria de linha sem conteúdo. Com ele, entra o
único item que tem o que excluir.

**O terceiro é o que a fórmula denuncia sozinha.** Item com base zerada — CST
06, alíquota zero, ou 73, suspensão — não pagou contribuição nenhuma, e subtrair
o ICMS de uma base zero dá base **negativa**: numa competência do gabarito eram
964 linhas assim, todas com total a recuperar zero e uma base STF de sinal
trocado. Nada a excluir de quem nada pagou.

**O quarto é o que restituição quer dizer.** Item de CST 06 — alíquota zero —
tem base cheia e contribuição nenhuma: a exclusão do ICMS o levaria a uma base
menor sobre a qual também não se pagou nada, e o total a recuperar sai zero. Em
todo o gabarito não há uma linha com PIS zero, COFINS zero ou alíquota zero;
sem este filtro entravam 9.123, todas valendo nada. Pede-se de volta o que se
pagou.

O primeiro filtro sai das tabelas que já existem: `tab_cfop_natureza_operacao`
diz o que é venda, e a natureza 12 de `tab_cfop_natureza_credito` diz o que é
devolução de venda. Não fez falta tabela nova.

## As duas bases, e por que são duas

* **Recalculada** — `item − desconto + rateio − ICMS`. É o que a base *deveria*
  ser, reconstruída dos componentes do próprio item;
* **STF** — a exclusão que se pede. Vale `base − ICMS`, **exceto quando a base
  já exclui o ICMS**: aí vale **zero**.

**A guarda do zero é a regra mais importante daqui.** Há cliente que já toma a
exclusão na própria escrituração — a base do C170 já vem sem o ICMS. São 1.668
linhas no gabarito. Um motor que apenas subtraísse o ICMS excluiria **duas
vezes** e produziria crédito sobre operação já corrigida: dinheiro que o cliente
pediria e não teria direito. Quando a base já está limpa, não há o que recuperar,
e as diferenças de base, PIS e COFINS saem todas em zero.

## O que se lê e o que se calcula

`Vlr PIS`, `Vlr Cofins`, a base e o ICMS **vêm do arquivo**, não da conta. Em
120 das 138.358 linhas o valor que o cliente declarou difere um centavo de
`base × alíquota`, e o gabarito respeita o declarado — é o que ele pagou, e é
sobre o que ele pagou que se pede de volta. Só as colunas derivadas são
calculadas.

## O arredondamento é por linha, e isso é uma escolha

A tese do PIS/COFINS na própria base agrega antes de arredondar, de propósito:
arredondar linha a linha infla o total em meio por cento numa base de milhões
de itens (`exclusoes/piscofins_na_propria_base.py`). Aqui **não** se agrega: o
903 é o detalhe que acompanha o pedido, cada linha tem de fechar sozinha, e é
assim que o gabarito faz. Quem quiser o total sem a inflação soma as bases e
aplica a alíquota uma vez — não soma esta coluna.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.infraestrutura.sped.tabelas import (
    tab_cfop_natureza_credito,
    tab_cfop_natureza_operacao,
    tab_selic,
)
from cat.log import obter_log

log = obter_log(__name__)

# como o MA classifica a operação na coluna "CFOP Faturamento"
FATURAMENTO = "Faturamento"
DEVOLUCAO_DE_FATURAMENTO = "Devolução Faturamento"

# a natureza 12 da 4.3.7: devolução de vendas
_DEVOLUCAO_DE_VENDA = "12"

_DE_INTERESSE = {b"0000", b"C010", b"C100", b"C170"}

ZERO = Decimal(0)
CEM = Decimal(100)
DOIS = Decimal("0.01")


def _numero(bruto: str) -> Decimal:
    """O número do SPED, em Decimal. Vazio é zero."""
    texto = (bruto or "").strip()
    if not texto:
        return ZERO
    try:
        return Decimal(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except ArithmeticError:
        return ZERO


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(DOIS, rounding=ROUND_HALF_UP)


def _dia(bruto: str) -> str:
    b = (bruto or "").strip()
    if len(b) != 8 or not b.isdigit():
        return b
    try:
        return date(int(b[4:]), int(b[2:4]), int(b[:2])).strftime("%d/%m/%Y")
    except ValueError:
        return b


def classificacao_do_cfop(cfop: str) -> str:
    """"Faturamento", "Devolução Faturamento", ou vazio para o que não é nem um.

    Vazio significa fora do relatório: o Tema 69 é sobre a **receita**, e o que
    não é venda nem devolução de venda não compõe receita.
    """
    if tab_cfop_natureza_operacao.natureza(cfop, "") == tab_cfop_natureza_operacao.VENDA:
        return FATURAMENTO
    if tab_cfop_natureza_credito.codigo(cfop) == _DEVOLUCAO_DE_VENDA:
        return DEVOLUCAO_DE_FATURAMENTO
    return ""


@dataclass
class LinhaDaExclusao:
    """Uma linha do 903, na ordem de colunas do MA."""

    cnpj: str = ""
    periodo: str = ""
    codigo_do_participante: str = ""
    situacao: str = ""
    numero_do_documento: str = ""
    chave: str = ""
    data_do_documento: str = ""
    data_de_entrada_ou_saida: str = ""
    numero_do_item: str = ""
    codigo_do_item: str = ""
    cfop: str = ""
    cfop_faturamento: str = ""
    cst: str = ""
    valor_do_item: str = ""
    desconto_do_item: str = ""
    base_do_icms: str = ""
    aliquota_do_icms: str = ""
    icms: str = ""
    icms_com_pagamento: str = ""
    rateio: str = ""
    ipi: str = ""
    base: str = ""
    base_recalculada: str = ""
    diferenca_da_base_recalculada: str = ""
    base_stf: str = ""
    diferenca_da_base: str = ""
    selic_acumulada: str = ""
    aliquota_do_pis: str = ""
    pis: str = ""
    pis_stf: str = ""
    diferenca_do_pis: str = ""
    selic_sobre_o_pis: str = ""
    total_do_pis_a_recuperar: str = ""
    aliquota_da_cofins: str = ""
    cofins: str = ""
    cofins_stf: str = ""
    diferenca_da_cofins: str = ""
    selic_sobre_a_cofins: str = ""
    total_da_cofins_a_recuperar: str = ""
    total_a_recuperar_atualizado: str = ""

    def como_dicionario(self) -> dict[str, str]:
        return asdict(self)


def colunas_da_exclusao() -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet vazio."""
    return list(LinhaDaExclusao().como_dicionario())


def _nomeados(prefixo: str, valores: list[str]) -> dict[str, str]:
    nomes = nomes_dos_campos(prefixo)
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


def exclusoes_do_icms(caminho: str, codificacao: str, ate: str,
                      acumulada: dict[str, Decimal] | None = None,
                      mensal: dict[str, Decimal] | None = None,
                      ) -> Iterator[LinhaDaExclusao]:
    """As exclusões do ICMS da base, item a item, corrigidas até `ate`.

    `ate` é o mês da restituição, em "aaaa-mm": é até ele que a Selic acumula.
    Não tem padrão de propósito — quem chama sabe de quando é o pedido, e um
    padrão silencioso faria o número mudar de sentido sem ninguém notar.

    `mensal` é a série da Selic, mês a mês. Em produção vem do banco
    (`infraestrutura/selic`), que a mantém atualizada pela API do Banco Central
    e nunca a esquece. Sem ela, a semente de `tab_selic` — que serve a teste e
    a script.

    `acumulada` é outra coisa, e mais forte: um mapa de "aaaa-mm" para a
    acumulada **já pronta**, que dispensa somar. Existe para a conferência
    contra gabarito — é assim que se confere **o cálculo** sem depender da
    **série**. Em produção fica vazio.
    """
    contexto = _Contexto(ate, acumulada, mensal)
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(registro,
                                    campos(linha.decode(codificacao, errors="replace")))
        # o último documento não vê outro para fechá-lo
        yield from contexto.fechar_documento()

    log.info("exclusão do ICMS da base gerada", extra={
        "arquivo": os.path.basename(caminho), "linhas": contexto.saíram,
        "itens_lidos": contexto.itens, "competencia": contexto.competencia,
        "selic_ate": ate,
    })


class _Contexto:
    """O estado da passada.

    **O documento é lido inteiro antes de emitir.** O rateio do frete, do seguro
    e das outras despesas é proporcional ao valor do item dentro da nota, e não
    se sabe a proporção antes de conhecer todos os itens. É a única razão de
    haver buffer aqui — e ele guarda uma nota por vez, não o arquivo.
    """

    def __init__(self, ate: str, acumulada: dict[str, Decimal] | None = None,
                 mensal: dict[str, Decimal] | None = None) -> None:
        self.ate = ate
        self.acumulada = acumulada or {}
        self.mensal = mensal
        self.competencia = ""      # "aaaa-mm", para a Selic
        self.periodo = ""          # "dd/mm/aaaa", como o relatório escreve
        self.selic = ZERO
        self.cnpj = ""
        self.c100: list[str] = []
        self.itens_do_documento: list[list[str]] = []
        self.saíram = 0
        self.itens = 0

    def ver(self, registro: bytes, valores: list[str]) -> Iterator[LinhaDaExclusao]:
        if registro == b"0000":
            try:
                cabecalho = ler_cabecalho("|" + "|".join(valores) + "|")
            except ArquivoNaoReconhecido as erro:
                log.warning("registro 0000 não reconhecido", extra={"motivo": str(erro)})
                return
            inicio = cabecalho.inicio.replace(day=1)
            self.periodo = inicio.strftime("%d/%m/%Y")
            self.competencia = inicio.strftime("%Y-%m")
            self.selic = (self.acumulada[self.competencia]
                          if self.competencia in self.acumulada
                          else tab_selic.acumulada(self.competencia, self.ate,
                                                   self.mensal))
        elif registro == b"C010":
            # a última nota do estabelecimento anterior ainda está no buffer, e o
            # CNPJ dela é o de quem a emitiu — não o de quem abre o bloco novo.
            # Fechar antes de trocar; medido em 61 linhas que o MA atribuía à
            # matriz e nós à filial seguinte
            yield from self.fechar_documento()
            self.cnpj = valores[1].strip() if len(valores) > 1 else ""
        elif registro == b"C100":
            yield from self.fechar_documento()
            self.c100 = valores
        elif registro == b"C170":
            self.itens_do_documento.append(valores)

    def fechar_documento(self) -> Iterator[LinhaDaExclusao]:
        """Emite os itens da nota que entram, já com o rateio repartido."""
        itens, self.itens_do_documento = self.itens_do_documento, []
        c100, self.c100 = self.c100, []
        if not c100 or not itens:
            return

        nota = _nomeados("C100", c100)
        # o que se reparte, e sobre o que se reparte. O denominador é a soma de
        # **todos** os itens, e não só a dos que entram no relatório: o frete da
        # nota foi pago pela nota inteira
        a_ratear = (_numero(nota["C100_VL_FRT"]) + _numero(nota["C100_VL_SEG"])
                    + _numero(nota["C100_VL_OUT_DA"]))
        valores_dos_itens = [_numero(_nomeados("C170", i)["C170_VL_ITEM"]) for i in itens]
        total_dos_itens = sum(valores_dos_itens, ZERO)

        for bruto, valor_do_item in zip(itens, valores_dos_itens):
            self.itens += 1
            item = _nomeados("C170", bruto)
            classificacao = classificacao_do_cfop(item["C170_CFOP"])
            icms = _numero(item["C170_VL_ICMS"])
            base = _numero(item["C170_VL_BC_PIS"])
            contribuiu = (_numero(item["C170_VL_PIS"]) > ZERO
                          or _numero(item["C170_VL_COFINS"]) > ZERO)
            # os quatro filtros. Ver "Quem entra", no topo
            if not classificacao or icms <= ZERO or base <= ZERO or not contribuiu:
                continue
            rateio = (_centavos(a_ratear * valor_do_item / total_dos_itens)
                      if a_ratear and total_dos_itens else ZERO)
            yield self._montar(nota, item, classificacao, valor_do_item, icms, rateio)

    def _montar(self, nota: dict[str, str], item: dict[str, str], classificacao: str,
                valor_do_item: Decimal, icms: Decimal, rateio: Decimal) -> LinhaDaExclusao:
        desconto = _numero(item["C170_VL_DESC"])
        base = _numero(item["C170_VL_BC_PIS"])

        # o que a base deveria ser, reconstruída do próprio item
        recalculada = valor_do_item - desconto + rateio - icms
        # a exclusão que se pede — zero quando a base já a tomou. Ver o topo
        ja_excluiu = base == recalculada
        stf = ZERO if ja_excluiu else base - icms

        aliquota_do_pis = _numero(item["C170_ALIQ_PIS_PERC"])
        aliquota_da_cofins = _numero(item["C170_ALIQ_COFINS_PERC"])
        # o que o cliente declarou: é sobre isto que se pede de volta
        pis = _numero(item["C170_VL_PIS"])
        cofins = _numero(item["C170_VL_COFINS"])
        pis_stf = _centavos(stf * aliquota_do_pis / CEM)
        cofins_stf = _centavos(stf * aliquota_da_cofins / CEM)

        sem_credito = stf == ZERO
        diferenca_da_base = ZERO if sem_credito else base - stf
        diferenca_do_pis = ZERO if sem_credito else pis - pis_stf
        diferenca_da_cofins = ZERO if sem_credito else cofins - cofins_stf
        selic_sobre_o_pis = _centavos(diferenca_do_pis * self.selic / CEM)
        selic_sobre_a_cofins = _centavos(diferenca_da_cofins * self.selic / CEM)
        total_do_pis = diferenca_do_pis + selic_sobre_o_pis
        total_da_cofins = diferenca_da_cofins + selic_sobre_a_cofins

        self.saíram += 1
        t = str
        return LinhaDaExclusao(
            cnpj=self.cnpj, periodo=self.periodo,
            codigo_do_participante=nota["C100_COD_PART"], situacao=nota["C100_COD_SIT"],
            numero_do_documento=nota["C100_NUM_DOC"], chave=nota["C100_CHV_NFE"],
            data_do_documento=_dia(nota["C100_DT_DOC"]),
            data_de_entrada_ou_saida=_dia(nota["C100_DT_E_S"]),
            numero_do_item=item["C170_NUM_ITEM"], codigo_do_item=item["C170_COD_ITEM"],
            cfop=item["C170_CFOP"], cfop_faturamento=classificacao, cst=item["C170_CST_PIS"],
            valor_do_item=t(valor_do_item), desconto_do_item=t(desconto),
            base_do_icms=t(_numero(item["C170_VL_BC_ICMS"])),
            aliquota_do_icms=t(_numero(item["C170_ALIQ_ICMS"])),
            icms=t(icms),
            # o ICMS sobre o qual houve pagamento de PIS/COFINS. No gabarito é
            # sempre o ICMS inteiro — a coluna existe para o caso em que parte
            # da operação não foi tributada, que este cliente não tem
            icms_com_pagamento=t(icms),
            rateio=t(rateio), ipi=t(_numero(item["C170_VL_IPI"])),
            base=t(base), base_recalculada=t(recalculada),
            diferenca_da_base_recalculada=t(base - recalculada),
            base_stf=t(stf), diferenca_da_base=t(diferenca_da_base),
            selic_acumulada=t(self.selic),
            aliquota_do_pis=t(aliquota_do_pis), pis=t(pis), pis_stf=t(pis_stf),
            diferenca_do_pis=t(diferenca_do_pis), selic_sobre_o_pis=t(selic_sobre_o_pis),
            total_do_pis_a_recuperar=t(total_do_pis),
            aliquota_da_cofins=t(aliquota_da_cofins), cofins=t(cofins),
            cofins_stf=t(cofins_stf), diferenca_da_cofins=t(diferenca_da_cofins),
            selic_sobre_a_cofins=t(selic_sobre_a_cofins),
            total_da_cofins_a_recuperar=t(total_da_cofins),
            total_a_recuperar_atualizado=t(total_do_pis + total_da_cofins))
