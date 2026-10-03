"""Conferência com o relatório gerencial do cliente no lugar do XML.

O cliente nem sempre entrega XML: às vezes só solta o relatório de movimento
do ERP, uma linha por item, com a coluna "Chave DFe". Para o confronto ele faz
o mesmo papel do XML — diz que o documento existe — e é a segunda origem
possível de um documento entregue. Estes testes simulam o que chega de
verdade: chave repetida por item, chave suja, chave que o Excel estragou,
relatório que não é de movimento, e o relatório junto com o XML.
"""

from __future__ import annotations

import duckdb
import pytest

from cat.dominio.icms.cat42.conferencia import Origem
from cat.infraestrutura.analitico.confronto import confrontar
from cat.infraestrutura.analitico.extracao import extrair_efd, extrair_pasta
from cat.infraestrutura.planilhas.conferencia import (
    gerar_conferidas,
    gerar_nao_escrituradas,
)

# a mesma empresa e a mesma nota do teste de conferência
CNPJ = "11517841000278"
CHAVE_NA_EFD = "41210511517841000278550010000446231411953289"
CHAVE_SO_NO_RELATORIO = "41210511517841000278550010000446240000000009"

CABECALHO_EFD = (
    f"|0000|015|0|01052021|31052021|EMPRESA DE TESTE|{CNPJ}||PR"
    "|9030138187|4106902||||"
)
C100 = (
    f"|C100|0|0|C10252525|55|00|001|44623|{CHAVE_NA_EFD}"
    "|01052021|01052021|8,49|2|0,49|0|8,98|9|0|0|0|0|0|0|0|0|0|0|0|0|"
)

# cabeçalho real do relatório de movimento, reduzido (o mesmo de test_gerencial)
CABECALHO_MOVIMENTO = (
    "Código|Descricao|Código Barras|Trib|Dt Emissão|Número Dcto|Ent|"
    "Qtde;Unitária|Valor|BC ICMS|Valor ICMS|Valor BC ST;Informada|"
    "Valor ST;Informada|Valor FCP ST|CNPJ/CPF|UF|CFOP;Mvto|CST;ICMS|"
    "BC ICMS ST;XML|VR. ICMS ST;XML|ST integral|Chave DFe"
)

XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    f'<nfeProc><NFe><infNFe Id="NFe{CHAVE_NA_EFD}">'
    f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>"
)


def item(chave: str, codigo: str = "117110", numero: str = "44623") -> str:
    """Uma linha do relatório: um item de um documento."""
    return (f"{codigo}|Alface|789|0705|01/05/21|{numero}|1|160|280|280|0|0|0|0|"
            f"00176231110|PR|1.102|040|0|0|0|{chave}")


def escrever(tmp_path, nome: str, linhas: list[str]) -> str:
    caminho = tmp_path / nome
    caminho.write_bytes(("\r\n".join(linhas) + "\r\n").encode("latin-1"))
    return str(caminho)


@pytest.fixture
def efd(tmp_path) -> str:
    """Uma nota só na EFD: a que o relatório vai (ou não) confirmar."""
    arquivo = escrever(tmp_path, "efd.txt", [CABECALHO_EFD, C100])
    destino = str(tmp_path / "efd.parquet")
    extrair_efd([arquivo], destino)
    return destino


def _pasta(tmp_path, xmls: list[str], relatorios: list[str]):
    destino = str(tmp_path / "pasta.parquet")
    progresso = extrair_pasta(xmls, relatorios, destino)
    return destino, progresso


def _linhas(parquet: str, colunas: str = "*"):
    con = duckdb.connect()
    try:
        return con.execute(f"SELECT {colunas} FROM read_parquet('{parquet}')").fetchall()
    finally:
        con.close()


