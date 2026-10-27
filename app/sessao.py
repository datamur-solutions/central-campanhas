"""
SESSAO E SEGURANCA

Problema que isto resolve: antes, o backend confiava no
e-mail que o navegador mandava (?email= no portal EPS e o
header x-usuario-email no interno). Com F12, qualquer pessoa
trocava esse e-mail e via os dados de outra EPS ou agia como
outro usuario.

Agora:
- ao acertar a senha, o backend grava um cookie de sessao
  assinado (HttpOnly: o JavaScript da pagina nao consegue ler
  nem alterar);
- em toda chamada /api/, o middleware le o cookie e SOBRESCREVE
  o e-mail que veio do navegador pelo e-mail da sessao;
- sem cookie valido, a API responde 401.

O resto do codigo (auth.py e as rotas) continua igual: ele
segue lendo o mesmo header e o mesmo ?email=, que agora so
podem conter o e-mail de quem realmente entrou.

Variaveis de ambiente:
  SESSION_SECRET   texto longo e aleatorio (obrigatorio em producao)
  SESSION_HORAS    validade da sessao, padrao 8
  COOKIE_SECURE    "false" so para rodar em http local
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, urlencode


_SEGREDO = os.getenv("SESSION_SECRET", "").strip()

if not _SEGREDO:
    # Sem segredo configurado, gera um na subida. Funciona,
    # mas toda reinicializacao do servico derruba as sessoes.
    _SEGREDO = secrets.token_urlsafe(48)
    print(
        "[SESSAO] SESSION_SECRET nao configurado. "
        "Usando segredo temporario: as sessoes caem a cada reinicio."
    )

SESSAO_SEGUNDOS = int(float(os.getenv("SESSION_HORAS", "8")) * 3600)

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() != "false"

NOME_COOKIE = {
    "interno": "central_sessao_interno",
    "eps": "central_sessao_eps",
}

PAGINA_LOGIN = {
    "interno": "/portal-interno",
    "eps": "/portal-eps",
}

# Rotas /api/ que funcionam sem sessao: login, senha, o
# pedido de acesso da EPS (usado antes de existir senha) e o
# robo de apuracao da VM. O robo nao tem login de pessoa: cada
# rota /api/robo/ exige a chave X-Robo-Key (ROBO_API_KEY) e
# recusa qualquer chamada sem ela (ver robo_apuracao_service.py).
ROTAS_PUBLICAS = (
    "/api/auth/",
    "/api/external/access/request",
    "/api/robo/",
)

HEADER_EMAIL = b"x-usuario-email"


# ------------------------------------------------------------
# TOKEN
# ------------------------------------------------------------

def _b64(dados):
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _unb64(texto):
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _assinar(corpo):
    return _b64(hmac.new(_SEGREDO.encode(), corpo.encode(), hashlib.sha256).digest())


def criar_token(portal, email):
    corpo = _b64(json.dumps({
        "p": portal,
        "e": email.strip().lower(),
        "x": int(time.time()) + SESSAO_SEGUNDOS,
    }).encode())

    return f"{corpo}.{_assinar(corpo)}"


def ler_token(token, portal):
    """Devolve o e-mail da sessao, ou None se invalida/expirada."""
    try:
        corpo, assinatura = token.split(".", 1)

        if not hmac.compare_digest(assinatura, _assinar(corpo)):
            return None

        dados = json.loads(_unb64(corpo))

        if dados.get("p") != portal or dados.get("x", 0) < time.time():
            return None

        return dados.get("e") or None

    except Exception:
        return None


# ------------------------------------------------------------
# COOKIE
# ------------------------------------------------------------

def gravar_sessao(response, portal, email):
    response.set_cookie(
        key=NOME_COOKIE[portal],
        value=criar_token(portal, email),
        max_age=SESSAO_SEGUNDOS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def apagar_sessao(response, portal):
    response.delete_cookie(
        key=NOME_COOKIE[portal],
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


def email_da_sessao(request, portal):
    """Para uso dentro das rotas (ex.: trocar senha)."""
    token = request.cookies.get(NOME_COOKIE.get(portal, ""), "")
    return ler_token(token, portal) if token else None


def _cookies_do_scope(scope):
    for nome, valor in scope.get("headers", []):
        if nome == b"cookie":
            jar = SimpleCookie()
            try:
                jar.load(valor.decode("latin-1"))
            except Exception:
                return {}
            return {k: m.value for k, m in jar.items()}
    return {}


# ------------------------------------------------------------
# MIDDLEWARE DE SESSAO
# ------------------------------------------------------------

async def _responder_json(send, status, corpo, headers=None):
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")

    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(dados)).encode()),
            *(headers or []),
        ],
    })
    await send({"type": "http.response.body", "body": dados})


class SessaoMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        caminho = scope.get("path", "")

        if not caminho.startswith("/api/") or caminho.startswith(ROTAS_PUBLICAS):
            return await self.app(scope, receive, send)

        portal = "eps" if caminho.startswith("/api/external/") else "interno"

        token = _cookies_do_scope(scope).get(NOME_COOKIE[portal], "")
        email = ler_token(token, portal) if token else None

        if not email:
            return await _responder_json(send, 401, {
                "detail": "Sua sessão expirou. Entre novamente.",
                "login": PAGINA_LOGIN[portal],
            })

        scope = dict(scope)

        # Header de identidade: descarta o que veio do navegador
        # e coloca o e-mail da sessao.
        headers = [
            (nome, valor)
            for nome, valor in scope.get("headers", [])
            if nome != HEADER_EMAIL
        ]
        headers.append((HEADER_EMAIL, email.encode("utf-8")))
        scope["headers"] = headers

        # ?email= do portal EPS: mesmo tratamento.
        if portal == "eps":
            parametros = [
                (chave, valor)
                for chave, valor in parse_qsl(
                    scope.get("query_string", b"").decode("latin-1"),
                    keep_blank_values=True,
                )
                if chave != "email"
            ]
            parametros.append(("email", email))
            scope["query_string"] = urlencode(parametros).encode("latin-1")

        return await self.app(scope, receive, send)


# ------------------------------------------------------------
# CABECALHOS DE SEGURANCA
# ------------------------------------------------------------

_CABECALHOS = [
    # Nao deixa outro site abrir a Central dentro de um iframe
    # (golpe de clique disfarcado).
    (b"x-frame-options", b"DENY"),
    # O navegador nao "adivinha" tipo de arquivo.
    (b"x-content-type-options", b"nosniff"),
    # Nao vaza o endereco (e o token de redefinicao) para
    # sites externos.
    (b"referrer-policy", b"same-origin"),
    # So HTTPS neste dominio pelos proximos 180 dias.
    (b"strict-transport-security", b"max-age=15552000"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class CabecalhosSegurancaMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        caminho = scope.get("path", "")

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                headers = list(mensagem.get("headers", []))
                existentes = {nome for nome, _ in headers}

                for nome, valor in _CABECALHOS:
                    if nome not in existentes:
                        headers.append((nome, valor))

                # Respostas da API nunca ficam em cache.
                if caminho.startswith("/api/") and b"cache-control" not in existentes:
                    headers.append((b"cache-control", b"no-store"))

                # Paginas, scripts e estilos: o navegador pode
                # guardar, mas confere a versao a cada acesso.
                # Se nada mudou, o servidor responde "304" e a
                # copia guardada e usada; se mudou, vem a nova.
                # Assim um deploy vale na hora para todo mundo,
                # sem depender de Ctrl+F5.
                elif (
                    b"cache-control" not in existentes
                    and (
                        caminho.endswith((".js", ".css", ".html"))
                        or caminho.startswith(("/portal-interno", "/portal-eps", "/redefinir-senha"))
                    )
                ):
                    headers.append((b"cache-control", b"no-cache"))

                mensagem = dict(mensagem, headers=headers)

            await send(mensagem)

        return await self.app(scope, receive, enviar)