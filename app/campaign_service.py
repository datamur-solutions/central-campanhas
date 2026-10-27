import uuid

from datetime import datetime, timezone
from decimal import Decimal

from app.db import (
    DATABASE,
    get_connection
)

from app.models import (
    CampaignCreate,
    CommercialValidation,
    EPSReleaseRequest
)




# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def agora_utc():

    return datetime.now(
        timezone.utc
    )


def novo_uuid():

    return str(
        uuid.uuid4()
    )


def decimal_ou_none(valor):

    if valor is None:
        return None

    return Decimal(
        str(valor)
    )


# ============================================================
# INSERT GENÉRICO
# ============================================================

def insert_dict(
    cursor,
    table_name,
    data
):

    colunas = list(
        data.keys()
    )

    placeholders = ", ".join(
        ["?"] * len(colunas)
    )

    sql_insert = f"""
        INSERT INTO {DATABASE}.{table_name}
        (
            {", ".join(colunas)}
        )
        VALUES
        (
            {placeholders}
        )
    """

    valores = [
        data[coluna]
        for coluna in colunas
    ]

    cursor.execute(
        sql_insert,
        parameters=valores
    )


# ============================================================
# GERAR ID OFICIAL CAM-###
# ============================================================

def reservar_codigo_campanha(
    cursor,
    campaign_uuid,
    usuario
):

    cursor.execute(
        f"""
        INSERT INTO {DATABASE}.campanha_id_seq
        (
            campaign_uuid,
            dt_reserva,
            reservado_por
        )
        VALUES
        (
            ?,
            current_timestamp(),
            ?
        )
        """,
        parameters=[
            campaign_uuid,
            usuario
        ]
    )


    cursor.execute(
        f"""
        SELECT
            numero

        FROM {DATABASE}.campanha_id_seq

        WHERE campaign_uuid = ?

        ORDER BY numero DESC

        LIMIT 1
        """,
        parameters=[
            campaign_uuid
        ]
    )


    resultado = cursor.fetchone()


    if not resultado:

        raise RuntimeError(
            "Não foi possível gerar "
            "o número da campanha."
        )


    numero = int(
        resultado[0]
    )


    return f"CAM-{numero:03d}"


# ============================================================
# BUSCAR DESTINATÁRIOS INTERNOS
# ============================================================

def buscar_destinatarios_internos(
    cursor
):

    cursor.execute(
        f"""
        SELECT
            email_usuario

        FROM
            {DATABASE}.
            vw_destinatarios_notificacao_campanha

        ORDER BY email_usuario
        """
    )


    emails = [
        linha[0]
        for linha in cursor.fetchall()
        if linha[0]
    ]


    return ";".join(
        emails
    )


# ============================================================
# CRIAR CAMPANHA
# ============================================================

