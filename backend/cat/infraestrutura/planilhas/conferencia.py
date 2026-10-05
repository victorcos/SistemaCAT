"""As três planilhas que saem da conferência.

Regras de Excel desta casa (ARQUITETURA §9), e cada uma existe por um motivo
que já custou retrabalho:

* **acima de 900 mil linhas, quebrar em abas.** O limite do Excel é pouco mais
  de um milhão, e estourar não dá erro: corta o resto em silêncio;
* **memória constante.** A lista de cobrança de uma base grande passa de um
  milhão de linhas; montar tudo em memória antes de gravar derruba o processo;
* **identificador com zero à esquerda vai como texto.** Chave de acesso, CNPJ e
  série viram número e perdem o zero — e chave de 44 dígitos vira notação
  científica, que é pior: parece certa e não é;
* **valor e data vão tipados**, senão não se soma nem se monta dinâmica, e o
  cliente que recebe a cobrança não consegue conferir o total.

**CSV é a outra saída, e serve a outra coisa.** O xlsx é para abrir e ler; o
CSV é para carregar em outro lugar — DuckDB, Power BI, banco, o sistema do
cliente — e para quando a lista passa do que o Excel aguenta, já que CSV não
tem limite de linha nem precisa quebrar em aba.

O CSV sai com `;` e vírgula decimal, que é o que o Excel em português espera,
e com BOM, senão o acento vira lixo. O que ele **não** faz é fingir tipo para
agradar o Excel: a chave de acesso vai como os 44 dígitos que ela é. Abrir o
CSV com dois cliques no Excel transforma isso em notação científica — é
exatamente o defeito que este projeto passou uma manhã diagnosticando num
relatório de cliente. Quem precisa abrir no Excel baixa o xlsx, que é imune;
quem precisa carregar em ferramenta baixa o CSV, que é correto.
"""

from __future__ import annotations

import csv
import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import xlsxwriter

from cat.log import obter_log

log = obter_log(__name__)

# O cabeçalho de todas as planilhas do projeto, no padrão do papel de trabalho
# da CAT 42 (pedido do Victor, 18/09/2026): faixa azul-marinho, Arial 10 em
# negrito branco, centralizado e com quebra de linha. Fica aqui, e não em cada
# gerador, porque planilha com cara diferente a cada etapa é o que o cliente
# percebe primeiro.
AZUL_DO_CABECALHO = "#001E50"
FONTE_DA_PLANILHA = "Arial"
CORPO_DA_FONTE = 10
ESTILO_DO_CABECALHO = {
    "bold": True, "bg_color": AZUL_DO_CABECALHO, "font_color": "#FFFFFF",
    "font_name": FONTE_DA_PLANILHA, "font_size": CORPO_DA_FONTE, "border": 1,
    "align": "center", "valign": "vcenter", "text_wrap": True,
}
# a altura da faixa de títulos: o do papel de trabalho tem 51, e é o que cabe
# em três linhas de texto sem cortar
ALTURA_DO_CABECALHO = 51

LIMITE_POR_ABA = 900_000
LINHAS_POR_LEITURA = 50_000

FORMATOS = ("xlsx", "csv")

# ; e vírgula decimal: é o que o Excel em português entende sem perguntar nada.
# Com vírgula de separador, todo valor com centavo quebraria a coluna.
SEPARADOR_CSV = ";"

# casas decimais por tipo, para o CSV não inventar precisão nem esconder fração
CASAS = {"numero": 2, "quantidade": 5, "numero_inteiro": 0}


@dataclass(frozen=True)
class Coluna:
    campo: str
    titulo: str
    tipo: str = "texto"      # texto | numero | quantidade | numero_inteiro | data
    largura: int = 16
    # o bloco do cabeçalho ("Dados Gerais", "Saídas") e o número do campo no
    # leiaute da CAT 42 ("1", "20"). Colunas seguidas com o mesmo bloco
    # viram uma faixa mesclada acima dos títulos; o número vai numa linha
    # abaixo deles. Vazios nos dois, o cabeçalho é de uma linha só, como era.
    bloco: str = ""
    numero: str = ""

    @property
    def titulo_no_csv(self) -> str:
        """No CSV não há faixa nem linha de número: tudo vira um título só."""
        return f"{self.titulo} ({self.numero})" if self.numero else self.titulo

    @property
    def numero_na_planilha(self) -> str:
        return f"({self.numero})" if self.numero else ""


