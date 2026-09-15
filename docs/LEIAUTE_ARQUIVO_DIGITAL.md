# Leiaute do arquivo digital da CAT 42 — referência para a etapa 7

> Fonte: *Manual de Orientação da Formação do Arquivo Digital do "Sistema de
> Apuração do Ressarcimento ou Complemento do ICMS Retido por Substituição
> Tributária ou Antecipado"*, SEFAZ-SP, **versão 1.50**, 18 páginas.
> Baixa sem login:
> https://portal.fazenda.sp.gov.br/servicos/st/Downloads/Leiaute_Arquivo_Digital_Sistema%20Ressarcimento_ICMS_ST.pdf
>
> Transcrito em 15/09/2026 para a etapa 7 ("Gerar o arquivo digital"). O
> cálculo das colunas da Ficha 3 está no outro manual, o do Sistema de Apuração
> (ver `DOMINIO.md`, seções 5 a 9). Este aqui diz **como o arquivo é escrito**.

---

## 1. Regras técnicas do arquivo

| Regra | Como é |
|---|---|
| Codificação | texto ASCII **ISO 8859-1 (Latin-1)**; nada de packed, zonado, binário, float, EBCDIC |
| Organização | sequencial; registros **agrupados por tipo, em ordem ascendente** (todo 0000, depois todo 0150, …) |
| Exceção à ordem | **0200 e 0205 são PAI-FILHO**: o 0205 vem logo abaixo do seu 0200 |
| Início da linha | coluna 1, tamanho variável |
| Separador | `|` entre campos |
| **Pipe nas pontas** | **não há `|` no início da linha**, salvo se o 1º campo estiver vazio; `|` antes do CRLF só se o último campo estiver vazio |
| Fim de linha | **CRLF** (13, 10) em todas as linhas |
| Campos | todos presentes, na ordem do leiaute, mesmo vazios (vazio = `||`) |

> ⚠ **Diferente da EFD.** A EFD começa e termina a linha com `|`; o exemplo do
> manual não (`5550|José Silva & Irmãos Ltda|60001556000257|01238578455`).
> Conferir contra um CAT5 real da BOA (`CAT5_SP_<CNPJ>_<M>_<AAAA>.txt`) antes
> de gerar — o Pós-Validador é o juiz.

### Formato dos campos

| Tipo | Conteúdo |
|---|---|
| **C** alfanumérico | qualquer caractere ASCII exceto `|` e os não imprimíveis (0–31); até 255, salvo indicação |
| **N** numérico | algarismos, `-` e `,` |

**Números com decimais:** sem separador de milhar, sem `%`, vírgula decimal;
respeitar as casas do registro. `1.255,42` → `|1255,42|`; `10.000,00` →
`|10000|` ou `|10000,00|`; `0,00` → `|0|` ou `|0,00|`; `18,50 %` → `|18,5|`.

**Data** `ddmmaaaa` (`01012005`); **período** `mmaaaa` (`012005`);
**exercício** `aaaa`.

**Identificadores numéricos** (CNPJ, CPF, COD_MUN): todos os dígitos, com zeros
à esquerda, sem máscara. Tamanho com `*` é **exato**.

**Identificadores alfanuméricos** (IE, IM): sem máscara, zeros à esquerda quando
o órgão exige. **Série/subsérie/ECF**: sem máscara (`U-2` → `U2`; caixa `003`
→ `3`). **Números de processo/arrecadação/arquivamento**: mantêm a formatação.
**Código alfanumérico** (COD_ITEM): a formatação faz parte do código. **Código
numérico**: só algarismos (`1.001` → `1001`).

### Coluna "tam" e "dec" do leiaute

| Indicação | Significado |
|---|---|
| `N` com número | tamanho; com `*`, exato |
| `N` com `-` | sem máximo |
| `C` com número | tamanho exato (caso geral) |
| `C` com `-` | até 255 |
| `dec` com número | **exatamente** essas casas decimais |
| `dec` com `-` | inteiro, sem casas |

---

## 2. Tabelas

### Código de enquadramento legal (COD_LEGAL)

| Código | Hipótese |
|---|---|
| 0 | Não enseja ressarcimento nem complemento |
| 1 | Ressarcimento **ou complemento** — art. 269, I, RICMS (consumidor final) |
| 2 | Ressarcimento — art. 269, II (fato gerador presumido não realizado) |
| 3 | Ressarcimento — art. 269, III (saída subsequente com isenção ou não incidência) |
| 4 | Ressarcimento — art. 269, IV (outro estado) |

### Versão do leiaute (COD_VER)

| Código | Versão | Obrigatório |
|---|---|---|
| `01` | 1.0.0 | a partir de 01/01/2018 |

### Finalidade (COD_FIN)

| Código | Descrição |
|---|---|
| `00` | remessa regular |
| `01` | requerido por intimação específica |
| `02` | substituição de arquivo remetido antes |

