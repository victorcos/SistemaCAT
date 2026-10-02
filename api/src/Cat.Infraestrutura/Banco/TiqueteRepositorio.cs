using Cat.Aplicacao.Trabalhos;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

/// <summary>
/// Tíquetes de download no Postgres. Ver <see cref="ITiquetesDeDownload"/>.
///
/// **No banco e não em memória porque haverá mais de uma instância da API.**
/// Tíquete emitido numa e resgatado noutra tem de ser encontrado, e memória de
/// processo não atravessa instância — nem sobrevive a um reinício no meio do
/// clique de alguém.
/// </summary>
public sealed class TiqueteRepositorio(CatDbContext banco) : ITiquetesDeDownload
{
    public async Task<string> Emitir(AutorizacaoDeDownload autorizacao, DateTimeOffset agora,
        CancellationToken cancelar)
    {
        await LimparVencidos(agora, cancelar);

        var segredo = Tiquete.NovoSegredo();
        banco.Tiquetes.Add(new TiqueteLinha
        {
            Id = segredo,
            UsuarioId = autorizacao.UsuarioId,
            ExecucaoId = autorizacao.ExecucaoId,
            Etapa = autorizacao.Etapa,
            Qual = autorizacao.Qual,
            Formato = autorizacao.Formato,
            Modelos = autorizacao.Modelos,
            Classificacoes = autorizacao.Classificacoes,
            CriadoEm = agora.UtcDateTime,
            ExpiraEm = agora.Add(Tiquete.Validade).UtcDateTime,
        });
        await banco.SaveChangesAsync(cancelar);
        return segredo;
    }

    public async Task<AutorizacaoDeDownload?> Resgatar(string tiquete, DateTimeOffset agora,
        CancellationToken cancelar)
    {
        var linha = await banco.Tiquetes.FirstOrDefaultAsync(t => t.Id == tiquete, cancelar);
        if (linha is null || linha.ExpiraEm <= agora.UtcDateTime)
            return null;

        // **auditoria, não trava.** Marcar o primeiro resgate e deixar o segundo
        // passar é escolha: o gerenciador de download do navegador repete a
        // requisição, e recusar a repetição transformaria um soluço de rede em
        // "o link morreu". Quem protege é o prazo. E porque não há trava, não há
        // corrida: duas instâncias resgatando o mesmo tíquete concordam
        if (linha.UsadoEm is null)
        {
            linha.UsadoEm = agora.UtcDateTime;
            await banco.SaveChangesAsync(cancelar);
        }

        return new AutorizacaoDeDownload(linha.UsuarioId, linha.ExecucaoId, linha.Etapa,
            linha.Qual, linha.Formato, linha.Modelos, linha.Classificacoes);
    }

    /// <summary>
    /// Apaga os vencidos ao emitir um novo.
    ///
    /// Sem tarefa agendada e sem a tabela crescer para sempre: quem cria um
    /// tíquete paga a limpeza do que já não serve, e o índice
    /// <c>ix_tiquete_expira</c> faz disso uma varredura curta. Falhar aqui não
    /// pode derrubar o download — linha vencida a mais é lixo, não defeito.
    /// </summary>
    private async Task LimparVencidos(DateTimeOffset agora, CancellationToken cancelar)
    {
        try
        {
            await banco.Tiquetes.Where(t => t.ExpiraEm <= agora.UtcDateTime)
                .ExecuteDeleteAsync(cancelar);
        }
        catch (Exception) when (!cancelar.IsCancellationRequested)
        {
            // segue: emitir o tíquete é o que o usuário pediu
        }
    }
}
