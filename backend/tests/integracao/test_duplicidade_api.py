"""Cópia de arquivo entre lotes, pelo canal interno do motor.

Registra um lote com um SPED; depois inspeciona outra pasta com uma cópia byte
a byte dele sob outro nome. A inspeção tem de apontar a cópia e deixá-la fora
da lista. Recusar a importação de uma pasta só de cópias é regra da API em C#
(api/tests/Cat.Api.Testes/LotesTestes.cs), que decide a partir desta resposta.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.dominio.comum.cnpj import Cnpj
from cat.infraestrutura.repositorios.modelos import Base
from tests.integracao.cadastro import (
    SEGREDO, criar_usuario, criar_empresa, criar_lote, criar_projeto, hashes_nos_lotes,
)

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
    f"|0000|018|0|01052021|31052021|EMPRESA DA COPIA|{CNPJ}||SP|9000000000|3550308||||\r\n"
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
    criar_usuario(s, usuario="copia_analista", email="copia@bms.local",
                     nome_exibicao="Analista da Cópia",
                     papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


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
def projeto_id(cliente):
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DA COPIA",
                            ie="9000000000", por="copia_analista")
    return criar_projeto(empresa_id=empresa, nome="Cópia de teste",
                         fim="2021-06-01", por="copia_analista")


def inspecionar(cliente, projeto_id, pasta):
    r = cliente.post("/interno/lotes/inspecionar", headers=SEGREDO,
                     json={"projeto_id": projeto_id, "pasta": pasta})
    assert r.status_code == 200, r.text
    return r.json()


class TestCopiaEntreLotes:
    def test_o_primeiro_lote_entra_e_grava_sem_hash(self, cliente, projeto_id, pastas):
        # sem candidato a cópia, ninguém é hashado: ler 100 GB inteiros a cada
        # importação não se justifica
        a, _, _ = pastas
        criar_lote(projeto_id=projeto_id, pasta=a)
        assert hashes_nos_lotes(projeto_id) == [None]

    def test_a_copia_e_apontada_e_fica_fora_da_lista(self, cliente, projeto_id, pastas):
        _, b, _ = pastas
        corpo = inspecionar(cliente, projeto_id, b)
        assert corpo["copias"] == 1
        assert corpo["arquivos"] == []
        assert any("já está no trabalho" in a for a in corpo["avisos"])

    def test_conteudo_novo_continua_entrando(self, cliente, projeto_id, pastas):
        _, _, c = pastas
        corpo = inspecionar(cliente, projeto_id, c)
        assert corpo["copias"] == 0
        assert [a["ja_no_trabalho"] for a in corpo["arquivos"]] == [False]
        assert corpo["serve"] is True
