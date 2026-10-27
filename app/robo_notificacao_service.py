"""
NOTIFICACOES DO ROBO DE APURACAO

Modulo novo. Reaproveita o envio por e-mail que a Central ja
usa (app/email_service.py, pelo Brevo). Nao mexe na fila de
notificacoes das campanhas.

Quem recebe:
  - ALERTA (robo nao conseguiu apurar): Admin + Planejamento
  - CAMPANHA APURADA (todas as EPS com apuracao final):
    Admin + Planejamento + Comercial
  - EPS nunca recebe.

Os destinatarios saem da tabela usuario_interno_acesso (perfil
e ativo). A variavel ROBO_ALERTA_EMAILS, se preenchida, troca a
lista dos alertas (separe os e-mails por virgula).

Para nao lotar a caixa: no maximo um e-mail por campanha x EPS
x motivo por dia, controlado na tabela apuracao_alerta.

O envio roda em segundo plano: se o e-mail falhar, a apuracao
continua gravada e o erro fica registrado em apuracao_alerta.
"""

import os
import threading
import uuid

from datetime import datetime, timedelta, timezone

from app.db import (
    DATABASE,
    fetch_all,
    get_connection,
)

from app.email_service import (
    base_url,
    enviar_email,
    montar_html,
    separar_emails,
    status_email,
)


FUSO_BRASILIA = timezone(timedelta(hours=-3))

PERFIS_ALERTA = ("ADMIN", "PLANEJAMENTO")
PERFIS_APURADA = ("ADMIN", "PLANEJAMENTO", "COMERCIAL")

NOMES_EPS = {"VOXA": "VOXA", "LUMEN": "Lumen", "PRISMA": "Prisma"}

# Motivo -> (titulo curto, o que fazer)
MOTIVOS = {
    "MAILING_AUSENTE": (
        "Mailing não encontrado",
        "Suba o arquivo mailing_<código>.csv ou .xlsx na pasta mailing do Databricks "
        "(lakehouse › comercial › contact_center). O robô tenta de novo na próxima hora.",
    ),
    "SEM_RESULTADO": (
        "Campanha sem resultado",
        "A apuração rodou, mas não encontrou nenhum lead acionado nem matrícula. "
        "Confira se o mailing é o certo (CPF e EPS) e se a EPS realmente executou a campanha.",
    ),
    "CAM_NAO_ENCONTRADO": (
        "Código da campanha não encontrado no painel da EPS",
        "A EPS não usou o código CAM no nome da campanha no painel dela. Peça para a EPS ajustar.",
    ),
    "BASE_ATRASADA": (
        "Base do Databricks atrasada",
        "A data base de D-1 não chegou no horário esperado. Acione o time de dados.",
    ),
    "PAINEL_INDISPONIVEL": (
        "Painel da EPS fora do ar",
        "O robô não conseguiu acessar o painel da EPS. Ele tenta de novo a cada hora; "
        "se persistir, confira login e senha do painel.",
    ),
    "REGRA_SEM_DE_PARA": (
        "Combinação sem regra de apuração",
        "A campanha tem um produto, modalidade, supercanal ou frente que ainda não tem de-para "
        "no robô. Ajuste o regras_campanha.py na VM.",
    ),
    "ERRO_PROCESSO": (
        "Erro no processo de apuração",
        "Falha inesperada do robô (rede, Databricks ou código). A mensagem técnica está abaixo.",
    ),
}


# ============================================================
# AUXILIARES
# ============================================================

def _hoje_brasilia():
    return datetime.now(FUSO_BRASILIA).date()


def _agora():
    return datetime.now(timezone.utc)


def _nome_eps(eps):
    return NOMES_EPS.get(eps or "", eps or "")


def _em_segundo_plano(funcao, *args):
    def rodar():
        try:
            funcao(*args)
        except Exception as erro:  # nunca derruba a apuracao
            print("[ROBO-NOTIFICACAO] ERRO:", erro)

    threading.Thread(target=rodar, daemon=True).start()


def destinatarios(perfis):
    """E-mails dos usuarios internos ativos com os perfis pedidos."""
    if perfis == PERFIS_ALERTA:
        fixos = separar_emails(os.getenv("ROBO_ALERTA_EMAILS", ""))
        if fixos:
            return fixos

    linhas = fetch_all(f"SELECT * FROM {DATABASE}.usuario_interno_acesso")
    emails = []

    for linha in linhas:
        email = (linha.get("email_usuario") or linha.get("email") or "").strip().lower()
        perfil = str(linha.get("perfil") or "").strip().upper()
        ativo = linha.get("ativo", True)

        if email and perfil in perfis and ativo not in (False, 0, "false", "FALSE", "N"):
            emails.append(email)

    return sorted(set(emails))


def _ja_enviado(codigo, eps, motivo, so_hoje=True):
    filtro_dia = "AND dia = ?" if so_hoje else ""
    parametros = [codigo or "", eps or "", motivo] + ([_hoje_brasilia()] if so_hoje else [])
    linhas = fetch_all(
        f"""
        SELECT 1 AS existe
        FROM {DATABASE}.apuracao_alerta
        WHERE coalesce(codigo_campanha, '') = ?
          AND coalesce(eps, '') = ?
          AND motivo = ?
          {filtro_dia}
          AND status_envio = 'ENVIADO'
        LIMIT 1
        """,
        parametros,
    )
    return bool(linhas)


def _registrar_alerta(codigo, eps, motivo, para, status, erro=None):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            INSERT INTO {DATABASE}.apuracao_alerta
            (alerta_uuid, codigo_campanha, eps, motivo, dia, destinatarios, status_envio, erro_envio, dt_criacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            parameters=[
                str(uuid.uuid4()), codigo, eps, motivo, _hoje_brasilia(),
                ", ".join(para), status, (str(erro)[:1000] if erro else None), _agora(),
            ],
        )


