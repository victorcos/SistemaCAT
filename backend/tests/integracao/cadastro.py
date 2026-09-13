"""Empresa e projeto para os testes de integração do motor.

Cadastrar empresa e criar projeto moram na API em C# desde 13/09/2026
(docs/MIGRACAO_CSHARP.md). O motor continua dono de lote, conferência,
movimentos e histórico, e os testes dessas rotas precisam de um projeto de
verdade no banco — só não o pedem mais a uma rota do motor.

Grava o mesmo que o C# grava: empresa com estabelecimento matriz e a alocação
de quem cadastrou, projeto com quem cria como responsável, e o evento
"criado" no histórico.

As etapas do projeto também são calculadas no C#. Aqui não se recalcula: os
testes conferem o **fato** de que a etapa depende — há base no lote, a última
conferência concluiu — e a regra de montar o roteiro tem teste lá.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select

from cat.aplicacao.casos_de_uso.historico_do_projeto import registrar
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import (
    AlocacaoDB, EmpresaDB, EstabelecimentoDB, EventoDoProjetoDB, ExecucaoDB,
    LoteDB, ProjetoDB, UsuarioDB,
)


def _usuario(s, nome: str) -> UsuarioDB:
    u = s.scalar(select(UsuarioDB).where(UsuarioDB.usuario == nome))
    assert u is not None, f"usuário {nome!r} não existe no banco de teste"
    return u


def criar_empresa(*, raiz: str, cnpj: str, razao: str, por: str, uf: str = "SP",
                  ie: str | None = None) -> int:
    """Devolve o id. Se a raiz já existe, devolve a existente."""
    with Sessao() as s:
        existente = s.scalar(select(EmpresaDB).where(EmpresaDB.cnpj_raiz == raiz))
        if existente is not None:
            return existente.id
        autor = _usuario(s, por)
        e = EmpresaDB(cnpj_raiz=raiz, cnpj_matriz=cnpj, razao_social=razao, uf=uf,
                      inscricao_estadual=ie, pre_cadastro=True, ativa=True,
                      criada_por=autor.id)
        s.add(e)
        s.flush()
        s.add(EstabelecimentoDB(empresa_id=e.id, cnpj=cnpj, ie=ie, nome=razao,
                                uf=uf, e_matriz=True))
        s.add(AlocacaoDB(usuario_id=autor.id, empresa_id=e.id,
                         papel_projeto="responsavel", alocado_por=autor.id))
        s.commit()
        return e.id


def criar_projeto(*, empresa_id: int, nome: str, por: str,
                  ini: str = "2021-05-01", fim: str = "2021-05-01",
                  frente: str = "cat42") -> int:
    with Sessao() as s:
        autor = _usuario(s, por)
        p = ProjetoDB(empresa_id=empresa_id, frente=frente, nome=nome,
                      competencia_ini=date.fromisoformat(ini),
                      competencia_fim=date.fromisoformat(fim),
                      status="em_andamento", criado_por=autor.id,
                      responsavel_id=autor.id,
                      criado_em=datetime.now(timezone.utc))
        s.add(p)
        s.commit()
        registrar(s, p.id, TipoDeEvento.CRIADO, texto=f"CAT 42 — ressarcimento de ICMS-ST · {nome}",
                  dados={"frente": frente, "nome": nome,
                         "competencia_ini": ini, "competencia_fim": fim},
                  por=autor)
        return p.id


def projeto(projeto_id: int) -> ProjetoDB | None:
    with Sessao() as s:
        return s.get(ProjetoDB, projeto_id)


def nome_de(usuario_id: int | None) -> str | None:
    if usuario_id is None:
        return None
    with Sessao() as s:
        u = s.get(UsuarioDB, usuario_id)
        return u.nome_exibicao if u else None


def comentarios(projeto_id: int) -> int:
    with Sessao() as s:
        return s.scalar(select(func.count()).select_from(EventoDoProjetoDB).where(
            EventoDoProjetoDB.projeto_id == projeto_id,
            EventoDoProjetoDB.tipo == TipoDeEvento.COMENTARIO.value)) or 0


def quantas_empresas() -> int:
    with Sessao() as s:
        return s.scalar(select(func.count()).select_from(EmpresaDB)) or 0


def tem_base(projeto_id: int) -> bool:
    """O fato de que depende a etapa "importar": algum lote com arquivo útil."""
    with Sessao() as s:
        return bool(s.scalar(select(func.count()).select_from(LoteDB).where(
            LoteDB.projeto_id == projeto_id, LoteDB.arquivos_uteis > 0)))


def ultima_situacao(projeto_id: int, etapa: str) -> str | None:
    """O fato de que dependem "conferencia" e "movimentos": a última rodada."""
    with Sessao() as s:
        return s.scalar(select(ExecucaoDB.situacao).where(
            ExecucaoDB.projeto_id == projeto_id, ExecucaoDB.etapa == etapa,
        ).order_by(ExecucaoDB.id.desc()).limit(1))
