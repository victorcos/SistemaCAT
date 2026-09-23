using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Lote;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class LoteRepositorio(CatDbContext banco) : IRepositorioDeLotes
{
    /// <summary>O módulo do trabalho: é ele que diz quais arquivos do lote são úteis.</summary>
    private async Task<string> Modulo(int projetoId, CancellationToken cancelar) =>
        await banco.Projetos.AsNoTracking().Where(p => p.Id == projetoId).Select(p => p.Modulo)
            .FirstOrDefaultAsync(cancelar) ?? Segmentos.Icms;

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

        var modulo = await Modulo(projetoId, cancelar);
        return linhas.Select(l => Lido(l, contagens.GetValueOrDefault(l.Id) ?? [], modulo)).ToList();
    }

    public async Task<LoteLido> Criar(int projetoId, string pasta, IReadOnlyList<ArquivoInspecionado> arquivos,
        string? observacao, Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        // o período é o do que ESTE trabalho lê, não o de tudo que estava na pasta
        var competencias = arquivos.Where(a => a.Competencia is not null && a.Alimenta)
            .Select(a => a.Competencia!.Value).Distinct().Order().ToList();
        var lote = new LoteLinha
        {
            ProjetoId = projetoId,
            Pasta = pasta,
            TotalArquivos = arquivos.Count,
            ArquivosUteis = arquivos.Count(a => a.Alimenta),
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
        return Lido(lote, contagens, await Modulo(projetoId, cancelar));
    }

    public async Task<Reclassificacao> Reclassificar(int projetoId, IReadOnlyList<ArquivoInspecionado> arquivos,
        string modulo,
        CancellationToken cancelar)
    {
        var porCaminho = arquivos.ToDictionary(a => a.Caminho, StringComparer.Ordinal);
        var caminhos = porCaminho.Keys.ToList();

        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var linhas = await banco.ArquivosDoLote
            .Where(a => caminhos.Contains(a.Caminho) && banco.Lotes.Any(l => l.Id == a.LoteId && l.ProjetoId == projetoId))
            .ToListAsync(cancelar);
        foreach (var linha in linhas)
        {
            var a = porCaminho[linha.Caminho];
            linha.Tipo = a.Tipo;
            linha.Cnpj = a.Cnpj;
            linha.Competencia = a.Competencia;
            linha.Uf = string.IsNullOrEmpty(a.Uf) ? null : a.Uf;
            linha.Detalhe = string.IsNullOrEmpty(a.Detalhe) ? null : a.Detalhe;
            linha.Retificadora = a.Retificadora;
        }
        await banco.SaveChangesAsync(cancelar);

        // o que ESTE trabalho lê e o período de cada lote tocado, como no registro
        var tocados = linhas.GroupBy(l => l.LoteId).OrderByDescending(g => g.Count()).Select(g => g.Key).ToList();
        foreach (var loteId in tocados)
        {
            var dele = await banco.ArquivosDoLote.AsNoTracking().Where(a => a.LoteId == loteId)
                .Select(a => new { a.Tipo, a.Competencia }).ToListAsync(cancelar);
            var uteis = dele.Where(a => TiposDeArquivo.Buscar(a.Tipo).Alimenta(modulo)).ToList();
            var competencias = uteis.Where(a => a.Competencia is not null).Select(a => a.Competencia!.Value)
                .Distinct().Order().ToList();
            await banco.Lotes.Where(l => l.Id == loteId).ExecuteUpdateAsync(s => s
                .SetProperty(l => l.ArquivosUteis, uteis.Count)
                .SetProperty(l => l.CompetenciaIni, competencias.Count > 0 ? competencias[0] : (DateOnly?)null)
                .SetProperty(l => l.CompetenciaFim, competencias.Count > 0 ? competencias[^1] : (DateOnly?)null), cancelar);
        }
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
        return new Reclassificacao(linhas.Count, tocados);
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

    private static LoteLido Lido(LoteLinha l, IReadOnlyList<(string Tipo, int Quantidade)> contagens,
        string modulo) => new(
        l.Id, l.ProjetoId, l.Pasta, l.TotalArquivos, l.ArquivosUteis, l.BytesTotais, l.CompetenciaIni, l.CompetenciaFim,
        l.Observacao, new DateTimeOffset(DateTime.SpecifyKind(l.CriadoEm, DateTimeKind.Utc)), contagens, modulo);
}
