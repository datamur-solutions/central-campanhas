"""
ROBO DE APURACAO - roda na VM (usuario de servico)

Uso:
  python robo_apuracao.py               apura tudo o que esta pendente e grava na Central
  python robo_apuracao.py --simular     apura e mostra na tela, sem gravar
  python robo_apuracao.py --ignorar-base   apura com a base disponivel, mesmo sem D-1 (carga manual)
  python robo_apuracao.py --refazer        reapura mesmo o que ja foi apurado com a base atual (apos ajuste de regra)
  python robo_apuracao.py --campanha CAM-009   so uma campanha
  python robo_apuracao.py --login       renova o login do Databricks (abre o navegador)
  python robo_apuracao.py --atualizar   baixa a versao mais nova do robo da Central
  python robo_apuracao.py --salvar-chave  copia a chave do cofre para arquivo (uma vez, antes do --agendar)
  python robo_apuracao.py --agendar     agenda o robo de hora em hora (dias uteis, 7h as 20h), com ou sem usuario conectado

Fluxo de cada rodada:
  1. Pergunta a Central quais campanhas estao em apuracao.
  2. Confere a data base D-1 de cada produto no Databricks.
  3. Carrega mailings novos da pasta mailing (acao comercial).
  4. Apura (mailing x base, ou perfil x periodo no incentivo).
  5. Grava na Central (PARCIAL ou FINAL) ou registra a pendencia,
     que dispara o alerta por e-mail.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

from decimal import Decimal
from datetime import date, datetime, timedelta, timezone

import keyring
import pandas as pd
import requests

from databricks import sql
from databricks.sql.experimental.oauth_persistence import DevOnlyFilePersistence

import regras_campanha as R
from paineis_eps import Paineis


# ===================== CONFIGURACAO =====================
PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_LOG = os.path.join(PASTA, "logs")
PASTA_TMP = os.path.join(PASTA, "tmp")
TOKEN_DBX = os.path.join(PASTA, "dbx_token.json")
TOKEN_ANTIGO = os.path.expanduser(r"~\teste_vm\dbx_token.json")
# Copia da chave do robo em arquivo: o agendamento roda sem senha do usuario
# (logon S4U) e, nesse modo, o Windows nao abre o cofre (keyring).
CHAVE_ARQ = os.path.join(PASTA, "chave_robo.txt")

CENTRAL = os.getenv("CENTRAL", "https://central-campanhas.example.com")
DBX_HOST = os.getenv("DBX_HOST", "dbc-xxxxxxxx-xxxx.cloud.databricks.com")
DBX_HTTP_PATH = os.getenv("DBX_HTTP_PATH", "/sql/1.0/warehouses/xxxxxxxxxxxxxxxx")
VOLUME = os.getenv("VOLUME", "/Volumes/lakehouse/comercial/arquivos")
TAB_MAILING = os.getenv("TAB_MAILING", "lakehouse.comercial.tb_mailing_campanha")
TAB_APURACAO = os.getenv("TAB_APURACAO", "lakehouse.comercial.tb_apuracao_campanha")
TAB_DETALHE = os.getenv("TAB_DETALHE", "lakehouse.comercial.tb_apuracao_campanha_detalhe")
SCHEMA_CENTRAL = os.getenv("SCHEMA_CENTRAL", "lakehouse.comercial")

# Pecas da ultima apuracao de cada campanha x EPS, para gravar o
# detalhe CPF a CPF no Databricks depois que a Central aceita.
DETALHE = {}

FUSO = timezone(timedelta(hours=-3))
HORA_ALERTA_BASE = 18          # depois disso, base atrasada vira alerta
LIMITE_RODADA_MIN = 45         # trava de seguranca da rodada

os.makedirs(PASTA_LOG, exist_ok=True)
os.makedirs(PASTA_TMP, exist_ok=True)


# ===================== LOG =====================
def log(msg):
    linha = f"{datetime.now(FUSO):%Y-%m-%d %H:%M:%S} | {msg}"
    print(linha, flush=True)
    with open(os.path.join(PASTA_LOG, f"robo_{datetime.now(FUSO):%Y-%m-%d}.log"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def hoje():
    return datetime.now(FUSO).date()


def iso(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return int(v) if v == int(v) else float(v)
    return v


def para_data(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


# ===================== CENTRAL =====================
class Central:
    def __init__(self):
        chave = None
        try:
            chave = keyring.get_password("central_robo", "robo")
        except Exception:
            chave = None  # agendamento sem senha: cofre indisponivel
        if not chave and os.path.exists(CHAVE_ARQ):
            with open(CHAVE_ARQ, encoding="utf-8") as f:
                chave = f.read().strip()
        if not chave:
            raise RuntimeError("Chave do robô não encontrada (cofre central_robo/robo nem chave_robo.txt). "
                               "Rode uma vez, logado: python robo_apuracao.py --salvar-chave")
        self.s = requests.Session()
        self.s.headers.update({"X-Robo-Key": chave})

    def acordar(self):
        for tentativa in range(12):
            try:
                if self.s.get(f"{CENTRAL}/health", timeout=30).status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(15)
        raise RuntimeError("A Central não respondeu em 3 minutos.")

    def pendentes(self):
        r = self.s.get(f"{CENTRAL}/api/robo/pendentes", timeout=120)
        r.raise_for_status()
        return r.json().get("pendentes", [])

    def gravar(self, codigo, payload):
        r = self.s.post(f"{CENTRAL}/api/robo/apuracao/{codigo}", data=json.dumps(payload, default=iso),
                        headers={"Content-Type": "application/json"}, timeout=180)
        if r.status_code >= 400:
            raise RuntimeError(f"Central recusou a apuração ({r.status_code}): {r.text[:300]}")
        return r.json()

    def execucao(self, resultado, codigo=None, eps=None, motivo=None, mensagem=None, dt_base=None, duracao=None):
        try:
            self.s.post(f"{CENTRAL}/api/robo/execucao", data=json.dumps({
                "codigo_campanha": codigo, "eps": eps, "resultado": resultado, "motivo": motivo,
                "mensagem": (mensagem or "")[:1900] or None, "dt_base": dt_base, "duracao_seg": duracao,
            }, default=iso), headers={"Content-Type": "application/json"}, timeout=120)
        except Exception as erro:
            log(f"   (nao consegui registrar a execucao na Central: {erro})")


# ===================== DATABRICKS =====================
def conectar_databricks(interativo=False):
    if not os.path.exists(TOKEN_DBX) and os.path.exists(TOKEN_ANTIGO):
        shutil.copy(TOKEN_ANTIGO, TOKEN_DBX)

    if not interativo and not os.path.exists(TOKEN_DBX):
        raise PermissionError("Login do Databricks não encontrado. Rode: python robo_apuracao.py --login")

    return sql.connect(
        server_hostname=DBX_HOST,
        http_path=DBX_HTTP_PATH,
        auth_type="databricks-oauth",
        experimental_oauth_persistence=DevOnlyFilePersistence(TOKEN_DBX),
        staging_allowed_local_path=PASTA_TMP.replace("\\", "/"),
    )


def consultar(cur, query, params=None):
    if params:
        cur.execute(query, params)
    else:
        cur.execute(query)
    if cur.description is None:
        return []
    nomes = [c[0] for c in cur.description]
    return [dict(zip(nomes, linha)) for linha in cur.fetchall()]


def data_base(cur, produto, cache, p):
    r = R.regra_campanha(produto, p)
    chave = (r["tabela"], r["col_dt_base"])
    if chave not in cache:
        linha = consultar(cur, f"SELECT MAX({r['col_dt_base']}) AS dt FROM {r['tabela']}")
        cache[chave] = para_data(linha[0]["dt"]) if linha else None
    return cache[chave]


# ===================== MAILINGS =====================
def preparar_tabela_mailing(cur):
    cur.execute(f"""CREATE TABLE IF NOT EXISTS {TAB_MAILING} (campanha_id STRING, eps STRING, cpf STRING, cpf_hash STRING,
                    data_mailing DATE, arquivo STRING, carregado_em TIMESTAMP)""")
    # Padroniza a EPS de cargas antigas (JA, LUMEN...) para o codigo da Central.
    cur.execute(f"""
        UPDATE {TAB_MAILING}
        SET eps = CASE
            WHEN UPPER(eps) LIKE 'JA%' THEN 'VOXA'
            WHEN UPPER(eps) LIKE 'LUMEN%' THEN 'LUMEN'
            WHEN UPPER(eps) LIKE 'PRISMA%' THEN 'PRISMA'
            ELSE '' END
        WHERE eps IS NOT NULL AND eps NOT IN ('VOXA', 'LUMEN', 'PRISMA', '')""")


def arquivos_mailing(cur):
    """{CAM-xxx: (nome_arquivo, modificado_em_ms)} - o mais recente de cada campanha."""
    arquivos = {}
    for linha in consultar(cur, f"LIST '{VOLUME}/mailing'"):
        nome = linha.get("name") or str(linha.get("path", "")).rstrip("/").split("/")[-1]
        cam = R.extrair_cam(nome)
        if not cam or not nome.lower().endswith((".csv", ".xlsx", ".xls")):
            continue
        mod = int(linha.get("modification_time") or 0)
        if cam not in arquivos or mod > arquivos[cam][1]:
            arquivos[cam] = (nome, mod)
    return arquivos


def _coluna(df, *candidatos):
    mapa = {re.sub(r"[^A-Z]", "", c.upper()): c for c in df.columns}
    for cand in candidatos:
        if re.sub(r"[^A-Z]", "", cand.upper()) in mapa:
            return mapa[re.sub(r"[^A-Z]", "", cand.upper())]
    return None


def _cpf(valor):
    txt = str(valor or "").strip()
    if re.fullmatch(r"\d+\.0", txt):
        txt = txt[:-2]
    dig = re.sub(r"\D", "", txt)
    return dig.zfill(11) if 0 < len(dig) <= 11 else ""


def carregar_mailing(cur, cam, nome, modificado_ms):
    """Carrega o arquivo na cc_mailing se ele for mais novo que a ultima carga dessa campanha."""
    ultima = consultar(cur, f"SELECT MAX(carregado_em) AS ult FROM {TAB_MAILING} WHERE campanha_id = :cam", {"cam": cam})
    ult = ultima[0]["ult"] if ultima else None
    if ult is not None:
        ult_ms = ult.replace(tzinfo=ult.tzinfo or timezone.utc).timestamp() * 1000
        if ult_ms >= modificado_ms:
            return False

    log(f"   carregando mailing {nome} ...")
    local = os.path.join(PASTA_TMP, nome).replace("\\", "/")
    if os.path.exists(local):
        os.remove(local)
    cur.execute(f"GET '{VOLUME}/mailing/{nome}' TO '{local}'")

    df = pd.read_excel(local, dtype=str) if nome.lower().endswith((".xlsx", ".xls")) else pd.read_csv(local, dtype=str, sep=None, engine="python")
    col_cpf = _coluna(df, "CVECPF", "CPF", "NR_CPF", "ALUNO_CPF", "CPF_S_PONT")
    if not col_cpf:
        raise ValueError(f"O arquivo {nome} não tem coluna de CPF.")
    col_eps = _coluna(df, "EPS")

    saida = pd.DataFrame({
        "campanha_id": cam,
        "eps": df[col_eps].map(R.normalizar_eps) if col_eps else "",
        "cpf": df[col_cpf].map(_cpf),
        "arquivo": nome,
    })
    saida = saida[saida["cpf"] != ""].drop_duplicates(["eps", "cpf"])

    csv = os.path.join(PASTA_TMP, f"carga_{cam}.csv").replace("\\", "/")
    saida.to_csv(csv, sep=";", index=False)
    cur.execute(f"PUT '{csv}' INTO '{VOLUME}/_carga/carga_{cam}.csv' OVERWRITE")
    cur.execute(f"DELETE FROM {TAB_MAILING} WHERE campanha_id = :cam", {"cam": cam})
    cur.execute(f"""
        INSERT INTO {TAB_MAILING}
        SELECT campanha_id, eps, cpf,
               LOWER(SHA2(CONCAT(SUBSTR(cpf,1,3),'.',SUBSTR(cpf,4,3),'.',SUBSTR(cpf,7,3),'-',SUBSTR(cpf,10,2)),256)),
               CAST(NULL AS DATE), arquivo, current_timestamp()
        FROM read_files('{VOLUME}/_carga/carga_{cam}.csv', format => 'csv', header => true, sep => ';',
             schema => 'campanha_id STRING, eps STRING, cpf STRING, arquivo STRING')""")
    os.remove(local)
    log(f"   mailing {cam}: {len(saida)} leads carregados")
    return True


# ===================== APURACAO NO DATABRICKS =====================
# Cada apuracao gravada na Central tambem vai para o Databricks:
#   1. tabela lakehouse.comercial.tb_apuracao_campanha (uma linha por
#      campanha x EPS, sempre o retrato mais recente);
#   2. arquivo apuracao/apuracao_CAM-xxx.csv no volume, com todas as
#      EPS da campanha.
# Falha aqui nao derruba a apuracao: so registra no log.
COLUNAS_APURACAO = [
    ("campanha_id", "STRING"), ("nome_campanha", "STRING"), ("eps", "STRING"), ("tipo_acao", "STRING"),
    ("produtos", "STRING"), ("status_apuracao", "STRING"), ("periodo_ini", "DATE"), ("periodo_fim", "DATE"),
    ("dt_base", "DATE"), ("mailing_enviado", "BIGINT"), ("mailing", "BIGINT"), ("trabalhados", "BIGINT"),
    ("tentativas", "BIGINT"), ("atendidos", "BIGINT"), ("efetivos", "BIGINT"), ("vendas", "BIGINT"),
    ("matriculas", "BIGINT"), ("meta_base", "STRING"), ("meta_eps", "BIGINT"), ("atingimento_pct", "DOUBLE"),
    ("fonte_funil", "STRING"), ("observacao", "STRING"), ("apurado_em", "TIMESTAMP"),
]


def preparar_tabela_apuracao(cur):
    colunas = ", ".join(f"{c} {t}" for c, t in COLUNAS_APURACAO)
    cur.execute(f"CREATE TABLE IF NOT EXISTS {TAB_APURACAO} ({colunas})")


def gravar_apuracao_databricks(cur, p, payload):
    f = payload["funil"]
    meta = p.get("meta_eps")
    base_meta = p.get("meta_base")
    real = f.get("vendas") if base_meta == "VENDAS" else f.get("matriculas")
    linha = {
        "campanha_id": p["codigo_campanha"],
        "nome_campanha": p.get("nome_campanha"),
        "eps": p["eps"],
        "tipo_acao": p.get("tipo_acao"),
        "produtos": ", ".join(sorted({str(e.get("produto")) for e in (p.get("escopos") or []) if e.get("produto")})),
        "status_apuracao": payload["status_apuracao"],
        "periodo_ini": payload["periodo_ini"],
        "periodo_fim": payload["periodo_fim"],
        "dt_base": payload["dt_base"],
        "mailing_enviado": f.get("mailing_enviado"),
        "mailing": f.get("mailing"),
        "trabalhados": f.get("trabalhados"),
        "tentativas": f.get("tentativas"),
        "atendidos": f.get("alo"),
        "efetivos": f.get("efetivos"),
        "vendas": f.get("vendas"),
        "matriculas": f.get("matriculas"),
        "meta_base": base_meta,
        "meta_eps": int(meta) if meta else None,
        "atingimento_pct": round(float(real or 0) / float(meta) * 100, 1) if meta else None,
        "fonte_funil": payload.get("fonte_funil"),
        "observacao": (payload.get("observacao") or "")[:1900],
        "apurado_em": datetime.now(timezone.utc).replace(tzinfo=None),
    }

    cur.execute(f"DELETE FROM {TAB_APURACAO} WHERE campanha_id = :cam AND eps = :eps",
                {"cam": linha["campanha_id"], "eps": linha["eps"]})
    valores = ", ".join(f"CAST(:{c} AS {t})" for c, t in COLUNAS_APURACAO)
    cur.execute(f"INSERT INTO {TAB_APURACAO} SELECT {valores}",
                {c: (iso(v) if isinstance(v, (date, datetime)) else v) for c, v in linha.items()})

    # Arquivo da campanha, com todas as EPS.
    linhas = consultar(cur, f"SELECT * FROM {TAB_APURACAO} WHERE campanha_id = :cam ORDER BY eps",
                       {"cam": linha["campanha_id"]})
    arquivo = os.path.join(PASTA_TMP, f"apuracao_{linha['campanha_id']}.csv").replace("\\", "/")
    pd.DataFrame(linhas).to_csv(arquivo, sep=";", index=False, encoding="utf-8-sig")
    cur.execute(f"PUT '{arquivo}' INTO '{VOLUME}/apuracao/apuracao_{linha['campanha_id']}.csv' OVERWRITE")
    os.remove(arquivo)


# ===================== DETALHE CPF A CPF + VIEW POR CAMPANHA =====================
# Para investigar um resultado: uma linha por CPF (por campanha, EPS e
# produto), com as mesmas regras do funil. Cada campanha ganha a sua
# view: lakehouse.comercial.apuracao_cam_021, por exemplo.
COLUNAS_DETALHE = [
    ("campanha_id", "STRING"), ("eps", "STRING"), ("produto", "STRING"), ("cpf", "STRING"), ("cpf_hash", "STRING"),
    ("no_mailing", "BOOLEAN"), ("inscricoes", "BIGINT"), ("tentativas", "BIGINT"),
    ("trabalhado", "INT"), ("atendido", "INT"), ("efetivo", "INT"), ("venda", "INT"), ("matricula", "INT"),
    ("venda_tabulada", "INT"), ("vendas_oficiais", "BIGINT"), ("matriculas_oficiais", "BIGINT"),
    ("primeira_tentativa", "DATE"), ("ultima_tentativa", "DATE"),
    ("ultima_tabulacao_2", "STRING"), ("ultima_tabulacao_3", "STRING"),
    ("data_venda", "DATE"), ("data_matricula", "DATE"), ("apurado_em", "TIMESTAMP"),
]


def preparar_tabela_detalhe(cur):
    colunas = ", ".join(f"{c} {t}" for c, t in COLUNAS_DETALHE)
    cur.execute(f"CREATE TABLE IF NOT EXISTS {TAB_DETALHE} ({colunas})")


def _sql_detalhe(produto, peca):
    """SELECT de uma linha por CPF para um produto da campanha x EPS."""
    tab2 = R.SEM_ACENTO
    inter = peca.get("interacao")
    cpf_norm = "LPAD(REGEXP_REPLACE(COALESCE(CAST({c} AS STRING), ''), '[^0-9]', ''), 11, '0')"
    ctes, chaves, juntas = [], [], []

    if inter:
        efetivo = inter["efetivo"]
        mat_ok = "1 = 1"  # matricula com esteira, como no funil
        prefixo = inter["base"].strip()
        ctes.append(f"""
          agg AS (
            SELECT CPF_HASH_CALLCENTER AS h,
                   MAX({cpf_norm.format(c='CPF')}) AS cpf,
                   COUNT(DISTINCT CHAVE_INSCRICAO) AS inscricoes,
                   COALESCE(SUM(FLAG_TENTATIVA), 0) AS tentativas,
                   MAX(CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_TRABALHADO)} THEN 1 ELSE 0 END) AS trabalhado,
                   MAX(CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_ATENDIDO)} THEN 1 ELSE 0 END) AS atendido,
                   MAX(CASE WHEN {efetivo} THEN 1 ELSE 0 END) AS efetivo,
                   MAX(CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_VENDA)} THEN 1 ELSE 0 END) AS venda_tab,
                   {"MAX(CASE WHEN MAT_LIQ_ATRIBUIDA_CALLCENTER = 1 AND " + mat_ok + " THEN 1 ELSE 0 END)" if inter["com_matricula"] else "0"} AS matricula_tab,
                   MIN(CAST(DATA_REFERENCIA AS DATE)) AS primeira,
                   MAX(CAST(DATA_REFERENCIA AS DATE)) AS ultima,
                   MAX_BY(TABULACAO_HUMANA_2, DATA_ACEITE_CALL_CENTER) AS tab2_ult,
                   MAX_BY(TABULACAO_HUMANA_3, DATA_ACEITE_CALL_CENTER) AS tab3_ult,
                   MIN(CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_VENDA)} THEN CAST(DATA_REFERENCIA AS DATE) END) AS data_venda_tab,
                   {"MIN(CASE WHEN MAT_LIQ_ATRIBUIDA_CALLCENTER = 1 AND " + mat_ok + " THEN CAST(COALESCE(DATA_MATRICULA, DATA_MATRICULA_CPF) AS DATE) END)" if inter["com_matricula"] else "CAST(NULL AS DATE)"} AS data_mat_tab
            FROM b
            WHERE CHAVE_INSCRICAO IS NOT NULL
            GROUP BY CPF_HASH_CALLCENTER
          )""")
        chaves.append("SELECT h FROM agg")
        juntas.append("LEFT JOIN agg ON agg.h = k.h")
    else:
        prefixo = "WITH"

    if peca.get("venda_sql"):
        h_of = R.hash_cpf_sql("v.aluno_cpf")
        ctes.append(f"""
          ov AS (
            SELECT {h_of} AS h, MAX({cpf_norm.format(c='v.aluno_cpf')}) AS cpf,
                   COUNT(DISTINCT v.matricula_id) AS vendas, MIN(CAST(v.dt_inscricao AS DATE)) AS data_venda
            FROM ({peca['venda_sql']}) v
            GROUP BY 1
          ),
          om AS (
            SELECT {h_of} AS h, MAX({cpf_norm.format(c='v.aluno_cpf')}) AS cpf,
                   COUNT(DISTINCT v.matricula_id) AS matriculas, MIN(CAST(v.dt_pma_conf AS DATE)) AS data_matricula
            FROM ({peca['mat_sql']}) v
            GROUP BY 1
          )""")
        chaves += ["SELECT h FROM ov", "SELECT h FROM om"]
        juntas += ["LEFT JOIN ov ON ov.h = k.h", "LEFT JOIN om ON om.h = k.h"]

    if peca.get("usa_mailing"):
        ctes.append(f"""
          mail AS (
            SELECT cpf_hash AS h, MAX(cpf) AS cpf FROM {TAB_MAILING}
            WHERE campanha_id = :cam AND (eps = :eps_c OR eps = '' OR eps IS NULL)
            GROUP BY cpf_hash
          )""")
        chaves.append("SELECT h FROM mail")
        juntas.append("LEFT JOIN mail ON mail.h = k.h")

    tem = lambda nome: any(j.startswith(f"LEFT JOIN {nome} ") for j in juntas)
    col = lambda nome, c, padrao="NULL": f"{nome}.{c}" if tem(nome) else padrao
    vendas_of = f"COALESCE({col('ov', 'vendas', '0')}, 0)"
    mats_of = f"COALESCE({col('om', 'matriculas', '0')}, 0)"
    venda_tab = f"COALESCE({col('agg', 'venda_tab', '0')}, 0)"
    venda = f"CASE WHEN {vendas_of} > 0 THEN 1 ELSE 0 END" if peca.get("venda_sql") else venda_tab
    matricula = (f"CASE WHEN {mats_of} > 0 THEN 1 ELSE 0 END" if peca.get("mat_sql")
                 else f"COALESCE({col('agg', 'matricula_tab', '0')}, 0)")
    etapa = lambda c: f"GREATEST(COALESCE({col('agg', c, '0')}, 0), {venda})"
    cpf = "COALESCE(" + ", ".join([col(n, "cpf") for n in ("mail", "agg", "ov", "om") if tem(n)] + ["NULL"]) + ")"

    sep = "," if inter else ""
    return f"""
      {prefixo}{sep}
      {",".join(ctes)},
      k AS ({" UNION ".join(chaves)})
      SELECT
        :cam AS campanha_id, :eps_c AS eps, '{produto}' AS produto,
        {cpf} AS cpf, k.h AS cpf_hash,
        {"mail.h IS NOT NULL" if tem("mail") else "FALSE"} AS no_mailing,
        COALESCE({col('agg', 'inscricoes', '0')}, 0) AS inscricoes,
        COALESCE({col('agg', 'tentativas', '0')}, 0) AS tentativas,
        {etapa('trabalhado')} AS trabalhado,
        {etapa('atendido')} AS atendido,
        {etapa('efetivo')} AS efetivo,
        {venda} AS venda,
        {matricula} AS matricula,
        {venda_tab} AS venda_tabulada,
        {vendas_of} AS vendas_oficiais,
        {mats_of} AS matriculas_oficiais,
        {col('agg', 'primeira')} AS primeira_tentativa,
        {col('agg', 'ultima')} AS ultima_tentativa,
        {col('agg', 'tab2_ult')} AS ultima_tabulacao_2,
        {col('agg', 'tab3_ult')} AS ultima_tabulacao_3,
        COALESCE({col('ov', 'data_venda')}, {col('agg', 'data_venda_tab')}) AS data_venda,
        COALESCE({col('om', 'data_matricula')}, {col('agg', 'data_mat_tab')}) AS data_matricula,
        current_timestamp() AS apurado_em
      FROM k
      {" ".join(juntas)}
      WHERE k.h IS NOT NULL"""


def nome_view_campanha(cam):
    return f"{SCHEMA_CENTRAL}.apuracao_" + re.sub(r"[^a-z0-9]", "_", cam.lower())


def gravar_detalhe_databricks(cur, p, detalhes):
    cam, eps = p["codigo_campanha"], p["eps"]
    cur.execute(f"DELETE FROM {TAB_DETALHE} WHERE campanha_id = :cam AND eps = :eps",
                {"cam": cam, "eps": eps})
    total = 0
    for peca in detalhes:
        params = {}
        if peca.get("mat_params"):
            params.update(peca["mat_params"])
        if peca.get("interacao"):
            params.update(peca["interacao"]["params"])
        params["fim_v"] = params.get("fim")
        params.update({"cam": cam, "eps_c": eps})
        cur.execute(f"INSERT INTO {TAB_DETALHE} SELECT * FROM ({_sql_detalhe(peca['produto'], peca)})", params)
        total += 1

    view = nome_view_campanha(cam)
    cur.execute(f"""
        CREATE OR REPLACE VIEW {view} AS
        SELECT a.status_apuracao, a.periodo_ini, a.periodo_fim, a.dt_base, d.*
        FROM {TAB_DETALHE} d
        LEFT JOIN {TAB_APURACAO} a ON a.campanha_id = d.campanha_id AND a.eps = d.eps
        WHERE d.campanha_id = '{cam}'""")
    return view


# ===================== PERIODO E STATUS =====================
def periodo_e_status(p, dt_base):
    """Devolve (ini, fim_campanha, fim_dados, status, janela_fim) da campanha x EPS."""
    ini = para_data(p["dt_inicio_prevista"])
    # Acao comercial: o go-live e o que libera a apuracao, mas a data do
    # clique na Central nao corta o periodo. Se a EPS registrou o go-live
    # depois do inicio (as vezes ja tendo executado), apura desde o inicio
    # previsto. So antecipa se o go-live foi antes do inicio.
    if p.get("tipo_acao") != "INCENTIVO" and p.get("dt_go_live"):
        go_live = para_data(p["dt_go_live"])
        if go_live and (ini is None or go_live < ini):
            ini = go_live
    fim_prev = para_data(p["dt_fim_prevista"]) or dt_base
    finalizada = p.get("status_execucao_eps") == "EXECUCAO_FINALIZADA"

    if p.get("tipo_acao") == "INCENTIVO":
        fim = fim_prev
        final = dt_base >= fim and hoje() > fim
    elif finalizada:
        fim = para_data(p.get("dt_finalizacao_eps")) or fim_prev
        final = dt_base >= fim
    else:
        fim = max(fim_prev, dt_base)  # acao comercial em andamento: segue ate a EPS finalizar
        final = False

    fim = max(fim, ini)
    fim_dados = max(min(fim, dt_base), ini)
    janela_fim = fim + timedelta(days=R.JANELA_MATRICULA_DIAS)
    return ini, fim, fim_dados, ("FINAL" if final else "PARCIAL"), janela_fim


def outras_campanhas_sql(p, pendentes):
    """Campanhas mais antigas, com mailing, mesma EPS e periodo sobreposto: o CPF fica com elas."""
    ini = para_data(p["dt_inicio_prevista"])
    fim = para_data(p["dt_fim_prevista"]) or hoje()
    linhas = []
    for o in pendentes:
        if o["codigo_campanha"] == p["codigo_campanha"] or o["eps"] != p["eps"] or not o.get("mailing_aplicavel"):
            continue
        o_ini = para_data(o["dt_inicio_prevista"])
        o_fim = para_data(o["dt_fim_prevista"]) or hoje()
        mais_antiga = (o_ini, o["codigo_campanha"]) < (ini, p["codigo_campanha"])
        if mais_antiga and o_ini <= fim and o_fim >= ini and re.fullmatch(r"CAM-\d+", o["codigo_campanha"]):
            linhas.append(f"('{o['codigo_campanha']}', DATE '{o_ini}', DATE '{o_fim}')")
    if not linhas:
        return "SELECT CAST(NULL AS STRING) AS cam, CAST(NULL AS DATE) AS ini, CAST(NULL AS DATE) AS fim WHERE 1 = 0"
    return "SELECT * FROM VALUES " + ", ".join(linhas) + " AS t(cam, ini, fim)"


# ===================== APURACAO: GRADUACAO / TECNICO =====================
def apurar_interacao(cur, produto, escopos, p, usa_mailing, ini, fim_dados, outras_sql, r=None, com_matricula=True,
                     venda_sql=None):
    """
    Funil padrao sobre uma base de interacoes.
    r: regra alternativa (funil de Pos/Prof); com_matricula=False quando a
    matricula vem de outra fonte (tabela oficial). Devolve None se a EPS
    nao tem interacoes nessa base (ex.: Prisma).
    """
    if r is None:
        r = R.regra_campanha(produto, p)
        eps_b = R.eps_base(produto, p["eps"])
    else:
        eps_b = r["eps"].get(p["eps"])
        if not eps_b:
            return None
    fixo = r.get("filtro_fixo", "1=1")
    params = {"eps": eps_b, "eps_c": p["eps"], "cam": p["codigo_campanha"], "ini": ini, "fim": fim_dados}

    if usa_mailing:
        base = f"""
          WITH m AS (
            SELECT DISTINCT cpf_hash FROM {TAB_MAILING}
            WHERE campanha_id = :cam AND (eps = :eps_c OR eps = '' OR eps IS NULL)
          ),
          outras AS ({outras_sql}),
          excl AS (
            SELECT DISTINCT mm.cpf_hash, o.ini, o.fim
            FROM outras o JOIN {TAB_MAILING} mm
              ON mm.campanha_id = o.cam AND (mm.eps = :eps_c OR mm.eps = '' OR mm.eps IS NULL)
          ),
          b AS (
            SELECT b.* FROM {r['tabela']} b
            JOIN m ON b.CPF_HASH_CALLCENTER = m.cpf_hash
            WHERE b.EPS = :eps AND b.DATA_REFERENCIA BETWEEN :ini AND :fim AND {fixo}
              AND NOT EXISTS (SELECT 1 FROM excl e WHERE e.cpf_hash = b.CPF_HASH_CALLCENTER
                              AND b.DATA_REFERENCIA BETWEEN e.ini AND e.fim)
          )"""
    else:
        filtro = R.filtro_escopos(produto, escopos, r)
        base = f"""
          WITH b AS (
            SELECT b.* FROM {r['tabela']} b
            WHERE b.EPS = :eps AND b.DATA_REFERENCIA BETWEEN :ini AND :fim AND {fixo} AND {filtro}
          )"""

    # Funil padrao (mesmas regras do painel Power BI, em regras_campanha.py)
    tab2 = R.SEM_ACENTO
    # Venda tambem e efetivo (e, pelas listas, atendido e trabalhado).
    efetivo = f"(({R.EFETIVO_POR_EPS.get(p['eps'], '1 = 0')}) OR {tab2} IN {R.lista_sql(R.STATUS_VENDA)})"
    funil = consultar(cur, base + f"""
        SELECT COUNT(DISTINCT CHAVE_INSCRICAO) AS mailing,
               COUNT(DISTINCT CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_TRABALHADO)} THEN CHAVE_INSCRICAO END) AS trabalhados,
               COALESCE(SUM(FLAG_TENTATIVA), 0) AS tentativas,
               COUNT(DISTINCT CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_ATENDIDO)} THEN CHAVE_INSCRICAO END) AS alo,
               COUNT(DISTINCT CASE WHEN {efetivo} THEN CHAVE_INSCRICAO END) AS efetivos,
               COUNT(DISTINCT CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_VENDA)} THEN CHAVE_INSCRICAO END) AS vendas,
               COALESCE(SUM(MAT_LIQ_ATRIBUIDA_CALLCENTER), 0) AS matriculas
        FROM b
        WHERE CHAVE_INSCRICAO IS NOT NULL""", params)[0]

    # Efetivo limitado como no painel (JA <= atendidos; Lumen <= atendidos e mailing)
    campo = {"atendidos": "alo", "mailing": "mailing"}
    limites = [int(funil.get(campo[k]) or 0) for k in R.EFETIVO_LIMITES.get(p["eps"], ())]
    if limites:
        funil["efetivos"] = min([int(funil.get("efetivos") or 0)] + limites)
    funil["leads_acionados"] = funil["mailing"]
    if not com_matricula:
        funil.pop("matriculas", None)

    # Pos/Prof: a venda vem da tabela oficial. Cada etapa (trabalhados,
    # atendidos, efetivos) = inscricoes da etapa cujo CPF NAO vendeu
    # + vendas oficiais. Tentativas ganham 1 por venda sem nenhuma
    # interacao no periodo. Mailing nao muda.
    if venda_sql:
        pv = {**params, "fim_v": fim_dados}
        vo = f""",
          vo AS (SELECT DISTINCT {R.hash_cpf_sql('v.aluno_cpf')} AS h FROM ({venda_sql}) v)"""
        sem = consultar(cur, base + vo + f"""
          SELECT
            COUNT(DISTINCT CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_TRABALHADO)} THEN b.CHAVE_INSCRICAO END) AS trabalhados,
            COUNT(DISTINCT CASE WHEN {tab2} IN {R.lista_sql(R.STATUS_ATENDIDO)} THEN b.CHAVE_INSCRICAO END) AS alo,
            COUNT(DISTINCT CASE WHEN {efetivo} THEN b.CHAVE_INSCRICAO END) AS efetivos
          FROM b LEFT ANTI JOIN vo ON b.CPF_HASH_CALLCENTER = vo.h
          WHERE b.CHAVE_INSCRICAO IS NOT NULL""", pv)[0]
        sem["vendas_sem_interacao"] = consultar(cur, base + f""",
          bb AS (SELECT DISTINCT CPF_HASH_CALLCENTER AS h FROM b)
          SELECT COUNT(DISTINCT v.matricula_id) AS n
          FROM ({venda_sql}) v
          LEFT ANTI JOIN bb ON {R.hash_cpf_sql('v.aluno_cpf')} = bb.h""", pv)[0]["n"]
        funil["_sem_venda"] = sem

    if usa_mailing:
        funil["mailing_enviado"] = consultar(cur, f"""SELECT COUNT(DISTINCT cpf_hash) AS n FROM {TAB_MAILING}
            WHERE campanha_id = :cam AND (eps = :eps_c OR eps = '' OR eps IS NULL)""", params)[0]["n"]

    # Quantas vezes cada inscricao foi tentada (reacionamento)
    faixas = consultar(cur, base + """
        SELECT CASE WHEN n = 1 THEN '1' WHEN n = 2 THEN '2' WHEN n = 3 THEN '3'
                    WHEN n <= 5 THEN '4-5' WHEN n <= 10 THEN '6-10' ELSE '11+' END AS faixa,
               COUNT(*) AS leads
        FROM (SELECT CHAVE_INSCRICAO, SUM(FLAG_TENTATIVA) AS n FROM b
              WHERE CHAVE_INSCRICAO IS NOT NULL GROUP BY CHAVE_INSCRICAO) t
        WHERE n > 0
        GROUP BY 1""", params)
    funil["_faixas"] = {l["faixa"]: int(l["leads"]) for l in faixas}
    funil["leads_reacionados"] = sum(v for k, v in funil["_faixas"].items() if k != "1")

    serie_mat = """
        UNION ALL
        SELECT CAST(COALESCE(DATA_MATRICULA, DATA_MATRICULA_CPF) AS DATE) AS dia, 0, 0,
               SUM(MAT_LIQ_ATRIBUIDA_CALLCENTER)
        FROM b WHERE MAT_LIQ_ATRIBUIDA_CALLCENTER = 1
        GROUP BY CAST(COALESCE(DATA_MATRICULA, DATA_MATRICULA_CPF) AS DATE)""" if com_matricula else ""
    serie = consultar(cur, base + """
        SELECT CAST(DATA_REFERENCIA AS DATE) AS dia, COUNT(*) AS tentativas,
               COUNT(DISTINCT CASE WHEN VENDAS_CALLCENTER = 1 THEN CPF_HASH_CALLCENTER END) AS vendas,
               0 AS matriculas
        FROM b GROUP BY CAST(DATA_REFERENCIA AS DATE)""" + serie_mat, params)

    tab = consultar(cur, base + """
        SELECT COALESCE(CLASSIFICACAO_TABULACAO, 'OUTROS') AS classificacao,
               TABULACAO_HUMANA_1 AS tabulacao_1, TABULACAO_HUMANA_2 AS tabulacao_2, TABULACAO_HUMANA_3 AS tabulacao_3,
               COUNT(*) AS interacoes, COUNT(DISTINCT CPF_HASH_CALLCENTER) AS leads
        FROM b GROUP BY 1, 2, 3, 4
        ORDER BY interacoes DESC LIMIT 4000""", params)

    funil["_det"] = {"base": base, "params": params, "efetivo": efetivo, "com_matricula": com_matricula,
                     "usa_mailing": usa_mailing}
    return funil, serie, tab


# ===================== APURACAO: POS / PROFISSIONALIZANTES =====================
def apurar_matricula(cur, produto, escopos, p, usa_mailing, ini, fim_mat, outras_sql, fim_venda=None):
    """
    Pos/Prof na tabela oficial:
      matriculas = fl_pma_conf = 1 por dt_pma_conf (periodo + esteira)
      vendas     = toda linha marcada com a EPS por dt_inscricao (periodo da
                   campanha), com ou sem matricula.
    """
    r = R.regra(produto)
    fim_venda = fim_venda or fim_mat
    params = {"eps_c": p["eps"], "cam": p["codigo_campanha"], "ini": ini, "fim": fim_mat, "fim_v": fim_venda}
    filtro = f"({r['filtro_produto']})" if usa_mailing else R.filtro_escopos(produto, escopos)

    def montar(col_data, fim_param, extra=""):
        cond_eps = R.cond_eps_matricula(produto, p["eps"], col_data)
        publico = ""
        if usa_mailing:
            publico = f"""
          AND b.aluno_cpf IN (SELECT cpf FROM {TAB_MAILING}
                              WHERE campanha_id = :cam AND (eps = :eps_c OR eps = '' OR eps IS NULL))
          AND NOT EXISTS (
              SELECT 1 FROM ({outras_sql}) o JOIN {TAB_MAILING} mm
                ON mm.campanha_id = o.cam AND (mm.eps = :eps_c OR mm.eps = '' OR mm.eps IS NULL)
              WHERE mm.cpf = b.aluno_cpf AND CAST({col_data} AS DATE) BETWEEN o.ini AND o.fim)"""
        return f"""
        SELECT b.* FROM {r['tabela']} b
        WHERE {filtro}
          AND {cond_eps}
          {extra}
          AND CAST({col_data} AS DATE) BETWEEN :ini AND :{fim_param}
          {publico}"""

    venda_inner = montar("b.dt_inscricao", "fim_v")
    mat_inner = montar("b.dt_pma_conf", "fim_m", "AND b.fl_pma_conf = 1")
    base = f"\n      WITH b AS ({montar('b.dt_pma_conf', 'fim', 'AND b.fl_pma_conf = 1')}\n      )"
    base_venda = f"\n      WITH b AS ({venda_inner}\n      )"

    funil = consultar(cur, base + """
        SELECT COUNT(DISTINCT matricula_id) AS matriculas, COUNT(DISTINCT aluno_cpf) AS alunos FROM b""", params)[0]
    funil["vendas"] = consultar(cur, base_venda + """
        SELECT COUNT(DISTINCT matricula_id) AS n FROM b""", params)[0]["n"]
    # Usado pelo funil para nao contar duas vezes quem e efetivo e vendeu.
    funil["_venda_sql"] = venda_inner
    funil["_mat_sql"] = mat_inner
    funil["_mat_params"] = {**params, "fim_m": fim_mat}

    # Matriculas cujo CPF tem tabulacao da EPS na view de interacoes
    # (o restante e "matricula sem tabulacao na internalizacao").
    rf = r.get("funil")
    eps_v = rf["eps"].get(p["eps"]) if rf else None
    if eps_v:
        funil["_mat_com_interacao"] = consultar(cur, base + f"""
            SELECT COUNT(DISTINCT b.matricula_id) AS n FROM b
            WHERE {R.hash_cpf_sql('b.aluno_cpf')} IN (
                SELECT DISTINCT v.CPF_HASH_CALLCENTER FROM {rf['tabela']} v
                WHERE v.ORIGEM_REGISTRO = 'INTERACAO' AND v.EPS = :eps_v AND v.DATA_REFERENCIA <= :fim)""",
            {**params, "eps_v": eps_v})[0]["n"]

    if usa_mailing:
        funil["mailing_enviado"] = consultar(cur, f"""SELECT COUNT(DISTINCT cpf) AS n FROM {TAB_MAILING}
            WHERE campanha_id = :cam AND (eps = :eps_c OR eps = '' OR eps IS NULL)""", params)[0]["n"]

    serie = consultar(cur, base + """
        SELECT CAST(dt_pma_conf AS DATE) AS dia, 0 AS tentativas, 0 AS vendas, COUNT(DISTINCT matricula_id) AS matriculas
        FROM b GROUP BY CAST(dt_pma_conf AS DATE)""", params)
    serie += consultar(cur, base_venda + """
        SELECT CAST(dt_inscricao AS DATE) AS dia, 0 AS tentativas, COUNT(DISTINCT matricula_id) AS vendas, 0 AS matriculas
        FROM b GROUP BY CAST(dt_inscricao AS DATE)""", params)

    return funil, serie, []


# ===================== UMA CAMPANHA x EPS =====================
def aplicar_hierarquia(f):
    """
    Regra do funil (todos os produtos e EPS). Cada etapa cabe na anterior:
        Matriculas <= Vendas <= Efetivos <= Atendidos <= Trabalhados <= Mailing
    - Toda matricula foi uma venda, e toda venda e efetiva, atendida e
      trabalhada: as etapas de baixo empurram as de cima.
    - O teto e o Mailing: Trabalhados no maximo 100% da base, e cada
      etapa seguinte no maximo igual a anterior.
    Matriculas e Mailing nunca sao alterados (sao os numeros oficiais).
    Tentativas ficam fora: sao interacoes, nao inscricoes.
    """
    def n(k):
        return int(f.get(k) or 0)

    # Toda matricula foi uma venda.
    if f.get("vendas") is not None and f.get("matriculas") is not None:
        f["vendas"] = max(n("vendas"), n("matriculas"))

    cadeia = ["vendas", "efetivos", "alo", "trabalhados"]
    if any(f.get(k) is None for k in cadeia + ["mailing"]):
        return f

    # Sobe: a etapa de baixo esta contida na de cima.
    for menor, maior in zip(cadeia, cadeia[1:]):
        f[maior] = max(n(maior), n(menor))

    # Teto: Trabalhados ate o Mailing; cada etapa ate a anterior.
    if n("mailing"):
        f["trabalhados"] = min(n("trabalhados"), n("mailing"))
    for maior, menor in [("trabalhados", "alo"), ("alo", "efetivos")]:
        f[menor] = min(n(menor), n(maior))

    # Se a venda passou do teto, o Mailing esta menor que o realizado.
    if n("vendas") > n("efetivos"):
        f["_aviso_funil"] = (
            f"Vendas ({n('vendas')}) acima do que cabe no mailing ({n('mailing')}): "
            "conferir o mailing da campanha."
        )
    return f


def somar_funis(funis):
    total = {}
    for f in funis:
        for k, v in f.items():
            if v is None or k.startswith("_"):
                continue
            total[k] = (total.get(k) or 0) + int(v)
    return total


def somar_faixas(funis):
    total = {}
    for f in funis:
        for k, v in (f.get("_faixas") or {}).items():
            total[k] = total.get(k, 0) + int(v)
    return total or None


def _int(v):
    return int(v or 0)


def juntar_serie(series):
    por_dia = {}
    for linhas in series:
        for l in linhas:
            if l["dia"] is None:
                continue
            d = para_data(l["dia"]).isoformat()
            atual = por_dia.setdefault(d, {"dia": d, "tentativas": 0, "vendas": 0, "matriculas": 0})
            for k in ("tentativas", "vendas", "matriculas"):
                atual[k] += int(l.get(k) or 0)
    return sorted(por_dia.values(), key=lambda x: x["dia"])


def apurar_campanha(cur, p, pendentes, cache_base, paineis=None):
    escopos = R.aplicar_ajuste_escopo(p["codigo_campanha"], p.get("escopos") or [])
    if not escopos:
        raise ValueError("Campanha sem escopo (produto/modalidade) cadastrado.")

    por_produto = {}
    for e in escopos:
        por_produto.setdefault(e.get("produto"), []).append(e)

    bases = {prod: data_base(cur, prod, cache_base, p) for prod in por_produto}
    if any(b is None for b in bases.values()):
        raise ValueError("Não consegui ler a data base de uma das tabelas.")
    dt_base = min(bases.values())

    ini, fim, fim_dados, status, janela_fim = periodo_e_status(p, dt_base)
    usa_mailing = bool(p.get("mailing_aplicavel")) and p.get("tipo_acao") != "INCENTIVO"
    outras_sql = outras_campanhas_sql(p, pendentes) if usa_mailing else None

    funis, series, tabs, fontes, notas = [], [], [], set(), []
    detalhes = []
    tem_funil = False
    cam_nao_encontrado = False

    for produto, escs in por_produto.items():
        regra = R.regra(produto)
        if regra["tipo"] == "interacao":
            f, s, t = apurar_interacao(cur, produto, escs, p, usa_mailing, ini, fim_dados, outras_sql)
            fontes.add("DATABRICKS")
            tem_funil = True
        else:
            fim_mat = max(min(janela_fim, dt_base), ini)
            f, s, t = apurar_matricula(cur, produto, escs, p, usa_mailing, ini, fim_mat, outras_sql, fim_dados)
            fontes.add("DATABRICKS")

            # Funil e tabulacoes de Pos/Prof: view de interacoes no Databricks.
            if regra.get("funil"):
                res = apurar_interacao(cur, produto, escs, p, usa_mailing, ini, fim_dados, outras_sql,
                                       r=regra["funil"], com_matricula=False, venda_sql=f.get("_venda_sql"))
                if res is None:
                    notas.append(f"{p['eps']} sem interações na internalização: funil indisponível.")
                else:
                    fi, si, ti = res
                    tem_funil = True
                    # Vendas e matriculas: tabela oficial. Ate Vendas (exclusive): internalizacao.
                    notas.append(f"{produto}: vendas oficiais {_int(f.get('vendas'))} "
                                 f"(aceitou oferta na internalização: {_int(fi.get('vendas'))}).")
                    f = {**{k: v for k, v in fi.items() if v is not None},
                         **{k: v for k, v in f.items() if v is not None}}
                    sv = fi.get("_sem_venda")
                    if sv:
                        v = int(f.get("vendas") or 0)
                        for etapa in ("trabalhados", "alo", "efetivos"):
                            f[etapa] = int(sv[etapa] or 0) + v
                        f["tentativas"] = int(f.get("tentativas") or 0) + int(sv["vendas_sem_interacao"] or 0)
                    s = s + [{**x, "vendas": 0} for x in si]
                    t = ti

                    mat, com_int = _int(f.get("matriculas")), f.get("_mat_com_interacao")
                    if com_int is not None and mat:
                        notas.append(f"{produto}: {mat - _int(com_int)} de {mat} matrículas sem tabulação na internalização.")

                # Conferencia com o painel da EPS (semana de transicao): so observacao.
                if R.CONFERIR_PAINEL and paineis is not None and p["eps"] in ("VOXA", "LUMEN"):
                    try:
                        res_p = paineis.apurar(produto, escs, p, usa_mailing, ini, fim_dados)
                        fp = res_p[0] if res_p else None
                    except Exception as erro:
                        fp = None
                        notas.append(f"Conferência painel indisponível: {erro}")
                    if fp:
                        comp = ", ".join(f"{k} {_int(fp.get(k))} x {_int(f.get(k))}"
                                         for k in ("tentativas", "trabalhados", "alo", "vendas") if fp.get(k) is not None)
                        notas.append(f"Conferência painel x Databricks ({produto}): {comp}.")

        detalhes.append({
            "produto": produto,
            "interacao": f.get("_det"),
            "venda_sql": f.get("_venda_sql"),
            "mat_sql": f.get("_mat_sql"),
            "mat_params": f.get("_mat_params"),
            "usa_mailing": usa_mailing,
        })

        f = aplicar_hierarquia(f)
        if f.get("_aviso_funil"):
            notas.append(f["_aviso_funil"])
        funis.append(f)
        series.append(s)
        tabs.extend(t)

    funil = somar_funis(funis)

    payload = {
        "eps": p["eps"],
        "status_apuracao": status,
        "periodo_ini": ini,
        "periodo_fim": fim,
        "janela_fim": janela_fim,
        "dt_base": dt_base,
        "fonte_funil": "DATABRICKS" if tem_funil else None,
        "fonte_matricula": "DATABRICKS",
        "funil": {
            # Topo do funil: com mailing enviado, vale o arquivo importado no
            # Databricks; sem mailing (incentivo), as inscricoes da operacao.
            "mailing": (funil.get("mailing_enviado") if usa_mailing and funil.get("mailing_enviado") is not None
                        else (funil.get("mailing") if tem_funil else None)),
            "mailing_enviado": funil.get("mailing_enviado") if usa_mailing else None,
            "leads_acionados": funil.get("leads_acionados") if tem_funil else None,
            "tentativas": funil.get("tentativas") if tem_funil else None,
            "trabalhados": funil.get("trabalhados") if tem_funil else None,
            "alo": funil.get("alo") if tem_funil else None,
            "efetivos": funil.get("efetivos") if tem_funil else None,
            "vendas": funil.get("vendas"),
            "matriculas": funil.get("matriculas", 0),
            "alunos": funil.get("alunos"),
            "leads_reacionados": funil.get("leads_reacionados"),
        },
        "faixas_tentativas": somar_faixas(funis),
        "serie_diaria": juntar_serie(series),
        "tabulacoes": [
            {
                "classificacao": str(t.get("classificacao") or "OUTROS")[:60],
                "tabulacao_1": (str(t["tabulacao_1"])[:300] if t.get("tabulacao_1") else None),
                "tabulacao_2": (str(t["tabulacao_2"])[:300] if t.get("tabulacao_2") else None),
                "tabulacao_3": (str(t["tabulacao_3"])[:300] if t.get("tabulacao_3") else None),
                "interacoes": _int(t.get("interacoes")),
                "leads": _int(t.get("leads")),
            }
            for t in tabs
        ][:4000],
        "observacao": " ".join([f"Fontes: {', '.join(sorted(fontes))}. Produtos: {', '.join(por_produto)}."] + notas)[:1900],
    }
    DETALHE[(p["codigo_campanha"], p["eps"])] = detalhes
    return payload, dt_base, cam_nao_encontrado


# ===================== RODADA =====================
def rodada(simular=False, so_campanha=None, ignorar_base=False, refazer=False):
    inicio = time.time()
    central = Central()
    central.acordar()

    pendentes = central.pendentes()
    pendentes = [p for p in pendentes if "TESTE" not in str(p.get("nome_campanha") or "").upper()]
    if so_campanha:
        pendentes_alvo = [p for p in pendentes if p["codigo_campanha"] == so_campanha.upper()]
    else:
        pendentes_alvo = pendentes
    log(f"{len(pendentes_alvo)} campanha(s) x EPS em apuração")

    if not pendentes_alvo:
        return

    # Login do Databricks: se falhar (login vencido, arquivo ausente),
    # avisa Admin e Planejamento por e-mail e no Dashboard. Um aviso por
    # dia, para nao repetir a cada hora; o aviso se rearma quando o
    # login volta a funcionar.
    marca_alerta = os.path.join(PASTA, "alerta_login.txt")
    try:
        conn = conectar_databricks()
    except Exception as erro:
        log(f"falha no login do Databricks: {type(erro).__name__}: {erro}")
        hoje_txt = hoje().isoformat()
        ja_avisou = os.path.exists(marca_alerta) and open(marca_alerta, encoding="utf-8").read().strip() == hoje_txt
        if not simular and not ja_avisou:
            try:
                central.execucao(
                    "ERRO", motivo="ERRO_PROCESSO",
                    mensagem=("Login do Databricks vencido ou inválido: o robô não conseguiu apurar nenhuma campanha. "
                              "Na VM (usuário de serviço), rode: python robo_apuracao.py --login"),
                )
                with open(marca_alerta, "w", encoding="utf-8") as arq:
                    arq.write(hoje_txt)
            except Exception as erro_aviso:
                log(f"não foi possível avisar a Central: {erro_aviso}")
        raise

    if os.path.exists(marca_alerta):
        os.remove(marca_alerta)

    cur = conn.cursor()
    preparar_tabela_mailing(cur)
    try:
        preparar_tabela_apuracao(cur)
        preparar_tabela_detalhe(cur)
    except Exception as erro:
        log(f"(não consegui preparar {TAB_APURACAO}: {erro})")
    cache_base = {}
    alertou_base = False
    paineis = Paineis()

    arquivos = arquivos_mailing(cur)
    for cam in sorted({p["codigo_campanha"] for p in pendentes_alvo if p.get("mailing_aplicavel") and p.get("tipo_acao") != "INCENTIVO"}):
        if cam in arquivos:
            try:
                carregar_mailing(cur, cam, *arquivos[cam])
            except Exception as erro:
                log(f"   ERRO ao carregar mailing {cam}: {erro}")
                central.execucao("ERRO", codigo=cam, motivo="ERRO_PROCESSO", mensagem=f"Falha ao carregar o mailing: {erro}")

    for p in pendentes_alvo:
        cam, eps = p["codigo_campanha"], p["eps"]
        t0 = time.time()
        log(f"-> {cam} / {eps} ({p.get('tipo_acao')})")
        log("   escopos: " + "; ".join(
            "/".join(str(e.get(k)) for k in ("produto", "frente_pos", "modalidade", "supercanal") if e.get(k))
            for e in (p.get("escopos") or [])))
        try:
            usa_mailing = bool(p.get("mailing_aplicavel")) and p.get("tipo_acao") != "INCENTIVO"
            if usa_mailing and cam not in arquivos:
                log("   pendência: mailing não encontrado")
                if not simular:
                    central.execucao("PENDENCIA", cam, eps, "MAILING_AUSENTE",
                                     f"Arquivo mailing_{cam} não encontrado na pasta mailing do Databricks.")
                continue

            produtos = {e.get("produto") for e in p.get("escopos") or []}
            bases = [data_base(cur, prod, cache_base, p) for prod in produtos if prod in R.PRODUTOS]
            dt_base = min(bases) if bases else None
            if dt_base is None or (dt_base < hoje() - timedelta(days=1) and not ignorar_base):
                log(f"   aguardando base D-1 (base atual: {dt_base})")
                if datetime.now(FUSO).hour >= HORA_ALERTA_BASE and not simular and not alertou_base:
                    alertou_base = True
                    central.execucao("PENDENCIA", None, None, "BASE_ATRASADA",
                                     f"A base do Databricks ainda está em {dt_base}; o esperado era {hoje() - timedelta(days=1)}.", dt_base)
                continue

            # Go-live depois da base disponivel (ex.: go-live hoje, base de
            # ontem): ainda nao ha dado do periodo. Espera a proxima base.
            inicio_apuracao = periodo_e_status(p, dt_base)[0]
            if inicio_apuracao and inicio_apuracao > dt_base:
                log(f"   início em {inicio_apuracao}; base ainda é de {dt_base}: aguardando a base do período")
                continue

            status_previsto = periodo_e_status(p, dt_base)[3]
            if (not refazer and str(p.get("ultima_dt_base") or "") == dt_base.isoformat()
                    and (p.get("status_apuracao") == status_previsto or p.get("status_apuracao") == "FINAL")):
                log("   já apurada com esta data base")
                continue

            # Falha de rede com o Databricks (conexao caiu, warehouse
            # reiniciando): reconecta e tenta mais uma vez antes de
            # registrar erro.
            try:
                payload, dt_base, cam_nao_encontrado = apurar_campanha(cur, p, pendentes, cache_base, paineis)
            except Exception as erro_rede:
                if type(erro_rede).__name__ not in ("RequestError", "OperationalError", "ConnectionError", "MaxRetryError"):
                    raise
                log(f"   falha de conexão com o Databricks ({type(erro_rede).__name__}); reconectando e tentando de novo")
                try:
                    conn.close()
                except Exception:
                    pass
                time.sleep(20)
                conn = conectar_databricks()
                cur = conn.cursor()
                payload, dt_base, cam_nao_encontrado = apurar_campanha(cur, p, pendentes, cache_base, paineis)
            payload["duracao_seg"] = round(time.time() - t0, 1)
            f = payload["funil"]
            log(f"   {payload['status_apuracao']} | período {payload['periodo_ini']} a {payload['periodo_fim']} | "
                f"mailing {f['mailing']} | acionados {f['leads_acionados']} | tentativas {f['tentativas']} | "
                f"reacionados {f.get('leads_reacionados')} | vendas {f['vendas']} | matrículas {f['matriculas']}")
            log(f"   obs: {payload['observacao']}")

            if simular:
                continue
            resp = central.gravar(cam, payload)
            log(f"   gravada na Central ({resp.get('apuracao', {}).get('status_apuracao')})")

            try:
                gravar_apuracao_databricks(cur, p, payload)
                log(f"   gravada no Databricks ({TAB_APURACAO} e apuracao/apuracao_{cam}.csv)")
                view = gravar_detalhe_databricks(cur, p, DETALHE.get((cam, eps), []))
                log(f"   detalhe CPF a CPF em {view}")
            except Exception as erro:
                log(f"   (não consegui gravar no Databricks: {type(erro).__name__}: {erro})")

            # Codigo CAM ausente no painel: avisa na primeira apuracao e no fechamento.
            if cam_nao_encontrado and (not p.get("status_apuracao") or payload["status_apuracao"] == "FINAL"):
                central.execucao("PENDENCIA", cam, eps, "CAM_NAO_ENCONTRADO",
                                 f"A EPS ainda não usa o código {cam} no nome da campanha no painel. "
                                 "O funil operacional dessa campanha fica indisponível até isso ser ajustado.")

        except ValueError as erro:
            log(f"   pendência de regra: {erro}")
            if not simular:
                central.execucao("PENDENCIA", cam, eps, "REGRA_SEM_DE_PARA", str(erro))
        except Exception as erro:
            log(f"   ERRO: {erro}")
            log(traceback.format_exc())
            if not simular:
                central.execucao("ERRO", cam, eps, "ERRO_PROCESSO", f"{type(erro).__name__}: {erro}")

    conn.close()
    log(f"rodada concluída em {time.time() - inicio:.0f}s")


# ===================== UTILITARIOS =====================
def atualizar():
    central = Central()
    central.acordar()
    nomes = central.s.get(f"{CENTRAL}/api/robo/arquivos", timeout=120).json()
    for nome in nomes:
        conteudo = central.s.get(f"{CENTRAL}/api/robo/arquivo/{nome}", timeout=120)
        conteudo.raise_for_status()
        with open(os.path.join(PASTA, nome), "wb") as f:
            f.write(conteudo.content)
        print(f"atualizado: {nome}")


def salvar_chave():
    """Copia a chave do cofre para chave_robo.txt, legivel so por este usuario."""
    chave = keyring.get_password("central_robo", "robo")
    if not chave:
        return print("Chave não encontrada no cofre (central_robo/robo).")
    with open(CHAVE_ARQ, "w", encoding="utf-8") as f:
        f.write(chave)
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
    subprocess.run(["icacls", CHAVE_ARQ, "/inheritance:r", "/grant:r", f"{usuario}:F"], capture_output=True)
    print(f"CHAVE SALVA em {CHAVE_ARQ}")


def agendar():
    """
    Agenda o robo (7h-20h, de hora em hora, seg a sex; feriado e conferido
    no proprio robo) e o keep-alive para rodarem com
    ou sem usuario conectado, SEM guardar senha (logon S4U). Rode o
    PowerShell como administrador.
    """
    python = sys.executable.replace("python.exe", "pythonw.exe")
    script = os.path.abspath(__file__)
    comando = f"""
