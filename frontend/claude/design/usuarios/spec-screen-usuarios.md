# Handoff: Tela de Usuários — Sistema CAT (BMS Consultoria Tributária)

## Overview
Tela de administração de usuários de um sistema interno de consultoria tributária. Um gestor (papel `Gestor`) lista os usuários da empresa, cria novos usuários, edita nome/e-mail/papel/cargo, gera senhas provisórias e ativa/desativa acessos. **Não existe autocadastro nem recuperação de senha por e-mail** — toda gestão de credenciais passa por um gestor.

Esta é uma reconstrução visual da tela legada (ver descrição em "Origem"): mesma paleta (azul-marinho escuro + laranja) e mesma logo BMS, com layout reorganizado e moderno.

## About the Design Files
Os arquivos deste pacote são **referências de design feitas em HTML** — protótipos que mostram aparência e comportamento pretendidos, **não código de produção para copiar**. A tarefa é **recriar estes designs no ambiente do codebase de destino** (React, Vue, Angular, etc.) usando os padrões e bibliotecas já estabelecidos lá. Se ainda não houver ambiente definido, escolher o framework mais adequado — o cliente indicou preferência por **React + Tailwind CSS + componentes estilo Aceternity UI** (efeitos de brilho/gradiente sutis, animações de entrada).

O protótipo usa estilos inline por restrição da ferramenta de prototipagem; na implementação real, traduzir para classes utilitárias Tailwind / tokens do design system.

## Fidelity
**High-fidelity (hifi).** Cores, tipografia, espaçamentos, estados e microinterações estão definidos. Recriar com fidelidade visual alta usando as bibliotecas do codebase.

## Origem (tela legada substituída)
A tela antiga tinha: sidebar escura com logo BMS, topo com nome do usuário + badge GESTOR + "1 empresa" + botão Sair, título "Usuários", botão laranja "Novo usuário", formulário de criação inline (expandindo acima da tabela) e uma tabela com selects nativos de Papel e Cargo editáveis direto na linha, badges de situação e botões "Redefinir senha"/"Desativar". Confirmações usavam `window.confirm()` nativo.

Mudanças aplicadas no redesign:
- Formulário de criação virou **modal**, não mais expansão inline.
- Papel e Cargo **não são mais editáveis na linha** — passam por um **modal "Editar usuário"**.
- Coluna **NOME é a primeira** da tabela (antes era USUÁRIO).
- Ações viraram **icon buttons** (lápis / chave / power) com `title` e `aria-label`.
- Todos os dropdowns são **comboboxes customizados com busca** — nenhum `<select>` nativo.
- `window.confirm()` substituído por **modal de confirmação** próprio.
- Adicionada faixa de **métricas** (total / ativos / senha provisória / inativos), **busca** e **filtros por situação**.
- Senha provisória gerada é exibida em um **banner de flash** com bloco monoespaçado (aparece uma única vez).

## Screens / Views

### 1. Shell (sidebar + topbar)
**Propósito:** navegação global e identidade.

**Layout:** `display:flex`, altura mínima 100vh.
- **Sidebar:** largura fixa `244px` (`flex: 0 0 244px`), `position: sticky; top: 0; height: 100vh`, padding `22px 16px`, `gap: 28px`, borda direita `1px solid rgba(255,255,255,.07)`, fundo `linear-gradient(180deg, rgba(12,19,36,.9), rgba(8,13,25,.9))`.
  - **Logo:** bloco de `38×38px`, `border-radius: 11px`, fundo `linear-gradient(140deg, #f2971d, #d9741a)`, sombra `0 8px 22px rgba(242,151,29,.28)`, contendo duas barras inclinadas (`transform: skewX(-14deg)`) escuras — **substituir pelo SVG oficial da logo BMS do repositório**. Ao lado: "BMS" (20px / 800 / `letter-spacing: .08em`) e "CONSULTORIA TRIBUTÁRIA" (8px / 600 / `letter-spacing: .22em` / `#7e8fad`).
  - **Nav:** rótulo "NAVEGAÇÃO" (10px / 700 / `.16em` / `#5f7191`); itens "Início", "Cadastro", "Usuários". Item inativo: 14px/600, `#9fb0cd`, hover `background: rgba(255,255,255,.05)` + `color: #e8edf7`, `border-radius: 10px`, padding `10px 12px`, com bolinha de 6px `#3c4a66`. Item ativo ("Usuários"): fundo `linear-gradient(90deg, rgba(242,151,29,.16), rgba(242,151,29,.02))`, borda `1px solid rgba(242,151,29,.28)`, barra lateral esquerda de 2px `#f2971d`, bolinha `#f2971d` com `box-shadow: 0 0 10px #f2971d`, texto branco 700.
  - **Rodapé da sidebar:** card `rgba(255,255,255,.02)`, borda `rgba(255,255,255,.06)`, "Sistema CAT" (11px `#6d7f9d`) + "sessão não comercial" (11px `#4d5d79`).
