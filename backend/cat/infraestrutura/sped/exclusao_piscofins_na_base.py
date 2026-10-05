"""As próprias contribuições fora da base, **item a item** — o relatório 680.

Equivalente à consulta **680 — Metodologia 01 — Todos Registros — Por Documento
e Itens** do Sistema MA. A tese é a mesma que `exclusoes/piscofins_na_propria_base.py`
calcula: o preço de venda embute o PIS e a COFINS, receita não é imposto, e a
base de **cada uma** perde **as duas**.

## Por que existem os dois, e por que os números não são iguais

São duas frentes da mesma tese, e cada uma responde a uma pergunta diferente:

* **o consolidado** (`exclusoes/piscofins_na_propria_base.py`) soma por grupo —
  estabelecimento, competência, registro, CST e CFOP — e arredonda **uma vez
  por grupo**, com a alíquota efetiva daquele grupo. É o número que se pede.
* **este**, item a item, nas 35 colunas do MA. É o detalhe que acompanha o
  pedido e permite conferir linha a linha contra o relatório do escritório
  anterior.

**A soma do detalhe não bate com o total do consolidado, e isso é de
propósito.** Arredondar linha a linha numa base de milhões de itens move o
total — na empresa 05 são 0,06%, cerca de R$ 1,6 mil em R$ 2,7 milhões. A decisão
de 24/09/2026 escolheu o arredondamento por grupo para o número que se pede; o
detalhe reproduz o do MA para que a conferência seja possível. Quem olhar os
dois lado a lado tem de encontrar essa diferença escrita, e não descobri-la.

## A conta, medida nas 3.568.362 linhas do arquivo de referência

```
base STF   = base − (PIS + COFINS)          ← as duas, em cada uma
PIS-STF    = arredonda(base STF × alíquota)
diferença  = PIS − PIS-STF
SELIC      = arredonda(diferença × acumulada)
total      = diferença + SELIC, nas duas contribuições
```

As sete fórmulas fecham em 100%. **A base, a alíquota e o valor pago vêm do
arquivo**, nunca da conta: é sobre o que o cliente declarou que se pede de
volta, como no 903.

**O `Vlr ICMS` e o `Vlr Rateio` são informativos.** Vêm preenchidos em 3,1
milhões de linhas e **não entram em conta nenhuma** — medido: a base do
relatório não é `item − desconto + rateio − ICMS`, é a base escriturada. Eles
estão ali porque o 680 é o detalhe geral da receita, e saem daqui pelo mesmo
motivo.

## Quem entra

```
receita        CFOP de venda ou de devolução de venda, quando há CFOP
               IND_OPER de receita, no registro que não tem CFOP
    E   base de cálculo maior que zero
    E   tributada: contribuição paga **ou** alíquota positiva
```

**O registro sem CFOP entra pelo `IND_OPER`, não por suposição.** O F100 e o
A170 não têm CFOP no leiaute, e o MA escreve `"S"` na coluna — o sentido, não um
código. Tratar todo registro sem CFOP como faturamento trazia **aquisição** para
dentro da tese: F100 de compra e serviço contratado, com CST 50, que é CST de
crédito e só existe na entrada. Ver `GERACAO_DE_RECEITA`. Perguntar o CFOP a
esses registros é o erro oposto, e maior — derruba R$ 10,28 milhões de base (ver
`tab_cfop_receita` e a decisão de 01/10/2026).

**Tributada basta; paga não é exigido.** Uma linha de R$ 0,06 com CST 01 e
alíquota cheia recolhe R$ 0,00 nas duas por arredondamento, e o MA a traz.

**A devolução entra com o CST que tiver.** Ela se escritura com CST de crédito —
50, 73, 98 e 99 nas 8.822 linhas do arquivo de referência —, porque é estorno de
uma venda tributada, não uma aquisição.

## Os quatro ramos

`C100/C170` é o item da nota — e o único que traz ICMS, desconto e rateio;
`C100/C175` o analítico da NFC-e, que **não tem item** (o MA deixa número,
código e descrição em branco) e traz só o desconto; `A100/A170` a nota de serviço
prestado; `F100` os demais documentos, **somados por dia** porque não têm
documento, modelo nem item que os distinga (ver `fechar_f100`).

Escrever a coluna que o ramo não tem seria inventar dado, e a ausência é do ramo
e não do campo: ver `_do_ramo`.
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
from cat.infraestrutura.sped.tabelas import tab_selic
from cat.infraestrutura.sped.tabelas.tab_cfop_receita import (
    FATURAMENTO,
    classificacao_do_cfop,
)
from cat.log import obter_log

log = obter_log(__name__)

# como o MA nomeia cada ramo na coluna "Registro Lançamento"
RAMO_C170 = "C100/C170"
RAMO_C175 = "C100/C175"
RAMO_A170 = "A100/A170"
RAMO_F100 = "F100"

# o que o MA escreve na coluna do CFOP quando o registro não tem CFOP: o
# sentido da operação, e não um código
SAIDA = "S"

# o `IND_OPER` que é receita nos dois registros sem CFOP: 1 — geração de receita
# no F100 (0 é aquisição, 2 "outros documentos e operações"), serviço **prestado**
# no A100 (0 é serviço contratado). Sem CFOP para perguntar, é este campo que diz
# o sentido, e sem ele a aquisição entra na tese
GERACAO_DE_RECEITA = "1"

_DE_INTERESSE = {
    b"0000", b"0140", b"0200",
    b"C010", b"C100", b"C170", b"C175",
    b"A010", b"A100", b"A170",
    b"F010", b"F100",
}

# o cadastro do item, para a descrição. Pende do 0140 — ver `sped/cadastro.py`
_CHAVE_DO_CADASTRO = {b"0200": 1}

ZERO = Decimal(0)
CEM = Decimal(100)
DOIS = Decimal("0.01")


def _numero(bruto: str) -> Decimal:
    texto = (bruto or "").strip()
    if not texto:
        return ZERO
    try:
        return Decimal(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except ArithmeticError:
        return ZERO


def _centavos(valor: Decimal) -> Decimal:
    """Arredonda ao centavo, sem zero negativo. Ver `exclusao_do_icms_st`."""
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


def _do_ramo(valor: str | None) -> str:
    """O número, ou **vazio quando o ramo não tem aquela coluna**.

    A ausência é do **ramo**, não do campo — medido no arquivo de referência: o
    C170 traz ICMS, desconto e rateio nas 602.510 linhas, mesmo zerados; o C175
    traz só o desconto, nas 2.965.485; o A170 e o F100 não trazem nenhum dos
    três, nem quando o leiaute tem o campo (o A170 tem `VL_DESC`, e o MA o deixa
    em branco de todo jeito).

    Por isso `None` e `""` são coisas diferentes aqui: `None` é o ramo dizendo
    que a coluna não existe para ele. Escrever zero no lugar do vazio divergia
    em 71.837 linhas de uma competência só.
    """
    return "" if valor is None else str(_numero(valor))


def _nomeados(prefixo: str, valores: list[str]) -> dict[str, str]:
    nomes = nomes_dos_campos(prefixo)
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


@dataclass
class LinhaDaExclusaoPisCofins:
    """Uma linha do 680, na ordem de colunas do MA."""

    cnpj: str = ""
    periodo: str = ""
    registro: str = ""
    modelo: str = ""
    numero_do_documento: str = ""
    chave: str = ""
    data_do_documento: str = ""
    numero_do_item: str = ""
    codigo_do_item: str = ""
    descricao_do_item: str = ""
    valor_do_item: str = ""
    desconto: str = ""
    icms: str = ""
    rateio: str = ""
    cfop: str = ""
    cfop_faturamento: str = ""
    cst: str = ""
    selic_acumulada: str = ""
    base_do_pis: str = ""
    base_do_pis_stf: str = ""
    aliquota_do_pis: str = ""
    pis: str = ""
    pis_stf: str = ""
    diferenca_do_pis: str = ""
    selic_sobre_o_pis: str = ""
    total_do_pis_a_recuperar: str = ""
    base_da_cofins: str = ""
    base_da_cofins_stf: str = ""
    aliquota_da_cofins: str = ""
    cofins: str = ""
    cofins_stf: str = ""
    diferenca_da_cofins: str = ""
    selic_sobre_a_cofins: str = ""
    total_da_cofins_a_recuperar: str = ""
    total_a_recuperar_atualizado: str = ""

    def como_dicionario(self) -> dict[str, str]:
        return asdict(self)

    # ---- os nomes que o núcleo compartilhado usa para somar ----
    # São **propriedades, e não campos**: `asdict` as ignora, e por isso o
    # parquet continua com as 35 colunas do MA. O que elas fazem é traduzir o
    # vocabulário deste relatório para o de `analitico/exclusoes_por_item.py`,
    # que soma as quatro teses pelo mesmo nome. Renomear as colunas em vez
    # disso quebraria a comparação com o arquivo de referência, que é o único
    # juiz de que a conta está certa
    @property
    def base(self) -> str:
        return self.base_do_pis

    @property
    def base_stf(self) -> str:
        return self.base_do_pis_stf

    @property
    def diferenca_da_base(self) -> str:
        """O que saiu da base: nesta tese, as duas contribuições pagas."""
        return str(_numero(self.base_do_pis) - _numero(self.base_do_pis_stf))


def colunas_da_exclusao_piscofins() -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet vazio."""
    return list(LinhaDaExclusaoPisCofins().como_dicionario())


