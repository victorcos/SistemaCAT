"""API de autenticação, ponta a ponta, contra um banco temporário."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_tmp = tempfile.mkdtemp()
os.environ["CAT_BANCO_URL"] = f"sqlite:///{_tmp}/teste.db".replace("\\", "/")
os.environ["CAT_JWT_SEGREDO"] = "segredo-so-de-teste-nao-usar-em-producao"

from cat.apresentacao.api.app import app  # noqa: E402
from cat.config import obter_config  # noqa: E402
from cat.dominio.acesso.usuario import Papel  # noqa: E402
from cat.infraestrutura.repositorios.modelos import (  # noqa: E402
    AlocacaoDB, Base, EmpresaDB,
)
from cat.infraestrutura.repositorios.usuario_repositorio import (  # noqa: E402
    UsuarioRepositorioSql,
)

SENHA = "Sistema2026cat"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    Sessao = sessionmaker(bind=motor, expire_on_commit=False)
    s = Sessao()

    empresa = EmpresaDB(cnpj_raiz="50948371", razao_social="Irmãos Boa", uf="SP")
    s.add(empresa)
    s.commit()
    s.refresh(empresa)

    repo = UsuarioRepositorioSql(s)
    ana = repo.criar("ana", "ana@bms.local", "Ana", SENHA, Papel.ANALISTA)
    repo.criar("inativo", "i@bms.local", "Inativo", SENHA, Papel.LEITURA)
    s.add(AlocacaoDB(usuario_id=ana.id, empresa_id=empresa.id,
                     papel_projeto="analista"))
    from cat.infraestrutura.repositorios.modelos import UsuarioDB
    s.get(UsuarioDB, 2).ativo = False
    s.commit()
    s.close()

    with TestClient(app) as c:
        yield c


def entrar(cliente, usuario, senha):
    return cliente.post("/api/auth/token",
                        data={"username": usuario, "password": senha})


def test_saude_responde(cliente):
    r = cliente.get("/api/saude")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_certo(cliente):
    r = entrar(cliente, "ana", SENHA)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["access_token"]
    assert corpo["usuario"]["papel"] == "analista"
    assert corpo["usuario"]["empresas"] == [1]


def test_login_aceita_maiuscula_no_usuario(cliente):
    assert entrar(cliente, "ANA", SENHA).status_code == 200


def test_senha_errada_da_401(cliente):
    r = entrar(cliente, "ana", "ErradaMesmo1")
    assert r.status_code == 401


def test_usuario_inexistente_da_401_com_a_mesma_mensagem(cliente):
    a = entrar(cliente, "ana", "ErradaMesmo1")
    b = entrar(cliente, "ninguem", "ErradaMesmo1")
    assert b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_usuario_inativo_da_403(cliente):
    r = entrar(cliente, "inativo", SENHA)
    assert r.status_code == 403
    assert "inativo" in r.json()["detail"].lower()


def test_eu_exige_token(cliente):
    assert cliente.get("/api/auth/eu").status_code == 401


def test_eu_recusa_token_falso(cliente):
    r = cliente.get("/api/auth/eu",
                    headers={"Authorization": "Bearer nao.e.um.token"})
    assert r.status_code == 401


def test_eu_com_token_valido(cliente):
    token = entrar(cliente, "ana", SENHA).json()["access_token"]
    r = cliente.get("/api/auth/eu", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["usuario"] == "ana"
    assert r.json()["empresas"] == [1]


def test_resposta_traz_identificador_de_requisicao(cliente):
    """Sem isso não dá para juntar as linhas de log de um mesmo pedido."""
    assert cliente.get("/api/saude").headers.get("X-Request-Id")


def test_senha_nunca_volta_na_resposta(cliente):
    corpo = entrar(cliente, "ana", SENHA).text.lower()
    assert SENHA.lower() not in corpo
    assert "senha_hash" not in corpo


def test_migra_resumo_antigo_no_primeiro_login(cliente):
    """Usuário com senha em bcrypt entra normalmente e sai com Argon2id.

    A migração só é possível na janela em que a senha em claro está em mãos,
    isto é, no login. Ninguém precisa trocar de senha.
    """
    import bcrypt
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cat.infraestrutura.repositorios.modelos import UsuarioDB

    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    s = sessionmaker(bind=motor, expire_on_commit=False)()

    repo = UsuarioRepositorioSql(s)
    antigo = repo.criar("legado", "legado@bms.local", "Legado", SENHA, Papel.LEITURA)
    linha = s.get(UsuarioDB, antigo.id)
    linha.senha_hash = bcrypt.hashpw(SENHA.encode(), bcrypt.gensalt()).decode()
    s.commit()
    assert linha.senha_hash.startswith("$2")

    assert entrar(cliente, "legado", SENHA).status_code == 200

    s.expire_all()
    assert s.get(UsuarioDB, antigo.id).senha_hash.startswith("$argon2id$")
    # e continua entrando depois da migração
    assert entrar(cliente, "legado", SENHA).status_code == 200
    s.close()


def test_senha_nao_e_recuperavel_do_banco(cliente):
    """O sistema não pode ser capaz de descobrir a senha de ninguém."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from cat.infraestrutura.repositorios.modelos import UsuarioDB

    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    s = sessionmaker(bind=motor)()
    for h in s.scalars(select(UsuarioDB.senha_hash)):
        assert SENHA not in h
        assert h.startswith(("$argon2", "$2"))
    s.close()
