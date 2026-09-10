# IDENTIDADE VISUAL — Sistema CAT

> A paleta vem da marca **BMS Consultoria Tributária**.
> Os tokens ficam em `frontend/src/estilos/tokens.css` e são a única fonte.
> Componente que escreve hexadecimal direto está errado.

---

## 1. As cores da marca

Extraídas do arquivo original do logotipo, por amostragem de pixel, não a olho.
O logotipo de referência está em `docs/marca/logo-bms.png`.

| Cor | Hex | Onde aparece na marca |
|---|---|---|
| Azul marinho | `#081C41` | fundo do logotipo |
| Laranja | `#EE8633` | símbolo |
| Dourado | `#C19B54` | linha divisória |
| Branco | `#FFFFFF` | tipografia |

## 2. Contraste conferido

Medido pelo critério WCAG AA, que pede 4,5:1 para texto normal.

| Combinação | Razão | Situação |
|---|---|---|
| Branco sobre azul | 16,76:1 | aprovado |
| Laranja sobre azul | 6,46:1 | aprovado |
| Dourado sobre azul | 6,45:1 | aprovado |
| Azul sobre branco | 16,76:1 | aprovado |
| **Laranja sobre branco** | **2,59:1** | **reprovado** |
| **Dourado sobre branco** | **2,60:1** | **reprovado** |

**Consequência.** O laranja e o dourado da marca funcionam sobre o azul, mas não
servem para texto sobre fundo claro. Para isso existem `--laranja-700` e
`--dourado-700`, escurecidos até passarem, mantendo o mesmo matiz.

O botão principal usa laranja da marca com texto **azul-escuro**, não branco.
Branco sobre laranja dá 2,59:1 e reprova.

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
