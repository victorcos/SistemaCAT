"""CAT 42 por filial e produto, no leiaute v5 — o acordado na empresa 18 —, sobre a base da empresa 17.

A Ficha 3 é por estabelecimento, e o de-para também: cada linha é uma filial + COD_ITEM.

O que muda em relação à v5 da empresa 18, por falta de fonte — e não por escolha:

* **Não há XML na base.** Os 15 lotes com "XML" no nome só contêm relatório. Caem a
  unidade e a descrição do XML, o GTIN de caixa (DUN-14) pelos 12 dígitos do meio,
  a base do ST do XML e o descarte do XML pareado com o item errado. O 2º fator de
  conversão sobra só com a unidade e a descrição da própria nota.
* **A base do ST é vazia** (294 linhas de entrada em 3,1 milhões): o C170 do
  comprador não traz `VL_BC_ICMS_ST`, e era o XML que traria. MVA, IVA médio e a
  relação Base ST / Venda saem em branco — ficam de coluna pronta para quando o
  XML chegar.
* **As entradas não retroagem.** A EFD registrada cobre 01 a 08/2026, o mesmo
  intervalo das saídas; na v5 da empresa 18 elas começavam 3 meses antes.
* **As linhas do relatório de movimentação com CFOP de entrada saem das saídas** —
  não são venda — e não entram como entrada, porque o C170 da EFD já as cobre.
  Somá-las duplicaria a compra.

Uso: relatorio_cat42_filial.py <pasta_da_execucao> <saida.xlsx> [titulo]
"""
from __future__ import annotations

import logging
import os
import sys
import time
from collections import defaultdict

import duckdb

from cat.dominio.icms.cat42.enquadramento import CFOP_DEVOLUCAO

from relatorio_cat42_filial_comum import (ESTOQUE, FAIXA_BOA, MESMO, PARADO, RAZAO_SUSPEITA, SEM_PAR, SITUACOES_REGULARES,
                             SO_ENTRADA, UNIFICADO, ean, fator_da_descricao, fator_da_unidade, n, sem_acento)
from relatorio_cat42_filial_planilha import escrever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("relatorio_cat42_filial")

CAMPOS_ENT = ("fornecedores cfops csts conversoes unidades ncms quantidade devolucao valor unit_min unit_max "
              "data_min data_max icms_min icms_max icms_total bcst_min bcst_max bcst_total itens_sem_bcst "
              "linhas nfs nfs_sem_bcst nfs_sem_st mva_min mva_max descricao descricoes tem_st").split()
CAMPOS_SAI = ("cfops csts unidades ncms quantidade devolucao valor valor_interestadual unit_min unit_max "
              "data_min data_max icms_min icms_max icms_total descricao descricoes tem_st").split()

