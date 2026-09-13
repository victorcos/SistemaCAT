using Cat.Dominio.Projeto;

namespace Cat.Dominio.Testes;

/// <summary>Portados de tests/unidade/test_historico.py.</summary>
public sealed class HistoricoTestes
{
    private static DefinicaoDeStatus S(string valor) => StatusDoProjeto.Buscar(valor)!;

    [Fact]
    public void Os_quatro_status_que_existem_na_ordem() =>
        Assert.Equal(["em_andamento", "pausado", "cancelado", "concluido"], StatusDoProjeto.Todos.Select(s => s.Valor));

    [Fact]
    public void Trabalho_parado_nao_roda_etapa_e_o_entregue_roda()
    {
        // pausar precisa significar alguma coisa; concluído roda porque refazer
        // uma conferência depois da entrega é o que se faz quando o cliente questiona
        Assert.False(S("pausado").AceitaProcessamento);
        Assert.False(S("cancelado").AceitaProcessamento);
        Assert.True(S("em_andamento").AceitaProcessamento);
        Assert.True(S("concluido").AceitaProcessamento);
    }

    [Fact]
    public void Parar_e_cancelar_exigem_motivo()
    {
        Assert.Equal(["pausado", "cancelado"], StatusDoProjeto.Todos.Where(s => s.ExigeMotivo).Select(s => s.Valor));
    }

    [Fact]
    public void Todo_status_tem_rotulo_e_explicacao()
    {
        Assert.All(StatusDoProjeto.Todos, s =>
        {
            Assert.True(char.IsUpper(s.Rotulo[0]));
            Assert.EndsWith(".", s.Explicacao);
        });
    }

    [Fact]
    public void Status_desconhecido_no_banco_vale_como_em_andamento() =>
        Assert.Equal("em_andamento", StatusDoProjeto.DoBanco("arquivado").Valor);

    [Fact]
    public void Comentario_apara_espaco_e_recusa_vazio()
    {
        Assert.Equal("falei com o cliente", Historico.ValidarComentario("  falei com o cliente  "));
        Assert.Throws<ComentarioVazio>(() => Historico.ValidarComentario("   \n  "));
    }

    [Fact]
    public void Comentario_no_limite_entra_e_passando_nao()
    {
        var limite = new string('a', Historico.TamanhoMaximoDoComentario);
        Assert.Equal(limite, Historico.ValidarComentario(limite));
        Assert.Throws<ComentarioLongoDemais>(() => Historico.ValidarComentario(limite + "a"));
    }

    [Fact]
    public void Mudanca_de_status_recusa_o_mesmo_e_parar_sem_motivo()
    {
        var mesmo = Assert.Throws<MesmoStatus>(() => Historico.ValidarMudancaDeStatus(S("pausado"), S("pausado"), "x"));
        Assert.Equal("O trabalho já está como pausado.", mesmo.Message);
        var semMotivo = Assert.Throws<MotivoObrigatorio>(() => Historico.ValidarMudancaDeStatus(S("em_andamento"), S("cancelado"), "  "));
        Assert.StartsWith("Diga por que o trabalho está sendo cancelado.", semMotivo.Message);
        Historico.ValidarMudancaDeStatus(S("pausado"), S("em_andamento"), "");
    }

    [Fact]
    public void Frases()
    {
        Assert.Equal("Em andamento → Pausado", Historico.FraseDeStatus(S("em_andamento"), S("pausado")));
        Assert.Equal("Ana → Bruno", Historico.FraseDeSucessao("Ana", "Bruno"));
        Assert.Equal("Responsável definido: Bruno", Historico.FraseDeSucessao(null, "Bruno"));
    }

    [Fact]
    public void Tipo_gravado_por_versao_mais_nova_aparece_como_comentario()
    {
        Assert.Equal("etapa_concluida", TipoDeEvento.Conhecido("etapa_concluida"));
        Assert.Equal("comentario", TipoDeEvento.Conhecido("tipo_do_futuro"));
        Assert.Equal("Arquivos importados", TipoDeEvento.Rotulo("lote_importado"));
    }
}
