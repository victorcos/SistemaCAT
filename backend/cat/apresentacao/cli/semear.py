"""Cria o primeiro gestor e uma empresa de exemplo, para o sistema subir vazio
sem ficar inacessível. Roda uma vez.

    python -m cat.apresentacao.cli.semear
"""

from __future__ import annotations

import secrets
import sys

from cat.config import obter_config
from cat.dominio.acesso.usuario import Papel, validar_politica_de_senha
from cat.infraestrutura.repositorios.banco import Sessao, criar_tabelas
from cat.infraestrutura.repositorios.modelos import AlocacaoDB, EmpresaDB
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from cat.log import configurar, obter_log

log = obter_log(__name__)


def main() -> int:
    configurar(obter_config().log_nivel)
    criar_tabelas()
    sessao = Sessao()
    repo = UsuarioRepositorioSql(sessao)

    if repo.existe_algum():
        log.info("já existe usuário, nada a semear")
        print("Já existe usuário. Nada foi feito.")
        return 0

    senha = sys.argv[1] if len(sys.argv) > 1 else _senha_forte()
    validar_politica_de_senha(senha)

    empresa = EmpresaDB(
        cnpj_raiz="00000000",
        razao_social="Empresa de exemplo",
        grupo_economico="—",
        uf="SP",
    )
    sessao.add(empresa)
    sessao.commit()
    sessao.refresh(empresa)

    usuario = repo.criar(
        usuario="gestor",
        email="gestor@bms.local",
        nome_exibicao="Gestor",
        senha=senha,
        papel=Papel.GESTOR,
    )
    sessao.add(
        AlocacaoDB(
            usuario_id=usuario.id,
            empresa_id=empresa.id,
            papel_projeto="responsavel",
        )
    )
    sessao.commit()

    print("\n  Usuário .. gestor")
    print(f"  Senha .... {senha}")
    print("\n  Anote agora. Esta senha não é exibida de novo.\n")
    log.info("semeadura concluída",
             extra={"usuario_id": usuario.id, "empresa_id": empresa.id})
    return 0


def _senha_forte() -> str:
    alfabeto = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        s = "".join(secrets.choice(alfabeto) for _ in range(16))
        try:
            validar_politica_de_senha(s)
            return s
        except Exception:
            continue


if __name__ == "__main__":
    raise SystemExit(main())
