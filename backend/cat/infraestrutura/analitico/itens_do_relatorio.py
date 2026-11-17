"""O item de saída que a EFD não traz — quando não há XML, vem do relatório do cliente.

A EFD não pede o item do documento de emissão própria: NF-e, NFC-e e CF-e vão à
escrituração só com o analítico (C190/C850), total por CST e CFOP. Medido na
empresa 17, matriz, janeiro de 2026: **100.269 saídas e nenhum C170**; a entrada
de terceiros, no mesmo arquivo, traz 8,3 itens por documento.

Até aqui o item de saída só tinha uma porta: o XML (`itens_do_xml.py`). Ela não
serve a quem não guardou XML — na empresa 17 há 7,4 mil arquivos para 13,8
milhões de documentos escriturados. O relatório do ERP faz o mesmo trabalho, e
é o que essas empresas têm: 217 arquivos cobrem a saída de 2026 inteira, item a
item, com chave.

**Este módulo é essa segunda porta, e é estreita de propósito.** Ele só grava a
linha que tem chave de 44 dígitos, porque é a chave que liga o item ao
documento que a EFD escriturou — é o mesmo encaixe do XML, e por isso o
estabelecimento, a data, o modelo e a situação continuam vindo da EFD, que é a
escrituração. O relatório entra como item, nunca como documento: linha de
relatório sem chave (total, rodapé, movimentação interna) é contada e fica de
fora.

**O XML ganha do relatório.** Quando os dois cobrem o mesmo documento, vale o
XML: ele é o que foi autorizado pela SEFAZ, e o relatório é o que o ERP diz. A
escolha é feita em `movimentacao.py`, onde as duas pernas se encontram.

**Uma cópia por chave.** O cliente reexporta: na empresa 17, a remessa de
13/11 repete 3,3 milhões das 5,5 milhões de chaves que já estavam nos 217
arquivos. A escolha de qual cópia fica é feita em SQL, por `(chave, arquivo)`,
e não com um conjunto de chaves em memória — 13,8 milhões de chaves num `set`
de Python passam de 1,5 GB, e o DuckDB resolve derramando em disco.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import pyarrow as pa

from cat.infraestrutura.analitico.extracao import Aviso, Progresso, _Escritor
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ITENS_DO_RELATORIO = "itens_do_relatorio.parquet"

CENTAVOS = Decimal("0.01")
QUANTIDADE = Decimal("0.00001")
ALIQUOTA = Decimal("0.0001")

# As colunas são as que o movimento precisa, e só elas. O relatório do ERP tem
# dezenas de outras (PIS, COFINS, reforma, cadastro do cliente); o que entra
# aqui é o que a Ficha 3 e o de-para leem.
ESQUEMA_ITENS_DO_RELATORIO = pa.schema([
    # a ligação com a EFD, e de qual arquivo a linha veio — é o par que decide
    # qual cópia fica quando o cliente reexporta o mesmo documento
    ("chave", pa.string()),
    ("arquivo", pa.string()),
    # a ordem do item dentro do documento, contada na leitura: o relatório não
    # numera. Serve para o item ter identidade, como o nItem do XML
    ("numero_item", pa.int32()),
    ("codigo", pa.string()),
    ("gtin", pa.string()),
    ("descricao", pa.string()),
    ("ncm", pa.string()),
    ("cfop", pa.string()),
    ("unidade", pa.string()),
    ("quantidade", pa.decimal128(20, 5)),
    ("valor", pa.decimal128(18, 2)),
    ("cst_icms", pa.string()),
    ("bc_icms", pa.decimal128(18, 2)),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("valor_icms", pa.decimal128(18, 2)),
    ("bc_st", pa.decimal128(18, 2)),
    ("valor_st", pa.decimal128(18, 2)),
])

TAMANHO_DA_CHAVE = 44
# quantas linhas inválidas vão ao log com o motivo: o bastante para reconhecer
# o defeito, longe de encher o log com milhões de linhas iguais
AMOSTRA_DE_INVALIDOS = 20


@dataclass
class ProgressoDoRelatorio(Progresso):
    """O `Progresso` de sempre mais o que a leitura dos relatórios conta."""

    itens: int = 0
    # linha de item sem chave de 44 dígitos: total, rodapé, movimentação
    # interna, ou chave que passou pelo Excel e voltou em notação científica.
    # Não é defeito do leitor, e também não entra — fica contada
    sem_chave: int = 0
    # linha de item sem CFOP: não se sabe se entrou ou saiu, e o movimento não
    # classifica. Mesma exigência que o registro montado fazia
    sem_cfop: int = 0
    # número ou CFOP que não converte
    invalidos: int = 0
    # arquivo que não é de movimento (inventário, resumo) ou que não abriu
    nao_sao_movimento: int = 0
    ilegiveis: int = 0
    documentos: int = 0


def _q(valor: Decimal | None, casas: Decimal) -> Decimal | None:
    """O decimal na escala do parquet. ``None`` continua ``None``.

    Sem isto o pyarrow recusa a tabela inteira por causa de uma linha com mais
    casas que o esquema — e o relatório do ERP traz unitário com seis casas.
    """
    if valor is None:
        return None
    return valor.quantize(casas, rounding=ROUND_HALF_UP)


def extrair_itens_do_relatorio(
    relatorios: list[str],
    destino: str,
    avisar: Aviso | None = None,
    progresso: ProgressoDoRelatorio | None = None,
) -> ProgressoDoRelatorio:
    """Grava `itens_do_relatorio.parquet` em `destino`: um registro por linha de item com chave.

    Um relatório por vez, gravando em blocos — a base da empresa 17 tem 111
    milhões de linhas em 46 GB, e acumular em memória não cabe.
    """
    # importado aqui, e não no topo, pela mesma razão dos outros casos: o
    # domínio do gerencial carrega o catálogo de campos, e quem só precisa do
    # esquema não paga por ele
    from cat.infraestrutura.arquivos.gerencial import Leitura

    os.makedirs(destino, exist_ok=True)
    progresso = progresso or ProgressoDoRelatorio(arquivos_totais=len(relatorios))
    caminho = os.path.join(destino, ARQUIVO_ITENS_DO_RELATORIO)
    escritor = _Escritor(caminho, ESQUEMA_ITENS_DO_RELATORIO)
    try:
        for origem in relatorios:
            nome = os.path.basename(origem)
            try:
                leitura = Leitura(origem)
                if not leitura.especie.serve_para_razao:
                    progresso.nao_sao_movimento += 1
                    log.info("relatório não é de movimento, sem item para extrair",
                             extra={"arquivo": nome, "especie": leitura.especie.value})
                    continue
                _ler_um(leitura, nome, escritor, progresso)
            # `RelatorioIlegivel` é um `ValueError`: entra aqui
            except (OSError, ValueError) as erro:
                progresso.ilegiveis += 1
                progresso.recusados.append(f"{nome}: {erro}")
                log.warning("relatório ilegível na extração de itens",
                            extra={"arquivo": nome, "motivo": str(erro)})
            finally:
                progresso.arquivos_lidos += 1
                if avisar is not None:
                    avisar(progresso)
    finally:
        escritor.fechar()

    log.info("itens dos relatórios extraídos",
             extra={"arquivos": progresso.arquivos_lidos,
                    "itens": progresso.itens,
                    "documentos": progresso.documentos,
                    "sem_chave": progresso.sem_chave,
                    "sem_cfop": progresso.sem_cfop,
                    "invalidos": progresso.invalidos,
                    "nao_sao_movimento": progresso.nao_sao_movimento,
                    "ilegiveis": progresso.ilegiveis})
    return progresso


# (coluna do parquet, chave do campo, escala) — os seis números que a ficha e o
# de-para leem. O relatório tem dezenas de outros (PIS, COFINS, IPI, reforma);
# converter o que não se usa é o que fazia esta leitura custar seis vezes mais
_NUMEROS = (
    ("quantidade", "quantidade", QUANTIDADE),
    ("valor", "valor_item", CENTAVOS),
    ("bc_icms", "bc_icms", CENTAVOS),
    ("aliq_icms", "aliquota_icms", ALIQUOTA),
    ("valor_icms", "valor_icms", CENTAVOS),
    ("bc_st", "bc_st", CENTAVOS),
    ("valor_st", "valor_st", CENTAVOS),
)
_TEXTOS = (
    ("codigo", "codigo_item"), ("gtin", "codigo_barras"),
    ("descricao", "descricao_item"), ("ncm", "ncm"),
    ("unidade", "unidade_medida"), ("cst_icms", "cst_icms"),
)


def _ler_um(leitura, nome: str, escritor: _Escritor, p: ProgressoDoRelatorio) -> None:
    """As linhas de um relatório, numerando o item dentro de cada documento.

    **Lê o texto cru (`brutos`), e não o registro montado (`movimentos`).** É o
    mesmo caminho do confronto, e pelo mesmo motivo: montar
    `MovimentoGerencial` converte vinte campos por linha — data, CFOP, CNPJ,
    PIS, COFINS, ST do XML, retido anterior —, e deste módulo só sete números
    e seis textos são usados. Medido na empresa 17, loja 02: 1,31 milhão de
    linhas em 110 s pelo registro montado (3,3 MB/s), contra os 19,6 MB/s que o
    confronto faz nos mesmos arquivos. Na base inteira a diferença é de quase
    quatro horas.

    O contador do item é por arquivo, e isso basta: o relatório vem por
    estabelecimento e mês, e as linhas de um documento saem juntas. Um
    documento que apareça em dois arquivos é resolvido depois, escolhendo um
    arquivo por chave — não aqui, somando itens de dois lugares no mesmo
    documento.
    """
    from cat.dominio.gerencial import valores as v

    numero: dict[str, int] = {}
    antes = p.itens
    for _linha, dados in leitura.brutos():
        chave = (dados.get("chave") or "").strip()
        if len(chave) != TAMANHO_DA_CHAVE or not chave.isdigit():
            # linha de total e de rodapé não tem código: não é item, e o
            # leitor do gerencial já a conta como descarte. O que se conta
            # aqui é o item de verdade cuja chave não serve
            if (dados.get("codigo_item") or "").strip():
                p.sem_chave += 1
            continue
        try:
            # sem CFOP não se sabe se entrou ou saiu, e o movimento não
            # classifica: é a mesma exigência que o registro montado fazia,
            # e a linha fica contada em vez de virar movimento sem lado
            cfop = v.cfop(dados.get("cfop"))
            if cfop is None:
                p.sem_cfop += 1
                continue
            linha = {"chave": chave, "arquivo": nome, "cfop": cfop}
            for coluna, campo in _TEXTOS:
                linha[coluna] = v.texto(dados.get(campo)) or None
            for coluna, campo, escala in _NUMEROS:
                linha[coluna] = _q(v.decimal(dados.get(campo), campo=campo), escala)
        except v.ValorInvalido as erro:
            # número ou CFOP que não converte. Um punhado é dado ruim; muitos
            # seriam mapeamento errado — e aí o confronto, que lê os mesmos
            # arquivos, recusa o relatório antes desta etapa
            p.invalidos += 1
            if p.invalidos <= AMOSTRA_DE_INVALIDOS:
                log.warning("linha de item inválida no relatório",
                            extra={"arquivo": nome, "linha": _linha, "motivo": str(erro)})
            continue
        linha["numero_item"] = numero[chave] = numero.get(chave, 0) + 1
        escritor.acrescentar(linha)
        p.itens += 1
    p.documentos += len(numero)
    p.bytes_lidos += _tamanho(leitura.inspecao.caminho)
    log.info("itens de um relatório",
             extra={"arquivo": nome, "itens": p.itens - antes,
                    "documentos": len(numero), "especie": leitura.especie.value})


def _tamanho(caminho: str) -> int:
    try:
        return os.path.getsize(caminho)
    except OSError:
        return 0
