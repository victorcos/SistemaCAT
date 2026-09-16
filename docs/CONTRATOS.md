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

### Formato das listas (xlsx ou csv)

As sete listas do sistema — três da conferência, quatro da movimentação — saem
nos dois formatos pela mesma rota, com `?formato=`:

| Valor | Content-Type | Para quê |
|---|---|---|
| `xlsx` (padrão) | `application/vnd.openxmlformats-…` | abrir e ler |
| `csv` | `text/csv; charset=utf-8` | carregar em outra ferramenta, ou lista grande demais para o Excel |

Formato desconhecido dá **404**. O nome do arquivo em cache carrega o formato,
senão o xlsx já gerado responderia ao pedido de csv.

O CSV sai com `;`, vírgula decimal, data `dd/mm/aaaa` e **BOM** — é o que o
Excel em português lê sem configurar nada. O que ele não faz é alterar valor
para agradar o Excel: a chave de acesso vai com os 44 dígitos que tem. Aberto
com dois cliques no Excel, isso vira notação científica e não volta. Para
Excel, xlsx.

O download é do navegador para o arquivo que a pessoa escolher, sem passar
pela memória, e pode ser cancelado no meio. Cancelar descarta o arquivo
parcial: meia planilha no disco é pior que nenhuma. A geração no servidor,
essa, segue até o fim e fica em cache.

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

## 7. Apuração do ICMS suportado (etapa 4)

Mesmo desenho das etapas 2 e 3: pedir a rodada, acompanhar, baixar. Duas
rotas a mais — cancelar e o analítico paginado.

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/projetos/{id}/suportado` | põe a rodada na fila (202). 422 sem movimentação concluída; 409 com outra em curso |
| `GET` | `/api/projetos/{id}/suportado` | as rodadas, mais recente primeiro |
| `GET` | `/api/suportado/{execucao}` | uma rodada, com o resumo |
| `POST` | `/api/suportado/{execucao}/cancelar` | na fila cancela na hora; rodando vira `cancelando` e para no próximo ponto seguro. 409 se já terminou |
| `GET` | `/api/suportado/{execucao}/linhas` | uma página do analítico: `escopo=documento\|item`, `fonte`, `busca`, `pagina`, `por_pagina` (teto 200) |
| `GET` | `/api/suportado/{execucao}/planilhas/suportado` | a lista inteira; `classificacoes=<fonte>` filtra, `formato=csv` troca o formato |

Situações da rodada: `na_fila`, `rodando`, `cancelando`, `concluida`,
`falhou`, `cancelada`. **`cancelando` ainda é em curso** — o roteiro mostra a
etapa em andamento e uma nova rodada é recusada até ela parar.

Fontes, na ordem da cascata: `documento`, `informado_pelo_fornecedor`,
`base_e_aliquota`, `nao_apuravel`. As duas primeiras são documentais.

O resumo (`versao: 2`) traz `itens`, `apurados`, `cobertura`, `valor_total`,
`valor_documental`, `fracao_documental`, `por_fonte` (sempre as quatro, na
ordem, com `documental` nulo no não apurável), `por_pendencia`
(`sem_o_que_apurar`, `falta_dado`), `por_cst`, `por_competencia` (com a
cobertura do mês), `estabelecimentos`, `cst_sem_o_que_apurar`, `iniciada_por`,
`relatorios` e `log` (`em`, `nivel`, `texto`). Enquanto roda, só `andamento`
(`itens`, `apurados`, `estabelecimentos`, `total`) e `log`. Valor em dinheiro
vai como texto, porque Decimal não é JSON.

Resumo **sem** `versao` é de antes desta forma: a tela pede para rodar de novo.

## 8. Razão dos itens (etapa 5)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/projetos/{id}/razao` | põe a montagem na fila (202). 422 sem movimentação ou apuração do suportado concluídas, ou com apuração que não gravou data e CFOP |
| `GET` | `/api/projetos/{id}/razao` | as rodadas, mais recente primeiro |
| `GET` | `/api/razao/{execucao}` | uma rodada, com o resumo |
| `POST` | `/api/razao/{execucao}/cancelar` | como na etapa 4 |
| `GET` | `/api/razao/{execucao}/fichas` | lista de fichas, válidas primeiro e maior ressarcimento: `busca`, `so` (validas, retiradas, negativas, sem_aliquota, indefinidas, divergentes, suspeita_unidade, sem_fator), `pagina`, `por_pagina` |
| `GET` | `/api/razao/{execucao}/ficha` | linhas de uma ficha: `cnpj`, `codigo` (obrigatórios), `pagina`, `por_pagina` |
| `GET` | `/api/razao/{execucao}/planilhas/ficha3` | a Ficha 3 inteira (CSV recomendado) |
| `GET` | `/api/razao/{execucao}/planilhas/fichas` | o resumo por ficha |

