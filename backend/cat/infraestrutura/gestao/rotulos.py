"""Rótulos dos relatórios de gestão, no texto abreviado que o MA usa.

O MA não usa a descrição oficial longa das tabelas do Guia Prático: ele
abrevia ("Crédito - Rec Trib no MI", "Máquinas, equip. bens do ativo -
Depreciação"). Para o relatório bater linha a linha com o do MA, os
rótulos precisam ser os dele.

Itens marcados ``# CONFIRMADO`` foram copiados do export real da Gestão
do MA (PIS.csv/COFINS.csv/IRPJ.xlsx/CSLL.xlsx, 59 competências). Os
demais seguem o mesmo padrão de abreviação sobre o texto oficial e ainda
não apareceram num export real; se divergirem, prevalece o do MA.
"""
from __future__ import annotations

# Tabela 4.3.5 — Código de Contribuição Social Apurada (M210/M610 COD_CONT)
COD_CONT: dict[str, str] = {
    "01": "Não Cumulativa - Alíquota Básica",  # CONFIRMADO
    "02": "Não Cumulativa - Alíquotas Diferenciadas",  # CONFIRMADO
    "03": "Não Cumulativa - Alíquota por Unidade de Produto",
    "04": "Não Cumulativa - Alíquota Básica - Atividade Imobiliária",
    "31": "Substituição Tributária",  # CONFIRMADO
    "32": "Substituição Tributária - Vendas à Zona Franca de Manaus",
    "51": "Cumulativa - Alíquota Básica",
    "52": "Cumulativa - Alíquotas Diferenciadas",
    "53": "Cumulativa - Alíquota por Unidade de Produto",
    "54": "Cumulativa - Alíquota Básica - Atividade Imobiliária",
    "70": "Atividade Imobiliária - RET",
    "71": "SCP - Não Cumulativa",
    "72": "SCP - Cumulativa",
    "99": "Folha de Salários",
}

# Tabela 4.3.6 — Código de Tipo de Crédito (M100/M500/1100/1500 COD_CRED).
# O código tem 3 dígitos: o 1º diz a receita a que o crédito se vincula e
# os dois últimos, o tipo.
_COD_CRED_GRUPO: dict[str, str] = {
    "1": "Tributada MI",  # CONFIRMADO
    "2": "Não Tributada MI",
    "3": "Exportação",
}
_COD_CRED_TIPO: dict[str, str] = {
    "01": "Alíquota Básica",  # CONFIRMADO
    "02": "Alíquotas Diferenciadas",  # CONFIRMADO
    "03": "Alíquota por Unidade de Produto",
    "04": "Estoque de Abertura",
    "05": "Aquisição Embalagens para Revenda",
    "06": "Presumido da Agroindústria",
    "07": "Outros Créditos Presumidos",
    "08": "Importação",  # CONFIRMADO
    "09": "Atividade Imobiliária",
    "99": "Outros",
}

# Tabela 4.3.8 — Código de Ajuste de Contribuição ou Créditos (M110/M220/M510/M620 COD_AJ)
COD_AJ: dict[str, str] = {
    "01": "Ajuste Oriundo de Ação Judicial",  # CONFIRMADO
    "02": "Ajuste Oriundo de Processo Administrativo",
    "03": "Ajuste Oriundo da Legislação Tributária",  # CONFIRMADO
    "04": "Ajuste Oriundo Especificamente do RTT",
    "05": "Ajuste Oriundo de Outras Situações",  # CONFIRMADO
    "06": "Estorno",  # CONFIRMADO
    "07": "Ajuste da CPRB: Adoção do Regime de Caixa",
    "08": "Ajuste da CPRB: Diferimento de Valores a Recolher no Período",
    "09": "Ajuste da CPRB: Adição de Valores Diferidos em Período(s) Anterior(es)",
    "11": (  # CONFIRMADO
        "Ajuste referente à redução linear dos incentivos e benefícios de natureza "
        "tributária, financeira ou creditícia - alíquota zero (LCP nº 224/2025 e "
        "art. 8º da IN RFB nº 2.305/2025)"
    ),
}

# Tabela 4.3.7 — Natureza da Base de Cálculo do Crédito, abreviada como no MA
# (a versão longa, oficial, está em src/sped/tabelas/tab_437.py).
NAT_BC_CRED: dict[str, str] = {
    "01": "Aquisição de bens para revenda",  # CONFIRMADO
    "02": "Aquisição de bens utilizados como insumo",  # CONFIRMADO
    "03": "Aquisição de serviços utilizados como insumo",  # CONFIRMADO
    "04": "Energia elétrica e térmica",  # CONFIRMADO
    "05": "Aluguéis de prédios",  # CONFIRMADO
    "06": "Aluguéis de máquinas e equipamentos",  # CONFIRMADO
    "07": "Armazenagem e frete na operação de venda",  # CONFIRMADO
    "08": "Contraprestações de arrendamento mercantil",  # CONFIRMADO
    "09": "Máquinas, equip. bens do ativo - Depreciação",  # CONFIRMADO
    "10": "Máquinas, equip. bens do ativo - Aquisição",  # CONFIRMADO
    "11": "Amortização e deprec. de edificações em imóveis",  # CONFIRMADO
    "12": "Devolução de vendas - Incidência Não-Cumulativa",  # CONFIRMADO
    "13": "Outras Operações com direito a crédito",  # CONFIRMADO
    "14": "Atividade de transp. de cargas – Subcontratação",  # CONFIRMADO
    "15": "Atividade Imobiliária – Custo Incorrido",
    "16": "Atividade Imobiliária – Custo Orçado",
    "17": "Atividade de prest. serv. de limpeza, cons. e manutenção",  # CONFIRMADO
    "18": "Estoque de abertura de bens",  # CONFIRMADO
}

