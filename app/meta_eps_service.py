"""
META, REALIZADO E ATINGIMENTO POR EPS

Uma acao pode ter varias EPS. Cada uma tem a sua meta, o seu
realizado e o seu atingimento. O total da acao e sempre a
soma: meta total = soma das metas, realizado total = soma dos
realizados, atingimento total = realizado total / meta total.

A meta e opcional. Quando existe, o Planejamento escolhe a
base do atingimento: MATRICULAS ou VENDAS.

De onde vem o realizado de cada EPS, na ordem de confianca:

1. FUNIL_PLANEJAMENTO  funil apurado pelo Planejamento no
                       encerramento (campanha_funil_eps)
2. ENCERRAMENTO_EPS    numeros finais informados pela EPS ao
                       encerrar a atuacao
3. ACOMPANHAMENTO      soma dos registros diarios. Quando o
                       mesmo dia tem registro da EPS e do time
                       interno, vale o interno, para nao contar
                       o mesmo dia duas vezes.

Todas as telas (portal EPS, detalhe interno e historico) usam
estas funcoes, para o mesmo numero aparecer igual em todo lugar.
"""

import uuid

from datetime import datetime, timezone

from app.db import (
    DATABASE,
    get_connection,
)


BASES_META = ["MATRICULAS", "VENDAS"]

CAMPOS_FUNIL = [
    "mailing",
    "trabalhado",
    "tentativas",
    "alo",
    "efetivos",
    "vendas",
    "matriculas",
]

# Nome no payload do encerramento -> chave do funil.
CAMPOS_PAYLOAD_FUNIL = {
    "mailing": "mailing",
    "mailing_trabalhado": "trabalhado",
    "tentativas": "tentativas",
    "alo": "alo",
    "efetivos": "efetivos",
    "vendas": "vendas",
    "matriculas": "matriculas",
}


def _agora():
    return datetime.now(timezone.utc)


def _linhas(cursor):
    nomes = [item[0] for item in cursor.description]
    return [dict(zip(nomes, linha)) for linha in cursor.fetchall()]


def _int(valor):
    if valor in (None, ""):
        return 0
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _numero_ou_none(valor, campo):
    if valor in (None, ""):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"{campo} precisa ser um número.") from erro
    if numero < 0:
        raise ValueError(f"{campo} não pode ser negativo.")
    return numero


def _funil_vazio():
    return {campo: 0 for campo in CAMPOS_FUNIL}


def _em_lista(campaign_uuids):
    """Trecho 'IN (?, ?, ...)' e parametros; vazio se None."""
    if not campaign_uuids:
        return "", []
    marcadores = ", ".join(["?"] * len(campaign_uuids))
    return f"WHERE campaign_uuid IN ({marcadores})", list(campaign_uuids)


# ============================================================
# REALIZADO POR EPS
# ============================================================

