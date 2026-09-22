"""A Ficha 3 volta editada: o que mudou, antes de gravar.

Esta é a **porta da planilha** da correção à mão. A pessoa baixa a Ficha 3 no
leiaute do papel de trabalho, corrige o que o sistema deduziu errado — alíquota,
redução, enquadramento, quantidade, valor, ICMS suportado —, escreve o motivo na
última coluna e sobe o arquivo de volta. Aqui o arquivo é comparado com o
parquet que o gerou, linha a linha, e o que sai é a **lista do que mudou**: de
que valor para que valor, em que linha da planilha, com o motivo escrito.

Nada é gravado aqui. Este módulo lê e confere; quem grava é a API em C#, depois
de a pessoa ver o diff na tela e confirmar. É de propósito: subir planilha e
gravar no mesmo gesto é como se perde o controle de uma base — uma coluna
arrastada no Excel viraria dez mil correções silenciosas.

## Como a linha é reconhecida

Pelo que o leiaute já mostra: CNPJ, código da mercadoria, chave (ou número do
documento, quando não há chave) e número do item. É a mesma chave com que o
razão aplica a correção (`_correcoes`, em `analitico/razao.py`), e é por isso
que a ordem das linhas não importa: quem ordena, filtra ou apaga linhas no Excel
continua sendo entendido. O que não se pode é mexer nas colunas de
identificação — e, se mexer, a linha volta como erro em vez de virar correção de
outro lugar.

## O motivo manda

Linha sem motivo escrito não vira correção, mesmo que o valor tenha mudado: a
regra é do domínio (`cat.dominio.icms.cat42.correcao`) e vale igual nas três portas.
Por isso a conferência só reclama de linha que **não foi achada na ficha** quando
ela tem motivo — numa planilha de dois milhões de linhas, acusar cada uma que
não casou daria dois milhões de erros para ler e nenhum deles útil.

## O que a planilha **não** faz

**Reincluir linha tirada.** A linha excluída sai da ficha e, portanto, sai da
planilha: não há linha para destildar. Trazer de volta é desfazer a correção na
tela, que é onde ela fica listada.

**Corrigir linha de relatório de PDV.** Ela não tem chave nem número de item —
não há como apontar para uma venda específica. O domínio recusa, e aqui a linha
volta como erro dizendo isso.

## Tolerância na comparação

O xlsx guarda número como float; o parquet, como decimal. Comparar por igualdade
acusaria milhares de mudanças que ninguém fez. Cada campo tem a tolerância de
meia unidade da última casa que ele mostra, e diferença menor que isso é o
arredondamento do Excel, não correção.
"""

from __future__ import annotations

import csv
import itertools
import os
from dataclasses import dataclass, field

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.icms.cat42.correcao import (
    CORRECOES_POR_PEDIDO,
    Alvo,
    Campo,
    CorrecaoInvalida,
    validar,
)
from cat.infraestrutura.planilhas.conferencia import SEPARADOR_CSV, _literal
from cat.infraestrutura.planilhas.razao import COLUNAS_FICHA3
from cat.log import obter_log

log = obter_log(__name__)


@dataclass(frozen=True)
class Editavel:
    """Uma coluna que a pessoa pode mexer, e como conferi-la.

    `na_ficha` é o SQL que dá o valor que o sistema pôs naquela célula, sobre a
    tabela do casamento (`pares`, apelidada `e`). `tolerancia` é meia unidade da
    última casa decimal que a coluna mostra: abaixo disso é arredondamento do
    Excel, não correção. O enquadramento é inteiro e não tem casa nenhuma.
    """

    coluna: str                 # o campo da coluna no leiaute (planilhas/razao.py)
    campo: Campo
    na_ficha: str
    tolerancia: float = 0.0
    sim_ou_nao: bool = False    # "sim"/"não" em vez de número


