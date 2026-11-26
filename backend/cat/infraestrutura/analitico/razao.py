"""Monta a Ficha 3 de cada mercadoria, juntando as fontes da movimentação.

A regra — custo médio ponderado móvel, entradas antes das saídas no dia,
ressarcimento e complemento — está em `cat.dominio.icms.cat42.razao`, e foi
conferida contra a Ficha 3 já calculada de um cliente, 100% das linhas. Aqui é
a parte suja: achar os movimentos, dizer de qual loja e de qual enquadramento
cada um é, e percorrer.

## De onde vem cada lado da ficha

| Lado | Fonte | Por quê |
|---|---|---|
| Entrada | apuração da etapa 4 | é onde está o ICMS suportado de cada item |
| Saída com item na EFD | movimentação da etapa 3 | documento fiscal: vence o relatório |
| Saída sem item na EFD, com XML | movimentação da etapa 3 (`origem` = xml) | o item do documento: vence o relatório |
| Saída sem item em lugar nenhum | relatório de saídas do cliente | cupom e NFC-e vão à EFD só com o analítico |
| Abertura | bloco H da EFD | o inventário do dia anterior ao período |

Na empresa 19, 36,5 milhões de documentos de saída não têm item na EFD, e a venda
com item é R$ 6 milhões contra R$ 5,8 bilhões. Sem o relatório não há saída a
lançar. O XML, quando vem, entra pela etapa 3 e vence o relatório (v0.53).

## Quais mercadorias

Entra no razão o código que teve **saída com CST 60** em qualquer loja do
período: é a mercadoria vendida com o imposto já retido, que é a matéria da
CAT 42. Mercadoria de CST 00 ou 20 tem imposto próprio, não suportado, e fica
de fora — decisão de 15/09/2026, depois de medir que ela respondia por 54% do
"suportado" apurado.

## Unidade: a ficha é na unidade do inventário

A Ficha 3 é escriturada na unidade do 0200 (UNID_INV). O item de nota vem na
unidade dela, e quando o rótulo difere o fator sai do 0220 da própria EFD.
Sem 0220, a quantidade fica como veio e a linha é marcada — não se adivinha
fator. Na empresa 19, que não entrega 0220, a quantidade da EFD já vem na unidade
básica mesmo com rótulo CX ou FD: bateu com a "Qtde;Unitária" do relatório em
100% dos itens de 05/2021. Converter pelo rótulo ali multiplicaria errado.

O juiz final da unidade é o inventário: o saldo da ficha em cada data de
bloco H é comparado com o que o bloco H diz. Diferença do tamanho de um fator
de embalagem é marcada como suspeita de unidade.

## Confronto dos enquadramentos 2 e 4, e o crédito do art. 271

A coluna 21 é o ICMS da operação própria da entrada. Como a saída não diz de
que nota veio, vale a regra do item 3.3.8: as entradas mais recentes da ficha,
até a data da saída, suficientes para a quantidade, com média ponderada — a
mesma regra que valora a abertura (`valor_da_abertura`). No enquadramento 4, a
coluna 21 também é o crédito do art. 271 (coluna 27). Conferido contra a Ficha 3
da RVZ na empresa 04: 2,15 suportado, 0,63 da entrada, 1,52 de ressarcimento e
0,63 de crédito.

Decisão do Victor, 26/11/2026: só conta a entrada **com destaque** do ICMS
próprio (a transferência CST 60, de próprio zero, não dilui mais a média e não
devolve o suportado inteiro). Sem entrada com destaque até a saída, vale a
primeira com destaque depois dela; se a ficha não teve entrada com destaque em
momento nenhum, o efetivo é `PERCENTUAL_SEM_DESTAQUE` (40%) do valor unitário
do saldo vezes a quantidade baixada. A coluna `criterio_do_efetivo` diz qual
das três valeu.

## Ficha com estoque negativo sai do total

Estoque negativo é movimento que falta — perda que não veio, mês de relatório
que falhou, produção. E nele o custo médio perde o sentido: com saldo perto de
zero o unitário explode (R$ 1,8 milhão por unidade num item do CD da empresa 19),
e uma única baixa vira centenas de milhões. No piloto de 15/09/2026, 99,99% do
ressarcimento vinha de 4.037 fichas assim.

Decisão do Victor, 15/09/2026: essas fichas **saem do total até os dados
chegarem**. Desde 17/09/2026 elas não saem mais: a ficha abre com a
quantidade que faltaria, sem ICMS suportado, e fica marcada (`ficou_negativo`,
`abertura_por_saldo_negativo`). Continuam gravadas e marcadas (`retirada`,
hoje sempre falso), para consulta e
download, mas não somam ressarcimento, complemento, enquadramento nem
competência.

## Redução de base: a entrada manda no efetivo da saída

Quando a entrada da mercadoria vem com CST 20 ou 70, o fornecedor declara base
reduzida, e o ICMS efetivo da saída a consumidor (enquadramento 1) incide sobre
essa mesma base — não sobre o valor cheio. A redução sai do `vBC` da nota, não
do `pRedBC`, e a chave é o NCM: cada saída herda a da entrada mais recente até
a data dela. O porquê está em `cat.dominio.icms.cat42.reducao`; aqui fica só a
leitura das entradas e o carimbo em `lancamentos.reducao_base`.

## De-para: o mesmo produto com outro código

Com pares aprovados (`Fontes.depara`, um parquet com `cnpj`, `codigo_origem`,
`codigo_destino` e `fator`), cada lançamento, o estoque de abertura e as
entradas anteriores passam para o código da mercadoria antes de tudo, e a
quantidade é multiplicada pelo fator — 1 kit de três vira 3 unidades. A
alíquota do confronto é a do 0200 do código de origem, e a do destino quando a
origem não tem cadastro. A Ficha 3 guarda o código de origem em
`codigo_original`.

## De qual loja é a saída do relatório

O relatório diz a unidade ("005"), não o CNPJ. O CNPJ sai de duas pistas que
se confirmam: a chave de acesso de quem emitiu, e a coluna CNPJ/CPF da venda
de PDV, que traz a própria loja. A unidade herda o CNPJ que essas linhas
apontarem; o que nenhuma pista alcança fica contado, não suposto.
"""

from __future__ import annotations

import os
import shutil
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.icms.cat42.correcao import Campo
from cat.dominio.icms.cat42.enquadramento import (
    CFOP_DEVOLUCAO,
    CFOP_OUTRAS_X949,
    CFOP_REGISTRADO_EM_CUPOM,
    CFOP_TRANSFERENCIA_RECEBIDA,
    CFOP_USO_E_CONSUMO,
    VendaAConsumidor,
    classificar,
)
from cat.dominio.icms.cat42.razao import (
    DestaquesDaFilial,
    EntradaAnterior,
    EnquadramentoLegal,
    escolher_destaque,
    ValorDaAbertura,
    valor_da_abertura,
    valor_pelas_entradas_do_remetente,
    valor_pelas_entradas_seguintes,
    Especie,
    Movimento,
    MovimentoInvalido,
    RazaoDoItem,
    SaldoInicial,
)
from cat.dominio.icms.cat42.reducao import (
    CST_COM_REDUCAO,
    icms_efetivo as icms_efetivo_da_saida,
    reducao_da_entrada,
)
from cat.infraestrutura.analitico.confronto import (
    SITUACOES_COM_DOCUMENTO,
    _abrir,
    _escapar,
    _limpar,
)
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML
from cat.infraestrutura.analitico.movimentacao import (
    ARQUIVO_CONVERSOES,
    ARQUIVO_ITENS,
    ARQUIVO_MOVIMENTOS,
)
from cat.infraestrutura.analitico.movimentos import (
    ARQUIVO_DOCUMENTOS,
    ARQUIVO_INVENTARIO,
    ARQUIVO_ITENS_DA_EFD,
)
from cat.infraestrutura.analitico.suportado import (
    ARQUIVO_SUPORTADO,
    ApuracaoCancelada,
    _leitura,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_SAIDAS_DO_RELATORIO = "saidas_do_relatorio.parquet"
ARQUIVO_FICHA3 = "ficha3.parquet"
ARQUIVO_FICHAS = "fichas.parquet"
ARQUIVO_CONFERENCIA_INVENTARIO = "conferencia_inventario.parquet"
# cada transferência recebida sem o retido e o valor que as entradas do
# remetente deram a ela: a prova do número que entrou na ficha
ARQUIVO_TRANSFERENCIAS_VALORADAS = "transferencias_valoradas.parquet"
ESQUEMA_TRANSFERENCIAS_VALORADAS = pa.schema([
    ("cnpj", pa.string()),
    ("codigo", pa.string()),
    ("data", pa.date32()),
    ("chave", pa.string()),
    ("numero_item", pa.int32()),
    ("remetente", pa.string()),
    ("quantidade", pa.decimal128(38, 9)),
    ("suportado", pa.decimal128(30, 15)),
    ("coberta", pa.decimal128(38, 9)),
    ("entradas_usadas", pa.int32()),
    # de onde veio o destaque (`CriterioDoSuportado`) e de que filial
    ("criterio", pa.string()),
    ("filial_do_destaque", pa.string()),
])

LINHAS_POR_LOTE = 200_000
POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200

# quantas linhas de um relatório se olham antes de concluir que ele é só de
# entradas. Ler inteiro um relatório de entradas para achar zero saídas custa,
# na empresa 19, 26 minutos sobre 20 GB
AMOSTRA_PARA_ACHAR_SAIDA = 5_000

# devolução de venda chega como entrada; devolução de compra, como saída
_DEVOLUCAO_DE_VENDA = frozenset(c for c in CFOP_DEVOLUCAO if c[0] in "123")
_DEVOLUCAO_DE_COMPRA = frozenset(c for c in CFOP_DEVOLUCAO if c[0] in "567")

_Q4 = Decimal("0.0001")
_Q6 = Decimal("0.000001")
# enquadramentos 2 e 4 sem entrada com destaque em momento nenhum da ficha: o
# ICMS efetivo da entrada é esta fração do valor unitário do saldo vezes a
# quantidade da saída (decisão do Victor, 26/11/2026)
PERCENTUAL_SEM_DESTAQUE = Decimal("0.40")
EFETIVO_PELA_ENTRADA = "entrada_anterior"
EFETIVO_PELA_ENTRADA_POSTERIOR = "entrada_posterior"
EFETIVO_PELO_PERCENTUAL = "percentual_do_saldo"
_Q15 = Decimal("0.000000000000001")

ESQUEMA_SAIDA_DO_RELATORIO = pa.schema([
    ("unidade", pa.string()),
    ("cnpj_participante", pa.string()),
    ("chave", pa.string()),
    ("numero_documento", pa.string()),
    ("codigo", pa.string()),
    ("data", pa.date32()),
    ("cfop", pa.string()),
    ("cst_icms", pa.string()),
    ("quantidade", pa.decimal128(20, 6)),
    ("valor", pa.decimal128(20, 6)),
    ("suportado", pa.decimal128(20, 6)),
    ("pdv", pa.bool_()),
])

ESQUEMA_FICHA3 = pa.schema([
    ("cnpj", pa.string()),
    ("codigo", pa.string()),
    # o cadastro da mercadoria, que o leiaute do papel de trabalho pede na
    # linha e não obriga a cruzar com outro arquivo para ler a ficha
    ("descricao", pa.string()),
    ("ncm", pa.string()),
    ("unidade_estoque", pa.string()),
    ("numero", pa.int32()),
    ("data", pa.date32()),
    ("especie", pa.string()),
    ("devolucao", pa.bool_()),
    ("cfop", pa.string()),
    # o CST do documento, como veio da EFD ou do XML: é por ele que se confere
    # o enquadramento e a tributação da linha, entrada e saída
    ("cst_icms", pa.string()),
    ("documento", pa.string()),
    ("origem", pa.string()),
    ("enquadramento", pa.int8()),
    ("enquadramento_indefinido", pa.bool_()),
    # a ficha inteira ficou fora do total: estoque negativo em alguma linha
    ("ficha_retirada", pa.bool_()),
    # a linha levou correção à mão em algum campo
    ("corrigida", pa.bool_()),
    # a quantidade vai na unidade do inventário; estas três dizem como chegou lá
    ("unidade_origem", pa.string()),
    ("fator_conversao", pa.decimal128(24, 9)),
    ("unidade_sem_fator", pa.bool_()),
    ("quantidade", pa.decimal128(24, 6)),
    # o VL_ITEM do documento, que é a base do confronto e o que se confere
    # contra a nota
    ("valor_item", pa.decimal128(20, 6)),
    ("icms_suportado", pa.decimal128(30, 15)),
    ("valor_unitario_usado", pa.decimal128(30, 15)),
    ("icms_efetivo", pa.decimal128(24, 6)),
    # a alíquota da operação, como o documento a traz — e, separada dela, a
    # alíquota interna que fez o confronto com a redução de base herdada da
    # entrada, em %, quando ela entrou no efetivo
    ("aliquota_documento", pa.decimal128(9, 4)),
    ("aliquota", pa.decimal128(9, 4)),
    # de onde saiu a alíquota do confronto quando o 0200 não a tinha: vazio é o
    # cadastro, e o resto diz a chave e a prova (`FONTES_DA_ALIQUOTA`)
    ("aliquota_origem", pa.string()),
    ("reducao_base", pa.decimal128(9, 4)),
    ("saldo_quantidade", pa.decimal128(24, 6)),
    ("saldo_unitario", pa.decimal128(30, 15)),
    ("saldo_valor", pa.decimal128(30, 15)),
    ("ressarcimento", pa.decimal128(30, 15)),
    ("complemento", pa.decimal128(30, 15)),
    # o documento da linha, como o arquivo digital pede: o 1100 leva chave e nº
    # do item; o 1200, participante, modelo e número. Vazio quando a fonte não
    # traz — a venda de PDV do relatório não tem chave nem nº do item
    ("chave", pa.string()),
    ("numero_item", pa.int32()),
    ("modelo", pa.string()),
    ("participante", pa.string()),
    ("numero_documento", pa.string()),
    ("serie", pa.string()),
    # o código como veio da fonte, quando o de-para o trocou pelo da mercadoria
    ("codigo_original", pa.string()),
    ("credito_operacao_propria", pa.decimal128(30, 15)),
    # transferência recebida sem retido: por que critério o suportado foi
    # achado, de que filial veio o destaque e, sem destaque nenhum, a marca de
    # que o valor precisa ser estimado (decisão de 25/11/2026)
    ("criterio_do_suportado", pa.string()),
    ("filial_do_destaque", pa.string()),
    ("suportado_a_estimar", pa.bool_()),
    # enquadramentos 2 e 4: de onde veio o ICMS efetivo da entrada (coluna 21) —
    # `entrada_anterior`, `entrada_posterior` ou `percentual_do_saldo`
    ("criterio_do_efetivo", pa.string()),
])

ESQUEMA_FICHAS = pa.schema([
    ("cnpj", pa.string()),
    ("uf", pa.string()),
    ("codigo", pa.string()),
    ("descricao", pa.string()),
    ("linhas", pa.int32()),
    ("abertura_quantidade", pa.decimal128(24, 6)),
    # o ICMS da abertura pelas entradas anteriores ao inventário (item 3.3.8)
    ("abertura_valor", pa.decimal128(30, 15)),
    ("abertura_sem_valor", pa.bool_()),
    # as entradas anteriores não alcançaram a quantidade: o resto foi pela média delas
    ("abertura_parcial", pa.bool_()),
    ("entradas", pa.decimal128(24, 6)),
    ("saidas", pa.decimal128(24, 6)),
    ("saldo_quantidade", pa.decimal128(24, 6)),
    ("saldo_valor", pa.decimal128(30, 15)),
    ("ressarcimento", pa.decimal128(30, 15)),
    ("complemento", pa.decimal128(30, 15)),
    ("credito_operacao_propria", pa.decimal128(30, 15)),
    ("ficou_negativo", pa.bool_()),
    # quantidade aberta para cobrir o estoque negativo, sem ICMS suportado
    ("abertura_por_saldo_negativo", pa.decimal128(24, 6)),
    # fora do total até os dados chegarem; o ressarcimento dela não é confiável
    ("retirada", pa.bool_()),
    ("saidas_sem_aliquota", pa.int32()),
    ("saidas_com_reducao", pa.int32()),
    ("saidas_indefinidas", pa.int32()),
    ("linhas_sem_fator", pa.int32()),
    # de onde veio a abertura: `ficha_anterior` (o saldo final da Ficha 3 do
    # período anterior) ou `bloco_h` (o inventário, valorado pelas entradas). A
    # quantidade do bloco H fica ao lado para conciliar as duas
    ("abertura_origem", pa.string()),
    ("abertura_bloco_h", pa.decimal128(24, 6)),
])

# o que a conferência com o inventário acrescenta a cada ficha
_COLUNAS_DA_CONFERENCIA = ("inventarios_conferidos", "inventarios_divergentes",
                           "maior_diferenca_inventario", "suspeita_de_unidade")

DeveParar = Callable[[], bool]


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A montagem do razão foi cancelada por quem a pediu.")


# ---------------------------------------------------------------------------
# saídas do relatório do cliente
# ---------------------------------------------------------------------------
@dataclass
class SaidasExtraidas:
    arquivos: int = 0
    so_de_entradas: int = 0
    recusados: int = 0
    linhas: int = 0
    # a mesma linha já vinda de outro relatório (as "quebras" dentro das "Saídas")
    repetidas_entre_relatorios: int = 0


def extrair_saidas(
    relatorios: list[str],
    destino: str,
    avisar: Callable[[int, int], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> SaidasExtraidas:
    """Grava as linhas de saída dos relatórios de movimento do cliente.

    Um relatório por vez, em partes, somadas no fim — a mesma lição da etapa
    4: acumular em memória não cabe numa base de dezenas de GB. O relatório
    que não mostra saída nenhuma nas primeiras linhas é de entradas e é
    deixado de lado sem ser lido inteiro.
    """
    from cat.infraestrutura.arquivos.gerencial import Leitura

    partes = destino + ".partes"
    shutil.rmtree(partes, ignore_errors=True)
    os.makedirs(partes)
    r = SaidasExtraidas(arquivos=len(relatorios))
    try:
        for n, caminho in enumerate(relatorios, 1):
            _conferir(deve_parar)
            nome = os.path.basename(caminho)
            try:
                leitura = Leitura(caminho)
                # **As duas espécies de movimento entram.** Até 17/11/2026 só
                # `MOVIMENTO` passava, e o relatório de saída do varejo — que é
                # `MOVIMENTO_SEM_ST`, porque venda de mercadoria com ST sai em
                # CST 60 e não tem parcela retida — era recusado em silêncio.
                # Na empresa 17 isso descartava os 217 arquivos que contêm a
                # única saída item a item que existe: as saídas do razão
                # sairiam vazias e a ficha fecharia só com entradas.
                #
                # O que o razão precisa daqui é a saída, e o relatório sem ST a
                # tem. O que falta nele é a parcela retida, que é da entrada e
                # se apura na etapa 4.
                if not leitura.especie.serve_para_razao:
                    r.recusados += 1
                    continue
                gravadas = _gravar_saidas_de(leitura, os.path.join(partes, f"{n:05d}.parquet"))
                if gravadas is None:
                    r.so_de_entradas += 1
                    log.info("relatório só de entradas, ignorado no razão", extra={"arquivo": nome})
                else:
                    r.linhas += gravadas
            except (OSError, ValueError) as erro:
                r.recusados += 1
                log.warning("relatório ilegível no razão", extra={"arquivo": nome, "motivo": str(erro)})
            finally:
                if avisar is not None:
                    avisar(n, len(relatorios))

        arquivos = [x for x in os.listdir(partes) if x.endswith(".parquet")]
        if arquivos:
            con = _leitura(partes)
            try:
                # **A mesma linha em dois relatórios conta uma vez.** O varejo
                # do projeto 1 manda "quebras" e "Saídas", e as quebras são as
                # baixas (5.927) que as Saídas já trazem: 77.539 das 78.017
                # linhas de janeiro eram idênticas. A linha fica com o primeiro
                # relatório que a tem; repetição DENTRO de um relatório é dado
                # dele (o pão francês pesado duas vezes no mesmo cupom) e fica.
                #
                # **Sem montar a rede inteira numa tabela.** A primeira versão
                # (23/11/2026) fazia uma janela sobre todas as linhas e estourou
                # 11,5 GB de temporário nos cupons de nove meses da rede toda.
                # Agora cada linha vira uma impressão de 128 bits (md5 dos oito
                # campos) e o número do relatório; o agrupamento guarda só as
                # impressões que aparecem em MAIS de um relatório, com o menor
                # número — pouca coisa — e a cópia final é um passe só, em
                # fluxo, que solta a linha cuja impressão é repetida e não é do
                # relatório que fica.
                campos = ("unidade", "chave", "numero_documento", "codigo", "data", "cfop",
                          "quantidade", "valor")
                impressao = "md5_number(concat_ws(chr(31), {}))".format(", ".join(
                    f"coalesce(CAST({c} AS VARCHAR), chr(30))" for c in campos))
                numero = r"CAST(regexp_extract(filename, '(\d+)\.parquet$', 1) AS INTEGER)"
                origem = (f"read_parquet('{_escapar(os.path.join(partes, '*.parquet'))}', "
                          "filename = true)")
                con.execute(f"""
                    CREATE TABLE repetidas AS
                    SELECT h, min(n) AS fica FROM (
                        SELECT {impressao} AS h, {numero} AS n FROM {origem})
                    GROUP BY h HAVING min(n) <> max(n)
                """)
                gravadas = con.execute(f"""
                    COPY (
                        SELECT l.* EXCLUDE (filename, h, n) FROM (
                            SELECT *, {impressao} AS h, {numero} AS n FROM {origem}) l
                        LEFT JOIN repetidas r ON l.h = r.h
                        WHERE r.h IS NULL OR l.n = r.fica
                    ) TO '{_escapar(destino)}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """).fetchone()[0]
                r.repetidas_entre_relatorios = r.linhas - gravadas
                r.linhas = gravadas
            finally:
                con.close()
        else:
            pq.write_table(ESQUEMA_SAIDA_DO_RELATORIO.empty_table(), destino)
    finally:
        shutil.rmtree(partes, ignore_errors=True)
    log.info("saídas do relatório extraídas", extra=vars(r))
    return r


def _gravar_saidas_de(leitura, destino: str) -> int | None:
    colunas: dict[str, list] = {c: [] for c in ESQUEMA_SAIDA_DO_RELATORIO.names}
    escritor = None
    vistas = saidas = 0
    try:
        for m in leitura.movimentos():
            vistas += 1
            if m.e_entrada:
                if saidas == 0 and vistas >= AMOSTRA_PARA_ACHAR_SAIDA:
                    return None
                continue
            saidas += 1
            colunas["unidade"].append(m.unidade)
            colunas["cnpj_participante"].append(m.cnpj_participante or "")
            colunas["chave"].append(m.chave)
            colunas["numero_documento"].append(str(m.numero_doc) if m.numero_doc else "")
            colunas["codigo"].append(m.codigo_item)
            colunas["data"].append(m.data)
            colunas["cfop"].append(m.cfop.replace(".", ""))
            colunas["cst_icms"].append(m.cst_icms)
            colunas["quantidade"].append(m.quantidade.quantize(_Q6))
            colunas["valor"].append(m.valor_item.quantize(_Q6))
            colunas["suportado"].append(m.imposto_suportado.quantize(_Q6))
            colunas["pdv"].append(m.e_venda_de_pdv)
            if len(colunas["codigo"]) >= LINHAS_POR_LOTE:
                escritor = escritor or pq.ParquetWriter(destino, ESQUEMA_SAIDA_DO_RELATORIO)
                escritor.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA_SAIDA_DO_RELATORIO))
                colunas = {c: [] for c in ESQUEMA_SAIDA_DO_RELATORIO.names}
        if saidas == 0:
            return None
        if colunas["codigo"]:
            escritor = escritor or pq.ParquetWriter(destino, ESQUEMA_SAIDA_DO_RELATORIO)
            escritor.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA_SAIDA_DO_RELATORIO))
        return saidas
    finally:
        if escritor is not None:
            escritor.close()


