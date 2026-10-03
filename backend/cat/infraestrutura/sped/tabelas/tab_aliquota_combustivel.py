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

## O que está conferido, e onde

**Espírito Santo** — texto consolidado da Lei 7.000/2001 (175 páginas, com o
histórico de redações de cada inciso). Diesel 12% (art. 20, II, "k"), gasolina
27% e álcool de todos os tipos 27% (art. 20, VI).

**São Paulo** — RICMS, Decreto 45.490/2000, arts. 52 a 56-C. É onde está **todo o
volume medido**: os quatro clientes com CST 61 são de SP. Diesel 12%/13,3% (art.
54, VI) e gasolina 25% (art. 55, XXVI).

O **GLP não entrou em nenhuma das duas** — não é nomeado nos artigos de alíquota
de qualquer dos dois estados. Ficou em `A_CONFERIR`, com o que falta ler escrito.

### São Paulo tem dois meses partidos, e eles são a razão do campo `dia`

O complemento de alíquota do art. 22 da **Lei 17.293/2020** somou 1,3 ponto às
operações do art. 54, levando o diesel de 12% a **13,3%** — e começou em
**15/01/2021**, não no dia 1º. O Decreto 67.524/2023 o revogou com efeitos
**retroativos a 15/01/2023**, também meio do mês.

Então 01/2021 e 01/2023 têm **duas alíquotas cada**, e a competência não decide
qual vale. `interna()` levanta `MesPartido` nesses dois meses em vez de escolher
um lado: a apuração precisa separar as entradas pela data do documento. Escolher
calado erraria 1,3 ponto num mês inteiro de compras de diesel.

O complemento **não** alcançou a gasolina: ele é dos arts. 53-A (7%) e 54 (12%),
e o art. 55 não tem parágrafo equivalente. Nem o adicional de 2% do art. 56-C
alcança combustível — ele vale só para bebida alcoólica da posição 2203 e fumo.

### Duas armadilhas na gasolina, uma por estado

**Espírito Santo, 30%.** Uma busca na internet devolve 30% para a gasolina do ES.
O número existe de fato na lei — a Lei 8.098, de 27/09/2005, incluiu o inciso VI
com exatamente 30%. Ele **nunca produziu efeitos**: a Lei 8.237, de 28/12/2005,
deu nova redação ao mesmo inciso antes de o primeiro entrar em vigor, e o texto
consolidado marca a versão anterior como *"sem efeitos"*.

**São Paulo, 27%.** Uma leitura resumida do RICMS/SP soma o adicional de 2% do
art. 56-C aos 25% do art. 55 e chega a 27%. O art. 56-C tem dois incisos, e são
*bebidas alcoólicas da posição 2203* e *fumo* — combustível não está lá.

Os dois erram **para cima**, os dois saem de fonte secundária, e os dois estão em
`REFUTADO` com o motivo. Sobre R$ 10 milhões de base de gasolina, o do ES são
R$ 300 mil e o de SP são R$ 200 mil pedidos a mais. Por isso o registro existe:
para que a próxima pessoa que topar com o número reconheça o que encontrou.

## Por que o livro do cliente não confere esta tabela

Em `tab_aliquota_icms` a regra da casa é *ato legal mais medição na escrituração
do cliente*. **Aqui a segunda metade não existe, e a razão é a própria tese:** na
era do ST o consumidor recebe a nota com CST 60, que não destaca imposto nenhum.
Foi essa ausência que criou a tese de recuperação; ela também impede que o livro
dele sirva de prova.

A prova independente que **vai** existir vem do XML, não do SPED: `vICMSSTRet`
dividido por `vBCSTRet`, que o leitor em `cat/dominio/notafiscal/xml.py` já lê
(`valor_st_retido` e `bc_st_retido`). Essa divisão confirma ou derruba as
alíquotas daqui — e aí a nota de procedência destas linhas muda.

**Em São Paulo isso é factível agora**, e é o próximo passo natural: os clientes
com volume são de SP, e o que falta é achar XML de compra de combustível anterior
a maio de 2023. O 13,3% é o alvo mais interessante da conferência, porque é o
número que ninguém espera encontrar.

