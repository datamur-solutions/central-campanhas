/* ============================================================
   DASHBOARD DE APURACAO
   Aba "Dashboard" do portal interno. Le o funil paralelo que o
   robo grava (GET /api/internal/apuracao/dashboard) e monta
   tudo no navegador: os filtros nao voltam ao servidor.

   Usa do interno.js: api(), esc(), viewAtual, renderPortal,
   usuarioAtual, campanhasCache. Por isso carrega depois dele.
   ============================================================ */

const APU = {
  dados: null,
  erro: null,
  f: { campanha: "", eps: "", produto: "", tipo: "", status: "", ini: "", fim: "" },
  serieMetrica: "matriculas",
  serieQuebra: "eps",
  serieAcumulada: false,
  tabBase: "leads",
  tabClasse: ""
};

const APU_EPS = {
  VOXA: { nome: "VOXA", cor: "var(--apu-voxa)", hex: "#6B21C8" },
  LUMEN: { nome: "Lumen", cor: "var(--apu-action)", hex: "#1F7A8C" },
  PRISMA: { nome: "Prisma", cor: "var(--apu-prisma)", hex: "#5F5D68" }
};

const APU_PRODUTO = {
  GRADUACAO: "Graduação",
  POS_GRADUACAO: "Pós-Graduação",
  TECNICO: "Técnico",
  PROFISSIONALIZANTES: "Profissionalizantes"
};

const APU_TIPO = { COMERCIAL: "Ação comercial", INCENTIVO: "Incentivo" };

/* Ordem e cor das classificacoes de tabulacao. */
const APU_CLASSES = [
  ["VENDA", "Venda", "#17694A"],
  ["RETORNO", "Retorno / agendamento", "#9B6BDB"],
  ["RECUSA", "Recusa", "#A32B2B"],
  ["SEM_CONTATO", "Sem contato", "#8C8A94"],
  ["CONTATO_INVALIDO", "Contato inválido", "#C9C6CE"],
  ["NAO_TRABALHADO", "Não trabalhado", "#E3E0DC"],
  ["OUTROS", "Outros", "#5F5D68"]
];

const APU_CORES_CAMPANHA = ["#6B21C8", "#1F7A8C", "#8A5A00", "#17694A", "#A32B2B", "#5F5D68", "#9B6BDB", "#3D6FB6"];


/* ---------------- formatacao ---------------- */

const apuInt = v => (v === null || v === undefined || isNaN(v))
  ? "—"
  : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 });

const apuPct = (v, casas = 1) => (v === null || v === undefined || !isFinite(v))
  ? "—"
  : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + "%";

const apuDiv = (a, b) => (b ? (a / b) * 100 : null);

function apuData(txt) {
  if (!txt) return "—";
  const d = new Date(String(txt).length <= 10 ? txt + "T12:00:00" : txt);
  return isNaN(d) ? "—" : d.toLocaleDateString("pt-BR");
}

