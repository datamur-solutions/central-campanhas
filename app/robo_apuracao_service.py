"""
ROBO DE APURACAO - FUNIL PARALELO

Modulo novo. Nao altera nenhum service existente: so LE as
tabelas da campanha (campanha_master, campanha_eps, escopos,
encerramento da EPS) e GRAVA nas tabelas proprias da apuracao:

    apuracao_funil         1 linha por campanha x EPS
    apuracao_serie_diaria  campanha x EPS x dia
    apuracao_tabulacao     campanha x EPS x tabulacao
    apuracao_execucao      log de cada rodada do robo

Quem grava: SO o robo da VM, autenticado pela chave do
cabecalho X-Robo-Key (variavel ROBO_API_KEY no Render).
Sem a variavel configurada, as rotas do robo ficam desligadas.

Quem le: a aba Dashboard do portal interno.

Regras de status (decididas aqui, nao so no robo):
  - Apuracao PARCIAL todos os dias:
      INCENTIVO: toda EPS liberada, a partir do inicio da campanha.
      ACAO COMERCIAL: so depois do go-live da EPS, e o periodo
      apurado comeca na data do go-live.
  - INCENTIVO vira FINAL quando passa a data de fim, mesmo que
    a EPS nao tenha finalizado.
  - ACAO COMERCIAL so vira FINAL quando a EPS finaliza a execucao.
  - Depois de FINAL, o robo continua atualizando as matriculas
    ate a janela_fim (maturacao); o status nao volta a PARCIAL.
"""

import hmac
import json
import os
import uuid

from pathlib import Path

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.db import (
    DATABASE,
    fetch_all,
    get_connection,
)

from app.robo_notificacao_service import (
    MOTIVOS,
    notificar_alerta,
    notificar_campanha_apurada,
)


EPS_VALIDAS = ("VOXA", "PRISMA", "LUMEN")
# A EPS foi liberada quando o status de execucao deixa de ser
# vazio (a liberacao grava AGUARDANDO_PLANEJAMENTO_EPS). Campanha
# cancelada nao entra.
STATUS_CAMPANHA_FORA = ("CANCELADA", "CANCELADO", "RASCUNHO")
FUSO_BRASILIA = timezone(timedelta(hours=-3))
STATUS_APURACAO = ("PARCIAL", "FINAL")


# ============================================================
# MODELOS DO PAYLOAD DO ROBO
# ============================================================

class FunilApurado(BaseModel):
    mailing: int | None = Field(default=None, ge=0)
    mailing_enviado: int | None = Field(default=None, ge=0)
    leads_acionados: int | None = Field(default=None, ge=0)
    tentativas: int | None = Field(default=None, ge=0)
    trabalhados: int | None = Field(default=None, ge=0)
    alo: int | None = Field(default=None, ge=0)
    efetivos: int | None = Field(default=None, ge=0)
    vendas: int | None = Field(default=None, ge=0)
    matriculas: int | None = Field(default=None, ge=0)
    alunos: int | None = Field(default=None, ge=0)
    leads_reacionados: int | None = Field(default=None, ge=0)


class PontoSerie(BaseModel):
    dia: date
    tentativas: int = Field(default=0, ge=0)
    vendas: int = Field(default=0, ge=0)
    matriculas: int = Field(default=0, ge=0)


class LinhaTabulacao(BaseModel):
    classificacao: str = Field(min_length=1, max_length=60)
    tabulacao_1: str | None = Field(default=None, max_length=300)
    tabulacao_2: str | None = Field(default=None, max_length=300)
    tabulacao_3: str | None = Field(default=None, max_length=300)
    interacoes: int = Field(default=0, ge=0)
    leads: int = Field(default=0, ge=0)


