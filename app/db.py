import json
import os
import subprocess
import threading

from dotenv import load_dotenv


# ------------------------------------------------------------
# CARREGA CONFIGURAÇÕES DO .env
# ------------------------------------------------------------

load_dotenv()


# ------------------------------------------------------------
# QUAL BANCO USAR
#
# databricks -> servidor interno da EduNova (VM)
# postgres   -> Supabase (ambiente de homologação)
# ------------------------------------------------------------

DB_ENGINE = os.getenv(
    "DB_ENGINE",
    "databricks"
).strip().lower()


# ------------------------------------------------------------
# DATABRICKS
# ------------------------------------------------------------

SERVER_HOSTNAME = os.getenv(
    "DATABRICKS_SERVER_HOSTNAME"
)

HTTP_PATH = os.getenv(
    "DATABRICKS_HTTP_PATH"
)

CATALOG = os.getenv(
    "DATABRICKS_CATALOG"
)

SCHEMA = os.getenv(
    "DATABRICKS_SCHEMA"
)

CONFIG_PROFILE = os.getenv(
    "DATABRICKS_CONFIG_PROFILE"
)

DATABRICKS_TOKEN = os.getenv(
    "DATABRICKS_TOKEN"
)


# ------------------------------------------------------------
# POSTGRES / SUPABASE
# ------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL"
)

POSTGRES_SCHEMA = os.getenv(
    "POSTGRES_SCHEMA",
    "public"
)

# Quantas conexões o pool mantém.
#
# O Supabase gratuito tem um limite baixo de conexões
# simultâneas. Mantemos o pool pequeno de propósito: cada
# tela do portal dispara várias chamadas ao carregar, e um
# pool grande esgota a cota do banco em vez de acelerar.
POOL_MIN = int(
    os.getenv("POSTGRES_POOL_MIN", "1")
)

POOL_MAX = int(
    os.getenv("POSTGRES_POOL_MAX", "5")
)


# ------------------------------------------------------------
# PREFIXO DAS TABELAS
# ------------------------------------------------------------

if DB_ENGINE == "postgres":
    DATABASE = POSTGRES_SCHEMA
else:
    DATABASE = f"{CATALOG}.{SCHEMA}"


# ============================================================
# DATABRICKS — AUTENTICAÇÃO
# ============================================================

def get_access_token():

    if DATABRICKS_TOKEN:
        return DATABRICKS_TOKEN

    if not CONFIG_PROFILE:
        raise RuntimeError(
            "Nenhuma credencial disponível. "
            "Configure DATABRICKS_TOKEN no ambiente "
            "ou DATABRICKS_CONFIG_PROFILE no .env."
        )

    try:
        resultado = subprocess.run(
            [
                "databricks",
                "auth",
                "token",
                "--profile",
                CONFIG_PROFILE,
                "-o",
                "json"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        dados = json.loads(
            resultado.stdout
        )

        token = dados.get(
            "access_token"
        )

        if not token:
            raise RuntimeError(
                "A Databricks CLI não retornou "
                "um access_token."
            )

        return token

    except FileNotFoundError as erro:
        raise RuntimeError(
            "A Databricks CLI não está instalada neste "
            "ambiente. Configure a variável "
            "DATABRICKS_TOKEN com um token de acesso "
            "pessoal."
        ) from erro

    except subprocess.CalledProcessError as erro:
        detalhe = (
            erro.stderr
            or erro.stdout
            or str(erro)
        )

        raise RuntimeError(
            "Falha ao obter autenticação "
            f"pela Databricks CLI: {detalhe}"
        ) from erro


# ============================================================
# POSTGRES — TRADUÇÃO DE SINTAXE
#
# O sistema foi escrito para o driver do Databricks, que usa
# "?" como marcador e recebe os valores em parameters=[...].
# O psycopg usa "%s" e valores posicionais.
#
# Estas classes traduzem na hora da execução, para o mesmo
# código rodar nos dois bancos sem reescrever as queries.
# ============================================================

# Diferencas de dialeto entre Databricks e Postgres.
#
# O codigo foi escrito em SQL do Databricks. Estas trocas
# acontecem so quando o banco e Postgres, na hora de
# executar — o SQL original continua intacto nos arquivos,
# e a VM nao e afetada.
_EQUIVALENCIAS_POSTGRES = [
    # No Postgres estas sao palavras reservadas e nao
    # aceitam parenteses.
    ("current_timestamp()", "current_timestamp"),
    ("CURRENT_TIMESTAMP()", "CURRENT_TIMESTAMP"),
    ("current_date()", "current_date"),
    ("CURRENT_DATE()", "CURRENT_DATE"),
]


# Funcoes que existem no Databricks e nao no Postgres.
# A chave e o nome da funcao; o valor monta a expressao
# equivalente a partir do argumento original.
#
# collect_set(x) agrupa valores distintos numa lista. No
# Postgres o equivalente e array_agg(distinct x).
_FUNCOES_POSTGRES = {
    "collect_set": "array_agg(distinct {arg})",
    "collect_list": "array_agg({arg})",
}


def _trocar_funcao(query, nome, modelo):
    """
    Troca nome(argumento) pela expressao equivalente.

    Percorre caractere a caractere contando parenteses, em
    vez de usar expressao regular, para nao se perder quando
    o argumento contiver parenteses proprios.
    """
    saida = []
    i = 0
    alvo = nome + "("

    while True:
        pos = query.find(alvo, i)

        if pos == -1:
            saida.append(query[i:])
            break

        saida.append(query[i:pos])

        # Encontra o parentese que fecha este argumento.
        profundidade = 0
        fim = None

        for j in range(pos + len(nome), len(query)):

            if query[j] == "(":
                profundidade += 1

            elif query[j] == ")":
                profundidade -= 1

                if profundidade == 0:
                    fim = j
                    break

        if fim is None:
            # Parentese sem fechamento: nao mexe.
            saida.append(query[pos:])
            break

        argumento = query[pos + len(nome) + 1:fim]

        saida.append(
            modelo.format(arg=argumento)
        )

        i = fim + 1

    return "".join(saida)


def _traduzir_dialeto(query):

    for origem, destino in _EQUIVALENCIAS_POSTGRES:
        query = query.replace(origem, destino)

    for nome, modelo in _FUNCOES_POSTGRES.items():

        if nome in query:
            query = _trocar_funcao(query, nome, modelo)

    return query


def _traduzir_marcadores(query):
    saida = []
    dentro_de_aspas = None

    for caractere in query:

        if dentro_de_aspas:
            if caractere == dentro_de_aspas:
                dentro_de_aspas = None
            saida.append(caractere)
            continue

        if caractere in ("'", '"'):
            dentro_de_aspas = caractere
            saida.append(caractere)
            continue

        if caractere == "?":
            saida.append("%s")
            continue

        if caractere == "%":
            saida.append("%%")
            continue

        saida.append(caractere)

    return "".join(saida)


class _CursorCompativel:

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, parameters=None):
        return self._cursor.execute(
            _traduzir_marcadores(
                _traduzir_dialeto(query)
            ),
            parameters or []
        )

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        return self._cursor.close()


# ============================================================
# POSTGRES — POOL DE CONEXÕES
#
# Antes, cada consulta abria uma conexão nova e fechava em
# seguida. Uma tela do portal dispara sete ou oito chamadas
# ao carregar: eram oito conexões novas, cada uma com o
# custo de rede e de autenticação, competindo pela cota do
# Supabase gratuito. Quando a cota estourava, as chamadas
# seguintes ficavam na fila — daí as esperas de minutos,
# alternadas com respostas em segundos.
#
# Com o pool, as conexões são criadas uma vez e reaproveitadas.
# ============================================================

_pool = None
_pool_lock = threading.Lock()


def _obter_pool():
    global _pool

    if _pool is not None:
        return _pool

    with _pool_lock:

        # Confere de novo: outra thread pode ter criado o
        # pool enquanto esta esperava o cadeado.
        if _pool is not None:
            return _pool

        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL não configurada. "
                "Informe a string de conexão do Postgres."
            )

        from psycopg2 import pool as pg_pool

        _pool = pg_pool.ThreadedConnectionPool(
            POOL_MIN,
            POOL_MAX,
            DATABASE_URL,
            connect_timeout=10,

            # Evita conexão pendurada para sempre quando a
            # rede cai no meio de uma consulta.
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3
        )

        return _pool


