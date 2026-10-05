"""O arquivo digital da CAT 42: a escrita e a pré-validação.

O formato foi conferido em arquivos que a empresa 17 transmitiu antes de virar
teste: sem `|` no início, `|` no fim só com o último campo vazio, CRLF,
quantidade com 3 casas e valor com 2.
"""

from datetime import date
from decimal import Decimal

import pytest

from cat.dominio.icms.cat42.arquivo_digital import (
    Abertura,
    ArquivoDigital,
    DocumentoEletronico,
    DocumentoNaoEletronico,
    IndicadorDeOperacao as Ind,
    Item,
    Natureza,
    Participante,
    Saldo,
    ValorInvalido,
    cod_legal_da_devolucao_de_venda,
    nome_do_arquivo,
    numero,
    texto,
)
from cat.dominio.icms.cat42.pre_validacao import (
    Regra,
    chave_valida,
    cpf_valido,
    ie_sp_valida,
    validar,
)
from cat.dominio.comum.cnpj import digitos_verificadores

D = Decimal
CNPJ = "44000003001334"  # formato real; o dígito é recalculado abaixo
CNPJ = CNPJ[:12] + digitos_verificadores(CNPJ[:12])
FORNECEDOR = "44000010000100"
FORNECEDOR = FORNECEDOR[:12] + digitos_verificadores(FORNECEDOR[:12])
IE_SP = "798092322114"          # IE real de SP, com os dois verificadores certos


def chave(cnpj: str, modelo: str, numero_nota: int) -> str:
    """Uma chave de 44 dígitos com o verificador certo."""
    base = f"3524{'01'}{cnpj}{modelo}001{numero_nota:09d}1{numero_nota:08d}"[:43]
    soma = sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(base)))
    resto = soma % 11
    return base + str(0 if resto < 2 else 11 - resto)


def bytes_de(arquivo: ArquivoDigital) -> list[bytes]:
    return [(l + "\r\n").encode("latin-1") for l in arquivo.linhas()]


def arquivo_que_fecha() -> ArquivoDigital:
    """Iogurte: abre com 10 un e R$ 20; entra 10 un com R$ 30; vende 4 no cupom.

        saldo 20 un, R$ 50, unitário 2,50 -> baixa 4 x 2,50 = 10 -> fim 16 un, R$ 40
    """
    compra = chave(FORNECEDOR, "55", 1)
    cupom = chave(CNPJ, "59", 2)
    return ArquivoDigital(
        abertura=Abertura(2024, 1, "LOJA DE TESTE", CNPJ, IE_SP, "3552205"),
        participantes=[Participante(CNPJ, "LOJA DE TESTE", cnpj=CNPJ, ie=IE_SP, cod_mun="3552205"),
                       Participante("120112", "FORNECEDOR", cnpj=FORNECEDOR, cod_mun="3506300")],
        itens=[Item("1002140", "IOGURTE 170G", "UN1", "04032000", "07891024183007", D(18), "1702200")],
        saldos=[Saldo("1002140", D(10), D(20), D(16), D(40))],
        eletronicos=[
            DocumentoEletronico(date(2024, 1, 3), 1, Ind.ENTRADA, "1002140", "1403", D(10), icms_tot=D(30),
                                chave=compra),
            DocumentoEletronico(date(2024, 1, 5), 33, Ind.SAIDA, "1002140", "5405", D(4), cod_legal=0,
                                chave=cupom),
        ],
    )


class TestFormato:
    def test_numero_com_as_casas_do_leiaute(self):
        assert numero(D("1255.42"), 2) == "1255,42"
        assert numero(D(10000), 2) == "10000,00"
        assert numero(D(1), 3) == "1,000"
        assert numero(D("0.005"), 2) == "0,01"      # meio para cima, só na escrita
        assert numero(None, 2) == ""

    def test_sem_sinal(self):
        with pytest.raises(ValorInvalido):
            numero(D("-1"), 3, "QTD")

    def test_texto_sem_pipe_sem_controle_e_em_latin1(self):
        assert texto("CHOC.|LACTA\tAO LEITE") == "CHOC. LACTA AO LEITE"
        assert texto("PÃO D’ÁGUA – 500G") == "PÃO D'ÁGUA - 500G"
        assert texto("x" * 300) == "x" * 255

    def test_linha_como_a_boa_transmitiu(self):
        linhas = list(arquivo_que_fecha().linhas())
        assert linhas[0] == f"0000|012024|LOJA DE TESTE|{CNPJ}|{IE_SP}|3552205|01|00"
        assert linhas[3] == "0200|1002140|IOGURTE 170G|07891024183007|UN1|04032000|18,00|1702200"
        assert linhas[4] == "1050|1002140|10,000|20,00|16,000|40,00"
        # entrada termina com | porque o último campo (COD_LEGAL) é vazio
        assert linhas[5].endswith("|1403|10,000|30,00||")
        assert linhas[6].endswith("|033|1|1002140|5405|4,000|||0")
        assert not any(l.startswith("|") for l in linhas)

    def test_nome_do_arquivo(self):
        assert nome_do_arquivo(CNPJ, 2024, 1) == f"CAT5_SP_{CNPJ}_1_2024.txt"
        assert nome_do_arquivo(CNPJ, 2024, 12, previa=True) == f"CAT5_SP_{CNPJ}_12_2024_PREVIA.txt"


