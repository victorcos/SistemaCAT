"""O pacote das exclusões: um zip com o consolidado e as quatro teses por item.

É um botão porque é um pedido. Quem recebe o cálculo põe os arquivos lado a lado
com os do escritório anterior e confere linha a linha — e isso só funciona se
tudo sair de uma vez, com o mesmo recorte, do mesmo instante. Cinco downloads em
cinco cliques são cinco oportunidades de misturar rodadas.

## O que vai dentro, e por que nessa ordem

```
Exclusoes - consolidado - todas as teses.xlsx   uma linha por grupo, as 4 teses
680 - PIS-Cofins da propria base - por item.csv     35 colunas, 100% conferido
903 - ICMS na base - por item.xlsx                  40 colunas, 100% conferido
839 - ICMS-ST presumido na base - por item.xlsx     46 colunas, 100% conferido
933 - ISS na base - por item.xlsx                   32 colunas, 100% conferido
LEIA-ME.txt
```

**O nome começa pelo número do relatório do MA** — 680, 903, 839, 933 — porque é
por esse número que quem confere acha o arquivo de referência correspondente.

## Por que o 680 vai em CSV, e os outros em xlsx

**Porque é o formato em que o MA o exporta.** O arquivo de referência da DMINAS
veio em CSV de 1,17 GB, e os do 839 e do 933 vieram em xlsx — e a razão é a
mesma nos dois casos: o 680 é o detalhe geral da receita e não cabe no Excel.

Medido no 680 da DMINAS, 3.568.362 linhas:

```
csv      33 s     862 MB
xlsx  1.181 s     512 MB     ← vinte minutos, em quatro abas
```

Vinte minutos é mais do que qualquer download espera, e um xlsx de meio giga não
abre no Excel nem quando chega. O CSV sai em trinta e três segundos, comprime
bem no zip, e é o que se carrega no DuckDB, no Power BI ou no banco — que é o
que se faz com três milhões e meio de linhas.

Os outros três cabem: o 839 tem 463.212 linhas, o 903 tem 138.358 e o 933 tem
33. Para eles o xlsx é o caminho de todo dia, e é o que o MA manda.

## As duas frentes da tese das contribuições, e o LEIA-ME

A tese 1 aparece **duas vezes**: consolidada, somada por grupo, e detalhada item
a item no 680. É de propósito, e os dois totais não batem: o consolidado
arredonda uma vez por grupo, com a alíquota efetiva daquele grupo, e o detalhe
arredonda por linha, como o MA. Na DMINAS a diferença é de 0,06% — cerca de
R$ 1,6 mil em R$ 2,7 milhões (decisão de 24/09/2026).

Quem abrir os dois vai subtrair um do outro. O `LEIA-ME.txt` existe para que
encontre a diferença **escrita**, e não a descubra achando que é defeito.

Ele também diz **o que faltou**: tese que não rodou não tem parquet, e um zip com
quatro arquivos onde deveriam haver cinco é indistinguível de um zip completo
para quem não participou da rodada.
"""

from __future__ import annotations

import os
import tempfile
import zipfile

from cat.infraestrutura.analitico.exclusao_do_icms import ARQUIVO_DA_EXCLUSAO_DO_ICMS
from cat.infraestrutura.analitico.exclusao_do_icms_st import (
    ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST,
)
from cat.infraestrutura.analitico.exclusao_do_iss import ARQUIVO_DA_EXCLUSAO_DO_ISS
from cat.infraestrutura.analitico.exclusao_piscofins_na_base import (
    ARQUIVO_DA_EXCLUSAO_PISCOFINS,
)
from cat.infraestrutura.analitico.exclusoes import ARQUIVO_DAS_EXCLUSOES
from cat.infraestrutura.planilhas.exclusao_do_icms import gerar_exclusao_do_icms
from cat.infraestrutura.planilhas.exclusao_do_icms_st import gerar_exclusao_do_icms_st
from cat.infraestrutura.planilhas.exclusao_do_iss import gerar_exclusao_do_iss
from cat.infraestrutura.planilhas.exclusao_piscofins_na_base import (
    gerar_exclusao_piscofins,
)
from cat.infraestrutura.planilhas.exclusoes import gerar_exclusoes
from cat.log import obter_log

