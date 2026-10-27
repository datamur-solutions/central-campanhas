import uuid

from datetime import datetime, timezone

from app.db import (
    DATABASE,
    get_connection
)

from app.external_auth import (
    identificar_eps_por_email
)

from app.models import (
    EPSOperationalPlanUpdate,
    EPSGoLiveRequest,
    EPSStartExecutionRequest,
    EPSMonitoringUpdate,
    EPSCloseExecutionRequest
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def novo_uuid():
    return str(
        uuid.uuid4()
    )


def agora_utc():
    return datetime.now(
        timezone.utc
    )


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

    query = f"""
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
        query,
        parameters=valores
    )


def linhas_para_dict(
    cursor,
    linhas
):
    colunas = [
        descricao[0]
        for descricao
        in cursor.description
    ]

    return [
        dict(
            zip(
                colunas,
                linha
            )
        )
        for linha in linhas
    ]


# ============================================================
# BUSCAR APROVADORES INTERNOS
# ============================================================

def buscar_aprovadores(
    cursor
):
    cursor.execute(
        f"""
        SELECT
            email_aprovador

        FROM {DATABASE}.acesso_eps_aprovador

        WHERE ativo = TRUE

        ORDER BY email_aprovador
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
# OBTER USUÁRIO EPS APROVADO
# ============================================================

def obter_usuario_eps_aprovado(
    email: str
):
    identificacao = (
        identificar_eps_por_email(
            email
        )
    )

    email_normalizado = (
        identificacao["email"]
    )

    eps_dominio = (
        identificacao["eps"]
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    email_usuario,
                    nome_usuario,
                    eps,
                    ativo

                FROM {DATABASE}.usuario_eps_acesso

                WHERE lower(email_usuario) =
                      lower(?)

                  AND ativo = TRUE

                LIMIT 1
                """,
                parameters=[
                    email_normalizado
                ]
            )

            usuario = (
                cursor.fetchone()
            )

            if not usuario:
                raise PermissionError(
                    "Usuário ainda não possui "
                    "acesso aprovado ao Portal EPS."
                )

            eps_usuario = (
                usuario[2]
            )

            if eps_usuario != eps_dominio:
                raise PermissionError(
                    "Vínculo de EPS incompatível "
                    "com o domínio do usuário."
                )

            return {
                "email":
                    usuario[0],

                "nome_usuario":
                    usuario[1],

                "eps":
                    eps_usuario,

                "ativo":
                    usuario[3]
            }

        finally:
            cursor.close()


# ============================================================
# GARANTIR USUÁRIO EPS
# ============================================================

def garantir_usuario_eps(
    cursor,
    email_usuario: str,
    nome_usuario: str | None,
    eps: str,
    agora
):
    cursor.execute(
        f"""
        SELECT
            usuario_eps_uuid

        FROM {DATABASE}.usuario_eps_acesso

        WHERE lower(email_usuario) =
              lower(?)

        LIMIT 1
        """,
        parameters=[
            email_usuario
        ]
    )

    usuario_eps = (
        cursor.fetchone()
    )

    if usuario_eps:
        cursor.execute(
            f"""
            UPDATE {DATABASE}.usuario_eps_acesso

            SET
                nome_usuario = ?,
                eps = ?,
                ativo = TRUE

            WHERE usuario_eps_uuid = ?
            """,
            parameters=[
                nome_usuario,
                eps,
                usuario_eps[0]
            ]
        )

    else:
        insert_dict(
            cursor,
            "usuario_eps_acesso",
            {
                "usuario_eps_uuid":
                    novo_uuid(),

                "email_usuario":
                    email_usuario,

                "nome_usuario":
                    nome_usuario,

                "eps":
                    eps,

                "ativo":
                    True,

                "dt_criacao":
                    agora
            }
        )


# ============================================================
# SOLICITAR PRIMEIRO ACESSO AO PORTAL EPS
# ============================================================

def solicitar_acesso_eps(
    email: str,
    nome_usuario: str | None,
    ip_origem: str | None,
    user_agent: str | None
):
    identificacao = (
        identificar_eps_por_email(
            email
        )
    )

    email_normalizado = (
        identificacao["email"]
    )

    dominio = (
        identificacao["dominio"]
    )

    eps = (
        identificacao["eps"]
    )

    agora = agora_utc()

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    email_usuario,
                    nome_usuario,
                    eps,
                    ativo

                FROM {DATABASE}.usuario_eps_acesso

                WHERE lower(email_usuario) =
                      lower(?)

                  AND ativo = TRUE

                LIMIT 1
                """,
                parameters=[
                    email_normalizado
                ]
            )

            usuario_existente = (
                cursor.fetchone()
            )

            if usuario_existente:
                return {
                    "status":
                        "APROVADO",

                    "email":
                        email_normalizado,

                    "eps":
                        usuario_existente[2],

                    "novo_pedido":
                        False,

                    "mensagem":
                        (
                            "Usuário já possui "
                            "acesso aprovado."
                        )
                }

            cursor.execute(
                f"""
                SELECT
                    solicitacao_uuid,
                    dt_solicitacao,
                    status_solicitacao

                FROM {DATABASE}.acesso_eps_solicitacao

                WHERE lower(email_usuario) =
                      lower(?)

                  AND status_solicitacao =
                      'PENDENTE'

                ORDER BY dt_solicitacao DESC

                LIMIT 1
                """,
                parameters=[
                    email_normalizado
                ]
            )

            solicitacao_existente = (
                cursor.fetchone()
            )

            if solicitacao_existente:
                return {
                    "status":
                        "PENDENTE",

                    "solicitacao_uuid":
                        solicitacao_existente[0],

                    "email":
                        email_normalizado,

                    "eps":
                        eps,

                    "novo_pedido":
                        False,

                    "mensagem":
                        (
                            "Sua solicitação já está "
                            "aguardando aprovação da EduNova."
                        )
                }

            solicitacao_uuid = (
                novo_uuid()
            )

            insert_dict(
                cursor,
                "acesso_eps_solicitacao",
                {
                    "solicitacao_uuid":
                        solicitacao_uuid,

                    "email_usuario":
                        email_normalizado,

                    "nome_usuario":
                        nome_usuario,

                    "dominio_email":
                        dominio,

                    "eps_identificada":
                        eps,

                    "dt_solicitacao":
                        agora,

                    "status_solicitacao":
                        "PENDENTE",

                    "origem":
                        "PORTAL_EPS",

                    "ip_origem":
                        ip_origem,

                    "user_agent":
                        user_agent,

                    "versao_decisao":
                        0
                }
            )

            destinatarios = (
                buscar_aprovadores(
                    cursor
                )
            )

            insert_dict(
                cursor,
                "acesso_eps_notificacao",
                {
                    "notificacao_uuid":
                        novo_uuid(),

                    "solicitacao_uuid":
                        solicitacao_uuid,

                    "tipo_evento":
                        "NOVO_ACESSO_EPS_SOLICITADO",

                    "assunto":
                        (
                            "[Central de Campanhas] "
                            f"Novo acesso EPS | {eps}"
                        ),

                    "destinatarios_to":
                        destinatarios,

                    "resumo_evento":
                        (
                            f"Novo acesso solicitado por "
                            f"{email_normalizado} "
                            f"para a EPS {eps}."
                        ),

                    "status_envio":
                        "PENDENTE",

                    "tentativas_envio":
                        0,

                    "dt_criacao":
                        agora
                }
            )

            return {
                "status":
                    "PENDENTE",

                "solicitacao_uuid":
                    solicitacao_uuid,

                "email":
                    email_normalizado,

                "eps":
                    eps,

                "novo_pedido":
                    True,

                "mensagem":
                    (
                        "Solicitação criada com sucesso. "
                        "Aguarde aprovação da EduNova."
                    )
            }

        finally:
            cursor.close()


# ============================================================
# DECIDIR SOLICITAÇÃO DE ACESSO EPS
# ============================================================

def decidir_acesso_eps(
    solicitacao_uuid: str,
    decisao: str,
    motivo: str | None,
    aprovador_email: str
):
    agora = agora_utc()

    decisao = (
        decisao
        .strip()
        .upper()
    )

    if decisao not in [
        "APROVAR",
        "REJEITAR"
    ]:
        raise ValueError(
            "Decisão inválida."
        )

    novo_status_desejado = (
        "APROVADO"
        if decisao == "APROVAR"
        else "REJEITADO"
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
    f"""
    SELECT
        email_aprovador

    FROM {DATABASE}.acesso_eps_aprovador

    WHERE lower(email_aprovador) =
          lower(?)

      AND ativo = TRUE

    LIMIT 1
    """,
    parameters=[
        aprovador_email
    ]
)

            aprovador = (
                cursor.fetchone()
            )

            if not aprovador:
                raise ValueError(
                    "Usuário não possui permissão "
                    "para aprovar acessos EPS."
                )

            cursor.execute(
                f"""
                SELECT
                    solicitacao_uuid,
                    email_usuario,
                    nome_usuario,
                    dominio_email,
                    eps_identificada,
                    status_solicitacao,
                    versao_decisao,
                    decisao_por

                FROM {DATABASE}.acesso_eps_solicitacao

                WHERE solicitacao_uuid = ?

                LIMIT 1
                """,
                parameters=[
                    solicitacao_uuid
                ]
            )

            solicitacao = (
                cursor.fetchone()
            )

            if not solicitacao:
                raise ValueError(
                    "Solicitação de acesso "
                    "não encontrada."
                )

            email_usuario = (
                solicitacao[1]
            )

            nome_usuario = (
                solicitacao[2]
            )

            eps = (
                solicitacao[4]
            )

            status_atual = (
                solicitacao[5]
            )

            versao_atual = int(
                solicitacao[6]
                or 0
            )

            decisao_anterior_por = (
                solicitacao[7]
            )

            if status_atual != "PENDENTE":
                mesma_decisao = (
                    status_atual
                    == novo_status_desejado
                )

                mesmo_aprovador = (
                    decisao_anterior_por
                    and
                    decisao_anterior_por.lower()
                    == aprovador_email.lower()
                )

                if (
                    mesma_decisao
                    and
                    mesmo_aprovador
                ):
                    if status_atual == "APROVADO":
                        garantir_usuario_eps(
                            cursor,
                            email_usuario,
                            nome_usuario,
                            eps,
                            agora
                        )

                    return {
                        "solicitacao_uuid":
                            solicitacao_uuid,

                        "email":
                            email_usuario,

                        "eps":
                            eps,

                        "status":
                            status_atual,

                        "decisao_por":
                            decisao_anterior_por,

                        "versao_decisao":
                            versao_atual,

                        "acesso_liberado":
                            (
                                status_atual
                                == "APROVADO"
                            ),

                        "ja_processada":
                            True
                    }

                raise ValueError(
                    (
                        "Esta solicitação já foi "
                        f"{status_atual.lower()} "
                        "e não pode ser alterada. "
                        f"Decisão registrada por "
                        f"{decisao_anterior_por}."
                    )
                )

            cursor.execute(
                f"""
                UPDATE {DATABASE}.acesso_eps_solicitacao

                SET
                    status_solicitacao = ?,
                    dt_decisao = ?,
                    decisao_por = ?,
                    motivo_decisao = ?,
                    versao_decisao = ?

                WHERE solicitacao_uuid = ?

                  AND status_solicitacao =
                      'PENDENTE'
                """,
                parameters=[
                    novo_status_desejado,
                    agora,
                    aprovador_email,
                    motivo,
                    versao_atual + 1,
                    solicitacao_uuid
                ]
            )

            cursor.execute(
                f"""
                SELECT
                    status_solicitacao,
                    decisao_por,
                    versao_decisao

                FROM {DATABASE}.acesso_eps_solicitacao

                WHERE solicitacao_uuid = ?

                LIMIT 1
                """,
                parameters=[
                    solicitacao_uuid
                ]
            )

            confirmacao = (
                cursor.fetchone()
            )

            if not confirmacao:
                raise ValueError(
                    "Não foi possível confirmar "
                    "a decisão da solicitação."
                )

            status_confirmado = (
                confirmacao[0]
            )

            decisor_confirmado = (
                confirmacao[1]
            )

            versao_confirmada = (
                confirmacao[2]
            )

            if (
                status_confirmado
                != novo_status_desejado
            ):
                raise ValueError(
                    "A solicitação foi alterada "
                    "por outro aprovador."
                )

            if (
                not decisor_confirmado
                or
                decisor_confirmado.lower()
                != aprovador_email.lower()
            ):
                raise ValueError(
                    "A solicitação já foi decidida "
                    "por outro aprovador."
                )

            if (
                novo_status_desejado
                == "APROVADO"
            ):
                garantir_usuario_eps(
                    cursor,
                    email_usuario,
                    nome_usuario,
                    eps,
                    agora
                )

            insert_dict(
                cursor,
                "acesso_eps_notificacao",
                {
                    "notificacao_uuid":
                        novo_uuid(),

                    "solicitacao_uuid":
                        solicitacao_uuid,

                    "tipo_evento":
                        (
                            "ACESSO_EPS_APROVADO"
                            if novo_status_desejado
                            == "APROVADO"
                            else
                            "ACESSO_EPS_REJEITADO"
                        ),

                    "assunto":
                        (
                            "[Central de Campanhas] "
                            f"Acesso "
                            f"{novo_status_desejado.lower()} "
                            f"| {eps}"
                        ),

                    "destinatarios_to":
                        email_usuario,

                    "resumo_evento":
                        (
                            "Solicitação de acesso "
                            "ao Portal EPS "
                            f"{novo_status_desejado.lower()}."
                        ),

                    "status_envio":
                        "PENDENTE",

                    "tentativas_envio":
                        0,

                    "dt_criacao":
                        agora
                }
            )

            return {
                "solicitacao_uuid":
                    solicitacao_uuid,

                "email":
                    email_usuario,

                "eps":
                    eps,

                "status":
                    novo_status_desejado,

                "decisao_por":
                    aprovador_email,

                "versao_decisao":
                    versao_confirmada,

                "acesso_liberado":
                    (
                        novo_status_desejado
                        == "APROVADO"
                    ),

                "ja_processada":
                    False
            }

        finally:
            cursor.close()


# ============================================================
# FASE 6E
# LISTAR CAMPANHAS DISPONÍVEIS PARA A EPS
# ============================================================

def listar_campanhas_portal_eps(
    email_usuario: str
):
    usuario = (
        obter_usuario_eps_aprovado(
            email_usuario
        )
    )

    eps_usuario = (
        usuario["eps"]
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.codigo_campanha,
                    m.nome_campanha,
                    m.produto,
                    m.tipo_acao,
                    m.status_campanha,

                    m.objetivo_campanha,
                    m.resultado_esperado,

                    m.dt_inicio_prevista,
                    m.dt_fim_prevista,

                    ce.eps,
                    ce.status_execucao_eps,
                    ce.dt_handoff,
                    ce.dt_liberacao_eps,
                    ce.liberada_para_eps

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE ce.eps = ?
                  AND ce.liberada_para_eps = TRUE

                ORDER BY
                    m.dt_inicio_prevista DESC,
                    m.codigo_campanha DESC
                """,
                parameters=[
                    eps_usuario
                ]
            )

            campanhas = (
                linhas_para_dict(
                    cursor,
                    cursor.fetchall()
                )
            )

            return {
                "usuario": {
                    "email":
                        usuario["email"],

                    "nome":
                        usuario["nome_usuario"],

                    "eps":
                        eps_usuario
                },

                "quantidade":
                    len(campanhas),

                "campanhas":
                    campanhas
            }

        finally:
            cursor.close()


# ============================================================
# FASE 6E + 6F
# DETALHAR CAMPANHA DA EPS
# ============================================================

def obter_campanha_portal_eps(
    email_usuario: str,
    codigo_campanha: str
):
    usuario = (
        obter_usuario_eps_aprovado(
            email_usuario
        )
    )

    eps_usuario = (
        usuario["eps"]
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    ce.campanha_eps_uuid,

                    m.codigo_campanha,
                    m.nome_campanha,
                    m.produto,
                    m.tipo_acao,
                    m.status_campanha,

                    m.oportunidade_problema,
                    m.fonte_oportunidade,
                    m.indicador_evidencia_oportunidade,
                    m.etapa_funil_alvo,

                    m.publico_alvo,
                    m.segmentacao,
                    m.criterio_elegibilidade,
                    m.criterio_exclusao,
                    m.dimensao_estimada,

                    m.estrategia,
                    m.mecanica,
                    m.oferta_beneficio,
                    m.argumento_comercial,
                    m.regras_comerciais,
                    m.condicoes_especificas,
                    m.canais_possiveis,

                    m.incentivo_aplicavel,
                    m.incentivo_gatilhos,
                    m.incentivo_criterios,
                    m.incentivo_condicao_pagamento,

                    m.objetivo_campanha,
                    m.resultado_esperado,

                    m.dt_inicio_prevista,
                    m.dt_fim_prevista,

                    ce.eps,
                    ce.status_execucao_eps,
                    ce.dt_handoff,
                    ce.dt_liberacao_eps,
                    ce.liberada_para_eps

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            linha_campanha = (
                cursor.fetchone()
            )

            if not linha_campanha:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            colunas_campanha = [
                descricao[0]
                for descricao
                in cursor.description
            ]

            campanha = dict(
                zip(
                    colunas_campanha,
                    linha_campanha
                )
            )

            campaign_uuid = (
                campanha["campaign_uuid"]
            )

            campanha_eps_uuid = (
                campanha[
                    "campanha_eps_uuid"
                ]
            )

            cursor.execute(
                f"""
                SELECT
                    esc.escopo_uuid,
                    esc.produto,
                    esc.frente_pos,
                    esc.supercanal,
                    esc.outro_supercanal_descricao,
                    esc.modalidade

                FROM {DATABASE}.campanha_eps_escopo ee

                INNER JOIN {DATABASE}.campanha_escopo esc
                    ON ee.escopo_uuid =
                       esc.escopo_uuid

                WHERE ee.campanha_eps_uuid = ?
                  AND ee.ativo = TRUE
                  AND esc.ativo = TRUE

                ORDER BY
                    esc.produto,
                    esc.supercanal,
                    esc.modalidade
                """,
                parameters=[
                    campanha_eps_uuid
                ]
            )

            escopos = (
                linhas_para_dict(
                    cursor,
                    cursor.fetchall()
                )
            )

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
                    ritmo_esperado

                FROM {DATABASE}.campanha_kpi

                WHERE campaign_uuid = ?
                  AND ativo = TRUE

                ORDER BY
                    kpi_principal DESC,
                    nome_kpi
                """,
                parameters=[
                    campaign_uuid
                ]
            )

            kpis = (
                linhas_para_dict(
                    cursor,
                    cursor.fetchall()
                )
            )

            campanha.pop(
                "campaign_uuid",
                None
            )

            campanha.pop(
                "campanha_eps_uuid",
                None
            )

            campanha[
                "escopos"
            ] = escopos

            campanha[
                "kpis"
            ] = kpis

            return {
                "usuario": {
                    "email":
                        usuario["email"],

                    "nome":
                        usuario["nome_usuario"],

                    "eps":
                        eps_usuario
                },

                "campanha":
                    campanha
            }

        finally:
            cursor.close()


# ============================================================
# FASE 7A
# SALVAR / ATUALIZAR PLANO OPERACIONAL DA EPS
# ============================================================

def salvar_plano_operacional_eps(
    email_usuario: str,
    codigo_campanha: str,
    payload: EPSOperationalPlanUpdate
):
    usuario = obter_usuario_eps_aprovado(
        email_usuario
    )

    eps_usuario = usuario["eps"]

    agora = agora_utc()

    dados = payload.model_dump(
        exclude_unset=True
    )

    if not dados:
        raise ValueError(
            "Nenhuma informação foi enviada "
            "para atualização."
        )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    ce.campanha_eps_uuid,
                    ce.status_execucao_eps

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            vinculo = cursor.fetchone()

            if not vinculo:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            campaign_uuid = vinculo[0]
            campanha_eps_uuid = vinculo[1]

            status_anterior = (
                vinculo[2]
                or
                "AGUARDANDO_PLANEJAMENTO_EPS"
            )

            campos_update = []
            valores_update = []

            for campo, valor in dados.items():
                campos_update.append(
                    f"{campo} = ?"
                )

                valores_update.append(
                    valor
                )

            campos_update.extend(
                [
                    "status_execucao_eps = ?",
                    "dt_atualizacao = ?",
                    "atualizado_por = ?"
                ]
            )

            valores_update.extend(
                [
                    "PLANEJAMENTO_EPS",
                    agora,
                    usuario["email"]
                ]
            )

            valores_update.append(
                campanha_eps_uuid
            )

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_eps

                SET
                    {", ".join(campos_update)}

                WHERE campanha_eps_uuid = ?
                """,
                parameters=valores_update
            )

            if (
                status_anterior
                != "PLANEJAMENTO_EPS"
            ):
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
                            eps_usuario,

                        "escopo":
                            "EPS",

                        "status_anterior":
                            status_anterior,

                        "status_novo":
                            "PLANEJAMENTO_EPS",

                        "etapa_pop":
                            "PLANEJAR_EPS",

                        "origem":
                            "EPS",

                        "usuario":
                            usuario["email"],

                        "dt_evento":
                            agora,

                        "observacao":
                            (
                                "EPS iniciou o preenchimento "
                                "do plano operacional."
                            ),

                        "dispara_email":
                            False,

                        "tipo_evento_email":
                            None
                    }
                )

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
                        usuario["email"],

                    "origem":
                        "EPS",

                    "evento":
                        "ATUALIZACAO_PLANO_EPS",

                    "campo_alterado":
                        "PLANO_OPERACIONAL_EPS",

                    "valor_anterior":
                        None,

                    "valor_novo":
                        ", ".join(
                            dados.keys()
                        ),

                    "observacao":
                        (
                            f"Plano operacional atualizado "
                            f"pela EPS {eps_usuario}."
                        )
                }
            )

            return {
                "codigo_campanha":
                    codigo_campanha.upper(),

                "eps":
                    eps_usuario,

                "status_anterior":
                    status_anterior,

                "status_execucao_eps":
                    "PLANEJAMENTO_EPS",

                "campos_atualizados":
                    list(
                        dados.keys()
                    ),

                "quantidade_campos_atualizados":
                    len(dados),

                "atualizado_por":
                    usuario["email"]
            }

        finally:
            cursor.close()


# ============================================================
# FASE 7B
# AVALIAR PRONTIDÃO PARA GO-LIVE
# ============================================================

def avaliar_prontidao_go_live_eps(
    email_usuario: str,
    codigo_campanha: str
):
    usuario = obter_usuario_eps_aprovado(
        email_usuario
    )

    eps_usuario = usuario["eps"]

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    m.codigo_campanha,
                    m.nome_campanha,
                    m.tipo_acao,

                    ce.campanha_eps_uuid,
                    ce.status_execucao_eps,
                    ce.go_live_aprovado,

                    ce.responsavel_eps,
                    ce.ponto_focal_eps,

                    ce.entendimento_confirmado,

                    ce.pendencias_criticas,
                    ce.pendencias_criticas_resolvidas,

                    ce.mailing_aplicavel,
                    ce.mailing_previsto,
                    ce.mailing_recebido,
                    ce.mailing_disponivel,
                    ce.mailing_validado,
                    ce.qualidade_mailing_validada,

                    ce.segmentacao_configurada,
                    ce.jornada_cadencia_definidas,
                    ce.canais_recursos_disponiveis,
                    ce.script_argumentacao_alinhados,

                    ce.capacidade_operacional_validada,
                    ce.responsaveis_pontos_focais_definidos,
                    ce.data_inicio_confirmada,

                    ce.dt_inicio_operacional,
                    ce.dt_fim_operacional,

                    ce.modelo_frequencia_reporte_acordados,
                    ce.frequencia_reporte_eps

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            linha = cursor.fetchone()

            if not linha:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            colunas = [
                descricao[0]
                for descricao
                in cursor.description
            ]

            dados = dict(
                zip(
                    colunas,
                    linha
                )
            )

            tipo_acao = dados[
                "tipo_acao"
            ]

            checklist = []

            def adicionar_check(
                item,
                ok,
                obrigatorio=True,
                detalhe=None
            ):
                checklist.append(
                    {
                        "item":
                            item,

                        "obrigatorio":
                            obrigatorio,

                        "ok":
                            bool(ok),

                        "detalhe":
                            detalhe
                    }
                )

            adicionar_check(
                "Plano operacional iniciado",
                dados["status_execucao_eps"]
                in [
                    "PLANEJAMENTO_EPS",
                    "GO_LIVE_APROVADO"
                ]
            )

            adicionar_check(
                "Entendimento da campanha confirmado",
                dados[
                    "entendimento_confirmado"
                ] is True
            )

            adicionar_check(
                "Responsáveis e pontos focais definidos",
                dados[
                    "responsaveis_pontos_focais_definidos"
                ] is True
            )

            adicionar_check(
                "Responsável EPS informado",
                bool(
                    dados[
                        "responsavel_eps"
                    ]
                )
            )

            pendencia_texto = (
                dados[
                    "pendencias_criticas"
                ]
            )

            possui_pendencia = bool(
                pendencia_texto
                and
                str(
                    pendencia_texto
                ).strip()
            )

            if possui_pendencia:
                adicionar_check(
                    "Pendências críticas resolvidas",
                    dados[
                        "pendencias_criticas_resolvidas"
                    ] is True
                )

            adicionar_check(
                "Capacidade operacional validada",
                dados[
                    "capacidade_operacional_validada"
                ] is True
            )

            adicionar_check(
                "Canais e recursos disponíveis",
                dados[
                    "canais_recursos_disponiveis"
                ] is True
            )

            adicionar_check(
                "Data de início confirmada",
                dados[
                    "data_inicio_confirmada"
                ] is True
            )

            adicionar_check(
                "Data de início operacional informada",
                dados[
                    "dt_inicio_operacional"
                ] is not None
            )

            adicionar_check(
                "Modelo e frequência de reporte acordados",
                dados[
                    "modelo_frequencia_reporte_acordados"
                ] is True
            )

            adicionar_check(
                "Frequência de reporte informada",
                bool(
                    dados[
                        "frequencia_reporte_eps"
                    ]
                )
            )

            mailing_aplicavel = (
                dados[
                    "mailing_aplicavel"
                ]
            )

            adicionar_check(
                "Aplicabilidade de mailing definida",
                mailing_aplicavel
                is not None
            )

            if mailing_aplicavel is True:
                adicionar_check(
                    "Mailing disponível",
                    dados[
                        "mailing_disponivel"
                    ] is True
                )

                adicionar_check(
                    "Mailing validado",
                    dados[
                        "mailing_validado"
                    ] is True
                )

                adicionar_check(
                    "Qualidade do mailing validada",
                    dados[
                        "qualidade_mailing_validada"
                    ] is True
                )

                adicionar_check(
                    "Volume de mailing recebido informado",
                    dados[
                        "mailing_recebido"
                    ] is not None
                )

            else:
                checklist.append(
                    {
                        "item":
                            "Mailing / Base",

                        "obrigatorio":
                            False,

                        "ok":
                            True,

                        "detalhe":
                            (
                                "Não aplicável "
                                "à campanha."
                            )
                    }
                )

            if tipo_acao == "COMERCIAL":
                adicionar_check(
                    "Segmentação operacional configurada",
                    dados[
                        "segmentacao_configurada"
                    ] is True
                )

                adicionar_check(
                    "Jornada e cadência definidas",
                    dados[
                        "jornada_cadencia_definidas"
                    ] is True
                )

                adicionar_check(
                    "Script e argumentação alinhados",
                    dados[
                        "script_argumentacao_alinhados"
                    ] is True
                )

            else:
                checklist.append(
                    {
                        "item":
                            (
                                "Segmentação / Cadência / "
                                "Script comercial"
                            ),

                        "obrigatorio":
                            False,

                        "ok":
                            True,

                        "detalhe":
                            (
                                "Não obrigatório "
                                "automaticamente para "
                                "campanha de incentivo."
                            )
                    }
                )

            checklist.append(
                {
                    "item":
                        "Capacitação",

                    "obrigatorio":
                        False,

                    "ok":
                        True,

                    "detalhe":
                        (
                            "Avaliada conforme necessidade "
                            "da campanha; não bloqueia "
                            "automaticamente o Go-Live."
                        )
                }
            )

            bloqueadores = [
                item["item"]

                for item in checklist

                if (
                    item["obrigatorio"] is True
                    and
                    item["ok"] is False
                )
            ]

            pronto = (
                len(
                    bloqueadores
                )
                == 0
            )

            return {
                "codigo_campanha":
                    dados[
                        "codigo_campanha"
                    ],

                "nome_campanha":
                    dados[
                        "nome_campanha"
                    ],

                "eps":
                    eps_usuario,

                "tipo_acao":
                    tipo_acao,

                "status_execucao_eps":
                    dados[
                        "status_execucao_eps"
                    ],

                "mailing_aplicavel":
                    mailing_aplicavel,

                "go_live_ja_aprovado":
                    dados[
                        "go_live_aprovado"
                    ] is True,

                "pronto_para_go_live":
                    pronto,

                "quantidade_bloqueadores":
                    len(
                        bloqueadores
                    ),

                "bloqueadores":
                    bloqueadores,

                "checklist":
                    checklist
            }

        finally:
            cursor.close()


# ============================================================
# FASE 7B
# APROVAR GO-LIVE
# ============================================================

def aprovar_go_live_eps(
    email_usuario: str,
    codigo_campanha: str,
    payload: EPSGoLiveRequest
):
    prontidao = (
        avaliar_prontidao_go_live_eps(
            email_usuario,
            codigo_campanha
        )
    )

    if not prontidao[
        "pronto_para_go_live"
    ]:
        bloqueadores = "; ".join(
            prontidao[
                "bloqueadores"
            ]
        )

        raise ValueError(
            (
                "Campanha ainda não está pronta "
                "para Go-Live. Pendências: "
                f"{bloqueadores}"
            )
        )

    usuario = (
        obter_usuario_eps_aprovado(
            email_usuario
        )
    )

    eps_usuario = (
        usuario["eps"]
    )

    agora = agora_utc()

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    ce.campanha_eps_uuid,
                    ce.status_execucao_eps,
                    ce.go_live_aprovado

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            vinculo = (
                cursor.fetchone()
            )

            if not vinculo:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            campaign_uuid = (
                vinculo[0]
            )

            campanha_eps_uuid = (
                vinculo[1]
            )

            status_anterior = (
                vinculo[2]
            )

            go_live_atual = (
                vinculo[3]
            )

            if go_live_atual is True:
                return {
                    "codigo_campanha":
                        codigo_campanha.upper(),

                    "eps":
                        eps_usuario,

                    "status_execucao_eps":
                        status_anterior,

                    "go_live_aprovado":
                        True,

                    "ja_aprovado":
                        True
                }

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_eps

                SET
                    go_live_aprovado = TRUE,

                    aderencia_modelo_aprovado = TRUE,

                    dt_go_live = ?,

                    status_execucao_eps =
                        'GO_LIVE_APROVADO',

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campanha_eps_uuid = ?
                """,
                parameters=[
                    agora,
                    agora,
                    usuario[
                        "email"
                    ],
                    campanha_eps_uuid
                ]
            )

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
                        eps_usuario,

                    "escopo":
                        "EPS",

                    "status_anterior":
                        status_anterior,

                    "status_novo":
                        "GO_LIVE_APROVADO",

                    "etapa_pop":
                        "VALIDAR_GO_LIVE",

                    "origem":
                        "EPS",

                    "usuario":
                        usuario[
                            "email"
                        ],

                    "dt_evento":
                        agora,

                    "observacao":
                        (
                            payload.observacao
                            or
                            (
                                "Checklist de prontidão "
                                "validado e Go-Live "
                                "aprovado pela EPS."
                            )
                        ),

                    "dispara_email":
                        False,

                    "tipo_evento_email":
                        None
                }
            )

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
                        usuario[
                            "email"
                        ],

                    "origem":
                        "EPS",

                    "evento":
                        "GO_LIVE_APROVADO",

                    "campo_alterado":
                        "go_live_aprovado",

                    "valor_anterior":
                        "FALSE",

                    "valor_novo":
                        "TRUE",

                    "observacao":
                        (
                            payload.observacao
                            or
                            (
                                "Go-Live aprovado após "
                                "validação do checklist "
                                "de prontidão."
                            )
                        )
                }
            )

            return {
                "codigo_campanha":
                    codigo_campanha.upper(),

                "eps":
                    eps_usuario,

                "status_anterior":
                    status_anterior,

                "status_execucao_eps":
                    "GO_LIVE_APROVADO",

                "go_live_aprovado":
                    True,

                "operacao_ativada":
                    False,

                "dt_go_live":
                    agora,

                "ja_aprovado":
                    False
            }

        finally:
            cursor.close()


