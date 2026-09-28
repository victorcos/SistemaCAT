"""O crédito outorgado: quem entra, quem fica de fora e o que a varredura conta.

A regra é a do projeto `Quebra de SPED`: a **descrição manda**, a NCM confirma.
Os casos aqui são os que separam uma coisa da outra — NCM sozinha, descrição
sozinha, as duas juntas — mais o que a travessia para esta casa trouxe de novo:
cupom SAT lido junto, nota denegada fora, e a mesma chave em dois arquivos
contada uma vez só.
"""

from __future__ import annotations

from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.dominio.icms.credito_outorgado import (
    MOTIVO_DESCRICAO,
    MOTIVO_NCM_E_DESCRICAO,
    MOTIVO_SEM_FILTRO,
    Filtro,
)
from cat.infraestrutura.analitico.credito_outorgado import (
    ARQUIVO_DESCARTADOS,
    ARQUIVO_ELEGIVEIS,
    serializar,
    varrer,
)

D = Decimal

CNPJ_EMITENTE = "11222333000181"
CHAVE_UM = "35210511222333000181550010000001231000000001"
CHAVE_DOIS = "35210511222333000181550010000004561000000002"
CHAVE_DENEGADA = "35210511222333000181550010000007891000000003"
CHAVE_CUPOM = "35210511222333000181590010000001111000000004"


# ---------------------------------------------------------------------------
# a regra, sem arquivo nenhum
# ---------------------------------------------------------------------------
def test_descricao_sozinha_elege():
    filtro = Filtro.de(ncms=["190590"], termos=["PÃO"])
    veredito = filtro.avaliar("PÃO DE FORMA GRANDE", "21069090")
    assert veredito.elegivel
    assert veredito.motivo == MOTIVO_DESCRICAO


def test_ncm_sozinha_nao_elege():
    """É a regra que a origem escolheu, e a razão dela: a NCM é declarada pelo
    emitente e erra; a descrição é o produto que o dono do negócio reconhece."""
    filtro = Filtro.de(ncms=["190590"], termos=["PÃO"])
    veredito = filtro.avaliar("BISCOITO RECHEADO", "19059090")
    assert not veredito.elegivel
    assert veredito.motivo == ""


def test_as_duas_juntas_dizem_que_estao_de_acordo():
    filtro = Filtro.de(ncms=["190590"], termos=["PÃO"])
    veredito = filtro.avaliar("PÃO FRANCÊS", "19059090")
    assert veredito.elegivel
    assert veredito.motivo == MOTIVO_NCM_E_DESCRICAO


def test_descricao_casa_por_pedaco_e_sem_caixa():
    filtro = Filtro.de(termos=["farinha"])
    assert filtro.avaliar("FARINHA DE TRIGO ESPECIAL 1KG", "11010010").elegivel


def test_acento_nao_e_dobrado():
    """Deliberado, e igual à origem: dobrar acento faria entrar aqui item que lá
    fica de fora, e os dois resultados precisam poder ser comparados."""
    filtro = Filtro.de(termos=["PAO"])
    assert not filtro.avaliar("PÃO FRANCÊS", "19059090").elegivel


def test_ncm_casa_por_prefixo_e_nao_por_pedaco():
    """A diferença consciente para a origem: lá, `690` era procurado em qualquer
    posição e achava `21069090`. NCM vale da esquerda para a direita."""
    filtro = Filtro.de(ncms=["0690"], termos=["BOLO"])
    assert filtro.avaliar("BOLO DE MILHO", "21069090").motivo == MOTIVO_DESCRICAO


def test_ncm_do_cadastro_aceita_ponto():
    filtro = Filtro.de(ncms=["1905.90"], termos=["PÃO"])
    assert filtro.avaliar("PÃO", "19059090").motivo == MOTIVO_NCM_E_DESCRICAO


def test_sem_filtro_tudo_entra_com_o_rotulo_que_avisa():
    filtro = Filtro.de(sem_filtro=True)
    veredito = filtro.avaliar("QUALQUER COISA", "99999999")
    assert veredito.elegivel
    assert veredito.motivo == MOTIVO_SEM_FILTRO


