"""O papel DEV e o que ele pode a mais.

Dev existe para manutenção: precisa reproduzir problema em qualquer cliente sem
depender de alguém alocá-lo em cada empresa nova. O preço desse poder é que o
acesso sem alocação tem de ser distinguível no log, e que a conta técnica não
pode substituir responsável pelo negócio.
"""

import pytest

from cat.dominio.acesso.usuario import Cargo, Papel, Usuario


def usuario(papel: Papel, empresas=()) -> Usuario:
    return Usuario(id=1, usuario="alguem", email="a@bms.local",
                   nome_exibicao="Alguém", papel=papel, cargo=Cargo.OUTRO,
                   empresas=empresas)


class TestPoderes:
    def test_dev_administra_usuarios(self):
        assert Papel.DEV.administra_usuarios

    def test_dev_escreve(self):
        assert Papel.DEV.pode_escrever

    def test_so_dev_ignora_o_escopo_de_empresa(self):
        assert Papel.DEV.ignora_escopo_de_empresa
        for p in (Papel.GESTOR, Papel.ANALISTA, Papel.REVISOR, Papel.LEITURA):
            assert not p.ignora_escopo_de_empresa


class TestEscopo:
    def test_dev_enxerga_empresa_sem_alocacao(self):
        assert usuario(Papel.DEV).enxerga_empresa(99)

    def test_gestor_sem_alocacao_nao_enxerga(self):
        """A diferença entre dev e gestor mora aqui."""
        assert not usuario(Papel.GESTOR).enxerga_empresa(99)

    def test_dev_com_alocacao_nao_marca_excecao(self):
        d = usuario(Papel.DEV, empresas=(7,))
        assert d.enxerga_empresa(7)
        assert not d.acessa_por_excecao(7)

    def test_dev_sem_alocacao_marca_excecao(self):
        """É o que permite o log distinguir acesso normal de bypass."""
        d = usuario(Papel.DEV, empresas=(7,))
        assert d.enxerga_empresa(99)
        assert d.acessa_por_excecao(99)

    def test_quem_nao_e_dev_nunca_marca_excecao(self):
        for p in (Papel.GESTOR, Papel.ANALISTA, Papel.REVISOR, Papel.LEITURA):
            assert not usuario(p, empresas=(7,)).acessa_por_excecao(99)


class TestNaoContaComoGestor:
    def test_dev_nao_conta(self):
        """Se contasse, dois gestores mais um dev pareceriam três e a
        salvaguarda do mínimo estaria furada."""
        assert not Papel.DEV.conta_como_gestor

    def test_gestor_conta(self):
        assert Papel.GESTOR.conta_como_gestor

    def test_os_demais_nao_contam(self):
        for p in (Papel.ANALISTA, Papel.REVISOR, Papel.LEITURA):
            assert not p.conta_como_gestor


class TestValorNoBanco:
    def test_o_valor_gravado_e_dev(self):
        assert Papel.DEV.value == "dev"

    def test_texto_desconhecido_nao_vira_dev(self):
        """Rebaixar para leitura é o padrão; virar dev por acidente, jamais."""
        with pytest.raises(ValueError):
            Papel("desenvolvedor")
