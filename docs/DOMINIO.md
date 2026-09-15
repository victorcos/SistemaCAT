# DOMÍNIO — Portaria CAT 42/2018

> Responsabilidade única: responder "como funciona a regra fiscal deste sistema".
> Sem código. Quem quiser saber como está implementado, ver ARQUITETURA.md.

---

## 1. O que a CAT 42 exige

A Portaria CAT 42/2018 da Secretaria da Fazenda de São Paulo disciplina o
**complemento e o ressarcimento do ICMS retido por substituição tributária ou
pago por antecipação**. O contribuinte substituído gera um arquivo digital
mensal, único por período de referência, e o submete a duas validações: a
pré-validação, feita por ele antes do envio, e a pós-validação, feita pela
Fazenda após a recepção.

## 2. Os dois manuais oficiais

São dois documentos distintos e ambos são necessários. Confundi-los custa tempo.

| Manual | O que define | URL |
|---|---|---|
| Leiaute do Arquivo Digital, v1.50, 18 pág. | Os registros do arquivo que vai à SEFAZ | https://portal.fazenda.sp.gov.br/servicos/st/Downloads/Leiaute_Arquivo_Digital_Sistema%20Ressarcimento_ICMS_ST.pdf |
| Sistema de Apuração, v1.50, 11 pág. | As Fichas e como cada coluna é calculada | https://portal.fazenda.sp.gov.br/servicos/st/Downloads/MANUAL%20Sistema%20Ressarcimento_ICMS_ST.pdf |

Texto da portaria: https://legislacao.fazenda.sp.gov.br/Paginas/pcat422018.aspx

Ambos baixam sem login.

## 3. Os registros do arquivo digital

| Registro | Conteúdo | Campos |
|---|---|---|
| 0000 | Abertura e identificação do contribuinte | 8 |
| 0150 | Cadastro de participantes | 8 |
| 0200 | Identificação do item | 8 |
| 0205 | Código anterior do item, só para dispensados do SPED | 4 |
| 1050 | Saldos inicial e final por item | 6 |
| 1100 | Documento fiscal eletrônico | 11 |
| 1200 | Documento fiscal não eletrônico | 15 |

Arquivo em texto, codificado em ISO 8859-1 (Latin-1), delimitador barra vertical,
cada linha terminada em CR e LF. Registros em ordem sequencial ascendente.

O registro **0200 é a chave do cadastro de produto**: traz código de barras, NCM,
CEST, unidade de inventário e alíquota interna. É a base de qualquer de-para.

## 4. As Fichas

| Ficha | Conteúdo |
|---|---|
| 1 | Cadastro de participantes de operações e prestações |
| 2 | Tabela de identificação do item |
| 3 | Controle de estoque das mercadorias em substituição tributária |

A Ficha 3 é **uma por código de mercadoria**, escriturada por custo médio
ponderado móvel. Entradas e devoluções do dia têm de ser lançadas **antes** das
saídas.

## 5. As colunas da Ficha 3 que decidem o cálculo

Numeração oficial. O export que os clientes entregam costuma ter quatro colunas
de identificação antes e quatro de carimbo depois, o que desloca tudo em quatro
posições.

| Col. | Conteúdo |
|---|---|
| 11, 12 | Quantidade e ICMS suportado na **entrada** |
| 13 | Quantidade na **saída** |
| 14 | Valor unitário do ICMS suportado, vindo da coluna 23 da **linha anterior** |
| 15 | Enquadramento 1, saída a consumidor ou usuário final |
| 16 | Enquadramento 2, fato gerador não realizado |
| 17 | Enquadramento 3, isenção ou não incidência |
| 18 | Enquadramento 4, saída para outro estado |
| 19 | Enquadramento 0, demais saídas |
| 20 | Valor de confronto, ICMS efetivo na **saída** (enq. 1 e 3) |
| 21 | Valor de confronto, ICMS efetivo da **entrada** (enq. 2 e 4) |
| 22, 23, 24 | Saldo em quantidade, valor unitário e valor total |
| 25 | **Ressarcimento** |
| 26 | **Complemento** |
| 27 | Crédito da operação própria, artigo 271 do RICMS |

## 6. As fórmulas

**Ressarcimento (coluna 25)** é a diferença **positiva**, exceto nas devoluções
de saída, entre a coluna 15, 16, 17 ou 18 e a coluna 20 ou 21.

**Complemento (coluna 26)** é a diferença **negativa**, exceto nas devoluções de
saída, entre a coluna 15 e a coluna 20 **apenas**.

> Consequência que já gerou falso alarme: nos enquadramentos 2, 3 e 4 **não
> existe complemento a apurar**. Diferença negativa ali resulta em ressarcimento
> zero e complemento zero, e isso está correto.

