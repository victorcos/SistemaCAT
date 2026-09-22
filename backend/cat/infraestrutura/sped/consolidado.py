"""O caminho consolidado: quando o contribuinte não escritura item a item.

Metade dos clientes desta casa escritura a EFD-Contribuições no **C170**, item a
item; a outra metade consolida por produto e CFOP, no **C180** (notas emitidas)
e no **C190** (notas adquiridas). A apuração tem de ler as duas formas, e é por
isso que este módulo existe ao lado de `extracao.itens_completos`.

## O grupo, e a armadilha dele

O pai traz produto, período e valor total; os filhos detalham PIS e COFINS por
CST e CFOP:

```
C010 (estabelecimento)
└── C180 (produto · período · total)      C190 (idem, nas aquisições)
    ├── C181 (PIS por CST e CFOP)         ├── C191 (PIS, e o participante)
    └── C185 (COFINS por CST e CFOP)      └── C195 (COFINS, e o participante)
```

**Os filhos não vêm intercalados.** Vêm *todos* os de PIS e só depois *todos* os
de COFINS — fato confirmado em dado real no projeto de origem, e a razão de este
módulo acumular em listas em vez de parear na hora. O `C181[i]` casa com o
`C185[i]` **pela posição**, e o grupo só fecha quando o próximo pai aparece ou o
arquivo acaba.

Tratar isso como 1:1:1 na leitura sequencial — que é a suposição natural — daria
um casamento torto sem erro nenhum: PIS de um CFOP somado com COFINS de outro.

**E o grupo não é 1:1 nem em quantidade.** Um C180 pode ter mais filhos que o
vizinho; em base com vários estabelecimentos, a contagem de C180 vem menor que a
de C181. Quando as duas listas têm tamanhos diferentes, sai uma linha por
posição existente, com o lado que faltou em branco — perder a linha seria perder
valor apurado.

Portado do projeto Quebra de SPED em 22/09/2026. Lá eram duas funções de ~150
linhas quase idênticas; aqui é uma só, porque C180 e C190 têm o mesmo leiaute e o
mesmo par de filhos — o que muda é o nome e o fato de os filhos do C190 trazerem
`COD_PART` (a aquisição sabe de quem se comprou; a venda consolidada não diz
para quem se vendeu).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass

from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.log import obter_log

log = obter_log(__name__)


@dataclass(frozen=True)
class Consolidacao:
    """Qual grupo consolidado se está lendo."""

    pai: str
    pis: str
    cofins: str
    # o que o grupo representa, para quem lê a planilha sem saber o leiaute
    rotulo: str


# as notas que a empresa emitiu, e as que ela adquiriu
EMITIDAS = Consolidacao("C180", "C181", "C185", "notas emitidas")
ADQUIRIDAS = Consolidacao("C190", "C191", "C195", "notas adquiridas")

# onde está a chave das tabelas do bloco 0 que o grupo usa
_CHAVE_DA_TABELA = {b"0200": 1, b"0500": 5}


def _nomeados(prefixo: str, valores: list[str], nomes: tuple[str, ...]) -> dict[str, str]:
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


def grupos_consolidados(caminho: str, codificacao: str,
                        qual: Consolidacao = ADQUIRIDAS) -> Iterator[dict[str, str]]:
    """Cada linha de consolidação com o par PIS/COFINS já casado.

    Uma passada sequencial, como o join do item. As colunas saem prefixadas pelo
    registro de origem — `C190_COD_ITEM`, `C191_CST_PIS`, `0200_COD_NCM` — para
    que não reste dúvida de onde veio cada número.
    """
    nomes = {chave: nomes_dos_campos(chave)
             for chave in ("0200", "0500", "C010", qual.pai, qual.pis, qual.cofins)}
    pai_b = qual.pai.encode("ascii")
    pis_b = qual.pis.encode("ascii")
    cofins_b = qual.cofins.encode("ascii")
    de_interesse = {pai_b, pis_b, cofins_b, b"C010", b"0200", b"0500"}

    tabelas: dict[bytes, dict[str, list[str]]] = {r: {} for r in _CHAVE_DA_TABELA}
    estabelecimento: list[str] = []
    pai: list[str] = []
    de_pis: list[list[str]] = []
    de_cofins: list[list[str]] = []
    grupos = linhas = 0

    def fechar() -> Iterator[dict[str, str]]:
        """Emite o grupo acumulado, casando os filhos pela posição."""
        nonlocal linhas
        if not pai:
            return
        for i in range(max(len(de_pis), len(de_cofins))):
            filho_pis = de_pis[i] if i < len(de_pis) else []
            filho_cofins = de_cofins[i] if i < len(de_cofins) else []
            # o COD_CTA pode vir de qualquer um dos dois lados
            conta = ""
            for filho, chave in ((filho_pis, qual.pis), (filho_cofins, qual.cofins)):
                if filho:
                    posicao = nomes[chave].index("COD_CTA")
                    if len(filho) > posicao and filho[posicao]:
                        conta = filho[posicao]
                        break
            cod_item = pai[4] if len(pai) > 4 else ""

            pronta: dict[str, str] = {}
            pronta.update(_nomeados("C010", estabelecimento, nomes["C010"]))
            pronta.update(_nomeados(qual.pai, pai, nomes[qual.pai]))
            pronta.update(_nomeados("0200", tabelas[b"0200"].get(cod_item, []), nomes["0200"]))
            pronta.update(_nomeados("0500", tabelas[b"0500"].get(conta, []), nomes["0500"]))
            pronta.update(_nomeados(qual.pis, filho_pis, nomes[qual.pis]))
            pronta.update(_nomeados(qual.cofins, filho_cofins, nomes[qual.cofins]))
            linhas += 1
            yield pronta

    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in de_interesse:
                continue
            valores = campos(linha.decode(codificacao, errors="replace"))
            if (posicao := _CHAVE_DA_TABELA.get(registro)) is not None:
                if len(valores) > posicao:
                    tabelas[registro][valores[posicao]] = valores
                continue
            if registro == b"C010":
                # o estabelecimento troca: o grupo aberto pertence ao anterior
                yield from fechar()
                pai, de_pis, de_cofins = [], [], []
                estabelecimento = valores
                continue
            if registro == pai_b:
                yield from fechar()
                pai, de_pis, de_cofins = valores, [], []
                grupos += 1
                continue
            if registro == pis_b:
                de_pis.append(valores)
            elif registro == cofins_b:
                de_cofins.append(valores)
        yield from fechar()

    log.info("consolidação do sped lida", extra={
        "arquivo": os.path.basename(caminho), "grupo": qual.pai, "o_que_e": qual.rotulo,
        "grupos": grupos, "linhas": linhas, "mercadorias": len(tabelas[b"0200"]),
    })


def colunas_do_consolidado(qual: Consolidacao = ADQUIRIDAS) -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet de arquivo vazio."""
    ordem = ("C010", qual.pai, "0200", "0500", qual.pis, qual.cofins)
    return [f"{prefixo}_{nome}"
            for prefixo in ordem
            for nome in nomes_dos_campos(prefixo)]
