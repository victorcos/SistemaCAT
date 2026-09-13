using System.Runtime.CompilerServices;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Log;

/// <summary>
/// Uma linha de log com mensagem fixa e campos à parte, como o
/// <c>log.info("...", extra={...})</c> do Python.
///
/// Mensagem fixa de propósito: "requisição atendida" se procura; "requisição
/// atendida com status 404 em 12 ms" não se agrupa.
/// </summary>
public sealed record EventoDeLog(
    string Mensagem,
    IReadOnlyDictionary<string, object?> Campos,
    string Local);

/// <summary>
/// Atalhos que carregam o local exato de quem chamou. Obrigatório pela
/// ARQUITETURA §12: log sem origem manda caçar de onde veio.
/// </summary>
public static class Registro
{
    public static void Info(this ILogger log, string mensagem, object? campos = null,
        [CallerFilePath] string arquivo = "", [CallerLineNumber] int linha = 0) =>
        Escrever(log, LogLevel.Information, mensagem, campos, null, arquivo, linha);

    public static void Aviso(this ILogger log, string mensagem, object? campos = null,
        [CallerFilePath] string arquivo = "", [CallerLineNumber] int linha = 0) =>
        Escrever(log, LogLevel.Warning, mensagem, campos, null, arquivo, linha);

    public static void Erro(this ILogger log, string mensagem, object? campos = null,
        Exception? excecao = null,
        [CallerFilePath] string arquivo = "", [CallerLineNumber] int linha = 0) =>
        Escrever(log, LogLevel.Error, mensagem, campos, excecao, arquivo, linha);

    /// <summary>Campos que acompanham toda linha emitida dentro do bloco.</summary>
    public static IDisposable? Contexto(this ILogger log, object campos) =>
        log.BeginScope(ParaDicionario(campos));

    private static void Escrever(ILogger log, LogLevel nivel, string mensagem, object? campos,
        Exception? excecao, string arquivo, int linha)
    {
        if (!log.IsEnabled(nivel))
            return;
        var evento = new EventoDeLog(mensagem, ParaDicionario(campos), $"{arquivo}:{linha}");
        log.Log(nivel, default, evento, excecao, static (e, _) => e.Mensagem);
    }

    public static IReadOnlyDictionary<string, object?> ParaDicionario(object? campos) =>
        campos switch
        {
            null => new Dictionary<string, object?>(),
            IReadOnlyDictionary<string, object?> pronto => pronto,
            IEnumerable<KeyValuePair<string, object?>> pares => pares.ToDictionary(),
            _ => campos.GetType().GetProperties()
                .ToDictionary(p => p.Name, p => p.GetValue(campos)),
        };
}
