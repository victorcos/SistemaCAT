"""A planilha do relatório CAT 42 por filial, no leiaute v5 — o acordado na empresa 18."""
from __future__ import annotations

import logging
import time
from collections import defaultdict

import xlsxwriter

from relatorio_cat42_filial_comum import (ESTOQUE, LIMITE_EXCEL, MESMO, PARADO, SEM_PAR, SO_ENTRADA, UNIFICADO,
                             descricao_bate, descricao_com_outras, ean, lista, media, n)

log = logging.getLogger("relatorio_cat42_filial")

CAB_DADOS = [
    "CNPJ da filial", "COD_ITEM", "CÓDIGO ANTIGO (de entrada, unificado neste código)",
    "DESCRIÇÃO NA ENTRADA (como veio na nota de compra)", "DESCRIÇÃO NA SAÍDA (como saiu na venda: cupom / NF-e)",
    "Entrada × saída: a descrição bate?", "EAN", "Situação do item",
    "Este código tem compra em quantas OUTRAS filiais",
    "MESMO PRODUTO com outro código: código",
    "Descrição desse outro código (compra: como veio na nota / venda: como saiu)",
    "EAN desse outro código", "Quem é comprado e quem é vendido", "Quantidade (compra → venda)",
    "Por que o sistema ligou os dois", "Unidade (este código × o outro)", "Observação da análise (preencher)",
    "Alíquota ICMS", "Redução de Base do ST",
    "ENTRADA - CNPJs (fornecedores)", "ENTRADA - NCM", "ENTRADA - CEST", "ENTRADA - CFOPs",
    "ENTRADA - Quantidade", "ENTRADA - Quantidade - Devolução", "ENTRADA - Unidade",
    "ENTRADA - CST ICMS / CSOSN", "ENTRADA - Valor Total",
    "ENTRADA - Valor Unitário Mínimo", "ENTRADA - Valor Unitário Máximo", "ENTRADA - Valor Unitário Médio",
    "ENTRADA - Data Mínima", "ENTRADA - Data Máxima",
    "ENTRADA - Valor Unitário do ICMS - Mínimo", "ENTRADA - Valor Unitário do ICMS - Máximo",
    "ENTRADA - Valor Unitário do ICMS - Médio",
    "ENTRADA - Valor Unitário da base do ST - Mínimo", "ENTRADA - Valor Unitário da base do ST - Máximo",
    "ENTRADA - Valor Unitário da base do ST - Médio",
    "ENTRADA - Quantidade de itens sem base do ST", "ENTRADA - Quantidade de NFs sem base do ST",
    "ENTRADA - Quantidade de NFs", "ENTRADA - NFs sem ST",
    "ENTRADA - Conversão de unidade aplicada (nota → cadastro)",
    "SAÍDA - NCM", "SAÍDA - CEST", "SAÍDA - CFOPs", "SAÍDA - Quantidade", "SAÍDA - Quantidade - Devolução",
    "SAÍDA - Unidade", "SAÍDA - Valor Total",
    "SAÍDA - Valor Unitário Mínimo", "SAÍDA - Valor Unitário Máximo", "SAÍDA - Valor Unitário Médio",
    "SAÍDA - Valor Total Interestadual", "SAÍDA - Data Mínima", "SAÍDA - Data Máxima",
    "SAÍDA - Valor Unitário do ICMS - Mínimo", "SAÍDA - Valor Unitário do ICMS - Máximo",
    "SAÍDA - Valor Unitário do ICMS - Médio",
    "ENTRADA x SAÍDA - MVA ST Mínimo", "ENTRADA x SAÍDA - MVA ST Máximo", "ENTRADA x SAÍDA - MVA ST Médio",
    "ENTRADA x SAÍDA - IVA Médio", "ENTRADA x SAÍDA - Relação Base do ST / Venda",
]
FAIXAS = [(0, 2, "Filial"), (2, 3, "DE-PARA"), (3, 19, "Item"),
          (19, 44, "ENTRADAS (compras)"), (44, 60, "SAÍDAS (vendas)"), (60, 65, "ENTRADA x SAÍDA")]

