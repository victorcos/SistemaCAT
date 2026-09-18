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
`lote_removido`, `lote_reclassificado` (v0.55: `dados.arquivos`, `dados.lotes`,
`dados.uteis` e `dados.trocas` = `[{de, para, arquivos}]`), `etapa_iniciada`,
`etapa_concluida`, `etapa_falhou`, `planilha_baixada`. Tipo desconhecido (versão mais nova gravando) chega como
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
`relatorios` e `log` (`em`, `nivel`, `texto`); desde a v0.53, `itens_com_valor_do_xml` e
`itens_com_retido_do_xml` (ver §15). Enquanto roda, só `andamento`
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

O período do razão é o do **cadastro do trabalho** (sem ele, o da base); se ele
não cruza com a base, a montagem falha dizendo os dois períodos. `abertura`
traz `fichas_valoradas`, `fichas_parciais`, `fichas_sem_valor` e `icms` — o
ICMS da abertura pelas entradas até o dia do inventário (item 3.3.8); cada
ficha ganhou `abertura_valor` e `abertura_parcial`. `fora_da_ficha` traz
`uso_e_consumo` (lançamentos de CFOP de uso e consumo, que não entram na ficha).

A alíquota do confronto (enquadramentos 1 e 3) é a do 0200 da EFD do **mês da
saída**; só quando o mês não traz alíquota vale a do cadastro mais recente. A
unidade é sempre a do cadastro mais recente.

Cada linha da ficha: `numero`, `data`, `especie` (`entrada`/`saida`),
`devolucao`, `cfop`, `documento`, `origem`, `enquadramento` (nulo em entrada,
devolução e indefinido), `enquadramento_indefinido`, `quantidade` (com sinal),
`icms_suportado`, `valor_unitario_usado`, `icms_efetivo` (valor de confronto,
nulo quando não se apura), `saldo_quantidade`, `saldo_unitario`, `saldo_valor`,
`ressarcimento`, `complemento`.

### VL_ITEM é a base do ICMS (v0.60.0)

`itens_do_xml.parquet` ganha `frete`, `seguro`, `outras`, `bc_efetiva`,
`aliquota_efetiva`, `icms_efetivo` e `base_do_item` — a base da operação, na
ordem `vBC` → `vBCEfet` → mercadoria + frete + seguro + outras − desconto.
`movimentos.parquet` leva `base_do_item_xml`, e o razão passa a usar essa base
no `valor` da saída: é o VL_ITEM da Ficha 3 e a base do valor de confronto.
Sem XML, vale a base do C170; sem nenhuma das duas, o valor do item, como era
antes.

### Ficha 3 no leiaute do papel de trabalho (v0.59.0)

`ficha3.parquet` ganha `descricao` (do 0200 e, sem cadastro, do xProd do XML que o próprio estabelecimento emitiu — preenchida no fim da rodada, como já era na ficha), `ncm`, `unidade_estoque` e `valor_item` — nas entradas, o VL_ITEM vem da movimentação, porque a apuração do suportado guarda o imposto e não o valor do item. A
planilha da etapa sai com cabeçalho de três linhas (faixa do bloco, título e o
número do campo do leiaute, de 1 a 27) e com as colunas do papel de trabalho da
CAT 42, mais CST, origem, alíquota do confronto e redução de base. O CSV leva o
número junto do título ("Chave (3)"). O estilo do cabeçalho — `#001E50`, Arial
10 negrito branco — passa a valer em todas as planilhas do projeto.

### CST na Ficha 3 (v0.58.1)

`ficha3.parquet` grava `cst_icms` em toda linha, entrada e saída, como veio da
EFD ou do XML — a planilha traz a coluna "CST" e a tela mostra ao lado do CFOP.

### Alíquota da nota de entrada (v0.58.0)

Sem alíquota no 0200 — do mês, a mais recente, a do destino do de-para —, o
confronto usa a da **nota de entrada** da mesma mercadoria, pelo NCM e pela
mesma regra de data da redução, e só de **entrada interna** (CFOP 5.xxx no XML
do fornecedor, 1.xxx na EFD): compra de fora vem a 4%, 7% ou 12%, que não é a
tributação interna da mercadoria. `ficha3.parquet` ganha `aliquota` (a que fez o
confronto) e o resumo do razão traz `aliquota_da_entrada` (quantas saídas
vieram dela).

### Redução de base herdada da entrada (v0.57.0)

