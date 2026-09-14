using System.Text.Json;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

public sealed record ExecucaoLida(
    int Id, int ProjetoId, string Etapa, string Situacao, string? Passo, double Fracao, int ArquivosTotais,
    int ArquivosLidos, long BytesLidos, long Documentos, string? Erro, DateTimeOffset IniciadaEm,
    DateTimeOffset? TerminadaEm, JsonElement? Resumo);

public sealed record PlanilhaPronta(string Caminho, string Nome, string Tipo);

public interface IRepositorioDeExecucoes
{
    Task<ExecucaoLida?> Buscar(int id, CancellationToken cancelar);

    /// <summary>As mais recentes primeiro.</summary>
    Task<IReadOnlyList<ExecucaoLida>> Listar(int projetoId, string etapa, int limite, CancellationToken cancelar);
}

public sealed class ExecucaoNaoEncontrada() : RecusaDeRegra("Execução não encontrada.");

/// <summary>
/// Conferência e movimentos, portados de <c>conferencia_router.py</c> e
/// <c>movimentos_router.py</c>. A rodada não cabe numa requisição: aqui se pede
/// a execução, o motor a põe na fila e a roda, e a tela acompanha lendo a tabela.
///
/// Preparar (se há o que conferir, se a conferência já concluiu, se o trabalho
/// está parado) é do motor, porque são as mesmas regras da leitura.
/// </summary>
public sealed class Execucoes(
    IRepositorioDeTrabalhos trabalhos,
    IRepositorioDeExecucoes execucoes,
    IMotor motor,
    ILogger<Execucoes> log)
{
    public const string Conferencia = "conferencia";
    public const string Movimentos = "movimentos";

    // quantas rodadas a tela lista: a última é a que importa, as outras são contexto
    public const int NaLista = 20;

    private async Task Projeto(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var p = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
        Escopo.Exigir(usuario, p.EmpresaId, log);
    }

    public async Task<ExecucaoLida> Iniciar(string etapa, int projetoId, Usuario por, CancellationToken cancelar)
    {
        await Projeto(projetoId, por, cancelar);
        var id = await motor.PedirExecucao(etapa, projetoId, por.Id, cancelar);
        log.Info("execução pedida ao motor", new { execucao_id = id, etapa, projeto_id = projetoId, por_usuario_id = por.Id });
        return await execucoes.Buscar(id, cancelar) ?? throw new ExecucaoNaoEncontrada();
    }

    public async Task<IReadOnlyList<ExecucaoLida>> Listar(string etapa, int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        await Projeto(projetoId, usuario, cancelar);
        return await execucoes.Listar(projetoId, etapa, NaLista, cancelar);
    }

    /// <param name="etapaExigida">
    /// A rota de movimentos só mostra execução de movimentos; a de conferência,
    /// como no Python, mostra qualquer uma pelo identificador.
    /// </param>
    public async Task<ExecucaoLida> Detalhar(int execucaoId, string? etapaExigida, Usuario usuario, CancellationToken cancelar)
    {
        var e = await execucoes.Buscar(execucaoId, cancelar) ?? throw new ExecucaoNaoEncontrada();
        await Projeto(e.ProjetoId, usuario, cancelar);
        if (etapaExigida is not null && e.Etapa != etapaExigida)
            throw new ExecucaoNaoEncontrada();
        return e;
    }

    public async Task<PlanilhaPronta> Planilha(int execucaoId, string etapaDaRota, string? etapaExigida, string qual,
        string? modelos, string? classificacoes, string formato, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, etapaExigida, usuario, cancelar);
        return await motor.GerarPlanilha(e.Id, etapaDaRota, qual, modelos, classificacoes, formato, cancelar);
    }
}
