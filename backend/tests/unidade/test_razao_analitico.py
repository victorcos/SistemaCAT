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

from cat.dominio.cat42.enquadramento import VendaAConsumidor
from cat.dominio.cat42.razao import EnquadramentoLegal
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML
from cat.infraestrutura.analitico.movimentacao import (
    ARQUIVO_CONVERSOES,
    ARQUIVO_ITENS,
    ARQUIVO_MOVIMENTOS,
)
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO, ARQUIVO_ITENS_DA_EFD
from cat.infraestrutura.analitico.razao import (
    ARQUIVO_CONFERENCIA_INVENTARIO,
    ARQUIVO_FICHA3,
    ARQUIVO_FICHAS,
    ESQUEMA_SAIDA_DO_RELATORIO,
    Fontes,
    _confronto,
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
        ("participante", pa.string()),
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
        ("numero_item", pa.int32()), ("participante", pa.string()),
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
        # o CST de cada linha vem junto, entrada e saída (pedido do Victor)
        assert [l["cst_icms"] for l in linhas] == ["060", "060", "060", "060"]
        assert venda["icms_efetivo"] == d("3.60")
        assert venda["ressarcimento"] == d("1.4")
        assert linhas[3]["devolucao"] and linhas[3]["saldo_valor"] == d(14)

    def test_a_linha_traz_o_cadastro_e_o_valor_do_item(self, montado):
        """O leiaute do papel de trabalho pede descrição, NCM e VL_ITEM na
        linha — inclusive na entrada, cujo valor está na movimentação."""
        destino, _ = montado
        entrada, venda = ficha(destino)[0], ficha(destino)[2]
        assert entrada["descricao"] == "Refrigerante cola 2L"
        assert entrada["valor_item"] == d(100)            # o C170 da entrada
        assert venda["descricao"] == "Refrigerante cola 2L"
        assert venda["valor_item"] == d(20)               # a venda de PDV do relatório

    def test_sem_0200_a_descricao_vem_do_xml_da_propria_saida(self, fontes, tmp_path):
        """Quatro códigos da Advertising não têm 0200 em arquivo nenhum: a
        descrição vem do xProd da nota que o próprio estabelecimento emitiu."""
        mov = tmp_path / "movimentacao"
        gravar(mov / ARQUIVO_ITENS, [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
            ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)),
        ], [{"cnpj": A, "codigo": "X", "descricao": "", "unidade": "UN", "aliq_icms": d(18)}])
        gravar(mov / ARQUIVO_ITENS_DO_XML, [
            ("chave", pa.string()), ("numero_item", pa.int32()), ("emitente", pa.string()),
            ("destinatario", pa.string()), ("emissao", pa.date32()), ("codigo", pa.string()),
            ("descricao", pa.string()), ("ncm", pa.string()), ("cst_icms", pa.string()),
            ("bc_icms", pa.decimal128(18, 2)), ("valor", pa.decimal128(18, 2)),
            ("desconto", pa.decimal128(18, 2)), ("aliq_icms", pa.decimal128(9, 4)),
            ("cfop", pa.string()),
        ], [
            {"chave": CHAVE_TRANSF, "numero_item": 1, "emitente": A, "destinatario": "22222222000100",
             "emissao": date(2021, 1, 6), "codigo": "X", "descricao": "REFRIGERANTE COLA 2L (XML)",
             "ncm": "22021000", "cst_icms": "060", "bc_icms": d(0), "valor": d(30),
             "desconto": d(0), "aliq_icms": d(0), "cfop": "5152"},
            # a nota do fornecedor traz o código dele: não serve de descrição nossa
            {"chave": "9" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "codigo": "X", "descricao": "CODIGO DO FORNECEDOR",
             "ncm": "22021000", "cst_icms": "000", "bc_icms": d(0), "valor": d(10),
             "desconto": d(0), "aliq_icms": d(0), "cfop": "5102"},
        ])
        destino = tmp_path / "descricao_do_xml"
        destino.mkdir()
        montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        assert {l["descricao"] for l in ficha(destino)} == {"REFRIGERANTE COLA 2L (XML)"}

    def test_a_aliquota_da_operacao_vem_do_documento(self, montado):
        """A Ficha 3 mostra a alíquota de cada linha como o documento a traz —
        é outra coisa que a alíquota interna do confronto."""
        destino, _ = montado
        linhas = ficha(destino)
        # a venda de PDV vem do relatório, que não traz alíquota: a ficha mostra
        # a interna da mercadoria, que é o que a operação teria
        assert linhas[2]["aliquota_documento"] == d(18)
        assert linhas[2]["aliquota"] == d(18)          # a do confronto, do 0200

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


