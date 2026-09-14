using System.Text.Json;
using Cat.Aplicacao.Trabalhos;
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
        return linha is null ? null : Lida(linha);
    }

    public async Task<IReadOnlyList<ExecucaoLida>> Listar(int projetoId, string etapa, int limite, CancellationToken cancelar) =>
        (await banco.Execucoes.AsNoTracking()
            .Where(e => e.ProjetoId == projetoId && e.Etapa == etapa)
            .OrderByDescending(e => e.Id)
            .Take(limite)
            .ToListAsync(cancelar))
        .Select(Lida).ToList();

    private static ExecucaoLida Lida(ExecucaoLinha e) => new(
        e.Id, e.ProjetoId, e.Etapa, e.Situacao, e.Passo, e.Fracao, e.ArquivosTotais, e.ArquivosLidos, e.BytesLidos,
        e.Documentos, e.Erro, Utc(e.IniciadaEm), e.TerminadaEm is { } t ? Utc(t) : null, Resumo(e.Resumo));

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
