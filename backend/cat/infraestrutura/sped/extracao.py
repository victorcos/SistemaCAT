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

Portado do projeto Quebra de SPED em 22/09/2026, com os nomes desta casa. O
enriquecimento que o original faz por cima — descrição de CFOP, natureza de
crédito, município — ficou de fora desta primeira fatia: são tabelas auxiliares
e não fazem falta para a exclusão do ICMS da base, que é o que motivou o porte.
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
            lidos += 1
            yield linha_pronta

    log.info("itens do sped extraídos", extra={
        "arquivo": os.path.basename(caminho), "itens": lidos,
        "mercadorias": len(tabelas[b"0200"]), "participantes": len(tabelas[b"0150"]),
    })


def colunas_do_item() -> list[str]:
    """Os nomes das colunas que `itens_completos` produz, na ordem.

    Existe para quem grava parquet: o esquema tem de ser o mesmo desde a
    primeira linha, e descobri-lo lendo a primeira linha faria o arquivo vazio
    não ter esquema nenhum.
    """
    ordem = ("0140", "C010", "C100", "0150", "0400", "0200", "C170")
    return [f"{prefixo}_{nome}"
            for prefixo in ordem
            for nome in nomes_dos_campos(prefixo)]
