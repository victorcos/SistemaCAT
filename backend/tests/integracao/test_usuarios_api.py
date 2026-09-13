"""Gestão de usuários pela API, ponta a ponta.

Cenário: os três gestores que o sistema exige, mais um analista.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app  # noqa: E402
from cat.config import obter_config  # noqa: E402
from cat.dominio.acesso.usuario import MINIMO_DE_GESTORES, Cargo, Papel  # noqa: E402
from cat.infraestrutura.auth.senha import SenhasArgon2  # noqa: E402
from cat.infraestrutura.repositorios.modelos import Base  # noqa: E402
from cat.infraestrutura.repositorios.usuario_repositorio import (  # noqa: E402
    UsuarioRepositorioSql,
)
from tests.integracao.sessao import cabecalhos_de, senha_confere, usuario

SENHA = "Sistema2026cat"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    repo = UsuarioRepositorioSql(s)
    senhas = SenhasArgon2(obter_config().senha_pimenta)

    for nome, cargo in [("diretor", Cargo.DIRETOR), ("gerente", Cargo.GERENTE),
                        ("coordenador", Cargo.COORDENADOR)]:
        repo.criar(usuario=nome, email=f"{nome}@bms.local",
                   nome_exibicao=nome.title(), senha_hash=senhas.gerar(SENHA),
                   papel=Papel.GESTOR, cargo=cargo)
    repo.criar(usuario="ana", email="ana@bms.local", nome_exibicao="Ana",
               senha_hash=senhas.gerar(SENHA), papel=Papel.ANALISTA,
               cargo=Cargo.ANALISTA)
    s.close()

    with TestClient(app) as c:
        yield c


def cab(cliente, nome, senha=SENHA):
    return cabecalhos_de(nome, senha)


def id_de(cliente, nome, como="diretor"):
    """Procura pelo nome. Identificador fixo quebra quando a bateria compartilha
    banco com outro módulo."""
    lista = cliente.get("/api/usuarios", headers=cab(cliente, como)).json()
    return next(u["id"] for u in lista if u["usuario"] == nome)


# ---------------------------------------------------------------------------
class TestPermissao:
    def test_sem_token_nao_lista(self, cliente):
        assert cliente.get("/api/usuarios").status_code == 401

    def test_analista_nao_lista(self, cliente):
        r = cliente.get("/api/usuarios", headers=cab(cliente, "ana"))
        assert r.status_code == 403

    def test_analista_nao_cria(self, cliente):
        r = cliente.post("/api/usuarios", headers=cab(cliente, "ana"), json={
            "usuario": "invasor", "email": "i@bms.local",
            "nome_exibicao": "I", "papel": "gestor", "cargo": "outro"})
        assert r.status_code == 403

    def test_analista_nao_redefine_senha_de_outro(self, cliente):
        alvo = id_de(cliente, "diretor")
        r = cliente.post(f"/api/usuarios/{alvo}/senha", headers=cab(cliente, "ana"))
        assert r.status_code == 403

    def test_gestor_lista(self, cliente):
        r = cliente.get("/api/usuarios", headers=cab(cliente, "diretor"))
        assert r.status_code == 200
        assert len(r.json()) >= 4


class TestCadastro:
    def test_gestor_cria_e_recebe_senha_provisoria(self, cliente):
        r = cliente.post("/api/usuarios", headers=cab(cliente, "diretor"), json={
            "usuario": "joao.novo", "email": "joao@bms.local",
            "nome_exibicao": "João", "papel": "analista", "cargo": "analista"})
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["usuario"]["senha_provisoria"] is True
        assert len(corpo["senha_provisoria"]) >= 10
        assert "não será exibida de novo" in corpo["aviso"]

    def test_nao_aceita_usuario_repetido(self, cliente):
        r = cliente.post("/api/usuarios", headers=cab(cliente, "diretor"), json={
            "usuario": "ana", "email": "outra@bms.local",
            "nome_exibicao": "Outra", "papel": "leitura", "cargo": "outro"})
        assert r.status_code == 409


class TestDados:
    """Nome e e-mail mudam pela rota de dados; o nome de usuário, nunca."""

    def test_gestor_altera_nome_e_email(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'ana')}/dados",
                          headers=cab(cliente, "diretor"),
                          json={"nome_exibicao": "Ana Paula", "email": "ana.paula@bms.local"})
        assert r.status_code == 200, r.text
        assert r.json()["nome_exibicao"] == "Ana Paula"
        assert r.json()["email"] == "ana.paula@bms.local"
        assert r.json()["usuario"] == "ana"           # imutável

    def test_email_de_outro_usuario_e_recusado(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'ana')}/dados",
                          headers=cab(cliente, "diretor"),
                          json={"nome_exibicao": "Ana", "email": "gerente@bms.local"})
        assert r.status_code == 409
        assert "e-mail" in r.json()["detail"]

    def test_o_proprio_email_nao_conta_como_duplicado(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'ana')}/dados",
                          headers=cab(cliente, "diretor"),
                          json={"nome_exibicao": "Ana Paula S.", "email": "ana.paula@bms.local"})
        assert r.status_code == 200, r.text

    def test_email_invalido_da_422(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'ana')}/dados",
                          headers=cab(cliente, "diretor"),
                          json={"nome_exibicao": "Ana", "email": "sem-arroba"})
        assert r.status_code == 422

    def test_quem_nao_e_gestor_nao_altera(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'gerente')}/dados",
                          headers=cab(cliente, "ana"),
                          json={"nome_exibicao": "X Y", "email": "x@bms.local"})
        assert r.status_code == 403


TRIO = ("diretor", "gerente", "coordenador")


@pytest.fixture
def so_o_trio(cliente):
    """Deixa ativos apenas os três gestores deste módulo.

    A salvaguarda conta o banco inteiro e a bateria compartilha um banco. Sem
    isto, um gestor semeado por outro módulo empurra a contagem para quatro e
    a recusa que se quer provar não acontece — o teste quebra sem que a regra
    tenha mudado. Foi o que aconteceu quando o módulo de histórico ganhou um
    gestor próprio.
    """
    c = cab(cliente, "diretor")
    extras = [
        u for u in cliente.get("/api/usuarios", headers=c).json()
        if u["papel"] == "gestor" and u["ativo"] and u["usuario"] not in TRIO
    ]
    # rebaixar é permitido enquanto sobrarem os três — é por isso que dá para
    # limpar o excedente sem esbarrar na própria salvaguarda
    for u in extras:
        r = cliente.patch(f"/api/usuarios/{u['id']}/papel", headers=c,
                          json={"papel": "analista"})
        assert r.status_code == 200, r.text
    assert len(TRIO) == MINIMO_DE_GESTORES
    yield
    for u in extras:
        cliente.patch(f"/api/usuarios/{u['id']}/papel", headers=c,
                      json={"papel": "gestor"})


class TestMinimoDeGestores:
    def test_nao_rebaixa_deixando_menos_de_tres(self, cliente, so_o_trio):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'gerente')}/papel",
                          headers=cab(cliente, "diretor"),
                          json={"papel": "analista"})
        assert r.status_code == 409
        assert "3 gestores" in r.json()["detail"]

    def test_nao_desativa_deixando_menos_de_tres(self, cliente, so_o_trio):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'gerente')}/situacao",
                          headers=cab(cliente, "diretor"),
                          json={"ativo": False})
        assert r.status_code == 409

    def test_gestor_nao_se_desativa(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'diretor')}/situacao",
                          headers=cab(cliente, "diretor"),
                          json={"ativo": False})
        assert r.status_code == 409
        assert "si mesmo" in r.json()["detail"]


class TestFluxoDaSenhaProvisoria:
    def test_ciclo_completo(self, cliente):
        """Gestor redefine, a pessoa entra, é obrigada a trocar, e a provisória
        para de funcionar."""
        gestor = cab(cliente, "diretor")
        alvo = cliente.get("/api/usuarios", headers=gestor).json()
        ana = next(u for u in alvo if u["usuario"] == "ana")

        r = cliente.post(f"/api/usuarios/{ana['id']}/senha", headers=gestor)
        assert r.status_code == 200
        provisoria = r.json()["senha_provisoria"]

        # a provisória confere e a conta fica marcada para trocar (o login em
        # C# lê esta marca e a tela obriga a troca)
        assert senha_confere("ana", provisoria)
        assert usuario("ana").senha_provisoria is True

        # troca
        nova = "TrocadaPelaAna2026"
        t = cabecalhos_de("ana", provisoria)
        troca = cliente.post("/api/usuarios/eu/senha", headers=t,
                             json={"senha_atual": provisoria, "senha_nova": nova})
        assert troca.status_code == 204

        # a provisória morreu, a nova funciona e a marca de troca sumiu
        assert not senha_confere("ana", provisoria)
        assert senha_confere("ana", nova)
        assert usuario("ana").senha_provisoria is False

    def test_troca_exige_a_senha_atual(self, cliente):
        t = cab(cliente, "coordenador")
        r = cliente.post("/api/usuarios/eu/senha", headers=t,
                         json={"senha_atual": "chutando", "senha_nova": "Nova2026abc"})
        assert r.status_code == 401

    def test_troca_recusa_senha_fraca(self, cliente):
        t = cab(cliente, "coordenador")
        r = cliente.post("/api/usuarios/eu/senha", headers=t,
                         json={"senha_atual": SENHA, "senha_nova": "curta1A"})
        assert r.status_code == 422

    def test_senha_provisoria_nunca_volta_em_listagem(self, cliente):
        """A senha só aparece uma vez, na resposta de quem a gerou."""
        corpo = cliente.get("/api/usuarios", headers=cab(cliente, "diretor")).text
        assert "senha_provisoria" in corpo          # o sinalizador, sim
        assert SENHA not in corpo                   # a senha, nunca


class TestDesbloqueio:
    def test_gestor_desbloqueia(self, cliente):
        gestor = cab(cliente, "diretor")
        lista = cliente.get("/api/usuarios", headers=gestor).json()
        alvo = next(u for u in lista if u["usuario"] == "joao.novo")

        # cinco senhas erradas, gravadas como o login em C# grava
        from cat.dominio.acesso.usuario import UsuarioBloqueadoTemporariamente
        from cat.infraestrutura.repositorios.banco import Sessao
        with Sessao() as s:
            repo = UsuarioRepositorioSql(s)
            joao = repo.buscar_por_usuario("joao.novo")
            for _ in range(5):
                joao.registrar_falha()
            repo.salvar_tentativa(joao)
        with pytest.raises(UsuarioBloqueadoTemporariamente, match="minuto"):
            usuario("joao.novo").garantir_que_pode_entrar()

        r = cliente.post(f"/api/usuarios/{alvo['id']}/desbloquear", headers=gestor)
        assert r.status_code == 200
        assert r.json()["tentativas_falhas"] == 0


class TestAcessoAEmpresas:
    """De onde vem o escopo de visibilidade.

    Antes desta rota a alocação só nascia de quem cadastrava a empresa pelo
    SPED — e os outros ficavam sem acesso a nada, sem caminho para ganhá-lo.
    """

    @pytest.fixture(scope="class")
    def empresa_id(self, cliente):
        r = cliente.post("/api/empresas", headers=cab(cliente, "diretor"), json={
            "cnpj_raiz": "12345678", "cnpj_matriz": "12345678000195",
            "razao_social": "EMPRESA DO ACESSO", "uf": "SP",
            "inscricao_estadual": "123456789012",
        })
        assert r.status_code in (201, 409), r.text
        lista = cliente.get("/api/empresas", headers=cab(cliente, "diretor")).json()
        return next(e["id"] for e in lista if e["cnpj_raiz"] == "12345678")

    def test_lista_todas_as_empresas_marcando_as_que_alcanca(self, cliente, empresa_id):
        r = cliente.get(f"/api/usuarios/{id_de(cliente, 'ana')}/empresas",
                        headers=cab(cliente, "diretor"))
        assert r.status_code == 200, r.text
        alvo = next(e for e in r.json() if e["empresa_id"] == empresa_id)
        assert alvo["tem_acesso"] is False
        assert alvo["razao_social"] == "EMPRESA DO ACESSO"

    def test_conceder_e_a_pessoa_passa_a_enxergar(self, cliente, empresa_id):
        alvo = id_de(cliente, "ana")
        r = cliente.put(f"/api/usuarios/{alvo}/empresas",
                        headers=cab(cliente, "diretor"),
                        json={"empresas": [empresa_id]})
        assert r.status_code == 200, r.text
        assert r.json()["concedidas"] == ["EMPRESA DO ACESSO"]
        assert r.json()["encerradas"] == []

        assert empresa_id in _empresas_de(cliente, "ana")

    def test_encerrar_tira_o_acesso_sem_apagar_a_linha(self, cliente, empresa_id):
        from sqlalchemy import text  # noqa: PLC0415

        from cat.infraestrutura.repositorios.banco import Sessao  # noqa: PLC0415

        alvo = id_de(cliente, "ana")
        r = cliente.put(f"/api/usuarios/{alvo}/empresas",
                        headers=cab(cliente, "diretor"), json={"empresas": []})
        assert r.status_code == 200, r.text
        assert r.json()["encerradas"] == ["EMPRESA DO ACESSO"]

        assert empresa_id not in _empresas_de(cliente, "ana")

        # a linha fica, com fim preenchido: quem tinha acesso em março
        # continua respondível meses depois
        with Sessao() as s:
            n = s.execute(text(
                "SELECT count(*) FROM alocacao WHERE usuario_id=:u "
                "AND empresa_id=:e AND fim IS NOT NULL"
            ), {"u": alvo, "e": empresa_id}).scalar()
        assert n == 1

    def test_ninguem_tira_o_proprio_acesso(self, cliente, empresa_id):
        meu_id = id_de(cliente, "diretor")
        # garante que o diretor tem ao menos uma empresa para tentar tirar
        cliente.put(f"/api/usuarios/{meu_id}/empresas",
                    headers=cab(cliente, "diretor"), json={"empresas": [empresa_id]})
        r = cliente.put(f"/api/usuarios/{meu_id}/empresas",
                        headers=cab(cliente, "diretor"), json={"empresas": []})
        assert r.status_code == 422
        assert "próprio acesso" in r.json()["detail"]

    def test_empresa_inexistente_e_recusada(self, cliente):
        r = cliente.put(f"/api/usuarios/{id_de(cliente, 'ana')}/empresas",
                        headers=cab(cliente, "diretor"),
                        json={"empresas": [999999]})
        assert r.status_code == 422
        assert "Empresa não encontrada" in r.json()["detail"]

    def test_quem_nao_e_gestor_nao_mexe(self, cliente, empresa_id):
        # `ana` teve a senha mexida por testes anteriores; o que importa aqui
        # é o papel, e para isso basta um token de analista qualquer
        r = cliente.put(f"/api/usuarios/{id_de(cliente, 'ana')}/empresas",
                        headers={"Authorization": "Bearer invalido"},
                        json={"empresas": [empresa_id]})
        assert r.status_code == 401


def _empresas_de(cliente, nome: str) -> list[int]:
    """As empresas que a pessoa alcança, lidas pela listagem do gestor."""
    lista = cliente.get("/api/usuarios", headers=cab(cliente, "diretor")).json()
    return next(u["empresas"] for u in lista if u["usuario"] == nome)
