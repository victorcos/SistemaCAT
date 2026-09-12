# CONTRATOS — interfaces entre camadas

> Responsabilidade única: o que cada camada promete à outra. Ler antes de mexer
> em qualquer módulo. Contrato quebrado sem atualizar este arquivo é bug.

---

## 1. Portas que a aplicação declara

A camada `aplicacao` nunca importa implementação concreta. Ela declara a
interface e recebe a implementação pronta. É o que permite testar caso de uso
sem banco, sem rede e sem arquivo grande.

| Porta | Promete | Implementada em |
|---|---|---|
| `LeitorDeArquivoFiscal` | percorrer registros de um pacote (rar, zip, txt) em fluxo, sem carregar tudo | `infraestrutura/arquivos/` |
| `RepositorioAnalitico` | agregar e consultar grandes volumes | `infraestrutura/analitico/` |
| `EscritorDePlanilha` | gravar resultado tabular com tipagem correta | `infraestrutura/planilhas/` |
| `RepositorioProjeto` | persistir empresa, projeto, alocação, execução | `infraestrutura/repositorios/` |
| `ServicoDeJulgamento` | decidir casos que a cascata não resolveu | `infraestrutura/ia/` |
| `RegistradorDeExecucao` | abrir, atualizar e fechar uma execução com log | `infraestrutura/repositorios/` |

## 2. Invariantes do domínio

Coisas que o domínio garante e que ninguém pode violar por fora.

- **Valor monetário nunca é `float`.** A Ficha 3 grava quinze casas decimais;
  arredondar cedo desloca o total.
- **Ressarcimento nunca é negativo.** É diferença positiva, ou zero.
- **Complemento só existe no enquadramento legal 1.** Ver DOMINIO.md, seção 6.
- **Código de item não é reutilizável** e não muda entre períodos.
- **Devolução lança nas mesmas colunas da origem, com sinal invertido.**

## 3. Formato entre etapas

Parquet, com esquema declarado. CSV e xlsx só na fronteira com o cliente.

Toda saída derivada carrega, na primeira coluna ou no metadado do arquivo, o
identificador da execução que a gerou. Sem isso não há rastreabilidade.

## 4. Contrato de log

Todo ponto de entrada de camada abre contexto de log com identificador da
execução, projeto, empresa, usuário e etapa. Detalhe em ARQUITETURA.md, seção 12.

## 5. Contrato de acesso

Nenhuma consulta a dado fiscal é feita sem escopo de empresa derivado da
**alocação vigente** do usuário ao projeto. O filtro é aplicado numa camada só,
no backend, e reforçado por segurança em nível de linha no banco. Nunca no front.

---

## 6. Histórico do trabalho — contrato para o front

Seis rotas. Quem vê o trabalho vê o histórico inteiro; o escopo por empresa já
limita o alcance, e dentro de um trabalho não há segredo entre quem trabalha
nele.

| Método | Rota | Quem | O que faz |
|---|---|---|---|
| `GET` | `/api/projetos/{id}/historico` | quem vê o trabalho | a linha do tempo |
| `POST` | `/api/projetos/{id}/historico/comentarios` | quem escreve | comenta |
| `GET` | `/api/status-de-projeto` | autenticado | o catálogo de status |
| `PATCH` | `/api/projetos/{id}/status` | quem escreve | muda o status |
| `GET` | `/api/projetos/{id}/sucessores` | quem vê o trabalho | quem pode receber |
| `PATCH` | `/api/projetos/{id}/responsavel` | **gestor ou dev** | passa o trabalho |

### A linha do tempo

`GET /api/projetos/{id}/historico?antes_de=&quantos=50&so_comentarios=false`

```json
{
  "eventos": [
    {
      "id": 42,
      "tipo": "status",
      "rotulo_do_tipo": "Status alterado",
      "texto": "Esperando o XML de 2023.",
      "dados": {"de": "em_andamento", "para": "pausado",
                "frase": "Em andamento → Pausado"},
      "autor": "Gestora do Histórico",
      "autor_id": 7,
      "quando": "2026-09-12T14:31:07.882Z",
      "e_comentario": false
    }
  ],
  "tem_mais": true,
  "proximo_cursor": 42
}
```

