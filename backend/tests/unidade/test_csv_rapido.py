"""O CSV escrito pelo DuckDB tem de ser byte a byte o que o módulo csv escrevia.

A regra de formato mora em `_texto_para_csv`; o `_gerar_csv` a repete em SQL
porque é 20 vezes mais rápido. Este teste é o que impede as duas de divergirem.
"""

import csv
import hashlib
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.planilhas import conferencia as planilhas
from cat.infraestrutura.planilhas.conferencia import Coluna

COLUNAS = (
    Coluna("texto", "Texto; com separador"),
    Coluna("vazio", "Vazio"),
    Coluna("nulo", "Nulo"),
    Coluna("ausente", "Coluna que o parquet não tem"),
    Coluna("valor", "Valor", "numero"),
    Coluna("quantidade", "Quantidade", "quantidade"),
    Coluna("inteiro", "Inteiro", "numero_inteiro"),
    Coluna("dia", "Dia", "data"),
    Coluna("dia_como_texto", "Dia como texto", "texto"),
    Coluna("marcado", "Marcado"),
    Coluna("decimal_como_texto", "Decimal como texto"),
    Coluna("fonte", "Fonte traduzida"),
    Coluna("modelo", "Modelo"),
    Coluna("classificacao", "Classificação traduzida"),
)


def antigo(parquet, destino, modelos=None, classificacoes=None):
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow([c.titulo for c in COLUNAS])
        for r in planilhas._filtradas(parquet, modelos, classificacoes):
            w.writerow(["" if r.get(c.campo) is None or r.get(c.campo) == ""
                        else planilhas._texto_para_csv(r.get(c.campo), c) for c in COLUNAS])


def test_o_duckdb_escreve_o_mesmo_csv_que_o_modulo_csv(tmp_path):
    parquet = tmp_path / "linhas.parquet"
    pq.write_table(pa.table({
        "texto": ['com "aspas"', "linha\nquebrada", "normal", None],
        "vazio": ["", "", "x", ""],
        "nulo": [None, "a", None, None],
        "valor": pa.array([Decimal("1.005"), Decimal("-0.004"), Decimal("123456.785"), None], pa.decimal128(18, 3)),
        "quantidade": [1.123456789, 2.0, None, 0.000005],
        "inteiro": [1, 20, None, 3],
        "dia": [date(2021, 5, 1), None, date(2024, 12, 31), date(2020, 1, 9)],
        "dia_como_texto": [date(2021, 5, 1), None, date(2024, 12, 31), date(2020, 1, 9)],
        "marcado": [True, False, None, True],
        "decimal_como_texto": pa.array([Decimal("1.50"), Decimal("0.00"), None, Decimal("10.10")], pa.decimal128(18, 2)),
        "fonte": ["documento", "estimado_pela_aliquota", "codigo_novo", None],
        "modelo": ["55", "65", "55", "59"],
        "classificacao": ["conferido", "pendente", "a_cobrar", "sem_chave"],
    }), parquet)

    hash_ = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    for filtro in ({}, {"modelos": frozenset({"55"})}, {"classificacoes": frozenset({"pendente", "a_cobrar"})},
                   {"modelos": frozenset()}):
        esperado, obtido = tmp_path / "antigo.csv", tmp_path / "novo.csv"
        antigo(str(parquet), str(esperado), **filtro)
        planilhas._gerar_csv(str(parquet), str(obtido), COLUNAS, **filtro)
        assert hash_(esperado) == hash_(obtido), (filtro, open(esperado, "rb").read(), open(obtido, "rb").read())
