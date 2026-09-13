namespace Cat.Dominio.Acesso;

/// <summary>
/// Quem entra no sistema. Domínio puro: sem banco, sem framework, sem relógio
/// escondido — o instante vem sempre de fora, para o teste escolher.
///
/// <see cref="Empresas"/> é o escopo de visibilidade, derivado das alocações
/// vigentes. Papel diz o QUE pode fazer; empresas dizem SOBRE QUEM.
/// </summary>
public sealed class Usuario
{
    // Bloqueio em dois níveis. Destravar é muito mais frequente que redefinir
    // senha, então precisa ser barato: cinco erros já inviabilizam força bruta
    // e quinze minutos resolvem sozinhos, sem chamado. O bloqueio que exige
    // gestor fica para quem insistiu vinte vezes.
    public const int TentativasBloqueioTemporario = 5;
    public const int MinutosBloqueioTemporario = 15;
    public const int TentativasBloqueioPermanente = 20;

    public required int Id { get; init; }
    public required string NomeDeUsuario { get; init; }
    public required string Email { get; init; }
    public required string NomeExibicao { get; init; }
    public required Papel Papel { get; init; }
    public Cargo Cargo { get; init; } = Cargo.Outro;
    public bool Ativo { get; init; } = true;
    public int TentativasFalhas { get; private set; }
    public DateTimeOffset? BloqueadoAte { get; private set; }
    public bool SenhaProvisoria { get; init; }
    public DateTimeOffset? UltimoAcesso { get; private set; }
    public IReadOnlyList<int> Empresas { get; init; } = [];

    /// <summary>Reconstitui o estado de tentativas lido do banco.</summary>
    public Usuario ComTentativas(int falhas, DateTimeOffset? bloqueadoAte, DateTimeOffset? ultimoAcesso)
    {
        TentativasFalhas = falhas;
        BloqueadoAte = bloqueadoAte;
        UltimoAcesso = ultimoAcesso;
        return this;
    }

    // ---------- bloqueio ----------
    public bool BloqueadoEmDefinitivo => TentativasFalhas >= TentativasBloqueioPermanente;

    /// <summary>
    /// Quanto falta do bloqueio temporário, arredondado para cima. Mesma conta
    /// do Python, inclusive no último segundo: menos de um segundo inteiro de
    /// espera arredonda para zero e libera.
    /// </summary>
    public int MinutosDeEspera(DateTimeOffset agora)
    {
        if (BloqueadoAte is not { } limite)
            return 0;
        var segundos = (limite - agora).TotalSeconds;
        if (segundos <= 0)
            return 0;
        var inteiros = (long)Math.Truncate(segundos);
        return (int)Math.Max(0, (inteiros + 59) / 60);
    }

    /// <summary>
    /// Ordem importa: inativo antes de bloqueado, porque desativar é decisão do
    /// gestor e bloquear é consequência automática. E o permanente antes do
    /// temporário, porque é o mais grave.
    /// </summary>
    public void GarantirQuePodeEntrar(DateTimeOffset agora)
    {
        if (!Ativo)
            throw new UsuarioInativo();
        if (BloqueadoEmDefinitivo)
            throw new UsuarioBloqueado(TentativasFalhas);
        var espera = MinutosDeEspera(agora);
        if (espera > 0)
            throw new UsuarioBloqueadoTemporariamente(espera);
    }

    public void RegistrarFalha(DateTimeOffset agora)
    {
        TentativasFalhas++;
        // a cada patamar de 5 erros, mais 15 minutos de espera
        if (TentativasFalhas % TentativasBloqueioTemporario == 0 && !BloqueadoEmDefinitivo)
            BloqueadoAte = agora.AddMinutes(MinutosBloqueioTemporario);
    }

    public void RegistrarSucesso(DateTimeOffset agora)
    {
        TentativasFalhas = 0;
        BloqueadoAte = null;
        UltimoAcesso = agora;
    }

    /// <summary>Quantas faltam para o próximo bloqueio temporário.</summary>
    public int TentativasRestantes =>
        TentativasBloqueioTemporario - TentativasFalhas % TentativasBloqueioTemporario;

    // ---------- senha ----------
    /// <summary>Quem entrou com senha provisória só faz isto: trocar a senha.</summary>
    public bool PrecisaTrocarSenha => SenhaProvisoria;

    // ---------- escopo ----------
    /// <summary>Nenhuma consulta a dado fiscal passa sem esta pergunta.</summary>
    public bool EnxergaEmpresa(int empresaId) =>
        Papel.IgnoraEscopoDeEmpresa() || Empresas.Contains(empresaId);

    /// <summary>
    /// Verdadeiro quando o acesso só passou por ser <b>dev</b>. Serve para o log
    /// distinguir acesso normal de exceção. Gestor sem alocação não entra aqui:
    /// ver a carteira toda é o escopo do papel, não um desvio dele.
    /// </summary>
    public bool AcessaPorExcecao(int empresaId) =>
        Papel == Papel.Dev && !Empresas.Contains(empresaId);
}
