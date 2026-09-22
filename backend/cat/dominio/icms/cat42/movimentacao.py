"""O histórico da movimentação: o que a EFD tem, item a item, e o que não tem.

É a terceira etapa do trabalho e a matéria-prima do razão. O que sai daqui
não é o razão ainda — é o inventário honesto do que existe para montá-lo:

* os **itens de entrada**, do C170, com quantidade, CST, CFOP, ICMS e ST;
* o **cadastro** (0200) que dá nome, código de barras, NCM e CEST a cada
  código;
* o **inventário** (bloco H), que abre a ficha;
* e, tão importante quanto, **as saídas que a EFD não detalha**. NF-e de
  emissão própria e cupom SAT vão para a EFD só com o analítico (C190/C850):
  total por CST e CFOP, sem item. Medido em duas empresas reais: 27.448 C170,
  nenhum de saída; 171.652 cupons, nenhum C810. O item de saída virá do XML,
  e a tela tem de dizer isso com número, não deixar para o razão descobrir.

Cada movimento carrega a classificação da conferência anterior — conferido,
pendente, sem chave — porque o histórico "do que foi encontrado" é isto: o
que tem documento sustenta o razão; o que não tem entra marcado, e some da
marca quando o cliente mandar o que falta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from cat.dominio.icms.cat42.conferencia import Fatia, _lista, _numero

ZERO = Decimal("0")


def _dinheiro(v: Decimal) -> str:
    inteiro, _, centavos = f"{v:,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


@dataclass
class ResumoDaMovimentacao:
    """Só números e recortes; as listas vivem em parquet."""

    arquivos: int = 0
    estabelecimentos: list[str] = field(default_factory=list)

    # ---- documentos: o que tem item e o que não tem ----
    documentos: int = 0
    documentos_com_item: int = 0
    # entrada de TERCEIROS sem C170: aí a EFD exige o item, e faltar é anomalia
    entradas_sem_item: int = 0
    # entrada de emissão PRÓPRIA sem C170 (devolução de venda, produtor rural,
    # retorno): mesma regra da saída própria — a EFD dispensa o item. Numa
    # base real eram 179.333, todas de emissão própria; não é raro, é regra
    entradas_proprias_sem_item: int = 0
    saidas_sem_item: int = 0
    valor_saidas_sem_item: Decimal = ZERO           # do analítico
    valor_saidas_sem_item_st: Decimal = ZERO        # idem, só CST x60
    saidas_sem_item_por_modelo: list[Fatia] = field(default_factory=list)

    # ---- o XML: o item que a EFD não trouxe, e os valores ao lado do C170 ----
    xml_arquivos: int = 0
    xml_documentos: int = 0
    xml_itens: int = 0
    xml_repetidos: int = 0
    xml_nao_sao_documento: int = 0
    xml_ilegiveis: int = 0
    # protocolo de uso denegado: a nota não existe, e sai com todas as cópias
    xml_nao_autorizados: int = 0
    # repetidos em que a cópia autorizada ficou no lugar da sem protocolo
    xml_copias_trocadas: int = 0
    saidas_completadas_pelo_xml: int = 0
    entradas_completadas_pelo_xml: int = 0
    movimentos_do_xml: int = 0
    # C170 com o item do XML ao lado (mesmo número do item e mesmo valor)
    itens_pareados_com_xml: int = 0
    # C170 de documento que tem XML, mas sem item que case: ficou com a EFD
    itens_sem_par_no_xml: int = 0
    # canceladas na SEFAZ (evento de cancelamento ou lista de chaves): as
    # chaves lidas, e o que a EFD trazia como válido e saiu da movimentação
    chaves_canceladas: int = 0
    documentos_cancelados_na_sefaz: int = 0
    movimentos_cancelados: int = 0

    # ---- não escrituradas: XML do estabelecimento fora da EFD do mês ----
    # a multa do art. 527 do RICMS/SP, sem SELIC (ver `contingencia.py`)
    nao_escrituradas_entradas: int = 0
    nao_escrituradas_saidas: int = 0
    valor_nao_escriturado_entradas: Decimal = ZERO
    icms_nao_escriturado_saidas: Decimal = ZERO
    multa_nao_escrituradas_entradas: Decimal = ZERO
    multa_nao_escrituradas_saidas: Decimal = ZERO
    contingencia_por_ano: list[Fatia] = field(default_factory=list)
    # itens sem a base no XML: com a da nota mais próxima do produto, e sem nota nenhuma
    contingencia_itens_de_nota_vizinha: int = 0
    contingencia_itens_sem_referencia: int = 0

    # ---- movimentos: as linhas de item ----
    movimentos: int = 0
    movimentos_entrada: int = 0
    movimentos_saida: int = 0
    valor_entradas: Decimal = ZERO
    valor_saidas: Decimal = ZERO
    st_nas_entradas: Decimal = ZERO                 # soma do VL_ICMS_ST do C170
    por_cst: list[Fatia] = field(default_factory=list)          # entradas
    por_classificacao: list[Fatia] = field(default_factory=list)

    # ---- cadastro e estoque ----
    itens_cadastrados: int = 0
    itens_movimentados: int = 0
    itens_sem_cadastro: int = 0
    inventarios: int = 0
    itens_em_estoque: int = 0
    valor_em_estoque: Decimal = ZERO

    conferencia_usada: bool = False
    arquivos_fora_de_ordem: int = 0

    @property
    def cobertura_de_item(self) -> float:
        """Fração dos documentos que trazem item na EFD. Zero a um."""
        if not self.documentos:
            return 0.0
        return self.documentos_com_item / self.documentos

    @property
    def avisos(self) -> list[str]:
        avisos: list[str] = []
        if self.saidas_sem_item:
            modelos = ", ".join(f.rotulo for f in self.saidas_sem_item_por_modelo[:3])
            faltam = max(0, self.saidas_sem_item - self.saidas_completadas_pelo_xml)
            completou = (f" O XML completou {_numero(self.saidas_completadas_pelo_xml)}; "
                         if self.saidas_completadas_pelo_xml else " ")
            avisos.append(
                f"{_numero(self.saidas_sem_item)} documento(s) de saída "
                f"({modelos}) não trazem item na EFD — NF-e própria e cupom "
                "SAT vão para a EFD só com o analítico. São "
                f"{_dinheiro(self.valor_saidas_sem_item)} de saídas, dos quais "
                f"{_dinheiro(self.valor_saidas_sem_item_st)} com CST 60 "
                f"(mercadoria com ST retida).{completou}"
                + (f"{_numero(faltam)} seguem sem item: sem o XML delas, o item só "
                   "vem do relatório de saídas do cliente, no razão." if faltam else
                   "nenhuma ficou sem item.")
            )
        if self.entradas_proprias_sem_item:
            faltam = max(0, self.entradas_proprias_sem_item - self.entradas_completadas_pelo_xml)
            avisos.append(
                f"{_numero(self.entradas_proprias_sem_item)} nota(s) de entrada "
                "de emissão própria (devolução de venda, produtor rural, "
                "retorno) também vêm sem item na EFD — mesma regra da saída "
                "própria. "
                + (f"{_numero(faltam)} seguem sem item por falta do XML." if faltam else
                   "O XML completou todas.")
            )
        if self.itens_sem_par_no_xml:
            avisos.append(
                f"{_numero(self.itens_sem_par_no_xml)} item(ns) do C170 são de nota "
                "com XML, mas não casaram com o item do XML (número do item ou valor "
                "diferentes). Ficaram com os valores da EFD."
            )
        if self.nao_escrituradas_entradas or self.nao_escrituradas_saidas:
            multa = self.multa_nao_escrituradas_entradas + self.multa_nao_escrituradas_saidas
            avisos.append(
                f"{_numero(self.nao_escrituradas_entradas)} entrada(s) e "
                f"{_numero(self.nao_escrituradas_saidas)} saída(s) têm XML e não estão na EFD do "
                f"estabelecimento: contingência de {_dinheiro(multa)} em multa do art. 527 do "
                "RICMS/SP (10% do valor nas entradas, 75% do ICMS nas saídas), sem SELIC. "
                "Não entram na ficha; a planilha traz nota a nota."
            )
            if self.contingencia_itens_de_nota_vizinha or self.contingencia_itens_sem_referencia:
                avisos.append(
                    f"Na contingência, {_numero(self.contingencia_itens_de_nota_vizinha)} item(ns) sem a base "
                    "no XML (ICMS na saída, valor na entrada) levaram o valor por unidade da nota mais próxima "
                    f"do mesmo produto; {_numero(self.contingencia_itens_sem_referencia)} não têm nota nenhuma "
                    "do produto com a base e ficaram com base zero."
                )
        if self.documentos_cancelados_na_sefaz:
            avisos.append(
                f"{_numero(self.documentos_cancelados_na_sefaz)} documento(s) estão cancelados na "
                "SEFAZ (evento de cancelamento ou lista de canceladas) e a EFD os traz como "
                f"válidos: {_numero(self.movimentos_cancelados)} movimento(s) ficaram fora da "
                "apuração. A EFD desses períodos pede retificação."
            )
        if self.xml_nao_autorizados:
            avisos.append(
                f"{_numero(self.xml_nao_autorizados)} XML têm protocolo de uso denegado (a SEFAZ "
                "não autorizou a nota) e ficaram fora: não completam a EFD nem entram na "
                "contingência das não escrituradas."
            )
        if self.xml_ilegiveis:
            avisos.append(
                f"{_numero(self.xml_ilegiveis)} XML não abriram (arquivo quebrado ou "
                "chave inválida). O nome dos arquivos está no log da etapa."
            )
        if self.entradas_sem_item:
            avisos.append(
                f"{_numero(self.entradas_sem_item)} entrada(s) de terceiros não "
                "trazem C170 — nesses documentos a EFD exige o item. Vale "
                "conferir se a EFD veio completa."
            )
        if self.itens_sem_cadastro:
            avisos.append(
                f"{_numero(self.itens_sem_cadastro)} código(s) movimentados não "
                "estão no cadastro 0200 de nenhum período. Entram no "
                "histórico com a descrição, o NCM e o CEST do XML quando há, "
                "e sem eles quando não há."
            )
        if self.movimentos and not self.inventarios:
            avisos.append(
                "Nenhum inventário (bloco H) nas EFD importadas. O saldo de "
                "abertura da ficha terá de vir de outra fonte — o relatório de "
                "inventário do ERP serve."
            )
        if not self.conferencia_usada:
            avisos.append(
                "Os movimentos não foram marcados contra a conferência: não "
                "havia rodada concluída com a lista de conferidos em disco."
            )
        pendentes = next((f for f in self.por_classificacao
                          if f.codigo == "pendente"), None)
        if pendentes and pendentes.documentos:
            avisos.append(
                f"{_numero(pendentes.documentos)} movimento(s) são de documentos "
                "ainda pendentes na conferência. Estão no histórico, marcados; "
                "quando o cliente mandar o que falta, a conferência e esta "
                "etapa rodam de novo e a marca some."
            )
        if self.arquivos_fora_de_ordem:
            avisos.append(
                f"{_numero(self.arquivos_fora_de_ordem)} arquivo(s) tinham item "
                "antes do documento pai — fora da ordem do leiaute. Essas "
                "linhas ficaram fora; o nome dos arquivos está no log."
            )
        if len(self.estabelecimentos) > 1:
            avisos.append(
                f"Movimentos de {len(self.estabelecimentos)} estabelecimentos: "
                f"{_lista(self.estabelecimentos)}. O razão é por "
                "estabelecimento e por item."
            )
        return avisos
