using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

/// <summary>
/// Mapeia as tabelas que o Alembic criou. <b>Não gera migração</b>: o esquema
/// tem um dono só, e é o Alembic. Dois donos do mesmo esquema divergem em
/// silêncio (DECISOES, 13/09/2026).
///
/// Cada tabela entra quando a primeira rota em C# precisa dela, e só com as
/// colunas que essa rota usa. Coluna que o EF não conhece fica intocada.
/// </summary>
public sealed class CatDbContext(DbContextOptions<CatDbContext> opcoes) : DbContext(opcoes)
{
    public DbSet<UsuarioLinha> Usuarios => Set<UsuarioLinha>();
    public DbSet<AlocacaoLinha> Alocacoes => Set<AlocacaoLinha>();
    public DbSet<EmpresaLinha> Empresas => Set<EmpresaLinha>();
    public DbSet<EstabelecimentoLinha> Estabelecimentos => Set<EstabelecimentoLinha>();
    public DbSet<ProjetoLinha> Projetos => Set<ProjetoLinha>();
    public DbSet<EventoLinha> Eventos => Set<EventoLinha>();
    public DbSet<LoteLinha> Lotes => Set<LoteLinha>();
    public DbSet<ArquivoDoLoteLinha> ArquivosDoLote => Set<ArquivoDoLoteLinha>();
    public DbSet<ExecucaoLinha> Execucoes => Set<ExecucaoLinha>();

    protected override void OnModelCreating(ModelBuilder modelo)
    {
        modelo.Entity<UsuarioLinha>(e =>
        {
            e.ToTable("usuario");
            e.HasKey(u => u.Id);
            e.Property(u => u.Id).HasColumnName("id");
            e.Property(u => u.Usuario).HasColumnName("usuario");
            e.Property(u => u.Email).HasColumnName("email");
            e.Property(u => u.NomeExibicao).HasColumnName("nome_exibicao");
            e.Property(u => u.SenhaHash).HasColumnName("senha_hash");
            e.Property(u => u.Papel).HasColumnName("papel");
            e.Property(u => u.Cargo).HasColumnName("cargo");
            e.Property(u => u.Ativo).HasColumnName("ativo");
            e.Property(u => u.TentativasFalhas).HasColumnName("tentativas_falhas");
            e.Property(u => u.BloqueadoAte).HasColumnName("bloqueado_ate");
            e.Property(u => u.SenhaProvisoria).HasColumnName("senha_provisoria");
            e.Property(u => u.UltimoAcesso).HasColumnName("ultimo_acesso");
            // NOT NULL sem valor padrão no banco: o SQLAlchemy preenche do lado da aplicação
            e.Property(u => u.CriadoEm).HasColumnName("criado_em");
            e.HasMany(u => u.Alocacoes).WithOne().HasForeignKey(a => a.UsuarioId);
        });

        modelo.Entity<AlocacaoLinha>(e =>
        {
            e.ToTable("alocacao");
            e.HasKey(a => a.Id);
            e.Property(a => a.Id).HasColumnName("id");
            e.Property(a => a.UsuarioId).HasColumnName("usuario_id");
            e.Property(a => a.EmpresaId).HasColumnName("empresa_id");
            e.Property(a => a.PapelProjeto).HasColumnName("papel_projeto");
            e.Property(a => a.Inicio).HasColumnName("inicio");
            e.Property(a => a.Fim).HasColumnName("fim");
            e.Property(a => a.AlocadoPor).HasColumnName("alocado_por");
            e.Property(a => a.MotivoSaida).HasColumnName("motivo_saida");
        });

        modelo.Entity<EmpresaLinha>(e =>
        {
            e.ToTable("empresa");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.CnpjRaiz).HasColumnName("cnpj_raiz");
            e.Property(x => x.RazaoSocial).HasColumnName("razao_social");
            e.Property(x => x.GrupoEconomico).HasColumnName("grupo_economico");
            e.Property(x => x.Uf).HasColumnName("uf");
            // NOT NULL sem valor padrão no banco; pre_cadastro e criada_em têm, e ficam com o banco
            e.Property(x => x.Ativa).HasColumnName("ativa");
            e.Property(x => x.CnpjMatriz).HasColumnName("cnpj_matriz");
            e.Property(x => x.InscricaoEstadual).HasColumnName("inscricao_estadual");
            e.Property(x => x.PreCadastro).HasColumnName("pre_cadastro");
            e.Property(x => x.CriadaPor).HasColumnName("criada_por");
        });

