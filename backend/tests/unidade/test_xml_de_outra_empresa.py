"""A nota que não é da empresa do trabalho não entra na leitura dos XML.

A importação já separa o XML solto de outra empresa (`inspecionar_lote`), mas o
**zip entra fechado**: o portal entrega a pasta do grupo, e dentro dela vêm as
notas de outro CNPJ. Quem quebra os XML abre uma a uma — é aqui, e só aqui, que
esse descarte pode ser feito.

A empresa pode estar em qualquer uma das duas pontas: emitente na venda,
destinatário na compra. A nota só sai quando **nenhuma** ponta conhecida é dela.
"""

from __future__ import annotations

import zipfile

import pyarrow.parquet as pq

from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML, extrair_itens_do_xml
from tests.unidade.test_itens_do_xml import ICMS60, det, nfe
from tests.unidade.test_movimentos import CNPJ

RAIZ = CNPJ[:8]                       # 44000002
FORNECEDOR = "99888777000166"
ESTRANHA = "22333444000155"
DE_FORA = "77666555000144"

VENDA = "41210544000002000237550010000001231000000030"
COMPRA = "41210599888777000166550010000001241000000032"
ALHEIA = "41210522333444000155550010000001251000000033"


def nota(chave: str, emit: str, dest: str = CNPJ) -> bytes:
    xml = nfe(chave, det(1, "F1", "5405", "1", "10.00", ICMS60), emit=emit)
    return xml.replace(f"<dest><CNPJ>{CNPJ}</CNPJ></dest>".encode(),
                       f"<dest><CNPJ>{dest}</CNPJ></dest>".encode())


def gravar(pasta, arquivos: dict[str, bytes]) -> list[str]:
    for nome, conteudo in arquivos.items():
        (pasta / nome).write_bytes(conteudo)
    return [str(pasta / nome) for nome in arquivos]


def chaves(destino: str) -> set[str]:
    return {l["chave"] for l in pq.read_table(f"{destino}/{ARQUIVO_ITENS_DO_XML}").to_pylist()}


class TestDuasPontas:
    def test_venda_e_compra_da_empresa_entram(self, tmp_path):
        caminhos = gravar(tmp_path, {
            "venda.xml": nota(VENDA, emit=CNPJ),
            "compra.xml": nota(COMPRA, emit=FORNECEDOR, dest=CNPJ),
        })
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino, cnpj_raiz=RAIZ)
        assert progresso.de_outra_empresa == 0
        assert chaves(destino) == {VENDA, COMPRA}

    def test_nota_sem_a_empresa_em_ponta_nenhuma_fica_de_fora(self, tmp_path):
        caminhos = gravar(tmp_path, {
            "venda.xml": nota(VENDA, emit=CNPJ),
            "alheia.xml": nota(ALHEIA, emit=ESTRANHA, dest=DE_FORA),
        })
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino, cnpj_raiz=RAIZ)
        assert (progresso.de_outra_empresa, progresso.documentos) == (1, 1)
        assert progresso.cnpjs_de_fora == {ESTRANHA[:8]: 1}
        assert chaves(destino) == {VENDA}

    def test_a_filial_entra_pela_raiz(self, tmp_path):
        """Outra filial é a mesma empresa: o cadastro é por raiz de CNPJ."""
        filial = RAIZ + "000359"
        caminhos = gravar(tmp_path, {"filial.xml": nota(VENDA, emit=filial, dest=DE_FORA)})
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino, cnpj_raiz=RAIZ)
        assert (progresso.de_outra_empresa, progresso.documentos) == (0, 1)


class TestSemRaiz:
    def test_sem_raiz_nada_e_descartado(self, tmp_path):
        """Leitura avulsa e trabalho sem CNPJ no cadastro leem tudo, como antes."""
        caminhos = gravar(tmp_path, {"alheia.xml": nota(ALHEIA, emit=ESTRANHA, dest=DE_FORA)})
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml(caminhos, destino)
        assert (progresso.de_outra_empresa, progresso.documentos) == (0, 1)


class TestDentroDoZip:
    def test_o_zip_do_portal_traz_o_grupo_e_so_a_empresa_fica(self, tmp_path):
        """O caso que motivou tudo: 7.186 arquivos de uma pasta de rede, com o
        zip do portal trazendo as notas de todas as empresas do grupo."""
        caminho = tmp_path / "portal.zip"
        with zipfile.ZipFile(caminho, "w") as zip_:
            zip_.writestr("venda.xml", nota(VENDA, emit=CNPJ))
            zip_.writestr("compra.xml", nota(COMPRA, emit=FORNECEDOR, dest=CNPJ))
            zip_.writestr("alheia.xml", nota(ALHEIA, emit=ESTRANHA, dest=DE_FORA))
        destino = str(tmp_path / "saida")
        progresso = extrair_itens_do_xml([str(caminho)], destino, cnpj_raiz=RAIZ)
        assert (progresso.de_outra_empresa, progresso.documentos) == (1, 2)
        assert chaves(destino) == {VENDA, COMPRA}