class TestSoRelatorio:
    """O cliente não mandou XML nenhum: só o relatório de movimento."""

    def test_o_relatorio_confirma_a_nota(self, efd, tmp_path):
        relatorio = escrever(tmp_path, "movimento.txt",
                             [CABECALHO_MOVIMENTO, item(CHAVE_NA_EFD)])
        pasta, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.documentos == 1
        assert progresso.recusados == []

        resumo = confrontar(efd, pasta, str(tmp_path / "saida"))
        assert resumo.conferidos == 1
        assert resumo.sem_documento == 0
        assert resumo.origens == [Origem.GERENCIAL]
        assert not any("não diz nada" in a for a in resumo.avisos)

    def test_a_lista_positiva_diz_que_veio_do_relatorio(self, efd, tmp_path):
        relatorio = escrever(tmp_path, "movimento.txt",
                             [CABECALHO_MOVIMENTO, item(CHAVE_NA_EFD)])
        pasta, _ = _pasta(tmp_path, [], [relatorio])
        destino = str(tmp_path / "saida")
        confrontar(efd, pasta, destino)

        [(origem, arquivo)] = _linhas(f"{destino}/conferidos.parquet",
                                      "origem, arquivo_do_documento")
        assert origem == "gerencial"
        assert arquivo == "movimento.txt"

        import openpyxl  # noqa: PLC0415

        xlsx = str(tmp_path / "conferidas.xlsx")
        gerar_conferidas(f"{destino}/conferidos.parquet", xlsx)
        aba = openpyxl.load_workbook(xlsx).active
        colunas = [c.value for c in aba[1]]
        assert aba.cell(row=2, column=colunas.index("Origem do documento") + 1
                        ).value == "Relatório do cliente"

    def test_uma_linha_por_item_e_um_documento_so(self, efd, tmp_path):
        # o relatório de movimento repete a chave em cada item da nota. Três
        # itens não são três documentos — e não podem virar três conferidos
        relatorio = escrever(tmp_path, "movimento.txt", [
            CABECALHO_MOVIMENTO,
            item(CHAVE_NA_EFD, codigo="117110"),
            item(CHAVE_NA_EFD, codigo="117111"),
            item(CHAVE_NA_EFD, codigo="117112"),
        ])
        pasta, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.documentos == 1

        resumo = confrontar(efd, pasta, str(tmp_path / "saida"))
        assert resumo.conferidos == 1
        assert resumo.documentos_na_pasta == 1

    def test_nota_do_relatorio_que_nao_esta_na_efd_e_nao_escriturada(
        self, efd, tmp_path
    ):
        relatorio = escrever(tmp_path, "movimento.txt", [
            CABECALHO_MOVIMENTO,
            item(CHAVE_NA_EFD),
            item(CHAVE_SO_NO_RELATORIO, numero="44624"),
        ])
        pasta, _ = _pasta(tmp_path, [], [relatorio])
        destino = str(tmp_path / "saida")
        resumo = confrontar(efd, pasta, destino)
        assert resumo.conferidos == 1
        assert resumo.nao_escrituradas == 1
        assert any("não estão na EFD" in a for a in resumo.avisos)

        [(chave, origem, arquivo)] = _linhas(
            f"{destino}/nao_escrituradas.parquet", "chave, origem, arquivo")
        assert (chave, origem, arquivo) == (CHAVE_SO_NO_RELATORIO, "gerencial",
                                            "movimento.txt")
        xlsx = str(tmp_path / "fora.xlsx")
        assert gerar_nao_escrituradas(f"{destino}/nao_escrituradas.parquet",
                                      xlsx) == 1


