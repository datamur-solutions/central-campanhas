from app.notification_service_v7 import (
    _atualizar_status,
    _enviar_webhook,
    _normalizar_status,
    listar_notificacoes,
    provider_status,
)


def _garantir_provider():
    status = provider_status()

    if not status.get("configurado"):
        raise ValueError(
            "Conector Power Automate não configurado."
        )


def _separar_por_status():
    dados = listar_notificacoes(limit=500)
    itens = dados.get("notificacoes", [])

    pendentes = []
    erros = []

    for item in itens:
        status = _normalizar_status(
            item.get("status_envio")
        )

        if status == "ERRO":
            erros.append(item)

        elif status in [
            "ARQUIVADO",
            "ARQUIVADA",
            "PROCESSANDO",
        ]:
            continue

        elif status not in [
            "ENVIADO",
            "ENVIADA",
        ]:
            pendentes.append(item)

    return pendentes, erros


def _texto(valor):
    """
    O esquema do gatilho HTTP do Power Automate foi gerado
    com campos do tipo string. Alguns eventos da Central
    podem ter campos não aplicáveis (por exemplo EPS na
    criação inicial da campanha), chegando como None.

    Para o Power Automate, enviamos string vazia nesses casos.
    """
    if valor is None:
        return ""

    return str(valor)


def _payload_item(
    item,
    destinatario_override=None,
    assunto_prefixo=None,
):
    assunto = (
        item.get("assunto")
        or item.get("tipo_evento")
        or "Central de Campanhas"
    )

    if assunto_prefixo:
        assunto = f"{assunto_prefixo} {assunto}"

    destinatarios_to = (
        destinatario_override
        or item.get("destinatarios_to")
        or ""
    )

    destinatarios_cc = (
        ""
        if destinatario_override
        else (
            item.get("destinatarios_cc")
            or ""
        )
    )

    return {
        "notificacao_uuid":
            _texto(
                item.get("notificacao_uuid")
            ),

        "origem":
            _texto(
                item.get("origem_notificacao")
            ),

        "codigo_campanha":
            _texto(
                item.get("codigo_campanha")
            ),

        "nome_campanha":
            _texto(
                item.get("nome_campanha")
            ),

        "eps":
            _texto(
                item.get("eps")
            ),

        "tipo_evento":
            _texto(
                item.get("tipo_evento")
            ),

        "assunto":
            _texto(
                assunto
            ),

        "destinatarios_to":
            _texto(
                destinatarios_to
            ),

        "destinatarios_cc":
            _texto(
                destinatarios_cc
            ),

        "resumo_evento":
            _texto(
                item.get("resumo_evento")
            ),

        "dt_criacao":
            _texto(
                item.get("dt_criacao")
            ),
    }


def _tabela_item(item):
    return (
        "acesso_eps_notificacao"
        if item.get("origem_notificacao") == "ACESSO_EPS"
        else "campanha_notificacao"
    )


def testar_uma_notificacao(
    email_teste: str,
):
    _garantir_provider()

    pendentes, erros = _separar_por_status()

    if pendentes:
        item = pendentes[0]
        origem_fila = "PENDENTE"

    elif erros:
        item = erros[0]
        origem_fila = "ERRO"

    else:
        raise ValueError(
            "Não existe notificação pendente ou com erro para testar."
        )

    try:
        _enviar_webhook(
            _payload_item(
                item,
                destinatario_override=email_teste,
                assunto_prefixo="[TESTE]",
            )
        )

    except Exception as error:
        raise ValueError(
            "Falha no teste com o Power Automate: "
            + str(error)
        ) from error

    return {
        "sucesso": True,
        "destinatario_teste": email_teste,
        "notificacao_uuid": item.get("notificacao_uuid"),
        "codigo_campanha": item.get("codigo_campanha"),
        "origem_fila": origem_fila,
        "fila_alterada": False,
    }


