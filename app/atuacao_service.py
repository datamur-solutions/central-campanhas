"""
ATUAÇÃO POR CANAL E COPY DE WHATSAPP

Duas camadas, na ordem em que acontecem:

1. O Planejamento sugere os canais no cadastro, com uma
   justificativa. É sugestão, não ordem.
2. Cada EPS define a forma de atuação definitiva e, quando
   atuar por WhatsApp, registra a copy e uma imagem opcional.

Tudo é opcional e só faz sentido quando a ação tem mailing.
O Planejamento e o Comercial enxergam as duas camadas no
portal interno.

Módulo separado de propósito: não altera o cadastro nem o
plano operacional, que já funcionam. Grava depois deles.
"""

import base64
import binascii

from datetime import datetime, timezone

from app.db import (
    DATABASE,
    get_connection,
)

from app.external_service import (
    obter_usuario_eps_aprovado,
)


CANAIS_VALIDOS = [
    "WHATSAPP",
    "DISCADOR",
    "RCS",
    "TODOS",
]

TIPOS_IMAGEM = [
    "image/png",
    "image/jpeg",
    "image/webp",
]

# ~1,5 MB. A imagem vai no banco como texto; acima disso o
# Supabase gratuito sente, e copy de WhatsApp não precisa
# de mais que isso.
TAMANHO_MAXIMO_IMAGEM = 1_500_000


def _agora():
    return datetime.now(timezone.utc)


def _linhas(cursor):
    nomes = [
        item[0]
        for item in cursor.description
    ]

    return [
        dict(zip(nomes, linha))
        for linha in cursor.fetchall()
    ]


def _normalizar_canais(lista):
    """
    Deduplica e valida. Se "TODOS" vier junto de outros,
    fica só "TODOS" — marcar os dois não acrescenta nada.
    """
    canais = []

    for item in (lista or []):
        valor = str(item).strip().upper()

        if valor in CANAIS_VALIDOS and valor not in canais:
            canais.append(valor)

    if "TODOS" in canais:
        return ["TODOS"]

    return canais


def _campaign_uuid(cursor, codigo_campanha):
    cursor.execute(
        f"""
        SELECT campaign_uuid
        FROM {DATABASE}.campanha_master
        WHERE upper(codigo_campanha) = upper(?)
        LIMIT 1
        """,
        parameters=[codigo_campanha]
    )

    linha = cursor.fetchone()

    if not linha:
        raise ValueError(
            "Campanha não encontrada."
        )

    return linha[0]


# ============================================================
# 1. SUGESTÃO DO PLANEJAMENTO
# ============================================================

def salvar_sugestao_atuacao(
    codigo_campanha,
    payload,
    usuario_email,
):

    canais = _normalizar_canais(
        payload.get("canais")
    )

    justificativa = (
        payload.get("justificativa") or ""
    ).strip() or None

    # Nada informado não é erro: a ação pode não ter mailing.
    if not canais and not justificativa:
        return {"sugestao_registrada": False}

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            campaign_uuid = _campaign_uuid(
                cursor,
                codigo_campanha,
            )

            cursor.execute(
                f"""
                SELECT 1
                FROM {DATABASE}.campanha_atuacao_sugestao
                WHERE campaign_uuid = ?
                LIMIT 1
                """,
                parameters=[campaign_uuid]
            )

            existe = cursor.fetchone()

            valores = [
                ",".join(canais) or None,
                justificativa,
                usuario_email,
                _agora(),
            ]

            if existe:
                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.campanha_atuacao_sugestao
                    SET canais = ?,
                        justificativa = ?,
                        sugerido_por = ?,
                        dt_atualizacao = ?
                    WHERE campaign_uuid = ?
                    """,
                    parameters=valores + [campaign_uuid]
                )

            else:
                cursor.execute(
                    f"""
                    INSERT INTO
                        {DATABASE}.campanha_atuacao_sugestao
                    (
                        canais,
                        justificativa,
                        sugerido_por,
                        dt_atualizacao,
                        campaign_uuid
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    parameters=valores + [campaign_uuid]
                )

            return {
                "sugestao_registrada": True,
                "canais": canais,
            }

        finally:
            cursor.close()


# ============================================================
# 2. FORMA DEFINITIVA DA EPS + COPY
# ============================================================

def _validar_imagem(payload):
    """
    Devolve (base64, nome, tipo) ou (None, None, None).

    Recusa tipo e tamanho fora do combinado em vez de gravar
    um arquivo que depois ninguém consegue abrir.
    """
    bruto = payload.get("imagem_base64")

    if not bruto:
        return None, None, None

    tipo = (
        payload.get("imagem_tipo") or ""
    ).strip().lower()

    if tipo not in TIPOS_IMAGEM:
        raise ValueError(
            "A imagem precisa ser PNG, JPG ou WEBP."
        )

    try:
        conteudo = base64.b64decode(
            bruto,
            validate=True,
        )

    except (binascii.Error, ValueError) as erro:
        raise ValueError(
            "Não foi possível ler a imagem enviada."
        ) from erro

    if len(conteudo) > TAMANHO_MAXIMO_IMAGEM:
        raise ValueError(
            "A imagem passa de 1,5 MB. "
            "Envie uma versão menor."
        )

    nome = (
        payload.get("imagem_nome") or "imagem"
    ).strip()[:120]

    return bruto, nome, tipo