LEIA_ME = """Layout do relatório 'CAT 42 - Ressarcimento consolidado por produto', POR FILIAL, com o de-para ao lado do item.
A Ficha 3 é por estabelecimento, e o de-para também: cada linha é uma filial + COD_ITEM. Ordem: filial, situação no de-para, valor de entradas.
Ficam só os participantes: filial+código com alguma linha de ST (CST x10/x30/x60/x70 ou CSOSN 201/202/203/500).

SITUAÇÃO DO ITEM (na filial):
  não precisa: compra e venda no mesmo código — a ficha fecha sozinha.
  unificado — o mesmo produto era comprado num código e vendido em outro, DESTA filial. O código de VENDA prevalece:
     todo o movimento do código antigo de entrada (compras, devoluções, estoque inicial) passa para o código de venda;
     o código antigo deixa de ter linha própria e aparece na coluna C (CÓDIGO ANTIGO). Lista completa na aba 'Códigos unificados'.
     1º pelo MESMO EAN no cadastro (0200); sem achar pelo EAN, pela descrição do cadastro EXATAMENTE igual. Nada além disso é ligado.
     Um código antigo que serviria a mais de um código de venda não é ligado: vai para a análise manual.
  não precisa: saída coberta pelo estoque inicial — vende sem compra, mas tinha no inventário de 31/12/2025 (bloco H) quantidade
     suficiente para a saída do período. O inventário de 31/12 vem na EFD de janeiro e de novo na de fevereiro: é contado uma vez
     (o da EFD mais recente que o traz).
  sem par: saída sem entrada — vende sem compra, sem estoque e sem EAN/descrição igual: fica EM BRANCO para a análise manual.
     Se 'compra em OUTRAS filiais' > 0, o mesmo código é comprado em outra filial: provável transferência fora da base.
  só entrada na base (sem saída no período) — comprou e não vendeu no período.

SEM PAR (aba): os itens 'sem par' para a análise manual, com colunas amarelas para preencher (código certo, fator, observação).
ENTRADA SEM SAÍDA (aba): os códigos que compram e não vendem na filial — onde procurar o par na análise manual.
CONFERIR UNIDADE (aba): a compra que ainda parece estar em caixa depois do 0220, com a coluna amarela para o fator correto.
CÓDIGOS UNIFICADOS (aba): cada par antigo → novo, com os EANs, o motivo e as unidades dos dois.
RESUMO POR FILIAL (aba): quantos itens de cada situação em cada filial.

PERÍODO: SAÍDAS e ENTRADAS de 01/01 a 31/08/2026. Na v5 da empresa 18 as entradas retroagiam 3 meses; aqui não há EFD anterior
  registrada, então a compra feita antes de janeiro não aparece — e o item dela cai em 'sem par' ou no estoque inicial.
DOCUMENTOS: só os regulares (situações 00, 01, 06, 07 e 08).

ENTRADAS: compras sem devolução; 'Quantidade - Devolução' = devolução de compra (negativa). CNPJs = emitentes, lidos da chave.
SAÍDAS: vendas e transferências sem devolução; 'Quantidade - Devolução' = devolução de venda. Interestadual = CFOP 6xxx.
  As linhas do relatório de movimentação que vieram com CFOP de ENTRADA (1xxx/2xxx) foram tiradas das saídas: não são venda.
  Elas não foram somadas às entradas porque o C170 da EFD já cobre a compra — somar duplicaria.

UNIDADE DAS ENTRADAS: a quantidade comprada vem na menor unidade (a do cadastro, a mesma da venda): 3 CX de 10 = 30 UN.
  1º pelo fator que a filial declara na EFD (0220); 2º, quando a compra ainda parece estar em caixa (custo médio acima de
  1,3x o preço de venda), pelo fator da própria nota — a unidade (CX12, FD6) ou a descrição (C/10, 24X200G) — e só se o fator
  explicar a diferença: custo/venda dividido pelo fator tem de cair entre 0,3 e 1,3.
  A coluna 'ENTRADA - Conversão de unidade aplicada' mostra o que foi feito em cada item.

SEM XML NESTA BASE: os lotes com 'XML' no nome só têm relatório. Por isso ficam vazias as colunas de base do ST
  (o C170 do comprador não preenche VL_BC_ICMS_ST: 294 linhas em 3,1 milhões), e com elas MVA ST, IVA Médio e a relação
  Base do ST / Venda. São colunas prontas para quando o XML das entradas chegar.

DESCRIÇÕES: cada item mostra como veio na NOTA DE COMPRA (C170) e como SAIU NA VENDA (relatório do ERP). Com mais de uma
  descrição, vai a de maior valor e '(+N outras)'. Sem compra (ou sem venda) na filial, aparece '— sem compra nesta filial —
  cadastro: <descrição do 0200>'. 'A descrição bate?': confere = mesmas palavras/abreviações (CERV = CERVEJA);
  conferir — medida diferente = 350ML x 473ML; conferir — descrição diferente = poucas palavras em comum.

FORA DESTA VERSÃO: relevância, ressarcimento/complemento por enquadramento e estoque — dependem do razão com o de-para.
Fonte: execução {execucao} do SistemaCAT (projeto 32), de-para por EAN / descrição idêntica."""


