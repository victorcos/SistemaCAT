"""O leitor do razão da ECD: escolher a conta, depois ver os lançamentos.

A amostra é um `razao.parquet` montado à mão, com duas contas numa empresa e
uma terceira noutra — o bastante para que qualquer vazamento entre contas ou
entre estabelecimentos apareça. Tudo texto, como a quebra grava.
"""

import pytest

from cat.infraestrutura.analitico.quebra_de_sped import ARQUIVO_DO_RAZAO, _Escritor
from cat.infraestrutura.analitico.razao_contabil import (
    POR_PAGINA_MAXIMO,
    RazaoNaoGerado,
    contas,
    estabelecimentos,
    lancamentos,
)

COLUNAS = [
    "cnpj", "conta", "descricao", "conta_referencial", "competencia", "data", "numero",
    "valor_do_lancamento", "centro_de_custo", "valor", "debito_ou_credito", "historico",
    "codigo_do_historico", "participante", "tipo", "saldo", "arquivo",
]

MATRIZ = "11222333000181"
FILIAL = "11222333000262"


def _linha(**campos: str) -> dict:
    """Uma partida, com o que não foi dito em branco."""
    base = dict.fromkeys(COLUNAS, "")
    base.update(campos)
    return base


# duas contas na matriz e uma na filial. A 1.1.1.01 fecha devedora; a 2.1.1.01,
# credora; a da filial tem o mesmo código da primeira, para pegar vazamento
PARTIDAS = [
    _linha(cnpj=MATRIZ, conta="1.1.1.01", descricao="CAIXA GERAL",
           conta_referencial="1.01.01.01", competencia="2024-01-01", data="2024-01-05",
           numero="1", valor="1000.00", debito_ou_credito="D", saldo="1000.00",
           historico="VENDA A VISTA", participante="F01", arquivo="ecd_2024.txt"),
    _linha(cnpj=MATRIZ, conta="1.1.1.01", descricao="CAIXA GERAL",
           conta_referencial="1.01.01.01", competencia="2024-01-01", data="2024-01-20",
           numero="2", valor="300.00", debito_ou_credito="C", saldo="700.00",
           historico="PAGAMENTO FORNECEDOR", arquivo="ecd_2024.txt"),
    _linha(cnpj=MATRIZ, conta="1.1.1.01", descricao="CAIXA GERAL",
           conta_referencial="1.01.01.01", competencia="2024-02-01", data="2024-02-10",
           numero="3", valor="150.00", debito_ou_credito="D", saldo="850.00",
           historico="VENDA A VISTA", arquivo="ecd_2024.txt"),
    _linha(cnpj=MATRIZ, conta="2.1.1.01", descricao="FORNECEDORES",
           conta_referencial="2.01.01.01", competencia="2024-01-01", data="2024-01-20",
           numero="2", valor="300.00", debito_ou_credito="C", saldo="-300.00",
           historico="COMPRA A PRAZO", arquivo="ecd_2024.txt"),
    _linha(cnpj=FILIAL, conta="1.1.1.01", descricao="CAIXA DA FILIAL",
           conta_referencial="1.01.01.01", competencia="2024-03-01", data="2024-03-15",
           numero="9", valor="80.00", debito_ou_credito="D", saldo="80.00",
           historico="SUPRIMENTO", arquivo="ecd_filial.txt"),
]


@pytest.fixture
def pasta(tmp_path):
    escritor = _Escritor(str(tmp_path / ARQUIVO_DO_RAZAO), COLUNAS)
    for partida in PARTIDAS:
        escritor.escrever(partida)
    escritor.fechar()
    return str(tmp_path)


class TestSeletorDeConta:
    def test_uma_linha_por_conta_com_movimento_e_saldo(self, pasta):
        resposta = contas(pasta)

        assert resposta["total"] == 3
        caixa = next(c for c in resposta["linhas"]
                     if c["cnpj"] == MATRIZ and c["conta"] == "1.1.1.01")
        assert caixa["descricao"] == "CAIXA GERAL"
        assert caixa["lancamentos"] == 3
        assert caixa["debitos"] == "1150.00"
        assert caixa["creditos"] == "300.00"
        assert caixa["saldo"] == "850.00"
        assert (caixa["de"], caixa["ate"]) == ("2024-01-05", "2024-02-10")

    def test_a_mesma_conta_em_dois_cnpj_nao_se_mistura(self, pasta):
        """Filial tem o plano de contas da matriz. Somar as duas seria erro."""
        resposta = contas(pasta, busca="1.1.1.01")

        assert [(c["cnpj"], c["saldo"]) for c in resposta["linhas"]] == [
            (MATRIZ, "850.00"), (FILIAL, "80.00")]

    def test_a_ordem_e_a_do_plano_de_contas(self, pasta):
        """Não a do maior movimento: é assim que o contador procura."""
        linhas = contas(pasta, cnpj=MATRIZ)["linhas"]
        assert [c["conta"] for c in linhas] == ["1.1.1.01", "2.1.1.01"]

    def test_a_busca_pega_codigo_nome_e_conta_referencial(self, pasta):
        assert contas(pasta, busca="FORNECEDORES")["total"] == 1
        assert contas(pasta, busca="2.01.01")["total"] == 1
        assert contas(pasta, busca="2.1.1")["total"] == 1
        assert contas(pasta, busca="não existe")["total"] == 0

    def test_o_filtro_por_estabelecimento(self, pasta):
        assert contas(pasta, cnpj=FILIAL)["total"] == 1
        assert contas(pasta, cnpj=MATRIZ)["total"] == 2

    def test_o_recorte_por_saldo(self, pasta):
        devedoras = contas(pasta, so="devedoras")["linhas"]
        credoras = contas(pasta, so="credoras")["linhas"]

        assert {c["conta"] for c in devedoras} == {"1.1.1.01"}
        assert [c["conta"] for c in credoras] == ["2.1.1.01"]

    def test_recorte_desconhecido_diz_quais_existem(self, pasta):
        with pytest.raises(ValueError, match="devedoras"):
            contas(pasta, so="inventado")

    def test_a_pagina_recorta_sem_mudar_o_total(self, pasta):
        primeira = contas(pasta, pagina=1, por_pagina=2)
        segunda = contas(pasta, pagina=2, por_pagina=2)

        assert primeira["total"] == segunda["total"] == 3
        assert len(primeira["linhas"]) == 2
        assert len(segunda["linhas"]) == 1

    def test_pagina_gigante_e_limitada(self, pasta):
        assert contas(pasta, por_pagina=100_000)["por_pagina"] == POR_PAGINA_MAXIMO


