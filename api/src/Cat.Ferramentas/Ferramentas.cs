using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;
using Cat.Infraestrutura.Banco;
using Cat.Infraestrutura.Configuracao;
using Cat.Infraestrutura.Log;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Console;
using Npgsql;

namespace Cat.Ferramentas;

/// <summary>
/// Comandos de servidor, portados de <c>cli/semear.py</c> e <c>cli/emergencia.py</c>.
///
/// <b>Semear</b> cria os três gestores iniciais e uma empresa de exemplo. São
/// três porque o sistema recusa ficar com menos.
///
/// <b>Emergência</b> é a saída quando os três gestores estão indisponíveis ao
/// mesmo tempo. Exigir acesso ao servidor é um segundo fator razoável para um
/// sistema interno: quem chega até aqui já tem a máquina.
/// </summary>
public static class Ferramentas
{
    public const string Ajuda = """
        Uso:
          dotnet run --project api/src/Cat.Ferramentas -- semear
          dotnet run --project api/src/Cat.Ferramentas -- emergencia listar-gestores
          dotnet run --project api/src/Cat.Ferramentas -- emergencia promover <usuario>
          dotnet run --project api/src/Cat.Ferramentas -- emergencia redefinir <usuario>
          dotnet run --project api/src/Cat.Ferramentas -- emergencia desbloquear <usuario>
          dotnet run --project api/src/Cat.Ferramentas -- emergencia criar-dev <usuario> <email> <nome>
        """;

    private static readonly (string Nome, string Email, string Exibicao, Cargo Cargo)[] Gestores =
    [
        ("diretor", "diretor@bms.local", "Diretor", Cargo.Diretor),
        ("gerente", "gerente@bms.local", "Gerente", Cargo.Gerente),
        ("coordenador", "coordenador@bms.local", "Coordenador", Cargo.Coordenador),
    ];

    public static async Task<int> Executar(string[] args, IConfiguration configuracao, TextWriter saida,
        TimeProvider? relogio = null)
    {
        var comando = args switch
        {
            ["semear"] => Semear,
            ["emergencia", "listar-gestores"] => ListarGestores,
            ["emergencia", "promover", _] => Promover,
            ["emergencia", "redefinir", _] => Redefinir,
            ["emergencia", "desbloquear", _] => Desbloquear,
            ["emergencia", "criar-dev", _, _, _] => CriarDev,
            _ => (Func<Ambiente, string[], Task<int>>?)null,
        };
        if (comando is null)
        {
            await saida.WriteLineAsync(Ajuda);
            return 2;
        }

        await using var servicos = Montar(configuracao, relogio ?? TimeProvider.System);
        await using var escopo = servicos.CreateAsyncScope();
        var ambiente = new Ambiente(escopo.ServiceProvider, saida);
        try
        {
            return await comando(ambiente, args);
        }
        catch (PostgresException erro) when (erro.SqlState == PostgresErrorCodes.UndefinedTable)
        {
            // O C# não cria tabela: o esquema tem um dono só, e é o Alembic.
            await saida.WriteLineAsync("O banco não tem as tabelas do sistema. Rode antes: cd backend; alembic upgrade head");
            return 1;
        }
        catch (DadoInvalido erro)
        {
            await saida.WriteLineAsync(erro.Message);
            return 1;
        }
    }