# ---------------------------------------------------------------------------
# banco
# ---------------------------------------------------------------------------
def abrir(pasta: str):
    """Conexão em arquivo, com o rascunho na pasta da execução — que está no disco grande."""
    banco = os.path.join(pasta, "relatorio_v5.duckdb")
    for sufixo in ("", ".wal"):
        if os.path.exists(banco + sufixo):
            os.remove(banco + sufixo)
    con = duckdb.connect(banco)
    con.execute(f"SET temp_directory = '{pasta}'")
    con.execute(f"SET memory_limit = '{os.environ.get('CAT_MEMORIA_ANALITICA', '4GB')}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"SET threads = {os.environ.get('CAT_THREADS_ANALITICAS', '4')}")
    return con


def preparar(con, pasta: str) -> None:
    def p(nome: str) -> str:
        return os.path.join(pasta, nome).replace("\\", "/")

    devol = ", ".join(f"'{c}'" for c in sorted(CFOP_DEVOLUCAO))
    regulares = ", ".join(f"'{s}'" for s in SITUACOES_REGULARES)
    # CST x10/x30/x60/x70 do regime normal, ou CSOSN 201/202/203/500 do Simples
    tem_st = ("(right(coalesce(cst_icms, ''), 2) IN ('10','30','60','70')"
              " OR coalesce(cst_icms, '') IN ('201','202','203','500'))")
    # só para ensaiar o roteiro numa filial antes de soltar nas 30
    uma = os.environ.get("CAT42_FILIAL", "").strip()
    so_uma_filial = f"AND m.cnpj = '{uma}'" if uma else ""
    if uma:
        log.warning("ENSAIO: só a filial %s", uma)

    con.execute(f"""
        CREATE OR REPLACE TABLE cad AS
        SELECT cnpj, codigo,
               max_by(descricao, competencia) AS descricao,
               max_by(codigo_barras, competencia) AS codigo_barras,
               max_by(unidade, competencia) AS unidade,
               max_by(ncm, competencia) AS ncm,
               max_by(cest, competencia) AS cest,
               max_by(aliq_icms, competencia) AS aliq_icms
        FROM read_parquet('{p("itens.parquet")}')
        GROUP BY cnpj, codigo
    """)
    log.info("cadastro 0200: %d filial+código", con.execute("SELECT count(*) FROM cad").fetchone()[0])

    con.execute(f"""
        CREATE OR REPLACE TABLE fator AS
        SELECT cnpj, codigo, upper(trim(unidade)) AS unidade, max_by(fator, competencia) AS fator
        FROM read_parquet('{p("conversoes.parquet")}')
        WHERE fator IS NOT NULL AND fator > 0
        GROUP BY 1, 2, 3
    """)

    # o inventário mais antigo, contado uma vez: o de 31/12 vem na EFD de janeiro
    # e de novo na de fevereiro, então fica o da EFD mais recente que o traz
    con.execute(f"CREATE OR REPLACE TABLE inv AS SELECT * FROM read_parquet('{p('inventario.parquet')}')")
    con.execute("""
        CREATE OR REPLACE TABLE estoque AS
        WITH antigo AS (SELECT min(data_inventario) AS d FROM inv),
             fonte AS (SELECT i.cnpj, max(i.competencia) AS c
                       FROM inv i, antigo a WHERE i.data_inventario = a.d GROUP BY 1)
        SELECT i.cnpj, i.codigo, sum(i.quantidade) AS quantidade, sum(i.valor) AS valor
        FROM inv i JOIN fonte f ON f.cnpj = i.cnpj AND f.c = i.competencia, antigo a
        WHERE i.data_inventario = a.d
        GROUP BY 1, 2
    """)
    log.info("estoque de abertura: %d filial+código",
             con.execute("SELECT count(*) FROM estoque").fetchone()[0])

    con.execute(f"""
        CREATE OR REPLACE VIEW base AS
        SELECT m.cnpj, m.codigo, m.data, m.chave, m.operacao,
               replace(m.cfop, '.', '') AS cfop, m.cst_icms,
               upper(trim(coalesce(m.unidade, ''))) AS unidade_nota,
               coalesce(f.fator, 1) AS fator_0220,
               m.quantidade * coalesce(f.fator, 1) AS qtd,
               m.valor - coalesce(m.desconto, 0) AS valor,
               m.valor_icms, m.bc_st,
               coalesce(nullif(trim(m.descricao_relatorio), ''),
                        nullif(trim(m.descricao_complementar), '')) AS descricao_doc,
               m.ncm_relatorio,
               replace(m.cfop, '.', '') IN ({devol}) AS devolucao,
               {tem_st} AS st
        FROM read_parquet('{p("movimentos.parquet")}') m
        LEFT JOIN fator f ON f.cnpj = m.cnpj AND f.codigo = m.codigo
                         AND f.unidade = upper(trim(coalesce(m.unidade, '')))
        WHERE m.situacao IN ({regulares})
          AND m.quantidade IS NOT NULL AND m.quantidade <> 0
          AND NOT (m.operacao = 'saida' AND left(replace(m.cfop, '.', ''), 1) IN ('1', '2'))
          {so_uma_filial}
    """)

    inicio = time.time()
    con.execute("""
        CREATE OR REPLACE TABLE ent AS
        SELECT cnpj, codigo,
               list_distinct(list(DISTINCT substr(chave, 7, 14)) FILTER (WHERE NOT devolucao)) AS fornecedores,
               list_distinct(list(DISTINCT cfop) FILTER (WHERE NOT devolucao)) AS cfops,
               list_distinct(list(DISTINCT cst_icms) FILTER (WHERE NOT devolucao)) AS csts,
               list_distinct(list(DISTINCT unidade_nota || ' x' || CAST(fator_0220 AS VARCHAR))
                             FILTER (WHERE NOT devolucao)) AS conversoes,
               list_distinct(list(DISTINCT unidade_nota) FILTER (WHERE NOT devolucao)) AS unidades,
               list_distinct(list(DISTINCT ncm_relatorio) FILTER (WHERE NOT devolucao)) AS ncms,
               sum(qtd) FILTER (WHERE NOT devolucao) AS quantidade,
               -sum(qtd) FILTER (WHERE devolucao) AS devolucao,
               sum(valor) FILTER (WHERE NOT devolucao) AS valor,
               min(valor / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS unit_min,
               max(valor / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS unit_max,
               min(data) FILTER (WHERE NOT devolucao) AS data_min,
               max(data) FILTER (WHERE NOT devolucao) AS data_max,
               min(valor_icms / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS icms_min,
               max(valor_icms / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS icms_max,
               sum(valor_icms) FILTER (WHERE NOT devolucao) AS icms_total,
               min(bc_st / qtd) FILTER (WHERE NOT devolucao AND qtd > 0 AND bc_st > 0) AS bcst_min,
               max(bc_st / qtd) FILTER (WHERE NOT devolucao AND qtd > 0 AND bc_st > 0) AS bcst_max,
               sum(bc_st) FILTER (WHERE NOT devolucao) AS bcst_total,
               count(*) FILTER (WHERE NOT devolucao AND coalesce(bc_st, 0) = 0) AS itens_sem_bcst,
               count(*) FILTER (WHERE NOT devolucao) AS linhas,
               count(DISTINCT chave) FILTER (WHERE NOT devolucao) AS nfs,
               count(DISTINCT chave) FILTER (WHERE NOT devolucao AND coalesce(bc_st, 0) = 0) AS nfs_sem_bcst,
               count(DISTINCT chave) FILTER (WHERE NOT devolucao AND NOT st) AS nfs_sem_st,
               min(bc_st / nullif(valor, 0) - 1) FILTER (WHERE NOT devolucao AND bc_st > 0) AS mva_min,
               max(bc_st / nullif(valor, 0) - 1) FILTER (WHERE NOT devolucao AND bc_st > 0) AS mva_max,
               max_by(descricao_doc, valor) FILTER (WHERE NOT devolucao) AS descricao,
               count(DISTINCT descricao_doc) FILTER (WHERE NOT devolucao) AS descricoes,
               bool_or(st) AS tem_st
        FROM base WHERE operacao = 'entrada'
        GROUP BY cnpj, codigo
    """)
    log.info("bloco das entradas: %d filial+código (%.0fs)",
             con.execute("SELECT count(*) FROM ent").fetchone()[0], time.time() - inicio)

    inicio = time.time()
    con.execute("""
        CREATE OR REPLACE TABLE sai AS
        SELECT cnpj, codigo,
               list_distinct(list(DISTINCT cfop) FILTER (WHERE NOT devolucao)) AS cfops,
               list_distinct(list(DISTINCT cst_icms) FILTER (WHERE NOT devolucao)) AS csts,
               list_distinct(list(DISTINCT unidade_nota) FILTER (WHERE NOT devolucao)) AS unidades,
               list_distinct(list(DISTINCT ncm_relatorio) FILTER (WHERE NOT devolucao)) AS ncms,
               sum(qtd) FILTER (WHERE NOT devolucao) AS quantidade,
               -sum(qtd) FILTER (WHERE devolucao) AS devolucao,
               sum(valor) FILTER (WHERE NOT devolucao) AS valor,
               sum(valor) FILTER (WHERE NOT devolucao AND left(cfop, 1) = '6') AS valor_interestadual,
               min(valor / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS unit_min,
               max(valor / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS unit_max,
               min(data) FILTER (WHERE NOT devolucao) AS data_min,
               max(data) FILTER (WHERE NOT devolucao) AS data_max,
               min(valor_icms / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS icms_min,
               max(valor_icms / qtd) FILTER (WHERE NOT devolucao AND qtd > 0) AS icms_max,
               sum(valor_icms) FILTER (WHERE NOT devolucao) AS icms_total,
               max_by(descricao_doc, valor) FILTER (WHERE NOT devolucao) AS descricao,
               count(DISTINCT descricao_doc) FILTER (WHERE NOT devolucao) AS descricoes,
               bool_or(st) AS tem_st
        FROM base WHERE operacao = 'saida'
        GROUP BY cnpj, codigo
    """)
    log.info("bloco das saídas: %d filial+código (%.0fs)",
             con.execute("SELECT count(*) FROM sai").fetchone()[0], time.time() - inicio)

    con.execute("""
        CREATE OR REPLACE TABLE compra_em AS
        SELECT codigo, count(DISTINCT cnpj) AS filiais FROM ent WHERE quantidade > 0 GROUP BY 1
    """)


def juntar(con) -> list[dict]:
    """Uma linha por filial + código, com os dois blocos e o cadastro ao lado."""
    sel_e = ", ".join(f"e.{c} AS e_{c}" for c in CAMPOS_ENT)
    sel_s = ", ".join(f"s.{c} AS s_{c}" for c in CAMPOS_SAI)
    cur = con.execute(f"""
        SELECT c.cnpj, c.codigo, c.descricao AS cad_descricao, c.codigo_barras, c.unidade AS cad_unidade,
               c.ncm AS cad_ncm, c.cest AS cad_cest, c.aliq_icms AS cad_aliq,
               {sel_e}, {sel_s},
               coalesce(q.quantidade, 0) AS estoque_qtd,
               coalesce(f.filiais, 0) AS filiais_que_compram
        FROM cad c
        LEFT JOIN ent e ON e.cnpj = c.cnpj AND e.codigo = c.codigo
        LEFT JOIN sai s ON s.cnpj = c.cnpj AND s.codigo = c.codigo
        LEFT JOIN estoque q ON q.cnpj = c.cnpj AND q.codigo = c.codigo
        LEFT JOIN compra_em f ON f.codigo = c.codigo
        WHERE e.codigo IS NOT NULL OR s.codigo IS NOT NULL
        ORDER BY c.cnpj, c.codigo
    """)
    nomes = [d[0] for d in cur.description]
    return [dict(zip(nomes, linha)) for linha in cur.fetchall()]


# ---------------------------------------------------------------------------
# 2º fator: a compra que ainda parece estar em caixa
# ---------------------------------------------------------------------------
def fator_da_caixa(item: dict) -> tuple[int | None, str, float, float, float]:
    """O fator da própria nota, quando o 0220 não converteu e o preço denuncia a caixa.

    Só entra se explicar a diferença: a razão custo/venda dividida pelo fator tem de
    cair na faixa de um varejo. Senão fica o diagnóstico, para a análise manual.
    """
    qe, ve = n(item.get("e_quantidade")), n(item.get("e_valor"))
    qs, vs = n(item.get("s_quantidade")), n(item.get("s_valor"))
    if not (qe and ve and qs and vs) or qe <= 0 or qs <= 0:
        return None, "", 0.0, 0.0, 0.0
    custo, preco = ve / qe, vs / qs
    if preco <= 0:
        return None, "", custo, preco, 0.0
    razao = custo / preco
    if razao <= RAZAO_SUSPEITA:
        return None, "", custo, preco, razao
    for unidade in sorted(item.get("e_unidades") or [], key=len, reverse=True):
        f = fator_da_unidade(unidade)
        if f and FAIXA_BOA[0] <= razao / f <= FAIXA_BOA[1]:
            return f, f"CONVERTIDO: 1 {unidade} = {f} (fator da unidade da nota)", custo, preco, razao
    f = fator_da_descricao(item.get("e_descricao") or "")
    if f and FAIXA_BOA[0] <= razao / f <= FAIXA_BOA[1]:
        return f, f"CONVERTIDO: fator {f} (achado na descrição da nota)", custo, preco, razao
    return None, f"custo de compra = {razao:.1f}x o preço de venda: pode ser caixa — informe o fator", \
        custo, preco, razao


def aplicar_fator(item: dict, f: int) -> None:
    """O fator multiplica a quantidade e divide o que é por unidade. O valor total não muda."""
    for campo in ("e_quantidade", "e_devolucao"):
        if item.get(campo) is not None:
            item[campo] = n(item[campo]) * f
    for campo in ("e_unit_min", "e_unit_max", "e_icms_min", "e_icms_max", "e_bcst_min", "e_bcst_max"):
        if item.get(campo) is not None:
            item[campo] = n(item[campo]) / f


# ---------------------------------------------------------------------------
# unificação de códigos, sempre dentro da mesma filial
# ---------------------------------------------------------------------------
def unificar(itens: list[dict]) -> dict:
    """Liga um código que vende a um código que só compra. O de venda prevalece.

    1º pelo mesmo EAN do cadastro; sem EAN igual, pela descrição do cadastro
    exatamente igual. Nada além disso. Um código antigo que serviria a mais de um
    código de venda não é unificado — vai à análise manual. Cadeia não acontece:
    o antigo, por construção, não vende.
    """
    por_filial: dict[str, list[dict]] = defaultdict(list)
    for item in itens:
        por_filial[item["cnpj"]].append(item)

    ligacoes: dict[tuple[str, str], tuple[str, str]] = {}
    ambiguos = 0
    for cnpj, linhas in por_filial.items():
        vende = [i for i in linhas if n(i.get("s_quantidade")) and n(i["s_quantidade"]) > 0]
        so_compra = [i for i in linhas
                     if n(i.get("e_quantidade")) and n(i["e_quantidade"]) > 0
                     and not (n(i.get("s_quantidade")) and n(i["s_quantidade"]) > 0)]
        if not vende or not so_compra:
            continue
        por_ean: dict[str, list[dict]] = defaultdict(list)
        por_desc: dict[str, list[dict]] = defaultdict(list)
        for v in vende:
            g = ean(v.get("codigo_barras"))
            if g:
                por_ean[g].append(v)
            d = sem_acento(v.get("cad_descricao")).strip()
            if d:
                por_desc[d].append(v)
        for a in so_compra:
            g = ean(a.get("codigo_barras"))
            alvos = por_ean.get(g, []) if g else []
            motivo = "mesmo EAN no cadastro"
            if not alvos:
                d = sem_acento(a.get("cad_descricao")).strip()
                alvos = por_desc.get(d, []) if d else []
                motivo = "descrição do cadastro exatamente igual"
            if len(alvos) == 1:
                ligacoes[(cnpj, a["codigo"])] = (alvos[0]["codigo"], motivo)
            elif len(alvos) > 1:
                ambiguos += 1
    log.info("unificação: %d ligações; %d códigos antigos ficaram de fora por servirem a mais de um código de venda",
             len(ligacoes), ambiguos)
    return ligacoes


def aplicar_unificacao(itens: list[dict], ligacoes: dict) -> list[dict]:
    """Passa o movimento do código antigo para o de venda e marca o antigo para sair."""
    por_chave = {(i["cnpj"], i["codigo"]): i for i in itens}
    unificados: list[dict] = []
    for (cnpj, antigo), (novo, motivo) in ligacoes.items():
        a, novo_item = por_chave.get((cnpj, antigo)), por_chave.get((cnpj, novo))
        if a is None or novo_item is None:
            continue
        for campo in ("e_quantidade", "e_devolucao", "e_valor", "e_icms_total", "e_bcst_total",
                      "e_itens_sem_bcst", "e_linhas", "e_nfs", "e_nfs_sem_bcst", "e_nfs_sem_st", "estoque_qtd"):
            if a.get(campo) is not None:
                novo_item[campo] = (n(novo_item.get(campo)) or 0) + n(a[campo])
        for campo in ("e_unit_min", "e_icms_min", "e_bcst_min", "e_mva_min"):
            if a.get(campo) is not None:
                atual = novo_item.get(campo)
                novo_item[campo] = n(a[campo]) if atual is None else min(n(atual), n(a[campo]))
        for campo in ("e_unit_max", "e_icms_max", "e_bcst_max", "e_mva_max"):
            if a.get(campo) is not None:
                atual = novo_item.get(campo)
                novo_item[campo] = n(a[campo]) if atual is None else max(n(atual), n(a[campo]))
        if a.get("e_data_min") is not None:
            atual = novo_item.get("e_data_min")
            novo_item["e_data_min"] = a["e_data_min"] if atual is None else min(atual, a["e_data_min"])
        if a.get("e_data_max") is not None:
            atual = novo_item.get("e_data_max")
            novo_item["e_data_max"] = a["e_data_max"] if atual is None else max(atual, a["e_data_max"])
        for campo in ("e_fornecedores", "e_cfops", "e_csts", "e_conversoes", "e_unidades", "e_ncms"):
            novo_item[campo] = sorted(set(list(novo_item.get(campo) or []) + list(a.get(campo) or [])))
        if not novo_item.get("e_descricao"):
            novo_item["e_descricao"] = a.get("e_descricao")
        novo_item["e_tem_st"] = bool(novo_item.get("e_tem_st")) or bool(a.get("e_tem_st"))
        novo_item.setdefault("antigos", []).append(a)
        novo_item.setdefault("motivos", []).append(motivo)
        a["removido"] = True
        unificados.append({"cnpj": cnpj, "novo": novo_item, "antigo": a, "motivo": motivo})
    return unificados


def classificar(item: dict) -> str:
    tem_e = bool(n(item.get("e_quantidade")) and n(item["e_quantidade"]) > 0)
    tem_s = bool(n(item.get("s_quantidade")) and n(item["s_quantidade"]) > 0)
    if item.get("antigos"):
        return UNIFICADO
    if tem_e and tem_s:
        return MESMO
    if tem_s and not tem_e:
        if (n(item.get("estoque_qtd")) or 0) >= n(item["s_quantidade"]):
            return ESTOQUE
        return SEM_PAR
    if tem_e and not tem_s:
        return SO_ENTRADA
    return PARADO


# ---------------------------------------------------------------------------
def main(pasta: str, saida: str, titulo: str) -> None:
    inicio = time.time()
    log.info("fonte: %s", pasta)
    con = abrir(pasta)
    preparar(con, pasta)

    itens = juntar(con)
    log.info("filial+código com movimento: %d (%.0fs)", len(itens), time.time() - inicio)

    ligacoes = unificar(itens)
    unificados = aplicar_unificacao(itens, ligacoes)
    itens = [i for i in itens if not i.get("removido")]

    # o 2º fator vem depois da unificação: a compra do código antigo já entrou
    conferir, convertidos = [], 0
    for i in itens:
        f, diagnostico, custo, preco, razao = fator_da_caixa(i)
        if f:
            aplicar_fator(i, f)
            convertidos += 1
        if diagnostico:
            antigos = i.get("antigos") or []
            conferir.append({
                "cnpj": i["cnpj"], "codigo": i["codigo"],
                "codigo_antigo": ", ".join(x["codigo"] for x in antigos),
                "descricao": i.get("cad_descricao") or "",
                "unidade_nota": ", ".join(sorted(i.get("e_unidades") or [])[:4]),
                "linhas": i.get("e_linhas") or 0,
                "quantidade": n(i.get("e_quantidade")) or 0.0,
                "custo": custo, "preco": preco, "razao": razao,
                "ja_0220": "sim" if any("x1.0" not in c for c in (i.get("e_conversoes") or [])) else "não",
                "diagnostico": diagnostico,
                "convertido": bool(f),
            })
    log.info("fator da caixa: %d itens convertidos, %d na aba Conferir unidade", convertidos, len(conferir))

    for i in itens:
        i["situacao"] = classificar(i)
        if i.get("antigos"):
            i["conversao_texto"] = "unificado: " + ", ".join(x["codigo"] for x in i["antigos"])

    # participantes: o código com alguma linha de ST, nele ou no antigo que ele absorveu
    antes = len(itens)
    itens = [i for i in itens if i.get("e_tem_st") or i.get("s_tem_st")]
    log.info("participantes (com linha de ST): %d de %d", len(itens), antes)

    itens.sort(key=lambda i: (i["cnpj"],
                              {UNIFICADO: 0, SEM_PAR: 1, MESMO: 2, ESTOQUE: 3, SO_ENTRADA: 4, PARADO: 5}
                              .get(i["situacao"], 9),
                              -(n(i.get("e_valor")) or 0.0)))
    conferir.sort(key=lambda c: -c["quantidade"])

    filiais = len({i["cnpj"] for i in itens})
    periodo = "01/01/2026 a 31/08/2026"
    escrever(itens, unificados, conferir, saida, titulo or "CAT 42 - Consolidado por filial e produto",
             filiais, periodo, LEIA_ME.format(execucao=os.path.basename(pasta)))
    tamanho = os.path.getsize(saida) / 1e6 if os.path.exists(saida) else 0
    log.info("planilha gravada: %s (%d linhas filial+item, %.1f MB) em %.0fs",
             saida, len(itens), tamanho, time.time() - inicio)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
