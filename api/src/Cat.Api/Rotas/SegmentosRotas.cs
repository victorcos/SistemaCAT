using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Api.Rotas;

/// <summary>
/// O catálogo de segmentos tributários e o que cada pessoa enxerga deles.
///
/// A tela inicial é montada a partir daqui: os cards do primeiro nível são os
/// segmentos que a pessoa pode ver, e os do segundo são os módulos de um deles.
/// Quem decide é o domínio (<see cref="Segmentos"/>), não a tela — assim a lista
/// não precisa ser repetida em TypeScript e não há como as duas divergirem.
/// </summary>
public static class SegmentosRotas
{
    public sealed record ModuloDto(string Chave, string Rotulo, string Descricao);

    public sealed record SegmentoDto(string Chave, string Rotulo, string Descricao,
        IReadOnlyList<ModuloDto> Modulos);

    /// <param name="Abertos">trabalhos que ainda andam — nem concluídos nem cancelados.</param>
    public sealed record ResumoDoModuloDto(string Modulo, int Abertos, int Total);

    public static void MapearSegmentos(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("segmentos");

        // só os que a pessoa enxerga: a tela nunca recebe o que não pode abrir
        api.MapGet("/segmentos", (HttpContext http) =>
                Results.Json(new Dictionary<string, object>
                {
                    ["segmentos"] = Segmentos.De(http.UsuarioAtual()).Select(Traduzir).ToList(),
                }))
            .ExigirUsuario();

        // quantos trabalhos há em cada módulo — os números dos cards do hub.
        //
        // Sai daqui, e não de uma contagem na tela, porque o recorte é o mesmo
        // da listagem: só as empresas que a pessoa enxerga. Contar no navegador
        // exigiria baixar a lista inteira para mostrar dois números.
        api.MapGet("/segmentos/resumo", async (HttpContext http, Trabalhos caso) =>
            {
                var meus = Segmentos.De(http.UsuarioAtual())
                    .SelectMany(s => s.Modulos)
                    .Select(m => m.Chave)
                    .ToHashSet();
                var projetos = await caso.ListarProjetos(http.UsuarioAtual(), http.RequestAborted);
                var porModulo = projetos
                    .Where(p => meus.Contains(p.Projeto.Modulo))
                    .GroupBy(p => p.Projeto.Modulo)
                    .ToDictionary(g => g.Key, g => (
                        Abertos: g.Count(p => p.Projeto.Status != StatusDoProjeto.Concluido
                                              && p.Projeto.Status != StatusDoProjeto.Cancelado),
                        Total: g.Count()));
                // módulo sem trabalho nenhum também sai, zerado: o card existe de
                // qualquer forma, e "0 trabalhos" é informação, ausência não é
                return Results.Json(new Dictionary<string, object>
                {
                    ["resumo"] = meus.OrderBy(m => m).Select(m => new ResumoDoModuloDto(
                        m,
                        porModulo.TryGetValue(m, out var c) ? c.Abertos : 0,
                        porModulo.TryGetValue(m, out var c2) ? c2.Total : 0)).ToList(),
                });
            })
            .ExigirUsuario();

        // o catálogo inteiro, para o gestor liberar segmento a quem está abaixo
        api.MapGet("/segmentos/todos", () =>
                Results.Json(new Dictionary<string, object>
                {
                    ["segmentos"] = Segmentos.Todos.Select(Traduzir).ToList(),
                }))
            .ExigirCapacidade(Capacidades.DefineSegmentos, "define_segmentos", "liberar segmentos");
    }

    private static SegmentoDto Traduzir(Segmento s) => new(
        s.Chave, s.Rotulo, s.Descricao,
        s.Modulos.Select(m => new ModuloDto(m.Chave, m.Rotulo, m.Descricao)).ToList());
}
