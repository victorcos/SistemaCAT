"""Extrair para parquet o item de cada XML do trabalho.

É a outra metade da etapa 3. A EFD dá o item de entrada (C170) e quase nada de
saída; o XML dá o item de qualquer documento que o cliente entregou. Sai daqui
``itens_do_xml.parquet``, uma linha por item, e a consolidação decide o que
fazer com ele (`movimentacao.py`): completar o documento que a EFD escriturou
sem item, e pôr os valores do XML ao lado do C170 que já existe — o XML vence.

Um documento por chave. O mesmo XML aparece mais de uma vez quando o cliente
manda a pasta do mês e a do trimestre — na empresa 04, 28.407 chaves em mais de
um arquivo. Vale a cópia com protocolo de autorização sobre a que não tem
protocolo (o XML do ERP antes de transmitir); entre iguais, a primeira lida, na
ordem do caminho. As outras são contadas. Nota com protocolo que não autoriza
(uso denegado, cStat 301/302/303) sai inteira, mesmo que outra cópia não tenha
protocolo, e é contada à parte.

Como o parquet é gravado em fluxo, a cópia melhor que chega depois é gravada
também, com um número de `leitura` maior; se isso aconteceu, ou se houve nota
denegada, uma passada no fim deixa uma cópia por chave.

O que não é documento (evento de cancelamento, carta de correção, inutilização)
e o que não abre ficam contados e no log, sem derrubar a leitura dos outros
milhares.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import duckdb
import pyarrow as pa

from cat.dominio.notafiscal.xml import DocumentoXml, XmlIlegivel, ler_documento_xml
from cat.infraestrutura.analitico.canceladas import chaves_de_evento
from cat.infraestrutura.analitico.confronto import _escapar
from cat.infraestrutura.analitico.extracao import Aviso, Progresso, _Escritor
from cat.infraestrutura.arquivos.xml_compactado import contar_xml, conteudos_de_xml
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ITENS_DO_XML = "itens_do_xml.parquet"

# quantos CNPJ de fora o resumo guarda. A lista existe para a pessoa
# reconhecer de quem é o que veio junto na pasta — uma pasta de rede
# compartilhada devolve o grupo inteiro, e vinte já dizem o que houve.
CNPJS_DE_FORA_GUARDADOS = 20

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_Q5 = Decimal("0.00001")

ESQUEMA_ITENS_DO_XML = pa.schema([
    ("chave", pa.string()),
    ("modelo", pa.string()),
    ("tipo", pa.string()),                  # tpNF: 0 entrada, 1 saída, de quem emitiu
    ("emitente", pa.string()),
    ("emitente_nome", pa.string()),
    ("destinatario", pa.string()),
    ("destinatario_nome", pa.string()),
    ("numero_documento", pa.string()),
    ("serie", pa.string()),
    ("emissao", pa.date32()),
    # indFinal da NF-e; NFC-e e CF-e são de consumidor final
    ("consumidor_final", pa.bool_()),
    # cStat do protocolo: 100 ou 150; vazio no XML sem protocolo e no CF-e
    ("protocolo", pa.string()),
    ("arquivo", pa.string()),
    ("numero_item", pa.int32()),
    ("codigo", pa.string()),
    ("gtin", pa.string()),
    ("descricao", pa.string()),
    ("ncm", pa.string()),
    ("cest", pa.string()),
    ("cfop", pa.string()),
    ("unidade", pa.string()),
    ("quantidade", pa.decimal128(20, 5)),
    ("valor", pa.decimal128(18, 2)),
    ("desconto", pa.decimal128(18, 2)),
    ("frete", pa.decimal128(18, 2)),
    ("seguro", pa.decimal128(18, 2)),
    ("outras", pa.decimal128(18, 2)),
    # a base do ICMS da operação: vBC, senão vBCEfet, senão a soma do item com
    # frete e despesas menos o desconto. É a base do valor de confronto
    ("base_do_item", pa.decimal128(18, 2)),
    ("cst_icms", pa.string()),
    ("bc_icms", pa.decimal128(18, 2)),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("valor_icms", pa.decimal128(18, 2)),
    ("bc_st", pa.decimal128(18, 2)),
    ("aliq_st", pa.decimal128(9, 4)),
    ("valor_st", pa.decimal128(18, 2)),
    ("fcp_st", pa.decimal128(18, 2)),
    ("bc_st_retido", pa.decimal128(18, 2)),
    # o que o CST 60 informa do imposto que a ST encerrou (NT 2020.005)
    ("reducao_declarada", pa.decimal128(9, 4)),
    ("bc_efetiva", pa.decimal128(18, 2)),
    ("aliquota_efetiva", pa.decimal128(9, 4)),
    ("icms_efetivo", pa.decimal128(18, 2)),
    # o ICMS suportado antes, como a NF-e informa no CST 60: substituto + retido + FCP
    ("retido_informado", pa.decimal128(18, 2)),
    # PIS, COFINS, IPI e ISSQN do item. Não entram em apuração nenhuma do
    # sistema — entram na extração dos XML, onde quem confere escolhe as
    # colunas. O leitor já os lia; só não chegavam ao disco
    ("cst_pis", pa.string()),
    ("bc_pis", pa.decimal128(18, 2)),
    ("aliq_pis", pa.decimal128(9, 4)),
    ("valor_pis", pa.decimal128(18, 2)),
    ("cst_cofins", pa.string()),
    ("bc_cofins", pa.decimal128(18, 2)),
    ("aliq_cofins", pa.decimal128(9, 4)),
    ("valor_cofins", pa.decimal128(18, 2)),
    ("cst_ipi", pa.string()),
    ("bc_ipi", pa.decimal128(18, 2)),
    ("aliq_ipi", pa.decimal128(9, 4)),
    ("valor_ipi", pa.decimal128(18, 2)),
    ("issqn_deducao", pa.decimal128(18, 2)),
    ("issqn_desconto_incondicional", pa.decimal128(18, 2)),
    ("issqn_desconto_condicional", pa.decimal128(18, 2)),
    # a ordem do arquivo na leitura: entre cópias da mesma chave, fica a de número maior
    ("leitura", pa.int64()),
])

# autorizada vence sem protocolo; denegada não entra
_PRIORIDADE_AUTORIZADA = 2
_PRIORIDADE_SEM_PROTOCOLO = 1


@dataclass
class ProgressoDoXml(Progresso):
    """O `Progresso` de sempre mais o que a leitura dos XML conta."""

    itens: int = 0
    repetidos: int = 0
    nao_sao_documento: int = 0
    ilegiveis: int = 0
    sem_item: int = 0
    # com protocolo que não autoriza (uso denegado): fora, com todas as cópias
    nao_autorizados: int = 0
    # cópia autorizada que chegou depois de uma sem protocolo e ficou no lugar dela
    copias_trocadas: int = 0
    # nota que não é da empresa do trabalho, nem emitente nem destinatário. O
    # zip é o único lugar onde isto se decide aqui: o XML solto a importação já
    # separa, mas o zip entra fechado, com o que o portal tiver posto dentro
    de_outra_empresa: int = 0
    # raiz do CNPJ de fora -> quantas notas. Nada sai em silêncio
    cnpjs_de_fora: dict[str, int] = field(default_factory=dict)
    exemplos_ilegiveis: list[str] = field(default_factory=list)
    # (chave, arquivo) dos eventos de cancelamento achados no meio dos XML — o
    # zip do portal traz os eventos junto com as notas
    cancelamentos: list[tuple[str, str]] = field(default_factory=list)


def _q(valor: Decimal, casas: Decimal) -> Decimal:
    return valor.quantize(casas, rounding=ROUND_HALF_UP)


def extrair_itens_do_xml(xmls: list[str], destino: str, avisar: Aviso | None = None,
                         progresso: ProgressoDoXml | None = None,
                         cnpj_raiz: str | None = None) -> ProgressoDoXml:
    """Grava `itens_do_xml.parquet` em `destino` com o item de cada XML, solto ou em zip.

    `cnpj_raiz` é a raiz do CNPJ da empresa do trabalho. Com ela, a nota de
    outra empresa fica de fora e é contada; sem ela, tudo entra — é o que os
    testes e as leituras avulsas fazem.
    """
    progresso = progresso or ProgressoDoXml(arquivos_totais=contar_xml(xmls))
    return extrair_itens_de_conteudos(conteudos_de_xml(xmls, recusados=progresso.recusados),
                                      destino, avisar, progresso, cnpj_raiz)


def extrair_itens_de_conteudos(fontes: Iterable[tuple[str, bytes | None]], destino: str,
                               avisar: Aviso | None = None,
                               progresso: ProgressoDoXml | None = None,
                               cnpj_raiz: str | None = None) -> ProgressoDoXml:
    """O mesmo, a partir de (nome, conteúdo). Conteúdo None: lê do disco pelo nome.

    É por aqui que um XML de dentro de zip entra sem ser extraído para o disco.
    """
    os.makedirs(destino, exist_ok=True)
    progresso = progresso or ProgressoDoXml()
    caminho = os.path.join(destino, ARQUIVO_ITENS_DO_XML)
    escritor = _Escritor(caminho, ESQUEMA_ITENS_DO_XML)
    # chave -> prioridade da cópia gravada
    vistas: dict[str, int] = {}
    negadas: set[str] = set()
    try:
        for nome, conteudo in fontes:
            _ler_um(nome, conteudo, escritor, vistas, negadas, progresso, cnpj_raiz)
            progresso.arquivos_lidos += 1
            if avisar is not None:
                avisar(progresso)
    finally:
        escritor.fechar()
    if progresso.copias_trocadas or negadas & vistas.keys():
        _uma_copia_por_chave(caminho, negadas, progresso)
    log.info("itens dos XML extraídos", extra={
        "arquivos": progresso.arquivos_lidos, "documentos": progresso.documentos,
        "itens": progresso.itens, "repetidos": progresso.repetidos,
        "copias_trocadas": progresso.copias_trocadas, "nao_autorizados": progresso.nao_autorizados,
        "nao_sao_documento": progresso.nao_sao_documento, "ilegiveis": progresso.ilegiveis,
        "sem_item": progresso.sem_item, "de_outra_empresa": progresso.de_outra_empresa,
        "cnpjs_de_fora": progresso.cnpjs_de_fora})
    return progresso


def _uma_copia_por_chave(caminho: str, negadas: set[str], progresso: ProgressoDoXml) -> None:
    """Regrava o parquet com a última cópia gravada de cada chave, sem as denegadas."""
    provisorio = caminho + ".copias"
    os.replace(caminho, provisorio)
    con = duckdb.connect()
    try:
        con.register("negadas", pa.table({"chave": pa.array(sorted(negadas), pa.string())}))
        con.execute(f"""
            COPY (
                SELECT x.* FROM read_parquet('{_escapar(provisorio)}') x
                ANTI JOIN negadas n ON n.chave = x.chave
                QUALIFY x.leitura = max(x.leitura) OVER (PARTITION BY x.chave)
                ORDER BY x.leitura, x.numero_item
            ) TO '{_escapar(caminho)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        progresso.documentos, progresso.itens = con.execute(
            f"SELECT count(DISTINCT chave), count(*) FROM read_parquet('{_escapar(caminho)}')").fetchone()
    finally:
        con.close()
    os.remove(provisorio)