- **Topbar:** `position: sticky; top: 0; z-index: 20`, padding `16px 28px`, fundo `rgba(8,13,25,.72)` + `backdrop-filter: blur(10px)`, borda inferior `1px solid rgba(255,255,255,.07)`.
  - Avatar `30×30`, radius 9px, `linear-gradient(140deg, #1e3a8a, #0f1e3f)`, iniciais 12px/700 `#cfe0ff`.
  - Nome "Diretor" 14px/700; badge "GESTOR" 10px/800, `letter-spacing:.1em`, padding `4px 8px`, radius 6px, fundo `rgba(255,255,255,.07)`, borda `rgba(255,255,255,.1)`, texto `#c6d4ea`; "1 empresa" 13px `#7b8dab`.
  - Botão **Sair** à direita: padding `9px 18px`, radius 10px, fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.12)`, texto `#dce6f7` 13px/700; hover → fundo `rgba(239,68,68,.14)`, borda `rgba(239,68,68,.4)`, texto `#fecaca`; transição `.18s`.

**Fundo da página:** `radial-gradient(900px 500px at 18% -10%, rgba(242,151,29,.10), transparent 60%), radial-gradient(900px 600px at 90% 0%, rgba(37,99,235,.14), transparent 65%), #070c18`.

### 2. Cabeçalho da página + métricas
Card com `border-radius: 18px`, borda `1px solid rgba(255,255,255,.08)`, fundo `linear-gradient(120deg, rgba(18,27,48,.9), rgba(10,16,31,.9))`, padding `24px 26px`, `position: relative; overflow: hidden`.
- Glow interno: `radial-gradient(420px 160px at 8% 0%, rgba(242,151,29,.16), transparent 70%)` (pointer-events none).
- **Linha de brilho superior (efeito Aceternity):** faixa de 1px no topo; filho de 40% de largura com `linear-gradient(90deg, transparent, #f2971d, transparent)` animado por `@keyframes dcSweep { 0%{translateX(-110%)} 100%{translateX(210%)} }`, `5.5s linear infinite`.
- Eyebrow "ADMINISTRAÇÃO": 11px/700, `letter-spacing:.18em`, `#f2971d`.
- Título "Usuários": 30px/800, `letter-spacing: -.02em`.
- Descrição: 14px, `line-height 1.55`, `#8798b6`, `max-width 560px`, `text-wrap: pretty` — texto exato: "Cadastro e redefinição de senha ficam com gestores. Não há autocadastro nem recuperação por e-mail."
- **Botão "+ Novo usuário":** padding `13px 22px`, radius 12px, sem borda, fundo `linear-gradient(135deg, #f9a72b, #e8801a)`, texto `#121a2c` 14px/800, sombra `0 12px 28px rgba(242,151,29,.3)`; hover `translateY(-2px)` + sombra `0 16px 34px rgba(242,151,29,.42)`.
- **Métricas:** `grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap: 12px; margin-top: 22px`. Cada card: padding `14px 16px`, radius 12px; rótulo 11px/700 `letter-spacing:.12em`; número 24px/800.
  - TOTAL — borda `rgba(255,255,255,.07)`, fundo `rgba(255,255,255,.03)`, rótulo `#7486a5`
  - ATIVOS — borda `rgba(52,211,153,.18)`, fundo `rgba(52,211,153,.06)`, rótulo `#6ee7b7`
  - SENHA PROVISÓRIA — borda `rgba(240,180,41,.2)`, fundo `rgba(240,180,41,.06)`, rótulo `#fbbf24`
  - INATIVOS — igual a TOTAL

