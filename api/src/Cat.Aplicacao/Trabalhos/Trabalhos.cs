using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Dominio.Comum;
using Cat.Dominio.Projeto;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

public sealed class SemAcessoAEmpresa() : RecusaDeRegra("Você não tem acesso a esta empresa.");

public sealed class RaizNaoConfere() : RecusaDeRegra("A raiz informada não é a do CNPJ da matriz.");

public sealed class EmpresaJaCadastrada(string raiz) : RecusaDeRegra($"A empresa de raiz {raiz} já está cadastrada.");

public sealed class EmpresaNaoEncontrada() : RecusaDeRegra("Empresa não encontrada.");

public sealed class FrenteDesconhecida() : RecusaDeRegra(
    $"Frente desconhecida. Use uma de: {string.Join(", ", Frentes.Todas.Select(f => f.Key))}.");

public sealed class CompetenciasInvertidas() : RecusaDeRegra("A competência final não pode ser anterior à inicial.");

public sealed class ProjetoRepetido() : RecusaDeRegra("Já existe um projeto com este nome nesta frente para esta empresa.");

public sealed class ProjetoNaoEncontrado(string mensagem = "Projeto não encontrado.") : RecusaDeRegra(mensagem);

public sealed class SenhaNaoConfere() : RecusaDeRegra("Senha incorreta. O trabalho não foi apagado.");

public sealed record ProjetoComEtapas(ProjetoLido Projeto, IReadOnlyList<EtapaDoProjeto> Etapas)
{
    public (int Feitas, int Totais) Progresso => Dominio.Projeto.Etapas.Progresso(Etapas);
}

/// <summary>
/// Empresas e projetos, portados de <c>importacao_router.py</c>. O fluxo da tela:
/// a remessa diz de quem é o arquivo (isso lê disco e fica no motor), a pessoa
/// confirma o pré-cadastro da empresa, e cria o projeto com as competências.
/// </summary>
public sealed class Trabalhos(
    IRepositorioDeTrabalhos repositorio,
    TimeProvider relogio,
    ILogger<Trabalhos> log)
{
    // ---------------------------------------------------------------- empresas
    /// <summary>O escopo de empresa vale aqui como em todo dado de cliente.</summary>
    public async Task<IReadOnlyList<EmpresaLida>> ListarEmpresas(Usuario usuario, CancellationToken cancelar) =>
        (await repositorio.ListarEmpresas(cancelar)).Where(e => usuario.EnxergaEmpresa(e.Id)).ToList();

    public async Task<EmpresaLida> CriarEmpresa(string cnpjRaiz, string cnpjMatriz, string razaoSocial, string uf,
        string? inscricaoEstadual, string? grupoEconomico, Usuario por, CancellationToken cancelar)
    {
        Cnpj matriz;
        try
        {
            matriz = new Cnpj(cnpjMatriz);
        }
        catch (CnpjInvalido erro)
        {
            throw new DadoInvalido(erro.Message);
        }
        if (matriz.Raiz != cnpjRaiz)
            throw new RaizNaoConfere();
        if (await repositorio.RaizCadastrada(matriz.Raiz, cancelar))
            throw new EmpresaJaCadastrada(matriz.Raiz);

        // Quem cadastra é alocado na hora. Sem isto a pessoa cadastraria uma
        // empresa que em seguida não conseguiria enxergar, porque o escopo vem
        // só das alocações vigentes.
        var empresa = await repositorio.CriarEmpresa(
            new NovaEmpresa(matriz.Raiz, matriz.Valor, razaoSocial.Trim(), uf.ToUpperInvariant(),
                string.IsNullOrEmpty(inscricaoEstadual) ? null : inscricaoEstadual, grupoEconomico),
            por, relogio.GetUtcNow(), cancelar);
        log.Info("empresa pré-cadastrada a partir do SPED",
            new { empresa_id = empresa.Id, cnpj_raiz = empresa.CnpjRaiz, cnpj_matriz = empresa.CnpjMatriz,
                  por_usuario_id = por.Id, alocado_automaticamente = true });
        return empresa;
    }

    // ---------------------------------------------------------------- projetos
    public async Task<IReadOnlyList<ProjetoComEtapas>> ListarProjetos(Usuario usuario, CancellationToken cancelar) =>
        (await repositorio.ListarProjetos(cancelar))
            .Where(p => usuario.EnxergaEmpresa(p.EmpresaId))
            .Select(ComEtapas)
            .ToList();

    public async Task<ProjetoComEtapas> Detalhar(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var projeto = await repositorio.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        if (!usuario.EnxergaEmpresa(projeto.EmpresaId))
            throw new SemAcessoAEmpresa();
        return ComEtapas(projeto);
    }

    public async Task<ProjetoComEtapas> CriarProjeto(int empresaId, string frente, string nome, DateOnly ini, DateOnly fim,
        string? observacao, Usuario por, CancellationToken cancelar)
    {
        if (!Frentes.Existe(frente))
            throw new FrenteDesconhecida();
        if (fim < ini)
            throw new CompetenciasInvertidas();
        if (!await repositorio.EmpresaExiste(empresaId, cancelar))
            throw new EmpresaNaoEncontrada();
        // O Python não conferia: quem escreve criava projeto em empresa que não
        // enxerga, e em seguida não via o que acabara de criar (DECISOES, 13/09/2026).
        if (!por.EnxergaEmpresa(empresaId))
            throw new SemAcessoAEmpresa();

        nome = nome.Trim();
        if (await repositorio.ProjetoRepetido(empresaId, frente, nome, cancelar))
            throw new ProjetoRepetido();

        var agora = relogio.GetUtcNow();
        var id = await repositorio.CriarProjeto(new NovoProjeto(empresaId, frente, nome, ini, fim, observacao), por, agora,
            cancelar);
        try
        {
            await repositorio.RegistrarEvento(id, TipoDeEvento.Criado, $"{Frentes.Rotulo(frente)} · {nome}",
                new Dictionary<string, object>
                {
                    ["frente"] = frente, ["nome"] = nome,
                    ["competencia_ini"] = ini.ToString("yyyy-MM-dd"), ["competencia_fim"] = fim.ToString("yyyy-MM-dd"),
                }, por, agora, cancelar);
        }
        catch (Exception erro) when (erro is not OperationCanceledException)
        {
            // registrar evento nunca derruba a operação que o gerou
            log.Aviso("não deu para registrar o evento do projeto",
                new { projeto_id = id, tipo = TipoDeEvento.Criado, motivo = erro.Message });
        }

        log.Info("projeto criado", new { projeto_id = id, empresa_id = empresaId, frente, por_usuario_id = por.Id });
        return ComEtapas((await repositorio.BuscarProjeto(id, cancelar))!);
    }

    /// <summary>
    /// A importação conclui quando entrou base, não quando o projeto nasceu: o
    /// cadastro lê uma amostra do SPED e não traz base nenhuma. Cada etapa de
    /// processamento conclui com uma rodada terminada; enquanto roda, aparece
    /// em andamento, que é o que explica a espera.
    /// </summary>
    public static ProjetoComEtapas ComEtapas(ProjetoLido p)
    {
        var concluidas = new HashSet<string>();
        string? emAndamento = null;
        if (p.TemBase)
            concluidas.Add("importar");
        foreach (var etapa in new[] { "conferencia", "movimentos" })
        {
            if (!p.UltimaSituacaoPorEtapa.TryGetValue(etapa, out var situacao))
                continue;
            if (situacao == "concluida")
                concluidas.Add(etapa);
            else if (situacao is "na_fila" or "rodando" && emAndamento is null)
                emAndamento = etapa;
        }
        return new ProjetoComEtapas(p, Etapas.Montar(concluidas, emAndamento));
    }
}

