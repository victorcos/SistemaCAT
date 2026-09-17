"""Pré-validar os arquivos digitais que o cliente já transmitiu.

A pré-validação é a mesma da etapa 7 (`cat.dominio.cat42.pre_validacao`): o
leiaute, a tabela de natureza e a Ficha 3 recomposta a partir do próprio
arquivo. O que muda é de onde o arquivo vem — gerado por outra ferramenta,
solto no lote ou dentro de zip — e o que só se confere com vários meses juntos.

## Zip sem extrair

Os arquivos da IRMAOS BOA chegaram em três zips, um deles com dois zips dentro:
805 e 295 TXT, dezenas de GB descompactados. Extrair para ler seria dobrar o
disco por nada: cada TXT é lido em fluxo de dentro do zip. O zip aninhado é a
exceção — lido por dentro, cada membro descomprimiria o de fora desde o começo
—, e vai compactado à pasta da execução, que é disco local, e é apagado depois.

## O que só se vê com o conjunto

* **Arquivo repetido.** O mesmo estabelecimento e mês em dois lugares (o zip que
  é cópia de outro, na BOA). O primeiro é lido; os outros ficam listados como
  repetidos, sem ler de novo — salvo a **substituição** (COD_FIN 02), que é o
  que vale na SEFAZ: lida depois de um original, ela é validada e o original
  vira substituído, fora dos totais, das ocorrências e da continuidade.
* **Continuidade do saldo.** O QTD_INI de um item num mês tem de ser o QTD_FIM
  da última competência em que ele apareceu. Quando não é, falta arquivo no
  meio ou o estoque foi ajustado por fora — aviso, com as duas competências.
* **Arquivo de outra empresa** fica de fora e contado, como na importação.
"""

from __future__ import annotations

import hashlib
import io
import multiprocessing
import os
import shutil
import zipfile
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.pre_validacao import Regra, Severidade, Validacao, validar
from cat.dominio.lote import caminho_de_certificado
from cat.infraestrutura.analitico.arquivo_digital import (
    ARQUIVO_OCORRENCIAS,
    ESQUEMA_OCORRENCIAS,
    _processos_viaveis,
)
from cat.infraestrutura.analitico.confronto import _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada, _leitura
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ARQUIVOS_DO_CLIENTE = "arquivos_do_cliente.parquet"
ARQUIVO_SALDOS_DO_CLIENTE = "saldos_do_cliente.parquet"
POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200
EXEMPLOS_DE_CONTINUIDADE_POR_ARQUIVO = 200
_Q2 = Decimal("0.01")

ESQUEMA_ARQUIVOS_DO_CLIENTE = pa.schema([
    ("nome", pa.string()),
    ("origem", pa.string()),                   # o caminho, e o membro quando veio de zip
    ("cnpj", pa.string()),
    ("competencia", pa.string()),              # "2024-01"
    ("repetido", pa.bool_()),
    ("finalidade", pa.string()),               # COD_FIN do 0000: 00 regular, 01 intimação, 02 substituição
    ("substituido", pa.bool_()),               # lido e depois vencido por uma substituição do mesmo mês
    ("linhas", pa.int64()),
    ("bytes", pa.int64()),
    ("sha256", pa.string()),
    ("participantes", pa.int32()),
    ("itens", pa.int32()),
    ("saldos", pa.int32()),
    ("eletronicos", pa.int64()),
    ("nao_eletronicos", pa.int64()),
    ("erros", pa.int64()),
    ("avisos", pa.int64()),
    ("itens_recompostos", pa.int32()),
    ("itens_que_fecham", pa.int32()),
    ("maior_diferenca_de_valor", pa.decimal128(24, 2)),
])

ESQUEMA_SALDOS_DO_CLIENTE = pa.schema([
    ("nome", pa.string()),
    ("cnpj", pa.string()),
    ("competencia", pa.string()),
    ("codigo", pa.string()),
    ("qtd_ini", pa.decimal128(24, 3)),
    ("icms_tot_ini", pa.decimal128(24, 2)),
    ("qtd_fim", pa.decimal128(24, 3)),
    ("icms_tot_fim", pa.decimal128(24, 2)),
])

DeveParar = Callable[[], bool]


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A pré-validação foi cancelada por quem a pediu.")


@dataclass
class Andamento:
    arquivos: int = 0
    bytes: int = 0