### 3. Banner de flash (senha provisória / confirmação de ação)
Aparece abaixo do cabeçalho após criar usuário, redefinir senha ou ativar/desativar. Padding `16px 18px`, radius 14px, borda `1px solid rgba(242,151,29,.35)`, fundo `linear-gradient(100deg, rgba(242,151,29,.14), rgba(242,151,29,.03))`, animação `dcFade .25s`.
- Ícone 34×34 radius 10px `rgba(242,151,29,.2)` (chave) — **trocar emoji 🔑 por ícone SVG do design system**.
- Título 13px/700; corpo 13px `#b9c7e0`.
- **Senha** (quando houver): `<code>` monoespaçado 15px, `letter-spacing:.06em`, padding `9px 14px`, radius 9px, fundo `rgba(0,0,0,.4)`, borda tracejada `1px dashed rgba(242,151,29,.5)`, texto `#ffd08a`.
- Botão × para dispensar (`#94a5c2`, hover branco).
- **Recomendação de implementação:** adicionar botão "Copiar" na senha; a senha nunca é reexibida.

### 4. Tabela de usuários
Card: radius 18px, borda `rgba(255,255,255,.08)`, fundo `rgba(13,20,37,.72)`, `overflow: hidden`.

**Toolbar** (padding `16px 18px`, borda inferior `rgba(255,255,255,.07)`, `flex-wrap: wrap; gap: 12px`):
- **Busca:** largura flexível `min 220px / max 360px`; input padding `11px 14px 11px 32px`, radius 10px, fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.1)`, 13px; foco → borda `rgba(242,151,29,.55)` + fundo `rgba(242,151,29,.06)`. Ícone de lupa absoluto à esquerda (13px, `#6b7d9b`). Placeholder: "Buscar por usuário, nome ou e-mail". Filtra por `username`, `name` e `email` (case-insensitive, substring).
- **Filtros (segmented):** container padding 4px, radius 11px, fundo `rgba(255,255,255,.03)`, borda `rgba(255,255,255,.08)`. Opções: **Todos · Ativos · Provisórios · Inativos**. Ativo: fundo `rgba(242,151,29,.16)`, texto `#ffbb5c`; inativo: transparente, `#8798b6`. 12px/700, padding `8px 14px`, radius 8px.
- **Contador** à direita: "N usuários" (singular "1 usuário"), 12px/600 `#7486a5`.

**Grid de colunas** (header e linhas usam o mesmo template):
`grid-template-columns: 1.5fr 1fr .8fr .9fr 1fr .9fr 1.4fr; gap: 12px;`
Ordem: **NOME · USUÁRIO · PAPEL · CARGO · SITUAÇÃO · ÚLTIMO ACESSO · AÇÕES** (AÇÕES alinhado à direita).
Wrapper com `overflow-x: auto` e `min-width: 1080px` interno.

**Header:** padding `12px 18px`, fundo `rgba(255,255,255,.025)`, borda inferior `rgba(255,255,255,.06)`, texto 10px/800 `letter-spacing:.14em` `#6f81a0`.

**Linha:** padding `14px 18px`, borda inferior `rgba(255,255,255,.05)`, hover `background: rgba(255,255,255,.035)` (`transition: background .16s`). Usuário inativo: `opacity: .62`.
- **NOME:** avatar 34×34, radius 10px, borda `rgba(255,255,255,.1)`, iniciais 12px/800 `#e9f0ff`; fundo por id — `linear-gradient(140deg, oklch(0.42 0.09 H), oklch(0.28 0.06 H))` com H ciclando em `[222, 262, 32, 190, 300, 150]`. À direita: nome 14px/700 e e-mail 12px `#7b8dab` (ambos com `text-overflow: ellipsis`).
- **USUÁRIO:** `<code>` monoespaçado 13px `#c8d6ee`; se for o próprio usuário logado, badge **VOCÊ** (9px/800, `.1em`, padding `3px 6px`, radius 5px, fundo `rgba(242,151,29,.16)`, borda `rgba(242,151,29,.35)`, texto `#ffbb5c`).
- **PAPEL:** texto 13px/600 `#dbe5f6` (somente leitura).
- **CARGO:** texto 13px `#a9b8d2` (somente leitura).
- **SITUAÇÃO:** pill `inline-flex`, gap 7px, 11px/700, padding `5px 10px`, radius 999px, com bolinha de 6px animada (`dcPulse 2.4s ease-in-out infinite`, opacidade .55↔1):
  - Ativo — texto `#6ee7b7`, fundo `rgba(52,211,153,.1)`, borda `rgba(52,211,153,.3)`
  - Senha provisória — texto `#fbbf24`, fundo `rgba(240,180,41,.1)`, borda `rgba(240,180,41,.32)`
  - Inativo — texto `#94a3b8`, fundo `rgba(148,163,184,.1)`, borda `rgba(148,163,184,.28)` (prevalece sobre o status quando `active === false`)
