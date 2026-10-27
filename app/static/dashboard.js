/* ==========================================================
   DASHBOARD DE CAMPANHAS
   ==========================================================
   Visão consolidada de ativas e encerradas, com filtro por
   produto, tipo, classificação, segmentação, período, EPS e
   busca livre por nome ou código.

   Os filtros rodam sobre os dados já carregados. Cada clique
   responde na hora, sem ida ao servidor — o que importa numa
   tela feita para explorar.

   FILTRO DE EPS
   Sem EPS selecionada, cada ação mostra o consolidado (soma
   de todas as EPS). Com uma EPS selecionada, só aparecem as
   ações dela, e funil, meta e atingimento passam a ser só os
   dela.

   VERSÃO
   A constante DASHBOARD_VERSAO aparece no Console (F12) ao
   carregar. Serve para confirmar que o deploy chegou ao
   navegador sem precisar adivinhar pela tela.

   NUMEROS = APURACAO DO ROBO
   Vendas, matrículas, funil e atingimento vêm da mesma
   apuração que a aba Dashboard mostra (/api/internal/apuracao/
   dashboard). O resultado lançado à mão não entra mais nos
   números. Campanha ainda sem apuração do robô aparece na
   lista e nos aprendizados, mas fica fora dos gráficos.
   O funil completo fica só na aba Dashboard.

   Este arquivo é carregado depois do interno.js e usa as
   funções dele (api, esc, perfilPode).
   ========================================================== */

const DASHBOARD_VERSAO = "2026-10-05.3";

console.info("dashboard.js versão " + DASHBOARD_VERSAO);

let dashboardDados = [];

let dashboardFiltros = {
  busca: "",
  produto: "",
  tipo: "",
  subtipo: "",
  situacao: "",
  classificacao: "",
  supercanal: "",
  modalidade: "",
  eps: "",
  mes: ""
};


/* ---------- EPS sempre em maiúsculas ----------
   O filtro de EPS trabalha em maiúsculas. Se o servidor
   devolver "Voxa" num lugar e "VOXA" em outro, a copy, o
   diário e o funil da EPS somem ao filtrar. Normalizar na
   carga resolve de uma vez.                              */

function dashEpsChave(valor) {
  return String(valor || "").trim().toUpperCase();
}

function dashNormalizarCampanha(c) {

  if (c.por_eps && typeof c.por_eps === "object") {
    const normalizado = {};

    Object.entries(c.por_eps).forEach(([eps, item]) => {
      normalizado[dashEpsChave(eps)] = item;
    });

    c.por_eps = normalizado;
  }

  (c.copys || []).forEach(item => {
    item.eps = dashEpsChave(item.eps);
  });

  (c.diario || []).forEach(item => {
    item.eps = dashEpsChave(item.eps);
  });

  return c;
}


/* ---------- leitura dos dados ---------- */

function dashCampanhaEncerrada(c) {
  return (
    c.status_campanha === "ENCERRADA_EDUNOVA"
    || !!c.encerramento
  );
}

function dashMesReferencia(c) {
  const data =
    c.dt_inicio_prevista
    || c.dt_criacao;

  return data
    ? String(data).slice(0, 7)
    : "";
}

function dashSupercanais(c) {
  return [
    ...new Set(
      (c.escopos || [])
        .map(e => e.supercanal)
        .filter(Boolean)
    )
  ];
}

function dashModalidades(c) {
  return [
    ...new Set(
      (c.escopos || [])
        .map(e => e.modalidade)
        .filter(Boolean)
    )
  ];
}

function dashEpsDaCampanha(c) {
  return [
    ...new Set(
      (c.eps || [])
        .map(e => dashEpsChave(e.eps))
        .filter(Boolean)
    )
  ];
}

const DASH_FUNIL_VAZIO = {
  mailing: 0,
  trabalhado: 0,
  tentativas: 0,
  alo: 0,
  efetivos: 0,
  vendas: 0,
  matriculas: 0
};

/* Realizado da ação no recorte atual: da EPS filtrada, ou o
   consolidado quando não há filtro de EPS. */
function dashRealizado(c) {
  const eps = dashboardFiltros.eps;

  if (eps) {
    return c.por_eps?.[eps]?.realizado || DASH_FUNIL_VAZIO;
  }

  return c.realizado || DASH_FUNIL_VAZIO;
}

/* Meta da ação no recorte atual.
   Devolve {base, meta, realizado} ou null se não há meta. */
function dashMeta(c) {
  const base = c.metas?.base;

  if (!base || c.sem_apuracao) return null;

  const eps = dashboardFiltros.eps;

  if (eps) {
    const item = c.por_eps?.[eps];

    if (!item || !item.meta) return null;

    return {
      base,
      meta: Number(item.meta),
      realizado: Number(item.valor_realizado || 0)
    };
  }

  const total = c.metas?.total;

  if (!total || !total.meta) return null;

  return {
    base,
    meta: Number(total.meta),
    realizado: Number(total.realizado || 0)
  };
}


/* ---------- indicadores ----------
   Calculados a partir dos volumes, nunca guardados. Assim
   nunca há um percentual discordando do número que o gerou. */

function dashIndicadores(r) {

  const pct = (parte, base) =>
    base ? (parte / base * 100) : null;

  return {
    trabalhado:  pct(r.trabalhado, r.mailing),
    spin:        r.mailing ? (r.tentativas / r.mailing) : null,
    alo:         pct(r.alo, r.mailing),
    efetivo:     pct(r.efetivos, r.mailing),
    conversao:   pct(r.vendas, r.efetivos),
    matricula:   pct(r.matriculas, r.vendas),
    retorno:     pct(r.matriculas || r.vendas, r.mailing)
  };
}

function dashPct(valor) {
  return valor === null || !Number.isFinite(valor)
    ? "—"
    : valor.toFixed(1).replace(".", ",") + "%";
}

function dashRazao(valor) {
  return valor === null || !Number.isFinite(valor)
    ? "—"
    : valor.toFixed(2).replace(".", ",");
}

function dashNumero(valor) {
  return (valor || 0).toLocaleString("pt-BR");
}


/* ---------- filtro ---------- */

function dashboardFiltrar() {

  const f = dashboardFiltros;

  const termo = f.busca.trim().toLowerCase();

  return dashboardDados.filter(c => {

    if (termo) {
      const alvo = (
        (c.codigo_campanha || "")
        + " "
        + (c.nome_campanha || "")
      ).toLowerCase();

      if (!alvo.includes(termo)) return false;
    }

    if (f.produto && c.produto !== f.produto) {
      return false;
    }

    if (f.subtipo && (c.tipo_acao === "INCENTIVO" || c.subtipo_acao !== f.subtipo)) {
      return false;
    }

    if (f.tipo && c.tipo_acao !== f.tipo) {
      return false;
    }

    if (f.situacao) {
      const encerrada = dashCampanhaEncerrada(c);

      if (f.situacao === "ENCERRADA" && !encerrada) return false;
      if (f.situacao === "ATIVA" && encerrada) return false;
    }

    if (f.classificacao) {
      const classe =
        c.encerramento?.classificacao_resultado || "";

      if (classe !== f.classificacao) return false;
    }

    if (
      f.supercanal
      && !dashSupercanais(c).includes(f.supercanal)
    ) {
      return false;
    }

    if (
      f.modalidade
      && !dashModalidades(c).includes(f.modalidade)
    ) {
      return false;
    }

    if (
      f.eps
      && !dashEpsDaCampanha(c).includes(f.eps)
    ) {
      return false;
    }

    if (f.mes && dashMesReferencia(c) !== f.mes) {
      return false;
    }

    return true;
  });
}


/* ---------- opções dos filtros ----------
   Montadas a partir dos dados: só aparece o que existe. */

function dashOpcoes(extrair) {
  return [
    ...new Set(
      dashboardDados
        .flatMap(extrair)
        .filter(Boolean)
    )
  ].sort();
}

function dashSelect(id, rotulo, opcoes, valorAtual, formatar) {
  return `
    <div>
      <label>${esc(rotulo)}</label>
      <select id="${id}">
        <option value="">Todos</option>
        ${
          opcoes
            .map(
              opcao => `
                <option
                  value="${esc(opcao)}"
                  ${opcao === valorAtual ? "selected" : ""}
                >${esc(
                  formatar ? formatar(opcao) : opcao
                )}</option>
              `
            )
            .join("")
        }
      </select>
    </div>
  `;
}


/* ---------- consolidado ---------- */

function dashConsolidado(lista) {

  const soma = {...DASH_FUNIL_VAZIO};

  lista.forEach(c => {
    const r = dashRealizado(c);

    Object.keys(soma).forEach(
      chave => {
        soma[chave] += (r?.[chave] || 0);
      }
    );
  });

  const classes = {
    SUCESSO: 0,
    OPORTUNIDADE_MELHORIA: 0,
    SEM_SUCESSO: 0,
    SEM_CLASSIFICACAO: 0
  };

  lista.forEach(c => {
    const classe =
      c.encerramento?.classificacao_resultado
      || "SEM_CLASSIFICACAO";

    if (classe in classes) classes[classe] += 1;
  });

  /* Meta: soma por base. Matrícula e venda não se somam
     entre si, então cada base tem o seu atingimento.     */
  const metas = {};

  lista.forEach(c => {
    const m = dashMeta(c);

    if (!m) return;

    metas[m.base] = metas[m.base] || {meta: 0, realizado: 0, acoes: 0};
    metas[m.base].meta += m.meta;
    metas[m.base].realizado += m.realizado;
    metas[m.base].acoes += 1;
  });

  return {
    soma,
    classes,
    metas,
    total: lista.length,
    semApuracao: lista.filter(c => c.sem_apuracao).length,

    encerradas:
      lista.filter(dashCampanhaEncerrada).length
  };
}


/* ---------- rótulos ---------- */

