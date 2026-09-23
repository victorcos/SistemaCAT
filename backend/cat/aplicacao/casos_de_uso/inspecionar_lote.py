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
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.config import obter_config
from cat.dominio.comum.modulos import MODULO_PADRAO
from cat.dominio.lote import (
    ArquivoDoLote,
    CertificadosIgnorados,
    ResumoDoLote,
    TipoDeArquivo,
    e_pasta_de_certificado,
)
from cat.infraestrutura.arquivos.classificador import (
    LIMITE_DE_ARQUIVOS,
    classificar,
    hash_de,
    percorrer_pasta,
)
from cat.infraestrutura.repositorios.modelos import ArquivoDoLoteDB, LoteDB, ProjetoDB
from cat.log import obter_log

log = obter_log(__name__)


# Quantos arquivos se identificam ao mesmo tempo. Isto é espera de rede, não
# cálculo: subir bem acima do número de núcleos é o certo. O teto existe para
# não afogar o servidor de arquivos, que é compartilhado com o resto da casa.
TAREFAS_SIMULTANEAS = 64


@dataclass(frozen=True)
class ArquivoExistente:
    """O que já está no trabalho, com o suficiente para detectar cópia.

    `hash_conteudo` pode vir vazio: arquivos importados antes desta regra não
    foram hashados. Nesse caso, o arquivo antigo é lido na hora — ele está em
    disco, o caminho é conhecido — e o hash gravado na próxima importação.
    """

    caminho: str
    tamanho: int
    tipo: str
    cnpj: str | None
    competencia: object
    retificadora: bool
    hash_conteudo: str | None = None

    @property
    def assinatura(self) -> tuple:
        return (self.tamanho, self.tipo, self.cnpj, self.competencia, self.retificadora)


def _assinatura(a: ArquivoDoLote) -> tuple:
    return (a.tamanho, a.tipo.value, a.cnpj, a.competencia, a.retificadora)


def _separar_copias(
    itens: list[ArquivoDoLote], existentes: tuple[ArquivoExistente, ...]
) -> tuple[list[ArquivoDoLote], list[tuple[ArquivoDoLote, str]]]:
    """Tira as cópias exatas, hashando só quem tem com quem se parecer.

    Candidato é quem coincide em tamanho, tipo, CNPJ, competência e finalidade
    com outro arquivo da pasta ou com um já importado. Conteúdo diferente com a
    mesma assinatura existe (dois relatórios do mesmo tamanho), então a
    assinatura só escolhe quem hashar; quem decide é o hash.
    """
    por_assinatura: dict[tuple, list[ArquivoDoLote]] = {}
    for a in itens:
        if a.tamanho > 0:
            por_assinatura.setdefault(_assinatura(a), []).append(a)
    antigos: dict[tuple, list[ArquivoExistente]] = {}
    for e in existentes:
        antigos.setdefault(e.assinatura, []).append(e)

    candidatos = [
        a for a in itens
        if a.tamanho > 0
        and (len(por_assinatura.get(_assinatura(a), [])) > 1
             or _assinatura(a) in antigos)
    ]
    if not candidatos:
        return itens, []

    # os antigos sem hash precisam ser lidos também; só os que importam agora
    a_ler_antigos = [
        e for assinatura in {_assinatura(a) for a in candidatos}
        for e in antigos.get(assinatura, []) if not e.hash_conteudo
    ]
    with ThreadPoolExecutor(max_workers=TAREFAS_SIMULTANEAS) as executor:
        hashes = dict(zip(
            [a.caminho for a in candidatos] + [e.caminho for e in a_ler_antigos],
            executor.map(_hash_tolerante,
                         [a.caminho for a in candidatos]
                         + [e.caminho for e in a_ler_antigos]),
        ))

    hash_antigo: dict[str, str] = {}
    for e in existentes:
        h = e.hash_conteudo or hashes.get(e.caminho)
        if h:
            hash_antigo.setdefault(h, e.caminho)

    # Entre cópias idênticas, sobrevive a de pasta mais rasa — a cópia costuma
    # estar em `backup/`, `old/`, `2021 (2)/`. Entre iguais na profundidade,
    # a ordem alfabética. Não muda o resultado (são o mesmo byte a byte); muda
    # o que a pessoa vê como "o original", e isso importa para confiar.
    sobrevivente: dict[str, str] = {}
    for a in sorted(itens, key=lambda x: (x.caminho.count(os.sep), x.caminho)):
        h = hashes.get(a.caminho)
        if h is not None and h not in hash_antigo:
            sobrevivente.setdefault(h, a.caminho)

    entram: list[ArquivoDoLote] = []
    copias: list[tuple[ArquivoDoLote, str]] = []
    for a in itens:
        h = hashes.get(a.caminho)
        if h is None:
            entram.append(a)
        elif h in hash_antigo:
            copias.append((replace(a, hash_conteudo=h),
                           "já no trabalho: " + hash_antigo[h]))
        elif sobrevivente[h] == a.caminho:
            entram.append(replace(a, hash_conteudo=h))
        else:
            copias.append((replace(a, hash_conteudo=h), sobrevivente[h]))
    return entram, copias


