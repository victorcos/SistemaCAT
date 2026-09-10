"""As duas planilhas que saem da conferência.

Regras de Excel desta casa (ARQUITETURA §9), e cada uma existe por um motivo
que já custou retrabalho:

* **acima de 900 mil linhas, quebrar em abas.** O limite do Excel é pouco mais
  de um milhão, e estourar não dá erro: corta o resto em silêncio;
* **memória constante.** A lista de cobrança de uma base grande passa de um
  milhão de linhas; montar tudo em memória antes de gravar derruba o processo;
* **identificador com zero à esquerda vai como texto.** Chave de acesso, CNPJ e
  série viram número e perdem o zero — e chave de 44 dígitos vira notação
  científica, que é pior: parece certa e não é;
* **valor e data vão tipados**, senão não se soma nem se monta dinâmica, e o
  cliente que recebe a cobrança não consegue conferir o total.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pyarrow.parquet as pq
import xlsxwriter

from cat.log import obter_log

log = obter_log(__name__)

LIMITE_POR_ABA = 900_000
LINHAS_POR_LEITURA = 50_000


@dataclass(frozen=True)
class Coluna:
    campo: str
    titulo: str
    tipo: str = "texto"      # texto | numero | data
    largura: int = 16


COLUNAS_SEM_DOCUMENTO = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "data", 13),
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("modelo", "Modelo", "texto", 9),
    Coluna("serie", "Série", "texto", 8),
    Coluna("numero", "Número", "texto", 12),
    Coluna("data", "Emissão", "data", 12),
    Coluna("valor", "Valor do documento", "numero", 18),
    Coluna("operacao", "Operação", "texto", 11),
    Coluna("emitente", "Emitente", "texto", 14),
    Coluna("participante", "Cód. participante", "texto", 18),
    Coluna("situacao", "Situação", "texto", 10),
    Coluna("arquivo_efd", "Arquivo da EFD", "texto", 34),
)

COLUNAS_NAO_ESCRITURADAS = (
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("origem", "Origem", "texto", 20),
    Coluna("arquivo", "Arquivo", "texto", 44),
)

_ROTULO_SITUACAO = {
    "00": "Regular", "01": "Regular, extemporâneo", "02": "Cancelado",
    "03": "Cancelado, extemporâneo", "04": "Denegado",
    "05": "Numeração inutilizada", "06": "Complementar",
    "07": "Complementar, extemporâneo", "08": "Regime especial",
}
_ROTULO_ORIGEM = {"xml": "XML", "gerencial": "Relatório do cliente"}
_ROTULO_OPERACAO = {"entrada": "Entrada", "saida": "Saída"}
_ROTULO_EMITENTE = {"propria": "Emissão própria", "terceiros": "Terceiros"}

_TRADUCOES = {
    "situacao": _ROTULO_SITUACAO,
    "origem": _ROTULO_ORIGEM,
    "operacao": _ROTULO_OPERACAO,
    "emitente": _ROTULO_EMITENTE,
}


def gerar(parquet: str, destino: str, colunas: tuple[Coluna, ...],
          titulo_da_aba: str, somente_cobraveis: bool = False,
          modelos: frozenset[str] | None = None) -> int:
    """Escreve o xlsx a partir do parquet. Devolve quantas linhas gravou.

    `modelos` restringe por modelo de documento, e não é detalhe: numa base
    real desta casa, 307.319 dos 321.337 documentos eram NFC-e. Cobrar do
    cliente o XML de cada cupom de consumidor não é trabalho que alguém vá
    fazer, e a planilha inteira perderia serventia por causa do volume.
    """
    livro = xlsxwriter.Workbook(destino, {
        "constant_memory": True,        # não segura a planilha em memória
        "default_date_format": "dd/mm/yyyy",
    })
    cabecalho = livro.add_format({
        "bold": True, "bg_color": "#021D44", "font_color": "#FFFFFF",
        "border": 1, "align": "left", "valign": "vcenter",
    })
    texto = livro.add_format({"num_format": "@"})
    dinheiro = livro.add_format({"num_format": "#,##0.00"})
    dia = livro.add_format({"num_format": "dd/mm/yyyy"})
    formatos = {"texto": texto, "numero": dinheiro, "data": dia}

    aba = _abrir_aba(livro, titulo_da_aba, 1, colunas, cabecalho)
    escritas = 0
    na_aba = 0
    abas = 1

    for lote in pq.ParquetFile(parquet).iter_batches(LINHAS_POR_LEITURA):
        registros = lote.to_pylist()
        for r in registros:
            if somente_cobraveis and not r.get("cobravel", True):
                continue
            if modelos is not None and r.get("modelo") not in modelos:
                continue
            if na_aba >= LIMITE_POR_ABA:
                abas += 1
                aba = _abrir_aba(livro, titulo_da_aba, abas, colunas, cabecalho)
                na_aba = 0
            _escrever(aba, na_aba + 1, r, colunas, formatos)
            na_aba += 1
            escritas += 1

    livro.close()
    log.info("planilha gerada",
             extra={"arquivo": os.path.basename(destino), "linhas": escritas,
                    "abas": abas})
    return escritas


def _abrir_aba(livro, titulo: str, numero: int, colunas: tuple[Coluna, ...],
               formato_cabecalho):
    nome = titulo if numero == 1 else f"{titulo} ({numero})"
    aba = livro.add_worksheet(nome[:31])
    for i, coluna in enumerate(colunas):
        aba.set_column(i, i, coluna.largura)
        aba.write(0, i, coluna.titulo, formato_cabecalho)
    aba.freeze_panes(1, 0)
    return aba


def _escrever(aba, linha: int, registro: dict, colunas: tuple[Coluna, ...],
              formatos: dict) -> None:
    for i, coluna in enumerate(colunas):
        valor = registro.get(coluna.campo)
        if valor is None or valor == "":
            continue
        traducao = _TRADUCOES.get(coluna.campo)
        if traducao:
            aba.write_string(linha, i, traducao.get(str(valor), str(valor)),
                             formatos["texto"])
        elif coluna.tipo == "data" and isinstance(valor, date):
            aba.write_datetime(linha, i, valor, formatos["data"])
        elif coluna.tipo == "numero":
            aba.write_number(linha, i, float(valor if isinstance(valor, Decimal)
                                             else valor), formatos["numero"])
        else:
            # tudo o mais é identificador: vai como texto para não perder zero
            aba.write_string(linha, i, str(valor), formatos["texto"])


def gerar_sem_documento(parquet: str, destino: str,
                        modelos: frozenset[str] | None = None) -> int:
    """A planilha de cobrança: só o que faz sentido pedir ao cliente."""
    return gerar(parquet, destino, COLUNAS_SEM_DOCUMENTO,
                 "Notas a cobrar", somente_cobraveis=True, modelos=modelos)


def gerar_nao_escrituradas(parquet: str, destino: str,
                           modelos: frozenset[str] | None = None) -> int:
    # o parquet das não escrituradas não tem modelo: a chave veio da pasta,
    # e o que se sabe dela é a origem
    return gerar(parquet, destino, COLUNAS_NAO_ESCRITURADAS,
                 "Não escrituradas")