**Crédito da operação própria (coluna 27)** vem da coluna 21, e só quando o
enquadramento é 4.

## 7. Os códigos de enquadramento legal

| Código | Operação | Base legal |
|---|---|---|
| 0 | Saída para comercialização subsequente e demais saídas | — |
| 1 | Saída a consumidor ou usuário final | art. 269, I, RICMS/00 |
| 2 | Fato gerador não realizado | art. 269, II |
| 3 | Saída ou saída subsequente com isenção ou não incidência | art. 269, III |
| 4 | Saída para outro estado | art. 269, IV |

## 8. O que é o ICMS suportado

É a base de cálculo da sujeição passiva por substituição multiplicada pela
alíquota interna aplicável à saída ao consumidor final. Soma o ICMS incidente na
operação própria do substituto com o retido por substituição. **Inclui o FECOEP**
da Lei 16.006/2015.

Exemplo do manual: mercadoria vendida a R$ 100,00 pelo fabricante, IVA-ST de 50%
e alíquota interna de 18%. Base de retenção R$ 150,00, ICMS suportado R$ 27,00,
sendo R$ 18,00 de operação própria e R$ 9,00 de retido.

## 9. Regras que pegam quem implementa

**Devoluções invertem o lado.** Devolução de venda (CFOP 1.411 e 2.411) é entrada
que anula saída. Devolução de compra (CFOP 5.411 e 6.411) é saída que anula
entrada. No arquivo digital os valores vão **sem** sinal; o sinal negativo é
inserido pelo Pós-Validador ao compor a Ficha 3.

**Baixa de estoque usa CFOP 5.927 e enquadramento 2.** Vale para perecimento,
deterioração, roubo, furto e extravio. O manual recomenda **uma única nota por
período de referência**, com um item por mercadoria.

**Quando não se identifica a entrada**, o valor de confronto usa as entradas mais
recentes, com média ponderada se uma nota não cobrir a quantidade saída.

**Não entram no sistema** as saídas para depósito fechado, armazém geral,
demonstração, conserto e garantia sem destaque do imposto, e seus retornos.

**A primeira linha do período é o saldo inicial**, transcrito da mesma ficha do
período anterior, mesmo que não tenha havido movimento.

## 10. Informação na nota fiscal

O imposto retido cobrável do destinatário vai no campo `infAdFisco` da NF-e, no
formato `&|codigo_do_item|valor|&`, sem espaços, com vírgula decimal.

## 11. Pontos que ainda dependem de confirmação

- Regras de crítica do pré-validador e do pós-validador da SEFAZ. Saber o que é
  rejeitado na prática vale mais que a norma.
- Manuais das demais CATs que o sistema venha a atender.

## 12. O relatório gerencial como fonte

Nem toda empresa libera o XML. Muitas liberam só o relatório gerencial do ERP,
e é com ele que o trabalho tem de sair. O formato varia por empresa e por ano;
o que não varia é o que precisamos dele.

**As três espécies.** A mesma pasta costuma ter arquivos de propósitos
diferentes:

| Espécie | Uma linha por | Serve para |
|---|---|---|
| Movimento | item de documento | é a fonte do razão da Ficha 3 |
| Inventário | item em estoque | estoque de abertura (item 4.1.1) |
| Resumo por produto | item no período | conferir totais; **não** monta razão |

O resumo não tem data nem CFOP por linha, e por isso não posiciona movimento
no razão nem alimenta a média ponderada móvel.

**O relatório pode substituir o XML.** Alguns ERPs já extraem os valores do
documento e os trazem em colunas próprias — no Amigão são `BC ICMS ST;XML`,
`VR. ICMS ST;XML` e `Chave DFe`. Quando existem, valem sobre os valores do
próprio ERP, pela regra de que o XML vence. Quando não existem, o sistema
avisa que o relatório não substitui o XML.

**O inventário nem sempre traz o imposto.** As colunas de ICMS e ST médios por
unidade podem existir no cabeçalho e vir vazias — é o caso do Amigão, nas
842.785 linhas do arquivo. Coluna existir não é coluna preenchida. Quando o
imposto não vem, o estoque de abertura ainda precisa da derivação do item
3.3.8, e o sistema tem de dizer isso em vez de somar zero calado.

**O que se lê de cada espécie** está em `cat/dominio/gerencial/campos.py`. A
lista de campos é o contrato; o mapeamento até as colunas é que é flexível.

---

> O leiaute do arquivo digital (registros 0000 a 1200, campo a campo, com as
> erratas do manual 1.50) está em [`LEIAUTE_ARQUIVO_DIGITAL.md`](LEIAUTE_ARQUIVO_DIGITAL.md).
