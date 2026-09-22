# Handoff — CRM Fiscal · BMS Consultoria Tributária

Reconstrução visual do sistema interno de apuração das obrigações da CAT. Sete telas em alta fidelidade, mesma paleta e logo da versão legada, layout reorganizado.

## Sobre os arquivos de design

Os `.dc.html` em `screens/` são **referências de design em HTML** — protótipos de aparência e comportamento, **não código de produção**. Recrie-os no ambiente do codebase de destino com os padrões já estabelecidos lá. Preferência do cliente: **React + Tailwind CSS + componentes estilo Aceternity UI** (brilhos e gradientes sutis, animações de entrada).

Os protótipos usam estilos inline por restrição da ferramenta; na implementação traduza para utilitários Tailwind / tokens do design system.

**Fidelidade: alta.** Cores, tipografia, espaçamentos, estados e microinterações estão definidos.

`screens/support.js` é runtime da ferramenta de prototipagem — necessário só para abrir os HTML localmente, **não** faz parte da entrega.

## Telas

| Arquivo | Tela | Rota sugerida |
|---|---|---|
| `Login.dc.html` | Entrar / primeiro acesso | `/login` |
| `Inicio.dc.html` | Trabalhos (lista de projetos) | `/` |
| `Cadastro.dc.html` | Cadastrar trabalho (wizard 4 passos) | `/cadastro` |
| `Trabalho.dc.html` | Detalhe do trabalho + etapas | `/trabalhos/:id` |
| `Etapa Importar.dc.html` | Etapa 1 — Importar base de dados | `/trabalhos/:id/importar` |
| `Etapa Conferir.dc.html` | Etapa 2 — Conferir documentos | `/trabalhos/:id/conferir` |
| `Etapa Extrair.dc.html` | Etapa 3 — Extrair movimentos | `/trabalhos/:id/extrair` |
| `Historico.dc.html` | Histórico do projeto (feed, situação, sucessão) | `/trabalhos/:id/historico` |
| `Usuarios.dc.html` | Administração de usuários | `/usuarios` |

O histórico tem documento próprio: **`README-Historico.md`** (inclui as alterações que ele trouxe em Trabalhos e no detalhe do trabalho).

### Fluxo
Login → Trabalhos → (card) Detalhe do trabalho → etapa clicada, ou → Histórico do projeto. "Cadastrar trabalho" abre o wizard de Cadastro, que termina em "Ver o trabalho". Usuários é acessível pela sidebar (somente gestores).

---

## Sistema visual

### Shell (todas as telas internas)
`display:flex`, `min-height:100vh`.

**Sidebar** — largura fixa `244px` (`flex:0 0 244px`), `position:sticky; top:0; height:100vh`, padding `22px 16px`, `gap:28px`, borda direita `1px solid rgba(255,255,255,.07)`, fundo `linear-gradient(180deg, rgba(12,19,36,.9), rgba(8,13,25,.9))`.
- Logo: `assets/bms-logo.png`, largura 172px (**substituir pelo SVG oficial do repositório** — o PNG foi extraído de captura de tela).
- Rótulo "NAVEGAÇÃO": 10px/700, `letter-spacing:.16em`, `#5f7191`, padding `0 10px 8px`.
- Item inativo: 14px/600 `#9fb0cd`, padding `10px 12px`, radius 10px, bolinha 6px `#3c4a66`; hover `background:rgba(255,255,255,.05)` + `color:#e8edf7`.
- Item ativo: fundo `linear-gradient(90deg, rgba(242,151,29,.16), rgba(242,151,29,.02))`, borda `1px solid rgba(242,151,29,.28)`, barra esquerda 2px `#f2971d`, bolinha `#f2971d` com `box-shadow:0 0 10px #f2971d`, texto branco 700.
- Rodapé: card `rgba(255,255,255,.02)` / borda `rgba(255,255,255,.06)` — "CRM Fiscal" + "sessão não comercial".

