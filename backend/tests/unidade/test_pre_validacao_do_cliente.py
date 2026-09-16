"""Pré-validar o que o cliente transmitiu: TXT solto, zip e zip dentro de zip.

Janeiro vem solto e fecha. Fevereiro vem num zip, e uma cópia de janeiro vem no
mesmo zip. Março vem num zip dentro do zip e abre com um saldo que não é o de
fevereiro. No meio, um TXT que não é da CAT 42 e um arquivo de outra empresa.
"""

import os
import zipfile
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.dominio.cat42.arquivo_digital import Abertura, ArquivoDigital, Item, Participante, Saldo
from cat.dominio.comum.cnpj import digitos_verificadores
from cat.infraestrutura.analitico.arquivo_digital import ocorrencias
from cat.infraestrutura.analitico.pre_validacao_do_cliente import (
    ARQUIVO_ARQUIVOS_DO_CLIENTE,
    arquivos_do_cliente,
    pre_validar,
    serializar,
)
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada
from tests.unidade.test_arquivo_digital import CNPJ, IE_SP, arquivo_que_fecha

D = Decimal
OUTRA = "112223330001" + digitos_verificadores("112223330001")


def conteudo(a: ArquivoDigital) -> bytes:
    return "".join(l + "\r\n" for l in a.linhas()).encode("latin-1")


def so_saldo(mes: int, qi, vi, qf, vf, cnpj: str = CNPJ) -> ArquivoDigital:
    return ArquivoDigital(
        abertura=Abertura(2024, mes, "LOJA DE TESTE", cnpj, IE_SP, "3552205"),
        participantes=[Participante(cnpj, "LOJA DE TESTE", cnpj=cnpj, ie=IE_SP, cod_mun="3552205")],
        itens=[Item("1002140", "IOGURTE 170G", "UN1", "04032000", "07891024183007", D(18), "1702200")],
        saldos=[Saldo("1002140", D(qi), D(vi), D(qf), D(vf))])


@pytest.fixture
def fontes(tmp_path):
    lote = tmp_path / "lote"
    lote.mkdir()
    janeiro = lote / f"CAT5_SP_{CNPJ}_1_2024.txt"
    janeiro.write_bytes(conteudo(arquivo_que_fecha()))

    interno = tmp_path / "interno.zip"
    with zipfile.ZipFile(interno, "w", zipfile.ZIP_DEFLATED) as z:
        # março abre com 10, e fevereiro fechou com 16
        z.writestr(f"marco/CAT5_SP_{CNPJ}_3_2024.txt", conteudo(so_saldo(3, 10, 20, 10, 20)))
    pacote = lote / "BOA_remessa.zip"
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"fev/CAT5_SP_{CNPJ}_2_2024.txt", conteudo(so_saldo(2, 16, 40, 16, 40)))
        z.writestr(f"copia/CAT5_SP_{CNPJ}_1_2024.txt", conteudo(arquivo_que_fecha()))
        z.writestr("LEIA-ME.txt", b"arquivos da remessa de agosto\r\n")
        z.writestr(f"CAT5_SP_{OUTRA}_2_2024.txt", conteudo(so_saldo(2, 1, 1, 1, 1, cnpj=OUTRA)))
        z.write(interno, "aninhado/interno.zip")
    return [str(janeiro), str(pacote)]


@pytest.fixture
def validado(fontes, tmp_path):
    destino = tmp_path / "execucao"
    destino.mkdir()
    return destino, pre_validar(fontes, str(destino), CNPJ[:8])


