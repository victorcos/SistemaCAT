"""Varrer os XML do trabalho e separar o que entra no crédito outorgado.

Portado do projeto `Quebra de SPED`, onde a funcionalidade nasceu e roda desde
então sobre 120 mil XML por vez. O que mudou na travessia:

* **o leitor é o da casa** (`dominio/notafiscal/xml`), e não um parser próprio.
  Com ele vêm de graça as coisas que a origem não tinha: CF-e SAT lido junto com
  a NF-e, CT-e e evento de cancelamento reconhecidos e ignorados, nota denegada
  fora da conta, XML declarado UTF-8 e gravado em Latin-1 relido em vez de
  perdido, e o zip aberto sem extrair para o disco;
* **a saída é parquet**, e não CSV — a planilha sai depois, a pedido, com o
  recorte que a tela pediu. É o caminho de todas as etapas daqui;
* **uma cópia por chave.** A mesma nota vem no zip do mês e no do trimestre; na
  empresa 04 foram 28.407 chaves repetidas. Contar duas vezes inflaria o valor
  elegível, que é o número que interessa;
* **só o que a empresa vendeu.** O benefício é sobre a saída, e o lote costuma
  ter tudo junto — a nota que a empresa emitiu e a que ela recebeu do
  fornecedor. Na origem isso não era problema porque a pessoa apontava uma
  pasta já separada; aqui a base é o lote inteiro do trabalho. Quem decide não é
  o `tpNF` sozinho (ver `DocumentoXml.saida_de`), e o que fica de fora é
  contado, não sumido;
* **três listas viraram duas**: elegíveis, sempre, e descartados, a pedido. A
  terceira ("todos") era a soma das duas, e some quem soma.

Não depende de etapa nenhuma: lê os XML do lote direto. É o mesmo preço que a
quebra e a apuração de PIS/COFINS pagam — reler o arquivo — em troca de as
funcionalidades não dependerem umas das outras (DECISOES, 23/09/2026).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import duckdb
import pyarrow as pa

from cat.dominio.icms.credito_outorgado import Filtro
from cat.dominio.notafiscal.xml import DocumentoXml, ItemDoXml, XmlIlegivel, ler_documento_xml
from cat.infraestrutura.analitico.confronto import _escapar
from cat.infraestrutura.analitico.escrita import LeituraCancelada, parar_se_pedirem
from cat.infraestrutura.analitico.extracao import Aviso, Progresso, _Escritor
from cat.infraestrutura.analitico.suportado import _leitura
from cat.infraestrutura.arquivos.xml_compactado import contar_xml, conteudos_de_xml
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ELEGIVEIS = "credito_outorgado_elegiveis.parquet"
ARQUIVO_DESCARTADOS = "credito_outorgado_descartados.parquet"

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_Q5 = Decimal("0.00001")
_Q10 = Decimal("0.0000000001")
_CEM = Decimal(100)

ESQUEMA = pa.schema([
    ("arquivo", pa.string()),
    ("chave", pa.string()),
    ("modelo", pa.string()),
    # tpNF: 0 entrada, 1 saída, do ponto de vista de quem emitiu
    ("tipo", pa.string()),
    ("numero_documento", pa.string()),
    ("serie", pa.string()),
    ("emissao", pa.date32()),
    ("emitente", pa.string()),
    ("emitente_nome", pa.string()),
    ("destinatario", pa.string()),
    ("destinatario_nome", pa.string()),
    ("numero_item", pa.int32()),
    ("codigo", pa.string()),
    ("descricao", pa.string()),
    ("ncm", pa.string()),
    ("cest", pa.string()),
    ("cfop", pa.string()),
    ("unidade", pa.string()),
    ("quantidade", pa.decimal128(20, 5)),
    ("valor_unitario", pa.decimal128(28, 10)),
    ("valor", pa.decimal128(18, 2)),
    ("cst_icms", pa.string()),
    ("bc_icms", pa.decimal128(18, 2)),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("valor_icms", pa.decimal128(18, 2)),
    ("cst_pis", pa.string()),
    ("bc_pis", pa.decimal128(18, 2)),
    ("aliq_pis", pa.decimal128(9, 4)),
    ("valor_pis", pa.decimal128(18, 2)),
    ("cst_cofins", pa.string()),
    ("bc_cofins", pa.decimal128(18, 2)),
    ("aliq_cofins", pa.decimal128(9, 4)),
    ("valor_cofins", pa.decimal128(18, 2)),
    ("elegivel", pa.bool_()),
    # "DESCRIÇÃO", "NCM+DESCRIÇÃO" ou "SEM FILTRO"; vazio no descartado
    ("motivo", pa.string()),
])

# a cópia autorizada vale mais que a sem protocolo; a denegada não entra
_PRIORIDADE_AUTORIZADA = 2
_PRIORIDADE_SEM_PROTOCOLO = 1


@dataclass
class ProgressoDoCredito(Progresso):
    """O `Progresso` de sempre mais o que esta varredura conta."""

    itens: int = 0
    elegiveis: int = 0
    descartados: int = 0
    # o que os itens elegíveis somam, em centavos — inteiro, como toda a casa
    centavos_elegiveis: int = 0
    repetidos: int = 0
    nao_sao_documento: int = 0
    # nota que não é saída da empresa do trabalho: compra, ou de outra empresa
    nao_sao_saida: int = 0
    nao_autorizados: int = 0
    ilegiveis: int = 0
    exemplos_ilegiveis: list[str] = field(default_factory=list)


def _q(valor: Decimal, casas: Decimal) -> Decimal:
    return valor.quantize(casas, rounding=ROUND_HALF_UP)


def varrer(xmls: list[str], destino: str, filtro: Filtro, *,
           raiz_do_cnpj: str = "",
           incluir_descartados: bool = False,
           avisar: Aviso | None = None,
           deve_parar: Callable[[], bool] | None = None) -> ProgressoDoCredito:
    """Grava em `destino` o que entra no benefício, e o que sobrou se pedirem."""
    progresso = ProgressoDoCredito(arquivos_totais=contar_xml(xmls))
    return varrer_conteudos(conteudos_de_xml(xmls, recusados=progresso.recusados), destino,
                            filtro, raiz_do_cnpj=raiz_do_cnpj,
                            incluir_descartados=incluir_descartados,
                            avisar=avisar, deve_parar=deve_parar, progresso=progresso)


def varrer_conteudos(fontes: Iterable[tuple[str, bytes | None]], destino: str, filtro: Filtro, *,
                     raiz_do_cnpj: str = "",
                     incluir_descartados: bool = False,
                     avisar: Aviso | None = None,
                     deve_parar: Callable[[], bool] | None = None,
                     progresso: ProgressoDoCredito | None = None) -> ProgressoDoCredito:
    """O mesmo, a partir de (nome, conteúdo). Conteúdo None: lê do disco pelo nome."""
    os.makedirs(destino, exist_ok=True)
    progresso = progresso or ProgressoDoCredito()
    caminho_elegiveis = os.path.join(destino, ARQUIVO_ELEGIVEIS)
    caminho_descartados = os.path.join(destino, ARQUIVO_DESCARTADOS)
    elegiveis = _Escritor(caminho_elegiveis, ESQUEMA)
    descartados = _Escritor(caminho_descartados, ESQUEMA) if incluir_descartados else None
    vistas: dict[str, int] = {}
    negadas: set[str] = set()
    try:
        for nome, conteudo in fontes:
            parar_se_pedirem(deve_parar)
            _ler_um(nome, conteudo, filtro, elegiveis, descartados, vistas, negadas,
                    progresso, raiz_do_cnpj)
            progresso.arquivos_lidos += 1
            if avisar is not None:
                avisar(progresso)
    finally:
        elegiveis.fechar()
        if descartados is not None:
            descartados.fechar()
    if negadas & vistas.keys():
        # a nota veio primeiro sem protocolo e depois denegada: as linhas da
        # primeira cópia já estão gravadas, e saem agora
        _sem_as_denegadas(caminho_elegiveis, negadas, progresso)
        if descartados is not None:
            _sem_as_denegadas(caminho_descartados, negadas)
    log.info("crédito outorgado varrido", extra={
        "arquivos": progresso.arquivos_lidos, "documentos": progresso.documentos,
        "itens": progresso.itens, "elegiveis": progresso.elegiveis,
        "centavos_elegiveis": progresso.centavos_elegiveis,
        "descartados": progresso.descartados, "repetidos": progresso.repetidos,
        "nao_autorizados": progresso.nao_autorizados,
        "nao_sao_documento": progresso.nao_sao_documento,
        "nao_sao_saida": progresso.nao_sao_saida, "ilegiveis": progresso.ilegiveis,
        "ncms": len(filtro.ncms), "termos": len(filtro.termos), "sem_filtro": filtro.sem_filtro})
    return progresso


def _sem_as_denegadas(caminho: str, negadas: set[str],
                      progresso: ProgressoDoCredito | None = None) -> None:
    """Regrava o parquet sem as chaves que outra cópia mostrou denegadas."""
    provisorio = caminho + ".denegadas"
    os.replace(caminho, provisorio)
    con = duckdb.connect()
    try:
        con.register("negadas", pa.table({"chave": pa.array(sorted(negadas), pa.string())}))
        con.execute(f"""
            COPY (
                SELECT x.* FROM read_parquet('{_escapar(provisorio)}') x
                ANTI JOIN negadas n ON n.chave = x.chave
            ) TO '{_escapar(caminho)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        if progresso is not None:
            linhas, centavos = con.execute(
                f"""SELECT count(*), coalesce(sum(valor), 0) * 100
                    FROM read_parquet('{_escapar(caminho)}')""").fetchone()
            progresso.elegiveis = int(linhas)
            progresso.centavos_elegiveis = int(centavos)
    finally:
        con.close()
    os.remove(provisorio)


