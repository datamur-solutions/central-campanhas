import os

from fastapi import (
    HTTPException,
    Request
)

from app.db import (
    DATABASE,
    fetch_one
)


# ------------------------------------------------------------
# CONFIGURAÇÃO DO AMBIENTE
#
# local      -> usa DEV_USER_EMAIL do .env
# homologacao-> usa o e-mail informado na tela de login
# producao   -> usa o header do Entra ID (Azure)
# ------------------------------------------------------------

APP_ENV = os.getenv(
    "APP_ENV",
    "local"
)

DEV_USER_EMAIL = os.getenv(
    "DEV_USER_EMAIL"
)


# ------------------------------------------------------------
# IDENTIFICA O E-MAIL DE QUEM ESTÁ ACESSANDO
# ------------------------------------------------------------

def get_request_email(request: Request):

    ambiente = APP_ENV.lower().strip()

    # --------------------------------------------------------
    # AMBIENTE LOCAL
    #
    # Enquanto desenvolvemos no computador, usamos o usuário
    # configurado no .env.
    # --------------------------------------------------------

    if ambiente == "local":

        if not DEV_USER_EMAIL:

            raise HTTPException(
                status_code=500,
                detail=(
                    "DEV_USER_EMAIL não configurado "
                    "no arquivo .env."
                )
            )

        return DEV_USER_EMAIL.lower().strip()


    # --------------------------------------------------------
    # AMBIENTE DE HOMOLOGAÇÃO
    #
    # O e-mail vem da tela de login e acompanha cada chamada.
    # O perfil e a permissão continuam vindo da tabela
    # usuario_interno_acesso, então Planejamento e Comercial
    # veem coisas diferentes, como em produção.
    #
    # ATENÇÃO: isto identifica o usuário, não o autentica.
    # Não há senha: quem souber um e-mail cadastrado entra.
    # É aceitável para homologar o fluxo com o time, protegido
    # pela senha única de acesso ao ambiente. NÃO substitui a
    # autenticação corporativa em produção.
    # --------------------------------------------------------

    if ambiente == "homologacao":

        email = (
            request.headers.get(
                "x-usuario-email"
            )
            or
            request.query_params.get(
                "email"
            )
        )

        if not email:

            raise HTTPException(
                status_code=401,
                detail=(
                    "Informe seu e-mail corporativo "
                    "na tela de acesso."
                )
            )

        return email.lower().strip()


    # --------------------------------------------------------
    # PRODUÇÃO
    #
    # O login Microsoft/Entra fornece o e-mail autenticado.
    # --------------------------------------------------------

    email = request.headers.get(
        "x-ms-client-principal-name"
    )

    if not email:

        raise HTTPException(
            status_code=401,
            detail="Usuário não autenticado."
        )

    return email.lower().strip()


# ------------------------------------------------------------
# BUSCA O USUÁRIO NA TABELA INTERNA
# ------------------------------------------------------------

def get_current_user(request: Request):

    email = get_request_email(
        request
    )

    usuario = fetch_one(

        f"""
        SELECT

            email_usuario,

            nome_usuario,

            perfil,

            ativo

        FROM {DATABASE}.usuario_interno_acesso

        WHERE lower(email_usuario) = lower(?)

          AND ativo = TRUE

        LIMIT 1
        """,

        [email]
    )

    if not usuario:

        raise HTTPException(
            status_code=403,
            detail=(
                "Usuário sem acesso autorizado "
                "à Central de Campanhas."
            )
        )

    return usuario


# ------------------------------------------------------------
# VALIDA PERFIL
# ------------------------------------------------------------

def validate_role(
    usuario,
    allowed_roles
):

    if usuario["perfil"] not in allowed_roles:

        raise HTTPException(
            status_code=403,
            detail=(
                "Seu perfil não possui permissão "
                "para executar esta ação."
            )
        )

    return True