"""A montagem do razão sobre parquet de verdade, com a conta feita à mão.

Cenário: uma loja A, uma mercadoria X vendida com CST 60.

    abertura 31/12/2020 .......... 10 un, sem valor de ICMS suportado
    05/01 entrada ................. 10 un, R$ 20,00 suportado  -> saldo 20 un, R$ 20, unit 1
    06/01 transferência (EFD) ..... 2 un                      -> saldo 18 un, R$ 18
    06/01 venda de PDV (relatório)  5 un, valor R$ 20, 18%    -> saldo 13 un, R$ 13
          confronto 20 x 18% = 3,60; suportado baixado 5,00 -> ressarcimento 1,40
    07/01 devolução de venda ...... 1 un                      -> saldo 14 un, R$ 14

E o que não entra: a mercadoria Y só sai com CST 00; a mesma transferência
vinda do relatório (a EFD vence); e a venda de uma loja que nenhuma pista diz
de quem é.
"""

import os
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.movimentacao import (
    ARQUIVO_CONVERSOES,
    ARQUIVO_ITENS,
    ARQUIVO_MOVIMENTOS,
)
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.analitico.razao import (
    ARQUIVO_CONFERENCIA_INVENTARIO,
    ARQUIVO_FICHA3,
    ARQUIVO_FICHAS,
    ESQUEMA_SAIDA_DO_RELATORIO,
    Fontes,
    linhas_da_ficha,
    lista_de_fichas,
    montar,
    serializar,
)
from cat.infraestrutura.analitico.suportado import ARQUIVO_SUPORTADO, ApuracaoCancelada

A = "11111111000191"
B = "11111111000272"
CHAVE_TRANSF = "35210111111111000191550010000000011000000010"   # emitida por A


def d(v) -> Decimal:
    return Decimal(str(v))


def gravar(caminho, esquema: list[tuple], linhas: list[dict]) -> None:
    s = pa.schema(esquema)
    pq.write_table(pa.Table.from_pydict({c: [l.get(c) for l in linhas] for c in s.names},
                                        schema=s), str(caminho))