class TestNatureza:
    """A tabela de obrigatoriedade da seção 5 do manual."""

    def test_as_quatro_naturezas(self):
        assert Natureza.de("0", "1403") is Natureza.ENTRADA
        assert Natureza.de("0", "1411") is Natureza.DEVOLUCAO_DE_SAIDA
        assert Natureza.de("1", "5405") is Natureza.SAIDA
        assert Natureza.de("1", "5411") is Natureza.DEVOLUCAO_DE_ENTRADA

    def test_saida_nao_leva_icms_e_zero_nao_leva_confronto(self):
        venda = DocumentoEletronico(date(2024, 1, 5), 1, Ind.SAIDA, "X", "5405", D(1),
                                    icms_tot=D(9), vl_confr=D(3), cod_legal=0, chave="1" * 44)
        assert venda.campos()[-3:] == ["", "", "0"]

    def test_saida_enquadrada_leva_confronto(self):
        perda = DocumentoEletronico(date(2024, 1, 31), 1, Ind.SAIDA, "X", "5927", D(2),
                                    vl_confr=D("1.2"), cod_legal=2, chave="1" * 44)
        assert perda.campos()[-3:] == ["", "1,20", "2"]

    def test_devolucao_de_saida_leva_os_tres(self):
        dev = DocumentoEletronico(date(2024, 1, 9), 1, Ind.ENTRADA, "X", "1411", D(1),
                                  icms_tot=D("2.5"), vl_confr=D("1.8"), cod_legal=1, chave="1" * 44)
        assert dev.campos()[-3:] == ["2,50", "1,80", "1"]

    def test_entrada_nao_leva_enquadramento(self):
        e = DocumentoEletronico(date(2024, 1, 9), 1, Ind.ENTRADA, "X", "1403", D(1),
                                icms_tot=D(3), cod_legal=1, vl_confr=D(1), chave="1" * 44)
        assert e.campos()[-3:] == ["3,00", "", ""]

    def test_1200_tem_o_cfop_antes_do_codigo(self):
        nf = DocumentoNaoEletronico(date(2024, 1, 9), 2, Ind.ENTRADA, "X", "1403", D(1), icms_tot=D(3),
                                    modelo="01", numero_documento="000123", participante="F1", serie="1")
        assert nf.campos() == ["1200", "F1", "01", "", "1", "000123", "002", "0", "09012024", "1403", "X",
                               "1,000", "3,00", "", ""]

    def test_nr_do_item_fora_do_leiaute(self):
        with pytest.raises(ValorInvalido):
            DocumentoEletronico(date(2024, 1, 9), 1000, Ind.ENTRADA, "X", "1403", D(1), chave="1").campos()


class TestDevolucaoDeVenda:
    def test_de_fora_do_estado_e_4(self):
        assert cod_legal_da_devolucao_de_venda("2411", cupom_no_zero=False) == 4

    def test_no_trabalho_que_poe_o_cupom_no_zero_e_0(self):
        assert cod_legal_da_devolucao_de_venda("1411", cupom_no_zero=True) == 0

    def test_sem_a_nota_original_nao_se_sabe(self):
        assert cod_legal_da_devolucao_de_venda("1411", cupom_no_zero=False) is None


class TestDigitos:
    def test_ie_de_sp(self):
        assert ie_sp_valida(IE_SP)
        assert not ie_sp_valida("798092322115")

    def test_cpf(self):
        assert cpf_valido("52998224725")
        assert not cpf_valido("52998224724") and not cpf_valido("11111111111")

    def test_chave(self):
        c = chave(CNPJ, "59", 7)
        assert chave_valida(c)
        assert not chave_valida(c[:43] + str((int(c[43]) + 1) % 10))


