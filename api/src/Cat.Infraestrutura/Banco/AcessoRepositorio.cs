using Cat.Aplicacao.Acesso;
using Cat.Dominio.Acesso;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class AcessoRepositorio(CatDbContext banco) : IRepositorioDeAcesso
{
    // o papel no projeto de quem ganha acesso pela tela; o de quem cadastra a
    // empresa ou a semeia é outro, e continua sendo gravado por quem cadastra
    public const string PapelPadrao = "executor";

    public async Task<IReadOnlyList<EmpresaParaAcesso>> ListarEmpresas(CancellationToken cancelar) =>
        await banco.Empresas.AsNoTracking()
            .OrderBy(e => e.RazaoSocial)
            .Select(e => new EmpresaParaAcesso(e.Id, e.RazaoSocial, e.Uf))
            .ToListAsync(cancelar);

    public async Task<IReadOnlyDictionary<int, DateTimeOffset>> Vigentes(int usuarioId, CancellationToken cancelar)
    {
        var linhas = await banco.Alocacoes.AsNoTracking()
            .Where(a => a.UsuarioId == usuarioId && a.Fim == null)
            .Select(a => new { a.EmpresaId, a.Inicio })
            .ToListAsync(cancelar);
        // duas alocações vigentes na mesma empresa não deveriam existir; se
        // existirem, vale a mais antiga, que é desde quando a pessoa alcança
        return linhas.GroupBy(a => a.EmpresaId).ToDictionary(
            g => g.Key,
            g => new DateTimeOffset(DateTime.SpecifyKind(g.Min(a => a.Inicio), DateTimeKind.Utc)));
    }

    public async Task Aplicar(int usuarioId, IReadOnlyCollection<int> conceder, IReadOnlyCollection<int> encerrar,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        var instante = new DateTime(agora.UtcTicks - agora.UtcTicks % 10, DateTimeKind.Utc);
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);

        foreach (var empresaId in conceder)
            banco.Alocacoes.Add(new AlocacaoLinha
            {
                UsuarioId = usuarioId,
                EmpresaId = empresaId,
                PapelProjeto = PapelPadrao,
                AlocadoPor = por.Id,
                Inicio = instante,
            });
        await banco.SaveChangesAsync(cancelar);

        if (encerrar.Count > 0)
        {
            var motivo = $"acesso encerrado por {por.NomeDeUsuario}";
            // a linha fica: quem tinha acesso em março continua respondível
            await banco.Alocacoes
                .Where(a => a.UsuarioId == usuarioId && encerrar.Contains(a.EmpresaId) && a.Fim == null)
                .ExecuteUpdateAsync(s => s
                    .SetProperty(a => a.Fim, instante)
                    .SetProperty(a => a.MotivoSaida, motivo), cancelar);
        }

        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
    }
}
