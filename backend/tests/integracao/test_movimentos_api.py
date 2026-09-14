"""Histórico de movimentação pela API, ponta a ponta.

Encadeamento: lote → conferência → movimentos. A etapa recusa enquanto não
há conferência concluída, roda em linha própria (aqui, na hora), grava o
resumo, marca cada movimento com o que a conferência achou e entrega as
quatro planilhas. E o roteiro do projeto passa a mostrar a etapa concluída.
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
from tests.integracao.sessao import cabecalhos_de
from tests.integracao.cadastro import (
    conferir, criar_empresa, criar_lote, criar_projeto, execucao, execucoes, iniciar, planilha,
    rodar_fila, ultima_situacao,
)

SENHA = "Sistema2026cat"

# raiz própria deste módulo: a bateria compartilha um banco só
CNPJ = "77889900000166"
RAIZ = "77889900"

CHAVE_A = "35210577889900000166550010000010001000000010"
CHAVE_B = "35210577889900000166550010000010002000000020"

CABECALHO = (f"|0000|015|0|01052021|31052021|EMPRESA DOS MOVIMENTOS|{CNPJ}||SP"
             "|123456789012|3550308||||")
ITEM = "|0200|1000144|Iog Vidativa 160g|7898194090401||CX|00|04031000||04||18|1702200|"
C100_A = (f"|C100|0|1|F001|55|00|001|10001|{CHAVE_A}"
          "|01052021|01052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C170_A = ("|C170|1|1000144|Iogurte|10|CX|100,00|0|0|010|1403|300|100,00|18|18,00"
          "|150,00|18|9,00||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
C100_B = (f"|C100|0|1|F002|55|00|001|10002|{CHAVE_B}"
          "|02052021|02052021|50,00|2|0|0|50,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C170_B = ("|C170|1|1000144|Iogurte|5|CX|50,00|0|0|010|1403|300|50,00|18|9,00"
          "|75,00|18|4,50||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
H005 = "|H005|30042021|96,39|01|"
H010 = "|H010|1000144|CX|81|1,19|96,39|0|||1.1.20.01.01|96,39|"

XML_A = ('<?xml version="1.0" encoding="UTF-8"?>'
         f'<nfeProc><NFe><infNFe Id="NFe{CHAVE_A}">'
         f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>")


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="mov_analista", email="mov@bms.local",
        nome_exibicao="Analista dos Movimentos",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.DEV, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    return cabecalhos_de("mov_analista", SENHA)


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Duas entradas com item; XML só da primeira; inventário."""
    pasta = tmp_path_factory.mktemp("base_movimentos")
    (pasta / "efd.txt").write_bytes(("\r\n".join([
        CABECALHO, ITEM, C100_A, C170_A, C100_B, C170_B, H005, H010,
    ]) + "\r\n").encode("latin-1"))
    (pasta / f"{CHAVE_A}-nfe.xml").write_text(XML_A, encoding="utf-8")
    return str(pasta)


@pytest.fixture(scope="module")
def projeto_id(cliente, cabecalhos, base):
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DOS MOVIMENTOS",
                            ie="123456789012", por="mov_analista")
    projeto = criar_projeto(empresa_id=empresa, nome="Movimentos de teste",
                            por="mov_analista")
    criar_lote(projeto_id=projeto, pasta=base)
    return projeto


class TestOrdemDasEtapas:
    def test_recusa_sem_conferencia(self, cliente, cabecalhos, projeto_id):
        r = iniciar(cliente, "movimentos", projeto_id, "mov_analista")
        assert r.status_code == 422
        assert "conferência" in r.json()["detail"].lower()
        # recusada, não chegou a nascer rodada — a etapa segue bloqueada no C#
        assert ultima_situacao(projeto_id, "movimentos") is None


class TestFluxo:
    @pytest.fixture(scope="class", autouse=True)
    def _conferido(self, cliente, cabecalhos, projeto_id):
        assert conferir(cliente, projeto_id, "mov_analista")["situacao"] == "concluida"

    @pytest.fixture(scope="class")
    def execucao(self, cliente, cabecalhos, projeto_id):
        r = iniciar(cliente, "movimentos", projeto_id, "mov_analista")
        assert r.status_code == 202, r.text
        rodar_fila()
        d = execucao(r.json()["id"])
        assert d["situacao"] == "concluida", d.get("erro")
        return d

    def test_resumo(self, execucao):
        r = execucao["resumo"]
        assert r["documentos"] == 2
        assert r["documentos_com_item"] == 2
        assert r["movimentos"] == 2
        assert r["itens_cadastrados"] == 1
        assert r["inventarios"] == 1
        assert r["valor_em_estoque"] == "96.39"
        assert r["conferencia_usada"] is True
        # a nota A tem XML; a B ficou pendente na conferência
        assert {f["codigo"]: f["documentos"] for f in r["por_classificacao"]} == {
            "conferido": 1, "pendente": 1}
        assert any("1 movimento(s) são de documentos ainda pendentes" in a
                   for a in r["avisos"])

    def test_a_etapa_do_projeto_conclui(self, cliente, cabecalhos, projeto_id, execucao):
        assert ultima_situacao(projeto_id, "movimentos") == "concluida"

    def test_planilha_de_outra_etapa_nao_existe_por_esta_rota(self, cliente, projeto_id, execucao):
        # uma execução de conferência pedida pela lista de movimentos
        conferencia = execucoes(projeto_id, "conferencia")[0]
        r = planilha(cliente, "movimentos", conferencia["id"], "movimentos")
        assert r.status_code == 410

    def test_baixa_as_quatro_planilhas(self, cliente, cabecalhos, execucao):
        for qual in ("movimentos", "itens", "inventario", "analitico"):
            r = planilha(cliente, "movimentos", execucao["id"], qual)
            assert r.status_code == 200, (qual, r.text)
            assert r.content[:2] == b"PK"

    def test_baixa_as_quatro_em_csv(self, cliente, cabecalhos, execucao):
        """As quatro listas da movimentação também saem em csv.

        A do analítico é a que mais pede: numa base real desta casa deu 37,9
        milhões de documentos, e o xlsx precisaria quebrar em 43 abas."""
        for qual in ("movimentos", "itens", "inventario", "analitico"):
            r = planilha(cliente, "movimentos", execucao["id"], qual, formato="csv")
            assert r.status_code == 200, (qual, r.text)
            assert r.headers["content-type"].startswith("text/csv")
            assert r.content[:3] == b"\xef\xbb\xbf"
            assert r.headers["content-disposition"].endswith('.csv"')

    def test_filtro_por_classificacao_muda_o_arquivo(self, cliente, cabecalhos, execucao):
        inteira = planilha(cliente, "movimentos", execucao["id"], "movimentos")
        so_pendentes = planilha(cliente, "movimentos", execucao["id"], "movimentos", classificacoes="pendente")
        assert so_pendentes.status_code == 200
        assert "-pendente" in so_pendentes.headers["content-disposition"]
        assert len(so_pendentes.content) < len(inteira.content)

    def test_segunda_rodada_ao_mesmo_tempo_e_recusada(self, cliente, cabecalhos,
                                                       projeto_id, execucao, monkeypatch):
        # sem rodar a fila, a primeira fica "na fila" e a segunda bate em 409
        r1 = iniciar(cliente, "movimentos", projeto_id, "mov_analista")
        assert r1.status_code == 202
        r2 = iniciar(cliente, "movimentos", projeto_id, "mov_analista")
        assert r2.status_code == 409
        assert "em andamento" in r2.json()["detail"]
        rodar_fila()
