using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Dominio.Testes;

public class DeParaTestes
{
    [Fact]
    public void Decisao_valida_sai_limpa()
    {
        var d = DePara.Validar(" 43112531000421 ", " 1111K308 ", "1111", "3", "kit", "aprovado", "alta", "  kit de 3  ");
        Assert.Equal(new DecisaoDeDePara("43112531000421", "1111K308", "1111", 3m, "kit", "aprovado", "alta", "kit de 3"), d);
        // sem CNPJ vale para a empresa inteira; sem fator é 1
        Assert.Equal("", DePara.Validar(null, "A", "B", null, "cliente", "recusado", null, null).Cnpj);
        Assert.Equal(1m, DePara.Validar(null, "A", "B", null, "cliente", "recusado", null, null).Fator);
        Assert.Equal(0.5m, DePara.Validar(null, "A", "B", "0.5", "analista", "aprovado", null, null).Fator);
    }

    [Theory]
    [InlineData("123", "A", "B", "1", "gtin", "aprovado", null)]
    [InlineData("", "", "B", "1", "gtin", "aprovado", null)]
    [InlineData("", "A", "A", "1", "gtin", "aprovado", null)]
    [InlineData("", "A", "B", "0", "gtin", "aprovado", null)]
    [InlineData("", "A", "B", "-2", "gtin", "aprovado", null)]
    [InlineData("", "A", "B", "três", "gtin", "aprovado", null)]
    [InlineData("", "A", "B", "1", "chute", "aprovado", null)]
    [InlineData("", "A", "B", "1", "gtin", "talvez", null)]
    [InlineData("", "A", "B", "1", "gtin", "aprovado", "baixa")]
    public void Recusa_o_que_nao_faz_sentido(string cnpj, string origem, string destino, string fator, string motivo,
        string situacao, string? confianca)
    {
        Assert.Throws<DadoInvalido>(() => DePara.Validar(cnpj, origem, destino, fator, motivo, situacao, confianca, null));
    }

    [Fact]
    public void Codigo_longo_demais_e_recusado_e_explicacao_longa_e_cortada()
    {
        Assert.Throws<DadoInvalido>(() => DePara.Validar("", new string('9', 61), "B", "1", "gtin", "aprovado", null, null));
        var d = DePara.Validar("", "A", "B", "1", "gtin", "aprovado", null, new string('x', 900));
        Assert.Equal(DePara.TamanhoMaximoDaExplicacao, d.Explicacao!.Length);
    }

    [Fact]
    public void Frase_conta_aprovados_e_recusados()
    {
        var a = DePara.Validar("", "A", "B", "1", "gtin", "aprovado", null, null);
        var r = DePara.Validar("", "C", "D", "1", "gtin", "recusado", null, null);
        Assert.Equal("De-para de códigos · 1 par aprovado", DePara.Frase([a]));
        Assert.Equal("De-para de códigos · 2 pares aprovados, 1 par recusado", DePara.Frase([a, a with { Origem = "E" }, r]));
    }
}
