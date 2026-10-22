"""Triagem da rede: em que cliente há ISS de saída para tirar da base do PIS/COFINS.

O 933 (`sped/exclusao_do_iss.py`) já lê a oportunidade — mas só no lote que
alguém cadastrou. Este módulo responde a pergunta de antes: **em qual das
centenas de pastas da rede vale a pena cadastrar um lote?** Ele não calcula a
tese; aponta onde ela pode existir.

## Três leituras, cada uma mais cara que a anterior

1. **Varredura** — `os.scandir` e 64 KB do começo e 64 KB do fim de cada
   candidato. O começo traz o 0000 (tipo, CNPJ, período, original ou
   retificadora); o fim traz o 9999 e, logo antes dele, o **9900**: a contagem
   que o próprio arquivo declara de cada registro. É dali que sai quantos A100
   o arquivo tem, **sem abrir o resto**. Arquivo com A100 = 0 está descartado.
2. **Bloco A** — só para quem tem A100. O bloco A vem logo depois do 0, então
   a leitura para no A990: 9,5 MB em vez de 1,1 GB, 0,29 s em vez de 17 s,
   medido na empresa 23. É aqui que se separa saída (IND_OPER = 1) de serviço
   tomado, que é crédito e não receita.
3. **O 933** — fora deste módulo, no lote cadastrado.

## Quatro coisas que só apareceram na rede real (22/10/2026, 6.053 arquivos)

* **O arquivo transmitido tem assinatura digital depois do 9999** — PKCS#7
  binário, perto de 8 KB, em 120 de 120 arquivos amostrados. Quem procura o
  9999 na última linha marca a base inteira como truncada.
* **`os.walk` + `os.stat` perde caminho de 260 caracteres ou mais**: a pasta
  lista o arquivo e o stat responde "não encontrado". Na empresa 23 foram 65
  arquivos e 34,6 GB que sumiriam calados. Daí o `DirEntry.stat()` (que vem
  da listagem) e o prefixo `\\\\?\\UNC\\` para abrir.
* **Hash do arquivo inteiro na varredura é inviável**: só as colisões de
  impressão somavam 85 GB a ler pela rede. A impressão é tamanho + os dois
  trechos de 64 KB que já foram lidos; o sha256 completo fica para quem lê o
  arquivo inteiro de qualquer forma.
* **Cópia é regra, não exceção**: 4.880 EFD ICMS/IPI eram 4.008 conteúdos, e
  155 EFD-Contribuições eram 121. E na empresa 23 há meses com **duas
  retificadoras diferentes** — mesma QTD_LIN no 9999, 270 MB de diferença. O
  módulo sugere a mais nova pelo carimbo do nome, mas marca para revisão: quem
  transmitiu é quem sabe qual vale.

## Nunca escreve na origem

Só lista e lê. O inventário é SQLite **local** — cache de leitura, como o
índice da quebra de SPED (DECISOES, 22/09/2026): apagado, refaz-se. Não vai
para o Postgres, porque ninguém decide nada sobre ele.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, TipoSped, ler_cabecalho
from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, codificacao_de, registro_de
from cat.infraestrutura.sped.registros import nomes_dos_campos
from cat.log import obter_log

log = obter_log(__name__)

EXTENSOES_TEXTO = (".txt", ".sped", ".efd")
EXTENSOES_ZIP = (".zip",)
# existem na rede, mas sem leitor na biblioteca padrão: entram no inventário
# como "nao_suportado", para a ausência não ser silenciosa
EXTENSOES_SEM_LEITOR = (".rar", ".7z")
AMOSTRA_DO_CABECALHO = 4096
# 64 KB cobrem a assinatura (~8 KB) e o bloco 9 inteiro com folga
TRECHO = 64 << 10
PASTAS_IGNORADAS = frozenset({"$recycle.bin", "system volume information", ".git", "__pycache__"})
SEGUNDOS_ENTRE_AVISOS = 15

_TIPO = {
    TipoSped.EFD_CONTRIBUICOES: "efd_contribuicoes", TipoSped.EFD_ICMS_IPI: "efd_icms_ipi",
    TipoSped.ECD: "ecd", TipoSped.ECF: "ecf",
}
_RE_CARIMBO = re.compile(r"_(?:Original|Retificadora)_(\d{14})_", re.IGNORECASE)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS execucao (
    id INTEGER PRIMARY KEY, inicio TEXT, fim TEXT, raizes TEXT, status TEXT,
    pastas INTEGER, candidatos INTEGER, identificados INTEGER, reaproveitados INTEGER,
    erros INTEGER, segundos REAL);
CREATE TABLE IF NOT EXISTS pasta_concluida (
    execucao_id INTEGER, caminho TEXT, PRIMARY KEY (execucao_id, caminho));
CREATE TABLE IF NOT EXISTS arquivo (
    caminho TEXT PRIMARY KEY,          -- membro de zip: <zip>!<membro>
    raiz TEXT,                         -- a raiz autorizada de onde veio
    nome TEXT, tamanho INTEGER, mtime REAL,
    status TEXT,                       -- ok | ilegivel | nao_sped | nao_suportado | vazio | zip
    tipo TEXT, cnpj TEXT, nome_empresa TEXT, dt_ini TEXT, dt_fin TEXT,
    cod_ver TEXT, tipo_escrit TEXT,    -- 0 original, 1 retificadora
    completo INTEGER,                  -- 1 = há |9999|; NULL = não verificado (zip)
    assinado INTEGER,                  -- 1 = há assinatura digital depois do 9999
    qtd_lin_9999 INTEGER,
    qtd_a100 INTEGER, qtd_a170 INTEGER, -- do 9900; NULL = bloco 9 fora do trecho lido
    impressao TEXT, motivo TEXT,
    primeira_execucao INTEGER, ultima_execucao INTEGER);
CREATE INDEX IF NOT EXISTS ix_arquivo_periodo ON arquivo (tipo, cnpj, dt_ini);
CREATE TABLE IF NOT EXISTS bloco_a (
    caminho TEXT PRIMARY KEY, tamanho INTEGER, mtime REAL,
    a100_saida INTEGER, a100_saida_tributada INTEGER, a100_entrada INTEGER,
    a100_cancelado INTEGER, saidas_sem_iss INTEGER,
    vl_doc_saida TEXT, vl_iss_saida TEXT, vl_pis_saida TEXT, vl_cofins_saida TEXT,
    a990_confere INTEGER, bytes_lidos INTEGER, segundos REAL);
CREATE TABLE IF NOT EXISTS erro (
    id INTEGER PRIMARY KEY, execucao_id INTEGER, caminho TEXT, etapa TEXT,
    mensagem TEXT, quando TEXT);
"""

