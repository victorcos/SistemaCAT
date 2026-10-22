"""A triagem da rede, com SPED sintético.

Cada teste reproduz uma coisa que a rede real mostrou (22/10/2026) e que um
leitor ingênuo erra: a assinatura depois do 9999, a cópia em outra pasta, as
duas retificadoras do mesmo mês, o arquivo cortado, e o serviço tomado que não
é receita. Ver o topo de `inventario_contribuicoes.py`.
"""

from __future__ import annotations

import csv
import sqlite3
from decimal import Decimal

from cat.infraestrutura.arquivos import inventario_contribuicoes as inv
from tools import triagem_contribuicoes as ferramenta

CNPJ = "11222333000181"
# o PKCS#7 que o PVA anexa depois do 9999: binário, perto de 8 KB
ASSINATURA = bytes(range(256)) * 30


def _sped(corpo: list[str], tipo_escrit: str = "0", inicio: str = "01012024",
          fim: str = "31012024", assinar: bool = True) -> bytes:
    linhas = [f"|0000|006|{tipo_escrit}|||{inicio}|{fim}|EMPRESA TESTE|{CNPJ}|SP|3550308||00|0|",
              "|0001|0|"] + corpo
    contagem: dict[str, int] = {}
    for l in linhas:
        r = l.split("|")[1]
        contagem[r] = contagem.get(r, 0) + 1
    bloco9 = ["|9001|0|"] + [f"|9900|{r}|{n}|" for r, n in contagem.items()]
    bloco9 += ["|9900|9001|1|", f"|9900|9900|{len(contagem) + 4}|", "|9900|9990|1|", "|9900|9999|1|"]
    total = len(linhas) + len(bloco9) + 2
    bloco9 += [f"|9990|{len(bloco9) + 2}|", f"|9999|{total}|"]
    texto = ("\r\n".join(linhas + bloco9) + "\r\n").encode("cp1252")
    return texto + (ASSINATURA if assinar else b"")


BLOCO_A = [
    "|A001|0|", f"|A010|{CNPJ}|",
    # prestado (saída), com ISS no SPED
    "|A100|1|0|P1|00|1||10|NFSE1|01012024|01012024|1000,00|0|0|1000,00|16,50|1000,00|76,00|0|0|50,00|",
    "|A170|1|S1|SERVICO|1000,00|0|||01|1000,00|1,65|16,50|01|1000,00|7,6|76,00||",
    # prestado sem VL_ISS: o ISS está na NFS-e, não aqui
    "|A100|1|0|P1|00|1||11|NFSE2|02012024|02012024|200,00|0|0|200,00|3,30|200,00|15,20|0|0||",
    "|A170|1|S1|SERVICO|200,00|0|||01|200,00|1,65|3,30|01|200,00|7,6|15,20||",
    # tomado (entrada): é crédito, não receita
    "|A100|0|1|P2|00|1||77|NFSE3|01012024|01012024|300,00|0|0|300,00|4,95|300,00|22,80|0|0|15,00|",
    "|A170|1|S2|TOMADO|300,00|0|03|0|50|300,00|1,65|4,95|50|300,00|7,6|22,80||",
    # cancelado: não conta
    "|A100|1|0|P1|02|1||12|NFSE4|03012024|03012024|900,00|0|0|900,00|14,85|900,00|68,40|0|0|45,00|",
    "|A990|10|",
    "|C001|1|", "|C990|2|",
]
SEM_BLOCO_A = ["|A001|1|", "|A990|2|", "|C001|1|", "|C990|2|"]


def test_assinatura_depois_do_9999_nao_e_arquivo_cortado():
    b = _sped(BLOCO_A)
    d = inv.identificar(b[:4096], b[-inv.TRECHO:])
    assert (d["tipo"], d["cnpj"], d["dt_ini"]) == ("efd_contribuicoes", CNPJ, "2024-01-01")
    assert d["completo"] == 1 and d["assinado"] == 1 and d["qtd_lin_9999"] > 0
    # o 9900 diz quantos A100 há, sem ler o meio do arquivo
    assert (d["qtd_a100"], d["qtd_a170"]) == (4, 3)


