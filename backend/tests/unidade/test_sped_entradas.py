"""A Consulta de Entradas (037): os oito ramos de documento de entrada.

A amostra tem **matriz e filial**, e é de propósito: o bug que o projeto de
origem achou contra arquivo real era o documento do bloco D de uma filial sair
com o CNPJ da matriz, porque o bloco D tem abridor próprio (D010) e o código
usava o último C010 visto. Três CNPJ correntes convivem no arquivo, e o teste
cobra os três.
"""

import pytest

from cat.infraestrutura.sped.entradas import (
    RAMO_C100,
    RAMO_C190,
    RAMO_C500,
    RAMO_D100,
    RAMO_D500,
    RAMO_F100,
    RAMO_F120,
    RAMO_F130,
    colunas_da_entrada,
    entradas,
)

MATRIZ = "11222333000181"
FILIAL = "11222333000262"

EFD = """|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|3550308||00|2|
|0140|001|MATRIZ|11222333000181|SP|111|3550308||||
|0140|002|FILIAL CURITIBA|11222333000262|PR|222|4106902||||
|0150|F01|FORNECEDOR ALFA|1058|99888777000166||111|3304557||||||
|0200|SKU1|XAMPU 350ML||||00|33051000||||||
|0500|01062021|01|A|3|3.1.1|COMPRAS DE MERCADORIA||
|0500|01062021|01|A|3|3.2.1|ENERGIA ELETRICA||
|C010|11222333000181|0|
|C100|0|1|F01|55|00|1|1001|35210611222333000181550010000010011000010017|01062021|02062021|1000,00||10,00||900,00||50,00|||900,00|162,00||||||||
|C170|1|SKU1|XAMPU GRANDE|10,000|UN|500,00|5,00|0|000|1102|N01|500,00|18,00|90,00||||0||||||50|500,00|1,6500|||8,25|50|500,00|7,6000|||38,00|3.1.1|
|C100|1|0|F01|55|||9001||03062021||||||||||||||||||||
|C170|1|SKU1|SAIDA NAO ENTRA|||700,00||||5102|||||||||||||||||||||||||||
|C500|F01|06|00|A||2001|05062021|06062021|300,00|54,00||||3512106|
|C501|50|300,00|09|300,00|1,6500|4,95|3.2.1|
|C505|50|300,00|09|300,00|7,6000|22,80|3.2.1|
|C190|55|01062021|30062021|SKU1|33051000||2000,00|
|C191|99888777000166|50|1102|1200,00||1200,00|1,6500|||19,80|3.1.1|
|C191|99888777000166|50|1202|800,00||800,00|1,6500|||13,20|3.1.1|
|C195|99888777000166|50|1102|1200,00||1200,00|7,6000|||91,20|3.1.1|
|C195|99888777000166|50|1202|800,00||800,00|7,6000|||60,80|3.1.1|
|D010|11222333000262|
|D100|0|0|F01|57|00|1||3001|41210611222333000262570010000030011000030015|10062021|11062021|||150,00|||150,00||27,00||||
|D101||150,00|50|09|150,00|1,6500|2,48|3.2.1|
|D105||150,00|50|09|150,00|7,6000|11,40|3.2.1|
|D500|0|0|F01|21|00|A||4001|15062021|16062021|80,00||80,00|||||14,40||||
|D501|50|80,00|09|80,00|1,6500|1,32|3.2.1|
|D505|50|80,00|09|80,00|7,6000|6,08|3.2.1|
|F010|11222333000181|
|F100|0|F01|SKU1|20062021|250,00|50|250,00|1,6500|4,13|50|250,00|7,6000|19,00|09||3.1.1||ALUGUEL|
|F100|1|F01|SKU1|21062021|999,00|||||||||||||SAIDA NAO ENTRA|
|F120|09||||1000,00|0,00|50|1000,00|1,6500|16,50|50|1000,00|7,6000|76,00|3.1.1||MAQUINA DE CORTE|
|F130|09|BEM01||||5000,00|0,00|5000,00||50|5000,00|1,6500|82,50|50|5000,00|7,6000|380,00|3.1.1||VEICULO|
|9999|33|
"""


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


@pytest.fixture
def linhas(arquivo):
    return list(entradas(arquivo, "cp1252"))


class TestOsOitoRamos:
    def test_todos_os_ramos_aparecem(self, linhas):
        ramos = {l.registros for l in linhas}
        assert ramos == {RAMO_C100, RAMO_C500, RAMO_C190, RAMO_D100,
                         RAMO_D500, RAMO_F100, RAMO_F120, RAMO_F130}

    def test_so_entrada_entra(self, linhas):
        """C100 e F100 de saída (IND_OPER=1) ficam de fora."""
        assert all("SAIDA NAO ENTRA" not in (l.descricao_complementar or "")
                   for l in linhas)
        assert [l.cfop for l in linhas if l.registros == RAMO_C100] == ["1102"]
        # o F100 de saída sumiu: sobra um só
        assert len([l for l in linhas if l.registros == RAMO_F100]) == 1


class TestOBlocoDTemEstabelecimentoProprio:
    def test_o_documento_da_filial_nao_sai_com_o_cnpj_da_matriz(self, linhas):
        """O bug real que a validação do projeto de origem achou."""
        do_bloco_c = [l for l in linhas if l.registros in (RAMO_C100, RAMO_C500, RAMO_C190)]
        do_bloco_d = [l for l in linhas if l.registros in (RAMO_D100, RAMO_D500)]

        assert {l.cnpj for l in do_bloco_c} == {MATRIZ}
        assert {l.cnpj for l in do_bloco_d} == {FILIAL}

    def test_o_bloco_f_segue_o_f010(self, linhas):
        do_bloco_f = [l for l in linhas if l.registros in (RAMO_F100, RAMO_F120, RAMO_F130)]
        assert {l.cnpj for l in do_bloco_f} == {MATRIZ}

    def test_a_uf_do_estabelecimento_acompanha_o_bloco(self, linhas):
        transporte = next(l for l in linhas if l.registros == RAMO_D100)
        nota = next(l for l in linhas if l.registros == RAMO_C100)
        # o participante é do RJ (cód. 3304557); os estabelecimentos, SP e PR
        assert nota.uf_origem_destino == "RJ/SP"
        assert transporte.uf_origem_destino == "RJ/PR"


