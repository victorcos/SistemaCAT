"""A rodada do combustível: ler o lote de EFD ICMS/IPI e gravar as compras.

Entre o leitor (`sped/combustivel.py`, uma passada por arquivo) e o que vem
depois (classificador, apuração, auditoria) falta a mecânica da etapa: escolher
quais arquivos do lote valem, lê-los em ordem, gravar um parquet, somar o que a
tela mostra, e não deixar arquivo pela metade quando alguém cancela.

É a mesma mecânica de `exclusoes_por_item.py`, e por isso as peças vêm dele:
`Escritor`, `parar_se_pedirem` e o `try/finally` que apaga o parquet
interrompido. **O que não vem é a soma.** O `Total` de lá lê `linha.pis`,
`linha.cofins` e `linha.selic_sobre_o_pis` — é moldado em PIS/COFINS *e* em
SELIC, os dois vícios que esta tese não tem (ver `DOMINIO_COMBUSTIVEL.md`, §9:
crédito escritural de ICMS não corrige, Súmula 411 do STJ).

## Ela grava todas as compras, e o crédito de cada uma

Cada linha passa pelo classificador (`sped/classificador_de_combustivel.py`) e
pela apuração (`sped/credito_de_combustivel.py`), e o parquet sai com as três
camadas: o que o arquivo trouxe, o que o classificador decidiu e o que a tabela
calculou. **Gravar tudo é deliberado:** a compra que não é combustível também
sai, com `produto = "fora"`, porque é assim que se confere que ela foi
descartada por regra e não por omissão.

### Três somas, três perguntas

* `grupos` — **o que entrou**, por CST e unidade como o arquivo os escreveu;
* `creditos` — **quanto vale**, por produto e regime, com a parte estimada à
  parte;
* `recusas` — **o que era da tese e não entrou**, por motivo.

As chaves são diferentes de propósito. Misturar CST com produto somaria litro
declarado com litro convertido, e um "balde de recusas" que recebesse tudo o que
não gera crédito receberia a loja inteira — parafuso incluído. Só entra ali o
que o classificador pôs na tese.

## A regra da retificadora não se reescreve

Escolher um arquivo por `(CNPJ, competência)` — retificadora vence, depois a
mais nova — é `gestao.montagem.selecionar_por_cnpj_e_competencia`. Esta etapa
**chama** aquela função em vez de repetir a regra: o desempate por data de
modificação é sutil, e regra sutil escrita duas vezes é regra que vai divergir
(a mesma lição de `sped/cadastro.py`).

Para isso o identificador monta um `ApuracaoEFD` com os cinco campos que a
seleção usa. O `tipo_escrit` dela vem do **`COD_FIN`** da EFD ICMS/IPI, que tem
outro nome e a mesma convenção: `0` original, `1` substituto. Conferido em 40
arquivos reais — 17 com `0` e 23 com `1`.

**E a de-duplicação não é teórica.** Os 411 arquivos da empresa 06 estão em três
pastas que repetem as mesmas competências; um lote que aponte a pasta-mãe traz
cada mês três vezes, e somar os três triplicaria a tese. Aconteceu antes, na
empresa 16: R$ 203.600,56 a mais por somar original e retificadora do mesmo mês.

## O que esta etapa deliberadamente não faz

**Não aplica prescrição.** O ICMS prescreve em cinco anos contados da **emissão
do documento** (LC 87/96, art. 23), e não da competência — regra diferente da do
PIS/COFINS, que `dominio/piscofins/prescricao.py` implementa. Escrever "cinco
anos, mais ou menos" aqui seria inventar a regra no lugar errado.

O resumo traz, em vez disso, **a primeira e a última emissão encontradas**: quem
roda vê o intervalo e sabe se prescrição é assunto, sem o módulo fingir que
resolveu.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from cat.infraestrutura.analitico.escrita import Escritor, parar_se_pedirem
from cat.infraestrutura.gestao.modelos import ApuracaoEFD
from cat.infraestrutura.gestao.montagem import selecionar_por_cnpj_e_competencia
from cat.infraestrutura.sped.classificador_de_combustivel import (
    Classificacao,
    classificar,
)
from cat.infraestrutura.sped.combustivel import LinhaDeCompra, compras
from cat.infraestrutura.sped.credito_de_combustivel import Credito, apurar
from cat.infraestrutura.sped.leitor import (
    campos,
    codificacao_de,
    registro_de,
    tamanho_de,
)
from cat.infraestrutura.sped.registros_icms import CAMPOS
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO = "compras_de_combustivel.parquet"

# o COD_FIN da EFD ICMS/IPI: 1 é arquivo substituto, que é o que a seleção
# chama de retificadora
SUBSTITUTO = "1"

_POS_0000 = {nome: i for i, nome in enumerate(CAMPOS["0000"])}


@dataclass
class Andamento:
    """O que a tela mostra enquanto roda."""

    arquivos: int = 0
    linhas: int = 0


@dataclass(frozen=True)
class Grupo:
    """Onde a soma mora: estabelecimento, mês, código de tributação e unidade.

    **A unidade entra na chave de propósito.** O mesmo cliente escreve o litro
    como `L`, `LT` e `LTS` — medido na empresa 06 —, e somar as três numa coluna
    só produziria um número sem grandeza. Separadas, a soma é conferível e o
    tamanho do problema de normalização fica visível para o classificador.

    Congelado porque é chave de dicionário: `@dataclass` sem `frozen` anula o
    `__hash__` e o erro só aparece na primeira linha somada.
    """

    cnpj: str
    competencia: str
    cst: str          # o código como o arquivo trouxe, de três dígitos
    unidade: str


@dataclass
class Total:
    """Uma soma de compras. Sem PIS, sem COFINS e sem SELIC — ver o topo."""

    linhas: int = 0
    quantidade: Decimal = Decimal(0)
    valor: Decimal = Decimal(0)

    def somar(self, linha: LinhaDeCompra) -> None:
        self.linhas += 1
        self.quantidade += linha.quantidade or Decimal(0)
        self.valor += linha.valor_do_item or Decimal(0)


@dataclass(frozen=True)
class GrupoDeCredito:
    """Onde o **crédito** soma: estabelecimento, mês, produto e regime.

    Chave diferente da do `Grupo` de propósito. Aquele responde "o que entrou"
    — e por isso guarda o CST e a unidade como o arquivo os escreveu. Este
    responde "quanto vale", e aí o que importa é o produto que o classificador
    decidiu e a era que a tabela aplicou.

    Somar os dois na mesma chave misturaria litro declarado com litro
    convertido, e CST com produto.
    """

    cnpj: str
    competencia: str
    produto: str
    regime: str


@dataclass
class TotalDeCredito:
    """Uma soma de crédito, com a parte estimada à parte.

    `estimado` é quanto do `valor` veio da era do ST, onde a base é o valor do
    item e não a base real. Separado, e não um sinalizador por grupo, porque um
    mês pode ter as duas eras — a virada do diesel foi no meio de 2023.
    """

    linhas: int = 0
    quantidade: Decimal = Decimal(0)   # já na unidade tributada
    valor: Decimal = Decimal(0)
    estimado: Decimal = Decimal(0)

    def somar(self, c: Credito) -> None:
        self.linhas += 1
        self.quantidade += c.quantidade or Decimal(0)
        self.valor += c.valor or Decimal(0)
        if c.estimativa:
            self.estimado += c.valor or Decimal(0)


@dataclass
class Recusa:
    """Quantas linhas caíram por um motivo, e uma frase de exemplo.

    A frase traz valores dentro — competência, alíquota, a suspeita de ad rem —
    e por isso não serve de chave. Guardar **uma** delas é o que permite à tela
    dizer "ad rem não conferida (9 linhas)" e abrir o porquê inteiro de uma.
    """

    linhas: int = 0
    exemplo: str = ""

    def somar(self, c: Credito) -> None:
        self.linhas += 1
        if not self.exemplo:
            self.exemplo = c.porque


@dataclass
class Resumo:
    """O que a rodada devolve para a tela e para o log."""

    arquivos_no_lote: int = 0
    arquivos_lidos: int = 0
    ignorados_por_duplicidade: int = 0
    ilegiveis: int = 0
    linhas: int = 0
    estabelecimentos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    grupos: dict[Grupo, Total] = field(default_factory=dict)
    # o crédito, por estabelecimento, mês, produto e regime
    creditos: dict[GrupoDeCredito, TotalDeCredito] = field(default_factory=dict)
    # por que as linhas da tese não entraram no total, por motivo
    recusas: dict[str, Recusa] = field(default_factory=dict)
    # quantas linhas o classificador marcou para revisão humana
    a_revisar: int = 0
    avisos: list[str] = field(default_factory=list)
    # o intervalo das emissões, que é o que diz se prescrição é assunto
    primeira_emissao: str = ""
    ultima_emissao: str = ""
    segundos: float = 0.0

    @property
    def credito(self) -> Decimal:
        """O total que entra no pedido. **Só o que não foi recusado.**"""
        return sum((t.valor for t in self.creditos.values()), Decimal(0))

    @property
    def credito_estimado(self) -> Decimal:
        """Quanto do total veio da era do ST, onde a base é proxy.

        Fica à vista no resumo, e não em nota de rodapé: um total com estimativa
        dentro não se apresenta sem dizer quanto.
        """
        return sum((t.estimado for t in self.creditos.values()), Decimal(0))

    @property
    def linhas_recusadas(self) -> int:
        return sum(r.linhas for r in self.recusas.values())

    @property
    def linhas_de_monofasico(self) -> int:
        """Quantas linhas de CST 61 — a dimensão da tese, sem classificador."""
        return sum(t.linhas for g, t in self.grupos.items()
                   if g.cst[1:] == "61" and len(g.cst) == 3)


def colunas() -> list[str]:
    """As colunas do parquet, na ordem.

    Vive aqui e não no leitor de propósito: o leiaute do parquet é assunto da
    etapa, e o leitor não deve saber que existe parquet. O `tributacao` sai
    desmontado em quatro colunas, porque parquet não guarda objeto.
    """
    return [
        "cnpj", "uf", "competencia",
        "situacao", "modelo", "serie", "numero", "chave", "data_de_emissao",
        "cnpj_do_fornecedor", "nome_do_fornecedor",
        "numero_do_item", "codigo_do_item", "descricao_no_documento",
        "quantidade", "unidade", "valor_do_item", "cfop",
        "cst_icms", "origem", "cst", "csosn", "ambiguo",
        "base_do_icms", "aliquota_do_icms", "valor_do_icms",
        "base_do_st", "aliquota_do_st", "valor_do_st",
        "descricao_do_item", "ncm", "unidade_de_inventario", "cest",
        # o que o classificador decidiu
        "produto", "confianca", "revisar", "por_que_classificou",
        # o que a apuração calculou
        "regime", "quantidade_tributada", "fator", "ad_rem", "fcv",
        "base_do_credito", "aliquota_do_credito", "credito",
        "cobertura", "estimativa", "motivo_da_recusa", "por_que_apurou",
    ]


def _como_dicionario(linha: LinhaDeCompra, classificacao: Classificacao,
                     credito: Credito) -> dict[str, str]:
    """A linha no formato do parquet, com vazio onde o campo veio vazio.

    `None` vira string vazia e não `"0"`: **vazio não é zero** continua valendo
    depois de gravado, e quem ler o parquet precisa distinguir "o fornecedor
    não destacou" de "destacou zero".
    """
    def texto(valor: Decimal | None) -> str:
        return "" if valor is None else str(valor)

    t = linha.tributacao
    return {
        "cnpj": linha.cnpj_do_estabelecimento,
        "uf": linha.uf,
        "competencia": linha.competencia,
        "situacao": linha.situacao,
        "modelo": linha.modelo,
        "serie": linha.serie,
        "numero": linha.numero,
        "chave": linha.chave,
        "data_de_emissao": linha.data_de_emissao,
        "cnpj_do_fornecedor": linha.cnpj_do_fornecedor,
        "nome_do_fornecedor": linha.nome_do_fornecedor,
        "numero_do_item": linha.numero_do_item,
        "codigo_do_item": linha.codigo_do_item,
        "descricao_no_documento": linha.descricao_no_documento,
        "quantidade": texto(linha.quantidade),
        "unidade": linha.unidade,
        "valor_do_item": texto(linha.valor_do_item),
        "cfop": linha.cfop,
        "cst_icms": t.bruto,
        "origem": t.origem,
        "cst": t.cst,
        "csosn": t.csosn,
        "ambiguo": "1" if t.ambiguo else "",
        "base_do_icms": texto(linha.base_do_icms),
        "aliquota_do_icms": texto(linha.aliquota_do_icms),
        "valor_do_icms": texto(linha.valor_do_icms),
        "base_do_st": texto(linha.base_do_st),
        "aliquota_do_st": texto(linha.aliquota_do_st),
        "valor_do_st": texto(linha.valor_do_st),
        "descricao_do_item": linha.descricao_do_item,
        "ncm": linha.ncm,
        "unidade_de_inventario": linha.unidade_de_inventario,
        "cest": linha.cest,
        "produto": classificacao.produto,
        "confianca": classificacao.confianca,
        "revisar": "1" if classificacao.revisar else "",
        "por_que_classificou": classificacao.porque,
        "regime": credito.regime,
        "quantidade_tributada": texto(credito.quantidade),
        "fator": texto(credito.fator),
        "ad_rem": texto(credito.ad_rem),
        "fcv": texto(credito.fcv),
        "base_do_credito": texto(credito.base),
        "aliquota_do_credito": texto(credito.aliquota),
        # vazio, e não "0,00", quando a linha foi recusada: zero soma, e quem
        # abrir o parquet precisa distinguir "não gerou crédito" de "ninguém
        # calculou"
        "credito": texto(credito.valor),
        "cobertura": credito.cobertura,
        "estimativa": "1" if credito.estimativa else "",
        "motivo_da_recusa": credito.motivo,
        "por_que_apurou": credito.porque,
    }


def identificar(caminho: str) -> ApuracaoEFD | None:
    """Quem e quando, lendo só o `0000`.

    O `0000` é a primeira linha do arquivo, então isto custa uma leitura de
    poucos bytes por arquivo — e é o que permite de-duplicar 411 arquivos sem
    abrir nenhum deles por inteiro.

    Devolve `None` para arquivo que não traz `0000` reconhecível: pode ser
    EFD-Contribuições, pode ser outra coisa, e nos dois casos não é este leitor
    que a lê.
    """
    try:
        with open(caminho, "rb") as arquivo:
            for linha in arquivo:
                if registro_de(linha) != b"0000":
                    continue
                valores = campos(linha.decode(codificacao_de(caminho),
                                              errors="replace"))
                if len(valores) != len(CAMPOS["0000"]):
                    return None
                inicio = valores[_POS_0000["DT_INI"]].strip()
                if len(inicio) != 8 or not inicio.isdigit():
                    return None
                return ApuracaoEFD(
                    arquivo=caminho,
                    file_hash="",
                    tamanho=tamanho_de(caminho),
                    cnpj=valores[_POS_0000["CNPJ"]].strip(),
                    razao_social=valores[_POS_0000["NOME"]].strip(),
                    periodo=f"{inicio[4:]}-{inicio[2:4]}",
                    dt_ini=inicio,
                    dt_fin=valores[_POS_0000["DT_FIN"]].strip(),
                    cod_ver=valores[_POS_0000["COD_VER"]].strip(),
                    tipo_escrit=valores[_POS_0000["COD_FIN"]].strip(),
                )
    except OSError as erro:
        log.warning("não deu para identificar a EFD ICMS/IPI",
                    extra={"arquivo": os.path.basename(caminho),
                           "erro": str(erro)})
    return None


def escolher(caminhos: list[str]) -> tuple[list[ApuracaoEFD], list[str], int]:
    """Um arquivo por `(CNPJ, competência)`, com o que ficou de fora dito.

    Devolve as escolhidas, os avisos e quantas foram descartadas. A regra do
    desempate não está aqui — é `selecionar_por_cnpj_e_competencia`, e chamar em
    vez de copiar é o ponto.
    """
    identificadas: list[ApuracaoEFD] = []
    avisos: list[str] = []
    for caminho in caminhos:
        apuracao = identificar(caminho)
        if apuracao is None:
            avisos.append(f"{os.path.basename(caminho)}: não é uma EFD "
                          f"ICMS/IPI reconhecível; ficou de fora.")
            continue
        identificadas.append(apuracao)

    escolhidas, avisos_da_selecao = selecionar_por_cnpj_e_competencia(identificadas)
    avisos.extend(avisos_da_selecao)
    return escolhidas, avisos, len(identificadas) - len(escolhidas)


def extrair(caminhos: list[str], destino: str,
            avisar: Callable[[Andamento], None] | None = None,
            deve_parar: Callable[[], bool] | None = None) -> Resumo:
    """Grava as compras do lote em parquet e devolve o resumo.

    Arquivo que não der para ler vira aviso e a rodada segue: uma EFD corrompida
    no meio de cinco anos não pode derrubar a etapa inteira. O cancelamento,
    sim, sobe — e aí o parquet pela metade é apagado, porque quem o abrir depois
    não tem como saber que faltou arquivo.
    """
    inicio = time.time()
    os.makedirs(destino, exist_ok=True)

    resumo = Resumo(arquivos_no_lote=len(caminhos))
    escolhidas, avisos, ignorados = escolher(caminhos)
    resumo.avisos.extend(avisos)
    resumo.ignorados_por_duplicidade = ignorados

    andamento = Andamento()
    estabelecimentos: set[str] = set()
    competencias: set[str] = set()
    emissoes: list[str] = []

    caminho_do_parquet = os.path.join(destino, ARQUIVO)
    escritor = Escritor(caminho_do_parquet, colunas())
    inteira = False
    try:
        for apuracao in escolhidas:
            parar_se_pedirem(deve_parar)
            _de_um_arquivo(apuracao, escritor, resumo, andamento,
                           estabelecimentos, competencias, emissoes)
            if avisar:
                avisar(andamento)
        inteira = True
    finally:
        escritor.fechar()
        if not inteira:
            _apagar(caminho_do_parquet)

    resumo.linhas = escritor.gravadas
    resumo.estabelecimentos = sorted(estabelecimentos)
    resumo.competencias = sorted(competencias)
    if emissoes:
        resumo.primeira_emissao = min(emissoes)
        resumo.ultima_emissao = max(emissoes)
    resumo.segundos = round(time.time() - inicio, 1)

    log.info("compras de combustível extraídas", extra=serializar(resumo))
    return resumo


def _apagar(caminho: str) -> None:
    try:
        os.remove(caminho)
    except OSError as erro:
        log.warning("não deu para apagar o parquet interrompido",
                    extra={"arquivo": os.path.basename(caminho),
                           "erro": str(erro)})


def _de_um_arquivo(apuracao: ApuracaoEFD, escritor: Escritor, resumo: Resumo,
                   andamento: Andamento, estabelecimentos: set[str],
                   competencias: set[str], emissoes: list[str]) -> None:
    nome = os.path.basename(apuracao.arquivo)
    try:
        codificacao = codificacao_de(apuracao.arquivo)
        for linha in compras(apuracao.arquivo, codificacao):
            classificacao = classificar(
                linha.descricao_do_item, linha.ncm, linha.unidade,
                linha.descricao_no_documento)
            credito = apurar(linha, classificacao)
            escritor.escrever(_como_dicionario(linha, classificacao, credito))
            estabelecimentos.add(linha.cnpj_do_estabelecimento)
            competencias.add(linha.competencia)
            if linha.data_de_emissao:
                emissoes.append(linha.data_de_emissao)
            _somar(resumo, linha, classificacao, credito)
    # só o arquivo ilegível vira aviso e segue; o cancelamento sobe
    except (OSError, ValueError) as erro:
        log.warning("não deu para ler as compras da EFD ICMS/IPI",
                    extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao ler as compras.")
        return

    resumo.arquivos_lidos += 1
    andamento.arquivos += 1
    andamento.linhas = escritor.gravadas


def _somar(resumo: Resumo, linha: LinhaDeCompra, classificacao: Classificacao,
           credito: Credito) -> None:
    """A linha entra em até três somas, e cada uma responde outra pergunta.

    A das **compras** (`grupos`) responde "o que entrou", e conta tudo. A do
    **crédito** conta só o que entra no total. A das **recusas** conta o que era
    da tese e não entrou — e nunca o que nem era da tese, senão o balde de
    recusas viraria a loja inteira.
    """
    resumo.grupos.setdefault(
        Grupo(cnpj=linha.cnpj_do_estabelecimento, competencia=linha.competencia,
              cst=linha.tributacao.bruto, unidade=linha.unidade),
        Total()).somar(linha)

    if classificacao.revisar:
        resumo.a_revisar += 1

    if credito.entra_no_total:
        resumo.creditos.setdefault(
            GrupoDeCredito(cnpj=linha.cnpj_do_estabelecimento,
                           competencia=linha.competencia,
                           produto=credito.produto, regime=credito.regime),
            TotalDeCredito()).somar(credito)
    elif classificacao.entra_na_tese:
        resumo.recusas.setdefault(credito.motivo, Recusa()).somar(credito)


def serializar(resumo: Resumo) -> dict:
    """O resumo como dicionário, para o log e para a rota.

    Os grupos saem contados, e não listados: numa base de supermercado são
    milhares, e log que não se lê não serve de log. Quem quer os grupos abre o
    parquet.
    """
    return {
        "arquivos_no_lote": resumo.arquivos_no_lote,
        "arquivos_lidos": resumo.arquivos_lidos,
        "ignorados_por_duplicidade": resumo.ignorados_por_duplicidade,
        "ilegiveis": resumo.ilegiveis,
        "linhas": resumo.linhas,
        "linhas_de_monofasico": resumo.linhas_de_monofasico,
        "estabelecimentos": len(resumo.estabelecimentos),
        "competencias": len(resumo.competencias),
        "grupos": len(resumo.grupos),
        "credito": str(resumo.credito),
        "credito_estimado": str(resumo.credito_estimado),
        "linhas_recusadas": resumo.linhas_recusadas,
        # o motivo e a contagem, sem a frase: ela é longa e vai para a tela,
        # não para o log
        "recusas": {m: r.linhas for m, r in sorted(resumo.recusas.items())},
        "a_revisar": resumo.a_revisar,
        "primeira_emissao": resumo.primeira_emissao,
        "ultima_emissao": resumo.ultima_emissao,
        "avisos": len(resumo.avisos),
        "segundos": resumo.segundos,
    }
