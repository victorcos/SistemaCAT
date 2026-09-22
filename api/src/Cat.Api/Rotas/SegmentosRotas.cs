using Cat.Api.Infra;
using Cat.Dominio.Acesso;

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
