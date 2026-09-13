using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Cat.Api.Testes;

/// <summary>
/// Portados de tests/integracao/test_auth_api.py, agora contra a API em C# e
/// o Postgres de verdade. Cada teste cria o próprio usuário: bloqueio e
/// tentativas são estado, e um teste não pode herdar o do outro.
/// </summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class AutenticacaoTestes(BancoDeTeste banco) : IDisposable
{
    private readonly string _backend = CriarBackendFalso();
    private WebApplicationFactory<Program>? _fabrica;

    public void Dispose()
    {
        _fabrica?.Dispose();
        Directory.Delete(_backend, recursive: true);
    }

    private static string CriarBackendFalso()
    {
        var pasta = Directory.CreateTempSubdirectory("cat-auth-").FullName;
        File.WriteAllText(Path.Combine(pasta, "pyproject.toml"), "version = \"1.2.3\"\n");
        File.WriteAllText(Path.Combine(pasta, ".env"), "");
        return pasta;
    }

    private HttpClient Cliente()
    {
        _fabrica ??= new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("CAT_RAIZ_BACKEND", _backend);
            b.UseSetting("CAT_BANCO_URL", banco.Url);
            b.UseSetting("CAT_SENHA_PIMENTA", BancoDeTeste.Pimenta);
            b.UseSetting("CAT_JWT_SEGREDO", BancoDeTeste.Segredo);
            // porta onde ninguém escuta: se uma rota de login cair no repasse, o teste falha
            b.UseSetting("CAT_MOTOR_URL", "http://127.0.0.1:9");
        });
        return _fabrica.CreateClient();
    }

    private static string Nome() => "u" + Guid.NewGuid().ToString("N")[..10];

    private static Task<HttpResponseMessage> Entrar(HttpClient cliente, string usuario, string senha) =>
        cliente.PostAsync("/api/auth/token", new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["username"] = usuario,
            ["password"] = senha,
        }));

    private static async Task<string> Detalhe(HttpResponseMessage r) =>
        (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail").GetString()!;

    [Fact]
    public async Task Login_certo_devolve_token_e_o_usuario_no_formato_da_tela()
    {
        var nome = Nome();
        var id = await banco.CriarUsuario(nome, papel: "analista", empresas: [7, 3], cargo: "coordenador");

        var r = await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var corpo = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("bearer", corpo.GetProperty("token_type").GetString());
        Assert.Equal(480 * 60, corpo.GetProperty("expires_in").GetInt32());
        Assert.False(string.IsNullOrEmpty(corpo.GetProperty("access_token").GetString()));

        var u = corpo.GetProperty("usuario");
        Assert.Equal(
            ["id", "usuario", "email", "nome_exibicao", "papel", "cargo", "empresas", "senha_provisoria", "ultimo_acesso"],
            u.EnumerateObject().Select(p => p.Name));
        Assert.Equal(id, u.GetProperty("id").GetInt32());
        Assert.Equal("analista", u.GetProperty("papel").GetString());
        Assert.Equal("coordenador", u.GetProperty("cargo").GetString());
        // ids das empresas, em ordem crescente, como o sorted() do Python
        var ids = new[]
        {
            await banco.Escalar<int>("SELECT id FROM empresa WHERE cnpj_raiz = '00000007'"),
            await banco.Escalar<int>("SELECT id FROM empresa WHERE cnpj_raiz = '00000003'"),
        }.Order();
        Assert.Equal(ids, u.GetProperty("empresas").EnumerateArray().Select(e => e.GetInt32()));
        Assert.EndsWith("+00:00", u.GetProperty("ultimo_acesso").GetString());
    }

    [Fact]
    public async Task Login_aceita_maiuscula_e_espaco_no_usuario()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome);

        var r = await Entrar(Cliente(), $"  {nome.ToUpperInvariant()} ", BancoDeTeste.SenhaPadrao);

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
    }

    [Fact]
    public async Task Senha_errada_e_usuario_inexistente_dao_401_com_a_mesma_mensagem()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome);
        var cliente = Cliente();

        var errada = await Entrar(cliente, nome, "Senha-Errada-2026");
        var inexistente = await Entrar(cliente, Nome(), "Senha-Errada-2026");

        Assert.Equal(HttpStatusCode.Unauthorized, errada.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, inexistente.StatusCode);
        var mensagem = await Detalhe(errada);
        Assert.Equal("Usuário ou senha inválidos.", mensagem);
        Assert.Equal(mensagem, await Detalhe(inexistente));
        Assert.Equal("Bearer", errada.Headers.WwwAuthenticate.Single().Scheme);
    }

    [Fact]
    public async Task Resposta_de_login_leva_pelo_menos_o_piso_mesmo_para_quem_nao_existe()
    {
        var cliente = Cliente();
        await Entrar(cliente, Nome(), "aquece-o-host");

        var relogio = Stopwatch.StartNew();
        await Entrar(cliente, Nome(), "Qualquer-2026");

        Assert.True(relogio.Elapsed >= TimeSpan.FromMilliseconds(340), $"respondeu em {relogio.ElapsedMilliseconds} ms");
    }

    [Fact]
    public async Task Usuario_inativo_da_403()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, ativo: false);

        var r = await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("Usuário inativo. Procure um gestor.", await Detalhe(r));
    }

    [Fact]
    public async Task Quinta_senha_errada_bloqueia_e_nem_a_senha_certa_entra()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome);
        var cliente = Cliente();

        for (var i = 0; i < 5; i++)
            Assert.Equal(HttpStatusCode.Unauthorized, (await Entrar(cliente, nome, "Senha-Errada-2026")).StatusCode);
        var certa = await Entrar(cliente, nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(HttpStatusCode.Forbidden, certa.StatusCode);
        Assert.Equal("Muitas tentativas. Tente de novo em 15 minutos.", await Detalhe(certa));
        Assert.Equal(5, await banco.Escalar<int>($"SELECT tentativas_falhas FROM usuario WHERE usuario = '{nome}'"));
        // o bloqueio foi gravado com fuso, e o Python lê o mesmo instante
        Assert.True(await banco.Escalar<bool>(
            $"SELECT bloqueado_ate BETWEEN now() + interval '14 minutes' AND now() + interval '16 minutes' FROM usuario WHERE usuario = '{nome}'"));
    }

    [Fact]
    public async Task Bloqueio_definitivo_da_403_com_a_mensagem_de_procurar_gestor()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, tentativas: 20);

        var r = await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("Usuário bloqueado por excesso de tentativas. Procure um gestor.", await Detalhe(r));
    }

    [Fact]
    public async Task Login_certo_zera_as_tentativas_e_marca_o_acesso()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, tentativas: 3);

        await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(0, await banco.Escalar<int>($"SELECT tentativas_falhas FROM usuario WHERE usuario = '{nome}'"));
        Assert.True(await banco.Escalar<bool>($"SELECT ultimo_acesso > now() - interval '1 minute' FROM usuario WHERE usuario = '{nome}'"));
    }

    [Fact]
    public async Task Resumo_bcrypt_antigo_vira_argon2_no_primeiro_login()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, resumo: BCrypt.Net.BCrypt.HashPassword(BancoDeTeste.SenhaPadrao, 4));

        var r = await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var resumo = await banco.Escalar<string>($"SELECT senha_hash FROM usuario WHERE usuario = '{nome}'");
        Assert.StartsWith("$argon2id$v=19$m=65536,t=3,p=4$", resumo);
        // e segue entrando com a mesma senha, agora pelo resumo novo
        Assert.Equal(HttpStatusCode.OK, (await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao)).StatusCode);
    }

    // Os três seguintes vieram de tests/unidade/test_autenticar.py, apagado quando
    // o login saiu do Python: eram os únicos cenários que esta bateria não provava.

    [Fact]
    public async Task Inativo_e_recusado_antes_de_conferir_a_senha_e_nao_conta_tentativa()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, ativo: false);

        var r = await Entrar(Cliente(), nome, "Senha-Errada-2026");

        // mesmo com a senha errada a resposta é "inativo": a senha nem foi olhada
        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("Usuário inativo. Procure um gestor.", await Detalhe(r));
        Assert.Equal(0, await banco.Escalar<int>($"SELECT tentativas_falhas FROM usuario WHERE usuario = '{nome}'"));
    }

    [Fact]
    public async Task Senha_errada_nao_regrava_resumo_antigo()
    {
        var nome = Nome();
        var bcrypt = BCrypt.Net.BCrypt.HashPassword(BancoDeTeste.SenhaPadrao, 4);
        await banco.CriarUsuario(nome, resumo: bcrypt);

        await Entrar(Cliente(), nome, "Senha-Errada-2026");

        // regravar só é possível com a senha em claro certa em mãos
        Assert.Equal(bcrypt, await banco.Escalar<string>($"SELECT senha_hash FROM usuario WHERE usuario = '{nome}'"));
    }

    [Fact]
    public async Task Resumo_atual_nao_e_regravado_a_cada_login()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome);

        await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao);

        Assert.Equal(banco.ResumoPadrao, await banco.Escalar<string>($"SELECT senha_hash FROM usuario WHERE usuario = '{nome}'"));
    }

    [Fact]
    public async Task Senha_e_resumo_nunca_voltam_na_resposta()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome);

        var texto = await (await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao)).Content.ReadAsStringAsync();

        Assert.DoesNotContain(BancoDeTeste.SenhaPadrao, texto);
        Assert.DoesNotContain("argon2", texto);
        Assert.DoesNotContain("senha_hash", texto);
    }

    [Fact]
    public async Task Formulario_sem_senha_da_422_com_texto_que_a_tela_mostra()
    {
        var r = await Cliente().PostAsync("/api/auth/token",
            new FormUrlEncodedContent(new Dictionary<string, string> { ["username"] = "alguem" }));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal("Informe usuário e senha.", await Detalhe(r));
    }

    [Fact]
    public async Task Eu_exige_token_e_recusa_token_falso()
    {
        var cliente = Cliente();

        var sem = await cliente.GetAsync("/api/auth/eu");
        cliente.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", "abc.def.ghi");
        var falso = await cliente.GetAsync("/api/auth/eu");

        Assert.Equal(HttpStatusCode.Unauthorized, sem.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, falso.StatusCode);
        Assert.Equal("Sessão inválida ou expirada.", await Detalhe(falso));
    }

    [Fact]
    public async Task Eu_com_token_valido_devolve_o_mesmo_usuario_do_login()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, empresas: [21]);
        var cliente = Cliente();
        var login = await (await Entrar(cliente, nome, BancoDeTeste.SenhaPadrao)).Content.ReadFromJsonAsync<JsonElement>();

        cliente.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", login.GetProperty("access_token").GetString());
        var eu = await cliente.GetFromJsonAsync<JsonElement>("/api/auth/eu");

        // inclusive o instante do último acesso, que o /eu lê do banco
        Assert.Equal(login.GetProperty("usuario").GetRawText(), eu.GetRawText());
    }

    [Fact]
    public async Task Desativado_depois_do_login_perde_o_acesso_na_hora()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome);
        var cliente = Cliente();
        var login = await (await Entrar(cliente, nome, BancoDeTeste.SenhaPadrao)).Content.ReadFromJsonAsync<JsonElement>();
        cliente.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", login.GetProperty("access_token").GetString());

        await banco.Comando($"UPDATE usuario SET ativo = false WHERE usuario = '{nome}'");

        Assert.Equal(HttpStatusCode.Unauthorized, (await cliente.GetAsync("/api/auth/eu")).StatusCode);
    }

    [Fact]
    public async Task Alocacao_encerrada_sai_do_escopo()
    {
        var nome = Nome();
        await banco.CriarUsuario(nome, empresas: [31, 32]);
        await banco.Comando($"""
            UPDATE alocacao SET fim = now() WHERE usuario_id = (SELECT id FROM usuario WHERE usuario = '{nome}')
              AND empresa_id = (SELECT id FROM empresa WHERE cnpj_raiz = '00000031')
            """);

        var corpo = await (await Entrar(Cliente(), nome, BancoDeTeste.SenhaPadrao)).Content.ReadFromJsonAsync<JsonElement>();

        var esperado = await banco.Escalar<int>("SELECT id FROM empresa WHERE cnpj_raiz = '00000032'");
        Assert.Equal([esperado], corpo.GetProperty("usuario").GetProperty("empresas").EnumerateArray().Select(e => e.GetInt32()));
    }

    [Fact]
    public async Task Resposta_traz_identificador_de_requisicao()
    {
        var r = await Entrar(Cliente(), Nome(), "x-2026-Senha");
        Assert.Matches("^[0-9a-f]{12}$", r.Headers.GetValues("X-Request-Id").Single());
    }
}