# ============================================================
# FASE 7C
# BUSCAR DESTINATÁRIOS INTERNOS DE CAMPANHAS
# ============================================================

def buscar_destinatarios_campanha(
    cursor
):
    cursor.execute(
        f"""
        SELECT
            email_usuario

        FROM {DATABASE}.vw_destinatarios_notificacao_campanha

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
# FASE 7C
# INICIAR EXECUÇÃO DA CAMPANHA
# ============================================================

def iniciar_execucao_eps(
    email_usuario: str,
    codigo_campanha: str,
    payload: EPSStartExecutionRequest
):
    usuario = (
        obter_usuario_eps_aprovado(
            email_usuario
        )
    )

    eps_usuario = (
        usuario["eps"]
    )

    agora = agora_utc()

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    m.nome_campanha,

                    ce.campanha_eps_uuid,
                    ce.status_execucao_eps,
                    ce.go_live_aprovado,
                    ce.operacao_ativada

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            vinculo = (
                cursor.fetchone()
            )

            if not vinculo:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            campaign_uuid = (
                vinculo[0]
            )

            nome_campanha = (
                vinculo[1]
            )

            campanha_eps_uuid = (
                vinculo[2]
            )

            status_anterior = (
                vinculo[3]
            )

            go_live_aprovado = (
                vinculo[4]
            )

            operacao_ativada = (
                vinculo[5]
            )

            if go_live_aprovado is not True:
                raise ValueError(
                    "O Go-Live precisa estar aprovado "
                    "antes de iniciar a execução."
                )

            if operacao_ativada is True:
                return {
                    "codigo_campanha":
                        codigo_campanha.upper(),

                    "eps":
                        eps_usuario,

                    "status_execucao_eps":
                        status_anterior,

                    "operacao_ativada":
                        True,

                    "ja_iniciada":
                        True
                }

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_eps

                SET
                    operacao_ativada = TRUE,

                    status_execucao_eps =
                        'EM_EXECUCAO',

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campanha_eps_uuid = ?
                """,
                parameters=[
                    agora,
                    usuario["email"],
                    campanha_eps_uuid
                ]
            )

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
                        eps_usuario,

                    "escopo":
                        "EPS",

                    "status_anterior":
                        status_anterior,

                    "status_novo":
                        "EM_EXECUCAO",

                    "etapa_pop":
                        "EXECUTAR_E_COMPROVAR",

                    "origem":
                        "EPS",

                    "usuario":
                        usuario["email"],

                    "dt_evento":
                        agora,

                    "observacao":
                        (
                            payload.observacao
                            or
                            "EPS iniciou a execução da campanha."
                        ),

                    "dispara_email":
                        True,

                    "tipo_evento_email":
                        "EPS_INICIOU_ATUACAO"
                }
            )

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
                        usuario["email"],

                    "origem":
                        "EPS",

                    "evento":
                        "INICIO_EXECUCAO_EPS",

                    "campo_alterado":
                        "status_execucao_eps",

                    "valor_anterior":
                        status_anterior,

                    "valor_novo":
                        "EM_EXECUCAO",

                    "observacao":
                        (
                            payload.observacao
                            or
                            f"EPS {eps_usuario} iniciou "
                            "a execução da campanha."
                        )
                }
            )

            destinatarios = (
                buscar_destinatarios_campanha(
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
                        eps_usuario,

                    "tipo_evento":
                        "EPS_INICIOU_ATUACAO",

                    "assunto":
                        (
                            "[Central de Campanhas] "
                            f"{eps_usuario} iniciou atuação | "
                            f"{codigo_campanha.upper()} - "
                            f"{nome_campanha}"
                        ),

                    "destinatarios_to":
                        destinatarios,

                    "destinatarios_cc":
                        None,

                    "resumo_evento":
                        (
                            f"A EPS {eps_usuario} iniciou "
                            "a execução da campanha."
                        ),

                    "status_envio":
                        "PENDENTE",

                    "tentativas_envio":
                        0,

                    "dt_criacao":
                        agora
                }
            )

            return {
                "codigo_campanha":
                    codigo_campanha.upper(),

                "eps":
                    eps_usuario,

                "status_anterior":
                    status_anterior,

                "status_execucao_eps":
                    "EM_EXECUCAO",

                "go_live_aprovado":
                    True,

                "operacao_ativada":
                    True,

                "iniciado_por":
                    usuario["email"],

                "dt_inicio_execucao":
                    agora,

                "ja_iniciada":
                    False
            }

        finally:
            cursor.close()