---

## 3. Composição e ordem

| Registro | Nome | Obrig. | Quantos |
|---|---|---|---|
| 0000 | Abertura e identificação do contribuinte | O | um |
| 0150 | Participantes | O | vários |
| 0200 | Identificação do item | O | vários |
| 0205 | Código anterior do item | OC — **só quem não é obrigado ao SPED** | vários |
| 1050 | Saldos | O | vários |
| 1100 | Documento fiscal **eletrônico** | OC | vários |
| 1200 | Documento fiscal **não eletrônico** | OC | vários |

`O` = sempre; `OC` = obrigatório quando a condição ocorre.

---

## 4. Registros, campo a campo

### 0000 — abertura (um por arquivo)

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `0000` | C | 004 | - | O |
| 02 | PERIODO | período das informações (`mmaaaa`) | N | 006 | - | O |
| 03 | NOME | nome empresarial | C | - | - | O |
| 04 | CNPJ | CNPJ da entidade — **DV conferido** | N | 014* | - | O |
| 05 | IE | inscrição estadual — **DV conferido pela UF** | C | 014 | - | O |
| 06 | COD_MUN | município (IBGE, 7 dígitos) | N | 007* | - | O |
| 07 | COD_VER | versão do leiaute (`01`) | N | 02 | - | O |
| 08 | COD_FIN | finalidade (`00`/`01`/`02`) | N | 02 | - | O |

Consequência: **um arquivo por estabelecimento (CNPJ + IE) e por período mensal**.

### 0150 — participantes

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `0150` | C | 004 | - | O |
| 02 | COD_PART | código do participante no arquivo | C | 060 | - | O |
| 03 | NOME | nome pessoal ou empresarial | C | - | - | O |
| 04 | COD_PAIS | país (item 3.2.1 do Ato COTEPE 09/2008) | N | 005 | - | OC |
| 05 | CNPJ | CNPJ | N | 014* | - | OC |
| 06 | CPF | CPF | N | 011* | - | OC |
| 07 | IE | inscrição estadual | C | 014 | - | OC |
| 08 | COD_MUN | município IBGE | N | 007* | - | OC |

- Pessoas das transações do período, **inclusive o próprio estabelecimento**;
  sem movimento no período, não entra.
- COD_PART de livre atribuição, **único no arquivo**, e tem de aparecer em outro
  registro; de preferência estável entre períodos.
- Dados do **último evento fiscal** do período.
- **Não informar** CNPJ/CPF só citados em documentos modelo **02, 2D, 59, 60 e 65**.
- COD_PAIS informado também para o Brasil (`01058` ou `1058`).
- CNPJ e CPF mutuamente exclusivos; um deles obrigatório no Brasil; DV conferido.
- IE validada pela UF dos dois primeiros dígitos do COD_MUN.
- COD_MUN obrigatório no Brasil; vazio no exterior.

### 0200 — item (**8 campos, não os 13 da EFD**)

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `0200` | C | 004 | - | O |
| 02 | COD_ITEM | código do item | C | 060 | - | O |
| 03 | DESCR_ITEM | descrição | C | - | - | O |
| 04 | COD_BARRA | GTIN-8/12/13/14 | C | - | - | OC |
| 05 | UNID_INV | **unidade de estoque** | C | 006 | - | O |
| 06 | COD_NCM | NCM | C | 008 | - | O |
| 07 | ALIQ_ICMS | alíquota da saída interna | N | - | **02** | OC |
| 08 | CEST | CEST | N | 007* | - | OC |

- Mesmo código em todo documento, lançamento e arquivo; não duplica, não se
  reutiliza; mercadoria que muda de característica ganha código novo.
- **COD_ITEM e UNID_INV têm de ser os do Registro de Inventário (bloco H)**.
- Só itens referenciados nos outros registros; **um 0200 por código**.
- Informações da **última ocorrência do período**.
- Descrição genérica é vedada; pode mudar sem descaracterizar (vale a atual).
- COD_BARRA vazio só se o produto não tiver código.

### 0205 — código anterior (só não obrigados ao SPED)

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `0205` | C | 004 | - | O |
| 02 | COD_ITEM | código alterado no 0200 | C | - | - | O |
| 03 | COD_ANT_ITEM | código anterior | C | - | - | O |
| 04 | DESCR_ANT_ITEM | descrição anterior | C | - | - | OC |

Contribuinte que escritura EFD (o caso do Amigão e da BOA) **não usa o 0205**.

### 1050 — saldos

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `1050` | N¹ | 002¹ | - | O |
| 02 | COD_ITEM | código do 0200 | C | 060 | - | O |
| 03 | QTD_INI | quantidade no início do 1º dia do período | N | - | **3** | O |
| 04 | ICMS_TOT_INI | ICMS suportado acumulado do item no início do 1º dia | N | - | **2** | O |
| 05 | QTD_FIM | quantidade no fim do último dia | N | - | **3** | O |
| 06 | ICMS_TOT_FIM | ICMS suportado acumulado no **fim do último dia**² | N | - | **2** | O |