O ICMS efetivo do **enquadramento 1** incide sobre a base reduzida quando a
entrada da mercadoria declara redução (CST 20 ou 70). O percentual sai do `vBC`
da nota — `1 - vBC / (vProd - vDesc)` —, não do `pRedBC`, e a chave é o NCM (o
da nota, o do 0200 quando falta). `ficha3.parquet` ganha `reducao_base` (%, nula
quando não houve), `fichas.parquet` ganha `saidas_com_reducao`, e o resumo do
razão traz `reducao_de_base` com `saidas` e `efetivo_reduzido`. Enquadramentos
2, 3 e 4 seguem como antes.

### Estoque negativo (v0.56.0)

A ficha cujo saldo ficaria negativo abre com a quantidade que faltaria, sem
ICMS suportado, e entra no total. `fichas.parquet` ganha
`abertura_por_saldo_negativo`; `ficou_negativo` continua marcando a
inconsistência e `retirada` fica falso (rodadas até a v0.55.4 podem ter
`retirada` verdadeiro). O resumo do razão traz `abertas_por_saldo_negativo`
(`fichas`, `quantidade`). Na apuração, `fichas_negativas` conta as mercadorias
assim na competência, e o motivo de bloqueio `estoque_negativo` impede o
arquivo digital até alguém conferir.

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
`pre_validacao`. O recorte `so` por trava compara o código inteiro. O 1200 leva
a série do documento (SER, sem máscara) quando a movimentação a guarda.

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
mês lido duas vezes fica como `repetido`, sem ler de novo — salvo a substituição
(COD_FIN 02) lida depois de um original: ela é validada e o original fica
`repetido` e `substituido`, fora dos totais, das ocorrências e da continuidade.
Cada arquivo traz `finalidade`; o recorte `so` aceita também `substituidos`, e o
resumo traz `substituidos`. Dois arquivos
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

## 13. Relatórios e entrega (etapa 8)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/projetos/{id}/entrega` | põe a montagem na fila (202). 422 sem arquivo digital, ou com apuração mais nova que a usada pelo arquivo digital |
| `GET` | `/api/projetos/{id}/entrega` | as rodadas, mais recente primeiro |
| `GET` | `/api/entrega/{execucao}` | uma rodada, com o resumo, `aprovada_por` (nome) e `aprovada_em` |
| `POST` | `/api/entrega/{execucao}/cancelar` | como nas outras rodadas |
| `POST` | `/api/entrega/{execucao}/aprovar` | `{"observacao": "..."}` opcional (até 500). Só revisor ou gestor (403 aos outros, dev incluído). 409 se a rodada não concluiu, já foi aprovada, há entrega mais nova, o arquivo digital foi gerado de novo depois dela ou o trabalho está parado; 422 observação longa. Grava `aprovada_por`/`aprovada_em` na execução e o evento `entrega_aprovada` |
| `GET` | `/api/entrega/{execucao}/estabelecimentos` | uma página: `so` (`no_dossie`, `fora_do_dossie`, `com_previa`, `fora_de_sp`), `busca`, `pagina`, `por_pagina` |
| `GET` | `/api/entrega/{execucao}/planilhas/pacote?formato=zip` | o pacote: `MANIFESTO.txt`, `relatorio_da_entrega.xlsx` e `dossie/<CNPJ>/…` |
| `GET` | `/api/entrega/{execucao}/planilhas/relatorio` | só o relatório (xlsx; outro formato é 404) |

**A etapa conclui com a aprovação.** A rodada termina como `concluida`, com o
passo `Aguardando aprovação`; no roteiro do trabalho a etapa aparece
`em_andamento` até alguém aprovar a última entrega montada. Toda execução
passa a trazer `aprovada_por` e `aprovada_em` (nulos fora da entrega).

O resumo (`versao: 1`) traz `competencias`, `competencias_de_sp`, `para_envio`,
`previas`, `fora_de_sp`, `sem_arquivo`, `estabelecimentos`,
`estabelecimentos_no_dossie`, `ressarcimento`, `complemento`,
`ressarcimento_para_envio`, `complemento_para_envio`, `arquivos_no_dossie`,
`arquivos_no_pacote`, `bytes_do_pacote`, `sha256_do_pacote`, `por_gravidade`
(`trava`, `atencao`, `informacao`), `pendencias` (etapa onde se resolve, nome
da etapa, código, rótulo, quantidade e unidade da primeira medida, gravidade,
o que fazer e `medidas` — o mesmo problema como cada etapa o viu: quantidade,
unidade, etapa) e o id de cada
execução usada (`arquivo_digital_execucao_id`, `apuracao_execucao_id`,
`razao_execucao_id`, `st_suportado_execucao_id`, `movimentos_execucao_id`,
`conferencia_execucao_id`).

