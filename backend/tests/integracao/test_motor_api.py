"""O motor por fora: só o canal interno, e o que ele garante por conta própria.

Desde a fatia 7 (docs/MIGRACAO_CSHARP.md) o motor não tem rota pública. Login,
usuários, empresas, projetos, histórico, lotes, execuções e planilhas moram na
API em C#; os cenários delas estão em api/tests/Cat.Api.Testes. O que chega
aqui vem da API, pelo canal interno, com o segredo.
"""

import os
import shutil
import tempfile

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base
from cat.versao import versao
from tests.integracao.cadastro import SEGREDO, criar_usuario


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="motor.ana", email="motor.ana@bms.local",
                     nome_exibicao="Ana", papel="analista")
    s.close()
    with TestClient(app) as c:
        yield c


class TestSemRotaPublica:
    """Uma regra existe num lugar só. Se uma rota pública voltar ao motor,
    voltam as duas — e a de cá sem conferir quem pede."""

    @staticmethod
    def _caminhos(rotas, prefixo=""):
        # o FastAPI 0.14x guarda o router incluído embrulhado, com o prefixo à parte
        for r in rotas:
            if isinstance(r, APIRoute):
                yield prefixo + r.path
            elif hasattr(r, "original_router"):
                yield from TestSemRotaPublica._caminhos(
                    r.original_router.routes, prefixo + r.include_context.prefix)

    def test_toda_rota_do_motor_e_do_canal_interno(self):
        caminhos = list(self._caminhos(app.routes))
        assert caminhos, "o motor ficou sem rota nenhuma"
        assert [c for c in caminhos if not c.startswith("/interno/")] == []

    @pytest.mark.parametrize("metodo, rota", [
        ("GET", "/api/saude"), ("POST", "/api/auth/token"), ("GET", "/api/usuarios"),
        ("GET", "/api/empresas"), ("GET", "/api/projetos/1"), ("GET", "/api/projetos/1/historico"),
        ("POST", "/api/projetos/1/lotes"), ("POST", "/api/importacoes/analisar"),
        ("POST", "/api/projetos/1/conferencias"), ("GET", "/api/movimentos/1/planilhas/itens"),
    ])
    def test_rotas_que_foram_para_o_csharp_nao_respondem_aqui(self, cliente, metodo, rota):
        assert cliente.request(metodo, rota).status_code in (404, 405)

    @pytest.mark.parametrize("rota", ["/docs", "/redoc", "/openapi.json"])
    def test_sem_documentacao_publica(self, cliente, rota):
        # quem descreve a API para a tela é o C#; o canal interno não se anuncia
        assert cliente.get(rota).status_code == 404


class TestSaude:
    def test_responde_pelo_canal_com_a_versao_e_a_pasta(self, cliente):
        r = cliente.get("/interno/saude", headers=SEGREDO)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["status"] == "ok"
        assert corpo["versao"] == versao()
        assert corpo["pasta_de_trabalho"] == obter_config().raiz_de_trabalho

    def test_sem_segredo_nao_diz_nada(self, cliente):
        r = cliente.get("/interno/saude")
        assert r.status_code == 403
        assert "versao" not in r.text

    def test_resposta_traz_identificador_de_requisicao(self, cliente):
        """Sem isso não dá para juntar as linhas de log de um mesmo pedido."""
        r = cliente.get("/interno/saude", headers={**SEGREDO, "X-Request-Id": "pedido-42"})
        assert r.headers.get("X-Request-Id") == "pedido-42"


class TestRemessaPeloCanal:
    SEGREDO = {"X-Cat-Motor-Segredo": "segredo-do-canal-so-de-teste"}
    SPED = ("|0000|018|0|01052021|31052021|EMPRESA DA REMESSA|11222333000181||SP"
            "|9030138187|3550308||||\r\n").encode("latin-1")

    def test_analisa_e_devolve_a_matriz_sem_dizer_se_esta_cadastrada(self, cliente):
        r = cliente.post("/interno/remessas/analisar", headers=self.SEGREDO,
                         files={"arquivo": ("efd.txt", self.SPED, "text/plain")})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["cnpj_raiz"] == "11222333"
        assert corpo["matriz"]["cnpj_formatado"] == "11.222.333/0001-81"
        # se a empresa já existe, quem diz é a API: ela tem o banco da tela
        assert "ja_cadastrada" not in corpo

    def test_sem_sped_e_recusada_e_sem_segredo_nao_entra(self, cliente):
        r = cliente.post("/interno/remessas/analisar", headers=self.SEGREDO,
                         files={"arquivo": ("nada.txt", b"conteudo qualquer", "text/plain")})
        assert r.status_code == 422
        r = cliente.post("/interno/remessas/analisar",
                         files={"arquivo": ("efd.txt", self.SPED, "text/plain")})
        assert r.status_code == 403