- **ÚLTIMO ACESSO:** 13px `#93a4c1`; "nunca entrou" quando nulo; senão `DD/MM/AAAA, HH:MM`.
- **AÇÕES:** três icon buttons de `34×34px`, radius 9px, gap 8px, `transition: all .16s`, cada um com `title` + `aria-label`:
  1. **Editar** (lápis) — fundo `rgba(242,151,29,.12)`, borda `rgba(242,151,29,.34)`, ícone `#ffc478`; hover fundo `rgba(242,151,29,.22)`, borda `rgba(242,151,29,.65)`, `translateY(-1px)`.
  2. **Redefinir senha** (chave) — fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.12)`, ícone `#c8d6ee`; hover fundo `rgba(242,151,29,.14)`, borda `rgba(242,151,29,.45)`, ícone `#ffc478`, `translateY(-1px)`.
  3. **Desativar / Reativar** (power) — fundo transparente; ativo: borda `rgba(248,113,113,.35)` + ícone `#f87171`; inativo (ação "Reativar"): borda `rgba(52,211,153,.35)` + ícone `#6ee7b7`; próprio usuário: desabilitado, borda `rgba(255,255,255,.07)`, ícone `#475569`, `cursor: not-allowed`. Hover `background: rgba(255,255,255,.06)`.
  - Ícones: SVG 16×16, `viewBox 0 0 24 24`, `fill:none`, `stroke: currentColor`, `stroke-width: 1.8`, `linecap/linejoin: round`. Substituir pelos equivalentes do icon set do codebase (ex.: lucide `pencil`, `key-round`, `power`).

**Estado vazio:** padding `54px 18px`, centralizado — "Nenhum usuário encontrado" (15px/700 `#b7c5de`) + "Ajuste a busca ou o filtro de situação." (13px `#7486a5`).

### 5. Combobox com busca (substitui todos os `<select>`)
Usado em Papel e Cargo nos modais de criação e edição. **Nenhum dropdown nativo na tela.**
- **Trigger:** botão full-width, padding `11px 13px`, radius 10px, fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.11)` (aberto: `rgba(242,151,29,.55)`; desabilitado: `rgba(255,255,255,.06)`), texto 13px/600 `#e8edf7` (desabilitado `#5a6b88`, `cursor: not-allowed`), caret `▾`/`▴` 11px `#7f91af` à direita. Substituir caret por ícone chevron do icon set.
- **Painel:** `position: absolute; top: calc(100% + 6px); left:0; right:0; z-index: 90`, radius 12px, borda `rgba(255,255,255,.12)`, fundo `#101a30`, sombra `0 22px 48px rgba(0,0,0,.55)`, `overflow: hidden`, animação `dcFade .14s`.
  - **Campo de busca:** padding do wrapper 9px, borda inferior `rgba(255,255,255,.07)`; input padding `8px 10px`, radius 8px, fundo `rgba(255,255,255,.05)`, borda `rgba(255,255,255,.1)`, 12px; foco borda `rgba(242,151,29,.5)`; placeholder "Buscar…". **Recebe foco automaticamente ao abrir.**
  - **Lista:** `max-height: 200px; overflow-y: auto; padding: 6px`. Item: padding `9px 10px`, radius 8px, 13px/600, hover `rgba(255,255,255,.06)`; selecionado: fundo `rgba(242,151,29,.14)`, texto `#ffc478`, check `✓` à direita; demais `#cfdbef`.
  - **Sem resultado:** "Nenhum resultado", 12px `#6d7f9d`, padding `12px 10px`.
- **Comportamento:** filtro por substring case-insensitive; fecha ao selecionar; fecha em clique fora (listener `mousedown` em capture que ignora cliques dentro do `[data-picker]` aberto); a query é limpa ao abrir/fechar; apenas um combobox aberto por vez.
- **A implementar na versão real (não coberto no protótipo):** navegação por teclado (↑/↓/Enter/Esc/Home/End), `role="combobox"`/`listbox`/`option`, `aria-expanded`, `aria-activedescendant`, e reposicionamento para cima quando não houver espaço abaixo.

