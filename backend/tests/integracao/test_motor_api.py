"""O que o motor segue garantindo por conta própria, sem rota de login.

Estes três vieram de test_auth_api.py quando o login foi para a API em C#
(13/09/2026). Os cenários de login em si estão em
api/tests/Cat.Api.Testes/AutenticacaoTestes.cs.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.dominio.acesso.usuario import Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base, UsuarioDB
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql

SENHA = "Sistema2026cat"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="motor.ana", email="motor.ana@bms.local", nome_exibicao="Ana",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


def test_saude_responde(cliente):
    r = cliente.get("/api/saude")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_resposta_traz_identificador_de_requisicao(cliente):
    """Sem isso não dá para juntar as linhas de log de um mesmo pedido."""
    assert cliente.get("/api/saude").headers.get("X-Request-Id")


def test_login_nao_mora_mais_no_motor(cliente):
    """A regra de login existe num lugar só. Se esta rota voltar, voltam as duas."""
    r = cliente.post("/api/auth/token", data={"username": "motor.ana", "password": SENHA})
    assert r.status_code in (404, 405)


def test_gestao_de_usuarios_nao_mora_mais_no_motor(cliente):
    """Mínimo de gestores e senha provisória existem num lugar só: a API em C#."""
    assert cliente.get("/api/usuarios").status_code in (404, 405)
    assert cliente.post("/api/usuarios/eu/senha", json={}).status_code in (404, 405)


def test_senha_nao_e_recuperavel_do_banco(cliente):
    """O sistema não pode ser capaz de descobrir a senha de ninguém."""
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    s = sessionmaker(bind=motor)()
    for h in s.scalars(select(UsuarioDB.senha_hash)):
        assert SENHA not in h
        assert h.startswith(("$argon2", "$2"))
    s.close()
