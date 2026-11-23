"""Leitura do relatório gerencial.

Os nomes de coluna abaixo são **os nomes reais** dos arquivos da empresa 19, só
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
    relatorios_do_lote,
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
        ("02/01/20", date(2020, 1, 2)),      # ano de dois dígitos, o da empresa 19
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
        # é assim que a empresa 19 escreve CFOP ausente
        assert v.cfop("  .      ") is None

    def test_tamanho_errado_levanta(self):
        with pytest.raises(v.ValorInvalido):
            v.cfop("110")


class TestDocumento:
    def test_catorze_digitos_e_cnpj(self):
        assert v.documento("44.000.002/0034-14") == ("44000002003414", None)

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
        # unidade e tipo do documento só vêm no relatório de saídas das lojas.
        # O que se afirma é a ausência **destes**, e não o conjunto inteiro:
        # campo opcional novo no catálogo não é regressão deste leiaute
        assert {"unidade", "tipo_documento"} <= {c.chave for c in m.nao_encontrados}
        assert not m.faltam_obrigatorios and not m.faltam_importantes

    def test_saida_de_loja_traz_unidade_e_tipo_do_documento(self):
        """É o que diz de qual loja é o cupom e que ele é venda a consumidor."""
        cabecalho = MOVIMENTO.split("|") + ["Unidade", "Descrição Tipo Dcto"]
        m = classificar(cabecalho)
        assert not m.faltam_obrigatorios and not m.faltam_importantes
        assert m.nomes_origem["unidade"] == "Unidade"
        assert m.nomes_origem["tipo_documento"] == "Descrição Tipo Dcto"

    def test_venda_de_pdv_e_consumidor_final_pelo_documento(self):
        dados = {"codigo_item": "100137", "data": "02/01/21", "cfop": "5.405",
                 "quantidade": "51", "unidade": "005",
                 "tipo_documento": "Estoque / Venda De Produtos PDVs"}
        m = MovimentoGerencial.de(dados, 2)
        assert m.unidade == "005" and m.e_venda_de_pdv and not m.e_entrada
        assert not MovimentoGerencial.de({**dados, "tipo_documento": "Transferência"}, 3).e_venda_de_pdv

    def test_cupom_com_nome_de_coluna_colado(self):
        """CSV diário de NFC-e de um ERP de varejo: os nomes vêm colados
        (VLRICMSST, BASCALCICMS). Sem o sinônimo exato, o ICMS-ST não casava e
        o valor do ICMS caía na BASE (o 'icms' parcial achava BASCALCICMS
        primeiro); a chave virava número do documento e a loja virava o
        participante."""
        cabecalho = ("CNPJ_FILIAL;NUM_EQUIP;CUP;CST;DATA_EMISSAO;NUM_AUTENTIC_NFE;"
                     "COD_MOD_DOC;NUM_SEQ_ITEM;COD_PRODUTO;DESCRICAO;COD_CFOP;QUANTIDADE;"
                     "FATOR_CONV_SAIDA;VLR_ITEM;BASCALCICMS;VLRICMS;BASCALCICMSST;VLRICMSST;"
                     "VLRIPI;BASPISCALC;VLRPISCALC;BASCOFINSCALC;VLRCOFINSCALC").split(";")
        m = classificar(cabecalho)
        assert m.especie is Especie.MOVIMENTO
        assert m.utilizavel
        assert {k: m.nomes_origem.get(k) for k in (
            "bc_icms", "valor_icms", "bc_st", "valor_st", "chave", "numero_doc", "unidade",
        )} == {
            "bc_icms": "BASCALCICMS", "valor_icms": "VLRICMS",
            "bc_st": "BASCALCICMSST", "valor_st": "VLRICMSST",
            "chave": "NUM_AUTENTIC_NFE", "numero_doc": "CUP", "unidade": "CNPJ_FILIAL",
        }
        # o consumidor não vem no cupom: a loja não pode passar por participante
        assert "cnpj_participante" not in m.posicoes

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
        # é o caso do arquivo real da empresa 19: as colunas existem e vêm vazias
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
            "00176231110|MS|1.102|040|0|0|0|502001440000020034555500100007338",
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
                f"44000002003414|MS|{cfop}|040|0|0|0|x")
        lt = Leitura(escrever(tmp_path, "mov.txt", [MOVIMENTO, *dados]))
        assert len(list(lt.movimentos())) == 100
        assert lt.total_incompletos == 100
        assert lt.total_invalidos == 0

    def test_coluna_trocada_aborta_a_leitura(self, tmp_path):
        # data onde deveria haver quantidade: o mapeamento é que está errado
        dados = [
            f"1171{i:02d}|Item|789|0705|não é data|1|1|1|1|1|0|0|0|0|"
            f"44000002003414|MS|1.102|040|0|0|0|x"
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


# ---------------------------------------------------------------------------
# Movimento sem ICMS-ST: o relatório de saída do varejo
#
# O cabeçalho abaixo é o real de um relatório de saídas item a item de um ERP de
# varejo (empresa 32), com os nomes como vêm — inclusive `CNNJ_CPF`, que é erro
# de digitação na origem, e o CST partido em duas colunas.
#
# Este arquivo caía como "não reconhecido" por faltar ICMS-ST, que ele não tem
# por natureza: venda a consumidor de mercadoria com ST sai em CST 60. E o pior
# não era a recusa — era que, aceitando-o, cinco campos casavam com a coluna
# errada pela busca parcial.
# ---------------------------------------------------------------------------
SAIDA_DO_VAREJO = (
    "CNPJ;NROEMPRESA;UF;DTAEMISSAO;NUMEROCFE;CFECHAVEACESSO;CODMODELO;SEQPESSOA;"
    "NOMERAZAO;CNNJ_CPF;CIDADE;UF;CFOP;SEQPRODUTO;DESCCOMPLETA;NCM;"
    "PRIMEIRO_DIGITO_CST;DOIS_ULTIMOS_DIGITOS_CST;SITUACAONFPIS;SITUACAONFCOFINS;"
    "UNIDADEPADRAO;QUANTIDADE;VLRUNITARIO;VLRDESCONTO;VLRTOTAL;VLRBASEICMS;"
    "PERALIQUOTAICMS;VLRICMS;BASEPISCALC;ALIQPISCALC;VLRPISCALC;BASECOFINSCALC;"
    "ALIQCOFINSCALC;VLRCOFINSCALC"
)


class TestMovimentoSemSt:
    def _mapa(self):
        return classificar(SAIDA_DO_VAREJO.split(";"))

    def test_e_movimento_sem_st_e_serve(self):
        m = self._mapa()
        assert m.especie is Especie.MOVIMENTO_SEM_ST
        assert m.utilizavel
        assert not m.faltam_obrigatorios and not m.faltam_importantes

    def test_a_especie_avisa_que_nao_tem_a_parcela_retida(self):
        """É o que impede o ICMS suportado de somar zero calado."""
        assert not Especie.MOVIMENTO_SEM_ST.tem_st
        assert Especie.MOVIMENTO.tem_st
        # mas serve ao razão: tem data e CFOP por linha
        assert Especie.MOVIMENTO_SEM_ST.serve_para_razao

    def test_cada_coluna_no_campo_certo(self):
        """O ponto da mudança. Antes, pela busca parcial: SEQPRODUTO caía na
        descrição, SITUACAONFPIS no número do documento, UNIDADEPADRAO na loja,
        o CNPJ do próprio estabelecimento no participante e só o dígito de
        origem no CST."""
        de = self._mapa().nomes_origem
        assert de["codigo_item"] == "SEQPRODUTO"
        assert de["descricao_item"] == "DESCCOMPLETA"
        assert de["numero_doc"] == "NUMEROCFE"
        assert de["unidade"] == "NROEMPRESA"
        assert de["unidade_medida"] == "UNIDADEPADRAO"
        assert de["cnpj_participante"] == "CNNJ_CPF"
        assert de["cst_icms"] == "DOIS_ULTIMOS_DIGITOS_CST"
        assert de["origem_mercadoria"] == "PRIMEIRO_DIGITO_CST"
        assert de["modelo_documento"] == "CODMODELO"
        assert de["valor_item"] == "VLRTOTAL"
        assert de["bc_icms"] == "VLRBASEICMS"
        assert de["aliquota_icms"] == "PERALIQUOTAICMS"
        assert de["valor_icms"] == "VLRICMS"
        assert de["chave"] == "CFECHAVEACESSO"

    def test_quem_tem_st_continua_movimento(self):
        """A regressão que importa: a espécie nova é menos exigente, e não pode
        roubar o arquivo que traz a parcela retida."""
        m = classificar(MOVIMENTO.split("|"))
        assert m.especie is Especie.MOVIMENTO

    def test_cupom_pelo_modelo_sem_texto_de_tipo(self):
        """Este relatório não tem a coluna de tipo de documento — só o modelo.
        Sem ler o modelo, a venda a consumidor não se reconhecia."""
        dados = {"codigo_item": "363204", "data": "02/01/2026", "cfop": "5102",
                 "quantidade": "1", "modelo_documento": "65"}
        m = MovimentoGerencial.de(dados, 2)
        assert m.e_venda_de_pdv and not m.e_entrada
        assert MovimentoGerencial.de({**dados, "modelo_documento": "59"}, 3).e_venda_de_pdv
        assert not MovimentoGerencial.de({**dados, "modelo_documento": "55"}, 4).e_venda_de_pdv

    def test_o_cst_vem_dos_dois_digitos_e_a_origem_a_parte(self):
        dados = {"codigo_item": "363204", "data": "02/01/2026", "cfop": "5102",
                 "quantidade": "1", "cst_icms": "60", "origem_mercadoria": "0",
                 "unidade_medida": "UN", "aliquota_icms": "18"}
        m = MovimentoGerencial.de(dados, 2)
        assert (m.cst_icms, m.origem_mercadoria) == ("60", "0")
        assert m.unidade_medida == "UN"
        assert m.aliquota_icms == Decimal("18")
        # sem ST informado, o registro não inventa parcela retida
        assert m.origem_do_st is OrigemDoSt.SEM_ST and m.st_que_vale == Decimal(0)


# Entrada do mesmo ERP de varejo: 160 colunas no arquivo real, aqui só as que o
# trabalho usa **e as que roubavam campo**. A ordem é a do arquivo, e é ela que
# importa: toda coluna isca vem ANTES da coluna certa, que foi o que fez o
# casamento parcial errar.
ENTRADA_DO_VAREJO = (
    "CNPJ Empresa;Data Ent/Saída;Espécie;Nro.Documento;Cód. Modelo;"
    "Entrada/Saida;Data Emissão;Série;Chave Acesso;Razão Social;"
    "CPF/CNPJ Pessoa;UF;CFOP;Descrição CFOP;NCM Cadastro;NCM Docto;"
    "Cód. Produto;Desc. Produto;Qtde.;Emb.;Valor Item;CST ICMS;Base ICMS;"
    "Aliq. ICMS;Valor ICMS;MVA ICMS/ST;Base ICMS/ST;Valor ICMS/ST;Cod. EAN;"
    "Vlr Origem;Valor FCP ICMS ST;Vlr Desp Fora NF"
)


class TestEntradaDoVarejo:
    def _mapa(self):
        return classificar(ENTRADA_DO_VAREJO.split(";"))

    def test_traz_st_entao_e_movimento_comum(self):
        m = self._mapa()
        assert m.especie is Especie.MOVIMENTO
        assert m.utilizavel

    def test_a_coluna_isca_nao_leva_mais_o_campo(self):
        """Cada um destes apontava para uma coluna errada, e sem erro nenhum.
        O pior era a descrição: o de-para casa por descrição, e passaria a
        comparar nome de operação ("Venda de mercadoria") em vez de produto."""
        de = self._mapa().nomes_origem
        assert de["descricao_item"] == "Desc. Produto"        # era Descrição CFOP
        assert de["numero_doc"] == "Nro.Documento"            # era Vlr Desp Fora NF
        assert de["indicador_entrada"] == "Entrada/Saida"     # era Data Ent/Saída
        assert "origem_mercadoria" not in de                  # era Vlr Origem

    def test_a_filial_nao_e_o_fornecedor(self):
        """A Ficha 3 é por estabelecimento: confundir os dois CNPJ junta a rede
        inteira num estabelecimento só e perde o participante."""
        de = self._mapa().nomes_origem
        assert de["unidade"] == "CNPJ Empresa"
        assert de["cnpj_participante"] == "CPF/CNPJ Pessoa"

    def test_acha_a_base_da_st_que_antes_passava_batido(self):
        """"Base ICMS/ST" não casava com "base st" nem com "bc icms st", e o
        campo ficava vazio com o dado ali do lado."""
        de = self._mapa().nomes_origem
        assert de["bc_st"] == "Base ICMS/ST"
        assert de["valor_st"] == "Valor ICMS/ST"
        assert de["valor_fcp_st"] == "Valor FCP ICMS ST"
        assert de["bc_icms"] == "Base ICMS"          # e não a base da ST


class TestApelidoCurto:
    """`so_exatos`: apelido curto demais para sair procurando dentro de outro
    nome de coluna."""

    def test_nao_casa_dentro_de_outro_nome(self):
        m = mapear(["Data", "Código", "CFOP", "Qtde", "Valor ICMS",
                    "Valor ICMS ST", "Vlr Desp Fora NF"], Especie.MOVIMENTO)
        assert "numero_doc" not in m.nomes_origem

    def test_mas_casa_quando_a_coluna_e_aquilo(self):
        m = mapear(["Data", "Código", "CFOP", "Qtde", "Valor ICMS",
                    "Valor ICMS ST", "NF"], Especie.MOVIMENTO)
        assert m.nomes_origem["numero_doc"] == "NF"

    def test_o_explicito_ganha_do_apelido_curto(self):
        """O apelido curto é tentado por último: com as duas colunas no
        arquivo, quem leva é a que diz o nome inteiro."""
        m = mapear(["Data", "Código", "CFOP", "Qtde", "Valor ICMS",
                    "Valor ICMS ST", "CNPJ", "CNNJ_CPF"], Especie.MOVIMENTO)
        assert m.nomes_origem["cnpj_participante"] == "CNNJ_CPF"


# ---------------------------------------------------------------------------
# O relatório de saídas de um ERP de varejo: todo campo entre aspas, a loja
# por número e por CNPJ lado a lado, e o mês de cupons dentro de zip. O
# cabeçalho é o real; a linha é inventada.
# ---------------------------------------------------------------------------
SAIDAS_DO_VAREJO = (
    '"LOJA";"CNPJ_LOJA";"COD_FORNEC";"CNPJ_FORNECEDOR";"RAZAO_SOCIAL";"NUM_DOC";'
    '"SERIE_DOCFIS";"DATA_EMISSAO";"COD_CFOP";"DT_ENTRADA";"COD_PRODUTO";"DESCRICAO_ITEM";'
    '"QTDEMBALAGEM";"UND_MEDIDA";"QUANTIDADE";"VLRITEM";"CST";"VLR_BASE_ICMS";"VLR_ICMS";'
    '"BASE_CALCULO_ICMS_ST";"VLR_IMPOSTO_ICMS_ST"'
)
LOJA = "11111111000272"
LINHA_DO_VAREJO = (
    f'"7";"{LOJA}";"7";"{LOJA}";"LOJA SETE";"123";"3";"28/01/2026";"5927";'
    '"28/01/2026";"555";"CARNE BOVINA kg";"1,000000";"KG";"11,616";"97,79";"020";'
    '"0";"0";"0";"0"'
)


class TestRelatorioEntreAspas:
    def test_a_loja_e_o_cnpj_e_a_unidade_nao_e_a_embalagem(self):
        """LOJA ("7") levava a unidade e QTDEMBALAGEM (um número) levava a
        unidade de medida; VLRITEM e a base da ST nem casavam."""
        m = classificar(SAIDAS_DO_VAREJO.split(";"))
        de = {k: v.strip('"') for k, v in m.nomes_origem.items()}
        assert m.utilizavel
        assert de["unidade"] == "CNPJ_LOJA"
        assert de["unidade_medida"] == "UND_MEDIDA"
        assert de["valor_item"] == "VLRITEM"
        assert de["bc_st"] == "BASE_CALCULO_ICMS_ST"
        assert de["valor_st"] == "VLR_IMPOSTO_ICMS_ST"

    def test_le_o_campo_sem_as_aspas(self, tmp_path):
        """Antes, `"28/01/2026"` não era data, as 500 primeiras linhas falhavam
        e o relatório inteiro era recusado."""
        c = escrever(tmp_path, "Saidas_JAN2026.csv", [SAIDAS_DO_VAREJO] + [LINHA_DO_VAREJO] * 3)
        leitura = Leitura(c)
        movs = list(leitura.movimentos())
        assert len(movs) == 3 and leitura.total_invalidos == 0
        m = movs[0]
        assert (m.data, m.cfop, m.unidade, m.unidade_medida) == (
            date(2026, 1, 28), "5927", LOJA, "KG")
        assert (m.quantidade, m.valor_item, m.numero_doc) == (
            Decimal("11.616"), Decimal("97.79"), 123)

    def test_aspas_dobradas_dentro_do_campo_viram_uma(self, tmp_path):
        linha = LINHA_DO_VAREJO.replace('"CARNE BOVINA kg"', '"PICANHA ""PREMIUM"""')
        c = escrever(tmp_path, "s.csv", [SAIDAS_DO_VAREJO, linha])
        assert next(Leitura(c).movimentos()).descricao_item == 'PICANHA "PREMIUM"'


