"""O de-para pelo canal interno: o que o sistema propõe, o que já foi decidido e
o que sobra para o cliente dizer.

A movimentação é a de um distribuidor: vende com `1012` e compra com `101208`,
`313308`, `400108` (o sufixo "08" se repete); vende também com um código de
marketplace que nada liga. Uma decisão antiga, do cliente, já aprovou
`CB1427 → 1427` para todos os estabelecimentos.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
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
