from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    model_validator
)


# ============================================================
# OPÇÕES OFICIAIS
# ============================================================

EPSCode = Literal[
    "VOXA",
    "PRISMA",
    "LUMEN"
]


ProductCode = Literal[
    "GRADUACAO",
    "POS_GRADUACAO",
    "TECNICO",
    "PROFISSIONALIZANTES"
]


SuperChannelCode = Literal[
    "MIDIA",
    "HUNTER",
    "NOVOS_CANAIS",
    "OUTROS"
]


ModalityCode = Literal[
    "PRESENCIAL",
    "SEMIPRESENCIAL",
    "EAD"
]


PostFrontCode = Literal[
    "RECEPTIVO",
    "EGRESSOS",
    "7_MINUTOS"
]


CampaignTypeCode = Literal[
    "COMERCIAL",
    "INCENTIVO"
]


# Subtipo: so para acao comercial.
CampaignSubtypeCode = Literal[
    "TROCA_PRECOS",
    "REPIQUE_BASE",
    "AGING",
    "DESCONTO",
    "OUTROS"
]


# ============================================================
# KPI
# ============================================================

class CampaignKPI(BaseModel):

    nome_kpi: str = Field(
        min_length=2
    )

    descricao_kpi: str | None = None

    principal: bool = False

    baseline_tipo: str

    baseline_descricao: str | None = None

    baseline_valor: float | None = None

    meta_descricao: str

    meta_valor: float | None = None

    unidade_medida: str

    regra_atribuicao: str

    frequencia_reporte: str

    ritmo_esperado: str | None = None


# ============================================================
# ESCOPO
# ============================================================

class CampaignScope(BaseModel):

    produto: ProductCode

    frente_pos: PostFrontCode | None = None

    supercanal: SuperChannelCode

    outro_supercanal_descricao: str | None = None

    modalidade: ModalityCode | None = None


    @model_validator(mode="after")
    def validar_escopo(self):

        # OUTROS exige descrição
        if (
            self.supercanal == "OUTROS"
            and not self.outro_supercanal_descricao
        ):

            raise ValueError(
                "Quando Supercanal = OUTROS, "
                "é obrigatório descrever o outro supercanal."
            )


        # Graduação / Técnico / Profissionalizantes
        if self.produto != "POS_GRADUACAO":

            if self.frente_pos is not None:

                raise ValueError(
                    "Frente Pós somente pode ser usada "
                    "para Pós-Graduação."
                )

            if self.modalidade is None:

                raise ValueError(
                    "Modalidade é obrigatória para "
                    "Graduação, Técnico e Profissionalizantes."
                )


        # Pós-Graduação
        if self.produto == "POS_GRADUACAO":

            if self.frente_pos is None:

                raise ValueError(
                    "Pós-Graduação exige uma frente: "
                    "RECEPTIVO, EGRESSOS ou 7_MINUTOS."
                )

            if (
                self.frente_pos == "7_MINUTOS"
                and self.modalidade is None
            ):

                raise ValueError(
                    "Pós-Graduação 7 MINUTOS "
                    "exige modalidade."
                )

        return self


# ============================================================
# CADASTRO DA CAMPANHA
# ============================================================