def test_filtro_sem_termo_nao_julga():
    """Sem termo e sem a chave geral nada seria elegível: quem chama precisa
    saber disso antes de varrer 120 mil arquivos para nada."""
    assert not Filtro.de(ncms=["190590"]).julga
    assert Filtro.de(termos=["PÃO"]).julga
    assert Filtro.de(sem_filtro=True).julga


def test_termo_repetido_entra_uma_vez_so_e_na_ordem_do_usuario():
    filtro = Filtro.de(termos=["pão", " PÃO ", "leite"])
    assert filtro.termos == ("PÃO", "LEITE")


# ---------------------------------------------------------------------------
# a varredura
# ---------------------------------------------------------------------------
def det(n: int, codigo: str, descricao: str, ncm: str, valor: str) -> str:
    return (f'<det nItem="{n}"><prod><cProd>{codigo}</cProd><xProd>{descricao}</xProd>'
            f"<NCM>{ncm}</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom>"
            f"<vUnCom>5.0000000000</vUnCom><vProd>{valor}</vProd></prod>"
            "<imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>10.00</vBC>"
            "<pICMS>18.00</pICMS><vICMS>1.80</vICMS></ICMS00></ICMS>"
            "<PIS><PISAliq><CST>01</CST><vBC>10.00</vBC><pPIS>1.65</pPIS><vPIS>0.17</vPIS></PISAliq></PIS>"
            "<COFINS><COFINSAliq><CST>01</CST><vBC>10.00</vBC><pCOFINS>7.60</pCOFINS>"
            "<vCOFINS>0.76</vCOFINS></COFINSAliq></COFINS></imposto></det>")


def nfe(chave: str, itens: str, cstat: str | None = "100",
        emitente: str = CNPJ_EMITENTE, tp: str = "1") -> bytes:
    protocolo = (f"<protNFe><infProt><chNFe>{chave}</chNFe><cStat>{cstat}</cStat></infProt></protNFe>"
                 if cstat else "")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{chave}" versao="4.00">
<ide><mod>55</mod><serie>1</serie><nNF>123</nNF><dhEmi>2021-05-04T10:00:00-03:00</dhEmi><tpNF>{tp}</tpNF></ide>
<emit><CNPJ>{emitente}</CNPJ><xNome>EMPRESA A</xNome></emit>
<dest><CPF>11122233344</CPF><xNome>CONSUMIDOR</xNome></dest>{itens}
</infNFe></NFe>{protocolo}</nfeProc>""".encode()


def cupom(chave: str, itens: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CFe><infCFe Id="CFe{chave}" versao="0.07">
<ide><mod>59</mod><nserieSAT>900001</nserieSAT><nCFe>111</nCFe><dEmi>20210504</dEmi></ide>
<emit><CNPJ>{CNPJ_EMITENTE}</CNPJ><xNome>EMPRESA A</xNome></emit><dest></dest>{itens}
</infCFe></CFe>""".encode()


@pytest.fixture
def pasta(tmp_path):
    xmls = tmp_path / "xml"
    xmls.mkdir()
    arquivos = {
        # um item que casa pelos dois critérios, um que casa só pela descrição e
        # um que não casa por nada
        "nota1.xml": nfe(CHAVE_UM,
                         det(1, "P01", "PAO FRANCES", "19059090", "10.00")
                         + det(2, "P02", "PAO DE QUEIJO CONGELADO", "21069090", "25.50")
                         + det(3, "X01", "DETERGENTE 500ML", "34022000", "7.00")),
        # a mesma chave da nota1, no zip do trimestre: não pode contar duas vezes
        "nota1_copia.xml": nfe(CHAVE_UM, det(1, "P01", "PAO FRANCES", "19059090", "10.00")),
        "nota2.xml": nfe(CHAVE_DOIS, det(1, "P01", "PAO DE FORMA", "19059090", "8.25")),
        # uso denegado: a nota não existe, e nada dela entra
        "denegada.xml": nfe(CHAVE_DENEGADA, det(1, "P01", "PAO SIRIO", "19059090", "99.00"), cstat="302"),
        "cupom.xml": cupom(CHAVE_CUPOM, det(1, "P01", "PAO DOCE", "19059090", "3.75")),
        # não é documento de mercadoria: não conta como erro
        "evento.xml": b'<?xml version="1.0"?><procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe">'
                      b"<evento/></procEventoNFe>",
        "quebrado.xml": b"<nfeProc><NFe>",
    }
    for nome, conteudo in arquivos.items():
        (xmls / nome).write_bytes(conteudo)
    return xmls


