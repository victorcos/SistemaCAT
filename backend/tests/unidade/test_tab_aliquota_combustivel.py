"""A alíquota do combustível na era do ST — a tabela que troca de era no meio.

Duas coisas são testadas aqui, e a segunda é a que protege.

A primeira é que ela **acerta** onde foi lida no texto da lei. A segunda é que
ela **recusa** em três situações diferentes, com erros diferentes: quando a
competência já é do monofásico (pergunta errada), quando o par UF/produto não foi
lido (dado que falta), e quando circula por aí um valor que já se provou errado.

Confundir a primeira recusa com a segunda é o erro caro: quem trata "não sei" e
"aqui não há percentual" como a mesma coisa acaba completando com a interna do
estado uma conta que devia ser `litros × ad rem × FCV`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.tabelas import tab_aliquota_combustivel as tab
from cat.infraestrutura.sped.tabelas.tab_ad_rem import DIESEL, GASOLINA, GLP
from cat.infraestrutura.sped.tabelas.tab_aliquota_combustivel import (
    ETANOL_HIDRATADO,
    LUBRIFICANTE,
    AliquotaDeCombustivelDesconhecida,
    ForaDoRegimePercentual,
    MesPartido,
    interna,
    no_monofasico,
)


class TestOQueALeiDoEspiritoSantoDiz:
    @pytest.mark.parametrize("produto, competencia, esperado", [
        (DIESEL, "2020-10", 12),
        (DIESEL, "2022-12", 12),
        (DIESEL, "2023-04", 12),
        (GASOLINA, "2020-10", 27),
        (GASOLINA, "2023-05", 27),
        (ETANOL_HIDRATADO, "2021-06", 27),
    ])
    def test_os_valores_lidos_no_texto_consolidado(self, produto, competencia, esperado):
        assert interna("ES", produto, competencia) == Decimal(esperado)

    def test_nenhum_dos_tres_segue_a_interna_geral_do_estado(self):
        """A razão de esta tabela existir separada de `tab_aliquota_icms`.

        A geral do ES é 17%, e nenhum dos três combustíveis a usa.
        """
        geral = Decimal(17)
        for produto in (DIESEL, GASOLINA, ETANOL_HIDRATADO):
            assert interna("ES", produto, "2022-06") != geral, produto

    def test_usar_a_geral_na_gasolina_credita_37_por_cento_menos(self):
        """O tamanho do erro de quem não separa combustível do resto."""
        geral, da_lei = Decimal(17), interna("ES", GASOLINA, "2022-06")

        a_menos = (da_lei - geral) / da_lei * 100
        assert Decimal(36) < a_menos < Decimal(38)

    def test_a_uf_vem_normalizada(self):
        assert interna("es", DIESEL, "2022-06") == interna(" ES ", DIESEL, "2022-06")


class TestARevogacaoQueNaoProduziuEfeitos:
    """O diesel do ES tem uma pegadinha de vigência que vale um teste.

    A Lei 11.768/2022 revogou a alínea dos 12% em 30/12/2022. Se alguém tomasse
    a revogação ao pé da letra, o diesel cairia na interna geral de 17% entre
    30/12/2022 e 1º/04/2023 — e o crédito daqueles meses sairia 42% maior.

    Mas o art. 179-I, § único, diz que essa revogação **não produz efeitos**,
    invocando o art. 32-A, § 1º, III, da LC 87/96. Os 12% valeram sem
    interrupção até o monofásico.
    """

    @pytest.mark.parametrize("competencia", ["2022-12", "2023-01", "2023-02",
                                             "2023-03", "2023-04"])
    def test_o_diesel_segue_a_12_por_cento_na_janela_da_revogacao(self, competencia):
        assert interna("ES", DIESEL, competencia) == Decimal(12)


class TestAViradaDasDuasEras:
    """Onde esta tabela acaba e `tab_ad_rem` começa — por produto, não por data."""

    def test_o_diesel_vira_em_maio_de_2023(self):
        assert interna("ES", DIESEL, "2023-04") == Decimal(12)

        with pytest.raises(ForaDoRegimePercentual):
            interna("ES", DIESEL, "2023-05")

    def test_a_gasolina_vira_um_mes_depois(self):
        """Ela entrou no monofásico em 1º/06/2023, o diesel em 1º/05/2023.

        Quem usa uma data só para os dois erra maio de 2023 inteiro na gasolina.
        """
        assert interna("ES", GASOLINA, "2023-05") == Decimal(27)

        with pytest.raises(ForaDoRegimePercentual):
            interna("ES", GASOLINA, "2023-06")

    def test_a_recusa_manda_a_pessoa_para_a_tabela_certa(self):
        with pytest.raises(ForaDoRegimePercentual) as erro:
            interna("ES", DIESEL, "2024-06")

        assert "tab_ad_rem" in str(erro.value)
        assert "ad rem" in str(erro.value)

    def test_a_virada_vale_mesmo_para_uf_que_nao_esta_conferida(self):
        """Porque ela é nacional: não depende de ninguém ler a lei do estado.

        E é a resposta mais útil — dizer "não sei a alíquota de MG" quando a
        pergunta nem tem alíquota manda a pessoa procurar o que não existe.
        """
        with pytest.raises(ForaDoRegimePercentual):
            interna("MG", DIESEL, "2024-06")

    def test_o_etanol_hidratado_nao_virou_e_segue_percentual(self):
        """O art. 3º-B pôs no monofásico o etanol **anidro** (EAC) e só ele."""
        assert no_monofasico(ETANOL_HIDRATADO, "2026-01") is False
        assert interna("ES", ETANOL_HIDRATADO, "2026-01") == Decimal(27)

    def test_o_lubrificante_tambem_nao(self):
        assert no_monofasico(LUBRIFICANTE, "2026-01") is False

    @pytest.mark.parametrize("produto, competencia, esperado", [
        (DIESEL, "2023-04", False),
        (DIESEL, "2023-05", True),
        (GLP, "2023-05", True),
        (GASOLINA, "2023-05", False),
        (GASOLINA, "2023-06", True),
    ])
    def test_no_monofasico_responde_antes_de_pedir_numero(
            self, produto, competencia, esperado):
        assert no_monofasico(produto, competencia) is esperado


class TestOQueElaRecusa:
    def test_o_glp_do_es_nao_esta_conferido(self):
        """O par que mais importa, e o que falta é específico: o anexo do RICMS."""
        with pytest.raises(AliquotaDeCombustivelDesconhecida) as erro:
            interna("ES", GLP, "2022-06")

        assert "17" in str(erro.value), "diz qual é o palpite"
        assert "Anexo" in str(erro.value), "diz onde ler para resolver"
        assert "12%" in str(erro.value), "diz qual é a outra possibilidade"

    def test_uf_sem_lei_lida(self):
        with pytest.raises(AliquotaDeCombustivelDesconhecida) as erro:
            interna("MG", DIESEL, "2022-06")

        assert "INTERNA" in str(erro.value), "diz onde acrescentar"

    def test_competencia_anterior_a_vigencia_mais_antiga(self):
        with pytest.raises(AliquotaDeCombustivelDesconhecida) as erro:
            interna("ES", GASOLINA, "2005-12")

        assert "2006-01" in str(erro.value)

    def test_o_marco_de_2006_do_hidratado_e_mes_partido_e_por_isso_recusa(self):
        """A alínea do álcool valeu de 29/03/2006 — março é meio e meio."""
        with pytest.raises(MesPartido):
            interna("ES", ETANOL_HIDRATADO, "2006-03")

        assert interna("ES", ETANOL_HIDRATADO, "2006-04") == Decimal(27)


class TestSaoPauloOndeEstaOVolume:
    """Os quatro clientes com CST 61 são de SP, então é aqui que o número sai.

    E SP é mais difícil que o ES por uma razão só: o complemento de alíquota da
    Lei 17.293/2020, que levou o diesel de 12% a 13,3% por dois anos e começou
    e terminou **no dia 15**.
    """

    @pytest.mark.parametrize("competencia, esperado", [
        ("2020-10", "12"),      # antes do complemento
        ("2020-12", "12"),
        ("2021-02", "13.3"),    # complemento em vigor
        ("2022-06", "13.3"),
        ("2022-12", "13.3"),
        ("2023-02", "12"),      # complemento revogado
        ("2023-04", "12"),
    ])
    def test_o_diesel_e_12_fora_da_janela_do_complemento_e_13_3_dentro(
            self, competencia, esperado):
        assert interna("SP", DIESEL, competencia) == Decimal(esperado)

    def test_a_gasolina_nao_levou_complemento_nenhum(self):
        """O complemento é dos arts. 53-A (7%) e 54 (12%); o art. 55 não tem
        parágrafo equivalente. A gasolina ficou 25% a era inteira."""
        for competencia in ("2020-10", "2021-06", "2022-12", "2023-05"):
            assert interna("SP", GASOLINA, competencia) == Decimal(25)

    def test_ignorar_o_complemento_perde_11_por_cento_do_credito_do_diesel(self):
        """Dois anos de compras a 12% quando a lei dava 13,3%."""
        com, sem = interna("SP", DIESEL, "2022-06"), Decimal(12)

        a_menos = (com - sem) / com * 100
        assert Decimal(9) < a_menos < Decimal(11)

    def test_sp_e_es_divergem_no_diesel_e_na_gasolina(self):
        """Prova que o eixo UF importa: mesma era, mesmos produtos, outro número."""
        assert interna("SP", DIESEL, "2022-06") != interna("ES", DIESEL, "2022-06")
        assert interna("SP", GASOLINA, "2022-06") != interna("ES", GASOLINA, "2022-06")

    def test_o_etanol_hidratado_de_sp_nao_esta_conferido(self):
        """Ele divide o inciso VI com o diesel, mas tem dois Informativos SFP só
        para ele — indício de regime próprio que ninguém leu ainda."""
        with pytest.raises(AliquotaDeCombustivelDesconhecida) as erro:
            interna("SP", ETANOL_HIDRATADO, "2022-10")

        assert "SFP" in str(erro.value)


class TestOMesPartido:
    """A recusa que nasceu de São Paulo, e que é erro próprio por uma razão.

    Aqui não falta ler lei nenhuma e a era está certa: o mês simplesmente tem
    **duas** alíquotas. A saída não é conferir nada, é separar as entradas pela
    data do documento — e por isso não pode cair no mesmo `except` de
    "não conferido".
    """

    @pytest.mark.parametrize("competencia", ["2021-01", "2023-01"])
    def test_os_dois_meses_de_virada_do_complemento_recusam(self, competencia):
        with pytest.raises(MesPartido):
            interna("SP", DIESEL, competencia)

    def test_a_mensagem_diz_as_duas_aliquotas_e_o_dia(self):
        """Mensagem que não dá os dois lados não serve para separar nada."""
        with pytest.raises(MesPartido) as erro:
            interna("SP", DIESEL, "2021-01")

        texto = str(erro.value)
        assert "15" in texto, "o dia da virada"
        assert "12" in texto and "13.3" in texto, "as duas alíquotas"
        assert "data do documento" in texto, "o que fazer"

    def test_nao_e_a_mesma_familia_de_nao_conferido(self):
        """Se fosse, um `except AliquotaDeCombustivelDesconhecida` no motor
        engoliria o mês partido e completaria com qualquer coisa."""
        assert not issubclass(MesPartido, AliquotaDeCombustivelDesconhecida)
        assert not issubclass(MesPartido, ForaDoRegimePercentual)

    def test_os_meses_vizinhos_respondem_normalmente(self):
        """A recusa é do mês da virada, não da vizinhança dela."""
        assert interna("SP", DIESEL, "2020-12") == Decimal(12)
        assert interna("SP", DIESEL, "2021-02") == Decimal("13.3")
        assert interna("SP", DIESEL, "2022-12") == Decimal("13.3")
        assert interna("SP", DIESEL, "2023-02") == Decimal(12)

    def test_toda_vigencia_com_dia_diferente_de_um_recusa_o_proprio_mes(self):
        """A regra vale para a tabela inteira, não só para os casos conhecidos."""
        for uf, por_produto in tab.INTERNA.items():
            for produto, vigencias in por_produto.items():
                for v in vigencias:
                    if v.dia == 1:
                        continue
                    with pytest.raises(MesPartido):
                        interna(uf, produto, v.desde)


class TestOsTrintaPorCentoQueNuncaValeram:
    """O engano que esta tabela existe para não repetir.

    A Lei 8.098/2005 incluiu o inciso VI com 30% para a gasolina do ES, e a Lei
    8.237/2005 deu nova redação ao mesmo inciso antes de ele entrar em vigor,
    fixando 27%. O consolidado marca a primeira versão como "sem efeitos" — e
    uma busca na internet devolve os 30% sem essa ressalva.
    """

    def test_os_30_estao_registrados_como_refutados(self):
        valor, motivo = tab.REFUTADO[("ES", GASOLINA)]

        assert valor == Decimal(30)
        assert "sem efeitos" in motivo, "o motivo tem de dizer por que não vale"

    def test_e_nao_estao_em_nenhuma_vigencia(self):
        """A guarda contra alguém promover o valor refutado um dia."""
        for uf, por_produto in tab.INTERNA.items():
            for produto, vigencias in por_produto.items():
                for v in vigencias:
                    refutado = tab.REFUTADO.get((uf, produto))
                    if refutado is not None:
                        assert v.aliquota != refutado[0], f"{uf} {produto}"

    def test_pedir_os_30_devolve_os_27(self):
        assert interna("ES", GASOLINA, "2022-06") == Decimal(27)


class TestAFormaDaTabela:
    def test_as_vigencias_vem_da_mais_nova_para_a_mais_antiga(self):
        """É a ordem em que `interna` procura: a primeira que couber vence."""
        for uf, por_produto in tab.INTERNA.items():
            for produto, vigencias in por_produto.items():
                datas = [v.desde for v in vigencias]
                assert datas == sorted(datas, reverse=True), f"{uf} {produto}"

    def test_toda_vigencia_cita_o_ato_legal_e_o_artigo(self):
        """Número sem fundamento não se confere depois, e vira folclore."""
        for uf, por_produto in tab.INTERNA.items():
            for produto, vigencias in por_produto.items():
                for v in vigencias:
                    onde = f"{uf} {produto} {v.desde}"
                    assert any(ato in v.fundamento
                               for ato in ("Lei", "Decreto", "RICMS")), onde
                    assert "art." in v.fundamento, onde

    def test_todo_valor_refutado_diz_por_que_nao_vale(self):
        """Refutado sem motivo é só uma opinião, e alguém a reabre."""
        for (uf, produto), (valor, motivo) in tab.REFUTADO.items():
            assert valor > 0, f"{uf} {produto}"
            assert len(motivo) > 60, f"{uf} {produto}"

    def test_os_dois_enganos_conhecidos_erram_para_cima(self):
        """Fonte secundária infla — nos dois estados, na gasolina, por somas que
        a lei não manda fazer. Vale registrar como propriedade, não anedota."""
        for (uf, produto), (errado, _) in tab.REFUTADO.items():
            conferida = tab.INTERNA.get(uf, {}).get(produto)
            if not conferida:
                continue
            assert errado > conferida[0].aliquota, f"{uf} {produto}"

    def test_o_que_esta_a_conferir_nao_esta_conferido(self):
        """Seria conferido e suspeito ao mesmo tempo, e alguém usaria a errada."""
        for (uf, produto) in tab.A_CONFERIR:
            assert produto not in tab.INTERNA.get(uf, {}), f"{uf} {produto}"

    def test_todo_palpite_diz_o_que_falta_ler(self):
        """Palpite sem caminho de saída fica palpite para sempre."""
        for (uf, produto), (_, motivo) in tab.A_CONFERIR.items():
            assert len(motivo) > 40, f"{uf} {produto}"

    def test_as_datas_do_monofasico_sao_as_do_art_3b(self):
        assert tab.MONOFASICO_DESDE == {
            DIESEL: "2023-05", GLP: "2023-05", GASOLINA: "2023-06"}
