# PLANEJAMENTO — Sistema CAT

> Histórico do que já foi levantado e o que vem pela frente.
> Atualizado a cada entrega. As escolhas de arquitetura ficam em DECISOES.md.

---

## Onde estamos

**Etapa 1 em andamento.** O leiaute da CAT 42 está decifrado e a fórmula do
ressarcimento validada em mais de 1,8 milhão de linhas reais. A primeira fatia
vertical está no ar: domínio de acesso, autenticação com escopo por empresa,
log estruturado e a tela de login, com 46 testes passando.

---

## O que já foi apurado

### Regra fiscal

Os dois manuais oficiais da SEFAZ-SP foram localizados e lidos. O leiaute do
arquivo digital e o Sistema de Apuração estão destrinchados em `DOMINIO.md`, com
as fórmulas de ressarcimento e complemento, os cinco enquadramentos legais e as
regras que costumam pegar quem implementa.

### Validação em dados reais

Duas empresas do Grupo Plurix foram processadas de ponta a ponta.

| | BOA | Casa Avenida |
|---|---|---|
| Volume lido | 119,82 GB | 99,99 GB |
| Linhas | 400.381.153 | 305.684.649 |
| Tempo | 711 s | 634 s |
| Filiais | 27 | 43 |
| Período | 01/2021 a 12/2025 | 06/2018 a 12/2025 |

A fórmula `ressarcimento = max(0, enquadramento − ICMS efetivo)` confere em
99,63% das linhas. As exceções divergem em no máximo um centavo, por
arredondamento da origem.

### Achados que viram funcionalidade

**Baixas sem enquadramento.** Linhas de CFOP 5927 de itens que tinham ICMS-ST em
estoque, mas sem enquadramento legal preenchido. Na BOA são 40.371 linhas e
R$ 181.302,55; na Casa Avenida, 114.343 linhas e R$ 521.509,98. A proporção é
muito diferente entre as duas, 15% contra 74%, o que sugere regra de negócio
distinta ou falha de geração. **Pendente de confirmação com a origem.**

**Cadastro de produto é limpo.** Na BOA, 24.730 itens distintos, 98,1% com código
de barras, 100% com NCM e CEST, e zero divergência de código de barras entre as
21 filiais. O de-para interno já vem pronto do ERP do cliente.

**Sortimento pouco sobreposto entre empresas.** No cruzamento BOA contra Casa
Avenida, 34,5% casam por código de barras e 59,5% simplesmente não existem na
outra empresa. Só 5,6% exigem julgamento.

---

## Roteiro

### Etapa 1 — Fundação

Objetivo: ter onde apoiar tudo o mais.

- [ ] Domínio da CAT 42 em código, com as duas fórmulas e os enquadramentos
- [ ] Testes de unidade do cálculo, rodando em milissegundos sem arquivo grande
- [x] Log estruturado, conforme ARQUITETURA.md seção 12
- [x] Postgres com migrações versionadas (Alembic)
- [ ] Modelo de dados: empresa, estabelecimento, projeto, usuário, alocação,
      atividade, execução — *empresa, usuário e alocação prontos; projeto,
      atividade e execução entram na etapa 2*
- [x] Gestão de usuários com as três salvaguardas
- [x] Autenticação com escopo por empresa
- [x] Tela de login
- [x] Tela de gestão de usuários e troca obrigatória de senha

### Etapa 2 — Ingestão

Objetivo: transformar pacote bruto do cliente em base consultável.

- [x] Leitura de remessa em zip, sem extrair para disco
- [ ] Leitura em fluxo de rar, incluindo aninhados
- [ ] Parser da Ficha 3 e do arquivo digital CAT 5
- [ ] Gravação em parquet, particionada por empresa e competência
- [ ] Registro de cada execução em banco, com hash dos arquivos gerados
- [ ] Manifesto de origem por empresa

### Etapa 3 — Apuração e conferência

Objetivo: o produto que o cliente enxerga.

- [ ] Recálculo independente do ressarcimento, para conferir o que veio pronto
- [ ] Detecção das anomalias já identificadas, começando pelas baixas sem
      enquadramento
- [ ] Relatórios em Excel, com quebra acima de 900 mil linhas
- [x] Histórico de movimentação: itens da EFD (C170), analítico (C190/C850),
      cadastro (0200) e inventário (bloco H), cada movimento marcado pela
      conferência — *etapa 3 no ar; item de saída vem do XML, etapa seguinte*
