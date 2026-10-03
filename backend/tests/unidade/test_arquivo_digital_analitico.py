"""A geração do arquivo digital sobre parquets pequenos, com a conta à mão.

Uma loja de SP e uma do PR. Em janeiro, o iogurte abre com 10 un e R$ 20,
entra 10 un com R$ 30 e sai 4 no cupom: fecha em 16 un e R$ 40 — apta, com
nota e cupom com chave, vai para o envio. Em fevereiro a venda veio do
relatório de PDV, sem chave: sai como prévia. A loja do PR não gera nada.
"""

import os
import zipfile
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.dominio.icms.cat42.enquadramento import VendaAConsumidor
from cat.dominio.icms.cat42.pre_validacao import validar
from cat.dominio.comum.cnpj import digitos_verificadores
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO, ARQUIVO_SALDOS, ESQUEMA_APURACAO, ESQUEMA_SALDOS
from cat.infraestrutura.analitico.arquivo_digital import (
    ARQUIVO_ARQUIVOS,
    ARQUIVO_OCORRENCIAS,
    PASTA_ENVIO,
    PASTA_PREVIAS,
    Fontes,
    arquivos,
    empacotar,
    gerar,
    ocorrencias,
    serializar,
)
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS
from cat.infraestrutura.analitico.movimentos import ARQUIVO_ITENS_DA_EFD
from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3, ESQUEMA_FICHA3
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada

D = Decimal
SP = "509483710013" + digitos_verificadores("509483710013")
PR = "509483710020" + digitos_verificadores("509483710020")
FORNECEDOR = "001586350001" + digitos_verificadores("001586350001")
IE_SP = "798092322114"


def chave(cnpj: str, modelo: str, n: int) -> str:
    base = f"352401{cnpj}{modelo}001{n:09d}1{n:08d}"[:43]
    soma = sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(base)))
    resto = soma % 11
    return base + str(0 if resto < 2 else 11 - resto)


def gravar(caminho, esquema: pa.Schema, linhas: list[dict]) -> None:
    pq.write_table(pa.Table.from_pydict({c: [l.get(c) for l in linhas] for c in esquema.names}, schema=esquema),
                   str(caminho))


def linha_da_ficha(**k) -> dict:
    base = {"numero": 1, "devolucao": False, "origem": "efd", "enquadramento_indefinido": False,
            "ficha_retirada": False, "unidade_origem": "", "fator_conversao": D(1), "unidade_sem_fator": False,
            "valor_unitario_usado": D(0), "saldo_unitario": D(0), "saldo_valor": D(0),
            "ressarcimento": D(0), "complemento": D(0), "chave": "", "participante": "",
            "numero_documento": "", "modelo": "", "documento": ""}
    return {**base, **k}


