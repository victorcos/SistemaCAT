"""Arquivo do lote que saiu do disco tem de interromper a conferência.

O que aconteceu e o que estes testes impedem de repetir: no Amigão a pasta dos
94 relatórios de entrada saiu do servidor. `caminhos_do_projeto` devolve o que
está registrado no lote, sem conferir disco; cada `Leitura` estourou
`FileNotFoundError`, a falha caiu em `recusados`, e o resumo gravava só as 20
primeiras — sem total. A rodada terminou **concluída**, com 2,6 milhões de
chaves entregues a menos, e a lista do que cobrar cresceu 881.185 documentos
que o relatório do próprio cliente já cobria.

O erro é perigoso pelo sinal: faltar documento entregue sempre **aumenta** o
que se cobra. Nada falha, a lista fica maior, e maior parece "mais trabalho
encontrado" em vez de "evidência perdida".

Três garantias:
  1. `arquivos_ausentes` enxerga o que não está no disco;
  2. o relatório ausente entra em `ausentes`, não em `recusados` — conteúdo
     ruim e base incompleta são coisas diferentes;
  3. `_exigir_presenca` levanta antes de qualquer leitura, com mensagem que
     diz quantos, de que tipo e em que pasta.
"""

from __future__ import annotations

import duckdb
import pytest

from cat.aplicacao.casos_de_uso.conferir_documentos import (
    ArquivosDoLoteAusentes,
    _exigir_presenca,
)
from cat.infraestrutura.analitico.extracao import arquivos_ausentes, extrair_pasta

CHAVE = "41210544000002000237550010000446231411953286"

# o mesmo cabeçalho reduzido de test_conferencia_por_relatorio: o leitor
# identifica a espécie pelo cabeçalho, então um inventado seria recusado antes
# de a chave ser lida — e o teste mediria a coisa errada
CABECALHO_MOVIMENTO = (
    "Código|Descricao|Código Barras|Trib|Dt Emissão|Número Dcto|Ent|"
    "Qtde;Unitária|Valor|BC ICMS|Valor ICMS|Valor BC ST;Informada|"
    "Valor ST;Informada|Valor FCP ST|CNPJ/CPF|UF|CFOP;Mvto|CST;ICMS|"
    "BC ICMS ST;XML|VR. ICMS ST;XML|ST integral|Chave DFe"
)


def _item(chave: str, numero: str = "44623") -> str:
    return (f"1|Alface|789|0705|01/05/21|{numero}|1|160|280|280|0|0|0|0|"
            f"00176231110|PR|1.102|040|0|0|0|{chave}")


def _relatorio(tmp_path, nome: str = "2021.01 - Relatório de Entradas SP.txt"):
    caminho = tmp_path / nome
    caminho.write_bytes(
        ("\r\n".join([CABECALHO_MOVIMENTO, _item(CHAVE)]) + "\r\n").encode("latin-1"))
    return caminho


def test_arquivos_ausentes_separa_o_que_sumiu(tmp_path):
    existe = _relatorio(tmp_path)
    sumiu = tmp_path / "2021.02 - Relatório de Entradas SP.txt"

    assert arquivos_ausentes([str(existe)]) == []
    assert arquivos_ausentes([str(sumiu)]) == [str(sumiu)]
    # a ordem do que entra é preservada, e só o ausente volta
    assert arquivos_ausentes([str(existe), str(sumiu)]) == [str(sumiu)]


def test_exigir_presenca_passa_quando_tudo_esta_no_lugar(tmp_path):
    existe = _relatorio(tmp_path)
    _exigir_presenca([], [str(existe)])      # não levanta


def test_exigir_presenca_interrompe_e_diz_quantos_e_onde(tmp_path):
    pasta_morta = tmp_path / "1.Relatório Gerencial - Entradas"
    sumidos = [str(pasta_morta / f"2021.{m:02d} - Relatório de Entradas SP.txt")
               for m in (1, 2, 3)]

    with pytest.raises(ArquivosDoLoteAusentes) as erro:
        _exigir_presenca([], sumidos)

    msg = str(erro.value)
    assert "3 arquivo(s)" in msg
    assert "relatório gerencial" in msg
    # tem de dizer ONDE: é o que permite decidir entre repor e remover o lote
    assert "1.Relatório Gerencial - Entradas" in msg
    # e tem de dizer qual é o risco, não só que falhou
    assert "cobraria" in msg


def test_efd_ausente_tambem_interrompe(tmp_path):
    with pytest.raises(ArquivosDoLoteAusentes) as erro:
        _exigir_presenca([str(tmp_path / "sped-que-nao-existe.txt")], [])
    assert "1 arquivo(s)" in str(erro.value)
    assert "EFD" in str(erro.value)


def test_relatorio_ausente_vai_para_ausentes_e_nao_para_recusados(tmp_path):
    """A distinção importa: `recusados` é conteúdo ruim; `ausentes` é base incompleta."""
    bom = _relatorio(tmp_path)
    sumiu = tmp_path / "2021.02 - Relatório de Entradas SP.txt"
    destino = tmp_path / "pasta.parquet"

    progresso = extrair_pasta([], [str(bom), str(sumiu)], str(destino))

    assert [n for n in progresso.ausentes] == [sumiu.name]
    assert not [r for r in progresso.recusados if sumiu.name in r]
    # o que existia continuou sendo lido: um arquivo que sumiu não leva os outros
    assert progresso.documentos == 1
    chaves = duckdb.connect().execute(
        f"SELECT chave FROM '{destino.as_posix()}'").fetchall()
    assert chaves == [(CHAVE,)]
    # e os dois contam como vistos, senão a barra de progresso nunca fecha
    assert progresso.arquivos_lidos == 2
