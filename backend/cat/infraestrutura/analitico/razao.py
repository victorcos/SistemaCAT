"""Monta a Ficha 3 de cada mercadoria, juntando as fontes da movimentação.

A regra — custo médio ponderado móvel, entradas antes das saídas no dia,
ressarcimento e complemento — está em `cat.dominio.cat42.razao`, e foi
conferida contra a Ficha 3 já calculada de um cliente, 100% das linhas. Aqui é
a parte suja: achar os movimentos, dizer de qual loja e de qual enquadramento
cada um é, e percorrer.

## De onde vem cada lado da ficha

| Lado | Fonte | Por quê |
|---|---|---|
| Entrada | apuração da etapa 4 | é onde está o ICMS suportado de cada item |
| Saída com item na EFD | movimentação da etapa 3 | documento fiscal: vence o relatório |
| Saída sem item na EFD | relatório de saídas do cliente | cupom e NFC-e vão à EFD só com o analítico |
| Abertura | bloco H da EFD | o inventário do dia anterior ao período |

No Amigão, 36,5 milhões de documentos de saída não têm item na EFD, e a venda
com item é R$ 6 milhões contra R$ 5,8 bilhões. Sem o relatório não há saída a
lançar. O XML dos cupons, quando vier, entra como fonte que vence as duas.

## Quais mercadorias

Entra no razão o código que teve **saída com CST 60** em qualquer loja do
período: é a mercadoria vendida com o imposto já retido, que é a matéria da
CAT 42. Mercadoria de CST 00 ou 20 tem imposto próprio, não suportado, e fica
de fora — decisão de 15/09/2026, depois de medir que ela respondia por 54% do
"suportado" apurado.

## De qual loja é a saída do relatório

O relatório diz a unidade ("005"), não o CNPJ. O CNPJ sai de duas pistas que
se confirmam: a chave de acesso de quem emitiu, e a coluna CNPJ/CPF da venda
de PDV, que traz a própria loja. A unidade herda o CNPJ que essas linhas
apontarem; o que nenhuma pista alcança fica contado, não suposto.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.enquadramento import (
    CFOP_DEVOLUCAO,
    classificar,
)
from cat.dominio.cat42.razao import (
    EnquadramentoLegal,
    Especie,
    Movimento,
    MovimentoInvalido,
    RazaoDoItem,
    SaldoInicial,
)
from cat.infraestrutura.analitico.confronto import _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.analitico.suportado import (
    ARQUIVO_SUPORTADO,
    ApuracaoCancelada,
    _leitura,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_SAIDAS_DO_RELATORIO = "saidas_do_relatorio.parquet"
ARQUIVO_FICHA3 = "ficha3.parquet"
ARQUIVO_FICHAS = "fichas.parquet"

LINHAS_POR_LOTE = 200_000
POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200

# quantas linhas de um relatório se olham antes de concluir que ele é só de
# entradas. Ler inteiro um relatório de entradas para achar zero saídas custa,
# no Amigão, 26 minutos sobre 20 GB
AMOSTRA_PARA_ACHAR_SAIDA = 5_000

# devolução de venda chega como entrada; devolução de compra, como saída
_DEVOLUCAO_DE_VENDA = frozenset(c for c in CFOP_DEVOLUCAO if c[0] in "123")
_DEVOLUCAO_DE_COMPRA = frozenset(c for c in CFOP_DEVOLUCAO if c[0] in "567")

_Q6 = Decimal("0.000001")
_Q15 = Decimal("0.000000000000001")

ESQUEMA_SAIDA_DO_RELATORIO = pa.schema([
    ("unidade", pa.string()),
    ("cnpj_participante", pa.string()),
    ("chave", pa.string()),
    ("numero_documento", pa.string()),
    ("codigo", pa.string()),
    ("data", pa.date32()),
    ("cfop", pa.string()),
    ("cst_icms", pa.string()),
    ("quantidade", pa.decimal128(20, 6)),
    ("valor", pa.decimal128(20, 6)),
    ("suportado", pa.decimal128(20, 6)),
    ("pdv", pa.bool_()),
])

ESQUEMA_FICHA3 = pa.schema([
    ("cnpj", pa.string()),
    ("codigo", pa.string()),
    ("numero", pa.int32()),
    ("data", pa.date32()),
    ("especie", pa.string()),
    ("devolucao", pa.bool_()),
    ("cfop", pa.string()),
    ("documento", pa.string()),
    ("origem", pa.string()),
    ("enquadramento", pa.int8()),
    ("enquadramento_indefinido", pa.bool_()),
    ("quantidade", pa.decimal128(24, 6)),
    ("icms_suportado", pa.decimal128(30, 15)),
    ("valor_unitario_usado", pa.decimal128(30, 15)),
    ("icms_efetivo", pa.decimal128(24, 6)),
    ("saldo_quantidade", pa.decimal128(24, 6)),
    ("saldo_unitario", pa.decimal128(30, 15)),
    ("saldo_valor", pa.decimal128(30, 15)),
    ("ressarcimento", pa.decimal128(30, 15)),
    ("complemento", pa.decimal128(30, 15)),
])

ESQUEMA_FICHAS = pa.schema([
    ("cnpj", pa.string()),
    ("uf", pa.string()),
    ("codigo", pa.string()),
    ("descricao", pa.string()),
    ("linhas", pa.int32()),
    ("abertura_quantidade", pa.decimal128(24, 6)),
    ("abertura_sem_valor", pa.bool_()),
    ("entradas", pa.decimal128(24, 6)),
    ("saidas", pa.decimal128(24, 6)),
    ("saldo_quantidade", pa.decimal128(24, 6)),
    ("saldo_valor", pa.decimal128(30, 15)),
    ("ressarcimento", pa.decimal128(30, 15)),
    ("complemento", pa.decimal128(30, 15)),
    ("ficou_negativo", pa.bool_()),
    ("saidas_sem_aliquota", pa.int32()),
    ("saidas_indefinidas", pa.int32()),
])

DeveParar = Callable[[], bool]


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A montagem do razão foi cancelada por quem a pediu.")


# ---------------------------------------------------------------------------
# saídas do relatório do cliente
# ---------------------------------------------------------------------------
@dataclass
class SaidasExtraidas:
    arquivos: int = 0
    so_de_entradas: int = 0
    recusados: int = 0
    linhas: int = 0


def extrair_saidas(
    relatorios: list[str],
    destino: str,
    avisar: Callable[[int, int], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> SaidasExtraidas:
    """Grava as linhas de saída dos relatórios de movimento do cliente.

    Um relatório por vez, em partes, somadas no fim — a mesma lição da etapa
    4: acumular em memória não cabe numa base de dezenas de GB. O relatório
    que não mostra saída nenhuma nas primeiras linhas é de entradas e é
    deixado de lado sem ser lido inteiro.
    """
    from cat.dominio.gerencial.campos import Especie as EspecieDoRelatorio
    from cat.infraestrutura.arquivos.gerencial import Leitura

    partes = destino + ".partes"
    shutil.rmtree(partes, ignore_errors=True)
    os.makedirs(partes)
    r = SaidasExtraidas(arquivos=len(relatorios))
    try:
        for n, caminho in enumerate(relatorios, 1):
            _conferir(deve_parar)
            nome = os.path.basename(caminho)
            try:
                leitura = Leitura(caminho)
                if leitura.especie is not EspecieDoRelatorio.MOVIMENTO:
                    r.recusados += 1
                    continue
                gravadas = _gravar_saidas_de(leitura, os.path.join(partes, f"{n:05d}.parquet"))
                if gravadas is None:
                    r.so_de_entradas += 1
                    log.info("relatório só de entradas, ignorado no razão", extra={"arquivo": nome})
                else:
                    r.linhas += gravadas
            except (OSError, ValueError) as erro:
                r.recusados += 1
                log.warning("relatório ilegível no razão", extra={"arquivo": nome, "motivo": str(erro)})
            finally:
                if avisar is not None:
                    avisar(n, len(relatorios))

        arquivos = [x for x in os.listdir(partes) if x.endswith(".parquet")]
        if arquivos:
            con = _leitura(partes)
            try:
                con.execute(f"""
                    COPY (SELECT * FROM read_parquet('{_escapar(os.path.join(partes, "*.parquet"))}'))
                    TO '{_escapar(destino)}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """)
            finally:
                con.close()
        else:
            pq.write_table(ESQUEMA_SAIDA_DO_RELATORIO.empty_table(), destino)
    finally:
        shutil.rmtree(partes, ignore_errors=True)
    log.info("saídas do relatório extraídas", extra=vars(r))
    return r


