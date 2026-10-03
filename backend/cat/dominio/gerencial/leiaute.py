"""Descobrir a forma do arquivo antes de tentar lê-lo.

O relatório gerencial não tem leiaute publicado: cada ERP exporta do seu jeito
e a mesma empresa muda de um ano para o outro. Em vez de cadastrar formato por
empresa — que envelhece e ninguém mantém — o sistema **descobre** três coisas
do próprio arquivo:

1. **o separador**, pelo caractere cuja contagem se repete igual em mais
   linhas. Consistência vale mais que quantidade: no relatório da empresa V o
   ponto-e-vírgula aparece 45 vezes na primeira linha, mas só dentro de nomes
   de coluna (``Qtde;Unitária``); o pipe é o que dá o mesmo número em toda
   linha;
2. **onde começa o cabeçalho**, porque o exportador às vezes despeja a própria
   consulta SQL no topo do arquivo;
3. **se o cabeçalho ocupa duas linhas**. O mesmo ERP exporta o cabeçalho de
   dois níveis de dois jeitos: junto numa linha só, com ponto-e-vírgula
   (``Valor ST;Informada``), ou em duas linhas físicas (``Devoluções`` em cima
   de ``Venda``). Só há dois níveis quando a linha de cima tem nomes
   repetidos — cabeçalho de um nível só não repete nome.

Linha cujo número de campos não bate com o do cabeçalho é lixo do exportador e
é descartada, com contagem e amostra no log para ninguém descobrir tarde que
perdeu registro.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

DELIMITADORES = ("|", "\t", ";", ",")
LINHAS_DE_AMOSTRA = 40

# um campo "parece dado" quando tem cara de número ou de data; cabeçalho não
# tem. É o que separa a segunda linha de um cabeçalho de dois níveis
# (``Entradas``, ``Saídas``) do primeiro registro de verdade.
_RE_PARECE_DADO = re.compile(r"^-?[\d.,]{1,20}$|^\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}$")


class LeiauteNaoReconhecido(ValueError):
    """Nem com farejamento dá para dizer onde estão as colunas."""


@dataclass(frozen=True)
class Leiaute:
    separador: str
    campos: int
    linha_do_cabecalho: int
    cabecalho: tuple[str, ...]
    niveis: int = 1

    @property
    def primeira_linha_de_dado(self) -> int:
        return self.linha_do_cabecalho + self.niveis


@dataclass
class Descarte:
    """O que foi jogado fora ao ler, para o log e para a tela de importação."""

    linhas: int = 0
    amostra: list[str] = field(default_factory=list)

    def registrar(self, numero: int, linha: str, campos: int) -> None:
        self.linhas += 1
        if len(self.amostra) < 3:
            self.amostra.append(f"linha {numero}: {campos} campos — {linha[:80]}")


def farejar_separador(linhas: list[str]) -> tuple[str, int]:
    melhor = ("", 0, 0)  # (separador, linhas que concordam, campos)
    for sep in DELIMITADORES:
        contagens = Counter(l.count(sep) for l in linhas if l.count(sep) > 0)
        if not contagens:
            continue
        ocorrencias, concordam = contagens.most_common(1)[0]
        if (concordam, ocorrencias) > (melhor[1], melhor[2]):
            melhor = (sep, concordam, ocorrencias)
    if not melhor[0]:
        raise LeiauteNaoReconhecido(
            "nenhum separador conhecido aparece no arquivo "
            f"({', '.join(repr(d) for d in DELIMITADORES)})"
        )
    return melhor[0], melhor[2] + 1


def _tem_nome_repetido(campos: list[str]) -> bool:
    nomes = [c.strip().lower() for c in campos if c.strip()]
    return len(nomes) != len(set(nomes))


def _parece_linha_de_dado(campos: list[str]) -> bool:
    return any(_RE_PARECE_DADO.match(c.strip()) for c in campos if c.strip())


def farejar(linhas: list[str]) -> Leiaute:
    """Separador, linha do cabeçalho e quantos níveis ele tem."""
    uteis = [l for l in linhas if l.strip()][:LINHAS_DE_AMOSTRA]
    if not uteis:
        raise LeiauteNaoReconhecido("arquivo vazio")

    sep, campos = farejar_separador(uteis)

    inicio = next(
        (i for i, l in enumerate(uteis) if l.count(sep) + 1 == campos), None
    )
    if inicio is None:
        raise LeiauteNaoReconhecido(
            f"nenhuma linha tem os {campos} campos esperados para o separador {sep!r}"
        )

    primeiro = uteis[inicio].split(sep)
    niveis = 1
    if inicio + 1 < len(uteis):
        segundo = uteis[inicio + 1].split(sep)
        if (
            len(segundo) == campos
            and _tem_nome_repetido(primeiro)
            and not _parece_linha_de_dado(segundo)
        ):
            niveis = 2
            primeiro = [
                " ".join(p for p in (a.strip(), b.strip()) if p)
                for a, b in zip(primeiro, segundo)
            ]

    return Leiaute(
        separador=sep,
        campos=campos,
        linha_do_cabecalho=inicio,
        cabecalho=tuple(primeiro),
        niveis=niveis,
    )
