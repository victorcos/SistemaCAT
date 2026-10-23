"""A rodada da simulação da reforma: das planilhas do lote às visões projetadas.

## O caminho

1. **Classificação.** Lê a revisão de SKU: NCM revisada, cClassTrib e, quando
   houver, a categoria do Imposto Seletivo marcada à mão e a categoria
   mercadológica do cliente.
2. **Base.** Lê as saídas custeadas linha a linha e soma por competência × UF ×
   item — a célula. Linha sem custo não entra: vira exclusão, contada pelo
   motivo que a própria base dá (transformado, sem compra, embalagem
   divergente).
3. **Enquadramento.** Cada célula ganha grupo de alíquota, categoria do IS,
   capítulo, posição e família. Item sem cadastro, ou com cClassTrib que o
   cenário não conhece, vira **pendência**: sai da conta e aparece com a receita
   que deixou de ser simulada. Não se chuta alíquota padrão para ele.
4. **Visões.** Para cada visão, soma as células por (chave, redução) e projeta
   cada ano. Somar antes de projetar é exato porque o modelo é linear
   (`dominio/reforma/projecao.py`); a redução entra na chave porque é ela que
   não é somável.

## Exclusão e pendência são coisas diferentes

A exclusão é decisão de método, tomada antes: a linha não tem custo de compra e
não há como medir margem sem ele. A pendência é falta de cadastro, e se resolve
classificando o item. Por isso as duas aparecem separadas, e a pendência com o
aviso de que deveria ser zero antes de apresentar o resultado.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Callable

from cat.dominio.reforma.dre import conferir
from cat.dominio.reforma.enquadramento import (
    capitulo, categoria_do_seletivo, familia, normalizar_ncm, subcapitulo)
from cat.dominio.reforma.parametros import CENARIO_BASE, ZERO, Cenario
from cat.dominio.reforma.projecao import (
    BaseDaLinha, ResultadoDoAno, projetar, receita_bruta_requerida)
from cat.infraestrutura.arquivos.planilhas_da_reforma import (
    ItemClassificado, LinhaDaBase, ler_base, ler_classificacao, normalizar)
from cat.log import obter_log

log = obter_log(__name__)

CAMPOS_DA_BASE = ("receita_bruta", "debito_icms", "debito_ipi", "debito_pis_cofins",
                  "credito_icms", "credito_pis_cofins", "custo_liquido",
                  "pis_cofins_sem_credito", "ipi_entrada")

# as visões, na ordem das abas. "sku" é a mais fina; "total" é uma chave só
VISOES = ("total", "grupo", "competencia", "uf", "capitulo", "posicao",
          "categoria_seletivo", "categoria_mercadologica", "familia", "sku")

PENDENCIA_SEM_CADASTRO = "Item sem cadastro de classificação"
PENDENCIA_SEM_GRUPO = "cClassTrib sem grupo no cenário"
PENDENCIA_SELETIVO = "Categoria do IS ilegível no cadastro (valeu a regra da NCM)"

EXEMPLOS_POR_PENDENCIA = 20


@dataclass
class Andamento:
    arquivos: int = 0
    linhas: int = 0


@dataclass
class Celula:
    competencia: str
    uf: str
    item: str
    descricao: str = ""
    base: BaseDaLinha = field(default_factory=BaseDaLinha)
    linhas: int = 0
    quantidade: Decimal = ZERO
    lojas: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Enquadramento:
    ncm: str
    grupo: str
    grupo_rotulo: str
    reducao: Decimal
    categoria_seletivo: str
    origem_seletivo: str
    categoria_mercadologica: str
    descricao: str


@dataclass
class Contagem:
    linhas: int = 0
    receita_bruta: Decimal = ZERO
    receita_liquida: Decimal = ZERO
    itens: set[str] = field(default_factory=set)
    exemplos: list[str] = field(default_factory=list)


@dataclass
class ChaveDaVisao:
    """O que se soma numa chave de visão, além da base: quantas linhas e SKUs."""

    rotulo: str = ""
    linhas: int = 0
    itens: set[str] = field(default_factory=set)
    por_reducao: dict[Decimal, BaseDaLinha] = field(default_factory=dict)


@dataclass(frozen=True)
class LinhaDaVisao:
    """Uma chave de uma visão, projetada em todos os anos."""

    visao: str
    chave: str
    rotulo: str
    linhas: int
    skus: int
    base: BaseDaLinha
    anos: dict[int, ResultadoDoAno]
    receita_requerida: dict[int, Decimal | None]

    def variacao_teorica(self, ano: int) -> Decimal | None:
        requerida = self.receita_requerida.get(ano)
        if requerida is None or not self.base.receita_bruta:
            return None
        return requerida / self.base.receita_bruta - 1


@dataclass
class ResultadoDaSimulacao:
    cenario: Cenario
    arquivos_de_base: int = 0
    arquivos_de_classificacao: int = 0
    linhas_lidas: int = 0
    linhas_consideradas: int = 0
    itens_classificados: int = 0
    conflitos_de_cadastro: int = 0
    exemplos_de_conflito: list[str] = field(default_factory=list)
    lojas: set[str] = field(default_factory=set)
    competencias: set[str] = field(default_factory=set)
    exclusoes: dict[str, Contagem] = field(default_factory=dict)
    pendencias: dict[str, Contagem] = field(default_factory=dict)
    visoes: dict[str, list[LinhaDaVisao]] = field(default_factory=dict)
    enquadramentos: dict[str, Enquadramento] = field(default_factory=dict)
    segundos: float = 0.0

    @property
    def total(self) -> LinhaDaVisao:
        return self.visoes["total"][0]


def _somar_linha(celula: Celula, linha: LinhaDaBase) -> None:
    celula.base = celula.base + BaseDaLinha(**{c: getattr(linha, c) for c in CAMPOS_DA_BASE})
    celula.linhas += 1
    celula.quantidade += linha.quantidade
    celula.lojas.add(linha.loja)
    if not celula.descricao:
        celula.descricao = linha.descricao


def _motivo_da_exclusao(linha: LinhaDaBase) -> str | None:
    """Por que a linha não entra, ou nada se entra. A base diz o motivo: o
    status do custo de quem não achou compra, ou a marcação manual da análise."""
    sem_custo = (not linha.tem_custo or linha.custo_liquido <= 0
                 or normalizar(linha.base_da_analise).startswith("sem custo"))
    if not sem_custo:
        return None
    for texto in (linha.status_custo, linha.base_da_analise):
        if texto and not normalizar(texto).startswith("sem custo - fora"):
            return texto
    return "Sem custo de compra"


def _ler_classificacao(caminhos: list[str], resultado: ResultadoDaSimulacao
                       ) -> dict[str, ItemClassificado]:
    """O cadastro de todos os arquivos. O mesmo SKU em dois arquivos com
    cClassTrib ou NCM diferentes é conflito: vale o primeiro, e o aviso diz
    quantos — escolher em silêncio seria decidir a alíquota sem dizer."""
    itens: dict[str, ItemClassificado] = {}
    for caminho in caminhos:
        resultado.arquivos_de_classificacao += 1
        for item in ler_classificacao(caminho):
            ja = itens.get(item.item)
            if ja is None:
                itens[item.item] = item
            elif (ja.cclasstrib, normalizar_ncm(ja.ncm)) != (item.cclasstrib, normalizar_ncm(item.ncm)):
                resultado.conflitos_de_cadastro += 1
                if len(resultado.exemplos_de_conflito) < EXEMPLOS_POR_PENDENCIA:
                    resultado.exemplos_de_conflito.append(
                        f"{item.item}: {ja.cclasstrib}/{ja.ncm} × {item.cclasstrib}/{item.ncm}")
    resultado.itens_classificados = len(itens)
    return itens


def _enquadrar(celula: Celula, cadastro: ItemClassificado | None, cenario: Cenario,
               resultado: ResultadoDaSimulacao) -> Enquadramento | None:
    def pendente(motivo: str, detalhe: str) -> None:
        conta = resultado.pendencias.setdefault(motivo, Contagem())
        conta.linhas += celula.linhas
        conta.receita_bruta += celula.base.receita_bruta
        if celula.item not in conta.itens and len(conta.exemplos) < EXEMPLOS_POR_PENDENCIA:
            conta.exemplos.append(f"{celula.item} {celula.descricao[:40]} {detalhe}".strip())
        conta.itens.add(celula.item)

    if cadastro is None:
        pendente(PENDENCIA_SEM_CADASTRO, "")
        return None
    grupo = cenario.grupo(cadastro.cclasstrib)
    if grupo is None:
        pendente(PENDENCIA_SEM_GRUPO, f"(cClassTrib {cadastro.cclasstrib or 'vazio'})")
        return None
    ncm = normalizar_ncm(cadastro.ncm)
    try:
        seletivo = categoria_do_seletivo(ncm, cadastro.categoria_seletivo, cenario)
    except ValueError:
        pendente(PENDENCIA_SELETIVO, f"({cadastro.categoria_seletivo})")
        seletivo = categoria_do_seletivo(ncm, None, cenario)
    return Enquadramento(
        ncm=ncm, grupo=grupo.chave, grupo_rotulo=grupo.rotulo, reducao=grupo.reducao,
        categoria_seletivo=seletivo.chave, origem_seletivo=seletivo.origem,
        categoria_mercadologica=cadastro.categoria_mercadologica,
        descricao=cadastro.descricao or celula.descricao)


def _chave(visao: str, celula: Celula, e: Enquadramento, cenario: Cenario) -> tuple[str, str]:
    """A chave e o rótulo da célula numa visão."""
    if visao == "total":
        return "TOTAL", "Total"
    if visao == "grupo":
        return e.grupo, e.grupo_rotulo
    if visao == "competencia":
        return celula.competencia, celula.competencia
    if visao == "uf":
        return celula.uf or "--", celula.uf or "(sem UF)"
    if visao == "capitulo":
        c = capitulo(e.ncm)
        return c, c
    if visao == "posicao":
        p = subcapitulo(e.ncm)
        return p, p
    if visao == "categoria_seletivo":
        for c in cenario.categorias_do_seletivo:
            if c.chave == e.categoria_seletivo:
                return c.chave, c.rotulo
        return "", "Sem Imposto Seletivo"
    if visao == "categoria_mercadologica":
        return e.categoria_mercadologica or "", e.categoria_mercadologica or "(sem categoria)"
    if visao == "familia":
        f = familia(e.descricao)
        return f, f
    # "sku"
    return celula.item, e.descricao


def _projetar_visao(visao: str, chaves: dict[str, ChaveDaVisao], cenario: Cenario
                    ) -> list[LinhaDaVisao]:
    linhas: list[LinhaDaVisao] = []
    base_do_ano_base = cenario.do_ano(cenario.ano_base)
    for chave, acumulado in chaves.items():
        anos: dict[int, ResultadoDoAno] = {}
        requerida: dict[int, Decimal | None] = {}
        base_total = BaseDaLinha()
        for reducao, base in acumulado.por_reducao.items():
            base_total = base_total + base
            lucro_base = projetar(base, reducao, base_do_ano_base).lucro_bruto
            for params in cenario.anos:
                r = projetar(base, reducao, params)
                anos[params.ano] = anos[params.ano] + r if params.ano in anos else r
                rb = receita_bruta_requerida(base, reducao, params, lucro_base)
                atual = requerida.get(params.ano, ZERO)
                requerida[params.ano] = None if rb is None or atual is None else atual + rb
        linhas.append(LinhaDaVisao(visao, chave, acumulado.rotulo, acumulado.linhas,
                                   len(acumulado.itens), base_total, anos, requerida))
    linhas.sort(key=lambda l: -l.base.receita_bruta)
    return linhas


def simular(bases: list[str], classificacoes: list[str], cenario: Cenario = CENARIO_BASE,
            avisar: Callable[[Andamento], None] | None = None,
            deve_parar: Callable[[], None] | None = None) -> ResultadoDaSimulacao:
    """A simulação inteira. `deve_parar` levanta `LeituraCancelada` quando pedem."""
    inicio = time.time()
    resultado = ResultadoDaSimulacao(cenario=cenario)
    andamento = Andamento()
    cadastro = _ler_classificacao(classificacoes, resultado)
    log.info("classificação lida", extra={"itens": len(cadastro),
                                          "arquivos": len(classificacoes),
                                          "conflitos": resultado.conflitos_de_cadastro})

    celulas: dict[tuple[str, str, str], Celula] = {}
    for caminho in bases:
        resultado.arquivos_de_base += 1
        for linha in ler_base(caminho, deve_parar):
            andamento.linhas += 1
            resultado.linhas_lidas += 1
            if andamento.linhas % 20000 == 0 and avisar is not None:
                avisar(andamento)
            motivo = _motivo_da_exclusao(linha)
            if motivo is not None:
                conta = resultado.exclusoes.setdefault(motivo, Contagem())
                conta.linhas += 1
                conta.receita_bruta += linha.receita_bruta
                conta.receita_liquida += linha.valor_liquido
                conta.itens.add(linha.item)
                continue
            competencia = linha.competencia.strftime("%Y-%m") if linha.competencia else "----"
            chave = (competencia, linha.uf, linha.item)
            celula = celulas.get(chave)
            if celula is None:
                celula = celulas[chave] = Celula(competencia, linha.uf, linha.item)
            _somar_linha(celula, linha)
        andamento.arquivos += 1
        if avisar is not None:
            avisar(andamento)
        log.info("base lida", extra={"arquivo": caminho, "linhas": andamento.linhas})

    visoes: dict[str, dict[str, ChaveDaVisao]] = {v: defaultdict(ChaveDaVisao) for v in VISOES}
    for celula in celulas.values():
        e = _enquadrar(celula, cadastro.get(celula.item), cenario, resultado)
        if e is None:
            continue
        resultado.enquadramentos.setdefault(celula.item, e)
        resultado.linhas_consideradas += celula.linhas
        resultado.lojas |= celula.lojas
        resultado.competencias.add(celula.competencia)
        base = replace(celula.base, seletivo_pleno=celula.base.custo_liquido
                       * cenario.aliquota_do_seletivo(e.categoria_seletivo))
        for visao in VISOES:
            chave, rotulo = _chave(visao, celula, e, cenario)
            acumulado = visoes[visao][chave]
            acumulado.rotulo = rotulo
            acumulado.linhas += celula.linhas
            acumulado.itens.add(celula.item)
            anterior = acumulado.por_reducao.get(e.reducao)
            acumulado.por_reducao[e.reducao] = base if anterior is None else anterior + base

    if deve_parar is not None:
        deve_parar()
    if not visoes["total"]:
        raise ValueError(
            "Nenhuma linha da base entrou na simulação: ou nenhuma tem custo de compra, ou "
            "nenhum item tem classificação com cClassTrib conhecido. Veja exclusões e pendências.")
    for visao in VISOES:
        resultado.visoes[visao] = _projetar_visao(visao, visoes[visao], cenario)

    for ano, r in resultado.total.anos.items():
        falhas = [c for c in conferir(r) if not c.fecha]
        if falhas:
            # identidade que não fecha é fórmula errada, e número errado não sai
            raise RuntimeError(f"Conferência de {ano} não fecha: "
                               + "; ".join(f"{c.nome} ({c.diferenca})" for c in falhas))
    resultado.segundos = round(time.time() - inicio, 1)
    log.info("simulação concluída", extra={
        "linhas": resultado.linhas_consideradas, "skus": len(resultado.enquadramentos),
        "pendencias": sum(c.linhas for c in resultado.pendencias.values()),
        "segundos": resultado.segundos})
    return resultado


# ---------------------------------------------------------------------------
# o resumo que a tela lê (vai para o diário da execução)
# ---------------------------------------------------------------------------

ANOS_EM_DESTAQUE = (2025, 2027, 2033)


def _n(valor: Decimal | None, casas: int = 2) -> float | None:
    return None if valor is None else round(float(valor), casas)


def _ano_serializado(ano: int, r: ResultadoDoAno, linha: LinhaDaVisao) -> dict:
    return {
        "ano": ano,
        "receita_bruta": _n(r.receita_bruta),
        "icms": _n(r.debito_icms), "pis_cofins": _n(r.debito_pis_cofins),
        "ipi": _n(r.debito_ipi), "cbs": _n(r.debito_cbs), "ibs": _n(r.debito_ibs),
        "receita_liquida": _n(r.receita_liquida),
        "custo_de_compra": _n(r.custo_de_compra), "ipi_custo": _n(r.ipi_custo),
        "seletivo": _n(r.seletivo), "cmv": _n(r.cmv),
        "lucro_bruto": _n(r.lucro_bruto), "margem": _n(r.margem, 6),
        "creditos": _n(r.creditos_recuperaveis),
        "valor_bruto_das_compras": _n(r.valor_bruto_das_compras),
        "a_recolher": _n(r.total_a_recolher), "carga": _n(r.carga_liquida, 6),
        "carga_com_seletivo": _n(r.carga_com_seletivo, 6),
        "teste_destacado": _n(r.teste_destacado),
        "variacao_teorica": _n(linha.variacao_teorica(ano), 6),
    }


def _linha_resumida(linha: LinhaDaVisao) -> dict:
    return {
        "chave": linha.chave, "rotulo": linha.rotulo, "linhas": linha.linhas,
        "skus": linha.skus, "receita_bruta": _n(linha.base.receita_bruta),
        "seletivo_pleno": _n(linha.base.seletivo_pleno),
        "anos": {str(a): {"lucro_bruto": _n(linha.anos[a].lucro_bruto),
                          "margem": _n(linha.anos[a].margem, 6),
                          "carga": _n(linha.anos[a].carga_liquida, 6),
                          "variacao_teorica": _n(linha.variacao_teorica(a), 6)}
                 for a in ANOS_EM_DESTAQUE if a in linha.anos},
    }


def serializar(r: ResultadoDaSimulacao) -> dict:
    total = r.total
    cenario = r.cenario
    return {
        "cenario": {
            "nome": cenario.nome,
            "fator_seletivo": _n(cenario.fator_seletivo, 4),
            "anos": [{"ano": a.ano, "cbs": _n(a.cbs, 6), "ibs": _n(a.ibs, 6),
                      "fator_icms": _n(a.fator_icms, 4), "observacao": a.observacao}
                     for a in cenario.anos],
            "grupos": [{"chave": g.chave, "rotulo": g.rotulo, "reducao": _n(g.reducao, 4),
                        "cclasstribs": sorted(g.cclasstribs)} for g in cenario.grupos],
            "seletivo": [{"chave": c.chave, "rotulo": c.rotulo,
                          "aliquota": _n(c.aliquota * cenario.fator_seletivo, 6),
                          "prefixos": list(c.prefixos)} for c in cenario.categorias_do_seletivo],
        },
        "base": {
            "arquivos": r.arquivos_de_base,
            "arquivos_de_classificacao": r.arquivos_de_classificacao,
            "linhas_lidas": r.linhas_lidas,
            "linhas_consideradas": r.linhas_consideradas,
            "skus": len(r.enquadramentos),
            "itens_classificados": r.itens_classificados,
            "lojas": len(r.lojas),
            "competencias": sorted(r.competencias),
            "receita_bruta": _n(total.base.receita_bruta),
            "conflitos_de_cadastro": r.conflitos_de_cadastro,
        },
        "exclusoes": [{"motivo": m, "linhas": c.linhas, "skus": len(c.itens),
                       "receita_bruta": _n(c.receita_bruta),
                       "receita_liquida": _n(c.receita_liquida)}
                      for m, c in sorted(r.exclusoes.items(), key=lambda kv: -kv[1].receita_liquida)],
        "pendencias": [{"motivo": m, "linhas": c.linhas, "skus": len(c.itens),
                        "receita_bruta": _n(c.receita_bruta), "exemplos": c.exemplos}
                       for m, c in sorted(r.pendencias.items(), key=lambda kv: -kv[1].receita_bruta)],
        "por_ano": [_ano_serializado(a, total.anos[a], total) for a in sorted(total.anos)],
        "por_grupo": [_linha_resumida(l) for l in r.visoes["grupo"]],
        "por_uf": [_linha_resumida(l) for l in r.visoes["uf"]],
        "por_seletivo": [_linha_resumida(l) for l in r.visoes["categoria_seletivo"]],
        "por_capitulo": [_linha_resumida(l) for l in r.visoes["capitulo"][:15]],
        "segundos": r.segundos,
    }
