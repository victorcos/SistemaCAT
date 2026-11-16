"""O de-para de um trabalho: o que o sistema propõe e o que já foi decidido.

As propostas saem da última movimentação concluída (`infraestrutura/analitico/
depara.py`) e não ficam gravadas: mudam quando a base muda. As decisões ficam,
na tabela `depara_item`, por empresa — quem grava é a API em C#.

Além dos pares, a resposta lista os **códigos sem par**: com saída e sem
entrada nem estoque, que nenhuma proposta nem decisão resolve. São os que ficam
negativos no razão, e os que vão para o cliente dizer de onde vieram — como a
RVZ fez na empresa 04 com os códigos de marketplace.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.apurar_suportado import movimentacao_concluida
from cat.dominio.depara.candidatos import (
    ItemParaCasar,
    Par,
    normalizar_codigo,
    ordenar_candidatos,
    propor,
    vale_sozinho,
)
from cat.infraestrutura.analitico.depara import itens_para_casar
from cat.infraestrutura.repositorios.modelos import DeParaDB, ProjetoDB, UsuarioDB
from cat.log import obter_log

log = obter_log(__name__)

LIMITE_SEM_PAR = 5000
# quantos candidatos a tela recebe de uma vez: o bastante para escolher sem
# virar rolagem infinita, e o de-para da empresa 04 nunca precisou de mais
LIMITE_DE_CANDIDATOS = 50


class SemMovimentacao(ValueError):
    """O trabalho ainda não tem movimentação para propor de-para."""


@dataclass(frozen=True)
class _Levantamento:
    """O que se sabe de um estabelecimento: os códigos, as propostas e o que
    já está resolvido.

    Existe para a tela e o relatório **contarem a mesma coisa**. Eram duas
    varreduras iguais escritas duas vezes, e no dia em que uma mudasse a
    planilha passaria a divergir do número na tela sem ninguém perceber.
    """

    cnpj: str
    itens: list[ItemParaCasar]
    propostos: list[Par]
    # códigos que alguma proposta toca, de um lado ou do outro
    cobertos: frozenset[str]
    # códigos que uma decisão gravada resolve: aprovados e seus destinos
    decididos: frozenset[str]

    def resolvido(self, codigo: str) -> bool:
        return codigo in self.cobertos or codigo in self.decididos

    @property
    def destinos(self) -> frozenset[str]:
        """Os códigos que recebem a ficha de outro — por proposta ou decisão."""
        return frozenset(p.destino for p in self.propostos) | self.decididos


def _levantar(itens: dict[str, list[ItemParaCasar]],
              decisoes: dict[tuple[str, str], DeParaDB]) -> Iterator[_Levantamento]:
    for cnpj, lista in sorted(itens.items()):
        propostos = propor(lista)
        aprovados = {o for (c, o), d in decisoes.items()
                     if d.situacao == "aprovado" and c in ("", cnpj)}
        destinos = {d.codigo_destino for (c, _), d in decisoes.items()
                    if d.situacao == "aprovado" and c in ("", cnpj)}
        yield _Levantamento(
            cnpj=cnpj, itens=lista, propostos=propostos,
            cobertos=frozenset(c for p in propostos for c in (p.origem, p.destino)),
            decididos=frozenset(aprovados | destinos))


def _carregar(projeto_id: int, sessao: Session):
    """A movimentação concluída, os códigos dela e as decisões da empresa.

    A tela e o relatório entram por aqui: duas leituras diferentes da mesma
    coisa divergem no dia em que uma mudar.
    """
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        raise LookupError("Trabalho não encontrado.")
    movimentos = movimentacao_concluida(projeto_id, sessao)
    if movimentos is None or not movimentos.pasta_de_trabalho:
        raise SemMovimentacao("Conclua a extração de movimentos antes: é dela que saem os códigos a casar.")

    itens = itens_para_casar(movimentos.pasta_de_trabalho)
    decisoes = {(d.cnpj, d.codigo_origem): d for d in sessao.scalars(
        select(DeParaDB).where(DeParaDB.empresa_id == projeto.empresa_id))}
    nomes = {u.id: u.nome_exibicao for u in sessao.scalars(
        select(UsuarioDB).where(UsuarioDB.id.in_({d.decidido_por for d in decisoes.values() if d.decidido_por})))}
    return projeto, movimentos, itens, decisoes, nomes


def candidatos_do_projeto(projeto_id: int, sessao: Session) -> dict:
    projeto, movimentos, itens, decisoes, nomes = _carregar(projeto_id, sessao)

    def decisao(cnpj: str, origem: str) -> DeParaDB | None:
        return decisoes.get((cnpj, origem)) or decisoes.get(("", origem))

    pares: list[dict] = []
    sem_par: list[dict] = []
    total_sem_par = 0
    precisavam_de_par = 0
    automaticos = 0
    vistas: set[tuple[str, str]] = set()
    for nivel in _levantar(itens, decisoes):
        cnpj = nivel.cnpj
        for p in nivel.propostos:
            d = decisao(cnpj, p.origem)
            vistas.add((d.cnpj, d.codigo_origem) if d else (cnpj, p.origem))
            # GTIN e sufixo valem por padrão: só há decisão gravada quando
            # alguém discorda, e discordar vence
            sozinho = d is None and vale_sozinho(p)
            automaticos += sozinho
            pares.append({
                "cnpj": cnpj, "origem": p.origem, "destino": p.destino, "fator": format(p.fator, "f"),
                "motivos": [m.value for m in p.motivos], "confianca": p.confianca.value,
                "explicacao": p.explicacao, "proposto": True, "automatico": sozinho,
                "travas": list(p.travas), "avisos": list(p.avisos),
                **_situacao(d, nomes, automatico=sozinho),
            })
        for item in nivel.itens:
            resolvido = nivel.resolvido(item.codigo)
            if item.tem_saida and not item.tem_origem:
                # **o denominador da cobertura.** Código com saída e sem entrada
                # é o que viraria ficha negativa e sairia do total; é esse o
                # problema que o de-para existe para resolver. Conta antes de
                # olhar se foi resolvido, senão a conta mede o que sobrou em
                # vez de medir o que havia
                precisavam_de_par += 1
            if item.tem_saida and not item.tem_origem and not resolvido:
                total_sem_par += 1
                if len(sem_par) < LIMITE_SEM_PAR:
                    sem_par.append({"cnpj": cnpj, "codigo": item.codigo, "descricao": item.descricao,
                                    "ncm": item.ncm, "saidas": format(item.saidas.normalize(), "f"),
                                    "codigo_normalizado": normalizar_codigo(item.codigo)})

    # decisões que não vieram de proposta: do cliente, do analista, ou de base antiga
    for (cnpj, origem), d in sorted(decisoes.items()):
        if (cnpj, origem) in vistas:
            continue
        pares.append({
            "cnpj": cnpj, "origem": origem, "destino": d.codigo_destino, "fator": format(d.fator.normalize(), "f"),
            "motivos": [d.motivo], "confianca": d.confianca, "explicacao": d.explicacao or "",
            # é decisão gravada: por definição alguém a tomou
            "proposto": False, "automatico": False, "travas": [], "avisos": [], **_situacao(d, nomes),
        })

    resumo = {
        "pares": len(pares),
        "pendentes": sum(p["situacao"] == "pendente" for p in pares),
        "aprovados": sum(p["situacao"] == "aprovado" for p in pares),
        # destes, os que valeram pela prova, sem ninguém decidir
        "automaticos": automaticos,
        "recusados": sum(p["situacao"] == "recusado" for p in pares),
        "sem_par": total_sem_par,
        # quantos códigos precisavam de par, e quantos deles já estão resolvidos
        # — por proposta do motor ou por decisão de quem trabalha. A conta sobe
        # conforme se decide, porque  já desconta o que foi aprovado
        "precisavam_de_par": precisavam_de_par,
        "resolvidos": precisavam_de_par - total_sem_par,
        "estabelecimentos": len(itens),
    }
    log.info("de-para do trabalho", extra={"projeto_id": projeto_id, "movimentos_execucao_id": movimentos.id,
                                           **resumo})
    return {"movimentos_execucao_id": movimentos.id, "empresa_id": projeto.empresa_id,
            "resumo": resumo, "pares": pares, "sem_par": sem_par}


def pares_que_valem_sozinhos(empresa_id: int, pasta_movimentos: str,
                             sessao: Session) -> list[tuple[str, str, str, Decimal]]:
    """Os pares de prova forte que entram na montagem sem ninguém aprovar.

    `(cnpj, origem, destino, fator)`. Deriva da movimentação a cada rodada, e
    não de linha gravada: a proposta nunca ficou guardada, e congelá-la agora
    faria o de-para envelhecer calado quando a base mudasse. O que fica
    gravado é a **discordância** — e qualquer decisão sobre o código, aprovada
    ou recusada, tira o par daqui: quem olhou manda.
    """
    decididos = {(d.cnpj, d.codigo_origem) for d in sessao.scalars(
        select(DeParaDB).where(DeParaDB.empresa_id == empresa_id))}
    achados: list[tuple[str, str, str, Decimal]] = []
    for cnpj, lista in sorted(itens_para_casar(pasta_movimentos).items()):
        for p in propor(lista):
            if vale_sozinho(p) and not {(cnpj, p.origem), ("", p.origem)} & decididos:
                achados.append((cnpj, p.origem, p.destino, p.fator))
    log.info("pares de de-para que valem sozinhos", extra={
        "empresa_id": empresa_id, "pares": len(achados), "decididos": len(decididos)})
    return achados


def _situacao(d: DeParaDB | None, nomes: dict[int, str], automatico: bool = False) -> dict:
    if d is None:
        # sem decisão: o par de prova forte já vale; o resto espera alguém. Em
        # nenhum dos dois casos há pessoa a creditar, e dizer que há seria
        # mentir no rastro de quem respondeu pelo número
        return {"situacao": "aprovado" if automatico else "pendente", "decidido_por": None,
                "decidido_em": None, "destino_decidido": None, "fator_decidido": None}
    return {"situacao": d.situacao, "decidido_por": nomes.get(d.decidido_por),
            "decidido_em": d.decidido_em.isoformat() if d.decidido_em else None,
            "destino_decidido": d.codigo_destino, "fator_decidido": format(d.fator.normalize(), "f")}


# ---------------------------------------------------------------------------
# O relatório: a entrada de um lado, a saída do outro
# ---------------------------------------------------------------------------
# O relatório antigo punha origem e destino na mesma linha, misturados com as
# marcas de suspeita, e não dizia qual dos dois lados era a entrada. Quem abria
# não distinguia o par do código solto, porque **código solto não aparecia**:
# só havia linha quando havia par.
#
# Aqui a linha tem dois blocos. À esquerda o código por onde o estoque entrou;
# à direita o código por onde ele saiu. Quando falta o par de um dos lados, o
# bloco daquele lado vem **vazio** — e é essa ponta vazia que mostra o que
# ainda precisa de decisão, sem precisar cruzar duas listas.
CASADO = "casado"
SAIDA_SEM_ENTRADA = "saída sem entrada"
ENTRADA_SEM_SAIDA = "entrada sem saída"

ROTULO_DO_MOTIVO = {
    "gtin": "mesmo GTIN",
    "sufixo": "código + sufixo",
    "kit": "kit",
    "descricao": "descrição e NCM",
    "cliente": "informado pelo cliente",
    "analista": "informado pelo analista",
}


def _rotulos(motivos) -> str:
    return ", ".join(ROTULO_DO_MOTIVO.get(str(m), str(m)) for m in motivos)


def _quantidade(valor: Decimal | None) -> Decimal | None:
    """Zero não vira célula: a ponta sem par tem de ficar visivelmente vazia."""
    return valor if valor else None


def _lado_da_entrada(item: ItemParaCasar | None, codigo: str) -> dict:
    if item is None:
        return {"codigo_entrada": codigo, "descricao_entrada": "", "ncm_entrada": "",
                "quantidade_entrada": None, "estoque_entrada": None}
    return {"codigo_entrada": item.codigo, "descricao_entrada": item.descricao,
            "ncm_entrada": item.ncm, "quantidade_entrada": _quantidade(item.entradas),
            "estoque_entrada": _quantidade(item.estoque_inicial)}


def _lado_da_saida(item: ItemParaCasar | None, codigo: str) -> dict:
    if item is None:
        return {"codigo_saida": codigo, "descricao_saida": "", "ncm_saida": "",
                "quantidade_saida": None}
    return {"codigo_saida": item.codigo, "descricao_saida": item.descricao,
            "ncm_saida": item.ncm, "quantidade_saida": _quantidade(item.saidas)}


VAZIO_NA_ENTRADA = {"codigo_entrada": "", "descricao_entrada": "", "ncm_entrada": "",
                    "quantidade_entrada": None, "estoque_entrada": None}
VAZIO_NA_SAIDA = {"codigo_saida": "", "descricao_saida": "", "ncm_saida": "",
                  "quantidade_saida": None}


def _lados(origem: str, destino: str,
           indice: dict[str, ItemParaCasar]) -> tuple[str, ItemParaCasar | None, str, ItemParaCasar | None]:
    """Qual dos dois códigos vai no bloco da entrada. `(cód, item, cód, item)`.

    A convenção do par é a **origem do lado da entrada**: ela é o código por
    onde o estoque entrou, e o destino é a ficha que recebe — a que tem a saída
    e ficaria negativa sem o par. Vale igual para a proposta do motor e para o
    par que o cliente informa.

    Mesmo assim o lado se confere pelo que o item **tem**, e não só pelo papel:
    base com código que compra e vende ao mesmo tempo existe, e pôr a entrada
    na coluna da saída é exatamente o tipo de troca silenciosa que fazia a
    planilha antiga não se entender. Na dúvida fica a convenção.
    """
    da_origem, do_destino = indice.get(origem), indice.get(destino)
    pela_convencao = (origem, da_origem, destino, do_destino)
    if da_origem is None or do_destino is None:
        return pela_convencao
    if da_origem.tem_origem and do_destino.tem_saida:
        return pela_convencao
    if do_destino.tem_origem and da_origem.tem_saida:
        return (destino, do_destino, origem, da_origem)
    return pela_convencao


@dataclass(frozen=True)
class RelatorioDoDePara:
    """As linhas e onde elas podem ser gravadas.

    A pasta vem junto porque é a da movimentação de onde o relatório saiu:
    quem escreve a planilha não deve ter de descobrir isso de novo, sob risco
    de gravar na pasta de outra rodada.
    """

    linhas: list[dict]
    pasta_de_trabalho: str
    movimentos_execucao_id: int


def linhas_do_relatorio(projeto_id: int, sessao: Session) -> RelatorioDoDePara:
    """Uma linha por par e por código solto, com a ponta que falta vazia."""
    projeto, movimentos, itens, decisoes, nomes = _carregar(projeto_id, sessao)

    def decisao(cnpj: str, origem: str) -> DeParaDB | None:
        return decisoes.get((cnpj, origem)) or decisoes.get(("", origem))

    linhas: list[dict] = []
    vistas: set[tuple[str, str]] = set()
    por_codigo: dict[tuple[str, str], ItemParaCasar] = {}
    for nivel in _levantar(itens, decisoes):
        cnpj = nivel.cnpj
        indice = {i.codigo: i for i in nivel.itens}
        por_codigo.update({(cnpj, c): i for c, i in indice.items()})
        destinos = nivel.destinos
        for p in nivel.propostos:
            d = decisao(cnpj, p.origem)
            vistas.add((d.cnpj, d.codigo_origem) if d else (cnpj, p.origem))
            aprovada = d is not None and d.situacao == "aprovado" and bool(d.codigo_destino)
            # o lado da entrada é o destino que o razão vai usar, e não o que
            # foi proposto: quem aprovou com outro destino manda
            destino = d.codigo_destino if aprovada else p.destino
            fator = d.fator if aprovada else p.fator
            avisos = list(p.avisos)
            if destino != p.destino:
                avisos.append(f"proposta era o código {p.destino}")
            sozinho = d is None and vale_sozinho(p)
            cod_entrada, item_entrada, cod_saida, item_saida = _lados(p.origem, destino, indice)
            linhas.append({
                "cnpj": cnpj, "casamento": CASADO,
                **_lado_da_entrada(item_entrada, cod_entrada),
                **_lado_da_saida(item_saida, cod_saida),
                "fator": fator, "ficha_do_codigo": destino,
                "como_casou": _rotulos(m.value for m in p.motivos),
                "confianca": p.confianca.value, "explicacao": p.explicacao,
                "vale_sozinho": "sim" if sozinho else "",
                "travas": "; ".join(p.travas), "avisos": "; ".join(avisos),
                **_decisao_no_relatorio(d, nomes, automatico=sozinho),
            })
        for item in nivel.itens:
            if nivel.resolvido(item.codigo):
                continue
            if item.tem_saida and not item.tem_origem:
                # saiu e não entrou: é a ficha que fica negativa, e o que o
                # de-para existe para resolver
                linhas.append({"cnpj": cnpj, "casamento": SAIDA_SEM_ENTRADA, **VAZIO_NA_ENTRADA,
                               **_lado_da_saida(item, item.codigo), **_SEM_PAR})
            elif item.tem_origem and not item.tem_saida and item.codigo not in destinos:
                # entrou e não saiu: é o candidato natural a par de alguma
                # linha de cima, e é por isso que ele vem na mesma planilha
                linhas.append({"cnpj": cnpj, "casamento": ENTRADA_SEM_SAIDA,
                               **_lado_da_entrada(item, item.codigo), **VAZIO_NA_SAIDA, **_SEM_PAR})

    # a decisão que não veio de proposta: do cliente, do analista, ou de base antiga
    for (cnpj, origem), d in sorted(decisoes.items()):
        if (cnpj, origem) in vistas:
            continue
        # a decisão pode ser do CNPJ vazio, que vale para todos: aí o item não
        # está indexado sob ele, e os dois lados saem só com o código
        indice = {c: i for (e, c), i in por_codigo.items() if e == cnpj}
        cod_entrada, item_entrada, cod_saida, item_saida = _lados(origem, d.codigo_destino, indice)
        linhas.append({
            "cnpj": cnpj, "casamento": CASADO,
            **_lado_da_entrada(item_entrada, cod_entrada),
            **_lado_da_saida(item_saida, cod_saida),
            "fator": d.fator, "ficha_do_codigo": d.codigo_destino,
            "como_casou": _rotulos([d.motivo]),
            "confianca": d.confianca or "", "explicacao": d.explicacao or "",
            "vale_sozinho": "", "travas": "", "avisos": "",
            **_decisao_no_relatorio(d, nomes),
        })
    log.info("relatório do de-para", extra={
        "projeto_id": projeto_id, "movimentos_execucao_id": movimentos.id,
        "empresa_id": projeto.empresa_id, "linhas": len(linhas),
        "casados": sum(l["casamento"] == CASADO for l in linhas),
        "saida_sem_entrada": sum(l["casamento"] == SAIDA_SEM_ENTRADA for l in linhas),
        "entrada_sem_saida": sum(l["casamento"] == ENTRADA_SEM_SAIDA for l in linhas)})
    return RelatorioDoDePara(linhas=linhas, pasta_de_trabalho=movimentos.pasta_de_trabalho or "",
                             movimentos_execucao_id=movimentos.id)


_SEM_PAR = {"fator": None, "ficha_do_codigo": "", "como_casou": "", "confianca": "", "situacao_do_par": "",
            "vale_sozinho": "", "decidido_por": "", "decidido_em": "",
            "explicacao": "", "travas": "", "avisos": ""}


def _decisao_no_relatorio(d: DeParaDB | None, nomes: dict[int, str],
                          automatico: bool = False) -> dict:
    if d is None:
        return {"situacao_do_par": "aprovado" if automatico else "pendente",
                "decidido_por": "", "decidido_em": ""}
    return {"situacao_do_par": d.situacao,
            "decidido_por": nomes.get(d.decidido_por, "") or "",
            "decidido_em": d.decidido_em.strftime("%d/%m/%Y") if d.decidido_em else ""}


class CodigoNaoEstaNaMovimentacao(LookupError):
    """Pediram candidatos para um código que a movimentação não tem."""


def candidatos_para_ligar(projeto_id: int, cnpj: str, origem: str, sessao: Session,
                          busca: str = "", limite: int = LIMITE_DE_CANDIDATOS) -> dict:
    """Os prováveis pares de um código, para quem vai ligar os dois à mão.

    Existe porque a tela pedia o código de destino **digitado de cabeça**: sem
    busca, sem a descrição do outro lado, e sem alcançar o código que só tem
    entrada — que é justamente o par que falta. Quem decide é a pessoa; isto só
    põe o provável na frente e diz por quê.

    Lê a mesma movimentação do de-para (`itens_para_casar`), e não uma fonte
    nova: duas leituras da mesma coisa divergem no dia em que uma mudar.
    """
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        raise LookupError("Trabalho não encontrado.")
    movimentos = movimentacao_concluida(projeto_id, sessao)
    if movimentos is None or not movimentos.pasta_de_trabalho:
        raise SemMovimentacao("Conclua a extração de movimentos antes: é dela que saem os códigos a casar.")

    itens = itens_para_casar(movimentos.pasta_de_trabalho)
    lista = itens.get(cnpj)
    if lista is None:
        raise CodigoNaoEstaNaMovimentacao(
            f"O estabelecimento {cnpj} não está nesta movimentação. "
            f"Há {len(itens)} na extração de movimentos.")
    procurado = normalizar_codigo(origem)
    item = next((i for i in lista if normalizar_codigo(i.codigo) == procurado), None)
    if item is None:
        raise CodigoNaoEstaNaMovimentacao(
            f"O código {origem} não está na movimentação do estabelecimento {cnpj}.")

    achados = ordenar_candidatos(item, lista, busca=busca, limite=limite)
    log.info("candidatos para ligar", extra={
        "projeto_id": projeto_id, "cnpj": cnpj, "origem": origem,
        "busca": busca, "candidatos": len(achados), "no_estabelecimento": len(lista)})
    return {
        "origem": {"codigo": item.codigo, "descricao": item.descricao, "ncm": item.ncm,
                   "entradas": format(item.entradas.normalize(), "f"),
                   "saidas": format(item.saidas.normalize(), "f")},
        "candidatos": [{
            "codigo": c.item.codigo, "descricao": c.item.descricao, "ncm": c.item.ncm,
            "entradas": format(c.item.entradas.normalize(), "f"),
            "saidas": format(c.item.saidas.normalize(), "f"),
            "pontos": c.pontos, "porques": list(c.porques),
        } for c in achados],
        "no_estabelecimento": len(lista),
    }
