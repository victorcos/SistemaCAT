"""Os módulos de trabalho, como o motor precisa conhecê-los.

O catálogo canônico — com descrição, segmento e quem enxerga o quê — vive na
API, em `Cat.Dominio/Acesso/Segmento.cs`. Aqui ficam só a ordem e o nome de
cada um, porque é o motor que escreve as frases que a tela mostra ("serve ao
trabalho de PIS/COFINS", "nenhum arquivo alimenta o trabalho de ICMS").

Se um terceiro lugar precisar desta lista, ela deixa de ser cópia e vira
contrato: sobe para o canal interno, junto do resto.
"""

from __future__ import annotations

# ordem de apresentação: o tributo mais pedido primeiro
MODULOS_EM_ORDEM: tuple[str, ...] = ("piscofins", "icms", "irpj_csll")

ROTULO_DO_MODULO: dict[str, str] = {
    "piscofins": "PIS/COFINS",
    "icms": "ICMS",
    "irpj_csll": "IRPJ/CSLL",
}

# o trabalho de ICMS é o de todo projeto anterior à divisão por tributo
MODULO_PADRAO = "icms"


def rotulo(modulo: str) -> str:
    """Módulo desconhecido aparece pela chave, em vez de sumir da frase."""
    return ROTULO_DO_MODULO.get(modulo, modulo)
