import uuid

from datetime import (
    datetime,
    timezone,
)

from app.db import (
    DATABASE,
    get_connection,
)


def agora_utc():
    return datetime.now(
        timezone.utc
    )


def novo_uuid():
    return str(
        uuid.uuid4()
    )


def linhas_para_dict(
    cursor,
    rows,
):
    colunas = [
        item[0]
        for item in cursor.description
    ]

    return [
        dict(
            zip(
                colunas,
                row,
            )
        )
        for row in rows
    ]


def insert_dict(
    cursor,
    table_name,
    data,
):
    colunas = list(
        data.keys()
    )

    placeholders = ", ".join(
        ["?"] * len(colunas)
    )

    cursor.execute(
        f"""
        INSERT INTO {DATABASE}.{table_name}
        (
            {", ".join(colunas)}
        )
        VALUES
        (
            {placeholders}
        )
        """,
        parameters=[
            data[coluna]
            for coluna in colunas
        ],
    )


def listar_solicitacoes_acesso_pendentes():
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    solicitacao_uuid,
                    email_usuario,
                    nome_usuario,
                    dominio_email,
                    eps_identificada,
                    dt_solicitacao,
                    status_solicitacao,
                    origem

                FROM {DATABASE}.acesso_eps_solicitacao

                WHERE upper(status_solicitacao) =
                      'PENDENTE'

                ORDER BY dt_solicitacao DESC
                """
            )

            return linhas_para_dict(
                cursor,
                cursor.fetchall(),
            )

        finally:
            cursor.close()


def listar_campanhas_prontas_encerramento():
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    m.codigo_campanha,
                    m.nome_campanha,
                    COUNT(*) AS total_eps,
                    SUM(
                        CASE
                            WHEN e.status_execucao_eps =
                                 'EXECUCAO_FINALIZADA'
                            THEN 1
                            ELSE 0
                        END
                    ) AS eps_finalizadas

                FROM {DATABASE}.campanha_master m

                INNER JOIN {DATABASE}.campanha_eps e
                    ON e.campaign_uuid =
                       m.campaign_uuid

                WHERE e.liberada_para_eps = TRUE

                  AND m.status_campanha =
                      'ENVIADA_EPS'

                GROUP BY
                    m.codigo_campanha,
                    m.nome_campanha

                HAVING
                    COUNT(*) > 0

                    AND SUM(
                        CASE
                            WHEN e.status_execucao_eps =
                                 'EXECUCAO_FINALIZADA'
                            THEN 1
                            ELSE 0
                        END
                    ) = COUNT(*)

                ORDER BY
                    m.codigo_campanha DESC
                """
            )

            return linhas_para_dict(
                cursor,
                cursor.fetchall(),
            )

        finally:
            cursor.close()


