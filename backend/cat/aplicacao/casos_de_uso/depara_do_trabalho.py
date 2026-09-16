"""O de-para de um trabalho: o que o sistema propõe e o que já foi decidido.

As propostas saem da última movimentação concluída (`infraestrutura/analitico/
depara.py`) e não ficam gravadas: mudam quando a base muda. As decisões ficam,
na tabela `depara_item`, por empresa — quem grava é a API em C#.

Além dos pares, a resposta lista os **códigos sem par**: com saída e sem
entrada nem estoque, que nenhuma proposta nem decisão resolve. São os que ficam
negativos no razão, e os que vão para o cliente dizer de onde vieram — como a
RVZ fez na Advertising com os códigos de marketplace.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.apurar_suportado import movimentacao_concluida
from cat.dominio.depara.candidatos import normalizar_codigo
from cat.infraestrutura.analitico.depara import itens_para_casar
from cat.dominio.depara.candidatos import propor
from cat.infraestrutura.repositorios.modelos import DeParaDB, ProjetoDB, UsuarioDB
from cat.log import obter_log

log = obter_log(__name__)

LIMITE_SEM_PAR = 5000


class SemMovimentacao(ValueError):
    """O trabalho ainda não tem movimentação para propor de-para."""


def candidatos_do_projeto(projeto_id: int, sessao: Session) -> dict:
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

    def decisao(cnpj: str, origem: str) -> DeParaDB | None:
        return decisoes.get((cnpj, origem)) or decisoes.get(("", origem))

    pares: list[dict] = []
    sem_par: list[dict] = []
    total_sem_par = 0
    vistas: set[tuple[str, str]] = set()
    for cnpj, lista in sorted(itens.items()):
        propostos = propor(lista)
        cobertos: set[str] = set()
        for p in propostos:
            d = decisao(cnpj, p.origem)
            vistas.add((d.cnpj, d.codigo_origem) if d else (cnpj, p.origem))
            cobertos |= {p.origem, p.destino}
            pares.append({
                "cnpj": cnpj, "origem": p.origem, "destino": p.destino, "fator": format(p.fator, "f"),
                "motivos": [m.value for m in p.motivos], "confianca": p.confianca.value,
                "explicacao": p.explicacao, "proposto": True, **_situacao(d, nomes),
            })
        aprovados_aqui = {o for (c, o), d in decisoes.items()
                          if d.situacao == "aprovado" and c in ("", cnpj)}
        destinos_aqui = {d.codigo_destino for (c, _), d in decisoes.items()
                         if d.situacao == "aprovado" and c in ("", cnpj)}
        for item in lista:
            resolvido = (item.codigo in cobertos or item.codigo in aprovados_aqui
                         or item.codigo in destinos_aqui)
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
            "proposto": False, **_situacao(d, nomes),
        })

    resumo = {
        "pares": len(pares),
        "pendentes": sum(p["situacao"] == "pendente" for p in pares),
        "aprovados": sum(p["situacao"] == "aprovado" for p in pares),
        "recusados": sum(p["situacao"] == "recusado" for p in pares),
        "sem_par": total_sem_par,
        "estabelecimentos": len(itens),
    }
    log.info("de-para do trabalho", extra={"projeto_id": projeto_id, "movimentos_execucao_id": movimentos.id,
                                           **resumo})
    return {"movimentos_execucao_id": movimentos.id, "empresa_id": projeto.empresa_id,
            "resumo": resumo, "pares": pares, "sem_par": sem_par}


def _situacao(d: DeParaDB | None, nomes: dict[int, str]) -> dict:
    if d is None:
        return {"situacao": "pendente", "decidido_por": None, "decidido_em": None, "destino_decidido": None,
                "fator_decidido": None}
    return {"situacao": d.situacao, "decidido_por": nomes.get(d.decidido_por),
            "decidido_em": d.decidido_em.isoformat() if d.decidido_em else None,
            "destino_decidido": d.codigo_destino, "fator_decidido": format(d.fator.normalize(), "f")}
