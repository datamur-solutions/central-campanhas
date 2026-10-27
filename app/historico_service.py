"""
DIARIO DE BORDO E COPYS NO HISTORICO

Diario de bordo: o que a EPS e o time interno escrevem em
"Como foi o periodo?" a cada registro de acompanhamento. Fica
em campanha_performance.ocorrencias_relevantes, uma entrada
por EPS, por dia e por origem (EPS ou EduNova).

Quem ve o que:
- EPS: o diario da propria EPS naquela campanha, incluindo o
  que a EduNova registrou para ela.
- Planejamento, Comercial e Admin: o diario de todas as EPS,
  no detalhe da campanha e no historico.

Copys: a forma de atuacao, a copy de WhatsApp e a imagem que
cada EPS registrou (campanha_eps_atuacao). No historico vai so
o texto e a indicacao de que existe imagem; a imagem em si e
carregada sob demanda, porque pesa.
"""

from app.db import (
    DATABASE,
    get_connection,
)


def _linhas(cursor):
    nomes = [item[0] for item in cursor.description]
    return [dict(zip(nomes, linha)) for linha in cursor.fetchall()]


def _texto(valor):
    return str(valor or "").strip()


def _em_lista(campaign_uuids):
    marcadores = ", ".join(["?"] * len(campaign_uuids))
    return f"campaign_uuid IN ({marcadores})", list(campaign_uuids)


# ============================================================
# DIARIO
# ============================================================

def diario_linhas(cursor, campaign_uuids, eps=None):
    if not campaign_uuids:
        return []

    filtro, parametros = _em_lista(campaign_uuids)

    if eps:
        filtro += " AND upper(eps) = ?"
        parametros.append(str(eps).strip().upper())

    cursor.execute(
        f"""
        SELECT
            campaign_uuid, eps, data_referencia, origem,
            ocorrencias_relevantes, resultado_periodo,
            tentativas_disparos, contatos_alo, produtivos,
            carregado_por, dt_carga
        FROM {DATABASE}.campanha_performance
        WHERE {filtro}
        """,
        parameters=parametros,
    )

    entradas = []

    for linha in _linhas(cursor):
        texto = _texto(linha.get("ocorrencias_relevantes"))
        resultado = _texto(linha.get("resultado_periodo"))

        if resultado and resultado != texto:
            texto = f"{texto}\n{resultado}".strip()

        if not texto:
            continue

        origem = (
            "EDUNOVA"
            if _texto(linha.get("origem")).upper() == "COMERCIAL"
            else "EPS"
        )

        entradas.append({
            "campaign_uuid": linha["campaign_uuid"],
            "eps": _texto(linha.get("eps")).upper(),
            "data": str(linha.get("data_referencia") or "")[:10],
            "origem": origem,
            "texto": texto,
            "autor": linha.get("carregado_por"),
            "registrado_em": str(linha.get("dt_carga") or "")[:16],
            "tentativas": linha.get("tentativas_disparos"),
            "alo": linha.get("contatos_alo"),
        })

    entradas.sort(
        key=lambda item: (item["data"], item["registrado_em"]),
        reverse=True,
    )

    return entradas


def _campaign_uuid(cursor, codigo_campanha):
    cursor.execute(
        f"""
        SELECT campaign_uuid
        FROM {DATABASE}.campanha_master
        WHERE upper(codigo_campanha) = upper(?)
        LIMIT 1
        """,
        parameters=[codigo_campanha],
    )
    linha = cursor.fetchone()

    if not linha:
        raise ValueError("Campanha não encontrada.")

    return linha[0]


def _sem_uuid(entradas):
    for item in entradas:
        item.pop("campaign_uuid", None)
    return entradas


def diario_interno(codigo_campanha):
    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            campaign_uuid = _campaign_uuid(cursor, codigo_campanha)
            return {"entradas": _sem_uuid(diario_linhas(cursor, [campaign_uuid]))}
        finally:
            cursor.close()


def diario_eps(email_usuario, codigo_campanha):
    # Import aqui para nao criar dependencia circular na subida.
    from app.external_service import obter_usuario_eps_aprovado

    usuario = obter_usuario_eps_aprovado(email_usuario)
    eps = usuario["eps"]

    with get_connection() as conexao:
        cursor = conexao.cursor()
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
                parameters=[codigo_campanha, eps],
            )
            linha = cursor.fetchone()

            if not linha:
                raise PermissionError("Campanha não disponível para a sua EPS.")

            return {
                "eps": eps,
                "entradas": _sem_uuid(diario_linhas(cursor, [linha[0]], eps)),
            }
        finally:
            cursor.close()


# ============================================================
# HISTORICO: DIARIO E COPYS POR CAMPANHA
# ============================================================