**Topbar** — `position:sticky; top:0; z-index:20`, padding `16px 28px`, fundo `rgba(8,13,25,.72)` + `backdrop-filter:blur(10px)`, borda inferior `rgba(255,255,255,.07)`. Avatar 30×30 radius 9px `linear-gradient(140deg,#1e3a8a,#0f1e3f)`, nome 14px/700, badge de papel (DEV/GESTOR) 10px/800 `letter-spacing:.1em`, botão **Sair** ghost com hover vermelho (`rgba(239,68,68,.14)` / borda `rgba(239,68,68,.4)` / texto `#fecaca`).

**Fundo da página** — `radial-gradient(900px 500px at 18% -10%, rgba(242,151,29,.10), transparent 60%), radial-gradient(900px 600px at 90% 0%, rgba(37,99,235,.14), transparent 65%), #070c18`.

**Main** — padding `24-28px`, `max-width` 1240–1400px, `gap:20px` em coluna.

### Card de cabeçalho de página (padrão repetido)
`border-radius:18px`, borda `rgba(255,255,255,.08)`, fundo `linear-gradient(120deg, rgba(18,27,48,.9), rgba(10,16,31,.9))`, padding `24px 26px`, `overflow:hidden`.
- Glow: `radial-gradient(420px 160px at 8% 0%, rgba(242,151,29,.16), transparent 70%)`, `pointer-events:none`.
- **Linha de brilho superior (Aceternity):** faixa de 1px; filho de 40% com `linear-gradient(90deg,transparent,#f2971d,transparent)` animado por `dcSweep` 5.5s linear infinite.
- Eyebrow 11px/700 `.18em` `#f2971d` · H1 30px/800 `-.02em` · descrição 14px/1.55 `#8798b6` `max-width:560-720px` `text-wrap:pretty`.
- CTA laranja à direita.

### Faixa de métricas
`grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap:12px`. Card: padding `14px 16px`, radius 12px; rótulo 11px/700 `.12em`; número 24px/800. Variantes de cor: neutro (`rgba(255,255,255,.03)` / `#7486a5`), azul (`rgba(59,130,246,.07)` / `#93c5fd`), verde (`rgba(52,211,153,.06)` / `#6ee7b7`), âmbar (`rgba(240,180,41,.06)` / `#fbbf24`).

### Toolbar de busca e filtros
- **Busca:** `min 220px / max 360-380px`; input padding `11px 14px 11px 32px`, radius 10px, fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.1)`, 13px; foco → borda `rgba(242,151,29,.55)` + fundo `rgba(242,151,29,.06)`; lupa absoluta à esquerda.
- **Segmented de filtros:** container padding 4px, radius 11px, fundo `rgba(255,255,255,.03)`, borda `rgba(255,255,255,.08)`; opção ativa fundo `rgba(242,151,29,.16)` texto `#ffbb5c`, inativa transparente `#8798b6`; 12px/700, padding `8px 14px`, radius 8px.
- **Contador** à direita, 12px/600 `#7486a5`.

### Combobox com busca (substitui TODOS os `<select>`)
Regra do projeto: **nenhum dropdown nativo em nenhuma tela.**
- **Trigger:** botão full-width, padding `11px 13px`, radius 10px, fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.11)` (aberto `rgba(242,151,29,.55)`, desabilitado `rgba(255,255,255,.06)`), 13px/600; caret `▾`/`▴` 11px `#7f91af`.
- **Painel:** `absolute; top:calc(100% + 6px); z-index:90`, radius 12px, borda `rgba(255,255,255,.12)`, fundo `#101a30`, sombra `0 22px 48px rgba(0,0,0,.55)`, animação `dcFade .14s`.
  - Campo de busca (padding wrapper 9px, borda inferior `rgba(255,255,255,.07)`; input 12px, radius 8px) — **foco automático ao abrir**.
  - Lista `max-height:200-220px; overflow-y:auto; padding:6px`; item padding `9px 10px`, radius 8px, 13px/600, hover `rgba(255,255,255,.06)`; selecionado fundo `rgba(242,151,29,.14)` texto `#ffc478` com `✓`.
  - Vazio: "Nenhum resultado" 12px `#6d7f9d`.
- **Comportamento:** filtro substring case-insensitive; fecha ao selecionar e em clique fora (listener `mousedown` em capture que compara o atributo `data-picker`); query limpa ao abrir/fechar; um combobox aberto por vez.
- **A implementar na versão real:** navegação por teclado (↑/↓/Enter/Esc/Home/End), `role="combobox"/"listbox"/"option"`, `aria-expanded`, `aria-activedescendant`, flip para cima sem espaço abaixo.

