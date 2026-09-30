"""O que as três exclusões por item fazem igual — e só isso.

São três teses, cada uma com o seu motor, o seu gabarito e o seu conferidor:

* **903** — o ICMS destacado (`sped/exclusao_do_icms.py`);
* **839** — o ICMS-ST presumido (`sped/exclusao_do_icms_st.py`);
* **933** — o ISS da nota de serviço (`sped/exclusao_do_iss.py`).

O que elas **não** têm em comum é a conta: cada relatório do MA tem a sua
aritmética, e isso foi descoberto três vezes num dia só — a diferença da
contribuição, o completamento do cadastro pela matriz e a base recalculada
divergem entre relatórios. Por isso os motores continuam separados e cada um
conferido contra o seu próprio gabarito.

O que elas têm em comum é a **rodada**: ler os SPED em ordem, gravar um parquet
por tese, somar por competência e por grupo, separar o que prescreveu, e não
deixar arquivo pela metade quando alguém cancela. Isso é idêntico nas três, e
três cópias dessa mecânica seriam três lugares para divergir em silêncio.

## O que entra por parâmetro

`Motor` descreve a tese para quem a roda: como ler, que colunas gravar, em que
arquivo, e se o grupo tem CFOP — o 933 não tem, porque nota de serviço não tem
CFOP. Nada de conta entra aqui: a conta já veio pronta do motor, em `Decimal`
de duas casas.

## O que prescreveu aparece e não soma

Como nas outras: a competência que os cinco anos levaram sai no relatório,
marcada, e fora da soma do crédito. Ver `dominio/piscofins/prescricao.py`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from cat.dominio.piscofins import prescricao
from cat.infraestrutura.analitico.escrita import Escritor, parar_se_pedirem
from cat.infraestrutura.sped.leitor import codificacao_de
from cat.log import obter_log

log = obter_log(__name__)

ZERO = Decimal(0)


def mes_de(referencia: date) -> str:
    """O mês da restituição, em "aaaa-mm"."""
    return referencia.strftime("%Y-%m")


def competencia_de(periodo: str) -> str:
    """"01/10/2022" -> "2022-10". O motor escreve como o relatório mostra."""
    partes = (periodo or "").split("/")
    return f"{partes[2]}-{partes[1]}" if len(partes) == 3 else ""


@dataclass(frozen=True)
class Motor:
    """A tese, descrita para quem a roda.

    `ler` recebe `(caminho, codificacao, ate)` e devolve as linhas prontas —
    já com a Selic, as exceções de alíquota e o que mais a tese precisar,
    fechado por quem montou o motor. O núcleo não sabe nada disso.
    """

    nome: str                       # "icms", "icms_st", "iss" — para o log
    tese: str                       # a coluna `tese` do parquet agregado
    arquivo: str                    # "exclusao_do_icms.parquet"
    registro: str                   # de onde as linhas saem: "C170", "A170"
    ler: Callable[[str, str, str], Iterator]
    colunas: Callable[[], list[str]]
    # o 933 não tem CFOP: nota de serviço não tem. O grupo fica sem a coluna,
    # e não com ela vazia — vazio numa chave de agrupamento é um valor
    por_cfop: bool = True


@dataclass
class Andamento:
    arquivos: int = 0
    linhas: int = 0


@dataclass(frozen=True)
class Grupo:
    """Onde a soma agregada mora: estabelecimento, mês, registro, CST e CFOP.

    Congelado porque é chave de dicionário — `@dataclass` sem `frozen` anula o
    `__hash__` e o erro só aparece na primeira linha somada.
    """

    cnpj: str
    competencia: str
    registro: str
    cst: str
    cfop: str = ""


@dataclass
class Total:
    """Uma soma — em Decimal, que é como a conta anda aqui.

    Serve às duas agregações: por competência, que é o que a tela mostra, e por
    grupo, que é o que entra no parquet ao lado das outras teses.
    """

    linhas: int = 0
    base: Decimal = ZERO
    excluido: Decimal = ZERO
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
        self.base += _d(linha.base)
        self.excluido += _d(linha.diferenca_da_base)
        self.pis += _d(linha.pis)
        self.cofins += _d(linha.cofins)
        self.base_stf += _d(linha.base_stf)
        self.pis_stf += _d(linha.pis_stf)
        self.cofins_stf += _d(linha.cofins_stf)
        self.diferenca_pis += _d(linha.diferenca_do_pis)
        self.diferenca_cofins += _d(linha.diferenca_da_cofins)
        self.selic += _d(linha.selic_sobre_o_pis) + _d(linha.selic_sobre_a_cofins)
        self.total_atualizado += _d(linha.total_a_recuperar_atualizado)
        self.selic_acumulada = linha.selic_acumulada


def _d(valor: str) -> Decimal:
    """O campo do motor, em Decimal. Vazio é zero — ver `_como_veio` do 933."""
    texto = (valor or "").strip()
    return Decimal(texto) if texto else ZERO


@dataclass
class Resumo:
    """O que a tese produziu, para a tela, a planilha e o histórico."""

    tese: str = ""
    ate: str = ""
    arquivos: int = 0
    ilegiveis: int = 0
    linhas: int = 0
    itens_lidos: int = 0
    estabelecimentos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    base: Decimal = ZERO
    excluido: Decimal = ZERO
    diferenca_pis: Decimal = ZERO
    diferenca_cofins: Decimal = ZERO
    selic: Decimal = ZERO
    total_atualizado: Decimal = ZERO
    # o que cinco anos já levaram: mostrado, nunca somado ao crédito
    prescrito: Decimal = ZERO
    competencias_prescritas: int = 0
    data_de_referencia: str = ""
    por_competencia: list[dict] = field(default_factory=list)
    # a mesma conta somada por grupo, que é a unidade em que o parquet agregado
    # grava. Fica fora de `serializar`: o diário não carrega milhares de grupos
    grupos: dict[Grupo, Total] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    segundos: float = 0.0


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "tese": r.tese, "ate": r.ate, "arquivos": r.arquivos,
        "ilegiveis": r.ilegiveis, "linhas": r.linhas, "itens_lidos": r.itens_lidos,
        "estabelecimentos": r.estabelecimentos, "competencias": r.competencias,
        "base": str(r.base), "excluido": str(r.excluido),
        "diferenca_pis": str(r.diferenca_pis),
        "diferenca_cofins": str(r.diferenca_cofins),
        "selic": str(r.selic), "total_atualizado": str(r.total_atualizado),
        "prescrito": str(r.prescrito),
        "competencias_prescritas": r.competencias_prescritas,
        "data_de_referencia": r.data_de_referencia,
        "por_competencia": r.por_competencia,
        "avisos": r.avisos, "segundos": r.segundos,
    }


def apurar(motor: Motor, contribuicoes: list[str], destino: str, ate: str = "",
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None) -> Resumo:
    """Escreve a tese em parquet e devolve o resumo.

    Cada arquivo que não der para ler vira aviso e segue — um SPED corrompido
    no meio de cinco anos não pode derrubar a tese inteira. O que **não** segue
    é a Selic desconhecida: aí o número sairia menor que o devido, calado, e é
    melhor a etapa parar dizendo qual mês falta na tabela.
    """
    inicio = time.time()
    referencia = referencia or date.today()
    ate = ate or mes_de(referencia)
    os.makedirs(destino, exist_ok=True)

    resumo = Resumo(tese=motor.tese, ate=ate,
                    data_de_referencia=referencia.isoformat())
    andamento = Andamento()
    totais: dict[str, Total] = {}
    estabelecimentos: set[str] = set()

    caminho_do_parquet = os.path.join(destino, motor.arquivo)
    escritor = Escritor(caminho_do_parquet, motor.colunas())
    inteira = False
    try:
        for caminho in contribuicoes:
            parar_se_pedirem(deve_parar)
            _de_um_arquivo(motor, caminho, ate, escritor, resumo, andamento,
                           totais, estabelecimentos)
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
    log.info("exclusão apurada", extra=serializar(resumo))
    return resumo


def _apagar(caminho: str) -> None:
    try:
        os.remove(caminho)
    except OSError as erro:
        log.warning("não deu para apagar o parquet interrompido",
                    extra={"arquivo": os.path.basename(caminho), "erro": str(erro)})


def _de_um_arquivo(motor: Motor, caminho: str, ate: str, escritor: Escritor,
                   resumo: Resumo, andamento: Andamento, totais: dict[str, Total],
                   estabelecimentos: set[str]) -> None:
    nome = os.path.basename(caminho)
    try:
        codificacao = codificacao_de(caminho)
        for linha in motor.ler(caminho, codificacao, ate):
            escritor.escrever(linha.como_dicionario())
            estabelecimentos.add(linha.cnpj)
            _somar(motor, totais, resumo.grupos, linha)
    # só o arquivo ilegível vira aviso e segue. A Selic desconhecida
    # (`SelicDesconhecida`) e o cancelamento (`LeituraCancelada`) sobem: número
    # corrigido a menos, calado, é pior que etapa parada dizendo o que falta
    except (OSError, ValueError) as erro:
        log.warning("não deu para tirar a exclusão da EFD-Contribuições",
                    extra={"arquivo": nome, "tese": motor.tese, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao apurar {motor.tese}.")
        return

    resumo.arquivos += 1
    andamento.arquivos += 1
    andamento.linhas = escritor.gravadas


def _somar(motor: Motor, totais: dict[str, Total], grupos: dict[Grupo, Total],
           linha) -> None:
    """A mesma linha entra nas duas somas: a da tela e a do parquet."""
    competencia = competencia_de(linha.periodo)
    totais.setdefault(competencia, Total()).somar(linha)
    grupo = Grupo(cnpj=linha.cnpj, competencia=competencia, registro=motor.registro,
                  cst=linha.cst, cfop=linha.cfop if motor.por_cfop else "")
    grupos.setdefault(grupo, Total()).somar(linha)


def _fechar_as_contas(resumo: Resumo, totais: dict[str, Total],
                      referencia: date) -> None:
    """Soma o crédito só do que está no prazo, e conta o resto à parte."""
    prescritas = {c for c in totais if prescricao.prescrita(c, referencia)}
    resumo.competencias_prescritas = len(prescritas)

    for competencia in sorted(totais):
        total = totais[competencia]
        resumo.base += total.base
        resumo.excluido += total.excluido
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
            "excluido": str(total.excluido),
            "diferenca_pis": str(total.diferenca_pis),
            "diferenca_cofins": str(total.diferenca_cofins),
            "selic": str(total.selic),
            "total_atualizado": str(total.total_atualizado),
        })
