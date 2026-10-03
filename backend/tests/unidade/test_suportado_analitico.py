"""A apuração do ICMS suportado ponta a ponta, sobre parquet de verdade.

O que se prova aqui é a junção: o item de CST 60 que a EFD zera precisa sair
com valor quando o relatório do cliente informa, e precisa sair marcado como
"informado pelo fornecedor" — não como se estivesse na nota.
"""

from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.dominio.icms.cat42.suportado import Fonte, Pendencia
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.infraestrutura.analitico.suportado import (
    ARQUIVO_DOCUMENTOS,
    ARQUIVO_RETIDO,
    ARQUIVO_SUPORTADO,
    ESQUEMA_RETIDO,
    ApuracaoCancelada,
    apurar,
    extrair_retido,
    fatias_por_fonte,
    linhas,
    quebras,
)

CNPJ = "44000002000237"
CHAVE_A = "4" * 44
CHAVE_B = "5" * 44
CHAVE_C = "6" * 44


def d(v: str) -> Decimal:
    return Decimal(v)


def escrever_movimentos(pasta, linhas: list[dict]) -> None:
    esquema = pa.schema([
        ("cnpj", pa.string()), ("competencia", pa.date32()),
        ("chave", pa.string()), ("numero_documento", pa.string()),
        ("modelo", pa.string()), ("participante", pa.string()),
        ("data", pa.date32()), ("cfop", pa.string()), ("numero_item", pa.int32()),
        ("codigo", pa.string()), ("descricao", pa.string()),
        ("cst_icms", pa.string()), ("operacao", pa.string()),
        ("quantidade", pa.decimal128(18, 5)),
        ("valor_icms", pa.decimal128(18, 2)),
        ("valor_st", pa.decimal128(18, 2)),
        ("bc_st", pa.decimal128(18, 2)),
    ])
    colunas = {c: [l.get(c) for l in linhas] for c in esquema.names}
    pq.write_table(pa.Table.from_pydict(colunas, schema=esquema),
                   str(pasta / ARQUIVO_MOVIMENTOS))


def escrever_retido(pasta, linhas: list[tuple[str, str, str]]) -> None:
    """Usa o esquema do próprio módulo, e não uma cópia.

    Uma cópia com duas casas escondeu o defeito que derrubou a extração real:
    o teste gravava o que o módulo não gravaria."""
    pq.write_table(pa.Table.from_pydict({
        "chave": [c for c, _, _ in linhas],
        "codigo": [k for _, k, _ in linhas],
        "informado": [d(v) for _, _, v in linhas],
    }, schema=ESQUEMA_RETIDO), str(pasta / ARQUIVO_RETIDO))


def escrever_cadastro(pasta, linhas: list[tuple[str, str, str]]) -> None:
    esquema = pa.schema([("cnpj", pa.string()), ("codigo", pa.string()),
                         ("aliq_icms", pa.decimal128(9, 4))])
    pq.write_table(pa.Table.from_pydict({
        "cnpj": [c for c, _, _ in linhas],
        "codigo": [k for _, k, _ in linhas],
        "aliq_icms": [d(a) for _, _, a in linhas],
    }, schema=esquema), str(pasta / ARQUIVO_ITENS))


def movimento(**kw) -> dict:
    base = {"cnpj": CNPJ, "competencia": date(2021, 5, 1), "chave": CHAVE_A,
            "numero_documento": "4411", "modelo": "55", "participante": "F168181",
            "data": date(2021, 5, 3), "cfop": "1403", "numero_item": 1,
            "codigo": "117110", "descricao": "Alface crespa", "cst_icms": "060",
            "operacao": "entrada",
            "quantidade": d("1.00000"), "valor_icms": d("0.00"),
            "valor_st": d("0.00"), "bc_st": d("0.00")}
    base.update(kw)
    return base


def ler_saida(pasta) -> list[dict]:
    return pq.read_table(str(pasta / ARQUIVO_SUPORTADO)).to_pylist()