@pytest.fixture
def fontes(tmp_path):
    apu, raz, mov, efd = (tmp_path / p for p in ("apuracao", "razao", "movimentacao", "efd"))
    for p in (apu, raz, mov, efd):
        p.mkdir()
    gravar(apu / ARQUIVO_APURACAO, ESQUEMA_APURACAO, [
        {"cnpj": SP, "uf": "SP", "competencia": "2024-01", "ressarcimento": D("1.50"), "complemento": D(0),
         "apta": True, "motivos": ""},
        {"cnpj": SP, "uf": "SP", "competencia": "2024-02", "ressarcimento": D(0), "complemento": D(0),
         "apta": False, "motivos": "sem_inventario"},
        {"cnpj": PR, "uf": "PR", "competencia": "2024-01", "ressarcimento": D(9), "complemento": D(0),
         "apta": False, "motivos": "fora_de_sp"},
    ])
    gravar(apu / ARQUIVO_SALDOS, ESQUEMA_SALDOS, [
        {"cnpj": SP, "competencia": "2024-01", "codigo": "1002140", "qtd_ini": D(10), "icms_tot_ini": D(20),
         "qtd_fim": D(16), "icms_tot_fim": D(40), "retirada": False},
        {"cnpj": SP, "competencia": "2024-02", "codigo": "1002140", "qtd_ini": D(16), "icms_tot_ini": D(40),
         "qtd_fim": D(15), "icms_tot_fim": D("37.5"), "retirada": False},
        {"cnpj": PR, "competencia": "2024-01", "codigo": "1002140", "qtd_ini": D(1), "icms_tot_ini": D(1),
         "qtd_fim": D(1), "icms_tot_fim": D(1), "retirada": False},
    ])
    gravar(raz / ARQUIVO_FICHA3, ESQUEMA_FICHA3, [
        linha_da_ficha(cnpj=SP, codigo="1002140", numero=1, data=date(2024, 1, 3), especie="entrada", cfop="1403",
                       quantidade=D(10), icms_suportado=D(30), chave=chave(FORNECEDOR, "55", 1), numero_item=1,
                       modelo="55", participante="F1", numero_documento="1"),
        linha_da_ficha(cnpj=SP, codigo="1002140", numero=2, data=date(2024, 1, 5), especie="saida", cfop="5405",
                       quantidade=D(-4), icms_suportado=D(-10), enquadramento=0, chave=chave(SP, "59", 2),
                       numero_item=33, modelo="59"),
        # fevereiro: venda de PDV do relatório, sem chave nem nº do item
        linha_da_ficha(cnpj=SP, codigo="1002140", numero=3, data=date(2024, 2, 9), especie="saida", cfop="5405",
                       quantidade=D(-1), icms_suportado=D("-2.5"), enquadramento=0, origem="relatorio"),
        linha_da_ficha(cnpj=PR, codigo="1002140", numero=1, data=date(2024, 1, 3), especie="entrada", cfop="1403",
                       quantidade=D(1), icms_suportado=D(1), chave=chave(FORNECEDOR, "55", 9), numero_item=1,
                       modelo="55", participante="F1"),
    ])
    gravar(mov / ARQUIVO_ITENS, pa.schema([
        ("cnpj", pa.string()), ("competencia", pa.date32()), ("codigo", pa.string()), ("descricao", pa.string()),
        ("codigo_barras", pa.string()), ("unidade", pa.string()), ("ncm", pa.string()),
        ("aliq_icms", pa.decimal128(9, 4)), ("cest", pa.string())]), [
        {"cnpj": SP, "competencia": date(2024, 1, 1), "codigo": "1002140", "descricao": "IOGURTE 170G",
         "codigo_barras": "07891024183007", "unidade": "UN1", "ncm": "04032000", "aliq_icms": D(18),
         "cest": "1702200"},
    ])
    janeiro = efd / "efd_sp_2024_01.txt"
    janeiro.write_bytes((
        f"|0000|017|0|01012024|31012024|LOJA DE TESTE|{SP}||SP|{IE_SP}|3552205||A|1|\r\n"
        "|0001|0|\r\n"
        # |0150|COD_PART|NOME|COD_PAIS|CNPJ|CPF|IE|COD_MUN|SUFRAMA|END|NUM|COMPL|BAIRRO|
        f"|0150|F1|FORNECEDOR DE IOGURTE|1058|{FORNECEDOR}|||3506300||RUA|1||CENTRO|\r\n"
        "|0150|F2|OUTRO QUE NAO MOVIMENTOU|1058||52998224725||3506300||RUA|1||CENTRO|\r\n"
        "|0990|5|\r\n|C001|0|\r\n").encode("latin-1"))
    return Fontes(apuracao=str(apu), razao=str(raz), movimentacao=str(mov),
                  efds=[(str(janeiro), SP, date(2024, 1, 1))])


@pytest.fixture
def gerado(fontes, tmp_path):
    destino = tmp_path / "arquivo"
    destino.mkdir()
    return destino, gerar(fontes, str(destino))


def registros(caminho) -> list[str]:
    return open(caminho, "rb").read().decode("latin-1").split("\r\n")[:-1]


class TestEnvio:
    def test_o_mes_apto_vai_para_o_envio_e_passa(self, gerado):
        destino, r = gerado
        caminho = destino / PASTA_ENVIO / f"CAT5_SP_{SP}_1_2024.txt"
        assert caminho.is_file()
        with open(caminho, "rb") as f:
            v = validar(f)
        assert v.passou and v.avisos == 0, [(o.regra.name, o.mensagem) for o in v.exemplos]
        assert (v.itens_recompostos, v.itens_que_fecham) == (1, 1)

    def test_os_registros_na_ordem_e_no_formato(self, gerado):
        destino, _ = gerado
        linhas = registros(destino / PASTA_ENVIO / f"CAT5_SP_{SP}_1_2024.txt")
        assert linhas[0] == f"0000|012024|LOJA DE TESTE|{SP}|{IE_SP}|3552205|01|00"
        # só o participante que movimentou, e o próprio estabelecimento pelo 0000
        assert [l.split("|")[1] for l in linhas if l.startswith("0150")] == ["F1", SP]
        assert "0200|1002140|IOGURTE 170G|07891024183007|UN1|04032000|18,00|1702200" in linhas
        assert "1050|1002140|10,000|20,00|16,000|40,00" in linhas
        assert [l[:4] for l in linhas] == ["0000", "0150", "0150", "0200", "1050", "1100", "1100"]
        assert linhas[5].endswith("|0|1002140|1403|10,000|30,00||")
        assert linhas[6].endswith("|033|1|1002140|5405|4,000|||0")

    def test_o_resumo(self, gerado):
        _, r = gerado
        s = serializar(r)
        assert (s["competencias"], s["competencias_fora_de_sp"], s["arquivos"]) == (2, 1, 2)
        assert (s["para_envio"], s["previas"]) == (1, 1)
        assert s["ressarcimento_para_envio"] == "1.50"
        assert s["linhas_sem_documento"] == 1
        assert {t["codigo"] for t in s["por_trava"]} == {"nao_apta", "sem_documento", "sem_abertura",
                                                          "pre_validacao"}


