"""A etapa do combustível, e o registro que faz ela existir.

Dois assuntos, e o segundo vale para todas as etapas.

O primeiro é o que esta etapa recusa: sem EFD ICMS/IPI no lote não há compra
para ler, e a mensagem tem de dizer **qual** arquivo falta — "importe a base"
não ajuda quem importou a de Contribuições achando que servia.

O segundo é o **registro**. Uma etapa precisa estar em dois mapas: o do canal
interno, que a põe na fila, e o da fila, que a executa. Esquecer um dos dois dá
erro só em produção, no clique — o canal responde "etapa desconhecida", ou a
execução entra na fila e fica lá para sempre. O teste abaixo percorre os dois
mapas e cobra os dois lados de **toda** etapa, não só desta.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso import apurar_combustivel
from cat.apresentacao.api.routers.interno_router import PREPARADORES
from cat.dominio.lote import TipoDeArquivo
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    Base,
    EmpresaDB,
    LoteDB,
    ProjetoDB,
)
from workers.fila import EXECUTORES


@pytest.fixture
def sessao() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _projeto(sessao: Session, *tipos: TipoDeArquivo) -> int:
    """Um trabalho com um lote, e nele um arquivo de cada tipo pedido."""
    empresa = EmpresaDB(cnpj_raiz="44000003", razao_social="EMPRESA DO TESTE LTDA")
    sessao.add(empresa)
    sessao.flush()
    projeto = ProjetoDB(empresa_id=empresa.id, frente="cat42", nome="Teste",
                        competencia_ini=date(2024, 1, 1),
                        competencia_fim=date(2024, 12, 31))
    sessao.add(projeto)
    sessao.flush()
    lote = LoteDB(projeto_id=projeto.id, pasta="C:/lote")
    sessao.add(lote)
    sessao.flush()
    for i, tipo in enumerate(tipos):
        sessao.add(ArquivoDoLoteDB(lote_id=lote.id, caminho=f"C:/lote/a{i}.txt",
                                   nome=f"a{i}.txt", tipo=tipo.value, tamanho=1))
    sessao.commit()
    return projeto.id


class TestOQueElaRecusa:
    def test_sem_efd_icms_ipi_recusa_dizendo_qual_arquivo_falta(self, sessao):
        projeto_id = _projeto(sessao)

        with pytest.raises(apurar_combustivel.NadaParaApurar) as erro:
            apurar_combustivel.preparar(projeto_id, usuario_id=1, sessao=sessao)

        assert "EFD ICMS/IPI" in str(erro.value)

    def test_a_efd_de_contribuicoes_nao_serve_e_a_mensagem_explica(self, sessao):
        """**O erro que a mensagem existe para evitar.** Quem tem o lote cheio
        de EFD-Contribuições vai achar que importou a base certa — e ela não
        traz o CST do ICMS nem a unidade do item."""
        projeto_id = _projeto(sessao, TipoDeArquivo.SPED_CONTRIBUICOES)

        with pytest.raises(apurar_combustivel.NadaParaApurar) as erro:
            apurar_combustivel.preparar(projeto_id, usuario_id=1, sessao=sessao)

        assert "Contribuições não serve" in str(erro.value)
        assert "CST" in str(erro.value), "diz o que falta nela"


class TestOQueElaAceita:
    def test_com_efd_icms_ipi_a_execucao_entra_na_fila(self, sessao):
        projeto_id = _projeto(sessao, TipoDeArquivo.SPED_ICMS_IPI,
                              TipoDeArquivo.SPED_ICMS_IPI)

        execucao = apurar_combustivel.preparar(projeto_id, usuario_id=1,
                                               sessao=sessao)

        assert execucao.etapa == apurar_combustivel.ETAPA
        assert execucao.situacao == "na_fila"
        assert execucao.arquivos_totais == 2

    def test_a_fonte_e_so_a_icms_ipi(self):
        """Pôr a de Contribuições aqui faria o leitor ler o `0000` errado: os
        dois leiautes colidem (ver `sped/registros_icms.py`)."""
        assert apurar_combustivel.FONTES == (TipoDeArquivo.SPED_ICMS_IPI,)


class TestTodaEtapaPrecisaDosDoisRegistros:
    """**O teste que vale para todas, e não só para a nova.**

    Uma etapa mora em dois mapas: `PREPARADORES`, do canal interno, que a põe na
    fila; e `EXECUTORES`, da fila, que a roda. Esquecer um dos dois não quebra
    teste nenhum — quebra no clique, em produção: ou o canal responde "etapa
    desconhecida", ou a execução entra na fila e fica lá para sempre, porque
    ninguém sabe executá-la.
    """

    def test_quem_prepara_tambem_executa(self):
        faltam = sorted(set(PREPARADORES) - set(EXECUTORES))

        assert not faltam, (f"etapas que o canal interno põe na fila e a fila "
                            f"não sabe rodar: {faltam}")

    def test_quem_executa_tambem_prepara(self):
        """O outro lado: executor sem preparador é código que nunca roda."""
        faltam = sorted(set(EXECUTORES) - set(PREPARADORES))

        assert not faltam, (f"etapas que a fila sabe rodar e o canal interno "
                            f"não sabe pôr na fila: {faltam}")

    def test_o_combustivel_esta_nos_dois(self):
        assert apurar_combustivel.ETAPA in PREPARADORES
        assert apurar_combustivel.ETAPA in EXECUTORES

    def test_cada_preparador_traz_a_excecao_e_a_frase_de_conflito(self):
        """A tupla do mapa é `(preparar, exceção, frase)`. Frase vazia deixaria
        a tela dizer "erro" quando a pessoa clica duas vezes."""
        for etapa, (preparar, excecao, frase) in PREPARADORES.items():
            assert callable(preparar), etapa
            assert issubclass(excecao, Exception), etapa
            assert len(frase) > 20, etapa
