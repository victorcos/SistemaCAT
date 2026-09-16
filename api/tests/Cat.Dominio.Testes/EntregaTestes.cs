using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Dominio.Testes;

/// <summary>A aprovação da etapa 8: quem aprova e o que a entrega precisa estar.</summary>
public class EntregaTestes
{
    private static readonly DefinicaoDeStatus EmAndamento = StatusDoProjeto.DoBanco(StatusDoProjeto.EmAndamento);

    private static EntregaParaAprovar Pronta(int id = 9) =>
        new(id, "concluida", null, null, UltimaEntrega: id, ArquivoDigitalUsado: 51, UltimoArquivoDigital: 51, EmAndamento);

    [Theory]
    [InlineData(Papel.Revisor, true)]
    [InlineData(Papel.Gestor, true)]
    [InlineData(Papel.Analista, false)]
    [InlineData(Papel.Leitura, false)]
    [InlineData(Papel.Dev, false)]
    public void Aprova_quem_responde_pelo_que_sai(Papel papel, bool pode) =>
        Assert.Equal(pode, papel.PodeAprovarEntrega());

    [Fact]
    public void Entrega_montada_mais_recente_e_do_ultimo_arquivo_digital_aprova() =>
        Entrega.ValidarAprovacao(Pronta());

    [Fact]
    public void Rodada_que_nao_concluiu_nao_aprova() =>
        Assert.Throws<EntregaNaoMontada>(() => Entrega.ValidarAprovacao(Pronta() with { Situacao = "falhou" }));

    [Fact]
    public void Aprovada_nao_se_aprova_de_novo()
    {
        var erro = Assert.Throws<EntregaJaAprovada>(() => Entrega.ValidarAprovacao(
            Pronta() with { AprovadaEm = DateTimeOffset.UtcNow, AprovadaPor = "Revisora" }));
        Assert.Contains("por Revisora", erro.Message);
    }

    [Fact]
    public void Entrega_superada_por_outra_mais_nova_nao_aprova()
    {
        var erro = Assert.Throws<EntregaSuperada>(() => Entrega.ValidarAprovacao(Pronta() with { UltimaEntrega = 12 }));
        Assert.Contains("#12", erro.Message);
    }

    [Fact]
    public void Arquivo_digital_gerado_de_novo_depois_da_entrega_nao_aprova() =>
        Assert.Throws<EntregaDesatualizada>(() => Entrega.ValidarAprovacao(Pronta() with { UltimoArquivoDigital = 60 }));

    [Fact]
    public void Trabalho_pausado_nao_aprova() =>
        Assert.Throws<TrabalhoParadoNaoEntrega>(() => Entrega.ValidarAprovacao(
            Pronta() with { StatusDoTrabalho = StatusDoProjeto.DoBanco(StatusDoProjeto.Pausado) }));

    [Fact]
    public void Observacao_vazia_e_nenhuma_e_longa_demais_e_recusa()
    {
        Assert.Null(Entrega.ValidarObservacao("   "));
        Assert.Equal("Conferido com o cliente", Entrega.ValidarObservacao("  Conferido com o cliente "));
        Assert.Throws<ObservacaoDaEntregaLongaDemais>(() => Entrega.ValidarObservacao(new string('x', 501)));
    }
}
