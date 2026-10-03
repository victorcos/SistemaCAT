"""A alíquota **percentual** do combustível, por UF e por produto — a era do ST.

O crédito de combustível tem duas eras, e elas não se calculam da mesma forma:

* **até abril/2023** (maio, na gasolina) o ICMS do combustível era percentual e
  estadual, cobrado por substituição tributária. O crédito é `base × alíquota`,
  e esta tabela é a alíquota;
* **de maio/2023 em diante** é `litros × ad rem × FCV`, sem percentual nenhum —
  ver `tab_ad_rem` e `tab_fcv`.

Um pedido de cinco anos atravessa a virada. Por isso esta tabela **acaba** onde a
outra começa: pedir percentual de uma competência do monofásico não é dado que
falta, é pergunta errada, e `interna()` recusa dizendo isso.

## Por que não serve a alíquota geral do estado

Porque combustível quase nunca segue a geral. No Espírito Santo, três produtos e
três alíquotas diferentes, nenhuma delas a interna de 17%: diesel a 12%, gasolina
a 27%, álcool a 27%. Usar a geral na gasolina credita **37% menos** do que a lei
manda — e errar para baixo é pior, porque o número menor não desperta ninguém.

É por isso que esta tabela existe separada de `tab_aliquota_icms`: lá o eixo é a
UF, aqui são **UF e produto**, e o produto manda mais.

## O que está conferido no Espírito Santo, e o que não está

Lido no **texto consolidado da Lei 7.000/2001** (175 páginas, com o histórico de
redações de cada inciso). Diesel e gasolina estão nomeados na lei e entraram em
`INTERNA`. O **GLP não está nomeado em lugar nenhum do art. 20** — e por isso
ficou em `A_CONFERIR`, não em `INTERNA`. Ver `A_CONFERIR` para o que falta ler.

### A armadilha dos 30% na gasolina, e por que ela está registrada

Uma busca na internet devolve **30%** para a gasolina do Espírito Santo. O número
existe de fato na lei — a Lei 8.098, de 27/09/2005, incluiu o inciso VI com
exatamente 30%. Ele **nunca produziu efeitos**: a Lei 8.237, de 28/12/2005, deu
nova redação ao mesmo inciso antes de o primeiro entrar em vigor, e o texto
consolidado marca a versão anterior como *"sem efeitos"*.

Quem lê um resumo, e não o consolidado com o histórico, pega os 30%. Sobre uma
base de R$ 10 milhões de gasolina isso são R$ 300 mil de crédito a mais, pedidos
com fundamento num inciso que nunca valeu. Por isso o valor está em `REFUTADO`:
para que a próxima pessoa que o encontrar reconheça o que encontrou.

## Por que o livro do cliente não confere esta tabela

Em `tab_aliquota_icms` a regra da casa é *ato legal mais medição na escrituração
do cliente*. **Aqui a segunda metade não existe, e a razão é a própria tese:** na
era do ST o consumidor recebe a nota com CST 60, que não destaca imposto nenhum.
Foi essa ausência que criou a tese de recuperação; ela também impede que o livro
dele sirva de prova.

A prova independente que **vai** existir vem do XML, não do SPED: `vICMSSTRet`
dividido por `vBCSTRet`, que o leitor em `cat/dominio/notafiscal/xml.py` já lê
(`valor_st_retido` e `bc_st_retido`). Quando houver XML de compra de combustível
de um cliente do ES na era do ST, essa divisão confirma ou derruba os 12% e os
27% — e aí a nota de procedência destas linhas muda.

Até lá o que dá peso ao Espírito Santo é a lei mais uma concordância
independente: um papel de trabalho de projeto encerrado, de outro escritório,
apurou gasolina a 27% e diesel a 12%. Ele **errou** o FCV (usou o de São Paulo
num cliente do ES, ver `tab_fcv`), e por isso não serve de gabarito sozinho — mas
acertar a alíquota pelo mesmo número que a lei, tendo errado outra coisa, é
concordância e não cópia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cat.infraestrutura.sped.tabelas.tab_ad_rem import DIESEL, GASOLINA, GLP

# Os produtos que **não** entraram no monofásico e por isso seguem percentuais
# até hoje. O art. 3º-B da Lei 7.000/2001 lista o etanol **anidro** (EAC) e só
# ele; o hidratado ficou fora, e continua no regime plurifásico.
ETANOL_HIDRATADO = "etanol_hidratado"
LUBRIFICANTE = "lubrificante"

# A competência em que o monofásico começou, por produto — isto é, o **primeiro
# mês sem percentual**. Datas do art. 3º-B da Lei 7.000/2001 (incisos III e IV
# incluídos pela Lei 11.843-R, de 13/06/2023), que reproduz em lei estadual o que
# os Convênios ICMS 199/2022 e 15/2023 fixaram. Produto fora deste mapa nunca
# entrou no monofásico.
#
# `GASOLINA` cobre a gasolina C e o etanol anidro, como em `tab_ad_rem`: o art.
# 3º-B os incluiu na mesma data e o convênio lhes dá a mesma ad rem.
MONOFASICO_DESDE: dict[str, str] = {
    DIESEL: "2023-05",
    GLP: "2023-05",
    GASOLINA: "2023-06",
}


@dataclass(frozen=True)
class Vigencia:
    """Uma alíquota interna de combustível, desde quando vale e de onde saiu."""

    aliquota: Decimal
    desde: str        # "aaaa-mm"; vale desta competência em diante
    fundamento: str   # o ato legal, com inciso e alínea


# Por UF e por produto, **só o que foi lido no texto da lei do estado**. Em
# ordem decrescente de vigência, que é a ordem em que se procura.
INTERNA: dict[str, dict[str, tuple[Vigencia, ...]]] = {
    "ES": {
        DIESEL: (
            Vigencia(Decimal(12), "2006-01",
                     "Lei 7.000/2001, art. 20, II, 'k', incluída pela Lei "
                     "8.098, de 27/09/2005, efeitos de 1º/01/2006; nova redação "
                     "pela Lei 9.937, de 22/11/2012, que acrescentou o biodiesel "
                     "B-100. A revogação pela Lei 11.768/2022 **não produziu "
                     "efeitos**, por força do art. 179-I, § único, que invoca o "
                     "art. 32-A, § 1º, III, da LC 87/96 — logo os 12% valeram "
                     "sem interrupção, e o próprio art. 179-I os reafirma de "
                     "1º/04/2023 até o monofásico"),
        ),
        GASOLINA: (
            Vigencia(Decimal(27), "2006-01",
                     "Lei 7.000/2001, art. 20, VI, 'a' ('gasolina, classificada "
                     "no código 2710.00.03'), na redação da Lei 8.237, de "
                     "28/12/2005, efeitos de 1º/01/2006; nunca revogado. Não "
                     "confundir com os 30% da Lei 8.098/2005, que não produziram "
                     "efeitos — ver REFUTADO"),
        ),
        ETANOL_HIDRATADO: (
            Vigencia(Decimal(27), "2006-04",
                     "Lei 7.000/2001, art. 20, VI, 'b' ('álcool de todos os "
                     "tipos, inclusive o álcool carburante', NCM 2207.10.0100 e "
                     "2207.10.9902), efeitos de 29/03/2006 — adotado aqui de "
                     "04/2006 porque março é mês partido. Segue percentual até "
                     "hoje: o art. 3º-B só pôs o anidro no monofásico"),
        ),
    },
}

# O que se suspeita e ainda não se leu. `interna()` **recusa** estes pares e põe
# o palpite na mensagem, nunca na conta — a mesma regra de `tab_ad_rem`.
#
# O GLP do Espírito Santo é o caso que importa, e o que falta ler é específico:
# ele não aparece nomeado em nenhum inciso do art. 20, o que à primeira vista o
# joga na interna geral de 17% (inciso I, 'a'). Só que o inciso II, 'm' (Lei
# 10.773/2017, efeitos de 12/07/2017) põe a 12% "as mercadorias listadas nos
# Anexos VII e VIII do Regulamento" — e esses anexos estão no Decreto 1.090-R,
# não na lei. **Se o GLP estiver lá, ele é 12% e não 17%**, e são cinco pontos de
# diferença sobre toda a base de GLP.
#
# É exatamente a divergência que se observou nas fontes secundárias: um papel de
# trabalho apurou 17%, uma busca na internet devolveu 12%. Nenhum dos dois leu o
# anexo, e enquanto ninguém ler, o motor não calcula GLP no ES.
A_CONFERIR: dict[tuple[str, str], tuple[Decimal, str]] = {
    ("ES", GLP): (
        Decimal(17),
        "interna geral do art. 20, I, 'a', por resíduo: o GLP não é nomeado em "
        "nenhum inciso do art. 20. Antes de usar, abrir os Anexos VII e VIII do "
        "RICMS/ES (Decreto 1.090-R) e conferir se o GLP está listado — se "
        "estiver, o art. 20, II, 'm' o põe a 12%"),
    ("ES", LUBRIFICANTE): (
        Decimal(17),
        "mesma situação do GLP, e com um agravante: lubrificante nunca entrou no "
        "monofásico, então a alíquota vale até hoje. Os 30% e os 56,63% que "
        "aparecem perto da palavra 'lubrificante' no texto da lei são **MVA** do "
        "Convênio ICMS 110/2007, não alíquota"),
}

# Valores que se encontram por aí e que **já se provou errados**. Não são
# suspeita: são engano identificado, com o motivo escrito. Ficam registrados para
# que quem topar com eles reconheça o que achou em vez de reabrir a discussão.
REFUTADO: dict[tuple[str, str], tuple[Decimal, str]] = {
    ("ES", GASOLINA): (
        Decimal(30),
        "a Lei 8.098, de 27/09/2005, de fato incluiu o inciso VI do art. 20 com "
        "30%, mas ele **nunca produziu efeitos**: a Lei 8.237, de 28/12/2005, "
        "deu nova redação ao mesmo inciso antes da entrada em vigor, fixando "
        "27%. O texto consolidado marca a versão de 2005 como 'sem efeitos'. "
        "Quem lê resumo em vez do consolidado pega os 30% e pede 11% a mais"),
}


class AliquotaDeCombustivelDesconhecida(LookupError):
    """Pediram a alíquota de um combustível, UF ou mês que não se conferiu."""


class ForaDoRegimePercentual(LookupError):
    """Pediram percentual de uma competência do monofásico — ali não há um.

    Erro separado de propósito: não é dado que falta, é a pergunta errada. Quem
    trata os dois juntos acaba completando com a interna do estado uma conta que
    devia ser `litros × ad rem × FCV`.
    """


def interna(uf: str, produto: str, competencia: str) -> Decimal:
    """A alíquota percentual daquele combustível, naquela UF, naquele mês.

    `competencia` em "aaaa-mm". Devolve pontos percentuais (12 para 12%), como
    `tab_aliquota_icms.interna`.

    Levanta `ForaDoRegimePercentual` quando a competência já é do monofásico, e
    `AliquotaDeCombustivelDesconhecida` quando a UF, o produto ou o mês não
    estão conferidos — **inclusive havendo palpite em `A_CONFERIR`**, caso em
    que a mensagem diz qual é e o que falta ler para usá-lo.
    """
    uf = (uf or "").strip().upper()

    monofasico = MONOFASICO_DESDE.get(produto)
    if monofasico is not None and competencia >= monofasico:
        raise ForaDoRegimePercentual(
            f"{produto} não tem alíquota percentual em {competencia}: o regime "
            f"monofásico começou em {monofasico} (art. 3º-B da Lei 7.000/2001 e "
            f"Convênios ICMS 199/2022 e 15/2023). O imposto ali é ad rem — use "
            f"`tab_ad_rem.da_competencia` e `tab_fcv.fator`.")

    por_produto = INTERNA.get(uf, {})
    vigencias = por_produto.get(produto)
    if not vigencias:
        raise AliquotaDeCombustivelDesconhecida(
            f"A alíquota de {produto} em {uf or '(sem UF)'} não está conferida."
            + _pista(uf, produto)
            + " Ler o ato legal do estado e acrescentar a linha em "
              "`tab_aliquota_combustivel.INTERNA`. Relatório de escritório "
              "anterior não confere: ver o topo de `tab_aliquota_icms`.")

    for vigencia in vigencias:
        if competencia >= vigencia.desde:
            return vigencia.aliquota

    mais_antiga = vigencias[-1].desde
    raise AliquotaDeCombustivelDesconhecida(
        f"A alíquota de {produto} em {uf} só é conhecida de {mais_antiga} em "
        f"diante, e pediram {competencia}. Acrescentar a vigência anterior em "
        f"`tab_aliquota_combustivel.INTERNA`.")


def _pista(uf: str, produto: str) -> str:
    """O que se sabe sobre um par não conferido: o palpite, ou o engano conhecido.

    Nunca volta para o cálculo — só para a mensagem de quem vai conferir.
    """
    if (suspeita := A_CONFERIR.get((uf, produto))) is not None:
        return (f" Suspeita-se de {suspeita[0]}% ({suspeita[1]}), e **não** se "
                f"deve usar sem ler.")
    if (engano := REFUTADO.get((uf, produto))) is not None:
        return (f" Cuidado: circula o valor de {engano[0]}%, que já se provou "
                f"errado ({engano[1]}).")
    return ""


def no_monofasico(produto: str, competencia: str) -> bool:
    """Se aquele produto já é ad rem naquela competência.

    Serve a quem precisa escolher o caminho da conta antes de pedir qualquer
    número — o motor de apuração decide por aqui qual das duas eras aplicar.
    """
    desde = MONOFASICO_DESDE.get(produto)
    return desde is not None and competencia >= desde