### 6. Modal "Novo usuário"
Overlay: `position: fixed; inset: 0; z-index: 60`, fundo `rgba(4,8,16,.66)` + `backdrop-filter: blur(6px)`, `align-items: flex-start`, padding `48px 20px`, `overflow-y: auto`.
Card: `max-width: 880px`, radius 20px, borda `rgba(255,255,255,.1)`, fundo `linear-gradient(150deg, rgba(19,28,50,.98), rgba(10,16,31,.98))`, sombra `0 40px 90px rgba(0,0,0,.6)`, animação `dcFade .22s`. **Sem `overflow: hidden`** (para os dropdowns não serem cortados).
- **Header** (padding `22px 26px`, borda inferior `rgba(255,255,255,.07)`): título "Novo usuário" 20px/800; subtítulo 13px `#8798b6` — "A senha é gerada pelo sistema e aparece uma única vez. A troca é obrigatória no primeiro acesso."; botão × 32×32 radius 9px.
- **Corpo** (padding `24px 26px`): `grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 18px`. Campos, nesta ordem:
  1. **Nome de usuário** — input monoespaçado, placeholder `ana.silva`; hint "Não pode ser alterado depois. Minúsculas, números, ponto, hífen e sublinhado."
  2. **Nome completo** — placeholder "Ana Silva"
  3. **E-mail** — placeholder "ana.silva@bms.local"
  4. **Papel** — combobox (Gestor · Operação · Leitura); hint dinâmico: Gestor → "Cadastra usuários e redefine senhas."; Operação → "Edita dados, sem gestão de acesso."; Leitura → "Só consulta."
  5. **Cargo** — combobox (Diretor · Gerente · Coordenador · Analista · Estagiário · Outro); hint "Posição na empresa. Não define permissão."
  - Label 12px/700 `#a9b8d2`; input padding `11px 13px`, radius 10px, fundo `rgba(255,255,255,.04)`, borda `rgba(255,255,255,.11)`, 13px, foco borda `rgba(242,151,29,.55)`; hint 11px `#6d7f9d`, `line-height 1.45`.
- **Footer** (padding `18px 26px 24px`, borda superior `rgba(255,255,255,.07)`): mensagem à esquerda 12px — padrão `#6d7f9d` "A senha provisória é exibida após a criação.", erro `#fca5a5`; botão **Cancelar** (ghost) e **Criar usuário** (laranja, padding `11px 22px`, radius 10px, 13px/800, sombra `0 10px 24px rgba(242,151,29,.28)`, hover `translateY(-1px)`).
- **Defaults do formulário:** Papel = `Leitura`, Cargo = `Analista`, demais vazios.

### 7. Modal "Editar usuário"
Mesmo overlay (`z-index: 65`) e mesmo card, `max-width: 640px`.
- Header: "Editar usuário" + subtítulo "Nome de usuário `<username>` não pode ser alterado."
- Corpo (mesmo grid): **Nome completo**, **E-mail**, **Papel** (combobox — desabilitado quando é o próprio usuário, hint "Você não pode alterar seu próprio papel."), **Cargo** (combobox).
- Footer: mensagem padrão "Alterações de papel valem no próximo acesso do usuário." (erro em `#fca5a5`); botões **Cancelar** e **Salvar alterações** (laranja).

### 8. Modal de confirmação (substitui `window.confirm`)
Overlay `z-index: 70`, centralizado. Card `max-width: 440px`, radius 18px, padding 26px, mesmo fundo/sombra, animação `dcFade .18s`.
- Ícone 40×40 radius 12px com fundo temático; título 17px/800 `margin: 16px 0 8px`; corpo 13px `line-height 1.6` `#8798b6`; ações à direita com gap 10px.
- **Redefinir senha:** ícone chave, fundo `rgba(242,151,29,.18)`; título "Gerar nova senha provisória para `<nome>`?"; corpo "A senha atual deixa de funcionar na hora, e a nova aparece uma única vez."; CTA "Gerar senha" (gradiente laranja, texto `#121a2c`).
- **Desativar:** ícone pausa, fundo `rgba(239,68,68,.16)`; título "Desativar `<nome>`?"; corpo "O acesso é bloqueado imediatamente. O histórico do usuário é preservado."; CTA "Desativar" — fundo `rgba(239,68,68,.16)`, borda `rgba(239,68,68,.45)`, texto `#fecaca`.
- **Reativar:** ícone play, fundo `rgba(52,211,153,.16)`; título "Reativar `<nome>`?"; corpo "O usuário volta a acessar o sistema com uma senha provisória."; CTA "Reativar" — fundo `rgba(52,211,153,.16)`, borda `rgba(52,211,153,.45)`, texto `#a7f3d0`.

