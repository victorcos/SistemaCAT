"""Quadros da Gestão de IRPJ e CSLL (Lucro Real), no layout do MA.

Monta, a partir da ECF, o mesmo bloco "Gestão Fiscal" que o MA exporta:

    Lucro Líquido Antes do IRPJ
      (+) ADIÇÕES            -> por código e por indicador de relacionamento
      (-) EXCLUSÕES          -> idem
      (-) Compensação de prejuízo (do período e de períodos anteriores)
      =   LUCRO REAL
      15% + Adicional  (CSLL: 9%)
      (-) DEDUÇÕES           -> por código
      =   $ IMPOSTO A PAGAR
      Saldo das contas da Parte B do e-Lalur/e-Lacs

As colunas são mensais: um período trimestral cai no mês que o encerra
(T01 -> março), e os meses sem apuração aparecem zerados, como no MA.

Duas linhas do MA vêm de fontes que este sistema não lê (DCTF e e-CAC).
Elas continuam no relatório, em branco e marcadas como externas, para não
passar a impressão de que o valor declarado é zero.

Portado do projeto Quebra de SPED em 22/09/2026. **Estes quadros ainda não
passaram pelo gabarito do MA** — a validação de 59 competências cobriu PIS e
COFINS; o IRPJ/CSLL de referência é de outra empresa e a comparação ficou
pendente lá também. Rodar `tools/validar_gestao.py` contra um export real é o
que falta para eles valerem tanto quanto os de PIS/COFINS.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cat.infraestrutura.gestao.ecf import (
    ApuracaoECF,
    LinhaLalur,
    PeriodoECF,
    normalizar,
)
from cat.infraestrutura.gestao.modelos import Linha, Quadro, Relatorio
from cat.infraestrutura.gestao.rotulos import IND_RELACAO, cortar_descricao_ecf

TRIBUTOS = ("IRPJ", "CSLL")


@dataclass
class _Dados:
    """Valores de uma competência, já calculados."""
    lucro_liquido: int = 0
    adicoes: int = 0
    exclusoes: int = 0
    comp_periodo: int = 0
    comp_anteriores: int = 0
    base: int = 0
    lucro_liquido_rural: int = 0
    adicoes_rural: int = 0
    exclusoes_rural: int = 0
    comp_periodo_rural: int = 0
    comp_anteriores_rural: int = 0
    base_rural: int = 0
    imposto: int = 0            # 15% (IRPJ) ou 9% (CSLL)
    adicional: int = 0          # IRPJ: adicional de 10%; CSLL: adição de créditos
    deducoes: int = 0
    estimativa_base: int = 0
    a_pagar: int = 0
    diferenca_obra: int = 0
    postergado: int = 0
    saldo_parte_b: int = 0
    det_adicoes: dict[str, tuple[str, int]] = field(default_factory=dict)
    det_exclusoes: dict[str, tuple[str, int]] = field(default_factory=dict)
    det_deducoes: dict[str, tuple[str, int]] = field(default_factory=dict)
    det_parte_b: dict[str, tuple[str, int]] = field(default_factory=dict)
    rel_adicoes: dict[str, int] = field(default_factory=dict)
    rel_exclusoes: dict[str, int] = field(default_factory=dict)
    det_rel_adicoes: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)
    det_rel_exclusoes: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)


def _somar_desc(linhas: dict[str, tuple[str, int]], *termos: str) -> int:
    """Soma as linhas N6xx cuja descrição contém todos os termos informados."""
    total = 0
    for desc, valor in linhas.values():
        norm = normalizar(desc)
        if all(t in norm for t in termos):
            total += valor
    return total


def _deducoes(linhas: dict[str, tuple[str, int]]) -> dict[str, tuple[str, int]]:
    """Linhas de dedução: no N630/N670 são as que começam com "(-)"."""
    return {cod: (desc, valor) for cod, (desc, valor) in linhas.items()
            if desc.strip().startswith("(-)")}


def _lancamentos(linhas: list[LinhaLalur], tipo: str, rural: bool) -> list[LinhaLalur]:
    """Adições/exclusões detalhadas: têm indicador de relacionamento.

    As linhas de total ("SOMA DAS ADIÇÕES") vêm com o mesmo tipo, mas sem
    indicador — usá-las dobraria o valor.
    """
    return [x for x in linhas
            if x.tipo == tipo and x.ind_relacao and x.rural == rural]


def _calculadas(linhas: list[LinhaLalur], rural: bool) -> list[LinhaLalur]:
    return [x for x in linhas if x.tipo == "L" and x.rural == rural]


def _compensacoes(linhas: list[LinhaLalur], rural: bool) -> tuple[int, int]:
    """(compensação do próprio período, compensação de períodos anteriores)."""
    periodo = anteriores = 0
    for x in linhas:
        if x.tipo != "P" or x.rural != rural:
            continue
        norm = normalizar(x.descricao)
        if "PROPRIO PERIODO" in norm:
            periodo += x.valor
        else:
            anteriores += x.valor
    if periodo == 0:
        # Sem linha própria: a compensação do período é a diferença entre o
        # lucro real antes e depois da compensação do próprio período.
        #
        # SUSPEITA, 22/09/2026 — essa diferença é a compensação **inteira**, e
        # não só a do próprio período: havendo compensação de prejuízo
        # anterior, o mesmo valor sai nas duas linhas. Provavelmente a dedução
        # só deveria valer quando `anteriores == 0`. Não mudei porque estes
        # quadros nunca passaram por gabarito — o IRPJ/CSLL de referência é de
        # outra empresa —, e mudar regra fiscal por raciocínio, sem arquivo que
        # confirme, foi exatamente como o erro da natureza do crédito nasceu.
        # Ver tests/unidade/test_gestao_ecf.py, que fixa o comportamento atual.
        calc = _calculadas(linhas, rural)
        if len(calc) >= 3:
            periodo = calc[1].valor - calc[2].valor
    return periodo, anteriores


def _dados_do_periodo(p: PeriodoECF, tributo: str) -> _Dados:
    lalur = p.lalur if tributo == "IRPJ" else p.lacs
    calculo = p.n630 if tributo == "IRPJ" else p.n670
    base_decl = p.n500 if tributo == "IRPJ" else p.n650
    sigla_conta = "I" if tributo == "IRPJ" else "C"
    d = _Dados()

    for rural in (False, True):
        calc = _calculadas(lalur, rural)
        lucro = calc[0].valor if calc else 0
        final = calc[-1].valor if calc else 0
        adic = _lancamentos(lalur, "A", rural)
        excl = _lancamentos(lalur, "E", rural)
        comp_per, comp_ant = _compensacoes(lalur, rural)
        if rural:
            d.lucro_liquido_rural, d.base_rural = lucro, final
            d.adicoes_rural = sum(x.valor for x in adic)
            d.exclusoes_rural = sum(x.valor for x in excl)
            d.comp_periodo_rural, d.comp_anteriores_rural = comp_per, comp_ant
            continue
        d.lucro_liquido, d.base = lucro, final
        d.adicoes = sum(x.valor for x in adic)
        d.exclusoes = sum(x.valor for x in excl)
        d.comp_periodo, d.comp_anteriores = comp_per, comp_ant
        for x in adic:
            _acumular_detalhe(d.det_adicoes, x)
            d.rel_adicoes[x.ind_relacao] = d.rel_adicoes.get(x.ind_relacao, 0) + x.valor
            _acumular_detalhe_rel(d.det_rel_adicoes, x)
        for x in excl:
            _acumular_detalhe(d.det_exclusoes, x)
            d.rel_exclusoes[x.ind_relacao] = d.rel_exclusoes.get(x.ind_relacao, 0) + x.valor
            _acumular_detalhe_rel(d.det_rel_exclusoes, x)

    if tributo == "IRPJ":
        d.imposto = _somar_desc(calculo, "ALIQUOTA DE 15")
        d.adicional = _somar_desc(calculo, "ADICIONAL")
        d.a_pagar = _somar_desc(calculo, "IMPOSTO DE RENDA A PAGAR")
        d.diferenca_obra = _somar_desc(calculo, "CUSTO ORCADO")
        d.postergado = _somar_desc(calculo, "POSTERGADO")
        d.estimativa_base = _somar_desc(base_decl, "ESTIMATIVA")
    else:
        d.imposto = _somar_desc(calculo, "CONTRIBUICAO SOCIAL SOBRE O LUCRO LIQUIDO POR ATIVIDADE")
        d.adicional = _somar_desc(calculo, "ADICAO DE CREDITOS")
        d.a_pagar = _somar_desc(calculo, "CSLL A PAGAR")
        d.diferenca_obra = _somar_desc(calculo, "CUSTO ORCADO")
        d.postergado = _somar_desc(calculo, "POSTERGADA")

    det = _deducoes(calculo)
    d.det_deducoes = det
    d.deducoes = sum(valor for _, valor in det.values())

    for conta in p.parte_b:
        if conta.tributo != sigla_conta:
            continue
        desc, acumulado = d.det_parte_b.get(conta.codigo, (conta.descricao, 0))
        d.det_parte_b[conta.codigo] = (desc or conta.descricao, acumulado + conta.saldo_final)
    d.saldo_parte_b = sum(valor for _, valor in d.det_parte_b.values())
    return d


def _acumular_detalhe(destino: dict[str, tuple[str, int]], x: LinhaLalur) -> None:
    desc, valor = destino.get(x.codigo, (x.descricao, 0))
    destino[x.codigo] = (desc, valor + x.valor)


def _acumular_detalhe_rel(destino: dict[tuple[str, str], tuple[str, int]], x: LinhaLalur) -> None:
    chave = (x.ind_relacao, x.codigo)
    desc, valor = destino.get(chave, (x.descricao, 0))
    destino[chave] = (desc, valor + x.valor)


def _meses_continuos(meses: list[str]) -> list[str]:
    """Do primeiro ao último mês, sem furos — o MA mostra os meses vazios."""
    if not meses:
        return []
    ordenados = sorted(meses)
    ano, mes = (int(x) for x in ordenados[0].split("-"))
    fim = ordenados[-1]
    saida = []
    atual = f"{ano:04d}-{mes:02d}"
    while atual <= fim:
        saida.append(atual)
        mes += 1
        if mes == 13:
            ano, mes = ano + 1, 1
        atual = f"{ano:04d}-{mes:02d}"
    return saida


def _rotulo_codigo(codigo: str, descricao: str) -> str:
    return f"{codigo} - {cortar_descricao_ecf(descricao)}"


def montar_relatorio_irpj_csll(apuracoes: list[ApuracaoECF], tributo: str) -> Relatorio:
    """Monta a gestão de IRPJ ou CSLL a partir de uma ou mais ECFs (uma por ano)."""
    if tributo not in TRIBUTOS:
        raise ValueError(f"tributo inválido: {tributo!r} (esperado IRPJ ou CSLL)")
    if not apuracoes:
        raise ValueError("nenhuma ECF informada")

    dados: dict[str, _Dados] = {}
    avisos: list[str] = []
    for ap in sorted(apuracoes, key=lambda a: a.dt_ini):
        if ap.forma_tributacao and ap.forma_tributacao != "1":
            avisos.append(
                f"ECF {ap.dt_fin[-4:]}: forma de tributação {ap.forma_tributacao} não é "
                "Lucro Real (código 1). Os quadros de Lucro Real podem sair vazios."
            )
        for p in ap.periodos:
            d = _dados_do_periodo(p, tributo)
            dados[p.mes] = d  # ECF mais recente do mesmo mês prevalece
            calculado = d.imposto + d.adicional - d.deducoes
            if d.a_pagar and abs(calculado - d.a_pagar) > 1:
                avisos.append(
                    f"{p.mes}: {tributo} a pagar declarado na ECF "
                    f"(R$ {d.a_pagar / 100:,.2f}) difere do calculado pela própria ECF "
                    f"(R$ {calculado / 100:,.2f})."
                )
        for motivo, n in ap.descartes.items():
            avisos.append(f"ECF {ap.dt_fin[-4:]}: {n} linha(s) ignorada(s) — {motivo}.")

    periodos = _meses_continuos(list(dados))
    linhas = _montar_linhas(dados, periodos, tributo)
    titulo = f"1. {tributo} - LUCRO REAL"
    base = sorted(apuracoes, key=lambda a: a.dt_ini)[-1]
    return Relatorio(
        tributo=tributo, cnpj=base.cnpj, razao_social=base.razao_social,
        periodos=periodos, quadros=[Quadro("1", titulo, linhas)], avisos=avisos,
    )


def _montar_linhas(dados: dict[str, _Dados], periodos: list[str], tributo: str) -> list[Linha]:
    irpj = tributo == "IRPJ"
    nome_base = "LUCRO REAL" if irpj else "Base de Cálculo CSLL"
    lalur = "e-Lalur" if irpj else "e-Lacs"
    # Texto das compensações como no MA ("de Prejuízos" no IRPJ, "da Base
    # Negativa" na CSLL — sem plural nesta).
    comp_periodo = ("de Prejuízo do Período" if irpj else "da Base Negativa do Período")
    comp_anteriores = ("de Prejuízos Anteriores" if irpj else "da Base Negativa Anteriores")
    comp_periodo_rural = comp_periodo + " Rural"
    comp_anteriores_rural = ("de Prejuízos Anteriores Rural" if irpj else "da Base Negativa Rural")

    def valores(fn) -> dict[str, int]:
        return {p: fn(dados[p]) if p in dados else 0 for p in periodos}

    def linha(rotulo: str, fn, nivel: int = 1) -> Linha:
        return Linha(rotulo, valores(fn), nivel=nivel)

    def titulo(rotulo: str, nivel: int) -> Linha:
        return Linha(rotulo, {p: None for p in periodos}, nivel=nivel, titulo=True)

    def externo(rotulo: str) -> Linha:
        return Linha(rotulo, {p: None for p in periodos}, nivel=1, externo=True)

    def detalhe(campo: str, nivel: int) -> list[Linha]:
        """Uma linha por código com valor em alguma competência.

        A ECF traz a tabela de códigos inteira, quase toda zerada (mais de
        800 linhas de adição); o MA lista só as que têm movimento.
        """
        codigos: dict[str, str] = {}
        for d in dados.values():
            for cod, (desc, valor) in getattr(d, campo).items():
                if valor:
                    codigos.setdefault(cod, desc)
        saida = []
        for cod in sorted(codigos, key=lambda c: _rotulo_codigo(c, codigos[c])):
            saida.append(Linha(
                _rotulo_codigo(cod, codigos[cod]),
                {p: getattr(dados[p], campo).get(cod, ("", 0))[1] if p in dados else 0
                 for p in periodos},
                nivel=nivel,
            ))
        return saida

    def por_relacionamento(campo_rel: str, campo_det: str, rotulo_grupo: str,
                           rotulo_detalhe: str) -> list[Linha]:
        indicadores = sorted({ind for d in dados.values()
                              for ind, valor in getattr(d, campo_rel).items() if valor})
        saida: list[Linha] = []
        for ind in indicadores:
            saida.append(Linha(
                f"          {ind} - {IND_RELACAO.get(ind, 'Relacionamento ' + ind)}",
                {p: getattr(dados[p], campo_rel).get(ind, 0) if p in dados else 0 for p in periodos},
                nivel=2,
            ))
            saida.append(titulo(f"          {rotulo_detalhe}", 3))
            codigos: dict[str, str] = {}
            for d in dados.values():
                for (i, cod), (desc, valor) in getattr(d, campo_det).items():
                    if i == ind and valor:
                        codigos.setdefault(cod, desc)
            for cod in sorted(codigos, key=lambda c: _rotulo_codigo(c, codigos[c])):
                saida.append(Linha(
                    f"               {_rotulo_codigo(cod, codigos[cod])}",
                    {p: getattr(dados[p], campo_det).get((ind, cod), ("", 0))[1] if p in dados else 0
                     for p in periodos},
                    nivel=4,
                ))
        if not saida:
            saida.append(titulo(f"          {rotulo_grupo} — sem lançamentos", 2))
        return saida

    L: list[Linha] = [
        linha(f"     Lucro Líquido Antes do {tributo}", lambda d: d.lucro_liquido),
        linha("            (+) ADIÇÕES", lambda d: d.adicoes),
        titulo("     2. ADIÇÕES - LUCRO REAL", 2),
        *[Linha(f"          {l.rotulo}", l.valores, nivel=3) for l in detalhe("det_adicoes", 3)],
        titulo("     8. ADIÇÃO POR RELACIONAMENTO", 2),
        *por_relacionamento("rel_adicoes", "det_rel_adicoes",
                            "ADIÇÃO POR RELACIONAMENTO", "12. ADIÇÃO POR RELACIONAMENTO/DETALHE"),
        linha("            (-) EXCLUSÕES", lambda d: d.exclusoes),
        titulo("     3. EXCLUSÕES - LUCRO REAL", 2),
        *[Linha(f"          {l.rotulo}", l.valores, nivel=3) for l in detalhe("det_exclusoes", 3)],
        titulo("     9. EXCLUSÃO POR RELACIONAMENTO", 2),
        *por_relacionamento("rel_exclusoes", "det_rel_exclusoes",
                            "EXCLUSÃO POR RELACIONAMENTO", "13. EXCLUSÃO POR RELACIONAMENTO/DETALHE"),
        linha(f"               (-) Compensação {comp_periodo}", lambda d: d.comp_periodo, 2),
        linha(f"               (-) Compensação {comp_anteriores}", lambda d: d.comp_anteriores, 2),
        linha(f"               =  {nome_base}", lambda d: d.base, 1),
        linha(f"     Lucro Líquido Antes do {tributo} Atividade Rural", lambda d: d.lucro_liquido_rural),
        linha("            (+) ADIÇÕES Rural", lambda d: d.adicoes_rural, 2),
        linha("            (-) EXCLUSÕES Rural", lambda d: d.exclusoes_rural, 2),
        linha(f"               (-) Compensação {comp_periodo_rural}", lambda d: d.comp_periodo_rural, 2),
        linha(f"               (-) Compensação {comp_anteriores_rural}", lambda d: d.comp_anteriores_rural, 2),
        linha(f"               =  {nome_base} Atividade Rural", lambda d: d.base_rural, 1),
    ]
    if irpj:
        L += [
            linha("        ☛ Alíquota de 15%", lambda d: d.imposto),
            linha("        ☛ Adicional", lambda d: d.adicional),
        ]
    else:
        L += [
            linha("        ☛ Contribuição 9%", lambda d: d.imposto),
            linha("        ☛ Adição Créditos CSLL Depreciação Anterior", lambda d: d.adicional),
        ]
    L += [
        linha("            (-) DEDUÇÕES", lambda d: d.deducoes),
        titulo("     4. DEDUÇÕES - LUCRO REAL", 2),
        *[Linha(f"          {l.rotulo}", l.valores, nivel=3) for l in detalhe("det_deducoes", 3)],
    ]
    if irpj:
        L.append(linha("     ESTIMATIVA/SUSPENSÃO/REDUÇÃO - Base de Cálculo", lambda d: d.estimativa_base))
        L.append(linha("         $ IMPOSTO DE RENDA A PAGAR", lambda d: d.a_pagar))
        L.append(linha("     Imposto de Renda - Diferença Obra", lambda d: d.diferenca_obra))
        L.append(linha("     Imposto de Renda Postergado", lambda d: d.postergado))
    else:
        L.append(linha("         $ CSLL A PAGAR", lambda d: d.a_pagar))
        L.append(linha("     Contribuição Social - Diferença Obra", lambda d: d.diferenca_obra))
        L.append(linha("     Contribuição Social Postergado", lambda d: d.postergado))
    L += [
        linha(f"       ➦   Saldo das Contas da Parte B do {lalur}", lambda d: d.saldo_parte_b),
        titulo(f"     16. DETALHAMENTO DA PARTE B DO {lalur.upper()}", 2),
        *[Linha(f"          {l.rotulo}", l.valores, nivel=3) for l in detalhe("det_parte_b", 3)],
        externo("     Valor do Débito Apurado na DCTF"),
        externo("     e-CAC - Pagamentos Consolidados"),
    ]
    return L