¹ ² ver erratas (seção 6). É o **saldo em quantidade e em valor da Ficha 3**,
abertura e fechamento do período.

### 1100 — documento fiscal eletrônico

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `1100` | N¹ | 002¹ | - | O |
| 02 | CHV_DOC | chave do documento eletrônico | N | 044* | - | O |
| 03 | DATA | data da entrada ou da saída | N | 008* | - | O |
| 04 | NUM_ITEM | nº sequencial do item no documento | N | 003 | - | O |
| 05 | IND_OPER | `0` entrada, `1` saída | N | 001 | - | O |
| 06 | COD_ITEM | código do 0200 | C | 060 | - | O |
| 07 | CFOP | CFOP **sob o enfoque do declarante** | N | 004* | - | O |
| 08 | QTD | quantidade **na unidade do 0200** | N | - | **3** | O |
| 09 | ICMS_TOT | ICMS suportado, só nas entradas | N | - | **2** | OC |
| 10 | VL_CONFR | valor de confronto, só nas saídas com COD_LEGAL > 0 | N | - | **2** | OC |
| 11 | COD_LEGAL | enquadramento legal, nas saídas | N | 001 | - | OC |

- **Só mercadoria sujeita a ST**, com documento eletrônico (NF-e, NFC-e, CF-e SAT).
- ICMS_TOT = base de cálculo da sujeição passiva por ST × alíquota da saída
  interna ao consumidor final.
- VL_CONFR quando COD_LEGAL > 0.

### 1200 — documento fiscal não eletrônico (**ordem dos campos diferente do 1100**)

| Nº | Campo | Descrição | Tipo | Tam | Dec | Obrig |
|---|---|---|---|---|---|---|
| 01 | REG | `1200` | N¹ | 002¹ | - | O |
| 02 | COD_PART | participante do 0150 | C | 060 | - | OC |
| 03 | COD_MOD | modelo (Tabela 4.1.1 do SPED) | C | 002 | - | O |
| 04 | ECF_FAB | nº de série de fabricação do ECF | C | 021 | - | OC |
| 05 | SER | série | C | 003 | - | OC |
| 06 | NUM_DOC | número do documento | N | 009 | - | O |
| 07 | NUM_ITEM | nº sequencial do item | N | 003 | - | O |
| 08 | IND_OPER | `0` entrada, `1` saída | N | 001 | - | O |
| 09 | DATA | data da entrada ou da saída | N | 008 | - | O |
| 10 | CFOP | CFOP | N | 004* | - | O |
| 11 | COD_ITEM | código do 0200 | C | 060 | - | O |
| 12 | QTD | quantidade na unidade do 0200 | N | - | **3** | O |
| 13 | ICMS_TOT | ICMS suportado, só entradas | N | - | **2** | OC |
| 14 | VL_CONFR | valor de confronto, saídas com COD_LEGAL > 0 | N | - | **2** | OC |
| 15 | COD_LEGAL | enquadramento legal | N | 001 | - | OC |

No 1100 é COD_ITEM (06) antes do CFOP (07); no 1200 é **CFOP (10) antes do
COD_ITEM (11)**. ECF_FAB só em documento emitido por ECF.

---

## 5. Regras de conteúdo que decidem o arquivo

### Quais campos cada natureza de operação preenche

| Natureza | ICMS_TOT | VL_CONFR | COD_LEGAL | CFOP de exemplo |
|---|---|---|---|---|
| **Entrada** | obrigatório | não pode | não pode | 1.403/2.403, 1.409/2.409 |
| **Devolução de entrada** | obrigatório, **o da entrada original** | não pode | não pode | 5.411/6.411 |
| **Saída** | não pode | obrigatório se COD_LEGAL 1–4; não pode se 0 | obrigatório | 5.405/6.404, 5.409/6.409, 6.102/6.108, 6.152 |
| **Devolução de saída** | obrigatório, **o da saída original** | obrigatório se o COD_LEGAL **da saída original** for 1–4; não pode se 0 | obrigatório | 1.411/2.411 |

### O que é o VL_CONFR

| Coluna da Ficha 3 | Enquadramento | VL_CONFR |
|---|---|---|
| **20** | **1** (consumidor ou usuário final) e **3** (saída subsequente com isenção ou não incidência) | **alíquota interna da mercadoria × base de cálculo da operação de saída** |
| **21** | **2 e 4** | **ICMS da operação própria do substituto** de quem a mercadoria foi recebida diretamente; ou o cobrado na operação interestadual anterior (antecipação); ou o ICMS que caberia à operação própria do substituído de quem se recebeu, se estivesse no regime comum. Observar o art. 271 do RICMS |

