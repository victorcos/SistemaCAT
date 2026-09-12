# Handoff — Histórico do projeto (Sistema CAT · BMS)

Complemento ao `README.md` do pacote. Cobre a tela nova e as duas alterações que ela trouxe.

Arquivo de referência: `screens/Historico.dc.html`. Rota sugerida: `/trabalhos/:id/historico`.
Como todas as telas deste pacote, é um **protótipo em HTML** — recriar em React + Tailwind com os padrões do codebase. Shell, tokens, combobox, chips, modais e animações são os já descritos no README principal.

## Função
Registro completo do que aconteceu em um projeto: comentários da equipe, importações, etapas concluídas, mudanças de situação e sucessão de responsável — cada evento com autor, papel e horário. A tela também é onde se **altera a situação** do projeto e onde administradores **transferem a titularidade**.

## Acesso
Botão **"Histórico do projeto"** no topo de `Trabalho.dc.html`, à direita do breadcrumb: pill `padding:11px 18px`, radius 11px, fundo `rgba(242,151,29,.12)`, borda `rgba(242,151,29,.34)`, texto `#ffc478` 13px/700, ícone de relógio 15px; hover `background:rgba(242,151,29,.22)` + borda `rgba(242,151,29,.6)` + `translateY(-1px)`.

## Layout
`max-width:1320px`. Breadcrumb "← Voltar ao trabalho", cabeçalho, e abaixo um grid `repeat(auto-fit, minmax(420px, 1fr)); gap:18px; align-items:start` — feed à esquerda, coluna de apoio à direita, colapsando em uma coluna em telas estreitas.

### Cabeçalho
Card de cabeçalho padrão (gradiente + glow + faixa `dcSweep`).
- Eyebrow "HISTÓRICO DO PROJETO", H1 com o nome do projeto (27px/800), razão social 14px/600 `#a9b8d2`, CNPJ monoespaçado + badge de UF.
- **Seletor de situação** à direita (min 250px): rótulo "SITUAÇÃO DO PROJETO" 10px/800 `.13em`; trigger padding `12px 14px`, radius 11px, **fundo/borda/texto na cor do status**, bolinha 8px pulsante (`dcPulse`), caret; hover `filter:brightness(1.12)`. Painel com busca (mesmo componente de combobox do sistema), cada opção com bolinha na sua cor e `✓` na atual.
- **4 cards de fato** (`repeat(auto-fit,minmax(180px,1fr))`): **CRIADO POR** (avatar + nome + data — visível para administradores), **RESPONSÁVEL ATUAL** (avatar + nome + papel), **FRENTE**, **COMPETÊNCIAS** (com "2 de 8 etapas concluídas"). Avatar 26×26 radius 8px, gradiente `oklch` derivado do nome (matizes `[222,262,32,190,300,150]`).

### Situação do projeto
Quatro estados; os três primeiros são os que aparecem no card da listagem.

| Estado | Texto | Fundo | Borda | Nota |
|---|---|---|---|---|
| Em andamento | `#93c5fd` | `rgba(59,130,246,.12)` | `rgba(96,165,250,.34)` | ativo nas listagens |
| Pausado | `#fbbf24` | `rgba(240,180,41,.12)` | `rgba(240,180,41,.34)` | etapas seguem acessíveis, card marcado |
| Cancelado | `#f87171` | `rgba(239,68,68,.12)` | `rgba(239,68,68,.36)` | sai do fluxo, fica só para consulta |
| Concluído | `#6ee7b7` | `rgba(52,211,153,.1)` | `rgba(52,211,153,.32)` | apuração encerrada |

Hint de 12px `#7b8dab` abaixo do seletor explica o efeito do estado escolhido.
Toda troca abre **modal de confirmação com justificativa** (textarea, "entra no histórico"); ao confirmar, gera um evento de situação com `de → para`. Justificativa vazia registra "Situação alterada sem justificativa."

### Feed de atividades e comentários
Card com header, lista rolável (`max-height:620px; overflow-y:auto`) e composer fixo ao pé.
- **Header:** título 18px/800 + contagem ("N registros · mais recente primeiro") e segmented de filtros **Tudo · Comentários · Situação · Arquivos** (`flex-wrap:wrap`, `max-width:100%`; bloco de texto com `min-width:0`).
- **Item:** padding `16px 0`, borda inferior `rgba(255,255,255,.05)`; à esquerda ícone 34×34 radius 10px + linha vertical de 1px `rgba(255,255,255,.07)` formando a timeline.
- **Linha de autoria:** nome 14px/700 · badge de papel (`ADMIN`/`GESTOR`/`OPERAÇÃO`/`AUTOMÁTICO`) 11px/700 em pill neutra · rótulo do tipo 12px `#7b8dab` · horário monoespaçado 11px `#6d7f9d` à direita.
- **Corpo:** 13px/1.6 — comentários em `#dbe5f6`, eventos de sistema em `#9fb3c9`.
- **Delta de situação/sucessão:** duas pills com `→` entre elas; a de destino usa as cores do estado (ou laranja na sucessão).
- **Arquivos:** pills azuis (`rgba(59,130,246,.12)` / borda `rgba(96,165,250,.3)` / `#93c5fd`) com tipo e volume do lote.