def _processar_lista(itens):
    enviadas = 0
    erros = 0

    for item in itens:
        tentativas = (
            item.get("tentativas_envio")
            or 0
        ) + 1

        tabela = _tabela_item(item)

        try:
            _enviar_webhook(
                _payload_item(item)
            )

            _atualizar_status(
                tabela,
                item["notificacao_uuid"],
                "ENVIADO",
                tentativas,
            )

            enviadas += 1

        except Exception as error:
            _atualizar_status(
                tabela,
                item["notificacao_uuid"],
                "ERRO",
                tentativas,
                str(error),
            )

            erros += 1

    return enviadas, erros


def processar_pendentes_confirmado(
    confirmar: bool,
    quantidade_esperada: int,
):
    _garantir_provider()

    if not confirmar:
        raise ValueError(
            "Envio não confirmado."
        )

    pendentes, _ = _separar_por_status()
    quantidade_atual = len(pendentes)

    if quantidade_atual != int(quantidade_esperada):
        raise ValueError(
            "A quantidade da fila mudou desde a revisão. "
            f"Você revisou {quantidade_esperada}, "
            f"mas agora existem {quantidade_atual}. "
            "Atualize a tela e revise novamente."
        )

    enviadas, erros = _processar_lista(
        pendentes
    )

    pendentes_restantes, _ = _separar_por_status()

    return {
        "processadas": quantidade_atual,
        "enviadas": enviadas,
        "erros": erros,
        "restantes": len(pendentes_restantes),
    }


def reprocessar_erros_confirmado(
    confirmar: bool,
    quantidade_esperada: int,
):
    _garantir_provider()

    if not confirmar:
        raise ValueError(
            "Reprocessamento não confirmado."
        )

    _, erros_itens = _separar_por_status()
    quantidade_atual = len(erros_itens)

    if quantidade_atual != int(quantidade_esperada):
        raise ValueError(
            "A quantidade de erros mudou desde a revisão. "
            f"Você revisou {quantidade_esperada}, "
            f"mas agora existem {quantidade_atual}. "
            "Atualize a tela e revise novamente."
        )

    enviadas, erros = _processar_lista(
        erros_itens
    )

    _, erros_restantes = _separar_por_status()

    return {
        "processadas": quantidade_atual,
        "enviadas": enviadas,
        "erros": erros,
        "restantes": len(erros_restantes),
    }



def arquivar_erros_confirmado(
    confirmar: bool,
    quantidade_esperada: int,
    usuario: str,
):
    if not confirmar:
        raise ValueError(
            "Arquivamento não confirmado."
        )

    _, erros_itens = _separar_por_status()
    quantidade_atual = len(erros_itens)

    if quantidade_atual != int(
        quantidade_esperada
    ):
        raise ValueError(
            "A quantidade de erros mudou desde a revisão. "
            f"Você revisou {quantidade_esperada}, "
            f"mas agora existem {quantidade_atual}. "
            "Atualize a tela e revise novamente."
        )

    if quantidade_atual == 0:
        raise ValueError(
            "Não existem notificações com erro para arquivar."
        )

    from app.db import (
        DATABASE,
        get_connection,
    )

    arquivadas = 0

    for item in erros_itens:
        tabela = _tabela_item(item)
        notificacao_uuid = item.get(
            "notificacao_uuid"
        )

        motivo = (
            "ARQUIVADO SEM ENVIO PELO PORTAL INTERNO. "
            f"Responsável: {usuario}. "
            "Motivo: erro histórico anterior à validação "
            "da integração Power Automate. | "
        )

        with get_connection() as connection:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.{tabela}

                    SET
                        status_envio = 'ARQUIVADO',

                        erro_envio = concat(
                            ?,
                            coalesce(
                                erro_envio,
                                ''
                            )
                        )

                    WHERE notificacao_uuid = ?

                      AND upper(
                            coalesce(
                                status_envio,
                                'PENDENTE'
                            )
                          ) = 'ERRO'
                    """,
                    parameters=[
                        motivo,
                        notificacao_uuid,
                    ],
                )

                arquivadas += 1

            finally:
                cursor.close()

    _, erros_restantes = _separar_por_status()

    return {
        "arquivadas": arquivadas,
        "erros_restantes": len(erros_restantes),
        "envios_realizados": 0,
    }
