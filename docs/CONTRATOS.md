# CONTRATOS — interfaces entre camadas

> Responsabilidade única: o que cada camada promete à outra. Ler antes de mexer
> em qualquer módulo. Contrato quebrado sem atualizar este arquivo é bug.

---

## 1. Portas que a aplicação declara

A camada `aplicacao` nunca importa implementação concreta. Ela declara a
interface e recebe a implementação pronta. É o que permite testar caso de uso
sem banco, sem rede e sem arquivo grande.

| Porta | Promete | Implementada em |
|---|---|---|
| `LeitorDeArquivoFiscal` | percorrer registros de um pacote (rar, zip, txt) em fluxo, sem carregar tudo | `infraestrutura/arquivos/` |
| `RepositorioAnalitico` | agregar e consultar grandes volumes | `infraestrutura/analitico/` |
| `EscritorDePlanilha` | gravar resultado tabular com tipagem correta | `infraestrutura/planilhas/` |
| `RepositorioProjeto` | persistir empresa, projeto, alocação, execução | `infraestrutura/repositorios/` |
| `ServicoDeJulgamento` | decidir casos que a cascata não resolveu | `infraestrutura/ia/` |
| `RegistradorDeExecucao` | abrir, atualizar e fechar uma execução com log | `infraestrutura/repositorios/` |

## 2. Invariantes do domínio

Coisas que o domínio garante e que ninguém pode violar por fora.

- **Valor monetário nunca é `float`.** A Ficha 3 grava quinze casas decimais;
  arredondar cedo desloca o total.
- **Ressarcimento nunca é negativo.** É diferença positiva, ou zero.
- **Complemento só existe no enquadramento legal 1.** Ver DOMINIO.md, seção 6.
- **Código de item não é reutilizável** e não muda entre períodos.
- **Devolução lança nas mesmas colunas da origem, com sinal invertido.**

## 3. Formato entre etapas

Parquet, com esquema declarado. CSV e xlsx só na fronteira com o cliente.

Toda saída derivada carrega, na primeira coluna ou no metadado do arquivo, o
identificador da execução que a gerou. Sem isso não há rastreabilidade.

## 4. Contrato de log

Todo ponto de entrada de camada abre contexto de log com identificador da
execução, projeto, empresa, usuário e etapa. Detalhe em ARQUITETURA.md, seção 12.

## 5. Contrato de acesso

Nenhuma consulta a dado fiscal é feita sem escopo de empresa derivado da
**alocação vigente** do usuário ao projeto. O filtro é aplicado numa camada só,
no backend, e reforçado por segurança em nível de linha no banco. Nunca no front.