@dataclass
class ResumoDaPreValidacao:
    fontes: int = 0
    arquivos: int = 0
    sem_ocorrencia: int = 0
    com_erro: int = 0
    com_aviso: int = 0
    repetidos: int = 0
    substituidos: int = 0
    de_outra_empresa: int = 0
    nao_sao_da_cat42: int = 0
    ilegiveis: int = 0
    linhas: int = 0
    bytes: int = 0
    erros: int = 0
    avisos: int = 0
    itens_recompostos: int = 0
    itens_que_fecham: int = 0
    estabelecimentos: set = field(default_factory=set)
    competencias: set = field(default_factory=set)
    por_regra: dict = field(default_factory=dict)      # código -> (arquivos, ocorrências)


# ---------------------------------------------------------------------------
# de onde vêm os arquivos
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidato:
    origem: str
    nome: str
    abrir: Callable[[], io.RawIOBase]
    # onde reabrir em outro processo: ("arquivo", caminho, None) ou ("zip", caminho do zip, membro)
    local: tuple = ("arquivo", "", None)


def candidatos(fontes: list[str], resumo: ResumoDaPreValidacao, rascunho: str,
               aninhados: list[str] | None = None) -> Iterator[Candidato]:
    """Cada TXT solto e cada TXT dentro de zip (com um nível de zip aninhado).

    `aninhados` recebe o caminho de cada zip aninhado copiado para o disco, que
    então fica até quem chamou apagar: um processo filho ainda pode estar lendo.
    Sem a lista, cada um é apagado assim que seus membros acabam.
    """
    for caminho in fontes:
        resumo.fontes += 1
        if caminho.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(caminho) as z:
                    yield from _do_zip(z, caminho, caminho, resumo, rascunho, aninhados)
            except (OSError, zipfile.BadZipFile) as erro:
                resumo.ilegiveis += 1
                log.warning("zip ilegível na pré-validação", extra={"arquivo": caminho, "motivo": str(erro)})
        else:
            yield Candidato(caminho, os.path.basename(caminho), lambda c=caminho: open(c, "rb"),
                            ("arquivo", caminho, None))


def _do_zip(z: zipfile.ZipFile, origem: str, caminho_do_zip: str, resumo: ResumoDaPreValidacao, rascunho: str,
            aninhados: list[str] | None, nivel: int = 0) -> Iterator[Candidato]:
    for info in z.infolist():
        nome = info.filename
        if caminho_de_certificado(nome):
            # certificado dentro do zip: não se abre, e o nome não vai a log nem ao resumo
            continue
        if nome.lower().endswith(".txt"):
            yield Candidato(f"{origem} :: {nome}", os.path.basename(nome), lambda i=info: z.open(i),
                            ("zip", caminho_do_zip, nome))
        elif nome.lower().endswith(".zip") and nivel == 0:
            # zip dentro de zip não se lê por dentro: cada membro faria descomprimir
            # o de fora desde o começo. Vai compactado ao disco local e volta a ser zip
            local = os.path.join(rascunho, f".aninhado-{os.getpid()}-{abs(hash(origem + nome))}.zip")
            if aninhados is not None:
                aninhados.append(local)
            try:
                with z.open(info) as interno, open(local, "wb") as saida:
                    shutil.copyfileobj(interno, saida, 1 << 20)
                with zipfile.ZipFile(local) as zi:
                    yield from _do_zip(zi, f"{origem} :: {nome}", local, resumo, rascunho, aninhados, nivel + 1)
            except (OSError, zipfile.BadZipFile) as erro:
                resumo.ilegiveis += 1
                log.warning("zip aninhado ilegível na pré-validação",
                            extra={"arquivo": f"{origem} :: {nome}", "motivo": str(erro)})
            finally:
                if aninhados is None and os.path.isfile(local):
                    os.remove(local)


def _validar_local(local: tuple) -> tuple[int, str, Validacao]:
    """Lê o arquivo inteiro e pré-valida: o que um processo filho faz.

    Os exemplos e os saldos voltam ao principal, que grava e em seguida os solta
    — com centenas de arquivos, segurá-los todos não caberia. Cada filho lê um
    arquivo por vez, e a BOA manda arquivos de até 77 MB: é por arquivo, e não
    por linha, que a leitura se divide.
    """
    tipo, caminho, membro = local
    if tipo == "zip":
        with zipfile.ZipFile(caminho) as z, z.open(membro) as bruto:
            contado = _Contado(bruto)
            v = validar(contado)
    else:
        with open(caminho, "rb") as bruto:
            contado = _Contado(bruto)
            v = validar(contado)
    return contado.bytes, contado.hash.hexdigest(), v


