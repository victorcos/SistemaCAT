"""Tirar do SPED o que se pede: um registro qualquer, ou o item inteiro.

Duas saídas, e elas custam coisas diferentes:

* **`registros()`** usa o índice: `seek` na posição e lê a linha. Serve para a
  tela mostrar a página 40 do C170 de um arquivo de 5 GB sem reler nada;
* **`itens_completos()`** faz uma passada sequencial e monta o join hierárquico
  do item — que é o que a apuração consome.

A segunda **não usa posição nenhuma**, e isso é de propósito. O join precisa de
tudo: as três tabelas do bloco 0, o estabelecimento, a nota e o item. Ler tudo
de uma vez em ordem é mais rápido que pular pelo arquivo, ainda mais em disco de
rede, onde cada `seek` é uma ida e volta. É a mesma conclusão a que
`analitico/extracao.py` chegou por conta própria.

## O join do item

```
0140 (estabelecimento) ── ligado pelo CNPJ do C010
└── C010
    └── C100 (a nota) ─── 0150 (participante) pelo COD_PART da nota
        └── C170 (o item) ┬ 0200 (a mercadoria) pelo COD_ITEM
                          └ 0400 (natureza)     pelo COD_NAT
```

As tabelas do bloco 0 vêm **antes** no arquivo — o leiaute garante —, então
montá-las durante a mesma passada funciona: quando o primeiro C170 aparece, as
três já estão completas. O C010 e o C100 são contexto corrente: valem até o
próximo aparecer.

## O enriquecimento

Além das colunas cruas, cada item sai com as colunas **traduzidas**: a descrição
do CFOP, o município do participante, o que cada indicador quer dizer, e a
natureza da base de cálculo do crédito. Nenhuma delas substitui a coluna crua —
todas são acrescentadas ao lado, para que quem confere possa ver o código e o
texto na mesma linha.

**A natureza do crédito vem do CFOP.** O C170 não tem campo `NAT_BC_CRED`, e a
regra foi validada contra 43.497 linhas de um relatório real e reconfirmada
contra outras 81.150, em vinte CFOP distintos, sem uma exceção. Saída não entra
no mapa de propósito: crédito de PIS/COFINS só se aplica a entrada.

Portado do projeto Quebra de SPED em 22/09/2026, com os nomes desta casa.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from cat.infraestrutura.sped.indice import IndiceDoArquivo
from cat.infraestrutura.sped.leitor import (
    BUFFER_DE_REDE,
    campos,
    campos_da_linha,
    registro_de,
)
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.infraestrutura.sped.tabelas import (
    tab_437,
    tab_cfop,
    tab_cfop_natureza_credito,
    tab_ind_escrit,
    tab_indicadores_c100,
    tab_municipio,
    tab_tipo_item,
)
from cat.log import obter_log

log = obter_log(__name__)


class RegistroNaoIndexado(KeyError):
    """Pediram posição de um registro que o índice não guardou."""


def registros(caminho: str, indice: IndiceDoArquivo, registro: str,
              de: int = 0, quantos: int | None = None) -> Iterator[list[str]]:
    """As linhas de um registro, pela posição guardada no índice.

    `de` e `quantos` paginam. É o que a tela usa: nenhuma base real cabe numa
    resposta, e reler o arquivo a cada página custaria minutos por clique.
    """
    guardadas = indice.posicoes.get(registro)
    if not guardadas:
        raise RegistroNaoIndexado(
            f"O registro {registro} não foi indexado neste arquivo. "
            f"Indexados: {', '.join(sorted(r for r, p in indice.posicoes.items() if p)) or 'nenhum'}."
        )
    fim = len(guardadas) if quantos is None else min(de + quantos, len(guardadas))
    with open(caminho, "rb") as arquivo:
        for i in range(de, fim):
            arquivo.seek(guardadas[i])
            yield campos_da_linha(arquivo.readline(), indice.codificacao)


def _nomeados(prefixo: str, valores: list[str], nomes: tuple[str, ...]) -> dict[str, str]:
    """Os campos com o nome do leiaute, prefixados pelo registro.

    Linha curta é o caso comum, não a exceção: o leiaute deixa campo final em
    branco e o gerador do cliente corta. Completar com vazio é o que evita um
    `IndexError` por causa de um COD_CTA que ninguém preencheu.
    """
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


# os registros que a passada do item olha; o resto da linha nem é decodificado
_DO_JOIN = {b"0140", b"0150", b"0200", b"0400", b"C010", b"C100", b"C170"}

# onde está a chave de cada tabela do bloco 0, na linha dela
_CHAVE_DA_TABELA = {b"0140": 3, b"0150": 1, b"0200": 1, b"0400": 1}


def itens_completos(caminho: str, codificacao: str) -> Iterator[dict[str, str]]:
    """Cada C170 com a nota, o estabelecimento e as tabelas do bloco 0.

    Uma passada só, sequencial. As colunas saem prefixadas pelo registro de
    origem — `C100_CHV_NFE`, `C170_CST_PIS`, `0200_COD_NCM` — para que nenhuma
    ambiguidade sobre de onde veio o número sobreviva à planilha.
    """
    nomes = {chave: nomes_dos_campos(chave)
             for chave in ("0140", "0150", "0200", "0400", "C010", "C100", "C170")}
    tabelas: dict[bytes, dict[str, list[str]]] = {r: {} for r in _CHAVE_DA_TABELA}
    estabelecimento: list[str] = []
    nota: list[str] = []
    lidos = 0

    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DO_JOIN:
                continue
            valores = campos(linha.decode(codificacao, errors="replace"))
            if (posicao := _CHAVE_DA_TABELA.get(registro)) is not None:
                if len(valores) > posicao:
                    tabelas[registro][valores[posicao]] = valores
                continue
            if registro == b"C010":
                estabelecimento = valores
                continue
            if registro == b"C100":
                nota = valores
                continue

            # C170: o item. Tudo o que ele precisa já passou antes dele
            cod_part = nota[3] if len(nota) > 3 else ""
            cod_item = valores[2] if len(valores) > 2 else ""
            cod_nat = valores[11] if len(valores) > 11 else ""
            cnpj = estabelecimento[1] if len(estabelecimento) > 1 else ""

            linha_pronta: dict[str, str] = {}
            linha_pronta.update(_nomeados("0140", tabelas[b"0140"].get(cnpj, []), nomes["0140"]))
            linha_pronta.update(_nomeados("C010", estabelecimento, nomes["C010"]))
            linha_pronta.update(_nomeados("C100", nota, nomes["C100"]))
            linha_pronta.update(_nomeados("0150", tabelas[b"0150"].get(cod_part, []), nomes["0150"]))
            linha_pronta.update(_nomeados("0400", tabelas[b"0400"].get(cod_nat, []), nomes["0400"]))
            linha_pronta.update(_nomeados("0200", tabelas[b"0200"].get(cod_item, []), nomes["0200"]))
            linha_pronta.update(_nomeados("C170", valores, nomes["C170"]))
            linha_pronta.update(_traduzido(linha_pronta, tabelas[b"0150"].get(cod_part, []),
                                           nomes["0150"]))
            lidos += 1
            yield linha_pronta

    log.info("itens do sped extraídos", extra={
        "arquivo": os.path.basename(caminho), "itens": lidos,
        "mercadorias": len(tabelas[b"0200"]), "participantes": len(tabelas[b"0150"]),
    })


# As colunas traduzidas, na ordem em que saem. Ficam **ao lado** das cruas, nunca
# no lugar delas: quem confere precisa ver o código e o texto na mesma linha.
#
# Os nomes são os do relatório de origem, com o sufixo `_DESC` onde ele o usa.
# Todo o resto deste relatório já sai com o nome de lá — `C170_CFOP`,
# `0200_COD_NCM` —, e trocar o nome só destas treze faria quem compara os dois
# lado a lado tropeçar sem ganhar nada.
TRADUZIDAS = (
    "PERIODO", "TIPO_OPERACAO_DESC", "INDICADOR_EMITENTE_DESC",
    "INDICADOR_ESCRITURACAO_DESC", "INDICADOR_PAGAMENTO_DESC",
    "INDICADOR_FRETE_DESC", "INDICADOR_MOVIMENTO_ITEM_DESC", "UF_ORIGEM_DESTINO",
    "MUNICIPIO", "TIPO_ITEM_DESC", "DESCRICAO_CFOP", "CFOP_FATURAMENTO",
    "NATUREZA_CREDITO",
)


def _competencia(bruto: str) -> str:
    """O primeiro dia do mês da data do documento, em dd/mm/aaaa.

    Mesmo formato que a 037 usa para o período (`entradas.py`), para que as duas
    planilhas agrupem pela mesma chave sem ninguém ter de converter nada.
    """
    b = (bruto or "").strip()
    if len(b) != 8 or not b.isdigit():
        return ""
    return f"01/{b[2:4]}/{b[4:]}"


def _rotulo_do_tipo(codigo: str) -> str:
    """O código e a descrição juntos — `00 Mercadoria para Revenda`."""
    codigo = (codigo or "").strip()
    descricao = tab_tipo_item.descricao(codigo) if codigo else ""
    return f"{codigo} {descricao}" if descricao else codigo


def _traduzido(linha: dict[str, str], participante: list[str],
               nomes_0150: tuple[str, ...]) -> dict[str, str]:
    """As colunas que traduzem código em texto, e a natureza do crédito.

    O município sai do 0150 do participante — que não tem campo de UF, só o
    código do IBGE; a UF vem dos dois primeiros dígitos dele, que é convenção
    pública e fixa.
    """
    cfop = linha.get("C170_CFOP", "")
    do_participante = dict(zip(nomes_0150, list(participante)
                               + [""] * max(0, len(nomes_0150) - len(participante))))
    municipio = do_participante.get("COD_MUN", "")
    uf_do_participante = tab_municipio.uf_do_municipio(municipio)
    uf_do_estabelecimento = linha.get("0140_UF", "")
    return {
        "PERIODO": _competencia(linha.get("C100_DT_DOC", "")),
        "TIPO_OPERACAO_DESC": tab_indicadores_c100.tipo_operacao(
            linha.get("C100_IND_OPER", "")),
        "INDICADOR_EMITENTE_DESC": tab_indicadores_c100.indicador_emitente(
            linha.get("C100_IND_EMIT", "")),
        "INDICADOR_ESCRITURACAO_DESC": tab_ind_escrit.rotulo(
            linha.get("C010_IND_ESCRIT", "")),
        "INDICADOR_PAGAMENTO_DESC": tab_indicadores_c100.indicador_pagamento(
            linha.get("C100_IND_PGTO", "")),
        "INDICADOR_FRETE_DESC": tab_indicadores_c100.indicador_frete(
            linha.get("C100_IND_FRT", "")),
        "INDICADOR_MOVIMENTO_ITEM_DESC": tab_indicadores_c100.indicador_movimento_item(
            linha.get("C170_IND_MOV", "")),
        "UF_ORIGEM_DESTINO": (f"{uf_do_participante}/{uf_do_estabelecimento}"
                              if (uf_do_participante or uf_do_estabelecimento) else ""),
        "MUNICIPIO": tab_municipio.descricao(municipio),
        "TIPO_ITEM_DESC": _rotulo_do_tipo(linha.get("0200_TIPO_ITEM", "")),
        "DESCRICAO_CFOP": tab_cfop.descricao(cfop),
        "CFOP_FATURAMENTO": tab_cfop_natureza_credito.cfop_faturamento(cfop),
        "NATUREZA_CREDITO": tab_437.rotulo(tab_cfop_natureza_credito.codigo(cfop)),
    }


def colunas_do_item() -> list[str]:
    """Os nomes das colunas que `itens_completos` produz, na ordem.

    Existe para quem grava parquet: o esquema tem de ser o mesmo desde a
    primeira linha, e descobri-lo lendo a primeira linha faria o arquivo vazio
    não ter esquema nenhum.
    """
    ordem = ("0140", "C010", "C100", "0150", "0400", "0200", "C170")
    cruas = [f"{prefixo}_{nome}" for prefixo in ordem for nome in nomes_dos_campos(prefixo)]
    return cruas + list(TRADUZIDAS)
