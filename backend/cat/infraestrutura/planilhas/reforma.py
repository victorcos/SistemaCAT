"""A planilha da simulação da reforma: premissas, DRE, trajetória e as visões.

Montada na rodada, e não a pedido: o download serve o arquivo pronto, do mesmo
instante e do mesmo cenário que a tela mostra.

**As premissas vêm primeiro.** Pedido do revisor (13/10/2026) e do cliente
(23/10/2026): quem abre tem de ler que o preço e o volume são constantes, o que
é lei e o que é hipótese, antes de ver qualquer margem. Cada aba de resultado
repete o cenário no título, porque aba copiada para outro arquivo perde o
contexto.

**Percentual é sempre recalculado da soma.** Nenhuma coluna de margem é média
de margens: a linha do capítulo é a soma das linhas, e a margem é a dela.
"""

from __future__ import annotations

from decimal import Decimal

import xlsxwriter

from cat.infraestrutura.analitico.reforma import ANOS_EM_DESTAQUE, LinhaDaVisao, ResultadoDaSimulacao

AZUL = "#002366"
DOURADO = "#E59A19"

PREMISSAS = (
    "Preço e volume constantes: a receita bruta do período-base vale para todos os anos, e a "
    "variação de imposto recai sobre a margem. Mede o tamanho do efeito; não é previsão de preço "
    "nem de venda.",
    "IBS e CBS \"por fora\": base = receita bruta − ICMS − PIS/COFINS (do ano), dividida por "
    "(1 + alíquota efetiva). Alíquota efetiva = (CBS + IBS do ano) × (1 − redução do cClassTrib).",
    "Custo de compra = custo líquido (sem ICMS, IPI e PIS/COFINS) + PIS/COFINS sem crédito "
    "(CST 70/72/73/75), que já está no preço do fornecedor e fica no custo em todos os anos. "
    "O IPI da entrada é custo até 2026 e sai em 2027.",
    "Crédito de IBS/CBS = (custo de compra + IS) × alíquota efetiva do item. Aproximado pelo custo "
    "das mercadorias vendidas no período, não pelas compras; sem crédito sobre despesas; como se "
    "todo fornecedor gerasse crédito pleno (Simples, produtor rural e monofásico ainda não tratados).",
    "ICMS: débito e crédito de hoje × fator do ano (1 até 2028; 0,9 a 0,6 de 2029 a 2032; 0 em 2033).",
    "2026: CBS 0,9% e IBS 0,1% destacados e compensados com PIS/COFINS — sem efeito líquido.",
    "Imposto Seletivo (a partir de 2027): alíquotas são HIPÓTESES, à espera de lei ordinária. "
    "Monofásico, cobrado do fabricante sobre o custo sem tributos, chega como custo e sem crédito; "
    "entra na base do IBS/CBS do fornecedor, e por isso o crédito sobe na mesma proporção.",
    "Alíquota de referência 26,5% (CBS 8,8% + IBS 17,7%): estimativa até a fixação pelo Senado.",
    "Variação teórica de preço: quanto a receita bruta teria de variar para preservar o lucro "
    "bruto em reais do ano-base, com o ICMS tratado proporcional ao preço. Não é recomendação "
    "de reajuste.",
)


class _Formatos:
    def __init__(self, livro: xlsxwriter.Workbook) -> None:
        self.titulo = livro.add_format({"bold": True, "font_size": 14, "font_color": AZUL})
        self.subtitulo = livro.add_format({"italic": True, "font_color": "#555555"})
        self.cabecalho = livro.add_format({"bold": True, "bg_color": AZUL, "font_color": "white",
                                           "text_wrap": True, "valign": "vcenter", "border": 1})
        self.texto = livro.add_format({"text_wrap": True, "valign": "top"})
        self.reais = livro.add_format({"num_format": "#,##0.00"})
        self.reais_negrito = livro.add_format({"num_format": "#,##0.00", "bold": True,
                                               "top": 1})
        self.pct = livro.add_format({"num_format": "0.00%"})
        self.pct_negrito = livro.add_format({"num_format": "0.00%", "bold": True})
        self.inteiro = livro.add_format({"num_format": "#,##0"})
        self.negrito = livro.add_format({"bold": True})
        self.destaque = livro.add_format({"bold": True, "font_color": DOURADO})


