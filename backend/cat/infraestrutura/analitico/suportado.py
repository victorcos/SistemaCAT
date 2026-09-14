"""Apura o ICMS suportado de cada item de entrada, juntando as fontes.

A regra de qual fonte vale está em `cat.dominio.cat42.suportado`. Aqui é a
parte suja: ler o relatório do cliente, casar com a EFD e gravar o resultado.

## Por que o relatório do cliente é indispensável

A EFD não tem o número em 99% dos itens. Medido na base real de 2021, com
8.761.002 itens de entrada, só 0,92% têm ICMS-ST destacado — e não é defeito do
arquivo: 42% das entradas são CST 60, mercadoria cujo imposto foi retido antes,
em que o remetente não destaca nada.

O relatório gerencial de entradas fecha esse buraco. Medido em 2021-05, um mês
inteiro com as três praças:

| | |
|---|---|
| Itens da EFD que casam por (chave, código) | 93,57% |
| Com imposto informado | 42,53% |
| CST 60 que casa | 94,2% |
| CST 60 com imposto informado | 92,7% |

Ou seja: o caso que a EFD zera é justamente o que o relatório preenche.

## A chave da junção

`(chave de acesso, código do item)`. A chave sozinha não serve — uma nota tem
muitos itens — e o código sozinho muito menos. Na base medida, 99,99% dos itens
de entrada da EFD têm chave de 44 dígitos e 99,83% das linhas do relatório
também, então a junção não perde quase nada por falta de chave.

## Quem soma o quê

O valor que o relatório informa **já vem somado pelo domínio do gerencial**:
`MovimentoGerencial.imposto_suportado` escolhe entre XML, ERP e retido
anteriormente, e sabe que no retido anterior não se soma o ICMS da operação —
a mercadoria já veio tributada, e somar contaria imposto que não é dela.
Refazer essa conta aqui seria ter duas verdades.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.suportado import (
    EntradaParaApurar,
    Fonte,
    ResumoDaApuracao,
    apurar as apurar_item,
)
from cat.infraestrutura.analitico.confronto import _abrir, _escapar
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_RETIDO = "retido_informado.parquet"
ARQUIVO_SUPORTADO = "suportado.parquet"

LINHAS_POR_LOTE = 200_000

# seis casas, não duas. O relatório do cliente traz ICMS com quatro casas
# ("2,3341" numa linha real), e um esquema de duas casas não grava esse valor:
# o pyarrow recusa com "Rescaling Decimal value would cause data loss". Truncar
# em silêncio seria pior — são centavos somados em milhões de itens.
ESQUEMA_RETIDO = pa.schema([
    ("chave", pa.string()),
    ("codigo", pa.string()),
    ("informado", pa.decimal128(18, 6)),
])

ESQUEMA_SUPORTADO = pa.schema([
    ("cnpj", pa.string()),
    ("competencia", pa.date32()),
    ("chave", pa.string()),
    ("codigo", pa.string()),
    ("cst_icms", pa.string()),
    ("quantidade", pa.decimal128(18, 5)),
    ("suportado", pa.decimal128(18, 6)),   # ver a nota do ESQUEMA_RETIDO
    ("fonte", pa.string()),
    ("motivo", pa.string()),
])


def extrair_retido(relatorios: list[str], destino: str) -> int:
    """Lê os relatórios do cliente e grava o imposto informado por item.

    Só entradas: a saída não carrega imposto suportado, ela o consome. E só
    linha com chave de 44 dígitos, porque sem chave não há como casar com a
    EFD — a linha existe, mas não serve a esta junção.

    Agrega por (chave, código) porque o mesmo item pode aparecer em mais de
    uma linha do relatório, e o que vale para a ficha é o total do item
    naquele documento.
    """
    from cat.dominio.gerencial.campos import Especie
    from cat.infraestrutura.arquivos.gerencial import Leitura

    acumulado: dict[tuple[str, str], Decimal] = {}
    lidos = recusados = sem_chave = 0

    for caminho in relatorios:
        nome = os.path.basename(caminho)
        try:
            leitura = Leitura(caminho)
            if leitura.especie is not Especie.MOVIMENTO:
                recusados += 1
                log.warning("relatório não é de movimento, ignorado na apuração",
                            extra={"arquivo": nome, "especie": leitura.especie.value})
                continue
            for m in leitura.movimentos():
                if not m.e_entrada:
                    continue
                lidos += 1
                chave = (m.chave or "").strip()
                if len(chave) != 44 or not chave.isdigit():
                    sem_chave += 1
                    continue
                valor = m.imposto_suportado
                if valor <= 0:
                    continue
                alvo = (chave, (m.codigo_item or "").strip())
                acumulado[alvo] = acumulado.get(alvo, Decimal(0)) + valor
        except (OSError, ValueError) as erro:
            recusados += 1
            log.warning("relatório ilegível na apuração do suportado",
                        extra={"arquivo": nome, "motivo": str(erro)})

    _gravar_retido(acumulado, destino)
    log.info("imposto informado pelo cliente extraído",
             extra={"arquivos": len(relatorios), "recusados": recusados,
                    "linhas_de_entrada": lidos, "sem_chave": sem_chave,
                    "itens": len(acumulado)})
    return len(acumulado)


def _gravar_retido(acumulado: dict, destino: str) -> None:
    """Grava sempre, mesmo vazio: parquet ausente e parquet sem linha dizem
    coisas diferentes, e a apuração precisa distinguir 'não rodou' de 'rodou
    e o cliente não informou nada'."""
    itens = list(acumulado.items())
    escritor = pq.ParquetWriter(destino, ESQUEMA_RETIDO)
    try:
        for i in range(0, len(itens), LINHAS_POR_LOTE):
            fatia = itens[i:i + LINHAS_POR_LOTE]
            escritor.write_table(pa.Table.from_pydict({
                "chave": [c for (c, _), _ in fatia],
                "codigo": [k for (_, k), _ in fatia],
                "informado": [v for _, v in fatia],
            }, schema=ESQUEMA_RETIDO))
    finally:
        escritor.close()


