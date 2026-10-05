# PLANEJAMENTO — CRM Fiscal

> O que existe, o que falta e em que ordem. Atualizado a cada entrega.
> O porquê de cada escolha fica em DECISOES.md; as rotas, em CONTRATOS.md.

---

## Onde estamos

**As oito etapas da CAT 42 estão no ar (v0.64.0), e o trabalho da empresa 19 passou
por todas** (de novo em 16/09/2026, da etapa 4 à 8, em 59 min). Desde a v0.53, a
etapa 3 lê o item do XML, o razão aplica o de-para aprovado e confronta os
enquadramentos 2 e 4 com o crédito do art. 271; na v0.54, a nota cancelada na
SEFAZ sai da movimentação, a não escriturada ganha a contingência do art. 527 e o
XML dentro de zip é lido sem extrair — correções que vieram da comparação com a
CAT 42 da empresa 04 (DECISOES). Da pasta com EFD, XML e relatórios do ERP até o pacote de entrega
com o arquivo digital pré-validado e o manifesto com SHA-256, pela tela, com
fila, cancelamento, histórico e aprovação de quem responde pelo negócio.

A API é C# (.NET 10) e o trabalho pesado é Python com DuckDB, num motor sem
rota pública (DECISOES, 13/09/2026). O front é React. Postgres guarda cadastro,
execuções e histórico; os dados de cada execução ficam em parquet no disco local.

O que o piloto deixou claro é que **o sistema calcula e a empresa 19 ainda não tem
dado para pedir**: todo o ressarcimento apurado é de lojas de MS, e as 234
competências de São Paulo saem como prévia porque o relatório de saídas que
chegou não tem as lojas paulistas (ver "Dados que faltam").


## A prioridade mudou: combustível passa a ser a atividade principal

**Decisão de 03/10/2026.** Levantar o crédito de ICMS sobre combustível deixa de
ser uma frente entre outras e passa a ser **o que o sistema faz**. A CAT 42 e as
exclusões de PIS/COFINS continuam no ar e continuam sendo mantidas, mas a ordem
de construção passa a ser definida pelo combustível.

Isso reordena o que vem abaixo, e muda o peso de três itens que pareciam
laterais:

* ~~o CNPJ na chave da seleção~~ — **feito** (v0.137.0): era o mais urgente dos
  três, porque sem ele o leitor nasceria descartando três quartos da base;
* ~~o leitor de EFD ICMS/IPI~~ — **feito**: o leiaute em v0.136.0
  (`sped/registros_icms.py`, 16 registros medidos em 40 arquivos reais) e o
  leitor das compras em v0.138.0 (`sped/combustivel.py`). Falta a **rodada** que
  o chama em ordem e grava parquet;
* ~~o classificador de produto~~ — **feito** (v0.140.0): NCM manda, descrição
  confirma, fila de revisão em 1,7% das linhas.

**E o produto não é achar crédito: é auditar o tomado.** Medido em 03/10/2026,
três dos quatro clientes com CST 61 **já creditam** — a empresa 06 por ajuste
`SP020799`, e a **empresa 21** também, com a descrição do próprio ajuste citando
os Convênios 26/2023 e 61/2023 e *"a proporcionalidade das operações
tributadas"*, que é um elemento novo: ela rateia o crédito pela parcela de
saídas tributadas. Só a empresa 09 não credita.

Isso não enfraquece o módulo; define o que ele vende. O que se acha não é um
crédito virgem, é a diferença: a empresa 06 credita `litros × ad rem` sem o FCV,
0,24% a mais, sistemático; a maioria dos meses dela sai curta; e um mês de 2024
sai 18% acima. Auditar isso exige a mesma conta que calcular do zero — mais a
leitura do `E111`, que é como se descobre o que o cliente já tomou.

---

## O roteiro no sistema