COLUNAS_SEM_DOCUMENTO = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "data", 13),
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("modelo", "Modelo", "texto", 9),
    Coluna("serie", "Série", "texto", 8),
    Coluna("numero", "Número", "texto", 12),
    Coluna("data", "Emissão", "data", 12),
    Coluna("valor", "Valor do documento", "numero", 18),
    Coluna("operacao", "Operação", "texto", 11),
    Coluna("emitente", "Emitente", "texto", 14),
    Coluna("participante", "Cód. participante", "texto", 18),
    Coluna("situacao", "Situação", "texto", 10),
    # quantas vezes a chave apareceu na EFD. 1 é o normal; 2 pode ser a nota
    # escriturada em duas filiais (legítimo) ou o mesmo arquivo importado duas
    # vezes (não). Sem esta coluna, quem baixa não tinha como ver a diferença.
    #
    # É contagem e sai como "1,00", porque o tipo é "numero" e não
    # "numero_inteiro". Fica assim de propósito: a planilha já circula desta
    # forma e trocar o tipo mudaria o arquivo que o pessoal usa. Decidido em
    # 12/09/2026 — se for para mudar um dia, muda nas duas listas ao mesmo
    # tempo, aqui e em COLUNAS_CONFERIDAS.
    Coluna("ocorrencias", "Ocorrências na EFD", "numero", 12),
    # o que fazer com a linha. Vem primeiro na ordenação do parquet, então
    # quem abre a planilha já cai no que há para cobrar
    Coluna("classificacao", "Classificação", "texto", 30),
    Coluna("arquivo_efd", "Arquivo da EFD", "texto", 34),
)

# a lista positiva: escriturada E com documento. As mesmas colunas da
# pendência, sem classificação (quem casou, casou) e com de onde veio o
# documento — é o que se abre quando alguém questiona a nota
COLUNAS_CONFERIDAS = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "data", 13),
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("modelo", "Modelo", "texto", 9),
    Coluna("serie", "Série", "texto", 8),
    Coluna("numero", "Número", "texto", 12),
    Coluna("data", "Emissão", "data", 12),
    Coluna("valor", "Valor do documento", "numero", 18),
    Coluna("operacao", "Operação", "texto", 11),
    Coluna("emitente", "Emitente", "texto", 14),
    Coluna("participante", "Cód. participante", "texto", 18),
    Coluna("situacao", "Situação", "texto", 10),
    # "numero" e não "numero_inteiro" de propósito: ver a nota em
    # COLUNAS_SEM_DOCUMENTO. As duas listas mudam juntas ou não mudam.
    Coluna("ocorrencias", "Ocorrências na EFD", "numero", 12),
    Coluna("origem", "Origem do documento", "texto", 20),
    Coluna("arquivo_do_documento", "Arquivo do documento", "texto", 44),
    Coluna("arquivo_efd", "Arquivo da EFD", "texto", 34),
)

COLUNAS_NAO_ESCRITURADAS = (
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("origem", "Origem", "texto", 20),
    Coluna("arquivo", "Arquivo", "texto", 44),
)

_ROTULO_SITUACAO = {
    "00": "Regular", "01": "Regular, extemporâneo", "02": "Cancelado",
    "03": "Cancelado, extemporâneo", "04": "Denegado",
    "05": "Numeração inutilizada", "06": "Complementar",
    "07": "Complementar, extemporâneo", "08": "Regime especial",
}
_ROTULO_ORIGEM = {"xml": "XML", "gerencial": "Relatório do cliente"}
_ROTULO_OPERACAO = {"entrada": "Entrada", "saida": "Saída"}
_ROTULO_EMITENTE = {"propria": "Emissão própria", "terceiros": "Terceiros"}
_ROTULO_CLASSIFICACAO = {
    "a_cobrar": "A cobrar do cliente",
    "sem_documento_a_pedir": "Cancelada, denegada ou inutilizada",
    "sem_chave": "Sem chave — conferir à mão",
    # as marcas que o histórico de movimentação carrega
    "conferido": "Documento conferido",
    "pendente": "Documento pendente na conferência",
    "nao_conferido": "Sem conferência",
}

