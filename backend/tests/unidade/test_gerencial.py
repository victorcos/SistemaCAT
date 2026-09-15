"""Leitura do relatório gerencial.

Os nomes de coluna abaixo são **os nomes reais** dos arquivos do Amigão, só
que em cabeçalhos reduzidos: o de movimento tem 143 colunas e o de inventário
40, e repetir tudo aqui não provaria mais nada do que provam as colunas que o
trabalho usa.

Três defeitos de arquivo real estão reproduzidos, porque foram eles que
moldaram o código:

* o exportador do inventário despeja a consulta SQL logo abaixo do cabeçalho,
  e as quebras dela viram separador — linha com número de campos errado;
* o resumo por produto tem cabeçalho de dois níveis, e a segunda linha parece
  dado até se olhar direito;
* o CFOP vem em branco como ``'  .      '`` em milhares de linhas.
"""

from datetime import date
from decimal import Decimal

import pytest

from cat.dominio.gerencial import valores as v
from cat.dominio.gerencial.campos import Especie, classificar, mapear
from cat.dominio.gerencial.leiaute import LeiauteNaoReconhecido, farejar
from cat.dominio.gerencial.registros import (
    ItemInventariado,
    MovimentoGerencial,
    OrigemDoSt,
)
from cat.infraestrutura.arquivos.gerencial import (
    Leitura,
    RelatorioIlegivel,
    inspecionar,
)

# ---------------------------------------------------------------------------
# cabeçalhos reais, reduzidos
# ---------------------------------------------------------------------------
MOVIMENTO = (
    "Código|Descricao|Código Barras|Trib|Dt Emissão|Número Dcto|Ent|"
    "Qtde;Unitária|Valor|BC ICMS|Valor ICMS|Valor BC ST;Informada|"
    "Valor ST;Informada|Valor FCP ST|CNPJ/CPF|UF|CFOP;Mvto|CST;ICMS|"
    "BC ICMS ST;XML|VR. ICMS ST;XML|ST integral|Chave DFe"
)

INVENTARIO = (
    "IFIS_UNID_CODIGO|IFIS_PROD_CODIGO|IFIS_PROD_DESCRICAO|IFIS_ESTOQUE|"
    "IFIS_CTFISCAL|IFIS_CTMEDIO|IFIS_DTULTCOMPRA|IFIS_CTEMPRESA|"
    "IFIS_VLRMEDIOUNICMS|IFIS_VLRMEDIOUNICMS_ST_BC|IFIS_VLRMEDIOUNICMS_ST|"
    "IFIS_VLRMEDIOUNFCP_ST|IFIS_ICMSALIQVIGENTE|IFIS_FCPALIQVIGENTE"
)

# O resumo por produto: cabeçalho em duas linhas, nomes repetidos em cima. O
# que dá sentido a `Qtde` é a linha de baixo — `Qtde`+`Vendas`, `Qtde`+`Compras`.
RESUMO_NIVEL_1 = (
    "Código|Descricao|Código Barras|Trib|Qtde|Vendas|Compras|Qtde|"
    "Perdas|Qtde Perdas|Devoluções|Qtde Devoluções|Vl. ICMS"
)
RESUMO_NIVEL_2 = (
    "||||Vendas|Líquidas|Líquidas|Compras|"
    "Estoque|Estoque|Venda|Venda|Informado"
)


# ---------------------------------------------------------------------------
# valores
# ---------------------------------------------------------------------------
class TestDecimal:
    @pytest.mark.parametrize(("bruto", "esperado"), [
        ("10,881", "10.881"),          # três casas, como o custo do ERP
        ("1275,55", "1275.55"),
        ("1.275,55", "1275.55"),       # ponto de milhar junto com a vírgula
        ("1.234", "1234"),             # só ponto e três casas: é milhar
        ("1.23", "1.23"),              # só ponto e duas casas: é decimal
        ("-45,10", "-45.10"),
        ("(45,10)", "-45.10"),         # negativo entre parênteses
        ("", "0"),
        ("   ", "0"),
    ])
    def test_le(self, bruto, esperado):
        assert v.decimal(bruto) == Decimal(esperado)

    def test_texto_que_nao_e_numero_levanta(self):
        with pytest.raises(v.ValorInvalido):
            v.decimal("dez reais")


