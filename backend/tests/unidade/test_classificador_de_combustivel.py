"""O classificador: NCM manda, descrição confirma — e o contrário erra R$ 240 mil.

Três famílias de teste, cada uma guardando uma decisão que custou medição.

**A ordem da cascata.** `OLEO MOTOR DIESEL SAE15` tem NCM `27101932`, que é
lubrificante, e descrição que diz DIESEL. Quem deixa a descrição decidir lança
R$ 239.828 de lubrificante como crédito de combustível — medido em 273 linhas da
empresa G.

**E a NCM sozinha também falha**, no mesmo cliente: 86 linhas de `DIESEL S10`
com NCM vazio. Ali só a descrição salva — e a mesma lista tem `LANTERNA`, então
a descrição tem de saber dizer não.

**O fator nunca é 1 por omissão.** O GLP é tributado por quilo e o SPED declara
`UN`: assumir "um botijão é um quilo" erra vinte vezes.

As descrições usadas aqui são **formas** medidas em arquivo real, não linhas de
cliente: nome de produto de posto não identifica ninguém, e é a forma que o teste
precisa guardar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped import classificador_de_combustivel as classificador
from cat.infraestrutura.sped.classificador_de_combustivel import (
    ALTA,
    BAIXA,
    MEDIA,
    chave_de_agrupamento,
    classificar,
    fator_no_texto,
    forma_canonica,
    normalizar,
    produto_pela_descricao,
)
from cat.infraestrutura.sped.tabelas import tab_combustivel
from cat.infraestrutura.sped.tabelas.tab_combustivel import (
    DIESEL,
    ETANOL_HIDRATADO,
    FORA,
    GASOLINA,
    GLP,
    LUBRIFICANTE,
)

NCM_DIESEL = "27101921"
NCM_GASOLINA = "27101259"
NCM_GLP = "27111910"
NCM_LUBRIFICANTE = "27101932"
NCM_ETANOL = "22071090"
NCM_PARAFUSO = "73181500"


class TestANcmManda:
    """A inversão em relação ao crédito outorgado, e o dinheiro que ela salva."""

    def test_o_lubrificante_que_diz_diesel_sai_lubrificante(self):
        """**R$ 239.828 em 273 linhas** dependem deste teste.

        `2710.19.21` é óleo diesel; `2710.19.3` é óleo lubrificante. A
        subposição é juridicamente precisa e é a descrição que mente.
        """
        c = classificar("OLEO MOTOR DIESEL SAE15", NCM_LUBRIFICANTE, "UN")

        assert c.produto == LUBRIFICANTE
        assert not c.entra_na_tese

    def test_quando_discordam_a_ncm_vence_e_a_linha_vai_para_revisao(self):
        """Vence, mas não cala: a descrição divergente entra no porquê."""
        c = classificar("DIESEL S10", NCM_LUBRIFICANTE, "L")

        assert c.produto == LUBRIFICANTE
        assert c.revisar
        assert "diesel" in c.porque.lower(), "o porquê diz o que a descrição sugeria"

    def test_ncm_medida_da_confianca_alta(self):
        c = classificar("OLEO DIESEL B S10", NCM_DIESEL, "L")

        assert (c.produto, c.confianca, c.revisar) == (DIESEL, ALTA, False)

    def test_ncm_so_por_prefixo_da_confianca_media(self):
        """`27101933` não foi medida; `2710193` é a subposição dos lubrificantes.
        O prefixo classifica, mas não com a mesma certeza do que se contou."""
        c = classificar("OLEO QUALQUER", "27101933", "L")

        assert (c.produto, c.confianca) == (LUBRIFICANTE, MEDIA)

    def test_o_prefixo_nunca_promove_a_tese(self):
        """Errar para dentro da tese é pedir crédito; errar para fora é deixar
        linha para o revisor ver."""
        for _, produto in tab_combustivel.POR_PREFIXO:
            assert not tab_combustivel.entra_na_tese(produto), produto


class TestQuandoNaoHaNcm:
    """As 86 linhas que a NCM não salvaria."""

    @pytest.mark.parametrize("descricao, produto", [
        ("DIESEL S10", DIESEL),
        ("OLEO DIESEL COMUM", DIESEL),
        ("DIESEL S-500", DIESEL),
        ("GASOLINA COMUM", GASOLINA),
        ("P20 - GLP 20 KGS", GLP),
        ("ETANOL COMUM", ETANOL_HIDRATADO),
    ])
    def test_a_descricao_decide(self, descricao, produto):
        c = classificar(descricao, "", "L")

        assert c.produto == produto

    def test_e_sai_para_revisao_porque_e_inferencia_sobre_texto(self):
        c = classificar("DIESEL S10", "", "L")

        assert (c.confianca, c.revisar) == (MEDIA, True)
        assert "sem NCM" in c.porque

    @pytest.mark.parametrize("descricao", ["LANTERNA", "FAROL", "PARAFUSO",
                                           "", "   "])
    def test_a_descricao_tambem_sabe_dizer_nao(self, descricao):
        """Medido: a lista de NCM vazio da empresa G tem `LANTERNA` e `FAROL`."""
        c = classificar(descricao, "", "PC")

        assert c.produto == ""
        assert (c.confianca, c.revisar) == (BAIXA, True)

    @pytest.mark.parametrize("descricao", [
        "OLEO MOTOR DIESEL SAE15",
        "LUB MOTOR DIESEL 15W40",
        "OLEO DIESEL HIDRAULICO",
    ])
    def test_o_lubrificante_e_testado_antes_do_diesel(self, descricao):
        """**A ordem dentro de `produto_pela_descricao`, sem NCM para socorrer.**

        Estas descrições têm as duas palavras: `DIESEL` e marca de óleo. Se o
        teste de diesel vier primeiro, elas saem combustível — e aqui não há NCM
        para corrigir, porque é justamente o ramo em que a NCM faltou.

        Este teste nasceu de uma mutação que passou: a versão anterior usava
        `OLEO MOTOR - 20 LITROS`, que **não contém DIESEL**, e por isso não
        exercitava a ordem que dizia guardar.
        """
        produto, _, porque = produto_pela_descricao(descricao)

        assert produto == LUBRIFICANTE
        assert "SAE" in porque or "óleo motor" in porque.lower()

    def test_sem_marca_de_oleo_o_diesel_passa(self):
        """O outro lado: a guarda não pode comer combustível de verdade."""
        for descricao in ("DIESEL S10", "OLEO DIESEL COMUM", "DIESEL S-500"):
            assert produto_pela_descricao(descricao)[0] == DIESEL, descricao


class TestAPosicaoDaNcmEsvaziaAFila:
    """O que fez a fila de revisão cair de 10.066 para 98 linhas.

    Parafuso é capítulo 73 e não é combustível em nenhuma circunstância — isso é
    fato sobre a nomenclatura, não inferência. Sem este corte, toda a compra
    comum da empresa caía em "não sei, revisar", e fila com dez mil parafusos
    não é fila.
    """

    @pytest.mark.parametrize("ncm", ["73181500", "40122000", "87169090",
                                     "25171000", "84212990"])
    def test_ncm_de_outra_posicao_sai_fora_sem_revisao(self, ncm):
        c = classificar("QUALQUER COISA", ncm, "PC")

        assert (c.produto, c.confianca, c.revisar) == (FORA, ALTA, False)

    def test_e_mesmo_quando_a_descricao_diz_diesel(self):
        """Porque a nomenclatura é categórica: um parafuso chamado "DIESEL" é um
        parafuso."""
        c = classificar("PARAFUSO DIESEL", NCM_PARAFUSO, "PC")

        assert c.produto == FORA

    @pytest.mark.parametrize("ncm", ["", "2710", "271019", "abcdefgh", "2710192"])
    def test_ncm_curta_ou_torta_e_desconhecida_e_nao_descartada(self, ncm):
        """Descartar por NCM malformada mataria as 86 linhas de `DIESEL S10`
        sem NCM — a descrição ainda tem de ser consultada."""
        assert not tab_combustivel.fora_das_posicoes(ncm)
        assert classificar("DIESEL S10", ncm, "L").produto == DIESEL

    def test_as_posicoes_cobrem_o_que_a_tabela_conhece(self):
        """Se uma NCM da tabela caísse fora das posições, ela nunca seria
        consultada — o corte viria antes."""
        for ncm in tab_combustivel.POR_NCM:
            assert not tab_combustivel.fora_das_posicoes(ncm), ncm


class TestOFator:
    def test_litro_declarado_em_litro_tem_fator_um(self):
        for unidade in ("L", "LT", "LTS", "l", "LITRO", "LI"):
            c = classificar("DIESEL S10", NCM_DIESEL, unidade)
            assert c.fator == Decimal(1), unidade
            assert c.unidade_tributada == "litro"

    def test_o_glp_e_por_quilo_e_o_fator_vem_do_texto(self):
        """O SPED declara `UN` e a ad rem é por quilo. O fardo está no texto, e
        em dois formatos no mesmo cliente."""
        for descricao in ("P20 - GLP 20 KGS", "20 KGS GLP ONU 1075 2.1"):
            c = classificar(descricao, NCM_GLP, "UN")
            assert c.unidade_tributada == "quilo", descricao
            assert c.fator == Decimal(20), descricao
            assert not c.revisar, descricao

    def test_embalagem_sem_fator_nenhum_vai_para_revisao(self):
        """**Nunca 1 por omissão:** um botijão não é um quilo."""
        c = classificar("GLP BOTIJAO", NCM_GLP, "UN")

        assert c.fator is None
        assert c.revisar
        assert "embalagem" in c.porque

    def test_o_0220_vence_o_texto(self):
        """O registro é a fonte certa; o texto é o recurso de quem não o tem."""
        c = classificar("P20 - GLP 20 KGS", NCM_GLP, "UN",
                        conversao={"UN": Decimal(13)})

        assert c.fator == Decimal(13)
        assert "0220" in c.porque

    def test_o_fator_do_texto_tem_de_casar_com_a_unidade_tributada(self):
        """`20LT` não serve para quem é tributado por quilo: inventar densidade
        aqui seria calcular no lugar errado."""
        assert fator_no_texto("GLP 20 LT", "quilo") is None
        assert fator_no_texto("GLP 20 KGS", "quilo") == Decimal(20)

    def test_produto_de_percentual_nao_tem_unidade_ad_rem(self):
        """Lubrificante e etanol hidratado são tributados por percentual sobre o
        valor: pedir unidade tributada a eles é erro de categoria."""
        for descricao, ncm in (("OLEO MOTOR SAE", NCM_LUBRIFICANTE),
                               ("ETANOL COMUM", NCM_ETANOL)):
            c = classificar(descricao, ncm, "L")
            assert c.unidade_tributada == "", descricao
            assert "percentual" in c.porque, descricao


class TestANormalizacao:
    @pytest.mark.parametrize("bruta, esperada", [
        ("DIESEL S-10", "DIESEL S10"),
        ("DIESEL S 10", "DIESEL S10"),
        ("OLEO DIESEL BS10", "OLEO DIESEL S10"),
        ("GASOLINA COMUM.....................", "GASOLINA COMUM"),
        ("OLEO DIESEL B S-10 ORIGINAL(BOMBA:27 BICO:27)",
         "OLEO DIESEL B S10 ORIGINAL"),
        ("ÓLEO DIESEL", "OLEO DIESEL"),
    ])
    def test_normalizar_tira_o_que_nao_distingue(self, bruta, esperada):
        assert normalizar(bruta) == esperada

    def test_a_forma_canonica_colapsa_mais_que_a_normalizada(self):
        """**Medido: 132 descrições de `27101921` colapsam para 18 formas.**

        São duas normalizações porque servem a coisas opostas: agrupar quer
        menos informação, revisar quer mais.
        """
        variantes = ["OLEO DIESEL B S10", "DIESEL S-10", "DIESEL S 10",
                     "OLEO DIESEL BS10", "DIESEL S10 ORIGINAL",
                     "ORIGINAL DIESEL S10", "OLEO DIESEL B S10 - COMUM",
                     "OLEO DIESEL B S-10 ORIGINAL(BOMBA:27 BICO:27)"]

        assert len({forma_canonica(v) for v in variantes}) == 1
        assert len({normalizar(v) for v in variantes}) > 1

    def test_a_forma_canonica_nao_colapsa_produtos_diferentes(self):
        """O colapso é para agrupar revisão, não para confundir produto."""
        formas = {forma_canonica(d) for d in
                  ("DIESEL S10", "GASOLINA COMUM", "GLP 13 KG",
                   "ETANOL HIDRATADO", "DIESEL S500")}

        assert len(formas) == 5

    def test_a_chave_nao_e_o_cod_item(self):
        """O posto gera um código por bico de bomba: indexar por `COD_ITEM`
        multiplicaria a fila sem acrescentar um produto."""
        um = chave_de_agrupamento("DIESEL S10 (BOMBA:27 BICO:27)", NCM_DIESEL)
        outro = chave_de_agrupamento("DIESEL S10 (BOMBA:31 BICO:02)", NCM_DIESEL)

        assert um == outro


class TestNuncaLevanta:
    """A confiança da classificação **não recusa** — ela emite tudo, ranqueado.

    Quem recusa é a cobertura da regra, que é fato sobre tabela e mora em
    `tab_ad_rem`. Aqui, exceção faria a linha desaparecer do relatório em vez de
    chegar ao revisor.
    """

    @pytest.mark.parametrize("descricao, ncm, unidade", [
        ("", "", ""),
        (None, None, None),
        ("x" * 500, "9" * 20, "???"),
        ("DIESEL", "27101921", ""),
        ("💧", "2710.19.21", "L"),
    ])
    def test_entrada_torta_devolve_classificacao_em_vez_de_erro(
            self, descricao, ncm, unidade):
        c = classificar(descricao, ncm, unidade)

        assert isinstance(c, classificador.Classificacao)

    def test_o_que_nao_se_sabe_vem_marcado_para_revisao(self):
        c = classificar("ABOBRINHA ESPACIAL", "", "KG")

        assert c.produto == ""
        assert c.revisar
        assert c.porque, "sem porquê o revisor não tem o que julgar"

    def test_toda_classificacao_traz_porque(self):
        for descricao, ncm, unidade in (
                ("DIESEL S10", NCM_DIESEL, "L"),
                ("PARAFUSO", NCM_PARAFUSO, "PC"),
                ("LANTERNA", "", "PC"),
                ("GLP", NCM_GLP, "UN")):
            assert classificar(descricao, ncm, unidade).porque


class TestOQueEntraNaTese:
    @pytest.mark.parametrize("ncm, entra", [
        (NCM_DIESEL, True),
        (NCM_GASOLINA, True),
        (NCM_GLP, True),
        (NCM_ETANOL, False),        # dúvida aberta
        (NCM_LUBRIFICANTE, False),  # outra tese
        (NCM_PARAFUSO, False),
    ])
    def test_so_os_tres_do_monofasico(self, ncm, entra):
        assert classificar("QUALQUER", ncm, "L").entra_na_tese is entra

    @pytest.mark.parametrize("descricao, ncm", [
        ("ETANOL HIDRATADO COMBUSTIVEL", NCM_ETANOL),
        ("OLEO MOTOR SAE 15W40", NCM_LUBRIFICANTE),
    ])
    def test_o_etanol_e_o_lubrificante_aparecem_mas_fora_do_total(
            self, descricao, ncm):
        """Os dois são classificados com confiança **alta** — não são dúvida de
        classificação. O que os tira do total é a tese, não a certeza.

        A descrição de cada um casa com a NCM de propósito: trocá-las criaria
        discordância, que é outro caso e baixa a confiança com razão.
        """
        c = classificar(descricao, ncm, "L")

        assert (c.confianca, c.revisar) == (ALTA, False)
        assert not c.entra_na_tese

    def test_descricao_que_discorda_da_ncm_baixa_a_confianca(self):
        """O irmão do teste acima, e a razão de ele parametrizar: descrição de
        lubrificante sob NCM de etanol é discordância, e discordância revisa."""
        c = classificar("OLEO MOTOR SAE", NCM_ETANOL, "L")

        assert (c.produto, c.confianca, c.revisar) == (
            ETANOL_HIDRATADO, MEDIA, True)
