"""Nenhuma planilha pode ter duas colunas com o mesmo título.

No xlsx a faixa do bloco separa "PIS" (apurado) de "PIS" (que volta). No CSV
não há faixa: saem duas colunas com o mesmo nome, e quem abre no Excel ou
aponta uma dinâmica para o arquivo não tem como saber qual é qual. Aconteceu
com a planilha das exclusões, e foi descoberto na hora de comparar com o MA.
"""

from __future__ import annotations

import pytest

from cat.infraestrutura.planilhas.conferencia import Coluna, titulos_do_csv
from cat.infraestrutura.planilhas.exclusao_do_icms import COLUNAS_DA_EXCLUSAO_DO_ICMS
from cat.infraestrutura.planilhas.exclusao_do_icms_st import (
    COLUNAS_DA_EXCLUSAO_DO_ICMS_ST,
)
from cat.infraestrutura.planilhas.exclusao_do_iss import COLUNAS_DA_EXCLUSAO_DO_ISS
from cat.infraestrutura.planilhas.exclusoes import COLUNAS_DAS_EXCLUSOES
from cat.infraestrutura.planilhas.itens_do_xml import CAMPOS as CAMPOS_DO_XML
from cat.infraestrutura.planilhas.quebra_de_sped import (
    COLUNAS_ENTRADAS,
    COLUNAS_RAZAO,
)

CATALOGOS: dict[str, tuple[Coluna, ...]] = {
    "exclusões": COLUNAS_DAS_EXCLUSOES,
    "exclusão do ICMS": COLUNAS_DA_EXCLUSAO_DO_ICMS,
    "exclusão do ICMS-ST": COLUNAS_DA_EXCLUSAO_DO_ICMS_ST,
    "exclusão do ISS": COLUNAS_DA_EXCLUSAO_DO_ISS,
    "itens do XML": CAMPOS_DO_XML,
    "consulta de entradas": COLUNAS_ENTRADAS,
    "razão contábil": COLUNAS_RAZAO,
}


@pytest.mark.parametrize("nome, colunas", CATALOGOS.items())
def test_nenhum_titulo_se_repete_no_csv(nome: str, colunas: tuple[Coluna, ...]):
    titulos = titulos_do_csv(colunas)
    repetidos = sorted({t for t in titulos if titulos.count(t) > 1})

    assert not repetidos, f"{nome}: título repetido no CSV — {repetidos}"


def test_o_bloco_entra_so_onde_havia_ambiguidade():
    """Arquivo que já circula não muda de cabeçalho sem motivo."""
    colunas = (
        Coluna("chave", "Chave", "texto", 10, "Documento"),
        Coluna("valor_pis", "Valor", "numero", 10, "PIS"),
        Coluna("valor_cofins", "Valor", "numero", 10, "COFINS"),
    )

    assert titulos_do_csv(colunas) == ["Chave", "PIS - Valor", "COFINS - Valor"]


def test_sem_bloco_o_titulo_fica_como_esta():
    """Não dá para desambiguar o que não tem bloco; melhor não inventar nome."""
    colunas = (
        Coluna("a", "Valor", "numero", 10),
        Coluna("b", "Valor", "numero", 10),
    )

    assert titulos_do_csv(colunas) == ["Valor", "Valor"]


@pytest.mark.parametrize("nome, colunas", CATALOGOS.items())
def test_nenhum_campo_se_repete(nome: str, colunas: tuple[Coluna, ...]):
    """Campo repetido sairia duas vezes com o mesmo valor."""
    campos = [c.campo for c in colunas]
    assert len(campos) == len(set(campos)), nome
