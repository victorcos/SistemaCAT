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
from cat.apresentacao.api.routers import conferencia_router
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql

SENHA = "Sistema2026cat"

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
    repo = UsuarioRepositorioSql(s)
    repo.criar(usuario="conf_analista", email="conf@bms.local",
               nome_exibicao="Analista da Conferência",
               senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
               papel=Papel.DEV, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    r = cliente.post("/api/auth/token",
                     data={"username": "conf_analista", "password": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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
def projeto_id(cliente, cabecalhos, base):
    r = cliente.post("/api/empresas", headers=cabecalhos, json={
        "cnpj_raiz": RAIZ, "cnpj_matriz": CNPJ,
        "razao_social": "EMPRESA DA CONFERENCIA", "uf": "SP",
        "inscricao_estadual": "9030138187",
    })
    assert r.status_code == 201, r.text
    empresa = r.json()["id"]

    r = cliente.post("/api/projetos", headers=cabecalhos, json={
        "empresa_id": empresa, "frente": "cat42", "nome": "Conferência de teste",
        "competencia_ini": "2021-05-01", "competencia_fim": "2021-05-01",
        "observacao": None,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
def rodar_na_hora(monkeypatch):
    """A tarefa roda dentro da requisição, para o teste não depender de tempo."""
    monkeypatch.setattr(conferencia_router, "disparar",
                        lambda funcao, *a, **k: funcao(*a, **k))


class TestSemBase:
    def test_recusa_quando_nao_ha_efd(self, cliente, cabecalhos, projeto_id):
        r = cliente.post(f"/api/projetos/{projeto_id}/conferencias",
                         headers=cabecalhos)
        assert r.status_code == 422
        assert "EFD ICMS/IPI" in r.json()["detail"]


class TestFluxo:
    @pytest.fixture(autouse=True)
    def _importar(self, cliente, cabecalhos, projeto_id, base):
        # o lote precisa existir antes: é dele que a conferência tira os caminhos
        cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                     json={"pasta": base, "observacao": None})

    def test_conferencia_roda_e_grava_o_resumo(
        self, cliente, cabecalhos, projeto_id
    ):
        r = cliente.post(f"/api/projetos/{projeto_id}/conferencias",
                         headers=cabecalhos)
        assert r.status_code == 202, r.text
        execucao_id = r.json()["id"]

        d = cliente.get(f"/api/conferencias/{execucao_id}",
                        headers=cabecalhos).json()
        assert d["situacao"] == "concluida", d.get("erro")
        resumo = d["resumo"]
        assert resumo["escriturados"] == 2
        assert resumo["conferidos"] == 1          # só a nota A tem XML
        assert resumo["sem_documento"] == 1
        assert resumo["nao_escrituradas"] == 1    # o XML que não está na EFD

    def test_a_etapa_do_projeto_conclui(self, cliente, cabecalhos, projeto_id):
        d = cliente.get(f"/api/projetos/{projeto_id}", headers=cabecalhos).json()
        etapa = next(e for e in d["etapas"] if e["chave"] == "conferencia")
        assert etapa["situacao"] == "concluida"

    def test_baixa_as_duas_planilhas(self, cliente, cabecalhos, projeto_id):
        execucao_id = cliente.get(f"/api/projetos/{projeto_id}/conferencias",
                                  headers=cabecalhos).json()[0]["id"]
        for qual in ("a-cobrar", "nao-escrituradas"):
            r = cliente.get(
                f"/api/conferencias/{execucao_id}/planilhas/{qual}",
                headers=cabecalhos)
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith(
                "application/vnd.openxmlformats")
            assert r.content[:2] == b"PK"        # xlsx é um zip

    def test_filtro_por_modelo_muda_o_arquivo(
        self, cliente, cabecalhos, projeto_id
    ):
        execucao_id = cliente.get(f"/api/projetos/{projeto_id}/conferencias",
                                  headers=cabecalhos).json()[0]["id"]
        inteira = cliente.get(
            f"/api/conferencias/{execucao_id}/planilhas/a-cobrar",
            headers=cabecalhos)
        so_cupom = cliente.get(
            f"/api/conferencias/{execucao_id}/planilhas/a-cobrar?modelos=59",
            headers=cabecalhos)
        assert so_cupom.status_code == 200
        # nada é modelo 59 nesta base: a planilha filtrada é menor
        assert len(so_cupom.content) < len(inteira.content)

    def test_planilha_desconhecida_da_404(self, cliente, cabecalhos, projeto_id):
        execucao_id = cliente.get(f"/api/projetos/{projeto_id}/conferencias",
                                  headers=cabecalhos).json()[0]["id"]
        r = cliente.get(f"/api/conferencias/{execucao_id}/planilhas/qualquer",
                        headers=cabecalhos)
        assert r.status_code == 404


class TestAcesso:
    def test_sem_token_nao_entra(self, cliente, projeto_id):
        assert cliente.post(
            f"/api/projetos/{projeto_id}/conferencias").status_code == 401

    def test_trabalho_inexistente(self, cliente, cabecalhos):
        assert cliente.post("/api/projetos/999999/conferencias",
                            headers=cabecalhos).status_code == 404