class _Contado:
    """Passa as linhas adiante contando bytes e somando o SHA-256 do conteúdo."""

    def __init__(self, bruto) -> None:
        self.bruto = bruto
        self.hash = hashlib.sha256()
        self.bytes = 0

    def __iter__(self):
        for linha in self.bruto:
            self.hash.update(linha)
            self.bytes += len(linha)
            yield linha


def _abertura(primeira: bytes) -> tuple[str, str, str] | None:
    """(CNPJ, competência "aaaa-mm", finalidade) do 0000, ou None se não é arquivo da CAT 42."""
    campos = primeira.rstrip(b"\r\n").decode("latin-1").split("|")
    if len(campos) != 8 or campos[0] != "0000" or len(campos[1]) != 6 or not campos[1].isdigit():
        return None
    return campos[3], f"{campos[1][2:]}-{campos[1][:2]}", campos[7]


FINALIDADE_SUBSTITUICAO = "02"


def _substitui(nova: str, anterior: str) -> bool:
    """A substituição vence o que não é substituição; entre iguais, vale o primeiro lido."""
    return nova == FINALIDADE_SUBSTITUICAO and anterior != FINALIDADE_SUBSTITUICAO


# ---------------------------------------------------------------------------
# a rodada
# ---------------------------------------------------------------------------
def pre_validar(
    fontes: list[str],
    destino: str,
    raiz_cnpj: str,
    avisar: Callable[[Andamento], None] | None = None,
    deve_parar: DeveParar | None = None,
    processos: int = 1,
) -> ResumoDaPreValidacao:
    """Pré-valida os arquivos do cliente, com `processos` lendo ao mesmo tempo.

    O principal lê só a primeira linha de cada arquivo e decide ali o que é
    repetido, substituição e nome; a leitura inteira vai a um processo filho
    (ou roda na hora, com um processo só). Os totais são somados no fim, só com
    os arquivos que valem.
    """
    resumo = ResumoDaPreValidacao()
    andamento = Andamento()
    caminho_arquivos = os.path.join(destino, ARQUIVO_ARQUIVOS_DO_CLIENTE)
    caminho_ocorrencias = os.path.join(destino, ARQUIVO_OCORRENCIAS)
    caminho_saldos = os.path.join(destino, ARQUIVO_SALDOS_DO_CLIENTE)
    # ocorrências e saldos vão primeiro a rascunhos: o arquivo substituído depois
    # de lido sai deles no fim, sem segurar os de todos na memória
    rascunho_oc = os.path.join(destino, ".ocorrencias_lidas.parquet")
    rascunho_saldos = os.path.join(destino, ".saldos_lidos.parquet")
    repetidos: list[dict] = []
    tarefas: list[dict] = []
    vistos: dict[tuple[str, str], dict] = {}
    nomes: dict[str, tuple[str, str]] = {}
    aninhados: list[str] = []
    if processos > 1 and not _processos_viaveis():
        log.warning("o módulo principal não se reimporta num processo novo; pré-validação num processo só")
        processos = 1
    pool = (ProcessPoolExecutor(max_workers=processos, mp_context=multiprocessing.get_context("spawn"))
            if processos > 1 else None)
    pendentes: dict[Future, dict] = {}

    escritor_oc = pq.ParquetWriter(rascunho_oc, ESQUEMA_OCORRENCIAS)
    escritor_saldos = pq.ParquetWriter(rascunho_saldos, ESQUEMA_SALDOS_DO_CLIENTE)

    def concluir(tarefa: dict, resultado=None, erro: BaseException | None = None) -> None:
        c, cnpj, competencia = tarefa["candidato"], tarefa["cnpj"], tarefa["competencia"]
        if erro is not None:
            if not isinstance(erro, (OSError, zipfile.BadZipFile, EOFError)):
                raise erro
            resumo.ilegiveis += 1
            tarefa["ilegivel"] = True
            anterior = tarefa.get("substitui")
            if anterior is not None and vistos.get((cnpj, competencia)) is tarefa:
                # o substituto não se leu: vale o que estava
                anterior["substituido"] = False
                vistos[(cnpj, competencia)] = anterior
            log.warning("arquivo ilegível na pré-validação", extra={"arquivo": c.origem, "motivo": str(erro)})
            return
        tamanho, sha, v = resultado
        tarefa["linha"] = _linha(c, cnpj, competencia, tamanho, sha, v, tarefa["finalidade"])
        ocorrencias = [_ocorrencia(c.nome, cnpj, competencia, o, v.por_regra[o.regra]) for o in v.exemplos]
        if ocorrencias:
            escritor_oc.write_table(pa.Table.from_pylist(ocorrencias, schema=ESQUEMA_OCORRENCIAS))
        if v.saldos:
            escritor_saldos.write_table(pa.Table.from_pylist([
                {"nome": c.nome, "cnpj": cnpj, "competencia": competencia, "codigo": codigo,
                 "qtd_ini": qi, "icms_tot_ini": vi, "qtd_fim": qf, "icms_tot_fim": vf}
                for codigo, (qi, vi, qf, vf) in v.saldos.items()], schema=ESQUEMA_SALDOS_DO_CLIENTE))
        # o que já foi gravado sai da memória; os totais só precisam das contagens
        v.saldos, v.exemplos = {}, []
        tarefa["validacao"] = v
        andamento.arquivos += 1
        andamento.bytes += tamanho
        if avisar is not None:
            avisar(andamento)
        log.info("arquivo do cliente pré-validado", extra={
            "arquivo": c.origem, "cnpj": cnpj, "competencia": competencia, "erros": v.erros,
            "avisos": v.avisos, "linhas": v.linhas})

    def colher(espera: float) -> None:
        if not pendentes:
            return
        prontos, _ = wait(list(pendentes), timeout=espera, return_when=FIRST_COMPLETED)
        for futuro in prontos:
            tarefa = pendentes.pop(futuro)
            erro = futuro.exception()
            if isinstance(erro, BrokenProcessPool):
                raise RuntimeError(
                    "Um processo da pré-validação parou sem responder (memória?). Para ler um arquivo "
                    "por vez, defina CAT_PROCESSOS_DO_ARQUIVO_DIGITAL=1 e rode de novo.") from erro
            concluir(tarefa, None if erro else futuro.result(), erro)

    try:
        # com processos, o zip aninhado fica no disco até o fim: um filho pode ainda estar lendo
        for c in candidatos(fontes, resumo, destino, aninhados if pool is not None else None):
            _conferir(deve_parar)
            try:
                with c.abrir() as bruto:
                    abertura = _abertura(bruto.readline())
            except (OSError, zipfile.BadZipFile, EOFError) as erro:
                resumo.ilegiveis += 1
                log.warning("arquivo ilegível na pré-validação", extra={"arquivo": c.origem, "motivo": str(erro)})
                continue
            if abertura is None:
                resumo.nao_sao_da_cat42 += 1
                continue
            cnpj, competencia, finalidade = abertura
            if cnpj[:8] != raiz_cnpj:
                resumo.de_outra_empresa += 1
                log.warning("arquivo da CAT 42 de outra empresa, fora da pré-validação",
                            extra={"arquivo": c.origem, "cnpj": cnpj})
                continue
            anterior = vistos.get((cnpj, competencia))
            if anterior is not None and not _substitui(finalidade, anterior["finalidade"]):
                repetidos.append(_repetido(c, cnpj, competencia, finalidade))
                log.info("arquivo repetido na pré-validação",
                         extra={"arquivo": c.origem, "primeiro": anterior["candidato"].origem})
                continue
            c = _com_nome_unico(c, cnpj, competencia, nomes)
            tarefa = {"candidato": c, "cnpj": cnpj, "competencia": competencia, "finalidade": finalidade,
                      "substitui": anterior, "substituido": False}
            if anterior is not None:
                # a substituição vence o original, lido antes ou ainda em leitura
                anterior["substituido"] = True
                log.info("arquivo substituído na pré-validação",
                         extra={"arquivo": anterior["candidato"].origem, "substituto": c.origem})
            vistos[(cnpj, competencia)] = tarefa
            tarefas.append(tarefa)
            if pool is None:
                try:
                    concluir(tarefa, _validar_local(c.local))
                except (OSError, zipfile.BadZipFile, EOFError) as erro:
                    concluir(tarefa, erro=erro)
            else:
                pendentes[pool.submit(_validar_local, c.local)] = tarefa
                # não deixa a fila crescer: cada resultado traz os saldos do arquivo
                while len(pendentes) >= 2 * processos:
                    _conferir(deve_parar)
                    colher(espera=1.0)
                colher(espera=0)
        while pendentes:
            _conferir(deve_parar)
            colher(espera=1.0)

        descartados = {tarefa["candidato"].nome for tarefa in tarefas
                       if tarefa["substituido"] and not tarefa.get("ilegivel")}
        escritor_saldos.close()
        _sem_os_descartados(destino, rascunho_saldos, caminho_saldos, descartados)
        linhas_de_arquivo = list(repetidos)
        for tarefa in tarefas:
            if tarefa.get("ilegivel"):
                continue
            linha = tarefa["linha"]
            if tarefa["substituido"]:
                linha["repetido"] = linha["substituido"] = True
                resumo.substituidos += 1
            else:
                v = tarefa["validacao"]
                _somar(resumo, tarefa["cnpj"], tarefa["competencia"], linha["bytes"], v)
            linhas_de_arquivo.append(linha)
        resumo.repetidos = sum(1 for l in linhas_de_arquivo if l["repetido"])
        _continuidade(destino, caminho_saldos, escritor_oc, linhas_de_arquivo, resumo)
        escritor_oc.close()
        _sem_os_descartados(destino, rascunho_oc, caminho_ocorrencias, descartados)
    except ApuracaoCancelada:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        escritor_oc.close()
        escritor_saldos.close()
        for alvo in (caminho_arquivos, caminho_ocorrencias, caminho_saldos):
            if os.path.isfile(alvo):
                os.remove(alvo)
        raise
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        escritor_oc.close()
        escritor_saldos.close()
        for rascunho in (rascunho_oc, rascunho_saldos, *aninhados):
            if os.path.isfile(rascunho):
                os.remove(rascunho)

    for l in linhas_de_arquivo:
        if l["repetido"]:
            continue
        if l["erros"]:
            resumo.com_erro += 1
        elif l["avisos"]:
            resumo.com_aviso += 1
        else:
            resumo.sem_ocorrencia += 1
    pq.write_table(pa.Table.from_pylist(
        sorted(linhas_de_arquivo, key=lambda l: (l["cnpj"], l["competencia"], l["repetido"], l["origem"])),
        schema=ESQUEMA_ARQUIVOS_DO_CLIENTE), caminho_arquivos)
    log.info("pré-validação dos arquivos do cliente concluída", extra={
        "arquivos": resumo.arquivos, "com_erro": resumo.com_erro, "repetidos": resumo.repetidos,
        "substituidos": resumo.substituidos, "de_outra_empresa": resumo.de_outra_empresa,
        "nao_sao_da_cat42": resumo.nao_sao_da_cat42, "processos": processos})
    return resumo


