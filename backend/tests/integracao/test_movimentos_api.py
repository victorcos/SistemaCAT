"""Histórico de movimentação pela API, ponta a ponta.

Encadeamento: lote → conferência → movimentos. A etapa recusa enquanto não
há conferência concluída, roda em linha própria (aqui, na hora), grava o
resumo, marca cada movimento com o que a conferência achou e entrega as
quatro planilhas. E o roteiro do projeto passa a mostrar a etapa concluída.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.apresentacao.api.routers import conferencia_router, movimentos_router
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql

SENHA = "Sistema2026cat"

# raiz própria deste módulo: a bateria compartilha um banco só
CNPJ = "77889900000166"
RAIZ = "77889900"

CHAVE_A = "35210577889900000166550010000010001000000010"
CHAVE_B = "35210577889900000166550010000010002000000020"

CABECALHO = (f"|0000|015|0|01052021|31052021|EMPRESA DOS MOVIMENTOS|{CNPJ}||SP"
             "|123456789012|3550308||||")
ITEM = "|0200|1000144|Iog Vidativa 160g|7898194090401||CX|00|04031000||04||18|1702200|"
C100_A = (f"|C100|0|1|F001|55|00|001|10001|{CHAVE_A}"
          "|01052021|01052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C170_A = ("|C170|1|1000144|Iogurte|10|CX|100,00|0|0|010|1403|300|100,00|18|18,00"
          "|150,00|18|9,00||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
C100_B = (f"|C100|0|1|F002|55|00|001|10002|{CHAVE_B}"
          "|02052021|02052021|50,00|2|0|0|50,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C170_B = ("|C170|1|1000144|Iogurte|5|CX|50,00|0|0|010|1403|300|50,00|18|9,00"
          "|75,00|18|4,50||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
H005 = "|H005|30042021|96,39|01|"
H010 = "|H010|1000144|CX|81|1,19|96,39|0|||1.1.20.01.01|96,39|"

XML_A = ('<?xml version="1.0" encoding="UTF-8"?>'
         f'<nfeProc><NFe><infNFe Id="NFe{CHAVE_A}">'
         f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>")


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="mov_analista", email="mov@bms.local",
        nome_exibicao="Analista dos Movimentos",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.DEV, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    r = cliente.post("/api/auth/token",
                     data={"username": "mov_analista", "password": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Duas entradas com item; XML só da primeira; inventário."""
    pasta = tmp_path_factory.mktemp("base_movimentos")
    (pasta / "efd.txt").write_bytes(("\r\n".join([
        CABECALHO, ITEM, C100_A, C170_A, C100_B, C170_B, H005, H010,
    ]) + "\r\n").encode("latin-1"))
    (pasta / f"{CHAVE_A}-nfe.xml").write_text(XML_A, encoding="utf-8")
    return str(pasta)


@pytest.fixture(scope="module")
def projeto_id(cliente, cabecalhos, base):
    r = cliente.post("/api/empresas", headers=cabecalhos, json={
        "cnpj_raiz": RAIZ, "cnpj_matriz": CNPJ,
        "razao_social": "EMPRESA DOS MOVIMENTOS", "uf": "SP",
        "inscricao_estadual": "123456789012",
    })
    assert r.status_code == 201, r.text
    r = cliente.post("/api/projetos", headers=cabecalhos, json={
        "empresa_id": r.json()["id"], "frente": "cat42",
        "nome": "Movimentos de teste",
        "competencia_ini": "2021-05-01", "competencia_fim": "2021-05-01",
        "observacao": None,
    })
    assert r.status_code == 201, r.text
    projeto = r.json()["id"]
    r = cliente.post(f"/api/projetos/{projeto}/lotes", headers=cabecalhos,
                     json={"pasta": base, "observacao": None})
    assert r.status_code == 201, r.text
    return projeto


@pytest.fixture(scope="module", autouse=True)
def rodar_na_hora():
    with pytest.MonkeyPatch.context() as mp:
        na_hora = lambda funcao, *a, **k: funcao(*a, **k)  # noqa: E731
        mp.setattr(conferencia_router, "disparar", na_hora)
        mp.setattr(movimentos_router, "disparar", na_hora)
        yield


def _etapa(cliente, cabecalhos, projeto_id, chave):
    d = cliente.get(f"/api/projetos/{projeto_id}", headers=cabecalhos).json()
    return next(e for e in d["etapas"] if e["chave"] == chave)