## Interactions & Behavior

| Gatilho | Efeito |
|---|---|
| Digitar na busca | Filtra a lista por `username`, `name`, `email` (substring, case-insensitive) |
| Clicar em filtro | `Todos` / `Ativos` (status ativo) / `Provisórios` (senha provisória) / `Inativos` (`active === false`) |
| **+ Novo usuário** | Abre modal de criação, limpa erro |
| **Criar usuário** | Valida → cria usuário com status `provisoria`, `lastAccess = "nunca entrou"`, fecha modal, reseta form e exibe flash com a senha gerada |
| **Editar** (lápis) | Abre modal de edição pré-preenchido |
| **Salvar alterações** | Valida nome e e-mail → atualiza usuário, fecha modal, flash "`<nome>` atualizado · Papel: X · Cargo: Y" |
| **Redefinir senha** (chave) | Modal de confirmação → gera senha, define status `provisoria` e `lastAccess = "nunca entrou"`, flash com a senha |
| **Desativar/Reativar** (power) | Modal de confirmação → alterna `active`; ao desativar, status vira `inativo`; ao reativar, `provisoria`; flash informativo. Desabilitado na própria linha |
| Clique fora de um combobox aberto | Fecha o combobox e limpa a query |
| Abrir combobox | Foca o campo de busca (`setTimeout 0`) |

**Validações (criação):**
- `username`: regex `^[a-z0-9._-]{3,}$` → "Nome de usuário inválido: mínimo 3 caracteres, minúsculas, números, ponto, hífen ou sublinhado."
- `name`: obrigatório → "Informe o nome completo."
- `email`: regex `^[^@\s]+@[^@\s]+\.[^@\s]+$` → "Informe um e-mail válido."
- `username` duplicado → "Esse nome de usuário já existe."

**Validações (edição):** nome obrigatório e e-mail válido (mesmas mensagens). `username` é imutável.

**Geração de senha (protótipo):** 10 caracteres do alfabeto `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (sem I, O, 0, 1), formatados `XXXXX-XXXXX`. **Na implementação real a senha deve ser gerada no backend com CSPRNG e devolvida uma única vez na resposta da API; nunca gerar no cliente.**

**Animações:** `dcFade` (opacity 0→1 + `translateY(8px)→0`) em modais e flash; `dcSweep` no brilho do header (5.5s linear infinite); `dcPulse` na bolinha do status (2.4s). Transições de hover `.16s–.18s`. Respeitar `prefers-reduced-motion` na implementação (não coberto no protótipo).

**Responsivo:** tabela rola horizontalmente abaixo de ~1080px. **Não coberto no protótipo:** sidebar colapsável e versão em cards para mobile — definir com o time.

## State Management
```
users: [{ id, username, name, email, role, position, status: 'ativo'|'provisoria'|'inativo', lastAccess, active, self }]
query: string                 // busca
filter: 'Todos'|'Ativos'|'Provisórios'|'Inativos'
showNew: boolean              // modal de criação
form: { username, name, email, role, position }
formError: string
edit: null | { id, username, name, email, role, position, isSelf }
editError: string
confirm: null | { icon, title, body, ctaLabel, onConfirm, ... }
flash: null | { title, body, secret? }
openPicker: null | 'newRole'|'newPosition'|'editRole'|'editPosition'
pickerQuery: string
```

**API esperada (a confirmar com o backend):**
- `GET /usuarios` → lista
- `POST /usuarios` → cria; resposta inclui `senhaProvisoria` (única exibição)
- `PATCH /usuarios/:id` → nome, e-mail, papel, cargo
- `POST /usuarios/:id/redefinir-senha` → resposta inclui `senhaProvisoria`
- `POST /usuarios/:id/ativar` | `/desativar`

**Regras de autorização:** somente `Gestor` acessa a tela; o usuário logado não pode alterar o próprio papel nem se desativar (backend deve reforçar, não só a UI).

## Design Tokens

**Cores**
| Token | Valor | Uso |
|---|---|---|
| bg/base | `#070c18` | fundo da aplicação |
| bg/panel | `rgba(13,20,37,.72)` | card da tabela |
| bg/panel-grad | `linear-gradient(120deg, rgba(18,27,48,.9), rgba(10,16,31,.9))` | card de cabeçalho |
| bg/modal | `linear-gradient(150deg, rgba(19,28,50,.98), rgba(10,16,31,.98))` | modais |
| bg/dropdown | `#101a30` | painel de combobox |
| border/subtle | `rgba(255,255,255,.07)` | divisores |
| border/default | `rgba(255,255,255,.11)` | inputs |
| border/strong | `rgba(255,255,255,.12)` | botões ghost |
| text/primary | `#e8edf7` | texto principal |
| text/secondary | `#a9b8d2` | labels |
| text/muted | `#8798b6` / `#7b8dab` | descrições |
| text/faint | `#6d7f9d` / `#6f81a0` | hints e headers de tabela |
| text/mono | `#c8d6ee` | usernames |
| accent/500 | `#f2971d` | laranja da marca |
| accent/grad | `linear-gradient(135deg, #f9a72b, #e8801a)` | botões primários |
| accent/soft | `#ffc478` / `#ffbb5c` | texto sobre laranja translúcido |
| success | `#6ee7b7` (bg `rgba(52,211,153,.1)`) | status ativo |
| warning | `#fbbf24` (bg `rgba(240,180,41,.1)`) | senha provisória |
| danger | `#f87171` / `#fecaca` | desativar |
| neutral/status | `#94a3b8` | inativo |
| on-accent | `#121a2c` | texto sobre laranja sólido |

