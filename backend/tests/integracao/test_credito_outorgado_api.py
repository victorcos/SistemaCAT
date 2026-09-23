"""O crédito outorgado ponta a ponta: filtro → varredura → produtos → planilha.

O que os testes de unidade não cobrem e aqui se cobra: que a etapa **se recuse
a rodar** sem filtro em vez de varrer para nada, que o filtro gravado seja o
que a rodada usa, que a tela consiga ler os produtos capturados, e que pedir a
lista de descartados de uma rodada que não os guardou dê uma resposta que diga
o que fazer — e não "rode de novo".

Os XML são os mesmos do teste de unidade da varredura: repeti-los aqui só
criaria uma segunda cópia para divergir.
"""

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
    planilha,
    rodar_fila,
)
from tests.unidade.test_credito_outorgado import (
    CHAVE_CUPOM,
    CHAVE_DOIS,
    CHAVE_UM,
    CNPJ_EMITENTE,
    cupom,
    det,
    nfe,
)

POR = "outorgado_analista"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario=POR, email="outorgado@bms.local",
                  nome_exibicao="Analista do Outorgado", papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def projeto_id(cliente, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_outorgado")
    (pasta / "nota1.xml").write_bytes(
        nfe(CHAVE_UM,
            det(1, "P01", "PAO FRANCES", "19059090", "10.00")
            + det(2, "P02", "PAO DE QUEIJO CONGELADO", "21069090", "25.50")
            + det(3, "X01", "DETERGENTE 500ML", "34022000", "7.00")))
    (pasta / "nota2.xml").write_bytes(nfe(CHAVE_DOIS, det(1, "P01", "PAO FRANCES", "19059090", "8.25")))
    (pasta / "cupom.xml").write_bytes(cupom(CHAVE_CUPOM, det(1, "P03", "PAO DOCE", "19059090", "3.75")))
    empresa = criar_empresa(raiz=CNPJ_EMITENTE[:8], cnpj=CNPJ_EMITENTE,
                            razao="COMERCIO DO TESTE LTDA", ie="123456789012", por=POR)
    projeto = criar_projeto(empresa_id=empresa, nome="Crédito outorgado de teste", por=POR)
    criar_lote(projeto_id=projeto, pasta=str(pasta))
    return projeto


def _gravar_filtro(cliente, projeto_id, **campos):
    corpo = {"projeto_id": projeto_id, "ncms": [], "termos": [], "sem_filtro": False,
             "guardar_descartados": False, **campos}
    return cliente.put("/interno/credito-outorgado/filtro", headers=SEGREDO, json=corpo)


class TestOFiltro:
    def test_trabalho_sem_filtro_responde_vazio_e_nao_erro(self, cliente, projeto_id):
        r = cliente.post("/interno/credito-outorgado/filtro", headers=SEGREDO,
                         json={"projeto_id": projeto_id})

        assert r.status_code == 200
        assert r.json()["termos"] == []

    def test_sem_termo_a_etapa_se_recusa_a_rodar(self, cliente, projeto_id):
        """Varrer 120 mil arquivos para entregar lista vazia não é resultado."""
        r = iniciar(cliente, "credito_outorgado", projeto_id, POR)

        assert r.status_code == 422
        assert "termo de descrição" in r.json()["detail"]

    def test_o_dominio_normaliza_o_que_a_tela_manda(self, cliente, projeto_id):
        r = _gravar_filtro(cliente, projeto_id, ncms=["1905.90", "1905.90"], termos=[" pao ", "PAO"])

        assert r.status_code == 200
        assert r.json()["ncms"] == ["190590"]
        assert r.json()["termos"] == ["PAO"]


@pytest.fixture(scope="module")
def rodada(cliente, projeto_id):
    _gravar_filtro(cliente, projeto_id, ncms=["190590"], termos=["PAO"])
    r = iniciar(cliente, "credito_outorgado", projeto_id, POR)
    assert r.status_code == 202, r.text
    rodar_fila()
    d = execucao(r.json()["id"])
    assert d["situacao"] == "concluida", d.get("erro")
    return d


class TestARodada:
    def test_separa_o_que_entra_no_beneficio(self, rodada):
        resumo = rodada["resumo"]

        assert resumo["documentos"] == 3
        assert resumo["itens"] == 5
        assert resumo["elegiveis"] == 4
        # 10,00 + 25,50 + 8,25 + 3,75
        assert resumo["centavos_elegiveis"] == 4750

    def test_o_filtro_que_produziu_a_lista_fica_gravado_com_ela(self, rodada):
        assert rodada["resumo"]["filtro"] == {
            "ncms": ["190590"], "termos": ["PAO"], "sem_filtro": False}


class TestATela:
    def test_os_produtos_vem_agrupados_e_do_maior_para_o_menor(self, cliente, rodada):
        r = cliente.post("/interno/credito-outorgado/produtos", headers=SEGREDO,
                         json={"execucao_id": rodada["id"]})

        assert r.status_code == 200
        corpo = r.json()
        # P01 em duas notas, P02 e P03 numa cada
        assert corpo["total"] == 3
        assert corpo["itens"] == 4
        assert corpo["valor"] == "47.50"
        assert [l["codigo"] for l in corpo["linhas"]] == ["P02", "P01", "P03"]

    def test_o_motivo_separa_o_que_a_ncm_confirmou(self, cliente, rodada):
        r = cliente.post("/interno/credito-outorgado/produtos", headers=SEGREDO,
                         json={"execucao_id": rodada["id"], "busca": "QUEIJO"})
        linha = r.json()["linhas"][0]

        # a NCM do pão de queijo não está cadastrada: entra só pela descrição
        assert linha["motivo"] == "DESCRIÇÃO"

    def test_os_itens_de_um_produto_saem_com_as_notas(self, cliente, rodada):
        r = cliente.post("/interno/credito-outorgado/itens", headers=SEGREDO,
                         json={"execucao_id": rodada["id"], "codigo": "P01"})
        corpo = r.json()

        assert corpo["total"] == 2
        assert {l["chave"] for l in corpo["linhas"]} == {CHAVE_UM, CHAVE_DOIS}
        assert corpo["linhas"][0]["emissao"] == "2021-05-04"

    def test_pedir_descartados_que_a_rodada_nao_guardou_diz_o_que_fazer(self, cliente, rodada):
        r = cliente.post("/interno/credito-outorgado/produtos", headers=SEGREDO,
                         json={"execucao_id": rodada["id"], "descartados": True})

        assert r.status_code == 410
        assert "guardar os descartados" in r.json()["detail"]


class TestAPlanilha:
    def test_a_lista_do_beneficio_sai_em_xlsx(self, cliente, rodada):
        import openpyxl  # noqa: PLC0415
        import io  # noqa: PLC0415

        p = planilha(cliente, "credito_outorgado", rodada["id"], "elegiveis")

        assert p.status_code == 200
        livro = openpyxl.load_workbook(io.BytesIO(p.content), read_only=True)
        assert livro.sheetnames == ["Crédito Outorgado"]

    def test_a_dos_descartados_recusa_com_o_motivo_certo(self, cliente, rodada):
        p = planilha(cliente, "credito_outorgado", rodada["id"], "descartados")

        assert p.status_code == 410
        assert "guardar os descartados" in p.json()["detail"]