# ============================================================
# FASE 7D
# REGISTRAR ACOMPANHAMENTO DA EXECUÇÃO
# ============================================================

def registrar_acompanhamento_eps(
    email_usuario: str,
    codigo_campanha: str,
    payload: EPSMonitoringUpdate
):
    usuario = (
        obter_usuario_eps_aprovado(
            email_usuario
        )
    )

    eps_usuario = (
        usuario["eps"]
    )

    agora = agora_utc()

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    m.nome_campanha,

                    ce.campanha_eps_uuid,
                    ce.status_execucao_eps,
                    ce.operacao_ativada

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            vinculo = (
                cursor.fetchone()
            )

            if not vinculo:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            campaign_uuid = (
                vinculo[0]
            )

            campanha_eps_uuid = (
                vinculo[2]
            )

            status_execucao = (
                vinculo[3]
            )

            operacao_ativada = (
                vinculo[4]
            )

            if (
                status_execucao
                != "EM_EXECUCAO"
                or
                operacao_ativada is not True
            ):
                raise ValueError(
                    "A campanha precisa estar "
                    "EM_EXECUCAO para receber "
                    "acompanhamentos."
                )

            performance_salva = False
            performance_acao = None
            gaps_criados = 0
            gaps_atualizados = 0
            evidencias_criadas = 0

            if payload.performance is not None:
                dados_performance = (
                    payload.performance.model_dump(
                        exclude_unset=True
                    )
                )

                data_referencia = (
                    dados_performance.pop(
                        "data_referencia"
                    )
                )

                cursor.execute(
                    f"""
                    SELECT
                        performance_uuid

                    FROM {DATABASE}.campanha_performance

                    WHERE campaign_uuid = ?
                      AND eps = ?
                      AND data_referencia = ?

                    LIMIT 1
                    """,
                    parameters=[
                        campaign_uuid,
                        eps_usuario,
                        data_referencia
                    ]
                )

                performance_existente = (
                    cursor.fetchone()
                )

                if performance_existente:
                    performance_uuid = (
                        performance_existente[0]
                    )

                    campos_update = []
                    valores_update = []

                    for campo, valor in (
                        dados_performance.items()
                    ):
                        campos_update.append(
                            f"{campo} = ?"
                        )

                        valores_update.append(
                            valor
                        )

                    campos_update.extend(
                        [
                            "dt_carga = ?",
                            "carregado_por = ?"
                        ]
                    )

                    valores_update.extend(
                        [
                            agora,
                            usuario["email"]
                        ]
                    )

                    valores_update.append(
                        performance_uuid
                    )

                    cursor.execute(
                        f"""
                        UPDATE {DATABASE}.campanha_performance

                        SET
                            {", ".join(campos_update)}

                        WHERE performance_uuid = ?
                        """,
                        parameters=valores_update
                    )

                    performance_acao = (
                        "ATUALIZADA"
                    )

                else:
                    linha_performance = {
                        "performance_uuid":
                            novo_uuid(),

                        "campaign_uuid":
                            campaign_uuid,

                        "eps":
                            eps_usuario,

                        "data_referencia":
                            data_referencia,

                        **dados_performance,

                        "dt_carga":
                            agora,

                        "carregado_por":
                            usuario["email"]
                    }

                    insert_dict(
                        cursor,
                        "campanha_performance",
                        linha_performance
                    )

                    performance_acao = (
                        "CRIADA"
                    )

                performance_salva = True

            for gap_payload in payload.gaps:
                dados_gap = (
                    gap_payload.model_dump(
                        exclude_unset=True
                    )
                )

                gap_uuid = (
                    dados_gap.pop(
                        "gap_uuid",
                        None
                    )
                )

                if gap_uuid:
                    cursor.execute(
                        f"""
                        SELECT
                            gap_uuid

                        FROM {DATABASE}.campanha_gap

                        WHERE gap_uuid = ?
                          AND campaign_uuid = ?
                          AND eps = ?

                        LIMIT 1
                        """,
                        parameters=[
                            gap_uuid,
                            campaign_uuid,
                            eps_usuario
                        ]
                    )

                    gap_existente = (
                        cursor.fetchone()
                    )

                    if not gap_existente:
                        raise PermissionError(
                            "Gap não encontrado "
                            "para esta campanha/EPS."
                        )

                    campos_update = []
                    valores_update = []

                    status_novo = (
                        dados_gap.get(
                            "status_gap"
                        )
                    )

                    if (
                        status_novo
                        and
                        status_novo.upper()
                        == "RESOLVIDO"
                    ):
                        dados_gap[
                            "dt_resolucao"
                        ] = agora

                    for campo, valor in (
                        dados_gap.items()
                    ):
                        campos_update.append(
                            f"{campo} = ?"
                        )

                        valores_update.append(
                            valor
                        )

                    if campos_update:
                        valores_update.append(
                            gap_uuid
                        )

                        cursor.execute(
                            f"""
                            UPDATE {DATABASE}.campanha_gap

                            SET
                                {", ".join(campos_update)}

                            WHERE gap_uuid = ?
                            """,
                            parameters=valores_update
                        )

                    gaps_atualizados += 1

                else:
                    if not dados_gap.get(
                        "status_gap"
                    ):
                        dados_gap[
                            "status_gap"
                        ] = "ABERTO"

                    linha_gap = {
                        "gap_uuid":
                            novo_uuid(),

                        "campaign_uuid":
                            campaign_uuid,

                        "eps":
                            eps_usuario,

                        "dt_identificacao":
                            agora,

                        **dados_gap,

                        "criado_por":
                            usuario["email"],

                        "dt_criacao":
                            agora
                    }

                    insert_dict(
                        cursor,
                        "campanha_gap",
                        linha_gap
                    )

                    gaps_criados += 1

            for evidencia_payload in (
                payload.evidencias
            ):
                dados_evidencia = (
                    evidencia_payload.model_dump(
                        exclude_unset=True
                    )
                )

                linha_evidencia = {
                    "evidencia_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "eps":
                        eps_usuario,

                    **dados_evidencia,

                    "dt_evidencia":
                        agora,

                    "validada":
                        False,

                    "validada_por":
                        None,

                    "dt_validacao":
                        None,

                    "criado_por":
                        usuario["email"],

                    "dt_criacao":
                        agora
                }

                insert_dict(
                    cursor,
                    "campanha_evidencia",
                    linha_evidencia
                )

                evidencias_criadas += 1

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_eps

                SET
                    dt_atualizacao = ?,
                    atualizado_por = ?

                WHERE campanha_eps_uuid = ?
                """,
                parameters=[
                    agora,
                    usuario["email"],
                    campanha_eps_uuid
                ]
            )

            resumo = (
                f"Performance: "
                f"{performance_acao or 'NÃO INFORMADA'}; "
                f"Gaps criados: {gaps_criados}; "
                f"Gaps atualizados: {gaps_atualizados}; "
                f"Evidências: {evidencias_criadas}."
            )

            if payload.observacao_geral:
                resumo = (
                    resumo
                    + " Observação: "
                    + payload.observacao_geral
                )

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
                        usuario["email"],

                    "origem":
                        "EPS",

                    "evento":
                        "ACOMPANHAMENTO_EXECUCAO",

                    "campo_alterado":
                        "ACOMPANHAMENTO_EPS",

                    "valor_anterior":
                        None,

                    "valor_novo":
                        resumo,

                    "observacao":
                        (
                            "Atualização de acompanhamento "
                            f"registrada pela EPS "
                            f"{eps_usuario}."
                        )
                }
            )

            return {
                "codigo_campanha":
                    codigo_campanha.upper(),

                "eps":
                    eps_usuario,

                "status_execucao_eps":
                    "EM_EXECUCAO",

                "performance_registrada":
                    performance_salva,

                "performance_acao":
                    performance_acao,

                "gaps_criados":
                    gaps_criados,

                "gaps_atualizados":
                    gaps_atualizados,

                "evidencias_criadas":
                    evidencias_criadas,

                "atualizado_por":
                    usuario["email"]
            }

        finally:
            cursor.close()


# ============================================================
# FASE 7E
# ENCERRAR EXECUÇÃO DA CAMPANHA PELA EPS
# ============================================================

def encerrar_execucao_eps(
    email_usuario: str,
    codigo_campanha: str,
    payload: EPSCloseExecutionRequest
):
    usuario = (
        obter_usuario_eps_aprovado(
            email_usuario
        )
    )

    eps_usuario = (
        usuario["eps"]
    )

    agora = agora_utc()

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    m.nome_campanha,

                    ce.campanha_eps_uuid,
                    ce.status_execucao_eps,
                    ce.operacao_ativada,
                    ce.mailing_aplicavel

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps ce
                    ON m.campaign_uuid =
                       ce.campaign_uuid

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                  AND ce.eps = ?

                  AND ce.liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha,
                    eps_usuario
                ]
            )

            vinculo = (
                cursor.fetchone()
            )

            if not vinculo:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            campaign_uuid = (
                vinculo[0]
            )

            nome_campanha = (
                vinculo[1]
            )

            campanha_eps_uuid = (
                vinculo[2]
            )

            status_anterior = (
                vinculo[3]
            )

            operacao_ativada = (
                vinculo[4]
            )

            mailing_aplicavel = (
                vinculo[5]
            )

            if (
                status_anterior
                == "EXECUCAO_FINALIZADA"
            ):
                return {
                    "codigo_campanha":
                        codigo_campanha.upper(),

                    "eps":
                        eps_usuario,

                    "status_execucao_eps":
                        "EXECUCAO_FINALIZADA",

                    "operacao_ativada":
                        False,

                    "ja_finalizada":
                        True
                }

            if (
                status_anterior
                != "EM_EXECUCAO"
                or
                operacao_ativada is not True
            ):
                raise ValueError(
                    "A campanha precisa estar "
                    "EM_EXECUCAO para ser finalizada."
                )

            cursor.execute(
                f"""
                SELECT
                    encerramento_eps_uuid

                FROM {DATABASE}.campanha_encerramento_eps

                WHERE campaign_uuid = ?
                  AND eps = ?

                LIMIT 1
                """,
                parameters=[
                    campaign_uuid,
                    eps_usuario
                ]
            )

            encerramento_existente = (
                cursor.fetchone()
            )

            if encerramento_existente:
                raise ValueError(
                    "Já existe um encerramento "
                    "registrado para esta EPS."
                )

            dados = (
                payload.model_dump(
                    exclude_unset=True
                )
            )

            linha_encerramento = {
                "encerramento_eps_uuid":
                    novo_uuid(),

                "campaign_uuid":
                    campaign_uuid,

                "eps":
                    eps_usuario,

                **dados,

                "dt_fechamento_eps":
                    agora,

                "dt_criacao":
                    agora,

                "criado_por":
                    usuario["email"]
            }

            insert_dict(
                cursor,
                "campanha_encerramento_eps",
                linha_encerramento
            )

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_eps

                SET
                    status_execucao_eps =
                        'EXECUCAO_FINALIZADA',

                    operacao_ativada =
                        FALSE,

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campanha_eps_uuid = ?
                """,
                parameters=[
                    agora,
                    usuario["email"],
                    campanha_eps_uuid
                ]
            )

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
                        eps_usuario,

                    "escopo":
                        "EPS",

                    "status_anterior":
                        status_anterior,

                    "status_novo":
                        "EXECUCAO_FINALIZADA",

                    "etapa_pop":
                        "ENCERRAR_EXECUCAO_EPS",

                    "origem":
                        "EPS",

                    "usuario":
                        usuario["email"],

                    "dt_evento":
                        agora,

                    "observacao":
                        (
                            f"A EPS {eps_usuario} "
                            "finalizou sua execução "
                            "da campanha."
                        ),

                    "dispara_email":
                        True,

                    "tipo_evento_email":
                        "EPS_FINALIZOU_ATUACAO"
                }
            )

            resumo_resultados = (
                f"Vendas finais: "
                f"{payload.vendas_final}; "
                f"Matrículas finais: "
                f"{payload.matriculas_final}; "
                f"Mailing aplicável: "
                f"{mailing_aplicavel}."
            )

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
                        usuario["email"],

                    "origem":
                        "EPS",

                    "evento":
                        "ENCERRAMENTO_EXECUCAO_EPS",

                    "campo_alterado":
                        "status_execucao_eps",

                    "valor_anterior":
                        status_anterior,

                    "valor_novo":
                        "EXECUCAO_FINALIZADA",

                    "observacao":
                        resumo_resultados
                }
            )

            destinatarios = (
                buscar_destinatarios_campanha(
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
                        eps_usuario,

                    "tipo_evento":
                        "EPS_FINALIZOU_ATUACAO",

                    "assunto":
                        (
                            "[Central de Campanhas] "
                            f"{eps_usuario} finalizou atuação | "
                            f"{codigo_campanha.upper()} - "
                            f"{nome_campanha}"
                        ),

                    "destinatarios_to":
                        destinatarios,

                    "destinatarios_cc":
                        None,

                    "resumo_evento":
                        (
                            f"A EPS {eps_usuario} "
                            "finalizou sua atuação na "
                            f"campanha "
                            f"{codigo_campanha.upper()}."
                        ),

                    "status_envio":
                        "PENDENTE",

                    "tentativas_envio":
                        0,

                    "dt_criacao":
                        agora
                }
            )

            return {
                "codigo_campanha":
                    codigo_campanha.upper(),

                "eps":
                    eps_usuario,

                "status_anterior":
                    status_anterior,

                "status_execucao_eps":
                    "EXECUCAO_FINALIZADA",

                "execucao_concluida":
                    True,

                "operacao_ativada":
                    False,

                "mailing_aplicavel":
                    mailing_aplicavel,

                "responsavel_fechamento":
                    payload.responsavel_fechamento_eps,

                "dt_fechamento_eps":
                    agora,

                "ja_finalizada":
                    False
            }

        finally:
            cursor.close()
