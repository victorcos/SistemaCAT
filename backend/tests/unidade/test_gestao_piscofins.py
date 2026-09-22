"""A Gestão de PIS/COFINS: ler a EFD uma vez e montar os 36 quadros.

A amostra é uma EFD-Contribuições reduzida de uma competência, com o que separa
um quadro certo de um quadro plausível:

* uma **saída com incidência** (CST 01) e uma **sem** (CST 06);
* duas **entradas com crédito** (CST 50), uma de CFOP que a tabela conhece e
  outra de CFOP que ela não conhece — a segunda fica fora dos quadros de
  crédito e vira aviso, como no MA;
* os registros de apuração do bloco M e o controle de créditos do 1100.

As linhas são montadas **pelo nome do campo**, nunca contando pipes. Para os
registros de documento o nome vem de `sped/registros.py`, que é o leiaute desta
casa — então o teste também confere que os índices do leiaute da gestão, que
vieram do projeto de origem, concordam com ele.
"""

import pytest

from cat.infraestrutura.gestao.agregador import agregar_efd
from cat.infraestrutura.gestao.leiaute import CAMPOS, CAMPOS_AJUSTE, campos_m210
from cat.infraestrutura.gestao.numeros import centavos, credito_recalculado
from cat.infraestrutura.gestao.montagem import ler, montar, selecionar_por_competencia
from cat.infraestrutura.gestao.quadros import montar_relatorio_piscofins
from cat.infraestrutura.sped.registros import nomes_dos_campos, posicao_do_campo

CNPJ = "11222333000181"

CABECALHO = (f"|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|{CNPJ}|SP"
             "|3550308||00|2|")


def _por_nome(registro: str, nomes: tuple[str, ...] | list[str], **valores: str) -> str:
    """Uma linha do SPED montada pelo nome do campo."""
    campos = [""] * len(nomes)
    campos[0] = registro
    indice = {n: i for i, n in enumerate(nomes)}
    for nome, valor in valores.items():
        assert nome in indice, f"{registro} não tem campo {nome}"
        campos[indice[nome]] = valor
    return "|" + "|".join(campos) + "|"


def _documento(registro: str, **valores: str) -> str:
    """C100/C170 pelo leiaute desta casa — o mesmo que a gestão indexa."""
    campos = [""] * len(nomes_dos_campos(registro))
    campos[0] = registro
    for nome, valor in valores.items():
        campos[posicao_do_campo(registro, nome)] = valor
    return "|" + "|".join(campos) + "|"


def _apuracao(registro: str, **valores: str) -> str:
    return _por_nome(registro, CAMPOS[registro], **valores)


# o M210/M610 mudou de leiaute em 2019; a amostra usa o de agora
CAMPOS_M210 = campos_m210(99)


def _detalhe(registro: str, **valores: str) -> str:
    return _por_nome(registro, CAMPOS_M210, **valores)