def realizado_por_eps(cursor, campaign_uuids=None):
    """
    Devolve {(campaign_uuid, EPS): {"realizado": {...}, "fonte": str}}
    para todas as combinacoes com algum numero registrado.
    """
    filtro, parametros = _em_lista(campaign_uuids)
    resultado = {}

    # 3. Acompanhamento diario (fonte mais fraca: entra primeiro
    #    e e sobrescrita pelas fontes mais fortes).
    cursor.execute(
        f"""
        SELECT
            campaign_uuid, eps, data_referencia, origem,
            mailing_recebido, mailing_trabalhado,
            tentativas_disparos, contatos_alo, produtivos,
            vendas, matriculas
        FROM {DATABASE}.campanha_performance
        {filtro}
        """,
        parameters=parametros,
    )

    por_dia = {}

    for linha in _linhas(cursor):
        eps = str(linha.get("eps") or "").strip().upper()
        if not eps:
            continue

        chave_dia = (linha["campaign_uuid"], eps, str(linha["data_referencia"]))
        interno = str(linha.get("origem") or "").upper() == "COMERCIAL"

        atual = por_dia.get(chave_dia)
        if atual is None or (interno and not atual[0]):
            por_dia[chave_dia] = (interno, linha)

    for (campaign_uuid, eps, _), (_, linha) in por_dia.items():
        item = resultado.setdefault(
            (campaign_uuid, eps),
            {"realizado": _funil_vazio(), "fonte": "ACOMPANHAMENTO"},
        )
        r = item["realizado"]
        r["mailing"] += _int(linha["mailing_recebido"])
        r["trabalhado"] += _int(linha["mailing_trabalhado"])
        r["tentativas"] += _int(linha["tentativas_disparos"])
        r["alo"] += _int(linha["contatos_alo"])
        r["efetivos"] += _int(linha["produtivos"])
        r["vendas"] += _int(linha["vendas"])
        r["matriculas"] += _int(linha["matriculas"])

    # 2. Encerramento da EPS.
    try:
        cursor.execute(
            f"""
            SELECT
                campaign_uuid, eps,
                mailing_final, mailing_trabalhado_final,
                tentativas_disparos_final, contatos_final,
                vendas_final, matriculas_final
            FROM {DATABASE}.campanha_encerramento_eps
            {filtro}
            """,
            parameters=parametros,
        )
        encerramentos = _linhas(cursor)
    except Exception as erro:
        print("[meta_eps] encerramento EPS indisponivel:", erro)
        encerramentos = []

    for linha in encerramentos:
        eps = str(linha.get("eps") or "").strip().upper()
        if not eps:
            continue

        numeros = {
            "mailing": linha["mailing_final"],
            "trabalhado": linha["mailing_trabalhado_final"],
            "tentativas": linha["tentativas_disparos_final"],
            "alo": linha["contatos_final"],
            "vendas": linha["vendas_final"],
            "matriculas": linha["matriculas_final"],
        }

        if all(valor in (None, "") for valor in numeros.values()):
            continue

        anterior = resultado.get((linha["campaign_uuid"], eps))
        realizado = _funil_vazio()

        # Efetivos nao existe no encerramento da EPS: aproveita o
        # que veio do acompanhamento, se houver.
        if anterior:
            realizado["efetivos"] = anterior["realizado"]["efetivos"]

        for campo, valor in numeros.items():
            realizado[campo] = _int(valor)

        resultado[(linha["campaign_uuid"], eps)] = {
            "realizado": realizado,
            "fonte": "ENCERRAMENTO_EPS",
        }

    # 1. Funil apurado pelo Planejamento (fonte oficial).
    try:
        cursor.execute(
            f"""
            SELECT
                campaign_uuid, eps, mailing, trabalhado,
                tentativas, alo, efetivos, vendas, matriculas
            FROM {DATABASE}.campanha_funil_eps
            {filtro}
            """,
            parameters=parametros,
        )
        funis = _linhas(cursor)
    except Exception as erro:
        print("[meta_eps] funil por EPS indisponivel:", erro)
        funis = []

    for linha in funis:
        eps = str(linha.get("eps") or "").strip().upper()
        if not eps:
            continue

        resultado[(linha["campaign_uuid"], eps)] = {
            "realizado": {campo: _int(linha.get(campo)) for campo in CAMPOS_FUNIL},
            "fonte": "FUNIL_PLANEJAMENTO",
        }

    return resultado


# ============================================================
# METAS DA CAMPANHA
# ============================================================

def _atingimento(realizado, meta):
    if not meta:
        return None
    return round(realizado / meta * 100, 1)