class TestData:
    @pytest.mark.parametrize(("bruto", "esperado"), [
        ("02/01/20", date(2020, 1, 2)),      # ano de dois dígitos, o do Amigão
        ("31/12/2021", date(2021, 12, 31)),
        ("02012020", date(2020, 1, 2)),      # colado, como no SPED
        ("2020-01-02", date(2020, 1, 2)),
        ("15/03/99", date(1999, 3, 15)),     # acima do pivô, é século XX
    ])
    def test_le(self, bruto, esperado):
        assert v.data(bruto) == esperado

    def test_vazia_nao_e_erro(self):
        assert v.data("") is None

    def test_dia_inexistente_levanta(self):
        with pytest.raises(v.ValorInvalido):
            v.data("31/02/2021")


class TestCfop:
    def test_com_ponto_e_sem_ponto_dao_o_mesmo(self):
        assert v.cfop("1.102") == v.cfop("1102") == "1102"

    def test_branco_do_erp_vira_nada(self):
        # é assim que o Amigão escreve CFOP ausente
        assert v.cfop("  .      ") is None

    def test_tamanho_errado_levanta(self):
        with pytest.raises(v.ValorInvalido):
            v.cfop("110")


class TestDocumento:
    def test_catorze_digitos_e_cnpj(self):
        assert v.documento("11.517.841/0034-55") == ("11517841003455", None)

    def test_onze_digitos_e_cpf(self):
        # produtor rural entrega nota como pessoa física
        assert v.documento("00176231110") == (None, "00176231110")

    def test_tamanho_estranho_nao_vira_nenhum_dos_dois(self):
        assert v.documento("123") == (None, None)


# ---------------------------------------------------------------------------
# leiaute
# ---------------------------------------------------------------------------
class TestFarejar:
    def test_ponto_e_virgula_dentro_do_nome_nao_engana(self):
        # 'Qtde;Unitária' tem ponto-e-vírgula, mas quem separa é o pipe
        leiaute = farejar([MOVIMENTO, "1|2|3" + "|x" * 19])
        assert leiaute.separador == "|"
        assert leiaute.campos == 22

    def test_pula_o_sql_que_o_exportador_deixou_no_topo(self):
        linhas = ["SELECT", "\tIFIS_ESTOQUE,IFIS_CTMEDIO", INVENTARIO,
                  "089|117307|Maca||||||||||"]
        leiaute = farejar(linhas)
        assert leiaute.linha_do_cabecalho == 2
        assert leiaute.cabecalho[0] == "IFIS_UNID_CODIGO"

    def test_junta_cabecalho_de_dois_niveis(self):
        linhas = [RESUMO_NIVEL_1, RESUMO_NIVEL_2, "1|2|3|4|5|6|7|8|9|10|11|12|13"]
        leiaute = farejar(linhas)
        assert leiaute.niveis == 2
        assert "Devoluções Venda" in leiaute.cabecalho
        assert leiaute.primeira_linha_de_dado == 2

    def test_nome_unico_em_cima_nao_vira_dois_niveis(self):
        leiaute = farejar([MOVIMENTO, "1|2|3" + "|x" * 19])
        assert leiaute.niveis == 1

    def test_sem_separador_conhecido_levanta(self):
        with pytest.raises(LeiauteNaoReconhecido):
            farejar(["um relatório sem coluna nenhuma", "outra linha assim"])


