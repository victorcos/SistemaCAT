"""Classificação dos arquivos de um lote.

As amostras abaixo são reduções de arquivos reais desta casa: o registro 0000
de um EFD ICMS/IPI e de um EFD Contribuições, o cabeçalho do relatório do
Amigão, e a marca de erro do OneDrive que ocupava 149 dos 284 arquivos de uma
pasta de trabalho — o defeito que motivou reconhecê-la como tipo próprio.
"""

from datetime import date

import pytest

from cat.aplicacao.casos_de_uso.inspecionar_lote import (
    PastaInvalida,
    inspecionar_pasta,
)
from cat.dominio.lote import Grupo, TipoDeArquivo
from cat.infraestrutura.arquivos.classificador import classificar

# raiz 50948371 — Irmãos Boa
ICMS_IPI = (
    "|0000|018|0|01012025|31012025|IRMAOS BOA LTDA|50948371000178||SP"
    "|407048962113|3550308|||A|0|"
)
CONTRIBUICOES = (
    "|0000|006|0|||01062021|30062021|IRMAOS BOA LTDA"
    "|50948371000178|SP|3550308||00|2|"
)
# outra empresa, para provar que a separação por CNPJ funciona
DE_OUTRA_EMPRESA = (
    "|0000|018|0|01012025|31012025|OUTRA EMPRESA LTDA|11222333000181||MG"
    "|123456789|3106200|||A|0|"
)

GERENCIAL = (
    "Código|Descricao|Dt Emissão|Qtde;Unitária|CFOP;Mvto|Valor ICMS|"
    "Valor ST;Informada|VR. ICMS ST;XML"
)
INVENTARIO = (
    "IFIS_PROD_CODIGO|IFIS_PROD_DESCRICAO|IFIS_ESTOQUE|IFIS_CTMEDIO|"
    "IFIS_VLRMEDIOUNICMS_ST"
)

NFE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<nfeProc versao="4.00"><NFe><infNFe Id="NFe5020011151784100345555001">'
    "<ide><dhEmi>2025-03-14T10:22:00-03:00</dhEmi></ide>"
    "<emit><CNPJ>50948371000178</CNPJ></emit></infNFe></NFe></nfeProc>"
)

# o texto exato que o OneDrive deixa no lugar do arquivo que não desceu
STUB = (
    "The file size exceeds the allowed limit. \n\n"
    "CorrelationId: b1ff4894-2a8c-4606-8751-063cf05ba294, \n\n"
    "UTC DateTime: 08/26/2026 17:45:09"
)


def escrever(pasta, nome, conteudo, codificacao="latin-1"):
    caminho = pasta / nome
    caminho.write_bytes(conteudo.encode(codificacao))
    return str(caminho)


class TestClassificar:
    def test_efd_icms_ipi_e_o_que_alimenta_a_cat(self, tmp_path):
        a = classificar(escrever(tmp_path, "boa.txt", ICMS_IPI))
        assert a.tipo is TipoDeArquivo.SPED_ICMS_IPI
        assert a.tipo.grupo is Grupo.SPED
        assert a.alimenta_a_cat
        assert a.cnpj == "50948371000178"
        assert a.competencia == date(2025, 1, 1)
        assert a.uf == "SP"

    def test_efd_contribuicoes_e_reconhecida_mas_nao_serve(self, tmp_path):
        # entra na mesma pasta o tempo todo; PIS/COFINS não tem ICMS-ST
        a = classificar(escrever(tmp_path, "contrib.txt", CONTRIBUICOES))
        assert a.tipo is TipoDeArquivo.SPED_CONTRIBUICOES
        assert not a.alimenta_a_cat

    def test_xml_de_nfe(self, tmp_path):
        a = classificar(escrever(tmp_path, "nota.xml", NFE, "utf-8"))
        assert a.tipo is TipoDeArquivo.XML_NFE
        assert a.alimenta_a_cat
        assert a.cnpj == "50948371000178"
        assert a.competencia == date(2025, 3, 1)   # a competência é o mês

    def test_xml_que_nao_e_nota_nao_serve(self, tmp_path):
        outro = '<?xml version="1.0"?><procEventoNFe><evento/></procEventoNFe>'
        a = classificar(escrever(tmp_path, "evento.xml", outro, "utf-8"))
        assert a.tipo is TipoDeArquivo.XML_OUTRO
        assert not a.alimenta_a_cat

    def test_relatorio_de_movimento(self, tmp_path):
        conteudo = GERENCIAL + "\n1|Item|02/01/20|10|1.102|0|0|0\n"
        a = classificar(escrever(tmp_path, "entradas.txt", conteudo))
        assert a.tipo is TipoDeArquivo.GERENCIAL_MOVIMENTO
        assert a.alimenta_a_cat
        assert "traz ST do XML" in a.detalhe

    def test_relatorio_de_inventario(self, tmp_path):
        conteudo = INVENTARIO + "\n1|Item|10|5,00|0\n"
        a = classificar(escrever(tmp_path, "invfisc.txt", conteudo))
        assert a.tipo is TipoDeArquivo.GERENCIAL_INVENTARIO
        assert a.alimenta_a_cat

    def test_marca_de_erro_do_onedrive(self, tmp_path):
        a = classificar(escrever(tmp_path, "2023.02 - Entradas.txt_Error.txt", STUB))
        assert a.tipo is TipoDeArquivo.NAO_BAIXADO
        assert not a.alimenta_a_cat
        assert "exceeds the allowed limit" in a.motivo

    def test_arquivo_grande_com_nome_parecido_nao_vira_marca_de_erro(self, tmp_path):
        # nome sozinho não decide: precisa ser pequeno e ter o texto
        conteudo = ICMS_IPI + "\n" + ("|C100|x|\n" * 500)
        a = classificar(escrever(tmp_path, "base_Error.txt", conteudo))
        assert a.tipo is TipoDeArquivo.SPED_ICMS_IPI

    def test_arquivo_digital_da_cat42_e_reconhecido_e_nao_alimenta_a_apuracao(self, tmp_path):
        # sem | no começo: é o que o separa da EFD
        a = classificar(escrever(tmp_path, "CAT5_SP_50948371001301_1_2024.txt",
                                 "0000|012024|LOJA|50948371001301|798092322114|3552205|01|00\r\n"
                                 "0150|1|LOJA|1058|50948371001301||798092322114|3552205\r\n"))
        assert a.tipo is TipoDeArquivo.CAT42_ARQUIVO_DIGITAL
        assert not a.alimenta_a_cat
        assert (a.cnpj, a.competencia, a.detalhe) == ("50948371001301", date(2024, 1, 1), "LOJA")

    def test_compactado_nao_e_aberto(self, tmp_path):
        a = classificar(escrever(tmp_path, "base.rar", "Rar!\x1a\x07"))
        assert a.tipo is TipoDeArquivo.COMPACTADO
        assert not a.alimenta_a_cat

    def test_planilha_nao_e_reconhecida(self, tmp_path):
        a = classificar(escrever(tmp_path, "conferencia.xlsx", "PK\x03\x04"))
        assert a.tipo is TipoDeArquivo.DESCONHECIDO

    def test_arquivo_que_some_no_meio_nao_derruba(self, tmp_path):
        a = classificar(str(tmp_path / "nao_existe.txt"))
        assert a.tipo is TipoDeArquivo.DESCONHECIDO
        assert a.motivo


