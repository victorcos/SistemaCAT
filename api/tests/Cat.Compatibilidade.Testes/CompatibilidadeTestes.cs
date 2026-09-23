using System.Diagnostics;
using System.Text.Json;
using Cat.Aplicacao.Acesso;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;
using Microsoft.Extensions.Time.Testing;

namespace Cat.Compatibilidade.Testes;

/// <summary>
/// Os resumos e o token de <c>vetores-python.json</c> foram gravados pelo
/// backend Python. Se o C# não conferir exatamente o mesmo, ninguém entra
/// depois da migração — é o primeiro teste da fatia 1 por isso.
/// </summary>
public sealed class VetoresDoPythonTestes
{
    private static readonly JsonElement Vetores =
        JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "vetores-python.json"))).RootElement;

    public static TheoryData<int> CasosArgon2() => new(Enumerable.Range(0, Vetores.GetProperty("argon2").GetArrayLength()));

    [Theory]
    [MemberData(nameof(CasosArgon2))]
    public void Resumo_argon2_do_python_confere_no_csharp(int caso)
    {
        var v = Vetores.GetProperty("argon2")[caso];
        var senhas = new SenhasArgon2(v.GetProperty("pimenta").GetString()!);
        var resumo = v.GetProperty("resumo").GetString()!;
        var senha = v.GetProperty("senha").GetString()!;

        Assert.True(senhas.Conferir(senha, resumo));
        Assert.False(senhas.Conferir(senha + "x", resumo));
        Assert.False(senhas.PrecisaRegravar(resumo));
    }

    [Fact]
    public void Pimenta_errada_ou_ausente_nao_confere()
    {
        var v = Vetores.GetProperty("argon2")[0];
        var resumo = v.GetProperty("resumo").GetString()!;
        var senha = v.GetProperty("senha").GetString()!;

        Assert.False(new SenhasArgon2("outra-pimenta").Conferir(senha, resumo));
        Assert.False(new SenhasArgon2("").Conferir(senha, resumo));
    }

    [Fact]
    public void Resumo_sem_pimenta_nao_confere_quando_ha_pimenta()
    {
        var sem = Vetores.GetProperty("argon2").EnumerateArray().Single(v => v.GetProperty("pimenta").GetString() == "");
        Assert.False(new SenhasArgon2("pimenta-de-teste-nao-e-segredo")
            .Conferir(sem.GetProperty("senha").GetString()!, sem.GetProperty("resumo").GetString()!));
    }

    [Fact]
    public void Bcrypt_legado_confere_sem_pimenta_e_pede_regravacao()
    {
        var v = Vetores.GetProperty("bcrypt_legado");
        // o bcrypt foi gravado antes da pimenta existir: confere mesmo com pimenta configurada
        var senhas = new SenhasArgon2("pimenta-de-teste-nao-e-segredo");
        var resumo = v.GetProperty("resumo").GetString()!;

        Assert.True(senhas.Conferir(v.GetProperty("senha").GetString()!, resumo));
        Assert.False(senhas.Conferir("Senha-Errada-1", resumo));
        Assert.True(senhas.PrecisaRegravar(resumo));
    }

    [Fact]
    public void Argon2_com_parametros_defasados_confere_e_pede_regravacao()
    {
        var v = Vetores.GetProperty("defasado");
        var senhas = new SenhasArgon2(v.GetProperty("pimenta").GetString()!);
        var resumo = v.GetProperty("resumo").GetString()!;

        Assert.True(senhas.Conferir(v.GetProperty("senha").GetString()!, resumo));
        Assert.True(senhas.PrecisaRegravar(resumo));
    }

    [Theory]
    [InlineData("")]
    [InlineData("$argon2id$v=19$m=65536,t=3,p=4$naoebase64!!$xx")]
    [InlineData("$argon2id$quebrado")]
    [InlineData("$2b$12$curto")]
    [InlineData("texto-qualquer")]
    public void Resumo_invalido_nao_derruba_e_nao_autentica(string ruim)
    {
        var senhas = new SenhasArgon2("p");
        Assert.False(senhas.Conferir("Qualquer-Senha-1", ruim));
        Assert.True(senhas.PrecisaRegravar(ruim));
    }

    [Fact]
    public void Resumo_gerado_aqui_tem_o_formato_do_argon2_cffi_e_sal_proprio()
    {
        var senhas = new SenhasArgon2("p");
        var a = senhas.Gerar("Senha-De-Teste-2026");
        var b = senhas.Gerar("Senha-De-Teste-2026");

        Assert.StartsWith("$argon2id$v=19$m=65536,t=3,p=4$", a);
        Assert.NotEqual(a, b);
        Assert.DoesNotContain("Senha", a);
        Assert.Equal(97, a.Length);   // o tamanho dos resumos gravados pelo Python no banco
        Assert.False(senhas.PrecisaRegravar(a));
    }

    [Fact]
    public void Senha_absurda_e_recusada() =>
        Assert.Throws<SenhaLonga>(() => new SenhasArgon2("p").Gerar(new string('a', 1025)));

    [Fact]
    public async Task Token_do_python_e_lido_aqui()
    {
        var v = Vetores.GetProperty("token");
        var tokens = new TokensJwt(v.GetProperty("segredo").GetString()!, 480,
            new FakeTimeProvider(DateTimeOffset.FromUnixTimeSeconds(1789000100)));

        var conteudo = await tokens.Ler(v.GetProperty("jwt").GetString()!);

        Assert.Equal(new ConteudoDoToken(7, "analista.um", Papel.Analista, [3, 11]) with { Empresas = conteudo.Empresas },
            conteudo);
        Assert.Equal([3, 11], conteudo.Empresas);
    }

    [Fact]
    public async Task Token_do_python_com_segredo_errado_e_recusado()
    {
        var v = Vetores.GetProperty("token");
        var tokens = new TokensJwt("outro-segredo-com-mais-de-trinta-e-dois-bytes-aqui", 480, TimeProvider.System);
        await Assert.ThrowsAsync<TokenInvalido>(() => tokens.Ler(v.GetProperty("jwt").GetString()!));
    }

    [Fact]
    public async Task Token_vencido_e_recusado_no_mesmo_segundo_que_no_python()
    {
        var segredo = "segredo-de-teste-com-mais-de-trinta-e-dois-bytes-nao-e-segredo";
        var relogio = new FakeTimeProvider(new DateTimeOffset(2026, 9, 13, 12, 0, 0, TimeSpan.Zero));
        var tokens = new TokensJwt(segredo, 1, relogio);
        var (token, expira) = tokens.Emitir(new Usuario
            { Id = 1, NomeDeUsuario = "a", Email = "a@b.cc", NomeExibicao = "A", Papel = Papel.Gestor });
        Assert.Equal(60, expira);

        relogio.Advance(TimeSpan.FromSeconds(59));
        await tokens.Ler(token);
        relogio.Advance(TimeSpan.FromSeconds(1));
        await Assert.ThrowsAsync<TokenInvalido>(() => tokens.Ler(token));
    }
}

