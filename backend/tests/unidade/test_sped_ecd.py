"""A quebra da ECD e o razão contábil.

A amostra tem duas contas analíticas, lançamentos **fora de ordem de data** — o
SPED não obriga ordem — e uma partida órfã. São os três casos que separam um
razão correto de uma lista de partidas.
"""

from datetime import date
from decimal import Decimal

import pytest

from cat.infraestrutura.sped.ecd import (
    EcdInvalida,
    indexar_ecd,
    razao,
)

# 3.1.1 — Caixa · 4.1.1 — Receita de vendas
# repare: o lançamento 2 é de 05/06 e vem DEPOIS do lançamento 3, de 20/06
ECD = """|0000|LECD|01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|111222333|3550308|||0|0|N||
|I050|01012021|01|S|2|3|
|COMERCIO DO TESTE|
|I050|01012021|01|A|3|3.1.1|3|CAIXA|
|I051||1.01.01.01|
|I050|01012021|04|A|3|4.1.1|4|RECEITA DE VENDAS|
|I051||3.01.01.01|
|I200|1|10062021|1000,00|N||
|I250|3.1.1||1000,00|D|1|001|RECEBIMENTO DE VENDA|C09||
|I250|4.1.1||1000,00|C|1|001|RECEBIMENTO DE VENDA|C09||
|I200|3|20062021|500,00|N||
|I250|3.1.1||500,00|D|1|002|VENDA A VISTA|C09||
|I250|4.1.1||500,00|C|1|002|VENDA A VISTA|C09||
|I200|2|05062021|300,00|N||
|I250|3.1.1||300,00|D|1|003|SALDO INICIAL|||
|9999|16|
"""


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "ecd.txt"
    caminho.write_bytes(ECD.encode("cp1252"))
    return str(caminho)


class TestOIndice:
    def test_le_o_plano_de_contas_e_separa_as_analiticas(self, arquivo):
        indice = indexar_ecd(arquivo)

        assert len(indice.contas) == 3
        assert [c.codigo for c in indice.analiticas] == ["3.1.1", "4.1.1"]
        assert indice.conta("3.1.1").nome == "CAIXA"
        # a sintética existe no plano mas não recebe partida
        assert not indice.conta("3").analitica

    def test_liga_a_conta_referencial(self, arquivo):
        indice = indexar_ecd(arquivo)
        assert indice.referencial["3.1.1"] == "1.01.01.01"
        assert indice.referencial["4.1.1"] == "3.01.01.01"

    def test_conta_lancamentos_e_partidas_por_conta(self, arquivo):
        indice = indexar_ecd(arquivo)

        assert indice.lancamentos == 3
        assert indice.partidas == 5
        assert indice.partidas_de("3.1.1") == 3
        assert indice.partidas_de("4.1.1") == 2

    def test_le_a_empresa_e_o_periodo_do_0000(self, arquivo):
        indice = indexar_ecd(arquivo)
        assert indice.cnpj == "11222333000181"
        assert indice.nome == "COMERCIO DO TESTE LTDA"
        assert (indice.inicio, indice.fim) == ("2021-06-01", "2021-06-30")


class TestORazao:
    def test_a_partida_sai_com_o_lancamento_que_a_contem(self, arquivo):
        indice = indexar_ecd(arquivo)

        linhas = list(razao(arquivo, indice, ["4.1.1"]))

        assert len(linhas) == 2
        assert linhas[0].numero == "1"
        assert linhas[0].valor_do_lancamento == Decimal("1000.00")
        assert linhas[0].historico == "RECEBIMENTO DE VENDA"
        assert linhas[0].descricao == "RECEITA DE VENDAS"
        assert linhas[0].conta_referencial == "3.01.01.01"

    def test_a_ordem_e_a_do_tempo_e_nao_a_do_arquivo(self, arquivo):
        """O SPED não obriga os lançamentos a virem em ordem de data."""
        indice = indexar_ecd(arquivo)

        linhas = list(razao(arquivo, indice, ["3.1.1"]))

        assert [l.data for l in linhas] == ["2021-06-05", "2021-06-10", "2021-06-20"]
        assert [l.numero for l in linhas] == ["2", "1", "3"]

    def test_o_saldo_corre_debito_somando_e_credito_subtraindo(self, arquivo):
        indice = indexar_ecd(arquivo)

        caixa = list(razao(arquivo, indice, ["3.1.1"]))
        receita = list(razao(arquivo, indice, ["4.1.1"]))

        assert [l.saldo for l in caixa] == [Decimal("300"), Decimal("1300"), Decimal("1800")]
        # receita é conta de crédito: o saldo vai para baixo de zero
        assert [l.saldo for l in receita] == [Decimal("-1000"), Decimal("-1500")]

    def test_o_saldo_e_decimal_e_nao_float(self, arquivo):
        """Float acumulado em milhões de partidas inventa centavo."""
        indice = indexar_ecd(arquivo)
        primeira = next(iter(razao(arquivo, indice, ["3.1.1"])))
        assert isinstance(primeira.saldo, Decimal)
        assert isinstance(primeira.valor, Decimal)

    def test_sem_contas_pedidas_sai_o_razao_de_todas_as_analiticas(self, arquivo):
        indice = indexar_ecd(arquivo)
        contas = {l.conta for l in razao(arquivo, indice)}
        assert contas == {"3.1.1", "4.1.1"}

    def test_a_competencia_e_o_primeiro_dia_do_mes(self, arquivo):
        indice = indexar_ecd(arquivo)
        assert next(iter(razao(arquivo, indice, ["3.1.1"]))).competencia == "2021-06-01"