| # | Etapa | O que faz | Desde |
|---|---|---|---|
| 1 | Importar base de dados | Classifica cada arquivo do lote (EFD, XML, relatório, arquivo digital), separa o de outra empresa, lê zip sem extrair | v0.9 |
| 2 | Conferir documentos | EFD × XML × relatório do cliente: pendentes, não escrituradas e conferidas, em xlsx e CSV | v0.13 |
| 3 | Extrair movimentos | C170, C190/C850, 0200 e bloco H, cada movimento marcado pela conferência, na data de entrada/saída | v0.18 |
| 4 | Apurar o ICMS suportado | Cascata de quatro fontes com procedência; XML vence o ERP | v0.41 |
| 5 | Montar o razão dos itens | Ficha 3 por estabelecimento e mercadoria, custo médio móvel, saída sem item vinda do relatório do cliente | v0.42 |
| 6 | Apurar ressarcimento e complemento | Por estabelecimento e mês, separados, com os saldos do 1050 e o que trava cada competência | v0.45 |
| 7 | Gerar o arquivo digital | 0000 a 1200 no leiaute, pré-validação que recompõe a Ficha 3, envio só do que está limpo e prévia do resto | v0.47 |
| 8 | Relatórios e entrega | Relatório de todas as competências, dossiê só do que vai à SEFAZ, manifesto; conclui com aprovação de revisor ou gestor | v0.50 |

Fora do roteiro: **pré-validar o arquivo que o cliente já transmitiu** (v0.48),
para auditoria de quem gera a CAT 42 com outra ferramenta.

**O combustível não está nesta tabela de propósito.** O roteiro acima é o da
CAT 42, onde a ordem é real — não se monta razão sem movimentos. O crédito de
combustível é frente própria, de uma etapa só, e não depende de nenhuma delas:
lê a EFD ICMS/IPI do lote direto. Quem importou a base já tem tudo o que ela
precisa (v0.146.0).

Em volta: login com Argon2id e escopo por empresa, gestão de usuários com as
três salvaguardas, acesso às empresas, histórico do trabalho com sucessão,
cadastro do trabalho editável com aviso de base fora do período (v0.51).

---

## O que foi medido contra dado real

| O quê | Contra | Resultado |
|---|---|---|
| Fórmula do ressarcimento | Ficha 3 da empresa 17 e da empresa 20, 706 milhões de linhas | 99,63% das linhas; o resto, 1 centavo de arredondamento |
| Razão do item | Ficha 3 da empresa 17, uma filial e um mês | 550.862 linhas, 100% em saldo e ressarcimento, R$ 0,00 de diferença |
| ICMS suportado | Book da empresa 08 | ICMS + ST + FECOP em 100% de 1.242.621 linhas |
| Leiaute do arquivo digital | 7 arquivos que a SEFAZ aceitou da empresa 17 (2021 a 2024) | registro a registro; nenhum erro de pré-validação nos aceitos |
| Pré-validação | Arquivos da empresa 17 | recompõe 100% das quantidades e 99,99% dos valores a 5 centavos |
| Leitura da EFD | 7.036 EFD reais, seis versões de leiaute | sem falha |
| Conferência | 37,9 milhões de documentos da empresa 19 | três listas, validada também com relatório do cliente simulado |
| Consulta de Saídas (047) | Gabarito do MA: 7.784.121 linhas, 57 competências | as 53 colunas iguais em 100% das linhas |
| Consulta de Entradas (037) | Gabarito do MA: 458.792 linhas, 57 competências | as 52 colunas iguais em 100% das linhas |

---

## O que vem pela frente

Em ordem de prioridade. Cada item entra com decisão registrada em DECISOES.md.

### 1. Fechar o piloto da empresa 19

- [ ] **Aprovar a entrega.** Só revisor ou gestor aprova; o dev não conta como
      responsável pelo negócio. Depende do Pedro, do Rafael ou do Vinícius.
- [ ] **Dados que faltam**, a pedir ao cliente:
  - relatório de saídas (ou XML dos cupons) das 22 lojas de São Paulo — sem ele
    o pedido paulista é zero por falta de dado, não de direito;
  - EFD de antes de 01/2021, para valorar a abertura pelas entradas anteriores
    (item 3.3.8 do manual); hoje 400 mil fichas abrem sem ICMS;
  - os arquivos de 2023 em diante que o OneDrive não baixou.

