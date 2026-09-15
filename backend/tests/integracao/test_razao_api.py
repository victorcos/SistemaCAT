"""O razão pelo canal interno, ponta a ponta: lote → conferência → movimentos →
suportado → razão.

Uma mercadoria, iogurte, com duas entradas e uma venda de PDV:

    01/05 entrada CST 10 ....... 10 un, suportado 27,00 (destacado)
    02/05 entrada CST 60 ....... 5 un,  suportado 4,75  (relatório do cliente)
          saldo 15 un, R$ 31,75, unitário 2,11666…
    10/05 venda de PDV CST 60 .. 3 un, valor 30,00, alíquota 18%
          baixa 6,35; confronto 5,40; ressarcimento 0,95

A alface, isenta, só tem entrada: não tem saída com CST 60, não tem ficha.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base
from tests.integracao.cadastro import (
    SEGREDO,
    conferir, criar_empresa, criar_lote, criar_projeto, criar_usuario, execucao,
    iniciar, planilha, rodar_fila, ultima_situacao,
)

CNPJ = "44332211000105"
RAIZ = "44332211"
CHAVE_A = "35210544332211000105550010000030001000000010"
CHAVE_B = "35210544332211000105550010000030002000000020"

CABECALHO = (f"|0000|015|0|01052021|31052021|EMPRESA DO RAZAO|{CNPJ}||SP"
             "|123456789012|3550308||||")
ITEM = "|0200|1000144|Iog Vidativa 160g|7898194090401||CX|00|04031000||04||18|1702200|"
ITEM_ISENTO = "|0200|2000|Alface crespa|7890000000002||UN|00|07051100||04||0|1702200|"


def c100(ch: str, numero: int, valor: str) -> str:
    return (f"|C100|0|1|F{numero}|55|00|001|{numero}|{ch}"
            f"|0{numero % 10 or 1}052021|0{numero % 10 or 1}052021|{valor}|2|0|0|{valor}|9|0|0|0|0|0|0|0|0|0|0|0|0|")


C170_A = ("|C170|1|1000144|Iogurte|10|CX|100,00|0|0|010|1403|300|100,00|18|18,00"
          "|150,00|18|9,00||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
C170_B = ("|C170|1|1000144|Iogurte|5|CX|50,00|0|0|060|1403|300|0|0|0"
          "|0|0|0||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
C170_C = ("|C170|1|2000|Alface|3|UN|9,00|0|0|040|1102|300|0|0|0"
          "|0|0|0||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")

CABECALHO_MOVIMENTO = (
    "Código|Descricao|Código Barras|Trib|Dt Emissão|Número Dcto|Ent|"
    "Qtde;Unitária|Valor|BC ICMS|Valor ICMS|Valor BC ST;Informada|"
    "Valor ST;Informada|Valor FCP ST|CNPJ/CPF|UF|CFOP;Mvto|CST;ICMS|"
    "BC ICMS ST;XML|VR. ICMS ST;XML|ST integral|Chave DFe"
)
ENTRADA_B = ("1000144|Iogurte|789|0403|02/05/21|30002|1|5|50|0|0|0|0|0|"
             f"00176231110|SP|1.403|060|0|0|4,75|{CHAVE_B}")
VENDA_PDV = ("1000144|Iogurte|789|0403|10/05/21|0|1|3|30|0|0|0|0|0|"
             f"{CNPJ}|SP|5.405|060|0|0|0||001|Estoque / Venda De Produtos PDVs")


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="raz_analista", email="raz@bms.local",
                  nome_exibicao="Analista do Razão", papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def projeto_id(cliente, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_razao")
    datas = {CHAVE_A: "01052021", CHAVE_B: "02052021", "3" * 44: "03052021"}

    def c100_(ch, numero, valor):
        return (f"|C100|0|1|F{numero}|55|00|001|{numero}|{ch}|{datas[ch]}|{datas[ch]}|{valor}"
                "|2|0|0|" + valor + "|9|0|0|0|0|0|0|0|0|0|0|0|0|")

    chave_c = "35210544332211000105550010000030003000000030"
    datas[chave_c] = "03052021"
    (pasta / "efd.txt").write_bytes(("\r\n".join([
        CABECALHO, ITEM, ITEM_ISENTO,
        c100_(CHAVE_A, 30001, "100,00"), C170_A,
        c100_(CHAVE_B, 30002, "50,00"), C170_B,
        c100_(chave_c, 30003, "9,00"), C170_C,
    ]) + "\r\n").encode("latin-1"))
    (pasta / "entradas.txt").write_bytes(
        ("\r\n".join([CABECALHO_MOVIMENTO, ENTRADA_B]) + "\r\n").encode("latin-1"))
    (pasta / "saidas.txt").write_bytes(
        ("\r\n".join([CABECALHO_MOVIMENTO + "|Unidade|Descrição Tipo Dcto", VENDA_PDV])
         + "\r\n").encode("latin-1"))
    for ch in (CHAVE_A, CHAVE_B, chave_c):
        (pasta / f"{ch}-nfe.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<nfeProc><NFe><infNFe Id="NFe{ch}"><emit><CNPJ>{CNPJ}</CNPJ></emit>'
            "</infNFe></NFe></nfeProc>", encoding="utf-8")
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DO RAZAO",
                            ie="123456789012", por="raz_analista")
    projeto = criar_projeto(empresa_id=empresa, nome="Razão de teste", por="raz_analista")
    criar_lote(projeto_id=projeto, pasta=str(pasta))
    return projeto


def rodar(cliente, etapa: str, projeto_id: int) -> dict:
    r = iniciar(cliente, etapa, projeto_id, "raz_analista")
    assert r.status_code == 202, r.text
    rodar_fila()
    d = execucao(r.json()["id"])
    assert d["situacao"] == "concluida", d.get("erro")
    return d


class TestOrdemDasEtapas:
    def test_recusa_sem_apuracao_do_suportado(self, cliente, projeto_id):
        r = iniciar(cliente, "razao", projeto_id, "raz_analista")
        assert r.status_code == 422
        assert ultima_situacao(projeto_id, "razao") is None


class TestFluxo:
    @pytest.fixture(scope="class")
    def razao(self, cliente, projeto_id):
        assert conferir(cliente, projeto_id, "raz_analista")["situacao"] == "concluida"
        rodar(cliente, "movimentos", projeto_id)
        rodar(cliente, "st_suportado", projeto_id)
        return rodar(cliente, "razao", projeto_id)

    def test_a_ficha_fecha_com_a_conta_a_mao(self, razao):
        r = razao["resumo"]
        assert r["fichas"] == 1 and r["codigos_com_st"] == 1
        assert Decimal(r["ressarcimento"]) == Decimal("0.95")
        assert r["saidas_por_origem"] == {"relatorio": 1}
        enq = {e["codigo"]: e for e in r["por_enquadramento"]}
        assert enq["1"]["linhas"] == 1 and Decimal(enq["1"]["confronto"]) == Decimal("5.40")
        assert r["relatorios"]["so_de_entradas"] == 1
        assert r["iniciada_por"] == "Analista do Razão"

    def test_fichas_e_linhas_pelo_canal_interno(self, cliente, razao):
        f = cliente.post("/interno/razao/fichas", headers=SEGREDO, json={"execucao_id": razao["id"]})
        assert f.status_code == 200, f.text
        ficha = f.json()["linhas"][0]
        assert ficha["codigo"] == "1000144" and ficha["uf"] == "SP"
        assert ficha["descricao"] == "Iog Vidativa 160g"
        l = cliente.post("/interno/razao/ficha", headers=SEGREDO, json={
            "execucao_id": razao["id"], "cnpj": CNPJ, "codigo": "1000144"})
        assert [x["especie"] for x in l.json()["linhas"]] == ["entrada", "entrada", "saida"]

    def test_as_duas_planilhas(self, cliente, razao):
        for qual in ("ficha3", "fichas"):
            r = planilha(cliente, "razao", razao["id"], qual)
            assert r.status_code == 200, (qual, r.text)
            assert r.content[:2] == b"PK"

    def test_razao_de_outra_etapa_nao_existe(self, cliente, projeto_id, razao):
        from tests.integracao.cadastro import execucoes  # noqa: PLC0415
        movimentos = execucoes(projeto_id, "movimentos")[0]
        r = cliente.post("/interno/razao/fichas", headers=SEGREDO, json={"execucao_id": movimentos["id"]})
        assert r.status_code == 404