class TestVendaAConsumidor:
    """A escolha do trabalho: o cupom no enquadramento 1 (o manual) ou no 0 (a BOA)."""

    def test_o_padrao_e_o_enquadramento_1(self, montado):
        destino, r = montado
        assert r.venda_a_consumidor == "enquadramento_1"
        assert serializar(r)["venda_a_consumidor"] == "enquadramento_1"

    def test_no_zero_o_cupom_nao_gera_ressarcimento(self, fontes, tmp_path):
        destino = tmp_path / "no_zero"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP"},
                   venda_a_consumidor=VendaAConsumidor.DEMAIS_SAIDAS)
        venda = [l for l in ficha(destino) if l["origem"] == "relatorio"][0]
        assert venda["enquadramento"] == 0 and venda["icms_efetivo"] is None
        assert venda["ressarcimento"] == 0 and venda["complemento"] == 0
        # o saldo não muda: o enquadramento decide o confronto, não a baixa
        assert venda["saldo_quantidade"] == d(13)
        assert r.ressarcimento == 0 and r.venda_a_consumidor == "demais_saidas"


class TestDocumentoDaLinha:
    """O que o arquivo digital vai pedir de cada linha: chave e nº do item (1100)."""

    def test_entrada_e_saida_da_efd_levam_chave_e_item(self, montado):
        destino, _ = montado
        linhas = ficha(destino)
        entrada, transferencia, devolucao = linhas[0], linhas[1], linhas[3]
        assert (entrada["chave"], entrada["numero_item"], entrada["modelo"]) == ("4" * 44, 1, "55")
        assert (transferencia["chave"], transferencia["numero_item"],
                transferencia["numero_documento"]) == (CHAVE_TRANSF, 1, "11")
        assert devolucao["chave"] == "6" * 44 and devolucao["numero_item"] == 1

    def test_venda_do_relatorio_nao_tem_item(self, montado):
        destino, _ = montado
        venda = ficha(destino)[2]
        assert venda["origem"] == "relatorio"
        assert venda["chave"] == "" and venda["numero_item"] is None


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


class TestEstoqueNegativo:
    """Estoque negativo abre a ficha com o que faltaria, sem ICMS suportado.

    Mercadoria W na loja A, sem abertura:
        05/01 entrada 1 un, R$ 5,00           -> faltam 4 un para a venda
        06/01 venda de PDV 5 un, R$ 100, 18%  -> confronto 18

    A ficha abre com as 4 unidades que faltam, sem imposto: o suportado das 5
    unidades vendidas vira R$ 5,00 (só o da entrada), e a saída gera
    complemento de R$ 13,00 — em vez de um ressarcimento de R$ 7,00 apoiado em
    estoque que não existia (decisão do Victor, 17/09/2026).
    """

    @pytest.fixture
    def com_w(self, fontes, tmp_path):
        def acrescentar(caminho, linha):
            t = pq.read_table(caminho)
            pq.write_table(pa.Table.from_pylist(t.to_pylist() + [linha], schema=t.schema), caminho)

        acrescentar(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO), {
            "cnpj": A, "codigo": "W", "data": date(2021, 1, 5), "cfop": "1403", "cst_icms": "060",
            "modelo": "55", "quantidade": d(1), "suportado": d(5), "chave": "7" * 44,
            "numero_documento": "3", "numero_item": 1})
        acrescentar(os.path.join(fontes.movimentacao, ARQUIVO_ITENS), {
            "cnpj": A, "codigo": "W", "descricao": "Cerveja lata", "unidade": "UN", "aliq_icms": d(18)})
        acrescentar(fontes.saidas_do_relatorio, {
            "unidade": "005", "cnpj_participante": "", "chave": "", "numero_documento": "", "codigo": "W",
            "data": date(2021, 1, 6), "cfop": "5405", "cst_icms": "060", "quantidade": d(5),
            "valor": d(100), "suportado": d(0), "pdv": True})
        destino = tmp_path / "com_w"
        destino.mkdir()
        return destino, montar(fontes, str(destino))

    def test_a_ficha_abre_com_o_que_faltava_e_soma_no_total(self, com_w):
        _, r = com_w
        assert r.fichas_abertas_por_negativo == 1 and r.quantidade_aberta_por_negativo == d(4)
        assert r.fichas_retiradas == 0
        assert r.ressarcimento == d("1.4")                  # a de W virou complemento
        assert r.complemento == d(13)
        s = serializar(r)
        assert s["abertas_por_saldo_negativo"]["fichas"] == 1
        assert d(s["abertas_por_saldo_negativo"]["quantidade"]) == d(4)
        assert sum(d(c["complemento"]) for c in s["por_competencia"]) == d(13)

    def test_a_ficha_fica_marcada_e_no_total(self, com_w):
        destino, _ = com_w
        linhas = [l for l in ficha(destino) if l["codigo"] == "W"]
        assert len(linhas) == 2 and not any(l["ficha_retirada"] for l in linhas)
        assert all(l["saldo_quantidade"] >= 0 for l in linhas)
        w = next(f for f in lista_de_fichas(str(destino))["linhas"] if f["codigo"] == "W")
        assert w["ficou_negativo"] and d(w["abertura_por_saldo_negativo"]) == d(4)
        assert lista_de_fichas(str(destino), so="retiradas")["linhas"] == []
        assert {f["codigo"] for f in lista_de_fichas(str(destino), so="validas")["linhas"]} == {"X", "W"}


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