def _com_nome_unico(c: Candidato, cnpj: str, competencia: str, nomes: dict[str, tuple[str, str]]) -> Candidato:
    """O nome é a chave das ocorrências na tela e na planilha.

    A BOA nomeia pelo CNPJ e mês, mas outra ferramenta pode chamar todo mês de
    `CAT42.txt` em pastas diferentes — e aí as ocorrências de janeiro e de
    fevereiro se misturariam. O segundo nome igual ganha o estabelecimento e o
    mês entre parênteses.
    """
    dono = (cnpj, competencia)
    if nomes.setdefault(c.nome, dono) == dono:
        return c
    base, extensao = os.path.splitext(c.nome)
    novo = f"{base} ({cnpj} {competencia}){extensao}"
    nomes[novo] = dono
    log.info("nome de arquivo repetido na pré-validação, desambiguado",
             extra={"arquivo": c.origem, "nome": c.nome, "novo_nome": novo})
    return replace(c, nome=novo)


def _sem_os_descartados(destino: str, rascunho: str, final: str, descartados: set[str]) -> None:
    """Copia o rascunho para o arquivo final, sem as linhas dos arquivos substituídos."""
    if not descartados:
        os.replace(rascunho, final)
        return
    lista = ", ".join("'" + n.replace("'", "''") + "'" for n in sorted(descartados))
    con = _leitura(destino)
    try:
        con.execute(f"COPY (SELECT * FROM read_parquet('{_escapar(rascunho)}') WHERE nome NOT IN ({lista})) "
                    f"TO '{_escapar(final)}' (FORMAT PARQUET)")
    finally:
        con.close()
    os.remove(rascunho)


