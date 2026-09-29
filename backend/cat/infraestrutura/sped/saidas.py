"""Consulta de Saídas: tudo que saiu, num relatório só.

Equivalente à consulta **047 — Saídas — Todos os Registros — Completos** do
Sistema MA, gerada **só a partir da EFD-Contribuições**. É a gêmea da 037, que
vive em `entradas.py` — e não é uma cópia dela: as colunas são outras, a ordem
é outra, e duas das regras se invertem.

## O que a 047 tem e a 037 não

* **Seguro** e **Outras despesas acessórias**, do C100;
* **Código do serviço**, do 0200;
* **Natureza** e **Faturamento** — a natureza da *operação*, tirada do CFOP,
  que não se confunde com a natureza do *crédito* da 037 (aquela é a Tabela
  4.3.7 e só vale para entrada). Ver `tab_cfop_natureza_operacao`;
* e não tem o nome da conta nem o "D/C suposto": o MA não os escreve aqui.

## A UF troca de lado

Na 037 a coluna "UF Origem/Destino" é **participante/estabelecimento**: numa
entrada, a origem é quem nos vendeu. Na 047 é **estabelecimento/participante**,
porque numa saída a origem somos nós. Conferido no gabarito contra os CFOP
interestaduais: um 6411 de MG para São Paulo sai "MG/SP", nunca "SP/MG".

## Os quatro ramos

```
C010 > 0140 > C100 (IND_OPER=1) > C170     + 0150 + 0200
C010 > 0140 > C100 (IND_OPER=1) > C175     (sem participante, sem item)
A010 > A100 (IND_OPER=1) > A170            + 0150 + 0200
F010 > F100 (IND_OPER=1)                   + 0150 + 0200
```

**O C175 não tem item.** É o analítico da NFC-e, agregado por CFOP e CST — não
há `COD_ITEM`, logo não há descrição, NCM, código de barra, tipo, quantidade
nem unidade. Todas essas colunas saem vazias, e é assim no gabarito: 6.668.467
linhas, todas elas. Quem for mexer aqui achando que faltou join, não faltou.

**O bloco A tem abridor próprio**, o A010, como o D na 037. Sem ele a nota de
serviço de uma filial sairia com o CNPJ da matriz.

## A nota cancelada vira uma linha sozinha

Documento com `COD_SIT` 02, 03, 04 ou 05 — cancelado, cancelado extemporâneo,
denegado ou inutilizado — é escriturado **sem filho nenhum**: o leiaute manda
preencher só até a chave. O MA ainda assim emite a linha, com o que há: CNPJ,
período, ramo, modelo, situação, número, série e chave. No gabarito são 3.360
linhas assim, e todas as demais 1.111.703 do ramo têm `COD_SIT = "00"`.

Aqui a regra não olha o `COD_SIT`: emite a linha do documento quando o C100
**fecha sem nenhum filho**. Dá o mesmo resultado e não depende de a lista de
situações estar completa — se amanhã aparecer um código novo de cancelamento,
a linha sai do mesmo jeito.

**Menos a NFC-e.** O modelo 65 cancelado não rende linha nenhuma no gabarito:
são 106 documentos numa competência, e nenhum deles aparece. O MA trata o
C100/C175 como uma consulta à parte, e a linha do documento sozinho só existe
na do C100/C170. Não é escolha nossa, e sem ela sobram 106 linhas que o MA não
tem.

## O que ainda não está aqui

A cadeia do 047 tem mais ramos: C180/C185, C380/C385, C400/C405/C485,
C490/C495, C600/C605, C860/C880, os documentos de saída do bloco D, o F500 ao
F560 e o I100. **O cliente de referência não tem uma ocorrência sequer de
nenhum deles** — os 7.784.121 do gabarito são só estes quatro ramos —, e sem
arquivo real não há como saber que rótulo o MA dá àquele ramo nem o que ele
põe em cada coluna. É a mesma escolha da 037, pelo mesmo motivo: inventar a
regra seria pior que a ausência.

Para que a ausência não seja silenciosa, a passada **conta** esses registros e
devolve a contagem em `nao_cobertos`. Quem rodar num cliente que os tenha vê no
diário quantas linhas o relatório ainda não sabe ler, em vez de descobrir isso
somando a planilha.

Validado contra o gabarito do MA em 29/09/2026 — ver `tools/validar_047.py`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.cadastro import CadastroPorEstabelecimento
from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.infraestrutura.sped.tabelas import (
    tab_cfop,
    tab_cfop_natureza_operacao,
    tab_municipio,
    tab_tipo_item,
)
from cat.log import obter_log

log = obter_log(__name__)

# como cada ramo se identifica na coluna "Registros" do relatório.
#
# **Copiado letra por letra do gabarito, plural torto incluído.** "Nota Fiscal
# Eletrônicas" não é erro de digitação nosso: é o que o MA escreve, e quem
# comparar os dois relatórios compara texto.
RAMO_C170 = "C100/C170 - Documento - Nota Fiscal"
RAMO_C175 = "C100/C175 - Documento - Nota Fiscal Eletrônicas"
RAMO_A170 = "A100/A170 - Nota Fiscal de Serviço"
RAMO_F100 = "F100 - Demais Documentos e Operações"

# os registros que a passada decodifica; o resto da linha nem é olhado
_DE_INTERESSE = {
    b"0000",
    b"0140", b"0150", b"0200",
    b"C010", b"C100", b"C170", b"C175",
    b"A010", b"A100", b"A170",
    b"F010", b"F100",
}

# os ramos de saída que o relatório ainda não sabe montar. Não são lidos — só
# contados, para que o diário diga o que ficou de fora. Ver o topo do módulo
_NAO_COBERTOS = {
    b"C180", b"C380", b"C400", b"C490", b"C600", b"C860",
    b"D200", b"D300", b"D350", b"D600",
    b"F500", b"F510", b"F550", b"F560", b"I100",
}

# as tabelas de cadastro e onde está a chave de cada uma. **Elas são do
# estabelecimento, não do arquivo** — ver `sped/cadastro.py`, que é onde essa
# regra mora e por que ela custou 1.953 linhas erradas para ser achada
_CHAVE_DO_CADASTRO = {b"0150": 1, b"0200": 1}

# IND_OPER = 0 é entrada; 1 é saída
SAIDA = "1"

# a NFC-e, que é o documento do ramo C175 — e o único cuja nota cancelada não
# rende linha. Ver "A nota cancelada vira uma linha sozinha", no topo
MODELO_NFCE = "65"


@dataclass
class LinhaDeSaida:
    """Uma linha do relatório, na ordem de colunas da 047."""

    cnpj: str = ""
    periodo: str = ""
    registros: str = ""
    modelo: str = ""
    situacao: str = ""
    codigo_do_participante: str = ""
    cnpj_do_participante: str = ""
    cpf_do_participante: str = ""
    nome_do_participante: str = ""
    uf_origem_destino: str = ""
    numero_do_documento: str = ""
    serie: str = ""
    chave: str = ""
    data_do_documento: str = ""
    data_de_saida: str = ""
    valor_do_documento: str = ""
    desconto_do_documento: str = ""
    valor_da_mercadoria: str = ""
    frete: str = ""
    seguro: str = ""
    outras_despesas: str = ""
    numero_do_item: str = ""
    codigo_do_item: str = ""
    descricao_complementar: str = ""
    descricao_do_item: str = ""
    ncm: str = ""
    codigo_do_servico: str = ""
    codigo_de_barra: str = ""
    tipo_do_item: str = ""
    valor_do_item: str = ""
    quantidade: str = ""
    unidade: str = ""
    desconto_do_item: str = ""
    cfop: str = ""
    descricao_do_cfop: str = ""
    faturamento: str = ""
    natureza: str = ""
    icms: str = ""
    icms_st: str = ""
    ipi: str = ""
    cst_pis: str = ""
    base_do_pis: str = ""
    quantidade_base_do_pis: str = ""
    aliquota_do_pis: str = ""
    quantidade_aliquota_do_pis: str = ""
    pis: str = ""
    cst_cofins: str = ""
    base_da_cofins: str = ""
    quantidade_base_da_cofins: str = ""
    aliquota_da_cofins: str = ""
    quantidade_aliquota_da_cofins: str = ""
    cofins: str = ""
    conta_contabil: str = ""

    def como_dicionario(self) -> dict[str, str]:
        return asdict(self)


def colunas_da_saida() -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet vazio."""
    return list(LinhaDeSaida().como_dicionario())