class TestORecorteDePeriodo:
    def test_a_partida_anterior_ao_recorte_nao_vira_linha_mas_entra_no_saldo(self, arquivo):
        """Sem isso o razão do mês começaria do zero e o saldo seria ficção."""
        indice = indexar_ecd(arquivo)

        linhas = list(razao(arquivo, indice, ["3.1.1"], de=date(2021, 6, 10)))

        assert [l.data for l in linhas] == ["2021-06-10", "2021-06-20"]
        # a de 05/06 (300 a débito) não aparece, mas o saldo começa nela
        assert linhas[0].saldo == Decimal("1300")

    def test_o_recorte_final_corta_sem_mexer_no_saldo_de_abertura(self, arquivo):
        indice = indexar_ecd(arquivo)

        linhas = list(razao(arquivo, indice, ["3.1.1"], ate=date(2021, 6, 10)))

        assert [l.data for l in linhas] == ["2021-06-05", "2021-06-10"]
        assert linhas[-1].saldo == Decimal("1300")

    def test_recorte_que_nao_pega_nada_devolve_lista_vazia(self, arquivo):
        indice = indexar_ecd(arquivo)
        assert list(razao(arquivo, indice, ["3.1.1"], de=date(2022, 1, 1))) == []


class TestOQueONaoServe:
    def test_partida_orfa_fica_de_fora_em_vez_de_sujar_o_razao(self, tmp_path):
        """Partida antes de qualquer lançamento: arquivo truncado produz isso."""
        orfa = tmp_path / "orfa.txt"
        orfa.write_bytes(
            ("|I050|01012021|01|A|3|3.1.1|3|CAIXA|" + chr(10)
             + "|I250|3.1.1||100,00|D|1|001|SEM PAI|||" + chr(10)
             + "|I200|1|10062021|100,00|N||" + chr(10)
             + "|I250|3.1.1||100,00|D|1|002|COM PAI|||").encode("cp1252"))
        indice = indexar_ecd(str(orfa))

        linhas = list(razao(str(orfa), indice, ["3.1.1"]))

        assert [l.historico for l in linhas] == ["COM PAI"]

    def test_arquivo_sem_plano_de_contas_e_recusado_dizendo_qual_falta(self, tmp_path):
        sem = tmp_path / "sem_plano.txt"
        sem.write_bytes("|I200|1|10062021|100,00|N||".encode("cp1252"))
        with pytest.raises(EcdInvalida, match="I050"):
            indexar_ecd(str(sem))

    def test_arquivo_sem_lancamento_e_recusado(self, tmp_path):
        sem = tmp_path / "sem_lcto.txt"
        sem.write_bytes("|I050|01012021|01|A|3|3.1.1|3|CAIXA|".encode("cp1252"))
        with pytest.raises(EcdInvalida, match="I200"):
            indexar_ecd(str(sem))

    def test_arquivo_com_lancamento_e_sem_partida_e_recusado(self, tmp_path):
        sem = tmp_path / "sem_partida.txt"
        sem.write_bytes(
            ("|I050|01012021|01|A|3|3.1.1|3|CAIXA|" + chr(10)
             + "|I200|1|10062021|100,00|N||").encode("cp1252"))
        with pytest.raises(EcdInvalida, match="I250"):
            indexar_ecd(str(sem))

    def test_conta_sem_partida_nao_devolve_linha_nem_quebra(self, arquivo):
        indice = indexar_ecd(arquivo)
        assert list(razao(arquivo, indice, ["9.9.9"])) == []
