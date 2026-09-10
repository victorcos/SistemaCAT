"""Configuração por variável de ambiente. Nenhum segredo no código."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CAT_", extra="ignore")

    # Postgres em produção; SQLite só para rodar teste sem subir contêiner
    banco_url: str = "sqlite:///./data/cat.db"

    # obrigatório trocar em produção; o valor padrão só existe para o dev subir
    jwt_segredo: str = "trocar-em-producao-isto-nao-e-segredo"
    jwt_algoritmo: str = "HS256"
    jwt_minutos: int = 480          # uma jornada de trabalho

    log_nivel: str = "INFO"
    origens_permitidas: str = "http://localhost:5173"

    @property
    def lista_origens(self) -> list[str]:
        return [o.strip() for o in self.origens_permitidas.split(",") if o.strip()]

    @property
    def segredo_e_padrao(self) -> bool:
        return self.jwt_segredo.startswith("trocar-em-producao")


@lru_cache
def obter_config() -> Config:
    return Config()