# ---------------------------------------------------------------------------
# formatação: o relatório sai no padrão brasileiro, como o de referência
# ---------------------------------------------------------------------------
def _numero(bruto: str) -> float:
    bruto = (bruto or "").strip()
    if not bruto:
        return 0.0
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        return float(bruto)
    except ValueError:
        return 0.0


def _dinheiro(bruto: str) -> str:
    """Duas casas, vírgula decimal. Vazio continua vazio — não vira "0,00"."""
    return f"{_numero(bruto):.2f}".replace(".", ",") if (bruto or "").strip() else ""


def _aliquota(bruto: str) -> str:
    return f"{_numero(bruto):.4f}".replace(".", ",") if (bruto or "").strip() else ""


def _quantidade(bruto: str) -> str:
    return f"{_numero(bruto):.5f}".replace(".", ",") if (bruto or "").strip() else ""


def _dia(bruto: str) -> str:
    """ddmmaaaa vira dd/mm/aaaa. O que não for data volta como veio."""
    b = (bruto or "").strip()
    if len(b) != 8 or not b.isdigit():
        return b
    try:
        return date(int(b[4:]), int(b[2:4]), int(b[:2])).strftime("%d/%m/%Y")
    except ValueError:
        return b


def _rotulo_do_tipo(codigo: str) -> str:
    codigo = (codigo or "").strip()
    descricao = tab_tipo_item.descricao(codigo) if codigo else ""
    return f"{codigo} {descricao}" if descricao else codigo


