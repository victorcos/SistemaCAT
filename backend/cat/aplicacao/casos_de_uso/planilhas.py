"""Gerar as planilhas de uma execução, a partir dos parquets dela.

Estava repetido nos dois roteadores de etapa; a API em C# passou a atender as
rotas (13/09/2026) e pede a planilha pelo canal interno. A regra de cache e o
motivo de cada recusa ficaram aqui, num lugar só.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cat.aplicacao.casos_de_uso import (
    apurar_periodo,
    apurar_suportado,
    conferir_documentos,
    extrair_movimentos,
    gerar_arquivo_digital,
    montar_razao,
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
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO, ARQUIVO_SALDOS
from cat.infraestrutura.analitico.arquivo_digital import ARQUIVO_ARQUIVOS, ARQUIVO_OCORRENCIAS
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
    gerar_inventario,
    gerar_itens,
    gerar_movimentos,
)
from cat.infraestrutura.planilhas.apuracao import gerar_apuracao, gerar_saldos
from cat.infraestrutura.planilhas.arquivo_digital import (
    gerar_arquivos,
    gerar_ocorrencias,
    zip_de_envio,
    zip_de_previas,
)
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
    },
    apurar_suportado.ETAPA: {
        "suportado": ("icms_suportado.xlsx", ARQUIVO_SUPORTADO, gerar_suportado),
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
}

NAO_TERMINOU = {
    conferir_documentos.ETAPA: "A conferência ainda não terminou.",
    extrair_movimentos.ETAPA: "A extração ainda não terminou.",
    apurar_suportado.ETAPA: "A apuração ainda não terminou.",
    montar_razao.ETAPA: "A montagem do razão ainda não terminou.",
    apurar_periodo.ETAPA: "A apuração do período ainda não terminou.",
    gerar_arquivo_digital.ETAPA: "A geração do arquivo digital ainda não terminou.",
}


class PlanilhaRecusada(Exception):
    def __init__(self, status: int, mensagem: str) -> None:
        self.status = status
        super().__init__(mensagem)


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
    if not os.path.isfile(origem):
        # os parquets são de disco local e podem ter sido limpos; a linha da
        # execução fica para sempre, o material de trabalho não. Ou a execução
        # é de antes de esta lista existir: a pasta está lá, a lista não.
        if etapa_da_rota == extrair_movimentos.ETAPA:
            raise PlanilhaRecusada(410, "Os arquivos desta extração não estão mais em disco. Rode de novo.")
        if etapa_da_rota in (apurar_suportado.ETAPA, montar_razao.ETAPA, apurar_periodo.ETAPA,
                             gerar_arquivo_digital.ETAPA):
            raise PlanilhaRecusada(410, "Os arquivos desta apuração não estão mais em disco. Rode de novo.")
        motivo = ("Esta conferência é de uma versão anterior e não tem esta lista."
                  if os.path.isdir(pasta) else "Os arquivos desta conferência não estão mais em disco.")
        raise PlanilhaRecusada(410, f"{motivo} Rode a conferência de novo.")

    # cada recorte vira arquivo próprio: sem isso, o primeiro download ficaria
    # em cache e o filtro seguinte devolveria a planilha errada. E o formato
    # entra no nome: sem isso o xlsx já gerado responderia ao pedido de csv.
    partes = sorted(escolhidos or ()) + sorted(classes or ())
    sufixo = "-" + "_".join(partes) if partes else ""
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
