using Cat.Dominio.Acesso;
using Cat.Dominio.Comum;
using Cat.Dominio.Projeto;

namespace Cat.Dominio.Testes;

/// <summary>Portados de tests/unidade/test_cnpj.py e das regras de etapas.py.</summary>
public sealed class CnpjTestes
{
    [Theory]
    [InlineData("11.222.333/0001-81", "11222333000181", "11222333", true)]
    [InlineData("11222333000262", "11222333000262", "11222333", false)]
    public void Aceita_numerico_com_ou_sem_pontuacao(string bruto, string valor, string raiz, bool matriz)
    {
        var c = new Cnpj(bruto);
        Assert.Equal(valor, c.Valor);
        Assert.Equal(raiz, c.Raiz);
        Assert.Equal(matriz, c.EMatriz);
    }

    [Fact]
    public void Aceita_alfanumerico_da_receita_de_2026()
    {
        // exemplo oficial do leiaute alfanumérico: 12ABC34501DE e dígitos 35
        var c = new Cnpj("12.ABC.345/01DE-35");
        Assert.Equal("12ABC34501DE35", c.Valor);
        Assert.Equal("12.ABC.345/01DE-35", c.Formatado);
        Assert.Equal("12ABC345", c.Raiz);
    }

    [Fact]
    public void Minuscula_vira_maiuscula() => Assert.Equal("12ABC34501DE35", new Cnpj("12abc34501de35").Valor);

    [Theory]
    [InlineData("1122233300018", "14 caracteres")]
    [InlineData("11222333000182", "dígito verificador")]
    [InlineData("11111111111111", "sequência repetida")]
    [InlineData("12ABC34501DEAB", "2 últimos só dígito")]
    public void Recusa_com_o_motivo(string bruto, string motivo)
    {
        var erro = Assert.Throws<CnpjInvalido>(() => new Cnpj(bruto));
        Assert.Contains(motivo, erro.Message);
    }

    [Fact]
    public void Tentar_devolve_nada_em_vez_de_derrubar()
    {
        Assert.Null(Cnpj.Tentar("lixo"));
        Assert.Null(Cnpj.Tentar(null));
        Assert.NotNull(Cnpj.Tentar("11222333000181"));
    }
}

public sealed class EtapasTestes
{
    private static IReadOnlyList<EtapaDoProjeto> Montar(string[] concluidas, string? emAndamento = null) =>
        Etapas.Montar(concluidas.ToHashSet(), emAndamento);

    private static SituacaoEtapa Situacao(IReadOnlyList<EtapaDoProjeto> e, string chave) =>
        e.Single(x => x.Definicao.Chave == chave).Situacao;

    [Fact]
    public void Projeto_novo_so_tem_importar_pendente()
    {
        var e = Montar([]);
        Assert.Equal(SituacaoEtapa.Pendente, Situacao(e, "importar"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "conferencia"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "movimentos"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "st_suportado"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "razao"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "apuracao"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "arquivo_digital"));
        Assert.Equal(SituacaoEtapa.NaoDisponivel, Situacao(e, "entrega"));
        Assert.Equal((0, 7), Etapas.Progresso(e));
    }

    [Fact]
    public void Com_base_a_conferencia_libera()
    {
        var e = Montar(["importar"]);
        Assert.Equal(SituacaoEtapa.Concluida, Situacao(e, "importar"));
        Assert.Equal(SituacaoEtapa.Pendente, Situacao(e, "conferencia"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "movimentos"));
        Assert.Equal((1, 7), Etapas.Progresso(e));
    }

    [Fact]
    public void Em_andamento_aparece_e_nao_libera_a_seguinte()
    {
        var e = Montar(["importar"], "conferencia");
        Assert.Equal(SituacaoEtapa.EmAndamento, Situacao(e, "conferencia"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "movimentos"));
        Assert.True(e.Single(x => x.Definicao.Chave == "conferencia").Acessivel);
        Assert.False(e.Single(x => x.Definicao.Chave == "movimentos").Acessivel);
    }

    [Fact]
    public void Concluida_fora_de_ordem_conta_mas_nao_desbloqueia_o_resto()
    {
        // movimentos concluídos com a conferência pendente: a conta é honesta,
        // o roteiro não pula a dependência
        var e = Montar(["movimentos"]);
        Assert.Equal(SituacaoEtapa.Concluida, Situacao(e, "movimentos"));
        Assert.Equal(SituacaoEtapa.Bloqueada, Situacao(e, "conferencia"));
        Assert.Equal((1, 7), Etapas.Progresso(e));
    }

    [Fact]
    public void Ordem_e_textos_iguais_aos_do_python()
    {
        Assert.Equal(
            ["importar", "conferencia", "movimentos", "st_suportado", "razao", "apuracao", "arquivo_digital", "entrega"],
            Etapas.Todas.Select(e => e.Chave));
        Assert.Equal("Aguardando etapa anterior", SituacaoEtapa.Bloqueada.Rotulo());
        Assert.Equal("nao_disponivel", SituacaoEtapa.NaoDisponivel.Valor());
    }

    [Fact]
    public void Frentes_e_status()
    {
        Assert.Equal(["cat42", "depara", "sped", "notafiscal"], Frentes.Todas.Select(f => f.Key));
        Assert.Equal("chave-antiga", Frentes.Rotulo("chave-antiga"));
        Assert.Equal("Concluído", StatusDoProjeto.Rotulo("concluido"));
        Assert.Equal("inventado", StatusDoProjeto.Rotulo("inventado"));
    }

    [Theory]
    [InlineData(Papel.Dev, true)]
    [InlineData(Papel.Gestor, true)]
    [InlineData(Papel.Analista, false)]
    [InlineData(Papel.Revisor, false)]
    [InlineData(Papel.Leitura, false)]
    public void Quem_escreve_nem_sempre_apaga(Papel papel, bool pode)
    {
        // veio de test_papel_dev.py: analista e revisor escrevem, e não desfazem meses de trabalho
        Assert.Equal(pode, papel.PodeExcluirTrabalho());
        if (papel is Papel.Analista or Papel.Revisor)
            Assert.True(papel.PodeEscrever());
    }
}
