"""Exclusão de trabalho e remoção de lote, pela API.

São as duas operações destrutivas do sistema. O que este módulo prova:

* quem escreve não necessariamente apaga — analista é barrado;
* senha errada não apaga nada, e o trabalho continua lá;
* apagar leva junto lotes, arquivos e execuções;
* remover um lote não toca no arquivo do cliente em disco.
"""

import os

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
from tests.integracao.sessao import cabecalhos_de, usuario

SENHA = "Sistema2026cat"

# raiz própria deste módulo: a bateria de integração compartilha um banco só
CNPJ = "65432198000128"
RAIZ = "65432198"

CABECALHO = (
    f"|0000|015|0|01052021|31052021|EMPRESA DA EXCLUSAO|{CNPJ}||SP"
    "|9030138187|3550308||||"
)
C100 = (
    "|C100|0|0|F001|55|00|001|44623"
    "|41210511517841000278550010000446231411953289"
    "|01052021|01052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|"
)


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    repo = UsuarioRepositorioSql(s)
    senhas = SenhasArgon2(obter_config().senha_pimenta)
    # DEV, e não GESTOR, de propósito: a bateria de integração compartilha um
    # banco só, e um dono a mais furaria a salvaguarda do mínimo de três que
    # o módulo de usuários testa. DEV tem a mesma capacidade de excluir e não
    # conta como dono. Que o GESTOR também possa está provado em unidade.
    repo.criar(usuario="exc_dono", email="exc.dono@bms.local",
               nome_exibicao="Dona da Exclusão",
               senha_hash=senhas.gerar(SENHA), papel=Papel.DEV,
               cargo=Cargo.OUTRO)
    repo.criar(usuario="exc_analista", email="exc.analista@bms.local",
               nome_exibicao="Analista", senha_hash=senhas.gerar(SENHA),
               papel=Papel.ANALISTA, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


def entrar(cliente, quem):
    return cabecalhos_de(quem, SENHA)


@pytest.fixture(scope="module")
def dono(cliente):
    return entrar(cliente, "exc_dono")


@pytest.fixture(scope="module")
def analista(cliente):
    return entrar(cliente, "exc_analista")


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    p = tmp_path_factory.mktemp("base_exclusao")
    (p / "efd.txt").write_bytes(
        ("\r\n".join([CABECALHO, C100]) + "\r\n").encode("latin-1"))
    return str(p)


def _alocar(empresa_id: int, usuario: str) -> None:
    """Põe o usuário na empresa, direto no banco.

    Sem isso, o analista é barrado pelo escopo de empresa antes mesmo de a
    permissão de exclusão ser consultada — e o teste provaria a guarda errada.
    """
    from cat.infraestrutura.repositorios.banco import Sessao
    from cat.infraestrutura.repositorios.modelos import AlocacaoDB, UsuarioDB

    with Sessao() as s:
        alvo = s.query(UsuarioDB).filter_by(usuario=usuario).one()
        ja = s.query(AlocacaoDB).filter_by(
            usuario_id=alvo.id, empresa_id=empresa_id).first()
        if ja is None:
            s.add(AlocacaoDB(usuario_id=alvo.id, empresa_id=empresa_id,
                             papel_projeto="analista"))
            s.commit()


@pytest.fixture
def trabalho(cliente, dono, pasta):
    """Um trabalho novo a cada teste, já com um lote dentro."""
    empresas = cliente.get("/api/empresas", headers=dono).json()
    existente = next((e for e in empresas if e["cnpj_raiz"] == RAIZ), None)
    if existente:
        empresa_id = existente["id"]
    else:
        r = cliente.post("/api/empresas", headers=dono, json={
            "cnpj_raiz": RAIZ, "cnpj_matriz": CNPJ,
            "razao_social": "EMPRESA DA EXCLUSAO", "uf": "SP",
            "inscricao_estadual": "9030138187"})
        assert r.status_code == 201, r.text
        empresa_id = r.json()["id"]
    _alocar(empresa_id, "exc_analista")

    nome = f"Trabalho {os.urandom(4).hex()}"
    r = cliente.post("/api/projetos", headers=dono, json={
        "empresa_id": empresa_id, "frente": "cat42", "nome": nome,
        "competencia_ini": "2021-05-01", "competencia_fim": "2021-05-01",
        "observacao": None})
    assert r.status_code == 201, r.text
    projeto_id = r.json()["id"]

    r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=dono,
                     json={"pasta": pasta, "observacao": None})
    assert r.status_code == 201, r.text
    return projeto_id, r.json()["id"]


class TestQuemPodeApagar:
    def test_analista_e_barrado(self, cliente, analista, trabalho):
        projeto_id, _ = trabalho
        r = cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                            headers=analista, json={"senha": SENHA})
        assert r.status_code == 403
        assert "permissão" in r.json()["detail"]
        # e o trabalho continua lá
        assert cliente.get(f"/api/projetos/{projeto_id}",
                           headers=analista).status_code == 200

    def test_analista_nao_ve_nem_a_previa(self, cliente, analista, trabalho):
        projeto_id, _ = trabalho
        r = cliente.get(f"/api/projetos/{projeto_id}/exclusao", headers=analista)
        assert r.status_code == 403

    def test_sem_token_nao_entra(self, cliente, trabalho):
        projeto_id, _ = trabalho
        r = cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                            json={"senha": SENHA})
        assert r.status_code == 401


