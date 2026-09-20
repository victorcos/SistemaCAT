using System.Text.Encodings.Web;
using System.Text.Json;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class CorrecaoRepositorio(CatDbContext banco) : IRepositorioDeCorrecoes
{
    private static readonly JsonSerializerOptions Json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    public async Task<IReadOnlyList<CorrecaoGravada>> Listar(int projetoId, bool somenteAtivas,
        CancellationToken cancelar)
    {
        var consulta = banco.Correcoes.AsNoTracking().Where(c => c.ProjetoId == projetoId);
        if (somenteAtivas)
            consulta = consulta.Where(c => c.Situacao == "ativa");
        // quem fez a correção pode ter sido desativado depois: o nome vem por
        // junção à esquerda, e a linha aparece mesmo sem autor
        var linhas = await (
            from c in consulta.OrderByDescending(c => c.CriadaEm).ThenByDescending(c => c.Id)
            join u in banco.Usuarios.AsNoTracking() on c.CriadaPor equals u.Id into autores
            from autor in autores.DefaultIfEmpty()
            select new { Linha = c, Nome = autor != null ? autor.NomeExibicao : null }
        ).ToListAsync(cancelar);
        return linhas.Select(x => Traduzir(x.Linha, x.Nome)).ToList();
    }

    public async Task<int> Gravar(int projetoId, IReadOnlyList<CorrecaoDoTrabalho> correcoes, string texto,
        object dados, Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        // o Postgres guarda microssegundos: o resto dos ticks some ao gravar
        var quando = new DateTime(agora.UtcTicks - agora.UtcTicks % 10, DateTimeKind.Utc);
        var existentes = await banco.Correcoes
            .Where(c => c.ProjetoId == projetoId)
            .ToDictionaryAsync(c => (c.Campo, c.Cnpj, c.Codigo, c.Documento, c.NumeroItem), cancelar);
        foreach (var c in correcoes)
        {
            if (!existentes.TryGetValue((c.Campo, c.Cnpj, c.Codigo, c.Documento, c.NumeroItem), out var linha))
            {
                linha = new CorrecaoLinha
                {
                    ProjetoId = projetoId, Campo = c.Campo, Cnpj = c.Cnpj, Codigo = c.Codigo,
                    Documento = c.Documento, NumeroItem = c.NumeroItem,
                };
                banco.Correcoes.Add(linha);
            }
            linha.Valor = c.Valor;
            linha.ValorAnterior = c.ValorAnterior;
            linha.Motivo = c.Motivo;
            linha.Situacao = "ativa";
            linha.CriadaPor = por.Id;
            linha.CriadaEm = quando;
            linha.DesfeitaPor = null;
            linha.DesfeitaEm = null;
        }
        Registrar(projetoId, TipoDeEvento.CorrecaoAplicada, texto, dados, por, quando);
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
        return correcoes.Count;
    }

    public async Task<CorrecaoGravada?> Desfazer(int projetoId, int correcaoId, string texto, object dados,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var linha = await banco.Correcoes.FirstOrDefaultAsync(
            c => c.Id == correcaoId && c.ProjetoId == projetoId, cancelar);
        if (linha is null)
            return null;
        var quando = new DateTime(agora.UtcTicks - agora.UtcTicks % 10, DateTimeKind.Utc);
        linha.Situacao = "desfeita";
        linha.DesfeitaPor = por.Id;
        linha.DesfeitaEm = quando;
        Registrar(projetoId, TipoDeEvento.CorrecaoDesfeita, texto, dados, por, quando);
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
        return Traduzir(linha, por.NomeExibicao);
    }

    private void Registrar(int projetoId, string tipo, string texto, object dados, Usuario por, DateTime quando) =>
        banco.Eventos.Add(new EventoLinha
        {
            ProjetoId = projetoId, Tipo = tipo, Texto = texto,
            Dados = JsonSerializer.Serialize(dados, Json), AutorId = por.Id,
            AutorNome = string.IsNullOrEmpty(por.NomeExibicao) ? "Sistema" : por.NomeExibicao,
            CriadoEm = quando,
        });

    private static CorrecaoGravada Traduzir(CorrecaoLinha c, string? autor)
    {
        var correcao = new CorrecaoDoTrabalho(c.Campo, c.Valor, c.Motivo, c.Cnpj, c.Codigo, c.Documento,
            c.NumeroItem, c.ValorAnterior ?? "");
        return new CorrecaoGravada(c.Id, c.Campo, Correcao.Rotulo(c.Campo), correcao.Onde, c.Cnpj, c.Codigo,
            c.Documento, c.NumeroItem, c.Valor, c.ValorAnterior ?? "", c.Motivo, c.Situacao,
            string.IsNullOrEmpty(autor) ? "Sistema" : autor, new DateTimeOffset(c.CriadaEm, TimeSpan.Zero),
            correcao.Frase);
    }
}