def _hash_tolerante(caminho: str) -> str | None:
    try:
        return hash_de(caminho)
    except OSError as erro:
        log.warning("não deu para ler o arquivo para conferir cópia",
                    extra={"arquivo": os.path.basename(caminho), "motivo": str(erro)})
        return None


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


def inspecionar_pasta(
    pasta: str, cnpj_raiz: str,
    existentes: tuple[ArquivoExistente, ...] = (),
    ja_lidos: JaLidos | None = None,
    modulo: str = MODULO_PADRAO,
) -> ResumoDoLote:
    """Classifica tudo que há na pasta, separando o que é de outra empresa
    e o que é cópia exata — de outro arquivo da pasta ou de um já importado.

    `ja_lidos` diz o que outro trabalho da mesma empresa já leu. Quem está nele
    **entra** no lote, marcado: não é cópia a recusar, é leitura a não repetir.

    `modulo` é o do trabalho que vai receber a pasta, e decide quais arquivos
    contam como úteis: a EFD-Contribuições não serve à CAT 42 e é o arquivo do
    trabalho de PIS/COFINS.
    """
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
    if any(e_pasta_de_certificado(parte) for parte in os.path.abspath(caminho).replace("\\", "/").split("/")):
        raise PastaInvalida(
            "Esta pasta é de certificado digital, ou está dentro de uma: o sistema não a abre. "
            "Escolha a pasta com os arquivos fiscais."
        )
    _conferir_permissao(caminho)

    resumo = ResumoDoLote(pasta=os.path.abspath(caminho), modulo=modulo)
    ja_lidos = ja_lidos or JaLidos()
    certificados = CertificadosIgnorados()
    lista = list(percorrer_pasta(caminho, certificados))
    resumo.certificados = certificados

    # Identificar arquivo em disco de rede é espera, não conta: cada arquivo
    # custa uma ida e volta até o servidor. Em série, 325 arquivos levaram 49 s,
    # e uma pasta de SPED desta casa tem 7.036 — daria quase vinte minutos, com
    # o usuário parado numa tela. Em paralelo o tempo cai para o da rede.
    with ThreadPoolExecutor(max_workers=TAREFAS_SIMULTANEAS) as executor:
        itens = list(executor.map(
            lambda par: classificar(par[0], par[1]), lista))

    da_empresa: list[ArquivoDoLote] = []
    for item in sorted(itens, key=lambda a: a.caminho):
        if _e_de_outra_empresa(item, cnpj_raiz):
            resumo.de_outra_empresa.append(item)
            continue
        da_empresa.append(item)
    # Caminho que já está no trabalho é "já importado" — o roteador conta e
    # recusa isso por conta própria. Não passa pelo hash: seria comparar o
    # arquivo consigo mesmo e chamá-lo de cópia. Só caminho NOVO com conteúdo
    # igual ao de algo já importado é cópia.
    caminhos_antigos = {e.caminho for e in existentes}
    ja_importados = [a for a in da_empresa if a.caminho in caminhos_antigos]
    novos = [a for a in da_empresa if a.caminho not in caminhos_antigos]
    entram, resumo.copias = _separar_copias(novos, existentes)
    # o que outro trabalho desta empresa já leu entra marcado: a etapa seguinte
    # reaproveita o derivado em vez de indexar de novo
    marcados = [replace(a, ja_lido_em=ja_lidos.trabalho_de(a)) if ja_lidos.trabalho_de(a) else a
                for a in entram + ja_importados]
    resumo.arquivos = sorted(marcados, key=lambda a: a.caminho)
    resumo.limite_atingido = len(lista) >= LIMITE_DE_ARQUIVOS

    log.info(
        "pasta de lote inspecionada",
        extra={
            "pasta": resumo.pasta,
            "arquivos": resumo.total,
            "uteis": len(resumo.uteis),
            "de_outra_empresa": len(resumo.de_outra_empresa),
            "copias": len(resumo.copias),
            "reaproveitados": len(resumo.reaproveitados),
            "bytes": resumo.bytes_totais,
            "por_tipo": {t.value: q for t, q in resumo.por_tipo.items()},
            "nao_baixados": resumo.por_tipo.get(TipoDeArquivo.NAO_BAIXADO, 0),
            "certificados_pastas": certificados.pastas,
            "certificados_arquivos": certificados.arquivos,
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


class ProjetoInexistente(LookupError):
    """O trabalho pedido não existe."""


def existentes_do_projeto(projeto_id: int, sessao: Session) -> tuple[ArquivoExistente, ...]:
    """O que já está no trabalho, para a importação nova detectar cópia."""
    linhas = sessao.execute(
        select(ArquivoDoLoteDB.caminho, ArquivoDoLoteDB.tamanho,
               ArquivoDoLoteDB.tipo, ArquivoDoLoteDB.cnpj,
               ArquivoDoLoteDB.competencia, ArquivoDoLoteDB.retificadora,
               ArquivoDoLoteDB.hash_conteudo)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id)
    ).all()
    return tuple(ArquivoExistente(*linha) for linha in linhas)


@dataclass(frozen=True)
class JaLidos:
    """O que OUTROS trabalhos da mesma empresa já leram.

    Não serve para recusar nada: serve para o trabalho novo saber que a leitura
    daquele arquivo já foi feita e o material derivado está em disco. A exclusão
    do ICMS da base do PIS/COFINS precisa da EFD ICMS/IPI que o trabalho de ICMS
    importou, e reindexá-la seria pagar duas vezes pelo mesmo byte.

    **Casa por caminho e por assinatura, nunca por hash.** O hash só é calculado
    para candidato a cópia — exigi-lo aqui obrigaria a ler 119 GB para descobrir
    que não era preciso ler nada. O caminho resolve o caso real (a mesma pasta do
    cliente no servidor de arquivos); a assinatura — tamanho, tipo, CNPJ,
    competência e finalidade — cobre a mesma base copiada para outro lugar.
    """

    por_caminho: dict[str, str] = field(default_factory=dict)
    por_assinatura: dict[tuple, str] = field(default_factory=dict)

    def trabalho_de(self, arquivo: ArquivoDoLote) -> str:
        """O nome do trabalho que já leu este arquivo, ou vazio."""
        return (self.por_caminho.get(arquivo.caminho)
                or self.por_assinatura.get(_assinatura(arquivo), ""))

    def __bool__(self) -> bool:
        return bool(self.por_caminho or self.por_assinatura)


def ja_lidos_na_empresa(empresa_id: int, exceto_projeto_id: int, sessao: Session) -> JaLidos:
    """Monta o mapa do que a empresa já leu fora deste trabalho."""
    linhas = sessao.execute(
        select(ArquivoDoLoteDB.caminho, ArquivoDoLoteDB.tamanho, ArquivoDoLoteDB.tipo,
               ArquivoDoLoteDB.cnpj, ArquivoDoLoteDB.competencia,
               ArquivoDoLoteDB.retificadora, ProjetoDB.nome)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .join(ProjetoDB, ProjetoDB.id == LoteDB.projeto_id)
        .where(ProjetoDB.empresa_id == empresa_id, ProjetoDB.id != exceto_projeto_id)
    ).all()
    achados = JaLidos()
    for caminho, tamanho, tipo, cnpj, competencia, retificadora, nome in linhas:
        # o primeiro que leu é o que se cita: é nele que o derivado está
        achados.por_caminho.setdefault(caminho, nome)
        if tamanho:
            achados.por_assinatura.setdefault(
                (tamanho, tipo, cnpj, competencia, retificadora), nome)
    return achados


def inspecionar_do_projeto(
    projeto_id: int, pasta: str, sessao: Session
) -> tuple[ResumoDoLote, dict[str, str]]:
    """Inspeciona a pasta para um trabalho que existe.

    Devolve o resumo e os caminhos que já estão no trabalho, cada um com o tipo
    gravado — quando a classificação de hoje diz outro tipo (o zip que virou
    `xml_compactado` na v0.54), a API atualiza o arquivo. É a entrada que o
    canal interno usa: a API em C# manda só o trabalho e a pasta, e o motor
    busca aqui a raiz do CNPJ e o que já foi importado — inclusive os hashes,
    que decidem o que é cópia.
    """
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        raise ProjetoInexistente(projeto_id)
    existentes = existentes_do_projeto(projeto_id, sessao)
    ja_lidos = ja_lidos_na_empresa(projeto.empresa_id, projeto_id, sessao)
    resumo = inspecionar_pasta(pasta, projeto.empresa.cnpj_raiz, existentes=existentes,
                               ja_lidos=ja_lidos, modulo=projeto.modulo or MODULO_PADRAO)
    return resumo, {e.caminho: e.tipo for e in existentes}