_COLUNAS = ("caminho", "raiz", "nome", "tamanho", "mtime", "status", "tipo", "cnpj",
            "nome_empresa", "dt_ini", "dt_fin", "cod_ver", "tipo_escrit", "completo",
            "assinado", "qtd_lin_9999", "qtd_a100", "qtd_a170", "impressao", "motivo")


def caminho_longo(caminho: str) -> str:
    """O caminho com o prefixo que o Windows exige acima de 260 caracteres."""
    if os.name != "nt" or caminho.startswith("\\\\?\\"):
        return caminho
    absoluto = os.path.abspath(caminho)
    if absoluto.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absoluto[2:]
    return "\\\\?\\" + absoluto


def carimbo_do_nome(nome: str) -> str | None:
    """O AAAAMMDDHHMMSS que o ReceitaNet põe no nome. Pista, nunca prova."""
    m = _RE_CARIMBO.search(nome or "")
    return m.group(1) if m else None


def _primeira_linha(bruto: bytes) -> str:
    if bruto.startswith(b"\xef\xbb\xbf"):
        texto = bruto[3:].decode("utf-8", errors="replace")
    else:
        texto = bruto.decode("cp1252", errors="replace")
    return next((l for l in texto.splitlines() if l.strip()), "")


def identificar(comeco: bytes, fim: bytes | None) -> dict:
    """O que o 0000, o 9900 e o 9999 dizem do arquivo. `fim` None = não verificado."""
    linha = _primeira_linha(comeco)
    if not linha.startswith("|0000|"):
        return {"status": "nao_sped", "motivo": f"primeira linha não é 0000: {linha[:30]!r}"}
    try:
        cab = ler_cabecalho(linha)
    except ArquivoNaoReconhecido as erro:
        return {"status": "ok", "tipo": "outro", "motivo": str(erro)}
    d: dict = {
        "status": "ok", "tipo": _TIPO.get(cab.tipo, "outro"),
        "cnpj": cab.cnpj.valor if cab.cnpj else None, "nome_empresa": cab.nome,
        "dt_ini": cab.inicio.isoformat(), "dt_fin": cab.fim.isoformat(),
        "cod_ver": cab.versao_leiaute, "tipo_escrit": "1" if cab.retificadora else "0",
    }
    if fim is None:
        return d
    # o 9999 é procurado no trecho inteiro: depois dele vem a assinatura
    i = fim.rfind(b"|9999|")
    if i < 0:
        d["completo"] = 0
        d["motivo"] = f"|9999| ausente nos últimos {len(fim)} bytes (truncado)"
        return d
    d["completo"] = 1
    fim_da_linha = fim.find(b"\n", i)
    resto = fim[fim_da_linha + 1:] if fim_da_linha >= 0 else b""
    d["assinado"] = 1 if resto.strip(b"\r\n \x00\x1a") else 0
    try:
        d["qtd_lin_9999"] = int(fim[i:fim_da_linha if fim_da_linha >= 0 else None].split(b"|")[2])
    except (IndexError, ValueError):
        d["motivo"] = "9999 sem quantidade legível"
    # o bloco 9 abre no 9001; se ele não coube no trecho, a contagem fica NULL,
    # e NULL não é zero — o relatório diz que não se sabe
    j = fim.find(b"|9001|")
    if j >= 0:
        declarado = {}
        for ln in fim[j:i].split(b"\n"):
            partes = ln.split(b"|")
            if len(partes) > 3 and partes[1] == b"9900":
                try:
                    declarado[partes[2]] = int(partes[3])
                except ValueError:
                    log.warning("9900 com quantidade ilegível",
                                extra={"registro": partes[2].decode("ascii", "replace")})
        d["qtd_a100"] = declarado.get(b"A100", 0)
        d["qtd_a170"] = declarado.get(b"A170", 0)
    return d


