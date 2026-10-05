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

    Frente e competências são o que delimita o escopo: "CAT 42 da empresa 12,
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
    # manual) ou "demais_saidas" (como a empresa 17 transmitiu). Ver
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



class FiltroDoCreditoOutorgadoDB(Base):
    """Quais produtos têm o benefício, neste trabalho.

    É do **trabalho**, e não da empresa nem do sistema: o crédito outorgado é
    concedido por lei estadual a uma lista de mercadorias, e essa lista muda
    com o estado, com o período e com o que a empresa vende. Herdá-la de um
    trabalho para o outro seria repetir sem olhar — o mesmo raciocínio da
    correção, e o oposto do de-para, que é da empresa.

    Uma linha por trabalho. `ncms` e `termos` são listas de texto: a NCM
    confirma, o termo da descrição é quem decide (ver
    `dominio/icms/credito_outorgado`).

    A rodada guarda **uma cópia** deste filtro no próprio resumo da execução.
    Não é redundância: aqui fica o filtro de hoje, lá fica o que produziu
    aquela lista — e é o de lá que responde, meses depois, por que ela tinha
    aquelas linhas.
    """

    __tablename__ = "credito_outorgado_filtro"

    projeto_id: Mapped[int] = mapped_column(
        ForeignKey("projeto.id", ondelete="CASCADE"), primary_key=True)
    ncms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    termos: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # rodar sem julgar nada, para ver o universo antes de escrever o primeiro
    # termo. Tudo sai elegível, marcado "SEM FILTRO" — o rótulo existe para que
    # ninguém confunda essa lista com uma apuração de benefício
    sem_filtro: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false")
    # guardar também o que ficou de fora. É como se revisa o filtro — o produto
    # que devia ter entrado e não entrou só aparece nessa lista. Custa: numa
    # base grande, os descartados são a maioria esmagadora das linhas
    guardar_descartados: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false")
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(), nullable=False,
    )
    atualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


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


class SelicMensalDB(Base):
    """A Selic de um mês, guardada para nunca mais ser buscada.

    **Taxa de mês fechado não muda.** É publicada uma vez e vale para sempre —
    a de março de 2021 hoje é a mesma de daqui a dez anos. Guardá-la é o que
    permite corrigir indébito sem depender de a API do Banco Central estar no
    ar: a rodada só sai à rede pelos meses que ainda faltam.

    `fonte` diz de onde veio — `bcb-sgs-4390` da API, `repositorio` da tabela
    que o time mantinha em código antes desta tabela existir. Serve à auditoria
    de um número que vira dinheiro.

    Não tem empresa nem projeto: a Selic é a mesma para todo mundo.
    """

    __tablename__ = "selic_mensal"

    # "aaaa-mm". Texto, e não data, porque o que existe é o mês — dia 1 seria
    # um dia inventado, e a ordenação de texto neste formato já é cronológica
    competencia: Mapped[str] = mapped_column(String(7), primary_key=True)
    # em por cento no mês, como o Banco Central publica: 1,05 é 1,05%
    taxa: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    obtida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(), nullable=False,
    )