EFD = "\n".join([
    CABECALHO,
    _por_nome("0110", CAMPOS["0110"], COD_INC_TRIB="1", IND_APRO_CRED="1"),
    _por_nome("0111", CAMPOS["0111"], REC_BRU_NCUM_TRIB_MI="1000,00",
              REC_BRU_TOTAL="1000,00"),

    # --- a saída com incidência: base 1.000, PIS 16,50 e COFINS 76,00
    _documento("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C09", NUM_DOC="1"),
    _documento("C170", NUM_ITEM="1", COD_ITEM="SKU1", CFOP="5102", VL_ITEM="1000,00",
               CST_PIS="01", VL_BC_PIS="1000,00", ALIQ_PIS_PERC="1,6500", VL_PIS="16,50",
               CST_COFINS="01", VL_BC_COFINS="1000,00", ALIQ_COFINS_PERC="7,6000",
               VL_COFINS="76,00"),

    # --- a saída sem incidência: entra pelo VL_ITEM, não pela base
    _documento("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C09", NUM_DOC="2"),
    _documento("C170", NUM_ITEM="1", COD_ITEM="SKU2", CFOP="5102", VL_ITEM="400,00",
               CST_PIS="06", CST_COFINS="06"),

    # --- a entrada com crédito, CFOP 1102 -> natureza 01
    _documento("C100", IND_OPER="0", IND_EMIT="0", COD_PART="F01", NUM_DOC="3"),
    _documento("C170", NUM_ITEM="1", COD_ITEM="SKU1", CFOP="1102", VL_ITEM="500,00",
               CST_PIS="50", VL_BC_PIS="500,00", ALIQ_PIS_PERC="1,6500", VL_PIS="8,25",
               CST_COFINS="50", VL_BC_COFINS="500,00", ALIQ_COFINS_PERC="7,6000",
               VL_COFINS="38,00"),

    # --- a entrada de CFOP que a tabela não conhece: fica fora e vira aviso
    _documento("C100", IND_OPER="0", IND_EMIT="0", COD_PART="F01", NUM_DOC="4"),
    _documento("C170", NUM_ITEM="1", COD_ITEM="SKU3", CFOP="1253", VL_ITEM="300,00",
               CST_PIS="50", VL_BC_PIS="300,00", ALIQ_PIS_PERC="1,6500", VL_PIS="4,95",
               CST_COFINS="50", VL_BC_COFINS="300,00", ALIQ_COFINS_PERC="7,6000",
               VL_COFINS="22,80"),

    # --- a apuração do PIS
    _apuracao("M100", COD_CRED="101", VL_BC="500,00", ALIQ="1,6500", VL_CRED="8,25",
              VL_CRED_DISP="8,25", SLD_CRED="0,00"),
    _apuracao("M105", NAT_BC_CRED="01", CST="50", VL_BC_TOT="500,00", VL_BC="500,00"),
    _por_nome("M110", CAMPOS_AJUSTE, IND_AJ="0", VL_AJ="1,00", COD_AJ="01"),
    _detalhe("M210", COD_CONT="01", VL_REC_BRT="1000,00", VL_BC_CONT="1000,00",
              VL_BC_CONT_AJUS="1000,00", ALIQ="1,6500", VL_CONT_APUR="16,50",
              VL_CONT_PER="16,50"),
    _apuracao("M200", VL_TOT_CONT_NC_PER="16,50", VL_TOT_CRED_DESC="8,25",
              VL_CONT_NC_REC="8,25", VL_TOT_CONT_REC="8,25"),
    _apuracao("1100", PER_APU_CRED="062021", COD_CRED="101", VL_CRED_APU="8,25",
              VL_TOT_CRED_APU="8,25", SD_CRED_DISP_EFD="8,25", VL_CRED_DESC_EFD="8,25",
              SLD_CRED_FIM="0,00"),

    # --- a apuração da COFINS, espelho campo a campo
    _apuracao("M500", COD_CRED="101", VL_BC="500,00", ALIQ="7,6000", VL_CRED="38,00",
              VL_CRED_DISP="38,00", SLD_CRED="0,00"),
    _apuracao("M505", NAT_BC_CRED="01", CST="50", VL_BC_TOT="500,00", VL_BC="500,00"),
    _detalhe("M610", COD_CONT="01", VL_REC_BRT="1000,00", VL_BC_CONT="1000,00",
              VL_BC_CONT_AJUS="1000,00", ALIQ="7,6000", VL_CONT_APUR="76,00",
              VL_CONT_PER="76,00"),
    _apuracao("M600", VL_TOT_CONT_NC_PER="76,00", VL_TOT_CRED_DESC="38,00",
              VL_CONT_NC_REC="38,00", VL_TOT_CONT_REC="38,00"),
    _apuracao("1500", PER_APU_CRED="062021", COD_CRED="101", VL_CRED_APU="38,00",
              VL_TOT_CRED_APU="38,00", SD_CRED_DISP_EFD="38,00", VL_CRED_DESC_EFD="38,00",
              SLD_CRED_FIM="0,00"),
    "|9999|24|",
]) + "\n"


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "efd_contribuicoes_062021.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


