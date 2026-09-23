"""A planilha da Gestão: uma aba por tributo, larga como a do MA.

O parquet guarda longo — uma linha por (tributo, quadro, linha, competência) —
porque o esquema tem de ser o mesmo em todo trabalho. Aqui o longo vira largo,
que é como se lê: **uma coluna por mês**, os quadros empilhados na ordem, e o
rótulo recuado conforme o nível.

É o formato que o export da Gestão do MA usa, e não por gosto: é ele que
`tools/validar_gestao.py` compara linha a linha. Sair diferente obrigaria quem
confere a converter antes, e conversão à mão na hora de conferir é onde o erro
entra.

## Três coisas que a formatação tem de dizer

* **linha de título** — cabeçalho de subquadro, sem valor: sai em negrito e as
  células ficam vazias, não zeradas;
* **linha externa** — vem de fonte que o sistema não lê (DCTF, e-CAC): as
  células ficam **vazias e cinzas**, com nota no rótulo. Zero seria uma
  afirmação que não temos como fazer;
* **percentual** — o rateio de créditos não é dinheiro. Formatá-lo como real
  faria 85% virar R$ 0,85.
"""

from __future__ import annotations

import os

import pyarrow.parquet as pq
import xlsxwriter

from cat.infraestrutura.planilhas.conferencia import (
    CORPO_DA_FONTE,
    ESTILO_DO_CABECALHO,
    FONTE_DA_PLANILHA,
    FORMATOS,
    SEPARADOR_CSV,
)
from cat.log import obter_log

log = obter_log(__name__)

# a ordem em que as abas saem: o que veio da EFD primeiro, como no MA
ORDEM_DOS_TRIBUTOS = ("PIS", "COFINS", "IRPJ", "CSLL")

LARGURA_DO_ROTULO = 62
LARGURA_DA_COMPETENCIA = 16
RECUO_POR_NIVEL = 2


def _mes(competencia: str) -> str:
    """"2021-06" -> "JUN/2021", como a coluna do MA."""
    meses = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
             "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")
    try:
        ano, mes = competencia.split("-")[:2]
        return f"{meses[int(mes) - 1]}/{ano}"
    except (ValueError, IndexError):
        return competencia


def _ler(parquet: str) -> list[dict]:
    if not os.path.isfile(parquet):
        return []
    return pq.read_table(parquet).to_pylist()


def _por_tributo(linhas: list[dict]) -> dict[str, list[dict]]:
    saida: dict[str, list[dict]] = {}
    for linha in linhas:
        saida.setdefault(linha["tributo"], []).append(linha)
    return {t: saida[t] for t in ORDEM_DOS_TRIBUTOS if t in saida} | {
        t: v for t, v in saida.items() if t not in ORDEM_DOS_TRIBUTOS
    }


def _competencias(linhas: list[dict]) -> list[str]:
    return sorted({l["competencia"] for l in linhas})


