"""Gerar as planilhas de uma execução, a partir dos parquets dela.

Estava repetido nos dois roteadores de etapa; a API em C# passou a atender as
rotas (13/09/2026) e pede a planilha pelo canal interno. A regra de cache e o
motivo de cada recusa ficaram aqui, num lugar só.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from dataclasses import dataclass

from cat.aplicacao.casos_de_uso import (
    apurar_contribuicoes,
    apurar_credito_outorgado,
    apurar_exclusoes,
    apurar_periodo,
    apurar_piscofins,
    apurar_suportado,
    conferir_documentos,
    extrair_movimentos,
    gerar_arquivo_digital,
    montar_entrega,
    montar_razao,
    pre_validar_arquivos,
    quebrar_sped,
    quebrar_xml,
)
from cat.infraestrutura.analitico.confronto import (
    ARQUIVO_CONFERIDOS,
    ARQUIVO_NAO_ESCRITURADAS,
    ARQUIVO_SEM_DOCUMENTO,
)
from cat.infraestrutura.analitico.movimentacao import (
    ARQUIVO_ANALITICO,
    ARQUIVO_ITENS,
    ARQUIVO_MOVIMENTOS,
)
from cat.infraestrutura.analitico.contingencia import ARQUIVO_CONTINGENCIA
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO, ARQUIVO_SALDOS
from cat.infraestrutura.analitico.arquivo_digital import ARQUIVO_ARQUIVOS, ARQUIVO_OCORRENCIAS
from cat.infraestrutura.analitico.entrega import ARQUIVO_PACOTE, ARQUIVO_RELATORIO
from cat.infraestrutura.analitico.pre_validacao_do_cliente import ARQUIVO_ARQUIVOS_DO_CLIENTE
from cat.infraestrutura.analitico.credito_outorgado import (
    ARQUIVO_DESCARTADOS,
    ARQUIVO_ELEGIVEIS,
)
from cat.infraestrutura.analitico.exclusao_do_icms import ARQUIVO_DA_EXCLUSAO_DO_ICMS
from cat.infraestrutura.analitico.exclusao_do_icms_st import ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST
from cat.infraestrutura.analitico.exclusao_do_iss import ARQUIVO_DA_EXCLUSAO_DO_ISS
from cat.infraestrutura.analitico.exclusao_piscofins_na_base import (
    ARQUIVO_DA_EXCLUSAO_PISCOFINS,
)
from cat.infraestrutura.analitico.exclusoes import ARQUIVO_DAS_EXCLUSOES
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML
from cat.infraestrutura.analitico.gestao import ARQUIVO_DOS_QUADROS
from cat.infraestrutura.analitico import consulta_de_saidas as saidas_na_tela
from cat.infraestrutura.analitico import registros_do_sped as extracao_de_registro
from cat.infraestrutura.analitico.piscofins import (
    ARQUIVO_DAS_ENTRADAS,
    ARQUIVO_DAS_SAIDAS,
    ARQUIVO_DO_RAZAO,
    fonte_do_razao,
)
from cat.infraestrutura.analitico.quebra_de_sped import (
    ARQUIVO_DAS_CONTAGENS,
    ARQUIVO_DOS_ARQUIVOS,
)
from cat.infraestrutura.analitico.razao import (
    ARQUIVO_CONFERENCIA_INVENTARIO,
    ARQUIVO_FICHA3,
    ARQUIVO_FICHAS,
)
from cat.infraestrutura.analitico.suportado import ARQUIVO_SUPORTADO
from cat.infraestrutura.planilhas.conferencia import (
    FORMATOS,
    gerar_conferidas,
    gerar_nao_escrituradas,
    gerar_sem_documento,
)
from cat.infraestrutura.planilhas.movimentacao import (
    gerar_analitico,
    gerar_contingencia,
    gerar_inventario,
    gerar_itens,
    gerar_movimentos,
)
from cat.infraestrutura.planilhas.apuracao import gerar_apuracao, gerar_saldos
from cat.infraestrutura.planilhas.arquivo_digital import (
    gerar_arquivos,
    gerar_arquivos_do_cliente,
    gerar_ocorrencias,
    zip_de_envio,
    zip_de_previas,
)
from cat.infraestrutura.planilhas.credito_outorgado import (
    gerar_descartados,
    gerar_elegiveis,
)
from cat.infraestrutura.planilhas.gestao import gerar_quadros
from cat.infraestrutura.planilhas.registros_do_sped import gerar_extracao
from cat.infraestrutura.planilhas.quebra_de_sped import (
    gerar_arquivos_quebrados,
    gerar_contagens,
    gerar_entradas,
    gerar_razao_contabil,
    gerar_saidas,
)
from cat.infraestrutura.planilhas.exclusao_do_icms import gerar_exclusao_do_icms
from cat.infraestrutura.planilhas.exclusao_do_icms_st import gerar_exclusao_do_icms_st
from cat.infraestrutura.planilhas.exclusao_do_iss import gerar_exclusao_do_iss
from cat.infraestrutura.planilhas.exclusao_piscofins_na_base import (
    gerar_exclusao_piscofins,
)
from cat.infraestrutura.planilhas.exclusoes import gerar_exclusoes
from cat.infraestrutura.planilhas.pacote_das_exclusoes import zip_das_exclusoes
from cat.infraestrutura.planilhas.itens_do_xml import gerar_itens_do_xml
from cat.infraestrutura.planilhas.razao import gerar_conferencia, gerar_ficha3, gerar_fichas
from cat.infraestrutura.planilhas.suportado import gerar_suportado
from cat.infraestrutura.repositorios.modelos import ExecucaoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

# o que o navegador recebe. CSV vai com charset declarado: sem isso o Excel
# ignora o BOM em algumas versões e o acento se perde no caminho
TIPOS = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
    "zip": "application/zip",
}

# nome do arquivo que o usuário recebe, e do que fica em cache na execução
PLANILHAS = {
    conferir_documentos.ETAPA: {
        "nao-escrituradas": ("notas_nao_escrituradas.xlsx", ARQUIVO_NAO_ESCRITURADAS, gerar_nao_escrituradas),
        "a-cobrar": ("notas_a_cobrar.xlsx", ARQUIVO_SEM_DOCUMENTO, gerar_sem_documento),
        "conferidas": ("notas_conferidas.xlsx", ARQUIVO_CONFERIDOS, gerar_conferidas),
    },
    extrair_movimentos.ETAPA: {
        "movimentos": ("movimentos.xlsx", ARQUIVO_MOVIMENTOS, gerar_movimentos),
        "itens": ("itens.xlsx", ARQUIVO_ITENS, gerar_itens),
        "inventario": ("inventario.xlsx", ARQUIVO_INVENTARIO, gerar_inventario),
        "analitico": ("analitico.xlsx", ARQUIVO_ANALITICO, gerar_analitico),
        "contingencia": ("contingencia_nao_escrituradas.xlsx", ARQUIVO_CONTINGENCIA, gerar_contingencia),
    },
    apurar_suportado.ETAPA: {
        "suportado": ("icms_suportado.xlsx", ARQUIVO_SUPORTADO, gerar_suportado),
    },
    quebrar_sped.ETAPA: {
        # o que a quebra entrega: o que foi lido e o que há dentro de cada um
        "arquivos": ("sped_quebrados.xlsx", ARQUIVO_DOS_ARQUIVOS, gerar_arquivos_quebrados),
        "contagens": ("registros_por_arquivo.xlsx", ARQUIVO_DAS_CONTAGENS, gerar_contagens),
    },
    apurar_piscofins.ETAPA: {
        # o par que se confronta: o fiscal de um lado, o contábil do outro
        "entradas": ("consulta_de_entradas.xlsx", ARQUIVO_DAS_ENTRADAS, gerar_entradas),
        "saidas": ("consulta_de_saidas.xlsx", ARQUIVO_DAS_SAIDAS, gerar_saidas),
        "razao-contabil": ("razao_contabil.xlsx", ARQUIVO_DO_RAZAO, gerar_razao_contabil),
    },
    quebrar_xml.ETAPA: {
        # uma linha por item, com as colunas que a tela escolher
        "itens": ("itens_do_xml.xlsx", ARQUIVO_ITENS_DO_XML, gerar_itens_do_xml),
    },
    apurar_exclusoes.ETAPA: {
        # uma linha por grupo, das duas teses: somar a coluna da diferença dá o
        # total da tela
        "exclusoes": ("exclusoes.xlsx", ARQUIVO_DAS_EXCLUSOES, gerar_exclusoes),
        # e cada tese por item no seu canto, no formato em que o cliente confere
        # contra o escritório anterior: o 680, o 903, o 839 e o 933
        "receita-por-item": ("exclusao_piscofins_na_base.xlsx",
                             ARQUIVO_DA_EXCLUSAO_PISCOFINS, gerar_exclusao_piscofins),
        "icms": ("exclusao_do_icms.xlsx", ARQUIVO_DA_EXCLUSAO_DO_ICMS,
                 gerar_exclusao_do_icms),
        "icms-st": ("exclusao_do_icms_st.xlsx", ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST,
                    gerar_exclusao_do_icms_st),
        "iss": ("exclusao_do_iss.xlsx", ARQUIVO_DA_EXCLUSAO_DO_ISS,
                gerar_exclusao_do_iss),
        # e o pacote: as cinco de uma vez, do mesmo instante e do mesmo recorte.
        # Cinco downloads em cinco cliques são cinco chances de misturar rodadas
        "pacote": ("exclusoes_da_base.zip", ARQUIVO_DAS_EXCLUSOES, zip_das_exclusoes),
    },
    apurar_contribuicoes.ETAPA: {
        # uma planilha só: os quadros dos quatro tributos, uma aba cada, no
        # formato largo do MA — que é o que `tools/validar_gestao.py` compara
        "quadros": ("gestao_fiscal.xlsx", ARQUIVO_DOS_QUADROS, gerar_quadros),
    },
    apurar_credito_outorgado.ETAPA: {
        # o que entra no benefício e, quando o trabalho pediu para guardar, o
        # que ficou de fora — as duas com as mesmas colunas, para se comparar
        "elegiveis": ("credito_outorgado.xlsx", ARQUIVO_ELEGIVEIS, gerar_elegiveis),
        "descartados": ("credito_outorgado_descartados.xlsx", ARQUIVO_DESCARTADOS, gerar_descartados),
    },
    montar_razao.ETAPA: {
        "ficha3": ("ficha3.xlsx", ARQUIVO_FICHA3, gerar_ficha3),
        "fichas": ("fichas.xlsx", ARQUIVO_FICHAS, gerar_fichas),
        "conferencia": ("conferencia_inventario.xlsx", ARQUIVO_CONFERENCIA_INVENTARIO, gerar_conferencia),
    },
    apurar_periodo.ETAPA: {
        "apuracao": ("apuracao_do_periodo.xlsx", ARQUIVO_APURACAO, gerar_apuracao),
        "saldos": ("saldos_1050.xlsx", ARQUIVO_SALDOS, gerar_saldos),
    },
    gerar_arquivo_digital.ETAPA: {
        "arquivos": ("arquivos_digitais.xlsx", ARQUIVO_ARQUIVOS, gerar_arquivos),
        "ocorrencias": ("pre_validacao.xlsx", ARQUIVO_OCORRENCIAS, gerar_ocorrencias),
        # os TXT em zip: um para a SEFAZ, outro para as prévias, que nunca se misturam
        "envio": ("arquivos_para_envio.zip", ARQUIVO_ARQUIVOS, zip_de_envio),
        "previas": ("previas.zip", ARQUIVO_ARQUIVOS, zip_de_previas),
    },
    pre_validar_arquivos.ETAPA: {
        "arquivos": ("arquivos_do_cliente.xlsx", ARQUIVO_ARQUIVOS_DO_CLIENTE, gerar_arquivos_do_cliente),
        "ocorrencias": ("pre_validacao_do_cliente.xlsx", ARQUIVO_OCORRENCIAS, gerar_ocorrencias),
    },
    # montados na rodada, não a pedido: o download serve o que a entrega escreveu
    montar_entrega.ETAPA: {
        "relatorio": (ARQUIVO_RELATORIO, ARQUIVO_RELATORIO, lambda *a, **k: _ja_montado()),
        "pacote": (ARQUIVO_PACOTE, ARQUIVO_PACOTE, lambda *a, **k: _ja_montado()),
    },
}

NAO_TERMINOU = {
    conferir_documentos.ETAPA: "A conferência ainda não terminou.",
    extrair_movimentos.ETAPA: "A extração ainda não terminou.",
    apurar_suportado.ETAPA: "A apuração ainda não terminou.",
    montar_razao.ETAPA: "A montagem do razão ainda não terminou.",
    quebrar_sped.ETAPA: "A quebra dos SPED ainda não terminou.",
    apurar_credito_outorgado.ETAPA: "A apuração do crédito outorgado ainda não terminou.",
    apurar_piscofins.ETAPA: "A apuração de PIS/COFINS ainda não terminou.",
    apurar_contribuicoes.ETAPA: "A apuração das contribuições ainda não terminou.",
    apurar_periodo.ETAPA: "A apuração do período ainda não terminou.",
    gerar_arquivo_digital.ETAPA: "A geração do arquivo digital ainda não terminou.",
    pre_validar_arquivos.ETAPA: "A pré-validação ainda não terminou.",
    montar_entrega.ETAPA: "A montagem da entrega ainda não terminou.",
    apurar_exclusoes.ETAPA: "A apuração das exclusões ainda não terminou.",
    quebrar_xml.ETAPA: "A quebra dos XML ainda não terminou.",
}


# o caminho inteiro precisa caber em 260 caracteres no Windows, e a pasta da
# execução já come boa parte
LIMITE_DO_SUFIXO = 60


class PlanilhaRecusada(Exception):
    def __init__(self, status: int, mensagem: str) -> None:
        self.status = status
        super().__init__(mensagem)


def sufixo_do_recorte(escolhidos: frozenset[str] | None,
                      classes: frozenset[str] | None) -> str:
    """O pedaço do nome do arquivo que identifica o recorte pedido.

    Cada recorte precisa de arquivo próprio: sem isso o primeiro download
    ficaria em cache e o filtro seguinte devolveria a planilha errada — quem
    confere a conta 4.1.1 receberia a 3.1.1 de volta, com o nome certo.

    Recorte grande — dezenas de contas do razão — daria nome maior do que o
    Windows aceita (260 caracteres com a pasta da execução), e a gravação
    morreria no meio do download. Nesses casos entra o resumo: continua sendo
    a mesma seleção que gera o mesmo nome, que é o que o cache precisa.

    A ordem não conta: marcar 3.1.1 e depois 4.1.1 é a mesma seleção que o
    contrário, e gerar duas vezes o mesmo arquivo seria desperdício.
    """
    partes = sorted(escolhidos or ()) + sorted(classes or ())
    if not partes:
        return ""
    junto = "_".join(partes)
    if len(junto) > LIMITE_DO_SUFIXO:
        return "-" + hashlib.sha1(junto.encode("utf-8")).hexdigest()[:12]
    return "-" + junto


def _ja_montado() -> int:
    """Só chega aqui o pedido em outro formato: o arquivo pronto é servido sem gerar."""
    raise PlanilhaRecusada(404, "Este arquivo da entrega só sai no formato em que foi montado.")


@dataclass(frozen=True)
class PlanilhaPronta:
    caminho: str
    nome: str
    tipo: str


def gerar(execucao: ExecucaoDB, etapa_da_rota: str, qual: str,
          modelos: str | None, classificacoes: str | None, formato: str) -> PlanilhaPronta:
    """Gera (ou reaproveita) a planilha e diz onde ela está.

    `etapa_da_rota` é a etapa pela qual a tela pediu: a lista de planilhas e a
    mensagem de "ainda não terminou" são dela, não da execução.
    """
    catalogo = PLANILHAS.get(etapa_da_rota, {})
    if qual not in catalogo:
        raise PlanilhaRecusada(404, "Planilha desconhecida.")
    if formato not in (*FORMATOS, "zip"):
        raise PlanilhaRecusada(404, f"Formato desconhecido: {formato}. Vale xlsx ou csv.")
    if execucao.situacao != "concluida":
        raise PlanilhaRecusada(409, NAO_TERMINOU[etapa_da_rota])

    nome, parquet, gerador = catalogo[qual]
    # o zip não tem par em csv: o formato é o do próprio arquivo
    if nome.endswith(".zip"):
        formato = "zip"
    elif formato == "zip":
        raise PlanilhaRecusada(404, "Esta lista não sai em zip. Vale xlsx ou csv.")
    escolhidos = conjunto(modelos)
    classes = conjunto(classificacoes)
    pasta = execucao.pasta_de_trabalho or ""
    origem = os.path.join(pasta, parquet)
    if parquet == ARQUIVO_DO_RAZAO:
        # o razão é o único que pode ser uma pasta de partes: as ECD são lidas
        # em paralelo desde 07/10/2026, uma parte por arquivo. `fonte_do_razao`
        # devolve a forma que esta execução gravou — a antiga ou a nova
        origem = fonte_do_razao(pasta) or origem
    if not (os.path.isfile(origem) or "*" in origem):
        # os parquets são de disco local e podem ter sido limpos; a linha da
        # execução fica para sempre, o material de trabalho não. Ou a execução
        # é de antes de esta lista existir: a pasta está lá, a lista não.
        if etapa_da_rota == extrair_movimentos.ETAPA:
            raise PlanilhaRecusada(410, "Os arquivos desta extração não estão mais em disco. Rode de novo.")
        # o descartado é opcional, e a rodada pode simplesmente não tê-lo
        # guardado. Dizer "não está mais em disco" mandaria procurar um arquivo
        # que nunca existiu
        if etapa_da_rota == apurar_credito_outorgado.ETAPA and qual == "descartados" \
                and os.path.isdir(pasta):
            raise PlanilhaRecusada(
                410, "Esta rodada não guardou os itens descartados. Ligue \"guardar os "
                     "descartados\" no filtro e rode de novo.")
        if etapa_da_rota in (apurar_suportado.ETAPA, montar_razao.ETAPA, apurar_periodo.ETAPA,
                             gerar_arquivo_digital.ETAPA, pre_validar_arquivos.ETAPA, montar_entrega.ETAPA,
                             quebrar_sped.ETAPA, apurar_credito_outorgado.ETAPA):
            raise PlanilhaRecusada(410, "Os arquivos desta apuração não estão mais em disco. Rode de novo.")
        motivo = ("Esta conferência é de uma versão anterior e não tem esta lista."
                  if os.path.isdir(pasta) else "Os arquivos desta conferência não estão mais em disco.")
        raise PlanilhaRecusada(410, f"{motivo} Rode a conferência de novo.")

    # cada recorte vira arquivo próprio: sem isso, o primeiro download ficaria
    # em cache e o filtro seguinte devolveria a planilha errada. E o formato
    # entra no nome: sem isso o xlsx já gerado responderia ao pedido de csv.
    sufixo = sufixo_do_recorte(escolhidos, classes)
    raiz, _ = os.path.splitext(nome)
    destino = os.path.join(pasta, f"{raiz}{sufixo}.{formato}")
    if precisa_gerar(destino, origem):
        with contexto(etapa=etapa_da_rota, execucao_id=execucao.id, planilha=qual):
            linhas = gerador(origem, destino, escolhidos, classes, formato=formato)
            log.info("planilha gerada",
                     extra={"planilha": qual, "linhas": linhas, "formato": formato,
                            "modelos": sorted(escolhidos) if escolhidos else "todos",
                            "classificacoes": sorted(classes) if classes else "todas"})
    return PlanilhaPronta(caminho=destino, nome=os.path.basename(destino), tipo=TIPOS[formato])


def conjunto(bruto: str | None) -> frozenset[str] | None:
    """"55,65" vira o conjunto; vazio significa todos."""
    if not bruto:
        return None
    escolhidos = {m.strip() for m in bruto.split(",") if m.strip()}
    return frozenset(escolhidos) or None


def precisa_gerar(planilha: str, parquet: str) -> bool:
    """A planilha em cache só vale se for mais nova que o dado que a originou.

    Guardar por nome e nunca conferir a idade servia planilha velha depois de a
    conferência rodar de novo: um download real veio com o conteúdo de uma
    execução anterior, e o número na tela não batia com o do arquivo.
    """
    if not os.path.isfile(planilha):
        return True
    try:
        return os.path.getmtime(planilha) < os.path.getmtime(parquet)
    except OSError:
        return True


# ---------------------------------------------------------------------------
# a extração de registro: fora do catálogo, e por quê
# ---------------------------------------------------------------------------
def extrair_registro(execucao: ExecucaoDB, alvo: str, formato: str,
                     recorte: extracao_de_registro.Recorte | None = None) -> PlanilhaPronta:
    """Extrai um registro (ou uma hierarquia) da quebra e devolve a planilha.

    Não entra em `PLANILHAS` porque a lista dali é fixa por etapa, e aqui o
    parquet e as colunas mudam com o alvo: seriam cinquenta e duas entradas de
    registro mais dezenove de hierarquia, todas iguais menos o nome.

    **O parquet é reaproveitado**, como as outras planilhas: extrair de novo 59
    arquivos a cada clique no botão de baixar seria minutos de espera para
    entregar o mesmo arquivo. A idade é medida contra o que a quebra deixou —
    quebra nova, extração nova.
    """
    pasta = execucao.pasta_de_trabalho or ""
    if not os.path.isdir(pasta):
        raise PlanilhaRecusada(
            410, "Os arquivos desta quebra não estão mais em disco. Rode a quebra de novo.")

    origem_da_quebra = os.path.join(pasta, ARQUIVO_DOS_ARQUIVOS)
    limpo = alvo.strip().upper()
    recorte = recorte or extracao_de_registro.Recorte()
    # o parquet e a planilha carregam a marca do recorte: sem ela, pedir o C170
    # de um CNPJ e depois o de outro serviria o primeiro arquivo para o segundo
    marca = extracao_de_registro.impressao_do_recorte(recorte)
    base = limpo.replace("+", "_") + marca
    parquet = os.path.join(pasta, extracao_de_registro.ARQUIVO_DA_EXTRACAO.format(alvo=base))
    if precisa_gerar(parquet, origem_da_quebra):
        with contexto(etapa="quebra_de_sped", execucao_id=execucao.id, alvo=limpo):
            extracao_de_registro.extrair(pasta, limpo, recorte)

    nome = f"sped_{base}.{formato}"
    destino = os.path.join(pasta, nome)
    if precisa_gerar(destino, parquet):
        with contexto(etapa="quebra_de_sped", execucao_id=execucao.id, alvo=limpo):
            linhas = gerar_extracao(parquet, destino, formato=formato, alvo=limpo)
            log.info("planilha de registro gerada",
                     extra={"alvo": limpo, "linhas": linhas, "formato": formato})
    return PlanilhaPronta(caminho=destino, nome=nome, tipo=TIPOS[formato])


def baixar_saidas(execucao: ExecucaoDB, formato: str,
                  recorte: saidas_na_tela.Recorte | None = None) -> PlanilhaPronta:
    """A 047 recortada como a tela está mostrando.

    A planilha do catálogo sai inteira, e inteira são 7,8 milhões de linhas num
    cliente de cinco anos — que o Excel não abre e que ninguém pediu. Quem está
    olhando uma competência na tela quer **aquela** competência no arquivo.

    Sem recorte, o nome e o caminho são os mesmos da planilha do catálogo: é o
    mesmo conteúdo, e gerar duas vezes o mesmo arquivo com dois nomes só faria
    a pasta crescer e a pessoa duvidar de qual é qual.
    """
    if formato not in FORMATOS:
        raise PlanilhaRecusada(404, f"Formato desconhecido: {formato}. Vale xlsx ou csv.")
    if execucao.situacao != "concluida":
        raise PlanilhaRecusada(409, NAO_TERMINOU[apurar_piscofins.ETAPA])
    pasta = execucao.pasta_de_trabalho or ""
    if not os.path.isdir(pasta):
        raise PlanilhaRecusada(
            410, "Os arquivos desta apuração não estão mais em disco. Rode de novo.")

    recorte = recorte or saidas_na_tela.RECORTE_INTEIRO
    try:
        parquet = saidas_na_tela.parquet_do_recorte(pasta, recorte)
    except saidas_na_tela.SaidasNaoGeradas as erro:
        raise PlanilhaRecusada(410, str(erro)) from erro

    nome = f"consulta_de_saidas{saidas_na_tela.impressao_do_recorte(recorte)}.{formato}"
    destino = os.path.join(pasta, nome)
    if precisa_gerar(destino, parquet):
        with contexto(etapa=apurar_piscofins.ETAPA, execucao_id=execucao.id,
                      planilha="saidas"):
            linhas = gerar_saidas(parquet, destino, formato=formato)
            log.info("planilha da 047 gerada", extra={
                "linhas": linhas, "formato": formato,
                "filtros": recorte.quantos_filtros})
    return PlanilhaPronta(caminho=destino, nome=nome, tipo=TIPOS[formato])


# quantos alvos cabem num pedido de lote. Não é regra fiscal: é o que impede
# um "marcar todos" de virar uma extração de setenta planilhas que ninguém
# pediu de verdade — e que levaria a tarde
LIMITE_DO_LOTE = 25


def extrair_registros_em_zip(execucao: ExecucaoDB, alvos: list[str], formato: str,
                             recorte: extracao_de_registro.Recorte | None = None) -> PlanilhaPronta:
    """Vários alvos de uma vez, num zip.

    **Por que zip e não vários downloads.** Baixar sete planilhas seguidas abre
    sete caixas de "onde salvar", e quem marcou sete registros quer uma pasta,
    não sete perguntas. É o mesmo motivo do pacote da entrega.

    Cada alvo reaproveita o cache de sempre: extrair o C170 sozinho e depois
    marcá-lo num lote não relê o arquivo.
    """
    if not alvos:
        raise PlanilhaRecusada(422, "Marque ao menos um registro para extrair.")
    if len(alvos) > LIMITE_DO_LOTE:
        raise PlanilhaRecusada(
            422, f"São {len(alvos)} registros de uma vez, e o limite é {LIMITE_DO_LOTE}. "
                 "Marque menos, ou extraia em duas levas.")

    pasta = execucao.pasta_de_trabalho or ""
    prontas = [extrair_registro(execucao, alvo, formato, recorte) for alvo in alvos]

    marca = extracao_de_registro.impressao_do_recorte(
        recorte or extracao_de_registro.Recorte())
    nome = f"sped_extracoes{marca}.zip"
    destino = os.path.join(pasta, nome)
    provisorio = f"{destino}.{os.getpid()}.tmp"
    with zipfile.ZipFile(provisorio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for pronta in prontas:
            z.write(pronta.caminho, arcname=pronta.nome)
    os.replace(provisorio, destino)

    log.info("extrações empacotadas", extra={
        "execucao_id": execucao.id, "alvos": len(prontas), "formato": formato,
        "zip": os.path.basename(destino)})
    return PlanilhaPronta(caminho=destino, nome=nome, tipo=TIPOS["zip"])