O resumo (`versao: 1`) traz `periodo_inicio`, `periodo_fim`, `abertura_em`,
`codigos_com_st`, `fichas`, `estabelecimentos`, `linhas`, `ressarcimento`,
`complemento`, `por_enquadramento` (`codigo` 1, 2, 3, 4, 0 ou `indefinido`, com
linhas, quantidade, suportado baixado, confronto, ressarcimento e complemento),
`por_competencia`, `saidas_por_origem` (`efd`, `relatorio`), `pendencias` e
`relatorios` (`arquivos`, `so_de_entradas`, `recusados`, `linhas`), `retiradas`
(`fichas`, `linhas`, `ressarcimento`, `complemento` das fichas com estoque
negativo, fora do total), `conversao`, `saidas_com_aliquota_do_mes` (saídas
confrontadas com a alíquota do 0200 do próprio mês, diferente da do fim do
período) e `conferencia_inventario`. Enquanto roda, `andamento` com `linhas`,
`total` e `fichas`.

A alíquota do confronto (enquadramentos 1 e 3) é a do 0200 da EFD do **mês da
saída**; só quando o mês não traz alíquota vale a do cadastro mais recente. A
unidade é sempre a do cadastro mais recente.

Cada linha da ficha: `numero`, `data`, `especie` (`entrada`/`saida`),
`devolucao`, `cfop`, `documento`, `origem`, `enquadramento` (nulo em entrada,
devolução e indefinido), `enquadramento_indefinido`, `quantidade` (com sinal),
`icms_suportado`, `valor_unitario_usado`, `icms_efetivo` (valor de confronto,
nulo quando não se apura), `saldo_quantidade`, `saldo_unitario`, `saldo_valor`,
`ressarcimento`, `complemento`.

## 9. Apuração do período (etapa 6)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/projetos/{id}/apuracao` | põe o fechamento na fila (202). 422 sem razão concluído |
| `GET` | `/api/projetos/{id}/apuracao` | as rodadas, mais recente primeiro |
| `GET` | `/api/apuracao/{execucao}` | uma rodada, com o resumo |
| `POST` | `/api/apuracao/{execucao}/cancelar` | como nas etapas 4 e 5 |
| `GET` | `/api/apuracao/{execucao}/competencias` | uma página das competências: `so` (aptas, bloqueadas ou o código de um motivo), `busca`, `pagina`, `por_pagina` |
| `GET` | `/api/apuracao/{execucao}/planilhas/apuracao` | uma linha por estabelecimento e mês |
| `GET` | `/api/apuracao/{execucao}/planilhas/saldos` | os saldos por mercadoria e mês — o registro 1050 |

O resumo (`versao: 1`) traz `competencias`, `aptas`, `estabelecimentos`,
`estabelecimentos_aptos`, `itens`, `linhas`, `saldos`, `ressarcimento`,
`complemento`, `credito_operacao_propria`, **`ressarcimento_apto`** e
`complemento_apto` (só das competências sem pendência), `por_competencia` e
`por_motivo` (código, rótulo, o que fazer, quantas competências).

