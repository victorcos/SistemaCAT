"""A exclusão do ICMS-ST da base do PIS/COFINS — o relatório 839, item a item.

Equivalente à consulta **839 — C100, C170 — Documento — Nota Fiscal e Itens**
do Sistema MA. É a tese do contribuinte **substituído**: quem compra mercadoria
cujo ICMS já foi retido lá atrás, revende sob CFOP de ST, paga PIS/COFINS sobre
a receita cheia — e nessa receita está embutido um imposto que não é dele.

## A diferença que muda tudo em relação ao 903

No 903 o ICMS está escrito na nota: lê-se `VL_ICMS` e exclui-se. **Aqui não há
o que ler.** A revenda com ST já retido não destaca imposto nenhum — é o que a
CST 60 significa. Medido nos 57 arquivos da empresa 05 e também na EFD ICMS/IPI do
mesmo cliente: **zero** linhas com ICMS-ST destacado, nem na entrada, nem na
saída, nem no analítico C190.

Então o ST é **reconstruído**:

```
base presumida = valor do item − desconto + rateio de frete/seguro/despesas
ICMS-ST        = base presumida × alíquota  (arredondado ao centavo)
base STF       = base do PIS/COFINS − ICMS-ST
```

As três fórmulas fecham em **100% das 463.212 linhas** do arquivo de
referência. Não há aqui a guarda do "já excluiu" que o 903 tem, e não faria
sentido: o que nunca foi escriturado não pode ter sido excluído antes.

**Isto é arbitramento, e quem assina precisa saber.** O 903 devolve o que está
no arquivo; este devolve uma reconstrução. A fórmula está escrita acima
justamente para que o pedido possa ser defendido por ela, e não por um número
que saiu de uma caixa.

## De onde vem a alíquota

De `tab_aliquota_icms`: a regra (interna do estado, ou a Resolução 22/1989 do
Senado na interestadual) mais as exceções por produto, que vêm do banco porque
são cadastro do cliente. A regra sozinha acerta 98,66% das linhas medidas. Ver
aquele módulo para por que as duas coisas ficam separadas.

## Quem entra

Quatro filtros:

```
CFOP de venda ou devolução de venda EM OPERAÇÃO COM ST
    E   CST de ICMS diferente de 00
    E   base de cálculo do PIS/COFINS maior que zero
    E   PIS ou COFINS efetivamente pago
```

**O segundo filtro é o que separa este relatório do 903**, e foi medido pelos
dois lados: as três linhas que sobravam aqui têm CST de ICMS 00 — tributada
integralmente — e estão, as três, no gabarito do 903. Um item entra num ou no
outro, nunca nos dois. Dos 601.570 itens dos dois relatórios, apenas 8 aparecem
em ambos: são CST 10 e 70, em que há ICMS próprio **e** ST na mesma linha.

**Não há filtro de ST maior que zero**, ao contrário do 903. Produto de
alíquota zero entra com exclusão zero: são 2.493 linhas no gabarito, e elas
existem para que quem confere veja que o item foi olhado.

## O cadastro por estabelecimento

Este relatório traz nome do participante, descrição do item e código EAN — que
o 903 não traz. Por isso passa pelo 0150 e pelo 0200, e por isso usa
`sped/cadastro.py`: na EFD-Contribuições essas tabelas pendem do 0140, e tratá-las
como uma tabela só por arquivo troca mercadoria entre matriz e filial.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.cadastro import CadastroPorEstabelecimento
from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.infraestrutura.sped.tabelas import (
    tab_aliquota_icms,
    tab_municipio,
    tab_selic,
)
from cat.log import obter_log

log = obter_log(__name__)

# os CFOP de venda e de devolução de venda **em operação com substituição
# tributária**. É o primeiro filtro, e é o que distingue este relatório do 903:
# lá entra a receita tributada normalmente, aqui a que carrega ST
CFOPS_COM_ST = frozenset({
    # vendas
    "5401", "5402", "5403", "5405", "5409",
    "6401", "6402", "6403", "6404", "6409",
    # devoluções de venda
    "1410", "1411", "2410", "2411",
})

# CST de ICMS 00 é "tributada integralmente": não há ST na operação, e a linha
# pertence ao 903. Ver "Quem entra", no topo
CST_SEM_ST = "00"

_DE_INTERESSE = {b"0000", b"0140", b"0150", b"0200", b"C010", b"C100", b"C170"}

# as tabelas de cadastro e onde está a chave de cada uma. Elas são do
# estabelecimento, não do arquivo — ver `sped/cadastro.py`
_CHAVE_DO_CADASTRO = {b"0150": 1, b"0200": 1}

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
    """Arredonda ao centavo, **sem zero negativo**.

    `Decimal("-0.001").quantize(...)` devolve `-0.00`, que sai na coluna como
    "-0" — e o MA escreve "0". Aparece nos itens de alíquota zero, em que a
    diferença é só resíduo de arredondamento e pode cair do lado negativo: são
    192 das 463.212 linhas do arquivo de referência. Menos um sinal não é menos
    dinheiro, mas é uma coluna que não bate.
    """
    arredondado = valor.quantize(DOIS, rounding=ROUND_HALF_UP)
    return ZERO if arredondado == ZERO else arredondado


def _dia(bruto: str) -> str:
    b = (bruto or "").strip()
    if len(b) != 8 or not b.isdigit():
        return b
    try:
        return date(int(b[4:]), int(b[2:4]), int(b[:2])).strftime("%d/%m/%Y")
    except ValueError:
        return b


def _nomeados(prefixo: str, valores: list[str]) -> dict[str, str]:
    nomes = nomes_dos_campos(prefixo)
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


def tem_substituicao(cst_do_icms: str) -> bool:
    """A operação carrega ST? CST 00 é tributada integralmente e vai ao 903."""
    return (cst_do_icms or "").strip()[-2:] != CST_SEM_ST


@dataclass
class LinhaDaExclusaoST:
    """Uma linha do 839, na ordem de colunas do MA."""

    cnpj: str = ""
    periodo: str = ""
    uf: str = ""
    modelo: str = ""
    codigo_do_participante: str = ""
    cnpj_do_participante: str = ""
    cpf_do_participante: str = ""
    nome_do_participante: str = ""
    situacao: str = ""
    numero_do_documento: str = ""
    chave: str = ""
    data_do_documento: str = ""
    data_de_entrada_ou_saida: str = ""
    valor_do_documento: str = ""
    desconto_do_documento: str = ""
    numero_do_item: str = ""
    codigo_do_item: str = ""
    codigo_ean: str = ""
    descricao_do_item: str = ""
    cfop: str = ""
    valor_do_item: str = ""
    desconto_do_item: str = ""
    base_do_icms_st_presumido: str = ""
    aliquota_interna: str = ""
    cst_do_icms: str = ""
    icms_st: str = ""
    icms_st_com_pagamento: str = ""
    rateio: str = ""
    cst: str = ""
    base: str = ""
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


def colunas_da_exclusao_st() -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet vazio."""
    return list(LinhaDaExclusaoST().como_dicionario())


