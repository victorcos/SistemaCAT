"""O índice lido sem as posições, e por que isso existe.

Em 09/10/2026 a execução #181 quebrou 46 EFD-Contribuições — 169.480.272 linhas.
A quebra concluiu em 16 min. Em seguida, montar a lista do que dava para extrair
**travou**, e a tela mostrou "O motor do sistema não respondeu".

A causa não era o motor: era `disponiveis()`. Para responder *quais* registros
dá para extrair, ela carregava os 789 MB de `posicoes.parquet` dos 46 arquivos
-- 169.200.030 posições, uma a uma, em objeto Python -- e descartava todas em
seguida. Medido: **142 s**, dos quais nenhum byte entrava na resposta.

A resposta já estava no `indice.json`, no campo `indexados`, gravado desde
sempre. Com ele, a mesma chamada leva **0,49 s** na mesma base.

Estes testes cobram as três coisas que a correção não pode perder:

* o resumo diz o mesmo que o índice inteiro sobre o que existe;
* ele **não** abre o parquet -- é a diferença toda, e sem isto o teste passaria
  mesmo se alguém voltasse a carregar as posições;
* índice que não serve continua não servindo, pelos mesmos três motivos.
"""

from __future__ import annotations

import json
import os

import pytest

from cat.infraestrutura.analitico.quebra_de_sped import PASTA_DOS_INDICES, quebrar
from cat.infraestrutura.analitico.escrita import pasta_do_indice
from cat.infraestrutura.analitico.registros_do_sped import disponiveis
from cat.infraestrutura.sped.indice import (
    ARQUIVO_DAS_POSICOES,
    ARQUIVO_DO_INDICE,
    buscar,
    resumo,
)


def _sped(inicio: str, fim: str) -> str:
    """Um EFD-Contribuições mínimo, com registro indexado e registro contado."""
    return "\n".join([
        f"|0000|005|0|{inicio}|{fim}|EMPRESA TESTE|31698759000113|MG|||0|",
        "|0140|001|EMPRESA TESTE|31698759000113|MG||||",
        "|C010|31698759000113|0|",
        "|C100|0|1|FORN|55|00|1|000000001|3510|01062021|01062021|100,00|",
        "|C170|1|ITEM-1|desc|1|UN|50,00|0,00|0|5102|",
        "|C170|2|ITEM-2|desc|1|UN|50,00|0,00|0|5102|",
        "|M200|10,00|0,00|0,00|0,00|0,00|10,00|0,00|0,00|0,00|10,00|",
        "|9999|8|",
    ]) + "\n"


@pytest.fixture(scope="module")
def quebrado(tmp_path_factory):
    base = tmp_path_factory.mktemp("resumo")
    caminhos = []
    for inicio, fim, nome in (("01062021", "30062021", "efd_062021.txt"),
                              ("01072021", "31072021", "efd_072021.txt")):
        alvo = base / nome
        alvo.write_bytes(_sped(inicio, fim).encode("cp1252"))
        caminhos.append(str(alvo))
    destino = str(base / "execucao")
    quebrar(caminhos, [], destino)
    return destino, caminhos


def _pasta_do_indice(destino: str, caminho: str) -> str:
    return os.path.join(destino, PASTA_DOS_INDICES, pasta_do_indice(caminho))


class TestDizOMesmoQueOIndiceInteiro:
    def test_os_registros_indexados_sao_os_mesmos(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])

        assert resumo(pasta, caminhos[0]).indexados == buscar(pasta, caminhos[0]).indexados

    def test_as_contagens_e_o_cabecalho_sao_os_mesmos(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])
        inteiro = buscar(pasta, caminhos[0])
        curto = resumo(pasta, caminhos[0])

        assert curto.contagens == inteiro.contagens
        assert curto.cabecalho == inteiro.cabecalho
        assert curto.bytes_totais == inteiro.bytes_totais
        assert curto.codificacao == inteiro.codificacao


class TestNaoAbreOParquet:
    """**O ponto todo.** Sem isto, tudo passaria com as posições de volta."""

    def test_o_resumo_sai_inteiro_mesmo_sem_o_arquivo_de_posicoes(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])
        posicoes = os.path.join(pasta, ARQUIVO_DAS_POSICOES)
        guardado = open(posicoes, "rb").read()
        os.remove(posicoes)
        try:
            curto = resumo(pasta, caminhos[0])
            assert "C170" in curto.indexados, (
                "o indexado vem do JSON; sem ele a correção não resolveu nada")
            assert curto.contagens["C170"] == 2
        finally:
            with open(posicoes, "wb") as volta:
                volta.write(guardado)

    def test_a_lista_de_alvos_sai_sem_o_parquet_de_nenhum_arquivo(self, quebrado):
        """A chamada que travou na #181, com as posições fora do alcance."""
        destino, caminhos = quebrado
        guardados = {}
        for caminho in caminhos:
            alvo = os.path.join(_pasta_do_indice(destino, caminho), ARQUIVO_DAS_POSICOES)
            guardados[alvo] = open(alvo, "rb").read()
            os.remove(alvo)
        try:
            d = disponiveis(destino)
            por_alvo = {l["alvo"]: l for l in d["linhas"]}
            assert por_alvo["C170"]["quantidade"] == 4   # dois por arquivo
            assert d["sem_indice"] == 0
        finally:
            for alvo, conteudo in guardados.items():
                with open(alvo, "wb") as volta:
                    volta.write(conteudo)


