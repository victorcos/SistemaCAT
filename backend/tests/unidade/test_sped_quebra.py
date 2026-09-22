"""A quebra de SPED: indexar uma vez, extrair sob demanda.

A amostra abaixo é uma EFD-Contribuições reduzida, com a hierarquia inteira que
o join do item percorre — duas mercadorias, dois participantes, duas notas e
quatro itens. Pequena o bastante para caber na cabeça, completa o bastante para
que qualquer erro de nível apareça.
"""

import os

import pytest

from cat.infraestrutura.sped.extracao import (
    TRADUZIDAS,
    RegistroNaoIndexado,
    _competencia,
    colunas_do_item,
    itens_completos,
    registros,
)
from cat.infraestrutura.sped.indice import (
    VERSAO_DO_ESQUEMA,
    buscar,
    guardar,
    impressao_de,
    indexar,
    indice_de,
)
from cat.infraestrutura.sped.leitor import campos, codificacao_de, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos, posicao_do_campo

EFD = """|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|3550308||00|2|
|0140|001|MATRIZ DO TESTE|11222333000181|SP|111222333|3550308||||
|0150|F01|FORNECEDOR ALFA|1058|99888777000166||111||RUA A|10||CENTRO|
|0150|C09|CLIENTE BETA|1058|55666777000122||222||RUA B|20||CENTRO|
|0200|SKU1|XAMPU 350ML||||00|33051000|||||
|0200|SKU2|SABONETE 90G||||00|34011190|||||
|0400|N01|VENDA NO ESTADO|
|C010|11222333000181|0|
|C100|0|1|F01|55|00|1|1001|35210611222333000181550010000010011000010017|01062021|01062021|1000,00|0|0,00|0,00|900,00|9||||900,00|162,00|||||||
|C170|1|SKU1|XAMPU 350ML|10,000|UN|500,00|0,00|0|000|1102|N01|500,00|18,00|90,00||||0||||||50|500,00|1,6500|||8,25|50|500,00|7,6000|||38,00|3.1.1|
|C170|2|SKU2|SABONETE 90G|20,000|UN|400,00|0,00|0|000|1102|N01|400,00|18,00|72,00||||0||||||50|400,00|1,6500|||6,60|50|400,00|7,6000|||30,40|3.1.1|
|C100|1|0|C09|55|00|1|2002|35210611222333000181550010000020021000020024|15062021|15062021|2000,00|0|0,00|0,00|1800,00|9||||1800,00|324,00|||||||
|C170|1|SKU1|XAMPU 350ML|30,000|UN|1500,00|0,00|0|000|5102|N01|1500,00|18,00|270,00||||0||||||01|1500,00|1,6500|||24,75|01|1500,00|7,6000|||114,00|3.1.1|
|C170|2|SKU2|SABONETE 90G|10,000|UN|300,00|0,00|0|000|5102|N01|300,00|18,00|54,00||||0||||||01|300,00|1,6500|||4,95|01|300,00|7,6000|||22,80|3.1.1|
|H010|SKU1|01|10,000|5,00|50,00|0||||
|9999|15|
"""


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "efd_contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


class TestLeitor:
    def test_o_registro_sai_sem_decodificar_a_linha(self):
        assert registro_de(b"|C170|1|SKU1|") == b"C170"
        assert registro_de(b"linha solta") is None
        assert registro_de(b"||vazio|") is None

    def test_a_linha_vira_campos_sem_o_vazio_das_pontas(self):
        assert campos("|C010|11222333000181|0|\r\n") == ["C010", "11222333000181", "0"]

    def test_linha_torta_volta_como_veio_em_vez_de_derrubar(self):
        # SPED de cliente tem preâmbulo de exportador e linha em branco
        assert campos("sem pipe nenhum") == ["sem pipe nenhum"]

    def test_sem_marca_de_utf8_assume_cp1252(self, arquivo, tmp_path):
        assert codificacao_de(arquivo) == "cp1252"
        com_marca = tmp_path / "com_bom.txt"
        com_marca.write_bytes(b"\xef\xbb\xbf|0000|")
        assert codificacao_de(str(com_marca)) == "utf-8-sig"


