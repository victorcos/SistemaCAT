"""O escritor de parquet em lotes, e a falha que ele escondeu por seis horas.

Em 05/10/2026 a apuração de PIS/COFINS de um cliente rodou das 20:27 às 02:56 e
morreu com:

    ArrowInvalid: Column 13 named participante
                  expected length 49365 but got length 49364

A mensagem fala de parquet, de pyarrow e de uma coluna por número — e **nada
disso era o problema**. O que houve foi: alguma coisa levantou dentro de
`escrever`, no meio do laço que apendava coluna a coluna; as doze primeiras
colunas ficaram com um valor a mais que as cinco seguintes; a exceção subiu até
o `finally` que fecha os escritores; e `fechar` levantou o erro do pyarrow **por
cima** da exceção original, que era a única que dizia o que tinha acontecido.

Seis horas e meia de leitura, e o que sobrou para diagnosticar foi um erro sobre
o tamanho de uma lista.

Estes testes cobram as duas metades da correção:

* `escrever` monta a linha inteira **antes** de encostar no lote, então uma
  exceção no meio não deixa o lote desemparelhado;
* se ainda assim ele desemparelhar, `fechar` **corta e segue**, em vez de
  levantar por cima de quem estava caindo. A linha incompleta seria lixo de
  qualquer jeito; o diagnóstico, não.
"""

from __future__ import annotations

import os

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.escrita import Escritor

COLUNAS = ["a", "b", "c"]


class ValorQueNaoViraTexto:
    """Um valor cujo `str()` levanta — o que quer que tenha sido, na prática."""

    def __str__(self) -> str:
        raise RuntimeError("este valor não vira texto")


def _ler(caminho: str) -> dict[str, list]:
    return pq.read_table(caminho).to_pydict()


class TestALinhaEntraInteiraOuNaoEntra:
    def test_a_excecao_no_meio_da_linha_nao_desemparelha_o_lote(self, tmp_path):
        caminho = str(tmp_path / "x.parquet")
        escritor = Escritor(caminho, COLUNAS)
        escritor.escrever({"a": "1", "b": "2", "c": "3"})

        with pytest.raises(RuntimeError, match="não vira texto"):
            escritor.escrever({"a": "4", "b": ValorQueNaoViraTexto(), "c": "6"})

        assert [len(v) for v in escritor.lote.values()] == [1, 1, 1], (
            "a linha que falhou não podia ter entrado pela metade")

    def test_a_linha_que_falhou_nao_conta_como_gravada(self, tmp_path):
        escritor = Escritor(str(tmp_path / "x.parquet"), COLUNAS)
        escritor.escrever({"a": "1", "b": "2", "c": "3"})

        with pytest.raises(RuntimeError):
            escritor.escrever({"a": "4", "b": ValorQueNaoViraTexto(), "c": "6"})

        assert escritor.gravadas == 1

    def test_depois_da_falha_o_arquivo_fecha_com_o_que_estava_bom(self, tmp_path):
        """**O ponto todo.** Quem chama põe `fechar()` num `finally`; se ele
        levantar, a exceção de verdade morre ali."""
        caminho = str(tmp_path / "x.parquet")
        escritor = Escritor(caminho, COLUNAS)

        try:
            escritor.escrever({"a": "1", "b": "2", "c": "3"})
            escritor.escrever({"a": "4", "b": ValorQueNaoViraTexto(), "c": "6"})
        except RuntimeError:
            pass
        finally:
            escritor.fechar()

        assert _ler(caminho) == {"a": ["1"], "b": ["2"], "c": ["3"]}


class TestOFinallyNaoDestroiODiagnostico:
    """A metade que importa de verdade: qual exceção chega a quem lê a tela."""

    def test_a_excecao_original_sobrevive_ao_fechar(self, tmp_path):
        escritor = Escritor(str(tmp_path / "x.parquet"), COLUNAS)

        with pytest.raises(RuntimeError, match="não vira texto"):
            try:
                escritor.escrever({"a": "1", "b": ValorQueNaoViraTexto(), "c": "3"})
            finally:
                # era aqui que o ArrowInvalid nascia e enterrava o RuntimeError
                escritor.fechar()

    def test_lote_desemparelhado_corta_e_segue_em_vez_de_levantar(self, tmp_path, caplog):
        """Mesmo que algo desemparelhe o lote por outro caminho, `fechar` não
        pode levantar: quem está caindo já tem um erro melhor para contar."""
        caminho = str(tmp_path / "x.parquet")
        escritor = Escritor(caminho, COLUNAS)
        escritor.escrever({"a": "1", "b": "2", "c": "3"})
        escritor.lote["a"].append("sobrando")   # o estado que derrubava tudo

        escritor.fechar()

        assert _ler(caminho) == {"a": ["1"], "b": ["2"], "c": ["3"]}, (
            "as linhas completas têm de ser gravadas")
        assert any("desemparelhado" in r.message for r in caplog.records), (
            "cortar em silêncio seria trocar um erro barulhento por um sumiço")


class TestOQueJaFuncionavaContinua:
    def test_grava_o_que_recebeu_na_ordem_das_colunas(self, tmp_path):
        caminho = str(tmp_path / "x.parquet")
        escritor = Escritor(caminho, COLUNAS)
        escritor.escrever({"a": "1", "b": "2", "c": "3"})
        escritor.escrever({"c": "9", "a": "7", "b": "8"})
        escritor.fechar()

        assert _ler(caminho) == {"a": ["1", "7"], "b": ["2", "8"], "c": ["3", "9"]}

    def test_campo_ausente_vira_vazio_e_nao_some(self, tmp_path):
        caminho = str(tmp_path / "x.parquet")
        escritor = Escritor(caminho, COLUNAS)
        escritor.escrever({"a": "1"})
        escritor.fechar()

        assert _ler(caminho) == {"a": ["1"], "b": [""], "c": [""]}

    def test_trabalho_sem_nenhuma_linha_ainda_produz_arquivo_legivel(self, tmp_path):
        """O esquema vem de fora justamente para isto — ver o docstring."""
        caminho = str(tmp_path / "x.parquet")
        Escritor(caminho, COLUNAS).fechar()

        assert os.path.exists(caminho)
        assert pq.read_table(caminho).column_names == COLUNAS
