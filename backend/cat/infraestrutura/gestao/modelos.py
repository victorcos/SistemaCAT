"""Estruturas de dados da gestão fiscal.

``ApuracaoEFD`` é o resumo de UM arquivo EFD-Contribuições, pequeno o
bastante para ir ao cache (poucos MB mesmo com o arquivo tendo 1 GB). Os
quadros são montados só a partir dele — trocar uma regra de quadro não
exige reler o SPED.

Valores monetários ficam em centavos inteiros (ver ``numeros.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Chave de agregação dos documentos:
# (tributo, reg, operacao "E"/"S", cst, cfop, nat_bc_cred, aliquota_bruta)
ChaveDoc = tuple[str, str, str, str, str, str, str]

# Posições do vetor de somas de cada chave
VL_ITEM, VL_BC, VL_TRIB, QUANT, QTD_LINHAS = range(5)


@dataclass
class ApuracaoEFD:
    """Tudo que a gestão precisa de um arquivo EFD-Contribuições."""
    arquivo: str
    file_hash: str
    tamanho: int
    cnpj: str = ""
    razao_social: str = ""
    periodo: str = ""          # "AAAA-MM"
    dt_ini: str = ""           # DDMMAAAA
    dt_fin: str = ""
    cod_ver: str = ""
    tipo_escrit: str = ""      # 0 original, 1 retificadora
    # Registros de apuração guardados como listas de campos, por código.
    registros: dict[str, list[list[str]]] = field(default_factory=dict)
    # (reg, IND_AJ, COD_AJ) -> soma de VL_AJ em centavos (M110/M220/M510/M620)
    ajustes: dict[tuple[str, str, str], int] = field(default_factory=dict)
    # Somas dos itens A/C/D/F: ChaveDoc -> [vl_item, vl_bc, vl_trib, quant, linhas]
    documentos: dict[ChaveDoc, list[int]] = field(default_factory=dict)
    contagens: dict[str, int] = field(default_factory=dict)
    # motivo -> quantidade de linhas ignoradas (nunca descartar em silêncio)
    descartes: dict[str, int] = field(default_factory=dict)
    segundos: float = 0.0
    schema_version: int = 0


@dataclass
class Linha:
    rotulo: str
    # periodo "AAAA-MM" -> centavos. None = o dado não vem do SPED (ex.: DCTF).
    valores: dict[str, int | None] = field(default_factory=dict)
    nivel: int = 0             # recuo visual (IRPJ/CSLL)
    titulo: bool = False       # linha de cabeçalho de subquadro, sem valores
    externo: bool = False      # valor depende de fonte que o sistema não lê


@dataclass
class Quadro:
    numero: str
    titulo: str
    linhas: list[Linha] = field(default_factory=list)


@dataclass
class Relatorio:
    tributo: str               # "PIS", "COFINS", "IRPJ", "CSLL"
    cnpj: str
    razao_social: str
    periodos: list[str]        # colunas, "AAAA-MM", em ordem
    quadros: list[Quadro] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    unidade_percentual: frozenset[str] = frozenset()  # rótulos cujo valor é %, não R$
