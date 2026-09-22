"""A quebra da ECD: o plano de contas e o razão contábil.

A ECD é a escrituração **contábil**; o razão é a lista de partidas de cada
conta, na ordem do tempo, com o saldo correndo. É o documento contra o qual se
confere o que a escrituração fiscal diz — a receita do razão tem de bater com a
receita da EFD, e é daí que sai boa parte do trabalho de PIS/COFINS e de
IRPJ/CSLL.

Portado do projeto Quebra de SPED em 22/09/2026.

## O desenho que faz isso ser rápido

Uma passada guarda três coisas:

* o **plano de contas** (I050) inteiro em memória — é pequeno, alguns milhares
  de contas, e serve a tudo depois;
* a posição de **todo I200** (o lançamento), num array ordenado;
* a posição de cada **I250** (a partida) **agrupada por conta**.

Com isso, o razão de *uma* conta lê só as partidas dela — e o lançamento dono de
cada partida sai por **busca binária** no array de I200: é o último I200 cuja
posição vem antes da partida, porque o SPED escreve o pai antes do filho. Sem
isso, mostrar o razão de uma conta custaria varrer o arquivo inteiro.

## Dinheiro em Decimal, e não em float

O projeto de origem acumula o saldo em `float`. Num razão de milhões de
partidas, o erro de representação binária se acumula e o saldo final sai com
centavos que não existem — e "centavo que não existe" num documento contábil é
exatamente o tipo de coisa que ninguém consegue explicar depois. Aqui o valor é
`Decimal` do começo ao fim, como em todo o resto desta casa.

## A partida órfã

Partida sem lançamento acima dela não deveria existir, mas existe: arquivo
truncado, exportação parcial. Ela é **contada e deixada de fora** — entrar sem
data e sem número de lançamento sujaria o razão sem que ninguém percebesse.
"""

from __future__ import annotations

import array
import bisect
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.leitor import (
    BUFFER_DE_REDE,
    campos,
    codificacao_de,
    linhas_com_posicao,
    registro_de,
    tamanho_de,
)
from cat.log import obter_log

log = obter_log(__name__)

ZERO = Decimal("0")

# Os registros da ECD que a quebra lê. O leiaute é o do Manual da ECD, e é
# outro do da EFD-Contribuições — por isso não reaproveita `registros.py`.
#
# **O 0000 não está aqui de propósito.** Ele muda de uma versão do leiaute para
# outra — um arquivo real trouxe dois campos a mais antes das datas, e ler por
# posição devolvia a data no lugar do CNPJ, calado. Quem o lê é
# `dominio/sped/cabecalho.py`, que acha os campos **pela forma**: o par de datas
# de oito dígitos, o CNPJ de catorze. Foi a segunda vez que este porte caiu na
# mesma armadilha (22/09/2026); a primeira foi na EFD ICMS/IPI.
CAMPOS_DA_ECD: dict[str, tuple[str, ...]] = {
    # o plano de contas, e a conta referencial dele
    "I050": ("REG", "DT_ALT", "COD_NAT", "IND_CTA", "NIVEL", "COD_CTA",
             "COD_CTA_SUP", "CTA"),
    "I051": ("REG", "COD_CCUS", "COD_CTA_REF"),
    # o lançamento, e as partidas dele
    "I200": ("REG", "NUM_LCTO", "DT_LCTO", "VL_LCTO", "IND_LCTO",
             "DT_LCTO_EXT", "VL_LCTO_MF"),
    "I250": ("REG", "COD_CTA", "COD_CCUS", "VL_DC", "IND_DC", "NUM_ARQ",
             "COD_HIST_PAD", "HIST", "COD_PART", "VL_DC_MF", "IND_DC_MF"),
}

TIPO_DE_LANCAMENTO = {
    "N": "Normal", "E": "Encerramento", "P": "Extemporâneo",
}


class EcdInvalida(ValueError):
    """O arquivo não é uma ECD que dê para quebrar, e dizer por quê ajuda."""


@dataclass(frozen=True)
class ContaContabil:
    """Uma conta do plano (I050)."""

    codigo: str
    superior: str
    nome: str
    nivel: str
    tipo: str          # "A" analítica, "S" sintética
    natureza: str = ""

    @property
    def analitica(self) -> bool:
        return self.tipo == "A"