class ApuracaoPayload(BaseModel):
    eps: Literal["VOXA", "PRISMA", "LUMEN"]
    status_apuracao: Literal["PARCIAL", "FINAL"]

    periodo_ini: date
    periodo_fim: date
    janela_fim: date | None = None
    dt_base: date

    fonte_funil: str | None = Field(default=None, max_length=60)
    fonte_matricula: str | None = Field(default=None, max_length=60)

    funil: FunilApurado
    faixas_tentativas: dict[str, int] | None = None
    serie_diaria: list[PontoSerie] = Field(default_factory=list)
    tabulacoes: list[LinhaTabulacao] = Field(default_factory=list)

    observacao: str | None = Field(default=None, max_length=2000)
    duracao_seg: float | None = None

    @model_validator(mode="after")
    def validar(self):
        if self.periodo_ini > self.periodo_fim:
            raise ValueError("periodo_ini maior que periodo_fim.")
        if len(self.serie_diaria) > 1000:
            raise ValueError("Serie diaria acima de 1000 pontos.")
        if len(self.tabulacoes) > 5000:
            raise ValueError("Tabulacoes acima de 5000 linhas.")
        return self


class ExecucaoPayload(BaseModel):
    codigo_campanha: str | None = Field(default=None, max_length=30)
    eps: str | None = Field(default=None, max_length=20)
    resultado: Literal["OK", "PENDENCIA", "ERRO", "SEM_PENDENTES", "AGUARDANDO_BASE"]
    motivo: str | None = Field(default=None, max_length=40)
    mensagem: str | None = Field(default=None, max_length=2000)
    dt_base: date | None = None
    duracao_seg: float | None = None


# ============================================================
# AUTENTICACAO DO ROBO
# ============================================================

def validar_chave_robo(chave_recebida: str | None):
    """
    Compara a chave do cabecalho com ROBO_API_KEY em tempo
    constante. Sem a variavel no ambiente, a integracao fica
    desligada (nada e aceito).
    """
    esperada = os.getenv("ROBO_API_KEY", "").strip()

    if not esperada:
        raise PermissionError("Integração do robô desligada neste ambiente.")

    if not chave_recebida or not hmac.compare_digest(
        chave_recebida.strip().encode(),
        esperada.encode(),
    ):
        raise PermissionError("Chave do robô inválida.")


# ============================================================
# AUXILIARES
# ============================================================

def _agora():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


def _linhas(cursor):
    if cursor.description is None:
        return []
    nomes = [item[0] for item in cursor.description]
    return [dict(zip(nomes, linha)) for linha in cursor.fetchall()]


def _inserir(cursor, tabela, dados):
    colunas = list(dados.keys())
    cursor.execute(
        f"""
        INSERT INTO {DATABASE}.{tabela} ({", ".join(colunas)})
        VALUES ({", ".join(["?"] * len(colunas))})
        """,
        parameters=[dados[c] for c in colunas],
    )


def _hoje():
    return datetime.now(FUSO_BRASILIA).date()