class TestSemRelatorio:
    def test_cst60_sozinho_fica_sem_apurar(self, tmp_path):
        """O retrato de hoje sem o relatório do cliente: a EFD não tem."""
        escrever_movimentos(tmp_path, [movimento()])
        resumo = apurar(str(tmp_path))
        assert resumo.itens == 1
        assert resumo.itens_apurados == 0
        assert resumo.por_fonte[Fonte.NAO_APURAVEL] == 1
        linha = ler_saida(tmp_path)[0]
        assert linha["fonte"] == "nao_apuravel"
        assert "CST 60" in linha["motivo"]

    def test_destacado_na_entrada_apura_sem_relatorio(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
        ])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("27.00")
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 1
        assert ler_saida(tmp_path)[0]["suportado"] == d("27.00")

    def test_saida_nao_entra_na_apuracao(self, tmp_path):
        """Saída consome o suportado, não o traz."""
        escrever_movimentos(tmp_path, [
            movimento(operacao="saida", cst_icms="060"),
            movimento(operacao="entrada", cst_icms="010",
                      valor_icms=d("1.00"), valor_st=d("1.00")),
        ])
        assert apurar(str(tmp_path)).itens == 1


class TestComRelatorio:
    def test_o_relatorio_fecha_o_buraco_do_cst60(self, tmp_path):
        """O ponto da etapa: o que a EFD zera, o cliente informa."""
        escrever_movimentos(tmp_path, [movimento()])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("4.75")
        assert resumo.por_fonte[Fonte.INFORMADO_PELO_FORNECEDOR] == 1
        assert resumo.cobertura == 1.0
        assert ler_saida(tmp_path)[0]["fonte"] == "informado_pelo_fornecedor"

    def test_o_valor_informado_nao_se_disfarca_de_documento(self, tmp_path):
        """A procedência é o que separa pedido sustentável de chute."""
        escrever_movimentos(tmp_path, [movimento()])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_documental == d("4.75")
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 0

    def test_a_juncao_e_por_chave_E_codigo(self, tmp_path):
        """Chave igual e código diferente não casa: uma nota tem muitos itens,
        e casar só pela chave daria o imposto de um item a outro."""
        escrever_movimentos(tmp_path, [
            movimento(codigo="117110"),
            movimento(codigo="999999"),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(tmp_path))
        assert resumo.por_fonte[Fonte.INFORMADO_PELO_FORNECEDOR] == 1
        assert resumo.por_fonte[Fonte.NAO_APURAVEL] == 1

    def test_nota_diferente_nao_casa(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento(chave=CHAVE_B)])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        assert apurar(str(tmp_path)).itens_apurados == 0

    def test_destaque_na_nota_vence_o_informado(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "999.00")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("27.00")
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 1


class TestPrecisao:
    """O relatório do cliente traz ICMS com quatro casas.

    Um esquema de duas casas não grava esse valor: o pyarrow recusa a
    gravação inteira. Foi o que derrubou a primeira extração de 2021, depois
    de treze minutos de leitura.
    """

    def test_valor_com_quatro_casas_sobrevive(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento()])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "2.3341")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("2.3341")
        assert ler_saida(tmp_path)[0]["suportado"] == d("2.334100")

    def test_soma_de_centavos_nao_se_perde(self, tmp_path):
        """Arredondar item a item desloca o total em base grande."""
        escrever_movimentos(tmp_path, [
            movimento(chave=CHAVE_A), movimento(chave=CHAVE_B),
            movimento(chave=CHAVE_C),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "0.3333"),
                                   (CHAVE_B, "117110", "0.3333"),
                                   (CHAVE_C, "117110", "0.3333")])
        assert apurar(str(tmp_path)).valor_total == d("0.9999")