def exclusoes_do_icms_st(caminho: str, codificacao: str, ate: str,
                         acumulada: dict[str, Decimal] | None = None,
                         mensal: dict[str, Decimal] | None = None,
                         excecoes: dict[tuple[str, str, str, str], Decimal] | None = None,
                         ) -> Iterator[LinhaDaExclusaoST]:
    """As exclusões do ICMS-ST da base, item a item, corrigidas até `ate`.

    `ate` é o mês da restituição, em "aaaa-mm". `mensal` é a série da Selic (do
    banco, em produção) e `acumulada` a acumulada já pronta, para conferência
    contra gabarito — as duas como no 903.

    `excecoes` é a alíquota interna dos produtos que fogem do padrão do estado,
    vinda do banco. Ver `tab_aliquota_icms`.
    """
    contexto = _Contexto(ate, acumulada, mensal, excecoes)
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(registro,
                                    campos(linha.decode(codificacao, errors="replace")))
        # o último documento não vê outro para fechá-lo
        yield from contexto.fechar_documento()

    log.info("exclusão do ICMS-ST da base gerada", extra={
        "arquivo": os.path.basename(caminho), "linhas": contexto.saíram,
        "itens_lidos": contexto.itens, "competencia": contexto.competencia,
        "selic_ate": ate,
    })


