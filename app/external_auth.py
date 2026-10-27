from app.db import (
    DATABASE,
    fetch_one
)


# ============================================================
# NORMALIZAR E-MAIL
# ============================================================

def normalizar_email(
    email: str
):

    if not email:

        raise ValueError(
            "E-mail não informado."
        )


    email_normalizado = (
        email
        .strip()
        .lower()
    )


    if "@" not in email_normalizado:

        raise ValueError(
            "E-mail inválido."
        )


    usuario, dominio = (
        email_normalizado
        .rsplit(
            "@",
            1
        )
    )


    if (
        not usuario
        or
        not dominio
    ):

        raise ValueError(
            "E-mail inválido."
        )


    return {
        "email":
            email_normalizado,

        "dominio":
            dominio
    }


# ============================================================
# IDENTIFICAR EPS PELO DOMÍNIO
# ============================================================

def identificar_eps_por_email(
    email: str
):

    dados_email = normalizar_email(
        email
    )


    dominio = dados_email[
        "dominio"
    ]


    resultado = fetch_one(

        f"""
        SELECT

            eps,

            dominio_email

        FROM {DATABASE}.dim_eps_dominio

        WHERE lower(dominio_email) =
              lower(?)

          AND ativo = TRUE

        LIMIT 1
        """,

        [
            dominio
        ]
    )


    if not resultado:

        raise ValueError(
            "Domínio de e-mail não autorizado "
            "para acesso ao Portal EPS."
        )


    return {

        "email":
            dados_email["email"],

        "dominio":
            dominio,

        "eps":
            resultado["eps"],

        "dominio_autorizado":
            True
    }


# ============================================================
# OBTER USUÁRIO EPS APROVADO
# ============================================================

def obter_usuario_eps_aprovado(
    email: str
):

    # --------------------------------------------------------
    # 1. IDENTIFICAR A EPS PELO DOMÍNIO
    # --------------------------------------------------------

    identificacao = (
        identificar_eps_por_email(
            email
        )
    )

    email_normalizado = (
        identificacao["email"]
    )

    eps_dominio = (
        identificacao["eps"]
    )


    # --------------------------------------------------------
    # 2. LOCALIZAR USUÁRIO APROVADO
    # --------------------------------------------------------

    usuario = fetch_one(
        f"""
        SELECT
            email_usuario,
            nome_usuario,
            eps,
            ativo

        FROM {DATABASE}.usuario_eps_acesso

        WHERE lower(email_usuario) =
              lower(?)

          AND ativo = TRUE

        LIMIT 1
        """,
        [
            email_normalizado
        ]
    )


    if not usuario:

        raise PermissionError(
            "Usuário ainda não possui "
            "acesso aprovado ao Portal EPS."
        )


    eps_usuario = (
        usuario["eps"]
    )


    # --------------------------------------------------------
    # 3. SEGURANÇA
    #
    # EPS gravada no usuário precisa coincidir
    # com a EPS determinada pelo domínio.
    # --------------------------------------------------------

    if eps_usuario != eps_dominio:

        raise PermissionError(
            "Vínculo de EPS incompatível "
            "com o domínio do usuário."
        )


    return {
        "email":
            usuario["email_usuario"],

        "nome_usuario":
            usuario["nome_usuario"],

        "eps":
            eps_usuario,

        "ativo":
            usuario["ativo"]
    }