EDITAVEIS: tuple[Editavel, ...] = (
    Editavel("aliquota", Campo.ALIQUOTA, "e.f_aliquota", 0.00005),
    Editavel("reducao_base", Campo.REDUCAO_BASE, "e.f_reducao_base", 0.00005),
    Editavel("cod_legal", Campo.ENQUADRAMENTO, "e.f_enquadramento"),
    Editavel("qtd_entrada", Campo.QUANTIDADE,
             "CASE WHEN e.f_especie = 'entrada' THEN abs(e.f_quantidade) END", 0.0000005),
    Editavel("qtd_saida", Campo.QUANTIDADE,
             "CASE WHEN e.f_especie = 'saida' THEN abs(e.f_quantidade) END", 0.0000005),
    Editavel("valor_item", Campo.VALOR_ITEM, "e.f_valor_item", 0.0000005),
    Editavel("suportado_entrada", Campo.ICMS_SUPORTADO,
             "CASE WHEN e.f_especie = 'entrada' THEN e.f_icms_suportado END", 0.0000005),
    Editavel("tirar_da_ficha", Campo.EXCLUIDA, "'nao'", sim_ou_nao=True),
)

# as colunas da ficha que a comparação lê, e o nome delas dentro de `pares`
DA_FICHA = ("aliquota", "reducao_base", "enquadramento", "quantidade", "valor_item",
            "icms_suportado", "especie")

# o que a planilha escreve para dizer "sim" nas colunas de sim/não. O Excel
# devolve booleano quando a célula é fórmula, e "x" é o que se marca à mão
SIM = ("sim", "s", "x", "1", "true", "v")

# a coluna do motivo: não se compara com nada, é o que justifica as outras
COLUNA_DO_MOTIVO = "motivo_da_correcao"

# as colunas que dizem QUAL linha é. Mexer nelas não é corrigir: é apontar para
# outra linha, e o que não bate volta como erro, nunca como correção de outro lugar
CHAVE = ("cnpj", "codigo", "chave", "numero_documento", "numero_item")

# quantas linhas de planilha se aceita ler de uma vez, e de quantas em quantas
# elas caem no parquet de rascunho
LINHAS_MAXIMAS = 2_000_000
LINHAS_POR_LOTE = 50_000

# quantos erros e avisos voltam para a tela. Quem subiu a planilha do razão
# errado não precisa ler dois milhões de linhas para descobrir isso
NA_LISTA = 200

# quantas linhas se olha procurando o cabeçalho, e quantos títulos têm de bater
# para a linha ser o cabeçalho. O da Ficha 3 tem três linhas (faixa, título,
# número do campo); a folga cobre quem inseriu uma linha de anotação em cima
LINHAS_DO_CABECALHO = 12
TITULOS_MINIMOS = 6

EXTENSOES = (".xlsx", ".xlsm", ".csv")

ARQUIVO_DE_RASCUNHO = "correcoes_enviadas.parquet"


class PlanilhaIlegivel(ValueError):
    """O arquivo não é a Ficha 3 desta casa, e adivinhar seria pior."""


@dataclass
class Conferencia:
    """O que a planilha diz que mudou, pronto para a tela mostrar."""

    correcoes: list[dict] = field(default_factory=list)
    erros: list[dict] = field(default_factory=list)
    avisos: list[dict] = field(default_factory=list)
    linhas_lidas: int = 0
    abas: list[str] = field(default_factory=list)
    nao_achadas: int = 0
    truncado: bool = False

    def como_json(self) -> dict:
        return {
            "correcoes": self.correcoes,
            "erros": self.erros[:NA_LISTA],
            "avisos": self.avisos[:NA_LISTA],
            "linhas_lidas": self.linhas_lidas,
            "abas": self.abas,
            "nao_achadas": self.nao_achadas,
            "total": len(self.correcoes),
            "total_de_erros": len(self.erros),
            "limite": CORRECOES_POR_PEDIDO,
            "truncado": self.truncado,
        }


# ---------------------------------------------------------------------------
# ler o arquivo
# ---------------------------------------------------------------------------
_ACENTOS = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                         "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")


def _sem_acento(texto: str) -> str:
    """Título comparável, sem depender de acento nem de espaço a mais.

    O Excel troca espaço por quebra de linha ao ajustar a coluna, e quem copia o
    cabeçalho à mão perde um acento. Nenhum dos dois deveria custar a leitura.
    """
    return " ".join(str(texto).translate(_ACENTOS).casefold().split())