def _ler_um(caminho: str, conteudo: bytes | None, filtro: Filtro, elegiveis: _Escritor,
            descartados: _Escritor | None, vistas: dict[str, int], negadas: set[str],
            progresso: ProgressoDoCredito, raiz_do_cnpj: str = "") -> None:
    nome = os.path.basename(caminho)
    try:
        if conteudo is None:
            with open(caminho, "rb") as f:
                conteudo = f.read()
        progresso.bytes_lidos += len(conteudo)
        doc = ler_documento_xml(conteudo)
    except (OSError, XmlIlegivel) as erro:
        _ilegivel(nome, erro, progresso)
        return
    if doc is None:
        # evento, CT-e, inutilização: não é documento de mercadoria, e não é erro
        progresso.nao_sao_documento += 1
        return
    if doc.autorizado is False:
        progresso.nao_autorizados += 1
        negadas.add(doc.chave)
        log.warning("XML com protocolo que não autoriza a nota", extra={
            "arquivo": nome, "chave": doc.chave, "cstat": doc.cstat})
        return
    # o benefício é sobre o que a empresa **vendeu**: a nota de compra que veio
    # na mesma pasta não entra. `tpNF` sozinho não responde isso — ver
    # `DocumentoXml.saida_de`
    if raiz_do_cnpj and doc.saida_de(raiz_do_cnpj) is not True:
        progresso.nao_sao_saida += 1
        return
    prioridade = _PRIORIDADE_AUTORIZADA if doc.autorizado else _PRIORIDADE_SEM_PROTOCOLO
    anterior = vistas.get(doc.chave)
    if anterior is not None:
        progresso.repetidos += 1
        # a cópia melhor que chega depois não é regravada: entre duas cópias da
        # mesma chave muda o protocolo, não o item — e é o item que se julga
        return
    vistas[doc.chave] = prioridade
    progresso.documentos += 1
    for item in doc.itens:
        _julgar(doc, nome, item, filtro, elegiveis, descartados, progresso)