class TestIndice:
    def test_conta_todo_registro_e_guarda_a_posicao_so_dos_alvos(self, arquivo):
        indice = indexar(arquivo)

        assert indice.quantos("C170") == 4
        assert indice.quantos("C100") == 2
        # o H010 é contado mesmo sem estar entre os alvos: contar tudo é o ponto
        assert indice.quantos("H010") == 1
        assert not indice.tem_posicoes("H010")
        assert len(indice.posicoes["C170"]) == 4
        assert indice.linhas == 16

    def test_le_o_cabecalho_na_mesma_passada(self, arquivo):
        """Quem lê o 0000 é o domínio, que conhece os três leiautes.

        O porte original trazia só as posições da EFD-Contribuições. Apontado a
        uma EFD ICMS/IPI real, devolvia a UF no lugar do CNPJ — achado no
        primeiro teste contra arquivo de verdade, em 22/09/2026.
        """
        c = indexar(arquivo).cabecalho
        assert c.cnpj == "11222333000181"
        assert c.nome == "COMERCIO DO TESTE LTDA"
        assert c.tipo == "efd_contribuicoes"
        assert (c.inicio, c.fim) == ("2021-06-01", "2021-06-30")

    def test_o_leiaute_do_icms_ipi_poe_os_campos_noutro_lugar(self, tmp_path):
        """A mesma empresa, o mesmo período, outro leiaute — e sai igual."""
        icms = tmp_path / "efd_icms.txt"
        icms.write_bytes(
            ("|0000|018|0|01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181||SP"
             "|111222333|3550308|||A|0|").encode("cp1252"))

        c = indexar(str(icms)).cabecalho

        assert c.cnpj == "11222333000181"
        assert c.nome == "COMERCIO DO TESTE LTDA"
        assert c.tipo == "efd_icms_ipi"
        assert (c.inicio, c.fim) == ("2021-06-01", "2021-06-30")

    def test_zero_zero_zero_zero_estranho_nao_derruba_a_contagem(self, tmp_path):
        torto = tmp_path / "torto.txt"
        torto.write_bytes(
            ("|0000|nada|disso|serve|" + chr(10) + "|C170|1|X|").encode("cp1252"))

        indice = indexar(str(torto))

        assert indice.cabecalho.cnpj == ""
        assert indice.quantos("C170") == 1

    def test_a_barra_de_progresso_chega_ao_fim(self, arquivo):
        vistos = []
        indexar(arquivo, avisar=lambda lidos, totais: vistos.append((lidos, totais)), a_cada=1)
        assert vistos[-1][0] == vistos[-1][1] > 0


class TestCacheDoIndice:
    def test_guardado_volta_igual(self, arquivo, tmp_path):
        pasta = str(tmp_path / "indices")
        original = indexar(arquivo)
        guardar(original, pasta)

        voltou = buscar(pasta, arquivo)

        assert voltou is not None
        assert voltou.contagens == original.contagens
        assert list(voltou.posicoes["C170"]) == list(original.posicoes["C170"])
        assert voltou.cabecalho.cnpj == original.cabecalho.cnpj

    def test_arquivo_que_mudou_de_tamanho_invalida_o_indice(self, arquivo, tmp_path):
        pasta = str(tmp_path / "indices")
        guardar(indexar(arquivo), pasta)
        with open(arquivo, "ab") as f:
            f.write(b"|9999|16|\n")

        assert buscar(pasta, arquivo) is None

    def test_indice_de_versao_anterior_e_refeito(self, arquivo, tmp_path, monkeypatch):
        import cat.infraestrutura.sped.indice as modulo
        pasta = str(tmp_path / "indices")
        guardar(indexar(arquivo), pasta)
        monkeypatch.setattr(modulo, "VERSAO_DO_ESQUEMA", VERSAO_DO_ESQUEMA + 1)

        assert buscar(pasta, arquivo) is None

    def test_sem_cache_indexa_e_grava_de_uma_vez(self, arquivo, tmp_path):
        pasta = str(tmp_path / "indices")

        primeiro = indice_de(arquivo, pasta)
        segundo = indice_de(arquivo, pasta)

        assert os.path.isfile(os.path.join(pasta, "indice.json"))
        assert primeiro.contagens == segundo.contagens

    def test_a_impressao_muda_quando_o_arquivo_muda(self, arquivo):
        antes = impressao_de(arquivo)
        with open(arquivo, "ab") as f:
            f.write(b"|9999|16|\n")
        assert impressao_de(arquivo) != antes