# o título como o xlsx o escreve e como o CSV o escreve. No xlsx o número do
# campo vai numa linha própria; no CSV, colado no título ("Chave (3)"), porque
# lá não há linha de baixo. Os dois têm de ser reconhecidos: a Ficha 3 volta
# editada nos dois formatos
_TITULOS = {_sem_acento(t): c.campo for c in COLUNAS_FICHA3
            for t in (c.titulo, c.titulo_no_csv)}


def _texto_da_celula(valor) -> str:
    """A célula como texto, sem o que o Excel inventa.

    Float inteiro vira inteiro: sem isto o número do item viria "2.0" e o código
    da mercadoria, "4002.0" — e nenhum dos dois casaria com a ficha.
    """
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "nao"
    if isinstance(valor, float):
        inteiro = int(valor)
        return str(inteiro) if valor == inteiro else repr(valor)
    return str(valor).strip()


def _cabecalho(linhas: list[list], onde_estou: str) -> tuple[int, dict[str, int]]:
    """Acha a linha dos títulos e o índice de cada coluna conhecida."""
    melhor: tuple[int, dict[str, int]] = (-1, {})
    for numero, linha in enumerate(linhas):
        achadas: dict[str, int] = {}
        for i, celula in enumerate(linha):
            campo = _TITULOS.get(_sem_acento(_texto_da_celula(celula)))
            if campo and campo not in achadas:
                achadas[campo] = i
        if len(achadas) > len(melhor[1]):
            melhor = (numero, achadas)
    if len(melhor[1]) < TITULOS_MINIMOS:
        raise PlanilhaIlegivel(
            f"Não achei o cabeçalho da Ficha 3 {onde_estou}. Suba a planilha como o sistema a "
            "gera, com a linha de títulos no lugar.")
    faltam = {c for c in CHAVE if c not in melhor[1]}
    if {"cnpj", "codigo"} & faltam or {"chave", "numero_documento"} <= faltam:
        raise PlanilhaIlegivel(
            "A planilha perdeu as colunas que dizem qual é a linha (CNPJ do Estabelecimento, "
            "Código da Mercadoria, Chave e Número do Documento). Sem elas não dá para saber o "
            "que corrigir.")
    return melhor[0], melhor[1]


def _e_linha_de_numeros(linha: list, onde: dict[str, int]) -> bool:
    """A linha de "(1) (2) (3)" que fica abaixo dos títulos não é dado."""
    vistos = [_texto_da_celula(linha[i]) for i in onde.values() if i < len(linha)]
    preenchidos = [v for v in vistos if v]
    return bool(preenchidos) and all(v.startswith("(") and v.endswith(")") for v in preenchidos)


def _abas_do_arquivo(caminho: str) -> list[tuple[str, object]]:
    """Cada aba como (nome, fábrica de linhas). CSV é uma aba só.

    A Ficha 3 quebra em abas acima de 900 mil linhas, e quem sobe a planilha
    inteira sobe todas: ler só a primeira perderia o resto em silêncio.
    """
    if caminho.lower().endswith(".csv"):
        def do_csv():
            with open(caminho, encoding="utf-8-sig", newline="") as f:
                yield from csv.reader(f, delimiter=SEPARADOR_CSV)
        return [("csv", do_csv)]
    try:
        from openpyxl import load_workbook
    except ImportError as erro:                                    # pragma: no cover
        raise PlanilhaIlegivel(
            "O motor não tem leitor de xlsx instalado. Suba a Ficha 3 em CSV.") from erro
    try:
        livro = load_workbook(caminho, read_only=True, data_only=True)
    except Exception as erro:
        raise PlanilhaIlegivel(f"Não consegui abrir a planilha: {erro}") from erro
    return [(aba.title, (lambda a=aba: (list(linha) for linha in a.iter_rows(values_only=True))))
            for aba in livro.worksheets]