class TestReconstrucao:
    def test_base_e_aliquota_do_cadastro_reconstroem(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento(bc_st=d("150.00"))])
        escrever_cadastro(tmp_path, [(CNPJ, "117110", "18.0000")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("27.00")
        assert resumo.por_fonte[Fonte.BASE_E_ALIQUOTA] == 1
        assert resumo.valor_documental == Decimal(0), "reconstrução não é documento"

    def test_sem_cadastro_nao_reconstroi(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento(bc_st=d("150.00"))])
        assert apurar(str(tmp_path)).itens_apurados == 0


class TestResumoParaATela:
    def test_a_cascata_vem_inteira_e_na_ordem_mesmo_com_fonte_zerada(self, tmp_path):
        """A fonte reconstruída com zero é informação: é o que diz que nada foi
        estimado. Esconder a fonte zerada apagaria isso."""
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
            movimento(chave=CHAVE_B),
        ])
        escrever_retido(tmp_path, [(CHAVE_B, "117110", "5.00")])
        fatias = fatias_por_fonte(apurar(str(tmp_path)))
        assert [f["codigo"] for f in fatias] == [
            "documento", "informado_pelo_fornecedor", "base_e_aliquota", "nao_apuravel"]
        reconstruido = fatias[2]
        assert reconstruido["itens"] == 0 and reconstruido["documental"] is False
        assert fatias[3]["documental"] is None      # não apurável não é sim nem não
        assert all(f["rotulo"] for f in fatias)

    def test_cobertura_e_fracao_documental(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
            movimento(chave=CHAVE_B, bc_st=d("100.00")),
            movimento(chave=CHAVE_C),
        ])
        escrever_cadastro(tmp_path, [(CNPJ, "117110", "18.0000")])
        resumo = apurar(str(tmp_path))
        assert resumo.itens == 3
        assert resumo.itens_apurados == 2
        assert round(resumo.cobertura, 4) == round(2 / 3, 4)
        assert resumo.valor_total == d("45.00")        # 27 + 18
        assert resumo.valor_documental == d("27.00")


class TestPastasSeparadas:
    """Movimentos são da etapa 3; resultado é desta. Na mesma pasta, rodar a
    apuração de novo sobrescreveria material de outra etapa."""

    def test_le_de_uma_pasta_e_grava_em_outra(self, tmp_path):
        mov = tmp_path / "movimentos"
        mov.mkdir()
        apu = tmp_path / "apuracao"
        apu.mkdir()
        escrever_movimentos(mov, [movimento()])
        escrever_retido(apu, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(mov), str(apu))
        assert resumo.valor_total == d("4.75")
        assert (apu / ARQUIVO_SUPORTADO).is_file()
        assert not (mov / ARQUIVO_SUPORTADO).exists()


class TestAndamentoECancelamento:
    def test_avisa_o_andamento(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(), movimento(chave=CHAVE_B, cnpj="99887766000105")])
        vistos = []
        apurar(str(tmp_path),
               avisar=lambda a: vistos.append((a.itens, a.estabelecimentos)))
        assert vistos and vistos[-1] == (2, 2)

    def test_cancelar_para_e_nao_deixa_meio_resultado(self, tmp_path):
        """Meio parquet no disco seria lido depois como apuração inteira."""
        escrever_movimentos(tmp_path, [movimento()])
        with pytest.raises(ApuracaoCancelada):
            apurar(str(tmp_path), deve_parar=lambda: True)
        assert not (tmp_path / ARQUIVO_SUPORTADO).exists()
        assert not (tmp_path / ARQUIVO_DOCUMENTOS).exists()

    def test_extrair_retido_respeita_o_cancelamento(self, tmp_path):
        with pytest.raises(ApuracaoCancelada):
            extrair_retido(["qualquer.txt"], str(tmp_path / "r.parquet"),
                           deve_parar=lambda: True)


CABECALHO_MOVIMENTO = (
    "Código|Descricao|Código Barras|Trib|Dt Emissão|Número Dcto|Ent|"
    "Qtde;Unitária|Valor|BC ICMS|Valor ICMS|Valor BC ST;Informada|"
    "Valor ST;Informada|Valor FCP ST|CNPJ/CPF|UF|CFOP;Mvto|CST;ICMS|"
    "BC ICMS ST;XML|VR. ICMS ST;XML|ST integral|Chave DFe"
)


def relatorio(pasta, nome: str, linhas: list[tuple[str, str, str]]) -> str:
    """Relatório gerencial de entradas com (chave, código, ST retido antes)."""
    corpo = [CABECALHO_MOVIMENTO] + [
        f"{codigo}|Item|789|0403|02/05/21|1|1|1|10|0|0|0|0|0|00176231110|SP|1.403|060|0|0|"
        f"{st}|{chave}"
        for chave, codigo, st in linhas
    ]
    caminho = pasta / nome
    caminho.write_bytes(("\r\n".join(corpo) + "\r\n").encode("latin-1"))
    return str(caminho)