class TestInspecionarPasta:
    def test_conta_por_tipo_e_diz_o_que_serve(self, tmp_path):
        escrever(tmp_path, "boa.txt", ICMS_IPI)
        escrever(tmp_path, "contrib.txt", CONTRIBUICOES)
        escrever(tmp_path, "nota.xml", NFE, "utf-8")
        escrever(tmp_path, "base.rar", "Rar!")

        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 4
        assert len(r.uteis) == 2          # o SPED ICMS/IPI e o XML
        assert r.serve
        assert r.por_tipo[TipoDeArquivo.SPED_CONTRIBUICOES] == 1

    def test_arquivo_de_outra_empresa_fica_de_fora(self, tmp_path):
        escrever(tmp_path, "boa.txt", ICMS_IPI)
        escrever(tmp_path, "intruso.txt", DE_OUTRA_EMPRESA)

        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 1
        assert len(r.de_outra_empresa) == 1
        assert r.de_outra_empresa[0].cnpj == "11222333000181"
        assert any("outra empresa" in a for a in r.avisos)

    def test_relatorio_sem_cnpj_nao_e_tratado_como_intruso(self, tmp_path):
        # o ERP não se identifica no relatório; chutar deixaria de fora
        # justamente a fonte de quem não libera XML
        escrever(tmp_path, "entradas.txt", GERENCIAL + "\n1|I|02/01/20|1|1.102|0|0|0\n")
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 1
        assert not r.de_outra_empresa

    def test_avisa_quando_nada_serve(self, tmp_path):
        escrever(tmp_path, "contrib.txt", CONTRIBUICOES)
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert not r.serve
        assert any("alimenta a CAT 42" in a for a in r.avisos)

    def test_avisa_o_que_nao_baixou(self, tmp_path):
        escrever(tmp_path, "boa.txt", ICMS_IPI)
        escrever(tmp_path, "2023.02.txt_Error.txt", STUB)
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert any("sincronização" in a for a in r.avisos)

    def test_entra_em_subpasta(self, tmp_path):
        sub = tmp_path / "2025" / "01"
        sub.mkdir(parents=True)
        escrever(sub, "boa.txt", ICMS_IPI)
        assert inspecionar_pasta(str(tmp_path), "50948371").total == 1

    def test_pasta_que_nao_existe_avisa_com_jeito(self, tmp_path):
        with pytest.raises(PastaInvalida, match="não existe"):
            inspecionar_pasta(str(tmp_path / "nada"), "50948371")

    def test_caminho_de_arquivo_nao_serve_como_pasta(self, tmp_path):
        caminho = escrever(tmp_path, "boa.txt", ICMS_IPI)
        with pytest.raises(PastaInvalida, match="é um arquivo"):
            inspecionar_pasta(caminho, "50948371")

    def test_pasta_vazia_no_texto_avisa(self):
        with pytest.raises(PastaInvalida, match="Informe a pasta"):
            inspecionar_pasta("   ", "50948371")