def criar_campanha(
    payload: CampaignCreate,
    usuario_email: str
):

    campaign_uuid = novo_uuid()

    agora = agora_utc()


    # --------------------------------------------------------
    # PRODUTO MASTER
    #
    # Se houver mais de um produto:
    # MULTIPRODUTO
    # --------------------------------------------------------

    produtos = sorted(
        {
            escopo.produto
            for escopo in payload.escopos
        }
    )


    if len(produtos) == 1:

        produto_master = produtos[0]

    else:

        produto_master = "MULTIPRODUTO"


    with get_connection() as connection:

        cursor = connection.cursor()

        try:

            # =================================================
            # 1. GERAR ID CAM-###
            # =================================================

            codigo_campanha = (
                reservar_codigo_campanha(
                    cursor,
                    campaign_uuid,
                    usuario_email
                )
            )


            # =================================================
            # 2. CAMPANHA MASTER
            # =================================================

            master = {

                "campaign_uuid":
                    campaign_uuid,

                "codigo_campanha":
                    codigo_campanha,

                "nome_campanha":
                    payload.nome_campanha,

                "produto":
                    produto_master,

                "tipo_acao":
                    payload.tipo_acao,

                "subtipo_acao":
                    payload.subtipo_acao,

                "subtipo_acao_outro":
                    payload.subtipo_acao_outro,

                # ---------------------------------------------
                # OPORTUNIDADE
                # ---------------------------------------------

                "oportunidade_problema":
                    payload.oportunidade_problema,

                "fonte_oportunidade":
                    payload.fonte_oportunidade,

                "indicador_evidencia_oportunidade":
                    (
                        payload.
                        indicador_evidencia_oportunidade
                    ),

                "etapa_funil_alvo":
                    payload.etapa_funil_alvo,

                "publico_alvo":
                    payload.publico_alvo,

                "segmentacao":
                    payload.segmentacao,

                "criterio_elegibilidade":
                    payload.criterio_elegibilidade,

                "criterio_exclusao":
                    payload.criterio_exclusao,

                "dimensao_estimada":
                    payload.dimensao_estimada,

                # ---------------------------------------------
                # ESTRATÉGIA
                # ---------------------------------------------

                "estrategia":
                    payload.estrategia,

                "mecanica":
                    payload.mecanica,

                "oferta_beneficio":
                    payload.oferta_beneficio,

                "argumento_comercial":
                    payload.argumento_comercial,

                "regras_comerciais":
                    payload.regras_comerciais,

                "condicoes_especificas":
                    payload.condicoes_especificas,

                "canais_possiveis":
                    payload.canais_possiveis,

                # ---------------------------------------------
                # INCENTIVO
                # ---------------------------------------------

                "incentivo_aplicavel":
                    (
                        payload.tipo_acao
                        == "INCENTIVO"
                    ),

                "incentivo_gatilhos":
                    payload.incentivo_gatilhos,

                "incentivo_criterios":
                    payload.incentivo_criterios,

                "incentivo_condicao_pagamento":
                    (
                        payload.
                        incentivo_condicao_pagamento
                    ),

                # ---------------------------------------------
                # OBJETIVO
                # ---------------------------------------------

                "objetivo_campanha":
                    payload.objetivo_campanha,

                "resultado_esperado":
                    payload.resultado_esperado,

                # ---------------------------------------------
                # VIGÊNCIA
                # ---------------------------------------------

                "dt_inicio_prevista":
                    payload.dt_inicio_prevista,

                "dt_fim_prevista":
                    payload.dt_fim_prevista,

                # ---------------------------------------------
                # RESPONSÁVEIS
                #
                # Planejamento vem do login.
                # ---------------------------------------------

                "responsavel_planejamento":
                    usuario_email,

                "responsavel_comercial":
                    payload.responsavel_comercial,

                # ---------------------------------------------
                # VALIDAÇÕES
                #
                # O Comercial ainda precisa validar.
                # ---------------------------------------------

                "estrategia_validada":
                    False,

                "mecanica_validada":
                    False,

                "oferta_argumento_validado":
                    False,

                "regras_elegibilidade_validadas":
                    False,

                # Mensuração e atribuição já foram
                # definidas no cadastro dos KPIs.

                "mensuracao_definida":
                    True,

                "atribuicao_definida":
                    True,

                "registrado_calendario":
                    False,

                # ---------------------------------------------
                # GOVERNANÇA
                # ---------------------------------------------

                "rito_followup":
                    payload.rito_followup,

                "canal_tratativa_desvios":
                    (
                        payload.
                        canal_tratativa_desvios
                    ),

                "criterio_encerramento":
                    payload.criterio_encerramento,

                "evidencias_obrigatorias":
                    payload.evidencias_obrigatorias,

                # ---------------------------------------------
                # WORKFLOW INICIAL
                # ---------------------------------------------

                "etapa_pop":
                    "OBJETIVO_KPIS",

                "status_campanha":
                    "CADASTRADA_PLANEJAMENTO",

                # ---------------------------------------------
                # AUDITORIA
                # ---------------------------------------------

                "dt_criacao":
                    agora,

                "criado_por":
                    usuario_email
            }


            insert_dict(
                cursor,
                "campanha_master",
                master
            )


            # =================================================
            # 3. KPIs
            # =================================================

            for kpi in payload.kpis:

                linha_kpi = {

                    "campanha_kpi_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "nome_kpi":
                        kpi.nome_kpi,

                    "kpi_principal":
                        kpi.principal,

                    "descricao_kpi":
                        kpi.descricao_kpi,

                    "baseline_tipo":
                        kpi.baseline_tipo,

                    "baseline_descricao":
                        kpi.baseline_descricao,

                    "baseline_valor":
                        decimal_ou_none(
                            kpi.baseline_valor
                        ),

                    "meta_descricao":
                        kpi.meta_descricao,

                    "meta_valor":
                        decimal_ou_none(
                            kpi.meta_valor
                        ),

                    "unidade_medida":
                        kpi.unidade_medida,

                    "regra_atribuicao":
                        kpi.regra_atribuicao,

                    "frequencia_reporte":
                        kpi.frequencia_reporte,

                    "ritmo_esperado":
                        kpi.ritmo_esperado,

                    "ativo":
                        True,

                    "dt_criacao":
                        agora,

                    "criado_por":
                        usuario_email
                }


                insert_dict(
                    cursor,
                    "campanha_kpi",
                    linha_kpi
                )


            # =================================================
            # 4. ESCOPOS
            # =================================================

            escopos_criados = []


            for escopo in payload.escopos:

                escopo_uuid = novo_uuid()


                linha_escopo = {

                    "escopo_uuid":
                        escopo_uuid,

                    "campaign_uuid":
                        campaign_uuid,

                    "produto":
                        escopo.produto,

                    "frente_pos":
                        escopo.frente_pos,

                    "supercanal":
                        escopo.supercanal,

                    "outro_supercanal_descricao":
                        (
                            escopo.
                            outro_supercanal_descricao
                        ),

                    "modalidade":
                        escopo.modalidade,

                    "ativo":
                        True,

                    "dt_criacao":
                        agora,

                    "criado_por":
                        usuario_email
                }


                insert_dict(
                    cursor,
                    "campanha_escopo",
                    linha_escopo
                )


                escopos_criados.append(
                    escopo_uuid
                )


            # =================================================
            # 5. EPS EXECUTORAS
            #
            # IMPORTANTE:
            # campanha nasce vinculada à EPS,
            # mas ainda NÃO é liberada para visualização.
            # =================================================

            campanhas_eps_criadas = []


            for eps in payload.eps:

                campanha_eps_uuid = (
                    novo_uuid()
                )


                linha_eps = {

                    "campanha_eps_uuid":
                        campanha_eps_uuid,

                    "campaign_uuid":
                        campaign_uuid,

                    "eps":
                        eps,

                    "liberada_para_eps":
                        False,

                    "status_execucao_eps":
                        None,

                    "dt_criacao":
                        agora,

                    "criado_por":
                        usuario_email
                }


                insert_dict(
                    cursor,
                    "campanha_eps",
                    linha_eps
                )


                campanhas_eps_criadas.append(
                    {
                        "campanha_eps_uuid":
                            campanha_eps_uuid,

                        "eps":
                            eps
                    }
                )


            # =================================================
            # 6. VÍNCULO EPS × ESCOPO
            #
            # Neste primeiro modelo:
            # todas as EPS selecionadas recebem
            # todos os escopos da campanha.
            # =================================================

            for campanha_eps in (
                campanhas_eps_criadas
            ):

                for escopo_uuid in (
                    escopos_criados
                ):

                    insert_dict(
                        cursor,
                        "campanha_eps_escopo",
                        {

                            "campanha_eps_escopo_uuid":
                                novo_uuid(),

                            "campanha_eps_uuid":
                                (
                                    campanha_eps[
                                        "campanha_eps_uuid"
                                    ]
                                ),

                            "escopo_uuid":
                                escopo_uuid,

                            "ativo":
                                True,

                            "dt_criacao":
                                agora,

                            "criado_por":
                                usuario_email
                        }
                    )


            # =================================================
            # 7. WORKFLOW
            # =================================================

            insert_dict(
                cursor,
                "campanha_workflow",
                {

                    "workflow_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "campanha_eps_uuid":
                        None,

                    "eps":
                        None,

                    "escopo":
                        "CAMPANHA",

                    "status_anterior":
                        "RASCUNHO_PLANEJAMENTO",

                    "status_novo":
                        "CADASTRADA_PLANEJAMENTO",

                    "etapa_pop":
                        "OBJETIVO_KPIS",

                    "origem":
                        "PLANEJAMENTO",

                    "usuario":
                        usuario_email,

                    "dt_evento":
                        agora,

                    "observacao":
                        (
                            "Campanha cadastrada "
                            "pelo Planejamento."
                        ),

                    "dispara_email":
                        True,

                    "tipo_evento_email":
                        (
                            "CAMPANHA_"
                            "CADASTRADA_PLANEJAMENTO"
                        )
                }
            )


            # =================================================
            # 8. HISTÓRICO
            # =================================================

            insert_dict(
                cursor,
                "campanha_historico",
                {

                    "historico_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "data_hora":
                        agora,

                    "usuario":
                        usuario_email,

                    "origem":
                        "PLANEJAMENTO",

                    "evento":
                        "CRIACAO_CAMPANHA",

                    "campo_alterado":
                        "status_campanha",

                    "valor_anterior":
                        None,

                    "valor_novo":
                        "CADASTRADA_PLANEJAMENTO",

                    "observacao":
                        (
                            f"Campanha "
                            f"{codigo_campanha} "
                            f"criada pelo Planejamento."
                        )
                }
            )


            # =================================================
            # 9. FILA DE NOTIFICAÇÃO
            # =================================================

            destinatarios = (
                buscar_destinatarios_internos(
                    cursor
                )
            )


            insert_dict(
                cursor,
                "campanha_notificacao",
                {

                    "notificacao_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "campanha_eps_uuid":
                        None,

                    "eps":
                        None,

                    "tipo_evento":
                        (
                            "CAMPANHA_"
                            "CADASTRADA_PLANEJAMENTO"
                        ),

                    "assunto":
                        (
                            "[Central de Campanhas] "
                            "Nova campanha | "
                            f"{codigo_campanha} - "
                            f"{payload.nome_campanha}"
                        ),

                    "destinatarios_to":
                        destinatarios,

                    "destinatarios_cc":
                        None,

                    "resumo_evento":
                        (
                            "Nova campanha cadastrada "
                            "pelo Planejamento."
                        ),

                    "status_envio":
                        "PENDENTE",

                    "tentativas_envio":
                        0,

                    "dt_criacao":
                        agora
                }
            )


            # =================================================
            # RETORNO
            # =================================================

            return {

                "campaign_uuid":
                    campaign_uuid,

                "codigo_campanha":
                    codigo_campanha,

                "nome_campanha":
                    payload.nome_campanha,

                "status_campanha":
                    "CADASTRADA_PLANEJAMENTO",

                "eps":
                    payload.eps,

                "quantidade_escopos":
                    len(payload.escopos),

                "quantidade_kpis":
                    len(payload.kpis),

                "liberada_para_eps":
                    False
            }


        finally:

            cursor.close()


    # ============================================================