const DASH_CLASSES = {
  SUCESSO: "Sucesso",
  OPORTUNIDADE_MELHORIA: "Oportunidade de melhoria",
  SEM_SUCESSO: "Sem sucesso",
  SEM_CLASSIFICACAO: "Sem classificação"
};

const DASH_BASES = {
  MATRICULAS: "matrículas",
  VENDAS: "vendas"
};

function dashMesLabel(mes) {
  if (!mes) return "";

  const [ano, numero] = mes.split("-");

  const nomes = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
  ];

  return `${nomes[Number(numero) - 1]}/${ano}`;
}


/* ==========================================================
   EXECUCAO E PRAZOS
   Regras (ajustaveis aqui):
   - Comercial valida em ate DASH_SLA_COMERCIAL_DU dias uteis
     depois do envio pelo Planejamento.
   - Comercial libera a EPS ate o inicio previsto.
   - EPS (acao comercial) faz go-live ate o inicio previsto, ou
     ate a liberacao, se a liberacao veio depois. Incentivo nao
     tem go-live: a EPS so precisa estar liberada.
   - Planejamento: sinaliza envio ao Comercial depois do
     inicio previsto.
   ========================================================== */

const DASH_SLA_COMERCIAL_DU = 2;

const DASH_STATUS_FORA = ["ARQUIVADA", "CANCELADA", "RASCUNHO_PLANEJAMENTO"];

function dashData(valor) {
  if (!valor) return null;
  const texto = String(valor).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(texto)) return null;
  const [a, m, d] = texto.split("-").map(Number);
  return new Date(a, m - 1, d);
}

function dashHoje() {
  const h = new Date();
  return new Date(h.getFullYear(), h.getMonth(), h.getDate());
}

function dashDiasCorridos(de, ate) {
  return Math.round((ate - de) / 86400000);
}

function dashPascoa(ano) {
  const a = ano % 19, b = Math.floor(ano / 100), c = ano % 100;
  const d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4), k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const mes = Math.floor((h + l - 7 * m + 114) / 31);
  const dia = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(ano, mes - 1, dia);
}

const dashFeriadosCache = {};

function dashFeriados(ano) {
  if (dashFeriadosCache[ano]) return dashFeriadosCache[ano];
  const p = dashPascoa(ano);
  const somar = n => new Date(p.getFullYear(), p.getMonth(), p.getDate() + n);
  const datas = [
    [1, 1], [4, 21], [5, 1], [9, 7], [10, 12], [11, 2], [11, 15], [11, 20], [12, 25]
  ].map(([m, d]) => new Date(ano, m - 1, d));
  datas.push(somar(-48), somar(-47), somar(-2), somar(60));
  return dashFeriadosCache[ano] = new Set(datas.map(d => d.toDateString()));
}

function dashDiaUtil(d) {
  const s = d.getDay();
  return s !== 0 && s !== 6 && !dashFeriados(d.getFullYear()).has(d.toDateString());
}

/* Dias uteis depois de "de" ate "ate" (inclusive). */
function dashDiasUteis(de, ate) {
  let n = 0;
  const d = new Date(de);
  while (d < ate) {
    d.setDate(d.getDate() + 1);
    if (dashDiaUtil(d)) n += 1;
  }
  return n;
}

function dashDataBr(d) {
  return d ? d.toLocaleDateString("pt-BR", {day: "2-digit", month: "2-digit"}) : "—";
}

function dashPlural(n, um, varios) {
  return `${n} ${n === 1 ? um : varios}`;
}

/* Situacao de execucao de uma campanha. Cada item tem
   tom: ok | atencao | critico | neutro. */
function dashExecucao(c) {
  const hoje = dashHoje();
  const inicio = dashData(c.dt_inicio_prevista);
  const envio = dashData(c.marcos?.envio_comercial);
  const validacao = dashData(c.marcos?.validacao_comercial);
  const encerrada = dashCampanhaEncerrada(c);
  const incentivo = String(c.tipo_acao || "").toUpperCase() === "INCENTIVO";
  const fora = DASH_STATUS_FORA.includes(String(c.status_campanha || "").toUpperCase());

  const exec = {planejamento: null, comercial: null, liberacao: [], eps: []};

  if (fora) return exec;

  /* Planejamento */
  if (envio && inicio) {
    const d = dashDiasCorridos(inicio, envio);
    exec.planejamento = d > 0
      ? {tom: "critico", texto: `Enviada ao Comercial ${dashPlural(d, "dia", "dias")} depois do início previsto`, dias: d}
      : {tom: "ok", texto: `Enviada ao Comercial ${dashPlural(-d, "dia", "dias")} antes do início`, dias: d};
  }

  /* Comercial: validacao */
  if (envio) {
    const fim = validacao || hoje;
    const du = dashDiasUteis(envio, fim);
    if (validacao) {
      exec.comercial = du > DASH_SLA_COMERCIAL_DU
        ? {tom: "critico", texto: `Validou em ${dashPlural(du, "dia útil", "dias úteis")} (prazo ${DASH_SLA_COMERCIAL_DU})`, du}
        : {tom: "ok", texto: du === 0 ? "Validou no mesmo dia" : `Validou em ${dashPlural(du, "dia útil", "dias úteis")}`, du};
    } else if (!encerrada) {
      exec.comercial = du > DASH_SLA_COMERCIAL_DU
        ? {tom: "critico", texto: `Validação pendente há ${dashPlural(du, "dia útil", "dias úteis")}`, du, pendente: true}
        : {tom: "atencao", texto: `Em validação há ${dashPlural(du, "dia útil", "dias úteis")}`, du, pendente: true};
    }
  }

  /* EPS: liberacao (Comercial) e inicio (EPS) */
  (c.eps || []).forEach(e => {
    const eps = dashEpsChave(e.eps);
    const liberacao = dashData(e.dt_liberacao_eps);
    const liberada = !!e.liberada_para_eps;

    if (inicio && liberada && liberacao) {
      const d = dashDiasCorridos(inicio, liberacao);
      exec.liberacao.push(d > 0
        ? {eps, tom: "critico", texto: `Liberada ${dashPlural(d, "dia", "dias")} depois do início`, dias: d}
        : {eps, tom: "ok", texto: "Liberada no prazo", dias: d});
    } else if (inicio && !liberada && validacao && hoje > inicio && !encerrada) {
      exec.liberacao.push({eps, tom: "critico", texto: "Ainda não liberada e o início já passou", dias: dashDiasCorridos(inicio, hoje)});
    }

    let item;

    if (incentivo) {
      item = liberada
        ? {tom: "neutro", rotulo: "Incentivo", texto: "Incentivo: sem go-live, vale a partir do início"}
        : {tom: "neutro", rotulo: "Não liberada", texto: "Aguardando liberação do Comercial"};
    } else if (!liberada) {
      item = {tom: "neutro", rotulo: "Não liberada", texto: "Aguardando liberação do Comercial"};
    } else {
      const ref = [inicio, liberacao].filter(Boolean).sort((a, b) => b - a)[0] || null;
      const goLive = dashData(e.dt_go_live) || dashData(e.dt_inicio_operacional);

      if (goLive && ref) {
        const d = dashDiasCorridos(ref, goLive);
        item = d > 0
          ? {tom: "critico", rotulo: `+${d}d`, texto: `Iniciou com ${dashPlural(d, "dia", "dias")} de atraso (${dashDataBr(goLive)})`, dias: d}
          : {tom: "ok", rotulo: "No prazo", texto: `Iniciou no prazo (${dashDataBr(goLive)})`, dias: 0};
      } else if (goLive) {
        item = {tom: "ok", rotulo: "Iniciou", texto: `Iniciou em ${dashDataBr(goLive)}`};
      } else if (ref && hoje > ref) {
        const d = dashDiasCorridos(ref, hoje);
        item = encerrada
          ? {tom: "critico", rotulo: "Não executou", texto: "Campanha encerrada sem go-live da EPS", naoIniciou: true}
          : {tom: "critico", rotulo: "Não iniciou", texto: `Não iniciou: ${dashPlural(d, "dia", "dias")} desde o início previsto`, dias: d, naoIniciou: true};
      } else {
        item = {tom: "neutro", rotulo: "A iniciar", texto: "Ainda dentro do prazo de início"};
      }
    }

    const fechamento = dashData(e.dt_fechamento_eps);
    exec.eps.push({eps, ...item, fechamento});
  });

  return exec;
}

function dashExecucaoFiltrada(c) {
  const exec = dashExecucao(c);
  const eps = dashboardFiltros.eps;
  if (!eps) return exec;
  return {
    ...exec,
    liberacao: exec.liberacao.filter(x => x.eps === eps),
    eps: exec.eps.filter(x => x.eps === eps)
  };
}

/* Resumo de execucao do recorte. */
function dashResumoExecucao(lista) {
  const r = {
    comercial: {total: 0, noPrazo: 0, pendentes: 0, somaDu: 0},
    planejamento: {total: 0, atrasadas: 0},
    liberacao: {total: 0, atrasadas: 0},
    porEps: {},
    epsTotal: 0, epsNoPrazo: 0
  };

  lista.forEach(c => {
    const exec = dashExecucaoFiltrada(c);

    if (exec.planejamento) {
      r.planejamento.total += 1;
      if (exec.planejamento.tom === "critico") r.planejamento.atrasadas += 1;
    }

    if (exec.comercial) {
      r.comercial.total += 1;
      r.comercial.somaDu += exec.comercial.du;
      if (exec.comercial.pendente) r.comercial.pendentes += 1;
      if (exec.comercial.tom === "ok") r.comercial.noPrazo += 1;
    }

    exec.liberacao.forEach(l => {
      r.liberacao.total += 1;
      if (l.tom === "critico") r.liberacao.atrasadas += 1;
    });

    exec.eps.forEach(e => {
      if (e.tom === "neutro") return;
      const alvo = r.porEps[e.eps] = r.porEps[e.eps] || {noPrazo: 0, atraso: 0, naoIniciou: 0, somaAtraso: 0};
      if (e.naoIniciou) alvo.naoIniciou += 1;
      else if (e.tom === "critico") { alvo.atraso += 1; alvo.somaAtraso += e.dias || 0; }
      else alvo.noPrazo += 1;
      r.epsTotal += 1;
      if (e.tom === "ok") r.epsNoPrazo += 1;
    });
  });

  return r;
}