/// <summary>
/// O cruzamento ao vivo com o código do motor, no que os dois lados ainda
/// compartilham: o dígito do CNPJ e a tabela de tipos de arquivo.
///
/// Senha e token cruzavam aqui até a fatia 7. O motor não confere senha nem lê
/// token desde então — o código Python deles foi apagado —, e o que prova que
/// quem já tinha senha continua entrando são os vetores gravados pelo Python,
/// em <see cref="VetoresDoPythonTestes"/>.
/// </summary>
public sealed class CruzamentoComOPythonTestes
{
    [Fact]
    public async Task Digito_do_cnpj_calculado_no_csharp_confere_no_python_inclusive_alfanumerico()
    {
        // o motor lê CNPJ de todo arquivo; a API valida o que a pessoa digita.
        // Um dígito diferente entre os dois recusaria na tela o CNPJ que o SPED traz.
        const string alfabeto = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        var aleatorio = new Random(20260913);
        var cnpjs = Enumerable.Range(0, 300).Select(i =>
        {
            var baseDoze = new string(Enumerable.Range(0, 12)
                .Select(_ => alfabeto[aleatorio.Next(i % 3 == 0 ? 10 : alfabeto.Length)]).ToArray());
            return baseDoze + Cat.Dominio.Comum.Cnpj.DigitosVerificadores(baseDoze);
        }).ToList();

        var saida = await Python("""
            import json, sys
            from cat.dominio.comum.cnpj import tentar
            e = json.load(sys.stdin)
            print(json.dumps({"recusados": [c for c in e["cnpjs"] if tentar(c) is None and len(set(c)) > 1]}))
            """, new { cnpjs });

        Assert.Empty(saida.GetProperty("recusados").EnumerateArray());
    }

