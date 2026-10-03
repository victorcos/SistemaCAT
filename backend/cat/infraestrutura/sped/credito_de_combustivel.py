"""Quanto vale o crédito de uma linha de compra de combustível.

Última peça da conta: o leitor entrega a compra, o classificador diz o que é, e
este módulo diz **quanto**. Ele não lê arquivo e não classifica nada — recebe
uma `LinhaDeCompra` e uma `Classificacao` e devolve um `Credito`.

> O humano decide o que o produto é; **a tabela decide quanto ele vale.**

Por isso aqui não há inferência nenhuma. Todo número sai de `tab_ad_rem`,
`tab_fcv` ou `tab_aliquota_combustivel`, e o que elas não cobrem **não vira
zero: vira recusa com o motivo**, e a linha aparece no relatório fora do total —
mesmo tratamento da competência prescrita.

## As duas eras, e as duas contas

```
monofásico (CST 61, de 05/2023)   quantidade × ad rem × FCV
ST         (CST 60, antes)        base × alíquota interna
```

A primeira é exata: os três fatores são tabela. A segunda **é estimativa**, e o
módulo a marca como tal — ver abaixo.

## Por que a era do ST é estimativa, e não cálculo

Porque **a base não está no arquivo**. Medido nos 40 arquivos da empresa G:
5.234 linhas de C170 com CST 60 ou 61 e **zero** com base ou valor de ST; 3.867
linhas de C190 das mesmas CST, todas com `VL_OPR` preenchido e **nenhuma** com
`VL_BC_ICMS_ST` ou `VL_ICMS_ST`.

Isso não é defeito do arquivo — é a premissa da tese. O imposto foi retido na
origem e o destinatário não o vê; foi essa ausência que criou o direito ao
crédito e é ela que impede de medi-lo aqui.

Então a estimativa usa o **valor do item** como base, que é o que o papel de
trabalho de terceiro fazia. **A base verdadeira do ST era o PMPF**, não o valor
pago, e a diferença entre os dois não se sabe sem a tabela de PMPF — nem o
sinal. Por isso `estimativa=True` vai na linha, e não numa nota de rodapé: quem
somar um total com estimativa dentro tem de saber disso pela própria linha.

A conferência prometida é o XML: `vICMSSTRet ÷ vBCSTRet`, campos que
`dominio/notafiscal/xml.py` já lê. É a fase 2, e é o que o usuário decidiu em
02/10/2026 — *estimar pela EFD, corrigir pelo XML depois de aprovado*.

## A cobertura da regra, e por que ela nunca chega a "alta" hoje

Regra da §8 do `DOMINIO_COMBUSTIVEL.md`: a cobertura é **fato sobre tabela**, não
probabilidade, e tem três níveis — vigência conferida **e** a UF internalizou o
crédito (alta); vigência conferida sem a norma da UF localizada (média); sem
vigência cobrindo a competência (recusa).

**Falta a tabela de internalização.** O Convênio ICMS 26/2023 dá o direito ao
crédito, mas quem o concede é o estado, por norma própria — e não se levantou
quais UF a editaram. Enquanto essa tabela não existir, o teto é `MEDIA`, e o
`porque` diz exatamente isso. Chamar de alta sem a norma seria inventar certeza.

## O que este módulo não faz

**Não corrige por SELIC.** Crédito escritural de ICMS não sofre correção
monetária — Súmula 411 do STJ, e `DOMINIO_COMBUSTIVEL.md`, §9. É o vício que o
módulo de PIS/COFINS tem e este não: reaproveitar o `Total` de lá traria a
SELIC junto.

**Não aplica prescrição.** Cinco anos da **emissão** (LC 87/96, art. 23), e a
regra do ICMS não é a do PIS/COFINS. Fica na rodada, e hoje nem lá — ver
`analitico/combustivel.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from cat.infraestrutura.sped.classificador_de_combustivel import Classificacao
from cat.infraestrutura.sped.combustivel import LinhaDeCompra
from cat.infraestrutura.sped.tabelas import (
    tab_ad_rem,
    tab_aliquota_combustivel,
    tab_fcv,
)

MONOFASICO = "monofasico"
ST = "st"

# a cobertura da regra. `ALTA` existe no vocabulário e **não é alcançável hoje**
# — falta a tabela de UF que internalizaram o Conv. 26/2023. Ver o topo.
ALTA = "alta"
MEDIA = "media"
RECUSADO = "recusado"

CENTAVO = Decimal("0.01")
CEM = Decimal(100)

# Por que a linha não entrou no total, em código curto.
#
# **A frase não serve de chave.** Ela traz valores dentro — a competência, a
# alíquota, a suspeita de ad rem — e agrupar por ela daria um grupo por linha.
# O código agrupa; a frase explica. A tela mostra "ad rem não conferida (9
# linhas)" e abre uma delas para ler o porquê inteiro.
SEM_CLASSIFICACAO = "sem_classificacao"
FORA_DA_TESE = "fora_da_tese"
SEM_COMPETENCIA = "sem_competencia"
SEM_QUANTIDADE = "sem_quantidade"
SEM_FATOR = "sem_fator"
SEM_VALOR_DO_ITEM = "sem_valor_do_item"
AD_REM_NAO_CONFERIDA = "ad_rem_nao_conferida"
FCV_DESCONHECIDO = "fcv_desconhecido"
ALIQUOTA_NAO_CONFERIDA = "aliquota_nao_conferida"
MES_PARTIDO = "mes_partido"
REGIME_INCOERENTE = "regime_incoerente"
CST_NAO_E_DO_REGIME = "cst_nao_e_do_regime"
ICMS_JA_DESTACADO = "icms_ja_destacado"


@dataclass(frozen=True)
class Credito:
    """Quanto a linha vale, com todos os fatores à vista.

    Os fatores ficam expostos de propósito: o relatório mostra a conta, não só o
    resultado, porque o cliente pergunta "por que esse número?" e a resposta tem
    de caber na linha.

    `valor is None` significa **recusado** — e aí `porque` diz o que falta. Nunca
    zero: zero soma, recusa aparece.
    """

    produto: str = ""
    regime: str = ""
    quantidade: Decimal | None = None     # já na unidade tributada
    fator: Decimal | None = None
    ad_rem: Decimal | None = None
    fcv: Decimal | None = None
    base: Decimal | None = None
    aliquota: Decimal | None = None
    valor: Decimal | None = None
    cobertura: str = RECUSADO
    # o código curto de por que não entrou; vazio quando entrou
    motivo: str = ""
    porque: str = ""
    estimativa: bool = False

    @property
    def entra_no_total(self) -> bool:
        """Só o que tem valor e não foi recusado.

        A linha recusada **aparece** no relatório; ela só não soma. É o mesmo
        tratamento da competência prescrita, e a razão é a mesma: linha que
        desaparece faz alguém procurar por que o total não fecha.
        """
        return self.valor is not None and self.cobertura != RECUSADO


def _recusa(motivo: str, porque: str, produto: str = "",
            regime: str = "") -> Credito:
    return Credito(produto=produto, regime=regime, cobertura=RECUSADO,
                   motivo=motivo, porque=porque)


def apurar(linha: LinhaDeCompra, classificacao: Classificacao) -> Credito:
    """O crédito daquela linha, ou a recusa com o motivo. **Nunca levanta.**

    As exceções das tabelas são capturadas e **viram texto na linha**: é a única
    forma de o motivo chegar ao relatório. Deixá-las subir derrubaria a rodada
    inteira por causa de uma competência sem vigência cadastrada.
    """
    produto = classificacao.produto
    if not produto:
        return _recusa(SEM_CLASSIFICACAO,
                       "a linha não foi classificada: " + classificacao.porque)
    if not classificacao.entra_na_tese:
        return _recusa(FORA_DA_TESE,
                       f"{produto} não entra nesta tese: {classificacao.porque}",
                       produto=produto)

    competencia = linha.competencia
    if not competencia:
        return _recusa(SEM_COMPETENCIA,
                       "o arquivo não trouxe competência no registro 0000",
                       produto=produto)

    monofasico = tab_aliquota_combustivel.no_monofasico(produto, competencia)
    if (recusa := _o_cst_nao_casa(linha, produto, monofasico)) is not None:
        return recusa

    if monofasico:
        return _no_monofasico(linha, classificacao, produto, competencia)
    return _na_era_do_st(linha, produto, competencia)


def _o_cst_nao_casa(linha: LinhaDeCompra, produto: str,
                    monofasico: bool) -> Credito | None:
    """A recusa quando a compra não pode gerar este crédito. `None` quando pode.

    **O teste que importa é o destaque, não o rótulo.** O produto diz *o que é*
    e o regime vem da lei; o CST diz como o fornecedor escriturou, e ele erra.
    Uma compra de diesel com **ICMS destacado** já deu crédito pelo caminho
    normal — somar a ad rem em cima creditaria o mesmo litro duas vezes. Esse é
    o risco real, e é ele que esta porta fecha.

    ### A medição que corrigiu a primeira versão desta função

    Ela recusava tudo que não fosse CST 61 na era do monofásico, e isso jogava
    fora **1.026 linhas, R$ 3 milhões**. Olhando o que eram: diesel e gasolina
    comprados em posto — `Rodoposto Bandeirantes`, `Auto Posto Viaduto` —, 914
    de diesel e 112 de gasolina, concentradas em 2025, **todas sem uma gota de
    ICMS destacado**. Compra de combustível de verdade, escriturada pelo
    fornecedor com 60 em vez de 61.

    O regime é da lei. Em 2025 o diesel é monofásico, tenha o posto escrito 60
    ou 61, e o imposto foi cobrado lá atrás nos dois casos. O que separa essas
    linhas das do CST 90 é o destaque: **CST 60 tem zero linhas com ICMS
    destacado; CST 90 tem 792 de 1.080**.

    Então a ordem é: destaque primeiro, rótulo depois — e o rótulo só recusa o
    que não é nem monofásico nem retido, que é o caso que pede olho humano.

    ### Quanto esta porta vale, medido

    Rodada a cadeia nas 25 competências da empresa G com e sem ela: o devido cai
    de R$ 1.567.603,81 para **R$ 1.566.349,35**. São **R$ 1.254,46** de crédito
    que seriam pedidos duas vezes.

    Pouco neste cliente, e vale dizer por quê: ele compra quase tudo em posto,
    sem destaque. Num cliente que compre de distribuidor com ICMS destacado a
    porta pesa muito mais — e o número a registrar é o medido, não a proporção
    que se estima olhando a contagem de linhas.
    """
    t = linha.tributacao
    regime = MONOFASICO if monofasico else ST

    if (linha.valor_do_icms or Decimal(0)) > 0:
        return _recusa(
            ICMS_JA_DESTACADO,
            f"a compra veio com ICMS destacado de R$ {linha.valor_do_icms} "
            f"(CST {t.bruto or '(vazio)'}): o documento já deu esse crédito "
            f"pelo caminho normal, e somar o do combustível em cima creditaria "
            f"o mesmo litro duas vezes",
            produto, regime)

    # sem destaque, o imposto foi cobrado antes — por monofásico ou por
    # substituição. Nos dois casos o crédito desta tese é o que resta
    if t.cst == "61" or t.e_substituicao:
        return None

    return _recusa(
        CST_NAO_E_DO_REGIME,
        f"a compra veio com CST {t.bruto or '(vazio)'} e sem ICMS destacado: "
        f"não é monofásico (61) nem imposto retido antes (60 ou CSOSN 500), "
        f"então não se sabe por qual via o {produto} foi tributado em "
        f"{linha.competencia}. A linha precisa de olho humano",
        produto, regime)


def _no_monofasico(linha: LinhaDeCompra, classificacao: Classificacao,
                   produto: str, competencia: str) -> Credito:
    """`quantidade × ad rem × FCV` — os três de tabela, nenhum de palpite."""
    if linha.quantidade is None:
        return _recusa(SEM_QUANTIDADE,
                       "o C170 não trouxe quantidade, e sem ela não há litro "
                       "para multiplicar", produto, MONOFASICO)
    if classificacao.fator is None:
        return _recusa(
            SEM_FATOR, f"falta o fator de conversão: {classificacao.porque}",
            produto, MONOFASICO)

    try:
        ad_rem = tab_ad_rem.da_competencia(produto, competencia)
    except tab_ad_rem.AdRemDesconhecida as erro:
        return _recusa(AD_REM_NAO_CONFERIDA, str(erro), produto, MONOFASICO)

    try:
        fcv = tab_fcv.fator(linha.uf, produto, competencia)
    except tab_fcv.FcvDesconhecido as erro:
        return _recusa(FCV_DESCONHECIDO, str(erro), produto, MONOFASICO)

    quantidade = linha.quantidade * classificacao.fator
    valor = (quantidade * ad_rem * fcv).quantize(CENTAVO, ROUND_HALF_UP)
    return Credito(
        produto=produto, regime=MONOFASICO,
        quantidade=quantidade, fator=classificacao.fator,
        ad_rem=ad_rem, fcv=fcv, valor=valor,
        cobertura=MEDIA,
        porque=(f"{quantidade} {classificacao.unidade_tributada} × ad rem "
                f"{ad_rem} × FCV {fcv} de {linha.uf}; a norma da UF que "
                f"internaliza o Conv. 26/2023 não foi levantada, então a "
                f"cobertura é média"),
    )


def _na_era_do_st(linha: LinhaDeCompra, produto: str,
                  competencia: str) -> Credito:
    """`base × alíquota interna` — **e a base é estimativa**, ver o topo."""
    try:
        aliquota = tab_aliquota_combustivel.interna(linha.uf, produto, competencia)
    except tab_aliquota_combustivel.MesPartido as erro:
        return _recusa(MES_PARTIDO, str(erro), produto, ST)
    except tab_aliquota_combustivel.ForaDoRegimePercentual as erro:
        # não deveria chegar aqui: `no_monofasico` já desviou. Se chegou, a
        # tabela e o desvio discordam, e isso é defeito a aparecer
        return _recusa(REGIME_INCOERENTE,
                       f"incoerência entre o regime e a tabela — {erro}",
                       produto, ST)
    except tab_aliquota_combustivel.AliquotaDeCombustivelDesconhecida as erro:
        return _recusa(ALIQUOTA_NAO_CONFERIDA, str(erro), produto, ST)

    if linha.valor_do_item is None:
        return _recusa(SEM_VALOR_DO_ITEM,
                       "o C170 não trouxe valor do item, que é a base da "
                       "estimativa", produto, ST)

    base = linha.valor_do_item
    valor = (base * aliquota / CEM).quantize(CENTAVO, ROUND_HALF_UP)
    return Credito(
        produto=produto, regime=ST,
        base=base, aliquota=aliquota, valor=valor,
        cobertura=MEDIA, estimativa=True,
        porque=(f"ESTIMATIVA: o arquivo não traz base de ST (medido: zero em "
                f"5.234 linhas de CST 60/61), então a base é o valor do item, "
                f"R$ {base}, × {aliquota}% de {linha.uf}. A base verdadeira era "
                f"o PMPF, e a diferença não se sabe sem a tabela dele — conferir "
                f"pelo XML (vICMSSTRet ÷ vBCSTRet)"),
    )
