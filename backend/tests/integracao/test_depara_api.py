"""O de-para pelo canal interno: o que o sistema propõe, o que já foi decidido e
o que sobra para o cliente dizer.

A movimentação é a de um distribuidor: vende com `1012` e compra com `101208`,
`313308`, `400108` (o sufixo "08" se repete); vende também com um código de
marketplace que nada liga. Uma decisão antiga, do cliente, já aprovou
`CB1427 → 1427` para todos os estabelecimentos.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cat.aplicacao.casos_de_uso.depara_do_trabalho import (
    CASADO,
    ENTRADA_SEM_SAIDA,
    SAIDA_SEM_ENTRADA,
)
from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.analitico.depara import ARQUIVO_DO_RELATORIO
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_MOVIMENTOS
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import Base, DeParaDB, ExecucaoDB, ProjetoDB
from tests.integracao.cadastro import SEGREDO, criar_empresa, criar_projeto, criar_usuario

CNPJ = "44000001000454"
D = Decimal


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="depara.ana", email="depara.ana@bms.local", nome_exibicao="Ana do De-para",
                  papel="analista")
    s.close()
    with TestClient(app) as c:
        yield c


def linha(codigo, operacao, quantidade, descricao="", cfop=None):
    return {"cnpj": CNPJ, "codigo": codigo, "operacao": operacao, "cfop": cfop or ("1403" if operacao == "entrada" else "5405"),
            "quantidade": D(quantidade), "descricao": descricao, "ncm": "33059000",
            "codigo_barras": None, "gtin_xml": None}


@pytest.fixture(scope="module")
def projeto_id(cliente, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("movimentos_depara")
    linhas = [
        linha("1012", "saida", 10, "GRECIN 2000"), linha("101208", "entrada", 30, "GRECIN 2000"),
        linha("3133", "saida", 4, "GRECIN PRETO"), linha("313308", "entrada", 6, "GRECIN PRETO"),
        linha("4001", "saida", 2, "GRECIN GX"), linha("400108", "entrada", 3, "GRECIN GX"),
        linha("1427", "saida", 5, "VAGISIL"), linha("CB1427", "entrada", 9, "VAGISIL DESOD"),
        linha("X0046E1FBP", "saida", 7, "Grecin Barba Marketplace"),
        # devolução de venda não é origem
        linha("X0046E1FBP", "entrada", 1, "Grecin Barba Marketplace", cfop="1202"),
    ]
    esquema = pa.schema([("cnpj", pa.string()), ("codigo", pa.string()), ("operacao", pa.string()),
                         ("cfop", pa.string()), ("quantidade", pa.decimal128(20, 5)), ("descricao", pa.string()),
                         ("ncm", pa.string()), ("codigo_barras", pa.string()), ("gtin_xml", pa.string())])
    pq.write_table(pa.Table.from_pylist(linhas, schema=esquema), str(pasta / ARQUIVO_MOVIMENTOS))
    empresa = criar_empresa(raiz="44000001", cnpj=CNPJ, razao="DISTRIBUIDORA DO DE-PARA", por="depara.ana")
    projeto = criar_projeto(empresa_id=empresa, nome="De-para de teste", por="depara.ana")
    with Sessao() as s:
        s.add(ExecucaoDB(projeto_id=projeto, etapa="movimentos", situacao="concluida", passo="Concluída",
                         pasta_de_trabalho=str(pasta), terminada_em=datetime.now(timezone.utc)))
        s.add(DeParaDB(empresa_id=empresa, cnpj="", codigo_origem="CB1427", codigo_destino="1427", fator=D(1),
                       motivo="cliente", situacao="aprovado", projeto_id=projeto))
        # uma proposta já recusada não volta como pendente
        s.add(DeParaDB(empresa_id=empresa, cnpj=CNPJ, codigo_origem="400108", codigo_destino="4001", fator=D(1),
                       motivo="sufixo", situacao="recusado", projeto_id=projeto))
        s.commit()
    return projeto


def pedir(cliente, projeto_id):
    r = cliente.post("/interno/depara/candidatos", headers=SEGREDO, json={"projeto_id": projeto_id})
    assert r.status_code == 200, r.text
    return r.json()


class TestCandidatos:
    def test_propoe_pelo_sufixo_e_respeita_o_que_ja_foi_decidido(self, cliente, projeto_id):
        d = pedir(cliente, projeto_id)
        pares = {p["origem"]: p for p in d["pares"]}
        # sufixo é prova forte: vale sozinho, e ninguém é creditado por ele
        assert (pares["101208"]["destino"], pares["101208"]["situacao"], pares["101208"]["proposto"],
                pares["101208"]["automatico"], pares["101208"]["decidido_por"]) == (
            "1012", "aprovado", True, True, None)
        assert pares["313308"]["motivos"] == ["sufixo", "descricao"] and pares["313308"]["confianca"] == "alta"
        assert pares["400108"]["situacao"] == "recusado"

    def test_quem_discordou_vence_a_prova(self, cliente, projeto_id):
        """`400108 → 4001` é sufixo como os outros, e foi **recusado**.

        Se a regra passasse por cima da recusa, o par voltaria toda vez que a
        tela fosse aberta e não haveria como tirá-lo da apuração. A decisão
        gravada é a única coisa que existe no banco justamente porque ela é a
        discordância: quem olhou manda.
        """
        pares = {p["origem"]: p for p in pedir(cliente, projeto_id)["pares"]}
        assert "sufixo" in pares["400108"]["motivos"] and pares["400108"]["confianca"] == "alta"
        assert pares["400108"]["situacao"] == "recusado" and pares["400108"]["automatico"] is False
        cliente_ = pares["CB1427"]
        assert (cliente_["destino"], cliente_["situacao"], cliente_["proposto"], cliente_["motivos"]) == (
            "1427", "aprovado", False, ["cliente"])

    def test_o_que_sobra_vai_para_o_cliente(self, cliente, projeto_id):
        d = pedir(cliente, projeto_id)
        assert [s["codigo"] for s in d["sem_par"]] == ["X0046E1FBP"]
        assert d["resumo"] == {"pares": 4, "pendentes": 0, "aprovados": 3, "automaticos": 2,
                               "recusados": 1, "sem_par": 1,
                               "precisavam_de_par": 5, "resolvidos": 4,
                               "estabelecimentos": 1}

    def test_a_cobertura_fecha_a_conta(self, cliente, projeto_id):
        """**O denominador é o problema, não o que sobrou dele.**

        `precisavam_de_par` conta o código com saída e sem entrada — o que
        viraria ficha negativa e sairia do total. Contado depois de resolver,
        mediria o resto e diria sempre quase zero.

        A soma tem de fechar: o que foi resolvido mais o que sobrou é o que
        havia. Numa base real da empresa JK são 56 + 1.591 = 1.647, e a
        cobertura sai 3,4% — o número que diz se o de-para resolveu o problema
        ou arranhou.
        """
        r = pedir(cliente, projeto_id)["resumo"]

        assert r["resolvidos"] + r["sem_par"] == r["precisavam_de_par"]
        assert r["resolvidos"] == 4 and r["precisavam_de_par"] == 5

    def test_sem_movimentacao_e_recusado(self, cliente):
        with Sessao() as s:
            p = s.get(ProjetoDB, criar_projeto(empresa_id=criar_empresa(
                raiz="44000001", cnpj=CNPJ, razao="DISTRIBUIDORA DO DE-PARA", por="depara.ana"),
                nome="Sem movimentos", por="depara.ana"))
            vazio = p.id
        r = cliente.post("/interno/depara/candidatos", headers=SEGREDO, json={"projeto_id": vazio})
        assert r.status_code == 422 and "extração de movimentos" in r.json()["detail"]
        assert cliente.post("/interno/depara/candidatos", headers=SEGREDO,
                            json={"projeto_id": 999999}).status_code == 404
        assert cliente.post("/interno/depara/candidatos", json={"projeto_id": vazio}).status_code == 403


class TestOQueEntraNaMontagem:
    """O razão não lê a tela: ele monta o parquet do de-para do banco.

    Por isso a aprovação automática tem de valer **aqui** também, ou a tela
    diria "aprovado" e a apuração sairia sem o par — o pior dos dois mundos,
    porque ninguém veria a diferença até conferir ficha por ficha.
    """

    def _gravar(self, projeto_id, tmp_path, com_movimentacao: bool = True):
        from cat.aplicacao.casos_de_uso.montar_razao import gravar_depara  # noqa: PLC0415

        with Sessao() as s:
            projeto = s.get(ProjetoDB, projeto_id)
            pasta = s.scalars(select(ExecucaoDB).where(
                ExecucaoDB.projeto_id == projeto_id, ExecucaoDB.etapa == "movimentos")).first().pasta_de_trabalho
            destino = str(tmp_path / f"depara_{com_movimentacao}.parquet")
            total, sozinhos = gravar_depara(projeto.empresa_id, [CNPJ], destino, s,
                                            movimentacao=pasta if com_movimentacao else None)
        lidos = {l["codigo_origem"]: l for l in pq.read_table(destino).to_pylist()} if total else {}
        return lidos, total, sozinhos

    def test_o_par_de_prova_forte_entra_sem_ninguem_aprovar(self, cliente, projeto_id, tmp_path):
        lidos, total, sozinhos = self._gravar(projeto_id, tmp_path)
        assert lidos["101208"]["codigo_destino"] == "1012"
        assert lidos["313308"]["codigo_destino"] == "3133"
        assert lidos["101208"]["fator"] == D(1)
        assert (total, sozinhos) == (3, 2)

    def test_o_recusado_fica_de_fora_e_o_aprovado_do_cliente_entra(self, cliente, projeto_id, tmp_path):
        lidos, _, _ = self._gravar(projeto_id, tmp_path)
        assert "400108" not in lidos           # sufixo, mas alguém recusou
        assert lidos["CB1427"]["codigo_destino"] == "1427"

    def test_sem_a_movimentacao_so_a_decisao_entra(self, cliente, projeto_id, tmp_path):
        """Reprocessar uma rodada antiga não inventa par: sem a movimentação
        não há de onde derivar a proposta, e o que foi decidido continua valendo."""
        lidos, total, sozinhos = self._gravar(projeto_id, tmp_path, com_movimentacao=False)
        assert set(lidos) == {"CB1427"} and (total, sozinhos) == (1, 0)


CNPJ_PONTAS = "44000002000199"


@pytest.fixture(scope="module")
def projeto_pontas(cliente, tmp_path_factory):
    """Uma movimentação feita para ter as duas pontas soltas de uma vez.

    O fixture da tela não tem entrada órfã: todos os códigos de entrada dele
    estão em alguma proposta. Aqui há um de cada — um par, uma saída sem
    entrada e uma entrada sem saída —, com descrição e NCM que nada ligam.
    """
    pasta = tmp_path_factory.mktemp("movimentos_pontas")

    def l(codigo, operacao, quantidade, descricao, ncm):
        return {"cnpj": CNPJ_PONTAS, "codigo": codigo, "operacao": operacao,
                "cfop": "1403" if operacao == "entrada" else "5405",
                "quantidade": D(quantidade), "descricao": descricao, "ncm": ncm,
                "codigo_barras": None, "gtin_xml": None}

    linhas = [
        # o par: mesmo código com o sufixo da compra
        l("2012", "saida", 10, "GAMA LOCAO 200ML", "33059000"),
        l("201208", "entrada", 30, "GAMA LOCAO 200ML", "33059000"),
        # saiu e não entrou
        l("Z9MARKET", "saida", 7, "Zeta Marketplace Avulso", "33059000"),
        # entrou e não saiu, e nada o liga ao de cima
        l("K7PARAFUSO", "entrada", 4, "Parafuso Sextavado 8mm", "73181500"),
    ]
    esquema = pa.schema([("cnpj", pa.string()), ("codigo", pa.string()), ("operacao", pa.string()),
                         ("cfop", pa.string()), ("quantidade", pa.decimal128(20, 5)), ("descricao", pa.string()),
                         ("ncm", pa.string()), ("codigo_barras", pa.string()), ("gtin_xml", pa.string())])
    pq.write_table(pa.Table.from_pylist(linhas, schema=esquema), str(pasta / ARQUIVO_MOVIMENTOS))
    empresa = criar_empresa(raiz="44000002", cnpj=CNPJ_PONTAS, razao="DAS DUAS PONTAS", por="depara.ana")
    projeto = criar_projeto(empresa_id=empresa, nome="De-para das pontas", por="depara.ana")
    with Sessao() as s:
        s.add(ExecucaoDB(projeto_id=projeto, etapa="movimentos", situacao="concluida", passo="Concluída",
                         pasta_de_trabalho=str(pasta), terminada_em=datetime.now(timezone.utc)))
        s.commit()
    return projeto


class TestRelatorio:
    """O relatório que se baixa na etapa: a entrada num bloco, a saída no outro.

    O que se garante aqui é o que o relatório antigo não dava: a ponta vazia.
    Código que saiu e não entrou aparece **sem** o bloco da entrada, e o que
    entrou e não saiu aparece **sem** o bloco da saída — na mesma lista, para
    quem decide ver os dois lados de uma vez.
    """

    def _linhas(self, cliente, projeto_id, formato="xlsx"):
        r = cliente.post("/interno/depara/planilha", headers=SEGREDO,
                         json={"projeto_id": projeto_id, "formato": formato})
        assert r.status_code == 200, r.text
        pronta = r.json()
        parquet = str(Path(pronta["caminho"]).with_name(ARQUIVO_DO_RELATORIO))
        return pronta, pq.read_table(parquet).to_pylist()

    def test_o_par_tem_a_entrada_de_um_lado_e_a_saida_do_outro(self, cliente, projeto_id):
        _, linhas = self._linhas(cliente, projeto_id)
        par = next(l for l in linhas if l["codigo_entrada"] == "101208")
        assert par["casamento"] == CASADO
        # a origem entrou (30) e o destino saiu (10): um em cada bloco
        assert par["quantidade_entrada"] == D(30)
        assert (par["codigo_saida"], par["quantidade_saida"]) == ("1012", D(10))
        # e a ficha que recebe é a do destino
        assert par["ficha_do_codigo"] == "1012"
        assert "código + sufixo" in par["como_casou"]

    def test_a_saida_sem_entrada_vem_com_o_bloco_da_entrada_vazio(self, cliente, projeto_id):
        _, linhas = self._linhas(cliente, projeto_id)
        solta = next(l for l in linhas if l["codigo_saida"] == "X0046E1FBP")
        assert solta["casamento"] == SAIDA_SEM_ENTRADA
        # a ponta vazia: nada do lado da entrada, nem código nem quantidade
        assert solta["codigo_entrada"] == ""
        assert solta["descricao_entrada"] == ""
        assert solta["quantidade_entrada"] is None
        assert solta["quantidade_saida"] == D(7)
        # sem par não há prova nem decisão a mostrar
        assert (solta["como_casou"], solta["situacao_do_par"], solta["fator"]) == ("", "", None)

    def test_a_entrada_sem_saida_vem_com_o_bloco_da_saida_vazio(self, cliente, projeto_pontas):
        _, linhas = self._linhas(cliente, projeto_pontas)
        solta = next(l for l in linhas if l["casamento"] == ENTRADA_SEM_SAIDA)
        assert solta["codigo_entrada"] == "K7PARAFUSO"
        assert solta["quantidade_entrada"] == D(4)
        # a outra ponta vazia: nada do lado da saída
        assert solta["codigo_saida"] == ""
        assert solta["descricao_saida"] == ""
        assert solta["quantidade_saida"] is None

    def test_o_par_do_cliente_entra_com_quem_decidiu(self, cliente, projeto_id):
        _, linhas = self._linhas(cliente, projeto_id)
        do_cliente = next(l for l in linhas if l["ficha_do_codigo"] == "1427")
        # CB1427 entrou (9), 1427 saiu (5): o par do cliente segue a mesma convenção
        assert (do_cliente["codigo_entrada"], do_cliente["codigo_saida"]) == ("CB1427", "1427")
        assert do_cliente["como_casou"] == "informado pelo cliente"
        assert do_cliente["situacao_do_par"] == "aprovado"

    def test_as_tres_situacoes_convivem_na_mesma_lista(self, cliente, projeto_pontas):
        """É o ponto do relatório: par e pontas soltas numa lista só, sem
        obrigar quem decide a cruzar duas planilhas."""
        pronta, linhas = self._linhas(cliente, projeto_pontas)
        assert {CASADO, SAIDA_SEM_ENTRADA, ENTRADA_SEM_SAIDA} == {l["casamento"] for l in linhas}
        assert pronta["nome"] == "depara_entrada_saida.xlsx"
        assert pronta["tipo"].endswith("spreadsheetml.sheet")

    def test_sai_em_csv_tambem(self, cliente, projeto_id):
        pronta, _ = self._linhas(cliente, projeto_id, formato="csv")
        assert pronta["nome"] == "depara_entrada_saida.csv"
        texto = Path(pronta["caminho"]).read_text(encoding="utf-8-sig")
        cabecalho = texto.splitlines()[0]
        # o cabeçalho do CSV não tem faixa: os dois blocos viram títulos próprios
        assert "Qtde entrada" in cabecalho and "Qtde saída" in cabecalho
        assert "X0046E1FBP" in texto

    def test_formato_desconhecido_e_recusado(self, cliente, projeto_id):
        r = cliente.post("/interno/depara/planilha", headers=SEGREDO,
                         json={"projeto_id": projeto_id, "formato": "pdf"})
        assert r.status_code == 404
        assert "xlsx" in r.json()["detail"]
