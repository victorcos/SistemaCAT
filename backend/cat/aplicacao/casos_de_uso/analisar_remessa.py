"""Analisar a remessa importada e dizer de quem ela é.

É o que permite pré-cadastrar a empresa sem ninguém digitar CNPJ: o registro
0000 de cada arquivo já traz razão social, CNPJ, UF e competência.

A tela mostra **apenas a matriz**, porque é ela que identifica a empresa. As
filiais aparecem como contagem: numa remessa real desta casa foram 101
estabelecimentos, e listar todos ali só atrapalharia a conferência.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from cat.dominio.comum.cnpj import Cnpj
from cat.dominio.sped.cabecalho import (
    MODULOS_EM_ORDEM,
    ROTULO_DO_MODULO,
    ArquivoNaoReconhecido,
    CabecalhoSped,
    TipoSped,
    ler_cabecalho,
)
from cat.infraestrutura.arquivos.remessa import ArquivoDaRemessa
from cat.log import obter_log

log = obter_log(__name__)


@dataclass
class EstabelecimentoDetectado:
    cnpj: Cnpj
    nome: str
    uf: str
    inscricao_estadual: str
    arquivos: int = 0
    competencias: set[str] = field(default_factory=set)

    @property
    def e_matriz(self) -> bool:
        return self.cnpj.e_matriz


@dataclass
class ArquivoRecusado:
    nome: str
    motivo: str


@dataclass
class RemessaAnalisada:
    """O que a tela precisa mostrar depois do envio."""

    raiz_cnpj: str = ""
    razao_social: str = ""
    cnpj_matriz: str | None = None
    uf_matriz: str = ""
    ie_matriz: str = ""
    estabelecimentos: list[EstabelecimentoDetectado] = field(default_factory=list)
    recusados: list[ArquivoRecusado] = field(default_factory=list)
    tipos: dict[str, int] = field(default_factory=dict)
    primeira_competencia: date | None = None
    ultima_competencia: date | None = None
    total_arquivos: int = 0
    lidos: int = 0

    # ---------- perguntas que a tela faz ----------
    @property
    def tem_matriz(self) -> bool:
        return self.cnpj_matriz is not None

    @property
    def filiais(self) -> int:
        return sum(1 for e in self.estabelecimentos if not e.e_matriz)

    @property
    def grupos_distintos(self) -> set[str]:
        return {e.cnpj.raiz for e in self.estabelecimentos}

    @property
    def serve_para_cat(self) -> int:
        return self.tipos.get(TipoSped.EFD_ICMS_IPI.value, 0)

    @property
    def modulos_atendidos(self) -> list[str]:
        """Os módulos de trabalho que têm o que ler nesta remessa."""
        presentes = [TipoSped(t) for t in self.tipos]
        return [
            m for m in MODULOS_EM_ORDEM if any(m in t.modulos for t in presentes)
        ]

    @property
    def observacoes(self) -> list[str]:
        """A que trabalho cada arquivo serve. Informação, não alerta.

        Antes a tela media a remessa só pela CAT 42 — "0 servem à CAT 42" e um
        aviso dizendo que Contribuições e ECD "servem a outras frentes", sem
        dizer quais. Quem ia cadastrar um trabalho de PIS/COFINS lia aquilo
        como recusa do arquivo, que é exatamente o arquivo daquele trabalho.
        """
        if not self.lidos:
            return []
        saida: list[str] = []
        for tipo, qtd in sorted(self.tipos.items()):
            t = TipoSped(tipo)
            verbo = "serve" if qtd == 1 else "servem"
            modulos = " e ".join(ROTULO_DO_MODULO[m] for m in t.modulos)
            saida.append(f"{qtd} {t.rotulo}: {verbo} ao trabalho de {modulos}.")
        if not self.serve_para_cat:
            saida.append(
                "A CAT 42 é de ICMS-ST: para ela, a remessa precisa da EFD ICMS/IPI."
            )
        return saida

    @property
    def avisos(self) -> list[str]:
        """O que o usuário precisa saber antes de confirmar o cadastro."""
        saida: list[str] = []
        if len(self.grupos_distintos) > 1:
            saida.append(
                f"A remessa tem {len(self.grupos_distintos)} empresas diferentes. "
                "Envie uma empresa por vez."
            )
        if not self.tem_matriz and self.estabelecimentos:
            saida.append(
                "Nenhum arquivo é da matriz. O CNPJ da matriz foi deduzido da "
                "raiz e precisa da sua conferência."
            )
        if self.recusados:
            saida.append(
                f"{len(self.recusados)} arquivo(s) não foram reconhecidos e "
                "ficaram de fora."
            )
        return saida


def analisar(arquivos: list[ArquivoDaRemessa]) -> RemessaAnalisada:
    """Lê o cabeçalho de cada arquivo e consolida por estabelecimento."""
    r = RemessaAnalisada(total_arquivos=len(arquivos))
    por_cnpj: dict[str, EstabelecimentoDetectado] = {}
    tipos: dict[str, int] = {}

    for a in arquivos:
        try:
            c = ler_cabecalho(a.primeira_linha)
        except ArquivoNaoReconhecido as erro:
            r.recusados.append(ArquivoRecusado(a.nome, erro.motivo))
            continue

        if c.cnpj is None:
            r.recusados.append(
                ArquivoRecusado(a.nome, "o registro 0000 não traz CNPJ válido")
            )
            continue

        r.lidos += 1
        tipos[c.tipo.value] = tipos.get(c.tipo.value, 0) + 1
        _acumular_periodo(r, c)

        e = por_cnpj.get(c.cnpj.valor)
        if e is None:
            e = por_cnpj[c.cnpj.valor] = EstabelecimentoDetectado(
                cnpj=c.cnpj, nome=c.nome, uf=c.uf,
                inscricao_estadual=c.inscricao_estadual,
            )
        e.arquivos += 1
        e.competencias.add(c.competencia)

    r.tipos = tipos
    r.estabelecimentos = sorted(
        por_cnpj.values(), key=lambda x: (not x.e_matriz, x.cnpj.valor)
    )
    _identificar_empresa(r)

    log.info(
        "remessa analisada",
        extra={"arquivos": r.total_arquivos, "lidos": r.lidos,
               "recusados": len(r.recusados),
               "estabelecimentos": len(r.estabelecimentos),
               "cnpj_matriz": r.cnpj_matriz, "tipos": tipos},
    )
    return r


def _acumular_periodo(r: RemessaAnalisada, c: CabecalhoSped) -> None:
    if r.primeira_competencia is None or c.inicio < r.primeira_competencia:
        r.primeira_competencia = c.inicio
    if r.ultima_competencia is None or c.fim > r.ultima_competencia:
        r.ultima_competencia = c.fim


def _identificar_empresa(r: RemessaAnalisada) -> None:
    """Descobre a matriz e a razão social do grupo."""
    if not r.estabelecimentos:
        return

    matriz = next((e for e in r.estabelecimentos if e.e_matriz), None)
    referencia = matriz or max(r.estabelecimentos, key=lambda e: e.arquivos)

    r.raiz_cnpj = referencia.cnpj.raiz
    r.razao_social = referencia.nome
    r.uf_matriz = referencia.uf

    if matriz:
        r.cnpj_matriz = matriz.cnpj.valor
        r.ie_matriz = matriz.inscricao_estadual
    else:
        # sem arquivo da matriz, deriva o CNPJ pela raiz. O dígito é
        # recalculado, então o número é válido — mas quem confere precisa
        # saber que foi deduzido, e o aviso diz isso.
        r.cnpj_matriz = referencia.cnpj.matriz().valor
        r.ie_matriz = ""
