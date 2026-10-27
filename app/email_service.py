"""
ENVIO DE E-MAIL — BREVO

Substitui o Power Automate. O envio e uma chamada HTTPS para
a API do Brevo, que o Render gratuito nao bloqueia (ele
bloqueia so as portas SMTP).

Variaveis de ambiente:
  BREVO_API_KEY          chave de API do Brevo
  EMAIL_REMETENTE        e-mail do remetente verificado no Brevo
  EMAIL_REMETENTE_NOME   nome exibido (padrao: Central de Campanhas)
  APP_BASE_URL           endereco publico da aplicacao
  EMAIL_DOMINIO_INTERNO  dominio dos usuarios internos
                         (padrao: edunova.com.br)
"""

import html
import json
import os
import re
import urllib.error
import urllib.request


BREVO_URL = "https://api.brevo.com/v3/smtp/email"


# ------------------------------------------------------------
# CONFIGURACAO
# ------------------------------------------------------------

def _env(nome, padrao=""):
    return (os.getenv(nome, padrao) or "").strip()


def base_url():
    return _env("APP_BASE_URL").rstrip("/")


def email_configurado():
    return bool(_env("BREVO_API_KEY") and _env("EMAIL_REMETENTE"))


def status_email():
    return {
        "provider": "BREVO",
        "configurado": email_configurado(),
        "variavel_env": "BREVO_API_KEY",
    }


# ------------------------------------------------------------
# DESTINATARIOS
# ------------------------------------------------------------

def separar_emails(valor):
    """
    Aceita string com ; , ou espaco, ou uma lista.
    Remove repetidos e mantem a ordem.
    """
    if not valor:
        return []

    if isinstance(valor, (list, tuple)):
        partes = [str(v) for v in valor]
    else:
        partes = re.split(r"[;,\s]+", str(valor))

    vistos = []

    for parte in partes:
        email = parte.strip().lower()

        if email and "@" in email and email not in vistos:
            vistos.append(email)

    return vistos


# ------------------------------------------------------------
# ENVIO
# ------------------------------------------------------------

