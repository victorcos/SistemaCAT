"""A rodada das exclusões da base do PIS/COFINS.

São **quatro teses**, no mesmo parquet, separadas pela coluna `tese`:

- as **próprias contribuições fora da base**
  (`exclusoes/piscofins_na_propria_base.py`), somada do agregado da Gestão;
- o **ICMS fora da base** — o Tema 69, relatório 903;
- o **ICMS-ST fora da base** — relatório 839;
- o **ISS fora da base** — relatório 933.

As três últimas se apuram **item a item** (`analitico/exclusoes_por_item.py`), e
cada uma tem o seu parquet detalhado, a sua planilha e o seu bloco na tela. Elas
nunca são somadas num número só: são pedidos diferentes, com fundamentos
diferentes, e um total único esconderia isso de quem assina.

A do ICMS desmentiu uma previsão que estava escrita aqui: esperava-se precisar
da EFD ICMS/IPI para achar o ICMS destacado. Não precisa — o C170 da própria
EFD-Contribuições traz `VL_ICMS`, e foi de lá que saíram as 138.358 linhas que
batem 100% com o relatório do MA. Uma fonte a menos para exigir do cliente.

**As três por item não usam o agregado, e não têm como usar.** Elas se apuram no
item: a base recalculada se reconstrói do valor, do desconto, do rateio e do
imposto de cada item, e é assim que se sabe quais notas **já** excluíram — que
são justamente as que não podem entrar no pedido. Por isso, quando rodam, os
SPED são lidos mesmo havendo agregado. São quatro leituras do mesmo lote, e a
tela diz qual está andando.

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
from decimal import ROUND_HALF_UP, Decimal

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy.exc import SQLAlchemyError

from cat.dominio.piscofins import prescricao
from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido
from cat.infraestrutura import selic
from cat.infraestrutura.aliquotas import excecoes_de
from cat.infraestrutura.analitico import (
    exclusao_do_icms,
    exclusao_do_icms_st,
    exclusao_do_iss,
    exclusao_piscofins_na_base,
)
from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.sped.tabelas import tab_selic
from cat.infraestrutura.sped.tabelas.tab_selic import SelicDesconhecida
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

UM = Decimal(1)

# as cinco leituras que a etapa faz, na ordem. A primeira é a tese da receita
# consolidada (que pode sair do agregado); as quatro seguintes leem os SPED
# inteiros, porque a conta delas é no item e agregado não tem item.
#
# **A receita aparece duas vezes, e não é repetição**: são as duas frentes da
# mesma tese — a consolidada, que arredonda uma vez por grupo e é o número que
# se pede, e o detalhe por item nas 35 colunas do 680 do MA, que é o que
# acompanha o pedido. Ver `analitico/exclusao_piscofins_na_base.py`
FASE_DA_RECEITA = "receita"
FASE_DA_RECEITA_POR_ITEM = "receita_por_item"
FASE_DO_ICMS = "icms"
FASE_DO_ICMS_ST = "icms_st"
FASE_DO_ISS = "iss"
FASES = (FASE_DA_RECEITA, FASE_DA_RECEITA_POR_ITEM, FASE_DO_ICMS,
         FASE_DO_ICMS_ST, FASE_DO_ISS)


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
    # a Selic sobre o que volta, e o total com ela. **Em 01/10/2026 esta tese
    # não corrigia**: eram R$ 755.828,97 que o relatório do MA mostrava e o
    # nosso não. Ver DECISOES daquele dia
    selic: int = 0
    # o mês da restituição até onde a Selic acumulou, em "aaaa-mm". Número
    # corrigido sem a data da correção não se reconfere no mês seguinte
    ate: str = ""
    # o que cinco anos já levaram: mostrado, nunca somado ao crédito. **Já
    # corrigido**, como nas outras três — meio corrigido seria incoerente
    prescrito: int = 0
    competencias_prescritas: int = 0
    data_de_referencia: str = ""
    competencias: list[str] = field(default_factory=list)
    # uma linha por competência, que é o que a tela mostra sem baixar nada
    por_competencia: list[dict] = field(default_factory=list)
    # motivo -> quantas chaves do agregado não entraram na tese
    fora: dict[str, int] = field(default_factory=dict)
    # as quatro teses por item, já serializadas — vazias quando não deu para
    # apurá-las. Cada uma no seu canto, nunca somadas num número só: são
    # pedidos diferentes, com fundamentos diferentes.
    #
    # `receita_por_item` é a exceção que confirma a regra: não é um quinto
    # pedido, é **a mesma tese dos campos acima** vista item a item. Somá-la ao
    # que já está neste resumo seria pedir a tese 1 duas vezes
    receita_por_item: dict = field(default_factory=dict)
    icms: dict = field(default_factory=dict)
    icms_st: dict = field(default_factory=dict)
    iss: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    segundos: float = 0.0

    @property
    def diferenca(self) -> int:
        """O principal que volta: só o que ainda está no prazo, sem a Selic."""
        return self.diferenca_pis + self.diferenca_cofins

    @property
    def total_atualizado(self) -> int:
        """O que se pede: o principal no prazo, corrigido pela Selic."""
        return self.diferenca + self.selic


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "fonte": r.fonte, "arquivos": r.arquivos,
        "ilegiveis": r.ilegiveis, "grupos": r.grupos,
        "base": str(reais(r.base)), "excluido": str(reais(r.excluido)),
        "diferenca_pis": str(reais(r.diferenca_pis)),
        "diferenca_cofins": str(reais(r.diferenca_cofins)),
        "diferenca": str(reais(r.diferenca)),
        "selic": str(reais(r.selic)),
        "total_atualizado": str(reais(r.total_atualizado)),
        "ate": r.ate, "competencias": r.competencias,
        "prescrito": str(reais(r.prescrito)),
        "competencias_prescritas": r.competencias_prescritas,
        "data_de_referencia": r.data_de_referencia,
        "por_competencia": r.por_competencia,
        "fora": r.fora, "receita_por_item": r.receita_por_item,
        "icms": r.icms, "icms_st": r.icms_st, "iss": r.iss,
        "avisos": r.avisos, "segundos": r.segundos,
    }


def apurar(contribuicoes: list[str], destino: str, agregados_de: str | None = None,
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None, ate: str = "") -> Resumo:
    """Calcula as quatro teses e grava os parquets. Devolve o resumo.

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

    # a série vem do banco e serve às quatro teses. Buscá-la aqui, e não dentro
    # de cada uma, é o que garante que as quatro corrijam pelo mesmo número
    resumo.ate = ate or exclusao_do_icms.mes_de(referencia)
    mensal = selic.serie(resumo.ate)
    acumuladas, por_grupo, por_periodo = _corrigir(exclusao, mensal, resumo.ate, resumo)

    # o crédito soma só o que está no prazo; o resto vai à parte, e a tela o
    # mostra em vermelho. Somar os dois daria um número que ninguém pode pedir
    for competencia, total in exclusao.por_periodo().items():
        selic_pis, selic_cofins = por_periodo.get(competencia, (0, 0))
        if competencia in prescritas:
            resumo.prescrito += total.diferenca + selic_pis + selic_cofins
        else:
            resumo.diferenca_pis += total.diferenca_pis
            resumo.diferenca_cofins += total.diferenca_cofins
            resumo.selic += selic_pis + selic_cofins

    resumo.por_competencia = [
        {"competencia": competencia, "grupos": total.grupos,
         "prescrita": competencia in prescritas,
         "base": str(reais(total.base)), "excluido": str(reais(total.excluido)),
         "pis": str(reais(total.pis)), "cofins": str(reais(total.cofins)),
         "pis_novo": str(reais(total.pis_novo)),
         "cofins_novo": str(reais(total.cofins_novo)),
         "diferenca_pis": str(reais(total.diferenca_pis)),
         "diferenca_cofins": str(reais(total.diferenca_cofins)),
         "diferenca": str(reais(total.diferenca)),
         "selic_acumulada": str(acumuladas.get(competencia, "")),
         "selic": str(reais(sum(por_periodo.get(competencia, (0, 0))))),
         "total_atualizado": str(reais(
             total.diferenca + sum(por_periodo.get(competencia, (0, 0)))))}
        for competencia, total in exclusao.por_periodo().items()
    ]
    resumo.fora = exclusao.resumo.fora
    resumo.avisos.extend(exclusao.resumo.avisos)

    por_item = _apurar_por_item(contribuicoes, destino, resumo, avisar, deve_parar,
                                referencia, resumo.ate, mensal)

    _gravar(exclusao, os.path.join(destino, ARQUIVO_DAS_EXCLUSOES), prescritas,
            por_item, por_grupo)
    if avisar is not None:
        avisar(Andamento(arquivos=resumo.arquivos, grupos=resumo.grupos))

    resumo.segundos = round(time.time() - inicio, 1)
    log.info("exclusões apuradas", extra=serializar(resumo))
    return resumo


