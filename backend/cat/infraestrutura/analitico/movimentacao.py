"""Consolidar os parquets da extração de movimentos e resumir, em DuckDB.

Duas coisas, a partir do que `movimentos.py` gravou:

1. **o cadastro que vale** — o 0200 se repete a cada período; fica, por
   estabelecimento e código, o do período mais recente (`itens.parquet`);
2. **os movimentos prontos para o razão** — cada C170/C810 com a descrição,
   NCM e CEST do cadastro, e com a **classificação da conferência**: conferido,
   pendente ou sem chave. Ordenados por estabelecimento, item e data, que é a
   ordem em que a ficha se lê (`movimentos.parquet`).

A marca da conferência é a única junção contra o lado grande, e é feita
pelo lado pequeno de propósito: a lista de conferidos de uma base saudável
tem dezenas de milhões de chaves, mas os movimentos com item são só as
entradas — poucos milhões de chaves distintas. Primeiro se reduz a lista de
conferidos a essas chaves (SEMI JOIN, com as chaves dos movimentos do lado
da construção), e só então se marca cada linha.

Mesmas regras do confronto para não estourar memória: conexão em arquivo com
`temp_directory`, `memory_limit` e `preserve_insertion_order` desligado. As
contagens do resumo saem dos parquets já gravados, uma varredura cada.
"""

from __future__ import annotations

import os
from decimal import Decimal