/// <summary>
/// Apagar um trabalho, portado de <c>excluir_trabalho.py</c>. A única operação
/// do sistema que pede a senha de novo: a sessão fica aberta a jornada inteira,
/// e uma tela deixada em máquina destravada não pode bastar para desfazer meses
/// de apuração. Não há lixeira — o que fica é o log.
/// </summary>
public sealed class ExcluirTrabalho(
    IRepositorioDeTrabalhos repositorio,
    IRepositorioDeUsuario usuarios,
    IConferidorDeSenha senhas,
    IMotor motor,
    ILogger<ExcluirTrabalho> log)
{
    /// <summary>
    /// O que some, para a confirmação ser informada: "apagar o trabalho?" é
    /// muito diferente de "apagar o trabalho, 3 lotes, 7.036 arquivos e 2 conferências?".
    /// </summary>
    public async Task<OQueSeraApagado> Resumir(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var projeto = await repositorio.BuscarProjeto(projetoId, cancelar)
                      ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
        if (!usuario.EnxergaEmpresa(projeto.EmpresaId))
            throw new SemAcessoAEmpresa();
        return await repositorio.ResumirExclusao(projetoId, cancelar)
               ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
    }

    public async Task<OQueSeraApagado> Executar(int projetoId, Usuario usuario, string senha, CancellationToken cancelar)
    {
        var resumo = await Resumir(projetoId, usuario, cancelar);

        if (string.IsNullOrEmpty(senha) ||
            !senhas.Conferir(senha, await usuarios.ObterResumoDaSenha(usuario.Id, cancelar)))
        {
            // Não conta tentativa de login de propósito: errar a senha ao
            // confirmar uma exclusão não pode trancar a pessoa fora do sistema.
            // Mas fica no log como evento de segurança.
            log.Aviso("senha incorreta na confirmação de exclusão de trabalho",
                new { usuario_id = usuario.Id, usuario = usuario.NomeDeUsuario, projeto_id = projetoId });
            throw new SenhaNaoConfere();
        }

        // Pastas antes do banco, como no Python: se o motor não responder, nada
        // foi apagado e a pessoa tenta de novo — em vez de sobrar pasta sem dono.
        var pastas = await repositorio.PastasDeTrabalho(projetoId, cancelar);
        if (pastas.Count > 0)
        {
            var resultado = await motor.ApagarPastas(pastas, cancelar);
            if (resultado.Recusadas.Count > 0)
                log.Aviso("pastas de trabalho fora da raiz do motor não foram apagadas",
                    new { projeto_id = projetoId, pastas = resultado.Recusadas });
        }

        await repositorio.ApagarTrabalho(projetoId, cancelar);

        // não há lixeira: o registro de quem apagou o quê precisa ser completo
        // o bastante para responder meses depois
        log.Aviso("trabalho excluído",
            new { projeto_id = projetoId, projeto = resumo.Projeto, empresa = resumo.Empresa, lotes = resumo.Lotes,
                  arquivos = resumo.Arquivos, execucoes = resumo.Execucoes, pastas_de_trabalho = pastas.Count,
                  por_usuario_id = usuario.Id, por_usuario = usuario.NomeDeUsuario, papel = usuario.Papel.Valor() });
        return resumo;
    }
}