    [Fact]
    public async Task Tabela_de_tipos_de_arquivo_e_a_mesma_do_motor()
    {
        // o motor reconhece o tipo; a API descreve. Tipo que alimenta um trabalho
        // num lado e não no outro faria a tela dizer que a base serve quando não
        // serve — ou recusar a importação de uma pasta que serve.
        var saida = await Python("""
            import json
            from cat.dominio.lote import TipoDeArquivo
            print(json.dumps([[t.value, t.rotulo, t.grupo.value, t.alimenta_a_cat,
                               list(t.modulos)] for t in TipoDeArquivo]))
            """, new { });

        var doPython = saida.EnumerateArray()
            .Select(t => (t[0].GetString(), t[1].GetString(), t[2].GetString(), t[3].GetBoolean(),
                          string.Join(",", t[4].EnumerateArray().Select(m => m.GetString())))).ToList();
        var doCsharp = Cat.Dominio.Lote.TiposDeArquivo.Todos
            .Select(t => ((string?)t.Valor, (string?)t.Rotulo, (string?)t.Grupo, t.AlimentaACat,
                          string.Join(",", t.Modulos))).ToList();
        Assert.Equal(doPython, doCsharp);
    }

    /// <summary>Roda um trecho com o Python do backend, que é o que está em produção.</summary>
    private static async Task<JsonElement> Python(string codigo, object entrada)
    {
        var backend = LocalizarBackend();
        var python = Path.Combine(backend, ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
            Assert.Fail($"Sem o ambiente Python em {python}. Rode scripts\\instalar.ps1: " +
                        "sem ele não há como provar a compatibilidade com o motor.");

        var inicio = new ProcessStartInfo(python)
        {
            WorkingDirectory = backend,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new System.Text.UTF8Encoding(false),
            StandardOutputEncoding = System.Text.Encoding.UTF8,
        };
        inicio.ArgumentList.Add("-c");
        inicio.ArgumentList.Add(codigo);
        inicio.Environment["PYTHONIOENCODING"] = "utf-8";

        using var processo = Process.Start(inicio)!;
        await processo.StandardInput.WriteAsync(JsonSerializer.Serialize(entrada));
        processo.StandardInput.Close();
        var saida = await processo.StandardOutput.ReadToEndAsync();
        var erro = await processo.StandardError.ReadToEndAsync();
        await processo.WaitForExitAsync();
        Assert.True(processo.ExitCode == 0, $"O Python falhou:\n{erro}");
        return JsonDocument.Parse(saida.Trim().Split('\n')[^1]).RootElement;
    }

    private static string LocalizarBackend()
    {
        for (var pasta = new DirectoryInfo(AppContext.BaseDirectory); pasta is not null; pasta = pasta.Parent)
        {
            var candidato = Path.Combine(pasta.FullName, "backend");
            if (File.Exists(Path.Combine(candidato, "pyproject.toml")))
                return candidato;
        }
        throw new InvalidOperationException("Não achei backend/ subindo a partir dos testes.");
    }
}
