"""
ACOMPANHAMENTO INTERNO DA CAMPANHA

Permite que Comercial e Planejamento registrem o andamento
diário de uma campanha que está com as EPS.

Por que existe um módulo separado:

O acompanhamento da EPS é identificado pelo e-mail do
fornecedor e passa pela validação de vínculo com a EPS. Aqui
quem registra é usuário interno, já autenticado pelo perfil,
e pode escolher para qual EPS está lançando. São regras
diferentes o suficiente para não caberem na mesma função.

Os dois lados gravam na mesma tabela, separados pela coluna
`origem` — assim o histórico mostra de onde veio cada número
em vez de um sobrescrever o outro.
"""

import uuid

from datetime import datetime, timezone

from app.db import (
    DATABASE,
    get_connection,
)


ORIGEM_INTERNA = "COMERCIAL"


def _agora_utc():
    return datetime.now(
        timezone.utc
    )


def _novo_uuid():
    return str(
        uuid.uuid4()
    )


# ============================================================
# REGISTRAR ACOMPANHAMENTO INTERNO
# ============================================================

def registrar_acompanhamento_interno(
    codigo_campanha: str,
    payload: dict,
    usuario_email: str,
):
    """
    Grava ou atualiza o acompanhamento de um dia.

    Todos os campos numéricos são opcionais: o Comercial
    preenche o que tiver. O único obrigatório é a data, que
    identifica o registro.
    """

    data_referencia = (
        payload.get("data_referencia")
        or ""
    ).strip()

    if not data_referencia:
        raise ValueError(
            "Informe a data do acompanhamento."
        )

    eps_alvo = (
        payload.get("eps")
        or ""
    ).strip().upper()

    if not eps_alvo:
        raise ValueError(
            "Selecione a EPS a que este "
            "acompanhamento se refere."
        )

    agora = _agora_utc()

    # Campos que o Comercial pode informar. Ficam de fora os
    # percentuais: são calculados a partir destes, e guardar
    # os dois abriria espaço para número inconsistente.
    campos_numericos = [
        "mailing_recebido",
        "mailing_trabalhado",
        "tentativas_disparos",
        "contatos_alo",
        "produtivos",
        "interessados",
        "vendas",
        "matriculas",
    ]

    campos_texto = [
        "resultado_periodo",
        "ocorrencias_relevantes",
    ]

    valores = {}

    for campo in campos_numericos:

        bruto = payload.get(campo)

        if bruto in (None, ""):
            continue

        try:
            numero = int(bruto)

        except (TypeError, ValueError) as erro:
            raise ValueError(
                f"O campo {campo} precisa ser "
                "um número inteiro."
            ) from erro

        if numero < 0:
            raise ValueError(
                f"O campo {campo} não pode "
                "ser negativo."
            )

        valores[campo] = numero

    for campo in campos_texto:

        bruto = payload.get(campo)

        if bruto:
            valores[campo] = str(bruto).strip()

    if not valores:
        raise ValueError(
            "Informe ao menos um número ou "
            "uma observação."
        )

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            # --------------------------------------------
            # 1. CAMPANHA E VÍNCULO COM A EPS
            # --------------------------------------------

            cursor.execute(
                f"""
                SELECT
                    m.campaign_uuid,
                    m.nome_campanha,
                    m.status_campanha

                FROM {DATABASE}.campanha_master m

                WHERE upper(m.codigo_campanha) =
                      upper(?)

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ]
            )

            campanha = cursor.fetchone()

            if not campanha:
                raise ValueError(
                    "Campanha não encontrada."
                )

            campaign_uuid = campanha[0]
            nome_campanha = campanha[1]

            cursor.execute(
                f"""
                SELECT
                    campanha_eps_uuid

                FROM {DATABASE}.campanha_eps

                WHERE campaign_uuid = ?
                  AND upper(eps) = upper(?)
                  AND liberada_para_eps = TRUE

                LIMIT 1
                """,
                parameters=[
                    campaign_uuid,
                    eps_alvo
                ]
            )

            if not cursor.fetchone():
                raise ValueError(
                    f"A EPS {eps_alvo} não está "
                    "liberada nesta campanha."
                )

            # --------------------------------------------
            # 2. JÁ EXISTE REGISTRO INTERNO NESSE DIA?
            #
            # A busca inclui a origem: o registro da EPS
            # para o mesmo dia é outro, e não pode ser
            # sobrescrito por este.
            # --------------------------------------------

            cursor.execute(
                f"""
                SELECT
                    performance_uuid

                FROM {DATABASE}.campanha_performance

                WHERE campaign_uuid = ?
                  AND upper(eps) = upper(?)
                  AND data_referencia = ?
                  AND origem = ?

                LIMIT 1
                """,
                parameters=[
                    campaign_uuid,
                    eps_alvo,
                    data_referencia,
                    ORIGEM_INTERNA
                ]
            )

            existente = cursor.fetchone()

            if existente:

                campos_update = []
                valores_update = []

                for campo, valor in valores.items():
                    campos_update.append(
                        f"{campo} = ?"
                    )
                    valores_update.append(valor)

                campos_update.extend(
                    [
                        "dt_carga = ?",
                        "carregado_por = ?"
                    ]
                )

                valores_update.extend(
                    [
                        agora,
                        usuario_email
                    ]
                )

                valores_update.append(
                    existente[0]
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

                acao = "ATUALIZADO"

            else:

                linha = {
                    "performance_uuid":
                        _novo_uuid(),

                    "campaign_uuid":
                        campaign_uuid,

                    "eps":
                        eps_alvo,

                    "data_referencia":
                        data_referencia,

                    "origem":
                        ORIGEM_INTERNA,

                    **valores,

                    "dt_carga":
                        agora,

                    "carregado_por":
                        usuario_email
                }

                colunas = list(linha.keys())

                marcadores = ", ".join(
                    ["?"] * len(colunas)
                )

                cursor.execute(
                    f"""
                    INSERT INTO
                        {DATABASE}.campanha_performance
                    (
                        {", ".join(colunas)}
                    )
                    VALUES
                    (
                        {marcadores}
                    )
                    """,
                    parameters=[
                        linha[coluna]
                        for coluna in colunas
                    ]
                )

                acao = "CRIADO"

            # --------------------------------------------
            # 3. HISTÓRICO
            #
            # Registrar quem informou importa: na apuração
            # final o Planejamento precisa saber se o número
            # veio do fornecedor ou de dentro de casa.
            # --------------------------------------------

            resumo = ", ".join(
                f"{campo}={valor}"
                for campo, valor in valores.items()
            )

            cursor.execute(
                f"""
                INSERT INTO {DATABASE}.campanha_historico
                (
                    historico_uuid,
                    campaign_uuid,
                    data_hora,
                    usuario,
                    origem,
                    evento,
                    campo_alterado,
                    valor_anterior,
                    valor_novo,
                    observacao
                )
                VALUES
                (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                parameters=[
                    _novo_uuid(),
                    campaign_uuid,
                    agora,
                    usuario_email,
                    "INTERNO",
                    "ACOMPANHAMENTO_INTERNO",
                    "campanha_performance",
                    None,
                    resumo[:900],
                    (
                        f"Acompanhamento de {data_referencia} "
                        f"{acao.lower()} pelo time interno "
                        f"para a EPS {eps_alvo}."
                    )
                ]
            )

            return {
                "codigo_campanha":
                    codigo_campanha.upper(),

                "nome_campanha":
                    nome_campanha,

                "eps":
                    eps_alvo,

                "data_referencia":
                    data_referencia,

                "origem":
                    ORIGEM_INTERNA,

                "acao":
                    acao,

                "campos_informados":
                    list(valores.keys()),

                "registrado_por":
                    usuario_email
            }

        finally:
            cursor.close()


# ============================================================
# FUNIL DO ENCERRAMENTO
#
# Preenchido pelo Planejamento no fechamento da campanha.
# Tudo opcional: nem toda acao tem funil, e algumas param na
# venda sem chegar a matricula.
#
# Roda depois de encerrar_campanha_edunova, complementando a
# linha que aquela funcao acabou de criar. Foi feito assim
# para nao alterar a funcao de encerramento, que ja funciona
# e e usada pela VM.
# ============================================================

CLASSIFICACOES = [
    "SUCESSO",
    "OPORTUNIDADE_MELHORIA",
    "SEM_SUCESSO",
]


def salvar_funil_encerramento(
    codigo_campanha: str,
    payload: dict,
    usuario_email: str,
):

    campos_funil = [
        "mailing",
        "mailing_trabalhado",
        "tentativas",
        "alo",
        "efetivos",
        "vendas",
        "matriculas",
    ]

    valores = {}

    for campo in campos_funil:

        bruto = payload.get(campo)

        if bruto in (None, ""):
            continue

        try:
            numero = int(bruto)

        except (TypeError, ValueError) as erro:
            raise ValueError(
                f"O campo {campo} precisa ser "
                "um número inteiro."
            ) from erro

        if numero < 0:
            raise ValueError(
                f"O campo {campo} não pode "
                "ser negativo."
            )

        valores[campo] = numero

    classificacao = (
        payload.get("classificacao_resultado")
        or ""
    ).strip().upper()

    if classificacao:

        if classificacao not in CLASSIFICACOES:
            raise ValueError(
                "Classificação inválida."
            )

        valores["classificacao_resultado"] = (
            classificacao
        )

    analise = (
        payload.get("analise_resultado")
        or ""
    ).strip()

    if analise:
        valores["analise_resultado"] = analise

    # Nada informado: o encerramento continua valendo, o
    # funil simplesmente nao existe para esta campanha.
    if not valores:
        return {
            "funil_registrado": False
        }

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                f"""
                SELECT
                    campaign_uuid

                FROM {DATABASE}.campanha_master

                WHERE upper(codigo_campanha) =
                      upper(?)

                LIMIT 1
                """,
                parameters=[
                    codigo_campanha
                ]
            )

            campanha = cursor.fetchone()

            if not campanha:
                raise ValueError(
                    "Campanha não encontrada."
                )

            campaign_uuid = campanha[0]

            campos_update = []
            valores_update = []

            for campo, valor in valores.items():
                campos_update.append(
                    f"{campo} = ?"
                )
                valores_update.append(valor)

            valores_update.append(campaign_uuid)

            cursor.execute(
                f"""
                UPDATE
                    {DATABASE}.campanha_encerramento_edunova

                SET
                    {", ".join(campos_update)}

                WHERE campaign_uuid = ?
                """,
                parameters=valores_update
            )

            return {
                "funil_registrado": True,
                "campos": list(valores.keys()),
                "classificacao": classificacao or None
            }

        finally:
            cursor.close()