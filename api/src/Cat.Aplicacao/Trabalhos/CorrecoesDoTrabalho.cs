using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

/// <summary>Uma correção como a tela a lê: com quem fez, quando e o antes.</summary>
public sealed record CorrecaoGravada(
    int Id, string Campo, string Rotulo, string Onde, string Cnpj, string Codigo, string Documento,
    int? NumeroItem, string Valor, string ValorAnterior, string Motivo, string Situacao,
    string Autor, DateTimeOffset CriadaEm, string Frase);

public interface IRepositorioDeCorrecoes
{
    Task<IReadOnlyList<CorrecaoGravada>> Listar(int projetoId, bool somenteAtivas, CancellationToken cancelar);

    /// <summary>
    /// Grava as correções do trabalho — o mesmo alvo e campo é substituído, não
    /// duplicado — e o evento que registra o antes e o depois, numa transação.
    /// </summary>
    Task<int> Gravar(int projetoId, IReadOnlyList<CorrecaoDoTrabalho> correcoes, string texto, object dados,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar);

    /// <summary>Desfaz uma correção, sem apagá-la, e registra no histórico. Nulo se ela não é do trabalho.</summary>
    Task<CorrecaoGravada?> Desfazer(int projetoId, int correcaoId, string texto, object dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar);
}

/// <summary>
/// As correções à mão de um trabalho: o que uma pessoa mudou no que o sistema
/// calculou, com motivo escrito e trilha de auditoria.
///
/// A etapa do razão lê as ativas e aplica; desfazer é tirar a correção, não
/// reescrever o dado — e a linha desfeita continua no banco, para o histórico
/// continuar contando o que foi feito e por quem.
/// </summary>
public sealed class CorrecoesDoTrabalho(
    IRepositorioDeTrabalhos trabalhos,
    IRepositorioDeCorrecoes correcoes,
    TimeProvider relogio,
    ILogger<CorrecoesDoTrabalho> log)
{
    public async Task<IReadOnlyList<CorrecaoGravada>> Listar(int projetoId, bool somenteAtivas, Usuario por,
        CancellationToken cancelar)
    {
        var projeto = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        return await correcoes.Listar(projetoId, somenteAtivas, cancelar);
    }

    public async Task<int> Gravar(int projetoId, IReadOnlyList<CorrecaoDoTrabalho> pedidas, Usuario por,
        CancellationToken cancelar)
    {
        var projeto = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        if (pedidas.Count == 0)
            throw new DadoInvalido("Nenhuma correção no pedido.");
        if (pedidas.Count > Correcao.CorrecoesPorPedido)
            throw new DadoInvalido($"No máximo {Correcao.CorrecoesPorPedido} correções por pedido.");

        var texto = pedidas.Count == 1
            ? pedidas[0].Frase
            : $"{pedidas.Count} correções à mão: " + string.Join("; ", pedidas.Take(3).Select(c => c.Frase))
              + (pedidas.Count > 3 ? "…" : "");
        var dados = new Dictionary<string, object?>
        {
            ["correcoes"] = pedidas.Count,
            ["por_campo"] = pedidas.GroupBy(c => c.Campo).ToDictionary(g => g.Key, g => g.Count()),
            // o antes e o depois de cada uma, que é o que a auditoria lê
            ["mudancas"] = pedidas.Take(Correcao.CorrecoesPorPedido).Select(c => new Dictionary<string, object?>
            {
                ["campo"] = c.Campo, ["rotulo"] = Correcao.Rotulo(c.Campo), ["onde"] = c.Onde,
                ["cnpj"] = c.Cnpj, ["codigo"] = c.Codigo, ["documento"] = c.Documento,
                ["numero_item"] = c.NumeroItem, ["de"] = c.ValorAnterior, ["para"] = c.Valor,
                ["motivo"] = c.Motivo, ["frase"] = c.Frase,
            }).ToList(),
        };
        var gravadas = await correcoes.Gravar(projetoId, pedidas, texto, dados, por, relogio.GetUtcNow(), cancelar);
        log.LogInformation("correções gravadas {Correcoes} no trabalho {ProjetoId}", gravadas, projetoId);
        return gravadas;
    }

    public async Task<CorrecaoGravada> Desfazer(int projetoId, int correcaoId, Usuario por, CancellationToken cancelar)
    {
        var projeto = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        var alvo = await correcoes.Listar(projetoId, somenteAtivas: false, cancelar);
        var atual = alvo.FirstOrDefault(c => c.Id == correcaoId)
                    ?? throw new DadoInvalido("Correção não encontrada neste trabalho.");
        if (atual.Situacao != "ativa")
            throw new DadoInvalido("Essa correção já foi desfeita.");
        // desfazer devolve o valor anterior: a frase do histórico vai ao contrário
        var texto = $"{atual.Rotulo} ({atual.Onde}) volta ao que era: {atual.Valor} → " +
                    $"{(atual.ValorAnterior.Length == 0 ? "o que o sistema calcular" : atual.ValorAnterior)}";
        var dados = new Dictionary<string, object?>
        {
            ["correcao_id"] = correcaoId, ["campo"] = atual.Campo, ["onde"] = atual.Onde,
            ["de"] = atual.Valor, ["para"] = atual.ValorAnterior, ["motivo"] = atual.Motivo,
            ["frase"] = texto,
        };
        var desfeita = await correcoes.Desfazer(projetoId, correcaoId, texto, dados, por, relogio.GetUtcNow(), cancelar)
                       ?? throw new DadoInvalido("Correção não encontrada neste trabalho.");
        log.LogInformation("correção desfeita {CorrecaoId} no trabalho {ProjetoId}", correcaoId, projetoId);
        return desfeita;
    }
}