def _gravar_saidas_de(leitura, destino: str) -> int | None:
    colunas: dict[str, list] = {c: [] for c in ESQUEMA_SAIDA_DO_RELATORIO.names}
    escritor = None
    vistas = saidas = 0
    try:
        for m in leitura.movimentos():
            vistas += 1
            if m.e_entrada:
                if saidas == 0 and vistas >= AMOSTRA_PARA_ACHAR_SAIDA:
                    return None
                continue
            saidas += 1
            colunas["unidade"].append(m.unidade)
            colunas["cnpj_participante"].append(m.cnpj_participante or "")
            colunas["chave"].append(m.chave)
            colunas["numero_documento"].append(str(m.numero_doc) if m.numero_doc else "")
            colunas["codigo"].append(m.codigo_item)
            colunas["data"].append(m.data)
            colunas["cfop"].append(m.cfop.replace(".", ""))
            colunas["cst_icms"].append(m.cst_icms)
            colunas["quantidade"].append(m.quantidade.quantize(_Q6))
            colunas["valor"].append(m.valor_item.quantize(_Q6))
            colunas["suportado"].append(m.imposto_suportado.quantize(_Q6))
            colunas["pdv"].append(m.e_venda_de_pdv)
            if len(colunas["codigo"]) >= LINHAS_POR_LOTE:
                escritor = escritor or pq.ParquetWriter(destino, ESQUEMA_SAIDA_DO_RELATORIO)
                escritor.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA_SAIDA_DO_RELATORIO))
                colunas = {c: [] for c in ESQUEMA_SAIDA_DO_RELATORIO.names}
        if saidas == 0:
            return None
        if colunas["codigo"]:
            escritor = escritor or pq.ParquetWriter(destino, ESQUEMA_SAIDA_DO_RELATORIO)
            escritor.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA_SAIDA_DO_RELATORIO))
        return saidas
    finally:
        if escritor is not None:
            escritor.close()


