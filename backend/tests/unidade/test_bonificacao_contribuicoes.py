"""Bonificação na EFD-Contribuições, com SPED sintético.

Cada teste guarda uma coisa que o grupo real mostrou (03/11/2026): o C181 e o
C185 fora de ordem, a nota com venda e bonificação juntas, a NFC-e no C175, as
duas versões do mesmo mês, a assinatura depois do 9999 e a nota que não existe
na Contribuições. Ver o topo de `tools/bonificacao_contribuicoes.py`.
"""

from __future__ import annotations

import csv
import datetime as dt
import os

import openpyxl
import pytest

from tools import bonificacao_contribuicoes as b

CNPJ = "11222333000181"
CNPJ_B = "44555666000172"
ASSINATURA = bytes(range(256)) * 30
SPED = os.path.join("6. RECEITANET BX", "SPED Contribuições")


def _chave(cnpj: str, num: str) -> str:
    return f"352401{cnpj}55001{int(num):09d}1{int(num):08d}"[:44].ljust(44, "0")


def c100(num="100", ind_oper="1", sit="00", mod="55", part="C1", cnpj=CNPJ, dt_doc="15012024", vl="100,00"):
    chv = _chave(cnpj, num)
    campos = ["C100", ind_oper, "0", part, mod, sit, "1", num, chv, dt_doc, dt_doc, vl, "0", "0", "0", vl, "9",
              "0", "0", "0", "0", "0", "0", "0", "0", "1,65", "7,60", "0", "0"]
    return "|" + "|".join(campos) + "|"


def c170(cfop, vl="100,00", cst_pis="01", pis="1,65", cst_cof="01", cof="7,60", num="1"):
    bc_pis = vl if pis != "0" else "0"
    bc_cof = vl if cof != "0" else "0"
    campos = ["C170", num, "ITEM1", "", "1", "UN", vl, "0", "0", "000", cfop, "", "0", "0", "0", "0", "0", "0", "", "",
              "", "0", "0", "0", cst_pis, bc_pis, "1,65" if pis != "0" else "0", "", "", pis, cst_cof, bc_cof,
              "7,6" if cof != "0" else "0", "", "", cof, ""]
    return "|" + "|".join(campos) + "|"


def c175(cfop, vl="80,00", pis="1,32", cof="6,08"):
    campos = ["C175", cfop, vl, "0", "01", vl, "1,65", "", "", pis, "01", vl, "7,6", "", "", cof, "", ""]
    return "|" + "|".join(campos) + "|"


def c180(cod_item="ITEM1", total="250,00"):
    return f"|C180|55|01012024|31012024|{cod_item}|22021000||{total}|"


def c18x(reg, cfop, cst, vl, contrib):
    aliq = "1,65" if reg == "C181" else "7,6"
    bc = vl if contrib != "0" else "0"
    return f"|{reg}|{cst}|{cfop}|{vl}|0|{bc}|{aliq if contrib != '0' else '0'}|||{contrib}|CTA1|"


def _sped(corpo: list[str], cnpj=CNPJ, tipo="0", ini="01012024", fim="31012024", assinar=True,
          qtd_lin_errada=False) -> bytes:
    linhas = [f"|0000|006|{tipo}|||{ini}|{fim}|EMPRESA TESTE|{cnpj}|SP|3550308||00|0|", "|0001|0|",
              f"|0140|1|EMPRESA TESTE|{cnpj}|SP|123456||||", "|0150|C1|CLIENTE UM|1058|99888777000166||3550308||R A|1|||",
              "|0200|ITEM1|PRODUTO UM||UN|00|||22021000|||||", "|0990|6|",
              "|C001|0|", f"|C010|{cnpj}|2|"] + corpo + [
              "|C990|0|", "|M001|0|", "|M200|100,00|40,00|0|60,00|0|0|60,00|0|0|0|0|60,00|",
              "|M600|500,00|200,00|0|300,00|0|0|300,00|0|0|0|0|300,00|", "|M990|3|", "|9001|0|", "|9990|2|"]
    total = len(linhas) + 1
    linhas.append(f"|9999|{total + (7 if qtd_lin_errada else 0)}|")
    texto = ("\r\n".join(linhas) + "\r\n").encode("latin-1")
    return texto + (ASSINATURA if assinar else b"")


def _gravar(raiz, empresa: str, cnpj: str, conteudo: bytes, ini="20240101", fim="20240131",
            tipo="Original", transmissao="20240210101010") -> str:
    pasta = raiz / f"{empresa}_{cnpj}" / SPED
    pasta.mkdir(parents=True, exist_ok=True)
    p = pasta / f"PISCOFINS_{ini}_{fim}_{cnpj}_{tipo}_{transmissao}_ABCDEF.txt"
    p.write_bytes(conteudo)
    return str(p)


