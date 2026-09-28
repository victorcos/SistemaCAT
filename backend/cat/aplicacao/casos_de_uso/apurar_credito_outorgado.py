"""Etapa: separar, nos XML do trabalho, o que entra no crédito outorgado.

Varre as NF-e, NFC-e e CF-e do lote e diz, item a item, o que é produto
beneficiado — pela descrição, que decide, e pela NCM, que confirma. Portado do
projeto `Quebra de SPED`; a regra está em `dominio/icms/credito_outorgado` e o
porquê de cada diferença está lá.

**O filtro é do trabalho e fica no banco** (`credito_outorgado_filtro`). Sem
nenhum termo cadastrado a etapa se recusa a rodar, em vez de varrer 120 mil
arquivos para entregar uma lista vazia — quem quer ver o universo antes de
escrever o primeiro termo liga o `sem_filtro`, que é explícito.

**Só o que a empresa vendeu.** O benefício é sobre a saída, e o lote costuma ter
tudo junto: a nota que a empresa emitiu e a que ela recebeu do fornecedor. A
direção sai do cruzamento entre o emitente e a raiz do CNPJ da empresa do
trabalho — `tpNF` sozinho é do ponto de vista de quem emitiu.

Não depende de etapa nenhuma: lê os XML do lote direto, como a quebra lê os
SPED. Cada rodada guarda no resumo o filtro que a produziu.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import caminhos_do_projeto, pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de
from cat.dominio.icms.credito_outorgado import Filtro
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.credito_outorgado import (
    LeituraCancelada,
    ProgressoDoCredito,
    serializar,
    varrer,
)
from cat.infraestrutura.arquivos.xml_compactado import contar_xml
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import (
    EmpresaDB, ExecucaoDB, FiltroDoCreditoOutorgadoDB, ProjetoDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "credito_outorgado"
VERSAO_DO_RESUMO = 1

FONTES = (TipoDeArquivo.XML_NFE, TipoDeArquivo.XML_COMPACTADO)


class NadaParaVarrer(ValueError):
    """Não há como rodar: falta o XML, ou falta o filtro."""


class SemFiltro(NadaParaVarrer):
    """Nenhum termo cadastrado, e a chave geral desligada: nada seria elegível."""


def filtro_do_projeto(projeto_id: int, sessao: Session) -> tuple[Filtro, bool]:
    """O filtro gravado e se os descartados devem ser guardados.

    Trabalho sem linha na tabela tem filtro vazio — e filtro vazio não julga,
    que é o que `preparar` verifica antes de varrer coisa alguma.
    """
    linha = sessao.get(FiltroDoCreditoOutorgadoDB, projeto_id)
    if linha is None:
        return Filtro.de(), False
    return (Filtro.de(ncms=linha.ncms or [], termos=linha.termos or [],
                      sem_filtro=bool(linha.sem_filtro)),
            bool(linha.guardar_descartados))


def gravar_filtro(projeto_id: int, ncms: list[str], termos: list[str], *,
                  sem_filtro: bool, guardar_descartados: bool,
                  usuario_id: int | None, sessao: Session) -> FiltroDoCreditoOutorgadoDB:
    """Cria ou atualiza o filtro do trabalho. Normaliza pelo domínio, não aqui."""
    limpo = Filtro.de(ncms=ncms, termos=termos, sem_filtro=sem_filtro)
    linha = sessao.get(FiltroDoCreditoOutorgadoDB, projeto_id)
    if linha is None:
        linha = FiltroDoCreditoOutorgadoDB(projeto_id=projeto_id)
        sessao.add(linha)
    linha.ncms = list(limpo.ncms)
    linha.termos = list(limpo.termos)
    linha.sem_filtro = limpo.sem_filtro
    linha.guardar_descartados = guardar_descartados
    linha.atualizado_em = datetime.now(timezone.utc)
    linha.atualizado_por = usuario_id
    sessao.commit()
    log.info("filtro do crédito outorgado gravado", extra={
        "projeto_id": projeto_id, "ncms": len(limpo.ncms), "termos": len(limpo.termos),
        "sem_filtro": limpo.sem_filtro, "guardar_descartados": guardar_descartados,
        "usuario_id": usuario_id})
    return linha


def raiz_da_empresa(projeto_id: int, sessao: Session) -> str:
    """A raiz do CNPJ da empresa do trabalho: é ela que diz o que é saída nossa.

    Vazia quando o trabalho não tem empresa — e aí a varredura não filtra
    direção nenhuma, em vez de filtrar tudo por engano.
    """
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        return ""
    empresa = sessao.get(EmpresaDB, projeto.empresa_id)
    return (empresa.cnpj_raiz or "") if empresa is not None else ""


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar o crédito outorgado")
    xmls = caminhos_do_projeto(projeto_id, FONTES, sessao)
    if not xmls:
        raise NadaParaVarrer(
            "O lote não tem XML de NF-e, NFC-e ou CF-e. Importe a pasta (ou o zip) com "
            "os documentos que a empresa emitiu no período.")
    filtro, _ = filtro_do_projeto(projeto_id, sessao)
    if not filtro.julga:
        raise SemFiltro(
            "Cadastre ao menos um termo de descrição antes de rodar: sem termo, nenhum "
            "item seria elegível. Para ver todos os itens sem julgar nenhum, ligue "
            "\"rodar sem filtro\".")
    total = contar_xml(xmls)
    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=total, criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Crédito outorgado · {milhar(total)} XML e {len(filtro.termos)} termo(s) de descrição",
        dados={"execucao_id": execucao.id, "xml": total, "ncms": len(filtro.ncms),
               "termos": len(filtro.termos), "sem_filtro": filtro.sem_filtro},
        autor_id=usuario_id)
    return execucao


def executar(execucao_id: int) -> None:
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None:
            log.error("execução sumiu antes de rodar", extra={"execucao_id": execucao_id})
            return
        destino = pasta_da_execucao(execucao_id)
        diario = Diario(execucao, sessao, VERSAO_DO_RESUMO)
        with contexto(etapa=ETAPA, execucao_id=execucao_id, projeto_id=execucao.projeto_id):
            try:
                _rodar(execucao, destino, sessao, diario)
            except LeituraCancelada:
                log.warning("crédito outorgado cancelado a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. O que ficou pela metade não vale.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Crédito outorgado cancelado a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("crédito outorgado falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Crédito outorgado falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Abrindo os XML"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    xmls = caminhos_do_projeto(execucao.projeto_id, FONTES, sessao)
    filtro, guardar_descartados = filtro_do_projeto(execucao.projeto_id, sessao)
    total = contar_xml(xmls)
    execucao.arquivos_totais = total
    if filtro.sem_filtro:
        diario.anotar("aviso", "Rodada sem filtro: todos os itens saem na lista, marcados "
                               "\"SEM FILTRO\". Não é uma apuração de benefício.")
    else:
        diario.anotar("info", f"{milhar(total)} XML para varrer, com {len(filtro.termos)} termo(s) "
                              f"de descrição e {len(filtro.ncms)} NCM cadastrada(s).")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(p: ProgressoDoCredito) -> None:
        execucao.arquivos_lidos = p.arquivos_lidos
        execucao.bytes_lidos = p.bytes_lidos
        execucao.documentos = p.documentos
        execucao.fracao = p.fracao
        execucao.passo = f"Varrendo {milhar(p.arquivos_lidos)} de {milhar(total)}"
        diario.base["andamento"] = {"arquivos": p.arquivos_lidos, "elegiveis": p.elegiveis}
        diario.salvar_de_vez_em_quando()

    raiz = raiz_da_empresa(execucao.projeto_id, sessao)
    if not raiz:
        diario.anotar("aviso", "O trabalho não tem empresa com CNPJ: a varredura não vai "
                               "separar o que a empresa vendeu do que ela comprou.")
    progresso = varrer(xmls, destino, filtro, raiz_do_cnpj=raiz,
                       incluir_descartados=guardar_descartados,
                       avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = progresso.arquivos_lidos
    execucao.bytes_lidos = progresso.bytes_lidos
    execucao.documentos = progresso.documentos
    diario.base.update(serializar(progresso, filtro))
    diario.base["segundos"] = segundos
    diario.base["guardou_descartados"] = guardar_descartados
    if progresso.ilegiveis:
        diario.anotar("aviso", f"{milhar(progresso.ilegiveis)} XML não deram para abrir — "
                               "veja os avisos abaixo.")
    if progresso.nao_sao_saida:
        diario.anotar("info", f"{milhar(progresso.nao_sao_saida)} documento(s) ficaram de fora "
                              "por não serem saída desta empresa — compra, ou nota de outra "
                              "empresa que veio na mesma pasta.")
    if progresso.nao_autorizados:
        diario.anotar("aviso", f"{milhar(progresso.nao_autorizados)} nota(s) com protocolo de uso "
                               "denegado ficaram de fora: a operação não existiu.")
    if progresso.elegiveis == 0 and not filtro.sem_filtro:
        diario.anotar("aviso", "Nenhum item casou com os termos cadastrados. Confira a grafia — "
                               "a comparação é por pedaço da descrição, mas não ignora acento.")
    for aviso in progresso.exemplos_ilegiveis[:20]:
        diario.anotar("aviso", aviso)
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info",
                  f"Concluída em {duracao(segundos)}: {milhar(progresso.documentos)} documentos, "
                  f"{milhar(progresso.itens)} itens lidos e {milhar(progresso.elegiveis)} "
                  f"elegíveis ao benefício.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Crédito outorgado apurado · {milhar(progresso.elegiveis)} itens elegíveis de "
        f"{milhar(progresso.itens)}",
        dados={"execucao_id": execucao.id, "documentos": progresso.documentos,
               "itens": progresso.itens, "elegiveis": progresso.elegiveis,
               "centavos_elegiveis": progresso.centavos_elegiveis,
               "segundos": segundos}, autor_id=execucao.criada_por)
