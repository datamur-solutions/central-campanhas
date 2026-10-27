import asyncio
import os

import traceback

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Response,
)

from fastapi.middleware.cors import CORSMiddleware

from app.db import (
    DATABASE,
    fetch_all,
    fetch_one,
)

from app.auth import (
    get_current_user,
    validate_role,
)

from app.homolog_guard import (
    HomologGuardMiddleware,
)

from app.models import (
    CampaignCreate,
    CommercialValidation,
    EPSReleaseRequest,
    ExternalAccessRequest,
    ExternalAccessDecision,
    EPSOperationalPlanUpdate,
    EPSGoLiveRequest,
    EPSStartExecutionRequest,
    EPSMonitoringUpdate,
    EPSCloseExecutionRequest,
)

from app.campaign_service import (
    criar_campanha,
    enviar_para_comercial,
    validar_comercial,
    liberar_para_eps,
)

from app.external_auth import (
    identificar_eps_por_email,
)

from app.external_service import (
    solicitar_acesso_eps,
    decidir_acesso_eps,
    listar_campanhas_portal_eps,
    obter_campanha_portal_eps,
    salvar_plano_operacional_eps,
    avaliar_prontidao_go_live_eps,
    aprovar_go_live_eps,
    iniciar_execucao_eps,
    registrar_acompanhamento_eps,
    encerrar_execucao_eps,
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from app.meta_eps_service import (
    salvar_metas_eps,
    metas_por_codigo,
    enriquecer_lista_eps,
    enriquecer_detalhe_eps,
    enriquecer_dashboard,
    consolidar_funil_encerramento,
    salvar_observacoes_eps,
)

from app.historico_service import (
    diario_interno,
    diario_eps,
    anexar_historico_dashboard,
    salvar_atuacao_interna,
)

from app.sessao import (
    SessaoMiddleware,
    CabecalhosSegurancaMiddleware,
    gravar_sessao,
    apagar_sessao,
    email_da_sessao,
)
from pathlib import Path

from app.internal_service import (
    obter_detalhe_campanha_interna,
)

from app.internal_monitoring_service import (
    registrar_acompanhamento_interno,
    salvar_funil_encerramento,
)

from app.internal_dashboard_service import (
    carregar_dashboard,
)

from app.atuacao_service import (
    salvar_sugestao_atuacao,
    salvar_atuacao_eps,
    obter_atuacao_interna,
    obter_atuacao_eps,
)



from app.senha_service import (
    status_senha,
    criar_senha,
    conferir_senha,
    trocar_senha,
    redefinir_senha,
    solicitar_redefinicao,
    validar_token,
    redefinir_com_token,
)

from app.campaign_html_auto import (
    atualizar_html_em_background,
)

from app.robo_apuracao_service import (
    ApuracaoPayload,
    ExecucaoPayload,
    validar_chave_robo,
    listar_pendentes,
    registrar_apuracao,
    registrar_execucao,
    carregar_dashboard_apuracao,
    listar_arquivos_robo,
    ler_arquivo_robo,
)


# O HTML automatico da campanha era enviado para um webhook do
# Power Automate, que nao existe mais. Sem a URL configurada,
# cada acao tentava 3 vezes, gastando tempo e conexoes com o
# banco a toa. Sem URL, a rotina simplesmente nao roda.
if not os.getenv("CAMPAIGN_HTML_WEBHOOK_URL", "").strip():
    def atualizar_html_em_background(*args, **kwargs):
        return None



# ============================================================
# API
# ============================================================

from app.internal_v6_service import (
    listar_solicitacoes_acesso_pendentes,
    listar_campanhas_prontas_encerramento,
    encerrar_campanha_edunova,
)

from app.notification_service_v7 import (
    provider_status,
    listar_notificacoes,
    processar_notificacoes,
)

from app.notification_service_v72 import (
    testar_uma_notificacao,
    processar_pendentes_confirmado,
    reprocessar_erros_confirmado,
    arquivar_erros_confirmado,
)

from app.notification_service_v8 import (
    automation_status,
    disparar_automatico_sem_excecao,
    testar_automacao_v8,
)

# A documentacao automatica (/docs, /redoc, /openapi.json)
# lista todas as rotas da API. Fica desligada, a menos que
# DOCS_HABILITADO=true (use so no seu computador).
_DOCS = os.getenv("DOCS_HABILITADO", "false").strip().lower() == "true"

app = FastAPI(
    title="Central de Campanhas Comerciais",
    description="Backend da Central de Campanhas Comerciais EduNova.",
    version="0.1.0",
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)


# Erro inesperado nao devolve detalhe tecnico para a tela
# (nome de tabela, caminho de arquivo, texto do banco). O
# detalhe fica so no log do Render.
@app.exception_handler(Exception)
async def erro_inesperado(request: Request, erro: Exception):
    print("[ERRO]", request.method, request.url.path)
    traceback.print_exception(type(erro), erro, erro.__traceback__)

    return JSONResponse(
        status_code=500,
        content={"detail": "Erro inesperado. Tente novamente em instantes."},
    )

STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static"
)