def _julgar(doc: DocumentoXml, arquivo: str, item: ItemDoXml, filtro: Filtro,
            elegiveis: _Escritor, descartados: _Escritor | None,
            progresso: ProgressoDoCredito) -> None:
    veredito = filtro.avaliar(item.descricao, item.ncm)
    progresso.itens += 1
    if not veredito.elegivel:
        progresso.descartados += 1
        if descartados is not None:
            descartados.acrescentar(_linha(doc, arquivo, item, veredito.elegivel, veredito.motivo))
        return
    progresso.elegiveis += 1
    progresso.centavos_elegiveis += int(_q(item.valor, _Q2) * _CEM)
    elegiveis.acrescentar(_linha(doc, arquivo, item, veredito.elegivel, veredito.motivo))


def _linha(doc: DocumentoXml, arquivo: str, item: ItemDoXml,
           elegivel: bool, motivo: str) -> dict:
    return {
        "arquivo": arquivo, "chave": doc.chave, "modelo": doc.modelo, "tipo": doc.tipo,
        "numero_documento": doc.numero, "serie": doc.serie, "emissao": doc.emissao,
        "emitente": doc.emitente, "emitente_nome": doc.emitente_nome,
        "destinatario": doc.destinatario, "destinatario_nome": doc.destinatario_nome,
        "numero_item": item.numero, "codigo": item.codigo, "descricao": item.descricao,
        "ncm": item.ncm, "cest": item.cest, "cfop": item.cfop, "unidade": item.unidade,
        "quantidade": _q(item.quantidade, _Q5),
        "valor_unitario": _q(item.valor_unitario, _Q10),
        "valor": _q(item.valor, _Q2),
        "cst_icms": item.cst_icms, "bc_icms": _q(item.bc_icms, _Q2),
        "aliq_icms": _q(item.aliq_icms, _Q4), "valor_icms": _q(item.valor_icms, _Q2),
        "cst_pis": item.cst_pis, "bc_pis": _q(item.bc_pis, _Q2),
        "aliq_pis": _q(item.aliq_pis, _Q4), "valor_pis": _q(item.valor_pis, _Q2),
        "cst_cofins": item.cst_cofins, "bc_cofins": _q(item.bc_cofins, _Q2),
        "aliq_cofins": _q(item.aliq_cofins, _Q4), "valor_cofins": _q(item.valor_cofins, _Q2),
        "elegivel": elegivel, "motivo": motivo,
    }


