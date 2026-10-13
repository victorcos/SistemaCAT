"""A lista que ajuda quem liga dois códigos à mão.

`propor` só devolve o que prova — GTIN igual, sufixo repetido, kit, ou metade
das palavras em comum. É deliberado: proposta fraca vira trabalho de recusar.

Mas o código que sobra sem par tem de ser decidido por alguém, e essa pessoa
estava **digitando o código de destino de cabeça**: a tela não mostrava a
descrição do outro lado nem deixava procurar. `ordenar_candidatos` existe para
essa escolha — não propõe e não decide, só põe o provável na frente.

A linha que estes testes guardam é a que separa as duas coisas: **o que
identifica o produto dá entrada na lista; o que descreve a forma do problema
só desempata.** Todo código de compra tem entrada e não tem saída; se isso
bastasse para entrar, um parafuso subiria na lista de uma castanha.
"""

from __future__ import annotations

from decimal import Decimal

from cat.dominio.depara.candidatos import ItemParaCasar, ordenar_candidatos

D = Decimal


def item(codigo, entradas=0, saidas=0, descricao="", ncm="08013200", gtins=()):
    return ItemParaCasar(codigo=codigo, descricao=descricao, ncm=ncm,
                         gtins=frozenset(gtins), entradas=D(entradas), saidas=D(saidas))


# o código de marketplace da empresa 04: vende e nunca entra
SEM_PAR = item("X00450IETL", saidas=120, descricao="CASTANHA ESCURA 500G")

ESPELHO = item("X00450IETL  08", entradas=20, descricao="CASTANHA ESCURA 500G")
MESMA_DESCRICAO = item("4450", entradas=300, descricao="CAST. ESCURO 500G")
O_KIT = item("4450K3", entradas=50, saidas=10, descricao="KIT 3X CAST. ESCURO 500G")
OUTRO_PRODUTO = item("9999", entradas=900, descricao="PARAFUSO SEXTAVADO", ncm="73181500")
CATALOGO = [MESMA_DESCRICAO, O_KIT, OUTRO_PRODUTO, ESPELHO]


def codigos(candidatos):
    return [c.item.codigo for c in candidatos]


class TestOQueEntraNaLista:
    def test_o_produto_sem_nada_em_comum_nao_entra(self):
        """**O ponto todo.** Sem isto, metade do catálogo entra em toda busca:
        todo código de compra tem entrada e não tem saída."""
        assert OUTRO_PRODUTO.codigo not in codigos(ordenar_candidatos(SEM_PAR, CATALOGO))

    def test_mas_entra_quando_a_pessoa_pede_pelo_nome(self):
        """Quem digitou "parafuso" já disse o que quer ver. Esconder aí seria a
        tela discordando de quem está decidindo."""
        achados = ordenar_candidatos(SEM_PAR, CATALOGO, busca="parafuso")

        assert codigos(achados) == [OUTRO_PRODUTO.codigo]

    def test_o_proprio_codigo_nunca_entra(self):
        """Ligar um código a ele mesmo é o que `DePara.Validar` recusa; oferecer
        seria convidar ao erro."""
        achados = ordenar_candidatos(SEM_PAR, [SEM_PAR, *CATALOGO])

        assert SEM_PAR.codigo not in codigos(achados)

    def test_o_mesmo_codigo_com_espacos_tambem_nao(self):
        """O ERP da empresa 04 grava `1012           08`: comparar sem normalizar
        ofereceria o código a ele mesmo com outra cara."""
        com_espacos = item("X00450IETL", entradas=5, descricao="CASTANHA ESCURA 500G")

        achados = ordenar_candidatos(SEM_PAR, [com_espacos])

        assert achados == []


class TestAOrdem:
    def test_o_espelho_vem_antes_de_todos(self):
        """Mesma descrição, mesmo NCM, o código começando o outro e entrada sem
        saída: é o par que conserta a ficha."""
        assert codigos(ordenar_candidatos(SEM_PAR, CATALOGO))[0] == ESPELHO.codigo

    def test_quem_tem_entrada_e_nao_tem_saida_passa_na_frente(self):
        """Entre dois parecidos, o que tem a forma do problema vence."""
        achados = ordenar_candidatos(SEM_PAR, [O_KIT, MESMA_DESCRICAO])

        assert codigos(achados) == [MESMA_DESCRICAO.codigo, O_KIT.codigo]

    def test_o_codigo_de_barras_pesa_mais_que_a_descricao(self):
        """GTIN é prova; descrição é indício. Um produto rebatizado no cadastro
        continua sendo o mesmo."""
        por_gtin = item("77", entradas=1, descricao="NADA A VER",
                        ncm="99999999", gtins=["7891000315507"])
        origem = ItemParaCasar(codigo="X1", descricao="CASTANHA ESCURA 500G",
                               ncm="08013200", saidas=D(10),
                               gtins=frozenset(["7891000315507"]))

        achados = ordenar_candidatos(origem, [por_gtin, MESMA_DESCRICAO])

        assert codigos(achados)[0] == por_gtin.codigo

    def test_gtin_invalido_nao_liga_nada(self):
        """Dígito verificador errado é lixo de cadastro, e ligar por ele juntaria
        produtos diferentes — a mesma regra que `propor` já segue."""
        falso = item("88", entradas=1, descricao="NADA A VER",
                     ncm="99999999", gtins=["1111111111111"])
        origem = ItemParaCasar(codigo="X1", descricao="OUTRA COISA", ncm="11111111",
                               saidas=D(10), gtins=frozenset(["1111111111111"]))

        assert ordenar_candidatos(origem, [falso]) == []


class TestABusca:
    def test_acha_pela_descricao_sem_acento_e_sem_pontuacao(self):
        """Quem digita "cast esc" tem de achar "CAST. ESCURO"."""
        achados = ordenar_candidatos(SEM_PAR, CATALOGO, busca="cast esc")

        assert MESMA_DESCRICAO.codigo in codigos(achados)

    def test_acha_por_pedaco_do_codigo(self):
        achados = ordenar_candidatos(SEM_PAR, CATALOGO, busca="4450")

        assert set(codigos(achados)) == {MESMA_DESCRICAO.codigo, O_KIT.codigo}

    def test_a_busca_ignora_os_espacos_do_erp(self):
        achados = ordenar_candidatos(SEM_PAR, CATALOGO, busca="X00450IETL08")

        assert codigos(achados) == [ESPELHO.codigo]

    def test_o_limite_corta_a_lista_e_mantem_os_melhores(self):
        muitos = [item(f"C{i}", entradas=1, descricao="CASTANHA ESCURA 500G")
                  for i in range(100)]

        achados = ordenar_candidatos(SEM_PAR, [*muitos, ESPELHO], limite=5)

        assert len(achados) == 5
        assert achados[0].item.codigo == ESPELHO.codigo


class TestCadaUmDizPorQueSubiu:
    def test_o_candidato_traz_os_motivos(self):
        """Lista ordenada sem o porquê é a pessoa confiando no palpite da
        máquina — que é exatamente o que esta casa não faz."""
        melhor = ordenar_candidatos(SEM_PAR, CATALOGO)[0]

        assert "mesmo NCM" in melhor.porques
        assert any("descrição" in p for p in melhor.porques)
        assert "tem entrada e não tem saída" in melhor.porques

    def test_quem_entra_so_pela_busca_pode_nao_ter_motivo_de_parecenca(self):
        achados = ordenar_candidatos(SEM_PAR, CATALOGO, busca="parafuso")

        assert achados[0].porques == ("tem entrada e não tem saída",)
