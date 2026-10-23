"""Etapa: a simulação da reforma tributária do consumo (IBS, CBS e IS).

Lê do lote as saídas já custeadas e a classificação dos itens, projeta cada
linha de 2025 a 2033 e entrega a DRE, a trajetória e as visões por grupo, UF,
mês, capítulo, posição, família, categoria do IS e SKU — na tela, pelo resumo,
e na planilha, montada aqui mesmo.

A regra não está aqui: o cálculo é `dominio/reforma/`, a leitura e a soma são
`analitico/reforma.py`, a planilha é `planilhas/reforma.py`. Esta etapa é a
casca: prepara a execução, chama a rodada, escreve o diário que a tela lê e
registra o que aconteceu no histórico do trabalho.

**Não depende de etapa nenhuma** e serve aos dois módulos da reforma, CBS e
IBS: é a mesma conta, que põe os cinco tributos lado a lado.

## Os avisos que mudam o que o analista faz

* **Pendência de cadastro** — item vendido sem classificação, ou com cClassTrib
  que o cenário não conhece. Sai da conta com a receita dita, e deveria ser
  zero antes de apresentar: o aviso diz quanto falta classificar.
* **Exclusão** — linha sem custo de compra. É método, não erro, mas a receita
  que ficou de fora vai ao relatório, porque muda a leitura da margem.
* **Um mês só** — a sazonalidade impede extrapolar: o aviso lembra quando a
  base tem uma competência.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import caminhos_do_projeto, pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de, reais
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.escrita import LeituraCancelada, parar_se_pedirem
from cat.infraestrutura.analitico.reforma import Andamento, ResultadoDaSimulacao, serializar, simular
from cat.infraestrutura.planilhas.reforma import gerar as gerar_planilha
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "simulacao_reforma"
VERSAO_DO_RESUMO = 1

FONTES = (TipoDeArquivo.REFORMA_BASE_CUSTEADA, TipoDeArquivo.REFORMA_CLASSIFICACAO)

# montada na rodada; o download serve este arquivo pronto
ARQUIVO_DA_SIMULACAO = "simulacao_reforma.xlsx"


class NadaParaSimular(ValueError):
    """Não há como rodar: falta a base custeada ou a classificação no lote."""


def _separar(projeto_id: int, sessao: Session) -> tuple[list[str], list[str]]:
    bases = caminhos_do_projeto(projeto_id, (TipoDeArquivo.REFORMA_BASE_CUSTEADA,), sessao)
    classificacoes = caminhos_do_projeto(projeto_id, (TipoDeArquivo.REFORMA_CLASSIFICACAO,),
                                         sessao)
    return sorted(set(bases)), sorted(set(classificacoes))


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    """Põe a execução na fila, ou recusa dizendo o que falta."""
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "simular a reforma tributária")

    bases, classificacoes = _separar(projeto_id, sessao)
    if not bases:
        raise NadaParaSimular(
            "O lote não tem a planilha de saídas custeadas: uma linha por loja e item, com a "
            "receita bruta, os débitos de hoje, o custo líquido de compra e os créditos de ICMS "
            "e PIS/COFINS (o leiaute \"Margem e Impacto Tributário\").")
    if not classificacoes:
        raise NadaParaSimular(
            "O lote não tem a classificação dos itens: o código do item com a NCM revisada, o "
            "CST e o cClassTrib. Sem ela não há como saber a alíquota de cada venda.")

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila",
                          passo="Na fila", arquivos_totais=len(bases) + len(classificacoes),
                          criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Simulação da reforma · {len(bases)} base(s) custeada(s) e "
        f"{len(classificacoes)} classificação(ões) no lote",
        dados={"execucao_id": execucao.id, "bases": len(bases),
               "classificacoes": len(classificacoes)},
        autor_id=usuario_id)
    return execucao


def executar(execucao_id: int) -> None:
    """O que a fila chama. Cancelamento e falha são estados, não exceções soltas."""
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None:
            log.error("execução sumiu antes de rodar", extra={"execucao_id": execucao_id})
            return
        destino = pasta_da_execucao(execucao_id)
        diario = Diario(execucao, sessao, VERSAO_DO_RESUMO)
        with contexto(etapa=ETAPA, execucao_id=execucao_id, projeto_id=execucao.projeto_id):
            try:
                _rodar(execucao, destino, sessao, diario)
            except LeituraCancelada:
                log.warning("simulação da reforma cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nenhum número dela vale.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Simulação da reforma cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("simulação da reforma falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Simulação da reforma falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo a classificação dos itens"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    bases, classificacoes = _separar(execucao.projeto_id, sessao)
    execucao.arquivos_totais = len(bases) + len(classificacoes)
    diario.anotar("info", f"{len(bases)} base(s) custeada(s) e {len(classificacoes)} "
                          "classificação(ões) de itens no lote. Cenário: LC 214/2025, "
                          "referência 26,5%, Imposto Seletivo hipotético.")
    freio = Freio(execucao.id)

    def parar() -> None:
        parar_se_pedirem(freio)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = len(classificacoes) + a.arquivos
        execucao.documentos = a.linhas
        # a leitura das bases é quase todo o tempo; a projeção é o resto
        execucao.fracao = min(0.95, a.arquivos / len(bases)) if bases else 0.0
        execucao.passo = (f"Lendo as saídas custeadas: {milhar(a.linhas)} linhas, "
                          f"{a.arquivos} de {len(bases)} arquivo(s)")
        diario.base["andamento"] = {"arquivos": a.arquivos, "linhas": a.linhas}
        diario.salvar_de_vez_em_quando()

    resultado = simular(bases, classificacoes, avisar=andou, deve_parar=parar)

    execucao.passo = "Montando a planilha"
    sessao.commit()
    gerar_planilha(resultado, os.path.join(destino, ARQUIVO_DA_SIMULACAO))

    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = execucao.arquivos_totais
    execucao.documentos = resultado.linhas_lidas
    diario.base.update(serializar(resultado))
    _anotar(resultado, diario)
    execucao.terminada_em = datetime.now(timezone.utc)
    total = resultado.total
    ano_base = resultado.cenario.ano_base
    ultimo = resultado.cenario.anos[-1].ano
    lb_base, lb_ultimo = total.anos[ano_base].lucro_bruto, total.anos[ultimo].lucro_bruto
    diario.anotar(
        "info",
        f"Concluída em {duracao(resultado.segundos)}: {milhar(resultado.linhas_consideradas)} "
        f"linhas e {milhar(len(resultado.enquadramentos))} SKUs simulados. Lucro bruto "
        f"{reais(lb_base)} em {ano_base} e {reais(lb_ultimo)} em {ultimo}.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Simulação da reforma · lucro bruto {reais(lb_base)} ({ano_base}) → "
        f"{reais(lb_ultimo)} ({ultimo})",
        dados={"execucao_id": execucao.id, "linhas": resultado.linhas_consideradas,
               "skus": len(resultado.enquadramentos), "lucro_bruto_base": str(lb_base),
               "lucro_bruto_final": str(lb_ultimo), "segundos": resultado.segundos},
        autor_id=execucao.criada_por)


def _anotar(r: ResultadoDaSimulacao, diario: Diario) -> None:
    pendentes = sum(c.linhas for c in r.pendencias.values())
    if pendentes:
        receita = sum(c.receita_bruta for c in r.pendencias.values())
        diario.anotar("aviso", f"{milhar(pendentes)} linha(s), {reais(receita)} de receita "
                               "bruta, ficaram fora por falta de cadastro: item sem "
                               "classificação ou cClassTrib sem grupo. Deveria ser zero antes "
                               "de apresentar — veja a aba \"Fora da conta\".")
    for motivo, conta in sorted(r.exclusoes.items(), key=lambda kv: -kv[1].receita_liquida):
        diario.anotar("info", f"{milhar(conta.linhas)} linha(s) sem custo de compra fora da "
                              f"conta por \"{motivo}\": {reais(conta.receita_liquida)} de "
                              "receita líquida.")
    if r.conflitos_de_cadastro:
        diario.anotar("aviso", f"{milhar(r.conflitos_de_cadastro)} SKU(s) aparecem com "
                               "classificação diferente em dois arquivos; valeu o primeiro. "
                               "Ex.: " + "; ".join(r.exemplos_de_conflito[:3]))
    if len(r.competencias) == 1:
        diario.anotar("aviso", f"A base tem uma competência só ({next(iter(r.competencias))}). "
                               "A sazonalidade impede extrapolar um mês para o ano: para a "
                               "leitura anual, importe o ano-calendário inteiro.")
    diario.anotar("info", "As alíquotas do Imposto Seletivo e a referência de 26,5% são "
                          "hipóteses. O resultado mede o efeito com preço e volume constantes; "
                          "não é previsão de preço nem de venda.")
