"""O leiaute da EFD ICMS/IPI: a tabela que troca uma coluna sem avisar.

Esta tabela não calcula nada — e é exatamente por isso que ela é perigosa. Um
nome a mais no meio de um registro empurra todos os seguintes uma casa, e o
valor que aparece na coluna errada **continua parecendo certo**: a alíquota cai
onde devia estar o valor do ICMS, e os dois são número com duas casas.

Por isso o teste central aqui é a **contagem de campos**, afirmada contra o que
se mediu em 40 arquivos reais. Não prova que os nomes estão na ordem certa;
prova que ninguém mexeu no tamanho sem medir de novo.

**Nenhuma linha de cliente entra como fixture.** As linhas de exemplo são
sintéticas, com a mesma forma e a mesma contagem das reais — dado de cliente não
se versiona, nem como amostra de leiaute.
"""

from __future__ import annotations

import pytest

from cat.dominio.sped.cabecalho import TipoSped
from cat.infraestrutura.sped import registros as contribuicoes
from cat.infraestrutura.sped import registros_icms as icms
from cat.infraestrutura.sped.registros_icms import (
    RegistroNaoMedido,
    campos_de,
    nomes_dos_campos,
    posicao_do_campo,
    tabela_de,
)

# Quantos campos cada registro tem, contado em 40 EFD ICMS/IPI reais
# (02/2023 a 03/2026). Mudar um número aqui exige medir de novo.
MEDIDO: dict[str, int] = {
    "0000": 15, "0005": 10, "0150": 13, "0190": 3, "0200": 13, "0205": 5,
    "0220": 4, "0400": 3, "0460": 3, "C100": 29, "C110": 3, "C170": 38,
    "C190": 12, "C197": 8, "E110": 15, "E111": 4, "E116": 10,
}



class TestAContagemMedida:
    @pytest.mark.parametrize("registro, quantos", sorted(MEDIDO.items()))
    def test_cada_registro_tem_o_tamanho_que_se_mediu(self, registro, quantos):
        assert len(nomes_dos_campos(registro)) == quantos

    def test_a_tabela_nao_tem_registro_fora_da_medicao(self):
        """Registro sem contagem afirmada é registro que ninguém conferiu."""
        assert set(icms.CAMPOS) == set(MEDIDO)

    def test_todo_registro_comeca_por_REG(self):
        for registro, nomes in icms.CAMPOS.items():
            assert nomes[0] == "REG", registro

    def test_nenhum_registro_repete_nome_de_campo(self):
        """Nome repetido faz `posicao_do_campo` devolver sempre o primeiro, e o
        segundo fica inalcançável — é o erro de digitação que não quebra nada."""
        for registro, nomes in icms.CAMPOS.items():
            assert len(nomes) == len(set(nomes)), registro


class TestPorQueSaoDoisModulos:
    """A razão de existir deste arquivo: dois registros colidem.

    Se um dia alguém juntar as duas tabelas, estes testes quebram — e é o que
    se quer, porque juntar significa ler um dos dois arquivos com os nomes do
    outro, calado.
    """

    def test_o_0000_dos_dois_arquivos_e_diferente(self):
        aqui = nomes_dos_campos("0000")
        lah = contribuicoes.nomes_dos_campos("0000")

        assert aqui != lah
        assert len(aqui) == 15 and len(lah) == 14

    def test_so_a_icms_ipi_tem_IND_PERFIL(self):
        assert "IND_PERFIL" in nomes_dos_campos("0000")
        assert "IND_PERFIL" not in contribuicoes.nomes_dos_campos("0000")

    def test_so_a_icms_ipi_tem_CEST_no_0200(self):
        """Medido nos dois lados: 13 campos aqui, 12 lá."""
        assert nomes_dos_campos("0200")[-1] == "CEST"
        assert "CEST" not in contribuicoes.nomes_dos_campos("0200")

    def test_o_0150_e_identico_nos_dois(self):
        """Para que ninguém conserte um e esqueça o outro."""
        assert nomes_dos_campos("0150") == contribuicoes.nomes_dos_campos("0150")


