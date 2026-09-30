"""A exclusão do ISS da base do PIS/COFINS — o relatório 933, por documento.

Equivalente à consulta **933 — A100, A170 — Detalhado por Documento** do
Sistema MA. Mesma tese das outras duas — imposto não é receita —, aplicada à
nota de serviço: o ISS que o prestador destaca não é dele, e não compõe a base
das contribuições.

## O irmão pequeno da família

O 903 exclui o ICMS que está escrito na nota; o 839 exclui o ICMS-ST que
ninguém escreveu e precisa ser presumido; este exclui o ISS, que **às vezes**
está escrito. O registro A100 tem o campo `VL_ISS`, e ele é facultativo: quem
preenche entrega a tese pronta, quem não preenche entrega uma linha sem nada a
excluir. Na DMINAS, de 33 notas de serviço, **uma** tem ISS — R$ 5.586,51 sobre
R$ 279.325,68, que rendem R$ 646,71 corrigidos.

**O relatório sai mesmo assim, e é assim que tem de ser.** As outras 32 linhas
saem com exclusão zero em vez de sumir: quem confere precisa ver que a nota foi
olhada e que o ISS não estava lá. Sumir com elas faria o relatório parecer
menor do que o trabalho que ele cobriu.

## O que falta, e é o próximo passo desta tese

Quando o `VL_ISS` vem vazio, o valor existe — só não está no SPED: está na
**NFS-e**. A cadeia completa do MA passa pelo XML da NFS-e (INF/SERVICO/VALORES)
e pelo leiaute próprio do município de São Paulo (cabeçalho e detalhe), de onde
ele tira o ISS que a escrituração não trouxe. Este módulo lê só a
EFD-Contribuições; ligar a NFS-e é trabalho à parte, e até lá a linha sem
`VL_ISS` sai com a coluna do ISS **em branco** — visível, e não silenciosa. O
resumo conta essas notas (`sem_iss`), que é o número que diz quanto da tese
está esperando a NFS-e.

## A conta

```
rateio          = valor do item ÷ soma dos itens do documento
ISS rateado     = VL_ISS do A100 × rateio
base recalculada = valor do item − desconto
base STF        = base do PIS/COFINS − ISS rateado
```

**O rateio é fração, não porcentagem**, apesar de a coluna do MA se chamar
"Percentual Rateio": nas 33 linhas do gabarito ele vale `1`, e não `100`. Como
todos os documentos têm um item só, `1` é o documento inteiro — e por isso o
rateio entre vários itens não tem uma linha sequer para conferir: a divisão
está aqui pela conta, não pela medida.

**E a diferença sai da base, não da subtração das contribuições.** Na única nota
com ISS, `PIS − PIS STF` dá 92,17 e o gabarito escreve 92,18, que é
`5.586,51 × 1,65%` arredondado. É o oposto do 903, onde a subtração está medida
em 138.358 linhas. Dois relatórios do mesmo sistema, duas contas — cada uma
conferida contra o seu próprio gabarito.

**E a recalculada daqui não subtrai o imposto**, ao contrário da do 903: ela é
`valor − desconto`, e serve para mostrar de onde a base deveria ter saído.

## Quem entra

```
A170 de documento de SAÍDA  (o A100 com IND_OPER = 1)
    E   PIS ou COFINS efetivamente pago
```

Dois filtros, e eles bastam: os 35 A100 do arquivo de referência são 33 de
saída e 2 de entrada, e os 33 de saída são exatamente as 33 linhas do gabarito.
Entrada de serviço é crédito, não receita, e tese de receita não a alcança.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.infraestrutura.sped.tabelas import tab_selic
from cat.log import obter_log

log = obter_log(__name__)

# IND_OPER = 1 é saída. Entrada de serviço é crédito, e não receita
SAIDA = "1"

_DE_INTERESSE = {b"0000", b"A010", b"A100", b"A170"}

ZERO = Decimal(0)
CEM = Decimal(100)
DOIS = Decimal("0.01")


def _numero(bruto: str) -> Decimal:
    """O número do SPED, em Decimal. Vazio é zero."""
    texto = (bruto or "").strip()
    if not texto:
        return ZERO
    try:
        return Decimal(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except ArithmeticError:
        return ZERO


def _centavos(valor: Decimal) -> Decimal:
    """Arredonda ao centavo, sem zero negativo. Ver `exclusao_do_icms_st`."""
    arredondado = valor.quantize(DOIS, rounding=ROUND_HALF_UP)
    return ZERO if arredondado == ZERO else arredondado


def _dia(bruto: str) -> str:
    b = (bruto or "").strip()
    if len(b) != 8 or not b.isdigit():
        return b
    try:
        return date(int(b[4:]), int(b[2:4]), int(b[:2])).strftime("%d/%m/%Y")
    except ValueError:
        return b


def _como_veio(bruto: str, valor: Decimal) -> str:
    """O número — ou **vazio**, quando o campo veio vazio do arquivo.

    O MA preserva a ausência: `VL_DESC` em branco sai em branco na planilha, e
    `VL_DESC` igual a "0,00" sai zero. São coisas diferentes para quem confere —
    "não informou" e "informou zero" —, e tratar as duas como zero divergia em
    todas as linhas sem desconto.
    """
    return "" if not (bruto or "").strip() else str(valor)


def _nomeados(prefixo: str, valores: list[str]) -> dict[str, str]:
    nomes = nomes_dos_campos(prefixo)
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return {f"{prefixo}_{nome}": completos[i] for i, nome in enumerate(nomes)}


@dataclass
class LinhaDaExclusaoISS:
    """Uma linha do 933, na ordem de colunas do MA."""

    cnpj: str = ""
    periodo: str = ""
    situacao: str = ""
    numero_do_documento: str = ""
    chave: str = ""
    data_do_documento: str = ""
    data_de_execucao_do_servico: str = ""
    cst: str = ""
    valor_do_documento: str = ""
    desconto_do_documento: str = ""
    valor_do_item: str = ""
    desconto_do_item: str = ""
    percentual_do_rateio: str = ""
    iss_rateado: str = ""
    base: str = ""
    base_recalculada: str = ""
    base_stf: str = ""
    diferenca_da_base: str = ""
    selic_acumulada: str = ""
    aliquota_do_pis: str = ""
    pis: str = ""
    pis_stf: str = ""
    diferenca_do_pis: str = ""
    selic_sobre_o_pis: str = ""
    total_do_pis_a_recuperar: str = ""
    aliquota_da_cofins: str = ""
    cofins: str = ""
    cofins_stf: str = ""
    diferenca_da_cofins: str = ""
    selic_sobre_a_cofins: str = ""
    total_da_cofins_a_recuperar: str = ""
    total_a_recuperar_atualizado: str = ""

    def como_dicionario(self) -> dict[str, str]:
        return asdict(self)


def colunas_da_exclusao_iss() -> list[str]:
    """Os nomes das colunas, na ordem — para quem grava parquet vazio."""
    return list(LinhaDaExclusaoISS().como_dicionario())


def exclusoes_do_iss(caminho: str, codificacao: str, ate: str,
                     acumulada: dict[str, Decimal] | None = None,
                     mensal: dict[str, Decimal] | None = None,
                     ) -> Iterator[LinhaDaExclusaoISS]:
    """As exclusões do ISS da base, item a item, corrigidas até `ate`.

    `ate` é o mês da restituição, em "aaaa-mm". `mensal` é a série da Selic (do
    banco, em produção) e `acumulada` a acumulada já pronta, para conferência
    contra gabarito — as duas como no 903 e no 839.
    """
    contexto = _Contexto(ate, acumulada, mensal)
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(registro,
                                    campos(linha.decode(codificacao, errors="replace")))
        # o último documento não vê outro para fechá-lo
        yield from contexto.fechar_documento()

    log.info("exclusão do ISS da base gerada", extra={
        "arquivo": os.path.basename(caminho), "linhas": contexto.saíram,
        "documentos": contexto.documentos, "sem_iss": contexto.sem_iss,
        "competencia": contexto.competencia, "selic_ate": ate,
    })


class _Contexto:
    """O estado da passada.

    **O documento é lido inteiro antes de emitir**, como no 903 e no 839: o
    rateio do ISS é proporcional ao valor do item dentro da nota, e não se sabe
    a proporção antes de conhecer todos os itens.
    """

    def __init__(self, ate: str, acumulada: dict[str, Decimal] | None = None,
                 mensal: dict[str, Decimal] | None = None) -> None:
        self.ate = ate
        self.acumulada = acumulada or {}
        self.mensal = mensal
        self.competencia = ""
        self.periodo = ""
        self.selic = ZERO
        self.cnpj = ""
        self.a100: list[str] = []
        self.a100_e_saida = False
        self.itens_do_documento: list[list[str]] = []
        self.saíram = 0
        self.documentos = 0
        # quantas notas de saída vieram sem o ISS preenchido. É o número que
        # diz quanto da tese está esperando a NFS-e — ver o topo do módulo
        self.sem_iss = 0

    def ver(self, registro: bytes, valores: list[str]) -> Iterator[LinhaDaExclusaoISS]:
        if registro == b"0000":
            try:
                cabecalho = ler_cabecalho("|" + "|".join(valores) + "|")
            except ArquivoNaoReconhecido as erro:
                log.warning("registro 0000 não reconhecido", extra={"motivo": str(erro)})
                return
            inicio = cabecalho.inicio.replace(day=1)
            self.periodo = inicio.strftime("%d/%m/%Y")
            self.competencia = inicio.strftime("%Y-%m")
            self.selic = (self.acumulada[self.competencia]
                          if self.competencia in self.acumulada
                          else tab_selic.acumulada(self.competencia, self.ate,
                                                   self.mensal))
        elif registro == b"A010":
            # a última nota do estabelecimento anterior ainda está no buffer, e
            # o CNPJ dela é o de quem a emitiu. Fechar antes de trocar — no 903
            # o mesmo descuido trocou o CNPJ de 61 linhas
            yield from self.fechar_documento()
            self.cnpj = valores[1].strip() if len(valores) > 1 else ""
        elif registro == b"A100":
            yield from self.fechar_documento()
            self.a100 = valores
            self.a100_e_saida = len(valores) > 1 and valores[1].strip() == SAIDA
        elif registro == b"A170":
            self.itens_do_documento.append(valores)

    def fechar_documento(self) -> Iterator[LinhaDaExclusaoISS]:
        """Emite os itens da nota de serviço que entram, com o ISS repartido."""
        itens, self.itens_do_documento = self.itens_do_documento, []
        a100, self.a100 = self.a100, []
        e_saida, self.a100_e_saida = self.a100_e_saida, False
        if not a100 or not itens or not e_saida:
            return

        self.documentos += 1
        nota = _nomeados("A100", a100)
        iss = _numero(nota["A100_VL_ISS"])
        if iss <= ZERO:
            self.sem_iss += 1

        # o denominador é a soma de **todos** os itens: o ISS foi destacado
        # sobre a nota inteira, e não sobre os itens que entram no relatório
        valores_dos_itens = [_numero(_nomeados("A170", i)["A170_VL_ITEM"]) for i in itens]
        total_dos_itens = sum(valores_dos_itens, ZERO)

        for bruto, valor_do_item in zip(itens, valores_dos_itens):
            item = _nomeados("A170", bruto)
            contribuiu = (_numero(item["A170_VL_PIS"]) > ZERO
                          or _numero(item["A170_VL_COFINS"]) > ZERO)
            if not contribuiu:
                continue
            rateio = (valor_do_item / total_dos_itens
                      if total_dos_itens else ZERO)
            yield self._montar(nota, item, valor_do_item, iss, rateio)

    def _montar(self, nota: dict[str, str], item: dict[str, str],
                valor_do_item: Decimal, iss: Decimal,
                rateio: Decimal) -> LinhaDaExclusaoISS:
        desconto = _numero(item["A170_VL_DESC"])
        base = _numero(item["A170_VL_BC_PIS"])
        iss_rateado = _centavos(iss * rateio)

        # o que a base deveria ser, reconstruída do item. **Não subtrai o ISS**,
        # ao contrário da recalculada do 903 — ver o topo do módulo
        recalculada = valor_do_item - desconto
        stf = base - iss_rateado
        diferenca_da_base = base - stf

        aliquota_do_pis = _numero(item["A170_ALIQ_PIS"])
        aliquota_da_cofins = _numero(item["A170_ALIQ_COFINS"])
        pis = _numero(item["A170_VL_PIS"])
        cofins = _numero(item["A170_VL_COFINS"])
        pis_stf = _centavos(stf * aliquota_do_pis / CEM)
        cofins_stf = _centavos(stf * aliquota_da_cofins / CEM)

        # **a diferença sai da base, e não da subtração das duas contribuições.**
        # Na única nota com ISS do arquivo de referência, `pis − pis_stf` dá
        # 92,17 e o gabarito escreve 92,18, que é 5.586,51 × 1,65% arredondado.
        # É o oposto do 903, que subtrai — e lá isso está medido em 138.358
        # linhas. Cada relatório com a sua conta, cada uma conferida na sua
        diferenca_do_pis = _centavos(diferenca_da_base * aliquota_do_pis / CEM)
        diferenca_da_cofins = _centavos(diferenca_da_base * aliquota_da_cofins / CEM)
        selic_sobre_o_pis = _centavos(diferenca_do_pis * self.selic / CEM)
        selic_sobre_a_cofins = _centavos(diferenca_da_cofins * self.selic / CEM)
        total_do_pis = diferenca_do_pis + selic_sobre_o_pis
        total_da_cofins = diferenca_da_cofins + selic_sobre_a_cofins

        self.saíram += 1
        t = str
        return LinhaDaExclusaoISS(
            cnpj=self.cnpj, periodo=self.periodo, situacao=nota["A100_COD_SIT"],
            numero_do_documento=nota["A100_NUM_DOC"], chave=nota["A100_CHV_NFSE"],
            data_do_documento=_dia(nota["A100_DT_DOC"]),
            data_de_execucao_do_servico=_dia(nota["A100_DT_EXE_SERV"]),
            cst=item["A170_CST_PIS"],
            valor_do_documento=t(_numero(nota["A100_VL_DOC"])),
            desconto_do_documento=_como_veio(nota["A100_VL_DESC"],
                                             _numero(nota["A100_VL_DESC"])),
            valor_do_item=t(valor_do_item),
            desconto_do_item=_como_veio(item["A170_VL_DESC"], desconto),
            percentual_do_rateio=t(rateio),
            iss_rateado=_como_veio(nota["A100_VL_ISS"], iss_rateado),
            base=t(base), base_recalculada=t(recalculada), base_stf=t(stf),
            diferenca_da_base=t(diferenca_da_base),
            selic_acumulada=t(self.selic),
            aliquota_do_pis=t(aliquota_do_pis), pis=t(pis), pis_stf=t(pis_stf),
            diferenca_do_pis=t(diferenca_do_pis),
            selic_sobre_o_pis=t(selic_sobre_o_pis),
            total_do_pis_a_recuperar=t(total_do_pis),
            aliquota_da_cofins=t(aliquota_da_cofins), cofins=t(cofins),
            cofins_stf=t(cofins_stf), diferenca_da_cofins=t(diferenca_da_cofins),
            selic_sobre_a_cofins=t(selic_sobre_a_cofins),
            total_da_cofins_a_recuperar=t(total_da_cofins),
            total_a_recuperar_atualizado=t(total_do_pis + total_da_cofins))
