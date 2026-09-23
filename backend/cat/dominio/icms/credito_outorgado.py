"""Quais itens vendidos entram no crédito outorgado, item a item.

O benefício é do produto, não da nota: a legislação estadual concede o crédito
sobre a saída de uma lista de mercadorias, e o trabalho do analista é dizer
quais das milhões de linhas vendidas são daquela lista. O item do XML traz duas
pistas — a **NCM**, que o emitente classificou, e a **descrição**, que ele
escreveu — e o filtro desta casa é feito das duas.

Portado do projeto `Quebra de SPED` (`src/credito_outorgado/service.py`), onde a
funcionalidade nasceu e roda desde então. A regra é a de lá:

**A descrição manda.** Item entra se a descrição contiver algum termo
cadastrado. Bater só a NCM **não basta** — e isso não é descuido: a NCM é
declarada pelo emitente e erra com frequência (a mesma farinha vem 11010010 num
fornecedor e 19019090 noutro), enquanto a descrição é o que o dono do negócio
reconhece como o produto dele. A NCM entra como **confirmação**: quando as duas
batem, o item sai marcado `NCM+DESCRIÇÃO`, e é por esse rótulo que se separa o
que está redondo do que precisa de olho.

Duas diferenças conscientes em relação à origem, ambas na comparação de NCM:

* **casa por prefixo, e não por "contém"** — lá, o código cadastrado era
  procurado em qualquer posição do NCM do item (`"690" in "21069090"` dava
  verdadeiro). NCM é hierárquica: os dígitos valem da esquerda para a direita,
  e `1905` é o capítulo do que se compara, não uma sequência solta;
* **o zero à esquerda fica** — lá, cadastro e item perdiam os zeros iniciais
  antes de comparar, o que juntava o capítulo 02 (carnes) com o 20 (preparações
  de hortaliças) em alguns casos.

Como a NCM sozinha nunca decide elegibilidade, as duas mudanças só podem mexer
no **rótulo** de um item já elegível pela descrição — nunca em quem entra.

O acento **não** é ignorado, também como na origem: quem cadastra "PAO" não
acha "PÃO FRANCÊS". É deliberado — dobrar acento faria itens entrarem aqui que
na origem ficavam de fora, e os dois resultados precisam poder ser comparados.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

MOTIVO_DESCRICAO = "DESCRIÇÃO"
MOTIVO_NCM_E_DESCRICAO = "NCM+DESCRIÇÃO"
MOTIVO_SEM_FILTRO = "SEM FILTRO"


@dataclass(frozen=True)
class Veredito:
    """Se o item entra, e por quê. O motivo vai para a planilha e para a tela."""

    elegivel: bool
    motivo: str


ELEGIVEL_POR_DESCRICAO = Veredito(True, MOTIVO_DESCRICAO)
ELEGIVEL_POR_NCM_E_DESCRICAO = Veredito(True, MOTIVO_NCM_E_DESCRICAO)
ELEGIVEL_SEM_FILTRO = Veredito(True, MOTIVO_SEM_FILTRO)
DESCARTADO = Veredito(False, "")


def _so_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _sem_repetir(itens: Iterable[str]) -> tuple[str, ...]:
    """Sem repetição e na ordem em que foram cadastrados — a ordem é do usuário."""
    return tuple(dict.fromkeys(i for i in itens if i))


@dataclass(frozen=True)
class Filtro:
    """A lista de NCMs e de termos que define o benefício deste trabalho.

    É configuração do trabalho, não do sistema: a mesma casa atende um atacado
    de alimentos e uma farmácia, e a lista de um não diz nada sobre o outro.

    `sem_filtro` é a saída de emergência da origem (lá, a caixa "desativar
    filtros"): roda a varredura inteira sem julgar nada, para quem quer ver o
    universo antes de escrever o primeiro termo. Tudo sai elegível, marcado
    `SEM FILTRO` — o rótulo existe para que ninguém confunda essa lista com uma
    apuração de benefício.
    """

    ncms: tuple[str, ...] = ()
    termos: tuple[str, ...] = ()
    sem_filtro: bool = False

    @classmethod
    def de(cls, ncms: Iterable[str] = (), termos: Iterable[str] = (),
           sem_filtro: bool = False) -> "Filtro":
        """Normaliza o que veio da tela: NCM só com dígitos, termo em maiúsculas."""
        return cls(
            ncms=_sem_repetir(_so_digitos(n) for n in ncms),
            termos=_sem_repetir(t.strip().upper() for t in termos),
            sem_filtro=sem_filtro,
        )

    @property
    def julga(self) -> bool:
        """Se há o que julgar. Sem termo e sem a chave geral, nada seria elegível."""
        return self.sem_filtro or bool(self.termos)

    def avaliar(self, descricao: str, ncm: str) -> Veredito:
        if self.sem_filtro:
            return ELEGIVEL_SEM_FILTRO
        if not any(termo in descricao.upper() for termo in self.termos):
            return DESCARTADO
        return ELEGIVEL_POR_NCM_E_DESCRICAO if self.bate_ncm(ncm) else ELEGIVEL_POR_DESCRICAO

    def bate_ncm(self, ncm: str) -> bool:
        """A NCM do item começa por algum código cadastrado.

        O cadastro costuma ter seis dígitos (`190590`) e o XML traz oito
        (`19059090`): a posição do item dentro da subposição não muda o
        benefício, então o prefixo é a comparação certa.
        """
        digitos = _so_digitos(ncm)
        return bool(digitos) and any(digitos.startswith(codigo) for codigo in self.ncms)
