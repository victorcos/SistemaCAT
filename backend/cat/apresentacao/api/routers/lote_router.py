"""Lote de arquivos: a base de trabalho de um projeto que já existe.

Separado do roteador de importação de propósito, e a separação é o ponto:

* `importacao_router` **cria** empresa e projeto a partir de uma amostra do
  SPED. É o cadastro, e acontece uma vez por trabalho.
* este roteador **alimenta** um projeto que já existe. É a base de análise, tem
  gigabytes e volta quantas vezes a empresa mandar arquivo.

Os dois caminhos estavam colapsados num só, e o link "importar mais arquivos"
de dentro do projeto levava de volta ao cadastro — que recomeçaria a criação da
empresa. Era redundância que produzia trabalho duplicado.

O fluxo tem dois passos, e o primeiro não grava nada:

    1. inspecionar a pasta e mostrar o que há dentro
    2. confirmar, e aí sim registrar o lote

O passo de conferência existe porque pasta de rede mistura cliente e mistura
tipo de arquivo. Quem confirma precisa ver o que vai entrar — e o que ficou de
fora, e por quê.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.excluir_trabalho import excluir_lote
from cat.aplicacao.casos_de_uso.inspecionar_lote import (
    ArquivoExistente,
    PastaInvalida,
    inspecionar_pasta,
)
from cat.apresentacao.api.seguranca import UsuarioAtual, exigir_capacidade, exigir_empresa
from cat.dominio.acesso.usuario import Usuario
from cat.dominio.lote import ArquivoDoLote, ResumoDoLote, TipoDeArquivo
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    LoteDB,
    ProjetoDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api", tags=["lote"])

PodeEscrever = Annotated[
    Usuario, Depends(exigir_capacidade("pode_escrever", "importar lote de arquivos"))
]

# quantos arquivos a tela recebe de volta na conferência. A lista existe para o
# usuário reconhecer o que está vendo, não para ele ler 7.036 linhas.
AMOSTRA_NA_TELA = 40


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------
class PastaEntrada(BaseModel):
    pasta: str = Field(min_length=1, max_length=1000)


class LoteEntrada(PastaEntrada):
    observacao: str | None = Field(default=None, max_length=500)


class ArquivoDto(BaseModel):
    nome: str
    caminho: str
    tamanho: int
    tipo: str
    tipo_rotulo: str
    grupo: str
    alimenta_a_cat: bool
    cnpj: str | None = None
    competencia: date | None = None
    uf: str = ""
    detalhe: str = ""
    motivo: str = ""


class ContagemDto(BaseModel):
    tipo: str
    rotulo: str
    grupo: str
    alimenta_a_cat: bool
    quantidade: int


class ResumoDto(BaseModel):
    pasta: str
    total_arquivos: int
    arquivos_uteis: int
    bytes_totais: int
    de_outra_empresa: int
    serve: bool
    competencia_ini: date | None = None
    competencia_fim: date | None = None
    cnpjs: list[str]
    contagens: list[ContagemDto]
    avisos: list[str]
    amostra: list[ArquivoDto]
    ja_no_trabalho: int = 0
    copias: int = 0


class LoteDto(BaseModel):
    id: int
    projeto_id: int
    pasta: str
    total_arquivos: int
    arquivos_uteis: int
    bytes_totais: int
    competencia_ini: date | None = None
    competencia_fim: date | None = None
    observacao: str | None = None
    criado_em: str
    contagens: list[ContagemDto] = []


# ---------------------------------------------------------------------------
# Tradução
# ---------------------------------------------------------------------------
def _arquivo_dto(a: ArquivoDoLote) -> ArquivoDto:
    return ArquivoDto(
        nome=a.nome, caminho=a.caminho, tamanho=a.tamanho,
        tipo=a.tipo.value, tipo_rotulo=a.tipo.rotulo, grupo=a.tipo.grupo.value,
        alimenta_a_cat=a.alimenta_a_cat, cnpj=a.cnpj,
        competencia=a.competencia, uf=a.uf, detalhe=a.detalhe, motivo=a.motivo,
    )


def _contagens(por_tipo: dict[TipoDeArquivo, int]) -> list[ContagemDto]:
    # o que serve primeiro, e dentro disso o mais numeroso primeiro
    ordenado = sorted(por_tipo.items(),
                      key=lambda kv: (not kv[0].alimenta_a_cat, -kv[1]))
    return [
        ContagemDto(tipo=t.value, rotulo=t.rotulo, grupo=t.grupo.value,
                    alimenta_a_cat=t.alimenta_a_cat, quantidade=q)
        for t, q in ordenado
    ]


def _resumo_dto(r: ResumoDoLote, ja_no_trabalho: int = 0) -> ResumoDto:
    competencias = r.competencias
    # a amostra mostra primeiro o que NÃO entrou: é o que o usuário precisa ver
    amostra = sorted(r.arquivos, key=lambda a: (a.alimenta_a_cat, a.nome))
    return ResumoDto(
        pasta=r.pasta,
        total_arquivos=r.total,
        arquivos_uteis=len(r.uteis),
        bytes_totais=r.bytes_totais,
        de_outra_empresa=len(r.de_outra_empresa),
        serve=r.serve,
        competencia_ini=competencias[0] if competencias else None,
        competencia_fim=competencias[-1] if competencias else None,
        cnpjs=r.cnpjs[:20],
        contagens=_contagens(r.por_tipo),
        avisos=r.avisos,
        amostra=[_arquivo_dto(a) for a in amostra[:AMOSTRA_NA_TELA]],
        ja_no_trabalho=ja_no_trabalho,
        copias=len(r.copias),
    )


def _projeto_do_usuario(
    projeto_id: int, usuario: Usuario, sessao: Session
) -> ProjetoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabalho não encontrado.")
    exigir_empresa(usuario, projeto.empresa_id)
    return projeto


def _existentes(projeto_id: int, sessao: Session) -> tuple[ArquivoExistente, ...]:
    """O que já está no trabalho, para a importação nova detectar cópia."""
    linhas = sessao.execute(
        select(ArquivoDoLoteDB.caminho, ArquivoDoLoteDB.tamanho,
               ArquivoDoLoteDB.tipo, ArquivoDoLoteDB.cnpj,
               ArquivoDoLoteDB.competencia, ArquivoDoLoteDB.retificadora,
               ArquivoDoLoteDB.hash_conteudo)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id)
    ).all()
    return tuple(ArquivoExistente(*linha) for linha in linhas)


def _caminhos_ja_no_projeto(projeto_id: int, sessao: Session) -> set[str]:
    return set(sessao.scalars(
        select(ArquivoDoLoteDB.caminho)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id)
    ))


# ---------------------------------------------------------------------------
# 1. Conferir a pasta, sem gravar
# ---------------------------------------------------------------------------
@router.post("/projetos/{projeto_id}/lotes/inspecionar", response_model=ResumoDto)
def inspecionar(
    projeto_id: int,
    entrada: PastaEntrada,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ResumoDto:
    projeto = _projeto_do_usuario(projeto_id, usuario, sessao)

    with contexto(etapa="inspecionar_lote", usuario_id=usuario.id,
                  projeto_id=projeto_id, pasta=entrada.pasta):
        try:
            resumo = inspecionar_pasta(entrada.pasta, projeto.empresa.cnpj_raiz,
                                       existentes=_existentes(projeto_id, sessao))
        except PastaInvalida as erro:
            log.warning("pasta recusada", extra={"motivo": str(erro)})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)
            ) from erro

        ja = _caminhos_ja_no_projeto(projeto_id, sessao)
        repetidos = sum(1 for a in resumo.arquivos if a.caminho in ja)
        return _resumo_dto(resumo, ja_no_trabalho=repetidos)


# ---------------------------------------------------------------------------
# 2. Confirmar: registrar o lote
# ---------------------------------------------------------------------------
@router.post("/projetos/{projeto_id}/lotes", response_model=LoteDto,
             status_code=status.HTTP_201_CREATED)
def criar_lote(
    projeto_id: int,
    entrada: LoteEntrada,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> LoteDto:
    projeto = _projeto_do_usuario(projeto_id, usuario, sessao)

    with contexto(etapa="criar_lote", usuario_id=usuario.id,
                  projeto_id=projeto_id, pasta=entrada.pasta):
        try:
            resumo = inspecionar_pasta(entrada.pasta, projeto.empresa.cnpj_raiz,
                                       existentes=_existentes(projeto_id, sessao))
        except PastaInvalida as erro:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)
            ) from erro

        # a mensagem certa antes da genérica: uma pasta só de cópias não é uma
        # pasta "sem nada para a CAT" — é uma pasta que já está no trabalho
        if not resumo.arquivos and resumo.copias:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Os {len(resumo.copias)} arquivo(s) desta pasta são cópias "
                "exatas de arquivos que já estão neste trabalho. Nada novo "
                "para importar.",
            )
        if not resumo.serve:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Nenhum arquivo desta pasta alimenta a CAT 42. Falta a EFD "
                "ICMS/IPI, o XML das notas ou o relatório gerencial.",
            )

        # arquivo que já está no trabalho não entra de novo: o mesmo SPED
        # contado duas vezes dobraria movimento na apuração
        ja = _caminhos_ja_no_projeto(projeto_id, sessao)
        novos = [a for a in resumo.arquivos if a.caminho not in ja]
        if not novos:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Todos os arquivos desta pasta já estão neste trabalho.",
            )

        # o período é o do que a CAT lê, não o de tudo que estava na pasta
        competencias = sorted({a.competencia for a in novos
                               if a.competencia and a.alimenta_a_cat})
        lote = LoteDB(
            projeto_id=projeto_id,
            pasta=resumo.pasta,
            total_arquivos=len(novos),
            arquivos_uteis=sum(1 for a in novos if a.alimenta_a_cat),
            bytes_totais=sum(a.tamanho for a in novos),
            competencia_ini=competencias[0] if competencias else None,
            competencia_fim=competencias[-1] if competencias else None,
            observacao=entrada.observacao,
            criado_por=usuario.id,
        )
        sessao.add(lote)
        sessao.flush()

        sessao.add_all([
            ArquivoDoLoteDB(
                lote_id=lote.id, caminho=a.caminho, nome=a.nome,
                tamanho=a.tamanho, tipo=a.tipo.value, cnpj=a.cnpj,
                competencia=a.competencia, uf=a.uf or None,
                detalhe=a.detalhe or None, retificadora=a.retificadora,
                hash_conteudo=a.hash_conteudo,
            )
            for a in novos
        ])
        sessao.commit()
        sessao.refresh(lote)

        log.info(
            "lote registrado",
            extra={"lote_id": lote.id, "arquivos": lote.total_arquivos,
                   "uteis": lote.arquivos_uteis, "bytes": lote.bytes_totais,
                   "repetidos_ignorados": len(resumo.arquivos) - len(novos)},
        )
        return _lote_dto(lote, _contagens(_por_tipo(novos)))


# ---------------------------------------------------------------------------
# 3. O que já entrou
# ---------------------------------------------------------------------------
@router.get("/projetos/{projeto_id}/lotes", response_model=list[LoteDto])
def listar_lotes(
    projeto_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> list[LoteDto]:
    _projeto_do_usuario(projeto_id, usuario, sessao)
    lotes = sessao.scalars(
        select(LoteDB)
        .where(LoteDB.projeto_id == projeto_id)
        .order_by(LoteDB.criado_em.desc())
    ).all()

    contagens = _contagens_por_lote([lote.id for lote in lotes], sessao)
    return [_lote_dto(lote, contagens.get(lote.id, [])) for lote in lotes]


def _contagens_por_lote(
    ids: list[int], sessao: Session
) -> dict[int, list[ContagemDto]]:
    if not ids:
        return {}
    linhas = sessao.execute(
        select(ArquivoDoLoteDB.lote_id, ArquivoDoLoteDB.tipo,
               func.count(ArquivoDoLoteDB.id))
        .where(ArquivoDoLoteDB.lote_id.in_(ids))
        .group_by(ArquivoDoLoteDB.lote_id, ArquivoDoLoteDB.tipo)
    ).all()

    bruto: dict[int, dict[TipoDeArquivo, int]] = {}
    for lote_id, tipo, quantos in linhas:
        try:
            t = TipoDeArquivo(tipo)
        except ValueError:      # tipo gravado por versão anterior do sistema
            t = TipoDeArquivo.DESCONHECIDO
        por_tipo = bruto.setdefault(lote_id, {})
        por_tipo[t] = por_tipo.get(t, 0) + quantos
    return {lote_id: _contagens(p) for lote_id, p in bruto.items()}


def _por_tipo(arquivos: list[ArquivoDoLote]) -> dict[TipoDeArquivo, int]:
    contagem: dict[TipoDeArquivo, int] = {}
    for a in arquivos:
        contagem[a.tipo] = contagem.get(a.tipo, 0) + 1
    return contagem


def _lote_dto(lote: LoteDB, contagens: list[ContagemDto]) -> LoteDto:
    return LoteDto(
        id=lote.id,
        projeto_id=lote.projeto_id,
        pasta=lote.pasta,
        total_arquivos=lote.total_arquivos,
        arquivos_uteis=lote.arquivos_uteis,
        bytes_totais=lote.bytes_totais,
        competencia_ini=lote.competencia_ini,
        competencia_fim=lote.competencia_fim,
        observacao=lote.observacao,
        criado_em=lote.criado_em.isoformat(),
        contagens=contagens,
    )


# ---------------------------------------------------------------------------
# 4. Tirar um lote do trabalho
#
# Não pede senha: desfaz uma importação, não o trabalho. Os arquivos do
# cliente não são tocados — o lote é só o registro de onde eles estão.
# ---------------------------------------------------------------------------
class LoteApagadoDto(BaseModel):
    pasta: str
    arquivos: int
    conferencias_invalidadas: int


@router.delete("/projetos/{projeto_id}/lotes/{lote_id}",
               response_model=LoteApagadoDto)
def remover_lote(
    projeto_id: int,
    lote_id: int,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> LoteApagadoDto:
    _projeto_do_usuario(projeto_id, usuario, sessao)

    lote = sessao.get(LoteDB, lote_id)
    if lote is None or lote.projeto_id != projeto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Lote não encontrado neste trabalho.")

    with contexto(etapa="remover_lote", usuario_id=usuario.id,
                  projeto_id=projeto_id, lote_id=lote_id):
        apagado = excluir_lote(lote_id, usuario, sessao)
    return LoteApagadoDto(pasta=apagado.pasta, arquivos=apagado.arquivos,
                          conferencias_invalidadas=apagado.conferencias_invalidadas)