function apuDataHora(txt) {
  if (!txt) return "—";
  const d = new Date(txt);
  return isNaN(d) ? "—" : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const apuDia = txt => String(txt || "").slice(0, 10);
const apuNomeEps = c => (APU_EPS[c] ? APU_EPS[c].nome : c);
const apuCorEps = c => (APU_EPS[c] ? APU_EPS[c].hex : "#5F5D68");
const apuClasse = c => APU_CLASSES.find(item => item[0] === c) || [c, c, "#5F5D68"];


/* ---------------- dados ---------------- */

async function carregarApuracao(forcar = false) {
  if (APU.dados && !forcar) return;

  try {
    APU.dados = await api("/api/internal/apuracao/dashboard");
    APU.erro = null;
  } catch (e) {
    APU.erro = e.message || "Não foi possível carregar a apuração.";
    APU.dados = { funil: [], serie_diaria: [], tabulacao: [], pendencias: [] };
  }
}

function apuFiltrar() {
  const d = APU.dados || {};
  const f = APU.f;

  const funil = (d.funil || []).filter(r => {
    if (f.campanha && r.codigo_campanha !== f.campanha) return false;
    if (f.eps && r.eps !== f.eps) return false;
    if (f.produto && r.produto !== f.produto) return false;
    if (f.tipo && r.tipo_acao !== f.tipo) return false;
    if (f.status && r.status_apuracao !== f.status) return false;
    if (f.ini && apuDia(r.periodo_fim) < f.ini) return false;
    if (f.fim && apuDia(r.periodo_ini) > f.fim) return false;
    return true;
  });

  const chaves = new Set(funil.map(r => r.codigo_campanha + "|" + r.eps));
  const dentro = r => chaves.has(r.codigo_campanha + "|" + r.eps);

  const serie = (d.serie_diaria || []).filter(r => {
    if (!dentro(r)) return false;
    const dia = apuDia(r.dia);
    if (f.ini && dia < f.ini) return false;
    if (f.fim && dia > f.fim) return false;
    return true;
  });

  return { funil, serie, tabulacao: (d.tabulacao || []).filter(dentro) };
}

function apuSomar(linhas) {
  const campos = ["mailing", "mailing_enviado", "leads_acionados", "tentativas", "trabalhados", "alo", "efetivos", "vendas", "matriculas", "alunos", "leads_reacionados"];
  const total = {};
  const informado = {};

  campos.forEach(c => { total[c] = 0; informado[c] = false; });

  linhas.forEach(r => campos.forEach(c => {
    if (r[c] !== null && r[c] !== undefined) {
      total[c] += Number(r[c]) || 0;
      informado[c] = true;
    }
  }));

  campos.forEach(c => { if (!informado[c]) total[c] = null; });

  let meta = 0;
  let realizado = 0;
  linhas.forEach(r => {
    if (r.meta_eps && r.meta_base) {
      meta += Number(r.meta_eps);
      realizado += Number(r.meta_base === "VENDAS" ? r.vendas : r.matriculas) || 0;
    }
  });

  total.meta = meta || null;
  total.realizado_meta = meta ? realizado : null;
  total.atingimento = meta ? (realizado / meta) * 100 : null;
  return total;
}

/* Tentativas por CPF: soma as faixas (1, 2, 3, 4-5, 6-10, 11+)
   de cada campanha x EPS. So existe onde o funil e lead a lead
   (Graduacao e Tecnico, pelo Databricks).                     */
const APU_FAIXAS = ["1", "2", "3", "4-5", "6-10", "11+"];

function apuFaixas(funil) {
  const total = {};
  let tem = false;
  funil.forEach(r => {
    let f = r.faixas_tentativas;
    if (typeof f === "string") { try { f = JSON.parse(f); } catch { f = null; } }
    if (!f) return;
    tem = true;
    Object.entries(f).forEach(([k, v]) => { total[k] = (total[k] || 0) + (Number(v) || 0); });
  });
  return tem ? total : null;
}

/* Esteira: matriculas que chegam depois do fechamento da
   campanha (data da matricula > periodo_fim). Entram no total,
   mas ficam visiveis a parte.                                */
function apuEsteira(funil, serie) {
  const fim = {};
  funil.forEach(r => { fim[r.codigo_campanha + "|" + r.eps] = apuDia(r.periodo_fim); });
  const porChave = {};
  let total = 0;
  serie.forEach(r => {
    const k = r.codigo_campanha + "|" + r.eps;
    if (fim[k] && apuDia(r.dia) > fim[k]) {
      const v = Number(r.matriculas) || 0;
      porChave[k] = (porChave[k] || 0) + v;
      total += v;
    }
  });
  return { total, porChave };
}

function apuPorEps(funil) {
  const grupos = {};
  funil.forEach(r => { (grupos[r.eps] = grupos[r.eps] || []).push(r); });
  return Object.keys(grupos).sort().map(eps => ({ eps, ...apuSomar(grupos[eps]) }));
}


/* ---------------- tela ---------------- */

function apuracaoConteudo() {
  return `<div id="apu-root" class="apu">${apuracaoMiolo()}</div>`;
}

function apuracaoMiolo() {
  const d = APU.dados || {};
  const todos = d.funil || [];

  if (APU.erro) {
    return `${apuCabecalho(d)}<div class="notice error">${esc(APU.erro)}</div>`;
  }

  if (!todos.length) {
    return `
      ${apuCabecalho(d)}
      <div class="apu-vazio">
        <h2>Nenhuma campanha apurada ainda</h2>
        <p>O robô apura todo dia, de forma parcial, cada campanha em que a EPS já está operando, assim que a base do Databricks chega em D-1. A apuração fecha quando a EPS finaliza (ação comercial) ou quando o prazo termina (incentivo).</p>
      </div>
      ${(d.pendencias || []).length ? `<div class="apu-grade" style="margin-top:18px">${apuPendencias(d.pendencias)}</div>` : ""}
    `;
  }

  const { funil, serie, tabulacao } = apuFiltrar();

  /* Conversoes so com quem tem funil: somar matriculas de uma
     EPS sem painel (ex.: Prisma) com leads de outra inflaria
     a taxa. O total de matriculas continua somando todas.    */
  const temFunil = r => r.trabalhados !== null && r.trabalhados !== undefined;
  const total = apuSomar(funil);
  const comFunil = funil.filter(temFunil);
  const totalFunil = apuSomar(comFunil);

  /* Uma etapa so entra no funil se TODAS as campanhas x EPS com
     funil tiverem o dado. Evita somar parte do recorte numa etapa
     e o recorte inteiro na outra (ex.: atendidos so de Pos).    */
  ["mailing", "trabalhados", "alo", "efetivos", "vendas", "tentativas"].forEach(c => {
    if (comFunil.some(r => r[c] === null || r[c] === undefined)) totalFunil[c] = null;
  });
  const semFunil = apuPorEps(funil.filter(r => !temFunil(r)));
  const porEps = apuPorEps(funil);
  const esteira = apuEsteira(funil, serie);
  const faixas = apuFaixas(funil.filter(temFunil));
  APU._esteira = esteira;

  return `
    ${apuCabecalho(d)}
    ${apuFiltros(todos)}
    ${funil.length ? `
      ${apuKpis(total, totalFunil, funil, esteira, semFunil)}
      <div class="apu-grade">
        <section class="apu-painel apu-col-7">${apuFunil(totalFunil, semFunil, faixas, total)}</section>
        <section class="apu-painel apu-col-5">${apuFunilPorEps(comFunil, totalFunil, semFunil, total)}</section>
      </div>
      <div class="apu-grade">
        <section class="apu-painel apu-col-12">${apuLeituras(total, porEps, funil, serie, tabulacao, semFunil, esteira, totalFunil, faixas)}</section>
      </div>
      <div class="apu-grade">
        <section class="apu-painel apu-col-12">${apuSerieDiaria(serie, funil)}</section>
      </div>
      <div class="apu-grade">
        <section class="apu-painel apu-col-12">${apuTabulacoes(tabulacao)}</section>
      </div>
      <div class="apu-grade">
        <section class="apu-painel apu-col-7">${apuMensal(serie)}</section>
        <section class="apu-painel apu-col-5">${apuAtingimento(porEps, total)}</section>
      </div>
      <div class="apu-grade">
        <section class="apu-painel apu-col-12">${apuTabela(funil, esteira)}</section>
      </div>
    ` : `<div class="apu-vazio"><h2>Nenhuma apuração com esses filtros</h2><p>Limpe os filtros ou amplie o período.</p></div>`}
    ${(d.pendencias || []).length ? `<div class="apu-grade">${apuPendencias(d.pendencias)}</div>` : ""}
  `;
}

function apuCabecalho(d) {
  const ult = d.ultima_execucao;
  const bases = (d.funil || []).map(r => apuDia(r.dt_base)).filter(Boolean).sort();
  const base = bases.length ? bases[bases.length - 1] : null;

  return `
    <div class="apu-cabecalho">
      <div>
        <h1>Apuração de campanhas</h1>
        <p>Funil, matrículas e tabulações de cada campanha, apurados pelo robô a partir do Databricks e dos painéis das EPS.</p>
      </div>
      <div class="apu-atualizacao">
        <span>Robô rodou em <strong>${apuDataHora(ult && ult.dt_execucao)}</strong>${base ? ` · base de <strong>${apuData(base)}</strong>` : ""}</span>
        <button class="apu-btn" data-apu="recarregar">Atualizar</button>
      </div>
    </div>
  `;
}

function apuFiltros(todos) {
  const f = APU.f;
  const campanhas = {};
  todos.forEach(r => { campanhas[r.codigo_campanha] = r.nome_campanha || ""; });
  const produtos = [...new Set(todos.map(r => r.produto).filter(Boolean))];
  const tipos = [...new Set(todos.map(r => r.tipo_acao).filter(Boolean))];
  const eps = [...new Set(todos.map(r => r.eps))].sort();

  const opcao = (valor, rotulo, atual) =>
    `<option value="${esc(valor)}" ${valor === atual ? "selected" : ""}>${esc(rotulo)}</option>`;

  return `
    <div class="apu-filtros">
      <div>
        <label for="apuCampanha">Campanha</label>
        <select id="apuCampanha" data-apu-filtro="campanha">
          ${opcao("", "Todas as campanhas", f.campanha)}
          ${Object.keys(campanhas).sort().reverse().map(c => opcao(c, `${c} · ${campanhas[c]}`, f.campanha)).join("")}
        </select>
      </div>
      <div>
        <label for="apuProduto">Produto</label>
        <select id="apuProduto" data-apu-filtro="produto">
          ${opcao("", "Todos", f.produto)}
          ${produtos.map(p => opcao(p, APU_PRODUTO[p] || p, f.produto)).join("")}
        </select>
      </div>
      <div>
        <label for="apuTipo">Tipo</label>
        <select id="apuTipo" data-apu-filtro="tipo">
          ${opcao("", "Todos", f.tipo)}
          ${tipos.map(t => opcao(t, APU_TIPO[t] || t, f.tipo)).join("")}
        </select>
      </div>
      <div>
        <label for="apuStatus">Status</label>
        <select id="apuStatus" data-apu-filtro="status">
          ${opcao("", "Todos", f.status)}
          ${opcao("FINAL", "Apurada", f.status)}
          ${opcao("PARCIAL", "Parcial (em andamento)", f.status)}
        </select>
      </div>
      <div>
        <label for="apuIni">De</label>
        <input id="apuIni" type="date" value="${esc(f.ini)}" data-apu-filtro="ini">
      </div>
      <div>
        <label for="apuFim">Até</label>
        <input id="apuFim" type="date" value="${esc(f.fim)}" data-apu-filtro="fim">
      </div>
      <button class="apu-btn" data-apu="limpar">Limpar</button>
    </div>
    <div class="apu-eps-chips">
      <button class="apu-chip ${f.eps ? "" : "ativo"}" data-apu-eps="">Todas as EPS</button>
      ${eps.map(e => `
        <button class="apu-chip ${f.eps === e ? "ativo" : ""}" data-apu-eps="${esc(e)}">
          <i style="background:${apuCorEps(e)}"></i>${esc(apuNomeEps(e))}
        </button>`).join("")}
    </div>
  `;
}

function apuAnel(pct, tamanho = 64) {
  const r = (tamanho - 8) / 2;
  const c = 2 * Math.PI * r;
  const valor = Math.max(0, Math.min(pct || 0, 100));
  const cor = pct >= 100 ? "var(--c-ok)" : pct >= 70 ? "var(--c-accent)" : pct >= 40 ? "var(--c-wait)" : "var(--c-stop)";

  return `
    <svg width="${tamanho}" height="${tamanho}" viewBox="0 0 ${tamanho} ${tamanho}" aria-hidden="true">
      <circle cx="${tamanho / 2}" cy="${tamanho / 2}" r="${r}" fill="none" stroke="var(--c-rule-soft)" stroke-width="8"/>
      <circle cx="${tamanho / 2}" cy="${tamanho / 2}" r="${r}" fill="none" stroke="${cor}" stroke-width="8"
        stroke-linecap="round" stroke-dasharray="${(c * valor) / 100} ${c}"
        transform="rotate(-90 ${tamanho / 2} ${tamanho / 2})"/>
    </svg>
  `;
}

function apuKpis(t, tf, funil, esteira = { total: 0 }, semFunil = []) {
  /* Quadros na ordem do funil padrao do time. Cada etapa traz
     o volume e, embaixo, o(s) indicador(es) que pertencem a ela.
     Taxas sempre sobre o recorte com funil (tf); o total de
     matriculas soma todas as EPS (t), como antes.              */
  const parciais = funil.filter(r => r.status_apuracao === "PARCIAL").length;
  const campanhas = new Set(funil.map(r => r.codigo_campanha)).size;
  const spin = tf.tentativas && tf.trabalhados
    ? (tf.tentativas / tf.trabalhados).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    : "—";

  const ind = (valor, nome, formula) =>
    `<p class="apu-kpi-ind" title="${esc(formula)}"><b>${valor}</b> ${esc(nome)}</p>`;
  const nota = texto => `<small>${texto}</small>`;
  const quadro = (rotulo, valor, miolo) => `
      <div class="apu-kpi">
        <span>${rotulo}</span>
        <strong>${valor}</strong>
        ${miolo}
      </div>`;

  /* O quadro de Matriculas e o RESULTADO REAL: todas as EPS, inclusive
     as que nao tem funil (ex.: Prisma na Pos). O funil abaixo soma so
     as EPS com funil; a diferenca fica explicada aqui.              */
  const foraFunil = semFunil.filter(e => e.matriculas > 0);
  const epsFunil = [...new Set(funil.filter(r => r.trabalhados !== null && r.trabalhados !== undefined).map(r => apuNomeEps(r.eps)))];
  const partes = [];
  if (foraFunil.length) {
    partes.push(`<b>Resultado real</b> · funil (${esc(epsFunil.join(" + ") || "—")}): ${apuInt(tf.matriculas)} · ${foraFunil.map(e => `${esc(apuNomeEps(e.eps))}: ${apuInt(e.matriculas)}`).join(" · ")}`);
  }
  if (esteira.total) {
    partes.push(`${apuInt((t.matriculas || 0) - esteira.total)} no período · ${apuInt(esteira.total)} na esteira`);
  }
  if (!partes.length) {
    partes.push(`${campanhas} campanha${campanhas === 1 ? "" : "s"}${parciais ? ` · ${parciais} parcial${parciais === 1 ? "" : "is"}` : ""}`);
  }
  const notaMat = partes.join("<br>");

  const meta = t.meta ? `
      <div class="apu-kpi apu-kpi-meta">
        ${apuAnel(t.atingimento)}
        <div>
          <span>Atingimento da meta</span>
          <strong>${apuPct(t.atingimento, 0)}</strong>
          <small>${apuInt(t.realizado_meta)} de ${apuInt(t.meta)}${foraFunil.length ? " · todas as EPS" : ""}</small>
        </div>
      </div>` : "";

  return `
    <div class="apu-kpis ${t.meta ? "com-meta" : ""}">
      ${meta}
      ${quadro("Mailing", apuInt(tf.mailing),
        nota(t.mailing_enviado ? "mailing enviado à EPS (Databricks)" : "inscrições na base da operação"))}
      ${quadro("Trabalhados", apuInt(tf.trabalhados),
        ind(apuPct(apuDiv(tf.trabalhados, tf.mailing)), "% Trab", "trabalhados ÷ mailing"))}
      ${quadro("Tentativas", apuInt(tf.tentativas),
        ind(spin, "Spin", "tentativas ÷ trabalhados"))}
      ${quadro("Atendidos", apuInt(tf.alo),
        ind(apuPct(apuDiv(tf.alo, tf.tentativas)), "Hitrate", "atendidos ÷ tentativas") +
        ind(apuPct(apuDiv(tf.alo, tf.mailing)), "% Atendido/Base", "atendidos ÷ mailing"))}
      ${quadro("Efetivos", apuInt(tf.efetivos),
        ind(apuPct(apuDiv(tf.efetivos, tf.mailing)), "% Efetivo/Base", "efetivos ÷ mailing"))}
      ${quadro("Vendas", apuInt(tf.vendas),
        ind(apuPct(apuDiv(tf.vendas, tf.efetivos)), "% Conv Venda", "vendas ÷ efetivos"))}
      ${quadro("Matrículas", apuInt(t.matriculas),
        ind(apuPct(apuDiv(tf.matriculas, tf.vendas)), "% Conv Mat", "matrículas ÷ vendas") +
        ind(apuPct(apuDiv(tf.matriculas, tf.mailing)), "% Ret", "matrículas ÷ mailing") +
        nota(notaMat))}
    </div>
  `;
}


/* ---------- indicadores do funil (padrao do time) ---------- */

function apuIndicadores(t) {
  const ind = [
    ["Spin", t.tentativas && t.trabalhados ? (t.tentativas / t.trabalhados).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "—", "tentativas ÷ trabalhados"],
    ["% Trab", apuPct(apuDiv(t.trabalhados, t.mailing)), "trabalhados ÷ mailing"],
    ["Hitrate", apuPct(apuDiv(t.alo, t.tentativas)), "atendidos ÷ tentativas"],
    ["% Atendido/Base", apuPct(apuDiv(t.alo, t.mailing)), "atendidos ÷ mailing"],
    ["% Efetivo/Base", apuPct(apuDiv(t.efetivos, t.mailing)), "efetivos ÷ mailing"],
    ["% Conv Venda", apuPct(apuDiv(t.vendas, t.efetivos)), "vendas ÷ efetivos"],
    ["% Ret", apuPct(apuDiv(t.matriculas, t.mailing)), "matrículas ÷ mailing"],
    ["% Conv Mat", apuPct(apuDiv(t.matriculas, t.vendas)), "matrículas ÷ vendas"]
  ];
  return `
    <div class="apu-indicadores">
      ${ind.map(i => `<div class="apu-ind"><span>${i[0]}</span><strong>${i[1]}</strong><small>${i[2]}</small></div>`).join("")}
    </div>`;
}


/* ---------- funil: a peca de destaque ---------- */

/* Aviso quando ha EPS sem funil com matricula (ex.: Prisma na Pos):
   o funil soma so as EPS com funil; o resultado real esta no quadro. */
function apuAvisoForaFunil(tf, semFunil = [], total = null) {
  const fora = semFunil.filter(e => e.matriculas > 0);
  if (!fora.length || !total) return "";
  return `
    <div class="apu-aviso-funil">
      <b>Matrículas do funil: só as EPS com funil (${apuInt(tf.matriculas)}).</b>
      ${fora.map(e => `${esc(apuNomeEps(e.eps))} não tem funil e soma ${apuInt(e.matriculas)}`).join("; ")}.
      Resultado real da campanha: <b>${apuInt(total.matriculas)} matrículas</b>, no quadro acima.
    </div>`;
}

function apuFunil(t, semFunil = [], faixas = null, total = null) {
  /* Mesma ordem do funil padrao do time. Tentativas e volume
     (ligacoes), nao pessoas: aparece como faixa propria, sem
     quebrar o afunilamento. Cada indicador fica ao lado da
     etapa a que pertence.                                     */
  const fmtSpin = v => (v === null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
  const spin = t.tentativas && t.trabalhados ? t.tentativas / t.trabalhados : null;
  const etapas = [
    { nome: "Mailing", v: t.mailing, ind: [["Topo do funil", ""]] },
    { nome: "Trabalhados", v: t.trabalhados, ind: [["% Trab", apuPct(apuDiv(t.trabalhados, t.mailing))]] },
    { nome: "Tentativas", v: t.tentativas, volume: true, ind: [["Spin", fmtSpin(spin)]] },
    { nome: "Atendidos", v: t.alo, ind: [["Hitrate", apuPct(apuDiv(t.alo, t.tentativas))], ["% Atendido/Base", apuPct(apuDiv(t.alo, t.mailing))]] },
    { nome: "Efetivos", v: t.efetivos, ind: [["% Efetivo/Base", apuPct(apuDiv(t.efetivos, t.mailing))]] },
    { nome: "Vendas", v: t.vendas, ind: [["% Conv Venda", apuPct(apuDiv(t.vendas, t.efetivos))]] },
    { nome: "Matrículas", v: t.matriculas, ind: [["% Conv Mat", apuPct(apuDiv(t.matriculas, t.vendas))], ["% Ret", apuPct(apuDiv(t.matriculas, t.mailing))]] }
  ].filter(e => e.v !== null && e.v !== undefined);

  const semFunilComMat = semFunil.filter(e => e.matriculas > 0);
  if (!etapas.length || t.trabalhados === null || t.trabalhados === undefined) {
    return `<div class="apu-painel-topo"><div><h2>Funil da campanha</h2></div></div>
      <div class="apu-sem-dado">Sem funil operacional neste recorte${semFunilComMat.length ? `: só matrículas (${semFunilComMat.map(e => `${esc(apuNomeEps(e.eps))} ${apuInt(e.matriculas)}`).join(", ")})` : ""}.</div>`;
  }

  const W = 680, H = 50, GAP = 6, X0 = 112, LARG = 300, XT = X0 + LARG + 24;
  const pessoas = etapas.filter(e => !e.volume);
  const nP = pessoas.length;
  const larguraP = i => LARG * (1 - (nP > 1 ? (i / (nP - 1)) * 0.58 : 0));
  const cinzas = ["#2B2A31", "#36343D", "#423F4A", "#4E4A58", "#5A5566", "#665F74"];
  const cx = X0 + LARG / 2;

  let iP = 0;
  const blocos = etapas.map((e, i) => {
    const y = i * (H + GAP);
    const indic = e.ind.map((par, k) => par[1]
      ? `<text class="${k === 0 ? "etapa-taxa-forte" : "etapa-taxa"}" x="${XT}" y="${y + (e.ind.length > 1 ? (k === 0 ? H / 2 - 2 : H / 2 + 15) : H / 2 + 5)}">${esc(par[0])} ${par[1]}</text>`
      : `<text class="etapa-taxa" x="${XT}" y="${y + H / 2 + 5}">${esc(par[0])}</text>`).join("");

    if (e.volume) {
      const w = larguraP(Math.max(iP - 1, 0)) * 0.94;
      return `
        <g>
          <text class="etapa-nome" x="0" y="${y + H / 2 + 5}">${esc(e.nome)}</text>
          <rect x="${cx - w / 2}" y="${y + 4}" width="${w}" height="${H - 8}" rx="8" fill="var(--c-surface)" stroke="#4E4A58" stroke-width="1.5" stroke-dasharray="5 4"/>
          <text class="etapa-valor fora" x="${cx}" y="${y + H / 2 + 6}" text-anchor="middle">${apuInt(e.v)}</text>
          ${indic}
        </g>`;
    }

    const w1 = larguraP(iP);
    const w2 = iP < nP - 1 ? larguraP(iP + 1) : w1 * 0.9;
    const ultima = iP === nP - 1;
    const cor = ultima ? "#6B21C8" : cinzas[Math.min(iP, cinzas.length - 1)];
    const pontos = `${cx - w1 / 2},${y} ${cx + w1 / 2},${y} ${cx + w2 / 2},${y + H} ${cx - w2 / 2},${y + H}`;
    iP += 1;
    return `
      <g>
        <text class="etapa-nome" x="0" y="${y + H / 2 + 5}">${esc(e.nome)}</text>
        <polygon class="seg" style="animation-delay:${i * 60}ms" points="${pontos}" fill="${cor}"/>
        <text class="etapa-valor" x="${cx}" y="${y + H / 2 + 6}" text-anchor="middle">${apuInt(e.v)}</text>
        ${indic}
      </g>`;
  }).join("");

  const altura = etapas.length * (H + GAP);

  return `
    <div class="apu-painel-topo">
      <div>
        <h2>Funil da campanha</h2>
        <p>Etapas e indicadores no padrão do time, somando as EPS do recorte</p>
      </div>
    </div>
    ${apuAvisoForaFunil(t, semFunil, total)}
    <div class="apu-funil">
      <svg viewBox="0 0 ${W} ${altura}" role="img" aria-label="Funil de apuração">${blocos}</svg>
    </div>
    ${apuBlocoTentativas(t, faixas)}
  `;
}


/* ---------- funil padrao por EPS (mesmo formato do relatorio do time) ---------- */

function apuFunilPorEps(comFunil, tf, semFunil = [], total = null) {
  const grupos = {};
  comFunil.forEach(r => { (grupos[r.eps] = grupos[r.eps] || []).push(r); });
  const eps = Object.keys(grupos).sort();
  const colunas = eps.map(e => ({ nome: apuNomeEps(e), t: apuSomar(grupos[e]) }));
  if (eps.length > 1) colunas.push({ nome: "Total", t: tf, total: true });

  const spin = t => (t.tentativas && t.trabalhados ? (t.tentativas / t.trabalhados).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "—");
  const linhas = [
    ["MAILING", t => apuInt(t.mailing)],
    ["TRABALHADOS", t => apuInt(t.trabalhados)],
    ["TENTATIVAS", t => apuInt(t.tentativas)],
    ["ATENDIDOS", t => apuInt(t.alo)],
    ["EFETIVOS", t => apuInt(t.efetivos)],
    ["VENDAS", t => apuInt(t.vendas)],
    ["MATRÍCULAS", t => apuInt(t.matriculas)],
    ["SPIN", spin, true],
    ["% TRAB", t => apuPct(apuDiv(t.trabalhados, t.mailing)), true],
    ["HITRATE", t => apuPct(apuDiv(t.alo, t.tentativas)), true],
    ["% ATENDIDO/BASE", t => apuPct(apuDiv(t.alo, t.mailing)), true],
    ["% EFETIVO/BASE", t => apuPct(apuDiv(t.efetivos, t.mailing)), true],
    ["% CONV VENDA", t => apuPct(apuDiv(t.vendas, t.efetivos)), true],
    ["% RET", t => apuPct(apuDiv(t.matriculas, t.mailing)), true],
    ["% CONV MAT", t => apuPct(apuDiv(t.matriculas, t.vendas)), true]
  ];

  if (!colunas.length) return `<h2>Funil por EPS</h2><div class="apu-sem-dado">Sem funil operacional neste recorte.</div>`;

  return `
    <div class="apu-painel-topo">
      <div>
        <h2>Funil por EPS</h2>
        <p>Mesmo formato do relatório de funil do time</p>
      </div>
    </div>
    ${apuAvisoForaFunil(tf, semFunil, total)}
    <div class="apu-tabela-wrap">
      <table class="apu-padrao">
        <thead><tr><th>FUNIL</th>${colunas.map(c => `<th class="${c.total ? "total" : ""}">${esc(c.nome)}</th>`).join("")}</tr></thead>
        <tbody>
          ${linhas.map(l => `<tr class="${l[2] ? "ind" : ""}"><td>${l[0]}</td>${colunas.map(c => `<td class="${c.total ? "total" : ""}">${l[1](c.t)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}


function apuBlocoTentativas(t, faixas) {
  if (!t.tentativas) return "";
  const media = t.tentativas / (t.trabalhados || t.mailing || 1);
  const cabecalho = `
    <div class="apu-tent-topo">
      <h3>Tentativas por inscrição</h3>
      <span><b>${apuInt(t.tentativas)}</b> tentativas · <b>${media.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</b> de spin${t.leads_reacionados !== null && t.mailing ? ` · <b>${apuInt(t.leads_reacionados)}</b> inscrições tentadas 2+ vezes (${apuPct(apuDiv(t.leads_reacionados, t.mailing), 0)})` : ""}</span>
    </div>`;
  if (!faixas) {
    return `<div class="apu-tent">${cabecalho}<p class="apu-funil-nota">Distribuição por CPF disponível só onde o funil é lead a lead (Graduação e Técnico).</p></div>`;
  }
  const tot = APU_FAIXAS.reduce((a, k) => a + (faixas[k] || 0), 0) || 1;
  const tons = ["#D9D3E8", "#B9A8DA", "#9677CB", "#7A4FC2", "#5E2BB0", "#3F1680"];
  return `
    <div class="apu-tent">
      ${cabecalho}
      <div class="apu-tent-barra">
        ${APU_FAIXAS.map((k, i) => {
          const v = faixas[k] || 0;
          if (!v) return "";
          const pct = (v / tot) * 100;
          return `<i style="width:${pct}%;background:${tons[i]};color:${i < 2 ? "var(--c-ink)" : "#fff"}" title="${k} tentativa(s): ${apuInt(v)} leads (${apuPct(pct)})">${pct >= 7 ? `${k}×` : ""}</i>`;
        }).join("")}
      </div>
      <div class="apu-legenda">
        ${APU_FAIXAS.map((k, i) => faixas[k] ? `<span><i style="background:${tons[i]}"></i>${k}× · ${apuInt(faixas[k])} (${apuPct(apuDiv(faixas[k], tot), 0)})</span>` : "").join("")}
      </div>
    </div>`;
}


/* ---------- leituras automaticas ---------- */

function apuLeituras(t, porEps, funil, serie, tabulacao, semFunil = [], esteira = { total: 0 }, tf = null, faixas = null) {
  const itens = [];

  if (t.meta) {
    const falta = Math.max(t.meta - (t.realizado_meta || 0), 0);
    itens.push([
      t.atingimento >= 100 ? "bom" : t.atingimento >= 70 ? "destaque" : "critico",
      t.atingimento >= 100
        ? `Meta batida: <b>${apuPct(t.atingimento, 0)}</b> (${apuInt(t.realizado_meta)} de ${apuInt(t.meta)}).`
        : `Atingimento de <b>${apuPct(t.atingimento, 0)}</b>: faltam <b>${apuInt(falta)}</b> para a meta de ${apuInt(t.meta)}.`
    ]);
  }

  const comLead = porEps.filter(e => e.mailing > 0 && e.trabalhados !== null && e.matriculas !== null);
  if (semFunil.length) {
    itens.push(["neutro", `${semFunil.map(e => `<b>${esc(apuNomeEps(e.eps))}</b>`).join(" e ")} sem funil operacional (sem painel): só matrícula apurada, fora das taxas de conversão.`]);
  }
  if (comLead.length > 1) {
    const ord = [...comLead].sort((a, b) => apuDiv(b.matriculas, b.mailing) - apuDiv(a.matriculas, a.mailing));
    const m = ord[0], p = ord[ord.length - 1];
    itens.push(["destaque",
      `% Ret: <b>${esc(apuNomeEps(m.eps))}</b> ${apuPct(apuDiv(m.matriculas, m.mailing))} · <b>${esc(apuNomeEps(p.eps))}</b> ${apuPct(apuDiv(p.matriculas, p.mailing))} (matrículas ÷ mailing).`]);
  }

  const comVenda = porEps.filter(e => e.vendas > 0 && e.matriculas !== null);
  if (comVenda.length > 1) {
    const ord = [...comVenda].sort((a, b) => a.matriculas / a.vendas - b.matriculas / b.vendas);
    const p = ord[0], m = ord[ord.length - 1];
    const rp = p.matriculas / p.vendas, rm = m.matriculas / m.vendas;
    if (rm > 0 && rm / Math.max(rp, 0.0001) >= 1.8) {
      itens.push(["atencao",
        `Só <b>${apuPct(rp * 100, 0)}</b> das vendas da ${esc(apuNomeEps(p.eps))} viraram matrícula, contra <b>${apuPct(rm * 100, 0)}</b> na ${esc(apuNomeEps(m.eps))}. O "aceitou oferta" não tem o mesmo critério nas duas.`]);
    }
  } else if (t.vendas > 0 && t.matriculas !== null) {
    itens.push(["neutro", `${apuPct(apuDiv(t.matriculas, t.vendas), 0)} das vendas declaradas viraram matrícula.`]);
  }

  if (tf && tf.mailing > 0 && tf.trabalhados !== null) {
    const cob = apuDiv(tf.trabalhados, tf.mailing);
    if (cob < 30) {
      itens.push(["critico", `Só <b>${apuPct(cob)}</b> do mailing foi trabalhado: ${apuInt(tf.mailing - tf.trabalhados)} inscrições ainda não foram tentadas.`]);
    } else if (cob >= 80) {
      itens.push(["bom", `Cobertura alta: <b>${apuPct(cob)}</b> do mailing foi trabalhado.`]);
    }
  }
  if (tf && tf.mailing) {
    const pctTrab = apuDiv(tf.trabalhados, tf.mailing), hit = apuDiv(tf.alo, tf.tentativas);
    if (pctTrab !== null && hit !== null) {
      itens.push(["neutro", `% Trab <b>${apuPct(pctTrab)}</b> · Hitrate <b>${apuPct(hit)}</b> · % Efetivo/Base <b>${apuPct(apuDiv(tf.efetivos, tf.mailing))}</b>.`]);
    }
  }

  const recusas = {};
  tabulacao.filter(r => r.classificacao === "RECUSA").forEach(r => {
    const nome = r.tabulacao_3 || r.tabulacao_2 || r.tabulacao_1 || "Sem detalhe";
    recusas[nome] = (recusas[nome] || 0) + (Number(r.leads) || Number(r.interacoes) || 0);
  });
  const totRec = Object.values(recusas).reduce((a, b) => a + b, 0);
  if (totRec) {
    const [nome, qtd] = Object.entries(recusas).sort((a, b) => b[1] - a[1])[0];
    itens.push(["atencao", `Principal motivo de recusa: <b>${esc(nome)}</b>, ${apuPct(apuDiv(qtd, totRec), 0)} das recusas.`]);
  }

  const porDia = {};
  serie.forEach(r => { const d = apuDia(r.dia); porDia[d] = (porDia[d] || 0) + (Number(r.matriculas) || 0); });
  const dias = Object.entries(porDia).sort((a, b) => b[1] - a[1]);
  if (dias.length > 2 && dias[0][1] > 0) {
    itens.push(["neutro", `Pico de matrículas em <b>${apuData(dias[0][0])}</b>, com ${apuInt(dias[0][1])} no dia.`]);
  }

  if (faixas && tf && tf.mailing) {
    const tot = Object.values(faixas).reduce((a, b) => a + b, 0) || 1;
    const muitas = (faixas["6-10"] || 0) + (faixas["11+"] || 0);
    const uma = faixas["1"] || 0;
    itens.push([muitas / tot >= 0.15 ? "atencao" : "neutro",
      `<b>${apuPct(apuDiv(tot - uma, tot), 0)}</b> dos leads foram tentados 2 vezes ou mais${muitas ? `; <b>${apuPct(apuDiv(muitas, tot), 0)}</b> passaram de 5 tentativas` : ""}.`]);
  }

  if (esteira.total) {
    itens.push(["destaque", `<b>${apuInt(esteira.total)}</b> matrícula${esteira.total === 1 ? "" : "s"} chegaram depois do fechamento (esteira), ${apuPct(apuDiv(esteira.total, t.matriculas), 0)} do total.`]);
  }

  const parciais = funil.filter(r => r.status_apuracao === "PARCIAL");
  if (parciais.length) {
    const janela = parciais.map(r => apuDia(r.janela_fim)).filter(Boolean).sort().pop();
    itens.push(["neutro", `${parciais.length} apuraç${parciais.length === 1 ? "ão" : "ões"} ainda em andamento: os números sobem a cada dia até a campanha fechar.`]);
  }

  return `
    <div class="apu-painel-topo">
      <div>
        <h2>Leituras do recorte</h2>
        <p>Geradas a partir dos números ao lado</p>
      </div>
    </div>
    ${itens.length
      ? `<ul class="apu-leituras">${itens.slice(0, 7).map(i => `<li class="${i[0]}"><span>${i[1]}</span></li>`).join("")}</ul>`
      : `<div class="apu-sem-dado">Ainda não há volume suficiente para leituras.</div>`}
  `;
}


/* ---------- curva diaria ---------- */

function apuSeriesDiarias(serie) {
  const metrica = APU.serieMetrica;
  const porSerie = {};
  const diasSet = new Set();

  serie.forEach(r => {
    const chave = APU.serieQuebra === "eps" ? r.eps : r.codigo_campanha;
    const dia = apuDia(r.dia);
    diasSet.add(dia);
    porSerie[chave] = porSerie[chave] || {};
    porSerie[chave][dia] = (porSerie[chave][dia] || 0) + (Number(r[metrica]) || 0);
  });

  const dias = [...diasSet].sort();
  const chaves = Object.keys(porSerie).sort();

  const series = chaves.map((chave, i) => {
    let acc = 0;
    const valores = dias.map(d => {
      const v = porSerie[chave][d] || 0;
      acc += v;
      return APU.serieAcumulada ? acc : v;
    });
    const cor = APU.serieQuebra === "eps" ? apuCorEps(chave) : APU_CORES_CAMPANHA[i % APU_CORES_CAMPANHA.length];
    return { chave, nome: APU.serieQuebra === "eps" ? apuNomeEps(chave) : chave, cor, valores };
  });

  return { dias, series };
}

function apuSerieDiaria(serie, funil = []) {
  const rotulos = { matriculas: "Matrículas", vendas: "Vendas", tentativas: "Tentativas" };
  const alternar = (grupo, valor, rotulo, atual) =>
    `<button class="${valor === atual ? "ativo" : ""}" data-apu-${grupo}="${valor}">${rotulo}</button>`;

  const topo = `
    <div class="apu-painel-topo">
      <div>
        <h2>${rotulos[APU.serieMetrica]} dia a dia</h2>
        <p>${APU.serieAcumulada ? "Acumulado no período" : "Volume diário"}, por ${APU.serieQuebra === "eps" ? "EPS" : "campanha"}</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
        <div class="apu-alternar">
          ${alternar("metrica", "matriculas", "Matrículas", APU.serieMetrica)}
          ${alternar("metrica", "vendas", "Vendas", APU.serieMetrica)}
          ${alternar("metrica", "tentativas", "Tentativas", APU.serieMetrica)}
        </div>
        <div class="apu-alternar">
          ${alternar("quebra", "eps", "Por EPS", APU.serieQuebra)}
          ${alternar("quebra", "campanha", "Por campanha", APU.serieQuebra)}
        </div>
        <div class="apu-alternar">
          <button class="${APU.serieAcumulada ? "" : "ativo"}" data-apu-acumulado="0">Diário</button>
          <button class="${APU.serieAcumulada ? "ativo" : ""}" data-apu-acumulado="1">Acumulado</button>
        </div>
      </div>
    </div>`;

  const { dias, series } = apuSeriesDiarias(serie);
  if (!dias.length) return topo + `<div class="apu-sem-dado">Sem série diária para este recorte.</div>`;

  const W = 1100, H = 280, M = { t: 14, r: 16, b: 30, l: 46 };
  const max = Math.max(1, ...series.flatMap(s => s.valores));
  const passo = apuEscala(max);
  const topoY = Math.ceil(max / passo) * passo;
  const x = i => M.l + (dias.length === 1 ? (W - M.l - M.r) / 2 : (i * (W - M.l - M.r)) / (dias.length - 1));
  const y = v => H - M.b - (v / topoY) * (H - M.t - M.b);

  let grade = "";
  for (let v = 0; v <= topoY; v += passo) {
    grade += `<line class="grade" x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/>
              <text class="eixo" x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${apuInt(v)}</text>`;
  }

  const salto = Math.max(1, Math.ceil(dias.length / 12));
  const eixoX = dias.map((d, i) => (i % salto === 0 || i === dias.length - 1)
    ? `<text class="eixo" x="${x(i)}" y="${H - 8}" text-anchor="middle">${d.slice(8, 10)}/${d.slice(5, 7)}</text>` : "").join("");

  const linhas = series.map(s => {
    const pts = s.valores.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    const area = APU.serieAcumulada || series.length > 1 ? "" :
      `<polygon points="${x(0)},${y(0)} ${pts} ${x(dias.length - 1)},${y(0)}" fill="${s.cor}" opacity=".08"/>`;
    const pontos = dias.length <= 31 ? s.valores.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="2.6" fill="${s.cor}"/>`).join("") : "";
    return `${area}<polyline points="${pts}" fill="none" stroke="${s.cor}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>${pontos}`;
  }).join("");

  APU._serieAtual = { dias, series, W, M, x };

  const fins = [...new Set(funil.filter(r => r.status_apuracao === "FINAL").map(r => apuDia(r.periodo_fim)))];
  let fechamento = "";
  if (fins.length === 1 && APU.serieMetrica === "matriculas") {
    const idx = dias.findIndex(d => d > fins[0]);
    if (idx > 0) {
      const xf = (x(idx - 1) + x(idx)) / 2;
      fechamento = `
        <rect x="${xf}" y="${M.t}" width="${W - M.r - xf}" height="${H - M.t - M.b}" fill="var(--c-accent-soft)" opacity=".55"/>
        <line x1="${xf}" x2="${xf}" y1="${M.t}" y2="${H - M.b}" stroke="var(--c-accent)" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text class="eixo" x="${W - M.r - xf > 280 ? xf + 6 : xf - 6}" y="${M.t + 12}" text-anchor="${W - M.r - xf > 280 ? "start" : "end"}" style="fill:var(--c-accent);font-weight:600">${W - M.r - xf > 280 ? "Esteira após o fechamento" : "Fechamento"} (${apuData(fins[0])})${W - M.r - xf > 280 ? "" : " · esteira →"}</text>`;
    }
  }

  return `
    ${topo}
    <div class="apu-grafico" id="apuSerieBox">
      <svg id="apuSerieSvg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Curva diária">
        ${fechamento}${grade}${eixoX}${linhas}
        <line id="apuSerieGuia" class="guia" x1="0" x2="0" y1="${M.t}" y2="${H - M.b}" style="display:none"/>
        <rect x="${M.l}" y="${M.t}" width="${W - M.l - M.r}" height="${H - M.t - M.b}" fill="transparent" id="apuSerieAlvo"/>
      </svg>
      <div class="apu-dica" id="apuSerieDica" style="display:none"></div>
    </div>
    <div class="apu-legenda">${series.map(s => `<span><i style="background:${s.cor}"></i>${esc(s.nome)} · ${apuInt(APU.serieAcumulada ? s.valores[s.valores.length - 1] : s.valores.reduce((a, b) => a + b, 0))}</span>`).join("")}</div>
  `;
}

function apuEscala(max) {
  const bruto = max / 4;
  const pot = Math.pow(10, Math.floor(Math.log10(bruto || 1)));
  const n = bruto / pot;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pot;
}

function apuBindSerie() {
  const svg = document.getElementById("apuSerieSvg");
  const alvo = document.getElementById("apuSerieAlvo");
  const dica = document.getElementById("apuSerieDica");
  const guia = document.getElementById("apuSerieGuia");
  const box = document.getElementById("apuSerieBox");
  const s = APU._serieAtual;
  if (!svg || !alvo || !s) return;

  alvo.addEventListener("mousemove", ev => {
    const r = svg.getBoundingClientRect();
    const escala = s.W / r.width;
    const px = (ev.clientX - r.left) * escala;
    let i = 0, melhor = Infinity;
    s.dias.forEach((_, k) => { const dist = Math.abs(s.x(k) - px); if (dist < melhor) { melhor = dist; i = k; } });

    guia.setAttribute("x1", s.x(i));
    guia.setAttribute("x2", s.x(i));
    guia.style.display = "";

    const d = s.dias[i];
    dica.innerHTML = `<b>${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}</b>` +
      s.series.map(se => `<div><i style="background:${se.cor}"></i>${esc(se.nome)}: ${apuInt(se.valores[i])}</div>`).join("");
    const br = box.getBoundingClientRect();
    dica.style.left = `${s.x(i) / escala}px`;
    dica.style.top = `${Math.max(ev.clientY - br.top - 12, 40)}px`;
    dica.style.display = "";
  });

  alvo.addEventListener("mouseleave", () => { dica.style.display = "none"; guia.style.display = "none"; });
}


/* ---------- tabulacoes ---------- */

function apuTabulacoes(tabulacao) {
  const base = APU.tabBase;
  const valor = r => Number(base === "leads" ? r.leads : r.interacoes) || 0;
  const alternar = (v, rotulo) => `<button class="${APU.tabBase === v ? "ativo" : ""}" data-apu-tabbase="${v}">${rotulo}</button>`;

  const topo = `
    <div class="apu-painel-topo">
      <div>
        <h2>Tabulações</h2>
        <p>Clique numa classificação para ver as tabulações das EPS por trás dela</p>
      </div>
      <div class="apu-alternar">${alternar("leads", "Leads")}${alternar("interacoes", "Interações")}</div>
    </div>`;

  if (!tabulacao.length) return topo + `<div class="apu-sem-dado">Sem tabulações para este recorte.</div>`;

  const porClasse = {};
  tabulacao.forEach(r => { porClasse[r.classificacao] = (porClasse[r.classificacao] || 0) + valor(r); });
  const ordem = APU_CLASSES.map(c => c[0]);
  const classes = Object.keys(porClasse).sort((a, b) => {
    const ia = ordem.indexOf(a), ib = ordem.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  const total = classes.reduce((a, c) => a + porClasse[c], 0) || 1;

  if (APU.tabClasse && !porClasse[APU.tabClasse]) APU.tabClasse = "";

  /* rosca */
  const R = 90, r0 = 58, C = 100;
  let ang = -Math.PI / 2;
  const fatias = classes.map(c => {
    const frac = porClasse[c] / total;
    const a0 = ang, a1 = ang + frac * Math.PI * 2 - (frac < 1 ? 0.012 : 0);
    ang += frac * Math.PI * 2;
    const grande = a1 - a0 > Math.PI ? 1 : 0;
    const p = (raio, a) => `${C + raio * Math.cos(a)},${C + raio * Math.sin(a)}`;
    const d = frac >= 0.9999
      ? `M ${C} ${C - R} A ${R} ${R} 0 1 1 ${C - 0.01} ${C - R} L ${C - 0.01} ${C - r0} A ${r0} ${r0} 0 1 0 ${C} ${C - r0} Z`
      : `M ${p(R, a0)} A ${R} ${R} 0 ${grande} 1 ${p(R, a1)} L ${p(r0, a1)} A ${r0} ${r0} 0 ${grande} 0 ${p(r0, a0)} Z`;
    const apagada = APU.tabClasse && APU.tabClasse !== c ? "apagada" : "";
    return `<path d="${d}" fill="${apuClasse(c)[2]}" class="${apagada}" data-apu-classe="${esc(c)}"><title>${esc(apuClasse(c)[1])}: ${apuPct(frac * 100)}</title></path>`;
  }).join("");

  const sel = APU.tabClasse;
  const centroValor = sel ? porClasse[sel] : total;

  const legenda = classes.map(c => `
    <li><button class="${sel === c ? "ativo" : ""}" data-apu-classe="${esc(c)}">
      <i style="background:${apuClasse(c)[2]}"></i>
      <span>${esc(apuClasse(c)[1])}</span>
      <em>${apuPct(apuDiv(porClasse[c], total))}</em>
    </button></li>`).join("");

  /* detalhe */
  const det = {};
  tabulacao.filter(r => !sel || r.classificacao === sel).forEach(r => {
    const nome = r.tabulacao_3 || r.tabulacao_2 || r.tabulacao_1 || apuClasse(r.classificacao)[1];
    const k = nome + "|" + r.classificacao;
    det[k] = det[k] || { nome, classe: r.classificacao, v: 0 };
    det[k].v += valor(r);
  });
  const lista = Object.values(det).sort((a, b) => b.v - a.v).slice(0, 12);

  const epsTab = [...new Set(tabulacao.map(r => r.eps))].sort();
  let porEpsHtml = "";
  if (epsTab.length > 1) {
    porEpsHtml = `<div class="apu-tab-eps">${epsTab.map(e => {
      const linhas = tabulacao.filter(r => r.eps === e);
      const tot = linhas.reduce((a, r) => a + valor(r), 0) || 1;
      const segs = classes.map(c => {
        const v = linhas.filter(r => r.classificacao === c).reduce((a, r) => a + valor(r), 0);
        if (!v) return "";
        const pct = (v / tot) * 100;
        const apagada = sel && sel !== c ? "opacity:.25;" : "";
        return `<i style="width:${pct}%;background:${apuClasse(c)[2]};${apagada}" title="${esc(apuClasse(c)[1])}: ${apuPct(pct)}"></i>`;
      }).join("");
      const selPct = sel ? apuPct(apuDiv(linhas.filter(r => r.classificacao === sel).reduce((a, r) => a + valor(r), 0), tot)) : "";
      return `<div class="apu-tab-eps-linha"><b>${esc(apuNomeEps(e))}</b><div class="apu-empilhada">${segs}</div><em>${selPct}</em></div>`;
    }).join("")}</div>`;
  }
  const maxDet = Math.max(1, ...lista.map(i => i.v));
  const baseDet = sel ? porClasse[sel] : total;

  return `
    ${topo}
    <div class="apu-tab">
      <div>
        <div class="apu-rosca">
          <svg viewBox="0 0 200 200" role="img" aria-label="Distribuição por classificação">${fatias}</svg>
          <div class="apu-rosca-centro">
            <strong>${apuInt(centroValor)}</strong>
            <span>${sel ? esc(apuClasse(sel)[1]) : (base === "leads" ? "leads" : "interações")}</span>
          </div>
        </div>
        <ul class="apu-classes">${legenda}</ul>
      </div>
      <div class="apu-detalhe">
        ${porEpsHtml ? `<h3>Mix por EPS${sel ? ` · % em "${esc(apuClasse(sel)[1])}"` : ""}</h3>${porEpsHtml}` : ""}
        <h3>${sel ? `Tabulações de "${esc(apuClasse(sel)[1])}"` : "Tabulações mais frequentes"}${sel ? ` <button class="apu-btn" style="margin-left:8px;padding:3px 9px" data-apu-classe="">Ver todas</button>` : ""}</h3>
        <div class="apu-barras">
          ${lista.map(i => `
            <div class="apu-barra-linha">
              <span title="${esc(i.nome)}">${esc(i.nome)}</span>
              <strong>${apuInt(i.v)} · ${apuPct(apuDiv(i.v, baseDet), 0)}</strong>
              <div class="apu-barra-trilho"><i style="width:${(i.v / maxDet) * 100}%;background:${apuClasse(i.classe)[2]}"></i></div>
            </div>`).join("")}
        </div>
      </div>
    </div>
  `;
}


/* ---------- mes a mes ---------- */

function apuMensal(serie) {
  const topo = `
    <div class="apu-painel-topo">
      <div>
        <h2>Matrículas mês a mês</h2>
        <p>Por mês da matrícula, empilhado por EPS</p>
      </div>
    </div>`;

  const porMes = {};
  const epsSet = new Set();
  serie.forEach(r => {
    const m = apuDia(r.dia).slice(0, 7);
    porMes[m] = porMes[m] || {};
    porMes[m][r.eps] = (porMes[m][r.eps] || 0) + (Number(r.matriculas) || 0);
    epsSet.add(r.eps);
  });

  const meses = Object.keys(porMes).sort();
  if (!meses.length) return topo + `<div class="apu-sem-dado">Sem matrículas no recorte.</div>`;

  const eps = [...epsSet].sort();
  const W = 640, H = 240, M = { t: 18, r: 10, b: 28, l: 40 };
  const totais = meses.map(m => eps.reduce((a, e) => a + (porMes[m][e] || 0), 0));
  const max = Math.max(1, ...totais);
  const passo = apuEscala(max);
  const topoY = Math.ceil(max / passo) * passo;
  const y = v => H - M.b - (v / topoY) * (H - M.t - M.b);
  const banda = (W - M.l - M.r) / meses.length;
  const larg = Math.min(56, banda * 0.6);
  const nomeMes = m => new Date(m + "-15T12:00:00").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", "");

  let grade = "";
  for (let v = 0; v <= topoY; v += passo) {
    grade += `<line class="grade" x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/>
              <text class="eixo" x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${apuInt(v)}</text>`;
  }

  const barras = meses.map((m, i) => {
    const x0 = M.l + i * banda + (banda - larg) / 2;
    let acc = 0;
    const blocos = eps.map(e => {
      const v = porMes[m][e] || 0;
      if (!v) return "";
      const yTop = y(acc + v), yBase = y(acc);
      acc += v;
      return `<rect x="${x0}" y="${yTop}" width="${larg}" height="${Math.max(yBase - yTop, 0)}" fill="${apuCorEps(e)}"><title>${esc(apuNomeEps(e))}: ${apuInt(v)}</title></rect>`;
    }).join("");
    return `${blocos}
      <text class="eixo" x="${x0 + larg / 2}" y="${y(totais[i]) - 6}" text-anchor="middle" style="fill:var(--c-ink);font-weight:600">${apuInt(totais[i])}</text>
      <text class="eixo" x="${x0 + larg / 2}" y="${H - 8}" text-anchor="middle">${nomeMes(m)}</text>`;
  }).join("");

  return `
    ${topo}
    <div class="apu-grafico"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Matrículas por mês">${grade}${barras}</svg></div>
    <div class="apu-legenda">${eps.map(e => `<span><i style="background:${apuCorEps(e)}"></i>${esc(apuNomeEps(e))}</span>`).join("")}</div>
  `;
}


/* ---------- atingimento / resultado por EPS ---------- */

function apuAtingimento(porEps, total) {
  const comMeta = porEps.filter(e => e.meta);

  if (comMeta.length) {
    const maxEscala = Math.max(120, ...comMeta.map(e => e.atingimento || 0));
    return `
      <div class="apu-painel-topo">
        <div>
          <h2>Atingimento por EPS</h2>
          <p>Realizado contra a meta de cada EPS · linha = 100%</p>
        </div>
      </div>
      <div class="apu-ating">
        ${comMeta.map(e => {
          const cor = e.atingimento >= 100 ? "var(--c-ok)" : e.atingimento >= 70 ? "var(--c-accent)" : e.atingimento >= 40 ? "var(--c-wait)" : "var(--c-stop)";
          return `
            <div class="apu-ating-linha">
              <b>${esc(apuNomeEps(e.eps))}</b>
              <div class="apu-ating-trilho">
                <i style="width:${Math.min((e.atingimento || 0) / maxEscala, 1) * 100}%;background:${cor}"></i>
                <u style="left:${(100 / maxEscala) * 100}%"></u>
              </div>
              <em>${apuPct(e.atingimento, 0)}</em>
              <div class="apu-ating-sub">${apuInt(e.realizado_meta)} de ${apuInt(e.meta)}</div>
            </div>`;
        }).join("")}
      </div>
      ${total.atingimento !== null ? `<p class="apu-funil-nota">Total do recorte: ${apuPct(total.atingimento, 0)} da meta.</p>` : ""}
      ${porEps.filter(e => !e.meta).length ? `<p class="apu-funil-nota">Sem meta cadastrada: ${porEps.filter(e => !e.meta).map(e => `${esc(apuNomeEps(e.eps))} (${apuInt(e.matriculas)} matrículas)`).join(", ")}.</p>` : ""}
    `;
  }

  const max = Math.max(1, ...porEps.map(e => e.matriculas || 0));
  return `
    <div class="apu-painel-topo">
      <div>
        <h2>Matrículas por EPS</h2>
        <p>Nenhuma campanha do recorte tem meta cadastrada</p>
      </div>
    </div>
    <div class="apu-ating">
      ${porEps.map(e => `
        <div class="apu-ating-linha">
          <b>${esc(apuNomeEps(e.eps))}</b>
          <div class="apu-ating-trilho"><i style="width:${((e.matriculas || 0) / max) * 100}%;background:${apuCorEps(e.eps)}"></i></div>
          <em>${apuInt(e.matriculas)}</em>
          <div class="apu-ating-sub">${e.mailing && e.trabalhados !== null ? `% Ret ${apuPct(apuDiv(e.matriculas, e.mailing))}` : "sem funil operacional"}</div>
        </div>`).join("")}
    </div>
  `;
}


/* ---------- tabela ---------- */

function apuTabela(funil, esteira = { porChave: {} }) {
  const linhas = [...funil].sort((a, b) =>
    apuDia(b.periodo_ini).localeCompare(apuDia(a.periodo_ini)) || a.codigo_campanha.localeCompare(b.codigo_campanha) || a.eps.localeCompare(b.eps));

  const n = v => (v === null || v === undefined ? `<span class="apu-indisp">—</span>` : apuInt(v));

  return `
    <div class="apu-painel-topo">
      <div>
        <h2>Campanhas apuradas</h2>
        <p>Uma linha por campanha e EPS · clique para filtrar o dashboard pela campanha</p>
      </div>
    </div>
    <div class="apu-tabela-wrap">
      <table class="apu-tabela">
        <thead>
          <tr>
            <th>Campanha</th><th>EPS</th><th>Status</th><th>Período</th>
            <th>Mailing env.</th><th>Mailing</th><th>Trabalhados</th><th>Atendidos</th><th>Efetivos</th><th>Vendas</th><th>Matrículas</th><th>Esteira</th>
            <th>% Ret</th><th>Meta</th><th>Ating.</th>
          </tr>
        </thead>
        <tbody>
          ${linhas.map(r => `
            <tr data-apu-linha="${esc(r.codigo_campanha)}">
              <td><b>${esc(r.codigo_campanha)}</b><small title="${esc(r.nome_campanha || "")}">${esc(r.nome_campanha || "")}</small></td>
              <td>${esc(apuNomeEps(r.eps))}</td>
              <td><span class="apu-status ${esc(r.status_apuracao)}">${r.status_apuracao === "FINAL" ? "Apurada" : "Parcial"}</span></td>
              <td>${apuData(r.periodo_ini)} a ${apuData(r.periodo_fim)}</td>
              <td>${n(r.mailing_enviado)}</td>
              <td>${n(r.mailing)}</td>
              <td>${n(r.trabalhados)}</td>
              <td>${n(r.alo)}</td>
              <td>${n(r.efetivos)}</td>
              <td>${n(r.vendas)}</td>
              <td><b>${n(r.matriculas)}</b></td>
              <td>${esteira.porChave[r.codigo_campanha + "|" + r.eps] ? apuInt(esteira.porChave[r.codigo_campanha + "|" + r.eps]) : `<span class="apu-indisp">—</span>`}</td>
              <td>${r.mailing && r.trabalhados !== null ? apuPct(apuDiv(r.matriculas, r.mailing)) : `<span class="apu-indisp">—</span>`}</td>
              <td>${r.meta_eps ? apuInt(r.meta_eps) : `<span class="apu-indisp">—</span>`}</td>
              <td>${(() => {
                const meta = Number(r.meta_eps) || 0;
                const real = Number(r.meta_base === "VENDAS" ? r.vendas : r.matriculas) || 0;
                return meta && r.meta_base ? apuPct((real / meta) * 100, 0) : `<span class="apu-indisp">—</span>`;
              })()}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}


/* ---------- pendencias do robo ---------- */

function apuPendencias(pendencias) {
  return `
    <section class="apu-painel apu-col-12">
      <div class="apu-painel-topo">
        <div>
          <h2>Pendências do robô</h2>
          <p>Campanhas que o robô não conseguiu apurar nos últimos 7 dias. Somem quando a apuração seguinte dá certo.</p>
        </div>
      </div>
      <ul class="apu-pend">
        ${pendencias.map(p => `
          <li>
            <span class="tipo ${esc(p.resultado)}">${p.resultado === "ERRO" ? "Erro" : "Pendência"}</span>
            <div><b>${esc(p.codigo_campanha || "Geral")}${p.eps ? ` · ${esc(apuNomeEps(p.eps))}` : ""}</b> — ${esc(p.mensagem || "")}</div>
            <span>${apuDataHora(p.dt_execucao)}</span>
          </li>`).join("")}
      </ul>
    </section>
  `;
}


/* ---------------- interacao ---------------- */

function apuRedesenhar() {
  const raiz = document.getElementById("apu-root");
  if (!raiz) return;
  raiz.innerHTML = apuracaoMiolo();
  apuBindSerie();
}

function bindApuracao() {
  const raiz = document.getElementById("apu-root");
  if (!raiz || raiz.dataset.ligado) { apuBindSerie(); return; }
  raiz.dataset.ligado = "1";

  raiz.addEventListener("change", ev => {
    const campo = ev.target.dataset.apuFiltro;
    if (!campo) return;
    APU.f[campo] = ev.target.value || "";
    apuRedesenhar();
  });

  raiz.addEventListener("click", async ev => {
    const el = ev.target.closest("[data-apu],[data-apu-eps],[data-apu-metrica],[data-apu-quebra],[data-apu-acumulado],[data-apu-tabbase],[data-apu-classe],[data-apu-linha]");
    if (!el) return;
    const ds = el.dataset;

    if (ds.apu === "recarregar") {
      await carregarApuracao(true);
    } else if (ds.apu === "limpar") {
      APU.f = { campanha: "", eps: "", produto: "", tipo: "", status: "", ini: "", fim: "" };
      APU.tabClasse = "";
    } else if (ds.apuEps !== undefined) {
      APU.f.eps = ds.apuEps;
    } else if (ds.apuMetrica) {
      APU.serieMetrica = ds.apuMetrica;
    } else if (ds.apuQuebra) {
      APU.serieQuebra = ds.apuQuebra;
    } else if (ds.apuAcumulado !== undefined) {
      APU.serieAcumulada = ds.apuAcumulado === "1";
    } else if (ds.apuTabbase) {
      APU.tabBase = ds.apuTabbase;
    } else if (ds.apuClasse !== undefined) {
      APU.tabClasse = APU.tabClasse === ds.apuClasse ? "" : ds.apuClasse;
    } else if (ds.apuLinha) {
      APU.f.campanha = APU.f.campanha === ds.apuLinha ? "" : ds.apuLinha;
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      return;
    }

    apuRedesenhar();
  });

  apuBindSerie();
}