def _linhas(caminho):
    return pq.read_table(caminho).to_pylist()


def test_varredura_separa_o_que_entra(pasta, tmp_path):
    destino = str(tmp_path / "saida")
    filtro = Filtro.de(ncms=["190590"], termos=["PAO"])

    progresso = varrer(sorted(str(p) for p in pasta.glob("*.xml")), destino, filtro,
                       incluir_descartados=True)

    # nota1 (3 itens), nota2 (1) e cupom (1); a cópia e a denegada ficam fora
    assert progresso.documentos == 3
    assert progresso.itens == 5
    assert progresso.elegiveis == 4
    assert progresso.descartados == 1
    assert progresso.repetidos == 1
    assert progresso.nao_autorizados == 1
    assert progresso.nao_sao_documento == 1
    assert progresso.ilegiveis == 1
    # 10,00 + 25,50 + 8,25 + 3,75
    assert progresso.centavos_elegiveis == 4750

    elegiveis = _linhas(f"{destino}/{ARQUIVO_ELEGIVEIS}")
    assert {l["codigo"] for l in elegiveis} == {"P01", "P02"}
    assert {l["motivo"] for l in elegiveis} == {MOTIVO_DESCRICAO, MOTIVO_NCM_E_DESCRICAO}
    # o de-queijo casa só pela descrição: a NCM dele não está cadastrada
    queijo = next(l for l in elegiveis if l["codigo"] == "P02")
    assert queijo["motivo"] == MOTIVO_DESCRICAO
    assert queijo["valor"] == D("25.50")
    assert queijo["emitente_nome"] == "EMPRESA A"
    assert queijo["valor_unitario"] == D("5.0000000000")
    assert queijo["cst_pis"] == "01"
    assert queijo["aliq_cofins"] == D("7.6000")

    descartados = _linhas(f"{destino}/{ARQUIVO_DESCARTADOS}")
    assert [l["codigo"] for l in descartados] == ["X01"]
    assert descartados[0]["elegivel"] is False


def test_sem_descartados_o_arquivo_nao_nasce(pasta, tmp_path):
    destino = str(tmp_path / "saida")
    varrer(sorted(str(p) for p in pasta.glob("*.xml")), destino, Filtro.de(termos=["PAO"]))
    assert not (tmp_path / "saida" / ARQUIVO_DESCARTADOS).exists()


def test_cupom_sat_entra_como_a_nfe(pasta, tmp_path):
    destino = str(tmp_path / "saida")
    varrer([str(pasta / "cupom.xml")], destino, Filtro.de(termos=["PAO"]))
    linhas = _linhas(f"{destino}/{ARQUIVO_ELEGIVEIS}")
    assert [l["modelo"] for l in linhas] == ["59"]
    assert linhas[0]["valor"] == D("3.75")


# ---------------------------------------------------------------------------
# entrada e saída
# ---------------------------------------------------------------------------
RAIZ = CNPJ_EMITENTE[:8]
CNPJ_FORNECEDOR = "99888777000166"
CHAVE_COMPRA = "35210599888777000166550010000005551000000005"
CHAVE_DEVOLUCAO = "35210599888777000166550010000006661000000006"


def test_a_nota_de_compra_nao_entra_no_beneficio(tmp_path):
    """O benefício é sobre o que a empresa **vendeu**. A nota do fornecedor vem
    na mesma pasta e tem tpNF=1 — saída, para ele —, e entraria se o filtro
    olhasse só o tpNF."""
    pasta = tmp_path / "xml"
    pasta.mkdir()
    (pasta / "venda.xml").write_bytes(nfe(CHAVE_UM, det(1, "P01", "PAO FRANCES", "19059090", "10.00")))
    (pasta / "compra.xml").write_bytes(
        nfe(CHAVE_COMPRA, det(1, "F01", "PAO DE FORMA", "19059090", "500.00"),
            emitente=CNPJ_FORNECEDOR))
    destino = str(tmp_path / "saida")

    progresso = varrer(sorted(str(p) for p in pasta.glob("*.xml")), destino,
                       Filtro.de(termos=["PAO"]), raiz_do_cnpj=RAIZ)

    assert progresso.nao_sao_saida == 1
    assert progresso.elegiveis == 1
    assert progresso.centavos_elegiveis == 1000
    assert [l["codigo"] for l in _linhas(f"{destino}/{ARQUIVO_ELEGIVEIS}")] == ["P01"]