### Chips de filtro (checkbox custom)
Pill padding `10px 16px`, radius 999px; caixa 16×16 radius 5px — desmarcada borda `rgba(255,255,255,.25)` fundo transparente, marcada fundo `#f2971d` com `✓` em `#121a2c`. Pill marcada: fundo `rgba(242,151,29,.14)`, borda `rgba(242,151,29,.45)`, texto `#ffc478`.

### Botões
- **Primário:** `linear-gradient(135deg,#f9a72b,#e8801a)`, texto `#121a2c` 14px/800, padding `13px 22px`, radius 11-12px, sombra `0 12px 28px rgba(242,151,29,.3)`; hover `translateY(-1/-2px)` + sombra `0 16px 34px rgba(242,151,29,.42)`.
- **Ghost:** fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.12)`, texto `#dbe5f6` 13px/700; hover laranja ou vermelho conforme a ação.
- **Desabilitado:** fundo `rgba(30,58,138,.42)`, texto `#7f93bb`, `cursor:not-allowed`, sem sombra.
- **Icon button:** 34×34 (30×30 em listas densas), radius 9px, SVG 16px `stroke:currentColor; stroke-width:1.8`.
- **Destrutivo:** fundo `rgba(239,68,68,.16)`, borda `rgba(239,68,68,.5)`, texto `#fecaca`.

### Modais
Overlay `fixed; inset:0`, fundo `rgba(4,8,16,.66-.7)` + `backdrop-filter:blur(6px)`; formulários alinhados ao topo (`padding:48px 20px; overflow-y:auto`), confirmações centralizadas.
Card radius 18-20px, borda `rgba(255,255,255,.1)`, fundo `linear-gradient(150deg, rgba(19,28,50,.98), rgba(10,16,31,.98))`, sombra `0 30-40px 70-90px rgba(0,0,0,.6)`, animação `dcFade .18-.22s`. **Sem `overflow:hidden`** quando contém combobox.
Header padding `22px 26px` + borda inferior; corpo `grid-template-columns: repeat(auto-fit, minmax(230px,1fr)); gap:18px`; footer com mensagem à esquerda (padrão `#6d7f9d`, erro `#fca5a5`) e ações à direita.
z-index: criação 60 · edição 65 · confirmação 70.

### Faixa de aviso / nota (usada nas etapas)
Padding `13-14px 15-18px`, radius 11-12px, borda esquerda 3px colorida, corpo 13px/1.6. Variantes: sucesso (`#34d399` / `rgba(6,38,32,.42)` / `#c8e6d9`), alerta (`#f2971d` / `rgba(46,31,10,.42)` / `#e9cfa6`), neutra (`#94a3b8` / `rgba(30,41,59,.42)` / `#b8c6da`), erro (`#ef4444` / `rgba(127,29,29,.34)` / `#fecaca`).

---

## Detalhe por tela

### 1. Login (`Login.dc.html`)
Split 50/50 em `grid-template-columns: 1fr 1fr`.
- **Painel esquerdo:** fundo `linear-gradient(160deg,#0b1c3a,#081527)`; halo laranja de 520px animado por `dcDrift` 16s; grade de 56px em `rgba(255,255,255,.035)` com máscara radial; logo centralizada (max 420px), régua de 64×2px com gradiente laranja, tagline 17px `#8ba6d6`. Borda direita `1px solid rgba(242,151,29,.28)`.
- **Painel direito:** form `max-width:412px`. H1 34px/800 · subtítulo 14px `#8798b6`. Campos padding `13px 15px`, radius 11px; foco borda `#f2971d` + `box-shadow:0 0 0 3px rgba(242,151,29,.16)`.
- **Senha:** botão olho 34×34 absoluto à direita (`right:7px`), alterna `type` e ícone (olho / olho cortado).
- **CTA Entrar:** desabilitado (azul apagado) até usuário e senha preenchidos; habilitado ganha gradiente laranja + faixa `dcSweep` de 35% no topo; estado carregando mostra spinner `dcSpin` e rótulo "Verificando…".
- **Erro:** faixa vermelha com ícone, título "Usuário ou senha inválidos." e `Código para suporte: <hex12>` em monoespaçada; o card inteiro faz `dcShake .34s`; a senha é limpa. O código é gerado por tentativa e serve para o suporte cruzar com o log — **gerar no backend**.
- **Primeiro acesso:** avisado por faixa âmbar; campos Nova senha / Confirmar; medidor de força de 4 barras (Muito fraca `#f87171` → Forte `#34d399`); lista de 4 requisitos com check verde (10+ caracteres, maiúsculas e minúsculas, número, símbolo); salvar exige score ≥ 3 e confirmação igual.
- **Sucesso:** ícone check verde + "Redirecionando para o CRM Fiscal…".
- Rodapé: "Esqueceu a senha ou o acesso está bloqueado? Procure um gestor da equipe. Por segurança, a redefinição não é automática." + assinatura.
- **Remover na implementação:** a linha DEMO (Sucesso / Erro / Primeiro acesso) existe só para navegar os estados no protótipo.

