"""Inspeção da pasta de um lote, pelo canal interno do motor.

Identificar o que há numa pasta é trabalho de disco, e fica no motor: o que
serve à CAT, de que competência, o que é de outra empresa e o que já está no
trabalho. Registrar o lote, listar e remover moram na API em C# desde
13/09/2026 (api/tests/Cat.Api.Testes/LotesTestes.cs), que chama esta rota.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base
from cat.dominio.lote import TipoDeArquivo
from tests.integracao.cadastro import (
    SEGREDO, criar_usuario, criar_empresa, criar_lote, criar_projeto, quantas_empresas, tem_base,
)

# Raiz própria deste módulo. A bateria de integração compartilha um banco
# só, e a raiz 50948371 já é usada por test_auth_api — cadastrar de novo
# daria 409 no setup.
ICMS_IPI = (
    "|0000|018|0|01012025|31012025|EMPRESA DO LOTE LTDA|77665544000105||SP"
    "|407048962113|3550308|||A|0|"
)
CONTRIBUICOES = (
    "|0000|006|0|||01062021|30062021|EMPRESA DO LOTE LTDA"
    "|77665544000105|SP|3550308||00|2|"
)
DE_OUTRA_EMPRESA = (
    "|0000|018|0|01012025|31012025|OUTRA EMPRESA LTDA|11222333000181||MG"
    "|123456789|3106200|||A|0|"
)


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="lote_analista", email="lote.analista@bms.local",
                     nome_exibicao="Analista do Lote",
                     papel="dev", cargo="analista")
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def projeto_id(cliente):
    empresa = criar_empresa(raiz="77665544", cnpj="77665544000105",
                            razao="EMPRESA DO LOTE LTDA", ie="407048962113",
                            por="lote_analista")
    return criar_projeto(empresa_id=empresa, nome="CAT 42 de teste",
                         ini="2025-01-01", fim="2025-12-01", por="lote_analista")


def escrever(pasta, nome, conteudo):
    (pasta / nome).write_bytes(conteudo.encode("latin-1"))


@pytest.fixture(scope="module")
def pasta_com_base(tmp_path_factory):
    """A MESMA pasta para todos os testes do módulo.

    Precisa ser de módulo: parte do que se prova aqui é que a segunda
    importação da mesma pasta é recusada, e com pasta nova a cada teste não
    haveria segunda vez.
    """
    pasta = tmp_path_factory.mktemp("base_do_trabalho")
    escrever(pasta, "boa_012025.txt", ICMS_IPI)
    escrever(pasta, "contribuicoes.txt", CONTRIBUICOES)
    escrever(pasta, "intruso.txt", DE_OUTRA_EMPRESA)
    return str(pasta)


def inspecionar(cliente, projeto_id, pasta):
    return cliente.post("/interno/lotes/inspecionar", headers=SEGREDO,
                        json={"projeto_id": projeto_id, "pasta": pasta})


def uteis(corpo) -> int:
    return sum(1 for a in corpo["arquivos"] if TipoDeArquivo(a["tipo"]).alimenta_a_cat)


class TestConferirAntesDeGravar:
    def test_diz_o_que_ha_sem_criar_nada(self, cliente, projeto_id, pasta_com_base):
        antes = quantas_empresas()

        r = inspecionar(cliente, projeto_id, pasta_com_base)
        assert r.status_code == 200, r.text
        corpo = r.json()

        assert len(corpo["arquivos"]) == 2        # o intruso não conta
        assert uteis(corpo) == 1                  # só a EFD ICMS/IPI
        assert corpo["de_outra_empresa"] == 1
        assert corpo["serve"] is True
        assert corpo["competencias"][0] == "2025-01-01"
        assert not any(a["ja_no_trabalho"] for a in corpo["arquivos"])

        # inspecionar não cria empresa nem lote: é o que separa esta tela do cadastro
        assert quantas_empresas() == antes
        assert not tem_base(projeto_id)

    def test_avisa_o_que_ficou_de_fora(self, cliente, projeto_id, pasta_com_base):
        avisos = " ".join(inspecionar(cliente, projeto_id, pasta_com_base).json()["avisos"])
        assert "outra empresa" in avisos

    def test_diz_de_quem_e_o_que_ficou_de_fora(self, cliente, projeto_id, pasta_com_base):
        """O descarte por empresa não pede confirmação, mas tem de ser conferível:
        quem importa precisa ver o CNPJ e o nome do arquivo que saiu."""
        corpo = inspecionar(cliente, projeto_id, pasta_com_base).json()
        assert [(e["cnpj"], e["arquivos"]) for e in corpo["empresas_de_fora"]] == [
            ("11222333000181", 1)]
        assert corpo["empresas_de_fora"][0]["bytes_totais"] > 0
        fora = corpo["fora_por_empresa"]
        assert len(fora) == 1 and fora[0]["cnpj"] == "11222333000181"
        assert fora[0]["motivo"] == "de outra empresa" and fora[0]["alimenta"] is False
        # e não entra na lista que vai virar lote
        assert fora[0]["caminho"] not in [a["caminho"] for a in corpo["arquivos"]]

    def test_pasta_inexistente_explica(self, cliente, projeto_id):
        r = inspecionar(cliente, projeto_id, "Z:/pasta/que/nao/existe")
        assert r.status_code == 422
        assert "não existe" in r.json()["detail"]

    def test_trabalho_inexistente_da_404(self, cliente, tmp_path):
        assert inspecionar(cliente, 999999, str(tmp_path)).status_code == 404

    def test_sem_o_segredo_nao_inspeciona(self, cliente, projeto_id, pasta_com_base):
        r = cliente.post("/interno/lotes/inspecionar",
                         json={"projeto_id": projeto_id, "pasta": pasta_com_base})
        assert r.status_code == 403


class TestDepoisDeRegistrado:
    def test_a_inspecao_marca_o_que_ja_esta_no_trabalho(
        self, cliente, projeto_id, pasta_com_base
    ):
        # é por esta marca que a API não registra o mesmo SPED duas vezes
        criar_lote(projeto_id=projeto_id, pasta=pasta_com_base)
        corpo = inspecionar(cliente, projeto_id, pasta_com_base).json()
        assert len(corpo["arquivos"]) == 2
        assert all(a["ja_no_trabalho"] for a in corpo["arquivos"])
        assert tem_base(projeto_id)

    def test_diz_o_tipo_gravado_para_a_api_reclassificar(
        self, cliente, projeto_id, pasta_com_base
    ):
        # o arquivo importado antes de a classificação mudar guarda o tipo antigo
        if not tem_base(projeto_id):
            criar_lote(projeto_id=projeto_id, pasta=pasta_com_base)
        from cat.infraestrutura.repositorios.banco import Sessao
        from cat.infraestrutura.repositorios.modelos import ArquivoDoLoteDB, LoteDB
        with Sessao() as s:
            arquivo = s.query(ArquivoDoLoteDB).join(LoteDB).filter(
                LoteDB.projeto_id == projeto_id).order_by(ArquivoDoLoteDB.caminho).first()
            arquivo.tipo = TipoDeArquivo.COMPACTADO.value
            s.commit()
            mudado = arquivo.caminho
        corpo = inspecionar(cliente, projeto_id, pasta_com_base).json()
        por_caminho = {a["caminho"]: a for a in corpo["arquivos"]}
        assert por_caminho[mudado]["tipo_no_trabalho"] == "compactado"
        assert por_caminho[mudado]["tipo"] != "compactado"
        assert all(a["tipo_no_trabalho"] == a["tipo"] for c, a in por_caminho.items() if c != mudado)
