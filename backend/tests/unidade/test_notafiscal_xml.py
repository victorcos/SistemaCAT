"""O item do documento fiscal eletrônico, lido do XML.

Os XML aqui são montados à mão, no leiaute da NF-e 4.00 e do CF-e SAT, com os
casos que os arquivos reais mostraram: a venda interestadual com CST 00, a
interna com CST 60 e o retido informado, o código de barras "SEM GTIN", o CEST
do cupom nas observações do fisco e a origem com maiúscula no CF-e.
"""

from datetime import date
from decimal import Decimal

import pytest

from cat.dominio.notafiscal.xml import XmlIlegivel, ler_documento_xml

D = Decimal
CHAVE_NFE = "35240643112531000421550030000714581149028312"
CHAVE_CFE = "35210611517841003455590009876540012345678901"


def nfe(itens: str, mod: str = "55", tp: str = "1", dest: str = "<CPF>12345678909</CPF>",
        ind_final: str = "1") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
 <NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe Id="NFe{CHAVE_NFE}" versao="4.00">
   <ide><cUF>35</cUF><mod>{mod}</mod><serie>3</serie><nNF>71458</nNF>
        <dhEmi>2024-06-26T10:15:00-03:00</dhEmi><tpNF>{tp}</tpNF><indFinal>{ind_final}</indFinal></ide>
   <emit><CNPJ>43112531000421</CNPJ><xNome>LOJA</xNome></emit>
   <dest>{dest}</dest>
   {itens}
  </infNFe>
 </NFe>
 <protNFe versao="4.00"><infProt><cStat>100</cStat></infProt></protNFe>
</nfeProc>""".encode("utf-8")


ITEM_CST00 = """
   <det nItem="1">
    <prod><cProd>1111K3</cProd><cEAN>7891653011115</cEAN><xProd>GRECIN 5 CAST. CLARO KIT 3X</xProd>
     <NCM>33059000</NCM><CEST>2002200</CEST><CFOP>6108</CFOP><uCom>PC</uCom><qCom>2.0000</qCom>
     <vUnCom>39.99</vUnCom><vProd>79.98</vProd><vDesc>1.50</vDesc></prod>
    <imposto><ICMS><ICMS00><orig>8</orig><CST>00</CST><modBC>3</modBC><vBC>79.98</vBC>
     <pICMS>4.0000</pICMS><vICMS>3.20</vICMS></ICMS00></ICMS></imposto>
   </det>"""

ITEM_CST60 = """
   <det nItem="2">
    <prod><cProd>1012</cProd><cEAN>SEM GTIN</cEAN><xProd>GRECIN 2000 HOMEM LOCAO</xProd>
     <NCM>33059000</NCM><CFOP>5405</CFOP><uCom>PC</uCom><qCom>1.0000</qCom><vProd>39.99</vProd></prod>
    <imposto><ICMS><ICMS60><orig>0</orig><CST>60</CST><vBCSTRet>30.00</vBCSTRet><pST>25.0000</pST>
     <vICMSSubstituto>1.20</vICMSSubstituto><vICMSSTRet>6.30</vICMSSTRet><vFCPSTRet>0.50</vFCPSTRet>
     </ICMS60></ICMS></imposto>
   </det>"""


class TestNFe:
    def test_documento_e_itens(self):
        doc = ler_documento_xml(nfe(ITEM_CST00 + ITEM_CST60))
        assert (doc.chave, doc.modelo, doc.tipo, doc.emitente, doc.destinatario) == (
            CHAVE_NFE, "55", "1", "43112531000421", "12345678909")
        assert (doc.numero, doc.serie, doc.emissao) == ("71458", "3", date(2024, 6, 26))
        assert [i.numero for i in doc.itens] == [1, 2]

    def test_venda_interestadual_com_icms_proprio(self):
        item = ler_documento_xml(nfe(ITEM_CST00)).itens[0]
        assert (item.codigo, item.gtin, item.ncm, item.cest, item.cfop) == (
            "1111K3", "7891653011115", "33059000", "2002200", "6108")
        assert (item.unidade, item.quantidade, item.valor, item.desconto) == ("PC", D("2.0000"), D("79.98"), D("1.50"))
        assert (item.cst_icms, item.bc_icms, item.aliq_icms, item.valor_icms) == ("800", D("79.98"), D("4.0000"), D("3.20"))
        assert item.retido_informado is None

    def test_cst_60_traz_o_retido_informado(self):
        item = ler_documento_xml(nfe(ITEM_CST60)).itens[0]
        assert (item.gtin, item.cst_icms, item.valor_st) == ("", "060", D(0))
        assert item.retido_informado == D("8.00")      # 1,20 + 6,30 + 0,50
        assert item.bc_st_retido == D("30.00")

    def test_substituto_destaca_a_st(self):
        item = """<det nItem="1"><prod><cProd>1050-N</cProd><cEAN>7891653010507</cEAN><xProd>TONS</xProd>
            <NCM>33059000</NCM><CFOP>5401</CFOP><uCom>UN</uCom><qCom>2208.0000</qCom><vProd>28430.25</vProd></prod>
            <imposto><ICMS><ICMS10><orig>0</orig><CST>10</CST><vBC>28430.25</vBC><pICMS>9.0000</pICMS>
            <vICMS>2559.51</vICMS><vBCST>35537.81</vBCST><pICMSST>25.0000</pICMSST><vICMSST>6324.94</vICMSST>
            <vFCPST>12.00</vFCPST></ICMS10></ICMS></imposto></det>"""
        i = ler_documento_xml(nfe(item, tp="1", dest="<CNPJ>43112531000421</CNPJ>")).itens[0]
        assert (i.cst_icms, i.valor_icms, i.bc_st, i.aliq_st, i.valor_st, i.fcp_st) == (
            "010", D("2559.51"), D("35537.81"), D("25.0000"), D("6324.94"), D("12.00"))

    def test_nfce_do_simples_com_csosn(self):
        item = """<det nItem="1"><prod><cProd>9</cProd><cEAN></cEAN><xProd>X</xProd><NCM>1</NCM>
            <CFOP>5405</CFOP><uCom>UN</uCom><qCom>1</qCom><vProd>10.00</vProd></prod>
            <imposto><ICMS><ICMSSN500><orig>0</orig><CSOSN>500</CSOSN><vBCSTRet>8.00</vBCSTRet>
            <vICMSSTRet>1.44</vICMSSTRet></ICMSSN500></ICMS></imposto></det>"""
        doc = ler_documento_xml(nfe(item, mod="65"))
        assert doc.modelo == "65"
        assert (doc.itens[0].cst_icms, doc.itens[0].gtin, doc.itens[0].retido_informado) == ("0500", "", D("1.44"))

    def test_nfe_sem_o_protocolo(self):
        conteudo = nfe(ITEM_CST00).decode().replace("<nfeProc", "<x").replace("</nfeProc>", "</x>")
        conteudo = conteudo.split("<protNFe")[0] + "</x>"
        assert ler_documento_xml(conteudo.encode()).chave == CHAVE_NFE


class TestCFeSat:
    def test_cupom(self):
        conteudo = f"""<?xml version="1.0"?>