def apurar(pasta: str) -> ResumoDaApuracao:
    """Cruza EFD, imposto informado e cadastro, e grava o suportado por item.

    A alíquota interna vem do 0200 do próprio estabelecimento, que é o único
    lugar onde ela existe por item. Serve à terceira fonte da cascata, a
    reconstrução — que na base medida não salvou nada, porque a BC ST também
    vem zerada no CST 60, mas existe para o cliente cujo arquivo a traga.
    """
    movimentos = os.path.join(pasta, ARQUIVO_MOVIMENTOS)
    retido = os.path.join(pasta, ARQUIVO_RETIDO)
    cadastro = os.path.join(pasta, ARQUIVO_ITENS)
    destino = os.path.join(pasta, ARQUIVO_SUPORTADO)

    if not os.path.isfile(movimentos):
        raise FileNotFoundError(
            f"{ARQUIVO_MOVIMENTOS} não está em {pasta}: a etapa de movimentação "
            "precisa ter rodado antes."
        )

    con = _abrir(pasta)
    try:
        con.execute(f"""
            CREATE OR REPLACE VIEW entradas AS
            SELECT m.cnpj, m.competencia, m.chave, m.codigo, m.cst_icms,
                   m.quantidade, m.valor_icms, m.valor_st, m.bc_st,
                   {'r.informado' if os.path.isfile(retido) else 'NULL'} AS informado,
                   {'i.aliq_icms' if os.path.isfile(cadastro) else 'NULL'} AS aliquota
            FROM read_parquet('{_escapar(movimentos)}') m
            {f"LEFT JOIN read_parquet('{_escapar(retido)}') r"
             " ON m.chave = r.chave AND m.codigo = r.codigo"
             if os.path.isfile(retido) else ""}
            {f"LEFT JOIN read_parquet('{_escapar(cadastro)}') i"
             " ON m.cnpj = i.cnpj AND m.codigo = i.codigo"
             if os.path.isfile(cadastro) else ""}
            WHERE m.operacao = 'entrada'
        """)
        resumo = _percorrer(con, destino)
    finally:
        con.close()

    log.info("ICMS suportado apurado",
             extra={"itens": resumo.itens, "apurados": resumo.itens_apurados,
                    "cobertura": round(resumo.cobertura, 4),
                    "valor": str(resumo.valor_total),
                    "documental": str(resumo.valor_documental),
                    "por_fonte": {f.value: n for f, n in resumo.por_fonte.items()}})
    return resumo


