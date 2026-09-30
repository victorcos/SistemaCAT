"""A lista de etapas que aceitam cancelamento não pode envelhecer.

Ela já envelheceu uma vez: ficou com seis etapas enquanto o sistema passava a
onze, e cinco rodadas longas recusavam cancelamento **mesmo sabendo parar** —
a quebra de SPED, a apuração de PIS/COFINS, as exclusões, a Gestão e o crédito
outorgado. Quem pôs 71 arquivos na fila por engano esperava a rodada inteira, e
a tela dizia "esta etapa ainda não aceita cancelamento", que era mentira.

O defeito é de uma classe chata: nada quebra quando alguém acrescenta o freio a
uma etapa nova e esquece a lista. O código roda, o teste passa, e só o usuário
descobre — meses depois, no pior momento.

Por isso este teste lê o **código-fonte** dos casos de uso, e não a lista: quem
constrói um `Freio` declara saber parar, e tem de estar lá.
"""

import re
from pathlib import Path

from cat.aplicacao.casos_de_uso.rodada import ETAPAS_CANCELAVEIS

CASOS_DE_USO = Path(__file__).resolve().parents[2] / "cat" / "aplicacao" / "casos_de_uso"

# as que ainda não sabem parar. Estar aqui é declaração, não desculpa: o dia de
# dar freio a uma delas é o dia de tirá-la desta lista
SEM_FREIO = {"conferencia", "movimentos", "quebra_xml"}


def etapas_do_codigo() -> dict[str, bool]:
    """Cada etapa e se o caso de uso dela constrói um `Freio`."""
    achadas: dict[str, bool] = {}
    for arquivo in CASOS_DE_USO.glob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        nome = re.search(r'^ETAPA = "([^"]+)"', fonte, re.MULTILINE)
        if nome:
            achadas[nome.group(1)] = "Freio(" in fonte
    return achadas


class TestQuemAceitaCancelamento:
    def test_toda_etapa_com_freio_esta_na_lista(self):
        """O esquecimento que este teste existe para pegar."""
        com_freio = {etapa for etapa, freia in etapas_do_codigo().items() if freia}
        assert com_freio - ETAPAS_CANCELAVEIS == set(), (
            "etapa que sabe parar e a tela recusa cancelar")

    def test_nenhuma_etapa_sem_freio_esta_na_lista(self):
        """O oposto é pior: a tela diria que vai parar uma rodada que não para."""
        sem_freio = {etapa for etapa, freia in etapas_do_codigo().items() if not freia}
        assert sem_freio & ETAPAS_CANCELAVEIS == set(), (
            "etapa na lista sem conferir o freio: o cancelamento ficaria pendurado")

    def test_as_tres_que_ainda_nao_param_continuam_nomeadas(self):
        """Se uma delas ganhar freio, este teste cobra a atualização das duas listas."""
        assert {e for e, freia in etapas_do_codigo().items() if not freia} == SEM_FREIO

    def test_o_codigo_tem_etapa_para_todas(self):
        """Uma varredura que não acha nada passaria calada nos testes acima."""
        assert len(etapas_do_codigo()) >= 14
