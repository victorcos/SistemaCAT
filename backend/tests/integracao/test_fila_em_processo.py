"""A rodada num processo próprio: o que morre lá não leva o motor, e vira falha.

Os alvos do processo filho moram neste módulo, no nível de cima, porque o
processo novo os reimporta pelo nome.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from workers import fila

from cat.config import obter_config
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import Base, ExecucaoDB


@pytest.fixture(scope="module")
def projeto_para_fila():
    from tests.integracao.cadastro import criar_empresa, criar_projeto, criar_usuario  # noqa: PLC0415
    motor = create_engine(obter_config().banco_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    criar_usuario(s, usuario="fila.processo", email="fila.processo@bms.local",
                  nome_exibicao="Fila", papel="analista")
    s.close()
    empresa = criar_empresa(raiz="27182818", cnpj="27182818000160", razao="EMPRESA DO PROCESSO",
                            por="fila.processo")
    return criar_projeto(empresa_id=empresa, nome=f"Processo {os.urandom(3).hex()}", por="fila.processo")


def morrer_sem_aviso(etapa: str, execucao_id: int) -> None:
    """Como o sistema faz com quem pede memória que não há: sem exceção, sem log."""
    os._exit(3)


def concluir(etapa: str, execucao_id: int) -> None:
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        execucao.situacao = "concluida"
        execucao.passo = "Concluída"
        execucao.terminada_em = datetime.now(timezone.utc)
        sessao.commit()


def sair_sem_gravar(etapa: str, execucao_id: int) -> None:
    return None


def _rodando(projeto_id: int) -> int:
    with Sessao() as sessao:
        execucao = ExecucaoDB(projeto_id=projeto_id, etapa="st_suportado", situacao="rodando",
                              passo="Lendo", criada_por=None)
        sessao.add(execucao)
        sessao.commit()
        return execucao.id


def _situacao(execucao_id: int) -> tuple[str, str | None]:
    with Sessao() as sessao:
        e = sessao.get(ExecucaoDB, execucao_id)
        return e.situacao, e.erro


class TestRodadaEmProcesso:
    def test_processo_que_morre_vira_falha_com_motivo(self, projeto_para_fila):
        execucao_id = _rodando(projeto_para_fila)
        assert fila.rodar_em_processo(execucao_id, "st_suportado", alvo=morrer_sem_aviso) == 3
        situacao, erro = _situacao(execucao_id)
        assert situacao == "falhou"
        assert "código 3" in erro and "memória" in erro

    def test_processo_que_conclui_fica_concluido(self, projeto_para_fila):
        execucao_id = _rodando(projeto_para_fila)
        assert fila.rodar_em_processo(execucao_id, "st_suportado", alvo=concluir) == 0
        assert _situacao(execucao_id) == ("concluida", None)

    def test_processo_que_sai_sem_gravar_nao_fica_rodando(self, projeto_para_fila):
        execucao_id = _rodando(projeto_para_fila)
        assert fila.rodar_em_processo(execucao_id, "st_suportado", alvo=sair_sem_gravar) == 0
        situacao, erro = _situacao(execucao_id)
        assert situacao == "falhou" and "sem gravar o resultado" in erro