### 2. Trabalhos (`Inicio.dc.html`)
Cabeçalho + métricas (TRABALHOS / EM ANDAMENTO / CONCLUÍDOS / ETAPAS PENDENTES) + toolbar (busca, filtros `Todos · Em andamento · Concluídos · Pré-cadastro`, combobox de UF, contador).
- **Grid de cards:** `repeat(auto-fill, minmax(340px,1fr)); gap:16px`.
- **Card:** radius 16px, borda `rgba(255,255,255,.08)`, fundo `linear-gradient(140deg, rgba(17,26,46,.92), rgba(10,16,31,.92))`, barra esquerda 3px na cor do status; hover `translateY(-3px)` + borda `rgba(242,151,29,.4)` + sombra `0 18px 40px rgba(0,0,0,.42)`. Conteúdo: badges (status com bolinha pulsante `dcPulse` + etapa atual), razão social 17px/800, CNPJ monoespaçado + UF, divisor, frente 12px/700 `#f2971d` + título 15px/600, COMPETÊNCIAS e ETAPAS em monoespaçada, barra de progresso 5px (laranja em andamento, verde concluído) e rodapé "próximo passo · atualizado há X". Clique navega para o detalhe.
- **Card fantasma** tracejado ao final abre o cadastro.
- **Modal Cadastrar trabalho:** Empresa (combobox, largura total), Tipo de trabalho (combobox), Título, Competência inicial/final em `MM/AAAA`. Validações: empresa obrigatória, título obrigatório, competências no formato `^\d{2}\/\d{4}$`. Nasce em Pré-cadastro com 0/3 etapas.

### 3. Cadastrar trabalho (`Cadastro.dc.html`)
Wizard de 4 passos. **Stepper:** pills radius 999px com número 22×22 — futuro (`rgba(255,255,255,.03)`, número `rgba(255,255,255,.07)`), atual (borda `rgba(242,151,29,.5)`, número `#f2971d` sobre `#121a2c`, texto branco), concluído (borda `rgba(52,211,153,.28)`, `✓` verde).
1. **Enviar** — dropzone tracejada (padding `46px 24px`, radius 16px; hover/preenchida muda borda para laranja/verde), lista de arquivos lidos com badge de extensão e pill "lido", CTA "Ler arquivos" com spinner ~1,1s. Aceita `.txt` (SPED Fiscal) e `.zip`.
2. **Conferir empresa** — 7 fatos do registro 0000 em `repeat(auto-fit,minmax(200px,1fr))`, cada um com barra esquerda laranja de 2px, rótulo 10px/800 `.13em`, valor 15-16px/700 (monoespaçado em CNPJ/IE/competências) e hint opcional. CTA "Pré-cadastrar empresa".
3. **Criar projeto** — Frente (combobox: CAT 42, De-para de produto, Quebra de SPED, Nota fiscal, Reenquadramento de NCM), Nome do projeto, Competência inicial/final (`type="date"` com `color-scheme:dark`), Observação (textarea 3 linhas). Valida nome, as duas datas e inicial ≤ final.
4. **Pronto** — ícone check verde, resumo em 4 cards (EMPRESA / FRENTE / PROJETO / COMPETÊNCIAS), CTA "Ver o trabalho" + "Cadastrar outra empresa".
"Começar de novo" no cabeçalho zera o wizard.

