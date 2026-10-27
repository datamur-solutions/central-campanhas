"""
Trava de homologação.

Coloca uma senha única na frente de TODA a aplicação. Serve
para publicar numa URL pública sem deixar os dados de campanha
abertos a quem tiver o link.

É proteção de perímetro, não substitui o login do sistema:
depois de passar por aqui, o get_current_user continua valendo
normalmente.

Liga e desliga por variável de ambiente. Sem HOMOLOG_USER e
HOMOLOG_PASS definidos, a trava não faz nada — então o
desenvolvimento local segue igual.
"""

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class HomologGuardMiddleware(BaseHTTPMiddleware):

    def __init__(self, app):
        super().__init__(app)

        self.usuario = os.getenv("HOMOLOG_USER", "")
        self.senha = os.getenv("HOMOLOG_PASS", "")
        self.ativo = bool(self.usuario and self.senha)

    async def dispatch(self, request, call_next):

        if not self.ativo:
            return await call_next(request)

        # O healthcheck da plataforma não manda credencial.
        # Se ele cair na trava, o serviço reinicia em loop.
        if request.url.path == "/health":
            return await call_next(request)

        cabecalho = request.headers.get("authorization", "")

        if cabecalho.startswith("Basic "):
            import base64

            try:
                bruto = base64.b64decode(
                    cabecalho[6:]
                ).decode("utf-8")

                usuario, _, senha = bruto.partition(":")

                # compare_digest evita vazar informação pelo
                # tempo de resposta
                ok_usuario = secrets.compare_digest(
                    usuario, self.usuario
                )

                ok_senha = secrets.compare_digest(
                    senha, self.senha
                )

                if ok_usuario and ok_senha:
                    return await call_next(request)

            except Exception:
                pass

        return Response(
            status_code=401,
            content="Ambiente de homologação restrito.",
            headers={
                "WWW-Authenticate": 'Basic realm="Homologacao"'
            },
        )