class TestOrdemDasEtapas:
    def test_recusa_sem_conferencia(self, cliente, cabecalhos, projeto_id):
        r = cliente.post(f"/api/projetos/{projeto_id}/movimentos", headers=cabecalhos)
        assert r.status_code == 422
        assert "conferência" in r.json()["detail"].lower()
        assert _etapa(cliente, cabecalhos, projeto_id, "movimentos")["situacao"] == "bloqueada"


class TestFluxo:
    @pytest.fixture(scope="class", autouse=True)
    def _conferido(self, cliente, cabecalhos, projeto_id):
        r = cliente.post(f"/api/projetos/{projeto_id}/conferencias", headers=cabecalhos)
        assert r.status_code == 202, r.text
        assert cliente.get(f"/api/conferencias/{r.json()['id']}",
                           headers=cabecalhos).json()["situacao"] == "concluida"

    @pytest.fixture(scope="class")
    def execucao(self, cliente, cabecalhos, projeto_id):
        r = cliente.post(f"/api/projetos/{projeto_id}/movimentos", headers=cabecalhos)
        assert r.status_code == 202, r.text
        d = cliente.get(f"/api/movimentos/{r.json()['id']}", headers=cabecalhos).json()
        assert d["situacao"] == "concluida", d.get("erro")
        return d

    def test_resumo(self, execucao):
        r = execucao["resumo"]
        assert r["documentos"] == 2
        assert r["documentos_com_item"] == 2
        assert r["movimentos"] == 2
        assert r["itens_cadastrados"] == 1
        assert r["inventarios"] == 1
        assert r["valor_em_estoque"] == "96.39"
        assert r["conferencia_usada"] is True
        # a nota A tem XML; a B ficou pendente na conferência
        assert {f["codigo"]: f["documentos"] for f in r["por_classificacao"]} == {
            "conferido": 1, "pendente": 1}
        assert any("1 movimento(s) são de documentos ainda pendentes" in a
                   for a in r["avisos"])

    def test_a_etapa_do_projeto_conclui(self, cliente, cabecalhos, projeto_id, execucao):
        assert _etapa(cliente, cabecalhos, projeto_id, "movimentos")["situacao"] == "concluida"

    def test_lista_e_detalha(self, cliente, cabecalhos, projeto_id, execucao):
        lista = cliente.get(f"/api/projetos/{projeto_id}/movimentos",
                            headers=cabecalhos).json()
        assert [e["id"] for e in lista] == [execucao["id"]]
        # uma execução de outra etapa não aparece por esta rota
        conferencia = cliente.get(f"/api/projetos/{projeto_id}/conferencias",
                                  headers=cabecalhos).json()[0]
        assert cliente.get(f"/api/movimentos/{conferencia['id']}",
                           headers=cabecalhos).status_code == 404

    def test_baixa_as_quatro_planilhas(self, cliente, cabecalhos, execucao):
        for qual in ("movimentos", "itens", "inventario", "analitico"):
            r = cliente.get(f"/api/movimentos/{execucao['id']}/planilhas/{qual}",
                            headers=cabecalhos)
            assert r.status_code == 200, (qual, r.text)
            assert r.content[:2] == b"PK"

    def test_filtro_por_classificacao_muda_o_arquivo(self, cliente, cabecalhos, execucao):
        inteira = cliente.get(f"/api/movimentos/{execucao['id']}/planilhas/movimentos",
                              headers=cabecalhos)
        so_pendentes = cliente.get(
            f"/api/movimentos/{execucao['id']}/planilhas/movimentos?classificacoes=pendente",
            headers=cabecalhos)
        assert so_pendentes.status_code == 200
        assert "-pendente" in so_pendentes.headers["content-disposition"]
        assert len(so_pendentes.content) < len(inteira.content)

    def test_segunda_rodada_ao_mesmo_tempo_e_recusada(self, cliente, cabecalhos,
                                                       projeto_id, execucao, monkeypatch):
        # sem rodar na hora, a primeira fica "na fila" e a segunda bate em 409
        monkeypatch.setattr(movimentos_router, "disparar", lambda *a, **k: None)
        r1 = cliente.post(f"/api/projetos/{projeto_id}/movimentos", headers=cabecalhos)
        assert r1.status_code == 202
        r2 = cliente.post(f"/api/projetos/{projeto_id}/movimentos", headers=cabecalhos)
        assert r2.status_code == 409
