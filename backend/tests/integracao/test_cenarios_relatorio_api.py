"""Três cenários de conferência com relatório do cliente, ponta a ponta.

Pedido da operação: "simule o pior cenário, o médio usual e um perfeito". Cada
um passa pelo caminho real — importar a pasta como lote, disparar a
conferência, ler o resumo, baixar as planilhas — com uma base de 200
documentos (120 NF-e e 80 CF-e-SAT) para o número ter cara de trabalho e não
de exemplo.

* **perfeito** — o relatório de movimento traz todas as chaves, limpas, e
  ainda há XML de parte delas. Fecha sem aviso.
* **médio usual** — o relatório cobre a maior parte, algumas chaves vêm com
  "NFe" na frente, há linhas sem chave, notas canceladas na EFD, cinco notas
  no relatório que a EFD não tem, e XML que completa o que o relatório não
  cobre.
* **pior** — o cliente mandou o inventário no lugar do movimento, o movimento
  que mandou teve a chave destruída pelo Excel, e o relatório "bom" é de
  outra filial. Nada casa, e a tela tem de dizer por quê.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.apresentacao.api.routers import conferencia_router
from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql

SENHA = "Sistema2026cat"

# raiz própria deste módulo: a bateria compartilha um banco só
CNPJ = "66778899000186"
RAIZ = "66778899"
OUTRA_FILIAL = "66778899000267"

NFE = 120
CFE = 80

CABECALHO_MOVIMENTO = (
    "Código|Descricao|Código Barras|Trib|Dt Emissão|Número Dcto|Ent|"
    "Qtde;Unitária|Valor|BC ICMS|Valor ICMS|Valor BC ST;Informada|"
    "Valor ST;Informada|Valor FCP ST|CNPJ/CPF|UF|CFOP;Mvto|CST;ICMS|"
    "BC ICMS ST;XML|VR. ICMS ST;XML|ST integral|Chave DFe"
)
CABECALHO_INVENTARIO = (
    "IFIS_UNID_CODIGO|IFIS_PROD_CODIGO|IFIS_PROD_DESCRICAO|IFIS_ESTOQUE|"
    "IFIS_CTFISCAL|IFIS_CTMEDIO|IFIS_DTULTCOMPRA|IFIS_CTEMPRESA|"
    "IFIS_VLRMEDIOUNICMS|IFIS_VLRMEDIOUNICMS_ST_BC|IFIS_VLRMEDIOUNICMS_ST|"
    "IFIS_VLRMEDIOUNFCP_ST|IFIS_ICMSALIQVIGENTE|IFIS_FCPALIQVIGENTE"
)


# ---------------------------------------------------------------------------
# geradores de dado
# ---------------------------------------------------------------------------
def chave(cnpj: str, modelo: str, numero: int) -> str:
    """44 dígitos com o CNPJ do emitente nas posições 7 a 20."""
    corpo = f"35{'2105'}{cnpj}{modelo}{1:03d}{numero:09d}1{numero:08d}"
    assert len(corpo) == 43
    return corpo + "0"


def c100(ch: str, numero: int, situacao: str = "00") -> str:
    return (f"|C100|1|0|F{numero:04d}|55|{situacao}|001|{numero}|{ch}"
            "|01052021|01052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")


def c100_sem_chave(numero: int) -> str:
    # nota modelo 1: não tem chave de acesso
    return (f"|C100|1|0|F{numero:04d}|01|00|001|{numero}|"
            "|01052021|01052021|100,00|2|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|")


def c800(ch: str, numero: int, situacao: str = "00") -> str:
    return (f"|C800|59|{situacao}|{numero}|01052021|2,59|0|0||900001234"
            f"|{ch}|0|2,59|0|0|0|0|")


def item(ch: str, codigo: str, numero: int) -> str:
    return (f"{codigo}|Item {codigo}|789|0705|01/05/21|{numero}|1|1|10|10|0|0|0|0|"
            f"00176231110|SP|1.102|040|0|0|0|{ch}")


def xml_de(ch: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<nfeProc><NFe><infNFe Id="NFe{ch}">'
            f"<emit><CNPJ>{CNPJ}</CNPJ></emit></infNFe></NFe></nfeProc>")


def escrever(pasta, nome: str, linhas: list[str]) -> None:
    (pasta / nome).write_bytes(("\r\n".join(linhas) + "\r\n").encode("latin-1"))


class Base200:
    """200 documentos na EFD: NF-e 1..120 e CF-e 1..80."""

    def __init__(self, canceladas: int = 0, sem_chave: int = 0) -> None:
        self.nfe = {n: chave(CNPJ, "55", n) for n in range(1, NFE + 1)}
        self.cfe = {n: chave(CNPJ, "59", n) for n in range(1, CFE + 1)}
        self.canceladas = set(range(1, canceladas + 1))       # NF-e 1..k
        self.sem_chave = sem_chave

    @property
    def chaves(self) -> list[str]:
        return list(self.nfe.values()) + list(self.cfe.values())

    @property
    def total(self) -> int:
        return NFE + CFE + self.sem_chave

    def efd(self) -> list[str]:
        linhas = [f"|0000|015|0|01052021|31052021|EMPRESA DOS CENARIOS|{CNPJ}||SP"
                  "|123456789012|3550308||||"]
        for n, ch in self.nfe.items():
            linhas.append(c100(ch, n, "02" if n in self.canceladas else "00"))
        for n in range(1, self.sem_chave + 1):
            linhas.append(c100_sem_chave(9000 + n))
        for n, ch in self.cfe.items():
            linhas.append(c800(ch, n))
        return linhas


def relatorio(chaves: list[str], itens_por_nota: int = 2) -> list[str]:
    linhas = [CABECALHO_MOVIMENTO]
    for i, ch in enumerate(chaves, start=1):
        for k in range(itens_por_nota):
            linhas.append(item(ch, f"{100000 + i * 10 + k}", i))
    return linhas


# ---------------------------------------------------------------------------
# infraestrutura da API
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="cenarios_analista", email="cenarios@bms.local",
        nome_exibicao="Analista dos Cenários",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.DEV, cargo=Cargo.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cabecalhos(cliente):
    r = cliente.post("/api/auth/token",
                     data={"username": "cenarios_analista", "password": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def empresa_id(cliente, cabecalhos):
    r = cliente.post("/api/empresas", headers=cabecalhos, json={
        "cnpj_raiz": RAIZ, "cnpj_matriz": CNPJ,
        "razao_social": "EMPRESA DOS CENARIOS", "uf": "SP",
        "inscricao_estadual": "123456789012",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def rodar_na_hora():
    """A tarefa roda dentro da requisição, para o teste não depender de tempo.

    Escopo de módulo, e não de função: as execuções são criadas em fixtures de
    classe, que sobem antes de qualquer fixture de função — com o monkeypatch
    de função, a conferência iria para a fila de verdade e o teste leria
    "rodando".
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(conferencia_router, "disparar",
                   lambda funcao, *a, **k: funcao(*a, **k))
        yield


