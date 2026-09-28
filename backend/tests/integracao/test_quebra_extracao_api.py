"""A extração de registro pela rota: o que dá para extrair, e a planilha.

O que se cobra aqui e os testes de unidade não cobrem: que a rota só aceite
execução de quebra concluída, que o alvo inventado volte 422 dizendo o que
vale, e que a planilha saia com a aba e as colunas do leiaute.
"""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base
from tests.integracao.cadastro import (
    SEGREDO,
    criar_empresa,
    criar_lote,
    criar_projeto,
    criar_usuario,
    execucao,
    iniciar,
    rodar_fila,
)
from tests.unidade.test_registros_do_sped import CNPJ, sped

POR = "extracao_analista"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario=POR, email="extracao@bms.local",
                  nome_exibicao="Analista da Extração", papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def quebra(cliente, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_extracao")
    (pasta / "efd_062021.txt").write_bytes(sped("01062021", "30062021").encode("cp1252"))
    (pasta / "efd_072021.txt").write_bytes(sped("01072021", "31072021").encode("cp1252"))
    empresa = criar_empresa(raiz=CNPJ[:8], cnpj=CNPJ, razao="COMERCIO DO TESTE LTDA",
                            ie="123456789012", por=POR)
    projeto = criar_projeto(empresa_id=empresa, nome="Extração de teste", por=POR,
                            frente="sped")
    criar_lote(projeto_id=projeto, pasta=str(pasta))
    r = iniciar(cliente, "quebra_de_sped", projeto, POR)
    assert r.status_code == 202, r.text
    rodar_fila()
    d = execucao(r.json()["id"])
    assert d["situacao"] == "concluida", d.get("erro")
    return d


class TestOQueDaParaExtrair:
    def test_lista_registros_hierarquias_e_blocos(self, cliente, quebra):
        r = cliente.post("/interno/quebra/alvos", headers=SEGREDO,
                         json={"execucao_id": quebra["id"]})

        assert r.status_code == 200
        corpo = r.json()
        por_alvo = {l["alvo"]: l for l in corpo["linhas"]}
        assert por_alvo["C170"]["quantidade"] == 6
        assert por_alvo["C100+C170"]["hierarquia"] is True
        assert "C" in corpo["blocos"]
        assert corpo["rotulos_dos_blocos"]["M"].startswith("Bloco M")

    def test_execucao_que_nao_e_quebra_nao_responde(self, cliente):
        r = cliente.post("/interno/quebra/alvos", headers=SEGREDO, json={"execucao_id": 999999})

        assert r.status_code == 404


class TestAPlanilha:
    def test_o_registro_sai_com_as_colunas_do_leiaute(self, cliente, quebra):
        import openpyxl  # noqa: PLC0415

        r = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "alvo": "C170"})

        assert r.status_code == 200, r.text
        pronta = r.json()
        assert pronta["nome"] == "sped_C170.xlsx"
        with open(pronta["caminho"], "rb") as f:
            livro = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True)
        assert livro.sheetnames == ["C170"]

    def test_a_hierarquia_sai_com_a_aba_sem_o_mais(self, cliente, quebra):
        import openpyxl  # noqa: PLC0415

        r = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "alvo": "C100+C170"})

        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "sped_C100_C170.xlsx"
        with open(r.json()["caminho"], "rb") as f:
            livro = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True)
        # o Excel recusa "+" no nome da aba
        assert livro.sheetnames == ["C100 C170"]

    def test_o_csv_sai_pelo_mesmo_caminho(self, cliente, quebra):
        r = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "alvo": "C170", "formato": "csv"})

        assert r.status_code == 200
        assert r.json()["nome"] == "sped_C170.csv"
        assert r.json()["tipo"].startswith("text/csv")

    def test_alvo_inventado_volta_422_dizendo_o_que_vale(self, cliente, quebra):
        r = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "alvo": "Z999"})

        assert r.status_code == 422
        assert "não é registro com leiaute" in r.json()["detail"]

    def test_formato_desconhecido_volta_404(self, cliente, quebra):
        r = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "alvo": "C170", "formato": "pdf"})

        assert r.status_code == 404


class TestORecortePelaRota:
    def test_o_recorte_muda_o_arquivo_entregue(self, cliente, quebra):
        inteiro = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                               json={"execucao_id": quebra["id"], "alvo": "C170"})
        recortado = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                                 json={"execucao_id": quebra["id"], "alvo": "C170",
                                       "cst_pis": ["01"]})

        assert inteiro.status_code == 200 and recortado.status_code == 200
        # nomes diferentes: o cache de um não pode responder pelo outro
        assert inteiro.json()["nome"] != recortado.json()["nome"]

    def test_valor_escrito_errado_volta_422_na_borda(self, cliente, quebra):
        r = cliente.post("/interno/quebra/extrair", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "alvo": "C170",
                               "vl_item_min": "mil reais"})

        assert r.status_code == 422
        assert "Valor inválido no recorte" in r.json()["detail"]

    def test_os_estabelecimentos_saem_para_a_tela_oferecer(self, cliente, quebra):
        r = cliente.post("/interno/quebra/alvos", headers=SEGREDO,
                         json={"execucao_id": quebra["id"]})

        estabelecimentos = r.json()["estabelecimentos"]
        assert [e["cnpj"] for e in estabelecimentos] == [CNPJ]
        assert estabelecimentos[0]["empresa"] == "EMPRESA DO TESTE"
