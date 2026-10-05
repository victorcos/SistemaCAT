"""A exclusão do PIS e da COFINS da própria base de cálculo.

A tese: o preço de venda embute as duas contribuições, e receita não é
imposto. Excluindo-as, a base encolhe e o que foi pago a mais volta.

**A regra, decidida em 24/09/2026 com quem apura:** a base de cada uma perde
**as duas**. Numa venda de R$ 1.000,00 com PIS de R$ 16,50 e COFINS de
R$ 76,00, a base nova é R$ 907,50 para os dois — não R$ 983,50 para o PIS e
R$ 924,00 para a COFINS. É a leitura mais comum da tese, e a que o escritório
pede. E vale **só no débito**: o crédito das aquisições fica como está.

**"Só no débito" não quer dizer "só a saída", e isso custou duas pontas.** Até
01/10/2026 o filtro era `operacao == SAIDA`, e ele errava nos dois sentidos:
deixava entrar remessa, bonificação e baixa de estoque — que são saída e não são
receita — e deixava de fora a **devolução de venda**, que é entrada e é estorno
de receita tributada. Quem apontou foi o relatório 680 do MA, da mesma
metodologia: R$ 215.706,22 de base a mais de um lado, R$ 723.198,32 a menos do
outro. Agora o filtro é o CFOP, o mesmo das outras três teses
(`tab_cfop_receita`).

**De onde vêm os números.** Do mesmo `ApuracaoEFD` que a Gestão monta — uma
passada pelo arquivo serve às duas, e qualquer correção na leitura vale para as
duas de uma vez. Quem entrega os agregados a esta função é a etapa; hoje a
Gestão os monta e descarta ao terminar, então a exclusão relê os arquivos. Ficam
anotados, para o próximo passo, os agregados em disco na pasta da execução: são
poucos MB para um SPED de 1 GB, e com eles a exclusão sai em segundos em vez de
uma hora.

**O agrupamento é o do MA**, e não por linha: registro, CST e CFOP dentro da
competência. Arredondar a diferença linha a linha inflaria o total — numa base
de milhões de itens, meio por cento (é o que o Gross UP da empresa 08 ensinou).
Aqui o arredondamento acontece uma vez por grupo, com a alíquota **efetiva**
do próprio grupo (valor ÷ base), que é imune a alíquota fora do padrão e a
arredondamento do ERP.

**O que a tese não alcança, e a conta não finge que alcança:**

* **alíquota em reais** (CST 03, e os registros por unidade de medida) — a
  contribuição não sai da receita, sai da quantidade: excluir dinheiro de uma
  base em litros não quer dizer nada. Fica de fora, contada à parte;
* **receita sem contribuição** (CST 04 a 09) — não há o que excluir;
* **registros que esta apuração ainda não lê** (C601/C605, D300, D350, F200,
  F510, F560, I100). Se o arquivo os tiver, o resumo diz quantos, porque
  descobrir uma receita faltando depois de entregar o cálculo é o pior jeito
  de descobrir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from cat.infraestrutura.gestao.modelos import VL_BC, VL_TRIB, ApuracaoEFD
from cat.infraestrutura.gestao.numeros import arredondar_div
from cat.infraestrutura.sped.tabelas.tab_cfop_receita import (
    FATURAMENTO,
    classificacao_do_cfop,
)
from cat.log import obter_log

log = obter_log(__name__)

# a operação que interessa: a tese é do débito. **Não basta**, e isso só se viu
# em 01/10/2026 — ver `_entra`, logo abaixo
SAIDA = "S"

# CST de receita com contribuição calculada sobre o valor
CST_COM_INCIDENCIA = frozenset({"01", "02", "05"})

# CST 03 é alíquota por unidade de medida: a contribuição não vem da receita
CST_POR_UNIDADE = "03"

# receita sem contribuição — não há o que excluir, e não é erro
CST_SEM_INCIDENCIA = frozenset({"04", "06", "07", "08", "09"})

# registros de receita que a leitura da Gestão ainda não cobre. Presentes no
# arquivo, viram aviso: a conta sai incompleta e quem assina precisa saber
REGISTROS_DE_FORA = (
    ("C601", "Consolidação diária de energia, água e gás — PIS"),
    ("C605", "Consolidação diária de energia, água e gás — COFINS"),
    ("D300", "Resumo diário de passagens (códigos 13 a 16 e 18)"),
    ("D350", "Resumo diário de cupom fiscal por ECF"),
    ("F200", "Atividade imobiliária — unidade vendida"),
    ("F510", "Lucro presumido, regime de caixa, por unidade de medida"),
    ("F560", "Lucro presumido, competência, por unidade de medida"),
    ("I100", "Consolidação das operações do período (instituições financeiras)"),
)


# Registros que trazem PIS e COFINS em **linhas separadas**: a consolidação
# escreve um registro para cada tributo, sobre a mesma receita. Sem juntá-los,
# a base entra duas vezes e cada grupo exclui só a própria contribuição — que é
# a tese conservadora, não a que se escolheu. Foi o que fez a apuração da empresa 16
# errar 29% nos meses de C180 e acertar nos de C175, que traz os dois na mesma
# linha. O nome da família é o do MA, para os dois relatórios se compararem.
FAMILIA_DO_REGISTRO = {
    "C181": "C180/C181/C185", "C185": "C180/C181/C185",
    "C191": "C190/C191/C195", "C195": "C190/C191/C195",
    "C381": "C380/C381/C385", "C385": "C380/C381/C385",
    "C481": "C400/C481/C485", "C485": "C400/C481/C485",
    "C491": "C490/C491/C495", "C495": "C490/C491/C495",
    "C501": "C500/C501/C505", "C505": "C500/C501/C505",
    "C601": "C600/C601/C605", "C605": "C600/C601/C605",
    "D101": "D100/D101/D105", "D105": "D100/D101/D105",
    "D201": "D200/D201/D205", "D205": "D200/D201/D205",
    "D501": "D500/D501/D505", "D505": "D500/D501/D505",
    "D601": "D600/D601/D605", "D605": "D600/D601/D605",
}


def familia(registro: str) -> str:
    """O par que fala da mesma receita. Registro que traz os dois volta igual."""
    return FAMILIA_DO_REGISTRO.get(registro, registro)


@dataclass(frozen=True)
class Grupo:
    """Onde a exclusão acontece: um CST dentro de um CFOP, num registro."""

    cnpj: str
    periodo: str            # "AAAA-MM"
    registro: str
    cst: str
    cfop: str


@dataclass
class Apurado:
    """O que o grupo tinha, e o que ele passa a ter. Tudo em centavos.

    A base vem **separada por tributo** porque é assim que o arquivo a traz:
    o C170 tem VL_BC_PIS e VL_BC_COFINS em campos próprios. Quase sempre são
    iguais, e quando não são a diferença é do cliente — não cabe a esta conta
    escolher uma das duas e esconder a outra.
    """

    base_pis: int = 0
    base_cofins: int = 0
    pis: int = 0
    cofins: int = 0

    @property
    def base(self) -> int:
        """A receita do grupo, para o relatório. Divergindo, vale a maior."""
        return max(self.base_pis, self.base_cofins)

    @property
    def bases_divergem(self) -> bool:
        return self.base_pis != self.base_cofins and min(self.base_pis, self.base_cofins) > 0

    @property
    def excluido(self) -> int:
        """O que sai da base: as duas contribuições, como decidido."""
        return self.pis + self.cofins

    @property
    def consistente(self) -> bool:
        """Receita tem de ser maior que a contribuição que ela mesma gerou.

        Quando não é, o grupo não entra na conta. Recalcular ali devolveria
        base zero e "recuperaria" a contribuição inteira — 100% de um grupo é
        o tipo de número que passa na soma e não sobrevive à fiscalização.
        """
        return self.base > self.excluido > 0

    @staticmethod
    def _recalcular(base: int, valor: int, excluido: int) -> int:
        """O tributo sobre a base nova, pela alíquota efetiva do grupo.

        `valor / base` é a alíquota que o próprio arquivo praticou — imune a
        alíquota fora do padrão, a ajuste na linha e ao arredondamento do ERP.
        Base menor que a contribuição que ela gerou é arquivo inconsistente: a
        base nova para em zero, e não vira crédito inventado.
        """
        if base <= 0 or valor <= 0:
            return valor
        return arredondar_div(max(0, base - excluido) * valor, base)

    @property
    def base_nova_pis(self) -> int:
        return max(0, self.base_pis - self.excluido)

    @property
    def base_nova_cofins(self) -> int:
        return max(0, self.base_cofins - self.excluido)

    @property
    def pis_novo(self) -> int:
        return self._recalcular(self.base_pis, self.pis, self.excluido)

    @property
    def cofins_novo(self) -> int:
        return self._recalcular(self.base_cofins, self.cofins, self.excluido)

    @property
    def diferenca_pis(self) -> int:
        return self.pis - self.pis_novo

    @property
    def diferenca_cofins(self) -> int:
        return self.cofins - self.cofins_novo

    @property
    def diferenca(self) -> int:
        return self.diferenca_pis + self.diferenca_cofins


@dataclass
class Resumo:
    """O que a rodada encontrou — inclusive o que deixou de fora."""

    arquivos: int = 0
    grupos: int = 0
    base: int = 0
    excluido: int = 0
    diferenca_pis: int = 0
    diferenca_cofins: int = 0
    # motivo -> quantas chaves do agregado não entraram
    fora: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    periodos: list[str] = field(default_factory=list)

    @property
    def diferenca(self) -> int:
        return self.diferenca_pis + self.diferenca_cofins


@dataclass
class Total:
    """Uma soma de grupos — uma competência, ou o trabalho inteiro.

    Soma o que cada grupo já resolveu, e **não recalcula sobre a soma**. O
    grupo é a unidade de arredondamento: recalcular aqui daria um total que
    não bate com a soma das linhas do relatório, e a primeira conferência que
    somasse a planilha à mão encontraria a diferença.
    """

    base: int = 0
    excluido: int = 0
    pis: int = 0
    cofins: int = 0
    pis_novo: int = 0
    cofins_novo: int = 0
    grupos: int = 0

    def somar(self, a: "Apurado") -> None:
        self.base += a.base
        self.excluido += a.excluido
        self.pis += a.pis
        self.cofins += a.cofins
        self.pis_novo += a.pis_novo
        self.cofins_novo += a.cofins_novo
        self.grupos += 1

    @property
    def diferenca_pis(self) -> int:
        return self.pis - self.pis_novo

    @property
    def diferenca_cofins(self) -> int:
        return self.cofins - self.cofins_novo

    @property
    def diferenca(self) -> int:
        return self.diferenca_pis + self.diferenca_cofins


@dataclass
class Exclusao:
    grupos: dict[Grupo, Apurado] = field(default_factory=dict)
    resumo: Resumo = field(default_factory=Resumo)

    def por_periodo(self) -> dict[str, Total]:
        """O total de cada competência — é a linha do relatório."""
        total: dict[str, Total] = defaultdict(Total)
        for grupo, a in self.grupos.items():
            if a.consistente:
                total[grupo.periodo].somar(a)
        return dict(sorted(total.items()))


def _natureza(cfop: str, operacao: str) -> str:
    """É receita? O CFOP responde quando há CFOP; o sentido, quando não há.

    **O A170 e o F100 não têm CFOP** — a nota de serviço e os demais documentos
    geradores de contribuição não o pedem no leiaute. Perguntar o CFOP deles
    devolveria vazio e os derrubaria: são R$ 10,28 milhões de base na empresa 05, e
    foi exatamente o que aconteceu na primeira versão desta regra.

    O MA resolve do mesmo jeito, e deixa à vista: na coluna "CFOP" dessas
    linhas ele escreve **"S"** — o sentido da operação, não um CFOP — e
    classifica como faturamento.
    """
    if (cfop or "").strip():
        return classificacao_do_cfop(cfop)
    return FATURAMENTO if operacao == SAIDA else ""


def calcular(apuracoes: list[ApuracaoEFD]) -> Exclusao:
    """A exclusão de um trabalho inteiro, a partir das apurações em cache.

    Cada `ApuracaoEFD` é um arquivo — um CNPJ numa competência. O mesmo
    estabelecimento em dois arquivos (original e retificadora) é problema de
    quem escolhe os arquivos, não daqui: esta função soma o que recebe.
    """
    resultado = Exclusao()
    fora: dict[str, int] = defaultdict(int)

    for ap in apuracoes:
        resultado.resumo.arquivos += 1
        _avisar_do_que_falta(ap, resultado.resumo)

        for chave, somas in ap.documentos.items():
            tributo, registro, operacao, cst, cfop, _nat, _aliq = chave
            natureza = _natureza(cfop, operacao)
            if not natureza:
                fora["CFOP fora da receita: não é venda nem devolução de venda"] += 1
                continue

            # a contribuição vem antes do CST de propósito: numa base real, a
            # maior parte das chaves de CST 04 e 49 vem zerada, e acusá-las
            # como "CST fora da tese" encheria o resumo de alarme falso — o
            # contador deixaria de servir para achar o que ficou de fora
            valor = somas[VL_TRIB]
            if valor <= 0:
                fora["grupo sem contribuição apurada"] += 1
                continue

            # **a devolução de venda entra com o CST que ela tiver.** Ela se
            # escritura com CST de crédito — 50, 73, 98, 99 nas 8.822 linhas do
            # relatório 680 do MA —, porque é estorno de uma venda que já foi
            # tributada, e não uma aquisição. Exigir CST de receita aqui era o
            # que a deixava de fora
            if natureza == FATURAMENTO:
                if cst == CST_POR_UNIDADE:
                    fora["alíquota em reais: a contribuição não vem da receita"] += 1
                    continue
                if cst in CST_SEM_INCIDENCIA:
                    fora["receita sem contribuição: não há o que excluir"] += 1
                    continue
                if cst not in CST_COM_INCIDENCIA:
                    fora[f"CST fora da tese, com contribuição apurada: "
                         f"{cst or 'em branco'}"] += 1
                    continue

            grupo = Grupo(ap.cnpj, ap.periodo, familia(registro), cst, cfop)
            alvo = resultado.grupos.setdefault(grupo, Apurado())
            if tributo == "PIS":
                alvo.base_pis += somas[VL_BC]
                alvo.pis += valor
            else:
                alvo.base_cofins += somas[VL_BC]
                alvo.cofins += valor

    _fechar(resultado, fora)
    return resultado


def _fechar(resultado: Exclusao, fora: dict[str, int]) -> None:
    resumo = resultado.resumo
    inconsistentes = sum(1 for a in resultado.grupos.values() if not a.consistente)
    if inconsistentes:
        fora["base menor que a contribuição do próprio grupo"] = inconsistentes
    resumo.fora = dict(sorted(fora.items()))

    resumo.grupos = sum(1 for a in resultado.grupos.values() if a.consistente)
    for grupo, a in resultado.grupos.items():
        if not a.consistente:
            continue
        resumo.base += a.base
        resumo.excluido += a.excluido
        resumo.diferenca_pis += a.diferenca_pis
        resumo.diferenca_cofins += a.diferenca_cofins
    resumo.periodos = sorted({g.periodo for g, a in resultado.grupos.items() if a.consistente})
    divergentes = sum(1 for a in resultado.grupos.values() if a.bases_divergem)
    if divergentes:
        resumo.avisos.append(
            f"{divergentes} grupo(s) têm base de PIS diferente da base de COFINS. "
            "Cada tributo foi recalculado sobre a própria base; o relatório mostra a maior.")
        log.warning("bases de pis e cofins divergem no mesmo grupo",
                    extra={"grupos": divergentes})

    log.info("exclusão do pis/cofins da própria base calculada", extra={
        "arquivos": resumo.arquivos, "grupos": resumo.grupos,
        "periodos": len(resumo.periodos),
        "base_centavos": resumo.base, "excluido_centavos": resumo.excluido,
        "diferenca_centavos": resumo.diferenca,
        "chaves_fora": sum(resumo.fora.values()),
    })


def _avisar_do_que_falta(ap: ApuracaoEFD, resumo: Resumo) -> None:
    """Receita que o arquivo tem e esta conta ainda não lê."""
    for registro, o_que_e in REGISTROS_DE_FORA:
        quantas = ap.contagens.get(registro, 0)
        if not quantas:
            continue
        aviso = (f"{ap.cnpj} {ap.periodo}: {quantas} linha(s) de {registro} "
                 f"({o_que_e}) ficaram de fora — a leitura ainda não as cobre.")
        resumo.avisos.append(aviso)
        log.warning("registro de receita fora da exclusão", extra={
            "cnpj": ap.cnpj, "periodo": ap.periodo,
            "registro": registro, "linhas": quantas,
        })