# a apuração do ICMS suportado: de onde veio o valor e, se não veio, por quê
_ROTULO_FONTE = {
    "documento": "Destacado na entrada",
    "informado_pelo_fornecedor": "Informado pelo fornecedor",
    "base_e_aliquota": "Reconstruído por base e alíquota",
    "nao_apuravel": "Não apurável",
}
_ROTULO_PENDENCIA = {
    "sem_o_que_apurar": "Sem o que apurar",
    "falta_dado": "Falta dado",
}

_TRADUCOES = {
    "fonte": _ROTULO_FONTE,
    "pendencia": _ROTULO_PENDENCIA,
    "situacao": _ROTULO_SITUACAO,
    "origem": _ROTULO_ORIGEM,
    "operacao": _ROTULO_OPERACAO,
    "emitente": _ROTULO_EMITENTE,
    "classificacao": _ROTULO_CLASSIFICACAO,
}


def gerar(parquet: str, destino: str, colunas: tuple[Coluna, ...],
          titulo_da_aba: str, modelos: frozenset[str] | None = None,
          classificacoes: frozenset[str] | None = None,
          formato: str = "xlsx",
          campo_da_classificacao: str = "classificacao") -> int:
    """Escreve a planilha a partir do parquet. Devolve quantas linhas gravou.

    `modelos` restringe por modelo de documento, e não é detalhe: numa base
    real desta casa, 307.319 dos 321.337 documentos eram NFC-e. Cobrar do
    cliente o XML de cada cupom de consumidor não é trabalho que alguém vá
    fazer, e a planilha inteira perderia serventia por causa do volume.

    `formato` escolhe entre xlsx e csv. O filtro e a tradução de rótulo são os
    mesmos nos dois: é o motivo de as duas saídas morarem aqui, e não em
    módulos separados que fatalmente divergiriam.
    """
    if formato not in FORMATOS:
        raise ValueError(f"formato desconhecido: {formato}")
    if formato == "csv":
        return _gerar_csv(parquet, destino, colunas, modelos, classificacoes,
                          campo_da_classificacao)
    return _gerar_xlsx(parquet, destino, colunas, titulo_da_aba,
                       modelos, classificacoes, campo_da_classificacao)


def _filtradas(parquet: str, modelos: frozenset[str] | None,
               classificacoes: frozenset[str] | None,
               campo: str = "classificacao") -> Iterator[dict]:
    """As linhas do parquet que passam no filtro, em lotes, sem segurar tudo.

    Fica separado porque é a parte que precisa ser idêntica nas duas saídas:
    xlsx e csv filtrando diferente dariam dois totais para a mesma cobrança.
    """
    for lote in pq.ParquetFile(parquet).iter_batches(LINHAS_POR_LEITURA):
        for r in lote.to_pylist():
            if modelos is not None and r.get("modelo") not in modelos:
                continue
            if (classificacoes is not None
                    and r.get(campo) not in classificacoes):
                continue
            yield r


def _texto_para_csv(valor, coluna: Coluna) -> str:
    """O valor como ele deve aparecer no CSV.

    Número sai com vírgula decimal e sem separador de milhar: com milhar, o
    Excel em português lê "1.234" como mil duzentos e trinta e quatro em uns
    lugares e como 1,234 em outros. Sem milhar não há ambiguidade.
    """
    traducao = _TRADUCOES.get(coluna.campo)
    if traducao:
        return traducao.get(str(valor), str(valor))
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if coluna.tipo == "data" and isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if coluna.tipo in CASAS:
        numero = float(valor if not isinstance(valor, Decimal) else valor)
        return f"{numero:.{CASAS[coluna.tipo]}f}".replace(".", ",")
    return str(valor)


def titulos_do_csv(colunas) -> list[str]:
    """Os títulos das colunas do CSV, sem dois iguais.

    No xlsx a faixa do bloco separa o "Valor" do PIS do "Valor" da COFINS. No
    CSV não há faixa: as duas colunas saem com o mesmo nome, e quem abre no
    Excel — ou aponta uma dinâmica para o arquivo — não tem como saber qual é
    qual. A Consulta de Entradas saía com sete pares assim.

    Quando o título se repete, o bloco entra na frente: "PIS - Valor". Quando
    não se repete, nada muda — os arquivos que já circulam continuam iguais.
    """
    titulos = [c.titulo_no_csv for c in colunas]
    repetidos = {t for t in titulos if titulos.count(t) > 1}
    return [
        f"{c.bloco} - {t}" if t in repetidos and c.bloco else t
        for c, t in zip(colunas, titulos)
    ]


