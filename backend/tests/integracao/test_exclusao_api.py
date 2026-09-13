"""Remoção de lote, pela API do motor.

Tirar um lote do trabalho desfaz a importação, não o dado do cliente: o
arquivo continua no servidor de arquivos. O que este módulo prova:

* remover um lote não toca no arquivo do cliente em disco;
* quem escreve pode desfazer uma importação;
* sem lote com base, a etapa de importar deixa de estar concluída.

A exclusão do trabalho inteiro — a outra operação destrutiva, que pede a
senha — mora na API em C# desde 13/09/2026, com os testes em
api/tests/Cat.Api.Testes/TrabalhosTestes.cs.
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
from tests.integracao.sessao import cabecalhos_de
from tests.integracao.cadastro import criar_empresa, criar_projeto, tem_base

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
    empresa_id = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DA EXCLUSAO",
                               ie="9030138187", por="exc_dono")
    _alocar(empresa_id, "exc_analista")
    projeto_id = criar_projeto(empresa_id=empresa_id,
                               nome=f"Trabalho {os.urandom(4).hex()}", por="exc_dono")

    r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=dono,
                     json={"pasta": pasta, "observacao": None})
    assert r.status_code == 201, r.text
    return projeto_id, r.json()["id"]


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

    def test_sem_lote_o_trabalho_fica_sem_base(self, cliente, dono, trabalho):
        projeto_id, lote_id = trabalho
        cliente.delete(f"/api/projetos/{projeto_id}/lotes/{lote_id}",
                       headers=dono)
        # a etapa "importar" é calculada no C# a partir disto: sem base, pendente
        assert not tem_base(projeto_id)