class TestExtracao:
    def test_registro_sai_pela_posicao_e_pagina(self, arquivo):
        indice = indexar(arquivo)

        todos = list(registros(arquivo, indice, "C170"))
        segunda_pagina = list(registros(arquivo, indice, "C170", de=2, quantos=2))

        assert len(todos) == 4
        assert todos[0][2] == "SKU1"
        assert [linha[2] for linha in segunda_pagina] == ["SKU1", "SKU2"]

    def test_registro_nao_indexado_diz_o_que_foi(self, arquivo):
        indice = indexar(arquivo)
        with pytest.raises(RegistroNaoIndexado, match="H010"):
            list(registros(arquivo, indice, "H010"))


class TestItemCompleto:
    def test_o_item_carrega_a_nota_o_estabelecimento_e_o_bloco_zero(self, arquivo):
        itens = list(itens_completos(arquivo, "cp1252"))

        assert len(itens) == 4
        primeiro = itens[0]
        # o item
        assert primeiro["C170_COD_ITEM"] == "SKU1"
        assert primeiro["C170_VL_ITEM"] == "500,00"
        assert primeiro["C170_CST_PIS"] == "50"
        # a nota que o contém
        assert primeiro["C100_NUM_DOC"] == "1001"
        assert primeiro["C100_CHV_NFE"].startswith("352106112223330001815500100000100")
        # o estabelecimento, e o cadastro dele pelo CNPJ
        assert primeiro["C010_CNPJ"] == "11222333000181"
        assert primeiro["0140_NOME"] == "MATRIZ DO TESTE"
        # o participante, pelo COD_PART da nota
        assert primeiro["0150_NOME"] == "FORNECEDOR ALFA"
        # a mercadoria, pelo COD_ITEM do item
        assert primeiro["0200_COD_NCM"] == "33051000"
        # a natureza, pelo COD_NAT do item
        assert primeiro["0400_DESCR_NAT"] == "VENDA NO ESTADO"

    def test_o_contexto_troca_quando_a_nota_troca(self, arquivo):
        itens = list(itens_completos(arquivo, "cp1252"))

        assert [i["C100_NUM_DOC"] for i in itens] == ["1001", "1001", "2002", "2002"]
        assert [i["0150_NOME"] for i in itens] == [
            "FORNECEDOR ALFA", "FORNECEDOR ALFA", "CLIENTE BETA", "CLIENTE BETA"]

    def test_o_icms_do_item_vem_junto(self, arquivo):
        """O C170 da EFD-Contribuições tem os campos do ICMS.

        Se o cliente os preenche, a exclusão do ICMS da base do PIS/COFINS sai
        daqui; se vierem vazios, é que será preciso cruzar com a EFD ICMS/IPI.
        """
        primeiro = next(iter(itens_completos(arquivo, "cp1252")))
        assert primeiro["C170_VL_ICMS"] == "90,00"
        assert primeiro["C170_ALIQ_ICMS"] == "18,00"

    def test_as_colunas_sao_conhecidas_antes_de_ler(self, arquivo):
        colunas = colunas_do_item()
        item = next(iter(itens_completos(arquivo, "cp1252")))
        assert set(item) == set(colunas)
        # a ordem agrupa por origem, do estabelecimento ao item, e as traduzidas
        # fecham a linha — depois das cruas, nunca no lugar delas
        assert colunas[0].startswith("0140_")
        assert colunas[-len(TRADUZIDAS) - 1].startswith("C170_")
        assert tuple(colunas[-len(TRADUZIDAS):]) == TRADUZIDAS

    def test_arquivo_sem_item_nao_devolve_nada_e_nao_quebra(self, tmp_path):
        vazio = tmp_path / "so_cabecalho.txt"
        vazio.write_bytes("|0000|006|0|||01062021|30062021|X|11222333000181|SP|\n".encode("cp1252"))
        assert list(itens_completos(str(vazio), "cp1252")) == []