**Tipos de evento**

| Tipo | Ícone | Cor do ícone | Rótulo | Origem |
|---|---|---|---|---|
| `criacao` | ★ | neutro | criou o projeto | cadastro do projeto |
| `etapa` | ✓ | verde | concluiu uma etapa | automático (pipeline) |
| `arquivo` | ↥ | azul | importou arquivos | Etapa 1 |
| `comentario` | 💬 | neutro | comentou | usuário |
| `status` | ⇄ | laranja | alterou a situação | seletor de situação |
| `sucessao` | ⇉ | laranja | transferiu o projeto | painel de sucessão |

Ícones são placeholders de texto — **substituir por SVG do icon set** (lucide: `star`, `check`, `upload`, `message-square`, `repeat`, `arrow-right-left`).

- **Composer:** avatar do usuário logado + textarea 2 linhas ("Escreva um comentário para a equipe do projeto…"), hint "Ctrl + Enter envia. Comentários ficam no histórico com seu nome.", botão **Comentar** desabilitado enquanto vazio. O comentário entra no topo do feed com nome, papel e horário do autor.
- Estado vazio por filtro: "Nada por aqui / Troque o filtro para ver outros registros."

### Coluna de apoio
- **Resumo:** contadores de Comentários, Mudanças de situação, Importações e Etapas concluídas (valor 15px/800 na cor do tipo).
- **Sucessão do projeto** (card laranja com barra esquerda 3px `#f2971d`): texto "Somente administradores. O responsável passa a responder pelo projeto; o histórico e o nome de quem criou permanecem."; bloco **RESPONSÁVEL ATUAL** (avatar 30×30 + nome + papel); combobox **"Passar para"** com busca na lista de usuários (`Nome — Papel`); botão **Transferir projeto** desabilitado até haver escolha. Confirmação em modal com justificativa; ao confirmar, o responsável muda, o campo volta ao placeholder e um evento `sucessao` (`de → para`) entra no feed. **O criador nunca muda.**

## Alterações trazidas em outras telas
- **`Trabalho.dc.html`** — botão "Histórico do projeto" no topo e novo fato **CRIADO POR** ("Victor Pedroso · 08/09/2026") na meta do cabeçalho.
- **`Inicio.dc.html`** — os cards agora exibem **Pausado** (âmbar) e **Cancelado** (vermelho) além de Em andamento e Concluído, com a barra de progresso na cor do estado; filtros passaram a ser **Todos · Em andamento · Pausados · Cancelados · Concluídos**; a quarta métrica virou **PAUSADOS / CANCELADOS**. Dois projetos de exemplo foram acrescentados para cobrir os estados.

## Modelo de dados sugerido
```
project: { id, name, company, cnpj, uf, front, periodFrom, periodTo,
           status: 'andamento'|'pausado'|'cancelado'|'concluido',
           createdBy: { id, name, role }, createdAt,
           owner:     { id, name, role } }

event: { id, projectId, kind: 'criacao'|'etapa'|'arquivo'|'comentario'|'status'|'sucessao',
         author: { id, name, role } | 'system',
         createdAt, body,
         from?, to?,            // status e sucessao
         files?: [{ label }] }  // arquivo
```

**API esperada (a confirmar com o backend)**
- `GET /projetos/:id/eventos?kind=` → feed paginado, mais recente primeiro
- `POST /projetos/:id/comentarios` `{ body }`
- `PATCH /projetos/:id/status` `{ status, reason }` → grava o evento `status`
- `PATCH /projetos/:id/responsavel` `{ userId, reason }` → grava o evento `sucessao`
- Eventos `criacao`, `etapa` e `arquivo` são escritos pelo próprio backend/pipeline, não pela UI.

**Autorização**
- Ver histórico e comentar: qualquer usuário com acesso ao projeto.
- Alterar situação: gestor ou administrador.
- Ver "criado por" e transferir o projeto: **administrador**.
- Eventos são **imutáveis** — sem edição nem exclusão; correções entram como novo comentário. O backend deve reforçar todas essas regras.

**A implementar na versão real:** paginação/scroll infinito do feed, atualização ao vivo (websocket ou polling), menção a usuários no comentário, anexos no comentário, e fuso/formatação de data pelo locale (o protótipo usa `DD/MM HH:MM` fixo).
