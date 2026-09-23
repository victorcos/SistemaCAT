using System.Globalization;
using System.Text.Json.Nodes;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Dominio.Acesso;
using Cat.Dominio.Lote;
using Cat.Dominio.Projeto;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

public sealed record ArquivoInspecionado(
    string Nome, string Caminho, long Tamanho, string Tipo, string? Cnpj, DateOnly? Competencia, string Uf,
    string Detalhe, string Motivo, bool Retificadora, string? HashConteudo, bool JaNoTrabalho,
    string? TipoNoTrabalho = null,
    // quem decide é o motor, que já sabe o módulo do trabalho e o tipo do arquivo
    bool Alimenta = false)
{

    /// <summary>
    /// Já está no trabalho com outro tipo: a classificação mudou desde a importação
    /// (o zip que virou <c>xml_compactado</c> e o evento que virou <c>xml_cancelamento</c> na v0.54).
    /// </summary>
    public bool Reclassificado => JaNoTrabalho && TipoNoTrabalho is not null && TipoNoTrabalho != Tipo;
}

/// <summary>O que o motor leu da pasta. Os avisos vêm prontos: dependem do que só a leitura sabe.</summary>
public sealed record LoteInspecionado(
    string Pasta, IReadOnlyList<ArquivoInspecionado> Arquivos, int DeOutraEmpresa, int Copias, bool Serve,
    IReadOnlyList<DateOnly> Competencias, IReadOnlyList<string> Cnpjs, IReadOnlyList<string> Avisos,
    // o módulo do trabalho: é contra ele que "serve" e "alimenta" foram medidos
    string Modulo = Segmentos.Icms);

public sealed record LoteLido(
    int Id, int ProjetoId, string Pasta, int TotalArquivos, int ArquivosUteis, long BytesTotais,
    DateOnly? CompetenciaIni, DateOnly? CompetenciaFim, string? Observacao, DateTimeOffset CriadoEm,
    IReadOnlyList<(string Tipo, int Quantidade)> Contagens,
    // o módulo do trabalho dono do lote: decide o que conta como útil na tela
    string Modulo = Segmentos.Icms);

public sealed record LoteRemovido(string Pasta, int Arquivos, int ConferenciasInvalidadas);

/// <summary>O que o registro fez: o lote criado ou, se nada era novo, o lote onde mais arquivos mudaram de tipo.</summary>
public sealed record LoteRegistrado(LoteLido Lote, bool Criado, int Reclassificados);

/// <param name="Lotes">os lotes com arquivo reclassificado, o de mais arquivos primeiro</param>
public sealed record Reclassificacao(int Arquivos, IReadOnlyList<int> Lotes);

public interface IRepositorioDeLotes
{
    /// <summary>Mais recentes primeiro, com a contagem por tipo de cada um.</summary>
    Task<IReadOnlyList<LoteLido>> Listar(int projetoId, CancellationToken cancelar);

    /// <summary>O lote e seus arquivos, numa transação.</summary>
    Task<LoteLido> Criar(int projetoId, string pasta, IReadOnlyList<ArquivoInspecionado> arquivos, string? observacao,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar);

    Task<int?> ProjetoDoLote(int loteId, CancellationToken cancelar);

    /// <summary>
    /// Regrava tipo, CNPJ, competência, UF, detalhe e finalidade dos arquivos que já estão no
    /// trabalho, pelo caminho, e refaz a contagem do que a CAT lê e o período de cada lote tocado.
    /// </summary>
    Task<Reclassificacao> Reclassificar(int projetoId, IReadOnlyList<ArquivoInspecionado> arquivos, string modulo,
        CancellationToken cancelar);

    /// <summary>Tira os arquivos e o lote. Os arquivos em disco não são tocados.</summary>
    Task<LoteRemovido> Remover(int loteId, CancellationToken cancelar);
}

public sealed class MotorRecusou(int status, string detalhe) : Exception(detalhe)
{
    public int Status { get; } = status;
}

public sealed class SoCopias(int quantas) : RecusaDeRegra(
    $"Os {quantas} arquivo(s) desta pasta são cópias exatas de arquivos que já estão neste trabalho. " +
    "Nada novo para importar.");

/// <summary>
/// Pasta que não traz nada do que ESTE trabalho lê. Não existe pasta inútil no
/// absoluto: uma pasta de EFD-Contribuições não serve à CAT 42 e é a base do
/// trabalho de PIS/COFINS.
/// </summary>
public sealed class NadaParaOTrabalho(string modulo) : RecusaDeRegra(
    $"Nenhum arquivo desta pasta alimenta o trabalho de {Segmentos.RotuloDoModulo(modulo)}. " +
    Segmentos.FaltaNoLote(modulo));

