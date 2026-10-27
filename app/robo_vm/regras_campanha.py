"""
REGRAS DA APURACAO AUTOMATICA - Central de Campanhas
Roda na VM junto com o robo_apuracao.py.

Os valores usados aqui sao os CODIGOS gravados pela Central
(GRADUACAO, POS_GRADUACAO, NOVOS_CANAIS...), nao os rotulos
da tela. Toda tabela da base usa o apelido "b".
"""

import re
from datetime import date, timedelta


# ===================== CODIGO DA CAMPANHA =====================
PADRAO_CAM = re.compile(r"(?i)(?<![A-Z0-9])CAM[\s\-_.]*0*(\d{1,4})(?!\d)")


# Painel da Lumen ainda nao tem filtro de campanha: ligar quando tiver.
REGRA_CAM_ATIVA_LUMEN = False

# Pos/Prof: o funil vem das views do Databricks. Enquanto True, o robo
# tambem consulta o painel da EPS so para CONFERENCIA (vai na observacao,
# nao entra nos numeros). Desligar apos a semana de conferencia.
CONFERIR_PAINEL = True


def extrair_cam(nome):
    m = PADRAO_CAM.search(nome or "")
    return f"CAM-{int(m.group(1)):03d}" if m else None


# ===================== CALENDARIO =====================
# O robo agendado so apura em dia util (seg-sex, fora dos feriados abaixo).
# Rodada manual na VM ignora o calendario.
FERIADOS_FIXOS = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
FERIADOS_EXTRAS = set()  # ex.: {date(2026, 12, 24)} para emendas


def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados(ano):
    """Nacionais + Carnaval (seg e ter), Sexta-feira Santa e Corpus Christi."""
    p = _pascoa(ano)
    moveis = {p - timedelta(days=48), p - timedelta(days=47), p - timedelta(days=2), p + timedelta(days=60)}
    return {date(ano, m, d) for m, d in FERIADOS_FIXOS} | moveis | {x for x in FERIADOS_EXTRAS if x.year == ano}


def dia_util(d):
    return d.weekday() < 5 and d not in feriados(d.year)


# ===================== AJUSTES DE CADASTRO =====================
# Campanhas cadastradas antes de existir "Todas as frentes" / "Todos
# os supercanais". O robo apura como se o cadastro tivesse "todas".
# Retire a linha quando o cadastro na Central for corrigido.
AJUSTE_ESCOPO = {
    "CAM-013": {"todas_frentes": True, "todos_supercanais": True, "todas_modalidades": True},  # Pos R$100/matricula: toda a Pos, 3 EPS; so o periodo filtra
}


def aplicar_ajuste_escopo(codigo, escopos):
    ajuste = AJUSTE_ESCOPO.get(codigo)
    if not ajuste:
        return escopos
    novos = []
    for e in escopos:
        e = dict(e)
        if ajuste.get("todas_frentes"):
            e["frente_pos"] = None
        if ajuste.get("todas_modalidades"):
            e["modalidade"] = None
        if ajuste.get("todos_supercanais"):
            e["supercanal"] = None
            e["outro_supercanal_descricao"] = None
        novos.append(e)
    return novos


# ===================== EPS =====================
def normalizar_eps(valor):
    """Qualquer grafia de EPS (mailing, base) -> codigo da Central."""
    v = re.sub(r"[^A-Z]", "", str(valor or "").upper())
    if v.startswith("VX"):
        return "VOXA"
    if v.startswith("LUMEN"):
        return "LUMEN"
    if v.startswith("PRISMA"):
        return "PRISMA"
    return ""


# EPS como aparece nas views de interacao (Prisma nao tem interacao)
EPS_VIEW = {"VOXA": "VX", "LUMEN": "LUMEN"}

EPS_CRM = {"VOXA": "VOXA - CALLCENTER", "LUMEN": "LUMEN - CALLCENTER", "PRISMA": "PRISMA - CALLCENTER"}

# Prof: a partir de jul/2026 toda matricula marcada como Lumen e da VOXA.
VIRADA_PROF_LUMEN_VOXA = "2026-07-01"

# Graduacao/Tecnico: campanha que comeca a partir daqui le o ciclo 27.1.
# Sem UNION: as duas tabelas leem as mesmas interacoes (CPF contaria em dobro).
VIRADA_GRAD_271 = "2026-10-12"
TABELA_GRAD_271 = "lakehouse.comercial.base_callcenter_nova_20271"
PRODUTOS_271 = ("GRADUACAO", "TECNICO")