class CampaignCreate(BaseModel):

    # IDENTIFICAÇÃO

    nome_campanha: str = Field(
        min_length=3,
        max_length=200
    )

    tipo_acao: CampaignTypeCode

    subtipo_acao: CampaignSubtypeCode | None = None

    subtipo_acao_outro: str | None = Field(
        default=None,
        max_length=120
    )


    # --------------------------------------------------------
    # 1. OPORTUNIDADE
    # --------------------------------------------------------

    oportunidade_problema: str

    fonte_oportunidade: str | None = None

    indicador_evidencia_oportunidade: str

    etapa_funil_alvo: str | None = None

    publico_alvo: str

    segmentacao: str | None = None

    criterio_elegibilidade: str

    criterio_exclusao: str

    dimensao_estimada: int = Field(
        gt=0
    )


    # --------------------------------------------------------
    # 2. ESTRATÉGIA
    # --------------------------------------------------------

    estrategia: str

    mecanica: str

    oferta_beneficio: str

    argumento_comercial: str

    regras_comerciais: str

    condicoes_especificas: str | None = None

    canais_possiveis: str


    # --------------------------------------------------------
    # INCENTIVO
    # --------------------------------------------------------

    incentivo_gatilhos: str | None = None

    incentivo_criterios: str | None = None

    incentivo_condicao_pagamento: str | None = None


    # --------------------------------------------------------
    # 3. OBJETIVO E RESULTADO
    # --------------------------------------------------------

    objetivo_campanha: str

    resultado_esperado: str


    # --------------------------------------------------------
    # VIGÊNCIA
    # --------------------------------------------------------

    dt_inicio_prevista: date

    dt_fim_prevista: date


    # --------------------------------------------------------
    # GOVERNANÇA
    #
    # Responsável Planejamento será capturado
    # automaticamente pelo login.
    # --------------------------------------------------------

    responsavel_comercial: str

    rito_followup: str

    canal_tratativa_desvios: str

    criterio_encerramento: str

    evidencias_obrigatorias: str


    # --------------------------------------------------------
    # EXECUTOR / ESCOPO / KPI
    # --------------------------------------------------------

    eps: list[EPSCode]

    escopos: list[CampaignScope]

    kpis: list[CampaignKPI]


    # ========================================================
    # VALIDAÇÕES GERAIS
    # ========================================================

    @model_validator(mode="after")
    def validar_campanha(self):

        # Subtipo: obrigatorio em acao comercial, ignorado em incentivo.
        if self.tipo_acao == "INCENTIVO":
            self.subtipo_acao = None
            self.subtipo_acao_outro = None

        else:
            if not self.subtipo_acao:
                raise ValueError(
                    "Escolha o subtipo da ação comercial."
                )

            if self.subtipo_acao == "OUTROS":
                self.subtipo_acao_outro = (
                    (self.subtipo_acao_outro or "").strip()
                    or None
                )

                if not self.subtipo_acao_outro:
                    raise ValueError(
                        "Quando o subtipo for OUTROS, "
                        "descreva o tipo de ação."
                    )
            else:
                self.subtipo_acao_outro = None

        # Vigência
        if (
            self.dt_inicio_prevista
            > self.dt_fim_prevista
        ):

            raise ValueError(
                "A data de início não pode ser "
                "posterior à data de término."
            )


        # EPS
        if not self.eps:

            raise ValueError(
                "Selecione pelo menos uma EPS."
            )


        # Escopo
        if not self.escopos:

            raise ValueError(
                "A campanha precisa possuir "
                "pelo menos um escopo."
            )


        # KPI
        if not self.kpis:

            raise ValueError(
                "A campanha precisa possuir "
                "pelo menos um KPI."
            )


        kpis_principais = [
            kpi
            for kpi in self.kpis
            if kpi.principal is True
        ]


        if len(kpis_principais) != 1:

            raise ValueError(
                "A campanha deve possuir "
                "exatamente um KPI principal."
            )


        # Incentivo
        if self.tipo_acao == "INCENTIVO":

            if not self.incentivo_gatilhos:

                raise ValueError(
                    "Campanha de incentivo exige "
                    "a definição dos gatilhos."
                )

            if not self.incentivo_criterios:

                raise ValueError(
                    "Campanha de incentivo exige "
                    "critérios definidos."
                )

            if not self.incentivo_condicao_pagamento:

                raise ValueError(
                    "Campanha de incentivo exige "
                    "condição de pagamento."
                )


        return self



        # ============================================================
# VALIDAÇÃO COMERCIAL
# ============================================================

class CommercialValidation(BaseModel):

    estrategia_validada: bool

    mecanica_validada: bool

    oferta_argumento_validado: bool

    regras_elegibilidade_validadas: bool

    mensuracao_definida: bool

    atribuicao_definida: bool

    observacao: str | None = None


# ============================================================
# LIBERAÇÃO PARA EPS
# ============================================================

class EPSReleaseRequest(BaseModel):

    eps: list[EPSCode]

    observacao_handoff: str | None = None


    @model_validator(mode="after")
    def validar_eps_liberacao(self):

        if not self.eps:

            raise ValueError(
                "Selecione pelo menos uma EPS "
                "para realizar o handoff."
            )

        return self


# ============================================================
# SOLICITAÇÃO DE PRIMEIRO ACESSO EPS
# ============================================================