class TestFila:
    """workers/fila.py: a tabela execucao é a fila, lida uma de cada vez."""

    @pytest.fixture
    def projeto_id(self, cliente):
        from tests.integracao.cadastro import criar_empresa, criar_projeto  # noqa: PLC0415
        empresa = criar_empresa(raiz="31415926", cnpj="31415926000126", razao="EMPRESA DA FILA", por="motor.ana")
        return criar_projeto(empresa_id=empresa, nome=f"Fila {os.urandom(3).hex()}", por="motor.ana")

    def _nova(self, projeto_id, etapa="conferencia", situacao="na_fila"):
        from cat.infraestrutura.repositorios.banco import Sessao  # noqa: PLC0415
        from cat.infraestrutura.repositorios.modelos import ExecucaoDB  # noqa: PLC0415
        with Sessao() as s:
            e = ExecucaoDB(projeto_id=projeto_id, etapa=etapa, situacao=situacao, passo="Na fila")
            s.add(e)
            s.commit()
            return e.id

    def _situacao(self, execucao_id):
        from tests.integracao.cadastro import execucao  # noqa: PLC0415
        return execucao(execucao_id)

    def test_interrompida_por_reinicio_vira_falha_com_motivo(self, cliente, projeto_id):
        from workers import fila  # noqa: PLC0415
        orfa = self._nova(projeto_id, situacao="rodando")
        assert fila.recuperar_interrompidas() >= 1
        d = self._situacao(orfa)
        assert d["situacao"] == "falhou"
        assert "reiniciou" in d["erro"]
        assert d["terminada_em"]

    def test_pega_a_mais_antiga_e_uma_de_cada_vez(self, cliente, projeto_id, monkeypatch):
        from workers import fila  # noqa: PLC0415
        rodadas = []
        monkeypatch.setitem(fila.EXECUTORES, "conferencia", rodadas.append)
        fila.processar_pendentes()          # esvazia o que outros testes deixaram
        rodadas.clear()
        primeira, segunda = self._nova(projeto_id), self._nova(projeto_id)
        assert fila.processar_uma() == primeira
        assert rodadas == [primeira]
        assert self._situacao(segunda)["situacao"] == "na_fila"
        assert fila.processar_pendentes() == [segunda]
        assert fila.processar_uma() is None

    def test_etapa_que_o_motor_nao_conhece_falha_em_vez_de_ficar_parada(self, cliente, projeto_id):
        from workers import fila  # noqa: PLC0415
        fila.processar_pendentes()
        desconhecida = self._nova(projeto_id, etapa="apuracao")
        assert fila.processar_uma() == desconhecida
        d = self._situacao(desconhecida)
        assert d["situacao"] == "falhou"
        assert "apuracao" in d["erro"]

    def test_excecao_que_escapa_do_executor_marca_falha(self, cliente, projeto_id, monkeypatch):
        from workers import fila  # noqa: PLC0415
        fila.processar_pendentes()
        def explode(_):
            raise RuntimeError("disco sumiu")
        monkeypatch.setitem(fila.EXECUTORES, "conferencia", explode)
        quebrada = self._nova(projeto_id)
        fila.processar_uma()
        assert self._situacao(quebrada)["situacao"] == "falhou"


class TestCanalInterno:
    """A API em C# pede, o motor apaga — só com o segredo, e só na pasta de trabalho."""

    SEGREDO = {"X-Cat-Motor-Segredo": "segredo-do-canal-so-de-teste"}

    @pytest.fixture
    def pastas(self):
        raiz = obter_config().raiz_de_trabalho
        dentro = os.path.join(raiz, f"execucao-{os.urandom(4).hex()}")
        os.makedirs(os.path.join(dentro, "sub"))
        with open(os.path.join(dentro, "sub", "parquet.bin"), "wb") as f:
            f.write(b"x")
        fora = tempfile.mkdtemp(prefix="cat_fora_da_raiz_")
        yield dentro, fora, raiz
        shutil.rmtree(fora, ignore_errors=True)

    def test_sem_segredo_nao_apaga(self, cliente, pastas):
        dentro, _, _ = pastas
        r = cliente.post("/interno/pastas/apagar", json={"pastas": [dentro]})
        assert r.status_code == 403
        r = cliente.post("/interno/pastas/apagar", json={"pastas": [dentro]},
                         headers={"X-Cat-Motor-Segredo": "errado"})
        assert r.status_code == 403
        assert os.path.isdir(dentro)

    def test_apaga_dentro_da_raiz_e_recusa_fora_e_a_propria_raiz(self, cliente, pastas):
        dentro, fora, raiz = pastas
        r = cliente.post("/interno/pastas/apagar", headers=self.SEGREDO,
                         json={"pastas": [dentro, fora, raiz, os.path.join(dentro, "..", "..")]})
        assert r.status_code == 200, r.text
        assert r.json()["apagadas"] == [dentro]
        assert len(r.json()["recusadas"]) == 3
        assert not os.path.exists(dentro)
        assert os.path.isdir(fora)
        assert os.path.isdir(raiz)

    def test_sem_segredo_configurado_o_canal_fica_fechado(self, cliente, pastas, monkeypatch):
        dentro, _, _ = pastas
        monkeypatch.setattr(obter_config(), "motor_segredo", "")
        r = cliente.post("/interno/pastas/apagar", headers=self.SEGREDO, json={"pastas": [dentro]})
        assert r.status_code == 503
        assert os.path.isdir(dentro)