def _data(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    return valor


# ============================================================
# 1. PENDENTES
#
# Toda campanha x EPS com a EPS operando, ja iniciada, e cuja
# apuracao ainda nao fechou (nao e FINAL, ou e FINAL mas a
# janela de maturacao das matriculas ainda esta aberta).
# O robo decide, com a data base do Databricks, se apura hoje.
# ============================================================

def listar_pendentes():
    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            f"""
            SELECT
                m.campaign_uuid,
                m.codigo_campanha,
                m.nome_campanha,
                m.tipo_acao,
                m.dt_inicio_prevista,
                m.dt_fim_prevista,
                m.meta_base,
                m.status_campanha,

                ce.campanha_eps_uuid,
                ce.eps,
                ce.status_execucao_eps,
                ce.go_live_aprovado,
                ce.dt_go_live,
                ce.mailing_aplicavel,
                ce.meta_eps,

                enc.dt_fechamento_eps,

                af.status_apuracao,
                af.janela_fim,
                af.dt_base AS ultima_dt_base,
                af.dt_apuracao AS ultima_apuracao

            FROM {DATABASE}.campanha_master m

            INNER JOIN {DATABASE}.campanha_eps ce
                ON ce.campaign_uuid = m.campaign_uuid

            LEFT JOIN {DATABASE}.campanha_encerramento_eps enc
                ON enc.campaign_uuid = m.campaign_uuid
               AND enc.eps = ce.eps

            LEFT JOIN {DATABASE}.apuracao_funil af
                ON af.codigo_campanha = m.codigo_campanha
               AND af.eps = ce.eps

            WHERE ce.status_execucao_eps IS NOT NULL
              AND trim(ce.status_execucao_eps) <> ''
              AND upper(coalesce(m.status_campanha, '')) NOT IN (?, ?, ?)
              AND (
                    (m.tipo_acao = 'INCENTIVO' AND m.dt_inicio_prevista <= ?)
                 OR (m.tipo_acao <> 'INCENTIVO' AND ce.go_live_aprovado = TRUE)
              )
              AND (
                    af.status_apuracao IS NULL
                 OR af.status_apuracao <> 'FINAL'
                 OR af.janela_fim IS NULL
                 OR af.janela_fim >= ?
              )

            ORDER BY m.dt_inicio_prevista, m.codigo_campanha, ce.eps
            """,
            parameters=[*STATUS_CAMPANHA_FORA, _hoje(), _hoje()],
        )
        vinculos = _linhas(cursor)

        if not vinculos:
            return {"quantidade": 0, "pendentes": []}

        uuids = [v["campanha_eps_uuid"] for v in vinculos]
        marcadores = ", ".join(["?"] * len(uuids))

        cursor.execute(
            f"""
            SELECT
                ee.campanha_eps_uuid,
                esc.produto,
                esc.frente_pos,
                esc.supercanal,
                esc.outro_supercanal_descricao,
                esc.modalidade

            FROM {DATABASE}.campanha_eps_escopo ee

            INNER JOIN {DATABASE}.campanha_escopo esc
                ON ee.escopo_uuid = esc.escopo_uuid

            WHERE ee.campanha_eps_uuid IN ({marcadores})
              AND ee.ativo = TRUE
              AND esc.ativo = TRUE
            """,
            parameters=uuids,
        )
        escopos = _linhas(cursor)

    escopos_por_vinculo = {}
    for esc in escopos:
        chave = esc.pop("campanha_eps_uuid")
        escopos_por_vinculo.setdefault(chave, []).append(esc)

    pendentes = []
    for v in vinculos:
        pendentes.append({
            "codigo_campanha": str(v["codigo_campanha"]).upper(),
            "nome_campanha": v["nome_campanha"],
            "tipo_acao": v["tipo_acao"],
            "eps": v["eps"],
            "status_campanha": v["status_campanha"],
            "status_execucao_eps": v["status_execucao_eps"],
            "dt_inicio_prevista": _data(v["dt_inicio_prevista"]),
            "dt_fim_prevista": _data(v["dt_fim_prevista"]),
            "dt_finalizacao_eps": _data(v["dt_fechamento_eps"]),
            "go_live_aprovado": bool(v["go_live_aprovado"]),
            "dt_go_live": _data(v["dt_go_live"]),
            "mailing_aplicavel": v["mailing_aplicavel"],
            "meta_base": v["meta_base"],
            "meta_eps": v["meta_eps"],
            "escopos": escopos_por_vinculo.get(v["campanha_eps_uuid"], []),
            "status_apuracao": v["status_apuracao"],
            "janela_fim": _data(v["janela_fim"]),
            "ultima_dt_base": _data(v["ultima_dt_base"]),
            "ultima_apuracao": v["ultima_apuracao"],
        })

    return {"quantidade": len(pendentes), "pendentes": pendentes}


# ============================================================
# 2. GRAVAR APURACAO
#
# Substitui a apuracao anterior da mesma campanha x EPS (o
# robo sempre manda o retrato completo), numa unica transacao.
# ============================================================

