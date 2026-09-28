# Handoff do front — CRM Fiscal

> Gerado de `frontend/tools/handoff.mjs` em 2026-09-28, sobre a versão **0.106.0**.
> Não editar à mão: rode `npm run handoff` de novo depois de mexer no front.

Tudo aqui sai do código-fonte em `frontend/src`. Se divergir da tela, o
errado é o código — não este documento.

## 1. Rotas (29)

O endereço, a tela que o atende e se exige papel específico.

| Endereço | Tela | Exige papel |
| --- | --- | --- |
| `/login` | Login | — |
| `/trocar-senha` | TrocarSenha | — |
| `/segmentos` | Segmentos | — |
| `/` | Entrada | — |
| `/segmentos/:chave` | ModulosDoSegmento | — |
| `/modulos/:chave` | Inicio | — |
| `/importar` | Importar | — |
| `/projetos/:id` | Projeto | — |
| `/projetos/:id/arquivos` | Lote | — |
| `/projetos/:id/conferencia` | Conferencia | — |
| `/projetos/:id/movimentos` | Movimentos | — |
| `/projetos/:id/suportado` | Suportado | — |
| `/projetos/:id/razao` | Razao | — |
| `/projetos/:id/depara` | DePara | — |
| `/projetos/:id/apuracao` | Apuracao | — |
| `/projetos/:id/arquivo-digital` | ArquivoDigital | — |
| `/projetos/:id/pre-validacao` | PreValidacao | — |
| `/projetos/:id/quebra-de-sped` | QuebraDeSped | — |
| `/projetos/:id/credito-outorgado` | CreditoOutorgado | — |
| `/projetos/:id/frente/:trilha` | Projeto | — |
| `/projetos/:id/apuracao-piscofins` | ApuracaoPisCofins | — |
| `/projetos/:id/razao-contabil` | RazaoContabil | — |
| `/projetos/:id/apuracao-contribuicoes` | Gestao | — |
| `/projetos/:id/exclusoes` | Exclusoes | — |
| `/projetos/:id/quebra-xml` | QuebraXml | — |
| `/projetos/:id/entrega` | Entrega | — |
| `/projetos/:id/historico` | Historico | — |
| `/usuarios` | Usuarios | sim |
| `*` | NaoEncontrada | — |

## 2. Telas (30)

O resumo é o que o próprio arquivo diz de si no comentário do topo.

### Apuracao

`src/pages/Apuracao.tsx` · 628 linhas

Etapa 6 — apurar ressarcimento e complemento. O fechamento por estabelecimento e mês, que é a unidade do arquivo digital.

### ApuracaoPisCofins

`src/pages/ApuracaoPisCofins.tsx` · 429 linhas

Apuração de PIS/COFINS — o par que se confronta. A tela existe para entregar **um par**: a Consulta de Entradas (037), do lado

### ArquivoDigital

`src/pages/ArquivoDigital.tsx` · 719 linhas

Etapa 7 — gerar o arquivo digital. Um arquivo por estabelecimento de SP e por mês. Duas regras mandam na tela:

### Conferencia

`src/pages/Conferencia.tsx` · 433 linhas

Etapa 2 — conferir documentos. Cruza o que a EFD escriturou (C100 e C800) com o XML e o relatório do

### CreditoOutorgado

`src/pages/CreditoOutorgado.tsx` · 862 linhas

Crédito outorgado — quais itens vendidos são produto beneficiado.

### DePara

`src/pages/DePara.tsx` · 393 linhas

De-para de códigos do trabalho. O sistema propõe os pares a partir da movimentação — mesmo GTIN, código de

### Entrega

`src/pages/Entrega.tsx` · 733 linhas

Etapa 8 — relatórios e entrega. Três regras mandam na tela: **o relatório mostra tudo e o dossiê só o que vai

### Exclusoes

`src/pages/Exclusoes.tsx` · 466 linhas

Exclusões da base do PIS/COFINS. Uma tese hoje: as próprias contribuições fora da base. A receita embute PIS e

### Gestao

`src/pages/Gestao.tsx` · 383 linhas

Apuração das contribuições — a Gestão Fiscal no padrão do MA.

### Historico

`src/pages/Historico.tsx` · 817 linhas

Ícone e cor de cada tipo. Tipo novo do servidor cai no padrão em vez de

### Importar

`src/pages/Importar.tsx` · 655 linhas

Cadastrar trabalho — o wizard de quatro passos. O cadastro começa por um arquivo do SPED porque é ele que traz CNPJ, razão

### Inicio.teste

`src/pages/Inicio.teste.tsx` · 141 linhas

"Novo trabalho" numa tela que já é de um tributo. O modal abria com um seletor de **Tributo** listando os cinco — e marcado em

### Inicio

`src/pages/Inicio.tsx` · 663 linhas

Os filtros da listagem. Os quatro status, mais o pré-cadastro, que não é

### Login

`src/pages/Login.tsx` · 101 linhas

_(sem comentário de topo)_

### Lote.teste

