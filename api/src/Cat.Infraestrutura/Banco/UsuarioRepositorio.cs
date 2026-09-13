using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace Cat.Infraestrutura.Banco;

/// <summary>Traduz tabela em entidade de domínio, e de volta.</summary>
public sealed class UsuarioRepositorio(CatDbContext banco, ILogger<UsuarioRepositorio> log) : IRepositorioDeUsuario
{
    public async Task<Usuario?> BuscarPorNome(string nomeDeUsuario, CancellationToken cancelar)
    {
        var linha = await Consulta().FirstOrDefaultAsync(u => u.Usuario == nomeDeUsuario, cancelar);
        return linha is null ? null : ParaDominio(linha);
    }

    public async Task<Usuario?> BuscarPorId(int id, CancellationToken cancelar)
    {
        var linha = await Consulta().FirstOrDefaultAsync(u => u.Id == id, cancelar);
        return linha is null ? null : ParaDominio(linha);
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
        banco.Usuarios.AsNoTracking().Include(u => u.Alocacoes.Where(a => a.Fim == null));

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