### 4. Detalhe do trabalho (`Trabalho.dc.html`)
Breadcrumb "← Trabalhos". Cabeçalho com badges, razão social 27px/800, CNPJ + UF, meta à direita (FRENTE / PROJETO / COMPETÊNCIAS) e barra de progresso "N de 8 etapas concluídas".
- **Lista de 8 etapas** (dependência real, não navegação livre). Card radius 14px com barra esquerda 3px e bolinha 30×30:
  - **Concluída** — `✓` verde, borda `rgba(52,211,153,.22)`, fundo `rgba(6,38,32,.4)`, badge "Concluída", ação ghost com hover laranja.
  - **Atual** — número em círculo `#f2971d`, borda `rgba(242,151,29,.35)`, fundo `linear-gradient(110deg, rgba(48,32,12,.5), rgba(13,20,37,.72))`, badge "Pendente", ação em botão laranja.
  - **Bloqueada** — cinza, `opacity:.72`, badge "Ainda não disponível", sem ação.
  - Etapas 1-3 navegam para as telas de etapa; 4-8 ainda não têm tela.
- **Zona de risco** ao final: card vermelho "Excluir este trabalho" + modal de confirmação (some projeto, lotes e conferências; sem desfazer).

### 5. Etapa 1 — Importar base de dados (`Etapa Importar.dc.html`)
Campo "Pasta com os arquivos" (monoespaçado) + botão "Conferir pasta" com spinner; hint sobre caminho local, subpastas e cache do Windows. Nada é copiado: registra caminho e tipo.
- **Lotes já importados:** card por lote com barra verde à esquerda, caminho monoespaçado (`word-break:break-all`), linha de números (`N arquivos`, `N para a CAT`, tamanho, período monoespaçado), pills de tipo por cor — EFD ICMS/IPI azul, XML DE NF-E verde, COMPACTADO neutro, XML DE OUTRO DOCUMENTO âmbar — data à direita e icon button × para remover (hover vermelho).
- Estado vazio tracejado quando não há lotes.

### 6. Etapa 2 — Conferir documentos (`Etapa Conferir.dc.html`)
CTA "Conferir de novo" no cabeçalho (spinner ~1,4s).
- **Resultado:** carimbo de conclusão + 4 KPIs com barra esquerda colorida (ESCRITURADAS NA EFD neutro · COM DOCUMENTO verde · SEM DOCUMENTO laranja · NÃO ESCRITURADAS cinza), barra de cobertura e 3 faixas de nota (delta desde a rodada anterior; documentos sem chave; canceladas/denegadas).
- **Blocos de saída:** "Notas conferidas" (11.693 + valor + baixar), "Notas não escrituradas" (0 + baixar), e o bloco laranja **"Notas a cobrar do cliente"** com número grande em `#f2971d`, chips POR CLASSIFICAÇÃO (a cobrar / cancelada-denegada-inutilizada / sem chave) e POR MODELO (NF-e / NF modelo 1-1A), CTA "Baixar planilha" e legenda dinâmica dos filtros. Sem filtro = planilha completa, cada linha marcada.
- Bloco final "O cliente mandou o que faltava?" com link para a Etapa 1.

### 7. Etapa 3 — Extrair movimentos (`Etapa Extrair.dc.html`)
CTA "Extrair de novo".
- **Resultado:** 4 KPIs (DOCUMENTOS NA EFD · COM ITEM NA EFD · MOVIMENTOS · SAÍDAS SEM ITEM NA EFD) + 4 faixas de nota (saídas sem item, entradas próprias, ausência de marcação da conferência, estabelecimentos).
- **Movimentos:** número grande, pills POR CST DAS ENTRADAS (CST · quantidade · valor monoespaçado), chips POR MARCA DA CONFERÊNCIA, CTA laranja "Baixar planilha".
- **Cadastro de itens** e **Inventário** lado a lado (`repeat(auto-fit,minmax(320px,1fr))`).
- **Analítico por documento:** número grande + pills SAÍDAS SEM ITEM, POR MODELO (NFC-e, CF-e-SAT, NF-e) + baixar.

