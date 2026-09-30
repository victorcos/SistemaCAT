"""A Selic que vem do banco e se atualiza sozinha.

Quatro regras valem dinheiro, e as quatro estão medidas aqui:

- **mês guardado nunca é buscado de novo** — taxa de mês fechado não muda, e
  rebuscá-la é pagar rede para receber o que já se sabe;
- **mês guardado nunca é sobrescrito** — nem quando a API o devolve diferente.
  Divergência vira aviso; aplicar em silêncio seria mexer no número que já
  corrigiu um pedido;
- **rede fora não derruba a rodada** — segue o que está guardado;
- **série curta recusa** — corrigir a menos, calado, é o pior erro possível
  aqui, porque ninguém confere um número que veio pequeno.

O Banco Central entra por parâmetro (`baixar`), então nenhum teste daqui toca a
rede. Quem confere a série de verdade contra o SGS é `test_tab_selic.py`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.infraestrutura.repositorios.modelos import Base, SelicMensalDB
from cat.infraestrutura.selic import bcb, repositorio, servico
from cat.infraestrutura.sped.tabelas import tab_selic


@pytest.fixture
def sessao():
    """Um banco só deste teste, na memória: nada vaza para os outros."""
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    with sessionmaker(bind=motor, expire_on_commit=False)() as aberta:
        yield aberta


class Espiao:
    """Um Banco Central de mentira que anota o que lhe pediram."""

    def __init__(self, devolve: dict[str, Decimal] | None = None,
                 falha: bool = False) -> None:
        self.devolve = devolve or {}
        self.falha = falha
        self.pedidos: list[tuple[str, str]] = []

    def __call__(self, de: str, ate: str) -> dict[str, Decimal]:
        self.pedidos.append((de, ate))
        if self.falha:
            raise bcb.ConsultaAoBcbFalhou("de mentira")
        return dict(self.devolve)


class TestASemente:
    def test_banco_vazio_recebe_o_que_ja_existe_em_codigo(self, sessao):
        """"Sempre salvar no banco o que já existe" — o pedido, em teste."""
        espiao = Espiao()

        serie = servico.serie("2026-09", sessao=sessao, baixar=espiao)

        assert serie == tab_selic.MENSAL
        assert repositorio.ler(sessao) == tab_selic.MENSAL

    def test_a_semente_fica_marcada_como_do_repositorio(self, sessao):
        """Saber de onde veio um número que vira dinheiro é auditoria."""
        servico.serie("2026-09", sessao=sessao, baixar=Espiao())
        linha = sessao.get(SelicMensalDB, "2021-03")

        assert linha is not None
        assert linha.fonte == servico.FONTE_DO_REPOSITORIO


class TestOQueVaiARede:
    def test_nao_busca_nada_quando_o_banco_ja_cobre(self, sessao):
        """A série semeada vai até 09/2026; corrigir até lá não pede nada."""
        espiao = Espiao()

        servico.serie(tab_selic.ultimo_mes(), sessao=sessao, baixar=espiao)

        assert espiao.pedidos == []

    def test_busca_so_os_meses_que_faltam(self, sessao):
        """E um a mais para trás: é a sobreposição que denuncia revisão."""
        ultimo = tab_selic.ultimo_mes()                 # 2026-09, na semente
        primeiro_que_falta = tab_selic.seguinte(ultimo)  # 2026-10
        ate = tab_selic.seguinte(tab_selic.seguinte(primeiro_que_falta))  # 2026-12
        espiao = Espiao({primeiro_que_falta: Decimal("1.11"),
                         tab_selic.seguinte(primeiro_que_falta): Decimal("1.12")})

        serie = servico.serie(ate, sessao=sessao, baixar=espiao)

        assert espiao.pedidos == [(ultimo, tab_selic.anterior(ate))]
        assert serie[primeiro_que_falta] == Decimal("1.11")

    def test_o_que_veio_da_api_fica_guardado(self, sessao):
        proximo = tab_selic.seguinte(tab_selic.ultimo_mes())
        ate = tab_selic.seguinte(proximo)
        servico.serie(ate, sessao=sessao, baixar=Espiao({proximo: Decimal("1.11")}))

        linha = sessao.get(SelicMensalDB, proximo)
        assert linha is not None
        assert Decimal(linha.taxa) == Decimal("1.11")
        assert linha.fonte == bcb.FONTE

    def test_a_segunda_rodada_nao_volta_a_rede(self, sessao):
        """Buscado uma vez, guardado para sempre."""
        proximo = tab_selic.seguinte(tab_selic.ultimo_mes())
        ate = tab_selic.seguinte(proximo)
        servico.serie(ate, sessao=sessao, baixar=Espiao({proximo: Decimal("1.11")}))

        espiao = Espiao()
        servico.serie(ate, sessao=sessao, baixar=espiao)

        assert espiao.pedidos == []


class TestOQueONuncaMuda:
    def test_mes_guardado_nao_e_sobrescrito(self, sessao):
        """Nem quando o Banco Central devolve outro número para ele."""
        servico.serie("2026-09", sessao=sessao, baixar=Espiao())
        original = tab_selic.MENSAL["2026-09"]

        repositorio.gravar(sessao, {"2026-09": original + Decimal("9")}, bcb.FONTE)

        assert repositorio.ler(sessao)["2026-09"] == original

    def test_a_divergencia_vira_aviso(self, sessao, caplog):
        servico.serie("2026-09", sessao=sessao, baixar=Espiao())
        original = tab_selic.MENSAL["2026-09"]

        with caplog.at_level("WARNING"):
            repositorio.gravar(sessao, {"2026-09": original + Decimal("9")}, bcb.FONTE)

        assert any("difere" in r.getMessage() for r in caplog.records)


class TestQuandoARedeCai:
    def test_segue_com_o_que_esta_guardado(self, sessao):
        """Rodada não morre porque um serviço de fora saiu do ar."""
        proximo = tab_selic.seguinte(tab_selic.ultimo_mes())
        espiao = Espiao(falha=True)

        serie = servico.serie(tab_selic.seguinte(proximo), sessao=sessao, baixar=espiao)

        assert espiao.pedidos                      # tentou
        assert serie == tab_selic.MENSAL           # e seguiu com o que tinha

    def test_mas_a_serie_curta_recusa_a_conta(self, sessao):
        """Seguir com o que tem não é fingir que cobre o mês pedido."""
        proximo = tab_selic.seguinte(tab_selic.ultimo_mes())
        ate = tab_selic.seguinte(proximo)
        serie = servico.serie(ate, sessao=sessao, baixar=Espiao(falha=True))

        assert not servico.alcanca(ate, serie)
        with pytest.raises(tab_selic.SelicDesconhecida):
            servico.acumulada("2022-10", ate, serie)


class TestOClienteDoBancoCentral:
    def test_traduz_a_resposta_do_sgs(self):
        assert bcb._converter([
            {"data": "01/03/2021", "valor": "0.20"},
            {"data": "01/04/2021", "valor": "0.21"},
        ]) == {"2021-03": Decimal("0.20"), "2021-04": Decimal("0.21")}

    def test_linha_torta_nao_derruba_as_boas(self):
        """Cem meses não se perdem por causa de um."""
        assert bcb._converter([
            {"data": "01/03/2021", "valor": "0.20"},
            {"data": "sem sentido", "valor": "x"},
            {"valor": "0.21"},
        ]) == {"2021-03": Decimal("0.20")}

    def test_resposta_que_nao_e_lista_e_erro(self):
        with pytest.raises(bcb.ConsultaAoBcbFalhou):
            bcb._converter({"erro": "serviço indisponível"})
