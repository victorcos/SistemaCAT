"""Os pares do de-para, no desenho da empresa D.

Venda com o código do produto (`1012`), compra com o mesmo código mais espaços
e "08" (`1012           08`, e às vezes `101208`), kit de três com `K3`, e
um código de marketplace que nada liga — esse vai para o cliente.
"""

from decimal import Decimal

from cat.dominio.depara.candidatos import (
    Confianca,
    ItemParaCasar,
    Motivo,
    fator_do_kit,
    gtin_valido,
    normalizar_codigo,
    normalizar_descricao,
    propor,
)

D = Decimal


def item(codigo, entradas=0, saidas=0, descricao="", ncm="33059000", gtins=(), estoque=0,
         dev_venda=0, dev_compra=0):
    return ItemParaCasar(codigo=codigo, descricao=descricao, ncm=ncm, gtins=frozenset(gtins),
                         entradas=D(entradas), saidas=D(saidas), estoque_inicial=D(estoque),
                         devolucoes_de_venda=D(dev_venda), devolucoes_de_compra=D(dev_compra))


BASE = [
    item("1012", saidas=100, descricao="GRECIN 2000 HOMEM LOCAO Lote: 11812022 Val: 01/06/25"),
    item("1012           08", entradas=300, descricao="GRECIN 2000 HOMEM LOCAO"),
    item("101208", entradas=24, descricao="GRECIN 2000 HOMEM LOCAO"),
    item("3133", saidas=40, descricao="GRECIN 5 PG PRETO"),
    item("313308", entradas=60, descricao="GRECIN 5 PG PRETO"),
    item("4001", saidas=10, descricao="GRECIN CONTROL GX SH RED GRIS 147ML"),
    item("400108", entradas=12, descricao="GRECIN CONTROL GX SH RED GRIS 147ML"),
    item("1111", saidas=50, descricao="GRECIN 5 CAST. CLARO"),
    item("1111K3", saidas=1, descricao="GRECIN 5 CAST. CLARO KIT 3X"),
    item("1111K3         08", entradas=500, descricao="GRECIN 5 CAST. CLARO KIT 3X"),
    item("X0046E1FBP", saidas=7, descricao="Grecin 5 Barba e Bigode Castanho Claro", ncm="33059000"),
]


def pares_por_origem(itens):
    return {p.origem: p for p in propor(itens)}


class TestNormalizacao:
    def test_codigo_sem_espacos(self):
        assert normalizar_codigo("1012           08") == normalizar_codigo("101208") == "101208"

    def test_descricao_sem_lote_validade_e_acento(self):
        assert normalizar_descricao("Grecin 2000 Homem Loção Lote: 11812022 Val: 01/06/25") == "GRECIN 2000 HOMEM LOCAO"

    def test_gtin(self):
        assert gtin_valido("7891653040016")
        assert not gtin_valido("7891653040017")
        assert not gtin_valido("SEM GTIN") and not gtin_valido("0000000000000") and not gtin_valido("")

    def test_kit_pelo_codigo_e_pela_descricao(self):
        assert fator_do_kit(item("1111K3")) == (3, "1111")
        assert fator_do_kit(item("CB9", descricao="Kit 3x Grecin Gel tonalizante")) == (3, "CB9")
        assert fator_do_kit(item("1111", descricao="GRECIN 5 CAST. CLARO")) is None


