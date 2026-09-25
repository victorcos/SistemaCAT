"""O documento fiscal eletrônico lido do XML, item a item. Puro: bytes entram,
dados saem.

A EFD não traz o item de quase nenhuma saída: NF-e de emissão própria, NFC-e e
CF-e SAT vão à escrituração só com o analítico. Na IRMAOS BOA e no Amigão, o
item de saída não existe na EFD; na Advertising Operations, 92.928 NF-e de
saída própria em 24 meses, nenhum C170. O item está no XML, e é daqui que ele
passa a vir.

## Três leiautes, uma forma

* **NF-e e NFC-e** (modelos 55 e 65): `nfeProc/NFe/infNFe` ou `NFe/infNFe`
  solto, com `ide`, `emit`, `dest` e um `det` por item;
* **CF-e SAT** (modelo 59): `CFe/infCFe`, com a data em `aaaammdd` e a origem
  da mercadoria em `Orig`, com maiúscula;
* **o que não é documento de mercadoria** — evento de cancelamento, carta de
  correção, inutilização, CT-e — devolve `None`: não tem item, e não é erro. O
  CT-e cita as notas que transporta num `infNFe` próprio; por isso a NF-e só é
  reconhecida com o `infNFe` dentro de `NFe` (na Advertising, 72 mil CT-e eram
  lidos como nota sem chave antes desta regra).

## Quem comprou

`indFinal` = 1 diz que a NF-e é venda a consumidor final, e 0 que não é: é a
informação que o CFOP 5.102 e o 5.405 não carregam, e que decide entre o
enquadramento 1 e o 0. NFC-e e CF-e são de consumidor por definição.

## O que se lê do imposto

O grupo do ICMS muda de nome conforme o CST (`ICMS00`, `ICMS10`, `ICMS60`,
`ICMSSN500`...). Lê-se o que houver dentro dele, pelo nome do campo:

* destacado — `vBC`, `pICMS`, `vICMS`, `vBCST`, `pICMSST`, `vICMSST`, `vFCPST`;
* **efetivo do CST 60** (NT 2020.005) — `vBCEfet`, `pICMSEfet`, `vICMSEfet`: o
  próprio emitente diz qual seria o imposto da operação que a ST encerrou;
* **retido anteriormente** — `vBCSTRet`, `vICMSSubstituto`, `vICMSSTRet`,
  `vFCPSTRet`. É o "informado pelo fornecedor" da cascata do suportado: o CST
  60 não destaca nada, e a NF-e 4.0 diz ali quanto foi suportado antes.

O CST sai como na EFD: origem mais os dois dígitos (`060`), ou origem mais o
CSOSN do Simples (`0500`) — o domínio do suportado compara só os dois últimos.

Do PIS e do COFINS lê-se o CST, a base, a alíquota e o valor, com a mesma regra
do grupo que muda de nome (`PISAliq`, `PISOutr`, `COFINSNT`…). Não servem à CAT
42; servem à triagem do crédito outorgado, onde o CST do produto confirma ou
desmente o que a descrição diz.

## O protocolo

O `nfeProc` traz, depois da nota, o `protNFe` com o `cStat` da SEFAZ. Só 100
(autorizado) e 150 (autorizado fora de prazo) são operação que existe; 301, 302
e 303 são uso denegado — na Advertising, 16 notas, 15 delas contadas como não
escrituradas antes desta regra. A NF-e sem protocolo (o XML que o ERP gera antes
de transmitir) e o CF-e não têm `cStat`: valem, mas perdem para a cópia
autorizada da mesma chave.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

ZERO = Decimal(0)

# o que o XML escreve quando o produto não tem código de barras
_SEM_GTIN = frozenset({"", "SEM GTIN", "SEMGTIN"})

MODELO_CFE_SAT = "59"

# cStat do protocolo que diz que a nota existe: autorizado e autorizado fora de prazo
CSTAT_AUTORIZADOS = frozenset({"100", "150"})

# o protNFe fica no fim do nfeProc: estes bytes finais bastam para achá-lo
BYTES_DO_PROTOCOLO = 4096
_RE_CSTAT = re.compile(rb"<cStat>\s*(\d{3})\s*</cStat>")


class XmlIlegivel(ValueError):
    """O arquivo não é XML bem formado."""


@dataclass(frozen=True)
class ItemDoXml:
    numero: int
    codigo: str
    gtin: str
    descricao: str
    ncm: str
    cest: str
    cfop: str
    unidade: str
    quantidade: Decimal
    valor: Decimal
    # vUnCom, como o emitente declarou. Não é `valor / quantidade`: a NF-e
    # admite dez casas aqui, e a divisão inventaria um arredondamento
    valor_unitario: Decimal = ZERO
    desconto: Decimal = ZERO
    # o que o emitente cobrou além da mercadoria e que entra na base do ICMS
    frete: Decimal = ZERO
    seguro: Decimal = ZERO
    outras: Decimal = ZERO
    cst_icms: str = ""
    bc_icms: Decimal = ZERO
    aliq_icms: Decimal = ZERO
    valor_icms: Decimal = ZERO
    bc_st: Decimal = ZERO
    aliq_st: Decimal = ZERO
    valor_st: Decimal = ZERO
    fcp_st: Decimal = ZERO
    bc_st_retido: Decimal = ZERO
    valor_icms_substituto: Decimal = ZERO
    valor_st_retido: Decimal = ZERO
    fcp_st_retido: Decimal = ZERO
    # grupo do CST 60: a base e o imposto que a operação teria sem a ST
    bc_efetiva: Decimal = ZERO
    aliquota_efetiva: Decimal = ZERO
    icms_efetivo: Decimal = ZERO
    # pRedBC: o percentual de redução da base que o emitente declara
    reducao_declarada: Decimal = ZERO
    # PIS e COFINS do item. Não entram em nada da CAT 42; entram na triagem do
    # crédito outorgado, onde o CST do produto confirma o que a descrição diz —
    # cesta básica sai com CST 04 ou 06, e o que sai com 01 merece um olhar
    cst_pis: str = ""
    bc_pis: Decimal = ZERO
    aliq_pis: Decimal = ZERO
    valor_pis: Decimal = ZERO
    cst_cofins: str = ""
    bc_cofins: Decimal = ZERO
    aliq_cofins: Decimal = ZERO
    valor_cofins: Decimal = ZERO
    # IPI e ISSQN. Não entram em apuração nenhuma do sistema; entram na planilha
    # de extração dos XML, onde quem confere escolhe as colunas que quer ver —
    # e quem trabalha com indústria ou com serviço precisa destas
    cst_ipi: str = ""
    bc_ipi: Decimal = ZERO
    aliq_ipi: Decimal = ZERO
    valor_ipi: Decimal = ZERO
    issqn_deducao: Decimal = ZERO
    issqn_desconto_incondicional: Decimal = ZERO
    issqn_desconto_condicional: Decimal = ZERO

    @property
    def base_da_operacao(self) -> Decimal:
        """O valor sobre o qual o ICMS da operação incide.

        Não é o valor da mercadoria: frete, seguro e despesas cobrados do
        destinatário entram na base (artigo 37, § 1º, 1 do RICMS/SP), e
        desconto incondicional sai. Por isso a ordem é a do próprio documento:

        1. `vBC`, a base que o emitente destacou — já com frete e desconto, e já
           reduzida quando há benefício (CST 20 e 70);
        2. `vBCEfet`, que o CST 60 informa como base do imposto que a ST
           encerrou — é o que a nota de venda a consumidor traz;
        3. na falta das duas, a soma: mercadoria mais frete, seguro e outras
           despesas, menos o desconto.

        É esta a base do valor de confronto da Ficha 3, e é o que o papel de
        trabalho da CAT 42 grava na coluna VL_ITEM (decisão do Victor,
        18/09/2026).
        """
        if self.bc_icms > ZERO:
            return self.bc_icms
        if self.bc_efetiva > ZERO:
            return self.bc_efetiva
        return self.valor + self.frete + self.seguro + self.outras - self.desconto

    @property
    def retido_informado(self) -> Decimal | None:
        """O ICMS suportado antes, como a NF-e informa no CST 60: a operação
        própria do substituto mais o retido e o FCP retido. None sem valor."""
        total = self.valor_icms_substituto + self.valor_st_retido + self.fcp_st_retido
        return total if total > ZERO else None


@dataclass(frozen=True)
class DocumentoXml:
    chave: str
    modelo: str
    # tpNF: "0" entrada, "1" saída — do ponto de vista de quem emitiu
    tipo: str
    emitente: str
    destinatario: str
    numero: str
    serie: str
    emissao: date | None
    itens: tuple[ItemDoXml, ...]
    # indFinal: True consumidor final, False operação normal, None quando o XML não diz
    consumidor_final: bool | None = None
    # cStat do protNFe; None sem protocolo (XML do ERP) e no CF-e
    cstat: str | None = None
    # a razão social como o XML escreveu. O CNPJ identifica; o nome é o que
    # alguém lê numa planilha de triagem sem consultar o cadastro
    emitente_nome: str = ""
    destinatario_nome: str = ""

    @property
    def autorizado(self) -> bool | None:
        """True autorizado, False denegado ou recusado, None quando o XML não diz."""
        return None if self.cstat is None else self.cstat in CSTAT_AUTORIZADOS


def cstat_do_fim(fim: bytes) -> str | None:
    """O cStat do protocolo, a partir dos bytes finais do XML. None sem protocolo.

    Para a etapa 2, que lê só o começo e o fim de cada arquivo. O `cStat` só
    aparece no `infProt`; procura-se depois do último `<infProt`.
    """
    inicio = fim.rfind(b"<infProt")
    if inicio < 0:
        return None
    achado = _RE_CSTAT.search(fim, inicio)
    return achado.group(1).decode("ascii") if achado else None


def ler_documento_xml(conteudo: bytes) -> DocumentoXml | None:
    """O documento com os itens; None quando o XML não é NF-e, NFC-e nem CF-e."""
    raiz = _raiz(conteudo)
    if _local(raiz.tag) in ("cteProc", "CTe", "procEventoNFe", "procEventoCTe", "inutNFe", "procInutNFe"):
        return None
    for no in raiz.iter():
        nome = _local(no.tag)
        if nome == "NFe":
            inf = _filho(no, "infNFe")
            if inf is not None:
                return _nfe(inf, _cstat(raiz))
        elif nome == "CFe":
            inf = _filho(no, "infCFe")
            if inf is not None:
                return _cfe(inf)
    return None


def _raiz(conteudo: bytes) -> ET.Element:
    """O XML aberto. Declarado UTF-8 e gravado em Latin-1 é relido como Latin-1.

    Na Advertising, 13.676 NF-e diziam `encoding="UTF-8"` e traziam o `º` de
    "nº" num byte só (0xBA), escrito pelo ERP no `infAdProd`. O documento está
    inteiro; só a declaração mente.
    """
    try:
        return ET.fromstring(conteudo)
    except ET.ParseError as erro:
        try:
            conteudo.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return ET.fromstring(conteudo.decode("latin-1").encode("utf-8"))
            except ET.ParseError:
                pass
        raise XmlIlegivel(str(erro)) from erro


# ---------------------------------------------------------------------------
# NF-e e NFC-e
# ---------------------------------------------------------------------------
def _cstat(raiz: ET.Element) -> str | None:
    prot = _achar(raiz, "infProt")
    cstat = _texto(prot, "cStat") if prot is not None else ""
    return cstat or None


def _nfe(inf: ET.Element, cstat: str | None = None) -> DocumentoXml:
    ide = _filho(inf, "ide")
    emissao = _texto(ide, "dhEmi") or _texto(ide, "dEmi")
    modelo = _texto(ide, "mod")
    ind_final = _texto(ide, "indFinal")
    consumidor = True if modelo == "65" else {"1": True, "0": False}.get(ind_final)
    return DocumentoXml(
        chave=_chave(inf, "NFe"),
        modelo=modelo,
        tipo=_texto(ide, "tpNF"),
        emitente=_documento(_filho(inf, "emit")),
        destinatario=_documento(_filho(inf, "dest")),
        numero=_texto(ide, "nNF"),
        serie=_texto(ide, "serie"),
        emissao=_data(emissao),
        itens=tuple(_item(det) for det in _filhos(inf, "det")),
        consumidor_final=consumidor,
        cstat=cstat,
        emitente_nome=_nome(_filho(inf, "emit")),
        destinatario_nome=_nome(_filho(inf, "dest")),
    )


# ---------------------------------------------------------------------------
# CF-e SAT
# ---------------------------------------------------------------------------
def _cfe(inf: ET.Element) -> DocumentoXml:
    ide = _filho(inf, "ide")
    return DocumentoXml(
        chave=_chave(inf, "CFe"),
        modelo=_texto(ide, "mod") or MODELO_CFE_SAT,
        # o cupom é sempre venda de quem emitiu
        tipo="1",
        emitente=_documento(_filho(inf, "emit")),
        destinatario=_documento(_filho(inf, "dest")),
        numero=_texto(ide, "nCFe"),
        serie=_texto(ide, "nserieSAT"),
        emissao=_data(_texto(ide, "dEmi")),
        itens=tuple(_item(det) for det in _filhos(inf, "det")),
        consumidor_final=True,
        emitente_nome=_nome(_filho(inf, "emit")),
        destinatario_nome=_nome(_filho(inf, "dest")),
    )


# ---------------------------------------------------------------------------
# o item
# ---------------------------------------------------------------------------
def _numero_do_item(det: ET.Element) -> int:
    """A posição do item no documento: atributo `nItem` ou filho `<nItem>`.

    O leiaute põe `nItem` como **atributo** de `<det>`, e é assim que a SEFAZ
    autoriza a nota. Mas XML que passou por ferramenta de terceiro — portal de
    consulta, conversor do cliente — chega reserializado, com o número virado
    elemento: as 121 notas que a Dom Atacarejo entregou em 25/09/2026 vinham
    todas assim, e todas saíram com item 0.

    **A posição é o que casa o item do XML com a linha do C170 da EFD.** Sem
    ela o cruzamento por (chave, item) não existe, e nada na nota denuncia a
    perda: o resto do item vem completo, e a planilha sai com uma coluna de
    zeros que parece dado.

    Não se inventa pela ordem do arquivo quando o número não vem de jeito
    nenhum: zero é falta declarada, e a ordem do arquivo não é promessa de
    nada.
    """
    bruto = (det.get("nItem") or "").strip() or _texto(det, "nItem")
    try:
        return int(bruto)
    except ValueError:
        return 0


def _item(det: ET.Element) -> ItemDoXml:
    prod = _filho(det, "prod")
    icms = _grupo_do_icms(det)
    pis = _grupo_do_tributo(det, "PIS")
    cofins = _grupo_do_tributo(det, "COFINS")
    ipi = _grupo_do_tributo(det, "IPI")
    issqn = _filho(_filho(det, "imposto"), "ISSQN") if _filho(det, "imposto") is not None else None
    gtin = _texto(prod, "cEAN").strip()
    cest = _texto(prod, "CEST")
    if not cest:
        # no CF-e o CEST vem nas observações do fisco do item
        for obs in _filhos(det, "obsFiscoDet"):
            if (obs.get("xCampoDet") or "").strip().upper() == "COD. CEST":
                cest = _texto(obs, "xTextoDet")
    return ItemDoXml(
        numero=_numero_do_item(det),
        codigo=_texto(prod, "cProd").strip(),
        gtin="" if gtin.upper() in _SEM_GTIN else gtin,
        descricao=_texto(prod, "xProd").strip(),
        ncm=_texto(prod, "NCM"),
        cest=cest.strip(),
        cfop=_texto(prod, "CFOP"),
        unidade=_texto(prod, "uCom").strip(),
        quantidade=_decimal(_texto(prod, "qCom")),
        valor=_decimal(_texto(prod, "vProd")),
        valor_unitario=_decimal(_texto(prod, "vUnCom")),
        desconto=_decimal(_texto(prod, "vDesc")),
        frete=_decimal(_texto(prod, "vFrete")),
        seguro=_decimal(_texto(prod, "vSeg")),
        outras=_decimal(_texto(prod, "vOutro")),
        cst_icms=_cst(icms),
        bc_icms=_decimal(_texto(icms, "vBC")),
        aliq_icms=_decimal(_texto(icms, "pICMS")),
        valor_icms=_decimal(_texto(icms, "vICMS")),
        bc_st=_decimal(_texto(icms, "vBCST")),
        aliq_st=_decimal(_texto(icms, "pICMSST")),
        valor_st=_decimal(_texto(icms, "vICMSST")),
        fcp_st=_decimal(_texto(icms, "vFCPST")),
        bc_st_retido=_decimal(_texto(icms, "vBCSTRet")),
        valor_icms_substituto=_decimal(_texto(icms, "vICMSSubstituto")),
        valor_st_retido=_decimal(_texto(icms, "vICMSSTRet")),
        fcp_st_retido=_decimal(_texto(icms, "vFCPSTRet")),
        reducao_declarada=_decimal(_texto(icms, "pRedBC")),
        bc_efetiva=_decimal(_texto(icms, "vBCEfet")),
        aliquota_efetiva=_decimal(_texto(icms, "pICMSEfet")),
        icms_efetivo=_decimal(_texto(icms, "vICMSEfet")),
        cst_pis=_texto(pis, "CST"),
        bc_pis=_decimal(_texto(pis, "vBC")),
        aliq_pis=_decimal(_texto(pis, "pPIS")),
        valor_pis=_decimal(_texto(pis, "vPIS")),
        cst_cofins=_texto(cofins, "CST"),
        bc_cofins=_decimal(_texto(cofins, "vBC")),
        aliq_cofins=_decimal(_texto(cofins, "pCOFINS")),
        valor_cofins=_decimal(_texto(cofins, "vCOFINS")),
        cst_ipi=_texto(ipi, "CST"),
        bc_ipi=_decimal(_texto(ipi, "vBC")),
        aliq_ipi=_decimal(_texto(ipi, "pIPI")),
        valor_ipi=_decimal(_texto(ipi, "vIPI")),
        issqn_deducao=_decimal(_texto(issqn, "vDeducao")),
        issqn_desconto_incondicional=_decimal(_texto(issqn, "vDescIncond")),
        issqn_desconto_condicional=_decimal(_texto(issqn, "vDescCond")),
    )


def _grupo_do_tributo(det: ET.Element, nome: str) -> ET.Element | None:
    """O grupo dentro de `imposto/PIS` ou `imposto/COFINS`.

    Mesma forma do ICMS: o nome do grupo muda com o regime — `PISAliq`,
    `PISQtde`, `PISOutr`, `PISNT`, e os quatro equivalentes do COFINS —, e o que
    interessa é o que está dentro dele. Serve também ao IPI (`IPITrib`,
    `IPINT`), que tem a mesma estrutura.
    """
    imposto = _filho(det, "imposto")
    tributo = _filho(imposto, nome) if imposto is not None else None
    return next(iter(tributo), None) if tributo is not None else None


def _grupo_do_icms(det: ET.Element) -> ET.Element | None:
    """O grupo dentro de `imposto/ICMS`: `ICMS00`, `ICMS60`, `ICMSSN102`..."""
    imposto = _filho(det, "imposto")
    icms = _filho(imposto, "ICMS") if imposto is not None else None
    if icms is None:
        return None
    return next(iter(icms), None)


def _cst(grupo: ET.Element | None) -> str:
    if grupo is None:
        return ""
    origem = _texto(grupo, "orig") or _texto(grupo, "Orig")
    tributacao = _texto(grupo, "CST") or _texto(grupo, "CSOSN")
    return f"{origem}{tributacao}" if tributacao else ""


# ---------------------------------------------------------------------------
# miúdos
# ---------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _achar(no: ET.Element, nome: str) -> ET.Element | None:
    for e in no.iter():
        if _local(e.tag) == nome:
            return e
    return None


def _filho(no: ET.Element | None, nome: str) -> ET.Element | None:
    if no is None:
        return None
    for e in no:
        if _local(e.tag) == nome:
            return e
    return None


def _filhos(no: ET.Element | None, nome: str) -> list[ET.Element]:
    if no is None:
        return []
    return [e for e in no if _local(e.tag) == nome]


def _texto(no: ET.Element | None, nome: str) -> str:
    alvo = _filho(no, nome)
    return (alvo.text or "").strip() if alvo is not None else ""


def _documento(no: ET.Element | None) -> str:
    return _texto(no, "CNPJ") or _texto(no, "CPF")


def _nome(no: ET.Element | None) -> str:
    """A razão social; o fantasia quando a nota não traz a razão."""
    return _texto(no, "xNome") or _texto(no, "xFant")


def _chave(inf: ET.Element, prefixo: str) -> str:
    identificador = (inf.get("Id") or "").strip()
    return identificador[len(prefixo):] if identificador.startswith(prefixo) else identificador


def _decimal(texto: str) -> Decimal:
    if not texto:
        return ZERO
    try:
        return Decimal(texto)
    except InvalidOperation:
        return ZERO


def _data(texto: str) -> date | None:
    """`2024-06-21T10:00:00-03:00` na NF-e, `20240621` no CF-e."""
    t = texto.strip()
    try:
        if len(t) >= 10 and t[4] == "-":
            return date(int(t[:4]), int(t[5:7]), int(t[8:10]))
        if len(t) == 8 and t.isdigit():
            return date(int(t[:4]), int(t[4:6]), int(t[6:8]))
    except ValueError:
        return None
    return None