class TestTabelaDeRegistros:
    def test_o_campo_e_achado_pelo_nome_em_vez_da_posicao(self):
        assert posicao_do_campo("C170", "CST_PIS") == 24
        assert posicao_do_campo("C100", "CHV_NFE") == 8

    def test_nome_errado_falha_na_hora_dizendo_o_que_existe(self):
        with pytest.raises(KeyError, match="CST_PIS"):
            posicao_do_campo("C170", "CST_PIZ")

    def test_registro_fora_da_tabela_nao_derruba_quem_so_conta(self):
        # o bloco H é de inventário: a quebra o conta sem saber nomear os campos
        assert nomes_dos_campos("H010") == ()


class TestEnriquecimento:
    """As colunas traduzidas: o código de um lado, o texto do outro.

    A amostra é montada **pelo nome do campo**, não contando pipes a olho — foi
    contando pipes que três fixtures deste projeto nasceram erradas. Se um nome
    não existir no leiaute, `posicao_do_campo` explode aqui, e não lá na frente.
    """

    @staticmethod
    def _linha(registro: str, **valores: str) -> str:
        colunas = [""] * len(nomes_dos_campos(registro))
        colunas[0] = registro
        for nome, valor in valores.items():
            colunas[posicao_do_campo(registro, nome)] = valor
        return "|" + "|".join(colunas) + "|"

    def _arquivo_com(self, tmp_path, nome: str, corpo: list[str]) -> str:
        caminho = tmp_path / nome
        caminho.write_bytes((chr(10).join(corpo) + chr(10)).encode("cp1252"))
        return str(caminho)

    @pytest.fixture
    def arquivo(self, tmp_path):
        linha = self._linha
        return self._arquivo_com(tmp_path, "enriquecido.txt", [
            "|0000|006|0|||01062021|30062021|COMERCIO DO TESTE|11222333000181|SP|3550308||00|2|",
            linha("0140", COD_EST="001", NOME="MATRIZ", CNPJ="11222333000181", UF="SP",
                  COD_MUN="3550308"),
            # fornecedor em Campinas/SP, cliente no Rio: a UF tem de mudar junto
            linha("0150", COD_PART="F01", NOME="FORNECEDOR", CNPJ="99888777000166",
                  COD_MUN="3509502"),
            linha("0150", COD_PART="C09", NOME="CLIENTE", CNPJ="55666777000122",
                  COD_MUN="3304557"),
            linha("0200", COD_ITEM="SKU1", DESCR_ITEM="XAMPU", TIPO_ITEM="00",
                  COD_NCM="33051000"),
            linha("C010", CNPJ="11222333000181", IND_ESCRIT="0"),
            # a compra para revenda
            linha("C100", IND_OPER="0", IND_EMIT="0", COD_PART="F01", NUM_DOC="1001",
                  DT_DOC="01062021", IND_PGTO="0", IND_FRT="9"),
            linha("C170", NUM_ITEM="1", COD_ITEM="SKU1", CFOP="1102", IND_MOV="0",
                  VL_ITEM="500,00", CST_PIS="50"),
            # a devolução de venda: entra crédito, e tem CFOP de faturamento
            linha("C100", IND_OPER="0", IND_EMIT="1", COD_PART="C09", NUM_DOC="2002",
                  DT_DOC="15072021", IND_PGTO="0", IND_FRT="9"),
            linha("C170", NUM_ITEM="1", COD_ITEM="SKU1", CFOP="1202", IND_MOV="0",
                  VL_ITEM="300,00", CST_PIS="50"),
            # a venda: não gera crédito, e por isso não tem natureza
            linha("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C09", NUM_DOC="3003",
                  DT_DOC="20072021", IND_PGTO="1", IND_FRT="0"),
            linha("C170", NUM_ITEM="1", COD_ITEM="SKU1", CFOP="5102", IND_MOV="0",
                  VL_ITEM="900,00", CST_PIS="01"),
        ])

    def test_a_natureza_do_credito_vem_do_cfop(self, arquivo):
        """Do CFOP, não do TIPO_ITEM.

        O C170 não tem `NAT_BC_CRED`. A regra pelo CFOP foi conferida contra
        43.497 linhas de um relatório de referência e reconfirmada contra outras
        81.150, em vinte CFOP distintos, sem uma exceção.
        """
        entrada, devolucao, saida = itens_completos(arquivo, "cp1252")

        assert entrada["NATUREZA_CREDITO"] == "01 - Aquisição de bens para revenda"
        assert devolucao["NATUREZA_CREDITO"] == "12 - Devolução de vendas - Incidência Não-Cumulativa"
        # saída não entra no mapa: crédito de PIS/COFINS é coisa de entrada
        assert saida["NATUREZA_CREDITO"] == ""

    def test_o_cfop_de_faturamento_so_aparece_na_devolucao(self, arquivo):
        entrada, devolucao, saida = itens_completos(arquivo, "cp1252")

        assert devolucao["CFOP_FATURAMENTO"] == "Devolução Faturamento"
        assert entrada["CFOP_FATURAMENTO"] == ""
        assert saida["CFOP_FATURAMENTO"] == ""

    def test_o_municipio_e_a_uf_saem_do_codigo_do_ibge(self, arquivo):
        """O 0150 não tem campo de UF: ela vem dos dois primeiros dígitos."""
        entrada, _, saida = itens_completos(arquivo, "cp1252")

        assert entrada["MUNICIPIO"] == "Campinas"
        assert entrada["UF_ORIGEM_DESTINO"] == "SP/SP"
        assert saida["MUNICIPIO"] == "Rio de Janeiro"
        assert saida["UF_ORIGEM_DESTINO"] == "RJ/SP"

    def test_o_periodo_e_o_primeiro_dia_do_mes_do_documento(self, arquivo):
        entrada, devolucao, _ = itens_completos(arquivo, "cp1252")

        assert entrada["PERIODO"] == "01/06/2021"
        assert devolucao["PERIODO"] == "01/07/2021"

    def test_data_torta_vira_competencia_vazia_em_vez_de_excecao(self):
        assert _competencia("") == ""
        assert _competencia("01/06/2021") == ""
        assert _competencia("0106") == ""

    def test_os_indicadores_saem_traduzidos_ao_lado_do_codigo(self, arquivo):
        entrada = next(iter(itens_completos(arquivo, "cp1252")))

        assert entrada["C100_IND_OPER"] == "0"
        assert entrada["TIPO_OPERACAO_DESC"] == "0 - Entrada"
        assert entrada["INDICADOR_EMITENTE_DESC"] == "0 - Emissão própria"
        assert entrada["INDICADOR_ESCRITURACAO_DESC"] == "0 - Consolidada"
        assert entrada["INDICADOR_PAGAMENTO_DESC"] == "0 - À vista"
        assert entrada["INDICADOR_FRETE_DESC"] == "9 - Sem ocorrência de transporte"
        assert entrada["INDICADOR_MOVIMENTO_ITEM_DESC"] == "0 - Sim"

    def test_o_cfop_e_o_tipo_do_item_ganham_descricao(self, arquivo):
        entrada = next(iter(itens_completos(arquivo, "cp1252")))

        assert entrada["C170_CFOP"] == "1102"
        assert entrada["DESCRICAO_CFOP"] == "Compra p/comercial"
        assert entrada["TIPO_ITEM_DESC"] == "00 Mercadoria para Revenda"

    def test_codigo_desconhecido_sai_vazio_em_vez_de_quebrar(self, tmp_path):
        """O cliente usa um CFOP que a tabela não tem. A linha sai assim mesmo."""
        linha = self._linha
        caminho = self._arquivo_com(tmp_path, "desconhecido.txt", [
            "|0000|006|0|||01062021|30062021|X|11222333000181|SP|3550308||00|2|",
            linha("C010", CNPJ="11222333000181", IND_ESCRIT="0"),
            linha("C100", IND_OPER="0", COD_PART="ZZZ", NUM_DOC="1", DT_DOC="01062021"),
            linha("C170", NUM_ITEM="1", COD_ITEM="SEM_CADASTRO", CFOP="9999",
                  VL_ITEM="1,00"),
        ])

        item = next(iter(itens_completos(caminho, "cp1252")))

        assert item["DESCRICAO_CFOP"] == ""
        assert item["NATUREZA_CREDITO"] == ""
        assert item["MUNICIPIO"] == ""
        assert item["UF_ORIGEM_DESTINO"] == ""
        assert set(item) == set(colunas_do_item())