### 2. Comparação com a CAT 42 da empresa 04 (16/09/2026)

- [x] Item do XML na etapa 3, com consumidor final pelo `indFinal` (v0.53)
- [x] De-para: propostas por GTIN, sufixo, kit e descrição; revisão na tela;
      planilha para o cliente; aplicado no razão (v0.53)
- [x] Confronto dos enquadramentos 2 e 4 e crédito do art. 271 (v0.53)
- [x] X.949 fora da ficha, contada (v0.53)
- [x] Nota de entrada não escriturada **não** entra na ficha: a RVZ incluiu a
      pedido do cliente, não é regra (decisão do Victor, 16/09/2026)
- [x] Notas canceladas na SEFAZ e ativas no SPED/XML: evento de cancelamento e
      lista de chaves no lote, fora da movimentação e contadas (v0.54.0)
- [x] Contingência das notas não escrituradas: multa do art. 527, sem SELIC,
      nota a nota na etapa 3 (v0.54.0)
- [x] XML dentro de zip no lote, com um nível de zip dentro de zip, sem extrair (v0.54.0)
- [x] Reimportar a pasta atualiza o tipo do arquivo já no trabalho; nota denegada
      (cStat fora de 100/150) sai; cópia autorizada vence a sem protocolo (v0.55.0)
- [x] Certificado digital na pasta do cliente não é aberto nem listado (v0.55.1)
- [x] Carregar a empresa 04 no sistema (trabalho 5) e comparar o de-para com a RVZ:
      44 de 44 pares, os 10 do cliente como sem par (v0.55.2)
- [x] Base da multa das não escrituradas sem valor no XML: a da nota vizinha do
      mesmo produto (decisão do Victor, v0.55.3)
- [x] Lista de canceladas: aba de devoluções e linha de cancelamento rejeitado não
      contam (v0.55.4)
- [x] Estoque negativo abre a ficha com o que faltaria, sem ICMS suportado, em vez
      de tirá-la do total (decisão do Victor, v0.56.0)
- [x] Redução de base da entrada (CST 20/70) no ICMS efetivo do enquadramento 1,
      pela base real da nota e não pelo `pRedBC` (decisão do Victor, v0.57.0)
- [x] Alíquota da nota de entrada quando a mercadoria não tem 0200 (decisão do
      Victor, v0.58.0)
- [x] VL_ITEM da Ficha 3 é a base de cálculo do ICMS, com frete e despesas
      (achado do Victor na comparação com a RVZ, v0.60.0)
- [x] Ficha 3 no leiaute do papel de trabalho, com o cabeçalho padrão em todas
      as planilhas (pedido do Victor, v0.59.0)
- [x] Redução aplicada é a que o documento declara no `pRedBC` — 13% no Grecin,
      6% no Vagisil —, sem o redutor do Decreto 65.255/2020 (decisões do
      Victor, v0.62.0)
- [ ] **Decidir a premissa do ICMS efetivo do enquadramento 1**: o § 1º do art.
      34 exclui a saída a consumidor final, e a RC 23455/2021 exclui a cadeia da
      ST. Hoje o sistema aplica a redução (R$ 392.475,69); a alíquota cheia dá
      −R$ 110.152,30. Ver DECISOES de 18/09/2026
- [x] Correção à mão: domínio, tabela e aplicação no razão (v0.63.0)
- [x] Correção à mão: rotas da API, com o antes e o depois no histórico (v0.64.0)
- [x] Correção à mão: subir planilha editada, com o que mudou à vista antes de gravar (v0.65.0)
- [x] Acesso por segmento tributário: domínio, tabela, rotas e entrada pós-login (v0.66.0)
- [x] Leitura compartilhada entre trabalhos da mesma empresa: a inspeção reconhece
      o que já foi lido (v0.67.0)
- [ ] **Reaproveitar o material derivado**: o parquet extraído de um arquivo é
      gerado uma vez por empresa, não uma vez por trabalho. É a fatia que corta o
      tempo de indexar 119 GB duas vezes
