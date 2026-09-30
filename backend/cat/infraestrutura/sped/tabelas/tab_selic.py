"""A SELIC mensal, para corrigir o indébito do Tema 69.

A restituição de tributo pago a maior se corrige pela **Selic acumulada**, e a
regra da Receita é específica: soma-se a Selic de cada mês **a partir do mês
seguinte ao do pagamento** até o mês **anterior** ao da restituição, e
acrescenta-se **1%** referente ao mês da restituição.

## Por que a tabela é mensal e não acumulada

A acumulada de uma competência **cresce a cada mês que passa** sem a
restituição. Uma tabela de acumuladas copiada de um relatório daria o número
certo no dia em que foi copiada e errado no mês seguinte — calado, que é o pior
modo de errar dinheiro. Guardando a mensal e acumulando na hora, o cálculo
envelhece sozinho.

## De onde vieram estes números

Da série 4390 do SGS do Banco Central — "Taxa de juros: Selic acumulada no
mês" —, que é a mesma que a Receita publica para corrigir indébito. São 105
taxas, de 01/2018 a 09/2026, baixadas da API e geradas no arquivo, não
transcritas:

    https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json

**Que esta é a série certa não foi suposto, foi medido.** As diferenças entre
competências consecutivas do gabarito do 903 da DMINAS (138.358 linhas,
30/09/2026) batem com a 4390 nos **56 meses** que o gabarito cobre, de 04/2021
a 11/2025 — e a validação completa fecha 100% usando esta tabela, sem pedir a
acumulada emprestada ao gabarito.

**Foi assim que se achou um erro de um mês.** A primeira versão desta tabela
derivou as taxas do gabarito e guardou cada diferença sob a competência de
origem. Só que `acumulada(M) - acumulada(M+1)` é a Selic de **M+1**, não a de
M: a série inteira estava deslocada um mês. Como a conferência do 903 rodava
com `--selic-do-gabarito`, a tabela nunca era exercitada e o deslocamento não
aparecia em lugar nenhum. Por isso `tests/unidade/test_tab_selic.py` compara
com a 4390 mês a mês: uma tabela que ninguém exerce é uma tabela que ninguém
confere.

**Manutenção.** Uma linha por mês, como já se faz com `tab_cfop`. `acumulada()`
recusa o que não sabe em vez de devolver número a menos: corrigir por SELIC
incompleta é pedir restituição menor do que a devida, e ninguém confere um
número que veio pequeno.
"""

from __future__ import annotations

from decimal import Decimal

# o 1% do mês da restituição, que a regra manda somar por último
UM_PORCENTO_DO_MES_FINAL = Decimal("1")


class SelicDesconhecida(LookupError):
    """Pediram acumulada até um mês que a série ainda não cobre."""


# "aaaa-mm" -> Selic do mês, em por cento
MENSAL: dict[str, Decimal] = {
    "2018-01": Decimal("0.58"),
    "2018-02": Decimal("0.47"),
    "2018-03": Decimal("0.53"),
    "2018-04": Decimal("0.52"),
    "2018-05": Decimal("0.52"),
    "2018-06": Decimal("0.52"),
    "2018-07": Decimal("0.54"),
    "2018-08": Decimal("0.57"),
    "2018-09": Decimal("0.47"),
    "2018-10": Decimal("0.54"),
    "2018-11": Decimal("0.49"),
    "2018-12": Decimal("0.49"),
    "2019-01": Decimal("0.54"),
    "2019-02": Decimal("0.49"),
    "2019-03": Decimal("0.47"),
    "2019-04": Decimal("0.52"),
    "2019-05": Decimal("0.54"),
    "2019-06": Decimal("0.47"),
    "2019-07": Decimal("0.57"),
    "2019-08": Decimal("0.50"),
    "2019-09": Decimal("0.46"),
    "2019-10": Decimal("0.48"),
    "2019-11": Decimal("0.38"),
    "2019-12": Decimal("0.37"),
    "2020-01": Decimal("0.38"),
    "2020-02": Decimal("0.29"),
    "2020-03": Decimal("0.34"),
    "2020-04": Decimal("0.28"),
    "2020-05": Decimal("0.24"),
    "2020-06": Decimal("0.21"),
    "2020-07": Decimal("0.19"),
    "2020-08": Decimal("0.16"),
    "2020-09": Decimal("0.16"),
    "2020-10": Decimal("0.16"),
    "2020-11": Decimal("0.15"),
    "2020-12": Decimal("0.16"),
    "2021-01": Decimal("0.15"),
    "2021-02": Decimal("0.13"),
    "2021-03": Decimal("0.20"),
    "2021-04": Decimal("0.21"),
    "2021-05": Decimal("0.27"),
    "2021-06": Decimal("0.31"),
    "2021-07": Decimal("0.36"),
    "2021-08": Decimal("0.43"),
    "2021-09": Decimal("0.44"),
    "2021-10": Decimal("0.49"),
    "2021-11": Decimal("0.59"),
    "2021-12": Decimal("0.77"),
    "2022-01": Decimal("0.73"),
    "2022-02": Decimal("0.76"),
    "2022-03": Decimal("0.93"),
    "2022-04": Decimal("0.83"),
    "2022-05": Decimal("1.03"),
    "2022-06": Decimal("1.02"),
    "2022-07": Decimal("1.03"),
    "2022-08": Decimal("1.17"),
    "2022-09": Decimal("1.07"),
    "2022-10": Decimal("1.02"),
    "2022-11": Decimal("1.02"),
    "2022-12": Decimal("1.12"),
    "2023-01": Decimal("1.12"),
    "2023-02": Decimal("0.92"),
    "2023-03": Decimal("1.17"),
    "2023-04": Decimal("0.92"),
    "2023-05": Decimal("1.12"),
    "2023-06": Decimal("1.07"),
    "2023-07": Decimal("1.07"),
    "2023-08": Decimal("1.14"),
    "2023-09": Decimal("0.97"),
    "2023-10": Decimal("1.00"),
    "2023-11": Decimal("0.92"),
    "2023-12": Decimal("0.89"),
    "2024-01": Decimal("0.97"),
    "2024-02": Decimal("0.80"),
    "2024-03": Decimal("0.83"),
    "2024-04": Decimal("0.89"),
    "2024-05": Decimal("0.83"),
    "2024-06": Decimal("0.79"),
    "2024-07": Decimal("0.91"),
    "2024-08": Decimal("0.87"),
    "2024-09": Decimal("0.84"),
    "2024-10": Decimal("0.93"),
    "2024-11": Decimal("0.79"),
    "2024-12": Decimal("0.93"),
    "2025-01": Decimal("1.01"),
    "2025-02": Decimal("0.99"),
    "2025-03": Decimal("0.96"),
    "2025-04": Decimal("1.06"),
    "2025-05": Decimal("1.14"),
    "2025-06": Decimal("1.10"),
    "2025-07": Decimal("1.28"),
    "2025-08": Decimal("1.16"),
    "2025-09": Decimal("1.22"),
    "2025-10": Decimal("1.28"),
    "2025-11": Decimal("1.05"),
    "2025-12": Decimal("1.22"),
    "2026-01": Decimal("1.16"),
    "2026-02": Decimal("1.00"),
    "2026-03": Decimal("1.21"),
    "2026-04": Decimal("1.09"),
    "2026-05": Decimal("1.07"),
    "2026-06": Decimal("1.12"),
    "2026-07": Decimal("1.22"),
    "2026-08": Decimal("1.09"),
    "2026-09": Decimal("1.03"),
}