O relatório tem as abas Resumo, Filial x competência (toda competência, com a
situação e o que falta), Por filial, Por mês, Pendências e Trilha. O dossiê de
cada estabelecimento com competência pronta leva os TXT de envio (SHA-256
conferido contra o da etapa 7), `ficha3_<CNPJ>.csv`, `saldos_1050_<CNPJ>.xlsx`,
`apuracao_<CNPJ>.xlsx` e `pre_validacao_<CNPJ>.xlsx`, só daquelas competências.

## 14. Cadastro do trabalho

| Método | Rota | O que faz |
|---|---|---|
| `PATCH` | `/api/projetos/{id}/cadastro` | `{"nome", "competencia_ini", "competencia_fim"}`, todos opcionais (datas `AAAA-MM-DD`); o que não vem fica. Quem escreve (403 a leitura). 409 se nada muda ou o nome já existe na frente e empresa; 422 nome curto, data inválida ou final antes da inicial. Grava o evento `parametro_alterado` com `parametro: cadastro`, `de` e `para`, e devolve o cartão do trabalho |

O detalhe do trabalho (`GET /api/projetos/{id}`) traz `base`: `efds` (EFD
importadas), `primeira` e `ultima` competência, e `fora_do_periodo` (quantas EFD
caem fora do período do cadastro, comparando mês, não dia). A tela do trabalho
avisa quando `fora_do_periodo` é maior que zero.

## 15. Itens do XML (etapa 3)

A extração de movimentos lê, depois das EFD, os arquivos do lote do tipo
`xml_nfe` — que desde a v0.53 inclui o CF-e SAT (`<CFe>`), e cujo rótulo passou
a "XML de NF-e ou CF-e". A barra conta EFD e XML juntos; o passo da segunda
fase é "Lendo os itens dos XML". Desde a v0.54.0 o lote tem também o tipo
`xml_compactado` ("Zip de XML", alimenta): zip com XML de NF-e ou CF-e, com
`detalhe` = "N XML" e o CNPJ da primeira nota. As etapas 2 e 3 leem os membros
do zip — e de um nível de zip dentro dele — sem extrair; a barra conta um por
XML de dentro, e `arquivo` vira `lote.zip > nota.xml`. Evento de cancelamento
dentro do zip vai para `chaves_canceladas.parquet`. O zip `xml_compactado`
também é fonte da pré-validação dos arquivos do cliente.

### Certificado digital (v0.55.1)

