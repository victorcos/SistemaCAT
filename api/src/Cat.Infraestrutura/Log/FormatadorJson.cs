using System.Text.Encodings.Web;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Logging.Console;
using Microsoft.Extensions.Options;

namespace Cat.Infraestrutura.Log;

/// <summary>
/// Uma linha, um JSON — com os mesmos nomes de campo do <c>cat/log.py</c>.
///
/// Durante a migração as duas APIs escrevem log ao mesmo tempo, e a mesma
/// requisição passa pelas duas. Se os campos tivessem nomes diferentes, uma
/// busca por <c>requisicao_id</c> acharia metade da história.
/// </summary>
public sealed class FormatadorJson : ConsoleFormatter
{
    public const string Nome = "cat-json";

    // nunca escrever isto em log, mesmo que venha nos campos
    private static readonly HashSet<string> Segredos = new(StringComparer.OrdinalIgnoreCase)
    {
        "senha", "password", "token", "access_token", "secret", "authorization",
        "hashed_password", "chave", "api_key", "senha_hash",
    };

    // acento sai como acento, como o ensure_ascii=False do Python
    private static readonly JsonWriterOptions OpcoesEscrita = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public FormatadorJson(IOptionsMonitor<ConsoleFormatterOptions> _) : base(Nome) { }

    public override void Write<TState>(in LogEntry<TState> entrada, IExternalScopeProvider? escopos,
        TextWriter saida)
    {
        var mensagem = entrada.Formatter(entrada.State, entrada.Exception);
        if (string.IsNullOrEmpty(mensagem) && entrada.Exception is null)
            return;

        using var buffer = new MemoryStream();
        using (var json = new Utf8JsonWriter(buffer, OpcoesEscrita))
        {
            json.WriteStartObject();
            json.WriteString("instante", DateTimeOffset.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffffzzz"));
            json.WriteString("nivel", Nivel(entrada.LogLevel));
            json.WriteString("origem", entrada.Category);
            json.WriteString("mensagem", mensagem);

            // contexto antes dos campos: o campo da linha vence o do bloco
            var campos = new Dictionary<string, object?>();
            escopos?.ForEachScope((escopo, acumulado) =>
            {
                if (escopo is IEnumerable<KeyValuePair<string, object?>> pares)
                    foreach (var (chave, valor) in pares)
                        if (chave != "{OriginalFormat}")
                            acumulado[chave] = valor;
            }, campos);

            string? local = null;
            switch (entrada.State)
            {
                case EventoDeLog evento:
                    foreach (var (chave, valor) in evento.Campos)
                        campos[chave] = valor;
                    local = evento.Local;
                    break;
                // log do próprio ASP.NET e do YARP: os argumentos do modelo de mensagem
                case IEnumerable<KeyValuePair<string, object?>> pares:
                    foreach (var (chave, valor) in pares)
                        if (chave != "{OriginalFormat}")
                            campos[chave] = valor;
                    break;
            }

            foreach (var (chave, valor) in campos)
            {
                json.WritePropertyName(chave);
                EscreverValor(json, Segredos.Contains(chave) ? "***" : valor);
            }

            if (entrada.Exception is not null)
                json.WriteString("excecao", entrada.Exception.ToString());
            if (local is not null)
                json.WriteString("local", local);
            json.WriteEndObject();
        }

        saida.WriteLine(System.Text.Encoding.UTF8.GetString(buffer.GetBuffer(), 0, (int)buffer.Length));
    }

    private static void EscreverValor(Utf8JsonWriter json, object? valor)
    {
        try
        {
            JsonSerializer.Serialize(json, valor, valor?.GetType() ?? typeof(object));
        }
        catch (Exception)
        {
            // como o default=str do Python: o que não serializa vira texto,
            // em vez de derrubar a linha de log inteira
            json.WriteStringValue(valor?.ToString());
        }
    }

    /// <summary>Os nomes do logging do Python, para um filtro servir aos dois.</summary>
    public static string Nivel(LogLevel nivel) => nivel switch
    {
        LogLevel.Trace or LogLevel.Debug => "DEBUG",
        LogLevel.Information => "INFO",
        LogLevel.Warning => "WARNING",
        LogLevel.Error => "ERROR",
        LogLevel.Critical => "CRITICAL",
        _ => "INFO",
    };

    public static LogLevel ParaNivel(string nome) => nome.ToUpperInvariant() switch
    {
        "DEBUG" => LogLevel.Debug,
        "WARNING" or "WARN" => LogLevel.Warning,
        "ERROR" => LogLevel.Error,
        "CRITICAL" => LogLevel.Critical,
        _ => LogLevel.Information,
    };
}