- [x] ~~Cruzamento ICMS x PIS/COFINS para a exclusão do Tema 69~~ — **não é
      preciso cruzar**: o `VL_ICMS` do C170 da própria EFD-Contribuições sustenta
      a tese nos 138.358 itens conferidos, e é dele que o relatório do MA sai.
      Ver DECISOES de 30/09/2026 (v0.114.0)
- [x] Roteiro de etapas por módulo, e o critério do que vira tabela (v0.69.0)
- [x] Quebra de SPED: índice, cache e o join do item (v0.70.0)
- [x] Etapa `quebra_de_sped` ligada à fila, com tela e downloads (v0.75.0)
- [x] ~~Exclusão do Tema 69 **sempre pelo cruzamento** das duas EFD~~ — a previsão
      de que o campo viria em branco não se confirmou em nenhum dos 138.358 itens
      medidos, e cruzar daria números diferentes dos do relatório que o cliente
      confere. Revisto em DECISOES de 30/09/2026 (v0.114.0)
- [x] Caminho consolidado: C180/C190 com os filhos de PIS e COFINS casados (v0.71.0)
- [x] Bloco M: a apuração e os ajustes, PIS e COFINS na mesma função (v0.72.0)
- [x] Quebra da ECD: plano de contas, índice por conta e razão contábil (v0.73.0)
- [x] Consulta de Entradas (037): os oito ramos de documento de entrada (v0.74.0)
- [x] Consulta de Saídas (047): C100/C170, C100/C175, A100/A170 e F100, conferida
      linha a linha contra as 7.784.121 do gabarito do MA (v0.111.0)
- [x] A 047 na tela: recortar por competência, estabelecimento, ramo, CFOP e CST,
      paginado no servidor, com o download saindo do tamanho do recorte (v0.112.0)
- [ ] Os ramos de saída que faltam na 047 — C180/C185, C380/C385, C400/C405/C485,
      C490/C495, C600/C605, C860/C880, o bloco D, F500 a F560 e I100. Dependem de
      um cliente que os tenha **e** de um relatório de referência dele: sem os
      dois não há como saber o rótulo do ramo nem o preenchimento das colunas. A
      etapa já conta esses registros e a tela os mostra, para a ausência não ser
      silenciosa
- [x] A 037 conferida contra o gabarito do MA: cinco deduções viraram medida, o
      ramo A100/A170 entrou e a coluna `Código Serviço` também (v0.113.0)
- [ ] O par de UF da 037 quando falta uma das pontas continua sem prova: nas
      458.792 linhas do gabarito não houve um caso, então a diferença que a 047
      mostrou (coluna vazia em vez de "MG/") segue sem medida do lado da 037
- [ ] Matar os motores velhos antes de subir o novo, no script de desenvolvimento:
      no Windows dois uvicorn prendem a mesma porta **sem erro**, e quem atende é
      o mais antigo — o código novo simplesmente não entra. Já custou uma
      investigação de "não subiu a alteração" nesta casa. `/api/saude` denuncia
      (versão diferente da do arquivo `VERSAO`), mas só quem olha
- [x] Motor do **839 — ICMS-ST fora da base**: o ST presumido (base × alíquota),
      conferido 100% contra as 463.212 linhas do gabarito do MA. A regra de
      alíquota acerta 98,66%; as 556 exceções por item são dado de cliente
      (v0.116.0)
- [x] Núcleo comum das três exclusões por item (`analitico/exclusoes_por_item.py`):
      a rodada é idêntica, a conta não. Os três motores seguem separados, cada um
      conferido contra o seu gabarito (v0.118.0)
- [x] Tabela `aliquota_de_item` no banco, com carregador (`tools/carregar_aliquotas.py`)
      e as 556 exceções da empresa 05 carregadas (v0.118.0)
- [x] **Mapa de valores** (`tools/mapear_valores.py`): total por tese e por
      competência, o nosso contra o do arquivo base. Serve também sem gabarito,
      como retrato de cliente novo (v0.118.0)
- [x] A tese das contribuições corrigida pela Selic e com o filtro de receita
      das outras três: base e exclusão batem ao centavo com o 680 do MA. Sobram
      0,06% do arredondamento por grupo, que é escolha de 24/09 (v0.122.0)
