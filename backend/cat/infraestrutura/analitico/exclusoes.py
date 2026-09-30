"""A rodada das exclusões da base do PIS/COFINS.

São duas teses, no mesmo parquet, separadas pela coluna `tese`:

- as **próprias contribuições fora da base**
  (`exclusoes/piscofins_na_propria_base.py`), somada do agregado da Gestão;
- o **ICMS destacado fora da base** — o Tema 69
  (`analitico/exclusao_do_icms.py`), apurada item a item.

A segunda desmentiu uma previsão que estava escrita aqui: esperava-se precisar
da EFD ICMS/IPI para achar o ICMS destacado. Não precisa — o C170 da própria
EFD-Contribuições traz `VL_ICMS`, e foi de lá que saíram as 138.358 linhas que
batem 100% com o relatório do MA. Uma fonte a menos para exigir do cliente.

**A do ICMS não usa o agregado, e não tem como usar.** Ela se apura no item: a
base recalculada se reconstrói do valor, do desconto, do rateio do frete e do
ICMS de cada item, e é assim que se sabe quais notas **já** excluíram o ICMS —
que são justamente as que não podem entrar no pedido. Por isso, quando ela
roda, os SPED são lidos mesmo havendo agregado.

**De onde vêm os números, e por que isso importa no relógio.** Do agregado que
a Gestão deixou em disco: ler os 65 SPED desta casa custa uma hora, e o
agregado volta em segundos. Sem Gestão rodada, esta etapa lê os SPED ela mesma
— e grava o agregado na própria pasta, para que a próxima tese não pague de
novo. O resumo diz de onde veio, porque "demorou uma hora" e "demorou dez
segundos" são a mesma etapa com fontes diferentes, e quem acompanha merece
saber qual foi.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.piscofins import prescricao
from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido
from cat.infraestrutura.analitico import exclusao_do_icms
from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura import selic
from cat.infraestrutura.exclusoes.piscofins_na_propria_base import calcular
from cat.infraestrutura.gestao.agregador import agregar_efd
from cat.infraestrutura.gestao.agregados import gravar as gravar_agregados
from cat.infraestrutura.gestao.agregados import ler as ler_agregados
from cat.infraestrutura.gestao.montagem import selecionar_por_competencia
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DAS_EXCLUSOES = "exclusoes.parquet"

# a tese que esta rodada calcula. Vira coluna para que a segunda — o ICMS
# destacado — entre no mesmo parquet sem quebrar quem já lê este
TESE_PISCOFINS_NA_BASE = "piscofins_na_propria_base"

ESQUEMA = pa.schema([
    ("tese", pa.string()),
    ("cnpj", pa.string()),
    ("competencia", pa.string()),
    ("registro", pa.string()),
    ("cst", pa.string()),
    ("cfop", pa.string()),
    # fora do prazo de cinco anos: aparece no relatório, some do total
    ("prescrita", pa.bool_()),
    # em reais, como as demais tabelas analíticas desta casa — a conta anda em
    # centavos inteiros e converte só aqui, na saída, uma vez por grupo
    ("base", pa.decimal128(18, 2)),
    ("excluido", pa.decimal128(18, 2)),
    ("pis", pa.decimal128(18, 2)),
    ("cofins", pa.decimal128(18, 2)),
    ("base_nova_pis", pa.decimal128(18, 2)),
    ("base_nova_cofins", pa.decimal128(18, 2)),
    ("pis_novo", pa.decimal128(18, 2)),
    ("cofins_novo", pa.decimal128(18, 2)),
    ("diferenca_pis", pa.decimal128(18, 2)),
    ("diferenca_cofins", pa.decimal128(18, 2)),
    # a correção pela Selic, que só a tese do ICMS tem. Fica zerada na outra —
    # e zero aqui quer dizer "esta tese não corrige", não "não rendeu juros"
    ("selic", pa.decimal128(18, 2)),
    ("total_atualizado", pa.decimal128(18, 2)),
])

CEM = Decimal(100)
DUAS_CASAS = Decimal("0.01")

# o que se grava na coluna de correção de quem não corrige
SEM_CORRECAO = Decimal(0)

# as duas leituras que a etapa faz, na ordem
FASE_DA_RECEITA = "receita"
FASE_DO_ICMS = "icms"


def reais(centavos: int) -> Decimal:
    """Centavos inteiros viram reais com duas casas, sem passar por float."""
    return (Decimal(centavos) / CEM).quantize(DUAS_CASAS)


class ExclusaoCancelada(RuntimeError):
    """A rodada parou porque pediram para parar."""


@dataclass
class Andamento:
    arquivos: int = 0
    grupos: int = 0
    # qual tese está andando, para a tela não repetir "Lendo 3 de 57" duas
    # vezes sem dizer que são leituras diferentes
    fase: str = FASE_DA_RECEITA


@dataclass
class Resumo:
    """O que a rodada produziu — e de onde veio."""

    fonte: str = ""                # "agregados" ou "sped"
    arquivos: int = 0
    ilegiveis: int = 0
    grupos: int = 0
    base: int = 0
    excluido: int = 0
    diferenca_pis: int = 0
    diferenca_cofins: int = 0
    # o que cinco anos já levaram: mostrado, nunca somado ao crédito
    prescrito: int = 0
    competencias_prescritas: int = 0
    data_de_referencia: str = ""
    competencias: list[str] = field(default_factory=list)
    # uma linha por competência, que é o que a tela mostra sem baixar nada
    por_competencia: list[dict] = field(default_factory=list)
    # motivo -> quantas chaves do agregado não entraram na tese
    fora: dict[str, int] = field(default_factory=dict)
    # a segunda tese, já serializada — ou vazio quando não deu para apurá-la.
    # Ver `analitico/exclusao_do_icms.py`
    icms: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    segundos: float = 0.0

    @property
    def diferenca(self) -> int:
        """O crédito: só o que ainda está no prazo."""
        return self.diferenca_pis + self.diferenca_cofins


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "fonte": r.fonte, "arquivos": r.arquivos,
        "ilegiveis": r.ilegiveis, "grupos": r.grupos,
        "base": str(reais(r.base)), "excluido": str(reais(r.excluido)),
        "diferenca_pis": str(reais(r.diferenca_pis)),
        "diferenca_cofins": str(reais(r.diferenca_cofins)),
        "diferenca": str(reais(r.diferenca)), "competencias": r.competencias,
        "prescrito": str(reais(r.prescrito)),
        "competencias_prescritas": r.competencias_prescritas,
        "data_de_referencia": r.data_de_referencia,
        "por_competencia": r.por_competencia,
        "fora": r.fora, "icms": r.icms, "avisos": r.avisos, "segundos": r.segundos,
    }


def apurar(contribuicoes: list[str], destino: str, agregados_de: str | None = None,
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None, ate: str = "") -> Resumo:
    """Calcula as duas teses e grava os parquets. Devolve o resumo.

    `referencia` é a data do pedido, que decide o que os cinco anos já levaram.
    Sem ela, hoje — que é o certo para quem está montando o cálculo agora.

    `ate` é o mês da restituição, que decide até onde a Selic do Tema 69
    acumula. Sem ele, o mês de `referencia`.
    """
    inicio = time.time()
    referencia = referencia or date.today()
    os.makedirs(destino, exist_ok=True)
    resumo = Resumo()

    agregados = ler_agregados(agregados_de) if agregados_de else []
    if agregados:
        resumo.fonte = "agregados"
        resumo.arquivos = len(agregados)
        log.info("exclusões partindo do agregado da gestão", extra={
            "arquivos": resumo.arquivos, "de": os.path.basename(agregados_de or "")})
        if avisar is not None:
            avisar(Andamento(arquivos=resumo.arquivos))
    else:
        resumo.fonte = "sped"
        agregados = _ler_os_sped(contribuicoes, destino, resumo, avisar, deve_parar)

    exclusao = calcular(agregados)
    resumo.data_de_referencia = referencia.isoformat()
    prescritas = {c for c in exclusao.resumo.periodos if prescricao.prescrita(c, referencia)}
    resumo.grupos = exclusao.resumo.grupos
    resumo.base = exclusao.resumo.base
    resumo.excluido = exclusao.resumo.excluido
    resumo.competencias = exclusao.resumo.periodos
    resumo.competencias_prescritas = len(prescritas)
    # o crédito soma só o que está no prazo; o resto vai à parte, e a tela o
    # mostra em vermelho. Somar os dois daria um número que ninguém pode pedir
    for competencia, total in exclusao.por_periodo().items():
        if competencia in prescritas:
            resumo.prescrito += total.diferenca
        else:
            resumo.diferenca_pis += total.diferenca_pis
            resumo.diferenca_cofins += total.diferenca_cofins

    resumo.por_competencia = [
        {"competencia": competencia, "grupos": total.grupos,
         "prescrita": competencia in prescritas,
         "base": str(reais(total.base)), "excluido": str(reais(total.excluido)),
         "pis": str(reais(total.pis)), "cofins": str(reais(total.cofins)),
         "pis_novo": str(reais(total.pis_novo)),
         "cofins_novo": str(reais(total.cofins_novo)),
         "diferenca_pis": str(reais(total.diferenca_pis)),
         "diferenca_cofins": str(reais(total.diferenca_cofins)),
         "diferenca": str(reais(total.diferenca))}
        for competencia, total in exclusao.por_periodo().items()
    ]
    resumo.fora = exclusao.resumo.fora
    resumo.avisos.extend(exclusao.resumo.avisos)

    do_icms = _apurar_o_icms(contribuicoes, destino, resumo, avisar, deve_parar,
                             referencia, ate)

    _gravar(exclusao, os.path.join(destino, ARQUIVO_DAS_EXCLUSOES), prescritas, do_icms)
    if avisar is not None:
        avisar(Andamento(arquivos=resumo.arquivos, grupos=resumo.grupos))

    resumo.segundos = round(time.time() - inicio, 1)
    log.info("exclusões apuradas", extra=serializar(resumo))
    return resumo


def _apurar_o_icms(contribuicoes: list[str], destino: str, resumo: Resumo,
                   avisar: Callable[[Andamento], None] | None,
                   deve_parar: Callable[[], bool] | None,
                   referencia: date | None, ate: str):
    """O Tema 69, item a item. Devolve o resumo dela, ou None.

    **Lê os SPED mesmo havendo agregado**, porque não há como não ler: a conta
    é no item. Sem EFD-Contribuições no lote não há tese — e isso vira aviso,
    não erro: a outra tese já rodou, e derrubá-la junto não ajudaria ninguém.
    """
    if not contribuicoes:
        resumo.avisos.append(
            "Sem EFD-Contribuições no lote, o ICMS fora da base (Tema 69) não foi "
            "apurado: ele se calcula no item da nota, e agregado não tem item.")
        return None

    # a série vem do banco, que a guarda para sempre e só vai ao Banco Central
    # pelos meses que ainda faltam. Ver `infraestrutura/selic`
    mes = ate or exclusao_do_icms.mes_de(referencia or date.today())
    mensal = selic.serie(mes)

    # e se confere **antes** de ler, não no meio: uma série curta faria a
    # leitura inteira para morrer no fim, e a outra tese cairia junto
    if falta := exclusao_do_icms.avisar_se_a_selic_nao_alcanca(mes, mensal):
        resumo.avisos.append(f"O Tema 69 não foi apurado. {falta}")
        return None

    def andou(a: exclusao_do_icms.Andamento) -> None:
        if avisar is not None:
            avisar(Andamento(arquivos=a.arquivos, grupos=a.linhas, fase=FASE_DO_ICMS))

    try:
        do_icms = exclusao_do_icms.apurar(
            contribuicoes, destino, ate=ate, avisar=andou,
            deve_parar=deve_parar, referencia=referencia, mensal=mensal)
    except LeituraCancelada as erro:
        # a etapa conhece o nome dela, não o da leitura
        raise ExclusaoCancelada("apuração das exclusões cancelada a pedido") from erro

    resumo.icms = exclusao_do_icms.serializar(do_icms)
    resumo.avisos.extend(do_icms.avisos)
    return do_icms


def _ler_os_sped(contribuicoes: list[str], destino: str, resumo: Resumo,
                 avisar: Callable[[Andamento], None] | None,
                 deve_parar: Callable[[], bool] | None) -> list:
    """Sem agregado pronto, lê os arquivos — e deixa o agregado para a próxima."""
    lidos = []
    for i, caminho in enumerate(contribuicoes, start=1):
        if deve_parar is not None and deve_parar():
            raise ExclusaoCancelada("apuração das exclusões cancelada a pedido")
        try:
            lidos.append(agregar_efd(caminho))
        except (ArquivoNaoReconhecido, OSError, ValueError) as erro:
            resumo.ilegiveis += 1
            aviso = f"{os.path.basename(caminho)}: {erro}"
            resumo.avisos.append(aviso)
            log.warning("arquivo não lido na apuração das exclusões",
                        extra={"arquivo": os.path.basename(caminho), "erro": str(erro)})
        if avisar is not None:
            avisar(Andamento(arquivos=i))

    # um arquivo por competência, como a Gestão faz: a retificadora vence, e o
    # mesmo arquivo entregue duas vezes conta uma. Sem isto, um lote com a
    # original e a retificadora do mesmo mês somaria as duas e a tese sairia
    # inflada — aconteceu na base da CEMA, com R$ 203.600,56 a mais
    lidos, avisos = selecionar_por_competencia(lidos)
    resumo.avisos.extend(avisos)

    resumo.arquivos = len(lidos)
    if lidos:
        # o próximo cálculo — outra tese, ou esta de novo — não paga a leitura
        gravar_agregados(lidos, destino)
    return lidos


def _gravar(exclusao, caminho: str, prescritas: set[str], do_icms=None) -> None:
    """Uma linha por grupo, das duas teses. O parquet nasce mesmo sem nenhuma.

    Etapa que termina sem arquivo é etapa que a seguinte não distingue de etapa
    que não rodou.
    """
    colunas: dict[str, list] = {nome: [] for nome in ESQUEMA.names}
    for grupo, a in exclusao.grupos.items():
        if not a.consistente:
            continue
        colunas["tese"].append(TESE_PISCOFINS_NA_BASE)
        colunas["cnpj"].append(grupo.cnpj)
        colunas["competencia"].append(grupo.periodo)
        colunas["registro"].append(grupo.registro)
        colunas["cst"].append(grupo.cst)
        colunas["cfop"].append(grupo.cfop)
        colunas["prescrita"].append(grupo.periodo in prescritas)
        colunas["base"].append(reais(a.base))
        colunas["excluido"].append(reais(a.excluido))
        colunas["pis"].append(reais(a.pis))
        colunas["cofins"].append(reais(a.cofins))
        colunas["base_nova_pis"].append(reais(a.base_nova_pis))
        colunas["base_nova_cofins"].append(reais(a.base_nova_cofins))
        colunas["pis_novo"].append(reais(a.pis_novo))
        colunas["cofins_novo"].append(reais(a.cofins_novo))
        colunas["diferenca_pis"].append(reais(a.diferenca_pis))
        colunas["diferenca_cofins"].append(reais(a.diferenca_cofins))
        # a tese das contribuições não corrige por Selic: o zero aqui é a
        # ausência de correção, e não juros que deram zero
        colunas["selic"].append(SEM_CORRECAO)
        colunas["total_atualizado"].append(SEM_CORRECAO)

    if do_icms is not None:
        _somar_o_icms(colunas, do_icms)

    pq.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA), caminho)


def _somar_o_icms(colunas: dict[str, list], do_icms) -> None:
    """As linhas do Tema 69, na mesma unidade da outra tese.

    Já vêm em reais do motor — que anda em `Decimal` de duas casas, não em
    centavos inteiros como o agregado da Gestão. Converter aqui seria converter
    duas vezes.
    """
    prescritas = {c["competencia"] for c in do_icms.por_competencia if c["prescrita"]}
    for grupo, total in do_icms.grupos.items():
        colunas["tese"].append(exclusao_do_icms.TESE_ICMS_NA_BASE)
        colunas["cnpj"].append(grupo.cnpj)
        colunas["competencia"].append(grupo.competencia)
        colunas["registro"].append(grupo.registro)
        colunas["cst"].append(grupo.cst)
        colunas["cfop"].append(grupo.cfop)
        colunas["prescrita"].append(grupo.competencia in prescritas)
        colunas["base"].append(total.base)
        colunas["excluido"].append(total.excluido)
        colunas["pis"].append(total.pis)
        colunas["cofins"].append(total.cofins)
        # a base do STF é uma só: o ICMS sai das duas bases do mesmo jeito
        colunas["base_nova_pis"].append(total.base_stf)
        colunas["base_nova_cofins"].append(total.base_stf)
        colunas["pis_novo"].append(total.pis_stf)
        colunas["cofins_novo"].append(total.cofins_stf)
        colunas["diferenca_pis"].append(total.diferenca_pis)
        colunas["diferenca_cofins"].append(total.diferenca_cofins)
        colunas["selic"].append(total.selic)
        colunas["total_atualizado"].append(total.total_atualizado)
