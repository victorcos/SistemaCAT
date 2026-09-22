"""Quadros da Gestão de PIS/Pasep e COFINS, no layout do MA.

Entrada: um ``ApuracaoEFD`` por competência (já deduplicado). Saída: um
``Relatorio`` com os mesmos quadros, numeração e rótulos da Gestão do MA.

Regras de classificação dos itens A/C/D/F (validadas contra o MA):

- **Saída com incidência**: CST 01, 02, 03, 05 — soma da base (VL_BC).
- **Saída sem incidência**: CST 04, 06, 07, 08, 09 — soma do VL_ITEM.
- **Receita** (quadros 4 e 22): CST 01 a 09. O CST 49 fica de fora.
- **Entrada com crédito**: CST 50-56/60-67 (ou CST 73 com alíquota
  preenchida) com natureza de crédito conhecida. O C170/C191 não tem
  NAT_BC_CRED: a natureza vem do CFOP
  (``tab_cfop_natureza_credito``); CFOP sem natureza (ex.: 1253, energia
  por NF-e) fica fora dos quadros de crédito, como no MA — e vira aviso.
- **Valor do crédito** (quadros 32 e 33): o MA não soma o VL_PIS das
  linhas; recalcula base x alíquota **por grupo** (registro, CST, CFOP,
  natureza, alíquota), arredonda cada grupo ao centavo e depois soma.

Controle de créditos (1100/1500), por competência de origem do crédito
(PER_APU_CRED) comparada à competência do arquivo:

- "Períodos Anteriores" = linhas de competência anterior;
- "do Mês" = linha da própria competência;
- "a Utilizar em Períodos Futuros" = todas as linhas.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable

from cat.infraestrutura.sped.tabelas import tab_cfop, tab_cfop_natureza_credito

from cat.infraestrutura.gestao import rotulos as tab
from cat.infraestrutura.gestao.leiaute import CAMPOS, DOCUMENTOS, POR_TRIBUTO, campos_m210
from cat.infraestrutura.gestao.modelos import QTD_LINHAS, VL_BC, VL_ITEM, ApuracaoEFD, Linha, Quadro, Relatorio
from cat.infraestrutura.gestao.numeros import ValorInvalido, aliquota_10k, centavos, credito_recalculado, formatar_aliquota

CST_SAIDA_COM_INCIDENCIA = frozenset({"01", "02", "03", "05"})
CST_SAIDA_SEM_INCIDENCIA = frozenset({"04", "06", "07", "08", "09"})
CST_RECEITA = CST_SAIDA_COM_INCIDENCIA | CST_SAIDA_SEM_INCIDENCIA
CST_CREDITO = frozenset({"50", "51", "52", "53", "54", "55", "56",
                         "60", "61", "62", "63", "64", "65", "66", "67"})
# CSTs que não geram crédito, mas que o MA conta como entrada com incidência
# quando a linha vem com alíquota preenchida (ver _entrada_credito).
CST_ENTRADA_EXTRA = frozenset({"73"})

# Registros sem NAT_BC_CRED próprio: a natureza sai do CFOP.
_NATUREZA_PELO_CFOP = frozenset({"C170", "C191", "C195"})


# ---------------------------------------------------------------------------
# Acesso aos registros de apuração
# ---------------------------------------------------------------------------

class _Reg:
    """Uma linha de registro de apuração acessada por nome de campo."""
    __slots__ = ("campos", "_idx")

    def __init__(self, campos: list[str], nomes: list[str]):
        self.campos = campos
        self._idx = {n: i for i, n in enumerate(nomes)}

    def txt(self, nome: str) -> str:
        i = self._idx.get(nome)
        return self.campos[i] if i is not None and i < len(self.campos) else ""

    def cent(self, nome: str) -> int:
        return centavos(self.txt(nome))


def _linhas_reg(ap: ApuracaoEFD, reg: str) -> list[_Reg]:
    out = []
    for campos in ap.registros.get(reg, []):
        if reg in ("M210", "M610"):
            nomes = campos_m210(len(campos))
        else:
            nomes = CAMPOS[reg]
        out.append(_Reg(campos, nomes))
    return out


def _per_apu(mmaaaa: str) -> str:
    """PER_APU_CRED "062021" -> "2021-06"."""
    mmaaaa = (mmaaaa or "").strip()
    return f"{mmaaaa[2:6]}-{mmaaaa[0:2]}" if len(mmaaaa) == 6 else mmaaaa


# ---------------------------------------------------------------------------
# Acumulador de linhas de um quadro
# ---------------------------------------------------------------------------

class _Acumulador:
    """rótulo -> período -> centavos, lembrando a chave de ordenação."""

    def __init__(self) -> None:
        self._valores: dict[str, dict[str, int]] = {}
        self._ordem: dict[str, object] = {}

    def somar(self, rotulo: str, periodo: str, valor: int, ordem: object = None) -> None:
        linha = self._valores.setdefault(rotulo, {})
        linha[periodo] = linha.get(periodo, 0) + valor
        if rotulo not in self._ordem:
            self._ordem[rotulo] = rotulo if ordem is None else ordem

    def linhas(self, periodos: list[str]) -> list[Linha]:
        rotulos = sorted(self._valores, key=lambda r: self._ordem[r])
        return [
            Linha(r, {p: self._valores[r].get(p, 0) for p in periodos})
            for r in rotulos
        ]


def _linha_fixa(rotulo: str, periodos: list[str], valor_por_periodo: dict[str, int],
                externo: bool = False) -> Linha:
    if externo:
        return Linha(rotulo, {p: None for p in periodos}, externo=True)
    return Linha(rotulo, {p: valor_por_periodo.get(p, 0) for p in periodos})


# ---------------------------------------------------------------------------
# Itens A/C/D/F
# ---------------------------------------------------------------------------

class _Item:
    """Um grupo agregado de itens de documento, já com a natureza resolvida."""
    __slots__ = ("reg", "op", "cst", "cfop", "nat", "aliq", "vl_item", "vl_bc", "linhas")

    def __init__(self, reg, op, cst, cfop, nat, aliq, soma):
        self.reg, self.op, self.cst, self.cfop, self.nat, self.aliq = reg, op, cst, cfop, nat, aliq
        self.vl_item, self.vl_bc, self.linhas = soma[VL_ITEM], soma[VL_BC], soma[QTD_LINHAS]

    @property
    def rotulo_registro(self) -> str:
        return DOCUMENTOS[self.reg].rotulo

    @property
    def rotulo_cfop(self) -> str:
        if self.cfop:
            desc = tab_cfop.TABELA.get(self.cfop, "")
            return f"{self.cfop} - {desc}" if desc else self.cfop
        return f"{self.rotulo_registro} - Sem CFOP"


def _itens(ap: ApuracaoEFD, tributo: str) -> Iterable[_Item]:
    for (trib, reg, op, cst, cfop, nat, aliq), soma in ap.documentos.items():
        if trib != tributo:
            continue
        if reg in _NATUREZA_PELO_CFOP:
            nat = tab_cfop_natureza_credito.codigo(cfop)
        yield _Item(reg, op, cst, cfop, nat, aliq, soma)


def _saida_com(i: _Item) -> bool:
    return i.op == "S" and i.cst in CST_SAIDA_COM_INCIDENCIA


def _saida_sem(i: _Item) -> bool:
    return i.op == "S" and i.cst in CST_SAIDA_SEM_INCIDENCIA


def _receita(i: _Item) -> bool:
    return i.op == "S" and i.cst in CST_RECEITA


def _entrada_credito(i: _Item) -> bool:
    """Entrada "com incidência", como o MA entende.

    Regra: CST de crédito (50-56 / 60-67) e natureza de crédito conhecida.

    Fora dela, o MA acrescenta o **CST 73 com alíquota preenchida**. É
    escrituração torta do ERP — "Aquisição a Alíquota Zero" não deveria vir
    com alíquota —, mas o MA reproduz e a gestão precisa reproduzir também:
    em abr/2025, no arquivo de referência, isso vale R$ 11,6 milhões de base
    (os R$ 20,3 milhões de CST 73 com alíquota zero continuam de fora).
    Já CST 70 e 98 com base e alíquota o MA ignora, mesmo assim.
    """
    if i.op != "E" or not i.nat:
        return False
    if i.cst in CST_CREDITO:
        return True
    return i.cst in CST_ENTRADA_EXTRA and i.aliq != 0


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

class _Montador:
    def __init__(self, apuracoes: list[ApuracaoEFD], tributo: str):
        if tributo not in POR_TRIBUTO:
            raise ValueError(f"tributo inválido: {tributo!r}")
        self.t = tributo
        self.r = POR_TRIBUTO[tributo]
        self.aps = sorted(apuracoes, key=lambda a: a.periodo)
        self.periodos = [a.periodo for a in self.aps]
        self.avisos: list[str] = []
        self._reg_cache: dict[tuple[str, str], list[_Reg]] = {}
        self._itens_cache: dict[str, list[_Item]] = {}
        self.nome = "PIS/PASEP" if tributo == "PIS" else "COFINS"
        # Nome dos campos no título (VL_BC_PIS / VL_BC_COFINS ...)
        self.sufixo = "PIS" if tributo == "PIS" else "COFINS"

    # -- acesso -------------------------------------------------------------
    def reg(self, ap: ApuracaoEFD, papel_ou_reg: str) -> list[_Reg]:
        reg = self.r.get(papel_ou_reg, papel_ou_reg)
        chave = (ap.periodo, reg)
        if chave not in self._reg_cache:
            self._reg_cache[chave] = _linhas_reg(ap, reg)
        return self._reg_cache[chave]

    def itens(self, ap: ApuracaoEFD) -> list[_Item]:
        if ap.periodo not in self._itens_cache:
            self._itens_cache[ap.periodo] = list(_itens(ap, self.t))
        return self._itens_cache[ap.periodo]

    def soma_reg(self, papel: str, campo: str) -> dict[str, int]:
        return {ap.periodo: sum(x.cent(campo) for x in self.reg(ap, papel)) for ap in self.aps}

    def soma_itens(self, filtro: Callable[[_Item], bool], chave: Callable[[_Item], str],
                   valor: Callable[[_Item], int]) -> list[Linha]:
        acc = _Acumulador()
        for ap in self.aps:
            for i in self.itens(ap):
                if filtro(i):
                    acc.somar(chave(i), ap.periodo, valor(i))
        return acc.linhas(self.periodos)

    def quadro(self, numero: str, titulo: str, linhas: list[Linha]) -> Quadro:
        return Quadro(numero, titulo, linhas)

    # -- controle de créditos 1100/1500 --------------------------------------
    def controle(self, filtro_per: str, campo: str, chave: Callable[[_Reg], tuple[str, object]]) -> list[Linha]:
        """filtro_per: "anteriores", "atual" ou "todos"."""
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "controle_credito"):
                per = _per_apu(x.txt("PER_APU_CRED"))
                if filtro_per == "anteriores" and not per < ap.periodo:
                    continue
                if filtro_per == "atual" and per != ap.periodo:
                    continue
                rotulo, ordem = chave(x)
                acc.somar(rotulo, ap.periodo, x.cent(campo), ordem)
        return acc.linhas(self.periodos)

    def soma_controle(self, filtro_per: str, campos: tuple[str, ...]) -> dict[str, int]:
        out: dict[str, int] = {}
        for ap in self.aps:
            total = 0
            for x in self.reg(ap, "controle_credito"):
                per = _per_apu(x.txt("PER_APU_CRED"))
                if filtro_per == "anteriores" and not per < ap.periodo:
                    continue
                if filtro_per == "atual" and per != ap.periodo:
                    continue
                total += sum(x.cent(c) for c in campos)
            out[ap.periodo] = total
        return out

    def soma_retencao(self, filtro_per: str, campos: tuple[str, ...]) -> dict[str, int]:
        out: dict[str, int] = {}
        for ap in self.aps:
            total = 0
            for x in self.reg(ap, "controle_retencao"):
                per = _per_apu(x.txt("PR_REC_RET"))
                if filtro_per == "anteriores" and not per < ap.periodo:
                    continue
                if filtro_per == "atual" and per != ap.periodo:
                    continue
                total += sum(x.cent(c) for c in campos)
            out[ap.periodo] = total
        return out

    # -----------------------------------------------------------------------
    # Quadros
    # -----------------------------------------------------------------------
    def q1_resumo(self) -> Quadro:
        P = self.periodos
        cc, cr = self.r["controle_credito"], self.r["controle_retencao"]
        detalhe = self.soma_reg
        m210 = self.r["detalhe"]

        def por_periodo(fn: Callable[[ApuracaoEFD], int]) -> dict[str, int]:
            return {ap.periodo: fn(ap) for ap in self.aps}

        receitas = por_periodo(lambda ap: sum(x.cent("VL_REC_BRT") for x in self.reg(ap, m210))
                               + sum(x.cent("VL_TOT_REC") for x in self.reg(ap, "sem_incidencia")))
        # Base ANTES dos ajustes de base de cálculo (VL_BC_CONT), como no MA —
        # a base ajustada (VL_BC_CONT_AJUS) é o "( = )" do quadro 35.
        base_contrib = por_periodo(lambda ap: sum(x.cent("VL_BC_CONT") for x in self.reg(ap, m210)))
        ajustes_contrib = por_periodo(lambda ap: sum(
            x.cent("VL_CONT_PER") - x.cent("VL_CONT_APUR") for x in self.reg(ap, m210)))
        ajustes_cred = por_periodo(lambda ap: sum(
            x.cent("VL_AJUS_ACRES") - x.cent("VL_AJUS_REDUC") - x.cent("VL_CRED_DIF")
            for x in self.reg(ap, "credito")))
        outras_ded = por_periodo(lambda ap: sum(
            x.cent("VL_RET_NC") + x.cent("VL_OUT_DED_NC") + x.cent("VL_RET_CUM") + x.cent("VL_OUT_DED_CUM")
            for x in self.reg(ap, "consolidacao")))
        rateio = por_periodo(self._percentual_rateio)
        folha = {ap.periodo: sum(x.cent("VL_TOT_CONT_FOL") for x in self.reg(ap, "M350")) for ap in self.aps}

        ret_campos_disp = ("SLD_RET", "VL_RET_DED", "VL_RET_PER", "VL_RET_DCOMP")
        nome_recolher = "PIS/PASEP" if self.t == "PIS" else "COFINS"
        L = [
            _linha_fixa(f"  ➥  Saldo de Crédito de Períodos Anteriores [{cc}]", P,
                        self.soma_controle("anteriores", ("SD_CRED_DISP_EFD",))),
            _linha_fixa(f"  ➥  Saldo de Retenção de Períodos Anteriores [{cr}]", P,
                        self.soma_retencao("anteriores", ret_campos_disp)),
            _linha_fixa("                Valor Total das Receitas", P, receitas),
            _linha_fixa("Valor da Base da Contribuição Apurada", P, base_contrib),
            _linha_fixa("        ( - )   Valor da Contribuição", P, detalhe("detalhe", "VL_CONT_APUR")),
            _linha_fixa("        (-/+)   Ajustes da Contribuição", P, ajustes_contrib),
            _linha_fixa("          =     Débito da Contribuição - Não Cumulativo   ➤  Débito", P,
                        detalhe("consolidacao", "VL_TOT_CONT_NC_PER")),
            _linha_fixa("          =     Débito da Contribuição - Cumulativo   ➤  Débito", P,
                        detalhe("consolidacao", "VL_TOT_CONT_CUM_PER")),
            _linha_fixa("Base de Cálculo dos Créditos do Período", P, detalhe("credito", "VL_BC")),
            _linha_fixa("Percentual de Rateio de Créditos [0111]", P, rateio),
            _linha_fixa("        ( + )   Valor dos Créditos", P, detalhe("credito", "VL_CRED")),
            _linha_fixa("        (-/+)  Ajustes dos Créditos", P, ajustes_cred),
            _linha_fixa("           =    Crédito Disponível", P, detalhe("credito", "VL_CRED_DISP")),
            _linha_fixa("( - ) Crédito Descontado Apurado no Periodo   ➤  Crédito", P,
                        detalhe("consolidacao", "VL_TOT_CRED_DESC")),
            _linha_fixa("( - ) Crédito Descontado de Períodos Anteriores   ➤  Crédito", P,
                        detalhe("consolidacao", "VL_TOT_CRED_DESC_ANT")),
            _linha_fixa("( - ) Outras Deduções e Retenções   ➤  Crédito", P, outras_ded),
            _linha_fixa("Saldo de Crédito Apurado no Período", P, detalhe("credito", "SLD_CRED")),
            _linha_fixa(f"           ➥  Saldo de Crédito do Mês ->> [{cc}]", P,
                        self.soma_controle("atual", ("SLD_CRED_FIM",))),
            _linha_fixa(f"           ➥  Saldo de Retenção do Mês ->> [{cr}]", P,
                        self.soma_retencao("atual", ("SLD_RET",))),
            _linha_fixa(f"           $  Valor da Contribuição da {nome_recolher} à Recolher", P,
                        detalhe("consolidacao", "VL_TOT_CONT_REC")),
        ]
        if self.t == "PIS":
            L.append(_linha_fixa("           $  Valor da Contribuição da PIS/PASEP-Folha à Pagar", P, folha))
        L += [
            _linha_fixa("Valor do Débito Apurado na DCTF Web", P, {}, externo=True),
            _linha_fixa("Valor do Débito Apurado MIT", P, {}, externo=True),
            _linha_fixa("e-CAC - Pgtos Consolidados/Darfs", P, {}, externo=True),
            _linha_fixa("        ( - )   Crédito Utilizado PER/DCOMP/Transferido", P,
                        self.soma_controle("todos", ("VL_CRED_PER_EFD", "VL_CRED_DCOMP_EFD", "VL_CRED_TRANS"))),
            _linha_fixa(f"  ➦  Saldo de Crédito a Utilizar em Períodos Futuros [{cc}]", P,
                        self.soma_controle("todos", ("SLD_CRED_FIM",))),
            _linha_fixa(f"  ➦  Saldo de Retenção a Utilizar em Períodos Futuros [{cr}]", P,
                        self.soma_retencao("todos", ("SLD_RET",))),
        ]
        titulo = "1. Resumo PIS/PASEP" if self.t == "PIS" else "1. Resumo COFINS"
        return self.quadro("1", titulo, L)

    def _percentual_rateio(self, ap: ApuracaoEFD) -> int:
        """% de receita tributada no MI sobre a total (0111). Sem 0111 = 100%."""
        r0111 = self.reg(ap, "0111")
        if not r0111:
            return 10_000
        x = r0111[0]
        total = x.cent("REC_BRU_TOTAL")
        if total == 0:
            return 0
        return round(x.cent("REC_BRU_NCUM_TRIB_MI") * 10_000 / total)

    def q2_sem_incidencia_cst(self) -> Quadro:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "sem_incidencia"):
                cst = x.txt("CST")
                acc.somar(tab.rotulo_cst(cst), ap.periodo, x.cent("VL_TOT_REC"), cst)
        r = self.r["sem_incidencia"]
        return self.quadro("2", f"2. Sem Incidência - Abertura CST - [ {r} - VL_TOT_REC ] - "
                                "Valor total da receita bruta no período", acc.linhas(self.periodos))

    def q3_receitas_com_sem(self) -> Quadro:
        P = self.periodos
        com = self.soma_reg("detalhe", "VL_REC_BRT")
        sem = self.soma_reg("sem_incidencia", "VL_TOT_REC")
        r4, r2 = self.r["sem_incidencia"], self.r["detalhe"]
        return self.quadro("3", f"3. Detalhe das Receitas - Com/Sem Incidência - [ {r4} - VL_TOT_REC ] - "
                                f"Valor total da receita bruta no período. [ {r2} - VL_REC_BRT ] - "
                                "Valor da Receita Bruta", [
            _linha_fixa("Receita - Com Incidência da Base de Cálculo da Contribuição", P, com),
            _linha_fixa("Receita - Sem Incidência da Contribuição", P, sem),
        ])

    def q4_receitas_por_registro(self) -> Quadro:
        return self.quadro("4", "4. Detalhe das Receitas - Lançamentos por Registros - "
                                "[ Blocos A, C, D, F - VL_ITEM ] - Valor total do item (mercadorias ou serviços)",
                           self.soma_itens(_receita, lambda i: i.rotulo_registro, lambda i: i.vl_item))

    def q5_tipo_contribuicao(self) -> Quadro:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "detalhe"):
                cod = x.txt("COD_CONT")
                rot = f"{cod} - {tab.rotulo_cod_cont(cod)} - {formatar_aliquota(_aliq(x.txt('ALIQ')))}%"
                acc.somar(rot, ap.periodo, x.cent("VL_BC_CONT"))
        r = self.r["detalhe"]
        return self.quadro("5", f"5. Tipo de Contribuição/Alíquotas - [ {r} - VL_BC_CONT ] - "
                                f"Valor da Base de Cálculo da Contribuição", acc.linhas(self.periodos))

    def q6_saida_com_incidencia(self) -> Quadro:
        return self.quadro("6", "6. Lançamentos por Registros - Saída C/ Incidência - "
                                f"[ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_saida_com, lambda i: i.rotulo_registro, lambda i: i.vl_bc))

    def q7_contribuicao_apurada(self) -> Quadro:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "detalhe"):
                acc.somar(tab.rotulo_cod_cont(x.txt("COD_CONT")), ap.periodo, x.cent("VL_CONT_PER"))
        r = self.r["detalhe"]
        return self.quadro("7", f"7. Código da Contribuição Apurada - [ {r} - VL_CONT_PER ] - "
                                "Valor Total da Contribuição do Período", acc.linhas(self.periodos))

    def _ajustes(self, papel: str, papel_dif: str, campo_dif: str, rotulo_dif: str) -> list[Linha]:
        reg = self.r[papel]
        acc = _Acumulador()
        for ap in self.aps:
            for (r, ind, cod), valor in ap.ajustes.items():
                if r != reg:
                    continue
                sinal = "( - )" if ind == "0" else "( + )"
                acc.somar(f"{sinal} {reg} - {cod} {tab.rotulo_cod_aj(cod)}".rstrip(),
                          ap.periodo, valor, (0 if ind == "0" else 1, cod))
            for x in self.reg(ap, papel_dif):
                v = x.cent(campo_dif)
                if v:
                    acc.somar(rotulo_dif, ap.periodo, v, (2, ""))
        return acc.linhas(self.periodos)

    def q8_ajustes_contribuicao(self) -> Quadro:
        r, d = self.r["ajuste_contrib"], self.r["diferimento"]
        linhas = self._ajustes("ajuste_contrib", "diferimento", "VL_CONT_DIF",
                               f"( - ) {d} - Contribuição Diferida no Período")
        return self.quadro("8", f"8. Ajustes da Contribuição - [ {r} - VL_AJ ] - Valor do ajuste "
                                f"[ {d} - VL_CONT_DIF ] - Valor da Contribuição diferida no período", linhas)

    def q9_natureza_m105(self) -> Quadro:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "credito_nat"):
                nat = x.txt("NAT_BC_CRED")
                acc.somar(tab.rotulo_nat(nat), ap.periodo, x.cent("VL_BC"), nat)
        r, m = self.r["credito_nat"], self.r["credito"]
        return self.quadro("9", f"9. Natureza dos Créditos - [ {r} - VL_BC_{self.sufixo} ] - Valor da Base de "
                                f"Cálculo do Crédito, vinculada ao tipo de Crédito escriturado em {m}",
                           acc.linhas(self.periodos))

    def q10_entradas_por_registro(self) -> Quadro:
        return self.quadro("10", "10. Lançamento por Registros - Entradas C/ Incidência - "
                                 f"[ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_entrada_credito, lambda i: i.rotulo_registro, lambda i: i.vl_bc))

    def _tipo_credito(self, campo: str) -> list[Linha]:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "credito"):
                rot = f"{tab.rotulo_cod_cred(x.txt('COD_CRED'))} - {formatar_aliquota(_aliq(x.txt('ALIQ')))}%"
                acc.somar(rot, ap.periodo, x.cent(campo))
        return acc.linhas(self.periodos)

    def q11_tipo_credito(self) -> Quadro:
        r = self.r["credito"]
        return self.quadro("11", f"11. Tipo de Crédito - [ {r} - VL_BC_{self.sufixo} ] - "
                                 "Valor da Base de Cálculo do Crédito", self._tipo_credito("VL_BC"))

    def q12_ajustes_credito(self) -> Quadro:
        r, d = self.r["ajuste_credito"], self.r["diferimento"]
        linhas = self._ajustes("ajuste_credito", "diferimento", "VL_CRED_DIF",
                               f"( - ) {d} - Crédito Diferido no Período")
        return self.quadro("12", f"12. Ajustes dos Créditos - [ {r} - VL_AJ ] - Valor do ajuste "
                                 f"[ {d} - VL_CRED_DIF ] - Valor do Crédito diferido no período", linhas)

    def q13_outras_deducoes(self) -> Quadro:
        P = self.periodos
        ret = {ap.periodo: sum(x.cent("VL_RET_NC") + x.cent("VL_RET_CUM") for x in self.reg(ap, "consolidacao"))
               for ap in self.aps}
        out = {ap.periodo: sum(x.cent("VL_OUT_DED_NC") + x.cent("VL_OUT_DED_CUM") for x in self.reg(ap, "consolidacao"))
               for ap in self.aps}
        r, cr = self.r["consolidacao"], self.r["controle_retencao"]
        return self.quadro("13", f"13. Outras Deduções e Retenções - [ {r} - VL_RET_NC ] - "
                                 "Valor Retido na Fonte Deduzido no Período", [
            _linha_fixa(f"{cr}/F600 - Valor Retido na Fonte", P, ret),
            _linha_fixa("F700 - Outras Deduções", P, out),
        ])

    def _por_tipo_cred(self, x: _Reg) -> tuple[str, object]:
        cod = x.txt("COD_CRED")
        return tab.rotulo_cod_cred(cod), cod

    def _por_mes(self, x: _Reg) -> tuple[str, object]:
        per = _per_apu(x.txt("PER_APU_CRED"))
        return per, per

    def q14_desc_anteriores_tipo(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("14", f"14. Crédito Descontado de Saldos Anteriores - Por Tipo de Crédito - "
                                 f"[{cc} - VL_CRED_DESC_EFD ] - Valor do Crédito descontado neste período de escrituração",
                           self.controle("anteriores", "VL_CRED_DESC_EFD", self._por_tipo_cred))

    def q15_regime(self) -> Quadro:
        P = self.periodos
        r = self.r["consolidacao"]
        return self.quadro("15", f"15. Detalhe por Regime - [ {r} - VL_CONT_NC_REC ] - Valor da Contribuição "
                                 f"Não Cumulativa a Recolher/Pagar [ {r} - VL_CONT_CUM_REC ] - "
                                 "Valor da Contribuição Cumulativa a Recolher/Pagar", [
            _linha_fixa("Valor da Contribuição Cumulativa a Recolher/Pagar", P,
                        self.soma_reg("consolidacao", "VL_CONT_CUM_REC")),
            _linha_fixa("Valor da Contribuição Não Cumulativa a Recolher/Pagar", P,
                        self.soma_reg("consolidacao", "VL_CONT_NC_REC")),
        ])

    def q16_codigo_receita(self) -> Quadro:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "cod_receita"):
                acc.somar(tab.rotulo_cod_receita(x.txt("COD_REC")), ap.periodo, x.cent("VL_DEBITO"))
        r = self.r["cod_receita"]
        return self.quadro("16", f"16. Detalhe por Código de Receita - [ {r} - VL_DEBITO ] - Valor do Débito "
                                 "correspondente ao código do Campo 03, conforme informação na DCTF",
                           acc.linhas(self.periodos))

    def q17_anteriores_mes_tipo(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("17", f"17. Por Mês e Tipo de Crédito - [{cc} - SD_CRED_DISP_EFD ] - Saldo do Crédito "
                                 "Disponível para Utilização neste Período de Escrituração",
                           self.controle("anteriores", "SD_CRED_DISP_EFD", self._por_mes))

    def q18_credito_disponivel(self) -> Quadro:
        r = self.r["credito"]
        return self.quadro("18", f"18. Tipo de Crédito Disponível - [ {r} - VL_CRED_DISP ] - Valor Total do "
                                 "Crédito Disponível relativo ao Período", self._tipo_credito("VL_CRED_DISP"))

    def q19_anteriores_tipo(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("19", f"19. Saldo de Créditos Anteriores - Por Tipo de Crédito - [{cc} - SD_CRED_DISP_EFD ] - "
                                 "Saldo do Crédito Disponível para Utilização neste Período de Escrituração",
                           self.controle("anteriores", "SD_CRED_DISP_EFD", self._por_tipo_cred))

    def q20_anteriores_mes(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("20", f"20. Saldo de Créditos Anteriores - Por Mês - [{cc} - SD_CRED_DISP_EFD ] - "
                                 "Saldo do Crédito Disponível para Utilização neste Período de Escrituração",
                           self.controle("anteriores", "SD_CRED_DISP_EFD", self._por_mes))

    def q21_saidas_sem_por_registro(self) -> Quadro:
        return self.quadro("21", "21. Lançamentos por Registros - Saídas S/ Incidência - "
                                 "[ Blocos A, C, D, F - VL_ITEM ] - Valor total do item (mercadorias ou serviços)",
                           self.soma_itens(_saida_sem, lambda i: i.rotulo_registro, lambda i: i.vl_item))

    def q22_receita_por_cst(self) -> Quadro:
        return self.quadro("22", "22. Valor Operacional por CST - [ Blocos A, C, D, F - VL_ITEM ] - "
                                 "Valor total do item (mercadorias ou serviços)",
                           self.soma_itens(_receita, lambda i: tab.rotulo_cst(i.cst), lambda i: i.vl_item))

    def q23_entradas_por_registro(self) -> Quadro:
        return self.quadro("23", "23. Natureza dos Crédito por Registros - "
                                 f"[ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_entrada_credito, lambda i: i.rotulo_registro, lambda i: i.vl_bc))

    def q24_saidas_sem_por_cfop(self) -> Quadro:
        return self.quadro("24", "24. Saídas S/ Incidência - Por CFOP - [ Blocos A, C, D, F - VL_ITEM ] - "
                                 "Valor total do item (mercadorias ou serviços)",
                           self.soma_itens(_saida_sem, lambda i: i.rotulo_cfop, lambda i: i.vl_item))

    def q25_saidas_com_por_cfop(self) -> Quadro:
        return self.quadro("25", "25. Saídas C/ Incidência - Por CFOP - "
                                 f"[ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_saida_com, lambda i: i.rotulo_cfop, lambda i: i.vl_bc))

    def q26_entradas_por_cfop(self) -> Quadro:
        return self.quadro("26", "26. Entradas C/ Incidência - Por CFOP - "
                                 f"[ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_entrada_credito, lambda i: i.rotulo_cfop, lambda i: i.vl_bc))

    def q28_saldo_mes_tipo(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("28", f"28. Saldo de Crédito do Mês - Tipo de Crédito - [{cc} - SLD_CRED_FIM ] - "
                                 "Saldo de Crédito do próprio período a utilizar em períodos futuros",
                           self.controle("atual", "SLD_CRED_FIM", self._por_tipo_cred))

    def q29_desc_anteriores_mes(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("29", f"29. Crédito Descontado de Saldos Anteriores - Por Mês - [{cc} - VL_CRED_DESC_EFD ] - "
                                 "Valor do Crédito descontado neste período de escrituração",
                           self.controle("anteriores", "VL_CRED_DESC_EFD", self._por_mes))

    def q30_saidas_com_por_cst(self) -> Quadro:
        return self.quadro("30", f"30. Por CST - Saídas C/ Incidência - [ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - "
                                 f"Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_saida_com, lambda i: tab.rotulo_cst(i.cst), lambda i: i.vl_bc))

    def q31_entradas_por_cst(self) -> Quadro:
        return self.quadro("31", f"31. Por CST - Entradas C/ Incidência - [ Blocos A, C, D, F - VL_BC_{self.sufixo} ] - "
                                 f"Valor da base de cálculo do {self.nome}",
                           self.soma_itens(_entrada_credito, lambda i: tab.rotulo_cst(i.cst), lambda i: i.vl_bc))

    def _credito_recalculado(self, chave: Callable[[_Item], tuple[str, object]]) -> list[Linha]:
        acc = _Acumulador()
        for ap in self.aps:
            for i in self.itens(ap):
                if _entrada_credito(i):
                    rotulo, ordem = chave(i)
                    acc.somar(rotulo, ap.periodo, credito_recalculado(i.vl_bc, i.aliq), ordem)
        return acc.linhas(self.periodos)

    def q32_natureza_valor(self) -> Quadro:
        return self.quadro("32", f"32. Natureza dos Créditos - [ Blocos A, C, D, F - VL_{self.sufixo} ] - "
                                 f"Valor do Crédito do {self.nome}",
                           self._credito_recalculado(lambda i: (tab.rotulo_nat(i.nat), i.nat)))

    def q33_natureza_valor_registro(self) -> Quadro:
        return self.quadro("33", f"33. Natureza dos Créditos por Registro - [ Blocos A, C, D, F - VL_{self.sufixo} ] - "
                                 f"Valor do Crédito do {self.nome}",
                           self._credito_recalculado(lambda i: (i.rotulo_registro, i.rotulo_registro)))

    def q35_ajustes_base(self) -> Quadro:
        P = self.periodos
        r = self.r["detalhe"]
        return self.quadro("35", f"35. Ajustes da Contribuição - Valor referente apuração do registro {r}", [
            _linha_fixa("Valor da Base de Cálculo da Contribuição, Antes de Ajustes", P,
                        self.soma_reg("detalhe", "VL_BC_CONT")),
            _linha_fixa("        ( + )   Valor do Total de Acréscimo", P, self.soma_reg("detalhe", "VL_AJUS_ACRES_BC")),
            _linha_fixa("        ( - )   Valor do Total de Redução", P, self.soma_reg("detalhe", "VL_AJUS_REDUC_BC")),
            _linha_fixa("        ( = )   Valor da Base de Cálculo da Contribuição", P,
                        {ap.periodo: sum((x.cent("VL_BC_CONT_AJUS") if x.txt("VL_BC_CONT_AJUS") != ""
                                          else x.cent("VL_BC_CONT")) for x in self.reg(ap, "detalhe"))
                         for ap in self.aps}),
        ])

    def q36_saldo_transportar_tipo(self) -> Quadro:
        cc = self.r["controle_credito"]
        return self.quadro("36", f"36. Saldo de Crédito por Tipo - [{cc} - SLD_CRED_FIM ] - "
                                 "Saldo de crédito a transportar para o próximo mês",
                           self.controle("todos", "SLD_CRED_FIM", self._por_tipo_cred))

    def q37_credito_utilizado(self) -> Quadro:
        acc = _Acumulador()
        for ap in self.aps:
            for x in self.reg(ap, "credito"):
                cod = x.txt("COD_CRED")
                acc.somar(tab.rotulo_cod_cred(cod), ap.periodo, x.cent("VL_CRED_DESC"), cod)
        r = self.r["credito"]
        return self.quadro("37", f"37. Crédito Utilizado no Mês - Por Código de Crédito - [ {r} - VL_CRED_DESC ] - "
                                 "Valor do Crédito Descontado no Período", acc.linhas(self.periodos))

    def q39_tipo_receita(self) -> Quadro:
        P = self.periodos
        campos = (
            ("Receita Bruta NC - Tributada Mercado Interno", "REC_BRU_NCUM_TRIB_MI"),
            ("Receita Bruta NC - Não Tributada Mercado Interno", "REC_BRU_NCUM_NT_MI"),
            ("Receita Bruta NC - Exportação", "REC_BRU_NCUM_EXP"),
            ("Receita Bruta Cumulativa", "REC_BRU_CUM"),
            ("Receita Bruta Total", "REC_BRU_TOTAL"),
        )
        return self.quadro("39", "39. Por Tipo de Receita - [ 0111 ] - Receita bruta para rateio de créditos", [
            _linha_fixa(rot, P, self.soma_reg("0111", campo)) for rot, campo in campos
        ])

    # -----------------------------------------------------------------------
    def avisos_de_dados(self) -> None:
        sem_nat: dict[str, int] = defaultdict(int)
        for ap in self.aps:
            for i in self.itens(ap):
                if i.op == "E" and i.cst in CST_CREDITO and not i.nat:
                    sem_nat[f"{i.reg} CFOP {i.cfop or '-'}"] += i.vl_bc
            for motivo, n in ap.descartes.items():
                self.avisos.append(f"{ap.periodo}: {n} linha(s) ignorada(s) na leitura — {motivo}.")
        for chave, base in sorted(sem_nat.items()):
            self.avisos.append(
                f"{chave}: entrada com CST de crédito sem natureza de crédito mapeada "
                f"(base R$ {base / 100:,.2f} no período todo) ficou fora dos quadros de crédito, "
                "como no MA. Se o CFOP gera crédito, inclua-o em tab_cfop_natureza_credito."
            )

    def montar(self) -> list[Quadro]:
        metodos = [
            self.q1_resumo, self.q2_sem_incidencia_cst, self.q3_receitas_com_sem,
            self.q4_receitas_por_registro, self.q5_tipo_contribuicao, self.q6_saida_com_incidencia,
            self.q7_contribuicao_apurada, self.q8_ajustes_contribuicao, self.q9_natureza_m105,
            self.q10_entradas_por_registro, self.q11_tipo_credito, self.q12_ajustes_credito,
            self.q13_outras_deducoes, self.q14_desc_anteriores_tipo, self.q15_regime,
            self.q16_codigo_receita, self.q17_anteriores_mes_tipo, self.q18_credito_disponivel,
            self.q19_anteriores_tipo, self.q20_anteriores_mes, self.q21_saidas_sem_por_registro,
            self.q22_receita_por_cst, self.q23_entradas_por_registro, self.q24_saidas_sem_por_cfop,
            self.q25_saidas_com_por_cfop, self.q26_entradas_por_cfop, self.q28_saldo_mes_tipo,
            self.q29_desc_anteriores_mes, self.q30_saidas_com_por_cst, self.q31_entradas_por_cst,
            self.q32_natureza_valor, self.q33_natureza_valor_registro, self.q35_ajustes_base,
            self.q36_saldo_transportar_tipo, self.q37_credito_utilizado, self.q39_tipo_receita,
        ]
        return [m() for m in metodos]


def _aliq(txt: str) -> int:
    try:
        return aliquota_10k(txt)
    except ValorInvalido:
        return 0


def montar_relatorio_piscofins(apuracoes: list[ApuracaoEFD], tributo: str) -> Relatorio:
    """Monta o relatório de gestão de PIS ou COFINS a partir das apurações mensais."""
    if not apuracoes:
        raise ValueError("nenhuma apuração EFD-Contribuições informada")
    m = _Montador(apuracoes, tributo)
    quadros = m.montar()
    m.avisos_de_dados()
    base = m.aps[-1]
    return Relatorio(
        tributo=tributo, cnpj=base.cnpj, razao_social=base.razao_social,
        periodos=m.periodos, quadros=quadros, avisos=m.avisos,
        unidade_percentual=frozenset({"Percentual de Rateio de Créditos [0111]"}),
    )
