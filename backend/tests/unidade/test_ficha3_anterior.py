"""A Ficha 3 anterior: o saldo final dela é a abertura (decisão de 26/11/2026)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.dominio.lote import TipoDeArquivo
from cat.infraestrutura.arquivos.classificador import classificar
from cat.infraestrutura.arquivos.ficha3_anterior import (
    colunas_do_cabecalho,
    gravar_saldos,
    identificar,
)

# o cabeçalho real repete "Quantidade" três vezes: entrada, saída e saldo
CABECALHO = "|".join([
    "Código da Mercadoria", "DESCR_ITEM", "UNID_INV", "ALIQ_ICMS", "Número de Ordem", "Data",
    "Chave do Documento Fiscal Eletrônico", "Número de Série de Fabricação do ECF",
    "Tipo do Documento", "Série do Documento", "Número do Documento",
    "Código do Remetente ou Destinatário", "CFOP", "Número do Ítem no Documento", "Quantidade",
    "Valor Total do ICMS Suportado na Retenção ou Antecipação por ST", "Quantidade",
    "Valor Unitário do ICMS Suportado", "Enq 1", "Enq 2", "Enq 3", "Enq 4", "Enq 0",
    "ICMS Efetivo na Saída", "CMS Efetivo da Entrada, nas Demais Hipóteses", "Quantidade",
    "Valor Unitário do Saldo", "Valor Total do Saldo", "Valor do Ressarcimento",
    "Valor do Complemento", "ICMS - Crédito da Operação Própria", "MES_ANO", "IE", "CNPJ_FILIAL",
    "PERIODO"])

A = "11111111000191"
B = "11111111000272"


def linha(codigo, ordem, dia, cfop, q_saldo, v_saldo, mes, cnpj=A):
    campos = [""] * 35
    campos[0], campos[1], campos[2] = codigo, "Produto de teste", "UN"
    campos[4], campos[5], campos[12] = str(ordem), dia, cfop
    campos[25], campos[27] = q_saldo, v_saldo
    campos[31], campos[33], campos[34] = mes, cnpj, mes
    return "|".join(campos)


def escrever(caminho, linhas):
    caminho.write_bytes(("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("latin-1"))
    return str(caminho)


@pytest.fixture
def arquivos(tmp_path):
    nov = escrever(tmp_path / "Ficha3 A - 2020-11.txt", [
        linha("X", 1, "01/11/2020", "0001", "50,000", "100,00", "11/2020"),
        # Z sai da ficha em novembro, ainda com saldo: dezembro não o lista
        linha("Z", 2, "01/11/2020", "0001", "6,000", "3,00", "11/2020")])
    dez = escrever(tmp_path / "Ficha3 A - 2020-12.txt", [
        linha("X", 3, "01/12/2020", "0001", "8,000", "16,00", "12/2020"),
        # a última linha do item, pela ordem, é o saldo final
        linha("X", 9, "20/12/2020", "5405", "7,000", "21,500000000000000", "12/2020"),
        linha("X", 5, "10/12/2020", "1403", "9,000", "27,00", "12/2020"),
        linha("W", 4, "01/12/2020", "0001", "0,000", "0,00", "12/2020")])
    jan = escrever(tmp_path / "Ficha3 A - 2021-01.txt", [
        linha("X", 1, "01/01/2021", "0001", "999,000", "999,00", "01/2021")])
    velha = escrever(tmp_path / "Ficha3 B - 2020-06.txt", [
        linha("X", 1, "01/06/2020", "0001", "4,000", "8,00", "06/2020", cnpj=B)])
    return [nov, dez, jan, velha]


class TestLeitura:
    def test_cabecalho_acha_o_saldo_pelo_valor_total(self):
        c = colunas_do_cabecalho(CABECALHO)
        assert (c.quantidade, c.valor, c.cnpj, c.mes_ano, c.ordem) == (25, 27, 33, 31, 4)
        assert colunas_do_cabecalho("LOJA;CNPJ_LOJA;NUM_DOC") is None

    def test_identifica_estabelecimento_e_mes(self, arquivos):
        i = identificar(arquivos[1])
        assert (i.cnpj, i.competencia) == (A, date(2020, 12, 1))

    def test_vale_a_ultima_linha_de_cada_item_em_qualquer_mes(self, arquivos, tmp_path):
        destino = str(tmp_path / "saldo.parquet")
        r = gravar_saldos(arquivos, date(2021, 1, 1), destino)
        saldos = {(s["cnpj"], s["codigo"]): (s["competencia"], s["quantidade"], s["valor"])
                  for s in pq.read_table(destino).to_pylist()}
        # jan/2021 já é do período: não conta; dez/2020 vence nov/2020
        assert saldos[(A, "X")] == (date(2020, 12, 1), Decimal(7), Decimal("21.5"))
        # o item que dezembro não lista fica com a última linha de novembro
        assert saldos[(A, "Z")] == (date(2020, 11, 1), Decimal(6), Decimal(3))
        assert saldos[(A, "W")][1:] == (Decimal(0), Decimal(0))
        # a ficha de B terminou em jun/2020: vale assim mesmo, e é contada
        assert saldos[(B, "X")] == (date(2020, 6, 1), Decimal(4), Decimal(8))
        assert (r.arquivos, r.itens, r.defasados, r.de_meses_anteriores) == (
            3, 4, {B: "2020-06-01"}, 1)

    def test_o_classificador_reconhece_a_ficha(self, arquivos):
        a = classificar(arquivos[1])
        assert (a.tipo, a.cnpj, a.competencia) == (TipoDeArquivo.FICHA3_ANTERIOR, A, date(2020, 12, 1))
        assert TipoDeArquivo.FICHA3_ANTERIOR.alimenta_a_cat