def _literal(texto: str) -> str:
    return "'" + str(texto).replace("'", "''") + "'"


def _expressao_csv(coluna: Coluna, tipos: dict[str, pa.DataType]) -> str:
    """A coluna como texto do CSV, em SQL, com as regras de `_texto_para_csv`.

    As duas implementações dizem a mesma coisa de propósito: a do Python
    documenta a regra, e a do SQL é a que roda. O teste de igualdade entre elas
    é o que impede que divirjam.
    """
    if coluna.campo not in tipos:
        return "NULL"
    col = '"' + coluna.campo.replace('"', '""') + '"'
    tipo = tipos[coluna.campo]
    traducao = _TRADUCOES.get(coluna.campo)
    if traducao:
        casos = " ".join(f"WHEN {_literal(k)} THEN {_literal(v)}" for k, v in traducao.items())
        expr = f"CASE CAST({col} AS VARCHAR) {casos} ELSE CAST({col} AS VARCHAR) END"
    elif pa.types.is_boolean(tipo):
        expr = f"CASE WHEN {col} THEN 'Sim' WHEN NOT {col} THEN 'Não' END"
    elif coluna.tipo == "data" and pa.types.is_date(tipo):
        expr = f"strftime({col}, '%d/%m/%Y')"
    elif coluna.tipo in CASAS:
        expr = f"replace(printf('%.{CASAS[coluna.tipo]}f', TRY_CAST({col} AS DOUBLE)), '.', ',')"
    else:
        expr = f"CAST({col} AS VARCHAR)"
    # vazio vira nulo: o DuckDB escreve texto vazio entre aspas ("") para
    # distinguir de nulo, e o CSV desta casa sempre saiu com o campo vazio
    return f"nullif({expr}, '')"


def _gerar_csv(parquet: str, destino: str, colunas: tuple[Coluna, ...],
               modelos: frozenset[str] | None = None,
               classificacoes: frozenset[str] | None = None,
               campo: str = "classificacao") -> int:
    """Uma linha por registro, sem limite e sem aba.

    Escrito pelo DuckDB, e não linha a linha em Python: a Ficha 3 de uma loja
    da empresa 19 (1,17 milhão de linhas) levava 60 s, e o dossiê de uma base do
    tamanho da empresa 17 leva uma por filial. Os bytes são os mesmos que o módulo
    `csv` escrevia — `;`, aspas só onde precisa, CRLF, vírgula decimal —, e o
    BOM vai à mão: sem ele o Excel lê o arquivo como ANSI e todo acento vira lixo.
    """
    tipos = {campo_.name: campo_.type for campo_ in pq.read_schema(parquet)}
    filtros = []
    if modelos is not None:
        filtros.append(f"modelo IN ({', '.join(map(_literal, sorted(modelos)))})"
                       if "modelo" in tipos and modelos else "false")
    if classificacoes is not None:
        filtros.append(f'"{campo}" IN ({", ".join(map(_literal, sorted(classificacoes)))})'
                       if campo in tipos and classificacoes else "false")
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    selecao = ", ".join(f"{_expressao_csv(c, tipos)} AS c{i}" for i, c in enumerate(colunas))
    corpo = destino + ".corpo"
    pasta = _pasta_de_rascunho(destino)

    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=SEPARADOR_CSV,
                   quoting=csv.QUOTE_MINIMAL).writerow(titulos_do_csv(colunas))
    con = duckdb.connect()
    try:
        con.execute("SET threads TO 4")
        con.execute(f"SET temp_directory = {_literal(pasta)}")
        escritas = con.execute(
            f"COPY (SELECT {selecao} FROM read_parquet({_literal(parquet)}) {onde}) TO {_literal(corpo)} "
            f"(HEADER false, DELIMITER '{SEPARADOR_CSV}', QUOTE '\"', ESCAPE '\"', NEW_LINE '\r\n')"
        ).fetchone()[0]
    finally:
        con.close()
    try:
        with open(destino, "ab") as saida, open(corpo, "rb") as origem:
            shutil.copyfileobj(origem, saida, 1 << 20)
    finally:
        if os.path.isfile(corpo):
            os.remove(corpo)

    log.info("csv gerado",
             extra={"arquivo": os.path.basename(destino), "linhas": escritas})
    return escritas