# Hash do CPF igual ao das views (SHA-256 do CPF formatado 000.000.000-00)
def hash_cpf_sql(col):
    c = f"LPAD(REGEXP_REPLACE(COALESCE(CAST({col} AS STRING), ''), '[^0-9]', ''), 11, '0')"
    return (f"LOWER(SHA2(CONCAT(SUBSTR({c},1,3),'.',SUBSTR({c},4,3),'.',"
            f"SUBSTR({c},7,3),'-',SUBSTR({c},10,2)), 256))")

NOVOS_CANAIS = "('DISTRIBUIDORES','CONSULTORIA EDUCACAO','EMPRESA','MARKETPLACE','VOCE INDICA','VOCÊ INDICA')"


def _supercanal(col, outros):
    return {
        "HUNTER": f"{col} = 'HUNTER'",
        "MIDIA": f"{col} = 'MIDIA'",
        "OUTROS": f"{col} = '{outros}'",
        "NOVOS_CANAIS": f"{col} IN {NOVOS_CANAIS}",
    }


# ===================== PRODUTOS =====================
# tipo "interacao": base com tabulacao + matricula atribuida (funil completo)
# tipo "matricula": base so de matriculas (sem funil operacional)
JANELA_MATRICULA_DIAS = 15  # esteira: matriculas ate 15 dias apos o fim

_GRAD = {
    "tipo": "interacao",
    "tabela": "lakehouse.comercial.base_callcenter_nova",
    "col_dt_base": "DT_BASE",
    "eps": {"VOXA": "VX", "LUMEN": "LUMEN"},
    "modalidade": {
        "PRESENCIAL": "b.MODALIDADE = 'PRESENCIAL'",
        "EAD": "b.MODALIDADE = 'EAD'",  # todo o EAD: inclui semi e EAD + Pratica
        "SEMIPRESENCIAL": "UPPER(COALESCE(b.DS_FORMATO_OFERTA,'')) LIKE '%SEMIPRESENCIAL%'",
    },
    "supercanal": _supercanal("b.SUPER_CANAL", "OUTROS"),
    "frente": {},
}

PRODUTOS = {
    "GRADUACAO": {**_GRAD, "filtro_produto": "b.TIPO_CURSO = 'GRADUAÇÃO'"},
    "TECNICO": {**_GRAD, "filtro_produto": "b.TIPO_CURSO = 'TÉCNICO'"},
    "POS_GRADUACAO": {
        "tipo": "matricula",
        "tabela": "lakehouse.comercial.tb_crm_fat_pos",
        "col_dt_base": "dt_base",
        "filtro_produto": "b.dt_base = (SELECT MAX(dt_base) FROM lakehouse.comercial.tb_crm_fat_pos)",
        "eps": EPS_CRM,
        "modalidade": {
            "PRESENCIAL": "b.ds_modalidade = 'PRESENCIAL'",
            "EAD": "b.ds_modalidade IN ('EAD','INTENSIVO','SUPERINTENSIVO','SEMI_PRESENCIAL')",
            "SEMIPRESENCIAL": "b.ds_modalidade = 'SEMI_PRESENCIAL'",
        },
        "supercanal": _supercanal("b.ds_canal_descida", "CALL CENTER"),
        "frente": {
            "7_MINUTOS": "b.ds_canal_descida = 'MIDIA'",
            "EGRESSOS": "b.fl_egresso_balde = 1",
            "RECEPTIVO": None,  # toda matricula da EPS no periodo
        },
        # Funil (tentativas -> vendas): view de interacoes da Pos.
        # Matricula NAO vem daqui: segue na tabela oficial acima.
        "funil": {
            "tabela": "lakehouse.comercial.base_callcenter_pos",
            "filtro_fixo": "b.ORIGEM_REGISTRO = 'INTERACAO'",
            "filtro_produto": "1=1",
            "eps": EPS_VIEW,
            "modalidade": {
                "PRESENCIAL": "b.MODALIDADE = 'PRESENCIAL'",
                "EAD": "b.MODALIDADE IN ('EAD','INTENSIVO','SUPERINTENSIVO','SEMI_PRESENCIAL')",
                "SEMIPRESENCIAL": "b.MODALIDADE = 'SEMI_PRESENCIAL'",
            },
            "supercanal": _supercanal("b.CANAL", "CALL CENTER"),
            "frente": {
                "7_MINUTOS": "b.CANAL = 'MIDIA'",
                "EGRESSOS": "b.FL_EGRESSO = 1",
                "RECEPTIVO": None,
            },
        },
    },
    "PROFISSIONALIZANTES": {
        "tipo": "matricula",
        "tabela": "lakehouse.comercial.tb_fat_prof",
        "col_dt_base": "dt_base",
        "filtro_produto": "b.dt_base = (SELECT MAX(dt_base) FROM lakehouse.comercial.tb_fat_prof) AND COALESCE(b.fl_teste,0) = 0",
        "eps": EPS_CRM,
        "modalidade": {
            "PRESENCIAL": "b.ds_modalidade = 'PRESENCIAL'",
            "EAD": "b.ds_modalidade IN ('EAD','SEMI_PRESENCIAL')",
            "SEMIPRESENCIAL": "b.ds_modalidade = 'SEMI_PRESENCIAL'",
        },
        "supercanal": _supercanal("b.ds_supercanal_vendas", "CALL CENTER"),
        "frente": {},
        # Venda/matricula da Lumen a partir de jul/2026 e da VOXA.
        # {dt} = data do evento (dt_pma_conf na matricula, dt_inscricao na venda).
        "eps_matricula": {
            "VOXA": f"(b.consultor_nome = 'VOXA - CALLCENTER' OR (b.consultor_nome = 'LUMEN - CALLCENTER' "
                   f"AND CAST({{dt}} AS DATE) >= DATE '{VIRADA_PROF_LUMEN_VOXA}'))",
            "LUMEN": f"(b.consultor_nome = 'LUMEN - CALLCENTER' "
                           f"AND CAST({{dt}} AS DATE) < DATE '{VIRADA_PROF_LUMEN_VOXA}')",
        },
        "funil": {
            "tabela": "lakehouse.comercial.base_callcenter_prof",
            "filtro_fixo": "b.ORIGEM_REGISTRO = 'INTERACAO'",
            "filtro_produto": "1=1",
            "eps": EPS_VIEW,
            "modalidade": {
                "PRESENCIAL": "b.MODALIDADE = 'PRESENCIAL'",
                "EAD": "b.MODALIDADE IN ('EAD','SEMI_PRESENCIAL')",
                "SEMIPRESENCIAL": "b.MODALIDADE = 'SEMI_PRESENCIAL'",
            },
            "supercanal": _supercanal("b.SUPER_CANAL", "CALL CENTER"),
            "frente": {},
        },
    },
}


