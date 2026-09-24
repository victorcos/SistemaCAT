"""A planilha dos itens do XML: quem escolhe as colunas é quem confere.

São 57 colunas possíveis e quase ninguém quer as 57. O que estes testes cobram:
que a escolha seja respeitada, que a ordem não dependa dela, e que uma escolha
estragada — campo que não existe mais, guardado no navegador — não derrube a
rodada nem devolva planilha vazia.
"""

from __future__ import annotations

import decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.analitico.itens_do_xml import ESQUEMA_ITENS_DO_XML
from cat.infraestrutura.planilhas.itens_do_xml import (
    CAMPOS,
    ICMS,
    PISCOFINS,
    campos_do_atalho,
    campos_do_bloco,
    colunas_escolhidas,
    gerar_itens_do_xml,
)


def _parquet(tmp_path, modelo: str = "55") -> str:
    """Um item só, com o esquema inteiro — o que importa aqui são as colunas."""
    linha = {}
    for campo in ESQUEMA_ITENS_DO_XML:
        if pa.types.is_string(campo.type):
            linha[campo.name] = ["55" if campo.name == "modelo" else "x"]
        elif pa.types.is_decimal(campo.type):
            linha[campo.name] = [decimal.Decimal("1.00")]
        elif pa.types.is_boolean(campo.type):
            linha[campo.name] = [True]
        elif pa.types.is_date(campo.type):
            linha[campo.name] = [None]
        else:
            linha[campo.name] = [1]
    linha["modelo"] = [modelo]
    caminho = str(tmp_path / "itens_do_xml.parquet")
    pq.write_table(pa.Table.from_pydict(linha, schema=ESQUEMA_ITENS_DO_XML), caminho)
    return caminho


def _cabecalho(csv: str) -> list[str]:
    with open(csv, encoding="utf-8-sig") as f:
        return f.readline().rstrip("\n").split(";")


class TestOCatalogo:
    def test_todo_campo_do_catalogo_existe_no_parquet(self):
        """Coluna que a tela oferece e o parquet não tem sairia vazia."""
        do_parquet = set(ESQUEMA_ITENS_DO_XML.names)
        assert {c.campo for c in CAMPOS} <= do_parquet

    def test_o_atalho_do_icms_nao_traz_piscofins(self):
        campos = campos_do_atalho("icms")

        assert "valor_icms" in campos and "bc_st" in campos
        assert "valor_pis" not in campos and "issqn_deducao" not in campos

    def test_o_atalho_de_piscofins_nao_traz_st(self):
        campos = campos_do_atalho("piscofins")

        assert "valor_pis" in campos and "cst_cofins" in campos
        assert "bc_st" not in campos

    def test_todo_atalho_leva_a_identificacao(self):
        """Item sem saber de que nota veio não confere nada."""
        for atalho in ("icms", "piscofins", "descontos", "tudo"):
            assert "chave" in campos_do_atalho(atalho), atalho

    def test_atalho_desconhecido_traz_tudo(self):
        assert campos_do_atalho("inventado") == tuple(c.campo for c in CAMPOS)

    def test_o_bloco_devolve_os_campos_dele(self):
        assert "valor_pis" in campos_do_bloco(PISCOFINS)
        assert "valor_pis" not in campos_do_bloco(ICMS)


class TestAEscolha:
    def test_sem_escolha_saem_todas_as_colunas(self):
        assert colunas_escolhidas(None) == CAMPOS
        assert colunas_escolhidas(frozenset()) == CAMPOS

    def test_a_ordem_e_a_do_catalogo_e_nao_a_da_escolha(self):
        """Marcar PIS/COFINS antes do ICMS não inverte a planilha."""
        escolhidas = colunas_escolhidas(frozenset({"valor_pis", "chave", "valor_icms"}))

        assert [c.campo for c in escolhidas] == ["chave", "valor_icms", "valor_pis"]

    def test_campo_que_nao_existe_mais_nao_derruba_nem_esvazia(self):
        """Escolha velha guardada no navegador não pode quebrar a extração."""
        assert [c.campo for c in colunas_escolhidas(frozenset({"chave", "vDesc_antigo"}))] == ["chave"]
        # e uma escolha só de campos inexistentes volta ao catálogo inteiro
        assert colunas_escolhidas(frozenset({"nada", "disso", "existe"})) == CAMPOS


class TestAPlanilha:
    def test_sai_com_as_colunas_escolhidas_e_so_com_elas(self, tmp_path):
        destino = str(tmp_path / "itens.csv")

        linhas = gerar_itens_do_xml(_parquet(tmp_path), destino,
                                    classificacoes=frozenset({"chave", "valor_pis", "cst_pis"}),
                                    formato="csv")

        assert linhas == 1
        assert _cabecalho(destino) == ["Chave de Acesso", "CST do PIS", "Valor do PIS"]

    def test_sem_escolha_sai_o_catalogo_inteiro(self, tmp_path):
        destino = str(tmp_path / "tudo.csv")

        gerar_itens_do_xml(_parquet(tmp_path), destino, formato="csv")

        assert len(_cabecalho(destino)) == len(CAMPOS)

    def test_o_modelo_continua_recortando_linha_e_nao_coluna(self, tmp_path):
        """`modelos` filtra documento; `classificacoes`, coluna. São canais diferentes."""
        parquet = _parquet(tmp_path, modelo="65")

        fora = gerar_itens_do_xml(parquet, str(tmp_path / "a.csv"),
                                  modelos=frozenset({"55"}), formato="csv")
        dentro = gerar_itens_do_xml(parquet, str(tmp_path / "b.csv"),
                                    modelos=frozenset({"65"}), formato="csv")

        assert fora == 0 and dentro == 1
