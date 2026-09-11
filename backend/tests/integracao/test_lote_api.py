"""Lote de arquivos pela API, ponta a ponta.

O que este módulo prova é a segregação que motivou a tela: importar base num
trabalho que já existe **não** passa pelo cadastro, não cria empresa e não cria
projeto. E o mesmo arquivo não entra duas vezes.
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

SENHA = "Sistema2026cat"

# Raiz própria deste módulo. A bateria de integração compartilha um banco
# só, e a raiz 50948371 já é usada por test_auth_api — cadastrar de novo
# daria 409 no setup.
ICMS_IPI = (
    "|0000|018|0|01012025|31012025|EMPRESA DO LOTE LTDA|77665544000105||SP"
    "|407048962113|3550308|||A|0|"
)
CONTRIBUICOES = (
    "|0000|006|0|||01062021|30062021|EMPRESA DO LOTE LTDA"
    "|77665544000105|SP|3550308||00|2|"
)
DE_OUTRA_EMPRESA = (
    "|0000|018|0|01012025|31012025|OUTRA EMPRESA LTDA|11222333000181||MG"
    "|123456789|3106200|||A|0|"
)


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    repo = UsuarioRepositorioSql(s)
    senhas = SenhasArgon2(obter_config().senha_pimenta)
    repo.criar(usuario="lote_analista", email="lote.analista@bms.local",
               nome_exibicao="Analista do Lote",
               senha_hash=senhas.gerar(SENHA), papel=Papel.DEV,
               cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    r = cliente.post("/api/auth/token",
                     data={"username": "lote_analista", "password": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def projeto_id(cliente, cabecalhos):
    r = cliente.post("/api/empresas", headers=cabecalhos, json={
        "cnpj_raiz": "77665544", "cnpj_matriz": "77665544000105",
        "razao_social": "EMPRESA DO LOTE LTDA", "uf": "SP",
        "inscricao_estadual": "407048962113",
    })
    assert r.status_code == 201, r.text
    empresa = r.json()["id"]

    r = cliente.post("/api/projetos", headers=cabecalhos, json={
        "empresa_id": empresa, "frente": "cat42", "nome": "CAT 42 de teste",
        "competencia_ini": "2025-01-01", "competencia_fim": "2025-12-01",
        "observacao": None,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def escrever(pasta, nome, conteudo):
    (pasta / nome).write_bytes(conteudo.encode("latin-1"))


@pytest.fixture(scope="module")
def pasta_com_base(tmp_path_factory):
    """A MESMA pasta para todos os testes do módulo.

    Precisa ser de módulo: parte do que se prova aqui é que a segunda
    importação da mesma pasta é recusada, e com pasta nova a cada teste não
    haveria segunda vez.
    """
    pasta = tmp_path_factory.mktemp("base_do_trabalho")
    escrever(pasta, "boa_012025.txt", ICMS_IPI)
    escrever(pasta, "contribuicoes.txt", CONTRIBUICOES)
    escrever(pasta, "intruso.txt", DE_OUTRA_EMPRESA)
    return str(pasta)


class TestConferirAntesDeGravar:
    def test_diz_o_que_ha_sem_criar_nada(
        self, cliente, cabecalhos, projeto_id, pasta_com_base
    ):
        antes = len(cliente.get("/api/empresas", headers=cabecalhos).json())

        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         headers=cabecalhos, json={"pasta": pasta_com_base})
        assert r.status_code == 200, r.text
        corpo = r.json()

        assert corpo["total_arquivos"] == 2       # o intruso não conta
        assert corpo["arquivos_uteis"] == 1       # só a EFD ICMS/IPI
        assert corpo["de_outra_empresa"] == 1
        assert corpo["serve"] is True
        assert corpo["competencia_ini"] == "2025-01-01"

        # conferir não cria empresa: é o que separa esta tela do cadastro
        assert len(cliente.get("/api/empresas", headers=cabecalhos).json()) == antes
        assert cliente.get(f"/api/projetos/{projeto_id}/lotes",
                           headers=cabecalhos).json() == []

    def test_avisa_o_que_ficou_de_fora(
        self, cliente, cabecalhos, projeto_id, pasta_com_base
    ):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         headers=cabecalhos, json={"pasta": pasta_com_base})
        avisos = " ".join(r.json()["avisos"])
        assert "outra empresa" in avisos

    def test_pasta_inexistente_explica(self, cliente, cabecalhos, projeto_id):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         headers=cabecalhos,
                         json={"pasta": "Z:/pasta/que/nao/existe"})
        assert r.status_code == 422
        assert "não existe" in r.json()["detail"]

    def test_trabalho_inexistente_da_404(self, cliente, cabecalhos, tmp_path):
        r = cliente.post("/api/projetos/999999/lotes/inspecionar",
                         headers=cabecalhos, json={"pasta": str(tmp_path)})
        assert r.status_code == 404


class TestRegistrar:
    def test_registra_e_aparece_na_lista(
        self, cliente, cabecalhos, projeto_id, pasta_com_base
    ):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": pasta_com_base,
                               "observacao": "primeira remessa da empresa"})
        assert r.status_code == 201, r.text
        lote = r.json()
        assert lote["total_arquivos"] == 2
        assert lote["arquivos_uteis"] == 1
        assert lote["observacao"] == "primeira remessa da empresa"
        assert any(c["tipo"] == "sped_icms_ipi" for c in lote["contagens"])

        lista = cliente.get(f"/api/projetos/{projeto_id}/lotes",
                            headers=cabecalhos).json()
        assert [l["id"] for l in lista] == [lote["id"]]

    def test_a_etapa_de_importar_so_conclui_com_base(
        self, cliente, cabecalhos, projeto_id
    ):
        # o projeto já existia antes deste lote, e a etapa não estava concluída;
        # agora que há base, está
        d = cliente.get(f"/api/projetos/{projeto_id}", headers=cabecalhos).json()
        etapa = next(e for e in d["etapas"] if e["chave"] == "importar")
        assert etapa["situacao"] == "concluida"

    def test_a_mesma_pasta_nao_entra_duas_vezes(
        self, cliente, cabecalhos, projeto_id, pasta_com_base
    ):
        # o mesmo SPED contado duas vezes dobraria movimento na apuração
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": pasta_com_base, "observacao": None})
        assert r.status_code == 409
        assert "já estão neste trabalho" in r.json()["detail"]

    def test_conferir_avisa_o_que_ja_entrou(
        self, cliente, cabecalhos, projeto_id, pasta_com_base
    ):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         headers=cabecalhos, json={"pasta": pasta_com_base})
        assert r.json()["ja_no_trabalho"] == 2

    def test_pasta_sem_nada_util_e_recusada(
        self, cliente, cabecalhos, projeto_id, tmp_path
    ):
        # período diferente do que os outros testes já importaram: com o
        # mesmo conteúdo, o sistema a barraria como cópia (409) antes de
        # chegar à recusa por "nada alimenta a CAT" que este teste prova
        escrever(tmp_path, "so_contribuicoes.txt",
                 CONTRIBUICOES.replace("01062021|30062021", "01072021|31072021"))
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                         json={"pasta": str(tmp_path), "observacao": None})
        assert r.status_code == 422
        assert "alimenta a CAT 42" in r.json()["detail"]


class TestAcesso:
    def test_sem_token_nao_entra(self, cliente, projeto_id, tmp_path):
        r = cliente.post(f"/api/projetos/{projeto_id}/lotes/inspecionar",
                         json={"pasta": str(tmp_path)})
        assert r.status_code == 401
