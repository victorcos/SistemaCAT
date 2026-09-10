"""Configuração comum dos testes.

Este arquivo é carregado pelo pytest **antes** de qualquer módulo de teste, que
é a única janela em que dá para definir o ambiente com efeito.

O motivo de centralizar aqui: `obter_config` é cacheada e `banco.py` cria o
motor no import. Se cada módulo de teste definisse o banco por conta própria,
valeria o do primeiro que fosse importado, e os demais gravariam no lugar
errado. Foi exatamente o que aconteceu.
"""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="cat_testes_")

# Um único banco para toda a bateria de integração. Cada módulo semeia com
# nomes próprios para não colidir.
os.environ.setdefault(
    "CAT_BANCO_URL", f"sqlite:///{_TMP}/testes.db".replace("\\", "/")
)
os.environ.setdefault("CAT_JWT_SEGREDO", "segredo-so-de-teste-nao-usar-em-producao")
os.environ.setdefault("CAT_SENHA_PIMENTA", "pimenta-so-de-teste")
os.environ.setdefault("CAT_LOG_NIVEL", "WARNING")
