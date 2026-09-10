"""Bloqueio em dois níveis.

Destravar é muito mais frequente que redefinir senha, então o bloqueio comum
tem de se resolver sozinho. O que exige gestor fica para quem insistiu muito.
"""

from datetime import timedelta

import pytest

from cat.dominio.acesso.usuario import (
    MINUTOS_BLOQUEIO_TEMPORARIO,
    Papel,
    TENTATIVAS_BLOQUEIO_PERMANENTE,
    TENTATIVAS_BLOQUEIO_TEMPORARIO,
    Usuario,
    UsuarioBloqueado,
    UsuarioBloqueadoTemporariamente,
    agora,
)


def novo(**t) -> Usuario:
    base = dict(id=1, usuario="ana", email="ana@bms.local", nome_exibicao="Ana",
                papel=Papel.ANALISTA)
    base.update(t)
    return Usuario(**base)


def errar(u: Usuario, vezes: int, quando=None) -> None:
    for _ in range(vezes):
        u.registrar_falha(quando)


class TestTemporario:
    def test_antes_do_limite_ainda_entra(self):
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO - 1)
        u.garantir_que_pode_entrar()

    def test_no_limite_bloqueia_por_tempo(self):
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO)
        with pytest.raises(UsuarioBloqueadoTemporariamente) as erro:
            u.garantir_que_pode_entrar()
        assert erro.value.minutos == MINUTOS_BLOQUEIO_TEMPORARIO

    def test_se_resolve_sozinho_depois_da_espera(self):
        """Este é o ponto: bloqueio comum não gera chamado para o gestor."""
        t0 = agora()
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO, t0)
        depois = t0 + timedelta(minutes=MINUTOS_BLOQUEIO_TEMPORARIO, seconds=1)
        u.garantir_que_pode_entrar(depois)

    def test_a_mensagem_diz_quanto_falta(self):
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO)
        with pytest.raises(UsuarioBloqueadoTemporariamente) as erro:
            u.garantir_que_pode_entrar()
        assert str(erro.value.minutos) in str(erro.value)

    def test_novo_patamar_estende_a_espera(self):
        t0 = agora()
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO, t0)
        depois = t0 + timedelta(minutes=MINUTOS_BLOQUEIO_TEMPORARIO, seconds=1)
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO, depois)
        with pytest.raises(UsuarioBloqueadoTemporariamente):
            u.garantir_que_pode_entrar(depois)


class TestPermanente:
    def test_exige_gestor(self):
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_PERMANENTE)
        with pytest.raises(UsuarioBloqueado):
            u.garantir_que_pode_entrar()

    def test_o_tempo_nao_resolve(self):
        t0 = agora()
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_PERMANENTE, t0)
        muito_depois = t0 + timedelta(days=30)
        with pytest.raises(UsuarioBloqueado):
            u.garantir_que_pode_entrar(muito_depois)

    def test_gestor_desbloqueia(self):
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_PERMANENTE)
        u.desbloquear()
        u.garantir_que_pode_entrar()
        assert u.tentativas_falhas == 0

    def test_desbloquear_nao_mexe_na_senha(self):
        u = novo(senha_provisoria=True)
        errar(u, TENTATIVAS_BLOQUEIO_PERMANENTE)
        u.desbloquear()
        assert u.senha_provisoria is True


class TestSucesso:
    def test_entrar_limpa_contador_e_espera(self):
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO)
        u.registrar_sucesso()
        assert u.tentativas_falhas == 0
        assert u.bloqueado_ate is None
        u.garantir_que_pode_entrar()

    def test_tentativas_restantes_no_ciclo(self):
        u = novo()
        assert u.tentativas_restantes == TENTATIVAS_BLOQUEIO_TEMPORARIO
        errar(u, 2)
        assert u.tentativas_restantes == TENTATIVAS_BLOQUEIO_TEMPORARIO - 2


class TestFusoHorario:
    """O SQLite devolve data sem fuso. O domínio não pode depender do banco."""

    def test_bloqueio_gravado_sem_fuso_ainda_funciona(self):
        from datetime import datetime

        t0 = agora()
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO, t0)
        # simula o que volta do SQLite: mesma data, sem fuso
        u.bloqueado_ate = u.bloqueado_ate.replace(tzinfo=None)
        assert isinstance(u.bloqueado_ate, datetime)
        with pytest.raises(UsuarioBloqueadoTemporariamente):
            u.garantir_que_pode_entrar()

    def test_espera_vencida_sem_fuso_libera(self):
        t0 = agora()
        u = novo()
        errar(u, TENTATIVAS_BLOQUEIO_TEMPORARIO, t0)
        u.bloqueado_ate = u.bloqueado_ate.replace(tzinfo=None)
        depois = t0 + timedelta(minutes=MINUTOS_BLOQUEIO_TEMPORARIO, seconds=1)
        u.garantir_que_pode_entrar(depois)
