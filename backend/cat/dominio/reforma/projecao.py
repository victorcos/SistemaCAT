"""A projeção de 2025 a 2033: o coração da simulação.

## A premissa que decide tudo

**O preço ao consumidor é constante.** A receita bruta de hoje vale para todos
os anos, e o que muda de imposto recai sobre a margem. O resultado mede o
tamanho do efeito — não é previsão de preço, nem de volume. O cliente pediu
que isso fique explícito (apresentação de 23/10/2026): a simulação não
presume queda de venda por causa do imposto.

## Linear, e por isso somável

Toda fórmula daqui é linear nos valores da linha, dados a redução do
cClassTrib e o ano. A consequência é a propriedade que o sistema exige: projetar
a soma de mil linhas de mesma redução dá o mesmo que somar as mil projeções. É
o que permite agregar a base antes de projetar — por grupo, capítulo, UF, SKU
— sem perder um centavo. O Imposto Seletivo entra já como valor (custo × alíquota
da categoria), e não como alíquota, justamente para continuar somável: dois SKUs
de categorias diferentes cabem na mesma soma.

A exceção é a variação teórica de preço, que divide pelo ICMS "por dentro" e
por isso depende do nível em que se calcula (ver `receita_bruta_requerida`).

## As fórmulas, na ordem da planilha (colunas U a AO do tabelão)

    aCBS, aIBS = alíquota do ano × (1 − redução); zero no ano de teste
    ICMSd  = débito ICMS × fator         PCd = débito PIS/COFINS × vigente
    Vliq   = (RB − ICMSd − PCd − IPId) ÷ (1 + aCBS + aIBS)      IBS/CBS "por fora"
    CBSd   = Vliq × aCBS                 IBSd = Vliq × aIBS
    IPI    = IPI da entrada × vigente    IS = IS pleno × vigente   (custo, sem crédito)
    CMV    = custo de compra + IPI + IS
    ICMSc  = crédito ICMS × fator        PCc = crédito PIS/COFINS × vigente
    CBSc   = (custo + IS) × aCBS         IBSc = (custo + IS) × aIBS
    Lucro bruto = Vliq − CMV

O débito de IPI na saída (IPId) não está na planilha da primeira simulação
porque o varejista não o tem: lá ele é zero. Entra aqui para a identidade de
2025 — Vliq igual à receita líquida de hoje — valer também para quem industrializa.

**Custo de compra** é o custo líquido mais o PIS/COFINS sem crédito (CST 70,
72, 73 e 75): esse imposto já está no preço que o fornecedor cobra e continua
lá em todos os anos. Só o IPI sai do custo em 2027.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal

from cat.dominio.reforma.parametros import UM, ZERO, ParametrosDoAno


def _somar(a, b):
    """Soma campo a campo de dois registros do mesmo tipo, todos Decimal."""
    return type(a)(**{f.name: getattr(a, f.name) + getattr(b, f.name) for f in fields(a)})


@dataclass(frozen=True)
class BaseDaLinha:
    """Os valores de hoje de uma linha de venda (ou de uma soma delas).

    Tudo em reais do mês-base. É a entrada da projeção, e é somável: a base de
    um grupo é a soma das bases das suas linhas.
    """

    receita_bruta: Decimal = ZERO
    debito_icms: Decimal = ZERO
    debito_ipi: Decimal = ZERO
    debito_pis_cofins: Decimal = ZERO
    credito_icms: Decimal = ZERO
    credito_pis_cofins: Decimal = ZERO      # só o do CST 50
    custo_liquido: Decimal = ZERO           # compra sem ICMS, IPI e PIS/COFINS; base do IS
    pis_cofins_sem_credito: Decimal = ZERO  # CST 70/72/73/75: já está no preço de compra
    ipi_entrada: Decimal = ZERO
    seletivo_pleno: Decimal = ZERO          # custo líquido × alíquota da categoria

    def __add__(self, outra: BaseDaLinha) -> BaseDaLinha:
        return _somar(self, outra)

    @property
    def custo_de_compra(self) -> Decimal:
        return self.custo_liquido + self.pis_cofins_sem_credito

    @property
    def receita_liquida(self) -> Decimal:
        return self.receita_bruta - self.debito_icms - self.debito_ipi - self.debito_pis_cofins

    @property
    def cmv_atual(self) -> Decimal:
        """O CMV do modelo de hoje: custo de compra mais o IPI, que não se recupera."""
        return self.custo_de_compra + self.ipi_entrada

    @property
    def lucro_bruto_atual(self) -> Decimal:
        return self.receita_liquida - self.cmv_atual


@dataclass(frozen=True)
class ResultadoDoAno:
    """Uma linha (ou uma soma delas) num ano. Somável como a base: o total do
    grupo é a soma dos resultados das linhas, e os percentuais se calculam
    sobre a soma — nunca como média de percentuais."""

    receita_bruta: Decimal = ZERO
    debito_icms: Decimal = ZERO
    debito_pis_cofins: Decimal = ZERO
    debito_ipi: Decimal = ZERO
    receita_liquida: Decimal = ZERO          # Vliq: a base do IBS/CBS
    debito_cbs: Decimal = ZERO
    debito_ibs: Decimal = ZERO
    custo_de_compra: Decimal = ZERO
    ipi_custo: Decimal = ZERO
    seletivo: Decimal = ZERO
    cmv: Decimal = ZERO
    credito_icms: Decimal = ZERO
    credito_pis_cofins: Decimal = ZERO
    credito_cbs: Decimal = ZERO
    credito_ibs: Decimal = ZERO
    teste_destacado: Decimal = ZERO          # CBS/IBS de 2026, destacado e compensado

    def __add__(self, outro: ResultadoDoAno) -> ResultadoDoAno:
        return _somar(self, outro)

    @property
    def icms_a_recolher(self) -> Decimal:
        return self.debito_icms - self.credito_icms

    @property
    def pis_cofins_a_recolher(self) -> Decimal:
        return self.debito_pis_cofins - self.credito_pis_cofins

    @property
    def cbs_a_recolher(self) -> Decimal:
        return self.debito_cbs - self.credito_cbs

    @property
    def ibs_a_recolher(self) -> Decimal:
        return self.debito_ibs - self.credito_ibs

    @property
    def total_a_recolher(self) -> Decimal:
        """ICMS, PIS/COFINS, CBS, IBS e o IPI da saída. O IS não: é custo, pago
        pelo fornecedor e embutido no preço de compra."""
        return (self.icms_a_recolher + self.pis_cofins_a_recolher + self.cbs_a_recolher
                + self.ibs_a_recolher + self.debito_ipi)

    @property
    def lucro_bruto(self) -> Decimal:
        return self.receita_liquida - self.cmv

    @property
    def margem(self) -> Decimal | None:
        """Lucro bruto sobre a receita bruta. Sem receita, não há margem — e
        devolver zero faria um grupo vazio parecer um grupo sem lucro."""
        return _razao(self.lucro_bruto, self.receita_bruta)

    @property
    def carga_liquida(self) -> Decimal | None:
        return _razao(self.total_a_recolher, self.receita_bruta)

    @property
    def carga_com_seletivo(self) -> Decimal | None:
        return _razao(self.total_a_recolher + self.seletivo, self.receita_bruta)

    @property
    def creditos_recuperaveis(self) -> Decimal:
        return self.credito_icms + self.credito_pis_cofins + self.credito_cbs + self.credito_ibs

    @property
    def valor_bruto_das_compras(self) -> Decimal:
        """O que a nota de compra soma: custo, os tributos que se recuperam e
        os que não se recuperam. Os créditos estão aqui, e não no CMV."""
        return self.custo_de_compra + self.creditos_recuperaveis + self.ipi_custo + self.seletivo


def _razao(parte: Decimal, todo: Decimal) -> Decimal | None:
    return parte / todo if todo else None


def projetar(base: BaseDaLinha, reducao: Decimal, ano: ParametrosDoAno) -> ResultadoDoAno:
    """A linha num ano. `reducao` é a do grupo do cClassTrib (0, 0,6 ou 1)."""
    a_cbs, a_ibs = ano.aliquotas(reducao)
    debito_icms = base.debito_icms * ano.fator_icms
    debito_pc = base.debito_pis_cofins if ano.pis_cofins_vigente else ZERO
    debito_ipi = base.debito_ipi if ano.ipi_vigente else ZERO
    receita_liquida = (base.receita_bruta - debito_icms - debito_pc - debito_ipi) / (UM + a_cbs + a_ibs)
    ipi_custo = base.ipi_entrada if ano.ipi_vigente else ZERO
    seletivo = base.seletivo_pleno if ano.is_vigente else ZERO
    custo = base.custo_de_compra
    base_do_credito = custo + seletivo
    teste = ((ano.cbs + ano.ibs) * (UM - reducao) * receita_liquida
             if ano.teste_compensavel else ZERO)
    return ResultadoDoAno(
        receita_bruta=base.receita_bruta,
        debito_icms=debito_icms,
        debito_pis_cofins=debito_pc,
        debito_ipi=debito_ipi,
        receita_liquida=receita_liquida,
        debito_cbs=receita_liquida * a_cbs,
        debito_ibs=receita_liquida * a_ibs,
        custo_de_compra=custo,
        ipi_custo=ipi_custo,
        seletivo=seletivo,
        cmv=custo + ipi_custo + seletivo,
        credito_icms=base.credito_icms * ano.fator_icms,
        credito_pis_cofins=base.credito_pis_cofins if ano.pis_cofins_vigente else ZERO,
        credito_cbs=base_do_credito * a_cbs,
        credito_ibs=base_do_credito * a_ibs,
        teste_destacado=teste,
    )


def receita_bruta_requerida(base: BaseDaLinha, reducao: Decimal, ano: ParametrosDoAno,
                            lucro_bruto_do_ano_base: Decimal) -> Decimal | None:
    """A receita bruta que preservaria, no ano, o lucro bruto em reais do ano-base.

    **Variação teórica, não recomendação de reajuste** — o termo "ajuste
    necessário" foi vetado pelo revisor em 13/10/2026.

    Aqui o ICMS é tratado "por dentro", proporcional ao preço:
    `t = débito ICMS ÷ (RB − débito PIS/COFINS) × fator`. É uma leitura
    diferente da projeção, que mantém o débito de ICMS fixo em reais — as duas
    estão documentadas, e a diferença é o motivo de esta função não ser
    somável: ela depende do nível em que se calcula. Quem chama decide o nível
    (grupo, capítulo, SKU) e soma as receitas requeridas.

    Devolve nada quando o ICMS consumiria o preço inteiro (t ≥ 1).
    """
    resultado = projetar(base, reducao, ano)
    a_cbs, a_ibs = ano.aliquotas(reducao)
    denominador = base.receita_bruta - base.debito_pis_cofins
    t = base.debito_icms / denominador * ano.fator_icms if denominador else ZERO
    if t >= UM:
        return None
    debito_pc = base.debito_pis_cofins if ano.pis_cofins_vigente else ZERO
    return (resultado.cmv + lucro_bruto_do_ano_base) * (UM / (UM - t) + a_cbs + a_ibs) + debito_pc
