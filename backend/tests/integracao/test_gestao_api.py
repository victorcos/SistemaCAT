"""A etapa da Gestão, ponta a ponta: lote → apuração → parquet → planilha.

Uma EFD-Contribuições e uma ECF da mesma empresa, no mesmo lote. O que os
testes cobram aqui e os de unidade não cobrem: que a etapa leia **as duas
fontes**, que o parquet saia no formato longo com as quatro competências certas,
e que a planilha nasça larga — uma aba por tributo.

As amostras vêm dos testes de unidade da gestão: um SPED montado por nome de
campo, que já se sabe correto. Repeti-las aqui só criaria uma segunda cópia para
divergir.
"""

import io
import os

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.infraestrutura.analitico.gestao import ARQUIVO_DOS_QUADROS
from cat.infraestrutura.repositorios.modelos import Base
from tests.integracao.cadastro import (
    criar_empresa,
    criar_lote,
    criar_projeto,
    criar_usuario,
    execucao,
    iniciar,
    planilha,
    rodar_fila,
    ultima_situacao,
)
from tests.unidade.test_gestao_ecf import ECF as ECF_AMOSTRA
from tests.unidade.test_gestao_piscofins import CNPJ as CNPJ_DA_EFD
from tests.unidade.test_gestao_piscofins import EFD as EFD_AMOSTRA

