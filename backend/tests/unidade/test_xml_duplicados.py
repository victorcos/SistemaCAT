"""A mesma nota em mais de um XML, e a nota de uso denegado.

Na empresa 04, 28.407 chaves vieram em mais de um arquivo (solta e no zip, em
dois zips), e 16 notas tinham protocolo de uso denegado. A cópia autorizada
vence a sem protocolo; a denegada sai, com todas as cópias.
"""

from __future__ import annotations

import zipfile
from decimal import Decimal

import pyarrow.parquet as pq

from cat.dominio.notafiscal.xml import cstat_do_fim, ler_documento_xml
from cat.infraestrutura.analitico.extracao import extrair_pasta
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML, extrair_itens_do_xml
from tests.unidade.test_itens_do_xml import ICMS60, det, nfe

D = Decimal
CHAVE = "41210599888777000166550010000001231000000031"
DENEGADA = "41210599888777000166550010000001241000000032"
OUTRA = "41210599888777000166550010000001251000000033"


def com_protocolo(xml: bytes, chave: str, cstat: str = "100") -> bytes:
    protocolo = (f'<protNFe versao="4.00"><infProt Id="ID1"><tpAmb>1</tpAmb><chNFe>{chave}</chNFe>'
                 f"<nProt>135210000000001</nProt><cStat>{cstat}</cStat><xMotivo>x</xMotivo></infProt></protNFe>")
    return xml.replace(b"</NFe></nfeProc>", f"</NFe>{protocolo}</nfeProc>".encode())


def nota(chave: str, valor: str) -> bytes:
    return nfe(chave, det(1, "F1", "5405", "1", valor, ICMS60))


def gravar(pasta, arquivos: dict[str, bytes]) -> list[str]:
    caminhos = []
    for nome, conteudo in arquivos.items():
        (pasta / nome).write_bytes(conteudo)
        caminhos.append(str(pasta / nome))
    return caminhos


class TestProtocolo:
    def test_autorizada_denegada_e_sem_protocolo(self):
        assert ler_documento_xml(com_protocolo(nota(CHAVE, "1.00"), CHAVE)).autorizado is True
        assert ler_documento_xml(com_protocolo(nota(CHAVE, "1.00"), CHAVE, "150")).autorizado is True
        denegada = ler_documento_xml(com_protocolo(nota(DENEGADA, "1.00"), DENEGADA, "302"))
        assert (denegada.cstat, denegada.autorizado) == ("302", False)
        assert ler_documento_xml(nota(CHAVE, "1.00")).autorizado is None

    def test_do_fim_do_arquivo(self):
        assert cstat_do_fim(com_protocolo(nota(CHAVE, "1.00"), CHAVE, "301")[-4096:]) == "301"
        assert cstat_do_fim(nota(CHAVE, "1.00")) is None


class TestNaEtapa3:
    def test_a_autorizada_fica_no_lugar_da_sem_protocolo_que_veio_antes(self, tmp_path):
        caminhos = gravar(tmp_path, {
            "a_erp.xml": nota(CHAVE, "10.00"),
            "b_portal.xml": com_protocolo(nota(CHAVE, "12.00"), CHAVE),
            "c_copia.xml": nota(CHAVE, "10.00"),
            "d_outra.xml": nota(OUTRA, "5.00"),
        })
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino)
        linhas = pq.read_table(f"{destino}/{ARQUIVO_ITENS_DO_XML}").to_pylist()
        da_chave = [l for l in linhas if l["chave"] == CHAVE]
        assert [(l["valor"], l["protocolo"], l["arquivo"]) for l in da_chave] == [(D("12.00"), "100", "b_portal.xml")]
        assert (progresso.documentos, progresso.itens, progresso.repetidos, progresso.copias_trocadas) == (2, 2, 2, 1)

    def test_entre_iguais_fica_a_primeira(self, tmp_path):
        caminhos = gravar(tmp_path, {
            "a.xml": com_protocolo(nota(CHAVE, "10.00"), CHAVE),
            "b.xml": com_protocolo(nota(CHAVE, "11.00"), CHAVE),
            "c.xml": nota(CHAVE, "12.00"),
        })
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino)
        linhas = pq.read_table(f"{destino}/{ARQUIVO_ITENS_DO_XML}").to_pylist()
        assert [l["arquivo"] for l in linhas] == ["a.xml"]
        assert (progresso.repetidos, progresso.copias_trocadas) == (2, 0)

    def test_denegada_sai_com_todas_as_copias(self, tmp_path):
        caminhos = gravar(tmp_path, {
            "a_sem_protocolo.xml": nota(DENEGADA, "10.00"),
            "b_denegada.xml": com_protocolo(nota(DENEGADA, "10.00"), DENEGADA, "301"),
            "c_outra.xml": nota(OUTRA, "5.00"),
        })
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino)
        linhas = pq.read_table(f"{destino}/{ARQUIVO_ITENS_DO_XML}").to_pylist()
        assert {l["chave"] for l in linhas} == {OUTRA}
        assert (progresso.documentos, progresso.itens, progresso.nao_autorizados) == (1, 1, 1)


class TestNaEtapa2:
    def test_conta_a_repetida_e_tira_a_denegada(self, tmp_path):
        soltos = gravar(tmp_path, {
            "nota.xml": com_protocolo(nota(CHAVE, "10.00"), CHAVE),
            "denegada_sem_protocolo.xml": nota(DENEGADA, "10.00"),
        })
        zip_ = tmp_path / "portal.zip"
        with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("nota.xml", nota(CHAVE, "10.00"))
            z.writestr("denegada.xml", com_protocolo(nota(DENEGADA, "10.00"), DENEGADA, "302"))
            z.writestr("outra.xml", nota(OUTRA, "5.00"))
        destino = str(tmp_path / "pasta.parquet")
        progresso = extrair_pasta(sorted(soltos) + [str(zip_)], [], destino)
        assert sorted(l["chave"] for l in pq.read_table(destino).to_pylist()) == [CHAVE, OUTRA]
        assert (progresso.documentos, progresso.xml_repetidos, progresso.xml_nao_autorizados) == (2, 1, 1)
