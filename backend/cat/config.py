"""Configuração por variável de ambiente. Nenhum segredo no código."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CAT_", extra="ignore")

    # Postgres é o banco do sistema. A porta 55432 é do contêiner de
    # desenvolvimento; 5432 e 5433 costumam estar ocupadas por Postgres local.
    # SQLite continua servindo à bateria de testes, e de propósito: ele não
    # guarda fuso horário, então é o ambiente mais severo para essa parte.
    banco_url: str = "postgresql+psycopg://cat:cat@localhost:55432/cat"

    # CAT_JWT_*, CAT_SENHA_PIMENTA e CAT_ORIGENS_PERMITIDAS seguem no mesmo .env,
    # mas só a API em C# os lê: o motor não confere senha, não lê token e não
    # atende navegador desde a fatia 7.

    # Segredo do canal interno com a API em C# (routers/interno_router.py).
    # Vazio fecha o canal para todo mundo, em vez de abri-lo.
    motor_segredo: str = ""

    # O trabalhador da fila de execuções (workers/fila.py) sobe com o motor.
    # Os testes desligam e esvaziam a fila na hora, para não depender de tempo.
    fila_automatica: bool = True

    log_nivel: str = "INFO"

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

    # Teto de memória do motor analítico. Existe para o confronto derramar
    # em disco em vez de brigar por RAM com a API e com o Postgres, que
    # rodam na mesma máquina. Baixo demais só deixa mais lento; alto demais
    # derruba o processo inteiro.
    memoria_analitica: str = "4GB"

    # Quantas linhas de execução o motor analítico usa. Cada uma mantém os
    # próprios blocos de agrupamento e de ordenação, então mais linhas é
    # mais memória de pico — e o gargalo aqui é memória, não processador.
    # Zero deixa o DuckDB decidir.
    threads_analiticas: int = 4

    # Quantos processos escrevem e pré-validam os arquivos digitais ao mesmo
    # tempo — os que a etapa 7 gera e os que o cliente já transmitiu. As duas
    # partes são Python puro, uma por arquivo: num perfil de 12 arquivos do
    # Amigão, 48% do tempo era pré-validação e 40% escrita. Zero escolhe pelo
    # processador, deixando folga para a API e o Postgres; 1 lê um por vez.
    processos_do_arquivo_digital: int = 0

    @property
    def processos_para_arquivos(self) -> int:
        if self.processos_do_arquivo_digital > 0:
            return self.processos_do_arquivo_digital
        return max(1, min(8, (os.cpu_count() or 2) - 4))

    @property
    def raiz_de_trabalho(self) -> str:
        """A pasta de trabalho como caminho absoluto.

        Relativo depende de onde o processo subiu, e dois processos com
        diretórios diferentes gravariam em lugares diferentes sem ninguém
        perceber. Pior: dois com o MESMO diretório e bancos diferentes
        gravam no mesmo lugar — foi assim que a bateria de testes
        sobrescreveu a planilha de uma execução real.
        """
        return os.path.abspath(self.pasta_de_trabalho)

    @property
    def lista_pastas_permitidas(self) -> list[str]:
        return [p.strip() for p in self.pastas_permitidas.split(";") if p.strip()]

    @property
    def usa_sqlite(self) -> bool:
        return self.banco_url.startswith("sqlite")


@lru_cache
def obter_config() -> Config:
    return Config()