def _nomeados(prefixo: str, valores: list[str]) -> dict[str, str]:
    nomes = nomes_dos_campos(prefixo)
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


@dataclass
class Contagem:
    """O que a passada viu, para o diário."""

    linhas: int = 0
    por_ramo: dict[str, int] | None = None
    nao_cobertos: dict[str, int] | None = None


def saidas(caminho: str, codificacao: str,
           contagem: Contagem | None = None) -> Iterator[LinhaDeSaida]:
    """Todas as saídas do arquivo, nos quatro ramos, numa passada só.

    `contagem`, quando vem, recebe o que se viu — inclusive os registros de
    saída que o relatório ainda não cobre, para o diário poder dizê-lo.
    """
    contexto = _Contexto(codificacao)
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None:
                continue
            if registro in _NAO_COBERTOS:
                contexto.nao_cobertos[registro.decode("ascii")] = (
                    contexto.nao_cobertos.get(registro.decode("ascii"), 0) + 1)
                continue
            if registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(registro, campos(linha.decode(codificacao, errors="replace")))
        # o último documento não vê outro para fechá-lo
        yield from contexto.fechar_documento()

    if contagem is not None:
        contagem.linhas = contexto.saíram
        contagem.por_ramo = dict(sorted(contexto.por_ramo.items()))
        contagem.nao_cobertos = dict(sorted(contexto.nao_cobertos.items()))

    log.info("consulta de saídas gerada", extra={
        "arquivo": os.path.basename(caminho), "linhas": contexto.saíram,
        "por_ramo": dict(sorted(contexto.por_ramo.items())),
        "nao_cobertos": dict(sorted(contexto.nao_cobertos.items())),
    })


