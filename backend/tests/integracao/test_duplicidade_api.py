"""Cópia de arquivo entre lotes, pela API.

Importa uma pasta com um SPED; depois tenta importar outra pasta com uma cópia
byte a byte dele sob outro nome. A conferência da pasta tem de apontar a cópia,
e a importação tem de recusar — não há nada novo para entrar.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.dominio.comum.cnpj import Cnpj
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from tests.integracao.sessao import cabecalhos_de
from tests.integracao.cadastro import criar_empresa, criar_projeto

SENHA = "Sistema2026cat"


def _cnpj_valido(raiz: str, ordem: str = "0001") -> str:
    for dv in range(100):
        tentativa = f"{raiz}{ordem}{dv:02d}"
        try:
            Cnpj(tentativa)
            return tentativa
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("nenhum dígito válido")


RAIZ = "55667788"
CNPJ = _cnpj_valido(RAIZ)

SPED = (
    f"|0000|018|0|01052021|31052021|EMPRESA DA COPIA|{CNPJ}||SP|9030138187|3550308||||\r\n"
    "|C100|0|0|F001|55|00|001|1|35210500000000000000550010000000011000000015"
    "|05052021|05052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|\r\n"
)
SPED_JUNHO = SPED.replace("01052021|31052021", "01062021|30062021")


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="copia_analista", email="copia@bms.local",
        nome_exibicao="Analista da Cópia",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.DEV, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    return cabecalhos_de("copia_analista", SENHA)


@pytest.fixture(scope="module")
def pastas(tmp_path_factory):
    a = tmp_path_factory.mktemp("lote_a")
    b = tmp_path_factory.mktemp("lote_b")
    c = tmp_path_factory.mktemp("lote_c")
    (a / "maio.txt").write_bytes(SPED.encode("latin-1"))
    (b / "maio - copia de seguranca.txt").write_bytes(SPED.encode("latin-1"))
    (c / "junho.txt").write_bytes(SPED_JUNHO.encode("latin-1"))
    return str(a), str(b), str(c)


@pytest.fixture(scope="module")
def projeto_id(cliente, cabecalhos):
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DA COPIA",
                            ie="9030138187", por="copia_analista")
    return criar_projeto(empresa_id=empresa, nome="Cópia de teste",
                         fim="2021-06-01", por="copia_analista")


class TestCopiaEntreLotes:
    def test_o_primeiro_lote_entra_e_grava_sem_hash(
        self, cliente, cabecalhos, projeto_id, pastas
    ):
        a, _, _ = pastas
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": a, "observacao": None})
        assert r.status_code == 201, r.text
        assert r.json()["total_arquivos"] == 1

    def test_a_copia_e_apontada_na_conferencia_da_pasta(
        self, cliente, cabecalhos, projeto_id, pastas
    ):
        _, b, _ = pastas
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         headers=cabecalhos, json={"pasta": b})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["copias"] == 1
        assert corpo["total_arquivos"] == 0
        assert any("já está no trabalho" in a for a in corpo["avisos"])

    def test_a_copia_nao_entra(self, cliente, cabecalhos, projeto_id, pastas):
        _, b, _ = pastas
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": b, "observacao": None})
        # nada novo para entrar, e a mensagem diz o motivo certo: cópia, e não
        # "nada alimenta a CAT" — que é o que a checagem genérica diria
        assert r.status_code == 409, r.text
        assert "cópias exatas" in r.json()["detail"]

    def test_conteudo_novo_continua_entrando(
        self, cliente, cabecalhos, projeto_id, pastas
    ):
        _, _, c = pastas
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": c, "observacao": None})
        assert r.status_code == 201, r.text
        assert r.json()["total_arquivos"] == 1
