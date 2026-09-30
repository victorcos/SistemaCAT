"""As tabelas do bloco 0 pendem do estabelecimento, e não do arquivo.

Na EFD-Contribuições o **0140 abre um bloco de cadastro próprio** — 0150 o
participante, 0190 a unidade, 0200 o item, 0400 a natureza, 0500 a conta — e um
segundo 0140 recomeça tudo. Não é detalhe de leiaute: o mesmo `COD_ITEM` é uma
mercadoria na matriz e outra na filial.

Achado em 29/09/2026, montando a 047 contra o gabarito do MA. No arquivo de
outubro/2025 de um cliente, **134 códigos de item apareciam nos dois
estabelecimentos com produtos que não têm nada a ver um com o outro** — o
código 10918 é "SABAO LIQ YPE" na matriz e "PAO DE FORMA ILUSTRE" na filial.
Uma tabela só por arquivo troca um pelo outro, e o relatório sai com a descrição
e o NCM errados sem nenhum sinal de que errou. Era assim que estava, e por isso
esta classe existe num módulo próprio: o defeito é o mesmo na 037 e na 047, e
uma regra sutil escrita duas vezes é uma regra que vai divergir.

## As duas ressalvas, as duas tiradas do gabarito

**Sem cadastro no estabelecimento corrente** — arquivo em que o C010 não casa
com nenhum 0140, por exemplo — ainda vale procurar nos outros, mas **só se o
código existir num só**. Havendo mais de um não há desempate, e cadastro errado
com cara de certo é pior que coluna vazia.

**Campo vazio no cadastro certo** o MA preenche com o do **cadastro da
matriz** — o estabelecimento cujo CNPJ é o do 0000. O código 910808 é "COXAO
MOLE BOVINO KG" na filial, sem código de barra, e "SAPOLIO RADIUM" na matriz,
com; o gabarito escreve, na linha do coxão, o código de barra do sapólio. É o
código de barra de outro produto, e discordo — mas quem confere confere texto
contra texto, e está marcado aqui como replicação, não como convicção.

**É a matriz, e não "quem cadastrou primeiro".** A diferença só aparece quando a
matriz não tem aquele código: em setembro/2022 o item 911047 é "PAO FRANCES KG"
em duas filiais, com NCM 19012000 na primeira delas e em branco na segunda, e o
gabarito escreve **em branco** nas 85 linhas da segunda — porque a matriz não
cadastrou 911047. Já o 911159 existe na matriz, e aí o gabarito escreve o NCM
dela nas 10 linhas da filial, ainda que lá o produto se chame "SALGADO" e na
matriz "BISC. RENATA 20X360G MAIZENA". Tomar "o primeiro do arquivo" por matriz
acerta um caso e erra o outro: foram 317 linhas erradas numa competência só.

A descrição, na prática, nunca se completa — ela é obrigatória no leiaute, e nas
1.975 linhas de outubro/2025 cujo item existe em dois estabelecimentos todas
trazem a descrição do próprio escopo.
"""

from __future__ import annotations


def completado(cadastro: list[str], outro: list[str]) -> list[str]:
    """O cadastro, com os campos vazios preenchidos pelo do outro."""
    if not outro:
        return cadastro
    return [valor or (outro[i] if i < len(outro) else "")
            for i, valor in enumerate(cadastro)]


class CadastroPorEstabelecimento:
    """As tabelas de cadastro de um arquivo, cada uma sob o seu 0140.

    `chaves` diz que registros guardar e em que posição está o código de cada
    um — `{b"0150": 1, b"0200": 1, b"0500": 5}`.

    `matriz` é o CNPJ do 0000: é dele o cadastro que preenche os campos que o
    do estabelecimento deixou em branco. Sem ele, nada se completa.
    """

    def __init__(self, chaves: dict[bytes, int], matriz: str = "") -> None:
        self.chaves = chaves
        self.matriz = "".join(c for c in matriz if c.isdigit())
        self.corrente = ""
        self.estabelecimentos: dict[str, list[str]] = {}
        self.linhas: dict[bytes, dict[tuple[str, str], list[str]]] = {r: {} for r in chaves}
        # de que estabelecimento é cada código; `None` quando é de mais de um
        self.donos: dict[bytes, dict[str, str | None]] = {r: {} for r in chaves}


    def definir_matriz(self, cnpj: str) -> None:
        """O CNPJ do 0000. Chegou depois do bloco 0? Vale mesmo assim."""
        self.matriz = "".join(c for c in (cnpj or "") if c.isdigit())

    def abrir(self, valores: list[str]) -> None:
        """Um 0140: daqui até o próximo, o cadastro é deste estabelecimento."""
        self.corrente = valores[3] if len(valores) > 3 else ""
        if self.corrente:
            self.estabelecimentos[self.corrente] = valores

    def guardar(self, registro: bytes, valores: list[str]) -> bool:
        """Guarda a linha, se o registro for de cadastro. Diz se era."""
        posicao = self.chaves.get(registro)
        if posicao is None:
            return False
        if len(valores) > posicao and (codigo := valores[posicao]):
            # o primeiro a aparecer é o que fica: o mesmo código repetido
            # dentro do mesmo 0140 é o cliente tendo cadastrado duas vezes, e é
            # o primeiro cadastro que o relatório de referência mostra
            self.linhas[registro].setdefault((self.corrente, codigo), valores)
            dono = self.donos[registro]
            if codigo not in dono:
                dono[codigo] = self.corrente
            elif dono[codigo] != self.corrente:
                dono[codigo] = None
        return True

    def linha(self, registro: bytes, codigo: str, cnpj: str,
              completar: bool = True) -> list[str]:
        """O cadastro daquele código, no estabelecimento daquele CNPJ.

        Vazio quando não há — nunca o de outro estabelecimento escolhido a
        esmo. Ver as duas ressalvas no topo do módulo.

        `completar=False` desliga o preenchimento pela matriz. **Nem todo
        relatório do MA completa**: a 047 completa — é de lá que a regra foi
        medida —, e o 839 não. Nas três linhas de setembro/2023 em que a filial
        cadastrou "SALAME ITALIANO PAMPLONA KG" sem código de barra e a matriz
        tem o mesmo código como "DETERGENTE LIMPOL", o 839 escreve o EAN em
        branco e a 047 escreveria o do detergente. Cada um replica o seu
        gabarito, e a diferença fica aqui, escrita, em vez de virar uma segunda
        classe quase igual a esta.
        """
        if not codigo:
            return []
        direto = self.linhas[registro].get((cnpj, codigo))
        if direto is None:
            dono = self.donos[registro].get(codigo)
            return self.linhas[registro].get((dono, codigo), []) if dono else []
        if not completar or not self.matriz or cnpj == self.matriz:
            return direto
        return completado(direto, self.linhas[registro].get((self.matriz, codigo), []))

    def estabelecimento(self, cnpj: str) -> list[str]:
        """A linha do 0140 daquele CNPJ."""
        return self.estabelecimentos.get(cnpj, [])