- [x] Motor do **680 — as contribuições fora da própria base, item a item**
      (`sped/exclusao_piscofins_na_base.py`), 35 colunas nos quatro ramos
      (C100/C170, C100/C175, A100/A170 e F100), conferido **100,0000%** contra
      as 3.568.362 linhas do gabarito nas 57 competências, com conferidor
      próprio (`tools/validar_680.py`). Quatro regras só o dado contou: a
      ausência é do ramo e não do campo; o rateio do frete obriga a guardar o
      documento (10 linhas em 3,5 milhões); tributada basta, paga não; e o F100
      sai somado por dia. E o erro que ele pegou: registro sem CFOP entrava como
      faturamento por suposição, trazendo **aquisição** para dentro da tese — o
      sentido vem do `IND_OPER` (v0.123.0)
- [x] **Pacote das exclusões** num botão: zip com o consolidado e as quatro
      teses por item, cada uma no leiaute do seu relatório do MA, mais um
      `LEIA-ME.txt` que diz o que é cada arquivo, o que não entrou e por que as
      duas frentes da tese 1 não batem ao centavo (v0.123.0)
- [ ] Varrer as outras etapas atrás do mesmo buraco de conferência: tese
      conferida sozinha e costura nunca exercitada. O `serializar` que faltava
      nos módulos novos passou por 60 testes de exclusão e caiu na tela do
      cliente — ver DECISOES de 01/10/2026
- [x] **Levantamento do crédito de ICMS sobre combustível** (`docs/DOMINIO_COMBUSTIVEL.md`):
      os dois regimes por produto e data, as duas camadas de regra, a cascata do
      classificador (NCM manda, descrição confirma — ao contrário do crédito
      outorgado), o percentual de confiança duplo, valor nominal sem SELIC e o
      prazo de 5 anos da emissão. **O produto não é achar crédito, é auditar o
      tomado**: a empresa 06 já credita R$ 5 mi via ajuste `SP020799`, sem aplicar o
      FCV e com a maioria dos meses curta (v0.128.0)
- [x] **As três tabelas de tributação do combustível** (v0.129.0 a v0.132.0):
      `tab_ad_rem` (ad rem por competência, só o lido no convênio), `tab_fcv`
      (as 27 UFs do Ato COTEPE 64/2019) e `tab_aliquota_combustivel` (a
      percentual da era do ST, ES e SP). A última recusa de três jeitos
      distintos: `ForaDoRegimePercentual` quando a era é ad rem, `MesPartido`
      quando a alíquota muda no meio do mês (SP tem dois) e
      `AliquotaDeCombustivelDesconhecida` quando ninguém leu o ato
- [x] Medir se "o cliente já credita" é regra ou exceção: **é regra**. Três dos
      quatro com CST 61 já creditam (empresa 06 e empresa 21 por ajuste; só a
      empresa 09 não). Confirma que o produto é auditar o tomado
- [x] **Construir o módulo de combustível, agora como frente principal** —
      **no ar em v0.146.0**. O motor em v0.138.0 a v0.145.0 (leitor,
      classificador, apuração, rodada, caso de uso) e a tela em v0.146.0
      (`pages/Combustivel.tsx`). Validado ponta a ponta contra a empresa 06,
      matriz, 25 competências: devido R$ 1.566.349,35 contra creditado
      R$ 1.328.691,14 — **R$ 237.658,21** a levantar. Três competências batem
      `litros × ad rem` a 7 centavos, o que prova de uma vez os litros do
      leitor, a ad rem de 1,0635 e que o cliente omite o FCV.
      **O que a tela diz além do total**: quanto é estimativa (a era do ST, cuja
      base é o valor do item), o que ficou fora com o motivo de cada recusa, e o
      intervalo de emissão — nenhuma etapa corta por prescrição sozinha
- [x] **CNPJ na chave da seleção** (v0.137.0): `selecionar_por_cnpj_e_competencia`
      substitui `selecionar_por_competencia`, que guardava uma apuração por
      competência e tratava filial como duplicata — na empresa 06 sobrariam 62 de
      411 arquivos. Três testes novos, e a mutação fiel prova que só eles caem
      com a chave antiga: o comportamento das exclusões não muda