A inspeção do lote não abre pasta com "certificado(s)" no nome nem lê .pfx,
.p12 ou compactado com essa palavra no nome; não os devolve em `arquivos` e
avisa só a contagem ("N pasta(s) de certificado e N arquivo(s) de certificado
ficaram de fora sem ser abertos"). Pasta escolhida que é de certificado, ou
está dentro de uma, dá 422. Nos zips (etapas 2 e 3, classificação e
pré-validação), membro de certificado é pulado sem aparecer em log nem em
recusados.

### Arquivo já no trabalho com outro tipo (v0.55)

`POST /interno/lotes/inspecionar` devolve, em cada arquivo já no trabalho,
`tipo_no_trabalho` (o tipo gravado). Na API:

* `POST /api/projetos/{id}/lotes/inspecionar` ganha `reclassificados`: quantos
  arquivos já no trabalho são reconhecidos hoje como outro tipo;
* `POST /api/projetos/{id}/lotes` atualiza esses arquivos onde estão (tipo,
  CNPJ, competência, UF, detalhe, retificadora), refaz `arquivos_uteis` e o
  período dos lotes tocados e grava `lote_reclassificado`. A resposta é o lote
  mais `criado` e `reclassificados`: 201 com o lote novo quando havia arquivo
  novo; 200 com o lote onde mais arquivos mudaram quando nada era novo. 409
  "Todos os arquivos desta pasta já estão neste trabalho" só quando nada é novo
  e nada mudou de tipo.

### Cópias e notas não autorizadas (v0.55)

A mesma chave em mais de um XML (solto e no zip, em dois zips) é lida uma vez.
Nas etapas 2 e 3, nota com protocolo cujo `cStat` não é 100 nem 150 (uso
denegado) sai com todas as cópias. Na etapa 3, a cópia com protocolo autorizado
vence a sem protocolo; entre iguais, a primeira na ordem do caminho.
`itens_do_xml.parquet` ganha `protocolo` (o `cStat`, vazio sem protocolo) e
`leitura` (a ordem do arquivo lido).

* resumo da conferência (etapa 2): `xml_repetidos`, `xml_nao_autorizados`, e
  aviso quando há nota denegada;
* resumo da etapa 3: `xml_nao_autorizados` e `xml_copias_trocadas`, além do
  `xml_repetidos` que já existia, e aviso quando há nota denegada. A nota
  denegada não completa a EFD nem entra na contingência.

`movimentos.parquet` ganha colunas:

| Coluna | O que é |
|---|---|
| `fonte_item` | `efd` (C170/C810) ou `xml` (item que o XML trouxe para documento escriturado sem item) |
| `codigo_xml`, `gtin_xml`, `descricao_xml`, `ncm_xml`, `cest_xml`, `unidade_xml`, `quantidade_xml` | o item do XML. No C170, só quando casa: mesma chave, mesmo número do item e valor a um centavo |
| `valor_icms_xml`, `bc_st_xml`, `valor_st_xml`, `fcp_st_xml` | o destacado no XML |
| `retido_xml` | ICMS suportado antes, como o XML informa no CST 60 (`vICMSSubstituto` + `vICMSSTRet` + `vFCPSTRet`) |
| `arquivo_xml` | nome do arquivo do XML |
| `cadastro_da_efd` | o código está no 0200. Sem ele, `descricao`, `codigo_barras`, `ncm` e `cest` vêm do XML |

`consumidor_final_xml` é o `indFinal` da NF-e (NFC-e e CF-e: verdadeiro). Um
C170 só ganha as colunas do XML quando o item casa pelo número e pela
quantidade ou pelo valor; pela contagem, só em nota de um item.

O item com `fonte_item = xml` tem `registro = XML` e o documento da EFD
(estabelecimento, operação, data, participante, número). Documento cancelado ou
denegado não é completado. Na entrada de terceiros, o `cfop` é o do analítico
do documento quando é um só, e senão o do XML com o primeiro dígito do lado de
quem recebeu.

O resumo da etapa 3 ganha `xml_arquivos`, `xml_documentos`, `xml_itens`,
`xml_repetidos`, `xml_nao_sao_documento`, `xml_ilegiveis`,
`saidas_completadas_pelo_xml`, `entradas_completadas_pelo_xml`,
`movimentos_do_xml`, `itens_pareados_com_xml` e `itens_sem_par_no_xml`. Execução
anterior não tem nenhum deles.

Na etapa 4, quando a movimentação tem as colunas do XML, o valor do XML vence o
do C170 (`valor_icms`, `valor_st`, `bc_st`, mais o FCP-ST) e o retido do XML
vence o do relatório do cliente. No razão (etapa 5), a saída que veio do XML
tem `origem = xml`, e ela também troca a linha do relatório com a mesma chave.

### Canceladas na SEFAZ (v0.54.0)

Dois tipos de arquivo do lote, ambos com `alimenta_a_cat`:

| Tipo | Rótulo | O que é |
|---|---|---|
| `xml_cancelamento` | Evento de cancelamento de NF-e | `procEventoNFe` com `tpEvento` 110111; `cnpj` e `competencia` saem da chave |
| `lista_de_canceladas` | Lista de notas canceladas | TXT/CSV com "cancel" no nome e chave em metade das linhas, ou planilha com "cancel" no nome e chave como texto |

A etapa 3 lê os dois depois dos XML (passo "Lendo as notas canceladas") e grava
`chaves_canceladas.parquet` (`chave`, `arquivo`, `origem` = `evento` ou
`lista`). Movimento de chave cancelada — C170 ou item do XML — não vai para
`movimentos.parquet`; o documento continua em `documentos.parquet`. O resumo
ganha `chaves_canceladas`, `documentos_cancelados_na_sefaz` e
`movimentos_cancelados`, e um aviso quando há documento cancelado. Execução
anterior não tem esses campos.

Lista de canceladas em planilha (v0.55.4): vale só a aba com "cancel" no nome
(sem nenhuma, todas menos a de "devol"), e a linha cujo retorno da SEFAZ diz
rejeição, uso autorizado ou denegação não conta.

### Notas não escrituradas e contingência (v0.54.0)

A consolidação grava `contingencia.parquet`: o item de cada XML do
estabelecimento, de mês com EFD dele, que a EFD dele não tem e que não está
cancelado. Colunas: `cnpj`, `competencia`, `emissao`, `operacao` (do lado do
estabelecimento), `modelo`, `numero_documento`, `serie`, `chave`, `emitente`,
`destinatario`, `numero_item`, `codigo`, `descricao`, `ncm`, `cfop`,
`cst_icms`, `valor`, `valor_icms`, `base_da_multa`, `percentual`, `multa`,
`fundamento`, `arquivo`.

Multa do art. 527 do RICMS/SP, sem SELIC: entrada, 10% do valor; saída, 75%
do ICMS. A base é a do XML; sem ela, o valor por unidade da nota mais próxima
do mesmo estabelecimento, operação e código (fora cancelada e devolução) × a
quantidade (v0.55.3). Colunas a mais: `quantidade`, `origem_da_base` (`xml`,
`nota anterior`, `nota posterior`, `sem referência`), `unitario_de_referencia`,
`chave_de_referencia`, `emissao_de_referencia`; `base_da_multa` é a base usada.
O resumo ganha `contingencia_itens_de_nota_vizinha` e
`contingencia_itens_sem_referencia`; `valor_nao_escriturado_entradas` e
`icms_nao_escriturado_saidas` passam a somar a base usada.

O resumo ganha `nao_escrituradas_entradas`, `nao_escrituradas_saidas`
(documentos), `valor_nao_escriturado_entradas`, `icms_nao_escriturado_saidas`,
`multa_nao_escrituradas_entradas`, `multa_nao_escrituradas_saidas` (texto
decimal) e `contingencia_por_ano` (fatias: ano, documentos, multa). A planilha
é `GET /api/movimentos/{execucao}/planilhas/contingencia`
(`contingencia_nao_escrituradas.xlsx`, aceita `modelos` e `formato`).

## 16. De-para de códigos

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/projetos/{id}/depara` | as propostas da última movimentação concluída e as decisões da empresa. 422 sem movimentação; 410 com o material apagado; 403 fora do escopo |
| `POST` | `/api/projetos/{id}/depara` | `{"decisoes": [{"cnpj", "origem", "destino", "fator", "motivo", "situacao", "confianca", "explicacao"}]}`, até 5.000; quem escreve. `cnpj` vazio vale para a empresa inteira; `situacao` é `aprovado` ou `recusado`; `motivo` um de `gtin`, `sufixo`, `kit`, `descricao`, `cliente`, `analista`. A mesma origem é atualizada, não duplicada. 422 com decisão inválida ou origem repetida no pedido. Grava `parametro_alterado` com `parametro: depara` |

A resposta do GET traz `resumo` (`pares`, `pendentes`, `aprovados`, `recusados`,
`sem_par`, `estabelecimentos`), `pares` (`cnpj`, `origem`, `destino`, `fator`,
`motivos`, `confianca`, `explicacao`, `proposto`, `situacao`, `decidido_por`,
`decidido_em`, `destino_decidido`, `fator_decidido`) e `sem_par` (código com
saída e sem origem que nenhuma proposta resolve, até 5.000).

`quantidade na origem × fator = quantidade no destino`. O razão aplica os pares
aprovados: a Ficha 3 ganha `codigo_original` e o resumo `linhas_com_depara` e
`codigos_trocados_pelo_depara`; os pares que valeram ficam em `depara.parquet`
na pasta da rodada.

## 17. Enquadramentos 2 e 4, art. 271 e X.949 (etapas 4 a 6)

A apuração do suportado grava `icms_proprio` (o ICMS da operação própria da
entrada, o do XML vencendo). O razão confronta as saídas de enquadramento 2 e 4
com o ICMS próprio das entradas mais recentes da ficha e grava
`credito_operacao_propria` (coluna 27) na Ficha 3 e nas fichas; o resumo ganha
`credito_operacao_propria`, `confronto_pela_entrada`, `por_enquadramento[].credito`
e `fora_da_ficha.x949`. A apuração do período soma o crédito em
`credito_operacao_propria` e só conta `confronto_pendente` quando a saída ficou
sem confronto. Apuração e razão de antes da v0.53 continuam lidos: sem as
colunas, o confronto de 2 e 4 fica pendente como antes.
