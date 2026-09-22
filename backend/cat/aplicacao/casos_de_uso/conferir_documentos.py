"""Conferir o que foi escriturado contra o documento que o cliente entregou.

Roda fora da requisição, como manda a arquitetura: a base de uma empresa desta
casa tem 7.036 arquivos e 100 GB, e um arquivo sozinho traz 39.265 registros
C100. A API cria a execução, devolve o identificador e o front acompanha.

A sequência é sempre a mesma:

    1. EFD  → parquet com todo C100 e C800
    2. pasta → parquet com a chave de cada XML e de cada linha do relatório
    3. confronto → duas listas em parquet e um resumo no banco

Os parquets ficam em disco local, numa pasta por execução. Disco de rede perde
gravação longa (ARQUITETURA §8), e uma execução dessas grava por minutos.
"""

from __future__ import annotations

import os
import shutil
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    exigir_que_ande,
    registrar_de_etapa,
)
from cat.config import obter_config
from cat.dominio.icms.cat42.conferencia import ResumoDaConferencia
from cat.dominio.projeto.historico import TipoDeEvento
from cat.dominio.lote import TipoDeArquivo
from cat.infraestrutura.analitico.confronto import (
    ARQUIVO_SEM_DOCUMENTO,
    confrontar,
)
from cat.infraestrutura.analitico.extracao import (
    Progresso,
    extrair_efd,
    extrair_pasta,
)
from cat.infraestrutura.arquivos.xml_compactado import contar_xml
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    ExecucaoDB,
    LoteDB,
    ProjetoDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "conferencia"

ARQUIVO_EFD = "efd.parquet"
ARQUIVO_PASTA = "pasta.parquet"

# de quanto em quanto tempo o progresso vai ao banco. Gravar a cada arquivo
# faria 7.036 UPDATEs para um trabalho que dura minutos.
SEGUNDOS_ENTRE_AVISOS = 2.0


class NadaParaConferir(ValueError):
    """O lote não tem o que confrontar."""


def caminhos_do_projeto(
    projeto_id: int, tipos: tuple[TipoDeArquivo, ...], sessao: Session
) -> list[str]:
    valores = [t.value for t in tipos]
    return list(sessao.scalars(
        select(ArquivoDoLoteDB.caminho)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id,
               ArquivoDoLoteDB.tipo.in_(valores))
        .order_by(ArquivoDoLoteDB.caminho)
    ))


def caminhos_de_efd_vigentes(
    projeto_id: int, sessao: Session
) -> tuple[list[str], list[str]]:
    """As EFD ICMS/IPI que valem, e as originais que uma retificadora substituiu.

    A retificadora substitui a original do mesmo estabelecimento e período POR
    INTEIRO — é a regra fiscal, não uma escolha nossa. Ler as duas dobraria os
    documentos do período e, pior, misturaria valores de antes e depois da
    retificação numa linha só. Então, onde há retificadora, a original sai da
    leitura. Sai da leitura, não do lote: continua registrada, e a tela diz
    quantas ficaram de fora e por quê.

    Se houver mais de uma retificadora para o mesmo período, todas entram: não
    há como saber qual é a mais recente sem a data de recepção, que o registro
    0000 não traz. Fica no log para alguém olhar.
    """
    linhas = sessao.execute(
        select(ArquivoDoLoteDB.caminho, ArquivoDoLoteDB.cnpj,
               ArquivoDoLoteDB.competencia, ArquivoDoLoteDB.retificadora)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id,
               ArquivoDoLoteDB.tipo == TipoDeArquivo.SPED_ICMS_IPI.value)
        .order_by(ArquivoDoLoteDB.caminho)
    ).all()

    retificadas = {(cnpj, competencia)
                   for _, cnpj, competencia, retificadora in linhas if retificadora}
    vigentes: list[str] = []
    substituidas: list[str] = []
    for caminho, cnpj, competencia, retificadora in linhas:
        if not retificadora and (cnpj, competencia) in retificadas:
            substituidas.append(caminho)
        else:
            vigentes.append(caminho)

    repetidas = [chave for chave, n in Counter(
        (cnpj, competencia) for _, cnpj, competencia, r in linhas if r
    ).items() if n > 1]
    if repetidas:
        log.warning("mais de uma retificadora para o mesmo período; todas entram",
                    extra={"projeto_id": projeto_id,
                           "periodos": [f"{c} {p}" for c, p in repetidas][:10]})
    if substituidas:
        log.info("EFD originais substituídas por retificadora",
                 extra={"projeto_id": projeto_id, "quantas": len(substituidas),
                        "amostra": [os.path.basename(c) for c in substituidas[:5]]})
    return vigentes, substituidas