@pytest.fixture
def grupo(tmp_path):
    # empresa A, item a item: venda + bonificação na mesma nota, bonificação própria, cancelada, entrada e NFC-e
    corpo_a = [
        c100("100"), c170("5102", "200,00", pis="3,30", cof="15,20", num="1"), c170("5910", "100,00", num="2"),
        c100("101"), c170("5910", "50,00", cst_pis="49", pis="0", cst_cof="49", cof="0"),
        c100("102", sit="02"),
        c100("103", ind_oper="0"), c170("1910", "999,00"),
        c100("104", mod="65"), c175("5102", "300,00", "4,95", "22,80"), c175("5910", "80,00", "1,32", "6,08"),
    ]
    _gravar(tmp_path, "EMPRESA A", CNPJ, _sped(corpo_a))
    # empresa B, consolidada: os filhos do C180 fora de ordem entre PIS e COFINS
    corpo_b = [
        c180("ITEM1", "250,00"),
        c18x("C181", "5102", "01", "200,00", "3,30"), c18x("C181", "5910", "08", "50,00", "0"),
        c18x("C185", "5910", "08", "50,00", "0"), c18x("C185", "5102", "01", "200,00", "15,20"),
        c180("ITEM2", "70,00"),
        c18x("C181", "5910", "01", "70,00", "1,16"),            # só PIS: o C185 de 5910 não veio
        c18x("C185", "5102", "01", "70,00", "5,32"),
    ]
    _gravar(tmp_path, "EMPRESA B", CNPJ_B, _sped(corpo_b, cnpj=CNPJ_B))
    (tmp_path / "EMPRESA C_77888999000155" / SPED).mkdir(parents=True)   # pasta vazia
    return tmp_path


def _ler(grupo, empresa: str) -> dict:
    usados, _ = b.escolher_arquivos(str(grupo))
    info = next(u for u in usados if u["empresa"] == empresa)
    return b.ler_arquivo(info)


class TestItemAItem:
    def test_soma_so_o_item_do_cfop_alvo_e_diz_que_a_nota_tem_venda_junto(self, grupo):
        r = _ler(grupo, "EMPRESA A")
        notas = {n[9]: dict(zip(b.COL_NOTAS, n)) for n in r["notas"]}
        n = notas["100"]
        assert n["CFOPs da nota"] == "5102/5910"
        assert n["Tipo de nota"] == "Junto com a venda"
        assert n["Itens no CFOP"] == 1
        assert (n["Valor no CFOP"], n["PIS"], n["COFINS"]) == (100.0, 1.65, 7.60)
        assert n["Valor da nota"] == 100.0 and n["PIS da nota (C100)"] == 1.65
        assert n["Cliente"] == "CLIENTE UM" and n["CNPJ/CPF cliente"] == "99888777000166"
        assert n["Emissão"] == dt.date(2024, 1, 15)

    def test_nota_so_de_bonificacao_sem_contribuicao_sai_com_cst_49_e_zero(self, grupo):
        r = _ler(grupo, "EMPRESA A")
        n = dict(zip(b.COL_NOTAS, next(x for x in r["notas"] if x[9] == "101")))
        assert n["Tipo de nota"] == "Nota própria"
        assert (n["CST PIS"], n["PIS"], n["COFINS"]) == ("49", 0.0, 0.0)

    def test_cancelada_e_entrada_ficam_de_fora_e_contadas(self, grupo):
        r = _ler(grupo, "EMPRESA A")
        numeros = {n[9] for n in r["notas"]}
        assert "102" not in numeros and "103" not in numeros
        assert r["contadores"]["c100_saida_descartada_sit_02"] == 1
        assert r["contadores"]["c100_entrada"] == 1

    def test_nfce_no_c175_entra_como_nota_com_fonte_propria(self, grupo):
        r = _ler(grupo, "EMPRESA A")
        n = dict(zip(b.COL_NOTAS, next(x for x in r["notas"] if x[9] == "104")))
        assert n["Fonte"] == "C175" and n["Modelo"] == "65"
        assert n["CFOPs da nota"] == "5102/5910" and n["Tipo de nota"] == "Junto com a venda"
        assert (n["Valor no CFOP"], n["PIS"], n["COFINS"]) == (80.0, 1.32, 6.08)

    def test_apuracao_do_mes_vem_do_m200_e_m600(self, grupo):
        r = _ler(grupo, "EMPRESA A")
        assert r["apuracao"]["pis"]["total_recolher"] == 60.0
        assert r["apuracao"]["cofins"]["total_recolher"] == 300.0


