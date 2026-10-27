import os

from app.db import (
    DATABASE,
    get_connection,
)

from app.email_service import (
    base_url,
    enviar_email,
    montar_html,
    separar_emails,
    status_email,
)


def _rows_to_dict(
    cursor,
    rows,
):
    columns = [
        item[0]
        for item in cursor.description
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


def _normalizar_status(
    status,
):
    return (
        status
        or "PENDENTE"
    ).upper()


def provider_status():
    # Antes: Power Automate. Agora: e-mail pelo Brevo.
    return status_email()


def listar_notificacoes(
    limit: int = 100,
):
    limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    itens = []

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            # A lista de EPS de cada campanha era montada no SQL
            # com sort_array/collect_set, funcoes do Databricks
            # que nao existem no Postgres. Agora a consulta so
            # busca as linhas e o agrupamento e feito no Python,
            # o que funciona igual nos dois bancos.
            cursor.execute(
                f"""
                SELECT
                    n.notificacao_uuid,
                    n.campaign_uuid,
                    m.codigo_campanha,
                    m.nome_campanha,
                    n.campanha_eps_uuid,
                    n.eps,
                    n.tipo_evento,
                    n.assunto,
                    n.destinatarios_to,
                    n.destinatarios_cc,
                    n.resumo_evento,
                    n.status_envio,
                    n.tentativas_envio,
                    n.dt_criacao,
                    n.dt_envio,
                    n.erro_envio

                FROM {DATABASE}.campanha_notificacao n

                LEFT JOIN {DATABASE}.campanha_master m
                    ON m.campaign_uuid =
                       n.campaign_uuid

                ORDER BY n.dt_criacao DESC

                LIMIT {limit}
                """
            )

            campanhas = _rows_to_dict(
                cursor,
                cursor.fetchall(),
            )

            cursor.execute(
                f"""
                SELECT campaign_uuid, eps
                FROM {DATABASE}.campanha_eps
                WHERE eps IS NOT NULL
                  AND trim(eps) <> ''
                """
            )

            eps_por_campanha = {}

            for campaign_uuid, eps in cursor.fetchall():
                eps_por_campanha.setdefault(
                    campaign_uuid, set()
                ).add(str(eps).strip())

            for item in campanhas:
                if not (item.get("eps") or "").strip():
                    item["eps"] = ", ".join(
                        sorted(
                            eps_por_campanha.get(
                                item.get("campaign_uuid"), set()
                            )
                        )
                    )

            for item in campanhas:
                item[
                    "origem_notificacao"
                ] = "CAMPANHA"

                itens.append(
                    item
                )

            cursor.execute(
                f"""
                SELECT
                    n.notificacao_uuid,
                    n.solicitacao_uuid,
                    s.email_usuario,
                    s.nome_usuario,
                    s.eps_identificada AS eps,
                    n.tipo_evento,
                    n.assunto,
                    n.destinatarios_to,
                    n.resumo_evento,
                    n.status_envio,
                    n.tentativas_envio,
                    n.dt_criacao,
                    n.dt_envio,
                    n.erro_envio

                FROM {DATABASE}.acesso_eps_notificacao n

                LEFT JOIN {DATABASE}.acesso_eps_solicitacao s
                    ON s.solicitacao_uuid =
                       n.solicitacao_uuid

                ORDER BY n.dt_criacao DESC

                LIMIT {limit}
                """
            )

            acessos = _rows_to_dict(
                cursor,
                cursor.fetchall(),
            )

            for item in acessos:
                item[
                    "origem_notificacao"
                ] = "ACESSO_EPS"

                item[
                    "codigo_campanha"
                ] = None

                item[
                    "nome_campanha"
                ] = None

                item[
                    "destinatarios_cc"
                ] = None

                itens.append(
                    item
                )

        finally:
            cursor.close()

    itens.sort(
        key=lambda item:
            str(
                item.get(
                    "dt_criacao",
                    ""
                )
            ),
        reverse=True,
    )

    itens = itens[:limit]

    resumo = {
        "pendentes": 0,
        "enviados": 0,
        "erros": 0,
        "arquivados": 0,
        "processando": 0,
    }

    for item in itens:
        status = _normalizar_status(
            item.get(
                "status_envio"
            )
        )

        if status in [
            "ENVIADO",
            "ENVIADA",
        ]:
            resumo["enviados"] += 1

        elif status == "ERRO":
            resumo["erros"] += 1

        elif status in [
            "ARQUIVADO",
            "ARQUIVADA",
        ]:
            resumo["arquivados"] += 1

        elif status == "PROCESSANDO":
            resumo["processando"] = (
                resumo.get("processando", 0)
                + 1
            )

        else:
            resumo["pendentes"] += 1

    return {
        "notificacoes":
            itens,

        "resumo":
            resumo,
    }


# ============================================================
# ENVIO
#
# O nome _enviar_webhook foi mantido de proposito: os
# modulos v72 e v8 importam esta funcao. So o que ela faz
# por dentro mudou — em vez de chamar o Power Automate, monta
# o e-mail e envia pelo Brevo.
# ============================================================

def _portal_do_destinatario(destinatarios):
    """
    Interno se algum destinatario for do dominio EduNova;
    caso contrario, portal EPS.
    """
    dominio = (
        os.getenv("EMAIL_DOMINIO_INTERNO", "edunova.com.br")
        .strip()
        .lower()
    )

    if any(e.endswith("@" + dominio) for e in destinatarios):
        return "/portal-interno"

    return "/portal-eps"


def _nome_evento(tipo_evento):
    if not tipo_evento:
        return ""

    return str(tipo_evento).replace("_", " ").strip().capitalize()


def _email_da_notificacao(payload):
    destinatarios = separar_emails(
        payload.get("destinatarios_to")
    )

    codigo = payload.get("codigo_campanha") or ""
    nome = payload.get("nome_campanha") or ""
    assunto = (
        payload.get("assunto")
        or payload.get("tipo_evento")
        or "Central de Campanhas"
    )

    titulo = nome or assunto

    detalhes = [
        ("Campanha", codigo),
        ("EPS", payload.get("eps")),
        ("Evento", _nome_evento(payload.get("tipo_evento"))),
    ]

    url = base_url()

    botao = (
        ("Abrir a Central", url + _portal_do_destinatario(destinatarios))
        if url
        else None
    )

    corpo_html = montar_html(
        titulo=titulo,
        paragrafos=[payload.get("resumo_evento")],
        detalhes=detalhes,
        botao=botao,
    )

    texto = "\n".join(
        parte
        for parte in [
            titulo,
            "",
            str(payload.get("resumo_evento") or ""),
            "",
            f"Campanha: {codigo}" if codigo else "",
            f"EPS: {payload.get('eps')}" if payload.get("eps") else "",
            botao[1] if botao else "",
        ]
        if parte is not None
    )

    return assunto, corpo_html, texto


def _enviar_webhook(
    payload,
):
    assunto, corpo_html, texto = _email_da_notificacao(
        payload
    )

    enviar_email(
        para=payload.get("destinatarios_to"),
        cc=payload.get("destinatarios_cc"),
        assunto=assunto,
        html_corpo=corpo_html,
        texto=texto,
    )


def _atualizar_status(
    tabela,
    notificacao_uuid,
    status,
    tentativas,
    erro=None,
):
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            if status == "ENVIADO":
                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.{tabela}

                    SET
                        status_envio = ?,
                        tentativas_envio = ?,
                        dt_envio = current_timestamp(),
                        erro_envio = NULL

                    WHERE notificacao_uuid = ?
                    """,
                    parameters=[
                        status,
                        tentativas,
                        notificacao_uuid,
                    ],
                )

            else:
                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.{tabela}

                    SET
                        status_envio = ?,
                        tentativas_envio = ?,
                        erro_envio = ?

                    WHERE notificacao_uuid = ?
                    """,
                    parameters=[
                        status,
                        tentativas,
                        erro,
                        notificacao_uuid,
                    ],
                )

        finally:
            cursor.close()


