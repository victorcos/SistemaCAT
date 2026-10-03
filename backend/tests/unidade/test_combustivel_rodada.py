"""A rodada do combustível: escolher os arquivos, gravar o parquet, não mentir.

O leitor já tem teste próprio (`test_combustivel_leitor.py`). Aqui se testa a
**etapa**: que arquivo repetido não entre duas vezes, que arquivo ilegível vire
aviso em vez de derrubar a rodada, que cancelamento não deixe parquet pela
metade, e que vazio continue vazio depois de gravado.

A de-duplicação é o que mais importa. Os 411 arquivos da empresa G estão em três
pastas que repetem as mesmas competências: um lote que aponte a pasta-mãe traz
cada mês três vezes, e somar os três triplicaria a tese.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico import combustivel as rodada
from cat.infraestrutura.analitico.combustivel import (
    ARQUIVO,
    Grupo,
    colunas,
    escolher,
    extrair,
    identificar,
    serializar,
)
from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.sped.registros_icms import CAMPOS

CNPJ = "44000003000109"
CNPJ_FILIAL = "44000003000284"


def _linha(registro: str, **valores: str) -> str:
    nomes = CAMPOS[registro]
    campos = [""] * len(nomes)
    campos[0] = registro
    indice = {nome: i for i, nome in enumerate(nomes)}
    for nome, valor in valores.items():
        assert nome in indice, f"{registro} não tem campo {nome}"
        campos[indice[nome]] = valor
    return "|" + "|".join(campos) + "|"


def _efd(tmp_path, nome: str, *, cnpj: str = CNPJ, competencia: str = "062022",
         cod_fin: str = "0", litros: str = "100,50",
         cst: str = "061") -> str:
    """Uma EFD ICMS/IPI com uma compra de combustível."""
    linhas = [
        _linha("0000", COD_VER="017", COD_FIN=cod_fin,
               DT_INI=f"01{competencia}", DT_FIN=f"30{competencia}",
               NOME="EMPRESA DO TESTE LTDA", CNPJ=cnpj, UF="SP",
               IND_PERFIL="A", IND_ATIV="1"),
        _linha("0150", COD_PART="F1", NOME="POSTO DO TESTE", CNPJ="11222333000181"),
        _linha("0200", COD_ITEM="I-DIESEL", DESCR_ITEM="OLEO DIESEL B S-10",
               UNID_INV="L", COD_NCM="27101921"),
        _linha("C100", IND_OPER="0", COD_PART="F1", COD_MOD="55", COD_SIT="00",
               NUM_DOC="1", CHV_NFE="3" * 44, DT_DOC=f"15{competencia}"),
        _linha("C170", NUM_ITEM="1", COD_ITEM="I-DIESEL", DESCR_COMPL="DIESEL",
               QTD=litros, UNID="L", VL_ITEM="600,00", CST_ICMS=cst,
               CFOP="1653"),
    ]
    caminho = tmp_path / nome
    caminho.write_bytes(("\n".join(linhas) + "\n").encode("cp1252"))
    return str(caminho)


class TestIdentificar:
    def test_le_quem_e_quando_do_0000(self, tmp_path):
        apuracao = identificar(_efd(tmp_path, "efd.txt"))

        assert apuracao is not None
        assert apuracao.cnpj == CNPJ
        assert apuracao.periodo == "2022-06"

    def test_o_COD_FIN_vira_tipo_escrit(self, tmp_path):
        """A seleção, que é da Gestão, chama de `tipo_escrit` o que a ICMS/IPI
        chama de `COD_FIN`. Mesma convenção: 0 original, 1 substituto."""
        original = identificar(_efd(tmp_path, "o.txt", cod_fin="0"))
        substituto = identificar(_efd(tmp_path, "s.txt", cod_fin="1"))

        assert original.tipo_escrit == "0"
        assert substituto.tipo_escrit == "1"

    def test_arquivo_que_nao_e_efd_icms_ipi_devolve_None(self, tmp_path):
        """Pode ser EFD-Contribuições, pode ser outra coisa. Nos dois casos não
        é este leitor que a lê, e não é erro — é aviso."""
        torto = tmp_path / "nao_e.txt"
        torto.write_bytes(b"isto nao e um sped\n")

        assert identificar(str(torto)) is None

    def test_arquivo_que_nao_existe_devolve_None(self, tmp_path):
        assert identificar(str(tmp_path / "nao_existe.txt")) is None


class TestEscolher:
    def test_o_mesmo_arquivo_em_duas_pastas_entra_uma_vez(self, tmp_path):
        """**O caso real.** Os 411 arquivos da empresa G estão em três pastas
        que repetem as competências; somar as três triplicaria a tese."""
        pasta_a = tmp_path / "a"
        pasta_b = tmp_path / "b"
        pasta_a.mkdir()
        pasta_b.mkdir()
        um = _efd(pasta_a, "junho.txt")
        outro = _efd(pasta_b, "junho.txt")

        escolhidas, avisos, ignorados = escolher([um, outro])

        assert len(escolhidas) == 1
        assert ignorados == 1
        assert len(avisos) == 1
        assert "mesmo estabelecimento" in avisos[0]

    def test_duas_filiais_na_mesma_competencia_entram_as_duas(self, tmp_path):
        matriz = _efd(tmp_path, "matriz.txt", cnpj=CNPJ)
        filial = _efd(tmp_path, "filial.txt", cnpj=CNPJ_FILIAL)

        escolhidas, avisos, ignorados = escolher([matriz, filial])

        assert len(escolhidas) == 2
        assert (ignorados, avisos) == (0, [])

    def test_o_substituto_vence_o_original(self, tmp_path):
        original = _efd(tmp_path, "original.txt", cod_fin="0")
        substituto = _efd(tmp_path, "substituto.txt", cod_fin="1")

        escolhidas, _, _ = escolher([original, substituto])

        assert [a.arquivo for a in escolhidas] == [substituto]

    def test_o_que_nao_e_efd_vira_aviso_e_nao_conta_como_duplicata(self, tmp_path):
        torto = tmp_path / "nao_e.txt"
        torto.write_bytes(b"xxx\n")
        bom = _efd(tmp_path, "bom.txt")

        escolhidas, avisos, ignorados = escolher([str(torto), bom])

        assert len(escolhidas) == 1
        assert ignorados == 0, "arquivo recusado não é duplicata"
        assert any("não é uma EFD" in a for a in avisos)


class TestExtrair:
    def test_grava_o_parquet_com_as_colunas_declaradas(self, tmp_path):
        destino = str(tmp_path / "saida")
        resumo = extrair([_efd(tmp_path, "efd.txt")], destino)

        tabela = pq.read_table(os.path.join(destino, ARQUIVO))
        assert tabela.column_names == colunas()
        assert tabela.num_rows == resumo.linhas == 1

    def test_o_resumo_conta_o_lote_e_o_que_entrou(self, tmp_path):
        pasta_a = tmp_path / "a"
        pasta_a.mkdir()
        resumo = extrair([_efd(tmp_path, "junho.txt"),
                          _efd(pasta_a, "junho.txt")],
                         str(tmp_path / "saida"))

        assert resumo.arquivos_no_lote == 2
        assert resumo.arquivos_lidos == 1
        assert resumo.ignorados_por_duplicidade == 1

    def test_conta_as_linhas_de_monofasico(self, tmp_path):
        """A dimensão da tese antes de existir classificador."""
        resumo = extrair([_efd(tmp_path, "diesel.txt", cst="061"),
                          _efd(tmp_path, "outro.txt", cnpj=CNPJ_FILIAL, cst="000")],
                         str(tmp_path / "saida"))

        assert resumo.linhas == 2
        assert resumo.linhas_de_monofasico == 1

    def test_o_grupo_separa_por_unidade(self, tmp_path):
        """O mesmo cliente escreve `L`, `LT` e `LTS`. Somar as três numa coluna
        só daria um número sem grandeza."""
        resumo = extrair([_efd(tmp_path, "efd.txt")], str(tmp_path / "saida"))

        assert list(resumo.grupos) == [
            Grupo(cnpj=CNPJ, competencia="2022-06", cst="061", unidade="L")]
        assert resumo.grupos[list(resumo.grupos)[0]].quantidade == Decimal("100.50")

    def test_o_intervalo_das_emissoes_entra_no_resumo(self, tmp_path):
        """Em vez de aplicar prescrição que ninguém escreveu, dizer o intervalo:
        quem roda vê se os cinco anos são assunto."""
        resumo = extrair([_efd(tmp_path, "a.txt", competencia="062022"),
                          _efd(tmp_path, "b.txt", competencia="062024")],
                         str(tmp_path / "saida"))

        assert resumo.primeira_emissao == "2022-06-15"
        assert resumo.ultima_emissao == "2024-06-15"

    def test_arquivo_ilegivel_vira_aviso_e_a_rodada_segue(self, tmp_path):
        """Uma EFD corrompida no meio de cinco anos não derruba a etapa."""
        bom = _efd(tmp_path, "bom.txt")
        pasta = tmp_path / "pasta_no_lugar_de_arquivo"
        pasta.mkdir()

        resumo = extrair([bom, str(pasta)], str(tmp_path / "saida"))

        assert resumo.linhas == 1
        assert any("não é uma EFD" in a for a in resumo.avisos)

    def test_sem_linha_nenhuma_o_parquet_existe_e_e_legivel(self, tmp_path):
        """Etapa que termina sem arquivo é etapa que a seguinte não distingue de
        etapa que não rodou."""
        destino = str(tmp_path / "saida")
        vazio = tmp_path / "vazio.txt"
        vazio.write_bytes(b"xxx\n")

        resumo = extrair([str(vazio)], destino)

        tabela = pq.read_table(os.path.join(destino, ARQUIVO))
        assert (tabela.num_rows, resumo.linhas) == (0, 0)
        assert tabela.column_names == colunas()


class TestCancelar:
    def test_cancelamento_sobe_e_apaga_o_parquet_pela_metade(self, tmp_path):
        """Parquet pela metade é pior que parquet nenhum: quem o abre não tem
        como saber que faltou arquivo."""
        destino = str(tmp_path / "saida")
        arquivos = [_efd(tmp_path, "a.txt", competencia="062022"),
                    _efd(tmp_path, "b.txt", competencia="072022")]
        chamadas = {"n": 0}

        def deve_parar() -> bool:
            chamadas["n"] += 1
            return chamadas["n"] > 1

        with pytest.raises(LeituraCancelada):
            extrair(arquivos, destino, deve_parar=deve_parar)

        assert not os.path.exists(os.path.join(destino, ARQUIVO))


class TestOParquetGravado:
    @pytest.fixture
    def tabela(self, tmp_path):
        destino = str(tmp_path / "saida")
        extrair([_efd(tmp_path, "efd.txt")], destino)
        return pq.read_table(os.path.join(destino, ARQUIVO)).to_pylist()[0]

    def test_o_documento_e_o_item_estao_na_mesma_linha(self, tabela):
        assert tabela["numero"] == "1"
        assert tabela["chave"] == "3" * 44
        assert tabela["codigo_do_item"] == "I-DIESEL"
        assert tabela["quantidade"] == "100.50"

    def test_o_cadastro_entrou(self, tabela):
        assert tabela["descricao_do_item"] == "OLEO DIESEL B S-10"
        assert tabela["ncm"] == "27101921"

    def test_a_tributacao_sai_desmontada(self, tabela):
        """Parquet não guarda objeto: as quatro colunas são o `CodigoDeTributacao`."""
        assert tabela["cst_icms"] == "061"
        assert tabela["origem"] == "0"
        assert tabela["cst"] == "61"
        assert tabela["csosn"] == ""
        assert tabela["ambiguo"] == ""

    def test_vazio_continua_vazio_depois_de_gravado(self, tabela):
        """**Vazio não é zero** tem de sobreviver ao parquet. Gravar `"0"` onde
        o fornecedor não destacou faria a etapa seguinte somar um imposto que
        ninguém cobrou."""
        assert tabela["aliquota_do_icms"] == ""
        assert tabela["valor_do_icms"] == ""

    def test_o_ambiguo_sai_marcado(self, tmp_path):
        destino = str(tmp_path / "saida")
        extrair([_efd(tmp_path, "sn.txt", cst="500")], destino)
        linha = pq.read_table(os.path.join(destino, ARQUIVO)).to_pylist()[0]

        assert (linha["csosn"], linha["ambiguo"]) == ("500", "1")


class TestOResumoParaOLog:
    def test_os_grupos_saem_contados_e_nao_listados(self, tmp_path):
        """Numa base de supermercado são milhares; log que não se lê não serve
        de log."""
        resumo = extrair([_efd(tmp_path, "efd.txt")], str(tmp_path / "saida"))

        assert serializar(resumo)["grupos"] == 1
        assert isinstance(serializar(resumo)["grupos"], int)

    def test_traz_o_que_a_tela_precisa(self, tmp_path):
        resumo = extrair([_efd(tmp_path, "efd.txt")], str(tmp_path / "saida"))
        d = serializar(resumo)

        for chave in ("arquivos_no_lote", "arquivos_lidos", "linhas",
                      "linhas_de_monofasico", "ignorados_por_duplicidade",
                      "primeira_emissao", "ultima_emissao", "segundos"):
            assert chave in d, chave


class TestOQueEstaEtapaNaoFaz:
    def test_nao_filtra_combustivel(self, tmp_path):
        """Ela grava **todas** as compras. Filtrar diesel exige o classificador,
        que não existe — e gravar tudo agora é o que permite construí-lo contra
        dado real em vez de contra suposição."""
        resumo = extrair([_efd(tmp_path, "parafuso.txt", cst="000")],
                         str(tmp_path / "saida"))

        assert resumo.linhas == 1
        assert resumo.linhas_de_monofasico == 0

    def test_nao_aplica_prescricao(self, tmp_path):
        """O ICMS prescreve em cinco anos da **emissão** (LC 87/96, art. 23),
        regra diferente da do PIS/COFINS. Escrever "mais ou menos cinco anos"
        aqui seria inventar a regra no lugar errado."""
        antiga = _efd(tmp_path, "antiga.txt", competencia="061999")

        resumo = extrair([antiga], str(tmp_path / "saida"))

        assert resumo.linhas == 1, "a linha antiga é gravada, não descartada"
        assert resumo.primeira_emissao == "1999-06-15", "e o intervalo a denuncia"
        assert not hasattr(resumo, "prescritas")