class TestOQueATeseDoCombustivelPrecisa:
    @pytest.mark.parametrize("registro, campo", [
        ("0000", "UF"),          # escolhe o FCV e a alíquota interna
        ("0000", "CNPJ"),        # a chave de de-duplicação por estabelecimento
        ("0000", "DT_INI"),      # a competência
        ("0200", "COD_NCM"),     # o classificador: NCM manda
        ("0200", "DESCR_ITEM"),  # e a descrição confirma
        ("0205", "DESCR_ANT_ITEM"),
        ("C100", "DT_DOC"),      # o prazo de 5 anos conta da emissão
        ("C100", "CHV_NFE"),     # a amarração com o XML da fase 2
        ("C170", "QTD"),         # o litro
        ("C170", "UNID"),
        ("C170", "CST_ICMS"),    # 60 = ST, 61 = monofásico, 90 = destacado
        ("C170", "CFOP"),
        ("E111", "COD_AJ_APUR"),      # o crédito já tomado
        ("E111", "VL_AJ_APUR"),
        ("E110", "VL_TOT_CREDITOS"),
    ])
    def test_o_campo_existe_e_tem_posicao(self, registro, campo):
        assert posicao_do_campo(registro, campo) >= 0

    def test_a_quantidade_e_a_unidade_ficam_lado_a_lado_no_C170(self):
        """`QTD` sem `UNID` é número sem grandeza — a conta do combustível
        depende de ler os dois juntos."""
        assert (posicao_do_campo("C170", "UNID")
                == posicao_do_campo("C170", "QTD") + 1)

    def test_o_CST_do_icms_vem_antes_do_CFOP(self):
        """A ordem do leiaute, e a que o leitor vai assumir."""
        assert (posicao_do_campo("C170", "CST_ICMS")
                < posicao_do_campo("C170", "CFOP"))


class TestLerUmaLinha:
    """A prova de que os nomes chegam nos valores certos.

    A linha é **sintética** — mesma forma e contagem de uma compra de diesel
    real, sem dado de cliente nenhum.
    """

    LINHA_C170 = (
        "|C170|1|000007|DIESEL B S-10|63,96|L|415,10|0|0|090|1653|1653000"
        "|415,10|12|49,81|0|0|0||||0|0|0|70|0|0|||0|70|0|0|||0|1562|0|"
    )

    def _campos(self, linha: str) -> dict[str, str]:
        partes = linha.rstrip("\r\n").split("|")[1:-1]
        nomes = campos_de(partes[0], len(partes))
        return dict(zip(nomes, partes, strict=True))

    def test_a_contagem_da_linha_casa_com_a_tabela(self):
        """`strict=True` no zip é de propósito: linha de tamanho diferente da
        tabela levanta, em vez de silenciosamente truncar o fim."""
        campos = self._campos(self.LINHA_C170)

        assert len(campos) == MEDIDO["C170"]

    @pytest.mark.parametrize("campo, esperado", [
        ("COD_ITEM", "000007"),
        ("DESCR_COMPL", "DIESEL B S-10"),
        ("QTD", "63,96"),
        ("UNID", "L"),
        ("VL_ITEM", "415,10"),
        ("CST_ICMS", "090"),
        ("CFOP", "1653"),
        ("ALIQ_ICMS", "12"),
        ("VL_ICMS", "49,81"),
    ])
    def test_cada_nome_pega_o_valor_certo(self, campo, esperado):
        assert self._campos(self.LINHA_C170)[campo] == esperado

    def test_a_mesma_linha_lida_com_a_tabela_errada_erra_calado(self):
        """**O erro que este módulo existe para impedir.**

        Lida com os nomes da EFD-Contribuições, a mesma linha de C170 não
        levanta exceção nenhuma — o C170 tem o mesmo tamanho nos dois leiautes.
        Ela só devolve outra coisa. Aqui o perigo é o `0200`, que tem tamanhos
        diferentes: com a tabela errada o `zip(strict=True)` levanta.
        """
        linha_0200 = "|0200|000000000665|ABRACADEIRA|||PC|00|73269090||73|||1006200|"
        partes = linha_0200.split("|")[1:-1]

        assert len(campos_de("0200", len(partes))) == len(partes)
        with pytest.raises(ValueError):
            dict(zip(contribuicoes.campos_de("0200", len(partes)), partes,
                     strict=True))


