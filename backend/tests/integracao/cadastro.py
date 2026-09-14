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
from cat.aplicacao.casos_de_uso.inspecionar_lote import inspecionar_do_projeto
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import (
    AlocacaoDB, ArquivoDoLoteDB, EmpresaDB, EstabelecimentoDB, EventoDoProjetoDB,
    ExecucaoDB, LoteDB, ProjetoDB, UsuarioDB,
)

# o segredo que tests/conftest.py define para o canal interno
SEGREDO = {"X-Cat-Motor-Segredo": "segredo-do-canal-so-de-teste"}


def criar_usuario(s, *, usuario: str, email: str, nome_exibicao: str,
                  papel: str, cargo: str = "outro") -> None:
    """Uma pessoa no banco, para ser autora de empresa, trabalho e evento.

    Sem senha que sirva: o motor não confere senha nem lê token desde a fatia 7
    (docs/MIGRACAO_CSHARP.md). Entrar no sistema é assunto da API em C#.
    """
    s.add(UsuarioDB(usuario=usuario, email=email, nome_exibicao=nome_exibicao,
                    senha_hash="!sem-senha-no-motor", papel=papel, cargo=cargo))
    s.commit()


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


def criar_lote(*, projeto_id: int, pasta: str) -> int:
    """Registra o lote como a API em C# registra: inspeciona pelo motor e grava
    o que é novo. É preparação para os testes de conferência e movimentos, que
    precisam de lote no banco; a regra de registrar tem teste no C#."""
    with Sessao() as s:
        resumo, ja = inspecionar_do_projeto(projeto_id, pasta, s)
        novos = [a for a in resumo.arquivos if a.caminho not in ja]
        assert novos, "nada novo para registrar nesta pasta"
        competencias = sorted({a.competencia for a in novos if a.competencia and a.alimenta_a_cat})
        lote = LoteDB(projeto_id=projeto_id, pasta=resumo.pasta, total_arquivos=len(novos),
                      arquivos_uteis=sum(1 for a in novos if a.alimenta_a_cat),
                      bytes_totais=sum(a.tamanho for a in novos),
                      competencia_ini=competencias[0] if competencias else None,
                      competencia_fim=competencias[-1] if competencias else None)
        s.add(lote)
        s.flush()
        s.add_all([ArquivoDoLoteDB(lote_id=lote.id, caminho=a.caminho, nome=a.nome,
                                   tamanho=a.tamanho, tipo=a.tipo.value, cnpj=a.cnpj,
                                   competencia=a.competencia, uf=a.uf or None,
                                   detalhe=a.detalhe or None, retificadora=a.retificadora,
                                   hash_conteudo=a.hash_conteudo)
                   for a in novos])
        s.commit()
        return lote.id


def tipos_nos_lotes(projeto_id: int) -> dict[str, int]:
    with Sessao() as s:
        return dict(s.execute(
            select(ArquivoDoLoteDB.tipo, func.count())
            .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
            .where(LoteDB.projeto_id == projeto_id)
            .group_by(ArquivoDoLoteDB.tipo)).all())


def hashes_nos_lotes(projeto_id: int) -> list[str | None]:
    with Sessao() as s:
        return list(s.scalars(
            select(ArquivoDoLoteDB.hash_conteudo)
            .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
            .where(LoteDB.projeto_id == projeto_id)))


def definir_status(projeto_id: int, status: str) -> None:
    """Mudar status é da API em C#; aqui só se põe o trabalho no estado do teste."""
    with Sessao() as s:
        s.get(ProjetoDB, projeto_id).status = status
        s.commit()


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


# ---------------------------------------------------------------------------
# Execuções e planilhas pelo canal interno
#
# As rotas de conferência e movimentos moram na API em C# desde 13/09/2026. O
# motor põe a execução na fila (/interno/execucoes), o trabalhador roda
# (workers/fila.py), e a planilha sai por /interno/planilhas. Estes auxiliares
# fazem o que a API faz, na hora, para os testes não dependerem de tempo.
# ---------------------------------------------------------------------------
def iniciar(cliente, etapa: str, projeto_id: int, por: str):
    return cliente.post("/interno/execucoes", headers=SEGREDO, json={
        "etapa": etapa, "projeto_id": projeto_id, "usuario_id": _id_de(por)})


def rodar_fila() -> list[int]:
    from workers import fila  # noqa: PLC0415
    return fila.processar_pendentes()


def conferir(cliente, projeto_id: int, por: str) -> dict:
    """Pede a conferência, roda a fila e devolve a execução como a tela a veria."""
    r = iniciar(cliente, "conferencia", projeto_id, por)
    assert r.status_code == 202, r.text
    rodar_fila()
    return execucao(r.json()["id"])


def execucao(execucao_id: int) -> dict:
    from cat.apresentacao.api.routers.interno_router import execucao_dto  # noqa: PLC0415
    with Sessao() as s:
        return execucao_dto(s.get(ExecucaoDB, execucao_id)).model_dump()


def execucoes(projeto_id: int, etapa: str) -> list[dict]:
    from cat.apresentacao.api.routers.interno_router import execucao_dto  # noqa: PLC0415
    with Sessao() as s:
        return [execucao_dto(e).model_dump() for e in s.scalars(
            select(ExecucaoDB).where(ExecucaoDB.projeto_id == projeto_id, ExecucaoDB.etapa == etapa)
            .order_by(ExecucaoDB.id.desc()))]


class Planilha:
    """A resposta que a API em C# dá: o arquivo, com tipo e nome no cabeçalho."""

    def __init__(self, resposta):
        self.status_code = resposta.status_code
        self._resposta = resposta
        self.headers: dict[str, str] = {}
        self.content = b""
        if resposta.status_code == 200:
            pronta = resposta.json()
            with open(pronta["caminho"], "rb") as f:
                self.content = f.read()
            self.headers = {"content-type": pronta["tipo"],
                            "content-disposition": f'attachment; filename="{pronta["nome"]}"'}

    @property
    def text(self) -> str:
        return self._resposta.text

    def json(self):
        return self._resposta.json()


def planilha(cliente, etapa: str, execucao_id: int, qual: str, **consulta) -> Planilha:
    return Planilha(cliente.post("/interno/planilhas", headers=SEGREDO, json={
        "execucao_id": execucao_id, "etapa": etapa, "qual": qual, **consulta}))


def _id_de(nome: str) -> int:
    with Sessao() as s:
        return _usuario(s, nome).id