@dataclass
class IndiceDaEcd:
    """O que uma passada pela ECD descobriu."""

    caminho: str
    codificacao: str
    cnpj: str = ""
    nome: str = ""
    inicio: str = ""
    fim: str = ""
    contas: list[ContaContabil] = field(default_factory=list)
    referencial: dict[str, str] = field(default_factory=dict)
    posicoes_i200: array.array = field(default_factory=lambda: array.array("q"))
    posicoes_i250: dict[str, array.array] = field(default_factory=dict)
    partidas: int = 0

    @property
    def lancamentos(self) -> int:
        return len(self.posicoes_i200)

    @property
    def analiticas(self) -> list[ContaContabil]:
        """Só as contas que recebem lançamento. As sintéticas somam filhas."""
        return [c for c in self.contas if c.analitica]

    def conta(self, codigo: str) -> ContaContabil | None:
        return next((c for c in self.contas if c.codigo == codigo), None)

    def partidas_de(self, codigo: str) -> int:
        return len(self.posicoes_i250.get(codigo, ()))

    def como_json(self) -> dict:
        return {
            "caminho": self.caminho, "cnpj": self.cnpj, "nome": self.nome,
            "inicio": self.inicio, "fim": self.fim, "contas": len(self.contas),
            "analiticas": len(self.analiticas), "lancamentos": self.lancamentos,
            "partidas": self.partidas,
        }


def _dicionario(valores: list[str], registro: str) -> dict[str, str]:
    nomes = CAMPOS_DA_ECD[registro]
    completos = list(valores) + [""] * max(0, len(nomes) - len(valores))
    return dict(zip(nomes, completos))


def _decimal(bruto: str) -> Decimal:
    """O valor do SPED em Decimal. Igual ao de `dominio/sped/fiscais.py`."""
    b = (bruto or "").strip().replace(".", "").replace(",", ".")
    if not b:
        return ZERO
    try:
        return Decimal(b)
    except InvalidOperation:
        return ZERO


def _data(bruto: str) -> date | None:
    b = (bruto or "").strip()
    if len(b) != 8 or not b.isdigit():
        return None
    try:
        return date(int(b[4:]), int(b[2:4]), int(b[:2]))
    except ValueError:
        return None


def _identificar(indice: IndiceDaEcd, linha: str) -> None:
    """Preenche empresa e período pelo domínio, que conhece os leiautes."""
    try:
        lido = ler_cabecalho(linha)
    except ArquivoNaoReconhecido as erro:
        log.warning("registro 0000 da ECD não reconhecido", extra={"motivo": str(erro)})
        return
    indice.nome = lido.nome
    indice.inicio, indice.fim = lido.inicio.isoformat(), lido.fim.isoformat()
    if lido.cnpj is None:
        # dígito verificador que não fecha: o razão sai sem CNPJ, e o aviso
        # aparece no log em vez de o número errado circular num documento
        log.warning("a ECD traz um CNPJ que não confere",
                    extra={"arquivo": os.path.basename(indice.caminho)})
        return
    indice.cnpj = lido.cnpj.valor


def indexar_ecd(caminho: str, avisar: Callable[[int, int], None] | None = None,
                a_cada: int = 50 << 20) -> IndiceDaEcd:
    """Lê a ECD uma vez e guarda o plano de contas e as posições."""
    codificacao = codificacao_de(caminho)
    totais = tamanho_de(caminho)
    indice = IndiceDaEcd(caminho=os.path.abspath(caminho), codificacao=codificacao)
    ultima_conta = ""
    proximo_aviso = a_cada

    for posicao, linha in linhas_com_posicao(caminho, buffer=BUFFER_DE_REDE):
        registro = registro_de(linha)
        if registro == b"I250":
            # parse raso: aqui só interessa a conta, que é o 2º campo. Decodificar
            # a linha inteira de milhões de partidas na indexação seria pagar duas
            # vezes — a linha completa só é lida quando o razão a pede
            partes = linha.split(b"|", 3)
            if len(partes) >= 3:
                conta = partes[2].decode(codificacao, errors="replace").strip()
                indice.posicoes_i250.setdefault(conta, array.array("q")).append(posicao)
                indice.partidas += 1
        elif registro == b"I200":
            indice.posicoes_i200.append(posicao)
        elif registro == b"I050":
            d = _dicionario(campos(linha.decode(codificacao, errors="replace")), "I050")
            ultima_conta = d["COD_CTA"]
            indice.contas.append(ContaContabil(
                codigo=ultima_conta, superior=d["COD_CTA_SUP"], nome=d["CTA"],
                nivel=d["NIVEL"], tipo=d["IND_CTA"], natureza=d["COD_NAT"]))
        elif registro == b"I051":
            # filho do I050 anterior: a conta referencial daquela analítica
            d = _dicionario(campos(linha.decode(codificacao, errors="replace")), "I051")
            if ultima_conta and d["COD_CTA_REF"].strip():
                indice.referencial[ultima_conta] = d["COD_CTA_REF"].strip()
        elif registro == b"0000":
            _identificar(indice, linha.decode(codificacao, errors="replace"))
        if avisar and posicao >= proximo_aviso:
            avisar(posicao, totais)
            proximo_aviso += a_cada
    if avisar:
        avisar(totais, totais)

    # os três que, faltando, tornam o arquivo inútil para o razão — e a mensagem
    # diz qual faltou, porque "ECD inválida" não ajuda ninguém
    if not indice.contas:
        raise EcdInvalida("Não achei o plano de contas (I050). Este arquivo é uma ECD?")
    if not indice.posicoes_i200:
        raise EcdInvalida("Não achei nenhum lançamento contábil (I200) no arquivo.")
    if not indice.partidas:
        raise EcdInvalida("Não achei nenhuma partida (I250): os lançamentos estão vazios.")

    log.info("ecd indexada", extra={
        "arquivo": os.path.basename(caminho), "cnpj": indice.cnpj,
        "contas": len(indice.contas), "analiticas": len(indice.analiticas),
        "lancamentos": indice.lancamentos, "partidas": indice.partidas,
    })
    return indice


