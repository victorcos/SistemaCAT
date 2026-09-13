using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Cat.Api.Testes;

/// <summary>
/// Portados de tests/integracao/test_usuarios_api.py e tests/unidade/test_gerir_usuarios.py,
/// contra a API em C# e o Postgres de verdade.
///
/// A salvaguarda de três gestores conta o banco inteiro, e o banco é da coleção.
/// Os testes que dependem da contagem montam o próprio trio e desativam os
/// gestores dos outros testes antes — mesma razão do so_o_trio do Python.
/// </summary>
[Collection(ColecaoDoBanco.Nome)]
public sealed class UsuariosTestes(BancoDeTeste banco) : IDisposable
{
    private readonly string _backend = CriarBackendFalso();
    private WebApplicationFactory<Program>? _fabrica;
    private readonly TokensJwt _tokens = new(BancoDeTeste.Segredo, 480, TimeProvider.System);

    public void Dispose()
    {
        _fabrica?.Dispose();
        Directory.Delete(_backend, recursive: true);
    }

    private static string CriarBackendFalso()
    {
        var pasta = Directory.CreateTempSubdirectory("cat-usuarios-").FullName;
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
            // porta onde ninguém escuta: rota de usuário que caísse no repasse falharia
            b.UseSetting("CAT_MOTOR_URL", "http://127.0.0.1:9");
        });
        return _fabrica.CreateClient();
    }

    private static string Nome(string prefixo = "u") => prefixo + Guid.NewGuid().ToString("N")[..10];

    /// <summary>Cliente já autenticado como esta pessoa. O token é o mesmo que o login emite.</summary>
    private async Task<HttpClient> Como(int usuarioId, string nome, string papel)
    {
        TextoDeAcesso.TentarPapel(papel, out var p);
        var (token, _) = _tokens.Emitir(new Usuario
            { Id = usuarioId, NomeDeUsuario = nome, Email = "x@y.zz", NomeExibicao = "X", Papel = p });
        var cliente = Cliente();
        cliente.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return await Task.FromResult(cliente);
    }

    private async Task<(int Id, string Nome, HttpClient Cliente)> Gestor(string cargo = "diretor")
    {
        var nome = Nome("g");
        var id = await banco.CriarUsuario(nome, papel: "gestor", cargo: cargo);
        return (id, nome, await Como(id, nome, "gestor"));
    }

    private async Task<(int Id, string Nome)> Analista(int[]? empresas = null)
    {
        var nome = Nome("a");
        return (await banco.CriarUsuario(nome, empresas: empresas), nome);
    }

    /// <summary>Deixa ativos só estes gestores, para a contagem ser a do teste.</summary>
    private Task SoEstesGestores(params int[] ids) =>
        banco.Comando($"UPDATE usuario SET ativo = false WHERE papel = 'gestor' AND id NOT IN ({string.Join(",", ids)})");

    private static async Task<JsonElement> Json(HttpResponseMessage r) => await r.Content.ReadFromJsonAsync<JsonElement>();
    private static async Task<string> Detalhe(HttpResponseMessage r) => (await Json(r)).GetProperty("detail").GetString()!;

    private static Task<HttpResponseMessage> Patch(HttpClient c, string url, object corpo) =>
        c.PatchAsync(url, JsonContent.Create(corpo));

    // ------------------------------------------------------------------ permissão
    [Fact]
    public async Task Sem_token_nao_lista()
    {
        Assert.Equal(HttpStatusCode.Unauthorized, (await Cliente().GetAsync("/api/usuarios")).StatusCode);
    }

    [Fact]
    public async Task Analista_nao_lista_nao_cria_nao_redefine_nem_mexe_em_acesso()
    {
        var (id, nome) = await Analista();
        var analista = await Como(id, nome, "analista");
        var (alvo, _, _) = await Gestor();

        var lista = await analista.GetAsync("/api/usuarios");
        var cria = await analista.PostAsJsonAsync("/api/usuarios",
            new { usuario = "invasor", email = "i@bms.local", nome_exibicao = "Invasor", papel = "gestor" });
        var redefine = await analista.PostAsync($"/api/usuarios/{alvo}/senha", null);
        var acesso = await analista.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = Array.Empty<int>() });

        Assert.All(new[] { lista, cria, redefine, acesso }, r => Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode));
        Assert.Equal("Você não tem permissão para administrar usuários.", await Detalhe(lista));
    }

    [Fact]
    public async Task Gestor_lista_com_os_campos_da_tela_de_gestao()
    {
        var (_, _, gestor) = await Gestor();

        var r = await gestor.GetAsync("/api/usuarios");

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var primeiro = (await Json(r)).EnumerateArray().First();
        Assert.Equal(
            ["id", "usuario", "email", "nome_exibicao", "papel", "cargo", "ativo", "bloqueado", "senha_provisoria",
             "tentativas_falhas", "empresas", "ultimo_acesso"],
            primeiro.EnumerateObject().Select(p => p.Name));
    }

    [Fact]
    public async Task Listagem_poe_ativos_primeiro_e_ordena_por_nome()
    {
        var (_, _, gestor) = await Gestor();
        await banco.CriarUsuario("zz.inativo." + Guid.NewGuid().ToString("N")[..6], ativo: false);

        var lista = (await Json(await gestor.GetAsync("/api/usuarios"))).EnumerateArray()
            .Select(u => (Ativo: u.GetProperty("ativo").GetBoolean(), Nome: u.GetProperty("usuario").GetString()!)).ToList();

        var ativos = lista.TakeWhile(u => u.Ativo).ToList();
        Assert.True(lista.Skip(ativos.Count).All(u => !u.Ativo));
        // A ordem por nome é a do Postgres (collation en_US, que ignora pontuação), como
        // era no Python. Comparar com a ordenação byte a byte do C# falharia ao acaso.
        await using var conexao = await banco.Abrir();
        await using var consulta = new Npgsql.NpgsqlCommand("SELECT usuario FROM usuario ORDER BY ativo DESC, usuario", conexao);
        await using var leitor = await consulta.ExecuteReaderAsync();
        var doBanco = new List<string>();
        while (await leitor.ReadAsync())
            doBanco.Add(leitor.GetString(0));
        Assert.Equal(doBanco, lista.Select(u => u.Nome));
    }

    // ------------------------------------------------------------------ cadastro
    [Fact]
    public async Task Gestor_cria_normalizando_e_recebe_senha_provisoria_que_confere()
    {
        var (_, _, gestor) = await Gestor();
        var sufixo = Guid.NewGuid().ToString("N")[..8];

        var r = await gestor.PostAsJsonAsync("/api/usuarios", new
        {
            usuario = $"  Novo.Maria{sufixo} ", email = $" Maria{sufixo}@BMS.Local ",
            nome_exibicao = " Maria ", papel = "analista", cargo = "analista",
        });

        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var corpo = await Json(r);
        var usuario = corpo.GetProperty("usuario");
        Assert.Equal($"novo.maria{sufixo}", usuario.GetProperty("usuario").GetString());
        Assert.Equal($"maria{sufixo}@bms.local", usuario.GetProperty("email").GetString());
        Assert.Equal("Maria", usuario.GetProperty("nome_exibicao").GetString());
        Assert.True(usuario.GetProperty("senha_provisoria").GetBoolean());
        Assert.True(usuario.GetProperty("ativo").GetBoolean());
        Assert.Contains("não será exibida de novo", corpo.GetProperty("aviso").GetString());

        var senha = corpo.GetProperty("senha_provisoria").GetString()!;
        PoliticaDeAcesso.ValidarSenha(senha);
        var resumo = await banco.Escalar<string>($"SELECT senha_hash FROM usuario WHERE usuario = 'novo.maria{sufixo}'");
        Assert.True(new SenhasArgon2(BancoDeTeste.Pimenta).Conferir(senha, resumo));
    }

    [Fact]
    public async Task Senha_provisoria_e_do_sistema_e_muda_a_cada_cadastro()
    {
        var (_, _, gestor) = await Gestor();
        async Task<string> Criar()
        {
            var n = Nome("p");
            var r = await gestor.PostAsJsonAsync("/api/usuarios",
                new { usuario = n, email = $"{n}@bms.local", nome_exibicao = "P P", papel = "leitura" });
            return (await Json(r)).GetProperty("senha_provisoria").GetString()!;
        }

        Assert.NotEqual(await Criar(), await Criar());
    }

    [Fact]
    public async Task Recusa_usuario_ou_email_repetido()
    {
        var (_, _, gestor) = await Gestor();
        var (_, existente) = await Analista();

        var mesmoNome = await gestor.PostAsJsonAsync("/api/usuarios",
            new { usuario = existente, email = "outra@bms.local", nome_exibicao = "Outra", papel = "leitura" });
        var mesmoEmail = await gestor.PostAsJsonAsync("/api/usuarios",
            new { usuario = Nome(), email = $"{existente}@teste.local", nome_exibicao = "Outra", papel = "leitura" });

        Assert.Equal(HttpStatusCode.Conflict, mesmoNome.StatusCode);
        Assert.Equal("Já existe usuário com este nome de usuário.", await Detalhe(mesmoNome));
        Assert.Equal(HttpStatusCode.Conflict, mesmoEmail.StatusCode);
        Assert.Equal("Já existe usuário com este e-mail.", await Detalhe(mesmoEmail));
    }

    [Theory]
    [InlineData("""{"usuario":"ab","email":"a@bms.local","nome_exibicao":"Ana","papel":"leitura"}""", "3 a 40")]
    [InlineData("""{"usuario":"com espaco","email":"a@bms.local","nome_exibicao":"Ana","papel":"leitura"}""", "letras minúsculas")]
    [InlineData("""{"usuario":"valido.um","email":"sem-arroba","nome_exibicao":"Ana","papel":"leitura"}""", "E-mail inválido.")]
    [InlineData("""{"usuario":"valido.dois","email":"a@bms.local","nome_exibicao":"A","papel":"leitura"}""", "2 caracteres")]
    [InlineData("""{"usuario":"valido.tres","email":"a@bms.local","nome_exibicao":"Ana","papel":"chefe"}""", "Papel desconhecido: chefe.")]
    [InlineData("""{"usuario":"valido.quatro","email":"a@bms.local","nome_exibicao":"Ana","papel":"leitura","cargo":"rei"}""", "Cargo desconhecido: rei.")]
    [InlineData("""{"usuario": """, "JSON")]
    public async Task Cadastro_invalido_da_422_com_texto(string corpo, string pedaco)
    {
        var (_, _, gestor) = await Gestor();

        var r = await gestor.PostAsync("/api/usuarios", new StringContent(corpo, System.Text.Encoding.UTF8, "application/json"));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Contains(pedaco, await Detalhe(r));
    }

    [Fact]
    public async Task Quem_foi_criado_entra_com_a_provisoria_e_a_tela_obriga_a_troca()
    {
        var (_, _, gestor) = await Gestor();
        var n = Nome("novo");
        var criado = await Json(await gestor.PostAsJsonAsync("/api/usuarios",
            new { usuario = n, email = $"{n}@bms.local", nome_exibicao = "Novo", papel = "analista" }));

        var login = await Cliente().PostAsync("/api/auth/token", new FormUrlEncodedContent(new Dictionary<string, string>
            { ["username"] = n, ["password"] = criado.GetProperty("senha_provisoria").GetString()! }));

        Assert.Equal(HttpStatusCode.OK, login.StatusCode);
        Assert.True((await Json(login)).GetProperty("usuario").GetProperty("senha_provisoria").GetBoolean());
    }

    // ------------------------------------------------------------------ dados e cargo
    [Fact]
    public async Task Gestor_altera_nome_e_email_e_o_nome_de_usuario_nao_muda()
    {
        var (_, _, gestor) = await Gestor();
        var (id, nome) = await Analista();
        var email = $"{nome}.novo@bms.local";

        var r = await Patch(gestor, $"/api/usuarios/{id}/dados", new { nome_exibicao = "Ana Paula", email = email.ToUpperInvariant() });

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var u = await Json(r);
        Assert.Equal("Ana Paula", u.GetProperty("nome_exibicao").GetString());
        Assert.Equal(email, u.GetProperty("email").GetString());
        Assert.Equal(nome, u.GetProperty("usuario").GetString());

        // o próprio e-mail não conta como duplicado
        Assert.Equal(HttpStatusCode.OK, (await Patch(gestor, $"/api/usuarios/{id}/dados", new { nome_exibicao = "Ana P.", email })).StatusCode);
    }

    [Fact]
    public async Task Email_de_outro_usuario_ou_invalido_e_recusado()
    {
        var (_, _, gestor) = await Gestor();
        var (id, _) = await Analista();
        var (_, outro) = await Analista();

        var deOutro = await Patch(gestor, $"/api/usuarios/{id}/dados", new { nome_exibicao = "Ana", email = $"{outro}@teste.local" });
        var invalido = await Patch(gestor, $"/api/usuarios/{id}/dados", new { nome_exibicao = "Ana", email = "sem-arroba" });

        Assert.Equal(HttpStatusCode.Conflict, deOutro.StatusCode);
        Assert.Contains("e-mail", await Detalhe(deOutro));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, invalido.StatusCode);
    }

    [Fact]
    public async Task Gestor_altera_cargo_e_cargo_desconhecido_da_422()
    {
        var (_, _, gestor) = await Gestor();
        var (id, _) = await Analista();

        var ok = await Patch(gestor, $"/api/usuarios/{id}/cargo", new { cargo = "estagiario" });
        var ruim = await Patch(gestor, $"/api/usuarios/{id}/cargo", new { cargo = "Estagiario" });

        Assert.Equal("estagiario", (await Json(ok)).GetProperty("cargo").GetString());
        Assert.Equal(HttpStatusCode.UnprocessableEntity, ruim.StatusCode);
    }

    [Fact]
    public async Task Usuario_inexistente_da_404()
    {
        var (_, _, gestor) = await Gestor();

        var r = await Patch(gestor, "/api/usuarios/999999/cargo", new { cargo = "outro" });

        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        Assert.Equal("Usuário não encontrado.", await Detalhe(r));
    }

    // ------------------------------------------------------------------ mínimo de gestores
    [Fact]
    public async Task Nao_rebaixa_nem_desativa_deixando_menos_de_tres()
    {
        var (diretor, _, cliente) = await Gestor();
        var (gerente, _, _) = await Gestor("gerente");
        var (coordenador, _, _) = await Gestor("coordenador");
        await SoEstesGestores(diretor, gerente, coordenador);

        var rebaixa = await Patch(cliente, $"/api/usuarios/{gerente}/papel", new { papel = "analista" });
        var desativa = await Patch(cliente, $"/api/usuarios/{gerente}/situacao", new { ativo = false });

        Assert.Equal(HttpStatusCode.Conflict, rebaixa.StatusCode);
        Assert.Contains("3 gestores", await Detalhe(rebaixa));
        Assert.Equal(HttpStatusCode.Conflict, desativa.StatusCode);
        Assert.Equal("gestor", await banco.Escalar<string>($"SELECT papel FROM usuario WHERE id = {gerente}"));
    }

    [Fact]
    public async Task Com_quatro_gestores_da_para_rebaixar_um()
    {
        var (a, _, cliente) = await Gestor();
        var (b, _, _) = await Gestor();
        var (c, _, _) = await Gestor();
        var (d, _, _) = await Gestor();
        await SoEstesGestores(a, b, c, d);

        var r = await Patch(cliente, $"/api/usuarios/{d}/papel", new { papel = "analista" });

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("analista", (await Json(r)).GetProperty("papel").GetString());
    }

    [Fact]
    public async Task Gestor_inativo_nao_conta_e_dev_tambem_nao()
    {
        var (a, _, cliente) = await Gestor();
        var (b, _, _) = await Gestor();
        var (c, _, _) = await Gestor();
        var dev = await banco.CriarUsuario(Nome("dev"), papel: "dev");
        await SoEstesGestores(a, b, c);
        await banco.Comando($"UPDATE usuario SET ativo = false WHERE id = {c}");

        // dois gestores ativos e um dev: não são três
        var r = await Patch(cliente, $"/api/usuarios/{b}/situacao", new { ativo = false });

        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
        Assert.True(dev > 0);
    }

    [Fact]
    public async Task Rebaixar_gestor_inativo_nao_esbarra_na_contagem()
    {
        // O Python recusava: descontava da contagem quem já estava fora dela.
        var (a, _, cliente) = await Gestor();
        var (b, _, _) = await Gestor();
        var (c, _, _) = await Gestor();
        var (inativo, _, _) = await Gestor();
        await SoEstesGestores(a, b, c);   // desativa o quarto

        var r = await Patch(cliente, $"/api/usuarios/{inativo}/papel", new { papel = "leitura" });

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
    }

    [Fact]
    public async Task Desativar_quem_nao_e_gestor_nao_e_barrado()
    {
        var (a, _, cliente) = await Gestor();
        var (b, _, _) = await Gestor();
        var (c, _, _) = await Gestor();
        await SoEstesGestores(a, b, c);
        var (analista, _) = await Analista();

        var r = await Patch(cliente, $"/api/usuarios/{analista}/situacao", new { ativo = false });

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.False((await Json(r)).GetProperty("ativo").GetBoolean());
    }

    [Fact]
    public async Task Ninguem_se_rebaixa_nem_se_desativa()
    {
        var (eu, _, cliente) = await Gestor();

        var rebaixa = await Patch(cliente, $"/api/usuarios/{eu}/papel", new { papel = "leitura" });
        var desativa = await Patch(cliente, $"/api/usuarios/{eu}/situacao", new { ativo = false });

        Assert.Equal(HttpStatusCode.Conflict, rebaixa.StatusCode);
        Assert.Equal("Você não pode rebaixar a si mesmo.", await Detalhe(rebaixa));
        Assert.Equal(HttpStatusCode.Conflict, desativa.StatusCode);
        Assert.Contains("si mesmo", await Detalhe(desativa));
    }

    // ------------------------------------------------------------------ senha
    [Fact]
    public async Task Redefinir_gera_provisoria_marca_troca_e_desbloqueia()
    {
        var (_, _, gestor) = await Gestor();
        var nome = Nome();
        var id = await banco.CriarUsuario(nome, tentativas: 20);

        var r = await gestor.PostAsync($"/api/usuarios/{id}/senha", null);

        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var corpo = await Json(r);
        Assert.Contains("próximo acesso", corpo.GetProperty("aviso").GetString());
        var senha = corpo.GetProperty("senha_provisoria").GetString()!;
        Assert.True(await banco.Escalar<bool>($"SELECT senha_provisoria FROM usuario WHERE id = {id}"));
        Assert.Equal(0, await banco.Escalar<int>($"SELECT tentativas_falhas FROM usuario WHERE id = {id}"));
        Assert.True(new SenhasArgon2(BancoDeTeste.Pimenta).Conferir(senha,
            await banco.Escalar<string>($"SELECT senha_hash FROM usuario WHERE id = {id}")));
    }

    [Fact]
    public async Task Redefinir_senha_de_quem_nao_existe_da_404()
    {
        var (_, _, gestor) = await Gestor();
        Assert.Equal(HttpStatusCode.NotFound, (await gestor.PostAsync("/api/usuarios/999999/senha", null)).StatusCode);
    }

    [Fact]
    public async Task Ciclo_da_senha_provisoria_pelo_login_de_verdade()
    {
        var (_, _, gestor) = await Gestor();
        var (id, nome) = await Analista();
        var anonimo = Cliente();
        Task<HttpResponseMessage> Entrar(string senha) => anonimo.PostAsync("/api/auth/token",
            new FormUrlEncodedContent(new Dictionary<string, string> { ["username"] = nome, ["password"] = senha }));

        var provisoria = (await Json(await gestor.PostAsync($"/api/usuarios/{id}/senha", null)))
            .GetProperty("senha_provisoria").GetString()!;

        // entra com a provisória e o sistema avisa que precisa trocar
        var entrada = await Json(await Entrar(provisoria));
        Assert.True(entrada.GetProperty("usuario").GetProperty("senha_provisoria").GetBoolean());

        // troca, com o token que o login acabou de dar
        var pessoa = Cliente();
        pessoa.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer",
            entrada.GetProperty("access_token").GetString());
        const string nova = "TrocadaPelaAna2026";
        var troca = await pessoa.PostAsJsonAsync("/api/usuarios/eu/senha", new { senha_atual = provisoria, senha_nova = nova });
        Assert.Equal(HttpStatusCode.NoContent, troca.StatusCode);

        // a provisória morreu, a nova funciona e a marca de troca sumiu
        Assert.Equal(HttpStatusCode.Unauthorized, (await Entrar(provisoria)).StatusCode);
        var respostaDepois = await Entrar(nova);
        Assert.Equal(HttpStatusCode.OK, respostaDepois.StatusCode);
        Assert.False((await Json(respostaDepois)).GetProperty("usuario").GetProperty("senha_provisoria").GetBoolean());
    }

    [Fact]
    public async Task Senha_atual_errada_da_403_e_nao_401_para_nao_derrubar_a_sessao()
    {
        var (id, nome) = await Analista();
        var pessoa = await Como(id, nome, "analista");

        var r = await pessoa.PostAsJsonAsync("/api/usuarios/eu/senha",
            new { senha_atual = "Errada-2026x", senha_nova = "NovaSenha2026" });

        Assert.Equal(HttpStatusCode.Forbidden, r.StatusCode);
        Assert.Equal("A senha atual está incorreta.", await Detalhe(r));
    }

    [Theory]
    [InlineData(BancoDeTeste.SenhaPadrao, "diferente da atual")]
    [InlineData("curta1A", "10 caracteres")]
    public async Task Troca_recusa_senha_repetida_ou_fraca(string nova, string pedaco)
    {
        var (id, nome) = await Analista();
        var pessoa = await Como(id, nome, "analista");

        var r = await pessoa.PostAsJsonAsync("/api/usuarios/eu/senha",
            new { senha_atual = BancoDeTeste.SenhaPadrao, senha_nova = nova });

        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Contains(pedaco, await Detalhe(r));
    }

    [Fact]
    public async Task Eu_senha_e_a_troca_da_propria_mesmo_para_gestor()
    {
        // "eu" não pode ser lido como identificador de alvo da redefinição
        var (_, _, gestor) = await Gestor();

        var r = await gestor.PostAsJsonAsync("/api/usuarios/eu/senha",
            new { senha_atual = BancoDeTeste.SenhaPadrao, senha_nova = "OutraSenha2026" });

        Assert.Equal(HttpStatusCode.NoContent, r.StatusCode);
    }

    [Fact]
    public async Task Senha_provisoria_nunca_volta_em_listagem()
    {
        var (_, _, gestor) = await Gestor();
        var (id, _) = await Analista();
        var senha = (await Json(await gestor.PostAsync($"/api/usuarios/{id}/senha", null)))
            .GetProperty("senha_provisoria").GetString()!;

        var corpo = await (await gestor.GetAsync("/api/usuarios")).Content.ReadAsStringAsync();

        Assert.Contains("senha_provisoria", corpo);
        Assert.DoesNotContain(senha, corpo);
        Assert.DoesNotContain("argon2", corpo);
    }

    [Fact]
    public async Task Gestor_desbloqueia()
    {
        var (_, _, gestor) = await Gestor();
        var nome = Nome();
        var id = await banco.CriarUsuario(nome, tentativas: 5);
        await banco.Comando($"UPDATE usuario SET bloqueado_ate = now() + interval '15 minutes' WHERE id = {id}");

        var antes = (await Json(await gestor.GetAsync("/api/usuarios"))).EnumerateArray()
            .Single(u => u.GetProperty("id").GetInt32() == id);
        var r = await gestor.PostAsync($"/api/usuarios/{id}/desbloquear", null);
        var depois = await Json(r);

        Assert.True(antes.GetProperty("bloqueado").GetBoolean());
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(0, depois.GetProperty("tentativas_falhas").GetInt32());
        Assert.False(depois.GetProperty("bloqueado").GetBoolean());
    }

    // ------------------------------------------------------------------ acesso a empresas
    private async Task<(int Id, string Razao)> Empresa()
    {
        var raiz = Random.Shared.Next(10_000_000, 99_999_999).ToString();
        var razao = "EMPRESA " + Guid.NewGuid().ToString("N")[..6].ToUpperInvariant();
        await banco.Comando($"INSERT INTO empresa (cnpj_raiz, razao_social, uf, ativa) VALUES ('{raiz}', '{razao}', 'SP', true)");
        return (await banco.Escalar<int>($"SELECT id FROM empresa WHERE cnpj_raiz = '{raiz}'"), razao);
    }

    [Fact]
    public async Task Lista_todas_as_empresas_em_ordem_marcando_as_que_alcanca()
    {
        var (_, _, gestor) = await Gestor();
        var (empresa, razao) = await Empresa();
        var (outra, _) = await Empresa();
        var (id, _) = await Analista();
        await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = new[] { outra } });

        var lista = (await Json(await gestor.GetAsync($"/api/usuarios/{id}/empresas"))).EnumerateArray().ToList();

        var semAcesso = lista.Single(e => e.GetProperty("empresa_id").GetInt32() == empresa);
        Assert.False(semAcesso.GetProperty("tem_acesso").GetBoolean());
        Assert.Equal(razao, semAcesso.GetProperty("razao_social").GetString());
        Assert.Equal(JsonValueKind.Null, semAcesso.GetProperty("desde").ValueKind);
        var comAcesso = lista.Single(e => e.GetProperty("empresa_id").GetInt32() == outra);
        Assert.True(comAcesso.GetProperty("tem_acesso").GetBoolean());
        Assert.EndsWith("+00:00", comAcesso.GetProperty("desde").GetString());
        Assert.Equal(["empresa_id", "razao_social", "uf", "tem_acesso", "desde"], semAcesso.EnumerateObject().Select(p => p.Name));
        Assert.Equal(lista.Count, await banco.Escalar<long>("SELECT count(*) FROM empresa"));
    }

    [Fact]
    public async Task Conceder_e_encerrar_mantendo_a_linha_do_historico()
    {
        var (gestorId, gestorNome, gestor) = await Gestor();
        var (empresa, razao) = await Empresa();
        var (id, _) = await Analista();

        var respostaConcede = await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = new[] { empresa } });
        Assert.Equal(HttpStatusCode.OK, respostaConcede.StatusCode);
        var concede = await Json(respostaConcede);
        Assert.Equal([razao], concede.GetProperty("concedidas").EnumerateArray().Select(x => x.GetString()));
        Assert.Empty(concede.GetProperty("encerradas").EnumerateArray());
        Assert.Equal("executor", await banco.Escalar<string>(
            $"SELECT papel_projeto FROM alocacao WHERE usuario_id = {id} AND empresa_id = {empresa} AND fim IS NULL"));
        Assert.Equal(gestorId, await banco.Escalar<int>(
            $"SELECT alocado_por FROM alocacao WHERE usuario_id = {id} AND empresa_id = {empresa}"));

        var encerra = await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = Array.Empty<int>() });
        Assert.Equal([razao], (await Json(encerra)).GetProperty("encerradas").EnumerateArray().Select(x => x.GetString()));
        Assert.Equal($"acesso encerrado por {gestorNome}", await banco.Escalar<string>(
            $"SELECT motivo_saida FROM alocacao WHERE usuario_id = {id} AND empresa_id = {empresa} AND fim IS NOT NULL"));

        // alocar de novo cria outra linha: o histórico fica com as duas passagens
        await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = new[] { empresa } });
        Assert.Equal(2, await banco.Escalar<long>($"SELECT count(*) FROM alocacao WHERE usuario_id = {id} AND empresa_id = {empresa}"));

        // e o escopo do login acompanha
        var noLogin = (await Json(await gestor.GetAsync("/api/usuarios"))).EnumerateArray()
            .Single(u => u.GetProperty("id").GetInt32() == id).GetProperty("empresas");
        Assert.Equal([empresa], noLogin.EnumerateArray().Select(e => e.GetInt32()));
    }

    [Fact]
    public async Task Sem_mudanca_nao_grava_nada()
    {
        var (_, _, gestor) = await Gestor();
        var (empresa, _) = await Empresa();
        var (id, _) = await Analista();
        await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = new[] { empresa } });

        var r = await Json(await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = new[] { empresa } }));

        Assert.Empty(r.GetProperty("concedidas").EnumerateArray());
        Assert.Empty(r.GetProperty("encerradas").EnumerateArray());
        Assert.Equal(1, await banco.Escalar<long>($"SELECT count(*) FROM alocacao WHERE usuario_id = {id}"));
    }

    [Fact]
    public async Task Ninguem_tira_o_proprio_acesso_mas_pode_se_conceder()
    {
        var (eu, _, gestor) = await Gestor();
        var (empresa, _) = await Empresa();

        var concede = await gestor.PutAsJsonAsync($"/api/usuarios/{eu}/empresas", new { empresas = new[] { empresa } });
        var tira = await gestor.PutAsJsonAsync($"/api/usuarios/{eu}/empresas", new { empresas = Array.Empty<int>() });

        Assert.Equal(HttpStatusCode.OK, concede.StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, tira.StatusCode);
        Assert.Contains("próprio acesso", await Detalhe(tira));
    }

    [Fact]
    public async Task Empresa_inexistente_e_recusada_e_nada_e_gravado()
    {
        var (_, _, gestor) = await Gestor();
        var (empresa, _) = await Empresa();
        var (id, _) = await Analista();

        var r = await gestor.PutAsJsonAsync($"/api/usuarios/{id}/empresas", new { empresas = new[] { empresa, 999999, 999998 } });

        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal("Empresa não encontrada: 999998, 999999", await Detalhe(r));
        Assert.Equal(0, await banco.Escalar<long>($"SELECT count(*) FROM alocacao WHERE usuario_id = {id}"));
    }

    [Fact]
    public async Task Acesso_de_quem_nao_existe_da_404_e_token_invalido_da_401()
    {
        var (_, _, gestor) = await Gestor();
        var anonimo = Cliente();
        anonimo.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", "invalido");

        Assert.Equal(HttpStatusCode.NotFound, (await gestor.GetAsync("/api/usuarios/999999/empresas")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized,
            (await anonimo.PutAsJsonAsync("/api/usuarios/1/empresas", new { empresas = Array.Empty<int>() })).StatusCode);
    }
}