class TestPrevia:
    def test_o_mes_sem_documento_sai_como_previa(self, gerado):
        destino, _ = gerado
        assert (destino / PASTA_PREVIAS / f"CAT5_SP_{SP}_2_2024_PREVIA.txt").is_file()
        assert not os.listdir(destino / PASTA_ENVIO) == []
        assert not any("_2_2024" in n for n in os.listdir(destino / PASTA_ENVIO))

    def test_a_previa_diz_por_que(self, gerado):
        destino, _ = gerado
        lista = arquivos(str(destino), so="previa")
        assert lista["total"] == 1
        previa = lista["linhas"][0]
        assert {t["codigo"] for t in previa["travas"]} == {"nao_apta", "sem_documento", "sem_abertura",
                                                            "pre_validacao"}
        assert previa["motivos"][0]["codigo"] == "sem_inventario"
        assert previa["linhas_sem_documento"] == 1
        # sem a venda, a ficha recomposta não chega ao 1050: é o erro que a SEFAZ acharia
        oc = ocorrencias(str(destino), previa["nome"])
        assert "saldo_em_quantidade" in {o["regra"] for o in oc["linhas"]}

    def test_fora_de_sp_nao_gera(self, gerado):
        destino, _ = gerado
        todos = os.listdir(destino / PASTA_ENVIO) + os.listdir(destino / PASTA_PREVIAS)
        assert not any(PR in n for n in todos)


class TestEntrega:
    def test_zip_do_envio_so_com_o_de_envio(self, gerado, tmp_path):
        destino, _ = gerado
        z = tmp_path / "envio.zip"
        assert empacotar(str(destino / ARQUIVO_ARQUIVOS), str(z), "envio") == 1
        assert zipfile.ZipFile(z).namelist() == [f"CAT5_SP_{SP}_1_2024.txt"]

    def test_o_indice_guarda_o_hash(self, gerado):
        destino, _ = gerado
        envio = arquivos(str(destino), so="envio")["linhas"][0]
        assert len(envio["sha256"]) == 64 and envio["bytes"] > 0
        assert os.path.isfile(destino / ARQUIVO_OCORRENCIAS)


class TestDecisoes:
    def test_devolucao_de_venda_no_trabalho_com_cupom_no_zero(self, fontes, tmp_path):
        """No 0, a devolução de dentro do estado é 0; no 1, sem a venda original, trava."""
        caminho = os.path.join(fontes.razao, ARQUIVO_FICHA3)
        t = pq.read_table(caminho).to_pylist()
        t.append(linha_da_ficha(cnpj=SP, codigo="1002140", numero=9, data=date(2024, 1, 20), especie="saida",
                                devolucao=True, cfop="1411", quantidade=D(1), icms_suportado=D("2.5"),
                                chave=chave(SP, "55", 7), numero_item=1, modelo="55"))
        pq.write_table(pa.Table.from_pylist(t, schema=ESQUEMA_FICHA3), caminho)

        no_um = tmp_path / "no_um"
        no_um.mkdir()
        r = gerar(fontes, str(no_um), VendaAConsumidor.ENQUADRAMENTO_1)
        assert serializar(r)["por_trava"][0]["codigo"] in {"devolucao_sem_venda", "nao_apta"}
        assert any(t["codigo"] == "devolucao_sem_venda" for t in serializar(r)["por_trava"])

        no_zero = tmp_path / "no_zero"
        no_zero.mkdir()
        r = gerar(fontes, str(no_zero), VendaAConsumidor.DEMAIS_SAIDAS)
        assert not any(t["codigo"] == "devolucao_sem_venda" for t in serializar(r)["por_trava"])
        linhas = registros(no_zero / PASTA_PREVIAS / f"CAT5_SP_{SP}_1_2024_PREVIA.txt")
        devolucao = next(l for l in linhas if "|1411|" in l)
        assert devolucao.endswith("|0|1002140|1411|1,000|2,50||0")

    def test_cancelar_nao_deixa_arquivo(self, fontes, tmp_path):
        destino = tmp_path / "cancelada"
        destino.mkdir()
        with pytest.raises(ApuracaoCancelada):
            gerar(fontes, str(destino), deve_parar=lambda: True)
        assert not os.path.exists(destino / PASTA_ENVIO)
        assert not os.path.exists(destino / ARQUIVO_ARQUIVOS)