def montar_metas(meta_base, linhas_eps, realizados, campaign_uuid):
    """
    linhas_eps: lista de dicts com eps, meta_eps, mailing_previsto.
    realizados: saida de realizado_por_eps.
    """
    base = (meta_base or "").upper() or None
    chave_base = "matriculas" if base == "MATRICULAS" else "vendas"

    por_eps = []

    for linha in sorted(linhas_eps, key=lambda item: str(item.get("eps") or "")):
        eps = str(linha.get("eps") or "").strip().upper()
        info = realizados.get((campaign_uuid, eps))

        realizado = info["realizado"] if info else _funil_vazio()
        meta = linha.get("meta_eps")
        meta = float(meta) if meta not in (None, "") else None
        valor = realizado[chave_base] if base else None

        por_eps.append({
            "eps": eps,
            "meta": meta,
            "mailing_previsto": linha.get("mailing_previsto"),
            "observacao_planejamento": linha.get("observacao_planejamento"),
            "observacao_comercial": linha.get("observacao_comercial"),
            "realizado": realizado,
            "valor_realizado": valor,
            "atingimento": _atingimento(valor, meta) if base else None,
            "fonte": info["fonte"] if info else None,
        })

    metas_validas = [item["meta"] for item in por_eps if item["meta"]]
    meta_total = sum(metas_validas) if metas_validas else None

    # O realizado total so soma as EPS que tem meta: comparar o
    # resultado de todas com a meta de algumas distorceria o %.
    realizado_total = (
        sum(item["valor_realizado"] or 0 for item in por_eps if item["meta"])
        if base and meta_total
        else None
    )

    return {
        "base": base,
        "tem_meta": bool(base and meta_total),
        "por_eps": por_eps,
        "total": {
            "meta": meta_total,
            "realizado": realizado_total,
            "atingimento": (
                _atingimento(realizado_total, meta_total)
                if realizado_total is not None
                else None
            ),
        },
    }


def metas_da_campanha(cursor, campaign_uuid):
    cursor.execute(
        f"""
        SELECT meta_base
        FROM {DATABASE}.campanha_master
        WHERE campaign_uuid = ?
        LIMIT 1
        """,
        parameters=[campaign_uuid],
    )
    linha = cursor.fetchone()
    meta_base = linha[0] if linha else None

    cursor.execute(
        f"""
        SELECT eps, meta_eps, mailing_previsto,
               observacao_planejamento, observacao_comercial
        FROM {DATABASE}.campanha_eps
        WHERE campaign_uuid = ?
        """,
        parameters=[campaign_uuid],
    )
    linhas_eps = _linhas(cursor)

    return montar_metas(
        meta_base,
        linhas_eps,
        realizado_por_eps(cursor, [campaign_uuid]),
        campaign_uuid,
    )


# ============================================================
# EDITAR METAS (PLANEJAMENTO)
# ============================================================