def _corrigir(exclusao, mensal: dict[str, Decimal], ate: str, resumo: Resumo):
    """A Selic sobre o que volta, **uma vez por grupo** — como a tese arredonda.

    Até 01/10/2026 esta tese não corrigia nada. O relatório 680 do MA, da mesma
    metodologia, trazia R$ 755.828,97 de Selic que o nosso não mostrava: o
    principal batia em 0,3% e faltava uma parcela inteira. Era lacuna tratada
    como característica — eu havia escrito no código que "esta tese não
    corrige", e o que o dado dizia é que ela precisava corrigir.

    **Por grupo, e não por competência**, porque é no grupo que esta tese
    arredonda (ver DECISOES de 24/09/2026): corrigir a soma da competência
    daria outro centavo, e os dois arredondamentos têm de morar no mesmo lugar.

    Série que não alcança o mês vira aviso e correção nenhuma — o principal
    continua valendo, e some só a parcela que não se sabe calcular.
    """
    acumuladas: dict[str, Decimal] = {}
    por_grupo: dict[object, tuple[int, int]] = {}
    por_periodo: dict[str, tuple[int, int]] = {}

    for grupo, a in exclusao.grupos.items():
        if not a.consistente:
            continue
        competencia = grupo.periodo
        if competencia not in acumuladas:
            try:
                acumuladas[competencia] = tab_selic.acumulada(competencia, ate, mensal)
            except SelicDesconhecida as erro:
                resumo.avisos.append(
                    f"As contribuições fora da base não foram corrigidas: {erro}")
                return {}, {}, {}
        acumulada = acumuladas[competencia]
        pis = _selic_em_centavos(a.diferenca_pis, acumulada)
        cofins = _selic_em_centavos(a.diferenca_cofins, acumulada)
        por_grupo[grupo] = (pis, cofins)
        antes = por_periodo.get(competencia, (0, 0))
        por_periodo[competencia] = (antes[0] + pis, antes[1] + cofins)

    return acumuladas, por_grupo, por_periodo


