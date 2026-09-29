"""Consulta de Entradas: tudo que entrou, num relatório só.

Equivalente à consulta **037 — Entradas — Todos os Registros — Completos** do
Sistema MA, gerada **só a partir da EFD-Contribuições** — sem depender daquele
sistema. É a saída que se confronta com o razão da ECD: o que a escrituração
fiscal diz ter entrado contra o que a contabilidade lançou.

Portado do projeto Quebra de SPED em 22/09/2026. **Porte fiel, de propósito.**
O que está aqui não foi deduzido do leiaute: foi confirmado contra arquivo de
referência real de duas empresas, e sem esse arquivo eu não teria como
redescobrir nem revalidar. Onde eu discordaria, escrevi o comentário em vez de
mudar a regra.

## Os oito ramos de documento de entrada

```
C010 > 0140 > C100 (IND_OPER=0) > C170        + 0150 + 0200 + 0500
C500 (sempre entrada) > C501 + C505           + 0150 + 0500
F010 > F100 (IND_OPER=0)                      + 0150 + 0200 + 0500
C010 > C190 > C191 + C195 (sempre entrada)    + 0200 + 0500
D010 > D100 (IND_OPER=0) > D101 + D105        + 0150 + 0500
D010 > D500 (IND_OPER=0) > D501 + D505        + 0150 + 0500
F010 > F120 (registro único, sem filhos)      + 0500
F010 > F130 (registro único, sem filhos)      + 0500
```

## O que só o dado real ensinou

**O C190 variou de 0% a 95%.** Na primeira empresa validada não havia uma
ocorrência sequer; na segunda era o ramo dominante, com mais de 95% das linhas. Quem portar este módulo achando que o
C100/C170 é "o caminho normal" e o resto é detalhe vai acertar num cliente e
perder o relatório inteiro no outro.

**O `COD_PART` do C191/C195 não referencia o 0150** naquela empresa — é o CNPJ
do participante direto, sem cadastro correspondente. Por isso esse ramo não
busca nome nem código curto, e a UF sai só a do estabelecimento.

**O bloco D tem abridor próprio.** Este foi bug de verdade, achado na validação:
o D010 abre o estabelecimento do bloco D, independente do C010 do bloco C. Sem
ele, D100 e D500 de uma **filial** saíam com o CNPJ da **matriz** — o último
C010 processado. Três CNPJ correntes convivem aqui, e é assim que tem de ser.

**E o cadastro também é do estabelecimento.** Segundo bug da mesma família,
achado em 29/09/2026 montando a 047: o 0150, o 0200 e o 0500 pendem do 0140, e
aqui eram uma tabela só por arquivo. Num cliente com matriz e filial o mesmo
`COD_ITEM` é outra mercadoria em cada uma — 134 códigos assim numa competência
—, e a nota da matriz saía com a descrição, o NCM e o código de barra da filial.
A regra mora em `sped/cadastro.py`, compartilhada com a 047.

**Os filhos do C190 não vêm intercalados** — todos os C191, depois todos os
C195, pareados por posição. É a mesma armadilha de `consolidado.py`.

**O que ficou de fora**: A100/A170, C395/C396 e F150. Nenhuma empresa validada
teve ocorrência, então não há regra de preenchimento confirmada. Inventá-la
seria pior que a ausência.

## Duas heurísticas, marcadas como tais

`natureza_do_credito` e `debito_ou_credito` **não saem do arquivo** — são
deduzidas. A primeira sai do CFOP, conferida contra 124.647 linhas de relatórios
de referência sem uma exceção; a segunda tem ~98% de aderência, com as
discordâncias concentradas em CFOP de devolução. As duas estão isoladas em
funções próprias, com o nome dizendo que são dedução, para que ninguém as tome
por leitura.
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
    tab_437,
    tab_cfop,
    tab_cfop_natureza_credito,
    tab_municipio,
    tab_tipo_item,
)
from cat.log import obter_log

log = obter_log(__name__)

# como cada ramo se identifica na coluna "Registros" do relatório
RAMO_C100 = "C100/C170 - Documento - Nota Fiscal"
RAMO_C500 = "C500/C505 - Nota Fiscal/Conta de Energia Elétrica/Água/Gás"
RAMO_F100 = "F100 - Demais Documentos e Operações"
RAMO_C190 = "C190/C195 - Consolidação de Notas Fiscais Eletrônicas"
RAMO_D100 = "D100/D105 - Aquisição de Serviços de Transporte"
RAMO_D500 = "D500/D505 - Nota Fiscal de Serviço de Comunicação"
RAMO_F120 = "F120 - Bens Incorporados ao Ativo Imobilizado - Depreciação"
RAMO_F130 = "F130 - Bens Incorporados ao Ativo Imobilizado - Aquisição"

# os registros que a passada olha; o resto da linha nem é decodificado
_DE_INTERESSE = {
    b"0000",
    b"0140", b"0150", b"0200", b"0500",
    b"C010", b"C100", b"C170", b"C190", b"C191", b"C195",
    b"C500", b"C501", b"C505", b"F010", b"F100",
    b"D010", b"D100", b"D101", b"D105", b"D500", b"D501", b"D505",
    b"F120", b"F130",
}

# as tabelas de cadastro e onde está a chave de cada uma. **Elas são do
# estabelecimento, não do arquivo** — ver `sped/cadastro.py`. Foi assim que
# esteve até 29/09/2026, e num cliente com matriz e filial isso trocava a
# descrição e o NCM do item em cerca de 1,7% das linhas, calado
_CHAVE_DO_CADASTRO = {b"0150": 1, b"0200": 1, b"0500": 5}

# IND_OPER = 0 é entrada; 1 é saída
ENTRADA = "0"


@dataclass
class LinhaDeEntrada:
    """Uma linha do relatório, no leiaute da 037."""

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
    municipio_do_participante: str = ""
    numero_do_documento: str = ""
    serie: str = ""
    chave: str = ""
    data_do_documento: str = ""
    data_de_entrada: str = ""
    valor_do_documento: str = ""
    desconto_do_documento: str = ""
    valor_da_mercadoria: str = ""
    frete: str = ""
    numero_do_item: str = ""
    codigo_do_item: str = ""
    descricao_complementar: str = ""
    descricao_do_item: str = ""
    ncm: str = ""
    codigo_de_barra: str = ""
    tipo_do_item: str = ""
    valor_do_item: str = ""
    quantidade: str = ""
    unidade: str = ""
    desconto_do_item: str = ""
    natureza_do_credito: str = ""
    cfop: str = ""
    descricao_do_cfop: str = ""
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
    nome_da_conta: str = ""
    debito_ou_credito: str = ""

    def como_dicionario(self) -> dict[str, str]:
        return asdict(self)


def colunas_da_entrada() -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet vazio."""
    return list(LinhaDeEntrada().como_dicionario())


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


