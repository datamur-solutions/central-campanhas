"""
SENHA DOS USUARIOS

Acrescenta senha ao login que ja existe. Perfis, dominio EPS
e liberacao de acesso continuam exatamente como estao: este
modulo so responde se a senha informada confere.

Regras:
- primeiro acesso sem senha -> o usuario cria a senha
- acessos seguintes         -> o usuario informa a senha
- o usuario pode trocar a senha a qualquer momento
- "esqueci minha senha": link com token enviado por e-mail
- a nova senha nunca pode ser igual a atual
- o ADMIN pode apagar a senha de alguem; no acesso seguinte
  a pessoa cria uma nova

A senha nunca e gravada: grava-se so o hash PBKDF2-SHA256,
da biblioteca padrao do Python (nenhuma dependencia nova).
"""

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from app.db import (
    DATABASE,
    fetch_all,
    get_connection,
)


TABELAS = {
    "interno": "usuario_interno_acesso",
    "eps": "usuario_eps_acesso",
}

COLUNA_EMAIL = "email_usuario"

ITERACOES = 310_000

MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 15 * 60


# ------------------------------------------------------------
# HASH
# ------------------------------------------------------------

def _gerar_hash(senha):
    sal = os.urandom(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        sal,
        ITERACOES,
    )

    return f"pbkdf2_sha256${ITERACOES}${sal.hex()}${digest.hex()}"


def _conferir_hash(senha, guardado):
    try:
        _, iteracoes, sal_hex, digest_hex = guardado.split("$")

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode("utf-8"),
            bytes.fromhex(sal_hex),
            int(iteracoes),
        )

        return hmac.compare_digest(
            digest.hex(),
            digest_hex,
        )

    except Exception:
        return False


def _validar_regra(senha):
    if not senha or len(senha) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")

    if not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        raise ValueError("A senha precisa ter letras e números.")


# ------------------------------------------------------------
# BLOQUEIO APOS TENTATIVAS ERRADAS
#
# Em memoria: se o servico reiniciar, o contador zera. Basta
# para impedir que alguem teste senhas em sequencia.
# ------------------------------------------------------------

_tentativas = {}
_trava = threading.Lock()


def _chave(portal, email):
    return f"{portal}:{email}"