    // ---------------------------------------------------------------- semear
    private static async Task<int> Semear(Ambiente a, string[] _)
    {
        var repo = a.Servico<IRepositorioDeUsuario>();
        var log = a.Log("Cat.Ferramentas.Semear");
        if (await repo.ExisteAlgum(CancellationToken.None))
        {
            log.Info("já existe usuário, nada a semear");
            await a.Saida.WriteLineAsync("Já existe usuário. Nada foi feito.");
            return 0;
        }

        var banco = a.Servico<CatDbContext>();
        var senhas = a.Servico<IConferidorDeSenha>();
        var agora = a.Servico<TimeProvider>().GetUtcNow().UtcDateTime;

        // Numa transação só. Pela metade, o banco ficaria com menos de três
        // gestores e "já existe usuário" impediria semear de novo.
        await using var transacao = await banco.Database.BeginTransactionAsync();
        var empresa = new EmpresaLinha
            { CnpjRaiz = "00000000", RazaoSocial = "Empresa de exemplo", GrupoEconomico = "—", Uf = "SP", Ativa = true };
        banco.Empresas.Add(empresa);
        await banco.SaveChangesAsync();

        var criados = new List<(string Nome, string Cargo, string Senha)>();
        foreach (var (nome, email, exibicao, cargo) in Gestores)
        {
            var senha = PoliticaDeAcesso.GerarSenhaProvisoria();
            var u = await repo.Criar(new NovoUsuario(nome, email, exibicao, senhas.Gerar(senha), Papel.Gestor, cargo,
                SenhaProvisoria: true), CancellationToken.None);
            banco.Alocacoes.Add(new AlocacaoLinha
                { UsuarioId = u.Id, EmpresaId = empresa.Id, PapelProjeto = "responsavel", Inicio = agora });
            criados.Add((nome, cargo.Valor(), senha));
        }
        await banco.SaveChangesAsync();
        await transacao.CommitAsync();

        await a.Saida.WriteLineAsync("\n  Três gestores criados. A troca de senha é obrigatória no");
        await a.Saida.WriteLineAsync("  primeiro acesso de cada um.\n");
        await a.Saida.WriteLineAsync($"  {"usuário",-14} {"cargo",-13} senha provisória");
        await a.Saida.WriteLineAsync($"  {new string('-', 14)} {new string('-', 13)} {new string('-', 16)}");
        foreach (var (nome, cargo, senha) in criados)
            await a.Saida.WriteLineAsync($"  {nome,-14} {cargo,-13} {senha}");
        await a.Saida.WriteLineAsync("\n  Anote agora. Estas senhas não são exibidas de novo.\n");

        log.Info("semeadura concluída", new { gestores = criados.Count, empresa_id = empresa.Id });
        return 0;
    }

    // ---------------------------------------------------------------- emergência
    private static async Task<int> ListarGestores(Ambiente a, string[] _)
    {
        var agora = a.Servico<TimeProvider>().GetUtcNow();
        var gestores = (await a.Servico<IRepositorioDeUsuario>().Listar(CancellationToken.None))
            .Where(u => u.Papel == Papel.Gestor).ToList();
        await a.Saida.WriteLineAsync($"\n  Gestores ativos: {gestores.Count(u => u.Ativo)}\n");
        foreach (var u in gestores)
        {
            var marca = u.Ativo ? " " : "×";
            var trava = u.Bloqueado(agora) ? " [bloqueado]" : "";
            await a.Saida.WriteLineAsync($"   {marca} {u.NomeDeUsuario,-20} {u.Cargo.Valor(),-12} {u.NomeExibicao}{trava}");
        }
        await a.Saida.WriteLineAsync();
        return 0;
    }