def enviar_email(para, assunto, html_corpo, texto=None, cc=None):
    """Envia um e-mail. Levanta excecao se falhar."""

    if not email_configurado():
        raise ValueError(
            "Envio de e-mail não configurado. Defina BREVO_API_KEY "
            "e EMAIL_REMETENTE nas variáveis de ambiente."
        )

    destinatarios = separar_emails(para)
    copias = [e for e in separar_emails(cc) if e not in destinatarios]

    if not destinatarios:
        raise ValueError("Notificação sem destinatário.")

    corpo = {
        "sender": {
            "email": _env("EMAIL_REMETENTE"),
            "name": _env("EMAIL_REMETENTE_NOME", "Central de Campanhas"),
        },
        "to": [{"email": e} for e in destinatarios],
        "subject": assunto or "Central de Campanhas",
        "htmlContent": html_corpo,
    }

    if copias:
        corpo["cc"] = [{"email": e} for e in copias]

    if texto:
        corpo["textContent"] = texto

    requisicao = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
        headers={
            "api-key": _env("BREVO_API_KEY"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            if resposta.status < 200 or resposta.status >= 300:
                raise RuntimeError(f"Brevo respondeu HTTP {resposta.status}.")

    except urllib.error.HTTPError as erro:
        detalhe = ""
        try:
            detalhe = erro.read().decode("utf-8")[:300]
        except Exception:
            pass

        raise RuntimeError(
            f"Brevo respondeu HTTP {erro.code}. {detalhe}".strip()
        ) from erro

    except urllib.error.URLError as erro:
        raise RuntimeError(
            f"Falha ao acessar o Brevo: {erro.reason}"
        ) from erro


# ------------------------------------------------------------
# MODELO HTML
#
# E-mail nao aceita CSS externo nem boa parte do CSS moderno:
# tudo inline, em tabela, com fonte de sistema.
# ------------------------------------------------------------

_TINTA = "#17161B"
_TINTA_2 = "#5F5D68"
_TINTA_3 = "#8B8379"
_PAPEL = "#F3EFE7"
_SUPERFICIE = "#FFFFFF"
_FIO = "#DFD8CC"
_DESTAQUE = "#6B21C8"


def _esc(valor):
    return html.escape(str(valor or ""))


def montar_html(titulo, paragrafos=None, detalhes=None, botao=None, rodape=None):
    """
    titulo     texto principal
    paragrafos lista de textos (quebras de linha viram <br>)
    detalhes   lista de (rotulo, valor), vira uma pequena tabela
    botao      (texto, url)
    rodape     texto pequeno no fim
    """
    blocos = []

    for texto in paragrafos or []:
        if not texto:
            continue

        blocos.append(
            f'<p style="margin:0 0 16px;color:{_TINTA_2};font-size:15px;line-height:1.55">'
            f'{_esc(texto).replace(chr(10), "<br>")}</p>'
        )

    linhas = [
        (rotulo, valor)
        for rotulo, valor in (detalhes or [])
        if valor not in (None, "")
    ]

    if linhas:
        celulas = "".join(
            f'<tr>'
            f'<td style="padding:10px 0;border-top:1px solid {_FIO};color:{_TINTA_3};'
            f'font-size:13px;width:38%;vertical-align:top">{_esc(rotulo)}</td>'
            f'<td style="padding:10px 0;border-top:1px solid {_FIO};color:{_TINTA};'
            f'font-size:14px;font-weight:600;vertical-align:top">{_esc(valor)}</td>'
            f'</tr>'
            for rotulo, valor in linhas
        )

        blocos.append(
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="margin:4px 0 20px;border-collapse:collapse">{celulas}</table>'
        )

    if botao and botao[1]:
        texto_botao, url = botao
        blocos.append(
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin:8px 0 8px">'
            f'<tr><td style="background:{_TINTA};border-radius:6px">'
            f'<a href="{_esc(url)}" style="display:inline-block;padding:13px 22px;'
            f'color:#FFFFFF;font-size:15px;font-weight:600;text-decoration:none">'
            f'{_esc(texto_botao)}</a></td></tr></table>'
            f'<p style="margin:12px 0 0;color:{_TINTA_3};font-size:12px;line-height:1.5">'
            f'Se o botão não abrir, copie este endereço no navegador:<br>'
            f'<span style="color:{_TINTA_2};word-break:break-all">{_esc(url)}</span></p>'
        )

    texto_rodape = rodape or (
        "Mensagem automática da Central de Campanhas Comerciais · "
        "EduNova Educação. Não responda este e-mail."
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<body style="margin:0;padding:0;background:{_PAPEL}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{_PAPEL}">
<tr><td align="center" style="padding:32px 14px">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="max-width:560px;font-family:Segoe UI,Arial,sans-serif">
    <tr><td style="padding:18px 28px;background:{_TINTA};border-radius:10px 10px 0 0">
      <span style="color:#FFFFFF;font-size:15px;font-weight:600">Central de Campanhas</span>
      <span style="color:#A5A2AC;font-size:13px">&nbsp;&nbsp;EduNova Educação</span>
    </td></tr>
    <tr><td style="padding:30px 28px 28px;background:{_SUPERFICIE};
                   border:1px solid {_FIO};border-top:0;border-radius:0 0 10px 10px">
      <div style="width:24px;height:2px;background:{_DESTAQUE};margin-bottom:16px"></div>
      <h1 style="margin:0 0 18px;color:{_TINTA};font-size:22px;line-height:1.25;font-weight:600">
        {_esc(titulo)}
      </h1>
      {"".join(blocos)}
    </td></tr>
    <tr><td style="padding:18px 6px 0;color:{_TINTA_3};font-size:12px;line-height:1.5;text-align:center">
      {_esc(texto_rodape)}
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""