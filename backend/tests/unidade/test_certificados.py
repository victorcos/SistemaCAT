"""Certificado digital na pasta do cliente: não se abre, não se lista.

A pasta da Advertising tem `05 - CERTIFICADO` e `10 - RETIFICAÇÃO SPEDS/CERTIFICADOS`,
com arquivos .pfx cujo nome carrega a senha. O lote, os zips das etapas 2 e 3 e a
pré-validação passam por eles sem abrir e sem guardar o nome.
"""

from __future__ import annotations

import zipfile

import pytest

from cat.aplicacao.casos_de_uso import inspecionar_lote
from cat.aplicacao.casos_de_uso.inspecionar_lote import PastaInvalida, inspecionar_pasta
from cat.infraestrutura.analitico.pre_validacao_do_cliente import ResumoDaPreValidacao, candidatos
from cat.infraestrutura.arquivos.xml_compactado import contar_xml, conteudos_de_xml
from tests.unidade.test_itens_do_xml import ICMS60, det, nfe
from tests.unidade.test_lote import ICMS_IPI

SENHA = "senha 1234"
CHAVE = "41210599888777000166550010000001231000000041"


@pytest.fixture
def pasta_do_cliente(tmp_path):
    raiz = tmp_path / "CAT 42 - Cliente"
    (raiz / "05 - CERTIFICADO").mkdir(parents=True)
    (raiz / "05 - CERTIFICADO" / f"empresa {SENHA}.pfx").write_bytes(b"\x30\x82 segredo")
    (raiz / "10 - RETIFICACAO SPEDS" / "CERTIFICADOS").mkdir(parents=True)
    (raiz / "10 - RETIFICACAO SPEDS" / "CERTIFICADOS" / f"outro {SENHA}.txt").write_bytes(ICMS_IPI.encode("latin-1"))
    (raiz / "10 - RETIFICACAO SPEDS" / "SPEDS").mkdir()
    (raiz / "10 - RETIFICACAO SPEDS" / "SPEDS" / "efd_retificada.txt").write_bytes(ICMS_IPI.encode("latin-1"))
    (raiz / "Certificadora Parceira").mkdir()
    (raiz / "Certificadora Parceira" / "efd.txt").write_bytes(ICMS_IPI.encode("latin-1"))
    (raiz / f"avulso {SENHA}.P12").write_bytes(b"\x30\x82 segredo")
    return raiz


class TestNoLote:
    def test_nao_abre_nem_guarda_o_nome(self, pasta_do_cliente, monkeypatch):
        abertos: list[str] = []
        original = inspecionar_lote.classificar
        monkeypatch.setattr(inspecionar_lote, "classificar",
                            lambda caminho, tamanho=None: abertos.append(caminho) or original(caminho, tamanho))

        resumo = inspecionar_pasta(str(pasta_do_cliente), "50948371")

        assert not [c for c in abertos if SENHA in c or "CERTIFICADO\\" in c.upper() or "CERTIFICADOS\\" in c.upper()]
        assert any(c.endswith("efd.txt") for c in abertos)  # "Certificadora Parceira" não é certificado
        assert sorted(a.nome for a in resumo.arquivos + resumo.de_outra_empresa + [c for c, _ in resumo.copias]) == ["efd.txt", "efd_retificada.txt"]
        assert (resumo.certificados.pastas, resumo.certificados.arquivos) == (2, 1)
        aviso = next(a for a in resumo.avisos if "certificado" in a)
        assert "2 pasta(s) de certificado e 1 arquivo(s) de certificado" in aviso
        assert SENHA not in " ".join(resumo.avisos)

    def test_pasta_escolhida_dentro_do_certificado_e_recusada(self, pasta_do_cliente):
        with pytest.raises(PastaInvalida, match="certificado digital"):
            inspecionar_pasta(str(pasta_do_cliente / "10 - RETIFICACAO SPEDS" / "CERTIFICADOS"), "50948371")


class TestNosZips:
    def test_xml_e_zip_de_certificado_ficam_de_fora(self, tmp_path):
        interno = tmp_path / "interno.zip"
        with zipfile.ZipFile(interno, "w") as z:
            z.writestr("nota.xml", nfe(CHAVE, det(1, "F1", "5405", "1", "1.00", ICMS60)))
        caminho = tmp_path / "portal.zip"
        with zipfile.ZipFile(caminho, "w") as z:
            z.writestr(f"CERTIFICADOS/{SENHA}.xml", b"<nada/>")
            z.writestr(f"{SENHA}.pfx", b"\x30\x82")
            z.write(interno, "certificado.zip")
            z.writestr("notas/nota.xml", nfe(CHAVE, det(1, "F1", "5405", "1", "1.00", ICMS60)))
        recusados: list[str] = []
        nomes = [n for n, _ in conteudos_de_xml([str(caminho)], recusados=recusados)]
        assert [n.rsplit(" > ", 1)[1] for n in nomes] == ["nota.xml"]
        assert contar_xml([str(caminho)]) == 1
        assert recusados == []

    def test_pre_validacao_nao_le_txt_de_pasta_de_certificado(self, tmp_path):
        caminho = tmp_path / "entrega.zip"
        with zipfile.ZipFile(caminho, "w") as z:
            z.writestr(f"05 - CERTIFICADO/{SENHA}.txt", b"0000|")
            z.writestr("CAT5_SP_43112531000421_1_2024.txt", b"0000|")
        resumo = ResumoDaPreValidacao()
        achados = [c.nome for c in candidatos([str(caminho)], resumo, str(tmp_path))]
        assert achados == ["CAT5_SP_43112531000421_1_2024.txt"]