def _esquema_da_enviada() -> pa.Schema:
    return pa.schema(
        [("aba", pa.string()), ("linha", pa.int64()),
         ("cnpj", pa.string()), ("codigo", pa.string()), ("documento", pa.string()),
         ("numero_item", pa.int32()), ("motivo", pa.string())]
        + [(e.coluna, pa.string()) for e in EDITAVEIS])


def _escrever_enviada(caminho: str, rascunho: str, conferencia: Conferencia) -> str | None:
    """Despeja a planilha num parquet com as colunas que interessam.

    Só o que identifica a linha e o que se pode corrigir: a Ficha 3 tem 49
    colunas e as outras 40 não entram na comparação. Devolve o caminho do
    parquet, ou nulo quando não havia linha nenhuma.
    """
    esquema = _esquema_da_enviada()
    escritor = pq.ParquetWriter(rascunho, esquema)
    lote: dict[str, list] = {c: [] for c in esquema.names}
    campos = ("cnpj", "codigo", "chave", "numero_documento", "numero_item", COLUNA_DO_MOTIVO,
              *(e.coluna for e in EDITAVEIS))
    total = 0
    try:
        for nome, fabrica in _abas_do_arquivo(caminho):
            if total >= LINHAS_MAXIMAS:
                conferencia.truncado = True
                break
            linhas = fabrica()
            inicio = [list(linha) for _, linha in zip(range(LINHAS_DO_CABECALHO), linhas)]
            try:
                titulo, onde = _cabecalho(inicio, f'na aba "{nome}"')
            except PlanilhaIlegivel as erro:
                # aba de anotação do cliente ao lado da Ficha 3: ignorá-la é
                # melhor que recusar o arquivo, desde que outra aba sirva
                conferencia.avisos.append({"aba": nome, "linha": 0, "mensagem": str(erro)})
                continue
            conferencia.abas.append(nome)
            resto = inicio[titulo + 1:]
            if resto and _e_linha_de_numeros(resto[0], onde):
                resto = resto[1:]
                titulo += 1
            indices = [onde.get(c) for c in campos]
            for deslocamento, linha in enumerate(itertools.chain(resto, linhas)):
                if total >= LINHAS_MAXIMAS:
                    conferencia.truncado = True
                    break
                celulas = [_texto_da_celula(linha[i]) if i is not None and i < len(linha) else ""
                           for i in indices]
                cnpj, codigo, chave, numero_documento, item, motivo = celulas[:6]
                documento = chave or numero_documento
                if not cnpj and not codigo and not documento:
                    continue                          # linha em branco no fim da aba
                total += 1
                lote["aba"].append(nome)
                lote["linha"].append(titulo + 2 + deslocamento)
                lote["cnpj"].append(_so_digitos(cnpj))
                lote["codigo"].append(codigo)
                lote["documento"].append(documento)
                lote["numero_item"].append(_inteiro(item))
                lote["motivo"].append(motivo)
                for editavel, valor in zip(EDITAVEIS, celulas[6:]):
                    lote[editavel.coluna].append(valor)
                if len(lote["linha"]) >= LINHAS_POR_LOTE:
                    escritor.write_table(pa.Table.from_pydict(lote, schema=esquema))
                    lote = {c: [] for c in esquema.names}
        if lote["linha"]:
            escritor.write_table(pa.Table.from_pydict(lote, schema=esquema))
    finally:
        escritor.close()
    conferencia.linhas_lidas = total
    if not total:
        os.remove(rascunho)
        return None
    return rascunho


def _so_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _inteiro(texto: str) -> int | None:
    try:
        return int(float(texto.replace(",", ".")))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# comparar com a ficha