# ---------------------------------------------------------------------------
# a montagem
# ---------------------------------------------------------------------------
@dataclass
class Fontes:
    """Onde está cada parquet que o razão lê. Cada um é de uma etapa."""

    movimentacao: str           # pasta da etapa 3
    apuracao: str               # pasta da etapa 4
    saidas_do_relatorio: str | None = None


@dataclass
class Andamento:
    linhas: int = 0
    total: int = 0
    fichas: int = 0


@dataclass
class ResumoDaMontagem:
    periodo_inicio: str = ""
    periodo_fim: str = ""
    abertura_em: str | None = None
    codigos_com_st: int = 0
    fichas: int = 0
    estabelecimentos: int = 0
    linhas: int = 0
    ressarcimento: Decimal = Decimal(0)
    complemento: Decimal = Decimal(0)
    por_enquadramento: dict = field(default_factory=dict)
    por_competencia: dict = field(default_factory=dict)
    saidas_por_origem: dict = field(default_factory=dict)
    saidas_sem_aliquota: int = 0
    saidas_indefinidas: int = 0
    confronto_pendente: int = 0
    fichas_negativas: int = 0
    fichas_abertura_sem_valor: int = 0
    fichas_fora_de_sp: int = 0
    relatorio_sem_estabelecimento: int = 0
    relatorio_trocado_pela_efd: int = 0
    quantidade_negativa: int = 0


def contar_movimentos(fontes: Fontes, destino: str) -> int:
    """Quantas linhas a montagem vai percorrer — o denominador da barra."""
    con = _abrir(destino)
    try:
        _preparar(con, fontes)
        return con.execute("SELECT count(*) FROM lancamentos").fetchone()[0]
    finally:
        con.close()
        _limpar(destino)


