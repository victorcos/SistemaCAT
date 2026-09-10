"""Leitura do registro 0000 do SPED.

As linhas de EFD Contribuições e ECD abaixo foram copiadas de arquivos reais
desta casa. A de EFD ICMS/IPI foi montada pelo leiaute oficial e **ainda não
foi conferida contra um arquivo real** — quando aparecer um, trocar por ele.
"""

from datetime import date

import pytest

from cat.dominio.sped.cabecalho import (
    ArquivoNaoReconhecido,
    TipoSped,
    detectar_tipo,
    ler_cabecalho,
    separar,
)

# real, do Center Box (EFD Contribuições)
CONTRIBUICOES = (
    "|0000|006|0|||01062021|30062021|CENTER BOX SUPERMERCADOS LTDA"
    "|11497712000184|CE|2304400||00|2|"
)

# real, arquivo de ECD desta casa — note que traz dois campos a mais antes das
# datas em relação ao leiaute publicado. Foi este arquivo que motivou ler por
# âncora em vez de posição fixa.
ECD = (
    "|0000|LECD|0||01012025|31012025|EMPRESA TESTE LTDA"
    "|12345678000199|SP|3550308||||"
)

# montada pelo leiaute oficial da EFD ICMS/IPI, com dados dos Irmãos Boa
ICMS_IPI = (
    "|0000|018|0|01012025|31012025|IRMAOS BOA LTDA|50948371000178||SP"
    "|407048962113|3550308|||A|0|"
)

# filial, para provar que matriz não é chute
ICMS_IPI_FILIAL = (
    "|0000|018|0|01012025|31012025|IRMAOS BOA LTDA|50948371000259||SP"
    "|407048962114|3550308|||A|0|"
)


class TestDeteccaoDeTipo:
    def test_icms_ipi(self):
        assert detectar_tipo(separar(ICMS_IPI)) is TipoSped.EFD_ICMS_IPI

    def test_contribuicoes(self):
        assert detectar_tipo(separar(CONTRIBUICOES)) is TipoSped.EFD_CONTRIBUICOES

    def test_ecd(self):
        assert detectar_tipo(separar(ECD)) is TipoSped.ECD

    def test_so_o_icms_ipi_serve_para_a_cat(self):
        assert TipoSped.EFD_ICMS_IPI.serve_para_cat
        assert not TipoSped.EFD_CONTRIBUICOES.serve_para_cat
        assert not TipoSped.ECD.serve_para_cat


class TestIcmsIpi:
    def test_le_a_empresa(self):
        c = ler_cabecalho(ICMS_IPI)
        assert c.nome == "IRMAOS BOA LTDA"
        assert c.cnpj.valor == "50948371000178"
        assert c.e_matriz
        assert c.uf == "SP"
        assert c.inscricao_estadual == "407048962113"
        assert c.codigo_municipio == "3550308"

    def test_le_o_periodo(self):
        c = ler_cabecalho(ICMS_IPI)
        assert c.inicio == date(2025, 1, 1)
        assert c.fim == date(2025, 1, 31)
        assert c.competencia == "01/2025"
        assert c.periodo_fechado_no_mes

    def test_reconhece_filial(self):
        c = ler_cabecalho(ICMS_IPI_FILIAL)
        assert not c.e_matriz
        assert c.cnpj.matriz().valor == "50948371000178"


class TestContribuicoes:
    def test_le_arquivo_real(self):
        c = ler_cabecalho(CONTRIBUICOES)
        assert c.nome == "CENTER BOX SUPERMERCADOS LTDA"
        assert c.cnpj.valor == "11497712000184"
        assert c.e_matriz
        assert c.uf == "CE"
        assert c.competencia == "06/2021"

    def test_nao_confunde_municipio_com_inscricao_estadual(self):
        """As Contribuições não têm IE: depois da UF vem o código do município.
        Sem esta distinção, o município entrava no sistema como IE."""
        c = ler_cabecalho(CONTRIBUICOES)
        assert c.inscricao_estadual == ""
        assert c.codigo_municipio == "2304400"


class TestEcd:
    def test_le_mesmo_fora_do_leiaute_publicado(self):
        """Este arquivo traz campos a mais antes das datas. A âncora aguenta."""
        c = ler_cabecalho(ECD)
        assert c.nome == "EMPRESA TESTE LTDA"
        assert c.uf == "SP"
        assert c.inicio == date(2025, 1, 1)

    def test_cnpj_invalido_nao_derruba_a_leitura(self):
        """O resto do cabeçalho ainda serve, e quem confere na tela corrige."""
        c = ler_cabecalho(ECD)
        assert c.cnpj is None
        assert not c.e_matriz


class TestEntradaRuim:
    def test_linha_que_nao_e_sped(self):
        with pytest.raises(ArquivoNaoReconhecido, match="formato SPED"):
            ler_cabecalho("isto nao e um sped")

    def test_primeira_linha_nao_e_o_0000(self):
        with pytest.raises(ArquivoNaoReconhecido, match="0000"):
            ler_cabecalho("|C100|0|1|blah|blah|blah|blah|blah|")

    def test_sem_par_de_datas(self):
        """A detecção de tipo pega isto antes da âncora, e tudo bem: o que
        importa é falhar alto dizendo que faltou a data."""
        with pytest.raises(ArquivoNaoReconhecido, match="data"):
            ler_cabecalho("|0000|018|0|xx|yy|NOME|50948371000178||SP|1|2|||A|0|")

    def test_ancora_falha_quando_o_tipo_e_reconhecido_mas_faltam_datas(self):
        with pytest.raises(ArquivoNaoReconhecido, match="par de datas"):
            ler_cabecalho("|0000|LECD|0||xx|yy|NOME|50948371000178|SP|3550308||||")

    def test_sem_razao_social(self):
        with pytest.raises(ArquivoNaoReconhecido, match="razão social"):
            ler_cabecalho("|0000|018|0|01012025|31012025||50948371000178||SP|1|2|||A|0|")

    def test_data_inexistente(self):
        with pytest.raises(ArquivoNaoReconhecido):
            ler_cabecalho(
                "|0000|018|0|32012025|31012025|NOME|50948371000178||SP|1|2|||A|0|"
            )


class TestPeriodo:
    def test_periodo_que_cruza_mes_e_sinalizado(self):
        """Escrituração fora do padrão merece atenção antes de virar
        competência no sistema."""
        linha = (
            "|0000|018|0|15012025|14022025|IRMAOS BOA LTDA|50948371000178||SP"
            "|407048962113|3550308|||A|0|"
        )
        assert not ler_cabecalho(linha).periodo_fechado_no_mes
