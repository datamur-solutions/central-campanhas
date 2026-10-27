import base64
import html
import json
import os
import urllib.request
import urllib.error
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.db import DATABASE, get_connection


# ============================================================
# HELPERS DE BANCO
# ============================================================

def _rows(sql, parameters=None):
    with get_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(
                sql,
                parameters=parameters or [],
            )

            nomes = [
                item[0]
                for item in cursor.description
            ]

            return [
                dict(zip(nomes, row))
                for row in cursor.fetchall()
            ]

        finally:
            cursor.close()


def _one(sql, parameters=None):
    dados = _rows(
        sql,
        parameters,
    )

    return (
        dados[0]
        if dados
        else None
    )


def _safe_rows(
    tabela,
    campaign_uuid,
    order_by=None,
    limit=None,
):
    sql = f"""
        SELECT *
        FROM {DATABASE}.{tabela}
        WHERE campaign_uuid = ?
    """

    if order_by:
        sql += f"""
            ORDER BY {order_by}
        """

    if limit:
        sql += f"""
            LIMIT {int(limit)}
        """

    try:
        return _rows(
            sql,
            [campaign_uuid],
        )

    except Exception as error:
        print(
            f"[HTML] Aviso ao consultar {tabela}:",
            str(error),
        )

        return []


# ============================================================
# FORMATADORES
# ============================================================

def _txt(valor, default="-"):
    if valor is None:
        return default

    if isinstance(valor, bool):
        return (
            "Sim"
            if valor
            else "Não"
        )

    if isinstance(valor, Decimal):
        valor = float(valor)

    if isinstance(valor, float):
        return (
            f"{valor:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    if isinstance(
        valor,
        (
            datetime,
            date,
        ),
    ):
        return valor.strftime(
            "%d/%m/%Y"
            if isinstance(valor, date)
            and not isinstance(valor, datetime)
            else "%d/%m/%Y %H:%M"
        )

    texto = str(valor).strip()

    return (
        texto
        if texto
        else default
    )


def _e(valor, default="-"):
    return html.escape(
        _txt(
            valor,
            default,
        )
    )


def _humanizar(valor):
    if not valor:
        return "-"

    mapa = {
        "CADASTRADA_PLANEJAMENTO":
            "Cadastrada no Planejamento",

        "EM_VALIDACAO_COMERCIAL":
            "Em validação Comercial",

        "VALIDADA_COMERCIAL":
            "Validada pelo Comercial",

        "PARCIALMENTE_LIBERADA_EPS":
            "Liberação parcial para EPS",

        "ENVIADA_EPS":
            "Com as EPS",

        "ENCERRADA_EDUNOVA":
            "Encerrada",

        "AGUARDANDO_PLANEJAMENTO_EPS":
            "Aguardando planejamento EPS",

        "PLANEJAMENTO_EPS":
            "Planejamento EPS",

        "GO_LIVE_APROVADO":
            "Go-live aprovado",

        "EM_EXECUCAO":
            "Em execução",

        "EXECUCAO_FINALIZADA":
            "Execução finalizada",

        "OBJETIVO_KPIS":
            "Objetivo e KPIs",

        "HANDOFF_PLANO_EPS":
            "Handoff e plano EPS",

        "EXECUTOR":
            "Validação Comercial",
    }

    if valor in mapa:
        return mapa[valor]

    return (
        str(valor)
        .replace("_", " ")
        .strip()
        .title()
    )


def _numero(valor):
    if valor in (
        None,
        "",
    ):
        return 0

    try:
        return float(valor)

    except Exception:
        return 0


def _inteiro(valor):
    return int(
        round(
            _numero(valor)
        )
    )


def _pct(valor):
    numero = _numero(valor)

    if numero <= 1:
        numero *= 100

    return (
        f"{numero:.1f}%"
        .replace(".", ",")
    )


# ============================================================
# IDENTIDADE VISUAL
# ============================================================

def _logo_data_uri():
    logo = (
        Path(__file__)
        .resolve()
        .parent
        / "static"
        / "EduNova.png"
    )

    if not logo.exists():
        return None

    mime = (
        "image/png"
    )

    encoded = base64.b64encode(
        logo.read_bytes()
    ).decode("ascii")

    return (
        f"data:{mime};base64,{encoded}"
    )


def _status_class(status):
    status = (
        status
        or ""
    ).upper()

    if (
        "ENCERR" in status
        or "FINALIZ" in status
    ):
        return "done"

    if (
        "EXECU" in status
        or "ENVIADA_EPS" in status
        or "GO_LIVE" in status
    ):
        return "run"

    if (
        "VALID" in status
        or "PLANEJ" in status
    ):
        return "attention"

    return "neutral"


# ============================================================
# DADOS DA CAMPANHA
# ============================================================

def carregar_dados_campanha(
    codigo_campanha: str,
):
    campanha = _one(
        f"""
        SELECT *
        FROM {DATABASE}.campanha_master
        WHERE upper(codigo_campanha) =
              upper(?)
        LIMIT 1
        """,
        [codigo_campanha],
    )

    if not campanha:
        raise ValueError(
            f"Campanha {codigo_campanha} não encontrada."
        )

    campaign_uuid = (
        campanha[
            "campaign_uuid"
        ]
    )

    dados = {
        "campanha":
            campanha,

        "escopos":
            _safe_rows(
                "campanha_escopo",
                campaign_uuid,
                "dt_criacao ASC",
            ),

        "eps":
            _safe_rows(
                "campanha_eps",
                campaign_uuid,
                "dt_criacao ASC",
            ),

        "kpis":
            _safe_rows(
                "campanha_kpi",
                campaign_uuid,
                "kpi_principal DESC, dt_criacao ASC",
            ),

        "performance":
            _safe_rows(
                "campanha_performance",
                campaign_uuid,
                "data_referencia DESC",
                60,
            ),

        "gaps":
            _safe_rows(
                "campanha_gap",
                campaign_uuid,
                "dt_identificacao DESC",
                30,
            ),

        "evidencias":
            _safe_rows(
                "campanha_evidencia",
                campaign_uuid,
                "dt_evidencia DESC",
                30,
            ),

        "workflow":
            _safe_rows(
                "campanha_workflow",
                campaign_uuid,
                "dt_evento DESC",
                40,
            ),

        "encerramentos_eps":
            _safe_rows(
                "campanha_encerramento_eps",
                campaign_uuid,
                "dt_fechamento_eps DESC",
            ),

        "encerramento_edunova":
            _safe_rows(
                "campanha_encerramento_edunova",
                campaign_uuid,
                "dt_encerramento DESC",
                1,
            ),
    }

    return dados


# ============================================================
# COMPONENTES HTML
# ============================================================

def _campo(
    label,
    valor,
):
    return f"""
        <div class="field">
            <span>{html.escape(label)}</span>
            <strong>{_e(valor)}</strong>
        </div>
    """


def _empty(
    mensagem,
):
    return f"""
        <div class="empty">
            {html.escape(mensagem)}
        </div>
    """


def _escopos_html(
    escopos,
):
    if not escopos:
        return _empty(
            "Nenhum escopo cadastrado."
        )

    itens = []

    for item in escopos:
        partes = [
            item.get(
                "produto"
            ),
            item.get(
                "frente_pos"
            ),
            item.get(
                "supercanal"
            ),
            item.get(
                "modalidade"
            ),
        ]

        partes = [
            _humanizar(parte)
            for parte in partes
            if parte
        ]

        itens.append(
            f"""
            <div class="scope-chip">
                {" · ".join(
                    html.escape(parte)
                    for parte in partes
                )}
            </div>
            """
        )

    return (
        '<div class="scope-list">'
        + "".join(itens)
        + "</div>"
    )