# ---------------------------------------------------------------------------
# classificação e mapeamento
# ---------------------------------------------------------------------------
class TestClassificar:
    def test_movimento(self):
        m = classificar(MOVIMENTO.split("|"))
        assert m.especie is Especie.MOVIMENTO
        assert m.utilizavel
        assert m.tem_valores_do_xml
        # unidade e tipo do documento só vêm no relatório de saídas das lojas
        assert {c.chave for c in m.nao_encontrados} == {"unidade", "tipo_documento"}

    def test_saida_de_loja_traz_unidade_e_tipo_do_documento(self):
        """É o que diz de qual loja é o cupom e que ele é venda a consumidor."""
        cabecalho = MOVIMENTO.split("|") + ["Unidade", "Descrição Tipo Dcto"]
        m = classificar(cabecalho)
        assert not m.nao_encontrados
        assert m.nomes_origem["unidade"] == "Unidade"
        assert m.nomes_origem["tipo_documento"] == "Descrição Tipo Dcto"

    def test_venda_de_pdv_e_consumidor_final_pelo_documento(self):
        dados = {"codigo_item": "100137", "data": "02/01/21", "cfop": "5.405",
                 "quantidade": "51", "unidade": "005",
                 "tipo_documento": "Estoque / Venda De Produtos PDVs"}
        m = MovimentoGerencial.de(dados, 2)
        assert m.unidade == "005" and m.e_venda_de_pdv and not m.e_entrada
        assert not MovimentoGerencial.de({**dados, "tipo_documento": "Transferência"}, 3).e_venda_de_pdv

    def test_inventario(self):
        m = classificar(INVENTARIO.split("|"))
        assert m.especie is Especie.INVENTARIO
        assert m.utilizavel

    def test_resumo_nao_pode_cair_como_inventario(self):
        # o resumo tem 'Qtde Perdas Estoque', que casa com o 'estoque' do
        # inventário. Quem decide é a espécie mais exigente.
        cabecalho = [
            " ".join(p for p in (a.strip(), b.strip()) if p)
            for a, b in zip(RESUMO_NIVEL_1.split("|"), RESUMO_NIVEL_2.split("|"))
        ]
        assert classificar(cabecalho).especie is Especie.RESUMO

    def test_cabecalho_que_nao_e_relatorio_nao_passa(self):
        m = classificar(["Fornecedor", "Código Antigo", "Código Novo"])
        assert not m.utilizavel
        assert m.faltam_obrigatorios


class TestMapear:
    def test_sinonimo_especifico_ganha_do_generico(self):
        # 'IFIS_VLRMEDIOUNICMS' é prefixo de '..._ST' e de '..._ST_BC';
        # sem casamento exato antes do parcial, um levaria a coluna do outro
        m = mapear(INVENTARIO.split("|"), Especie.INVENTARIO)
        assert m.nomes_origem["icms_unitario"] == "IFIS_VLRMEDIOUNICMS"
        assert m.nomes_origem["st_unitario"] == "IFIS_VLRMEDIOUNICMS_ST"
        assert m.nomes_origem["bc_st_unitaria"] == "IFIS_VLRMEDIOUNICMS_ST_BC"

    def test_acento_e_pontuacao_nao_atrapalham(self):
        m = mapear(["CODIGO", "dt_emissao", "qtde unitaria", "cfop",
                    "valor icms", "valor st"], Especie.MOVIMENTO)
        assert m.utilizavel

    def test_coluna_nao_e_usada_duas_vezes(self):
        m = mapear(MOVIMENTO.split("|"), Especie.MOVIMENTO)
        assert len(set(m.posicoes.values())) == len(m.posicoes)


# ---------------------------------------------------------------------------
# registros: as regras do trabalho
# ---------------------------------------------------------------------------
def movimento(**campos) -> MovimentoGerencial:
    base = {"data": "02/01/20", "cfop": "1102", "codigo_item": "117110",
            "quantidade": "10"}
    return MovimentoGerencial.de({**base, **campos}, numero_linha=1)


class TestQualStVale:
    def test_xml_ganha_do_erp(self):
        # a regra do sistema: o documento fiscal é o que a SEFAZ vê
        m = movimento(valor_st="100,00", valor_st_xml="98,00")
        assert m.origem_do_st is OrigemDoSt.XML
        assert m.st_que_vale == Decimal("98.00")

    def test_erp_vale_quando_o_xml_nao_veio(self):
        m = movimento(valor_st="100,00")
        assert m.origem_do_st is OrigemDoSt.ERP
        assert m.st_que_vale == Decimal("100.00")

    def test_divergencia_e_a_distancia_do_erp_ate_o_xml(self):
        m = movimento(valor_st="100,00", valor_st_xml="98,00")
        assert m.divergencia_de_st == Decimal("2.00")

    def test_sem_os_dois_nao_ha_divergencia(self):
        assert movimento(valor_st="100,00").divergencia_de_st == 0

    def test_sem_st_nenhum(self):
        assert movimento().origem_do_st is OrigemDoSt.SEM_ST