class TestLancamentosDaConta:
    def test_so_os_lancamentos_da_conta_escolhida(self, pasta):
        resposta = lancamentos(pasta, MATRIZ, "1.1.1.01")

        assert resposta["total"] == 3
        assert {l["conta"] for l in resposta["linhas"]} == {"1.1.1.01"}
        assert {l["cnpj"] for l in resposta["linhas"]} == {MATRIZ}
        assert resposta["descricao"] == "CAIXA GERAL"
        assert resposta["conta_referencial"] == "1.01.01.01"

    def test_a_ordem_e_a_que_gerou_o_saldo(self, pasta):
        """Data e depois número. Outra ordem faria a coluna de saldo mentir."""
        linhas = lancamentos(pasta, MATRIZ, "1.1.1.01")["linhas"]

        assert [l["data"] for l in linhas] == ["2024-01-05", "2024-01-20", "2024-02-10"]
        assert [l["saldo"] for l in linhas] == ["1000.00", "700.00", "850.00"]

    def test_os_totais_sao_da_conta_inteira_nao_da_pagina(self, pasta):
        """Total que muda ao virar a página não serve para conferir nada."""
        primeira = lancamentos(pasta, MATRIZ, "1.1.1.01", pagina=1, por_pagina=1)

        assert len(primeira["linhas"]) == 1
        assert primeira["totais"] == {"debitos": "1150.00", "creditos": "300.00",
                                      "saldo": "850.00"}

    def test_o_recorte_de_data_muda_os_totais_e_diz_que_mudou(self, pasta):
        janeiro = lancamentos(pasta, MATRIZ, "1.1.1.01", de="2024-01-01", ate="2024-01-31")

        assert janeiro["total"] == 2
        assert janeiro["recortado"] is True
        assert janeiro["totais"]["saldo"] == "700.00"
        assert lancamentos(pasta, MATRIZ, "1.1.1.01")["recortado"] is False

    def test_a_busca_olha_historico_numero_e_participante(self, pasta):
        assert lancamentos(pasta, MATRIZ, "1.1.1.01", busca="VENDA")["total"] == 2
        assert lancamentos(pasta, MATRIZ, "1.1.1.01", busca="F01")["total"] == 1
        assert lancamentos(pasta, MATRIZ, "1.1.1.01", busca="3")["total"] == 1

    def test_conta_sem_lancamento_devolve_vazio_e_zero(self, pasta):
        resposta = lancamentos(pasta, MATRIZ, "9.9.9.99")

        assert resposta["total"] == 0
        assert resposta["linhas"] == []
        assert resposta["totais"] == {"debitos": "0.00", "creditos": "0.00", "saldo": "0.00"}
        assert resposta["descricao"] == ""


class TestEstabelecimentos:
    def test_os_cnpj_com_quantas_contas_cada_um(self, pasta):
        assert estabelecimentos(pasta) == [
            {"cnpj": MATRIZ, "contas": 2, "lancamentos": 4,
             "de": "2024-01-05", "ate": "2024-02-10"},
            {"cnpj": FILIAL, "contas": 1, "lancamentos": 1,
             "de": "2024-03-15", "ate": "2024-03-15"},
        ]


class TestSemArquivo:
    def test_execucao_sem_razao_diz_o_que_fazer(self, tmp_path):
        with pytest.raises(RazaoNaoGerado, match="Rode a quebra de SPED"):
            contas(str(tmp_path))
        with pytest.raises(RazaoNaoGerado):
            lancamentos(str(tmp_path), MATRIZ, "1.1.1.01")
        with pytest.raises(RazaoNaoGerado):
            estabelecimentos(str(tmp_path))