CAB_SEM_PAR = ["CNPJ da filial", "COD_ITEM", "DESCRIÇÃO NA SAÍDA (como saiu na venda)", "EAN (cadastro)",
               "NCM", "Unidade", "Quantidade saída", "Valor Total saída", "Valor Unitário Médio saída",
               "Este código tem compra em quantas OUTRAS filiais", "Código do mesmo produto (preencher)",
               "Fator / unidades por item (se kit)", "Observação"]
CAB_ENT_SEM_SAI = ["CNPJ da filial", "COD_ITEM", "DESCRIÇÃO NA ENTRADA (como veio na nota de compra)",
                   "EAN (cadastro)", "NCM", "Unidade", "Quantidade entrada", "Valor Total entrada",
                   "Valor Unitário Médio", "Data Mínima", "Data Máxima"]
CAB_UNIDADE = ["CNPJ da filial", "COD_ITEM", "Código na nota (se unificado)", "Descrição (cadastro)",
               "Unidade na nota", "Unidade no XML", "Descrição no XML", "Linhas",
               "Quantidade de entrada (como está)", "Custo unitário de compra", "Preço unitário de venda",
               "Custo ÷ preço", "Já convertido pelo 0220?", "Diagnóstico", "Fator correto (preencher)",
               "Observação"]
CAB_UNIFICADOS = ["CNPJ da filial", "CÓDIGO QUE FICOU (venda)", "Descrição (cadastro)",
                  "CÓDIGO ANTIGO (entrada)", "Descrição do antigo (cadastro)", "EAN do que ficou",
                  "EAN do antigo", "Por que unificou", "Resultado", "Unidade do antigo × do que ficou",
                  "Conferir unidade / quantidade"]
CAB_RESUMO = ["CNPJ da filial", "Itens no relatório", "unificados (código antigo → código de venda)",
              SEM_PAR, MESMO, ESTOQUE, SO_ENTRADA, PARADO,
              "Sem par com entrada do código em outra filial"]