def _eps_html(
    eps_rows,
):
    if not eps_rows:
        return _empty(
            "Nenhuma EPS vinculada."
        )

    cards = []

    for item in eps_rows:
        status = (
            item.get(
                "status_execucao_eps"
            )
            or "AGUARDANDO_PLANEJAMENTO_EPS"
        )

        cards.append(
            f"""
            <article class="eps-card">
                <div class="eps-top">
                    <strong>
                        {_e(item.get("eps"))}
                    </strong>

                    <span class="status {_status_class(status)}">
                        {html.escape(_humanizar(status))}
                    </span>
                </div>

                <div class="eps-grid">
                    {_campo(
                        "Responsável EPS",
                        item.get(
                            "responsavel_eps"
                        ),
                    )}

                    {_campo(
                        "Ponto focal",
                        item.get(
                            "ponto_focal_eps"
                        ),
                    )}

                    {_campo(
                        "Mailing aplicável",
                        item.get(
                            "mailing_aplicavel"
                        ),
                    )}

                    {_campo(
                        "Go-live",
                        item.get(
                            "go_live_aprovado"
                        ),
                    )}
                </div>
            </article>
            """
        )

    return (
        '<div class="eps-cards">'
        + "".join(cards)
        + "</div>"
    )


def _kpis_html(
    kpis,
):
    if not kpis:
        return _empty(
            "Nenhum KPI cadastrado."
        )

    cards = []

    for item in kpis:
        principal = (
            "Principal"
            if item.get(
                "kpi_principal"
            )
            else "Indicador"
        )

        cards.append(
            f"""
            <article class="kpi-card">
                <div class="kpi-label">
                    {principal}
                </div>

                <h3>
                    {_e(item.get("nome_kpi"))}
                </h3>

                <div class="kpi-values">
                    <div>
                        <span>Baseline</span>
                        <strong>
                            {_e(
                                item.get(
                                    "baseline_valor"
                                )
                                or
                                item.get(
                                    "baseline_descricao"
                                )
                            )}
                        </strong>
                    </div>

                    <div>
                        <span>Meta</span>
                        <strong>
                            {_e(
                                item.get(
                                    "meta_valor"
                                )
                                or
                                item.get(
                                    "meta_descricao"
                                )
                            )}
                        </strong>
                    </div>
                </div>

                <p>
                    {_e(
                        item.get(
                            "descricao_kpi"
                        ),
                        ""
                    )}
                </p>
            </article>
            """
        )

    return (
        '<div class="kpi-grid">'
        + "".join(cards)
        + "</div>"
    )


def _performance_resumo(
    performance,
):
    if not performance:
        return {
            "mailing":
                0,

            "trabalhado":
                0,

            "contatos":
                0,

            "vendas":
                0,

            "matriculas":
                0,
        }

    return {
        "mailing":
            sum(
                _inteiro(
                    item.get(
                        "mailing_recebido"
                    )
                )
                for item in performance
            ),

        "trabalhado":
            sum(
                _inteiro(
                    item.get(
                        "mailing_trabalhado"
                    )
                )
                for item in performance
            ),

        "contatos":
            sum(
                _inteiro(
                    item.get(
                        "contatos_alo"
                    )
                )
                for item in performance
            ),

        "vendas":
            sum(
                _inteiro(
                    item.get(
                        "vendas"
                    )
                )
                for item in performance
            ),

        "matriculas":
            sum(
                _inteiro(
                    item.get(
                        "matriculas"
                    )
                )
                for item in performance
            ),
    }


def _performance_html(
    performance,
):
    if not performance:
        return _empty(
            "Ainda não há performance registrada."
        )

    linhas = []

    for item in performance[:20]:
        linhas.append(
            f"""
            <tr>
                <td>
                    {_e(item.get("data_referencia"))}
                </td>

                <td>
                    {_e(item.get("eps"))}
                </td>

                <td class="num">
                    {_e(item.get("mailing_trabalhado"))}
                </td>

                <td class="num">
                    {_e(item.get("contatos_alo"))}
                </td>

                <td class="num">
                    {_e(item.get("vendas"))}
                </td>

                <td class="num">
                    {_e(item.get("matriculas"))}
                </td>

                <td>
                    {_e(
                        item.get(
                            "resultado_vs_objetivo"
                        )
                        or
                        item.get(
                            "resultado_periodo"
                        )
                    )}
                </td>
            </tr>
            """
        )

    return f"""
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>EPS</th>
                        <th>Trabalhado</th>
                        <th>Contatos</th>
                        <th>Vendas</th>
                        <th>Matrículas</th>
                        <th>Leitura</th>
                    </tr>
                </thead>

                <tbody>
                    {"".join(linhas)}
                </tbody>
            </table>
        </div>
    """


def _gaps_html(
    gaps,
):
    if not gaps:
        return _empty(
            "Nenhum gap registrado."
        )

    cards = []

    for item in gaps[:12]:
        status = (
            item.get(
                "status_gap"
            )
            or "ABERTO"
        )

        cards.append(
            f"""
            <article class="gap-card">
                <div class="gap-top">
                    <span>
                        {_e(item.get("categoria_gap"))}
                    </span>

                    <strong>
                        {_e(_humanizar(status))}
                    </strong>
                </div>

                <h3>
                    {_e(item.get("gap"))}
                </h3>

                <p>
                    <b>Causa:</b>
                    {_e(item.get("causa"))}
                </p>

                <p>
                    <b>Ação:</b>
                    {_e(item.get("acao"))}
                </p>

                <div class="gap-footer">
                    <span>
                        Responsável:
                        {_e(item.get("responsavel"))}
                    </span>

                    <span>
                        Prazo:
                        {_e(item.get("prazo"))}
                    </span>
                </div>
            </article>
            """
        )

    return (
        '<div class="gap-grid">'
        + "".join(cards)
        + "</div>"
    )


def _evidencias_html(
    evidencias,
):
    if not evidencias:
        return _empty(
            "Nenhuma evidência registrada."
        )

    linhas = []

    for item in evidencias[:20]:
        url = (
            item.get(
                "url_evidencia"
            )
            or ""
        )

        link = (
            f"""
            <a
                href="{html.escape(url)}"
                target="_blank"
                rel="noopener noreferrer"
            >
                Abrir evidência ↗
            </a>
            """
            if url
            else "-"
        )

        linhas.append(
            f"""
            <tr>
                <td>
                    {_e(item.get("dt_evidencia"))}
                </td>

                <td>
                    {_e(item.get("eps"))}
                </td>

                <td>
                    {_e(
                        item.get(
                            "titulo"
                        )
                        or
                        item.get(
                            "tipo_evidencia"
                        )
                    )}
                </td>

                <td>
                    {link}
                </td>
            </tr>
            """
        )

    return f"""
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>EPS</th>
                        <th>Evidência</th>
                        <th>Arquivo/Link</th>
                    </tr>
                </thead>

                <tbody>
                    {"".join(linhas)}
                </tbody>
            </table>
        </div>
    """