def test_arquivo_cortado_e_contagem_desconhecida():
    # cortado no meio do texto, antes do 9999 (e portanto sem assinatura)
    b = _sped(BLOCO_A, assinar=False)
    b = b[: len(b) // 2]
    d = inv.identificar(b[:4096], b)
    assert d["completo"] == 0 and "9999" in d["motivo"]
    # sem o bloco 9 não se sabe — e não saber não é zero
    assert d.get("qtd_a100") is None


def test_o_que_nao_e_sped():
    assert inv.identificar(b"CNPJ;VALOR\r\n", b"")["status"] == "nao_sped"


def test_bloco_a_separa_saida_entrada_e_cancelado(tmp_path):
    p = tmp_path / "jan.txt"
    p.write_bytes(_sped(BLOCO_A))
    r = inv.ler_bloco_a(str(p))
    assert (r.a100_saida, r.a100_saida_tributada, r.a100_entrada, r.a100_cancelado) == (2, 2, 1, 1)
    assert r.vl_iss_saida == Decimal("50.00") and r.saidas_sem_iss == 1
    assert r.vl_doc_saida == Decimal("1200.00")
    assert r.a990_confere is True
    # parou no A990: não leu o bloco C nem o 9
    assert r.bytes_lidos < len(p.read_bytes()) // 2


def test_a990_que_nao_bate_e_denunciado(tmp_path):
    p = tmp_path / "jan.txt"
    p.write_bytes(_sped([l if l != "|A990|10|" else "|A990|9|" for l in BLOCO_A]))
    assert inv.ler_bloco_a(str(p)).a990_confere is False


def _rede(tmp_path):
    raiz = tmp_path / "rede" / "CLIENTE"
    (raiz / "2024").mkdir(parents=True)
    (raiz / "copia").mkdir()
    (raiz / "2024" / "jan.txt").write_bytes(_sped(BLOCO_A))
    (raiz / "copia" / "jan.txt").write_bytes(_sped(BLOCO_A))                       # cópia idêntica
    (raiz / "2024" / "fev.txt").write_bytes(_sped(SEM_BLOCO_A, "0", "01022024", "29022024"))
    (raiz / "2024" / "fev_ret.txt").write_bytes(_sped(SEM_BLOCO_A, "1", "01022024", "29022024",
                                                      assinar=False))              # retificadora
    (raiz / "2024" / "abr.txt").write_bytes(_sped(SEM_BLOCO_A, "0", "01042024", "30042024", assinar=False)[:120])  # cortado
    (raiz / "2024" / "planilha.txt").write_bytes(b"nada")
    (raiz / "2024" / "vazio.txt").write_bytes(b"")
    return raiz


def test_varredura_reexecucao_e_versoes(tmp_path):
    raiz = _rede(tmp_path)
    banco = str(tmp_path / "inv.sqlite")
    assert ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz)]) == 0
    db = sqlite3.connect(banco)
    assert dict(db.execute("SELECT status, COUNT(*) FROM arquivo GROUP BY 1")) == {
        "ok": 5, "nao_sped": 1, "vazio": 1}
    # reexecução: nada relido, nada duplicado
    assert ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz)]) == 0
    assert db.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0] == 7
    assert db.execute("SELECT reaproveitados FROM execucao ORDER BY id DESC").fetchone()[0] == 7

    v = {x["dt_ini"]: x for x in inv.versoes(db)}
    assert v["2024-01-01"]["situacao"] == "copias_identicas" and v["2024-01-01"]["copias_redundantes"] == 1
    assert v["2024-02-01"]["situacao"] == "retificadora_unica"
    assert v["2024-02-01"]["arquivo"].endswith("fev_ret.txt")
    assert v["2024-04-01"]["situacao"] == "incompleto"


def test_duas_retificadoras_diferentes_vao_para_revisao(tmp_path):
    raiz = tmp_path / "r"
    raiz.mkdir()
    (raiz / "PISCOFINS_x_Retificadora_20250422162131_a.txt").write_bytes(_sped(SEM_BLOCO_A, "1"))
    (raiz / "PISCOFINS_x_Retificadora_20260512112659_b.txt").write_bytes(_sped(BLOCO_A, "1"))
    banco = str(tmp_path / "i.sqlite")
    ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz)])
    [v] = inv.versoes(sqlite3.connect(banco))
    assert v["situacao"] == "revisao"
    # a sugestão é a mais nova pelo carimbo do nome — sugestão, não decisão
    assert "20260512112659" in v["arquivo"]


