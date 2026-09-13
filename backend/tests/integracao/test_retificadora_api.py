"""Retificadora ponta a ponta: importa, confere, e a original fica fora da leitura.

Três EFD no lote: a original de maio, a retificadora de maio (que traz uma
nota a mais) e a original de junho. A conferência tem de ler DUAS — a
retificadora e junho —, nunca a original de maio. Se lesse as três, a nota A
apareceria duas vezes e a retificação não teria substituído nada.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.apresentacao.api.routers import conferencia_router
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.dominio.comum.cnpj import Cnpj
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from tests.integracao.sessao import cabecalhos_de

SENHA = "Sistema2026cat"


def _cnpj_valido(raiz: str, ordem: str = "0001") -> str:
    """Um CNPJ com dígito válido para esta raiz. A bateria compartilha um banco
    só, então cada módulo precisa de raiz própria."""
    for dv in range(100):
        tentativa = f"{raiz}{ordem}{dv:02d}"
        try:
            Cnpj(tentativa)
            return tentativa
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("nenhum dígito válido")


RAIZ = "44556677"
CNPJ = _cnpj_valido(RAIZ)

CHAVE_A = "35210500000000000000550010000000011000000015"
CHAVE_B = "35210500000000000000550010000000021000000024"
CHAVE_C = "35210600000000000000550010000000031000000033"


def cabecalho(cod_fin: str, ini: str, fim: str) -> str:
    return (f"|0000|018|{cod_fin}|{ini}|{fim}|EMPRESA RETIF|{CNPJ}||SP"
            "|9030138187|3550308||||")


def c100(chave: str, numero: str, data: str) -> str:
    return (f"|C100|0|0|F001|55|00|001|{numero}|{chave}"
            f"|{data}|{data}|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")


ORIGINAL_MAIO = "\r\n".join([cabecalho("0", "01052021", "31052021"),
                             c100(CHAVE_A, "1", "05052021")]) + "\r\n"
RETIFICADORA_MAIO = "\r\n".join([cabecalho("1", "01052021", "31052021"),
                                 c100(CHAVE_A, "1", "05052021"),
                                 c100(CHAVE_B, "2", "06052021")]) + "\r\n"
ORIGINAL_JUNHO = "\r\n".join([cabecalho("0", "01062021", "30062021"),
                              c100(CHAVE_C, "3", "03062021")]) + "\r\n"
XML_C = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    f'<nfeProc><NFe><infNFe Id="NFe{CHAVE_C}">'
    f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>"
)


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="retif_analista", email="retif@bms.local",
        nome_exibicao="Analista da Retificação",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.DEV, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    return cabecalhos_de("retif_analista", SENHA)


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_retificadora")
    (pasta / "maio.txt").write_bytes(ORIGINAL_MAIO.encode("latin-1"))
    (pasta / "maio_retificadora.txt").write_bytes(RETIFICADORA_MAIO.encode("latin-1"))
    (pasta / "junho.txt").write_bytes(ORIGINAL_JUNHO.encode("latin-1"))
    (pasta / "nota_c.xml").write_text(XML_C, encoding="utf-8")
    return str(pasta)


@pytest.fixture(scope="module")
def projeto_id(cliente, cabecalhos):
    r = cliente.post("/api/empresas", headers=cabecalhos, json={
        "cnpj_raiz": RAIZ, "cnpj_matriz": CNPJ, "razao_social": "EMPRESA RETIF",
        "uf": "SP", "inscricao_estadual": "9030138187"})
    assert r.status_code == 201, r.text
    r = cliente.post("/api/projetos", headers=cabecalhos, json={
        "empresa_id": r.json()["id"], "frente": "cat42",
        "nome": "Retificadora de teste", "competencia_ini": "2021-05-01",
        "competencia_fim": "2021-06-01", "observacao": None})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(autouse=True)
def rodar_na_hora(monkeypatch):
    monkeypatch.setattr(conferencia_router, "disparar",
                        lambda funcao, *a, **k: funcao(*a, **k))


class TestImportacao:
    def test_a_conferencia_da_pasta_avisa(self, cliente, cabecalhos, projeto_id, base):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         headers=cabecalhos, json={"pasta": base})
        assert r.status_code == 200, r.text
        assert r.json()["total_arquivos"] == 4      # as três EFD entram, mais o XML
        assert any("retificadora" in a for a in r.json()["avisos"])

    def test_as_tres_efd_entram_no_lote(self, cliente, cabecalhos, projeto_id, base):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": base, "observacao": None})
        assert r.status_code == 201, r.text
        efd = next(c for c in r.json()["contagens"] if c["tipo"] == "sped_icms_ipi")
        assert efd["quantidade"] == 3


class TestConferencia:
    def test_le_a_retificadora_e_nao_a_original(self, cliente, cabecalhos, projeto_id):
        r = cliente.post(f"/api/projetos/{projeto_id}/conferencias", headers=cabecalhos)
        assert r.status_code == 202, r.text
        d = cliente.get(f"/api/conferencias/{r.json()['id']}", headers=cabecalhos).json()
        assert d["situacao"] == "concluida", d.get("erro")

        # retificadora (A, B) + junho (C) = 3 documentos; com a original seriam 4
        assert d["documentos"] == 3
        resumo = d["resumo"]
        assert resumo["escriturados"] == 3
        assert resumo["conferidos"] == 1            # só C tem XML
        assert resumo["sem_documento"] == 2         # A e B
        assert resumo["efd_originais_substituidas"] == 1
        assert any("retificadora" in a for a in resumo["avisos"])