def salvar_metas_eps(codigo_campanha, payload, usuario_email):
    """
    payload = {
        "meta_base": "MATRICULAS" | "VENDAS" | null,
        "metas":   {"VOXA": 300, "PRISMA": null, ...},
        "mailing": {"VOXA": 12000, ...}      (opcional)
    }
    Base vazia remove a meta da acao inteira.
    """
    base = (payload.get("meta_base") or "").strip().upper() or None

    if base and base not in BASES_META:
        raise ValueError("A base da meta precisa ser Matrículas ou Vendas.")

    metas = payload.get("metas") or {}
    mailing = payload.get("mailing") or {}

    metas_limpas = {
        str(eps).strip().upper(): _numero_ou_none(valor, f"Meta da {eps}")
        for eps, valor in metas.items()
    }

    if not base and any(valor for valor in metas_limpas.values()):
        raise ValueError("Escolha se a meta é de Matrículas ou de Vendas.")

    mailing_limpo = {}
    for eps, valor in mailing.items():
        numero = _numero_ou_none(valor, f"Mailing previsto da {eps}")
        mailing_limpo[str(eps).strip().upper()] = (
            int(numero) if numero is not None else None
        )

    agora = _agora()

    with get_connection() as conexao:
        cursor = conexao.cursor()

        try:
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

            campaign_uuid = linha[0]

            cursor.execute(
                f"""
                SELECT eps FROM {DATABASE}.campanha_eps
                WHERE campaign_uuid = ?
                """,
                parameters=[campaign_uuid],
            )
            eps_da_campanha = {
                str(item[0]).strip().upper() for item in cursor.fetchall()
            }

            for eps in list(metas_limpas) + list(mailing_limpo):
                if eps not in eps_da_campanha:
                    raise ValueError(f"A EPS {eps} não está vinculada a esta campanha.")

            cursor.execute(
                f"""
                UPDATE {DATABASE}.campanha_master
                SET meta_base = ?, dt_atualizacao = ?, atualizado_por = ?
                WHERE campaign_uuid = ?
                """,
                parameters=[base, agora, usuario_email, campaign_uuid],
            )

            for eps in eps_da_campanha:
                campos, valores = [], []

                if eps in metas_limpas or not base:
                    campos.append("meta_eps = ?")
                    valores.append(metas_limpas.get(eps) if base else None)

                if eps in mailing_limpo:
                    campos.append("mailing_previsto = ?")
                    valores.append(mailing_limpo[eps])

                if not campos:
                    continue

                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.campanha_eps
                    SET {", ".join(campos)}
                    WHERE campaign_uuid = ? AND upper(eps) = ?
                    """,
                    parameters=valores + [campaign_uuid, eps],
                )

            resumo = "; ".join(
                f"{eps}: {valor:g}" for eps, valor in metas_limpas.items() if valor
            ) or "sem meta"

            cursor.execute(
                f"""
                INSERT INTO {DATABASE}.campanha_historico
                (historico_uuid, campaign_uuid, data_hora, usuario, origem,
                 evento, campo_alterado, valor_anterior, valor_novo, observacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                parameters=[
                    str(uuid.uuid4()), campaign_uuid, agora, usuario_email,
                    "PLANEJAMENTO", "ATUALIZACAO_METAS_EPS", "meta_eps", None,
                    resumo[:900],
                    f"Metas por EPS atualizadas (base: {base or 'sem meta'}).",
                ],
            )

            return metas_da_campanha(cursor, campaign_uuid)

        finally:
            cursor.close()


# ============================================================
# FUNIL DO ENCERRAMENTO POR EPS
# ============================================================

def salvar_funil_por_eps(cursor, campaign_uuid, funil_eps, usuario_email):
    """
    funil_eps = {"VOXA": {"mailing": 100, "vendas": 10, ...}, ...}
    Grava uma linha por EPS (substitui a anterior) e devolve a
    soma, que e o funil consolidado da acao.
    """
    cursor.execute(
        f"""
        SELECT eps FROM {DATABASE}.campanha_eps
        WHERE campaign_uuid = ?
        """,
        parameters=[campaign_uuid],
    )
    eps_da_campanha = {str(item[0]).strip().upper() for item in cursor.fetchall()}

    total = _funil_vazio()
    preenchidos = set()
    agora = _agora()

    for eps_bruto, numeros in (funil_eps or {}).items():
        eps = str(eps_bruto).strip().upper()

        if eps not in eps_da_campanha:
            raise ValueError(f"A EPS {eps} não está vinculada a esta campanha.")

        linha = {}
        for campo_payload, campo in CAMPOS_PAYLOAD_FUNIL.items():
            bruto = (numeros or {}).get(campo_payload)
            if bruto in (None, ""):
                continue
            try:
                numero = int(bruto)
            except (TypeError, ValueError) as erro:
                raise ValueError(
                    f"{eps}: o campo {campo_payload} precisa ser um número inteiro."
                ) from erro
            if numero < 0:
                raise ValueError(f"{eps}: o campo {campo_payload} não pode ser negativo.")
            linha[campo] = numero

        if not linha:
            continue

        preenchidos.update(linha.keys())

        cursor.execute(
            f"""
            DELETE FROM {DATABASE}.campanha_funil_eps
            WHERE campaign_uuid = ? AND eps = ?
            """,
            parameters=[campaign_uuid, eps],
        )

        colunas = ["funil_eps_uuid", "campaign_uuid", "eps"] + CAMPOS_FUNIL + [
            "dt_atualizacao", "atualizado_por",
        ]
        valores = [str(uuid.uuid4()), campaign_uuid, eps] + [
            linha.get(campo) for campo in CAMPOS_FUNIL
        ] + [agora, usuario_email]

        cursor.execute(
            f"""
            INSERT INTO {DATABASE}.campanha_funil_eps
            ({", ".join(colunas)})
            VALUES ({", ".join(["?"] * len(colunas))})
            """,
            parameters=valores,
        )

        for campo in CAMPOS_FUNIL:
            total[campo] += linha.get(campo) or 0

    # Campo que nenhuma EPS informou fica None, e nao zero:
    # zero seria uma informacao falsa no consolidado.
    if not preenchidos:
        return None

    return {
        campo: (total[campo] if campo in preenchidos else None)
        for campo in CAMPOS_FUNIL
    }