/* ==========================================================
   DESTAQUES: O QUE FOI BEM E O QUE PRECISA DE ATENCAO
   ========================================================== */

function dashDestaques(lista) {
  const bem = [];
  const atencao = [];

  lista.forEach(c => {
    const m = dashMeta(c);
    const nome = `${c.codigo_campanha}`;

    if (m && m.meta) {
      const pct = m.realizado / m.meta * 100;
      if (pct >= 100) {
        bem.push({peso: pct, tipo: "Resultado", texto: `${nome} bateu a meta: ${dashPct(pct)} (${dashNumero(m.realizado)} de ${dashNumero(m.meta)} ${DASH_BASES[m.base] || ""}).`, code: c.codigo_campanha});
      } else if (pct < 70 && (dashCampanhaEncerrada(c) || (dashData(c.dt_fim_prevista) && dashData(c.dt_fim_prevista) < dashHoje()))) {
        atencao.push({peso: 100 - pct, tipo: "Resultado", texto: `${nome} está em ${dashPct(pct)} da meta (${dashNumero(m.realizado)} de ${dashNumero(m.meta)}).`, code: c.codigo_campanha});
      }
    }

    const exec = dashExecucaoFiltrada(c);

    if (exec.comercial?.tom === "critico") {
      atencao.push({peso: 50 + exec.comercial.du, tipo: "Comercial", texto: `${nome}: ${exec.comercial.texto.toLowerCase()}.`, code: c.codigo_campanha});
    }

    if (exec.planejamento?.tom === "critico") {
      atencao.push({peso: 40 + exec.planejamento.dias, tipo: "Planejamento", texto: `${nome}: ${exec.planejamento.texto.toLowerCase()}.`, code: c.codigo_campanha});
    }

    exec.liberacao.filter(l => l.tom === "critico").forEach(l => {
      atencao.push({peso: 45 + (l.dias || 0), tipo: "Comercial", texto: `${nome} · ${humanizarV9(l.eps)}: ${l.texto.toLowerCase()}.`, code: c.codigo_campanha});
    });

    exec.eps.forEach(e => {
      if (e.naoIniciou) {
        atencao.push({peso: 90 + (e.dias || 0), tipo: "EPS", texto: `${nome} · ${humanizarV9(e.eps)}: ${e.texto.toLowerCase()}.`, code: c.codigo_campanha});
      } else if (e.tom === "critico") {
        atencao.push({peso: 60 + (e.dias || 0), tipo: "EPS", texto: `${nome} · ${humanizarV9(e.eps)}: ${e.texto.toLowerCase()}.`, code: c.codigo_campanha});
      }
    });

    exec.eps.filter(e => e.tom === "ok" && e.dias === 0).forEach(e => {
      bem.push({peso: 20, tipo: "EPS", texto: `${nome} · ${humanizarV9(e.eps)}: ${e.texto.toLowerCase()}.`, code: c.codigo_campanha});
    });

    if (exec.comercial?.tom === "ok") {
      bem.push({peso: 15, tipo: "Comercial", texto: `${nome}: ${exec.comercial.texto.toLowerCase()}.`, code: c.codigo_campanha});
    }

    if (exec.planejamento?.tom === "ok" && exec.planejamento.dias <= -5) {
      bem.push({peso: 12, tipo: "Planejamento", texto: `${nome}: ${exec.planejamento.texto.toLowerCase()}.`, code: c.codigo_campanha});
    }

    if (m && m.meta) {
      const pct = m.realizado / m.meta * 100;
      if (pct >= 70 && pct < 100 && !dashCampanhaEncerrada(c)) {
        bem.push({peso: pct / 2, tipo: "Resultado", texto: `${nome} já está em ${dashPct(pct)} da meta.`, code: c.codigo_campanha});
      }
    }

    if (c.encerramento?.classificacao_resultado === "SUCESSO") {
      bem.push({peso: 30, tipo: "Planejamento", texto: `${nome} encerrada como sucesso pelo Planejamento.`, code: c.codigo_campanha});
    } else if (c.encerramento?.classificacao_resultado === "SEM_SUCESSO") {
      atencao.push({peso: 30, tipo: "Planejamento", texto: `${nome} encerrada sem sucesso pelo Planejamento.`, code: c.codigo_campanha});
    }
  });

  const ordenar = arr => arr.sort((a, b) => b.peso - a.peso).slice(0, 8);
  const bloco = (titulo, tom, itens, vazio) => `
    <article class="hist-destaque ${tom}">
      <header><span class="hist-ponto"></span><h3>${titulo}</h3><small>${itens.length}</small></header>
      ${
        itens.length
          ? `<ul>${itens.map(i => `
              <li class="abrir-campanha" data-code="${esc(i.code)}">
                <span class="hist-tag">${esc(i.tipo)}</span>
                <span>${esc(i.texto)}</span>
              </li>`).join("")}</ul>`
          : `<p class="hist-vazio">${vazio}</p>`
      }
    </article>
  `;

  return `
    <section class="hist-secao">
      <div class="hist-secao-cab">
        <h2>Destaques do período</h2>
        <p>O que foi bem e o que precisa de atenção, em resultado e em execução (Planejamento, Comercial e EPS). Clique para abrir a campanha.</p>
      </div>
      <div class="hist-destaques">
        ${bloco("O que foi bem", "bom", ordenar(bem), "Nenhum destaque positivo no recorte.")}
        ${bloco("O que precisa de atenção", "ruim", ordenar(atencao), "Nada fora do esperado no recorte.")}
      </div>
    </section>
  `;
}


/* ==========================================================
   PAINEL DE EXECUCAO E PRAZOS
   ========================================================== */

function dashPill(tom, texto, titulo) {
  return `<span class="hist-pill ${tom}" ${titulo ? `title="${esc(titulo)}"` : ""}>${esc(texto)}</span>`;
}

