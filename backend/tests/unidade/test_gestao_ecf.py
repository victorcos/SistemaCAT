"""A Gestão de IRPJ e CSLL: ler a ECF e montar o bloco do Lucro Real.

A amostra é uma ECF anual reduzida, com o que separa um quadro certo de um
quadro plausível:

* a Parte A do e-Lalur (M300) com **linhas calculadas** (lucro líquido, lucro
  real) e **lançamentos** (adições e exclusões) — os dois vêm com o mesmo tipo
  e só o indicador de relacionamento os distingue; somar os dois dobraria tudo;
* o e-Lacs (M350) da CSLL, com os próprios valores;
* o cálculo do imposto (N630) e da contribuição (N670), onde as linhas são
  achadas **pela descrição**, não pelo código — que muda a cada leiaute;
* uma conta da Parte B com saldo credor, que entra negativo.

As linhas são montadas por nome de campo a partir do leiaute da ECF, escrito
aqui uma vez só e usado por todos os registros.
"""

import pytest

from cat.dominio.sped.cabecalho import TipoSped, ler_cabecalho
from cat.infraestrutura.gestao.ecf import ArquivoECFInvalido, ler_ecf, normalizar
from cat.infraestrutura.gestao.montagem import ler_ecfs, montar_irpj_csll
from cat.infraestrutura.gestao.numeros import centavos
from cat.infraestrutura.gestao.quadros_irpj_csll import montar_relatorio_irpj_csll

CNPJ = "11222333000181"

# o leiaute de cada registro que a amostra usa, campo a campo
LEIAUTE = {
    "0000": ["REG", "LECF", "COD_VER", "CNPJ", "NOME", "IND_SIT_INI_PER", "SIT_ESPECIAL",
             "PAT_REMAN_CIS", "DT_SIT_ESP", "DT_INI", "DT_FIN", "RETIFICADORA", "NUM_REC",
             "TIP_ECF", "COD_SCP"],
    "0010": ["REG", "OPT_REFIS", "OPT_PAES", "FORMA_TRIB", "FORMA_APUR", "COD_QUALIF_PJ"],
    "M010": ["REG", "COD_CTA_B", "DESC_CTA_B", "DT_AP_SD", "COD_LAN_ORIG", "DESC_LAN_ORIG",
             "TIPO_TRIBUTO", "SD_INI", "IND_SD_INI"],
    "M030": ["REG", "DT_INI", "DT_FIN", "PER_APUR"],
    "M300": ["REG", "CODIGO", "DESCRICAO", "TIPO_LANCAMENTO", "IND_RELACAO", "VALOR",
             "HIST_LAN_LALUR", "JUST"],
    "M350": ["REG", "CODIGO", "DESCRICAO", "TIPO_LANCAMENTO", "IND_RELACAO", "VALOR",
             "HIST_LAN_LACS", "JUST"],
    "M500": ["REG", "COD_CTA_B", "TIPO_TRIBUTO", "DT_AP_SD", "COD_LAN_ORIG", "SD_INI",
             "IND_SD_INI", "VL_LAN_PARTE_B", "IND_VL_LAN_PARTE_B", "SD_FIM", "IND_SD_FIM"],
    "N030": ["REG", "DT_INI", "DT_FIN", "PER_APUR"],
    "N500": ["REG", "CODIGO", "DESCRICAO", "VALOR"],
    "N630": ["REG", "CODIGO", "DESCRICAO", "VALOR"],
    "N650": ["REG", "CODIGO", "DESCRICAO", "VALOR"],
    "N670": ["REG", "CODIGO", "DESCRICAO", "VALOR"],
}


def _linha(registro: str, **valores: str) -> str:
    nomes = LEIAUTE[registro]
    campos = [""] * len(nomes)
    campos[0] = registro
    indice = {n: i for i, n in enumerate(nomes)}
    for nome, valor in valores.items():
        assert nome in indice, f"{registro} não tem campo {nome}"
        campos[indice[nome]] = valor
    return "|" + "|".join(campos) + "|"


CABECALHO = _linha("0000", LECF="LECF", COD_VER="0009", CNPJ=CNPJ,
                   NOME="COMERCIO DO TESTE LTDA", IND_SIT_INI_PER="0",
                   DT_INI="01012021", DT_FIN="31122021", RETIFICADORA="0")