class TestO0220QueTemDuasLarguras:
    """O caso que `tools/medir_leiaute_icms.py` encontrou, e que a leitura do
    Guia não encontraria: o mesmo registro com dois tamanhos no mesmo acervo.

    Não é defeito do cliente — é versão de PVA. Por isso a chave da variante é
    `(registro, tamanho)` e não a data: retificadora de 2021 transmitida em 2024
    sai no leiaute novo.
    """

    def test_a_tabela_tem_a_largura_nova(self):
        assert nomes_dos_campos("0220")[-1] == "COD_BARRA"

    def test_a_linha_de_tres_campos_cai_na_variante(self):
        assert campos_de("0220", 3) == ("REG", "UNID_CONV", "FAT_CONV")

    def test_a_linha_de_quatro_campos_cai_na_tabela(self):
        assert campos_de("0220", 4) == nomes_dos_campos("0220")

    def test_o_fator_esta_no_mesmo_lugar_nas_duas(self):
        """É o que importa: `FAT_CONV` é o número que multiplica, e ler a
        largura errada o poria na coluna do código de barra."""
        for largura in (3, 4):
            nomes = campos_de("0220", largura)
            assert nomes.index("FAT_CONV") == 2

    @pytest.mark.parametrize("linha, fator", [
        ("|0220|CX|12|", "12"),
        ("|0220|CX|12|7891234567890|", "12"),
        ("|0220|FD|6,5||", "6,5"),
    ])
    def test_le_o_fator_das_duas_larguras(self, linha, fator):
        partes = linha.split("|")[1:-1]
        campos = dict(zip(campos_de("0220", len(partes)), partes, strict=True))

        assert campos["FAT_CONV"] == fator


class TestOsDoisQueNaoSeMediu:
    @pytest.mark.parametrize("registro", ["0206", "C171"])
    def test_estao_nomeados_com_o_motivo(self, registro):
        assert registro in icms.NAO_MEDIDOS
        assert len(icms.NAO_MEDIDOS[registro]) > 40

    @pytest.mark.parametrize("registro", ["0206", "C171"])
    def test_pedir_campo_deles_diz_que_falta_medir(self, registro):
        with pytest.raises(RegistroNaoMedido) as erro:
            posicao_do_campo(registro, "QUALQUER")

        assert "não foi medido" in str(erro.value)
        assert "registros_icms.CAMPOS" in str(erro.value)

    def test_nao_estao_na_tabela(self):
        """Seria medido e não medido ao mesmo tempo."""
        assert not set(icms.NAO_MEDIDOS) & set(icms.CAMPOS)

    def test_o_0220_saiu_da_lista_porque_foi_medido(self):
        """Ele esteve aqui, e sair daqui é o que marca que a medição aconteceu."""
        assert "0220" not in icms.NAO_MEDIDOS
        assert "0220" in icms.CAMPOS


class TestOQueElaRecusa:
    def test_campo_que_nao_existe_diz_quais_existem(self):
        with pytest.raises(KeyError) as erro:
            posicao_do_campo("C170", "VL_PIS_ST")

        assert "CST_ICMS" in str(erro.value), "lista os que existem"

    def test_registro_fora_da_tabela_devolve_vazio(self):
        """Vazio, e não erro: a quebra de SPED conta registro por índice."""
        assert nomes_dos_campos("K200") == ()
        assert campos_de("K200", 5) == ()


class TestQualTabelaParaQualArquivo:
    def test_cada_tipo_leva_a_sua(self):
        assert tabela_de(TipoSped.EFD_ICMS_IPI) is icms.CAMPOS
        assert tabela_de(TipoSped.EFD_CONTRIBUICOES) is contribuicoes.CAMPOS

    @pytest.mark.parametrize("tipo", [TipoSped.ECD, TipoSped.ECF])
    def test_ecd_e_ecf_recusam_em_vez_de_cair_na_de_outro(self, tipo):
        with pytest.raises(KeyError) as erro:
            tabela_de(tipo)

        assert tipo.rotulo in str(erro.value)