# ---------------------------------------------------------------------------
# a montagem
# ---------------------------------------------------------------------------
@dataclass
class Fontes:
    """Onde está cada parquet que o razão lê. Cada um é de uma etapa."""

    movimentacao: str           # pasta da etapa 3
    apuracao: str               # pasta da etapa 4
    saidas_do_relatorio: str | None = None
    # o período do cadastro do trabalho. Sem ele, o da base. Com ele, o que a
    # base tem antes do início não entra na ficha: serve para valorar a abertura
    periodo: tuple[date, date] | None = None
    # os pares de de-para aprovados: cnpj, codigo_origem, codigo_destino, fator
    depara: str | None = None
    # o parquet com as correções à mão do trabalho, escrito pela etapa
    correcoes: str | None = None
    # o saldo com que a Ficha 3 de um período anterior terminou (cnpj, codigo,
    # quantidade, valor): onde ele tem o item, a abertura é ele, e não o bloco H
    saldo_anterior: str | None = None


class PeriodoSemMovimento(ValueError):
    """O cadastro do trabalho não cruza com a base importada."""


@dataclass
class Andamento:
    linhas: int = 0
    total: int = 0
    fichas: int = 0


@dataclass
class ResumoDaMontagem:
    periodo_inicio: str = ""
    # a escolha do trabalho com que o razão foi montado: muda o enquadramento
    # da venda a consumidor, e por isso o que vem depois precisa saber qual foi
    venda_a_consumidor: str = VendaAConsumidor.ENQUADRAMENTO_1.value
    periodo_fim: str = ""
    abertura_em: str | None = None
    codigos_com_st: int = 0
    fichas: int = 0
    estabelecimentos: int = 0
    linhas: int = 0
    ressarcimento: Decimal = Decimal(0)
    complemento: Decimal = Decimal(0)
    credito_operacao_propria: Decimal = Decimal(0)
    # saídas de enquadramento 2 e 4 confrontadas com o ICMS próprio das entradas
    confronto_pela_entrada: int = 0
    # ... pela primeira entrada com destaque depois da saída, e pelo percentual
    # do saldo, quando a ficha não teve entrada com destaque nenhuma
    confronto_pela_entrada_posterior: int = 0
    confronto_pelo_percentual: int = 0
    # notas do relatório sem chave que ganharam a do C100 da EFD
    relatorio_chave_do_c100: int = 0
    por_enquadramento: dict = field(default_factory=dict)
    por_competencia: dict = field(default_factory=dict)
    saidas_por_origem: dict = field(default_factory=dict)
    saidas_sem_aliquota: int = 0
    # saídas do enquadramento 1 cujo efetivo saiu de base reduzida, e quanto a
    # redução tirou do valor de confronto
    saidas_com_reducao: int = 0
    efetivo_reduzido: Decimal = Decimal(0)
    # saídas cuja alíquota veio da nota de entrada, por falta de 0200, e de
    # onde ela veio em cada uma (`FONTES_DA_ALIQUOTA`)
    saidas_com_aliquota_da_entrada: int = 0
    aliquota_por_fonte: dict = field(default_factory=dict)
    # correções à mão aplicadas nesta rodada, por campo
    correcoes: dict = field(default_factory=dict)
    saidas_indefinidas: int = 0
    confronto_pendente: int = 0
    fichas_negativas: int = 0
    fichas_abertura_sem_valor: int = 0
    fichas_abertura_valorada: int = 0
    fichas_abertura_parcial: int = 0
    icms_da_abertura: Decimal = Decimal(0)
    fichas_abertura_da_ficha_anterior: int = 0
    icms_da_ficha_anterior: Decimal = Decimal(0)
    # transferências recebidas sem o retido, valoradas pelas entradas mais
    # recentes do remetente (§ 5º da CAT 42/2018): inteiras, só em parte, e as
    # que o remetente não tinha entrada para cobrir
    transferencias_valoradas: int = 0
    transferencias_parciais: int = 0
    transferencias_sem_entrada: int = 0      # sem destaque nenhum: precisam ser estimadas
    icms_das_transferencias: Decimal = Decimal(0)
    transferencias_por_criterio: dict = field(default_factory=dict)
    # fora da ficha por decisão: uso e consumo não é estoque de comercialização
    lancamentos_de_uso_e_consumo: int = 0
    # fora da ficha por decisão: X.949, outras entradas e saídas (remessa e retorno)
    lancamentos_x949: int = 0
    fichas_fora_de_sp: int = 0
    relatorio_sem_estabelecimento: int = 0
    relatorio_trocado_pela_efd: int = 0
    # linhas de 5.929/6.929 do relatório: a venda já está no cupom
    relatorio_registrado_em_cupom: int = 0
    quantidade_negativa: int = 0
    fichas_retiradas: int = 0
    linhas_retiradas: int = 0
    # fichas que abriram com o que faltava para o estoque não ficar negativo
    fichas_abertas_por_negativo: int = 0
    quantidade_aberta_por_negativo: Decimal = Decimal(0)
    ressarcimento_retirado: Decimal = Decimal(0)
    complemento_retirado: Decimal = Decimal(0)
    linhas_convertidas: int = 0
    linhas_unidade_sem_fator: int = 0
    abertura_sem_fator: int = 0
    # saídas confrontadas com a alíquota do 0200 do próprio mês, diferente da
    # do fim do período — antes da revisão da etapa 7, usava-se a do fim
    saidas_com_aliquota_do_mes: int = 0
    # lançamentos que o de-para passou para outro código, e de quantos códigos
    linhas_com_depara: int = 0
    codigos_trocados_pelo_depara: int = 0
    conferencia: dict = field(default_factory=dict)


def contar_movimentos(fontes: Fontes, destino: str) -> int:
    """Quantas linhas a montagem vai percorrer — o denominador da barra."""
    con = _abrir(destino)
    try:
        _preparar(con, fontes)
        return con.execute("SELECT count(*) FROM lancamentos").fetchone()[0]
    finally:
        con.close()
        _limpar(destino)


def montar(
    fontes: Fontes,
    destino: str,
    uf_por_cnpj: dict[str, str] | None = None,
    descricoes: dict[tuple[str, str], str] | None = None,
    avisar: Callable[[Andamento], None] | None = None,
    deve_parar: DeveParar | None = None,
    venda_a_consumidor: VendaAConsumidor = VendaAConsumidor.ENQUADRAMENTO_1,
) -> ResumoDaMontagem:
    """Percorre os lançamentos de cada (estabelecimento, mercadoria) e grava a ficha.

    O cálculo é o do domínio, linha a linha, por decisão: a regra foi conferida
    contra uma Ficha 3 real, e reescrevê-la em SQL daria duas versões dela.
    Ao SQL cabe o que ele faz bem — juntar, filtrar, ordenar.
    """
    uf_por_cnpj = uf_por_cnpj or {}
    ficha3 = os.path.join(destino, ARQUIVO_FICHA3)
    fichas = os.path.join(destino, ARQUIVO_FICHAS)
    resumo = ResumoDaMontagem(venda_a_consumidor=venda_a_consumidor.value)
    con = _abrir(destino)
    try:
        info = _preparar(con, fontes)
        resumo.periodo_inicio = info["inicio"].isoformat()
        resumo.periodo_fim = info["fim"].isoformat()
        resumo.abertura_em = info["abertura_em"].isoformat() if info["abertura_em"] else None
        resumo.codigos_com_st = info["codigos"]
        resumo.relatorio_sem_estabelecimento = info["sem_estabelecimento"]
        resumo.relatorio_trocado_pela_efd = info["trocado_pela_efd"]
        resumo.relatorio_chave_do_c100 = info.get("chave_do_c100", 0)
        resumo.relatorio_registrado_em_cupom = info["registrado_em_cupom"]
        resumo.abertura_sem_fator = info["abertura_sem_fator"]
        resumo.saidas_com_aliquota_do_mes = con.execute(
            "SELECT count(*) FROM lancamentos WHERE especie = 'saida' AND NOT devolucao "
            "AND aliquota_do_mes_diferente").fetchone()[0]
        resumo.correcoes = info["correcoes"]
        resumo.lancamentos_de_uso_e_consumo = info["uso_e_consumo"]
        resumo.lancamentos_x949 = info["x949"]
        resumo.linhas_com_depara, resumo.codigos_trocados_pelo_depara = con.execute(
            "SELECT count(*), count(DISTINCT (cnpj, codigo_original)) FROM lancamentos "
            "WHERE codigo_original <> codigo").fetchone()
        _valorar_transferencias(con, destino, resumo, uf_por_cnpj)
        aberturas, origens, do_bloco_h, da_ficha = {}, {}, {}, {}
        for c, k, q, origem, valor, q_bloco in con.execute(
                "SELECT cnpj, codigo, quantidade, origem, valor_anterior, quantidade_bloco_h "
                "FROM abertura").fetchall():
            aberturas[(c, k)] = q
            origens[(c, k)] = (origem, q_bloco)
            if origem == "ficha_anterior":
                da_ficha[(c, k)] = ValorDaAbertura(Decimal(valor or 0), Decimal(q), Decimal(q))
            else:
                do_bloco_h[(c, k)] = q
        # o saldo da ficha anterior já vem com o ICMS: só o bloco H é valorado
        valores = {**_valorar_aberturas(con, do_bloco_h), **da_ficha}
        total = con.execute("SELECT count(*) FROM lancamentos").fetchone()[0]
        if total == 0 and not aberturas and info["base_inicio"] is not None and fontes.periodo:
            raise PeriodoSemMovimento(
                f"Nenhum movimento no período do trabalho ({info['inicio']:%m/%Y} a {info['fim']:%m/%Y}); "
                f"a base vai de {info['base_inicio']:%m/%Y} a {info['base_fim']:%m/%Y}. "
                "Corrija o cadastro do trabalho ou a base importada.")

        leitor = con.execute("""
            SELECT * FROM lancamentos
            ORDER BY cnpj, codigo, data, prioridade, origem, documento
        """).to_arrow_reader(LINHAS_POR_LOTE)
        _percorrer(leitor, aberturas, ficha3, fichas, resumo, total,
                   uf_por_cnpj, descricoes or {}, avisar, deve_parar, venda_a_consumidor, valores,
                   origens, resolver_sem_destaque=info["tem_icms_proprio"])
        # conexão nova para a conferência: a do percurso ainda segura o leitor
        # (a lição do índice da etapa 4). O banco é em arquivo, as tabelas ficam
        del leitor
        con.close()
        con = _abrir(destino)
        resumo.conferencia = _conferir_inventario(
            con, fontes, ficha3, fichas, os.path.join(destino, ARQUIVO_CONFERENCIA_INVENTARIO),
            info["inicio"], info["fim"])
        itens_do_cadastro = os.path.join(fontes.movimentacao, ARQUIVO_ITENS)
        _completar_fichas(con, fichas, itens_do_cadastro,
                          os.path.join(destino, ARQUIVO_CONFERENCIA_INVENTARIO))
        _completar_ficha3(con, ficha3, itens_do_cadastro,
                          os.path.join(fontes.movimentacao, ARQUIVO_ITENS_DO_XML))
    except ApuracaoCancelada:
        con.close()
        for arquivo in (ficha3, fichas, os.path.join(destino, ARQUIVO_CONFERENCIA_INVENTARIO)):
            if os.path.isfile(arquivo):
                os.remove(arquivo)
        raise
    finally:
        con.close()
        _limpar(destino)

    log.info("razão montado", extra={
        "fichas": resumo.fichas, "linhas": resumo.linhas,
        "ressarcimento": str(resumo.ressarcimento), "complemento": str(resumo.complemento)})
    return resumo