class ExternalAccessRequest(BaseModel):

    email: str

    nome_usuario: str | None = None



# ============================================================
# DECISÃO DE ACESSO EPS
# ============================================================

class ExternalAccessDecision(BaseModel):

    decisao: Literal[
        "APROVAR",
        "REJEITAR"
    ]

    motivo: str | None = None


class ExternalAccessDecision(BaseModel):

    decisao: Literal[
        "APROVAR",
        "REJEITAR"
    ]

    motivo: str | None = None



# ============================================================
# FASE 7A
# PLANO OPERACIONAL DA EPS
#
# O preenchimento é incremental.
# Nenhum bloco é obrigatório apenas por existir.
#
# Mailing/base é condicional:
#
# mailing_aplicavel = TRUE
# -> campos de mailing podem ser utilizados e validados.
#
# mailing_aplicavel = FALSE
# -> mailing não se aplica à campanha.
# -> demais campos de mailing podem permanecer NULL.
# -> mailing não poderá bloquear Go-Live ou execução.
# ============================================================

class EPSOperationalPlanUpdate(BaseModel):

    # --------------------------------------------------------
    # RESPONSÁVEIS / ENTENDIMENTO
    # --------------------------------------------------------

    responsavel_eps: str | None = None

    ponto_focal_eps: str | None = None

    entendimento_confirmado: bool | None = None

    pendencias_criticas: str | None = None

    responsavel_resolucao_pendencias: str | None = None

    pendencias_criticas_resolvidas: bool | None = None


    # --------------------------------------------------------
    # MAILING / BASE
    #
    # IMPORTANTE:
    # não é obrigatório para todas as campanhas.
    # Ex.: campanhas de incentivo podem não ter mailing.
    # --------------------------------------------------------

    mailing_aplicavel: bool | None = None

    mailing_previsto: int | None = None

    mailing_recebido: int | None = None

    mailing_disponivel: bool | None = None

    mailing_validado: bool | None = None

    qualidade_mailing_validada: bool | None = None


    # --------------------------------------------------------
    # SEGMENTAÇÃO OPERACIONAL
    # --------------------------------------------------------

    perfil_acionamento: str | None = None

    segmentacao_operacional: str | None = None

    criterios_priorizacao: str | None = None

    criterios_exclusao_operacional: str | None = None

    segmentacao_configurada: bool | None = None

    prioridades_configuradas: bool | None = None

    exclusoes_configuradas: bool | None = None


    # --------------------------------------------------------
    # ABORDAGEM / CANAIS
    # --------------------------------------------------------

    abordagem_modelo: str | None = None

    canais_ativacao: str | None = None


    # --------------------------------------------------------
    # JORNADA / CADÊNCIA
    # --------------------------------------------------------

    dt_inicio_operacional: date | None = None

    dt_fim_operacional: date | None = None

    cadencia_descricao: str | None = None

    frequencia_tentativas: str | None = None

    qtd_tentativas_previstas: int | None = None

    intervalo_acionamento: str | None = None

    jornada_cadencia_definidas: bool | None = None


    # --------------------------------------------------------
    # RECURSOS
    # --------------------------------------------------------

    recursos_necessarios: str | None = None

    canais_recursos_disponiveis: bool | None = None


    # --------------------------------------------------------
    # SCRIPT / ARGUMENTAÇÃO
    # --------------------------------------------------------

    script: str | None = None

    argumentacao: str | None = None

    objecoes: str | None = None

    script_argumentacao_alinhados: bool | None = None


    # --------------------------------------------------------
    # CAPACITAÇÃO
    # --------------------------------------------------------

    capacitacao_realizada: bool | None = None

    dt_capacitacao: datetime | None = None

    capacitacao_descricao: str | None = None


    # --------------------------------------------------------
    # CAPACIDADE OPERACIONAL
    # --------------------------------------------------------

    capacidade_operacional_validada: bool | None = None

    capacidade_descricao: str | None = None

    responsaveis_pontos_focais_definidos: bool | None = None

    data_inicio_confirmada: bool | None = None


    # --------------------------------------------------------
    # REPORTES
    # --------------------------------------------------------

    modelo_frequencia_reporte_acordados: bool | None = None

    frequencia_reporte_eps: str | None = None


    # ========================================================
    # VALIDAÇÕES
    # ========================================================

    @model_validator(mode="after")
    def validar_plano_operacional(self):

        # ----------------------------------------------------
        # MAILING
        #
        # Só há validação quantitativa quando
        # mailing realmente se aplica.
        # ----------------------------------------------------

        if self.mailing_aplicavel is True:

            if (
                self.mailing_previsto is not None
                and
                self.mailing_previsto < 0
            ):

                raise ValueError(
                    "mailing_previsto não pode ser negativo."
                )


            if (
                self.mailing_recebido is not None
                and
                self.mailing_recebido < 0
            ):

                raise ValueError(
                    "mailing_recebido não pode ser negativo."
                )


        # ----------------------------------------------------
        # QUANTIDADE DE TENTATIVAS
        # ----------------------------------------------------

        if (
            self.qtd_tentativas_previstas is not None
            and
            self.qtd_tentativas_previstas < 0
        ):

            raise ValueError(
                "qtd_tentativas_previstas "
                "não pode ser negativa."
            )


        # ----------------------------------------------------
        # DATAS OPERACIONAIS
        # ----------------------------------------------------

        if (
            self.dt_inicio_operacional
            and
            self.dt_fim_operacional
            and
            self.dt_inicio_operacional
            >
            self.dt_fim_operacional
        ):

            raise ValueError(
                "A data de início operacional "
                "não pode ser posterior à data final."
            )


        return self


