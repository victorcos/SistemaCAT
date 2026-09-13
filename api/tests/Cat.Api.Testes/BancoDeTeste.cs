using System.Diagnostics;
using Cat.Infraestrutura.Auth;
using Npgsql;

namespace Cat.Api.Testes;

/// <summary>
/// Um banco Postgres só para os testes, recriado a cada rodada e migrado pelo
/// Alembic — o dono do esquema. Testar contra SQLite provaria outra coisa: a API
/// em C# fala só com Postgres, e é no Postgres que fuso horário e tipo pegam.
/// </summary>
public sealed class BancoDeTeste : IAsyncLifetime
{
    public const string Pimenta = "pimenta-de-teste-nao-e-segredo";
    public const string Segredo = "segredo-de-teste-com-mais-de-trinta-e-dois-bytes-nao-e-segredo";
    public const string SenhaPadrao = "Senha-Certa-2026";

    private const string Nome = "cat_testes_csharp";

    // mesmo contêiner do desenvolvimento; banco próprio para nunca tocar em dado de trabalho
    private static readonly string Servidor =
        Environment.GetEnvironmentVariable("CAT_TESTES_POSTGRES") ?? "Host=127.0.0.1;Port=55432;Username=cat;Password=cat";

    public string Url { get; } = $"postgresql+psycopg://cat:cat@127.0.0.1:55432/{Nome}";
    public string ResumoPadrao { get; } = new SenhasArgon2(Pimenta).Gerar(SenhaPadrao);

    public async Task InitializeAsync()
    {
        try
        {
            await using var admin = new NpgsqlConnection($"{Servidor};Database=postgres");
            await admin.OpenAsync();
            await Executar(admin, $"DROP DATABASE IF EXISTS {Nome} WITH (FORCE)");
            await Executar(admin, $"CREATE DATABASE {Nome}");
        }
        catch (NpgsqlException erro)
        {
            throw new InvalidOperationException(
                "Os testes de integração precisam do Postgres do docker/docker-compose.yml no ar " +
                $"(porta 55432). Suba com: docker compose -f docker/docker-compose.yml up -d. {erro.Message}", erro);
        }
        await MigrarComAlembic();
    }

    public Task DisposeAsync() => Task.CompletedTask;

    public async Task<NpgsqlConnection> Abrir()
    {
        var conexao = new NpgsqlConnection($"{Servidor};Database={Nome}");
        await conexao.OpenAsync();
        return conexao;
    }

    public async Task<int> CriarUsuario(string nome, string papel = "analista", bool ativo = true,
        string? resumo = null, int tentativas = 0, int[]? empresas = null, string cargo = "analista")
    {
        await using var c = await Abrir();
        await using var cmd = new NpgsqlCommand("""
            INSERT INTO usuario (usuario, email, nome_exibicao, senha_hash, papel, cargo, ativo,
                                 tentativas_falhas, senha_provisoria, criado_em)
            VALUES (@u, @e, @n, @h, @p, @c, @a, @t, false, now()) RETURNING id
            """, c);
        cmd.Parameters.AddWithValue("u", nome);
        cmd.Parameters.AddWithValue("e", $"{nome}@teste.local");
        cmd.Parameters.AddWithValue("n", nome.ToUpperInvariant());
        cmd.Parameters.AddWithValue("h", resumo ?? ResumoPadrao);
        cmd.Parameters.AddWithValue("p", papel);
        cmd.Parameters.AddWithValue("c", cargo);
        cmd.Parameters.AddWithValue("a", ativo);
        cmd.Parameters.AddWithValue("t", tentativas);
        var id = (int)(await cmd.ExecuteScalarAsync())!;

        foreach (var empresa in empresas ?? [])
        {
            await Executar(c, $"""
                INSERT INTO empresa (cnpj_raiz, razao_social, ativa) VALUES ('{empresa:D8}', 'Empresa {empresa}', true)
                ON CONFLICT (cnpj_raiz) DO NOTHING
                """);
            await Executar(c, $"""
                INSERT INTO alocacao (usuario_id, empresa_id, papel_projeto, inicio)
                SELECT {id}, id, 'analista', now() FROM empresa WHERE cnpj_raiz = '{empresa:D8}'
                """);
        }
        return id;
    }

    public async Task<T> Escalar<T>(string sql)
    {
        await using var c = await Abrir();
        await using var cmd = new NpgsqlCommand(sql, c);
        return (T)(await cmd.ExecuteScalarAsync())!;
    }

    public async Task Comando(string sql)
    {
        await using var c = await Abrir();
        await Executar(c, sql);
    }

    private static async Task Executar(NpgsqlConnection conexao, string sql)
    {
        await using var cmd = new NpgsqlCommand(sql, conexao);
        await cmd.ExecuteNonQueryAsync();
    }

    private async Task MigrarComAlembic()
    {
        var backend = RaizDoRepositorio.Backend();
        var inicio = new ProcessStartInfo(Path.Combine(backend, ".venv", "Scripts", "python.exe"))
        {
            WorkingDirectory = backend,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var arg in new[] { "-m", "alembic", "upgrade", "head" })
            inicio.ArgumentList.Add(arg);
        inicio.Environment["CAT_BANCO_URL"] = Url;

        using var processo = Process.Start(inicio)!;
        var erro = processo.StandardError.ReadToEndAsync();
        await processo.StandardOutput.ReadToEndAsync();
        await processo.WaitForExitAsync();
        if (processo.ExitCode != 0)
            throw new InvalidOperationException($"O Alembic não migrou o banco de teste:\n{await erro}");
    }
}

public static class RaizDoRepositorio
{
    public static string Backend()
    {
        for (var pasta = new DirectoryInfo(AppContext.BaseDirectory); pasta is not null; pasta = pasta.Parent)
        {
            var candidato = Path.Combine(pasta.FullName, "backend");
            if (File.Exists(Path.Combine(candidato, "pyproject.toml")))
                return candidato;
        }
        throw new InvalidOperationException("Não achei backend/ subindo a partir dos testes.");
    }
}

[CollectionDefinition(Nome)]
public sealed class ColecaoDoBanco : ICollectionFixture<BancoDeTeste>
{
    public const string Nome = "banco";
}
