using System.Text.Encodings.Web;
using System.Text.Json;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.EntityFrameworkCore;

namespace Cat.Infraestrutura.Banco;

public sealed class DeParaRepositorio(CatDbContext banco) : IRepositorioDeDePara
{
    private static readonly JsonSerializerOptions Json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    public async Task Decidir(int empresaId, int projetoId, IReadOnlyList<DecisaoDeDePara> decisoes, string texto,
        object dados, Usuario por, DateTimeOffset agora, CancellationToken cancelar)
    {
        await using var transacao = await banco.Database.BeginTransactionAsync(cancelar);
        var origens = decisoes.Select(d => d.Origem).Distinct().ToList();
        var existentes = await banco.DePara
            .Where(x => x.EmpresaId == empresaId && origens.Contains(x.CodigoOrigem))
            .ToDictionaryAsync(x => (x.Cnpj, x.CodigoOrigem), cancelar);
        // o Postgres guarda microssegundos: o resto dos ticks some ao gravar
        var quando = new DateTime(agora.UtcTicks - agora.UtcTicks % 10, DateTimeKind.Utc);
        foreach (var d in decisoes)
        {
            if (!existentes.TryGetValue((d.Cnpj, d.Origem), out var linha))
            {
                linha = new DeParaLinha { EmpresaId = empresaId, Cnpj = d.Cnpj, CodigoOrigem = d.Origem };
                banco.DePara.Add(linha);
            }
            linha.CodigoDestino = d.Destino;
            linha.Fator = d.Fator;
            linha.Motivo = d.Motivo;
            linha.Situacao = d.Situacao;
            linha.Confianca = d.Confianca;
            linha.Explicacao = d.Explicacao;
            linha.ProjetoId = projetoId;
            linha.DecididoPor = por.Id;
            linha.DecididoEm = quando;
        }
        banco.Eventos.Add(new EventoLinha
        {
            ProjetoId = projetoId, Tipo = TipoDeEvento.ParametroAlterado, Texto = texto,
            Dados = JsonSerializer.Serialize(dados, Json), AutorId = por.Id,
            AutorNome = string.IsNullOrEmpty(por.NomeExibicao) ? "Sistema" : por.NomeExibicao,
            CriadoEm = quando,
        });
        await banco.SaveChangesAsync(cancelar);
        await transacao.CommitAsync(cancelar);
        banco.ChangeTracker.Clear();
    }
}
