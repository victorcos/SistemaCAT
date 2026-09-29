"""Conferir a nossa Consulta de Saídas contra o gabarito do MA, linha a linha.

O 047 não se confere por total. Um relatório de saídas que bate no somatório e
erra a coluna da natureza em 30% das linhas passa no teste do total e reprova
no uso — e foi exatamente para não depender do total que esta ferramenta
compara **a linha inteira**: as 53 colunas, texto contra texto.

## Como

1. lê os SPED da pasta e gera as nossas linhas com `sped/saidas.py`;
2. lê os CSV que o MA exportou — quantas partes forem — e monta as dele;
3. compara.

A comparação é de **multiconjunto**: cada linha vira uma tupla das 53 colunas,
e o que se conta é quantas vezes cada tupla aparece de cada lado. Isso torna a
conferência indiferente à ordem, que é como tem de ser: o MA exporta na ordem
dele e nós na ordem do arquivo, e ordem diferente não é erro.

Na rodada inteira a tupla é guardada como hash, senão não cabe na memória —
são 7,8 milhões de linhas. Com `--competencia` a comparação é de uma
competência só e guarda a linha inteira, o que permite dizer **qual coluna**
divergiu e em quantas linhas. É esse o modo de investigar; o outro é o de
conferir.

**O ponto-e-vírgula é o único ajuste na comparação.** Ver `comparavel`: o CSV
do MA não consegue transportá-lo, e comparar sem isso acusaria defeito onde
não há.

**Não versiona dado de cliente.** Recebe os caminhos por argumento e imprime
nomes de coluna, contagens e, no modo detalhado, no máximo três exemplos por
coluna divergente — que é o mínimo para achar o defeito.

    python tools/validar_047.py <pasta dos SPED> <pasta dos CSV do MA>
    python tools/validar_047.py <pasta> <pasta> --competencia 01/10/2025
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
import time

from cat.infraestrutura.sped.leitor import codificacao_de
from cat.infraestrutura.sped.saidas import colunas_da_saida, saidas

# a ordem em que o MA exporta, coluna a coluna, casada com a nossa
COLUNAS_DO_MA = (
    "CNPJ", "Período", "Registros", "Modelo", "Situação", "Código Participante",
    "CNPJ Participante", "CPF Participante", "Nome Participante", "UF Origem/Destino",
    "Número Documento", "Série", "Chave NF-e", "Data Documento", "Data Entrada/Saída",
    "Vlr Documento", "Vlr Desconto NF", "Vlr Mercadoria/Operação", "Vlr Frete", "Vlr Seguro",
    "Vlr Outras DA", "Número Item", "Código Item", "Descrição Complementar", "Descrição Item",
    "NCM", "Código Serviço", "Código Barra", "Tipo Item", "Vlr Item", "Qtde", "Unidade Medida",
    "Vlr Desconto Item", "CFOP", "Descrição CFOP", "Faturamento", "Natureza", "Vlr ICMS",
    "Vlr ICMS-ST", "Vlr IPI", "CST PIS", "Vlr Base Cálculo PIS", "Qtde Base Cálculo PIS",
    "Alíquota PIS", "Qtde Alíquota PIS", "Vlr PIS", "CST Cofins", "Vlr Base Cálculo Cofins",
    "Qtde Base Cálculo Cofins", "Alíquota Cofins", "Qtde Alíquota Cofins", "Vlr Cofins",
    "Conta Contábil",
)

# o nosso nome de campo está nesta mesma ordem — é o que `colunas_da_saida()`
# devolve, e a asserção abaixo é o que impede que uma inserção no meio do
# dataclass desalinhe a conferência inteira sem ninguém notar
NOSSAS = tuple(colunas_da_saida())
assert len(NOSSAS) == len(COLUNAS_DO_MA), (
    f"a 047 tem {len(NOSSAS)} colunas e o gabarito {len(COLUNAS_DO_MA)}")


def limpar(bruto: str) -> str:
    """Tira o `="..."` com que o MA protege o zero à esquerda no Excel.

    **E desdobra a aspa dobrada.** Dentro de campo entre aspas, o CSV escreve
    uma aspa literal como duas — `1.2""` é `1.2"`. Sem desfazer isso, uma
    descrição com polegada no nome aparece como divergência que não existe:
    foi o que aconteceu com uma trincha de 1.2" em setembro de 2022, e passei
    um tempo procurando defeito no relatório em vez de no conferidor.
    """
    texto = bruto.strip()
    if texto.startswith('="') and texto.endswith('"'):
        texto = texto[2:-1]
    elif texto.startswith('"') and texto.endswith('"'):
        texto = texto[1:-1]
    return texto.replace('""', '"').strip()


def linhas_do_ma(pasta: str, competencia: str | None):
    """As linhas do gabarito, já limpas, na ordem das colunas."""
    arquivos = sorted(glob.glob(os.path.join(pasta, "*047*.csv")))
    if not arquivos:
        raise SystemExit(f"nenhum CSV do 047 em {pasta}")
    for caminho in arquivos:
        with open(caminho, "rb", buffering=1 << 22) as arquivo:
            cabecalho = [limpar(c) for c in
                         arquivo.readline().decode("utf-8-sig", "replace").rstrip().split(";")]
            if tuple(cabecalho) != COLUNAS_DO_MA:
                faltam = set(COLUNAS_DO_MA) - set(cabecalho)
                sobram = set(cabecalho) - set(COLUNAS_DO_MA)
                raise SystemExit(f"{os.path.basename(caminho)}: cabeçalho diferente do esperado. "
                                 f"faltam={sorted(faltam)} sobram={sobram}")
            for bruto in arquivo:
                partes = bruto.decode("utf-8-sig", "replace").rstrip("\r\n").split(";")
                if len(partes) != len(COLUNAS_DO_MA):
                    continue
                linha = tuple(limpar(p) for p in partes)
                if competencia is None or linha[1] == competencia:
                    yield linha


def comparavel(valor: str) -> str:
    """O nosso valor como o MA conseguiria escrevê-lo no CSV dele.

    **O gabarito não consegue escrever ponto-e-vírgula.** É o separador do
    arquivo, e o MA o troca por ponto antes de exportar: o item que o SPED
    chama de "MARG DELICIA 1KG C/SAL C/CREME DE LEITE ;" aparece lá terminado
    em ponto. O valor certo é o nosso — veio do arquivo —, e a diferença é do
    gabarito, não do relatório.

    Sem isto, essas linhas apareceriam como divergência para sempre, e quem
    rodasse a conferência ficaria procurando defeito onde não há. São 3 linhas
    em 7.784.121, todas do mesmo produto.
    """
    return valor.replace(";", ".") if ";" in valor else valor


def nossas_linhas(pasta: str, competencia: str | None):
    """As nossas, de todos os SPED da pasta — ou de um arquivo só.

    Aceitar um arquivo é o que torna a investigação viável: conferir uma
    competência lendo as 57 é esperar por 56 que não serão comparadas.
    """
    arquivos = ([pasta] if os.path.isfile(pasta)
                else sorted(glob.glob(os.path.join(pasta, "*.txt"))))
    if not arquivos:
        raise SystemExit(f"nenhum SPED em {pasta}")
    for caminho in arquivos:
        for linha in saidas(caminho, codificacao_de(caminho)):
            valores = linha.como_dicionario()
            if competencia is None or valores["periodo"] == competencia:
                yield tuple(comparavel(valores[nome]) for nome in NOSSAS)


def conferir_tudo(pasta_sped: str, pasta_ma: str) -> int:
    """A rodada inteira, por hash: bate ou não bate, e onde não bate."""
    print("lendo o gabarito…", flush=True)
    inicio = time.time()
    # por competência, e não num balaio só: quando sobra linha, o que se quer
    # saber primeiro é **em que mês** — é com isso que se roda o modo detalhado
    do_ma: collections.Counter[tuple[str, int]] = collections.Counter()
    ramos_do_ma: collections.Counter[tuple[str, str]] = collections.Counter()
    for linha in linhas_do_ma(pasta_ma, None):
        do_ma[(linha[1], hash(linha))] += 1
        ramos_do_ma[(linha[1], linha[2])] += 1
    print(f"  {sum(do_ma.values()):,} linhas em {time.time() - inicio:.0f}s".replace(",", "."))

    print("lendo os SPED…", flush=True)
    inicio = time.time()
    nossos: collections.Counter[tuple[str, int]] = collections.Counter()
    nossos_ramos: collections.Counter[tuple[str, str]] = collections.Counter()
    for linha in nossas_linhas(pasta_sped, None):
        nossos[(linha[1], hash(linha))] += 1
        nossos_ramos[(linha[1], linha[2])] += 1
    print(f"  {sum(nossos.values()):,} linhas em {time.time() - inicio:.0f}s".replace(",", "."))

    faltando = do_ma - nossos
    sobrando = nossos - do_ma
    iguais = sum((do_ma & nossos).values())
    so_do_ma = sum(faltando.values())
    so_nossas = sum(sobrando.values())
    total = sum(do_ma.values())
    print(f"\n{'IGUAIS':<12}{iguais:>12,}  {100 * iguais / max(total, 1):.4f}% do gabarito"
          .replace(",", "."))
    print(f"{'SÓ DO MA':<12}{so_do_ma:>12,}  linhas que o gabarito tem e nós não".replace(",", "."))
    print(f"{'SÓ NOSSAS':<12}{so_nossas:>12,}  linhas que geramos a mais".replace(",", "."))

    por_competencia: collections.Counter[str] = collections.Counter()
    for (competencia, _), quantas in faltando.items():
        por_competencia[competencia] += quantas
    if por_competencia:
        print(f"\nAS COMPETÊNCIAS COM LINHA DIFERENTE ({len(por_competencia)} de "
              f"{len({c for c, _ in do_ma})}):")
        for competencia, quantas in por_competencia.most_common(20):
            print(f"  {competencia}  {quantas:>8,}".replace(",", "."))
        print("\nRode --competencia numa delas para saber qual coluna.")

    divergentes = sorted({p for p in set(ramos_do_ma) | set(nossos_ramos)
                          if ramos_do_ma[p] != nossos_ramos[p]})
    if divergentes:
        print(f"\nCOMPETÊNCIAS E RAMOS COM CONTAGEM DIFERENTE ({len(divergentes)}):")
        for competencia, ramo in divergentes[:40]:
            print(f"  {competencia}  {ramo:<52} MA={ramos_do_ma[(competencia, ramo)]:>9,}  "
                  f"nós={nossos_ramos[(competencia, ramo)]:>9,}".replace(",", "."))
        if len(divergentes) > 40:
            print(f"  … e mais {len(divergentes) - 40}")
    else:
        print("\nA contagem por competência e ramo bate em todas.")
    return 0 if (so_do_ma == 0 and so_nossas == 0) else 1


def conferir_competencia(pasta_sped: str, pasta_ma: str, competencia: str) -> int:
    """Uma competência só, guardando a linha inteira — para saber qual coluna."""
    do_ma = collections.Counter(linhas_do_ma(pasta_ma, competencia))
    nossas = collections.Counter(nossas_linhas(pasta_sped, competencia))
    print(f"{competencia}: gabarito {sum(do_ma.values()):,} linhas, "
          f"nós {sum(nossas.values()):,}".replace(",", "."))

    iguais = sum((do_ma & nossas).values())
    print(f"iguais: {iguais:,}".replace(",", "."))
    sobrando_do_ma = do_ma - nossas
    sobrando_nossas = nossas - do_ma
    if not sobrando_do_ma and not sobrando_nossas:
        print("bate inteiro.")
        return 0

    # para dizer qual coluna divergiu, é preciso saber que linha é qual: o par
    # se acha pela chave do documento mais o que distingue o filho dentro dele
    def chave(linha: tuple[str, ...]) -> tuple[str, ...]:
        # o código do item entra porque é cópia crua do C170 e nunca diverge:
        # sem ele, duas linhas parecidas se emparelham trocadas e a divergência
        # que aparece é a do par errado, não a do defeito
        return (linha[0], linha[2], linha[12] or linha[10] + "/" + linha[11], linha[21],
                linha[22], linha[33], linha[40], linha[29])

    por_chave_do_ma: dict[tuple[str, ...], list[tuple[str, ...]]] = collections.defaultdict(list)
    for linha in sobrando_do_ma.elements():
        por_chave_do_ma[chave(linha)].append(linha)

    colunas_ruins: collections.Counter[str] = collections.Counter()
    exemplos: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    sem_par = 0
    for nossa in sobrando_nossas.elements():
        candidatas = por_chave_do_ma.get(chave(nossa))
        if not candidatas:
            sem_par += 1
            continue
        dela = candidatas.pop()
        for i, (minha, sua) in enumerate(zip(nossa, dela)):
            if minha != sua:
                colunas_ruins[NOSSAS[i]] += 1
                if len(exemplos[NOSSAS[i]]) < 3:
                    exemplos[NOSSAS[i]].append((minha, sua))

    print(f"\nlinhas nossas sem par no gabarito: {sem_par:,}".replace(",", "."))
    print(f"linhas do gabarito sem par nossa:  "
          f"{sum(len(v) for v in por_chave_do_ma.values()):,}".replace(",", "."))
    if colunas_ruins:
        print("\nCOLUNAS QUE DIVERGEM:")
        for coluna, quantas in colunas_ruins.most_common():
            print(f"  {coluna:<30}{quantas:>9,}".replace(",", "."))
            for nosso, dele in exemplos[coluna]:
                print(f"      nosso={nosso!r}  MA={dele!r}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sped", help="pasta com os arquivos da EFD-Contribuições")
    parser.add_argument("ma", help="pasta com os CSV que o MA exportou")
    parser.add_argument("--competencia", help="dd/mm/aaaa — confere só esta, e diz qual coluna")
    args = parser.parse_args()
    if args.competencia:
        return conferir_competencia(args.sped, args.ma, args.competencia)
    return conferir_tudo(args.sped, args.ma)


if __name__ == "__main__":
    sys.exit(main())