def registrar_apuracao(codigo_campanha: str, payload: ApuracaoPayload):
    codigo = codigo_campanha.strip().upper()
    agora = _agora()

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            f"""
            SELECT
                m.campaign_uuid,
                m.produto,
                m.tipo_acao,
                m.meta_base,
                ce.meta_eps,
                ce.status_execucao_eps,
                m.dt_fim_prevista,
                ce.go_live_aprovado

            FROM {DATABASE}.campanha_master m

            INNER JOIN {DATABASE}.campanha_eps ce
                ON ce.campaign_uuid = m.campaign_uuid

            WHERE upper(m.codigo_campanha) = ?
              AND ce.eps = ?

            LIMIT 1
            """,
            parameters=[codigo, payload.eps],
        )
        vinculo = cursor.fetchone()

        if not vinculo:
            raise ValueError(f"{codigo} não tem a EPS {payload.eps}.")

        campaign_uuid, produto, tipo_acao, meta_base, meta_eps, status_eps, dt_fim, go_live = vinculo
        dt_fim = _data(dt_fim)

        if not (status_eps or "").strip():
            raise ValueError(
                f"{codigo} / {payload.eps}: a campanha ainda não foi liberada para esta EPS."
            )
        if tipo_acao != "INCENTIVO" and go_live is not True:
            raise ValueError(
                f"{codigo} / {payload.eps}: ação comercial só é apurada depois do go-live da EPS."
            )

        if payload.status_apuracao == "FINAL":
            pode_finalizar = (
                status_eps == "EXECUCAO_FINALIZADA"
                or (tipo_acao == "INCENTIVO" and dt_fim is not None and dt_fim < _hoje())
            )
            if not pode_finalizar:
                raise ValueError(
                    f"{codigo} / {payload.eps}: FINAL só depois da EPS finalizar "
                    "(ação comercial) ou do fim do prazo (incentivo)."
                )

        funil = payload.funil
        base = (meta_base or "").upper()
        meta = float(meta_eps) if meta_eps not in (None, "") else None
        realizado = (
            funil.matriculas if base == "MATRICULAS"
            else funil.vendas if base == "VENDAS"
            else None
        )
        atingimento = (
            round((realizado or 0) / meta * 100, 1)
            if meta and realizado is not None
            else None
        )

        cursor.execute(
            f"SELECT status_apuracao FROM {DATABASE}.apuracao_funil WHERE codigo_campanha = ? AND eps = ?",
            parameters=[codigo, payload.eps],
        )
        anterior = cursor.fetchone()
        status_anterior = anterior[0] if anterior else None

        status_gravado = (
            "FINAL" if status_anterior == "FINAL" else payload.status_apuracao
        )

        for tabela in ("apuracao_funil", "apuracao_serie_diaria", "apuracao_tabulacao"):
            cursor.execute(
                f"DELETE FROM {DATABASE}.{tabela} WHERE codigo_campanha = ? AND eps = ?",
                parameters=[codigo, payload.eps],
            )

        _inserir(cursor, "apuracao_funil", {
            "apuracao_uuid": _uuid(),
            "codigo_campanha": codigo,
            "campaign_uuid": campaign_uuid,
            "eps": payload.eps,
            "produto": produto,
            "tipo_acao": tipo_acao,
            "status_apuracao": status_gravado,
            "periodo_ini": payload.periodo_ini,
            "periodo_fim": payload.periodo_fim,
            "janela_fim": payload.janela_fim,
            "dt_base": payload.dt_base,
            "fonte_funil": payload.fonte_funil,
            "fonte_matricula": payload.fonte_matricula,
            "mailing": funil.mailing,
            "mailing_enviado": funil.mailing_enviado,
            "leads_acionados": funil.leads_acionados,
            "tentativas": funil.tentativas,
            "trabalhados": funil.trabalhados,
            "alo": funil.alo,
            "efetivos": funil.efetivos,
            "vendas": funil.vendas,
            "matriculas": funil.matriculas,
            "alunos": funil.alunos,
            "leads_reacionados": funil.leads_reacionados,
            "faixas_tentativas": json.dumps(payload.faixas_tentativas) if payload.faixas_tentativas else None,
            "meta_base": base or None,
            "meta_eps": meta,
            "atingimento": atingimento,
            "observacao": payload.observacao,
            "dt_apuracao": agora,
        })

        for ponto in payload.serie_diaria:
            _inserir(cursor, "apuracao_serie_diaria", {
                "codigo_campanha": codigo,
                "eps": payload.eps,
                "dia": ponto.dia,
                "tentativas": ponto.tentativas,
                "vendas": ponto.vendas,
                "matriculas": ponto.matriculas,
                "dt_apuracao": agora,
            })

        for linha in payload.tabulacoes:
            _inserir(cursor, "apuracao_tabulacao", {
                "tabulacao_uuid": _uuid(),
                "codigo_campanha": codigo,
                "eps": payload.eps,
                "classificacao": linha.classificacao.strip().upper(),
                "tabulacao_1": linha.tabulacao_1,
                "tabulacao_2": linha.tabulacao_2,
                "tabulacao_3": linha.tabulacao_3,
                "interacoes": linha.interacoes,
                "leads": linha.leads,
                "dt_apuracao": agora,
            })

        _inserir(cursor, "apuracao_execucao", {
            "execucao_uuid": _uuid(),
            "codigo_campanha": codigo,
            "eps": payload.eps,
            "resultado": "OK",
            "mensagem": f"Apuração {status_gravado} gravada.",
            "dt_base": payload.dt_base,
            "duracao_seg": payload.duracao_seg,
            "dt_execucao": agora,
        })

    # Avisos depois do commit, em segundo plano.
    sem_resultado = not (funil.leads_acionados or 0) and not (funil.matriculas or 0)
    if sem_resultado and status_gravado == "FINAL":
        notificar_alerta(
            codigo, payload.eps, "SEM_RESULTADO",
            f"Período {payload.periodo_ini:%d/%m/%Y} a {payload.periodo_fim:%d/%m/%Y}, base de {payload.dt_base:%d/%m/%Y}.",
        )

    if status_gravado == "FINAL" and status_anterior != "FINAL":
        notificar_campanha_apurada(codigo)

    return {
        "codigo_campanha": codigo,
        "eps": payload.eps,
        "status_apuracao": status_gravado,
        "sem_resultado": sem_resultado,
        "atingimento": atingimento,
        "pontos_serie": len(payload.serie_diaria),
        "linhas_tabulacao": len(payload.tabulacoes),
        "dt_apuracao": agora,
    }