def _ilegivel(nome: str, erro: Exception, progresso: ProgressoDoCredito) -> None:
    progresso.ilegiveis += 1
    if len(progresso.exemplos_ilegiveis) < 20:
        progresso.exemplos_ilegiveis.append(f"{nome}: {erro}")
    log.warning("XML ilegível na varredura do crédito outorgado",
                extra={"arquivo": nome, "motivo": str(erro)})


# ---------------------------------------------------------------------------
# ler na tela
# ---------------------------------------------------------------------------
POR_PAGINA_PADRAO = 100
POR_PAGINA_MAXIMO = 500


class ListaNaoGerada(FileNotFoundError):
    """Pediram uma lista que esta execução não tem em disco."""


def _arquivo(destino: str, descartados: bool) -> str:
    nome = ARQUIVO_DESCARTADOS if descartados else ARQUIVO_ELEGIVEIS
    caminho = os.path.join(destino, nome)
    if not os.path.isfile(caminho):
        if descartados:
            raise ListaNaoGerada(
                "Esta rodada não guardou os itens descartados. Ligue \"guardar os "
                "descartados\" no filtro e rode de novo.")
        raise ListaNaoGerada(
            "A lista do crédito outorgado não está em disco nesta execução. Rode de novo.")
    return caminho


def _pagina(pagina: int, por_pagina: int) -> tuple[int, int]:
    return max(1, int(pagina)), max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))


def _recorte(caminho: str, busca: str | None) -> tuple[str, list[object]]:
    """A fonte da consulta, já com a busca aplicada. Busca vazia não filtra."""
    fonte = f"read_parquet('{_escapar(caminho)}')"
    termo = (busca or "").strip()
    if not termo:
        return fonte, []
    return (f"(SELECT * FROM {fonte} WHERE descricao ILIKE ? OR codigo ILIKE ? OR ncm ILIKE ?)",
            [f"%{termo}%"] * 3)


