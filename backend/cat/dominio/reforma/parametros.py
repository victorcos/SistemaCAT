"""Os parâmetros da simulação: o cronograma de cada ano, os grupos de alíquota
e as categorias do Imposto Seletivo — reunidos num cenário.

## Por que cenário, e não constante

Três dos números daqui não são lei. A alíquota de referência (26,5%) é uma
estimativa até o Senado fixar a definitiva; as alíquotas do Imposto Seletivo
dependem de lei ordinária que não existe; e o próprio cliente pediu, na
apresentação de 23/10/2026, para reprocessar quando elas forem publicadas. Um
número que vai mudar não pode morar espalhado pelo código: mora num cenário,
que se troca inteiro, e o relatório diz qual cenário produziu cada número.

`CENARIO_BASE` é o da EC 132/2023 (art. 128 do ADCT) e da LC 214/2025, com as
hipóteses de IS usadas na primeira simulação (empresa 23, dez/2025).

## O que é legislação e o que é hipótese

| Parâmetro | Natureza |
|---|---|
| cronograma 2026–2033, fator do ICMS, fim do PIS/COFINS e do IPI | legislação |
| redução de 60% e alíquota zero por cClassTrib | legislação (anexos da LC 214) |
| alíquota de referência 8,8% + 17,7% | estimativa |
| alíquotas do Imposto Seletivo | hipótese |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal(0)
UM = Decimal(1)


class CenarioInvalido(ValueError):
    """O cenário não fecha: ano repetido, alíquota fora de 0 a 1, cClassTrib em
    dois grupos. Recusado ao montar, para não produzir número de cenário torto."""


@dataclass(frozen=True)
class ParametrosDoAno:
    """O que vale num ano da transição.

    `fator_icms` é a fração do ICMS de hoje que ainda existe (1 até 2028, 0,9 em
    2029, ..., 0 em 2033). `teste_compensavel` marca 2026: a CBS de 0,9% e o IBS
    de 0,1% são destacados mas compensados com o PIS/COFINS, sem efeito líquido.
    """

    ano: int
    cbs: Decimal
    ibs: Decimal
    fator_icms: Decimal
    pis_cofins_vigente: bool
    ipi_vigente: bool
    teste_compensavel: bool
    is_vigente: bool
    observacao: str = ""

    def aliquotas(self, reducao: Decimal) -> tuple[Decimal, Decimal]:
        """CBS e IBS efetivos do item: a do ano, menos a redução do cClassTrib.
        No ano de teste a alíquota efetiva é zero — o destacado é compensado."""
        if self.teste_compensavel:
            return ZERO, ZERO
        fator = UM - reducao
        return self.cbs * fator, self.ibs * fator


@dataclass(frozen=True)
class GrupoDeAliquota:
    """Um grupo de tratamento do IBS/CBS, pelo cClassTrib do item.

    `reducao` é a fração que sai da alíquota: 0 na padrão, 0,6 na redução de
    60%, 1 na alíquota zero. Um cClassTrib novo (30%, outro anexo) é uma linha
    nova aqui, e nenhuma mudança de código.
    """

    chave: str
    rotulo: str
    reducao: Decimal
    cclasstribs: frozenset[str]


@dataclass(frozen=True)
class CategoriaDoSeletivo:
    """Uma categoria do Imposto Seletivo, achada pelo começo da NCM.

    `prefixos` casam com a NCM de 8 dígitos: "2402" pega a posição inteira,
    "22021000" pega só o código. A alíquota é hipótese até a lei ordinária.
    """

    chave: str
    rotulo: str
    aliquota: Decimal
    prefixos: tuple[str, ...]


@dataclass(frozen=True)
class Cenario:
    """Um jogo completo de premissas: cronograma, grupos e Imposto Seletivo.

    `fator_seletivo` multiplica todas as alíquotas do IS de uma vez — é a
    sensibilidade (0, 0,5, 1, 1,5) que a primeira simulação mostrou.
    """

    nome: str
    anos: tuple[ParametrosDoAno, ...]
    grupos: tuple[GrupoDeAliquota, ...]
    categorias_do_seletivo: tuple[CategoriaDoSeletivo, ...]
    fator_seletivo: Decimal = UM
    _por_cclasstrib: dict[str, GrupoDeAliquota] = field(
        init=False, repr=False, compare=False, default_factory=dict)

    def __post_init__(self) -> None:
        anos = [a.ano for a in self.anos]
        if not anos:
            raise CenarioInvalido("O cenário precisa de pelo menos um ano.")
        if anos != sorted(set(anos)):
            raise CenarioInvalido(f"Anos repetidos ou fora de ordem: {anos}.")
        for a in self.anos:
            for nome, valor in (("CBS", a.cbs), ("IBS", a.ibs), ("fator do ICMS", a.fator_icms)):
                if not ZERO <= valor <= UM:
                    raise CenarioInvalido(f"{nome} de {a.ano} fora de 0 a 1: {valor}.")
        for g in self.grupos:
            if not ZERO <= g.reducao <= UM:
                raise CenarioInvalido(f"Redução do grupo {g.rotulo} fora de 0 a 1: {g.reducao}.")
            for c in g.cclasstribs:
                if c in self._por_cclasstrib:
                    raise CenarioInvalido(
                        f"cClassTrib {c} está em dois grupos: "
                        f"{self._por_cclasstrib[c].rotulo} e {g.rotulo}.")
                self._por_cclasstrib[c] = g
        if self.fator_seletivo < ZERO:
            raise CenarioInvalido(f"Fator do Imposto Seletivo negativo: {self.fator_seletivo}.")

    @property
    def ano_base(self) -> int:
        """O primeiro ano é o modelo atual, contra o qual tudo se compara."""
        return self.anos[0].ano

    def do_ano(self, ano: int) -> ParametrosDoAno:
        for a in self.anos:
            if a.ano == ano:
                return a
        raise KeyError(f"O cenário {self.nome} não tem o ano {ano}.")

    def grupo(self, cclasstrib: str | None) -> GrupoDeAliquota | None:
        """O grupo do cClassTrib, ou nada. Nada é pendência de cadastro, e não
        alíquota padrão: chutar a padrão esconderia o item que ninguém revisou."""
        return self._por_cclasstrib.get(normalizar_cclasstrib(cclasstrib))

    def aliquota_do_seletivo(self, categoria: str | None) -> Decimal:
        """A alíquota da categoria já com o fator de sensibilidade. Sem
        categoria, o item não paga IS."""
        for c in self.categorias_do_seletivo:
            if c.chave == categoria:
                return c.aliquota * self.fator_seletivo
        return ZERO


def normalizar_cclasstrib(valor: object) -> str:
    """O cClassTrib tem seis dígitos com zero à esquerda. A planilha devolve
    `200003` como número e `000001` como 1 — sem isto, o padrão some."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.zfill(6) if texto.isdigit() else texto