def _workflow_html(
    workflow,
):
    if not workflow:
        return _empty(
            "Ainda não há histórico de workflow."
        )

    itens = []

    for item in workflow[:18]:
        itens.append(
            f"""
            <div class="timeline-item">
                <div class="timeline-dot"></div>

                <div>
                    <div class="timeline-meta">
                        {_e(item.get("dt_evento"))}
                        ·
                        {_e(item.get("origem"))}
                    </div>

                    <strong>
                        {_e(
                            _humanizar(
                                item.get(
                                    "status_novo"
                                )
                                or
                                item.get(
                                    "tipo_evento_email"
                                )
                            )
                        )}
                    </strong>

                    <p>
                        {_e(
                            item.get(
                                "observacao"
                            ),
                            ""
                        )}
                    </p>

                    <small>
                        {_e(item.get("usuario"))}
                    </small>
                </div>
            </div>
            """
        )

    return (
        '<div class="timeline">'
        + "".join(itens)
        + "</div>"
    )


def _encerramento_html(
    encerramentos_eps,
    encerramento_edunova,
):
    if (
        not encerramentos_eps
        and not encerramento_edunova
    ):
        return _empty(
            "O encerramento ainda não foi realizado."
        )

    blocos = []

    for item in encerramentos_eps:
        blocos.append(
            f"""
            <article class="closure-card">
                <div class="closure-label">
                    Fechamento EPS ·
                    {_e(item.get("eps"))}
                </div>

                <div class="closure-numbers">
                    {_campo(
                        "Vendas",
                        item.get(
                            "vendas_final"
                        ),
                    )}

                    {_campo(
                        "Matrículas",
                        item.get(
                            "matriculas_final"
                        ),
                    )}

                    {_campo(
                        "Contatos",
                        item.get(
                            "contatos_final"
                        ),
                    )}

                    {_campo(
                        "Mailing trabalhado",
                        item.get(
                            "mailing_trabalhado_final"
                        ),
                    )}
                </div>

                <div class="closure-text">
                    <div>
                        <span>
                            Principais gaps
                        </span>

                        <p>
                            {_e(
                                item.get(
                                    "principais_gaps"
                                )
                            )}
                        </p>
                    </div>

                    <div>
                        <span>
                            Ações corretivas
                        </span>

                        <p>
                            {_e(
                                item.get(
                                    "acoes_corretivas_realizadas"
                                )
                            )}
                        </p>
                    </div>

                    <div>
                        <span>
                            Aprendizados
                        </span>

                        <p>
                            {_e(
                                item.get(
                                    "aprendizados_operacionais"
                                )
                            )}
                        </p>
                    </div>

                    <div>
                        <span>
                            Limitações
                        </span>

                        <p>
                            {_e(
                                item.get(
                                    "limitacoes_execucao"
                                )
                            )}
                        </p>
                    </div>
                </div>
            </article>
            """
        )

    if encerramento_edunova:
        item = (
            encerramento_edunova[0]
        )

        ignorar = {
            "campaign_uuid",
            "encerramento_edunova_uuid",
            "dt_criacao",
            "criado_por",
        }

        campos = []

        for chave, valor in item.items():
            if (
                chave in ignorar
                or valor in (
                    None,
                    "",
                )
            ):
                continue

            label = (
                chave
                .replace("_", " ")
                .title()
            )

            campos.append(
                _campo(
                    label,
                    valor,
                )
            )

        blocos.append(
            f"""
            <article class="closure-card internal">
                <div class="closure-label">
                    Encerramento EduNova
                </div>

                <div class="closure-numbers">
                    {"".join(campos)}
                </div>
            </article>
            """
        )

    return (
        '<div class="closure-grid">'
        + "".join(blocos)
        + "</div>"
    )



# ============================================================
# LEITURA EXECUTIVA DE RESULTADO / IMPACTO
# ============================================================

def _normalizar_chave(valor):
    texto = str(valor or "").strip().lower()

    texto = "".join(
        caractere
        for caractere in unicodedata.normalize(
            "NFD",
            texto,
        )
        if unicodedata.category(
            caractere
        ) != "Mn"
    )

    return (
        texto
        .replace("-", " ")
        .replace("_", " ")
    )


def _valor_numerico(valor):
    if valor in (
        None,
        "",
    ):
        return None

    if isinstance(
        valor,
        (
            int,
            float,
            Decimal,
        ),
    ):
        return float(valor)

    texto = (
        str(valor)
        .strip()
        .replace("R$", "")
        .replace("%", "")
        .replace(" ", "")
    )

    if not texto:
        return None

    try:
        if (
            "," in texto
            and "." in texto
        ):
            texto = (
                texto
                .replace(".", "")
                .replace(",", ".")
            )

        elif "," in texto:
            texto = texto.replace(
                ",",
                ".",
            )

        return float(texto)

    except Exception:
        return None


def _formatar_resultado_numero(
    valor,
    unidade=None,
):
    if valor is None:
        return "-"

    unidade_norm = _normalizar_chave(
        unidade
    )

    if (
        "r$" in str(unidade or "").lower()
        or "real" in unidade_norm
        or "receita" in unidade_norm
        or "rol" in unidade_norm
    ):
        return (
            "R$ "
            + f"{valor:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    if (
        "%" in str(unidade or "")
        or "percent" in unidade_norm
        or "taxa" in unidade_norm
        or "convers" in unidade_norm
    ):
        return (
            f"{valor:.1f}%"
            .replace(".", ",")
        )

    if abs(
        valor
        -
        round(valor)
    ) < 0.00001:
        return (
            f"{int(round(valor)):,}"
            .replace(",", ".")
        )

    return (
        f"{valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _buscar_texto(
    registros,
    chaves,
):
    chaves_norm = [
        _normalizar_chave(
            chave
        )
        for chave in chaves
    ]

    for registro in registros or []:
        for chave, valor in registro.items():
            if valor in (
                None,
                "",
            ):
                continue

            chave_norm = _normalizar_chave(
                chave
            )

            if any(
                alvo in chave_norm
                for alvo in chaves_norm
            ):
                texto = str(
                    valor
                ).strip()

                if texto:
                    return texto

    return None


def _resultado_atual_por_kpi(
    kpi,
    resumo,
):
    if not kpi:
        return (
            None,
            None,
        )

    nome = _normalizar_chave(
        kpi.get(
            "nome_kpi"
        )
    )

    mapa = [
        (
            [
                "matricula",
                "matriculas",
            ],
            "matriculas",
        ),
        (
            [
                "venda",
                "vendas",
            ],
            "vendas",
        ),
        (
            [
                "contato",
                "alo",
            ],
            "contatos",
        ),
        (
            [
                "mailing trabalhado",
                "base trabalhada",
            ],
            "trabalhado",
        ),
        (
            [
                "mailing recebido",
                "base recebida",
            ],
            "mailing",
        ),
    ]

    for termos, chave_resumo in mapa:
        if any(
            termo in nome
            for termo in termos
        ):
            return (
                float(
                    resumo.get(
                        chave_resumo,
                        0,
                    )
                ),
                chave_resumo,
            )

    return (
        None,
        None,
    )


