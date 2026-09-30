"""A tese do ICMS fora da base do PIS/COFINS — o Tema 69, item a item.

O que sai daqui é o relatório 903: uma linha por **item de nota fiscal**, com a
base como foi escriturada, a base sem o ICMS, a diferença de cada contribuição,
a Selic acumulada e o total a recuperar corrigido. Quarenta colunas, medidas
contra o relatório do MA e batendo 100% nas 138.358 linhas da DMINAS.

## Por que esta tese não usa o agregado

A outra tese desta etapa — as contribuições fora da própria base — parte do
agregado que a Gestão deixou: somas por competência, CST e CFOP, que voltam em
segundos. Esta **não pode**: o Tema 69 se apura no item, porque a base
recalculada se reconstrói do valor do item, do desconto, do rateio do frete e
do ICMS destacado. Agregado não tem item; tem soma de item. Quem soma primeiro
e exclui depois não consegue dizer quais notas **já** excluíram o ICMS — e é
justamente essa a linha que não pode entrar no pedido.

Ler os SPED custa cerca de um minuto por ano de arquivo nesta casa. É barato
perto de pedir restituição em duplicidade.

## O mês da restituição

A correção pela Selic cresce a cada mês que passa, então o número só existe com
uma data ao lado. `ate` é o mês em que se pretende restituir; sem ele, o mês de
`referencia` — que é hoje, para quem está montando o cálculo agora. O resumo
diz qual foi usado, e a planilha e a tela repetem: número corrigido sem a data
da correção é número que ninguém consegue conferir no mês seguinte.

## O que prescreveu aparece

Como na outra tese: a competência que os cinco anos levaram sai no relatório,
marcada, e fora da soma do crédito. Ver `dominio/piscofins/prescricao.py`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from cat.dominio.piscofins import prescricao
from cat.infraestrutura.analitico.escrita import Escritor, parar_se_pedirem
from cat.infraestrutura.sped.exclusao_do_icms import (
    colunas_da_exclusao,
    exclusoes_do_icms,
)
from cat.infraestrutura.sped.leitor import codificacao_de
from cat.infraestrutura.sped.tabelas.tab_selic import alcanca, ultimo_mes
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DA_EXCLUSAO_DO_ICMS = "exclusao_do_icms.parquet"

# o nome da tese no parquet agregado das exclusões, ao lado da outra
TESE_ICMS_NA_BASE = "icms_na_base"

# de onde saem todas as linhas do 903: o item da nota fiscal. A coluna existe
# porque a outra tese lê vários registros, e as duas dividem o mesmo parquet
REGISTRO = "C170"

ZERO = Decimal(0)


def mes_de(referencia: date) -> str:
    """O mês da restituição, em "aaaa-mm"."""
    return referencia.strftime("%Y-%m")


def competencia_de(periodo: str) -> str:
    """"01/10/2022" -> "2022-10". O motor escreve como o relatório mostra."""
    partes = (periodo or "").split("/")
    return f"{partes[2]}-{partes[1]}" if len(partes) == 3 else ""


@dataclass
class Andamento:
    arquivos: int = 0
    linhas: int = 0


@dataclass(frozen=True)
class Grupo:
    """Onde a soma agregada mora: estabelecimento, mês, CST e CFOP.

    Congelado porque é chave de dicionário — `@dataclass` sem `frozen` anula o
    `__hash__` e o erro só aparece na primeira linha somada.
    """

    cnpj: str
    competencia: str
    registro: str
    cst: str
    cfop: str


@dataclass
class Total:
    """Uma soma — em Decimal, que é como a conta anda aqui.

    Serve às duas agregações: por competência, que é o que a tela mostra, e por
    grupo, que é o que entra no parquet ao lado da outra tese.
    """

    linhas: int = 0
    base: Decimal = ZERO
    icms_excluido: Decimal = ZERO
    pis: Decimal = ZERO
    cofins: Decimal = ZERO
    base_stf: Decimal = ZERO
    pis_stf: Decimal = ZERO
    cofins_stf: Decimal = ZERO
    diferenca_pis: Decimal = ZERO
    diferenca_cofins: Decimal = ZERO
    selic: Decimal = ZERO
    total_atualizado: Decimal = ZERO
    # a acumulada aplicada aqui: uma só por competência, por construção
    selic_acumulada: str = ""

    def somar(self, linha) -> None:
        self.linhas += 1
        self.base += Decimal(linha.base or 0)
        self.icms_excluido += Decimal(linha.diferenca_da_base or 0)
        self.pis += Decimal(linha.pis or 0)
        self.cofins += Decimal(linha.cofins or 0)
        self.base_stf += Decimal(linha.base_stf or 0)
        self.pis_stf += Decimal(linha.pis_stf or 0)
        self.cofins_stf += Decimal(linha.cofins_stf or 0)
        self.diferenca_pis += Decimal(linha.diferenca_do_pis or 0)
        self.diferenca_cofins += Decimal(linha.diferenca_da_cofins or 0)
        self.selic += (Decimal(linha.selic_sobre_o_pis or 0)
                       + Decimal(linha.selic_sobre_a_cofins or 0))
        self.total_atualizado += Decimal(linha.total_a_recuperar_atualizado or 0)
        self.selic_acumulada = linha.selic_acumulada


@dataclass
class Resumo:
    """O que a tese produziu, para a tela, a planilha e o histórico."""

    ate: str = ""
    arquivos: int = 0
    ilegiveis: int = 0
    linhas: int = 0
    itens_lidos: int = 0
    estabelecimentos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    base: Decimal = ZERO
    icms_excluido: Decimal = ZERO
    diferenca_pis: Decimal = ZERO
    diferenca_cofins: Decimal = ZERO
    selic: Decimal = ZERO
    total_atualizado: Decimal = ZERO
    # o que cinco anos já levaram: mostrado, nunca somado ao crédito
    prescrito: Decimal = ZERO
    competencias_prescritas: int = 0
    data_de_referencia: str = ""
    por_competencia: list[dict] = field(default_factory=list)
    # a mesma conta somada por estabelecimento/mês/CST/CFOP, que é a unidade em
    # que a outra tese grava. Fica fora de `serializar`: o diário não carrega
    # milhares de grupos, quem os quer lê o parquet
    grupos: dict[Grupo, Total] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    segundos: float = 0.0


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "ate": r.ate, "arquivos": r.arquivos, "ilegiveis": r.ilegiveis,
        "linhas": r.linhas, "itens_lidos": r.itens_lidos,
        "estabelecimentos": r.estabelecimentos, "competencias": r.competencias,
        "base": str(r.base), "icms_excluido": str(r.icms_excluido),
        "diferenca_pis": str(r.diferenca_pis),
        "diferenca_cofins": str(r.diferenca_cofins),
        "selic": str(r.selic), "total_atualizado": str(r.total_atualizado),
        "prescrito": str(r.prescrito),
        "competencias_prescritas": r.competencias_prescritas,
        "data_de_referencia": r.data_de_referencia,
        "por_competencia": r.por_competencia,
        "avisos": r.avisos, "segundos": r.segundos,
    }


def apurar(contribuicoes: list[str], destino: str, ate: str = "",
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None,
           mensal: dict[str, Decimal] | None = None) -> Resumo:
    """Escreve o 903 em parquet e devolve o resumo.

    Cada arquivo que não der para ler vira aviso e segue — um SPED corrompido
    no meio de cinco anos não pode derrubar a tese inteira. O que **não** segue
    é a Selic desconhecida: aí o número sairia menor que o devido, calado, e é
    melhor a etapa parar dizendo qual mês falta na tabela.
    """
    inicio = time.time()
    referencia = referencia or date.today()
    ate = ate or mes_de(referencia)
    # a série que corrige: do banco, quando quem chama a trouxe, e a semente de
    # `tab_selic` quando não. Ver `infraestrutura/selic`
    mensal = mensal or None
    os.makedirs(destino, exist_ok=True)

    resumo = Resumo(ate=ate, data_de_referencia=referencia.isoformat())
    andamento = Andamento()
    totais: dict[str, Total] = {}
    estabelecimentos: set[str] = set()

    caminho_do_parquet = os.path.join(destino, ARQUIVO_DA_EXCLUSAO_DO_ICMS)
    escritor = Escritor(caminho_do_parquet, colunas_da_exclusao())
    inteira = False
    try:
        for caminho in contribuicoes:
            parar_se_pedirem(deve_parar)
            _de_um_arquivo(caminho, ate, escritor, resumo, andamento,
                           totais, estabelecimentos, mensal)
            if avisar:
                avisar(andamento)
        inteira = True
    finally:
        escritor.fechar()
        # meia leitura não vale, e parquet pela metade é pior que parquet
        # nenhum: quem o abre não tem como saber que faltou arquivo
        if not inteira:
            _apagar(caminho_do_parquet)

    resumo.linhas = escritor.gravadas
    resumo.estabelecimentos = sorted(estabelecimentos)
    resumo.competencias = sorted(totais)
    _fechar_as_contas(resumo, totais, referencia)
    resumo.segundos = round(time.time() - inicio, 1)
    log.info("exclusão do ICMS da base apurada", extra=serializar(resumo))
    return resumo


def _apagar(caminho: str) -> None:
    try:
        os.remove(caminho)
    except OSError as erro:
        log.warning("não deu para apagar o parquet interrompido",
                    extra={"arquivo": os.path.basename(caminho), "erro": str(erro)})


def _de_um_arquivo(caminho: str, ate: str, escritor: Escritor, resumo: Resumo,
                   andamento: Andamento, totais: dict[str, Total],
                   estabelecimentos: set[str],
                   mensal: dict[str, Decimal] | None = None) -> None:
    nome = os.path.basename(caminho)
    try:
        codificacao = codificacao_de(caminho)
        for linha in exclusoes_do_icms(caminho, codificacao, ate, mensal=mensal):
            escritor.escrever(linha.como_dicionario())
            estabelecimentos.add(linha.cnpj)
            _somar(totais, resumo.grupos, linha)
    # só o arquivo ilegível vira aviso e segue. A Selic desconhecida
    # (`SelicDesconhecida`) e o cancelamento (`LeituraCancelada`) sobem: número
    # corrigido a menos, calado, é pior que etapa parada dizendo o que falta
    except (OSError, ValueError) as erro:
        log.warning("não deu para tirar a exclusão do ICMS da EFD-Contribuições",
                    extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao apurar o Tema 69.")
        return

    resumo.arquivos += 1
    andamento.arquivos += 1
    andamento.linhas = escritor.gravadas


def _somar(totais: dict[str, Total], grupos: dict[Grupo, Total], linha) -> None:
    """A mesma linha entra nas duas somas: a da tela e a do parquet."""
    competencia = competencia_de(linha.periodo)
    totais.setdefault(competencia, Total()).somar(linha)
    grupo = Grupo(cnpj=linha.cnpj, competencia=competencia, registro=REGISTRO,
                  cst=linha.cst, cfop=linha.cfop)
    grupos.setdefault(grupo, Total()).somar(linha)


def _fechar_as_contas(resumo: Resumo, totais: dict[str, Total],
                      referencia: date) -> None:
    """Soma o crédito só do que está no prazo, e conta o resto à parte."""
    prescritas = {c for c in totais if prescricao.prescrita(c, referencia)}
    resumo.competencias_prescritas = len(prescritas)

    for competencia in sorted(totais):
        total = totais[competencia]
        resumo.base += total.base
        resumo.icms_excluido += total.icms_excluido
        resumo.itens_lidos += total.linhas
        if competencia in prescritas:
            resumo.prescrito += total.total_atualizado
        else:
            resumo.diferenca_pis += total.diferenca_pis
            resumo.diferenca_cofins += total.diferenca_cofins
            resumo.selic += total.selic
            resumo.total_atualizado += total.total_atualizado

        resumo.por_competencia.append({
            "competencia": competencia,
            "linhas": total.linhas,
            "prescrita": competencia in prescritas,
            "selic_acumulada": total.selic_acumulada,
            "base": str(total.base),
            "icms_excluido": str(total.icms_excluido),
            "diferenca_pis": str(total.diferenca_pis),
            "diferenca_cofins": str(total.diferenca_cofins),
            "selic": str(total.selic),
            "total_atualizado": str(total.total_atualizado),
        })


def avisar_se_a_selic_nao_alcanca(ate: str,
                                  mensal: dict[str, Decimal] | None = None) -> str:
    """O aviso que a tela dá **antes** de rodar uma hora à toa.

    Devolve vazio quando a série cobre o mês pedido. `mensal` é a série que
    será usada de verdade — a do banco, em produção; conferir outra aqui seria
    aprovar a rodada olhando para a série errada.
    """
    if alcanca(ate, mensal):
        return ""
    ultimo = ultimo_mes(mensal)
    onde = f"vai até {ultimo[5:]}/{ultimo[:4]}" if ultimo else "está vazia"
    return (f"A série da Selic {onde} e a correção foi pedida até "
            f"{ate[5:]}/{ate[:4]}. O Banco Central ainda não publicou esses "
            "meses, ou não deu para falar com ele: corrigir por série "
            "incompleta devolveria menos do que o devido.")
