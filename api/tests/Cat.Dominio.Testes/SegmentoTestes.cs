using Cat.Dominio.Acesso;

namespace Cat.Dominio.Testes;

/// <summary>
/// A terceira dimensão de acesso: em que assunto a pessoa trabalha.
///
/// O que estes testes protegem é o que a tela inicial promete — que ninguém veja
/// card de segmento que não pode abrir, e que quem tem um caminho só não seja
/// obrigado a escolher entre uma opção.
/// </summary>
public class SegmentoTestes
{
    private static Usuario Pessoa(Papel papel, params string[] segmentos) => new()
    {
        Id = 1, NomeDeUsuario = "ana", Email = "a@b.cc", NomeExibicao = "Ana",
        Papel = papel, Segmentos = segmentos,
    };

    [Fact]
    public void O_catalogo_casa_a_reforma_com_o_tributo_que_ela_sucede()
    {
        // CBS substitui PIS/COFINS; IBS substitui ICMS/ISS. Trocar os dois de lugar
        // é o erro que sai caro depois de a tela circular com cliente
        Assert.Equal(["piscofins", "cbs"],
            Segmentos.Buscar("piscofins")!.Modulos.Select(m => m.Chave));
        Assert.Equal(["icms", "ibs"], Segmentos.Buscar("icms")!.Modulos.Select(m => m.Chave));
        // IRPJ e CSLL apuram juntos: um módulo só
        Assert.Single(Segmentos.Buscar("irpj_csll")!.Modulos);
    }

    [Theory]
    [InlineData(Papel.Gestor)]
    [InlineData(Papel.Dev)]
    public void Gestor_e_dev_enxergam_tudo_sem_ninguem_liberar(Papel papel)
    {
        var pessoa = Pessoa(papel);
        Assert.Equal(Segmentos.Todos.Count, Segmentos.De(pessoa).Count);
        Assert.True(Segmentos.PodeVer(pessoa, "irpj_csll"));
        Assert.True(Segmentos.Entrada(pessoa).TodosOsSegmentos);
    }

    [Fact]
    public void Quem_nao_e_gestor_so_ve_o_que_foi_liberado()
    {
        var pessoa = Pessoa(Papel.Analista, "piscofins");
        Assert.Equal(["piscofins"], Segmentos.De(pessoa).Select(s => s.Chave));
        Assert.False(Segmentos.PodeVer(pessoa, "icms"));
    }

    [Fact]
    public void Com_um_segmento_de_dois_modulos_a_entrada_e_a_tela_de_modulos()
    {
        var entrada = Segmentos.Entrada(Pessoa(Papel.Analista, "piscofins"));
        Assert.False(entrada.TodosOsSegmentos);
        Assert.Equal("piscofins", entrada.Segmento);
        // dois módulos: ela ainda escolhe entre PIS/COFINS e CBS
        Assert.Null(entrada.Modulo);
    }

    [Fact]
    public void Com_um_segmento_de_um_modulo_so_a_entrada_pula_as_duas_telas()
    {
        var entrada = Segmentos.Entrada(Pessoa(Papel.Revisor, "irpj_csll"));
        Assert.Equal("irpj_csll", entrada.Segmento);
        Assert.Equal("irpj_csll", entrada.Modulo);
    }

    [Fact]
    public void Com_dois_segmentos_a_entrada_e_a_tela_de_segmentos()
    {
        var entrada = Segmentos.Entrada(Pessoa(Papel.Analista, "piscofins", "icms"));
        Assert.True(entrada.TodosOsSegmentos);
        Assert.Null(entrada.Segmento);
    }

    [Fact]
    public void Sem_segmento_nenhum_nao_ha_para_onde_mandar()
    {
        var entrada = Segmentos.Entrada(Pessoa(Papel.Leitura));
        Assert.False(entrada.TodosOsSegmentos);
        Assert.Null(entrada.Segmento);
        Assert.Empty(Segmentos.De(Pessoa(Papel.Leitura)));
    }

    [Fact]
    public void A_limpeza_tira_repetido_ordena_e_recusa_o_que_nao_existe()
    {
        Assert.Equal(["piscofins", "icms"], Segmentos.Limpar(["icms", "piscofins", "ICMS"]));
        Assert.Empty(Segmentos.Limpar(null));
        Assert.Throws<DadoInvalido>(() => Segmentos.Limpar(["piscofins", "iss"]));
    }

    [Fact]
    public void Segmento_que_saiu_da_lista_aparece_pela_chave_em_vez_de_sumir()
    {
        Assert.Equal("aposentado", Segmentos.Rotulo("aposentado"));
        Assert.Equal("PIS/COFINS", Segmentos.Rotulo("piscofins"));
    }
}
