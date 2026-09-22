"""Tabelas. Reflete o modelo desenhado em docs/ARQUITETURA.md.

Nesta fatia entram só as tabelas que a tela de login exige. Projeto, atividade e
execução vêm na etapa de ingestão, mas empresa e alocação já entram porque o
escopo de visibilidade nasce delas.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmpresaDB(Base):
    """Uma empresa cliente, identificada pela raiz do CNPJ.

    A raiz é a chave porque é o que todas as filiais compartilham. O CNPJ da
    matriz fica ao lado por ser o que as pessoas reconhecem.
    """

    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj_raiz: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    cnpj_matriz: Mapped[str | None] = mapped_column(String(14))
    razao_social: Mapped[str] = mapped_column(Text, nullable=False)
    grupo_economico: Mapped[str | None] = mapped_column(Text)
    uf: Mapped[str | None] = mapped_column(String(2))
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20))
    # verdadeiro enquanto veio só do arquivo e ninguém conferiu
    pre_cadastro: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(),
        nullable=False,
    )
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


class UsuarioDB(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(Text, nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    papel: Mapped[str] = mapped_column(String(20), nullable=False, default="leitura")
    cargo: Mapped[str] = mapped_column(String(20), nullable=False, default="outro")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senha_provisoria: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )

    # a tabela de alocação aponta duas vezes para usuário (quem foi alocado e
    # quem alocou), então o lado da chave precisa ser dito explicitamente
    alocacoes: Mapped[list["AlocacaoDB"]] = relationship(
        back_populates="usuario_obj",
        lazy="selectin",
        foreign_keys="AlocacaoDB.usuario_id",
    )


class AlocacaoDB(Base):
    """Quem trabalha em qual empresa, com histórico.

    Nunca apagar linha. Quando a pessoa sai, preenche-se `fim`. É o que permite
    responder quem tinha acesso a um dado em determinado mês, meses depois.
    """

    __tablename__ = "alocacao"
    __table_args__ = (UniqueConstraint("usuario_id", "empresa_id", "inicio"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    papel_projeto: Mapped[str] = mapped_column(String(20), nullable=False)
    inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alocado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    motivo_saida: Mapped[str | None] = mapped_column(Text)

    usuario_obj: Mapped[UsuarioDB] = relationship(
        back_populates="alocacoes", foreign_keys=[usuario_id]
    )

    @property
    def vigente(self) -> bool:
        return self.fim is None


class UsuarioSegmentoDB(Base):
    """Em que assunto a pessoa trabalha: PIS/COFINS, ICMS, IRPJ/CSLL.

    Terceira dimensão de acesso, ao lado do papel e da alocação por empresa.
    Gestor e dev não têm linha aqui — enxergam todo segmento por papel, como já
    ignoram o escopo de empresa. Quem decide é a API em C#
    (`Cat.Dominio/Acesso/Segmento.cs`); aqui só se guarda.
    """

    __tablename__ = "usuario_segmento"
    __table_args__ = (UniqueConstraint("usuario_id", "segmento", name="uq_usuario_segmento"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    segmento: Mapped[str] = mapped_column(String(30), nullable=False)
    liberado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    liberado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )


class EstabelecimentoDB(Base):
    """Uma filial ou a matriz. Um por CNPJ completo.

    O escopo de confidencialidade é por EMPRESA, não por estabelecimento: quem
    enxerga a empresa enxerga todas as filiais dela.
    """

    __tablename__ = "estabelecimento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    nome: Mapped[str | None] = mapped_column(Text)
    ie: Mapped[str | None] = mapped_column(String(20))
    uf: Mapped[str | None] = mapped_column(String(2))
    e_matriz: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    ativo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    empresa: Mapped[EmpresaDB] = relationship(lazy="joined")


class ProjetoDB(Base):
    """Um trabalho contratado para uma empresa, numa frente e num período.

    Frente e competências são o que delimita o escopo: "CAT 42 da Sulamericana,
    01/2021 a 12/2025". Toda execução e toda entrega pendura aqui.
    """

    __tablename__ = "projeto"
    __table_args__ = (UniqueConstraint("empresa_id", "frente", "nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    frente: Mapped[str] = mapped_column(String(20), nullable=False)
    # o segmento tributário a que o trabalho pertence, que é por onde a tela
    # inicial o encontra. Todo trabalho anterior a esta coluna é de ICMS — o
    # sistema nasceu na CAT 42 —, e é esse o padrão
    modulo: Mapped[str] = mapped_column(String(30), nullable=False, default="icms", index=True)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    competencia_ini: Mapped[date] = mapped_column(Date, nullable=False)
    competencia_fim: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="em_andamento", nullable=False
    )
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    # Quem responde pelo trabalho hoje — nem sempre quem o criou. Férias,
    # desligamento e troca de carteira acontecem no meio de uma apuração que
    # dura meses, e a sucessão fica registrada no histórico.
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    # como a venda a consumidor final entra no razão: "enquadramento_1" (o
    # manual) ou "demais_saidas" (como a BOA transmitiu). Ver
    # cat.dominio.icms.cat42.enquadramento.VendaAConsumidor
    venda_a_consumidor: Mapped[str] = mapped_column(
        String(20), default="enquadramento_1", server_default="enquadramento_1", nullable=False
    )

    empresa: Mapped[EmpresaDB] = relationship(lazy="joined")
    autor: Mapped["UsuarioDB | None"] = relationship(
        lazy="joined", foreign_keys=[criado_por]
    )
    responsavel: Mapped["UsuarioDB | None"] = relationship(
        lazy="joined", foreign_keys=[responsavel_id]
    )


class EventoDoProjetoDB(Base):
    """Uma linha da história do trabalho. Nunca se altera nem se apaga.

    Mistura o que o sistema fez com o que a pessoa escreveu, na ordem em que
    aconteceu — ver `cat.dominio.projeto.historico`.

    O autor é opcional porque o usuário pode ser apagado um dia e o fato,
    não: "lote importado em 10/09" continua verdadeiro mesmo sem a conta de
    quem o importou. `autor_nome` guarda o nome de exibição do momento pela
    mesma razão — quem lê o histórico daqui a um ano quer o nome que a pessoa
    tinha quando fez, não o de agora.
    """

    __tablename__ = "evento_do_projeto"
    __table_args__ = (Index("ix_evento_projeto", "projeto_id", "criado_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projeto_id: Mapped[int] = mapped_column(
        ForeignKey("projeto.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    texto: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dados: Mapped[dict | None] = mapped_column(JSON)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    autor_nome: Mapped[str] = mapped_column(Text, default="", nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )


class LoteDB(Base):
    """Uma entrada de arquivos para um trabalho.

    Um projeto tem vários lotes, e é assim que tem de ser: a empresa manda o
    que faltou, manda o ano seguinte, manda o relatório que o ERP só soltou
    depois. Cada entrada fica registrada com quem trouxe e de onde, porque
    quando um número da apuração for questionado meses depois, a primeira
    pergunta é de qual base ele saiu.

    O conteúdo dos arquivos não é copiado: guarda-se o caminho. Base de cliente
    tem gigabytes e já vive no servidor de arquivos com a política de guarda da
    casa; duplicar isso dentro do sistema só multiplicaria o dado sigiloso.
    """

    __tablename__ = "lote"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id"), nullable=False)
    pasta: Mapped[str] = mapped_column(Text, nullable=False)
    total_arquivos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arquivos_uteis: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_totais: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    competencia_ini: Mapped[date | None] = mapped_column(Date)
    competencia_fim: Mapped[date | None] = mapped_column(Date)
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(),
        nullable=False,
    )
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    projeto: Mapped[ProjetoDB] = relationship(lazy="joined")


class ArquivoDoLoteDB(Base):
    """Um arquivo de um lote, já identificado.

    A etapa seguinte lê esta tabela para saber o que abrir: filtra por tipo e
    por competência em vez de varrer a pasta de novo. Por isso guarda o tipo
    reconhecido, e não só o caminho.
    """

    __tablename__ = "arquivo_do_lote"
    __table_args__ = (
        # o mesmo arquivo não entra duas vezes no mesmo lote
        UniqueConstraint("lote_id", "caminho"),
        # a etapa de movimentos filtra por tipo dentro do lote
        Index("ix_arquivo_do_lote_tipo", "lote_id", "tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote.id"), nullable=False)
    caminho: Mapped[str] = mapped_column(Text, nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    tamanho: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String(14))
    competencia: Mapped[date | None] = mapped_column(Date)
    uf: Mapped[str | None] = mapped_column(String(2))
    detalhe: Mapped[str | None] = mapped_column(Text)
    # SPED retificador: a conferência precisa saber, porque a retificadora
    # substitui a original do mesmo estabelecimento e período
    retificadora: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # SHA-256 do conteúdo, só de quem foi candidato a cópia na importação.
    # Vazio para os demais — e para tudo importado antes desta regra.
    hash_conteudo: Mapped[str | None] = mapped_column(String(64))


class ExecucaoDB(Base):
    """Uma rodada de processamento pesado, com o que ela leu e o que produziu.

    A arquitetura pede isto desde o começo: extração completa de uma empresa lê
    mais de 100 GB e leva minutos, então não vive dentro da requisição — a API
    devolve um identificador e o front acompanha.

    A linha fica **para sempre**, mesmo depois de a rodada terminar. Quando um
    número da apuração for questionado meses depois, é aqui que se responde de
    qual base ele saiu, quando, por quem e sobre quantos arquivos.
    """

    __tablename__ = "execucao"
    __table_args__ = (Index("ix_execucao_projeto", "projeto_id", "etapa"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id"), nullable=False)
    etapa: Mapped[str] = mapped_column(String(30), nullable=False)
    situacao: Mapped[str] = mapped_column(
        String(20), default="na_fila", server_default="na_fila", nullable=False
    )
    passo: Mapped[str | None] = mapped_column(Text)
    fracao: Mapped[float] = mapped_column(Float, default=0.0,
                                          server_default="0", nullable=False)
    arquivos_totais: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arquivos_lidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_lidos: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    documentos: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    pasta_de_trabalho: Mapped[str | None] = mapped_column(Text)
    resumo: Mapped[dict | None] = mapped_column(JSON)
    erro: Mapped[str | None] = mapped_column(Text)
    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(),
        nullable=False,
    )
    terminada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    # só a etapa 8 usa: a entrega conclui quando um revisor ou gestor aprova o
    # pacote. Quem grava é a API; o motor só lê
    aprovada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    aprovada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeParaDB(Base):
    """Um par do de-para: o mesmo produto escriturado com outro código.

    É da **empresa**, não do trabalho: o código de compra que o ERP do cliente
    grava é o mesmo no trabalho de 2021 e no de 2024, e decidir de novo seria
    repagar a revisão. `cnpj` vazio vale para todos os estabelecimentos.

    `quantidade na origem × fator = quantidade no destino`: 1 kit de três vira
    3 unidades. `situacao` é `aprovado` (o razão aplica) ou `recusado` (a
    proposta não volta a aparecer como pendente).
    """

    __tablename__ = "depara_item"
    __table_args__ = (UniqueConstraint("empresa_id", "cnpj", "codigo_origem", name="uq_depara_origem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, default="", server_default="")
    codigo_origem: Mapped[str] = mapped_column(Text, nullable=False)
    codigo_destino: Mapped[str] = mapped_column(Text, nullable=False)
    fator: Mapped[Decimal] = mapped_column(Numeric(24, 9), nullable=False, default=1, server_default="1")
    motivo: Mapped[str] = mapped_column(String(20), nullable=False)
    situacao: Mapped[str] = mapped_column(String(12), nullable=False)
    confianca: Mapped[str | None] = mapped_column(String(10))
    explicacao: Mapped[str | None] = mapped_column(Text)
    projeto_id: Mapped[int | None] = mapped_column(ForeignKey("projeto.id"))
    decidido_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    decidido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(), nullable=False,
    )



class CorrecaoDB(Base):
    """Uma correção à mão no que o sistema calculou.

    É do **trabalho**, não da empresa (decisão do Victor, 20/09/2026): alíquota
    e enquadramento mudam com a lei e com o período, e herdá-los no trabalho
    seguinte seria repetir sem olhar. O de-para é o contrário, e por isso vive
    em outra tabela.

    O alvo é a mercadoria (`cnpj` + `codigo`) ou a linha (`cnpj` + `documento` +
    `numero_item`); `campo` diz o quê, e `valor` vai como texto porque cada
    campo tem o seu tipo — quem converte é `cat.dominio.icms.cat42.correcao`.

    `situacao` é `ativa` ou `desfeita`: desfazer não apaga a linha, para o
    histórico continuar contando o que foi feito e por quem.
    """

    __tablename__ = "correcao"
    __table_args__ = (
        UniqueConstraint("projeto_id", "campo", "cnpj", "codigo", "documento", "numero_item",
                         name="uq_correcao_alvo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id"), nullable=False)
    campo: Mapped[str] = mapped_column(String(20), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, default="", server_default="")
    codigo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    documento: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    numero_item: Mapped[int | None] = mapped_column(Integer)
    valor: Mapped[str] = mapped_column(Text, nullable=False)
    # o que estava lá quando alguém corrigiu: é o "antes" do histórico
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    situacao: Mapped[str] = mapped_column(String(10), nullable=False, default="ativa", server_default="ativa")
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(), nullable=False,
    )
    desfeita_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    desfeita_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
