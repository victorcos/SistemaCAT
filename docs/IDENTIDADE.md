# IDENTIDADE VISUAL — CRM Fiscal

> A paleta vem da marca **BMS Consultoria Tributária**.
> Os tokens ficam em `frontend/src/estilos/tokens.css` e são a única fonte.
> Componente que escreve hexadecimal direto está errado.

---

## 1. As cores da marca

Extraídas dos **arquivos oficiais da marca**, em alta resolução e com
transparência, por amostragem de pixel.

| Cor | Hex | Onde aparece na marca |
|---|---|---|
| Marinho | `#021D44` | tipografia e símbolo |
| Laranja | `#FF7F00` | símbolo |
| Dourado | `#C19B54` | linha divisória da versão Equipe SP |
| Branco | `#FFFFFF` | tipografia sobre fundo escuro |

> **Correção de 10/09/2026.** Os primeiros valores foram tirados de uma captura
> de tela comprimida e estavam deslocados: `#081C41` contra o marinho real
> `#021D44`, e sobretudo `#EE8633` contra o laranja real `#FF7F00`. Compressão
> de imagem desloca cor, e captura de tela nunca serve como fonte de paleta.

## 2. Contraste conferido

Medido pelo critério WCAG AA, que pede 4,5:1 para texto normal.

| Combinação | Razão | Situação |
|---|---|---|
| Branco sobre marinho | 16,64:1 | aprovado |
| Laranja sobre marinho | 6,57:1 | aprovado |
| Marinho sobre branco | 16,64:1 | aprovado |
| Marinho sobre o laranja | 6,57:1 | aprovado |
| **Laranja sobre branco** | **2,53:1** | **reprovado** |
| **Branco sobre o laranja** | **2,53:1** | **reprovado** |

**Consequência.** O laranja e o dourado da marca funcionam sobre o azul, mas não
servem para texto sobre fundo claro. Para isso existem `--laranja-700` e
`--dourado-700`, escurecidos até passarem, mantendo o mesmo matiz.

O botão principal usa laranja da marca com texto **azul-escuro**, não branco.
Branco sobre laranja dá 2,53:1 e reprova.

## 3. Como a paleta é aplicada

**Fundo claro por padrão.** O analista passa horas lendo tabela de milhão de
linhas. Fundo escuro em jornada longa cansa mais e prejudica a leitura de número.

**O azul da marca fica na moldura.** Cabeçalho, menu lateral e cabeçalho de
tabela. É onde a identidade aparece sem competir com o dado.

**O laranja é ação, não decoração.** Botão principal, item ativo do menu, e
pouco mais. Laranja espalhado perde a função de dizer "clique aqui".

**O dourado é divisória.** Separador de seção e faixa de destaque, como na
própria marca. Não usar em texto corrido.

**Tema escuro existe** e nele o azul da marca vira o fundo do sistema inteiro.
Segue a preferência do sistema operacional, e a escolha explícita do usuário
vence nos dois sentidos.

## 4. A regra que evita confusão

**Atenção não usa o laranja da marca.** O token `--atencao` é um âmbar
deliberadamente diferente. Se o alerta tiver a mesma cor do botão principal, o
usuário deixa de distinguir identidade de aviso, e num sistema fiscal isso custa
caro.

## 5. Cores do domínio

Conceitos que aparecem em tabela e gráfico o tempo todo ganharam token próprio,
para não haver duas telas pintando ressarcimento de cores diferentes.

| Token | Significado |
|---|---|
| `--fiscal-ressarcimento` | crédito a favor do contribuinte |
| `--fiscal-complemento` | valor devido |
| `--fiscal-verificar` | anomalia, exige julgamento |
| `--fiscal-sem-valor` | linha sem apuração |
| `--fiscal-estoque` | saldo e movimentação |

## 6. Número em tabela

Fonte monoespaçada, algarismo tabular e alinhamento à direita. Sem isso, a coluna
de valor não se lê ao percorrer com o olho, que é exatamente o que o revisor faz
o dia inteiro.

## 7. Os arquivos do logotipo

Todos com fundo transparente, gerados dos oficiais em alta resolução.

| Arquivo | Tinta | Onde usar |
|---|---|---|
| `bms-marinho.png` | marinho e laranja | superfície **clara** |
| `bms-branco.png` | branco e laranja | superfície **escura** |
| `bms-marinho-compacto.png` | marinho e laranja | espaço apertado, sem o descritivo |
| `bms-branco-compacto.png` | branco e laranja | idem, sobre escuro |

Cada um tem também a versão de largura reduzida, com sufixo numérico, e o
original em alta guardado em `docs/marca/*-original.png`.

**A limitação anterior acabou.** Antes só existia a versão branca, tirada de
captura de tela, o que obrigava a colar retângulos azuis atrás do logotipo em
qualquer superfície clara. Esses remendos foram removidos.

**O que ainda ajudaria:** o logotipo em vetor (SVG ou AI). O PNG em 4900 px
resolve qualquer tamanho de tela, mas vetor gera favicon e material impresso
sem perda.

## 8. A pergunta do fundo claro contra fundo escuro

**O que está implementado:** tema claro por padrão, tema escuro disponível,
seguindo a preferência do sistema operacional, com a escolha explícita do usuário
vencendo nos dois sentidos. Não existe versão "azul por padrão".

**O que continua em aberto:** se a moldura, isto é, cabeçalho e menu lateral,
deve ser azul da marca ou clara no tema claro.

| | Moldura marinho (atual) | Moldura clara |
|---|---|---|
| Identidade | presente o tempo todo | só nos detalhes |
| Área útil para dado | igual | igual |
| Descanso visual | separa navegação de conteúdo | menos contraste entre as áreas |

A moldura segue marinho, mas agora **por escolha, não por falta de arquivo**:
ela ancora a navegação e dá descanso ao olho de quem lê tabela o dia inteiro.
Trocar por moldura clara é possível a qualquer momento — a variante existe.