function dashPainelExecucao(lista) {
  const r = dashResumoExecucao(lista);
  const comPrazo = lista.filter(c => {
    const e = dashExecucaoFiltrada(c);
    return e.comercial || e.planejamento || e.eps.length;
  });

  if (!comPrazo.length) return "";

  const epsNomes = Object.keys(r.porEps).sort();
  const mediaDu = r.comercial.total ? (r.comercial.somaDu / r.comercial.total) : null;

  const cartaoResp = (titulo, valor, apoio, tom) => `
    <article class="hist-resp ${tom}">
      <span>${esc(titulo)}</span>
      <strong>${valor}</strong>
      <small>${apoio}</small>
    </article>
  `;

  return `
    <section class="hist-secao">
      <div class="hist-secao-cab">
        <h2>Execução e prazos</h2>
        <p>
          Quem cumpriu o combinado. Comercial valida em até ${DASH_SLA_COMERCIAL_DU} dias úteis e libera a EPS até o início;
          a EPS faz go-live até o início (ou até a liberação, se ela veio depois). Incentivo não tem go-live.
        </p>
      </div>

      <div class="hist-resps">
        ${cartaoResp(
          "Planejamento",
          r.planejamento.total ? dashPct((r.planejamento.total - r.planejamento.atrasadas) / r.planejamento.total * 100) : "—",
          r.planejamento.total
            ? `enviadas ao Comercial antes do início · ${dashPlural(r.planejamento.atrasadas, "atrasada", "atrasadas")}`
            : "sem envio registrado no recorte",
          r.planejamento.atrasadas ? "critico" : "ok"
        )}
        ${cartaoResp(
          "Comercial · validação",
          r.comercial.total ? dashPct(r.comercial.noPrazo / r.comercial.total * 100) : "—",
          r.comercial.total
            ? `no prazo · média de ${String((mediaDu || 0).toFixed(1)).replace(".", ",")} dias úteis${r.comercial.pendentes ? ` · ${dashPlural(r.comercial.pendentes, "pendente", "pendentes")}` : ""}`
            : "sem envio registrado no recorte",
          r.comercial.total && r.comercial.noPrazo < r.comercial.total ? "critico" : "ok"
        )}
        ${cartaoResp(
          "Comercial · liberação",
          r.liberacao.total ? dashPct((r.liberacao.total - r.liberacao.atrasadas) / r.liberacao.total * 100) : "—",
          r.liberacao.total
            ? `das EPS liberadas até o início · ${dashPlural(r.liberacao.atrasadas, "atrasada", "atrasadas")}`
            : "sem liberação no recorte",
          r.liberacao.atrasadas ? "critico" : "ok"
        )}
        ${cartaoResp(
          "EPS · início",
          r.epsTotal ? dashPct(r.epsNoPrazo / r.epsTotal * 100) : "—",
          r.epsTotal
            ? `iniciaram no prazo · ${dashPlural(epsNomes.reduce((s, n) => s + r.porEps[n].naoIniciou, 0), "não iniciou", "não iniciaram")}`
            : "sem ação comercial com go-live no recorte",
          r.epsTotal && r.epsNoPrazo < r.epsTotal ? "critico" : "ok"
        )}
      </div>

      ${
        epsNomes.length
          ? `
            <div class="hist-eps-grade">
              ${epsNomes.map(n => {
                const e = r.porEps[n];
                const total = e.noPrazo + e.atraso + e.naoIniciou;
                const pct = v => total ? v / total * 100 : 0;
                return `
                  <div class="hist-eps-linha">
                    <strong>${esc(humanizarV9(n))}</strong>
                    <div class="hist-empilhada" title="${e.noPrazo} no prazo · ${e.atraso} com atraso · ${e.naoIniciou} não iniciaram">
                      <i class="ok" style="width:${pct(e.noPrazo)}%"></i>
                      <i class="atencao" style="width:${pct(e.atraso)}%"></i>
                      <i class="critico" style="width:${pct(e.naoIniciou)}%"></i>
                    </div>
                    <small>
                      ${e.noPrazo} no prazo · ${e.atraso} com atraso${e.atraso ? ` (média ${String((e.somaAtraso / e.atraso).toFixed(1)).replace(".", ",")} dias)` : ""} · ${e.naoIniciou} não ${e.naoIniciou === 1 ? "iniciou" : "iniciaram"}
                    </small>
                  </div>
                `;
              }).join("")}
              <div class="dash-legenda">
                <span><i style="background:var(--c-ok)"></i>No prazo</span>
                <span><i style="background:var(--c-wait)"></i>Com atraso</span>
                <span><i style="background:var(--c-stop)"></i>Não iniciou</span>
              </div>
            </div>
          `
          : ""
      }

      <div class="v9-table-scroll">
        <table class="v9-table hist-tabela-exec">
          <thead>
            <tr>
              <th>Campanha</th>
              <th>Início previsto</th>
              <th>Planejamento</th>
              <th>Comercial</th>
              <th>EPS</th>
            </tr>
          </thead>
          <tbody>
            ${comPrazo.map(c => {
              const e = dashExecucaoFiltrada(c);
              const lib = Object.fromEntries(e.liberacao.map(l => [l.eps, l]));
              return `
                <tr class="abrir-campanha" data-code="${esc(c.codigo_campanha)}">
                  <td class="v9-table-title">
                    <strong>${esc(c.codigo_campanha)}</strong>
                    <small>${esc(c.nome_campanha)}</small>
                  </td>
                  <td>${esc(dashDataBr(dashData(c.dt_inicio_prevista)))}</td>
                  <td>${e.planejamento ? dashPill(e.planejamento.tom, e.planejamento.tom === "ok" ? "No prazo" : `+${e.planejamento.dias}d`, e.planejamento.texto) : `<span class="muted">—</span>`}</td>
                  <td>${e.comercial ? dashPill(e.comercial.tom, e.comercial.pendente ? `Pendente ${e.comercial.du}du` : `${e.comercial.du}du`, e.comercial.texto) : `<span class="muted">—</span>`}</td>
                  <td><div class="hist-eps-celula">
                    ${e.eps.map(x => `
                      <span class="hist-eps-tag">
                        <b>${esc(humanizarV9(x.eps))}</b>
                        ${lib[x.eps]?.tom === "critico" ? dashPill("atencao", "Lib. atrasada", lib[x.eps].texto) : ""}
                        ${dashPill(x.tom, x.rotulo, x.texto + (x.fechamento ? ` · finalizou em ${dashDataBr(x.fechamento)}` : ""))}
                      </span>
                    `).join("") || `<span class="muted">—</span>`}
                  </div></td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
      <p class="hist-nota">Passe o mouse sobre cada etiqueta para ver o detalhe. du = dias úteis; d = dias corridos.</p>
    </section>
  `;
}


/* ==========================================================
   RENDER
   ========================================================== */

function dashboardConteudo() {

  dashEstilosExtras();

  const lista = dashboardFiltrar();
  const c = dashConsolidado(lista);
  const f = dashboardFiltros;
  const exec = dashResumoExecucao(lista);

  const filtrando = Object.values(f).some(Boolean);

  const cardsMeta = Object.entries(c.metas).map(([base, m]) => {
    const pct = m.meta ? m.realizado / m.meta * 100 : null;
    return [
      `Atingimento · ${DASH_BASES[base] || base}`,
      dashPct(pct),
      `${dashNumero(m.realizado)} de ${dashNumero(m.meta)} em ${dashPlural(m.acoes, "ação", "ações")} com meta`,
      pct === null ? "" : pct >= 100 ? "ok" : pct >= 70 ? "atencao" : "critico"
    ];
  });

  const kpis = [
    ["Campanhas", dashNumero(c.total), `${c.encerradas} encerrada${c.encerradas === 1 ? "" : "s"} · ${c.total - c.encerradas} em andamento`, ""],
    ...cardsMeta,
    ["Matrículas", dashNumero(c.soma.matriculas), "apuradas pelo robô", ""],
    ["Vendas", dashNumero(c.soma.vendas), "apuradas pelo robô", ""],
    ["EPS no prazo", exec.epsTotal ? dashPct(exec.epsNoPrazo / exec.epsTotal * 100) : "—", exec.epsTotal ? `${exec.epsNoPrazo} de ${exec.epsTotal} inícios de ação comercial` : "sem go-live no recorte", exec.epsTotal ? (exec.epsNoPrazo === exec.epsTotal ? "ok" : "critico") : ""],
    ["Campanhas apuradas", dashNumero(c.total - c.semApuracao), `de ${dashNumero(c.total)} no filtro`, ""]
  ];

  const graficos = [
    dashGraficoAtingimento(lista),
    dashGraficoPorEps(lista),
    dashGraficoMensal(lista)
  ].filter(Boolean);

  return `
    <div class="v9-contained-page hist">

      <!-- cabecalho -->
      <header class="hist-cabecalho">
        <div>
          <span class="hist-kicker">Histórico de campanhas${f.eps ? ` · visão da EPS ${esc(humanizarV9(f.eps))}` : ""}</span>
          <h1>${dashPlural(c.total, "campanha", "campanhas")} ${filtrando ? "no filtro atual" : "no portfólio"}</h1>
          <p>
            Resultado e execução de cada campanha, em um lugar só. Os números são os da apuração
            do robô, os mesmos da aba Dashboard${c.semApuracao ? `; ${dashPlural(c.semApuracao, "campanha ainda sem apuração fica", "campanhas ainda sem apuração ficam")} fora dos totais` : ""}.
            O funil completo de cada campanha fica no Dashboard.
          </p>
        </div>
      </header>

      <!-- filtros -->
      <section class="hist-filtros">
        <div class="hist-busca">
          <label>Buscar por nome ou código</label>
          <input id="dashBusca" value="${esc(f.busca)}" placeholder="Ex.: CAM-006, rematrícula, boletos">
        </div>
        ${dashSelect("dashEps", "EPS", dashOpcoes(dashEpsDaCampanha), f.eps, humanizarV9)}
        ${dashSelect("dashProduto", "Produto", dashOpcoes(camp => [camp.produto]), f.produto, humanizarV9)}
        ${dashSelect("dashTipo", "Tipo de campanha", dashOpcoes(camp => [camp.tipo_acao]), f.tipo, humanizarV9)}
        ${dashSelect("dashSubtipo", "Subtipo (ação comercial)", dashOpcoes(camp => camp.tipo_acao === "INCENTIVO" ? [] : [camp.subtipo_acao]), f.subtipo, v => (typeof SUBTIPOS_ACAO !== "undefined" && SUBTIPOS_ACAO[v]) || humanizarV9(v))}
        ${dashSelect("dashSituacao", "Situação", ["ATIVA", "ENCERRADA"], f.situacao, v => v === "ATIVA" ? "Em andamento" : "Encerrada")}
        ${dashSelect("dashClassificacao", "Resultado", Object.keys(DASH_CLASSES), f.classificacao, v => DASH_CLASSES[v])}
        ${dashSelect("dashSupercanal", "Supercanal", dashOpcoes(dashSupercanais), f.supercanal, humanizarV9)}
        ${dashSelect("dashModalidade", "Modalidade", dashOpcoes(dashModalidades), f.modalidade, humanizarV9)}
        ${dashSelect("dashMes", "Mês de início", dashOpcoes(camp => [dashMesReferencia(camp)]).reverse(), f.mes, dashMesLabel)}
        <div class="hist-limpar">
          <button class="apu-btn" id="dashLimpar" ${filtrando ? "" : "disabled"}>Limpar filtros</button>
        </div>
      </section>

      <!-- resumo -->
      <section class="hist-kpis">
        ${kpis.map(([rotulo, valor, apoio, tom]) => `
          <article class="hist-kpi ${tom}">
            <span>${esc(rotulo)}</span>
            <strong>${esc(valor)}</strong>
            <small>${esc(apoio)}</small>
          </article>
        `).join("")}
      </section>

      <!-- destaques -->
      ${dashDestaques(lista)}

      <!-- execucao e prazos -->
      ${dashPainelExecucao(lista)}

      <!-- resultado -->
      <section class="hist-secao">
        <div class="hist-secao-cab">
          <h2>Resultado</h2>
          <p>Como as campanhas terminaram, atingimento de meta, resultado por EPS e evolução mês a mês.</p>
        </div>

        <div class="hist-classes">
          ${Object.entries(DASH_CLASSES).map(([chave, rotulo]) => {
            const qtd = c.classes[chave];
            const largura = c.total ? (qtd / c.total * 100) : 0;
            return `
              <article class="hist-classe ${esc(chave.toLowerCase())}">
                <span>${esc(rotulo)}</span>
                <strong>${qtd}</strong>
                <div class="dash-barra"><i class="${esc(chave.toLowerCase())}" style="width:${largura}%"></i></div>
              </article>
            `;
          }).join("")}
        </div>
        <p class="hist-nota">Só conta campanha encerrada e classificada pelo Planejamento. A classificação é da ação como um todo, não de cada EPS.</p>

        ${graficos.length ? `<div class="dash-graficos">${graficos.join("")}</div>` : ""}
      </section>

      <!-- leitura automatica -->
      ${dashLeituraAutomatica(lista)}

      <!-- aprendizados -->
      ${
        (() => {
          const comTexto = lista.filter(
            camp => camp.encerramento?.analise_resultado || camp.encerramento?.aprendizados || camp.encerramento?.resumo
          );

          if (!comTexto.length) return "";

          return `
            <section class="v9-panel" style="margin-top:20px">
              <div class="v9-panel-head"><div>
                <h2>O que aprendemos (análise do Planejamento)</h2>
                <p>Análise registrada no encerramento de cada campanha. É o contexto que os números não contam.</p>
              </div></div>

              <div class="dash-aprendizados">
                ${comTexto.map(camp => `
                  <article class="dash-aprendizado ${esc((camp.encerramento?.classificacao_resultado || "sem").toLowerCase())}">
                    <div class="dash-aprendizado-topo">
                      <strong>${esc(camp.codigo_campanha)}</strong>
                      <span>${esc(DASH_CLASSES[camp.encerramento?.classificacao_resultado] || "Sem classificação")}</span>
                    </div>
                    <h4>${esc(camp.nome_campanha)}</h4>
                    ${camp.encerramento.resumo ? `<div class="dash-bloco"><b>Resultado</b><p>${esc(camp.encerramento.resumo)}</p></div>` : ""}
                    ${camp.encerramento.analise_resultado ? `<div class="dash-bloco"><b>Análise</b><p>${esc(camp.encerramento.analise_resultado)}</p></div>` : ""}
                    ${camp.encerramento.aprendizados ? `<div class="dash-bloco aprendizado"><b>Aprendizado</b><p>${esc(camp.encerramento.aprendizados)}</p></div>` : ""}
                  </article>
                `).join("")}
              </div>
            </section>
          `;
        })()
      }

      <!-- copys -->
      ${dashCopys(lista)}

      <!-- diario -->
      ${dashDiario(lista)}

      <!-- lista -->
      <section class="v9-campaigns-panel v9-panel" style="margin-top:20px">

        <div class="v9-panel-head">
          <div>
            <h2>Campanhas</h2>
            <p>Clique para abrir o histórico completo. ${f.eps ? `Números da ${esc(humanizarV9(f.eps))}.` : ""}</p>
          </div>
        </div>

        ${
          lista.length
            ? `
              <div class="v9-table-scroll">
                <table class="v9-table">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Campanha</th>
                      <th>EPS</th>
                      <th>Início</th>
                      <th>Execução</th>
                      <th>Resultado</th>
                      <th>Vendas</th>
                      <th>Matrículas</th>
                      <th>Meta</th>
                      <th>Atingimento</th>
                      <th>Retorno</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    ${lista.map(camp => {
                      const r = dashRealizado(camp);
                      const i = dashIndicadores(r);
                      const m = dashMeta(camp);
                      const classe = camp.encerramento?.classificacao_resultado;
                      const atingimento = m && m.meta ? m.realizado / m.meta * 100 : null;
                      const e = dashExecucaoFiltrada(camp);
                      const problemas = [
                        e.planejamento?.tom === "critico",
                        e.comercial?.tom === "critico",
                        ...e.liberacao.map(l => l.tom === "critico"),
                        ...e.eps.map(x => x.tom === "critico")
                      ].filter(Boolean).length;
                      const temPrazo = e.planejamento || e.comercial || e.eps.some(x => x.tom !== "neutro");

                      return `
                        <tr class="abrir-campanha" data-code="${esc(camp.codigo_campanha)}">
                          <td>${esc(camp.codigo_campanha)}</td>
                          <td class="v9-table-title">
                            <strong>${esc(camp.nome_campanha)}</strong>
                            <small>${esc(humanizarV9(camp.status_campanha))} · ${esc(humanizarV9(camp.produto))}${typeof rotuloSubtipoAcao === "function" && rotuloSubtipoAcao(camp) ? ` · ${esc(rotuloSubtipoAcao(camp))}` : ""}</small>
                          </td>
                          <td>${esc(f.eps ? humanizarV9(f.eps) : dashEpsDaCampanha(camp).map(humanizarV9).join(", ") || "—")}</td>
                          <td>${esc(dashData(camp.dt_inicio_prevista)?.toLocaleDateString("pt-BR") ?? "—")}</td>
                          <td>${
                            !temPrazo
                              ? `<span class="muted">—</span>`
                              : problemas
                                ? dashPill("critico", dashPlural(problemas, "atraso", "atrasos"))
                                : dashPill("ok", "No prazo")
                          }</td>
                          <td>${
                            classe
                              ? `<span class="v9-status-pill ${classe === "SUCESSO" ? "neutral" : classe === "SEM_SUCESSO" ? "critical" : "attention"}">${esc(DASH_CLASSES[classe])}</span>`
                              : `<span class="muted">—</span>`
                          }</td>
                          <td>${camp.sem_apuracao ? `<span class="muted">—</span>` : dashNumero(r.vendas)}</td>
                          <td>${camp.sem_apuracao ? `<span class="muted">—</span>` : dashNumero(r.matriculas)}</td>
                          <td>${m ? `${dashNumero(m.meta)} <small class="muted">${esc(DASH_BASES[m.base] || "")}</small>` : `<span class="muted">—</span>`}</td>
                          <td>${
                            atingimento === null
                              ? `<span class="muted">—</span>`
                              : `<span class="v9-status-pill ${atingimento >= 100 ? "neutral" : atingimento >= 70 ? "attention" : "critical"}">${dashPct(atingimento)}</span>`
                          }</td>
                          <td>${camp.sem_apuracao ? `<span class="muted">—</span>` : dashPct(i.retorno)}</td>
                          <td class="v9-linha-ir">›</td>
                        </tr>
                      `;
                    }).join("")}
                  </tbody>
                </table>
              </div>
            `
            : `
              <div class="v9-empty-state">
                <strong>Nenhuma campanha nesse recorte</strong>
                <span>Ajuste os filtros ou limpe a seleção para ver o portfólio inteiro.</span>
              </div>
            `
        }

      </section>

    </div>
  `;
}


function bindDashboardFiltros() {

  const ligar = (id, campo) => {
    const elemento =
      document.getElementById(id);

    if (!elemento) return;

    const evento =
      elemento.tagName === "INPUT"
        ? "oninput"
        : "onchange";

    elemento[evento] = () => {
      dashboardFiltros[campo] = elemento.value;

      renderPortal(
        usuarioAtual,
        campanhasCache
      );

      /* A busca perde o foco ao redesenhar a tela. Sem
         devolver o cursor, digitar vira uma letra por vez. */
      if (id === "dashBusca") {
        const novo =
          document.getElementById("dashBusca");

        if (novo) {
          novo.focus();
          novo.setSelectionRange(
            novo.value.length,
            novo.value.length
          );
        }
      }
    };
  };

  ligar("dashBusca", "busca");
  ligar("dashEps", "eps");
  ligar("dashProduto", "produto");
  ligar("dashTipo", "tipo");
  ligar("dashSubtipo", "subtipo");
  ligar("dashSituacao", "situacao");
  ligar("dashClassificacao", "classificacao");
  ligar("dashSupercanal", "supercanal");
  ligar("dashModalidade", "modalidade");
  ligar("dashMes", "mes");

  bindCopysDashboard();

  const limpar =
    document.getElementById("dashLimpar");

  if (limpar) {
    limpar.onclick = () => {
      Object.keys(dashboardFiltros).forEach(
        chave => dashboardFiltros[chave] = ""
      );

      renderPortal(
        usuarioAtual,
        campanhasCache
      );
    };
  }
}


async function carregarDashboard() {

  try {
    const [dados, apuracao] = await Promise.all([
      api("/api/internal/dashboard"),
      api("/api/internal/apuracao/dashboard")
    ]);

    dashboardDados =
      (dados.campanhas || [])
        .map(dashNormalizarCampanha)
        .map(c => dashAplicarApuracao(c, apuracao?.funil || []));

  } catch (erro) {
    dashboardDados = [];
    alert(erro.message);
  }
}


/* ---------- números oficiais = apuração do robô ----------
   Substitui o realizado de cada campanha (total e por EPS)
   pelo que o robô apurou. A meta continua a da Central.    */

function dashSoLetras(valor) {
  return String(valor || "").toUpperCase().replace(/[^A-Z]/g, "");
}

function dashAplicarApuracao(c, funil) {
  const codigo = String(c.codigo_campanha || "").toUpperCase();
  const linhas = funil.filter(
    r => String(r.codigo_campanha || "").toUpperCase() === codigo
  );

  if (!linhas.length) {
    c.sem_apuracao = true;
    c.realizado = {...DASH_FUNIL_VAZIO};
    Object.values(c.por_eps || {}).forEach(item => {
      item.realizado = {...DASH_FUNIL_VAZIO};
      item.valor_realizado = 0;
    });
    return c;
  }

  const base = c.metas?.base || linhas.find(r => r.meta_base)?.meta_base || "MATRICULAS";
  const num = v => Number(v || 0);
  const total = {...DASH_FUNIL_VAZIO};
  const porEps = {};
  let metaTotal = 0;
  let realizadoMetaTotal = 0;

  /* Chave da EPS: a que a Central já usa para essa campanha,
     casada pelas letras (VOXA = Voxa, LUMEN = Lumen). */
  const chaves = Object.keys(c.por_eps || {});

  linhas.forEach(r => {
    const chave =
      chaves.find(k => dashSoLetras(k) === dashSoLetras(r.eps))
      || dashEpsChave(r.eps);

    const realizado = {
      mailing:    num(r.mailing_enviado || r.mailing),
      trabalhado: num(r.trabalhados),
      tentativas: num(r.tentativas),
      alo:        num(r.alo),
      efetivos:   num(r.efetivos),
      vendas:     num(r.vendas),
      matriculas: num(r.matriculas)
    };

    const anterior = (c.por_eps || {})[chave] || {};
    const meta = Number(r.meta_eps || anterior.meta || 0);
    const valor = base === "VENDAS" ? realizado.vendas : realizado.matriculas;

    porEps[chave] = {
      ...anterior,
      meta: meta || null,
      realizado,
      valor_realizado: valor,
      status_apuracao: r.status_apuracao
    };

    Object.keys(total).forEach(k => total[k] += realizado[k]);
    if (meta) {
      metaTotal += meta;
      realizadoMetaTotal += valor;
    }
  });

  c.por_eps = porEps;
  c.realizado = total;
  c.metas = {
    ...(c.metas || {}),
    base,
    total: metaTotal ? {meta: metaTotal, realizado: realizadoMetaTotal} : null
  };
  c.sem_apuracao = false;
  return c;
}


/* ==========================================================
   GRAFICOS, LEITURA AUTOMATICA, COPYS E DIARIO
   ========================================================== */

function dashEstilosExtras() {
  if (document.getElementById("dashExtrasEstilos")) return;

  const style = document.createElement("style");
  style.id = "dashExtrasEstilos";
  style.textContent = `
    .dash-graficos{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:20px;margin-top:20px}
    .dash-graficos .v9-panel{margin:0}
    .dash-lista-barras{display:flex;flex-direction:column;gap:12px;margin-top:18px}
    .dash-barra.dupla{display:flex;flex-direction:column;gap:3px;height:auto;background:none}
    .dash-barra.dupla i{height:9px;border-radius:2px}
    .dash-barra.dupla i.vendas{background:var(--c-ink)}
    .dash-barra.dupla i.matriculas{background:var(--c-accent)}
    .dash-legenda{display:flex;gap:16px;margin-top:14px;color:var(--c-ink-2);font-size:13px}
    .dash-legenda i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
    .dash-barra i.ating-ok{background:var(--c-ok)}
    .dash-barra i.ating-perto{background:var(--c-wait)}
    .dash-barra i.ating-baixo{background:var(--c-stop)}
    .dash-leitura{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-top:20px}
    .dash-leitura article{padding:18px 20px;border:1px solid var(--c-rule);border-left:3px solid var(--c-ink-3);border-radius:8px;background:var(--c-surface)}
    .dash-leitura article.boa{border-left-color:var(--c-ok)}
    .dash-leitura article.atencao{border-left-color:var(--c-wait)}
    .dash-leitura article.abaixo{border-left-color:var(--c-stop)}
    .dash-leitura h4{margin:6px 0 10px;font-size:16px}
    .dash-leitura ul{margin:0;padding-left:18px}
    .dash-leitura li{margin:0 0 6px;color:var(--c-ink-2);font-size:14px;line-height:1.5}
    .dash-veredito{font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
    .dash-copys{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-top:20px}
    .dash-copy{padding:18px 20px;border:1px solid var(--c-rule);border-radius:8px;background:var(--c-surface)}
    .dash-copy p{white-space:pre-wrap;margin:10px 0;font-size:14px;line-height:1.55;color:var(--c-ink)}
    .dash-copy img{max-width:100%;border-radius:6px;border:1px solid var(--c-rule);margin-top:8px}
    .dash-diario{margin-top:18px}
    .dash-diario article{padding:12px 14px;border:1px solid var(--c-rule);border-left:3px solid var(--c-accent);border-radius:6px;background:var(--c-surface);margin-bottom:8px}
    .dash-diario article.edunova{border-left-color:var(--c-ink)}
    .dash-diario header{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--c-ink-3);margin-bottom:6px}
    .dash-diario header strong{color:var(--c-ink)}
    .dash-diario p{margin:0;white-space:pre-wrap;font-size:14px;line-height:1.55}
    .dash-aviso{margin-top:14px;padding:12px 14px;border:1px dashed var(--c-rule);border-radius:6px;color:var(--c-ink-2);font-size:14px;line-height:1.5}
    @media (max-width:760px){.dash-graficos{grid-template-columns:1fr}}
    /* ---------- Historico (layout limpo, mesma linguagem do Dashboard) ---------- */
    .hist{color:var(--c-ink)}
    .hist-cabecalho{margin:4px 0 18px}
    .hist-kicker{display:block;font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--c-ink-3);margin-bottom:6px}
    .hist-cabecalho h1{margin:0 0 6px;font-size:30px;font-weight:600;letter-spacing:-.025em}
    .hist-cabecalho p{margin:0;color:var(--c-ink-2);font-size:14px;line-height:1.55;max-width:80ch}
    .hist-filtros{display:grid;grid-template-columns:minmax(220px,2fr) repeat(4,minmax(130px,1fr));gap:10px;align-items:end;padding:14px;background:var(--c-surface);border:1px solid var(--c-rule);border-radius:12px;margin-bottom:14px}
    .hist-filtros label{display:block;margin:0 0 5px;font-size:12px;font-weight:600;color:var(--c-ink-2)}
    .hist-filtros select,.hist-filtros input{width:100%;height:36px;padding:0 10px;border:1px solid var(--c-rule);border-radius:8px;background:var(--c-surface);font-size:13px;color:var(--c-ink)}
    .hist-limpar{display:flex;align-items:end}
    .hist-limpar .apu-btn{height:36px;width:100%}
    .hist-limpar .apu-btn:disabled{opacity:.45;cursor:default}
    .hist-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));background:var(--c-surface);border:1px solid var(--c-rule);border-radius:12px;overflow:hidden;margin-bottom:18px}
    .hist-kpi{padding:16px 18px;border-left:1px solid var(--c-rule-soft);border-top:3px solid transparent;min-width:0}
    .hist-kpi:first-child{border-left:0}
    .hist-kpi span{display:block;color:var(--c-ink-2);font-size:13px}
    .hist-kpi strong{display:block;font-size:26px;font-weight:600;letter-spacing:-.02em;margin-top:4px;line-height:1.1;font-variant-numeric:tabular-nums}
    .hist-kpi small{display:block;margin-top:6px;color:var(--c-ink-3);font-size:12px;line-height:1.4}
    .hist-kpi.ok{border-top-color:var(--c-ok)}
    .hist-kpi.atencao{border-top-color:var(--c-wait)}
    .hist-kpi.critico{border-top-color:var(--c-stop)}
    .hist-kpi.ok strong{color:var(--c-ok)}
    .hist-kpi.critico strong{color:var(--c-stop)}
    .hist-secao{background:var(--c-surface);border:1px solid var(--c-rule);border-radius:12px;padding:20px 22px;margin-bottom:18px}
    .hist-secao-cab{padding-bottom:14px;border-bottom:1px solid var(--c-rule);margin-bottom:16px}
    .hist-secao-cab h2{margin:0 0 4px;font-size:18px;font-weight:600;letter-spacing:-.01em}
    .hist-secao-cab p{margin:0;color:var(--c-ink-2);font-size:13px;line-height:1.5;max-width:90ch}
    .hist-destaques{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .hist-destaque{border:1px solid var(--c-rule);border-radius:10px;padding:14px 16px;background:var(--c-paper)}
    .hist-destaque header{display:flex;align-items:center;gap:8px;margin-bottom:10px}
    .hist-destaque h3{margin:0;font-size:15px;font-weight:600;flex:1}
    .hist-destaque header small{font-size:12px;color:var(--c-ink-3);font-weight:600}
    .hist-ponto{width:9px;height:9px;border-radius:50%;background:var(--c-ink-3)}
    .hist-destaque.bom .hist-ponto{background:var(--c-ok)}
    .hist-destaque.ruim .hist-ponto{background:var(--c-stop)}
    .hist-destaque ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
    .hist-destaque li{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;background:var(--c-surface);border:1px solid var(--c-rule-soft);border-radius:8px;font-size:13px;line-height:1.45;cursor:pointer}
    .hist-destaque li:hover{border-color:var(--c-ink-3)}
    .hist-tag{flex-shrink:0;font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--c-ink-2);background:var(--c-rule-soft);border-radius:4px;padding:2px 6px;margin-top:1px}
    .hist-vazio{margin:0;color:var(--c-ink-3);font-size:13px}
    .hist-resps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
    .hist-resp{border:1px solid var(--c-rule);border-left:3px solid var(--c-ink-3);border-radius:8px;padding:12px 14px;background:var(--c-paper)}
    .hist-resp.ok{border-left-color:var(--c-ok)}
    .hist-resp.critico{border-left-color:var(--c-stop)}
    .hist-resp span{display:block;font-size:12px;font-weight:600;color:var(--c-ink-2)}
    .hist-resp strong{display:block;font-size:24px;font-weight:600;margin:4px 0;font-variant-numeric:tabular-nums}
    .hist-resp small{display:block;font-size:12px;color:var(--c-ink-3);line-height:1.4}
    .hist-eps-grade{display:flex;flex-direction:column;gap:10px;margin-bottom:18px}
    .hist-eps-linha{display:grid;grid-template-columns:140px 1fr;gap:4px 14px;align-items:center}
    .hist-eps-linha strong{font-size:14px}
    .hist-eps-linha small{grid-column:2;font-size:12px;color:var(--c-ink-3)}
    .hist-empilhada{display:flex;height:12px;border-radius:3px;overflow:hidden;background:var(--c-rule-soft)}
    .hist-empilhada i.ok{background:var(--c-ok)}
    .hist-empilhada i.atencao{background:var(--c-wait)}
    .hist-empilhada i.critico{background:var(--c-stop)}
    .hist-pill{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:2px 9px;white-space:nowrap;border:1px solid transparent;cursor:default}
    .hist-pill.ok{color:var(--c-ok);background:#E7F2EC}
    .hist-pill.atencao{color:var(--c-wait);background:#FBF1DE}
    .hist-pill.critico{color:var(--c-stop);background:#F8E5E5}
    .hist-pill.neutro{color:var(--c-ink-2);background:var(--c-rule-soft)}
    .hist-tabela-exec td{vertical-align:middle}
    .hist-eps-celula{display:flex;flex-wrap:wrap;gap:6px 14px}
    .hist-eps-tag{display:inline-flex;align-items:center;gap:6px}
    .hist-eps-tag b{font-size:13px;font-weight:600}
    .hist-nota{margin:10px 0 0;font-size:12px;color:var(--c-ink-3)}
    .hist-classes{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
    .hist-classe{border:1px solid var(--c-rule);border-radius:8px;padding:12px 14px;background:var(--c-paper)}
    .hist-classe span{display:block;font-size:13px;color:var(--c-ink-2)}
    .hist-classe strong{display:block;font-size:24px;font-weight:600;margin:4px 0 8px}
    .hist-classe .dash-barra{height:6px}
    .hist .dash-graficos{margin-top:18px}
    .hist > .v9-panel{border-radius:12px;padding:20px 22px;margin:0 0 18px !important}
    .hist .v9-panel h2{font-size:18px;font-weight:600;letter-spacing:-.01em;margin:0 0 4px}
    .hist .v9-panel-head{padding-bottom:14px;border-bottom:1px solid var(--c-rule);margin-bottom:4px}
    .hist .v9-panel-head p{font-size:13px;color:var(--c-ink-2);margin:0}
    .hist .hist-secao .v9-panel{background:var(--c-paper);border-radius:10px;padding:16px 18px;margin:0}
    .hist .hist-secao .v9-panel h2{font-size:15px}
    .hist .v9-table td:first-child{white-space:nowrap}
    .hist .v9-table td{font-variant-numeric:tabular-nums}
    @media (max-width:1100px){.hist-filtros{grid-template-columns:repeat(2,minmax(0,1fr))}.hist-busca{grid-column:1/-1}.hist-resps,.hist-classes{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media (max-width:760px){.hist-destaques{grid-template-columns:1fr}.hist-resps,.hist-classes{grid-template-columns:1fr}.hist-eps-linha{grid-template-columns:1fr}.hist-eps-linha small{grid-column:1}}
  `;
  document.head.appendChild(style);
}

function dashClasseAtingimento(pct) {
  return pct >= 100 ? "ating-ok" : pct >= 70 ? "ating-perto" : "ating-baixo";
}

function dashDataCurta(texto) {
  if (!texto) return "";
  const [ano, mes, dia] = String(texto).slice(0, 10).split("-");
  return dia && mes ? `${dia}/${mes}/${ano}` : texto;
}

/* Painel vazio para quando uma única campanha está no filtro
   e não há copy ou diário. Diferencia "não tem registro" de
   "o servidor não mandou o campo" — este segundo caso indica
   historico_service ou main.py desatualizados no Render.   */
function dashPainelVazio(titulo, campanha, campo, textoSemRegistro) {
  const servidorSemCampo = !Array.isArray(campanha[campo]);

  return `
    <section class="v9-panel" style="margin-top:20px">
      <div class="v9-panel-head"><div>
        <h2>${esc(titulo)}</h2>
      </div></div>
      <div class="dash-aviso">
        ${
          servidorSemCampo
            ? `O servidor não enviou este dado para ${esc(campanha.codigo_campanha)}. O backend publicado está desatualizado: confira o deploy do historico_service.py e do main.py.`
            : `${esc(textoSemRegistro)}`
        }
      </div>
    </section>
  `;
}


/* ---------- 1. atingimento por campanha ---------- */

function dashGraficoAtingimento(lista) {
  const itens = lista
    .map(c => ({c, m: dashMeta(c)}))
    .filter(x => x.m && x.m.meta)
    .map(x => ({...x, pct: x.m.realizado / x.m.meta * 100}))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 15);

  if (!itens.length) return "";

  return `
    <section class="v9-panel">
      <div class="v9-panel-head"><div>
        <h2>Atingimento por campanha</h2>
        <p>Apurado pelo robô sobre a meta. Verde a partir de 100%, âmbar de 70% a 99%.</p>
      </div></div>

      <div class="dash-lista-barras">
        ${itens.map(({c, m, pct}) => `
          <div>
            <div class="dash-etapa-topo">
              <span>${esc(c.codigo_campanha)} · ${esc(c.nome_campanha)}</span>
              <strong>${dashPct(pct)}</strong>
            </div>
            <div class="dash-barra">
              <i class="${dashClasseAtingimento(pct)}" style="width:${Math.min(100, pct / 1.5)}%"></i>
            </div>
            <div class="dash-etapa-pe">
              ${dashNumero(m.realizado)} de ${dashNumero(m.meta)} ${esc(DASH_BASES[m.base] || "")}
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}


/* ---------- 2. resultado por EPS ---------- */

function dashGraficoPorEps(lista) {
  if (dashboardFiltros.eps) return "";

  const porEps = {};

  lista.forEach(c => {
    if (c.sem_apuracao) return;
    Object.entries(c.por_eps || {}).forEach(([eps, item]) => {
      const alvo = porEps[eps] = porEps[eps] || {
        vendas: 0, matriculas: 0, metas: {}
      };

      alvo.vendas += item.realizado?.vendas || 0;
      alvo.matriculas += item.realizado?.matriculas || 0;

      const base = c.metas?.base;
      if (base && item.meta) {
        alvo.metas[base] = alvo.metas[base] || {meta: 0, realizado: 0};
        alvo.metas[base].meta += Number(item.meta);
        alvo.metas[base].realizado += Number(item.valor_realizado || 0);
      }
    });
  });

  const nomes = Object.keys(porEps).sort();
  if (nomes.length < 2) return "";

  const teto = Math.max(1, ...nomes.map(n => Math.max(porEps[n].vendas, porEps[n].matriculas)));

  return `
    <section class="v9-panel">
      <div class="v9-panel-head"><div>
        <h2>Resultado por EPS</h2>
        <p>Soma das campanhas selecionadas, EPS a EPS, pela apuração do robô.</p>
      </div></div>

      <div class="dash-lista-barras">
        ${nomes.map(nome => {
          const e = porEps[nome];
          const atingimentos = Object.entries(e.metas)
            .map(([base, m]) => `${dashPct(m.meta ? m.realizado / m.meta * 100 : null)} da meta de ${DASH_BASES[base]}`)
            .join(" · ");

          return `
            <div>
              <div class="dash-etapa-topo">
                <span>${esc(humanizarV9(nome))}</span>
                <strong>${dashNumero(e.matriculas)} mat. · ${dashNumero(e.vendas)} vendas</strong>
              </div>
              <div class="dash-barra dupla">
                <i class="vendas" style="width:${e.vendas / teto * 100}%"></i>
                <i class="matriculas" style="width:${e.matriculas / teto * 100}%"></i>
              </div>
              <div class="dash-etapa-pe">${esc(atingimentos) || "&nbsp;"}</div>
            </div>
          `;
        }).join("")}
      </div>

      <div class="dash-legenda">
        <span><i style="background:var(--c-ink)"></i>Vendas</span>
        <span><i style="background:var(--c-accent)"></i>Matrículas</span>
      </div>
    </section>
  `;
}


/* ---------- 3. evolucao mensal ---------- */

function dashGraficoMensal(lista) {
  const meses = {};

  lista.forEach(c => {
    const mes = dashMesReferencia(c);
    if (!mes || c.sem_apuracao) return;

    const r = dashRealizado(c);
    meses[mes] = meses[mes] || {vendas: 0, matriculas: 0, acoes: 0};
    meses[mes].vendas += r.vendas || 0;
    meses[mes].matriculas += r.matriculas || 0;
    meses[mes].acoes += 1;
  });

  const chaves = Object.keys(meses).sort();
  if (chaves.length < 2) return "";

  const teto = Math.max(1, ...chaves.map(m => Math.max(meses[m].vendas, meses[m].matriculas)));

  return `
    <section class="v9-panel">
      <div class="v9-panel-head"><div>
        <h2>Evolução por mês de início</h2>
        <p>Vendas e matrículas apuradas das campanhas iniciadas em cada mês.</p>
      </div></div>

      <div class="dash-lista-barras">
        ${chaves.map(mes => `
          <div>
            <div class="dash-etapa-topo">
              <span>${esc(dashMesLabel(mes))} · ${meses[mes].acoes} ${meses[mes].acoes === 1 ? "ação" : "ações"}</span>
              <strong>${dashNumero(meses[mes].matriculas)} mat. · ${dashNumero(meses[mes].vendas)} vendas</strong>
            </div>
            <div class="dash-barra dupla">
              <i class="vendas" style="width:${meses[mes].vendas / teto * 100}%"></i>
              <i class="matriculas" style="width:${meses[mes].matriculas / teto * 100}%"></i>
            </div>
          </div>
        `).join("")}
      </div>

      <div class="dash-legenda">
        <span><i style="background:var(--c-ink)"></i>Vendas</span>
        <span><i style="background:var(--c-accent)"></i>Matrículas</span>
      </div>
    </section>
  `;
}


/* ---------- 4. leitura automatica da apuracao ----------
   Regras simples e explicaveis, calculadas sobre os numeros
   apurados: meta, comparacao com a media do portfolio e a
   etapa do funil com maior perda. Complementa a analise do
   Planejamento, nao substitui. */

const DASH_INDICADORES_LEITURA = [
  ["retorno", "Retorno sobre a base"],
  ["conversao", "Conversão de venda"],
  ["alo", "% alô sobre a base"],
  ["trabalhado", "% da base trabalhada"],
  ["matricula", "Matrícula sobre venda"]
];

const DASH_PASSAGENS = [
  ["mailing", "trabalhado", "Base → Trabalhado"],
  ["mailing", "alo", "Base → Alô"],
  ["alo", "efetivos", "Alô → Efetivos"],
  ["efetivos", "vendas", "Efetivos → Vendas"],
  ["vendas", "matriculas", "Vendas → Matrículas"]
];

function dashMediaPortfolio() {
  const soma = {...DASH_FUNIL_VAZIO};
  let quantidade = 0;

  dashboardDados.forEach(c => {
    const r = dashRealizado(c);
    if (!r || !r.mailing) return;
    quantidade += 1;
    Object.keys(soma).forEach(chave => soma[chave] += r[chave] || 0);
  });

  return {soma, indicadores: dashIndicadores(soma), quantidade};
}

function dashLeituraCampanha(c, media) {
  const r = dashRealizado(c);
  const m = dashMeta(c);
  const ind = dashIndicadores(r);
  const pontos = [];
  let veredito = null;

  if (m && m.meta) {
    const pct = m.realizado / m.meta * 100;
    veredito = pct >= 100 ? "boa" : pct >= 70 ? "atencao" : "abaixo";
    pontos.push(
      pct >= 100
        ? `Meta batida: ${dashPct(pct)} (${dashNumero(m.realizado)} de ${dashNumero(m.meta)} ${DASH_BASES[m.base]}).`
        : `Ficou em ${dashPct(pct)} da meta (${dashNumero(m.realizado)} de ${dashNumero(m.meta)} ${DASH_BASES[m.base]}); faltaram ${dashNumero(Math.max(0, m.meta - m.realizado))}.`
    );
  }

  if (r.mailing && media.quantidade >= 3) {
    const destaques = [];

    DASH_INDICADORES_LEITURA.forEach(([chave, rotulo]) => {
      const valor = ind[chave];
      const ref = media.indicadores[chave];
      if (valor === null || !ref) return;
      destaques.push({rotulo, valor, ref, rel: valor / ref - 1});
    });

    const melhor = destaques.filter(d => d.rel >= 0.2).sort((a, b) => b.rel - a.rel)[0];
    const pior = destaques.filter(d => d.rel <= -0.2).sort((a, b) => a.rel - b.rel)[0];

    if (melhor) {
      pontos.push(`Ponto forte: ${melhor.rotulo.toLowerCase()} de ${dashPct(melhor.valor)}, ${dashPct(melhor.rel * 100)} acima da média do portfólio (${dashPct(melhor.ref)}).`);
    }

    if (pior) {
      pontos.push(`Ponto de atenção: ${pior.rotulo.toLowerCase()} de ${dashPct(pior.valor)}, ${dashPct(Math.abs(pior.rel) * 100)} abaixo da média (${dashPct(pior.ref)}).`);
    }

    /* Maior perda relativa no funil, comparada com a mesma
       passagem na media do portfolio. */
    const perdas = DASH_PASSAGENS
      .map(([de, para, rotulo]) => {
        if (!r[de] || r[para] === undefined) return null;
        const taxa = r[para] / r[de];
        const ref = media.soma[de] ? media.soma[para] / media.soma[de] : null;
        if (!ref) return null;
        return {rotulo, taxa, ref, rel: taxa / ref - 1};
      })
      .filter(Boolean)
      .sort((a, b) => a.rel - b.rel);

    if (perdas[0] && perdas[0].rel <= -0.15) {
      pontos.push(`Maior perda no funil: ${perdas[0].rotulo} (${dashPct(perdas[0].taxa * 100)} contra ${dashPct(perdas[0].ref * 100)} na média).`);
    }

    if (!veredito && ind.retorno !== null && media.indicadores.retorno) {
      const rel = ind.retorno / media.indicadores.retorno;
      veredito = rel >= 1.1 ? "boa" : rel >= 0.9 ? "atencao" : "abaixo";
      pontos.unshift(`Retorno de ${dashPct(ind.retorno)} contra ${dashPct(media.indicadores.retorno)} na média do portfólio.`);
    }
  }

  const diario = (c.diario || []).filter(
    item => !dashboardFiltros.eps || item.eps === dashboardFiltros.eps
  );

  if (diario.length) {
    pontos.push(`${diario.length} registro${diario.length === 1 ? "" : "s"} no diário de bordo — veja o contexto abaixo.`);
  }

  if (!veredito) return null;

  return {veredito, pontos};
}

function dashLeituraAutomatica(lista) {
  const media = dashMediaPortfolio();

  const leituras = lista
    .map(c => ({c, l: dashLeituraCampanha(c, media)}))
    .filter(x => x.l)
    .sort((a, b) => Number(dashCampanhaEncerrada(b.c)) - Number(dashCampanhaEncerrada(a.c)))
    .slice(0, 12);

  if (!leituras.length) return "";

  const rotulos = {
    boa: "Resultado bom",
    atencao: "Resultado próximo do esperado",
    abaixo: "Resultado abaixo do esperado"
  };

  return `
    <section class="v9-panel" style="margin-top:20px">
      <div class="v9-panel-head"><div>
        <h2>Leitura automática da apuração</h2>
        <p>
          Gerada a partir dos números: meta, comparação com a média do portfólio
          (${media.quantidade} ações com base) e a etapa do funil com maior perda.
          Complementa a análise do Planejamento.
        </p>
      </div></div>

      <div class="dash-leitura">
        ${leituras.map(({c, l}) => `
          <article class="${l.veredito}">
            <div class="dash-aprendizado-topo">
              <strong>${esc(c.codigo_campanha)}</strong>
              <span class="dash-veredito">${rotulos[l.veredito]}</span>
            </div>
            <h4>${esc(c.nome_campanha)}</h4>
            <ul>${l.pontos.map(p => `<li>${esc(p)}</li>`).join("")}</ul>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}


/* ---------- 5. copys utilizadas ---------- */

function dashCopys(lista) {
  const f = dashboardFiltros;

  const cartoes = [];

  lista.forEach(c => {
    (c.copys || [])
      .filter(item => !f.eps || item.eps === f.eps)
      .filter(item => item.copy_whatsapp || item.tem_imagem || (item.canais || []).length)
      .forEach(item => cartoes.push({c, item}));
  });

  if (!cartoes.length) {
    return lista.length === 1
      ? dashPainelVazio(
          "Copys e canais utilizados",
          lista[0],
          "copys",
          f.eps
            ? `A ${humanizarV9(f.eps)} não registrou copy nem canais nesta campanha.`
            : "Nenhuma EPS registrou copy nem canais nesta campanha."
        )
      : "";
  }

  return `
    <section class="v9-panel" style="margin-top:20px">
      <div class="v9-panel-head"><div>
        <h2>Copys e canais utilizados</h2>
        <p>Como cada EPS atuou em cada campanha, com a copy de WhatsApp e a imagem quando houver.</p>
      </div></div>

      <div class="dash-copys">
        ${cartoes.slice(0, 30).map(({c, item}) => `
          <article class="dash-copy">
            <div class="dash-aprendizado-topo">
              <strong>${esc(c.codigo_campanha)} · ${esc(humanizarV9(item.eps))}</strong>
              <span>${esc((item.canais || []).map(humanizarV9).join(", ") || "—")}</span>
            </div>
            <h4 style="margin:6px 0 0;font-size:15px">${esc(c.nome_campanha)}</h4>
            ${
              item.copy_whatsapp
                ? `<p>${esc(item.copy_whatsapp)}</p>`
                : `<p class="muted">Sem copy registrada.</p>`
            }
            ${
              item.tem_imagem
                ? `<div class="dash-copy-imagem">
                     <button class="btn secondary dash-ver-imagem"
                             data-code="${esc(c.codigo_campanha)}"
                             data-eps="${esc(item.eps)}">
                       Ver imagem
                     </button>
                   </div>`
                : ""
            }
          </article>
        `).join("")}
      </div>
      ${cartoes.length > 30 ? `<p class="muted" style="margin-top:12px">Mostrando 30 de ${cartoes.length}. Use os filtros para ver as demais.</p>` : ""}
    </section>
  `;
}

function bindCopysDashboard() {
  document.querySelectorAll(".dash-ver-imagem").forEach(botao => {
    botao.onclick = async () => {
      const caixa = botao.parentElement;
      const epsAlvo = dashEpsChave(botao.dataset.eps);

      try {
        botao.disabled = true;
        botao.textContent = "Carregando...";

        const dados = await api(
          `/api/internal/campaigns/${encodeURIComponent(botao.dataset.code)}/atuacao`
        );

        const item = (dados.eps || []).find(
          x => dashEpsChave(x.eps) === epsAlvo
        );

        if (!item || !item.imagem_base64) {
          caixa.innerHTML = `<span class="muted">Imagem não encontrada.</span>`;
          return;
        }

        caixa.innerHTML = `
          <img
            src="data:${esc(item.imagem_tipo || "image/png")};base64,${item.imagem_base64}"
            alt="Imagem da copy de ${esc(epsAlvo)}"
          >
        `;

      } catch (erro) {
        caixa.innerHTML = `<span class="muted">${esc(erro.message)}</span>`;
      }
    };
  });
}


/* ---------- 6. diario de bordo ---------- */

function dashDiario(lista) {
  const f = dashboardFiltros;

  const entradas = [];

  lista.forEach(c => {
    (c.diario || [])
      .filter(item => !f.eps || item.eps === f.eps)
      .forEach(item => entradas.push({c, item}));
  });

  if (!entradas.length) {
    return lista.length === 1
      ? dashPainelVazio(
          "Diário de bordo",
          lista[0],
          "diario",
          "Ainda não há registros no diário de bordo desta campanha."
        )
      : "";
  }

  entradas.sort((a, b) => String(b.item.data).localeCompare(String(a.item.data)));

  const limite = lista.length === 1 ? entradas.length : 40;

  return `
    <section class="v9-panel" style="margin-top:20px">
      <div class="v9-panel-head"><div>
        <h2>Diário de bordo</h2>
        <p>
          Impactos e benefícios registrados dia a dia pelas EPS e pela EduNova.
          ${lista.length === 1 ? "" : "Busque uma campanha para ver o diário completo dela."}
        </p>
      </div></div>

      <div class="dash-diario">
        ${entradas.slice(0, limite).map(({c, item}) => `
          <article class="${item.origem === "EDUNOVA" ? "edunova" : ""}">
            <header>
              <strong>${esc(dashDataCurta(item.data))} · ${esc(c.codigo_campanha)} · ${esc(humanizarV9(item.eps))}</strong>
              <span>${item.origem === "EDUNOVA" ? "EduNova" : "EPS"}${item.autor ? " · " + esc(item.autor) : ""}</span>
            </header>
            <p>${esc(item.texto)}</p>
          </article>
        `).join("")}
      </div>
      ${entradas.length > limite ? `<p class="muted">Mostrando ${limite} de ${entradas.length} registros.</p>` : ""}
    </section>
  `;
}