def test_a_nota_de_entrada_que_o_cliente_emite_e_saida_nossa(tmp_path):
    """Quem emite com tpNF=0 está registrando uma entrada **dele** — a mercadoria
    saiu de nós. O cruzamento acerta os dois lados; o tpNF sozinho erraria."""
    pasta = tmp_path / "xml"
    pasta.mkdir()
    (pasta / "devolucao.xml").write_bytes(
        nfe(CHAVE_DEVOLUCAO, det(1, "P01", "PAO FRANCES", "19059090", "7.00"),
            emitente=CNPJ_FORNECEDOR, tp="0"))
    destino = str(tmp_path / "saida")

    progresso = varrer([str(pasta / "devolucao.xml")], destino,
                       Filtro.de(termos=["PAO"]), raiz_do_cnpj=RAIZ)

    assert progresso.nao_sao_saida == 0
    assert progresso.elegiveis == 1


def test_sem_raiz_nao_filtra_direcao_nenhuma(tmp_path):
    """Sem saber de quem é a nota, filtrar seria adivinhar — e adivinhar aqui é
    apagar a apuração inteira."""
    pasta = tmp_path / "xml"
    pasta.mkdir()
    (pasta / "compra.xml").write_bytes(
        nfe(CHAVE_COMPRA, det(1, "F01", "PAO DE FORMA", "19059090", "500.00"),
            emitente=CNPJ_FORNECEDOR))
    destino = str(tmp_path / "saida")

    progresso = varrer([str(pasta / "compra.xml")], destino, Filtro.de(termos=["PAO"]))

    assert progresso.nao_sao_saida == 0
    assert progresso.elegiveis == 1


def test_a_direcao_e_do_ponto_de_vista_de_quem_pergunta():
    """A regra pura, sem arquivo: quatro combinações, duas de cada lado."""
    from cat.dominio.notafiscal.xml import ler_documento_xml  # noqa: PLC0415

    nossa_venda = ler_documento_xml(nfe(CHAVE_UM, det(1, "P", "X", "1", "1.00")))
    compra = ler_documento_xml(
        nfe(CHAVE_COMPRA, det(1, "P", "X", "1", "1.00"), emitente=CNPJ_FORNECEDOR))
    nossa_entrada = ler_documento_xml(nfe(CHAVE_UM, det(1, "P", "X", "1", "1.00"), tp="0"))
    devolucao = ler_documento_xml(
        nfe(CHAVE_DEVOLUCAO, det(1, "P", "X", "1", "1.00"), emitente=CNPJ_FORNECEDOR, tp="0"))

    assert nossa_venda.saida_de(RAIZ) is True
    assert compra.saida_de(RAIZ) is False
    assert nossa_entrada.saida_de(RAIZ) is False
    assert devolucao.saida_de(RAIZ) is True
    # sem raiz não há lado: não se inventa um
    assert nossa_venda.saida_de("") is None


def test_o_filtro_fica_gravado_com_o_resultado(pasta, tmp_path):
    """Sem o retrato do filtro, meses depois não há como responder por que
    aquela lista tinha aquelas linhas."""
    destino = str(tmp_path / "saida")
    filtro = Filtro.de(ncms=["1905.90"], termos=["pao"])
    progresso = varrer([str(pasta / "nota2.xml")], destino, filtro)

    resumo = serializar(progresso, filtro)
    assert resumo["filtro"] == {"ncms": ["190590"], "termos": ["PAO"], "sem_filtro": False}
    assert resumo["elegiveis"] == 1
    assert resumo["centavos_elegiveis"] == 825