@pytest.fixture
def fontes(tmp_path):
    mov = tmp_path / "movimentacao"
    apu = tmp_path / "apuracao"
    mov.mkdir()
    apu.mkdir()
    gravar(mov / ARQUIVO_MOVIMENTOS, [
        ("cnpj", pa.string()), ("competencia", pa.date32()), ("operacao", pa.string()),
        ("codigo", pa.string()), ("data", pa.date32()), ("cfop", pa.string()),
        ("unidade", pa.string()), ("numero_item", pa.int32()),
        ("cst_icms", pa.string()), ("modelo", pa.string()), ("quantidade", pa.decimal128(20, 5)),
        ("valor", pa.decimal128(18, 2)), ("valor_icms", pa.decimal128(18, 2)),
        ("valor_st", pa.decimal128(18, 2)), ("chave", pa.string()), ("numero_documento", pa.string()),
    ], [
        # entrada: aparece também aqui, mas o razão lê a da apuração
        {"cnpj": A, "competencia": date(2021, 1, 1), "operacao": "entrada", "codigo": "X",
         "data": date(2021, 1, 5), "cfop": "1403", "cst_icms": "060", "modelo": "55",
         "unidade": "UN", "numero_item": 1,
         "quantidade": d(10), "valor": d(100), "valor_icms": d(0), "valor_st": d(0),
         "chave": "4" * 44, "numero_documento": "1"},
        {"cnpj": A, "competencia": date(2021, 1, 1), "operacao": "saida", "codigo": "X",
         "data": date(2021, 1, 6), "cfop": "5152", "cst_icms": "060", "modelo": "55",
         "unidade": "UN", "numero_item": 1,
         "quantidade": d(2), "valor": d(30), "valor_icms": d(0), "valor_st": d(0),
         "chave": CHAVE_TRANSF, "numero_documento": "11"},
        {"cnpj": B, "competencia": date(2021, 1, 1), "operacao": "saida", "codigo": "Y",
         "data": date(2021, 1, 6), "cfop": "5102", "cst_icms": "000", "modelo": "55",
         "unidade": "UN", "numero_item": 1,
         "quantidade": d(1), "valor": d(10), "valor_icms": d(1.8), "valor_st": d(0),
         "chave": "5" * 44, "numero_documento": "12"},
    ])
    gravar(mov / ARQUIVO_ITENS, [
        ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
        ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)),
    ], [{"cnpj": A, "codigo": "X", "descricao": "Refrigerante cola 2L", "unidade": "UN",
         "aliq_icms": d(18)}])
    gravar(mov / ARQUIVO_INVENTARIO, [
        ("cnpj", pa.string()), ("codigo", pa.string()), ("data_inventario", pa.date32()),
        ("unidade", pa.string()), ("quantidade", pa.decimal128(20, 5)),
    ], [
        {"cnpj": A, "codigo": "X", "data_inventario": date(2020, 12, 31), "unidade": "UN", "quantidade": d(10)},
        {"cnpj": A, "codigo": "X", "data_inventario": date(2020, 11, 30), "unidade": "UN", "quantidade": d(99)},
        # o estoque que a empresa declarou no fim do mês: bate com a ficha
        {"cnpj": A, "codigo": "X", "data_inventario": date(2021, 1, 31), "unidade": "UN", "quantidade": d(14)},
    ])
    gravar(apu / ARQUIVO_SUPORTADO, [
        ("cnpj", pa.string()), ("codigo", pa.string()), ("data", pa.date32()), ("cfop", pa.string()),
        ("cst_icms", pa.string()), ("modelo", pa.string()), ("quantidade", pa.decimal128(18, 5)),
        ("suportado", pa.decimal128(18, 6)), ("chave", pa.string()), ("numero_documento", pa.string()),
        ("numero_item", pa.int32()),
    ], [
        {"cnpj": A, "codigo": "X", "data": date(2021, 1, 5), "cfop": "1403", "cst_icms": "060",
         "modelo": "55", "quantidade": d(10), "suportado": d(20), "chave": "4" * 44,
         "numero_documento": "1", "numero_item": 1},
        {"cnpj": A, "codigo": "X", "data": date(2021, 1, 7), "cfop": "1411", "cst_icms": "060",
         "modelo": "55", "quantidade": d(1), "suportado": d(0), "chave": "6" * 44,
         "numero_documento": "2", "numero_item": 1},
    ])
    rel = tmp_path / "saidas_do_relatorio.parquet"
    base = {"numero_documento": "", "cst_icms": "060", "suportado": d(0), "valor": d(0)}
    pq.write_table(pa.Table.from_pylist([
        # a mesma transferência da EFD: a EFD vence, esta linha sai — mas ensina
        # que a unidade 005 é a loja A
        {**base, "unidade": "005", "cnpj_participante": "22222222000100", "chave": CHAVE_TRANSF,
         "codigo": "X", "data": date(2021, 1, 6), "cfop": "5152", "quantidade": d(2), "pdv": False},
        # venda de PDV sem CNPJ: a unidade diz de quem é
        {**base, "unidade": "005", "cnpj_participante": "", "chave": "", "codigo": "X",
         "data": date(2021, 1, 6), "cfop": "5405", "quantidade": d(5), "valor": d(20), "pdv": True},
        # loja que nenhuma pista alcança
        {**base, "unidade": "777", "cnpj_participante": "", "chave": "", "codigo": "X",
         "data": date(2021, 1, 6), "cfop": "5405", "quantidade": d(3), "valor": d(9), "pdv": True},
    ], schema=ESQUEMA_SAIDA_DO_RELATORIO), str(rel))
    return Fontes(movimentacao=str(mov), apuracao=str(apu), saidas_do_relatorio=str(rel))


@pytest.fixture
def montado(fontes, tmp_path):
    destino = tmp_path / "razao"
    destino.mkdir()
    resumo = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
    return destino, resumo


def ficha(destino) -> list[dict]:
    return pq.read_table(str(destino / ARQUIVO_FICHA3)).to_pylist()