**Ressarcimento e complemento nunca vêm somados** — um é crédito a pedir, o
outro é imposto a recolher, e o líquido é leitura, não o valor do pedido.

Cada competência traz `apta` e `motivos` (código, rótulo e o que fazer). Os
motivos possíveis: `fora_de_sp`, `ficha_retirada`, `confronto_pendente`,
`sem_aliquota`, `enquadramento_indefinido`, `diverge_do_inventario` e
`sem_inventario`.

A linha da Ficha 3 guarda também o documento, para o arquivo digital: `chave`,
`numero_item`, `modelo`, `participante` e `numero_documento`. A venda de PDV do
relatório fica sem chave e sem `numero_item`. O resumo do razão diz
`venda_a_consumidor`, a escolha do trabalho com que foi montado.

## 10. Venda a consumidor final (escolha do trabalho)

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/venda-a-consumidor` | as duas leituras: `valor`, `rotulo`, `explicacao` |
| `PUT` | `/api/projetos/{id}/venda-a-consumidor` | `{"valor": "enquadramento_1" \| "demais_saidas"}`; devolve o cartão do trabalho. 409 se já está assim, 422 valor desconhecido; grava evento `parametro_alterado` com `de` e `para` |

O cartão do trabalho traz `venda_a_consumidor` e `venda_a_consumidor_rotulo`.
Em `demais_saidas` o cupom e a venda comum dentro do estado vão ao
enquadramento 0; 5.927, interestadual e isenção não mudam.

## 11. Arquivo digital (etapa 7)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/projetos/{id}/arquivo-digital` | põe a geração na fila (202). 422 sem apuração, com razão mais novo que a apuração, com razão de outra escolha de venda a consumidor ou de antes do documento por linha |
| `GET` | `/api/projetos/{id}/arquivo-digital` | as rodadas, mais recente primeiro |
| `GET` | `/api/arquivo-digital/{execucao}` | uma rodada, com o resumo |
| `POST` | `/api/arquivo-digital/{execucao}/cancelar` | como nas etapas 4 a 6 |
| `GET` | `/api/arquivo-digital/{execucao}/arquivos` | uma página dos arquivos: `so` (`envio`, `previa` ou o código de uma trava), `busca`, `pagina`, `por_pagina` |
| `GET` | `/api/arquivo-digital/{execucao}/ocorrencias?arquivo=` | as ocorrências da pré-validação de um arquivo, erros primeiro |
| `GET` | `/api/arquivo-digital/{execucao}/planilhas/arquivos` | o índice dos arquivos, com tamanho e SHA-256 (xlsx ou csv) |
| `GET` | `/api/arquivo-digital/{execucao}/planilhas/ocorrencias` | as ocorrências de todos os arquivos (xlsx ou csv) |
| `GET` | `/api/arquivo-digital/{execucao}/planilhas/envio` | zip com os TXT prontos para a SEFAZ |
| `GET` | `/api/arquivo-digital/{execucao}/planilhas/previas` | zip com as prévias — nunca junto do envio |

Um arquivo por estabelecimento **de SP** e por mês, com nome
`CAT5_SP_<CNPJ>_<M>_<AAAA>.txt`; a prévia leva `_PREVIA` antes da extensão.
Vai para o envio só a competência `apta` na etapa 6, sem trava e sem erro na
pré-validação.

O resumo (`versao: 1`) traz `competencias` (de SP), `competencias_fora_de_sp`,
`arquivos`, `para_envio`, `previas`, `linhas`, `bytes`, `por_registro`,
`linhas_sem_documento`, `entradas_sem_icms` (1100/1200 de entrada escritos
com ICMS_TOT zero — não trava, avisa), `erros`, `avisos`, `itens_recompostos`,
`itens_que_fecham`, `ressarcimento_para_envio`, `complemento_para_envio`,
`venda_a_consumidor`, `por_trava` e `por_regra` (código, rótulo, severidade, o
que fazer, arquivos, ocorrências).