class TestONotaFiscal:
    def test_a_linha_junta_nota_item_e_cadastro(self, linhas):
        nota = next(l for l in linhas if l.registros == RAMO_C100)

        assert nota.numero_do_documento == "1001"
        assert nota.chave.startswith("352106112223330001815500100000100")
        assert nota.data_do_documento == "01/06/2021"
        assert nota.data_de_entrada == "02/06/2021"
        assert nota.nome_do_participante == "FORNECEDOR ALFA"
        assert nota.cnpj_do_participante == "99888777000166"
        # a descrição vem do 0200; a complementar, do próprio item
        assert nota.descricao_do_item == "XAMPU 350ML"
        assert nota.descricao_complementar == "XAMPU GRANDE"
        assert nota.ncm == "33051000"
        assert nota.nome_da_conta == "COMPRAS DE MERCADORIA"

    def test_o_periodo_e_o_primeiro_dia_do_mes(self, linhas):
        assert {l.periodo for l in linhas} == {"01/06/2021"}

    def test_os_numeros_saem_no_padrao_brasileiro(self, linhas):
        nota = next(l for l in linhas if l.registros == RAMO_C100)
        assert nota.valor_do_documento == "1000,00"
        assert nota.frete == "50,00"
        assert nota.quantidade == "10,00000"
        assert nota.aliquota_do_pis == "1,6500"
        assert nota.descricao_do_cfop  # a tabela de CFOP responde

    def test_campo_vazio_continua_vazio_e_nao_vira_zero(self, linhas):
        nota = next(l for l in linhas if l.registros == RAMO_C100)
        assert nota.icms_st == ""
        assert nota.ipi == ""


class TestAConsolidacao:
    def test_pis_e_cofins_casam_pelo_cfop(self, linhas):
        consolidadas = [l for l in linhas if l.registros == RAMO_C190]

        assert len(consolidadas) == 2
        assert [l.cfop for l in consolidadas] == ["1102", "1202"]
        assert [l.pis for l in consolidadas] == ["19,80", "13,20"]
        assert [l.cofins for l in consolidadas] == ["91,20", "60,80"]

    def test_o_participante_e_o_cnpj_direto_sem_cadastro(self, linhas):
        """Confirmado em dado real: o COD_PART do C191 não referencia o 0150."""
        consolidada = next(l for l in linhas if l.registros == RAMO_C190)
        assert consolidada.cnpj_do_participante == "99888777000166"
        assert consolidada.nome_do_participante == ""
        # sem participante no cadastro, só a UF do estabelecimento é conhecida
        assert consolidada.uf_origem_destino == "SP"

    def test_o_ultimo_grupo_sai_mesmo_sem_outro_c190_depois(self, linhas):
        assert len([l for l in linhas if l.registros == RAMO_C190]) == 2


class TestAsHeuristicas:
    def test_a_natureza_e_deduzida_do_tipo_do_item_so_no_codigo_00(self, linhas):
        nota = next(l for l in linhas if l.registros == RAMO_C100)
        assert nota.tipo_do_item.startswith("00")
        assert nota.natureza_do_credito.startswith("01 -")

    def test_quando_o_registro_traz_a_natureza_ela_nao_e_deduzida(self, linhas):
        energia = next(l for l in linhas if l.registros == RAMO_C500)
        assert energia.natureza_do_credito.startswith("09")

    def test_o_debito_credito_e_hipotese_marcada(self, linhas):
        nota = next(l for l in linhas if l.registros == RAMO_C100)
        assert nota.debito_ou_credito == "C"      # CST 50 com PIS > 0
        consolidada = next(l for l in linhas if l.registros == RAMO_C190)
        assert consolidada.debito_ou_credito == "C"


class TestOsRamosRaros:
    def test_o_ativo_imobilizado_nao_tem_participante(self, linhas):
        depreciacao = next(l for l in linhas if l.registros == RAMO_F120)
        aquisicao = next(l for l in linhas if l.registros == RAMO_F130)

        assert depreciacao.nome_do_participante == ""
        assert depreciacao.descricao_complementar == "MAQUINA DE CORTE"
        assert aquisicao.descricao_complementar == "VEICULO"
        assert aquisicao.codigo_do_item == "BEM01"

    def test_a_comunicacao_traz_frete_zerado_por_nao_ter_mercadoria(self, linhas):
        comunicacao = next(l for l in linhas if l.registros == RAMO_D500)
        assert comunicacao.frete == "0,00"


class TestContrato:
    def test_as_colunas_sao_conhecidas_antes_de_ler(self, linhas):
        colunas = colunas_da_entrada()
        assert len(colunas) == 51
        assert set(linhas[0].como_dicionario()) == set(colunas)

    def test_arquivo_sem_entrada_nenhuma_nao_quebra(self, tmp_path):
        vazio = tmp_path / "so_cabecalho.txt"
        vazio.write_bytes(
            "|0000|006|0|||01062021|30062021|X|11222333000181|SP|".encode("cp1252"))
        assert list(entradas(str(vazio), "cp1252")) == []