class TestORecuoQuandoOJsonENovoDemaisOuVelhoDemais:
    def test_sem_a_lista_de_indexados_ele_le_do_parquet(self, quebrado):
        """Devolver conjunto vazio seria dizer 'nada é extraível' em silêncio."""
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])
        alvo = os.path.join(pasta, ARQUIVO_DO_INDICE)
        guardado = open(alvo, encoding="utf-8").read()
        bruto = json.loads(guardado)
        del bruto["indexados"]
        with open(alvo, "w", encoding="utf-8") as saida:
            json.dump(bruto, saida)
        try:
            assert "C170" in resumo(pasta, caminhos[0]).indexados
        finally:
            with open(alvo, "w", encoding="utf-8") as volta:
                volta.write(guardado)

    def test_indice_de_outro_esquema_nao_serve(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])
        alvo = os.path.join(pasta, ARQUIVO_DO_INDICE)
        guardado = open(alvo, encoding="utf-8").read()
        bruto = json.loads(guardado)
        bruto["versao_do_esquema"] = 1
        with open(alvo, "w", encoding="utf-8") as saida:
            json.dump(bruto, saida)
        try:
            assert resumo(pasta, caminhos[0]) is None
        finally:
            with open(alvo, "w", encoding="utf-8") as volta:
                volta.write(guardado)

    def test_arquivo_que_mudou_de_tamanho_nao_serve(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])
        with open(caminhos[0], "ab") as cresce:
            cresce.write(b"|9999|9|\n")
        try:
            assert resumo(pasta, caminhos[0]) is None
        finally:
            dados = open(caminhos[0], "rb").read()
            with open(caminhos[0], "wb") as volta:
                volta.write(dados[: -len(b"|9999|9|\n")])

    def test_indice_que_nao_existe_devolve_nulo(self, tmp_path):
        assert resumo(str(tmp_path), str(tmp_path / "nao_existe.txt")) is None


class TestOIndiceCarregadoSoDoQuePrecisa:
    """A segunda metade do mesmo defeito, agora na extração.

    Extrair um alvo carregava as posições de **todos** os registros de todos os
    arquivos — 169.200.030 na #181, 205 s por alvo. A extração usa as de **um**
    registro; a de hierarquia não usa nenhuma, porque lê o arquivo em ordem.
    Seis alvos de bloco M viravam quarenta minutos, e o navegador desistia
    antes com "Não foi possível baixar a planilha".
    """

    def test_pedir_um_registro_traz_as_mesmas_posicoes_daquele_registro(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])

        inteiro = buscar(pasta, caminhos[0])
        filtrado = buscar(pasta, caminhos[0], ["C170"])

        assert list(filtrado.posicoes["C170"]) == list(inteiro.posicoes["C170"])

    def test_nao_traz_o_que_nao_foi_pedido(self, quebrado):
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])

        filtrado = buscar(pasta, caminhos[0], ["C170"])

        assert set(filtrado.posicoes) == {"C170"}, (
            "carregar o resto é exatamente o custo que esta mudança corta")

    def test_hierarquia_pede_nada_e_nada_vem(self, quebrado):
        """Lista vazia não é 'tudo': é 'nenhum'. A diferença são 205 s."""
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])

        assert buscar(pasta, caminhos[0], []).posicoes == {}

    def test_sem_pedido_continua_trazendo_tudo(self, quebrado):
        """A reindexação depende disto; só quem sabe o que quer filtra."""
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])

        assert set(buscar(pasta, caminhos[0]).posicoes) > {"C170"}

    def test_o_filtro_nao_encolhe_a_lista_de_indexados(self, quebrado):
        """Senão a mensagem de erro diria 'indexados: C170' para quem pediu
        C170 e não achou — justamente a informação que ele foi buscar."""
        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])

        assert buscar(pasta, caminhos[0], ["C170"]).indexados == \
            buscar(pasta, caminhos[0]).indexados

    def test_o_registro_ausente_ainda_lista_o_que_existe(self, quebrado):
        """O índice filtrado não pode empobrecer o diagnóstico."""
        from cat.infraestrutura.sped.extracao import RegistroNaoIndexado, registros

        destino, caminhos = quebrado
        pasta = _pasta_do_indice(destino, caminhos[0])
        indice = buscar(pasta, caminhos[0], ["C500"])      # não existe na base

        with pytest.raises(RegistroNaoIndexado, match="C170"):
            next(registros(caminhos[0], indice, "C500"))


class TestQuemDecideOQuePedir:
    def test_registro_simples_pede_as_posicoes_dele(self):
        from cat.infraestrutura.analitico.registros_do_sped import _posicoes_necessarias

        assert _posicoes_necessarias("C170") == ("C170",)

    def test_hierarquia_nao_pede_posicao_nenhuma(self):
        from cat.infraestrutura.analitico.registros_do_sped import (
            HIERARQUIAS,
            _posicoes_necessarias,
        )

        assert _posicoes_necessarias(HIERARQUIAS[0]) == ()