from cat.dominio.cat42.conferencia import Fatia
from cat.dominio.cat42.movimentacao import ResumoDaMovimentacao
from cat.infraestrutura.analitico.confronto import _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.movimentos import (  # noqa: F401
    ARQUIVO_ANALITICO,
    ARQUIVO_DOCUMENTOS,
    ARQUIVO_INVENTARIO,
    ARQUIVO_ITENS_DA_EFD,
    ARQUIVO_MOVIMENTOS_BRUTOS,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ITENS = "itens.parquet"
ARQUIVO_MOVIMENTOS = "movimentos.parquet"

_MODELOS = {"01": "NF modelo 1/1-A", "55": "NF-e", "59": "CF-e-SAT", "65": "NFC-e",
            "57": "CT-e", "04": "NF de Produtor"}
_CLASSIFICACAO = {
    "conferido": "Documento conferido",
    "pendente": "Documento pendente na conferência",
    "sem_chave": "Sem chave — conferir à mão",
    "nao_conferido": "Sem conferência",
}


def consolidar(destino: str, conferidos: str | None) -> ResumoDaMovimentacao:
    """Grava `itens`, `movimentos` e `analitico` finais e devolve o resumo."""
    p = lambda nome: _escapar(os.path.join(destino, nome))  # noqa: E731
    con = _abrir(destino)
    try:
        # 1. o cadastro mais recente por estabelecimento e código
        con.execute(f"""
            COPY (
                SELECT * FROM read_parquet('{p(ARQUIVO_ITENS_DA_EFD)}')
                QUALIFY row_number() OVER (
                    PARTITION BY cnpj, codigo
                    ORDER BY competencia DESC NULLS LAST, arquivo DESC) = 1
            ) TO '{p(ARQUIVO_ITENS)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        # 2. os movimentos com cadastro e com a marca da conferência.
        # A lista de conferidos é uma linha por chave; sem ela, ninguém é
        # marcado e o resumo avisa.
        if conferidos and os.path.isfile(conferidos):
            # as chaves dos movimentos (lado pequeno) contra a lista de
            # conferidos (lado grande): o que sobra é o que se marca
            con.execute(f"""
                CREATE TABLE chaves_dos_movimentos AS
                SELECT DISTINCT chave FROM read_parquet('{p(ARQUIVO_MOVIMENTOS_BRUTOS)}')
                WHERE length(chave) = 44
            """)
            con.execute(f"""
                CREATE TABLE conferidos AS
                SELECT k.chave FROM chaves_dos_movimentos k
                SEMI JOIN read_parquet('{_escapar(conferidos)}') c ON c.chave = k.chave
            """)
            classificacao = """
                CASE WHEN length(m.chave) <> 44 THEN 'sem_chave'
                     WHEN c.chave IS NOT NULL THEN 'conferido'
                     ELSE 'pendente' END"""
            juncao = "LEFT JOIN conferidos c ON c.chave = m.chave"
            usada = True
        else:
            classificacao = "'nao_conferido'"
            juncao = ""
            usada = False
        con.execute(f"""
            COPY (
                SELECT m.*,
                       i.descricao, i.codigo_barras, i.ncm, i.cest,
                       i.unidade AS unidade_cadastro,
                       {classificacao} AS classificacao
                FROM read_parquet('{p(ARQUIVO_MOVIMENTOS_BRUTOS)}') m
                LEFT JOIN read_parquet('{p(ARQUIVO_ITENS)}') i
                       ON i.cnpj = m.cnpj AND i.codigo = m.codigo
                {juncao}
                ORDER BY m.cnpj, m.codigo, m.data, m.numero_documento, m.numero_item
            ) TO '{p(ARQUIVO_MOVIMENTOS)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        try:
            os.remove(os.path.join(destino, ARQUIVO_MOVIMENTOS_BRUTOS))
        except OSError:
            log.warning("não deu para apagar parquet intermediário",
                        extra={"arquivo": ARQUIVO_MOVIMENTOS_BRUTOS})

        resumo = _resumir(con, p, usada)
    finally:
        con.close()
        _limpar(destino)

    log.info("movimentos consolidados",
             extra={"documentos": resumo.documentos,
                    "com_item": resumo.documentos_com_item,
                    "saidas_sem_item": resumo.saidas_sem_item,
                    "movimentos": resumo.movimentos,
                    "itens": resumo.itens_cadastrados,
                    "sem_cadastro": resumo.itens_sem_cadastro,
                    "inventarios": resumo.inventarios})
    return resumo


def _resumir(con, p, conferencia_usada: bool) -> ResumoDaMovimentacao:
    r = ResumoDaMovimentacao(conferencia_usada=conferencia_usada)

    docs = p(ARQUIVO_DOCUMENTOS)
    (r.documentos, r.documentos_com_item, r.entradas_sem_item,
     r.saidas_sem_item, arquivos) = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE itens > 0),
               count(*) FILTER (WHERE operacao = 'entrada' AND itens = 0),
               count(*) FILTER (WHERE operacao = 'saida' AND itens = 0),
               count(DISTINCT arquivo)
        FROM read_parquet('{docs}')
    """).fetchone()
    r.arquivos = arquivos
    r.estabelecimentos = [c for (c,) in con.execute(
        f"SELECT DISTINCT cnpj FROM read_parquet('{docs}') "
        "WHERE cnpj IS NOT NULL AND cnpj <> '' ORDER BY 1").fetchall()]
    r.saidas_sem_item_por_modelo = [
        Fatia(rotulo=_MODELOS.get(m, f"Modelo {m}"), documentos=n, valor=_dec(v),
              codigo=m)
        for m, n, v in con.execute(f"""
            SELECT modelo, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{docs}') WHERE operacao = 'saida' AND itens = 0
            GROUP BY 1 ORDER BY 2 DESC, 1
        """).fetchall()
    ]

    # o analítico diz quanto dessas saídas é CST 60: mercadoria com ST retida,
    # exatamente o que o razão precisa por item e a EFD não detalha
    valor, valor_st = con.execute(f"""
        SELECT coalesce(sum(valor_operacao), 0),
               coalesce(sum(valor_operacao) FILTER (WHERE right(cst_icms, 2) = '60'), 0)
        FROM read_parquet('{p(ARQUIVO_ANALITICO)}')
        WHERE operacao = 'saida' AND NOT tem_item
    """).fetchone()
    r.valor_saidas_sem_item, r.valor_saidas_sem_item_st = _dec(valor), _dec(valor_st)

    mov = p(ARQUIVO_MOVIMENTOS)
    (r.movimentos, r.movimentos_entrada, r.movimentos_saida, v_ent, v_sai, st,
     r.itens_movimentados, r.itens_sem_cadastro) = con.execute(f"""
        SELECT count(*),
               count(*) FILTER (WHERE operacao = 'entrada'),
               count(*) FILTER (WHERE operacao = 'saida'),
               coalesce(sum(valor) FILTER (WHERE operacao = 'entrada'), 0),
               coalesce(sum(valor) FILTER (WHERE operacao = 'saida'), 0),
               coalesce(sum(valor_st) FILTER (WHERE operacao = 'entrada'), 0),
               count(DISTINCT codigo),
               count(DISTINCT codigo) FILTER (WHERE descricao IS NULL)
        FROM read_parquet('{mov}')
    """).fetchone()
    r.valor_entradas, r.valor_saidas, r.st_nas_entradas = _dec(v_ent), _dec(v_sai), _dec(st)

    r.por_cst = [
        Fatia(rotulo=f"CST {c}", documentos=n, valor=_dec(v), codigo=c)
        for c, n, v in con.execute(f"""
            SELECT cst_icms, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{mov}') WHERE operacao = 'entrada'
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 12
        """).fetchall()
    ]
    r.por_classificacao = [
        Fatia(rotulo=_CLASSIFICACAO.get(c, c), documentos=n, valor=_dec(v), codigo=c)
        for c, n, v in con.execute(f"""
            SELECT classificacao, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{mov}') GROUP BY 1 ORDER BY 2 DESC, 1
        """).fetchall()
    ]

    r.itens_cadastrados = con.execute(
        f"SELECT count(*) FROM read_parquet('{p(ARQUIVO_ITENS)}')").fetchone()[0]

    r.inventarios, r.itens_em_estoque, valor = con.execute(f"""
        SELECT count(DISTINCT (cnpj, data_inventario)), count(*),
               coalesce(sum(valor), 0)
        FROM read_parquet('{p(ARQUIVO_INVENTARIO)}')
    """).fetchone()
    r.valor_em_estoque = _dec(valor)
    return r


def _dec(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))
