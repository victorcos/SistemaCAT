# De-para: quatro reforços vindos do README do CRM Fiscal

Pedido do usuário, 09/11/2026. Prioridade fechada por ele: na ordem abaixo, sem
mudar. É da frente de ICMS (`frente/icms`); regra de convivência em
`docs/TRABALHO_EM_PARALELO.md`.

Ficou decidido também **o que NÃO entra**:
- aprovação gravada de tudo: o "GTIN/sufixo valem sozinhos" continua;
- trocar a semelhança de palavras por `pg_trgm`/embeddings;
- histórico por CNPJ do fornecedor + `cProd`;
- nota não escriturada como entrada da Ficha 3 (decisão de 16/09/2026 mantida).
  O XML dela pode servir de **prova** para o de-para (GTIN, descrição), nunca
  de quantidade na ficha.

Tudo o que é regra vai em `cat/dominio/depara/candidatos.py` (domínio puro,
testável sem arquivo); a leitura dos dados, em `infraestrutura/analitico/depara.py`.

---

## MEDIÇÃO NO EMPRESA 29 (09/11/2026) — muda ① e ④, ler antes de tudo

Medido sem gravar nada no projeto 29 (CAT 42 4T2021, movimentos da execução
215: 73 estabelecimentos, 1,04 milhão de códigos, 1.661 pares propostos). Os
scripts e o CSV de cada par estão na mesma pasta desta especificação
(`medir_depara.py`, `medir_custo_v2.py`, `depara_medicao.csv (fora do repo: tem CNPJ)`).

**O problema é maior que o previsto: o GTIN está juntando produtos diferentes.**
- 266 pares valem sozinhos hoje, e **nenhuma decisão está gravada** para a
  empresa: os 266 entram no razão em silêncio;
- **157 dos 260 pares de GTIN (60%) ligam códigos com NCM diferente**, 105 deles
  de **capítulo** diferente (2 primeiros dígitos). Só 4 casos são o NCM genérico
  `11111111`. Os GTINs são válidos e reais (`7896232115673` em 12 pares):
  é cadastro do cliente com GTIN de outro produto, o mesmo defeito do caso
  GRECIN, em escala;
- extremos: custo 124× (NCM genérico × tecido), 23× (bebida × preparação),
  18× (cofre 8303 × empilhadeira 8427);
- dos 266 que valem sozinhos, **143 têm NCM de capítulo diferente ou CEST
  diferente**; 117 passam por todas as travas.

**Correções nesta especificação por causa da medição:**
1. **① A conta muda.** Cerca de 80% das saídas em nota da empresa 29 são
   **transferência** (5152, 5409, 6152, 6409), que sai a preço de custo; a venda
   de varejo é cupom. Com o preço de todas as saídas, a mediana dos pares de GTIN
   deu 1,01 e a faixa 0,30–1,20 derrubaria 100 de 266 por motivo errado. Usar:
   - **primeiro custo × custo**: `(custo_origem ÷ fator) ÷ custo_destino`, com o
     custo das entradas dos dois lados, faixa `FAIXA_DE_CUSTO = (0.50, 2.00)`;
   - **sem entrada no destino**, o preço só de **vendas**: excluir as
     transferências (`x152 x409 x151 x408 x155 x156 x552 x557`), faixa 0,30–1,20;
   - medido assim: 83 dos 266 incoerentes, e **71 desses 83 também têm NCM
     diferente** — duas provas independentes.
2. **④ deixa de ser só alerta.** NCM de **capítulo diferente** num par de GTIN
   ou sufixo **tira o par do `vale_sozinho`** e manda para revisão (105 pares no
   empresa 29). NCM diferente no mesmo capítulo continua só alerta.
3. **② não foi medido:** o empresa 29 não tem 0220 (`conversoes.parquet` vazio).
   Medir na JK ou na Advertising antes de integrar.
4. **③ confirmado:** 70 dos 266 que valem sozinhos têm CEST diferente.

**Antes de integrar, rodar o razão da empresa 29 de novo** e comparar o ressarcimento
antes/depois: pares errados de GTIN juntaram fichas de produtos diferentes.

---

## SEGUNDA MEDIÇÃO (10/11/2026) — gabarito e regras ⑥–⑩ · muda a recomendação