def escrever(itens, unificados, conferir, saida, titulo, filiais, periodo, leia_me):
    wb = xlsxwriter.Workbook(saida, {"constant_memory": True, "default_date_format": "dd/mm/yyyy"})
    f_titulo = wb.add_format({"bold": True, "font_size": 14})
    f_nota = wb.add_format({"italic": True, "font_color": "#555555"})
    cores = {"Filial": "#404040", "DE-PARA": "#7030A0", "Item": "#595959",
             "ENTRADAS (compras)": "#1F3864", "SAÍDAS (vendas)": "#375623", "ENTRADA x SAÍDA": "#833C0C"}
    f_cab = {k: wb.add_format({"bold": True, "bg_color": v, "font_color": "white", "text_wrap": True,
                               "valign": "vcenter", "border": 1}) for k, v in cores.items()}
    f_amarelo = wb.add_format({"bold": True, "bg_color": "#FFD966", "text_wrap": True,
                               "valign": "vcenter", "border": 1})
    f_data = wb.add_format({"num_format": "dd/mm/yyyy"})
    f_moeda = wb.add_format({"num_format": "#,##0.00"})
    f_qtd = wb.add_format({"num_format": "#,##0.000"})

    def cab_simples(ws, nomes, amarelas=()):
        ws.set_row(0, 46)
        for j, nome in enumerate(nomes):
            ws.write(0, j, nome, f_amarelo if j in amarelas else f_cab["Filial"])
            ws.set_column(j, j, 46 if "DESCRI" in nome.upper() else 17)
        ws.freeze_panes(1, 2)

    # ------------------------------------------------------------------ Dados
    ws = wb.add_worksheet("Dados")
    ws.write(0, 0, titulo, f_titulo)
    ws.write(2, 0, "empresa 17 (CAT 42)", f_nota)
    ws.write(4, 0, f"Filiais: {filiais} — a Ficha 3 é por estabelecimento: cada linha é uma filial + COD_ITEM",
             f_nota)
    ws.write(6, 0, f"PERÍODO DA BASE: {periodo}", f_nota)
    ws.write(8, 0, "Gerado em:", f_nota)
    ws.write(8, 1, time.strftime("%d/%m/%Y %H:%M"), f_nota)
    ws.write(8, 2, "Sem itens não-participantes (só quem tem linha de ST)", f_nota)
    faixa_de = {}
    for ini, fim, nome in FAIXAS:
        for j in range(ini, fim):
            faixa_de[j] = nome
    ws.set_row(10, 18)
    ws.set_row(11, 64)
    for j, nome in enumerate(CAB_DADOS):
        faixa = faixa_de[j]
        ws.write(10, j, faixa, f_cab[faixa])
        ws.write(11, j, nome, f_amarelo if nome.endswith("(preencher)") else f_cab[faixa])
        ws.set_column(j, j, 46 if "DESCRI" in nome.upper() else (19 if j > 16 else 23))
    ws.freeze_panes(12, 2)

    linha = 12
    for i in itens:
        if linha >= LIMITE_EXCEL:
            log.warning("aba Dados cortada no limite do Excel em %d linhas", linha)
            break
        antigos = i.get("antigos") or []
        a = antigos[0] if antigos else None
        bcst_med = media(i.get("e_bcst_total"), i.get("e_quantidade"))
        venda_med = media(i.get("s_valor"), i.get("s_quantidade"))
        iva = (n(i.get("e_bcst_total")) / n(i.get("e_valor")) - 1) \
            if n(i.get("e_bcst_total")) and n(i.get("e_valor")) else None
        valores = [
            i["cnpj"], i["codigo"], ", ".join(x["codigo"] for x in antigos),
            descricao_com_outras(i.get("e_descricao"), i.get("e_descricoes"), i.get("cad_descricao"), "compra"),
            descricao_com_outras(i.get("s_descricao"), i.get("s_descricoes"), i.get("cad_descricao"), "venda"),
            descricao_bate(i.get("e_descricao") or "", i.get("s_descricao") or ""),
            ean(i.get("codigo_barras")) or "", i["situacao"], i.get("filiais_que_compram"),
            a["codigo"] if a else "",
            (a.get("e_descricao") or a.get("cad_descricao") or "") if a else "",
            (ean(a.get("codigo_barras")) or "") if a else "",
            "o outro é comprado; este é vendido" if a else "",
            f"{n(a.get('e_quantidade')) or 0:,.0f} → {n(i.get('s_quantidade')) or 0:,.0f}" if a else "",
            "; ".join(i.get("motivos") or []),
            f"{i.get('cad_unidade') or ''} × {a.get('cad_unidade') or ''}" if a else "",
            "", n(i.get("cad_aliq")), None,
            lista(i.get("e_fornecedores")), lista(i.get("e_ncms")) or (i.get("cad_ncm") or ""),
            i.get("cad_cest") or "", lista(i.get("e_cfops")),
            n(i.get("e_quantidade")), n(i.get("e_devolucao")), i.get("cad_unidade") or "",
            lista(i.get("e_csts")), n(i.get("e_valor")),
            n(i.get("e_unit_min")), n(i.get("e_unit_max")), media(i.get("e_valor"), i.get("e_quantidade")),
            i.get("e_data_min"), i.get("e_data_max"),
            n(i.get("e_icms_min")), n(i.get("e_icms_max")), media(i.get("e_icms_total"), i.get("e_quantidade")),
            n(i.get("e_bcst_min")), n(i.get("e_bcst_max")), bcst_med,
            i.get("e_itens_sem_bcst"), i.get("e_nfs_sem_bcst"), i.get("e_nfs"), i.get("e_nfs_sem_st"),
            i.get("conversao_texto") or lista(i.get("e_conversoes"), 4),
            lista(i.get("s_ncms")) or (i.get("cad_ncm") or ""), i.get("cad_cest") or "", lista(i.get("s_cfops")),
            n(i.get("s_quantidade")), n(i.get("s_devolucao")), i.get("cad_unidade") or "", n(i.get("s_valor")),
            n(i.get("s_unit_min")), n(i.get("s_unit_max")), venda_med,
            n(i.get("s_valor_interestadual")), i.get("s_data_min"), i.get("s_data_max"),
            n(i.get("s_icms_min")), n(i.get("s_icms_max")), media(i.get("s_icms_total"), i.get("s_quantidade")),
            n(i.get("e_mva_min")), n(i.get("e_mva_max")), iva, iva,
            (bcst_med / venda_med) if bcst_med and venda_med else None,
        ]
        for j, v in enumerate(valores):
            if v is None or v == "":
                continue
            if hasattr(v, "year"):
                ws.write_datetime(linha, j, v, f_data)
            elif isinstance(v, float):
                # só a quantidade de produto leva 3 casas; "Quantidade de NFs" é contagem
                de_quantidade = CAB_DADOS[j].endswith("Quantidade") or "Quantidade - " in CAB_DADOS[j]
                ws.write_number(linha, j, v, f_qtd if de_quantidade else f_moeda)
            else:
                ws.write(linha, j, v)
        linha += 1
    log.info("aba Dados: %d linhas", linha - 12)

    # --------------------------------------------------------------- Sem par
    ws = wb.add_worksheet("Sem par")
    cab_simples(ws, CAB_SEM_PAR, amarelas={10, 11, 12})
    r = 1
    for i in itens:
        if i["situacao"] != SEM_PAR or r >= LIMITE_EXCEL:
            continue
        ws.write_row(r, 0, [i["cnpj"], i["codigo"],
                            descricao_com_outras(i.get("s_descricao"), i.get("s_descricoes"),
                                                 i.get("cad_descricao"), "venda"),
                            ean(i.get("codigo_barras")) or "", i.get("cad_ncm") or "",
                            i.get("cad_unidade") or ""])
        ws.write_number(r, 6, n(i.get("s_quantidade")) or 0, f_qtd)
        ws.write_number(r, 7, n(i.get("s_valor")) or 0, f_moeda)
        ws.write_number(r, 8, media(i.get("s_valor"), i.get("s_quantidade")) or 0, f_moeda)
        ws.write_number(r, 9, i.get("filiais_que_compram") or 0)
        r += 1
    log.info("aba Sem par: %d linhas", r - 1)

    # ----------------------------------------------------- Entrada sem saída
    ws = wb.add_worksheet("Entrada sem saída")
    cab_simples(ws, CAB_ENT_SEM_SAI)
    r = 1
    for i in itens:
        if i["situacao"] != SO_ENTRADA or r >= LIMITE_EXCEL:
            continue
        ws.write_row(r, 0, [i["cnpj"], i["codigo"],
                            descricao_com_outras(i.get("e_descricao"), i.get("e_descricoes"),
                                                 i.get("cad_descricao"), "compra"),
                            ean(i.get("codigo_barras")) or "", i.get("cad_ncm") or "",
                            i.get("cad_unidade") or ""])
        ws.write_number(r, 6, n(i.get("e_quantidade")) or 0, f_qtd)
        ws.write_number(r, 7, n(i.get("e_valor")) or 0, f_moeda)
        ws.write_number(r, 8, media(i.get("e_valor"), i.get("e_quantidade")) or 0, f_moeda)
        for j, campo in ((9, "e_data_min"), (10, "e_data_max")):
            if i.get(campo) is not None:
                ws.write_datetime(r, j, i[campo], f_data)
        r += 1
    log.info("aba Entrada sem saída: %d linhas", r - 1)

    # ------------------------------------------------------ Conferir unidade
    ws = wb.add_worksheet("Conferir unidade")
    cab_simples(ws, CAB_UNIDADE, amarelas={14})
    for r, c in enumerate(conferir[:LIMITE_EXCEL], start=1):
        ws.write_row(r, 0, [c["cnpj"], c["codigo"], c["codigo_antigo"], c["descricao"],
                            c["unidade_nota"], "", "", c["linhas"]])
        ws.write_number(r, 8, c["quantidade"], f_qtd)
        ws.write_number(r, 9, c["custo"], f_moeda)
        ws.write_number(r, 10, c["preco"], f_moeda)
        ws.write_number(r, 11, c["razao"], f_moeda)
        ws.write(r, 12, c["ja_0220"])
        ws.write(r, 13, c["diagnostico"])
    log.info("aba Conferir unidade: %d linhas", len(conferir))

    # ---------------------------------------------------- Códigos unificados
    ws = wb.add_worksheet("Códigos unificados")
    cab_simples(ws, CAB_UNIFICADOS)
    for r, u in enumerate(unificados[:LIMITE_EXCEL], start=1):
        novo, antigo = u["novo"], u["antigo"]
        iguais = (antigo.get("cad_unidade") or "") == (novo.get("cad_unidade") or "")
        ws.write_row(r, 0, [u["cnpj"], novo["codigo"], novo.get("cad_descricao") or "",
                            antigo["codigo"], antigo.get("cad_descricao") or "",
                            ean(novo.get("codigo_barras")) or "", ean(antigo.get("codigo_barras")) or "",
                            u["motivo"], "unificado",
                            f"{antigo.get('cad_unidade') or ''} × {novo.get('cad_unidade') or ''}",
                            "" if iguais else "unidades diferentes no cadastro"])
    log.info("aba Códigos unificados: %d linhas", len(unificados))

    # ------------------------------------------------------ Resumo por filial
    ws = wb.add_worksheet("Resumo por filial")
    cab_simples(ws, CAB_RESUMO)
    por_filial: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for i in itens:
        c = por_filial[i["cnpj"]]
        c["itens"] += 1
        c[i["situacao"]] += 1
        if i["situacao"] == UNIFICADO:
            c["unificados"] += len(i.get("antigos") or [])
        if i["situacao"] == SEM_PAR and (i.get("filiais_que_compram") or 0) > 0:
            c["outra_filial"] += 1
    totais: dict[str, int] = defaultdict(int)
    log.info("resumo por filial")
    log.info("  %-18s %8s %8s %8s %8s %8s %8s", "CNPJ", "itens", "unific.", "sem par", "mesmo", "estoque", "outra")
    for r, cnpj in enumerate(sorted(por_filial), start=1):
        c = por_filial[cnpj]
        ws.write_row(r, 0, [cnpj, c["itens"], c["unificados"], c[SEM_PAR], c[MESMO], c[ESTOQUE],
                            c[SO_ENTRADA], c[PARADO], c["outra_filial"]])
        for k, v in c.items():
            totais[k] += v
        log.info("  %-18s %8d %8d %8d %8d %8d %8d", cnpj, c["itens"], c["unificados"], c[SEM_PAR],
                 c[MESMO], c[ESTOQUE], c["outra_filial"])
    r = len(por_filial) + 1
    ws.write_row(r, 0, ["TODAS", totais["itens"], totais["unificados"], totais[SEM_PAR], totais[MESMO],
                        totais[ESTOQUE], totais[SO_ENTRADA], totais[PARADO], totais["outra_filial"]])
    log.info("  %-18s %8d %8d %8d %8d %8d %8d", "TODAS", totais["itens"], totais["unificados"],
             totais[SEM_PAR], totais[MESMO], totais[ESTOQUE], totais["outra_filial"])

    # -------------------------------------------------------------- Leia-me
    ws = wb.add_worksheet("Leia-me")
    ws.set_column(0, 0, 155)
    for r, texto in enumerate(leia_me.split("\n")):
        ws.write(r, 0, texto)
    wb.close()
    return dict(totais)
