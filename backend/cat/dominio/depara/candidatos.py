"""De-para de códigos: achar o mesmo produto escriturado com códigos diferentes.

A CAT 42 controla o estoque por mercadoria. Quando a entrada é escriturada com
um código e a saída com outro, o razão monta duas fichas — uma só com
entradas, que não pede nada, e outra só com saídas, que fica negativa e sai do
total. O ressarcimento daquele produto some sem aviso de que era o mesmo.

Na empresa 04 (RVZ, 2022 a 2024) o mesmo produto tinha até quatro
códigos: `1111` na venda, `1111K3` no kit de três, `1111K3         08` na compra
(o código de venda mais espaços e "08") e `X00450IETL` na venda por
marketplace. Nada disso é exceção: é o ERP de um distribuidor.

## Como se acha

Os códigos que são o mesmo produto formam um **grupo**, ligados por:

* **GTIN** — o mesmo código de barras (0200 ou XML). Prova forte;
* **sufixo que se repete** — o código de compra é o de venda mais um sufixo, e o
  mesmo sufixo aparece em vários pares (no mínimo `MINIMO_DE_PARES_DO_SUFIXO`).
  Um par só com sufixo pode ser coincidência; dez pares com "08", não;
* **kit** — o código ou a descrição diz "KIT 3X"/`K3`, e existe o código da
  unidade com a mesma base. Liga com **fator**: 1 kit = 3 unidades;
* **descrição e NCM** — a mesma descrição, limpa de lote e validade, e o mesmo
  NCM. Prova média: vai à revisão marcada assim.

Só se propõe grupo que **conserta alguma ficha**: com pelo menos um código sem
entrada ou sem saída. Dois códigos com entrada e saída cada um são, até prova
em contrário, produtos diferentes que se parecem. Devolução conta como
movimento aqui — o `4004` da empresa 04 só tinha devolução de compra (5.411),
e a ficha dele, só com a devolução, é a que juntar conserta —, mas não escolhe
o destino, que é onde se vende.

Em cada grupo, o código que fica é o de **mais saídas** (é nele que o cliente
vende); os outros viram pares `origem → destino` com o fator acumulado.

## O que impede juntar demais

* `K3` no fim do código é kit, não sufixo: quem liga o kit à unidade é a regra
  do kit, com fator. Tratado como sufixo, o kit virava unidade com fator 1;
* o kit reconhecido pela descrição ("KIT 3X") procura a unidade pela descrição
  sem o kit; quando ela tem mais de um código (`3133` e `3133           08`),
  fica o que é o começo do código do kit (`3133K3         08`). Quando a
  descrição do kit abrevia a da unidade ("CAST. ESC" e "CAST. ESCURO"), vale o
  código mais longo que começa o do kit, com o mesmo NCM e descrição compatível.
  Na empresa 04 eram 8 kits de compra que ficavam sem par;
* GTIN não liga kit a unidade — são embalagens diferentes do mesmo produto, e
  o fator não sai do GTIN;
* sufixo também só liga descrições compatíveis: num catálogo numérico grande,
  "código + um dígito" coincide por acaso (na empresa 19, `1024078` e `102407`,
  "repetido em 4 pares"). O mesmo código com e sem espaços liga sempre;
* GTIN só liga descrições compatíveis (metade das palavras em comum): o 0200
  da empresa 04 trazia no `1114` ("GRECIN 5 PRETO") o GTIN do `1050` ("GRECIN
  TONS DE GRISALHO"), e o GTIN sozinho juntava seis produtos num;
* quando dois caminhos do grupo dão fatores diferentes para o mesmo código, o
  grupo inteiro cai para confiança média, com o conflito escrito.

## O que vale sozinho, e o que espera alguém

Até 14/10/2026 nada era aplicado sozinho: tudo ia à revisão (decisão do Victor,
16/09/2026). Medido na empresa 26, isso virou 57 pares — **todos de GTIN** —
aprovados um a um, sem ninguém discordar de nenhum: trabalho que não decide
nada.

Agora o par de **GTIN** ou de **sufixo que se repete** vale por padrão, e a
decisão só é gravada quando alguém **discorda** dele (`vale_sozinho`). As duas
provas identificam o mesmo produto e ligam sempre com fator 1, então aceitá-las
não muda quantidade nenhuma — só junta duas fichas do mesmo produto, que é o
que o razão erraria sem elas.

Desde 10/11/2026 o par de prova forte ainda passa por cinco **travas**
(`travas_do_par`): sufixo entre descrições diferentes, GTIN usado em capítulos
de NCM diferentes, os dois códigos convivendo, peso/volume diferente na
descrição e custo incoerente. Qualquer uma manda o par para a revisão. Sem
elas, do que valia sozinho só 42% e 13% era o mesmo produto, nas duas bases
medidas; com elas, 89,5% e 90,5%.

O **kit** fica de fora mesmo com confiança alta: é ele que traz fator diferente
de 1, e fator errado erra a quantidade da ficha, não só o agrupamento. A
**descrição** fica de fora por ser a prova mais fraca. Essas duas continuam
esperando alguém olhar, e o que não casar vai para o cliente preencher.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

ZERO = Decimal(0)
UM = Decimal(1)

MINIMO_DE_PARES_DO_SUFIXO = 3
TAMANHO_MAXIMO_DO_SUFIXO = 3


class Motivo(str, Enum):
    GTIN = "gtin"
    SUFIXO = "sufixo"
    KIT = "kit"
    DESCRICAO = "descricao"
    CLIENTE = "cliente"
    ANALISTA = "analista"

    @property
    def rotulo(self) -> str:
        return {
            Motivo.GTIN: "Mesmo código de barras",
            Motivo.SUFIXO: "Código de compra = código de venda + sufixo",
            Motivo.KIT: "Kit de unidades do mesmo produto",
            Motivo.DESCRICAO: "Mesma descrição e NCM",
            Motivo.CLIENTE: "Informado pelo cliente",
            Motivo.ANALISTA: "Informado pelo analista",
        }[self]


class Confianca(str, Enum):
    ALTA = "alta"
    MEDIA = "media"


@dataclass(frozen=True)
class ItemParaCasar:
    """O que se sabe de um código num estabelecimento."""

    codigo: str
    descricao: str = ""
    ncm: str = ""
    gtins: frozenset[str] = frozenset()
    # os que o **documento** declarou, não o cadastro. Ver `_por_gtin`
    gtins_do_xml: frozenset[str] = frozenset()
    entradas: Decimal = ZERO        # quantidade entrada no período, sem devolução
    saidas: Decimal = ZERO          # quantidade saída no período, sem devolução
    estoque_inicial: Decimal = ZERO  # abertura do inventário
    devolucoes_de_venda: Decimal = ZERO   # entrada de devolução (1.411, 2.411...)
    devolucoes_de_compra: Decimal = ZERO  # saída de devolução ao fornecedor (5.411, 6.411...)
    # para as travas do `vale_sozinho` (ver "O que tira o par do vale sozinho")
    semanas_com_saida: frozenset = frozenset()    # início de cada semana com venda/saída
    semanas_com_entrada: frozenset = frozenset()  # início de cada semana com entrada
    custo_unitario: Decimal | None = None   # Σ(valor − desconto) ÷ Σ quantidade das entradas
    preco_de_venda: Decimal | None = None   # Σ valor ÷ Σ quantidade das saídas, sem transferência

    @property
    def tem_origem(self) -> bool:
        return self.entradas > ZERO or self.estoque_inicial > ZERO

    @property
    def tem_saida(self) -> bool:
        return self.saidas > ZERO

    @property
    def movimenta_entrada(self) -> bool:
        """Algo entra na ficha deste código, devolução inclusive."""
        return self.tem_origem or self.devolucoes_de_venda > ZERO

    @property
    def movimenta_saida(self) -> bool:
        """Algo sai da ficha deste código, devolução inclusive."""
        return self.tem_saida or self.devolucoes_de_compra > ZERO


@dataclass(frozen=True)
class Par:
    """`quantidade na origem × fator = quantidade no destino`."""

    origem: str
    destino: str
    fator: Decimal
    motivos: tuple[Motivo, ...]
    confianca: Confianca
    explicacao: str
    # o que impede o par de valer sozinho, escrito para quem revisa
    travas: tuple[str, ...] = ()
    # o que não impede, mas merece olho (o NCM de capítulo diferente)
    avisos: tuple[str, ...] = ()


# as provas que valem sem ninguém aprovar: identificam o mesmo produto e ligam
# com fator 1. O kit não entra — é ele que traz fator, e fator errado erra a
# quantidade da ficha
MOTIVOS_QUE_VALEM_SOZINHOS = frozenset({Motivo.GTIN, Motivo.SUFIXO})


def vale_sozinho(par: Par) -> bool:
    """O par entra na montagem sem ninguém aprovar?

    Cinco exigências. As do meio são o cinto depois do suspensório: o grupo
    pode ter sido ligado por mais de um caminho, e basta um kit no meio para o
    fator deixar de ser 1. Aceitar fator sem alguém olhar mudaria a quantidade
    da ficha, que é coisa diferente de juntar duas fichas do mesmo produto.

    A última é nenhuma **trava** (`travas_do_par`): a prova pode ser real e o
    produto, outro.
    """
    return (par.confianca is Confianca.ALTA
            and bool(MOTIVOS_QUE_VALEM_SOZINHOS & set(par.motivos))
            and Motivo.KIT not in par.motivos
            and par.fator == UM
            and not par.travas)


# ---------------------------------------------------------------------------
# O que tira o par do vale sozinho
# ---------------------------------------------------------------------------
#
# Medido em 10/11/2026 com gabarito (cada par lido dos dois lados), em duas
# bases: a empresa 29 (supermercado, 214 pares rotulados) e a execução 227
# (material de construção, amostra de 150). Do que valia sozinho, era mesmo
# produto **42%** na primeira e **13%** na segunda. O GTIN existia e era
# válido — estava no produto errado do cadastro, ou chegou por um pareamento
# C170 × XML fora de ordem; o sufixo ligava por corrente ("joelho de PVC →
# argamassa"). Com as cinco travas abaixo: **89,5% e 90,5%**. A conta está em
# `docs/especificacoes/depara/reforcos-do-depara.md`.
#
# Cada trava **manda para a revisão**, não recusa: o par certo barrado custa
# um clique; o errado aceito vai calado para a ficha.
#
# Ficam como **aviso**, sem barrar: o NCM de capítulo diferente — barrava 28
# pares certos de gaveta de dinheiro com NCM de empilhadeira num lado, que é
# cadastro errado e não produto diferente (e é o achado que o reenquadramento
# de PIS/COFINS quer). Ficaram de fora: unidade, sabor/versão (barrava mais
# certo que errado) e CEST (só tirava certos).

# sufixo com descrições com até isto de palavras em comum (Jaccard)
SEMELHANCA_MINIMA_DO_SUFIXO = 0.2
# semanas em comum, de venda ou de compra, que provam que os dois convivem
SEMANAS_QUE_PROVAM_CONVIVENCIA = 2
# peso/volume da descrição: diferença tolerada, já descontado o fator
TOLERANCIA_DA_MEDIDA = Decimal("0.10")
# custo da origem ÷ fator, sobre o custo do destino
FAIXA_DE_CUSTO = (Decimal("0.5"), Decimal("2.0"))
# custo da origem ÷ fator, sobre o preço de venda do destino (sem entrada nele)
FAIXA_DE_CUSTO_SOBRE_PRECO = (Decimal("0.3"), Decimal("1.2"))
# NCM que não diz capítulo nenhum
NCM_GENERICOS = frozenset({"11111111", "00000000", "99999999"})

_MEDIDA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KGS?|GRS?|G|MG|LTS?|L|ML)\b")
_PARA_BASE = {"KG": ("massa", Decimal(1000)), "KGS": ("massa", Decimal(1000)), "G": ("massa", UM),
              "GR": ("massa", UM), "GRS": ("massa", UM), "MG": ("massa", Decimal("0.001")),
              "L": ("volume", Decimal(1000)), "LT": ("volume", Decimal(1000)),
              "LTS": ("volume", Decimal(1000)), "ML": ("volume", UM)}
_PALAVRA = re.compile(r"[A-Z]{3,}")


def capitulo(ncm: str) -> str:
    """Os dois primeiros dígitos do NCM, ou "" quando ele não diz nada."""
    n = (ncm or "").strip()
    return n[:2] if len(n) >= 2 and n.isdigit() and n not in NCM_GENERICOS else ""


def semelhanca_de_palavras(a: str, b: str) -> float | None:
    """Jaccard das palavras de 3+ letras, sem acento. None quando um lado não tem descrição."""
    pa = set(_PALAVRA.findall(normalizar_descricao(a)))
    pb = set(_PALAVRA.findall(normalizar_descricao(b)))
    if not pa or not pb:
        return None
    return len(pa & pb) / len(pa | pb)


def medidas_da_descricao(descricao: str) -> dict[str, Decimal]:
    """O primeiro peso e o primeiro volume escritos na descrição, em g e ml."""
    achadas: dict[str, Decimal] = {}
    for numero, unidade in _MEDIDA.findall((descricao or "").upper()):
        tipo, mult = _PARA_BASE[unidade]
        achadas.setdefault(tipo, Decimal(numero.replace(",", ".")) * mult)
    return achadas


def gtins_contaminados(itens: Iterable[ItemParaCasar]) -> frozenset[str]:
    """GTINs que o estabelecimento usa em códigos de dois ou mais capítulos de NCM.

    Um GTIN é de um produto. Quando o mesmo aparece em creme de leite e em
    milho verde, ou o cadastro ou o pareamento erraram, e o GTIN deixa de
    provar qualquer coisa ali: na empresa 29, `7896232115673` estava em 12
    pares. Precisão medida: 87%.
    """
    capitulos: dict[str, set[str]] = {}
    for item in itens:
        cap = capitulo(item.ncm)
        if not cap:
            continue
        for g in item.gtins | item.gtins_do_xml:
            if gtin_valido(g):
                capitulos.setdefault(g.lstrip("0"), set()).add(cap)
    return frozenset(g for g, caps in capitulos.items() if len(caps) >= 2)


def travas_do_par(origem: ItemParaCasar, destino: ItemParaCasar, fator: Decimal,
                  motivos: Iterable[Motivo], contaminados: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """O que impede o par de valer sozinho; vazio quando nada impede."""
    motivos = set(motivos)
    travas: list[str] = []

    # 1. sufixo entre descrições que não se parecem: o par vem de uma corrente
    # no grupo (na execução 227, 118 erros barrados e nenhum certo)
    if Motivo.SUFIXO in motivos:
        s = semelhanca_de_palavras(origem.descricao, destino.descricao)
        if s is not None and s <= SEMELHANCA_MINIMA_DO_SUFIXO:
            travas.append(f"sufixo entre descrições diferentes ({s:.0%} das palavras em comum)")

    # 2. GTIN em códigos de capítulos diferentes de NCM
    comuns = ({g.lstrip("0") for g in origem.gtins | origem.gtins_do_xml if gtin_valido(g)}
              & {g.lstrip("0") for g in destino.gtins | destino.gtins_do_xml if gtin_valido(g)})
    sujos = sorted(comuns & contaminados)
    if sujos:
        travas.append(f"GTIN {sujos[0]} usado em produtos de capítulos de NCM diferentes")

    # 3. os dois convivem: troca de código não convive (precisão 94% e 100%)
    juntas = max(len(origem.semanas_com_saida & destino.semanas_com_saida),
                 len(origem.semanas_com_entrada & destino.semanas_com_entrada))
    if juntas >= SEMANAS_QUE_PROVAM_CONVIVENCIA:
        travas.append(f"os dois códigos se movimentam nas mesmas semanas ({juntas}): parecem produtos que convivem")

    # 4. peso ou volume da descrição diferente, descontado o fator (precisão 96%)
    mo, md = medidas_da_descricao(origem.descricao), medidas_da_descricao(destino.descricao)
    for tipo in sorted(mo.keys() & md.keys()):
        if md[tipo] and fator and abs(mo[tipo] / md[tipo] / fator - UM) > TOLERANCIA_DA_MEDIDA:
            u = "g" if tipo == "massa" else "ml"
            travas.append(f"{mo[tipo].normalize():f} {u} × {md[tipo].normalize():f} {u} na descrição")
            break

    # 5. custo incoerente com o fator
    co = origem.custo_unitario
    if co and fator:
        if destino.custo_unitario:
            razao, faixa, contra = co / fator / destino.custo_unitario, FAIXA_DE_CUSTO, "o custo"
        elif destino.preco_de_venda:
            razao, faixa, contra = co / fator / destino.preco_de_venda, FAIXA_DE_CUSTO_SOBRE_PRECO, "o preço de venda"
        else:
            razao = None
        if razao is not None and not faixa[0] <= razao <= faixa[1]:
            travas.append(f"custo incoerente: {razao:.2f} × {contra} do destino — confira o fator")
    return tuple(travas)


def avisos_do_par(origem: ItemParaCasar, destino: ItemParaCasar) -> tuple[str, ...]:
    """O que merece olho, sem barrar."""
    co, cd = capitulo(origem.ncm), capitulo(destino.ncm)
    if co and cd and co != cd:
        return (f"NCM de capítulos diferentes ({origem.ncm} × {destino.ncm}): um dos cadastros está errado",)
    return ()


@dataclass
class _Ligacao:
    a: str
    b: str
    # quantidade em `a` × fator = quantidade em `b`
    fator: Decimal
    motivo: Motivo
    detalhe: str


# ---------------------------------------------------------------------------
# normalização
# ---------------------------------------------------------------------------
_ESPACOS = re.compile(r"\s+")
_LOTE_VALIDADE = re.compile(r"\b(LOTE|LT|VAL|VALIDADE|FAB)\b\s*[:.]?\s*\S+", re.IGNORECASE)
_KIT_NA_DESCRICAO = re.compile(r"\bKIT\s*(?:C/|COM|DE)?\s*(\d{1,3})\s*(?:X|UN|UNID|UNIDADES)?\b"
                               r"|\b(\d{1,3})\s*X\s*KIT\b|\bKIT\b.*?\b(\d{1,3})\s*X\b", re.IGNORECASE)
_KIT_NO_CODIGO = re.compile(r"^(.+?)K(\d{1,2})$", re.IGNORECASE)
# "C/12", "C/ 12", "C/12UN": a embalagem com N unidades ("Cerveja Brahma 350ml Lata C/12"). Lido no texto
# **original** — normalizada, a barra vira espaço e "1680.C.100.112" (modelo da Deca) pareceria "C 100".
# Não vale com medida ou conteúdo depois do número: "C/100MT", "C/10 COMP", "C/25 SACHET" são uma unidade
# vendida inteira, não N unidades vendidas soltas
_KIT_C_BARRA = re.compile(
    r"\bC/\s*(\d{1,3})\s*(?:UN|UND|UNID|UNIDADES)?(?![\d,.])"
    r"(?!\s*(?:ML|MT|MTS|M|MM|CM|G|GR|KG|L|LT|LTS|CAPS|CAP|COMP|CPR|CP|DRG|SACHE|SACHES|SACHET|SACHETS"
    r"|FL|FLS|FOLHAS|DOSES|METROS|LAMINAS|ROLOS|PECAS|PCS|PC)\b)", re.IGNORECASE)
# acima disto o número é conteúdo, não fardo: "Lenço C/50", "Fralda C/36", "Espaçador cruzeta C/100 UNI".
# Fardo de bebida vai até 24. Medido na execução 227: sem o teto, 6 pares certos de GTIN se perdiam
MAXIMO_DO_KIT_C_BARRA = 24


def _kit_c_barra(descricao: str) -> int | None:
    """Unidades do fardo escrito como "C/12" na descrição, ou None."""
    for achado in _KIT_C_BARRA.finditer(descricao or ""):
        n = int(achado.group(1))
        if 1 < n <= MAXIMO_DO_KIT_C_BARRA:
            return n
    return None
_NAO_ALFANUMERICO = re.compile(r"[^A-Z0-9 ]+")


def normalizar_codigo(codigo: str) -> str:
    """Sem espaços: o ERP da empresa 04 grava `1012           08` e `101208`."""
    return _ESPACOS.sub("", codigo or "").upper()


def normalizar_descricao(descricao: str) -> str:
    """Maiúsculas, sem acento, sem lote e validade, sem pontuação, espaço único."""
    texto = unicodedata.normalize("NFKD", descricao or "").encode("ascii", "ignore").decode()
    texto = _LOTE_VALIDADE.sub(" ", texto.upper())
    texto = _NAO_ALFANUMERICO.sub(" ", texto)
    return _ESPACOS.sub(" ", texto).strip()


def gtin_valido(gtin: str) -> bool:
    """8, 12, 13 ou 14 dígitos, não todos iguais, com o dígito verificador certo."""
    g = (gtin or "").strip()
    if len(g) not in (8, 12, 13, 14) or not g.isdigit() or len(set(g)) == 1:
        return False
    corpo, dv = g[:-1], int(g[-1])
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10 == dv


def fator_do_kit(item: ItemParaCasar) -> tuple[int, str] | None:
    """(unidades no kit, base do código) quando o item é kit; senão None."""
    codigo = normalizar_codigo(item.codigo)
    no_codigo = _KIT_NO_CODIGO.match(codigo)
    achado = _KIT_NA_DESCRICAO.search(normalizar_descricao(item.descricao))
    n_descricao = next((int(g) for g in achado.groups() if g), None) if achado else None
    if no_codigo and int(no_codigo.group(2)) > 1:
        return int(no_codigo.group(2)), no_codigo.group(1)
    if n_descricao and n_descricao > 1:
        return n_descricao, codigo
    c_barra = _kit_c_barra(item.descricao)
    if c_barra:
        return c_barra, codigo
    return None


def descricoes_compativeis(a: str, b: str, minimo: float = 0.5) -> bool:
    """Se as duas descrições falam do mesmo produto: metade das palavras em comum.

    Sem descrição de um lado não há o que contrariar, e vale o GTIN.
    """
    pa = {p for p in _descricao_sem_kit(a).split() if len(p) >= 2}
    pb = {p for p in _descricao_sem_kit(b).split() if len(p) >= 2}
    if not pa or not pb:
        return True
    return len(pa & pb) / len(pa | pb) >= minimo


def _descricao_sem_kit(descricao: str) -> str:
    # tira só o "C/12" que é fardo; o "C/001 UN" e o "C/100" ficam, como estavam
    texto = normalizar_descricao(_KIT_C_BARRA.sub(
        lambda m: " " if 1 < int(m.group(1)) <= MAXIMO_DO_KIT_C_BARRA else m.group(0), descricao or ""))
    texto = re.sub(r"\bKIT\s*(C|COM|DE)?\s*\d{1,3}\s*(X|UN|UNID|UNIDADES)?\b", " ", texto)
    texto = re.sub(r"\b\d{1,3}\s*X\b", " ", texto)
    texto = re.sub(r"\bKIT\b", " ", texto)
    return _ESPACOS.sub(" ", texto).strip()


# ---------------------------------------------------------------------------
# as ligações
# ---------------------------------------------------------------------------
def _por_gtin(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    """Mesmo código de barras.

    ## Dois GTIN de força diferente

    O do **cadastro** (0200) é um campo que alguém digitou uma vez. Na empresa
    04 ele trazia no `1114` ("GRECIN 5 PRETO") o GTIN do `1050` ("GRECIN TONS
    DE GRISALHO"), e sozinho juntava seis produtos num. Por isso ele só liga
    descrições compatíveis — metade das palavras em comum.

    O do **documento** é o fornecedor declarando, na nota, qual é o código de
    barras daquele item. Quando o mesmo GTIN aparece no XML dos **dois** lados,
    são dois documentos independentes concordando, e a descrição não tem o que
    acrescentar — nem o que vetar.

    E vetava. Na empresa 26 eram **305 pares** recusados porque o fornecedor
    abreviou o que o cliente escreveu por extenso, com NCM igual nos dois:

        MARRETA 1,5 KG C/CABO TRAMONTINA  ↔  MARRETA C/CAB 1,5KG FORJ.OIT.TRAMO
        LUVA PVC SOLDA REDUC AMANCO 50X25MM  ↔  AMANCO PR - LUVA RED SOLD 50X25MM

    São o mesmo produto, e a regra escrita para proteger de um cadastro errado
    estava reprovando o que dois documentos afirmavam. Medido nessa base: o
    GTIN do cadastro e o do XML concordam em 7.381 linhas e divergem em 39 —
    as 39 são exatamente o risco que a exigência de descrição cobre, e ela
    continua cobrindo.

    O kit segue de fora nos dois casos: embalagens diferentes do mesmo produto
    compartilham código de barras, e o fator não sai daqui.
    """
    por_gtin: dict[str, list[str]] = {}
    for codigo, item in itens.items():
        for g in item.gtins | item.gtins_do_xml:
            if gtin_valido(g):
                por_gtin.setdefault(g.lstrip("0"), []).append(codigo)
    ligacoes = []
    for gtin, codigos in por_gtin.items():
        codigos = sorted(set(codigos))
        raiz = itens[codigos[0]]
        for outro in codigos[1:]:
            item = itens[outro]
            # kit e unidade com o mesmo GTIN: o fator não sai daqui
            if (fator_do_kit(item) is None) != (fator_do_kit(raiz) is None):
                continue
            nos_documentos = _declarado_no_xml(item, gtin) and _declarado_no_xml(raiz, gtin)
            if not nos_documentos and not descricoes_compativeis(item.descricao, raiz.descricao):
                continue
            detalhe = f"GTIN {gtin}" + (" nos dois documentos" if nos_documentos else "")
            ligacoes.append(_Ligacao(outro, codigos[0], UM, Motivo.GTIN, detalhe))
    return ligacoes


def _declarado_no_xml(item: ItemParaCasar, gtin: str) -> bool:
    """Este GTIN veio do documento deste item, e não só do cadastro dele?"""
    return any(gtin_valido(g) and g.lstrip("0") == gtin for g in item.gtins_do_xml)


def _por_sufixo(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    """Pares `base + sufixo`, só com sufixo que se repete."""
    normal = {normalizar_codigo(c): c for c in itens}
    pares: dict[str, list[tuple[str, str]]] = {}
    for longo_n, longo in normal.items():
        if _KIT_NO_CODIGO.match(longo_n):
            continue                     # `1111K3` é kit do 1111, não sufixo
        for tamanho in range(1, TAMANHO_MAXIMO_DO_SUFIXO + 1):
            base_n, sufixo = longo_n[:-tamanho], longo_n[-tamanho:]
            if len(base_n) >= 2 and base_n in normal:
                pares.setdefault(sufixo, []).append((longo, normal[base_n]))
    ligacoes = []
    for sufixo, lista in pares.items():
        # a repetição só conta entre pares que falam do mesmo produto
        lista = [(longo, base) for longo, base in lista
                 if descricoes_compativeis(itens[longo].descricao, itens[base].descricao)]
        if len(lista) < MINIMO_DE_PARES_DO_SUFIXO:
            continue
        for longo, base in lista:
            ligacoes.append(_Ligacao(longo, base, UM, Motivo.SUFIXO,
                                     f"sufixo \"{sufixo}\", repetido em {len(lista)} pares"))
    # o mesmo código sem espaços (`1012           08` e `101208`) é o mesmo código
    por_normal: dict[str, list[str]] = {}
    for c in itens:
        por_normal.setdefault(normalizar_codigo(c), []).append(c)
    for n, lista in por_normal.items():
        lista = sorted(lista)
        for outro in lista[1:]:
            ligacoes.append(_Ligacao(outro, lista[0], UM, Motivo.SUFIXO, "mesmo código sem os espaços"))
    return ligacoes


def _por_kit(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    normal = {normalizar_codigo(c): c for c in itens}
    por_descricao: dict[str, list[str]] = {}
    for c, item in itens.items():
        if fator_do_kit(item) is None:
            por_descricao.setdefault(_descricao_sem_kit(item.descricao), []).append(c)
    ligacoes = []
    for codigo, item in itens.items():
        kit = fator_do_kit(item)
        if kit is None:
            continue
        unidades, base = kit
        unidade = normal.get(base) if base != normalizar_codigo(codigo) else None
        if unidade is None:
            candidatos = [c for c in por_descricao.get(_descricao_sem_kit(item.descricao), [])
                          if (itens[c].ncm or item.ncm) == (item.ncm or itens[c].ncm)]
            if len(candidatos) > 1:
                # a unidade com mais de um código: vale o que é o começo do código do kit
                do_kit = normalizar_codigo(codigo)
                prefixos = [c for c in candidatos if do_kit.startswith(normalizar_codigo(c))]
                candidatos = prefixos or candidatos
            unidade = candidatos[0] if len(candidatos) == 1 else None
        if unidade is None:
            unidade = _unidade_pelo_comeco_do_codigo(codigo, item, itens, normal)
        if unidade is not None and unidade != codigo:
            ligacoes.append(_Ligacao(codigo, unidade, Decimal(unidades), Motivo.KIT,
                                     f"kit de {unidades} unidades"))
    return ligacoes


def _unidade_pelo_comeco_do_codigo(codigo: str, kit: ItemParaCasar, itens: dict[str, ItemParaCasar],
                                   normal: dict[str, str]) -> str | None:
    """O código mais longo que começa o código do kit, com o mesmo NCM e descrição compatível.

    A descrição do kit costuma abreviar a da unidade ("GRECIN 5 PG CAST. ESC KIT 3X"
    e "GRECIN 5 PG CAST. ESCURO"), e a igualdade não acha. O começo do código
    (`3132K3         08` → `3132`) acha, e a descrição confere.
    """
    do_kit = normalizar_codigo(codigo)
    for tamanho in range(len(do_kit) - 1, 1, -1):
        outro = normal.get(do_kit[:tamanho])
        if outro is None or outro == codigo or fator_do_kit(itens[outro]) is not None:
            continue
        if (itens[outro].ncm or kit.ncm) != (kit.ncm or itens[outro].ncm):
            continue
        if descricoes_compativeis(kit.descricao, itens[outro].descricao):
            return outro
    return None


def _por_descricao(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    grupos: dict[tuple[str, str], list[str]] = {}
    for c, item in itens.items():
        d = normalizar_descricao(item.descricao)
        if len(d) >= 6 and item.ncm and fator_do_kit(item) is None:
            grupos.setdefault((d, item.ncm), []).append(c)
    ligacoes = []
    for (d, ncm), codigos in grupos.items():
        codigos = sorted(codigos)
        for outro in codigos[1:]:
            ligacoes.append(_Ligacao(outro, codigos[0], UM, Motivo.DESCRICAO, f"\"{d}\", NCM {ncm}"))
    return ligacoes


# ---------------------------------------------------------------------------
# os grupos e os pares
# ---------------------------------------------------------------------------
@dataclass
class _Grupo:
    codigos: set[str] = field(default_factory=set)
    # fator de cada código para a raiz provisória do grupo: q(código) × f = q(raiz)
    fatores: dict[str, Decimal] = field(default_factory=dict)
    motivos: dict[str, set[Motivo]] = field(default_factory=dict)
    detalhes: dict[str, list[str]] = field(default_factory=dict)
    conflitos: list[str] = field(default_factory=list)


def propor(itens: list[ItemParaCasar]) -> list[Par]:
    """Os pares `origem → destino` que juntam o mesmo produto, para revisão."""
    por_codigo = {i.codigo: i for i in itens}
    contaminados = gtins_contaminados(por_codigo.values())
    ligacoes = (_por_gtin(por_codigo) + _por_sufixo(por_codigo)
                + _por_kit(por_codigo) + _por_descricao(por_codigo))

    # o fator de cada código até uma raiz comum, andando pelas ligações
    vizinhos: dict[str, list[tuple[str, Decimal, _Ligacao]]] = {}
    for l in ligacoes:
        vizinhos.setdefault(l.a, []).append((l.b, l.fator, l))
        vizinhos.setdefault(l.b, []).append((l.a, UM / l.fator, l))

    vistos: set[str] = set()
    pares: list[Par] = []
    for inicio in sorted(vizinhos):
        if inicio in vistos:
            continue
        grupo = _Grupo()
        grupo.fatores[inicio] = UM
        fila = [inicio]
        while fila:
            atual = fila.pop()
            if atual in grupo.codigos:
                continue
            grupo.codigos.add(atual)
            for vizinho, fator, ligacao in vizinhos.get(atual, []):
                # q(vizinho) × f(vizinho) = q(raiz), e q(atual) × fator = q(vizinho)
                esperado = grupo.fatores[atual] / fator
                if vizinho in grupo.fatores and grupo.fatores[vizinho] != esperado:
                    grupo.conflitos.append(f"{vizinho}: fator {grupo.fatores[vizinho].normalize()} "
                                           f"ou {esperado.normalize()} ({ligacao.detalhe})")
                grupo.fatores.setdefault(vizinho, esperado)
                for c in (ligacao.a, ligacao.b):
                    grupo.motivos.setdefault(c, set()).add(ligacao.motivo)
                    grupo.detalhes.setdefault(c, [])
                    if ligacao.detalhe not in grupo.detalhes[c]:
                        grupo.detalhes[c].append(ligacao.detalhe)
                if vizinho not in grupo.codigos:
                    fila.append(vizinho)
        vistos |= grupo.codigos
        pares += _pares_do_grupo(grupo, por_codigo, contaminados)
    return sorted(pares, key=lambda p: (p.destino, p.origem))


def _arredondar_fator(fator: Decimal) -> Decimal:
    """O fator sem o resíduo da divisão: 1 ÷ (1/6) dava 5,99999…, e o razão multiplicava por isso."""
    redondo = fator.quantize(Decimal("1e-10"))
    if abs(redondo - redondo.to_integral_value()) < Decimal("1e-8"):
        redondo = redondo.to_integral_value()
    return redondo.normalize()


def _pares_do_grupo(grupo: _Grupo, itens: dict[str, ItemParaCasar],
                    contaminados: frozenset[str] = frozenset()) -> list[Par]:
    membros = [itens[c] for c in grupo.codigos if c in itens]
    if len(membros) < 2:
        return []
    # só vale propor se juntar conserta alguma ficha; a devolução é movimento da ficha
    if all(m.tem_origem and m.tem_saida for m in membros):
        return []
    if not any(m.movimenta_entrada for m in membros) or not any(m.movimenta_saida for m in membros):
        return []
    # o destino é onde se vende: mais saídas na unidade da raiz; empate, o código mais curto
    destino = max(membros, key=lambda m: (m.saidas * grupo.fatores[m.codigo],
                                          -len(normalizar_codigo(m.codigo)), m.codigo))
    f_destino = grupo.fatores[destino.codigo]
    pares = []
    for m in membros:
        if m.codigo == destino.codigo:
            continue
        # q(m) × f(m) = q(raiz) = q(destino) × f(destino)  →  q(destino) = q(m) × f(m) / f(destino)
        fator = _arredondar_fator(grupo.fatores[m.codigo] / f_destino)
        motivos = tuple(sorted(grupo.motivos.get(m.codigo, set()) | grupo.motivos.get(destino.codigo, set()),
                               key=lambda x: list(Motivo).index(x)))
        confianca = (Confianca.ALTA if any(x in (Motivo.GTIN, Motivo.SUFIXO, Motivo.KIT) for x in motivos)
                     and not grupo.conflitos else Confianca.MEDIA)
        detalhes = "; ".join(dict.fromkeys(grupo.detalhes.get(m.codigo, []) + grupo.detalhes.get(destino.codigo, [])))
        if grupo.conflitos:
            detalhes = f"fatores em conflito no grupo ({'; '.join(grupo.conflitos[:2])}); {detalhes}"
        travas = travas_do_par(m, destino, fator, motivos, contaminados)
        avisos = avisos_do_par(m, destino)
        # quem revisa lê o porquê na explicação, sem a tela precisar mudar
        for texto in travas:
            detalhes = f"{detalhes}; revisar: {texto}"
        for texto in avisos:
            detalhes = f"{detalhes}; atenção: {texto}"
        pares.append(Par(m.codigo, destino.codigo, fator, motivos, confianca, detalhes, travas, avisos))
    return pares


# ---------------------------------------------------------------------------
# a ligação feita à mão
# ---------------------------------------------------------------------------
#
# `propor` só devolve grupo que ela **prova**: GTIN igual, sufixo repetido, kit
# ou descrição com metade das palavras em comum. É deliberado — proposta fraca
# vira trabalho de recusar, não ajuda.
#
# Mas o código que sobra sem par precisa de alguém decidindo, e essa pessoa
# estava digitando o código de destino **de cabeça**: a tela não mostrava a
# descrição do outro lado nem deixava procurar. O que segue ordena candidatos
# para essa escolha — não propõe nada, não decide nada, só põe o provável na
# frente de quem vai olhar.


@dataclass(frozen=True)
class Candidato:
    """Um código que talvez seja o mesmo produto, e por que ele subiu na lista."""

    item: ItemParaCasar
    pontos: int
    porques: tuple[str, ...]


# O código sem par tem saída e não tem entrada. O par que conserta a ficha dele
# é, quase sempre, o espelho: entrada sem saída. Pesa mais que a descrição
# porque é a forma do problema, não uma semelhança de texto.
PONTOS_ESPELHO = 50
PONTOS_GTIN = 100
PONTOS_NCM = 20
PONTOS_DESCRICAO = 60        # multiplicado pela fração de palavras em comum
PONTOS_CODIGO_PARECIDO = 25


def _semelhanca(a: str, b: str) -> float:
    """Fração de palavras em comum, de 0 a 1. É a métrica de `descricoes_compativeis`."""
    pa = {p for p in _descricao_sem_kit(a).split() if len(p) >= 2}
    pb = {p for p in _descricao_sem_kit(b).split() if len(p) >= 2}
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def ordenar_candidatos(origem: ItemParaCasar, outros: Iterable[ItemParaCasar],
                       busca: str = "", limite: int = 50) -> list[Candidato]:
    """Os prováveis pares de `origem`, do mais provável ao menos.

    `busca` filtra por pedaço do código ou da descrição, com a mesma
    normalização do resto do módulo — quem digita "cast esc" acha
    "CAST. ESCURO". Sem busca, devolve os mais parecidos.

    **Não é proposta.** O que `propor` devolve tem prova; isto é uma ordenação
    para quem vai decidir olhando. Por isso entra candidato que o motor nunca
    proporia sozinho, e por isso cada um diz por que subiu.
    """
    termo = normalizar_descricao(busca)
    codigo_buscado = normalizar_codigo(busca)
    gtins_da_origem = {g for g in origem.gtins if gtin_valido(g)}
    achados: list[Candidato] = []

    for item in outros:
        if normalizar_codigo(item.codigo) == normalizar_codigo(origem.codigo):
            continue
        if termo or codigo_buscado:
            casa = (termo and termo in normalizar_descricao(item.descricao)) or \
                   (codigo_buscado and codigo_buscado in normalizar_codigo(item.codigo))
            if not casa:
                continue

        pontos = 0
        porques: list[str] = []
        # **o que identifica o produto.** Só estes dão entrada na lista: sem
        # nenhum deles, o que sobra vale para metade do catálogo
        if gtins_da_origem & {g for g in item.gtins if gtin_valido(g)}:
            pontos += PONTOS_GTIN
            porques.append("mesmo código de barras")
        if origem.ncm and item.ncm and origem.ncm == item.ncm:
            pontos += PONTOS_NCM
            porques.append("mesmo NCM")
        parecida = _semelhanca(origem.descricao, item.descricao)
        if parecida > 0:
            pontos += int(PONTOS_DESCRICAO * parecida)
            porques.append(f"descrição {parecida:.0%} parecida")
        a, b = normalizar_codigo(origem.codigo), normalizar_codigo(item.codigo)
        if a and b and (a.startswith(b) or b.startswith(a)):
            pontos += PONTOS_CODIGO_PARECIDO
            porques.append("um código começa o outro")
        identificado = pontos > 0

        # **a forma do problema**, que desempata entre os identificados. Sozinha
        # não vale: todo código de compra do catálogo tem entrada e não tem
        # saída, e um parafuso subiria na lista de uma castanha
        if item.tem_origem and not item.saidas:
            pontos += PONTOS_ESPELHO
            porques.append("tem entrada e não tem saída")

        # quem buscou pelo nome já disse o que quer ver, mesmo sem parecença
        if identificado or termo or codigo_buscado:
            achados.append(Candidato(item, pontos, tuple(porques)))

    achados.sort(key=lambda c: (-c.pontos, -c.item.entradas, c.item.codigo))
    return achados[:limite]
