"""Cópia exata de arquivo não entra duas vezes no lote.

A regra é por conteúdo, não por caminho — mas o hash só é calculado para quem
tem com quem se parecer (mesmo tamanho, tipo, CNPJ, competência e finalidade).
Os testes provam as três coisas que importam: cópia é barrada, conteúdo
diferente com a mesma assinatura passa, e quem não é candidato nem é lido.
"""

from datetime import date

from cat.aplicacao.casos_de_uso.inspecionar_lote import (
    ArquivoExistente,
    inspecionar_pasta,
)
from cat.infraestrutura.arquivos.classificador import hash_de

# raiz 50948371 — Irmãos Boa
CABECALHO = (
    "|0000|018|0|01052025|31052025|IRMAOS BOA LTDA|50948371000178||SP"
    "|407048962113|3550308|||A|0|"
)
C100_A = ("|C100|0|0|F001|55|00|001|00001|35250500000000000000550010000000011000000015"
          "|05052025|05052025|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")
# mesmo comprimento que a linha A, conteúdo diferente: mesma assinatura, outro hash
C100_B = C100_A.replace("00001|3525050000000000000055001000000001100000001", "00002|3525050000000000000055001000000002100000002")

SPED = CABECALHO + "\r\n" + C100_A + "\r\n"
SPED_MESMO_TAMANHO = CABECALHO + "\r\n" + C100_B + "\r\n"
SPED_MAIOR = SPED + C100_B + "\r\n"

assert len(SPED) == len(SPED_MESMO_TAMANHO), "as fixtures precisam ter o mesmo tamanho"


def escrever(pasta, nome, conteudo):
    caminho = pasta / nome
    caminho.write_bytes(conteudo.encode("latin-1"))
    return str(caminho)


class TestHash:
    def test_igual_para_conteudo_igual(self, tmp_path):
        a = escrever(tmp_path, "a.txt", SPED)
        b = escrever(tmp_path / "sub", "b.txt", SPED) if (tmp_path / "sub").mkdir() is None else None
        assert hash_de(a) == hash_de(b)
        assert len(hash_de(a)) == 64

    def test_diferente_para_conteudo_diferente(self, tmp_path):
        assert hash_de(escrever(tmp_path, "a.txt", SPED)) != \
            hash_de(escrever(tmp_path, "b.txt", SPED_MESMO_TAMANHO))


class TestNaMesmaPasta:
    def test_copia_exata_fica_de_fora_com_aviso(self, tmp_path):
        escrever(tmp_path, "maio.txt", SPED)
        (tmp_path / "backup").mkdir()
        escrever(tmp_path / "backup", "maio (2).txt", SPED)

        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 1
        assert len(r.copias) == 1
        copia, de_quem = r.copias[0]
        assert copia.nome == "maio (2).txt"
        assert de_quem.endswith("maio.txt")
        assert r.arquivos[0].hash_conteudo is not None
        assert any("cópia exata" in a for a in r.avisos)

    def test_mesma_assinatura_conteudo_diferente_entram_os_dois(self, tmp_path):
        escrever(tmp_path, "a.txt", SPED)
        escrever(tmp_path, "b.txt", SPED_MESMO_TAMANHO)
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 2 and not r.copias
        # foram candidatos, então foram hashados — e os hashes diferem
        hashes = {a.hash_conteudo for a in r.arquivos}
        assert None not in hashes and len(hashes) == 2

    def test_sem_candidato_ninguem_e_lido_inteiro(self, tmp_path):
        # tamanhos diferentes: assinatura diferente, nada a hashar
        escrever(tmp_path, "a.txt", SPED)
        escrever(tmp_path, "b.txt", SPED_MAIOR)
        r = inspecionar_pasta(str(tmp_path), "50948371")
        assert r.total == 2
        assert all(a.hash_conteudo is None for a in r.arquivos)


class TestContraOQueJaEstaNoTrabalho:
    def _existente(self, caminho, conteudo, com_hash=True):
        return ArquivoExistente(
            caminho=caminho, tamanho=len(conteudo.encode("latin-1")),
            tipo="sped_icms_ipi", cnpj="50948371000178",
            competencia=date(2025, 5, 1), retificadora=False,
            hash_conteudo=hash_de(caminho) if com_hash else None,
        )

    def test_copia_do_que_ja_esta_no_trabalho_e_barrada(self, tmp_path):
        antigo = escrever(tmp_path / "lote1", "maio.txt", SPED) if (tmp_path / "lote1").mkdir() is None else None
        (tmp_path / "lote2").mkdir()
        escrever(tmp_path / "lote2", "maio_de_novo.txt", SPED)

        r = inspecionar_pasta(str(tmp_path / "lote2"), "50948371",
                              existentes=(self._existente(antigo, SPED),))
        assert r.total == 0
        assert len(r.copias) == 1
        assert r.copias[0][1].startswith("já no trabalho")
        assert any("já está no trabalho" in a for a in r.avisos)

    def test_antigo_sem_hash_e_lido_na_hora(self, tmp_path):
        # importado antes desta regra: não tem hash gravado, mas está em disco
        (tmp_path / "lote1").mkdir()
        antigo = escrever(tmp_path / "lote1", "maio.txt", SPED)
        (tmp_path / "lote2").mkdir()
        escrever(tmp_path / "lote2", "copia.txt", SPED)

        r = inspecionar_pasta(str(tmp_path / "lote2"), "50948371",
                              existentes=(self._existente(antigo, SPED, com_hash=False),))
        assert r.total == 0 and len(r.copias) == 1

    def test_conteudo_diferente_do_antigo_entra(self, tmp_path):
        (tmp_path / "lote1").mkdir()
        antigo = escrever(tmp_path / "lote1", "maio.txt", SPED)
        (tmp_path / "lote2").mkdir()
        escrever(tmp_path / "lote2", "outro.txt", SPED_MESMO_TAMANHO)

        r = inspecionar_pasta(str(tmp_path / "lote2"), "50948371",
                              existentes=(self._existente(antigo, SPED),))
        assert r.total == 1 and not r.copias