def _repetido(c: Candidato, cnpj: str, competencia: str, finalidade: str = "") -> dict:
    return {"nome": c.nome, "origem": c.origem, "cnpj": cnpj, "competencia": competencia, "repetido": True,
            "finalidade": finalidade, "substituido": False,
            "linhas": 0, "bytes": 0, "sha256": "", "participantes": 0, "itens": 0, "saldos": 0,
            "eletronicos": 0, "nao_eletronicos": 0, "erros": 0, "avisos": 0, "itens_recompostos": 0,
            "itens_que_fecham": 0, "maior_diferenca_de_valor": Decimal(0)}


def _linha(c: Candidato, cnpj: str, competencia: str, tamanho: int, sha: str, v, finalidade: str = "") -> dict:
    reg = v.por_registro
    return {"nome": c.nome, "origem": c.origem, "cnpj": cnpj, "competencia": competencia, "repetido": False,
            "finalidade": finalidade, "substituido": False,
            "linhas": v.linhas, "bytes": tamanho, "sha256": sha,
            "participantes": reg.get("0150", 0), "itens": reg.get("0200", 0), "saldos": reg.get("1050", 0),
            "eletronicos": reg.get("1100", 0), "nao_eletronicos": reg.get("1200", 0),
            "erros": v.erros, "avisos": v.avisos, "itens_recompostos": v.itens_recompostos,
            "itens_que_fecham": v.itens_que_fecham,
            "maior_diferenca_de_valor": v.maior_diferenca_de_valor.quantize(_Q2)}


