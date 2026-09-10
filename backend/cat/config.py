"""Configuração por variável de ambiente. Nenhum segredo no código."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CAT_", extra="ignore")

    # Postgres é o banco do sistema. A porta 55432 é do contêiner de
    # desenvolvimento; 5432 e 5433 costumam estar ocupadas por Postgres local.
    # SQLite continua servindo à bateria de testes, e de propósito: ele não
    # guarda fuso horário, então é o ambiente mais severo para essa parte.
    banco_url: str = "postgresql+psycopg://cat:cat@localhost:55432/cat"

    # obrigatório trocar em produção; o valor padrão só existe para o dev subir
    jwt_segredo: str = "trocar-em-producao-isto-nao-e-segredo"
    jwt_algoritmo: str = "HS256"
    jwt_minutos: int = 480          # uma jornada de trabalho

    # pimenta: segredo do servidor que entra no resumo da senha e fica FORA do
    # banco. Vazar só o banco não basta para atacar as senhas.
    # Trocar a pimenta invalida todas as senhas existentes — só com plano.
    senha_pimenta: str = ""

    log_nivel: str = "INFO"
    origens_permitidas: str = "http://localhost:5173"

    # De onde o lote pode ler arquivo. Separar por ";".
    # Vazio libera o disco inteiro, o que serve enquanto o sistema roda na
    # máquina de quem trabalha. No dia em que virar servidor compartilhado,
    # isto precisa estar preenchido: sem limite, qualquer usuário do sistema
    # pede a listagem de qualquer pasta da máquina.
    pastas_permitidas: str = ""

    # Onde ficam os parquets de cada execução. Disco LOCAL de propósito:
    # gravação longa em unidade de rede se perde (ARQUITETURA §8), e uma
    # extração dessas grava por minutos.
    pasta_de_trabalho: str = "data/trabalho"

    @property
    def lista_origens(self) -> list[str]:
        return [o.strip() for o in self.origens_permitidas.split(",") if o.strip()]

    @property
    def lista_pastas_permitidas(self) -> list[str]:
        return [p.strip() for p in self.pastas_permitidas.split(";") if p.strip()]

    @property
    def usa_sqlite(self) -> bool:
        return self.banco_url.startswith("sqlite")

    @property
    def sem_pimenta(self) -> bool:
        return not self.senha_pimenta

    @property
    def segredo_e_padrao(self) -> bool:
        return self.jwt_segredo.startswith("trocar-em-producao")


@lru_cache
def obter_config() -> Config:
    return Config()
