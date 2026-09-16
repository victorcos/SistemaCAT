using System.Text.Encodings.Web;
using System.Text.Json;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class TrabalhoRepositorio(CatDbContext banco) : IRepositorioDeTrabalhos
{
    private static readonly JsonSerializerOptions Json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    // ---------------------------------------------------------------- empresas
    public async Task<IReadOnlyList<EmpresaLida>> ListarEmpresas(CancellationToken cancelar) =>
        await banco.Empresas.AsNoTracking()
            .OrderBy(e => e.RazaoSocial)
            .Select(e => new EmpresaLida(e.Id, e.CnpjRaiz, e.CnpjMatriz, e.RazaoSocial, e.Uf, e.InscricaoEstadual,
                e.PreCadastro, banco.Projetos.Any(p => p.EmpresaId == e.Id)))
            .ToListAsync(cancelar);

    public Task<bool> EmpresaExiste(int id, CancellationToken cancelar) => banco.Empresas.AnyAsync(e => e.Id == id, cancelar);

    public Task<bool> RaizCadastrada(string raiz, CancellationToken cancelar) =>
        banco.Empresas.AnyAsync(e => e.CnpjRaiz == raiz, cancelar);

    public async Task<EmpresaLida> CriarEmpresa(NovaEmpresa nova, Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var empresa = new EmpresaLinha
        {
            CnpjRaiz = nova.CnpjRaiz, CnpjMatriz = nova.CnpjMatriz, RazaoSocial = nova.RazaoSocial, Uf = nova.Uf,
            InscricaoEstadual = nova.InscricaoEstadual, GrupoEconomico = nova.GrupoEconomico,
            PreCadastro = true, Ativa = true, CriadaPor = por.Id,
        };
        banco.Empresas.Add(empresa);
        await banco.SaveChangesAsync(cancelar);

        banco.Estabelecimentos.Add(new EstabelecimentoLinha
        {
            EmpresaId = empresa.Id, Cnpj = nova.CnpjMatriz, Ie = nova.InscricaoEstadual, Nome = nova.RazaoSocial,
            Uf = nova.Uf, EMatriz = true, Ativo = true,
        });
        banco.Alocacoes.Add(new AlocacaoLinha
        {
            UsuarioId = por.Id, EmpresaId = empresa.Id, PapelProjeto = "responsavel", AlocadoPor = por.Id,
            Inicio = Utc(agora),
        });
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();

        return new EmpresaLida(empresa.Id, empresa.CnpjRaiz, empresa.CnpjMatriz, empresa.RazaoSocial, empresa.Uf,
            empresa.InscricaoEstadual, empresa.PreCadastro, TemProjeto: false);
    }

    // ---------------------------------------------------------------- projetos
    public Task<IReadOnlyList<ProjetoLido>> ListarProjetos(CancellationToken cancelar) => Ler(null, cancelar);

    public async Task<ProjetoLido?> BuscarProjeto(int id, CancellationToken cancelar) =>
        (await Ler(id, cancelar)).FirstOrDefault();

    public Task<bool> ProjetoRepetido(int empresaId, string frente, string nome, CancellationToken cancelar) =>
        banco.Projetos.AnyAsync(p => p.EmpresaId == empresaId && p.Frente == frente && p.Nome == nome, cancelar);

    public async Task<int> CriarProjeto(NovoProjeto novo, Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        var linha = new ProjetoLinha
        {
            EmpresaId = novo.EmpresaId, Frente = novo.Frente, Nome = novo.Nome,
            CompetenciaIni = novo.CompetenciaIni, CompetenciaFim = novo.CompetenciaFim,
            Status = Dominio.Projeto.StatusDoProjeto.EmAndamento, Observacao = novo.Observacao,
            CriadoEm = Utc(agora), CriadoPor = por.Id,
            // quem cria responde, até passar adiante
            ResponsavelId = por.Id,
        };
        banco.Projetos.Add(linha);
        await banco.SaveChangesAsync(cancelar);
        banco.ChangeTracker.Clear();
        return linha.Id;
    }

    public async Task RegistrarEvento(int projetoId, string tipo, string texto, object? dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar)
    {
        banco.Eventos.Add(new EventoLinha
        {
            ProjetoId = projetoId, Tipo = tipo, Texto = texto,
            Dados = dados is null ? null : JsonSerializer.Serialize(dados, Json),
            AutorId = por.Id,
            // o nome do momento: quem lê o histórico daqui a um ano quer o nome
            // que a pessoa tinha quando fez, não o de agora
            AutorNome = string.IsNullOrEmpty(por.NomeExibicao) ? "Sistema" : por.NomeExibicao,
            CriadoEm = Utc(agora),
        });
        try
        {
            await banco.SaveChangesAsync(cancelar);
        }
        finally
        {
            banco.ChangeTracker.Clear();
        }
    }

    /// <summary>
    /// A leitura agregada. O projeto e seus nomes numa consulta; base, execuções
    /// e comentários em uma consulta cada, para todos os projetos de uma vez.
    /// </summary>
    private async Task<IReadOnlyList<ProjetoLido>> Ler(int? id, CancellationToken cancelar)
    {
        var consulta = banco.Projetos.AsNoTracking().Where(p => id == null || p.Id == id);
        var linhas = await (
            from p in consulta
            join e in banco.Empresas on p.EmpresaId equals e.Id
            join autor in banco.Usuarios on p.CriadoPor equals (int?)autor.Id into autores
            from autor in autores.DefaultIfEmpty()
            join resp in banco.Usuarios on p.ResponsavelId equals (int?)resp.Id into responsaveis
            from resp in responsaveis.DefaultIfEmpty()
            orderby p.CriadoEm descending
            select new
            {
                p, Empresa = e.RazaoSocial, e.CnpjMatriz, e.Uf, e.PreCadastro,
                Autor = autor == null ? null : autor.NomeExibicao,
                Responsavel = resp == null ? null : resp.NomeExibicao,
            }).ToListAsync(cancelar);
        if (linhas.Count == 0)
            return [];

        var ids = linhas.Select(l => l.p.Id).ToList();
        var comBase = (await banco.Lotes.AsNoTracking()
            .Where(l => ids.Contains(l.ProjetoId) && l.ArquivosUteis > 0)
            .Select(l => l.ProjetoId).Distinct().ToListAsync(cancelar)).ToHashSet();
        var comentarios = await banco.Eventos.AsNoTracking()
            .Where(ev => ids.Contains(ev.ProjetoId) && ev.Tipo == Dominio.Projeto.TipoDeEvento.Comentario)
            .GroupBy(ev => ev.ProjetoId)
            .Select(g => new { g.Key, Total = g.Count() })
            .ToDictionaryAsync(g => g.Key, g => g.Total, cancelar);
        // a última rodada de cada etapa, pela ordem de criação — é a que diz onde o trabalho está
        var execucoes = await banco.Execucoes.AsNoTracking()
            .Where(x => ids.Contains(x.ProjetoId) && Execucoes.DeProcessamento.Contains(x.Etapa))
            .Select(x => new { x.Id, x.ProjetoId, x.Etapa, x.Situacao })
            .ToListAsync(cancelar);
        var ultimas = execucoes
            .GroupBy(x => (x.ProjetoId, x.Etapa))
            .ToDictionary(g => g.Key, g => g.MaxBy(x => x.Id)!.Situacao);

        return linhas.Select(l => new ProjetoLido(
            l.p.Id, l.p.EmpresaId, l.Empresa, l.CnpjMatriz, l.Uf, l.PreCadastro, l.p.Frente, l.p.Nome,
            l.p.CompetenciaIni, l.p.CompetenciaFim, l.p.Status, l.Autor, l.p.CriadoPor, l.Responsavel, l.p.ResponsavelId,
            comentarios.GetValueOrDefault(l.p.Id), comBase.Contains(l.p.Id),
            ultimas.Where(u => u.Key.ProjetoId == l.p.Id).ToDictionary(u => u.Key.Etapa, u => u.Value),
            l.p.VendaAConsumidor)).ToList();
    }

    public async Task DefinirVendaAConsumidor(int projetoId, string valor, object dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        await banco.Projetos.Where(p => p.Id == projetoId)
            .ExecuteUpdateAsync(s => s.SetProperty(p => p.VendaAConsumidor, valor), cancelar);
        banco.Eventos.Add(new EventoLinha
        {
            ProjetoId = projetoId, Tipo = Dominio.Projeto.TipoDeEvento.ParametroAlterado,
            Texto = "Venda a consumidor final: " + Dominio.Projeto.VendaAConsumidor.DoBanco(valor).Rotulo,
            Dados = JsonSerializer.Serialize(dados, Json),
            AutorId = por.Id,
            AutorNome = string.IsNullOrEmpty(por.NomeExibicao) ? "Sistema" : por.NomeExibicao,
            CriadoEm = Utc(agora),
        });
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
    }

    // ---------------------------------------------------------------- exclusão
    public async Task<OQueSeraApagado?> ResumirExclusao(int projetoId, CancellationToken cancelar)
    {
        var projeto = await (
            from p in banco.Projetos.AsNoTracking()
            join e in banco.Empresas on p.EmpresaId equals e.Id into empresas
            from e in empresas.DefaultIfEmpty()
            where p.Id == projetoId
            select new { p.Nome, Empresa = e == null ? "" : e.RazaoSocial }).FirstOrDefaultAsync(cancelar);
        if (projeto is null)
            return null;

        var lotes = banco.Lotes.Where(l => l.ProjetoId == projetoId);
        return new OQueSeraApagado(
            projeto.Nome, projeto.Empresa,
            await lotes.CountAsync(cancelar),
            await banco.ArquivosDoLote.CountAsync(a => lotes.Select(l => l.Id).Contains(a.LoteId), cancelar),
            await banco.Execucoes.CountAsync(x => x.ProjetoId == projetoId, cancelar));
    }

    public async Task<IReadOnlyList<string>> PastasDeTrabalho(int projetoId, CancellationToken cancelar) =>
        await banco.Execucoes.AsNoTracking()
            .Where(x => x.ProjetoId == projetoId && x.PastaDeTrabalho != null && x.PastaDeTrabalho != "")
            .Select(x => x.PastaDeTrabalho!)
            .Distinct()
            .ToListAsync(cancelar);

    public async Task ApagarTrabalho(int projetoId, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var lotes = banco.Lotes.Where(l => l.ProjetoId == projetoId).Select(l => l.Id);
        await banco.ArquivosDoLote.Where(a => lotes.Contains(a.LoteId)).ExecuteDeleteAsync(cancelar);
        await banco.Execucoes.Where(x => x.ProjetoId == projetoId).ExecuteDeleteAsync(cancelar);
        await banco.Lotes.Where(l => l.ProjetoId == projetoId).ExecuteDeleteAsync(cancelar);
        // evento_do_projeto cai em cascata (ON DELETE CASCADE na migração)
        await banco.Projetos.Where(p => p.Id == projetoId).ExecuteDeleteAsync(cancelar);
        await transacao.CommitAsync(cancelar);
    }

    private static DateTime Utc(DateTimeOffset instante) =>
        new(instante.UtcTicks - instante.UtcTicks % 10, DateTimeKind.Utc);
}
