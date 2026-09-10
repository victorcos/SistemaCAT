"""Emissão e leitura de JWT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from cat.dominio.acesso.usuario import Papel, Usuario


class TokenInvalido(Exception):
    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__("Sessão inválida ou expirada.")


@dataclass(frozen=True)
class Conteudo:
    usuario_id: int
    usuario: str
    papel: Papel
    empresas: tuple[int, ...]


class TokensJwt:
    def __init__(self, segredo: str, algoritmo: str, minutos: int) -> None:
        self._segredo = segredo
        self._algoritmo = algoritmo
        self._minutos = minutos

    def emitir(self, usuario: Usuario) -> tuple[str, int]:
        agora = datetime.now(timezone.utc)
        expira = agora + timedelta(minutes=self._minutos)
        carga = {
            "sub": str(usuario.id),
            "usr": usuario.usuario,
            "pap": usuario.papel.value,
            # escopo de empresa viaja no token para a API não consultar a cada
            # requisição; a fonte continua sendo a alocação vigente no banco
            "emp": list(usuario.empresas),
            "iat": int(agora.timestamp()),
            "exp": int(expira.timestamp()),
        }
        token = jwt.encode(carga, self._segredo, algorithm=self._algoritmo)
        return token, self._minutos * 60

    def ler(self, token: str) -> Conteudo:
        try:
            carga = jwt.decode(token, self._segredo, algorithms=[self._algoritmo])
        except JWTError as erro:
            raise TokenInvalido(str(erro)) from erro
        try:
            return Conteudo(
                usuario_id=int(carga["sub"]),
                usuario=carga["usr"],
                papel=Papel(carga["pap"]),
                empresas=tuple(carga.get("emp", ())),
            )
        except (KeyError, ValueError) as erro:
            raise TokenInvalido(f"conteúdo inesperado: {erro}") from erro