class TestConsolidado:
    def test_c181_casa_com_o_c185_pelo_cfop_e_nao_pela_posicao(self, grupo):
        r = _ler(grupo, "EMPRESA B")
        linhas = [dict(zip(b.COL_CONS, c)) for c in r["consolidado"]]
        item1 = next(l for l in linhas if l["Cód. item"] == "ITEM1")
        assert item1["CFOP"] == "5910"
        assert (item1["CST PIS"], item1["PIS"]) == ("08", 0.0)
        assert (item1["CST COFINS"], item1["COFINS"]) == ("08", 0.0)      # por posição viria o 5102, com 15,20
        assert item1["Observação"] == ""
        assert item1["Descrição (0200)"] == "PRODUTO UM" and item1["Total do item no mês (C180)"] == 250.0
        assert all(l["CFOP"] == "5910" for l in linhas)

    def test_lado_sem_par_sai_em_branco_e_contado(self, grupo):
        r = _ler(grupo, "EMPRESA B")
        item2 = next(dict(zip(b.COL_CONS, c)) for c in r["consolidado"] if c[6] == "ITEM2")
        assert item2["PIS"] == 1.16 and item2["CST COFINS"] == "" and item2["COFINS"] == 0.0
        assert item2["Observação"] == "sem C185 correspondente (só PIS)"
        assert r["contadores"]["c181_sem_c185"] == 1
        assert r["contadores"].get("c180_filhos_desbalanceados", 0) == 0


class TestArquivo:
    def test_assinatura_depois_do_9999_nao_estraga_a_contagem(self, grupo):
        r = _ler(grupo, "EMPRESA A")
        assert r["valido"] and r["linhas"] == r["qtd_lin_9999"]
        assert r["contadores"].get("linha_fora_do_padrao", 0) == 0

    def test_qtd_lin_divergente_marca_o_arquivo(self, tmp_path):
        _gravar(tmp_path, "EMPRESA D", CNPJ, _sped([c100("1"), c170("5910")], qtd_lin_errada=True))
        r = _ler(tmp_path, "EMPRESA D")
        assert not r["valido"]
        assert r["contadores"]["arquivo_qtd_lin_divergente"] == 1

    def test_mes_com_duas_versoes_usa_a_transmitida_por_ultimo(self, tmp_path):
        _gravar(tmp_path, "EMPRESA E", CNPJ, _sped([c100("1"), c170("5910", "10,00")]), transmissao="20240210101010")
        _gravar(tmp_path, "EMPRESA E", CNPJ, _sped([c100("1"), c170("5910", "20,00")], tipo="1"),
                tipo="Retificadora", transmissao="20240301090000")
        usados, todos = b.escolher_arquivos(str(tmp_path))
        assert len(usados) == 1 and "Retificadora" in usados[0]["nome_arquivo"]
        assert sorted(t["situacao"] for t in todos) == ["substituído por versão mais recente", "usado"]
        r = b.ler_arquivo(usados[0])
        assert r["notas"][0][22] == 20.0

    def test_pasta_vazia_entra_no_inventario_sem_arquivo(self, grupo):
        usados, todos = b.escolher_arquivos(str(grupo))
        assert {u["empresa"] for u in usados} == {"EMPRESA A", "EMPRESA B"}
        assert next(t for t in todos if t["empresa"] == "EMPRESA C")["situacao"] == "pasta vazia"


class TestPlanilha:
    def test_painel_mensal_e_observacoes(self, grupo, tmp_path):
        usados, todos = b.escolher_arquivos(str(grupo))
        resultados = [b.ler_arquivo(u) for u in usados]
        saida = str(tmp_path / "saida" / "bonif.xlsx")
        res = b.planilha(resultados, todos, saida, str(grupo), b.CFOP_PADRAO, hoje=dt.date(2026, 11, 3))
        painel = res["painel"]
        a = painel["EMPRESA A"]
        assert a["Fonte(s)"] == "C170/C175" and a["Notas (C170/C175)"] == 3
        assert a["Valor no CFOP"] == pytest.approx(230.0)
        assert a["PIS"] == pytest.approx(1.65 + 1.32) and a["COFINS"] == pytest.approx(7.60 + 6.08)
        bb = painel["EMPRESA B"]
        assert bb["Linhas consolidadas (C181/C185)"] == 2 and bb["PIS"] == pytest.approx(1.16) and bb["COFINS"] == 0.0
        assert painel["EMPRESA C"]["Observação"] == "Sem EFD-Contribuições na pasta (pasta vazia)"
        assert painel["TOTAL"]["PIS + COFINS"] == pytest.approx(1.65 + 1.32 + 7.60 + 6.08 + 1.16)
        wb = openpyxl.load_workbook(saida, read_only=True)
        assert wb.sheetnames == ["0_Premissas", "1_Painel", "2_Resumo_por_ano", "3_Mensal_por_estab", "4_Por_CFOP_CST",
                                 "5_Por_cliente", "6_Notas", "7_Consolidado_C181_C185", "8_Arquivos"]
        mensal = list(wb["3_Mensal_por_estab"].iter_rows(values_only=True))
        cab = list(mensal[0])
        linha_a = next(l for l in mensal[1:] if l[0] == "EMPRESA A" and l[cab.index("Fonte")] == "C170")
        assert linha_a[cab.index("Situação do mês")] == "Houve PIS/COFINS a recolher"
        assert linha_a[cab.index("PIS a recolher no mês (M200)")] == 60.0
        assert linha_a[cab.index("Prazo prescricional (conservador)")] == dt.datetime(2029, 2, 25)
        assert res["abas"]["6_Notas"] == 3 and res["abas"]["7_Consolidado_C181_C185"] == 2