def gravar_itens_do_mes(fontes, linhas: list[dict]) -> None:
    gravar(os.path.join(fontes.movimentacao, ARQUIVO_ITENS_DA_EFD), [
        ("cnpj", pa.string()), ("competencia", pa.date32()), ("arquivo", pa.string()),
        ("codigo", pa.string()), ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)),
    ], linhas)


class TestAliquotaDoMes:
    """O confronto usa a alíquota do 0200 do mês da saída, não a do fim do período."""

    def test_a_venda_de_janeiro_confronta_com_a_aliquota_de_janeiro(self, fontes, tmp_path):
        # o cadastro mais recente diz 18%; o de janeiro dizia 12%
        gravar_itens_do_mes(fontes, [
            {"cnpj": A, "competencia": date(2021, 1, 1), "arquivo": "efd_01.txt", "codigo": "X",
             "unidade": "UN", "aliq_icms": d(12)},
            {"cnpj": A, "competencia": date(2021, 2, 1), "arquivo": "efd_02.txt", "codigo": "X",
             "unidade": "UN", "aliq_icms": d(18)},
        ])
        destino = tmp_path / "aliq_do_mes"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        # 20 x 12% = 2,40; suportado baixado 5,00 -> ressarcimento 2,60
        assert venda["icms_efetivo"] == d("2.40")
        assert venda["ressarcimento"] == d("2.6")
        # a transferência e a venda saíram em janeiro com a alíquota de janeiro
        assert r.saidas_com_aliquota_do_mes == 2
        assert serializar(r)["saidas_com_aliquota_do_mes"] == 2

    def test_mes_sem_aliquota_fica_com_a_mais_recente(self, fontes, tmp_path):
        gravar_itens_do_mes(fontes, [
            {"cnpj": A, "competencia": date(2021, 1, 1), "arquivo": "efd_01.txt", "codigo": "X",
             "unidade": "UN", "aliq_icms": None},
        ])
        destino = tmp_path / "aliq_vazia"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["icms_efetivo"] == d("3.60")
        assert r.saidas_com_aliquota_do_mes == 0


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


def acrescentar_linhas(caminho, linhas: list[dict]) -> None:
    t = pq.read_table(caminho)
    pq.write_table(pa.Table.from_pylist(t.to_pylist() + linhas, schema=t.schema), caminho)


def entrada_anterior(data, quantidade, suportado, n, cfop="1403") -> dict:
    return {"cnpj": A, "codigo": "X", "data": data, "cfop": cfop, "cst_icms": "060", "modelo": "55",
            "quantidade": d(quantidade), "suportado": d(suportado), "chave": str(n) * 44,
            "numero_documento": str(n), "numero_item": 1}