class TiqueteDeDownloadDB(Base):
    """Autorização de **um** download, de vida curta, para baixar por navegação.

    ## Por que existe

    O front baixava com `fetch` e `await r.blob()` — o arquivo inteiro na
    memória da aba antes de gravar. Numa lista de 2,93 milhões de linhas isso
    não passa, e o servidor já fazia a parte dele certo: serve do disco em
    fluxo. Todo o desperdício estava no navegador.

    A saída é deixar o **navegador** baixar, por navegação: o gerenciador dele
    grava direto no disco, mostra progresso, não tem teto de tamanho e funciona
    em qualquer navegador, com ou sem contexto seguro. Mas navegação não manda
    cabeçalho `Authorization`, e é para isso que este tíquete serve.

    ## Por que no banco, e não em memória

    Haverá mais de uma instância da API. Tíquete emitido numa e resgatado noutra
    tem de ser encontrado, e memória de processo não atravessa instância. O
    `UPDATE ... WHERE expira_em > now()` do Postgres também resolve a corrida
    entre duas instâncias sem combinarem nada.

    ## O que ele autoriza, e nada além

    Cada campo abaixo faz parte do que o arquivo servido **é**: trocar o
    `formato` ou o recorte muda o arquivo. Por isso o tíquete carrega todos, e a
    rota serve exatamente o que ele descreve — não o que a URL pedir.

    ## Vida curta em vez de uso único, e isso é escolha

    `usado_em` registra o primeiro resgate, mas **não** barra o segundo dentro
    da validade. Uso único seria mais apertado no papel e hostil na prática: o
    gerenciador de download do navegador **repete a requisição** — numa queda de
    rede, num redirecionamento, às vezes num `HEAD` antes do `GET` —, e recusar
    a repetição transforma um soluço de rede em "o link morreu".

    O que protege aqui é o prazo. Um tíquete que vive dois minutos, amarrado a
    um arquivo e a um usuário, é inútil a quem o encontrar no histórico do
    navegador ou no log depois disso. Uso único somaria pouco a isso e custaria
    o botão de tentar de novo.

    **A expiração vale no início da requisição, não durante.** Um xlsx de 16
    minutos é autorizado quando o download começa; o prazo não interrompe
    transferência em curso.
    """

    __tablename__ = "tiquete_de_download"
    __table_args__ = (Index("ix_tiquete_expira", "expira_em"),)

    # o próprio segredo é a chave: 32 bytes aleatórios em base64url
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # **em cascata, e isso não é detalhe.** Um tíquete vive dois minutos e não
    # pode ser o que impede apagar um trabalho: sem a cascata, o primeiro
    # download de uma execução a trava para sempre. Apareceu na tela em
    # 02/10/2026, horas depois de a tabela nascer — 23503 ao excluir o projeto
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    execucao_id: Mapped[int] = mapped_column(
        ForeignKey("execucao.id", ondelete="CASCADE"), nullable=False)
    # a etapa pela qual a tela pediu, que é de quem é o catálogo de planilhas
    etapa: Mapped[str] = mapped_column(String(30), nullable=False)
    qual: Mapped[str] = mapped_column(String(40), nullable=False)
    formato: Mapped[str] = mapped_column(String(10), nullable=False)
    # o recorte: lista diferente é arquivo diferente, e o tíquete autoriza um
    modelos: Mapped[str | None] = mapped_column(Text)
    classificacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(),
        nullable=False,
    )
    expira_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    # quando foi resgatado pela primeira vez. Auditoria, não trava — ver acima
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AliquotaDeItemDB(Base):
    """A alíquota de ICMS de um produto, quando ela foge da regra do estado.

    Serve ao ICMS-ST presumido do relatório 839: o ST que se exclui da base do
    PIS/COFINS é `base × alíquota`, e a alíquota tem duas metades. A **regra** —
    interna do estado, ou a Resolução 22/1989 do Senado na interestadual — é lei,
    e mora em `sped/tabelas/tab_aliquota_icms.py`. A **exceção** é classificação
    fiscal de mercadoria: cesta básica a 12%, supérfluo a 25%, isento a 0%,
    importado a 4%. É esta tabela.

    **Está no banco porque é dado de cliente.** Código de item é do ERP de quem
    o cadastrou, e não faz sentido no de outro; versionar isso no repositório
    seria publicar a carteira de produtos de quem nos contratou.

    Medido no arquivo de referência: a regra sozinha acerta 98,66% das linhas, e
    a exceção são 556 pares. `fonte` diz de onde veio — `gabarito-839` quando
    extraída do relatório do escritório anterior, `cliente` quando veio do
    cadastro dele, `time` quando alguém daqui a conferiu.
    """

    __tablename__ = "aliquota_de_item"

    # o estabelecimento, e não a empresa: a mesma mercadoria pode ter
    # tratamento diferente em filiais de estados diferentes
    cnpj: Mapped[str] = mapped_column(String(14), primary_key=True)
    uf_origem: Mapped[str] = mapped_column(String(2), primary_key=True)
    uf_destino: Mapped[str] = mapped_column(String(2), primary_key=True)
    codigo_do_item: Mapped[str] = mapped_column(String(60), primary_key=True)
    # em por cento: 12 é 12%
    aliquota: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(), nullable=False,
    )