- [ ] Acrescentar o grupo **`ICMS61`** ao leitor de XML (`vICMSMonoRet`,
      `adRemICMSRet`): é a fase 2 do combustível. A era do ST já está coberta —
      o leitor tem `vICMSSTRet`, `vICMSSubstituto` e `vICMSEfet`
- [x] Confirmar o **etanol hidratado**: o art. 3º-B da Lei 7.000/2001 põe no
      monofásico o etanol **anidro** (EAC) e só ele, então o hidratado segue
      percentual até hoje e **não tem ad rem** — pedir uma é erro de categoria.
      No ES são 27%; em SP ele divide o inciso VI com o diesel mas tem dois
      Informativos SFP próprios, e por isso ainda recusa
- [ ] Decidir se o **lubrificante** entra como tese separada — R$ ~1 mi medido
      na empresa 06. Confirmado que nunca entrou no monofásico, então a alíquota
      percentual vale até hoje
- [ ] Ler os **Anexos VII e VIII do RICMS/ES** (Decreto 1.090-R) e o **Anexo II
      do RICMS/SP** para resolver o **GLP**: nos dois estados ele não é nomeado
      no artigo de alíquota, e no ES o inciso II, "m" põe a 12% o que está no
      anexo — cinco pontos sobre toda a base de GLP. O motor recusa até lá
- [ ] Decidir o **F100 `IND_OPER = 2`** ("outros documentos e operações"): o
      agregador da Gestão o conta como saída e o 680 o recusa. Na empresa 05 não
      existe nenhum, então não há como medir qual está certo — fica para a
      primeira base que tiver. É divergência latente entre o número que se pede
      e o detalhe que o acompanha (ver DECISOES de 01/10/2026)
- [ ] Levar o **Cancelar para o lado do botão** nas outras telas que ainda o
      põem no lugar dele (`ui/Botao.tsx` com `aoCancelar`, usado na Entrega): é o
      mesmo defeito relatado em 01/10/2026 na tela de exclusões — clique
      impaciente aborta o próprio download e apaga o arquivo já criado
- [x] As três exclusões ligadas ponta a ponta: planilha própria de cada uma,
      bloco próprio na tela, quatro fases na barra da rodada e testes das
      camadas analíticas (v0.119.0)
- [x] Motor do **933 — ISS fora da base** (A100/A170), conferido 100% contra as
      33 linhas do gabarito. O `VL_ISS` do A100 é facultativo: quem não preenche
      sai com a coluna em branco, e o resumo conta quantas notas esperam a
      NFS-e (v0.117.0)
- [x] A alíquota interna com **vigência** e conferida contra a escrituração do
      cliente, não contra o MA. `INTERNA` só tem o que foi medido (MG); as
      outras 26 UF recusam até alguém provar (v0.120.0)
- [ ] Conferir a alíquota interna dos outros 26 estados, uma por uma, no
      primeiro trabalho de cada um: `tools/aferir_aliquota_interna.py` sobre a
      EFD ICMS/IPI do cliente, mais o ato legal. Vários subiram entre 2023 e
      2025, então quase todos vão precisar de **mais de uma vigência**
- [ ] Ler a **NFS-e** para o 933: o XML (INF/SERVICO/VALORES) e o leiaute do
      município de São Paulo, de onde sai o ISS que a escrituração não trouxe.
      Sem isso a tese só alcança quem preencheu o A100 — 1 de 33 notas na empresa 05
- [ ] Varrer os outros motores atrás do mesmo descuido do `C010`: documento que
      fica em buffer e é emitido **depois** de o bloco seguinte já ter trocado o
      estabelecimento. Custou 61 linhas no 903 e estava latente no 037; a 047 já
      fechava antes de trocar
- [ ] Estender o escopo por estabelecimento (`sped/cadastro.py`) a
      `sped/extracao.py`, `sped/consolidado.py` e `analitico/registros_do_sped.py`:
      têm o mesmo defeito que a 037 e a 047 tinham — o 0200 e o 0150 pendem do
      0140, e uma tabela só por arquivo troca a mercadoria entre matriz e filial