class TestAberturaValorada:
    """A abertura de 31/12/2020 (10 un) pelas entradas de antes do período (item 3.3.8)."""

    def test_as_entradas_mais_recentes_valoram_a_abertura(self, fontes, tmp_path):
        # 6 un a R$ 2 em dezembro e 10 un a R$ 3 em novembro: 6 x 2 + 4 x 3 = R$ 24
        acrescentar_linhas(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO), [
            entrada_anterior(date(2020, 11, 10), 10, 30, 7),
            entrada_anterior(date(2020, 12, 20), 6, 12, 8),
            # devolução de venda e uso e consumo não são de onde o estoque veio
            entrada_anterior(date(2020, 12, 28), 50, 999, 9, cfop="1411"),
        ])
        destino = tmp_path / "abertura"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        f = pq.read_table(str(destino / ARQUIVO_FICHAS)).to_pylist()[0]
        assert (f["abertura_valor"], f["abertura_sem_valor"], f["abertura_parcial"]) == (d(24), False, False)
        # a entrada de 05/01 soma R$ 20 aos R$ 24 da abertura
        assert ficha(destino)[0]["saldo_valor"] == d(44)
        assert (r.fichas_abertura_valorada, r.fichas_abertura_sem_valor, r.icms_da_abertura) == (1, 0, d(24))
        # as entradas de 2020 valoram a abertura e não entram na ficha
        assert len(ficha(destino)) == 4
        assert serializar(r)["abertura"]["icms"] == "24.00"

        # e a etapa 6 abre o 1050 com o ICMS da abertura
        from cat.infraestrutura.analitico.apuracao import ARQUIVO_SALDOS, apurar  # noqa: PLC0415
        periodo = tmp_path / "periodo"
        periodo.mkdir()
        apurar(str(destino), str(periodo), {A: "SP"})
        saldo = pq.read_table(str(periodo / ARQUIVO_SALDOS)).to_pylist()[0]
        assert (saldo["qtd_ini"], saldo["icms_tot_ini"]) == (d(10), d(24))

    def test_entradas_que_nao_alcancam_marcam_a_abertura_como_parcial(self, fontes, tmp_path):
        acrescentar_linhas(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO), [
            entrada_anterior(date(2020, 12, 20), 4, 8, 8)])
        destino = tmp_path / "parcial"
        destino.mkdir()
        r = montar(fontes, str(destino))
        f = pq.read_table(str(destino / ARQUIVO_FICHAS)).to_pylist()[0]
        assert (f["abertura_valor"], f["abertura_parcial"]) == (d(20), True)
        assert serializar(r)["pendencias"]["fichas_abertura_parcial"] == 1

    def test_x949_sai_da_ficha_e_fica_contado(self, fontes, tmp_path):
        """Remessa para armazém (5.949) e o retorno (1.949): nem venda nem compra."""
        mov = os.path.join(fontes.movimentacao, ARQUIVO_MOVIMENTOS)
        linhas = pq.read_table(mov).to_pylist()
        linhas.append({**linhas[1], "cfop": "5949", "quantidade": d(4), "chave": "8" * 44, "numero_documento": "14"})
        pq.write_table(pa.Table.from_pylist(linhas, schema=pq.read_schema(mov)), mov)
        sup = os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO)
        entradas = pq.read_table(sup).to_pylist()
        entradas.append({**entradas[0], "cfop": "1949", "quantidade": d(4), "chave": "9" * 44})
        pq.write_table(pa.Table.from_pylist(entradas, schema=pq.read_schema(sup)), sup)
        destino = tmp_path / "x949"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert not [l for l in ficha(destino) if l["cfop"] in ("5949", "1949")]
        assert r.lancamentos_x949 == 2
        assert serializar(r)["fora_da_ficha"]["x949"] == 2

    def test_uso_e_consumo_sai_da_ficha_e_fica_contado(self, fontes, tmp_path):
        acrescentar_linhas(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO), [
            entrada_anterior(date(2021, 1, 6), 3, 9, 8, cfop="1556")])
        destino = tmp_path / "uso"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert len(ficha(destino)) == 4
        assert r.lancamentos_de_uso_e_consumo == 1
        assert serializar(r)["fora_da_ficha"] == {"uso_e_consumo": 1, "x949": 0}

    def test_periodo_do_cadastro_que_nao_cruza_a_base_e_recusado(self, fontes, tmp_path):
        from cat.infraestrutura.analitico.razao import PeriodoSemMovimento  # noqa: PLC0415
        fontes.periodo = (date(2019, 1, 1), date(2019, 12, 31))
        destino = tmp_path / "sem_periodo"
        destino.mkdir()
        with pytest.raises(PeriodoSemMovimento, match="01/2019 a 12/2019"):
            montar(fontes, str(destino))

    def test_periodo_do_cadastro_manda_no_inicio(self, fontes, tmp_path):
        # com o cadastro em 2021, a mesma base monta a mesma ficha
        fontes.periodo = (date(2021, 1, 1), date(2021, 12, 31))
        destino = tmp_path / "com_periodo"
        destino.mkdir()
        r = montar(fontes, str(destino))
        assert (r.periodo_inicio, r.periodo_fim, len(ficha(destino))) == ("2021-01-01", "2021-12-31", 4)


class TestSerieDaLinha:
    def test_a_serie_do_suportado_vai_para_a_ficha(self, fontes, tmp_path):
        caminho = os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO)
        linhas = pq.read_table(caminho).to_pylist()
        for l in linhas:
            l["serie"] = "3"
        esquema = pq.read_schema(caminho).append(pa.field("serie", pa.string()))
        pq.write_table(pa.Table.from_pylist(linhas, schema=esquema), caminho)
        destino = tmp_path / "serie"
        destino.mkdir()
        montar(fontes, str(destino))
        por_cfop = {l["cfop"]: l["serie"] for l in ficha(destino)}
        assert por_cfop["1403"] == "3"
        # a venda do relatório não tem série; a transferência da EFD de teste também não
        assert por_cfop["5405"] == ""


def trocar_codigos(fontes, entrada: str, inventario: str) -> None:
    """A entrada de 05/01 escriturada com o código de compra; a abertura, com o do kit."""
    sup = os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO)
    linhas = pq.read_table(sup).to_pylist()
    for l in linhas:
        if l["cfop"] == "1403":
            l["codigo"] = entrada
    pq.write_table(pa.Table.from_pylist(linhas, schema=pq.read_schema(sup)), sup)
    inv = os.path.join(fontes.movimentacao, ARQUIVO_INVENTARIO)
    linhas = pq.read_table(inv).to_pylist()
    for l in linhas:
        if l["data_inventario"] == date(2020, 12, 31):
            l["codigo"], l["quantidade"] = inventario, d(2)
    pq.write_table(pa.Table.from_pylist(linhas, schema=pq.read_schema(inv)), inv)