def _rotulo_da_natureza(codigo: str) -> str:
    codigo = (codigo or "").strip()
    descricao = tab_437.descricao(codigo) if codigo else ""
    return f"{codigo} - {descricao}" if descricao else codigo


# ---------------------------------------------------------------------------
# as duas heurísticas — deduzidas, não lidas
# ---------------------------------------------------------------------------
def _natureza_deduzida(cfop: str, tipo_do_item: str) -> str:
    """A natureza do crédito quando o registro não tem campo para ela.

    É o caso do C170 e do C191/C195 — só o C501, o D101, o D501 e o bloco F
    trazem `NAT_BC_CRED` escrito.

    **A dedução é pelo CFOP.** A natureza descreve a *operação*, e é o CFOP que
    codifica a operação; o tipo do item descreve a *mercadoria*. A regra foi
    conferida contra 43.497 linhas de um relatório de referência e reconfirmada
    contra outras 81.150, em vinte CFOP distintos, sem uma exceção.

    O tipo do item fica como segunda tentativa, e só para `TIPO_ITEM = "00"`.
    Ele era a regra antes desta — e estava errado: na amostra que derrubou a
    hipótese, o campo vinha constante em `"99"` em 100% das linhas, o que fazia
    a natureza sumir de toda a base. Continua servindo para o CFOP que a tabela
    não conhece, quando o cadastro diz que a mercadoria é de revenda.

    Fora isso, branco de propósito: natureza errada com cara de certa é pior que
    coluna vazia.
    """
    pelo_cfop = tab_cfop_natureza_credito.codigo(cfop)
    if pelo_cfop:
        return _rotulo_da_natureza(pelo_cfop)
    return _rotulo_da_natureza("01") if (tipo_do_item or "").strip() == "00" else ""


