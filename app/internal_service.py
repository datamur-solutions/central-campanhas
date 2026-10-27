from app.db import (
    DATABASE,
    get_connection,
)


def _row_to_dict(cursor, row):
    if not row:
        return None

    columns = [
        description[0]
        for description in cursor.description
    ]

    return dict(
        zip(
            columns,
            row,
        )
    )


def _rows_to_dict(cursor, rows):
    columns = [
        description[0]
        for description in cursor.description
    ]

    return [
        dict(
            zip(
                columns,
                row,
            )
        )
        for row in rows
    ]


def obter_detalhe_campanha_interna(
    codigo_campanha: str,
):
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            # =================================================
            # CAMPANHA MASTER
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    campaign_uuid,
                    codigo_campanha,
                    nome_campanha,
                    produto,
                    tipo_acao,
                    subtipo_acao,
                    subtipo_acao_outro,

                    oportunidade_problema,
                    fonte_oportunidade,
                    indicador_evidencia_oportunidade,
                    etapa_funil_alvo,
                    publico_alvo,
                    segmentacao,
                    criterio_elegibilidade,
                    criterio_exclusao,
                    dimensao_estimada,

                    estrategia,
                    mecanica,
                    oferta_beneficio,
                    argumento_comercial,
                    regras_comerciais,
                    condicoes_especificas,
                    canais_possiveis,

                    incentivo_aplicavel,
                    incentivo_gatilhos,
                    incentivo_criterios,
                    incentivo_condicao_pagamento,

                    objetivo_campanha,
                    resultado_esperado,

                    dt_inicio_prevista,
                    dt_fim_prevista,

                    responsavel_planejamento,
                    responsavel_comercial,

                    estrategia_validada,
                    mecanica_validada,
                    oferta_argumento_validado,
                    regras_elegibilidade_validadas,
                    mensuracao_definida,
                    atribuicao_definida,

                    rito_followup,
                    canal_tratativa_desvios,
                    criterio_encerramento,
                    evidencias_obrigatorias,

                    etapa_pop,
                    status_campanha,

                    dt_criacao,
                    criado_por,
                    dt_atualizacao,
                    atualizado_por

                FROM {DATABASE}.campanha_master

                WHERE upper(codigo_campanha) =
                      upper(?)

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ]
            )

            campanha = _row_to_dict(
                cursor,
                cursor.fetchone()
            )

            if not campanha:
                raise ValueError(
                    "Campanha não encontrada."
                )

            campaign_uuid = (
                campanha["campaign_uuid"]
            )

            # =================================================
            # EPS
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    campanha_eps_uuid,
                    eps,
                    liberada_para_eps,
                    dt_liberacao_eps,
                    dt_handoff,

                    status_execucao_eps,

                    responsavel_eps,
                    ponto_focal_eps,
                    entendimento_confirmado,

                    mailing_aplicavel,
                    mailing_previsto,
                    mailing_recebido,

                    go_live_aprovado,
                    dt_go_live,
                    operacao_ativada,

                    dt_inicio_operacional,
                    dt_fim_operacional,

                    atualizado_por,
                    dt_atualizacao

                FROM {DATABASE}.campanha_eps

                WHERE campaign_uuid = ?

                ORDER BY eps
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            eps = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # =================================================
            # ESCOPOS
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    escopo_uuid,
                    produto,
                    frente_pos,
                    supercanal,
                    outro_supercanal_descricao,
                    modalidade,
                    ativo

                FROM {DATABASE}.campanha_escopo

                WHERE campaign_uuid = ?

                ORDER BY
                    produto,
                    supercanal,
                    modalidade
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            escopos = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # =================================================
            # KPIs
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    campanha_kpi_uuid,
                    nome_kpi,
                    kpi_principal,
                    descricao_kpi,
                    baseline_tipo,
                    baseline_descricao,
                    baseline_valor,
                    meta_descricao,
                    meta_valor,
                    unidade_medida,
                    regra_atribuicao,
                    frequencia_reporte,
                    ritmo_esperado,
                    ativo

                FROM {DATABASE}.campanha_kpi

                WHERE campaign_uuid = ?

                ORDER BY
                    kpi_principal DESC,
                    nome_kpi
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            kpis = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # =================================================
            # PERFORMANCE
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    performance_uuid,
                    eps,
                    data_referencia,
                    mailing_recebido,
                    mailing_trabalhado,
                    tentativas_disparos,
                    contatos_alo,
                    produtivos,
                    interessados,
                    vendas,
                    matriculas,
                    pct_trabalhado,
                    taxa_contato,
                    taxa_produtividade,
                    conversao,
                    resultado_periodo,
                    resultado_acumulado,
                    resultado_vs_objetivo,
                    resultado_vs_baseline,
                    resultado_incremental,
                    aderencia_script,
                    ocorrencias_relevantes,
                    origem_vendas_validada,
                    observacao_origem,
                    dt_carga,
                    carregado_por

                FROM {DATABASE}.campanha_performance

                WHERE campaign_uuid = ?

                ORDER BY
                    data_referencia DESC,
                    eps
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            performance = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # =================================================
            # GAPS
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    gap_uuid,
                    eps,
                    dt_identificacao,
                    categoria_gap,
                    gap,
                    causa,
                    acao,
                    responsavel,
                    prazo,
                    status_gap,
                    mudanca_rota,
                    descricao_mudanca_rota,
                    dt_resolucao,
                    criado_por,
                    dt_criacao

                FROM {DATABASE}.campanha_gap

                WHERE campaign_uuid = ?

                ORDER BY
                    dt_criacao DESC
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            gaps = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # =================================================
            # EVIDÊNCIAS
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    evidencia_uuid,
                    eps,
                    tipo_evidencia,
                    titulo,
                    descricao,
                    url_evidencia,
                    dt_evidencia,
                    validada,
                    validada_por,
                    dt_validacao,
                    criado_por,
                    dt_criacao

                FROM {DATABASE}.campanha_evidencia

                WHERE campaign_uuid = ?

                ORDER BY
                    dt_criacao DESC
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            evidencias = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # =================================================
            # WORKFLOW
            # =================================================
            cursor.execute(
                f"""
                SELECT
                    workflow_uuid,
                    eps,
                    escopo,
                    status_anterior,
                    status_novo,
                    etapa_pop,
                    origem,
                    usuario,
                    dt_evento,
                    observacao,
                    dispara_email,
                    tipo_evento_email

                FROM {DATABASE}.campanha_workflow

                WHERE campaign_uuid = ?

                ORDER BY
                    dt_evento DESC
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            workflow = _rows_to_dict(
                cursor,
                cursor.fetchall()
            )

            # UUID interno não precisa ser exposto
            campanha.pop(
                "campaign_uuid",
                None
            )

            return {
                "campanha":
                    campanha,

                "eps":
                    eps,

                "escopos":
                    escopos,

                "kpis":
                    kpis,

                "performance":
                    performance,

                "gaps":
                    gaps,

                "evidencias":
                    evidencias,

                "workflow":
                    workflow,
            }

        finally:
            cursor.close()