`src/pages/Lote.teste.tsx` · 112 linhas

O descarte por empresa, na tela da importação. O sistema não pergunta se pode deixar de fora o arquivo de outra empresa —

### Lote

`src/pages/Lote.tsx` · 547 linhas

Etapa 1 — importar a base de dados de um trabalho que já existe.

### ModulosDoSegmento

`src/pages/ModulosDoSegmento.tsx` · 105 linhas

O segundo nível: dentro de um segmento, qual frente. PIS/COFINS e CBS; ICMS e IBS. A reforma mora ao lado do tributo que sucede

### Movimentos

`src/pages/Movimentos.tsx` · 481 linhas

Etapa 3 — histórico de movimentação. Lê os itens de cada documento da EFD (C170), o analítico (C190/C850), o

### PreValidacao

`src/pages/PreValidacao.tsx` · 622 linhas

Pré-validar os arquivos digitais que o cliente já transmitiu.

### Projeto

`src/pages/Projeto.tsx` · 550 linhas

Para onde cada funcionalidade leva, e com que palavras. A tela não decide o que está disponível — isso vem do domínio, em

### QuebraDeSped

`src/pages/QuebraDeSped.tsx` · 418 linhas

Quebrar os SPED — abrir os arquivos e dizer o que há dentro.

### QuebraXml.teste

`src/pages/QuebraXml.teste.tsx` · 181 linhas

O seletor de colunas da quebra de XML segue o tributo do trabalho.

### QuebraXml

`src/pages/QuebraXml.tsx` · 600 linhas

Quebra de XML — as notas do lote, item a item. A tela entrega **uma planilha sob medida**: são 57 colunas possíveis e quase

### Razao

`src/pages/Razao.tsx` · 932 linhas

Etapa 5 — montar o razão dos itens (Ficha 3). Uma ficha por estabelecimento e mercadoria com ST, pelo custo médio

### RazaoContabil.teste

`src/pages/RazaoContabil.teste.tsx` · 263 linhas

O seletor do razão: o que a marcação tem de aguentar. Existe por uma pergunta feita em 23/09/2026, na revisão da tela: *"filtrar,

### RazaoContabil

`src/pages/RazaoContabil.tsx` · 780 linhas

Razão contábil da ECD — escolher a conta, depois ver os lançamentos.

### Segmentos

`src/pages/Segmentos.tsx` · 142 linhas

O hub: por onde se começa depois de entrar. Um card por segmento tributário que a pessoa enxerga — e, para quem

### Suportado

`src/pages/Suportado.tsx` · 1313 linhas

Etapa 4 — apurar o ICMS suportado. O imposto que entrou com a mercadoria não vem pronto: sai de uma cascata de

### TrocarSenha

`src/pages/TrocarSenha.tsx` · 110 linhas

Troca obrigatória da senha provisória. Aparece no lugar da aplicação, sem menu e sem saída pelos lados: quem entrou

### Usuarios

`src/pages/Usuarios.tsx` · 1153 linhas

O que se diz da pessoa numa linha: uma situação só, na ordem de

## 3. Componentes (31 arquivos)

O que já existe e pode ser reaproveitado. Desenhar um componente que já
está aqui custa o dobro: o trabalho de desenhar e o de reconciliar depois.

### `src/components/ui`

