"""A etapa das exclusões rodando inteira — o caminho que a tela dispara.

Havia 60 testes de exclusão e nenhum chamava `exclusoes.apurar`. Cada tese era
conferida sozinha, e os motores batiam 100% contra os gabaritos do MA; o que
ninguém exercitava era a **costura** — a função que roda as quatro teses, junta
os resumos e grava o parquet agregado.

Foi exatamente ali que o defeito apareceu, em 01/10/2026: `exclusao_do_icms_st`
e `exclusao_do_iss` não reexportavam `serializar`, e a apuração morria com
`AttributeError` no meio da rodada do cliente. O teste de superfície
(`test_analitico_superficie_das_exclusoes.py`) fecha aquela porta; este fecha a
sala: se a costura quebrar por qualquer outro motivo — um argumento com nome
errado, um resumo que não serializa, o agregado sem uma tese —, falha aqui.

**Vale a leitura de disco que custa.** São dois SPED minúsculos, e o que se
ganha é a única prova de que a etapa roda de ponta a ponta sem um cliente na
frente.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from datetime import date

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico import (
    exclusao_do_icms,
    exclusao_do_icms_st,
    exclusao_do_iss,
    exclusao_piscofins_na_base,
    exclusoes,
)
from cat.infraestrutura.planilhas.pacote_das_exclusoes import (
    LEIA_ME,
    PACOTE,
    zip_das_exclusoes,
)
from cat.infraestrutura.repositorios.banco import criar_tabelas
from cat.infraestrutura.sped.registros import CAMPOS

CNPJ = "11222333000181"
REFERENCIA = date(2026, 9, 30)
ATE = "2026-09"


@pytest.fixture(scope="module", autouse=True)
def banco():
    """A etapa lê a Selic e as alíquotas do banco; sem tabela não há o que ler."""
    criar_tabelas()


def reg(nome: str, **campos: str) -> str:
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


EFD = "\n".join([
    reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI="01102022", DT_FIN="31102022",
        NOME="COMERCIO DO TESTE LTDA", CNPJ=CNPJ, UF="MG", COD_MUN="3106200",
        IND_NAT_PJ="0", IND_ATIV="0"),
    reg("0140", COD_EST="001", NOME="MATRIZ", CNPJ=CNPJ, UF="MG", IE="111",
        COD_MUN="3106200"),
    reg("0150", COD_PART="C01", NOME="MERCADO DO TESTE", COD_PAIS="1058",
        CNPJ="99888777000166", COD_MUN="3106200"),
    reg("0200", COD_ITEM="SKU1", DESCR_ITEM="ARROZ 5KG", COD_BARRA="7890000000017",
        UNID_INV="PC", TIPO_ITEM="00", COD_NCM="10063021"),

    reg("C010", CNPJ=CNPJ),
    # venda tributada, com ICMS destacado: entra no 903
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="6001", CHV_NFE="31" + "6" * 42, DT_DOC="02102022",
        DT_E_S="02102022", VL_DOC="500,00", VL_MERC="500,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="500,00", CFOP="5102",
        CST_ICMS="000", VL_BC_ICMS="500,00", ALIQ_ICMS="18,00", VL_ICMS="90,00",
        CST_PIS="01", ALIQ_PIS_PERC="1,6500", VL_BC_PIS="500,00", VL_PIS="8,25",
        CST_COFINS="01", ALIQ_COFINS_PERC="7,6000", VL_BC_COFINS="500,00",
        VL_COFINS="38,00"),
    # revenda com ST já retido: entra no 839
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="7001", CHV_NFE="31" + "7" * 42, DT_DOC="03102022",
        DT_E_S="03102022", VL_DOC="1000,00", VL_MERC="1000,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="1000,00", CFOP="5405",
        CST_ICMS="060", CST_PIS="01", ALIQ_PIS_PERC="1,6500", VL_BC_PIS="1000,00",
        VL_PIS="16,50", CST_COFINS="01", ALIQ_COFINS_PERC="7,6000",
        VL_BC_COFINS="1000,00", VL_COFINS="76,00"),

    # nota de serviço com ISS: entra no 933
    reg("A010", CNPJ=CNPJ),
    reg("A100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_SIT="00", SER="A",
        NUM_DOC="55", DT_DOC="05102022", DT_EXE_SERV="05102022", VL_DOC="2000,00",
        VL_ISS="40,00"),
    reg("A170", NUM_ITEM="1", COD_ITEM="SRV1", VL_ITEM="2000,00", CST_PIS="01",
        VL_BC_PIS="2000,00", ALIQ_PIS="1,6500", VL_PIS="33,00", CST_COFINS="01",
        VL_BC_COFINS="2000,00", ALIQ_COFINS="7,6000", VL_COFINS="152,00"),
    "|9999|14|",
    "",
])


@pytest.fixture(scope="module")
def rodada(tmp_path_factory):
    """Uma rodada da etapa, inteira. Módulo inteiro usa a mesma: lê disco."""
    pasta = tmp_path_factory.mktemp("exclusoes")
    sped = pasta / "contribuicoes.txt"
    sped.write_bytes(EFD.encode("cp1252"))
    destino = str(pasta / "saida")
    resumo = exclusoes.apurar([str(sped)], destino, ate=ATE, referencia=REFERENCIA)
    return resumo, destino


class TestACostura:
    def test_a_etapa_roda_sem_estourar(self, rodada):
        """O teste que faltava: era aqui que o `AttributeError` aparecia."""
        resumo, _ = rodada

        assert resumo.receita_por_item, "o resumo da receita por item não voltou"
        assert resumo.icms, "o resumo do ICMS não voltou"
        assert resumo.icms_st, "o resumo do ICMS-ST não voltou"
        assert resumo.iss, "o resumo do ISS não voltou"

    def test_cada_resumo_tem_a_forma_que_a_tela_espera(self, rodada):
        resumo, _ = rodada
        esperado = {"tese", "ate", "linhas", "base", "excluido", "total_atualizado",
                    "prescrito", "competencias_prescritas", "por_competencia"}

        for nome in ("receita_por_item", "icms", "icms_st", "iss"):
            tese = getattr(resumo, nome)
            assert esperado <= set(tese), f"{nome}: falta {esperado - set(tese)}"
            assert tese["ate"] == ATE

    def test_as_quatro_teses_vem_nomeadas_e_distintas(self, rodada):
        resumo, _ = rodada
        nomes = {resumo.receita_por_item["tese"], resumo.icms["tese"],
                 resumo.icms_st["tese"], resumo.iss["tese"]}

        assert nomes == {
            exclusao_piscofins_na_base.TESE_PISCOFINS_POR_ITEM,
            exclusao_do_icms.TESE_ICMS_NA_BASE,
            exclusao_do_icms_st.TESE_ICMS_ST_NA_BASE,
            exclusao_do_iss.TESE_ISS_NA_BASE,
        }

    def test_as_duas_frentes_da_receita_falam_da_mesma_tese(self, rodada):
        """O consolidado e o detalhe por item: mesma base, arredondamento diferente.

        Não é para baterem ao centavo — a decisão de 24/09/2026 escolheu
        arredondar uma vez por grupo no número que se pede, e o detalhe
        reproduz o do MA linha a linha. O que **tem** de bater é a base: se as
        duas frentes partissem de receitas diferentes, uma das duas estaria
        filtrando errado, e aí nenhuma serviria para conferir a outra.
        """
        resumo, _ = rodada

        assert resumo.receita_por_item["base"] == str(exclusoes.reais(resumo.base))


class TestOQueFicaEmDisco:
    def test_os_cinco_parquets_nascem(self, rodada):
        _, destino = rodada
        for arquivo in (exclusoes.ARQUIVO_DAS_EXCLUSOES,
                        exclusao_piscofins_na_base.ARQUIVO_DA_EXCLUSAO_PISCOFINS,
                        exclusao_do_icms.ARQUIVO_DA_EXCLUSAO_DO_ICMS,
                        exclusao_do_icms_st.ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST,
                        exclusao_do_iss.ARQUIVO_DA_EXCLUSAO_DO_ISS):
            assert os.path.isfile(os.path.join(destino, arquivo)), arquivo

    def test_o_detalhe_da_receita_nao_entra_no_agregado(self, rodada):
        """Senão quem somar o parquet por tese pede a tese 1 duas vezes.

        A tese da receita já está no agregado, consolidada. O detalhe por item
        é a outra frente da **mesma** tese, e mora no seu próprio parquet.
        """
        _, destino = rodada
        tabela = pq.read_table(os.path.join(destino, exclusoes.ARQUIVO_DAS_EXCLUSOES))
        teses = set(tabela.column("tese").to_pylist())

        assert exclusoes.TESE_PISCOFINS_NA_BASE in teses
        assert exclusao_piscofins_na_base.TESE_PISCOFINS_POR_ITEM not in teses

    def test_o_agregado_separa_as_teses_por_item(self, rodada):
        """É a coluna `tese` que mantém as quatro no mesmo parquet sem se somarem."""
        _, destino = rodada
        tabela = pq.read_table(os.path.join(destino, exclusoes.ARQUIVO_DAS_EXCLUSOES))
        teses = set(tabela.column("tese").to_pylist())

        assert exclusao_do_icms.TESE_ICMS_NA_BASE in teses
        assert exclusao_do_icms_st.TESE_ICMS_ST_NA_BASE in teses
        assert exclusao_do_iss.TESE_ISS_NA_BASE in teses

    def test_o_agregado_traz_as_colunas_da_correcao(self, rodada):
        _, destino = rodada
        tabela = pq.read_table(os.path.join(destino, exclusoes.ARQUIVO_DAS_EXCLUSOES))

        assert "selic" in tabela.column_names
        assert "total_atualizado" in tabela.column_names


class TestOAndamento:
    def test_a_tela_recebe_as_quatro_fases(self, tmp_path):
        """A barra dá um quarto a cada uma; fase que não chega é barra travada."""
        sped = tmp_path / "contribuicoes.txt"
        sped.write_bytes(EFD.encode("cp1252"))
        fases: list[str] = []

        exclusoes.apurar([str(sped)], str(tmp_path / "saida"), ate=ATE,
                         referencia=REFERENCIA, avisar=lambda a: fases.append(a.fase))

        assert set(fases) == set(exclusoes.FASES), (
            f"faltou avisar da fase {set(exclusoes.FASES) - set(fases)}")


class TestOPacote:
    """O botão que entrega tudo de uma vez.

    Cinco planilhas em cinco downloads são cinco oportunidades de misturar
    rodadas; quem confere contra o escritório anterior precisa dos cinco do
    **mesmo instante**. Este é o teste de que o botão entrega os cinco.
    """

    def test_o_zip_traz_as_cinco_planilhas_e_o_leia_me(self, rodada, tmp_path):
        _, destino = rodada
        zip_ = tmp_path / "exclusoes_da_base.zip"

        quantas = zip_das_exclusoes(
            os.path.join(destino, exclusoes.ARQUIVO_DAS_EXCLUSOES), str(zip_))

        assert quantas == len(PACOTE)
        with zipfile.ZipFile(zip_) as z:
            dentro = set(z.namelist())
        assert dentro == {nome for nome, _, _, _, _ in PACOTE} | {LEIA_ME}

    def test_o_nome_de_cada_arquivo_comeca_pelo_numero_do_relatorio(self):
        """É por esse número que quem confere acha o arquivo de referência."""
        por_item = [nome for nome, _, _, _, _ in PACOTE if "por item" in nome]

        assert [nome.split(" ")[0] for nome in por_item] == ["680", "903", "839", "933"]

    def test_o_680_vai_em_csv_e_os_outros_em_xlsx(self):
        """O formato é o do arquivo de referência, e a razão foi medida.

        O 680 da DMINAS tem 3.568.362 linhas: em xlsx leva 1.181 segundos e sai
        com 512 MB em quatro abas, que nem abre no Excel; em CSV leva 33. E é
        assim que o MA o exporta — o arquivo de referência veio em CSV de 1,17
        GB, enquanto o do 839 e o do 933 vieram em xlsx.
        """
        formatos = {nome.split(" ")[0]: formato for nome, _, _, formato, _ in PACOTE}

        assert formatos["680"] == "csv"
        assert {formatos[n] for n in ("903", "839", "933")} == {"xlsx"}
        assert all(nome.endswith(f".{formato}")
                   for nome, _, _, formato, _ in PACOTE), (
            "o nome dentro do pacote tem de dizer o formato que ele é")

    def test_o_leia_me_avisa_da_diferenca_de_arredondamento(self, rodada, tmp_path):
        """Quem subtrair uma frente da outra tem de achar a diferença escrita.

        Sem este aviso, a diferença de 0,06% entre o consolidado e o detalhe por
        item parece defeito — e quem a encontra não tem como saber que foi
        escolhida (decisão de 24/09/2026).
        """
        _, destino = rodada
        zip_ = tmp_path / "exclusoes_da_base.zip"
        zip_das_exclusoes(os.path.join(destino, exclusoes.ARQUIVO_DAS_EXCLUSOES),
                          str(zip_))

        with zipfile.ZipFile(zip_) as z:
            leia_me = z.read(LEIA_ME).decode("ascii")

        assert "E DE PROPOSITO" in leia_me
        assert "0,06%" in leia_me

    def test_tese_que_nao_rodou_sai_nomeada_no_leia_me(self, rodada, tmp_path):
        """Zip com quatro arquivos onde deveriam ser cinco parece completo."""
        _, destino = rodada
        copia = tmp_path / "sem_o_iss"
        shutil.copytree(destino, copia)
        os.remove(copia / exclusao_do_iss.ARQUIVO_DA_EXCLUSAO_DO_ISS)
        zip_ = tmp_path / "exclusoes_da_base.zip"

        quantas = zip_das_exclusoes(
            str(copia / exclusoes.ARQUIVO_DAS_EXCLUSOES), str(zip_))

        assert quantas == len(PACOTE) - 1
        with zipfile.ZipFile(zip_) as z:
            dentro = set(z.namelist())
            leia_me = z.read(LEIA_ME).decode("ascii")
        assert not [nome for nome in dentro if nome.startswith("933")]
        assert "O QUE NAO ENTROU" in leia_me
        assert "933" in leia_me

    def test_nao_deixa_zip_pela_metade(self, rodada, tmp_path):
        """O `.tmp` não sobrevive à montagem: ele é renomeado, não copiado."""
        _, destino = rodada
        zip_ = tmp_path / "exclusoes_da_base.zip"

        zip_das_exclusoes(os.path.join(destino, exclusoes.ARQUIVO_DAS_EXCLUSOES),
                          str(zip_))

        assert not os.path.exists(str(zip_) + ".tmp")