# ============================================================
# COMPLEMENTOS DAS TELAS
#
# Aplicados nas rotas do main.py sobre o que os services ja
# devolvem. Assim os services que ja funcionam nao mudam.
# ============================================================

def _mapa_campanhas(cursor, codigos=None):
    """{codigo_campanha: (campaign_uuid, meta_base)}"""
    if codigos:
        marcadores = ", ".join(["?"] * len(codigos))
        filtro = f"WHERE upper(codigo_campanha) IN ({marcadores})"
        parametros = [str(c).upper() for c in codigos]
    else:
        filtro, parametros = "", []

    cursor.execute(
        f"""
        SELECT codigo_campanha, campaign_uuid, meta_base
        FROM {DATABASE}.campanha_master
        {filtro}
        """,
        parameters=parametros,
    )
    return {
        str(linha[0]).upper(): (linha[1], linha[2])
        for linha in cursor.fetchall()
    }


def _linhas_eps(cursor, campaign_uuids):
    filtro, parametros = _em_lista(campaign_uuids)
    cursor.execute(
        f"""
        SELECT campaign_uuid, eps, meta_eps, mailing_previsto
        FROM {DATABASE}.campanha_eps
        {filtro}
        """,
        parameters=parametros,
    )
    por_campanha = {}
    for linha in _linhas(cursor):
        por_campanha.setdefault(linha["campaign_uuid"], []).append(linha)
    return por_campanha


def _meta_de_uma_eps(metas, eps):
    """Recorte que a EPS pode ver: so a propria meta."""
    eps = str(eps or "").strip().upper()
    item = next((x for x in metas["por_eps"] if x["eps"] == eps), None)

    if not item or not metas["base"] or not item["meta"]:
        return None

    return {
        "base": metas["base"],
        "meta": item["meta"],
        "realizado": item["valor_realizado"] or 0,
        "atingimento": item["atingimento"],
        "fonte": item["fonte"],
    }


def enriquecer_lista_eps(resultado):
    """Portal EPS, lista: acrescenta a meta da EPS em cada campanha."""
    campanhas = resultado.get("campanhas") or []
    eps = (resultado.get("usuario") or {}).get("eps")

    if not campanhas or not eps:
        return resultado

    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            mapa = _mapa_campanhas(cursor, [c["codigo_campanha"] for c in campanhas])
            uuids = [valor[0] for valor in mapa.values()]
            linhas = _linhas_eps(cursor, uuids)
            realizados = realizado_por_eps(cursor, uuids)
        finally:
            cursor.close()

    for campanha in campanhas:
        campaign_uuid, meta_base = mapa.get(
            str(campanha["codigo_campanha"]).upper(), (None, None)
        )
        if not campaign_uuid:
            continue
        metas = montar_metas(meta_base, linhas.get(campaign_uuid, []), realizados, campaign_uuid)
        campanha["meta_eps"] = _meta_de_uma_eps(metas, eps)

    return resultado


