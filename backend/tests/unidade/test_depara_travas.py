"""As travas que tiram um par de prova forte do "vale sozinho".

Os casos vêm das duas bases medidas em 10/11/2026: a empresa 29 (supermercado)
e a execução 227 (material de construção).
"""

from datetime import date, timedelta
from decimal import Decimal

from cat.dominio.depara.candidatos import (
    ItemParaCasar,
    Motivo,
    avisos_do_par,
    gtins_contaminados,
    medidas_da_descricao,
    propor,
    travas_do_par,
    vale_sozinho,
)

D = Decimal
UM = D(1)
SEGUNDA = date(2021, 10, 4)


def semanas(*n):
    return frozenset(SEGUNDA + timedelta(weeks=i) for i in n)


def item(codigo, descricao="", ncm="19053100", entradas=0, saidas=0, gtins=(), gtins_do_xml=(),
         sem_saida=(), sem_entrada=(), custo=None, preco=None):
    return ItemParaCasar(codigo=codigo, descricao=descricao, ncm=ncm, gtins=frozenset(gtins),
                         gtins_do_xml=frozenset(gtins_do_xml), entradas=D(entradas), saidas=D(saidas),
                         semanas_com_saida=semanas(*sem_saida), semanas_com_entrada=semanas(*sem_entrada),
                         custo_unitario=None if custo is None else D(custo),
                         preco_de_venda=None if preco is None else D(preco))


class TestSufixo:
    def test_a_corrente_joelho_argamassa_vai_para_a_revisao(self):
        """Execução 227: o sufixo liga o joelho ao código de compra dele, o GTIN
        dos dois documentos liga esse código à argamassa, e o grupo propõe
        joelho → argamassa, que vale sozinho por ter GTIN e sufixo no motivo."""
        gtin = "7891960123457"
        itens = [
            item("J1", "JOELHO PVC ROSCA AMANCO 90X3/4", "39174090", saidas=40),
            item("J108", "JOELHO PVC ROSCA AMANCO 90X3/4", "39174090", entradas=50, gtins_do_xml={gtin}),
            item("K1", "LUVA PVC SOLDA AMANCO 25MM", "39174090", saidas=10),
            item("K108", "LUVA PVC SOLDA AMANCO 25MM", "39174090", entradas=10),
            item("L1", "CAP PVC SOLDA AMANCO 25MM", "39174090", saidas=10),
            item("L108", "CAP PVC SOLDA AMANCO 25MM", "39174090", entradas=10),
            item("A1", "ARGAMASSA PRECONMASSA 20KG AC3 EXT", "32149000", saidas=500, gtins_do_xml={gtin}),
        ]
        pares = {p.origem: p for p in propor(itens)}
        joelho = pares["J1"]
        assert joelho.destino == "A1"
        assert {Motivo.GTIN, Motivo.SUFIXO} <= set(joelho.motivos)
        assert not vale_sozinho(joelho)
        assert any("sufixo entre descrições diferentes" in t for t in joelho.travas)
        assert "revisar:" in joelho.explicacao
        # o par de sufixo entre descrições iguais continua valendo
        assert vale_sozinho(pares["K108"])

    def test_sufixo_sem_descricao_de_um_lado_nao_trava(self):
        travas = travas_do_par(item("10108"), item("101", "GRECIN 5 PRETO"), UM, [Motivo.SUFIXO])
        assert travas == ()


class TestGtinContaminado:
    def test_o_gtin_em_dois_capitulos_trava_o_par(self):
        """Empresa 29: o GTIN do milho verde estava também no creme de leite."""
        gtin = "7897517209391"
        itens = [item("S1", "CR LEITE TP 200G ITALAC", "04022930", gtins_do_xml={gtin}),
                 item("S2", "CREME DE LEITE ITALAC 200G", "04022930", gtins_do_xml={gtin}),
                 item("M1", "MILHO VERDE FUGINI 170G", "20058000", gtins_do_xml={gtin})]
        sujos = gtins_contaminados(itens)
        assert sujos == {gtin}
        travas = travas_do_par(itens[0], itens[1], UM, [Motivo.GTIN], sujos)
        assert any("capítulos de NCM diferentes" in t for t in travas)

    def test_o_ncm_generico_nao_contamina(self):
        gtin = "7897517209391"
        itens = [item("S1", ncm="04022930", gtins={gtin}), item("S2", ncm="11111111", gtins={gtin})]
        assert gtins_contaminados(itens) == frozenset()