def _selic_em_centavos(valor: int, acumulada: Decimal) -> int:
    """A Selic sobre um valor em centavos. Esta tese anda em inteiro, não em reais."""
    return int((Decimal(valor) * acumulada / CEM).quantize(UM, rounding=ROUND_HALF_UP))


def _apurar_por_item(contribuicoes: list[str], destino: str, resumo: Resumo,
                     avisar: Callable[[Andamento], None] | None,
                     deve_parar: Callable[[], bool] | None,
                     referencia: date | None, ate: str,
                     mensal: dict[str, Decimal]) -> dict:
    """As quatro exclusões por item: a receita, o ICMS, o ICMS-ST e o ISS.

    **Leem os SPED mesmo havendo agregado**, porque não há como não ler: a conta
    das quatro é no item, e agregado não tem item. Sem EFD-Contribuições no lote
    não há nenhuma delas — e isso vira aviso, não erro: a tese da receita já
    rodou consolidada, e derrubá-la junto não ajudaria ninguém.

    Devolve `{nome da tese: resumo}` das que entram no parquet agregado — **o
    detalhe da receita não entra**, porque a tese dele já está lá consolidada.
    Ver `analitico/exclusao_piscofins_na_base.py`.
    """
    if not contribuicoes:
        resumo.avisos.append(
            "Sem EFD-Contribuições no lote, as exclusões por item — receita, ICMS, "
            "ICMS-ST e ISS — não foram apuradas: elas se calculam no item da nota, "
            "e agregado não tem item.")
        return {}

    # a série já veio pronta de `apurar`, que a usou também na tese da receita:
    # as quatro teses corrigem pelo mesmo número ou não corrigem nenhuma
    mes = ate

    # e se confere **antes** de ler, não no meio: uma série curta faria três
    # leituras inteiras para morrer no fim, e a tese da receita cairia junto
    if falta := exclusao_do_icms.avisar_se_a_selic_nao_alcanca(mes, mensal):
        resumo.avisos.append(
            f"As exclusões por item não foram apuradas. {falta}")
        return {}

    def andando(fase: str):
        def andou(a) -> None:
            if avisar is not None:
                avisar(Andamento(arquivos=a.arquivos, grupos=a.linhas, fase=fase))
        return andou

    comum = {"ate": ate, "deve_parar": deve_parar, "referencia": referencia,
             "mensal": mensal}
    try:
        da_receita = exclusao_piscofins_na_base.apurar(
            contribuicoes, destino, avisar=andando(FASE_DA_RECEITA_POR_ITEM),
            **comum)

        do_icms = exclusao_do_icms.apurar(
            contribuicoes, destino, avisar=andando(FASE_DO_ICMS), **comum)

        # a alíquota por produto que foge da regra do estado, dos
        # estabelecimentos que este lote tem. Ver `infraestrutura/aliquotas`
        excecoes = _excecoes_dos(do_icms.estabelecimentos)
        do_icms_st = exclusao_do_icms_st.apurar(
            contribuicoes, destino, avisar=andando(FASE_DO_ICMS_ST),
            excecoes=excecoes, **comum)

        do_iss = exclusao_do_iss.apurar(
            contribuicoes, destino, avisar=andando(FASE_DO_ISS), **comum)
    except LeituraCancelada as erro:
        # a etapa conhece o nome dela, não o da leitura
        raise ExclusaoCancelada("apuração das exclusões cancelada a pedido") from erro

    resumo.receita_por_item = exclusao_piscofins_na_base.serializar(da_receita)
    resumo.icms = exclusao_do_icms.serializar(do_icms)
    resumo.icms_st = exclusao_do_icms_st.serializar(do_icms_st)
    resumo.iss = exclusao_do_iss.serializar(do_iss)
    for resultado in (da_receita, do_icms, do_icms_st, do_iss):
        resumo.avisos.extend(resultado.avisos)

    # o detalhe da receita fica fora do agregado de propósito: ver o docstring
    return {
        exclusao_do_icms.TESE_ICMS_NA_BASE: do_icms,
        exclusao_do_icms_st.TESE_ICMS_ST_NA_BASE: do_icms_st,
        exclusao_do_iss.TESE_ISS_NA_BASE: do_iss,
    }