log = obter_log(__name__)

LEIA_ME = "LEIA-ME.txt"

# o que entra no zip: nome dentro do pacote, parquet de origem, gerador, formato
# e a linha que o descreve no LEIA-ME. **A descrição vai sem acento**, porque é
# ela que entra no texto do pacote — ver `_leia_me`.
#
# O formato é o do arquivo de referência do MA, e a razão está no topo do módulo:
# o 680 não cabe no Excel, e os outros três cabem
PACOTE: tuple[tuple[str, str, object, str, str], ...] = (
    ("Exclusoes - consolidado - todas as teses.xlsx", ARQUIVO_DAS_EXCLUSOES,
     gerar_exclusoes, "xlsx",
     "as quatro teses somadas por grupo (estabelecimento, competencia, "
     "registro, CST e CFOP). E o numero que se pede."),
    ("680 - PIS-Cofins da propria base - por item.csv", ARQUIVO_DA_EXCLUSAO_PISCOFINS,
     gerar_exclusao_piscofins, "csv",
     "as proprias contribuicoes fora da base, item a item - 35 colunas, no "
     "leiaute do relatorio 680 (Metodologia 01). Em CSV porque e assim que o MA "
     "o exporta: nao cabe no Excel."),
    ("903 - ICMS na base - por item.xlsx", ARQUIVO_DA_EXCLUSAO_DO_ICMS,
     gerar_exclusao_do_icms, "xlsx",
     "o ICMS destacado fora da base, item a item - 40 colunas, no leiaute do "
     "relatorio 903 (Tema 69)."),
    ("839 - ICMS-ST presumido na base - por item.xlsx", ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST,
     gerar_exclusao_do_icms_st, "xlsx",
     "o ICMS-ST presumido fora da base, item a item - 46 colunas, no leiaute "
     "do relatorio 839."),
    ("933 - ISS na base - por item.xlsx", ARQUIVO_DA_EXCLUSAO_DO_ISS,
     gerar_exclusao_do_iss, "xlsx",
     "o ISS da nota de servico fora da base, item a item - 32 colunas, no "
     "leiaute do relatorio 933."),
)