public sealed class TudoJaNoTrabalho() : RecusaDeRegra("Todos os arquivos desta pasta já estão neste trabalho.");

public sealed class LoteNaoEncontrado() : RecusaDeRegra("Lote não encontrado neste trabalho.");

/// <summary>
/// Lote de arquivos: a base de trabalho de um projeto que já existe, portado de
/// <c>lote_router.py</c>. Dois passos, e o primeiro não grava nada: inspecionar
/// a pasta e mostrar o que há, e só então registrar.
///
/// Ler a pasta é do motor. Aqui fica quem pode, as regras de registrar e o banco.
/// </summary>
public sealed class Lotes(
    IRepositorioDeTrabalhos trabalhos,
    IRepositorioDeLotes lotes,
    IMotor motor,
    TimeProvider relogio,
    ILogger<Lotes> log)
{
    private async Task Projeto(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var p = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
        Escopo.Exigir(usuario, p.EmpresaId, log);
    }

    public async Task<LoteInspecionado> Inspecionar(int projetoId, string pasta, Usuario usuario, CancellationToken cancelar)
    {
        await Projeto(projetoId, usuario, cancelar);
        return await motor.InspecionarLote(projetoId, pasta, cancelar);
    }

    public async Task<LoteRegistrado> Registrar(int projetoId, string pasta, string? observacao, Usuario por,
        CancellationToken cancelar)
    {
        await Projeto(projetoId, por, cancelar);
        // inspeciona de novo, e não confia no que a tela mostrou: a pasta pode
        // ter mudado entre conferir e confirmar
        var inspecao = await motor.InspecionarLote(projetoId, pasta, cancelar);

        // a mensagem certa antes da genérica: uma pasta só de cópias não é uma
        // pasta "sem nada para a CAT" — é uma pasta que já está no trabalho
        if (inspecao.Arquivos.Count == 0 && inspecao.Copias > 0)
            throw new SoCopias(inspecao.Copias);
        if (!inspecao.Serve)
            throw new NadaParaOTrabalho(inspecao.Modulo);
        // arquivo que já está no trabalho não entra de novo: o mesmo SPED
        // contado duas vezes dobraria movimento na apuração. Mas, se a
        // classificação de hoje diz outro tipo, ele é atualizado onde está
        var novos = inspecao.Arquivos.Where(a => !a.JaNoTrabalho).ToList();
        var mudaram = inspecao.Arquivos.Where(a => a.Reclassificado).ToList();
        if (novos.Count == 0 && mudaram.Count == 0)
            throw new TudoJaNoTrabalho();

        var agora = relogio.GetUtcNow();
        Reclassificacao? reclassificacao = null;
        if (mudaram.Count > 0)
            reclassificacao = await ReclassificarArquivos(projetoId, inspecao.Pasta, mudaram, inspecao.Modulo,
                por, agora, cancelar);
        if (novos.Count == 0)
        {
            var principal = (await lotes.Listar(projetoId, cancelar)).First(l => l.Id == reclassificacao!.Lotes[0]);
            return new LoteRegistrado(principal, Criado: false, reclassificacao!.Arquivos);
        }

        var lote = await lotes.Criar(projetoId, inspecao.Pasta, novos, observacao, por, agora, cancelar);
        var repetidos = inspecao.Arquivos.Count - novos.Count;
        await Registrar(projetoId, TipoDeEvento.LoteImportado,
            $"{novos.Count.ToString("#,0", CultureInfo.GetCultureInfo("pt-BR"))} arquivo(s) de {lote.Pasta}",
            new Dictionary<string, object?>
            {
                ["lote_id"] = lote.Id, ["pasta"] = lote.Pasta, ["arquivos"] = lote.TotalArquivos,
                ["uteis"] = lote.ArquivosUteis, ["bytes"] = lote.BytesTotais, ["repetidos_ignorados"] = repetidos,
            }, por, agora, cancelar);
        log.Info("lote registrado",
            new { lote_id = lote.Id, projeto_id = projetoId, arquivos = lote.TotalArquivos, uteis = lote.ArquivosUteis,
                  bytes = lote.BytesTotais, repetidos_ignorados = repetidos });
        return new LoteRegistrado(lote, Criado: true, reclassificacao?.Arquivos ?? 0);
    }

    private async Task<Reclassificacao> ReclassificarArquivos(int projetoId, string pasta,
        IReadOnlyList<ArquivoInspecionado> mudaram, string modulo, Usuario por, DateTimeOffset agora,
        CancellationToken cancelar)
    {
        var feita = await lotes.Reclassificar(projetoId, mudaram, modulo, cancelar);
        var trocas = mudaram.GroupBy(a => (De: a.TipoNoTrabalho!, Para: a.Tipo))
            .OrderByDescending(g => g.Count())
            .Select(g => new Dictionary<string, object?>
            {
                ["de"] = g.Key.De, ["para"] = g.Key.Para, ["arquivos"] = g.Count(),
            }).ToList();
        await Registrar(projetoId, TipoDeEvento.LoteReclassificado,
            $"{feita.Arquivos.ToString("#,0", CultureInfo.GetCultureInfo("pt-BR"))} arquivo(s) de {pasta}",
            new Dictionary<string, object?>
            {
                ["pasta"] = pasta, ["arquivos"] = feita.Arquivos, ["lotes"] = feita.Lotes,
                ["uteis"] = mudaram.Count(a => a.Alimenta), ["trocas"] = trocas,
            }, por, agora, cancelar);
        log.Info("arquivos reclassificados no trabalho",
            new { projeto_id = projetoId, pasta, arquivos = feita.Arquivos, lotes = feita.Lotes,
                  trocas = string.Join("; ", trocas.Select(t => $"{t["de"]} -> {t["para"]}: {t["arquivos"]}")) });
        return feita;
    }

    public async Task<IReadOnlyList<LoteLido>> Listar(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        await Projeto(projetoId, usuario, cancelar);
        return await lotes.Listar(projetoId, cancelar);
    }

    /// <summary>
    /// Tira um lote do trabalho. Não pede senha: desfaz uma importação, não o
    /// trabalho. Toda conferência já feita olhou este lote, e a resposta diz quantas.
    /// </summary>
    public async Task<LoteRemovido> Remover(int projetoId, int loteId, Usuario por, CancellationToken cancelar)
    {
        await Projeto(projetoId, por, cancelar);
        if (await lotes.ProjetoDoLote(loteId, cancelar) != projetoId)
            throw new LoteNaoEncontrado();

        var removido = await lotes.Remover(loteId, cancelar);
        await Registrar(projetoId, TipoDeEvento.LoteRemovido, removido.Pasta,
            new Dictionary<string, object?>
            {
                ["lote_id"] = loteId, ["pasta"] = removido.Pasta, ["arquivos"] = removido.Arquivos,
                ["conferencias_invalidadas"] = removido.ConferenciasInvalidadas,
            }, por, relogio.GetUtcNow(), cancelar);
        log.Aviso("lote removido do trabalho",
            new { lote_id = loteId, projeto_id = projetoId, pasta = removido.Pasta, arquivos = removido.Arquivos,
                  conferencias_afetadas = removido.ConferenciasInvalidadas, por_usuario_id = por.Id,
                  por_usuario = por.NomeDeUsuario });
        return removido;
    }

    /// <summary>
    /// De quem é a remessa enviada. O motor lê o arquivo; se a empresa já está
    /// cadastrada, quem diz é o banco daqui.
    /// </summary>
    public async Task<JsonObject> AnalisarRemessa(Stream corpo, string tipoDoConteudo, long? tamanho,
        CancellationToken cancelar)
    {
        var analise = await motor.AnalisarRemessa(corpo, tipoDoConteudo, tamanho, cancelar);
        var raiz = analise["cnpj_raiz"]?.GetValue<string>() ?? "";
        var empresa = (await trabalhos.ListarEmpresas(cancelar)).FirstOrDefault(e => e.CnpjRaiz == raiz);

        // a ordem de campos da resposta do FastAPI: os dois do banco antes da matriz
        var saida = new JsonObject();
        foreach (var (chave, valor) in analise.ToList())
        {
            if (chave == "matriz")
            {
                saida["ja_cadastrada"] = empresa is not null;
                saida["empresa_id"] = empresa?.Id;
            }
            analise.Remove(chave);
            saida[chave] = valor;
        }
        return saida;
    }

    private async Task Registrar(int projetoId, string tipo, string texto, object dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar)
    {
        try
        {
            await trabalhos.RegistrarEvento(projetoId, tipo, texto, dados, por, agora, cancelar);
        }
        catch (Exception erro) when (erro is not OperationCanceledException)
        {
            // registrar evento nunca derruba a operação que o gerou
            log.Aviso("não deu para registrar o evento do projeto",
                new { projeto_id = projetoId, tipo, motivo = erro.Message });
        }
    }
}
