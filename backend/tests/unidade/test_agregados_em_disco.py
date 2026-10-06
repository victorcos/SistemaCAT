"""Os agregados da EFD gravados em disco, e lidos de volta.

Existem porque ler os SPED desta casa custa uma hora, e a tese seguinte precisa
dos mesmos números. O que o teste cobra é a ida e a volta sem perda — e, em
especial, que o registro **sem linha de documento** sobreviva: é justamente ele
(C601, D350 e companhia) que a tese precisa contar para avisar que ficou
receita de fora.

Desde 06/10/2026 o **bloco M** vai junto, e a ida e a volta dele é cobrada aqui
pelo mesmo motivo: sem os ajustes do M220/M620 a tese soma a contribuição bruta
dos grupos, e sem o M200/M600 ela não sabe quanto do débito virou DARF e quanto
foi quitado com crédito. Os dois buracos apareceram numa base real, como um
"excluído da base" maior que a contribuição escriturada.
"""

from __future__ import annotations

from cat.infraestrutura.gestao.agregados import gravar, ler
from cat.infraestrutura.gestao.modelos import ApuracaoEFD

CNPJ = "44000007002122"


def _apuracao(**campos) -> ApuracaoEFD:
    base = dict(arquivo="C:/base/contrib_202109.txt", file_hash="h", tamanho=1,
                cnpj=CNPJ, periodo="2021-09")
    base.update(campos)
    return ApuracaoEFD(**base)


class TestOBlocoM:
    """A apuração que o cliente declarou, que até 06/10/2026 ficava de fora."""

    # o M210 do PIS como o arquivo escreve: campos vazios no meio, e é assim
    # que têm de voltar — um "" virando ausente desloca todo o resto do leiaute
    M210 = ["M210", "01", "1000000", "1000000", "", "", "1000000", "1,65",
            "", "", "16500", "", "500", "", "", "16000"]
    M200 = ["M200", "16000", "4000", "0", "12000", "0", "0", "12000",
            "0", "0", "0", "0", "12000"]

    def test_os_registros_voltam_iguais_e_na_ordem(self, tmp_path):
        registros = {"M200": [self.M200],
                     "M210": [self.M210, ["M210", "02"] + self.M210[2:]]}
        gravar([_apuracao(registros=registros)], str(tmp_path))

        (voltou,) = ler(str(tmp_path))

        assert voltou.registros == registros, "campo vazio e ordem inclusive"

    def test_o_campo_vazio_no_fim_nao_some(self, tmp_path):
        """`"a|b|"` e `"a|b"` são leiautes diferentes: o último campo existe e
        está vazio. Perder isso desalinharia a leitura de quem contar posições."""
        registros = {"M400": [["M400", "04", "1000", "", ""]]}
        gravar([_apuracao(registros=registros)], str(tmp_path))

        (voltou,) = ler(str(tmp_path))

        assert voltou.registros["M400"][0] == ["M400", "04", "1000", "", ""]

    def test_os_ajustes_voltam_somados_por_codigo(self, tmp_path):
        ajustes = {("M220", "0", "01"): 150_000, ("M620", "1", "02"): -47_350,
                   ("M110", "0", "03"): 900}
        gravar([_apuracao(ajustes=ajustes)], str(tmp_path))

        (voltou,) = ler(str(tmp_path))

        assert voltou.ajustes == ajustes, "o negativo é redutor, e tem de sobreviver"

    def test_arquivo_so_com_bloco_m_nao_some_da_lista(self, tmp_path):
        """Um SPED sem documento que a leitura cubra existe só aqui. Se apenas
        os documentos criassem o agregado, ele sumiria com a apuração dentro."""
        gravar([_apuracao(documentos={}, contagens={},
                          registros={"M200": [self.M200]})], str(tmp_path))

        (voltou,) = ler(str(tmp_path))

        assert voltou.registros["M200"] == [self.M200]

    def test_agregado_gravado_antes_da_mudanca_volta_sem_bloco_m(self, tmp_path):
        """Compatibilidade: pasta de execução antiga não tem os dois parquets
        novos. Volta sem bloco M — que é o que as teses viam — em vez de quebrar."""
        import os

        gravar([_apuracao(
            documentos={("PIS", "C170", "S", "01", "5102", "", "1,65"): [10, 10, 1, 0, 1]},
            registros={"M200": [self.M200]}, ajustes={("M220", "0", "01"): 1},
        )], str(tmp_path))
        os.remove(tmp_path / "apuracao_efd.parquet")
        os.remove(tmp_path / "ajustes_efd.parquet")

        (voltou,) = ler(str(tmp_path))

        assert voltou.documentos, "os documentos continuam vindo"
        assert voltou.registros == {} and voltou.ajustes == {}

    def test_dois_arquivos_nao_misturam_a_apuracao(self, tmp_path):
        """Cada competência tem o seu M200. Misturá-los somaria débito de meses
        diferentes — e é o tipo de erro que passa despercebido num total."""
        janeiro = _apuracao(periodo="2021-01", arquivo="C:/base/a.txt",
                            registros={"M200": [["M200", "100"]]})
        fevereiro = _apuracao(periodo="2021-02", arquivo="C:/base/b.txt",
                              registros={"M200": [["M200", "200"]]})
        gravar([janeiro, fevereiro], str(tmp_path))

        voltaram = {a.periodo: a for a in ler(str(tmp_path))}

        assert voltaram["2021-01"].registros["M200"] == [["M200", "100"]]
        assert voltaram["2021-02"].registros["M200"] == [["M200", "200"]]