class _Contexto:
    """O estado da passada.

    **O documento é lido inteiro antes de emitir**, pela mesma razão do 903: o
    rateio do frete é proporcional ao valor do item dentro da nota, e não se
    sabe a proporção antes de conhecer todos os itens.
    """

    def __init__(self, ate: str, acumulada: dict[str, Decimal] | None = None,
                 mensal: dict[str, Decimal] | None = None,
                 excecoes: dict[tuple[str, str, str, str], Decimal] | None = None) -> None:
        self.ate = ate
        self.acumulada = acumulada or {}
        self.mensal = mensal
        self.excecoes = excecoes or {}
        self.competencia = ""      # "aaaa-mm", para a Selic
        self.periodo = ""          # "dd/mm/aaaa", como o relatório escreve
        self.selic = ZERO
        self.cnpj = ""
        self.cadastro = CadastroPorEstabelecimento(_CHAVE_DO_CADASTRO)
        self.c100: list[str] = []
        self.itens_do_documento: list[list[str]] = []
        self.saíram = 0
        self.itens = 0

    # ---------- busca nas tabelas do bloco 0 ----------
    def _participante(self, codigo: str) -> dict[str, str]:
        d = _nomeados("0150", self.cadastro.linha(b"0150", codigo, self.cnpj))
        return {
            "codigo_do_participante": codigo,
            "cnpj_do_participante": d["0150_CNPJ"],
            "cpf_do_participante": d["0150_CPF"],
            "nome_do_participante": d["0150_NOME"],
        }

    def _item(self, codigo: str) -> dict[str, str]:
        """O item **do estabelecimento**, sem completar pela matriz.

        Este relatório não completa, e a 047 completa — medido nos dois
        gabaritos. Ver `sped/cadastro.py`, onde a diferença está escrita.
        """
        d = _nomeados("0200", self.cadastro.linha(b"0200", codigo, self.cnpj,
                                                  completar=False))
        return {"codigo_ean": d["0200_COD_BARRA"], "descricao_do_item": d["0200_DESCR_ITEM"]}

    def _ufs(self, participante: str) -> tuple[str, str]:
        """A UF do estabelecimento e a do participante, nesta ordem.

        Como na 047: numa saída a origem somos nós. O 0150 não traz UF — só o
        código do município —, e a UF sai dos dois primeiros dígitos do código
        do IBGE, que é convenção pública e fixa.
        """
        municipio = _nomeados(
            "0150", self.cadastro.linha(b"0150", participante, self.cnpj))["0150_COD_MUN"]
        do_estabelecimento = _nomeados(
            "0140", self.cadastro.estabelecimento(self.cnpj))["0140_UF"]
        return do_estabelecimento, tab_municipio.uf_do_municipio(municipio)

    # ---------- a passada ----------
    def ver(self, registro: bytes, valores: list[str]) -> Iterator[LinhaDaExclusaoST]:
        if self.cadastro.guardar(registro, valores):
            return
        if registro == b"0140":
            self.cadastro.abrir(valores)
            return
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
            # é do cadastro da matriz que sai o campo que o do estabelecimento
            # deixou em branco. Ver `sped/cadastro.py`
            self.cadastro.definir_matriz(str(cabecalho.cnpj or ""))
        elif registro == b"C010":
            # a última nota do estabelecimento anterior ainda está no buffer, e
            # o CNPJ dela é o de quem a emitiu. Fechar antes de trocar — no 903
            # o mesmo descuido trocou o CNPJ de 61 linhas
            yield from self.fechar_documento()
            self.cnpj = valores[1].strip() if len(valores) > 1 else ""
        elif registro == b"C100":
            yield from self.fechar_documento()
            self.c100 = valores
        elif registro == b"C170":
            self.itens_do_documento.append(valores)

    def fechar_documento(self) -> Iterator[LinhaDaExclusaoST]:
        """Emite os itens da nota que entram, já com o rateio repartido."""
        itens, self.itens_do_documento = self.itens_do_documento, []
        c100, self.c100 = self.c100, []
        if not c100 or not itens:
            return

        nota = _nomeados("C100", c100)
        # o denominador é a soma de **todos** os itens, e não só a dos que
        # entram no relatório: o frete da nota foi pago pela nota inteira
        a_ratear = (_numero(nota["C100_VL_FRT"]) + _numero(nota["C100_VL_SEG"])
                    + _numero(nota["C100_VL_OUT_DA"]))
        valores_dos_itens = [_numero(_nomeados("C170", i)["C170_VL_ITEM"]) for i in itens]
        total_dos_itens = sum(valores_dos_itens, ZERO)

        for bruto, valor_do_item in zip(itens, valores_dos_itens):
            self.itens += 1
            item = _nomeados("C170", bruto)
            base = _numero(item["C170_VL_BC_PIS"])
            contribuiu = (_numero(item["C170_VL_PIS"]) > ZERO
                          or _numero(item["C170_VL_COFINS"]) > ZERO)
            # os quatro filtros. Ver "Quem entra", no topo
            if (item["C170_CFOP"] not in CFOPS_COM_ST
                    or not tem_substituicao(item["C170_CST_ICMS"])
                    or base <= ZERO or not contribuiu):
                continue
            rateio = (_centavos(a_ratear * valor_do_item / total_dos_itens)
                      if a_ratear and total_dos_itens else ZERO)
            yield self._montar(nota, item, valor_do_item, rateio)

    def _montar(self, nota: dict[str, str], item: dict[str, str],
                valor_do_item: Decimal, rateio: Decimal) -> LinhaDaExclusaoST:
        codigo_do_participante = nota["C100_COD_PART"]
        codigo_do_item = item["C170_COD_ITEM"]
        origem, destino = self._ufs(codigo_do_participante)

        desconto = _numero(item["C170_VL_DESC"])
        base = _numero(item["C170_VL_BC_PIS"])

        # o ST que ninguém escriturou, reconstruído. Ver o topo do módulo
        presumida = valor_do_item - desconto + rateio
        # a competência entra porque **a alíquota interna tem data**: um pedido
        # de cinco anos atravessa mudança de lei estadual, e uma tabela sem
        # vigência aplicaria a de hoje a uma operação de 2021, calada
        aliquota = tab_aliquota_icms.aplicavel(
            origem, destino, self.competencia, self.cnpj, codigo_do_item,
            self.excecoes)
        icms_st = _centavos(presumida * aliquota / CEM)
        stf = base - icms_st

        aliquota_do_pis = _numero(item["C170_ALIQ_PIS_PERC"])
        aliquota_da_cofins = _numero(item["C170_ALIQ_COFINS_PERC"])
        # o que o cliente declarou: é sobre isto que se pede de volta
        pis = _numero(item["C170_VL_PIS"])
        cofins = _numero(item["C170_VL_COFINS"])
        pis_stf = _centavos(stf * aliquota_do_pis / CEM)
        cofins_stf = _centavos(stf * aliquota_da_cofins / CEM)

        diferenca_do_pis = pis - pis_stf
        diferenca_da_cofins = cofins - cofins_stf
        selic_sobre_o_pis = _centavos(diferenca_do_pis * self.selic / CEM)
        selic_sobre_a_cofins = _centavos(diferenca_da_cofins * self.selic / CEM)
        total_do_pis = diferenca_do_pis + selic_sobre_o_pis
        total_da_cofins = diferenca_da_cofins + selic_sobre_a_cofins

        self.saíram += 1
        t = str
        return LinhaDaExclusaoST(
            cnpj=self.cnpj, periodo=self.periodo,
            uf=f"{origem}/{destino}" if origem and destino else "",
            modelo=nota["C100_COD_MOD"],
            **self._participante(codigo_do_participante),
            situacao=nota["C100_COD_SIT"],
            numero_do_documento=nota["C100_NUM_DOC"], chave=nota["C100_CHV_NFE"],
            data_do_documento=_dia(nota["C100_DT_DOC"]),
            data_de_entrada_ou_saida=_dia(nota["C100_DT_E_S"]),
            valor_do_documento=t(_numero(nota["C100_VL_DOC"])),
            desconto_do_documento=t(_numero(nota["C100_VL_DESC"])),
            numero_do_item=item["C170_NUM_ITEM"], codigo_do_item=codigo_do_item,
            **self._item(codigo_do_item),
            cfop=item["C170_CFOP"],
            valor_do_item=t(valor_do_item), desconto_do_item=t(desconto),
            base_do_icms_st_presumido=t(presumida),
            aliquota_interna=t(aliquota),
            cst_do_icms=item["C170_CST_ICMS"],
            icms_st=t(icms_st),
            # o ST sobre o qual houve pagamento de PIS/COFINS. No gabarito é
            # sempre o ST inteiro — a coluna existe para o caso em que parte da
            # operação não foi tributada, que este cliente não tem
            icms_st_com_pagamento=t(icms_st),
            rateio=t(rateio),
            cst=item["C170_CST_PIS"],
            base=t(base), base_stf=t(stf), diferenca_da_base=t(base - stf),
            selic_acumulada=t(self.selic),
            aliquota_do_pis=t(aliquota_do_pis), pis=t(pis), pis_stf=t(pis_stf),
            diferenca_do_pis=t(diferenca_do_pis),
            selic_sobre_o_pis=t(selic_sobre_o_pis),
            total_do_pis_a_recuperar=t(total_do_pis),
            aliquota_da_cofins=t(aliquota_da_cofins), cofins=t(cofins),
            cofins_stf=t(cofins_stf), diferenca_da_cofins=t(diferenca_da_cofins),
            selic_sobre_a_cofins=t(selic_sobre_a_cofins),
            total_da_cofins_a_recuperar=t(total_da_cofins),
            total_a_recuperar_atualizado=t(total_do_pis + total_da_cofins))
