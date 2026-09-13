using System.Text.RegularExpressions;
using Cat.Infraestrutura.Auth;
using Microsoft.Extensions.Configuration;
using Npgsql;
using Ferramenta = Cat.Ferramentas.Ferramentas;

namespace Cat.Api.Testes;

/// <summary>
/// semear e emergência, portados de cli/semear.py e cli/emergencia.py.
/// Num banco próprio e vazio: semear só faz algo onde não há usuário.
/// </summary>
public sealed class FerramentasTestes(BancoVazio banco) : IClassFixture<BancoVazio>
{
    private IConfiguration Config(string? url = null) => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CAT_RAIZ_BACKEND"] = RaizDoRepositorio.Backend(),
            // arquivo que não existe: os testes nunca leem o .env real da máquina
            ["CAT_ENV_ARQUIVO"] = Path.Combine(Path.GetTempPath(), "cat-sem-env-" + Guid.NewGuid().ToString("N")),
            ["CAT_BANCO_URL"] = url ?? banco.Url,
            ["CAT_SENHA_PIMENTA"] = BancoDeTeste.Pimenta,
            ["CAT_LOG_NIVEL"] = "ERROR",
        }).Build();

    private async Task<(int Codigo, string Saida)> Rodar(params string[] args)
    {
        var saida = new StringWriter();
        var codigo = await Ferramenta.Executar(args, Config(), saida);
        return (codigo, saida.ToString());
    }

    private async Task<bool> SenhaConfere(string usuario, string senha) =>
        new SenhasArgon2(BancoDeTeste.Pimenta).Conferir(senha,
            await banco.Escalar<string>($"SELECT senha_hash FROM usuario WHERE usuario = '{usuario}'"));

    [Fact]
    public async Task Sem_comando_conhecido_mostra_a_ajuda_e_sai_com_2()
    {
        var (codigo, saida) = await Rodar("emergencia", "apagar-tudo");

        Assert.Equal(2, codigo);
        Assert.Contains("emergencia redefinir <usuario>", saida);
    }

    /// <summary>
    /// Um fluxo só, em ordem, porque cada passo depende do anterior: o semear
    /// cria quem a emergência vai redefinir, desbloquear e promover.
    /// </summary>
    [Fact]
    public async Task Semear_e_saida_de_emergencia_de_ponta_a_ponta()
    {
        // ---- semear num banco vazio
        var (codigo, saida) = await Rodar("semear");
        Assert.Equal(0, codigo);
        Assert.Contains("Três gestores criados", saida);
        var senhas = Regex.Matches(saida, @"^\s+(diretor|gerente|coordenador)\s+\S+\s+(\S{14})\s*$", RegexOptions.Multiline)
            .ToDictionary(m => m.Groups[1].Value, m => m.Groups[2].Value);
        Assert.Equal(3, senhas.Count);
        foreach (var (usuario, senha) in senhas)
            Assert.True(await SenhaConfere(usuario, senha), $"a senha impressa para {usuario} não confere");
        Assert.Equal(3, await banco.Escalar<long>("SELECT count(*) FROM usuario WHERE papel = 'gestor' AND ativo AND senha_provisoria"));
        Assert.Equal("Empresa de exemplo", await banco.Escalar<string>("SELECT razao_social FROM empresa WHERE cnpj_raiz = '00000000'"));
        Assert.Equal(3, await banco.Escalar<long>("SELECT count(*) FROM alocacao WHERE papel_projeto = 'responsavel' AND fim IS NULL"));

        // ---- de novo não faz nada
        (codigo, saida) = await Rodar("semear");
        Assert.Equal(0, codigo);
        Assert.Contains("Já existe usuário. Nada foi feito.", saida);
        Assert.Equal(3, await banco.Escalar<long>("SELECT count(*) FROM usuario"));

        // ---- listar
        (codigo, saida) = await Rodar("emergencia", "listar-gestores");
        Assert.Equal(0, codigo);
        Assert.Contains("Gestores ativos: 3", saida);

        // ---- redefinir também desbloqueia
        await banco.Comando("UPDATE usuario SET tentativas_falhas = 20 WHERE usuario = 'gerente'");
        (_, saida) = await Rodar("emergencia", "listar-gestores");
        Assert.Contains("[bloqueado]", saida);
        (codigo, saida) = await Rodar("emergencia", "redefinir", "gerente");
        Assert.Equal(0, codigo);
        var nova = Regex.Match(saida, @"Senha \.+ (\S+)").Groups[1].Value;
        Assert.True(await SenhaConfere("gerente", nova));
        Assert.Equal(0, await banco.Escalar<int>("SELECT tentativas_falhas FROM usuario WHERE usuario = 'gerente'"));
        Assert.False(await SenhaConfere("gerente", senhas["gerente"]));

        // ---- desbloquear
        await banco.Comando("UPDATE usuario SET tentativas_falhas = 7 WHERE usuario = 'diretor'");
        (codigo, _) = await Rodar("emergencia", "desbloquear", "diretor");
        Assert.Equal(0, codigo);
        Assert.Equal(0, await banco.Escalar<int>("SELECT tentativas_falhas FROM usuario WHERE usuario = 'diretor'"));

        // ---- criar-dev, recusando repetido e e-mail inválido
        (codigo, saida) = await Rodar("emergencia", "criar-dev", "Manutencao", "Manut@BMS.local", "Manutenção");
        Assert.Equal(0, codigo);
        Assert.Contains("Papel dev", saida);
        Assert.Equal("dev", await banco.Escalar<string>("SELECT papel FROM usuario WHERE usuario = 'manutencao'"));
        (codigo, saida) = await Rodar("emergencia", "criar-dev", "manutencao", "outro@bms.local", "X");
        Assert.Equal(1, codigo);
        Assert.Contains("Já existe usuário 'manutencao'", saida);
        (codigo, saida) = await Rodar("emergencia", "criar-dev", "outro.dev", "sem-arroba", "X");
        Assert.Equal(1, codigo);
        Assert.Contains("E-mail inválido.", saida);

        // ---- promover reativa e faz gestor
        await banco.Comando("UPDATE usuario SET ativo = false WHERE usuario = 'manutencao'");
        (codigo, _) = await Rodar("emergencia", "promover", "manutencao");
        Assert.Equal(0, codigo);
        Assert.True(await banco.Escalar<bool>("SELECT papel = 'gestor' AND ativo FROM usuario WHERE usuario = 'manutencao'"));

        // ---- quem não existe
        (codigo, saida) = await Rodar("emergencia", "redefinir", "fantasma");
        Assert.Equal(1, codigo);
        Assert.Contains("Usuário 'fantasma' não encontrado.", saida);
    }

    [Fact]
    public async Task Banco_sem_esquema_manda_rodar_as_migracoes_em_vez_de_criar_tabela()
    {
        const string nome = "cat_testes_csharp_sem_esquema";
        await using (var admin = new NpgsqlConnection("Host=127.0.0.1;Port=55432;Username=cat;Password=cat;Database=postgres"))
        {
            await admin.OpenAsync();
            await new NpgsqlCommand($"DROP DATABASE IF EXISTS {nome} WITH (FORCE)", admin).ExecuteNonQueryAsync();
            await new NpgsqlCommand($"CREATE DATABASE {nome}", admin).ExecuteNonQueryAsync();
        }

        var saida = new StringWriter();
        var codigo = await Ferramenta.Executar(["emergencia", "listar-gestores"],
            Config($"postgresql+psycopg://cat:cat@127.0.0.1:55432/{nome}"), saida);

        Assert.Equal(1, codigo);
        Assert.Contains("alembic upgrade head", saida.ToString());
    }
}