class TestPares:
    def test_sufixo_que_se_repete_liga_compra_e_venda(self):
        pares = pares_por_origem(BASE)
        for origem, destino in (("1012           08", "1012"), ("313308", "3133"), ("400108", "4001")):
            assert (pares[origem].destino, pares[origem].fator) == (destino, D(1))
            assert Motivo.SUFIXO in pares[origem].motivos
            assert pares[origem].confianca is Confianca.ALTA

    def test_o_mesmo_codigo_com_e_sem_espacos(self):
        assert pares_por_origem(BASE)["101208"].destino == "1012"

    def test_kit_leva_fator_e_encadeia_com_o_sufixo(self):
        pares = pares_por_origem(BASE)
        assert (pares["1111K3"].destino, pares["1111K3"].fator) == ("1111", D(3))
        compra = pares["1111K3         08"]
        assert (compra.destino, compra.fator) == ("1111", D(3))
        assert {Motivo.SUFIXO, Motivo.KIT} <= set(compra.motivos)

    def test_kit_de_compra_acha_a_unidade_que_tem_dois_codigos(self):
        """Na empresa D: `3133K3         08` entra, e a unidade é `3133` e `3133           08`."""
        itens = BASE + [
            item("3133           08", entradas=22668, descricao="GRECIN 5 PG PRETO"),
            item("3133K3         08", entradas=1268, descricao="GRECIN 5 PG PRETO KIT 3X", gtins={"7891653040238"}),
        ]
        compra = pares_por_origem(itens)["3133K3         08"]
        assert (compra.destino, compra.fator) == ("3133", D(3))
        assert Motivo.KIT in compra.motivos

    def test_kit_com_descricao_abreviada_acha_a_unidade_pelo_comeco_do_codigo(self):
        itens = BASE + [
            item("3132", saidas=12416, descricao="GRECIN 5 PG CAST. ESCURO"),
            item("3132           08", entradas=9000, descricao="GRECIN 5 PG CAST. ESCURO"),
            item("3132K3         08", entradas=1768, descricao="GRECIN 5 PG CAST. ESC KIT 3X"),
        ]
        compra = pares_por_origem(itens)["3132K3         08"]
        assert (compra.destino, compra.fator) == ("3132", D(3))

    def test_comeco_do_codigo_com_descricao_de_outro_produto_nao_liga(self):
        itens = [item("31", saidas=100, descricao="VAGISIL DESODORANTE FP"),
                 item("31K3         08", entradas=30, descricao="GRECIN 5 PG CAST. ESC KIT 3X")]
        assert propor(itens) == []

    def test_codigo_so_com_devolucao_de_compra_junta_com_o_da_entrada(self):
        """O `4004` só tinha devolução ao fornecedor (5.411); a entrada foi no `4004           08`."""
        itens = BASE + [
            item("4004", dev_compra=2300, ncm="34012010", gtins={"7891653040047"},
                 descricao="PACK VAGISIL PH + DEO PH Lote: 32002023 Val: 01/07/26"),
            item("4004           08", entradas=2316, ncm="34012010", gtins={"7891653040047"},
                 descricao="PACK VAGISIL PH + DEO PH"),
        ]
        par = pares_por_origem(itens)["4004           08"]
        assert (par.destino, par.fator) == ("4004", D(1))

    def test_so_devolucao_dos_dois_lados_nao_conserta_nada(self):
        itens = [item("5005", dev_compra=10, gtins={"7891653040047"}, descricao="PRODUTO X"),
                 item("5005           08", dev_compra=5, gtins={"7891653040047"}, descricao="PRODUTO X")]
        assert propor(itens) == []

    def test_codigo_sem_ligacao_fica_para_o_cliente(self):
        pares = pares_por_origem(BASE)
        assert "X0046E1FBP" not in pares
        assert all(p.destino != "X0046E1FBP" for p in pares.values())

    def test_sufixo_que_coincide_em_produtos_diferentes_nao_liga(self):
        """Código numérico denso: 1024078 e 102407 são produtos diferentes."""
        itens = []
        for base, nome_a, nome_b in (("102407", "LEITE UHT 1L", "PAPEL TOALHA 2UN"), ("270105", "ARROZ 5KG", "SABAO PO 1KG"),
                                     ("274461", "CAFE 500G", "BISCOITO 200G"), ("283452", "OLEO 900ML", "DETERGENTE 500ML")):
            itens += [item(base, saidas=5, descricao=nome_a), item(base + "8", entradas=5, descricao=nome_b)]
        assert propor(itens) == []

    def test_sufixo_isolado_nao_basta(self):
        so_um = [item("1012", saidas=5), item("101208", entradas=5, descricao="OUTRA COISA", ncm="1")]
        assert propor(so_um) == []

    def test_gtin_igual(self):
        pares = pares_por_origem([
            item("A1", saidas=3, gtins=["7891653040016"], ncm=""),
            item("FORN-9", entradas=6, gtins=["07891653040016"], ncm=""),
        ])
        assert (pares["FORN-9"].destino, pares["FORN-9"].motivos) == ("A1", (Motivo.GTIN,))

    def test_descricao_e_ncm_e_confianca_media(self):
        pares = pares_por_origem([
            item("ABC", saidas=3, descricao="GRECIN 5 PRETO Lote: 123 Val: 01/08/25"),
            item("XYZ", entradas=6, descricao="Grecin 5 Preto"),
        ])
        assert (pares["XYZ"].destino, pares["XYZ"].confianca) == ("ABC", Confianca.MEDIA)

    def test_dois_produtos_completos_nao_se_juntam(self):
        assert propor([
            item("P1", entradas=5, saidas=5, gtins=["7891653040016"]),
            item("P2", entradas=5, saidas=5, gtins=["7891653040016"]),
        ]) == []

    def test_gtin_nao_liga_kit_a_unidade(self):
        pares = pares_por_origem([
            item("2222", saidas=5, descricao="SHAMPOO A", gtins=["7891653040016"]),
            item("2222K3", entradas=9, descricao="SHAMPOO A KIT 3X", gtins=["7891653040016"]),
        ])
        # liga pelo kit, com fator, e não pelo GTIN com fator 1
        assert (pares["2222K3"].fator, pares["2222K3"].motivos) == (D(3), (Motivo.KIT,))

    def test_fator_em_conflito_baixa_a_confianca(self):
        pares = pares_por_origem([
            item("UNID", saidas=5, descricao="CREME B"),
            # dois kits com o mesmo GTIN, um de 3 e outro de 6: o GTIN diz que são iguais, o kit não
            item("KITA", entradas=9, descricao="CREME B KIT 3X", gtins=["7891653040016"]),
            item("KITB", entradas=2, descricao="CREME B KIT 6X", gtins=["7891653040016"]),
        ])
        assert all(p.confianca is Confianca.MEDIA for p in pares.values())
        assert any("conflito" in p.explicacao for p in pares.values())

    def test_gtin_com_descricao_de_outro_produto_nao_liga(self):
        """O 0200 da empresa D tinha o GTIN do 1050 no 1114."""
        assert propor([
            item("1050", saidas=5, descricao="GRECIN TONS DE GRISALHO", gtins=["7891653010507"]),
            item("1114", entradas=9, descricao="GRECIN 5 PRETO", gtins=["7891653010507"]),
        ]) == []
        # e a mesma mercadoria com a descrição de outro fornecedor liga
        pares = pares_por_origem([
            item("1050", saidas=5, descricao="GRECIN TONS DE GRISALHO", gtins=["7891653010507"]),
            item("1050-N", entradas=9, descricao="TONS DE GRISALHO GELGRECIN 40G", gtins=["7891653010507"]),
        ])
        assert pares["1050-N"].destino == "1050"

    def test_estoque_inicial_conta_como_origem(self):
        pares = pares_por_origem([
            item("V1", saidas=5, gtins=["7891653040016"]),
            item("V1-ANTIGO", estoque=10, gtins=["7891653040016"]),
        ])
        assert pares["V1-ANTIGO"].destino == "V1"
