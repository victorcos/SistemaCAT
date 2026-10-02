using System.Security.Cryptography.X509Certificates;
using Cat.Infraestrutura.Configuracao;

namespace Cat.Api.Infra;

/// <summary>
/// O certificado que põe a API em HTTPS, lido de um par PEM.
///
/// PEM e não PFX porque é o que o `openssl` gera numa linha, é o que o
/// `frontend/tools/certificado.mjs` já produz, e é texto — some a senha do
/// arquivo, que seria um segredo a mais para guardar.
/// </summary>
public static class Tls
{
    /// <summary>
    /// Carrega o par e devolve um certificado que o Kestrel aceita.
    ///
    /// **O passeio pelo PKCS#12 não é supérfluo.** No Windows, um certificado
    /// vindo de `CreateFromPemFile` carrega a chave privada num provedor que o
    /// SChannel não usa, e o Kestrel falha no primeiro handshake com um erro que
    /// não menciona nem PEM nem chave. Exportar e reimportar devolve o mesmo
    /// certificado num formato que o sistema operacional sabe usar.
    /// </summary>
    public static X509Certificate2 Carregar(ConfigCat config)
    {
        if (!File.Exists(config.TlsCertificado) || !File.Exists(config.TlsChave))
            throw new FileNotFoundException(
                "CAT_TLS_CERTIFICADO e CAT_TLS_CHAVE apontam para arquivo que não existe. "
                + "Gere o par com `cd frontend && npm run certificado`, ou limpe as duas "
                + "variáveis para a API subir em HTTP.",
                File.Exists(config.TlsCertificado) ? config.TlsChave : config.TlsCertificado);

        using var doPem = X509Certificate2.CreateFromPemFile(
            config.TlsCertificado, config.TlsChave);
        return X509CertificateLoader.LoadPkcs12(
            doPem.Export(X509ContentType.Pkcs12), password: null);
    }
}
