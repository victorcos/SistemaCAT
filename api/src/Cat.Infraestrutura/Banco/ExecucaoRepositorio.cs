using System.Text.Json;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

/// <summary>
/// Só leitura: quem cria a execução é o motor (<c>/interno/execucoes</c>) e quem
/// grava o progresso é o trabalhador da fila. A tela acompanha por aqui.
/// </summary>
public sealed class ExecucaoRepositorio(CatDbContext banco) : IRepositorioDeExecucoes
{
    public async Task<ExecucaoLida?> Buscar(int id, CancellationToken cancelar)
    {
        var linha = await banco.Execucoes.AsNoTracking().FirstOrDefaultAsync(e => e.Id == id, cancelar);
        return linha is null ? null : (await Lidas([linha], cancelar))[0];
    }

    public async Task<IReadOnlyList<ExecucaoLida>> Listar(int projetoId, string etapa, int limite, CancellationToken cancelar) =>
        await Lidas(await banco.Execucoes.AsNoTracking()
            .Where(e => e.ProjetoId == projetoId && e.Etapa == etapa)
            .OrderByDescending(e => e.Id)
            .Take(limite)
            .ToListAsync(cancelar), cancelar);

    public async Task<int?> UltimaConcluida(int projetoId, string etapa, CancellationToken cancelar) =>
        await banco.Execucoes.AsNoTracking()
            .Where(e => e.ProjetoId == projetoId && e.Etapa == etapa && e.Situacao == "concluida")
            .OrderByDescending(e => e.Id)
            .Select(e => (int?)e.Id)
            .FirstOrDefaultAsync(cancelar);

    public async Task<bool> AprovarEntrega(int execucaoId, int projetoId, Usuario por, string texto, object dados,
        DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var quando = agora.UtcDateTime;
        // só sobre a que ainda não tem aprovação: dois revisores ao mesmo tempo, vale o primeiro
        var gravadas = await banco.Execucoes
            .Where(e => e.Id == execucaoId && e.AprovadaEm == null)
            .ExecuteUpdateAsync(s => s.SetProperty(e => e.AprovadaPor, por.Id).SetProperty(e => e.AprovadaEm, quando), cancelar);
        if (gravadas == 0)
            return false;
        banco.Eventos.Add(new EventoLinha
        {
            ProjetoId = projetoId, Tipo = Dominio.Projeto.TipoDeEvento.EntregaAprovada, Texto = texto,
            Dados = JsonSerializer.Serialize(dados, Json),
            AutorId = por.Id,
            AutorNome = string.IsNullOrEmpty(por.NomeExibicao) ? "Sistema" : por.NomeExibicao,
            CriadoEm = quando,
        });
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
        return true;
    }

    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = null };

    /// <summary>Com o nome de quem aprovou, numa consulta só para a lista inteira.</summary>
    private async Task<IReadOnlyList<ExecucaoLida>> Lidas(IReadOnlyList<ExecucaoLinha> linhas, CancellationToken cancelar)
    {
        var ids = linhas.Where(l => l.AprovadaPor is not null).Select(l => l.AprovadaPor!.Value).Distinct().ToList();
        var nomes = ids.Count == 0
            ? new Dictionary<int, string>()
            : await banco.Usuarios.AsNoTracking().Where(u => ids.Contains(u.Id))
                .ToDictionaryAsync(u => u.Id, u => u.NomeExibicao, cancelar);
        return linhas.Select(e => Lida(e, e.AprovadaPor is { } p ? nomes.GetValueOrDefault(p) : null)).ToList();
    }

    private static ExecucaoLida Lida(ExecucaoLinha e, string? aprovadaPor) => new(
        e.Id, e.ProjetoId, e.Etapa, e.Situacao, e.Passo, e.Fracao, e.ArquivosTotais, e.ArquivosLidos, e.BytesLidos,
        e.Documentos, e.Erro, Utc(e.IniciadaEm), e.TerminadaEm is { } t ? Utc(t) : null, Resumo(e.Resumo),
        aprovadaPor, e.AprovadaEm is { } a ? Utc(a) : null);

    private static DateTimeOffset Utc(DateTime valor) => new(DateTime.SpecifyKind(valor, DateTimeKind.Utc));

    private static JsonElement? Resumo(string? texto)
    {
        if (string.IsNullOrEmpty(texto))
            return null;
        try
        {
            using var documento = JsonDocument.Parse(texto);
            return documento.RootElement.ValueKind == JsonValueKind.Null ? null : documento.RootElement.Clone();
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