class TestDePara:
    """A mesma conta do cenário, com a entrada no código de compra (X08) e a
    abertura em kits de cinco (XK5, 2 kits): o de-para junta tudo em X."""

    def test_sem_de_para_a_entrada_e_a_abertura_se_perdem(self, fontes, tmp_path):
        trocar_codigos(fontes, "X08", "XK5")
        destino = tmp_path / "sem_depara"
        destino.mkdir()
        montar(fontes, str(destino))
        assert all(l["especie"] == "saida" for l in ficha(destino))

    def test_com_de_para_a_ficha_e_a_mesma_e_guarda_o_codigo_de_origem(self, fontes, tmp_path, montado):
        esperado = [(l["especie"], l["saldo_quantidade"], l["saldo_valor"]) for l in ficha(montado[0])]
        trocar_codigos(fontes, "X08", "XK5")
        depara = tmp_path / "depara.parquet"
        pq.write_table(pa.Table.from_pylist([
            {"cnpj": A, "codigo_origem": "X08", "codigo_destino": "X", "fator": d(1)},
            {"cnpj": A, "codigo_origem": "XK5", "codigo_destino": "X", "fator": d(5)},
        ]), str(depara))
        fontes.depara = str(depara)
        destino = tmp_path / "com_depara"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        linhas = ficha(destino)
        assert [(l["especie"], l["saldo_quantidade"], l["saldo_valor"]) for l in linhas] == esperado
        entrada = next(l for l in linhas if l["especie"] == "entrada")
        assert (entrada["codigo"], entrada["codigo_original"]) == ("X", "X08")
        assert all(l["codigo_original"] is None for l in linhas if l is not entrada)
        assert (r.linhas_com_depara, r.codigos_trocados_pelo_depara) == (1, 1)
        assert r.ressarcimento == d("1.4")
        assert Decimal(lista_de_fichas(str(destino))["linhas"][0]["abertura_quantidade"]) == 10


def com_venda_para_outro_estado(fontes, icms_proprio_da_entrada):
    """06/01: 3 un para outro estado (6.102). A entrada de 05/01 passa a dizer o ICMS próprio."""
    mov = os.path.join(fontes.movimentacao, ARQUIVO_MOVIMENTOS)
    linhas = pq.read_table(mov).to_pylist()
    linhas.append({**linhas[1], "cfop": "6102", "quantidade": d(3), "valor": d(45), "chave": "7" * 44,
                   "numero_documento": "13"})
    pq.write_table(pa.Table.from_pylist(linhas, schema=pq.read_schema(mov)), mov)
    sup = os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO)
    tabela = pq.read_table(sup)
    proprio = [icms_proprio_da_entrada if l["cfop"] == "1403" else d(0) for l in tabela.to_pylist()]
    pq.write_table(tabela.append_column("icms_proprio", pa.array(proprio, pa.decimal128(18, 6))), sup)


class TestConfrontoPelaEntrada:
    """Enquadramento 4: suportado baixado 3,00 (unitário 1,00); ICMS próprio da entrada
    6,00 em 10 un, 0,60 a unidade, 1,80 nas 3 — ressarcimento 1,20 e crédito do art. 271 1,80."""

    def test_confronta_com_o_icms_proprio_das_entradas_e_da_o_credito(self, fontes, tmp_path):
        com_venda_para_outro_estado(fontes, d(6))
        destino = tmp_path / "enq4"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP"})
        venda = next(l for l in ficha(destino) if l["cfop"] == "6102")
        assert venda["enquadramento"] == 4
        assert (venda["icms_efetivo"], venda["ressarcimento"], venda["credito_operacao_propria"]) == (
            d("1.8"), d("1.2"), d("1.8"))
        assert (r.confronto_pendente, r.confronto_pela_entrada) == (0, 1)
        assert r.credito_operacao_propria == d("1.8")
        enq = {e["codigo"]: e for e in serializar(r)["por_enquadramento"]}
        assert (enq["4"]["ressarcimento"], enq["4"]["credito"]) == ("1.20", "1.80")

    def test_sem_icms_proprio_na_apuracao_fica_pendente(self, fontes, tmp_path):
        """Apuração de antes da v0.53 não tem a coluna: o confronto de 2 e 4 fica como era."""
        com_venda_para_outro_estado(fontes, d(6))
        sup = os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO)
        pq.write_table(pq.read_table(sup).drop(["icms_proprio"]), sup)
        destino = tmp_path / "pendente"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP"})
        venda = next(l for l in ficha(destino) if l["cfop"] == "6102")
        assert venda["icms_efetivo"] is None and venda["credito_operacao_propria"] == 0
        assert (r.confronto_pendente, r.credito_operacao_propria) == (1, 0)


