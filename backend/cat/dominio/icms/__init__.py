"""ICMS: o que é de imposto estadual.

O sistema nasceu na CAT 42 e por isso a regra dela morava na raiz do domínio,
como se fosse o domínio inteiro. Com PIS/COFINS e IRPJ/CSLL entrando como
módulos próprios (decisão do Victor, 22/09/2026), cada tributo passa a ter o seu
lugar — e a CAT 42 é **uma** obrigação do ICMS, não o contrário.

Aqui dentro cabem, além dela, o ressarcimento de ST fora do rito da CAT 42 e o
crédito outorgado. O que é de leitura de arquivo fiscal — SPED, nota fiscal,
de-para — fica um nível acima, em `dominio/`, porque serve a todos os módulos:
a exclusão do ICMS da base do PIS/COFINS lê a mesma EFD que a CAT 42 lê.
"""
