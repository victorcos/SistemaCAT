"""As três exclusões por item, no que a rodada faz com elas.

Os motores são conferidos cada um contra o seu gabarito do MA
(`tools/validar_903.py`, `_839`, `_933`). O que se mede aqui é o núcleo que as
roda igual — e, principalmente, **onde elas não são iguais**:

- o 839 aplica a **alíquota de exceção** por produto, que vem do banco. Sem ela
  a regra do estado responde, e o número muda;
- o 933 agrupa **sem CFOP**, porque nota de serviço não tem. Vazio numa chave de
  agrupamento é um valor, e somaria coisas diferentes no mesmo balde;
- cada tese grava **o seu próprio parquet**, com as suas colunas.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico import exclusao_do_icms_st, exclusao_do_iss
from cat.infraestrutura.sped.exclusao_do_icms_st import colunas_da_exclusao_st
from cat.infraestrutura.sped.exclusao_do_iss import colunas_da_exclusao_iss
from cat.infraestrutura.sped.registros import CAMPOS

CNPJ = "11222333000181"
REFERENCIA = date(2026, 9, 30)
COMPETENCIA = "2022-10"


def reg(nome: str, **campos: str) -> str:
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


EFD = "\n".join([
    reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI="01102022", DT_FIN="31102022",
        NOME="COMERCIO DO TESTE LTDA", CNPJ=CNPJ, UF="MG", COD_MUN="3106200",
        IND_NAT_PJ="0", IND_ATIV="0"),
    reg("0140", COD_EST="001", NOME="MATRIZ", CNPJ=CNPJ, UF="MG", IE="111",
        COD_MUN="3106200"),
    reg("0150", COD_PART="C01", NOME="MERCADO DO TESTE", COD_PAIS="1058",
        CNPJ="99888777000166", COD_MUN="3106200"),
    reg("0200", COD_ITEM="SKU1", DESCR_ITEM="ARROZ 5KG", COD_BARRA="7890000000017",
        UNID_INV="PC", TIPO_ITEM="00", COD_NCM="10063021"),

    # ---- revenda com ST já retido: entra no 839 ------------------------
    reg("C010", CNPJ=CNPJ),
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="7001", CHV_NFE="31" + "7" * 42, DT_DOC="03102022",
        DT_E_S="03102022", VL_DOC="1000,00", VL_MERC="1000,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="1000,00", CFOP="5405",
        CST_ICMS="060", CST_PIS="01", ALIQ_PIS_PERC="1,6500", VL_BC_PIS="1000,00",
        VL_PIS="16,50", CST_COFINS="01", ALIQ_COFINS_PERC="7,6000",
        VL_BC_COFINS="1000,00", VL_COFINS="76,00"),

    # ---- nota de serviço com ISS: entra no 933 -------------------------
    reg("A010", CNPJ=CNPJ),
    reg("A100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_SIT="00", SER="A",
        NUM_DOC="55", DT_DOC="05102022", DT_EXE_SERV="05102022", VL_DOC="2000,00",
        VL_ISS="40,00"),
    reg("A170", NUM_ITEM="1", COD_ITEM="SRV1", VL_ITEM="2000,00", CST_PIS="01",
        VL_BC_PIS="2000,00", ALIQ_PIS="1,6500", VL_PIS="33,00", CST_COFINS="01",
        VL_BC_COFINS="2000,00", ALIQ_COFINS="7,6000", VL_COFINS="152,00"),
    "|9999|10|",
    "",
])


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return [str(caminho)]


@pytest.fixture
def destino(tmp_path):
    return str(tmp_path / "saida")


class TestCadaTeseNoSeuCanto:
    def test_o_icms_st_grava_o_proprio_parquet(self, arquivo, destino):
        exclusao_do_icms_st.apurar(arquivo, destino, ate="2026-09", referencia=REFERENCIA)
        tabela = pq.read_table(
            os.path.join(destino, exclusao_do_icms_st.ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST))

        assert tabela.column_names == colunas_da_exclusao_st()
        assert tabela.num_rows == 1

    def test_o_iss_grava_o_proprio_parquet(self, arquivo, destino):
        exclusao_do_iss.apurar(arquivo, destino, ate="2026-09", referencia=REFERENCIA)
        tabela = pq.read_table(
            os.path.join(destino, exclusao_do_iss.ARQUIVO_DA_EXCLUSAO_DO_ISS))

        assert tabela.column_names == colunas_da_exclusao_iss()
        assert tabela.num_rows == 1

    def test_os_arquivos_nao_se_pisam(self, arquivo, destino):
        """Rodar as duas na mesma pasta deixa as duas — cada uma no seu nome."""
        exclusao_do_icms_st.apurar(arquivo, destino, ate="2026-09", referencia=REFERENCIA)
        exclusao_do_iss.apurar(arquivo, destino, ate="2026-09", referencia=REFERENCIA)

        assert os.path.isfile(
            os.path.join(destino, exclusao_do_icms_st.ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST))
        assert os.path.isfile(
            os.path.join(destino, exclusao_do_iss.ARQUIVO_DA_EXCLUSAO_DO_ISS))


class TestAAliquotaDeExcecao:
    def test_sem_excecao_vale_a_regra_do_estado(self, arquivo, destino):
        """MG interno: 18%. 1.000,00 × 18% = 180,00 de ICMS-ST presumido."""
        resumo = exclusao_do_icms_st.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA)

        assert Decimal(resumo.excluido) == Decimal("180.00")

    def test_a_excecao_do_banco_manda_na_regra(self, arquivo, destino):
        """O mesmo produto a 12% — cesta básica — dá 120,00, e não 180,00."""
        resumo = exclusao_do_icms_st.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA,
            excecoes={(CNPJ, "MG", "MG", "SKU1"): Decimal(12)})

        assert Decimal(resumo.excluido) == Decimal("120.00")

    def test_a_excecao_de_outro_estabelecimento_nao_vale(self, arquivo, destino):
        """Código de item é do ERP de quem o cadastrou, e não atravessa CNPJ."""
        resumo = exclusao_do_icms_st.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA,
            excecoes={("99999999000199", "MG", "MG", "SKU1"): Decimal(12)})

        assert Decimal(resumo.excluido) == Decimal("180.00")


class TestOsGrupos:
    def test_o_icms_st_agrupa_com_cfop(self, arquivo, destino):
        resumo = exclusao_do_icms_st.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA)
        grupo = next(iter(resumo.grupos))

        assert grupo.registro == exclusao_do_icms_st.REGISTRO
        assert grupo.cfop == "5405"

    def test_o_iss_agrupa_sem_cfop(self, arquivo, destino):
        """Nota de serviço não tem CFOP: a coluna fica fora da chave."""
        resumo = exclusao_do_iss.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA)
        grupo = next(iter(resumo.grupos))

        assert grupo.registro == exclusao_do_iss.REGISTRO
        assert grupo.cfop == ""


class TestOResumo:
    def test_o_iss_exclui_o_que_a_nota_destacou(self, arquivo, destino):
        """Um item só: o rateio é a nota inteira, e o ISS sai todo da base."""
        resumo = exclusao_do_iss.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA)

        assert Decimal(resumo.excluido) == Decimal("40.00")
        assert Decimal(resumo.base) == Decimal("2000.00")

    def test_a_tese_vai_nomeada_no_resumo(self, arquivo, destino):
        """É a coluna que separa as quatro no parquet agregado."""
        st = exclusao_do_icms_st.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA)
        iss = exclusao_do_iss.apurar(
            arquivo, destino, ate="2026-09", referencia=REFERENCIA)

        assert st.tese == exclusao_do_icms_st.TESE_ICMS_ST_NA_BASE
        assert iss.tese == exclusao_do_iss.TESE_ISS_NA_BASE
        assert st.tese != iss.tese
