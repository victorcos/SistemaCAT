"""Agregação de um arquivo EFD-Contribuições em UMA passada.

Lê o arquivo em bytes, linha a linha (memória constante), e produz um
``ApuracaoEFD``:

- registros de apuração (0110/0111, bloco M, 1100/1300/1500/1700) guardados
  inteiros — são poucas linhas por arquivo;
- ajustes M110/M220/M510/M620 somados por IND_AJ + COD_AJ (um arquivo real
  tem 6 mil M110 de estorno, e o quadro só usa a soma);
- itens dos blocos A/C/D/F somados por tributo, registro, operação, CST,
  CFOP, natureza do crédito e alíquota.

A natureza de crédito do C170/C191 NÃO é derivada aqui (fica vazia): o
montador dos quadros aplica a tabela CFOP -> natureza. Assim uma correção
nessa tabela vale sem reler o arquivo.

A leitura para no registro 9999: o que vem depois é a assinatura digital
em binário.

Portado do projeto Quebra de SPED em 22/09/2026. Duas coisas mudaram no
caminho, e as duas são regra desta casa:

* **o 0000 é lido pelo domínio**, nunca aqui por posição fixa. O original
  pegava `c[5], c[6], c[7], c[8]` — que até acerta na EFD-Contribuições, mas é
  a forma que já devolveu UF no lugar de CNPJ duas vezes neste projeto (ver
  DECISOES de 22/09/2026);
* **o log é o estruturado**, com o contexto que localiza o erro sem precisar
  reproduzi-lo.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.gestao.leiaute import (
    DO_PAI,
    DO_PROPRIO_F100,
    DOCUMENTOS,
    REGISTROS_AJUSTE,
    REGISTROS_APURACAO,
    SAIDA,
)
from cat.infraestrutura.gestao.modelos import ApuracaoEFD
from cat.infraestrutura.gestao.numeros import ValorInvalido, aliquota_10k, centavos
from cat.log import obter_log

log = obter_log(__name__)

# Descartes além deste número (por motivo) só são contados, não logados um a um.
_MAX_LOG_POR_MOTIVO = 20
_PASSO_PROGRESSO = 64 * (1 << 20)


def _montar_plano() -> dict[bytes, tuple]:
    """Pré-calcula, por registro, os índices já deslocados para o split por '|'.

    ``line.split(b"|")`` devolve ``["", "C170", campo1, ...]``: o campo de
    índice ``i`` do leiaute fica na posição ``i + 1``.
    """
    plano: dict[bytes, tuple] = {}
    for reg, d in DOCUMENTOS.items():
        tributos = tuple(
            (
                t.nome,
                t.i_cst + 1,
                None if t.i_bc is None else t.i_bc + 1,
                t.i_aliq + 1,
                t.i_valor + 1,
                None if t.i_quant is None else t.i_quant + 1,
            )
            for t in d.tributos
        )
        plano[reg.encode("ascii")] = (
            reg,
            d.operacao,
            d.i_vl_item + 1,
            None if d.i_cfop is None else d.i_cfop + 1,
            None if d.i_nat is None else d.i_nat + 1,
            d.cfop_do_pai,
            tributos,
        )
    return plano


_PLANO = _montar_plano()
_APURACAO_B = frozenset(r.encode("ascii") for r in REGISTROS_APURACAO)
_AJUSTE_B = frozenset(r.encode("ascii") for r in REGISTROS_AJUSTE)


def _detectar_encoding(path: Path) -> str:
    with open(path, "rb") as f:
        inicio = f.read(3)
    return "utf-8-sig" if inicio == b"\xef\xbb\xbf" else "cp1252"


def _identificar(ap: ApuracaoEFD, linha: str, descartar) -> None:
    """A empresa e o período, pelo leitor do domínio.

    Quem conhece os três leiautes do 0000 é `dominio/sped/cabecalho.py`, que
    acha cada campo **pela forma** — o par de datas de 8 dígitos, o CNPJ de 14
    com dígito conferido. Ler por posição aqui foi o erro que este projeto
    cometeu duas vezes; não se comete a terceira.
    """
    try:
        c = ler_cabecalho(linha)
    except ArquivoNaoReconhecido as erro:
        descartar("registro_0000_nao_reconhecido", 0, erro=str(erro)[:120])
        return
    # o domínio devolve o CNPJ como objeto de valor, já com o dígito conferido;
    # a gestão trabalha com o texto de 14 dígitos, que é o que vai no relatório
    ap.cnpj = c.cnpj.valor if c.cnpj is not None else ""
    ap.razao_social = c.nome or ""
    ap.cod_ver = c.versao_leiaute or ""
    ap.tipo_escrit = "1" if c.retificadora else "0"
    if c.inicio is not None:
        ap.dt_ini = c.inicio.strftime("%d%m%Y")
        ap.periodo = c.inicio.strftime("%Y-%m")
    if c.fim is not None:
        ap.dt_fin = c.fim.strftime("%d%m%Y")


def agregar_efd(
    path: str | Path,
    file_hash: str = "",
    on_progress: Callable[[int, int], None] | None = None,
) -> ApuracaoEFD:
    """Lê o arquivo inteiro uma vez e devolve o resumo para a gestão."""
    path = Path(path)
    tamanho = path.stat().st_size
    encoding = _detectar_encoding(path)
    ap = ApuracaoEFD(arquivo=str(path), file_hash=file_hash, tamanho=tamanho)
    nome = os.path.basename(str(path))
    log.info("gestão começou a ler a efd", extra={
        "arquivo": nome, "bytes": tamanho, "codificacao": encoding})

    documentos: dict[tuple, list[int]] = {}
    registros: dict[str, list[list[str]]] = {}
    ajustes: dict[tuple[str, str, str], int] = {}
    contagens: dict[bytes, int] = {}
    descartes: dict[str, int] = {}

    # Contexto do registro pai corrente
    ind_oper = {b"A": b"", b"C": b""}
    cfop_d200 = b""

    def descartar(motivo: str, nlinha: int, **ctx) -> None:
        """Nunca descartar em silêncio — mas também não encher o log.

        As primeiras ocorrências de cada motivo saem com linha e contexto, que é
        o que permite abrir o arquivo no lugar certo. Da vigésima em diante só a
        contagem, que vai no resumo: um arquivo torto tem milhares.
        """
        n = descartes.get(motivo, 0) + 1
        descartes[motivo] = n
        if n <= _MAX_LOG_POR_MOTIVO:
            log.warning("linha da efd descartada na gestão", extra={
                "arquivo": nome, "motivo": motivo, "linha": nlinha, "ocorrencia": n, **ctx})

    t0 = time.monotonic()
    lidos = 0
    proximo_progresso = _PASSO_PROGRESSO
    fim_encontrado = False

    with open(path, "rb", buffering=8 << 20) as f:
        for nlinha, line in enumerate(f, 1):
            lidos += len(line)
            if on_progress is not None and lidos >= proximo_progresso:
                on_progress(lidos, tamanho)
                proximo_progresso += _PASSO_PROGRESSO

            if line[:1] != b"|":
                continue
            j = line.find(b"|", 1)
            if j < 0:
                continue
            reg = line[1:j]
            contagens[reg] = contagens.get(reg, 0) + 1

            plano = _PLANO.get(reg)
            if plano is not None:
                reg_s, operacao, i_vl, i_cfop, i_nat, cfop_pai, tributos = plano
                campos = line.rstrip(b"\r\n").split(b"|")
                try:
                    if operacao == DO_PAI:
                        pai = ind_oper[reg[:1]]
                        if pai == b"1":
                            op = "S"
                        elif pai == b"0":
                            op = "E"
                        else:
                            descartar("item_sem_registro_pai", nlinha, registro=reg_s)
                            continue
                    elif operacao == DO_PROPRIO_F100:
                        op = "E" if campos[2] == b"0" else "S"
                    else:
                        op = "S" if operacao == SAIDA else "E"

                    if i_cfop is not None:
                        cfop = campos[i_cfop].decode("ascii")
                    elif cfop_pai:
                        cfop = cfop_d200.decode("ascii")
                    else:
                        cfop = ""
                    nat = campos[i_nat].decode("ascii") if i_nat is not None else ""
                    vl_item = centavos(campos[i_vl])

                    for nome, i_cst, i_bc, i_aliq, i_valor, i_quant in tributos:
                        cst = campos[i_cst].decode("ascii")
                        if not cst:
                            descartar("cst_vazio", nlinha, registro=reg_s, tributo=nome)
                            continue
                        chave = (nome, reg_s, op, cst, cfop, nat, aliquota_10k(campos[i_aliq]))
                        soma = documentos.get(chave)
                        if soma is None:
                            soma = documentos[chave] = [0, 0, 0, 0, 0]
                        soma[0] += vl_item
                        if i_bc is not None:
                            soma[1] += centavos(campos[i_bc])
                        soma[2] += centavos(campos[i_valor])
                        if i_quant is not None:
                            soma[3] += centavos(campos[i_quant])
                        soma[4] += 1
                except IndexError:
                    descartar("campos_faltando", nlinha, registro=reg_s, qtd_campos=len(campos) - 2)
                except (ValorInvalido, UnicodeDecodeError) as exc:
                    descartar("valor_invalido", nlinha, registro=reg_s, erro=str(exc)[:120])
                continue

            if reg == b"C100" or reg == b"A100":
                ind_oper[reg[:1]] = line[6:7]
            elif reg == b"D200":
                partes = line.split(b"|", 10)
                cfop_d200 = partes[8] if len(partes) > 8 else b""
            elif reg in _APURACAO_B:
                campos_s = line.rstrip(b"\r\n").decode(encoding, errors="replace").split("|")[1:-1]
                registros.setdefault(campos_s[0], []).append(campos_s)
            elif reg in _AJUSTE_B:
                campos_s = line.rstrip(b"\r\n").decode(encoding, errors="replace").split("|")[1:-1]
                try:
                    chave_aj = (campos_s[0], campos_s[1], campos_s[3])
                    ajustes[chave_aj] = ajustes.get(chave_aj, 0) + centavos(campos_s[2])
                except (IndexError, ValorInvalido) as exc:
                    descartar("ajuste_invalido", nlinha, registro=campos_s[0], erro=str(exc)[:120])
            elif reg == b"0000":
                _identificar(ap, line.rstrip(b"\r\n").decode(encoding, errors="replace"),
                             descartar)
            elif reg == b"9999":
                fim_encontrado = True
                break

    if on_progress is not None:
        on_progress(tamanho, tamanho)

    ap.registros = registros
    ap.ajustes = ajustes
    ap.documentos = documentos
    ap.contagens = {k.decode("ascii", errors="replace"): v for k, v in contagens.items()}
    ap.descartes = descartes
    ap.segundos = round(time.monotonic() - t0, 2)

    if not fim_encontrado:
        descartes["arquivo_sem_registro_9999"] = 1
    if not ap.periodo:
        log.error("efd sem período no 0000: a gestão não sabe em que coluna pô-la",
                  extra={"arquivo": nome})
    log.info("gestão terminou de ler a efd", extra={
        "arquivo": nome, "periodo": ap.periodo, "cnpj": ap.cnpj, "segundos": ap.segundos,
        "mb_por_segundo": round(tamanho / 1e6 / max(ap.segundos, 0.001), 1),
        "grupos_de_documento": len(documentos), "registros_de_apuracao": len(registros),
        "descartes": descartes,
    })
    return ap