class _Contexto:
    """O estado da passada: as tabelas do bloco 0 e o documento aberto.

    Três CNPJ correntes — bloco C, bloco A e bloco F, cada um com seu abridor.
    Ver o topo do módulo: sem o do bloco A, nota de serviço de filial sairia
    com CNPJ de matriz, que foi bug de verdade na 037 com o bloco D.
    """

    def __init__(self, codificacao: str) -> None:
        self.codificacao = codificacao
        self.periodo = ""
        self.cadastro = CadastroPorEstabelecimento(_CHAVE_DO_CADASTRO)
        self.cnpj_c = self.cnpj_a = self.cnpj_f = ""
        # o documento aberto e se ele já teve filho: um C100 que fecha sem
        # nenhum é nota cancelada, e mesmo assim rende uma linha
        self.c100: list[str] = []
        self.c100_e_saida = False
        self.c100_teve_filho = False
        self.a100: list[str] = []
        self.a100_e_saida = False
        self.saíram = 0
        self.por_ramo: dict[str, int] = {}
        self.nao_cobertos: dict[str, int] = {}

    # ---------- busca nas tabelas do bloco 0 ----------
    def _participante(self, codigo: str, cnpj: str) -> dict[str, str]:
        d = _nomeados("0150", self.cadastro.linha(b"0150", codigo, cnpj))
        return {
            "codigo_do_participante": codigo,
            "cnpj_do_participante": d["0150_CNPJ"],
            "cpf_do_participante": d["0150_CPF"],
            "nome_do_participante": d["0150_NOME"],
        }

    def _item(self, codigo: str, cnpj: str) -> dict[str, str]:
        d = _nomeados("0200", self.cadastro.linha(b"0200", codigo, cnpj))
        return {"descricao": d["0200_DESCR_ITEM"], "ncm": d["0200_COD_NCM"],
                "barra": d["0200_COD_BARRA"], "tipo": d["0200_TIPO_ITEM"],
                "servico": d["0200_COD_LST"]}

    def _uf_do_estabelecimento(self, cnpj: str) -> str:
        return _nomeados("0140", self.cadastro.estabelecimento(cnpj))["0140_UF"]

    def _uf_origem_destino(self, participante: str, cnpj: str) -> str:
        """"UF do estabelecimento / UF do participante".

        **Nesta ordem, e é o contrário da 037.** Numa saída a origem somos nós.
        O 0150 não traz UF — só o código do município —, e a UF sai dos dois
        primeiros dígitos do código do IBGE, que é convenção pública e fixa.

        **Faltando uma das duas, a coluna sai vazia** — nunca "MG/". Uma ponta
        só não é par de origem e destino, e o gabarito escreve vazio: é uma
        linha em 7.784.121, um participante cujo município o 0150 não traz, e
        foi a última divergência a cair.
        """
        municipio = _nomeados(
            "0150", self.cadastro.linha(b"0150", participante, cnpj))["0150_COD_MUN"]
        do_participante = tab_municipio.uf_do_municipio(municipio)
        do_estabelecimento = self._uf_do_estabelecimento(cnpj)
        return (f"{do_estabelecimento}/{do_participante}"
                if (do_participante and do_estabelecimento) else "")

    def _da_operacao(self, cfop: str) -> dict[str, str]:
        """CFOP, descrição, natureza e faturamento — as quatro andam juntas."""
        descricao = tab_cfop.descricao_por_extenso(cfop)
        natureza = tab_cfop_natureza_operacao.natureza(cfop, descricao)
        return {"cfop": cfop, "descricao_do_cfop": descricao, "natureza": natureza,
                "faturamento": tab_cfop_natureza_operacao.faturamento(natureza)}

    def _emitir(self, linha: LinhaDeSaida) -> LinhaDeSaida:
        self.saíram += 1
        self.por_ramo[linha.registros] = self.por_ramo.get(linha.registros, 0) + 1
        return linha

    # ---------- a passada ----------
    def ver(self, registro: bytes, valores: list[str]) -> Iterator[LinhaDeSaida]:
        if self.cadastro.guardar(registro, valores):
            return
        primeiro = valores[1].strip() if len(valores) > 1 else ""
        if registro == b"0140":
            self.cadastro.abrir(valores)
            return
        if registro == b"0000":
            # o período é o mesmo em todas as linhas do arquivo, e quem lê o
            # 0000 é o domínio — nunca este módulo, por posição fixa
            try:
                cabecalho = ler_cabecalho("|" + "|".join(valores) + "|")
                self.periodo = cabecalho.inicio.replace(day=1).strftime("%d/%m/%Y")
                # é do cadastro da matriz que sai o campo que o do
                # estabelecimento deixou em branco. Ver `sped/cadastro.py`
                self.cadastro.definir_matriz(str(cabecalho.cnpj or ""))
            except ArquivoNaoReconhecido as erro:
                log.warning("registro 0000 não reconhecido; o período fica em branco",
                            extra={"motivo": str(erro)})
        elif registro == b"C010":
            yield from self.fechar_documento()
            self.cnpj_c = primeiro
        elif registro == b"A010":
            yield from self.fechar_documento()
            self.cnpj_a = primeiro
        elif registro == b"F010":
            yield from self.fechar_documento()
            self.cnpj_f = primeiro
        elif registro == b"C100":
            yield from self.fechar_documento()
            self.c100, self.c100_e_saida, self.c100_teve_filho = valores, primeiro == SAIDA, False
        elif registro == b"C170" and self.c100_e_saida:
            self.c100_teve_filho = True
            yield self._do_c170(valores)
        elif registro == b"C175" and self.c100_e_saida:
            self.c100_teve_filho = True
            yield self._do_c175(valores)
        elif registro == b"A100":
            yield from self.fechar_documento()
            self.a100, self.a100_e_saida = valores, primeiro == SAIDA
        elif registro == b"A170" and self.a100_e_saida:
            yield self._do_a170(valores)
        elif registro == b"F100" and primeiro == SAIDA:
            yield self._do_f100(valores)

    def fechar_documento(self) -> Iterator[LinhaDeSaida]:
        """O C100 de saída que não teve filho rende a linha do documento.

        É a nota cancelada, denegada ou inutilizada: o leiaute manda escriturar
        só até a chave, e o MA emite a linha assim mesmo — **exceto quando é
        NFC-e**. Ver o topo do módulo para as duas metades dessa regra.
        """
        if (self.c100 and self.c100_e_saida and not self.c100_teve_filho
                and _nomeados("C100", self.c100)["C100_COD_MOD"] != MODELO_NFCE):
            yield self._do_c100_sozinho()
        self.c100, self.c100_e_saida, self.c100_teve_filho = [], False, False

    # ---------- um método por ramo ----------
    def _do_documento(self, nota: dict[str, str]) -> dict[str, str]:
        """As colunas do C100, que os dois ramos do bloco C compartilham."""
        return {
            "cnpj": self.cnpj_c, "periodo": self.periodo,
            "modelo": nota["C100_COD_MOD"], "situacao": nota["C100_COD_SIT"],
            "numero_do_documento": nota["C100_NUM_DOC"], "serie": nota["C100_SER"],
            "chave": nota["C100_CHV_NFE"], "data_do_documento": _dia(nota["C100_DT_DOC"]),
            "data_de_saida": _dia(nota["C100_DT_E_S"]),
            "valor_do_documento": _dinheiro(nota["C100_VL_DOC"]),
            "desconto_do_documento": _dinheiro(nota["C100_VL_DESC"]),
            "valor_da_mercadoria": _dinheiro(nota["C100_VL_MERC"]),
            "frete": _dinheiro(nota["C100_VL_FRT"]),
            "seguro": _dinheiro(nota["C100_VL_SEG"]),
            "outras_despesas": _dinheiro(nota["C100_VL_OUT_DA"]),
        }

    def _do_c100_sozinho(self) -> LinhaDeSaida:
        """A nota sem filho: sai o que o leiaute deixou escrever, e nada mais."""
        nota = _nomeados("C100", self.c100)
        participante = nota["C100_COD_PART"]
        return self._emitir(LinhaDeSaida(
            registros=RAMO_C170,
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_c)
            if participante else "",
            **self._do_documento(nota),
            **(self._participante(participante, self.cnpj_c) if participante else {})))

    def _do_c170(self, valores: list[str]) -> LinhaDeSaida:
        nota = _nomeados("C100", self.c100)
        item = _nomeados("C170", valores)
        cadastro = self._item(item["C170_COD_ITEM"], self.cnpj_c)
        participante = nota["C100_COD_PART"]
        return self._emitir(LinhaDeSaida(
            registros=RAMO_C170,
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_c),
            numero_do_item=item["C170_NUM_ITEM"], codigo_do_item=item["C170_COD_ITEM"],
            descricao_complementar=item["C170_DESCR_COMPL"],
            descricao_do_item=cadastro["descricao"], ncm=cadastro["ncm"],
            codigo_do_servico=cadastro["servico"], codigo_de_barra=cadastro["barra"],
            tipo_do_item=_rotulo_do_tipo(cadastro["tipo"]),
            valor_do_item=_dinheiro(item["C170_VL_ITEM"]),
            quantidade=_quantidade(item["C170_QTD"]), unidade=item["C170_UNID"],
            desconto_do_item=_dinheiro(item["C170_VL_DESC"]),
            icms=_dinheiro(item["C170_VL_ICMS"]), icms_st=_dinheiro(item["C170_VL_ICMS_ST"]),
            ipi=_dinheiro(item["C170_VL_IPI"]),
            cst_pis=item["C170_CST_PIS"], base_do_pis=_dinheiro(item["C170_VL_BC_PIS"]),
            quantidade_base_do_pis=item["C170_QUANT_BC_PIS"],
            aliquota_do_pis=_aliquota(item["C170_ALIQ_PIS_PERC"]),
            quantidade_aliquota_do_pis=item["C170_ALIQ_PIS_REAIS"],
            pis=_dinheiro(item["C170_VL_PIS"]),
            cst_cofins=item["C170_CST_COFINS"],
            base_da_cofins=_dinheiro(item["C170_VL_BC_COFINS"]),
            quantidade_base_da_cofins=item["C170_QUANT_BC_COFINS"],
            aliquota_da_cofins=_aliquota(item["C170_ALIQ_COFINS_PERC"]),
            quantidade_aliquota_da_cofins=item["C170_ALIQ_COFINS_REAIS"],
            cofins=_dinheiro(item["C170_VL_COFINS"]),
            conta_contabil=item["C170_COD_CTA"],
            **self._do_documento(nota),
            **self._da_operacao(item["C170_CFOP"]),
            **self._participante(participante, self.cnpj_c)))

    def _do_c175(self, valores: list[str]) -> LinhaDeSaida:
        """O analítico da NFC-e: por CFOP e CST, sem item e sem participante.

        Não há `COD_ITEM` no C175 — nem `COD_PART` na NFC-e, que é venda a
        consumidor não identificado. As duas famílias de colunas saem vazias, e
        no gabarito saem vazias nas 6.668.467 linhas.
        """
        nota = _nomeados("C100", self.c100)
        analitico = _nomeados("C175", valores)
        return self._emitir(LinhaDeSaida(
            registros=RAMO_C175,
            valor_do_item=_dinheiro(analitico["C175_VL_OPR"]),
            desconto_do_item=_dinheiro(analitico["C175_VL_DESC"]),
            cst_pis=analitico["C175_CST_PIS"],
            base_do_pis=_dinheiro(analitico["C175_VL_BC_PIS"]),
            quantidade_base_do_pis=analitico["C175_QUANT_BC_PIS"],
            aliquota_do_pis=_aliquota(analitico["C175_ALIQ_PIS"]),
            quantidade_aliquota_do_pis=analitico["C175_ALIQ_PIS_QUANT"],
            pis=_dinheiro(analitico["C175_VL_PIS"]),
            cst_cofins=analitico["C175_CST_COFINS"],
            base_da_cofins=_dinheiro(analitico["C175_VL_BC_COFINS"]),
            quantidade_base_da_cofins=analitico["C175_QUANT_BC_COFINS"],
            aliquota_da_cofins=_aliquota(analitico["C175_ALIQ_COFINS"]),
            quantidade_aliquota_da_cofins=analitico["C175_ALIQ_COFINS_QUANT"],
            cofins=_dinheiro(analitico["C175_VL_COFINS"]),
            conta_contabil=analitico["C175_COD_CTA"],
            **self._do_documento(nota),
            **self._da_operacao(analitico["C175_CFOP"])))

    def _do_a170(self, valores: list[str]) -> LinhaDeSaida:
        """Serviço prestado. O CNPJ é o do A010, e não há modelo nem CFOP."""
        nota = _nomeados("A100", self.a100)
        item = _nomeados("A170", valores)
        cadastro = self._item(item["A170_COD_ITEM"], self.cnpj_a)
        participante = nota["A100_COD_PART"]
        return self._emitir(LinhaDeSaida(
            cnpj=self.cnpj_a, periodo=self.periodo, registros=RAMO_A170,
            situacao=nota["A100_COD_SIT"],
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_a),
            numero_do_documento=nota["A100_NUM_DOC"], serie=nota["A100_SER"],
            chave=nota["A100_CHV_NFSE"], data_do_documento=_dia(nota["A100_DT_DOC"]),
            data_de_saida=_dia(nota["A100_DT_EXE_SERV"]),
            valor_do_documento=_dinheiro(nota["A100_VL_DOC"]),
            desconto_do_documento=_dinheiro(nota["A100_VL_DESC"]),
            numero_do_item=item["A170_NUM_ITEM"], codigo_do_item=item["A170_COD_ITEM"],
            descricao_complementar=item["A170_DESCR_COMPL"],
            descricao_do_item=cadastro["descricao"], ncm=cadastro["ncm"],
            codigo_do_servico=cadastro["servico"], codigo_de_barra=cadastro["barra"],
            tipo_do_item=_rotulo_do_tipo(cadastro["tipo"]),
            valor_do_item=_dinheiro(item["A170_VL_ITEM"]),
            desconto_do_item=_dinheiro(item["A170_VL_DESC"]),
            cst_pis=item["A170_CST_PIS"], base_do_pis=_dinheiro(item["A170_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(item["A170_ALIQ_PIS"]),
            pis=_dinheiro(item["A170_VL_PIS"]),
            cst_cofins=item["A170_CST_COFINS"],
            base_da_cofins=_dinheiro(item["A170_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(item["A170_ALIQ_COFINS"]),
            cofins=_dinheiro(item["A170_VL_COFINS"]),
            conta_contabil=item["A170_COD_CTA"],
            **self._participante(participante, self.cnpj_a)))

    def _do_f100(self, valores: list[str]) -> LinhaDeSaida:
        """Demais documentos e operações. O CNPJ é o do F010, e não há CFOP."""
        d = _nomeados("F100", valores)
        cadastro = self._item(d["F100_COD_ITEM"], self.cnpj_f)
        participante = d["F100_COD_PART"]
        return self._emitir(LinhaDeSaida(
            cnpj=self.cnpj_f, periodo=self.periodo, registros=RAMO_F100,
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_f)
            if participante else "",
            data_do_documento=_dia(d["F100_DT_OPER"]),
            valor_do_documento=_dinheiro(d["F100_VL_OPER"]),
            valor_da_mercadoria=_dinheiro(d["F100_VL_OPER"]),
            codigo_do_item=d["F100_COD_ITEM"], descricao_do_item=cadastro["descricao"],
            ncm=cadastro["ncm"], codigo_do_servico=cadastro["servico"],
            codigo_de_barra=cadastro["barra"], tipo_do_item=_rotulo_do_tipo(cadastro["tipo"]),
            valor_do_item=_dinheiro(d["F100_VL_OPER"]),
            cst_pis=d["F100_CST_PIS"], base_do_pis=_dinheiro(d["F100_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(d["F100_ALIQ_PIS"]), pis=_dinheiro(d["F100_VL_PIS"]),
            cst_cofins=d["F100_CST_COFINS"],
            base_da_cofins=_dinheiro(d["F100_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(d["F100_ALIQ_COFINS"]),
            cofins=_dinheiro(d["F100_VL_COFINS"]),
            conta_contabil=d["F100_COD_CTA"],
            **(self._participante(participante, self.cnpj_f) if participante else {})))