def acrescentar(caminho, linhas: list[dict]) -> None:
    tabela = pq.read_table(caminho)
    pq.write_table(pa.Table.from_pylist(tabela.to_pylist() + linhas, schema=tabela.schema), caminho)


class TestRevisao:
    """O que a revisão da etapa 7 corrigiu, com o piloto da empresa V como origem."""

    def test_o_0200_leva_o_cadastro_do_mes_com_a_unidade_da_ficha(self, fontes, tmp_path):
        # em janeiro o item tinha outra descrição, 12% e estava cadastrado em caixa
        gravar(os.path.join(fontes.movimentacao, ARQUIVO_ITENS_DA_EFD), pa.schema([
            ("cnpj", pa.string()), ("competencia", pa.date32()), ("arquivo", pa.string()), ("codigo", pa.string()),
            ("descricao", pa.string()), ("codigo_barras", pa.string()), ("unidade", pa.string()),
            ("ncm", pa.string()), ("aliq_icms", pa.decimal128(9, 4)), ("cest", pa.string())]), [
            {"cnpj": SP, "competencia": date(2024, 1, 1), "arquivo": "efd_01.txt", "codigo": "1002140",
             "descricao": "IOGURTE 170G ANTIGO", "codigo_barras": "", "unidade": "CX", "ncm": "04032000",
             "aliq_icms": D(12), "cest": "1702200"},
        ])
        destino = tmp_path / "do_mes"
        destino.mkdir()
        gerar(fontes, str(destino))
        janeiro = registros(destino / PASTA_ENVIO / f"CAT5_SP_{SP}_1_2024.txt")
        # descrição e alíquota do mês; o código de barras vazio no mês vem do mais
        # recente; a unidade é a da ficha, não a do mês
        assert "0200|1002140|IOGURTE 170G ANTIGO|07891024183007|UN1|04032000|12,00|1702200" in janeiro
        # fevereiro não tem 0200 do mês: fica com o mais recente
        fevereiro = registros(destino / PASTA_PREVIAS / f"CAT5_SP_{SP}_2_2024_PREVIA.txt")
        assert "0200|1002140|IOGURTE 170G|07891024183007|UN1|04032000|18,00|1702200" in fevereiro

    def test_participante_cadastrado_so_em_outro_mes(self, fontes, tmp_path):
        # a EFD de janeiro perdeu o F1; a de fevereiro o tem
        janeiro = fontes.efds[0][0]
        conteudo = open(janeiro, "rb").read().replace(b"|0150|F1|", b"|0150|F9|")
        open(janeiro, "wb").write(conteudo)
        fevereiro = os.path.join(os.path.dirname(janeiro), "efd_sp_2024_02.txt")
        open(fevereiro, "wb").write(
            (f"|0000|017|0|01022024|29022024|LOJA DE TESTE|{SP}||SP|{IE_SP}|3552205||A|1|\r\n"
             f"|0150|F1|FORNECEDOR DE IOGURTE|1058|{FORNECEDOR}|||3506300||RUA|1||CENTRO|\r\n"
             "|0990|3|\r\n").encode("latin-1"))
        fontes.efds.append((fevereiro, SP, date(2024, 2, 1)))
        destino = tmp_path / "outro_mes"
        destino.mkdir()
        r = gerar(fontes, str(destino))
        assert not any(t["codigo"] == "participante_sem_cadastro" for t in serializar(r)["por_trava"])
        linhas = registros(destino / PASTA_ENVIO / f"CAT5_SP_{SP}_1_2024.txt")
        assert [l.split("|")[1] for l in linhas if l.startswith("0150")] == ["F1", SP]

    def test_icms_negativo_com_estoque_positivo_tem_trava_propria(self, fontes, tmp_path):
        acrescentar(os.path.join(fontes.apuracao, ARQUIVO_SALDOS), [
            {"cnpj": SP, "competencia": "2024-01", "codigo": "999", "qtd_ini": D(5), "icms_tot_ini": D(0),
             "qtd_fim": D(3), "icms_tot_fim": D("-2.00"), "retirada": False}])
        destino = tmp_path / "valor_negativo"
        destino.mkdir()
        r = gerar(fontes, str(destino))
        travas = {t["codigo"] for t in serializar(r)["por_trava"]}
        assert "valor_negativo" in travas and "saldo_negativo" not in travas
        janeiro = arquivos(str(destino), so="valor_negativo")["linhas"]
        assert [(a["competencia"], a["valores_negativos"], a["saldos_negativos"]) for a in janeiro] == [
            ("2024-01", 1, 0)]

    def test_entrada_com_icms_zero_e_contada(self, fontes, tmp_path):
        caminho = os.path.join(fontes.razao, ARQUIVO_FICHA3)
        acrescentar(caminho, [linha_da_ficha(
            cnpj=SP, codigo="1002140", numero=2, data=date(2024, 1, 4), especie="entrada", cfop="2152",
            quantidade=D(1), icms_suportado=D(0), chave=chave(FORNECEDOR, "55", 3), numero_item=1,
            modelo="55", participante="F1", numero_documento="3")])
        destino = tmp_path / "sem_icms"
        destino.mkdir()
        r = gerar(fontes, str(destino))
        assert serializar(r)["entradas_sem_icms"] == 1
        # a entrada com R$ 30 e a venda não contam
        assert arquivos(str(destino), busca="2024-01")["linhas"][0]["entradas_sem_icms"] == 1

    def test_recorte_por_trava_e_pelo_codigo_inteiro(self, gerado):
        destino, _ = gerado
        # "sem_documento" existe; um código parecido, com "_" coringa no LIKE, não
        assert arquivos(str(destino), so="sem_documento")["total"] == 1
        assert arquivos(str(destino), so="item_sem_cadastro")["total"] == 0

    def test_falha_no_meio_nao_deixa_rascunho(self, fontes, tmp_path, monkeypatch):
        import cat.infraestrutura.analitico.arquivo_digital as modulo

        def quebra(_):
            raise RuntimeError("disco cheio")

        monkeypatch.setattr(modulo, "validar", quebra)
        destino = tmp_path / "quebrada"
        destino.mkdir()
        with pytest.raises(RuntimeError):
            gerar(fontes, str(destino))
        assert not [n for n in os.listdir(destino) if n.startswith(".CAT5_")]