def _pasta_de_rascunho(destino: str) -> str:
    """Onde o xlsxwriter despeja o XML enquanto monta a planilha.

    A pasta do próprio destino, criada se faltar. Não é a pasta temporária do
    sistema de propósito: ela costuma estar no disco do Windows, que é o menor
    da máquina, e o rascunho de uma lista grande não cabe lá.

    Também não é a pasta que o usuário escolheu no "salvar como": o servidor
    nunca fica sabendo dela, e, quando é pasta de rede, escrever rascunho lá
    seria pedir o defeito que este projeto já conhece — gravação que atrasa e
    se perde. Gera-se local, entrega-se depois.
    """
    pasta = os.path.dirname(os.path.abspath(destino))
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _gerar_xlsx(parquet: str, destino: str, colunas: tuple[Coluna, ...],
                titulo_da_aba: str, modelos: frozenset[str] | None = None,
                classificacoes: frozenset[str] | None = None,
                campo: str = "classificacao") -> int:
    livro = xlsxwriter.Workbook(destino, {
        "constant_memory": True,        # não segura a planilha em memória
        "default_date_format": "dd/mm/yyyy",
        # o rascunho fica ao lado do arquivo que está sendo escrito, e não na
        # pasta temporária do sistema. Com `constant_memory` o xlsxwriter
        # despeja cada linha em disco: são 7 a 9 GB de XML para uma lista de
        # 8,7 milhões de linhas. No C: desta casa isso enchia o disco antes de
        # a planilha ficar pronta, e derrubava a máquina junto. Aqui o rascunho
        # cai na pasta de trabalho, que é onde o volume foi dimensionado — a
        # mesma escolha que o DuckDB já faz com `temp_directory`.
        "tmpdir": _pasta_de_rascunho(destino),
    })
    cabecalho = livro.add_format(ESTILO_DO_CABECALHO)
    corpo = {"font_name": FONTE_DA_PLANILHA, "font_size": CORPO_DA_FONTE}
    texto = livro.add_format({"num_format": "@", **corpo})
    dinheiro = livro.add_format({"num_format": "#,##0.00", **corpo})
    # quantidade tem até cinco casas na EFD; mostrar duas esconderia fração
    quantidade = livro.add_format({"num_format": "#,##0.00###", **corpo})
    inteiro = livro.add_format({"num_format": "0", **corpo})
    dia = livro.add_format({"num_format": "dd/mm/yyyy", **corpo})
    formatos = {"texto": texto, "numero": dinheiro, "quantidade": quantidade,
                "numero_inteiro": inteiro, "data": dia}

    aba, primeira = _abrir_aba(livro, titulo_da_aba, 1, colunas, cabecalho)
    escritas = 0
    na_aba = 0
    abas = 1

    for r in _filtradas(parquet, modelos, classificacoes, campo):
        if na_aba >= LIMITE_POR_ABA:
            abas += 1
            aba, primeira = _abrir_aba(livro, titulo_da_aba, abas, colunas, cabecalho)
            na_aba = 0
        _escrever(aba, primeira + na_aba, r, colunas, formatos)
        na_aba += 1
        escritas += 1

    livro.close()
    log.info("planilha gerada",
             extra={"arquivo": os.path.basename(destino), "linhas": escritas,
                    "abas": abas})
    return escritas


def _faixas(colunas: tuple[Coluna, ...]) -> list[tuple[str, int, int]]:
    """As faixas de bloco: (título, primeira coluna, última), colunas seguidas
    com o mesmo bloco viram uma só."""
    faixas: list[tuple[str, int, int]] = []
    for i, coluna in enumerate(colunas):
        if faixas and faixas[-1][0] == coluna.bloco:
            faixas[-1] = (coluna.bloco, faixas[-1][1], i)
        else:
            faixas.append((coluna.bloco, i, i))
    return faixas