def enriquecer_detalhe_eps(resultado):
    """
    Portal EPS, detalhe: acrescenta a meta da EPS e retira a
    meta total dos KPIs quando a acao tem mais de uma EPS — a
    EPS so enxerga o que e dela.
    """
    campanha = resultado.get("campanha") or {}
    eps = (resultado.get("usuario") or {}).get("eps")

    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            mapa = _mapa_campanhas(cursor, [campanha.get("codigo_campanha")])
            campaign_uuid, _ = mapa.get(
                str(campanha.get("codigo_campanha")).upper(), (None, None)
            )
            if not campaign_uuid:
                return resultado
            metas = metas_da_campanha(cursor, campaign_uuid)
        finally:
            cursor.close()

    campanha["meta_eps"] = _meta_de_uma_eps(metas, eps)

    propria = next(
        (item for item in metas["por_eps"]
         if item["eps"] == str(eps or "").strip().upper()),
        None,
    )
    campanha["orientacoes_eps"] = {
        "planejamento": (propria or {}).get("observacao_planejamento"),
        "comercial": (propria or {}).get("observacao_comercial"),
    }

    if len(metas["por_eps"]) > 1:
        for kpi in campanha.get("kpis") or []:
            kpi["meta_valor"] = None
            kpi["meta_descricao"] = None

    return resultado


def metas_por_codigo(codigo_campanha):
    """Portal interno, detalhe: metas de todas as EPS + total."""
    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            mapa = _mapa_campanhas(cursor, [codigo_campanha])
            campaign_uuid, _ = mapa.get(str(codigo_campanha).upper(), (None, None))
            if not campaign_uuid:
                raise ValueError("Campanha não encontrada.")
            return metas_da_campanha(cursor, campaign_uuid)
        finally:
            cursor.close()


def enriquecer_dashboard(dados):
    """
    Historico: acrescenta, em cada campanha, a meta e o
    realizado de cada EPS. Quando o Planejamento apurou o
    funil por EPS, o realizado da campanha passa a ser a soma
    desses funis (e o consolidado oficial).
    """
    campanhas = dados.get("campanhas") or []

    if not campanhas:
        return dados

    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            mapa = _mapa_campanhas(cursor)
            uuids = [valor[0] for valor in mapa.values()]
            linhas = _linhas_eps(cursor, uuids)
            realizados = realizado_por_eps(cursor, uuids)
        finally:
            cursor.close()

    for campanha in campanhas:
        campaign_uuid, meta_base = mapa.get(
            str(campanha.get("codigo_campanha")).upper(), (None, None)
        )

        if not campaign_uuid:
            campanha["metas"] = None
            campanha["por_eps"] = {}
            continue

        metas = montar_metas(meta_base, linhas.get(campaign_uuid, []), realizados, campaign_uuid)
        campanha["metas"] = {
            "base": metas["base"],
            "tem_meta": metas["tem_meta"],
            "total": metas["total"],
        }
        campanha["por_eps"] = {
            item["eps"]: {
                "realizado": item["realizado"],
                "meta": item["meta"],
                "valor_realizado": item["valor_realizado"],
                "atingimento": item["atingimento"],
                "fonte": item["fonte"],
            }
            for item in metas["por_eps"]
        }

        apurados = [
            item for item in metas["por_eps"]
            if item["fonte"] == "FUNIL_PLANEJAMENTO"
        ]

        if apurados:
            soma = _funil_vazio()
            for item in metas["por_eps"]:
                for campo in CAMPOS_FUNIL:
                    soma[campo] += item["realizado"][campo]
            campanha["realizado"] = soma

    return dados