def regra(produto):
    if produto not in PRODUTOS:
        raise ValueError(f"Produto '{produto}' sem regra cadastrada.")
    return PRODUTOS[produto]


def regra_campanha(produto, p):
    """Regra do produto com a tabela do ciclo da campanha p (Graduacao/Tecnico); demais produtos sem mudanca."""
    r = regra(produto)
    if produto in PRODUTOS_271 and str(p.get("dt_inicio_prevista") or "")[:10] >= VIRADA_GRAD_271:
        return {**r, "tabela": TABELA_GRAD_271}
    return r


def eps_base(produto, eps_central):
    r = regra(produto)
    if eps_central not in r["eps"]:
        raise ValueError(f"A EPS {eps_central} não tem dados na base de {produto}.")
    return r["eps"][eps_central]


def cond_eps_matricula(produto, eps_central, col_data="b.dt_pma_conf"):
    """WHERE da EPS na tabela oficial (Pos/Prof). col_data: data do evento apurado."""
    r = regra(produto)
    especial = (r.get("eps_matricula") or {}).get(eps_central)
    if especial:
        return especial.format(dt=col_data)
    return f"b.consultor_nome = '{eps_base(produto, eps_central)}'"


def supercanal_e_todos(escopos):
    """'Todos os supercanais' vira Midia+Hunter+Novos Canais; cadastro antigo usou 'Outros: todos'."""
    canais = {e.get("supercanal") for e in escopos}
    if {"MIDIA", "HUNTER", "NOVOS_CANAIS"} <= canais:
        return True
    return any(
        e.get("supercanal") == "OUTROS" and "TODOS" in str(e.get("outro_supercanal_descricao") or "").upper()
        for e in escopos
    )