# ENVIAR CAMPANHA PARA O COMERCIAL
# ============================================================

def enviar_para_comercial(
    codigo_campanha: str,
    usuario_email: str
):

    agora = agora_utc()


    with get_connection() as connection:

        cursor = connection.cursor()

        try:

            # ------------------------------------------------
            # 1. BUSCAR A CAMPANHA
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT

                    campaign_uuid,

                    nome_campanha,

                    status_campanha,

                    responsavel_comercial

                FROM {DATABASE}.campanha_master

                WHERE codigo_campanha = ?

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ]
            )


            resultado = cursor.fetchone()


            if not resultado:

                raise ValueError(
                    "Campanha não encontrada."
                )


            campaign_uuid = resultado[0]

            nome_campanha = resultado[1]

            status_atual = resultado[2]

            responsavel_comercial = resultado[3]


            # ------------------------------------------------
            # 2. VALIDAR STATUS ATUAL
            # ------------------------------------------------

            if (
                status_atual
                != "CADASTRADA_PLANEJAMENTO"
            ):

                raise ValueError(
                    "A campanha não está mais no status "
                    "CADASTRADA_PLANEJAMENTO."
                )


            # ------------------------------------------------
            # 3. ATUALIZAR MASTER
            # ------------------------------------------------

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_master

                SET

                    status_campanha =
                        'EM_VALIDACAO_COMERCIAL',

                    etapa_pop =
                        'EXECUTOR',

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campaign_uuid = ?
                """,
                parameters=[
                    agora,
                    usuario_email,
                    campaign_uuid
                ]
            )


            # ------------------------------------------------
            # 4. WORKFLOW
            # ------------------------------------------------

            insert_dict(
                cursor,
                "campanha_workflow",
                {

                    "workflow_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "campanha_eps_uuid":
                        None,

                    "eps":
                        None,

                    "escopo":
                        "CAMPANHA",

                    "status_anterior":
                        "CADASTRADA_PLANEJAMENTO",

                    "status_novo":
                        "EM_VALIDACAO_COMERCIAL",

                    "etapa_pop":
                        "EXECUTOR",

                    "origem":
                        "PLANEJAMENTO",

                    "usuario":
                        usuario_email,

                    "dt_evento":
                        agora,

                    "observacao":
                        (
                            "Campanha encaminhada "
                            "para validação Comercial."
                        ),

                    "dispara_email":
                        True,

                    "tipo_evento_email":
                        "CAMPANHA_COM_COMERCIAL"
                }
            )


            # ------------------------------------------------
            # 5. HISTÓRICO
            # ------------------------------------------------

            insert_dict(
                cursor,
                "campanha_historico",
                {

                    "historico_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "data_hora":
                        agora,

                    "usuario":
                        usuario_email,

                    "origem":
                        "PLANEJAMENTO",

                    "evento":
                        "ENVIO_COMERCIAL",

                    "campo_alterado":
                        "status_campanha",

                    "valor_anterior":
                        "CADASTRADA_PLANEJAMENTO",

                    "valor_novo":
                        "EM_VALIDACAO_COMERCIAL",

                    "observacao":
                        (
                            "Campanha encaminhada "
                            "para o Comercial."
                        )
                }
            )


            # ------------------------------------------------
            # 6. DESTINATÁRIOS INTERNOS
            # ------------------------------------------------

            destinatarios = (
                buscar_destinatarios_internos(
                    cursor
                )
            )


            # ------------------------------------------------
            # 7. FILA DE NOTIFICAÇÃO
            # ------------------------------------------------

            insert_dict(
                cursor,
                "campanha_notificacao",
                {

                    "notificacao_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "campanha_eps_uuid":
                        None,

                    "eps":
                        None,

                    "tipo_evento":
                        "CAMPANHA_COM_COMERCIAL",

                    "assunto":
                        (
                            "[Central de Campanhas] "
                            "Campanha com Comercial | "
                            f"{codigo_campanha} - "
                            f"{nome_campanha}"
                        ),

                    "destinatarios_to":
                        destinatarios,

                    "destinatarios_cc":
                        None,

                    "resumo_evento":
                        (
                            "Campanha encaminhada "
                            "para validação Comercial."
                        ),

                    "status_envio":
                        "PENDENTE",

                    "tentativas_envio":
                        0,

                    "dt_criacao":
                        agora
                }
            )


            # ------------------------------------------------
            # 8. RETORNO
            # ------------------------------------------------

            return {

                "codigo_campanha":
                    codigo_campanha,

                "nome_campanha":
                    nome_campanha,

                "status_anterior":
                    "CADASTRADA_PLANEJAMENTO",

                "status_campanha":
                    "EM_VALIDACAO_COMERCIAL",

                "responsavel_comercial":
                    responsavel_comercial
            }


        finally:

            cursor.close()


    # ============================================================
# VALIDAR CAMPANHA PELO COMERCIAL
# ============================================================

def validar_comercial(
    codigo_campanha: str,
    payload: CommercialValidation,
    usuario_email: str
):

    agora = agora_utc()


    with get_connection() as connection:

        cursor = connection.cursor()

        try:

            # ------------------------------------------------
            # 1. BUSCAR CAMPANHA
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT

                    campaign_uuid,

                    nome_campanha,

                    status_campanha

                FROM {DATABASE}.campanha_master

                WHERE codigo_campanha = ?

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ]
            )


            resultado = cursor.fetchone()


            if not resultado:

                raise ValueError(
                    "Campanha não encontrada."
                )


            campaign_uuid = resultado[0]

            nome_campanha = resultado[1]

            status_atual = resultado[2]


            # ------------------------------------------------
            # 2. STATUS PERMITIDO
            # ------------------------------------------------

            if (
                status_atual
                != "EM_VALIDACAO_COMERCIAL"
            ):

                raise ValueError(
                    "A campanha precisa estar em "
                    "EM_VALIDACAO_COMERCIAL."
                )


            # ------------------------------------------------
            # 3. VERIFICAR SE TODAS AS VALIDAÇÕES
            #    FORAM CONCLUÍDAS
            # ------------------------------------------------

            validacoes = [

                payload.estrategia_validada,

                payload.mecanica_validada,

                payload.oferta_argumento_validado,

                payload.regras_elegibilidade_validadas,

                payload.mensuracao_definida,

                payload.atribuicao_definida
            ]


            todas_validas = all(
                validacoes
            )


            novo_status = (

                "VALIDADA_COMERCIAL"

                if todas_validas

                else "EM_VALIDACAO_COMERCIAL"
            )


            nova_etapa = (

                "HANDOFF_PLANO_EPS"

                if todas_validas

                else "EXECUTOR"
            )


            # ------------------------------------------------
            # 4. ATUALIZAR MASTER
            # ------------------------------------------------

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_master

                SET

                    estrategia_validada = ?,

                    mecanica_validada = ?,

                    oferta_argumento_validado = ?,

                    regras_elegibilidade_validadas = ?,

                    mensuracao_definida = ?,

                    atribuicao_definida = ?,

                    status_campanha = ?,

                    etapa_pop = ?,

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campaign_uuid = ?
                """,
                parameters=[

                    payload.estrategia_validada,

                    payload.mecanica_validada,

                    payload.oferta_argumento_validado,

                    payload.regras_elegibilidade_validadas,

                    payload.mensuracao_definida,

                    payload.atribuicao_definida,

                    novo_status,

                    nova_etapa,

                    agora,

                    usuario_email,

                    campaign_uuid
                ]
            )


            # ------------------------------------------------
            # 5. HISTÓRICO
            # ------------------------------------------------

            insert_dict(
                cursor,
                "campanha_historico",
                {

                    "historico_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "data_hora":
                        agora,

                    "usuario":
                        usuario_email,

                    "origem":
                        "COMERCIAL",

                    "evento":
                        "VALIDACAO_COMERCIAL",

                    "campo_alterado":
                        "status_campanha",

                    "valor_anterior":
                        status_atual,

                    "valor_novo":
                        novo_status,

                    "observacao":
                        (
                            payload.observacao
                            or
                            "Validação Comercial realizada."
                        )
                }
            )


            # ------------------------------------------------
            # 6. SE TODAS AS VALIDAÇÕES ESTIVEREM OK,
            #    REGISTRAR TRANSIÇÃO NO WORKFLOW
            # ------------------------------------------------

            if todas_validas:

                insert_dict(
                    cursor,
                    "campanha_workflow",
                    {

                        "workflow_uuid":
                            novo_uuid(),

                        "campaign_uuid":
                            campaign_uuid,

                        "campanha_eps_uuid":
                            None,

                        "eps":
                            None,

                        "escopo":
                            "CAMPANHA",

                        "status_anterior":
                            "EM_VALIDACAO_COMERCIAL",

                        "status_novo":
                            "VALIDADA_COMERCIAL",

                        "etapa_pop":
                            "HANDOFF_PLANO_EPS",

                        "origem":
                            "COMERCIAL",

                        "usuario":
                            usuario_email,

                        "dt_evento":
                            agora,

                        "observacao":
                            (
                                "Validação Comercial concluída. "
                                "Campanha pronta para handoff."
                            ),

                        "dispara_email":
                            False,

                        "tipo_evento_email":
                            None
                    }
                )


            return {

                "codigo_campanha":
                    codigo_campanha,

                "nome_campanha":
                    nome_campanha,

                "todas_validacoes_concluidas":
                    todas_validas,

                "status_campanha":
                    novo_status,

                "etapa_pop":
                    nova_etapa
            }


        finally:

            cursor.close()



    # ============================================================