class TestAConta:
    def test_a_ficha_fecha_com_a_conta_a_mao(self, montado):
        destino, _ = montado
        linhas = ficha(destino)
        assert [(l["especie"], l["origem"], l["saldo_quantidade"]) for l in linhas] == [
            ("entrada", "efd", d(20)), ("saida", "efd", d(18)),
            ("saida", "relatorio", d(13)), ("saida", "efd", d(14))]
        venda = linhas[2]
        assert venda["enquadramento"] == 1
        assert venda["icms_efetivo"] == d("3.60")
        assert venda["ressarcimento"] == d("1.4")
        assert linhas[3]["devolucao"] and linhas[3]["saldo_valor"] == d(14)

    def test_o_resumo_soma_o_que_a_ficha_diz(self, montado):
        _, r = montado
        assert r.fichas == 1 and r.codigos_com_st == 1 and r.estabelecimentos == 1
        assert r.ressarcimento == d("1.4") and r.complemento == 0
        assert r.abertura_em == "2020-12-31"
        assert r.fichas_abertura_sem_valor == 1
        s = serializar(r)
        enq = {e["codigo"]: e for e in s["por_enquadramento"]}
        assert enq["1"]["ressarcimento"] == "1.40" and enq["0"]["linhas"] == 1
        assert s["saidas_por_origem"] == {"efd": 1, "relatorio": 1}


class TestAsFontes:
    def test_mercadoria_sem_saida_cst60_fica_fora(self, montado):
        destino, _ = montado
        assert {l["codigo"] for l in ficha(destino)} == {"X"}

    def test_a_efd_vence_o_relatorio_na_mesma_nota(self, montado):
        destino, r = montado
        assert r.relatorio_trocado_pela_efd == 1
        transferencias = [l for l in ficha(destino) if l["cfop"] == "5152"]
        assert len(transferencias) == 1 and transferencias[0]["origem"] == "efd"

    def test_loja_sem_pista_e_contada_nao_suposta(self, montado):
        _, r = montado
        assert r.relatorio_sem_estabelecimento == 1

    def test_sem_relatorio_so_a_efd(self, fontes, tmp_path):
        fontes.saidas_do_relatorio = None
        destino = tmp_path / "so_efd"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert r.saidas_por_origem == {"efd": 1}


def trocar_unidade_da_entrada(fontes, unidade: str) -> None:
    """A entrada de 05/01 passa a vir noutra unidade na nota."""
    caminho = os.path.join(fontes.movimentacao, ARQUIVO_MOVIMENTOS)
    t = pq.read_table(caminho).to_pylist()
    for linha in t:
        if linha["operacao"] == "entrada":
            linha["unidade"] = unidade
    pq.write_table(pa.Table.from_pylist(t, schema=pq.read_schema(caminho)), caminho)


class TestUnidade:
    def test_entrada_em_caixa_vira_unidade_pelo_0220(self, fontes, tmp_path):
        """10 caixas de 2 são 20 unidades: a ficha é na unidade do inventário.

            abertura 10 + entrada 20 = 30 un, R$ 20      -> unit 0,6667
            transferência 2 -> 28; PDV 5 baixa 3,3333; confronto 3,60
            -> ressarcimento 0 e complemento 0,2667 (enquadramento 1)
        """
        trocar_unidade_da_entrada(fontes, "CX")
        gravar(os.path.join(fontes.movimentacao, ARQUIVO_CONVERSOES), [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("unidade", pa.string()),
            ("fator", pa.decimal128(24, 9)),
        ], [{"cnpj": A, "codigo": "X", "unidade": "CX", "fator": d(2)}])
        destino = tmp_path / "convertido"
        destino.mkdir()
        r = montar(fontes, str(destino))
        entrada = next(l for l in ficha(destino) if l["especie"] == "entrada")
        assert entrada["quantidade"] == d(20) and entrada["fator_conversao"] == d(2)
        assert entrada["unidade_origem"] == "CX" and not entrada["unidade_sem_fator"]
        assert r.linhas_convertidas == 1 and r.linhas_unidade_sem_fator == 0
        assert r.ressarcimento == 0 and round(r.complemento, 4) == d("0.2667")

    def test_unidade_diferente_sem_0220_fica_como_veio_e_marcada(self, fontes, tmp_path):
        """Não se adivinha fator: sem 0220, a quantidade não muda e a linha diz."""
        trocar_unidade_da_entrada(fontes, "FD")
        destino = tmp_path / "sem_fator"
        destino.mkdir()
        r = montar(fontes, str(destino))
        entrada = next(l for l in ficha(destino) if l["especie"] == "entrada")
        assert entrada["quantidade"] == d(10) and entrada["unidade_sem_fator"]
        assert r.linhas_unidade_sem_fator == 1
        assert serializar(r)["pendencias"]["linhas_unidade_sem_fator"] == 1
        assert lista_de_fichas(str(destino), so="sem_fator")["total"] == 1


