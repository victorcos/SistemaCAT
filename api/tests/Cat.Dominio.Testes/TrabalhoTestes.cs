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
    // o roteiro de ICMS é o do sistema inteiro até 22/09/2026, e é o que estes
    // casos descrevem; o de cada módulo tem teste próprio em RoteiroPorModuloTestes
    private static IReadOnlyList<EtapaDoProjeto> Montar(string[] concluidas, string? emAndamento = null) =>
        Etapas.Montar("icms", concluidas.ToHashSet(), emAndamento);

    private static SituacaoEtapa Situacao(IReadOnlyList<EtapaDoProjeto> e, string chave) =>
        e.Single(x => x.Definicao.Chave == chave).Situacao;

    /// <summary>Quantas etapas do módulo entram no progresso: construídas e que concluem.</summary>
    private static int QuantasContam(string modulo) =>
        Etapas.Do(modulo).Count(d => d.Implementada && d.Conta);

    [Fact]
    public void Projeto_novo_tem_tudo_pendente_e_nada_barrado()
    {
        // até 23/09/2026 as sete seguintes saíam "bloqueadas". A ordem do
        // manual continua real — não se monta razão sem movimentos —, mas quem
        // a cobra é o servidor, com a frase que explica o que falta. Aba
        // apagada não explica nada.
        var e = Montar([]);
        Assert.All(e, x => Assert.Equal(SituacaoEtapa.Pendente, x.Situacao));
        Assert.All(e, x => Assert.True(x.Acessivel));
        // o denominador sai das frentes do módulo, e não de um número escrito
        // aqui: ele muda toda vez que uma frente nova entra, e congelá-lo faz
        // este teste quebrar por acerto do sistema, não por defeito
        Assert.Equal((0, QuantasContam("icms")), Etapas.Progresso(e));
    }

    [Fact]
    public void Com_base_a_conferencia_libera()
    {
        var e = Montar(["importar"]);
        Assert.Equal(SituacaoEtapa.Concluida, Situacao(e, "importar"));
        Assert.Equal(SituacaoEtapa.Pendente, Situacao(e, "conferencia"));
        Assert.Equal(SituacaoEtapa.Pendente, Situacao(e, "movimentos"));
        Assert.Equal((1, QuantasContam("icms")), Etapas.Progresso(e));
    }

    [Fact]
    public void Em_andamento_aparece_como_tal()
    {
        var e = Montar(["importar"], "conferencia");
        Assert.Equal(SituacaoEtapa.EmAndamento, Situacao(e, "conferencia"));
        Assert.True(e.Single(x => x.Definicao.Chave == "conferencia").Acessivel);
    }

    [Fact]
    public void Concluida_fora_de_ordem_conta_e_o_resto_segue_pendente()
    {
        // movimentos concluídos com a conferência pendente: acontece, e a
        // conta é honesta — uma feita de quantas o módulo tem
        var e = Montar(["movimentos"]);
        Assert.Equal(SituacaoEtapa.Concluida, Situacao(e, "movimentos"));
        Assert.Equal(SituacaoEtapa.Pendente, Situacao(e, "conferencia"));
        Assert.Equal((1, QuantasContam("icms")), Etapas.Progresso(e));
    }

    [Fact]
    public void Ordem_e_textos_iguais_aos_do_python()
    {
        // a paridade com o Python é da CADEIA da CAT 42, não do catálogo nem do
        // roteiro inteiro: desde 22/09/2026 `Todas` guarda também as etapas dos
        // outros módulos, e o roteiro de ICMS ganhou duas coisas que não são do
        // rito — o histórico (consulta, não conta) e o crédito outorgado (conta,
        // mas não depende de nada). A cadeia é o que vem primeiro, na ordem
        Assert.Equal(
            ["importar", "conferencia", "movimentos", "st_suportado", "razao", "apuracao", "arquivo_digital", "entrega"],
            Etapas.Do("icms").Select(e => e.Chave).Take(8));
        Assert.Equal("Ainda não disponível", SituacaoEtapa.NaoDisponivel.Rotulo());
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

/// <summary>
/// Cada módulo tributário percorre o seu roteiro.
///
/// Antes havia uma lista só, e ela era a da CAT 42: um trabalho de PIS/COFINS
/// herdaria sete etapas de ICMS que nunca rodariam, e o cartão diria "0 de 7"
/// para sempre. O que estes testes protegem é isso — e que declarar etapa nova
/// seja uma linha no catálogo e uma chave no roteiro, nada mais.
/// </summary>
public sealed class RoteiroPorModuloTestes
{
    /// <summary>A cadeia da CAT 42: a única ordem que é dependência real.</summary>
    private static readonly string[] CadeiaDaCat42 =
        ["importar", "conferencia", "movimentos", "st_suportado", "razao", "apuracao",
         "arquivo_digital", "entrega"];

    [Fact]
    public void Cada_roteiro_so_cita_etapa_que_existe_no_catalogo()
    {
        // é o que substitui a tabela: o compilador não cobra a chave, o teste cobra
        var conhecidas = Etapas.Todas.Select(d => d.Chave).ToHashSet();
        foreach (var (modulo, chaves) in Etapas.Roteiros)
            Assert.All(chaves, c => Assert.True(conhecidas.Contains(c),
                $"o roteiro de {modulo} cita a etapa '{c}', que não está no catálogo"));
    }

    [Fact]
    public void Todo_roteiro_comeca_por_importar()
    {
        // sem base não há o que apurar, em nenhum tributo
        Assert.All(Etapas.Roteiros.Values, r => Assert.Equal("importar", r[0]));
    }

    [Fact]
    public void O_icms_mantem_o_roteiro_da_cat42()
    {
        var chaves = Etapas.Do("icms").Select(d => d.Chave).ToList();

        Assert.Equal(
            ["importar", "conferencia", "movimentos", "st_suportado", "razao", "apuracao",
             "arquivo_digital", "entrega"],
            chaves.Take(8));
        // o histórico está em todo módulo, e em nenhum conta como trabalho
        Assert.Contains("historico", chaves);
        // o que não é da cadeia fica depois dela e antes do histórico: são as
        // frentes que leem o lote direto e não esperam etapa nenhuma
        Assert.Equal("historico", chaves[^1]);
        var foraDaCadeia = chaves[8..^1];
        Assert.Contains("credito_outorgado", foraDaCadeia);
        Assert.All(foraDaCadeia, c => Assert.DoesNotContain(c, CadeiaDaCat42));
    }

    [Fact]
    public void Toda_trilha_comeca_por_importar()
    {
        // a base é a mesma para todas: quem importou para a CAT 42 já importou
        // para o crédito outorgado, e o card de cada frente conta essa etapa
        Assert.All(Etapas.TrilhasPorModulo.Values.SelectMany(t => t),
            t => Assert.Equal("importar", t.Etapas[0]));
    }

    [Fact]
    public void Toda_etapa_do_roteiro_cabe_numa_trilha()
    {
        // é o que garante que nenhuma etapa fique sem card na tela do trabalho.
        // `importar` e `historico` são de qualquer trabalho, e não de uma frente
        foreach (var (modulo, chaves) in Etapas.Roteiros)
        {
            var nasTrilhas = Etapas.TrilhasDo(modulo).SelectMany(t => t.Etapas).ToHashSet();
            Assert.All(chaves.Where(c => c is not "importar" and not "historico"),
                c => Assert.True(nasTrilhas.Contains(c),
                    $"a etapa '{c}' está no roteiro de {modulo} e em trilha nenhuma"));
        }
    }

    [Fact]
    public void O_roteiro_sai_das_trilhas_e_nao_repete_o_importar()
    {
        foreach (var (modulo, chaves) in Etapas.Roteiros)
        {
            Assert.Equal("importar", chaves[0]);
            Assert.Equal("historico", chaves[^1]);
            // toda trilha começa por importar, e o roteiro o traz uma vez só
            Assert.Single(chaves.Where(c => c == "importar"));
            // e o roteiro é exatamente o que as trilhas dizem, na ordem delas
            var dasTrilhas = Etapas.TrilhasDo(modulo)
                .SelectMany(t => t.Etapas).Where(c => c != "importar").Distinct();
            Assert.Equal(["importar", .. dasTrilhas, "historico"], chaves);
        }
    }

    [Fact]
    public void A_cat42_e_a_primeira_frente_do_icms_e_as_outras_nao_dependem_dela()
    {
        var trilhas = Etapas.TrilhasDo("icms");

        // a cadeia inteira mora numa trilha só, e é ela que tem ordem
        Assert.Equal("cat42", trilhas[0].Chave);
        Assert.Equal(CadeiaDaCat42, trilhas[0].Etapas);
        // as demais leem o lote direto: a base, e a etapa delas. Nenhuma toma
        // emprestada uma etapa da cadeia — se tomasse, dependeria dela
        Assert.All(trilhas.Skip(1), t =>
        {
            Assert.Equal("importar", t.Etapas[0]);
            Assert.All(t.Etapas.Skip(1),
                c => Assert.DoesNotContain(c, CadeiaDaCat42));
        });
        Assert.Contains(trilhas, t => t.Chave == "credito_outorgado");
    }

    [Fact]
    public void Modulo_sem_frente_construida_nao_inventa_nenhuma()
    {
        Assert.Empty(Etapas.TrilhasDo("irpj_csll"));
        Assert.Equal(["importar", "historico"], Etapas.Roteiros["irpj_csll"]);
    }

    [Fact]
    public void O_piscofins_nao_herda_etapa_de_icms()
    {
        var chaves = Etapas.Do("piscofins").Select(d => d.Chave).ToList();
        Assert.DoesNotContain("razao", chaves);
        Assert.DoesNotContain("arquivo_digital", chaves);
        Assert.Contains("quebra_de_sped", chaves);
    }

    [Fact]
    public void Etapa_declarada_e_nao_construida_aparece_como_indisponivel()
    {
        // Em 23/09/2026 a última etapa por fazer ficou pronta, e este teste
        // perdeu o caso real que o exercia. A regra continua valendo, então
        // passou a ser exercida sobre um roteiro dado: amarrá-la à existência
        // de trabalho pendente era perdê-la no dia em que o trabalho acabasse.
        var porFazer = new DefinicaoEtapa("inventada", "Etapa por fazer", "", Implementada: false);
        var roteiro = Etapas.Montar(
            [Etapas.Todas.First(d => d.Chave == "importar"), porFazer],
            new HashSet<string>());

        Assert.Equal(SituacaoEtapa.NaoDisponivel, roteiro[1].Situacao);
        // e não conta no denominador: só entram as que existem
        Assert.Equal((0, 1), Etapas.Progresso(roteiro));
    }

    [Fact]
    public void A_barra_de_piscofins_tem_as_funcionalidades_na_ordem()
    {
        var roteiro = Etapas.Montar("piscofins", new HashSet<string> { "importar" });

        Assert.Equal(
            ["Arquivos", "Quebras", "Apuração", "Exclusões", "Gestão", "Quebra XML", "Histórico"],
            roteiro.Select(e => e.Definicao.Rotulo));
        // o histórico é consulta: aparece na barra e não entra no denominador
        Assert.False(roteiro.Single(e => e.Definicao.Chave == "historico").Definicao.Conta);
        // o denominador sai do que está construído e conclui, e não de um número
        // aqui: as exclusões entraram em 24/09/2026 e a quebra de XML em
        // 28/09/2026, e cada uma mudou essa conta
        var contam = Etapas.Do("piscofins").Count(d => d.Implementada && d.Conta);
        Assert.Equal((1, contam), Etapas.Progresso(roteiro));
        // nada fica inacessível: o que não existe é que não entra na conta
        Assert.All(roteiro.Where(e => e.Definicao.Implementada), e => Assert.True(e.Acessivel));
    }

    [Fact]
    public void Quebrar_sped_e_apurar_piscofins_sao_funcionalidades_distintas()
    {
        // eu as tinha empacotado na mesma etapa porque as portei no mesmo dia.
        // A quebra abre os arquivos; a apuração confronta a 037 com o razão da
        // ECD. Ver DECISOES de 23/09/2026.
        var chaves = Etapas.Do("piscofins").Select(d => d.Chave).ToList();

        Assert.Contains("quebra_de_sped", chaves);
        Assert.Contains("apuracao_piscofins", chaves);
        Assert.NotEqual(
            chaves.IndexOf("quebra_de_sped"), chaves.IndexOf("apuracao_piscofins"));
    }

    [Fact]
    public void A_quebra_de_sped_abre_sem_esperar_a_importacao()
    {
        // e quem recusa, se não houver SPED no lote, é o motor — com a frase
        // que diz onde importar
        var roteiro = Etapas.Montar("piscofins", new HashSet<string>());
        var quebra = roteiro.Single(e => e.Definicao.Chave == "quebra_de_sped");

        Assert.True(quebra.Definicao.Implementada);
        Assert.Equal(SituacaoEtapa.Pendente, quebra.Situacao);
        Assert.True(quebra.Acessivel);
    }

    [Fact]
    public void Modulo_desconhecido_cai_no_de_icms()
    {
        // trabalho anterior à divisão por módulo: errar para o lado do que funciona
        Assert.Equal(Etapas.Do("icms").Count, Etapas.Do("").Count);
        Assert.Equal(Etapas.Do("icms").Count, Etapas.Do(null).Count);
        Assert.Equal(Etapas.Do("icms").Count, Etapas.Do("inventado").Count);
    }

    [Fact]
    public void O_de_processamento_e_a_uniao_dos_roteiros_sem_importar()
    {
        Assert.DoesNotContain("importar", Etapas.DeProcessamento);
        Assert.Contains("razao", Etapas.DeProcessamento);
        Assert.Contains("quebra_de_sped", Etapas.DeProcessamento);
        // sem repetição: "importar" está em todos os roteiros, os outros podem se repetir
        Assert.Equal(Etapas.DeProcessamento.Count, Etapas.DeProcessamento.Distinct().Count());
    }
}