def pasta_da_execucao(execucao_id: int) -> str:
    raiz = obter_config().raiz_de_trabalho
    return os.path.join(raiz, f"execucao-{execucao_id}")


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    """Cria a execução já sabendo quantos arquivos vai ler.

    Confere aqui, ainda dentro da requisição, se há o que fazer: é barato, e
    dizer 'não há EFD neste trabalho' na hora vale mais do que uma execução que
    nasce e morre em silêncio.
    """
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "conferir documentos")

    efd, _ = caminhos_de_efd_vigentes(projeto_id, sessao)
    if not efd:
        raise NadaParaConferir(
            "Este trabalho não tem nenhuma EFD ICMS/IPI importada. "
            "Importe a base de dados antes de conferir."
        )
    documentos = caminhos_do_projeto(
        projeto_id,
        (TipoDeArquivo.XML_NFE, TipoDeArquivo.XML_COMPACTADO, TipoDeArquivo.GERENCIAL_MOVIMENTO),
        sessao,
    )
    if not documentos:
        raise NadaParaConferir(
            "Este trabalho não tem XML nem relatório de movimento do cliente. "
            "Sem documento para confrontar, a conferência não diz nada."
        )

    execucao = ExecucaoDB(
        projeto_id=projeto_id,
        etapa=ETAPA,
        situacao="na_fila",
        passo="Na fila",
        arquivos_totais=len(efd) + len(documentos),
        criada_por=usuario_id,
    )
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Conferência de documentos · {len(efd)} EFD e "
        f"{len(documentos)} documento(s) do cliente",
        dados={"execucao_id": execucao.id,
               "arquivos": execucao.arquivos_totais},
        autor_id=usuario_id,
    )
    return execucao


def executar(execucao_id: int) -> None:
    """O trabalho pesado. Roda em linha de execução própria, com sessão própria."""
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None:
            log.error("execução sumiu antes de rodar",
                      extra={"execucao_id": execucao_id})
            return

        destino = pasta_da_execucao(execucao_id)
        with contexto(etapa=ETAPA, execucao_id=execucao_id,
                      projeto_id=execucao.projeto_id):
            try:
                _rodar(execucao, destino, sessao)
            except Exception as erro:            # noqa: BLE001
                # qualquer falha precisa virar linha visível: execução que morre
                # calada deixa o usuário olhando uma barra que não anda
                log.exception("conferência falhou", extra={"erro": str(erro)})
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                sessao.commit()
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Conferência falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por,
                )


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session) -> None:
    os.makedirs(destino, exist_ok=True)
    execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo a EFD"
    sessao.commit()

    projeto_id = execucao.projeto_id
    efd, substituidas = caminhos_de_efd_vigentes(projeto_id, sessao)
    xmls = caminhos_do_projeto(projeto_id, (TipoDeArquivo.XML_NFE, TipoDeArquivo.XML_COMPACTADO), sessao)
    relatorios = caminhos_do_projeto(
        projeto_id, (TipoDeArquivo.GERENCIAL_MOVIMENTO,), sessao)

    execucao.arquivos_totais = len(efd) + contar_xml(xmls) + len(relatorios)
    sessao.commit()

    relogio = _Relogio(execucao, sessao, execucao.arquivos_totais)

    inicio = time.time()
    caminho_efd = os.path.join(destino, ARQUIVO_EFD)
    passo_efd = extrair_efd(efd, caminho_efd, avisar=relogio.marcar)

    # A EFD acabou: os totais dela ficam congelados na linha. Sem isto, o
    # relógio da fase seguinte sobrescrevia `documentos` e `bytes` com os
    # números da leitura dos XML — e a tela mostrava "1 documentos · 0 B"
    # para uma base de 37,9 milhões, o que parecia travamento.
    relogio.deslocar(len(efd))
    relogio.congelar_totais(documentos=passo_efd.documentos,
                            bytes_lidos=passo_efd.bytes_lidos)
    execucao.passo = "Lendo os documentos do cliente"
    sessao.commit()

    caminho_pasta = os.path.join(destino, ARQUIVO_PASTA)
    passo_pasta = extrair_pasta(xmls, relatorios, caminho_pasta,
                                avisar=relogio.marcar)

    # leitura acabou por inteiro: o contador de arquivos fecha antes de o
    # confronto começar, em vez de ficar no último tique que o limitador viu
    execucao.passo = "Confrontando"
    execucao.arquivos_lidos = execucao.arquivos_totais
    execucao.fracao = 0.97
    sessao.commit()

    resumo = confrontar(caminho_efd, caminho_pasta, destino,
                        anterior=_pendencias_anteriores(execucao, sessao))
    resumo.efd_originais_substituidas = len(substituidas)
    resumo.xml_repetidos = passo_pasta.xml_repetidos
    resumo.xml_nao_autorizados = passo_pasta.xml_nao_autorizados

    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = execucao.arquivos_totais
    execucao.bytes_lidos = passo_efd.bytes_lidos + passo_pasta.bytes_lidos
    execucao.documentos = passo_efd.documentos
    execucao.resumo = _serializar(resumo, passo_efd, passo_pasta)
    execucao.terminada_em = datetime.now(timezone.utc)
    sessao.commit()

    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Conferência concluída · {resumo.conferidos:,} com documento, "
        f"{resumo.sem_documento:,} a cobrar, "
        f"{resumo.nao_escrituradas:,} não escrituradas".replace(",", "."),
        dados={"execucao_id": execucao.id,
               "escriturados": resumo.escriturados,
               "conferidos": resumo.conferidos,
               "sem_documento": resumo.sem_documento,
               "nao_escrituradas": resumo.nao_escrituradas,
               "segundos": round(time.time() - inicio, 1)},
        autor_id=execucao.criada_por,
    )
    log.info("conferência concluída",
             extra={"segundos": round(time.time() - inicio, 1),
                    "documentos": passo_efd.documentos,
                    "sem_documento": resumo.sem_documento,
                    "nao_escrituradas": resumo.nao_escrituradas})