def encerrar_campanha_edunova(
    codigo_campanha: str,
    decisao: str,
    resumo: str,
    aprendizados: str,
    usuario: str,
):
    agora = agora_utc()

    decisao = (
        decisao
        .strip()
        .upper()
    )

    decisoes_validas = [
        "ENCERRAR",
        "REPLICAR",
        "AJUSTAR_E_REPLICAR",
        "NAO_REPLICAR",
    ]

    if decisao not in decisoes_validas:
        raise ValueError(
            "Decisão final inválida."
        )

    resumo = (
        resumo
        .strip()
    )

    aprendizados = (
        aprendizados
        .strip()
    )

    if not resumo:
        raise ValueError(
            "Informe o resumo do resultado."
        )

    if not aprendizados:
        raise ValueError(
            "Informe o principal aprendizado."
        )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    campaign_uuid,
                    codigo_campanha,
                    nome_campanha,
                    status_campanha

                FROM {DATABASE}.campanha_master

                WHERE upper(codigo_campanha) =
                      upper(?)

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ],
            )

            campanha = (
                cursor.fetchone()
            )

            if not campanha:
                raise ValueError(
                    "Campanha não encontrada."
                )

            campaign_uuid = (
                campanha[0]
            )

            status_atual = (
                campanha[3]
            )

            if (
                status_atual ==
                "ENCERRADA_EDUNOVA"
            ):
                return {
                    "codigo_campanha":
                        campanha[1],

                    "nome_campanha":
                        campanha[2],

                    "status":
                        "ENCERRADA_EDUNOVA",

                    "ja_encerrada":
                        True,
                }

            if (
                status_atual !=
                "ENVIADA_EPS"
            ):
                raise ValueError(
                    "A campanha ainda não está "
                    "na etapa de encerramento EduNova."
                )

            cursor.execute(
                f"""
                SELECT
                    eps,
                    status_execucao_eps

                FROM {DATABASE}.campanha_eps

                WHERE campaign_uuid = ?

                  AND liberada_para_eps = TRUE

                ORDER BY eps
                """,
                parameters=[
                    campaign_uuid
                ],
            )

            eps_rows = (
                cursor.fetchall()
            )

            if not eps_rows:
                raise ValueError(
                    "A campanha não possui EPS "
                    "liberadas para execução."
                )

            pendentes = [
                row[0]
                for row in eps_rows
                if row[1] !=
                   "EXECUCAO_FINALIZADA"
            ]

            if pendentes:
                raise ValueError(
                    "Ainda existem EPS sem fechamento: "
                    + ", ".join(
                        pendentes
                    )
                )

            observacao = (
                f"Decisão final: {decisao}. "
                f"Resumo: {resumo}. "
                f"Aprendizados: {aprendizados}"
            )

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_master

                SET
                    status_campanha =
                        'ENCERRADA_EDUNOVA',

                    etapa_pop =
                        'ENCERRAMENTO_EDUNOVA',

                    dt_atualizacao = ?,

                    atualizado_por = ?

                WHERE campaign_uuid = ?
                """,
                parameters=[
                    agora,
                    usuario,
                    campaign_uuid,
                ],
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
                        usuario,

                    "origem":
                        "PORTAL_INTERNO",

                    "evento":
                        "ENCERRAMENTO_EDUNOVA",

                    "campo_alterado":
                        "status_campanha",

                    "valor_anterior":
                        status_atual,

                    "valor_novo":
                        "ENCERRADA_EDUNOVA",

                    "observacao":
                        observacao,
                },
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
                        None,

                    "eps":
                        None,

                    "escopo":
                        "EDUNOVA",

                    "status_anterior":
                        status_atual,

                    "status_novo":
                        "ENCERRADA_EDUNOVA",

                    "etapa_pop":
                        "ENCERRAMENTO_EDUNOVA",

                    "origem":
                        "PORTAL_INTERNO",

                    "usuario":
                        usuario,

                    "dt_evento":
                        agora,

                    "observacao":
                        observacao,

                    "dispara_email":
                        True,

                    "tipo_evento_email":
                        "EDUNOVA_ENCERROU_CAMPANHA",
                },
            )

            # ------------------------------------------------
            # REGISTRO DO ENCERRAMENTO
            #
            # Faltava esta gravacao: o status virava
            # ENCERRADA_EDUNOVA, o workflow e o historico eram
            # escritos, mas a apuracao em si nunca era salva.
            # A tabela ficava vazia e o historico de campanhas
            # nao tinha de onde ler resultado.
            #
            # O funil e a classificacao chegam depois, pela
            # salvar_funil_encerramento, que atualiza esta
            # mesma linha.
            # ------------------------------------------------

            insert_dict(
                cursor,
                "campanha_encerramento_edunova",
                {
                    "encerramento_edunova_uuid":
                        novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "dt_encerramento":
                        agora,

                    "aprendizados":
                        aprendizados,

                    "decisao_final":
                        decisao,

                    # A tabela nao tem coluna de resumo: o
                    # texto vai em recomendacoes, que e o
                    # campo livre existente.
                    "recomendacoes":
                        resumo,

                    "criado_por":
                        usuario,

                    "dt_criacao":
                        agora,
                },
            )

            return {
                "codigo_campanha":
                    campanha[1],

                "nome_campanha":
                    campanha[2],

                "status":
                    "ENCERRADA_EDUNOVA",

                "decisao":
                    decisao,

                "resumo":
                    resumo,

                "aprendizados":
                    aprendizados,

                "ja_encerrada":
                    False,
            }

        finally:
            cursor.close()