def _avaliar_impacto_campanha(
    dados,
    resumo,
):
    campanha = (
        dados[
            "campanha"
        ]
    )

    kpis = (
        dados.get(
            "kpis"
        )
        or []
    )

    kpi = next(
        (
            item
            for item in kpis
            if item.get(
                "kpi_principal"
            )
        ),
        (
            kpis[0]
            if kpis
            else None
        ),
    )

    atual, chave_resultado = (
        _resultado_atual_por_kpi(
            kpi,
            resumo,
        )
    )

    meta = (
        _valor_numerico(
            kpi.get(
                "meta_valor"
            )
        )
        if kpi
        else None
    )

    baseline = (
        _valor_numerico(
            kpi.get(
                "baseline_valor"
            )
        )
        if kpi
        else None
    )

    unidade = (
        kpi.get(
            "unidade_medida"
        )
        if kpi
        else None
    )

    atingimento = (
        (
            atual
            /
            meta
            *
            100
        )
        if (
            atual is not None
            and meta not in (
                None,
                0,
            )
        )
        else None
    )

    ganho_vs_meta = (
        atual
        -
        meta
        if (
            atual is not None
            and meta is not None
        )
        else None
    )

    ganho_vs_baseline = (
        atual
        -
        baseline
        if (
            atual is not None
            and baseline is not None
        )
        else None
    )

    status_campanha = (
        campanha.get(
            "status_campanha"
        )
        or ""
    )

    encerrada = (
        "ENCERR" in status_campanha.upper()
        or bool(
            dados.get(
                "encerramentos_eps"
            )
        )
        or bool(
            dados.get(
                "encerramento_edunova"
            )
        )
    )

    if atingimento is not None:
        if atingimento >= 110:
            classificacao = (
                "SUPER CAMPANHA"
            )

            titulo = (
                "Resultado acima da meta"
            )

            classe = (
                "super"
            )

            icone = (
                "★"
            )

        elif atingimento >= 100:
            classificacao = (
                "CAMPANHA DE SUCESSO"
            )

            titulo = (
                "Meta atingida"
            )

            classe = (
                "success"
            )

            icone = (
                "✓"
            )

        elif atingimento >= 90:
            classificacao = (
                "RESULTADO FORTE"
            )

            titulo = (
                "Muito próxima da meta"
            )

            classe = (
                "strong"
            )

            icone = (
                "↗"
            )

        elif atingimento >= 70:
            classificacao = (
                "RESULTADO PARCIAL"
            )

            titulo = (
                "Gerou resultado, mas abaixo da meta"
            )

            classe = (
                "partial"
            )

            icone = (
                "◐"
            )

        else:
            classificacao = (
                "APRENDIZADO IMPORTANTE"
            )

            titulo = (
                "Resultado abaixo do esperado"
            )

            classe = (
                "learning"
            )

            icone = (
                "!"
            )

    elif encerrada:
        classificacao = (
            "CAMPANHA ENCERRADA"
        )

        titulo = (
            "Resultado consolidado"
        )

        classe = (
            "closed"
        )

        icone = (
            "✓"
        )

    else:
        classificacao = (
            "EM ACOMPANHAMENTO"
        )

        titulo = (
            "Resultado em construção"
        )

        classe = (
            "ongoing"
        )

        icone = (
            "↗"
        )

    registros_textuais = []

    if dados.get(
        "performance"
    ):
        registros_textuais.extend(
            dados[
                "performance"
            ]
        )

    if dados.get(
        "encerramentos_eps"
    ):
        registros_textuais.extend(
            dados[
                "encerramentos_eps"
            ]
        )

    if dados.get(
        "encerramento_edunova"
    ):
        registros_textuais.extend(
            dados[
                "encerramento_edunova"
            ]
        )

    impacto_texto = _buscar_texto(
        registros_textuais,
        [
            "resultado_incremental",
            "resultado_vs_objetivo",
            "resultado_vs_baseline",
            "resultado_acumulado",
            "resultado_periodo",
            "impacto",
            "ganho",
        ],
    )

    aprendizado = _buscar_texto(
        registros_textuais,
        [
            "aprendizados_operacionais",
            "aprendizado",
            "learning",
            "licao",
        ],
    )

    decisao = _buscar_texto(
        dados.get(
            "encerramento_edunova"
        )
        or [],
        [
            "decisao",
            "recomendacao",
            "conclusao",
            "replicar",
            "escalar",
            "continuidade",
        ],
    )

    if (
        not aprendizado
        and dados.get(
            "gaps"
        )
    ):
        principal_gap = (
            dados[
                "gaps"
            ][0]
        )

        partes = [
            principal_gap.get(
                "causa"
            ),
            principal_gap.get(
                "acao"
            ),
        ]

        partes = [
            str(item).strip()
            for item in partes
            if item
        ]

        if partes:
            aprendizado = (
                " | ".join(
                    partes
                )
            )

    if not impacto_texto:
        if atingimento is not None:
            impacto_texto = (
                f"O KPI principal atingiu "
                f"{atingimento:.1f}% da meta."
            )

        elif resumo.get(
            "matriculas"
        ):
            impacto_texto = (
                f"A execução registra "
                f"{resumo['matriculas']} matrículas "
                f"até o momento."
            )

        elif resumo.get(
            "vendas"
        ):
            impacto_texto = (
                f"A execução registra "
                f"{resumo['vendas']} vendas "
                f"até o momento."
            )

    if not aprendizado:
        if atingimento is not None:
            if atingimento >= 100:
                aprendizado = (
                    "O resultado comprova aderência da campanha "
                    "à meta principal. Preservar os fatores que "
                    "sustentaram a execução e documentar a mecânica "
                    "para possível replicação."
                )

            elif atingimento >= 70:
                aprendizado = (
                    "A campanha gerou tração, mas ainda há espaço "
                    "para melhorar a eficiência. Revisar os gaps, "
                    "a execução por EPS e os pontos de conversão "
                    "antes de uma próxima rodada."
                )

            else:
                aprendizado = (
                    "O resultado não atingiu a referência principal. "
                    "O valor da campanha está no aprendizado: entender "
                    "os gaps, ajustar a mecânica e testar novamente "
                    "somente com mudanças claras de execução."
                )

        else:
            aprendizado = (
                "Ainda não há aprendizado final consolidado. "
                "Ele será atualizado automaticamente no encerramento."
            )

    if not decisao:
        if atingimento is not None:
            if atingimento >= 100:
                decisao = (
                    "Sinal positivo para continuidade ou replicação, "
                    "desde que a mesma condição operacional seja preservada."
                )

            elif atingimento >= 90:
                decisao = (
                    "Campanha promissora. Ajustar os pontos de perda "
                    "antes de escalar."
                )

            elif atingimento >= 70:
                decisao = (
                    "Manter como aprendizado controlado e otimizar "
                    "a execução antes de uma nova rodada."
                )

            else:
                decisao = (
                    "Não escalar no formato atual. Tratar causas "
                    "e redesenhar os pontos críticos antes de repetir."
                )

        elif encerrada:
            decisao = (
                "Revisar os aprendizados consolidados antes de "
                "definir continuidade ou replicação."
            )

        else:
            decisao = (
                "Aguardar evolução da execução antes de concluir "
                "sobre continuidade ou escala."
            )

    metric_name = (
        kpi.get(
            "nome_kpi"
        )
        if kpi
        else (
            "Matrículas"
            if chave_resultado == "matriculas"
            else "Resultado"
        )
    )

    return {
        "classificacao":
            classificacao,

        "titulo":
            titulo,

        "classe":
            classe,

        "icone":
            icone,

        "kpi_nome":
            metric_name,

        "atual":
            atual,

        "atual_formatado":
            _formatar_resultado_numero(
                atual,
                unidade,
            ),

        "meta":
            meta,

        "meta_formatada":
            _formatar_resultado_numero(
                meta,
                unidade,
            ),

        "baseline":
            baseline,

        "baseline_formatada":
            _formatar_resultado_numero(
                baseline,
                unidade,
            ),

        "atingimento":
            atingimento,

        "atingimento_formatado":
            (
                f"{atingimento:.1f}%"
                .replace(".", ",")
                if atingimento is not None
                else "-"
            ),

        "ganho_vs_meta":
            ganho_vs_meta,

        "ganho_vs_meta_formatado":
            _formatar_resultado_numero(
                ganho_vs_meta,
                unidade,
            ),

        "ganho_vs_baseline":
            ganho_vs_baseline,

        "ganho_vs_baseline_formatado":
            _formatar_resultado_numero(
                ganho_vs_baseline,
                unidade,
            ),

        "impacto":
            impacto_texto
            or
            "Ainda não há impacto consolidado.",

        "aprendizado":
            aprendizado,

        "decisao":
            decisao,

        "encerrada":
            encerrada,
    }


