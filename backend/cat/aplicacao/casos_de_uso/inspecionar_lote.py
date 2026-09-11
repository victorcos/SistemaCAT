"""Olhar uma pasta e dizer o que ela tem para o trabalho.

Roda antes de gravar qualquer coisa. Quem vai confirmar o lote precisa ver o
que vai entrar — quantos SPED, de que competências, quantos XML, quanto de
relatório, e principalmente **o que ficou de fora e por quê**.

A separação por empresa é a regra dura daqui. Pasta de rede mistura cliente, e
arquivo de outra empresa entrar num trabalho é o acidente mais caro que este
sistema pode causar: contamina a apuração de dois clientes de uma vez. O
sistema barra sozinho, comparando a raiz do CNPJ de cada arquivo com a do
projeto, e não pede confirmação para isso.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from cat.config import obter_config
from cat.dominio.lote import ArquivoDoLote, ResumoDoLote, TipoDeArquivo
from cat.infraestrutura.arquivos.classificador import (
    LIMITE_DE_ARQUIVOS,
    classificar,
    percorrer_pasta,
)
from cat.log import obter_log

log = obter_log(__name__)


# Quantos arquivos se identificam ao mesmo tempo. Isto é espera de rede, não
# cálculo: subir bem acima do número de núcleos é o certo. O teto existe para
# não afogar o servidor de arquivos, que é compartilhado com o resto da casa.
TAREFAS_SIMULTANEAS = 64


class PastaInvalida(ValueError):
    """O caminho não serve como origem de lote."""


def _conferir_permissao(pasta: str) -> None:
    permitidas = obter_config().lista_pastas_permitidas
    if not permitidas:
        return
    real = os.path.normcase(os.path.abspath(pasta))
    for raiz in permitidas:
        raiz_real = os.path.normcase(os.path.abspath(raiz))
        if real == raiz_real or real.startswith(raiz_real + os.sep):
            return
    raise PastaInvalida(
        "Esta pasta está fora das origens permitidas. "
        f"Permitidas: {'; '.join(permitidas)}"
    )


def inspecionar_pasta(pasta: str, cnpj_raiz: str) -> ResumoDoLote:
    """Classifica tudo que há na pasta, separando o que é de outra empresa."""
    caminho = os.path.expandvars(os.path.expanduser((pasta or "").strip()))
    if not caminho:
        raise PastaInvalida("Informe a pasta onde estão os arquivos.")
    if not os.path.exists(caminho):
        raise PastaInvalida(
            f"'{caminho}' não existe ou não está acessível desta máquina. "
            "Se for unidade de rede, confira se ela está mapeada."
        )
    if not os.path.isdir(caminho):
        raise PastaInvalida(f"'{caminho}' é um arquivo, não uma pasta.")
    _conferir_permissao(caminho)

    resumo = ResumoDoLote(pasta=os.path.abspath(caminho))
    lista = list(percorrer_pasta(caminho))

    # Identificar arquivo em disco de rede é espera, não conta: cada arquivo
    # custa uma ida e volta até o servidor. Em série, 325 arquivos levaram 49 s,
    # e uma pasta de SPED desta casa tem 7.036 — daria quase vinte minutos, com
    # o usuário parado numa tela. Em paralelo o tempo cai para o da rede.
    with ThreadPoolExecutor(max_workers=TAREFAS_SIMULTANEAS) as executor:
        itens = list(executor.map(
            lambda par: classificar(par[0], par[1]), lista))

    for item in sorted(itens, key=lambda a: a.caminho):
        if _e_de_outra_empresa(item, cnpj_raiz):
            resumo.de_outra_empresa.append(item)
            continue
        resumo.arquivos.append(item)
    resumo.limite_atingido = len(lista) >= LIMITE_DE_ARQUIVOS

    log.info(
        "pasta de lote inspecionada",
        extra={
            "pasta": resumo.pasta,
            "arquivos": resumo.total,
            "uteis": len(resumo.uteis),
            "de_outra_empresa": len(resumo.de_outra_empresa),
            "bytes": resumo.bytes_totais,
            "por_tipo": {t.value: q for t, q in resumo.por_tipo.items()},
            "nao_baixados": resumo.por_tipo.get(TipoDeArquivo.NAO_BAIXADO, 0),
        },
    )
    return resumo


def _e_de_outra_empresa(item: ArquivoDoLote, cnpj_raiz: str) -> bool:
    """Só decide quando o arquivo diz de quem é — e por QUALQUER ponta.

    Relatório gerencial não traz CNPJ: quem o produziu foi o ERP da própria
    empresa, e ele não se identifica. Chutar que é de outra empresa deixaria
    de fora justamente a fonte de quem não libera XML.

    No XML, a empresa pode ser o emitente (nota que ela emitiu) OU o
    destinatário (nota que ela recebeu do fornecedor). Comparar só o emitente
    rejeitava toda nota de compra como se fosse de outra empresa — e nota de
    compra, com ST retido, é o insumo principal da CAT 42. O arquivo só é de
    outra empresa quando NENHUMA das pontas conhecidas tem a raiz do projeto.
    """
    if not cnpj_raiz:
        return False
    pontas = [c for c in (item.cnpj, item.cnpj_destinatario) if c]
    if not pontas:
        return False
    return all(c[:8] != cnpj_raiz for c in pontas)
