"""A 047 na tela: recortar primeiro, olhar depois.

O que se cobra aqui é o que a tela depende e o olho não confere: que o recorte
combine os filtros, que a contagem de cada chip **ignore o próprio filtro** — é
o que impede o filtro de virar armadilha de mão única — e que os totais sejam
do recorte inteiro, e não da página que está à vista.
"""

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico import consulta_de_saidas as tela
from cat.infraestrutura.analitico.escrita import Escritor
from cat.infraestrutura.analitico.piscofins import ARQUIVO_DAS_SAIDAS
from cat.infraestrutura.sped.saidas import RAMO_C170, RAMO_C175, colunas_da_saida

MATRIZ = "11222333000181"
FILIAL = "11222333000262"


def linha(**campos: str) -> dict[str, str]:
    """Uma linha da 047 com tudo em branco menos o que o teste diz."""
    return {nome: campos.get(nome, "") for nome in colunas_da_saida()}


# duas competências, dois estabelecimentos, dois ramos, três CFOP e dois CST.
# Pequena o bastante para conferir na mão, grande o bastante para o cruzamento
# dos filtros significar alguma coisa
AMOSTRA = [
    linha(cnpj=MATRIZ, periodo="01/06/2021", registros=RAMO_C170, numero_do_documento="1",
          numero_do_item="1", codigo_do_item="SKU1", descricao_do_item="XAMPU 350ML",
          cfop="5102", natureza="Venda", faturamento="Faturamento", valor_do_item="100,00",
          cst_pis="01", pis="1,65", cofins="7,60", descricao_do_cfop="Venda de mercadoria"),
    linha(cnpj=MATRIZ, periodo="01/06/2021", registros=RAMO_C170, numero_do_documento="1",
          numero_do_item="2", codigo_do_item="SKU2", descricao_do_item="ARROZ 5KG",
          cfop="5405", natureza="Venda", faturamento="Faturamento", valor_do_item="50,00",
          cst_pis="04", pis="0,00", cofins="0,00"),
    linha(cnpj=MATRIZ, periodo="01/07/2021", registros=RAMO_C175, numero_do_documento="7001",
          cfop="5102", natureza="Venda", faturamento="Faturamento", valor_do_item="10,00",
          cst_pis="01", pis="0,17", cofins="0,76"),
    linha(cnpj=FILIAL, periodo="01/06/2021", registros=RAMO_C170, numero_do_documento="2",
          numero_do_item="1", codigo_do_item="SKU1", descricao_do_item="COXAO MOLE KG",
          nome_do_participante="CLIENTE MINEIRO",
          cfop="5949", natureza="Outras saídas/prestações", valor_do_item="30,00",
          cst_pis="01", pis="0,50", cofins="2,28"),
    linha(cnpj=FILIAL, periodo="01/07/2021", registros=RAMO_C170, numero_do_documento="3",
          numero_do_item="1", codigo_do_item="SKU2", descricao_do_item="ARROZ 5KG",
          cfop="5405", natureza="Venda", faturamento="Faturamento", valor_do_item="20,00",
          cst_pis="04", pis="0,00", cofins="0,00"),
]


@pytest.fixture
def pasta(tmp_path):
    escritor = Escritor(str(tmp_path / ARQUIVO_DAS_SAIDAS), colunas_da_saida())
    for l in AMOSTRA:
        escritor.escrever(l)
    escritor.fechar()
    return str(tmp_path)


def valores(escolhas: list[dict]) -> dict[str, int]:
    return {e["valor"]: e["linhas"] for e in escolhas}


class TestOQueHaParaEscolher:
    def test_cada_filtro_lista_o_que_existe_com_o_tamanho(self, pasta):
        f = tela.filtros(pasta)

        assert valores(f["cnpjs"]) == {MATRIZ: 3, FILIAL: 2}
        assert valores(f["competencias"]) == {"01/06/2021": 3, "01/07/2021": 2}
        assert valores(f["cfops"]) == {"5102": 2, "5405": 2, "5949": 1}
        assert valores(f["cst_pis"]) == {"01": 3, "04": 2}
        assert f["linhas_no_total"] == f["linhas_no_recorte"] == 5

    def test_a_descricao_do_cfop_vem_junto_para_a_tela_explicar_o_codigo(self, pasta):
        f = tela.filtros(pasta)
        cinco_um_zero_dois = next(e for e in f["cfops"] if e["valor"] == "5102")
        assert cinco_um_zero_dois["rotulo"] == "Venda de mercadoria"

    def test_o_filtro_nao_encolhe_a_propria_lista(self, pasta):
        """Marcar o 5102 não pode sumir com o 5405 da lista de CFOP.

        Se sumisse, o filtro seria de mão única: quem marcou um CFOP nunca mais
        acharia outro para marcar junto. As **outras** listas, sim, encolhem —
        é o que mostra o que aquele CFOP tem dentro.
        """
        f = tela.filtros(pasta, tela.Recorte(cfops=("5102",)))

        assert valores(f["cfops"]) == {"5102": 2, "5405": 2, "5949": 1}
        assert valores(f["cst_pis"]) == {"01": 2}
        assert valores(f["competencias"]) == {"01/06/2021": 1, "01/07/2021": 1}
        assert f["linhas_no_recorte"] == 2

    def test_os_totais_sao_do_recorte(self, pasta):
        f = tela.filtros(pasta, tela.Recorte(cnpjs=(FILIAL,)))
        assert f["totais"] == {"valor": "50.00", "pis": "0.50", "cofins": "2.28"}