# LIBERAR CAMPANHA PARA EPS
# ============================================================

def liberar_para_eps(
    codigo_campanha: str,
    payload: EPSReleaseRequest,
    usuario_email: str
):

    agora = agora_utc()


    with get_connection() as connection:

        cursor = connection.cursor()

        try:

            # ------------------------------------------------
            # 1. BUSCAR CAMPANHA
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT

                    campaign_uuid,

                    nome_campanha,

                    status_campanha

                FROM {DATABASE}.campanha_master

                WHERE codigo_campanha = ?

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ]
            )


            resultado = cursor.fetchone()


            if not resultado:

                raise ValueError(
                    "Campanha não encontrada."
                )


            campaign_uuid = resultado[0]

            nome_campanha = resultado[1]

            status_atual = resultado[2]


            # ------------------------------------------------
            # 2. CAMPANHA PRECISA TER SIDO VALIDADA
            # ------------------------------------------------

            if status_atual not in [

                "VALIDADA_COMERCIAL",

                "LIBERACAO_PARCIAL_EPS"
            ]:

                raise ValueError(
                    "A campanha precisa estar "
                    "validada pelo Comercial "
                    "antes do handoff."
                )


            # ------------------------------------------------
            # 3. BUSCAR EPS VINCULADAS À CAMPANHA
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT

                    campanha_eps_uuid,

                    eps,

                    liberada_para_eps

                FROM {DATABASE}.campanha_eps

                WHERE campaign_uuid = ?
                """,
                parameters=[
                    campaign_uuid
                ]
            )


            eps_registradas = (
                cursor.fetchall()
            )


            mapa_eps = {

                linha[1]: {

                    "campanha_eps_uuid":
                        linha[0],

                    "liberada_para_eps":
                        linha[2]
                }

                for linha in eps_registradas
            }


            # ------------------------------------------------
            # 4. VALIDAR SE AS EPS SOLICITADAS
            #    REALMENTE PERTENCEM À CAMPANHA
            # ------------------------------------------------

            for eps in payload.eps:

                if eps not in mapa_eps:

                    raise ValueError(
                        f"A EPS {eps} não está "
                        "vinculada a esta campanha."
                    )


            eps_liberadas_agora = []


            # ------------------------------------------------
            # 5. LIBERAR CADA EPS
            # ------------------------------------------------

            for eps in payload.eps:

                dados_eps = mapa_eps[
                    eps
                ]


                campanha_eps_uuid = (
                    dados_eps[
                        "campanha_eps_uuid"
                    ]
                )


                # Já liberada:
                # não duplicamos eventos.

                if (
                    dados_eps[
                        "liberada_para_eps"
                    ]
                    is True
                ):

                    continue


                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.campanha_eps

                    SET

                        liberada_para_eps = TRUE,

                        dt_liberacao_eps = ?,

                        dt_handoff = ?,

                        status_execucao_eps =
                            'AGUARDANDO_PLANEJAMENTO_EPS',

                        dt_atualizacao = ?,

                        atualizado_por = ?

                    WHERE campanha_eps_uuid = ?
                    """,
                    parameters=[

                        agora,

                        agora,

                        agora,

                        usuario_email,

                        campanha_eps_uuid
                    ]
                )


                # --------------------------------------------
                # WORKFLOW POR EPS
                # --------------------------------------------

                insert_dict(
                    cursor,
                    "campanha_workflow",
                    {

                        "workflow_uuid":
                            novo_uuid(),

                        "campaign_uuid":
                            campaign_uuid,

                        "campanha_eps_uuid":
                            campanha_eps_uuid,

                        "eps":
                            eps,

                        "escopo":
                            "EPS",

                        "status_anterior":
                            "NAO_LIBERADA",

                        "status_novo":
                            "AGUARDANDO_PLANEJAMENTO_EPS",

                        "etapa_pop":
                            "HANDOFF_PLANO_EPS",

                        "origem":
                            "COMERCIAL",

                        "usuario":
                            usuario_email,

                        "dt_evento":
                            agora,

                        "observacao":
                            (
                                payload.
                                observacao_handoff
                                or
                                (
                                    "Campanha liberada "
                                    f"para {eps}."
                                )
                            ),

                        "dispara_email":
                            True,

                        "tipo_evento_email":
                            "CAMPANHA_ENVIADA_EPS"
                    }
                )


                # --------------------------------------------
                # HISTÓRICO
                # --------------------------------------------

                insert_dict(
                    cursor,
                    "campanha_historico",
                    {

                        "historico_uuid":
                            novo_uuid(),

                        "campaign_uuid":
                            campaign_uuid,

                        "data_hora":
                            agora,

                        "usuario":
                            usuario_email,

                        "origem":
                            "COMERCIAL",

                        "evento":
                            "LIBERACAO_EPS",

                        "campo_alterado":
                            "liberada_para_eps",

                        "valor_anterior":
                            "FALSE",

                        "valor_novo":
                            "TRUE",

                        "observacao":
                            (
                                "Campanha liberada "
                                f"para EPS {eps}."
                            )
                    }
                )


                # --------------------------------------------
                # NOTIFICAÇÃO
                # --------------------------------------------

                destinatarios = (
                    buscar_destinatarios_internos(
                        cursor
                    )
                )


                insert_dict(
                    cursor,
                    "campanha_notificacao",
                    {

                        "notificacao_uuid":
                            novo_uuid(),

                        "campaign_uuid":
                            campaign_uuid,

                        "campanha_eps_uuid":
                            campanha_eps_uuid,

                        "eps":
                            eps,

                        "tipo_evento":
                            "CAMPANHA_ENVIADA_EPS",

                        "assunto":
                            (
                                "[Central de Campanhas] "
                                f"Campanha enviada à {eps} | "
                                f"{codigo_campanha} - "
                                f"{nome_campanha}"
                            ),

                        "destinatarios_to":
                            destinatarios,

                        "destinatarios_cc":
                            None,

                        "resumo_evento":
                            (
                                f"Campanha liberada "
                                f"para atuação da {eps}."
                            ),

                        "status_envio":
                            "PENDENTE",

                        "tentativas_envio":
                            0,

                        "dt_criacao":
                            agora
                    }
                )


                eps_liberadas_agora.append(
                    eps
                )


            # ------------------------------------------------
            # 6. VERIFICAR SE TODAS AS EPS
            #    DA CAMPANHA JÁ FORAM LIBERADAS
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT

                    COUNT(*) AS total_eps,

                    SUM(
                        CASE
                            WHEN liberada_para_eps = TRUE
                            THEN 1
                            ELSE 0
                        END
                    ) AS total_liberadas

                FROM {DATABASE}.campanha_eps

                WHERE campaign_uuid = ?
                """,
                parameters=[
                    campaign_uuid
                ]
            )


            contagem = cursor.fetchone()


            total_eps = int(
                contagem[0]
                or 0
            )


            total_liberadas = int(
                contagem[1]
                or 0
            )


            todas_liberadas = (
                total_eps > 0
                and
                total_eps == total_liberadas
            )


            # ------------------------------------------------
            # 7. STATUS MASTER
            # ------------------------------------------------

            novo_status_master = (

                "ENVIADA_EPS"

                if todas_liberadas

                else "LIBERACAO_PARCIAL_EPS"
            )


            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_master

                SET

                    status_campanha = ?,

                    etapa_pop =
                        'HANDOFF_PLANO_EPS',

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campaign_uuid = ?
                """,
                parameters=[

                    novo_status_master,

                    agora,

                    usuario_email,

                    campaign_uuid
                ]
            )


            return {

                "codigo_campanha":
                    codigo_campanha,

                "nome_campanha":
                    nome_campanha,

                "eps_liberadas_agora":
                    eps_liberadas_agora,

                "total_eps":
                    total_eps,

                "total_eps_liberadas":
                    total_liberadas,

                "todas_eps_liberadas":
                    todas_liberadas,

                "status_campanha":
                    novo_status_master
            }


        finally:

            cursor.close()