class TestExtrairRetido:
    def test_soma_o_mesmo_item_entre_relatorios(self, tmp_path):
        """O mês quebrado por praça põe o mesmo item em dois relatórios, e vale
        o total — somado agora no DuckDB, e não num dicionário em memória."""
        a = relatorio(tmp_path, "sp.txt", [(CHAVE_A, "117110", "1,25"), (CHAVE_B, "9", "2,00")])
        b = relatorio(tmp_path, "pr.txt", [(CHAVE_A, "117110", "3,50")])
        destino = tmp_path / ARQUIVO_RETIDO
        r = extrair_retido([a, b], str(destino))
        assert r.itens == 2 and r.arquivos == 2 and r.recusados == 0
        lido = {(x["chave"], x["codigo"]): x["informado"]
                for x in pq.read_table(str(destino)).to_pylist()}
        assert lido == {(CHAVE_A, "117110"): d("4.75"), (CHAVE_B, "9"): d("2.00")}
        assert not (tmp_path / (ARQUIVO_RETIDO + ".partes")).exists()

    def test_relatorio_so_de_saidas_nao_e_lido_inteiro(self, tmp_path, monkeypatch):
        import cat.infraestrutura.analitico.suportado as mod
        monkeypatch.setattr(mod, "AMOSTRA_PARA_ACHAR_ENTRADA", 2)
        saidas = [(CHAVE_A, "1", "0")] * 3
        caminho = relatorio(tmp_path, "saidas.txt", saidas).replace(".txt", ".txt")
        # troca o CFOP de entrada por um de venda
        texto = open(caminho, encoding="latin-1").read().replace("1.403", "5.405")
        open(caminho, "w", encoding="latin-1", newline="").write(texto)
        r = extrair_retido([caminho], str(tmp_path / ARQUIVO_RETIDO))
        assert r.so_de_saidas == 1 and r.itens == 0

    def test_sem_nada_informado_grava_parquet_vazio(self, tmp_path):
        destino = tmp_path / ARQUIVO_RETIDO
        assert extrair_retido([], str(destino)).itens == 0
        assert pq.read_table(str(destino)).num_rows == 0


class TestPendenciaNoParquet:
    def test_separa_sem_o_que_apurar_de_falta_dado(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(chave=CHAVE_A, cst_icms="040"),
            movimento(chave=CHAVE_B, cst_icms="060"),
        ])
        resumo = apurar(str(tmp_path))
        assert resumo.por_pendencia[Pendencia.SEM_O_QUE_APURAR] == 1
        assert resumo.por_pendencia[Pendencia.FALTA_DADO] == 1
        pend = {l["cst_icms"]: l["pendencia"] for l in ler_saida(tmp_path)}
        assert pend == {"040": "sem_o_que_apurar", "060": "falta_dado"}


