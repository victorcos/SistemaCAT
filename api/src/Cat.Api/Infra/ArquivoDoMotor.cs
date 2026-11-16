using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
using Cat.Infraestrutura.Configuracao;

namespace Cat.Api.Infra;

/// <summary>
/// Entrega o arquivo que o motor montou.
///
/// Fica aqui, e não na rota, porque mais de uma rota o serve e a regra tem um
/// lado de segurança: o caminho vem do motor, e a API **só** serve arquivo de
/// dentro da pasta de trabalho — nem se o motor pedir outro lugar da máquina.
/// Duplicar essa conferência por rota é como ela deixa de valer numa delas.
/// </summary>
public static class ArquivoDoMotor
{
    /// <summary>
    /// O arquivo sai direto do disco, em fluxo: um CSV de dezenas de milhões de
    /// linhas tem gigabytes.
    /// </summary>
    public static IResult Servir(PlanilhaPronta pronta, ConfigCat config, ILogger log)
    {
        var raiz = Path.GetFullPath(config.PastaDeTrabalho).TrimEnd(Path.DirectorySeparatorChar)
                   + Path.DirectorySeparatorChar;
        var caminho = Path.GetFullPath(pronta.Caminho);
        if (!caminho.StartsWith(raiz, StringComparison.OrdinalIgnoreCase) || !File.Exists(caminho))
        {
            log.Erro("motor devolveu arquivo fora da pasta de trabalho ou inexistente",
                new { caminho, raiz, existe = File.Exists(caminho) });
            return CorpoJson.Recusar("O arquivo não pôde ser entregue. Veja o log do servidor.",
                StatusCodes.Status502BadGateway);
        }
        return Results.File(caminho, pronta.Tipo, pronta.Nome, enableRangeProcessing: true);
    }
}