class TestSenhaNaConfirmacao:
    def test_senha_errada_nao_apaga(self, cliente, dono, trabalho):
        projeto_id, _ = trabalho
        r = cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                            headers=dono, json={"senha": "senha errada"})
        assert r.status_code == 403
        assert "não foi apagado" in r.json()["detail"]
        assert cliente.get(f"/api/projetos/{projeto_id}",
                           headers=dono).status_code == 200

    def test_senha_errada_nao_bloqueia_o_login(self, cliente, dono, trabalho):
        # errar a confirmação não pode trancar a pessoa fora do sistema
        projeto_id, _ = trabalho
        for _ in range(6):
            cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                            headers=dono, json={"senha": "errada"})
        # o login mora na API em C#; o que importa aqui é o estado que ele lê
        dono_agora = usuario("exc_dono")
        assert dono_agora.tentativas_falhas == 0
        dono_agora.garantir_que_pode_entrar()

    def test_senha_vazia_e_recusada(self, cliente, dono, trabalho):
        projeto_id, _ = trabalho
        r = cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                            headers=dono, json={"senha": ""})
        assert r.status_code == 422    # o contrato exige senha não vazia


class TestApagar:
    def test_a_previa_diz_o_que_some(self, cliente, dono, trabalho):
        projeto_id, _ = trabalho
        r = cliente.get(f"/api/projetos/{projeto_id}/exclusao", headers=dono)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["lotes"] == 1
        assert corpo["arquivos"] == 1
        assert corpo["empresa"] == "EMPRESA DA EXCLUSAO"

    def test_apaga_o_trabalho_e_o_que_pendura_nele(
        self, cliente, dono, trabalho
    ):
        projeto_id, _ = trabalho
        r = cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                            headers=dono, json={"senha": SENHA})
        assert r.status_code == 200, r.text
        assert r.json()["lotes"] == 1

        assert cliente.get(f"/api/projetos/{projeto_id}",
                           headers=dono).status_code == 404
        assert cliente.get(f"/api/projetos/{projeto_id}/lotes",
                           headers=dono).status_code == 404
        ids = [p["id"] for p in cliente.get("/api/projetos",
                                            headers=dono).json()]
        assert projeto_id not in ids

    def test_a_empresa_continua(self, cliente, dono, trabalho):
        # outros trabalhos da mesma empresa não podem ser levados junto
        projeto_id, _ = trabalho
        cliente.request("DELETE", f"/api/projetos/{projeto_id}",
                        headers=dono, json={"senha": SENHA})
        raizes = [e["cnpj_raiz"] for e in cliente.get("/api/empresas",
                                                      headers=dono).json()]
        assert RAIZ in raizes

    def test_trabalho_inexistente(self, cliente, dono):
        r = cliente.request("DELETE", "/api/projetos/999999",
                            headers=dono, json={"senha": SENHA})
        assert r.status_code == 404


class TestRemoverLote:
    def test_remove_e_a_lista_esvazia(self, cliente, dono, trabalho):
        projeto_id, lote_id = trabalho
        r = cliente.delete(f"/api/projetos/{projeto_id}/lotes/{lote_id}",
                           headers=dono)
        assert r.status_code == 200, r.text
        assert r.json()["arquivos"] == 1
        assert cliente.get(f"/api/projetos/{projeto_id}/lotes",
                           headers=dono).json() == []

    def test_o_arquivo_do_cliente_nao_e_tocado(
        self, cliente, dono, trabalho, pasta
    ):
        # o lote é o registro de onde os arquivos estão, não uma cópia deles
        projeto_id, lote_id = trabalho
        cliente.delete(f"/api/projetos/{projeto_id}/lotes/{lote_id}",
                       headers=dono)
        assert os.path.isfile(os.path.join(pasta, "efd.txt"))

    def test_analista_pode_remover_lote(self, cliente, analista, trabalho):
        # desfazer uma importação não é o mesmo que apagar meses de trabalho
        projeto_id, lote_id = trabalho
        r = cliente.delete(f"/api/projetos/{projeto_id}/lotes/{lote_id}",
                           headers=analista)
        assert r.status_code == 200

    def test_lote_de_outro_trabalho_da_404(self, cliente, dono, trabalho):
        _, lote_id = trabalho
        r = cliente.delete(f"/api/projetos/999999/lotes/{lote_id}",
                           headers=dono)
        assert r.status_code == 404

    def test_a_etapa_volta_a_pendente_sem_lote(self, cliente, dono, trabalho):
        projeto_id, lote_id = trabalho
        cliente.delete(f"/api/projetos/{projeto_id}/lotes/{lote_id}",
                       headers=dono)
        d = cliente.get(f"/api/projetos/{projeto_id}", headers=dono).json()
        etapa = next(e for e in d["etapas"] if e["chave"] == "importar")
        assert etapa["situacao"] == "pendente"
