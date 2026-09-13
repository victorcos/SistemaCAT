using System.Text;
using Microsoft.Extensions.Configuration;

namespace Cat.Ferramentas;

// Classe com nome, e não instruções de nível superior: estas gerariam outro
// "Program", que colide com o da API nos testes que referenciam os dois.
public static class Entrada
{
    public static async Task<int> Main(string[] args)
    {
        // o console do Windows abre em página de código antiga, e a senha
        // provisória sairia ao lado de "usuÃ¡rio"
        Console.OutputEncoding = Encoding.UTF8;
        var configuracao = new ConfigurationBuilder().AddEnvironmentVariables().Build();
        return await Ferramentas.Executar(args, configuracao, Console.Out);
    }
}
