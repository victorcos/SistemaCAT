"""O item do XML na etapa 3, e o valor dele na etapa 4.

A EFD é a de `test_movimentos` — entrada com C170, NF-e própria de saída e
cupom SAT só com o analítico — mais uma nota cancelada e uma entrada de
terceiros sem C170. Os XML completam o que a EFD não detalha, casam com o C170
que existe e, quando casam, vencem na apuração do suportado.
"""

from __future__ import annotations

from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.dominio.icms.cat42.suportado import Fonte
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML, extrair_itens_do_xml
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_MOVIMENTOS, consolidar
from cat.infraestrutura.analitico.movimentos import extrair_movimentos
from cat.infraestrutura.analitico.suportado import ARQUIVO_SUPORTADO, apurar
from tests.unidade.test_movimentos import (
    C100_ENTRADA, C100_SAIDA, C170_1, C170_2, C170_SEM_CADASTRO, C190_ENTRADA, C190_ENTRADA_60,
    C190_SAIDA_00, C190_SAIDA_60, C800, C850, CABECALHO, CHAVE_CUPOM, CHAVE_ENTRADA, CHAVE_SAIDA,
    CNPJ, CONV_A_FD, ITEM_A_V2, ITEM_B, escrever,
)

D = Decimal
CHAVE_CANCELADA = "41210544000002000237550010000446250000000001"
CHAVE_SEM_C170 = "41210599888777000166550010000001231000000002"
CHAVE_FORA_DA_EFD = "41210599888777000166550010000009991000000003"

