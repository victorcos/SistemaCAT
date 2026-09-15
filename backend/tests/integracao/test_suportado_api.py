"""Apuração do ICMS suportado pelo canal interno, ponta a ponta.

Encadeamento: lote → conferência → movimentos → apuração. Três entradas, uma
de cada lado da cascata:

* nota A, CST 10 — ICMS e ST destacados: sai do próprio documento;
* nota B, CST 60 — EFD zerada, e o relatório do cliente informa 4,75 de ST
  retido antes: é o caso que obriga a etapa a existir;
* nota C, CST 40 — isento: não apurável, e **sem o que apurar**, não falta de
  dado.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import Base, ExecucaoDB
from tests.integracao.cadastro import (
    SEGREDO,
    conferir, criar_empresa, criar_lote, criar_projeto, criar_usuario, execucao,
    iniciar, planilha, rodar_fila, ultima_situacao, _id_de,
)

# raiz própria deste módulo: a bateria compartilha um banco só
CNPJ = "55443322000181"
RAIZ = "55443322"

CHAVE_A = "35210555443322000181550010000020001000000010"
CHAVE_B = "35210555443322000181550010000020002000000020"
CHAVE_C = "35210555443322000181550010000020003000000030"

CABECALHO = (f"|0000|015|0|01052021|31052021|EMPRESA DO SUPORTADO|{CNPJ}||SP"
             "|123456789012|3550308||||")
ITEM = "|0200|1000144|Iog Vidativa 160g|7898194090401||CX|00|04031000||04||18|1702200|"
ITEM_ISENTO = "|0200|2000|Alface crespa|7890000000002||UN|00|07051100||04||0|1702200|"


def c100(ch: str, numero: int, valor: str) -> str:
    return (f"|C100|0|1|F{numero}|55|00|001|{numero}|{ch}"
            f"|01052021|01052021|{valor}|2|0|0|{valor}|9|0|0|0|0|0|0|0|0|0|0|0|0|")


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
# a nota B no relatório do cliente: CST 60 com 4,75 de ST retido antes
RELATORIO_B = ("1000144|Iogurte|789|0403|02/05/21|20002|1|5|50|0|0|0|0|0|"
               f"00176231110|SP|1.403|060|0|0|4,75|{CHAVE_B}")


def xml_de(ch: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<nfeProc><NFe><infNFe Id="NFe{ch}">'
            f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>")


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="sup_analista", email="sup@bms.local",
                  nome_exibicao="Analista do Suportado",
                  papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_suportado")
    (pasta / "efd.txt").write_bytes(("\r\n".join([
        CABECALHO, ITEM, ITEM_ISENTO,
        c100(CHAVE_A, 20001, "100,00"), C170_A,
        c100(CHAVE_B, 20002, "50,00"), C170_B,
        c100(CHAVE_C, 20003, "9,00"), C170_C,
    ]) + "\r\n").encode("latin-1"))
    (pasta / "movimento.txt").write_bytes(
        ("\r\n".join([CABECALHO_MOVIMENTO, RELATORIO_B]) + "\r\n").encode("latin-1"))
    for ch in (CHAVE_A, CHAVE_C):
        (pasta / f"{ch}-nfe.xml").write_text(xml_de(ch), encoding="utf-8")
    return str(pasta)


@pytest.fixture(scope="module")
def projeto_id(cliente, base):
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DO SUPORTADO",
                            ie="123456789012", por="sup_analista")
    projeto = criar_projeto(empresa_id=empresa, nome="Suportado de teste",
                            por="sup_analista")
    criar_lote(projeto_id=projeto, pasta=base)
    return projeto


def cancelar(cliente, execucao_id: int, por: str = "sup_analista"):
    return cliente.post(f"/interno/execucoes/{execucao_id}/cancelar", headers=SEGREDO,
                        json={"usuario_id": _id_de(por)})


def linhas(cliente, execucao_id: int, **pedido):
    return cliente.post("/interno/suportado/linhas", headers=SEGREDO,
                        json={"execucao_id": execucao_id, **pedido})


class TestOrdemDasEtapas:
    def test_recusa_sem_movimentacao(self, cliente, projeto_id):
        r = iniciar(cliente, "st_suportado", projeto_id, "sup_analista")
        assert r.status_code == 422
        assert "movimentos" in r.json()["detail"].lower()
        assert ultima_situacao(projeto_id, "st_suportado") is None


class TestFluxo:
    @pytest.fixture(scope="class", autouse=True)
    def _movimentos(self, cliente, projeto_id):
        assert conferir(cliente, projeto_id, "sup_analista")["situacao"] == "concluida"
        r = iniciar(cliente, "movimentos", projeto_id, "sup_analista")
        assert r.status_code == 202, r.text
        rodar_fila()
        assert execucao(r.json()["id"])["situacao"] == "concluida"

    @pytest.fixture(scope="class")
    def apuracao(self, cliente, projeto_id, _movimentos):
        r = iniciar(cliente, "st_suportado", projeto_id, "sup_analista")
        assert r.status_code == 202, r.text
        rodar_fila()
        d = execucao(r.json()["id"])
        assert d["situacao"] == "concluida", d.get("erro")
        return d

    def test_a_cascata_fecha_os_tres_casos(self, apuracao):
        r = apuracao["resumo"]
        assert r["versao"] == 2
        assert r["itens"] == 3
        assert r["apurados"] == 2
        assert Decimal(r["valor_total"]) == Decimal("31.75")        # 27 + 4,75
        assert Decimal(r["valor_documental"]) == Decimal("31.75")
        fontes = {f["codigo"]: f["itens"] for f in r["por_fonte"]}
        assert fontes == {"documento": 1, "informado_pelo_fornecedor": 1,
                          "base_e_aliquota": 0, "nao_apuravel": 1}

    def test_isento_nao_e_falta_de_dado(self, apuracao):
        r = apuracao["resumo"]
        assert r["por_pendencia"] == {"sem_o_que_apurar": 1, "falta_dado": 0}
        assert r["cst_sem_o_que_apurar"] == {"cst": "40", "itens": 1}

    def test_quebras_e_log_vao_no_resumo(self, apuracao):
        r = apuracao["resumo"]
        assert r["estabelecimentos"] == 1
        assert [c["competencia"] for c in r["por_competencia"]] == ["2021-05"]
        assert {c["cst"] for c in r["por_cst"]} == {"10", "60", "40"}
        assert r["iniciada_por"] == "Analista do Suportado"
        assert r["relatorios"]["itens"] == 1
        assert any("Concluída" in e["texto"] for e in r["log"])

    def test_etapa_do_projeto_conclui(self, projeto_id, apuracao):
        assert ultima_situacao(projeto_id, "st_suportado") == "concluida"

    def test_analitico_por_documento_e_por_item(self, cliente, apuracao):
        r = linhas(cliente, apuracao["id"], escopo="documento")
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 3
        b = next(d for d in r.json()["linhas"] if d["chave"] == CHAVE_B)
        assert b["fonte"] == "informado_pelo_fornecedor"
        assert b["filhos"][0]["descricao"] == "Iog Vidativa 160g"

        r = linhas(cliente, apuracao["id"], escopo="item", fonte="nao_apuravel")
        assert [i["chave"] for i in r.json()["linhas"]] == [CHAVE_C]

    def test_analitico_recusa_escopo_desconhecido(self, cliente, apuracao):
        assert linhas(cliente, apuracao["id"], escopo="tudo").status_code == 422

    def test_analitico_de_outra_etapa_nao_existe(self, cliente, projeto_id, apuracao):
        with Sessao() as s:
            outra = s.query(ExecucaoDB).filter_by(projeto_id=projeto_id,
                                                  etapa="movimentos").first()
        assert linhas(cliente, outra.id).status_code == 404

    def test_planilha_inteira_e_so_uma_fonte(self, cliente, apuracao):
        inteira = planilha(cliente, "st_suportado", apuracao["id"], "suportado")
        assert inteira.status_code == 200, inteira.text
        assert inteira.content[:2] == b"PK"
        csv = planilha(cliente, "st_suportado", apuracao["id"], "suportado",
                       formato="csv", classificacoes="nao_apuravel")
        assert csv.status_code == 200, csv.text
        texto = csv.content.decode("utf-8-sig")
        assert "Não apurável" in texto and "Sem o que apurar" in texto
        assert CHAVE_B not in texto
        assert len(texto.strip().splitlines()) == 2      # cabeçalho + nota C


class TestCancelar:
    def test_na_fila_cancela_na_hora_e_libera_nova_rodada(self, cliente, projeto_id):
        # depende do fluxo acima ter deixado a movimentação concluída
        if ultima_situacao(projeto_id, "movimentos") != "concluida":
            pytest.skip("sem movimentação concluída")
        r = iniciar(cliente, "st_suportado", projeto_id, "sup_analista")
        assert r.status_code == 202, r.text
        c = cancelar(cliente, r.json()["id"])
        assert c.status_code == 200, c.text
        assert c.json()["situacao"] == "cancelada"
        assert rodar_fila() == []                          # nada ficou na fila
        assert cancelar(cliente, r.json()["id"]).status_code == 409

    def test_rodando_para_no_proximo_ponto_seguro(self, cliente, projeto_id):
        if ultima_situacao(projeto_id, "movimentos") != "concluida":
            pytest.skip("sem movimentação concluída")
        r = iniciar(cliente, "st_suportado", projeto_id, "sup_analista")
        execucao_id = r.json()["id"]
        # a rodada é reivindicada e alguém manda parar antes do primeiro lote
        with Sessao() as s:
            e = s.get(ExecucaoDB, execucao_id)
            e.situacao = "rodando"
            s.commit()
        assert cancelar(cliente, execucao_id).json()["situacao"] == "cancelando"
        assert iniciar(cliente, "st_suportado", projeto_id, "sup_analista").status_code == 409

        from cat.aplicacao.casos_de_uso import apurar_suportado  # noqa: PLC0415
        apurar_suportado.executar(execucao_id)
        d = execucao(execucao_id)
        assert d["situacao"] == "cancelada"
        assert any("cancelada" in e["texto"].lower() for e in d["resumo"]["log"])

    def test_etapa_sem_freio_nao_aceita_cancelamento(self, cliente, projeto_id):
        with Sessao() as s:
            mov = s.query(ExecucaoDB).filter_by(projeto_id=projeto_id,
                                                etapa="movimentos").first()
        assert cancelar(cliente, mov.id).status_code == 422
