"""Domínio de acesso. Sem banco, sem rede — roda em milissegundos."""

import pytest

from cat.dominio.acesso.usuario import (
    Cargo, Papel, SenhaFraca, TENTATIVAS_BLOQUEIO_PERMANENTE, Usuario,
    UsuarioBloqueado, UsuarioInativo, validar_email, validar_nome_de_usuario,
    validar_politica_de_senha,
)


def novo(**troca) -> Usuario:
    base = dict(id=1, usuario="ana", email="ana@bms.local",
                nome_exibicao="Ana", papel=Papel.ANALISTA)
    base.update(troca)
    return Usuario(**base)


class TestPolitica:
    @pytest.mark.parametrize("senha", ["Sistema2026cat", "Xyz12345678A"])
    def test_aceita_senha_boa(self, senha):
        validar_politica_de_senha(senha)

    @pytest.mark.parametrize("senha,pedaco", [
        ("Curta1A", "10 caracteres"),
        ("tudominusculo1", "maiúsculas"),
        ("TUDOMAIUSCULO1", "maiúsculas"),
        ("SemNumeroAqui", "número"),
        (" ComEspaco123 ", "espaço"),
    ])
    def test_recusa_senha_ruim(self, senha, pedaco):
        with pytest.raises(SenhaFraca, match=pedaco):
            validar_politica_de_senha(senha)


class TestIdentificadores:
    def test_normaliza_usuario(self):
        assert validar_nome_de_usuario("  Ana.Silva  ") == "ana.silva"

    @pytest.mark.parametrize("nome", ["ab", "com espaco", "acento_ç", "A" * 41])
    def test_recusa_usuario_invalido(self, nome):
        with pytest.raises(ValueError):
            validar_nome_de_usuario(nome)

    def test_normaliza_email(self):
        assert validar_email("  Ana@BMS.com  ") == "ana@bms.com"

    @pytest.mark.parametrize("email", ["sem-arroba", "a@b", "@b.com"])
    def test_recusa_email_invalido(self, email):
        with pytest.raises(ValueError):
            validar_email(email)


class TestEntrada:
    def test_usuario_normal_entra(self):
        novo().garantir_que_pode_entrar()

    def test_inativo_nao_entra(self):
        with pytest.raises(UsuarioInativo):
            novo(ativo=False).garantir_que_pode_entrar()

    def test_inativo_tem_precedencia_sobre_bloqueado(self):
        """Desativar e decisao do gestor; bloquear e consequencia automatica."""
        u = novo(ativo=False, tentativas_falhas=TENTATIVAS_BLOQUEIO_PERMANENTE)
        with pytest.raises(UsuarioInativo):
            u.garantir_que_pode_entrar()

    def test_bloqueio_definitivo_impede_entrada(self):
        u = novo(tentativas_falhas=TENTATIVAS_BLOQUEIO_PERMANENTE)
        with pytest.raises(UsuarioBloqueado):
            u.garantir_que_pode_entrar()

    def test_sucesso_zera_tentativas_e_marca_acesso(self):
        u = novo(tentativas_falhas=3)
        u.registrar_sucesso()
        assert u.tentativas_falhas == 0
        assert u.ultimo_acesso is not None


class TestEscopo:
    def test_so_enxerga_empresa_alocada(self):
        u = novo(empresas=(10, 20))
        assert u.enxerga_empresa(10)
        assert not u.enxerga_empresa(30)

    def test_sem_alocacao_nao_enxerga_nada(self):
        assert not novo().enxerga_empresa(10)

    def test_gestor_sem_alocacao_enxerga_tudo(self):
        """Para quem executa, alocação diz SOBRE QUEM se trabalha. Gestor não
        tem esse recorte: responde pela carteira inteira da casa."""
        gestor = novo(papel=Papel.GESTOR, empresas=())
        assert gestor.papel.administra_usuarios
        assert gestor.enxerga_empresa(10)


class TestPapel:
    def test_so_gestor_administra(self):
        assert Papel.GESTOR.administra_usuarios
        for p in (Papel.ANALISTA, Papel.REVISOR, Papel.LEITURA):
            assert not p.administra_usuarios

    def test_leitura_nao_escreve(self):
        assert not Papel.LEITURA.pode_escrever
        for p in (Papel.GESTOR, Papel.ANALISTA, Papel.REVISOR):
            assert p.pode_escrever


class TestCargo:
    def test_cargo_nao_e_papel(self):
        """Cargo e informacao organizacional; papel e permissao."""
        u = novo(papel=Papel.ANALISTA, cargo=Cargo.DIRETOR)
        assert u.cargo.e_de_gestao
        assert not u.papel.administra_usuarios

    def test_cargos_de_gestao(self):
        for c in (Cargo.DIRETOR, Cargo.GERENTE, Cargo.COORDENADOR):
            assert c.e_de_gestao
        for c in (Cargo.ANALISTA, Cargo.ESTAGIARIO, Cargo.OUTRO):
            assert not c.e_de_gestao

    def test_padrao_e_outro(self):
        assert novo().cargo is Cargo.OUTRO


class TestSenhaProvisoria:
    def test_marca_troca_obrigatoria(self):
        assert novo(senha_provisoria=True).precisa_trocar_senha

    def test_senha_normal_nao_pede_troca(self):
        assert not novo().precisa_trocar_senha