class TestQuebras:
    def test_por_cst_por_competencia_e_estabelecimentos(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(chave=CHAVE_A, competencia=date(2021, 5, 1)),
            movimento(chave=CHAVE_B, competencia=date(2021, 6, 1), cst_icms="040",
                      cnpj="99887766000105"),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        apurar(str(tmp_path))
        q = quebras(str(tmp_path))
        assert q["estabelecimentos"] == 2
        cst = {c["cst"]: c for c in q["por_cst"]}
        assert cst["60"]["valor"] == d("4.75") and cst["60"]["apurados"] == 1
        assert cst["40"]["apurados"] == 0
        comp = {c["competencia"]: c for c in q["por_competencia"]}
        assert comp["2021-05"]["cobertura"] == 1.0
        assert comp["2021-06"]["cobertura"] == 0.0
        assert q["cst_sem_o_que_apurar"] == {"cst": "40", "itens": 1}


class TestAnalitico:
    def _base(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(chave=CHAVE_A, codigo="1", descricao="Leite condensado"),
            movimento(chave=CHAVE_A, codigo="2", descricao="Refrigerante"),
            movimento(chave=CHAVE_B, codigo="3", cst_icms="040", participante="F999"),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "1", "5.00"), (CHAVE_A, "2", "3.00")])
        apurar(str(tmp_path))

    def test_por_item_e_uma_linha_por_item(self, tmp_path):
        self._base(tmp_path)
        r = linhas(str(tmp_path), escopo="item")
        assert r["total"] == 3 and len(r["linhas"]) == 3

    def test_por_documento_agrupa_e_traz_os_itens(self, tmp_path):
        self._base(tmp_path)
        r = linhas(str(tmp_path), escopo="documento")
        assert r["total"] == 2
        doc_a = next(x for x in r["linhas"] if x["chave"] == CHAVE_A)
        assert doc_a["itens"] == 2 and len(doc_a["filhos"]) == 2
        assert Decimal(doc_a["suportado"]) == d("8.00")
        assert doc_a["fonte"] == "informado_pelo_fornecedor"

    def test_filtrar_por_fonte_filtra_antes_de_agrupar(self, tmp_path):
        self._base(tmp_path)
        r = linhas(str(tmp_path), escopo="documento", fonte="nao_apuravel")
        assert [x["chave"] for x in r["linhas"]] == [CHAVE_B]

    def test_busca_por_descricao_participante_e_chave(self, tmp_path):
        self._base(tmp_path)
        assert linhas(str(tmp_path), escopo="item", busca="condensado")["total"] == 1
        assert linhas(str(tmp_path), escopo="item", busca="F999")["total"] == 1
        assert linhas(str(tmp_path), escopo="documento", busca=CHAVE_B[:20])["total"] == 1

    def test_paginacao_no_servidor(self, tmp_path):
        self._base(tmp_path)
        p1 = linhas(str(tmp_path), escopo="item", pagina=1, por_pagina=2)
        p2 = linhas(str(tmp_path), escopo="item", pagina=2, por_pagina=2)
        assert len(p1["linhas"]) == 2 and len(p2["linhas"]) == 1
        assert p1["total"] == p2["total"] == 3

    def test_por_pagina_tem_teto(self, tmp_path):
        self._base(tmp_path)
        assert linhas(str(tmp_path), por_pagina=10_000)["por_pagina"] == 200

    def test_o_indice_responde_igual_ao_calculo_na_hora(self, tmp_path):
        """O índice é atalho, não outra verdade: sem ele, a mesma página."""
        self._base(tmp_path)
        assert (tmp_path / ARQUIVO_DOCUMENTOS).is_file()
        pedidos = [dict(escopo="documento"), dict(escopo="documento", fonte="nao_apuravel"),
                   dict(escopo="documento", fonte="informado_pelo_fornecedor",
                        pagina=1, por_pagina=1)]
        com_indice = [linhas(str(tmp_path), **p) for p in pedidos]
        (tmp_path / ARQUIVO_DOCUMENTOS).unlink()
        sem_indice = [linhas(str(tmp_path), **p) for p in pedidos]
        assert com_indice == sem_indice

    def test_paginacao_pelo_indice_nao_repete_nem_pula(self, tmp_path):
        chaves = [str(n) * 44 for n in range(1, 8)]
        escrever_movimentos(tmp_path, [movimento(chave=c) for c in chaves])
        apurar(str(tmp_path))
        vistas = []
        for pagina in (1, 2, 3, 4):
            vistas += [d["chave"] for d in
                       linhas(str(tmp_path), escopo="documento", pagina=pagina, por_pagina=2)["linhas"]]
        assert vistas == sorted(chaves)

    def test_nota_sem_chave_nao_vira_um_documento_so(self, tmp_path):
        """Nota modelo 1 não tem chave. Agrupar pela chave vazia juntava todas
        numa só: 904 itens de 667 notas na base real."""
        escrever_movimentos(tmp_path, [
            movimento(chave="", modelo="01", numero_documento="10", codigo="1"),
            movimento(chave="", modelo="01", numero_documento="10", codigo="2"),
            movimento(chave="", modelo="01", numero_documento="11", codigo="1"),
            movimento(chave=CHAVE_A),
        ])
        apurar(str(tmp_path))
        for com_indice in (True, False):
            if not com_indice:
                (tmp_path / ARQUIVO_DOCUMENTOS).unlink()
            r = linhas(str(tmp_path), escopo="documento")
            assert r["total"] == 3, com_indice
            itens = {d["numero_documento"]: len(d["filhos"]) for d in r["linhas"] if not d["chave"]}
            assert itens == {"10": 2, "11": 1}, com_indice
            assert len({d["documento"] for d in r["linhas"]}) == 3

    def test_escopo_e_fonte_desconhecidos_sao_recusados(self, tmp_path):
        self._base(tmp_path)
        with pytest.raises(ValueError, match="Escopo"):
            linhas(str(tmp_path), escopo="tudo")
        with pytest.raises(ValueError, match="Fonte"):
            linhas(str(tmp_path), fonte="chute")


class TestOrdemDasEtapas:
    def test_sem_movimentacao_a_apuracao_recusa_e_diz_o_que_falta(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="movimentação"):
            apurar(str(tmp_path))
