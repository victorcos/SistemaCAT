using Cat.Dominio.Acesso;

namespace Cat.Dominio.Testes;

/// <summary>Portados de tests/unidade/test_usuario.py, mais o relógio do bloqueio.</summary>
public sealed class UsuarioTestes
{
    private static readonly DateTimeOffset Agora = new(2026, 9, 13, 12, 0, 0, TimeSpan.Zero);

    private static Usuario Novo(Papel papel = Papel.Analista, bool ativo = true, int[]? empresas = null) => new()
    {
        Id = 1, NomeDeUsuario = "ana", Email = "ana@bms.local", NomeExibicao = "Ana",
        Papel = papel, Ativo = ativo, Empresas = empresas ?? [],
    };

    [Fact]
    public void Usuario_normal_entra() => Novo().GarantirQuePodeEntrar(Agora);

    [Fact]
    public void Inativo_nao_entra() =>
        Assert.Throws<UsuarioInativo>(() => Novo(ativo: false).GarantirQuePodeEntrar(Agora));

    [Fact]
    public void Inativo_tem_precedencia_sobre_bloqueado()
    {
        var u = Novo(ativo: false).ComTentativas(Usuario.TentativasBloqueioPermanente, null, null);
        Assert.Throws<UsuarioInativo>(() => u.GarantirQuePodeEntrar(Agora));
    }

    [Fact]
    public void Bloqueio_definitivo_impede_entrada_mesmo_sem_espera()
    {
        var u = Novo().ComTentativas(20, null, null);
        var erro = Assert.Throws<UsuarioBloqueado>(() => u.GarantirQuePodeEntrar(Agora));
        Assert.Equal(20, erro.Tentativas);
    }

    [Fact]
    public void Quinta_falha_bloqueia_por_quinze_minutos()
    {
        var u = Novo();
        for (var i = 0; i < 4; i++)
            u.RegistrarFalha(Agora);
        Assert.Null(u.BloqueadoAte);
        Assert.Equal(1, u.TentativasRestantes);

        u.RegistrarFalha(Agora);

        Assert.Equal(Agora.AddMinutes(15), u.BloqueadoAte);
        var erro = Assert.Throws<UsuarioBloqueadoTemporariamente>(() => u.GarantirQuePodeEntrar(Agora));
        Assert.Equal(15, erro.Minutos);
        Assert.Equal("Muitas tentativas. Tente de novo em 15 minutos.", erro.Message);
        Assert.Equal(5, u.TentativasRestantes);
    }

    [Theory]
    // mesma conta do Python: segundos inteiros, arredondados para cima em minutos
    [InlineData(15 * 60, 15)]
    [InlineData(61, 2)]
    [InlineData(60.9, 1)]
    [InlineData(1, 1)]
    [InlineData(0.5, 0)]   // menos de um segundo inteiro libera, como no Python
    [InlineData(0, 0)]
    [InlineData(-30, 0)]
    public void Espera_arredonda_como_o_python(double segundosRestantes, int minutos)
    {
        var u = Novo().ComTentativas(5, Agora.AddSeconds(segundosRestantes), null);
        Assert.Equal(minutos, u.MinutosDeEspera(Agora));
    }

    [Fact]
    public void Um_minuto_no_singular()
    {
        var u = Novo().ComTentativas(5, Agora.AddSeconds(30), null);
        var erro = Assert.Throws<UsuarioBloqueadoTemporariamente>(() => u.GarantirQuePodeEntrar(Agora));
        Assert.Equal("Muitas tentativas. Tente de novo em 1 minuto.", erro.Message);
    }

    [Fact]
    public void Espera_vencida_libera_sem_zerar_contador()
    {
        var u = Novo().ComTentativas(5, Agora.AddMinutes(-1), null);
        u.GarantirQuePodeEntrar(Agora);
        Assert.Equal(5, u.TentativasFalhas);
    }

    [Fact]
    public void Vigesima_falha_nao_marca_espera_porque_o_bloqueio_ja_e_definitivo()
    {
        var u = Novo().ComTentativas(19, null, null);
        u.RegistrarFalha(Agora);
        Assert.True(u.BloqueadoEmDefinitivo);
        Assert.Null(u.BloqueadoAte);
    }

    [Fact]
    public void Sucesso_zera_tentativas_e_marca_acesso()
    {
        var u = Novo().ComTentativas(3, Agora.AddMinutes(5), null);
        u.RegistrarSucesso(Agora);
        Assert.Equal(0, u.TentativasFalhas);
        Assert.Null(u.BloqueadoAte);
        Assert.Equal(Agora, u.UltimoAcesso);
    }

    [Fact]
    public void So_enxerga_empresa_alocada() =>
        Assert.Equal([true, false], new[] { 3, 4 }.Select(Novo(empresas: [3]).EnxergaEmpresa));

    [Fact]
    public void Sem_alocacao_nao_enxerga_nada() => Assert.False(Novo().EnxergaEmpresa(1));

    [Theory]
    [InlineData(Papel.Gestor)]
    [InlineData(Papel.Dev)]
    public void Gestor_e_dev_sem_alocacao_enxergam_tudo(Papel papel) => Assert.True(Novo(papel).EnxergaEmpresa(99));

    [Fact]
    public void So_o_dev_acessa_por_excecao()
    {
        Assert.True(Novo(Papel.Dev).AcessaPorExcecao(99));
        Assert.False(Novo(Papel.Dev, empresas: [99]).AcessaPorExcecao(99));
        Assert.False(Novo(Papel.Gestor).AcessaPorExcecao(99));
    }

    [Fact]
    public void Capacidades_por_papel()
    {
        Assert.Equal([Papel.Dev, Papel.Gestor], Enum.GetValues<Papel>().Where(p => p.AdministraUsuarios()));
        Assert.Equal([Papel.Dev, Papel.Gestor, Papel.Analista, Papel.Revisor],
            Enum.GetValues<Papel>().Where(p => p.PodeEscrever()));
        Assert.Equal([Papel.Gestor], Enum.GetValues<Papel>().Where(p => p.ContaComoGestor()));
    }

    [Fact]
    public void Cargos_de_gestao() =>
        Assert.Equal([Cargo.Diretor, Cargo.Gerente, Cargo.Coordenador], Enum.GetValues<Cargo>().Where(c => c.EDeGestao()));

    [Theory]
    [InlineData("gestor", true)]
    [InlineData("estagiario", false)]
    [InlineData("Gestor", false)]   // o banco grava minúsculo; outra grafia é valor desconhecido
    [InlineData("1", false)]
    [InlineData(null, false)]
    public void Texto_do_papel_e_o_mesmo_do_python(string? texto, bool valido) =>
        Assert.Equal(valido, TextoDeAcesso.TentarPapel(texto, out _));

    [Fact]
    public void Senha_provisoria_pede_troca() =>
        Assert.True(new Usuario { Id = 1, NomeDeUsuario = "a", Email = "a@b.cc", NomeExibicao = "A",
            Papel = Papel.Leitura, SenhaProvisoria = true }.PrecisaTrocarSenha);
}