def _ocorrencia(nome: str, cnpj: str, competencia: str, o, vezes: int) -> dict:
    return {"nome": nome, "cnpj": cnpj, "competencia": competencia, "regra": o.regra.codigo,
            "severidade": o.regra.severidade.value, "rotulo": o.regra.rotulo, "o_que_fazer": o.regra.o_que_fazer,
            "vezes_no_arquivo": vezes, "linha": o.linha, "registro": o.registro, "campo": o.campo,
            "item": o.item, "mensagem": o.mensagem}


def _somar(resumo: ResumoDaPreValidacao, cnpj: str, competencia: str, tamanho: int, v) -> None:
    resumo.arquivos += 1
    resumo.linhas += v.linhas
    resumo.bytes += tamanho
    resumo.erros += v.erros
    resumo.avisos += v.avisos
    resumo.itens_recompostos += v.itens_recompostos
    resumo.itens_que_fecham += v.itens_que_fecham
    resumo.estabelecimentos.add(cnpj)
    resumo.competencias.add(competencia)
    for regra, n in v.por_regra.items():
        arquivos, ocorrencias = resumo.por_regra.get(regra.codigo, (0, 0))
        resumo.por_regra[regra.codigo] = (arquivos + 1, ocorrencias + n)


def _continuidade(destino: str, saldos: str, escritor_oc, linhas_de_arquivo: list[dict],
                  resumo: ResumoDaPreValidacao) -> None:
    """O saldo inicial de cada item contra o final da última competência em que apareceu."""
    if not os.path.isfile(saldos) or pq.ParquetFile(saldos).metadata.num_rows == 0:
        return
    regra = Regra.SALDO_INICIAL_DIFERENTE_DO_ANTERIOR
    con = _abrir(destino)
    try:
        cursor = con.execute(f"""
            WITH ordenado AS (
                SELECT *, lag(qtd_fim) OVER j AS qtd_antes, lag(icms_tot_fim) OVER j AS icms_antes,
                       lag(competencia) OVER j AS competencia_antes
                FROM read_parquet('{_escapar(saldos)}')
                WINDOW j AS (PARTITION BY cnpj, codigo ORDER BY competencia)
            )
            SELECT nome, cnpj, competencia, codigo, qtd_ini, icms_tot_ini, qtd_antes, icms_antes, competencia_antes,
                   count(*) OVER (PARTITION BY nome) AS vezes,
                   row_number() OVER (PARTITION BY nome ORDER BY codigo) AS ordem
            FROM ordenado
            WHERE competencia_antes IS NOT NULL
              AND (abs(qtd_ini - qtd_antes) > 0.0005 OR abs(icms_tot_ini - icms_antes) > 0.05)
        """)
        por_arquivo: dict[str, int] = {}
        while lote := cursor.fetchmany(10_000):
            linhas = []
            for nome, cnpj, competencia, codigo, qi, vi, qa, va, ca, vezes, ordem in lote:
                por_arquivo[nome] = vezes
                if ordem > EXEMPLOS_DE_CONTINUIDADE_POR_ARQUIVO:
                    continue
                linhas.append({
                    "nome": nome, "cnpj": cnpj, "competencia": competencia, "regra": regra.codigo,
                    "severidade": regra.severidade.value, "rotulo": regra.rotulo, "o_que_fazer": regra.o_que_fazer,
                    "vezes_no_arquivo": vezes, "linha": None, "registro": "1050", "campo": "QTD_INI", "item": codigo,
                    "mensagem": (f"Item '{codigo}' abre {competencia} com {qi.normalize():f} un e R$ {vi}; "
                                 f"fechou {ca} com {qa.normalize():f} un e R$ {va}.")})
            if linhas:
                escritor_oc.write_table(pa.Table.from_pylist(linhas, schema=ESQUEMA_OCORRENCIAS))
    finally:
        con.close()
        _limpar(destino)
    for l in linhas_de_arquivo:
        n = por_arquivo.get(l["nome"], 0) if not l["repetido"] else 0
        if n:
            l["avisos"] += n
            resumo.avisos += n
            arquivos, ocorrencias = resumo.por_regra.get(regra.codigo, (0, 0))
            resumo.por_regra[regra.codigo] = (arquivos + 1, ocorrencias + n)