### Devoluções (item 3.3.6 do manual do sistema)

- **Devolução de saída** é entrada que anula a saída: ICMS_TOT e VL_CONFR
  **conforme a saída original** (VL_CONFR só se o COD_LEGAL original > 0) e a
  quantidade.
- **Devolução de entrada** é saída que anula a entrada: ICMS_TOT **conforme a
  entrada original** e a quantidade.
- **Sem sinal negativo no arquivo** — quantidade e valores de 1100 e 1200 vão
  positivos; o **Pós-Validador** põe o sinal ao compor a Ficha 3.

### Fato gerador presumido não realizado (art. 269, II)

- **Um registro por mercadoria** no período, com quantidades e valores
  **englobados**.
- Quando **não houver emissão de documento** (§ 3º do art. 3º da Portaria CAT
  158/15): CHV = `0`, DATA = **último dia do período**, NUM_ITEM = `999`.
- IND_OPER **sempre `1`**; CFOP **sempre `5001`**; ICMS_TOT **vazio**.

---

## 6. Erratas e ambiguidades do manual 1.50

| Onde | O que diz | O que vale |
|---|---|---|
| 1050, 1100, 1200 — REG | tipo N, tamanho 002 | o texto fixo tem 4 caracteres (`1050`); tratar como os outros REG (C 004) |
| 1050 campo 06, tabela | "ICMS_TOT_FIM … no início do primeiro dia" | a observação diz "no final do último dia do período" — vale a observação |
| 1100, observações dos campos 3, 7 e 8 | campo 3 DATA "informe o número do item"; campo 7 = QTD; campo 8 = CFOP | a **tabela** (07 CFOP, 08 QTD) é o que os arquivos reais da BOA seguem |
| 1200, observação do campo 9 | DATA "informe o número do item" | é a data da entrada ou da saída |
| 1200, observação do campo 5 | "série do Documento Fiscal Eletrônico" | o 1200 é de documento **não** eletrônico |
| Exemplo de valor | `$ 1.129.998,99 → |1129989,99|` | erro de digitação; é `1129998,99` |
| Fato gerador não realizado | CFOP "sempre 5001" | o manual do sistema manda baixar por CFOP 5.927 com enquadramento 2; o 5001 é o caso **sem documento**. Confirmar com o Pós-Validador antes de gerar |

---

## 7. O que a etapa 7 herda do sistema de hoje

Cruzado com o estado das etapas 1 a 5 em 15/09/2026.

1. **Um arquivo por estabelecimento de SP e por mês.** O 0000 leva CNPJ, IE
   com DV e PERIODO `mmaaaa`. As fichas de loja fora de SP (o piloto do Amigão
   é PR e MS) não geram arquivo.
2. **O 1100 exige chave e número do item de cada documento.** A venda de PDV
   do relatório do cliente vem **consolidada por item e dia, sem chave** — não
   preenche 1100. O cupom (NFC-e, CF-e SAT) precisa vir do **XML**, que é a
   fonte que vence (decisão "os dois", 15/09/2026). Sem o XML, a Ficha 3 pode
   ser calculada, mas o arquivo digital não fecha.
3. **Devolução de saída carrega o COD_LEGAL e o VL_CONFR da saída original.**
   O razão hoje lança a devolução de venda sem enquadramento. A etapa 7 precisa
   amarrar a devolução à venda (chave referenciada na nota de devolução).
4. **VL_CONFR dos enquadramentos 2 e 4** é o ICMS da operação própria da
   entrada (coluna 21) — é o "confronto pendente" do razão.
5. **1050 é o saldo em valor da Ficha 3.** A abertura sem ICMS suportado
   (inventário do cliente sem imposto) sai direto no ICMS_TOT_INI; resolver o
   item 3.3.8 antes.
6. **QTD na unidade do 0200 (UNID_INV)**, com 3 casas — a conversão do 0220 já
   deixa a ficha nessa unidade. **0200 do arquivo tem 8 campos**, e o COD_ITEM e
   a UNID_INV têm de ser os do bloco H.
7. **Só mercadoria com ST** em 1100/1200, e só itens referenciados no 0200 —
   bate com o critério do razão (saída com CST 60).
8. **Valores: 2 casas; quantidades: 3 casas; vírgula decimal; sem sinal.** O
   razão guarda 15 casas no saldo: arredondar só na escrita.
9. **0150** com o próprio estabelecimento e só participantes com movimento,
   **sem** os de documentos 02, 2D, 59, 60 e 65. O relatório do cliente dá
   código de participante, não 0150 completo — o 0150 da EFD serve.
10. **Conferir o pipe no início da linha** contra um CAT5 real da BOA antes de
    escrever o gerador (seção 1).
