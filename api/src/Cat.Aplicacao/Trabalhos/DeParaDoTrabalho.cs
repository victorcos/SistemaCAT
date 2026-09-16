using System.Text.Json;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

public interface IRepositorioDeDePara
{
    /// <summary>
    /// Grava as decisões da empresa — a mesma origem no mesmo estabelecimento é
    /// atualizada, não duplicada — e o evento que as registra, numa transação.
    /// </summary>
    Task Decidir(int empresaId, int projetoId, IReadOnlyList<DecisaoDeDePara> decisoes, string texto, object dados,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar);
}

/// <summary>
/// O de-para de códigos de um trabalho: as propostas vêm do motor, que lê a
/// movimentação; as decisões ficam no banco, por empresa, gravadas aqui.
/// </summary>
public sealed class DeParaDoTrabalho(
    IRepositorioDeTrabalhos trabalhos,
    IRepositorioDeDePara depara,
    IMotor motor,
    TimeProvider relogio,
    ILogger<DeParaDoTrabalho> log)
{
    public async Task<JsonElement> Listar(int projetoId, Usuario por, CancellationToken cancelar)
    {
        var projeto = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        return await motor.CandidatosDeDePara(projetoId, cancelar);
    }

    public async Task<int> Decidir(int projetoId, IReadOnlyList<DecisaoDeDePara> decisoes, Usuario por,
        CancellationToken cancelar)
    {
        var projeto = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        if (decisoes.Count == 0)
            throw new DadoInvalido("Nenhuma decisão no pedido.");
        if (decisoes.Count > DePara.DecisoesPorPedido)
            throw new DadoInvalido($"No máximo {DePara.DecisoesPorPedido} decisões por pedido.");
        var repetidas = decisoes.GroupBy(d => (d.Cnpj, d.Origem)).FirstOrDefault(g => g.Count() > 1);
        if (repetidas is not null)
            throw new DadoInvalido($"O código {repetidas.Key.Origem} aparece mais de uma vez no pedido.");

        var texto = DePara.Frase(decisoes);
        var dados = new Dictionary<string, object?>
        {
            ["parametro"] = "depara",
            ["aprovados"] = decisoes.Count(d => d.Situacao == DePara.Aprovado),
            ["recusados"] = decisoes.Count(d => d.Situacao == DePara.Recusado),
            ["pares"] = decisoes.Take(50).Select(d => new Dictionary<string, object?>
            {
                ["cnpj"] = d.Cnpj, ["origem"] = d.Origem, ["destino"] = d.Destino, ["fator"] = d.Fator,
                ["motivo"] = d.Motivo, ["situacao"] = d.Situacao,
            }).ToList(),
        };
        await depara.Decidir(projeto.EmpresaId, projetoId, decisoes, texto, dados, por, relogio.GetUtcNow(), cancelar);
        log.Aviso("de-para decidido", new
        {
            projeto_id = projetoId, empresa_id = projeto.EmpresaId, por_usuario_id = por.Id,
            aprovados = dados["aprovados"], recusados = dados["recusados"],
        });
        return decisoes.Count;
    }
}