# ============================================================
# FASE 7B
# CONFIRMAÇÃO DE GO-LIVE DA EPS
# ============================================================

class EPSGoLiveRequest(BaseModel):

    observacao: str | None = None


# ============================================================
# FASE 7C
# INICIAR EXECUÇÃO DA CAMPANHA PELA EPS
# ============================================================

class EPSStartExecutionRequest(BaseModel):

    observacao: str | None = None


# ============================================================
# FASE 7D
# PERFORMANCE DA CAMPANHA
# ============================================================

class EPSPerformanceUpdate(BaseModel):

    data_referencia: date

    # --------------------------------------------------------
    # VOLUMES
    #
    # Todos opcionais.
    # Mailing não é obrigatório.
    # --------------------------------------------------------

    mailing_recebido: int | None = None
    mailing_trabalhado: int | None = None
    tentativas_disparos: int | None = None

    contatos_alo: int | None = None
    produtivos: int | None = None
    interessados: int | None = None
    vendas: int | None = None
    matriculas: int | None = None


    # --------------------------------------------------------
    # TAXAS / INDICADORES
    # --------------------------------------------------------

    pct_trabalhado: Decimal | None = None
    taxa_contato: Decimal | None = None
    taxa_produtividade: Decimal | None = None
    conversao: Decimal | None = None


    # --------------------------------------------------------
    # LEITURA EXECUTIVA
    # --------------------------------------------------------

    cadencia_realizada: str | None = None

    resultado_periodo: str | None = None
    resultado_acumulado: str | None = None
    resultado_vs_objetivo: str | None = None
    resultado_vs_baseline: str | None = None
    resultado_incremental: str | None = None

    aderencia_script: str | None = None
    ocorrencias_relevantes: str | None = None

    origem_vendas_validada: bool | None = None
    observacao_origem: str | None = None


    @model_validator(mode="after")
    def validar_performance(self):

        campos_volume = [
            self.mailing_recebido,
            self.mailing_trabalhado,
            self.tentativas_disparos,
            self.contatos_alo,
            self.produtivos,
            self.interessados,
            self.vendas,
            self.matriculas
        ]

        for valor in campos_volume:

            if (
                valor is not None
                and
                valor < 0
            ):

                raise ValueError(
                    "Volumes de performance "
                    "não podem ser negativos."
                )

        return self


# ============================================================
# FASE 7D
# GAP / DESVIO / AÇÃO CORRETIVA
# ============================================================