def _impacto_html(
    impacto,
):
    cards = [
        (
            "Resultado atual",
            impacto[
                "atual_formatado"
            ],
            impacto[
                "kpi_nome"
            ],
        ),
        (
            "Atingimento",
            impacto[
                "atingimento_formatado"
            ],
            "versus meta principal",
        ),
        (
            "Ganho vs baseline",
            impacto[
                "ganho_vs_baseline_formatado"
            ],
            "incremento observado",
        ),
        (
            "Ganho vs meta",
            impacto[
                "ganho_vs_meta_formatado"
            ],
            "saldo sobre a referência",
        ),
    ]

    return f"""
        <section class="impact-panel {impacto['classe']}">

            <div class="impact-verdict">

                <div class="impact-icon">
                    {html.escape(
                        impacto[
                            "icone"
                        ]
                    )}
                </div>

                <div>
                    <div class="impact-overline">
                        VEREDITO EXECUTIVO
                    </div>

                    <div class="impact-classification">
                        {html.escape(
                            impacto[
                                "classificacao"
                            ]
                        )}
                    </div>

                    <h2>
                        {html.escape(
                            impacto[
                                "titulo"
                            ]
                        )}
                    </h2>

                    <p>
                        {html.escape(
                            impacto[
                                "impacto"
                            ]
                        )}
                    </p>
                </div>

            </div>

            <div class="impact-kpis">

                {
                    "".join(
                        f"""
                        <div class="impact-kpi">
                            <span>
                                {html.escape(label)}
                            </span>

                            <strong>
                                {html.escape(
                                    str(valor)
                                )}
                            </strong>

                            <small>
                                {html.escape(subtitulo)}
                            </small>
                        </div>
                        """
                        for (
                            label,
                            valor,
                            subtitulo,
                        )
                        in cards
                    )
                }

            </div>

            <div class="impact-learning">

                <div class="impact-note">
                    <span>
                        O QUE ESTE RESULTADO NOS DIZ
                    </span>

                    <p>
                        {html.escape(
                            impacto[
                                "aprendizado"
                            ]
                        )}
                    </p>
                </div>

                <div class="impact-note decision">
                    <span>
                        DECISÃO / PRÓXIMO PASSO
                    </span>

                    <p>
                        {html.escape(
                            impacto[
                                "decisao"
                            ]
                        )}
                    </p>
                </div>

            </div>

        </section>
    """

# ============================================================
# HTML PRINCIPAL
# ============================================================

def gerar_html_campanha(
    codigo_campanha: str,
):
    dados = carregar_dados_campanha(
        codigo_campanha
    )

    c = (
        dados[
            "campanha"
        ]
    )

    resumo = _performance_resumo(
        dados[
            "performance"
        ]
    )

    impacto = _avaliar_impacto_campanha(
        dados,
        resumo,
    )

    logo = _logo_data_uri()

    logo_html = (
        f"""
        <img
            src="{logo}"
            alt="EduNova Educação"
            class="logo"
        >
        """
        if logo
        else """
        <div class="logo-text">
            edunova
            <small>EDUCAÇÃO</small>
        </div>
        """
    )

    status = (
        c.get(
            "status_campanha"
        )
        or "-"
    )

    atualizacao = datetime.now().strftime(
        "%d/%m/%Y %H:%M"
    )

    html_final = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(c.get("codigo_campanha"))} — {_e(c.get("nome_campanha"))}</title>

<style>
:root{{
    --ink:#1c1420;
    --muted:#716873;
    --paper:#fbfaf7;
    --cream:#f1ede6;
    --line:#ddd4ca;
    --plum:#351044;
    --purple:#742bbd;
    --lilac:#f1e9f7;
    --orange:#ffae00;
    --green:#2f7d4b;
    --red:#b14a55;
    --blue:#386e9d;
    --white:#ffffff;
    --display:"Aptos Display","Segoe UI Variable Display","Segoe UI",Arial,sans-serif;
    --body:"Aptos","Segoe UI Variable Text","Segoe UI",Arial,sans-serif;
}}

*{{
    box-sizing:border-box;
}}

html{{
    scroll-behavior:smooth;
}}

body{{
    margin:0;
    background:var(--cream);
    color:var(--ink);
    font-family:var(--body);
    -webkit-font-smoothing:antialiased;
}}

.shell{{
    width:min(1480px,calc(100% - 42px));
    margin:22px auto 54px;
}}

.topbar{{
    min-height:72px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:24px;
    padding:0 26px;
    background:var(--ink);
    color:#fff;
}}

.logo{{
    width:122px;
    max-height:46px;
    object-fit:contain;
}}

.logo-text{{
    font-size:25px;
    font-weight:800;
    letter-spacing:-1px;
}}

.logo-text small{{
    display:block;
    font-size:7px;
    letter-spacing:2px;
}}

.top-meta{{
    text-align:right;
}}

.top-meta strong{{
    display:block;
    font-size:12px;
}}

.top-meta span{{
    color:#c8bdca;
    font-size:9px;
}}

.hero{{
    display:grid;
    grid-template-columns:1.3fr .7fr;
    min-height:430px;
    background:var(--paper);
    border:1px solid var(--line);
    border-top:0;
}}

.hero-copy{{
    padding:56px 58px;
    display:flex;
    flex-direction:column;
    justify-content:center;
}}

.mono{{
    color:#756c78;
    font-size:9px;
    font-weight:800;
    letter-spacing:.14em;
    text-transform:uppercase;
}}

.hero h1{{
    margin:16px 0 12px;
    font-family:var(--display);
    font-size:clamp(45px,5vw,76px);
    line-height:.95;
    letter-spacing:-.058em;
    font-weight:650;
}}

.hero p{{
    max-width:800px;
    margin:0;
    color:#655d68;
    font-size:15px;
    line-height:1.6;
}}

.hero-side{{
    position:relative;
    overflow:hidden;
    padding:44px;
    background:var(--plum);
    color:#fff;
}}

.hero-side::after{{
    content:"";
    position:absolute;
    width:250px;
    height:250px;
    right:-80px;
    bottom:-80px;
    border:1px solid rgba(255,255,255,.16);
    border-radius:50%;
}}

.status-line{{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:16px;
    padding-bottom:16px;
    border-bottom:1px solid rgba(255,255,255,.17);
}}

