# VERSIONAMENTO — regra do projeto

> **Toda implementação nova sobe para o GitHub, versionada.** Regra do dono do
> produto, estabelecida em 10/09/2026. Não é sugestão.

---

## 1. O que significa "toda implementação"

Qualquer coisa que mude comportamento ou conhecimento do sistema:

- módulo novo ou alterado
- correção de defeito
- script de apoio
- documento de domínio, arquitetura ou decisão
- migração de banco

Trabalho que fica só na máquina de quem escreveu não existe para o time.

## 2. Versionamento semântico

Formato `MAJOR.MINOR.PATCH`, com etiqueta anotada no Git.

| Parte | Quando sobe | Exemplo neste projeto |
|---|---|---|
| MAJOR | quebra contrato de quem consome | mudança no formato da API ou do arquivo entregue |
| MINOR | funcionalidade nova, compatível | leitor de XML no nível de item |
| PATCH | correção sem mudar contrato | ajuste no denominador do escore de similaridade |

Antes de `1.0.0`, o sistema ainda não está em produção, e MINOR pode conter
quebra. A partir de `1.0.0`, não pode.

## 3. Ramos

- `main` — sempre funcional. Nada entra sem passar nos testes.
- `feat/<assunto>` — funcionalidade nova
- `fix/<assunto>` — correção
- `docs/<assunto>` — só documentação

Nunca commitar direto em `main` depois que houver mais de uma pessoa no projeto.

## 4. Mensagem de commit

Formato convencional, em português, no imperativo.

```
<tipo>(<escopo>): <o que mudou>

<por que mudou, se não for óbvio>
```

Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`.

Exemplo:

```
fix(depara): corrigir denominador do escore de similaridade

Termos ausentes do outro catálogo ficavam fora do denominador, e itens
com vocabulário próprio desconhecido casavam 1,00 com qualquer vizinho
que compartilhasse uma palavra rara.
```

## 5. O que nunca sobe

- Dado fiscal de cliente, em qualquer formato
- Arquivo compactado de origem
- Planilha ou CSV gerado, exceto amostra pequena e anonimizada para teste
- Senha, token, chave e arquivo de ambiente

O `.gitignore` já bloqueia esses padrões. Se algo passar, o remédio é reescrever
o histórico, não apagar num commit seguinte.

## 6. Antes de subir

1. Testes de unidade passando
2. Log presente no código novo, conforme ARQUITETURA.md seção 12
3. `DECISOES.md` atualizado se houve escolha de arquitetura
4. `PLANEJAMENTO.md` atualizado se concluiu item do roteiro

## 7. Repositório

Privado. A documentação contém nome de cliente, volume e valor apurado. Só passa
a público se houver decisão explícita e limpeza prévia do conteúdo sensível.

## 4. Onde a versão vive

**Em um lugar só: `backend/pyproject.toml`, campo `version`.** A API lê daí
(`cat/versao.py`) e expõe em `/api/saude`. A etiqueta do git repete o número,
com o prefixo `v`.

A ordem de um release é sempre a mesma, e a ordem importa:

1. bump do `version` no `pyproject.toml`
2. commit (com `docs/DECISOES.md` em dia)
3. `git tag -a v<version>` no mesmo commit
4. `git push --follow-tags`

**Por quê.** A versão já viveu escrita à mão em dois lugares — `app.py` e
`pyproject.toml` — e os dois pararam em 0.3.0 enquanto as etiquetas chegavam a
v0.15.2. O `/api/saude`, que existe para dizer *o que está rodando*, dizia
outra coisa. Um teste (`tests/unidade/test_versao.py`) falha quando a etiqueta
mais recente está **à frente** do `pyproject` — que é exatamente como o drift
aconteceu. O contrário é normal: é o commit de bump, antes de etiquetar.
