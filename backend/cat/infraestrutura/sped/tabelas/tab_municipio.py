"""Código de Município (tabela IBGE) -> nome do município.

A tabela de NOMES cobre capitais e municípios grandes/comuns (mesma
filosofia incremental do `tab_cfop.py`: cobre a maioria dos casos reais,
código desconhecido cai em "" sem quebrar nada). Popular a tabela IBGE
completa (~5.570 municípios) fica para uma expansão futura, se necessário
— adicionar códigos aqui não exige nenhuma mudança de código.

`UF_POR_PREFIXO`, por sua vez, é necessária desde já: o registro 0150
(participante) só tem COD_MUN, não UF — a coluna "UF Origem/Destino" da
Consulta de Entradas/Documentos e Itens precisa derivar a UF do
participante a partir dos 2 primeiros dígitos do código IBGE do município
(convenção fixa e pública do IBGE, não uma tabela auxiliar do EFD).
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

TABELA: dict[str, str] = {
    # Capitais (código IBGE de 7 dígitos)
    "1100205": "Porto Velho",
    "1200401": "Rio Branco",
    "1302603": "Manaus",
    "1400100": "Boa Vista",
    "1501402": "Belém",
    "1600303": "Macapá",
    "1721000": "Palmas",
    "2111300": "São Luís",
    "2211001": "Teresina",
    "2304400": "Fortaleza",
    "2408102": "Natal",
    "2507507": "João Pessoa",
    "2611606": "Recife",
    "2704302": "Maceió",
    "2800308": "Aracaju",
    "2927408": "Salvador",
    "3106200": "Belo Horizonte",
    "3205309": "Vitória",
    "3304557": "Rio de Janeiro",
    "3550308": "São Paulo",
    "4106902": "Curitiba",
    "4205407": "Florianópolis",
    "4314902": "Porto Alegre",
    "5002704": "Campo Grande",
    "5103403": "Cuiabá",
    "5208707": "Goiânia",
    "5300108": "Brasília",
    # Municípios grandes/comuns fora das capitais (região metropolitana de SP
    # e demais praças frequentes em documentos fiscais de varejo/atacado)
    "3509502": "Campinas",
    "3547809": "Santo André",
    "3548708": "São Bernardo do Campo",
    "3548906": "São Caetano do Sul",
    "3529401": "Osasco",
    "3534401": "Praia Grande",
    "3548500": "São Vicente",
    "3547304": "Santos",
    "3541000": "Ribeirão Preto",
    "3543402": "Sorocaba",
    "3552205": "Taboão da Serra",
    "3552502": "Taubaté",
    "3518800": "Guarulhos",
    "3505708": "Barueri",
    "3503208": "Aparecida",
    "3549805": "São José dos Campos",
    "3549904": "São José do Rio Preto",
    "3301702": "Duque de Caxias",
    "3303500": "Nova Iguaçu",
    "3304904": "São Gonçalo",
    "4113700": "Londrina",
    "4119905": "Maringá",
    "4209102": "Joinville",
    "4313409": "Novo Hamburgo",
    "5201108": "Aparecida de Goiânia",
}

UF_POR_PREFIXO: dict[str, str] = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}


def descricao(codigo: str) -> str:
    """Retorna o nome do município, ou string vazia se desconhecido/tabela vazia."""
    return TABELA.get((codigo or "").strip(), "")


def uf_do_municipio(cod_mun: str) -> str:
    """Deriva a UF a partir dos 2 primeiros dígitos do código IBGE do município."""
    cod_mun = (cod_mun or "").strip()
    return UF_POR_PREFIXO.get(cod_mun[:2], "") if len(cod_mun) >= 2 else ""
