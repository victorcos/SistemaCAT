# Sistema CAT

Sistema de apuração e conferência das obrigações da CAT, começando pela
Portaria CAT 42/2018 de São Paulo (ressarcimento e complemento do ICMS retido
por substituição tributária).

## Frentes previstas

| Frente | Situação |
|---|---|
| CAT 42 — ressarcimento e complemento de ICMS-ST | leiaute decifrado e fórmula validada |
| De-para de produto | cascata determinística medida e definida |
| Quebra de SPED ICMS-IPI | motor existente a portar |
| Nota fiscal (XML) | leitor de cabeçalho existente, falta nível de item |

## Documentação

Ler nesta ordem:

1. `docs/DOMINIO.md` — a regra fiscal, sem código
2. `docs/ARQUITETURA.md` — como o sistema é montado e por quê
3. `docs/CONTRATOS.md` — o que cada camada promete
4. `docs/DECISOES.md` — as escolhas, datadas e justificadas
5. `docs/PLANEJAMENTO.md` — o que já foi apurado e o roteiro
6. `docs/VERSIONAMENTO.md` — como se sobe código neste projeto

## Estrutura

```
backend/    Python: domínio, aplicação, infraestrutura, apresentação, workers
frontend/   React + TypeScript, fala só por API
data/       entrada, trabalho e saída (não versionado)
docker/
scripts/
```

## Regras que não se negociam

- Domínio puro, sem I/O. O cálculo roda em teste de unidade em milissegundos.
- Todo código com log estruturado. Ver ARQUITETURA.md, seção 12.
- Cliente é dado, não pasta de código.
- Gerar em disco local e copiar para a rede depois, conferindo hash.
- Toda implementação nova sobe versionada. Ver VERSIONAMENTO.md.
- Dado fiscal de cliente **nunca** entra no repositório.