def produtos(destino: str, descartados: bool = False, busca: str | None = None,
             pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Os **produtos** da lista, e não as linhas: é assim que se revisa o filtro.

    Ninguém confere um benefício lendo três milhões de linhas de venda. O que se
    lê é a lista de produtos distintos que o filtro capturou — e aí salta aos
    olhos o que não devia estar ali ("PÃO DE VELA") e o que ficou de fora.

    Agrupa por código, descrição e NCM, porque os três juntos são o produto: o
    mesmo código com duas descrições costuma ser recadastro no ERP, e ver os
    dois lados é justamente o ponto.
    """
    pagina, por_pagina = _pagina(pagina, por_pagina)
    caminho = _arquivo(destino, descartados)
    fonte, parametros = _recorte(caminho, busca)
    agrupado = f"""
        SELECT codigo, descricao, ncm,
               min(motivo) AS motivo,
               count(*) AS itens,
               sum(quantidade) AS quantidade,
               sum(valor) AS valor
        FROM {fonte}
        GROUP BY codigo, descricao, ncm
    """
    con = _leitura(destino)
    try:
        total, linhas_totais, valor_total = con.execute(
            f"SELECT count(*), coalesce(sum(itens), 0), coalesce(sum(valor), 0) FROM ({agrupado})",
            parametros).fetchone()
        cursor = con.execute(
            f"{agrupado} ORDER BY valor DESC, descricao "
            f"LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}", parametros)
        nomes = [c[0] for c in cursor.description]
        produtos_ = [dict(zip(nomes, r)) for r in cursor.fetchall()]
    finally:
        con.close()
    log.info("produtos do crédito outorgado lidos", extra={
        "execucao_pasta": os.path.basename(destino), "descartados": descartados,
        "total": total, "pagina": pagina, "buscou": bool((busca or "").strip())})
    return {
        "pagina": pagina, "por_pagina": por_pagina, "total": int(total),
        "linhas": [_texto_no_produto(p) for p in produtos_],
        "itens": int(linhas_totais or 0),
        "valor": _dinheiro(valor_total),
        "descartados": descartados,
        "buscou": bool((busca or "").strip()),
    }


def itens(destino: str, descartados: bool = False, busca: str | None = None,
          codigo: str | None = None, pagina: int = 1,
          por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """As linhas, para quem já achou o produto e quer ver as notas dele."""
    pagina, por_pagina = _pagina(pagina, por_pagina)
    caminho = _arquivo(destino, descartados)
    fonte, parametros = _recorte(caminho, busca)
    if codigo:
        fonte = f"(SELECT * FROM {fonte} WHERE codigo = ?)"
        parametros = [*parametros, codigo]
    con = _leitura(destino)
    try:
        total, valor_total = con.execute(
            f"SELECT count(*), coalesce(sum(valor), 0) FROM {fonte}", parametros).fetchone()
        cursor = con.execute(
            f"SELECT * FROM {fonte} ORDER BY emissao, chave, numero_item "
            f"LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}", parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [dict(zip(nomes, r)) for r in cursor.fetchall()]
    finally:
        con.close()
    log.info("itens do crédito outorgado lidos", extra={
        "execucao_pasta": os.path.basename(destino), "descartados": descartados,
        "total": total, "pagina": pagina, "codigo": codigo or ""})
    return {
        "pagina": pagina, "por_pagina": por_pagina, "total": int(total),
        "linhas": [_texto_no_item(linha) for linha in linhas],
        "valor": _dinheiro(valor_total),
        "descartados": descartados,
        "buscou": bool((busca or "").strip()),
    }


def _dinheiro(valor) -> str:
    """Decimal vira texto com duas casas: é o que atravessa o JSON sem arredondar."""
    return format(Decimal(valor or 0).quantize(_Q2), "f")


def _texto_no_produto(produto: dict) -> dict:
    return {**produto,
            "itens": int(produto["itens"]),
            "quantidade": format(Decimal(produto["quantidade"] or 0).quantize(_Q5), "f"),
            "valor": _dinheiro(produto["valor"])}


def _texto_no_item(linha: dict) -> dict:
    """O que é Decimal vira texto; a data vira ISO. O resto já é string."""
    saida = dict(linha)
    for campo in ("quantidade", "valor_unitario", "valor", "bc_icms", "aliq_icms", "valor_icms",
                  "bc_pis", "aliq_pis", "valor_pis", "bc_cofins", "aliq_cofins", "valor_cofins"):
        if saida.get(campo) is not None:
            saida[campo] = format(Decimal(saida[campo]), "f")
    if saida.get("emissao") is not None:
        saida["emissao"] = saida["emissao"].isoformat()
    return saida


def serializar(progresso: ProgressoDoCredito, filtro: Filtro) -> dict:
    """O que fica gravado na execução: o resultado **e o filtro que o produziu**.

    O filtro vai junto de propósito. Ele muda com o tempo — o analista acrescenta
    um termo, tira outro —, e sem o retrato de quando a rodada correu não há como
    responder, meses depois, por que aquela lista tinha aquelas linhas.
    """
    return {
        "versao": 1,
        "arquivos": progresso.arquivos_lidos,
        "bytes": progresso.bytes_lidos,
        "documentos": progresso.documentos,
        "itens": progresso.itens,
        "elegiveis": progresso.elegiveis,
        "descartados": progresso.descartados,
        "centavos_elegiveis": progresso.centavos_elegiveis,
        "repetidos": progresso.repetidos,
        "nao_autorizados": progresso.nao_autorizados,
        "nao_sao_documento": progresso.nao_sao_documento,
        "nao_sao_saida": progresso.nao_sao_saida,
        "ilegiveis": progresso.ilegiveis,
        "exemplos_ilegiveis": progresso.exemplos_ilegiveis[:20],
        "recusados": progresso.recusados[:20],
        "filtro": {
            "ncms": list(filtro.ncms),
            "termos": list(filtro.termos),
            "sem_filtro": filtro.sem_filtro,
        },
    }


__all__ = [
    "ARQUIVO_DESCARTADOS",
    "ARQUIVO_ELEGIVEIS",
    "ESQUEMA",
    "POR_PAGINA_PADRAO",
    "LeituraCancelada",
    "ListaNaoGerada",
    "ProgressoDoCredito",
    "itens",
    "produtos",
    "serializar",
    "varrer",
    "varrer_conteudos",
]