@app.get("/portal-eps/app", include_in_schema=False)
def portal_eps():

    return FileResponse(
        STATIC_DIR / "eps.html"
    )


@app.get("/portal-interno/app", include_in_schema=False)
def portal_interno():

    return FileResponse(
        STATIC_DIR / "interno.html"
    )


# ============================================================
# CORS
# FRONT-END LOCAL
#
# Em produção, restringir aos domínios oficiais.
# ============================================================

CORS_ORIGINS = [
    origem.strip()
    for origem in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origem.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# TRAVA DE HOMOLOGACAO
#
# Senha unica na frente de toda a aplicacao, para publicar
# numa URL publica sem deixar os dados abertos a quem tiver
# o link. So age quando HOMOLOG_USER e HOMOLOG_PASS estao
# definidos no ambiente: no seu computador, nada muda.
# ============================================================

app.add_middleware(HomologGuardMiddleware)


# ============================================================
# SESSAO E CABECALHOS DE SEGURANCA — ver app/sessao.py
# ============================================================

app.add_middleware(SessaoMiddleware)
app.add_middleware(CabecalhosSegurancaMiddleware)


# ============================================================
# TESTES / SAÚDE
# ============================================================

@app.get("/")
def inicio():
    return {
        "sistema": "Central de Campanhas Comerciais",
        "status": "online",
    }


@app.get("/health")
def health():
    # Rota usada pela plataforma de hospedagem.
    #
    # NAO pode depender do Databricks: se o cluster estiver
    # frio ou lento, a plataforma entende que a aplicacao
    # morreu e reinicia o servico em loop.
    return {
        "api": "ok",
    }


@app.get("/health/db")
def health_db():
    # Checagem profunda, para chamar na mao quando quiser
    # saber se a conexao com o Databricks esta viva.
    try:
        resultado = fetch_one(
            "SELECT 1 AS ok"
        )

        return {
            "api": "ok",
            "banco": resultado["ok"],
        }

    except Exception as erro:
        # O texto do erro de conexao pode trazer host e
        # usuario do banco: vai so para o log.
        print("[HEALTH/DB]", erro)

        raise HTTPException(
            status_code=503,
            detail="Banco indisponível.",
        ) from erro


# ============================================================
# USUÁRIO INTERNO
# ============================================================

@app.get("/api/me")
def me(request: Request):
    usuario = get_current_user(
        request
    )

    return {
        "email": usuario["email_usuario"],
        "nome": usuario["nome_usuario"],
        "perfil": usuario["perfil"],
        "ativo": usuario["ativo"],
    }


# ============================================================
# SENHA — PORTAIS INTERNO E EPS
#
# "portal" no corpo: "interno" ou "eps".
# ============================================================

def _erro_senha(erro):
    if isinstance(erro, PermissionError):
        return HTTPException(status_code=403, detail=str(erro))
    return HTTPException(status_code=400, detail=str(erro))


@app.post("/api/auth/senha/status")
def auth_senha_status(payload: dict):
    try:
        return status_senha(payload.get("portal"), payload.get("email"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro


@app.post("/api/auth/senha/criar")
def auth_senha_criar(payload: dict, response: Response):
    portal = payload.get("portal")
    email = (payload.get("email") or "").strip().lower()

    try:
        resultado = criar_senha(portal, email, payload.get("nova_senha"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro

    # Criou a senha: ja entra, com a sessao gravada no cookie.
    gravar_sessao(response, portal, email)
    return resultado


@app.post("/api/auth/senha/entrar")
def auth_senha_entrar(payload: dict, response: Response):
    portal = payload.get("portal")
    email = (payload.get("email") or "").strip().lower()

    try:
        resultado = conferir_senha(portal, email, payload.get("senha"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro

    gravar_sessao(response, portal, email)
    return resultado


@app.post("/api/auth/senha/trocar")
def auth_senha_trocar(payload: dict, request: Request):
    portal = payload.get("portal")

    # O e-mail vem da sessao, nunca do corpo da chamada.
    email = email_da_sessao(request, portal)

    if not email:
        raise HTTPException(status_code=401, detail="Sua sessão expirou. Entre novamente.")

    try:
        return trocar_senha(
            portal,
            email,
            payload.get("senha_atual"),
            payload.get("nova_senha"),
        )
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro


@app.post("/api/auth/sair")
def auth_sair(payload: dict, response: Response):
    portal = payload.get("portal")

    if portal in ("interno", "eps"):
        apagar_sessao(response, portal)

    return {"sucesso": True}


@app.post("/api/auth/senha/esqueci")
def auth_senha_esqueci(payload: dict):
    try:
        return solicitar_redefinicao(payload.get("portal"), payload.get("email"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro


@app.post("/api/auth/senha/token")
def auth_senha_token(payload: dict):
    try:
        return validar_token(payload.get("token"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro


@app.post("/api/auth/senha/redefinir-token")
def auth_senha_redefinir_token(payload: dict):
    try:
        return redefinir_com_token(payload.get("token"), payload.get("nova_senha"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro


@app.post("/api/internal/usuarios/senha/redefinir")
def auth_senha_redefinir(payload: dict, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["ADMIN"])

    try:
        return redefinir_senha(payload.get("portal"), payload.get("email"))
    except (ValueError, PermissionError) as erro:
        raise _erro_senha(erro) from erro


# ============================================================
# PORTAL INTERNO
# LISTAR CAMPANHAS
# ============================================================

@app.get("/api/internal/campaigns")
def internal_campaigns(
    request: Request,
):
    usuario = get_current_user(
        request
    )

    campanhas = fetch_all(
        f"""
        SELECT
            codigo_campanha,
            nome_campanha,
            produto,
            tipo_acao,
            status_campanha,
            etapa_pop,
            responsavel_planejamento,
            responsavel_comercial,
            dt_inicio_prevista,
            dt_fim_prevista,
            dt_criacao

        FROM {DATABASE}.campanha_master

        ORDER BY dt_criacao DESC
        """
    )

    return {
        "usuario": {
            "email": usuario["email_usuario"],
            "perfil": usuario["perfil"],
        },
        "quantidade": len(campanhas),
        "campanhas": campanhas,
    }


# ============================================================
# PORTAL INTERNO
# VALIDAR CADASTRO
#
# NÃO grava no Databricks.
# ============================================================

@app.post("/api/internal/campaigns/validate")
def validate_campaign(
    payload: CampaignCreate,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    validate_role(
        usuario,
        [
            "PLANEJAMENTO",
            "ADMIN",
        ],
    )

    return {
        "valido": True,
        "mensagem": (
            "Cadastro validado com sucesso. "
            "Nenhum dado foi gravado."
        ),
        "responsavel_planejamento": usuario["email_usuario"],
        "tipo_acao": payload.tipo_acao,
        "nome_campanha": payload.nome_campanha,
        "quantidade_eps": len(payload.eps),
        "eps": payload.eps,
        "quantidade_escopos": len(payload.escopos),
        "quantidade_kpis": len(payload.kpis),
    }


# ============================================================
# PORTAL INTERNO
# CRIAR CAMPANHA
# ============================================================

@app.post(
    "/api/internal/campaigns",
    status_code=201,
)
def create_campaign_endpoint(
    payload: CampaignCreate,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    validate_role(
        usuario,
        [
            "PLANEJAMENTO",
            "ADMIN",
        ],
    )

    resultado = criar_campanha(
        payload,
        usuario["email_usuario"],
    )

    atualizar_html_em_background(
        resultado.get("codigo_campanha")
    )

    return {
        "sucesso": True,
        "mensagem": (
            "Campanha criada com sucesso. "
            "A campanha ainda não está liberada para nenhuma EPS."
        ),
        "campanha": resultado,
    }


# ============================================================
# PORTAL INTERNO
# ENVIAR PARA O COMERCIAL
# ============================================================

@app.post(
    "/api/internal/campaigns/"
    "{codigo_campanha}/send-commercial"
)
def send_campaign_to_commercial(
    codigo_campanha: str,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    validate_role(
        usuario,
        [
            "PLANEJAMENTO",
            "ADMIN",
        ],
    )

    try:
        resultado = enviar_para_comercial(
            codigo_campanha.upper(),
            usuario["email_usuario"],
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Campanha encaminhada para o Comercial."
            ),
            "campanha": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL INTERNO
# VALIDAÇÃO COMERCIAL
# ============================================================

@app.post(
    "/api/internal/campaigns/"
    "{codigo_campanha}/commercial-validation"
)
def commercial_validation_endpoint(
    codigo_campanha: str,
    payload: CommercialValidation,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    validate_role(
        usuario,
        [
            "COMERCIAL",
            "ADMIN",
        ],
    )

    try:
        resultado = validar_comercial(
            codigo_campanha.upper(),
            payload,
            usuario["email_usuario"],
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "campanha": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL INTERNO
# LIBERAR CAMPANHA PARA EPS
# ============================================================

@app.post(
    "/api/internal/campaigns/"
    "{codigo_campanha}/release-eps"
)
def release_eps_endpoint(
    codigo_campanha: str,
    payload: EPSReleaseRequest,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    validate_role(
        usuario,
        [
            "COMERCIAL",
            "ADMIN",
        ],
    )

    try:
        resultado = liberar_para_eps(
            codigo_campanha.upper(),
            payload,
            usuario["email_usuario"],
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Handoff realizado para a(s) EPS selecionada(s)."
            ),
            "campanha": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL INTERNO
# IDENTIFICAR EPS PELO E-MAIL
#
# Antes era /test/external/identify, sem autenticacao.
# Numa URL publica isso permitia descobrir quais e-mails tem
# acesso de EPS, entao agora exige login interno.
# ============================================================

@app.get("/api/internal/external/identify")
def internal_external_identify(
    target_email: str,
    request: Request,
):
    usuario = get_current_user(request)

    validate_role(
        usuario,
        ["PLANEJAMENTO", "COMERCIAL", "ADMIN"],
    )

    try:
        resultado = identificar_eps_por_email(
            target_email
        )

        return {
            "sucesso": True,
            "usuario": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL EPS
# SOLICITAR PRIMEIRO ACESSO
# ============================================================

@app.post("/api/external/access/request")
def external_access_request(
    payload: ExternalAccessRequest,
    request: Request,
):
    try:
        ip_origem = (
            request.client.host
            if request.client
            else None
        )

        user_agent = request.headers.get(
            "user-agent"
        )

        resultado = solicitar_acesso_eps(
            payload.email,
            payload.nome_usuario,
            ip_origem,
            user_agent,
        )

        return {
            "sucesso": True,
            "acesso": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL INTERNO
# DECIDIR SOLICITAÇÃO DE ACESSO EPS
# ============================================================

@app.post(
    "/api/internal/external-access/"
    "{solicitacao_uuid}/decision"
)
def decide_external_access(
    solicitacao_uuid: str,
    payload: ExternalAccessDecision,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    # Aprovar acesso de fornecedor e decisao de governanca:
    # antes qualquer usuario logado conseguia.
    validate_role(
        usuario,
        ["PLANEJAMENTO", "COMERCIAL", "ADMIN"],
    )

    try:
        resultado = decidir_acesso_eps(
            solicitacao_uuid,
            payload.decisao,
            payload.motivo,
            usuario["email_usuario"],
        )

        return {
            "sucesso": True,
            "mensagem": "Decisão registrada com sucesso.",
            "acesso": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL EPS
# LISTAR CAMPANHAS
# ============================================================

@app.get("/api/external/campaigns")
def external_campaigns(
    email: str,
):
    try:
        return enriquecer_lista_eps(
            listar_campanhas_portal_eps(
                email
            )
        )

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro


# ============================================================
# PORTAL EPS
# DETALHAR CAMPANHA
# ============================================================

@app.get(
    "/api/external/campaigns/"
    "{codigo_campanha}"
)
def external_campaign_detail(
    codigo_campanha: str,
    email: str,
):
    try:
        return enriquecer_detalhe_eps(
            obter_campanha_portal_eps(
                email,
                codigo_campanha.upper(),
            )
        )

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro


# ============================================================
# FASE 7A
# PORTAL EPS
# ATUALIZAR PLANO OPERACIONAL
# ============================================================

@app.patch(
    "/api/external/campaigns/"
    "{codigo_campanha}/operational-plan"
)
def update_external_operational_plan(
    codigo_campanha: str,
    payload: EPSOperationalPlanUpdate,
    email: str,
):
    try:
        resultado = salvar_plano_operacional_eps(
            email,
            codigo_campanha.upper(),
            payload,
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Plano operacional atualizado com sucesso."
            ),
            "plano": resultado,
        }

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# FASE 7B
# PORTAL EPS
# CHECKLIST DE PRONTIDÃO
# ============================================================

@app.get(
    "/api/external/campaigns/"
    "{codigo_campanha}/readiness"
)
def external_campaign_readiness(
    codigo_campanha: str,
    email: str,
):
    try:
        return avaliar_prontidao_go_live_eps(
            email,
            codigo_campanha.upper(),
        )

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# FASE 7B
# PORTAL EPS
# APROVAR GO-LIVE
# ============================================================

@app.post(
    "/api/external/campaigns/"
    "{codigo_campanha}/go-live"
)
def external_campaign_go_live(
    codigo_campanha: str,
    payload: EPSGoLiveRequest,
    email: str,
):
    try:
        resultado = aprovar_go_live_eps(
            email,
            codigo_campanha.upper(),
            payload,
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": "Go-Live aprovado com sucesso.",
            "go_live": resultado,
        }

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# FASE 7C
# PORTAL EPS
# INICIAR EXECUÇÃO
# ============================================================

@app.post(
    "/api/external/campaigns/"
    "{codigo_campanha}/start-execution"
)
def external_campaign_start_execution(
    codigo_campanha: str,
    payload: EPSStartExecutionRequest,
    email: str,
):
    try:
        resultado = iniciar_execucao_eps(
            email,
            codigo_campanha.upper(),
            payload,
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Execução da campanha iniciada com sucesso."
            ),
            "execucao": resultado,
        }

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# FASE 7D
# PORTAL EPS
# REGISTRAR ACOMPANHAMENTO
# ============================================================

@app.post(
    "/api/external/campaigns/"
    "{codigo_campanha}/monitoring"
)
def external_campaign_monitoring(
    codigo_campanha: str,
    payload: EPSMonitoringUpdate,
    email: str,
):
    try:
        resultado = registrar_acompanhamento_eps(
            email,
            codigo_campanha.upper(),
            payload,
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Acompanhamento registrado com sucesso."
            ),
            "acompanhamento": resultado,
        }

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# FASE 7E
# PORTAL EPS
# ENCERRAR EXECUÇÃO
# ============================================================

@app.post(
    "/api/external/campaigns/"
    "{codigo_campanha}/close-execution"
)
def external_campaign_close_execution(
    codigo_campanha: str,
    payload: EPSCloseExecutionRequest,
    email: str,
):
    try:
        resultado = encerrar_execucao_eps(
            email,
            codigo_campanha.upper(),
            payload,
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Execução da EPS finalizada com sucesso."
            ),
            "encerramento": resultado,
        }

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


@app.get(
    "/api/internal/campaigns/"
    "{codigo_campanha}"
)
def internal_campaign_detail(
    codigo_campanha: str,
    request: Request,
):
    usuario = get_current_user(
        request
    )

    validate_role(
        usuario,
        [
            "PLANEJAMENTO",
            "COMERCIAL",
            "ADMIN",
        ],
    )

    try:
        return obter_detalhe_campanha_interna(
            codigo_campanha.upper()
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=404,
            detail=str(erro),
        ) from erro


# ============================================================
# V6 — ACESSOS EPS PENDENTES
# ============================================================

@app.get("/api/internal/external-access/pending")
def internal_pending_external_access(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    solicitacoes = listar_solicitacoes_acesso_pendentes()
    return {
        "quantidade": len(solicitacoes),
        "solicitacoes": solicitacoes,
    }


# ============================================================
# V6 — CAMPANHAS PRONTAS PARA ENCERRAMENTO
# ============================================================

@app.get("/api/internal/closure-ready")
def internal_closure_ready(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    campanhas = listar_campanhas_prontas_encerramento()
    return {
        "quantidade": len(campanhas),
        "campanhas": campanhas,
    }


# ============================================================
# V6 — ENCERRAMENTO EDUNOVA
# ============================================================

@app.post("/api/internal/campaigns/{codigo_campanha}/close-edunova")
def internal_close_edunova(codigo_campanha: str, payload: dict, request: Request):
    usuario = get_current_user(request)

    # O encerramento e a apuracao de resultado sao do
    # Planejamento. O Comercial acompanha, mas nao fecha.
    validate_role(usuario, ["PLANEJAMENTO", "ADMIN"])
    email_usuario = (
        usuario.get("email_usuario")
        or usuario.get("email")
        or "PORTAL_INTERNO"
    )

    try:
        # Funil por EPS: grava cada um e troca o consolidado
        # do payload pela soma. Vem antes do encerramento para
        # que um numero invalido barre tudo, e nao deixe a
        # campanha encerrada sem funil.
        payload = consolidar_funil_encerramento(
            codigo_campanha.upper(),
            payload,
            email_usuario,
        )

        resultado = encerrar_campanha_edunova(
            codigo_campanha.upper(),
            payload.get("decisao", ""),
            payload.get("resumo", ""),
            payload.get("aprendizados", ""),
            email_usuario,
        )

        # O funil vem no mesmo envio, mas e gravado depois:
        # a campanha ja esta encerrada neste ponto, e os
        # numeros complementam esse registro.
        funil = salvar_funil_encerramento(
            codigo_campanha.upper(),
            payload,
            email_usuario,
        )

        atualizar_html_em_background(
            codigo_campanha.upper()
        )

        return {
            "sucesso": True,
            "mensagem": "Campanha encerrada com sucesso.",
            "encerramento": resultado,
            "funil": funil,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# METAS POR EPS
#
# Leitura: Planejamento, Comercial e Admin.
# Edicao: Planejamento e Admin.
# ============================================================

@app.get("/api/internal/campaigns/{codigo_campanha}/metas-eps")
def internal_metas_eps(codigo_campanha: str, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])

    try:
        return metas_por_codigo(codigo_campanha.upper())
    except ValueError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


@app.put("/api/internal/campaigns/{codigo_campanha}/metas-eps")
def internal_salvar_metas_eps(codigo_campanha: str, payload: dict, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "ADMIN"])

    try:
        return salvar_metas_eps(
            codigo_campanha.upper(),
            payload,
            usuario["email_usuario"],
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


# ============================================================
# DIARIO DE BORDO
# ============================================================

@app.get("/api/internal/campaigns/{codigo_campanha}/diario")
def internal_diario(codigo_campanha: str, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])

    try:
        return diario_interno(codigo_campanha.upper())
    except ValueError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


# Canais e copy de uma EPS preenchidos pelo Comercial, em
# qualquer etapa da campanha (inclusive em execucao).
@app.put("/api/internal/campaigns/{codigo_campanha}/atuacao-eps")
def internal_salvar_atuacao_eps(codigo_campanha: str, payload: dict, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["COMERCIAL", "ADMIN"])

    try:
        return salvar_atuacao_interna(
            codigo_campanha.upper(),
            payload.get("eps"),
            payload,
            usuario["email_usuario"],
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.get("/api/external/campaigns/{codigo_campanha}/diario")
def external_diario(codigo_campanha: str, email: str):
    try:
        return diario_eps(email, codigo_campanha.upper())
    except (PermissionError, ValueError) as erro:
        raise HTTPException(status_code=403, detail=str(erro)) from erro


# Observacoes por EPS. O perfil define qual observacao pode
# ser gravada: Planejamento escreve a do Planejamento, o
# Comercial escreve a do Comercial. Admin escreve as duas.
@app.put("/api/internal/campaigns/{codigo_campanha}/observacoes-eps")
def internal_salvar_observacoes_eps(codigo_campanha: str, payload: dict, request: Request):
    usuario = get_current_user(request)

    tipo = str(payload.get("tipo") or "").strip().upper()

    permitidos = {
        "PLANEJAMENTO": ["PLANEJAMENTO", "ADMIN"],
        "COMERCIAL": ["COMERCIAL", "ADMIN"],
    }.get(tipo)

    if not permitidos:
        raise HTTPException(status_code=400, detail="Tipo de observação inválido.")

    validate_role(usuario, permitidos)

    try:
        return salvar_observacoes_eps(
            codigo_campanha.upper(),
            tipo,
            payload.get("observacoes") or {},
            usuario["email_usuario"],
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


# ============================================================
# ATUACAO POR CANAL E COPY DE WHATSAPP
#
# Planejamento sugere os canais; cada EPS define a forma
# definitiva e registra a copy de WhatsApp. Tudo opcional, e
# so faz sentido quando a acao tem mailing.
# ============================================================

@app.post("/api/internal/campaigns/{codigo_campanha}/atuacao")
def internal_salvar_atuacao(
    codigo_campanha: str,
    payload: dict,
    request: Request,
):
    usuario = get_current_user(request)

    validate_role(usuario, ["PLANEJAMENTO", "ADMIN"])

    email_usuario = (
        usuario.get("email_usuario")
        or usuario.get("email")
        or "PORTAL_INTERNO"
    )

    try:
        return salvar_sugestao_atuacao(
            codigo_campanha.upper(),
            payload,
            email_usuario,
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


@app.get("/api/internal/campaigns/{codigo_campanha}/atuacao")
def internal_ler_atuacao(
    codigo_campanha: str,
    request: Request,
):
    usuario = get_current_user(request)

    validate_role(
        usuario,
        ["PLANEJAMENTO", "COMERCIAL", "ADMIN"],
    )

    try:
        return obter_atuacao_interna(
            codigo_campanha.upper()
        )

    except ValueError as erro:
        raise HTTPException(
            status_code=404,
            detail=str(erro),
        ) from erro


@app.post("/api/external/campaigns/{codigo_campanha}/atuacao")
def external_salvar_atuacao(
    codigo_campanha: str,
    payload: dict,
    email: str,
):
    try:
        return salvar_atuacao_eps(
            email,
            codigo_campanha.upper(),
            payload,
        )

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


@app.get("/api/external/campaigns/{codigo_campanha}/atuacao")
def external_ler_atuacao(
    codigo_campanha: str,
    email: str,
):
    try:
        return obter_atuacao_eps(
            email,
            codigo_campanha.upper(),
        )

    except PermissionError as erro:
        raise HTTPException(
            status_code=403,
            detail=str(erro),
        ) from erro

    except ValueError as erro:
        raise HTTPException(
            status_code=404,
            detail=str(erro),
        ) from erro


# ============================================================
# DASHBOARD DE CAMPANHAS
#
# Visao consolidada de ativas e encerradas. Devolve a lista
# completa: os filtros acontecem no navegador, para responder
# sem ida ao servidor a cada clique.
# ============================================================

@app.get("/api/internal/dashboard")
def internal_dashboard(request: Request):
    usuario = get_current_user(request)

    validate_role(
        usuario,
        ["PLANEJAMENTO", "COMERCIAL", "ADMIN"],
    )

    return anexar_historico_dashboard(
        enriquecer_dashboard(
            carregar_dashboard()
        )
    )


# ============================================================
# ACOMPANHAMENTO INTERNO DA CAMPANHA
#
# Comercial e Planejamento registram o andamento diario de
# uma campanha que esta com as EPS. O preenchimento e
# opcional: serve para registrar o que o time interno
# observa, sem depender do fornecedor.
# ============================================================

@app.post(
    "/api/internal/campaigns/"
    "{codigo_campanha}/monitoring"
)
def internal_campaign_monitoring(
    codigo_campanha: str,
    payload: dict,
    request: Request,
):
    usuario = get_current_user(request)

    validate_role(
        usuario,
        ["PLANEJAMENTO", "COMERCIAL", "ADMIN"],
    )

    email_usuario = (
        usuario.get("email_usuario")
        or usuario.get("email")
        or "PORTAL_INTERNO"
    )

    try:
        resultado = registrar_acompanhamento_interno(
            codigo_campanha.upper(),
            payload,
            email_usuario,
        )

        return {
            "sucesso": True,
            "mensagem": (
                "Acompanhamento registrado com sucesso."
            ),
            "acompanhamento": resultado,
        }

    except ValueError as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# V7 — CENTRAL DE NOTIFICAÇÕES
# ============================================================

@app.get("/api/internal/notifications")
def internal_notifications(request: Request, limit: int = 100):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    return listar_notificacoes(limit=limit)


@app.get("/api/internal/notifications/provider-status")
def internal_notifications_provider_status(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    return provider_status()


@app.post("/api/internal/notifications/process-legacy-disabled")
def internal_notifications_process(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])

    try:
        return processar_notificacoes(limite=30)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


# ============================================================
# V7.2 — SEGURANÇA DE DISPARO
# ============================================================

@app.post("/api/internal/notifications/test-one")
def internal_notifications_test_one(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    email_usuario = usuario.get("email_usuario") or usuario.get("email")
    if not email_usuario:
        raise HTTPException(status_code=400, detail="Não foi possível identificar o e-mail do usuário interno.")
    try:
        return testar_uma_notificacao(email_usuario)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.post("/api/internal/notifications/process-confirmed")
def internal_notifications_process_confirmed(payload: dict, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    try:
        return processar_pendentes_confirmado(
            bool(payload.get("confirmar")),
            int(payload.get("quantidade_esperada", -1)),
        )
    except (ValueError, TypeError) as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.post("/api/internal/notifications/retry-errors-confirmed")
def internal_notifications_retry_errors_confirmed(payload: dict, request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    try:
        return reprocessar_erros_confirmado(
            bool(payload.get("confirmar")),
            int(payload.get("quantidade_esperada", -1)),
        )
    except (ValueError, TypeError) as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


# ============================================================
# V7.2.3 — ARQUIVAMENTO SEGURO DE ERROS
# ============================================================

@app.post("/api/internal/notifications/archive-errors-confirmed")
def internal_notifications_archive_errors_confirmed(
    payload: dict,
    request: Request,
):
    usuario = get_current_user(request)

    validate_role(
        usuario,
        ["PLANEJAMENTO", "COMERCIAL", "ADMIN"],
    )

    email_usuario = (
        usuario.get("email_usuario")
        or usuario.get("email")
        or "PORTAL_INTERNO"
    )

    try:
        return arquivar_erros_confirmado(
            bool(payload.get("confirmar")),
            int(payload.get("quantidade_esperada", -1)),
            email_usuario,
        )

    except (ValueError, TypeError) as erro:
        raise HTTPException(
            status_code=400,
            detail=str(erro),
        ) from erro


# ============================================================
# V8 — ENVIO AUTOMÁTICO DE NOTIFICAÇÕES
# ============================================================

@app.get("/api/internal/notifications/automation-status")
def internal_notifications_automation_status(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    return automation_status()


@app.post("/api/internal/notifications/automation-test")
def internal_notifications_automation_test(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    email_usuario = usuario.get("email_usuario") or usuario.get("email")
    if not email_usuario:
        raise HTTPException(status_code=400, detail="Não foi possível identificar o e-mail do usuário interno.")
    try:
        return testar_automacao_v8(email_usuario)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.middleware("http")
async def v8_auto_notification_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    method = request.method.upper()
    mutacao_api = (
        method in {"POST", "PATCH", "PUT", "DELETE"}
        and path.startswith("/api/")
    )
    rota_notificacao = path.startswith("/api/internal/notifications")
    sucesso = 200 <= response.status_code < 300
    if mutacao_api and sucesso and not rota_notificacao:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, disparar_automatico_sem_excecao)
    return response


# ============================================================
# V9.3.1 — TELAS DE LOGIN
# ============================================================

STATIC_DIR_V931 = Path(__file__).resolve().parent / "static"

@app.get("/portal-interno")
def portal_interno_login_v931():
    return FileResponse(STATIC_DIR_V931 / "login_interno.html")

@app.get("/portal-eps")
def portal_eps_login_v931():
    return FileResponse(STATIC_DIR_V931 / "login_eps.html")


@app.get("/redefinir-senha", include_in_schema=False)
def pagina_redefinir_senha():
    return FileResponse(STATIC_DIR_V931 / "redefinir_senha.html")


# ============================================================
# ROBO DE APURACAO — FUNIL PARALELO
#
# Rotas /api/robo/*: so o robo da VM, com a chave do
# cabecalho X-Robo-Key (variavel ROBO_API_KEY no Render).
# Rota /api/internal/apuracao/dashboard: aba Dashboard.
# Regras em app/robo_apuracao_service.py.
# ============================================================

def _exigir_robo(request: Request):
    try:
        validar_chave_robo(request.headers.get("x-robo-key"))
    except PermissionError as erro:
        raise HTTPException(status_code=401, detail=str(erro)) from erro


@app.get("/api/robo/pendentes", include_in_schema=False)
def robo_pendentes(request: Request):
    _exigir_robo(request)
    return listar_pendentes()


@app.post("/api/robo/apuracao/{codigo_campanha}", include_in_schema=False)
def robo_registrar_apuracao(
    codigo_campanha: str,
    payload: ApuracaoPayload,
    request: Request,
):
    _exigir_robo(request)

    try:
        return {
            "sucesso": True,
            "apuracao": registrar_apuracao(codigo_campanha, payload),
        }
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro


@app.post("/api/robo/execucao", include_in_schema=False)
def robo_registrar_execucao(payload: ExecucaoPayload, request: Request):
    _exigir_robo(request)
    return registrar_execucao(payload)


@app.get("/api/robo/arquivos", include_in_schema=False)
def robo_listar_arquivos(request: Request):
    _exigir_robo(request)
    return listar_arquivos_robo()


@app.get("/api/robo/arquivo/{nome}", include_in_schema=False)
def robo_baixar_arquivo(nome: str, request: Request):
    _exigir_robo(request)

    try:
        return PlainTextResponse(ler_arquivo_robo(nome), media_type="text/x-python; charset=utf-8")
    except FileNotFoundError as erro:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.") from erro


@app.get("/api/internal/apuracao/dashboard")
def internal_apuracao_dashboard(request: Request):
    usuario = get_current_user(request)
    validate_role(usuario, ["PLANEJAMENTO", "COMERCIAL", "ADMIN"])
    return carregar_dashboard_apuracao()