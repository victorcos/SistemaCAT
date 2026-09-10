"""Portas — o que a aplicação exige do mundo, sem saber quem entrega.

É o que permite testar caso de uso sem banco. Ver docs/CONTRATOS.md.
"""

from __future__ import annotations

from typing import Protocol

from cat.dominio.acesso.usuario import Usuario


class RepositorioUsuario(Protocol):
    def buscar_por_usuario(self, usuario: str) -> Usuario | None: ...

    def obter_hash_senha(self, usuario_id: int) -> str: ...

    def salvar_tentativa(self, usuario: Usuario) -> None: ...

    def regravar_hash_senha(self, usuario_id: int, novo_hash: str) -> None: ...


class VerificadorDeSenha(Protocol):
    def conferir(self, senha: str, hash_armazenado: str) -> bool: ...

    def precisa_regravar(self, hash_armazenado: str) -> bool: ...

    def gerar(self, senha: str) -> str: ...


class EmissorDeToken(Protocol):
    def emitir(self, usuario: Usuario) -> tuple[str, int]:
        """Devolve o token e por quantos segundos ele vale."""
        ...