# ============================================================
# 3. LOG DE EXECUCAO (pendencia, erro, aguardando base...)
# ============================================================

def registrar_execucao(payload: ExecucaoPayload):
    agora = _agora()

    with get_connection() as connection:
        cursor = connection.cursor()
        _inserir(cursor, "apuracao_execucao", {
            "execucao_uuid": _uuid(),
            "codigo_campanha": (payload.codigo_campanha or "").upper() or None,
            "eps": payload.eps,
            "resultado": payload.resultado,
            "motivo": payload.motivo,
            "mensagem": payload.mensagem,
            "dt_base": payload.dt_base,
            "duracao_seg": payload.duracao_seg,
            "dt_execucao": agora,
        })

    if payload.resultado in ("PENDENCIA", "ERRO"):
        motivo = payload.motivo if payload.motivo in MOTIVOS else (
            "ERRO_PROCESSO" if payload.resultado == "ERRO" else payload.motivo or "ERRO_PROCESSO"
        )
        notificar_alerta(
            (payload.codigo_campanha or "").upper() or None,
            payload.eps,
            motivo,
            payload.mensagem,
        )

    return {"registrado": True, "dt_execucao": agora}


# ============================================================
# 4. LEITURA PARA A ABA DASHBOARD
#
# Devolve tudo de uma vez; os filtros acontecem no navegador,
# como no dashboard de historico.
# ============================================================

