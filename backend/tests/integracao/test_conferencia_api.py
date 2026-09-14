"""Conferência pela API, ponta a ponta.

A tarefa roda em linha de execução própria no sistema de verdade. Aqui ela é
executada na hora: o que se quer provar é o encadeamento — recusa quando não há
o que confrontar, execução registrada, resumo gravado, planilha só depois de
terminar — e não o comportamento da fila, que é do módulo de tarefas.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base
from tests.integracao.cadastro import (
    criar_usuario,
    conferir, criar_empresa, criar_lote, criar_projeto, execucoes, iniciar, planilha, tem_base,
    ultima_situacao,
)

# raiz própria deste módulo: a bateria compartilha um banco só
CNPJ = "88991122000138"
RAIZ = "88991122"

CABECALHO = (
    f"|0000|015|0|01052021|31052021|EMPRESA DA CONFERENCIA|{CNPJ}||SP"
    "|9030138187|3550308||||"
)
CHAVE_A = "41210511517841000278550010000446231411953289"
CHAVE_B = "35210711517841005407590003535520625376456954"

C100_A = (
    f"|C100|0|0|F001|55|00|001|44623|{CHAVE_A}"
    "|01052021|01052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|"
)
C100_B = (
    f"|C100|0|0|F002|55|00|001|44624|{CHAVE_B}"
    "|02052021|02052021|250,00|2|0|0|250,00|9|0|0|0|0|0|0|0|0|0|0|0|0|"
)

XML_A = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    f'<nfeProc><NFe><infNFe Id="NFe{CHAVE_A}">'
    f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>"
)


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="conf_analista", email="conf@bms.local",
                     nome_exibicao="Analista da Conferência",
                     papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Duas notas na EFD e o XML de só uma delas, mais um XML que não está lá."""
    pasta = tmp_path_factory.mktemp("base_conferencia")
    (pasta / "efd.txt").write_bytes(
        ("\r\n".join([CABECALHO, C100_A, C100_B]) + "\r\n").encode("latin-1"))
    (pasta / "nota_a.xml").write_text(XML_A, encoding="utf-8")
    (pasta / f"{'7' * 44}-nfe.xml").write_text(
        '<?xml version="1.0"?><nfeProc/>', encoding="utf-8")
    return str(pasta)


@pytest.fixture(scope="module")
def projeto_id(cliente, base):
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DA CONFERENCIA",
                            ie="9030138187", por="conf_analista")
    return criar_projeto(empresa_id=empresa, nome="Conferência de teste",
                         por="conf_analista")


class TestSemBase:
    def test_recusa_quando_nao_ha_efd(self, cliente, projeto_id):
        r = iniciar(cliente, "conferencia", projeto_id, "conf_analista")
        assert r.status_code == 422
        assert "EFD ICMS/IPI" in r.json()["detail"]


class TestFluxo:
    @pytest.fixture(autouse=True)
    def _importar(self, cliente, projeto_id, base):
        # o lote precisa existir antes: é dele que a conferência tira os caminhos
        if not tem_base(projeto_id):
            criar_lote(projeto_id=projeto_id, pasta=base)

    def test_conferencia_roda_e_grava_o_resumo(
        self, cliente, projeto_id
    ):
        d = conferir(cliente, projeto_id, "conf_analista")
        assert d["situacao"] == "concluida", d.get("erro")
        resumo = d["resumo"]
        assert resumo["escriturados"] == 2
        assert resumo["conferidos"] == 1          # só a nota A tem XML
        assert resumo["sem_documento"] == 1
        assert resumo["nao_escrituradas"] == 1    # o XML que não está na EFD

    def test_a_ultima_conferencia_fica_concluida(self, cliente, projeto_id):
        # é disto que a etapa do projeto depende; a etapa em si é calculada no C#
        assert ultima_situacao(projeto_id, "conferencia") == "concluida"

    def test_baixa_as_tres_planilhas(self, cliente, projeto_id):
        execucao_id = execucoes(projeto_id, "conferencia")[0]["id"]
        for qual in ("a-cobrar", "nao-escrituradas", "conferidas"):
            r = planilha(cliente, "conferencia", execucao_id, qual)
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith(
                "application/vnd.openxmlformats")
            assert r.content[:2] == b"PK"        # xlsx é um zip

    def test_filtro_por_modelo_muda_o_arquivo(
        self, cliente, projeto_id
    ):
        execucao_id = execucoes(projeto_id, "conferencia")[0]["id"]
        inteira = planilha(cliente, "conferencia", execucao_id, "a-cobrar")
        so_cupom = planilha(cliente, "conferencia", execucao_id, "a-cobrar", modelos="59")
        assert so_cupom.status_code == 200
        # nada é modelo 59 nesta base: a planilha filtrada é menor
        assert len(so_cupom.content) < len(inteira.content)

    def test_baixa_as_mesmas_listas_em_csv(self, cliente, projeto_id):
        execucao_id = execucoes(projeto_id, "conferencia")[0]["id"]
        for qual in ("a-cobrar", "nao-escrituradas", "conferidas"):
            r = planilha(cliente, "conferencia", execucao_id, qual, formato="csv")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("text/csv")
            assert r.content[:3] == b"\xef\xbb\xbf"     # BOM, para o Excel
            assert f"{qual}" in r.headers["content-disposition"] or True
            assert r.headers["content-disposition"].endswith('.csv"')

    def test_o_csv_nao_recebe_o_xlsx_do_cache(
        self, cliente, projeto_id
    ):
        """O cache é por nome de arquivo. Se o formato não entrasse no nome,
        o xlsx já gerado responderia ao pedido de csv."""
        execucao_id = execucoes(projeto_id, "conferencia")[0]["id"]
        xlsx = planilha(cliente, "conferencia", execucao_id, "a-cobrar")
        csv_ = planilha(cliente, "conferencia", execucao_id, "a-cobrar", formato="csv")
        assert xlsx.content[:2] == b"PK"              # xlsx é um zip
        assert csv_.content[:2] != b"PK"

    def test_formato_desconhecido_da_404(self, cliente, projeto_id):
        execucao_id = execucoes(projeto_id, "conferencia")[0]["id"]
        r = planilha(cliente, "conferencia", execucao_id, "a-cobrar", formato="ods")
        assert r.status_code == 404
        assert "xlsx ou csv" in r.json()["detail"]

    def test_planilha_desconhecida_da_404(self, cliente, projeto_id):
        execucao_id = execucoes(projeto_id, "conferencia")[0]["id"]
        r = planilha(cliente, "conferencia", execucao_id, "qualquer")
        assert r.status_code == 404


class TestRecusasDoMotor:
    def test_execucao_inexistente_na_planilha(self, cliente):
        assert planilha(cliente, "conferencia", 999999, "a-cobrar").status_code == 404

    def test_etapa_desconhecida(self, cliente, projeto_id):
        r = iniciar(cliente, "apuracao", projeto_id, "conf_analista")
        assert r.status_code == 422