ECF = "\n".join([
    CABECALHO,
    _linha("0010", FORMA_TRIB="1", FORMA_APUR="A"),

    # o cadastro das contas da Parte B
    _linha("M010", COD_CTA_B="B001", DESC_CTA_B="PREJUIZO FISCAL A COMPENSAR",
           TIPO_TRIBUTO="I"),
    _linha("M010", COD_CTA_B="B002", DESC_CTA_B="RESERVA DE SUBVENCAO",
           TIPO_TRIBUTO="I"),

    # --- o e-Lalur do exercício
    _linha("M030", DT_INI="01012021", DT_FIN="31122021", PER_APUR="A00"),
    _linha("M300", CODIGO="L001", DESCRICAO="LUCRO LIQUIDO ANTES DO IRPJ",
           TIPO_LANCAMENTO="L", VALOR="100000,00"),
    # adições: têm indicador de relacionamento; a soma abaixo não tem
    _linha("M300", CODIGO="A001", DESCRICAO="MULTAS NAO DEDUTIVEIS",
           TIPO_LANCAMENTO="A", IND_RELACAO="1", VALOR="8000,00"),
    _linha("M300", CODIGO="A002", DESCRICAO="BRINDES", TIPO_LANCAMENTO="A",
           IND_RELACAO="2", VALOR="2000,00"),
    _linha("M300", CODIGO="A999", DESCRICAO="SOMA DAS ADICOES", TIPO_LANCAMENTO="A",
           VALOR="10000,00"),
    _linha("M300", CODIGO="E001", DESCRICAO="REVERSAO DE PROVISOES",
           TIPO_LANCAMENTO="E", IND_RELACAO="1", VALOR="5000,00"),
    _linha("M300", CODIGO="E999", DESCRICAO="SOMA DAS EXCLUSOES", TIPO_LANCAMENTO="E",
           VALOR="5000,00"),
    _linha("M300", CODIGO="L002", DESCRICAO="LUCRO REAL ANTES DA COMPENSACAO",
           TIPO_LANCAMENTO="L", VALOR="105000,00"),
    _linha("M300", CODIGO="P001", DESCRICAO="COMPENSACAO DE PREJUIZOS DE PERIODOS ANTERIORES",
           TIPO_LANCAMENTO="P", IND_RELACAO="1", VALOR="15000,00"),
    _linha("M300", CODIGO="L003", DESCRICAO="LUCRO REAL", TIPO_LANCAMENTO="L",
           VALOR="90000,00"),

    # --- o e-Lacs
    _linha("M350", CODIGO="L001", DESCRICAO="LUCRO LIQUIDO ANTES DA CSLL",
           TIPO_LANCAMENTO="L", VALOR="100000,00"),
    _linha("M350", CODIGO="A001", DESCRICAO="MULTAS NAO DEDUTIVEIS",
           TIPO_LANCAMENTO="A", IND_RELACAO="1", VALOR="8000,00"),
    _linha("M350", CODIGO="L002", DESCRICAO="BASE DE CALCULO DA CSLL",
           TIPO_LANCAMENTO="L", VALOR="108000,00"),

    # --- a Parte B: prejuízo é saldo devedor (positivo); reserva, credor
    _linha("M500", COD_CTA_B="B001", TIPO_TRIBUTO="I", SD_FIM="30000,00", IND_SD_FIM="D"),
    _linha("M500", COD_CTA_B="B002", TIPO_TRIBUTO="I", SD_FIM="12000,00", IND_SD_FIM="C"),

    # --- o cálculo do imposto
    _linha("N030", DT_INI="01012021", DT_FIN="31122021", PER_APUR="A00"),
    _linha("N500", CODIGO="N01", DESCRICAO="BASE DE CALCULO DA ESTIMATIVA",
           VALOR="90000,00"),
    _linha("N630", CODIGO="N10", DESCRICAO="IMPOSTO A ALIQUOTA DE 15%", VALOR="13500,00"),
    _linha("N630", CODIGO="N11", DESCRICAO="ADICIONAL DO IMPOSTO DE RENDA", VALOR="3000,00"),
    _linha("N630", CODIGO="N20", DESCRICAO="(-) INCENTIVO FISCAL PAT", VALOR="500,00"),
    _linha("N630", CODIGO="N30", DESCRICAO="IMPOSTO DE RENDA A PAGAR", VALOR="16000,00"),
    _linha("N650", CODIGO="N40", DESCRICAO="BASE DE CALCULO DA CSLL", VALOR="108000,00"),
    _linha("N670", CODIGO="N50",
           DESCRICAO="CONTRIBUICAO SOCIAL SOBRE O LUCRO LIQUIDO POR ATIVIDADE",
           VALOR="9720,00"),
    _linha("N670", CODIGO="N60", DESCRICAO="(-) COMPENSACOES", VALOR="720,00"),
    _linha("N670", CODIGO="N70", DESCRICAO="CSLL A PAGAR", VALOR="9000,00"),
    "|9999|30|",
]) + "\n"


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "ecf_2021.txt"
    caminho.write_bytes(ECF.encode("cp1252"))
    return str(caminho)


@pytest.fixture
def apuracao(arquivo):
    return ler_ecf(arquivo)