class EPSGapUpdate(BaseModel):

    # Se vier preenchido:
    # atualiza um gap existente.
    #
    # Se vier NULL:
    # cria um novo gap.

    gap_uuid: str | None = None

    categoria_gap: str | None = None

    gap: str | None = None

    causa: str | None = None

    acao: str | None = None

    responsavel: str | None = None

    prazo: date | None = None

    status_gap: str | None = None

    mudanca_rota: bool | None = None

    descricao_mudanca_rota: str | None = None


    @model_validator(mode="after")
    def validar_gap(self):

        # Novo gap exige descrição.

        if (
            self.gap_uuid is None
            and
            not self.gap
        ):

            raise ValueError(
                "Para registrar um novo gap, "
                "descreva o gap identificado."
            )


        if (
            self.mudanca_rota is True
            and
            not self.descricao_mudanca_rota
        ):

            raise ValueError(
                "Quando houver mudança de rota, "
                "descreva a mudança."
            )


        return self


# ============================================================
# FASE 7D
# EVIDÊNCIA
# ============================================================

class EPSEvidenceCreate(BaseModel):

    tipo_evidencia: str

    titulo: str

    descricao: str | None = None

    url_evidencia: str | None = None


# ============================================================
# FASE 7D
# ACOMPANHAMENTO CONSOLIDADO
# ============================================================

class EPSMonitoringUpdate(BaseModel):

    performance: EPSPerformanceUpdate | None = None

    gaps: list[EPSGapUpdate] = Field(
        default_factory=list
    )

    evidencias: list[EPSEvidenceCreate] = Field(
        default_factory=list
    )

    observacao_geral: str | None = None


    @model_validator(mode="after")
    def validar_acompanhamento(self):

        if (
            self.performance is None
            and
            not self.gaps
            and
            not self.evidencias
            and
            not self.observacao_geral
        ):

            raise ValueError(
                "Informe pelo menos performance, "
                "gap, evidência ou observação."
            )


        return self


# ============================================================
# FASE 7E
# ENCERRAMENTO DA EXECUÇÃO PELA EPS
# ============================================================

class EPSCloseExecutionRequest(BaseModel):

    # --------------------------------------------------------
    # CONFIRMAÇÃO DE EXECUÇÃO
    # --------------------------------------------------------

    execucao_concluida: bool

    execucao_dentro_vigencia: bool | None = None


    # --------------------------------------------------------
    # RESULTADOS FINAIS
    #
    # Todos opcionais.
    # Mailing não é obrigatório.
    # --------------------------------------------------------

    mailing_final: int | None = None

    mailing_trabalhado_final: int | None = None

    tentativas_disparos_final: int | None = None

    contatos_final: int | None = None

    vendas_final: int | None = None

    matriculas_final: int | None = None


    # --------------------------------------------------------
    # CONSOLIDAÇÃO / ATRIBUIÇÃO
    # --------------------------------------------------------

    vendas_matriculas_consolidadas_atribuicao: bool | None = None

    funil_final_indicadores_encaminhados: bool | None = None


    # --------------------------------------------------------
    # GAPS / AÇÕES
    # --------------------------------------------------------

    principais_gaps: str | None = None

    acoes_corretivas_realizadas: str | None = None

    gaps_acoes_registrados: bool | None = None


    # --------------------------------------------------------
    # EVIDÊNCIAS / APRENDIZADOS
    # --------------------------------------------------------

    evidencias_finais_organizadas: bool | None = None

    ocorrencias_relevantes: str | None = None

    aprendizados_operacionais: str | None = None

    limitacoes_execucao: str | None = None


    # --------------------------------------------------------
    # RESPONSÁVEL PELO FECHAMENTO
    # --------------------------------------------------------

    responsavel_eps_confirmou: bool

    responsavel_fechamento_eps: str


    @model_validator(mode="after")
    def validar_encerramento_eps(self):

        if self.execucao_concluida is not True:

            raise ValueError(
                "Para encerrar a atuação, "
                "a EPS precisa confirmar que "
                "a execução foi concluída."
            )


        if self.responsavel_eps_confirmou is not True:

            raise ValueError(
                "O responsável da EPS precisa "
                "confirmar o encerramento."
            )


        if not self.responsavel_fechamento_eps.strip():

            raise ValueError(
                "Informe o responsável pelo "
                "fechamento da EPS."
            )


        campos_volume = [
            self.mailing_final,
            self.mailing_trabalhado_final,
            self.tentativas_disparos_final,
            self.contatos_final,
            self.vendas_final,
            self.matriculas_final
        ]


        for valor in campos_volume:

            if (
                valor is not None
                and
                valor < 0
            ):

                raise ValueError(
                    "Volumes finais não podem "
                    "ser negativos."
                )


        return self