def _projeto(cliente, cabecalhos, empresa_id, nome: str) -> int:
    r = cliente.post("/api/projetos", headers=cabecalhos, json={
        "empresa_id": empresa_id, "frente": "cat42", "nome": nome,
        "competencia_ini": "2021-05-01", "competencia_fim": "2021-05-01",
        "observacao": None,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _conferir(cliente, cabecalhos, projeto_id: int, pasta: str) -> dict:
    """Importa a pasta, roda a conferência e devolve a execução concluída."""
    r = cliente.post(f"/api/projetos/{projeto_id}/lotes", headers=cabecalhos,
                     json={"pasta": pasta, "observacao": None})
    assert r.status_code == 201, r.text
    r = cliente.post(f"/api/projetos/{projeto_id}/conferencias",
                     headers=cabecalhos)
    assert r.status_code == 202, r.text
    d = cliente.get(f"/api/conferencias/{r.json()['id']}",
                    headers=cabecalhos).json()
    assert d["situacao"] == "concluida", d.get("erro")
    return d


def _planilha(cliente, cabecalhos, execucao_id: int, qual: str, **filtro) -> int:
    """Baixa a planilha e devolve quantas linhas de dado ela tem."""
    import io  # noqa: PLC0415

    import openpyxl  # noqa: PLC0415

    params = "&".join(f"{k}={v}" for k, v in filtro.items())
    r = cliente.get(f"/api/conferencias/{execucao_id}/planilhas/{qual}"
                    + (f"?{params}" if params else ""), headers=cabecalhos)
    assert r.status_code == 200, r.text
    livro = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True)
    return sum(aba.max_row - 1 for aba in livro.worksheets)


def _contar(cliente, cabecalhos, execucao_id: int) -> dict[str, int]:
    return {qual: _planilha(cliente, cabecalhos, execucao_id, qual)
            for qual in ("conferidas", "a-cobrar", "nao-escrituradas")}


def _relatar(nome: str, resumo: dict, planilhas: dict[str, int]) -> None:
    """Sai no terminal com `pytest -s`: é o que se mostra para a operação."""
    print(f"\n=== {nome} ===")
    for campo in ("escriturados", "conferidos", "sem_documento",
                  "sem_documento_cobravel", "nao_escrituradas",
                  "documentos_na_pasta", "cobertura", "origens"):
        print(f"  {campo:24} {resumo[campo]}")
    print(f"  {'planilhas':24} {planilhas}")
    for a in resumo["avisos"]:
        print(f"  aviso: {a}")
    for r in resumo["recusados"]:
        print(f"  recusado: {r}")


# ---------------------------------------------------------------------------
# os três cenários
# ---------------------------------------------------------------------------
class TestCenarioPerfeito:
    @pytest.fixture(scope="class")
    @classmethod
    def execucao(cls, cliente, cabecalhos, empresa_id, tmp_path_factory):
        base = Base200()
        pasta = tmp_path_factory.mktemp("perfeito")
        escrever(pasta, "efd.txt", base.efd())
        escrever(pasta, "movimento.txt", relatorio(base.chaves))
        for n in range(1, 11):                       # XML de dez NF-e
            (pasta / f"{base.nfe[n]}-nfe.xml").write_text(
                xml_de(base.nfe[n]), encoding="utf-8")
        projeto = _projeto(cliente, cabecalhos, empresa_id, "Cenário perfeito")
        return _conferir(cliente, cabecalhos, projeto, str(pasta))

    def test_fecha_sem_aviso(self, cliente, cabecalhos, execucao):
        r = execucao["resumo"]
        planilhas = _contar(cliente, cabecalhos, execucao["id"])
        _relatar("PERFEITO", r, planilhas)

        assert r["escriturados"] == 200
        assert r["conferidos"] == 200
        assert r["sem_documento"] == 0
        assert r["nao_escrituradas"] == 0
        assert r["cobertura"] == 1.0
        assert r["avisos"] == []
        assert r["recusados"] == []
        assert set(r["origens"]) == {"xml", "gerencial"}
        assert planilhas == {"conferidas": 200, "a-cobrar": 0,
                             "nao-escrituradas": 0}

    def test_o_xml_venceu_onde_havia_os_dois(self, cliente, cabecalhos, execucao):
        # dez notas tinham XML e relatório: dez conferidas pelo XML
        import duckdb  # noqa: PLC0415

        from cat.infraestrutura.repositorios.banco import obter_sessao  # noqa: PLC0415
        from cat.infraestrutura.repositorios.modelos import ExecucaoDB  # noqa: PLC0415

        sessao = next(obter_sessao())
        pasta = sessao.get(ExecucaoDB, execucao["id"]).pasta_de_trabalho
        con = duckdb.connect()
        por_origem = dict(con.execute(
            f"SELECT origem, count(*) FROM read_parquet('{pasta}/conferidos.parquet') "
            "GROUP BY 1").fetchall())
        con.close()
        assert por_origem == {"xml": 10, "gerencial": 190}


class TestCenarioMedioUsual:
    """O que chega de verdade: quase tudo, com sujeira."""

    COBERTAS_PELO_RELATORIO = 170     # das 196 regulares
    COM_PREFIXO_NFE = 6
    LINHAS_SEM_CHAVE = 8
    SO_NO_RELATORIO = 5
    XML_QUE_COMPLETAM = 5             # notas fora do relatório, com XML
    XML_REPETIDOS = 10                # notas no relatório E com XML
    CANCELADAS = 4

    @pytest.fixture(scope="class")
    @classmethod
    def execucao(cls, cliente, cabecalhos, empresa_id, tmp_path_factory):
        base = Base200(canceladas=cls.CANCELADAS)
        pasta = tmp_path_factory.mktemp("medio")
        escrever(pasta, "efd.txt", base.efd())

        # as regulares, na ordem: NF-e 5..120 depois CF-e 1..80
        regulares = ([base.nfe[n] for n in range(cls.CANCELADAS + 1, NFE + 1)]
                     + list(base.cfe.values()))
        no_relatorio = regulares[:cls.COBERTAS_PELO_RELATORIO]
        fora_do_relatorio = regulares[cls.COBERTAS_PELO_RELATORIO:]
        assert len(fora_do_relatorio) == 196 - cls.COBERTAS_PELO_RELATORIO

        sujas = ([f"NFe{ch}" for ch in no_relatorio[:cls.COM_PREFIXO_NFE]]
                 + no_relatorio[cls.COM_PREFIXO_NFE:])
        estranhas = [chave(CNPJ, "55", 5000 + i)
                     for i in range(cls.SO_NO_RELATORIO)]
        linhas = relatorio(sujas + estranhas)
        for i in range(cls.LINHAS_SEM_CHAVE):
            linhas.append(item("", f"{999000 + i}", 8000 + i))
        escrever(pasta, "movimento.txt", linhas)

        for ch in (fora_do_relatorio[:cls.XML_QUE_COMPLETAM]
                   + no_relatorio[-cls.XML_REPETIDOS:]):
            (pasta / f"{ch}-nfe.xml").write_text(xml_de(ch), encoding="utf-8")

        projeto = _projeto(cliente, cabecalhos, empresa_id, "Cenário médio")
        return _conferir(cliente, cabecalhos, projeto, str(pasta))

    def test_os_numeros(self, cliente, cabecalhos, execucao):
        r = execucao["resumo"]
        planilhas = _contar(cliente, cabecalhos, execucao["id"])
        _relatar("MÉDIO USUAL", r, planilhas)

        conferidos = self.COBERTAS_PELO_RELATORIO + self.XML_QUE_COMPLETAM
        assert r["escriturados"] == 200
        assert r["conferidos"] == conferidos                       # 175
        assert r["sem_documento"] == 200 - conferidos              # 25
        assert r["sem_documento_cobravel"] == 200 - conferidos - self.CANCELADAS
        assert r["nao_escrituradas"] == self.SO_NO_RELATORIO
        assert r["documentos_na_pasta"] == conferidos + self.SO_NO_RELATORIO
        assert set(r["origens"]) == {"xml", "gerencial"}
        assert planilhas == {"conferidas": conferidos,
                             "a-cobrar": 200 - conferidos,
                             "nao-escrituradas": self.SO_NO_RELATORIO}

    def test_a_planilha_de_cobranca_filtra_o_que_se_cobra(
        self, cliente, cabecalhos, execucao
    ):
        so_cobrar = _planilha(cliente, cabecalhos, execucao["id"], "a-cobrar",
                              classificacoes="a_cobrar")
        assert so_cobrar == 200 - 175 - self.CANCELADAS               # 21
        so_nfe = _planilha(cliente, cabecalhos, execucao["id"], "a-cobrar",
                           modelos="55")
        so_cfe = _planilha(cliente, cabecalhos, execucao["id"], "a-cobrar",
                           modelos="59")
        assert so_nfe + so_cfe == 25

    def test_a_tela_explica_a_sujeira(self, execucao):
        r = execucao["resumo"]
        # as canceladas ficam na lista, marcadas
        assert any("canceladas, denegadas" in a for a in r["avisos"])
        # o que o relatório traz e a EFD não tem
        assert any("não estão na EFD" in a for a in r["avisos"])
        # as linhas sem chave não somem em silêncio. Aqui o documento está
        # identificado e só falta a chave, que é problema de quem entrega:
        # a nota existe e não tem como cruzar
        [recusado] = r["recusados"]
        assert "movimento.txt" in recusado
        assert (f"{self.LINHAS_SEM_CHAVE} linha(s) de documento identificado "
                "mas sem chave") in recusado
        # e o motivo não é chutado: nada de Excel onde não houve Excel
        assert "Excel" not in recusado
        # e o que NÃO é problema não vira aviso
        assert not any("filiais diferentes" in a for a in r["avisos"])
        assert not any("em dobro" in a for a in r["avisos"])


class TestCenarioPior:
    """Tudo que pode dar errado com o relatório, de uma vez."""

    CANCELADAS = 4
    SEM_CHAVE = 3
    NOTAS_DA_OUTRA_FILIAL = 50

    @pytest.fixture(scope="class")
    @classmethod
    def execucao(cls, cliente, cabecalhos, empresa_id, tmp_path_factory):
        base = Base200(canceladas=cls.CANCELADAS, sem_chave=cls.SEM_CHAVE)
        pasta = tmp_path_factory.mktemp("pior")
        escrever(pasta, "efd.txt", base.efd())

        # (a) mandaram o inventário achando que era o movimento
        escrever(pasta, "inventario.txt", [
            CABECALHO_INVENTARIO,
            "089|117307|Maca|1|0705|10,88|08/03/24|10,88|0|0|0|0|19,5|2",
        ])
        # (b) o movimento passou pelo Excel: toda chave virou "3,52105E+43"
        escrever(pasta, "movimento.txt",
                 relatorio(["3,52105E+43"] * 200, itens_por_nota=2))
        # (c) o relatório que está inteiro é da outra filial
        escrever(pasta, "movimento_filial_02.txt", relatorio(
            [chave(OUTRA_FILIAL, "55", n)
             for n in range(1, cls.NOTAS_DA_OUTRA_FILIAL + 1)]))

        projeto = _projeto(cliente, cabecalhos, empresa_id, "Cenário pior")
        return _conferir(cliente, cabecalhos, projeto, str(pasta))

    def test_nada_casa_e_nada_some(self, cliente, cabecalhos, execucao):
        r = execucao["resumo"]
        planilhas = _contar(cliente, cabecalhos, execucao["id"])
        _relatar("PIOR", r, planilhas)

        total = 200 + self.SEM_CHAVE
        assert r["escriturados"] == total
        assert r["conferidos"] == 0
        assert r["sem_documento"] == total                  # tudo pendente
        assert r["sem_documento_cobravel"] == total - self.CANCELADAS - self.SEM_CHAVE
        assert r["nao_escrituradas"] == self.NOTAS_DA_OUTRA_FILIAL
        assert r["cobertura"] == 0.0
        assert planilhas == {"conferidas": 0, "a-cobrar": total,
                             "nao-escrituradas": self.NOTAS_DA_OUTRA_FILIAL}

    def test_a_tela_diz_por_que(self, execucao):
        r = execucao["resumo"]
        avisos = "\n".join(r["avisos"])
        # o relatório inteiro é de outra filial: é isto, não falta de documento
        assert "filiais diferentes" in avisos
        assert OUTRA_FILIAL in avisos and CNPJ in avisos
        # o Excel comeu as chaves: 400 linhas. Veio algo na coluna que não
        # são 44 dígitos, e é o único caso em que citar o Excel se sustenta
        [recusado] = r["recusados"]
        assert "movimento.txt" in recusado
        assert "400 linha(s) com chave ilegível" in recusado
        assert "Excel" in recusado
        # as 3 sem chave e as 4 canceladas continuam na lista, marcadas
        assert f"{self.SEM_CHAVE} documento(s) da EFD estão sem chave" in avisos
        assert "canceladas, denegadas" in avisos
        # e as 50 da outra filial saíram da análise, com aviso
        assert "50 nota(s) da pasta não estão na EFD" in avisos

    def test_o_inventario_ficou_no_lote_mas_fora_da_conferencia(
        self, cliente, cabecalhos, execucao
    ):
        lotes = cliente.get(f"/api/projetos/{execucao['projeto_id']}/lotes",
                            headers=cabecalhos).json()
        tipos = {c["tipo"]: c["quantidade"] for c in lotes[0]["contagens"]}
        assert tipos.get("gerencial_inventario") == 1
        assert tipos.get("gerencial_movimento") == 2
        # 1 EFD + 2 movimentos lidos; o inventário não entra na conta
        assert execucao["arquivos_totais"] == 3