class TestOrigensPermitidas:
    """A lista de pastas permitidas fecha a leitura do disco do servidor.

    Vazia por padrão, porque hoje o sistema roda na máquina de quem trabalha.
    No dia em que virar servidor compartilhado, sem isso qualquer usuário pede
    a listagem de qualquer pasta da máquina.
    """

    @pytest.fixture(autouse=True)
    def _limpar_cache(self):
        from cat.config import obter_config
        obter_config.cache_clear()
        yield
        obter_config.cache_clear()

    def test_vazia_libera(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CAT_PASTAS_PERMITIDAS", raising=False)
        escrever(tmp_path, "boa.txt", ICMS_IPI)
        assert inspecionar_pasta(str(tmp_path), "50948371").total == 1

    def test_fora_da_lista_e_recusada(self, tmp_path, monkeypatch):
        permitida = tmp_path / "permitida"
        outra = tmp_path / "outra"
        permitida.mkdir()
        outra.mkdir()
        escrever(outra, "boa.txt", ICMS_IPI)
        monkeypatch.setenv("CAT_PASTAS_PERMITIDAS", str(permitida))

        with pytest.raises(PastaInvalida, match="origens permitidas"):
            inspecionar_pasta(str(outra), "50948371")

    def test_subpasta_da_permitida_passa(self, tmp_path, monkeypatch):
        dentro = tmp_path / "2025"
        dentro.mkdir()
        escrever(dentro, "boa.txt", ICMS_IPI)
        monkeypatch.setenv("CAT_PASTAS_PERMITIDAS", str(tmp_path))

        assert inspecionar_pasta(str(dentro), "50948371").total == 1


# NF-e de FORNECEDOR: emitente é outra raiz, destinatário é a empresa do
# projeto (raiz 50948371). É a nota de compra — o insumo principal da CAT 42.
NFE_DE_FORNECEDOR = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<nfeProc versao="4.00"><NFe><infNFe Id="NFe4125031151784100027855001000044623141195329">'
    "<ide><dhEmi>2025-03-14T10:22:00-03:00</dhEmi></ide>"
    "<emit><CNPJ>11517841000278</CNPJ><xNome>FORNECEDOR LTDA</xNome></emit>"
    "<dest><CNPJ>50948371000178</CNPJ><xNome>IRMAOS BOA</xNome></dest>"
    "</infNFe></NFe></nfeProc>"
)
# nem emitente nem destinatário são da empresa: essa sim é de outra
NFE_ALHEIA = NFE_DE_FORNECEDOR.replace("50948371000178", "99999999000191")
# venda a consumidor: <dest> tem CPF, não CNPJ — só o emitente identifica
NFE_A_CONSUMIDOR = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<nfeProc versao="4.00"><NFe><infNFe Id="NFe3525035094837100017865001000000010000000015">'
    "<ide><dhEmi>2025-03-14T10:22:00-03:00</dhEmi></ide>"
    "<emit><CNPJ>50948371000178</CNPJ></emit>"
    "<dest><CPF>00176231110</CPF></dest>"
    "</infNFe></NFe></nfeProc>"
)


class TestXmlDeFornecedor:
    """A empresa pode ser o emitente OU o destinatário da nota.

    A primeira versão comparava só o emitente e jogava fora toda nota de
    compra como "de outra empresa". Não apareceu no primeiro teste real porque
    os 884 XML eram de emissão própria; num varejista importando nota de
    fornecedor, apareceria na primeira pasta.
    """

    def test_classificador_extrai_as_duas_pontas(self, tmp_path):
        a = classificar(escrever(tmp_path, "compra.xml", NFE_DE_FORNECEDOR, "utf-8"))
        assert a.cnpj == "11517841000278"              # emitente: o fornecedor
        assert a.cnpj_destinatario == "50948371000178"  # destinatário: a empresa

    def test_nota_de_compra_entra_no_lote(self, tmp_path):
        escrever(tmp_path, "compra.xml", NFE_DE_FORNECEDOR, "utf-8")
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 1
        assert not r.de_outra_empresa

    def test_nota_de_emissao_propria_continua_entrando(self, tmp_path):
        escrever(tmp_path, "venda.xml", NFE, "utf-8")
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 1 and not r.de_outra_empresa

    def test_venda_a_consumidor_sem_cnpj_no_destinatario(self, tmp_path):
        a = classificar(escrever(tmp_path, "cupom.xml", NFE_A_CONSUMIDOR, "utf-8"))
        assert a.cnpj == "50948371000178"
        assert a.cnpj_destinatario is None
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 1 and not r.de_outra_empresa

    def test_nota_sem_nenhuma_ponta_da_empresa_fica_de_fora(self, tmp_path):
        escrever(tmp_path, "alheia.xml", NFE_ALHEIA, "utf-8")
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 0
        assert len(r.de_outra_empresa) == 1