@dataclass
class LinhaDoRazao:
    """Uma partida, com o lançamento que a contém e o saldo até ela."""

    cnpj: str
    conta: str
    descricao: str
    conta_referencial: str
    competencia: str        # aaaa-mm-01, o mês do lançamento
    data: str               # aaaa-mm-dd
    numero: str
    valor_do_lancamento: Decimal
    centro_de_custo: str
    valor: Decimal
    debito_ou_credito: str
    historico: str
    codigo_do_historico: str
    participante: str
    tipo: str
    saldo: Decimal
    arquivo: str

    @property
    def movimento(self) -> Decimal:
        """O que a partida faz com o saldo: débito soma, crédito subtrai."""
        return self.valor if self.debito_ou_credito == "D" else -self.valor


def razao(caminho: str, indice: IndiceDaEcd, contas: list[str] | None = None,
          de: date | None = None, ate: date | None = None) -> Iterator[LinhaDoRazao]:
    """O razão das contas pedidas, conta a conta, em ordem de data.

    `contas` vazio significa todas as analíticas. `de` e `ate` recortam o
    período — e partida **anterior** ao recorte não vira linha, mas **entra no
    saldo**: sem isso o razão do mês começaria do zero e o saldo seria ficção.

    Partida sem data utilizável fica de fora quando há recorte (não dá para
    afirmar que está na faixa) e entra quando não há.
    """
    alvos = contas if contas else [c.codigo for c in indice.analiticas]
    orfas = sem_data = fora = 0
    saiu = 0

    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        def linha_em(posicao: int) -> list[str]:
            arquivo.seek(posicao)
            return campos(arquivo.readline().decode(indice.codificacao, errors="replace"))

        for codigo in alvos:
            posicoes = indice.posicoes_i250.get(codigo)
            if not posicoes:
                continue
            dados_da_conta = indice.conta(codigo)
            colhidas: list[tuple[date, str, LinhaDoRazao]] = []
            abertura = ZERO

            for posicao in posicoes:
                # o lançamento dono da partida é o último I200 antes dela
                anterior = bisect.bisect_right(indice.posicoes_i200, posicao) - 1
                if anterior < 0:
                    orfas += 1
                    continue
                lancamento = _dicionario(linha_em(indice.posicoes_i200[anterior]), "I200")
                partida = _dicionario(linha_em(posicao), "I250")

                quando = _data(lancamento["DT_LCTO"])
                valor = _decimal(partida["VL_DC"])
                lado = (partida["IND_DC"] or "").strip().upper()
                movimento = valor if lado == "D" else -valor

                if de is not None or ate is not None:
                    if quando is None:
                        sem_data += 1
                        continue
                    if de is not None and quando < de:
                        abertura += movimento     # entra no saldo, não na lista
                        fora += 1
                        continue
                    if ate is not None and quando > ate:
                        fora += 1
                        continue

                colhidas.append((quando or date.min, lancamento["NUM_LCTO"], LinhaDoRazao(
                    cnpj=indice.cnpj, conta=codigo,
                    descricao=dados_da_conta.nome if dados_da_conta else "",
                    conta_referencial=indice.referencial.get(codigo, ""),
                    competencia=quando.replace(day=1).isoformat() if quando else "",
                    data=quando.isoformat() if quando else lancamento["DT_LCTO"],
                    numero=lancamento["NUM_LCTO"],
                    valor_do_lancamento=_decimal(lancamento["VL_LCTO"]),
                    centro_de_custo=partida["COD_CCUS"], valor=valor,
                    debito_ou_credito=lado, historico=partida["HIST"],
                    codigo_do_historico=partida["COD_HIST_PAD"],
                    participante=partida["COD_PART"],
                    tipo=TIPO_DE_LANCAMENTO.get((lancamento["IND_LCTO"] or "").strip().upper(),
                                                lancamento["IND_LCTO"]),
                    saldo=ZERO, arquivo=os.path.basename(caminho))))

            # a ordem do razão é a do tempo, não a do arquivo: o SPED não
            # obriga os lançamentos a virem em ordem de data
            saldo = abertura
            for _, _, pronta in sorted(colhidas, key=lambda x: (x[0], x[1])):
                saldo += pronta.movimento
                pronta.saldo = saldo
                saiu += 1
                yield pronta

    log.info("razão da ecd gerado", extra={
        "arquivo": os.path.basename(caminho), "contas": len(alvos), "linhas": saiu,
        "orfas": orfas, "fora_do_periodo": fora, "sem_data": sem_data,
    })
