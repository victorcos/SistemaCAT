"""A leitura dos resumos das etapas numa lista de pendências só."""

from cat.dominio.cat42.entrega import Gravidade, SituacaoDaCompetencia, pendencias

RESUMOS = {
    "conferencia": {"sem_documento_cobravel": 120, "nao_escrituradas": 0, "sem_chave_na_efd": 3},
    "st_suportado": {"por_pendencia": {"sem_o_que_apurar": 900, "falta_dado": 45}},
    "razao": {"pendencias": {"saidas_sem_aliquota": 2, "fichas_negativas": 0, "fichas_fora_de_sp": 7}},
    "apuracao": {"por_motivo": [
        {"codigo": "fora_de_sp", "rotulo": "Estabelecimento fora de São Paulo", "o_que_fazer": "x", "competencias": 5},
        {"codigo": "sem_inventario", "rotulo": "Sem inventário", "o_que_fazer": "y", "competencias": 2},
    ]},
    "arquivo_digital": {
        "entradas_sem_icms": 10,
        "por_trava": [
            {"codigo": "nao_apta", "rotulo": "Competência com pendência", "o_que_fazer": "z", "arquivos": 2},
            {"codigo": "saldo_negativo", "rotulo": "Estoque negativo no 1050", "o_que_fazer": "w", "arquivos": 1},
        ],
        "por_regra": [
            {"codigo": "vl_confr", "rotulo": "VL_CONFR", "severidade": "erro", "o_que_fazer": "v", "ocorrencias": 4},
            {"codigo": "saldo_em_valor", "rotulo": "Saldo em valor", "severidade": "aviso", "o_que_fazer": "u",
             "ocorrencias": 1},
        ],
    },
}


class TestPendencias:
    def test_so_entra_o_que_tem_quantidade(self):
        codigos = {p.codigo for p in pendencias(RESUMOS)}
        assert "nao_escrituradas" not in codigos
        assert {"documentos_a_cobrar", "sem_chave_na_efd", "icms_suportado", "sem_aliquota", "fora_de_sp"} <= codigos

    def test_trava_primeiro_depois_atencao_depois_informacao(self):
        lista = pendencias(RESUMOS)
        gravidades = [p.gravidade for p in lista]
        assert gravidades == sorted(gravidades, key=[Gravidade.TRAVA, Gravidade.ATENCAO, Gravidade.INFORMACAO].index)
        # dentro da mesma gravidade, na ordem das etapas em que se resolve
        travas = [p.etapa for p in lista if p.gravidade is Gravidade.TRAVA]
        assert travas == ["razao", "apuracao", "arquivo_digital", "arquivo_digital"]

    def test_listas_das_etapas_6_e_7(self):
        por_codigo = {p.codigo: p for p in pendencias(RESUMOS)}
        assert por_codigo["sem_inventario"].gravidade is Gravidade.TRAVA
        assert por_codigo["sem_inventario"].unidade == "competências"
        # "não apta" repete os motivos da etapa 6: não entra duas vezes
        assert "nao_apta" not in por_codigo
        assert por_codigo["pre_validacao_saldo_em_valor"].gravidade is Gravidade.ATENCAO

    def test_o_mesmo_problema_visto_por_varias_etapas_vira_uma_pendencia(self):
        por_codigo = {p.codigo: p for p in pendencias(RESUMOS)}
        # fora de SP: fichas no razão e competências na apuração
        fora = por_codigo["fora_de_sp"]
        assert fora.gravidade is Gravidade.INFORMACAO and fora.etapa == "razao"
        assert [(m.quantidade, m.unidade, m.etapa) for m in fora.medidas] == [
            (7, "fichas", "razao"), (5, "competências", "apuracao")]
        # estoque negativo: só a etapa 7 viu neste resumo, e o rótulo é o do assunto
        assert por_codigo["estoque_negativo"].medidas[0].unidade == "arquivos"
        # o suportado que faltou na etapa 4 é o ICMS_TOT zero da etapa 7
        suportado = por_codigo["icms_suportado"]
        assert (suportado.etapa, suportado.quantidade) == ("st_suportado", 45)
        assert [m.etapa for m in suportado.medidas] == ["st_suportado", "arquivo_digital"]
        # a regra VL_CONFR da pré-validação é o confronto pendente: trava
        assert por_codigo["confronto_pendente"].gravidade is Gravidade.TRAVA
        assert "pre_validacao_vl_confr" not in por_codigo

    def test_gravidade_do_assunto_e_a_mais_alta(self):
        resumos = {"razao": {"pendencias": {"confronto_pendente": 3}},
                   "arquivo_digital": {"por_regra": [{"codigo": "vl_confr", "rotulo": "x", "severidade": "erro",
                                                      "o_que_fazer": "", "ocorrencias": 2}]}}
        [p] = pendencias(resumos)
        assert (p.codigo, p.gravidade, p.quantidade, len(p.medidas)) == ("confronto_pendente", Gravidade.TRAVA, 3, 2)

    def test_regras_da_mesma_etapa_e_unidade_somam(self):
        regra = lambda codigo, n: {"codigo": codigo, "rotulo": codigo, "severidade": "erro",  # noqa: E731
                                   "o_que_fazer": "", "ocorrencias": n}
        [p] = pendencias({"arquivo_digital": {"por_regra": [regra("item_sem_saldo", 69), regra("saldo_negativo", 2)]}})
        assert [(m.quantidade, m.unidade) for m in p.medidas] == [(71, "ocorrências")]

    def test_resumo_ausente_ou_antigo_nao_inventa_pendencia(self):
        assert pendencias({}) == []
        assert pendencias({"razao": {"pendencias": "texto de versão antiga"}}) == []


class TestSituacaoDaCompetencia:
    def test_fora_de_sp_vence_o_destino(self):
        assert SituacaoDaCompetencia.de("PR", "envio") is SituacaoDaCompetencia.FORA_DE_SP

    def test_sp_pelo_destino_do_arquivo(self):
        assert SituacaoDaCompetencia.de("SP", "envio") is SituacaoDaCompetencia.ENVIO
        assert SituacaoDaCompetencia.de("sp", "previa") is SituacaoDaCompetencia.PREVIA
        assert SituacaoDaCompetencia.de("SP", None) is SituacaoDaCompetencia.SEM_ARQUIVO
