"""Pré-validação do arquivo digital da CAT 42. Puro, sem I/O.

Não temos as regras de crítica do validador da SEFAZ (PLANEJAMENTO, riscos).
O que existe são duas coisas, e as duas estão aqui:

1. **o leiaute**, campo a campo e na tabela de obrigatoriedade por natureza
   de operação (`arquivo_digital.LEIAUTE`);
2. **o que o Pós-Validador faz**: compor a Ficha 3 a partir das linhas do
   arquivo. Se o saldo que ele chega a não for o 1050 informado, o arquivo
   não se sustenta.

O segundo foi medido antes de virar regra. Dois arquivos que a IRMAOS BOA
transmitiu (8.062 e 6.924 itens), recompostos pelo mesmo `RazaoDoItem` do
sistema a partir do 1050 inicial e do 1100: **100% das quantidades fecham** e
99,99% dos valores ficam a até 5 centavos do ICMS_TOT_FIM — o resto é
arredondamento de linha a linha com 2 casas. Por isso quantidade que não fecha
é erro, e valor fora de 5 centavos é aviso, com a diferença dita.

Recebe as linhas em bytes, com o terminador: CRLF e Latin-1 são regra do
leiaute, e só dá para conferi-los antes de decodificar.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum

from cat.dominio.cat42.arquivo_digital import (
    CODIFICACAO,
    LEIAUTE,
    MODELOS_ELETRONICOS,
    ORDEM_DOS_REGISTROS,
    PAIS_BRASIL,
    Campo,
    Natureza,
)
from cat.dominio.cat42.razao import (
    EnquadramentoLegal,
    Especie,
    Movimento,
    MovimentoInvalido,
    RazaoDoItem,
    SaldoInicial,
)
from cat.dominio.comum.cnpj import CnpjInvalido, Cnpj

TOLERANCIA_DE_VALOR = Decimal("0.05")
TOLERANCIA_DE_QUANTIDADE = Decimal("0.0005")
# um arquivo quebrado pode ter uma ocorrência por linha; guardar 800 mil não
# ajuda ninguém. Conta-se tudo, e guardam-se os primeiros de cada regra
EXEMPLOS_POR_REGRA = 200

_RE_NUMERO = re.compile(r"^-?\d+(,\d+)?$")
_UFS_IBGE = frozenset({"11", "12", "13", "14", "15", "16", "17", "21", "22", "23", "24", "25", "26",
                       "27", "28", "29", "31", "32", "33", "35", "41", "42", "43", "50", "51", "52", "53"})
_PESOS_IE_SP_1 = (1, 3, 4, 5, 6, 7, 8, 10)
_PESOS_IE_SP_2 = (3, 2, 10, 9, 8, 7, 6, 5, 4, 3, 2)


class Severidade(str, Enum):
    ERRO = "erro"        # o arquivo não vai para a SEFAZ assim
    AVISO = "aviso"      # vai, mas alguém precisa olhar


class Regra(Enum):
    """Cada regra: (severidade, rótulo, o que fazer)."""

    LINHA_SEM_CRLF = (Severidade.ERRO, "Linha sem CR+LF no fim", "Gerar de novo: toda linha termina em CRLF.")
    REGISTRO_DESCONHECIDO = (Severidade.ERRO, "Registro que o leiaute não tem", "Tirar a linha ou corrigir o REG.")
    QUANTIDADE_DE_CAMPOS = (Severidade.ERRO, "Número de campos errado", "Todo campo vai, mesmo vazio (||).")
    ORDEM_DOS_REGISTROS = (Severidade.ERRO, "Registros fora de ordem", "Agrupar por tipo: 0000, 0150, 0200, 1050, 1100, 1200.")
    ABERTURA = (Severidade.ERRO, "0000 ausente, repetido ou fora do início", "Um 0000, na primeira linha.")
    CAMPO_OBRIGATORIO = (Severidade.ERRO, "Campo obrigatório vazio", "Preencher o campo.")
    TIPO_DO_CAMPO = (Severidade.ERRO, "Campo com formato inválido", "Número com vírgula decimal, sem milhar e sem sinal; casas do leiaute.")
    TAMANHO_DO_CAMPO = (Severidade.ERRO, "Campo maior que o leiaute ou fora do tamanho exato", "Conferir o tamanho na tabela do registro.")
    VALOR_NEGATIVO = (Severidade.ERRO, "Valor ou quantidade negativa", "O arquivo não leva sinal: o Pós-Validador põe o da devolução.")
    PERIODO = (Severidade.ERRO, "Período inválido", "PERIODO é mmaaaa, com mês de 01 a 12.")
    CNPJ = (Severidade.ERRO, "CNPJ com dígito verificador errado", "Conferir o CNPJ no cadastro.")
    CPF = (Severidade.ERRO, "CPF com dígito verificador errado", "Conferir o CPF no cadastro de participantes.")
    INSCRICAO_ESTADUAL = (Severidade.ERRO, "Inscrição estadual de SP com dígito errado", "Conferir a IE no cadastro.")
    MUNICIPIO = (Severidade.ERRO, "Código de município inválido", "Sete dígitos do IBGE, começando pela UF.")
    VERSAO_OU_FINALIDADE = (Severidade.ERRO, "Versão do leiaute ou finalidade inválida", "COD_VER 01; COD_FIN 00, 01 ou 02.")
    PARTICIPANTE_REPETIDO = (Severidade.ERRO, "COD_PART repetido no 0150", "Um código por participante.")
    PARTICIPANTE_SEM_DOCUMENTO = (Severidade.ERRO, "Participante do Brasil sem CNPJ nem CPF, ou com os dois", "Um dos dois, nunca ambos.")
    PARTICIPANTE_INEXISTENTE = (Severidade.ERRO, "COD_PART do 1200 que não está no 0150", "Incluir o participante no 0150.")
    SEM_O_ESTABELECIMENTO = (Severidade.AVISO, "O próprio estabelecimento não está no 0150", "O manual pede o estabelecimento entre os participantes.")
    ITEM_REPETIDO = (Severidade.ERRO, "COD_ITEM repetido no 0200 ou no 1050", "Um registro por código.")
    ITEM_INEXISTENTE = (Severidade.ERRO, "Código de item que não está no 0200", "Todo item citado precisa do 0200.")
    ITEM_SEM_SALDO = (Severidade.ERRO, "Item com movimento e sem 1050", "Sem saldo inicial não se compõe a Ficha 3.")
    ITEM_SEM_USO = (Severidade.AVISO, "Item do 0200 que nenhum registro cita", "O manual pede só os itens referenciados.")
    CHAVE = (Severidade.ERRO, "Chave de acesso inválida", "44 dígitos com o dígito verificador certo.")
    MODELO_DA_CHAVE = (Severidade.AVISO, "Chave de modelo que não é NF-e, NFC-e nem CF-e SAT", "Documento não eletrônico vai no 1200.")
    MODELO_DO_1200 = (Severidade.ERRO, "Documento eletrônico no 1200", "NF-e, NFC-e e CF-e SAT vão no 1100, pela chave.")
    DATA = (Severidade.ERRO, "Data inválida ou fora do período", "ddmmaaaa, dentro do mês do 0000.")
    ITEM_DO_DOCUMENTO = (Severidade.ERRO, "Nº do item fora de 1 a 999", "O nº sequencial do item no documento.")
    ITEM_DO_DOCUMENTO_REPETIDO = (Severidade.ERRO, "Linha repetida: mesmo documento, nº do item e código", "A mesma operação lançada duas vezes.")
    # num arquivo que a BOA transmitiu, 3 itens de nota aparecem com dois códigos
    # (kit desmembrado, provavelmente): aceito pela SEFAZ, então é aviso
    ITEM_DO_DOCUMENTO_COM_DOIS_CODIGOS = (Severidade.AVISO, "Mesmo documento e nº do item com dois códigos", "Conferir se o item foi desmembrado de propósito.")
    INDICADOR = (Severidade.ERRO, "IND_OPER diferente de 0 e 1", "0 entrada, 1 saída.")
    CFOP_E_INDICADOR = (Severidade.ERRO, "CFOP que não combina com o indicador", "Entrada começa por 1, 2 ou 3; saída por 5, 6 ou 7.")
    ICMS_TOT = (Severidade.ERRO, "ICMS_TOT onde a natureza não admite, ou faltando onde exige", "Entradas e devoluções levam; saída não.")
    COD_LEGAL = (Severidade.ERRO, "COD_LEGAL onde a natureza não admite, ou faltando onde exige", "Saída e devolução de saída levam 0 a 4; entradas não.")
    VL_CONFR = (Severidade.ERRO, "VL_CONFR onde não cabe, ou faltando com COD_LEGAL de 1 a 4", "Só com COD_LEGAL de 1 a 4.")
    SALDO_EM_QUANTIDADE = (Severidade.ERRO, "Ficha 3 recomposta não chega ao QTD_FIM do 1050", "Falta ou sobra movimento do item no mês.")
    SALDO_EM_VALOR = (Severidade.AVISO, "Ficha 3 recomposta passa de 5 centavos do ICMS_TOT_FIM", "Conferir o custo médio do item.")
    SALDO_NEGATIVO = (Severidade.ERRO, "Estoque negativo na Ficha 3 recomposta", "Saída sem estoque: falta entrada ou abertura.")
    # só se confere com vários meses juntos: a pré-validação do cliente
    SALDO_INICIAL_DIFERENTE_DO_ANTERIOR = (Severidade.AVISO, "Saldo inicial diferente do final da última competência do item",
                                           "Conferir se falta arquivo entre os dois meses ou se o estoque foi ajustado por fora.")

    @property
    def severidade(self) -> Severidade:
        return self.value[0]

    @property
    def rotulo(self) -> str:
        return self.value[1]

    @property
    def o_que_fazer(self) -> str:
        return self.value[2]

    @property
    def codigo(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Ocorrencia:
    regra: Regra
    linha: int | None
    registro: str
    campo: str
    mensagem: str
    item: str = ""


@dataclass
class Validacao:
    """O resultado: contagens de tudo, exemplos do começo de cada regra."""

    linhas: int = 0
    por_registro: dict[str, int] = field(default_factory=dict)
    por_regra: dict[Regra, int] = field(default_factory=dict)
    exemplos: list[Ocorrencia] = field(default_factory=list)
    cnpj: str = ""
    periodo: str = ""
    itens_recompostos: int = 0
    itens_que_fecham: int = 0
    maior_diferenca_de_valor: Decimal = Decimal(0)
    # o 1050 de cada item (qtd e ICMS no início e no fim): é o que a conferência
    # entre meses precisa, e só existe depois de ler o arquivo inteiro
    saldos: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = field(default_factory=dict)

    def anotar(self, regra: Regra, linha: int | None, registro: str, campo: str, mensagem: str,
               item: str = "") -> None:
        n = self.por_regra.get(regra, 0) + 1
        self.por_regra[regra] = n
        if n <= EXEMPLOS_POR_REGRA:
            self.exemplos.append(Ocorrencia(regra, linha, registro, campo, mensagem, item))

    @property
    def erros(self) -> int:
        return sum(n for r, n in self.por_regra.items() if r.severidade is Severidade.ERRO)

    @property
    def avisos(self) -> int:
        return sum(n for r, n in self.por_regra.items() if r.severidade is Severidade.AVISO)

    @property
    def passou(self) -> bool:
        return self.erros == 0


# ---------------------------------------------------------------------------
# dígitos verificadores
# ---------------------------------------------------------------------------
def cpf_valido(cpf: str) -> bool:
    if len(cpf) != 11 or not cpf.isdigit() or len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[tamanho]):
            return False
    return True


def ie_sp_valida(ie: str) -> bool:
    """IE de comércio e indústria de SP: 12 dígitos, verificadores na 9ª e na 12ª."""
    if len(ie) != 12 or not ie.isdigit():
        return False
    d1 = sum(int(ie[i]) * p for i, p in enumerate(_PESOS_IE_SP_1)) % 11 % 10
    d2 = sum(int(ie[i]) * p for i, p in enumerate(_PESOS_IE_SP_2)) % 11 % 10
    return int(ie[8]) == d1 and int(ie[11]) == d2


def chave_valida(chave: str) -> bool:
    if len(chave) != 44 or not chave.isdigit():
        return False
    soma = sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(chave[:43])))
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return dv == int(chave[43])


def _decimal(valor: str) -> Decimal | None:
    if not valor:
        return None
    try:
        return Decimal(valor.replace(",", "."))
    except InvalidOperation:
        return None


def _data(valor: str) -> date | None:
    if len(valor) != 8 or not valor.isdigit():
        return None
    try:
        return date(int(valor[4:]), int(valor[2:4]), int(valor[:2]))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# a leitura
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Lancamento:
    linha: int
    data: date
    natureza: Natureza
    quantidade: Decimal
    icms_tot: Decimal | None
    vl_confr: Decimal | None
    cod_legal: int | None
    cfop: str


class _Leitor:
    def __init__(self) -> None:
        self.v = Validacao()
        self.ordem_atual = -1
        self.aberturas = 0
        self.ano_mes: tuple[int, int] | None = None
        self.cnpj = ""
        self.cod_mun_estab = ""
        self.participantes: set[str] = set()
        self.docs_participantes: set[str] = set()
        self.itens: set[str] = set()
        self.saldos: dict[str, tuple[Decimal, Decimal, Decimal, Decimal, int]] = {}
        self.citados: set[str] = set()
        self.documentos: dict[tuple[str, str], set[str]] = {}
        self.lancamentos: dict[str, list[_Lancamento]] = defaultdict(list)
        self.ultimo_registro = ""

    # --- estrutura -----------------------------------------------------
    def ler(self, numero: int, bruto: bytes) -> None:
        v = self.v
        if not bruto.endswith(b"\r\n"):
            # a última linha sem terminador ainda é linha, e ainda é erro
            v.anotar(Regra.LINHA_SEM_CRLF, numero, "", "", "A linha não termina em CR+LF.")
        conteudo = bruto.rstrip(b"\r\n")
        if not conteudo:
            return
        v.linhas += 1
        campos = conteudo.decode(CODIFICACAO).split("|")
        reg = campos[0]
        leiaute = LEIAUTE.get(reg)
        if leiaute is None:
            v.anotar(Regra.REGISTRO_DESCONHECIDO, numero, reg[:8], "REG", f"REG '{reg[:8]}' não existe no leiaute.")
            return
        v.por_registro[reg] = v.por_registro.get(reg, 0) + 1

        ordem = ORDEM_DOS_REGISTROS[reg]
        if ordem < self.ordem_atual:
            v.anotar(Regra.ORDEM_DOS_REGISTROS, numero, reg, "REG",
                     f"{reg} depois de registro de bloco posterior ({self.ultimo_registro}).")
        if reg == "0205" and self.ultimo_registro not in ("0200", "0205"):
            v.anotar(Regra.ORDEM_DOS_REGISTROS, numero, reg, "REG", "0205 fora de baixo do seu 0200.")
        self.ordem_atual = max(self.ordem_atual, ordem)
        self.ultimo_registro = reg

        if len(campos) != len(leiaute):
            v.anotar(Regra.QUANTIDADE_DE_CAMPOS, numero, reg, "",
                     f"{reg} com {len(campos)} campos; o leiaute tem {len(leiaute)}.")
            return
        valores = {c.nome: bruto_ for c, bruto_ in zip(leiaute, campos)}
        for campo, valor in zip(leiaute, campos):
            self._campo(numero, reg, campo, valor)
        getattr(self, f"_r{reg}")(numero, valores)

    def _campo(self, numero: int, reg: str, c: Campo, valor: str) -> None:
        v = self.v
        if not valor:
            if c.obrigatorio:
                v.anotar(Regra.CAMPO_OBRIGATORIO, numero, reg, c.nome, f"{c.nome} vazio.")
            return
        if c.tipo == "N":
            if c.nome == "CNPJ":
                return  # CNPJ alfanumérico existe desde 07/2026: a regra própria confere
            if c.nome == "CHV_DOC" and valor == "0":
                return  # fato gerador presumido não realizado sem documento
            if not _RE_NUMERO.match(valor):
                v.anotar(Regra.TIPO_DO_CAMPO, numero, reg, c.nome, f"{c.nome} '{valor[:30]}' não é número.")
                return
            if valor.startswith("-"):
                v.anotar(Regra.VALOR_NEGATIVO, numero, reg, c.nome, f"{c.nome} negativo: {valor}.")
            inteiro, _, casas = valor.lstrip("-").partition(",")
            if c.decimais is None and casas:
                v.anotar(Regra.TIPO_DO_CAMPO, numero, reg, c.nome, f"{c.nome} '{valor}' não leva casas decimais.")
            elif c.decimais is not None and len(casas) > c.decimais:
                v.anotar(Regra.TIPO_DO_CAMPO, numero, reg, c.nome,
                         f"{c.nome} '{valor}' passa de {c.decimais} casas decimais.")
            tamanho = len(inteiro)
        else:
            tamanho = len(valor)
        if (c.exato and tamanho != c.tamanho) or tamanho > c.maximo:
            v.anotar(Regra.TAMANHO_DO_CAMPO, numero, reg, c.nome,
                     f"{c.nome} com {tamanho} caracteres; o leiaute pede "
                     f"{'exatamente ' if c.exato else 'até '}{c.maximo}.")

    # --- registro a registro ---------------------------------------------
    def _r0000(self, numero: int, c: dict) -> None:
        v = self.v
        self.aberturas += 1
        if self.aberturas > 1 or v.linhas != 1:
            v.anotar(Regra.ABERTURA, numero, "0000", "REG", "0000 repetido ou fora da primeira linha.")
        p = c["PERIODO"]
        if len(p) == 6 and p.isdigit() and 1 <= int(p[:2]) <= 12:
            self.ano_mes = (int(p[2:]), int(p[:2]))
            v.periodo = p
        else:
            v.anotar(Regra.PERIODO, numero, "0000", "PERIODO", f"PERIODO '{p}' não é mmaaaa.")
        self.cnpj = c["CNPJ"]
        v.cnpj = self.cnpj
        self._cnpj(numero, "0000", self.cnpj)
        self.cod_mun_estab = c["COD_MUN"]
        self._municipio(numero, "0000", c["COD_MUN"])
        self._ie(numero, "0000", c["IE"], c["COD_MUN"])
        if c["COD_VER"] != "01" or c["COD_FIN"] not in ("00", "01", "02"):
            v.anotar(Regra.VERSAO_OU_FINALIDADE, numero, "0000", "COD_VER",
                     f"COD_VER '{c['COD_VER']}', COD_FIN '{c['COD_FIN']}'.")

    def _r0150(self, numero: int, c: dict) -> None:
        v = self.v
        codigo = c["COD_PART"]
        if codigo in self.participantes:
            v.anotar(Regra.PARTICIPANTE_REPETIDO, numero, "0150", "COD_PART", f"COD_PART '{codigo}' repetido.")
        self.participantes.add(codigo)
        cnpj, cpf = c["CNPJ"], c["CPF"]
        if cnpj:
            self.docs_participantes.add(cnpj)
        brasil = c["COD_PAIS"].lstrip("0") in ("", PAIS_BRASIL)
        if brasil and bool(cnpj) == bool(cpf):
            v.anotar(Regra.PARTICIPANTE_SEM_DOCUMENTO, numero, "0150", "CNPJ",
                     f"Participante '{codigo}' com {'os dois' if cnpj else 'nenhum dos dois'}.")
        if cnpj:
            self._cnpj(numero, "0150", cnpj)
        if cpf and not cpf_valido(cpf):
            v.anotar(Regra.CPF, numero, "0150", "CPF", f"CPF {cpf} do participante '{codigo}'.")
        if brasil:
            if not c["COD_MUN"]:
                v.anotar(Regra.CAMPO_OBRIGATORIO, numero, "0150", "COD_MUN", f"Participante '{codigo}' do Brasil sem município.")
            else:
                self._municipio(numero, "0150", c["COD_MUN"])
                self._ie(numero, "0150", c["IE"], c["COD_MUN"])

    def _r0200(self, numero: int, c: dict) -> None:
        codigo = c["COD_ITEM"]
        if codigo in self.itens:
            self.v.anotar(Regra.ITEM_REPETIDO, numero, "0200", "COD_ITEM", f"Item '{codigo}' repetido.", codigo)
        self.itens.add(codigo)
        if not c["COD_NCM"].isdigit() or len(c["COD_NCM"]) != 8:
            self.v.anotar(Regra.TIPO_DO_CAMPO, numero, "0200", "COD_NCM", f"NCM '{c['COD_NCM']}' não tem 8 dígitos.", codigo)

    def _r0205(self, numero: int, c: dict) -> None:
        self.citados.add(c["COD_ITEM"])

    def _r1050(self, numero: int, c: dict) -> None:
        codigo = c["COD_ITEM"]
        self._item_existe(numero, "1050", codigo)
        if codigo in self.saldos:
            self.v.anotar(Regra.ITEM_REPETIDO, numero, "1050", "COD_ITEM", f"Item '{codigo}' com dois 1050.", codigo)
            return
        valores = [_decimal(c[k]) for k in ("QTD_INI", "ICMS_TOT_INI", "QTD_FIM", "ICMS_TOT_FIM")]
        if any(x is None for x in valores):
            return
        self.saldos[codigo] = (*valores, numero)  # type: ignore[arg-type]

    def _r1100(self, numero: int, c: dict) -> None:
        v = self.v
        chave = c["CHV_DOC"]
        sem_documento = chave == "0"
        if not sem_documento:
            if not chave_valida(chave):
                v.anotar(Regra.CHAVE, numero, "1100", "CHV_DOC", f"Chave '{chave[:44]}' inválida.")
            elif chave[20:22] not in MODELOS_ELETRONICOS:
                v.anotar(Regra.MODELO_DA_CHAVE, numero, "1100", "CHV_DOC", f"Chave de modelo {chave[20:22]}.")
        self._operacao(numero, "1100", chave, c)

    def _r1200(self, numero: int, c: dict) -> None:
        v = self.v
        if c["COD_MOD"] in MODELOS_ELETRONICOS:
            v.anotar(Regra.MODELO_DO_1200, numero, "1200", "COD_MOD", f"Modelo {c['COD_MOD']} no 1200.")
        if c["COD_PART"]:
            if c["COD_PART"] not in self.participantes:
                v.anotar(Regra.PARTICIPANTE_INEXISTENTE, numero, "1200", "COD_PART",
                         f"COD_PART '{c['COD_PART']}' fora do 0150.")
        documento = "|".join((c["COD_PART"], c["COD_MOD"], c["SER"], c["NUM_DOC"]))
        self._operacao(numero, "1200", documento, c)

    def _operacao(self, numero: int, reg: str, documento: str, c: dict) -> None:
        v = self.v
        codigo = c["COD_ITEM"]
        self.citados.add(codigo)
        self._item_existe(numero, reg, codigo)

        d = _data(c["DATA"])
        if d is None or (self.ano_mes and (d.year, d.month) != self.ano_mes):
            v.anotar(Regra.DATA, numero, reg, "DATA", f"DATA '{c['DATA']}' inválida ou fora de {v.periodo}.", codigo)
        item = c["NUM_ITEM"]
        if not item.isdigit() or not 1 <= int(item) <= 999:
            v.anotar(Regra.ITEM_DO_DOCUMENTO, numero, reg, "NUM_ITEM", f"NUM_ITEM '{item}'.", codigo)
        elif documento != "0":
            ja = self.documentos.get((documento, item))
            if ja is None:
                self.documentos[(documento, item)] = {codigo}
            elif codigo in ja:
                v.anotar(Regra.ITEM_DO_DOCUMENTO_REPETIDO, numero, reg, "NUM_ITEM",
                         f"Documento {documento[-20:]} item {item} código '{codigo}' repetido.", codigo)
            else:
                ja.add(codigo)
                v.anotar(Regra.ITEM_DO_DOCUMENTO_COM_DOIS_CODIGOS, numero, reg, "NUM_ITEM",
                         f"Documento {documento[-20:]} item {item} com os códigos {', '.join(sorted(ja))}.", codigo)

        ind, cfop = c["IND_OPER"], c["CFOP"]
        if ind not in ("0", "1"):
            v.anotar(Regra.INDICADOR, numero, reg, "IND_OPER", f"IND_OPER '{ind}'.", codigo)
            return
        if cfop[:1] not in (("1", "2", "3") if ind == "0" else ("5", "6", "7")):
            v.anotar(Regra.CFOP_E_INDICADOR, numero, reg, "CFOP", f"CFOP {cfop} com IND_OPER {ind}.", codigo)
        natureza = Natureza.de(ind, cfop)

        icms, confr, legal = c["ICMS_TOT"], c["VL_CONFR"], c["COD_LEGAL"]
        if natureza.leva_icms_tot != bool(icms):
            # fato gerador não realizado sem documento: ICMS_TOT sempre vazio
            if not (documento == "0" and natureza is Natureza.SAIDA):
                v.anotar(Regra.ICMS_TOT, numero, reg, "ICMS_TOT",
                         f"{natureza.value.replace('_', ' ')} {'sem' if natureza.leva_icms_tot else 'com'} ICMS_TOT.", codigo)
        cod_legal: int | None = None
        if natureza.leva_cod_legal:
            if not legal:
                v.anotar(Regra.COD_LEGAL, numero, reg, "COD_LEGAL", f"{natureza.value.replace('_', ' ')} sem COD_LEGAL.", codigo)
            elif legal not in ("0", "1", "2", "3", "4"):
                v.anotar(Regra.COD_LEGAL, numero, reg, "COD_LEGAL", f"COD_LEGAL '{legal}'.", codigo)
            else:
                cod_legal = int(legal)
                if (cod_legal > 0) != bool(confr):
                    v.anotar(Regra.VL_CONFR, numero, reg, "VL_CONFR",
                             f"COD_LEGAL {cod_legal} {'sem' if cod_legal > 0 else 'com'} VL_CONFR.", codigo)
        else:
            if legal:
                v.anotar(Regra.COD_LEGAL, numero, reg, "COD_LEGAL", f"{natureza.value.replace('_', ' ')} com COD_LEGAL.", codigo)
            if confr:
                v.anotar(Regra.VL_CONFR, numero, reg, "VL_CONFR", f"{natureza.value.replace('_', ' ')} com VL_CONFR.", codigo)

        quantidade = _decimal(c["QTD"])
        if d is not None and quantidade is not None:
            self.lancamentos[codigo].append(_Lancamento(
                numero, d, natureza, abs(quantidade), _decimal(icms), _decimal(confr), cod_legal, cfop))

    # --- conferências de apoio ---------------------------------------------
    def _item_existe(self, numero: int, reg: str, codigo: str) -> None:
        if codigo and codigo not in self.itens:
            self.v.anotar(Regra.ITEM_INEXISTENTE, numero, reg, "COD_ITEM", f"Item '{codigo}' sem 0200.", codigo)

    def _cnpj(self, numero: int, reg: str, cnpj: str) -> None:
        try:
            Cnpj(cnpj)
        except CnpjInvalido:
            self.v.anotar(Regra.CNPJ, numero, reg, "CNPJ", f"CNPJ '{cnpj}'.")

    def _municipio(self, numero: int, reg: str, cod_mun: str) -> None:
        if len(cod_mun) != 7 or not cod_mun.isdigit() or cod_mun[:2] not in _UFS_IBGE:
            self.v.anotar(Regra.MUNICIPIO, numero, reg, "COD_MUN", f"COD_MUN '{cod_mun}'.")

    def _ie(self, numero: int, reg: str, ie: str, cod_mun: str) -> None:
        # só a de SP: é a UF da CAT 42, e a regra de cada estado é outra
        if cod_mun.startswith("35") and ie.isdigit() and len(ie) == 12 and not ie_sp_valida(ie):
            self.v.anotar(Regra.INSCRICAO_ESTADUAL, numero, reg, "IE", f"IE '{ie}'.")

    # --- o fim: o que só se sabe com o arquivo inteiro ---------------------
    def fechar(self, tolerancia_de_valor: Decimal) -> Validacao:
        v = self.v
        if self.aberturas == 0:
            v.anotar(Regra.ABERTURA, None, "0000", "REG", "O arquivo não tem 0000.")
        if self.cnpj and self.cnpj not in self.docs_participantes and v.por_registro.get("0150"):
            v.anotar(Regra.SEM_O_ESTABELECIMENTO, None, "0150", "CNPJ",
                     f"O CNPJ {self.cnpj} do 0000 não aparece no 0150.")
        for codigo in sorted(self.itens - self.citados - set(self.saldos)):
            v.anotar(Regra.ITEM_SEM_USO, None, "0200", "COD_ITEM", f"Item '{codigo}' sem 1050 nem movimento.", codigo)
        for codigo in sorted(set(self.lancamentos) - set(self.saldos)):
            v.anotar(Regra.ITEM_SEM_SALDO, self.lancamentos[codigo][0].linha, "1100", "COD_ITEM",
                     f"Item '{codigo}' movimentado sem 1050.", codigo)
        for codigo, (qi, vi, qf, vf, numero) in self.saldos.items():
            self._recompor(codigo, qi, vi, qf, vf, numero, tolerancia_de_valor)
            v.saldos[codigo] = (qi, vi, qf, vf)
        return v

    def _recompor(self, codigo: str, qi: Decimal, vi: Decimal, qf: Decimal, vf: Decimal, numero: int,
                  tolerancia: Decimal) -> None:
        """A Ficha 3 do item, pelo mesmo domínio que o sistema usa para calculá-la."""
        v = self.v
        razao = RazaoDoItem(codigo, SaldoInicial(qi, vi))
        for i, l in enumerate(self.lancamentos.get(codigo, [])):
            devolucao = l.natureza in (Natureza.DEVOLUCAO_DE_ENTRADA, Natureza.DEVOLUCAO_DE_SAIDA)
            entra = l.natureza in (Natureza.ENTRADA, Natureza.DEVOLUCAO_DE_ENTRADA)
            try:
                razao.lancar(Movimento(
                    data=l.data, especie=Especie.ENTRADA if entra else Especie.SAIDA,
                    quantidade=l.quantidade,
                    icms_suportado=(l.icms_tot or Decimal(0)) if entra else None,
                    enquadramento=EnquadramentoLegal(l.cod_legal or 0), icms_efetivo=l.vl_confr,
                    devolucao=devolucao, cfop=l.cfop, ordem_na_fonte=i))
            except MovimentoInvalido:
                continue
        linhas = razao.apurar()
        v.itens_recompostos += 1
        if any(ln.saldo_quantidade < 0 for ln in linhas):
            primeira = next(ln for ln in linhas if ln.saldo_quantidade < 0)
            v.anotar(Regra.SALDO_NEGATIVO, numero, "1050", "QTD_FIM",
                     f"Item '{codigo}' fica com {primeira.saldo_quantidade} em {primeira.data:%d/%m/%Y}.", codigo)
        q = linhas[-1].saldo_quantidade if linhas else qi
        valor = linhas[-1].saldo_valor if linhas else vi
        if abs(q - qf) > TOLERANCIA_DE_QUANTIDADE:
            v.anotar(Regra.SALDO_EM_QUANTIDADE, numero, "1050", "QTD_FIM",
                     f"Item '{codigo}': a ficha chega a {q.normalize():f} e o 1050 diz {qf.normalize():f}.", codigo)
            return
        diferenca = abs(valor - vf)
        v.maior_diferenca_de_valor = max(v.maior_diferenca_de_valor, diferenca)
        if diferenca > tolerancia:
            v.anotar(Regra.SALDO_EM_VALOR, numero, "1050", "ICMS_TOT_FIM",
                     f"Item '{codigo}': a ficha chega a {valor.quantize(Decimal('0.01'))} e o 1050 diz {vf} "
                     f"(diferença de {diferenca.quantize(Decimal('0.01'))}).", codigo)
            return
        v.itens_que_fecham += 1


def validar(linhas: Iterable[bytes], tolerancia_de_valor: Decimal = TOLERANCIA_DE_VALOR) -> Validacao:
    """Lê o arquivo inteiro, linha a linha, e devolve o que achou."""
    leitor = _Leitor()
    for numero, bruto in enumerate(linhas, 1):
        leitor.ler(numero, bruto)
    return leitor.fechar(tolerancia_de_valor)
