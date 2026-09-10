"""Relatório gerencial — os campos que o trabalho precisa, e como achá-los.

Muitas empresas não liberam o XML, só o relatório gerencial do ERP delas. O
formato muda de empresa para empresa, mas **o que precisamos é sempre o
mesmo**. Então o catálogo de campos-alvo é fixo e o mapeamento para as colunas
de origem é flexível: casa por NOME de coluna, não por posição, porque posição
muda entre versões do mesmo relatório.

Um achado que mudou o desenho: a pasta de "relatório gerencial" de uma empresa
não tem um formato, tem **três espécies de arquivo** com propósitos diferentes
(:class:`Especie`). Tentar ler as três com o mesmo catálogo faz o sistema
reprovar arquivo bom por falta de campo que aquela espécie nunca teve. Então
primeiro se classifica, depois se mapeia.

O outro achado: o relatório de movimento do Amigão já traz colunas rotuladas
``XML`` — base e valor de ICMS-ST vindos do documento, mais a chave da NF-e.
Ou seja, **o relatório gerencial pode substituir o XML** para os campos de que
precisamos, quando o ERP faz essa extração. Nem todo ERP faz, e por isso o
campo é opcional e o sistema diz quando ele falta.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum


class Especie(str, Enum):
    """Que espécie de arquivo é, pelo que ele descreve."""

    MOVIMENTO = "movimento"
    INVENTARIO = "inventario"
    RESUMO = "resumo"

    @property
    def rotulo(self) -> str:
        return {
            Especie.MOVIMENTO: "Movimento por documento",
            Especie.INVENTARIO: "Inventário",
            Especie.RESUMO: "Resumo por produto",
        }[self]

    @property
    def descricao(self) -> str:
        return {
            Especie.MOVIMENTO:
                "Uma linha por item de nota. É a fonte do razão da Ficha 3.",
            Especie.INVENTARIO:
                "Uma linha por item, com saldo e imposto médio por unidade. "
                "Serve de estoque de abertura.",
            Especie.RESUMO:
                "Uma linha por item, com totais do período por tipo de "
                "movimento. Não tem data nem documento: serve para conferir, "
                "não para montar o razão.",
        }[self]

    @property
    def serve_para_razao(self) -> bool:
        """Só o movimento tem data e CFOP por linha, que é o que o razão pede."""
        return self is Especie.MOVIMENTO


class Necessidade(str, Enum):
    OBRIGATORIO = "obrigatorio"     # sem ele o arquivo não serve
    IMPORTANTE = "importante"       # dá para seguir, mas com perda
    OPCIONAL = "opcional"

    @property
    def rotulo(self) -> str:
        return {
            Necessidade.OBRIGATORIO: "Obrigatório",
            Necessidade.IMPORTANTE: "Importante",
            Necessidade.OPCIONAL: "Opcional",
        }[self]


@dataclass(frozen=True)
class Campo:
    chave: str
    nome: str
    para_que: str
    necessidade: Necessidade
    sinonimos: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Movimento: uma linha por item de documento. É a espécie que alimenta o razão.
# Esta lista É o contrato do relatório gerencial de movimento.
# ---------------------------------------------------------------------------
CAMPOS_MOVIMENTO: tuple[Campo, ...] = (
    # ---------- identificação do documento ----------
    Campo("chave", "Chave do documento", "amarra a linha à NF-e e permite cruzar com o SPED",
          Necessidade.IMPORTANTE, ("chave dfe", "chave nfe", "chave de acesso", "chave")),
    Campo("numero_doc", "Número do documento", "identifica a nota quando não há chave",
          Necessidade.IMPORTANTE, ("numero dcto", "numero documento", "num doc", "nf")),
    Campo("data", "Data de emissão", "define a posição do movimento no razão",
          Necessidade.OBRIGATORIO, ("dt emissao", "data emissao", "dt mvto", "data movimento", "emissao")),
    Campo("cnpj_participante", "CNPJ do participante", "distingue compra de substituto e de substituído",
          Necessidade.IMPORTANTE, ("cnpj cpf", "cnpj", "cpf cnpj", "cnpj fornecedor")),
    Campo("uf_participante", "UF do participante", "operação interestadual muda a regra",
          Necessidade.OPCIONAL, ("uf", "uf mvto", "estado")),

    # ---------- item ----------
    Campo("codigo_item", "Código do item", "é a chave da ficha: uma por mercadoria",
          Necessidade.OBRIGATORIO, ("codigo", "cod item", "codigo produto", "cod produto")),
    Campo("descricao_item", "Descrição do item", "identifica a mercadoria para conferência e de-para",
          Necessidade.IMPORTANTE, ("descricao", "descricao cliente", "descricao produto", "produto")),
    Campo("codigo_barras", "Código de barras", "chave exata do de-para entre empresas",
          Necessidade.OPCIONAL, ("codigo barras", "ean", "gtin", "cod barras")),
    Campo("ncm", "NCM", "classificação fiscal, usada no enquadramento",
          Necessidade.OPCIONAL, ("ncm", "trib", "classificacao fiscal")),

    # ---------- movimento ----------
    Campo("quantidade", "Quantidade", "entra no custo médio ponderado móvel",
          Necessidade.OBRIGATORIO, ("qtde unitaria", "quantidade", "qtd", "qtde")),
    Campo("valor_item", "Valor do item", "confere o total e apura divergência",
          Necessidade.IMPORTANTE, ("valor", "valor total", "vlr item", "valor item")),
    Campo("cfop", "CFOP", "diz o que a operação é: entrada, saída, devolução, baixa",
          Necessidade.OBRIGATORIO, ("cfop mvto", "cfop", "cod fiscal")),
    Campo("cst_icms", "CST do ICMS", "situação tributária, separa o que é ST do que não é",
          Necessidade.IMPORTANTE, ("cst icms", "cst", "situacao tributaria")),
    Campo("indicador_entrada", "Indicador de entrada", "distingue entrada de saída quando o CFOP não basta",
          Necessidade.OPCIONAL, ("ent", "entrada", "ind mov", "e s")),

    # ---------- ICMS próprio ----------
    Campo("bc_icms", "Base de cálculo do ICMS", "compõe o ICMS suportado",
          Necessidade.IMPORTANTE, ("bc icms", "base icms", "base calculo icms", "valor bc icms")),
    Campo("valor_icms", "Valor do ICMS", "é a parcela da operação própria do substituto",
          Necessidade.OBRIGATORIO, ("valor icms", "vlr icms", "icms")),

    # ---------- ICMS-ST: o coração do trabalho ----------
    Campo("bc_st", "Base de cálculo da ST", "confere o cálculo da retenção",
          Necessidade.IMPORTANTE,
          ("valor bc st informada", "bc st", "base st", "base calculo st",
           "valor bc st", "bc icms st")),
    Campo("valor_st", "Valor do ICMS-ST", "é a parcela retida, o que se busca ressarcir",
          Necessidade.OBRIGATORIO,
          ("valor st informada", "valor sub trib", "valor st", "vlr st",
           "valor icms st", "icms st")),
    Campo("valor_fcp_st", "FCP retido por ST", "o manual inclui o FECOEP no imposto suportado",
          Necessidade.IMPORTANTE,
          ("valor fcp st", "fcp st", "valor fcp st ret", "vlr fcp st")),

    # ---------- valores vindos do XML pelo próprio ERP ----------
    Campo("bc_st_xml", "Base da ST no XML", "o valor do documento, que prevalece sobre o do ERP",
          Necessidade.OPCIONAL, ("bc icms st xml", "base st xml", "bc st xml")),
    Campo("valor_st_xml", "Valor da ST no XML", "quando existe, é o valor que vale",
          Necessidade.IMPORTANTE, ("vr icms st xml", "valor icms st xml", "valor st xml")),
    Campo("st_retido_anterior", "ST retido anteriormente", "o suportado de quem compra de substituído",
          Necessidade.IMPORTANTE,
          ("st integral", "icms st retido anteriormente", "vicmssubstituto",
           "icms substituto", "st retido")),
)


# ---------------------------------------------------------------------------
# Inventário: uma linha por item, com o saldo e o imposto médio por unidade.
#
# Vale mais do que parece. O item 4.1.1 do manual manda abrir a Ficha 3 com o
# estoque, e o item 3.3.8 manda derivar o ST desse estoque pelas entradas mais
# recentes. Quando o ERP já entrega ICMS e ST médios por unidade, o estoque de
# abertura sai pronto — sem a derivação, que é onde mais se erra.
#
# Só que "quando entrega" não é sempre, e coluna existir não é coluna
# preenchida: no inventário do Amigão as quatro colunas de imposto por unidade
# estão no cabeçalho e vêm vazias nas 842.785 linhas. Por isso o imposto é
# IMPORTANTE e não OBRIGATÓRIO, e por isso existe `tem_imposto_pronto` — o
# sistema precisa dizer que vai ter de derivar, em vez de somar zero calado.
# A alíquota vigente, essa vem preenchida, e permite reconstruir o ICMS.
# ---------------------------------------------------------------------------
CAMPOS_INVENTARIO: tuple[Campo, ...] = (
    Campo("estabelecimento", "Estabelecimento", "o estoque é por loja, não da empresa toda",
          Necessidade.IMPORTANTE,
          ("ifis unid codigo", "unid codigo", "loja", "filial", "estabelecimento", "unidade")),
    Campo("codigo_item", "Código do item", "é a chave da ficha: uma por mercadoria",
          Necessidade.OBRIGATORIO,
          ("ifis prod codigo", "prod codigo", "codigo produto", "cod produto", "codigo")),
    Campo("descricao_item", "Descrição do item", "identifica a mercadoria para conferência",
          Necessidade.IMPORTANTE,
          ("ifis prod descricao", "prod descricao", "descricao produto", "descricao")),
    Campo("codigo_barras", "Código de barras", "chave exata do de-para entre empresas",
          Necessidade.OPCIONAL, ("codigo barras", "ean", "gtin", "cod barras")),
    Campo("ncm", "NCM", "classificação fiscal, usada no enquadramento",
          Necessidade.OPCIONAL, ("ifis ctfiscal", "ctfiscal", "ncm", "trib", "classificacao fiscal")),

    Campo("quantidade_estoque", "Quantidade em estoque", "é o saldo que abre a ficha",
          Necessidade.OBRIGATORIO,
          ("ifis estoque", "quantidade estoque", "qtde estoque", "saldo", "estoque")),
    Campo("custo_medio", "Custo médio", "é o valor que abre a ficha, no critério do manual",
          Necessidade.IMPORTANTE,
          ("ifis ctmedio", "ctmedio", "custo medio", "custo medio unitario")),
    Campo("custo_empresa", "Custo da empresa", "alternativa ao custo médio quando ele vem zerado",
          Necessidade.OPCIONAL, ("ifis ctempresa", "ctempresa", "custo empresa")),
    Campo("data_ultima_compra", "Data da última compra",
          "é o que o item 3.3.8 usa para achar a entrada mais recente",
          Necessidade.OPCIONAL,
          ("ifis dtultcompra", "dtultcompra", "data ultima compra", "dt ult compra")),

    # o imposto por unidade, que é o motivo de este arquivo importar
    Campo("bc_st_unitaria", "Base da ST por unidade", "confere o ST médio do estoque",
          Necessidade.OPCIONAL,
          ("ifis vlrmediounicms st bc", "vlrmediounicms st bc", "bc st unitaria", "bc st medio")),
    Campo("st_unitario", "ICMS-ST por unidade", "é o ST suportado do estoque de abertura",
          Necessidade.IMPORTANTE,
          ("ifis vlrmediounicms st", "vlrmediounicms st", "st unitario", "st medio unitario")),
    Campo("fcp_st_unitario", "FCP-ST por unidade", "o manual inclui o FECOEP no imposto suportado",
          Necessidade.IMPORTANTE,
          ("ifis vlrmediounfcp st", "vlrmediounfcp st", "fcp st unitario", "fcp st medio")),
    Campo("icms_unitario", "ICMS por unidade", "é a parcela própria dentro do imposto suportado",
          Necessidade.IMPORTANTE,
          ("ifis vlrmediounicms", "vlrmediounicms", "icms unitario", "icms medio unitario")),
    Campo("aliquota_icms", "Alíquota do ICMS", "reconstrói o imposto quando o valor unitário falta",
          Necessidade.OPCIONAL,
          ("ifis icmsaliqvigente", "icmsaliqvigente", "aliquota icms", "aliq icms")),
    Campo("aliquota_fcp", "Alíquota do FCP", "reconstrói o FECOEP quando o valor unitário falta",
          Necessidade.OPCIONAL,
          ("ifis fcpaliqvigente", "fcpaliqvigente", "aliquota fcp", "aliq fcp")),
)


# ---------------------------------------------------------------------------
# Resumo por produto: totais do período, um por item. Não tem data nem
# documento, então não monta razão — mas fecha total com o que o razão apurou,
# e é o que sobra quando a empresa não solta o movimento analítico.
#
# O cabeçalho vem em dois níveis (``Devoluções`` em cima de ``Venda``), que o
# módulo de leiaute junta antes de chegar aqui.
# ---------------------------------------------------------------------------
CAMPOS_RESUMO: tuple[Campo, ...] = (
    Campo("codigo_item", "Código do item", "é a chave do confronto com o razão",
          Necessidade.OBRIGATORIO, ("codigo", "cod item", "codigo produto", "cod produto")),
    Campo("descricao_item", "Descrição do item", "identifica a mercadoria",
          Necessidade.IMPORTANTE, ("descricao", "descricao produto", "produto")),
    Campo("codigo_barras", "Código de barras", "chave exata do de-para entre empresas",
          Necessidade.OPCIONAL, ("codigo barras", "ean", "gtin")),
    Campo("ncm", "NCM", "classificação fiscal",
          Necessidade.OPCIONAL, ("trib", "ncm")),

    Campo("qtd_compras", "Quantidade comprada", "total de entrada por compra no período",
          Necessidade.OBRIGATORIO, ("qtde compras", "quantidade compras")),
    Campo("valor_compras", "Valor comprado", "total de entrada por compra no período",
          Necessidade.IMPORTANTE, ("compras liquidas", "valor compras", "compras")),
    Campo("qtd_vendas", "Quantidade vendida", "total de saída por venda no período",
          Necessidade.OBRIGATORIO, ("qtde vendas", "quantidade vendas")),
    Campo("valor_vendas", "Valor vendido", "total de saída por venda no período",
          Necessidade.IMPORTANTE, ("vendas liquidas", "valor vendas", "vendas")),
    Campo("qtd_devolucao_venda", "Quantidade devolvida de venda",
          "devolução de venda volta ao estoque",
          Necessidade.IMPORTANTE, ("qtde devolucoes venda", "qtde devolucao venda")),
    Campo("valor_devolucao_venda", "Valor devolvido de venda",
          "devolução de venda volta ao estoque",
          Necessidade.OPCIONAL, ("devolucoes venda", "devolucao venda")),
    Campo("qtd_devolucao_compra", "Quantidade devolvida de compra",
          "devolução de compra sai do estoque",
          Necessidade.IMPORTANTE, ("qtde devolucoes compra", "qtde devolucao compra")),
    Campo("valor_devolucao_compra", "Valor devolvido de compra",
          "devolução de compra sai do estoque",
          Necessidade.OPCIONAL, ("devolucoes compra", "devolucao compra")),
    Campo("qtd_perdas", "Quantidade de perda", "baixa de estoque, que é o CFOP 5927 do trabalho",
          Necessidade.IMPORTANTE, ("qtde perdas estoque", "qtde perdas", "quantidade perdas")),
    Campo("valor_perdas", "Valor de perda", "baixa de estoque, que é o CFOP 5927 do trabalho",
          Necessidade.OPCIONAL, ("perdas", "valor perdas")),
    Campo("valor_icms", "Valor do ICMS", "fecha o imposto do período contra o razão",
          Necessidade.OPCIONAL, ("vl icms informado", "valor icms", "vl icms", "icms")),
)


CATALOGOS: dict[Especie, tuple[Campo, ...]] = {
    Especie.MOVIMENTO: CAMPOS_MOVIMENTO,
    Especie.INVENTARIO: CAMPOS_INVENTARIO,
    Especie.RESUMO: CAMPOS_RESUMO,
}

def _quantos_obrigatorios(especie: Especie) -> int:
    return sum(1 for c in CATALOGOS[especie]
               if c.necessidade is Necessidade.OBRIGATORIO)


# A espécie mais exigente ganha o desempate, e a exigência sai dos próprios
# catálogos — não de uma ordem escrita à mão que envelhece quando um catálogo
# muda. Sem isso, o resumo por produto cai como inventário: ele tem código e
# tem uma coluna com "estoque" no nome, que é tudo o que o inventário exige.
ORDEM_DE_CLASSIFICACAO = tuple(
    sorted(Especie, key=_quantos_obrigatorios, reverse=True)
)

_RE_LIMPAR = re.compile(r"[^a-z0-9 ]+")
_RE_ESPACO = re.compile(r"\s+")


def normalizar(nome: str) -> str:
    """Nome de coluna comparável: sem acento, sem pontuação, minúsculo.

    ``Valor BC ST;Informada`` e ``valor_bc_st_informada`` viram a mesma coisa.
    """
    t = unicodedata.normalize("NFD", (nome or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = _RE_LIMPAR.sub(" ", t)
    return _RE_ESPACO.sub(" ", t).strip()


@dataclass
class Mapeamento:
    """De qual coluna do arquivo sai cada campo do trabalho."""

    especie: Especie = Especie.MOVIMENTO
    posicoes: dict[str, int] = field(default_factory=dict)
    nomes_origem: dict[str, str] = field(default_factory=dict)
    nao_encontrados: list[Campo] = field(default_factory=list)
    colunas_ignoradas: int = 0

    @property
    def faltam_obrigatorios(self) -> list[Campo]:
        return [c for c in self.nao_encontrados
                if c.necessidade is Necessidade.OBRIGATORIO]

    @property
    def faltam_importantes(self) -> list[Campo]:
        return [c for c in self.nao_encontrados
                if c.necessidade is Necessidade.IMPORTANTE]

    @property
    def utilizavel(self) -> bool:
        return not self.faltam_obrigatorios

    @property
    def tem_valores_do_xml(self) -> bool:
        """Quando o ERP já extraiu o XML, o relatório substitui o XML."""
        return "valor_st_xml" in self.posicoes

    def indice(self, chave: str) -> int | None:
        return self.posicoes.get(chave)


def mapear(cabecalho: list[str] | tuple[str, ...],
           especie: Especie = Especie.MOVIMENTO) -> Mapeamento:
    """Casa o cabeçalho com os campos que aquela espécie de arquivo tem.

    São duas passadas, e a ordem entre elas é o que faz o casamento não sair
    torto. **Toda** correspondência exata é resolvida antes de qualquer
    correspondência parcial — se fosse campo a campo, o sinônimo genérico de
    um campo anterior levaria a coluna exata de um posterior: ``Valor``, do
    valor do item, engoliria ``Valor ICMS`` só por vir antes no catálogo.
    """
    normalizados = [normalizar(c) for c in cabecalho]
    catalogo = CATALOGOS[especie]
    m = Mapeamento(especie=especie)
    usadas: set[int] = set()
    faltando = list(catalogo)

    for exato in (True, False):
        restantes: list[Campo] = []
        for campo in faltando:
            alvo = [normalizar(s) for s in (campo.sinonimos or (campo.chave,))]
            achado = _casar(normalizados, alvo, usadas, exato=exato)
            if achado is None:
                restantes.append(campo)
                continue
            m.posicoes[campo.chave] = achado
            m.nomes_origem[campo.chave] = cabecalho[achado]
            usadas.add(achado)
        faltando = restantes

    m.nao_encontrados = faltando
    m.colunas_ignoradas = len(cabecalho) - len(usadas)
    return m


def classificar(cabecalho: list[str] | tuple[str, ...]) -> Mapeamento:
    """Descobre que espécie de arquivo é, pelo que as colunas dizem.

    Não olha nome de arquivo nem prefixo de ERP: olha se as colunas dão conta
    do que cada espécie exige. Assim vale para o próximo ERP também.

    Quando nenhuma espécie fecha, devolve o mapeamento da que chegou mais
    perto — com ``utilizavel`` falso e a lista do que faltou, que é o que a
    tela de importação precisa mostrar.
    """
    tentativas = [mapear(cabecalho, e) for e in ORDEM_DE_CLASSIFICACAO]
    passaram = [m for m in tentativas if m.utilizavel]
    if passaram:
        return max(passaram, key=lambda m: (_quantos_obrigatorios(m.especie),
                                            len(m.posicoes)))
    return max(tentativas,
               key=lambda m: (len(m.posicoes), -len(m.faltam_obrigatorios)))


def _casar(
    normalizados: list[str], alvo: list[str], usadas: set[int], *, exato: bool
) -> int | None:
    for s in alvo:
        for i, n in enumerate(normalizados):
            if i in usadas or not n:
                continue
            if (n == s) if exato else (s in n):
                return i
    return None


# nomes de quando só existia a espécie de movimento
CAMPOS = CAMPOS_MOVIMENTO
POR_CHAVE = {c.chave: c for c in CAMPOS_MOVIMENTO}
OBRIGATORIOS = tuple(c for c in CAMPOS_MOVIMENTO
                     if c.necessidade is Necessidade.OBRIGATORIO)
