"""Que produto é esta linha de compra — e em que unidade ele é tributado.

A tabela de NCM é `tabelas/tab_combustivel.py`. Aqui mora a **cascata**, que é
regra: quem decide, em que ordem, e com que confiança.

## A cascata, e por que esta ordem

```
1. código ANP (0206)          chave exata — nunca apareceu em cliente nenhum
2. NCM presente               DECIDE. Lubrificante sai aqui, mesmo dizendo "diesel"
3. NCM ausente                a descrição decide
4. NCM e descrição discordam  fila humana, nunca palpite
```

A NCM manda porque a subposição é juridicamente precisa e **é a descrição que
mente**: `OLEO MOTOR DIESEL SAE15` está em `27101932`, que é lubrificante. São
R$ 239.828 em 273 linhas na empresa G que um classificador de descrição lançaria
como crédito.

Mas a NCM sozinha também falha, e no mesmo cliente: **86 linhas de `DIESEL S10`
com NCM vazio**, mais `GASOLINA COMUM` (24) e `DIESEL S-500` (10). Combustível de
verdade, sem NCM — ali só a descrição salva. E a mesma lista de NCM vazio tem
`LANTERNA` e `FAROL`, então a descrição tem de saber dizer não.

## A saída é tupla, não rótulo

Dizer "é GLP" não serve: a ad rem do GLP é **por quilo**, o SPED declara `UN`, e
o fator está no texto. Por isso a saída traz produto, unidade tributada, fator,
confiança e **o porquê** — a frase que o revisor lê para concordar ou discordar.

## A confiança aqui nunca recusa

Regra da casa (`DOMINIO_COMBUSTIVEL.md`, §8): a **confiança da classificação** é
inferência sobre texto livre e emite tudo, ranqueado, com o motivo — o revisor
decide. Quem recusa é a **cobertura da regra**, que é fato sobre tabela e mora em
`tab_ad_rem`: sem vigência cobrindo a competência, a linha sai do total.

> O humano decide o que o produto é; a tabela decide quanto ele vale. Nunca o
> contrário.

Por isso este módulo não tem exceção nenhuma. Ele devolve `produto=""` com
`confianca=BAIXA` e `revisar=True` quando não sabe, e a linha aparece.

## A chave de agrupamento não é o `COD_ITEM`

Medido: o padrão `(BOMBA:27 BICO:27)` mostra que o posto gera **um código por
bico de bomba** — foi assim que uma NCM só rendeu 135 descrições. A chave é
`(descrição normalizada, NCM)`, que é o que `chave_de_agrupamento` devolve.

E é a normalização que torna este classificador **conferível**: as 132 descrições
de `27101921` colapsam para poucas formas, e num universo de sete produtos dá
para revisar 100% uma vez. Nem o reenquadrador nem o de-para puderam fazer isso.

## O fator de conversão: 0220 primeiro, texto depois

O `0220` é a fonte certa — `UNID_CONV` e `FAT_CONV`, medidos em 20 milhões de
linhas da empresa Z. Quem tiver o 0220 do item passa em `conversao`; quem não
tiver cai no texto, que é onde o GLP escreve o fardo: `P20 - GLP 20 KGS`.

Sem nenhum dos dois, o fator sai `None` e `revisar` sai `True`. **Nunca 1 por
omissão:** assumir "um botijão é um quilo" erraria vinte vezes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from cat.infraestrutura.sped.tabelas import tab_combustivel
from cat.infraestrutura.sped.tabelas.tab_ad_rem import (
    LITRO,
    QUILO,
    UNIDADE,
)
from cat.infraestrutura.sped.tabelas.tab_combustivel import (
    DIESEL,
    ETANOL_ANIDRO,
    ETANOL_HIDRATADO,
    FORA,
    GASOLINA,
    GLP,
    LUBRIFICANTE,
)

ALTA = "alta"
MEDIA = "media"
BAIXA = "baixa"

# As unidades em que o próprio litro vem declarado. Medidas em CST 60/61 da
# empresa G: `L` (1.920), `LT` (947), `LTS` (318), `l` (117), `LITRO` (9).
# `LI` entrou do levantamento de 95 arquivos.
UNIDADES_DE_LITRO = frozenset({"L", "LT", "LTS", "LITRO", "LITROS", "LI"})

# E as de quilo.
UNIDADES_DE_QUILO = frozenset({"KG", "KGS", "QUILO", "QUILOS", "K"})

# As de embalagem, em que a quantidade é de **recipientes** e não do produto.
# `BD` é balde, `GL` galão — os dois medidos. Aqui o fator é obrigatório.
UNIDADES_DE_EMBALAGEM = frozenset({
    "UN", "UND", "UNID", "UNIDA", "UNIDADE", "PC", "PÇ", "PECA", "PEÇA",
    "BD", "GL", "GA", "CX", "FD", "TB", "P", "SC",
})

# `(BOMBA:27 BICO:27)` e irmãos: o posto gera um código por bico, e o texto do
# bico não distingue produto nenhum
_PARENTESES = re.compile(r"\([^)]*\)")

# `GASOLINA COMUM.....................` — ponto de preenchimento de campo fixo
_PONTOS_DE_PREENCHIMENTO = re.compile(r"\.{2,}")

# `S-10`, `S 10`, `BS10`, `S10` são o mesmo diesel; `S-500` idem
_ENXOFRE = re.compile(r"\bB?S[\s\-]?(10|500)\b")

# o que sobra de pontuação depois do resto
_NAO_ALFANUMERICO = re.compile(r"[^A-Z0-9 ]+")
_ESPACOS = re.compile(r"\s+")

# o fator no texto: `20 KGS`, `20KG`, `- 20LT`, `13 KG`
_FATOR_NO_TEXTO = re.compile(
    r"(?<![A-Z0-9])(\d{1,4}(?:[.,]\d{1,3})?)\s*(KGS?|LTS?|L|LITROS?|ML)\b")

# marcadores de que o "diesel" do texto é **óleo de motor**, não combustível.
# `SAE` é grau de viscosidade, e não existe em combustível
_MARCAS_DE_LUBRIFICANTE = (
    "SAE", "OLEO MOTOR", "OLEO DE MOTOR", "LUBRIFICANTE", "LUB ", "GRAXA",
    "HIDRAULICO", "TRANSMISSAO", "CAMBIO", "ATF", "W40", "W30", "15W", "20W",
)


@dataclass(frozen=True)
class Classificacao:
    """O que a linha é, em que unidade se tributa, e por quê.

    `produto` vazio significa "não sei" — e vem sempre com `revisar=True`. Não
    há exceção neste módulo: a confiança da classificação não recusa, emite
    tudo ranqueado para o revisor decidir.
    """

    produto: str = ""
    unidade_tributada: str = ""
    fator: Decimal | None = None
    confianca: str = BAIXA
    porque: str = ""
    revisar: bool = False

    @property
    def entra_na_tese(self) -> bool:
        """Se este produto gera o crédito que o módulo apura.

        Falso para lubrificante (outra tese) e etanol hidratado (dúvida aberta):
        os dois aparecem no relatório, fora do total.
        """
        return tab_combustivel.entra_na_tese(self.produto)


def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def normalizar(descricao: str) -> str:
    """A descrição na forma canônica, que é o que colapsa 132 em poucas.

    Tira, nesta ordem: os parênteses do bico de bomba, os pontos de
    preenchimento, os acentos, a pontuação; e colapsa `S-10`, `S 10` e `BS10`
    em `S10`. Não tira marca nem variante — `ORIGINAL` e `ADITIVADA` ficam,
    porque quem decide o produto é a busca de termo, e tirar palavra é tirar
    evidência de quem revisa.
    """
    texto = sem_acento((descricao or "").upper())
    texto = _PARENTESES.sub(" ", texto)
    texto = _PONTOS_DE_PREENCHIMENTO.sub(" ", texto)
    texto = _ENXOFRE.sub(lambda m: f"S{m.group(1)}", texto)
    texto = _NAO_ALFANUMERICO.sub(" ", texto)
    return _ESPACOS.sub(" ", texto).strip()


# Palavras que não distinguem produto nenhum neste universo de sete: marca
# (`ORIGINAL` é Ipiranga, `IPIMAX` também), embalagem, e os qualificadores de
# grau que acompanham o combustível sem mudar o que ele é — `B` do diesel B e
# `C` da gasolina C **são** a tese.
#
# Só saem na forma canônica, que é chave de agrupamento. `normalizar` as mantém,
# porque o revisor decide lendo o texto e tirar palavra é tirar evidência.
RUIDO = frozenset({
    "OLEO", "ORIGINAL", "COMUM", "TIPO", "GRANEL", "ADITIVADA", "ADITIVADO",
    "IPIMAX", "B", "C", "DE", "DO", "DA", "P", "KG", "KGS", "LT", "LTS", "L",
})


def forma_canonica(descricao: str) -> str:
    """A descrição reduzida ao que decide o produto — a chave de agrupamento.

    É o que torna este classificador **conferível**: medido na empresa G, as 132
    descrições distintas de `27101921` colapsam para **3** formas, e as 26 da
    gasolina para **4**. Num universo de sete produtos, dá para revisar 100% uma
    vez — e aí a confiança passa a ser taxa de acerto medida, não número
    estimado. Nem o reenquadrador (milhares de NCM) nem o de-para (24.730
    itens) puderam fazer isso.

    Diferente de `normalizar`, que é a forma de leitura: esta tira marca e
    qualificador de grau. As duas existem porque servem a coisas opostas —
    agrupar quer menos informação, revisar quer mais.
    """
    palavras = [p for p in normalizar(descricao).split() if p not in RUIDO]
    return " ".join(palavras)


def chave_de_agrupamento(descricao: str, ncm: str) -> tuple[str, str]:
    """A chave que o revisor revisa: forma canônica e NCM.

    **Não é o `COD_ITEM`** — o posto gera um código por bico de bomba, e indexar
    por ele multiplicaria a fila de revisão sem acrescentar um produto.
    """
    return forma_canonica(descricao), (ncm or "").strip()


def _e_lubrificante_pelo_texto(normalizada: str) -> bool:
    return any(marca in normalizada for marca in _MARCAS_DE_LUBRIFICANTE)


def produto_pela_descricao(descricao: str) -> tuple[str, str, str]:
    """O produto que a descrição indica: `(produto, confiança, porquê)`.

    Só é consultada quando a NCM não decide — e é ela que salva as 86 linhas de
    `DIESEL S10` sem NCM. A ordem importa: o teste de lubrificante vem **antes**
    do de diesel, porque `OLEO MOTOR DIESEL SAE15` contém as duas palavras.
    """
    t = normalizar(descricao)
    if not t:
        return "", BAIXA, "descrição vazia"

    if _e_lubrificante_pelo_texto(t):
        return (LUBRIFICANTE, MEDIA,
                "a descrição tem marca de óleo lubrificante (grau SAE, 'óleo "
                "motor', graxa), que não existe em combustível")

    if "GLP" in t or "GAS LIQUEFEITO" in t or "LIQUEFEITO DE PETROLEO" in t:
        return GLP, MEDIA, "a descrição diz GLP"
    if "GASOLINA" in t:
        return GASOLINA, MEDIA, "a descrição diz GASOLINA"
    if "DIESEL" in t:
        return DIESEL, MEDIA, "a descrição diz DIESEL e não tem marca de óleo"
    if "ANIDRO" in t:
        return ETANOL_ANIDRO, MEDIA, "a descrição diz ANIDRO"
    if "ETANOL" in t or "ALCOOL" in t:
        return (ETANOL_HIDRATADO, MEDIA,
                "a descrição diz ETANOL ou ÁLCOOL, e sem 'anidro' o hidratado é "
                "o que se compra na bomba")
    return "", BAIXA, "a descrição não tem termo de combustível conhecido"


def fator_no_texto(descricao: str, unidade_tributada: str) -> Decimal | None:
    """O fator escrito na descrição, quando ele está lá.

    É onde o GLP põe o fardo: `P20 - GLP 20 KGS` e `20 KGS GLP ONU 1075 2.1`,
    dois formatos do mesmo cliente. Só aceita a unidade **que casa com a
    tributada** — `20LT` não serve para quem é tributado por quilo, e inventar
    densidade aqui seria calcular no lugar errado.
    """
    t = normalizar(descricao)
    for bruto, unidade in _FATOR_NO_TEXTO.findall(t):
        casa = (unidade.startswith("KG") and unidade_tributada == QUILO) or (
            unidade.startswith(("LT", "L")) and unidade_tributada == LITRO)
        if not casa:
            continue
        try:
            return Decimal(bruto.replace(".", "").replace(",", "."))
        except InvalidOperation:
            continue
    return None


def _fator_da_unidade(unidade: str, unidade_tributada: str, descricao: str,
                      conversao: dict[str, Decimal] | None,
                      ) -> tuple[Decimal | None, str]:
    """Quantas unidades tributadas cabem na unidade declarada, e de onde saiu."""
    declarada = (unidade or "").strip().upper()

    if conversao and (do_0220 := conversao.get(declarada)) is not None:
        return do_0220, f"fator {do_0220} do registro 0220 para {declarada!r}"

    se_litro = unidade_tributada == LITRO and declarada in UNIDADES_DE_LITRO
    se_quilo = unidade_tributada == QUILO and declarada in UNIDADES_DE_QUILO
    if se_litro or se_quilo:
        return Decimal(1), f"{declarada!r} já é a unidade tributada"

    if (do_texto := fator_no_texto(descricao, unidade_tributada)) is not None:
        return do_texto, f"fator {do_texto} lido na descrição"

    if declarada in UNIDADES_DE_EMBALAGEM:
        return None, (f"{declarada!r} é embalagem e o fator não está no 0220 "
                      f"nem na descrição")
    return None, f"{declarada!r} não é unidade conhecida para {unidade_tributada}"


def classificar(descricao_do_item: str, ncm: str, unidade: str,
                descricao_no_documento: str = "",
                conversao: dict[str, Decimal] | None = None) -> Classificacao:
    """Classifica uma linha de compra. **Nunca levanta.**

    `descricao_do_item` é a do cadastro (`0200`) e `descricao_no_documento` a do
    `C170` — as duas entram, porque o fornecedor escreve uma coisa na nota e o
    cliente cadastrou outra, e a evidência do revisor são ambas.

    `conversao` é o `0220` daquele item, quando houver: `UNID_CONV` → `FAT_CONV`.
    """
    texto = f"{descricao_do_item} {descricao_no_documento}".strip()

    # a resposta categórica primeiro: parafuso é capítulo 73 e não é
    # combustível em nenhuma circunstância. Sem isto a fila de revisão recebe
    # toda a compra comum da empresa — 10.066 linhas na empresa G
    if tab_combustivel.fora_das_posicoes(ncm):
        return Classificacao(
            produto=FORA, confianca=ALTA,
            porque=f"NCM {ncm} não é de posição de combustível nem de "
                   f"lubrificante ({', '.join(tab_combustivel.POSICOES_DE_INTERESSE)})")

    pela_ncm = tab_combustivel.produto_de(ncm)
    pelo_texto, confianca_do_texto, porque_do_texto = produto_pela_descricao(texto)

    if pela_ncm:
        exata = (ncm or "").strip() in tab_combustivel.POR_NCM
        discordam = bool(pelo_texto) and pelo_texto != pela_ncm
        confianca = ALTA if exata and not discordam else MEDIA
        porque = (f"NCM {ncm} é {pela_ncm}"
                  + ("" if exata else ", pela subposição")
                  + (f"; a descrição sugeria {pelo_texto} — {porque_do_texto}"
                     if discordam else ""))
        return _montar(pela_ncm, unidade, texto, conversao, confianca, porque,
                       revisar=discordam)

    if pelo_texto:
        return _montar(pelo_texto, unidade, texto, conversao, confianca_do_texto,
                       f"sem NCM; {porque_do_texto}", revisar=True)

    return Classificacao(
        confianca=BAIXA, revisar=True,
        porque=(f"NCM {ncm!r} não está na tabela e {porque_do_texto}"
                if (ncm or "").strip()
                else f"sem NCM e {porque_do_texto}"))


def _montar(produto: str, unidade: str, descricao: str,
            conversao: dict[str, Decimal] | None, confianca: str, porque: str,
            revisar: bool) -> Classificacao:
    """Completa a classificação com a unidade tributada e o fator."""
    if produto == FORA:
        return Classificacao(produto=FORA, confianca=confianca, porque=porque,
                             revisar=revisar)

    unidade_tributada = UNIDADE.get(produto, "")
    if not unidade_tributada:
        # lubrificante e etanol hidratado não são do monofásico: não têm unidade
        # tributada por ad rem, e a alíquota deles é percentual sobre o valor
        return Classificacao(produto=produto, confianca=confianca,
                             porque=f"{porque}; tributado por percentual, "
                                    f"sem unidade ad rem",
                             revisar=revisar)

    fator, de_onde = _fator_da_unidade(unidade, unidade_tributada, descricao,
                                       conversao)
    return Classificacao(
        produto=produto,
        unidade_tributada=unidade_tributada,
        fator=fator,
        confianca=confianca,
        porque=f"{porque}; {de_onde}",
        # fator que não saiu é revisão obrigatória: multiplicar por 1 por
        # omissão erraria vinte vezes num botijão de 20 kg
        revisar=revisar or fator is None,
    )
