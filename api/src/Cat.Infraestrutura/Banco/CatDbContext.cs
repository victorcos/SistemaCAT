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
}