### 8. Usuários (`Usuarios.dc.html`)
Cabeçalho + métricas (TOTAL / ATIVOS / SENHA PROVISÓRIA / INATIVOS), banner de flash para senha provisória (bloco monoespaçado tracejado — exibida uma única vez), busca e filtros (`Todos · Ativos · Provisórios · Inativos`).
- **Tabela** com `grid-template-columns: 1.5fr 1fr .8fr .9fr 1fr .9fr 1.4fr`, colunas **NOME · USUÁRIO · PAPEL · CARGO · SITUAÇÃO · ÚLTIMO ACESSO · AÇÕES**; wrapper com `overflow-x:auto` e `min-width:1080px`.
  - NOME: avatar 34×34 (gradiente por id via `oklch`, matizes `[222,262,32,190,300,150]`) + nome 14px/700 e e-mail 12px `#7b8dab`.
  - USUÁRIO: monoespaçado + badge **VOCÊ** quando é o usuário logado.
  - PAPEL e CARGO: texto somente leitura (edição só pelo modal).
  - SITUAÇÃO: pill com bolinha pulsante — Ativo verde, Senha provisória âmbar, Inativo cinza (prevalece quando `active === false`; linha com `opacity:.62`).
  - AÇÕES: três icon buttons 34×34 — **Editar** (lápis, laranja), **Redefinir senha** (chave, ghost→laranja), **Desativar/Reativar** (power, vermelho/verde; desabilitado na própria linha).
- **Modais:** Novo usuário (username imutável, nome, e-mail, papel e cargo em combobox, senha gerada e exibida uma vez), Editar usuário (nome, e-mail, papel — bloqueado para si mesmo — e cargo), e confirmação para redefinir senha / desativar / reativar.
- **Validações:** username `^[a-z0-9._-]{3,}$` e único; nome obrigatório; e-mail `^[^@\s]+@[^@\s]+\.[^@\s]+$`.
- **Regra de negócio:** não há autocadastro nem recuperação por e-mail; senha provisória só por gestor; troca obrigatória no primeiro acesso.

---

## Design tokens

**Cores**
| Token | Valor | Uso |
|---|---|---|
| bg/base | `#070c18` | fundo da aplicação |
| bg/panel | `rgba(13,20,37,.72)` | cards de conteúdo |
| bg/panel-grad | `linear-gradient(120deg, rgba(18,27,48,.9), rgba(10,16,31,.9))` | cabeçalhos de página |
| bg/card | `linear-gradient(140deg, rgba(17,26,46,.92), rgba(10,16,31,.92))` | cards de trabalho |
| bg/modal | `linear-gradient(150deg, rgba(19,28,50,.98), rgba(10,16,31,.98))` | modais |
| bg/dropdown | `#101a30` | painel de combobox |
| bg/login-left | `linear-gradient(160deg,#0b1c3a,#081527)` | painel de marca |
| border/subtle | `rgba(255,255,255,.07)` | divisores |
| border/default | `rgba(255,255,255,.11)` | inputs |
| border/strong | `rgba(255,255,255,.12)` | botões ghost |
| text/primary | `#e8edf7` | texto principal |
| text/secondary | `#a9b8d2` | labels |
| text/muted | `#8798b6` / `#7b8dab` | descrições |
| text/faint | `#6d7f9d` / `#6f81a0` | hints e headers |
| text/mono | `#c8d6ee` / `#93a4c1` | códigos e caminhos |
| accent/500 | `#f2971d` | laranja da marca |
| accent/grad | `linear-gradient(135deg,#f9a72b,#e8801a)` | botões primários |
| accent/soft | `#ffc478` / `#ffbb5c` | texto sobre laranja translúcido |
| success | `#6ee7b7` / `#34d399` (bg `rgba(52,211,153,.1)`) | concluído, ativo |
| info | `#93c5fd` (bg `rgba(59,130,246,.1)`) | em andamento |
| warning | `#fbbf24` (bg `rgba(240,180,41,.1)`) | pendente, provisória |
| danger | `#f87171` / `#fecaca` (bg `rgba(239,68,68,.16)`) | excluir, erro |
| neutral/status | `#94a3b8` | inativo, bloqueado |
| on-accent | `#121a2c` | texto sobre laranja sólido |
| disabled/bg | `rgba(30,58,138,.42)` + `#7f93bb` | botão desabilitado |

