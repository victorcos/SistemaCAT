using System.Text.Encodings.Web;
using System.Text.Json;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class HistoricoRepositorio(CatDbContext banco) : IRepositorioDeHistorico
{
    private static readonly JsonSerializerOptions Json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    public async Task<IReadOnlyList<EventoLido>> Listar(int projetoId, int? antesDe, int quantos, bool soComentarios,
        CancellationToken cancelar)
    {
        var consulta = banco.Eventos.AsNoTracking().Where(e => e.ProjetoId == projetoId);
        if (soComentarios)
            consulta = consulta.Where(e => e.Tipo == TipoDeEvento.Comentario);
        if (antesDe is { } limite)
            consulta = consulta.Where(e => e.Id < limite);
        var linhas = await consulta.OrderByDescending(e => e.Id).Take(quantos).ToListAsync(cancelar);
        return linhas.Select(Lido).ToList();
    }

    public async Task<EventoLido> Comentar(int projetoId, string texto, Usuario por, DateTimeOffset agora,
        CancellationToken cancelar)
    {
        var linha = Evento(projetoId, TipoDeEvento.Comentario, texto, null, por, agora);
        banco.Eventos.Add(linha);
        await banco.SaveChangesAsync(cancelar);
        banco.ChangeTracker.Clear();
        return Lido(linha);
    }

    public async Task MudarStatus(int projetoId, string novo, string motivo, object dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        await banco.Projetos.Where(p => p.Id == projetoId)
            .ExecuteUpdateAsync(s => s.SetProperty(p => p.Status, novo), cancelar);
        banco.Eventos.Add(Evento(projetoId, TipoDeEvento.Status, motivo, dados, por, agora));
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
    }

    public async Task<IReadOnlyList<Candidato>> Candidatos(int empresaId, CancellationToken cancelar)
    {
        // os papéis que escrevem, pela capacidade do domínio e não por lista escrita aqui
        var papeis = Enum.GetValues<Papel>().Where(p => p.PodeEscrever()).Select(p => p.Valor()).ToList();
        var linhas = await banco.Usuarios.AsNoTracking()
            .Where(u => u.Ativo && papeis.Contains(u.Papel))
            .OrderBy(u => u.NomeExibicao)
            .Select(u => new
            {
                u.Id, u.NomeExibicao, u.Usuario, u.Papel, u.Cargo,
                Alocado = banco.Alocacoes.Any(a => a.UsuarioId == u.Id && a.EmpresaId == empresaId && a.Fim == null),
            })
            .ToListAsync(cancelar);
        return linhas.Select(u => new Candidato(u.Id, u.NomeExibicao, u.Usuario, u.Papel, u.Cargo,
            // gestor e dev enxergam todas pelo papel: para eles não há alocação a criar
            Alcanca: u.Alocado || (TextoDeAcesso.TentarPapel(u.Papel, out var papel) && papel.IgnoraEscopoDeEmpresa())))
            .ToList();
    }

    public async Task Suceder(int projetoId, int empresaId, int novoId, bool alocar, string motivo, object dados,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        await banco.Projetos.Where(p => p.Id == projetoId)
            .ExecuteUpdateAsync(s => s.SetProperty(p => p.ResponsavelId, novoId), cancelar);
        if (alocar)
            banco.Alocacoes.Add(new AlocacaoLinha
            {
                UsuarioId = novoId, EmpresaId = empresaId, PapelProjeto = "responsavel", AlocadoPor = por.Id,
                Inicio = Utc(agora),
            });
        banco.Eventos.Add(Evento(projetoId, TipoDeEvento.Sucessao, motivo, dados, por, agora));
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
    }

    private static EventoLinha Evento(int projetoId, string tipo, string texto, object? dados, Usuario por,
        DateTimeOffset agora) => new()
    {
        ProjetoId = projetoId,
        Tipo = tipo,
        Texto = texto,
        Dados = dados is null ? null : JsonSerializer.Serialize(dados, Json),
        AutorId = por.Id,
        AutorNome = string.IsNullOrEmpty(por.NomeExibicao) ? "Sistema" : por.NomeExibicao,
        CriadoEm = Utc(agora),
    };

    private static EventoLido Lido(EventoLinha l)
    {
        JsonElement? dados = null;
        if (!string.IsNullOrEmpty(l.Dados))
        {
            try
            {
                dados = JsonDocument.Parse(l.Dados).RootElement.Clone();
            }
            catch (JsonException)
            {
                // dado ilegível não derruba a linha do tempo: aparece sem os detalhes
            }
        }
        return new EventoLido(l.Id, TipoDeEvento.Conhecido(l.Tipo), l.Texto, dados, l.AutorNome, l.AutorId,
            new DateTimeOffset(DateTime.SpecifyKind(l.CriadoEm, DateTimeKind.Utc)));
    }

    private static DateTime Utc(DateTimeOffset instante) =>
        new(instante.UtcTicks - instante.UtcTicks % 10, DateTimeKind.Utc);
}
