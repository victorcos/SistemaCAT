"""As compras da EFD ICMS/IPI: o leitor que alimenta o crédito de combustível.

Duas famílias de teste, e a segunda é a que teria evitado um erro real.

A primeira confere a **extração**: que o item sai com o documento e o cadastro
juntos, que saída e documento cancelado não rendem linha, e que campo vazio
continua vazio em vez de virar zero.

A segunda confere a **leitura do `CST_ICMS`**, que é um campo com dois domínios
dentro. Ali eu errei escrevendo a lista clássica de CST — sem o `61`, que é a
tese inteira — e o código mais importante do módulo não era reconhecido. O teste
existe nomeado para que esse erro não volte.

**Nenhuma linha de cliente entra como fixture.** As EFD dos testes são montadas
**pelo nome do campo**, a partir de `registros_icms.CAMPOS` — o que faz o teste
conferir também que o leitor e a tabela de leiaute concordam.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped import combustivel
from cat.infraestrutura.sped.combustivel import (
    AMBIGUOS,
    CST_DE_ICMS,
    codigo_de_tributacao,
    compras,
    itens_do_cadastro,
)
from cat.infraestrutura.sped.registros_icms import CAMPOS

CNPJ = "44000003000109"
CNPJ_FORNECEDOR = "11222333000181"


def _linha(registro: str, **valores: str) -> str:
    """Uma linha de SPED montada pelo nome do campo, nunca contando pipes."""
    nomes = CAMPOS[registro]
    campos = [""] * len(nomes)
    campos[0] = registro
    indice = {nome: i for i, nome in enumerate(nomes)}
    for nome, valor in valores.items():
        assert nome in indice, f"{registro} não tem campo {nome}"
        campos[indice[nome]] = valor
    return "|" + "|".join(campos) + "|"


def _cabecalho(cnpj: str = CNPJ, uf: str = "SP") -> str:
    return _linha("0000", COD_VER="017", COD_FIN="0", DT_INI="01062022",
                  DT_FIN="30062022", NOME="EMPRESA DO TESTE LTDA", CNPJ=cnpj,
                  UF=uf, IND_PERFIL="A", IND_ATIV="1")


def _escrever(tmp_path, nome: str, linhas: list[str]) -> str:
    caminho = tmp_path / nome
    caminho.write_bytes(("\n".join(linhas) + "\n").encode("cp1252"))
    return str(caminho)


# ---------------------------------------------------------------- extração


@pytest.fixture
def arquivo(tmp_path) -> str:
    """Uma EFD com o que separa o leitor certo do leitor plausível.

    Uma entrada regular de dois itens — diesel e um parafuso —, uma saída, e uma
    entrada cancelada. Mais o cadastro dos itens e do fornecedor.
    """
    return _escrever(tmp_path, "efd.txt", [
        _cabecalho(),
        _linha("0150", COD_PART="F1", NOME="POSTO DO TESTE LTDA",
               CNPJ=CNPJ_FORNECEDOR),
        _linha("0190", UNID="L", DESCR="LITRO"),
        _linha("0200", COD_ITEM="I-DIESEL", DESCR_ITEM="OLEO DIESEL B S-10",
               UNID_INV="L", COD_NCM="27101921", CEST="0600100"),
        _linha("0200", COD_ITEM="I-PARAFUSO", DESCR_ITEM="PARAFUSO SEXTAVADO",
               UNID_INV="PC", COD_NCM="73181500"),
        # entrada regular, dois itens
        _linha("C100", IND_OPER="0", IND_EMIT="1", COD_PART="F1",
               COD_MOD="55", COD_SIT="00", SER="1", NUM_DOC="12345",
               CHV_NFE="3" * 44, DT_DOC="15062022", DT_E_S="15062022",
               VL_DOC="1000,00"),
        _linha("C170", NUM_ITEM="1", COD_ITEM="I-DIESEL",
               DESCR_COMPL="DIESEL S10", QTD="100,50", UNID="L",
               VL_ITEM="600,00", CST_ICMS="061", CFOP="1653"),
        _linha("C170", NUM_ITEM="2", COD_ITEM="I-PARAFUSO",
               DESCR_COMPL="PARAFUSO", QTD="10", UNID="PC", VL_ITEM="400,00",
               CST_ICMS="000", CFOP="1102", VL_BC_ICMS="400,00",
               ALIQ_ICMS="18", VL_ICMS="72,00"),
        # saída: não é compra
        _linha("C100", IND_OPER="1", COD_PART="F1", COD_MOD="55",
               COD_SIT="00", NUM_DOC="999", DT_DOC="20062022"),
        _linha("C170", NUM_ITEM="1", COD_ITEM="I-DIESEL", QTD="5", UNID="L",
               VL_ITEM="30,00", CST_ICMS="061", CFOP="5653"),
        # entrada cancelada
        _linha("C100", IND_OPER="0", COD_PART="F1", COD_MOD="55",
               COD_SIT="02", NUM_DOC="777", DT_DOC="25062022"),
        _linha("C170", NUM_ITEM="1", COD_ITEM="I-DIESEL", QTD="9999",
               UNID="L", VL_ITEM="99999,00", CST_ICMS="061", CFOP="1653"),
    ])


class TestOQueSai:
    def test_so_os_itens_da_entrada_regular(self, arquivo):
        linhas = list(compras(arquivo, "cp1252"))

        assert [l.codigo_do_item for l in linhas] == ["I-DIESEL", "I-PARAFUSO"]

    def test_o_cabecalho_entra_em_toda_linha(self, arquivo):
        for linha in compras(arquivo, "cp1252"):
            assert linha.cnpj_do_estabelecimento == CNPJ
            assert linha.uf == "SP"
            assert linha.competencia == "2022-06"

    def test_o_documento_entra_em_toda_linha(self, arquivo):
        primeira = next(iter(compras(arquivo, "cp1252")))

        assert primeira.numero == "12345"
        assert primeira.modelo == "55"
        assert primeira.chave == "3" * 44
        assert primeira.data_de_emissao == "2022-06-15"

    def test_o_fornecedor_vem_do_0150(self, arquivo):
        primeira = next(iter(compras(arquivo, "cp1252")))

        assert primeira.cnpj_do_fornecedor == CNPJ_FORNECEDOR
        assert primeira.nome_do_fornecedor == "POSTO DO TESTE LTDA"

    def test_o_cadastro_do_item_vem_do_0200(self, arquivo):
        primeira = next(iter(compras(arquivo, "cp1252")))

        assert primeira.descricao_do_item == "OLEO DIESEL B S-10"
        assert primeira.ncm == "27101921"
        assert primeira.unidade_de_inventario == "L"
        assert primeira.cest == "0600100"

    def test_as_duas_descricoes_convivem(self, arquivo):
        """A do cadastro e a do documento são dados diferentes, e o
        classificador usa as duas: o fornecedor escreve uma coisa na nota e o
        cliente cadastrou outra."""
        primeira = next(iter(compras(arquivo, "cp1252")))

        assert primeira.descricao_do_item == "OLEO DIESEL B S-10"
        assert primeira.descricao_no_documento == "DIESEL S10"

    def test_a_quantidade_e_decimal_e_nao_float(self, arquivo):
        """`100,50` litros vezes ad rem não pode passar por float: a tese
        multiplica milhões de litros e alguém assina o total."""
        primeira = next(iter(compras(arquivo, "cp1252")))

        assert primeira.quantidade == Decimal("100.50")
        assert isinstance(primeira.quantidade, Decimal)


class TestOQueNaoSai:
    def test_a_saida_nao_rende_linha(self, arquivo):
        """`IND_OPER` 1 é venda, e crédito nasce de compra."""
        linhas = list(compras(arquivo, "cp1252"))

        assert all(l.numero != "999" for l in linhas)

    def test_a_entrada_cancelada_nao_rende_linha(self, arquivo):
        """**Medido: 21 dos 7.210 documentos da empresa G têm `COD_SIT` 02.**

        Pouco o bastante para passar despercebido num total, e o suficiente
        para um pedido conter nota cancelada. A nota cancelada do arquivo deste
        teste tem 9.999 litros: se ela vazar, vaza visível.
        """
        linhas = list(compras(arquivo, "cp1252"))

        assert all(l.quantidade != Decimal(9999) for l in linhas)
        assert all(l.situacao not in combustivel.SITUACOES_SEM_CREDITO
                   for l in linhas)

    @pytest.mark.parametrize("situacao", sorted(combustivel.SITUACOES_SEM_CREDITO))
    def test_cada_situacao_sem_credito_e_recusada(self, tmp_path, situacao):
        arquivo = _escrever(tmp_path, f"sit{situacao}.txt", [
            _cabecalho(),
            _linha("C100", IND_OPER="0", COD_MOD="55", COD_SIT=situacao,
                   NUM_DOC="1", DT_DOC="15062022"),
            _linha("C170", NUM_ITEM="1", COD_ITEM="X", QTD="1", UNID="L",
                   VL_ITEM="1,00", CST_ICMS="061", CFOP="1653"),
        ])

        assert list(compras(arquivo, "cp1252")) == []

    @pytest.mark.parametrize("situacao", ["00", "01", "06", "07", "08"])
    def test_as_situacoes_que_escrituram_normalmente_passam(self, tmp_path,
                                                            situacao):
        """06, 07 e 08 são complementar e regime especial — escrituram."""
        arquivo = _escrever(tmp_path, f"sit{situacao}.txt", [
            _cabecalho(),
            _linha("C100", IND_OPER="0", COD_MOD="55", COD_SIT=situacao,
                   NUM_DOC="1", DT_DOC="15062022"),
            _linha("C170", NUM_ITEM="1", COD_ITEM="X", QTD="1", UNID="L",
                   VL_ITEM="1,00", CST_ICMS="061", CFOP="1653"),
        ])

        assert len(list(compras(arquivo, "cp1252"))) == 1

    def test_linha_torta_nao_derruba_a_passada(self, tmp_path):
        """SPED de cliente tem preâmbulo de exportador e linha em branco."""
        arquivo = _escrever(tmp_path, "torto.txt", [
            "isto nao e uma linha de sped",
            _cabecalho(),
            "",
            "|C170|1|falta campo|",
            _linha("C100", IND_OPER="0", COD_MOD="55", COD_SIT="00",
                   NUM_DOC="1", DT_DOC="15062022"),
            _linha("C170", NUM_ITEM="1", COD_ITEM="X", QTD="1", UNID="L",
                   VL_ITEM="1,00", CST_ICMS="061", CFOP="1653"),
        ])

        assert len(list(compras(arquivo, "cp1252"))) == 1


class TestVazioNaoEZero:
    """A lição do relatório 680, e ela vale igual aqui.

    Alíquota ausente e alíquota zero são fatos diferentes. Somar as duas como
    zero não erra o total — erra a pergunta "este fornecedor destacou imposto?",
    que é a que decide se a linha entra na tese.

    **E não é hipótese:** o CST `000` da empresa G tem 610 linhas de entrada e
    só 24 com valor de ICMS. O campo é facultativo por perfil, e este cliente
    quase não o preenche.
    """

    @pytest.fixture
    def arquivo(self, tmp_path) -> str:
        return _escrever(tmp_path, "vazios.txt", [
            _cabecalho(),
            _linha("C100", IND_OPER="0", COD_MOD="55", COD_SIT="00",
                   NUM_DOC="1", DT_DOC="15062022"),
            # sem ALIQ_ICMS nem VL_ICMS: o cliente não preencheu
            _linha("C170", NUM_ITEM="1", COD_ITEM="X", QTD="1", UNID="L",
                   VL_ITEM="10,00", CST_ICMS="060", CFOP="1403"),
            # com zero explícito: o cliente preencheu, e o valor é zero
            _linha("C170", NUM_ITEM="2", COD_ITEM="Y", QTD="1", UNID="L",
                   VL_ITEM="10,00", CST_ICMS="041", CFOP="1403",
                   ALIQ_ICMS="0", VL_ICMS="0,00"),
        ])

    def test_campo_ausente_vira_None(self, arquivo):
        primeira = next(iter(compras(arquivo, "cp1252")))

        assert primeira.aliquota_do_icms is None
        assert primeira.valor_do_icms is None

    def test_zero_escrito_vira_zero(self, arquivo):
        segunda = list(compras(arquivo, "cp1252"))[1]

        assert segunda.aliquota_do_icms == Decimal(0)
        assert segunda.valor_do_icms == Decimal(0)

    def test_os_dois_nao_se_confundem(self, arquivo):
        ausente, zero = compras(arquivo, "cp1252")

        assert ausente.valor_do_icms != zero.valor_do_icms


# -------------------------------------------------- o campo de dois domínios


class TestOCstQueEuErrei:
    """**O erro que este teste existe para impedir.**

    A primeira versão trazia a lista clássica de CST de ICMS — 00, 10, 20, 30,
    40, 41, 50, 51, 60, 70, 90 — e com ela o `061` não era reconhecido como
    nada: nem CST, nem CSOSN. O módulo inteiro existe para achar compra de
    combustível, e o código que a marca saía vazio.

    O monofásico criou quatro CST que a lista clássica não tem, e um deles é o
    `61`.
    """

    @pytest.mark.parametrize("cst", ["02", "15", "53", "61"])
    def test_os_quatro_cst_do_monofasico_estao_na_lista(self, cst):
        assert cst in CST_DE_ICMS

    def test_o_61_e_monofasico(self):
        lido = codigo_de_tributacao("061")

        assert (lido.origem, lido.cst) == ("0", "61")
        assert lido.e_monofasico

    def test_o_60_nao_e_monofasico_e_isso_importa(self):
        """O 60 é **toda** mercadoria com ST retido — cerveja, sabão, pneu.
        Tomá-lo por indicador de combustível traria a loja inteira."""
        lido = codigo_de_tributacao("060")

        assert not lido.e_monofasico
        assert lido.e_substituicao


class TestOrigemOuCsosn:
    @pytest.mark.parametrize("bruto, origem, cst", [
        ("000", "0", "00"),
        ("060", "0", "60"),
        ("061", "0", "61"),
        ("090", "0", "90"),
        ("260", "2", "60"),   # importado, com ST
        ("560", "5", "60"),
        ("041", "0", "41"),
    ])
    def test_origem_mais_cst(self, bruto, origem, cst):
        lido = codigo_de_tributacao(bruto)

        assert (lido.origem, lido.cst, lido.csosn) == (origem, cst, "")

    @pytest.mark.parametrize("bruto", ["101", "103", "201", "203", "900"])
    def test_csosn_sem_ambiguidade(self, bruto):
        lido = codigo_de_tributacao(bruto)

        assert lido.csosn == bruto
        assert (lido.origem, lido.cst) == ("", "")
        assert not lido.ambiguo

    def test_o_900_nao_e_origem_9_porque_origem_9_nao_existe(self):
        """A origem vai de 0 a 8. É o que desempata o `900` sem precisar de
        estatística."""
        assert codigo_de_tributacao("900").csosn == "900"
        assert not codigo_de_tributacao("900").ambiguo

    def test_codigo_que_nao_e_nenhum_dos_dois_volta_so_com_o_bruto(self):
        """Inventar leitura para código desconhecido é escrever crédito em cima
        de um campo que ninguém entendeu."""
        lido = codigo_de_tributacao("970")

        assert lido.bruto == "970"
        assert (lido.origem, lido.cst, lido.csosn) == ("", "", "")

    @pytest.mark.parametrize("bruto", ["", "  ", "6", "0610", "abc", "06x"])
    def test_o_que_nao_tem_forma_de_codigo(self, bruto):
        lido = codigo_de_tributacao(bruto)

        assert (lido.origem, lido.cst, lido.csosn) == ("", "", "")


class TestOsCincoAmbiguos:
    """Os códigos que cabem nos dois domínios, e por que o CSOSN vence.

    `102` pode ser CSOSN 102 ou origem 1 com CST 02 (monofásica própria);
    `300`, `400` e `500`, CSOSN ou origem com CST 00. Nos 40 arquivos medidos
    todos se comportaram como CSOSN — o `500` tem 3.245 linhas de entrada e uma
    só com ICMS destacado, e tributada integralmente traria em quase todas.

    **A estatística é de um cliente, e por isso o par sai marcado.** A apuração
    pode recusar um código ambíguo em vez de confiar nela.
    """

    def test_sao_cinco_e_calculados(self):
        assert AMBIGUOS == {"102", "202", "300", "400", "500"}

    @pytest.mark.parametrize("bruto", sorted(["102", "202", "300", "400", "500"]))
    def test_cada_um_vence_como_csosn_e_sai_marcado(self, bruto):
        lido = codigo_de_tributacao(bruto)

        assert lido.csosn == bruto
        assert lido.ambiguo

    def test_a_lista_e_derivada_e_nao_digitada(self):
        """Acrescentar um CST novo recalcula a ambiguidade; uma lista digitada
        ficaria velha em silêncio."""
        for bruto in AMBIGUOS:
            assert bruto in combustivel.CSOSN
            assert bruto[0] in combustivel.ORIGENS
            assert bruto[1:] in CST_DE_ICMS

    def test_o_500_conta_como_substituicao(self):
        """CSOSN 500 é "ICMS cobrado anteriormente por substituição": para a
        tese do ST ele é irmão do CST 60, e deixá-lo de fora perderia toda
        compra de fornecedor do Simples Nacional."""
        assert codigo_de_tributacao("500").e_substituicao


# ----------------------------------------------------------- cadastro de itens


class TestOCadastroDeItens:
    @pytest.fixture
    def arquivo(self, tmp_path) -> str:
        return _escrever(tmp_path, "cadastro.txt", [
            _cabecalho(),
            _linha("0200", COD_ITEM="I-DIESEL", DESCR_ITEM="OLEO DIESEL B S-10",
                   UNID_INV="L", COD_NCM="27101921", CEST="0600100"),
            _linha("0205", DESCR_ANT_ITEM="OLEO DIESEL S10 ANTIGO",
                   DT_INI="01012021", DT_FIM="31122021"),
            _linha("0205", DESCR_ANT_ITEM="DIESEL COMUM",
                   DT_INI="01012020", DT_FIM="31122020"),
            _linha("0200", COD_ITEM="I-PARAFUSO", DESCR_ITEM="PARAFUSO",
                   UNID_INV="PC", COD_NCM="73181500"),
        ])

    def test_traz_o_0200_por_codigo(self, arquivo):
        itens = itens_do_cadastro(arquivo, "cp1252")

        assert set(itens) == {"I-DIESEL", "I-PARAFUSO"}
        assert itens["I-DIESEL"].ncm == "27101921"
        assert itens["I-DIESEL"].cest == "0600100"

    def test_o_0205_pende_do_0200_anterior(self, arquivo):
        """É filho, não irmão: as duas descrições antigas são do diesel, e
        nenhuma do parafuso."""
        itens = itens_do_cadastro(arquivo, "cp1252")

        assert len(itens["I-DIESEL"].anteriores) == 2
        assert itens["I-PARAFUSO"].anteriores == []

    def test_a_descricao_anterior_vem_com_vigencia(self, arquivo):
        """Sem a vigência a descrição antiga não serve: o classificador precisa
        saber **quando** o código se chamava aquilo."""
        itens = itens_do_cadastro(arquivo, "cp1252")

        assert itens["I-DIESEL"].anteriores[0] == (
            "OLEO DIESEL S10 ANTIGO", "2021-01-01", "2021-12-31")

    def test_0205_sem_0200_antes_nao_derruba(self, tmp_path):
        arquivo = _escrever(tmp_path, "orfao.txt", [
            _cabecalho(),
            _linha("0205", DESCR_ANT_ITEM="SEM PAI", DT_INI="01012021"),
        ])

        assert itens_do_cadastro(arquivo, "cp1252") == {}
