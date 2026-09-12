"""Importação de arquivos, pré-cadastro da empresa e criação do projeto.

O fluxo que a tela segue:

    1. envia a remessa (SPED solto ou zip)
    2. o sistema lê o registro 0000 de cada arquivo e diz de quem é
    3. o usuário confere e confirma o pré-cadastro da empresa
    4. cria o projeto, já com as competências que vieram nos arquivos

Nenhum arquivo é gravado nesta etapa. Ler o cabeçalho basta para identificar a
empresa, e guardar gigabytes antes de o usuário confirmar seria desperdício.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.analisar_remessa import RemessaAnalisada, analisar
from cat.aplicacao.casos_de_uso.excluir_trabalho import (
    SenhaNaoConfere,
    TrabalhoNaoEncontrado,
    excluir_trabalho,
    resumir,
)
from cat.apresentacao.api.seguranca import UsuarioAtual, exigir_capacidade
from cat.dominio.acesso.usuario import Usuario
from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    contar_comentarios,
    registrar,
)
from cat.dominio.cat42 import etapas as etapas_dominio
from cat.dominio.projeto.historico import StatusDoProjeto, TipoDeEvento
from cat.dominio.comum.cnpj import Cnpj, CnpjInvalido
from cat.config import obter_config
from cat.infraestrutura.arquivos.remessa import RemessaInvalida, percorrer
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.usuario_repositorio import (
    UsuarioRepositorioSql,
)
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import (
    AlocacaoDB,
    EmpresaDB,
    EstabelecimentoDB,
    ExecucaoDB,
    LoteDB,
    ProjetoDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api", tags=["importação"])

PodeEscrever = Annotated[
    Usuario, Depends(exigir_capacidade("pode_escrever", "importar arquivos"))
]

FRENTES = {
    "cat42": "CAT 42 — ressarcimento de ICMS-ST",
    "depara": "De-para de produto",
    "sped": "Quebra de SPED",
    "notafiscal": "Nota fiscal",
}


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------
class EstabelecimentoDetectadoDto(BaseModel):
    cnpj: str
    cnpj_formatado: str
    nome: str
    uf: str
    inscricao_estadual: str
    e_matriz: bool
    arquivos: int
    competencias: int


class RemessaDto(BaseModel):
    razao_social: str
    cnpj_raiz: str
    cnpj_matriz: str | None
    cnpj_matriz_formatado: str | None
    matriz_encontrada: bool
    uf: str
    inscricao_estadual: str
    filiais: int
    total_arquivos: int
    lidos: int
    recusados: int
    tipos: dict[str, int]
    arquivos_para_cat: int
    primeira_competencia: date | None
    ultima_competencia: date | None
    avisos: list[str]
    ja_cadastrada: bool = False
    empresa_id: int | None = None
    # só a matriz por padrão; as filiais entram sob demanda
    matriz: EstabelecimentoDetectadoDto | None = None


class PedidoEmpresa(BaseModel):
    cnpj_raiz: str = Field(min_length=8, max_length=8)
    cnpj_matriz: str
    razao_social: str = Field(min_length=2)
    uf: str = Field(min_length=2, max_length=2)
    inscricao_estadual: str = ""
    grupo_economico: str | None = None


class EmpresaDto(BaseModel):
    id: int
    cnpj_raiz: str
    cnpj_matriz: str | None
    cnpj_matriz_formatado: str | None
    razao_social: str
    uf: str | None
    inscricao_estadual: str | None
    pre_cadastro: bool
    projetos: int = 0


class PedidoProjeto(BaseModel):
    empresa_id: int
    frente: str
    nome: str = Field(min_length=2)
    competencia_ini: date
    competencia_fim: date
    observacao: str | None = None


class ProjetoDto(BaseModel):
    id: int
    empresa_id: int
    empresa: str
    cnpj_matriz: str | None = None
    cnpj_matriz_formatado: str | None = None
    uf: str | None = None
    frente: str
    frente_rotulo: str
    nome: str
    competencia_ini: date
    competencia_fim: date
    status: str
    status_rotulo: str = ""
    pre_cadastro: bool = False
    etapas_feitas: int = 0
    etapas_totais: int = 0
    # quem criou e quem responde hoje. Nomes, não identificadores: a tela
    # mostra gente, e buscar cada nome depois seria uma consulta por cartão.
    criado_por: str | None = None
    criado_por_id: int | None = None
    responsavel: str | None = None
    responsavel_id: int | None = None
    comentarios: int = 0


class EtapaDto(BaseModel):
    chave: str
    nome: str
    descricao: str
    situacao: str
    situacao_rotulo: str
    implementada: bool
    acessivel: bool


class ProjetoDetalheDto(BaseModel):
    projeto: ProjetoDto
    etapas: list[EtapaDto]


# ---------------------------------------------------------------------------
# 1. Analisar a remessa
# ---------------------------------------------------------------------------
@router.post("/importacoes/analisar", response_model=RemessaDto)
async def analisar_remessa(
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
    arquivo: Annotated[UploadFile, File()],
) -> RemessaDto:
    conteudo = await arquivo.read()
    nome = arquivo.filename or "remessa"

    with contexto(etapa="analisar_remessa", usuario_id=usuario.id,
                  arquivo=nome, bytes=len(conteudo)):
        try:
            r = analisar(list(percorrer(conteudo, nome)))
        except RemessaInvalida as erro:
            log.warning("remessa recusada", extra={"motivo": str(erro)})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)
            ) from erro

        if not r.estabelecimentos:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Nenhum arquivo da remessa foi reconhecido como SPED.",
            )
        return _para_dto(r, sessao)


def _para_dto(r: RemessaAnalisada, sessao: Session) -> RemessaDto:
    ja = sessao.scalar(select(EmpresaDB).where(EmpresaDB.cnpj_raiz == r.raiz_cnpj))
    matriz = next((e for e in r.estabelecimentos if e.e_matriz), None)

    return RemessaDto(
        razao_social=r.razao_social,
        cnpj_raiz=r.raiz_cnpj,
        cnpj_matriz=r.cnpj_matriz,
        cnpj_matriz_formatado=Cnpj(r.cnpj_matriz).formatado if r.cnpj_matriz else None,
        matriz_encontrada=matriz is not None,
        uf=r.uf_matriz,
        inscricao_estadual=r.ie_matriz,
        filiais=r.filiais,
        total_arquivos=r.total_arquivos,
        lidos=r.lidos,
        recusados=len(r.recusados),
        tipos=r.tipos,
        arquivos_para_cat=r.serve_para_cat,
        primeira_competencia=r.primeira_competencia,
        ultima_competencia=r.ultima_competencia,
        avisos=r.avisos,
        ja_cadastrada=ja is not None,
        empresa_id=ja.id if ja else None,
        matriz=(
            EstabelecimentoDetectadoDto(
                cnpj=matriz.cnpj.valor,
                cnpj_formatado=matriz.cnpj.formatado,
                nome=matriz.nome,
                uf=matriz.uf,
                inscricao_estadual=matriz.inscricao_estadual,
                e_matriz=True,
                arquivos=matriz.arquivos,
                competencias=len(matriz.competencias),
            )
            if matriz
            else None
        ),
    )


# ---------------------------------------------------------------------------
# 2. Empresas
# ---------------------------------------------------------------------------
@router.get("/empresas", response_model=list[EmpresaDto])
def listar_empresas(
    usuario: UsuarioAtual, sessao: Annotated[Session, Depends(obter_sessao)]
) -> list[EmpresaDto]:
    linhas = sessao.scalars(select(EmpresaDB).order_by(EmpresaDB.razao_social))
    saida = []
    for e in linhas:
        # o escopo de empresa vale aqui como em todo dado de cliente
        if not usuario.enxerga_empresa(e.id):
            continue
        n = sessao.scalar(
            select(ProjetoDB).where(ProjetoDB.empresa_id == e.id).limit(1)
        )
        saida.append(_empresa_dto(e, 1 if n else 0))
    return saida


@router.post("/empresas", response_model=EmpresaDto,
             status_code=status.HTTP_201_CREATED)
def criar_empresa(
    pedido: PedidoEmpresa,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> EmpresaDto:
    try:
        matriz = Cnpj(pedido.cnpj_matriz)
    except CnpjInvalido as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro

    if matriz.raiz != pedido.cnpj_raiz:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A raiz informada não é a do CNPJ da matriz.",
        )

    if sessao.scalar(select(EmpresaDB).where(EmpresaDB.cnpj_raiz == matriz.raiz)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A empresa de raiz {matriz.raiz} já está cadastrada.",
        )

    e = EmpresaDB(
        cnpj_raiz=matriz.raiz,
        cnpj_matriz=matriz.valor,
        razao_social=pedido.razao_social.strip(),
        uf=pedido.uf.upper(),
        inscricao_estadual=pedido.inscricao_estadual or None,
        grupo_economico=pedido.grupo_economico,
        pre_cadastro=True,
        criada_por=usuario.id,
    )
    sessao.add(e)
    sessao.commit()
    sessao.refresh(e)

    sessao.add(
        EstabelecimentoDB(
            empresa_id=e.id, cnpj=matriz.valor, ie=pedido.inscricao_estadual or None,
            nome=e.razao_social, uf=e.uf, e_matriz=True,
        )
    )
    # Quem importou a empresa é alocado a ela na hora. Sem isto a pessoa
    # cadastraria uma empresa que em seguida não conseguiria enxergar, porque o
    # escopo de visibilidade vem só das alocações vigentes.
    sessao.add(
        AlocacaoDB(
            usuario_id=usuario.id, empresa_id=e.id,
            papel_projeto="responsavel", alocado_por=usuario.id,
        )
    )
    sessao.commit()

    log.info(
        "empresa pré-cadastrada a partir do SPED",
        extra={"empresa_id": e.id, "cnpj_raiz": e.cnpj_raiz,
               "cnpj_matriz": e.cnpj_matriz, "por_usuario_id": usuario.id,
               "alocado_automaticamente": True},
    )
    return _empresa_dto(e, 0)


def _empresa_dto(e: EmpresaDB, projetos: int) -> EmpresaDto:
    return EmpresaDto(
        id=e.id,
        cnpj_raiz=e.cnpj_raiz,
        cnpj_matriz=e.cnpj_matriz,
        cnpj_matriz_formatado=Cnpj(e.cnpj_matriz).formatado if e.cnpj_matriz else None,
        razao_social=e.razao_social,
        uf=e.uf,
        inscricao_estadual=e.inscricao_estadual,
        pre_cadastro=e.pre_cadastro,
        projetos=projetos,
    )


# ---------------------------------------------------------------------------
# 3. Projetos
# ---------------------------------------------------------------------------
@router.get("/frentes")
def listar_frentes() -> dict[str, str]:
    return FRENTES


@router.get("/projetos", response_model=list[ProjetoDto])
def listar_projetos(
    usuario: UsuarioAtual, sessao: Annotated[Session, Depends(obter_sessao)]
) -> list[ProjetoDto]:
    linhas = sessao.scalars(select(ProjetoDB).order_by(ProjetoDB.criado_em.desc()))
    return [
        _projeto_dto(p, sessao) for p in linhas
        if usuario.enxerga_empresa(p.empresa_id)
    ]


@router.post("/projetos", response_model=ProjetoDto,
             status_code=status.HTTP_201_CREATED)
def criar_projeto(
    pedido: PedidoProjeto,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ProjetoDto:
    if pedido.frente not in FRENTES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Frente desconhecida. Use uma de: {', '.join(FRENTES)}.",
        )
    if pedido.competencia_fim < pedido.competencia_ini:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A competência final não pode ser anterior à inicial.",
        )

    empresa = sessao.get(EmpresaDB, pedido.empresa_id)
    if empresa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")

    repetido = sessao.scalar(
        select(ProjetoDB).where(
            ProjetoDB.empresa_id == pedido.empresa_id,
            ProjetoDB.frente == pedido.frente,
            ProjetoDB.nome == pedido.nome.strip(),
        )
    )
    if repetido:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Já existe um projeto com este nome nesta frente para esta empresa.",
        )

    p = ProjetoDB(
        empresa_id=pedido.empresa_id,
        frente=pedido.frente,
        nome=pedido.nome.strip(),
        competencia_ini=pedido.competencia_ini,
        competencia_fim=pedido.competencia_fim,
        observacao=pedido.observacao,
        criado_por=usuario.id,
        # quem cria responde, até passar adiante
        responsavel_id=usuario.id,
    )
    sessao.add(p)
    sessao.commit()
    sessao.refresh(p)

    registrar(
        sessao, p.id, TipoDeEvento.CRIADO,
        texto=f"{FRENTES.get(p.frente, p.frente)} · {p.nome}",
        dados={"frente": p.frente, "nome": p.nome,
               "competencia_ini": p.competencia_ini.isoformat(),
               "competencia_fim": p.competencia_fim.isoformat()},
        por=usuario,
    )
    log.info(
        "projeto criado",
        extra={"projeto_id": p.id, "empresa_id": p.empresa_id,
               "frente": p.frente, "por_usuario_id": usuario.id},
    )
    return _projeto_dto(p, sessao)


def _etapas_do(
    p: ProjetoDB, sessao: Session
) -> list[etapas_dominio.EtapaDoProjeto]:
    """A importação conclui quando entrou base, não quando o projeto nasceu.

    Antes concluía só por existir o projeto — mas o projeto nasce do cadastro,
    que lê uma amostra do SPED para descobrir a empresa e não traz base nenhuma.
    Dar a etapa por feita ali dizia ao usuário que havia dado quando não havia.
    Agora conclui quando existe pelo menos um lote com arquivo que a CAT lê.
    """
    concluidas: set[str] = set()
    em_andamento: str | None = None

    tem_base = sessao.scalar(
        select(func.count())
        .select_from(LoteDB)
        .where(LoteDB.projeto_id == p.id, LoteDB.arquivos_uteis > 0)
    ) or 0
    if tem_base:
        concluidas.add("importar")

    # cada etapa de processamento conclui com uma rodada terminada; enquanto
    # roda, aparece em andamento, que é o que explica a espera ao usuário
    for etapa in ("conferencia", "movimentos"):
        situacao = sessao.scalar(
            select(ExecucaoDB.situacao)
            .where(ExecucaoDB.projeto_id == p.id, ExecucaoDB.etapa == etapa)
            .order_by(ExecucaoDB.id.desc())
            .limit(1)
        )
        if situacao == "concluida":
            concluidas.add(etapa)
        elif situacao in ("na_fila", "rodando") and em_andamento is None:
            em_andamento = etapa

    return etapas_dominio.montar(concluidas, em_andamento)


def _projeto_dto(p: ProjetoDB, sessao: Session) -> ProjetoDto:
    e = p.empresa
    feitas, totais = etapas_dominio.progresso(_etapas_do(p, sessao))
    return ProjetoDto(
        id=p.id,
        empresa_id=p.empresa_id,
        empresa=e.razao_social if e else "",
        cnpj_matriz=e.cnpj_matriz if e else None,
        cnpj_matriz_formatado=(
            Cnpj(e.cnpj_matriz).formatado if e and e.cnpj_matriz else None
        ),
        uf=e.uf if e else None,
        frente=p.frente,
        frente_rotulo=FRENTES.get(p.frente, p.frente),
        nome=p.nome,
        competencia_ini=p.competencia_ini,
        competencia_fim=p.competencia_fim,
        status=p.status,
        status_rotulo=_rotulo_do_status(p.status),
        pre_cadastro=e.pre_cadastro if e else False,
        etapas_feitas=feitas,
        etapas_totais=totais,
        criado_por=p.autor.nome_exibicao if p.autor else None,
        criado_por_id=p.criado_por,
        responsavel=p.responsavel.nome_exibicao if p.responsavel else None,
        responsavel_id=p.responsavel_id,
        comentarios=contar_comentarios(p.id, sessao),
    )


def _rotulo_do_status(valor: str) -> str:
    try:
        return StatusDoProjeto(valor).rotulo
    except ValueError:
        return valor


@router.get("/projetos/{projeto_id}", response_model=ProjetoDetalheDto)
def detalhar_projeto(
    projeto_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ProjetoDetalheDto:
    p = sessao.get(ProjetoDB, projeto_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Projeto não encontrado.")
    if not usuario.enxerga_empresa(p.empresa_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Você não tem acesso a esta empresa."
        )
    return ProjetoDetalheDto(
        projeto=_projeto_dto(p, sessao),
        etapas=[
            EtapaDto(
                chave=e.definicao.chave,
                nome=e.definicao.nome,
                descricao=e.definicao.descricao,
                situacao=e.situacao.value,
                situacao_rotulo=e.situacao.rotulo,
                implementada=e.definicao.implementada,
                acessivel=e.acessivel,
            )
            for e in _etapas_do(p, sessao)
        ],
    )


# ---------------------------------------------------------------------------
# 5. Excluir o trabalho
#
# A única operação do sistema que pede a senha de novo. A sessão fica aberta a
# jornada inteira, e uma tela deixada em máquina destravada não pode bastar
# para desfazer meses de apuração.
# ---------------------------------------------------------------------------
PodeExcluir = Annotated[
    Usuario,
    Depends(exigir_capacidade("pode_excluir_trabalho", "excluir um trabalho")),
]


class ConfirmacaoDeExclusao(BaseModel):
    senha: str = Field(min_length=1, max_length=200)


class OQueSeraApagadoDto(BaseModel):
    projeto: str
    empresa: str
    lotes: int
    arquivos: int
    execucoes: int


@router.get("/projetos/{projeto_id}/exclusao", response_model=OQueSeraApagadoDto)
def previa_da_exclusao(
    projeto_id: int,
    usuario: PodeExcluir,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> OQueSeraApagadoDto:
    """O que some se confirmar. A confirmação tem de ser informada."""
    p = sessao.get(ProjetoDB, projeto_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabalho não encontrado.")
    if not usuario.enxerga_empresa(p.empresa_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Você não tem acesso a esta empresa.")
    return OQueSeraApagadoDto(**asdict(resumir(projeto_id, sessao)))


@router.delete("/projetos/{projeto_id}", response_model=OQueSeraApagadoDto)
def excluir_projeto(
    projeto_id: int,
    confirmacao: ConfirmacaoDeExclusao,
    usuario: PodeExcluir,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> OQueSeraApagadoDto:
    p = sessao.get(ProjetoDB, projeto_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabalho não encontrado.")
    if not usuario.enxerga_empresa(p.empresa_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Você não tem acesso a esta empresa.")

    with contexto(etapa="excluir_trabalho", usuario_id=usuario.id,
                  projeto_id=projeto_id):
        try:
            apagado = excluir_trabalho(
                projeto_id, usuario, confirmacao.senha, sessao,
                senhas=SenhasArgon2(obter_config().senha_pimenta),
                repositorio=UsuarioRepositorioSql(sessao),
            )
        except SenhaNaoConfere:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Senha incorreta. O trabalho não foi apagado.",
            ) from None
        except TrabalhoNaoEncontrado:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Trabalho não encontrado."
            ) from None
    return OQueSeraApagadoDto(**asdict(apagado))