def _checar_bloqueio(portal, email):
    with _trava:
        falhas, desde = _tentativas.get(_chave(portal, email), (0, 0))

        if falhas >= MAX_TENTATIVAS:
            restante = BLOQUEIO_SEGUNDOS - (time.time() - desde)

            if restante > 0:
                minutos = int(restante // 60) + 1
                raise PermissionError(
                    "Muitas tentativas erradas. "
                    f"Tente de novo em {minutos} min."
                )

            _tentativas.pop(_chave(portal, email), None)


def _registrar_falha(portal, email):
    with _trava:
        falhas, _ = _tentativas.get(_chave(portal, email), (0, 0))
        _tentativas[_chave(portal, email)] = (falhas + 1, time.time())


def _limpar_falhas(portal, email):
    with _trava:
        _tentativas.pop(_chave(portal, email), None)


# ------------------------------------------------------------
# BANCO
# ------------------------------------------------------------

def _tabela(portal):
    tabela = TABELAS.get((portal or "").strip().lower())

    if not tabela:
        raise ValueError("Portal inválido.")

    return tabela


def _normalizar(email):
    email = (email or "").strip().lower()

    if not email:
        raise ValueError("Informe o e-mail.")

    return email


def _hashes_do_usuario(portal, email):
    """
    Devolve None se o e-mail nao existe na tabela de acesso,
    ou a lista de hashes das linhas dele (pode haver mais de
    uma linha por e-mail).
    """
    linhas = fetch_all(
        f"""
        SELECT senha_hash
        FROM {DATABASE}.{_tabela(portal)}
        WHERE lower({COLUNA_EMAIL}) = ?
        """,
        [email],
    )

    if not linhas:
        return None

    return [l["senha_hash"] for l in linhas if l["senha_hash"]]


def _gravar_hash(portal, email, novo_hash):
    # Escrita dentro do "with": no Postgres o commit acontece
    # ao sair do bloco; no Databricks e automatico.
    with get_connection() as conexao:
        cursor = conexao.cursor()

        try:
            cursor.execute(
                f"""
                UPDATE {DATABASE}.{_tabela(portal)}
                SET senha_hash = ?,
                    dt_senha = current_timestamp()
                WHERE lower({COLUNA_EMAIL}) = ?
                """,
                parameters=[novo_hash, email],
            )
        finally:
            cursor.close()


# ------------------------------------------------------------
# OPERACOES
# ------------------------------------------------------------

def status_senha(portal, email):
    email = _normalizar(email)
    hashes = _hashes_do_usuario(portal, email)

    return {
        "existe": hashes is not None,
        "tem_senha": bool(hashes),
    }


def criar_senha(portal, email, nova_senha):
    email = _normalizar(email)
    hashes = _hashes_do_usuario(portal, email)

    if hashes is None:
        raise PermissionError("E-mail sem acesso liberado.")

    if hashes:
        raise ValueError("Este usuário já tem senha. Use a opção de entrar.")

    _validar_regra(nova_senha)
    _gravar_hash(portal, email, _gerar_hash(nova_senha))

    return {"sucesso": True}


def conferir_senha(portal, email, senha):
    email = _normalizar(email)
    _checar_bloqueio(portal, email)

    hashes = _hashes_do_usuario(portal, email)

    if hashes is None:
        raise PermissionError("E-mail sem acesso liberado.")

    if not hashes:
        raise ValueError("Senha ainda não criada.")

    if not any(_conferir_hash(senha or "", h) for h in hashes):
        _registrar_falha(portal, email)
        raise PermissionError("E-mail ou senha incorretos.")

    _limpar_falhas(portal, email)

    return {"sucesso": True}


def _igual_a_atual(portal, email, nova_senha):
    hashes = _hashes_do_usuario(portal, email) or []
    return any(_conferir_hash(nova_senha or "", h) for h in hashes)


def trocar_senha(portal, email, senha_atual, nova_senha):
    conferir_senha(portal, email, senha_atual)

    if _igual_a_atual(portal, _normalizar(email), nova_senha):
        raise ValueError("A nova senha precisa ser diferente da atual.")

    _validar_regra(nova_senha)
    _gravar_hash(portal, _normalizar(email), _gerar_hash(nova_senha))

    return {"sucesso": True}


def redefinir_senha(portal, email):
    """Uso do ADMIN: apaga a senha para o usuario criar outra."""
    email = _normalizar(email)

    if _hashes_do_usuario(portal, email) is None:
        raise ValueError("E-mail não encontrado neste portal.")

    _gravar_hash(portal, email, None)
    _limpar_falhas(portal, email)

    return {"sucesso": True}


# ------------------------------------------------------------
# ESQUECI MINHA SENHA
#
# O token vai so no link do e-mail; no banco fica o hash dele.
# Quem ler a tabela senha_redefinicao nao consegue usar o link.
# ------------------------------------------------------------

VALIDADE_TOKEN_MIN = 30
INTERVALO_PEDIDOS_SEG = 120

PAGINA_LOGIN = {
    "interno": "/portal-interno",
    "eps": "/portal-eps",
}

MENSAGEM_PEDIDO = (
    "Se o e-mail estiver cadastrado, você vai receber um link "
    "para redefinir a senha. O link vale por "
    f"{VALIDADE_TOKEN_MIN} minutos."
)


def _agora():
    return datetime.now(timezone.utc)


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _executar(query, parametros):
    with get_connection() as conexao:
        cursor = conexao.cursor()
        try:
            cursor.execute(query, parameters=parametros)
        finally:
            cursor.close()


def _data(valor):
    """Normaliza o que o banco devolve para datetime com fuso UTC."""
    if valor is None:
        return None

    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))

    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)

    return valor