Mesmo trabalho, mesmos 266 pares que valem sozinhos. Desta vez com **gabarito**:
cada par rotulado pela leitura das duas descrições (S = mesmo produto, D =
diferente, I = não dá para dizer). Resultado: **90 S, 124 D, 52 I**. O
percentual de acerto é calculado sobre os 214 rotulados: dos pares que
continuariam valendo sozinhos, quantos são de fato o mesmo produto. O
componente de cesta de Natal com mesmo tipo e tamanho do produto de marca
conta como S. O rótulo é de uma pessoa, numa empresa só: serve para comparar
as regras entre si, não como taxa garantida.
Scripts: `medir_reforcos_v3.py`, `gabarito266.py`, `combos266.py`.

**Regras novas medidas:**
- ⑥ **GTIN contaminado:** o GTIN do par está, no mesmo CNPJ, em códigos de
  dois ou mais capítulos de NCM (fora o genérico `11111111`);
- ⑦ **os dois convivem:** origem e destino têm saída (ou entrada) em 3 ou mais
  semanas em comum. Troca de código não convive, dois produtos convivem;
- ⑧ **gramatura diverge:** o peso ou volume da descrição (`500G`, `1,5L`,
  `900ML`) é diferente dos dois lados e a razão não bate com o fator;
- trava de **sufixo:** par de sufixo sem nenhuma palavra em comum na descrição;
- ⑨ unidade, ⑩ XML do fornecedor e a higiene do GTIN **não pegaram nada** nesta
  base: o 0200 é quase todo em CX, o GTIN dos dois lados veio do próprio XML e
  o `gtin_valido` já descarta os inválidos. Ficam fora por ora.

**Percentual de acerto (dos que continuam valendo sozinhos):**

| Metodologia | Aceitos | Acerto | Erros barrados | Certos barrados |
|---|---:|---:|---:|---:|
| Atual (sem trava) | 214 | **42,1%** | 0 de 124 | 0 de 90 |
| Cinco reforços (①③④) | 65 | **60,0%** | 98 | 51 |
| ⑥⑦⑧ | 91 | **84,6%** | 110 | 13 |
| **⑥⑦⑧ + trava de sufixo** | 88 | **87,5%** | 113 | 13 |
| ① + ⑥⑦⑧ + sufixo | 77 | 88,3% | 115 | 22 |
| Tudo (①③④⑥⑦⑧ + sufixo) | 39 | 82,1% | 117 | 58 |

**Precisão de cada regra** (de tudo o que ela barra, quanto era erro mesmo):
⑧ gramatura 96,4% · ⑦ convivência 93,5% · ⑥ GTIN contaminado 87,3% ·
① custo 82,9% · ③ CEST 79,7% · ④ NCM de capítulo 70,8%.

**O que muda:**
1. **④ volta a ser só alerta.** Ele barrou 28 pares certos: as gavetas de
   dinheiro, cadastradas com NCM 8427 (empilhadeira) num lado. O produto era o
   mesmo e o NCM estava errado. É justamente o caso que a frente de PIS/COFINS
   quer receber (contrato `divergencias_de_ncm`), não um motivo para separar.
   O "cofre × empilhadeira" da primeira medição era esse caso.
2. **⑥⑦⑧ e a trava de sufixo é que tiram o par do `vale_sozinho`**, com o motivo
   escrito. Ganho: o acerto vai de 42% para 87,5%, contra 60% dos cinco
   reforços, e barra só 13 pares certos em vez de 51.
3. **① e ③ viram selo na tela de revisão, sem barrar.** Somar o ① ganha menos
   de 1 ponto de acerto e barra 9 pares certos a mais. Continua valendo para kit
   e descrição, como estava no ①.
4. **O que ainda passa (11 erros):** variação de **sabor ou versão** com mesma
   marca e tamanho (Red Horse Maçã Verde × Cramberry, Vodka Kislla Big Apple ×
   Maracujá, Molho Alho × Pimenta, Bala Mastigável × Goma) e marca diferente
   com o mesmo GTIN (Óleo Concórdia × Vitaliv). Candidato a regra ⑪: mesma
   marca e tamanho, mas a palavra final diferente → revisão. Medir antes de
   incluir.

---

## TERCEIRA MEDIÇÃO (10/11/2026) — segunda base e calibragem · REGRA FINAL

Segunda base: execução 227, um estabelecimento de material de construção,
8.294 códigos, **2.842 pares valendo sozinhos**. Amostra aleatória de 150
pares (semente 42), rotulada como antes: 19 S, 124 D, 7 I. **O atual acerta
13,3%.** Quase todo o erro vem de **sufixo**: os pares `sufixo` e
`gtin+sufixo` ligam joelho de PVC a argamassa, tinta spray a pilha. O par é
proposto contra a raiz do grupo, e o grupo foi formado por uma corrente de
sufixos. Scripts: `avaliar_bases.py`, `final_bases.py`.

