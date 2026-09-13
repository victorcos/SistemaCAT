using System.Text.Json;
using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

public sealed record EventoLido(
    int Id, string Tipo, string Texto, JsonElement? Dados, string Autor, int? AutorId, DateTimeOffset Quando);

public sealed record Candidato(int Id, string NomeExibicao, string Usuario, string Papel, string Cargo, bool Alcanca);

public sealed record SucessaoFeita(int ResponsavelId, string Responsavel);

public interface IRepositorioDeHistorico
{
    /// <summary>Do mais recente para o mais antigo, com um a mais para saber se há próxima página.</summary>
    Task<IReadOnlyList<EventoLido>> Listar(int projetoId, int? antesDe, int quantos, bool soComentarios,
        CancellationToken cancelar);

    Task<EventoLido> Comentar(int projetoId, string texto, Usuario por, DateTimeOffset agora, CancellationToken cancelar);

    /// <summary>O status novo e o evento que o descreve, numa transação: um não existe sem o outro.</summary>
    Task MudarStatus(int projetoId, string novo, string motivo, object dados, Usuario por, DateTimeOffset agora,
        CancellationToken cancelar);

    /// <summary>
    /// Ativos, com papel que escreve, por nome de exibição — e se já alcançam a
    /// empresa por uma alocação <b>vigente</b> ou pelo papel.
    /// </summary>
    Task<IReadOnlyList<Candidato>> Candidatos(int empresaId, CancellationToken cancelar);

    /// <summary>Responsável novo, alocação (se precisar) e o evento, numa transação.</summary>
    Task Suceder(int projetoId, int empresaId, int novoId, bool alocar, string motivo, object dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar);
}

public sealed class NaoPodeSuceder() : RecusaDeRegra(
    "Só gestor passa um trabalho para outra pessoa. Quem executa pede " +
    "ao gestor — a carteira é decisão de quem coordena.");

public sealed class SucessorInvalido(string motivo) : RecusaDeRegra(motivo);

public sealed class StatusDesconhecido(string valor) : RecusaDeRegra(
    $"Status desconhecido: {valor}. Use um de: {string.Join(", ", StatusDoProjeto.Todos.Select(s => s.Valor))}.");