C100_CANCELADA = (f"|C100|1|0|C001|55|02|001|44625|{CHAVE_CANCELADA}"
                  "|02052021||0|0|0|0|0|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C100_SEM_C170 = (f"|C100|0|1|F002|55|00|001|123|{CHAVE_SEM_C170}"
                 "|04052021|05052021|40,00|2|0|0|40,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
C190_SEM_C170 = "|C190|060|1403|0|40,00|0|0|0|0|0|0||"


def nfe(chave: str, itens: str, tp: str = "1", emit: str = "99888777000166") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{chave}" versao="4.00">
<ide><mod>55</mod><serie>1</serie><nNF>1</nNF><dhEmi>2021-05-01T10:00:00-03:00</dhEmi><tpNF>{tp}</tpNF></ide>
<emit><CNPJ>{emit}</CNPJ></emit><dest><CNPJ>{CNPJ}</CNPJ></dest>{itens}
</infNFe></NFe></nfeProc>""".encode()


def det(n: int, codigo: str, cfop: str, qtd: str, valor: str, icms: str, gtin: str = "SEM GTIN",
        descricao: str = "PRODUTO") -> str:
    return (f'<det nItem="{n}"><prod><cProd>{codigo}</cProd><cEAN>{gtin}</cEAN><xProd>{descricao}</xProd>'
            f"<NCM>04031000</NCM><CEST>1702200</CEST><CFOP>{cfop}</CFOP><uCom>UN</uCom><qCom>{qtd}</qCom>"
            f"<vProd>{valor}</vProd></prod><imposto><ICMS>{icms}</ICMS></imposto></det>")


ICMS10 = ("<ICMS10><orig>0</orig><CST>10</CST><vBC>100.00</vBC><pICMS>18.00</pICMS><vICMS>18.00</vICMS>"
          "<vBCST>150.00</vBCST><pICMSST>18.00</pICMSST><vICMSST>9.00</vICMSST><vFCPST>1.00</vFCPST></ICMS10>")
ICMS60_RETIDO = ("<ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>5.00</vBCSTRet><vICMSSubstituto>0.30</vICMSSubstituto>"
                 "<vICMSSTRet>0.50</vICMSSTRet></ICMS60>")
ICMS60 = "<ICMS60><orig>0</orig><CST>60</CST></ICMS60>"
ICMS00 = "<ICMS00><orig>0</orig><CST>00</CST><vBC>50.00</vBC><pICMS>18.00</pICMS><vICMS>9.00</vICMS></ICMS00>"


@pytest.fixture
def pasta(tmp_path):
    efd = escrever(tmp_path, "efd_2021_05.txt", [
        CABECALHO, ITEM_A_V2, CONV_A_FD, ITEM_B,
        C100_ENTRADA, C170_1, C170_2, C170_SEM_CADASTRO, C190_ENTRADA, C190_ENTRADA_60,
        C100_SAIDA, C190_SAIDA_60, C190_SAIDA_00,
        C800, C850,
        C100_CANCELADA,
        C100_SEM_C170, C190_SEM_C170,
    ])
    xmls = tmp_path / "xml"
    xmls.mkdir()
    arquivos = {
        # do fornecedor, com um item a mais que o C170: o 1 casa (número e quantidade), o 2 não casa
        # (quantidade e valor diferentes), o 3 casa com retido; o 4 não tem C170
        "entrada.xml": nfe(CHAVE_ENTRADA, det(1, "FORN-1", "5401", "10", "100.00", ICMS10, gtin="7898194090401")
                           + det(2, "FORN-2", "5405", "19", "99.00", ICMS60)
                           + det(3, "FORN-3", "5405", "1", "5.00", ICMS60_RETIDO)
                           + det(4, "FORN-4", "5405", "1", "1.00", ICMS60)),
        # a saída própria: um item com cadastro, outro com código que o 0200 não tem
        "saida.xml": nfe(CHAVE_SAIDA, det(1, "1000144", "5405", "2", "250.00", ICMS60)
                         + det(2, "X-MKT", "5102", "1", "50.00", ICMS00, gtin="7890000000017",
                               descricao="CODIGO DE MARKETPLACE"), emit=CNPJ),
        "saida_copia.xml": nfe(CHAVE_SAIDA, det(1, "1000144", "5405", "2", "250.00", ICMS60), emit=CNPJ),
        "cupom.xml": (f'<?xml version="1.0"?><CFe><infCFe Id="CFe{CHAVE_CUPOM}"><ide><mod>59</mod>'
                      f"<nserieSAT>353552</nserieSAT><nCFe>62537</nCFe><dEmi>20210503</dEmi></ide>"
                      f"<emit><CNPJ>{CNPJ}</CNPJ></emit><dest/>"
                      + det(1, "537861", "5405", "1.5", "36.20", ICMS60.replace("orig", "Orig"))
                      + "</infCFe></CFe>").encode(),
        "cancelada.xml": nfe(CHAVE_CANCELADA, det(1, "1000144", "5405", "1", "10.00", ICMS60), emit=CNPJ),
        "sem_c170.xml": nfe(CHAVE_SEM_C170, det(1, "FORN-9", "5405", "4", "40.00", ICMS60)),
        "fora_da_efd.xml": nfe(CHAVE_FORA_DA_EFD, det(1, "FORN-8", "5405", "1", "1.00", ICMS60)),
        "evento.xml": b"<procEventoNFe><evento><infEvento><tpEvento>110111</tpEvento></infEvento></evento></procEventoNFe>",
        "quebrado.xml": b"<nfeProc><NFe>",
    }
    caminhos = []
    for nome, conteudo in sorted(arquivos.items()):
        (xmls / nome).write_bytes(conteudo)
        caminhos.append(str(xmls / nome))
    destino = str(tmp_path / "saida")
    extrair_movimentos([efd], destino)
    do_xml = extrair_itens_do_xml(caminhos, destino)
    resumo = consolidar(destino, None)
    linhas = pq.read_table(f"{destino}/{ARQUIVO_MOVIMENTOS}").to_pylist()
    return destino, do_xml, resumo, linhas


class TestLeitura:
    def test_um_documento_por_chave_e_o_resto_contado(self, pasta):
        destino, do_xml, _, _ = pasta
        assert (do_xml.arquivos_lidos, do_xml.documentos, do_xml.repetidos) == (9, 6, 1)
        assert (do_xml.nao_sao_documento, do_xml.ilegiveis) == (1, 1)
        assert pq.read_metadata(f"{destino}/{ARQUIVO_ITENS_DO_XML}").num_rows == do_xml.itens == 10


class TestCompletar:
    def test_saida_propria_e_cupom_ganham_o_item(self, pasta):
        _, _, resumo, linhas = pasta
        do_xml = sorted((l["chave"], l["numero_item"], l["codigo"], l["operacao"], l["registro"])
                        for l in linhas if l["fonte_item"] == "xml")
        assert do_xml == [
            (CHAVE_CUPOM, 1, "537861", "saida", "XML"),
            (CHAVE_SAIDA, 1, "1000144", "saida", "XML"),
            (CHAVE_SAIDA, 2, "X-MKT", "saida", "XML"),
            (CHAVE_SEM_C170, 1, "FORN-9", "entrada", "XML"),
        ]
        assert (resumo.saidas_completadas_pelo_xml, resumo.entradas_completadas_pelo_xml,
                resumo.movimentos_do_xml) == (2, 1, 4)

    def test_documento_e_o_da_efd_e_o_cadastro_vem_do_xml_quando_falta(self, pasta):
        _, _, _, linhas = pasta
        mkt = next(l for l in linhas if l["codigo"] == "X-MKT")
        assert (mkt["cnpj"], mkt["numero_documento"], mkt["cfop"], mkt["cst_icms"]) == (CNPJ, "44624", "5102", "000")
        assert (mkt["descricao"], mkt["codigo_barras"], mkt["cadastro_da_efd"]) == (
            "CODIGO DE MARKETPLACE", "7890000000017", False)
        iogurte = next(l for l in linhas if l["chave"] == CHAVE_SAIDA and l["codigo"] == "1000144")
        assert (iogurte["descricao"], iogurte["cadastro_da_efd"]) == ("Iog Vidativa 160g Ameixa", True)

    def test_cancelada_nao_e_completada(self, pasta):
        _, _, _, linhas = pasta
        assert not [l for l in linhas if l["chave"] == CHAVE_CANCELADA]

    def test_entrada_de_terceiros_leva_o_cfop_de_quem_recebeu(self, pasta):
        _, _, _, linhas = pasta
        sem_c170 = next(l for l in linhas if l["chave"] == CHAVE_SEM_C170)
        assert (sem_c170["cfop"], sem_c170["codigo_xml"]) == ("1403", "FORN-9")

    def test_nota_fora_da_efd_nao_vira_movimento(self, pasta):
        _, _, _, linhas = pasta
        assert not [l for l in linhas if l["chave"] == CHAVE_FORA_DA_EFD]


class TestAoLadoDoC170:
    def test_casa_pelo_numero_confirmado_pela_quantidade_ou_valor(self, pasta):
        _, _, resumo, linhas = pasta
        entrada = {l["numero_item"]: l for l in linhas if l["chave"] == CHAVE_ENTRADA}
        assert {n: l["fonte_item"] for n, l in entrada.items()} == {1: "efd", 2: "efd", 3: "efd"}
        assert (entrada[1]["codigo"], entrada[1]["codigo_xml"], entrada[1]["gtin_xml"]) == (
            "1000144", "FORN-1", "7898194090401")
        assert (entrada[1]["valor_st"], entrada[1]["valor_st_xml"], entrada[1]["fcp_st_xml"]) == (
            D("9.00"), D("9.00"), D("1.00"))
        assert entrada[2]["codigo_xml"] is None            # 19 un e R$ 99,00 contra 20,5 un e R$ 100,00
        assert entrada[3]["retido_xml"] == D("0.80")
        assert (resumo.itens_pareados_com_xml, resumo.itens_sem_par_no_xml) == (2, 1)
        assert any("não casaram com o item do XML" in a for a in resumo.avisos)


class TestNoSuportado:
    def test_o_xml_vence(self, pasta):
        destino, _, _, _ = pasta
        resumo = apurar(destino)
        linhas = {(l["chave"], l["numero_item"]): l for l in pq.read_table(f"{destino}/{ARQUIVO_SUPORTADO}").to_pylist()}
        # o C170 destaca 18 + 9; o XML, 18 + 9 + 1 de FCP
        assert linhas[(CHAVE_ENTRADA, 1)]["suportado"] == D("28")
        assert linhas[(CHAVE_ENTRADA, 3)]["fonte"] == Fonte.INFORMADO_PELO_FORNECEDOR.name.lower()
        assert linhas[(CHAVE_ENTRADA, 3)]["suportado"] == D("0.80")
        assert (resumo.itens_com_valor_do_xml, resumo.itens_com_retido_do_xml) == (3, 1)
