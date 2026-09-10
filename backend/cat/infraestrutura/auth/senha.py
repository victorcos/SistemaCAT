"""Proteção de senha.

Senha NÃO é criptografada. Criptografia é reversível: quem tem a chave recupera
o valor original, e isso é justamente o que não pode acontecer. O sistema não
deve ser capaz de descobrir a senha de ninguém, nem sob ordem judicial, nem com
acesso total ao banco.

O que se faz é resumo de mão única com função lenta e propositalmente cara, mais
sal aleatório por senha. Na conferência, resume-se o que foi digitado e comparam-
se os resumos.

Algoritmo: **Argon2id**, vencedor da Password Hashing Competition e recomendação
atual da OWASP. Ele é caro em memória, não só em tempo, o que tira a vantagem de
quem ataca com placa de vídeo — é exatamente onde o bcrypt fica atrás.

Camadas aqui:

1. **Sal** aleatório por senha, gerado pela biblioteca. Duas pessoas com a mesma
   senha têm resumos diferentes, e tabela pronta de ataque não serve.
2. **Pimenta** (`CAT_SENHA_PIMENTA`), segredo do servidor que entra na conta e
   fica FORA do banco. Vazar só o banco não basta para atacar as senhas.
   Isto sim é segredo, e o único ponto onde há chave nesta história.
3. **Reprocessamento transparente**: ao entrar, se o resumo estiver em formato
   antigo (bcrypt) ou com parâmetros defasados, ele é regravado no formato
   atual. A migração acontece sozinha, sem pedir troca de senha a ninguém.
"""

from __future__ import annotations

import hashlib
import hmac

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError, VerificationError, VerifyMismatchError,
)

from cat.log import obter_log

log = obter_log(__name__)

# bcrypt trunca em 72 bytes; o Argon2 não tem esse limite, mas mantemos um teto
# para não aceitar entrada absurda
LIMITE_BCRYPT = 72
LIMITE_SENHA = 1024


class SenhaLonga(ValueError):
    pass


class SenhasArgon2:
    """Resumo de senha com Argon2id, com migração automática do bcrypt.

    Os parâmetros são os padrões da biblioteca, que seguem a RFC 9106: 64 MiB de
    memória, 3 iterações e 4 vias. Custam cerca de 50 ms por conferência nesta
    máquina, que é o alvo: imperceptível para quem entra, caro para quem tenta
    milhões de combinações.
    """

    def __init__(self, pimenta: str = "") -> None:
        self._ph = PasswordHasher()
        self._pimenta = pimenta.encode("utf-8") if pimenta else b""

    # ---------- interno ----------
    def _temperar(self, senha: str) -> str:
        """Aplica a pimenta antes do resumo.

        Passa por HMAC-SHA256 primeiro para que o resultado tenha tamanho fixo,
        o que também elimina o limite de 72 bytes que o bcrypt impõe.
        """
        if not self._pimenta:
            return senha
        return hmac.new(
            self._pimenta, senha.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    # ---------- uso ----------
    def gerar(self, senha: str) -> str:
        if len(senha.encode("utf-8")) > LIMITE_SENHA:
            raise SenhaLonga(f"A senha excede {LIMITE_SENHA} bytes.")
        return self._ph.hash(self._temperar(senha))

    def conferir(self, senha: str, hash_armazenado: str) -> bool:
        if not hash_armazenado:
            return False

        if hash_armazenado.startswith("$argon2"):
            try:
                self._ph.verify(hash_armazenado, self._temperar(senha))
                return True
            except VerifyMismatchError:
                return False
            except (VerificationError, InvalidHashError) as erro:
                log.error(
                    "resumo de senha ilegível no banco",
                    extra={"formato": "argon2", "erro": type(erro).__name__},
                )
                return False

        # formato antigo: bcrypt, gravado antes da migração
        if hash_armazenado.startswith("$2"):
            try:
                # o bcrypt legado foi gravado sem pimenta
                return bcrypt.checkpw(
                    senha.encode("utf-8")[:LIMITE_BCRYPT],
                    hash_armazenado.encode("utf-8"),
                )
            except (ValueError, TypeError):
                log.error("resumo de senha ilegível no banco",
                          extra={"formato": "bcrypt"})
                return False

        log.error("formato de resumo de senha desconhecido",
                  extra={"prefixo": hash_armazenado[:7]})
        return False

    def precisa_regravar(self, hash_armazenado: str) -> bool:
        """Diz se o resumo está em formato antigo ou com parâmetros defasados.

        Chamado depois de uma conferência bem-sucedida, para regravar sem que o
        usuário perceba. É o que permite endurecer os parâmetros no futuro sem
        forçar ninguém a trocar de senha.
        """
        if not hash_armazenado.startswith("$argon2"):
            return True
        try:
            return self._ph.check_needs_rehash(hash_armazenado)
        except InvalidHashError:
            return True


# nome antigo mantido para não quebrar importação existente
SenhasBcrypt = SenhasArgon2