def _debito_ou_credito_suposto(cst_pis: str, pis: str) -> str:
    """Hipótese com ~98% de aderência ao arquivo de referência.

    "C" quando o CST do PIS é 50 e há valor de PIS; vazio no resto. As
    discordâncias concentram-se em CFOP de devolução (1202, 1411…). Fica isolada
    aqui, com "suposto" no nome, para que ninguém a confunda com leitura — e
    para que o dia de corrigi-la seja o dia de mexer numa função só.
    """
    return "C" if (cst_pis or "").strip() == "50" and _numero(pis) > 0 else ""


def _nomeados(prefixo: str, valores: list[str]) -> dict[str, str]:
    nomes = nomes_dos_campos(prefixo)
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


def entradas(caminho: str, codificacao: str) -> Iterator[LinhaDeEntrada]:
    """Todas as entradas do arquivo, nos oito ramos, numa passada só."""
    contexto = _Contexto(codificacao)
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(registro, campos(linha.decode(codificacao, errors="replace")))
        # o último grupo do C190 não vê outro C190 para fechá-lo
        yield from contexto.fechar_c190()

    log.info("consulta de entradas gerada", extra={
        "arquivo": os.path.basename(caminho), "linhas": contexto.saíram,
        "por_ramo": dict(sorted(contexto.por_ramo.items())),
    })