**Tipografia** — UI: `"Plus Jakarta Sans"` (400/500/600/700/800); monoespaçada: `"JetBrains Mono"` (400/500) para CNPJ, caminhos, competências, CST, valores em tabela e senhas.

| Papel | Tamanho / peso |
|---|---|
| H1 login | 34px / 800 |
| H1 página | 28-30px / 800 / `-.02em` |
| H1 detalhe | 27px / 800 |
| H2 seção | 18-19px / 800 |
| Número destaque | 30-38px / 800 |
| Métrica | 24-26px / 800 |
| Título de card | 16-17px / 800 |
| Corpo | 13-14px / 400-600 |
| Label de campo | 12px / 700 |
| Hint / meta | 11-12px |
| Rótulo de dado | 10px / 800 / `.13em` |
| Header de tabela | 10px / 800 / `.14em` |
| Eyebrow | 11px / 700 / `.18em` |
| Badge | 9-11px / 700-800 / `.08-.1em` |

**Espaçamento:** escala de 4px — usados 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 26, 28, 46, 48.
**Radius:** 5 (checkbox) · 6 (badge) · 8-9 (item, icon button) · 10-11 (input, botão) · 12 (dropdown, métrica, nota) · 14 (etapa, lote) · 16 (card, dropzone) · 18 (seção) · 20 (modal) · 999 (pill).
**Sombras:** `0 12px 28px rgba(242,151,29,.3)` → hover `0 16px 34px rgba(242,151,29,.42)` (CTA) · `0 18px 40px rgba(0,0,0,.42)` (card hover) · `0 22px 48px rgba(0,0,0,.55)` (dropdown) · `0 30-40px 70-90px rgba(0,0,0,.6)` (modal).

**Animações**
| Nome | Efeito | Uso |
|---|---|---|
| `dcFade` | opacity 0→1 + `translateY(8px)→0` | modais, painéis, faixas |
| `dcSweep` | `translateX(-110%)→210%` | brilho no topo de cabeçalhos (5.5s) e no CTA de login (3.4s) |
| `dcPulse` | opacity .45/.55↔1 | bolinha de status (2.4s) |
| `dcSpin` | rotação 360° | spinners (.7s) |
| `dcShake` | translateX ±5px | erro de login (.34s) |
| `dcDrift` | translate(24px,-18px) | halo do painel de login (16s) |

Transições de hover `.16-.18s`. **Respeitar `prefers-reduced-motion`** na implementação (não coberto nos protótipos).

**Responsivo:** tabelas rolam horizontalmente; grids usam `auto-fit/auto-fill` com `minmax`. **Não coberto:** sidebar colapsável e layout mobile — definir com o time.

## Assets
- `screens/assets/bms-logo.png` — logo extraída de captura (fundo removido). **Trocar pelo SVG oficial do repositório.**
- **Ícones:** SVGs inline simples (lápis, chave, power, olho, upload, check, ×, lupa, caret, lixeira, cadeado, alerta). Substituir pelo icon set do projeto — lucide-react recomendado: `pencil`, `key-round`, `power`, `eye`, `eye-off`, `upload`, `check`, `x`, `search`, `chevron-down`, `trash-2`, `lock`, `alert-circle`.
- **Fontes:** Plus Jakarta Sans e JetBrains Mono via Google Fonts — self-hostar se necessário.
- Nenhuma imagem raster além da logo.

## Notas de implementação
- Senhas provisórias: gerar no backend com CSPRNG, devolver uma única vez na resposta; nunca gerar no cliente (o protótipo gera para demonstrar o fluxo).
- Todos os números, valores e caminhos nos protótipos são dados de exemplo vindos das capturas do sistema legado.
- Autorização: a tela de Usuários é só para `Gestor`; o usuário logado não pode alterar o próprio papel nem se desativar — o backend deve reforçar, não só a UI.
- As etapas 4 a 8 do processamento ainda não têm tela desenhada.