def filtro_escopos(produto, escopos, r=None):
    """
    WHERE de perfil para os escopos de UM produto: OR entre os
    escopos, AND dentro de cada escopo. Erro se faltar de-para.
    r: regra alternativa (ex.: a do funil de Pos/Prof); padrao = do produto.
    """
    r = r or regra(produto)
    ignorar_canal = supercanal_e_todos(escopos)
    blocos = set()

    for e in escopos:
        partes = []

        mod = e.get("modalidade")
        if mod:
            if mod not in r["modalidade"]:
                raise ValueError(f"Modalidade '{mod}' sem de-para para {produto}.")
            partes.append(r["modalidade"][mod])

        # Egressos sao ex-alunos: a matricula deles sempre desce como
        # canal CALL CENTER, entao o supercanal do cadastro nao se aplica.
        canal = None if e.get("frente_pos") == "EGRESSOS" else e.get("supercanal")
        if canal and not ignorar_canal:
            if canal not in r["supercanal"]:
                raise ValueError(f"Supercanal '{canal}' sem de-para para {produto}.")
            partes.append(r["supercanal"][canal])

        frente = e.get("frente_pos")
        if frente and r["frente"]:
            if frente not in r["frente"]:
                raise ValueError(f"Frente '{frente}' sem de-para para {produto}.")
            if r["frente"][frente]:
                partes.append(r["frente"][frente])

        blocos.add(" AND ".join(f"({p})" for p in partes) if partes else "1=1")

    perfil = "1=1" if "1=1" in blocos else " OR ".join(f"({b})" for b in sorted(blocos))
    return f"({r['filtro_produto']}) AND ({perfil})"


# ===================== FUNIL PADRAO (mesmas regras do painel Power BI) =====================
# Unidade de contagem: CHAVE_INSCRICAO (inscricao), nao CPF.
# Status comparados sem acento e em maiusculas (TABULACAO_HUMANA_2).
#   Mailing     = inscricoes presentes na base de interacoes do recorte
#   Trabalhados = inscricoes com algum status da lista TRABALHADO
#   Tentativas  = soma de FLAG_TENTATIVA (uma por interacao)
#   Atendidos   = inscricoes com algum status da lista ATENDIDO
#   Efetivos    = JA: TABULACAO_HUMANA_4 = 'EFETIVO' (limitado a Atendidos)
#                 LUMEN: TAB_4 = 'EFETIVO' ou TAB_5 = 'P' (limitado a Atendidos e Mailing)
#   Vendas      = inscricoes com 'ACEITOU OFERTA'
#   Matriculas  = MAT_LIQ_ATRIBUIDA_CALLCENTER

STATUS_TRABALHADO = [
    "ACEITOU OFERTA", "EM NEGOCIACAO", "FINANCEIRO", "ACADEMICO", "CUMPRIMENTO", "PESSOAL",
    "PAROU DE INTERAGIR", "JA RECEBEU ATENDIMENTO", "RECUSOU OFERTA",
    "CONTATO COM TERCEIRO", "CONTATO NAO REALIZADO", "NAO RESPONDE", "NAO ATENDE", "CHAMADA OCUPADA",
    "CAIU A LINHA", "QUEDA DE LIGACAO", "LINHA MUDA", "CAIXA POSTAL",
    "TELEFONE ERRADO", "NUMERO ERRADO", "ERRO OPERADORA", "FORA DE AREA", "ENGANO", "FALECIDO",
    "SISTEMA", "URA - ABANDONO FILA", "ABANDONO FILA",
]

STATUS_ATENDIDO = [
    "ABANDONO FILA", "ACADEMICO", "ACEITOU OFERTA", "CAIU A LINHA", "CONTATO COM TERCEIRO",
    "EM NEGOCIACAO", "ENGANO", "FALECIDO", "FINANCEIRO", "JA RECEBEU ATENDIMENTO", "NUMERO ERRADO",
    "PAROU DE INTERAGIR", "PESSOAL", "QUEDA DE LIGACAO", "RECUSOU OFERTA", "SISTEMA",
    "TELEFONE ERRADO", "URA - ABANDONO FILA",
]

STATUS_VENDA = ["ACEITOU OFERTA"]

# Efetivo por EPS (codigo da Central) -> condicao SQL sobre a base "b"
EFETIVO_POR_EPS = {
    "VOXA": "UPPER(TRIM(b.TABULACAO_HUMANA_4)) = 'EFETIVO'",
    "LUMEN": "(UPPER(TRIM(b.TABULACAO_HUMANA_4)) = 'EFETIVO' OR UPPER(TRIM(b.TABULACAO_HUMANA_5)) = 'P')",
}
# Limites do efetivo (como no DAX): JA <= atendidos; LUMEN <= atendidos e <= mailing
EFETIVO_LIMITES = {"VOXA": ("atendidos",), "LUMEN": ("atendidos", "mailing")}

SEM_ACENTO = "translate(UPPER(TRIM(b.TABULACAO_HUMANA_2)), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC')"


def lista_sql(itens):
    return "(" + ", ".join("'" + i.replace("'", "''") + "'" for i in itens) + ")"