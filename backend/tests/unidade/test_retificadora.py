"""SPED retificador, do cabeçalho até o aviso na tela.

A retificadora substitui a original do mesmo estabelecimento e período por
inteiro — regra fiscal, não escolha nossa. Original e retificadora na mesma
pasta é o caso comum (a pasta `10 - RETIFICAÇÃO SPEDS` de um trabalho real
desta casa mostra isso). Ler as duas dobra os documentos do período e mistura
valores de antes e depois da retificação.
"""

from datetime import date

from cat.aplicacao.casos_de_uso.inspecionar_lote import inspecionar_pasta
from cat.dominio.icms.cat42.conferencia import ResumoDaConferencia
from cat.infraestrutura.arquivos.classificador import classificar

# raiz 44000003 — Irmãos Boa. COD_FIN é o campo antes de DT_INI: 0 / 1.
ORIGINAL_MAIO = (
    "|0000|018|0|01052025|31052025|EMPRESA T LTDA|44000003000109||SP"
    "|407048962113|3550308|||A|0|"
)
RETIFICADORA_MAIO = ORIGINAL_MAIO.replace("|0000|018|0|", "|0000|018|1|", 1)
ORIGINAL_JUNHO = ORIGINAL_MAIO.replace("01052025|31052025", "01062025|30062025")
# outra filial, mesmo período: a retificadora de uma não substitui a outra
ORIGINAL_MAIO_FILIAL = ORIGINAL_MAIO.replace("44000003000109", "44000003000281")


def escrever(pasta, nome, conteudo):
    caminho = pasta / nome
    caminho.write_bytes(conteudo.encode("latin-1"))
    return str(caminho)


class TestClassificador:
    def test_original(self, tmp_path):
        a = classificar(escrever(tmp_path, "maio.txt", ORIGINAL_MAIO))
        assert a.retificadora is False
        assert a.competencia == date(2025, 5, 1)

    def test_retificadora(self, tmp_path):
        a = classificar(escrever(tmp_path, "maio_retif.txt", RETIFICADORA_MAIO))
        assert a.retificadora is True


class TestResumoDoLote:
    def test_original_com_retificadora_do_mesmo_periodo_e_apontada(self, tmp_path):
        escrever(tmp_path, "maio.txt", ORIGINAL_MAIO)
        escrever(tmp_path, "maio_retif.txt", RETIFICADORA_MAIO)
        r = inspecionar_pasta(str(tmp_path), "44000003")
        assert r.total == 2                      # as duas ENTRAM no lote
        assert [a.nome for a in r.substituidas_por_retificadora] == ["maio.txt"]
        assert any("retificadora" in a for a in r.avisos)

    def test_periodos_diferentes_nao_se_substituem(self, tmp_path):
        escrever(tmp_path, "maio_retif.txt", RETIFICADORA_MAIO)
        escrever(tmp_path, "junho.txt", ORIGINAL_JUNHO)
        r = inspecionar_pasta(str(tmp_path), "44000003")
        assert r.substituidas_por_retificadora == []
        assert not any("retificadora" in a for a in r.avisos)

    def test_filiais_diferentes_nao_se_substituem(self, tmp_path):
        escrever(tmp_path, "maio_retif.txt", RETIFICADORA_MAIO)
        escrever(tmp_path, "maio_filial.txt", ORIGINAL_MAIO_FILIAL)
        r = inspecionar_pasta(str(tmp_path), "44000003")
        assert r.substituidas_por_retificadora == []


class TestAvisoDaConferencia:
    def test_diz_quantas_originais_ficaram_fora(self):
        r = ResumoDaConferencia(escriturados=10, efd_originais_substituidas=2)
        aviso = next(a for a in r.avisos if "retificadora" in a)
        assert aviso.startswith("2 EFD original(is)")

    def test_sem_substituicao_nao_avisa(self):
        r = ResumoDaConferencia(escriturados=10)
        assert not any("retificadora" in a for a in r.avisos)