@pytest.fixture
def irpj(apuracao):
    return montar_relatorio_irpj_csll([apuracao], "IRPJ")


def _valor(relatorio, rotulo_contem: str, periodo="2021-12") -> int:
    for quadro in relatorio.quadros:
        for linha in quadro.linhas:
            if rotulo_contem in linha.rotulo:
                return linha.valores[periodo]
    raise AssertionError(f"nenhuma linha com {rotulo_contem!r}")


class TestOReconhecimentoDoArquivo:
    def test_o_dominio_reconhece_o_zero_zero_zero_zero_da_ecf(self):
        """A ECF é o quarto leiaute, e o único com o CNPJ antes das datas."""
        c = ler_cabecalho(CABECALHO)

        assert c.tipo is TipoSped.ECF
        assert c.cnpj.valor == CNPJ
        assert c.nome == "COMERCIO DO TESTE LTDA"
        assert (c.inicio.isoformat(), c.fim.isoformat()) == ("2021-01-01", "2021-12-31")
        assert c.versao_leiaute == "0009"

    def test_a_data_de_situacao_especial_nao_confunde_o_periodo(self):
        """Com DT_SIT_ESP preenchida ficam três datas coladas; vale o último par."""
        especial = _linha("0000", LECF="LECF", COD_VER="0009", CNPJ=CNPJ,
                          NOME="COMERCIO DO TESTE LTDA", SIT_ESPECIAL="1",
                          DT_SIT_ESP="15062021", DT_INI="01012021", DT_FIN="30062021",
                          RETIFICADORA="1")
        c = ler_cabecalho(especial)

        assert (c.inicio.isoformat(), c.fim.isoformat()) == ("2021-01-01", "2021-06-30")
        assert c.retificadora is True

    def test_a_identificacao_da_apuracao_vem_do_dominio(self, apuracao):
        assert apuracao.cnpj == CNPJ
        assert apuracao.razao_social == "COMERCIO DO TESTE LTDA"
        assert (apuracao.dt_ini, apuracao.dt_fin) == ("01012021", "31122021")
        assert apuracao.forma_tributacao == "1"     # Lucro Real
        assert apuracao.forma_apuracao == "A"       # anual

    def test_arquivo_que_nao_e_ecf_e_recusado_dizendo_o_que_e(self, tmp_path):
        outro = tmp_path / "nao_e_ecf.txt"
        outro.write_bytes(
            ("|0000|006|0|||01062021|30062021|X|11222333000181|SP|3550308||00|2|\n")
            .encode("cp1252"))

        with pytest.raises(ArquivoECFInvalido, match="EFD Contribuições"):
            ler_ecf(str(outro))

    def test_arquivo_sem_zero_zero_zero_zero_nenhum(self, tmp_path):
        vazio = tmp_path / "vazio.txt"
        vazio.write_bytes(b"|M300|L001|LUCRO|L||0,00|\n")

        with pytest.raises(ArquivoECFInvalido):
            ler_ecf(str(vazio))


class TestALeituraDaParteAEDaParteB:
    def test_o_periodo_anual_cai_em_dezembro(self, apuracao):
        assert [p.codigo for p in apuracao.periodos] == ["A00"]
        assert apuracao.periodos[0].mes == "2021-12"

    def test_lancamento_e_total_se_distinguem_pelo_indicador(self, apuracao):
        """"SOMA DAS ADIÇÕES" tem o mesmo tipo das adições. Somar os dois dobra."""
        lalur = apuracao.periodos[0].lalur
        com_indicador = [x for x in lalur if x.tipo == "A" and x.ind_relacao]

        assert sum(x.valor for x in com_indicador) == centavos("10000,00")
        assert any(x.tipo == "A" and not x.ind_relacao for x in lalur)

    def test_saldo_credor_da_parte_b_entra_negativo(self, apuracao):
        """Prejuízo fiscal é devedor e soma; reserva de subvenção é credora."""
        contas = {c.codigo: c for c in apuracao.periodos[0].parte_b}

        assert contas["B001"].saldo_final == centavos("30000,00")
        assert contas["B002"].saldo_final == -centavos("12000,00")
        assert contas["B001"].descricao == "PREJUIZO FISCAL A COMPENSAR"

    def test_nada_foi_descartado_em_silencio(self, apuracao):
        assert apuracao.descartes == {}

    def test_a_normalizacao_tira_acento_e_colapsa_espaco(self):
        assert normalizar("  Adição   de  Créditos ") == "ADICAO DE CREDITOS"