**Achados:**
- a trava de sufixo da segunda medição (só no motivo `sufixo` puro, sem
  nenhuma palavra em comum) **não basta**. Ela tem que valer para todo par com
  sufixo no motivo, inclusive `gtin+sufixo`, e com **semelhança de palavras ≤
  0,2** (Jaccard das palavras de 3+ letras). Assim ela barrou 118 erros e
  nenhum certo na 227, e 6 erros e nenhum certo na empresa 29;
- ⑦ com **2 semanas** é melhor que com 3 nas duas bases;
- ⑧ com tolerância de **10%** recupera 3 pares certos na empresa 29 ("430 g ×
  450 g" da cesta), sem soltar erro;
- ⑪ (sabor/versão) **fica de fora**: na empresa 29 barra 17 certos para pegar
  10 errados e na 227 barra 2 certos e nenhum errado;
- ① custo barra 47 erros e nenhum certo na 227. Volta a barrar o `vale_sozinho`;
- ③ CEST e ④ NCM de capítulo seguem como alerta: somar o ③ só tira certos.

**Percentual de acerto (dos que continuam valendo sozinhos):**

| Metodologia | Empresa 29 | Execução 227 |
|---|---:|---:|
| Atual | 42,1% | 13,3% |
| Cinco reforços (①③④) | 60,0% | 19,3% |
| ⑥⑦⑧ + sufixo (2ª medição) | 87,5% | 24,4% |
| ⑥⑦⑧ + sufixo ≤ 0,2 em todo par de sufixo | 87,5% | 79,2% |
| **Regra final: ① + ⑥ + ⑦(2 sem.) + ⑧(10%) + sufixo ≤ 0,2** | **89,5%** | **90,5%** |

Na regra final ficam barrados, para revisão, 22 dos 90 certos na empresa 29 e
0 dos 19 na 227. Sem o ①, o acerto é 89,7% e 82,6%, com 12 e 0 certos
barrados. A escolha pelo ① é porque um erro aceito vai calado para a ficha, e
um certo barrado só custa um clique de revisão.

**Regra final para implementar** (tira do `vale_sozinho` e manda à revisão com
o motivo escrito):
1. sufixo no motivo e semelhança das descrições ≤ 0,2;
2. ⑥ GTIN contaminado (o mesmo GTIN em códigos de 2+ capítulos de NCM no CNPJ);
3. ⑦ origem e destino com saída ou entrada em 2+ semanas em comum;
4. ⑧ peso/volume da descrição diferente além de 10%, descontado o fator;
5. ① custo incoerente (custo × custo 0,5–2,0; sem entrada no destino, preço de
   venda sem transferência 0,3–1,2).

Viram selo, sem barrar: ③ CEST diferente, ④ NCM de capítulo diferente (com o
contrato `divergencias_de_ncm` para PIS/COFINS). Ficam de fora: ⑨ unidade,
⑩ XML do fornecedor, higiene do GTIN e ⑪ sabor/versão.

Limite das medições: 364 pares rotulados por uma pessoa, em duas empresas. A
regra de sufixo merece um teste de unidade com a corrente
("joelho → argamassa") que a 227 mostrou.

---

## ① Teste de sanidade de custo (o mais importante)

**Problema:** nada confere se o **fator** faz sentido. Kit de 3 gravado como 12
erra a quantidade da ficha e o ressarcimento, sem aviso.

**Dados:** já estão em `movimentos.parquet` (`valor`, `desconto`, `quantidade`,
`operacao`, `cfop`, `codigo`, `cnpj`). Nada novo a extrair.

**Conta, por par `origem → destino` com `fator`:**
- `custo_origem` = Σ(valor − desconto) ÷ Σ quantidade das **entradas** da origem
  (sem devolução: `CFOP_DEVOLUCAO` de `enquadramento.py`);
- `preco_destino` = Σ valor ÷ Σ quantidade das **saídas** do destino (sem devolução);
- `razao = (custo_origem ÷ fator) ÷ preco_destino`.

**Leitura:**
- `FAIXA_DE_CUSTO = (0.30, 1.20)`, parametrizável: o custo de uma unidade do
  destino entre 30% e 120% do preço de venda dela;
- dentro → "custo coerente (custo 0,62 do preço)";
- fora → "custo incoerente: custo 3,9× o preço — confira o fator";
- sem entrada na origem ou sem saída no destino → "sem preço para conferir".
  **Não bloqueia nem rebaixa**: falta de dado não é prova contra.
- Quando o **destino também tem entradas**, mostrar o fator que o custo sugere:
  `custo_origem ÷ custo_destino`. Arredondado, ele é a melhor pista para o kit.

**Efeito:**
- `vale_sozinho` ganha a quinta exigência: custo **não** incoerente. Par de GTIN
  com custo incoerente vai para revisão, com o motivo escrito;
- kit e descrição incoerentes caem para confiança `media`, com o número na
  explicação;
- a tela de revisão mostra o selo (coerente / incoerente / sem preço).

**Testes:** kit 3 certo (coerente); kit gravado como 12 (incoerente); GTIN fator 1
com custo 5× o preço (sai do `vale_sozinho`); origem sem entrada (sem preço, não
rebaixa).

## ② 0220 como prova do fator do kit

**Dados:** `conversoes.parquet` na pasta de movimentos (cada 0220 amarrado ao 0200).

**Regra:** para o par de **kit**, procurar o 0220 do código do kit:
- fator do 0220 = fator do kit → motivo extra "0220 confirma o fator 3",
  confiança `alta`. **Continua esperando aprovação**: kit nunca vale sozinho;
- fator do 0220 ≠ fator do kit → confiança `media`, com o conflito escrito
  ("o kit diz 3, o 0220 diz 6");
- sem 0220 → nada muda.

**Testes:** 0220 confirma; 0220 contradiz; sem 0220.

## ③ CEST como trava

Na ST o CEST define o segmento: CEST diferente quase nunca é o mesmo produto.

**Dados:** `cest` (0200) e `cest_xml` em `movimentos.parquet`. Levar para
`ItemParaCasar` (`cests`, como já se faz com `gtins`), descartando vazio.

**Regra (penalidade, não filtro: o CEST costuma vir vazio ou errado):**
- par por **descrição** com CEST dos dois lados e diferente → **não propor**;
- par por **GTIN ou sufixo** com CEST diferente → sai do `vale_sozinho` e vai
  à revisão, com "CEST 03.001.00 × 17.046.00";
- em `ordenar_candidatos`: CEST igual `+15`; CEST diferente `−40`, com o porquê.

**Testes:** descrição com CEST diferente (some); GTIN com CEST diferente
(revisão); um lado sem CEST (nada muda).

## ④ Alerta de NCM divergente (consumido pela frente de PIS/COFINS)

Quando o par junta dois códigos com **NCM diferente** (8 dígitos), um dos
cadastros está errado. Para o ICMS é só um aviso; para o reenquadramento de
PIS/COFINS é um achado.

**No de-para (ICMS):**
- marcar o par com `ncm_divergente` e os dois NCMs; aviso na tela de revisão;
- **não muda confiança nem `vale_sozinho`**: mesmo produto com NCM errado num
  cadastro continua sendo o mesmo produto.

**Contrato para a frente de PIS/COFINS** (anotar em `docs/CONTRATOS.md` §16 —
é mudança compartilhada, commit próprio):
- uma planilha/consulta `divergencias_de_ncm` por trabalho, com: `cnpj`,
  `codigo_origem`, `descricao_origem`, `ncm_origem`, `codigo_destino`,
  `descricao_destino`, `ncm_destino`, `motivo_do_par`, `situacao` (proposto /
  aprovado / recusado / vale sozinho);
- só pares **aprovados ou que valem sozinhos**: par recusado não é prova de
  nada.

A frente de PIS/COFINS lê esse contrato depois; não precisa esperar por ela.

## ⑤ NCM de 4 dígitos (ajuste de peso, pequeno)

Em `ordenar_candidatos`: mesmos 4 primeiros dígitos e NCM diferente → `+10`,
"mesma posição do NCM". Não elimina ninguém.

---

## Fechamento

- Registrar em `docs/DECISOES.md`: os quatro reforços, as faixas escolhidas e o
  que ficou de fora (lista no topo).
- Medir num trabalho real antes de integrar: quantos pares mudaram de situação
  por ① e ③. Se ① rebaixar muito GTIN, a faixa está apertada demais.
- Integrar com `bash scripts/integrar.sh minor`.