class _ConexaoCompativel:
    """
    Envolve a conexão do psycopg.

    Dois pontos que importam:

    1. O Databricks confirma cada comando automaticamente,
       o Postgres não. Sem o commit ao sair do bloco, nada
       do que a aplicação grava seria salvo.

    2. A conexão volta para o pool em vez de ser fechada.
       Se ela estiver quebrada, é descartada, para não
       envenenar o pool com uma conexão morta.
    """

    def __init__(self, conexao, pool):
        self._conexao = conexao
        self._pool = pool
        self._devolvida = False

    def cursor(self):
        return _CursorCompativel(
            self._conexao.cursor()
        )

    def __enter__(self):
        return self

    def __exit__(self, tipo_erro, valor, traceback):

        try:
            if tipo_erro is None:
                self._conexao.commit()
            else:
                self._conexao.rollback()

        except Exception:
            self._devolver(quebrada=True)
            raise

        self._devolver()

        return False

    def _devolver(self, quebrada=False):

        if self._devolvida:
            return

        self._devolvida = True

        try:
            self._pool.putconn(
                self._conexao,
                close=quebrada
            )
        except Exception:
            pass

    def close(self):
        self._devolver()


# ============================================================
# CONEXÃO
# ============================================================

def get_connection():

    if DB_ENGINE == "postgres":

        pool = _obter_pool()

        conexao = pool.getconn()

        return _ConexaoCompativel(
            conexao,
            pool
        )

    from databricks import sql

    return sql.connect(
        server_hostname=SERVER_HOSTNAME,
        http_path=HTTP_PATH,
        catalog=CATALOG,
        schema=SCHEMA,
        access_token=get_access_token()
    )


# ============================================================
# CONSULTA QUE RETORNA VÁRIAS LINHAS
# ============================================================

def fetch_all(
    query,
    parameters=None
):

    parameters = parameters or []

    connection = get_connection()

    try:
        cursor = connection.cursor()

        try:
            cursor.execute(
                query,
                parameters=parameters
            )

            if cursor.description is None:
                return []

            columns = [
                column[0]
                for column
                in cursor.description
            ]

            rows = cursor.fetchall()

            return [
                dict(
                    zip(
                        columns,
                        row
                    )
                )
                for row
                in rows
            ]

        finally:
            cursor.close()

    finally:
        connection.close()


# ============================================================
# CONSULTA QUE RETORNA UMA LINHA
# ============================================================

def fetch_one(
    query,
    parameters=None
):

    rows = fetch_all(
        query,
        parameters
    )

    if not rows:
        return None

    return rows[0]