class TestRelatorioEXmlJuntos:
    def test_o_xml_vence_quando_os_dois_trazem_a_mesma_chave(self, efd, tmp_path):
        # regra da casa: XML é sempre o vencedor. O relatório só confirma o
        # que o XML já disse; a origem registrada é o XML
        xml = tmp_path / "nota.xml"
        xml.write_text(XML, encoding="utf-8")
        relatorio = escrever(tmp_path, "movimento.txt",
                             [CABECALHO_MOVIMENTO, item(CHAVE_NA_EFD)])
        pasta, progresso = _pasta(tmp_path, [str(xml)], [relatorio])
        assert progresso.documentos == 1          # uma chave, não duas

        destino = str(tmp_path / "saida")
        resumo = confrontar(efd, pasta, destino)
        assert resumo.conferidos == 1
        assert set(resumo.origens) == {Origem.XML}
        [(origem, arquivo)] = _linhas(f"{destino}/conferidos.parquet",
                                      "origem, arquivo_do_documento")
        assert origem == "xml"
        assert arquivo == "nota.xml"

    def test_o_relatorio_completa_o_que_o_xml_nao_cobre(self, tmp_path):
        # duas notas na EFD; XML de uma, relatório da outra: as duas conferem
        outra = CHAVE_SO_NO_RELATORIO
        c100_b = C100.replace(CHAVE_NA_EFD, outra).replace("|44623|", "|44624|")
        arquivo = escrever(tmp_path, "efd.txt", [CABECALHO_EFD, C100, c100_b])
        efd = str(tmp_path / "efd.parquet")
        extrair_efd([arquivo], efd)

        xml = tmp_path / "nota.xml"
        xml.write_text(XML, encoding="utf-8")
        relatorio = escrever(tmp_path, "movimento.txt",
                             [CABECALHO_MOVIMENTO, item(outra, numero="44624")])
        pasta, _ = _pasta(tmp_path, [str(xml)], [relatorio])

        destino = str(tmp_path / "saida")
        resumo = confrontar(efd, pasta, destino)
        assert resumo.escriturados == 2
        assert resumo.conferidos == 2
        assert resumo.sem_documento == 0
        assert set(resumo.origens) == {Origem.XML, Origem.GERENCIAL}
        origens = dict(_linhas(f"{destino}/conferidos.parquet", "chave, origem"))
        assert origens == {CHAVE_NA_EFD: "xml", outra: "gerencial"}


class TestChaveComoElaVem:
    """A coluna de chave do ERP raramente vem limpa."""

    def test_prefixo_nfe_espaco_e_pontuacao_nao_perdem_a_chave(self, efd, tmp_path):
        sujas = [
            f"NFe{CHAVE_NA_EFD}",                         # prefixo do Id do XML
            f"  {CHAVE_NA_EFD}  ",                        # espaço em volta
            " ".join(CHAVE_NA_EFD[i:i + 4] for i in range(0, 44, 4)),  # em blocos
        ]
        for i, suja in enumerate(sujas):
            relatorio = escrever(tmp_path, f"mov{i}.txt",
                                 [CABECALHO_MOVIMENTO, item(suja)])
            pasta, progresso = _pasta(tmp_path, [], [relatorio])
            assert progresso.documentos == 1, suja
            assert _linhas(pasta, "chave") == [(CHAVE_NA_EFD,)], suja

    def test_chave_estragada_pelo_excel_e_contada_e_avisada(self, efd, tmp_path):
        # o Excel converte 44 dígitos em número e grava "4,12105E+43": os
        # dígitos foram embora, não há como recuperar. Tem de aparecer — a
        # nota vai cair como pendente e alguém precisa saber por quê
        relatorio = escrever(tmp_path, "movimento.txt", [
            CABECALHO_MOVIMENTO,
            item("4,12105E+43"),
        ])
        pasta, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.documentos == 0
        assert len(progresso.recusados) == 1
        assert "1 linha(s) com chave ilegível" in progresso.recusados[0]
        assert "Excel" in progresso.recusados[0]
        assert "movimento.txt" in progresso.recusados[0]

        resumo = confrontar(efd, pasta, str(tmp_path / "saida"))
        assert resumo.sem_documento == 1          # a nota fica pendente


