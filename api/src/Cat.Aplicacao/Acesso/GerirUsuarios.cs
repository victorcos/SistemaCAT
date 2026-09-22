using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Acesso;

public sealed class UsuarioJaExiste(string campo) : RecusaDeRegra($"Já existe usuário com este {campo}.");

public sealed class UsuarioNaoEncontrado() : RecusaDeRegra("Usuário não encontrado.");

public sealed class SenhaAtualIncorreta() : RecusaDeRegra("A senha atual está incorreta.");

public sealed class SenhaRepetida() : RecusaDeRegra("A nova senha precisa ser diferente da atual.");

public sealed record UsuarioCriado(Usuario Usuario, string SenhaProvisoria);

/// <summary>
/// Gestão de usuários, portada de <c>gerir_usuarios.py</c>.
///
/// Cadastro e redefinição ficam com o gestor: o sistema roda na rede interna,
/// a base é fechada, e conceder acesso a dado fiscal de cliente precisa ser
/// ato deliberado. Não há autocadastro nem redefinição por e-mail. As
/// salvaguardas: mínimo de três gestores, ninguém rebaixa nem desativa a si
/// mesmo, e a senha de outra pessoa é sempre gerada pelo sistema.
/// </summary>
public sealed class GerirUsuarios(
    IRepositorioDeUsuario repositorio,
    IConferidorDeSenha senhas,
    TimeProvider relogio,
    ILogger<GerirUsuarios> log)
{
    public Task<IReadOnlyList<Usuario>> Listar(CancellationToken cancelar) => repositorio.Listar(cancelar);

    // ---------- cadastro ----------
    public async Task<UsuarioCriado> Criar(string nomeDeUsuario, string email, string nomeExibicao,
        Papel papel, Cargo cargo, Usuario criadoPor, CancellationToken cancelar)
    {
        nomeDeUsuario = PoliticaDeAcesso.ValidarNomeDeUsuario(nomeDeUsuario);
        email = PoliticaDeAcesso.ValidarEmail(email);
        nomeExibicao = PoliticaDeAcesso.ValidarNomeDeExibicao(nomeExibicao);

        if (await repositorio.BuscarPorNome(nomeDeUsuario, cancelar) is not null)
            throw new UsuarioJaExiste("nome de usuário");
        if (await repositorio.BuscarPorEmail(email, cancelar) is not null)
            throw new UsuarioJaExiste("e-mail");

        var senha = PoliticaDeAcesso.GerarSenhaProvisoria();
        var novo = await repositorio.Criar(
            new NovoUsuario(nomeDeUsuario, email, nomeExibicao, senhas.Gerar(senha), papel, cargo, SenhaProvisoria: true),
            cancelar);
        log.Info("usuário criado",
            new { usuario_id = novo.Id, usuario = novo.NomeDeUsuario, papel = papel.Valor(),
                  cargo = cargo.Valor(), por_usuario_id = criadoPor.Id });
        return new UsuarioCriado(novo, senha);
    }

    // ---------- senha ----------
    /// <summary>
    /// Gera senha provisória de uso único e devolve para o gestor entregar.
    /// Também desbloqueia: quem esqueceu a senha em geral se bloqueou tentando.
    /// </summary>
    public async Task<string> RedefinirSenha(int alvoId, Usuario por, CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        var senha = PoliticaDeAcesso.GerarSenhaProvisoria();
        await repositorio.DefinirSenha(alvo.Id, senhas.Gerar(senha), provisoria: true, cancelar);
        await repositorio.Desbloquear(alvo.Id, cancelar);
        log.Aviso("senha redefinida por gestor",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, por_usuario_id = por.Id, provisoria = true });
        return senha;
    }

    /// <summary>A pessoa troca a própria senha. Único caminho para sair da provisória.</summary>
    public async Task TrocarPropriaSenha(Usuario usuario, string senhaAtual, string senhaNova, CancellationToken cancelar)
    {
        var resumoAtual = await repositorio.ObterResumoDaSenha(usuario.Id, cancelar);
        if (!senhas.Conferir(senhaAtual, resumoAtual))
        {
            log.Aviso("troca de senha recusada, senha atual incorreta",
                new { usuario_id = usuario.Id, motivo = "senha_atual_incorreta" });
            throw new SenhaAtualIncorreta();
        }
        if (senhaAtual == senhaNova)
            throw new SenhaRepetida();

        PoliticaDeAcesso.ValidarSenha(senhaNova);
        await repositorio.DefinirSenha(usuario.Id, senhas.Gerar(senhaNova), provisoria: false, cancelar);
        log.Info("senha trocada pelo próprio usuário", new { usuario_id = usuario.Id });
    }

    // ---------- dados, papel e situação ----------
    /// <summary>
    /// Nome de exibição e e-mail. O nome de usuário não muda nunca: é a
    /// identidade nos logs e nas alocações.
    /// </summary>
    public async Task<Usuario> AlterarDados(int alvoId, string nomeExibicao, string email, Usuario por,
        CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        email = PoliticaDeAcesso.ValidarEmail(email);
        nomeExibicao = PoliticaDeAcesso.ValidarNomeDeExibicao(nomeExibicao);
        if (await repositorio.BuscarPorEmail(email, cancelar) is { } dono && dono.Id != alvo.Id)
            throw new UsuarioJaExiste("e-mail");

        await repositorio.DefinirDados(alvo.Id, nomeExibicao, email, cancelar);
        log.Info("dados alterados",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, email_anterior = alvo.Email,
                  email_novo = email, por_usuario_id = por.Id });
        return await Buscar(alvoId, cancelar);
    }

    public async Task<Usuario> AlterarCargo(int alvoId, Cargo cargo, Usuario por, CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        await repositorio.DefinirCargo(alvo.Id, cargo, cancelar);
        log.Info("cargo alterado",
            new { usuario_id = alvo.Id, cargo_anterior = alvo.Cargo.Valor(), cargo_novo = cargo.Valor(),
                  por_usuario_id = por.Id });
        return await Buscar(alvoId, cancelar);
    }

    /// <summary>
    /// Define em que assuntos a pessoa trabalha — a terceira dimensão de acesso,
    /// ao lado do papel e da alocação por empresa.
    ///
    /// Gestor e dev são recusados de propósito: eles enxergam todo segmento por
    /// papel, e gravar uma lista para eles guardaria um dado que mente sobre o
    /// acesso real. Quem quiser restringi-los muda o papel primeiro.
    /// </summary>
    public async Task<Usuario> DefinirSegmentos(int alvoId, IReadOnlyList<string> segmentos, Usuario por,
        CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        var limpos = Dominio.Acesso.Segmentos.Limpar(segmentos);
        if (alvo.Papel.EnxergaTodosOsSegmentos())
            throw new DadoInvalido(
                $"{alvo.NomeExibicao} é {alvo.Papel.Valor()} e já enxerga todos os segmentos. " +
                "Mude o papel antes, se a intenção é restringir.");
        await repositorio.DefinirSegmentos(alvo.Id, limpos, por.Id, relogio.GetUtcNow(), cancelar);
        log.Aviso("segmentos definidos",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario,
                  antes = string.Join(",", alvo.Segmentos), depois = string.Join(",", limpos),
                  por_usuario_id = por.Id });
        return await Buscar(alvoId, cancelar);
    }

    public async Task<Usuario> AlterarPapel(int alvoId, Papel papel, Usuario por, CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        if (alvo.Id == por.Id && papel != Papel.Gestor)
            throw new NaoPodeAlterarSiMesmo("rebaixar");
        // Só gestor ATIVO sai da conta. O Python descontava também o inativo e
        // recusava rebaixá-lo com exatamente três ativos — sem que a contagem
        // mudasse (DECISOES, 13/09/2026).
        if (alvo is { Papel: Papel.Gestor, Ativo: true } && papel != Papel.Gestor)
            await ChecarGestoresAposPerder(alvo, cancelar);

        await repositorio.DefinirPapel(alvo.Id, papel, cancelar);
        log.Aviso("papel alterado",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, papel_anterior = alvo.Papel.Valor(),
                  papel_novo = papel.Valor(), por_usuario_id = por.Id });
        return await Buscar(alvoId, cancelar);
    }

    public async Task<Usuario> DefinirSituacao(int alvoId, bool ativo, Usuario por, CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        if (alvo.Id == por.Id && !ativo)
            throw new NaoPodeAlterarSiMesmo("desativar");
        if (alvo is { Papel: Papel.Gestor, Ativo: true } && !ativo)
            await ChecarGestoresAposPerder(alvo, cancelar);

        await repositorio.DefinirSituacao(alvo.Id, ativo, cancelar);
        log.Aviso("situação de usuário alterada",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, ativo, por_usuario_id = por.Id });
        return await Buscar(alvoId, cancelar);
    }

    public async Task<Usuario> Desbloquear(int alvoId, Usuario por, CancellationToken cancelar)
    {
        var alvo = await Buscar(alvoId, cancelar);
        await repositorio.Desbloquear(alvo.Id, cancelar);
        log.Info("usuário desbloqueado por gestor",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, tentativas_antes = alvo.TentativasFalhas,
                  por_usuario_id = por.Id });
        return await Buscar(alvoId, cancelar);
    }

    // ---------- interno ----------
    private async Task<Usuario> Buscar(int alvoId, CancellationToken cancelar) =>
        await repositorio.BuscarPorId(alvoId, cancelar) ?? throw new UsuarioNaoEncontrado();

    /// <summary>Quantos gestores sobrariam se este deixasse de contar.</summary>
    private async Task ChecarGestoresAposPerder(Usuario alvo, CancellationToken cancelar)
    {
        var restantes = await repositorio.ContarGestoresAtivos(cancelar) - 1;
        try
        {
            PoliticaDeAcesso.GarantirMinimoDeGestores(restantes);
        }
        catch (UltimoGestor)
        {
            log.Aviso("alteração recusada para não deixar o sistema sem gestores",
                new { usuario_id = alvo.Id, gestores_restantes = restantes });
            throw;
        }
    }
}
