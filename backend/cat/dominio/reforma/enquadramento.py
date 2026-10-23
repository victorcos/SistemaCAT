"""O enquadramento do item: NCM, capítulo, categoria do Imposto Seletivo e
família — as chaves por onde a simulação se abre.

## A NCM que vale é a revisada

O cadastro do cliente traz a NCM do ERP e a NCM revisada pela consultoria. A
revisada é a que manda em tudo — capítulo, subcapítulo e Imposto Seletivo —,
porque a do ERP erra: na primeira base havia NCM com nove dígitos e posição
trocada. A do ERP fica só como informação.

## Seletivo: o cadastro decide antes da regra

A regra por NCM é o padrão. Só que ela não separa o que a NCM junta: o
refrigerante zero divide o 2202.10.00 com o açucarado. Na primeira simulação a
tentativa de separá-los pela descrição falhou calada (a expressão regular foi
gravada com o escape quebrado) e quatro itens "sem açúcar" saíram do IS por
efeito colateral. Por isso a marcação explícita no cadastro, por SKU, vence a
regra — inclusive para dizer "este não paga" — e descrição nenhuma decide nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from cat.dominio.reforma.parametros import Cenario, CategoriaDoSeletivo

# o que o cadastro escreve para dizer "este SKU não paga IS", mesmo com NCM sujeita
SEM_SELETIVO = "nenhuma"


def normalizar_ncm(valor: object) -> str:
    """Oito dígitos, com o zero à esquerda que a planilha come.

    `3032300` vira `03032300`. Mais de oito dígitos não é NCM: volta como veio,
    para aparecer na pendência em vez de ser cortado num código que existe.
    """
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    digitos = "".join(c for c in texto if c.isdigit())
    if not digitos:
        return ""
    return digitos.zfill(8) if len(digitos) < 8 else digitos


def capitulo(ncm: str) -> str:
    """Os dois primeiros dígitos. Sem NCM, `--`, que agrupa e não some."""
    return ncm[:2] if len(ncm) >= 2 else "--"


def subcapitulo(ncm: str) -> str:
    """A posição (quatro dígitos): o nível que o cliente pediu para abrir os
    capítulos grandes, como o 22 (bebidas) e o 04 (laticínios)."""
    return ncm[:4] if len(ncm) >= 4 else "----"


def familia(descricao: str | None) -> str:
    """A primeira palavra da descrição: "CERV", "REFR", "BISC". Rústico, mas é
    como o varejo abrevia o tipo do produto no cadastro, e serve até o cliente
    mandar a classificação mercadológica dele."""
    palavras = (descricao or "").strip().upper().split()
    return palavras[0] if palavras else "(sem descrição)"


def categoria_pela_ncm(ncm: str, cenario: Cenario) -> CategoriaDoSeletivo | None:
    """A categoria do IS pela regra de NCM do cenário. O prefixo mais longo
    vence, para uma regra de código específico não perder para a de capítulo."""
    melhor: CategoriaDoSeletivo | None = None
    tamanho = 0
    for categoria in cenario.categorias_do_seletivo:
        for prefixo in categoria.prefixos:
            if ncm.startswith(prefixo) and len(prefixo) > tamanho:
                melhor, tamanho = categoria, len(prefixo)
    return melhor


@dataclass(frozen=True)
class CategoriaAtribuida:
    """A categoria do IS de um SKU e de onde ela veio — "cadastro" ou "ncm".
    `chave` vazia é "não paga IS"."""

    chave: str
    origem: str


def categoria_do_seletivo(ncm: str, marcada_no_cadastro: str | None,
                          cenario: Cenario) -> CategoriaAtribuida:
    """O cadastro vence a regra. A marcação precisa ser uma categoria do
    cenário ou `nenhuma`; qualquer outra coisa é erro de digitação, e recusar
    é melhor que tratar como "não paga"."""
    marcada = (marcada_no_cadastro or "").strip().lower()
    if marcada:
        if marcada == SEM_SELETIVO:
            return CategoriaAtribuida("", "cadastro")
        chaves = {c.chave for c in cenario.categorias_do_seletivo}
        if marcada not in chaves:
            raise ValueError(
                f"Categoria do Imposto Seletivo desconhecida no cadastro: {marcada!r}. "
                f"Vale uma de: {', '.join(sorted(chaves))}, ou {SEM_SELETIVO!r}.")
        return CategoriaAtribuida(marcada, "cadastro")
    pela_ncm = categoria_pela_ncm(ncm, cenario)
    return CategoriaAtribuida(pela_ncm.chave if pela_ncm else "", "ncm")