@dataclass
class Contadores:
    pastas: int = 0
    candidatos: int = 0
    identificados: int = 0
    reaproveitados: int = 0
    erros: int = 0
    por_status: dict[str, int] = field(default_factory=dict)


class Interrompida(Exception):
    """O prazo da execução acabou. O que já foi feito fica, e `retomar` continua."""


class Inventario:
    """O SQLite da triagem. Reexecução não duplica: a chave é o caminho."""

    def __init__(self, banco: str) -> None:
        self.db = sqlite3.connect(banco)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(ESQUEMA)
        self.execucao_id = 0
        self.c = Contadores()
        self.prazo: float | None = None
        self._desde_o_commit = 0

    # ---------- execução ----------
    def abrir_execucao(self, raizes: list[str]) -> int:
        cur = self.db.execute(
            "INSERT INTO execucao (inicio, raizes, status) VALUES (?, ?, 'rodando')",
            (datetime.now().isoformat(timespec="seconds"), json.dumps(raizes, ensure_ascii=False)))
        self.db.commit()
        self.execucao_id = cur.lastrowid
        return self.execucao_id

    def retomar_execucao(self, execucao_id: int) -> list[str]:
        linha = self.db.execute("SELECT raizes FROM execucao WHERE id = ?", (execucao_id,)).fetchone()
        if linha is None:
            raise ValueError(f"execução {execucao_id} não existe neste inventário")
        self.execucao_id = execucao_id
        self.db.execute("UPDATE execucao SET status = 'retomada' WHERE id = ?", (execucao_id,))
        self.db.commit()
        return json.loads(linha[0])

    def fechar_execucao(self, segundos: float, status: str) -> None:
        c = self.c
        self.db.execute(
            "UPDATE execucao SET fim=?, status=?, pastas=?, candidatos=?, identificados=?, "
            "reaproveitados=?, erros=?, segundos=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), status, c.pastas, c.candidatos,
             c.identificados, c.reaproveitados, c.erros, round(segundos, 2), self.execucao_id))
        self.db.commit()

    def _erro(self, caminho: str, etapa: str, erro: BaseException | str) -> None:
        self.c.erros += 1
        log.warning("falha na triagem", extra={"caminho": caminho, "etapa": etapa, "motivo": str(erro)})
        self.db.execute(
            "INSERT INTO erro (execucao_id, caminho, etapa, mensagem, quando) VALUES (?,?,?,?,?)",
            (self.execucao_id, caminho, etapa, str(erro), datetime.now().isoformat(timespec="seconds")))

    def _talvez_commit(self) -> None:
        self._desde_o_commit += 1
        if self._desde_o_commit >= 200:
            self.db.commit()
            self._desde_o_commit = 0

    def _checar_prazo(self) -> None:
        # checado a cada arquivo, e não só a cada pasta: uma pasta de cliente
        # com milhares de SPED passava do prazo em quase um minuto na medição
        if self.prazo is not None and time.monotonic() > self.prazo:
            self.db.commit()
            raise Interrompida

    # ---------- varredura ----------
    def varrer(self, raiz: str) -> None:
        if not os.path.isdir(caminho_longo(raiz)):
            self._erro(raiz, "raiz_inacessivel", "a raiz não existe ou não há permissão")
            return
        concluidas = {r[0] for r in self.db.execute(
            "SELECT caminho FROM pasta_concluida WHERE execucao_id = ?", (self.execucao_id,))}
        pilha = [raiz]
        ultimo_aviso = time.monotonic()
        while pilha:
            pasta = pilha.pop()
            try:
                with os.scandir(caminho_longo(pasta)) as it:
                    entradas = list(it)
            except OSError as erro:
                self._erro(pasta, "listar_pasta", erro)
                continue
            self.c.pastas += 1
            ja_feita = pasta in concluidas
            for e in entradas:
                caminho = os.path.join(pasta, e.name)
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name.lower() not in PASTAS_IGNORADAS:
                            pilha.append(caminho)
                        continue
                except OSError as erro:
                    self._erro(caminho, "tipo_da_entrada", erro)
                    continue
                extensao = os.path.splitext(e.name)[1].lower()
                if ja_feita or extensao not in EXTENSOES_TEXTO + EXTENSOES_ZIP + EXTENSOES_SEM_LEITOR:
                    continue
                self._checar_prazo()
                try:
                    st = e.stat()  # no Windows vem da listagem: sem outra ida ao servidor
                except OSError as erro:
                    self._erro(caminho, "stat", erro)
                    continue
                self.c.candidatos += 1
                self._candidato(raiz, caminho, e.name, extensao, st.st_size, st.st_mtime)
            self.db.execute("INSERT OR IGNORE INTO pasta_concluida VALUES (?, ?)",
                            (self.execucao_id, pasta))
            self._talvez_commit()
            if time.monotonic() - ultimo_aviso > SEGUNDOS_ENTRE_AVISOS:
                ultimo_aviso = time.monotonic()
                log.info("triagem em andamento", extra={
                    "pastas": self.c.pastas, "candidatos": self.c.candidatos,
                    "reaproveitados": self.c.reaproveitados, "pilha": len(pilha)})
        self.db.commit()

    def _ja_conhecido(self, caminho: str, tamanho: int, mtime: float) -> bool:
        r = self.db.execute("SELECT tamanho, mtime, status FROM arquivo WHERE caminho = ?",
                            (caminho,)).fetchone()
        return bool(r and r[0] == tamanho and abs((r[1] or 0) - mtime) < 1e-3 and r[2] != "ilegivel")

    def _candidato(self, raiz, caminho, nome, extensao, tamanho, mtime) -> None:
        if self._ja_conhecido(caminho, tamanho, mtime):
            self.c.reaproveitados += 1
            self.db.execute(
                "UPDATE arquivo SET ultima_execucao = ? WHERE caminho = ? OR caminho LIKE ? ESCAPE '\\'",
                (self.execucao_id, caminho,
                 caminho.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "!%"))
            return
        base = {"caminho": caminho, "raiz": raiz, "nome": nome, "tamanho": tamanho, "mtime": mtime}
        if extensao in EXTENSOES_SEM_LEITOR:
            self._gravar({**base, "status": "nao_suportado", "motivo": f"{extensao} sem leitor"})
        elif extensao in EXTENSOES_ZIP:
            self._zip(base)
        elif tamanho == 0:
            self._gravar({**base, "status": "vazio", "motivo": "0 byte"})
        else:
            self._texto(base)

    def _texto(self, base: dict) -> None:
        tamanho = base["tamanho"]
        try:
            with open(caminho_longo(base["caminho"]), "rb") as f:
                comeco = f.read(TRECHO)
                if tamanho > 2 * TRECHO:
                    f.seek(-TRECHO, os.SEEK_END)
                    fim = f.read(TRECHO)
                else:
                    fim = comeco
        except OSError as erro:
            self._erro(base["caminho"], "ler_trechos", erro)
            self._gravar({**base, "status": "ilegivel", "motivo": str(erro)})
            return
        d = identificar(comeco[:AMOSTRA_DO_CABECALHO], fim)
        if d["status"] == "ok":
            h = hashlib.sha256(str(tamanho).encode())
            h.update(comeco)
            if fim is not comeco:
                h.update(fim)
            d["impressao"] = h.hexdigest()
            self.c.identificados += 1
        self._gravar({**base, **d})

    def _zip(self, base: dict) -> None:
        caminho = base["caminho"]
        self._gravar({**base, "status": "zip"})
        try:
            with zipfile.ZipFile(caminho_longo(caminho)) as z:
                for info in z.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(EXTENSOES_TEXTO):
                        continue
                    virtual = f"{caminho}!{info.filename}"
                    membro = {**base, "caminho": virtual, "nome": os.path.basename(info.filename),
                              "tamanho": info.file_size}
                    self.c.candidatos += 1
                    try:
                        with z.open(info) as f:
                            comeco = f.read(AMOSTRA_DO_CABECALHO)
                    except (OSError, zipfile.BadZipFile, RuntimeError) as erro:
                        self._erro(virtual, "ler_membro_do_zip", erro)
                        self._gravar({**membro, "status": "ilegivel", "motivo": str(erro)})
                        continue
                    # o fim do membro exige descomprimi-lo inteiro: fica sem verificar
                    d = identificar(comeco, None)
                    if d["status"] == "ok":
                        d["impressao"] = f"zipcrc:{info.CRC:08x}:{info.file_size}"
                        self.c.identificados += 1
                    self._gravar({**membro, **d})
        except (OSError, zipfile.BadZipFile) as erro:
            self._erro(caminho, "abrir_zip", erro)
            self.db.execute("UPDATE arquivo SET status = 'ilegivel', motivo = ? WHERE caminho = ?",
                            (str(erro), caminho))

    def _gravar(self, d: dict) -> None:
        status = d.get("status", "?")
        self.c.por_status[status] = self.c.por_status.get(status, 0) + 1
        self.db.execute(
            f"INSERT INTO arquivo ({','.join(_COLUNAS)}, primeira_execucao, ultima_execucao) "
            f"VALUES ({','.join('?' * len(_COLUNAS))}, ?, ?) ON CONFLICT(caminho) DO UPDATE SET "
            + ", ".join(f"{k} = excluded.{k}" for k in _COLUNAS[1:])
            + ", ultima_execucao = excluded.ultima_execucao",
            [d.get(k) for k in _COLUNAS] + [self.execucao_id, self.execucao_id])

    # ---------- bloco A ----------
    def ler_blocos_a(self, raizes: list[str] | None = None) -> int:
        """Lê até o A990 cada arquivo escolhido que declara A100. Devolve quantos leu.

        Só a versão que `versoes` escolheu para o período: ler a cópia e a
        original substituída custaria um quinto a mais e não mudaria o
        relatório, que só olha a escolhida. `raizes` restringe a quem veio
        delas — para priorizar um compartilhamento sem ler o outro.
        """
        escolhidos = {v["arquivo"] for v in versoes(self.db)
                      if not raizes or any(v["raiz"].startswith(r) for r in raizes)}
        lidos = 0
        for caminho, tamanho, mtime in self.db.execute(
                "SELECT caminho, tamanho, mtime FROM arquivo WHERE tipo = 'efd_contribuicoes' "
                "AND status = 'ok' AND qtd_a100 > 0 AND caminho NOT LIKE '%!%'").fetchall():
            if caminho not in escolhidos:
                continue
            feito = self.db.execute("SELECT tamanho, mtime FROM bloco_a WHERE caminho = ?",
                                    (caminho,)).fetchone()
            if feito and feito[0] == tamanho and abs(feito[1] - mtime) < 1e-3:
                continue
            self._checar_prazo()
            try:
                r = ler_bloco_a(caminho)
            except OSError as erro:
                self._erro(caminho, "ler_bloco_a", erro)
                continue
            self.db.execute(
                "INSERT OR REPLACE INTO bloco_a VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (caminho, tamanho, mtime, r.a100_saida, r.a100_saida_tributada, r.a100_entrada,
                 r.a100_cancelado, r.saidas_sem_iss, str(r.vl_doc_saida), str(r.vl_iss_saida),
                 str(r.vl_pis_saida), str(r.vl_cofins_saida),
                 None if r.a990_confere is None else int(r.a990_confere), r.bytes_lidos,
                 round(r.segundos, 3)))
            self.db.commit()
            lidos += 1
        return lidos