def _meses(de: str, ate: str) -> list[str]:
    """Os meses de `de` a `ate`, inclusive, no formato "aaaa-mm"."""
    a, m = (int(x) for x in de.split("-"))
    fim = tuple(int(x) for x in ate.split("-"))
    saida = []
    while (a, m) <= fim:
        saida.append(f"{a:04d}-{m:02d}")
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return saida


def acumulada(competencia: str, ate: str) -> Decimal:
    """A Selic acumulada de uma competência até o mês da restituição.

    `competencia` e `ate` em "aaaa-mm". A regra corrige a partir do mês seguinte
    ao do **pagamento**, e o PIS/COFINS de uma competência se paga no mês
    seguinte ao dela — vence no dia 25. Logo a soma começa **dois** meses depois
    da competência, vai até o mês **anterior** ao da restituição, e acrescenta
    1% pelo mês da restituição.

    Esse mês de defasagem vale dinheiro e não estava aqui: as 57 competências do
    gabarito do 903 batiam todas com um mês a mais de Selic. Corrigido e medido
    — as 57 fecham exatas contra a coluna "SELIC Acumulada" do MA.

    Levanta `SelicDesconhecida` quando falta algum mês do caminho: devolver a
    soma do que se sabe daria restituição a menos, e número pequeno ninguém
    confere.
    """
    pagamento = _seguinte(competencia)
    if pagamento >= ate:
        return UM_PORCENTO_DO_MES_FINAL
    caminho = _meses(_seguinte(pagamento), _anterior(ate))
    faltam = [m for m in caminho if m not in MENSAL]
    if faltam:
        raise SelicDesconhecida(
            f"A série da Selic não cobre {', '.join(faltam[:3])}"
            f"{' e mais ' + str(len(faltam) - 3) if len(faltam) > 3 else ''}. "
            f"Ela vai até {max(MENSAL)}; acrescente os meses em `tab_selic.MENSAL`.")
    return sum((MENSAL[m] for m in caminho), UM_PORCENTO_DO_MES_FINAL)


def _seguinte(mes: str) -> str:
    a, m = (int(x) for x in mes.split("-"))
    return f"{a + 1:04d}-01" if m == 12 else f"{a:04d}-{m + 1:02d}"


def _anterior(mes: str) -> str:
    a, m = (int(x) for x in mes.split("-"))
    return f"{a - 1:04d}-12" if m == 1 else f"{a:04d}-{m - 1:02d}"


def ultimo_mes() -> str:
    """O mês mais novo da série. A tela usa para avisar antes de calcular."""
    return max(MENSAL)


def alcanca(ate: str) -> bool:
    """A série cobre uma restituição neste mês?

    A acumulada soma até o mês **anterior** ao da restituição, então a série
    pode terminar um mês antes de `ate` e ainda servir. Quem pergunta é a tela,
    antes de mandar ler os SPED: descobrir que falta mês depois de uma hora de
    leitura é descobrir tarde.
    """
    return _anterior(ate) <= ultimo_mes()