- [ ] Consulta de movimentação por item

### Etapa 4 — De-para

Objetivo: casar produto com custo baixo e sem invenção.

- [ ] Cascata determinística: código de barras, depois NCM com CEST e descrição,
      depois descrição
- [ ] Similaridade textual com o denominador correto e mínimo de dois termos
      distintivos em comum
- [ ] Fila de julgamento, com candidatas, para o agente decidir
- [ ] Persistência do de-para aprovado, para não repagar o mesmo item

### Etapa 5 — Front

Objetivo: sair do terminal.

- [x] Obter o logotipo nas versões positiva e negativa (PNG em alta; vetor ainda ajudaria)

- [ ] API com as rotas de projeto, execução e consulta
- [ ] React com tabela virtualizada, para o detalhe de milhão de linhas
- [ ] Acompanhamento de processo longo
- [ ] Tela de revisão do de-para

### Etapa 6 — Demais frentes

- [ ] Quebra de SPED ICMS-IPI, portando o indexador por offset
- [ ] Nota fiscal em XML, ampliando o leitor para o nível de item
- [ ] Pré-validação do arquivo antes do envio à SEFAZ

---

## Riscos conhecidos

**A anomalia das baixas sem enquadramento não está explicada.** Enquanto não
houver confirmação da origem, nenhum número derivado dela deve ser apresentado ao
cliente como definitivo.

**Não temos as regras de crítica do validador da SEFAZ.** Sem elas, a
pré-validação será uma aproximação. Um lote de rejeições reais vale mais que a
norma.

**Espaço em disco.** A razão de expansão é de cerca de nove vezes. Trabalhando do
compactado cabem dezenas de empresas no drive Z; descompactando, cerca de dez. O
drive Y está em 100% de uso.

---

## Histórico

**2026-09-09** — Análise da CAT já existente nas empresas BOA e Casa Avenida.
Leiaute decifrado, manuais oficiais localizados, fórmula validada. Extração de
CFOP 5927 e movimentação por item entregues nas duas empresas. De-para
sistemático medido e desenhado.

**2026-09-09** — Definição da arquitetura, do modelo de usuários e da estrutura de
pastas. Projeto criado.

**2026-09-10** — Repositório publicado no GitHub e regra de versionamento
estabelecida.

**2026-09-10** — Identidade visual definida a partir da marca BMS. Cores
extraídas do logotipo por amostragem, contraste conferido, tokens criados.

**2026-09-10** — Primeira fatia vertical entregue: domínio de acesso, caso de uso
de autenticação, JWT com bcrypt, log estruturado, API e tela de login. 46 testes,
sendo 35 de unidade rodando em 0,07 s sem banco.

**2026-09-10** — Senha migrada de bcrypt para Argon2id, com pimenta opcional e
reprocessamento transparente no login. 70 testes.

**2026-09-10** — Gestão de usuários com as três salvaguardas, bloqueio em dois
níveis e migração para Postgres com Alembic. 122 testes.

**2026-09-10** — Papel dev com bypass auditável do escopo de empresa. Rotas
passam a exigir capacidade em vez de papel. 135 testes.

**2026-09-10** — Front da gestão de usuários: moldura da aplicação, lista com
ações, cadastro, e a troca obrigatória de senha que fechava o ciclo da senha
provisória.

**2026-09-10** — Logotipos oficiais recebidos em alta resolução com
transparência. Paleta corrigida: o laranja estava em `#EE8633` e o oficial é
`#FF7F00`.

**2026-09-10** — Razão do item (Ficha 3) no domínio, com custo médio ponderado
móvel. Importação de remessa, pré-cadastro de empresa a partir do SPED e
cadastro de projeto, com tela. Validado contra 7.036 arquivos reais de EFD
ICMS/IPI, seis versões de leiaute, sem falha.

**2026-09-10** — Tela de trabalhos com cartões por projeto e página de detalhe
com o roteiro de processamento da CAT em sete etapas.

**2026-09-11** — Conferência de documentos (etapa 2) com três listas —
pendentes, não escrituradas e conferidas — validada em base real de 37,9
milhões de documentos e em três cenários simulados com relatório do cliente.
Etapa 3, histórico de movimentação, no ar: a EFD não tem item de saída
(NF-e própria sem C170, SAT sem C810), e a etapa diz isso com número.