def salvar_atuacao_eps(
    email_usuario,
    codigo_campanha,
    payload,
):

    usuario = obter_usuario_eps_aprovado(
        email_usuario
    )

    eps = usuario["eps"]

    canais = _normalizar_canais(
        payload.get("canais")
    )

    atua_whatsapp = (
        "WHATSAPP" in canais
        or "TODOS" in canais
    )

    # A copy só vale para WhatsApp. Fora disso é descartada,
    # para não sobrar texto órfão associado a outro canal.
    copy_whatsapp = None
    imagem = (None, None, None)

    if atua_whatsapp:
        copy_whatsapp = (
            payload.get("copy_whatsapp") or ""
        ).strip() or None

        imagem = _validar_imagem(payload)

    manter_imagem = bool(
        payload.get("manter_imagem")
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT m.campaign_uuid
                FROM {DATABASE}.campanha_master m
                INNER JOIN {DATABASE}.campanha_eps ce
                    ON ce.campaign_uuid = m.campaign_uuid
                WHERE upper(m.codigo_campanha) = upper(?)
                  AND ce.eps = ?
                  AND ce.liberada_para_eps = TRUE
                LIMIT 1
                """,
                parameters=[codigo_campanha, eps]
            )

            linha = cursor.fetchone()

            if not linha:
                raise PermissionError(
                    "Campanha não disponível "
                    "para a sua EPS."
                )

            campaign_uuid = linha[0]

            cursor.execute(
                f"""
                SELECT
                    imagem_base64,
                    imagem_nome,
                    imagem_tipo
                FROM {DATABASE}.campanha_eps_atuacao
                WHERE campaign_uuid = ?
                  AND eps = ?
                LIMIT 1
                """,
                parameters=[campaign_uuid, eps]
            )

            anterior = cursor.fetchone()

            # Reenviar o formulário sem trocar a imagem não
            # pode apagar a que já estava salva.
            if (
                imagem[0] is None
                and manter_imagem
                and anterior
                and atua_whatsapp
            ):
                imagem = (
                    anterior[0],
                    anterior[1],
                    anterior[2],
                )

            valores = [
                ",".join(canais) or None,
                copy_whatsapp,
                imagem[0],
                imagem[1],
                imagem[2],
                usuario["email"],
                _agora(),
            ]

            if anterior is not None:
                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.campanha_eps_atuacao
                    SET canais = ?,
                        copy_whatsapp = ?,
                        imagem_base64 = ?,
                        imagem_nome = ?,
                        imagem_tipo = ?,
                        atualizado_por = ?,
                        dt_atualizacao = ?
                    WHERE campaign_uuid = ?
                      AND eps = ?
                    """,
                    parameters=(
                        valores + [campaign_uuid, eps]
                    )
                )

            else:
                cursor.execute(
                    f"""
                    INSERT INTO
                        {DATABASE}.campanha_eps_atuacao
                    (
                        canais,
                        copy_whatsapp,
                        imagem_base64,
                        imagem_nome,
                        imagem_tipo,
                        atualizado_por,
                        dt_atualizacao,
                        campaign_uuid,
                        eps
                    )
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    parameters=(
                        valores + [campaign_uuid, eps]
                    )
                )

            return {
                "atuacao_registrada": True,
                "eps": eps,
                "canais": canais,
                "tem_copy": bool(copy_whatsapp),
                "tem_imagem": bool(imagem[0]),
            }

        finally:
            cursor.close()


# ============================================================
# 3. LEITURA
# ============================================================

def _ler_atuacao(cursor, campaign_uuid, eps=None):

    cursor.execute(
        f"""
        SELECT
            canais,
            justificativa,
            sugerido_por,
            dt_atualizacao
        FROM {DATABASE}.campanha_atuacao_sugestao
        WHERE campaign_uuid = ?
        LIMIT 1
        """,
        parameters=[campaign_uuid]
    )

    encontrados = _linhas(cursor)

    sugestao = encontrados[0] if encontrados else None

    if sugestao:
        sugestao["canais"] = [
            item
            for item in (
                sugestao.get("canais") or ""
            ).split(",")
            if item
        ]

    filtro = "AND eps = ?" if eps else ""

    parametros = (
        [campaign_uuid] + ([eps] if eps else [])
    )

    cursor.execute(
        f"""
        SELECT
            eps,
            canais,
            copy_whatsapp,
            imagem_base64,
            imagem_nome,
            imagem_tipo,
            atualizado_por,
            dt_atualizacao
        FROM {DATABASE}.campanha_eps_atuacao
        WHERE campaign_uuid = ? {filtro}
        ORDER BY eps
        """,
        parameters=parametros
    )

    atuacoes = _linhas(cursor)

    for item in atuacoes:
        item["canais"] = [
            canal
            for canal in (
                item.get("canais") or ""
            ).split(",")
            if canal
        ]

    return sugestao, atuacoes


def obter_atuacao_interna(codigo_campanha):

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            campaign_uuid = _campaign_uuid(
                cursor,
                codigo_campanha,
            )

            sugestao, atuacoes = _ler_atuacao(
                cursor,
                campaign_uuid,
            )

            return {
                "sugestao": sugestao,
                "eps": atuacoes,
            }

        finally:
            cursor.close()


def obter_atuacao_eps(email_usuario, codigo_campanha):

    usuario = obter_usuario_eps_aprovado(
        email_usuario
    )

    eps = usuario["eps"]

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            campaign_uuid = _campaign_uuid(
                cursor,
                codigo_campanha,
            )

            sugestao, atuacoes = _ler_atuacao(
                cursor,
                campaign_uuid,
                eps,
            )

            return {
                "sugestao": sugestao,
                "minha": atuacoes[0] if atuacoes else None,
            }

        finally:
            cursor.close()
