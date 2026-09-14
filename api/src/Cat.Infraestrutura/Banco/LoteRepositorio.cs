using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class LoteRepositorio(CatDbContext banco) : IRepositorioDeLotes
{
    public async Task<IReadOnlyList<LoteLido>> Listar(int projetoId, CancellationToken cancelar)
    {
        var linhas = await banco.Lotes.AsNoTracking()
            .Where(l => l.ProjetoId == projetoId)
            .OrderByDescending(l => l.CriadoEm)
            .ToListAsync(cancelar);
        if (linhas.Count == 0)
            return [];

        var ids = linhas.Select(l => l.Id).ToList();
        var contagens = (await banco.ArquivosDoLote.AsNoTracking()
                .Where(a => ids.Contains(a.LoteId))
                .GroupBy(a => new { a.LoteId, a.Tipo })
                .Select(g => new { g.Key.LoteId, g.Key.Tipo, Quantidade = g.Count() })
                .ToListAsync(cancelar))
            .GroupBy(c => c.LoteId)
            .ToDictionary(g => g.Key, g => g.Select(c => (c.Tipo, c.Quantidade)).ToList());

        return linhas.Select(l => Lido(l, contagens.GetValueOrDefault(l.Id) ?? [])).ToList();
    }

    public async Task<LoteLido> Criar(int projetoId, string pasta, IReadOnlyList<ArquivoInspecionado> arquivos,
        string? observacao, Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        // o período é o do que a CAT lê, não o de tudo que estava na pasta
        var competencias = arquivos.Where(a => a.Competencia is not null && a.AlimentaACat)
            .Select(a => a.Competencia!.Value).Distinct().Order().ToList();
        var lote = new LoteLinha
        {
            ProjetoId = projetoId,
            Pasta = pasta,
            TotalArquivos = arquivos.Count,
            ArquivosUteis = arquivos.Count(a => a.AlimentaACat),
            BytesTotais = arquivos.Sum(a => a.Tamanho),
            CompetenciaIni = competencias.Count > 0 ? competencias[0] : null,
            CompetenciaFim = competencias.Count > 0 ? competencias[^1] : null,
            Observacao = observacao,
            CriadoEm = new DateTime(agora.UtcTicks - agora.UtcTicks % 10, DateTimeKind.Utc),
            CriadoPor = por.Id,
        };

        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        banco.Lotes.Add(lote);
        await banco.SaveChangesAsync(cancelar);

        // uma base real tem 7.036 arquivos: sem isto o EF compara cada entidade a cada inclusão
        banco.ChangeTracker.AutoDetectChangesEnabled = false;
        try
        {
            banco.ArquivosDoLote.AddRange(arquivos.Select(a => new ArquivoDoLoteLinha
            {
                LoteId = lote.Id, Caminho = a.Caminho, Nome = a.Nome, Tamanho = a.Tamanho, Tipo = a.Tipo,
                Cnpj = a.Cnpj, Competencia = a.Competencia, Uf = string.IsNullOrEmpty(a.Uf) ? null : a.Uf,
                Detalhe = string.IsNullOrEmpty(a.Detalhe) ? null : a.Detalhe, Retificadora = a.Retificadora,
                HashConteudo = a.HashConteudo,
            }));
            await banco.SaveChangesAsync(cancelar);
        }
        finally
        {
            banco.ChangeTracker.AutoDetectChangesEnabled = true;
        }
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();

        var contagens = arquivos.GroupBy(a => a.Tipo).Select(g => (g.Key, g.Count())).ToList();
        return Lido(lote, contagens);
    }

    public Task<int?> ProjetoDoLote(int loteId, CancellationToken cancelar) =>
        banco.Lotes.Where(l => l.Id == loteId).Select(l => (int?)l.ProjetoId).FirstOrDefaultAsync(cancelar);

    public async Task<LoteRemovido> Remover(int loteId, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var lote = await banco.Lotes.AsNoTracking().FirstAsync(l => l.Id == loteId, cancelar);
        // toda conferência já feita olhou este lote; tirá-lo muda o resultado
        var conferencias = await banco.Execucoes.CountAsync(x => x.ProjetoId == lote.ProjetoId && x.Situacao == "concluida", cancelar);
        var arquivos = await banco.ArquivosDoLote.Where(a => a.LoteId == loteId).ExecuteDeleteAsync(cancelar);
        await banco.Lotes.Where(l => l.Id == loteId).ExecuteDeleteAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        return new LoteRemovido(lote.Pasta, arquivos, conferencias);
    }

    private static LoteLido Lido(LoteLinha l, IReadOnlyList<(string Tipo, int Quantidade)> contagens) => new(
        l.Id, l.ProjetoId, l.Pasta, l.TotalArquivos, l.ArquivosUteis, l.BytesTotais, l.CompetenciaIni, l.CompetenciaFim,
        l.Observacao, new DateTimeOffset(DateTime.SpecifyKind(l.CriadoEm, DateTimeKind.Utc)), contagens);
}
