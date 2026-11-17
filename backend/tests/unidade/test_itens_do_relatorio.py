"""O item de saída vindo do relatório do cliente — a segunda porta.

A EFD de teste reproduz o que os arquivos reais mostram: a entrada de
terceiros tem C170; a saída de emissão própria **não tem**, vai só com o
analítico. Medido na empresa 17, matriz, janeiro de 2026: 100.269 saídas e
zero C170.

Até 17/11/2026 o item dessa saída só podia vir do XML. Quem não guardou XML —
na empresa 17, 7,4 mil arquivos para 13,8 milhões de documentos — ficava sem
item de saída nenhum, e o de-para via todo código como "só entrada".
"""

from __future__ import annotations

from decimal import Decimal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.itens_do_relatorio import (
    ARQUIVO_ITENS_DO_RELATORIO,
    extrair_itens_do_relatorio,
)
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML, ESQUEMA_ITENS_DO_XML
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_MOVIMENTOS, consolidar
from cat.infraestrutura.analitico.movimentos import extrair_movimentos

CNPJ = "44000003000100"
CHAVE_SAIDA = "35260144000003000100650010000001231000000017"
CHAVE_ENTRADA = "35260111222333000144550010000004561000000025"
# a mesma loja, outro documento de saída
CHAVE_SAIDA_2 = "35260144000003000100650010000001241000000018"

CABECALHO = (f"|0000|015|0|01012026|31012026|EMPRESA DE TESTE|{CNPJ}||SP"
             "|9000000000|3550308||||")
# o 0200 só lista o item que o arquivo referencia: aqui, o da entrada. O código
# que só vende não tem cadastro — é o caso real da empresa 17
ITEM_CADASTRADO = "|0200|363204|Arroz Tio Joao 5kg|7896006711117||PC|00|10063021||04||18|1702200|"

C100_ENTRADA = (f"|C100|0|1|F001|55|00|001|456|{CHAVE_ENTRADA}"
                "|05012026|05012026|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C170_ENTRADA = ("|C170|1|363204|Arroz|4|PC|100,00|0|0|060|1403|300|0|0|0"
                "|0|0|0||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.01|0|")
C190_ENTRADA = "|C190|060|1403|0|105,00|0|0|0|0|0|0||"

