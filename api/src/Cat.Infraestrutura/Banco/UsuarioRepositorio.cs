using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace Cat.Infraestrutura.Banco;

/// <summary>Traduz tabela em entidade de domínio, e de volta.</summary>
public sealed class UsuarioRepositorio(CatDbContext banco, TimeProvider relogio, ILogger<UsuarioRepositorio> log)
    : IRepositorioDeUsuario
{
    public async Task<Usuario?> BuscarPorNome(string nomeDeUsuario, CancellationToken cancelar)
    {
        var linha = await Consulta().FirstOrDefaultAsync(u => u.Usuario == nomeDeUsuario, cancelar);
        return linha is null ? null : ParaDominio(linha);
    }

    public async Task<Usuario?> BuscarPorEmail(string email, CancellationToken cancelar)
    {
        var linha = await Consulta().FirstOrDefaultAsync(u => u.Email == email, cancelar);
        return linha is null ? null : ParaDominio(linha);
    }

    public async Task<Usuario?> BuscarPorId(int id, CancellationToken cancelar)
    {
        var linha = await Consulta().FirstOrDefaultAsync(u => u.Id == id, cancelar);
        return linha is null ? null : ParaDominio(linha);
    }

    public async Task<IReadOnlyList<Usuario>> Listar(CancellationToken cancelar) =>
        (await Consulta().OrderByDescending(u => u.Ativo).ThenBy(u => u.Usuario).ToListAsync(cancelar))
        .Select(ParaDominio).ToList();

    public Task<int> ContarGestoresAtivos(CancellationToken cancelar) =>
        banco.Usuarios.CountAsync(u => u.Papel == "gestor" && u.Ativo, cancelar);

    public Task<bool> ExisteAlgum(CancellationToken cancelar) => banco.Usuarios.AnyAsync(cancelar);

    public async Task<Usuario> Criar(NovoUsuario novo, CancellationToken cancelar)
    {
        var linha = new UsuarioLinha
        {
            Usuario = novo.NomeDeUsuario,
            Email = novo.Email,
            NomeExibicao = novo.NomeExibicao,
            SenhaHash = novo.ResumoDaSenha,
            Papel = novo.Papel.Valor(),
            Cargo = novo.Cargo.Valor(),
            Ativo = true,
            TentativasFalhas = 0,
            SenhaProvisoria = novo.SenhaProvisoria,
            CriadoEm = ParaBanco(relogio.GetUtcNow())!.Value,
        };
        banco.Usuarios.Add(linha);
        await banco.SaveChangesAsync(cancelar);
        banco.Entry(linha).State = EntityState.Detached;
        return (await BuscarPorId(linha.Id, cancelar))!;
    }

    public async Task<string> ObterResumoDaSenha(int id, CancellationToken cancelar) =>
        await banco.Usuarios.Where(u => u.Id == id).Select(u => u.SenhaHash).FirstOrDefaultAsync(cancelar) ?? "";

    public async Task SalvarTentativa(Usuario usuario, CancellationToken cancelar)
    {
        var alteradas = await banco.Usuarios.Where(u => u.Id == usuario.Id).ExecuteUpdateAsync(s => s
            .SetProperty(u => u.TentativasFalhas, usuario.TentativasFalhas)
            .SetProperty(u => u.BloqueadoAte, ParaBanco(usuario.BloqueadoAte))
            .SetProperty(u => u.UltimoAcesso, ParaBanco(usuario.UltimoAcesso)), cancelar);
        if (alteradas == 0)
            log.Erro("tentativa de salvar tentativa em usuário inexistente", new { usuario_id = usuario.Id });
    }

    public Task DefinirSenha(int id, string novoResumo, bool provisoria, CancellationToken cancelar) =>
        Alterar(id, "definir senha", s => s
            .SetProperty(u => u.SenhaHash, novoResumo)
            .SetProperty(u => u.SenhaProvisoria, provisoria), cancelar);

    public Task DefinirPapel(int id, Papel papel, CancellationToken cancelar)
    {
        var valor = papel.Valor();
        return Alterar(id, "definir papel", s => s.SetProperty(u => u.Papel, valor), cancelar);
    }

    public Task DefinirCargo(int id, Cargo cargo, CancellationToken cancelar)
    {
        var valor = cargo.Valor();
        return Alterar(id, "definir cargo", s => s.SetProperty(u => u.Cargo, valor), cancelar);
    }

    /// <summary>
    /// Grava a lista inteira numa transação: o que saiu é apagado, o que entrou é
    /// criado, e o que ficou não é tocado — preservando quem liberou e quando.
    /// </summary>
    public async Task DefinirSegmentos(int id, IReadOnlyList<string> segmentos, int porUsuarioId,
        DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var atuais = await banco.UsuariosSegmentos.Where(s => s.UsuarioId == id).ToListAsync(cancelar);
        var querem = segmentos.ToHashSet();
        foreach (var fora in atuais.Where(s => !querem.Contains(s.Segmento)))
            banco.UsuariosSegmentos.Remove(fora);
        // o Postgres guarda microssegundos: o resto dos ticks some ao gravar
        var quando = new DateTime(agora.UtcTicks - agora.UtcTicks % 10, DateTimeKind.Utc);
        foreach (var novo in querem.Where(c => atuais.All(s => s.Segmento != c)))
            banco.UsuariosSegmentos.Add(new UsuarioSegmentoLinha
            {
                UsuarioId = id, Segmento = novo, LiberadoPor = porUsuarioId, LiberadoEm = quando,
            });
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
    }

    public Task DefinirDados(int id, string nomeExibicao, string email, CancellationToken cancelar) =>
        Alterar(id, "definir dados", s => s
            .SetProperty(u => u.NomeExibicao, nomeExibicao)
            .SetProperty(u => u.Email, email), cancelar);

    public Task DefinirSituacao(int id, bool ativo, CancellationToken cancelar) =>
        Alterar(id, "definir situação", s => s.SetProperty(u => u.Ativo, ativo), cancelar);

    /// <summary>Ação do gestor. Zera contador e espera, sem tocar na senha.</summary>
    public Task Desbloquear(int id, CancellationToken cancelar) =>
        Alterar(id, "desbloquear", s => s
            .SetProperty(u => u.TentativasFalhas, 0)
            .SetProperty(u => u.BloqueadoAte, (DateTime?)null), cancelar);

    private async Task Alterar(int id, string acao,
        Action<Microsoft.EntityFrameworkCore.Query.UpdateSettersBuilder<UsuarioLinha>> campos, CancellationToken cancelar)
    {
        var alteradas = await banco.Usuarios.Where(u => u.Id == id).ExecuteUpdateAsync(campos, cancelar);
        if (alteradas == 0)
            log.Erro($"tentativa de {acao} em usuário inexistente", new { usuario_id = id });
    }

    public async Task RegravarResumoDaSenha(int id, string novoResumo, CancellationToken cancelar)
    {
        var anterior = await ObterResumoDaSenha(id, cancelar);
        var alteradas = await banco.Usuarios.Where(u => u.Id == id)
            .ExecuteUpdateAsync(s => s.SetProperty(u => u.SenhaHash, novoResumo), cancelar);
        if (alteradas == 0)
        {
            log.Erro("tentativa de regravar hash em usuário inexistente", new { usuario_id = id });
            return;
        }
        log.Info("resumo de senha migrado para o formato atual",
            new { usuario_id = id, formato_anterior = Prefixo(anterior), formato_atual = Prefixo(novoResumo) });
    }

    private IQueryable<UsuarioLinha> Consulta() =>
        banco.Usuarios.AsNoTracking().Include(u => u.Alocacoes.Where(a => a.Fim == null))
                                     .Include(u => u.Segmentos);

    private Usuario ParaDominio(UsuarioLinha linha)
    {
        // Valor desconhecido rebaixa para o padrão e registra. Melhor um usuário
        // com menos permissão do que uma exceção que impede todo mundo de entrar.
        if (!TextoDeAcesso.TentarPapel(linha.Papel, out var papel))
        {
            log.Erro("papel desconhecido no banco, usando o padrão",
                new { usuario_id = linha.Id, encontrado = linha.Papel, padrao = "leitura" });
            papel = Papel.Leitura;
        }
        if (!TextoDeAcesso.TentarCargo(linha.Cargo, out var cargo))
        {
            log.Erro("cargo desconhecido no banco, usando o padrão",
                new { usuario_id = linha.Id, encontrado = linha.Cargo, padrao = "outro" });
            cargo = Cargo.Outro;
        }

        return new Usuario
        {
            Id = linha.Id,
            NomeDeUsuario = linha.Usuario,
            Email = linha.Email,
            NomeExibicao = linha.NomeExibicao,
            Papel = papel,
            Cargo = cargo,
            Ativo = linha.Ativo,
            SenhaProvisoria = linha.SenhaProvisoria,
            // escopo de visibilidade vem SÓ das alocações vigentes
            Empresas = linha.Alocacoes.Select(a => a.EmpresaId).Distinct().Order().ToList(),
            // segmento desconhecido no banco é ignorado, não derruba o login: a
            // pessoa entra com menos acesso, que é o lado seguro de errar
            Segmentos = Cat.Dominio.Acesso.Segmentos.Todos
                .Where(s => linha.Segmentos.Any(l => l.Segmento == s.Chave))
                .Select(s => s.Chave).ToList(),
        }.ComTentativas(linha.TentativasFalhas, DoBanco(linha.BloqueadoAte), DoBanco(linha.UltimoAcesso));
    }

    private static DateTimeOffset? DoBanco(DateTime? valor) =>
        valor is { } v ? new DateTimeOffset(DateTime.SpecifyKind(v, DateTimeKind.Utc)) : null;

    // O Postgres guarda microssegundos; truncar antes de gravar faz o instante
    // devolvido no login ser o mesmo que o /api/auth/eu lê do banco depois.
    private static DateTime? ParaBanco(DateTimeOffset? valor) =>
        valor is { } v ? new DateTime(v.UtcTicks - v.UtcTicks % 10, DateTimeKind.Utc) : null;

    private static string Prefixo(string resumo) => resumo[..Math.Min(7, resumo.Length)];
}