.status{{
    display:inline-flex;
    align-items:center;
    min-height:26px;
    padding:0 10px;
    border-radius:999px;
    font-size:8px;
    font-weight:800;
}}

.status.neutral{{
    background:#eee8ef;
    color:#574d5a;
}}

.status.attention{{
    background:#fff0d5;
    color:#986006;
}}

.status.run{{
    background:#e6f3ea;
    color:#2f7647;
}}

.status.done{{
    background:#e5f3e9;
    color:#286e41;
}}

.hero-status{{
    margin:42px 0 0;
}}

.hero-status .big{{
    display:block;
    font-family:var(--display);
    font-size:42px;
    line-height:1.02;
    letter-spacing:-.045em;
}}

.hero-status small{{
    display:block;
    margin-top:8px;
    color:#cab8cf;
    font-size:10px;
}}

.hero-dates{{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:14px;
    margin-top:44px;
}}

.hero-dates div{{
    padding-top:14px;
    border-top:1px solid rgba(255,255,255,.15);
}}

.hero-dates span,
.hero-dates strong{{
    display:block;
}}

.hero-dates span{{
    color:#bfaec5;
    font-size:8px;
    letter-spacing:.08em;
    text-transform:uppercase;
}}

.hero-dates strong{{
    margin-top:6px;
    font-size:13px;
}}


.impact-panel{{
    margin-top:20px;
    border:1px solid var(--line);
    background:#fff;
    overflow:hidden;
}}

.impact-verdict{{
    display:grid;
    grid-template-columns:auto 1fr;
    gap:20px;
    align-items:start;
    padding:30px;
    background:#f7f3f8;
    border-bottom:1px solid var(--line);
}}

.impact-panel.super .impact-verdict,
.impact-panel.success .impact-verdict{{
    background:#eaf5ed;
}}

.impact-panel.strong .impact-verdict{{
    background:#eef3f8;
}}

.impact-panel.partial .impact-verdict{{
    background:#fff6df;
}}

.impact-panel.learning .impact-verdict{{
    background:#fff0ee;
}}

.impact-panel.closed .impact-verdict{{
    background:#f0ecf3;
}}

.impact-panel.ongoing .impact-verdict{{
    background:#f4eff8;
}}

.impact-icon{{
    width:56px;
    height:56px;
    display:flex;
    align-items:center;
    justify-content:center;
    border-radius:50%;
    background:var(--ink);
    color:#fff;
    font-size:24px;
    font-weight:800;
}}

.impact-panel.super .impact-icon,
.impact-panel.success .impact-icon{{
    background:var(--green);
}}

.impact-panel.partial .impact-icon{{
    background:#b57608;
}}

.impact-panel.learning .impact-icon{{
    background:var(--red);
}}

.impact-overline{{
    color:#746a76;
    font-size:8px;
    font-weight:800;
    letter-spacing:.13em;
}}

.impact-classification{{
    display:inline-flex;
    align-items:center;
    min-height:24px;
    margin-top:8px;
    padding:0 9px;
    border-radius:999px;
    background:rgba(255,255,255,.72);
    color:#36283b;
    font-size:8px;
    font-weight:900;
    letter-spacing:.08em;
}}

.impact-verdict h2{{
    margin:11px 0 7px;
    font-family:var(--display);
    font-size:31px;
    line-height:1;
    letter-spacing:-.045em;
}}

.impact-verdict p{{
    max-width:920px;
    margin:0;
    color:#655b68;
    font-size:12px;
    line-height:1.55;
}}

.impact-kpis{{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    border-bottom:1px solid var(--line);
}}

.impact-kpi{{
    min-height:116px;
    padding:18px;
    border-right:1px solid var(--line);
}}

.impact-kpi:last-child{{
    border-right:0;
}}

.impact-kpi span,
.impact-kpi strong,
.impact-kpi small{{
    display:block;
}}

.impact-kpi span{{
    color:#897e8b;
    font-size:8px;
    font-weight:800;
    letter-spacing:.08em;
    text-transform:uppercase;
}}

.impact-kpi strong{{
    margin-top:16px;
    font-family:var(--display);
    font-size:29px;
    line-height:1;
    letter-spacing:-.04em;
}}

.impact-kpi small{{
    margin-top:6px;
    color:#9a909b;
    font-size:8px;
}}

.impact-learning{{
    display:grid;
    grid-template-columns:1fr 1fr;
}}

.impact-note{{
    min-height:150px;
    padding:22px;
}}

.impact-note + .impact-note{{
    border-left:1px solid var(--line);
}}

.impact-note span{{
    color:#7d707f;
    font-size:8px;
    font-weight:900;
    letter-spacing:.11em;
}}

.impact-note p{{
    margin:10px 0 0;
    color:#4f4453;
    font-size:11px;
    line-height:1.58;
}}

.impact-note.decision{{
    background:#fbf8fc;
}}

.section{{
    margin-top:20px;
    padding:30px;
    border:1px solid var(--line);
    background:var(--paper);
}}

.section-head{{
    display:flex;
    align-items:flex-end;
    justify-content:space-between;
    gap:20px;
    margin-bottom:22px;
}}

.section-head h2{{
    margin:6px 0 0;
    font-family:var(--display);
    font-size:27px;
    line-height:1;
    letter-spacing:-.04em;
}}

.section-head p{{
    max-width:560px;
    margin:0;
    color:#7a717d;
    font-size:10px;
    line-height:1.5;
}}

.kpis-top{{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    border-top:1px solid var(--ink);
    border-bottom:1px solid var(--ink);
}}

.big-number{{
    min-height:130px;
    padding:20px;
    border-right:1px solid var(--line);
}}

.big-number:last-child{{
    border-right:0;
}}

.big-number span,
.big-number strong{{
    display:block;
}}

.big-number span{{
    color:#817783;
    font-size:8px;
    font-weight:800;
    letter-spacing:.09em;
    text-transform:uppercase;
}}

.big-number strong{{
    margin-top:20px;
    font-family:var(--display);
    font-size:34px;
    line-height:1;
    letter-spacing:-.04em;
}}

.field-grid{{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:1px;
    background:var(--line);
    border:1px solid var(--line);
}}

.field{{
    min-height:92px;
    padding:16px;
    background:#fff;
}}

.field span,
.field strong{{
    display:block;
}}

.field span{{
    color:#8e8490;
    font-size:8px;
    letter-spacing:.07em;
    text-transform:uppercase;
}}

.field strong{{
    margin-top:8px;
    color:#352a39;
    font-size:11px;
    line-height:1.45;
    font-weight:650;
}}

.scope-list{{
    display:flex;
    flex-wrap:wrap;
    gap:8px;
}}

.scope-chip{{
    padding:9px 11px;
    border:1px solid #ddd3e4;
    background:#f7f2fa;
    color:#582578;
    font-size:9px;
    font-weight:700;
}}

.eps-cards{{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:12px;
}}

.eps-card,
.kpi-card,
.gap-card,
.closure-card{{
    border:1px solid var(--line);
    background:#fff;
    padding:18px;
}}

.eps-top{{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    margin-bottom:15px;
}}

.eps-grid{{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:1px;
    background:var(--line);
}}

.eps-grid .field{{
    min-height:75px;
}}

.kpi-grid{{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:12px;
}}

.kpi-label,
.closure-label{{
    color:#742bbd;
    font-size:8px;
    font-weight:800;
    letter-spacing:.09em;
    text-transform:uppercase;
}}

