using Cat.Dominio.Projeto;

namespace Cat.Dominio.Testes;

public class CadastroDoTrabalhoTestes
{
    private static readonly DateOnly Jan = new(2021, 1, 1);
    private static readonly DateOnly Dez = new(2021, 12, 31);

    [Fact]
    public void Competencia_e_mes_o_dia_do_cadastro_nao_conta()
    {
        Assert.False(CadastroDoTrabalho.ForaDoPeriodo(new DateOnly(2021, 12, 1), Jan, new DateOnly(2021, 12, 10)));
        Assert.True(CadastroDoTrabalho.ForaDoPeriodo(new DateOnly(2020, 12, 1), Jan, Dez));
        Assert.True(CadastroDoTrabalho.ForaDoPeriodo(new DateOnly(2022, 1, 1), Jan, Dez));
    }

    [Fact]
    public void Resumo_da_base_soma_as_efd_fora_do_periodo()
    {
        var b = CadastroDoTrabalho.Resumir(
            [(new DateOnly(2021, 1, 1), 70), (new DateOnly(2021, 2, 1), 72), (new DateOnly(2025, 1, 1), 3)],
            new DateOnly(2025, 1, 1), new DateOnly(2025, 12, 31));
        Assert.Equal(new BaseDoTrabalho(145, new DateOnly(2021, 1, 1), new DateOnly(2025, 1, 1), 142), b);
        Assert.Equal(new BaseDoTrabalho(0, null, null, 0), CadastroDoTrabalho.Resumir([], Jan, Dez));
    }

    [Fact]
    public void Frase_diz_so_o_que_mudou()
    {
        Assert.Equal("Cadastro do trabalho: nome «A» → «B»",
            CadastroDoTrabalho.Frase("A", Jan, Dez, "B", Jan, Dez));
        Assert.Equal("Cadastro do trabalho: período 01/2025 a 12/2025 → 01/2021 a 12/2021",
            CadastroDoTrabalho.Frase("A", new DateOnly(2025, 1, 1), new DateOnly(2025, 12, 31), "A", Jan, Dez));
    }
}