class TestOQueSeLe:
    def test_solto_zip_e_zip_dentro_de_zip(self, validado):
        destino, r = validado
        s = serializar(r)
        assert (s["fontes"], s["arquivos"]) == (2, 3)
        assert (s["competencia_inicial"], s["competencia_final"]) == ("2024-01", "2024-03")
        assert s["estabelecimentos"] == 1
        origens = {l["competencia"]: l["origem"] for l in pq.read_table(destino / ARQUIVO_ARQUIVOS_DO_CLIENTE).to_pylist()
                   if not l["repetido"]}
        assert origens["2024-03"].endswith(f"aninhado/interno.zip :: marco/CAT5_SP_{CNPJ}_3_2024.txt")
        # o zip aninhado copiado para ler não fica para trás
        assert not [n for n in os.listdir(destino) if n.startswith(".aninhado")]

    def test_o_que_fica_de_fora_e_contado(self, validado):
        _, r = validado
        assert (r.repetidos, r.de_outra_empresa, r.nao_sao_da_cat42) == (1, 1, 1)

    def test_o_arquivo_bom_passa_e_a_ficha_fecha(self, validado):
        destino, r = validado
        janeiro = arquivos_do_cliente(str(destino), busca="2024-01")["linhas"]
        lido = next(l for l in janeiro if not l["repetido"])
        assert (lido["erros"], lido["avisos"]) == (0, 0)
        assert (lido["itens_recompostos"], lido["itens_que_fecham"]) == (1, 1)
        assert len(lido["sha256"]) == 64 and lido["bytes"] > 0


class TestContinuidade:
    def test_saldo_que_nao_emenda_com_o_mes_anterior_e_aviso(self, validado):
        destino, r = validado
        marco = arquivos_do_cliente(str(destino), so="com_aviso")["linhas"]
        assert [l["competencia"] for l in marco] == ["2024-03"]
        oc = ocorrencias(str(destino), marco[0]["nome"])["linhas"]
        assert oc[0]["regra"] == "saldo_inicial_diferente_do_anterior"
        assert "fechou 2024-02 com 16 un" in oc[0]["mensagem"]
        assert {x["codigo"] for x in serializar(r)["por_regra"]} == {"saldo_inicial_diferente_do_anterior"}

    def test_recortes(self, validado):
        destino, _ = validado
        assert arquivos_do_cliente(str(destino), so="sem_ocorrencia")["total"] == 2
        assert arquivos_do_cliente(str(destino), so="repetidos")["total"] == 1
        assert arquivos_do_cliente(str(destino), so="com_erro")["total"] == 0
        with pytest.raises(ValueError):
            arquivos_do_cliente(str(destino), so="qualquer")


class TestCancelar:
    def test_nao_deixa_resultado(self, fontes, tmp_path):
        destino = tmp_path / "cancelada"
        destino.mkdir()
        with pytest.raises(ApuracaoCancelada):
            pre_validar(fontes, str(destino), CNPJ[:8], deve_parar=lambda: True)
        assert not os.path.exists(destino / ARQUIVO_ARQUIVOS_DO_CLIENTE)


class TestNomes:
    def test_mesmo_nome_em_pastas_diferentes_nao_mistura_as_ocorrencias(self, tmp_path):
        """Outra ferramenta pode chamar todo mês de CAT42.txt."""
        lote = tmp_path / "lote"
        for mes, saldo in ((1, (10, 20, 10, 20)), (2, (16, 40, 16, 40))):
            pasta = lote / f"mes{mes}"
            pasta.mkdir(parents=True)
            (pasta / "CAT42.txt").write_bytes(conteudo(so_saldo(mes, *saldo)))
        destino = tmp_path / "execucao"
        destino.mkdir()
        pre_validar([str(lote / "mes1" / "CAT42.txt"), str(lote / "mes2" / "CAT42.txt")], str(destino), CNPJ[:8])
        nomes = {l["competencia"]: l["nome"] for l in arquivos_do_cliente(str(destino))["linhas"]}
        assert nomes == {"2024-01": "CAT42.txt", "2024-02": f"CAT42 ({CNPJ} 2024-02).txt"}
        # fevereiro abre com 16 e janeiro fechou com 10: o aviso é só de fevereiro
        assert ocorrencias(str(destino), "CAT42.txt")["total"] == 0
        assert ocorrencias(str(destino), nomes["2024-02"])["linhas"][0]["regra"] == "saldo_inicial_diferente_do_anterior"