def zip_das_exclusoes(parquet: str, destino: str, modelos=None, classificacoes=None,
                      formato: str = "zip") -> int:
    """Gera as cinco planilhas e as empacota. Devolve quantas entraram.

    `parquet` é o agregado das exclusões, e serve de **âncora**: os outros quatro
    moram na mesma pasta da execução. A assinatura é a de todo gerador de
    planilha desta casa, que recebe um parquet só.

    Tese que não rodou não tem parquet, e aí ela não entra e o `LEIA-ME.txt` diz
    que não entrou. O zip é montado em `.tmp` e renomeado no fim: pacote pela
    metade parece inteiro para quem o baixa.

    **As planilhas intermediárias nascem ao lado do zip**, e não no temp do
    sistema: o 680 de um atacadista tem 3,5 milhões de linhas e quatro abas, e
    sozinho passa de centenas de megabytes. Escrevê-lo no disco do sistema para
    depois copiá-lo é enchê-lo sem precisar; a pasta da execução já é o disco
    local que a rodada escolheu.
    """
    pasta = os.path.dirname(parquet)
    entraram: list[tuple[str, str]] = []
    faltaram: list[str] = []
    provisorio = destino + ".tmp"

    with tempfile.TemporaryDirectory(prefix="pacote_",
                                     dir=os.path.dirname(destino) or None) as temporaria:
        with zipfile.ZipFile(provisorio, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for nome, arquivo, gerar, formato_da_planilha, descricao in PACOTE:
                origem = os.path.join(pasta, arquivo)
                if not os.path.isfile(origem):
                    faltaram.append(nome)
                    log.warning("tese fora do pacote das exclusões: sem parquet",
                                extra={"arquivo": arquivo, "no_pacote": nome})
                    continue
                caminho = os.path.join(temporaria, nome)
                linhas = gerar(origem, caminho, formato=formato_da_planilha)
                z.write(caminho, arcname=nome)
                entraram.append((nome, descricao))
                log.info("planilha no pacote das exclusões",
                         extra={"no_pacote": nome, "linhas": linhas})
            z.writestr(LEIA_ME, _leia_me(entraram, faltaram))

    os.replace(provisorio, destino)
    log.info("pacote das exclusões montado", extra={
        "planilhas": len(entraram), "faltaram": len(faltaram), "zip": destino})
    return len(entraram)


def _leia_me(entraram: list[tuple[str, str]], faltaram: list[str]) -> str:
    """O texto que acompanha o pacote. **Sem acento, de propósito.**

    O zip grava o texto em UTF-8 e o Notepad antigo do Windows o abre como
    cp1252; em ASCII os dois concordam, e ninguém recebe um LEIA-ME ilegível.
    Fim de linha CRLF pelo mesmo motivo.
    """
    linhas = [
        "EXCLUSOES DA BASE DO PIS/COFINS",
        "=" * 70,
        "",
        "O que ha neste pacote:",
        "",
    ]
    for nome, descricao in entraram:
        linhas.append(f"  {nome}")
        linhas.append(f"      {descricao}")
        linhas.append("")

    if faltaram:
        linhas += [
            "O QUE NAO ENTROU",
            "-" * 70,
            "As teses abaixo nao foram apuradas nesta rodada, e por isso nao estao",
            "aqui. O motivo esta nos avisos da etapa, na tela.",
            "",
        ]
        linhas += [f"  {nome}" for nome in faltaram]
        linhas.append("")

    linhas += [
        "A TESE DAS CONTRIBUICOES APARECE DUAS VEZES, E E DE PROPOSITO",
        "-" * 70,
        "Ela sai consolidada (somada por grupo) no arquivo do consolidado, e",
        "detalhada item a item no 680. Os dois totais NAO batem, e nao e defeito:",
        "",
        "  - o consolidado arredonda uma vez por grupo, com a aliquota efetiva",
        "    daquele grupo. E o numero que se pede;",
        "  - o detalhe arredonda por linha, como o relatorio do MA faz, para que",
        "    a conferencia linha a linha seja possivel.",
        "",
        "Arredondar milhoes de itens um a um move o total. Na base em que a regra",
        "foi medida a diferenca ficou em 0,06% - cerca de R$ 1,6 mil em R$ 2,7",
        "milhoes. Se voce subtrair um do outro, e essa diferenca que vai achar.",
        "",
        "O 680 VAI EM CSV, E OS OUTROS EM XLSX",
        "-" * 70,
        "Porque e assim que o relatorio do MA sai. O 680 e o detalhe geral da",
        "receita e passa de tres milhoes de linhas: nao cabe no Excel, que para em",
        "pouco mais de um milhao. CSV com ponto-e-virgula e virgula decimal, que e",
        "o que o Excel em portugues espera - mas para abrir nao use dois cliques,",
        "e sim Dados > Obter Dados > De Texto/CSV, senao a chave de 44 digitos",
        "vira notacao cientifica. Para carregar em ferramenta (DuckDB, Power BI,",
        "banco), que e o uso natural de uma lista desse tamanho, ele ja esta no",
        "formato certo.",
        "",
        "AS QUATRO TESES NUNCA SE SOMAM NUM NUMERO SO",
        "-" * 70,
        "Sao pedidos diferentes, com fundamentos diferentes. Quem quiser o total",
        "geral que some, sabendo o que esta somando.",
        "",
        "O QUE PRESCREVEU APARECE E NAO SOMA",
        "-" * 70,
        "Competencia fora dos cinco anos sai marcada nas planilhas e fora do",
        "total do credito. O prazo conta do dia 25 do mes seguinte a competencia.",
        "",
        "A SELIC TEM DATA",
        "-" * 70,
        "A correcao acumula ate o mes da restituicao, que esta na coluna SELIC",
        "Acumulada de cada planilha por item. Rodar de novo no mes que vem da",
        "outro numero - maior, e certo.",
        "",
    ]
    return "\r\n".join(linhas)