@pytest.fixture
def apuracao(arquivo):
    return agregar_efd(arquivo)


@pytest.fixture
def pis(apuracao):
    return montar_relatorio_piscofins([apuracao], "PIS")


def _quadro(relatorio, numero: str):
    return next(q for q in relatorio.quadros if q.numero == numero)


def _valor(relatorio, numero: str, rotulo_contem: str, periodo="2021-06") -> int:
    linha = next(l for l in _quadro(relatorio, numero).linhas if rotulo_contem in l.rotulo)
    return linha.valores[periodo]


class TestALeituraDoArquivo:
    def test_a_empresa_e_o_periodo_vem_do_leitor_do_dominio(self, apuracao):
        """O 0000 não é lido por posição fixa aqui — já mordeu duas vezes."""
        assert apuracao.cnpj == CNPJ
        assert apuracao.razao_social == "COMERCIO DO TESTE LTDA"
        assert apuracao.periodo == "2021-06"
        assert (apuracao.dt_ini, apuracao.dt_fin) == ("01062021", "30062021")
        assert apuracao.tipo_escrit == "0"

    def test_os_itens_sao_agregados_por_chave_e_nao_linha_a_linha(self, apuracao):
        """Um arquivo real tem milhões de C170; o que a gestão guarda são grupos."""
        chaves = {(t, r, op, cst, cfop) for (t, r, op, cst, cfop, _, _) in apuracao.documentos}

        assert ("PIS", "C170", "S", "01", "5102") in chaves
        assert ("PIS", "C170", "E", "50", "1102") in chaves
        assert ("COFINS", "C170", "E", "50", "1253") in chaves
        # dois tributos x quatro grupos de item
        assert len(apuracao.documentos) == 8

    def test_o_ajuste_entra_somado_por_codigo(self, apuracao):
        assert apuracao.ajustes[("M110", "0", "01")] == centavos("1,00")

    def test_a_apuracao_guarda_os_registros_do_bloco_m_inteiros(self, apuracao):
        assert len(apuracao.registros["M200"]) == 1
        assert len(apuracao.registros["M610"]) == 1
        assert apuracao.contagens["C170"] == 4

    def test_nada_foi_descartado_em_silencio(self, apuracao):
        assert apuracao.descartes == {}


class TestOsQuadros:
    def test_sao_trinta_e_seis(self, pis):
        assert len(pis.quadros) == 36
        assert pis.tributo == "PIS"
        assert pis.cnpj == CNPJ
        assert pis.periodos == ["2021-06"]

    def test_saida_com_incidencia_entra_pela_base(self, pis):
        """CST 01: o quadro 30 soma VL_BC, não VL_ITEM."""
        assert _valor(pis, "30", "01") == centavos("1000,00")

    def test_saida_sem_incidencia_entra_pelo_valor_do_item(self, pis):
        """CST 06 não tem base: o quadro 21 soma o VL_ITEM."""
        assert _valor(pis, "21", "C100/C170") == centavos("400,00")

    def test_entrada_com_credito_so_conta_com_natureza_conhecida(self, pis):
        """A de CFOP 1253 fica de fora, como no MA — a de 1102 entra."""
        assert _valor(pis, "31", "50") == centavos("500,00")

    def test_o_credito_e_recalculado_por_grupo_nao_somado_do_arquivo(self, pis):
        """O MA não soma o VL_PIS da linha: refaz base x alíquota por grupo."""
        esperado = credito_recalculado(centavos("500,00"), 16500)

        assert esperado == centavos("8,25")
        assert _valor(pis, "32", "Aquisição de bens para revenda") == esperado

    def test_a_natureza_do_m105_vem_do_proprio_registro(self, pis):
        assert _valor(pis, "9", "Aquisição de bens para revenda") == centavos("500,00")

    def test_o_quadro_35_abre_a_base_antes_e_depois_do_ajuste(self, pis):
        assert _valor(pis, "35", "Antes de Ajustes") == centavos("1000,00")
        assert _valor(pis, "35", "( = )") == centavos("1000,00")

    def test_o_cofins_espelha_o_pis_com_a_propria_aliquota(self, apuracao):
        cofins = montar_relatorio_piscofins([apuracao], "COFINS")

        assert len(cofins.quadros) == 36
        assert _valor(cofins, "30", "01") == centavos("1000,00")
        assert _valor(cofins, "32", "Aquisição de bens para revenda") == centavos("38,00")

    def test_tributo_que_nao_existe_e_recusado(self, apuracao):
        with pytest.raises(ValueError, match="tributo"):
            montar_relatorio_piscofins([apuracao], "ICMS")

    def test_sem_apuracao_nenhuma_nao_monta_relatorio_vazio(self):
        with pytest.raises(ValueError, match="nenhuma apuração"):
            montar_relatorio_piscofins([], "PIS")


