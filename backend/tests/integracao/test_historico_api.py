"""Histórico do trabalho pela API, ponta a ponta.

O que se prova aqui: o trabalho nasce com um evento, cada coisa que acontece
entra na linha do tempo com o nome de quem fez, status parado bloqueia
processamento, e passar o trabalho adiante é de gestor.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import AlocacaoDB, Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql

SENHA = "Sistema2026cat"

# raiz própria deste módulo: a bateria compartilha um banco só
CNPJ = "99887766000105"
RAIZ = "99887766"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    repo = UsuarioRepositorioSql(s)
    senhas = SenhasArgon2(obter_config().senha_pimenta)
    repo.criar(usuario="hist_gestor", email="hist.gestor@bms.local",
               nome_exibicao="Gestora do Histórico",
               senha_hash=senhas.gerar(SENHA), papel=Papel.DEV,
               cargo=Cargo.DIRETOR)
    repo.criar(usuario="hist_analista", email="hist.analista@bms.local",
               nome_exibicao="Analista do Histórico",
               senha_hash=senhas.gerar(SENHA), papel=Papel.ANALISTA,
               cargo=Cargo.ANALISTA)
    repo.criar(usuario="hist_inativo", email="hist.inativo@bms.local",
               nome_exibicao="Fulano Desligado",
               senha_hash=senhas.gerar(SENHA), papel=Papel.ANALISTA,
               cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


def cab(cliente, quem):
    r = cliente.post("/api/auth/token", data={"username": quem, "password": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def id_de(cliente, nome):
    lista = cliente.get("/api/usuarios", headers=cab(cliente, "hist_gestor")).json()
    return next(u["id"] for u in lista if u["usuario"] == nome)


@pytest.fixture(scope="module")
def projeto(cliente):
    c = cab(cliente, "hist_gestor")
    r = cliente.post("/api/empresas", headers=c, json={
        "cnpj_raiz": RAIZ, "cnpj_matriz": CNPJ,
        "razao_social": "EMPRESA DO HISTORICO", "uf": "SP",
        "inscricao_estadual": "123456789012",
    })
    assert r.status_code == 201, r.text
    empresa_id = r.json()["id"]
    # o analista precisa de alocação para enxergar a empresa; sem ela, a
    # recusa viria do escopo e não da regra que se quer provar
    with Sessao() as s:
        s.add(AlocacaoDB(usuario_id=id_de(cliente, "hist_analista"),
                         empresa_id=empresa_id, papel_projeto="executor"))
        s.commit()

    r = cliente.post("/api/projetos", headers=c, json={
        "empresa_id": empresa_id, "frente": "cat42",
        "nome": "Trabalho com história",
        "competencia_ini": "2021-05-01", "competencia_fim": "2021-05-31",
        "observacao": None,
    })
    assert r.status_code == 201, r.text
    return r.json()


def historico(cliente, projeto_id, quem="hist_gestor", **params):
    r = cliente.get(f"/api/projetos/{projeto_id}/historico",
                    headers=cab(cliente, quem), params=params)
    assert r.status_code == 200, r.text
    return r.json()


class TestNascimento:
    def test_o_trabalho_nasce_com_um_evento(self, cliente, projeto):
        pagina = historico(cliente, projeto["id"])
        assert len(pagina["eventos"]) == 1
        e = pagina["eventos"][0]
        assert e["tipo"] == "criado"
        assert e["autor"] == "Gestora do Histórico"
        assert "Trabalho com história" in e["texto"]
        assert not e["e_comentario"]

    def test_quem_cria_responde_pelo_trabalho(self, cliente, projeto):
        d = cliente.get(f"/api/projetos/{projeto['id']}",
                        headers=cab(cliente, "hist_gestor")).json()["projeto"]
        assert d["criado_por"] == "Gestora do Histórico"
        assert d["responsavel"] == "Gestora do Histórico"
        assert d["status"] == "em_andamento"
        assert d["status_rotulo"] == "Em andamento"


class TestComentario:
    def test_comenta_e_aparece_no_topo(self, cliente, projeto):
        r = cliente.post(
            f"/api/projetos/{projeto['id']}/historico/comentarios",
            headers=cab(cliente, "hist_analista"),
            json={"texto": "  Falei com o cliente: manda o que falta na sexta.  "},
        )
        assert r.status_code == 201, r.text
        assert r.json()["autor"] == "Analista do Histórico"
        assert r.json()["texto"] == "Falei com o cliente: manda o que falta na sexta."
        assert r.json()["e_comentario"] is True

        topo = historico(cliente, projeto["id"])["eventos"][0]
        assert topo["tipo"] == "comentario"

    def test_conta_no_resumo_do_projeto(self, cliente, projeto):
        d = cliente.get(f"/api/projetos/{projeto['id']}",
                        headers=cab(cliente, "hist_gestor")).json()["projeto"]
        assert d["comentarios"] == 1

    def test_vazio_e_recusado(self, cliente, projeto):
        r = cliente.post(f"/api/projetos/{projeto['id']}/historico/comentarios",
                         headers=cab(cliente, "hist_gestor"),
                         json={"texto": "   "})
        assert r.status_code == 422

    def test_filtro_so_comentarios(self, cliente, projeto):
        pagina = historico(cliente, projeto["id"], so_comentarios=True)
        assert all(e["e_comentario"] for e in pagina["eventos"])
        assert len(pagina["eventos"]) == 1


class TestStatus:
    def test_catalogo_traz_rotulo_e_explicacao(self, cliente):
        r = cliente.get("/api/status-de-projeto", headers=cab(cliente, "hist_gestor"))
        assert r.status_code == 200
        por_valor = {s["valor"]: s for s in r.json()}
        assert por_valor["pausado"]["rotulo"] == "Pausado"
        assert por_valor["pausado"]["exige_motivo"] is True
        assert por_valor["em_andamento"]["exige_motivo"] is False

    def test_pausar_sem_motivo_e_recusado(self, cliente, projeto):
        r = cliente.patch(f"/api/projetos/{projeto['id']}/status",
                          headers=cab(cliente, "hist_gestor"),
                          json={"status": "pausado", "motivo": "  "})
        assert r.status_code == 422
        assert "Diga por que" in r.json()["detail"]

    def test_pausar_com_motivo_registra_quem_e_por_que(self, cliente, projeto):
        r = cliente.patch(
            f"/api/projetos/{projeto['id']}/status",
            headers=cab(cliente, "hist_gestor"),
            json={"status": "pausado", "motivo": "Esperando o XML de 2023."},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "pausado", "rotulo": "Pausado"}

        topo = historico(cliente, projeto["id"])["eventos"][0]
        assert topo["tipo"] == "status"
        assert topo["texto"] == "Esperando o XML de 2023."
        assert topo["dados"]["frase"] == "Em andamento → Pausado"
        assert topo["autor"] == "Gestora do Histórico"

    def test_o_mesmo_status_de_novo_e_recusado(self, cliente, projeto):
        r = cliente.patch(f"/api/projetos/{projeto['id']}/status",
                          headers=cab(cliente, "hist_gestor"),
                          json={"status": "pausado", "motivo": "de novo"})
        assert r.status_code == 422
        assert "já está" in r.json()["detail"]

    def test_trabalho_pausado_nao_roda_etapa(self, cliente, projeto):
        r = cliente.post(f"/api/projetos/{projeto['id']}/conferencias",
                         headers=cab(cliente, "hist_gestor"))
        assert r.status_code == 422
        assert "pausado" in r.json()["detail"]
        assert "Retome-o no histórico" in r.json()["detail"]

    def test_retomar_libera(self, cliente, projeto):
        r = cliente.patch(f"/api/projetos/{projeto['id']}/status",
                          headers=cab(cliente, "hist_gestor"),
                          json={"status": "em_andamento", "motivo": ""})
        assert r.status_code == 200, r.text
        # agora a recusa volta a ser por falta de base, não por status
        r = cliente.post(f"/api/projetos/{projeto['id']}/conferencias",
                         headers=cab(cliente, "hist_gestor"))
        assert r.status_code == 422
        assert "EFD" in r.json()["detail"]


class TestSucessao:
    def test_quem_pode_receber(self, cliente, projeto):
        r = cliente.get(f"/api/projetos/{projeto['id']}/sucessores",
                        headers=cab(cliente, "hist_gestor"))
        assert r.status_code == 200
        nomes = [p["usuario"] for p in r.json()]
        assert "hist_analista" in nomes
        assert "hist_gestor" in nomes

    def test_analista_nao_passa_trabalho(self, cliente, projeto):
        r = cliente.patch(f"/api/projetos/{projeto['id']}/responsavel",
                          headers=cab(cliente, "hist_analista"),
                          json={"responsavel_id": id_de(cliente, "hist_analista"),
                                "motivo": "quero para mim"})
        assert r.status_code == 403
        assert "Só gestor" in r.json()["detail"]

    def test_gestor_passa_e_fica_registrado(self, cliente, projeto):
        alvo = id_de(cliente, "hist_analista")
        r = cliente.patch(
            f"/api/projetos/{projeto['id']}/responsavel",
            headers=cab(cliente, "hist_gestor"),
            json={"responsavel_id": alvo, "motivo": "Férias da gestora."},
        )
        assert r.status_code == 200, r.text
        assert r.json()["responsavel"] == "Analista do Histórico"

        topo = historico(cliente, projeto["id"])["eventos"][0]
        assert topo["tipo"] == "sucessao"
        assert topo["dados"]["frase"] == "Gestora do Histórico → Analista do Histórico"
        assert topo["texto"] == "Férias da gestora."

        d = cliente.get(f"/api/projetos/{projeto['id']}",
                        headers=cab(cliente, "hist_gestor")).json()["projeto"]
        assert d["responsavel"] == "Analista do Histórico"
        # quem criou não muda: são coisas diferentes
        assert d["criado_por"] == "Gestora do Histórico"

    def test_passar_para_quem_ja_responde_e_recusado(self, cliente, projeto):
        r = cliente.patch(f"/api/projetos/{projeto['id']}/responsavel",
                          headers=cab(cliente, "hist_gestor"),
                          json={"responsavel_id": id_de(cliente, "hist_analista"),
                                "motivo": ""})
        assert r.status_code == 422
        assert "já responde" in r.json()["detail"]

    def test_passar_para_conta_desativada_e_recusado(self, cliente, projeto):
        alvo = id_de(cliente, "hist_inativo")
        assert cliente.patch(f"/api/usuarios/{alvo}/situacao",
                             headers=cab(cliente, "hist_gestor"),
                             json={"ativo": False}).status_code == 200

        r = cliente.patch(f"/api/projetos/{projeto['id']}/responsavel",
                          headers=cab(cliente, "hist_gestor"),
                          json={"responsavel_id": alvo, "motivo": ""})
        assert r.status_code == 422
        assert "desativado" in r.json()["detail"]
        # e some da lista de quem pode receber
        sucessores = cliente.get(f"/api/projetos/{projeto['id']}/sucessores",
                                 headers=cab(cliente, "hist_gestor")).json()
        assert "hist_inativo" not in [p["usuario"] for p in sucessores]


class TestPaginacao:
    def test_pagina_para_tras_sem_repetir(self, cliente, projeto):
        c = cab(cliente, "hist_gestor")
        for i in range(6):
            cliente.post(f"/api/projetos/{projeto['id']}/historico/comentarios",
                         headers=c, json={"texto": f"nota {i}"})

        primeira = historico(cliente, projeto["id"], quantos=3)
        assert len(primeira["eventos"]) == 3
        assert primeira["tem_mais"] is True
        assert primeira["proximo_cursor"] == primeira["eventos"][-1]["id"]

        segunda = historico(cliente, projeto["id"], quantos=3,
                            antes_de=primeira["proximo_cursor"])
        ids_primeira = {e["id"] for e in primeira["eventos"]}
        ids_segunda = {e["id"] for e in segunda["eventos"]}
        assert not (ids_primeira & ids_segunda)
        # e vêm em ordem decrescente, do mais recente para o mais antigo
        assert max(ids_segunda) < min(ids_primeira)


class TestEscopo:
    def test_trabalho_inexistente_da_404(self, cliente):
        r = cliente.get("/api/projetos/999999/historico",
                        headers=cab(cliente, "hist_gestor"))
        assert r.status_code == 404

    def test_sem_token_nao_le(self, cliente, projeto):
        assert cliente.get(f"/api/projetos/{projeto['id']}/historico").status_code == 401