class TestRelatorioDentroDoZip:
    @staticmethod
    def _zip(caminho, membros: dict[str, str]) -> str:
        import zipfile
        with zipfile.ZipFile(caminho, "w") as z:
            for nome, texto in membros.items():
                z.writestr(nome, texto.encode("latin-1"))
        return str(caminho)

    TEXTO = "\r\n".join([SAIDAS_DO_VAREJO, LINHA_DO_VAREJO, LINHA_DO_VAREJO])

    def test_le_o_membro_direto_do_zip(self, tmp_path):
        z = self._zip(tmp_path / "CUPONS_FEV2026.zip", {"CUPONS_02FEV2026.CSV": self.TEXTO})
        [membro] = relatorios_do_lote([z])
        assert membro == f"{z}::CUPONS_02FEV2026.CSV"
        assert len(list(Leitura(membro).movimentos())) == 2

    def test_o_mesmo_relatorio_entra_uma_vez_e_o_solto_vence(self, tmp_path):
        """O cliente mandou os CSV de janeiro abertos, o zip de janeiro e a
        pasta inteira zipada de novo: janeiro entraria três vezes."""
        solto = tmp_path / "CUPONS_02JAN2026.CSV"
        solto.write_bytes(self.TEXTO.encode("latin-1"))
        outro = self.TEXTO + "\r\n"                     # outro relatório: tamanho diferente
        mes = self._zip(tmp_path / "CUPONS_JAN2026.zip", {
            "CUPONS_02JAN2026.CSV": self.TEXTO,          # o mesmo que está solto
            "CUPONS_03JAN2026.CSV": outro,
            "leia-me.pdf": "não é relatório",
        })
        pasta = self._zip(tmp_path / "ERP_2026.zip", {
            "ERP_2026/CUPONS_JAN2026.zip": "zip dentro de zip não se abre",
            "ERP_2026/CUPONS_03JAN2026.CSV": outro,      # repete o do primeiro zip
            "ERP_2026/Saidas_JAN2026.csv": self.TEXTO,
        })
        assert relatorios_do_lote([str(solto), mes, pasta]) == [
            str(solto),
            f"{mes}::CUPONS_03JAN2026.CSV",
            f"{pasta}::ERP_2026/Saidas_JAN2026.csv",
        ]

    def test_zip_ilegivel_fica_de_fora_sem_derrubar_o_resto(self, tmp_path):
        ruim = tmp_path / "CUPONS_MAR2026.zip"
        ruim.write_bytes(b"isto nao e zip")
        solto = tmp_path / "s.csv"
        solto.write_text("x")
        assert relatorios_do_lote([str(ruim), str(solto)]) == [str(solto)]
