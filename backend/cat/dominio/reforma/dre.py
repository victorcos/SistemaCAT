"""A DRE de cada ano e as duas reconciliações que a sustentam.

Responde à pergunta do revisor (13/10/2026): como um custo de R$ 425,8 mi
convive com R$ 65,1 mi de crédito sem que um se subtraia do outro? Porque são
três visões diferentes do mesmo número, e cada uma fecha em zero sozinha:

1. **DRE (contábil).** Receita bruta menos os tributos sobre a venda dá a
   receita líquida; menos o CMV — já líquido do que se recupera — dá o lucro.
2. **Composição do CMV.** A nota de compra soma custo, tributo recuperável e
   tributo não recuperável. O recuperável vira ativo fiscal e sai; o que fica
   é o CMV. O custo líquido é constante por hipótese — o que muda de ano a ano
   é o valor bruto da compra, porque muda o tributo destacado na nota.
3. **Apuração fiscal (memória, fora da DRE).** Débitos menos créditos é o
   tributo a recolher.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cat.dominio.reforma.projecao import ResultadoDoAno

# tolerância das conferências: a soma de meio milhão de linhas em Decimal fecha
# no centavo, e um real de folga já denuncia fórmula errada
TOLERANCIA = Decimal("1")


@dataclass(frozen=True)
class Conferencia:
    nome: str
    diferenca: Decimal

    @property
    def fecha(self) -> bool:
        return abs(self.diferenca) < TOLERANCIA


def conferir(r: ResultadoDoAno) -> list[Conferencia]:
    """As identidades que todo ano tem de satisfazer. Uma que não fecha é
    fórmula errada, não dado ruim — por isso a rodada falha em vez de avisar."""
    tributos_na_venda = r.debito_icms + r.debito_pis_cofins + r.debito_ipi + r.debito_cbs + r.debito_ibs
    debitos = r.debito_icms + r.debito_pis_cofins + r.debito_cbs + r.debito_ibs + r.debito_ipi
    return [
        Conferencia("DRE: receita bruta − tributos na venda = receita líquida",
                    r.receita_bruta - tributos_na_venda - r.receita_liquida),
        Conferencia("CMV: valor bruto das compras − créditos recuperáveis = CMV",
                    r.valor_bruto_das_compras - r.creditos_recuperaveis - r.cmv),
        Conferencia("Apuração: débitos − créditos = tributo a recolher",
                    debitos - r.creditos_recuperaveis - r.total_a_recolher),
    ]
