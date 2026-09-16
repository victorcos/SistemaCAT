"""Gera o arquivo digital de cada estabelecimento de SP e mês, e pré-valida.

A escrita é do domínio (`cat.dominio.cat42.arquivo_digital`) e a pré-validação
também (`pre_validacao`). Aqui é a parte suja: juntar o que cada etapa deixou e
decidir, arquivo a arquivo, se ele vai para o envio ou sai como prévia.

## De onde vem cada registro

| Registro | Fonte |
|---|---|
| 0000 | o 0000 da EFD do estabelecimento no mês: nome, IE, município |
| 0150 | o 0150 da mesma EFD, só os participantes citados, mais o próprio estabelecimento |
| 0200 | o cadastro de itens da etapa 3 (`itens.parquet`, a última ocorrência de cada código) |
| 1050 | os saldos da etapa 6 (`saldos.parquet`), campo a campo |
| 1100 | a linha da Ficha 3 (etapa 5) com chave de 44 dígitos e nº do item |
| 1200 | a linha da Ficha 3 com modelo não eletrônico, número e nº do item |

## Envio ou prévia

Vai para `envio/` só o arquivo de competência **apta** na etapa 6, sem trava
de escrita (linha sem documento, devolução sem a venda, confronto pendente…) e
que a pré-validação, lendo o arquivo de volta do disco, não acusou erro. Todo o
resto das competências de SP sai em `previas/`, com PREVIA no nome — decisão do
Victor, 16/09/2026. Fora de SP não se gera nada: a CAT 42 é paulista.

## Uma passagem pelas linhas, com memória constante

Um arquivo real tem 875 mil linhas de 1100. Segurar os registros em memória
para escrever 0150 e 0200 antes deles não cabe: as linhas vão para um rascunho
enquanto se descobre quais participantes e itens elas citam, e o arquivo final
é o cabeçalho seguido do rascunho.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.apuracao import MotivoDeBloqueio
from cat.dominio.cat42.arquivo_digital import (
    FIM_DE_LINHA,
    MODELOS_ELETRONICOS,
    MODELOS_SEM_PARTICIPANTE,
    Abertura,
    DocumentoEletronico,
    DocumentoNaoEletronico,
    IndicadorDeOperacao,
    Item,
    Participante,
    Saldo,
    TravaDoArquivo,
    ValorInvalido,
    cod_legal_da_devolucao_de_venda,
    linha as juntar,
    nome_do_arquivo,
    so_digitos,
)
from cat.dominio.cat42.enquadramento import VendaAConsumidor
from cat.dominio.cat42.pre_validacao import Regra, Validacao, validar
from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.dominio.sped.participante import ParticipanteDaEfd, ler_participante
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO, ARQUIVO_SALDOS
from cat.infraestrutura.analitico.confronto import _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS
from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada, _leitura
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ARQUIVOS = "arquivos_digitais.parquet"
ARQUIVO_OCORRENCIAS = "pre_validacao.parquet"
PASTA_ENVIO = "envio"
PASTA_PREVIAS = "previas"
ENVIO = "envio"
PREVIA = "previa"

LINHAS_POR_LOTE = 100_000
POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200
_Q2 = Decimal("0.01")

ESQUEMA_ARQUIVOS = pa.schema([
    ("cnpj", pa.string()),
    ("competencia", pa.string()),              # "2021-05"
    ("nome", pa.string()),
    ("destino", pa.string()),                  # envio | previa
    ("apta", pa.bool_()),                      # na etapa 6
    ("motivos", pa.string()),                  # da etapa 6, códigos por vírgula
    ("travas", pa.string()),                   # desta etapa, códigos por vírgula
    ("ressarcimento", pa.decimal128(24, 2)),
    ("complemento", pa.decimal128(24, 2)),
    ("linhas", pa.int64()),
    ("bytes", pa.int64()),
    ("sha256", pa.string()),
    ("participantes", pa.int32()),
    ("itens", pa.int32()),
    ("saldos", pa.int32()),
    ("eletronicos", pa.int64()),
    ("nao_eletronicos", pa.int64()),
    ("linhas_sem_documento", pa.int64()),
    ("saidas_indefinidas", pa.int64()),
    ("devolucoes_sem_venda", pa.int64()),
    ("confronto_pendente", pa.int64()),
    ("saldos_negativos", pa.int32()),
    ("itens_sem_cadastro", pa.int32()),
    ("participantes_sem_cadastro", pa.int32()),
    ("erros", pa.int64()),
    ("avisos", pa.int64()),
    ("itens_recompostos", pa.int32()),
    ("itens_que_fecham", pa.int32()),
])

ESQUEMA_OCORRENCIAS = pa.schema([
    ("nome", pa.string()),
    ("cnpj", pa.string()),
    ("competencia", pa.string()),
    ("regra", pa.string()),
    ("severidade", pa.string()),
    ("rotulo", pa.string()),
    ("o_que_fazer", pa.string()),
    ("vezes_no_arquivo", pa.int64()),          # quantas houve; os exemplos são os primeiros
    ("linha", pa.int64()),
    ("registro", pa.string()),
    ("campo", pa.string()),
    ("item", pa.string()),
    ("mensagem", pa.string()),
])

DeveParar = Callable[[], bool]


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A geração do arquivo digital foi cancelada por quem a pediu.")


@dataclass
class Fontes:
    apuracao: str                 # pasta da etapa 6
    razao: str                    # pasta da etapa 5
    movimentacao: str             # pasta da etapa 3
    # (caminho, cnpj, competência) das EFD vigentes — a retificadora já venceu
    efds: list[tuple[str, str, date]] = field(default_factory=list)


@dataclass
class Andamento:
    arquivos: int = 0
    total: int = 0


@dataclass
class ResumoDoArquivoDigital:
    venda_a_consumidor: str = VendaAConsumidor.ENQUADRAMENTO_1.value
    competencias: int = 0
    competencias_fora_de_sp: int = 0
    arquivos: int = 0
    para_envio: int = 0
    previas: int = 0
    linhas: int = 0
    bytes: int = 0
    por_registro: dict = field(default_factory=dict)
    linhas_sem_documento: int = 0
    erros: int = 0
    avisos: int = 0
    itens_recompostos: int = 0
    itens_que_fecham: int = 0
    ressarcimento_para_envio: Decimal = Decimal(0)
    complemento_para_envio: Decimal = Decimal(0)
    por_trava: dict = field(default_factory=dict)          # código -> arquivos
    por_regra: dict = field(default_factory=dict)          # código -> [arquivos, ocorrências]
    efds_lidas: int = 0
    efds_ilegiveis: int = 0


# ---------------------------------------------------------------------------
# o bloco 0 da EFD: 0000 e 0150
# ---------------------------------------------------------------------------
@dataclass
class CadastroDoMes:
    nome: str = ""
    ie: str = ""
    cod_mun: str = ""
    participantes: dict[str, ParticipanteDaEfd] = field(default_factory=dict)


def ler_cadastros(efds: list[tuple[str, str, date]], alvo: set[tuple[str, str]],
                  resumo: ResumoDoArquivoDigital, deve_parar: DeveParar | None = None
                  ) -> dict[tuple[str, str], CadastroDoMes]:
    """O 0000 e o 0150 de cada EFD que interessa, lendo só o bloco 0.

    O bloco 0 fica no começo do arquivo e termina no 0990: não há por que
    atravessar os GB do bloco C para achar o nome da loja.
    """
    cadastros: dict[tuple[str, str], CadastroDoMes] = {}
    for caminho, cnpj, competencia in efds:
        chave = (cnpj, competencia.strftime("%Y-%m"))
        if chave not in alvo:
            continue
        _conferir(deve_parar)
        cad = cadastros.setdefault(chave, CadastroDoMes())
        try:
            with open(caminho, "rb") as f:
                for bruto in f:
                    if bruto.startswith(b"|0000|"):
                        c = ler_cabecalho(bruto.decode("latin-1").rstrip("\r\n"))
                        cad.nome, cad.ie, cad.cod_mun = c.nome, c.inscricao_estadual, c.codigo_municipio
                    elif bruto.startswith(b"|0150|"):
                        p = ler_participante(bruto.decode("latin-1").rstrip("\r\n").split("|"))
                        if p is not None and p.codigo:
                            cad.participantes[p.codigo] = p
                    elif bruto.startswith(b"|0990|") or bruto[:2] in (b"|B", b"|C", b"|D", b"|E", b"|H"):
                        break
            resumo.efds_lidas += 1
        except (OSError, ArquivoNaoReconhecido) as erro:
            resumo.efds_ilegiveis += 1
            log.warning("EFD ilegível para o cadastro do arquivo digital",
                        extra={"arquivo": caminho, "cnpj": cnpj, "motivo": str(erro)})
    return cadastros


# ---------------------------------------------------------------------------
# a geração
# ---------------------------------------------------------------------------
def gerar(
    fontes: Fontes,
    destino: str,
    venda_a_consumidor: VendaAConsumidor = VendaAConsumidor.ENQUADRAMENTO_1,
    avisar: Callable[[Andamento], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> ResumoDoArquivoDigital:
    apuracao = os.path.join(fontes.apuracao, ARQUIVO_APURACAO)
    saldos = os.path.join(fontes.apuracao, ARQUIVO_SALDOS)
    ficha3 = os.path.join(fontes.razao, ARQUIVO_FICHA3)
    itens = os.path.join(fontes.movimentacao, ARQUIVO_ITENS)
    for obrigatorio in (apuracao, saldos, ficha3):
        if not os.path.isfile(obrigatorio):
            raise FileNotFoundError(f"{os.path.basename(obrigatorio)} não está em {os.path.dirname(obrigatorio)}.")

    resumo = ResumoDoArquivoDigital(venda_a_consumidor=venda_a_consumidor.value)
    for pasta in (PASTA_ENVIO, PASTA_PREVIAS):
        os.makedirs(os.path.join(destino, pasta), exist_ok=True)
    caminho_arquivos = os.path.join(destino, ARQUIVO_ARQUIVOS)
    caminho_ocorrencias = os.path.join(destino, ARQUIVO_OCORRENCIAS)

    con = _abrir(destino)
    escritor = pq.ParquetWriter(caminho_arquivos, ESQUEMA_ARQUIVOS)
    escritor_oc = pq.ParquetWriter(caminho_ocorrencias, ESQUEMA_OCORRENCIAS)
    try:
        alvo = _preparar(con, apuracao, saldos, ficha3, itens, resumo)
        cadastros = ler_cadastros(fontes.efds, {(c, m) for c, m, *_ in alvo}, resumo, deve_parar)
        andamento = Andamento(total=len(alvo))
        for cnpj, competencia, apta, motivos, ressarc, compl in alvo:
            _conferir(deve_parar)
            linha_arquivo, ocorrencias = _um_arquivo(
                con, destino, cnpj, competencia, apta, motivos, ressarc, compl,
                cadastros.get((cnpj, competencia)), venda_a_consumidor, resumo)
            escritor.write_table(pa.Table.from_pylist([linha_arquivo], schema=ESQUEMA_ARQUIVOS))
            if ocorrencias:
                escritor_oc.write_table(pa.Table.from_pylist(ocorrencias, schema=ESQUEMA_OCORRENCIAS))
            andamento.arquivos += 1
            if avisar is not None:
                avisar(andamento)
    except ApuracaoCancelada:
        escritor.close()
        escritor_oc.close()
        con.close()
        for alvo_ in (caminho_arquivos, caminho_ocorrencias):
            if os.path.isfile(alvo_):
                os.remove(alvo_)
        for pasta in (PASTA_ENVIO, PASTA_PREVIAS):
            shutil.rmtree(os.path.join(destino, pasta), ignore_errors=True)
        raise
    finally:
        escritor.close()
        escritor_oc.close()
        con.close()
        _limpar(destino)

    log.info("arquivo digital gerado", extra={
        "arquivos": resumo.arquivos, "para_envio": resumo.para_envio, "previas": resumo.previas,
        "linhas": resumo.linhas, "linhas_sem_documento": resumo.linhas_sem_documento,
        "erros": resumo.erros, "avisos": resumo.avisos})
    return resumo


def _preparar(con, apuracao: str, saldos: str, ficha3: str, itens: str,
              resumo: ResumoDoArquivoDigital) -> list[tuple]:
    """Tabelas de trabalho só com as competências de SP, e a lista delas."""
    con.execute(f"""
        CREATE OR REPLACE TABLE alvo AS
        SELECT cnpj, competencia, apta, motivos, ressarcimento, complemento
        FROM read_parquet('{_escapar(apuracao)}') WHERE uf = 'SP'
    """)
    resumo.competencias_fora_de_sp = con.execute(
        f"SELECT count(*) FROM read_parquet('{_escapar(apuracao)}') WHERE coalesce(uf, '') <> 'SP'").fetchone()[0]
    con.execute(f"""
        CREATE OR REPLACE TABLE saldos AS
        SELECT s.* FROM read_parquet('{_escapar(saldos)}') s
        JOIN alvo a ON a.cnpj = s.cnpj AND a.competencia = s.competencia
    """)
    # ordenada por arquivo: cada consulta de um mês lê um trecho contíguo
    con.execute(f"""
        CREATE OR REPLACE TABLE linhas AS
        SELECT f.cnpj, strftime(f.data, '%Y-%m') AS competencia, f.codigo, f.numero, f.data, f.especie,
               f.devolucao, f.cfop, f.enquadramento, f.enquadramento_indefinido, f.quantidade,
               f.icms_suportado, f.icms_efetivo, f.chave, f.numero_item, f.modelo, f.participante,
               f.numero_documento
        FROM read_parquet('{_escapar(ficha3)}') f
        JOIN alvo a ON a.cnpj = f.cnpj AND a.competencia = strftime(f.data, '%Y-%m')
        ORDER BY f.cnpj, competencia, f.data, f.chave, f.numero_item, f.codigo, f.numero
    """)
    if os.path.isfile(itens):
        con.execute(f"""
            CREATE OR REPLACE TABLE cadastro AS
            SELECT cnpj, codigo, any_value(descricao) AS descricao, any_value(codigo_barras) AS codigo_barras,
                   any_value(unidade) AS unidade, any_value(ncm) AS ncm, any_value(aliq_icms) AS aliq_icms,
                   any_value(cest) AS cest
            FROM read_parquet('{_escapar(itens)}')
            WHERE cnpj IN (SELECT DISTINCT cnpj FROM alvo)
            GROUP BY cnpj, codigo
        """)
    else:
        con.execute("CREATE OR REPLACE TABLE cadastro (cnpj VARCHAR, codigo VARCHAR, descricao VARCHAR, "
                    "codigo_barras VARCHAR, unidade VARCHAR, ncm VARCHAR, aliq_icms DECIMAL(9, 4), cest VARCHAR)")
    alvo = con.execute("SELECT * FROM alvo ORDER BY cnpj, competencia").fetchall()
    resumo.competencias = len(alvo)
    return alvo


@dataclass
class _Contagem:
    eletronicos: int = 0
    nao_eletronicos: int = 0
    sem_documento: int = 0
    indefinidas: int = 0
    devolucoes_sem_venda: int = 0
    confronto_pendente: int = 0
    saldos_negativos: int = 0
    itens_sem_cadastro: int = 0
    participantes_sem_cadastro: int = 0


def _um_arquivo(con, destino: str, cnpj: str, competencia: str, apta: bool, motivos: str,
                ressarcimento, complemento, cadastro: CadastroDoMes | None,
                venda: VendaAConsumidor, resumo: ResumoDoArquivoDigital) -> tuple[dict, list[dict]]:
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    nome_final = nome_do_arquivo(cnpj, ano, mes)
    corpo = os.path.join(destino, f".{nome_final}.corpo")
    cabeca = os.path.join(destino, f".{nome_final}.cabeca")
    n = _Contagem()
    citados_itens: set[str] = set()
    citados_participantes: set[str] = set()
    linhas_escritas = 0

    # --- 1100 e 1200, num rascunho, descobrindo o que citam ---------------------
    with open(corpo, "wb") as saida_1100, open(corpo + "2", "wb") as saida_1200:
        cursor = con.execute("SELECT * FROM linhas WHERE cnpj = ? AND competencia = ?", [cnpj, competencia])
        nomes = [d[0] for d in cursor.description]
        while lote := cursor.fetchmany(LINHAS_POR_LOTE):
            for bruto in lote:
                l = dict(zip(nomes, bruto))
                escrito = _registro_da_linha(l, venda, n)
                if escrito is None:
                    continue
                registro, texto = escrito
                if isinstance(registro, DocumentoEletronico):
                    saida_1100.write((texto + FIM_DE_LINHA).encode("latin-1"))
                    n.eletronicos += 1
                else:
                    saida_1200.write((texto + FIM_DE_LINHA).encode("latin-1"))
                    n.nao_eletronicos += 1
                citados_itens.add(registro.codigo)
                if (l["participante"] or "") and (l["modelo"] or "").upper() not in MODELOS_SEM_PARTICIPANTE:
                    citados_participantes.add(l["participante"])

    # --- 0000, 0150, 0200, 1050 ------------------------------------------------
    cad = cadastro or CadastroDoMes()
    saldos = []
    for codigo, qi, vi, qf, vf in con.execute(
            "SELECT codigo, qtd_ini, icms_tot_ini, qtd_fim, icms_tot_fim FROM saldos "
            "WHERE cnpj = ? AND competencia = ? ORDER BY codigo", [cnpj, competencia]).fetchall():
        if min(qi, vi, qf, vf) < 0:
            n.saldos_negativos += 1
            continue
        saldos.append(Saldo(codigo, qi, vi, qf, vf))
        citados_itens.add(codigo)

    participantes = _participantes(cnpj, cad, citados_participantes, n)
    itens = _itens(con, cnpj, citados_itens, n)
    abertura = Abertura(ano, mes, cad.nome, cnpj, cad.ie, cad.cod_mun)
    with open(cabeca, "wb") as saida:
        for registro in [abertura, *participantes, *itens, *saldos]:
            saida.write((juntar(registro.campos()) + FIM_DE_LINHA).encode("latin-1"))
            linhas_escritas += 1
        for parte in (corpo, corpo + "2"):
            with open(parte, "rb") as origem:
                shutil.copyfileobj(origem, saida, 1 << 20)
    os.remove(corpo)
    os.remove(corpo + "2")
    linhas_escritas += n.eletronicos + n.nao_eletronicos

    # --- pré-validação: o arquivo lido de volta do disco, como a SEFAZ o lê -----
    with open(cabeca, "rb") as f:
        v = validar(f)
    travas = _travas(apta, cad, n, v)
    pronto = not travas
    nome = nome_do_arquivo(cnpj, ano, mes, previa=not pronto)
    final = os.path.join(destino, PASTA_ENVIO if pronto else PASTA_PREVIAS, nome)
    os.replace(cabeca, final)
    tamanho, sha = _hash(final)

    _somar(resumo, pronto, linhas_escritas, tamanho, n, v, travas, abertura, saldos, ressarcimento, complemento)
    log.info("arquivo digital escrito", extra={
        "arquivo": nome, "cnpj": cnpj, "competencia": competencia, "destino": ENVIO if pronto else PREVIA,
        "linhas": linhas_escritas, "erros": v.erros, "avisos": v.avisos,
        "travas": [t.codigo for t in travas]})

    linha_arquivo = {
        "cnpj": cnpj, "competencia": competencia, "nome": nome, "destino": ENVIO if pronto else PREVIA,
        "apta": bool(apta), "motivos": motivos or "", "travas": ",".join(t.codigo for t in travas),
        "ressarcimento": Decimal(ressarcimento or 0).quantize(_Q2),
        "complemento": Decimal(complemento or 0).quantize(_Q2),
        "linhas": linhas_escritas, "bytes": tamanho, "sha256": sha,
        "participantes": len(participantes), "itens": len(itens), "saldos": len(saldos),
        "eletronicos": n.eletronicos, "nao_eletronicos": n.nao_eletronicos,
        "linhas_sem_documento": n.sem_documento, "saidas_indefinidas": n.indefinidas,
        "devolucoes_sem_venda": n.devolucoes_sem_venda, "confronto_pendente": n.confronto_pendente,
        "saldos_negativos": n.saldos_negativos, "itens_sem_cadastro": n.itens_sem_cadastro,
        "participantes_sem_cadastro": n.participantes_sem_cadastro,
        "erros": v.erros, "avisos": v.avisos,
        "itens_recompostos": v.itens_recompostos, "itens_que_fecham": v.itens_que_fecham,
    }
    ocorrencias = [{
        "nome": nome, "cnpj": cnpj, "competencia": competencia, "regra": o.regra.codigo,
        "severidade": o.regra.severidade.value, "rotulo": o.regra.rotulo, "o_que_fazer": o.regra.o_que_fazer,
        "vezes_no_arquivo": v.por_regra[o.regra], "linha": o.linha, "registro": o.registro, "campo": o.campo,
        "item": o.item, "mensagem": o.mensagem,
    } for o in v.exemplos]
    return linha_arquivo, ocorrencias


def _registro_da_linha(l: dict, venda: VendaAConsumidor, n: _Contagem) -> tuple | None:
    """A linha da Ficha 3 vira 1100, 1200 ou nada — e o nada é contado.

    Devolve o registro e a linha já escrita: é na escrita que o leiaute recusa
    (nº do item acima de 999, valor negativo), e a recusa também é contada.
    """
    entrada, devolucao = l["especie"] == "entrada", bool(l["devolucao"])
    # sentido físico: devolução de venda entra, devolução de compra sai
    ind = IndicadorDeOperacao.SAIDA if entrada == devolucao else IndicadorDeOperacao.ENTRADA
    quantidade = abs(Decimal(l["quantidade"] or 0))
    icms = abs(Decimal(l["icms_suportado"] or 0))
    icms_tot = icms if (entrada or devolucao) else None
    cod_legal = vl_confr = None

    if not entrada and not devolucao:                       # saída
        if l["enquadramento_indefinido"] or l["enquadramento"] is None:
            n.indefinidas += 1
        else:
            cod_legal = int(l["enquadramento"])
            if cod_legal > 0:
                vl_confr = l["icms_efetivo"]
                if vl_confr is None:
                    n.confronto_pendente += 1
    elif not entrada and devolucao:                         # devolução de venda
        cod_legal = cod_legal_da_devolucao_de_venda(l["cfop"] or "", venda is VendaAConsumidor.DEMAIS_SAIDAS)
        if cod_legal is None:
            n.devolucoes_sem_venda += 1
        elif cod_legal > 0:
            n.confronto_pendente += 1                        # o confronto é o da venda original

    chave = so_digitos(l["chave"])
    modelo = (l["modelo"] or "").strip().upper()
    item = l["numero_item"]
    base = dict(data=l["data"], num_item=int(item or 0), ind_oper=ind, codigo=l["codigo"], cfop=l["cfop"] or "",
                quantidade=quantidade, icms_tot=icms_tot, vl_confr=vl_confr, cod_legal=cod_legal)
    registro = None
    if len(chave) == 44 and item and (modelo in MODELOS_ELETRONICOS or chave[20:22] in MODELOS_ELETRONICOS):
        registro = DocumentoEletronico(**base, chave=chave)
    elif not chave and item and l["numero_documento"] and modelo and modelo not in MODELOS_ELETRONICOS:
        registro = DocumentoNaoEletronico(**base, modelo=modelo, numero_documento=l["numero_documento"],
                                          participante=l["participante"] or "")
    if registro is not None:
        try:
            return registro, juntar(registro.campos())
        except ValorInvalido as erro:
            log.warning("linha da Ficha 3 que o leiaute recusa", extra={
                "cnpj": l["cnpj"], "codigo": l["codigo"], "data": str(l["data"]), "motivo": str(erro)})
    n.sem_documento += 1
    return None


def _participantes(cnpj: str, cad: CadastroDoMes, citados: set[str], n: _Contagem) -> list[Participante]:
    """Os citados, pelo 0150 da EFD do mês, e o próprio estabelecimento."""
    saida: list[Participante] = []
    vistos: set[str] = set()
    proprio = next((p for p in cad.participantes.values() if so_digitos(p.cnpj) == cnpj), None)
    for codigo in sorted(citados | ({proprio.codigo} if proprio else set())):
        p = cad.participantes.get(codigo)
        if p is None:
            n.participantes_sem_cadastro += 1
            continue
        saida.append(Participante(p.codigo, p.nome, cnpj=p.cnpj, cpf=p.cpf, ie=p.ie, cod_mun=p.cod_mun,
                                  cod_pais=p.cod_pais or "1058"))
        vistos.add(p.codigo)
    if proprio is None and cad.nome:
        # sem o próprio no 0150 da EFD: entra pelo 0000, com o CNPJ como código
        saida.append(Participante(cnpj, cad.nome, cnpj=cnpj, ie=cad.ie, cod_mun=cad.cod_mun))
    return saida


def _itens(con, cnpj: str, citados: set[str], n: _Contagem) -> list[Item]:
    if not citados:
        return []
    # dez mil códigos num INSERT por linha levam segundos; como tabela, nada
    con.register("citados", pa.table({"codigo": sorted(citados)}))
    try:
        linhas = con.execute("""
            SELECT c.codigo, k.descricao, k.codigo_barras, k.unidade, k.ncm, k.aliq_icms, k.cest
            FROM citados c LEFT JOIN cadastro k ON k.cnpj = ? AND k.codigo = c.codigo
            ORDER BY c.codigo
        """, [cnpj]).fetchall()
    finally:
        con.unregister("citados")
    itens = []
    for codigo, descricao, barras, unidade, ncm, aliquota, cest in linhas:
        if unidade is None:
            n.itens_sem_cadastro += 1
            continue
        itens.append(Item(codigo, descricao or "", unidade, ncm or "", barras or "", aliquota, cest or ""))
    return itens


def _travas(apta: bool, cad: CadastroDoMes, n: _Contagem, v: Validacao) -> list[TravaDoArquivo]:
    travas = [
        (not apta, TravaDoArquivo.NAO_APTA),
        (n.sem_documento > 0, TravaDoArquivo.SEM_DOCUMENTO),
        (n.indefinidas > 0, TravaDoArquivo.SAIDA_INDEFINIDA),
        (n.devolucoes_sem_venda > 0, TravaDoArquivo.DEVOLUCAO_SEM_VENDA),
        (n.confronto_pendente > 0, TravaDoArquivo.CONFRONTO_PENDENTE),
        (n.saldos_negativos > 0, TravaDoArquivo.SALDO_NEGATIVO),
        (n.itens_sem_cadastro > 0, TravaDoArquivo.ITEM_SEM_CADASTRO),
        (n.participantes_sem_cadastro > 0, TravaDoArquivo.PARTICIPANTE_SEM_CADASTRO),
        (not cad.nome, TravaDoArquivo.SEM_ABERTURA),
        (v.erros > 0, TravaDoArquivo.PRE_VALIDACAO),
    ]
    return [t for condicao, t in travas if condicao]


def _somar(resumo: ResumoDoArquivoDigital, pronto: bool, linhas: int, tamanho: int, n: _Contagem,
           v: Validacao, travas: list[TravaDoArquivo], abertura: Abertura, saldos: list, ressarcimento,
           complemento) -> None:
    resumo.arquivos += 1
    resumo.linhas += linhas
    resumo.bytes += tamanho
    resumo.linhas_sem_documento += n.sem_documento
    resumo.erros += v.erros
    resumo.avisos += v.avisos
    resumo.itens_recompostos += v.itens_recompostos
    resumo.itens_que_fecham += v.itens_que_fecham
    for reg, quantos in v.por_registro.items():
        resumo.por_registro[reg] = resumo.por_registro.get(reg, 0) + quantos
    if pronto:
        resumo.para_envio += 1
        resumo.ressarcimento_para_envio += Decimal(ressarcimento or 0)
        resumo.complemento_para_envio += Decimal(complemento or 0)
    else:
        resumo.previas += 1
    for t in travas:
        resumo.por_trava[t.codigo] = resumo.por_trava.get(t.codigo, 0) + 1
    for regra, quantas in v.por_regra.items():
        arquivos, ocorrencias = resumo.por_regra.get(regra.codigo, (0, 0))
        resumo.por_regra[regra.codigo] = (arquivos + 1, ocorrencias + quantas)


def _hash(caminho: str) -> tuple[int, str]:
    h = hashlib.sha256()
    tamanho = 0
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
            tamanho += len(bloco)
    return tamanho, h.hexdigest()


# ---------------------------------------------------------------------------
# o que a tela lê e baixa depois de pronto
# ---------------------------------------------------------------------------
def arquivos(destino: str, so: str | None = None, busca: str | None = None,
             pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Os arquivos gerados: os de envio primeiro, depois as prévias por ressarcimento.

    `so` recorta: `envio`, `previa` ou o código de uma trava.
    """
    recortes = {ENVIO: "destino = 'envio'", PREVIA: "destino = 'previa'"}
    recortes.update({t.codigo: f"travas LIKE '%{t.codigo}%'" for t in TravaDoArquivo})
    if so and so not in recortes:
        raise ValueError(f"Recorte desconhecido: {so}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_ARQUIVOS)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_ARQUIVOS} não está em {destino}.")
    filtros, parametros = [], []
    if so:
        filtros.append(recortes[so])
    if busca and busca.strip():
        filtros.append("(cnpj ILIKE ? OR competencia ILIKE ? OR nome ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 3
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"
    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY destino, ressarcimento DESC, cnpj, competencia
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [_legivel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def ocorrencias(destino: str, nome: str, pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """As ocorrências da pré-validação de um arquivo, erros primeiro."""
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_OCORRENCIAS)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_OCORRENCIAS} não está em {destino}.")
    con = _leitura(destino)
    try:
        base = f"read_parquet('{_escapar(caminho)}') WHERE nome = ?"
        total = con.execute(f"SELECT count(*) FROM {base}", [nome]).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY severidade = 'aviso', regra, linha
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, [nome])
        nomes = [c[0] for c in cursor.description]
        linhas = [dict(zip(nomes, r)) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def _legivel(linha: dict) -> dict:
    saida = {k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in linha.items()}
    saida["motivos"] = [
        {"codigo": c, "rotulo": MotivoDeBloqueio(c).rotulo, "o_que_fazer": MotivoDeBloqueio(c).o_que_fazer}
        for c in (linha.get("motivos") or "").split(",") if c]
    saida["travas"] = [
        {"codigo": c, "rotulo": TravaDoArquivo[c.upper()].rotulo, "o_que_fazer": TravaDoArquivo[c.upper()].o_que_fazer}
        for c in (linha.get("travas") or "").split(",") if c]
    return saida


def empacotar(parquet_dos_arquivos: str, destino_zip: str, qual: str) -> int:
    """Os arquivos de envio (ou as prévias) num zip. Devolve quantos entraram.

    O zip é montado na pasta de trabalho, do disco local: é de lá que a API
    serve o download, em fluxo.
    """
    pasta = os.path.dirname(parquet_dos_arquivos)
    subpasta = PASTA_ENVIO if qual == ENVIO else PASTA_PREVIAS
    nomes = [r["nome"] for r in pq.read_table(parquet_dos_arquivos, columns=["nome", "destino"]).to_pylist()
             if r["destino"] == qual]
    provisorio = destino_zip + ".tmp"
    with zipfile.ZipFile(provisorio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nome in sorted(nomes):
            z.write(os.path.join(pasta, subpasta, nome), arcname=nome)
    os.replace(provisorio, destino_zip)
    log.info("arquivos digitais empacotados", extra={"qual": qual, "arquivos": len(nomes), "zip": destino_zip})
    return len(nomes)


def serializar(resumo: ResumoDoArquivoDigital) -> dict:
    def texto(v):
        return format(Decimal(v).quantize(_Q2), "f")

    return {
        "venda_a_consumidor": resumo.venda_a_consumidor,
        "competencias": resumo.competencias,
        "competencias_fora_de_sp": resumo.competencias_fora_de_sp,
        "arquivos": resumo.arquivos,
        "para_envio": resumo.para_envio,
        "previas": resumo.previas,
        "linhas": resumo.linhas,
        "bytes": resumo.bytes,
        "por_registro": dict(sorted(resumo.por_registro.items())),
        "linhas_sem_documento": resumo.linhas_sem_documento,
        "erros": resumo.erros,
        "avisos": resumo.avisos,
        "itens_recompostos": resumo.itens_recompostos,
        "itens_que_fecham": resumo.itens_que_fecham,
        "ressarcimento_para_envio": texto(resumo.ressarcimento_para_envio),
        "complemento_para_envio": texto(resumo.complemento_para_envio),
        "efds_lidas": resumo.efds_lidas,
        "efds_ilegiveis": resumo.efds_ilegiveis,
        "por_trava": [
            {"codigo": t.codigo, "rotulo": t.rotulo, "o_que_fazer": t.o_que_fazer,
             "arquivos": resumo.por_trava[t.codigo]}
            for t in TravaDoArquivo if resumo.por_trava.get(t.codigo)
        ],
        "por_regra": [
            {"codigo": r.codigo, "rotulo": r.rotulo, "severidade": r.severidade.value,
             "o_que_fazer": r.o_que_fazer, "arquivos": resumo.por_regra[r.codigo][0],
             "ocorrencias": resumo.por_regra[r.codigo][1]}
            for r in Regra if r.codigo in resumo.por_regra
        ],
    }
