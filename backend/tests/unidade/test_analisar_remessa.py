"""A análise da remessa que precede o pré-cadastro da empresa.

O caso que motivou estes testes: uma remessa só de EFD-Contribuições — o
arquivo do trabalho de PIS/COFINS — aparecia na tela como "0 servem à CAT 42",
com um aviso de atenção dizendo que aquilo "serve a outras frentes". Quem ia
cadastrar o trabalho de PIS/COFINS lia como recusa do arquivo.
"""

from cat.aplicacao.casos_de_uso.analisar_remessa import analisar
from cat.infraestrutura.arquivos.remessa import ArquivoDaRemessa

# as mesmas linhas reais usadas em test_sped_cabecalho.py
CONTRIBUICOES = (
    "|0000|006|0|||01062021|30062021|CENTER BOX SUPERMERCADOS LTDA"
    "|11497712000184|CE|2304400||00|2|"
)
ICMS_IPI = (
    "|0000|018|0|01012025|31012025|IRMAOS BOA LTDA|50948371000178||SP"
    "|407048962113|3550308|||A|0|"
)
# a ECD de test_sped_cabecalho.py traz CNPJ fictício, que a análise recusa por
# dígito verificador — aqui ela repete o CNPJ real da linha de Contribuições
ECD = (
    "|0000|LECD|0||01012025|31012025|CENTER BOX SUPERMERCADOS LTDA"
    "|11497712000184|CE|2304400||||"
)


def arquivo(nome: str, primeira_linha: str) -> ArquivoDaRemessa:
    return ArquivoDaRemessa(
        nome=nome, caminho_interno=nome, tamanho=len(primeira_linha),
        primeira_linha=primeira_linha,
    )


class TestRemessaDeContribuicoes:
    """Só EFD-Contribuições: é remessa válida, do trabalho de PIS/COFINS."""

    def analise(self):
        return analisar([arquivo("PISCOFINS_062021.txt", CONTRIBUICOES)])

    def test_o_arquivo_e_lido(self):
        r = self.analise()
        assert r.lidos == 1
        assert r.recusados == []

    def test_atende_piscofins(self):
        assert self.analise().modulos_atendidos == ["piscofins"]

    def test_diz_a_que_trabalho_o_arquivo_serve(self):
        obs = self.analise().observacoes
        assert "1 EFD Contribuições: serve ao trabalho de PIS/COFINS." in obs

    def test_a_falta_da_efd_icms_e_observacao_e_nao_aviso(self):
        r = self.analise()
        assert any("CAT 42" in o for o in r.observacoes)
        # o que sobra em `avisos` é o que pede ação; faltar EFD ICMS/IPI não é
        assert r.avisos == []


class TestRemessaDeIcms:
    def test_atende_icms_e_tambem_piscofins(self):
        """A EFD ICMS/IPI é da CAT 42 e também serve ao PIS/COFINS: é dela que
        sai a exclusão do ICMS da base (Tema 69)."""
        r = analisar([arquivo("EFD_012025.txt", ICMS_IPI)])
        assert r.modulos_atendidos == ["piscofins", "icms"]
        assert r.serve_para_cat == 1
        assert not any("CAT 42" in o for o in r.observacoes)


class TestRemessaMista:
    def test_soma_os_modulos_sem_repetir(self):
        r = analisar([
            arquivo("EFD_012025.txt", ICMS_IPI),
            arquivo("PISCOFINS_062021.txt", CONTRIBUICOES),
            arquivo("ECD_2025.txt", ECD),
        ])
        assert r.modulos_atendidos == ["piscofins", "icms", "irpj_csll"]
        assert len(r.observacoes) == 3  # um por tipo, sem a nota da CAT 42

    def test_empresas_diferentes_continuam_sendo_aviso(self):
        """O que exige decisão do usuário segue em `avisos`."""
        r = analisar([
            arquivo("EFD_012025.txt", ICMS_IPI),
            arquivo("PISCOFINS_062021.txt", CONTRIBUICOES),
        ])
        assert any("empresas diferentes" in a for a in r.avisos)


class TestRemessaVazia:
    def test_sem_arquivo_lido_nao_ha_observacao(self):
        r = analisar([arquivo("leia-me.txt", "isto não é SPED")])
        assert r.lidos == 0
        assert r.observacoes == []
        assert r.modulos_atendidos == []
