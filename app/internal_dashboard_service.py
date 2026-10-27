"""
DASHBOARD DE CAMPANHAS

Visão consolidada de todas as campanhas — ativas e encerradas
— para o time olhar o histórico, comparar e responder o que
funcionou.

Decisão de desenho: este módulo devolve a lista completa, com
os dados já reunidos, e o filtro acontece no navegador.

O volume é de dezenas de campanhas, não milhões. Filtrar no
banco exigiria uma consulta nova a cada combinação de filtro
— e como o Supabase gratuito cobra latência por conexão, o
usuário sentiria cada clique. Trazendo tudo de uma vez, os
filtros respondem instantaneamente.
"""

from app.db import (
    DATABASE,
    get_connection,
)


def _linhas(cursor):
    nomes = [
        item[0]
        for item in cursor.description
    ]

    return [
        dict(zip(nomes, linha))
        for linha in cursor.fetchall()
    ]


def _numero(valor):
    if valor in (None, ""):
        return 0

    try:
        return int(valor)

    except (TypeError, ValueError):
        return 0


def carregar_dashboard():

    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            # ------------------------------------------------
            # 1. CAMPANHAS
            # ------------------------------------------------

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
                    status_campanha,
                    etapa_pop,
                    objetivo_campanha,
                    publico_alvo,
                    dimensao_estimada,
                    responsavel_planejamento,
                    responsavel_comercial,
                    dt_inicio_prevista,
                    dt_fim_prevista,
                    dt_criacao

                FROM {DATABASE}.campanha_master

                ORDER BY dt_criacao DESC
                """
            )

            campanhas = _linhas(cursor)

            if not campanhas:
                return {
                    "quantidade": 0,
                    "campanhas": []
                }

            por_uuid = {
                item["campaign_uuid"]: item
                for item in campanhas
            }

            for item in campanhas:
                item["escopos"] = []
                item["eps"] = []
                item["encerramento"] = None

                # Marcos do fluxo (primeira vez de cada etapa).
                # Alimentam "Execução e prazos" no historico.
                item["marcos"] = {
                    "cadastro": None,
                    "envio_comercial": None,
                    "validacao_comercial": None,
                }

                item["realizado"] = {
                    "mailing": 0,
                    "trabalhado": 0,
                    "tentativas": 0,
                    "alo": 0,
                    "efetivos": 0,
                    "vendas": 0,
                    "matriculas": 0,
                }

            # ------------------------------------------------
            # 2. ESCOPOS — alimentam os filtros de segmentação
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT
                    campaign_uuid,
                    produto,
                    frente_pos,
                    supercanal,
                    modalidade

                FROM {DATABASE}.campanha_escopo

                WHERE ativo = TRUE
                """
            )

            for linha in _linhas(cursor):

                alvo = por_uuid.get(
                    linha["campaign_uuid"]
                )

                if alvo is not None:
                    alvo["escopos"].append(linha)

            # ------------------------------------------------
            # 3. EPS VINCULADAS
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT
                    campaign_uuid,
                    eps,
                    status_execucao_eps,
                    liberada_para_eps,
                    dt_liberacao_eps,
                    go_live_aprovado,
                    dt_go_live,
                    operacao_ativada,
                    dt_inicio_operacional,
                    dt_fim_operacional

                FROM {DATABASE}.campanha_eps
                """
            )

            for linha in _linhas(cursor):

                alvo = por_uuid.get(
                    linha["campaign_uuid"]
                )

                if alvo is not None:
                    linha["dt_fechamento_eps"] = None
                    alvo["eps"].append(linha)

            # ------------------------------------------------
            # 3b. MARCOS DO FLUXO (workflow da campanha)
            #
            # Primeira data de cada etapa: cadastro pelo
            # Planejamento, envio ao Comercial e validacao.
            # Se a tabela falhar, o historico segue sem prazos.
            # ------------------------------------------------

            try:
                cursor.execute(
                    f"""
                    SELECT
                        campaign_uuid,
                        status_novo,
                        MIN(dt_evento) AS dt_evento

                    FROM {DATABASE}.campanha_workflow

                    WHERE status_novo IN (
                        'CADASTRADA_PLANEJAMENTO',
                        'EM_VALIDACAO_COMERCIAL',
                        'VALIDADA_COMERCIAL'
                    )

                    GROUP BY campaign_uuid, status_novo
                    """
                )

                marcos = _linhas(cursor)

            except Exception as erro:
                print("[dashboard] workflow indisponivel:", str(erro))
                marcos = []

            nome_marco = {
                "CADASTRADA_PLANEJAMENTO": "cadastro",
                "EM_VALIDACAO_COMERCIAL": "envio_comercial",
                "VALIDADA_COMERCIAL": "validacao_comercial",
            }

            for linha in marcos:
                alvo = por_uuid.get(linha["campaign_uuid"])
                chave = nome_marco.get(linha["status_novo"])

                if alvo is not None and chave:
                    alvo["marcos"][chave] = linha["dt_evento"]

            # ------------------------------------------------
            # 3c. FINALIZACAO INFORMADA PELA EPS
            # ------------------------------------------------

            try:
                cursor.execute(
                    f"""
                    SELECT campaign_uuid, eps, dt_fechamento_eps
                    FROM {DATABASE}.campanha_encerramento_eps
                    """
                )

                for linha in _linhas(cursor):
                    alvo = por_uuid.get(linha["campaign_uuid"])

                    if alvo is None:
                        continue

                    for item_eps in alvo["eps"]:
                        if item_eps["eps"] == linha["eps"]:
                            item_eps["dt_fechamento_eps"] = linha["dt_fechamento_eps"]

            except Exception as erro:
                print("[dashboard] encerramento EPS indisponivel:", str(erro))

            for item in campanhas:
                for item_eps in item["eps"]:
                    item_eps.pop("campaign_uuid", None)

            # ------------------------------------------------
            # 4. PERFORMANCE ACUMULADA
            #
            # Soma os registros diários. Para campanha em
            # andamento é o único número que existe — o funil
            # do encerramento ainda não foi preenchido.
            # ------------------------------------------------

            cursor.execute(
                f"""
                SELECT
                    campaign_uuid,
                    mailing_recebido,
                    mailing_trabalhado,
                    tentativas_disparos,
                    contatos_alo,
                    produtivos,
                    vendas,
                    matriculas

                FROM {DATABASE}.campanha_performance
                """
            )

            for linha in _linhas(cursor):

                alvo = por_uuid.get(
                    linha["campaign_uuid"]
                )

                if alvo is None:
                    continue

                acumulado = alvo["realizado"]

                acumulado["mailing"] += _numero(
                    linha["mailing_recebido"]
                )

                acumulado["trabalhado"] += _numero(
                    linha["mailing_trabalhado"]
                )

                acumulado["tentativas"] += _numero(
                    linha["tentativas_disparos"]
                )

                acumulado["alo"] += _numero(
                    linha["contatos_alo"]
                )

                acumulado["efetivos"] += _numero(
                    linha["produtivos"]
                )

                acumulado["vendas"] += _numero(
                    linha["vendas"]
                )

                acumulado["matriculas"] += _numero(
                    linha["matriculas"]
                )

            # ------------------------------------------------
            # 5. ENCERRAMENTO
            #
            # Quando existe, é a fonte oficial do resultado:
            # foi apurado pelo Planejamento e substitui a
            # soma dos registros diários.
            # ------------------------------------------------

            # SELECT * de proposito: a tabela de encerramento
            # variou de nome de coluna entre ambientes, e uma
            # coluna a menos derrubava a consulta inteira e
            # zerava o dashboard. Aqui lemos tudo e pegamos o
            # que existir.
            try:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM {DATABASE}.campanha_encerramento_edunova
                    """
                )

                encerramentos = _linhas(cursor)

            except Exception as erro:
                print(
                    "[dashboard] encerramento indisponivel:",
                    str(erro)
                )
                encerramentos = []

            # Nomes alternativos ja vistos para o mesmo dado.
            mapa_funil = {
                "mailing": [
                    "mailing", "mailing_final",
                    "mailing_total", "base"
                ],
                "trabalhado": [
                    "mailing_trabalhado",
                    "mailing_trabalhado_final",
                    "trabalhado"
                ],
                "tentativas": [
                    "tentativas", "tentativas_disparos",
                    "tentativas_disparos_final"
                ],
                "alo": [
                    "alo", "contatos", "contatos_alo",
                    "contatos_final", "atendidos"
                ],
                "efetivos": [
                    "efetivos", "produtivos", "efetivo"
                ],
                "vendas": [
                    "vendas", "vendas_final"
                ],
                "matriculas": [
                    "matriculas", "matriculas_final"
                ],
            }

            def _primeiro(linha, nomes):
                for nome in nomes:
                    if nome in linha and linha[nome] not in (None, ""):
                        return linha[nome]
                return None

            for linha in encerramentos:

                chave = (
                    linha.get("campaign_uuid")
                    or linha.get("campanha_uuid")
                )

                alvo = por_uuid.get(chave)

                if alvo is None:
                    continue

                alvo["encerramento"] = {
                    "classificacao_resultado":
                        linha.get("classificacao_resultado"),

                    "analise_resultado":
                        linha.get("analise_resultado"),

                    "aprendizados":
                        _primeiro(linha, [
                            "aprendizados",
                            "principais_aprendizados",
                            "aprendizado"
                        ]),

                    "resumo":
                        _primeiro(linha, [
                            "recomendacoes",
                            "resumo_resultado",
                            "resumo", "observacao"
                        ]),

                    "decisao":
                        _primeiro(linha, [
                            "decisao_final", "decisao"
                        ]),
                }

                for destino, nomes in mapa_funil.items():

                    valor = _primeiro(linha, nomes)

                    if valor is not None:
                        alvo["realizado"][destino] = (
                            _numero(valor)
                        )

            for item in campanhas:
                item.pop("campaign_uuid", None)

            return {
                "quantidade": len(campanhas),
                "campanhas": campanhas
            }

        finally:
            cursor.close()