class TestCruzamento:
    def test_acha_a_chave_e_classifica_pelo_cfop_da_contribuicoes(self, grupo):
        usados, _ = b.escolher_arquivos(str(grupo))
        info = next(u for u in usados if u["empresa"] == "EMPRESA A")
        r = b.cruzar_um((info, {_chave(CNPJ, "100"), _chave(CNPJ, "101"), _chave(CNPJ, "999")}, b.CFOP_PADRAO))
        assert r["tem_c170"] and not r["tem_c180"]
        assert set(r["achadas"]) == {_chave(CNPJ, "100"), _chave(CNPJ, "101")}
        n100 = r["achadas"][_chave(CNPJ, "100")]
        assert n100["cfops"] == {"5102", "5910"} and n100["pis"] == pytest.approx(3.30 + 1.65)
        assert (n100["vl_alvo"], n100["pis_alvo"]) == (100.0, 1.65)
        assert b._classe(n100["cfops"], b.CFOP_PADRAO) == "5910/6910 (CFOP alvo)"
        assert b._classe({"5102"}, b.CFOP_PADRAO) == "CFOP de venda (5102)"

    def test_mes_consolidado_nao_e_cruzavel_mesmo_com_alguma_nota(self):
        assert b.modo_do_mes(tem_c170=False, tem_c180=True) == "consolidado (C180/C181/C185)"
        assert b.modo_do_mes(tem_c170=True, tem_c180=True) == "consolidado (C180/C181/C185) + poucas notas C100"
        assert b.modo_do_mes(tem_c170=True, tem_c180=False) == "item a item (C170/C175)"

    def test_de_ponta_a_ponta_separa_encontrada_nao_encontrada_e_nao_cruzavel(self, grupo, tmp_path):
        usados, _ = b.escolher_arquivos(str(grupo))
        chaves = tmp_path / "chaves.csv"
        with open(chaves, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["empresa", "cnpj", "competencia", "chave", "icms"])
            w.writerow(["EMPRESA A", CNPJ, "01/2024", _chave(CNPJ, "100"), "12,00"])
            w.writerow(["EMPRESA A", CNPJ, "01/2024", _chave(CNPJ, "555"), "3,00"])
            w.writerow(["EMPRESA B", CNPJ_B, "01/2024", _chave(CNPJ_B, "1"), "5,00"])
            w.writerow(["EMPRESA A", CNPJ, "02/2024", _chave(CNPJ, "7"), "1,00"])
        res = b.cruzar(str(chaves), usados, str(tmp_path / "cruz.xlsx"), workers=1, alvo=b.CFOP_PADRAO)
        a, bb = res["resumo"]["EMPRESA A"], res["resumo"]["EMPRESA B"]
        assert a["Notas no CSV"] == 3 and a["Encontradas na Contribuições"] == 1
        assert a["NÃO encontradas (mês item a item)"] == 1 and a["Não cruzável (sem EFD-Contribuições)"] == 1
        assert a["Encontradas com CFOP alvo"] == 1 and a["PIS + COFINS nas encontradas"] == pytest.approx(3.30 + 1.65 + 15.20 + 7.60)
        assert bb["Não cruzável (mês consolidado C180)"] == 1 and bb["Encontradas na Contribuições"] == 0
        assert res["resumo"]["TOTAL"]["Notas no CSV"] == 4
        col = res["colunas"]
        linha_b = next(n for n in res["notas"] if n[0] == "EMPRESA B")
        assert linha_b[col.index("Situação")] == "não cruzável — consolidado (C180/C181/C185)"
        assert linha_b[col.index("icms")] == "5,00"      # as colunas do CSV passam intactas
