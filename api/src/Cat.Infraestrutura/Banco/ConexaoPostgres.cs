using Npgsql;

namespace Cat.Infraestrutura.Banco;

/// <summary>
/// Traduz o <c>CAT_BANCO_URL</c> do SQLAlchemy para a cadeia de conexão do Npgsql.
///
/// O endereço fica escrito uma vez só, no formato que o Python já usa. Duas
/// variáveis para o mesmo banco é convite a apontar cada processo para um lugar.
/// </summary>
public static class ConexaoPostgres
{
    public static string DeUrl(string bancoUrl)
    {
        if (bancoUrl.StartsWith("sqlite", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                "A API em C# fala só com Postgres, e CAT_BANCO_URL aponta para SQLite. " +
                "Suba o Postgres do docker/docker-compose.yml e ajuste o backend/.env.");

        // "postgresql+psycopg://", "postgresql://" e "postgres://" dizem a mesma coisa
        var semDriver = System.Text.RegularExpressions.Regex.Replace(
            bancoUrl, @"^postgres(ql)?(\+[a-z0-9]+)?://", "postgresql://");
        if (!Uri.TryCreate(semDriver, UriKind.Absolute, out var uri) || uri.Scheme != "postgresql")
            throw new InvalidOperationException($"CAT_BANCO_URL não é um endereço de Postgres: {Mascarar(bancoUrl)}");

        var credenciais = uri.UserInfo.Split(':', 2);
        var cadeia = new NpgsqlConnectionStringBuilder
        {
            Host = uri.Host,
            Port = uri.IsDefaultPort || uri.Port <= 0 ? 5432 : uri.Port,
            Database = Uri.UnescapeDataString(uri.AbsolutePath.TrimStart('/')),
            Username = Uri.UnescapeDataString(credenciais[0]),
            Password = credenciais.Length > 1 ? Uri.UnescapeDataString(credenciais[1]) : null,
            // o nome aparece em pg_stat_activity: saber qual processo segura a conexão
            ApplicationName = "cat-api-csharp",
        };
        return cadeia.ConnectionString;
    }

    /// <summary>O endereço sem a senha, para log e mensagem de erro.</summary>
    public static string Mascarar(string bancoUrl) =>
        System.Text.RegularExpressions.Regex.Replace(bancoUrl, @"(://[^:/@]+:)[^@]*@", "$1***@");
}