class TestOsQuadrosDeIrpj:
    def test_a_apuracao_do_lucro_real_fecha(self, irpj):
        assert irpj.tributo == "IRPJ"
        assert irpj.cnpj == CNPJ
        assert _valor(irpj, "Lucro Líquido Antes do IRPJ") == centavos("100000,00")
        assert _valor(irpj, "(+) ADIÇÕES") == centavos("10000,00")
        assert _valor(irpj, "(-) EXCLUSÕES") == centavos("5000,00")

    def test_o_imposto_e_o_adicional_vem_do_n630_pela_descricao(self, irpj):
        """O código da linha muda a cada leiaute; a descrição é estável."""
        assert _valor(irpj, "Alíquota de 15%") == centavos("13500,00")
        assert _valor(irpj, "Adicional") == centavos("3000,00")
        assert _valor(irpj, "IMPOSTO DE RENDA A PAGAR") == centavos("16000,00")

    def test_a_deducao_e_a_linha_que_comeca_com_menos(self, irpj):
        assert _valor(irpj, "(-) DEDUÇÕES") == centavos("500,00")

    def test_a_compensacao_derivada_repete_a_de_periodos_anteriores(self, irpj):
        """**Comportamento suspeito, fixado de propósito.**

        Quando o e-Lalur não traz linha de "compensação do próprio período", a
        regra portada deduz esse valor da diferença entre o lucro real antes e
        depois da compensação. Só que essa diferença é a compensação **inteira**
        — inclusive a de períodos anteriores. Nesta amostra os R$ 15.000,00 de
        prejuízo anterior aparecem nas duas linhas.

        A regra veio do projeto de origem e **não foi validada contra gabarito**
        — o IRPJ/CSLL de referência é de outra empresa e a comparação ficou
        pendente lá também. Não a mudei sem evidência: mudar uma regra fiscal
        por raciocínio, sem arquivo que confirme, é como o erro da natureza do
        crédito nasceu. Este teste existe para que a correção, quando vier, seja
        deliberada — e para que a suspeita não se perca.
        """
        assert _valor(irpj, "Compensação de Prejuízos Anteriores") == centavos("15000,00")
        assert _valor(irpj, "Compensação de Prejuízo do Período") == centavos("15000,00")
        # e o lucro real continua o que a própria ECF declarou
        assert _valor(irpj, "=  LUCRO REAL") == centavos("90000,00")

    def test_o_saldo_da_parte_b_soma_devedor_com_credor(self, irpj):
        assert _valor(irpj, "Saldo das Contas da Parte B") == centavos("18000,00")

    def test_as_linhas_de_fonte_externa_ficam_em_branco_e_marcadas(self, irpj):
        """DCTF e e-CAC não são lidos: valor zero passaria por declarado zero."""
        externas = [l for q in irpj.quadros for l in q.linhas if l.externo]

        assert {l.rotulo.strip() for l in externas} == {
            "Valor do Débito Apurado na DCTF", "e-CAC - Pagamentos Consolidados"}
        assert all(v is None for l in externas for v in l.valores.values())


class TestOsQuadrosDeCsll:
    def test_a_csll_sai_do_e_lacs_e_do_n670(self, apuracao):
        csll = montar_relatorio_irpj_csll([apuracao], "CSLL")

        assert csll.tributo == "CSLL"
        assert _valor(csll, "Contribuição 9%") == centavos("9720,00")
        assert _valor(csll, "CSLL A PAGAR") == centavos("9000,00")
        assert _valor(csll, "(-) DEDUÇÕES") == centavos("720,00")

    def test_a_parte_b_do_irpj_nao_entra_na_csll(self, apuracao):
        """As contas são separadas pelo tributo: I não soma em C."""
        csll = montar_relatorio_irpj_csll([apuracao], "CSLL")

        assert _valor(csll, "Saldo das Contas da Parte B") == 0

    def test_tributo_que_nao_existe_e_recusado(self, apuracao):
        with pytest.raises(ValueError):
            montar_relatorio_irpj_csll([apuracao], "PIS")


class TestAMontagem:
    def test_uma_ecf_vira_os_dois_relatorios(self, arquivo):
        apuracoes, avisos = ler_ecfs([arquivo])
        irpj, csll = montar_irpj_csll(apuracoes, avisos)

        assert avisos == []
        assert (irpj.tributo, csll.tributo) == ("IRPJ", "CSLL")
        assert irpj.periodos == csll.periodos

    def test_arquivo_ilegivel_vira_aviso_e_nao_derruba(self, arquivo, tmp_path):
        torto = tmp_path / "nao_e_sped.txt"
        torto.write_bytes(b"isto nao e um sped\n")

        apuracoes, avisos = ler_ecfs([arquivo, str(torto)])

        assert len(apuracoes) == 1
        assert any("nao_e_sped.txt" in a for a in avisos)

    def test_sem_ecf_nenhuma_nao_monta_relatorio(self):
        assert montar_irpj_csll([]) == []