class TestPreValidacao:
    def test_o_arquivo_bem_formado_passa_e_a_ficha_fecha(self):
        v = validar(bytes_de(arquivo_que_fecha()))
        assert v.passou, [(o.regra.name, o.mensagem) for o in v.exemplos]
        assert v.avisos == 0
        assert v.por_registro == {"0000": 1, "0150": 2, "0200": 1, "1050": 1, "1100": 2}
        assert (v.itens_recompostos, v.itens_que_fecham) == (1, 1)
        assert v.cnpj == CNPJ and v.periodo == "012024"

    def test_linha_sem_crlf(self):
        linhas = bytes_de(arquivo_que_fecha())
        linhas[2] = linhas[2].rstrip(b"\r\n") + b"\n"
        assert validar(linhas).por_regra[Regra.LINHA_SEM_CRLF] == 1

    def test_saldo_que_nao_fecha_em_quantidade_e_erro(self):
        a = arquivo_que_fecha()
        a.saldos = [Saldo("1002140", D(10), D(20), D(17), D(40))]
        v = validar(bytes_de(a))
        assert v.por_regra == {Regra.SALDO_EM_QUANTIDADE: 1}
        assert "chega a 16" in v.exemplos[0].mensagem

    def test_saldo_que_diverge_em_valor_e_aviso(self):
        a = arquivo_que_fecha()
        a.saldos = [Saldo("1002140", D(10), D(20), D(16), D("40.50"))]
        v = validar(bytes_de(a))
        assert v.passou and v.por_regra == {Regra.SALDO_EM_VALOR: 1}

    def test_a_venda_sem_documento_deixa_a_ficha_sem_fechar(self):
        """O cupom do relatório não tem chave: fora do 1100, o saldo não chega ao 1050."""
        a = arquivo_que_fecha()
        a.eletronicos = a.eletronicos[:1]
        v = validar(bytes_de(a))
        assert Regra.SALDO_EM_QUANTIDADE in v.por_regra

    def test_regras_da_tabela_de_natureza(self):
        a = arquivo_que_fecha()
        linhas = bytes_de(a)
        # venda sem COD_LEGAL, e entrada com COD_LEGAL
        linhas[6] = linhas[6].replace(b"|||0\r\n", b"|||\r\n")
        linhas[5] = linhas[5].replace(b"30,00||\r\n", b"30,00||1\r\n")
        v = validar(linhas)
        assert v.por_regra[Regra.COD_LEGAL] == 2

    def test_campos_e_referencias(self):
        linhas = bytes_de(arquivo_que_fecha())
        linhas.insert(4, b"0200|1002140|REPETIDO|x|UN|04032000|18,00|1702200\r\n")   # código repetido
        linhas[7] = linhas[7].replace(b"|1002140|5405|", b"|9999|5405|")               # venda de item sem 0200
        v = validar(linhas)
        assert v.por_regra[Regra.ITEM_REPETIDO] == 1
        assert v.por_regra[Regra.ITEM_INEXISTENTE] == 1

    def test_ordem_e_chave(self):
        linhas = bytes_de(arquivo_que_fecha())
        linhas[4], linhas[5] = linhas[5], linhas[4]      # 1100 antes do 1050
        c = chave(FORNECEDOR, "55", 1)
        linhas[4] = linhas[4].replace(c.encode(), (c[:43] + str((int(c[43]) + 1) % 10)).encode())
        v = validar(linhas)
        assert v.por_regra[Regra.ORDEM_DOS_REGISTROS] == 1
        assert v.por_regra[Regra.CHAVE] == 1

    def test_valor_negativo_e_data_fora_do_mes(self):
        linhas = bytes_de(arquivo_que_fecha())
        linhas[6] = linhas[6].replace(b"05012024", b"05022024").replace(b"|4,000|", b"|-4,000|")
        v = validar(linhas)
        assert v.por_regra[Regra.DATA] == 1 and v.por_regra[Regra.VALOR_NEGATIVO] == 1

    def test_item_de_nota_com_dois_codigos_e_aviso_e_linha_repetida_e_erro(self):
        """Num arquivo que a empresa 17 transmitiu, 3 itens de nota têm dois códigos: aceito, é aviso."""
        linhas = bytes_de(arquivo_que_fecha())
        outro_codigo = linhas[5].replace(b"|1002140|", b"|1002141|")
        repetida = linhas[5]
        v = validar(linhas[:6] + [outro_codigo, repetida] + linhas[6:])
        assert v.por_regra[Regra.ITEM_DO_DOCUMENTO_COM_DOIS_CODIGOS] == 1
        assert v.por_regra[Regra.ITEM_DO_DOCUMENTO_REPETIDO] == 1

    def test_sem_o_estabelecimento_no_0150(self):
        a = arquivo_que_fecha()
        a.participantes = a.participantes[1:]
        assert validar(bytes_de(a)).por_regra == {Regra.SEM_O_ESTABELECIMENTO: 1}

    def test_exemplos_sao_limitados_e_a_contagem_nao(self):
        a = arquivo_que_fecha()
        base = a.eletronicos[1]
        torta = base.chave[:43] + str((int(base.chave[43]) + 1) % 10)
        a.eletronicos = [a.eletronicos[0]] + [
            DocumentoEletronico(base.data, i, Ind.SAIDA, "1002140", "5405", D("0.001"), cod_legal=0,
                                chave=torta) for i in range(1, 400)]
        v = validar(bytes_de(a))
        assert v.por_regra[Regra.CHAVE] == 399
        assert sum(1 for o in v.exemplos if o.regra is Regra.CHAVE) == 200