- [x] Enriquecimento: descrição de CFOP, município, indicadores e tipo de item, e a
      natureza do crédito deduzida do CFOP — não do tipo do item (v0.76.0)
- [x] Gestão (36 quadros): o núcleo — agregador da EFD, os quadros de PIS e COFINS,
      a seleção por competência e o oráculo `tools/validar_gestao.py` (v0.78.0)
- [x] Etapa `apuracao_contribuicoes`: a Gestão na fila, com parquet longo, planilha
      larga (uma aba por tributo) e tela (v0.83.0)
- [ ] Rodar `tools/validar_gestao.py` contra o export do MA e as EFD reais: é o que
      confirma o porte, e o gabarito não pode ser versionado
- [x] Gestão de IRPJ/CSLL: leitor da ECF, os quadros do Lucro Real e a ECF no
      leitor do 0000 do domínio, como quarto leiaute (v0.79.0)
- [ ] Conferir a suspeita da compensação do próprio período (`_compensacoes`):
      o valor derivado repete a compensação de períodos anteriores
- [x] Caminho até as telas de PIS/COFINS: seletor de tributo ao criar o trabalho,
      destino da etapa `quebra_de_sped` e link do razão contábil (v0.80.0)
- [x] Hub de cards: `/segmentos`, `/segmentos/:chave` e `/modulos/:chave`, com o
      destino pós-login resolvido pelo servidor e o resumo por módulo (v0.81.0)
- [ ] O resto do handoff em Usuários: coluna de módulos na lista e chips de
      "módulos liberados" nos modais de criar e editar — a API já grava desde a v0.66.0
- [ ] Resolver a colisão de vocabulário: o handoff chama de "módulo" o nível 1 e de
      "frente" o nível 2, e `frente` já existe no código como tipo de trabalho
- [x] Tela do razão da ECD, com seletor de conta: busca por código, nome e conta
      referencial, recorte por saldo e os lançamentos em ordem de data (v0.77.0)
- [x] Separar quebra de apuração, e trocar o roteiro linear pela barra de
      funcionalidades — nada trava mais (v0.86.0)
- [ ] Em Quebras: escolher um registro e baixá-lo. O índice já guarda a posição
      de cada um; falta a rota e a tela
- [x] Abas de Exclusões e Histórico na barra; o histórico não conta no progresso (v0.87.0)
- [x] `exclusoes`: as duas teses na mesma rodada — as contribuições fora da
      própria base e o ICMS fora da base (Tema 69), este item a item, corrigido
      pela Selic e conferido 100% contra as 138.358 linhas do relatório 903 do MA
      (v0.114.0)
- [x] A Selic no banco (`selic_mensal`), atualizada pela série 4390 do SGS do
      Banco Central e buscada **só pelos meses que faltam**: mês fechado não muda,
      então guardado é guardado. Rede fora não derruba a rodada; série curta
      recusa a conta em vez de corrigir a menos (v0.115.0)
- [ ] O mês da restituição do Tema 69 é o mês em que se roda. Quem precisar
      simular outro — protocolo planejado para o trimestre que vem — ainda não
      tem por onde pedir: falta o campo na tela e o parâmetro na rota
- [x] Tela do gestor para liberar segmentos a cada pessoa: coluna na lista e
      chips nos formulários de criar e editar (v0.90.0)
- [ ] `quebra_xml`: declarada e sem código. Abrir os XML do lote item a item
- [x] Importar com card próprio, primeiro de todo módulo, e frente de uma etapa
      só indo direto para a tela dela — subir arquivo deixou de exigir entrar
      numa frente de trabalho (v0.121.0)
- [ ] Escolher entre a barra (`BarraDeFuncionalidades`) e os cards
      (`PainelDoTrabalho`): as duas foram construídas para o mesmo lugar
