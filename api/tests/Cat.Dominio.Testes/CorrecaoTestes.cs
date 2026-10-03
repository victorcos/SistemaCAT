using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Dominio.Testes;

/// <summary>
/// A correção à mão na porta de entrada. A mesma regra roda no motor
/// (<c>cat/dominio/cat42/correcao.py</c>), e os números têm de ser os mesmos:
/// o que passa aqui tem de ser aplicável lá.
/// </summary>
public class CorrecaoTestes
{
    [Fact]
    public void Correcao_de_mercadoria_sai_limpa()
    {
        var c = Correcao.Validar("aliquota", " 25 ", "  Sem 0200; NCM 3305.90.00, art. 55, IV  ",
            " 44000001000454 ", " 4002 ", null, null, "18");
        Assert.Equal("aliquota", c.Campo);
        Assert.Equal("25.0000", c.Valor);
        Assert.Equal("4002", c.Codigo);
        Assert.Equal("Sem 0200; NCM 3305.90.00, art. 55, IV", c.Motivo);
        Assert.Equal("mercadoria 4002", c.Onde);
    }

    [Fact]
    public void Correcao_de_mercadoria_ignora_documento_e_item()
    {
        var c = Correcao.Validar("reducao_base", "48", "benefício do art. 34", null, "4002",
            new string('3', 44), 2, null);
        Assert.Equal("", c.Documento);
        Assert.Null(c.NumeroItem);
        Assert.Equal("48.0000", c.Valor);
    }

    [Fact]
    public void Correcao_de_linha_exige_documento_e_item()
    {
        var c = Correcao.Validar("enquadramento", "1", "consumidor confirmado pelo cliente", null, null,
            new string('3', 44), 2, "indefinido");
        Assert.Equal("1", c.Valor);
        Assert.Equal("documento …333333, item 2", c.Onde);
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("enquadramento", "1", "motivo bom", null, null, null, 2, null));
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("enquadramento", "1", "motivo bom", null, null, "3", null, null));
    }

    [Fact]
    public void O_historico_mostra_o_antes_e_o_depois()
    {
        var c = Correcao.Validar("aliquota", "25", "Sem 0200; NCM 3305.90.00", null, "4002", null, null, "18.0000");
        Assert.Equal("Alíquota interna (mercadoria 4002): 18.0000 → 25.0000", c.Frase);
        var sem = Correcao.Validar("aliquota", "25", "motivo bom", null, "4002", null, null, null);
        Assert.EndsWith("(vazio) → 25.0000", sem.Frase);
    }

    [Theory]
    [InlineData("sim", "sim")]
    [InlineData("SIM", "sim")]
    [InlineData("x", "sim")]
    [InlineData("não", "nao")]
    [InlineData("", "nao")]
    public void Fora_da_ficha_entende_o_que_a_planilha_escreve(string escrito, string gravado)
    {
        var c = Correcao.Validar("excluida", escrito, "cancelada na SEFAZ, fora da lista", null, null,
            new string('3', 44), 1, null);
        Assert.Equal(gravado, c.Valor);
    }

    [Theory]
    [InlineData("aliquota", "0")]
    [InlineData("aliquota", "101")]
    [InlineData("aliquota", "abc")]
    [InlineData("reducao_base", "100")]
    [InlineData("reducao_base", "-1")]
    [InlineData("enquadramento", "5")]
    [InlineData("enquadramento", "1.5")]
    [InlineData("quantidade", "0")]
    [InlineData("quantidade", "-3")]
    [InlineData("valor_item", "-0.01")]
    [InlineData("icms_suportado", "-1")]
    [InlineData("excluida", "talvez")]
    public void Recusa_o_que_nao_faz_sentido(string campo, string valor)
    {
        Assert.Throws<DadoInvalido>(() => Correcao.Validar(campo, valor, "motivo suficiente", null, "4002",
            new string('3', 44), 1, null));
    }

    [Fact]
    public void Sem_motivo_nao_grava()
    {
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("aliquota", "25", "", null, "4002", null, null, null));
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("aliquota", "25", "x", null, "4002", null, null, null));
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("aliquota", "25", new string('a', 501), null, "4002", null, null, null));
    }

    [Fact]
    public void Campo_desconhecido_e_cnpj_torto_sao_recusados()
    {
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("aliquota_st", "25", "motivo bom", null, "X", null, null, null));
        Assert.Throws<DadoInvalido>(() => Correcao.Validar("aliquota", "25", "motivo bom", "123", "X", null, null, null));
    }

    [Fact]
    public void A_virgula_decimal_da_planilha_e_aceita()
    {
        Assert.Equal("13.3000", Correcao.Validar("aliquota", "13,3", "redutor do Decreto 65.255", null, "X", null, null, null).Valor);
        Assert.Equal("2.500000", Correcao.Validar("quantidade", "2,5", "pesável", null, null, "7", 1, null).Valor);
    }

    [Fact]
    public void Os_campos_dizem_o_alvo_e_o_rotulo()
    {
        Assert.True(Correcao.EhDaMercadoria("aliquota"));
        Assert.False(Correcao.EhDaMercadoria("quantidade"));
        Assert.Equal(7, Correcao.Campos.Count);
        Assert.All(Correcao.Campos, c => Assert.NotEqual(c, Correcao.Rotulo(c)));
    }
}