class TestSerieDo1200:
    def test_nota_sem_chave_vai_no_1200_com_a_serie_sem_mascara(self, fontes, tmp_path):
        acrescentar(os.path.join(fontes.razao, ARQUIVO_FICHA3), [linha_da_ficha(
            cnpj=SP, codigo="1002140", numero=2, data=date(2024, 1, 4), especie="entrada", cfop="1403",
            quantidade=D(1), icms_suportado=D(0), numero_item=2, modelo="01", participante="F1",
            numero_documento="4455", serie="U-2")])
        destino = tmp_path / "serie"
        destino.mkdir()
        gerar(fontes, str(destino))
        todos = [os.path.join(p, n) for p in (destino / PASTA_ENVIO, destino / PASTA_PREVIAS) for n in os.listdir(p)
                 if "_1_2024" in n]
        linhas = registros(todos[0])
        assert "1200|F1|01||U2|4455|002|0|04012024|1403|1002140|1,000|0,00||" in linhas


class TestEmParalelo:
    def test_varios_processos_escrevem_os_mesmos_arquivos_e_o_mesmo_resumo(self, fontes, tmp_path):
        um, dois = tmp_path / "um", tmp_path / "dois"
        um.mkdir()
        dois.mkdir()
        r1 = gerar(fontes, str(um), processos=1)
        r2 = gerar(fontes, str(dois), processos=2)
        assert serializar(r1) == serializar(r2)

        def indice(destino):
            return {(a["nome"], a["sha256"], a["destino"], tuple(x["codigo"] for x in a["travas"])) for a in arquivos(str(destino))["linhas"]}

        assert indice(um) == indice(dois)
        oc = lambda d: sorted((o["nome"], o["regra"], o["linha"]) for o in  # noqa: E731
                              pq.read_table(str(d / ARQUIVO_OCORRENCIAS)).to_pylist())
        assert oc(um) == oc(dois)
        # as partições são de trabalho: não ficam
        assert not os.path.exists(dois / ".particoes")
