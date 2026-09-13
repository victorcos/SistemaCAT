using System.Text;
using System.Text.Json;
using Cat.Aplicacao.Acesso;
using Cat.Dominio.Acesso;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;

namespace Cat.Infraestrutura.Auth;

/// <summary>
/// Emissão e leitura de JWT com as mesmas reivindicações do <c>python-jose</c>:
/// <c>sub</c> (id em texto), <c>usr</c>, <c>pap</c>, <c>emp</c>, <c>iat</c>, <c>exp</c>.
///
/// Token emitido de um lado vale do outro. É o que permite portar rota por
/// rota: quem entrou pelo login em C# segue usando as rotas que ainda estão no
/// Python, com a mesma sessão.
/// </summary>
public sealed class TokensJwt : IEmissorDeToken
{
    private readonly SymmetricSecurityKey _chave;
    private readonly int _minutos;
    private readonly TimeProvider _relogio;
    private readonly JsonWebTokenHandler _manipulador = new();

    public TokensJwt(string segredo, int minutos, TimeProvider relogio)
    {
        _chave = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(segredo));
        _minutos = minutos;
        _relogio = relogio;
    }

    public (string Token, int ExpiraEmSegundos) Emitir(Usuario usuario)
    {
        var agora = _relogio.GetUtcNow().ToUnixTimeSeconds();
        // A carga é escrita à mão, e não por descritor de token: o descritor
        // acrescenta nbf e reordena campos. Igual ao Python é mais fácil de
        // conferir do que "equivalente".
        var carga = JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["sub"] = usuario.Id.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["usr"] = usuario.NomeDeUsuario,
            ["pap"] = usuario.Papel.Valor(),
            // escopo de empresa viaja no token para a API não consultar a cada
            // requisição; a fonte continua sendo a alocação vigente no banco
            ["emp"] = usuario.Empresas,
            ["iat"] = agora,
            ["exp"] = agora + _minutos * 60L,
        });
        var token = _manipulador.CreateToken(carga, new SigningCredentials(_chave, SecurityAlgorithms.HmacSha256));
        return (token, _minutos * 60);
    }

    public async Task<ConteudoDoToken> Ler(string token)
    {
        var resultado = await _manipulador.ValidateTokenAsync(token, new TokenValidationParameters
        {
            IssuerSigningKey = _chave,
            ValidAlgorithms = [SecurityAlgorithms.HmacSha256],
            // o Python não emite emissor nem audiência
            ValidateIssuer = false,
            ValidateAudience = false,
            ValidateLifetime = true,
            // o python-jose não tolera atraso de relógio; os dois lados precisam
            // expirar a sessão no mesmo segundo
            ClockSkew = TimeSpan.Zero,
            LifetimeValidator = (_, expira, _, _) => expira is null || expira > _relogio.GetUtcNow().UtcDateTime,
        });
        if (!resultado.IsValid)
            throw new TokenInvalido(resultado.Exception?.Message ?? "token recusado");

        var jwt = (JsonWebToken)resultado.SecurityToken;
        try
        {
            var papelTexto = jwt.GetPayloadValue<string>("pap");
            if (!TextoDeAcesso.TentarPapel(papelTexto, out var papel))
                throw new TokenInvalido($"conteúdo inesperado: papel {papelTexto}");
            var empresas = jwt.TryGetPayloadValue<int[]>("emp", out var emp) ? emp : [];
            return new ConteudoDoToken(
                int.Parse(jwt.Subject, System.Globalization.CultureInfo.InvariantCulture),
                jwt.GetPayloadValue<string>("usr"),
                papel,
                empresas);
        }
        catch (Exception erro) when (erro is ArgumentException or FormatException or OverflowException
                                         or SecurityTokenException)
        {
            throw new TokenInvalido($"conteúdo inesperado: {erro.Message}");
        }
    }
}
