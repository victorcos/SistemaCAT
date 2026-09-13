namespace Cat.Infraestrutura.Configuracao;

/// <summary>
/// Leitor do <c>backend/.env</c>, o mesmo arquivo que o Python lê.
///
/// Uma máquina tem um arquivo de segredos só. Se o C# tivesse o próprio, a
/// pimenta e o segredo do token acabariam com duas cópias — e bastaria uma
/// divergir para ninguém mais conseguir entrar.
/// </summary>
public static class ArquivoEnv
{
    public static IReadOnlyDictionary<string, string> Ler(string caminho)
    {
        if (!File.Exists(caminho))
            return new Dictionary<string, string>();
        // o instalar.ps1 grava com BOM; o leitor padrão do .NET já o descarta
        return Interpretar(File.ReadAllText(caminho));
    }

    public static IReadOnlyDictionary<string, string> Interpretar(string conteudo)
    {
        var valores = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var bruta in conteudo.TrimStart('\uFEFF').Split('\n'))
        {
            var linha = bruta.Trim();
            if (linha.Length == 0 || linha.StartsWith('#'))
                continue;

            // só o primeiro "=" separa: o valor pode conter outros
            var igual = linha.IndexOf('=');
            if (igual <= 0)
                continue;

            var chave = linha[..igual].Trim();
            var valor = linha[(igual + 1)..].Trim();
            if (valor.Length >= 2 &&
                ((valor[0] == '"' && valor[^1] == '"') || (valor[0] == '\'' && valor[^1] == '\'')))
                valor = valor[1..^1];

            valores[chave] = valor;
        }
        return valores;
    }
}