def e_de_outra_empresa(doc: DocumentoXml, cnpj_raiz: str) -> bool:
    """A nota não tem a empresa do trabalho em ponta nenhuma.

    É a regra da importação (`inspecionar_lote._e_de_outra_empresa`), aplicada
    agora nota a nota: a empresa pode ser o emitente (nota que ela emitiu) ou o
    destinatário (nota que ela recebeu do fornecedor). Comparar só o emitente
    jogaria fora toda a compra.

    **Nota sem ponta legível fica.** Recusar o que não se sabe de quem é
    perderia nota boa — e o que não tem CNPJ nenhum não contamina apuração de
    outro cliente, que é o risco que esta regra existe para evitar.
    """
    pontas = [c for c in (doc.emitente, doc.destinatario) if c]
    return bool(pontas) and all(c[:8] != cnpj_raiz for c in pontas)


def _anotar_de_fora(doc: DocumentoXml, progresso: ProgressoDoXml) -> None:
    """Conta a nota de fora e guarda de quem ela é, sem guardar a nota."""
    progresso.de_outra_empresa += 1
    quem = (doc.emitente or doc.destinatario or "")[:8]
    if quem in progresso.cnpjs_de_fora or len(progresso.cnpjs_de_fora) < CNPJS_DE_FORA_GUARDADOS:
        progresso.cnpjs_de_fora[quem] = progresso.cnpjs_de_fora.get(quem, 0) + 1