def _abrir_aba(livro, titulo: str, numero: int, colunas: tuple[Coluna, ...],
               formato_cabecalho):
    """Abre a aba e escreve o cabeçalho. Devolve (aba, primeira linha de dado).

    Com bloco ou número nas colunas, o cabeçalho tem três linhas — faixa,
    título e número do campo no leiaute —, como o papel de trabalho da CAT 42.
    Sem eles, continua com uma linha só.
    """
    nome = titulo if numero == 1 else f"{titulo} ({numero})"
    aba = livro.add_worksheet(nome[:31])
    tem_faixa = any(c.bloco for c in colunas)
    tem_numero = any(c.numero for c in colunas)
    linha_do_titulo = 1 if tem_faixa else 0
    for i, coluna in enumerate(colunas):
        aba.set_column(i, i, coluna.largura)
    # com `constant_memory` o xlsxwriter despeja cada linha em disco assim que
    # a seguinte começa: a faixa tem de ser escrita antes dos títulos, e os
    # títulos antes dos números, senão a linha de cima já foi e some
    if tem_faixa:
        for bloco, de, ate in _faixas(colunas):
            if de == ate:
                aba.write(0, de, bloco, formato_cabecalho)
            else:
                aba.merge_range(0, de, 0, ate, bloco, formato_cabecalho)
    aba.set_row(linha_do_titulo, ALTURA_DO_CABECALHO)
    for i, coluna in enumerate(colunas):
        aba.write(linha_do_titulo, i, coluna.titulo, formato_cabecalho)
    if tem_numero:
        for i, coluna in enumerate(colunas):
            aba.write(linha_do_titulo + 1, i, coluna.numero_na_planilha, formato_cabecalho)
    primeira = linha_do_titulo + (2 if tem_numero else 1)
    aba.freeze_panes(primeira, 0)
    return aba, primeira


def _escrever(aba, linha: int, registro: dict, colunas: tuple[Coluna, ...],
              formatos: dict) -> None:
    for i, coluna in enumerate(colunas):
        valor = registro.get(coluna.campo)
        if valor is None or valor == "":
            continue
        traducao = _TRADUCOES.get(coluna.campo)
        if traducao:
            aba.write_string(linha, i, traducao.get(str(valor), str(valor)),
                             formatos["texto"])
        elif isinstance(valor, bool):
            # antes de "numero": bool é int em Python, e "True" numa célula
            # não diz nada a quem lê em português
            aba.write_string(linha, i, "Sim" if valor else "Não", formatos["texto"])
        elif coluna.tipo == "data" and isinstance(valor, date):
            aba.write_datetime(linha, i, valor, formatos["data"])
        elif coluna.tipo in ("numero", "quantidade", "numero_inteiro"):
            aba.write_number(linha, i, float(valor if isinstance(valor, Decimal)
                                             else valor), formatos[coluna.tipo])
        else:
            # tudo o mais é identificador: vai como texto para não perder zero
            aba.write_string(linha, i, str(valor), formatos["texto"])


def gerar_sem_documento(parquet: str, destino: str,
                        modelos: frozenset[str] | None = None,
                        classificacoes: frozenset[str] | None = None,
                        formato: str = "xlsx") -> int:
    """A planilha de pendências.

    Sem filtro, sai inteira — cancelada, denegada e sem chave incluídas,
    cada uma marcada na coluna Classificação. Excluir alguma delas aqui as
    tiraria do controle para sempre: na rodada seguinte, quando o cliente
    mandar o que faltava, ninguém voltaria a olhá-las.
    """
    return gerar(parquet, destino, COLUNAS_SEM_DOCUMENTO, "Pendências",
                 modelos=modelos, classificacoes=classificacoes,
                 formato=formato)


def gerar_conferidas(parquet: str, destino: str,
                     modelos: frozenset[str] | None = None,
                     classificacoes: frozenset[str] | None = None,
                     formato: str = "xlsx") -> int:
    """A lista positiva: está na EFD e o documento veio.

    É o que segue para a apuração. Não tem classificação; o filtro por modelo
    vale pelo mesmo motivo da cobrança — cupom domina o volume.
    """
    return gerar(parquet, destino, COLUNAS_CONFERIDAS, "Conferidas",
                 modelos=modelos, formato=formato)


def gerar_nao_escrituradas(parquet: str, destino: str,
                           modelos: frozenset[str] | None = None,
                           classificacoes: frozenset[str] | None = None,
                           formato: str = "xlsx") -> int:
    # o parquet das não escrituradas não tem modelo: a chave veio da pasta,
    # e o que se sabe dela é a origem
    return gerar(parquet, destino, COLUNAS_NAO_ESCRITURADAS,
                 "Não escrituradas", formato=formato)