**Tipografia** — família UI: `"Plus Jakarta Sans"` (Google Fonts, 400/500/600/700/800); monoespaçada: `"JetBrains Mono"` (400/500).
| Papel | Tamanho / peso |
|---|---|
| H1 página | 30px / 800 / `-.02em` |
| H2 modal | 20px / 800 |
| H3 confirmação | 17px / 800 |
| Métrica | 24px / 800 |
| Corpo | 13–14px / 400–600 |
| Label de campo | 12px / 700 |
| Hint / meta | 11–12px / 400–600 |
| Header de tabela | 10px / 800 / `.14em` |
| Eyebrow | 11px / 700 / `.18em` |
| Badge | 9–10px / 800 / `.1em` |

**Espaçamento:** escala de 4px — usados: 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 26, 28, 48.
**Radius:** 5 (badge) · 8 (item de lista) · 9 (icon button) · 10 (input/botão) · 11 · 12 (dropdown/métrica) · 14 (flash) · 18 (card/modal pequeno) · 20 (modal grande) · 999 (pill).
**Sombras:** `0 8px 22px rgba(242,151,29,.28)` (logo) · `0 10px 24px rgba(242,151,29,.28)` (CTA modal) · `0 12px 28px rgba(242,151,29,.3)` → hover `0 16px 34px rgba(242,151,29,.42)` (CTA principal) · `0 22px 48px rgba(0,0,0,.55)` (dropdown) · `0 30px 70px` / `0 40px 90px rgba(0,0,0,.6)` (modais).

## Assets
- **Logo BMS:** o protótipo usa um placeholder geométrico (bloco laranja com duas barras inclinadas) + wordmark em texto. **Usar o SVG oficial da logo BMS já existente no codebase/repositório.**
- **Ícones:** SVGs inline simples (lápis, chave, power, lupa, caret). Substituir pelo icon set do projeto (lucide-react recomendado: `pencil`, `key-round`, `power`, `search`, `chevron-down`, `check`, `x`).
- **Emojis** usados como placeholder nos modais (🔑 ⏸ ▶) devem ser trocados por ícones SVG.
- **Fontes:** Plus Jakarta Sans e JetBrains Mono via Google Fonts — self-hostar se o projeto exigir.
- Nenhuma imagem raster.

## Files
- `Usuarios.dc.html` — protótipo completo da tela (markup + lógica de estado). Abre direto no navegador.
- `support.js` — runtime da ferramenta de prototipagem; necessário apenas para abrir o HTML localmente, **não** faz parte da entrega de produção.