def test_ida_e_volta_preserva_chave_e_somas(tmp_path):
    documentos = {
        ("PIS", "C170", "S", "01", "5102", "", "1,65"): [1000, 900, 15, 0, 3],
        ("COFINS", "C170", "S", "01", "5102", "", "7,60"): [1000, 900, 68, 0, 3],
        ("PIS", "C191", "E", "50", "1102", "01", "1,65"): [500, 500, 8, 2, 1],
    }
    gravar([_apuracao(documentos=documentos, contagens={"C170": 3})], str(tmp_path))

    (voltou,) = ler(str(tmp_path))

    assert voltou.cnpj == CNPJ and voltou.periodo == "2021-09"
    assert voltou.documentos == documentos


def test_registro_sem_documento_sobrevive(tmp_path):
    """C601 não vira linha de documento — e é o que a tese precisa avisar."""
    gravar([_apuracao(
        documentos={("PIS", "C170", "S", "01", "5102", "", "1,65"): [10, 10, 1, 0, 1]},
        contagens={"C170": 1, "C601": 12, "D350": 3},
    )], str(tmp_path))

    (voltou,) = ler(str(tmp_path))

    assert voltou.contagens["C601"] == 12
    assert voltou.contagens["D350"] == 3


def test_arquivo_que_so_tem_registro_de_fora_nao_some(tmp_path):
    """Um SPED sem nenhum documento lido ainda precisa aparecer para a tese."""
    gravar([_apuracao(documentos={}, contagens={"C601": 7})], str(tmp_path))

    (voltou,) = ler(str(tmp_path))

    assert voltou.documentos == {}
    assert voltou.contagens == {"C601": 7}


def test_varios_arquivos_nao_se_misturam(tmp_path):
    um = _apuracao(documentos={("PIS", "C170", "S", "01", "5102", "", "1,65"): [1, 1, 1, 0, 1]})
    outro = _apuracao(arquivo="C:/base/contrib_202110.txt", periodo="2021-10",
                      documentos={("PIS", "C175", "S", "01", "5405", "", "1,65"): [2, 2, 2, 0, 1]})
    gravar([um, outro], str(tmp_path))

    voltaram = sorted(ler(str(tmp_path)), key=lambda a: a.periodo)

    assert [a.periodo for a in voltaram] == ["2021-09", "2021-10"]
    assert list(voltaram[0].documentos)[0][1] == "C170"
    assert list(voltaram[1].documentos)[0][1] == "C175"


def test_pasta_sem_agregado_volta_vazio(tmp_path):
    """Quem chama decide o que fazer; o que não pode é parecer base zerada."""
    assert ler(str(tmp_path)) == []


def test_o_mesmo_arquivo_gravado_duas_vezes_conta_uma_e_nao_em_silencio(tmp_path, caplog):
    """Aconteceu na base da empresa 16: o mesmo SPED entrou duas vezes no lote.

    Contar as duas somaria a competência inteira de novo — foram R$ 203.600,56
    a mais na tese. Ficar com uma é o certo; fazê-lo calado, não.
    """
    documentos = {("PIS", "C170", "S", "01", "5102", "", "1,65"): [100, 100, 2, 0, 1]}
    dobrado = _apuracao(documentos=documentos, contagens={"C170": 1})

    gravar([dobrado, dobrado], str(tmp_path))
    with caplog.at_level("WARNING"):
        (voltou,) = ler(str(tmp_path))

    assert voltou.documentos == documentos
    assert "entrou duas vezes" in caplog.text
