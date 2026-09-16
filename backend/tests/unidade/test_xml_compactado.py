"""XML dentro de zip: no lote, na conferência (etapa 3) e nos movimentos (etapa 3).

O zip é como o do portal: notas, um evento de cancelamento e um CT-e que cita
uma nota dentro do `infDoc`, tudo misturado.
"""

from __future__ import annotations

import zipfile

import pyarrow.parquet as pq
import pytest

from cat.dominio.lote import TipoDeArquivo
from cat.infraestrutura.analitico.canceladas import ARQUIVO_CHAVES_CANCELADAS, ler_chaves_canceladas
from cat.infraestrutura.analitico.extracao import extrair_pasta
from cat.infraestrutura.analitico.itens_do_xml import extrair_itens_do_xml
from cat.infraestrutura.arquivos.classificador import classificar
from cat.infraestrutura.arquivos.xml_compactado import contar_xml, conteudos_de_xml
from tests.unidade.test_canceladas import evento
from tests.unidade.test_itens_do_xml import ICMS60, det, nfe
from tests.unidade.test_movimentos import CNPJ

CHAVE_1 = "41210599888777000166550010000001231000000021"
CHAVE_2 = "41210599888777000166550010000001241000000022"
CHAVE_CANCELADA = "41210599888777000166550010000001251000000023"
CTE = (f'<?xml version="1.0"?><cteProc><CTe><infCte Id="CTe41210599888777000166570010000000011000000024">'
       f"<ide><mod>57</mod></ide><infCTeNorm><infDoc><infNFe><chave>{CHAVE_1}</chave></infNFe>"
       f"</infDoc></infCTeNorm></infCte></CTe></cteProc>").encode()


def zipar(caminho, membros: dict[str, bytes]) -> str:
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in membros.items():
            z.writestr(nome, conteudo)
    return str(caminho)


@pytest.fixture
def do_portal(tmp_path):
    return zipar(tmp_path / "baixados_2021_05.zip", {
        "maio/cte.xml": CTE,
        f"maio/{CHAVE_1}.xml": nfe(CHAVE_1, det(1, "F1", "5405", "1", "10.00", ICMS60)),
        f"maio/{CHAVE_2}.xml": nfe(CHAVE_2, det(1, "F2", "5405", "2", "20.00", ICMS60)),
        "maio/cancelamento.xml": evento(CHAVE_CANCELADA),
        "leia-me.txt": b"baixado do portal",
    })


class TestNoLote:
    def test_zip_com_nota_alimenta_e_diz_de_quem_e(self, do_portal):
        a = classificar(do_portal)
        assert a.tipo is TipoDeArquivo.XML_COMPACTADO and a.alimenta_a_cat
        assert (a.cnpj, a.cnpj_destinatario, a.competencia, a.detalhe) == (
            "99888777000166", CNPJ, None, "4 XML")

    def test_zip_sem_nota_continua_compactado(self, tmp_path):
        a = classificar(zipar(tmp_path / "ctes.zip", {"cte.xml": CTE, "b.txt": b"x"}))
        assert a.tipo is TipoDeArquivo.COMPACTADO and not a.alimenta_a_cat
        assert "NF-e" in a.motivo

    def test_zip_quebrado_nao_derruba(self, tmp_path):
        (tmp_path / "quebrado.zip").write_bytes(b"PK\x03\x04 nada")
        a = classificar(str(tmp_path / "quebrado.zip"))
        assert a.tipo is TipoDeArquivo.COMPACTADO and "ilegível" in a.motivo


class TestLeitura:
    def test_conta_um_por_xml_de_dentro(self, do_portal, tmp_path):
        solto = tmp_path / "solto.xml"
        solto.write_bytes(nfe(CHAVE_2, ""))
        (tmp_path / "quebrado.zip").write_bytes(b"PK")
        assert contar_xml([do_portal, str(solto), str(tmp_path / "quebrado.zip")]) == 5

    def test_nome_do_membro_leva_o_zip_e_o_quebrado_vai_para_recusados(self, do_portal, tmp_path):
        (tmp_path / "quebrado.zip").write_bytes(b"PK")
        recusados: list[str] = []
        nomes = [n for n, _ in conteudos_de_xml([do_portal, str(tmp_path / "quebrado.zip")],
                                                limite=100, recusados=recusados)]
        assert nomes[1].endswith(f"baixados_2021_05.zip > {CHAVE_1}.xml")
        assert len(nomes) == 4 and len(recusados) == 1


class TestZipDentroDeZip:
    def test_um_nivel_e_aberto_guardado_ou_comprimido(self, tmp_path):
        interno_guardado = tmp_path / "guardado.zip"
        zipar(interno_guardado, {f"{CHAVE_1}.xml": nfe(CHAVE_1, det(1, "F1", "5405", "1", "10.00", ICMS60))})
        interno_comprimido = tmp_path / "comprimido.zip"
        zipar(interno_comprimido, {f"{CHAVE_2}.xml": nfe(CHAVE_2, det(1, "F2", "5405", "1", "10.00", ICMS60)),
                                   "fundo.zip": b"PK nao entra: segundo nivel"})
        externo = str(tmp_path / "portal.zip")
        with zipfile.ZipFile(externo, "w") as z:
            z.write(interno_guardado, "lote1/guardado.zip", compress_type=zipfile.ZIP_STORED)
            z.write(interno_comprimido, "lote2/comprimido.zip", compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("quebrado.zip", b"PK isto nao e zip")

        a = classificar(externo)
        assert a.tipo is TipoDeArquivo.XML_COMPACTADO
        assert a.detalhe == "2 XML, 1 zip(s) de dentro ilegíveis"
        assert contar_xml([externo]) == 2
        recusados: list[str] = []
        nomes = [n for n, _ in conteudos_de_xml([externo], recusados=recusados)]
        assert [n.split("portal.zip > ")[1] for n in nomes] == [
            f"guardado.zip > {CHAVE_1}.xml", f"comprimido.zip > {CHAVE_2}.xml"]
        assert len(recusados) == 1 and recusados[0].startswith("portal.zip > quebrado.zip")


class TestNasEtapas:
    def test_conferencia_so_leva_as_notas(self, do_portal, tmp_path):
        destino = str(tmp_path / "pasta.parquet")
        progresso = extrair_pasta([do_portal], [], destino)
        linhas = pq.read_table(destino).to_pylist()
        assert sorted(l["chave"] for l in linhas) == [CHAVE_1, CHAVE_2]
        assert linhas[0]["arquivo"].startswith("baixados_2021_05.zip > ")
        assert (progresso.arquivos_totais, progresso.arquivos_lidos, progresso.recusados) == (4, 4, [])

    def test_movimentos_leem_os_itens_e_guardam_o_cancelamento(self, do_portal, tmp_path):
        destino = str(tmp_path / "saida")
        do_xml = extrair_itens_do_xml([do_portal], destino)
        assert (do_xml.arquivos_totais, do_xml.documentos, do_xml.itens) == (4, 2, 2)
        assert do_xml.cancelamentos == [(CHAVE_CANCELADA, "baixados_2021_05.zip > cancelamento.xml")]
        progresso = ler_chaves_canceladas([], destino, de_eventos=do_xml.cancelamentos)
        assert (progresso.eventos, progresso.chaves) == (1, 1)
        linhas = pq.read_table(f"{destino}/{ARQUIVO_CHAVES_CANCELADAS}").to_pylist()
        assert [(l["chave"], l["origem"]) for l in linhas] == [(CHAVE_CANCELADA, "evento")]