/// <summary>
/// A história do trabalho que a tela usa: ler, comentar, mudar status e passar
/// adiante. Portado de <c>historico_do_projeto.py</c>.
///
/// Registrar evento de lote e de etapa fica no motor, que é quem faz lote e
/// etapa. Os dois lados escrevem na mesma tabela, no mesmo formato.
/// </summary>
public sealed class HistoricoDoProjeto(
    IRepositorioDeTrabalhos trabalhos,
    IRepositorioDeHistorico historico,
    IRepositorioDeUsuario usuarios,
    TimeProvider relogio,
    ILogger<HistoricoDoProjeto> log)
{
    // quantos a tela traz por vez: ninguém rola mil linhas atrás do que aconteceu ontem
    public const int PorPagina = 50;
    public const int MaximoPorPagina = 200;

    /// <summary>
    /// Quem vê o trabalho vê o histórico inteiro. O escopo por empresa já
    /// limita o que cada um alcança; dentro de um trabalho não há segredo.
    /// </summary>
    public async Task<ProjetoLido> Projeto(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var p = await trabalhos.BuscarProjeto(projetoId, cancelar)
                ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
        Escopo.Exigir(usuario, p.EmpresaId, log);
        return p;
    }

    /// <summary>
    /// Paginado por <paramref name="antesDe"/> (o id do último que a tela já tem),
    /// sem deslocamento: com evento entrando enquanto se lê, deslocamento repete e pula linha.
    /// </summary>
    public async Task<(IReadOnlyList<EventoLido> Eventos, bool TemMais)> Listar(int projetoId, Usuario usuario,
        int? antesDe, int quantos, bool soComentarios, CancellationToken cancelar)
    {
        await Projeto(projetoId, usuario, cancelar);
        quantos = Math.Clamp(quantos, 1, MaximoPorPagina);
        var linhas = await historico.Listar(projetoId, antesDe, quantos + 1, soComentarios, cancelar);
        return (linhas.Take(quantos).ToList(), linhas.Count > quantos);
    }

    public async Task<EventoLido> Comentar(int projetoId, string texto, Usuario por, CancellationToken cancelar)
    {
        await Projeto(projetoId, por, cancelar);
        var limpo = Historico.ValidarComentario(texto);
        var evento = await historico.Comentar(projetoId, limpo, por, relogio.GetUtcNow(), cancelar);
        log.Info("comentário no trabalho",
            new { projeto_id = projetoId, por_usuario_id = por.Id, caracteres = limpo.Length });
        return evento;
    }

    public async Task<DefinicaoDeStatus> MudarStatus(int projetoId, string valorNovo, string motivo, Usuario por,
        CancellationToken cancelar)
    {
        var p = await Projeto(projetoId, por, cancelar);
        var novo = StatusDoProjeto.Buscar(valorNovo) ?? throw new StatusDesconhecido(valorNovo);
        var atual = StatusDoProjeto.DoBanco(p.Status);
        Historico.ValidarMudancaDeStatus(atual, novo, motivo);

        await historico.MudarStatus(projetoId, novo.Valor, motivo.Trim(),
            new Dictionary<string, object> { ["de"] = atual.Valor, ["para"] = novo.Valor, ["frase"] = Historico.FraseDeStatus(atual, novo) },
            por, relogio.GetUtcNow(), cancelar);
        log.Aviso("status do trabalho alterado",
            new { projeto_id = projetoId, de = atual.Valor, para = novo.Valor, por_usuario_id = por.Id,
                  motivo = motivo.Trim()[..Math.Min(200, motivo.Trim().Length)] });
        return novo;
    }

    /// <summary>
    /// Quem pode receber ESTE trabalho: conta ativa e papel que escreve. Quem
    /// ainda não alcança a empresa vem marcado — acesso não é condição, é
    /// consequência: a transferência o concede.
    /// </summary>
    public async Task<IReadOnlyList<Candidato>> Sucessores(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var p = await Projeto(projetoId, usuario, cancelar);
        return await historico.Candidatos(p.EmpresaId, cancelar);
    }

    /// <summary>
    /// Passa o trabalho para outra pessoa. Só gestor e dev. Validar o sucessor
    /// não é burocracia: passar para conta desativada é como o trabalho fica sem
    /// dono sem ninguém perceber.
    /// </summary>
    public async Task<SucessaoFeita> Suceder(int projetoId, int novoId, string motivo, Usuario por,
        CancellationToken cancelar)
    {
        var p = await Projeto(projetoId, por, cancelar);
        if (!por.Papel.AdministraUsuarios())
            throw new NaoPodeSuceder();

        var novo = await usuarios.BuscarPorId(novoId, cancelar) ?? throw new SucessorInvalido("A pessoa escolhida não existe.");
        if (!novo.Ativo)
            throw new SucessorInvalido(
                $"{novo.NomeExibicao} está com o acesso desativado. Reative antes " +
                "de passar o trabalho, ou escolha outra pessoa.");
        if (p.ResponsavelId == novo.Id)
            throw new SucessorInvalido($"{novo.NomeExibicao} já responde por este trabalho.");

        // Quem recebe precisa enxergar a empresa. É o significado de passar o
        // trabalho: junto vai o acesso, e o histórico registra que foi assim.
        // Só alocação VIGENTE conta: o Python contava também a encerrada, e quem
        // teve o acesso retirado recebia um trabalho que não enxergava.
        var alocar = !novo.EnxergaEmpresa(p.EmpresaId);

        var anterior = p.Responsavel;
        await historico.Suceder(projetoId, p.EmpresaId, novo.Id, alocar, motivo.Trim(),
            new Dictionary<string, object?>
            {
                ["de"] = anterior, ["para"] = novo.NomeExibicao, ["de_id"] = p.ResponsavelId, ["para_id"] = novo.Id,
                ["alocou_na_empresa"] = alocar, ["frase"] = Historico.FraseDeSucessao(anterior, novo.NomeExibicao),
            },
            por, relogio.GetUtcNow(), cancelar);

        if (alocar)
            log.Aviso("acesso à empresa concedido pela sucessão",
                new { usuario_id = novo.Id, usuario = novo.NomeDeUsuario, empresa = p.EmpresaId, por_usuario_id = por.Id });
        log.Aviso("trabalho passado para outra pessoa",
            new { projeto_id = projetoId, de = anterior, para = novo.NomeExibicao, por_usuario_id = por.Id,
                  alocou_na_empresa = alocar });
        return new SucessaoFeita(novo.Id, novo.NomeExibicao);
    }
}