class TestConferenciaComInventario:
    def test_saldo_que_bate_com_o_bloco_h(self, montado):
        destino, r = montado
        c = r.conferencia
        assert c["datas"] == 1 and c["com_estoque"] == 1 and c["batem"] == 1
        linha = pq.read_table(str(destino / ARQUIVO_CONFERENCIA_INVENTARIO)).to_pylist()[0]
        assert linha["situacao"] == "bate" and linha["saldo_ficha"] == d(14)
        f = lista_de_fichas(str(destino))["linhas"][0]
        assert f["inventarios_conferidos"] == 1 and f["inventarios_divergentes"] == 0

    def test_diferenca_do_tamanho_de_um_fator_e_suspeita_de_unidade(self, fontes, tmp_path):
        """A empresa declarou 168 (14 x 12): a ficha contou em caixa o que o
        estoque conta em unidade, ou o contrário."""
        caminho = os.path.join(fontes.movimentacao, ARQUIVO_INVENTARIO)
        t = pq.read_table(caminho).to_pylist()
        for linha in t:
            if linha["data_inventario"] == date(2021, 1, 31):
                linha["quantidade"] = d(168)
        pq.write_table(pa.Table.from_pylist(t, schema=pq.read_schema(caminho)), caminho)
        destino = tmp_path / "suspeita"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert r.conferencia["suspeita_unidade"] == 1 and r.conferencia["fichas_suspeita_unidade"] == 1
        assert lista_de_fichas(str(destino), so="suspeita_unidade")["total"] == 1

    def test_item_fora_do_bloco_h_e_estoque_zero(self, fontes, tmp_path):
        caminho = os.path.join(fontes.movimentacao, ARQUIVO_INVENTARIO)
        t = [l for l in pq.read_table(caminho).to_pylist() if l["data_inventario"] != date(2021, 1, 31)]
        # outro item no inventário do fim do mês: a data existe para a loja A
        t.append({"cnpj": A, "codigo": "Z", "data_inventario": date(2021, 1, 31), "unidade": "UN",
                  "quantidade": d(1)})
        pq.write_table(pa.Table.from_pylist(t, schema=pq.read_schema(caminho)), caminho)
        destino = tmp_path / "fora"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert r.conferencia["divergentes"] == 1


class TestPendencias:
    def test_sem_aliquota_nao_inventa_ressarcimento(self, fontes, tmp_path):
        os.remove(os.path.join(fontes.movimentacao, ARQUIVO_ITENS))
        destino = tmp_path / "sem_aliq"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert r.saidas_sem_aliquota == 1 and r.ressarcimento == 0

    def test_cancelar_nao_deixa_ficha_pela_metade(self, fontes, tmp_path):
        destino = tmp_path / "cancelado"
        destino.mkdir()
        with pytest.raises(ApuracaoCancelada):
            montar(fontes, str(destino), deve_parar=lambda: True)
        assert not (destino / ARQUIVO_FICHA3).exists()
        assert not (destino / ARQUIVO_FICHAS).exists()


class TestATela:
    def test_lista_de_fichas_com_descricao_do_cadastro(self, montado):
        destino, _ = montado
        r = lista_de_fichas(str(destino))
        assert r["total"] == 1
        f = r["linhas"][0]
        assert f["descricao"] == "Refrigerante cola 2L" and f["uf"] == "SP"
        assert d(f["ressarcimento"]) == d("1.4")
        assert lista_de_fichas(str(destino), busca="cola")["total"] == 1
        assert lista_de_fichas(str(destino), so="negativas")["total"] == 0

    def test_linhas_de_uma_ficha_em_ordem(self, montado):
        destino, _ = montado
        r = linhas_da_ficha(str(destino), A, "X", pagina=1, por_pagina=2)
        assert r["total"] == 4 and [l["numero"] for l in r["linhas"]] == [1, 2]

    def test_recorte_desconhecido_e_recusado(self, montado):
        destino, _ = montado
        with pytest.raises(ValueError):
            lista_de_fichas(str(destino), so="tudo")
