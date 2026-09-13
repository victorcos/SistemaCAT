using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Acesso;

public sealed class NaoPodeAlocar() : RecusaDeRegra(
    "Só gestor define a quais empresas alguém tem acesso. Quem executa " +
    "pede ao gestor — o escopo é decisão de quem coordena.");

public sealed class NaoPodeTirarDeSi() : RecusaDeRegra(
    "Você não pode tirar o seu próprio acesso a uma empresa. Peça a " +
    "outro gestor — evita alguém se trancar para fora por engano.");

public sealed class EmpresaInexistente(IEnumerable<int> ids)
    : RecusaDeRegra("Empresa não encontrada: " + string.Join(", ", ids.Order()));

public sealed record AcessoAEmpresa(int EmpresaId, string RazaoSocial, string? Uf, bool TemAcesso, DateTimeOffset? Desde);

public sealed record OQueMudou(IReadOnlyList<string> Concedidas, IReadOnlyList<string> Encerradas)
{
    public bool Mudou => Concedidas.Count > 0 || Encerradas.Count > 0;
}

/// <summary>
/// Quem trabalha em qual empresa, portado de <c>alocar_em_empresas.py</c>.
///
/// O escopo de visibilidade nasce daqui: as empresas de um usuário são as
/// alocações <b>vigentes</b>. Tirar acesso não apaga a linha, preenche o fim —
/// é o que permite responder, meses depois, quem tinha acesso a um dado em
/// determinado mês. Alocar de novo cria outra linha, e o histórico fica com as
/// duas passagens.
/// </summary>
public sealed class AcessoAEmpresas(
    IRepositorioDeUsuario usuarios,
    IRepositorioDeAcesso acessos,
    TimeProvider relogio,
    ILogger<AcessoAEmpresas> log)
{
    /// <summary>
    /// Todas as empresas, marcando quais esta pessoa alcança. Todas de
    /// propósito: a tela é de conceder e tirar, e mostrar só o que já tem
    /// deixaria o gesto de conceder sem alvo.
    /// </summary>
    public async Task<IReadOnlyList<AcessoAEmpresa>> Listar(int usuarioId, CancellationToken cancelar)
    {
        _ = await usuarios.BuscarPorId(usuarioId, cancelar) ?? throw new UsuarioNaoEncontrado();
        var desde = await acessos.Vigentes(usuarioId, cancelar);
        return (await acessos.ListarEmpresas(cancelar))
            .Select(e => new AcessoAEmpresa(e.Id, e.RazaoSocial, e.Uf, desde.ContainsKey(e.Id),
                desde.TryGetValue(e.Id, out var inicio) ? inicio : null))
            .ToList();
    }

    /// <summary>Faz o acesso da pessoa ser exatamente este conjunto de empresas.</summary>
    public async Task<OQueMudou> Definir(int usuarioId, IReadOnlySet<int> empresas, Usuario por,
        CancellationToken cancelar)
    {
        if (!por.Papel.AdministraUsuarios())
            throw new NaoPodeAlocar();
        var alvo = await usuarios.BuscarPorId(usuarioId, cancelar) ?? throw new UsuarioNaoEncontrado();

        var todas = await acessos.ListarEmpresas(cancelar);
        var nomes = todas.ToDictionary(e => e.Id, e => e.RazaoSocial);
        var inexistentes = empresas.Where(id => !nomes.ContainsKey(id)).ToList();
        if (inexistentes.Count > 0)
            throw new EmpresaInexistente(inexistentes);

        var atuais = (await acessos.Vigentes(usuarioId, cancelar)).Keys.ToHashSet();
        var conceder = empresas.Except(atuais).Order().ToList();
        var encerrar = atuais.Except(empresas).Order().ToList();

        if (encerrar.Count > 0 && alvo.Id == por.Id)
            throw new NaoPodeTirarDeSi();

        var mudou = new OQueMudou(
            conceder.Select(id => nomes[id]).ToList(),
            encerrar.Select(id => nomes.GetValueOrDefault(id, id.ToString())).ToList());
        if (!mudou.Mudou)
            return mudou;

        await acessos.Aplicar(alvo.Id, conceder, encerrar, por, relogio.GetUtcNow(), cancelar);
        log.Aviso("acesso a empresas alterado",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, concedidas = mudou.Concedidas,
                  encerradas = mudou.Encerradas, por_usuario_id = por.Id });
        return mudou;
    }
}
