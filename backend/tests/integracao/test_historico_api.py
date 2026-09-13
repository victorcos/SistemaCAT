"""Trabalho parado não roda etapa — a parte do histórico que é do motor.

A linha do tempo, os comentários, a mudança de status e a sucessão moram na API
em C# desde 13/09/2026 (api/tests/Cat.Api.Testes/HistoricoTestes.cs). O que
fica aqui é a consequência que o motor aplica: pausar e cancelar precisam
significar alguma coisa, e uma extração de 44 minutos não pode disparar num
trabalho que a equipe decidiu parar.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from tests.integracao.cadastro import criar_empresa, criar_projeto, definir_status
from tests.integracao.sessao import cabecalhos_de

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
    UsuarioRepositorioSql(s).criar(
        usuario="hist_gestor", email="hist.gestor@bms.local",
        nome_exibicao="Gestora do Histórico",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.DEV, cargo=Cargo.DIRETOR)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def projeto_id(cliente):
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DO HISTORICO",
                            ie="123456789012", por="hist_gestor")
    return criar_projeto(empresa_id=empresa, nome="Trabalho com história",
                         fim="2021-05-31", por="hist_gestor")


def conferir(cliente, projeto_id):
    return cliente.post(f"/api/projetos/{projeto_id}/conferencias",
                        headers=cabecalhos_de("hist_gestor", SENHA))


class TestTrabalhoParado:
    def test_pausado_nao_roda_etapa(self, cliente, projeto_id):
        definir_status(projeto_id, "pausado")
        r = conferir(cliente, projeto_id)
        assert r.status_code == 422
        assert "pausado" in r.json()["detail"]
        assert "Retome-o no histórico" in r.json()["detail"]

    def test_cancelado_fica_so_para_consulta(self, cliente, projeto_id):
        definir_status(projeto_id, "cancelado")
        r = conferir(cliente, projeto_id)
        assert r.status_code == 422
        assert "cancelado fica só para consulta" in r.json()["detail"]

    def test_retomar_libera(self, cliente, projeto_id):
        definir_status(projeto_id, "em_andamento")
        # agora a recusa volta a ser por falta de base, não por status
        r = conferir(cliente, projeto_id)
        assert r.status_code == 422
        assert "EFD" in r.json()["detail"]

    def test_concluido_roda(self, cliente, projeto_id):
        # refazer a conferência depois da entrega é o que se faz quando o
        # cliente questiona um número
        definir_status(projeto_id, "concluido")
        r = conferir(cliente, projeto_id)
        assert "EFD" in r.json()["detail"]