class TestImpostoSuportado:
    def test_soma_proprio_st_e_fecoep(self):
        m = movimento(valor_icms="10,00", valor_st="20,00", valor_fcp_st="2,00")
        assert m.imposto_suportado == Decimal("32.00")

    def test_retido_anterior_nao_soma_o_icms_da_operacao(self):
        # comprando de substituído a mercadoria já veio tributada; somar o
        # ICMS da nota contaria imposto que não é dela
        m = movimento(valor_icms="10,00", st_retido_anterior="20,00")
        assert m.origem_do_st is OrigemDoSt.RETIDO_ANTERIOR
        assert m.imposto_suportado == Decimal("20.00")

    def test_unitario_divide_pela_quantidade(self):
        m = movimento(quantidade="4", valor_st="20,00")
        assert m.unitario_suportado == Decimal("5")

    def test_quantidade_zero_nao_estoura(self):
        assert movimento(quantidade="0", valor_st="20,00").unitario_suportado == 0


class TestDirecao:
    @pytest.mark.parametrize(("cfop", "entrada"), [
        ("1102", True), ("2152", True), ("3101", True),
        ("5927", False), ("6108", False), ("7101", False),
    ])
    def test_o_cfop_diz_o_sentido(self, cfop, entrada):
        assert movimento(cfop=cfop).e_entrada is entrada


class TestCampoObrigatorioEmBranco:
    @pytest.mark.parametrize("campo", ["data", "cfop", "codigo_item"])
    def test_em_branco_levanta_campo_vazio(self, campo):
        with pytest.raises(v.CampoVazio):
            movimento(**{campo: ""})

    def test_cfop_do_erp_em_branco_e_campo_vazio_nao_valor_invalido(self):
        # a diferença importa: campo vazio não aciona a defesa de mapeamento
        with pytest.raises(v.CampoVazio):
            movimento(cfop="  .      ")


class TestInventario:
    def test_custo_da_empresa_supre_o_custo_medio_zerado(self):
        i = ItemInventariado.de(
            {"codigo_item": "1", "quantidade_estoque": "2",
             "custo_medio": "0", "custo_empresa": "10,00"}, 1)
        assert i.custo == Decimal("10.00")
        assert i.valor_do_estoque == Decimal("20.00")

    def test_diz_quando_o_erp_nao_mandou_o_imposto(self):
        # é o caso do arquivo real do Amigão: as colunas existem e vêm vazias
        i = ItemInventariado.de(
            {"codigo_item": "1", "quantidade_estoque": "2",
             "custo_medio": "10,00", "st_unitario": "", "icms_unitario": ""}, 1)
        assert not i.tem_imposto_pronto
        assert i.suportado_total == 0

    def test_quando_mandou_o_imposto_o_suportado_sai_pronto(self):
        i = ItemInventariado.de(
            {"codigo_item": "1", "quantidade_estoque": "3",
             "icms_unitario": "1,00", "st_unitario": "2,00",
             "fcp_st_unitario": "0,50"}, 1)
        assert i.tem_imposto_pronto
        assert i.suportado_total == Decimal("10.50")


# ---------------------------------------------------------------------------
# leitura de arquivo
# ---------------------------------------------------------------------------
def escrever(tmp_path, nome, linhas, codificacao="latin-1"):
    caminho = tmp_path / nome
    caminho.write_bytes(("\r\n".join(linhas) + "\r\n").encode(codificacao))
    return str(caminho)