def _ler_um(caminho: str, conteudo: bytes | None, escritor: _Escritor, vistas: dict[str, int],
            negadas: set[str], progresso: ProgressoDoXml,
            cnpj_raiz: str | None = None) -> None:
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
        progresso.nao_sao_documento += 1
        progresso.cancelamentos += [(chave, nome) for chave in chaves_de_evento(conteudo)]
        return
    if len(doc.chave) != 44 or not doc.chave.isdigit():
        _ilegivel(nome, ValueError(f"chave de acesso inválida: {doc.chave!r}"), progresso)
        return
    # antes de qualquer outra coisa: nota de outra empresa não é cópia, não é
    # denegada, não é nada deste trabalho — é dado de outro cliente
    if cnpj_raiz and e_de_outra_empresa(doc, cnpj_raiz):
        _anotar_de_fora(doc, progresso)
        return
    if doc.autorizado is False:
        progresso.nao_autorizados += 1
        negadas.add(doc.chave)
        log.warning("XML com protocolo que não autoriza a nota", extra={
            "arquivo": nome, "chave": doc.chave, "cstat": doc.cstat})
        return
    prioridade = _PRIORIDADE_AUTORIZADA if doc.autorizado else _PRIORIDADE_SEM_PROTOCOLO
    anterior = vistas.get(doc.chave)
    if anterior is not None:
        progresso.repetidos += 1
        if prioridade <= anterior:
            return
    try:
        linhas = [_linha(doc, nome, item, progresso.arquivos_lidos) for item in doc.itens]
    except (ArithmeticError, ValueError) as erro:
        # valor que não cabe no esquema: o arquivo inteiro fica de fora, avisado
        _ilegivel(nome, erro, progresso)
        return
    vistas[doc.chave] = prioridade
    if anterior is None:
        progresso.documentos += 1
        if not linhas:
            progresso.sem_item += 1
    else:
        progresso.copias_trocadas += 1
        log.info("cópia autorizada no lugar da sem protocolo", extra={"arquivo": nome, "chave": doc.chave})
    for linha in linhas:
        escritor.acrescentar(linha)
    progresso.itens += len(linhas)