| Componente | Exporta | Propriedades | Para que serve |
| --- | --- | --- | --- |
| `Andamento.tsx` | Andamento | `e` | O andamento de uma execução longa. Só o que toda execução tem — passo, fração, arquivos, documentos, bytes. |
| `Aviso.tsx` | Aviso | `tom = "erro", titulo, children, codigo, acao, aoFechar, className` | Mensagem de erro, aviso ou confirmação. O bloco `<div className="aviso aviso--erro" role="alert">` aparecia 19 vezes |
| `Botao.tsx` | Botao, BotaoLink | `variante, tamanho = "md", carregando, aoCancelar, icone, largo, className, children, disabled, …resto` | O botão do sistema. Substitui `.botao` + `.botao--principal/--secundario/--perigo`, que estavam |
| `BotaoIcone.tsx` | BotaoIcone | `icone, rotulo, tom = "neutro", carregando, className, disabled, …resto` | Botão de 34×34 só com ícone, para ações de linha em tabela. Exige `rotulo` porque um ícone sozinho não tem nome para leitor de tela |
| `Campo.tsx` | Campo | `rotulo` | Rótulo + controle + dica, com os `id` e `aria-describedby` ligados. |
| `Carregando.tsx` | Carregando | `texto = "Carregando…", className` | Estado de carregamento. Existe porque `.carregando` e `.pagina__carregando` |
| `Combobox.tsx` | Combobox | `id, "aria-describedby", valor, opcoes, aoMudar, disabled, placeholderDaBusca = "Buscar…", className` | Seletor com busca, no lugar do `<select>` nativo. A spec da tela de usuários pede que nenhum dropdown seja nativo: o select |
| `Etiqueta.tsx` | Etiqueta, EtiquetaDePapel | `tom = "neutro", pulso, children, className, title` | Pílula de estado. Substitui `.etiqueta--*` (Leiaute), `.pilula--*` |
| `Filtros.tsx` | Toolbar, Busca, Segmentado, Contador, GrupoDeChips, Chip, Pilula | `children` | Busca, segmentado e chips — a barra que aparece sobre toda lista. |
| `ForcaDaSenha.tsx` | ForcaDaSenha | `senha` | Medidor de força e lista de requisitos da senha. A política é a mesma do domínio (`validar_senha`), repetida aqui para dar |
| `LogoBMS.tsx` | LogoBMS | `sobre, className, alt = "BMS Consultoria Tributária"` | O logotipo, escolhendo a tinta pela superfície. Não existe SVG do logotipo no repositório — só PNG em alta (ver |
| `Modal.tsx` | Modal | `aberto, aoFechar, titulo, sub, tamanho = "md", rodape, children` | Diálogo sobre a tela. Usa o <dialog> nativo em vez de uma div com position:fixed — ele já traz de |
| `Pagina.tsx` | Voltar, CabecalhoDePagina, Metricas, Metrica, Secao, Numerao, Barra, Vazio | `para` | "← Trabalhos" no topo de uma tela de detalhe. |
| `Tabela.tsx` | Tabela, Linha, Celula | `colunas, children, className` | Tabela de dados. `<table>` de verdade, e não uma grade de divs: aqui há cabeçalho de coluna, |

### `src/components/shared`

| Componente | Exporta | Propriedades | Para que serve |
| --- | --- | --- | --- |
| `BaixarPlanilha.tsx` | BaixarPlanilha | `aoBaixar, desabilitado, rotulo = "Baixar planilha", destaque, baixando = null, aoCancelar` | O par de botões de download: a planilha e o CSV da mesma lista. |
| `BarraDeFuncionalidades.tsx` | BarraDeFuncionalidades | `etapas, rota` | A barra do trabalho: as funcionalidades, lado a lado. \| Arquivos \| Quebras \| Apuração \| Gestão \| Quebra XML \| |
| `CardDeEscolha.tsx` | CardDeEscolha | `escolha` | O card das telas de entrada — segmentos e módulos. Os dois níveis mostram a mesma coisa com palavras diferentes: uma sigla, um |
| `CardDeFuncionalidade.tsx` | CardDeFuncionalidade | `etapa` | Uma funcionalidade do trabalho, como card. É o card do hub (`CardDeEscolha`) um nível abaixo: lá se escolhe o tributo, |
| `CorrecoesAMao.tsx` | CorrecoesAMao | `projetoId` | Correção à mão do trabalho: a porta da planilha e a lista do que já foi |
| `EditarCadastro.tsx` | EditarCadastro | `projeto, aberto, aoFechar, aoSalvar` | Nome e período do trabalho. Existe porque o período muda de verdade: o trabalho do Amigão nasceu como |
| `ExtrairDoSped.tsx` | ExtrairDoSped | `execucaoId` | Extrair um registro do SPED, consolidado de todos os arquivos. |
| `FrentesDoTrabalho.tsx` | FrentesDoTrabalho | `projetoId, modulo, trilhas` | As frentes de trabalho de um trabalho: a CAT 42, o crédito outorgado, e as |
| `OcorrenciasDoArquivo.tsx` | OcorrenciasDoArquivo | `chave, carregar, cabecalho` | O que a pré-validação achou num arquivo digital. Serve às duas telas que pré-validam — a do arquivo que o sistema gerou e a |
| `PainelDoTrabalho.tsx` | PainelDoTrabalho, FaixaDeLeiautes | `projetoId, etapas, rota, bloqueio` | O painel do trabalho: o que há para ler, e o que dá para fazer. |
| `Rodada.tsx` | quando, duracao, Faixa, Rotulo, Cartao, BarraFina, ListaDoLog | `titulo` | As peças das telas de etapa que rodam no servidor e mostram o resultado em |
| `SegmentosDoUsuario.tsx` | useCatalogoDeSegmentos, PilulasDeSegmento, ChipsDeSegmento | `segmentos, catalogo, papel` | O catálogo inteiro, buscado uma vez por montagem de tela. |
| `TrabalhoParado.tsx` | TrabalhoParado | `status, projetoId` | A faixa que explica por que a etapa não roda. Aparece nas três telas de etapa e no detalhe do trabalho, sempre com a |
| `VendaAConsumidor.tsx` | EscolhaDaVendaAConsumidor | `projeto, usadaNoRazao, bloqueada, aoMudar` | Como o trabalho enquadra a venda a consumidor final. É escolha do trabalho (decisão de 16/09/2026): o manual põe o cupom no |

### `src/layout`

| Componente | Exporta | Propriedades | Para que serve |
| --- | --- | --- | --- |
| `BarraTopo.tsx` | BarraTopo | `usuario, antes, solta` | @param antes o que vai à esquerda do nome. Na porta de entrada é o logotipo, |
| `LeiauteAcesso.tsx` | LeiauteAcesso | `titulo, sub, rodape, children` | A moldura das telas de acesso (login e troca de senha). Metade marinho com o logotipo, metade formulário. Em tela estreita o lado |
| `MenuLateral.tsx` | MenuLateral | `papel` | O menu lateral. Preto, como o resto da moldura — ver docs/IDENTIDADE.md seção 3. Em tela |

## 4. Tokens de design (217)

Em `src/styles/tokens.css`. Toda cor, raio e sombra da tela sai daqui —
nenhum valor literal no componente. Um desenho que precise de uma cor nova
precisa de um token novo, e o token tem de valer nos dois temas.

### marca, valores exatos do logotipo

| Token | Valor | Nota |
| --- | --- | --- |
| `--marca-azul` | `#021D44` | marinho do logotipo |
| `--marca-laranja` | `#FF7F00` | símbolo |
| `--marca-dourado` | `#C19B54` | linha divisória |
| `--marca-branco` | `#FFFFFF` | — |

### azul, escala derivada

| Token | Valor | Nota |
| --- | --- | --- |
| `--azul-900` | `#050F26` | — |
| `--azul-800` | `#021D44` | a cor da marca |
| `--azul-700` | `#0E2A5C` | — |
| `--azul-600` | `#163B7A` | — |
| `--azul-500` | `#22509B` | — |
| `--azul-400` | `#3C6CB8` | — |
| `--azul-300` | `#6D93CE` | — |
| `--azul-200` | `#A8C0E2` | — |
| `--azul-100` | `#D6E2F1` | — |
| `--azul-050` | `#EFF4FA` | — |
| `--laranja-900` | `#6B3200` | — |
| `--laranja-800` | `#8F4200` | 7,13:1 sobre branco |
| `--laranja-700` | `#B35400` | 5,02:1 sobre branco — mínimo p/ texto |
| `--laranja-600` | `#E06B00` | — |
| `--laranja-500` | `#FF7F00` | a cor da marca |
| `--laranja-400` | `#FF9633` | — |
| `--laranja-300` | `#FFAD5C` | — |
| `--laranja-200` | `#FFD1A0` | — |
| `--laranja-100` | `#FFE8D1` | — |
| `--laranja-050` | `#FFF5EB` | — |

### preto, escala neutra

| Token | Valor | Nota |
| --- | --- | --- |
| `--preto-950` | `#09090B` | o fundo da página |
| `--preto-900` | `#101012` | superfície: cartão, painel |
| `--preto-850` | `#17171A` | superfície alternada, linha ímpar |
| `--preto-800` | `#1C1C20` | elevada: o que flutua sobre a superfície |
| `--preto-700` | `#26262B` | borda |
| `--preto-600` | `#33333A` | borda forte |
| `--preto-100` | `#EDEDEF` | texto |
| `--preto-200` | `#A8A8B3` | texto suave |
| `--preto-300` | `#76767F` | texto fraco |

### dourado, escala derivada

| Token | Valor | Nota |
| --- | --- | --- |
| `--dourado-800` | `#6B5222` | — |
| `--dourado-700` | `#8A6B2E` | 4,97:1 sobre branco |
| `--dourado-600` | `#A6813C` | — |
| `--dourado-500` | `#C19B54` | a cor da marca |
| `--dourado-400` | `#D3B37C` | — |
| `--dourado-300` | `#E3CCA6` | — |
| `--dourado-200` | `#EFE2CB` | — |
| `--dourado-100` | `#F7F0E4` | — |

### neutros

| Token | Valor | Nota |
| --- | --- | --- |
| `--cinza-900` | `#16181D` | — |
| `--cinza-800` | `#24272E` | — |
| `--cinza-700` | `#3A3E48` | — |
| `--cinza-600` | `#545963` | — |
| `--cinza-500` | `#767C88` | — |
| `--cinza-400` | `#9BA1AC` | — |
| `--cinza-300` | `#C3C8D0` | — |
| `--cinza-200` | `#DFE2E7` | — |
| `--cinza-100` | `#EFF1F4` | — |
| `--cinza-050` | `#F7F8FA` | — |
| `--sucesso` | `#1B7A4B` | — |
| `--sucesso-fundo` | `#E6F4EC` | — |
| `--atencao` | `#A15C00` | âmbar, deliberadamente fora do laranja da marca |
| `--atencao-fundo` | `#FFF4E0` | — |
| `--erro` | `#B3261E` | — |
| `--erro-fundo` | `#FCEBEA` | — |
| `--info` | `#163B7A` | — |
| `--info-fundo` | `#E8EFF9` | — |
| `--fiscal-ressarcimento` | `#1B7A4B` | crédito a favor do contribuinte |
| `--fiscal-complemento` | `#B3261E` | valor devido |
| `--fiscal-verificar` | `#A15C00` | anomalia, exige julgamento |
| `--fiscal-sem-valor` | `var(--cinza-500)` | — |
| `--fiscal-estoque` | `var(--azul-600)` | — |
| `--etiqueta-neutra-texto` | `var(--cinza-700)` | — |
| `--etiqueta-neutra-fundo` | `var(--cinza-200)` | — |
| `--etiqueta-destaque-texto` | `var(--dourado-800)` | — |
| `--etiqueta-destaque-fundo` | `var(--dourado-200)` | — |
| `--fundo` | `var(--cinza-050)` | — |
| `--superficie` | `var(--marca-branco)` | — |
| `--superficie-alt` | `var(--cinza-100)` | — |
| `--superficie-elevada` | `var(--marca-branco)` | — |
| `--texto` | `var(--cinza-900)` | — |
| `--texto-suave` | `var(--cinza-600)` | — |
| `--texto-fraco` | `var(--cinza-500)` | — |
| `--texto-invertido` | `var(--marca-branco)` | — |
| `--borda` | `var(--cinza-200)` | — |
| `--borda-forte` | `var(--cinza-300)` | — |
| `--borda-foco` | `var(--azul-500)` | — |
| `--moldura-fundo` | `#0C0C0E` | — |
| `--moldura-texto` | `var(--preto-100)` | — |
| `--moldura-texto-suave` | `var(--preto-300)` | — |
| `--moldura-ativo` | `var(--marca-laranja)` | — |
| `--moldura-borda` | `var(--preto-700)` | — |
| `--acao-fundo` | `var(--marca-laranja)` | — |
| `--acao-texto` | `var(--preto-950)` | — |
| `--acao-hover` | `var(--laranja-600)` | — |
| `--acao-ativo` | `var(--laranja-700)` | — |
| `--acao-inativo-fundo` | `var(--cinza-300)` | — |
| `--acao-inativo-texto` | `var(--cinza-600)` | — |

### ação secundária

| Token | Valor | Nota |
| --- | --- | --- |
| `--acao2-fundo` | `transparent` | — |
| `--acao2-texto` | `var(--azul-700)` | — |
| `--acao2-borda` | `var(--cinza-300)` | — |
| `--acao2-hover` | `var(--azul-050)` | — |
| `--link` | `var(--azul-600)` | — |
| `--link-hover` | `var(--azul-700)` | — |

### tabela, o componente mais usado do sistema

| Token | Valor | Nota |
| --- | --- | --- |
| `--tabela-cabecalho-fundo` | `var(--marca-azul)` | — |
| `--tabela-cabecalho-texto` | `var(--marca-branco)` | — |
| `--tabela-linha` | `var(--marca-branco)` | — |
| `--tabela-linha-alt` | `var(--cinza-050)` | — |
| `--tabela-linha-hover` | `var(--azul-050)` | — |
| `--tabela-linha-marcada` | `var(--laranja-050)` | — |
| `--tabela-borda` | `var(--cinza-200)` | — |
| `--tabela-numero` | `var(--cinza-900)` | — |
| `--destaque` | `var(--marca-dourado)` | divisória, faixa de seção |
| `--superficie-vidro` | `rgb(2 29 68 / 3%)` | — |
| `--borda-sutil` | `rgb(2 29 68 / 8%)` | — |

### brilho do CTA laranja, do redesenho da tela de usuários

| Token | Valor | Nota |
| --- | --- | --- |
| `--brilho-acao` | `0 12px 28px rgb(255 127 0 / 30%)` | — |
| `--sombra` | `0 1px 2px rgb(2 29 68 / 8%), 0 2px 8px rgb(2 29 68 / 6%)` | — |
| `--sombra-elevada` | `0 4px 12px rgb(2 29 68 / 12%), 0 12px 32px rgb(2 29 68 / 10%)` | — |
| `--raio` | `6px` | — |
| `--raio-g` | `10px` | — |
| `--raio-cartao` | `18px` | cartão grande do redesenho; o 6px é de botão |
| `--fonte` | `"Inter Variable", "Inter", "Segoe UI", system-ui, -apple-system, sans-serif` | — |
| `--fonte-num` | `"IBM Plex Mono", "Consolas", ui-monospace, monospace` | — |
| `--fundo` | `var(--preto-950)` | — |
| `--superficie` | `var(--preto-900)` | — |
| `--superficie-alt` | `var(--preto-850)` | — |
| `--superficie-elevada` | `var(--preto-800)` | — |
| `--texto` | `var(--preto-100)` | — |
| `--texto-suave` | `var(--preto-200)` | — |
| `--texto-fraco` | `var(--preto-300)` | — |
| `--texto-invertido` | `var(--preto-950)` | — |
| `--borda` | `var(--preto-700)` | — |
| `--borda-forte` | `var(--preto-600)` | — |
| `--borda-foco` | `var(--laranja-400)` | — |
| `--moldura-fundo` | `#0C0C0E` | — |
| `--moldura-texto` | `var(--preto-100)` | — |
| `--moldura-texto-suave` | `var(--preto-300)` | — |
| `--moldura-borda` | `var(--preto-700)` | — |
| `--acao-hover` | `var(--laranja-400)` | — |
| `--acao-ativo` | `var(--laranja-300)` | — |
| `--acao-inativo-fundo` | `var(--preto-700)` | — |
| `--acao-inativo-texto` | `var(--preto-300)` | — |
| `--acao2-texto` | `var(--preto-200)` | — |
| `--acao2-borda` | `var(--preto-600)` | — |
| `--acao2-hover` | `var(--preto-800)` | — |
| `--link` | `var(--laranja-400)` | — |
| `--link-hover` | `var(--laranja-300)` | — |
| `--tabela-cabecalho-fundo` | `var(--preto-800)` | — |
| `--tabela-linha` | `var(--preto-900)` | — |
| `--tabela-linha-alt` | `var(--preto-850)` | — |
| `--tabela-linha-hover` | `var(--preto-800)` | — |
| `--tabela-linha-marcada` | `#3A2410` | — |
| `--tabela-borda` | `var(--preto-700)` | — |
| `--tabela-numero` | `var(--preto-100)` | — |
| `--sucesso` | `#4ECB8B` | — |
| `--sucesso-fundo` | `#0C2E1F` | — |
| `--atencao` | `#E0A44A` | — |
| `--atencao-fundo` | `#33240C` | — |
| `--erro` | `#F58179` | — |
| `--erro-fundo` | `#3A1512` | — |
| `--info` | `#7FA9E8` | — |
| `--info-fundo` | `#16181D` | — |
| `--fiscal-ressarcimento` | `#4ECB8B` | — |
| `--fiscal-complemento` | `#F58179` | — |
| `--fiscal-verificar` | `#E0A44A` | — |
| `--fiscal-sem-valor` | `var(--preto-300)` | — |
| `--fiscal-estoque` | `#7FA9E8` | — |
| `--etiqueta-neutra-texto` | `var(--preto-200)` | — |
| `--etiqueta-neutra-fundo` | `var(--preto-700)` | — |
| `--etiqueta-destaque-texto` | `var(--dourado-400)` | — |
| `--etiqueta-destaque-fundo` | `#2A2213` | — |
| `--sombra` | `0 1px 2px rgb(0 0 0 / 40%), 0 2px 8px rgb(0 0 0 / 30%)` | — |
| `--sombra-elevada` | `0 4px 12px rgb(0 0 0 / 50%), 0 12px 32px rgb(0 0 0 / 40%)` | — |
| `--superficie-vidro` | `rgb(255 255 255 / 4%)` | — |
| `--borda-sutil` | `rgb(255 255 255 / 8%)` | — |
| `--brilho-acao` | `0 12px 28px rgb(255 127 0 / 30%)` | — |

### escolha explícita do usuário vence o sistema, nos dois sentidos

| Token | Valor | Nota |
| --- | --- | --- |
| `--fundo` | `var(--preto-950)` | — |
| `--superficie` | `var(--preto-900)` | — |
| `--superficie-alt` | `var(--preto-850)` | — |
| `--superficie-elevada` | `var(--preto-800)` | — |
| `--texto` | `var(--preto-100)` | — |
| `--texto-suave` | `var(--preto-200)` | — |
| `--texto-fraco` | `var(--preto-300)` | — |
| `--texto-invertido` | `var(--preto-950)` | — |
| `--borda` | `var(--preto-700)` | — |
| `--borda-forte` | `var(--preto-600)` | — |
| `--borda-foco` | `var(--laranja-400)` | — |
| `--moldura-fundo` | `#0C0C0E` | — |
| `--moldura-texto` | `var(--preto-100)` | — |
| `--moldura-texto-suave` | `var(--preto-300)` | — |
| `--moldura-borda` | `var(--preto-700)` | — |
| `--acao-hover` | `var(--laranja-400)` | — |
| `--acao-ativo` | `var(--laranja-300)` | — |
| `--acao-inativo-fundo` | `var(--preto-700)` | — |
| `--acao-inativo-texto` | `var(--preto-300)` | — |
| `--acao2-texto` | `var(--preto-200)` | — |
| `--acao2-borda` | `var(--preto-600)` | — |
| `--acao2-hover` | `var(--preto-800)` | — |
| `--link` | `var(--laranja-400)` | — |
| `--link-hover` | `var(--laranja-300)` | — |
| `--tabela-cabecalho-fundo` | `var(--preto-800)` | — |
| `--tabela-linha` | `var(--preto-900)` | — |
| `--tabela-linha-alt` | `var(--preto-850)` | — |
| `--tabela-linha-hover` | `var(--preto-800)` | — |
| `--tabela-linha-marcada` | `#3A2410` | — |
| `--tabela-borda` | `var(--preto-700)` | — |
| `--tabela-numero` | `var(--preto-100)` | — |
| `--sucesso` | `#4ECB8B` | — |
| `--atencao` | `#E0A44A` | — |
| `--erro` | `#F58179` | — |
| `--info` | `#7FA9E8` | — |
| `--fiscal-ressarcimento` | `#4ECB8B` | — |
| `--fiscal-complemento` | `#F58179` | — |
| `--fiscal-verificar` | `#E0A44A` | — |
| `--fiscal-sem-valor` | `var(--preto-300)` | — |
| `--fiscal-estoque` | `#7FA9E8` | — |
| `--etiqueta-neutra-texto` | `var(--preto-200)` | — |
| `--etiqueta-neutra-fundo` | `var(--preto-700)` | — |
| `--etiqueta-destaque-texto` | `var(--dourado-400)` | — |
| `--etiqueta-destaque-fundo` | `#2A2213` | — |
| `--sombra` | `0 1px 2px rgb(0 0 0 / 40%), 0 2px 8px rgb(0 0 0 / 30%)` | — |
| `--sombra-elevada` | `0 4px 12px rgb(0 0 0 / 50%), 0 12px 32px rgb(0 0 0 / 40%)` | — |
| `--superficie-vidro` | `rgb(255 255 255 / 4%)` | — |
| `--borda-sutil` | `rgb(255 255 255 / 8%)` | — |
| `--brilho-acao` | `0 12px 28px rgb(255 127 0 / 30%)` | — |

## 5. O que a tela pede ao servidor (106 chamadas)

Agrupado pelo serviço que faz a chamada. Os parâmetros da URL aparecem como
`:id`, qualquer que seja o nome no código.

### `apuracao`

| Método | Rota |
| --- | --- |
| GET | `/api/apuracao/:id` |
| POST | `/api/apuracao/:id/cancelar` |
| GET | `/api/apuracao/:id/competencias` |
| GET | `/api/apuracao/:id/planilhas/:id` |
| POST | `/api/projetos/:id/apuracao` |

### `apuracaoPisCofins`

| Método | Rota |
| --- | --- |
| GET | `/api/apuracao-piscofins/:id` |
| POST | `/api/apuracao-piscofins/:id/cancelar` |
| GET | `/api/apuracao-piscofins/:id/contas` |
| GET | `/api/apuracao-piscofins/:id/estabelecimentos` |
| GET | `/api/apuracao-piscofins/:id/lancamentos` |
| GET | `/api/apuracao-piscofins/:id/planilhas/:id` |
| POST | `/api/projetos/:id/apuracao-piscofins` |

### `arquivoDigital`

| Método | Rota |
| --- | --- |
| GET | `/api/:id/:id/ocorrencias` |
| GET | `/api/arquivo-digital/:id` |
| GET | `/api/arquivo-digital/:id/arquivos` |
| POST | `/api/arquivo-digital/:id/cancelar` |
| GET | `/api/arquivo-digital/:id/planilhas/:id` |
| POST | `/api/projetos/:id/arquivo-digital` |

### `auth`

| Método | Rota |
| --- | --- |
| GET | `/api/auth/eu` |
| POST | `/api/auth/token` |

### `conferencia`

| Método | Rota |
| --- | --- |
| GET | `/api/conferencias/:id` |
| GET | `/api/conferencias/:id/planilhas/:id` |
| POST | `/api/projetos/:id/conferencias` |

### `correcoes`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/correcoes` |
| GET | `/api/projetos/:id/correcoes:id` |
| DELETE | `/api/projetos/:id/correcoes/:id` |
| POST | `/api/razao/:id/correcoes/planilha` |

### `creditoOutorgado`

| Método | Rota |
| --- | --- |
| GET | `/api/credito-outorgado/:id` |
| POST | `/api/credito-outorgado/:id/cancelar` |
| GET | `/api/credito-outorgado/:id/itens:id` |
| GET | `/api/credito-outorgado/:id/planilhas/:id` |
| GET | `/api/credito-outorgado/:id/produtos:id` |
| POST | `/api/projetos/:id/credito-outorgado` |
| PUT | `/api/projetos/:id/credito-outorgado/filtro` |

### `depara`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/depara` |

### `entrega`

| Método | Rota |
| --- | --- |
| GET | `/api/entrega/:id` |
| POST | `/api/entrega/:id/aprovar` |
| POST | `/api/entrega/:id/cancelar` |
| GET | `/api/entrega/:id/estabelecimentos` |
| GET | `/api/entrega/:id/planilhas/pacote` |
| GET | `/api/entrega/:id/planilhas/relatorio` |
| POST | `/api/projetos/:id/entrega` |

### `exclusoes`

| Método | Rota |
| --- | --- |
| GET | `/api/exclusoes/:id` |
| POST | `/api/exclusoes/:id/cancelar` |
| GET | `/api/exclusoes/:id/planilhas/exclusoes:id` |
| POST | `/api/projetos/:id/exclusoes` |

### `gestao`

| Método | Rota |
| --- | --- |
| GET | `/api/apuracao-contribuicoes/:id` |
| POST | `/api/apuracao-contribuicoes/:id/cancelar` |
| GET | `/api/apuracao-contribuicoes/:id/planilhas/quadros:id` |
| POST | `/api/projetos/:id/apuracao-contribuicoes` |

### `historico`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/historico/comentarios` |
| GET | `/api/projetos/:id/historico${q ` |
| PATCH | `/api/projetos/:id/responsavel` |
| PATCH | `/api/projetos/:id/status` |
| GET | `/api/projetos/:id/sucessores` |
| GET | `/api/status-de-projeto` |

### `importacao`

| Método | Rota |
| --- | --- |
| POST | `/api/empresas` |
| POST | `/api/projetos` |
| DELETE | `/api/projetos/:id` |
| PATCH | `/api/projetos/:id/cadastro` |
| GET | `/api/projetos/:id/exclusao` |
| PUT | `/api/projetos/:id/venda-a-consumidor` |
| GET | `/api/venda-a-consumidor` |

### `lote`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/lotes` |
| DELETE | `/api/projetos/:id/lotes/:id` |
| POST | `/api/projetos/:id/lotes/inspecionar` |

### `movimentos`

| Método | Rota |
| --- | --- |
| GET | `/api/movimentos/:id` |
| GET | `/api/movimentos/:id/planilhas/:id` |
| POST | `/api/projetos/:id/movimentos` |

### `preValidacao`

| Método | Rota |
| --- | --- |
| GET | `/api/pre-validacao/:id` |
| GET | `/api/pre-validacao/:id/arquivos` |
| POST | `/api/pre-validacao/:id/cancelar` |
| GET | `/api/pre-validacao/:id/planilhas/:id` |
| POST | `/api/projetos/:id/pre-validacao` |

### `quebraDeSped`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/quebra-de-sped` |
| GET | `/api/quebra-de-sped/:id` |
| GET | `/api/quebra-de-sped/:id/alvos` |
| POST | `/api/quebra-de-sped/:id/cancelar` |
| GET | `/api/quebra-de-sped/:id/extracao` |
| GET | `/api/quebra-de-sped/:id/planilhas/:id` |

### `quebraXml`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/quebra-xml` |
| GET | `/api/quebra-xml/:id` |
| POST | `/api/quebra-xml/:id/cancelar` |
| GET | `/api/quebra-xml/:id/planilhas/itens:id` |
| GET | `/api/quebra-xml/campos` |

### `razao`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/razao` |
| GET | `/api/razao/:id` |
| POST | `/api/razao/:id/cancelar` |
| GET | `/api/razao/:id/ficha` |
| GET | `/api/razao/:id/fichas` |
| GET | `/api/razao/:id/planilhas/:id` |

### `segmentos`

| Método | Rota |
| --- | --- |
| GET | `/api/segmentos` |
| GET | `/api/segmentos/resumo` |
| GET | `/api/segmentos/todos` |
| PUT | `/api/usuarios/:id/segmentos` |

### `suportado`

| Método | Rota |
| --- | --- |
| POST | `/api/projetos/:id/suportado` |
| GET | `/api/suportado/:id` |
| POST | `/api/suportado/:id/cancelar` |
| GET | `/api/suportado/:id/linhas` |
| GET | `/api/suportado/:id/planilhas/suportado:id` |

### `usuarios`

| Método | Rota |
| --- | --- |
| POST | `/api/usuarios` |
| PATCH | `/api/usuarios/:id/:id` |
| POST | `/api/usuarios/:id/desbloquear` |
| PUT | `/api/usuarios/:id/empresas` |
| POST | `/api/usuarios/:id/senha` |
| POST | `/api/usuarios/eu/senha` |

## 6. Papéis e menu

### Listas de papel usadas pela tela

| Lista | Papéis |
| --- | --- |
| `ORDEM_PAPEIS` | gestor, analista, revisor, leitura, dev, |
| `ADMINISTRA_USUARIOS` | dev, gestor |
| `IGNORA_ESCOPO_DE_EMPRESA` | dev, gestor |
| `ENXERGA_TODOS_OS_SEGMENTOS` | dev, gestor |
| `PODE_EXCLUIR_TRABALHO` | dev, gestor |
| `PODE_APROVAR_ENTREGA` | revisor, gestor |
| `PODE_ESCREVER` | dev, gestor, analista, revisor |

### Menu lateral

| Rótulo | Rota |
| --- | --- |
| Segmentos | `ROTAS.segmentos` |
| Cadastro | `ROTAS.importar` |
| Usuários | `ROTAS.usuarios` |

## 7. Buracos de navegação

A pergunta que um handoff tem de responder: **partindo da tela inicial, dá
para chegar lá?** Registrar a rota não cria caminho nenhum — em 22/09/2026
três telas ficaram prontas, testadas e inalcançáveis por causa disso.

#### Rotas declaradas em `routes.ts` e não registradas no roteador

_Nenhuma._

#### Telas em `pages/` sem rota

- `Inicio.teste`
- `Lote.teste`
- `QuebraXml.teste`
- `RazaoContabil.teste`

#### Rotas que nenhum link aponta

Alcançáveis só digitando o endereço. Nem toda é defeito — algumas são
destino de redirecionamento do servidor —, mas cada uma merece uma resposta.

_Nenhuma._