@dataclass
class BlocoA:
    a100_saida: int = 0
    a100_saida_tributada: int = 0
    a100_entrada: int = 0
    a100_cancelado: int = 0
    saidas_sem_iss: int = 0
    vl_doc_saida: Decimal = Decimal(0)
    vl_iss_saida: Decimal = Decimal(0)
    vl_pis_saida: Decimal = Decimal(0)
    vl_cofins_saida: Decimal = Decimal(0)
    a990_confere: bool | None = None
    bytes_lidos: int = 0
    segundos: float = 0.0


def _valor(bruto: str) -> Decimal:
    texto = (bruto or "").strip()
    if not texto:
        return Decimal(0)
    try:
        return Decimal(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except InvalidOperation:
        log.warning("valor ilegível no A100", extra={"valor": texto[:20]})
        return Decimal(0)


_A100 = {n: i for i, n in enumerate(nomes_dos_campos("A100"))}
# COD_SIT 02 é documento cancelado; 03 e 04, cancelamento extemporâneo e denegado
_CANCELADO = {"02", "03", "04", "05"}


def ler_bloco_a(caminho: str) -> BlocoA:
    """Resume os A100 do arquivo, parando no A990.

    Saída tributada usa o mesmo critério do 933: IND_OPER = 1 e PIS ou COFINS
    efetivamente pago. É a contagem que diz se o cliente tem a tese; o valor
    a recuperar continua sendo do 933.
    """
    r = BlocoA()
    aberto = caminho_longo(caminho)
    codificacao = codificacao_de(aberto)
    linhas_do_bloco = 0
    t0 = time.perf_counter()

    def campo(c: list[str], nome: str) -> str:
        i = _A100[nome]
        return c[i] if i < len(c) else ""

    with open(aberto, "rb", buffering=BUFFER_DE_REDE) as f:
        for linha in f:
            r.bytes_lidos += len(linha)
            reg = registro_de(linha)
            if reg is None:
                continue
            if reg[:1] == b"A":
                linhas_do_bloco += 1
            elif reg[:1] not in (b"0",):
                # passou do bloco A sem A990: arquivo fora de ordem; para assim mesmo
                log.warning("bloco A sem A990", extra={"arquivo": os.path.basename(caminho),
                                                       "registro": reg.decode("ascii", "replace")})
                break
            if reg == b"A990":
                c = linha.decode(codificacao, errors="replace").rstrip("\r\n")[1:-1].split("|")
                r.a990_confere = len(c) > 1 and c[1].isdigit() and int(c[1]) == linhas_do_bloco
                break
            if reg != b"A100":
                continue
            c = linha.decode(codificacao, errors="replace").rstrip("\r\n")[1:-1].split("|")
            if campo(c, "COD_SIT") in _CANCELADO:
                r.a100_cancelado += 1
                continue
            if campo(c, "IND_OPER") != "1":
                r.a100_entrada += 1
                continue
            r.a100_saida += 1
            pis, cofins = _valor(campo(c, "VL_PIS")), _valor(campo(c, "VL_COFINS"))
            iss = _valor(campo(c, "VL_ISS"))
            if pis > 0 or cofins > 0:
                r.a100_saida_tributada += 1
                r.vl_doc_saida += _valor(campo(c, "VL_DOC"))
                r.vl_iss_saida += iss
                r.vl_pis_saida += pis
                r.vl_cofins_saida += cofins
                if iss == 0:
                    # o ISS existe, só não está no SPED: está na NFS-e (ver o 933)
                    r.saidas_sem_iss += 1
    r.segundos = time.perf_counter() - t0
    log.info("bloco A lido", extra={"arquivo": os.path.basename(caminho), "mb": round(r.bytes_lidos / 2**20, 1),
                                    "saidas": r.a100_saida, "a990_confere": r.a990_confere,
                                    "segundos": round(r.segundos, 2)})
    return r


# ---------- versões e relatório ----------
def versoes(db: sqlite3.Connection) -> list[dict]:
    """Qual arquivo vale para cada CNPJ × período. Nunca soma versões.

    `unica` e `copias_identicas` têm um conteúdo só; `retificadora_unica` é a
    original (ou nenhuma) mais uma retificadora; `revisao` é mais de um
    conteúdo do mesmo tipo de escrituração — vai a quem transmitiu, com a
    mais nova pelo carimbo do nome como sugestão.
    """
    grupos: dict[tuple, list] = defaultdict(list)
    for linha in db.execute(
            "SELECT cnpj, dt_ini, caminho, nome, tipo_escrit, impressao, completo, raiz, nome_empresa "
            "FROM arquivo WHERE tipo = 'efd_contribuicoes' AND status = 'ok'"):
        grupos[(linha[0], linha[1])].append(linha)
    saida = []
    for (cnpj, inicio), arquivos in sorted(grupos.items()):
        por_conteudo: dict[str, list] = defaultdict(list)
        for a in arquivos:
            por_conteudo[a[5]].append(a)
        # o representante de cada conteúdo é o de caminho menor: estável entre rodadas
        conteudos = [min(v, key=lambda a: a[2]) for v in por_conteudo.values()]
        retificadoras = [a for a in conteudos if a[4] == "1"]
        if len(conteudos) == 1:
            situacao = "copias_identicas" if len(arquivos) > 1 else "unica"
            escolhido = conteudos[0]
        elif len(retificadoras) == 1:
            situacao, escolhido = "retificadora_unica", retificadoras[0]
        else:
            situacao = "revisao"
            candidatos = retificadoras or conteudos
            com_carimbo = [a for a in candidatos if carimbo_do_nome(a[3])]
            escolhido = (max(com_carimbo, key=lambda a: carimbo_do_nome(a[3])) if com_carimbo
                         else min(candidatos, key=lambda a: a[2]))
        if escolhido[6] == 0 and situacao != "revisao":
            situacao = "incompleto"
        saida.append({
            "cnpj": cnpj, "dt_ini": inicio, "situacao": situacao, "arquivo": escolhido[2],
            "raiz": escolhido[7], "nome_empresa": escolhido[8], "arquivos": len(arquivos),
            "conteudos": len(conteudos), "copias_redundantes": len(arquivos) - len(conteudos),
        })
    return saida


def _meses_ausentes(meses: set[str]) -> list[str]:
    primeiro, ultimo = min(meses), max(meses)
    ano, mes = int(primeiro[:4]), int(primeiro[5:7])
    faltam = []
    while f"{ano:04d}-{mes:02d}" <= ultimo:
        if f"{ano:04d}-{mes:02d}" not in meses:
            faltam.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return faltam


def triagem(db: sqlite3.Connection) -> list[dict]:
    """Uma linha por CNPJ, da versão escolhida de cada período, em ordem de potencial."""
    por_cnpj: dict[str, list[dict]] = defaultdict(list)
    for v in versoes(db):
        por_cnpj[v["cnpj"]].append(v)
    contagem = {c: (a100, a170) for c, a100, a170 in
                db.execute("SELECT caminho, qtd_a100, qtd_a170 FROM arquivo")}
    bloco = {r[0]: r for r in db.execute(
        "SELECT caminho, a100_saida_tributada, vl_doc_saida, vl_iss_saida, saidas_sem_iss, a990_confere "
        "FROM bloco_a")}
    linhas = []
    for cnpj, periodos in por_cnpj.items():
        meses = {p["dt_ini"][:7] for p in periodos}
        com_a100 = [p for p in periodos if (contagem[p["arquivo"]][0] or 0) > 0]
        sem_contagem = sum(1 for p in periodos if contagem[p["arquivo"]][0] is None)
        lidos = [bloco[p["arquivo"]] for p in com_a100 if p["arquivo"] in bloco]
        tributadas = sum(b[1] for b in lidos)
        linhas.append({
            "cnpj": cnpj, "nome_empresa": periodos[0]["nome_empresa"], "pasta": periodos[0]["raiz"],
            "primeira_competencia": min(meses), "ultima_competencia": max(meses),
            "competencias": len(meses), "competencias_ausentes": ",".join(_meses_ausentes(meses)),
            "arquivos": sum(p["arquivos"] for p in periodos),
            "copias_redundantes": sum(p["copias_redundantes"] for p in periodos),
            "periodos_em_revisao": ",".join(p["dt_ini"][:7] for p in periodos if p["situacao"] == "revisao"),
            "periodos_incompletos": ",".join(p["dt_ini"][:7] for p in periodos if p["situacao"] == "incompleto"),
            "periodos_sem_contagem_9900": sem_contagem,
            "competencias_com_a100": ",".join(sorted(p["dt_ini"][:7] for p in com_a100)),
            "a100_declarados": sum(contagem[p["arquivo"]][0] or 0 for p in periodos),
            "a170_declarados": sum(contagem[p["arquivo"]][1] or 0 for p in periodos),
            "bloco_a_lido": f"{len(lidos)}/{len(com_a100)}",
            "a100_saida_tributada": tributadas if lidos else "",
            "vl_doc_saida_tributada": str(sum((Decimal(b[2]) for b in lidos), Decimal(0))) if lidos else "",
            "vl_iss_saida_no_sped": str(sum((Decimal(b[3]) for b in lidos), Decimal(0))) if lidos else "",
            "saidas_sem_iss_no_sped": sum(b[4] for b in lidos) if lidos else "",
            "a990_nao_confere": sum(1 for b in lidos if b[5] == 0),
        })

    def prioridade(l: dict):
        iss = Decimal(l["vl_iss_saida_no_sped"] or 0)
        return (-iss, -(l["a100_saida_tributada"] or 0), -l["a100_declarados"])

    return sorted(linhas, key=prioridade)