def _linha(doc: DocumentoXml, arquivo: str, item, leitura: int) -> dict:
    return {
        "chave": doc.chave, "modelo": doc.modelo, "tipo": doc.tipo, "emitente": doc.emitente,
        "emitente_nome": doc.emitente_nome, "destinatario_nome": doc.destinatario_nome,
        "destinatario": doc.destinatario, "numero_documento": doc.numero, "serie": doc.serie,
        "emissao": doc.emissao, "consumidor_final": doc.consumidor_final, "protocolo": doc.cstat,
        "arquivo": arquivo, "leitura": leitura,
        "numero_item": item.numero, "codigo": item.codigo, "gtin": item.gtin,
        "descricao": item.descricao, "ncm": item.ncm, "cest": item.cest, "cfop": item.cfop,
        "unidade": item.unidade, "quantidade": _q(item.quantidade, _Q5),
        "valor": _q(item.valor, _Q2), "desconto": _q(item.desconto, _Q2),
        "cst_icms": item.cst_icms,
        "frete": _q(item.frete, _Q2), "seguro": _q(item.seguro, _Q2),
        "outras": _q(item.outras, _Q2), "base_do_item": _q(item.base_da_operacao, _Q2),
        "reducao_declarada": _q(item.reducao_declarada, _Q4),
        "bc_efetiva": _q(item.bc_efetiva, _Q2),
        "aliquota_efetiva": _q(item.aliquota_efetiva, _Q4),
        "icms_efetivo": _q(item.icms_efetivo, _Q2),
        "bc_icms": _q(item.bc_icms, _Q2), "aliq_icms": _q(item.aliq_icms, _Q4),
        "valor_icms": _q(item.valor_icms, _Q2),
        "bc_st": _q(item.bc_st, _Q2), "aliq_st": _q(item.aliq_st, _Q4),
        "valor_st": _q(item.valor_st, _Q2), "fcp_st": _q(item.fcp_st, _Q2),
        "bc_st_retido": _q(item.bc_st_retido, _Q2),
        "retido_informado": _q(item.retido_informado, _Q2) if item.retido_informado is not None else None,
        "cst_pis": item.cst_pis, "bc_pis": _q(item.bc_pis, _Q2),
        "aliq_pis": _q(item.aliq_pis, _Q4), "valor_pis": _q(item.valor_pis, _Q2),
        "cst_cofins": item.cst_cofins, "bc_cofins": _q(item.bc_cofins, _Q2),
        "aliq_cofins": _q(item.aliq_cofins, _Q4), "valor_cofins": _q(item.valor_cofins, _Q2),
        "cst_ipi": item.cst_ipi, "bc_ipi": _q(item.bc_ipi, _Q2),
        "aliq_ipi": _q(item.aliq_ipi, _Q4), "valor_ipi": _q(item.valor_ipi, _Q2),
        "issqn_deducao": _q(item.issqn_deducao, _Q2),
        "issqn_desconto_incondicional": _q(item.issqn_desconto_incondicional, _Q2),
        "issqn_desconto_condicional": _q(item.issqn_desconto_condicional, _Q2),
    }


def _ilegivel(nome: str, erro: Exception, progresso: ProgressoDoXml) -> None:
    progresso.ilegiveis += 1
    if len(progresso.exemplos_ilegiveis) < 20:
        progresso.exemplos_ilegiveis.append(f"{nome}: {erro}")
    log.warning("XML ilegível na extração de itens", extra={"arquivo": nome, "motivo": str(erro)})