def montar(
    fontes: Fontes,
    destino: str,
    uf_por_cnpj: dict[str, str] | None = None,
    descricoes: dict[tuple[str, str], str] | None = None,
    avisar: Callable[[Andamento], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> ResumoDaMontagem:
    """Percorre os lançamentos de cada (estabelecimento, mercadoria) e grava a ficha.

    O cálculo é o do domínio, linha a linha, por decisão: a regra foi conferida
    contra uma Ficha 3 real, e reescrevê-la em SQL daria duas versões dela.
    Ao SQL cabe o que ele faz bem — juntar, filtrar, ordenar.
    """
    uf_por_cnpj = uf_por_cnpj or {}
    ficha3 = os.path.join(destino, ARQUIVO_FICHA3)
    fichas = os.path.join(destino, ARQUIVO_FICHAS)
    resumo = ResumoDaMontagem()
    con = _abrir(destino)
    try:
        info = _preparar(con, fontes)
        resumo.periodo_inicio = info["inicio"].isoformat()
        resumo.periodo_fim = info["fim"].isoformat()
        resumo.abertura_em = info["abertura_em"].isoformat() if info["abertura_em"] else None
        resumo.codigos_com_st = info["codigos"]
        resumo.relatorio_sem_estabelecimento = info["sem_estabelecimento"]
        resumo.relatorio_trocado_pela_efd = info["trocado_pela_efd"]
        aberturas = {(c, k): q for c, k, q in con.execute(
            "SELECT cnpj, codigo, quantidade FROM abertura").fetchall()}
        total = con.execute("SELECT count(*) FROM lancamentos").fetchone()[0]

        leitor = con.execute("""
            SELECT * FROM lancamentos
            ORDER BY cnpj, codigo, data, prioridade, origem, documento
        """).to_arrow_reader(LINHAS_POR_LOTE)
        _percorrer(leitor, aberturas, ficha3, fichas, resumo, total,
                   uf_por_cnpj, descricoes or {}, avisar, deve_parar)
        _descrever(con, fichas, os.path.join(fontes.movimentacao, ARQUIVO_ITENS))
    except ApuracaoCancelada:
        con.close()
        for arquivo in (ficha3, fichas):
            if os.path.isfile(arquivo):
                os.remove(arquivo)
        raise
    finally:
        con.close()
        _limpar(destino)

    log.info("razão montado", extra={
        "fichas": resumo.fichas, "linhas": resumo.linhas,
        "ressarcimento": str(resumo.ressarcimento), "complemento": str(resumo.complemento)})
    return resumo


def _descrever(con, fichas: str, itens: str) -> None:
    """Põe a descrição do 0200 em cada ficha. Em SQL, no fim: o cadastro inteiro
    num dicionário do Python seriam milhões de entradas só para um rótulo."""
    if not os.path.isfile(itens) or not os.path.isfile(fichas):
        return
    provisorio = fichas + ".tmp"
    con.execute(f"""
        COPY (
            SELECT f.* REPLACE (coalesce(nullif(f.descricao, ''), i.descricao, '') AS descricao)
            FROM read_parquet('{_escapar(fichas)}') f
            LEFT JOIN read_parquet('{_escapar(itens)}') i ON i.cnpj = f.cnpj AND i.codigo = f.codigo
        ) TO '{_escapar(provisorio)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    os.replace(provisorio, fichas)


def _preparar(con, fontes: Fontes) -> dict:
    """Monta a tabela `lancamentos` e a `abertura`. Tudo em SQL, nada calculado."""
    mov = f"read_parquet('{_escapar(os.path.join(fontes.movimentacao, ARQUIVO_MOVIMENTOS))}')"
    sup = f"read_parquet('{_escapar(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO))}')"
    itens = os.path.join(fontes.movimentacao, ARQUIVO_ITENS)
    inventario = os.path.join(fontes.movimentacao, ARQUIVO_INVENTARIO)
    rel = fontes.saidas_do_relatorio
    tem_rel = bool(rel and os.path.isfile(rel))

    inicio, fim = con.execute(f"SELECT min(competencia), max(competencia) FROM {mov}").fetchone()
    # fim do último mês
    fim = (fim.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    lista = lambda conj: ", ".join(f"'{c}'" for c in sorted(conj))  # noqa: E731

    con.execute(f"CREATE OR REPLACE TABLE estabs AS SELECT DISTINCT cnpj FROM {mov}")
    con.execute(f"""
        CREATE OR REPLACE TABLE saidas_efd AS
        SELECT cnpj, codigo, data, replace(cfop, '.', '') AS cfop, cst_icms, modelo,
               quantidade, valor, coalesce(valor_icms, 0) + coalesce(valor_st, 0) AS suportado,
               coalesce(nullif(chave, ''), numero_documento) AS documento, chave,
               false AS pdv, 'efd' AS origem
        FROM {mov} WHERE operacao = 'saida'
    """)

    sem_estab = trocado = 0
    if tem_rel:
        con.execute(f"""
            CREATE OR REPLACE TABLE rel AS
            SELECT r.*,
                   CASE WHEN length(r.chave) = 44 AND substr(r.chave, 7, 14) IN (SELECT cnpj FROM estabs)
                            THEN substr(r.chave, 7, 14)
                        WHEN r.pdv AND r.cnpj_participante IN (SELECT cnpj FROM estabs)
                            THEN r.cnpj_participante
                   END AS cnpj_direto
            FROM read_parquet('{_escapar(rel)}') r
            WHERE r.data BETWEEN DATE '{inicio}' AND DATE '{fim}'
        """)
        con.execute("""
            CREATE OR REPLACE TABLE unidade_cnpj AS
            SELECT unidade, mode(cnpj_direto) AS cnpj FROM rel
            WHERE cnpj_direto IS NOT NULL GROUP BY unidade
        """)
        con.execute("""
            CREATE OR REPLACE TABLE rel_com_cnpj AS
            SELECT r.*, coalesce(r.cnpj_direto, u.cnpj) AS cnpj
            FROM rel r LEFT JOIN unidade_cnpj u ON u.unidade = r.unidade
        """)
        sem_estab = con.execute("SELECT count(*) FROM rel_com_cnpj WHERE cnpj IS NULL").fetchone()[0]
        # documento da EFD vence o relatório: a nota que tem item lá não entra duas vezes
        trocado = con.execute("""
            SELECT count(*) FROM rel_com_cnpj
            WHERE length(chave) = 44 AND chave IN (SELECT chave FROM saidas_efd WHERE length(chave) = 44)
        """).fetchone()[0]
        con.execute("""
            CREATE OR REPLACE TABLE saidas_rel AS
            SELECT cnpj, codigo, data, cfop, cst_icms,
                   CASE WHEN length(chave) = 44 THEN substr(chave, 21, 2) ELSE '' END AS modelo,
                   quantidade, valor, suportado,
                   coalesce(nullif(chave, ''), 'relatorio|' || unidade || '|' || numero_documento) AS documento,
                   chave, pdv, 'relatorio' AS origem
            FROM rel_com_cnpj
            WHERE cnpj IS NOT NULL
              AND NOT (length(chave) = 44
                       AND chave IN (SELECT chave FROM saidas_efd WHERE length(chave) = 44))
        """)
        saidas = "(SELECT * FROM saidas_efd UNION ALL BY NAME SELECT * FROM saidas_rel)"
    else:
        saidas = "saidas_efd"

    con.execute(f"""
        CREATE OR REPLACE TABLE codigos AS
        SELECT DISTINCT codigo FROM {saidas} WHERE right(coalesce(cst_icms, ''), 2) = '60'
    """)
    codigos = con.execute("SELECT count(*) FROM codigos").fetchone()[0]
    aliquota = (f"LEFT JOIN read_parquet('{_escapar(itens)}') i ON i.cnpj = l.cnpj AND i.codigo = l.codigo"
                if os.path.isfile(itens) else "")
    coluna_aliquota = "i.aliq_icms" if aliquota else "NULL"

    con.execute(f"""
        CREATE OR REPLACE TABLE lancamentos AS
        SELECT l.*, {coluna_aliquota} AS aliquota
        FROM (
            SELECT s.cnpj, s.codigo, s.data, replace(s.cfop, '.', '') AS cfop, s.cst_icms, s.modelo,
                   s.quantidade, NULL::DECIMAL(20, 6) AS valor, s.suportado,
                   coalesce(nullif(s.chave, ''), s.numero_documento) AS documento,
                   false AS pdv, 'efd' AS origem,
                   CASE WHEN replace(s.cfop, '.', '') IN ({lista(_DEVOLUCAO_DE_VENDA)}) THEN 'saida' ELSE 'entrada' END AS especie,
                   replace(s.cfop, '.', '') IN ({lista(_DEVOLUCAO_DE_VENDA)}) AS devolucao,
                   1 AS prioridade
            FROM {sup} s
            UNION ALL
            SELECT s.cnpj, s.codigo, s.data, s.cfop, s.cst_icms, s.modelo,
                   s.quantidade, s.valor, s.suportado, s.documento, s.pdv, s.origem,
                   CASE WHEN s.cfop IN ({lista(_DEVOLUCAO_DE_COMPRA)}) THEN 'entrada' ELSE 'saida' END,
                   s.cfop IN ({lista(_DEVOLUCAO_DE_COMPRA)}),
                   2
            FROM {saidas} s
        ) l
        {aliquota}
        WHERE l.codigo IN (SELECT codigo FROM codigos)
          AND l.cnpj IN (SELECT cnpj FROM estabs)
          AND l.data BETWEEN DATE '{inicio}' AND DATE '{fim}'
    """)

    abertura_em = None
    if os.path.isfile(inventario):
        abertura_em = con.execute(f"""
            SELECT max(data_inventario) FROM read_parquet('{_escapar(inventario)}')
            WHERE data_inventario < DATE '{inicio}'
        """).fetchone()[0]
    if abertura_em is not None:
        con.execute(f"""
            CREATE OR REPLACE TABLE abertura AS
            SELECT cnpj, codigo, sum(quantidade) AS quantidade
            FROM read_parquet('{_escapar(inventario)}')
            WHERE data_inventario = DATE '{abertura_em}'
              AND codigo IN (SELECT codigo FROM codigos) AND cnpj IN (SELECT cnpj FROM estabs)
            GROUP BY cnpj, codigo HAVING sum(quantidade) <> 0
        """)
    else:
        con.execute("CREATE OR REPLACE TABLE abertura (cnpj VARCHAR, codigo VARCHAR, quantidade DECIMAL(20, 5))")

    return {"inicio": inicio, "fim": fim, "abertura_em": abertura_em, "codigos": codigos,
            "sem_estabelecimento": sem_estab, "trocado_pela_efd": trocado}


# ---------------------------------------------------------------------------
# o percurso, ficha a ficha
# ---------------------------------------------------------------------------
def _enquadrar(linha: dict) -> tuple[EnquadramentoLegal | None, bool]:
    enq = classificar(linha["cfop"] or "", linha["cst_icms"] or "",
                      consumidor_final=True if linha["pdv"] else None,
                      modelo=linha["modelo"] or "")
    return enq, enq is None


def _confronto(enq: EnquadramentoLegal, linha: dict) -> tuple[Decimal | None, bool, bool]:
    """(ICMS efetivo, faltou alíquota, confronto pendente).

    Enquadramentos 1 e 3 confrontam com a alíquota interna vezes o valor da
    saída (leiaute, VL_CONFR). Os 2 e 4 confrontam com o ICMS da operação
    própria da entrada, que ainda não é acompanhado por item: ficam pendentes,
    contados, sem ressarcimento inventado.
    """
    if not enq.gera_ressarcimento:
        return None, False, False
    if not enq.confronta_com_saida:
        return None, False, True
    aliquota = linha["aliquota"]
    valor = linha["valor"]
    if not aliquota or valor is None:
        return None, True, False
    return (Decimal(valor) * Decimal(aliquota) / 100).quantize(_Q6), False, False


def _percorrer(leitor, aberturas: dict, ficha3: str, fichas: str, resumo: ResumoDaMontagem,
               total: int, uf_por_cnpj: dict, descricoes: dict, avisar, deve_parar) -> None:
    escritor = pq.ParquetWriter(ficha3, ESQUEMA_FICHA3)
    escritor_fichas = pq.ParquetWriter(fichas, ESQUEMA_FICHAS)
    lote: dict[str, list] = {c: [] for c in ESQUEMA_FICHA3.names}
    lote_fichas: dict[str, list] = {c: [] for c in ESQUEMA_FICHAS.names}
    estabelecimentos: set[str] = set()
    atual: tuple[str, str] | None = None
    movimentos: list[Movimento] = []
    extras: list[tuple[bool, int]] = []   # (indefinido, faltou alíquota) por movimento
    andamento = Andamento(total=total)
    vistos: set[tuple[str, str]] = set()

    def fechar(chave: tuple[str, str]) -> None:
        cnpj, codigo = chave
        qtd_abertura = Decimal(aberturas.get(chave) or 0)
        razao = RazaoDoItem(codigo, SaldoInicial(qtd_abertura, Decimal(0)))
        razao.lancar_varios(movimentos)
        linhas = razao.apurar()
        indice = {id(m): x for m, x in zip(movimentos, extras)}
        entradas = saidas = ressarc = compl = Decimal(0)
        negativo = False
        sem_aliq = indef = 0
        for ln in linhas:
            m = ln.movimento
            indefinido, faltou = indice[id(m)]
            competencia = m.data.isoformat()[:7]
            _acrescentar(lote, cnpj, codigo, ln, indefinido)
            if m.especie.e_entrada:
                entradas += ln.quantidade
            else:
                saidas += -ln.quantidade
                if not m.devolucao:
                    chave_enq = "indefinido" if indefinido else str(int(m.enquadramento))
                    e = resumo.por_enquadramento.setdefault(chave_enq, {
                        "linhas": 0, "quantidade": Decimal(0), "suportado": Decimal(0),
                        "confronto": Decimal(0), "ressarcimento": Decimal(0), "complemento": Decimal(0)})
                    e["linhas"] += 1
                    e["quantidade"] += m.quantidade
                    e["suportado"] += abs(ln.icms_suportado)
                    e["confronto"] += m.icms_efetivo or Decimal(0)
                    e["ressarcimento"] += ln.ressarcimento
                    e["complemento"] += ln.complemento
                    origem = resumo.saidas_por_origem.setdefault(m.origem, 0)
                    resumo.saidas_por_origem[m.origem] = origem + 1
            if ln.saldo_quantidade < 0:
                negativo = True
            sem_aliq += faltou
            indef += indefinido
            ressarc += ln.ressarcimento
            compl += ln.complemento
            c = resumo.por_competencia.setdefault(competencia, {
                "linhas": 0, "ressarcimento": Decimal(0), "complemento": Decimal(0)})
            c["linhas"] += 1
            c["ressarcimento"] += ln.ressarcimento
            c["complemento"] += ln.complemento
            if len(lote["cnpj"]) >= LINHAS_POR_LOTE:
                escritor.write_table(pa.Table.from_pydict(lote, schema=ESQUEMA_FICHA3))
                for k in lote:
                    lote[k].clear()

        ultima = linhas[-1] if linhas else None
        uf = uf_por_cnpj.get(cnpj, "")
        for k, val in (("cnpj", cnpj), ("uf", uf), ("codigo", codigo),
                       ("descricao", descricoes.get((cnpj, codigo)) or descricoes.get(("", codigo), "")),
                       ("linhas", len(linhas)),
                       ("abertura_quantidade", qtd_abertura.quantize(_Q6)),
                       ("abertura_sem_valor", qtd_abertura != 0),
                       ("entradas", entradas.quantize(_Q6)), ("saidas", saidas.quantize(_Q6)),
                       ("saldo_quantidade", (ultima.saldo_quantidade if ultima else qtd_abertura).quantize(_Q6)),
                       ("saldo_valor", (ultima.saldo_valor if ultima else Decimal(0)).quantize(_Q15)),
                       ("ressarcimento", ressarc.quantize(_Q15)), ("complemento", compl.quantize(_Q15)),
                       ("ficou_negativo", negativo), ("saidas_sem_aliquota", sem_aliq),
                       ("saidas_indefinidas", indef)):
            lote_fichas[k].append(val)
        resumo.fichas += 1
        resumo.linhas += len(linhas)
        resumo.ressarcimento += ressarc
        resumo.complemento += compl
        resumo.saidas_sem_aliquota += sem_aliq
        resumo.saidas_indefinidas += indef
        resumo.fichas_negativas += negativo
        resumo.fichas_abertura_sem_valor += qtd_abertura != 0
        resumo.fichas_fora_de_sp += bool(uf) and uf != "SP"
        estabelecimentos.add(cnpj)
        vistos.add(chave)
        if len(lote_fichas["cnpj"]) >= LINHAS_POR_LOTE:
            escritor_fichas.write_table(pa.Table.from_pydict(lote_fichas, schema=ESQUEMA_FICHAS))
            for k in lote_fichas:
                lote_fichas[k].clear()

    try:
        for bloco in leitor:
            _conferir(deve_parar)
            d = bloco.to_pydict()
            for i in range(bloco.num_rows):
                linha = {k: d[k][i] for k in d}
                chave = (linha["cnpj"], linha["codigo"])
                if chave != atual:
                    if atual is not None:
                        fechar(atual)
                    atual, movimentos, extras = chave, [], []
                m, indefinido, faltou, pendente = _movimento(linha, len(movimentos), resumo)
                if m is None:
                    continue
                resumo.confronto_pendente += pendente
                movimentos.append(m)
                extras.append((indefinido, faltou))
                andamento.linhas += 1
            if avisar is not None:
                andamento.fichas = resumo.fichas
                avisar(andamento)
        if atual is not None:
            fechar(atual)
        # quem só tem abertura, sem movimento no período, também tem ficha
        for chave in sorted(set(aberturas) - vistos):
            atual, movimentos, extras = chave, [], []
            fechar(chave)
        if lote["cnpj"]:
            escritor.write_table(pa.Table.from_pydict(lote, schema=ESQUEMA_FICHA3))
        if lote_fichas["cnpj"]:
            escritor_fichas.write_table(pa.Table.from_pydict(lote_fichas, schema=ESQUEMA_FICHAS))
    finally:
        escritor.close()
        escritor_fichas.close()
    resumo.estabelecimentos = len(estabelecimentos)


def _movimento(linha: dict, ordem: int, resumo: ResumoDaMontagem):
    """Converte um lançamento em `Movimento`. Devolve (movimento, indefinido,
    faltou alíquota, confronto pendente)."""
    especie = Especie.ENTRADA if linha["especie"] == "entrada" else Especie.SAIDA
    quantidade = Decimal(linha["quantidade"] or 0)
    if quantidade < 0:
        # o domínio recusa sinal: devolução é marca, não quantidade negativa
        resumo.quantidade_negativa += 1
        quantidade = -quantidade
    enq, indefinido, faltou, pendente, efetivo = EnquadramentoLegal.DEMAIS_SAIDAS, False, False, False, None
    if especie is Especie.SAIDA and not linha["devolucao"]:
        classificado, indefinido = _enquadrar(linha)
        if classificado is not None:
            enq = classificado
            efetivo, faltou, pendente = _confronto(enq, linha)
    try:
        m = Movimento(
            data=linha["data"],
            especie=especie,
            quantidade=quantidade,
            icms_suportado=Decimal(linha["suportado"] or 0) if especie.e_entrada else None,
            enquadramento=enq,
            icms_efetivo=efetivo,
            devolucao=bool(linha["devolucao"]),
            cfop=linha["cfop"] or "",
            documento=linha["documento"] or "",
            origem=linha["origem"],
            ordem_na_fonte=ordem,
        )
    except MovimentoInvalido as erro:
        log.warning("lançamento recusado pelo razão", extra={"motivo": str(erro),
                                                            "codigo": linha["codigo"]})
        return None, False, False, False
    return m, indefinido, faltou, pendente


def _acrescentar(lote: dict, cnpj: str, codigo: str, ln, indefinido: bool) -> None:
    m = ln.movimento
    lote["cnpj"].append(cnpj)
    lote["codigo"].append(codigo)
    lote["numero"].append(ln.numero)
    lote["data"].append(m.data)
    lote["especie"].append(m.especie.value)
    lote["devolucao"].append(m.devolucao)
    lote["cfop"].append(m.cfop)
    lote["documento"].append(m.documento)
    lote["origem"].append(m.origem)
    saida_propria = not m.especie.e_entrada and not m.devolucao
    lote["enquadramento"].append(None if (indefinido or not saida_propria) else int(m.enquadramento))
    lote["enquadramento_indefinido"].append(indefinido)
    lote["quantidade"].append(ln.quantidade.quantize(_Q6))
    lote["icms_suportado"].append(ln.icms_suportado.quantize(_Q15))
    lote["valor_unitario_usado"].append(ln.valor_unitario_usado.quantize(_Q15))
    lote["icms_efetivo"].append(m.icms_efetivo.quantize(_Q6) if m.icms_efetivo is not None else None)
    lote["saldo_quantidade"].append(ln.saldo_quantidade.quantize(_Q6))
    lote["saldo_unitario"].append(ln.saldo_unitario.quantize(_Q15))
    lote["saldo_valor"].append(ln.saldo_valor.quantize(_Q15))
    lote["ressarcimento"].append(ln.ressarcimento.quantize(_Q15))
    lote["complemento"].append(ln.complemento.quantize(_Q15))


# ---------------------------------------------------------------------------
# o que a tela lê depois de pronto
# ---------------------------------------------------------------------------
def lista_de_fichas(destino: str, busca: str | None = None, so: str | None = None,
                    pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """As fichas, maior ressarcimento primeiro. `so` recorta as que pedem atenção:
    `negativas`, `sem_aliquota`, `indefinidas`."""
    recortes = {"negativas": "ficou_negativo", "sem_aliquota": "saidas_sem_aliquota > 0",
                "indefinidas": "saidas_indefinidas > 0"}
    if so and so not in recortes:
        raise ValueError(f"Recorte desconhecido: {so}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_FICHAS)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_FICHAS} não está em {destino}.")
    filtros, parametros = [], []
    if so:
        filtros.append(recortes[so])
    if busca and busca.strip():
        filtros.append("(codigo ILIKE ? OR descricao ILIKE ? OR cnpj ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 3
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"
    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY ressarcimento DESC, cnpj, codigo
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [_jsonavel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def linhas_da_ficha(destino: str, cnpj: str, codigo: str,
                    pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Uma página da Ficha 3 de uma mercadoria num estabelecimento, em ordem."""
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_FICHA3)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_FICHA3} não está em {destino}.")
    con = _leitura(destino)
    try:
        base = f"read_parquet('{_escapar(caminho)}') WHERE cnpj = ? AND codigo = ?"
        total = con.execute(f"SELECT count(*) FROM {base}", [cnpj, codigo]).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY numero
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, [cnpj, codigo])
        nomes = [c[0] for c in cursor.description]
        linhas = [_jsonavel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def _jsonavel(linha: dict) -> dict:
    """Decimal vira texto e data vira ISO: é o que atravessa o JSON sem perder casa."""
    saida = {}
    for k, v in linha.items():
        if isinstance(v, Decimal):
            saida[k] = str(v.normalize()) if v == v.to_integral() else format(v.normalize(), "f")
        elif hasattr(v, "isoformat"):
            saida[k] = v.isoformat()
        else:
            saida[k] = v
    return saida


def serializar(resumo: ResumoDaMontagem) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    def texto(v):
        return format(Decimal(v).quantize(Decimal("0.01")), "f")
    rotulos = {"1": "Consumidor final", "2": "Fato gerador não realizado",
               "3": "Isenção ou não incidência", "4": "Outro estado",
               "0": "Demais saídas", "indefinido": "Indefinido"}
    return {
        "periodo_inicio": resumo.periodo_inicio,
        "periodo_fim": resumo.periodo_fim,
        "abertura_em": resumo.abertura_em,
        "codigos_com_st": resumo.codigos_com_st,
        "fichas": resumo.fichas,
        "estabelecimentos": resumo.estabelecimentos,
        "linhas": resumo.linhas,
        "ressarcimento": texto(resumo.ressarcimento),
        "complemento": texto(resumo.complemento),
        "por_enquadramento": [
            {"codigo": k, "rotulo": rotulos.get(k, k), "linhas": v["linhas"],
             "quantidade": texto(v["quantidade"]), "suportado": texto(v["suportado"]),
             "confronto": texto(v["confronto"]), "ressarcimento": texto(v["ressarcimento"]),
             "complemento": texto(v["complemento"])}
            for k, v in sorted(resumo.por_enquadramento.items(),
                               key=lambda kv: ("1", "2", "3", "4", "0", "indefinido").index(kv[0]))
        ],
        "por_competencia": [
            {"competencia": k, "linhas": v["linhas"], "ressarcimento": texto(v["ressarcimento"]),
             "complemento": texto(v["complemento"])}
            for k, v in sorted(resumo.por_competencia.items())
        ],
        "saidas_por_origem": resumo.saidas_por_origem,
        "pendencias": {
            "saidas_sem_aliquota": resumo.saidas_sem_aliquota,
            "saidas_indefinidas": resumo.saidas_indefinidas,
            "confronto_pendente": resumo.confronto_pendente,
            "fichas_negativas": resumo.fichas_negativas,
            "fichas_abertura_sem_valor": resumo.fichas_abertura_sem_valor,
            "fichas_fora_de_sp": resumo.fichas_fora_de_sp,
            "relatorio_sem_estabelecimento": resumo.relatorio_sem_estabelecimento,
            "relatorio_trocado_pela_efd": resumo.relatorio_trocado_pela_efd,
            "quantidade_negativa": resumo.quantidade_negativa,
        },
    }