Cada arquivo traz `destino`, `apta`, `motivos` (da etapa 6), `travas` (desta),
contagem por registro, `linhas_sem_documento`, `entradas_sem_icms`,
`saldos_negativos`, `valores_negativos`, `erros`, `avisos`, `bytes` e
`sha256`. As travas: `nao_apta`, `sem_documento`, `saida_indefinida`,
`devolucao_sem_venda`, `confronto_pendente`, `saldo_negativo` (quantidade
negativa no 1050), `valor_negativo` (quantidade positiva e ICMS negativo),
`item_sem_cadastro`, `participante_sem_cadastro`, `sem_abertura` e
`pre_validacao`. O recorte `so` por trava compara o código inteiro.

De onde vem o cadastro: o 0200 é o da EFD do mês do arquivo (descrição, código
de barras, NCM, alíquota, CEST), com o mais recente onde o mês não diz, e a
unidade sempre a do mais recente, que é a da ficha. O 0150 é o da EFD do mês e,
quando o participante não está lá, o da EFD mais recente do estabelecimento
que o tenha.

## 12. Pré-validação dos arquivos do cliente

Fora do roteiro do trabalho: não depende de etapa nenhuma nem entra na conta
de etapas concluídas.

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/projetos/{id}/pre-validacao` | põe a pré-validação na fila (202). 422 se o lote não tem arquivo digital da CAT 42 nem zip |
| `GET` | `/api/projetos/{id}/pre-validacao` | as rodadas, mais recente primeiro |
| `GET` | `/api/pre-validacao/{execucao}` | uma rodada, com o resumo |
| `POST` | `/api/pre-validacao/{execucao}/cancelar` | como nas outras rodadas |
| `GET` | `/api/pre-validacao/{execucao}/arquivos` | uma página dos arquivos lidos: `so` (`com_erro`, `com_aviso`, `sem_ocorrencia`, `repetidos`), `busca`, `pagina`, `por_pagina` |
| `GET` | `/api/pre-validacao/{execucao}/ocorrencias?arquivo=` | as ocorrências de um arquivo, erros primeiro |
| `GET` | `/api/pre-validacao/{execucao}/planilhas/arquivos` | o índice dos arquivos lidos, com origem e SHA-256 |
| `GET` | `/api/pre-validacao/{execucao}/planilhas/ocorrencias` | as ocorrências de todos os arquivos |

Lê do lote o tipo `cat42_arquivo_digital` (o TXT solto, reconhecido pelo
`0000|mmaaaa|` sem `|` no começo) e os zips, com um nível de zip aninhado.
Arquivo de outra raiz de CNPJ fica de fora e contado; o mesmo estabelecimento e
mês lido duas vezes fica como `repetido`, sem ler de novo. Dois arquivos
diferentes com o mesmo nome (outra ferramenta pode chamar todo mês de
`CAT42.txt`) não se misturam: o segundo ganha `(<CNPJ> <aaaa-mm>)` no nome,
que é a chave das ocorrências.

O resumo (`versao: 1`) traz `fontes`, `arquivos`, `sem_ocorrencia`, `com_erro`,
`com_aviso`, `repetidos`, `de_outra_empresa`, `nao_sao_da_cat42`, `ilegiveis`,
`linhas`, `bytes`, `erros`, `avisos`, `itens_recompostos`, `itens_que_fecham`,
`estabelecimentos`, `competencia_inicial`, `competencia_final` e `por_regra`.
Além das regras de cada arquivo, uma que só se vê com o conjunto:
`saldo_inicial_diferente_do_anterior` (aviso), quando o saldo inicial de um item
não é o final da última competência em que ele apareceu.