def _quadros(linhas: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """Os quadros na ordem, cada um com as linhas dele em ordem.

    Agrupar por (quadro, ordem, rótulo) é o que junta as competências de volta
    numa linha só — que é exatamente o que o formato longo desfez.
    """
    agrupado: dict[tuple[str, int, str], dict] = {}
    titulos: dict[str, str] = {}
    ordem_dos_quadros: list[str] = []
    for linha in linhas:
        numero = linha["quadro"]
        if numero not in titulos:
            titulos[numero] = linha["quadro_titulo"]
            ordem_dos_quadros.append(numero)
        chave = (numero, linha["ordem"], linha["rotulo"])
        registro = agrupado.get(chave)
        if registro is None:
            registro = agrupado[chave] = {
                "rotulo": linha["rotulo"], "nivel": linha["nivel"],
                "titulo": linha["titulo"], "externo": linha["externo"],
                "unidade": linha["unidade"], "valores": {},
            }
        registro["valores"][linha["competencia"]] = linha["valor"]
    return [
        (numero, titulos[numero],
         [agrupado[c] for c in sorted(agrupado) if c[0] == numero])
        for numero in ordem_dos_quadros
    ]


def gerar_quadros(parquet: str, destino: str, modelos=None, classificacoes=None,
                  formato: str = "xlsx") -> int:
    """Escreve a Gestão. Devolve quantas linhas gravou."""
    if formato not in FORMATOS:
        raise ValueError(f"formato desconhecido: {formato}")
    linhas = _ler(parquet)
    if formato == "csv":
        return _csv(linhas, destino)
    return _xlsx(linhas, destino)


def _xlsx(linhas: list[dict], destino: str) -> int:
    pasta = os.path.dirname(os.path.abspath(destino))
    os.makedirs(pasta, exist_ok=True)
    livro = xlsxwriter.Workbook(destino, {"tmpdir": pasta})
    corpo = {"font_name": FONTE_DA_PLANILHA, "font_size": CORPO_DA_FONTE}
    f = {
        "cabecalho": livro.add_format(ESTILO_DO_CABECALHO),
        "quadro": livro.add_format({**corpo, "bold": True, "bg_color": "#EFF4FA",
                                    "border": 1, "valign": "vcenter", "text_wrap": True}),
        "rotulo": livro.add_format({**corpo, "num_format": "@"}),
        "rotulo_forte": livro.add_format({**corpo, "num_format": "@", "bold": True}),
        "rotulo_externo": livro.add_format({**corpo, "num_format": "@", "italic": True,
                                            "font_color": "#6D7F9D"}),
        "dinheiro": livro.add_format({**corpo, "num_format": "#,##0.00"}),
        "percentual": livro.add_format({**corpo, "num_format": "0.00%"}),
        "vazio": livro.add_format({**corpo, "bg_color": "#F5F7FA"}),
    }

    escritas = 0
    for tributo, doTributo in _por_tributo(linhas).items():
        competencias = _competencias(doTributo)
        aba = livro.add_worksheet(tributo[:31])
        aba.set_column(0, 0, LARGURA_DO_ROTULO)
        aba.set_column(1, len(competencias), LARGURA_DA_COMPETENCIA)
        aba.write(0, 0, "Descrição", f["cabecalho"])
        for i, competencia in enumerate(competencias, start=1):
            aba.write(0, i, _mes(competencia), f["cabecalho"])
        aba.freeze_panes(1, 1)

        atual = 1
        for numero, titulo, doQuadro in _quadros(doTributo):
            # o título do quadro atravessa a largura inteira: é uma faixa, não
            # uma linha de dado, e mesclar deixa isso visível de longe
            if competencias:
                aba.merge_range(atual, 0, atual, len(competencias), titulo, f["quadro"])
            else:
                aba.write(atual, 0, titulo, f["quadro"])
            atual += 1
            for linha in doQuadro:
                aba.write_string(atual, 0,
                                 " " * (RECUO_POR_NIVEL * int(linha["nivel"] or 0))
                                 + linha["rotulo"],
                                 _formatoDoRotulo(linha, f))
                for i, competencia in enumerate(competencias, start=1):
                    valor = linha["valores"].get(competencia)
                    if linha["titulo"] or linha["externo"] or valor is None:
                        aba.write_blank(atual, i, None, f["vazio"])
                        continue
                    if linha["unidade"] == "percentual":
                        aba.write_number(atual, i, valor / 1_000_000, f["percentual"])
                    else:
                        aba.write_number(atual, i, valor / 100, f["dinheiro"])
                atual += 1
                escritas += 1
            atual += 1  # uma linha em branco entre quadros

    if escritas == 0:
        # planilha sem aba nenhuma não abre no Excel
        vazia = livro.add_worksheet("Sem dados")
        vazia.write(0, 0, "Nenhum quadro foi apurado nesta rodada.", f["rotulo"])
    livro.close()
    log.info("planilha da gestão gerada", extra={
        "arquivo": os.path.basename(destino), "linhas": escritas,
        "tributos": len(_por_tributo(linhas)),
    })
    return escritas


def _formatoDoRotulo(linha: dict, f: dict):
    if linha["titulo"]:
        return f["rotulo_forte"]
    if linha["externo"]:
        return f["rotulo_externo"]
    return f["rotulo"]


def _csv(linhas: list[dict], destino: str) -> int:
    """O mesmo conteúdo em CSV, largo, com o tributo numa coluna.

    Não há aba em CSV, então o tributo vira coluna — quem abre no Excel filtra
    por ela e vê o mesmo que veria na aba.
    """
    pasta = os.path.dirname(os.path.abspath(destino))
    os.makedirs(pasta, exist_ok=True)
    competencias = _competencias(linhas)
    escritas = 0
    with open(destino, "w", encoding="utf-8-sig", newline="") as arquivo:
        cabecalho = ["Tributo", "Quadro", "Título do Quadro", "Descrição"]
        cabecalho += [_mes(c) for c in competencias]
        arquivo.write(SEPARADOR_CSV.join(cabecalho) + "\r\n")
        for tributo, doTributo in _por_tributo(linhas).items():
            for numero, titulo, doQuadro in _quadros(doTributo):
                for linha in doQuadro:
                    campos = [tributo, numero, titulo, linha["rotulo"].strip()]
                    for competencia in competencias:
                        valor = linha["valores"].get(competencia)
                        if linha["titulo"] or linha["externo"] or valor is None:
                            campos.append("")
                        elif linha["unidade"] == "percentual":
                            campos.append(f"{valor / 10_000:.4f}".replace(".", ","))
                        else:
                            campos.append(f"{valor / 100:.2f}".replace(".", ","))
                    arquivo.write(SEPARADOR_CSV.join(
                        c.replace(SEPARADOR_CSV, " ").replace("\n", " ") for c in campos) + "\r\n")
                    escritas += 1
    log.info("csv da gestão gerado", extra={
        "arquivo": os.path.basename(destino), "linhas": escritas})
    return escritas