No Espírito Santo não há cliente com combustível, então o que dá peso é a lei
mais uma concordância independente: um papel de trabalho de projeto encerrado, de
outro escritório, apurou gasolina a 27% e diesel a 12%. Ele **errou** o FCV (usou
o de São Paulo num cliente do ES, ver `tab_fcv`), e por isso não serve de
gabarito sozinho — mas acertar a alíquota pelo mesmo número que a lei, tendo
errado outra coisa, é concordância e não cópia.
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
    """Uma alíquota interna de combustível, desde quando vale e de onde saiu.

    `dia` é o dia do mês em que ela passou a valer. Quando não é o dia 1º, a
    competência de `desde` é **mês partido** — duas alíquotas no mesmo mês — e
    `interna()` recusa aquele mês em vez de escolher um dos lados. Não é zelo:
    São Paulo tem dois desses (15/01/2021 e 15/01/2023), e devolver o lado
    errado erra 1,3 ponto num mês inteiro de compras, calado.
    """

    aliquota: Decimal
    desde: str        # "aaaa-mm"; vale desta competência em diante
    fundamento: str   # o ato legal, com inciso e alínea
    dia: int = 1      # dia do mês em que começou; != 1 marca mês partido


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
            Vigencia(Decimal(27), "2006-03",
                     "Lei 7.000/2001, art. 20, VI, 'b' ('álcool de todos os "
                     "tipos, inclusive o álcool carburante', NCM 2207.10.0100 e "
                     "2207.10.9902), efeitos de 29/03/2006. Segue percentual até "
                     "hoje: o art. 3º-B só pôs o anidro no monofásico",
                     dia=29),
        ),
    },
    # São Paulo é onde está todo o volume medido — os quatro clientes com CST 61
    # são daqui. O RICMS/SP (Decreto 45.490/2000) separa os combustíveis em dois
    # artigos, e o de 12% levou o complemento da Lei 17.293/2020.
    "SP": {
        DIESEL: (
            Vigencia(Decimal(12), "2023-01",
                     "RICMS/SP, art. 54, VI: volta aos 12% porque o complemento "
                     "do § 7º foi **revogado** pelo Decreto 67.524, de "
                     "27/02/2023, com efeitos retroativos a 15/01/2023",
                     dia=15),
            Vigencia(Decimal("13.3"), "2021-01",
                     "RICMS/SP, art. 54, § 7º: os 12% do inciso VI ficaram "
                     "sujeitos a complemento de 1,3%, 'passando as operações "
                     "internas indicadas no caput a ter uma carga tributária de "
                     "13,3%' (Lei 17.293/2020, art. 22). Decreto 65.253, de "
                     "15/10/2020, com a redação do Decreto 65.470, de "
                     "14/01/2021; efeitos de 15/01/2021. O diesel é o inciso VI "
                     "e **não** está entre as exceções do § 7º (incisos I e XIX)",
                     dia=15),
            Vigencia(Decimal(12), "2014-03",
                     "RICMS/SP, art. 54, VI ('óleo diesel e etanol hidratado "
                     "combustível - EHC'), na redação do Decreto 59.997, de "
                     "20/12/2013, em vigor de 1º/03/2014; Lei 6.374/89, art. 34, "
                     "§ 1º, item 10"),
        ),
        GASOLINA: (
            Vigencia(Decimal(25), "2014-03",
                     "RICMS/SP, art. 55, XXVI ('etanol anidro combustível - EAC "
                     "[...] e gasolina classificada nos códigos 2710.00.0301 a "
                     "0399'), na redação do Decreto 59.997, de 20/12/2013, em "
                     "vigor de 1º/03/2014. **Sem complemento**: o do art. 22 da "
                     "Lei 17.293/2020 alcançou só as alíquotas de 7% e de 12% "
                     "(arts. 53-A e 54), e o art. 55 não tem parágrafo "
                     "equivalente. E sem o adicional de 2% do art. 56-C, que "
                     "vale só para bebida alcoólica e fumo"),
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
    ("SP", GLP): (
        Decimal(18),
        "geral do art. 52, I, por resíduo: o GLP não é nomeado nos arts. 54 nem "
        "55 — só aparece no inciso XXVII do art. 55 como *exclusão* da definição "
        "de solvente. Antes de usar, procurar redução de base de cálculo no "
        "Anexo II do RICMS/SP, que é por onde SP costuma tratar o botijão. "
        "Lembrar que o próprio 18% ainda está em `tab_aliquota_icms.A_CONFERIR`"),
    ("SP", ETANOL_HIDRATADO): (
        Decimal("13.3"),
        "ele divide o inciso VI do art. 54 com o diesel, então à primeira vista "
        "segue os 12%/13,3%. **Mas o RICMS traz duas notas de Informativo SFP só "
        "para ele** — uma 'aplicável de 15/07/2022 a 30/06/2023' e outra "
        "'aplicável a partir de 1º/07/2023' —, o que indica regime próprio "
        "nessas janelas. Ler os dois informativos (DOE 18/07/2022 e DOE "
        "30/06/2023) antes de calcular EHC em SP"),
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
    ("SP", GASOLINA): (
        Decimal(27),
        "soma indevida do adicional de 2% do art. 56-C aos 25% do art. 55, "
        "XXVI. O art. 56-C tem **dois incisos**, e são bebidas alcoólicas da "
        "posição 2203 da NCM e fumo do capítulo 24 — combustível não está lá, e "
        "o adicional só vale em operação destinada a consumidor final. Quem "
        "soma pede 8% a mais"),
}


class AliquotaDeCombustivelDesconhecida(LookupError):
    """Pediram a alíquota de um combustível, UF ou mês que não se conferiu."""


class MesPartido(LookupError):
    """A alíquota mudou no meio daquele mês: há duas, e a competência não decide.

    Erro separado dos outros dois de propósito, porque a saída é diferente — aqui
    não falta ler lei nenhuma e a era está certa. O que falta é **a data do
    documento**: a apuração daquele mês precisa separar as entradas antes e
    depois do dia da virada. Devolver um dos lados erraria o outro calado.
    """


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

    Três recusas, de propósito distintas, porque a saída de cada uma é outra:

    * `ForaDoRegimePercentual` — a competência já é do monofásico. Não falta
      dado: ali não existe percentual. Ir para `tab_ad_rem` e `tab_fcv`;
    * `MesPartido` — a alíquota mudou no meio daquele mês e há duas. Separar as
      entradas pela data do documento;
    * `AliquotaDeCombustivelDesconhecida` — a UF, o produto ou o mês não estão
      conferidos. **Inclusive havendo palpite em `A_CONFERIR`**, caso em que a
      mensagem diz qual é e o que falta ler para usá-lo.
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
        if competencia == vigencia.desde and vigencia.dia != 1:
            anterior = _anterior_a(vigencias, vigencia)
            raise MesPartido(
                f"{produto} em {uf} mudou de alíquota no dia {vigencia.dia} de "
                f"{competencia}: "
                + (f"{anterior.aliquota}% até o dia {vigencia.dia - 1} e "
                   if anterior else "")
                + f"{vigencia.aliquota}% a partir dele ({vigencia.fundamento}). "
                f"A competência não decide qual vale — separar as entradas pela "
                f"data do documento e somar os dois pedaços.")
        if competencia >= vigencia.desde:
            return vigencia.aliquota

    mais_antiga = vigencias[-1].desde
    raise AliquotaDeCombustivelDesconhecida(
        f"A alíquota de {produto} em {uf} só é conhecida de {mais_antiga} em "
        f"diante, e pediram {competencia}. Acrescentar a vigência anterior em "
        f"`tab_aliquota_combustivel.INTERNA`.")


def _anterior_a(vigencias: tuple[Vigencia, ...],
                vigencia: Vigencia) -> Vigencia | None:
    """A vigência que valia antes desta — serve à mensagem do mês partido, que
    só é útil se disser as **duas** alíquotas do mês."""
    posterior = vigencias.index(vigencia) + 1
    return vigencias[posterior] if posterior < len(vigencias) else None


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