def exclusoes_do_piscofins(caminho: str, codificacao: str, ate: str,
                           acumulada: dict[str, Decimal] | None = None,
                           mensal: dict[str, Decimal] | None = None,
                           ) -> Iterator[LinhaDaExclusaoPisCofins]:
    """As contribuições fora da própria base, item a item, corrigidas até `ate`."""
    contexto = _Contexto(ate, acumulada, mensal)
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(registro,
                                    campos(linha.decode(codificacao, errors="replace")))
        # o último documento do arquivo não vê outro para fechá-lo, e o F100
        # inteiro só pode ser somado depois de lido
        yield from contexto.fechar_documento()
        yield from contexto.fechar_f100()

    log.info("exclusão das contribuições da base gerada, item a item", extra={
        "arquivo": os.path.basename(caminho), "linhas": contexto.saíram,
        "competencia": contexto.competencia, "selic_ate": ate,
    })


class _Contexto:
    """O estado da passada.

    **O documento é guardado só por causa de uma coluna.** O rateio do frete, do
    seguro e das outras despesas não entra em conta nenhuma desta tese — mas o MA
    o escreve na linha do C170, e reparti-lo exige conhecer todos os itens da
    nota. São 10 linhas não-zero em 3,5 milhões, e é a diferença entre reproduzir
    o relatório e quase reproduzi-lo.

    Os outros três ramos saem na hora: o C175, o A170 e o F100 não têm rateio.
    """

    def __init__(self, ate: str, acumulada: dict[str, Decimal] | None = None,
                 mensal: dict[str, Decimal] | None = None) -> None:
        self.ate = ate
        self.acumulada = acumulada or {}
        self.mensal = mensal
        self.competencia = ""
        self.periodo = ""
        self.selic = ZERO
        self.cadastro = CadastroPorEstabelecimento(_CHAVE_DO_CADASTRO)
        self.cnpj_c = self.cnpj_a = self.cnpj_f = ""
        self.c100: dict[str, str] = {}
        self.a100: dict[str, str] = {}
        # os itens do C100 aberto, à espera do rateio. Ver o topo da classe
        self.itens_do_documento: list[dict[str, str]] = []
        # o F100 somado por dia. Ver `fechar_f100`
        self.f100: dict[tuple[str, ...], list[Decimal]] = {}
        self.saíram = 0

    def _descricao(self, codigo: str, cnpj: str) -> str:
        d = _nomeados("0200", self.cadastro.linha(b"0200", codigo, cnpj, completar=False))
        return d["0200_DESCR_ITEM"]

    def ver(self, registro: bytes,
            valores: list[str]) -> Iterator[LinhaDaExclusaoPisCofins]:
        if self.cadastro.guardar(registro, valores):
            return
        if registro == b"0140":
            self.cadastro.abrir(valores)
            return

        primeiro = valores[1].strip() if len(valores) > 1 else ""
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
                          else tab_selic.acumulada(self.competencia, self.ate, self.mensal))
            self.cadastro.definir_matriz(str(cabecalho.cnpj or ""))
        elif registro == b"C010":
            yield from self.fechar_documento()
            self.cnpj_c = primeiro
        elif registro == b"A010":
            self.cnpj_a = primeiro
        elif registro == b"F010":
            self.cnpj_f = primeiro
        elif registro == b"C100":
            yield from self.fechar_documento()
            self.c100 = _nomeados("C100", valores)
        elif registro == b"A100":
            self.a100 = _nomeados("A100", valores)
        elif registro == b"C170":
            self.itens_do_documento.append(_nomeados("C170", valores))
        elif registro == b"C175":
            linha = self._do_c175(_nomeados("C175", valores))
            if linha:
                yield linha
        elif registro == b"A170":
            linha = self._do_a170(_nomeados("A170", valores))
            if linha:
                yield linha
        elif registro == b"F100":
            self._somar_f100(_nomeados("F100", valores))

    def fechar_documento(self) -> Iterator[LinhaDaExclusaoPisCofins]:
        """Emite os itens do C100 aberto, com o rateio já repartido."""
        itens, self.itens_do_documento = self.itens_do_documento, []
        if not itens:
            return

        # o que se reparte, e sobre o que se reparte. O denominador é a soma de
        # **todos** os itens, e não só a dos que entram na tese: o frete foi
        # pago pela nota inteira. Mesma conta do 903
        a_ratear = (_numero(self.c100.get("C100_VL_FRT", ""))
                    + _numero(self.c100.get("C100_VL_SEG", ""))
                    + _numero(self.c100.get("C100_VL_OUT_DA", "")))
        valores = [_numero(i["C170_VL_ITEM"]) for i in itens]
        total = sum(valores, ZERO)

        for item, valor in zip(itens, valores):
            rateio = (_centavos(a_ratear * valor / total)
                      if a_ratear and total else ZERO)
            linha = self._do_c170(item, rateio)
            if linha:
                yield linha

    # ---------- os quatro ramos ----------
    def _do_c170(self, item: dict[str, str],
                 rateio: Decimal) -> LinhaDaExclusaoPisCofins | None:
        return self._montar(
            cnpj=self.cnpj_c, ramo=RAMO_C170, cfop=item["C170_CFOP"],
            modelo=self.c100.get("C100_COD_MOD", ""),
            documento=self.c100.get("C100_NUM_DOC", ""),
            chave=self.c100.get("C100_CHV_NFE", ""),
            data=self.c100.get("C100_DT_DOC", ""),
            numero_do_item=item["C170_NUM_ITEM"], codigo=item["C170_COD_ITEM"],
            descricao=self._descricao(item["C170_COD_ITEM"], self.cnpj_c),
            valor=item["C170_VL_ITEM"], desconto=item["C170_VL_DESC"],
            icms=item["C170_VL_ICMS"], rateio=str(rateio),
            cst=item["C170_CST_PIS"],
            base_pis=item["C170_VL_BC_PIS"], aliq_pis=item["C170_ALIQ_PIS_PERC"],
            pis=item["C170_VL_PIS"],
            base_cof=item["C170_VL_BC_COFINS"], aliq_cof=item["C170_ALIQ_COFINS_PERC"],
            cofins=item["C170_VL_COFINS"])

    def _do_c175(self, item: dict[str, str]) -> LinhaDaExclusaoPisCofins | None:
        """O analítico da NFC-e. **Não tem item** — e o MA deixa em branco."""
        return self._montar(
            cnpj=self.cnpj_c, ramo=RAMO_C175, cfop=item["C175_CFOP"],
            modelo=self.c100.get("C100_COD_MOD", ""),
            documento=self.c100.get("C100_NUM_DOC", ""),
            chave=self.c100.get("C100_CHV_NFE", ""),
            data=self.c100.get("C100_DT_DOC", ""),
            numero_do_item="", codigo="", descricao="",
            valor=item["C175_VL_OPR"], desconto=item["C175_VL_DESC"],
            icms=None, rateio=None,
            cst=item["C175_CST_PIS"],
            base_pis=item["C175_VL_BC_PIS"], aliq_pis=item["C175_ALIQ_PIS"],
            pis=item["C175_VL_PIS"],
            base_cof=item["C175_VL_BC_COFINS"], aliq_cof=item["C175_ALIQ_COFINS"],
            cofins=item["C175_VL_COFINS"])

    def _do_a170(self, item: dict[str, str]) -> LinhaDaExclusaoPisCofins | None:
        """A nota de serviço **prestada**. Não tem CFOP: entra pelo sentido.

        O `IND_OPER` do A100 diz qual das duas é, e ignorá-lo trazia serviço
        contratado para dentro: duas notas de CST 50 em 10/2024, R$ 81,3 mil de
        base que o MA não tem. Mesmo erro do F100, mesma causa — registro sem
        CFOP cujo sentido ninguém perguntou.
        """
        if self.a100.get("A100_IND_OPER", "").strip() != GERACAO_DE_RECEITA:
            return None
        return self._montar(
            cnpj=self.cnpj_a, ramo=RAMO_A170, cfop="",
            modelo="", documento=self.a100.get("A100_NUM_DOC", ""),
            chave="", data=self.a100.get("A100_DT_DOC", ""),
            numero_do_item=item["A170_NUM_ITEM"], codigo=item["A170_COD_ITEM"],
            descricao=self._descricao(item["A170_COD_ITEM"], self.cnpj_a),
            valor=item["A170_VL_ITEM"], desconto=None, icms=None, rateio=None,
            cst=item["A170_CST_PIS"],
            base_pis=item["A170_VL_BC_PIS"], aliq_pis=item["A170_ALIQ_PIS"],
            pis=item["A170_VL_PIS"],
            base_cof=item["A170_VL_BC_COFINS"], aliq_cof=item["A170_ALIQ_COFINS"],
            cofins=item["A170_VL_COFINS"])

    def _somar_f100(self, item: dict[str, str]) -> None:
        """Acumula o F100 de receita. **Não emite**: quem emite é `fechar_f100`.

        **O sentido vem do `IND_OPER`, e aqui ele é obrigatório.** O F100 não tem
        CFOP, e tratar todo F100 como faturamento trazia aquisição para dentro da
        tese: duas linhas de CST 50 — crédito, que só existe na entrada — em
        03/2025, R$ 193.939,37 de base que o MA não tem. Pedir imposto de volta
        sobre uma compra é o tipo de erro que o relatório não deixa ver, porque a
        linha parece com todas as outras.
        """
        if item["F100_IND_OPER"].strip() != GERACAO_DE_RECEITA:
            return
        chave = (self.cnpj_f, item["F100_CST_PIS"], item["F100_DT_OPER"],
                 item["F100_ALIQ_PIS"], item["F100_ALIQ_COFINS"])
        soma = self.f100.setdefault(chave, [ZERO, ZERO, ZERO, ZERO, ZERO])
        for i, campo in enumerate(("F100_VL_OPER", "F100_VL_BC_PIS", "F100_VL_PIS",
                                   "F100_VL_BC_COFINS", "F100_VL_COFINS")):
            soma[i] += _numero(item[campo])

    def fechar_f100(self) -> Iterator[LinhaDaExclusaoPisCofins]:
        """Os demais documentos, **somados por dia** — uma linha, não várias.

        É o único ramo que o MA consolida, e a razão aparece quando se olha o
        leiaute: o F100 não tem número de documento, nem modelo, nem item. Duas
        linhas dele com o mesmo CNPJ, CST, data e alíquota são indistinguíveis no
        relatório — seriam duas linhas iguais com valores diferentes, e ninguém
        saberia dizer a que documento cada uma pertence.

        **Medido:** nos 334 F100 do arquivo de referência, o número de linhas de
        cada grupo (CNPJ, competência, CST) é exatamente o número de datas
        distintas do grupo, e a alíquota é sempre uma só. Somar por dia reduziu
        841 linhas nossas às 334 dele, e a soma fecha ao centavo — em 03/2025,
        91.667,15 + 41.479,98 + 1.526,00 = 134.673,13, o valor do MA.

        A alíquota entra na chave por segurança, e não por medida: no arquivo de
        referência ela nunca varia dentro do grupo, e somar bases de alíquotas
        diferentes numa linha só daria um número que nenhuma das duas explica.
        """
        for (cnpj, cst, data, aliq_pis, aliq_cof), soma in self.f100.items():
            linha = self._montar(
                cnpj=cnpj, ramo=RAMO_F100, cfop="",
                modelo="", documento="", chave="", data=data,
                numero_do_item="", codigo="", descricao="",
                valor=str(soma[0]), desconto=None, icms=None, rateio=None,
                cst=cst,
                base_pis=str(soma[1]), aliq_pis=aliq_pis, pis=str(soma[2]),
                base_cof=str(soma[3]), aliq_cof=aliq_cof, cofins=str(soma[4]))
            if linha:
                yield linha
        self.f100 = {}

    # ---------- a conta, que é uma só ----------
    def _montar(self, *, cnpj: str, ramo: str, cfop: str, modelo: str, documento: str,
                chave: str, data: str, numero_do_item: str, codigo: str, descricao: str,
                valor: str, desconto: str | None, icms: str | None,
                rateio: str | None, cst: str,
                base_pis: str, aliq_pis: str, pis: str,
                base_cof: str, aliq_cof: str,
                cofins: str) -> LinhaDaExclusaoPisCofins | None:
        natureza = (classificacao_do_cfop(cfop) if (cfop or "").strip()
                    else FATURAMENTO)
        if not natureza:
            return None

        base = _numero(base_pis)
        valor_do_pis, valor_da_cofins = _numero(pis), _numero(cofins)
        aliquota_do_pis, aliquota_da_cofins = _numero(aliq_pis), _numero(aliq_cof)
        if base <= ZERO:
            return None
        # **tributada é o que basta, e não paga.** Uma linha de R$ 0,06 com CST
        # 01 e alíquota cheia recolhe R$ 0,00 nas duas contribuições por
        # arredondamento, e o MA a traz: era a única das 81.193 linhas de
        # 05/2021 que ficava de fora quando o filtro pedia valor pago. A
        # alíquota entra na pergunta ao lado do valor, e não no lugar dele,
        # porque o monofásico de pauta tem valor sem alíquota percentual
        if not (valor_do_pis > ZERO or valor_da_cofins > ZERO
                or aliquota_do_pis > ZERO or aliquota_da_cofins > ZERO):
            return None

        # **a base de cada uma perde as duas.** É a tese, e é a única linha
        # deste módulo que escolhe algo — o resto é leitura e aritmética
        stf = base - valor_do_pis - valor_da_cofins
        pis_stf = _centavos(stf * aliquota_do_pis / CEM)
        cofins_stf = _centavos(stf * aliquota_da_cofins / CEM)
        diferenca_do_pis = valor_do_pis - pis_stf
        diferenca_da_cofins = valor_da_cofins - cofins_stf
        selic_do_pis = _centavos(diferenca_do_pis * self.selic / CEM)
        selic_da_cofins = _centavos(diferenca_da_cofins * self.selic / CEM)
        total_do_pis = diferenca_do_pis + selic_do_pis
        total_da_cofins = diferenca_da_cofins + selic_da_cofins

        self.saíram += 1
        t = str
        return LinhaDaExclusaoPisCofins(
            cnpj=cnpj, periodo=self.periodo, registro=ramo, modelo=modelo,
            numero_do_documento=documento, chave=chave, data_do_documento=_dia(data),
            numero_do_item=numero_do_item, codigo_do_item=codigo,
            descricao_do_item=descricao,
            valor_do_item=t(_numero(valor)), desconto=_do_ramo(desconto),
            icms=_do_ramo(icms), rateio=_do_ramo(rateio),
            cfop=(cfop or "").strip() or SAIDA, cfop_faturamento=natureza, cst=cst,
            selic_acumulada=t(self.selic),
            base_do_pis=t(base), base_do_pis_stf=t(stf),
            aliquota_do_pis=t(aliquota_do_pis), pis=t(valor_do_pis), pis_stf=t(pis_stf),
            diferenca_do_pis=t(diferenca_do_pis), selic_sobre_o_pis=t(selic_do_pis),
            total_do_pis_a_recuperar=t(total_do_pis),
            base_da_cofins=t(_numero(base_cof)), base_da_cofins_stf=t(stf),
            aliquota_da_cofins=t(aliquota_da_cofins), cofins=t(valor_da_cofins),
            cofins_stf=t(cofins_stf), diferenca_da_cofins=t(diferenca_da_cofins),
            selic_sobre_a_cofins=t(selic_da_cofins),
            total_da_cofins_a_recuperar=t(total_da_cofins),
            total_a_recuperar_atualizado=t(total_do_pis + total_da_cofins))
