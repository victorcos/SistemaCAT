"""PIS/COFINS: apuração, créditos e as exclusões da base.

Módulo novo (decisão do Victor, 22/09/2026). O que entra aqui é regra das
contribuições: o que compõe e o que sai da base de cálculo, o regime cumulativo
e o não cumulativo, os créditos, e o reenquadramento de CST.

**A CBS mora ao lado**, quando chegar: ela substitui PIS/COFINS a partir de 2027
e, de lá até 2033, é a mesma equipe apurando as duas lado a lado.

Duas coisas ficam **fora** daqui de propósito:

* **ler SPED** é de `dominio/sped/` e `infraestrutura/`, porque a mesma EFD serve
  a todos os módulos — a exclusão do ICMS da base (Tema 69) lê a EFD ICMS/IPI
  que o trabalho de ICMS já importou;
* **a quebra de SPED** — indexar por offset e extrair bloco sob demanda — não é
  regra de contribuição: é leitura de arquivo, e serve a qualquer tributo.
"""
