"""Conferir a nossa Consulta de Entradas contra o gabarito do MA, linha a linha.

A gêmea de `validar_047.py`, e não uma cópia dela: o gabarito do 037 veio em
**xlsx**, e xlsx guarda número como número. Onde o CSV do 047 dizia `"1.234,56"`
e bastava comparar texto, aqui vem `1234.56` — e `40652.97`, e `7.6`, e `106`.
Comparar texto contra texto reprovaria a planilha inteira por causa do zero à
direita que o Excel não guarda.

## As três diferenças que o formato impõe

1. **O valor se compara como número.** As colunas de dinheiro, alíquota e
   quantidade passam por `Decimal` dos dois lados; o resto continua texto;
2. **O gabarito é lido de um parquet local**, convertido uma vez do xlsx. Foram
   216 s para percorrer o xlsx uma vez, e a conferência o percorre dezenas de
   vezes — ver `--converter`;
3. **Uma coluna de cada lado não tem par.** A nossa 037 traz `Município do
   Participante`, acrescentado em v0.76.0 ao lado da UF, que o MA não tem; o MA
   traz `Código Serviço`, que veio do 0200. A comparação ignora a nossa e cobra
   a dele — as duas ausências estão nomeadas em `SO_NOSSA` e no mapa.

## Como

    python tools/validar_037.py --converter <xlsx do MA> <parquet destino>
    python tools/validar_037.py <pasta dos SPED> <parquet do gabarito>
    python tools/validar_037.py <pasta> <parquet> --competencia 01/10/2024

**Não versiona dado de cliente.** Recebe os caminhos por argumento e imprime
nomes de coluna, contagens e, no modo detalhado, no máximo três exemplos por
coluna divergente.
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
import time
from decimal import Decimal, InvalidOperation

import pyarrow.parquet as pq

from cat.infraestrutura.sped.entradas import colunas_da_entrada, entradas
from cat.infraestrutura.sped.leitor import codificacao_de

# a coluna do MA e o nosso campo que responde por ela, na ordem em que o MA
# exporta. `None` é coluna que ainda não temos
MAPA: tuple[tuple[str, str | None], ...] = (
    ("CNPJ", "cnpj"),
    ("Período", "periodo"),
    ("Registros", "registros"),
    ("Modelo", "modelo"),
    ("Situação", "situacao"),
    ("Código Participante", "codigo_do_participante"),
    ("CNPJ Participante", "cnpj_do_participante"),
    ("CPF Participante", "cpf_do_participante"),
    ("Nome Participante", "nome_do_participante"),
    ("UF Origem/Destino", "uf_origem_destino"),
    ("Número Documento", "numero_do_documento"),
    ("Série", "serie"),
    ("Chave NF-e", "chave"),
    ("Data Documento", "data_do_documento"),
    ("Data Entrada/Saída", "data_de_entrada"),
    ("Vlr Documento", "valor_do_documento"),
    ("Vlr Desconto NF", "desconto_do_documento"),
    ("Vlr Mercadoria/Operação", "valor_da_mercadoria"),
    ("Vlr Frete", "frete"),
    ("Número Item", "numero_do_item"),
    ("Código Item", "codigo_do_item"),
    ("Descrição Complementar", "descricao_complementar"),
    ("Descrição Item", "descricao_do_item"),
    ("NCM", "ncm"),
    ("Código Serviço", "codigo_do_servico"),
    ("Código Barra", "codigo_de_barra"),
    ("Tipo Item", "tipo_do_item"),
    ("Vlr Item", "valor_do_item"),
    ("Qtde", "quantidade"),
    ("Unidade Medida", "unidade"),
    ("Vlr Desconto Item", "desconto_do_item"),
    ("Natureza Crédito", "natureza_do_credito"),
    ("CFOP", "cfop"),
    ("Descrição CFOP", "descricao_do_cfop"),
    ("Vlr ICMS", "icms"),
    ("Vlr ICMS-ST", "icms_st"),
    ("Vlr IPI", "ipi"),
    ("CST PIS", "cst_pis"),
    ("Vlr Base Cálculo PIS", "base_do_pis"),
    ("Qtde Base Cálculo PIS", "quantidade_base_do_pis"),
    ("Alíquota PIS", "aliquota_do_pis"),
    ("Qtde Alíquota PIS", "quantidade_aliquota_do_pis"),
    ("Vlr PIS", "pis"),
    ("CST Cofins", "cst_cofins"),
    ("Vlr Base Cálculo Cofins", "base_da_cofins"),
    ("Qtde Base Cálculo Cofins", "quantidade_base_da_cofins"),
    ("Alíquota Cofins", "aliquota_da_cofins"),
    ("Qtde Alíquota Cofins", "quantidade_aliquota_da_cofins"),
    ("Vlr Cofins", "cofins"),
    ("Conta Contábil", "conta_contabil"),
    ("Nome Contábil", "nome_da_conta"),
    ("deb_cred", "debito_ou_credito"),
)

COLUNAS_DO_MA = tuple(coluna for coluna, _ in MAPA)
NOSSAS = tuple(campo for _, campo in MAPA)

# o que é nosso e não tem par no gabarito. Fica fora da comparação, e fica
# escrito aqui para ninguém procurar depois por que a conta não fecha
SO_NOSSA = ("municipio_do_participante",)

# as colunas em que `40652.97` e `40.652,97` são o mesmo número. Fora daqui, a
# comparação é de texto: código de item, CST e CFOP têm zero à esquerda que
# significa coisa, e transformá-los em número os destruiria
NUMERICAS = frozenset({
    "valor_do_documento", "desconto_do_documento", "valor_da_mercadoria", "frete",
    "valor_do_item", "quantidade", "desconto_do_item",
    "icms", "icms_st", "ipi",
    "base_do_pis", "quantidade_base_do_pis", "aliquota_do_pis",
    "quantidade_aliquota_do_pis", "pis",
    "base_da_cofins", "quantidade_base_da_cofins", "aliquota_da_cofins",
    "quantidade_aliquota_da_cofins", "cofins",
})


def numero(bruto: str) -> Decimal | None:
    """O valor como número, ou `None` quando não é número nenhum.

    Aceita as duas escritas: a do xlsx (`1234.56`) e a nossa (`1.234,56`).
    Vazio é vazio, e não zero: a 037 deixa em branco o campo que o arquivo não
    trouxe, e confundir os dois esconderia justamente a diferença entre "não
    informado" e "informado como zero".
    """
    texto = (bruto or "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def como_o_ma_leria(texto: str) -> str:
    """O texto como o MA o teria lido — e ele lê a EFD errado.

    **O arquivo é cp1252 e o MA o decodifica como latin-1.** As duas só diferem
    na faixa 0x80–0x9F, mas é ali que moram as aspas tipográficas: o byte 0x92,
    que em cp1252 é o apóstrofo `’`, no latin-1 é caractere de controle. O
    participante "STELLA D’ORO" aparece no gabarito com um caractere de controle
    no meio do nome.

    Quem está certo somos nós — o leiaute da EFD é cp1252 —, e é por isso que a
    normalização acontece **deste lado**: o conferidor reproduz o defeito do
    gabarito para não acusar divergência onde não há. São 10 linhas em 458.792,
    todas de nome de participante.
    """
    try:
        return texto.encode("cp1252").decode("latin-1")
    except UnicodeEncodeError:
        return texto


def comparavel(campo: str, valor: str) -> str:
    """O valor na forma em que os dois lados podem ser comparados."""
    if campo not in NUMERICAS:
        return como_o_ma_leria((valor or "").strip())
    n = numero(valor)
    return "" if n is None else format(n.normalize(), "f")


def linhas_do_ma(parquet: str, competencia: str | None):
    """As linhas do gabarito, já na ordem e na forma comparável."""
    tabela = pq.read_table(parquet)
    faltam = set(COLUNAS_DO_MA) - set(tabela.column_names)
    if faltam:
        raise SystemExit(f"o parquet do gabarito não tem: {sorted(faltam)}")
    colunas = [tabela.column(nome).to_pylist() for nome in COLUNAS_DO_MA]
    onde_periodo = COLUNAS_DO_MA.index("Período")
    for i in range(tabela.num_rows):
        if competencia is not None and colunas[onde_periodo][i] != competencia:
            continue
        yield tuple(comparavel(NOSSAS[j], colunas[j][i] or "")
                    for j in range(len(COLUNAS_DO_MA)))


def nossas_linhas(pasta: str, competencia: str | None):
    """As nossas, de todos os SPED da pasta — ou de um arquivo só."""
    arquivos = ([pasta] if os.path.isfile(pasta)
                else sorted(glob.glob(os.path.join(pasta, "*.txt"))))
    if not arquivos:
        raise SystemExit(f"nenhum SPED em {pasta}")
    temos = set(colunas_da_entrada())
    for caminho in arquivos:
        for linha in entradas(caminho, codificacao_de(caminho)):
            valores = linha.como_dicionario()
            if competencia is not None and valores["periodo"] != competencia:
                continue
            yield tuple(comparavel(campo, valores.get(campo, "") if campo in temos else "")
                        for campo in NOSSAS)


def conferir_tudo(pasta_sped: str, parquet: str) -> int:
    print("lendo o gabarito…", flush=True)
    inicio = time.time()
    do_ma: collections.Counter[tuple[str, int]] = collections.Counter()
    ramos_do_ma: collections.Counter[tuple[str, str]] = collections.Counter()
    for linha in linhas_do_ma(parquet, None):
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
    total = sum(do_ma.values())
    print(f"\n{'IGUAIS':<12}{iguais:>12,}  {100 * iguais / max(total, 1):.4f}% do gabarito"
          .replace(",", "."))
    print(f"{'SÓ DO MA':<12}{sum(faltando.values()):>12,}  o gabarito tem e nós não"
          .replace(",", "."))
    print(f"{'SÓ NOSSAS':<12}{sum(sobrando.values()):>12,}  geramos a mais".replace(",", "."))

    por_competencia: collections.Counter[str] = collections.Counter()
    for (competencia, _), quantas in faltando.items():
        por_competencia[competencia] += quantas
    if por_competencia:
        print(f"\nCOMPETÊNCIAS COM LINHA DIFERENTE ({len(por_competencia)} de "
              f"{len({c for c, _ in do_ma})}):")
        for competencia, quantas in por_competencia.most_common(20):
            print(f"  {competencia}  {quantas:>8,}".replace(",", "."))

    divergentes = sorted({p for p in set(ramos_do_ma) | set(nossos_ramos)
                          if ramos_do_ma[p] != nossos_ramos[p]})
    if divergentes:
        print(f"\nRAMOS COM CONTAGEM DIFERENTE ({len(divergentes)}):")
        for competencia, ramo in divergentes[:30]:
            print(f"  {competencia}  {ramo:<52} MA={ramos_do_ma[(competencia, ramo)]:>8,}  "
                  f"nós={nossos_ramos[(competencia, ramo)]:>8,}".replace(",", "."))
        if len(divergentes) > 30:
            print(f"  … e mais {len(divergentes) - 30}")
    else:
        print("\nA contagem por competência e ramo bate em todas.")
    return 0 if not faltando and not sobrando else 1


def conferir_competencia(pasta_sped: str, parquet: str, competencia: str) -> int:
    do_ma = collections.Counter(linhas_do_ma(parquet, competencia))
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

    def chave(l: tuple[str, ...]) -> tuple[str, ...]:
        # CNPJ, ramo, documento, item, código do item, CFOP e CST: o bastante
        # para o par ser o mesmo item da mesma nota
        return (l[0], l[2], l[12] or l[10] + "/" + l[11], l[19], l[20], l[32], l[37])

    por_chave: dict[tuple[str, ...], list[tuple[str, ...]]] = collections.defaultdict(list)
    for linha in sobrando_do_ma.elements():
        por_chave[chave(linha)].append(linha)

    colunas_ruins: collections.Counter[str] = collections.Counter()
    exemplos: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    sem_par = 0
    for nossa in sobrando_nossas.elements():
        candidatas = por_chave.get(chave(nossa))
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
          f"{sum(len(v) for v in por_chave.values()):,}".replace(",", "."))
    if colunas_ruins:
        print("\nCOLUNAS QUE DIVERGEM:")
        for coluna, quantas in colunas_ruins.most_common():
            print(f"  {coluna:<30}{quantas:>9,}".replace(",", "."))
            for nosso, dele in exemplos[coluna]:
                print(f"      nosso={nosso!r}  MA={dele!r}")
    return 1


def converter(xlsx: str, destino: str) -> int:
    """O xlsx do MA vira parquet local, uma vez só.

    Percorrer o xlsx leva minutos e a conferência o percorre dezenas de vezes.
    O valor vai como **texto cru**, do jeito que o Excel guardou: a normalização
    acontece à vista, em `comparavel`, e não escondida aqui.
    """
    import warnings

    import openpyxl
    import pyarrow as pa

    warnings.filterwarnings("ignore")

    def texto(v) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    inicio = time.time()
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    # o xlsx do MA não declara as dimensões: sem isto, o openpyxl lê uma coluna
    ws.reset_dimensions()
    linhas = ws.iter_rows(values_only=True)
    cabecalho = [texto(c) for c in next(linhas)]
    colunas: dict[str, list[str]] = {nome: [] for nome in cabecalho}
    for bruta in linhas:
        for i, nome in enumerate(cabecalho):
            colunas[nome].append(texto(bruta[i]) if i < len(bruta) else "")
    pa_tabela = pa.table({k: pa.array(v, type=pa.string()) for k, v in colunas.items()})
    pq.write_table(pa_tabela, destino)
    print(f"{pa_tabela.num_rows:,} linhas em {time.time() - inicio:.0f}s -> {destino}"
          .replace(",", "."))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origem", help="pasta dos SPED — ou o xlsx, com --converter")
    parser.add_argument("gabarito", help="parquet do gabarito — ou o destino, com --converter")
    parser.add_argument("--competencia", help="dd/mm/aaaa — confere só esta, e diz qual coluna")
    parser.add_argument("--converter", action="store_true",
                        help="converte o xlsx do MA para parquet e sai")
    args = parser.parse_args()
    if args.converter:
        return converter(args.origem, args.gabarito)
    if args.competencia:
        return conferir_competencia(args.origem, args.gabarito, args.competencia)
    return conferir_tudo(args.origem, args.gabarito)


if __name__ == "__main__":
    sys.exit(main())