def _chave_do_c100(con, fontes: "Fontes", inicio: date, fim: date) -> int:
    """A nota do relatório que veio sem chave ganha a do C100 da EFD.

    A NF-e emitida pela própria loja vai para a EFD sem C170: o C100 tem a
    chave, o número e a data, mas nenhum item, e por isso o relatório é a única
    fonte das quantidades. A perda (5.927) do projeto 1 é toda assim: 352 das
    364 notas do teste estavam na EFD só como C100. Decisão do Victor,
    26/11/2026: a chave se acha por estabelecimento, número e data.

    Só NF-e (modelo 55) de saída e regular, e só quando o par aponta uma nota
    só: o número da NFC-e se repete entre séries e anos, e a nota cancelada não
    é baixa de estoque. Devolve quantas linhas ganharam a chave.
    """
    docs = os.path.join(fontes.movimentacao, ARQUIVO_DOCUMENTOS)
    if not os.path.isfile(docs):
        return 0
    situacoes = ", ".join(f"'{x}'" for x in SITUACOES_COM_DOCUMENTO)
    con.execute(f"""
        CREATE OR REPLACE TABLE chave_do_c100 AS
        SELECT cnpj, ltrim(numero_documento, '0') AS numero, data, min(chave) AS chave
        FROM read_parquet('{_escapar(docs)}')
        WHERE operacao = 'saida' AND modelo = '55' AND length(chave) = 44
          AND situacao IN ({situacoes}) AND cnpj IN (SELECT cnpj FROM estabs)
          AND data BETWEEN DATE '{inicio}' AND DATE '{fim}'
          AND coalesce(numero_documento, '') <> ''
        GROUP BY 1, 2, 3 HAVING count(DISTINCT chave) = 1
    """)
    return con.execute("""
        UPDATE rel_com_cnpj r SET chave = c.chave
        FROM chave_do_c100 c
        WHERE coalesce(length(r.chave), 0) <> 44 AND c.cnpj = r.cnpj
          AND c.numero = ltrim(r.numero_documento, '0') AND c.data = r.data
    """).fetchone()[0]


def _juntar_saldo_anterior(con, saldo_anterior: str | None) -> None:
    """A abertura começa onde a Ficha 3 anterior terminou (decisão do Victor,
    26/11/2026; até ali valia sempre o bloco H).

    Onde a ficha anterior tem o item, a quantidade e o ICMS são os do saldo
    final dela, mesmo que seja zero: a ficha nova começa ali. O bloco H, já
    convertido, fica como reserva para o item que a ficha anterior não tem e
    para o estabelecimento que não tem ficha anterior. A quantidade dele fica
    ao lado nos dois casos, para o quadro de conciliação.

    A ficha anterior está na unidade da ficha (UNID_INV) e com o código do
    cliente: o de-para vale para ela como para o inventário.
    """
    con.execute("ALTER TABLE abertura ADD COLUMN IF NOT EXISTS origem VARCHAR")
    con.execute("ALTER TABLE abertura ADD COLUMN IF NOT EXISTS valor_anterior DECIMAL(38, 15)")
    con.execute("ALTER TABLE abertura ADD COLUMN IF NOT EXISTS quantidade_bloco_h DECIMAL(38, 9)")
    con.execute("UPDATE abertura SET origem = 'bloco_h', quantidade_bloco_h = quantidade")
    if not saldo_anterior or not os.path.isfile(saldo_anterior):
        return
    con.execute(f"""
        CREATE OR REPLACE TABLE saldo_anterior AS
        SELECT s.cnpj, coalesce(d.codigo_destino, s.codigo) AS codigo,
               sum(s.quantidade * coalesce(d.fator, 1)) AS quantidade, sum(s.valor) AS valor
        FROM read_parquet('{_escapar(saldo_anterior)}') s
        LEFT JOIN depara d ON d.cnpj = s.cnpj AND d.codigo_origem = s.codigo
        WHERE s.cnpj IN (SELECT cnpj FROM estabs)
          AND coalesce(d.codigo_destino, s.codigo) IN (SELECT codigo FROM codigos)
        GROUP BY 1, 2
    """)
    con.execute("""
        CREATE OR REPLACE TABLE abertura AS
        SELECT a.cnpj, a.codigo, a.quantidade, a.sem_fator, 'bloco_h' AS origem,
               CAST(NULL AS DECIMAL(38, 15)) AS valor_anterior,
               CAST(a.quantidade AS DECIMAL(38, 9)) AS quantidade_bloco_h
        FROM abertura a
        WHERE NOT EXISTS (SELECT 1 FROM saldo_anterior s WHERE s.cnpj = a.cnpj AND s.codigo = a.codigo)
        UNION ALL
        SELECT s.cnpj, s.codigo, s.quantidade, false, 'ficha_anterior', s.valor,
               CAST(a.quantidade AS DECIMAL(38, 9))
        FROM saldo_anterior s LEFT JOIN abertura a ON a.cnpj = s.cnpj AND a.codigo = s.codigo
        WHERE s.quantidade <> 0 OR s.valor <> 0
    """)


def _valorar_aberturas(con, aberturas: dict) -> dict[tuple[str, str], ValorDaAbertura]:
    """O ICMS de cada abertura pelas entradas mais recentes até o inventário.

    As entradas vêm da mais recente para a mais antiga, e param de ser
    guardadas quando já cobrem a quantidade: numa base com anos de entrada, o
    item não precisa de todas na memória.
    """
    valores: dict[tuple[str, str], ValorDaAbertura] = {}
    atual: tuple[str, str] | None = None
    entradas: list[EntradaAnterior] = []
    coberto = Decimal(0)
    cursor = con.execute("""
        SELECT x.cnpj, x.codigo, x.data, x.quantidade, x.suportado FROM anteriores x
        WHERE EXISTS (SELECT 1 FROM abertura a WHERE a.cnpj = x.cnpj AND a.codigo = x.codigo
                      AND a.origem = 'bloco_h')
        ORDER BY x.cnpj, x.codigo, x.data DESC, x.chave DESC, x.numero_item DESC
    """)
    while lote := cursor.fetchmany(LINHAS_POR_LOTE):
        for cnpj, codigo, data_, quantidade, suportado in lote:
            chave = (cnpj, codigo)
            if chave != atual:
                if atual is not None:
                    valores[atual] = valor_da_abertura(Decimal(aberturas[atual]), entradas)
                atual, entradas, coberto = chave, [], Decimal(0)
            if coberto >= Decimal(aberturas[chave]):
                continue
            q = Decimal(quantidade)
            entradas.append(EntradaAnterior(data_, q, Decimal(suportado), ordem=-len(entradas)))
            coberto += q
    if atual is not None:
        valores[atual] = valor_da_abertura(Decimal(aberturas[atual]), entradas)
    for chave, quantidade in aberturas.items():
        if chave not in valores:
            valores[chave] = valor_da_abertura(Decimal(quantidade), [])
    return valores


def _valorar_transferencias(con, destino: str, resumo: ResumoDaMontagem,
                            uf_por_cnpj: dict | None = None) -> None:
    """Dá às transferências recebidas sem retido o ICMS suportado de um destaque.

    A ordem é a de `escolher_destaque` (decisão de 25/11/2026): o destaque do
    mesmo produto na mesma filial, até 6 meses antes ou, sem ele, até 6 meses
    depois; depois o do remetente e o de outra filial da mesma UF, na mesma
    janela; sem nenhum, a linha fica marcada para estimar e o suportado não é
    inventado. Até 25/11/2026 valia sempre o remetente, em cadeia.

    "Destaque" é o retido que a nota trouxe: uma transferência valorada aqui não
    serve de destaque para outra, e por isso a ordem de data na rede deixou de
    importar. Vai um código por vez — as entradas de um produto em todas as
    filiais cabem em memória; as da rede inteira, não.

    As quantidades vão na unidade da ficha (`quantidade * fator`) e o código é o
    de depois do de-para. Só a linha sem valor nenhum é valorada: o retido que a
    nota trouxe vale mais que qualquer reconstrução.
    """
    lista = lambda conj: ", ".join(f"'{c}'" for c in sorted(conj))  # noqa: E731
    recebidas = lista(CFOP_TRANSFERENCIA_RECEBIDA)
    con.execute("ALTER TABLE lancamentos ADD COLUMN IF NOT EXISTS criterio_do_suportado VARCHAR")
    con.execute("ALTER TABLE lancamentos ADD COLUMN IF NOT EXISTS filial_do_destaque VARCHAR")
    con.execute(f"""
        CREATE OR REPLACE TABLE sem_retido AS
        SELECT cnpj, codigo, data, coalesce(chave, '') AS chave, numero_item,
               CASE WHEN length(coalesce(chave, '')) = 44 THEN substr(chave, 7, 14) END AS remetente,
               quantidade * fator AS quantidade
        FROM lancamentos
        WHERE especie = 'entrada' AND NOT devolucao AND cfop IN ({recebidas})
          AND coalesce(suportado, 0) = 0 AND quantidade > 0
          AND (length(coalesce(chave, '')) <> 44 OR substr(chave, 7, 14) <> cnpj)
    """)
    total = con.execute("SELECT count(*) FROM sem_retido").fetchone()[0]
    if total == 0:
        return
    con.execute("""CREATE OR REPLACE TABLE codigos_pedidos AS
                   SELECT codigo, row_number() OVER (ORDER BY codigo) AS k
                   FROM (SELECT DISTINCT codigo FROM sem_retido)""")
    # os destaques de cada código pedido, em todas as filiais: as entradas do
    # período e as de antes do inventário que a abertura já separou
    # dois cursores, lidos juntos em ordem de código: um `execute` na mesma
    # conexão descartaria o resultado do outro
    c_destaques, c_pedidos = con.cursor(), con.cursor()
    c_destaques.execute("""
        SELECT p.k, x.cnpj, x.data, x.quantidade, x.suportado FROM (
            SELECT l.cnpj, l.codigo, l.data, coalesce(l.chave, '') AS chave,
                   coalesce(l.numero_item, 0) AS numero_item, l.quantidade * l.fator AS quantidade,
                   l.suportado
            FROM lancamentos l
            WHERE l.especie = 'entrada' AND NOT l.devolucao AND l.quantidade > 0
              AND coalesce(l.suportado, 0) > 0
            UNION ALL
            SELECT a.cnpj, a.codigo, a.data, a.chave, a.numero_item, a.quantidade, a.suportado
            FROM anteriores a WHERE a.quantidade > 0 AND coalesce(a.suportado, 0) > 0
        ) x JOIN codigos_pedidos p ON p.codigo = x.codigo
        ORDER BY p.k, x.cnpj, x.data, x.chave, x.numero_item
    """)
    c_pedidos.execute("""
        SELECT p.k, s.cnpj, s.codigo, s.data, s.chave, s.numero_item, s.remetente, s.quantidade
        FROM sem_retido s JOIN codigos_pedidos p ON p.codigo = s.codigo
        ORDER BY p.k, s.data, s.chave, s.numero_item
    """)

    def linhas(cursor):
        while lote := cursor.fetchmany(LINHAS_POR_LOTE):
            yield from lote

    ufs = uf_por_cnpj or {}
    por_uf: dict[str, set[str]] = {}
    for c, u in ufs.items():
        por_uf.setdefault(u, set()).add(c)
    mesma_uf = (lambda c: por_uf.get(ufs.get(c, ""), set())) if ufs else (lambda c: None)  # noqa: E731

    saida = {n: [] for n in ESQUEMA_TRANSFERENCIAS_VALORADAS.names}
    fonte = linhas(c_destaques)
    proxima = next(fonte, None)
    k_atual, do_codigo = None, {}
    try:
        for k, cnpj, codigo, data_, chave, item, remetente, quantidade in linhas(c_pedidos):
            if k != k_atual:
                # junta os destaques deste código (os dois lados vêm em ordem de k)
                por_filial: dict[str, list[EntradaAnterior]] = {}
                while proxima is not None and proxima[0] <= k:
                    kk, cnpj_e, dia_e, q_e, v_e = proxima
                    if kk == k:
                        lista_f = por_filial.setdefault(cnpj_e, [])
                        lista_f.append(EntradaAnterior(dia_e, Decimal(q_e), Decimal(v_e),
                                                       ordem=len(lista_f)))
                    proxima = next(fonte, None)
                k_atual, do_codigo = k, {f: DestaquesDaFilial(e) for f, e in por_filial.items()}
            quantidade = Decimal(quantidade)
            e = escolher_destaque(quantidade, data_, cnpj, remetente, do_codigo, mesma_uf(cnpj))
            for nome, x in (("cnpj", cnpj), ("codigo", codigo), ("data", data_), ("chave", chave),
                            ("numero_item", item), ("remetente", remetente), ("quantidade", quantidade),
                            ("suportado", e.valor.valor.quantize(Decimal("0.000000000000001"))),
                            ("coberta", e.valor.coberta), ("entradas_usadas", e.entradas_usadas),
                            ("criterio", e.criterio.value), ("filial_do_destaque", e.filial)):
                saida[nome].append(x)
            por_criterio = resumo.transferencias_por_criterio
            por_criterio[e.criterio.value] = por_criterio.get(e.criterio.value, 0) + 1
            if e.precisa_estimar:
                resumo.transferencias_sem_entrada += 1
            else:
                resumo.transferencias_valoradas += 1
                resumo.transferencias_parciais += int(e.valor.parcial)
                resumo.icms_das_transferencias += e.valor.valor
    finally:
        c_destaques.close()
        c_pedidos.close()

    caminho = os.path.join(destino, ARQUIVO_TRANSFERENCIAS_VALORADAS)
    pq.write_table(pa.Table.from_pydict(saida, schema=ESQUEMA_TRANSFERENCIAS_VALORADAS), caminho)
    # o valor volta ao lançamento; a quantidade da ficha é `quantidade * fator`,
    # e o suportado é o da linha inteira, então nada a converter. A linha que
    # precisa ser estimada recebe só a marca: o suportado continua zero
    con.execute(f"""
        UPDATE lancamentos l SET
            suportado = CASE WHEN v.criterio = 'precisa_estimar' THEN l.suportado
                             ELSE CAST(v.suportado AS DECIMAL(18, 6)) END,
            criterio_do_suportado = v.criterio,
            filial_do_destaque = v.filial_do_destaque
        FROM read_parquet('{_escapar(caminho)}') v
        WHERE v.cnpj = l.cnpj AND v.codigo = l.codigo AND v.chave = coalesce(l.chave, '')
          AND v.numero_item IS NOT DISTINCT FROM l.numero_item
          AND l.especie = 'entrada' AND NOT l.devolucao AND l.cfop IN ({recebidas})
          AND coalesce(l.suportado, 0) = 0
    """)
    log.info("transferências recebidas sem retido, valoradas por destaque",
             extra={"linhas": total, "valoradas": resumo.transferencias_valoradas,
                    "parciais": resumo.transferencias_parciais,
                    "a_estimar": resumo.transferencias_sem_entrada,
                    "por_criterio": resumo.transferencias_por_criterio})


