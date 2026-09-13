namespace Cat.Dominio.Acesso;

/// <summary>O que a pessoa pode fazer. Ortogonal a QUAIS empresas ela enxerga.</summary>
public enum Papel
{
    /// <summary>Manutenção do sistema; ignora o escopo de empresa.</summary>
    Dev,
    /// <summary>Administra usuários e alocações.</summary>
    Gestor,
    /// <summary>Executa apuração e aprova de-para.</summary>
    Analista,
    /// <summary>Confere e aprova entrega.</summary>
    Revisor,
    /// <summary>Só consulta.</summary>
    Leitura,
}

/// <summary>
/// As capacidades de cada papel. As rotas perguntam a capacidade, nunca o
/// papel: enumerar papéis na rota faz todo papel novo exigir caçar rotas.
/// </summary>
public static class Capacidades
{
    public static bool AdministraUsuarios(this Papel papel) => papel is Papel.Dev or Papel.Gestor;

    public static bool PodeEscrever(this Papel papel) =>
        papel is Papel.Dev or Papel.Gestor or Papel.Analista or Papel.Revisor;

    /// <summary>
    /// Apagar um trabalho inteiro é de quem responde pelo cliente. Separada de
    /// <see cref="AdministraUsuarios"/> de propósito, embora hoje recaia sobre
    /// os mesmos papéis: no dia em que uma mudar, a outra não deve mudar junto.
    /// </summary>
    public static bool PodeExcluirTrabalho(this Papel papel) => papel is Papel.Dev or Papel.Gestor;

    /// <summary>
    /// Gestor responde pela carteira inteira; dev precisa reproduzir problema
    /// em qualquer cliente. A diferença entre os dois está em
    /// <see cref="Usuario.AcessaPorExcecao"/>.
    /// </summary>
    public static bool IgnoraEscopoDeEmpresa(this Papel papel) => papel is Papel.Dev or Papel.Gestor;

    /// <summary>
    /// Dev NÃO conta para o mínimo de gestores: conta técnica não substitui
    /// responsável pelo negócio. Se contasse, dois gestores e um dev pareceriam três.
    /// </summary>
    public static bool ContaComoGestor(this Papel papel) => papel is Papel.Gestor;
}

/// <summary>
/// Posição na estrutura da empresa. Não confundir com Papel: papel define
/// permissão; cargo é informação organizacional.
/// </summary>
public enum Cargo
{
    Diretor,
    Gerente,
    Coordenador,
    Analista,
    Estagiario,
    Outro,
}

public static class Cargos
{
    public static bool EDeGestao(this Cargo cargo) =>
        cargo is Cargo.Diretor or Cargo.Gerente or Cargo.Coordenador;
}

/// <summary>
/// O texto gravado no banco e trocado com a tela. É o mesmo do Python
/// (<c>"gestor"</c>, <c>"estagiario"</c>), e não o nome do enum em C#.
/// </summary>
public static class TextoDeAcesso
{
    public static string Valor(this Papel papel) => papel.ToString().ToLowerInvariant();

    public static string Valor(this Cargo cargo) => cargo.ToString().ToLowerInvariant();

    public static bool TentarPapel(string? texto, out Papel papel) => TentarEnum(texto, out papel);

    public static bool TentarCargo(string? texto, out Cargo cargo) => TentarEnum(texto, out cargo);

    // só aceita exatamente o texto minúsculo: "Gestor" ou "1" no banco é
    // valor desconhecido, como é para o Enum do Python
    private static bool TentarEnum<T>(string? texto, out T valor) where T : struct, Enum
    {
        foreach (var candidato in Enum.GetValues<T>())
        {
            if (candidato.ToString().ToLowerInvariant() == texto)
            {
                valor = candidato;
                return true;
            }
        }
        valor = default;
        return false;
    }
}
