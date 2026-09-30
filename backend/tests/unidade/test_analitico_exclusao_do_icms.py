"""A rodada do Tema 69: do SPED ao parquet, ao resumo e aos grupos.

O motor já é conferido em `test_sped_exclusao_do_icms.py`, contra o gabarito do
MA. O que se mede aqui é o que a **etapa** faz com ele: o que grava, o que soma,
o que separa por prescrição, e o que faz quando não pode calcular.

Duas regras valem dinheiro e estão medidas abaixo:

- o que prescreveu **aparece e não soma** — some do total, fica na tabela;
- rodada interrompida **não deixa parquet**, porque parquet pela metade parece
  inteiro para quem o abre depois.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.analitico.exclusao_do_icms import (
    ARQUIVO_DA_EXCLUSAO_DO_ICMS,
    REGISTRO,
    apurar,
    avisar_se_a_selic_nao_alcanca,
)
from cat.infraestrutura.sped.exclusao_do_icms import colunas_da_exclusao
from cat.infraestrutura.sped.registros import CAMPOS

CNPJ = "11222333000181"

# o pedido é de 30/09/2026; 10/2020 venceu em 25/11/2020 e já passou dos cinco
# anos, 10/2022 não
REFERENCIA = date(2026, 9, 30)
NO_PRAZO = "2022-10"
PRESCRITA = "2020-10"


def reg(nome: str, **campos: str) -> str:
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


def efd(competencia: str, numero: str, cfop: str = "5102") -> str:
    """Uma EFD-Contribuições de um mês, com uma venda tributada."""
    ano, mes = competencia.split("-")
    inicio, fim = f"01{mes}{ano}", f"28{mes}{ano}"
    return "\n".join([
        reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI=inicio, DT_FIN=fim,
            NOME="COMERCIO DO TESTE LTDA", CNPJ=CNPJ, UF="MG", COD_MUN="3106200",
            IND_NAT_PJ="0", IND_ATIV="0"),
        reg("C010", CNPJ=CNPJ),
        reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55",
            COD_SIT="00", SER="1", NUM_DOC=numero, CHV_NFE="31" + numero.zfill(42),
            DT_DOC=inicio, DT_E_S=inicio, VL_DOC="1000,00", VL_MERC="1000,00"),
        reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="1000,00", CFOP=cfop,
            VL_BC_ICMS="1000,00", ALIQ_ICMS="18,00", VL_ICMS="180,00",
            CST_PIS="01", ALIQ_PIS_PERC="1,6500", VL_BC_PIS="1000,00", VL_PIS="16,50",
            CST_COFINS="01", ALIQ_COFINS_PERC="7,6000", VL_BC_COFINS="1000,00",
            VL_COFINS="76,00"),
        "|9999|5|",
        "",
    ])


@pytest.fixture
def arquivos(tmp_path):
    caminhos = []
    for competencia, numero in ((PRESCRITA, "900"), (NO_PRAZO, "901")):
        caminho = tmp_path / f"contribuicoes_{competencia}.txt"
        caminho.write_bytes(efd(competencia, numero).encode("cp1252"))
        caminhos.append(str(caminho))
    return caminhos


@pytest.fixture
def destino(tmp_path):
    return str(tmp_path / "saida")


class TestOQueGrava:
    def test_o_parquet_sai_com_as_quarenta_colunas(self, arquivos, destino):
        apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA)
        tabela = pq.read_table(os.path.join(destino, ARQUIVO_DA_EXCLUSAO_DO_ICMS))

        assert tabela.column_names == colunas_da_exclusao()
        assert tabela.num_rows == 2

    def test_o_parquet_nasce_mesmo_sem_nenhuma_linha(self, destino, tmp_path):
        """Etapa sem arquivo é etapa que a seguinte não distingue de não rodada."""
        vazio = tmp_path / "sem_venda.txt"
        vazio.write_bytes(efd(NO_PRAZO, "902", cfop="5152").encode("cp1252"))

        resumo = apurar([str(vazio)], destino, ate="2026-09", referencia=REFERENCIA)

        assert resumo.linhas == 0
        assert os.path.isfile(os.path.join(destino, ARQUIVO_DA_EXCLUSAO_DO_ICMS))


class TestOQueSoma:
    def test_o_credito_nao_soma_o_que_prescreveu(self, arquivos, destino):
        resumo = apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA)

        assert resumo.competencias == [PRESCRITA, NO_PRAZO]
        assert resumo.competencias_prescritas == 1
        assert resumo.prescrito > 0
        # o total é só o da competência que ainda alcança
        no_prazo = next(c for c in resumo.por_competencia
                        if c["competencia"] == NO_PRAZO)
        assert Decimal(resumo.total_atualizado) == Decimal(no_prazo["total_atualizado"])

    def test_o_que_prescreveu_continua_na_tabela(self, arquivos, destino):
        resumo = apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA)
        prescrita = next(c for c in resumo.por_competencia
                         if c["competencia"] == PRESCRITA)

        assert prescrita["prescrita"] is True
        assert Decimal(prescrita["total_atualizado"]) > 0

    def test_a_base_soma_as_duas_competencias(self, arquivos, destino):
        """O que se mostra é tudo; o que se pede é só o que está no prazo."""
        resumo = apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA)

        assert Decimal(resumo.base) == Decimal("2000.00")
        assert Decimal(resumo.icms_excluido) == Decimal("360.00")

    def test_os_grupos_saem_por_estabelecimento_mes_cst_e_cfop(self, arquivos, destino):
        resumo = apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA)
        grupos = {(g.cnpj, g.competencia, g.registro, g.cst, g.cfop)
                  for g in resumo.grupos}

        assert grupos == {
            (CNPJ, PRESCRITA, REGISTRO, "01", "5102"),
            (CNPJ, NO_PRAZO, REGISTRO, "01", "5102"),
        }

    def test_a_selic_de_cada_competencia_vai_no_resumo(self, arquivos, destino):
        """Sem a acumulada ao lado, o total da linha não se reconfere."""
        resumo = apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA)

        assert all(c["selic_acumulada"] for c in resumo.por_competencia)
        assert resumo.ate == "2026-09"


class TestQuandoNaoDaParaCalcular:
    def test_rodada_interrompida_nao_deixa_parquet(self, arquivos, destino):
        """Meia leitura não vale, e meio parquet parece inteiro."""
        with pytest.raises(LeituraCancelada):
            apurar(arquivos, destino, ate="2026-09", referencia=REFERENCIA,
                   deve_parar=lambda: True)

        assert not os.path.isfile(os.path.join(destino, ARQUIVO_DA_EXCLUSAO_DO_ICMS))

    def test_o_aviso_da_selic_vem_antes_de_ler(self):
        """Descobrir que falta mês depois de uma hora de leitura é tarde."""
        assert avisar_se_a_selic_nao_alcanca("2026-09") == ""
        assert "tab_selic.MENSAL" in avisar_se_a_selic_nao_alcanca("2030-01")

    def test_o_mes_da_restituicao_sai_da_referencia_quando_nao_vem(self, arquivos,
                                                                   destino):
        resumo = apurar(arquivos, destino, referencia=REFERENCIA)

        assert resumo.ate == "2026-09"
        assert resumo.data_de_referencia == "2026-09-30"