# as duas amostras são da mesma empresa: é o caso real, e é o que permite um
# relatório só com os quatro tributos
CNPJ = CNPJ_DA_EFD
ECF = ECF_AMOSTRA.replace("55443322000105", CNPJ).replace("11222333000181", CNPJ)


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="gestao_analista", email="gestao@bms.local",
                  nome_exibicao="Analista da Gestão", papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def projeto_id(cliente, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_gestao")
    (pasta / "efd_062021.txt").write_bytes(EFD_AMOSTRA.encode("cp1252"))
    (pasta / "ecf_2021.txt").write_bytes(ECF.encode("cp1252"))
    empresa = criar_empresa(raiz=CNPJ[:8], cnpj=CNPJ, razao="COMERCIO DO TESTE LTDA",
                            ie="123456789012", por="gestao_analista")
    projeto = criar_projeto(empresa_id=empresa, nome="Gestão de teste", por="gestao_analista")
    criar_lote(projeto_id=projeto, pasta=str(pasta))
    return projeto


@pytest.fixture(scope="module")
def apuracao(cliente, projeto_id):
    r = iniciar(cliente, "apuracao_contribuicoes", projeto_id, "gestao_analista")
    assert r.status_code == 202, r.text
    rodar_fila()
    d = execucao(r.json()["id"])
    assert d["situacao"] == "concluida", d.get("erro")
    return d


class TestARodada:
    def test_le_as_duas_fontes_e_monta_os_quatro_tributos(self, apuracao):
        r = apuracao["resumo"]

        assert (r["contribuicoes"], r["ecf"]) == (1, 1)
        assert r["tributos"] == ["PIS", "COFINS", "IRPJ", "CSLL"]
        assert r["ilegiveis"] == 0
        assert r["cnpj"] == CNPJ

    def test_as_competencias_das_duas_fontes_convivem(self, apuracao):
        """A EFD é de junho; a ECF, anual, cai em dezembro."""
        assert apuracao["resumo"]["competencias"] == ["2021-06", "2021-12"]

    def test_os_36_quadros_de_pis_e_cofins_entram(self, apuracao):
        # 36 de PIS + 36 de COFINS + os de IRPJ e CSLL
        assert apuracao["resumo"]["quadros"] > 72

    def test_o_aviso_sobre_o_gabarito_do_irpj_aparece(self, apuracao):
        """Quem usa o número precisa saber que ele não passou por gabarito."""
        avisos = [e["texto"] for e in apuracao["resumo"]["log"] if e["nivel"] == "aviso"]

        assert any("IRPJ e CSLL ainda não foram conferidos" in a for a in avisos)


class TestOParquet:
    def test_sai_no_formato_longo_com_o_esquema_fixo(self, apuracao):
        caminho = os.path.join(pasta_da_execucao(apuracao["id"]), ARQUIVO_DOS_QUADROS)
        tabela = pq.read_table(caminho)

        assert tabela.schema.names == [
            "tributo", "quadro", "quadro_titulo", "ordem", "rotulo", "nivel",
            "titulo", "externo", "unidade", "competencia", "valor"]
        assert tabela.num_rows > 0

    def test_a_linha_externa_fica_nula_e_nao_zerada(self, apuracao):
        """Zero é uma afirmação; a DCTF não é lida, então não se afirma nada."""
        caminho = os.path.join(pasta_da_execucao(apuracao["id"]), ARQUIVO_DOS_QUADROS)
        linhas = pq.read_table(caminho).to_pylist()
        externas = [l for l in linhas if l["externo"]]

        assert externas, "a amostra de IRPJ tem linhas de DCTF e e-CAC"
        assert all(l["valor"] is None for l in externas)

    def test_o_valor_de_um_quadro_conhecido_bate(self, apuracao):
        """O quadro 30 do PIS soma a base das saídas com incidência."""
        caminho = os.path.join(pasta_da_execucao(apuracao["id"]), ARQUIVO_DOS_QUADROS)
        linhas = pq.read_table(caminho).to_pylist()
        achada = next(l for l in linhas
                      if l["tributo"] == "PIS" and l["quadro"] == "30"
                      and l["competencia"] == "2021-06" and l["rotulo"].startswith("01"))

        assert achada["valor"] == 100_000       # R$ 1.000,00 em centavos
        assert achada["unidade"] == "dinheiro"


class TestAPlanilha:
    def test_sai_uma_aba_por_tributo(self, cliente, apuracao):
        import openpyxl  # noqa: PLC0415

        baixada = planilha(cliente, "apuracao_contribuicoes", apuracao["id"], "quadros")
        assert baixada.status_code == 200, baixada.text
        assert "gestao_fiscal.xlsx" in baixada.headers["content-disposition"]
        livro = openpyxl.load_workbook(io.BytesIO(baixada.content), read_only=True)

        assert livro.sheetnames == ["PIS", "COFINS", "IRPJ", "CSLL"]
        aba = livro["PIS"]
        # a primeira coluna é a descrição; as seguintes, os meses
        assert aba.cell(row=1, column=1).value == "Descrição"
        assert aba.cell(row=1, column=2).value == "JUN/2021"
        livro.close()

    def test_o_csv_traz_o_tributo_numa_coluna(self, cliente, apuracao):
        """Não há aba em CSV: o tributo vira coluna e quem abre filtra por ela."""
        baixada = planilha(cliente, "apuracao_contribuicoes", apuracao["id"], "quadros",
                           formato="csv")
        assert baixada.status_code == 200, baixada.text
        linhas = baixada.content.decode("utf-8-sig").splitlines()
        cabecalho = linhas[0].split(";")
        primeira = linhas[1]

        assert cabecalho[:4] == ["Tributo", "Quadro", "Título do Quadro", "Descrição"]
        assert "JUN/2021" in cabecalho
        assert primeira.startswith("PIS;")


class TestOQueARodadaRecusa:
    def test_lote_sem_efd_e_sem_ecf_e_recusado_dizendo_o_que_falta(
            self, cliente, tmp_path_factory):
        pasta = tmp_path_factory.mktemp("base_sem_fonte")
        (pasta / "qualquer.txt").write_bytes(b"nao e sped\n")
        empresa = criar_empresa(raiz="99887766", cnpj="99887766000133",
                                razao="EMPRESA SEM FONTE", ie="1", por="gestao_analista")
        projeto = criar_projeto(empresa_id=empresa, nome="Sem fonte", por="gestao_analista")
        criar_lote(projeto_id=projeto, pasta=str(pasta))

        r = iniciar(cliente, "apuracao_contribuicoes", projeto, "gestao_analista")

        assert r.status_code == 422
        assert "EFD-Contribuições nem ECF" in r.json()["detail"]
        assert ultima_situacao(projeto, "apuracao_contribuicoes") is None