class TestOsFiltrosSeCombinam:
    def test_dois_filtros_sao_e_e_nao_ou(self, pasta):
        recorte = tela.Recorte(competencias=("01/06/2021",), cnpjs=(MATRIZ,))
        assert tela.linhas(pasta, recorte)["total"] == 2

    def test_varios_valores_do_mesmo_filtro_sao_ou(self, pasta):
        recorte = tela.Recorte(cfops=("5102", "5949"))
        assert tela.linhas(pasta, recorte)["total"] == 3

    def test_recorte_sem_resultado_volta_vazio_e_nao_quebra(self, pasta):
        recorte = tela.Recorte(cfops=("5102",), cst_pis=("04",))
        pagina = tela.linhas(pasta, recorte)
        assert pagina["total"] == 0
        assert pagina["linhas"] == []
        assert pagina["totais"] == {"valor": "0.00", "pis": "0.00", "cofins": "0.00"}


class TestABuscaLivre:
    def test_procura_no_produto_e_no_participante(self, pasta):
        assert tela.linhas(pasta, tela.Recorte(busca="arroz"))["total"] == 2
        assert tela.linhas(pasta, tela.Recorte(busca="mineiro"))["total"] == 1

    def test_nao_distingue_maiuscula(self, pasta):
        assert tela.linhas(pasta, tela.Recorte(busca="XAMPU"))["total"] == 1
        assert tela.linhas(pasta, tela.Recorte(busca="xampu"))["total"] == 1

    def test_a_tela_e_avisada_de_que_a_contagem_do_chip_ignora_a_busca(self, pasta):
        """Os chips contam pelo resumo, que não conhece a busca.

        Dizer isso é o que evita a pessoa somar os chips e achar que o total
        está errado.
        """
        assert tela.filtros(pasta)["busca_conta_no_resumo"] is True
        assert tela.filtros(pasta, tela.Recorte(busca="arroz"))["busca_conta_no_resumo"] is False


class TestAPagina:
    def test_os_totais_sao_do_recorte_inteiro_e_nao_da_pagina(self, pasta):
        """Total que muda ao virar a página não serve para conferir nada."""
        primeira = tela.linhas(pasta, por_pagina=2, pagina=1)
        segunda = tela.linhas(pasta, por_pagina=2, pagina=2)

        assert len(primeira["linhas"]) == len(segunda["linhas"]) == 2
        assert primeira["total"] == segunda["total"] == 5
        assert primeira["totais"] == segunda["totais"]
        assert primeira["totais"]["valor"] == "210.00"

    def test_a_ordem_e_a_da_escrituracao(self, pasta):
        pagina = tela.linhas(pasta)
        assert [l["periodo"] for l in pagina["linhas"]] == [
            "01/06/2021", "01/06/2021", "01/06/2021", "01/07/2021", "01/07/2021"]

    def test_pagina_alem_do_fim_volta_vazia_com_o_total_certo(self, pasta):
        pagina = tela.linhas(pasta, pagina=99)
        assert pagina["linhas"] == []
        assert pagina["total"] == 5

    def test_por_pagina_tem_teto(self, pasta):
        assert tela.linhas(pasta, por_pagina=99999)["por_pagina"] == tela.POR_PAGINA_MAXIMO

    def test_a_pagina_diz_se_houve_recorte(self, pasta):
        assert tela.linhas(pasta)["recortado"] is False
        assert tela.linhas(pasta, tela.Recorte(cfops=("5102",)))["recortado"] is True


class TestOParquetDoRecorte:
    def test_sem_recorte_e_o_proprio_arquivo(self, pasta):
        caminho = tela.parquet_do_recorte(pasta, tela.RECORTE_INTEIRO)
        assert caminho.endswith(ARQUIVO_DAS_SAIDAS)

    def test_com_recorte_sai_um_arquivo_so_com_o_que_passa(self, pasta):
        recorte = tela.Recorte(cfops=("5405",))
        caminho = tela.parquet_do_recorte(pasta, recorte)

        assert not caminho.endswith(ARQUIVO_DAS_SAIDAS)
        linhas = pq.read_table(caminho).to_pylist()
        assert len(linhas) == 2
        assert {l["cfop"] for l in linhas} == {"5405"}
        assert len(linhas[0]) == 53

    def test_recortes_diferentes_nao_se_confundem(self, pasta):
        """Sem isso o primeiro download ficaria em cache e o segundo filtro
        devolveria a planilha errada, com o nome certo."""
        um = tela.parquet_do_recorte(pasta, tela.Recorte(cfops=("5405",)))
        outro = tela.parquet_do_recorte(pasta, tela.Recorte(cfops=("5102",)))
        assert um != outro
        assert len(pq.read_table(outro).to_pylist()) == 2

    def test_a_marca_nao_depende_da_ordem_em_que_se_marcou(self, pasta):
        assert (tela.impressao_do_recorte(tela.Recorte(cfops=("5102", "5405")))
                == tela.impressao_do_recorte(tela.Recorte(cfops=("5405", "5102"))))


class TestQuandoNaoHa:
    def test_sem_parquet_a_mensagem_diz_o_que_fazer(self, tmp_path):
        with pytest.raises(tela.SaidasNaoGeradas) as erro:
            tela.linhas(str(tmp_path))
        assert "apuração de PIS/COFINS" in str(erro.value)
