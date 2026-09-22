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
        Escopo.Exigir(usuario, projeto.EmpresaId, log);
        return ComEtapas(projeto);
    }

    /// <param name="modulo">
    /// O assunto tributário do trabalho (ver <see cref="Segmentos"/>). Vazio cai em
    /// ICMS, que é o que todo trabalho criado antes desta coluna é — o sistema
    /// nasceu na CAT 42. Não se confunde com a frente: frente é o TIPO de trabalho
    /// (razão, de-para, quebra de SPED), módulo é o TRIBUTO.
    /// </param>
    public async Task<ProjetoComEtapas> CriarProjeto(int empresaId, string frente, string nome, DateOnly ini, DateOnly fim,
        string? observacao, Usuario por, CancellationToken cancelar, string? modulo = null)
    {
        if (!Frentes.Existe(frente))
            throw new FrenteDesconhecida();
        var assunto = string.IsNullOrWhiteSpace(modulo) ? Segmentos.Icms : modulo.Trim().ToLowerInvariant();
        if (Segmentos.Todos.SelectMany(s => s.Modulos).All(m => m.Chave != assunto))
            throw new DadoInvalido($"Módulo desconhecido: {assunto}.");
        // criar trabalho num assunto que a pessoa não enxerga é o mesmo tipo de
        // acidente que criar em empresa fora do escopo: ela não o veria depois
        var dono = Segmentos.Todos.First(s => s.Modulos.Any(m => m.Chave == assunto));
        if (!Segmentos.PodeVer(por, dono.Chave))
            throw new SemAcessoAoSegmento(dono.Rotulo);
        if (fim < ini)
            throw new CompetenciasInvertidas();
        if (!await repositorio.EmpresaExiste(empresaId, cancelar))
            throw new EmpresaNaoEncontrada();
        // O Python não conferia: quem escreve criava projeto em empresa que não
        // enxerga, e em seguida não via o que acabara de criar (DECISOES, 13/09/2026).
        Escopo.Exigir(por, empresaId, log);

        nome = nome.Trim();
        if (await repositorio.ProjetoRepetido(empresaId, frente, nome, cancelar))
            throw new ProjetoRepetido();

        var agora = relogio.GetUtcNow();
        var id = await repositorio.CriarProjeto(
            new NovoProjeto(empresaId, frente, assunto, nome, ini, fim, observacao), por, agora, cancelar);
        try
        {
            await repositorio.RegistrarEvento(id, TipoDeEvento.Criado, $"{Frentes.Rotulo(frente)} · {nome}",
                new Dictionary<string, object>
                {
                    ["frente"] = frente, ["modulo"] = assunto, ["nome"] = nome,
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
    /// Nome e período do trabalho. O que não vem fica como está; o que muda vira
    /// evento com o de e o para, e nada mudando é recusa, não evento vazio.
    /// </summary>
    public async Task<ProjetoComEtapas> AlterarCadastro(int projetoId, string? nome, DateOnly? ini, DateOnly? fim, Usuario por,
        CancellationToken cancelar)
    {
        var projeto = await repositorio.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        var novoNome = nome?.Trim() ?? projeto.Nome;
        if (novoNome.Length < CadastroDoTrabalho.TamanhoMinimoDoNome)
            throw new DadoInvalido($"O nome do trabalho precisa de pelo menos {CadastroDoTrabalho.TamanhoMinimoDoNome} caracteres.");
        var novoIni = ini ?? projeto.CompetenciaIni;
        var novoFim = fim ?? projeto.CompetenciaFim;
        if (novoFim < novoIni)
            throw new CompetenciasInvertidas();
        if (novoNome == projeto.Nome && novoIni == projeto.CompetenciaIni && novoFim == projeto.CompetenciaFim)
            throw new CadastroSemMudanca();
        if (novoNome != projeto.Nome && await repositorio.ProjetoRepetido(projeto.EmpresaId, projeto.Frente, novoNome, cancelar))
            throw new ProjetoRepetido();

        var texto = CadastroDoTrabalho.Frase(projeto.Nome, projeto.CompetenciaIni, projeto.CompetenciaFim, novoNome, novoIni, novoFim);
        var dados = new Dictionary<string, object>
        {
            ["parametro"] = "cadastro",
            ["de"] = new Dictionary<string, string>
            {
                ["nome"] = projeto.Nome, ["competencia_ini"] = projeto.CompetenciaIni.ToString("yyyy-MM-dd"),
                ["competencia_fim"] = projeto.CompetenciaFim.ToString("yyyy-MM-dd"),
            },
            ["para"] = new Dictionary<string, string>
            {
                ["nome"] = novoNome, ["competencia_ini"] = novoIni.ToString("yyyy-MM-dd"),
                ["competencia_fim"] = novoFim.ToString("yyyy-MM-dd"),
            },
        };
        await repositorio.AlterarCadastro(projetoId, novoNome, novoIni, novoFim, texto, dados, por, relogio.GetUtcNow(), cancelar);
        log.Aviso("cadastro do trabalho alterado", new
        {
            projeto_id = projetoId, por_usuario_id = por.Id, nome_de = projeto.Nome, nome_para = novoNome,
            ini_de = projeto.CompetenciaIni, ini_para = novoIni, fim_de = projeto.CompetenciaFim, fim_para = novoFim,
        });
        return ComEtapas((await repositorio.BuscarProjeto(projetoId, cancelar))!);
    }

    /// <summary>De quando é a base importada, contra o período do cadastro.</summary>
    public async Task<BaseDoTrabalho> BaseDoTrabalho(ProjetoLido projeto, CancellationToken cancelar) =>
        CadastroDoTrabalho.Resumir(await repositorio.CompetenciasDaBase(projeto.Id, cancelar),
            projeto.CompetenciaIni, projeto.CompetenciaFim);

    /// <summary>
    /// Como o trabalho enquadra a venda a consumidor final. Muda o razão e a
    /// apuração: o que já foi montado com a escolha antiga continua como está, e
    /// a tela do razão avisa que ele precisa rodar de novo.
    /// </summary>
    public async Task<ProjetoComEtapas> DefinirVendaAConsumidor(int projetoId, string valor, Usuario por,
        CancellationToken cancelar)
    {
        var projeto = await repositorio.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado();
        Escopo.Exigir(por, projeto.EmpresaId, log);
        var nova = VendaAConsumidor.Buscar(valor) ?? throw new VendaAConsumidorDesconhecida(valor);
        var atual = VendaAConsumidor.DoBanco(projeto.VendaAConsumidor);
        if (nova.Valor == atual.Valor)
            throw new MesmaVendaAConsumidor(atual);

        await repositorio.DefinirVendaAConsumidor(projetoId, nova.Valor,
            new Dictionary<string, object> { ["parametro"] = "venda_a_consumidor", ["de"] = atual.Valor, ["para"] = nova.Valor },
            por, relogio.GetUtcNow(), cancelar);
        // muda o valor do pedido: fica em aviso, para se achar no log sem filtro
        log.Aviso("venda a consumidor do trabalho alterada",
            new { projeto_id = projetoId, de = atual.Valor, para = nova.Valor, por_usuario_id = por.Id });
        return ComEtapas((await repositorio.BuscarProjeto(projetoId, cancelar))!);
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
        foreach (var etapa in Execucoes.DeProcessamento)
        {
            if (!p.UltimaSituacaoPorEtapa.TryGetValue(etapa, out var situacao))
                continue;
            if (situacao == "concluida")
                concluidas.Add(etapa);
            // a entrega montada que espera o revisor ainda está andando
            else if ((Execucoes.EmCurso(situacao) || situacao == Execucoes.AguardandoAprovacao) && emAndamento is null)
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
        Escopo.Exigir(usuario, projeto.EmpresaId, log);
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