class TestConvivencia:
    def test_vender_nas_mesmas_semanas_trava(self):
        o = item("1", sem_saida=(0, 1, 2))
        d = item("2", sem_saida=(1, 2, 5))
        assert any("mesmas semanas (2)" in t for t in travas_do_par(o, d, UM, [Motivo.GTIN]))

    def test_troca_de_codigo_nao_convive(self):
        """O código velho para de vender quando o novo começa; uma semana de
        sobreposição é a troca, não convivência."""
        o = item("1", sem_saida=(0, 1, 2))
        d = item("2", sem_saida=(2, 3, 4))
        assert travas_do_par(o, d, UM, [Motivo.GTIN]) == ()

    def test_compra_num_codigo_e_venda_no_outro_nao_convive(self):
        o = item("1", sem_entrada=(0, 1, 2, 3))
        d = item("2", sem_saida=(0, 1, 2, 3))
        assert travas_do_par(o, d, UM, [Motivo.GTIN]) == ()


class TestMedida:
    def test_le_peso_e_volume(self):
        assert medidas_da_descricao("Cha Leao 1,5l Matte") == {"volume": D("1500")}
        assert medidas_da_descricao("ARGAMASSA 20KG AC3") == {"massa": D("20000")}
        assert medidas_da_descricao("Biscoito Cesta Natal 115/125g") == {"massa": D("125")}

    def test_tamanhos_diferentes_travam(self):
        o = item("1", "Pao Seven Boys 300g Bisnaguinha")
        d = item("2", "Pao Seven Boys 450g Tradicional")
        assert any("300 g × 450 g" in t for t in travas_do_par(o, d, UM, [Motivo.GTIN]))

    def test_diferenca_pequena_passa(self):
        """O pêssego da cesta (430 g) e o da marca (450 g): 4%, dentro dos 10%."""
        o = item("1", "Pessego Calda Cesta Natal 430g")
        d = item("2", "Pessego Calda Schramm 450g Esp Extra")
        assert travas_do_par(o, d, UM, [Motivo.GTIN]) == ()

    def test_o_fator_desconta_a_medida(self):
        o = item("1", "AGUA MINERAL 6L")
        d = item("2", "AGUA MINERAL 1L")
        assert travas_do_par(o, d, D(6), [Motivo.KIT]) == ()


class TestCusto:
    def test_custo_cinco_vezes_o_do_destino_trava(self):
        o = item("1", custo="50")
        d = item("2", custo="10")
        assert any("custo incoerente: 5.00" in t for t in travas_do_par(o, d, UM, [Motivo.GTIN]))

    def test_custo_parecido_passa(self):
        assert travas_do_par(item("1", custo="11"), item("2", custo="10"), UM, [Motivo.GTIN]) == ()

    def test_sem_entrada_no_destino_compara_com_o_preco_de_venda(self):
        assert travas_do_par(item("1", custo="7"), item("2", preco="10"), UM, [Motivo.GTIN]) == ()
        assert travas_do_par(item("1", custo="20"), item("2", preco="10"), UM, [Motivo.GTIN]) != ()

    def test_sem_dado_nao_trava(self):
        """Falta de preço não é prova contra."""
        assert travas_do_par(item("1"), item("2", preco="10"), UM, [Motivo.GTIN]) == ()


class TestNcmDeCapituloDiferenteEhSoAviso:
    def test_a_gaveta_com_ncm_de_empilhadeira_nao_e_travada_pelo_ncm(self):
        """Empresa 29: o mesmo produto, com o NCM errado num cadastro. Barrar
        pelo NCM separava 28 pares certos; o erro é de cadastro, e vira aviso.
        (Se o GTIN do par for o que está nos dois capítulos, quem trava é o
        GTIN contaminado — outra regra, medida à parte.)"""
        o = item("G1", "GAVETA BEMATECH", "83030000")
        d = item("G2", "GAVETA DINHEIRO GD56 PRET BEMATECH", "84279000")
        assert travas_do_par(o, d, UM, [Motivo.GTIN]) == ()
        avisos = avisos_do_par(o, d)
        assert len(avisos) == 1 and "83030000 × 84279000" in avisos[0]

    def test_o_aviso_vai_no_par_e_na_explicacao(self):
        itens = [item("10108", "GAVETA BEMATECH", "83030000", entradas=5),
                 item("101", "GAVETA BEMATECH GD56", "84279000", saidas=5),
                 item("20208", "BOBINA TERMICA 80MM", "48169000", entradas=5),
                 item("202", "BOBINA TERMICA 80MM", "48169000", saidas=5),
                 item("30308", "ETIQUETA GONDOLA", "48211000", entradas=5),
                 item("303", "ETIQUETA GONDOLA", "48211000", saidas=5)]
        par = {p.origem: p for p in propor(itens)}["10108"]
        assert vale_sozinho(par)
        assert par.avisos and "atenção:" in par.explicacao