def _excecoes_dos(estabelecimentos: list[str]) -> dict:
    """A alíquota de exceção dos estabelecimentos do lote.

    Sessão curta e própria, como a da Selic: a tabela é cadastro do cliente, não
    é do projeto nem da rodada, e prendê-la à transação da etapa faria um
    `rollback` de lá desfazer uma leitura.

    Banco fora do ar não derruba a tese: sem exceção, a regra do estado responde
    por tudo — e ela acerta 98,66% das linhas medidas. O aviso fica no log.
    """
    if not estabelecimentos:
        return {}
    from cat.infraestrutura.repositorios.banco import Sessao  # noqa: PLC0415

    try:
        with Sessao() as sessao:
            return excecoes_de(sessao, estabelecimentos)
    except SQLAlchemyError as erro:
        log.warning("não deu para ler as alíquotas de exceção; vale a regra do estado",
                    extra={"erro": str(erro), "estabelecimentos": len(estabelecimentos)})
        return {}


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
    # inflada — aconteceu na base da empresa S, com R$ 203.600,56 a mais
    lidos, avisos = selecionar_por_competencia(lidos)
    resumo.avisos.extend(avisos)

    resumo.arquivos = len(lidos)
    if lidos:
        # o próximo cálculo — outra tese, ou esta de novo — não paga a leitura
        gravar_agregados(lidos, destino)
    return lidos


def _gravar(exclusao, caminho: str, prescritas: set[str], por_item=None,
            por_grupo=None) -> None:
    """Uma linha por grupo, das quatro teses. O parquet nasce mesmo sem nenhuma.

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
        selic_pis, selic_cofins = (por_grupo or {}).get(grupo, (0, 0))
        colunas["selic"].append(reais(selic_pis + selic_cofins))
        colunas["total_atualizado"].append(
            reais(a.diferenca_pis + a.diferenca_cofins + selic_pis + selic_cofins))

    for tese, resultado in (por_item or {}).items():
        _somar_por_item(colunas, tese, resultado)

    pq.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA), caminho)


def _somar_por_item(colunas: dict[str, list], tese: str, resultado) -> None:
    """As linhas de uma tese por item, na mesma unidade da tese da receita.

    Já vêm em reais do motor — que anda em `Decimal` de duas casas, não em
    centavos inteiros como o agregado da Gestão. Converter aqui seria converter
    duas vezes.
    """
    prescritas = {c["competencia"] for c in resultado.por_competencia if c["prescrita"]}
    for grupo, total in resultado.grupos.items():
        colunas["tese"].append(tese)
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
        # a base do STF é uma só: o imposto sai das duas bases do mesmo jeito
        colunas["base_nova_pis"].append(total.base_stf)
        colunas["base_nova_cofins"].append(total.base_stf)
        colunas["pis_novo"].append(total.pis_stf)
        colunas["cofins_novo"].append(total.cofins_stf)
        colunas["diferenca_pis"].append(total.diferenca_pis)
        colunas["diferenca_cofins"].append(total.diferenca_cofins)
        colunas["selic"].append(total.selic)
        colunas["total_atualizado"].append(total.total_atualizado)
