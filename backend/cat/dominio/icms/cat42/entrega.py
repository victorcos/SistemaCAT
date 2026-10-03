"""A entrega do trabalho — o que se junta de todas as etapas. Puro, sem I/O.

Oitava etapa. Não calcula nada novo: reúne o que as etapas 2 a 7 deixaram
num relatório executivo e num dossiê por estabelecimento. Duas decisões do
Victor (16/09/2026) mandam aqui:

* **o relatório mostra tudo, o dossiê não**: toda competência aparece no
  relatório, pronta ou travada, com o que falta; o dossiê leva só o que vai à
  SEFAZ — prévia nunca entra no pacote do pedido;
* **gerar não é entregar**: o pacote pronto espera um revisor ou gestor
  aprovar (quem aprova é regra da API, que conhece o papel de cada um).

O que mora neste módulo é a leitura dos resumos: cada etapa grava o seu com
nomes próprios, e a lista de pendências precisa falar uma língua só —
gravidade, quantas, de quê e o que fazer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

ETAPAS = (
    ("conferencia", "Conferir documentos"),
    ("movimentos", "Extrair movimentos"),
    ("st_suportado", "Apurar o ICMS suportado"),
    ("razao", "Montar o razão dos itens"),
    ("apuracao", "Apurar ressarcimento e complemento"),
    ("arquivo_digital", "Gerar o arquivo digital"),
    ("entrega", "Relatórios e entrega"),
)
NOME_DA_ETAPA = dict(ETAPAS)
_ORDEM_DA_ETAPA = {chave: i for i, (chave, _) in enumerate(ETAPAS)}


class Gravidade(str, Enum):
    """O peso de uma pendência para quem vai decidir se entrega."""

    TRAVA = "trava"            # a competência não vai à SEFAZ assim
    ATENCAO = "atencao"        # vai, mas o valor pode estar menor ou pede conferência
    INFORMACAO = "informacao"  # contexto: não muda o pedido

    @property
    def rotulo(self) -> str:
        return {"trava": "Trava o envio", "atencao": "Atenção", "informacao": "Informação"}[self.value]


_ORDEM_DA_GRAVIDADE = {Gravidade.TRAVA: 0, Gravidade.ATENCAO: 1, Gravidade.INFORMACAO: 2}


@dataclass(frozen=True)
class Medida:
    """Quanto de um problema uma etapa viu, na unidade dela."""

    quantidade: int
    unidade: str
    etapa: str

    @property
    def nome_da_etapa(self) -> str:
        return NOME_DA_ETAPA.get(self.etapa, self.etapa)


@dataclass(frozen=True)
class Pendencia:
    """Um problema, com a primeira etapa que o viu e as medidas de todas.

    `quantidade` e `unidade` são da primeira medida — a da etapa mais cedo, que
    é onde se resolve. `medidas` traz as outras: o mesmo confronto pendente é
    linha no razão, competência na apuração e arquivo na etapa 7.
    """

    etapa: str
    codigo: str
    rotulo: str
    quantidade: int
    unidade: str
    gravidade: Gravidade
    o_que_fazer: str
    medidas: tuple[Medida, ...] = ()

    @property
    def nome_da_etapa(self) -> str:
        return NOME_DA_ETAPA.get(self.etapa, self.etapa)


# (etapa, caminho no resumo, código, rótulo, unidade, gravidade, o que fazer)
# O caminho é a chave no resumo, com "." para descer um nível. Só entra o que
# a etapa grava hoje; chave que não existe (resumo de versão antiga) é pulada.
_DOS_RESUMOS: tuple[tuple[str, str, str, str, str, Gravidade, str], ...] = (
    ("conferencia", "sem_documento_cobravel", "documentos_a_cobrar",
     "Documentos escriturados sem XML nem relatório do cliente", "documentos", Gravidade.ATENCAO,
     "Cobrar do cliente pela planilha «a cobrar» da etapa 2."),
    ("conferencia", "nao_escrituradas", "nao_escrituradas",
     "Documentos na pasta que a EFD não escriturou", "documentos", Gravidade.ATENCAO,
     "Conferir com o cliente: ficam fora da apuração."),
    ("conferencia", "sem_chave_na_efd", "sem_chave_na_efd",
     "Documentos da EFD sem chave de acesso", "documentos", Gravidade.INFORMACAO,
     "Conferir à mão: não dá para casar por chave."),
    ("movimentos", "itens_sem_cadastro", "itens_sem_cadastro",
     "Itens movimentados sem cadastro (0200)", "itens", Gravidade.ATENCAO,
     "Conferir o cadastro de itens da EFD."),
    ("st_suportado", "por_pendencia.falta_dado", "suportado_falta_dado",
     "Entradas sem dado para apurar o ICMS suportado", "itens", Gravidade.ATENCAO,
     "Pedir o XML ou o relatório de entradas com a ST informada: sem o imposto, o ressarcimento sai menor."),
    ("razao", "pendencias.saidas_sem_aliquota", "saidas_sem_aliquota",
     "Saídas sem alíquota interna no cadastro", "linhas", Gravidade.TRAVA,
     "Completar a alíquota no 0200 da EFD."),
    ("razao", "pendencias.saidas_indefinidas", "saidas_indefinidas",
     "Saídas com enquadramento indefinido", "linhas", Gravidade.TRAVA,
     "Dizer quem comprou, ou escolher o cupom nas demais saídas no trabalho."),
    ("razao", "pendencias.confronto_pendente", "confronto_pendente",
     "Saídas de enquadramento 2 ou 4 sem valor de confronto", "linhas", Gravidade.TRAVA,
     "Apurar o ICMS da operação própria da entrada (coluna 21, art. 271)."),
    ("razao", "pendencias.fichas_negativas", "fichas_retiradas",
     "Fichas retiradas por estoque negativo", "fichas", Gravidade.TRAVA,
     "Falta entrada, abertura ou algum tipo de saída: completar a base e montar o razão de novo."),
    ("razao", "pendencias.fichas_abertura_sem_valor", "abertura_sem_valor",
     "Fichas abertas com quantidade e sem ICMS suportado", "fichas", Gravidade.ATENCAO,
     "Importar as EFD dos meses antes do inventário: o ICMS da abertura vem das entradas mais recentes "
     "(item 3.3.8). Sem elas, o complemento sai inflado."),
    ("razao", "pendencias.fichas_abertura_parcial", "abertura_parcial",
     "Aberturas valoradas só em parte pelas entradas anteriores", "fichas", Gravidade.ATENCAO,
     "As entradas antes do inventário não cobriram a quantidade: importar meses mais antigos."),
    ("razao", "fora_da_ficha.uso_e_consumo", "uso_e_consumo",
     "Lançamentos de uso e consumo fora da ficha", "lançamentos", Gravidade.INFORMACAO,
     "Não são estoque de comercialização: ficam fora da Ficha 3 por decisão do trabalho."),
    ("razao", "fora_da_ficha.x949", "x949",
     "Outras entradas e saídas (X.949) fora da ficha", "lançamentos", Gravidade.INFORMACAO,
     "Remessa e retorno (armazém, depósito) não são compra nem venda: ficam fora da Ficha 3 e contadas."),
    ("razao", "pendencias.linhas_unidade_sem_fator", "unidade_sem_fator",
     "Linhas com unidade diferente da do inventário e sem fator (0220)", "linhas", Gravidade.ATENCAO,
     "Informar o fator de conversão: a quantidade ficou como veio."),
    ("razao", "pendencias.abertura_sem_fator", "abertura_sem_fator",
     "Aberturas com unidade sem fator de conversão", "itens", Gravidade.ATENCAO,
     "Informar o fator de conversão do item no 0220."),
    ("razao", "pendencias.fichas_fora_de_sp", "fichas_fora_de_sp",
     "Fichas de estabelecimento fora de SP", "fichas", Gravidade.INFORMACAO,
     "A CAT 42 é paulista: não entram no pedido."),
    ("arquivo_digital", "entradas_sem_icms", "entradas_sem_icms",
     "Entradas escritas no arquivo com ICMS_TOT zero", "entradas", Gravidade.ATENCAO,
     "Conferir as pendências do ICMS suportado na etapa 4: o ressarcimento fica menor se o imposto existia."),
)


def _valor(resumo: dict, caminho: str) -> int:
    atual: object = resumo
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return 0
        atual = atual[parte]
    try:
        return int(atual or 0)
    except (TypeError, ValueError):
        return 0


# O mesmo problema visto por etapas diferentes, cada uma na sua unidade. Na
# entrega da empresa V (16/09/2026) o confronto pendente aparecia quatro vezes —
# linhas, competências, arquivos e ocorrências da pré-validação — e o revisor
# lia quatro problemas onde havia um. Assunto -> (rótulo, o que fazer).
_ASSUNTOS: dict[str, tuple[str, str]] = {
    "sem_aliquota": ("Saídas sem alíquota interna no cadastro",
                     "Completar a alíquota no 0200 da EFD e montar o razão de novo."),
    "enquadramento_indefinido": ("Saídas com enquadramento indefinido",
                                 "Dizer quem comprou, ou escolher o cupom nas demais saídas no trabalho."),
    "confronto_pendente": ("Saídas de enquadramento 2 ou 4 sem valor de confronto",
                           "Apurar o ICMS da operação própria da entrada (coluna 21, art. 271)."),
    "estoque_negativo": ("Estoque negativo: fichas retiradas do total",
                         "Falta entrada, abertura ou algum tipo de saída: completar a base e montar o razão de novo."),
    "fora_de_sp": ("Estabelecimentos fora de SP", "A CAT 42 é paulista: não entram no pedido."),
    "icms_suportado": ("Entradas sem ICMS suportado apurado",
                       "Pedir o XML ou o relatório de entradas com a ST informada: sem o imposto, o ressarcimento sai menor."),
}

# (etapa, código de origem) -> assunto
_ASSUNTO_DE: dict[tuple[str, str], str] = {
    ("razao", "saidas_sem_aliquota"): "sem_aliquota",
    ("apuracao", "sem_aliquota"): "sem_aliquota",
    ("razao", "saidas_indefinidas"): "enquadramento_indefinido",
    ("apuracao", "enquadramento_indefinido"): "enquadramento_indefinido",
    ("arquivo_digital", "saida_indefinida"): "enquadramento_indefinido",
    ("razao", "confronto_pendente"): "confronto_pendente",
    ("apuracao", "confronto_pendente"): "confronto_pendente",
    ("arquivo_digital", "confronto_pendente"): "confronto_pendente",
    ("arquivo_digital", "pre_validacao_vl_confr"): "confronto_pendente",
    ("razao", "fichas_retiradas"): "estoque_negativo",
    ("apuracao", "ficha_retirada"): "estoque_negativo",
    ("arquivo_digital", "saldo_negativo"): "estoque_negativo",
    ("arquivo_digital", "pre_validacao_item_sem_saldo"): "estoque_negativo",
    ("arquivo_digital", "pre_validacao_saldo_negativo"): "estoque_negativo",
    ("razao", "fichas_fora_de_sp"): "fora_de_sp",
    ("apuracao", "fora_de_sp"): "fora_de_sp",
    ("st_suportado", "suportado_falta_dado"): "icms_suportado",
    ("arquivo_digital", "entradas_sem_icms"): "icms_suportado",
}


def _juntar(soltas: list[Pendencia]) -> list[Pendencia]:
    """Uma pendência por assunto; a gravidade é a mais alta entre as etapas."""
    grupos: dict[str, list[Pendencia]] = {}
    for p in soltas:
        chave = _ASSUNTO_DE.get((p.etapa, p.codigo), f"{p.etapa}:{p.codigo}")
        grupos.setdefault(chave, []).append(p)
    saida = []
    for chave, membros in grupos.items():
        membros.sort(key=lambda p: _ORDEM_DA_ETAPA.get(p.etapa, 99))
        primeira = membros[0]
        # duas regras da mesma etapa na mesma unidade (item sem 1050 e estoque
        # negativo, ambas "ocorrências") somam: é o mesmo problema contado duas vezes
        somadas: dict[tuple[str, str], int] = {}
        for p in membros:
            somadas[(p.etapa, p.unidade)] = somadas.get((p.etapa, p.unidade), 0) + p.quantidade
        medidas = tuple(Medida(n, unidade, etapa) for (etapa, unidade), n in somadas.items())
        gravidade = min((p.gravidade for p in membros), key=_ORDEM_DA_GRAVIDADE.__getitem__)
        if chave in _ASSUNTOS:
            rotulo, o_que_fazer = _ASSUNTOS[chave]
            codigo = chave
        else:
            rotulo, o_que_fazer, codigo = primeira.rotulo, primeira.o_que_fazer, primeira.codigo
        saida.append(Pendencia(primeira.etapa, codigo, rotulo, primeira.quantidade, primeira.unidade,
                               gravidade, o_que_fazer, medidas))
    return saida


def pendencias(resumos: dict[str, dict]) -> list[Pendencia]:
    """As pendências de todas as etapas, das que travam para as que informam.

    `resumos` é etapa -> resumo da execução que a entrega usou. Etapa ausente
    não gera pendência: não é papel da entrega inventar o que não foi medido.
    O mesmo problema visto por várias etapas vira uma pendência só, com a
    medida de cada uma.
    """
    saida: list[Pendencia] = []
    for etapa, caminho, codigo, rotulo, unidade, gravidade, o_que_fazer in _DOS_RESUMOS:
        n = _valor(resumos.get(etapa) or {}, caminho)
        if n > 0:
            saida.append(Pendencia(etapa, codigo, rotulo, n, unidade, gravidade, o_que_fazer))

    # as listas que as etapas 6 e 7 já gravam com rótulo e o que fazer
    for m in (resumos.get("apuracao") or {}).get("por_motivo") or []:
        if m.get("competencias"):
            gravidade = Gravidade.INFORMACAO if m.get("codigo") == "fora_de_sp" else Gravidade.TRAVA
            saida.append(Pendencia("apuracao", m["codigo"], m["rotulo"], int(m["competencias"]), "competências",
                                   gravidade, m.get("o_que_fazer", "")))
    arquivo = resumos.get("arquivo_digital") or {}
    for t in arquivo.get("por_trava") or []:
        # "não apta" repete, arquivo a arquivo, os motivos da etapa 6 já listados
        if t.get("arquivos") and t.get("codigo") != "nao_apta":
            saida.append(Pendencia("arquivo_digital", t["codigo"], t["rotulo"], int(t["arquivos"]), "arquivos",
                                   Gravidade.TRAVA, t.get("o_que_fazer", "")))
    for r in arquivo.get("por_regra") or []:
        if r.get("ocorrencias"):
            gravidade = Gravidade.TRAVA if r.get("severidade") == "erro" else Gravidade.ATENCAO
            saida.append(Pendencia("arquivo_digital", f"pre_validacao_{r['codigo']}",
                                   f"Pré-validação: {r['rotulo']}", int(r["ocorrencias"]), "ocorrências",
                                   gravidade, r.get("o_que_fazer", "")))

    return sorted(_juntar(saida), key=lambda p: (_ORDEM_DA_GRAVIDADE[p.gravidade], _ORDEM_DA_ETAPA.get(p.etapa, 99)))


class SituacaoDaCompetencia(str, Enum):
    """Onde a competência ficou na entrega."""

    ENVIO = "envio"              # vai no dossiê
    PREVIA = "previa"            # SP, com o que resolver: só no relatório
    FORA_DE_SP = "fora_de_sp"    # não gera arquivo
    SEM_ARQUIVO = "sem_arquivo"  # SP sem arquivo gerado: a etapa 7 é de antes da apuração

    @property
    def rotulo(self) -> str:
        return {
            "envio": "Pronta para envio",
            "previa": "Prévia (com pendência)",
            "fora_de_sp": "Fora de SP",
            "sem_arquivo": "Sem arquivo gerado",
        }[self.value]

    @classmethod
    def de(cls, uf: str | None, destino: str | None) -> "SituacaoDaCompetencia":
        if (uf or "").upper() not in ("", "SP"):
            return cls.FORA_DE_SP
        if destino == "envio":
            return cls.ENVIO
        if destino == "previa":
            return cls.PREVIA
        return cls.SEM_ARQUIVO
