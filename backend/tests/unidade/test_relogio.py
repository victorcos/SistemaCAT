"""O relógio de progresso da conferência não pode rebaixar o que já contou.

Cada fase de extração conta a própria coisa: a EFD conta C100/C800, a leitura
da pasta conta chaves de XML. Numa base real de 37,9 milhões de documentos, a
tela mostrou "885 de 960 arquivos · 1 documentos · 0 B" durante o confronto —
o último tique da fase dos XML tinha escrito por cima dos totais da EFD, e o
limitador de dois segundos engoliu o tique final. Parecia travado; não estava.
"""

from types import SimpleNamespace

from cat.aplicacao.casos_de_uso.conferir_documentos import _Relogio
from cat.infraestrutura.analitico.extracao import Progresso


class SessaoFalsa:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass


def _execucao(total: int) -> SimpleNamespace:
    return SimpleNamespace(arquivos_totais=total, arquivos_lidos=0,
                           documentos=0, bytes_lidos=0, fracao=0.0)


def _relogio(total: int) -> tuple[_Relogio, SimpleNamespace, SessaoFalsa]:
    execucao, sessao = _execucao(total), SessaoFalsa()
    r = _Relogio(execucao, sessao, total)
    return r, execucao, sessao


def _tique(r: _Relogio, **campos) -> None:
    r.ultimo = -1e9          # força passar pelo limitador de dois segundos
    r.marcar(Progresso(**campos))


class TestFaseUnica:
    def test_marca_o_que_a_fase_conta(self):
        r, e, _ = _relogio(total=10)
        _tique(r, arquivos_totais=10, arquivos_lidos=4, documentos=1000, bytes_lidos=500)
        assert (e.arquivos_lidos, e.documentos, e.bytes_lidos) == (4, 1000, 500)
        assert e.fracao == 0.4

    def test_nunca_passa_de_95_por_cento_antes_do_confronto(self):
        r, e, _ = _relogio(total=10)
        _tique(r, arquivos_totais=10, arquivos_lidos=10, documentos=1, bytes_lidos=1)
        assert e.fracao == 0.95

    def test_o_limitador_engole_tiques_seguidos(self):
        r, e, s = _relogio(total=10)
        _tique(r, arquivos_totais=10, arquivos_lidos=1, documentos=1, bytes_lidos=1)
        r.marcar(Progresso(arquivos_totais=10, arquivos_lidos=2, documentos=2, bytes_lidos=2))
        assert e.arquivos_lidos == 1        # o segundo veio cedo demais
        assert s.commits == 1


class TestSegundaFase:
    """Depois da EFD, os XML: contam chaves, não documentos, e são poucos."""

    def _depois_da_efd(self):
        r, e, s = _relogio(total=960)
        _tique(r, arquivos_totais=900, arquivos_lidos=885, documentos=37_930_719,
               bytes_lidos=100_000_000_000)
        r.deslocar(900)
        r.congelar_totais(documentos=37_930_719, bytes_lidos=100_000_000_000)
        return r, e, s

    def test_congelar_grava_os_totais_na_hora(self):
        _, e, _ = self._depois_da_efd()
        # o tique final da EFD (900/900) que o limitador engoliria fica gravado
        assert e.arquivos_lidos == 900
        assert e.documentos == 37_930_719
        assert e.bytes_lidos == 100_000_000_000

    def test_a_fase_dos_xml_nao_rebaixa_documentos_nem_bytes(self):
        r, e, _ = self._depois_da_efd()
        # o defeito real: 1 chave de XML, 0 bytes — escrevia por cima
        _tique(r, arquivos_totais=60, arquivos_lidos=30, documentos=1, bytes_lidos=0)
        assert e.documentos == 37_930_719
        assert e.bytes_lidos == 100_000_000_000
        assert e.arquivos_lidos == 930          # 900 da EFD + 30 dos XML
        # 930/960 seria 96,9%, mas o teto de 95% antes do confronto vence
        assert e.fracao == 0.95
