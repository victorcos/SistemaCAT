"""Duas condições previsíveis que o motor devolvia como "falha não tratada".

Em 14/10/2026, no mesmo dia e na mesma máquina:

* o disco de trabalho chegou a zero byte e a planilha estourou no meio da
  escrita (`OSError: [Errno 28]`). Virou 500 sem mensagem, a conexão do
  download caiu, e o navegador anunciou **"verifique a conexão com a
  Internet"** — meia hora procurando defeito de rede que não existia;
* duas telas pediram o mesmo resumo ao mesmo tempo, os dois pedidos
  escolheram o mesmo rascunho (o PID, que é igual para os dois) e o segundo
  morreu com `PermissionError` na **limpeza**, escondendo do log o erro que a
  causou.

Nenhuma das duas é exceção inesperada. O que estes testes guardam é que elas
cheguem à tela com o próprio nome.
"""

from __future__ import annotations

import errno
import glob
import os
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.aplicacao.casos_de_uso.planilhas import (
    FOLGA_MINIMA,
    PlanilhaRecusada,
    espaco_necessario,
    espaco_que_acaba,
    exigir_espaco,
)
from cat.infraestrutura.analitico.rascunho import (
    apagar,
    ja_vale,
    materializando,
    modificado_em,
    nome_provisorio,
)

GB = 1024**3


def _disco(livre: int):
    """O que `shutil.disk_usage` devolve, com o livre que o teste quer."""
    return type("Uso", (), {"free": livre})()


@pytest.fixture
def parquet(tmp_path):
    caminho = str(tmp_path / "origem.parquet")
    pq.write_table(pa.table({"a": list(range(1000)), "b": ["x"] * 1000}), caminho)
    return caminho


class TestORascunho:
    def test_cada_chamada_ganha_um_nome_so_dela(self, tmp_path):
        """O que o PID não dava: dois pedidos no mesmo processo colidiam."""
        alvo = str(tmp_path / "resumo.parquet")
        nomes = {nome_provisorio(alvo) for _ in range(100)}
        assert len(nomes) == 100
        assert all(n.startswith(alvo) and n.endswith(".parcial") for n in nomes)

    def test_promove_ao_nome_final_quando_dá_certo(self, tmp_path):
        alvo = str(tmp_path / "resumo.parquet")
        with materializando(alvo) as parcial:
            assert parcial != alvo and not os.path.exists(alvo)
            with open(parcial, "w", encoding="utf-8") as f:
                f.write("pronto")
        assert open(alvo, encoding="utf-8").read() == "pronto"
        assert os.listdir(tmp_path) == ["resumo.parquet"]      # nada de rascunho sobrando

    def test_falha_nao_deixa_nome_final_nem_rascunho(self, tmp_path):
        """Meio arquivo com o nome certo é pior que arquivo nenhum: quem lê não
        vê erro, vê linha faltando."""
        alvo = str(tmp_path / "resumo.parquet")
        with pytest.raises(ZeroDivisionError), materializando(alvo) as parcial:
            with open(parcial, "w", encoding="utf-8") as f:
                f.write("pela metade")
            1 / 0
        assert os.listdir(tmp_path) == []

    def test_dois_blocos_ao_mesmo_tempo_nao_se_atrapalham(self, tmp_path):
        """O caso real: duas telas pedindo o mesmo resumo do mesmo trabalho."""
        alvo = str(tmp_path / "resumo.parquet")
        with materializando(alvo) as um, materializando(alvo) as outro:
            assert um != outro
            for caminho, texto in ((um, "primeiro"), (outro, "segundo")):
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(texto)
        # o último a sair é o que fica, e nenhum dos dois quebrou
        assert open(alvo, encoding="utf-8").read() == "primeiro"

    def test_apagar_o_que_nao_dá_para_apagar_nao_derruba_ninguem(self, tmp_path):
        """Rascunho preso é lixo, não defeito — e a limpeza não pode virar a
        falha que aparece no log no lugar da verdadeira."""
        apagar(str(tmp_path / "nunca-existiu.parcial"))
        with patch("os.remove", side_effect=PermissionError("WinError 5")):
            apagar(str(tmp_path / "preso.parcial"))