def processar_notificacoes(
    limite: int = 30,
):
    status_provider = (
        provider_status()
    )

    if not status_provider[
        "configurado"
    ]:
        raise ValueError(
            "Envio de e-mail não configurado. "
            "Defina BREVO_API_KEY e EMAIL_REMETENTE."
        )

    dados = listar_notificacoes(
        limit=500
    )

    pendentes = [
        item
        for item in dados[
            "notificacoes"
        ]
        if _normalizar_status(
            item.get(
                "status_envio"
            )
        ) not in [
            "ENVIADO",
            "ENVIADA",
        ]
    ]

    pendentes = pendentes[
        :max(
            1,
            min(
                int(limite),
                100,
            )
        )
    ]

    enviadas = 0
    erros = 0

    for item in pendentes:
        tentativas = (
            item.get(
                "tentativas_envio"
            )
            or 0
        ) + 1

        origem = item.get(
            "origem_notificacao"
        )

        tabela = (
            "acesso_eps_notificacao"
            if origem == "ACESSO_EPS"
            else "campanha_notificacao"
        )

        payload = {
            "notificacao_uuid":
                item.get(
                    "notificacao_uuid"
                ),

            "origem":
                origem,

            "codigo_campanha":
                item.get(
                    "codigo_campanha"
                ),

            "nome_campanha":
                item.get(
                    "nome_campanha"
                ),

            "eps":
                item.get(
                    "eps"
                ),

            "tipo_evento":
                item.get(
                    "tipo_evento"
                ),

            "assunto":
                item.get(
                    "assunto"
                ),

            "destinatarios_to":
                item.get(
                    "destinatarios_to"
                ),

            "destinatarios_cc":
                item.get(
                    "destinatarios_cc"
                ),

            "resumo_evento":
                item.get(
                    "resumo_evento"
                ),

            "dt_criacao":
                item.get(
                    "dt_criacao"
                ),
        }

        try:
            _enviar_webhook(
                payload
            )

            _atualizar_status(
                tabela,
                item[
                    "notificacao_uuid"
                ],
                "ENVIADO",
                tentativas,
            )

            enviadas += 1

        except Exception as error:
            _atualizar_status(
                tabela,
                item[
                    "notificacao_uuid"
                ],
                "ERRO",
                tentativas,
                str(error),
            )

            erros += 1

    return {
        "processadas":
            len(pendentes),

        "enviadas":
            enviadas,

        "erros":
            erros,
    }