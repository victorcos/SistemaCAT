"""O que se baixa da etapa 7: os arquivos, as prévias e a pré-validação.

Os TXT vão em zip — um para o que segue à SEFAZ, outro para as prévias, que
nunca se misturam. As duas planilhas são o índice dos arquivos (com hash, para
conferir a cópia que for para a rede) e as ocorrências da pré-validação.
"""

from __future__ import annotations

from cat.infraestrutura.analitico.arquivo_digital import ENVIO, PREVIA, empacotar
from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

COLUNAS_ARQUIVOS = (
    Coluna("nome", "Arquivo", "texto", 44),
    Coluna("destino", "Destino (envio ou prévia)", "texto", 12),
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "texto", 12),
    Coluna("ressarcimento", "Ressarcimento", "numero", 16),
    Coluna("complemento", "Complemento", "numero", 16),
    Coluna("travas", "O que impede o envio", "texto", 50),
    Coluna("motivos", "Pendências da apuração (etapa 6)", "texto", 50),
    Coluna("linhas", "Linhas", "numero_inteiro", 12),
    Coluna("eletronicos", "Registros 1100", "numero_inteiro", 12),
    Coluna("nao_eletronicos", "Registros 1200", "numero_inteiro", 12),
    Coluna("saldos", "Registros 1050", "numero_inteiro", 12),
    Coluna("itens", "Registros 0200", "numero_inteiro", 12),
    Coluna("participantes", "Registros 0150", "numero_inteiro", 12),
    Coluna("linhas_sem_documento", "Linhas da Ficha 3 sem documento", "numero_inteiro", 14),
    Coluna("erros", "Erros da pré-validação", "numero_inteiro", 12),
    Coluna("avisos", "Avisos da pré-validação", "numero_inteiro", 12),
    Coluna("itens_recompostos", "Itens recompostos", "numero_inteiro", 12),
    Coluna("itens_que_fecham", "Itens que fecham com o 1050", "numero_inteiro", 14),
    Coluna("bytes", "Tamanho (bytes)", "numero_inteiro", 14),
    Coluna("sha256", "SHA-256", "texto", 66),
)

COLUNAS_OCORRENCIAS = (
    Coluna("nome", "Arquivo", "texto", 44),
    Coluna("severidade", "Severidade", "texto", 10),
    Coluna("rotulo", "Regra", "texto", 50),
    Coluna("vezes_no_arquivo", "Vezes no arquivo", "numero_inteiro", 12),
    Coluna("linha", "Linha", "numero_inteiro", 10),
    Coluna("registro", "Registro", "texto", 10),
    Coluna("campo", "Campo", "texto", 14),
    Coluna("item", "Item", "texto", 16),
    Coluna("mensagem", "O que foi achado", "texto", 70),
    Coluna("o_que_fazer", "O que fazer", "texto", 60),
)


COLUNAS_ARQUIVOS_DO_CLIENTE = (
    Coluna("nome", "Arquivo", "texto", 44),
    Coluna("origem", "De onde veio (pasta, zip e membro)", "texto", 70),
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "texto", 12),
    Coluna("repetido", "Repetido (não lido de novo)", "texto", 12),
    Coluna("erros", "Erros da pré-validação", "numero_inteiro", 12),
    Coluna("avisos", "Avisos da pré-validação", "numero_inteiro", 12),
    Coluna("itens_recompostos", "Itens recompostos", "numero_inteiro", 12),
    Coluna("itens_que_fecham", "Itens que fecham com o 1050", "numero_inteiro", 14),
    Coluna("maior_diferenca_de_valor", "Maior diferença de valor no 1050", "numero", 16),
    Coluna("linhas", "Linhas", "numero_inteiro", 12),
    Coluna("eletronicos", "Registros 1100", "numero_inteiro", 12),
    Coluna("nao_eletronicos", "Registros 1200", "numero_inteiro", 12),
    Coluna("saldos", "Registros 1050", "numero_inteiro", 12),
    Coluna("itens", "Registros 0200", "numero_inteiro", 12),
    Coluna("participantes", "Registros 0150", "numero_inteiro", 12),
    Coluna("bytes", "Tamanho (bytes)", "numero_inteiro", 14),
    Coluna("sha256", "SHA-256", "texto", 66),
)


def gerar_arquivos_do_cliente(parquet: str, destino: str, modelos=None, classificacoes=None,
                              formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_ARQUIVOS_DO_CLIENTE, "Arquivos do cliente", formato=formato)


def gerar_arquivos(parquet: str, destino: str, modelos=None, classificacoes=None, formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_ARQUIVOS, "Arquivos digitais", formato=formato)


def gerar_ocorrencias(parquet: str, destino: str, modelos=None, classificacoes=None, formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_OCORRENCIAS, "Pré-validação", formato=formato)


def zip_de_envio(parquet: str, destino: str, modelos=None, classificacoes=None, formato: str = "zip") -> int:
    return empacotar(parquet, destino, ENVIO)


def zip_de_previas(parquet: str, destino: str, modelos=None, classificacoes=None, formato: str = "zip") -> int:
    return empacotar(parquet, destino, PREVIA)