def _d(texto: str) -> Decimal:
    return Decimal(texto)


# EC 132/2023, art. 128 do ADCT, e LC 214/2025. 2025 é o modelo atual.
CRONOGRAMA_LC_214: tuple[ParametrosDoAno, ...] = (
    ParametrosDoAno(2025, ZERO, ZERO, UM, True, True, False, False, "Modelo atual"),
    ParametrosDoAno(2026, _d("0.009"), _d("0.001"), UM, True, True, True, False,
                    "Teste: CBS 0,9% + IBS 0,1% compensáveis com PIS/COFINS"),
    ParametrosDoAno(2027, _d("0.087"), _d("0.001"), UM, False, False, False, True,
                    "CBS cheia (−0,1 p.p.), IBS 0,1%, fim do PIS/COFINS, IPI zerado"),
    ParametrosDoAno(2028, _d("0.087"), _d("0.001"), UM, False, False, False, True, "Idem 2027"),
    ParametrosDoAno(2029, _d("0.088"), _d("0.0177"), _d("0.9"), False, False, False, True,
                    "ICMS 90% / IBS 10%"),
    ParametrosDoAno(2030, _d("0.088"), _d("0.0354"), _d("0.8"), False, False, False, True,
                    "ICMS 80% / IBS 20%"),
    ParametrosDoAno(2031, _d("0.088"), _d("0.0531"), _d("0.7"), False, False, False, True,
                    "ICMS 70% / IBS 30%"),
    ParametrosDoAno(2032, _d("0.088"), _d("0.0708"), _d("0.6"), False, False, False, True,
                    "ICMS 60% / IBS 40%"),
    ParametrosDoAno(2033, _d("0.088"), _d("0.177"), ZERO, False, False, False, True,
                    "IBS/CBS pleno, ICMS extinto"),
)

GRUPOS_LC_214: tuple[GrupoDeAliquota, ...] = (
    GrupoDeAliquota("padrao", "Alíquota padrão", ZERO, frozenset({"000001"})),
    GrupoDeAliquota("reducao_60", "Redução de 60%", _d("0.6"),
                    frozenset({"200030", "200034", "200035", "200038"})),
    # Anexo I (cesta básica) e Anexo XV (hortícolas, frutas e ovos)
    GrupoDeAliquota("zero", "Alíquota zero", UM, frozenset({"200003", "200014"})),
)

# Hipóteses: dependem de lei ordinária. Bebida açucarada inclui as versões
# zero e diet, que dividem a NCM — o cadastro por SKU é que pode tirá-las.
SELETIVO_HIPOTESE: tuple[CategoriaDoSeletivo, ...] = (
    CategoriaDoSeletivo("fumo", "Cigarros e fumo", _d("2.5"), ("2402", "2403")),
    CategoriaDoSeletivo("alcool", "Bebidas alcoólicas", _d("0.5"),
                        ("2203", "2204", "2205", "2206", "2208")),
    CategoriaDoSeletivo("acucaradas", "Bebidas açucaradas", _d("0.32"),
                        ("22021000", "22029900")),
    CategoriaDoSeletivo("veiculos", "Veículos a combustão", _d("0.1"), ("87",)),
    CategoriaDoSeletivo("extracao", "Extração mineral e petróleo", _d("0.0025"),
                        ("25", "26", "27")),
)

CENARIO_BASE = Cenario(
    nome="Base — LC 214/2025, referência 26,5%, IS hipotético",
    anos=CRONOGRAMA_LC_214,
    grupos=GRUPOS_LC_214,
    categorias_do_seletivo=SELETIVO_HIPOTESE,
)
