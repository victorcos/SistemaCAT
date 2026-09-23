"""As fontes que a etapa abre: a consulta tem de valer no banco de verdade.

Existe por um erro que a suíte inteira não pegava. `SELECT DISTINCT caminho
ORDER BY competencia` roda no SQLite, onde os testes rodam, e o Postgres
recusa — e o sistema roda em Postgres. As duas etapas de PIS/COFINS morriam de
500 no canal interno, e a tela só dizia "o motor do sistema não respondeu".

Por isso o teste olha a consulta, e não o resultado: no SQLite o resultado sai
certo mesmo quando a consulta está errada.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso import apurar_contribuicoes, quebrar_sped
from cat.aplicacao.casos_de_uso.rodada import caminhos_do_lote, consulta_de_caminhos
from cat.dominio.lote import TipoDeArquivo
from cat.infraestrutura.repositorios.modelos import ArquivoDoLoteDB, Base, LoteDB

TIPOS = [TipoDeArquivo.SPED_CONTRIBUICOES, TipoDeArquivo.SPED_ECD, TipoDeArquivo.SPED_ECF]


def _colunas(trecho: str) -> list[str]:
    return [c.strip().removesuffix(" ASC").removesuffix(" DESC")
            for c in trecho.split(",") if c.strip()]


@pytest.mark.parametrize("tipo", TIPOS, ids=lambda t: t.value)
def test_distinct_enxerga_tudo_que_ordena(tipo: TipoDeArquivo) -> None:
    sql = str(consulta_de_caminhos(1, tipo).compile(dialect=postgresql.dialect()))
    assert "SELECT DISTINCT" in sql

    selecionadas = _colunas(re.search(r"SELECT DISTINCT (.+?) \nFROM", sql, re.S).group(1))
    ordenadas = _colunas(sql.rsplit("ORDER BY", 1)[1])
    faltando = [c for c in ordenadas if c not in selecionadas]
    assert not faltando, f"o Postgres recusa: ORDER BY {faltando} fora do SELECT DISTINCT"


def test_mesmo_arquivo_em_dois_lotes_sai_uma_vez_so() -> None:
    """A empresa reenvia a pasta e o arquivo entra de novo, em outro lote."""
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    with Session(motor) as s:
        s.add_all([LoteDB(id=1, projeto_id=7, pasta="Z:/um"),
                   LoteDB(id=2, projeto_id=7, pasta="Z:/dois")])
        for lote in (1, 2):
            s.add(ArquivoDoLoteDB(lote_id=lote, caminho="Z:/base/contrib_202401.txt",
                                  nome="contrib_202401.txt",
                                  tipo=TipoDeArquivo.SPED_CONTRIBUICOES.value))
        s.add(ArquivoDoLoteDB(lote_id=2, caminho="Z:/base/contrib_202402.txt",
                              nome="contrib_202402.txt",
                              tipo=TipoDeArquivo.SPED_CONTRIBUICOES.value))
        s.commit()

        achados = caminhos_do_lote(7, TipoDeArquivo.SPED_CONTRIBUICOES, s)

    assert achados == ["Z:/base/contrib_202401.txt", "Z:/base/contrib_202402.txt"]


def test_as_duas_etapas_de_piscofins_usam_a_mesma_consulta() -> None:
    """Uma só regra de "o que abrir": corrigir num lugar corrige nos dois."""
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    with Session(motor) as s:
        s.add(LoteDB(id=1, projeto_id=7, pasta="Z:/um"))
        for tipo in (TipoDeArquivo.SPED_CONTRIBUICOES, TipoDeArquivo.SPED_ECD,
                     TipoDeArquivo.SPED_ECF):
            s.add(ArquivoDoLoteDB(lote_id=1, caminho=f"Z:/base/{tipo.value}.txt",
                                  nome=f"{tipo.value}.txt", tipo=tipo.value))
        s.commit()

        contrib_quebra, ecds = quebrar_sped.fontes_do_projeto(7, s)
        contrib_apur, ecfs = apurar_contribuicoes.fontes_do_projeto(7, s)

    assert contrib_quebra == contrib_apur == ["Z:/base/sped_contribuicoes.txt"]
    assert ecds == ["Z:/base/sped_ecd.txt"]
    assert ecfs == ["Z:/base/sped_ecf.txt"]