def consolidar_funil_encerramento(codigo_campanha, payload, usuario_email):
    """
    Encerramento: grava o funil de cada EPS e troca os campos
    consolidados do payload pela soma deles. O resto do
    encerramento segue igual, gravando o consolidado.
    """
    funil_eps = payload.get("funil_eps")

    if not funil_eps:
        return payload

    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            mapa = _mapa_campanhas(cursor, [codigo_campanha])
            campaign_uuid, _ = mapa.get(str(codigo_campanha).upper(), (None, None))
            if not campaign_uuid:
                raise ValueError("Campanha não encontrada.")
            total = salvar_funil_por_eps(cursor, campaign_uuid, funil_eps, usuario_email)
        finally:
            cursor.close()

    if total:
        payload = dict(payload)
        for campo_payload, campo in CAMPOS_PAYLOAD_FUNIL.items():
            payload[campo_payload] = total[campo]

    return payload


# ============================================================
# OBSERVACOES POR EPS
#
# Cada EPS recebe orientacoes proprias — por exemplo, faixas
# de incentivo diferentes. Duas origens, cada uma com o seu
# campo: o Planejamento (no cadastro ou no detalhe) e o
# Comercial (na liberacao para a EPS). A EPS le so as dela.
# ============================================================

COLUNA_OBSERVACAO = {
    "PLANEJAMENTO": "observacao_planejamento",
    "COMERCIAL": "observacao_comercial",
}

LIMITE_OBSERVACAO = 4000


def salvar_observacoes_eps(codigo_campanha, tipo, observacoes, usuario_email):
    """observacoes = {"VOXA": "texto", "LUMEN": ""}; vazio apaga."""
    tipo = str(tipo or "").strip().upper()
    coluna = COLUNA_OBSERVACAO.get(tipo)

    if not coluna:
        raise ValueError("Tipo de observação inválido.")

    limpas = {}

    for eps, texto in (observacoes or {}).items():
        texto = str(texto or "").strip()

        if len(texto) > LIMITE_OBSERVACAO:
            raise ValueError(
                f"A observação da {eps} passa de {LIMITE_OBSERVACAO} caracteres."
            )

        limpas[str(eps).strip().upper()] = texto or None

    if not limpas:
        return {"atualizadas": []}

    agora = _agora()

    with get_connection() as conexao:
        cursor = conexao.cursor()

        try:
            mapa = _mapa_campanhas(cursor, [codigo_campanha])
            campaign_uuid, _ = mapa.get(str(codigo_campanha).upper(), (None, None))

            if not campaign_uuid:
                raise ValueError("Campanha não encontrada.")

            cursor.execute(
                f"""
                SELECT eps FROM {DATABASE}.campanha_eps
                WHERE campaign_uuid = ?
                """,
                parameters=[campaign_uuid],
            )
            eps_da_campanha = {
                str(item[0]).strip().upper() for item in cursor.fetchall()
            }

            for eps, texto in limpas.items():
                if eps not in eps_da_campanha:
                    raise ValueError(f"A EPS {eps} não está vinculada a esta campanha.")

                cursor.execute(
                    f"""
                    UPDATE {DATABASE}.campanha_eps
                    SET {coluna} = ?
                    WHERE campaign_uuid = ? AND upper(eps) = ?
                    """,
                    parameters=[texto, campaign_uuid, eps],
                )

                cursor.execute(
                    f"""
                    INSERT INTO {DATABASE}.campanha_historico
                    (historico_uuid, campaign_uuid, data_hora, usuario, origem,
                     evento, campo_alterado, valor_anterior, valor_novo, observacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    parameters=[
                        str(uuid.uuid4()), campaign_uuid, agora, usuario_email,
                        tipo, f"OBSERVACAO_{tipo}_EPS", coluna, None,
                        (texto or "(removida)")[:900],
                        f"Observação do {tipo.capitalize()} para a EPS {eps} atualizada.",
                    ],
                )

            return {"atualizadas": list(limpas.keys())}

        finally:
            cursor.close()