**Do mais recente para o mais antigo**, e a paginação é por cursor
(`antes_de` = `proximo_cursor` da página anterior), nunca por `offset`: com
evento entrando enquanto se lê, offset repete linha e pula linha.

`tipo` é um destes, e `rotulo_do_tipo` já vem traduzido — a tela não reescreve
nenhum: `criado`, `comentario`, `status`, `sucessao`, `lote_importado`,
`lote_removido`, `etapa_iniciada`, `etapa_concluida`, `etapa_falhou`,
`planilha_baixada`. Tipo desconhecido (versão mais nova gravando) chega como
comentário em vez de sumir da linha do tempo.

`e_comentario` é o que separa o que a pessoa escreveu do que o sistema
registrou — é por ele que a tela decide o desenho de cada linha. `dados`
carrega o que mudou, para quem quiser reconstruir; `dados.frase` já vem pronta
nos eventos de status e sucessão.

### Status

Quatro, e `GET /api/status-de-projeto` devolve rótulo, explicação e
`exige_motivo` de cada um:

| valor | rótulo | exige motivo | roda etapa |
|---|---|---|---|
| `em_andamento` | Em andamento | não | sim |
| `pausado` | Pausado | **sim** | **não** |
| `cancelado` | Cancelado | **sim** | **não** |
| `concluido` | Concluído | não | sim |

`PATCH /api/projetos/{id}/status` com `{"status": "...", "motivo": "..."}`.
Recusa com **422** quando o status é o mesmo ou quando falta motivo em pausar
e cancelar.

**O status vale de verdade:** iniciar conferência ou extração num trabalho
pausado ou cancelado responde **422** com a explicação — não é só uma cor no
cartão.

### Sucessão

`GET /api/projetos/{id}/sucessores` lista quem pode receber: conta **ativa** e
papel que escreve (dev, gestor, analista, revisor). Conta desativada não
aparece e é recusada se tentada — é assim que um trabalho fica sem dono sem
ninguém perceber.

`PATCH /api/projetos/{id}/responsavel` com `{"responsavel_id": 7, "motivo": ""}`.
**403** para quem não é gestor nem dev; **422** para sucessor inexistente,
desativado ou que já responde pelo trabalho.

### O que o resumo do projeto passou a trazer

`GET /api/projetos` e `GET /api/projetos/{id}` agora incluem, em cada projeto:

```
status, status_rotulo, criado_por, criado_por_id,
responsavel, responsavel_id, comentarios
```

`criado_por` e `responsavel` são **nomes de exibição**, não identificadores: a
tela mostra gente, e buscar cada nome depois seria uma consulta por cartão.
São campos diferentes de propósito — quem criou não muda nunca; quem responde
muda a cada sucessão.

### Acesso às empresas (escopo de visibilidade)

Duas rotas, **só para gestor e dev**, na tela de Usuários:

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/usuarios/{id}/empresas` | todas as empresas, com `tem_acesso` e `desde` |
| `PUT` | `/api/usuarios/{id}/empresas` | `{"empresas": [1, 3]}` — faz o acesso ser exatamente essa lista |

A resposta do `PUT` diz o que mudou: `{"concedidas": [...], "encerradas": [...]}`,
com os nomes das empresas.

**Tirar acesso não apaga a alocação** — preenche `fim` e `motivo_saida`, como
o modelo pede desde o começo: é o que permite responder, meses depois, quem
tinha acesso a um dado em determinado mês. Alocar de novo cria linha nova, e
o histórico fica com as duas passagens.

**Ninguém tira o próprio acesso** (422): evita alguém se trancar para fora por
engano.

**Gestor e dev ignoram o escopo por definição do papel** — alocação neles não
muda nada, e a tela avisa. O gestor responde pela carteira inteira da casa; o
dev precisa reproduzir problema em qualquer cliente. A diferença entre os dois
está no log: o acesso do dev sem alocação é registrado como exceção, o do
gestor não, porque é o escopo normal do papel.

Essas rotas continuam existindo para **quem executa** — analista, revisor e
leitura —, que é quem de fato tem recorte de carteira.