def _f(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


def _escrever(aba, linha: int, coluna: int, valor, formato=None) -> None:
    if valor is None:
        aba.write_blank(linha, coluna, None, formato)
    elif isinstance(valor, (int, float, Decimal)):
        aba.write_number(linha, coluna, float(valor), formato)
    else:
        aba.write_string(linha, coluna, str(valor), formato)


def _titulo(aba, fmt: _Formatos, titulo: str, r: ResultadoDaSimulacao) -> None:
    aba.write(0, 0, titulo, fmt.titulo)
    aba.write(1, 0, f"Cenário: {r.cenario.nome} · competências {', '.join(sorted(r.competencias))}"
                    " · R$ do período-base · preço e volume constantes", fmt.subtitulo)


def _premissas(livro, fmt: _Formatos, r: ResultadoDaSimulacao) -> None:
    aba = livro.add_worksheet("Premissas")
    aba.set_column(0, 0, 14)
    aba.set_column(1, 8, 16)
    _titulo(aba, fmt, "Simulação da reforma tributária do consumo — premissas", r)
    aba.write(3, 0, "Simulação preliminar sujeita à validação de premissas.", fmt.destaque)
    linha = 5
    for i, texto in enumerate(PREMISSAS, start=1):
        aba.merge_range(linha, 0, linha, 8, f"{i}. {texto}", fmt.texto)
        aba.set_row(linha, 45)
        linha += 1

    linha += 1
    aba.write(linha, 0, "Cronograma (legislação: EC 132/2023, art. 128 do ADCT; LC 214/2025)",
              fmt.negrito)
    linha += 1
    for c, nome in enumerate(("Ano", "CBS", "IBS", "Fator ICMS", "PIS/COFINS", "IPI",
                              "Teste 2026", "IS vigente", "Observação")):
        aba.write(linha, c, nome, fmt.cabecalho)
    for a in r.cenario.anos:
        linha += 1
        aba.write_number(linha, 0, a.ano)
        aba.write_number(linha, 1, float(a.cbs), fmt.pct)
        aba.write_number(linha, 2, float(a.ibs), fmt.pct)
        aba.write_number(linha, 3, float(a.fator_icms), fmt.pct)
        for c, flag in enumerate((a.pis_cofins_vigente, a.ipi_vigente, a.teste_compensavel,
                                  a.is_vigente), start=4):
            aba.write(linha, c, "sim" if flag else "não")
        aba.write(linha, 8, a.observacao)

    linha += 2
    aba.write(linha, 0, "Grupos de alíquota por cClassTrib (anexos da LC 214/2025)", fmt.negrito)
    linha += 1
    for c, nome in enumerate(("Grupo", "Redução", "Alíquota plena", "cClassTrib")):
        aba.write(linha, c, nome, fmt.cabecalho)
    plena = r.cenario.anos[-1].cbs + r.cenario.anos[-1].ibs
    for g in r.cenario.grupos:
        linha += 1
        aba.write(linha, 0, g.rotulo)
        aba.write_number(linha, 1, float(g.reducao), fmt.pct)
        aba.write_number(linha, 2, float(plena * (1 - g.reducao)), fmt.pct)
        aba.write(linha, 3, ", ".join(sorted(g.cclasstribs)))

    linha += 2
    aba.write(linha, 0, "Imposto Seletivo — HIPÓTESES (dependem de lei ordinária)", fmt.negrito)
    linha += 1
    for c, nome in enumerate(("Categoria", "Alíquota", "NCM (começo)")):
        aba.write(linha, c, nome, fmt.cabecalho)
    for c in r.cenario.categorias_do_seletivo:
        linha += 1
        aba.write(linha, 0, c.rotulo)
        aba.write_number(linha, 1, float(c.aliquota * r.cenario.fator_seletivo), fmt.pct)
        aba.write(linha, 2, ", ".join(c.prefixos))
    if r.cenario.fator_seletivo != 1:
        aba.write(linha + 1, 0, f"Alíquotas já multiplicadas pelo fator de sensibilidade "
                                f"{r.cenario.fator_seletivo}.", fmt.subtitulo)


# as linhas da DRE: rótulo, atributo do ResultadoDoAno, se é subtração, formato
_DRE = (
    ("Receita bruta de vendas", "receita_bruta", False),
    ("(−) ICMS sobre vendas", "debito_icms", True),
    ("(−) PIS/COFINS sobre vendas", "debito_pis_cofins", True),
    ("(−) IPI sobre vendas", "debito_ipi", True),
    ("(−) CBS sobre vendas", "debito_cbs", True),
    ("(−) IBS sobre vendas", "debito_ibs", True),
    ("(=) Receita líquida", "receita_liquida", False),
    ("(−) CMV — líquido de tributos recuperáveis", "cmv", True),
    ("(=) Lucro bruto", "lucro_bruto", False),
    ("Margem bruta (% da receita bruta)", "margem", None),
    ("", None, None),
    ("Composição do CMV", None, None),
    ("Custo de compra (constante por hipótese)", "custo_de_compra", False),
    ("(+) Créditos recuperáveis (ICMS, PIS/COFINS, CBS, IBS)", "creditos_recuperaveis", False),
    ("(+) IPI — não recuperável", "ipi_custo", False),
    ("(+) Imposto Seletivo — não recuperável", "seletivo", False),
    ("(=) Valor bruto das compras (nota fiscal)", "valor_bruto_das_compras", False),
    ("(−) Créditos recuperáveis (ativo fiscal)", "creditos_recuperaveis", True),
    ("(=) CMV levado à DRE", "cmv", False),
    ("", None, None),
    ("Apuração fiscal (memória, fora da DRE)", None, None),
    ("ICMS a recolher", "icms_a_recolher", False),
    ("PIS/COFINS a recolher", "pis_cofins_a_recolher", False),
    ("CBS a recolher", "cbs_a_recolher", False),
    ("IBS a recolher", "ibs_a_recolher", False),
    ("(=) Tributo líquido a recolher", "total_a_recolher", False),
    ("Carga líquida (% da receita bruta)", "carga_liquida", None),
    ("Carga com IS (% da receita bruta)", "carga_com_seletivo", None),
    ("CBS/IBS de teste destacado e compensado (informativo)", "teste_destacado", False),
)


def _dre(livro, fmt: _Formatos, r: ResultadoDaSimulacao) -> None:
    aba = livro.add_worksheet("DRE 2025-2033")
    total = r.total
    anos = sorted(total.anos)
    aba.set_column(0, 0, 52)
    aba.set_column(1, len(anos) + 1, 16)
    _titulo(aba, fmt, "DRE, composição do CMV e apuração fiscal — total da empresa", r)
    aba.write(3, 0, "R$", fmt.cabecalho)
    for c, ano in enumerate(anos, start=1):
        aba.write_number(3, c, ano, fmt.cabecalho)
    for i, (rotulo, atributo, subtrai) in enumerate(_DRE, start=4):
        negrito = rotulo.startswith("(=)")
        aba.write(i, 0, rotulo, fmt.negrito if negrito or atributo is None else None)
        if atributo is None:
            continue
        for c, ano in enumerate(anos, start=1):
            valor = getattr(total.anos[ano], atributo)
            if subtrai is None:
                _escrever(aba, i, c, _f(valor), fmt.pct_negrito if "Margem" in rotulo else fmt.pct)
            else:
                _escrever(aba, i, c, _f(-valor if subtrai else valor),
                          fmt.reais_negrito if negrito else fmt.reais)
    linha = 4 + len(_DRE) + 1
    aba.write(linha, 0, "Variação teórica de preço p/ preservar o lucro bruto de "
                        f"{r.cenario.ano_base}", fmt.negrito)
    for c, ano in enumerate(anos, start=1):
        _escrever(aba, linha, c, _f(total.variacao_teorica(ano)), fmt.pct)
    aba.freeze_panes(4, 1)


def _visao(livro, fmt: _Formatos, r: ResultadoDaSimulacao, visao: str, nome_da_aba: str,
           rotulo_da_chave: str, extras: tuple[tuple[str, int], ...] = ()) -> None:
    linhas: list[LinhaDaVisao] = r.visoes[visao]
    aba = livro.add_worksheet(nome_da_aba)
    _titulo(aba, fmt, f"{nome_da_aba} — lucro bruto, margem e carga por ano", r)
    destaque = [a for a in ANOS_EM_DESTAQUE if a in r.total.anos]
    cabecalho = [rotulo_da_chave, "Descrição", *[n for n, _ in extras], "Linhas", "SKUs",
                 "Receita bruta", "% da receita", "IS pleno (R$)"]
    cabecalho += [f"Lucro bruto {a}" for a in destaque]
    cabecalho += [f"Margem {a}" for a in destaque]
    cabecalho += [f"Carga c/ IS {a}" for a in destaque]
    cabecalho += [f"Var. teórica de preço {a}" for a in destaque if a != r.cenario.ano_base]
    for c, nome in enumerate(cabecalho):
        aba.write(3, c, nome, fmt.cabecalho)
    aba.set_row(3, 32)
    aba.set_column(0, 0, 14)
    aba.set_column(1, 1, 38)
    aba.set_column(2, len(cabecalho), 15)
    receita_total = r.total.base.receita_bruta
    for i, l in enumerate(linhas, start=4):
        c = 0
        aba.write_string(i, c, l.chave); c += 1
        aba.write_string(i, c, l.rotulo if l.rotulo != l.chave else ""); c += 1
        for _, extra in extras:
            e = r.enquadramentos.get(l.chave)
            aba.write_string(i, c, ("" if e is None else
                                    (e.ncm, e.grupo_rotulo, e.categoria_seletivo,
                                     e.categoria_mercadologica)[extra]))
            c += 1
        aba.write_number(i, c, l.linhas, fmt.inteiro); c += 1
        aba.write_number(i, c, l.skus, fmt.inteiro); c += 1
        aba.write_number(i, c, float(l.base.receita_bruta), fmt.reais); c += 1
        _escrever(aba, i, c, _f(l.base.receita_bruta / receita_total) if receita_total else None,
                  fmt.pct); c += 1
        aba.write_number(i, c, float(l.base.seletivo_pleno), fmt.reais); c += 1
        for a in destaque:
            aba.write_number(i, c, float(l.anos[a].lucro_bruto), fmt.reais); c += 1
        for a in destaque:
            _escrever(aba, i, c, _f(l.anos[a].margem), fmt.pct); c += 1
        for a in destaque:
            _escrever(aba, i, c, _f(l.anos[a].carga_com_seletivo), fmt.pct); c += 1
        for a in destaque:
            if a != r.cenario.ano_base:
                _escrever(aba, i, c, _f(l.variacao_teorica(a)), fmt.pct); c += 1
    aba.freeze_panes(4, 2)
    aba.autofilter(3, 0, 3 + len(linhas), len(cabecalho) - 1)


def _trajetoria(livro, fmt: _Formatos, r: ResultadoDaSimulacao, visao: str, nome_da_aba: str
                ) -> None:
    """Uma chave por linha, um ano por coluna: lucro bruto e margem. É a
    linha do tempo que a primeira simulação montou por capítulo."""
    linhas = r.visoes[visao]
    anos = sorted(r.total.anos)
    aba = livro.add_worksheet(nome_da_aba)
    _titulo(aba, fmt, f"{nome_da_aba} — lucro bruto e margem, ano a ano", r)
    cab = ["Chave", "Descrição", "Receita bruta", *[f"LB {a}" for a in anos],
           *[f"Margem {a}" for a in anos]]
    for c, nome in enumerate(cab):
        aba.write(3, c, nome, fmt.cabecalho)
    aba.set_column(0, 0, 12)
    aba.set_column(1, 1, 30)
    aba.set_column(2, len(cab), 14)
    for i, l in enumerate(linhas, start=4):
        aba.write_string(i, 0, l.chave)
        aba.write_string(i, 1, l.rotulo if l.rotulo != l.chave else "")
        aba.write_number(i, 2, float(l.base.receita_bruta), fmt.reais)
        for j, a in enumerate(anos):
            aba.write_number(i, 3 + j, float(l.anos[a].lucro_bruto), fmt.reais)
            _escrever(aba, i, 3 + len(anos) + j, _f(l.anos[a].margem), fmt.pct)
    aba.freeze_panes(4, 2)


def _fora_da_conta(livro, fmt: _Formatos, r: ResultadoDaSimulacao) -> None:
    aba = livro.add_worksheet("Fora da conta")
    _titulo(aba, fmt, "O que ficou fora da simulação, e por quê", r)
    aba.set_column(0, 0, 50)
    aba.set_column(1, 4, 16)
    aba.set_column(5, 5, 80)
    linha = 3
    aba.write(linha, 0, "Exclusões — linhas sem custo de compra (decisão de método)", fmt.negrito)
    linha += 1
    for c, nome in enumerate(("Motivo", "Linhas", "SKUs", "Receita líquida")):
        aba.write(linha, c, nome, fmt.cabecalho)
    for motivo, conta in sorted(r.exclusoes.items(), key=lambda kv: -kv[1].receita_liquida):
        linha += 1
        aba.write(linha, 0, motivo)
        aba.write_number(linha, 1, conta.linhas, fmt.inteiro)
        aba.write_number(linha, 2, len(conta.itens), fmt.inteiro)
        aba.write_number(linha, 3, float(conta.receita_liquida), fmt.reais)
    linha += 2
    aba.write(linha, 0, "Pendências de cadastro — deveriam ser zero antes de apresentar",
              fmt.destaque)
    linha += 1
    for c, nome in enumerate(("Motivo", "Linhas", "SKUs", "Receita bruta", "", "Exemplos")):
        aba.write(linha, c, nome, fmt.cabecalho)
    if not r.pendencias:
        linha += 1
        aba.write(linha, 0, "Nenhuma: todo item com custo tem classificação e grupo.")
    for motivo, conta in sorted(r.pendencias.items(), key=lambda kv: -kv[1].receita_bruta):
        linha += 1
        aba.write(linha, 0, motivo)
        aba.write_number(linha, 1, conta.linhas, fmt.inteiro)
        aba.write_number(linha, 2, len(conta.itens), fmt.inteiro)
        aba.write_number(linha, 3, float(conta.receita_bruta), fmt.reais)
        aba.write(linha, 5, "; ".join(conta.exemplos), fmt.texto)
    if r.conflitos_de_cadastro:
        linha += 2
        aba.write(linha, 0, f"{r.conflitos_de_cadastro} SKU(s) com classificação diferente em "
                            "dois arquivos — valeu o primeiro", fmt.destaque)
        aba.write(linha, 5, "; ".join(r.exemplos_de_conflito), fmt.texto)


def gerar(r: ResultadoDaSimulacao, destino: str) -> None:
    livro = xlsxwriter.Workbook(destino, {"strings_to_numbers": False})
    try:
        fmt = _Formatos(livro)
        _premissas(livro, fmt, r)
        _dre(livro, fmt, r)
        _visao(livro, fmt, r, "grupo", "Por grupo", "Grupo")
        _visao(livro, fmt, r, "uf", "Por UF", "UF")
        _visao(livro, fmt, r, "competencia", "Por mês", "Competência")
        _visao(livro, fmt, r, "categoria_seletivo", "Imposto Seletivo", "Categoria")
        _visao(livro, fmt, r, "capitulo", "Por capítulo NCM", "Capítulo")
        _trajetoria(livro, fmt, r, "capitulo", "Capítulo - linha do tempo")
        _visao(livro, fmt, r, "posicao", "Por posição NCM", "Posição")
        if any(l.chave for l in r.visoes["categoria_mercadologica"]):
            _visao(livro, fmt, r, "categoria_mercadologica", "Por categoria", "Categoria")
        _visao(livro, fmt, r, "familia", "Por família", "Família")
        _visao(livro, fmt, r, "sku", "Por SKU", "SKU",
               extras=(("NCM", 0), ("Grupo", 1), ("Categoria IS", 2)))
        _fora_da_conta(livro, fmt, r)
    finally:
        livro.close()
