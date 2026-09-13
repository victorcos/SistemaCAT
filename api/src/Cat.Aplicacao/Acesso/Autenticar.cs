using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Acesso;

public sealed record Autenticado(string Token, int ExpiraEmSegundos, Usuario Usuario);

/// <summary>Caso de uso: autenticar. Orquestra domínio e portas, sem tocar em I/O.</summary>
public sealed class Autenticar(
    IRepositorioDeUsuario repositorio,
    IConferidorDeSenha senhas,
    IEmissorDeToken tokens,
    TimeProvider relogio,
    ILogger<Autenticar> log)
{
    public async Task<Autenticado> Executar(string? nomeInformado, string senha, CancellationToken cancelar)
    {
        var nome = (nomeInformado ?? "").Trim().ToLowerInvariant();
        var usuario = await repositorio.BuscarPorNome(nome, cancelar);

        if (usuario is null)
        {
            // não dizemos "usuário não existe": isso entrega quais contas existem
            log.Aviso("tentativa de login para usuário inexistente",
                new { usuario_informado = nome, motivo = "nao_encontrado" });
            throw new CredencialInvalida();
        }

        var agora = relogio.GetUtcNow();
        try
        {
            usuario.GarantirQuePodeEntrar(agora);
        }
        catch (UsuarioInativo)
        {
            log.Aviso("login recusado, usuário inativo",
                new { usuario_id = usuario.Id, usuario = usuario.NomeDeUsuario, motivo = "inativo" });
            throw;
        }
        catch (UsuarioBloqueado erro)
        {
            log.Aviso("login recusado, usuário bloqueado",
                new { usuario_id = usuario.Id, usuario = usuario.NomeDeUsuario, motivo = "bloqueado",
                      tentativas = erro.Tentativas });
            throw;
        }

        var resumoAtual = await repositorio.ObterResumoDaSenha(usuario.Id, cancelar);
        if (!senhas.Conferir(senha, resumoAtual))
        {
            usuario.RegistrarFalha(agora);
            await repositorio.SalvarTentativa(usuario, cancelar);
            log.Aviso("login recusado, senha incorreta",
                new { usuario_id = usuario.Id, usuario = usuario.NomeDeUsuario, motivo = "senha_incorreta",
                      tentativas_falhas = usuario.TentativasFalhas,
                      tentativas_restantes = usuario.TentativasRestantes });
            throw new CredencialInvalida();
        }

        usuario.RegistrarSucesso(agora);
        await repositorio.SalvarTentativa(usuario, cancelar);

        // Migração silenciosa: resumo em formato antigo ou com parâmetros
        // defasados é regravado agora, enquanto a senha em claro está em mãos.
        // É a única janela em que isso é possível.
        if (senhas.PrecisaRegravar(resumoAtual))
            await repositorio.RegravarResumoDaSenha(usuario.Id, senhas.Gerar(senha), cancelar);

        var (token, expira) = tokens.Emitir(usuario);
        log.Info("login concluído",
            new { usuario_id = usuario.Id, usuario = usuario.NomeDeUsuario, papel = usuario.Papel.Valor(),
                  empresas = usuario.Empresas, expira_em_s = expira });
        return new Autenticado(token, expira, usuario);
    }
}