class TestOEspacoEmDisco:
    def test_a_conta_cresce_com_as_linhas_e_o_xlsx_pesa_mais(self, parquet):
        xlsx = espaco_necessario(parquet, "xlsx")
        csv = espaco_necessario(parquet, "csv")
        assert xlsx > csv > FOLGA_MINIMA
        # 1.000 linhas: o que manda é o chão, não a conta
        assert xlsx < FOLGA_MINIMA * 1.01

    def test_sem_metadado_legivel_fica_so_o_chao(self, tmp_path):
        """Não se adivinha o tamanho do que não dá para ler — e recusar por
        isso seria recusar por não saber."""
        quebrado = str(tmp_path / "quebrado.parquet")
        open(quebrado, "wb").write(b"isto nao e parquet")
        assert espaco_necessario(quebrado, "xlsx") == FOLGA_MINIMA

    def test_recusa_antes_de_escrever_dizendo_quanto_falta(self, parquet, tmp_path):
        with patch("shutil.disk_usage", return_value=_disco(livre=GB // 2)):
            with pytest.raises(PlanilhaRecusada) as erro:
                exigir_espaco(parquet, str(tmp_path), "xlsx")
        assert erro.value.status == 422
        assert "Sem espaço em disco" in str(erro.value)
        assert "0,5 GB" in str(erro.value)          # o que restava
        assert "2,0 GB" in str(erro.value)          # o que precisava

    def test_com_espaco_de_sobra_nao_atrapalha(self, parquet, tmp_path):
        with patch("shutil.disk_usage", return_value=_disco(livre=500 * GB)):
            exigir_espaco(parquet, str(tmp_path), "xlsx")

    def test_o_disco_que_acaba_no_meio_vira_a_mesma_frase(self, tmp_path):
        """A estimativa erra para os dois lados, e outro processo pode encher o
        disco no meio. Esta é a rede que não depende de adivinhação."""
        with patch("shutil.disk_usage", return_value=_disco(livre=0)):
            with pytest.raises(PlanilhaRecusada) as erro:
                with espaco_que_acaba(str(tmp_path)):
                    raise OSError(errno.ENOSPC, "No space left on device")
        assert erro.value.status == 422
        assert "O disco acabou" in str(erro.value)

    def test_outro_erro_de_disco_continua_subindo(self, tmp_path):
        """Só o disco cheio vira recusa: esconder o resto seria mentir duas vezes."""
        with pytest.raises(PermissionError):
            with espaco_que_acaba(str(tmp_path)):
                raise PermissionError(errno.EACCES, "Acesso negado")


class TestDoisPedidosAoMesmoTempo:
    """O caso real: três pedidos do razão contábil da empresa 24, às 19:30 de
    14/10/2026, materializando o mesmo resumo ao mesmo tempo.

    Nome exclusivo resolveu a colisão na **escrita**. Sobrou a da **troca de
    nome**: no Windows não se renomeia por cima de arquivo que outra thread já
    está lendo, e o terceiro pedido levou `PermissionError [WinError 5]` depois
    de 149 segundos de trabalho.
    """

    def test_a_troca_recusada_com_destino_novo_nao_derruba_o_pedido(self, tmp_path):
        alvo = str(tmp_path / "resumo.parquet")
        with patch("os.replace", side_effect=PermissionError("WinError 5")):
            with materializando(alvo) as meu:
                with open(meu, "w", encoding="utf-8") as f:
                    f.write("o meu")
                # quem chegou antes: destino escrito durante o nosso bloco
                with open(alvo, "w", encoding="utf-8") as f:
                    f.write("o dele")
        assert open(alvo, encoding="utf-8").read() == "o dele"
        assert not list(tmp_path.glob("*.parcial"))

    def test_a_troca_recusada_sem_destino_continua_sendo_erro(self, tmp_path):
        """Esconder isso entregaria ao chamador um caminho que não existe."""
        alvo = str(tmp_path / "resumo.parquet")
        with pytest.raises(PermissionError), \
                patch("os.replace", side_effect=PermissionError("WinError 5")):
            with materializando(alvo) as meu:
                with open(meu, "w", encoding="utf-8") as f:
                    f.write("o meu")
        assert not os.path.exists(alvo)
        assert not list(tmp_path.glob("*.parcial"))

    def test_destino_velho_nao_serve_de_desculpa(self, tmp_path):
        """Arquivo que já estava lá antes do bloco não é de ninguém chegando
        primeiro — é o que se queria substituir."""
        alvo = str(tmp_path / "resumo.parquet")
        with open(alvo, "w", encoding="utf-8") as f:
            f.write("velho")
        os.utime(alvo, (0, 0))                     # bem anterior ao bloco
        with pytest.raises(PermissionError), \
                patch("os.replace", side_effect=PermissionError("WinError 5")):
            with materializando(alvo) as meu:
                with open(meu, "w", encoding="utf-8") as f:
                    f.write("o meu")


class TestOCacheQueOlhaAIdade:
    """A origem pode ser **uma pasta de partes**, e era aí que o cache sumia.

    O razão da apuração de PIS/COFINS é `razao/*.parquet` desde 07/10/2026.
    `os.path.getmtime` não aceita glob, e quem herdou isso perguntava a data ao
    caminho como se fosse arquivo. Dois estragos diferentes pelo mesmo motivo:

    * em `planilhas.precisa_gerar`, o `except OSError` respondia "precisa
      gerar" sempre — uma planilha de 227 milhões de linhas remontada a cada
      clique, com o cache existindo e nunca pegando;
    * em `razao_contabil._resumo`, não havia `except`, e a tela passou a
      devolver "o motor não respondeu" assim que o resumo foi materializado
      pela primeira vez (14/10/2026).
    """

    def _partes(self, tmp_path, quantas: int = 3) -> str:
        pasta = tmp_path / "razao"
        pasta.mkdir()
        for i in range(quantas):
            (pasta / f"parte-{i}.parquet").write_text("x", encoding="utf-8")
        return str(pasta / "*.parquet")

    def test_a_data_de_um_glob_e_a_da_parte_mais_nova(self, tmp_path):
        origem = self._partes(tmp_path)
        partes = sorted(glob.glob(origem))
        for parte in partes:
            os.utime(parte, (1_000, 1_000))
        os.utime(partes[1], (9_000, 9_000))     # a do meio é a mais nova
        assert modificado_em(origem) == 9_000

    def test_derivado_mais_novo_que_todas_as_partes_vale(self, tmp_path):
        origem = self._partes(tmp_path)
        for p in glob.glob(origem):
            os.utime(p, (1_000, 1_000))
        derivado = tmp_path / "resumo.parquet"
        derivado.write_text("pronto", encoding="utf-8")
        os.utime(derivado, (2_000, 2_000))
        assert ja_vale(str(derivado), origem)

    def test_uma_parte_reescrita_invalida_o_derivado_inteiro(self, tmp_path):
        origem = self._partes(tmp_path)
        derivado = tmp_path / "resumo.parquet"
        derivado.write_text("pronto", encoding="utf-8")
        os.utime(derivado, (2_000, 2_000))
        os.utime(sorted(glob.glob(origem))[1], (3_000, 3_000))
        assert not ja_vale(str(derivado), origem)

    def test_glob_sem_nenhuma_parte_nao_vale(self, tmp_path):
        """Origem ilegível responde não: refazer custa tempo, servir material
        velho custa número errado."""
        derivado = tmp_path / "resumo.parquet"
        derivado.write_text("pronto", encoding="utf-8")
        assert not ja_vale(str(derivado), str(tmp_path / "vazio" / "*.parquet"))

    def test_arquivo_unico_continua_funcionando(self, tmp_path):
        """A forma antiga não pode ter regredido: execução velha não se regrava."""
        origem = tmp_path / "razao.parquet"
        origem.write_text("x", encoding="utf-8")
        os.utime(origem, (1_000, 1_000))
        derivado = tmp_path / "resumo.parquet"
        derivado.write_text("pronto", encoding="utf-8")
        os.utime(derivado, (2_000, 2_000))
        assert ja_vale(str(derivado), str(origem))
        os.utime(origem, (3_000, 3_000))
        assert not ja_vale(str(derivado), str(origem))