def _botao():
    url = base_url()
    return ("Abrir o Dashboard", url + "/portal-interno") if url else None


# ============================================================
# 1. ALERTA: o robo nao conseguiu apurar
# ============================================================

def _enviar_alerta(codigo, eps, motivo, mensagem):
    motivo = motivo if motivo in MOTIVOS else "ERRO_PROCESSO"

    if not status_email().get("configurado"):
        print("[ROBO-NOTIFICACAO] e-mail nao configurado; alerta nao enviado.")
        return

    if _ja_enviado(codigo, eps, motivo):
        return

    para = destinatarios(PERFIS_ALERTA)
    if not para:
        print("[ROBO-NOTIFICACAO] sem destinatarios para alerta.")
        return

    titulo_motivo, o_que_fazer = MOTIVOS[motivo]
    alvo = " · ".join(p for p in [codigo, _nome_eps(eps)] if p) or "Robô de apuração"
    assunto = f"[Robô de apuração] {titulo_motivo} | {alvo}"

    paragrafos = [o_que_fazer]
    if mensagem:
        paragrafos.append(f"Detalhe: {mensagem}")

    html = montar_html(
        titulo=f"{titulo_motivo}",
        paragrafos=paragrafos,
        detalhes=[("Campanha", codigo), ("EPS", _nome_eps(eps)), ("Motivo", titulo_motivo)],
        botao=_botao(),
    )
    texto = "\n".join([titulo_motivo, "", *paragrafos, "", f"Campanha: {codigo or '-'}", f"EPS: {_nome_eps(eps) or '-'}"])

    try:
        enviar_email(para=para, cc=None, assunto=assunto, html_corpo=html, texto=texto)
        _registrar_alerta(codigo, eps, motivo, para, "ENVIADO")
    except Exception as erro:
        _registrar_alerta(codigo, eps, motivo, para, "ERRO", erro)
        raise


def notificar_alerta(codigo, eps, motivo, mensagem):
    _em_segundo_plano(_enviar_alerta, codigo, eps, motivo, mensagem)


# ============================================================
# 2. CAMPANHA APURADA: todas as EPS com apuracao FINAL
# ============================================================

def _enviar_campanha_apurada(codigo):
    if not status_email().get("configurado"):
        return

    vinculos = fetch_all(
        f"""
        SELECT ce.eps, af.status_apuracao, af.leads_acionados, af.vendas,
               af.matriculas, af.meta_eps, af.atingimento, af.meta_base,
               m.nome_campanha
        FROM {DATABASE}.campanha_master m
        INNER JOIN {DATABASE}.campanha_eps ce
            ON ce.campaign_uuid = m.campaign_uuid
        LEFT JOIN {DATABASE}.apuracao_funil af
            ON af.codigo_campanha = upper(m.codigo_campanha)
           AND af.eps = ce.eps
        WHERE upper(m.codigo_campanha) = ?
        """,
        [codigo],
    )

    if not vinculos or any(v.get("status_apuracao") != "FINAL" for v in vinculos):
        return  # ainda falta EPS: avisa quando a ultima fechar

    # Aviso de campanha apurada sai uma vez so, em qualquer dia.
    if _ja_enviado(codigo, "", "CAMPANHA_APURADA", so_hoje=False):
        return

    para = destinatarios(PERFIS_APURADA)
    if not para:
        return

    nome = vinculos[0].get("nome_campanha") or codigo
    num = lambda v: "-" if v is None else f"{int(v):,}".replace(",", ".")

    matriculas = sum(int(v.get("matriculas") or 0) for v in vinculos)
    metas = [v for v in vinculos if v.get("meta_eps")]
    meta_total = sum(float(v["meta_eps"]) for v in metas)
    realizado_meta = sum(
        int((v.get("vendas") if v.get("meta_base") == "VENDAS" else v.get("matriculas")) or 0)
        for v in metas
    )

    resumo = f"A apuração da campanha foi concluída: {num(matriculas)} matrículas no total."
    if meta_total:
        resumo += f" Atingimento de {round(realizado_meta / meta_total * 100)}% da meta ({num(realizado_meta)} de {num(meta_total)})."

    detalhes = [("Campanha", f"{codigo} · {nome}")]
    for v in vinculos:
        linha = f"{num(v.get('matriculas'))} matrículas"
        if v.get("leads_acionados") is not None:
            linha += f" · {num(v.get('vendas'))} vendas · {num(v.get('leads_acionados'))} leads"
        if v.get("atingimento") is not None:
            linha += f" · {round(float(v['atingimento']))}% da meta"
        detalhes.append((_nome_eps(v.get("eps")), linha))

    html = montar_html(
        titulo=f"Campanha apurada: {nome}",
        paragrafos=[resumo, "O funil completo, as tabulações e a curva de matrículas estão na aba Dashboard."],
        detalhes=detalhes,
        botao=_botao(),
    )
    texto = "\n".join([f"Campanha apurada: {nome}", "", resumo, ""] + [f"{d[0]}: {d[1]}" for d in detalhes])

    try:
        enviar_email(para=para, cc=None, assunto=f"[Central de Campanhas] {codigo} apurada", html_corpo=html, texto=texto)
        _registrar_alerta(codigo, "", "CAMPANHA_APURADA", para, "ENVIADO")
    except Exception as erro:
        _registrar_alerta(codigo, "", "CAMPANHA_APURADA", para, "ERRO", erro)
        raise


def notificar_campanha_apurada(codigo):
    _em_segundo_plano(_enviar_campanha_apurada, codigo)