class TestPorQueNaoTemChave:
    """Três coisas diferentes, que a mensagem antiga tratava como uma só.

    Ela dizia sempre "costuma ser chave que o Excel converteu em número". Nos
    relatórios da empresa V isso era 0% dos casos: as 1.270 linhas sem chave
    tinham a coluna **vazia**, e 1.205 delas nem número de documento tinham —
    movimentação interna de estoque, CFOP 1.949, R$ 0,00 de ST. Chamar isso de
    problema de leitura enchia a tela de alarme e escondia falha de verdade.
    """

    def test_documento_identificado_sem_chave_e_recusado(self, efd, tmp_path):
        """A nota existe e está numerada, mas não dá para cruzar com a EFD.

        Isto é problema de quem entrega o dado: a nota vai cair como pendente
        e quem for cobrar precisa saber que o relatório a trazia."""
        relatorio = escrever(tmp_path, "movimento.txt", [
            CABECALHO_MOVIMENTO,
            item("", numero="44624"),
        ])
        _pasta_, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.documentos == 0
        assert progresso.observacoes == []
        assert len(progresso.recusados) == 1
        assert "1 linha(s) de documento identificado mas sem chave" in \
            progresso.recusados[0]
        assert "Excel" not in progresso.recusados[0]

    def test_linha_sem_documento_nenhum_nao_e_problema(self, efd, tmp_path):
        """Movimentação interna de estoque nunca teve nota.

        Sai do bloco de erro e vai para `observacoes`: continua visível, para
        a conta fechar, sem disputar atenção com arquivo que não abriu."""
        relatorio = escrever(tmp_path, "movimento.txt", [
            CABECALHO_MOVIMENTO,
            item("", numero=""),
            item("", numero=""),
        ])
        _pasta_, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.documentos == 0
        assert progresso.recusados == []
        assert len(progresso.observacoes) == 1
        assert "2 linha(s) sem documento nenhum" in progresso.observacoes[0]
        assert "movimentação interna" in progresso.observacoes[0]

    def test_os_tres_motivos_juntos_ficam_separados(self, efd, tmp_path):
        """Um arquivo com os três casos não vira uma linha só de aviso."""
        relatorio = escrever(tmp_path, "movimento.txt", [
            CABECALHO_MOVIMENTO,
            item("4,12105E+43"),
            item("", numero="44624"),
            item("", numero=""),
            item(CHAVE_NA_EFD),
        ])
        _pasta_, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.documentos == 1
        assert len(progresso.recusados) == 2
        assert len(progresso.observacoes) == 1
        assert any("chave ilegível" in r for r in progresso.recusados)
        assert any("documento identificado mas sem chave" in r
                   for r in progresso.recusados)

    def test_relatorio_limpo_nao_gera_observacao(self, efd, tmp_path):
        """Sem linha fora, nada aparece — nem no erro, nem na informação."""
        relatorio = escrever(tmp_path, "movimento.txt",
                             [CABECALHO_MOVIMENTO, item(CHAVE_NA_EFD)])
        _pasta_, progresso = _pasta(tmp_path, [], [relatorio])
        assert progresso.recusados == []
        assert progresso.observacoes == []


class TestRelatorioErrado:
    def test_inventario_nao_serve_para_conferir_e_diz_por_que(self, efd, tmp_path):
        # inventário não tem documento nem chave; passar por ele em silêncio
        # daria "0 documentos" sem explicação
        inventario = escrever(tmp_path, "inventario.txt", [
            "IFIS_UNID_CODIGO|IFIS_PROD_CODIGO|IFIS_PROD_DESCRICAO|IFIS_ESTOQUE|"
            "IFIS_CTFISCAL|IFIS_CTMEDIO|IFIS_DTULTCOMPRA|IFIS_CTEMPRESA|"
            "IFIS_VLRMEDIOUNICMS|IFIS_VLRMEDIOUNICMS_ST_BC|IFIS_VLRMEDIOUNICMS_ST|"
            "IFIS_VLRMEDIOUNFCP_ST|IFIS_ICMSALIQVIGENTE|IFIS_FCPALIQVIGENTE",
            "089|117307|Maca|1|0705|10,88|08/03/24|10,88|0|0|0|0|19,5|2",
        ])
        pasta, progresso = _pasta(tmp_path, [], [inventario])
        assert progresso.documentos == 0
        assert len(progresso.recusados) == 1
        assert "inventario.txt" in progresso.recusados[0]
        assert "movimento" in progresso.recusados[0].lower()

    def test_arquivo_ilegivel_nao_derruba_os_outros(self, efd, tmp_path):
        lixo = tmp_path / "lixo.txt"
        lixo.write_bytes(b"\x00\x01\x02 isto nao e um relatorio")
        bom = escrever(tmp_path, "movimento.txt",
                       [CABECALHO_MOVIMENTO, item(CHAVE_NA_EFD)])
        pasta, progresso = _pasta(tmp_path, [], [str(lixo), bom])
        assert progresso.documentos == 1
        assert progresso.arquivos_lidos == 2
        assert len(progresso.recusados) == 1
        assert "lixo.txt" in progresso.recusados[0]

        resumo = confrontar(efd, pasta, str(tmp_path / "saida"))
        assert resumo.conferidos == 1
