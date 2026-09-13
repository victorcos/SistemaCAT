using Cat.Dominio.Acesso;

namespace Cat.Dominio.Testes;

/// <summary>Portados de tests/unidade/test_usuario.py (política e identificadores).</summary>
public sealed class PoliticaTestes
{
    [Theory]
    [InlineData("Sistema2026cat")]
    [InlineData("Xyz12345678A")]
    [InlineData("Açúcar2026ção")]
    public void Aceita_senha_boa(string senha) => PoliticaDeAcesso.ValidarSenha(senha);

    [Theory]
    [InlineData("Curta1A", "10 caracteres")]
    [InlineData("tudominusculo1", "maiúsculas")]
    [InlineData("TUDOMAIUSCULO1", "maiúsculas")]
    [InlineData("SemNumeroAqui", "número")]
    [InlineData(" ComEspaco123 ", "espaço")]
    public void Recusa_senha_ruim_com_a_mensagem_do_python(string senha, string pedaco)
    {
        var erro = Assert.Throws<SenhaFraca>(() => PoliticaDeAcesso.ValidarSenha(senha));
        Assert.Contains(pedaco, erro.Message);
    }

    [Fact]
    public void Tamanho_conta_caracteres_e_nao_unidades_utf16()
    {
        // 9 caracteres com um emoji (2 unidades UTF-16): curta para o Python, curta aqui
        var erro = Assert.Throws<SenhaFraca>(() => PoliticaDeAcesso.ValidarSenha("Abcdef1🎉x"[..10]));
        Assert.Contains("10 caracteres", erro.Message);
    }

    [Fact]
    public void Normaliza_usuario() => Assert.Equal("ana.silva", PoliticaDeAcesso.ValidarNomeDeUsuario("  Ana.Silva  "));

    [Theory]
    [InlineData("ab")]
    [InlineData("com espaco")]
    [InlineData("acento_ç")]
    [InlineData("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")]   // 41
    public void Recusa_usuario_invalido(string nome) =>
        Assert.Throws<DadoInvalido>(() => PoliticaDeAcesso.ValidarNomeDeUsuario(nome));

    [Fact]
    public void Normaliza_email() => Assert.Equal("ana@bms.com", PoliticaDeAcesso.ValidarEmail("  Ana@BMS.com  "));

    [Theory]
    [InlineData("sem-arroba")]
    [InlineData("a@b")]
    [InlineData("@b.com")]
    [InlineData("a@b.c")]
    public void Recusa_email_invalido(string email)
    {
        var erro = Assert.Throws<DadoInvalido>(() => PoliticaDeAcesso.ValidarEmail(email));
        Assert.Equal("E-mail inválido.", erro.Message);
    }

    [Fact]
    public void Nome_de_exibicao_vazio_e_recusado() =>
        Assert.Throws<DadoInvalido>(() => PoliticaDeAcesso.ValidarNomeDeExibicao("   "));

    [Fact]
    public void Senha_provisoria_passa_na_politica_e_nao_tem_caractere_ambiguo()
    {
        var senhas = Enumerable.Range(0, 200).Select(_ => PoliticaDeAcesso.GerarSenhaProvisoria()).ToList();

        Assert.All(senhas, s =>
        {
            Assert.Equal(14, s.Length);
            PoliticaDeAcesso.ValidarSenha(s);
            // quem recebe digita lendo de um bilhete: sem l, 1, I, O, 0 (o alfabeto do Python)
            Assert.DoesNotContain(s, c => "l1IO0".Contains(c));
        });
        Assert.Equal(senhas.Count, senhas.Distinct().Count());
    }

    [Theory]
    [InlineData(3, false)]
    [InlineData(2, true)]
    [InlineData(0, true)]
    public void Minimo_de_tres_gestores(int restantes, bool recusa)
    {
        Assert.Equal(3, PoliticaDeAcesso.MinimoDeGestores);
        var erro = Record.Exception(() => PoliticaDeAcesso.GarantirMinimoDeGestores(restantes));
        Assert.Equal(recusa, erro is UltimoGestor);
    }

    [Fact]
    public void Bloqueado_cobre_as_duas_formas()
    {
        var agora = DateTimeOffset.UtcNow;
        Usuario Com(int falhas, DateTimeOffset? ate) => new Usuario
            { Id = 1, NomeDeUsuario = "a", Email = "a@b.cc", NomeExibicao = "A", Papel = Papel.Leitura }
            .ComTentativas(falhas, ate, null);

        Assert.False(Com(3, null).Bloqueado(agora));
        Assert.True(Com(5, agora.AddMinutes(10)).Bloqueado(agora));
        Assert.False(Com(5, agora.AddMinutes(-1)).Bloqueado(agora));
        Assert.True(Com(20, null).Bloqueado(agora));
    }
}
