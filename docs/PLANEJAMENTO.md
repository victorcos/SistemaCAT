# PLANEJAMENTO — Sistema CAT

> O que existe, o que falta e em que ordem. Atualizado a cada entrega.
> O porquê de cada escolha fica em DECISOES.md; as rotas, em CONTRATOS.md.

---

## Onde estamos

**As oito etapas da CAT 42 estão no ar (v0.60.2), e o trabalho do Amigão passou
por todas** (de novo em 16/09/2026, da etapa 4 à 8, em 59 min). Desde a v0.53, a
etapa 3 lê o item do XML, o razão aplica o de-para aprovado e confronta os
enquadramentos 2 e 4 com o crédito do art. 271; na v0.54, a nota cancelada na
SEFAZ sai da movimentação, a não escriturada ganha a contingência do art. 527 e o
XML dentro de zip é lido sem extrair — correções que vieram da comparação com a
CAT 42 da Advertising (DECISOES). Da pasta com EFD, XML e relatórios do ERP até o pacote de entrega
com o arquivo digital pré-validado e o manifesto com SHA-256, pela tela, com
fila, cancelamento, histórico e aprovação de quem responde pelo negócio.

A API é C# (.NET 10) e o trabalho pesado é Python com DuckDB, num motor sem
rota pública (DECISOES, 13/09/2026). O front é React. Postgres guarda cadastro,
execuções e histórico; os dados de cada execução ficam em parquet no disco local.

O que o piloto deixou claro é que **o sistema calcula e o Amigão ainda não tem
dado para pedir**: todo o ressarcimento apurado é de lojas de MS, e as 234
competências de São Paulo saem como prévia porque o relatório de saídas que
chegou não tem as lojas paulistas (ver "Dados que faltam").

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

Em volta: login com Argon2id e escopo por empresa, gestão de usuários com as
três salvaguardas, acesso às empresas, histórico do trabalho com sucessão,
cadastro do trabalho editável com aviso de base fora do período (v0.51).

---

## O que foi medido contra dado real

| O quê | Contra | Resultado |
|---|---|---|
| Fórmula do ressarcimento | Ficha 3 da BOA e da Casa Avenida, 706 milhões de linhas | 99,63% das linhas; o resto, 1 centavo de arredondamento |
| Razão do item | Ficha 3 da BOA, uma filial e um mês | 550.862 linhas, 100% em saldo e ressarcimento, R$ 0,00 de diferença |
| ICMS suportado | Book do Superpão | ICMS + ST + FECOP em 100% de 1.242.621 linhas |
| Leiaute do arquivo digital | 7 arquivos que a SEFAZ aceitou da BOA (2021 a 2024) | registro a registro; nenhum erro de pré-validação nos aceitos |
| Pré-validação | Arquivos da BOA | recompõe 100% das quantidades e 99,99% dos valores a 5 centavos |
| Leitura da EFD | 7.036 EFD reais, seis versões de leiaute | sem falha |
| Conferência | 37,9 milhões de documentos do Amigão | três listas, validada também com relatório do cliente simulado |

---

## O que vem pela frente

Em ordem de prioridade. Cada item entra com decisão registrada em DECISOES.md.

### 1. Fechar o piloto do Amigão

- [ ] **Aprovar a entrega.** Só revisor ou gestor aprova; o dev não conta como
      responsável pelo negócio. Depende do Pedro, do Rafael ou do Vinícius.
- [ ] **Dados que faltam**, a pedir ao cliente:
  - relatório de saídas (ou XML dos cupons) das 22 lojas de São Paulo — sem ele
    o pedido paulista é zero por falta de dado, não de direito;
  - EFD de antes de 01/2021, para valorar a abertura pelas entradas anteriores
    (item 3.3.8 do manual); hoje 400 mil fichas abrem sem ICMS;
  - os arquivos de 2023 em diante que o OneDrive não baixou.

### 2. Comparação com a CAT 42 da Advertising Operations (16/09/2026)

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
- [x] Carregar a Advertising no sistema (trabalho 5) e comparar o de-para com a RVZ:
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
- [ ] **Decidir a premissa do ICMS efetivo do enquadramento 1**: o art. 34 do
      Anexo II (carga 12%) não alcança saída a consumidor final (§ 1º) nem a
      cadeia da ST (RC 23455/2021). Hoje o sistema aplica a redução
      (+R$ 407.210,25); a alíquota cheia dá −R$ 77.779,52. Ver DECISOES de
      18/09/2026
- [ ] Comparar com a RVZ razão, apuração, X.949, canceladas e não escrituradas

### 3. O que a apuração ainda não calcula

- [ ] No arquivo digital: ECF_FAB, 0205 (quem não escritura EFD) e fato gerador
      presumido sem documento (CHV 0, item 999).

### 4. Leitura e desempenho

- [ ] **Movimentos em paralelo por arquivo.** A etapa 3 leu os 12 GB do Amigão
      em 44 min, um arquivo por vez; a escrita e a pré-validação dos arquivos
      digitais já dividem por processo (DECISOES, 16/09/2026).
- [ ] Leitura de rar e 7z. O lote reconhece como compactado, mas só o zip é
      lido por dentro.
- [ ] Consulta de movimentação por item, na tela.

---

## Riscos conhecidos

**Baixa em 5.927 sem enquadramento na origem.** A BOA transmitiu parte das
5.927 no enquadramento 0; na Casa Avenida a proporção é outra (15% contra 74%).
O sistema segue o manual (5.927 é enquadramento 2). Enquanto a origem não
explicar, número derivado das baixas das duas não vai ao cliente como definitivo.

**A pré-validação não é o validador da SEFAZ.** Foi calibrada contra arquivos
aceitos, não contra rejeições. Um lote de rejeições reais vale mais que a norma.

**Venda a consumidor final é escolha do trabalho.** O manual põe o cupom no
enquadramento 1; a BOA transmitiu no 0 e a SEFAZ aceitou. A escolha muda o
complemento inteiro (R$ 1,53 milhão no piloto) e fica registrada no histórico.

**Espaço e rede.** A razão de expansão da base é de cerca de nove vezes, e as
unidades de rede perdem gravação longa: tudo se grava no disco local e só o
pacote pronto vai à rede, conferido pelo SHA-256 do manifesto.

---

## Histórico

**2026-09-09** — Análise da CAT já existente na BOA e na Casa Avenida: leiaute
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
real da BOA a 100%.

**2026-09-15** — Etapa 4 com rodada e tela, primeira rodada real (8,76 milhões
de itens em 33 min). Etapa 5, razão dos itens, com unidade de conversão e
fichas de estoque negativo fora do total.

**2026-09-16** — Etapas 6, 7 e 8: apuração do período, arquivo digital com
pré-validação, relatórios e entrega com aprovação. Pré-validação do arquivo do
cliente. Revisão da etapa 7 contra os arquivos aceitos da BOA. Lapidação:
cadastro editável, pendências por assunto, abertura pelas entradas anteriores,
uso e consumo fora da ficha, série no 1200, substituição entre arquivos do
cliente, CSV pelo DuckDB e arquivos digitais em paralelo.