def _pendencias_anteriores(execucao: ExecucaoDB, sessao: Session) -> str | None:
    """O `sem_documento.parquet` da última rodada concluída deste trabalho.

    É o que permite dizer o que andou. Quando a pasta da rodada anterior já foi
    limpa, a comparação simplesmente não aparece — o resultado desta rodada
    continua completo, só não tem com o que se comparar.
    """
    anterior = sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == execucao.projeto_id,
               ExecucaoDB.etapa == ETAPA,
               ExecucaoDB.situacao == "concluida",
               ExecucaoDB.id != execucao.id)
        .order_by(ExecucaoDB.id.desc())
        .limit(1)
    )
    if anterior is None or not anterior.pasta_de_trabalho:
        return None
    caminho = os.path.join(anterior.pasta_de_trabalho, ARQUIVO_SEM_DOCUMENTO)
    return caminho if os.path.isfile(caminho) else None


def _serializar(resumo: ResumoDaConferencia, efd: Progresso,
                pasta: Progresso) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    dados = asdict(resumo)
    dados["origens"] = [o.value for o in resumo.origens]
    for chave in ("valor_conferido", "valor_nao_escriturado",
                  "valor_sem_documento"):
        dados[chave] = str(dados[chave])
    for lista in ("por_modelo", "por_operacao", "por_classificacao"):
        dados[lista] = [{**f, "valor": str(f["valor"])} for f in dados[lista]]
    dados["cobertura"] = round(resumo.cobertura, 4)
    dados["avisos"] = resumo.avisos
    dados["andou"] = resumo.andou
    dados["recusados"] = (efd.recusados + pasta.recusados)[:20]
    dados["observacoes"] = (efd.observacoes + pasta.observacoes)[:20]
    return dados


def descartar_pasta(execucao: ExecucaoDB) -> None:
    """Apaga os parquets de uma execução. A linha do banco fica."""
    if execucao.pasta_de_trabalho and os.path.isdir(execucao.pasta_de_trabalho):
        shutil.rmtree(execucao.pasta_de_trabalho, ignore_errors=True)


class _Relogio:
    """Leva o progresso ao banco de vez em quando, não a cada arquivo."""

    def __init__(self, execucao: ExecucaoDB, sessao: Session, total: int) -> None:
        self.execucao = execucao
        self.sessao = sessao
        self.total = max(total, 1)
        self.deslocamento = 0
        self.ultimo = 0.0
        # totais de uma fase já encerrada; a fase seguinte não os rebaixa
        self.congelados: dict[str, int] | None = None

    def deslocar(self, quantos: int) -> None:
        self.deslocamento += quantos

    def congelar_totais(self, documentos: int, bytes_lidos: int) -> None:
        """Fixa `documentos` e `bytes` da fase que acabou e grava na hora.

        Cada fase de extração conta a própria coisa — a EFD conta C100/C800,
        a pasta conta chaves de XML. Se a segunda escrevesse por cima da
        primeira, a tela mostraria "1 documentos · 0 B" numa base de 37,9
        milhões. Gravar na hora também cobre o último tique que o limitador de
        dois segundos costuma engolir (era o "885 de 960").
        """
        self.congelados = {"documentos": documentos, "bytes_lidos": bytes_lidos}
        self.execucao.documentos = documentos
        self.execucao.bytes_lidos = bytes_lidos
        self.execucao.arquivos_lidos = self.deslocamento
        self.execucao.fracao = min(0.95, self.deslocamento / self.total)

    def marcar(self, progresso: Progresso) -> None:
        agora = time.monotonic()
        if agora - self.ultimo < SEGUNDOS_ENTRE_AVISOS:
            return
        self.ultimo = agora
        lidos = self.deslocamento + progresso.arquivos_lidos
        self.execucao.arquivos_lidos = lidos
        if self.congelados is None:
            self.execucao.bytes_lidos = progresso.bytes_lidos
            self.execucao.documentos = progresso.documentos
        else:
            # a fase atual conta outra coisa (chaves de XML); os totais que a
            # tela mostra continuam sendo os da EFD
            self.execucao.bytes_lidos = self.congelados["bytes_lidos"] + progresso.bytes_lidos
            self.execucao.documentos = self.congelados["documentos"]
        # 0,95 e não 1: o confronto ainda vem depois da leitura
        self.execucao.fracao = min(0.95, lidos / self.total)
        try:
            self.sessao.commit()
        except Exception:                        # noqa: BLE001
            # progresso é enfeite; perder um aviso não pode derrubar a extração
            self.sessao.rollback()