# ---------------------------------------------------------------------------
def _diferente(editavel: Editavel) -> str:
    """O SQL que diz se a célula enviada difere do que o sistema calculou."""
    enviado = f'nullif(trim(e."{editavel.coluna}"), \'\')'
    if editavel.sim_ou_nao:
        # "tirar da ficha" não tem "antes": a linha está na ficha, e o que a
        # célula diz é se ela sai. Só o sim é mudança
        lista = ", ".join(f"'{s}'" for s in SIM)
        return f"lower(coalesce({enviado}, '')) IN ({lista})"
    numero = f"TRY_CAST(replace({enviado}, ',', '.') AS DOUBLE)"
    sistema = f"TRY_CAST({editavel.na_ficha} AS DOUBLE)"
    return (f"{numero} IS NOT NULL "
            f"AND ({sistema} IS NULL OR abs({numero} - {sistema}) > {editavel.tolerancia})")


def _selecao(editavel: Editavel) -> str:
    de = "'nao'" if editavel.sim_ou_nao else f"CAST({editavel.na_ficha} AS VARCHAR)"
    return f"""
        SELECT e.aba, e.linha, '{editavel.campo.value}' AS campo, '{editavel.coluna}' AS coluna,
               e.cnpj, e.codigo, e.documento, e.numero_item, e.motivo,
               coalesce({de}, '') AS de, trim(e."{editavel.coluna}") AS para
        FROM pares e
        WHERE e.achadas = 1 AND ({_diferente(editavel)})"""


def _mudou_alguma_coisa() -> str:
    return " OR ".join(f"({_diferente(e)})" for e in EDITAVEIS)


def _casar(con, enviada: str, ficha3: str) -> None:
    """Põe cada linha da planilha ao lado da linha da ficha que ela diz ser."""
    colunas = {c.name for c in pq.read_schema(ficha3)}
    if {"cnpj", "codigo", "documento", "numero_item", "especie"} - colunas:
        raise PlanilhaIlegivel(
            "Este razão é de uma versão anterior e a ficha dele não tem as colunas da correção. "
            "Monte o razão de novo antes de corrigir à mão.")
    # o que o parquet não tiver — rodada de antes de a coluna existir — vira
    # nulo, e aquele campo simplesmente não acusa mudança
    da_ficha = ", ".join(f"{'f.' + c if c in colunas else 'NULL'} AS f_{c}" for c in DA_FICHA)
    con.execute(f"""
        CREATE OR REPLACE TABLE pares AS
        SELECT e.*, {da_ficha},
               count(f.cnpj) OVER (PARTITION BY e.aba, e.linha) AS achadas
        FROM read_parquet({_literal(enviada)}) e
        LEFT JOIN read_parquet({_literal(ficha3)}) f
          ON f.cnpj = e.cnpj AND f.codigo = e.codigo AND f.documento = e.documento
         AND coalesce(f.numero_item, 0) = coalesce(e.numero_item, 0)""")