def anexar_historico_dashboard(dados):
    campanhas = dados.get("campanhas") or []

    if not campanhas:
        return dados

    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            cursor.execute(
                f"""
                SELECT codigo_campanha, campaign_uuid
                FROM {DATABASE}.campanha_master
                """
            )
            mapa = {
                str(linha[0]).upper(): linha[1]
                for linha in cursor.fetchall()
            }
            uuids = list(mapa.values())

            diario = diario_linhas(cursor, uuids)

            try:
                cursor.execute(
                    f"""
                    SELECT
                        campaign_uuid, eps, canais, copy_whatsapp,
                        imagem_nome, imagem_tipo,
                        CASE WHEN imagem_base64 IS NULL THEN 0 ELSE 1 END AS tem_imagem,
                        atualizado_por, dt_atualizacao
                    FROM {DATABASE}.campanha_eps_atuacao
                    """
                )
                atuacoes = _linhas(cursor)
            except Exception as erro:
                print("[historico] atuacao indisponivel:", erro)
                atuacoes = []

        finally:
            cursor.close()

    diario_por_campanha = {}
    for item in diario:
        diario_por_campanha.setdefault(item.pop("campaign_uuid"), []).append(item)

    copys_por_campanha = {}
    for item in atuacoes:
        copys_por_campanha.setdefault(item["campaign_uuid"], []).append({
            "eps": _texto(item.get("eps")).upper(),
            "canais": [c for c in _texto(item.get("canais")).split(",") if c],
            "copy_whatsapp": item.get("copy_whatsapp"),
            "tem_imagem": bool(item.get("tem_imagem")),
            "imagem_nome": item.get("imagem_nome"),
            "atualizado_por": item.get("atualizado_por"),
            "dt_atualizacao": str(item.get("dt_atualizacao") or "")[:16],
        })

    for campanha in campanhas:
        campaign_uuid = mapa.get(str(campanha.get("codigo_campanha")).upper())
        campanha["diario"] = diario_por_campanha.get(campaign_uuid, [])
        campanha["copys"] = copys_por_campanha.get(campaign_uuid, [])

    return dados


# ============================================================
# COPY PREENCHIDA PELO TIME INTERNO
#
# O Comercial pode registrar ou corrigir canais e copy de uma
# EPS a qualquer momento, inclusive com a campanha em
# execucao. Mesma tabela e mesmas regras da tela da EPS
# (canais validos, copy so com WhatsApp, imagem ate 1,5 MB).
# ============================================================

def salvar_atuacao_interna(codigo_campanha, eps, payload, usuario_email):
    from datetime import datetime, timezone
    from app.atuacao_service import _normalizar_canais, _validar_imagem

    eps = str(eps or "").strip().upper()

    if not eps:
        raise ValueError("Informe a EPS.")

    canais = _normalizar_canais(payload.get("canais"))
    atua_whatsapp = "WHATSAPP" in canais or "TODOS" in canais

    copy_whatsapp = None
    imagem = (None, None, None)

    if atua_whatsapp:
        copy_whatsapp = str(payload.get("copy_whatsapp") or "").strip() or None
        imagem = _validar_imagem(payload)

    manter_imagem = bool(payload.get("manter_imagem"))
    agora = datetime.now(timezone.utc)

    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            cursor.execute(
                f"""
                SELECT m.campaign_uuid
                FROM {DATABASE}.campanha_master m
                INNER JOIN {DATABASE}.campanha_eps ce
                    ON ce.campaign_uuid = m.campaign_uuid
                WHERE upper(m.codigo_campanha) = upper(?)
                  AND upper(ce.eps) = ?
                LIMIT 1
                """,
                parameters=[codigo_campanha, eps],
            )
            linha = cursor.fetchone()

            if not linha:
                raise ValueError(f"A EPS {eps} não está vinculada a esta campanha.")

            campaign_uuid = linha[0]

            cursor.execute(
                f"""
                SELECT imagem_base64, imagem_nome, imagem_tipo
                FROM {DATABASE}.campanha_eps_atuacao
                WHERE campaign_uuid = ? AND upper(eps) = ?
                LIMIT 1
                """,
                parameters=[campaign_uuid, eps],
            )
            anterior = cursor.fetchone()

            if imagem[0] is None and manter_imagem and anterior and atua_whatsapp:
                imagem = (anterior[0], anterior[1], anterior[2])

            valores = [
                ",".join(canais) or None, copy_whatsapp,
                imagem[0], imagem[1], imagem[2],
                usuario_email, agora,
            ]

            if anterior is not None:
                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.campanha_eps_atuacao
                    SET canais = ?, copy_whatsapp = ?, imagem_base64 = ?,
                        imagem_nome = ?, imagem_tipo = ?,
                        atualizado_por = ?, dt_atualizacao = ?
                    WHERE campaign_uuid = ? AND upper(eps) = ?
                    """,
                    parameters=valores + [campaign_uuid, eps],
                )
            else:
                cursor.execute(
                    f"""
                    INSERT INTO {DATABASE}.campanha_eps_atuacao
                    (canais, copy_whatsapp, imagem_base64, imagem_nome,
                     imagem_tipo, atualizado_por, dt_atualizacao,
                     campaign_uuid, eps)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    parameters=valores + [campaign_uuid, eps],
                )

            import uuid as _uuid
            cursor.execute(
                f"""
                INSERT INTO {DATABASE}.campanha_historico
                (historico_uuid, campaign_uuid, data_hora, usuario, origem,
                 evento, campo_alterado, valor_anterior, valor_novo, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                parameters=[
                    str(_uuid.uuid4()), campaign_uuid, agora, usuario_email,
                    "COMERCIAL", "ATUALIZACAO_COPY_EPS", "copy_whatsapp", None,
                    (copy_whatsapp or "(sem copy)")[:900],
                    f"Canais e copy da EPS {eps} atualizados pelo time interno.",
                ],
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