.kpi-card h3{{
    margin:9px 0 18px;
    font-family:var(--display);
    font-size:19px;
    letter-spacing:-.03em;
}}

.kpi-values{{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:8px;
}}

.kpi-values div{{
    padding:12px;
    background:#f5f1f6;
}}

.kpi-values span,
.kpi-values strong{{
    display:block;
}}

.kpi-values span{{
    color:#918792;
    font-size:7px;
    text-transform:uppercase;
}}

.kpi-values strong{{
    margin-top:5px;
    font-size:12px;
}}

.kpi-card p{{
    margin:14px 0 0;
    color:#786f7a;
    font-size:10px;
    line-height:1.45;
}}

.table-wrap{{
    overflow:auto;
    border-top:1px solid var(--ink);
}}

table{{
    width:100%;
    border-collapse:collapse;
}}

th{{
    padding:10px 12px;
    border-bottom:1px solid var(--line);
    color:#8a818c;
    text-align:left;
    font-size:7px;
    letter-spacing:.08em;
    text-transform:uppercase;
}}

td{{
    padding:12px;
    border-bottom:1px solid #ece6e0;
    color:#5f5662;
    font-size:9px;
    vertical-align:top;
}}

td.num{{
    font-weight:700;
    color:#2d2331;
}}

td a{{
    color:#6926a5;
    font-weight:700;
    text-decoration:none;
}}

.gap-grid{{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:12px;
}}

.gap-top{{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    color:#8f8591;
    font-size:8px;
    text-transform:uppercase;
}}

.gap-top strong{{
    color:#82384a;
}}

.gap-card h3{{
    margin:12px 0;
    font-size:14px;
}}

.gap-card p{{
    margin:7px 0;
    color:#706773;
    font-size:10px;
    line-height:1.45;
}}

.gap-footer{{
    display:flex;
    justify-content:space-between;
    gap:12px;
    margin-top:15px;
    padding-top:12px;
    border-top:1px solid var(--line);
    color:#8a818c;
    font-size:8px;
}}

.timeline{{
    position:relative;
}}

.timeline-item{{
    position:relative;
    display:grid;
    grid-template-columns:20px 1fr;
    gap:10px;
    padding:0 0 18px;
}}

.timeline-item::before{{
    content:"";
    position:absolute;
    left:6px;
    top:12px;
    bottom:0;
    width:1px;
    background:#d8cfe0;
}}

.timeline-item:last-child::before{{
    display:none;
}}

.timeline-dot{{
    position:relative;
    z-index:2;
    width:13px;
    height:13px;
    margin-top:2px;
    border-radius:50%;
    background:#742bbd;
    box-shadow:0 0 0 4px #efe6f6;
}}

.timeline-meta{{
    color:#9b929d;
    font-size:8px;
}}

.timeline-item strong{{
    display:block;
    margin-top:3px;
    font-size:11px;
}}

.timeline-item p{{
    margin:4px 0 0;
    color:#746b77;
    font-size:9px;
}}

.timeline-item small{{
    display:block;
    margin-top:5px;
    color:#a298a4;
    font-size:8px;
}}

.closure-grid{{
    display:grid;
    gap:12px;
}}

.closure-numbers{{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:1px;
    margin-top:14px;
    background:var(--line);
}}

.closure-text{{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:12px;
    margin-top:14px;
}}

.closure-text div{{
    padding:14px;
    background:#f8f5f9;
}}

.closure-text span{{
    color:#7d6d84;
    font-size:8px;
    font-weight:800;
    text-transform:uppercase;
}}

.closure-text p{{
    margin:7px 0 0;
    color:#605566;
    font-size:10px;
    line-height:1.5;
}}

.empty{{
    padding:24px;
    border:1px dashed #d7cedb;
    color:#928995;
    text-align:center;
    font-size:10px;
}}

.footer{{
    display:flex;
    justify-content:space-between;
    gap:20px;
    margin-top:20px;
    padding:20px 4px;
    color:#8a818c;
    font-size:8px;
}}

@media(max-width:1000px){{
    .hero{{
        grid-template-columns:1fr;
    }}

    .impact-kpis{{
        grid-template-columns:repeat(2,minmax(0,1fr));
    }}

    .impact-kpi:nth-child(2){{
        border-right:0;
    }}

    .impact-kpi:nth-child(-n+2){{
        border-bottom:1px solid var(--line);
    }}

    .kpis-top{{
        grid-template-columns:repeat(2,minmax(0,1fr));
    }}

    .field-grid,
    .kpi-grid,
    .eps-cards,
    .closure-numbers{{
        grid-template-columns:repeat(2,minmax(0,1fr));
    }}
}}

@media(max-width:650px){{
    .impact-verdict{{
        grid-template-columns:1fr;
    }}

    .impact-kpis,
    .impact-learning{{
        grid-template-columns:1fr;
    }}

    .impact-kpi{{
        border-right:0;
        border-bottom:1px solid var(--line);
    }}

    .impact-note + .impact-note{{
        border-left:0;
        border-top:1px solid var(--line);
    }}

    .shell{{
        width:calc(100% - 20px);
        margin:10px auto 30px;
    }}

    .topbar{{
        padding:0 16px;
    }}

    .hero-copy,
    .hero-side,
    .section{{
        padding:24px;
    }}

    .hero h1{{
        font-size:44px;
    }}

    .kpis-top,
    .field-grid,
    .kpi-grid,
    .eps-cards,
    .gap-grid,
    .closure-numbers,
    .closure-text{{
        grid-template-columns:1fr;
    }}

    .section-head{{
        align-items:flex-start;
        flex-direction:column;
    }}
}}
</style>
</head>

<body>