def carregar_dashboard_apuracao():
    funil = fetch_all(
        f"""
        SELECT
            af.codigo_campanha, af.eps, af.produto, af.tipo_acao,
            af.status_apuracao, af.periodo_ini, af.periodo_fim, af.janela_fim,
            af.dt_base, af.fonte_funil, af.fonte_matricula,
            af.mailing, af.mailing_enviado, af.leads_acionados, af.tentativas, af.trabalhados,
            af.alo, af.efetivos, af.vendas, af.matriculas, af.alunos,
            af.leads_reacionados, af.faixas_tentativas,
            -- Meta sempre a atual da Central (se o Planejamento corrigir a
            -- meta, o Dashboard reflete na hora, sem esperar o robo).
            COALESCE(m.meta_base, af.meta_base) AS meta_base,
            COALESCE(ce.meta_eps, af.meta_eps) AS meta_eps,
            af.atingimento, af.dt_apuracao,
            m.nome_campanha, m.status_campanha
        FROM {DATABASE}.apuracao_funil af
        LEFT JOIN {DATABASE}.campanha_master m
            ON upper(m.codigo_campanha) = af.codigo_campanha
        LEFT JOIN {DATABASE}.campanha_eps ce
            ON ce.campaign_uuid = m.campaign_uuid
           AND ce.eps = af.eps
        ORDER BY af.periodo_ini DESC, af.codigo_campanha, af.eps
        """
    )

    serie = fetch_all(
        f"""
        SELECT codigo_campanha, eps, dia, tentativas, vendas, matriculas
        FROM {DATABASE}.apuracao_serie_diaria
        ORDER BY dia
        """
    )

    tabulacao = fetch_all(
        f"""
        SELECT codigo_campanha, eps, classificacao,
               tabulacao_1, tabulacao_2, tabulacao_3, interacoes, leads
        FROM {DATABASE}.apuracao_tabulacao
        """
    )

    ultima = fetch_all(
        f"""
        SELECT resultado, mensagem, dt_base, dt_execucao
        FROM {DATABASE}.apuracao_execucao
        ORDER BY dt_execucao DESC
        LIMIT 1
        """
    )

    # Pendencias e erros recentes, para o quadro "Pendencias do
    # robo". So a ocorrencia mais recente de cada campanha x EPS
    # x motivo, para nao repetir a mesma linha a cada hora. Some
    # da lista quando uma apuracao posterior da mesma campanha x
    # EPS da certo.
    pendencias = fetch_all(
        f"""
        SELECT codigo_campanha, eps, resultado, motivo, mensagem, dt_base, dt_execucao
        FROM (
            SELECT
                e.*,
                ROW_NUMBER() OVER (
                    PARTITION BY coalesce(e.codigo_campanha, ''), coalesce(e.eps, ''), coalesce(e.motivo, e.resultado)
                    ORDER BY e.dt_execucao DESC
                ) AS rn
            FROM {DATABASE}.apuracao_execucao e
            WHERE e.resultado IN ('PENDENCIA', 'ERRO')
              AND e.dt_execucao >= ?
        ) t
        WHERE t.rn = 1
          AND NOT EXISTS (
              SELECT 1
              FROM {DATABASE}.apuracao_execucao ok
              WHERE ok.resultado = 'OK'
                AND ok.codigo_campanha = t.codigo_campanha
                AND ok.eps = t.eps
                AND ok.dt_execucao > t.dt_execucao
          )
        ORDER BY t.dt_execucao DESC
        LIMIT 50
        """,
        [datetime.now(timezone.utc) - timedelta(days=7)],
    )

    return {
        "funil": funil,
        "serie_diaria": serie,
        "tabulacao": tabulacao,
        "ultima_execucao": ultima[0] if ultima else None,
        "pendencias": pendencias,
    }


# ============================================================
# 5. ARQUIVOS DO ROBO DA VM
#
# A VM baixa daqui a versao atual do robo (python
# robo_apuracao.py --atualizar). Assim, correcoes chegam pelo
# deploy normal da Central, sem copiar e colar na VM. So a
# pasta app/robo_vm, so .py, e sempre com a chave do robo.
# ============================================================

PASTA_ROBO_VM = Path(__file__).resolve().parent / "robo_vm"


def listar_arquivos_robo():
    if not PASTA_ROBO_VM.is_dir():
        return []
    return sorted(p.name for p in PASTA_ROBO_VM.glob("*.py") if p.is_file())


def ler_arquivo_robo(nome: str):
    if nome not in listar_arquivos_robo():
        raise FileNotFoundError(nome)
    return (PASTA_ROBO_VM / nome).read_text(encoding="utf-8")