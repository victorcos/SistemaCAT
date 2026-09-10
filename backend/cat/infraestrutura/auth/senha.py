"""Hash de senha com bcrypt. Nunca guardar senha, nem cifrada."""

from __future__ import annotations

import bcrypt

# bcrypt trunca em 72 bytes; avisar em vez de cortar em silêncio
LIMITE_BYTES = 72


class SenhaLonga(ValueError):
    pass


class SenhasBcrypt:
    def gerar(self, senha: str) -> str:
        bruto = senha.encode("utf-8")
        if len(bruto) > LIMITE_BYTES:
            raise SenhaLonga(
                f"A senha excede {LIMITE_BYTES} bytes, que é o limite do bcrypt."
            )
        return bcrypt.hashpw(bruto, bcrypt.gensalt()).decode("utf-8")

    def conferir(self, senha: str, hash_armazenado: str) -> bool:
        try:
            return bcrypt.checkpw(
                senha.encode("utf-8")[:LIMITE_BYTES],
                hash_armazenado.encode("utf-8"),
            )
        except (ValueError, TypeError):
            # hash corrompido ou vazio: é falha de conferência, não exceção
            return False