<CFe><infCFe Id="CFe{CHAVE_CFE}" versao="0.07">
 <ide><cUF>35</cUF><mod>59</mod><nserieSAT>900001234</nserieSAT><nCFe>987654</nCFe><dEmi>20210615</dEmi></ide>
 <emit><CNPJ>11517841003455</CNPJ></emit><dest/>
 <det nItem="1"><prod><cProd>000123</cProd><cEAN>7891000100103</cEAN><xProd>IOGURTE</xProd><NCM>04032000</NCM>
   <CFOP>5405</CFOP><uCom>UN</uCom><qCom>3.0000</qCom><vUnCom>2.50</vUnCom><vProd>7.50</vProd></prod>
   <imposto><ICMS><ICMS40><Orig>0</Orig><CST>60</CST></ICMS40></ICMS></imposto>
   <obsFiscoDet xCampoDet="Cod. CEST"><xTextoDet>1702200</xTextoDet></obsFiscoDet>
 </det>
</infCFe></CFe>""".encode()
        doc = ler_documento_xml(conteudo)
        assert (doc.chave, doc.modelo, doc.tipo, doc.emitente, doc.destinatario) == (CHAVE_CFE, "59", "1", "11517841003455", "")
        assert doc.consumidor_final is True
        assert (doc.numero, doc.serie, doc.emissao) == ("987654", "900001234", date(2021, 6, 15))
        item = doc.itens[0]
        assert (item.codigo, item.cest, item.cst_icms, item.quantidade, item.valor) == (
            "000123", "1702200", "060", D("3.0000"), D("7.50"))


class TestQuemComprou:
    def test_ind_final_da_nfe(self):
        assert ler_documento_xml(nfe(ITEM_CST60, ind_final="1")).consumidor_final is True
        assert ler_documento_xml(nfe(ITEM_CST60, ind_final="0")).consumidor_final is False
        sem = nfe(ITEM_CST60).replace(b"<indFinal>1</indFinal>", b"")
        assert ler_documento_xml(sem).consumidor_final is None

    def test_nfce_e_de_consumidor(self):
        assert ler_documento_xml(nfe(ITEM_CST60, mod="65", ind_final="0")).consumidor_final is True


class TestOQueNaoEDocumento:
    def test_cte_cita_notas_mas_nao_e_nota(self):
        cte = b"""<cteProc xmlns="http://www.portalfiscal.inf.br/cte"><CTe><infCte Id="CTe3524...">
            <infCTeNorm><infDoc><infNFe><chave>35240643112531000421550030000714581149028312</chave></infNFe>
            </infDoc></infCTeNorm></infCte></CTe></cteProc>"""
        assert ler_documento_xml(cte) is None

    def test_evento_de_cancelamento(self):
        evento = b"""<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00"><evento>
            <infEvento Id="ID1101113524..."><chNFe>35240643112531000421550030000714581149028312</chNFe>
            <tpEvento>110111</tpEvento></infEvento></evento></procEventoNFe>"""
        assert ler_documento_xml(evento) is None

    def test_inutilizacao(self):
        assert ler_documento_xml(b'<inutNFe xmlns="http://www.portalfiscal.inf.br/nfe"><infInut/></inutNFe>') is None

    def test_declarado_utf8_e_gravado_em_latin1(self):
        latin1 = nfe(ITEM_CST00).replace(b"GRECIN 5 CAST. CLARO", "GRECIN Nº 5".encode("latin-1"))
        with pytest.raises(UnicodeDecodeError):
            latin1.decode("utf-8")
        assert ler_documento_xml(latin1).itens[0].descricao.startswith("GRECIN Nº 5")

    def test_xml_quebrado(self):
        with pytest.raises(XmlIlegivel):
            ler_documento_xml(b"<nfeProc><NFe>")
