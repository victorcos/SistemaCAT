"""O cadastro do bloco 0, que é do estabelecimento e não do arquivo.

A regra tem quatro casos e três deles são contraintuitivos, por isso o teste é
direto na classe: nos relatórios ela aparece misturada com vinte outras coisas,
e quem for mexer aqui precisa ver a regra sozinha.
"""

from cat.infraestrutura.sped.cadastro import CadastroPorEstabelecimento

MATRIZ = "11222333000181"
FILIAL = "11222333000262"

CHAVES = {b"0200": 1}


def cadastro_com(*blocos: tuple[str, list[list[str]]]) -> CadastroPorEstabelecimento:
    """Um cadastro montado como a passada monta: um 0140, depois os seus 0200."""
    c = CadastroPorEstabelecimento(CHAVES, matriz=MATRIZ)
    for cnpj, linhas in blocos:
        c.abrir(["0140", "001", "NOME", cnpj, "SP"])
        for linha in linhas:
            c.guardar(b"0200", linha)
    return c


def item(codigo: str, descricao: str, barra: str = "", ncm: str = "") -> list[str]:
    # REG, COD_ITEM, DESCR_ITEM, COD_BARRA, COD_ANT_ITEM — o NCM está longe
    # daqui no leiaute, mas a posição 4 serve para testar "campo não completável"
    return ["0200", codigo, descricao, barra, ncm]


class TestOEscopoManda:
    def test_o_mesmo_codigo_e_outro_produto_em_cada_estabelecimento(self):
        c = cadastro_com(
            (MATRIZ, [item("SKU1", "XAMPU")]),
            (FILIAL, [item("SKU1", "COXAO")]),
        )
        assert c.linha(b"0200", "SKU1", MATRIZ)[2] == "XAMPU"
        assert c.linha(b"0200", "SKU1", FILIAL)[2] == "COXAO"

    def test_repetido_dentro_do_mesmo_0140_vale_o_primeiro(self):
        c = cadastro_com((MATRIZ, [item("SKU1", "PRIMEIRO"), item("SKU1", "SEGUNDO")]))
        assert c.linha(b"0200", "SKU1", MATRIZ)[2] == "PRIMEIRO"


class TestABuscaForaDoEscopo:
    def test_codigo_de_um_estabelecimento_so_e_achado_de_qualquer_um(self):
        """Sem ambiguidade não há risco: vale procurar fora."""
        c = cadastro_com((MATRIZ, [item("SKU1", "XAMPU")]), (FILIAL, []))
        assert c.linha(b"0200", "SKU1", FILIAL)[2] == "XAMPU"

    def test_codigo_de_dois_nao_e_achado_por_um_terceiro(self):
        """Com dois candidatos não há desempate, e escolher um seria inventar."""
        c = cadastro_com(
            (MATRIZ, [item("SKU1", "XAMPU")]),
            (FILIAL, [item("SKU1", "COXAO")]),
        )
        assert c.linha(b"0200", "SKU1", "99999999000199") == []

    def test_codigo_que_nao_existe_volta_vazio(self):
        c = cadastro_com((MATRIZ, [item("SKU1", "XAMPU")]))
        assert c.linha(b"0200", "SKU9", MATRIZ) == []
        assert c.linha(b"0200", "", MATRIZ) == []


class TestOBrancoSeCompletaComODaMatriz:
    def test_o_vazio_da_filial_vem_da_matriz(self):
        c = cadastro_com(
            (MATRIZ, [item("SKU1", "XAMPU", "789001")]),
            (FILIAL, [item("SKU1", "COXAO")]),
        )
        completo = c.linha(b"0200", "SKU1", FILIAL)
        assert (completo[2], completo[3]) == ("COXAO", "789001")

    def test_o_vazio_da_matriz_nao_vem_da_filial(self):
        """A matriz não se completa com ninguém: é ela a fonte."""
        c = cadastro_com(
            (MATRIZ, [item("SKU1", "XAMPU")]),
            (FILIAL, [item("SKU1", "COXAO", "789002")]),
        )
        assert c.linha(b"0200", "SKU1", MATRIZ)[3] == ""

    def test_o_que_a_matriz_nao_tem_nao_se_completa(self):
        """Duas filiais, sem a matriz: o vazio fica vazio.

        É o caso que separa "a matriz" de "quem cadastrou primeiro" — e o que
        o gabarito mostra no item 911047, cadastrado em duas filiais e em
        branco nas 85 linhas da segunda.
        """
        outra = "11222333000343"
        c = cadastro_com(
            (FILIAL, [item("SKU1", "XAMPU", "789001", "33051000")]),
            (outra, [item("SKU1", "COXAO")]),
        )
        completo = c.linha(b"0200", "SKU1", outra)
        assert (completo[3], completo[4]) == ("", "")

    def test_sem_repeticao_o_cadastro_sai_intocado(self):
        c = cadastro_com((MATRIZ, [item("SKU1", "XAMPU")]))
        assert c.linha(b"0200", "SKU1", MATRIZ) == item("SKU1", "XAMPU")

    def test_sem_matriz_conhecida_nada_se_completa(self):
        c = CadastroPorEstabelecimento(CHAVES)
        c.abrir(["0140", "001", "NOME", MATRIZ, "SP"])
        c.guardar(b"0200", item("SKU1", "XAMPU", "789001"))
        c.abrir(["0140", "002", "NOME", FILIAL, "PR"])
        c.guardar(b"0200", item("SKU1", "COXAO"))
        assert c.linha(b"0200", "SKU1", FILIAL)[3] == ""


class TestOQueNaoECadastro:
    def test_registro_de_fora_da_tabela_nao_e_guardado(self):
        c = CadastroPorEstabelecimento(CHAVES, matriz=MATRIZ)
        assert c.guardar(b"C100", ["C100", "1"]) is False
        assert c.guardar(b"0200", ["0200", "SKU1", "XAMPU"]) is True

    def test_o_estabelecimento_sai_pelo_cnpj(self):
        c = cadastro_com((MATRIZ, []), (FILIAL, []))
        assert c.estabelecimento(MATRIZ)[3] == MATRIZ
        assert c.estabelecimento("00000000000000") == []
