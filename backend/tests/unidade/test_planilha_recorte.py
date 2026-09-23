"""O nome do arquivo de um recorte de planilha.

Nasceu da extração do razão por conta: marcar trinta contas na tela produzia
nome de arquivo com os trinta códigos, e o caminho passava do que o Windows
aceita — o download morria na gravação, depois de o servidor ter feito a
planilha inteira.
"""

from __future__ import annotations

from cat.aplicacao.casos_de_uso.planilhas import LIMITE_DO_SUFIXO, sufixo_do_recorte

CONTAS = frozenset({f"1.1.{n:02d}.0001" for n in range(1, 31)})


def test_sem_recorte_nao_ha_sufixo():
    assert sufixo_do_recorte(None, None) == ""
    assert sufixo_do_recorte(frozenset(), frozenset()) == ""


def test_recorte_pequeno_fica_legivel_no_nome():
    assert sufixo_do_recorte(None, frozenset({"3.1.1", "4.1.1"})) == "-3.1.1_4.1.1"


def test_a_ordem_de_marcar_nao_muda_o_arquivo():
    """Marcar 4.1.1 e depois 3.1.1 é a mesma seleção — e o mesmo arquivo."""
    um = sufixo_do_recorte(None, frozenset({"3.1.1", "4.1.1"}))
    outro = sufixo_do_recorte(None, frozenset({"4.1.1", "3.1.1"}))
    assert um == outro


def test_recorte_grande_vira_resumo_curto():
    sufixo = sufixo_do_recorte(None, CONTAS)

    assert len(sufixo) <= 13
    assert sufixo.startswith("-")
    # e continua sendo o mesmo arquivo para a mesma seleção
    assert sufixo == sufixo_do_recorte(None, CONTAS)


def test_selecoes_grandes_diferentes_nao_colidem():
    outra = frozenset(CONTAS - {"1.1.01.0001"})
    assert sufixo_do_recorte(None, CONTAS) != sufixo_do_recorte(None, outra)


def test_o_limite_vale_para_o_conjunto_e_nao_para_cada_parte():
    """Muitas contas curtas também estouram — o que conta é o texto inteiro."""
    curtas = frozenset({f"{n}" for n in range(100)})
    assert len("_".join(sorted(curtas))) > LIMITE_DO_SUFIXO
    assert len(sufixo_do_recorte(None, curtas)) <= 13
