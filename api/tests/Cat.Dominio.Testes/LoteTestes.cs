using Cat.Dominio.Lote;

namespace Cat.Dominio.Testes;

public sealed class TiposDeArquivoTestes
{
    [Fact]
    public void So_sete_tipos_alimentam_a_cat() =>
        Assert.Equal(["sped_icms_ipi", "xml_nfe", "xml_cancelamento", "xml_compactado", "gerencial_movimento",
                "gerencial_inventario", "lista_de_canceladas"],
            TiposDeArquivo.Todos.Where(t => t.AlimentaACat).Select(t => t.Valor));

    [Theory]
    [InlineData("sped_contribuicoes", "sped", "EFD Contribuições")]
    [InlineData("xml_outro", "xml", "XML de outro documento")]
    [InlineData("gerencial_resumo", "gerencial", "Resumo por produto")]
    [InlineData("compactado", "compactado", "Compactado")]
    [InlineData("nao_baixado", "outro", "Não baixado do OneDrive")]
    public void Grupo_e_rotulo(string valor, string grupo, string rotulo)
    {
        var t = TiposDeArquivo.Buscar(valor);
        Assert.Equal(grupo, t.Grupo);
        Assert.Equal(rotulo, t.Rotulo);
    }

    [Fact]
    public void Tipo_que_o_motor_criar_depois_aparece_como_nao_reconhecido()
    {
        var t = TiposDeArquivo.Buscar("sped_do_futuro");
        Assert.Equal("desconhecido", t.Valor);
        Assert.False(t.AlimentaACat);
    }
}