def solicitar_redefinicao(portal, email):
    """
    Sempre devolve a mesma mensagem, exista o e-mail ou nao,
    para ninguem descobrir quais e-mails tem acesso.
    """
    from app.email_service import base_url, enviar_email, montar_html

    tabela = _tabela(portal)  # valida o portal
    email = _normalizar(email)

    if _hashes_do_usuario(portal, email) is None:
        return {"mensagem": MENSAGEM_PEDIDO}

    ultimo = fetch_all(
        f"""
        SELECT dt_criacao
        FROM {DATABASE}.senha_redefinicao
        WHERE email = ? AND portal = ?
        ORDER BY dt_criacao DESC
        LIMIT 1
        """,
        [email, portal],
    )

    if ultimo:
        criado = _data(ultimo[0]["dt_criacao"])
        if criado and (_agora() - criado).total_seconds() < INTERVALO_PEDIDOS_SEG:
            return {"mensagem": MENSAGEM_PEDIDO}

    # Um link valido por vez: o pedido novo invalida os anteriores.
    _executar(
        f"""
        UPDATE {DATABASE}.senha_redefinicao
        SET dt_uso = ?
        WHERE email = ? AND portal = ? AND dt_uso IS NULL
        """,
        [_agora(), email, portal],
    )

    token = secrets.token_urlsafe(32)
    agora = _agora()

    _executar(
        f"""
        INSERT INTO {DATABASE}.senha_redefinicao
            (token_hash, portal, email, dt_criacao, dt_expira, dt_uso)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        [
            _hash_token(token),
            portal,
            email,
            agora,
            agora + timedelta(minutes=VALIDADE_TOKEN_MIN),
        ],
    )

    link = f"{base_url()}/redefinir-senha?token={token}"

    try:
        enviar_email(
            para=email,
            assunto="Redefinição de senha — Central de Campanhas",
            html_corpo=montar_html(
                titulo="Redefinir sua senha",
                paragrafos=[
                    "Recebemos um pedido para redefinir a senha de acesso "
                    f"da conta {email} na Central de Campanhas.",
                    f"O link abaixo vale por {VALIDADE_TOKEN_MIN} minutos e "
                    "pode ser usado uma única vez.",
                ],
                botao=("Criar nova senha", link),
                rodape=(
                    "Se você não pediu a redefinição, ignore este e-mail: "
                    "sua senha atual continua valendo."
                ),
            ),
            texto=(
                "Redefinir sua senha na Central de Campanhas.\n\n"
                f"Abra o link (válido por {VALIDADE_TOKEN_MIN} minutos):\n{link}\n\n"
                "Se você não pediu, ignore este e-mail."
            ),
        )
    except Exception as erro:
        # Nao expoe a falha na tela (revelaria que o e-mail
        # existe). Fica no log do Render para investigar.
        print("[SENHA] Falha ao enviar e-mail de redefinição:", erro)

    return {"mensagem": MENSAGEM_PEDIDO}


def _token_valido(token):
    if not token:
        raise ValueError("Link inválido.")

    linhas = fetch_all(
        f"""
        SELECT portal, email, dt_expira, dt_uso
        FROM {DATABASE}.senha_redefinicao
        WHERE token_hash = ?
        """,
        [_hash_token(token)],
    )

    if not linhas:
        raise ValueError("Link inválido. Peça um novo na tela de login.")

    linha = linhas[0]

    if linha["dt_uso"] is not None:
        raise ValueError("Este link já foi usado ou foi substituído por um mais recente.")

    if _data(linha["dt_expira"]) < _agora():
        raise ValueError("Este link expirou. Peça um novo na tela de login.")

    return linha


def validar_token(token):
    linha = _token_valido(token)

    return {
        "valido": True,
        "email": linha["email"],
        "portal": linha["portal"],
        "pagina_login": PAGINA_LOGIN.get(linha["portal"], "/"),
    }


def redefinir_com_token(token, nova_senha):
    linha = _token_valido(token)

    portal = linha["portal"]
    email = linha["email"]

    _validar_regra(nova_senha)

    if _igual_a_atual(portal, email, nova_senha):
        raise ValueError("A nova senha precisa ser diferente da atual.")

    _gravar_hash(portal, email, _gerar_hash(nova_senha))

    _executar(
        f"""
        UPDATE {DATABASE}.senha_redefinicao
        SET dt_uso = ?
        WHERE token_hash = ?
        """,
        [_agora(), _hash_token(token)],
    )

    _limpar_falhas(portal, email)

    return {
        "sucesso": True,
        "pagina_login": PAGINA_LOGIN.get(portal, "/"),
    }