# ---------------------------------------------------------------------------
# o que a tela lê depois de pronto
# ---------------------------------------------------------------------------
_RECORTES = {
    "com_erro": "NOT repetido AND erros > 0",
    "com_aviso": "NOT repetido AND erros = 0 AND avisos > 0",
    "sem_ocorrencia": "NOT repetido AND erros = 0 AND avisos = 0",
    "repetidos": "repetido",
    "substituidos": "substituido",
}


def arquivos_do_cliente(destino: str, so: str | None = None, busca: str | None = None,
                        pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Os arquivos lidos: com erro primeiro, depois por estabelecimento e mês."""
    if so and so not in _RECORTES:
        raise ValueError(f"Recorte desconhecido: {so}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_ARQUIVOS_DO_CLIENTE)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_ARQUIVOS_DO_CLIENTE} não está em {destino}.")
    filtros, parametros = [], []
    if so:
        filtros.append(_RECORTES[so])
    if busca and busca.strip():
        filtros.append("(cnpj ILIKE ? OR competencia ILIKE ? OR nome ILIKE ? OR origem ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 4
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"
    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY repetido, erros = 0, avisos = 0, cnpj, competencia
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [{k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in zip(nomes, r)}
                  for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def serializar(resumo: ResumoDaPreValidacao) -> dict:
    competencias = sorted(resumo.competencias)
    return {
        "fontes": resumo.fontes,
        "arquivos": resumo.arquivos,
        "sem_ocorrencia": resumo.sem_ocorrencia,
        "com_erro": resumo.com_erro,
        "com_aviso": resumo.com_aviso,
        "repetidos": resumo.repetidos,
        "substituidos": resumo.substituidos,
        "de_outra_empresa": resumo.de_outra_empresa,
        "nao_sao_da_cat42": resumo.nao_sao_da_cat42,
        "ilegiveis": resumo.ilegiveis,
        "linhas": resumo.linhas,
        "bytes": resumo.bytes,
        "erros": resumo.erros,
        "avisos": resumo.avisos,
        "itens_recompostos": resumo.itens_recompostos,
        "itens_que_fecham": resumo.itens_que_fecham,
        "estabelecimentos": len(resumo.estabelecimentos),
        "competencia_inicial": competencias[0] if competencias else None,
        "competencia_final": competencias[-1] if competencias else None,
        "por_regra": [
            {"codigo": r.codigo, "rotulo": r.rotulo, "severidade": r.severidade.value,
             "o_que_fazer": r.o_que_fazer, "arquivos": resumo.por_regra[r.codigo][0],
             "ocorrencias": resumo.por_regra[r.codigo][1]}
            for r in sorted(Regra, key=lambda r: r.severidade is not Severidade.ERRO)
            if r.codigo in resumo.por_regra
        ],
    }