class TestOsAvisos:
    def test_entrada_de_cfop_sem_natureza_vira_aviso_com_o_valor(self, pis):
        """Ficar de fora calado seria o defeito: o valor sumiria do relatório."""
        aviso = next(a for a in pis.avisos if "1253" in a)

        assert "C170" in aviso
        assert "300" in aviso


class TestAMontagem:
    """Quais arquivos entram — o que muda número sem mudar regra nenhuma."""

    @staticmethod
    def _gravar(tmp_path, nome: str, tipo_escrit: str, competencia: str) -> str:
        """A mesma EFD, com outra competência e outro tipo de escrituração."""
        cabecalho = (f"|0000|006|{tipo_escrit}|||01{competencia}|30{competencia}"
                     f"|COMERCIO DO TESTE LTDA|{CNPJ}|SP|3550308||00|2|")
        corpo = EFD.replace(CABECALHO, cabecalho, 1)
        caminho = tmp_path / nome
        caminho.write_bytes(corpo.encode("cp1252"))
        return str(caminho)

    def test_a_retificadora_vence_a_original_da_mesma_competencia(self, tmp_path):
        original = self._gravar(tmp_path, "original.txt", "0", "062021")
        retificadora = self._gravar(tmp_path, "retificadora.txt", "1", "062021")

        apuracoes, _ = ler([original, retificadora])
        escolhidas, avisos = selecionar_por_competencia(apuracoes)

        assert [a.arquivo for a in escolhidas] == [retificadora]
        assert len(avisos) == 1
        # o preterido é nomeado: sumir calado esconderia de onde veio o número
        assert "original.txt" in avisos[0] and "retificadora.txt" in avisos[0]

    def test_competencias_diferentes_convivem_e_viram_colunas(self, tmp_path):
        junho = self._gravar(tmp_path, "junho.txt", "0", "062021")
        julho = self._gravar(tmp_path, "julho.txt", "0", "072021")

        apuracoes, _ = ler([junho, julho])
        pis, cofins = montar(apuracoes)

        assert pis.periodos == ["2021-06", "2021-07"]
        assert (pis.tributo, cofins.tributo) == ("PIS", "COFINS")
        assert _valor(pis, "30", "01", "2021-07") == centavos("1000,00")

    def test_arquivo_ilegivel_vira_aviso_e_nao_derruba_a_rodada(self, tmp_path, arquivo):
        torto = tmp_path / "nao_e_sped.txt"
        torto.write_bytes(b"isto nao e um sped\n")

        apuracoes, avisos = ler([arquivo, str(torto)])

        assert len(apuracoes) == 1
        assert any("nao_e_sped.txt" in a for a in avisos)

    def test_sem_arquivo_nenhum_nao_monta_relatorio(self):
        assert montar([]) == []