        modelo.Entity<EstabelecimentoLinha>(e =>
        {
            e.ToTable("estabelecimento");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.EmpresaId).HasColumnName("empresa_id");
            e.Property(x => x.Cnpj).HasColumnName("cnpj");
            e.Property(x => x.Nome).HasColumnName("nome");
            e.Property(x => x.Ie).HasColumnName("ie");
            e.Property(x => x.Uf).HasColumnName("uf");
            e.Property(x => x.EMatriz).HasColumnName("e_matriz");
            e.Property(x => x.Ativo).HasColumnName("ativo");
        });

        modelo.Entity<ProjetoLinha>(e =>
        {
            e.ToTable("projeto");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.EmpresaId).HasColumnName("empresa_id");
            e.Property(x => x.Frente).HasColumnName("frente");
            e.Property(x => x.Nome).HasColumnName("nome");
            e.Property(x => x.CompetenciaIni).HasColumnName("competencia_ini");
            e.Property(x => x.CompetenciaFim).HasColumnName("competencia_fim");
            e.Property(x => x.Status).HasColumnName("status");
            e.Property(x => x.Observacao).HasColumnName("observacao");
            e.Property(x => x.CriadoEm).HasColumnName("criado_em");
            e.Property(x => x.CriadoPor).HasColumnName("criado_por");
            e.Property(x => x.ResponsavelId).HasColumnName("responsavel_id");
        });

        modelo.Entity<EventoLinha>(e =>
        {
            e.ToTable("evento_do_projeto");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.ProjetoId).HasColumnName("projeto_id");
            e.Property(x => x.Tipo).HasColumnName("tipo");
            e.Property(x => x.Texto).HasColumnName("texto");
            // coluna json do SQLAlchemy: texto JSON, que o Python lê de volta como dicionário
            e.Property(x => x.Dados).HasColumnName("dados").HasColumnType("json");
            e.Property(x => x.AutorId).HasColumnName("autor_id");
            e.Property(x => x.AutorNome).HasColumnName("autor_nome");
            e.Property(x => x.CriadoEm).HasColumnName("criado_em");
        });

        modelo.Entity<LoteLinha>(e =>
        {
            e.ToTable("lote");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.ProjetoId).HasColumnName("projeto_id");
            e.Property(x => x.ArquivosUteis).HasColumnName("arquivos_uteis");
        });

        modelo.Entity<ArquivoDoLoteLinha>(e =>
        {
            e.ToTable("arquivo_do_lote");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.LoteId).HasColumnName("lote_id");
        });

        modelo.Entity<ExecucaoLinha>(e =>
        {
            e.ToTable("execucao");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.ProjetoId).HasColumnName("projeto_id");
            e.Property(x => x.Etapa).HasColumnName("etapa");
            e.Property(x => x.Situacao).HasColumnName("situacao");
            e.Property(x => x.PastaDeTrabalho).HasColumnName("pasta_de_trabalho");
        });
    }
}

public sealed class UsuarioLinha
{
    public int Id { get; set; }
    public string Usuario { get; set; } = "";
    public string Email { get; set; } = "";
    public string NomeExibicao { get; set; } = "";
    public string SenhaHash { get; set; } = "";
    public string Papel { get; set; } = "leitura";
    public string Cargo { get; set; } = "outro";
    public bool Ativo { get; set; }
    public int TentativasFalhas { get; set; }
    // timestamptz: o Npgsql entrega e exige DateTime em UTC
    public DateTime? BloqueadoAte { get; set; }
    public bool SenhaProvisoria { get; set; }
    public DateTime? UltimoAcesso { get; set; }
    public DateTime CriadoEm { get; set; }
    public List<AlocacaoLinha> Alocacoes { get; set; } = [];
}

public sealed class AlocacaoLinha
{
    public int Id { get; set; }
    public int UsuarioId { get; set; }
    public int EmpresaId { get; set; }
    public string PapelProjeto { get; set; } = "";
    public DateTime Inicio { get; set; }
    /// <summary>Nunca se apaga alocação: quando a pessoa sai, preenche-se o fim.</summary>
    public DateTime? Fim { get; set; }
    public int? AlocadoPor { get; set; }
    public string? MotivoSaida { get; set; }
}

public sealed class EmpresaLinha
{
    public int Id { get; set; }
    public string CnpjRaiz { get; set; } = "";
    public string RazaoSocial { get; set; } = "";
    public string? GrupoEconomico { get; set; }
    public string? Uf { get; set; }
    public bool Ativa { get; set; } = true;
    public string? CnpjMatriz { get; set; }
    public string? InscricaoEstadual { get; set; }
    /// <summary>Verdadeiro enquanto veio só do arquivo e ninguém conferiu.</summary>
    public bool PreCadastro { get; set; } = true;
    public int? CriadaPor { get; set; }
}

public sealed class EstabelecimentoLinha
{
    public int Id { get; set; }
    public int EmpresaId { get; set; }
    public string Cnpj { get; set; } = "";
    public string? Nome { get; set; }
    public string? Ie { get; set; }
    public string? Uf { get; set; }
    public bool EMatriz { get; set; }
    public bool Ativo { get; set; } = true;
}

public sealed class ProjetoLinha
{
    public int Id { get; set; }
    public int EmpresaId { get; set; }
    public string Frente { get; set; } = "";
    public string Nome { get; set; } = "";
    public DateOnly CompetenciaIni { get; set; }
    public DateOnly CompetenciaFim { get; set; }
    public string Status { get; set; } = "em_andamento";
    public string? Observacao { get; set; }
    public DateTime CriadoEm { get; set; }
    public int? CriadoPor { get; set; }
    public int? ResponsavelId { get; set; }
}

public sealed class EventoLinha
{
    public int Id { get; set; }
    public int ProjetoId { get; set; }
    public string Tipo { get; set; } = "";
    public string Texto { get; set; } = "";
    public string? Dados { get; set; }
    public int? AutorId { get; set; }
    public string AutorNome { get; set; } = "";
    public DateTime CriadoEm { get; set; }
}

public sealed class LoteLinha
{
    public int Id { get; set; }
    public int ProjetoId { get; set; }
    public int ArquivosUteis { get; set; }
}

public sealed class ArquivoDoLoteLinha
{
    public int Id { get; set; }
    public int LoteId { get; set; }
}

public sealed class ExecucaoLinha
{
    public int Id { get; set; }
    public int ProjetoId { get; set; }
    public string Etapa { get; set; } = "";
    public string Situacao { get; set; } = "";
    public string? PastaDeTrabalho { get; set; }
}
