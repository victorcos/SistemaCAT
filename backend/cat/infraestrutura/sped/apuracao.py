"""O bloco M: a apuração das contribuições, e os ajustes dela.

É onde a EFD-Contribuições diz quanto de PIS e de COFINS se apurou no período,
por código de contribuição, e o que foi ajustado para mais ou para menos. Os
blocos C e D dizem o que aconteceu; o M diz no que deu.

## PIS e COFINS são espelhos

Registro a registro, a apuração das duas é a mesma estrutura com números
diferentes. É por isso que este módulo tem **uma** função e uma tabela, e não
oito funções quase idênticas — que é como o projeto de origem as tinha, cada uma
com suas cinquenta linhas repetidas.

| | crédito | base do crédito | ajuste do crédito | contribuição | detalhe | ajuste |
|---|---|---|---|---|---|---|
| **PIS** | M100 | M105 | M110 | M200 | M210 | M220 |
| **COFINS** | M500 | M505 | M510 | M600 | M610 | M620 |

## A cadeia

Cada linha sai do registro mais fundo, carregando os de cima — e "o de cima" é
simplesmente **o último que apareceu**, porque o SPED escreve pai antes de
filho. A cadeia do ajuste da contribuição tem três níveis:

```
M200 (a contribuição do período)
└── M210 (por código de contribuição)
    └── M220 (cada ajuste dela)
```

Pai que ainda não apareceu entra em branco em vez de a linha sumir: arquivo de
cliente tem bloco truncado, e perder o ajuste porque o M200 faltou seria perder
valor apurado sem dizer nada.

Portado do projeto Quebra de SPED em 22/09/2026.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.log import obter_log

log = obter_log(__name__)

# As cadeias do bloco M, do ancestral à folha. O nome é o do registro que sai
# em cada linha — é por ele que a etapa pede.
CADEIAS: dict[str, tuple[str, ...]] = {
    # PIS
    "M105": ("M100", "M105"),      # base de cálculo do crédito
    "M110": ("M100", "M110"),      # ajustes do crédito
    "M210": ("M200", "M210"),      # detalhamento da contribuição
    "M220": ("M200", "M210", "M220"),   # ajustes da contribuição
    # COFINS — o mesmo, cinco centenas adiante
    "M505": ("M500", "M505"),
    "M510": ("M500", "M510"),
    "M610": ("M600", "M610"),
    "M620": ("M600", "M610", "M620"),
}

# qual contribuição cada cadeia apura, para quem lê a planilha
CONTRIBUICAO = {r: ("COFINS" if r[1] in "56" else "PIS/PASEP") for r in CADEIAS}


class CadeiaDesconhecida(KeyError):
    """Pediram um registro do bloco M que este módulo não sabe montar."""


def _nomeados(prefixo: str, valores: list[str], nomes: tuple[str, ...]) -> dict[str, str]:
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


def cadeia(caminho: str, codificacao: str, folha: str) -> Iterator[dict[str, str]]:
    """Cada linha do registro pedido, com os pais dele na mesma linha.

    `folha` é o registro que sai — M210, M620, M105… A cadeia inteira vem de
    `CADEIAS`, e uma passada sequencial basta: o SPED escreve pai antes de filho.
    """
    if folha not in CADEIAS:
        raise CadeiaDesconhecida(
            f"Não sei montar {folha}. Sei: {', '.join(sorted(CADEIAS))}."
        )
    ordem = CADEIAS[folha]
    nomes = {r: nomes_dos_campos(r) for r in ordem}
    em_bytes = {r.encode("ascii"): r for r in ordem}
    folha_b = folha.encode("ascii")
    # o contexto corrente de cada ancestral; a folha não guarda contexto
    corrente: dict[str, list[str]] = {r: [] for r in ordem[:-1]}
    saíram = 0

    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in em_bytes:
                continue
            valores = campos(linha.decode(codificacao, errors="replace"))
            nome = em_bytes[registro]
            if registro != folha_b:
                corrente[nome] = valores
                # trocou de pai: o que estava aberto abaixo dele não vale mais
                nivel = ordem.index(nome)
                for abaixo in ordem[nivel + 1:-1]:
                    corrente[abaixo] = []
                continue
            pronta: dict[str, str] = {}
            for ancestral in ordem[:-1]:
                pronta.update(_nomeados(ancestral, corrente[ancestral], nomes[ancestral]))
            pronta.update(_nomeados(folha, valores, nomes[folha]))
            saíram += 1
            yield pronta

    log.info("apuração do sped lida", extra={
        "arquivo": os.path.basename(caminho), "registro": folha,
        "contribuicao": CONTRIBUICAO[folha], "linhas": saíram,
        "cadeia": " > ".join(ordem),
    })


def colunas_da_cadeia(folha: str) -> list[str]:
    """Os nomes das colunas da cadeia, na ordem — do ancestral à folha."""
    if folha not in CADEIAS:
        raise CadeiaDesconhecida(f"Não sei montar {folha}.")
    ordem = CADEIAS[folha]
    return [f"{prefixo}_{nome}"
            for prefixo in (*ordem[:-1], folha)
            for nome in nomes_dos_campos(prefixo)]


def espelho_de(folha: str) -> str:
    """O registro equivalente na outra contribuição: M210 ↔ M610.

    PIS e COFINS são a mesma estrutura, e a diferença entre as duas cadeias é
    somar 400 ao número. Serve para quem apura as duas e quer garantir que leu o
    mesmo recorte dos dois lados.
    """
    if folha not in CADEIAS:
        raise CadeiaDesconhecida(f"Não sei montar {folha}.")
    numero = int(folha[1:])
    return f"M{numero + 400 if numero < 500 else numero - 400}"
