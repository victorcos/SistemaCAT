"""Cria os três gestores iniciais e uma empresa de exemplo.

São três porque o sistema recusa ficar com menos de três gestores ativos. Com
um só, férias, desligamento ou senha esquecida travariam tudo e não haveria quem
destravasse. Os cargos são direção, gerência e coordenação.

    python -m cat.apresentacao.cli.semear
"""

from __future__ import annotations

from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel, gerar_senha_provisoria
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.banco import Sessao, criar_tabelas
from cat.infraestrutura.repositorios.modelos import AlocacaoDB, EmpresaDB
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from cat.log import configurar, obter_log

log = obter_log(__name__)

GESTORES = [
    ("diretor", "diretor@bms.local", "Diretor", Cargo.DIRETOR),
    ("gerente", "gerente@bms.local", "Gerente", Cargo.GERENTE),
    ("coordenador", "coordenador@bms.local", "Coordenador", Cargo.COORDENADOR),
]


def main() -> int:
    cfg = obter_config()
    configurar(cfg.log_nivel)
    criar_tabelas()
    sessao = Sessao()
    repo = UsuarioRepositorioSql(sessao)

    if repo.existe_algum():
        log.info("já existe usuário, nada a semear")
        print("Já existe usuário. Nada foi feito.")
        return 0

    empresa = EmpresaDB(
        cnpj_raiz="00000000",
        razao_social="Empresa de exemplo",
        grupo_economico="—",
        uf="SP",
    )
    sessao.add(empresa)
    sessao.commit()
    sessao.refresh(empresa)

    senhas = SenhasArgon2(cfg.senha_pimenta)
    criados = []
    for nome, email, exibicao, cargo in GESTORES:
        senha = gerar_senha_provisoria()
        u = repo.criar(
            usuario=nome,
            email=email,
            nome_exibicao=exibicao,
            senha_hash=senhas.gerar(senha),
            papel=Papel.GESTOR,
            cargo=cargo,
            senha_provisoria=True,
        )
        sessao.add(
            AlocacaoDB(
                usuario_id=u.id, empresa_id=empresa.id, papel_projeto="responsavel"
            )
        )
        criados.append((nome, cargo.value, senha))
    sessao.commit()

    print("\n  Três gestores criados. A troca de senha é obrigatória no")
    print("  primeiro acesso de cada um.\n")
    print(f"  {'usuário':14} {'cargo':13} senha provisória")
    print(f"  {'-'*14} {'-'*13} {'-'*16}")
    for nome, cargo, senha in criados:
        print(f"  {nome:14} {cargo:13} {senha}")
    print("\n  Anote agora. Estas senhas não são exibidas de novo.\n")

    log.info("semeadura concluída",
             extra={"gestores": len(criados), "empresa_id": empresa.id})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