# saída própria de NFC-e: sem C170, só o analítico
C100_SAIDA = (f"|C100|1|0|C001|65|00|001|123|{CHAVE_SAIDA}"
              "|10012026|10012026|60,00|2|0|0|60,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C190_SAIDA = "|C190|060|5405|0|60,00|0|0|0|0|0|0||"

C100_SAIDA_2 = (f"|C100|1|0|C001|65|00|001|124|{CHAVE_SAIDA_2}"
                "|11012026|11012026|30,00|2|0|0|30,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C190_SAIDA_2 = "|C190|060|5405|0|30,00|0|0|0|0|0|0||"

CABECALHO_DO_RELATORIO = (
    "CNPJ;NROEMPRESA;UF;DTAEMISSAO;NUMEROCFE;CFECHAVEACESSO;CODMODELO;SEQPESSOA;"
    "NOMERAZAO;CNNJ_CPF;CIDADE;UF;CFOP;SEQPRODUTO;DESCCOMPLETA;NCM;"
    "PRIMEIRO_DIGITO_CST;DOIS_ULTIMOS_DIGITOS_CST;SITUACAONFPIS;SITUACAONFCOFINS;"
    "UNIDADEPADRAO;QUANTIDADE;VLRUNITARIO;VLRDESCONTO;VLRTOTAL;VLRBASEICMS;"
    "PERALIQUOTAICMS;VLRICMS;BASEPISCALC;ALIQPISCALC;VLRPISCALC;BASECOFINSCALC;"
    "ALIQCOFINSCALC;VLRCOFINSCALC"
)


def linha_de_saida(chave: str, codigo: str, descricao: str, ncm: str, cfop: str,
                   quantidade: str, total: str, cst: str = "60",
                   data: str = "10/01/2026", icms: str = "0") -> str:
    """Uma linha do relatório de saída, no leiaute real (34 colunas)."""
    campos = [""] * 34
    campos[0] = "440000030001-00"       # formatado e, em algumas lojas, furado
    campos[1] = "2"                     # NROEMPRESA: a loja, não o CNPJ
    campos[2] = "SP"
    campos[3] = data
    campos[4] = "123"
    campos[5] = chave
    campos[6] = "65"
    campos[9] = "11122233344"
    campos[12] = cfop
    campos[13] = codigo
    campos[14] = descricao
    campos[15] = ncm
    campos[16] = "0"                    # PRIMEIRO_DIGITO_CST
    campos[17] = cst                    # DOIS_ULTIMOS_DIGITOS_CST
    campos[20] = "UN"
    campos[21] = quantidade
    campos[24] = total
    campos[25] = "0"
    campos[26] = "18"
    campos[27] = icms
    return ";".join(campos)


# a linha de total, que o exportador despeja sem chave e sem código — fica fora
# antes daqui, pelo leitor do gerencial, que a conta como registro incompleto
LINHA_DE_TOTAL = linha_de_saida("", "", "Total:", "", "5102", "0", "90,00")
# o arquivo que passou pelo Excel e voltou com a chave em notação científica:
# o código está lá, a linha é um item de verdade, e a chave perdeu 38 dígitos.
# Aconteceu numa loja da empresa 17, e não há como reconstruir
LINHA_COM_CHAVE_ESTRAGADA = linha_de_saida(
    "3,52601E+43", "363204", "ARROZ TIO JOAO 5KG", "10063021", "5405", "1", "25,00")


def escrever(tmp_path, nome: str, linhas: list[str]) -> str:
    caminho = tmp_path / nome
    caminho.write_bytes(("\r\n".join(linhas) + "\r\n").encode("latin-1"))
    return str(caminho)


@pytest.fixture
def efd(tmp_path) -> list[str]:
    return [escrever(tmp_path, "efd_2026_01.txt", [
        CABECALHO, ITEM_CADASTRADO,
        C100_ENTRADA, C170_ENTRADA, C190_ENTRADA,
        C100_SAIDA, C190_SAIDA,
        C100_SAIDA_2, C190_SAIDA_2,
    ])]


@pytest.fixture
def relatorio(tmp_path) -> str:
    """Duas saídas: a primeira com dois itens, a segunda com um.

    O código 999777 não está no 0200 — é o que só vende.
    """
    return escrever(tmp_path, "Loja 2 01.2026.txt", [
        CABECALHO_DO_RELATORIO,
        linha_de_saida(CHAVE_SAIDA, "363204", "ARROZ TIO JOAO 5KG", "10063021",
                       "5405", "2", "50,00"),
        linha_de_saida(CHAVE_SAIDA, "999777", "LINGUICA TOSCANA KG", "16010000",
                       "5405", "0,532", "10,00"),
        LINHA_DE_TOTAL,
        LINHA_COM_CHAVE_ESTRAGADA,
        linha_de_saida(CHAVE_SAIDA_2, "363204", "ARROZ TIO JOAO 5KG", "10063021",
                       "5405", "1", "30,00", data="11/01/2026"),
    ])


@pytest.fixture
def extraido(efd, tmp_path):
    destino = str(tmp_path / "execucao")
    extrair_movimentos(efd, destino)
    return destino


def _linhas(caminho: str, sql: str):
    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW r AS SELECT * FROM read_parquet('{caminho}')")
        return con.execute(sql).fetchall()
    finally:
        con.close()


class TestExtracao:
    def test_grava_uma_linha_por_item_com_chave(self, relatorio, tmp_path):
        destino = str(tmp_path / "ex")
        p = extrair_itens_do_relatorio([relatorio], destino)
        assert p.itens == 3
        assert p.documentos == 2
        # o item cuja chave o Excel destruiu é item de verdade e não liga a
        # documento nenhum: fica fora, e contado. É por este número que se
        # percebe um arquivo estragado na origem
        assert p.sem_chave == 1
        assert p.ilegiveis == 0 and p.nao_sao_movimento == 0

    def test_numera_o_item_dentro_do_documento(self, relatorio, tmp_path):
        """O relatório não numera o item. Sem numeração não há identidade, e o
        encaixe com a EFD é o mesmo do XML: (chave, número do item)."""
        destino = str(tmp_path / "ex")
        extrair_itens_do_relatorio([relatorio], destino)
        linhas = _linhas(f"{destino}/{ARQUIVO_ITENS_DO_RELATORIO}",
                         "SELECT chave, numero_item, codigo FROM r ORDER BY chave, numero_item")
        assert linhas == [(CHAVE_SAIDA, 1, "363204"),
                          (CHAVE_SAIDA, 2, "999777"),
                          (CHAVE_SAIDA_2, 1, "363204")]

    def test_a_quantidade_fracionada_nao_e_arredondada(self, relatorio, tmp_path):
        """Item de balança vem em quilo com três casas: 0,532 kg de linguiça.
        Arredondar para inteiro aqui zeraria a saída do pesável."""
        destino = str(tmp_path / "ex")
        extrair_itens_do_relatorio([relatorio], destino)
        (qtd,), = _linhas(f"{destino}/{ARQUIVO_ITENS_DO_RELATORIO}",
                          "SELECT quantidade FROM r WHERE codigo = '999777'")
        assert qtd == Decimal("0.53200")

    def test_linha_sem_cfop_e_com_numero_torto_ficam_de_fora_e_contadas(self, tmp_path):
        """A leitura é pelo texto cru, para não pagar vinte conversões por
        linha. O que o registro montado recusava continua recusado — e agora
        cada motivo tem o seu número, em vez de um 'incompleto' só."""
        arquivo = escrever(tmp_path, "tortas.txt", [
            CABECALHO_DO_RELATORIO,
            # sem CFOP: não se sabe se entrou ou saiu
            linha_de_saida(CHAVE_SAIDA, "363204", "ARROZ", "10063021",
                           "", "1", "10,00"),
            # quantidade que não é número
            linha_de_saida(CHAVE_SAIDA, "363204", "ARROZ", "10063021",
                           "5405", "mil", "10,00"),
            linha_de_saida(CHAVE_SAIDA, "363204", "ARROZ", "10063021",
                           "5405", "1", "10,00"),
        ])
        p = extrair_itens_do_relatorio([arquivo], str(tmp_path / "ex"))
        assert (p.sem_cfop, p.invalidos, p.itens) == (1, 1, 1)
        # o item que entrou é o número 1: a numeração não conta o que foi fora
        (n,), = _linhas(f"{tmp_path}/ex/{ARQUIVO_ITENS_DO_RELATORIO}",
                        "SELECT numero_item FROM r")
        assert n == 1

    def test_o_que_nao_e_movimento_nao_entra_e_e_contado(self, tmp_path):
        inventario = escrever(tmp_path, "inv.txt", [
            "CNPJ|CODIGO|DESCRICAO|UNIDADE|QUANTIDADE|VALOR_UNITARIO|ICMS_ST_UNITARIO|DATA",
            f"{CNPJ}|363204|Arroz|PC|10|25,00|1,50|31/12/2025",
        ])
        p = extrair_itens_do_relatorio([inventario], str(tmp_path / "ex"))
        assert p.itens == 0
        # ou não é movimento, ou não foi reconhecido: o que não pode é passar calado
        assert p.nao_sao_movimento + p.ilegiveis == 1


class TestOItemChegaAoMovimento:
    @pytest.fixture
    def consolidado(self, extraido, relatorio):
        extrair_itens_do_relatorio([relatorio], extraido)
        return consolidar(extraido, None), extraido

    def test_a_saida_sem_c170_ganha_item(self, consolidado):
        """O ponto de tudo: sem isto a saída da empresa 17 não tem item nenhum."""
        resumo, destino = consolidado
        assert resumo.saidas_completadas_pelo_relatorio == 2
        assert resumo.entradas_completadas_pelo_relatorio == 0
        assert resumo.movimentos_do_relatorio == 3
        linhas = _linhas(f"{destino}/{ARQUIVO_MOVIMENTOS}",
                         "SELECT codigo, operacao, fonte_item, registro FROM r "
                         "WHERE fonte_item = 'relatorio' ORDER BY codigo")
        assert {(o, f, r) for _, o, f, r in linhas} == {("saida", "relatorio", "RELATORIO")}
        assert sorted(c for c, *_ in linhas) == ["363204", "363204", "999777"]

    def test_a_entrada_com_c170_nao_e_tocada(self, consolidado):
        """O relatório só completa documento escriturado SEM item. A entrada de
        terceiros tem C170, e é dele que a apuração vive."""
        _, destino = consolidado
        linhas = _linhas(f"{destino}/{ARQUIVO_MOVIMENTOS}",
                         "SELECT fonte_item, registro FROM r WHERE operacao = 'entrada'")
        assert linhas == [("efd", "C170")]

    def test_o_cfop_do_relatorio_entra_como_esta(self, consolidado):
        """O CFOP do XML é de quem emitiu e às vezes tem de virar; o do
        relatório já é o do próprio cliente. Virar trocaria entrada por saída."""
        _, destino = consolidado
        cfops = {c for (c,) in _linhas(f"{destino}/{ARQUIVO_MOVIMENTOS}",
                                       "SELECT DISTINCT cfop FROM r WHERE fonte_item = 'relatorio'")}
        assert cfops == {"5405"}

    def test_codigo_sem_0200_herda_nome_e_ncm_do_relatorio(self, consolidado):
        """O 0200 só lista o item que o arquivo referencia, e a saída vai sem
        item: o código que só vende não aparece em cadastro nenhum. Sem esta
        queda a ficha dele sairia sem nome e sem NCM."""
        _, destino = consolidado
        (desc, ncm, do_cadastro), = _linhas(
            f"{destino}/{ARQUIVO_MOVIMENTOS}",
            "SELECT descricao, ncm, cadastro_da_efd FROM r WHERE codigo = '999777'")
        assert desc == "LINGUICA TOSCANA KG"
        assert ncm == "16010000"
        assert do_cadastro is False

    def test_o_0200_continua_ganhando_do_relatorio(self, consolidado):
        """Quando a EFD cadastra o item, é o cadastro que vale: é ele que a
        Ficha 3 escritura, inclusive a unidade do inventário."""
        _, destino = consolidado
        descricoes = {d for (d,) in _linhas(
            f"{destino}/{ARQUIVO_MOVIMENTOS}",
            "SELECT DISTINCT descricao FROM r WHERE codigo = '363204'")}
        assert descricoes == {"Arroz Tio Joao 5kg"}


class TestOXmlGanhaDoRelatorio:
    """Quando os dois cobrem o mesmo documento vale o XML: é o que a SEFAZ
    autorizou. O relatório é o que o ERP diz."""

    def test_documento_com_xml_nao_recebe_o_relatorio(self, extraido, relatorio):
        xml = pa.table(
            {c.name: pa.array(
                [CHAVE_SAIDA] if c.name == "chave"
                else [1] if c.name == "numero_item"
                else ["DO XML"] if c.name == "descricao"
                else ["363204"] if c.name == "codigo"
                else [None], type=c.type)
             for c in ESQUEMA_ITENS_DO_XML},
            schema=ESQUEMA_ITENS_DO_XML)
        pq.write_table(xml, f"{extraido}/{ARQUIVO_ITENS_DO_XML}")
        extrair_itens_do_relatorio([relatorio], extraido)
        resumo = consolidar(extraido, None)
        # a primeira saída foi do XML; só a segunda sobrou para o relatório
        assert resumo.saidas_completadas_pelo_xml == 1
        assert resumo.saidas_completadas_pelo_relatorio == 1
        fontes = dict(_linhas(f"{extraido}/{ARQUIVO_MOVIMENTOS}",
                              "SELECT chave, fonte_item FROM r WHERE operacao = 'saida'"))
        assert fontes[CHAVE_SAIDA] == "xml"
        assert fontes[CHAVE_SAIDA_2] == "relatorio"


class TestUmaCopiaPorChave:
    """O cliente reexporta: na empresa 17, 3,3 milhões das 5,5 milhões de
    chaves da remessa de 13/11 já estavam nos 217 relatórios. Somar as duas
    cópias dobraria a quantidade vendida de cada item."""

    def test_documento_em_dois_relatorios_entra_uma_vez(self, extraido, relatorio, tmp_path):
        remessa = escrever(tmp_path, "remessa_nova_13-11-2026.txt", [
            CABECALHO_DO_RELATORIO,
            linha_de_saida(CHAVE_SAIDA, "363204", "ARROZ TIO JOAO 5KG", "10063021",
                           "5405", "2", "50,00"),
            linha_de_saida(CHAVE_SAIDA, "999777", "LINGUICA TOSCANA KG", "16010000",
                           "5405", "0,532", "10,00"),
        ])
        p = extrair_itens_do_relatorio([relatorio, remessa], extraido)
        assert p.itens == 5          # 3 do primeiro + 2 repetidos do segundo
        resumo = consolidar(extraido, None)
        # mas só uma cópia chega ao movimento
        assert resumo.movimentos_do_relatorio == 3
        (quantidade,), = _linhas(
            f"{extraido}/{ARQUIVO_MOVIMENTOS}",
            "SELECT sum(quantidade) FROM r WHERE codigo = '999777'")
        assert quantidade == Decimal("0.53200")


class TestOsPortoesDoRelatorioDeSaida:
    """O relatório de saída do varejo é `MOVIMENTO_SEM_ST`, e tinha de passar
    por quatro portões para chegar à apuração. Cada um destes testes falha com
    o código de antes de 17/11/2026."""

    def test_o_tipo_de_arquivo_e_pedido_ao_banco(self):
        """O primeiro portão, e o mais silencioso: a conferência, o razão e a
        movimentação listavam os arquivos do lote por `GERENCIAL_MOVIMENTO`
        apenas. O tipo existia, era reconhecido na importação, contava no
        cartão do lote — e não chegava a etapa nenhuma."""
        from cat.dominio.lote import GERENCIAIS_DE_MOVIMENTO, TipoDeArquivo
        assert TipoDeArquivo.GERENCIAL_SEM_ST in GERENCIAIS_DE_MOVIMENTO
        assert TipoDeArquivo.GERENCIAL_MOVIMENTO in GERENCIAIS_DE_MOVIMENTO
        # inventário e resumo não são movimento e não entram por esta porta
        assert TipoDeArquivo.GERENCIAL_INVENTARIO not in GERENCIAIS_DE_MOVIMENTO
        assert TipoDeArquivo.GERENCIAL_RESUMO not in GERENCIAIS_DE_MOVIMENTO

    def test_quem_lista_o_gerencial_usa_a_constante(self):
        """Uma constante, e não a lista escrita em cada arquivo. Foi a lista
        repetida em três lugares que deixou o tipo novo de fora de todos."""
        import inspect

        from cat.aplicacao.casos_de_uso import (
            conferir_documentos,
            extrair_movimentos,
            montar_razao,
        )
        for modulo in (conferir_documentos, extrair_movimentos, montar_razao):
            fonte = inspect.getsource(modulo)
            assert "GERENCIAIS_DE_MOVIMENTO" in fonte, modulo.__name__
            assert "(TipoDeArquivo.GERENCIAL_MOVIMENTO,)" not in fonte, modulo.__name__

    def test_o_razao_extrai_a_saida_do_relatorio_sem_st(self, relatorio, tmp_path):
        """O segundo portão. `extrair_saidas` exigia `MOVIMENTO` e recusava
        este arquivo em silêncio — as saídas do razão saíam vazias e a ficha
        fechava só com entradas."""
        from cat.infraestrutura.analitico.razao import extrair_saidas

        destino = str(tmp_path / "saidas_do_relatorio.parquet")
        r = extrair_saidas([relatorio], destino)
        assert r.recusados == 0
        assert r.so_de_entradas == 0
        assert r.linhas == 4        # as três com chave e a de chave estragada
        codigos = sorted(c for (c,) in _linhas(destino, "SELECT codigo FROM r"))
        assert codigos == ["363204", "363204", "363204", "999777"]

    def test_a_extracao_de_itens_aceita_a_especie_sem_st(self, relatorio, tmp_path):
        """O terceiro portão, o da extração de movimentos — e é por ele que o
        item de saída chega ao `movimentos.parquet`."""
        p = extrair_itens_do_relatorio([relatorio], str(tmp_path / "ex"))
        assert p.nao_sao_movimento == 0 and p.itens == 3


class TestSemRelatorio:
    def test_consolidar_sem_o_parquet_do_relatorio_continua_igual(self, extraido):
        """A perna nova não pode exigir arquivo: a maioria dos trabalhos não
        tem relatório, e a rodada deles não muda."""
        resumo = consolidar(extraido, None)
        assert resumo.relatorio_itens == 0
        assert resumo.movimentos_do_relatorio == 0
        assert resumo.saidas_completadas_pelo_relatorio == 0
        assert resumo.saidas_sem_item == 2