def test_interrompida_e_retomada_sem_perder_nem_repetir(tmp_path):
    raiz = _rede(tmp_path)
    banco = str(tmp_path / "inv.sqlite")
    assert ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz),
                            "--limite-segundos", "0"]) == 3
    db = sqlite3.connect(banco)
    assert db.execute("SELECT status FROM execucao").fetchone()[0] == "interrompida"
    assert ferramenta.main(["varrer", "--inventario", banco, "--retomar", "1"]) == 0
    assert db.execute("SELECT COUNT(*) FROM arquivo").fetchone()[0] == 7


def test_relatorio_por_cnpj(tmp_path):
    raiz = _rede(tmp_path)
    banco = str(tmp_path / "inv.sqlite")
    ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz)])
    assert ferramenta.main(["bloco-a", "--inventario", banco]) == 0
    saida = tmp_path / "triagem.csv"
    assert ferramenta.main(["relatorio", "--inventario", banco, "--saida", str(saida)]) == 0
    [linha] = list(csv.DictReader(open(saida, encoding="utf-8-sig"), delimiter=";"))
    assert linha["cnpj"] == CNPJ
    assert linha["competencias"] == "3" and linha["competencias_ausentes"] == "2024-03"
    assert linha["competencias_com_a100"] == "2024-01"
    # a cópia não conta em dobro
    assert linha["a100_declarados"] == "4" and linha["copias_redundantes"] == "1"
    assert linha["a100_saida_tributada"] == "2" and linha["vl_iss_saida_no_sped"] == "50.00"
    assert linha["saidas_sem_iss_no_sped"] == "1" and linha["periodos_incompletos"] == "2024-04"


def test_bloco_a_so_da_versao_escolhida_e_so_da_raiz_pedida(tmp_path):
    raiz = _rede(tmp_path)
    outra = tmp_path / "outra"
    outra.mkdir()
    (outra / "jan.txt").write_bytes(_sped(BLOCO_A, inicio="01052024", fim="31052024"))
    banco = str(tmp_path / "inv.sqlite")
    ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz), "--raiz", str(outra)])
    i = inv.Inventario(banco)
    # jan.txt e a cópia dele têm o mesmo conteúdo: só um é lido
    assert i.ler_blocos_a([str(raiz)]) == 1
    assert i.db.execute("SELECT COUNT(*) FROM bloco_a").fetchone()[0] == 1
    # a outra raiz fica para depois, e entra quando pedida
    assert i.ler_blocos_a() == 1


def test_arquivo_entre_64_e_128_kb_tem_o_fim_lido(tmp_path):
    # 400 notas de serviço põem o arquivo no meio da faixa que perdia o fim
    corpo = ["|A001|0|", f"|A010|{CNPJ}|"]
    for n in range(400):
        corpo += [f"|A100|1|0|P1|00|1||{n}|NFSE{n}|01012024|01012024|100,00|0|0|100,00|1,65|100,00|7,60|0|0|5,00|",
                  "|A170|1|S1|SERVICO DE TESTE COM DESCRICAO|100,00|0|||01|100,00|1,65|1,65|01|100,00|7,6|7,60||"]
    corpo += [f"|A990|{len(corpo) + 1}|", "|C001|1|", "|C990|2|"]
    b = _sped(corpo)
    assert inv.TRECHO < len(b) <= 2 * inv.TRECHO
    raiz = tmp_path / "r"
    raiz.mkdir()
    (raiz / "medio.txt").write_bytes(b)
    banco = str(tmp_path / "i.sqlite")
    ferramenta.main(["varrer", "--inventario", banco, "--raiz", str(raiz)])
    assert sqlite3.connect(banco).execute(
        "SELECT completo, assinado, qtd_a100 FROM arquivo").fetchone() == (1, 1, 400)