<div class="shell">

    <header class="topbar">
        <div>
            {logo_html}
        </div>

        <div class="top-meta">
            <strong>
                Central de Campanhas
            </strong>

            <span>
                Documento executivo interno EduNova
            </span>
        </div>
    </header>

    <section class="hero">

        <div class="hero-copy">
            <div class="mono">
                {_e(c.get("codigo_campanha"))}
                ·
                {_e(c.get("produto"))}
            </div>

            <h1>
                {_e(c.get("nome_campanha"))}
            </h1>

            <p>
                {_e(
                    c.get(
                        "objetivo_campanha"
                    )
                    or
                    c.get(
                        "oportunidade_problema"
                    )
                )}
            </p>
        </div>

        <aside class="hero-side">

            <div class="status-line">
                <span>
                    STATUS ATUAL
                </span>

                <span class="status {_status_class(status)}">
                    {html.escape(_humanizar(status))}
                </span>
            </div>

            <div class="hero-status">
                <span class="big">
                    {html.escape(_humanizar(c.get("etapa_pop")))}
                </span>

                <small>
                    etapa atual do POP
                </small>
            </div>

            <div class="hero-dates">
                <div>
                    <span>
                        Início previsto
                    </span>

                    <strong>
                        {_e(c.get("dt_inicio_prevista"))}
                    </strong>
                </div>

                <div>
                    <span>
                        Fim previsto
                    </span>

                    <strong>
                        {_e(c.get("dt_fim_prevista"))}
                    </strong>
                </div>
            </div>

        </aside>

    </section>

    {_impacto_html(impacto)}

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    01 / RESULTADO
                </div>

                <h2>
                    Resultado consolidado
                </h2>
            </div>

            <p>
                Consolidação dos registros de performance
                informados pelas EPS durante a execução.
            </p>
        </div>

        <div class="kpis-top">

            <div class="big-number">
                <span>
                    Mailing recebido
                </span>

                <strong>
                    {resumo["mailing"]}
                </strong>
            </div>

            <div class="big-number">
                <span>
                    Mailing trabalhado
                </span>

                <strong>
                    {resumo["trabalhado"]}
                </strong>
            </div>

            <div class="big-number">
                <span>
                    Contatos
                </span>

                <strong>
                    {resumo["contatos"]}
                </strong>
            </div>

            <div class="big-number">
                <span>
                    Vendas
                </span>

                <strong>
                    {resumo["vendas"]}
                </strong>
            </div>

            <div class="big-number">
                <span>
                    Matrículas
                </span>

                <strong>
                    {resumo["matriculas"]}
                </strong>
            </div>

        </div>

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    02 / CAMPANHA
                </div>

                <h2>
                    Estratégia e objetivo
                </h2>
            </div>
        </div>

        <div class="field-grid">

            {_campo(
                "Tipo de ação",
                c.get("tipo_acao"),
            )}

            {_campo(
                "Público-alvo",
                c.get("publico_alvo"),
            )}

            {_campo(
                "Estratégia",
                c.get("estrategia"),
            )}

            {_campo(
                "Mecânica",
                c.get("mecanica"),
            )}

            {_campo(
                "Oferta / benefício",
                c.get("oferta_beneficio"),
            )}

            {_campo(
                "Argumento comercial",
                c.get("argumento_comercial"),
            )}

            {_campo(
                "Responsável Planejamento",
                c.get(
                    "responsavel_planejamento"
                ),
            )}

            {_campo(
                "Responsável Comercial",
                c.get(
                    "responsavel_comercial"
                ),
            )}

        </div>

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    03 / ESCOPO
                </div>

                <h2>
                    Abrangência da campanha
                </h2>
            </div>
        </div>

        {_escopos_html(dados["escopos"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    04 / EPS
                </div>

                <h2>
                    Execução operacional
                </h2>
            </div>

            <p>
                Status individual de cada EPS
                vinculada à campanha.
            </p>
        </div>

        {_eps_html(dados["eps"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    05 / INDICADORES
                </div>

                <h2>
                    KPIs, baseline e meta
                </h2>
            </div>
        </div>

        {_kpis_html(dados["kpis"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    06 / PERFORMANCE
                </div>

                <h2>
                    Evolução da execução
                </h2>
            </div>
        </div>

        {_performance_html(dados["performance"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    07 / GAPS
                </div>

                <h2>
                    Desvios e planos de ação
                </h2>
            </div>
        </div>

        {_gaps_html(dados["gaps"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    08 / EVIDÊNCIAS
                </div>

                <h2>
                    Comprovações da execução
                </h2>
            </div>
        </div>

        {_evidencias_html(dados["evidencias"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    09 / HISTÓRICO
                </div>

                <h2>
                    Jornada da campanha
                </h2>
            </div>
        </div>

        {_workflow_html(dados["workflow"])}

    </section>

    <section class="section">

        <div class="section-head">
            <div>
                <div class="mono">
                    10 / ENCERRAMENTO
                </div>

                <h2>
                    Resultado e aprendizados
                </h2>
            </div>

            <p>
                Esta seção evolui automaticamente
                conforme EPS e EduNova concluem o fechamento.
            </p>
        </div>

        {_encerramento_html(
            dados["encerramentos_eps"],
            dados["encerramento_edunova"],
        )}

    </section>

    <footer class="footer">
        <span>
            EduNova Educação · Central de Campanhas Comerciais
        </span>

        <span>
            Atualizado automaticamente em
            {atualizacao}
        </span>
    </footer>

</div>

</body>
</html>
"""

    return (
        html_final,
        dados,
    )


# ============================================================
# DIRECIONAMENTO DE PASTA
# ============================================================

def pasta_produto(
    produto,
):
    bruto = str(
        produto
        or ""
    ).strip()

    chave = _normalizar_chave(
        bruto
    )

    # Aceita as formas usadas no banco/front:
    # GRADUACAO / GRADUAÇÃO
    # POS_GRADUACAO / PÓS-GRADUAÇÃO / PÓS GRADUAÇÃO
    # TECNICO / TÉCNICO
    # PROFISSIONALIZANTES

    if chave in {
        "graduacao",
        "graduacao ",
    }:
        nome_pasta = "Graduação"

    elif (
        chave in {
            "pos graduacao",
            "posgraduacao",
        }
        or (
            "pos" in chave
            and "graduacao" in chave
        )
    ):
        nome_pasta = "Pós graduação"

    elif chave == "tecnico":
        nome_pasta = "Técnico"

    elif chave == "profissionalizantes":
        nome_pasta = "Profissionalizantes"

    else:
        raise ValueError(
            "Produto sem pasta configurada: "
            + bruto
        )

    return (
        "/Campanhas Comerciais/"
        + nome_pasta
    )


# ============================================================
# ENVIO POWER AUTOMATE
# ============================================================

def _webhook_url():
    url = (
        os.getenv(
            "CAMPAIGN_HTML_WEBHOOK_URL"
        )
        or ""
    ).strip()

    if not url:
        raise ValueError(
            "CAMPAIGN_HTML_WEBHOOK_URL "
            "não configurada no .env."
        )

    return url


def publicar_html_campanha(
    codigo_campanha: str,
):
    conteudo_html, dados = (
        gerar_html_campanha(
            codigo_campanha
        )
    )

    campanha = (
        dados[
            "campanha"
        ]
    )

    codigo = (
        campanha[
            "codigo_campanha"
        ]
    )

    pasta = pasta_produto(
        campanha.get(
            "produto"
        )
    )

    nome_arquivo = (
        f"Campanha_{codigo}.html"
    )

    caminho = (
        pasta
        + "/"
        + nome_arquivo
    )

    payload = {
        "codigo_campanha":
            codigo,

        "nome_campanha":
            campanha.get(
                "nome_campanha"
            ),

        "produto":
            campanha.get(
                "produto"
            ),

        "pasta_produto":
            pasta,

        "nome_arquivo":
            nome_arquivo,

        "caminho_arquivo":
            caminho,

        "conteudo_html":
            conteudo_html,

        "dt_atualizacao":
            datetime.now().isoformat(),
    }

    req = urllib.request.Request(
        _webhook_url(),
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Content-Type":
                "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=90,
        ) as response:
            corpo = response.read().decode(
                "utf-8",
                errors="replace",
            )

            return {
                "sucesso":
                    True,

                "status_http":
                    response.status,

                "codigo_campanha":
                    codigo,

                "pasta":
                    pasta,

                "nome_arquivo":
                    nome_arquivo,

                "caminho":
                    caminho,

                "resposta":
                    corpo,
            }

    except urllib.error.HTTPError as error:
        corpo = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "Power Automate respondeu "
            f"HTTP {error.code}: "
            f"{corpo or error.reason}"
        ) from error


def gerar_preview_local(
    codigo_campanha: str,
    destino=None,
):
    conteudo_html, dados = (
        gerar_html_campanha(
            codigo_campanha
        )
    )

    codigo = (
        dados[
            "campanha"
        ][
            "codigo_campanha"
        ]
    )

    path = Path(
        destino
        or
        f"preview_{codigo}.html"
    )

    path.write_text(
        conteudo_html,
        encoding="utf-8",
    )

    return path