class TestLeitura:
    def test_le_movimento_e_reconhece_a_especie(self, tmp_path):
        c = escrever(tmp_path, "mov.txt", [
            MOVIMENTO,
            "117110|Alface|789|0705|02/01/20|73383|1|160|280|280|0|0|0|0|"
            "00176231110|MS|1.102|040|0|0|0|502001115178410034555500100007338",
        ])
        lt = Leitura(c)
        assert lt.especie is Especie.MOVIMENTO
        (m,) = list(lt.movimentos())
        assert m.codigo_item == "117110"
        assert m.data == date(2020, 1, 2)
        assert m.cfop == "1102"
        assert m.cpf_participante == "00176231110"

    def test_descarta_a_linha_de_tamanho_errado_em_vez_de_alinhar(self, tmp_path):
        c = escrever(tmp_path, "inv.txt", [
            INVENTARIO,
            "SELECT|\tIFIS_UNID_CODIGO,IFIS_PROD_CODIGO|\tCAL,IFIS_PRVENDA",
            "089|117307|Maca|1|0705|10,88|08/03/24|10,88|0|0|0|0|19,5|2",
        ])
        lt = Leitura(c)
        itens = list(lt.inventario())
        assert len(itens) == 1
        assert lt.descarte.linhas == 1
        assert lt.descarte.amostra  # o log precisa mostrar o que caiu

    def test_linha_incompleta_nao_aborta_a_leitura(self, tmp_path):
        # metade sem CFOP: é dado ruim, não coluna trocada
        dados = []
        for i in range(200):
            cfop = "  .      " if i % 2 else "1.102"
            dados.append(
                f"1171{i:02d}|Item|789|0705|02/01/20|1|1|1|1|1|0|0|0|0|"
                f"11517841003455|MS|{cfop}|040|0|0|0|x")
        lt = Leitura(escrever(tmp_path, "mov.txt", [MOVIMENTO, *dados]))
        assert len(list(lt.movimentos())) == 100
        assert lt.total_incompletos == 100
        assert lt.total_invalidos == 0

    def test_coluna_trocada_aborta_a_leitura(self, tmp_path):
        # data onde deveria haver quantidade: o mapeamento é que está errado
        dados = [
            f"1171{i:02d}|Item|789|0705|não é data|1|1|1|1|1|0|0|0|0|"
            f"11517841003455|MS|1.102|040|0|0|0|x"
            for i in range(600)
        ]
        lt = Leitura(escrever(tmp_path, "mov.txt", [MOVIMENTO, *dados]))
        with pytest.raises(RelatorioIlegivel, match="mapeada errada"):
            list(lt.movimentos())

    def test_pedir_especie_errada_avisa_em_vez_de_ler_torto(self, tmp_path):
        c = escrever(tmp_path, "inv.txt", [
            INVENTARIO, "089|117307|Maca|1|0705|10,88|08/03/24|10,88|0|0|0|0|19,5|2"])
        with pytest.raises(RelatorioIlegivel):
            list(Leitura(c).movimentos())

    def test_arquivo_sem_os_campos_obrigatorios_avisa_o_que_falta(self, tmp_path):
        c = escrever(tmp_path, "depara.txt",
                     ["Fornecedor|Código Antigo|Código Novo", "1|2|3"])
        with pytest.raises(RelatorioIlegivel, match="obrigatórios"):
            list(Leitura(c).brutos())

    def test_arquivo_vazio_avisa(self, tmp_path):
        c = tmp_path / "vazio.txt"
        c.write_bytes(b"")
        with pytest.raises(RelatorioIlegivel, match="vazio"):
            inspecionar(str(c))

    def test_utf8_com_bom_e_lido_como_utf8(self, tmp_path):
        c = escrever(tmp_path, "mov.txt", [MOVIMENTO, "1|Ação|" + "|" * 19],
                     codificacao="utf-8-sig")
        assert inspecionar(c).codificacao == "utf-8-sig"

    def test_resumo_por_produto_nao_promete_razao(self, tmp_path):
        c = escrever(tmp_path, "res.txt",
                     [RESUMO_NIVEL_1, RESUMO_NIVEL_2,
                      "1|Item|789|0705|1|2|3|4|5|6|7|8|9"])
        insp = inspecionar(c)
        assert insp.especie is Especie.RESUMO
        assert not insp.especie.serve_para_razao
