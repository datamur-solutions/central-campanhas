import os
import threading
import uuid

from app.db import (
    DATABASE,
    get_connection,
)

from app.notification_service_v7 import (
    _atualizar_status,
    _enviar_webhook,
    _normalizar_status,
    listar_notificacoes,
    provider_status,
)

from app.notification_service_v72 import (
    _payload_item,
    _tabela_item,
)


_worker_lock = threading.Lock()


def automacao_habilitada():
    valor = (
        os.getenv(
            "AUTO_NOTIFICATIONS_ENABLED",
            "false",
        )
        .strip()
        .lower()
    )

    return valor in {
        "1",
        "true",
        "yes",
        "sim",
        "on",
    }


def automation_status():
    provider = provider_status()
    enabled = automacao_habilitada()

    return {
        "habilitada": enabled,
        "provider_configurado": bool(
            provider.get("configurado")
        ),
        "ativa": (
            enabled
            and bool(
                provider.get("configurado")
            )
        ),
        "modo": (
            "AUTOMATICO"
            if enabled
            else "MANUAL_SEGURO"
        ),
        "variavel_env":
            "AUTO_NOTIFICATIONS_ENABLED",
    }


def _claim_item(item):
    tabela = _tabela_item(item)
    notificacao_uuid = item.get(
        "notificacao_uuid"
    )

    token = (
        "AUTO_CLAIM:"
        + str(uuid.uuid4())
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                UPDATE {DATABASE}.{tabela}

                SET
                    status_envio =
                        'PROCESSANDO',

                    erro_envio = ?

                WHERE notificacao_uuid = ?

                  AND upper(
                        coalesce(
                            status_envio,
                            'PENDENTE'
                        )
                      ) = 'PENDENTE'
                """,
                parameters=[
                    token,
                    notificacao_uuid,
                ],
            )

            cursor.execute(
                f"""
                SELECT
                    status_envio,
                    erro_envio

                FROM {DATABASE}.{tabela}

                WHERE notificacao_uuid = ?

                LIMIT 1
                """,
                parameters=[
                    notificacao_uuid
                ],
            )

            row = cursor.fetchone()

            if not row:
                return None

            status_atual = (
                row[0]
                or ""
            ).upper()

            token_atual = (
                row[1]
                or ""
            )

            if (
                status_atual == "PROCESSANDO"
                and token_atual == token
            ):
                return {
                    "tabela": tabela,
                    "token": token,
                }

            return None

        finally:
            cursor.close()


def _pendentes_automaticos(
    limite=100,
):
    dados = listar_notificacoes(
        limit=500
    )

    pendentes = []

    for item in dados.get(
        "notificacoes",
        []
    ):
        status = _normalizar_status(
            item.get("status_envio")
        )

        if status == "PENDENTE":
            pendentes.append(item)

        if len(pendentes) >= limite:
            break

    return pendentes


def processar_pendentes_automaticamente(
    limite=100,
):
    status = automation_status()

    if not status["ativa"]:
        return {
            "executado": False,
            "motivo":
                "AUTOMACAO_DESATIVADA",
        }

    if not _worker_lock.acquire(
        blocking=False
    ):
        return {
            "executado": False,
            "motivo":
                "WORKER_EM_EXECUCAO",
        }

    try:
        pendentes = (
            _pendentes_automaticos(
                limite=limite
            )
        )

        enviadas = 0
        erros = 0
        ignoradas = 0

        for item in pendentes:
            claim = _claim_item(item)

            if not claim:
                ignoradas += 1
                continue

            tentativas = (
                item.get(
                    "tentativas_envio"
                )
                or 0
            ) + 1

            try:
                _enviar_webhook(
                    _payload_item(item)
                )

                _atualizar_status(
                    claim["tabela"],
                    item["notificacao_uuid"],
                    "ENVIADO",
                    tentativas,
                )

                enviadas += 1

            except Exception as error:
                _atualizar_status(
                    claim["tabela"],
                    item["notificacao_uuid"],
                    "ERRO",
                    tentativas,
                    str(error),
                )

                erros += 1

        return {
            "executado": True,
            "encontradas": len(pendentes),
            "enviadas": enviadas,
            "erros": erros,
            "ignoradas": ignoradas,
        }

    finally:
        _worker_lock.release()


def disparar_automatico_sem_excecao():
    try:
        resultado = (
            processar_pendentes_automaticamente()
        )

        print(
            "[AUTO-NOTIFICACOES]",
            resultado,
        )

        return resultado

    except Exception as error:
        print(
            "[AUTO-NOTIFICACOES] ERRO:",
            str(error),
        )

        return {
            "executado": False,
            "motivo": "ERRO_WORKER",
            "erro": str(error),
        }


def testar_automacao_v8(
    email_teste: str,
):
    provider = provider_status()

    if not provider.get(
        "configurado"
    ):
        raise ValueError(
            "Power Automate não está configurado."
        )

    payload = {
        "notificacao_uuid":
            "TESTE-V8",
        "origem":
            "TESTE_AUTOMACAO_V8",
        "codigo_campanha":
            "TESTE",
        "nome_campanha":
            "Validação do envio automático",
        "eps":
            "",
        "tipo_evento":
            "TESTE_AUTOMACAO_V8",
        "assunto":
            "[TESTE V8] Central de Campanhas | Envio automático",
        "destinatarios_to":
            email_teste,
        "destinatarios_cc":
            "",
        "resumo_evento":
            (
                "Teste controlado da V8. "
                "Nenhuma notificação da fila foi consumida."
            ),
        "dt_criacao":
            "",
    }

    _enviar_webhook(payload)

    return {
        "sucesso": True,
        "destinatario_teste":
            email_teste,
        "fila_alterada": False,
    }