def _percorrer(con, destino: str) -> ResumoDaApuracao:
    """Aplica a regra do domínio linha a linha e grava o parquet.

    Linha a linha, e não em SQL: a cascata é regra fiscal e mora no domínio.
    Reescrevê-la em SQL daria duas versões dela, que é como se começa a
    divergir sem ninguém perceber.
    """
    resumo = ResumoDaApuracao()
    escritor = pq.ParquetWriter(destino, ESQUEMA_SUPORTADO)
    lote = _LoteVazio()
    try:
        leitor = con.execute("SELECT * FROM entradas").to_arrow_reader(
            LINHAS_POR_LOTE)
        for bloco in leitor:
            d = bloco.to_pydict()
            for i in range(bloco.num_rows):
                r = apurar_item(EntradaParaApurar(
                    cst_icms=d["cst_icms"][i] or "",
                    valor_icms=d["valor_icms"][i] or Decimal(0),
                    valor_st=d["valor_st"][i] or Decimal(0),
                    bc_st=d["bc_st"][i] or Decimal(0),
                    retido_informado=d["informado"][i],
                    aliquota_interna=d["aliquota"][i],
                ))
                resumo.somar(r)
                lote.acrescentar(d, i, r)
            if lote.cheio:
                escritor.write_table(lote.tabela())
                lote = _LoteVazio()
        if lote.tem:
            escritor.write_table(lote.tabela())
    finally:
        escritor.close()
    return resumo


class _LoteVazio:
    """Acumula linhas e vira tabela de uma vez: escrever de linha em linha
    num parquet de milhões de itens custa mais que o cálculo inteiro."""

    def __init__(self) -> None:
        self.colunas: dict[str, list] = {c: [] for c in ESQUEMA_SUPORTADO.names}

    def acrescentar(self, d: dict, i: int, r) -> None:
        self.colunas["cnpj"].append(d["cnpj"][i])
        self.colunas["competencia"].append(d["competencia"][i])
        self.colunas["chave"].append(d["chave"][i])
        self.colunas["codigo"].append(d["codigo"][i])
        self.colunas["cst_icms"].append(d["cst_icms"][i])
        self.colunas["quantidade"].append(d["quantidade"][i])
        self.colunas["suportado"].append(r.valor)
        self.colunas["fonte"].append(r.fonte.name.lower())
        self.colunas["motivo"].append(r.motivo)

    @property
    def tem(self) -> bool:
        return bool(self.colunas["chave"])

    @property
    def cheio(self) -> bool:
        return len(self.colunas["chave"]) >= LINHAS_POR_LOTE

    def tabela(self) -> pa.Table:
        return pa.Table.from_pydict(self.colunas, schema=ESQUEMA_SUPORTADO)


def fatias_por_fonte(resumo: ResumoDaApuracao) -> list[dict]:
    """O recorte que a tela mostra: quantos itens e quanto valor por fonte."""
    return [
        {"codigo": f.name.lower(), "rotulo": f.rotulo,
         "quantidade": resumo.por_fonte[f],
         "valor": resumo.valor_por_fonte[f]}
        for f in Fonte if resumo.por_fonte[f]
    ]