    private static async Task<int> Promover(Ambiente a, string[] args)
    {
        var repo = a.Servico<IRepositorioDeUsuario>();
        if (await Alvo(a, args[2]) is not { } alvo)
            return 1;
        await repo.DefinirPapel(alvo.Id, Papel.Gestor, CancellationToken.None);
        await repo.DefinirSituacao(alvo.Id, true, CancellationToken.None);
        a.Log("Cat.Ferramentas.Emergencia").Aviso("promoção a gestor pela saída de emergência",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, papel_anterior = alvo.Papel.Valor(),
                  via = "cli_emergencia" });
        await a.Saida.WriteLineAsync($"'{args[2]}' agora é gestor e está ativo.");
        return 0;
    }

    private static async Task<int> Redefinir(Ambiente a, string[] args)
    {
        var repo = a.Servico<IRepositorioDeUsuario>();
        if (await Alvo(a, args[2]) is not { } alvo)
            return 1;
        var senha = PoliticaDeAcesso.GerarSenhaProvisoria();
        await repo.DefinirSenha(alvo.Id, a.Servico<IConferidorDeSenha>().Gerar(senha), provisoria: true,
            CancellationToken.None);
        await repo.Desbloquear(alvo.Id, CancellationToken.None);
        a.Log("Cat.Ferramentas.Emergencia").Aviso("senha redefinida pela saída de emergência",
            new { usuario_id = alvo.Id, usuario = alvo.NomeDeUsuario, via = "cli_emergencia" });
        await a.Saida.WriteLineAsync($"\n  Usuário .. {args[2]}");
        await a.Saida.WriteLineAsync($"  Senha .... {senha}");
        await a.Saida.WriteLineAsync("\n  Provisória: a troca é obrigatória no primeiro acesso.\n");
        return 0;
    }

    private static async Task<int> Desbloquear(Ambiente a, string[] args)
    {
        if (await Alvo(a, args[2]) is not { } alvo)
            return 1;
        await a.Servico<IRepositorioDeUsuario>().Desbloquear(alvo.Id, CancellationToken.None);
        a.Log("Cat.Ferramentas.Emergencia").Aviso("desbloqueio pela saída de emergência",
            new { usuario_id = alvo.Id, via = "cli_emergencia" });
        await a.Saida.WriteLineAsync($"'{args[2]}' desbloqueado.");
        return 0;
    }

    /// <summary>
    /// Conta de manutenção, papel dev. Só pela linha de comando, de propósito:
    /// conta que ignora o escopo de empresa não deve nascer por clique na tela.
    /// </summary>
    private static async Task<int> CriarDev(Ambiente a, string[] args)
    {
        var repo = a.Servico<IRepositorioDeUsuario>();
        var nome = PoliticaDeAcesso.ValidarNomeDeUsuario(args[2]);
        var email = PoliticaDeAcesso.ValidarEmail(args[3]);
        if (await repo.BuscarPorNome(nome, CancellationToken.None) is not null)
        {
            await a.Saida.WriteLineAsync($"Já existe usuário '{nome}'.");
            return 1;
        }
        if (await repo.BuscarPorEmail(email, CancellationToken.None) is not null)
        {
            await a.Saida.WriteLineAsync($"Já existe usuário com o e-mail '{email}'.");
            return 1;
        }

        var senha = PoliticaDeAcesso.GerarSenhaProvisoria();
        var novo = await repo.Criar(new NovoUsuario(nome, email, PoliticaDeAcesso.ValidarNomeDeExibicao(args[4]),
            a.Servico<IConferidorDeSenha>().Gerar(senha), Papel.Dev, Cargo.Outro, SenhaProvisoria: true),
            CancellationToken.None);
        a.Log("Cat.Ferramentas.Emergencia").Aviso("conta de manutencao criada",
            new { usuario_id = novo.Id, usuario = nome, papel = Papel.Dev.Valor(), via = "cli_emergencia",
                  ignora_escopo_de_empresa = true });
        await a.Saida.WriteLineAsync($"\n  Usuário .. {nome}");
        await a.Saida.WriteLineAsync($"  Senha .... {senha}");
        await a.Saida.WriteLineAsync("\n  Papel dev: enxerga toda empresa, com ou sem alocação.");
        await a.Saida.WriteLineAsync("  Cada acesso sem alocação fica registrado no log como exceção.");
        await a.Saida.WriteLineAsync("  Provisória: a troca é obrigatória no primeiro acesso.\n");
        return 0;
    }

    // ---------------------------------------------------------------- interno
    private static async Task<Usuario?> Alvo(Ambiente a, string nome)
    {
        var alvo = await a.Servico<IRepositorioDeUsuario>().BuscarPorNome(nome, CancellationToken.None);
        if (alvo is null)
            await a.Saida.WriteLineAsync($"Usuário '{nome}' não encontrado.");
        return alvo;
    }

    private static ServiceProvider Montar(IConfiguration configuracao, TimeProvider relogio)
    {
        var config = ConfigCat.Carregar(configuracao);
        var servicos = new ServiceCollection();
        servicos.AddLogging(l => l
            .AddConsole(o => o.FormatterName = FormatadorJson.Nome)
            .AddConsoleFormatter<FormatadorJson, ConsoleFormatterOptions>()
            .SetMinimumLevel(FormatadorJson.ParaNivel(config.LogNivel))
            .AddFilter("Microsoft", LogLevel.Warning));
        servicos.AddSingleton(config);
        servicos.AddSingleton(relogio);
        servicos.AddDbContext<CatDbContext>(o => o.UseNpgsql(ConexaoPostgres.DeUrl(config.BancoUrl)));
        servicos.AddSingleton<IConferidorDeSenha>(sp =>
            new SenhasArgon2(config.SenhaPimenta, sp.GetRequiredService<ILogger<SenhasArgon2>>()));
        servicos.AddScoped<IRepositorioDeUsuario, UsuarioRepositorio>();
        return servicos.BuildServiceProvider();
    }

    private sealed record Ambiente(IServiceProvider Servicos, TextWriter Saida)
    {
        public T Servico<T>() where T : notnull => Servicos.GetRequiredService<T>();
        public ILogger Log(string categoria) => Servicos.GetRequiredService<ILoggerFactory>().CreateLogger(categoria);
    }
}
