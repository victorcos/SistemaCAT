using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

/// <summary>
/// Todo acesso a dado fiscal passa por aqui, como o <c>exigir_empresa</c> do
/// Python. Nunca filtrar no front.
/// </summary>
public static class Escopo
{
    public static void Exigir(Usuario usuario, int empresaId, ILogger log)
    {
        if (usuario.AcessaPorExcecao(empresaId))
        {
            // o dev passou sem alocação: vai para o log como exceção, para não
            // virar rotina invisível no meio do tráfego normal
            log.Aviso("acesso a empresa por exceção de dev",
                new { usuario_id = usuario.Id, usuario = usuario.NomeDeUsuario, empresa = empresaId,
                      papel = usuario.Papel.Valor(), sem_alocacao = true });
            return;
        }
        if (usuario.EnxergaEmpresa(empresaId))
            return;
        log.Aviso("acesso negado a empresa fora do escopo",
            new { usuario_id = usuario.Id, empresa_pedida = empresaId, empresas_do_usuario = usuario.Empresas });
        throw new SemAcessoAEmpresa();
    }
}