# Tabela 4.3.3 — CST PIS/COFINS, abreviado como no MA
CST: dict[str, str] = {
    "01": "Alíquota Básica",  # CONFIRMADO
    "02": "Alíquota Diferenciada",  # CONFIRMADO
    "03": "Alíquota por Unidade de Medida",
    "04": "Monofásica - Revenda a Alíquota Zero",  # CONFIRMADO
    "05": "Substituição Tributária",  # CONFIRMADO
    "06": "Alíquota zero",  # CONFIRMADO
    "07": "Isenta da Contribuição",  # CONFIRMADO
    "08": "Sem Incidência da Contribuição",
    "09": "Suspensão da Contribuição",  # CONFIRMADO
    "49": "Outras Operações de Saída",
    "50": "Crédito - Rec Trib no MI",  # CONFIRMADO
    "51": "Crédito - Rec Não Trib no MI",
    "52": "Crédito - Rec de Exportação",
    "53": "Crédito - Rec Trib e Não Trib no MI",
    "54": "Crédito - Rec Trib no MI e Exportação",
    "55": "Crédito - Rec Não Trib no MI e Exportação",
    "56": "Crédito - Rec Trib e Não Trib no MI e Exportação",
    "60": "Créd Presumido - Rec Trib no MI",
    "61": "Créd Presumido - Rec Não Trib no MI",
    "62": "Créd Presumido - Rec de Exportação",
    "63": "Créd Presumido - Rec Trib e Não Trib no MI",
    "64": "Créd Presumido - Rec Trib no MI e Exportação",
    "65": "Créd Presumido - Rec Não Trib no MI e Exportação",
    "66": "Créd Presumido - Rec Trib e Não Trib no MI e Exportação",
    "67": "Créd Presumido - Outras Operações",
    "70": "Aquisição sem Direito a Crédito",
    "71": "Aquisição com Isenção",
    "72": "Aquisição com Suspensão",
    "73": "Aquisição a Alíquota Zero",  # CONFIRMADO
    "74": "Aquisição sem Incidência da Contribuição",
    "75": "Aquisição por Substituição Tributária",
    "98": "Outras Operações de Entrada",
    "99": "Outras Operações",
}

# Código de receita do DARF (M205/M605 COD_REC — os 4 primeiros dígitos;
# os 2 últimos são a variação).
COD_RECEITA: dict[str, str] = {
    "6912": "PIS - NÃO CUMULATIVO (LEI 10.637/02)",  # CONFIRMADO
    "5856": "COFINS NÃO-CUMULATIVA",  # CONFIRMADO
    "8109": "PIS - FATURAMENTO - PJ EM GERAL",
    "2172": "COFINS - FATURAMENTO - PJ EM GERAL",
    "8301": "PIS - FOLHA DE SALÁRIOS",
}

# e-Lalur/e-Lacs (M300/M350 IND_RELACAO)
IND_RELACAO: dict[str, str] = {
    "1": "Com Conta da Parte B",
    "2": "Com Conta Contábil",  # CONFIRMADO
    "3": "Com Conta da parte B e Conta Contábil",  # CONFIRMADO
    "4": "Sem Relacionamento",  # CONFIRMADO
}

# O MA corta a descrição dos códigos da ECF em 66 caracteres
# ("... patrimônio líquido - perda rec"). CONFIRMADO em 9 linhas do export.
LIMITE_DESCRICAO_ECF = 66


def rotulo_cod_cont(cod: str) -> str:
    return COD_CONT.get(cod, f"Código {cod}")


def rotulo_cod_cred(cod: str) -> str:
    """``"101"`` -> ``"101 - Tributada MI: Alíquota Básica"``."""
    grupo = _COD_CRED_GRUPO.get(cod[:1])
    tipo = _COD_CRED_TIPO.get(cod[1:3])
    if grupo and tipo:
        return f"{cod} - {grupo}: {tipo}"
    return cod


def rotulo_cod_aj(cod: str) -> str:
    return COD_AJ.get(cod, "")


def rotulo_nat(cod: str) -> str:
    desc = NAT_BC_CRED.get(cod)
    return f"{cod} - {desc}" if desc else cod


def rotulo_cst(cod: str) -> str:
    desc = CST.get(cod)
    return f"{cod} - {desc}" if desc else cod


def rotulo_cod_receita(cod_rec: str) -> str:
    base = (cod_rec or "")[:4]
    desc = COD_RECEITA.get(base)
    return f"{base} - {desc}" if desc else base


def cortar_descricao_ecf(desc: str) -> str:
    return (desc or "")[:LIMITE_DESCRICAO_ECF]