- [ ] Correção à mão: editar na tela do razão, linha a linha
- [ ] **Fim da ST de perfumaria e higiene em 1º/04/2026** (Portaria SRE 94/2025):
      trabalho cuja competência cruze 31/03/2026 monta a ficha como se a ST
      continuasse, e o ICMS suportado do estoque de 31/03/2026 fica no saldo em
      vez de virar pedido. Falta o aviso no razão e o encerramento da ficha na
      data. Ver DECISOES de 21/09/2026
- [ ] Comparar com a RVZ razão, apuração, X.949, canceladas e não escrituradas

### 3. O que a apuração ainda não calcula

- [ ] No arquivo digital: ECF_FAB, 0205 (quem não escritura EFD) e fato gerador
      presumido sem documento (CHV 0, item 999).

### 4. Leitura e desempenho

- [ ] **Movimentos em paralelo por arquivo.** A etapa 3 leu os 12 GB da empresa 19
      em 44 min, um arquivo por vez; a escrita e a pré-validação dos arquivos
      digitais já dividem por processo (DECISOES, 16/09/2026).
- [ ] Leitura de rar e 7z. O lote reconhece como compactado, mas só o zip é
      lido por dentro.
- [ ] Consulta de movimentação por item, na tela.

---

## Riscos conhecidos

**Baixa em 5.927 sem enquadramento na origem.** A empresa 17 transmitiu parte das
5.927 no enquadramento 0; na empresa 20 a proporção é outra (15% contra 74%).
O sistema segue o manual (5.927 é enquadramento 2). Enquanto a origem não
explicar, número derivado das baixas das duas não vai ao cliente como definitivo.

**A pré-validação não é o validador da SEFAZ.** Foi calibrada contra arquivos
aceitos, não contra rejeições. Um lote de rejeições reais vale mais que a norma.

**Venda a consumidor final é escolha do trabalho.** O manual põe o cupom no
enquadramento 1; a empresa 17 transmitiu no 0 e a SEFAZ aceitou. A escolha muda o
complemento inteiro (R$ 1,53 milhão no piloto) e fica registrada no histórico.

**Espaço e rede.** A razão de expansão da base é de cerca de nove vezes, e as
unidades de rede perdem gravação longa: tudo se grava no disco local e só o
pacote pronto vai à rede, conferido pelo SHA-256 do manifesto.

---

## Histórico

**2026-09-09** — Análise da CAT já existente na empresa 17 e na empresa 20: leiaute
decifrado, manuais oficiais localizados, fórmula validada. Arquitetura, modelo
de usuários e estrutura de pastas definidos.

**2026-09-10** — Repositório no GitHub com versionamento. Identidade visual da
BMS. Login com Argon2id, gestão de usuários, papel dev auditável. Razão do item
no domínio, importação de remessa e cadastro de trabalho. Roteiro do trabalho na
tela.

**2026-09-11** — Etapa 2, conferência de documentos, validada em 37,9 milhões
de documentos. Etapa 3, histórico de movimentação. Instalação a um comando.

**2026-09-12** — Front reconstruído no desenho novo. Histórico do trabalho,
sucessão, acesso às empresas, CSV ao lado do xlsx, cancelar carregamentos.

**2026-09-13 e 14** — API migrada para C#, com o motor Python atrás de canal
interno (v0.28 a v0.35). ICMS suportado em cascata, relatório do cliente como
fonte, enquadramento pelo modelo do documento, razão confrontado com a Ficha 3
real da empresa 17 a 100%.

**2026-09-15** — Etapa 4 com rodada e tela, primeira rodada real (8,76 milhões
de itens em 33 min). Etapa 5, razão dos itens, com unidade de conversão e
fichas de estoque negativo fora do total.

**2026-09-16** — Etapas 6, 7 e 8: apuração do período, arquivo digital com
pré-validação, relatórios e entrega com aprovação. Pré-validação do arquivo do
cliente. Revisão da etapa 7 contra os arquivos aceitos da empresa 17. Lapidação:
cadastro editável, pendências por assunto, abertura pelas entradas anteriores,
uso e consumo fora da ficha, série no 1200, substituição entre arquivos do
cliente, CSV pelo DuckDB e arquivos digitais em paralelo.