$usuario = "$env:USERDOMAIN\\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType S4U -RunLevel Highest
$acao = New-ScheduledTaskLumen -Execute '{python}' -Argument '"{script}" --agendado' -WorkingDirectory '{PASTA}'
$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '07:00'
$gatilho.Repetition = (New-ScheduledTaskTrigger -Once -At '07:00' -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 13 -Minutes 5)).Repetition
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 50) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'Central_Robo_Apuracao' -Lumen $acao -Trigger $gatilho -Settings $config -Principal $principal -Description 'Robo de apuracao da Central (dias uteis, 7h-20h, de hora em hora)' -Force | Out-Null
'ROBO AGENDADO (sem senha, com ou sem usuario conectado)'
if (Get-ScheduledTask -TaskName 'Central_KeepAlive' -ErrorLumen SilentlyContinue) {{
    Set-ScheduledTask -TaskName 'Central_KeepAlive' -Principal $principal | Out-Null
    'KEEP-ALIVE AJUSTADO (sem senha, com ou sem usuario conectado)'
}} else {{ 'AVISO: tarefa Central_KeepAlive nao encontrada' }}
"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", lumen="store_true")
    ap.add_argument("--ignorar-base", lumen="store_true", help="carga manual: apura com a base disponivel, mesmo sem D-1")
    ap.add_argument("--refazer", lumen="store_true", help="reapura mesmo o que ja foi apurado com esta data base")
    ap.add_argument("--campanha")
    ap.add_argument("--login", lumen="store_true")
    ap.add_argument("--atualizar", lumen="store_true")
    ap.add_argument("--agendar", lumen="store_true")
    ap.add_argument("--agendado", lumen="store_true", help="rodada do agendador: so roda em dia util")
    ap.add_argument("--salvar-chave", lumen="store_true", help="copia a chave do cofre para chave_robo.txt (antes do --agendar)")
    args = ap.parse_args()

    if args.atualizar:
        return atualizar()
    if args.salvar_chave:
        return salvar_chave()
    if args.agendar:
        return agendar()
    if args.login:
        conn = conectar_databricks(interativo=True)
        conn.cursor().execute("SELECT 1")
        conn.close()
        return print("LOGIN DO DATABRICKS OK")

    # Agendador: fim de semana e feriado nao apuram (rodada manual ignora isso).
    if args.agendado and not R.dia_util(hoje()):
        return log("dia não útil (fim de semana ou feriado): rodada agendada não executada")

    # Trava de seguranca: se o login do Databricks expirar, a conexao
    # ficaria esperando o navegador para sempre numa rodada agendada.
    def estourou():
        log(f"rodada passou de {LIMITE_RODADA_MIN} min; encerrando. Se repetir, rode --login.")
        os._exit(2)

    trava = threading.Timer(LIMITE_RODADA_MIN * 60, estourou)
    trava.daemon = True
    trava.start()

    try:
        rodada(simular=args.simular, so_campanha=args.campanha, ignorar_base=args.ignorar_base, refazer=args.refazer)
    except Exception as erro:
        log(f"FALHA GERAL: {erro}")
        log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()