def _completar_ficha3(con, ficha3: str, itens: str, xml_itens: str = "") -> None:
    """Põe a descrição da mercadoria em cada linha da Ficha 3.

    Mesma razão de `_completar_fichas`, e a mesma escolha: em SQL, no fim. A
    descrição é do cadastro, não do lançamento — mas o leiaute do papel de
    trabalho a quer na linha, e quem abre a planilha não deve precisar de um
    segundo arquivo para saber que mercadoria é aquela.

    Primeiro o 0200. Sem cadastro, vale o **xProd do XML da própria saída**: na
    empresa 04, quatro códigos não têm 0200 em arquivo nenhum e respondem por
    34.672 linhas — a mesma lacuna que obrigou a buscar a alíquota na nota de
    entrada (v0.58.0).
    """
    if not os.path.isfile(ficha3):
        return
    juncoes, fontes_da_descricao = [], []
    if os.path.isfile(itens):
        juncoes.append(f"""
            LEFT JOIN (SELECT cnpj, codigo, any_value(descricao) AS descricao
                       FROM read_parquet('{_escapar(itens)}') GROUP BY cnpj, codigo) i
              ON i.cnpj = f.cnpj AND i.codigo = f.codigo""")
        fontes_da_descricao.append("nullif(i.descricao, '')")
    if os.path.isfile(xml_itens) and {"codigo", "descricao", "emitente"} <= {
            c.name for c in pq.read_schema(xml_itens)}:
        # só o que o próprio estabelecimento emitiu: aí o cProd é o código da
        # ficha. Na nota do fornecedor, o código é o dele
        juncoes.append(f"""
            LEFT JOIN (SELECT replace(codigo, ' ', '') AS codigo, mode(descricao) AS descricao
                       FROM read_parquet('{_escapar(xml_itens)}') x
                       WHERE x.emitente IN (SELECT DISTINCT cnpj FROM read_parquet('{_escapar(ficha3)}'))
                         AND nullif(x.descricao, '') IS NOT NULL
                       GROUP BY 1) x
              ON x.codigo = replace(f.codigo, ' ', '')""")
        fontes_da_descricao.append("nullif(x.descricao, '')")
    if not fontes_da_descricao:
        return
    provisorio = ficha3 + ".tmp"
    con.execute(f"""
        COPY (
            SELECT f.* REPLACE (coalesce(nullif(f.descricao, ''),
                                         {', '.join(fontes_da_descricao)}, '') AS descricao)
            FROM read_parquet('{_escapar(ficha3)}') f
            {"".join(juncoes)}
        ) TO '{_escapar(provisorio)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    os.replace(provisorio, ficha3)


def _completar_fichas(con, fichas: str, itens: str, conferencia: str) -> None:
    """Põe em cada ficha a descrição do 0200 e o que a conferência com o
    inventário achou. Em SQL, no fim: o cadastro inteiro num dicionário do
    Python seriam milhões de entradas só para um rótulo."""
    if not os.path.isfile(fichas):
        return
    descricao = (f"LEFT JOIN read_parquet('{_escapar(itens)}') i ON i.cnpj = f.cnpj AND i.codigo = f.codigo"
                 if os.path.isfile(itens) else "")
    coluna_descricao = "coalesce(nullif(f.descricao, ''), i.descricao, '')" if descricao else "f.descricao"
    if os.path.isfile(conferencia):
        agregado = f"""(
            SELECT cnpj, codigo,
                   count(*) FILTER (saldo_ficha <> 0 OR inventario <> 0)::INTEGER AS inventarios_conferidos,
                   count(*) FILTER (situacao IN ('divergente', 'suspeita_unidade'))::INTEGER AS inventarios_divergentes,
                   max(abs(diferenca))::DECIMAL(24, 6) AS maior_diferenca_inventario,
                   bool_or(situacao = 'suspeita_unidade') AS suspeita_de_unidade
            FROM read_parquet('{_escapar(conferencia)}') GROUP BY cnpj, codigo)"""
    else:
        agregado = ("(SELECT NULL::VARCHAR AS cnpj, NULL::VARCHAR AS codigo, 0 AS inventarios_conferidos, "
                    "0 AS inventarios_divergentes, NULL::DECIMAL(24, 6) AS maior_diferenca_inventario, "
                    "false AS suspeita_de_unidade WHERE false)")
    provisorio = fichas + ".tmp"
    con.execute(f"""
        COPY (
            SELECT f.* REPLACE ({coluna_descricao} AS descricao),
                   coalesce(c.inventarios_conferidos, 0) AS inventarios_conferidos,
                   coalesce(c.inventarios_divergentes, 0) AS inventarios_divergentes,
                   coalesce(c.maior_diferenca_inventario, 0) AS maior_diferenca_inventario,
                   coalesce(c.suspeita_de_unidade, false) AS suspeita_de_unidade
            FROM read_parquet('{_escapar(fichas)}') f
            {descricao}
            LEFT JOIN {agregado} c ON c.cnpj = f.cnpj AND c.codigo = f.codigo
        ) TO '{_escapar(provisorio)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    os.replace(provisorio, fichas)


def _conferir_inventario(con, fontes: Fontes, ficha3: str, fichas: str, destino: str,
                         inicio, fim) -> dict:
    """O saldo de cada ficha em cada data de inventário do período, contra o bloco H.

    É o juiz da unidade e da completude: se a entrada viesse em caixa e a
    venda em unidade, ou se faltasse um tipo de saída, o saldo não fecharia com
    o estoque que a própria empresa declarou. Item ausente do bloco H numa data
    é estoque zero naquela data.
    """
    inventario = os.path.join(fontes.movimentacao, ARQUIVO_INVENTARIO)
    if not os.path.isfile(inventario) or not os.path.isfile(ficha3):
        return {}
    con.execute(f"""
        CREATE OR REPLACE TABLE inv_periodo AS
        SELECT v.cnpj, v.codigo, v.data_inventario,
               sum(v.quantidade * {_FATOR.format(t="v")}) AS inventario
        FROM read_parquet('{_escapar(inventario)}') v
        LEFT JOIN unid u ON u.cnpj = v.cnpj AND u.codigo = v.codigo
        LEFT JOIN conv cv ON cv.cnpj = v.cnpj AND cv.codigo = v.codigo AND cv.unidade = upper(trim(v.unidade))
        WHERE v.data_inventario BETWEEN DATE '{inicio}' AND DATE '{fim}'
        GROUP BY 1, 2, 3
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE alvo AS
        SELECT f.cnpj, f.codigo, d.data_inventario, f.abertura_quantidade
        FROM read_parquet('{_escapar(fichas)}') f
        JOIN (SELECT DISTINCT cnpj, data_inventario FROM inv_periodo) d ON d.cnpj = f.cnpj
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE saldo_dia AS
        SELECT cnpj, codigo, data, arg_max(saldo_quantidade, numero) AS saldo
        FROM read_parquet('{_escapar(ficha3)}') GROUP BY 1, 2, 3
    """)
    con.execute("""
        CREATE OR REPLACE TABLE conf0 AS
        SELECT a.cnpj, a.codigo, a.data_inventario, coalesce(s.saldo, a.abertura_quantidade) AS saldo_ficha
        FROM alvo a ASOF LEFT JOIN saldo_dia s
          ON s.cnpj = a.cnpj AND s.codigo = a.codigo AND a.data_inventario >= s.data
    """)
    con.execute(f"""
        COPY (
            SELECT c.cnpj, c.codigo, c.data_inventario, c.saldo_ficha,
                   coalesce(i.inventario, 0) AS inventario,
                   c.saldo_ficha - coalesce(i.inventario, 0) AS diferenca,
                   CASE
                     WHEN abs(c.saldo_ficha - coalesce(i.inventario, 0)) < 0.001 THEN 'bate'
                     WHEN abs(c.saldo_ficha - coalesce(i.inventario, 0))
                          <= greatest(1, 0.02 * abs(coalesce(i.inventario, 0))) THEN 'proxima'
                     WHEN c.saldo_ficha > 0 AND i.inventario > 0
                          AND {_RAZAO} >= 4
                          AND abs({_RAZAO} - round({_RAZAO})) <= 0.02 * {_RAZAO} THEN 'suspeita_unidade'
                     ELSE 'divergente'
                   END AS situacao
            FROM conf0 c
            LEFT JOIN inv_periodo i
              ON i.cnpj = c.cnpj AND i.codigo = c.codigo AND i.data_inventario = c.data_inventario
        ) TO '{_escapar(destino)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    linha = con.execute(f"""
        SELECT count(DISTINCT data_inventario), count(*),
               count(*) FILTER (saldo_ficha <> 0 OR inventario <> 0),
               count(*) FILTER ((saldo_ficha <> 0 OR inventario <> 0) AND situacao = 'bate'),
               count(*) FILTER ((saldo_ficha <> 0 OR inventario <> 0) AND situacao = 'proxima'),
               count(*) FILTER (situacao = 'divergente'),
               count(*) FILTER (situacao = 'suspeita_unidade'),
               count(DISTINCT cnpj || '|' || codigo) FILTER (situacao IN ('divergente', 'suspeita_unidade')),
               count(DISTINCT cnpj || '|' || codigo) FILTER (situacao = 'suspeita_unidade')
        FROM read_parquet('{_escapar(destino)}')
    """).fetchone()
    chaves = ("datas", "comparacoes", "com_estoque", "batem", "proximas", "divergentes",
              "suspeita_unidade", "fichas_divergentes", "fichas_suspeita_unidade")
    return dict(zip(chaves, linha))


# o fator da linha: 1 quando a unidade já é a do inventário (ou não se sabe
# nenhuma das duas); o do 0220 quando há; 1, marcado, quando não há
_FATOR = """
    CASE WHEN nullif(trim({t}.unidade), '') IS NULL OR u.unidade IS NULL
              OR upper(trim({t}.unidade)) = u.unidade THEN 1::DECIMAL(24, 9)
         WHEN cv.fator > 0 THEN cv.fator
         ELSE 1::DECIMAL(24, 9) END
"""
_SEM_FATOR = """
    (nullif(trim({t}.unidade), '') IS NOT NULL AND u.unidade IS NOT NULL
     AND upper(trim({t}.unidade)) <> u.unidade AND coalesce(cv.fator, 0) <= 0)
"""
_RAZAO = ("(greatest(c.saldo_ficha, i.inventario)::DOUBLE "
          "/ least(c.saldo_ficha, i.inventario)::DOUBLE)")


def _preparar(con, fontes: Fontes) -> dict:
    """Monta a tabela `lancamentos` e a `abertura`. Tudo em SQL, nada calculado."""
    mov = f"read_parquet('{_escapar(os.path.join(fontes.movimentacao, ARQUIVO_MOVIMENTOS))}')"
    sup = f"read_parquet('{_escapar(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO))}')"
    colunas_mov = pq.read_schema(os.path.join(fontes.movimentacao, ARQUIVO_MOVIMENTOS)).names
    # etapas de antes da v0.52 não guardam a série do documento: vai vazia
    serie_mov = "serie" if "serie" in colunas_mov else "NULL::VARCHAR"
    # e de antes da v0.53 não têm item do XML: toda saída com item é da EFD
    origem_mov = "coalesce(fonte_item, 'efd')" if "fonte_item" in colunas_mov else "'efd'"
    # o indFinal do XML diz se a NF-e foi a consumidor final
    consumidor_mov = "consumidor_final_xml" if "consumidor_final_xml" in colunas_mov else "NULL::BOOLEAN"
    # A alíquota da operação, que a Ficha 3 mostra em cada linha: a destacada no
    # documento e, no CST 60 — que não destaca nada —, a que o emitente informa
    # como efetiva (pICMSEfet). Não confundir com a alíquota do confronto, que é
    # a interna da mercadoria e só existe no enquadramento que confronta a saída.
    aliq_doc = " ".join(f'nullif(s.{c}, 0),' for c in ("aliq_icms", "aliquota_efetiva_xml")
                        if c in colunas_mov)
    aliq_doc = f"coalesce({aliq_doc} NULL)" if aliq_doc else "NULL::DECIMAL(9, 4)"
    # A base do confronto não é o valor da mercadoria: frete e despesas cobrados
    # do destinatário entram, e desconto sai (artigo 37, § 1º, 1 do RICMS/SP).
    # O XML já traz isso calculado em `base_do_item`; sem XML, vale a base do
    # C170; sem nenhuma das duas, o valor do item, como era antes da v0.60.
    base_mov = " ".join(f'nullif(s.{c}, 0),' for c in ("base_do_item_xml", "bc_icms")
                        if c in colunas_mov)
    base_mov = f"coalesce({base_mov} s.valor)"
    # o NCM diz de qual mercadoria é a redução de base: o do XML primeiro, o do
    # cadastro depois. Etapas antigas não têm nem uma coluna nem outra
    ncm_mov = ", ".join(f"nullif(s.{c}, '')" for c in ("ncm_xml", "ncm") if c in colunas_mov)
    ncm_mov = f"coalesce({ncm_mov})" if ncm_mov else "NULL::VARCHAR"
    colunas_sup = pq.read_schema(os.path.join(fontes.apuracao, ARQUIVO_SUPORTADO)).names
    serie_sup = "s.serie" if "serie" in colunas_sup else "NULL::VARCHAR"
    # apuração de antes da v0.53 não guarda o ICMS próprio: o confronto de 2 e 4 fica pendente
    proprio_sup = "s.icms_proprio" if "icms_proprio" in colunas_sup else "NULL::DECIMAL(18, 6)"
    itens = os.path.join(fontes.movimentacao, ARQUIVO_ITENS)
    conversoes = os.path.join(fontes.movimentacao, ARQUIVO_CONVERSOES)
    inventario = os.path.join(fontes.movimentacao, ARQUIVO_INVENTARIO)
    rel = fontes.saidas_do_relatorio
    tem_rel = bool(rel and os.path.isfile(rel))

    base_inicio, base_fim = con.execute(f"SELECT min(competencia), max(competencia) FROM {mov}").fetchone()
    if fontes.periodo:
        inicio, fim = fontes.periodo[0].replace(day=1), fontes.periodo[1]
    else:
        inicio, fim = base_inicio, base_fim
    # fim do último mês
    fim = (fim.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    lista = lambda conj: ", ".join(f"'{c}'" for c in sorted(conj))  # noqa: E731

    con.execute(f"CREATE OR REPLACE TABLE estabs AS SELECT DISTINCT cnpj FROM {mov}")
    if fontes.depara and os.path.isfile(fontes.depara):
        con.execute(f"""CREATE OR REPLACE TABLE depara AS
            SELECT cnpj, codigo_origem, any_value(codigo_destino) AS codigo_destino,
                   any_value(CAST(fator AS DECIMAL(24, 9))) AS fator
            FROM read_parquet('{_escapar(fontes.depara)}')
            WHERE codigo_origem <> codigo_destino AND fator > 0
            GROUP BY cnpj, codigo_origem""")
    else:
        con.execute("CREATE OR REPLACE TABLE depara (cnpj VARCHAR, codigo_origem VARCHAR, "
                    "codigo_destino VARCHAR, fator DECIMAL(24, 9))")
    con.execute(f"""
        CREATE OR REPLACE TABLE saidas_efd AS
        SELECT cnpj, codigo, data, replace(cfop, '.', '') AS cfop, cst_icms, modelo, unidade,
               {ncm_mov} AS ncm, {aliq_doc} AS aliquota_documento,
               quantidade, {base_mov} AS valor,
               coalesce(valor_icms, 0) + coalesce(valor_st, 0) AS suportado,
               coalesce(nullif(chave, ''), numero_documento) AS documento, chave,
               false AS pdv, {origem_mov} AS origem,
               numero_item, participante, numero_documento, {serie_mov} AS serie,
               {consumidor_mov} AS consumidor_final
        FROM {mov} s WHERE s.operacao = 'saida'
    """)

    sem_estab = trocado = do_cupom = chave_do_c100 = 0
    if tem_rel:
        con.execute(f"""
            CREATE OR REPLACE TABLE rel AS
            SELECT r.*,
                   CASE WHEN length(r.chave) = 44 AND substr(r.chave, 7, 14) IN (SELECT cnpj FROM estabs)
                            THEN substr(r.chave, 7, 14)
                        WHEN r.pdv AND r.cnpj_participante IN (SELECT cnpj FROM estabs)
                            THEN r.cnpj_participante
                        -- o relatório que traz a loja como CNPJ diz direto de
                        -- quem é a linha. Sem isto, a loja que não tem venda de
                        -- PDV (o CD) não aprendia o próprio CNPJ de ninguém e
                        -- as baixas dela iam para "sem estabelecimento"
                        WHEN r.unidade IN (SELECT cnpj FROM estabs) THEN r.unidade
                   END AS cnpj_direto
            FROM read_parquet('{_escapar(rel)}') r
            WHERE r.data BETWEEN DATE '{inicio}' AND DATE '{fim}'
        """)
        con.execute("""
            CREATE OR REPLACE TABLE unidade_cnpj AS
            SELECT unidade, mode(cnpj_direto) AS cnpj FROM rel
            WHERE cnpj_direto IS NOT NULL GROUP BY unidade
        """)
        con.execute("""
            CREATE OR REPLACE TABLE rel_com_cnpj AS
            SELECT r.*, coalesce(r.cnpj_direto, u.cnpj) AS cnpj
            FROM rel r LEFT JOIN unidade_cnpj u ON u.unidade = r.unidade
        """)
        sem_estab = con.execute("SELECT count(*) FROM rel_com_cnpj WHERE cnpj IS NULL").fetchone()[0]
        chave_do_c100 = _chave_do_c100(con, fontes, inicio, fim)
        # documento da EFD vence o relatório: a nota que tem item lá não entra
        # duas vezes. Pela chave, e — para o relatório que não traz chave — por
        # estabelecimento, número e data. Sem a segunda regra, as transferências
        # das "Saídas" do varejo do projeto 1 (98 mil linhas em janeiro, todas
        # com XML na base) entrariam em dobro. A série não entra na conta: o
        # relatório a escreve diferente da EFD ("3" contra "003") e só 80 de
        # 163 mil batiam. Número e data na mesma loja já separam a nota.
        con.execute(f"""
            CREATE OR REPLACE TABLE notas_com_item AS
            SELECT DISTINCT cnpj, ltrim(numero_documento, '0') AS numero, data
            FROM saidas_efd WHERE coalesce(numero_documento, '') <> ''
        """)
        con.execute(f"""
            CREATE OR REPLACE TABLE rel_com_cnpj AS
            SELECT r.*,
                   CASE WHEN length(r.chave) = 44
                            THEN r.chave IN (SELECT chave FROM saidas_efd WHERE length(chave) = 44)
                        ELSE (r.cnpj, ltrim(r.numero_documento, '0'), r.data) IN
                             (SELECT (cnpj, numero, data) FROM notas_com_item)
                   END AS ja_na_efd,
                   replace(r.cfop, '.', '') IN ({lista(CFOP_REGISTRADO_EM_CUPOM)}) AS do_cupom
            FROM rel_com_cnpj r
        """)
        trocado = con.execute("SELECT count(*) FROM rel_com_cnpj WHERE ja_na_efd").fetchone()[0]
        do_cupom = con.execute(
            "SELECT count(*) FROM rel_com_cnpj WHERE do_cupom AND NOT ja_na_efd").fetchone()[0]
        con.execute("""
            CREATE OR REPLACE TABLE saidas_rel AS
            SELECT cnpj, codigo, data, cfop, cst_icms,
                   CASE WHEN length(chave) = 44 THEN substr(chave, 21, 2) ELSE '' END AS modelo,
                   -- a "Qtde;Unitária" do relatório já é a unidade básica
                   NULL::VARCHAR AS unidade,
                   -- o relatório não traz NCM nem alíquota: vêm do 0200
                   NULL::VARCHAR AS ncm, NULL::DECIMAL(9, 4) AS aliquota_documento,
                   quantidade, valor, suportado,
                   coalesce(nullif(chave, ''), 'relatorio|' || unidade || '|' || numero_documento) AS documento,
                   chave, pdv, 'relatorio' AS origem,
                   -- o relatório não traz nº do item nem código de participante:
                   -- a linha calcula a ficha, mas não vira registro do arquivo digital
                   NULL::INTEGER AS numero_item, '' AS participante, numero_documento,
                   NULL::VARCHAR AS serie, CASE WHEN pdv THEN true END AS consumidor_final
            FROM rel_com_cnpj
            -- a NF-e de 5.929 é papel de uma venda que o cupom já contou
            WHERE cnpj IS NOT NULL AND NOT ja_na_efd AND NOT do_cupom
        """)
        saidas = "(SELECT * FROM saidas_efd UNION ALL BY NAME SELECT * FROM saidas_rel)"
    else:
        saidas = "saidas_efd"

    con.execute(f"""
        CREATE OR REPLACE TABLE codigos AS
        SELECT DISTINCT coalesce(d.codigo_destino, s.codigo) AS codigo FROM {saidas} s
        LEFT JOIN depara d ON d.cnpj = s.cnpj AND d.codigo_origem = s.codigo
        WHERE right(coalesce(s.cst_icms, ''), 2) = '60'
          AND replace(s.cfop, '.', '') NOT IN ({lista(CFOP_USO_E_CONSUMO | CFOP_OUTRAS_X949)})
    """)
    codigos = con.execute("SELECT count(*) FROM codigos").fetchone()[0]
    if os.path.isfile(itens):
        ncm_cad = "nullif(i.ncm, '')" if "ncm" in pq.read_schema(itens).names else "NULL::VARCHAR"
        con.execute(f"""CREATE OR REPLACE TABLE unid AS
            SELECT i.cnpj, i.codigo, nullif(upper(trim(i.unidade)), '') AS unidade, i.aliq_icms,
                   {ncm_cad} AS ncm
            FROM read_parquet('{_escapar(itens)}') i""")
    else:
        con.execute("CREATE OR REPLACE TABLE unid (cnpj VARCHAR, codigo VARCHAR, unidade VARCHAR, "
                    "aliq_icms DECIMAL(9, 4), ncm VARCHAR)")
    # A alíquota do confronto é a do mês da saída, não a do fim do período: na
    # empresa 19, 23 mil itens mudaram de alíquota dentro de 2021 (12% para 13,3% em
    # fevereiro). A unidade continua a mais recente — é nela que a ficha inteira
    # é contada, e mudar de unidade no meio da ficha quebraria o saldo.
    itens_do_mes = os.path.join(fontes.movimentacao, ARQUIVO_ITENS_DA_EFD)
    if os.path.isfile(itens_do_mes):
        con.execute(f"""CREATE OR REPLACE TABLE aliq_mes AS
            SELECT cnpj, codigo, competencia, aliq_icms
            FROM read_parquet('{_escapar(itens_do_mes)}')
            WHERE aliq_icms IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY cnpj, codigo, competencia ORDER BY arquivo DESC) = 1""")
    else:
        con.execute("CREATE OR REPLACE TABLE aliq_mes (cnpj VARCHAR, codigo VARCHAR, competencia DATE, aliq_icms DECIMAL(9, 4))")
    if os.path.isfile(conversoes):
        con.execute(f"""CREATE OR REPLACE TABLE conv AS
            SELECT cnpj, codigo, upper(trim(unidade)) AS unidade, fator
            FROM read_parquet('{_escapar(conversoes)}')""")
    else:
        con.execute("CREATE OR REPLACE TABLE conv (cnpj VARCHAR, codigo VARCHAR, unidade VARCHAR, fator DECIMAL(24, 9))")
    aliq_doc_entrada = aliq_doc.replace("s.", "")
    # a unidade de cada entrada está na movimentação, não na apuração
    con.execute(f"""
        CREATE OR REPLACE TABLE unidade_das_entradas AS
        SELECT cnpj, chave, numero_documento, data, numero_item, codigo, any_value(unidade) AS unidade,
               any_value(valor) AS valor, max({aliq_doc_entrada}) AS aliquota_documento
        FROM {mov} WHERE operacao = 'entrada'
        GROUP BY cnpj, chave, numero_documento, data, numero_item, codigo
    """)

    con.execute(f"""
        CREATE OR REPLACE TABLE lancamentos AS
        SELECT l.* REPLACE (coalesce(d.codigo_destino, l.codigo) AS codigo,
                            -- o NCM da nota, e o do cadastro quando ela não traz
                            coalesce(l.ncm, u.ncm, ud.ncm) AS ncm),
               l.codigo AS codigo_original,
               coalesce(am.aliq_icms, u.aliq_icms, ud.aliq_icms) AS aliquota, u.unidade AS unidade_estoque,
               (am.aliq_icms IS NOT NULL AND u.aliq_icms IS NOT NULL
                AND am.aliq_icms <> u.aliq_icms) AS aliquota_do_mes_diferente,
               {_FATOR.format(t="l")} * coalesce(d.fator, 1) AS fator, {_SEM_FATOR.format(t="l")} AS sem_fator
        FROM (
            SELECT s.cnpj, s.codigo, s.data, replace(s.cfop, '.', '') AS cfop, s.cst_icms, s.modelo,
                   ue.unidade, NULL::VARCHAR AS ncm, ue.aliquota_documento,
                   -- o VL_ITEM da entrada está na movimentação: a apuração do
                   -- suportado guarda o imposto, não o valor do item
                   s.quantidade, ue.valor, s.suportado,
                   coalesce(nullif(s.chave, ''), s.numero_documento) AS documento,
                   false AS pdv, 'efd' AS origem,
                   CASE WHEN replace(s.cfop, '.', '') IN ({lista(_DEVOLUCAO_DE_VENDA)}) THEN 'saida' ELSE 'entrada' END AS especie,
                   replace(s.cfop, '.', '') IN ({lista(_DEVOLUCAO_DE_VENDA)}) AS devolucao,
                   1 AS prioridade,
                   s.chave, s.numero_item, s.participante, s.numero_documento, {serie_sup} AS serie,
                   NULL::BOOLEAN AS consumidor_final, {proprio_sup} AS icms_proprio
            FROM {sup} s
            LEFT JOIN unidade_das_entradas ue
              ON ue.cnpj = s.cnpj AND ue.chave = s.chave AND ue.numero_documento = s.numero_documento
             AND ue.data = s.data AND ue.numero_item = s.numero_item AND ue.codigo = s.codigo
            UNION ALL
            SELECT s.cnpj, s.codigo, s.data, s.cfop, s.cst_icms, s.modelo, s.unidade, s.ncm,
                   s.aliquota_documento,
                   s.quantidade, s.valor, s.suportado, s.documento, s.pdv, s.origem,
                   CASE WHEN s.cfop IN ({lista(_DEVOLUCAO_DE_COMPRA)}) THEN 'entrada' ELSE 'saida' END,
                   s.cfop IN ({lista(_DEVOLUCAO_DE_COMPRA)}),
                   2,
                   s.chave, s.numero_item, s.participante, s.numero_documento, s.serie, s.consumidor_final,
                   NULL::DECIMAL(18, 6) AS icms_proprio
            FROM {saidas} s
        ) l
        LEFT JOIN unid u ON u.cnpj = l.cnpj AND u.codigo = l.codigo
        LEFT JOIN aliq_mes am ON am.cnpj = l.cnpj AND am.codigo = l.codigo
                             AND am.competencia = date_trunc('month', l.data)::DATE
        LEFT JOIN conv cv ON cv.cnpj = l.cnpj AND cv.codigo = l.codigo AND cv.unidade = upper(trim(l.unidade))
        LEFT JOIN depara d ON d.cnpj = l.cnpj AND d.codigo_origem = l.codigo
        LEFT JOIN unid ud ON ud.cnpj = l.cnpj AND ud.codigo = d.codigo_destino
        WHERE coalesce(d.codigo_destino, l.codigo) IN (SELECT codigo FROM codigos)
          AND l.cnpj IN (SELECT cnpj FROM estabs)
          AND l.data BETWEEN DATE '{inicio}' AND DATE '{fim}'
    """)
    _reducoes(con, fontes, mov, colunas_mov)
    correcoes = _correcoes(con, fontes)

    # uso e consumo não é estoque de comercialização: sai da ficha e fica contado
    uso_e_consumo = con.execute(
        f"SELECT count(*) FROM lancamentos WHERE cfop IN ({lista(CFOP_USO_E_CONSUMO)})").fetchone()[0]
    if uso_e_consumo:
        con.execute(f"DELETE FROM lancamentos WHERE cfop IN ({lista(CFOP_USO_E_CONSUMO)})")
    # X.949 também: remessa e retorno não são compra nem venda
    x949 = con.execute(f"SELECT count(*) FROM lancamentos WHERE cfop IN ({lista(CFOP_OUTRAS_X949)})").fetchone()[0]
    if x949:
        con.execute(f"DELETE FROM lancamentos WHERE cfop IN ({lista(CFOP_OUTRAS_X949)})")

    abertura_em = None
    if os.path.isfile(inventario):
        abertura_em = con.execute(f"""
            SELECT max(data_inventario) FROM read_parquet('{_escapar(inventario)}')
            WHERE data_inventario < DATE '{inicio}'
        """).fetchone()[0]
    if abertura_em is not None:
        con.execute(f"""
            CREATE OR REPLACE TABLE abertura AS
            SELECT v.cnpj, coalesce(d.codigo_destino, v.codigo) AS codigo,
                   sum(v.quantidade * {_FATOR.format(t="v")} * coalesce(d.fator, 1)) AS quantidade,
                   bool_or({_SEM_FATOR.format(t="v")}) AS sem_fator
            FROM read_parquet('{_escapar(inventario)}') v
            LEFT JOIN unid u ON u.cnpj = v.cnpj AND u.codigo = v.codigo
            LEFT JOIN conv cv ON cv.cnpj = v.cnpj AND cv.codigo = v.codigo AND cv.unidade = upper(trim(v.unidade))
            LEFT JOIN depara d ON d.cnpj = v.cnpj AND d.codigo_origem = v.codigo
            WHERE v.data_inventario = DATE '{abertura_em}'
              AND coalesce(d.codigo_destino, v.codigo) IN (SELECT codigo FROM codigos)
              AND v.cnpj IN (SELECT cnpj FROM estabs)
            GROUP BY v.cnpj, coalesce(d.codigo_destino, v.codigo) HAVING sum(v.quantidade) <> 0
        """)
    else:
        con.execute("CREATE OR REPLACE TABLE abertura (cnpj VARCHAR, codigo VARCHAR, "
                    "quantidade DECIMAL(38, 9), sem_fator BOOLEAN)")
    _juntar_saldo_anterior(con, fontes.saldo_anterior)
    abertura_sem_fator = con.execute("SELECT count(*) FROM abertura WHERE sem_fator").fetchone()[0]

    # as entradas até o dia do inventário, na unidade da ficha: é delas que o
    # estoque de abertura veio (item 3.3.8). Só existem se a base tiver meses
    # antes do período do trabalho
    if abertura_em is not None:
        con.execute(f"""
            CREATE OR REPLACE TABLE anteriores AS
            SELECT e.cnpj, coalesce(d.codigo_destino, e.codigo) AS codigo, e.data, coalesce(e.chave, '') AS chave,
                   coalesce(e.numero_item, 0) AS numero_item,
                   e.quantidade * {_FATOR.format(t="e")} * coalesce(d.fator, 1) AS quantidade,
                   coalesce(e.suportado, 0) AS suportado
            FROM (
                SELECT s.cnpj, s.codigo, s.data, s.cfop, s.chave, s.numero_item, s.quantidade, s.suportado,
                       ue.unidade
                FROM {sup} s
                LEFT JOIN unidade_das_entradas ue
                  ON ue.cnpj = s.cnpj AND ue.chave = s.chave AND ue.numero_documento = s.numero_documento
                 AND ue.data = s.data AND ue.numero_item = s.numero_item AND ue.codigo = s.codigo
                WHERE s.data <= DATE '{abertura_em}'
            ) e
            LEFT JOIN unid u ON u.cnpj = e.cnpj AND u.codigo = e.codigo
            LEFT JOIN conv cv ON cv.cnpj = e.cnpj AND cv.codigo = e.codigo AND cv.unidade = upper(trim(e.unidade))
            LEFT JOIN depara d ON d.cnpj = e.cnpj AND d.codigo_origem = e.codigo
            WHERE replace(e.cfop, '.', '') NOT IN ({lista(_DEVOLUCAO_DE_VENDA)})
              AND replace(e.cfop, '.', '') NOT IN ({lista(CFOP_USO_E_CONSUMO | CFOP_OUTRAS_X949)})
              AND e.quantidade > 0
              AND EXISTS (SELECT 1 FROM abertura a
                          WHERE a.cnpj = e.cnpj AND a.codigo = coalesce(d.codigo_destino, e.codigo))
        """)
    else:
        con.execute("CREATE OR REPLACE TABLE anteriores (cnpj VARCHAR, codigo VARCHAR, data DATE, chave VARCHAR, "
                    "numero_item INTEGER, quantidade DECIMAL(38, 9), suportado DECIMAL(38, 15))")

    return {"inicio": inicio, "fim": fim, "abertura_em": abertura_em, "codigos": codigos,
            "correcoes": correcoes,
            "sem_estabelecimento": sem_estab, "trocado_pela_efd": trocado,
            "chave_do_c100": chave_do_c100,
            "registrado_em_cupom": do_cupom,
            "abertura_sem_fator": abertura_sem_fator, "uso_e_consumo": uso_e_consumo, "x949": x949,
            "base_inicio": base_inicio, "base_fim": base_fim,
            # apuração de antes da v0.53: sem o ICMS próprio, não se sabe se houve
            # destaque, e o confronto de 2 e 4 fica pendente como era
            "tem_icms_proprio": "icms_proprio" in colunas_sup}


# ---------------------------------------------------------------------------
# o percurso, ficha a ficha
# ---------------------------------------------------------------------------
def _correcoes(con, fontes) -> dict[str, int]:
    """Aplica em `lancamentos` o que uma pessoa corrigiu à mão.

    A correção é do trabalho e não toca o dado de origem: o parquet do
    documento continua como o documento é. Aqui ela entra na conta, e a linha
    fica marcada — `corrigida` — para a Ficha 3 mostrar de onde veio o número.

    A ordem importa: alíquota e redução da mercadoria valem para todas as
    linhas dela e entram depois de tudo o que o sistema deduziu, porque a
    correção é a última palavra. A exclusão vem por último, porque não adianta
    corrigir o que sai da ficha.
    """
    con.execute("ALTER TABLE lancamentos ADD COLUMN enquadramento_corrigido TINYINT")
    con.execute("ALTER TABLE lancamentos ADD COLUMN corrigida BOOLEAN DEFAULT false")
    caminho = fontes.correcoes
    if not caminho or not os.path.isfile(caminho):
        return {}
    con.execute(f"""CREATE OR REPLACE TABLE correcoes AS
        SELECT campo, coalesce(cnpj, '') AS cnpj, coalesce(codigo, '') AS codigo,
               coalesce(documento, '') AS documento, numero_item, valor
        FROM read_parquet('{_escapar(caminho)}')""")
    # o alvo: mercadoria (código, e o CNPJ quando informado) ou linha
    de_mercadoria = ("c.codigo = lancamentos.codigo "
                     "AND (c.cnpj = '' OR c.cnpj = lancamentos.cnpj)")
    de_linha = ("c.documento = lancamentos.documento AND c.numero_item = lancamentos.numero_item "
                "AND (c.cnpj = '' OR c.cnpj = lancamentos.cnpj)")
    colunas = {
        Campo.ALIQUOTA: ("aliquota", "DECIMAL(9, 4)", de_mercadoria),
        Campo.REDUCAO_BASE: ("reducao_base", "DECIMAL(9, 4)", de_mercadoria),
        Campo.ENQUADRAMENTO: ("enquadramento_corrigido", "TINYINT", de_linha),
        Campo.QUANTIDADE: ("quantidade", "DECIMAL(24, 6)", de_linha),
        Campo.VALOR_ITEM: ("valor", "DECIMAL(20, 6)", de_linha),
        Campo.ICMS_SUPORTADO: ("suportado", "DECIMAL(20, 6)", de_linha),
    }
    aplicadas: dict[str, int] = {}
    for campo, (coluna, tipo, onde) in colunas.items():
        existe = (f"EXISTS (SELECT 1 FROM correcoes c WHERE c.campo = '{campo.value}' AND {onde})")
        atingidas = con.execute(f"SELECT count(*) FROM lancamentos WHERE {existe}").fetchone()[0]
        if not atingidas:
            continue
        con.execute(f"""UPDATE lancamentos
            SET {coluna} = (SELECT CAST(c.valor AS {tipo}) FROM correcoes c
                            WHERE c.campo = '{campo.value}' AND {onde} LIMIT 1),
                corrigida = true
            WHERE {existe}""")
        aplicadas[campo.value] = atingidas
    # a quantidade corrigida vem sempre positiva: o sinal é da espécie
    if Campo.QUANTIDADE.value in aplicadas:
        con.execute("""UPDATE lancamentos SET quantidade = -abs(quantidade)
            WHERE corrigida AND especie = 'saida' AND NOT devolucao AND quantidade > 0""")
    fora = (f"EXISTS (SELECT 1 FROM correcoes c WHERE c.campo = '{Campo.EXCLUIDA.value}' "
            f"AND c.valor = 'sim' AND {de_linha})")
    excluidas = con.execute(f"SELECT count(*) FROM lancamentos WHERE {fora}").fetchone()[0]
    if excluidas:
        con.execute(f"DELETE FROM lancamentos WHERE {fora}")
        aplicadas[Campo.EXCLUIDA.value] = excluidas
    if aplicadas:
        log.info("correções à mão aplicadas", extra=aplicadas)
    return aplicadas


# ---------------------------------------------------------------------------
# a alíquota interna da mercadoria, quando o 0200 não a traz
# ---------------------------------------------------------------------------
# O cadastro é a fonte natural — e falha calado. Na empresa 04 eram 13.909
# saídas de quatro códigos sem 0200 em arquivo nenhum; na empresa 26, 2.228
# saídas **todas de CST 60**, de mercadoria que o cliente nunca comprou com
# aquele código. Sem alíquota não há confronto, e sem confronto não há
# ressarcimento: a linha some do pedido sem ninguém ver.
#
# A entrada da mesma mercadoria diz a alíquota de três jeitos, nesta ordem de
# prova (decisão do Victor, 17/09/2026, estendida em 14/10/2026):
#
# * `interna` — o ICMS **destacado** numa entrada dentro do estado. É a
#   alíquota que o fornecedor usou na operação própria. A compra de fora não
#   serve: ela vem com 4%, 7% ou 12%, que não são a tributação interna.
# * `st` — o `pICMSST` de uma entrada com ST retido (CST 10, 30, 70). O
#   substituto calcula a retenção com a alíquota interna **do destino**, então
#   esta serve mesmo quando a compra veio de outro estado — e só existe onde a
#   mercadoria estava em ST naquela data, que é exatamente o caso que se quer.
# * `efetiva` — o `pICMSEfet` do CST 60, que é a interna **já reduzida**. Por
#   isso ela só entra onde a mercadoria não tem redução: com redução, o
#   confronto reduziria a base uma segunda vez.
FONTES_DA_ALIQUOTA = ("interna", "st", "efetiva")

# a coluna do documento e a condição extra de cada fonte; `{cfop}` recebe o
# teste de operação interna, que só a alíquota destacada exige
_FONTES_NO_XML = {"interna": ("aliq_icms", "{cfop}"), "st": ("aliq_st", "true"),
                  "efetiva": ("aliquota_efetiva", "true")}
_FONTES_NA_EFD = {"interna": ("aliq_icms", "{cfop}"), "st": ("aliq_st", "true"),
                  "efetiva": ("aliquota_efetiva_xml", "true")}

# por onde se procura a mercadoria, da chave mais perto dela para a mais larga:
# o código do item é a própria mercadoria; o NCM é a classificação, que alcança
# o código que nunca foi comprado — e é o que resolve o CST 60 da empresa 26
_CHAVES_DA_ALIQUOTA = (
    ("item", "aliq_item", "a.cnpj = lancamentos.cnpj AND a.codigo = lancamentos.codigo"),
    ("ncm", "aliq_ncm", "a.ncm = lancamentos.ncm"),
)


def _uniao(selects: list[str], vazia: str) -> str:
    """As fontes somadas, ou uma relação vazia com as mesmas colunas.

    A base que não traz coluna nenhuma delas precisa de uma tabela vazia, não
    de um erro de sintaxe: ficar sem alíquota é um resultado, não uma falha.
    """
    if selects:
        return " UNION ALL ".join(selects)
    return (f"SELECT {vazia}, NULL::DATE AS data, NULL::DECIMAL(9, 4) AS aliquota, "
            "NULL::VARCHAR AS fonte WHERE false")


def _completar_aliquota(con) -> dict[str, int]:
    """Preenche `lancamentos.aliquota` com o que as entradas dizem.

    Duas passadas, e **a ordem entre elas é o que respeita o período**: primeiro
    todas as fontes que têm uma entrada até a data da saída, e só no que sobrar
    a primeira entrada que houver. Uma alíquota de 2024 numa saída de 2021 erra
    mais do que uma alíquota mais larga do mês certo — e erra calada, porque
    sai no relatório como qualquer outra.

    Cada linha guarda em `aliquota_origem` de onde a dela veio, para a Ficha 3
    mostrar e para ninguém confundir o que foi lido com o que foi deduzido.
    """
    con.execute("ALTER TABLE lancamentos ADD COLUMN aliquota_origem VARCHAR")
    ordem = [(f"{chave}_{fonte}", tabela, liga, fonte)
             for chave, tabela, liga in _CHAVES_DA_ALIQUOTA for fonte in FONTES_DA_ALIQUOTA]
    for no_periodo in (True, False):
        for nome, tabela, liga, fonte in ordem:
            casa = f"{liga} AND a.fonte = '{fonte}'"
            ate_a_data = " AND a.data <= lancamentos.data" if no_periodo else ""
            ordena = "a.data DESC" if no_periodo else "a.data"
            sem_reducao = " AND reducao_base IS NULL" if fonte == "efetiva" else ""
            con.execute(f"""UPDATE lancamentos SET
                    aliquota = (SELECT a.aliquota FROM {tabela} a
                                WHERE {casa}{ate_a_data} ORDER BY {ordena} LIMIT 1),
                    aliquota_origem = '{nome}'
                WHERE aliquota IS NULL{sem_reducao}
                  AND EXISTS (SELECT 1 FROM {tabela} a WHERE {casa}{ate_a_data})""")
    con.execute("UPDATE lancamentos SET aliquota_da_entrada = aliquota_origem IS NOT NULL")
    lidas = dict(con.execute(
        "SELECT aliquota_origem, count(*) FROM lancamentos WHERE aliquota_origem IS NOT NULL "
        "GROUP BY 1 ORDER BY 1").fetchall())
    sobraram = con.execute(
        "SELECT count(*) FROM lancamentos WHERE aliquota IS NULL").fetchone()[0]
    log.info("alíquota lida na entrada onde falta 0200",
             extra={"resolvidas": sum(lidas.values()), "sem_aliquota": sobraram, **lidas})
    return lidas


def _reducoes(con, fontes, mov: str, colunas_mov: list[str]) -> None:
    """Põe em `lancamentos.reducao_base` a redução de base da mercadoria.

    Quem declara a redução é a entrada, com CST 20 ou 70. O percentual sai da
    base que a nota de fato usou, e não do `pRedBC` — que o fornecedor da
    empresa 04 preenche ao contrário (ver `cat.dominio.icms.cat42.reducao`). O
    benefício é da mercadoria, então a chave é o NCM, e cada saída herda a
    redução da entrada mais recente até a data dela; antes da primeira entrada,
    a primeira que houver.
    """
    cst = ", ".join(f"'{c}'" for c in sorted(CST_COM_REDUCAO))
    fontes_sql: list[str] = []
    aliq_sql: list[str] = []
    aliq_item_sql: list[str] = []
    xml_itens = os.path.join(fontes.movimentacao, ARQUIVO_ITENS_DO_XML)
    colunas_xml = set(pq.read_schema(xml_itens).names) if os.path.isfile(xml_itens) else set()
    # o pRedBC do documento, que é o percentual de redução que vale
    declarada_xml = "x.reducao_declarada" if "reducao_declarada" in colunas_xml else "NULL::DECIMAL(9, 4)"
    declarada_efd = ("m.reducao_declarada_xml" if "reducao_declarada_xml" in colunas_mov
                     else "NULL::DECIMAL(9, 4)")
    de_fora = {"ncm", "emissao", "destinatario", "emitente", "cfop"}
    # Só entrada **interna** empresta alíquota e redução: o confronto do
    # enquadramento 1 é de uma saída dentro do estado, e a compra de fora vem
    # com 4%, 7% ou 12%, que não são a tributação interna da mercadoria. No XML
    # o CFOP é o do emitente (5.xxx é interna); na EFD, o nosso (1.xxx).
    interna_xml = "left(replace(coalesce(x.cfop, ''), '.', ''), 1) = '5'"
    interna_efd = "left(replace(coalesce(m.cfop, ''), '.', ''), 1) = '1'"
    if de_fora | {"cst_icms", "bc_icms", "valor", "desconto"} <= colunas_xml:  # noqa: SIM300
        # o XML vence: na empresa 04, a EFD escritura a entrada com CST 70 e
        # zera base e imposto, e só o XML do fornecedor tem a base reduzida
        fontes_sql.append(f"""
            SELECT nullif(x.ncm, '') AS ncm, x.emissao AS data, x.cst_icms,
                   x.bc_icms, x.valor, x.desconto, {declarada_xml} AS declarada
            FROM read_parquet('{_escapar(xml_itens)}') x
            WHERE x.destinatario IN (SELECT cnpj FROM estabs)
              AND x.emitente NOT IN (SELECT cnpj FROM estabs)
              AND right(coalesce(x.cst_icms, ''), 2) IN ({cst}) AND x.bc_icms > 0
              AND {interna_xml}""")
    de_estab = ("x.destinatario IN (SELECT cnpj FROM estabs) "
                "AND x.emitente NOT IN (SELECT cnpj FROM estabs)")
    for fonte, (col, onde) in _FONTES_NO_XML.items():
        if not de_fora | {col} <= colunas_xml:
            continue
        aliq_sql.append(f"""
            SELECT nullif(x.ncm, '') AS ncm, x.emissao AS data, x.{col} AS aliquota,
                   '{fonte}' AS fonte
            FROM read_parquet('{_escapar(xml_itens)}') x
            WHERE {de_estab} AND x.{col} > 0 AND {onde.format(cfop=interna_xml)}""")
        if {"chave", "codigo"} <= colunas_xml and {"chave", "codigo_xml"} <= set(colunas_mov):
            # o código do item no XML é o **do fornecedor**; quem o devolve ao
            # código do cliente é a própria movimentação, que casou os dois
            aliq_item_sql.append(f"""
                SELECT m.cnpj, coalesce(d.codigo_destino, m.codigo) AS codigo, m.data,
                       x.{col} AS aliquota, '{fonte}' AS fonte
                FROM read_parquet('{_escapar(xml_itens)}') x
                JOIN {mov} m ON m.chave = x.chave AND m.codigo_xml = x.codigo
                 AND m.operacao = 'entrada'
                LEFT JOIN depara d ON d.cnpj = m.cnpj AND d.codigo_origem = m.codigo
                WHERE {de_estab} AND x.{col} > 0 AND {onde.format(cfop=interna_xml)}""")
    if {"ncm", "bc_icms", "desconto", "cfop"} <= set(colunas_mov):
        fontes_sql.append(f"""
            SELECT nullif(m.ncm, '') AS ncm, m.data, m.cst_icms, m.bc_icms, m.valor, m.desconto,
                   {declarada_efd} AS declarada
            FROM {mov} m
            WHERE m.operacao = 'entrada'
              AND right(coalesce(m.cst_icms, ''), 2) IN ({cst}) AND m.bc_icms > 0
              AND {interna_efd}""")
    for fonte, (col, onde) in _FONTES_NA_EFD.items():
        if not {"ncm", "cfop", col} <= set(colunas_mov):
            continue
        aliq_sql.append(f"""
            SELECT nullif(m.ncm, '') AS ncm, m.data, m.{col} AS aliquota, '{fonte}' AS fonte
            FROM {mov} m WHERE m.operacao = 'entrada' AND m.{col} > 0
              AND {onde.format(cfop=interna_efd)}""")
        aliq_item_sql.append(f"""
            SELECT m.cnpj, coalesce(d.codigo_destino, m.codigo) AS codigo, m.data,
                   m.{col} AS aliquota, '{fonte}' AS fonte
            FROM {mov} m
            LEFT JOIN depara d ON d.cnpj = m.cnpj AND d.codigo_origem = m.codigo
            WHERE m.operacao = 'entrada' AND m.{col} > 0 AND {onde.format(cfop=interna_efd)}""")
    por_dia: dict[tuple[str, date], list[Decimal]] = {}
    if fontes_sql:
        for ncm, data, cst_item, base, valor, desconto, declarada in con.execute(
                " UNION ALL ".join(fontes_sql)).fetchall():
            reduzida = reducao_da_entrada(cst_item, base, valor, desconto, declarada)
            if reduzida is None or not ncm or data is None:
                continue
            por_dia.setdefault((ncm, data), []).append(reduzida)
    con.execute("ALTER TABLE lancamentos ADD COLUMN reducao_base DECIMAL(9, 4)")
    con.execute("ALTER TABLE lancamentos ADD COLUMN aliquota_da_entrada BOOLEAN DEFAULT false")
    if por_dia:
        # o dia com mais de uma entrada fica com a mediana: um item digitado
        # errado não muda a redução da mercadoria inteira
        lidas = pa.Table.from_pylist(
            # a mediana de um número par de entradas é uma média, e média de
            # decimal estoura as quatro casas do esquema
            [{"ncm": n, "data": d, "reducao": median(v).quantize(_Q4)}
             for (n, d), v in sorted(por_dia.items())],
            schema=pa.schema([("ncm", pa.string()), ("data", pa.date32()),
                              ("reducao", pa.decimal128(9, 4))]))
        con.register("reducoes_lidas", lidas)
        con.execute("CREATE OR REPLACE TABLE reducoes AS SELECT * FROM reducoes_lidas")
        con.unregister("reducoes_lidas")
        con.execute("""UPDATE lancamentos SET reducao_base = (
                SELECT r.reducao FROM reducoes r
                WHERE r.ncm = lancamentos.ncm AND r.data <= lancamentos.data
                ORDER BY r.data DESC LIMIT 1)
            WHERE ncm IS NOT NULL""")
        # a saída anterior à primeira entrada herda a primeira redução que houver
        con.execute("""UPDATE lancamentos SET reducao_base = (
                SELECT r.reducao FROM reducoes r
                WHERE r.ncm = lancamentos.ncm ORDER BY r.data LIMIT 1)
            WHERE reducao_base IS NULL AND ncm IS NOT NULL""")
    log.info("redução de base lida das entradas",
             extra={"mercadorias": len({n for n, _ in por_dia}), "dias": len(por_dia)})

    con.execute(f"""CREATE OR REPLACE TABLE aliq_ncm AS
        SELECT ncm, data, fonte, CAST(median(aliquota) AS DECIMAL(9, 4)) AS aliquota
        FROM ({_uniao(aliq_sql, "NULL::VARCHAR AS ncm")})
        WHERE ncm IS NOT NULL AND data IS NOT NULL GROUP BY ncm, data, fonte""")
    con.execute(f"""CREATE OR REPLACE TABLE aliq_item AS
        SELECT cnpj, codigo, data, fonte, CAST(median(aliquota) AS DECIMAL(9, 4)) AS aliquota
        FROM ({_uniao(aliq_item_sql, "NULL::VARCHAR AS cnpj, NULL::VARCHAR AS codigo")})
        WHERE codigo IS NOT NULL AND data IS NOT NULL GROUP BY cnpj, codigo, data, fonte""")
    _completar_aliquota(con)

    # o documento nem sempre diz a alíquota: o CST 60 não destaca nada, e nem
    # todo emitente preenche o pICMSEfet (na empresa 04, 35.448 dos 81.157
    # itens). Nessas linhas a Ficha 3 mostra a alíquota interna da mercadoria,
    # que é o que a operação teria — é o que o papel de trabalho faz
    con.execute("""UPDATE lancamentos SET aliquota_documento = aliquota
        WHERE aliquota_documento IS NULL AND aliquota IS NOT NULL""")


def _enquadrar(linha: dict, venda_a_consumidor: VendaAConsumidor) -> tuple[EnquadramentoLegal | None, bool]:
    enq = classificar(linha["cfop"] or "", linha["cst_icms"] or "",
                      consumidor_final=True if linha["pdv"] else linha.get("consumidor_final"),
                      modelo=linha["modelo"] or "",
                      venda_a_consumidor=venda_a_consumidor)
    return enq, enq is None


def _confronto(enq: EnquadramentoLegal, linha: dict,
               entradas: list[EntradaAnterior] | None = None
               ) -> tuple[Decimal | None, bool, bool, Decimal | None]:
    """(ICMS efetivo, faltou alíquota, confronto pendente, redução aplicada).

    Enquadramentos 1 e 3 confrontam com a alíquota interna vezes o valor da
    saída (leiaute, VL_CONFR). Os 2 e 4 confrontam com o ICMS da operação
    própria das entradas com destaque mais recentes da ficha até a saída (item
    3.3.8); sem nenhuma, ficam pendentes aqui e `_resolver_sem_destaque` decide
    no fechamento da ficha.

    No enquadramento 1 — e só nele, por decisão do Victor de 17/09/2026 — a
    alíquota incide sobre a base já reduzida, quando a entrada da mercadoria
    declara redução (`cat.dominio.icms.cat42.reducao`).
    """
    if not enq.gera_ressarcimento:
        return None, False, False, None
    if not enq.confronta_com_saida:
        if not entradas:
            return None, False, True, None
        quantidade = Decimal(linha["quantidade"] or 0) * Decimal(linha["fator"] or 1)
        return valor_da_abertura(abs(quantidade), entradas).valor.quantize(_Q6), False, False, None
    aliquota = linha["aliquota"]
    valor = linha["valor"]
    if not aliquota or valor is None:
        return None, True, False, None
    reducao = linha.get("reducao_base") if enq is EnquadramentoLegal.CONSUMIDOR_FINAL else None
    reducao = Decimal(reducao) if reducao else None
    return (icms_efetivo_da_saida(Decimal(valor), Decimal(aliquota), reducao).quantize(_Q6),
            False, False, reducao)


def _percorrer(leitor, aberturas: dict, ficha3: str, fichas: str, resumo: ResumoDaMontagem,
               total: int, uf_por_cnpj: dict, descricoes: dict, avisar, deve_parar,
               venda_a_consumidor: VendaAConsumidor = VendaAConsumidor.ENQUADRAMENTO_1,
               valores: dict | None = None, origens: dict | None = None,
               resolver_sem_destaque: bool = True) -> None:
    escritor = pq.ParquetWriter(ficha3, ESQUEMA_FICHA3)
    escritor_fichas = pq.ParquetWriter(fichas, ESQUEMA_FICHAS)
    lote: dict[str, list] = {c: [] for c in ESQUEMA_FICHA3.names}
    lote_fichas: dict[str, list] = {c: [] for c in ESQUEMA_FICHAS.names}
    estabelecimentos: set[str] = set()
    atual: tuple[str, str] | None = None
    movimentos: list[Movimento] = []
    extras: list[DadosDaLinha] = []
    # as entradas da ficha lidas até aqui, com o ICMS próprio: o confronto de 2 e 4
    entradas_da_ficha: list[EntradaAnterior] = []
    andamento = Andamento(total=total)
    vistos: set[tuple[str, str]] = set()

    def fechar(chave: tuple[str, str]) -> None:
        cnpj, codigo = chave
        descricao = descricoes.get((cnpj, codigo)) or descricoes.get(("", codigo), "")
        qtd_abertura = Decimal(aberturas.get(chave) or 0)
        va = (valores or {}).get(chave)
        valor_abertura = va.valor if va is not None else Decimal(0)
        movs, dados_movs, pelo_percentual = (
            _resolver_sem_destaque(movimentos, extras, entradas_da_ficha) if resolver_sem_destaque
            else (movimentos, extras, set()))
        resumo.confronto_pendente -= sum(1 for d in dados_movs if d.criterio_do_efetivo in (
            EFETIVO_PELA_ENTRADA_POSTERIOR, EFETIVO_PELO_PERCENTUAL))
        resumo.confronto_pela_entrada_posterior += sum(
            1 for d in dados_movs if d.criterio_do_efetivo == EFETIVO_PELA_ENTRADA_POSTERIOR)
        resumo.confronto_pelo_percentual += len(pelo_percentual)
        inicial = SaldoInicial(qtd_abertura, valor_abertura)
        razao = RazaoDoItem(codigo, inicial)
        razao.lancar_varios(movs)
        linhas = razao.apurar()
        # Estoque negativo não tira mais a ficha do total (decisão do Victor,
        # 17/09/2026): ela abre com a quantidade que faltaria, sem ICMS
        # suportado, e fica marcada. É o que a RVZ fez na empresa 04 — a ficha
        # dela nunca fica negativa porque começa com o déficit —, e mantém no
        # total o ressarcimento das unidades que têm imposto pago.
        negativo = any(ln.saldo_quantidade < 0 for ln in linhas)
        aberta_por_negativo = Decimal(0)
        if negativo:
            aberta_por_negativo = -min(ln.saldo_quantidade for ln in linhas)
            inicial = SaldoInicial(qtd_abertura + aberta_por_negativo, valor_abertura)
            razao = RazaoDoItem(codigo, inicial)
            razao.lancar_varios(movs)
            linhas = razao.apurar()
        if pelo_percentual:
            # o efetivo é a fração do suportado que a própria saída levou (o
            # unitário do saldo vezes a quantidade): o saldo não muda, e o razão
            # roda de novo só para apurar o ressarcimento com ele
            efetivos = {id(ln.movimento): (abs(ln.icms_suportado) * PERCENTUAL_SEM_DESTAQUE).quantize(_Q6)
                        for ln in linhas if id(ln.movimento) in pelo_percentual}
            movs = [replace(m, icms_efetivo=efetivos[id(m)]) if id(m) in efetivos else m for m in movs]
            razao = RazaoDoItem(codigo, inicial)
            razao.lancar_varios(movs)
            linhas = razao.apurar()
        indice = {id(m): x for m, x in zip(movs, dados_movs)}
        entradas = saidas = ressarc = compl = credito = Decimal(0)
        retirada = False
        sem_aliq = indef = sem_fator = com_reducao = com_aliq_entrada = 0
        for ln in linhas:
            m = ln.movimento
            d = indice[id(m)]
            indefinido, faltou, conversao = d.indefinido, d.faltou_aliquota, d.conversao
            com_aliq_entrada += d.aliquota_da_entrada
            competencia = m.data.isoformat()[:7]
            _acrescentar(lote, cnpj, codigo, ln, d, retirada, descricao)
            if d.reducao:
                com_reducao += 1
                # o que a redução tirou do confronto: efetivo * r / (100 - r)
                resumo.efetivo_reduzido += ((m.icms_efetivo or Decimal(0))
                                            * Decimal(d.reducao) / (Decimal(100) - Decimal(d.reducao)))
            if d.aliquota_origem:
                lidas = resumo.aliquota_por_fonte
                lidas[d.aliquota_origem] = lidas.get(d.aliquota_origem, 0) + 1
            sem_fator += conversao[2]
            resumo.linhas_convertidas += conversao[1] != 1
            resumo.linhas_unidade_sem_fator += conversao[2]
            if m.especie.e_entrada:
                entradas += ln.quantidade
            else:
                saidas += -ln.quantidade
                if not m.devolucao and not retirada:
                    chave_enq = "indefinido" if indefinido else str(int(m.enquadramento))
                    e = resumo.por_enquadramento.setdefault(chave_enq, {
                        "linhas": 0, "quantidade": Decimal(0), "suportado": Decimal(0),
                        "confronto": Decimal(0), "ressarcimento": Decimal(0), "complemento": Decimal(0),
                        "credito": Decimal(0)})
                    e["linhas"] += 1
                    e["quantidade"] += m.quantidade
                    e["suportado"] += abs(ln.icms_suportado)
                    e["confronto"] += m.icms_efetivo or Decimal(0)
                    e["ressarcimento"] += ln.ressarcimento
                    e["complemento"] += ln.complemento
                    e["credito"] += ln.credito_operacao_propria
                    origem = resumo.saidas_por_origem.setdefault(m.origem, 0)
                    resumo.saidas_por_origem[m.origem] = origem + 1
            sem_aliq += faltou
            indef += indefinido
            ressarc += ln.ressarcimento
            compl += ln.complemento
            credito += ln.credito_operacao_propria
            if not retirada:
                c = resumo.por_competencia.setdefault(competencia, {
                    "linhas": 0, "ressarcimento": Decimal(0), "complemento": Decimal(0)})
                c["linhas"] += 1
                c["ressarcimento"] += ln.ressarcimento
                c["complemento"] += ln.complemento
            if len(lote["cnpj"]) >= LINHAS_POR_LOTE:
                escritor.write_table(pa.Table.from_pydict(lote, schema=ESQUEMA_FICHA3))
                for k in lote:
                    lote[k].clear()

        ultima = linhas[-1] if linhas else None
        uf = uf_por_cnpj.get(cnpj, "")
        origem_abertura, q_bloco_h = (origens or {}).get(chave, (None, None))
        for k, val in (("cnpj", cnpj), ("uf", uf), ("codigo", codigo),
                       ("descricao", descricao),
                       ("linhas", len(linhas)),
                       ("abertura_quantidade", qtd_abertura.quantize(_Q6)),
                       ("abertura_valor", valor_abertura.quantize(_Q15)),
                       ("abertura_sem_valor", qtd_abertura != 0 and valor_abertura == 0),
                       ("abertura_parcial", bool(va is not None and va.parcial)),
                       ("entradas", entradas.quantize(_Q6)), ("saidas", saidas.quantize(_Q6)),
                       ("saldo_quantidade", (ultima.saldo_quantidade if ultima else qtd_abertura).quantize(_Q6)),
                       ("saldo_valor", (ultima.saldo_valor if ultima else valor_abertura).quantize(_Q15)),
                       ("ressarcimento", ressarc.quantize(_Q15)), ("complemento", compl.quantize(_Q15)),
                       ("credito_operacao_propria", credito.quantize(_Q15)),
                       ("ficou_negativo", negativo), ("retirada", retirada),
                       ("abertura_por_saldo_negativo", aberta_por_negativo.quantize(_Q6)),
                       ("saidas_sem_aliquota", sem_aliq),
                       ("saidas_com_reducao", com_reducao),
                       ("saidas_indefinidas", indef), ("linhas_sem_fator", sem_fator),
                       ("abertura_origem", origem_abertura),
                       ("abertura_bloco_h",
                        None if q_bloco_h is None else Decimal(q_bloco_h).quantize(_Q6))):
            lote_fichas[k].append(val)
        resumo.fichas += 1
        resumo.linhas += len(linhas)
        if retirada:
            resumo.fichas_retiradas += 1
            resumo.linhas_retiradas += len(linhas)
            resumo.ressarcimento_retirado += ressarc
            resumo.complemento_retirado += compl
        else:
            resumo.ressarcimento += ressarc
            resumo.complemento += compl
            resumo.credito_operacao_propria += credito
        resumo.saidas_sem_aliquota += sem_aliq
        resumo.saidas_com_reducao += com_reducao
        resumo.saidas_com_aliquota_da_entrada += com_aliq_entrada
        resumo.saidas_indefinidas += indef
        resumo.fichas_negativas += negativo
        resumo.fichas_abertas_por_negativo += bool(aberta_por_negativo)
        resumo.quantidade_aberta_por_negativo += aberta_por_negativo
        resumo.fichas_abertura_sem_valor += qtd_abertura != 0 and valor_abertura == 0
        resumo.fichas_abertura_valorada += valor_abertura != 0
        resumo.fichas_abertura_parcial += bool(va is not None and va.parcial)
        resumo.icms_da_abertura += valor_abertura
        if origem_abertura == "ficha_anterior":
            resumo.fichas_abertura_da_ficha_anterior += 1
            resumo.icms_da_ficha_anterior += valor_abertura
        resumo.fichas_fora_de_sp += bool(uf) and uf != "SP"
        estabelecimentos.add(cnpj)
        vistos.add(chave)
        if len(lote_fichas["cnpj"]) >= LINHAS_POR_LOTE:
            escritor_fichas.write_table(pa.Table.from_pydict(lote_fichas, schema=ESQUEMA_FICHAS))
            for k in lote_fichas:
                lote_fichas[k].clear()

    try:
        for bloco in leitor:
            _conferir(deve_parar)
            d = bloco.to_pydict()
            for i in range(bloco.num_rows):
                linha = {k: d[k][i] for k in d}
                chave = (linha["cnpj"], linha["codigo"])
                if chave != atual:
                    if atual is not None:
                        fechar(atual)
                    atual, movimentos, extras, entradas_da_ficha = chave, [], [], []
                m, pendente, dados = _movimento(
                    linha, len(movimentos), resumo, venda_a_consumidor, entradas_da_ficha)
                if m is None:
                    continue
                # só a entrada com destaque do ICMS próprio confronta (26/11/2026)
                if (m.especie is Especie.ENTRADA and not m.devolucao and linha.get("icms_proprio") is not None
                        and Decimal(linha["icms_proprio"]) > 0 and m.quantidade > 0):
                    entradas_da_ficha.append(EntradaAnterior(m.data, m.quantidade, Decimal(linha["icms_proprio"]),
                                                             len(entradas_da_ficha)))
                resumo.confronto_pendente += pendente
                movimentos.append(m)
                extras.append(dados)
                andamento.linhas += 1
            if avisar is not None:
                andamento.fichas = resumo.fichas
                avisar(andamento)
        if atual is not None:
            fechar(atual)
        # quem só tem abertura, sem movimento no período, também tem ficha
        for chave in sorted(set(aberturas) - vistos):
            atual, movimentos, extras = chave, [], []
            fechar(chave)
        if lote["cnpj"]:
            escritor.write_table(pa.Table.from_pydict(lote, schema=ESQUEMA_FICHA3))
        if lote_fichas["cnpj"]:
            escritor_fichas.write_table(pa.Table.from_pydict(lote_fichas, schema=ESQUEMA_FICHAS))
    finally:
        escritor.close()
        escritor_fichas.close()
    resumo.estabelecimentos = len(estabelecimentos)


@dataclass(frozen=True)
class DadosDaLinha:
    """O que a linha da Ficha 3 guarda além do que o razão calcula.

    Era uma tupla que crescia a cada versão — e cada campo novo obrigava a
    contar posições em quatro lugares. Aqui cada coisa tem nome.
    """

    indefinido: bool = False
    faltou_aliquota: bool = False
    # (unidade de origem, fator, unidade sem fator)
    conversao: tuple = ("", Decimal(1), False)
    # (chave, nº do item, modelo, participante, número, série, código de origem)
    documento: tuple = ("", None, "", "", "", "", None)
    aliquota: Decimal | None = None
    reducao: Decimal | None = None
    aliquota_da_entrada: bool = False
    # vazio quando a alíquota é a do cadastro (`FONTES_DA_ALIQUOTA`)
    aliquota_origem: str = ""
    cst: str = ""
    ncm: str = ""
    unidade_estoque: str = ""
    valor_item: Decimal | None = None
    aliquota_documento: Decimal | None = None
    corrigida: bool = False
    criterio_do_suportado: str = ""
    filial_do_destaque: str = ""
    criterio_do_efetivo: str = ""


def _documento(linha: dict) -> tuple:
    """(chave, nº do item, modelo, participante, número, série, código de origem) — o
    que o arquivo digital pede, e de que código a linha veio."""
    original = linha.get("codigo_original")
    return ((linha.get("chave") or "").strip(), linha.get("numero_item"),
            (linha.get("modelo") or "").strip(), (linha.get("participante") or "").strip(),
            (linha.get("numero_documento") or "").strip(), (linha.get("serie") or "").strip(),
            original if original and original != linha.get("codigo") else None)


def _sem_confronto(m: Movimento) -> bool:
    """Saída de enquadramento 2 ou 4 que não achou entrada com destaque até ela."""
    return (not m.especie.e_entrada and not m.devolucao and m.icms_efetivo is None
            and m.enquadramento.gera_ressarcimento and not m.enquadramento.confronta_com_saida)


def _resolver_sem_destaque(movimentos: list, extras: list, entradas: list[EntradaAnterior]
                           ) -> tuple[list, list, set]:
    """As saídas de 2 e 4 que ficaram sem entrada com destaque antes delas.

    Com a ficha inteira lida, `entradas` tem todas as entradas com destaque do
    período. Havendo alguma, vale a primeira depois da saída (as seguintes, em
    ordem, se uma não basta). Não havendo nenhuma, a saída vai para o
    percentual do saldo, que só o razão sabe calcular: devolve o conjunto dos
    `id` desses movimentos para o fechamento aplicar depois de apurar.
    """
    if not any(_sem_confronto(m) for m in movimentos):
        return movimentos, extras, set()
    em_ordem = sorted(entradas, key=lambda e: (e.data, e.ordem))
    movs, dados, pelo_percentual = [], [], set()
    for m, d in zip(movimentos, extras):
        if _sem_confronto(m):
            if em_ordem:
                depois = [e for e in em_ordem if e.data >= m.data]
                valor = (valor_pelas_entradas_seguintes(m.quantidade, depois) if depois
                         else valor_da_abertura(m.quantidade, em_ordem))
                m = replace(m, icms_efetivo=valor.valor.quantize(_Q6))
                d = replace(d, criterio_do_efetivo=EFETIVO_PELA_ENTRADA_POSTERIOR)
            else:
                pelo_percentual.add(id(m))
                d = replace(d, criterio_do_efetivo=EFETIVO_PELO_PERCENTUAL)
        movs.append(m)
        dados.append(d)
    return movs, dados, pelo_percentual


def _movimento(linha: dict, ordem: int, resumo: ResumoDaMontagem,
               venda_a_consumidor: VendaAConsumidor = VendaAConsumidor.ENQUADRAMENTO_1,
               entradas_da_ficha: list[EntradaAnterior] | None = None):
    """Converte um lançamento em `Movimento`. Devolve o movimento, se o
    confronto ficou pendente e os `DadosDaLinha` que a ficha grava."""
    especie = Especie.ENTRADA if linha["especie"] == "entrada" else Especie.SAIDA
    quantidade = Decimal(linha["quantidade"] or 0)
    if quantidade < 0:
        # o domínio recusa sinal: devolução é marca, não quantidade negativa
        resumo.quantidade_negativa += 1
        quantidade = -quantidade
    fator = Decimal(linha["fator"] or 1)
    conversao = (linha["unidade"] or "", fator, bool(linha["sem_fator"]))
    dados = lambda **kw: DadosDaLinha(  # noqa: E731 - fecha sobre o lançamento
        conversao=conversao, documento=_documento(linha),
        cst=(linha.get("cst_icms") or "").strip(),
        ncm=(linha.get("ncm") or "").strip(),
        unidade_estoque=(linha.get("unidade_estoque") or "").strip(),
        valor_item=linha.get("valor"), aliquota_documento=linha.get("aliquota_documento"),
        corrigida=bool(linha.get("corrigida")),
        criterio_do_suportado=linha.get("criterio_do_suportado") or "",
        filial_do_destaque=linha.get("filial_do_destaque") or "", **kw)
    # a ficha é na unidade do inventário
    quantidade = quantidade * fator
    enq, indefinido, faltou, pendente, efetivo = EnquadramentoLegal.DEMAIS_SAIDAS, False, False, False, None
    reducao = aliquota = None
    criterio_efetivo = ""
    da_entrada = False
    origem_da_aliquota = ""
    if especie is Especie.SAIDA and not linha["devolucao"]:
        classificado, indefinido = _enquadrar(linha, venda_a_consumidor)
        corrigido = linha.get("enquadramento_corrigido")
        if corrigido is not None:
            # correção à mão é a última palavra, inclusive sobre o indefinido
            classificado, indefinido = EnquadramentoLegal(int(corrigido)), False
        if classificado is not None:
            enq = classificado
            efetivo, faltou, pendente, reducao = _confronto(enq, linha, entradas_da_ficha)
            if efetivo is not None and enq.confronta_com_saida:
                aliquota = linha.get("aliquota")
                da_entrada = bool(linha.get("aliquota_da_entrada"))
                origem_da_aliquota = linha.get("aliquota_origem") or ""
            if efetivo is not None and not enq.confronta_com_saida:
                resumo.confronto_pela_entrada += 1
                criterio_efetivo = EFETIVO_PELA_ENTRADA
    try:
        m = Movimento(
            data=linha["data"],
            especie=especie,
            quantidade=quantidade,
            icms_suportado=Decimal(linha["suportado"] or 0) if especie.e_entrada else None,
            enquadramento=enq,
            icms_efetivo=efetivo,
            devolucao=bool(linha["devolucao"]),
            cfop=linha["cfop"] or "",
            documento=linha["documento"] or "",
            origem=linha["origem"],
            ordem_na_fonte=ordem,
        )
    except MovimentoInvalido as erro:
        log.warning("lançamento recusado pelo razão", extra={"motivo": str(erro),
                                                            "codigo": linha["codigo"]})
        return None, False, dados()
    return m, pendente, dados(indefinido=indefinido, faltou_aliquota=faltou, aliquota=aliquota,
                              reducao=reducao, aliquota_da_entrada=da_entrada,
                              aliquota_origem=origem_da_aliquota, criterio_do_efetivo=criterio_efetivo)


def _acrescentar(lote: dict, cnpj: str, codigo: str, ln, dados: DadosDaLinha,
                 retirada: bool = False, descricao: str = "") -> None:
    m = ln.movimento
    indefinido, conversao, doc = dados.indefinido, dados.conversao, dados.documento
    lote["cnpj"].append(cnpj)
    lote["codigo"].append(codigo)
    lote["descricao"].append(descricao)
    lote["ncm"].append(dados.ncm)
    lote["unidade_estoque"].append(dados.unidade_estoque)
    lote["numero"].append(ln.numero)
    lote["data"].append(m.data)
    lote["especie"].append(m.especie.value)
    lote["devolucao"].append(m.devolucao)
    lote["cfop"].append(m.cfop)
    lote["cst_icms"].append(dados.cst)
    lote["documento"].append(m.documento)
    lote["origem"].append(m.origem)
    saida_propria = not m.especie.e_entrada and not m.devolucao
    lote["enquadramento"].append(None if (indefinido or not saida_propria) else int(m.enquadramento))
    lote["enquadramento_indefinido"].append(indefinido)
    lote["ficha_retirada"].append(retirada)
    lote["corrigida"].append(dados.corrigida)
    lote["unidade_origem"].append(conversao[0])
    lote["fator_conversao"].append(Decimal(conversao[1]).quantize(Decimal("0.000000001")))
    lote["unidade_sem_fator"].append(conversao[2])
    lote["quantidade"].append(ln.quantidade.quantize(_Q6))
    lote["valor_item"].append(Decimal(dados.valor_item).quantize(_Q6)
                              if dados.valor_item is not None else None)
    lote["icms_suportado"].append(ln.icms_suportado.quantize(_Q15))
    lote["valor_unitario_usado"].append(ln.valor_unitario_usado.quantize(_Q15))
    lote["icms_efetivo"].append(m.icms_efetivo.quantize(_Q6) if m.icms_efetivo is not None else None)
    lote["aliquota_documento"].append(Decimal(dados.aliquota_documento).quantize(_Q4)
                                      if dados.aliquota_documento else None)
    lote["aliquota"].append(Decimal(dados.aliquota).quantize(_Q4) if dados.aliquota else None)
    lote["aliquota_origem"].append(dados.aliquota_origem or None)
    lote["reducao_base"].append(Decimal(dados.reducao).quantize(_Q4) if dados.reducao else None)
    lote["saldo_quantidade"].append(ln.saldo_quantidade.quantize(_Q6))
    lote["saldo_unitario"].append(ln.saldo_unitario.quantize(_Q15))
    lote["saldo_valor"].append(ln.saldo_valor.quantize(_Q15))
    lote["ressarcimento"].append(ln.ressarcimento.quantize(_Q15))
    lote["complemento"].append(ln.complemento.quantize(_Q15))
    lote["chave"].append(doc[0])
    lote["numero_item"].append(doc[1])
    lote["modelo"].append(doc[2])
    lote["participante"].append(doc[3])
    lote["numero_documento"].append(doc[4])
    lote["serie"].append(doc[5] if len(doc) > 5 else "")
    lote["codigo_original"].append(doc[6] if len(doc) > 6 else None)
    lote["credito_operacao_propria"].append(ln.credito_operacao_propria.quantize(_Q15))
    lote["criterio_do_suportado"].append(dados.criterio_do_suportado or None)
    lote["filial_do_destaque"].append(dados.filial_do_destaque or None)
    lote["suportado_a_estimar"].append(dados.criterio_do_suportado == "precisa_estimar")
    lote["criterio_do_efetivo"].append(dados.criterio_do_efetivo or None)


# ---------------------------------------------------------------------------
# o que a tela lê depois de pronto
# ---------------------------------------------------------------------------
def lista_de_fichas(destino: str, busca: str | None = None, so: str | None = None,
                    pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """As fichas, maior ressarcimento primeiro. `so` recorta as que pedem atenção:
    `validas` (as que entram no total), `retiradas`,
    `negativas`, `sem_aliquota`, `indefinidas`, `divergentes` (do inventário),
    `suspeita_unidade` e `sem_fator`."""
    recortes = {"validas": "NOT retirada", "retiradas": "retirada",
                "negativas": "ficou_negativo", "sem_aliquota": "saidas_sem_aliquota > 0",
                "indefinidas": "saidas_indefinidas > 0",
                "divergentes": "inventarios_divergentes > 0",
                "suspeita_unidade": "suspeita_de_unidade",
                "sem_fator": "linhas_sem_fator > 0"}
    if so and so not in recortes:
        raise ValueError(f"Recorte desconhecido: {so}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_FICHAS)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_FICHAS} não está em {destino}.")
    filtros, parametros = [], []
    if so:
        filtros.append(recortes[so])
    if busca and busca.strip():
        filtros.append("(codigo ILIKE ? OR descricao ILIKE ? OR cnpj ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 3
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"
    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY retirada, ressarcimento DESC, cnpj, codigo
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [_jsonavel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def linhas_da_ficha(destino: str, cnpj: str, codigo: str,
                    pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Uma página da Ficha 3 de uma mercadoria num estabelecimento, em ordem."""
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_FICHA3)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_FICHA3} não está em {destino}.")
    con = _leitura(destino)
    try:
        base = f"read_parquet('{_escapar(caminho)}') WHERE cnpj = ? AND codigo = ?"
        total = con.execute(f"SELECT count(*) FROM {base}", [cnpj, codigo]).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY numero
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, [cnpj, codigo])
        nomes = [c[0] for c in cursor.description]
        linhas = [_jsonavel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def _jsonavel(linha: dict) -> dict:
    """Decimal vira texto e data vira ISO: é o que atravessa o JSON sem perder casa."""
    saida = {}
    for k, v in linha.items():
        if isinstance(v, Decimal):
            saida[k] = str(v.normalize()) if v == v.to_integral() else format(v.normalize(), "f")
        elif hasattr(v, "isoformat"):
            saida[k] = v.isoformat()
        else:
            saida[k] = v
    return saida


def serializar(resumo: ResumoDaMontagem) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    def texto(v):
        return format(Decimal(v).quantize(Decimal("0.01")), "f")
    rotulos = {"1": "Consumidor final", "2": "Fato gerador não realizado",
               "3": "Isenção ou não incidência", "4": "Outro estado",
               "0": "Demais saídas", "indefinido": "Indefinido"}
    return {
        "venda_a_consumidor": resumo.venda_a_consumidor,
        "periodo_inicio": resumo.periodo_inicio,
        "periodo_fim": resumo.periodo_fim,
        "abertura_em": resumo.abertura_em,
        "codigos_com_st": resumo.codigos_com_st,
        "fichas": resumo.fichas,
        "estabelecimentos": resumo.estabelecimentos,
        "linhas": resumo.linhas,
        "ressarcimento": texto(resumo.ressarcimento),
        "complemento": texto(resumo.complemento),
        "credito_operacao_propria": texto(resumo.credito_operacao_propria),
        "confronto_pela_entrada": resumo.confronto_pela_entrada,
        "confronto_pela_entrada_posterior": resumo.confronto_pela_entrada_posterior,
        "confronto_pelo_percentual": resumo.confronto_pelo_percentual,
        # fora do total até os dados chegarem: o valor delas não é confiável
        "abertas_por_saldo_negativo": {
            "fichas": resumo.fichas_abertas_por_negativo,
            "quantidade": texto(resumo.quantidade_aberta_por_negativo),
        },
        "retiradas": {
            "fichas": resumo.fichas_retiradas,
            "linhas": resumo.linhas_retiradas,
            "ressarcimento": texto(resumo.ressarcimento_retirado),
            "complemento": texto(resumo.complemento_retirado),
        },
        "por_enquadramento": [
            {"codigo": k, "rotulo": rotulos.get(k, k), "linhas": v["linhas"],
             "quantidade": texto(v["quantidade"]), "suportado": texto(v["suportado"]),
             "confronto": texto(v["confronto"]), "ressarcimento": texto(v["ressarcimento"]),
             "complemento": texto(v["complemento"]), "credito": texto(v.get("credito", 0))}
            for k, v in sorted(resumo.por_enquadramento.items(),
                               key=lambda kv: ("1", "2", "3", "4", "0", "indefinido").index(kv[0]))
        ],
        "por_competencia": [
            {"competencia": k, "linhas": v["linhas"], "ressarcimento": texto(v["ressarcimento"]),
             "complemento": texto(v["complemento"])}
            for k, v in sorted(resumo.por_competencia.items())
        ],
        "saidas_por_origem": resumo.saidas_por_origem,
        # quantas saídas do enquadramento 1 confrontaram com base reduzida, e
        # quanto a redução tirou do valor de confronto
        "correcoes": resumo.correcoes,
        "reducao_de_base": {
            "saidas": resumo.saidas_com_reducao,
            "efetivo_reduzido": texto(resumo.efetivo_reduzido),
        },
        "aliquota_da_entrada": resumo.saidas_com_aliquota_da_entrada,
        # e de onde ela veio: `item`/`ncm` é a chave, `interna`/`st`/`efetiva`
        # é a prova (`FONTES_DA_ALIQUOTA`)
        "aliquota_por_fonte": dict(sorted(resumo.aliquota_por_fonte.items())),
        "pendencias": {
            "saidas_sem_aliquota": resumo.saidas_sem_aliquota,
            "saidas_indefinidas": resumo.saidas_indefinidas,
            "confronto_pendente": resumo.confronto_pendente,
            "fichas_negativas": resumo.fichas_negativas,
            "fichas_abertura_sem_valor": resumo.fichas_abertura_sem_valor,
            "fichas_abertura_parcial": resumo.fichas_abertura_parcial,
            "fichas_fora_de_sp": resumo.fichas_fora_de_sp,
            "relatorio_sem_estabelecimento": resumo.relatorio_sem_estabelecimento,
            "relatorio_trocado_pela_efd": resumo.relatorio_trocado_pela_efd,
            "relatorio_chave_do_c100": resumo.relatorio_chave_do_c100,
            "relatorio_registrado_em_cupom": resumo.relatorio_registrado_em_cupom,
            "linhas_com_depara": resumo.linhas_com_depara,
            "codigos_trocados_pelo_depara": resumo.codigos_trocados_pelo_depara,
            "quantidade_negativa": resumo.quantidade_negativa,
            "linhas_unidade_sem_fator": resumo.linhas_unidade_sem_fator,
            "abertura_sem_fator": resumo.abertura_sem_fator,
        },
        "conversao": {
            "linhas_convertidas": resumo.linhas_convertidas,
            "linhas_sem_fator": resumo.linhas_unidade_sem_fator,
        },
        "saidas_com_aliquota_do_mes": resumo.saidas_com_aliquota_do_mes,
        "abertura": {
            "fichas_valoradas": resumo.fichas_abertura_valorada,
            "fichas_parciais": resumo.fichas_abertura_parcial,
            "fichas_sem_valor": resumo.fichas_abertura_sem_valor,
            "icms": texto(resumo.icms_da_abertura),
            "fichas_da_ficha_anterior": resumo.fichas_abertura_da_ficha_anterior,
            "icms_da_ficha_anterior": texto(resumo.icms_da_ficha_anterior),
        },
        "fora_da_ficha": {"uso_e_consumo": resumo.lancamentos_de_uso_e_consumo, "x949": resumo.lancamentos_x949},
        "conferencia_inventario": resumo.conferencia,
    }