class TestReducaoDeBase:
    """Entrada com CST 70 reduz a base do ICMS efetivo da saída a consumidor.

    A entrada diz que a mercadoria tem o benefício; o quanto ele vale é a lei
    que diz — carga de 12% (artigo 34 do Anexo II). Então a venda de PDV da
    mercadoria X, R$ 20,00 a 18%, deixa de confrontar com R$ 3,60 e passa a
    confrontar com R$ 2,40, que é a redução de 33,3333% sobre a base.
    """

    @pytest.fixture
    def com_reducao(self, fontes, tmp_path):
        mov = tmp_path / "movimentacao"
        gravar(mov / ARQUIVO_ITENS, [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
            ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)), ("ncm", pa.string()),
        ], [{"cnpj": A, "codigo": "X", "descricao": "Refrigerante cola 2L", "unidade": "UN",
             "aliq_icms": d(18), "ncm": "33059000"}])
        gravar(mov / ARQUIVO_ITENS_DO_XML, [
            ("chave", pa.string()), ("numero_item", pa.int32()), ("emitente", pa.string()),
            ("destinatario", pa.string()), ("emissao", pa.date32()), ("ncm", pa.string()),
            ("cst_icms", pa.string()), ("bc_icms", pa.decimal128(18, 2)),
            ("valor", pa.decimal128(18, 2)), ("desconto", pa.decimal128(18, 2)),
            ("aliq_icms", pa.decimal128(9, 4)), ("cfop", pa.string()),
        ], [
            # a entrada de 05/01: base reduzida a 48% do valor, CST 70
            {"chave": "4" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "ncm": "33059000", "cst_icms": "570",
             "bc_icms": d(48), "valor": d(100), "desconto": d(0), "aliq_icms": d(25), "cfop": "5401"},
            # a saída da própria loja não entra na conta da redução
            {"chave": CHAVE_TRANSF, "numero_item": 1, "emitente": A, "destinatario": "22222222000100",
             "emissao": date(2021, 1, 6), "ncm": "33059000", "cst_icms": "070",
             "bc_icms": d(90), "valor": d(100), "desconto": d(0), "aliq_icms": d(18), "cfop": "5405"},
        ])
        destino = tmp_path / "razao_reduzido"
        destino.mkdir()
        return destino, montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})

    def test_a_venda_a_consumidor_confronta_com_a_base_reduzida(self, com_reducao):
        destino, _ = com_reducao
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["enquadramento"] == 1
        assert venda["reducao_base"] == d("33.3333")   # 18% com carga de 12%
        assert venda["icms_efetivo"] == d("2.400001")   # 20,00 x 66,6667% x 18%
        assert venda["ressarcimento"] == d("2.599999")  # 5,00 baixados - 2,40

    def test_o_resumo_diz_quanto_a_reducao_tirou_do_confronto(self, com_reducao):
        _, r = com_reducao
        assert r.saidas_com_reducao == 1
        assert round(r.efetivo_reduzido, 2) == d("1.20")  # 3,60 cheios - 2,40
        assert serializar(r)["reducao_de_base"] == {"saidas": 1, "efetivo_reduzido": "1.20"}

    def test_a_ficha_conta_as_saidas_com_reducao(self, com_reducao):
        destino, _ = com_reducao
        x = next(f for f in lista_de_fichas(str(destino))["linhas"] if f["codigo"] == "X")
        assert x["saidas_com_reducao"] == 1

    def test_sem_entrada_reduzida_a_aliquota_continua_cheia(self, montado):
        destino, r = montado
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["reducao_base"] is None and venda["icms_efetivo"] == d("3.60")
        assert r.saidas_com_reducao == 0

    def test_o_ncm_da_nota_vence_o_do_cadastro(self, fontes, tmp_path):
        """A venda com NCM no XML não depende do 0200 — e o coalesce entre as
        duas colunas não pode virar concatenação (bug da v0.57.1)."""
        mov = tmp_path / "movimentacao"
        gravar(mov / ARQUIVO_ITENS, [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
            ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)), ("ncm", pa.string()),
        ], [{"cnpj": A, "codigo": "X", "descricao": "Refrigerante cola 2L", "unidade": "UN",
             "aliq_icms": d(18), "ncm": "00000000"}])           # cadastro com NCM errado
        antigo = pq.read_table(str(mov / ARQUIVO_MOVIMENTOS)).to_pylist()
        gravar(mov / ARQUIVO_MOVIMENTOS, [
            ("cnpj", pa.string()), ("competencia", pa.date32()), ("operacao", pa.string()),
            ("codigo", pa.string()), ("data", pa.date32()), ("cfop", pa.string()),
            ("unidade", pa.string()), ("numero_item", pa.int32()), ("cst_icms", pa.string()),
            ("modelo", pa.string()), ("quantidade", pa.decimal128(20, 5)),
            ("valor", pa.decimal128(18, 2)), ("valor_icms", pa.decimal128(18, 2)),
            ("valor_st", pa.decimal128(18, 2)), ("chave", pa.string()),
            ("numero_documento", pa.string()), ("participante", pa.string()),
            ("ncm_xml", pa.string()), ("ncm", pa.string()), ("consumidor_final_xml", pa.bool_()),
        ], antigo + [
            # venda a consumidor final da EFD, com o NCM na nota
            {"cnpj": A, "competencia": date(2021, 1, 1), "operacao": "saida", "codigo": "X",
             "data": date(2021, 1, 6), "cfop": "5405", "cst_icms": "060", "modelo": "55",
             "unidade": "UN", "numero_item": 1, "quantidade": d(3), "valor": d(30),
             "valor_icms": d(0), "valor_st": d(0), "chave": "8" * 44, "numero_documento": "13",
             "ncm_xml": "33059000", "consumidor_final_xml": True},
        ])
        gravar(mov / ARQUIVO_ITENS_DO_XML, [
            ("chave", pa.string()), ("numero_item", pa.int32()), ("emitente", pa.string()),
            ("destinatario", pa.string()), ("emissao", pa.date32()), ("ncm", pa.string()),
            ("cst_icms", pa.string()), ("bc_icms", pa.decimal128(18, 2)),
            ("valor", pa.decimal128(18, 2)), ("desconto", pa.decimal128(18, 2)),
            ("aliq_icms", pa.decimal128(9, 4)), ("cfop", pa.string()),
        ], [{"chave": "4" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "ncm": "33059000", "cst_icms": "570",
             "bc_icms": d(48), "valor": d(100), "desconto": d(0), "aliq_icms": d(25), "cfop": "5401"}])
        destino = tmp_path / "ncm_da_nota"
        destino.mkdir()
        montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        venda = next(l for l in ficha(destino) if l["cfop"] == "5405" and l["origem"] == "efd")
        assert venda["enquadramento"] == 1
        assert venda["reducao_base"] == d("33.3333")
        assert venda["icms_efetivo"] == d("3.600002")            # 30 x 66,6667% x 18%
        # a venda de PDV do relatório não tem NCM e cai no cadastro, que aqui está errado
        pdv = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert pdv["reducao_base"] is None

    def test_duas_entradas_no_mesmo_dia_nao_quebram_a_gravacao(self, fontes, tmp_path):
        """A mediana de um número par de entradas é uma média, e média de
        decimal estoura as quatro casas do esquema se não for arredondada.

        O que a ficha grava é a redução da lei, não a medida — mas a medida
        continua sendo calculada para saber que há benefício, e é ali que o
        arredondamento quebrava."""
        mov = tmp_path / "movimentacao"
        gravar(mov / ARQUIVO_ITENS, [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
            ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)), ("ncm", pa.string()),
        ], [{"cnpj": A, "codigo": "X", "descricao": "Refrigerante cola 2L", "unidade": "UN",
             "aliq_icms": d(18), "ncm": "33059000"}])
        gravar(mov / ARQUIVO_ITENS_DO_XML, [
            ("chave", pa.string()), ("numero_item", pa.int32()), ("emitente", pa.string()),
            ("destinatario", pa.string()), ("emissao", pa.date32()), ("ncm", pa.string()),
            ("cst_icms", pa.string()), ("bc_icms", pa.decimal128(18, 4)),
            ("valor", pa.decimal128(18, 2)), ("desconto", pa.decimal128(18, 2)),
            ("aliq_icms", pa.decimal128(9, 4)), ("cfop", pa.string()),
        ], [
            # 51,2715% e 51,2714% -> mediana 51,27145%, que não cabe em 4 casas
            {"chave": "4" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "ncm": "33059000", "cst_icms": "570",
             "bc_icms": d("48.7285"), "valor": d(100), "desconto": d(0), "aliq_icms": d(25), "cfop": "5401"},
            {"chave": "7" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "ncm": "33059000", "cst_icms": "570",
             "bc_icms": d("48.7286"), "valor": d(100), "desconto": d(0), "aliq_icms": d(25), "cfop": "5401"},
        ])
        destino = tmp_path / "mediana"
        destino.mkdir()
        montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["reducao_base"] == d("33.3333")

    def test_sem_0200_a_aliquota_vem_da_nota_de_entrada(self, fontes, tmp_path):
        """Decisão do Victor, 17/09/2026: sem cadastro, vale a alíquota que o
        fornecedor usou na entrada da mesma mercadoria."""
        mov = tmp_path / "movimentacao"
        gravar(mov / ARQUIVO_ITENS, [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
            ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)), ("ncm", pa.string()),
        ], [{"cnpj": A, "codigo": "X", "descricao": "Refrigerante cola 2L", "unidade": "UN",
             "aliq_icms": None, "ncm": "33059000"}])          # 0200 sem alíquota
        gravar(mov / ARQUIVO_ITENS_DO_XML, [
            ("chave", pa.string()), ("numero_item", pa.int32()), ("emitente", pa.string()),
            ("destinatario", pa.string()), ("emissao", pa.date32()), ("ncm", pa.string()),
            ("cst_icms", pa.string()), ("bc_icms", pa.decimal128(18, 2)),
            ("valor", pa.decimal128(18, 2)), ("desconto", pa.decimal128(18, 2)),
            ("aliq_icms", pa.decimal128(9, 4)), ("cfop", pa.string()),
        ], [{"chave": "4" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "ncm": "33059000", "cst_icms": "570",
             "bc_icms": d(48), "valor": d(100), "desconto": d(0), "aliq_icms": d(25), "cfop": "5401"}])
        destino = tmp_path / "aliquota_da_entrada"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["aliquota"] == d("25.0000") and venda["reducao_base"] == d("52.0000")
        assert venda["icms_efetivo"] == d("2.4")             # 20 x 48% x 25% = carga de 12%
        assert r.saidas_com_aliquota_da_entrada == 1 and r.saidas_sem_aliquota == 0
        assert serializar(r)["aliquota_da_entrada"] == 1

    def test_entrada_de_fora_do_estado_nao_empresta_aliquota(self, fontes, tmp_path):
        """A compra interestadual vem a 4%, 7% ou 12%: não é a tributação
        interna da mercadoria, e não pode virar o confronto de uma saída
        interna (corrigido na v0.58.1)."""
        mov = tmp_path / "movimentacao"
        gravar(mov / ARQUIVO_ITENS, [
            ("cnpj", pa.string()), ("codigo", pa.string()), ("descricao", pa.string()),
            ("unidade", pa.string()), ("aliq_icms", pa.decimal128(9, 4)), ("ncm", pa.string()),
        ], [{"cnpj": A, "codigo": "X", "descricao": "Refrigerante cola 2L", "unidade": "UN",
             "aliq_icms": None, "ncm": "33059000"}])
        gravar(mov / ARQUIVO_ITENS_DO_XML, [
            ("chave", pa.string()), ("numero_item", pa.int32()), ("emitente", pa.string()),
            ("destinatario", pa.string()), ("emissao", pa.date32()), ("ncm", pa.string()),
            ("cst_icms", pa.string()), ("bc_icms", pa.decimal128(18, 2)),
            ("valor", pa.decimal128(18, 2)), ("desconto", pa.decimal128(18, 2)),
            ("aliq_icms", pa.decimal128(9, 4)), ("cfop", pa.string()),
        ], [{"chave": "4" * 44, "numero_item": 1, "emitente": "99999999000191", "destinatario": A,
             "emissao": date(2021, 1, 5), "ncm": "33059000", "cst_icms": "570",
             "bc_icms": d(48), "valor": d(100), "desconto": d(0), "aliq_icms": d(12),
             "cfop": "6401"}])                               # compra de outro estado
        destino = tmp_path / "de_fora"
        destino.mkdir()
        r = montar(fontes, str(destino), uf_por_cnpj={A: "SP", B: "SP"})
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["aliquota"] is None and venda["reducao_base"] is None
        assert venda["icms_efetivo"] is None
        assert r.saidas_com_aliquota_da_entrada == 0 and r.saidas_sem_aliquota == 1

    def test_o_0200_vence_a_nota_de_entrada(self, com_reducao):
        """Com cadastro, a alíquota é a dele: 18% do 0200, não os 25% da entrada."""
        destino, r = com_reducao
        venda = next(l for l in ficha(destino) if l["origem"] == "relatorio")
        assert venda["aliquota"] == d("18.0000")
        assert r.saidas_com_aliquota_da_entrada == 0

    def test_so_o_enquadramento_1_usa_a_base_reduzida(self):
        """Decisão do Victor, 17/09/2026: o 3 segue com a alíquota cheia."""
        linha = {"aliquota": d(18), "valor": d(100), "reducao_base": d(52),
                 "quantidade": d(1), "fator": d(1)}
        efetivo, _, _, reducao = _confronto(EnquadramentoLegal.CONSUMIDOR_FINAL, linha)
        assert (efetivo, reducao) == (d("8.64"), d(52))
        efetivo, _, _, reducao = _confronto(EnquadramentoLegal.ISENCAO_OU_NAO_INCIDENCIA, linha)
        assert (efetivo, reducao) == (d(18), None)

