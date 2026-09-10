# DECISÕES — Sistema CAT

> Registro datado das escolhas e do porquê. Decisão sem motivo escrito vira
> discussão de novo daqui a seis meses.

---

## 2026-09-09 — Python com DuckDB como base, não outra linguagem

**Decisão.** Python para leitura e varredura, DuckDB para agregação, xlsxwriter
para planilha.

**Por quê.** Medição, não preferência. A mesma varredura de 119,82 GB e
400.381.153 linhas levou 711 segundos quebrando toda linha e 293 segundos
filtrando por bytes. Mesma linguagem, 2,4 vezes de diferença. No segundo caso o
processo já rodava na velocidade do descompactador, então o teto deixou de ser a
linguagem. Reescrever em Rust ou Go daria ganho perto de zero e jogaria fora o
ecossistema e os projetos que já existem.

**Consequência.** Rust e Go só voltam à mesa se um perfil mostrar gargalo de CPU
em parsing, o que hoje não existe.

---

## 2026-09-09 — Front em React, saindo do Streamlit

**Decisão.** React com TypeScript, falando só por API com o FastAPI.

**Por quê.** O Streamlit reexecuta o script a cada interação. Isso não sustenta
tabela de 1,28 milhão de linhas, processo de onze minutos, múltiplos usuários com
separação por cliente, nem tela com regra visual própria.

**O ponto que importa mais que o framework.** O erro a evitar não é usar
Streamlit, é deixar regra de negócio dentro da tela. Com a lógica num pacote e
API por cima, o front vira detalhe substituível.

---

## 2026-09-09 — Postgres desde o início, não SQLite

**Decisão.** Postgres, com segurança em nível de linha nas tabelas fiscais.

**Por quê.** Usuário, papel, vínculo com cliente, auditoria e execução exigem
transação e concorrência real. O reenquadrador usa SQLite e funciona para o
escopo dele, mas não escala para vários analistas em processos longos
simultâneos.

---

## 2026-09-09 — Log obrigatório em todo código

**Decisão.** Nenhum código entra sem log estruturado. Detalhe em ARQUITETURA.md,
seção 12.

**Por quê.** Pedido do dono do produto. Os processos são longos e sobre arquivos
enormes; quando falha, não dá para reproduzir observando. A informação precisa
estar gravada na primeira execução.

---

## 2026-09-09 — Módulo por frente, nunca por cliente

**Decisão.** `cat42`, `depara`, `sped`, `notafiscal`. Cliente é dado.

**Por quê.** Já são quatro empresas e vão entrar mais. Se cliente virar pasta de
código, cada empresa nova custa desenvolvimento em vez de cadastro.

---

## 2026-09-09 — Reaproveitar estrutura do reenquadrador, nunca o conteúdo

**Decisão.** Extrair `MotorClassTrib`, `MotorRegras` e `PreProcessadorTexto` para
uso comum. A base de conhecimento tributária **não** é reaproveitada.

**Por quê.** A mecânica de hierarquia de prefixo de NCM, exceção com escopo e
escala de confiança já passou por produção e levaria meses para reinventar. Mas o
conteúdo é de PIS e COFINS e não vale para ICMS-ST. Misturar os dois produziria
enquadramento errado com aparência de fundamentado.

---

## 2026-09-09 — De-para com cascata determinística antes do modelo

**Decisão.** Casar por código de barras, depois por NCM com CEST e descrição
normalizada, depois por descrição, e só então similaridade textual. O modelo
recebe candidatas, nunca a pergunta em aberto.

**Por quê.** Medição na BOA: 24.730 itens distintos, 98,1% com código de barras,
100% com NCM e CEST, e **zero** códigos com barras divergente entre as 21
filiais. Onde existe chave exata, usar similaridade é trocar certeza por
probabilidade.

**Duas armadilhas registradas na mesma data.** Primeira: "código de barras sem
par" não é fila de IA; se o código não existe do outro lado, não há decisão a
tomar e pedir decisão induz invenção. Segunda: no escore de similaridade o
denominador tem de somar o peso de **todos** os termos da consulta, usando peso
máximo para termo ausente do outro catálogo. Sem isso, um cigarro casou com uma
cerveja com escore 1,00 porque a única palavra em comum era "orange".

---

## 2026-09-09 — Gerar em disco local e copiar depois

**Decisão.** Nenhuma escrita longa direto em unidade de rede. Gerar local,
copiar, conferir hash.

**Por quê.** Histórico de gravações perdidas, agora explicado: o drive Y está em
100% de uso, com 36 GB livres de 3,7 TB. Não era instabilidade de rede.

---

## 2026-09-09 — Parquet como formato de trabalho, CSV só para entrega

**Decisão.** Entre etapas, parquet. CSV e xlsx só no que vai ao cliente.

**Por quê.** Menor, tipado, e o DuckDB lê muito mais rápido. Um extrato de 470 MB
em CSV é lento de reler a cada análise.
