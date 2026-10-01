"""As três teses por item têm de expor a mesma superfície.

`exclusoes.apurar` trata ICMS, ICMS-ST e ISS pelo mesmo molde: chama `apurar`
de cada módulo e, logo depois, `serializar` de cada um. Quem escreve um módulo
novo copia o anterior — e é aí que falta um reexporte.

Foi o que aconteceu: `exclusao_do_icms_st` e `exclusao_do_iss` importavam só
`Andamento`, `Motor` e `Resumo` de `exclusoes_por_item`, sem o `serializar`. Os
60 testes de exclusão passavam, porque nenhum deles olhava para a superfície
dos módulos — o erro só apareceu na tela do usuário, no meio de uma apuração:

    AttributeError: module 'cat.infraestrutura.analitico.exclusao_do_icms_st'
    has no attribute 'serializar'

Este teste é barato e fecha essa porta: se amanhã nascer uma quarta tese por
item, ela falha aqui e não na apuração do cliente.
"""

from __future__ import annotations

import pytest

from cat.infraestrutura.analitico import (
    exclusao_do_icms,
    exclusao_do_icms_st,
    exclusao_do_iss,
    exclusoes_por_item,
)

# o que `exclusoes.apurar` chama em cada módulo de tese
MODULOS = (
    ("ICMS", exclusao_do_icms),
    ("ICMS-ST", exclusao_do_icms_st),
    ("ISS", exclusao_do_iss),
)
ESPERADO = ("apurar", "serializar", "Andamento", "Resumo")


@pytest.mark.parametrize("nome,modulo", MODULOS, ids=[n for n, _ in MODULOS])
@pytest.mark.parametrize("atributo", ESPERADO)
def test_modulo_da_tese_expoe_o_que_a_etapa_chama(nome, modulo, atributo):
    assert hasattr(modulo, atributo), (
        f"{nome}: o módulo não expõe {atributo!r}. "
        "`exclusoes.apurar` chama isso nos três — reexporte de "
        "`exclusoes_por_item`, como o módulo do ICMS faz."
    )


@pytest.mark.parametrize("nome,modulo", MODULOS, ids=[n for n, _ in MODULOS])
def test_serializar_e_o_mesmo_para_as_tres_teses(nome, modulo):
    """Serializar diferente por tese faria o resumo mudar de forma sem aviso."""
    assert modulo.serializar is exclusoes_por_item.serializar, (
        f"{nome}: `serializar` não é o de `exclusoes_por_item`. "
        "O resumo das três teses tem de ter o mesmo formato."
    )


@pytest.mark.parametrize("nome,modulo", MODULOS, ids=[n for n, _ in MODULOS])
def test_tese_tem_nome_e_arquivo_proprios(nome, modulo):
    """Cada tese grava o seu parquet e entra no agregado com o seu nome."""
    teses = [v for k, v in vars(modulo).items() if k.startswith("TESE_")]
    arquivos = [v for k, v in vars(modulo).items() if k.startswith("ARQUIVO_")]
    assert len(teses) == 1, f"{nome}: esperava uma constante TESE_*, achei {teses}"
    assert len(arquivos) == 1, f"{nome}: esperava uma ARQUIVO_*, achei {arquivos}"
    assert str(arquivos[0]).endswith(".parquet")


def test_as_tres_teses_tem_nomes_distintos():
    """Dois módulos com a mesma TESE_* se sobrescreveriam no agregado."""
    nomes = []
    for _, modulo in MODULOS:
        nomes += [v for k, v in vars(modulo).items() if k.startswith("TESE_")]
    assert len(set(nomes)) == len(nomes), f"nomes de tese repetidos: {nomes}"
