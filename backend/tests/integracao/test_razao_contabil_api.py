"""O razão contábil pelo canal interno: apurar e depois ler na tela.

Uma ECD pequena, duas contas analíticas, lançamentos **fora de ordem de data** —
o SPED não obriga ordem, e é isso que separa um razão de uma lista de partidas.
O caminho inteiro: lote → apuração de PIS/COFINS → seletor → lançamentos.

O que os testes cobram aqui e o teste de unidade não cobre: que a rota só
responda sobre execução **concluída** da etapa **certa** — que desde 23/09/2026
é a apuração, e não mais a quebra —, e que o segredo do canal seja obrigatório.
Ler parquet é problema do módulo analítico.
"""

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
    criar_empresa,
    criar_lote,
    criar_projeto,
    criar_usuario,
    execucao,
    iniciar,
    planilha,
    rodar_fila,
)

CNPJ = "55443322000105"
RAIZ = "55443322"

# 3.1.1 Caixa e 4.1.1 Receita. O lançamento 2 é de 05/06 e vem depois do 3,
# que é de 20/06: o razão tem de reordenar
ECD = "\n".join([
    f"|0000|LECD|01062021|30062021|EMPRESA DA ECD|{CNPJ}|SP|111222333|3550308|||0|0|N||",
    "|I050|01012021|01|S|2|3|",
    "|EMPRESA DA ECD|",
    "|I050|01012021|01|A|3|3.1.1|3|CAIXA|",
    "|I051||1.01.01.01|",
    "|I050|01012021|04|A|3|4.1.1|4|RECEITA DE VENDAS|",
    "|I051||3.01.01.01|",
    "|I200|1|10062021|1000,00|N||",
    "|I250|3.1.1||1000,00|D|1|001|RECEBIMENTO DE VENDA|C09||",
    "|I250|4.1.1||1000,00|C|1|001|RECEBIMENTO DE VENDA|C09||",
    "|I200|3|20062021|500,00|N||",
    "|I250|3.1.1||500,00|D|1|002|VENDA A VISTA|C09||",
    "|I250|4.1.1||500,00|C|1|002|VENDA A VISTA|C09||",
    "|I200|2|05062021|300,00|N||",
    "|I250|3.1.1||300,00|D|1|003|SALDO INICIAL|||",
    "|9999|16|",
]) + "\n"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="ecd_analista", email="ecd@bms.local",
                  nome_exibicao="Analista da ECD", papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def projeto_id(cliente, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("base_ecd")
    (pasta / "ecd.txt").write_bytes(ECD.encode("cp1252"))
    empresa = criar_empresa(raiz=RAIZ, cnpj=CNPJ, razao="EMPRESA DA ECD",
                            ie="123456789012", por="ecd_analista")
    projeto = criar_projeto(empresa_id=empresa, nome="ECD de teste", por="ecd_analista")
    criar_lote(projeto_id=projeto, pasta=str(pasta))
    return projeto


@pytest.fixture(scope="module")
def quebra(cliente, projeto_id):
    r = iniciar(cliente, "apuracao_piscofins", projeto_id, "ecd_analista")
    assert r.status_code == 202, r.text
    rodar_fila()
    d = execucao(r.json()["id"])
    assert d["situacao"] == "concluida", d.get("erro")
    return d


def _contas(cliente, execucao_id: int, **extra) -> dict:
    r = cliente.post("/interno/razao-contabil/contas", headers=SEGREDO,
                     json={"execucao_id": execucao_id, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _lancamentos(cliente, execucao_id: int, conta: str, **extra) -> dict:
    r = cliente.post("/interno/razao-contabil/lancamentos", headers=SEGREDO,
                     json={"execucao_id": execucao_id, "cnpj": CNPJ, "conta": conta, **extra})
    assert r.status_code == 200, r.text
    return r.json()


class TestSeletorDeConta:
    def test_as_duas_analiticas_saem_com_saldo(self, cliente, quebra):
        resposta = _contas(cliente, quebra["id"])

        assert resposta["total"] == 2
        por_conta = {c["conta"]: c for c in resposta["linhas"]}
        assert por_conta["3.1.1"]["descricao"] == "CAIXA"
        assert por_conta["3.1.1"]["conta_referencial"] == "1.01.01.01"
        assert por_conta["3.1.1"]["saldo"] == "1800.00"
        assert por_conta["4.1.1"]["saldo"] == "-1500.00"

    def test_a_busca_e_o_recorte_chegam_ao_leitor(self, cliente, quebra):
        assert _contas(cliente, quebra["id"], busca="CAIXA")["total"] == 1
        assert _contas(cliente, quebra["id"], so="credoras")["total"] == 1

    def test_recorte_inventado_volta_422_dizendo_quais_existem(self, cliente, quebra):
        r = cliente.post("/interno/razao-contabil/contas", headers=SEGREDO,
                         json={"execucao_id": quebra["id"], "so": "inventado"})
        assert r.status_code == 422
        assert "devedoras" in r.json()["detail"]

    def test_os_estabelecimentos_saem_para_o_filtro(self, cliente, quebra):
        r = cliente.post("/interno/razao-contabil/estabelecimentos", headers=SEGREDO,
                         json={"execucao_id": quebra["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["linhas"] == [
            {"cnpj": CNPJ, "contas": 2, "lancamentos": 5,
             "de": "2021-06-05", "ate": "2021-06-20"}]


class TestLancamentosDaConta:
    def test_saem_em_ordem_de_data_com_o_saldo_corrente(self, cliente, quebra):
        """O lançamento 2 é de 05/06 e está por último no arquivo."""
        resposta = _lancamentos(cliente, quebra["id"], "3.1.1")

        assert resposta["total"] == 3
        assert [l["data"] for l in resposta["linhas"]] == [
            "2021-06-05", "2021-06-10", "2021-06-20"]
        assert [l["saldo"] for l in resposta["linhas"]] == ["300.00", "1300.00", "1800.00"]
        assert resposta["descricao"] == "CAIXA"

    def test_os_totais_sao_da_conta_inteira(self, cliente, quebra):
        resposta = _lancamentos(cliente, quebra["id"], "3.1.1", pagina=1, por_pagina=1)

        assert len(resposta["linhas"]) == 1
        assert resposta["totais"] == {"debitos": "1800.00", "creditos": "0.00",
                                      "saldo": "1800.00"}

    def test_o_recorte_de_data_diz_que_recortou(self, cliente, quebra):
        resposta = _lancamentos(cliente, quebra["id"], "3.1.1",
                                de="2021-06-10", ate="2021-06-30")

        assert resposta["total"] == 2
        assert resposta["recortado"] is True
        assert resposta["totais"]["saldo"] == "1500.00"


class TestOQueAsRotasRecusam:
    def test_sem_o_segredo_do_canal_nao_responde(self, cliente, quebra):
        r = cliente.post("/interno/razao-contabil/contas",
                         json={"execucao_id": quebra["id"]})
        assert r.status_code == 403

    def test_execucao_de_outra_etapa_nao_e_um_razao(self, cliente, projeto_id):
        """A quebra é execução também — e desde a separação não é a que tem o razão."""
        with Sessao() as s:
            outra = ExecucaoDB(projeto_id=projeto_id, etapa="quebra_de_sped",
                               situacao="concluida", passo="Concluída")
            s.add(outra)
            s.commit()
            outra_id = outra.id

        resposta = cliente.post("/interno/razao-contabil/contas", headers=SEGREDO,
                                json={"execucao_id": outra_id})
        assert resposta.status_code == 404

    def test_apuracao_que_ainda_nao_terminou(self, cliente, projeto_id):
        """Ler o razão de uma apuração em andamento leria parquet pela metade."""
        with Sessao() as s:
            andando = ExecucaoDB(projeto_id=projeto_id, etapa="apuracao_piscofins",
                                 situacao="rodando", passo="Apurando")
            s.add(andando)
            s.commit()
            andando_id = andando.id

        resposta = cliente.post("/interno/razao-contabil/contas", headers=SEGREDO,
                                json={"execucao_id": andando_id})
        assert resposta.status_code == 409

    def test_execucao_que_nao_existe(self, cliente):
        r = cliente.post("/interno/razao-contabil/contas", headers=SEGREDO,
                         json={"execucao_id": 999_999})
        assert r.status_code == 404


class TestExtrairAsContasMarcadas:
    """A extração do que se marcou na tela — o que vai ser comparado com a 037.

    O cruzamento não é automático por decisão de 23/09/2026: casar partida
    contábil com item de nota exige critério que muda de cliente para cliente.
    O que o sistema entrega é a planilha das contas escolhidas.
    """

    def test_sem_marcar_nada_sai_o_razao_inteiro(self, cliente, quebra):
        saida = planilha(cliente, "apuracao_piscofins", quebra["id"], "razao-contabil",
                         formato="csv")

        linhas = saida.content.decode("utf-8-sig").splitlines()
        contas = {linha.split(";")[1] for linha in linhas[1:] if linha}
        assert contas == {"3.1.1", "4.1.1"}

    def test_marcada_uma_conta_sai_so_ela(self, cliente, quebra):
        saida = planilha(cliente, "apuracao_piscofins", quebra["id"], "razao-contabil",
                         classificacoes="3.1.1", formato="csv")

        linhas = [x for x in saida.content.decode("utf-8-sig").splitlines()[1:] if x]
        assert {linha.split(";")[1] for linha in linhas} == {"3.1.1"}
        # a 3.1.1 tem três partidas na ECD do teste; a 4.1.1 tem duas
        assert len(linhas) == 3

    def test_o_recorte_nao_reaproveita_o_arquivo_do_recorte_anterior(self, cliente, quebra):
        """Dois recortes seguidos: o segundo não pode servir o primeiro.

        O nome do arquivo em cache carrega a seleção justamente por isso — e,
        quando a seleção é grande demais para caber no nome, um resumo dela.
        """
        uma = planilha(cliente, "apuracao_piscofins", quebra["id"], "razao-contabil",
                       classificacoes="3.1.1", formato="csv")
        outra = planilha(cliente, "apuracao_piscofins", quebra["id"], "razao-contabil",
                         classificacoes="4.1.1", formato="csv")

        assert uma.content != outra.content
        assert {x.split(";")[1] for x in outra.content.decode("utf-8-sig").splitlines()[1:] if x} == {"4.1.1"}