def _alcance(con, ficha3: str, mercadorias: set[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Quantas linhas da ficha cada mercadoria corrigida tem.

    A correção de alíquota é da mercadoria: a pessoa editou uma célula e vai
    mexer em todas as linhas daquele código. A tela mostra quantas são antes de
    ela confirmar — é a diferença entre corrigir uma nota e corrigir o ano.
    """
    if not mercadorias:
        return {}
    con.execute("CREATE OR REPLACE TABLE mercadorias (cnpj VARCHAR, codigo VARCHAR)")
    con.executemany("INSERT INTO mercadorias VALUES (?, ?)", sorted(mercadorias))
    linhas = con.execute(
        f"""SELECT f.cnpj, f.codigo, count(*) FROM read_parquet({_literal(ficha3)}) f
            JOIN mercadorias m ON m.cnpj = f.cnpj AND m.codigo = f.codigo
            GROUP BY f.cnpj, f.codigo""").fetchall()
    return {(cnpj, codigo): quantas for cnpj, codigo, quantas in linhas}


def _conferir_com_duckdb(enviada: str, ficha3: str, pasta: str, conferencia: Conferencia) -> None:
    con = duckdb.connect()
    try:
        con.execute("SET threads TO 4")
        con.execute(f"SET temp_directory = {_literal(pasta)}")
        _casar(con, enviada, ficha3)
        # só linha com motivo pode virar correção: reclamar das outras encheria
        # a tela com dois milhões de erros que ninguém pediu
        com_motivo = "nullif(trim(e.motivo), '') IS NOT NULL"
        conferencia.nao_achadas = con.execute(
            f"SELECT count(*) FROM pares e WHERE e.achadas = 0 AND {com_motivo}").fetchone()[0]
        nao_achadas = con.execute(
            f"""SELECT e.aba, e.linha, e.cnpj, e.codigo, e.documento, e.numero_item
                FROM pares e WHERE e.achadas = 0 AND {com_motivo}
                ORDER BY e.linha LIMIT {NA_LISTA}""").fetchall()
        ambiguas = con.execute(
            f"""SELECT DISTINCT e.aba, e.linha FROM pares e
                WHERE e.achadas > 1 AND {com_motivo} ORDER BY e.linha LIMIT {NA_LISTA}""").fetchall()
        sem_mudanca = con.execute(
            f"""SELECT e.aba, e.linha FROM pares e
                WHERE {com_motivo} AND e.achadas = 1 AND NOT ({_mudou_alguma_coisa()})
                ORDER BY e.linha LIMIT {NA_LISTA}""").fetchall()
        uniao = "\n        UNION ALL".join(_selecao(e) for e in EDITAVEIS)
        con.execute(f"CREATE OR REPLACE TABLE mudou AS SELECT * FROM ({uniao}) ORDER BY linha, campo")
        mudou = con.execute("SELECT * FROM mudou").fetchall()
        nomes = [d[0] for d in con.description]
        campo, cnpj, codigo = nomes.index("campo"), nomes.index("cnpj"), nomes.index("codigo")
        alcance = _alcance(con, ficha3, {
            (linha[cnpj], linha[codigo]) for linha in mudou
            if Campo(linha[campo]).alvo is Alvo.MERCADORIA})
    finally:
        con.close()

    for aba, linha, cnpj_, codigo_, documento, item in nao_achadas:
        conferencia.erros.append({
            "aba": aba, "linha": linha, "campo": "", "rotulo": "",
            "mensagem": f"Não achei esta linha na ficha do razão (CNPJ {cnpj_ or '—'}, mercadoria "
                        f"{codigo_ or '—'}, documento {documento or '—'}, item {item or '—'}). "
                        "As colunas de identificação não podem ser alteradas, e a planilha "
                        "tem de ser a deste razão."})
    for aba, linha in ambiguas:
        conferencia.erros.append({
            "aba": aba, "linha": linha, "campo": "", "rotulo": "",
            "mensagem": "Esta linha aponta para mais de um lançamento da ficha — venda de "
                        "relatório de PDV não tem chave nem número de item. Corrija na tela do razão."})
    for aba, linha in sem_mudanca:
        conferencia.avisos.append({
            "aba": aba, "linha": linha,
            "mensagem": "Tem motivo escrito e nenhum valor mudou: nada será gravado desta linha."})

    _montar(mudou, nomes, alcance, conferencia)


def _montar(mudou: list, nomes: list[str], alcance: dict, conferencia: Conferencia) -> None:
    """Valida cada mudança pelo domínio e monta a lista que a tela mostra.

    A mesma `validar` da API em C# e da edição na tela: o que a planilha propõe
    passa pela regra antes de aparecer como correção, e o que não passa vira
    erro com o número da linha — que é o que a pessoa precisa para achar a
    célula no Excel.
    """
    indice = {nome: i for i, nome in enumerate(nomes)}
    vistos: dict[tuple, dict] = {}
    for bruta in mudou:
        linha = {nome: bruta[i] for nome, i in indice.items()}
        campo = Campo(linha["campo"])
        eh_mercadoria = campo.alvo is Alvo.MERCADORIA
        try:
            correcao = validar(
                campo, linha["para"], linha["motivo"], cnpj=linha["cnpj"], codigo=linha["codigo"],
                documento=linha["documento"], numero_item=linha["numero_item"],
                valor_anterior=linha["de"])
        except CorrecaoInvalida as erro:
            conferencia.erros.append({
                "aba": linha["aba"], "linha": linha["linha"], "campo": campo.value,
                "rotulo": campo.rotulo, "mensagem": str(erro)})
            continue
        chave = ((campo.value, correcao.cnpj, correcao.codigo) if eh_mercadoria
                 else (campo.value, correcao.cnpj, correcao.documento, correcao.numero_item))
        pronta = {
            "campo": campo.value, "rotulo": campo.rotulo, "alvo": campo.alvo.value,
            "onde": correcao.onde, "cnpj": correcao.cnpj, "codigo": correcao.codigo,
            "documento": correcao.documento, "numero_item": correcao.numero_item,
            "de": correcao.valor_anterior, "para": correcao.valor_gravado,
            "motivo": correcao.motivo, "frase": correcao.frase, "coluna": linha["coluna"],
            "aba": linha["aba"], "linha_na_planilha": linha["linha"],
            "linhas_atingidas": (alcance.get((correcao.cnpj, correcao.codigo), 1)
                                 if eh_mercadoria else 1),
        }
        anterior = vistos.get(chave)
        if anterior is None:
            vistos[chave] = pronta
        elif anterior["para"] != pronta["para"]:
            # duas linhas da mesma mercadoria pedindo alíquotas diferentes: não
            # há como obedecer as duas, e escolher uma calado seria pior
            conferencia.erros.append({
                "aba": pronta["aba"], "linha": pronta["linha_na_planilha"], "campo": campo.value,
                "rotulo": campo.rotulo,
                "mensagem": f"{correcao.onde}: a planilha pede {anterior['para']} na linha "
                            f"{anterior['linha_na_planilha']} e {pronta['para']} aqui. "
                            "Deixe um valor só."})
            anterior["conflito"] = True

    conferencia.correcoes = sorted(
        (c for c in vistos.values() if not c.pop("conflito", False)),
        key=lambda c: (c["linha_na_planilha"], c["campo"]))
    if len(conferencia.correcoes) > CORRECOES_POR_PEDIDO:
        conferencia.correcoes = conferencia.correcoes[:CORRECOES_POR_PEDIDO]
        conferencia.truncado = True


# ---------------------------------------------------------------------------
# a porta
# ---------------------------------------------------------------------------
def conferir(planilha: str, ficha3: str, pasta: str | None = None) -> Conferencia:
    """Lê a planilha editada e devolve o que mudou em relação à ficha do razão.

    `planilha` é o arquivo que a pessoa subiu (xlsx ou csv); `ficha3`, o parquet
    que a etapa do razão escreveu. Nada é gravado: o que volta é a proposta.
    """
    if not os.path.isfile(ficha3):
        raise FileNotFoundError(ficha3)
    if not planilha.lower().endswith(EXTENSOES):
        raise PlanilhaIlegivel("Suba a Ficha 3 em xlsx ou csv, como o sistema a gera.")
    pasta = pasta or os.path.dirname(os.path.abspath(ficha3))
    os.makedirs(pasta, exist_ok=True)
    rascunho = os.path.join(pasta, ARQUIVO_DE_RASCUNHO)
    conferencia = Conferencia()
    enviada = _escrever_enviada(planilha, rascunho, conferencia)
    try:
        if not conferencia.abas:
            # nenhuma aba tinha o cabeçalho: o motivo da primeira é o motivo do
            # arquivo, e é ele que a pessoa precisa ler — não "planilha vazia"
            raise PlanilhaIlegivel(conferencia.avisos[0]["mensagem"] if conferencia.avisos
                                   else "A planilha não tem o cabeçalho da Ficha 3.")
        if enviada is None:
            raise PlanilhaIlegivel("A planilha não tem nenhuma linha de dado abaixo do cabeçalho.")
        _conferir_com_duckdb(enviada, ficha3, pasta, conferencia)
    finally:
        if os.path.isfile(rascunho):
            os.remove(rascunho)
    log.info("planilha de correções conferida",
             extra={"linhas": conferencia.linhas_lidas, "correcoes": len(conferencia.correcoes),
                    "erros": len(conferencia.erros), "abas": len(conferencia.abas),
                    "nao_achadas": conferencia.nao_achadas, "truncado": conferencia.truncado})
    return conferencia