class _Contexto:
    """O estado da passada: as tabelas do bloco 0 e os documentos abertos.

    Vive numa classe e não em closures porque são **três CNPJ correntes** —
    bloco C, bloco D e bloco F, cada um com seu abridor —, além de cinco
    documentos em aberto. Em closures isso vira um emaranhado de `nonlocal`.
    """

    def __init__(self, codificacao: str) -> None:
        self.codificacao = codificacao
        self.periodo = ""
        self.cadastro = CadastroPorEstabelecimento(_CHAVE_DO_CADASTRO)
        # três estabelecimentos correntes, um por bloco. Ver o topo do módulo:
        # sem o do bloco D, documento de filial saía com CNPJ de matriz
        self.cnpj_c = self.cnpj_d = self.cnpj_f = ""
        self.c100: list[str] = []
        self.c100_e_entrada = False
        self.c190: list[str] = []
        self.c191: list[list[str]] = []
        self.c195: list[list[str]] = []
        self.c500: list[str] = []
        self.c501: list[str] | None = None
        self.d100: list[str] = []
        self.d101: list[str] | None = None
        self.d500: list[str] = []
        self.d501: list[str] | None = None
        self.saíram = 0
        self.por_ramo: dict[str, int] = {}

    # ---------- busca nas tabelas do bloco 0 ----------
    def _participante(self, codigo: str, cnpj: str) -> dict[str, str]:
        """Os dados do participante, município incluído.

        O 0150 traz o município como código do IBGE; o nome sai da tabela. Os
        ramos sem participante — o C190 consolidado, o F120 e o F130 — ficam com
        a coluna em branco, que é o que ela significa ali: não há de quem.
        """
        d = _nomeados("0150", self.cadastro.linha(b"0150", codigo, cnpj))
        return {
            "codigo_do_participante": codigo,
            "cnpj_do_participante": d["0150_CNPJ"],
            "cpf_do_participante": d["0150_CPF"],
            "nome_do_participante": d["0150_NOME"],
            "municipio_do_participante": tab_municipio.descricao(d["0150_COD_MUN"]),
        }

    def _conta(self, codigo: str, cnpj: str) -> tuple[str, str]:
        return codigo, _nomeados("0500", self.cadastro.linha(b"0500", codigo, cnpj))["0500_NOME_CTA"]

    def _item(self, codigo: str, cnpj: str) -> dict[str, str]:
        d = _nomeados("0200", self.cadastro.linha(b"0200", codigo, cnpj))
        return {"descricao": d["0200_DESCR_ITEM"], "ncm": d["0200_COD_NCM"],
                "barra": d["0200_COD_BARRA"], "tipo": d["0200_TIPO_ITEM"]}

    def _uf_do_estabelecimento(self, cnpj: str) -> str:
        return _nomeados("0140", self.cadastro.estabelecimento(cnpj))["0140_UF"]

    def _uf_origem_destino(self, participante: str, cnpj: str) -> str:
        """"UF do participante / UF do estabelecimento".

        O 0150 não traz UF — só o código do município. A UF sai dos dois
        primeiros dígitos do código do IBGE, que é convenção pública e fixa.
        """
        municipio = _nomeados(
            "0150", self.cadastro.linha(b"0150", participante, cnpj))["0150_COD_MUN"]
        do_participante = tab_municipio.uf_do_municipio(municipio)
        do_estabelecimento = self._uf_do_estabelecimento(cnpj)
        return (f"{do_participante}/{do_estabelecimento}"
                if (do_participante or do_estabelecimento) else "")

    def _emitir(self, linha: LinhaDeEntrada) -> LinhaDeEntrada:
        self.saíram += 1
        self.por_ramo[linha.registros] = self.por_ramo.get(linha.registros, 0) + 1
        return linha

    # ---------- a passada ----------
    def ver(self, registro: bytes, valores: list[str]) -> Iterator[LinhaDeEntrada]:
        if self.cadastro.guardar(registro, valores):
            return
        primeiro = valores[1].strip() if len(valores) > 1 else ""
        if registro == b"0140":
            self.cadastro.abrir(valores)
            return
        if registro == b"0000":
            # o período é o mesmo em todas as linhas do arquivo, e quem lê o
            # 0000 é o domínio — nunca este módulo, por posição fixa. Ver
            # DECISOES de 22/09/2026: ele já mordeu duas vezes
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
            self.cnpj_c = primeiro
        elif registro == b"D010":
            self.cnpj_d = primeiro
        elif registro == b"F010":
            self.cnpj_f = primeiro
        elif registro == b"C100":
            self.c100, self.c100_e_entrada = valores, primeiro == ENTRADA
        elif registro == b"C170" and self.c100_e_entrada:
            yield self._do_c170(valores)
        elif registro == b"C500":
            self.c500, self.c501 = valores, None
        elif registro == b"C501":
            self.c501 = valores
        elif registro == b"C505" and self.c501 is not None:
            yield self._do_c505(valores)
            self.c501 = None
        elif registro == b"D100":
            self.d100, self.d101 = valores, None
        elif registro == b"D101":
            self.d101 = valores
        elif registro == b"D105" and self.d101 is not None:
            if len(self.d100) > 1 and self.d100[1].strip() == ENTRADA:
                yield self._do_d105(valores)
            self.d101 = None
        elif registro == b"D500":
            self.d500, self.d501 = valores, None
        elif registro == b"D501":
            self.d501 = valores
        elif registro == b"D505" and self.d501 is not None:
            if len(self.d500) > 1 and self.d500[1].strip() == ENTRADA:
                yield self._do_d505(valores)
            self.d501 = None
        elif registro == b"C190":
            yield from self.fechar_c190()
            self.c190, self.c191, self.c195 = valores, [], []
        elif registro == b"C191":
            self.c191.append(valores)
        elif registro == b"C195":
            self.c195.append(valores)
        elif registro == b"F100" and primeiro == ENTRADA:
            yield self._do_f100(valores)
        elif registro == b"F120":
            yield self._do_f120(valores)
        elif registro == b"F130":
            yield self._do_f130(valores)

    def fechar_c190(self) -> Iterator[LinhaDeEntrada]:
        """Pareia C191[i] com C195[i]. Par incompleto fica de fora."""
        for pis, cofins in zip(self.c191, self.c195):
            yield self._do_c190(pis, cofins)

    # ---------- um método por ramo ----------
    def _do_c170(self, valores: list[str]) -> LinhaDeEntrada:
        nota = _nomeados("C100", self.c100)
        item = _nomeados("C170", valores)
        cadastro = self._item(item["C170_COD_ITEM"], self.cnpj_c)
        conta, nome_da_conta = self._conta(item["C170_COD_CTA"], self.cnpj_c)
        participante = nota["C100_COD_PART"]
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_c, periodo=self.periodo, registros=RAMO_C100,
            modelo=nota["C100_COD_MOD"], situacao=nota["C100_COD_SIT"],
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_c),
            numero_do_documento=nota["C100_NUM_DOC"], serie=nota["C100_SER"],
            chave=nota["C100_CHV_NFE"], data_do_documento=_dia(nota["C100_DT_DOC"]),
            data_de_entrada=_dia(nota["C100_DT_E_S"]),
            valor_do_documento=_dinheiro(nota["C100_VL_DOC"]),
            desconto_do_documento=_dinheiro(nota["C100_VL_DESC"]),
            valor_da_mercadoria=_dinheiro(nota["C100_VL_MERC"]),
            frete=_dinheiro(nota["C100_VL_FRT"]),
            numero_do_item=item["C170_NUM_ITEM"], codigo_do_item=item["C170_COD_ITEM"],
            descricao_complementar=item["C170_DESCR_COMPL"],
            descricao_do_item=cadastro["descricao"], ncm=cadastro["ncm"],
            codigo_de_barra=cadastro["barra"], tipo_do_item=_rotulo_do_tipo(cadastro["tipo"]),
            valor_do_item=_dinheiro(item["C170_VL_ITEM"]),
            quantidade=_quantidade(item["C170_QTD"]), unidade=item["C170_UNID"],
            desconto_do_item=_dinheiro(item["C170_VL_DESC"]),
            # o C170 não tem campo de natureza do crédito: ela é deduzida do CFOP
            natureza_do_credito=_natureza_deduzida(item["C170_CFOP"], cadastro["tipo"]),
            cfop=item["C170_CFOP"], descricao_do_cfop=tab_cfop.descricao(item["C170_CFOP"]),
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
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(item["C170_CST_PIS"],
                                                         item["C170_VL_PIS"]),
            **self._participante(participante, self.cnpj_c)))

    def _do_c505(self, valores: list[str]) -> LinhaDeEntrada:
        """Energia, água e gás. O C500 é sempre entrada — não tem IND_OPER."""
        doc = _nomeados("C500", self.c500)
        pis = _nomeados("C501", self.c501 or [])
        cofins = _nomeados("C505", valores)
        conta, nome_da_conta = self._conta(pis["C501_COD_CTA"], self.cnpj_c)
        participante = doc["C500_COD_PART"]
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_c, periodo=self.periodo, registros=RAMO_C500,
            modelo=doc["C500_COD_MOD"], situacao=doc["C500_COD_SIT"],
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_c),
            numero_do_documento=doc["C500_NUM_DOC"], serie=doc["C500_SER"],
            chave=doc["C500_CHV_DOCe"], data_do_documento=_dia(doc["C500_DT_DOC"]),
            data_de_entrada=_dia(doc["C500_DT_ENT"]),
            valor_do_documento=_dinheiro(doc["C500_VL_DOC"]),
            valor_do_item=_dinheiro(pis["C501_VL_ITEM"]),
            natureza_do_credito=_rotulo_da_natureza(pis["C501_NAT_BC_CRED"]),
            icms=_dinheiro(doc["C500_VL_ICMS"]),
            cst_pis=pis["C501_CST_PIS"], base_do_pis=_dinheiro(pis["C501_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(pis["C501_ALIQ_PIS"]), pis=_dinheiro(pis["C501_VL_PIS"]),
            cst_cofins=cofins["C505_CST_COFINS"],
            base_da_cofins=_dinheiro(cofins["C505_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(cofins["C505_ALIQ_COFINS"]),
            cofins=_dinheiro(cofins["C505_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(pis["C501_CST_PIS"],
                                                         pis["C501_VL_PIS"]),
            **self._participante(participante, self.cnpj_c)))

    def _do_c190(self, filho_pis: list[str], filho_cofins: list[str]) -> LinhaDeEntrada:
        """Consolidação de NF-e. Sempre entrada."""
        grupo = _nomeados("C190", self.c190)
        pis = _nomeados("C191", filho_pis)
        cofins = _nomeados("C195", filho_cofins)
        cadastro = self._item(grupo["C190_COD_ITEM"], self.cnpj_c)
        conta, nome_da_conta = self._conta(pis["C191_COD_CTA"], self.cnpj_c)
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_c, periodo=self.periodo, registros=RAMO_C190,
            modelo=grupo["C190_COD_MOD"],
            # aqui o COD_PART é o CNPJ direto, sem cadastro no 0150 — por isso
            # não há nome nem código curto, e a UF é só a do estabelecimento
            cnpj_do_participante=pis["C191_COD_PART"],
            uf_origem_destino=self._uf_do_estabelecimento(self.cnpj_c),
            data_do_documento=_dia(grupo["C190_DT_INI"]),
            # a referência usa DT_INI nos dois campos: o C190 agrega um intervalo
            # de dias, não um documento, e o DT_FIN pode divergir
            data_de_entrada=_dia(grupo["C190_DT_INI"]),
            valor_da_mercadoria=_dinheiro(grupo["C190_VL_TOT_ITEM"]),
            codigo_do_item=grupo["C190_COD_ITEM"], descricao_do_item=cadastro["descricao"],
            ncm=cadastro["ncm"] or grupo["C190_COD_NCM"], codigo_de_barra=cadastro["barra"],
            tipo_do_item=_rotulo_do_tipo(cadastro["tipo"]),
            valor_do_item=_dinheiro(pis["C191_VL_ITEM"]),
            desconto_do_item=_dinheiro(pis["C191_VL_DESC"]),
            natureza_do_credito=_natureza_deduzida(pis["C191_CFOP"], cadastro["tipo"]),
            cfop=pis["C191_CFOP"], descricao_do_cfop=tab_cfop.descricao(pis["C191_CFOP"]),
            cst_pis=pis["C191_CST_PIS"], base_do_pis=_dinheiro(pis["C191_VL_BC_PIS"]),
            quantidade_base_do_pis=pis["C191_QUANT_BC_PIS"],
            aliquota_do_pis=_aliquota(pis["C191_ALIQ_PIS_PERC"]),
            quantidade_aliquota_do_pis=pis["C191_ALIQ_PIS_QUANT"],
            pis=_dinheiro(pis["C191_VL_PIS"]),
            cst_cofins=cofins["C195_CST_COFINS"],
            base_da_cofins=_dinheiro(cofins["C195_VL_BC_COFINS"]),
            quantidade_base_da_cofins=cofins["C195_QUANT_BC_COFINS"],
            aliquota_da_cofins=_aliquota(cofins["C195_ALIQ_COFINS_PERC"]),
            quantidade_aliquota_da_cofins=cofins["C195_ALIQ_COFINS_QUANT"],
            cofins=_dinheiro(cofins["C195_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(pis["C191_CST_PIS"],
                                                         pis["C191_VL_PIS"])))

    def _do_d105(self, valores: list[str]) -> LinhaDeEntrada:
        """Serviço de transporte. O CNPJ é o do D010, não o do C010."""
        doc = _nomeados("D100", self.d100)
        pis = _nomeados("D101", self.d101 or [])
        cofins = _nomeados("D105", valores)
        conta, nome_da_conta = self._conta(pis["D101_COD_CTA"], self.cnpj_d)
        participante = doc["D100_COD_PART"]
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_d, periodo=self.periodo, registros=RAMO_D100,
            modelo=doc["D100_COD_MOD"], situacao=doc["D100_COD_SIT"],
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_d),
            numero_do_documento=doc["D100_NUM_DOC"], serie=doc["D100_SER"],
            chave=doc["D100_CHV_CTE"], data_do_documento=_dia(doc["D100_DT_DOC"]),
            data_de_entrada=_dia(doc["D100_DT_A_P"]),
            valor_do_documento=_dinheiro(doc["D100_VL_DOC"]),
            desconto_do_documento=_dinheiro(doc["D100_VL_DESC"]),
            valor_da_mercadoria=_dinheiro(doc["D100_VL_SERV"]),
            valor_do_item=_dinheiro(pis["D101_VL_ITEM"]),
            natureza_do_credito=_rotulo_da_natureza(pis["D101_NAT_BC_CRED"]),
            icms=_dinheiro(doc["D100_VL_ICMS"]),
            cst_pis=pis["D101_CST_PIS"], base_do_pis=_dinheiro(pis["D101_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(pis["D101_ALIQ_PIS"]), pis=_dinheiro(pis["D101_VL_PIS"]),
            cst_cofins=cofins["D105_CST_COFINS"],
            base_da_cofins=_dinheiro(cofins["D105_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(cofins["D105_ALIQ_COFINS"]),
            cofins=_dinheiro(cofins["D105_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(pis["D101_CST_PIS"],
                                                         pis["D101_VL_PIS"]),
            **self._participante(participante, self.cnpj_d)))

    def _do_d505(self, valores: list[str]) -> LinhaDeEntrada:
        """Serviço de comunicação. Também do D010."""
        doc = _nomeados("D500", self.d500)
        pis = _nomeados("D501", self.d501 or [])
        cofins = _nomeados("D505", valores)
        conta, nome_da_conta = self._conta(pis["D501_COD_CTA"], self.cnpj_d)
        participante = doc["D500_COD_PART"]
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_d, periodo=self.periodo, registros=RAMO_D500,
            modelo=doc["D500_COD_MOD"], situacao=doc["D500_COD_SIT"],
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_d),
            numero_do_documento=doc["D500_NUM_DOC"], serie=doc["D500_SER"],
            data_do_documento=_dia(doc["D500_DT_DOC"]),
            data_de_entrada=_dia(doc["D500_DT_A_P"]),
            valor_do_documento=_dinheiro(doc["D500_VL_DOC"]),
            desconto_do_documento=_dinheiro(doc["D500_VL_DESC"]),
            valor_da_mercadoria=_dinheiro(doc["D500_VL_SERV"]),
            # não há nota de mercadoria aqui, logo não há frete: a referência
            # real traz "0,00" fixo neste ramo
            frete="0,00",
            valor_do_item=_dinheiro(pis["D501_VL_ITEM"]),
            natureza_do_credito=_rotulo_da_natureza(pis["D501_NAT_BC_CRED"]),
            icms=_dinheiro(doc["D500_VL_ICMS"]),
            cst_pis=pis["D501_CST_PIS"], base_do_pis=_dinheiro(pis["D501_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(pis["D501_ALIQ_PIS"]), pis=_dinheiro(pis["D501_VL_PIS"]),
            cst_cofins=cofins["D505_CST_COFINS"],
            base_da_cofins=_dinheiro(cofins["D505_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(cofins["D505_ALIQ_COFINS"]),
            cofins=_dinheiro(cofins["D505_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(pis["D501_CST_PIS"],
                                                         pis["D501_VL_PIS"]),
            **self._participante(participante, self.cnpj_d)))

    def _do_f100(self, valores: list[str]) -> LinhaDeEntrada:
        """Demais documentos e operações. O CNPJ é o do F010."""
        d = _nomeados("F100", valores)
        cadastro = self._item(d["F100_COD_ITEM"], self.cnpj_f)
        conta, nome_da_conta = self._conta(d["F100_COD_CTA"], self.cnpj_f)
        participante = d["F100_COD_PART"]
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_f, periodo=self.periodo, registros=RAMO_F100,
            uf_origem_destino=self._uf_origem_destino(participante, self.cnpj_f),
            data_do_documento=_dia(d["F100_DT_OPER"]),
            valor_do_documento=_dinheiro(d["F100_VL_OPER"]),
            valor_da_mercadoria=_dinheiro(d["F100_VL_OPER"]),
            codigo_do_item=d["F100_COD_ITEM"], descricao_do_item=cadastro["descricao"],
            ncm=cadastro["ncm"], codigo_de_barra=cadastro["barra"],
            tipo_do_item=_rotulo_do_tipo(cadastro["tipo"]),
            valor_do_item=_dinheiro(d["F100_VL_OPER"]),
            natureza_do_credito=_rotulo_da_natureza(d["F100_NAT_BC_CRED"]),
            cst_pis=d["F100_CST_PIS"], base_do_pis=_dinheiro(d["F100_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(d["F100_ALIQ_PIS"]), pis=_dinheiro(d["F100_VL_PIS"]),
            cst_cofins=d["F100_CST_COFINS"],
            base_da_cofins=_dinheiro(d["F100_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(d["F100_ALIQ_COFINS"]),
            cofins=_dinheiro(d["F100_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(d["F100_CST_PIS"], d["F100_VL_PIS"]),
            **self._participante(participante, self.cnpj_f)))

    def _do_f120(self, valores: list[str]) -> LinhaDeEntrada:
        """Ativo imobilizado — depreciação. Registro único, sem filhos."""
        d = _nomeados("F120", valores)
        conta, nome_da_conta = self._conta(d["F120_COD_CTA"], self.cnpj_f)
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_f, periodo=self.periodo, registros=RAMO_F120,
            uf_origem_destino=self._uf_do_estabelecimento(self.cnpj_f),
            descricao_complementar=d["F120_DESC_BEM_IMOB"],
            valor_do_documento=_dinheiro(d["F120_VL_OPER_DEP"]),
            # o F120 não distingue documento de item: a mesma origem preenche os
            # dois campos de desconto, como no arquivo de referência
            desconto_do_documento=_dinheiro(d["F120_PARC_OPER_NAO_BC_CRED"]),
            valor_do_item=_dinheiro(d["F120_VL_OPER_DEP"]),
            desconto_do_item=_dinheiro(d["F120_PARC_OPER_NAO_BC_CRED"]),
            natureza_do_credito=_rotulo_da_natureza(d["F120_NAT_BC_CRED"]),
            cst_pis=d["F120_CST_PIS"], base_do_pis=_dinheiro(d["F120_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(d["F120_ALIQ_PIS"]), pis=_dinheiro(d["F120_VL_PIS"]),
            cst_cofins=d["F120_CST_COFINS"],
            base_da_cofins=_dinheiro(d["F120_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(d["F120_ALIQ_COFINS"]),
            cofins=_dinheiro(d["F120_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(d["F120_CST_PIS"], d["F120_VL_PIS"])))

    def _do_f130(self, valores: list[str]) -> LinhaDeEntrada:
        """Ativo imobilizado — aquisição. Registro único, sem filhos."""
        d = _nomeados("F130", valores)
        conta, nome_da_conta = self._conta(d["F130_COD_CTA"], self.cnpj_f)
        return self._emitir(LinhaDeEntrada(
            cnpj=self.cnpj_f, periodo=self.periodo, registros=RAMO_F130,
            uf_origem_destino=self._uf_do_estabelecimento(self.cnpj_f),
            codigo_do_item=d["F130_IDENT_BEM_IMOB"],
            descricao_complementar=d["F130_DESC_BEM_IMOB"],
            valor_do_documento=_dinheiro(d["F130_VL_OPER_AQUIS"]),
            desconto_do_documento=_dinheiro(d["F130_PARC_OPER_NAO_BC_CRED"]),
            valor_do_item=_dinheiro(d["F130_VL_BC_CRED"]),
            desconto_do_item=_dinheiro(d["F130_PARC_OPER_NAO_BC_CRED"]),
            natureza_do_credito=_rotulo_da_natureza(d["F130_NAT_BC_CRED"]),
            cst_pis=d["F130_CST_PIS"], base_do_pis=_dinheiro(d["F130_VL_BC_PIS"]),
            aliquota_do_pis=_aliquota(d["F130_ALIQ_PIS"]), pis=_dinheiro(d["F130_VL_PIS"]),
            cst_cofins=d["F130_CST_COFINS"],
            base_da_cofins=_dinheiro(d["F130_VL_BC_COFINS"]),
            aliquota_da_cofins=_aliquota(d["F130_ALIQ_COFINS"]),
            cofins=_dinheiro(d["F130_VL_COFINS"]),
            conta_contabil=conta, nome_da_conta=nome_da_conta,
            debito_ou_credito=_debito_ou_credito_suposto(d["F130_CST_PIS"], d["F130_VL_PIS"])))
