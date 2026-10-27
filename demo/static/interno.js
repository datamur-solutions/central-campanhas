
const app = document.getElementById("app");
let campanhasCache = [];
let campanhaAtual = null;
let acessosPendentes = [];
let prontasEncerramento = [];
let usuarioAtual = null;
let viewAtual = "campanhas";
let filtroCampanhaV9 = "TODAS";
let notificacoes = [];
let notificacaoResumo = {pendentes:0, enviados:0, erros:0, arquivados:0};
let notificacaoProvider = {configurado:false, provider:"POWER_AUTOMATE"};
let notificacaoAutomacao = {
  habilitada: false,
  provider_configurado: false,
  ativa: false,
  modo: "MANUAL_SEGURO"
};

const esc = v =>
  String(v ?? "")
    .replace(/[&<>"']/g, m => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[m]));

function mensagemErroApi(detail) {
  if (Array.isArray(detail)) {
    return detail.map(item => {
      const campo = Array.isArray(item.loc)
        ? item.loc.filter(x => x !== "body").join(" › ")
        : "";
      return `${campo ? campo + ": " : ""}${item.msg || "valor inválido"}`;
    }).join(" | ");
  }

  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {}
  }

  return detail || "Erro ao processar a solicitação.";
}



let loadingRequests = 0;
let loadingStartedAt = 0;

function garantirLoadingOverlay() {
  let overlay = document.getElementById("globalLoadingOverlay");

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "globalLoadingOverlay";
    overlay.className = "global-loading-overlay hidden";
    overlay.innerHTML = `
      <div class="global-loading-card">
        <div class="global-spinner" aria-hidden="true"></div>
        <div>
          <strong id="globalLoadingTitle">Atualizando informações...</strong>
          <span id="globalLoadingText">Aguarde enquanto carregamos os dados.</span>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
  }

  return overlay;
}


function mostrarLoading(
  texto = "Aguarde enquanto carregamos os dados."
) {
  loadingRequests += 1;

  if (loadingRequests > 1) {
    const textoEl =
      document.getElementById("globalLoadingText");

    if (textoEl) {
      textoEl.textContent = texto;
    }

    return;
  }

  loadingStartedAt = Date.now();

  const overlay =
    garantirLoadingOverlay();

  const textoEl =
    overlay.querySelector(
      "#globalLoadingText"
    );

  if (textoEl) {
    textoEl.textContent =
      texto;
  }

  overlay.classList.remove(
    "hidden"
  );

  requestAnimationFrame(
    () =>
      overlay.classList.add(
        "visible"
      )
  );
}


function ocultarLoading() {
  loadingRequests =
    Math.max(
      0,
      loadingRequests - 1
    );

  if (loadingRequests > 0) {
    return;
  }

  const overlay =
    document.getElementById(
      "globalLoadingOverlay"
    );

  if (!overlay) {
    return;
  }

  const minimoVisivel =
    320;

  const decorrido =
    Date.now() -
    loadingStartedAt;

  const espera =
    Math.max(
      0,
      minimoVisivel -
      decorrido
    );

  setTimeout(
    () => {
      if (loadingRequests > 0) {
        return;
      }

      overlay.classList.remove(
        "visible"
      );

      setTimeout(
        () =>
          overlay.classList.add(
            "hidden"
          ),
        180
      );
    },
    espera
  );
}


async function api(url, opt = {}) {
  mostrarLoading(
    "Consultando a Central de Campanhas..."
  );

  try {
    const r =
      await fetch(
        url,
        opt
      );

    let d = {};

    try {
      d =
        await r.json();
    } catch {}

    if (!r.ok) {
      throw new Error(
        mensagemErroApi(
          d.detail
        )
      );
    }

    return d;

  } finally {
    ocultarLoading();
  }
}

function statusClass(status) {
  if (
    status === "ENVIADA_EPS" ||
    status === "EM_EXECUCAO"
  ) {
    return "status run";
  }

  return "status";
}


function statusLabel(status) {
  const mapa = {
    CADASTRADA_PLANEJAMENTO: "Planejamento",
    EM_VALIDACAO_COMERCIAL: "Validação Comercial",
    VALIDADA_COMERCIAL: "Validada pelo Comercial",
    PARCIALMENTE_LIBERADA_EPS: "Liberação parcial para EPS",
    ENVIADA_EPS: "Com as EPS",
    AGUARDANDO_PLANEJAMENTO_EPS: "Aguardando planejamento EPS",
    PLANEJAMENTO_EPS: "Planejamento EPS",
    GO_LIVE_APROVADO: "Go-Live aprovado",
    EM_EXECUCAO: "Em execução",
    EXECUCAO_FINALIZADA: "Execução finalizada",
    ENCERRADA_EDUNOVA: "Encerrada pela EduNova"
  };

  return mapa[status] || status || "-";
}


function fluxoCampanha(campanha, eps) {
  const status = campanha.status_campanha;

  const epsLiberadas =
    (eps || []).filter(
      item =>
        item.liberada_para_eps
    );

  const epsEmExecucao =
    epsLiberadas.some(
      item =>
        item.status_execucao_eps ===
        "EM_EXECUCAO"
    );

  const epsPreparando =
    epsLiberadas.some(
      item =>
        [
          "AGUARDANDO_PLANEJAMENTO_EPS",
          "PLANEJAMENTO_EPS",
          "GO_LIVE_APROVADO"
        ].includes(
          item.status_execucao_eps
        )
    );

  const todasFinalizadas =
    epsLiberadas.length > 0 &&
    epsLiberadas.every(
      item =>
        item.status_execucao_eps ===
        "EXECUCAO_FINALIZADA"
    );

  let etapa = 0;
  let titulo = "Campanha cadastrada";
  let descricao =
    "O Planejamento precisa encaminhar a campanha ao Comercial.";
  let cta =
    "Enviar para Comercial";
  let destino =
    "acoes";

  if (
    status ===
    "EM_VALIDACAO_COMERCIAL"
  ) {
    etapa = 1;
    titulo =
      "Aguardando validação Comercial";
    descricao =
      "O Comercial revisa a campanha e confirma que ela está pronta para seguir.";
    cta =
      "Validar campanha";
    destino =
      "acoes";
  }

  if (
    [
      "VALIDADA_COMERCIAL",
      "PARCIALMENTE_LIBERADA_EPS"
    ].includes(
      status
    )
  ) {
    etapa = 2;
    titulo =
      "Pronta para liberar às EPS";
    descricao =
      "Selecione as EPS e faça o handoff operacional.";
    cta =
      "Liberar para EPS";
    destino =
      "acoes";
  }

  if (
    status ===
    "ENVIADA_EPS"
  ) {
    etapa = 2;
    titulo =
      "Campanha enviada às EPS";
    descricao =
      "Acompanhe a preparação e a execução das EPS.";
    cta =
      "Acompanhar EPS";
    destino =
      "eps";

    if (
      epsPreparando
    ) {
      etapa = 2;
    }

    if (
      epsEmExecucao
    ) {
      etapa = 3;
      titulo =
        "Campanha em execução";
      descricao =
        "Acompanhe performance, gaps e evidências.";
      cta =
        "Ver performance";
      destino =
        "performance";
    }

    if (
      todasFinalizadas
    ) {
      etapa = 4;
      titulo =
        "Pronta para encerramento EduNova";
      descricao =
        "Todas as EPS finalizaram. Falta somente o fechamento interno da campanha.";
      cta =
        "Encerrar campanha";
      destino =
        "acoes";
    }
  }

  if (
    status ===
    "ENCERRADA_EDUNOVA"
  ) {
    etapa = 4;
    titulo =
      "Campanha encerrada";
    descricao =
      "O ciclo operacional foi concluído pela EduNova.";
    cta =
      "Ver resultados";
    destino =
      "performance";
  }

  return {
    etapa,
    titulo,
    descricao,
    cta,
    destino
  };
}


function fluxoVisual(campanha, eps) {
  const fluxo = fluxoCampanha(campanha, eps);
  const etapas = [
    "Planejamento",
    "Comercial",
    "EPS",
    "Execução",
    "Finalizada"
  ];

  return `
    <div class="status-hero">
      <div>
        <div class="eyebrow">PRÓXIMA AÇÃO</div>
        <h3>${esc(fluxo.titulo)}</h3>
        <p>${esc(fluxo.descricao)}</p>
      </div>

      <button
        class="btn status-hero-btn"
        id="fluxoCta"
        data-destino="${esc(fluxo.destino)}"
      >
        ${esc(fluxo.cta)} ›
      </button>
    </div>

    <div class="flow-track">
      ${etapas.map((nome, indice) => `
        <div class="flow-step ${indice < fluxo.etapa ? "done" : ""} ${indice === fluxo.etapa ? "active" : ""}">
          <span>${indice < fluxo.etapa ? "✓" : indice + 1}</span>
          <strong>${nome}</strong>
        </div>
        ${indice < etapas.length - 1 ? `<div class="flow-line ${indice < fluxo.etapa ? "done" : ""}"></div>` : ""}
      `).join("")}
    </div>
  `;
}

async function carregar() {
  try {
    const [
      me,
      lista
    ] = await Promise.all([
      api("/api/me"),
      api("/api/internal/campaigns")
    ]);

    usuarioAtual =
      me;

    campanhasCache =
      lista.campanhas || [];

    const complementares =
      await Promise.allSettled([
        api("/api/internal/external-access/pending"),
        api("/api/internal/closure-ready"),
        api("/api/internal/notifications?limit=100"),
        api("/api/internal/notifications/provider-status"),
        api("/api/internal/notifications/automation-status")
      ]);

    const acessosResultado =
      complementares[0];

    const encerramentoResultado =
      complementares[1];

    const notificacoesResultado =
      complementares[2];

    const providerResultado =
      complementares[3];

    const automacaoResultado =
      complementares[4];

    acessosPendentes =
      acessosResultado.status === "fulfilled"
        ? acessosResultado.value.solicitacoes || []
        : [];

    prontasEncerramento =
      encerramentoResultado.status === "fulfilled"
        ? encerramentoResultado.value.campanhas || []
        : [];

    if (
      notificacoesResultado.status ===
      "fulfilled"
    ) {
      notificacoes =
        notificacoesResultado.value.notificacoes || [];

      notificacaoResumo =
        notificacoesResultado.value.resumo || {
          pendentes: 0,
          enviados: 0,
          erros: 0,
          arquivados: 0,
          processando: 0
        };
    } else {
      notificacoes = [];

      notificacaoResumo = {
        pendentes: 0,
        enviados: 0,
        erros: 0,
        arquivados: 0,
        processando: 0
      };

      console.warn(
        "Central de notificações indisponível:",
        notificacoesResultado.reason
      );
    }

    if (
      providerResultado.status ===
      "fulfilled"
    ) {
      notificacaoProvider =
        providerResultado.value;
    } else {
      notificacaoProvider = {
        configurado: false,
        provider: "POWER_AUTOMATE"
      };
    }

    if (
      automacaoResultado.status ===
      "fulfilled"
    ) {
      notificacaoAutomacao =
        automacaoResultado.value;
    } else {
      notificacaoAutomacao = {
        habilitada: false,
        provider_configurado: false,
        ativa: false,
        modo: "MANUAL_SEGURO"
      };
    }

    renderPortal(
      usuarioAtual,
      campanhasCache
    );

  } catch (e) {
    app.innerHTML = `
      <div class="main">
        <div class="notice error">
          ${esc(e.message)}
        </div>
      </div>
    `;
  }
}

function renderPortal(
  me,
  campanhas
) {
  const acaoNecessaria =
    campanhas.filter(
      item =>
        [
          "CADASTRADA_PLANEJAMENTO",
          "EM_VALIDACAO_COMERCIAL",
          "VALIDADA_COMERCIAL",
          "PARCIALMENTE_LIBERADA_EPS"
        ].includes(
          item.status_campanha
        )
    ).length;

  const comEPS =
    campanhas.filter(
      item =>
        item.status_campanha ===
        "ENVIADA_EPS"
    ).length;

  const encerradas =
    campanhas.filter(
      item =>
        item.status_campanha ===
        "ENCERRADA_EDUNOVA"
    ).length;

  app.innerHTML = `
    <div class="v9-app-shell">

      <header class="v9-topbar">

        <div class="v9-brand-block">

          <img
            src="static/EduNova.png"
            alt="EduNova Educação"
            class="v9-logo"
          >

          <div class="v9-brand-divider"></div>

          <div class="v9-product-name">
            <strong>
              Central de Campanhas
            </strong>

            <span>
              Governança Comercial
            </span>
          </div>

        </div>

        <nav class="v9-topnav">

          <button
            id="navCampanhas"
            class="${viewAtual === "campanhas" ? "active" : ""}"
          >
            Visão geral
          </button>

          <button
            id="navAcessos"
            class="${viewAtual === "acessos" ? "active" : ""}"
          >
            Acessos EPS

            ${
              acessosPendentes.length
                ? `
                  <span class="v9-nav-count">
                    ${acessosPendentes.length}
                  </span>
                `
                : ""
            }
          </button>

          <button
            id="navNotificacoes"
            class="${viewAtual === "notificacoes" ? "active" : ""}"
          >
            Notificações

            ${
              notificacaoResumo.pendentes ||
              notificacaoResumo.erros
                ? `
                  <span class="v9-nav-count">
                    ${
                      Number(
                        notificacaoResumo.pendentes ||
                        0
                      )
                      +
                      Number(
                        notificacaoResumo.erros ||
                        0
                      )
                    }
                  </span>
                `
                : ""
            }
          </button>

        </nav>

        <div class="v9-user-block">

          <div class="v9-user-avatar">
            ${
              esc(
                primeiroNomeV9(
                  me.nome
                )
                .charAt(0)
                .toUpperCase()
              )
            }
          </div>

          <div>
            <strong>
              ${esc(primeiroNomeV9(me.nome))}
            </strong>

            <span>
              ${esc(me.perfil || "")}
            </span>
          </div>

        </div>

      </header>

      <main class="v9-main">

        ${
          viewAtual === "campanhas"
            ? campanhasViewV6(
                me,
                campanhas,
                acaoNecessaria,
                comEPS,
                encerradas
              )
            : viewAtual === "acessos"
              ? `
                <div class="v9-contained-page">
                  ${acessosViewV6()}
                </div>
              `
              : `
                <div class="v9-contained-page">
                  ${notificacoesViewV7()}
                </div>
              `
        }

      </main>

    </div>

    <div id="modalRoot"></div>
  `;

  document
    .getElementById(
      "navCampanhas"
    )
    .onclick =
      () => {
        viewAtual =
          "campanhas";

        renderPortal(
          usuarioAtual,
          campanhasCache
        );
      };

  document
    .getElementById(
      "navAcessos"
    )
    .onclick =
      () => {
        viewAtual =
          "acessos";

        renderPortal(
          usuarioAtual,
          campanhasCache
        );
      };

  document
    .getElementById(
      "navNotificacoes"
    )
    .onclick =
      () => {
        viewAtual =
          "notificacoes";

        renderPortal(
          usuarioAtual,
          campanhasCache
        );
      };

  if (
    viewAtual === "campanhas"
  ) {
    bindCampanhasV6();
  } else if (
    viewAtual === "acessos"
  ) {
    bindAcessosV6();
  } else {
    bindNotificacoesV7();
  }
}



function primeiroNomeV9(
  nome
) {
  const valor =
    String(
      nome ||
      "Usuário"
    )
      .trim()
      .split(/\s+/)[0];

  return valor
    ? valor.charAt(0).toUpperCase() +
      valor.slice(1).toLowerCase()
    : "Usuário";
}


function saudacaoV9() {
  const hora =
    new Date()
      .getHours();

  if (hora < 12) {
    return "Bom dia";
  }

  if (hora < 18) {
    return "Boa tarde";
  }

  return "Boa noite";
}


function humanizarV9(
  valor
) {
  return String(
    valor ||
    "-"
  )
    .replaceAll(
      "_",
      " "
    )
    .toLowerCase()
    .replace(
      /\b\w/g,
      letra =>
        letra.toUpperCase()
    );
}


function bucketCampanhaV9(
  status
) {
  if (
    status ===
    "ENCERRADA_EDUNOVA"
  ) {
    return "ENCERRADA";
  }

  if (
    status ===
    "ENVIADA_EPS"
  ) {
    return "EPS";
  }

  return "INTERNA";
}


function proximaAcaoInternaV9(
  status
) {
  const mapa = {
    CADASTRADA_PLANEJAMENTO:
      "Enviar para Comercial",

    EM_VALIDACAO_COMERCIAL:
      "Validar campanha",

    VALIDADA_COMERCIAL:
      "Liberar para EPS",

    PARCIALMENTE_LIBERADA_EPS:
      "Concluir liberação",

    ENVIADA_EPS:
      "Acompanhar execução",

    ENCERRADA_EDUNOVA:
      "Consultar resultados"
  };

  return (
    mapa[
      status
    ]
    ||
    "Abrir campanha"
  );
}


function prioridadeCampanhaV9(
  item
) {
  const status =
    item.status_campanha;

  if (
    status ===
    "CADASTRADA_PLANEJAMENTO"
  ) {
    return {
      classe:
        "attention",

      titulo:
        "Planejamento",

      texto:
        "Pronta para seguir ao Comercial"
    };
  }

  if (
    status ===
    "EM_VALIDACAO_COMERCIAL"
  ) {
    return {
      classe:
        "critical",

      titulo:
        "Comercial",

      texto:
        "Aguardando validação"
    };
  }

  if (
    [
      "VALIDADA_COMERCIAL",
      "PARCIALMENTE_LIBERADA_EPS"
    ].includes(
      status
    )
  ) {
    return {
      classe:
        "attention",

      titulo:
        "Handoff",

      texto:
        "Pronta para liberar à EPS"
    };
  }

  if (
    status ===
    "ENVIADA_EPS"
  ) {
    return {
      classe:
        "healthy",

      titulo:
        "Com as EPS",

      texto:
        "Em acompanhamento operacional"
    };
  }

  return {
    classe:
      "neutral",

    titulo:
      "Encerrada",

    texto:
      "Ciclo concluído"
  };
}


function statusDistribuicaoV9(
  campanhas
) {
  const interno =
    campanhas.filter(
      item =>
        bucketCampanhaV9(
          item.status_campanha
        ) ===
        "INTERNA"
    ).length;

  const eps =
    campanhas.filter(
      item =>
        bucketCampanhaV9(
          item.status_campanha
        ) ===
        "EPS"
    ).length;

  const encerrada =
    campanhas.filter(
      item =>
        bucketCampanhaV9(
          item.status_campanha
        ) ===
        "ENCERRADA"
    ).length;

  const total =
    Math.max(
      1,
      campanhas.length
    );

  const pInterno =
    (
      interno /
      total *
      100
    );

  const pEps =
    (
      eps /
      total *
      100
    );

  return {
    interno,
    eps,
    encerrada,
    pInterno,
    pEps,
    gradiente:
      `conic-gradient(
        #7b35d4 0 ${pInterno}%,
        #b388eb ${pInterno}% ${pInterno + pEps}%,
        #38a66b ${pInterno + pEps}% 100%
      )`
  };
}


function produtosV9(
  campanhas
) {
  const mapa =
    new Map();

  campanhas.forEach(
    item => {
      const produto =
        humanizarV9(
          item.produto ||
          "Não definido"
        );

      mapa.set(
        produto,
        (
          mapa.get(
            produto
          )
          ||
          0
        )
        +
        1
      );
    }
  );

  return Array
    .from(
      mapa.entries()
    )
    .sort(
      (
        a,
        b
      ) =>
        b[1] -
        a[1]
    );
}


function campanhaCardAtencaoV9(
  item
) {
  const prioridade =
    prioridadeCampanhaV9(
      item
    );

  return `
    <article class="v9-attention-card ${prioridade.classe}">

      <div class="v9-attention-top">

        <span class="v9-code">
          ${esc(item.codigo_campanha)}
        </span>

        <span class="v9-health-dot"></span>

      </div>

      <h3>
        ${esc(item.nome_campanha)}
      </h3>

      <div class="v9-attention-meta">

        <span>
          ${esc(humanizarV9(item.produto))}
        </span>

        <span>
          ${esc(prioridade.titulo)}
        </span>

      </div>

      <p>
        ${esc(prioridade.texto)}
      </p>

      <button
        class="v9-link abrir-campanha"
        data-code="${esc(item.codigo_campanha)}"
      >
        ${esc(
          proximaAcaoInternaV9(
            item.status_campanha
          )
        )}
        <span>›</span>
      </button>

    </article>
  `;
}


function produtoBarsV9(
  campanhas
) {
  const produtos =
    produtosV9(
      campanhas
    );

  const maximo =
    Math.max(
      1,
      ...produtos.map(
        item =>
          item[1]
      )
    );

  if (
    !produtos.length
  ) {
    return `
      <div class="v9-empty-mini">
        Ainda não há dados de produto.
      </div>
    `;
  }

  return produtos
    .slice(
      0,
      6
    )
    .map(
      (
        [
          produto,
          quantidade
        ]
      ) => `
        <div class="v9-bar-row">

          <div class="v9-bar-label">
            <span>${esc(produto)}</span>
            <strong>${quantidade}</strong>
          </div>

          <div class="v9-bar-track">
            <div
              class="v9-bar-fill"
              style="width:${
                quantidade /
                maximo *
                100
              }%"
            ></div>
          </div>

        </div>
      `
    )
    .join("");
}


function rowsV9(
  campanhas
) {
  const prontas =
    new Set(
      prontasEncerramento.map(
        item =>
          item.codigo_campanha
      )
    );

  return campanhas
    .map(
      item => {

        const prioridade =
          prioridadeCampanhaV9(
            item
          );

        return `
          <tr>

            <td>
              <button
                class="v9-code-button abrir-campanha"
                data-code="${esc(item.codigo_campanha)}"
              >
                ${esc(item.codigo_campanha)}
              </button>
            </td>

            <td>
              <div class="v9-table-title">
                <strong>
                  ${esc(item.nome_campanha)}
                </strong>

                <small>
                  ${
                    item.tipo_acao
                      ? esc(
                          humanizarV9(
                            item.tipo_acao
                          )
                        )
                      : "Campanha comercial"
                  }
                </small>
              </div>
            </td>

            <td>
              ${esc(humanizarV9(item.produto))}
            </td>

            <td>
              <span class="v9-status-pill ${prioridade.classe}">
                ${
                  prontas.has(
                    item.codigo_campanha
                  )
                    ? "Pronta para encerrar"
                    : esc(
                        statusLabel(
                          item.status_campanha
                        )
                      )
                }
              </span>
            </td>

            <td>
              ${esc(humanizarV9(item.etapa_pop))}
            </td>

            <td>
              <div class="v9-owner">
                <span class="v9-avatar-mini">
                  ${
                    esc(
                      String(
                        item.responsavel_comercial ||
                        "C"
                      )
                        .charAt(0)
                        .toUpperCase()
                    )
                  }
                </span>

                <span>
                  ${
                    esc(
                      item.responsavel_comercial ||
                      "-"
                    )
                  }
                </span>
              </div>
            </td>

            <td>
              <button
                class="v9-open-icon abrir-campanha"
                data-code="${esc(item.codigo_campanha)}"
                aria-label="Abrir campanha"
                title="Abrir campanha"
              >
                ›
              </button>
            </td>

          </tr>
        `;
      }
    )
    .join("");
}

function campanhasViewV6(
  me,
  campanhas,
  acaoNecessaria,
  comEPS,
  encerradas
) {
  const distribuicao =
    statusDistribuicaoV9(
      campanhas
    );

  const atencao =
    campanhas
      .filter(
        item =>
          item.status_campanha !==
          "ENCERRADA_EDUNOVA"
      )
      .sort(
        (
          a,
          b
        ) => {
          const ordem = {
            EM_VALIDACAO_COMERCIAL: 0,
            CADASTRADA_PLANEJAMENTO: 1,
            VALIDADA_COMERCIAL: 2,
            PARCIALMENTE_LIBERADA_EPS: 3,
            ENVIADA_EPS: 4
          };

          return (
            (
              ordem[
                a.status_campanha
              ]
              ??
              99
            )
            -
            (
              ordem[
                b.status_campanha
              ]
              ??
              99
            )
          );
        }
      )
      .slice(
        0,
        4
      );

  const nome =
    primeiroNomeV9(
      me.nome
    );

  const total =
    campanhas.length;

  const ativas =
    Math.max(
      0,
      total -
      encerradas
    );

  return `
    <section class="v9-hero">

      <div class="v9-hero-copy">

        <span class="v9-hero-kicker">
          ${saudacaoV9()}, ${esc(nome)}
        </span>

        <h1>
          ${
            acaoNecessaria
              ? `<strong>${acaoNecessaria}</strong> campanha${acaoNecessaria > 1 ? "s" : ""} ${acaoNecessaria > 1 ? "esperam" : "espera"} sua decisão.`
              : "Nenhuma campanha exige decisão agora."
          }
        </h1>

        <p>
          ${
            acaoNecessaria
              ? `Portfólio de ${total} campanha(s). ${comEPS} em execução nas EPS.`
              : `Portfólio de ${total} campanha(s). Acompanhe a execução nas EPS.`
          }
        </p>

        <div class="v9-hero-actions">

          <button
            class="v9-primary-action"
            id="novaCampanha"
          >
            <span>+</span>
            Nova campanha
          </button>

          <button
            class="v9-ghost-action"
            id="refresh"
          >
            Atualizar visão
          </button>

        </div>

      </div>

    </section>

    ${
      acessosPendentes.length ||
      prontasEncerramento.length
        ? `
          <section class="v9-alert-strip">

            ${
              acessosPendentes.length
                ? `
                  <button
                    class="v9-alert-item"
                    id="alertAcessos"
                  >
                    <span class="v9-alert-mark">!</span>

                    <div>
                      <strong>
                        ${acessosPendentes.length}
                        acesso(s) EPS aguardando decisão
                      </strong>

                      <small>
                        Revisar solicitações
                      </small>
                    </div>

                    <span class="v9-alert-arrow">›</span>
                  </button>
                `
                : ""
            }

            ${
              prontasEncerramento.length
                ? `
                  <div class="v9-alert-item success">
                    <span class="v9-alert-mark">✓</span>

                    <div>
                      <strong>
                        ${prontasEncerramento.length}
                        campanha(s) pronta(s) para encerrar
                      </strong>

                      <small>
                        Execução das EPS finalizada
                      </small>
                    </div>
                  </div>
                `
                : ""
            }

          </section>
        `
        : ""
    }

    <section class="v10-acoes">

      <button
        class="v10-acao principal"
        id="novaCampanhaQuick"
      >
        <span class="v10-acao-marca">+</span>

        <div>
          <strong>Cadastrar campanha</strong>
          <p>Cria o código CAM e abre o fluxo de planejamento.</p>
        </div>
      </button>

      <button
        class="v10-acao ${acaoNecessaria ? "is-live" : ""}"
        data-filtro="comercial"
      >
        <span class="v10-acao-numero">${acaoNecessaria}</span>

        <div>
          <strong>Precisam de decisão</strong>
          <p>Aguardando validação comercial interna.</p>
        </div>
      </button>

      <button
        class="v10-acao"
        data-filtro="eps"
      >
        <span class="v10-acao-numero">${comEPS}</span>

        <div>
          <strong>Com as EPS</strong>
          <p>Liberadas para execução externa.</p>
        </div>
      </button>

      <button
        class="v10-acao"
        data-filtro="encerradas"
      >
        <span class="v10-acao-numero">${encerradas}</span>

        <div>
          <strong>Encerradas</strong>
          <p>Ciclo concluído, ${ativas} ainda ativa(s).</p>
        </div>
      </button>

    </section>

    <section class="v9-dashboard-grid">

      <article class="v9-panel">

        <div class="v9-panel-head">
          <div>
            <h2>
              Onde as campanhas estão
            </h2>

            <p>
              Do cadastro ao encerramento. O acúmulo em uma etapa
              mostra onde o fluxo está travando.
            </p>
          </div>
        </div>

        <div class="v10-esteira">
          ${esteiraV10(campanhas)}
        </div>

      </article>

      <article class="v9-panel">

        <div class="v9-panel-head">
          <div>
            <h2>
              Campanhas por produto
            </h2>
          </div>
        </div>

        <div class="v9-bars">
          ${produtoBarsV9(campanhas)}
        </div>

      </article>

    </section>

    <section class="v9-section">

      <div class="v9-section-head">

        <div>
          <h2>
            Precisa da sua atenção
          </h2>

          <p>
            As campanhas abaixo aparecem primeiro
            porque exigem decisão ou acompanhamento.
          </p>
        </div>

      </div>

      <div class="v10-linhas">

        ${
          atencao.length
            ? atencao
                .map(
                  linhaCampanhaV10
                )
                .join("")
            : `
              <div class="v9-empty-state">
                <strong>
                  Nenhuma ação pendente
                </strong>
                <span>
                  Todas as campanhas estão em dia.
                </span>
              </div>
            `
        }

      </div>

    </section>

    <section class="v9-panel v9-campaigns-panel">

      <div class="v9-section-head v9-table-head">

        <div>
          <h2>
            Todas as campanhas
          </h2>
        </div>

        <div class="v9-search-wrap">

          <span class="v9-search-icon">
            ⌕
          </span>

          <input
            id="busca"
            placeholder="Buscar campanha, código, produto..."
          >

        </div>

      </div>

      <div class="v10-filtros" id="filtros">
        <button class="v10-filtro ativo" data-filtro="todas">Todas</button>
        <button class="v10-filtro" data-filtro="planejamento">Planejamento</button>
        <button class="v10-filtro" data-filtro="comercial">Comercial</button>
        <button class="v10-filtro" data-filtro="eps">Com as EPS</button>
        <button class="v10-filtro" data-filtro="encerradas">Encerradas</button>
      </div>

      <div class="v9-table-scroll">

        <table class="v9-table">

          <thead>
            <tr>
              <th>Código</th>
              <th>Campanha</th>
              <th>Produto</th>
              <th>Status</th>
              <th>Etapa</th>
              <th>Responsável</th>
              <th></th>
            </tr>
          </thead>

          <tbody id="tb">
            ${rowsV9(campanhas)}
          </tbody>

        </table>

      </div>

    </section>
  `;
}


function rowsV6(
  campanhas
) {
  return rowsV9(
    campanhas
  );
}


function bindCampanhasV6() {
  const refresh =
    document.getElementById(
      "refresh"
    );

  if (
    refresh
  ) {
    refresh.onclick =
      carregar;
  }

  const nova =
    document.getElementById(
      "novaCampanha"
    );

  if (
    nova
  ) {
    nova.onclick =
      abrirCadastroMVP;
  }

  const busca =
    document.getElementById(
      "busca"
    );

  if (
    busca
  ) {
    busca.oninput = aplicarFiltroV10;
  }

  const alert =
    document.getElementById(
      "alertAcessos"
    );

  if (
    alert
  ) {
    alert.onclick =
      () => {
        viewAtual =
          "acessos";

        renderPortal(
          usuarioAtual,
          campanhasCache
        );
      };
  }

  bindAbrir();
  bindFiltrosV10();
}


function acessosViewV6() {
  return `
    <div class="top">

      <div>
        <div class="eyebrow">
          GOVERNANÇA DE ACESSO
        </div>

        <h1>
          Acessos EPS
        </h1>

        <p class="muted">
          Aprove ou rejeite solicitações de
          primeiro acesso ao Portal EPS.
        </p>
      </div>

      <span class="badge">
        ${acessosPendentes.length}
        pendente(s)
      </span>

    </div>

    <section class="panel">

      ${
        acessosPendentes.length
          ? `
            <div class="access-grid">

              ${
                acessosPendentes
                  .map(
                    item => `
                      <article class="access-card">

                        <div class="card-top">

                          <span class="code">
                            ${esc(item.eps_identificada)}
                          </span>

                          <span class="status">
                            PENDENTE
                          </span>

                        </div>

                        <h3>
                          ${esc(
                            item.nome_usuario ||
                            "Usuário EPS"
                          )}
                        </h3>

                        <p class="access-email">
                          ${esc(item.email_usuario)}
                        </p>

                        <div class="access-meta">

                          <span>
                            Domínio:
                            ${esc(item.dominio_email)}
                          </span>

                          <span>
                            Solicitado:
                            ${esc(item.dt_solicitacao)}
                          </span>

                        </div>

                        <div class="access-actions">

                          <button
                            class="btn approve-access"
                            data-id="${esc(item.solicitacao_uuid)}"
                            data-email="${esc(item.email_usuario)}"
                          >
                            Aprovar
                          </button>

                          <button
                            class="btn secondary reject-access"
                            data-id="${esc(item.solicitacao_uuid)}"
                            data-email="${esc(item.email_usuario)}"
                          >
                            Rejeitar
                          </button>

                        </div>

                      </article>
                    `
                  )
                  .join("")
              }

            </div>
          `
          : `
            <div class="empty-state">

              <div class="empty-icon">
                ✓
              </div>

              <h2>
                Nenhum acesso pendente
              </h2>

              <p>
                Todas as solicitações recebidas
                já foram tratadas.
              </p>

            </div>
          `
      }

    </section>
  `;
}


function bindAcessosV6() {
  document
    .querySelectorAll(
      ".approve-access"
    )
    .forEach(
      button => {
        button.onclick =
          () =>
            decidirAcessoV6(
              button.dataset.id,
              "APROVAR",
              button.dataset.email
            );
      }
    );

  document
    .querySelectorAll(
      ".reject-access"
    )
    .forEach(
      button => {
        button.onclick =
          () =>
            decidirAcessoV6(
              button.dataset.id,
              "REJEITAR",
              button.dataset.email
            );
      }
    );
}


async function decidirAcessoV6(
  id,
  decisao,
  email
) {
  let motivo =
    null;

  if (
    decisao ===
    "REJEITAR"
  ) {
    motivo =
      window.prompt(
        `Motivo da rejeição para ${email}:`
      );

    if (
      motivo ===
      null
    ) {
      return;
    }
  } else {
    const confirmar =
      window.confirm(
        `Aprovar acesso de ${email}?`
      );

    if (
      !confirmar
    ) {
      return;
    }
  }

  try {
    await api(
      `/api/internal/external-access/${encodeURIComponent(id)}/decision`,
      {
        method:
          "POST",

        headers: {
          "Content-Type":
            "application/json"
        },

        body:
          JSON.stringify({
            decisao,
            motivo
          })
      }
    );

    await carregar();

    viewAtual =
      "acessos";

    renderPortal(
      usuarioAtual,
      campanhasCache
    );

  } catch (error) {
    alert(
      error.message
    );
  }
}


function notificacoesViewV7() {
  const statusConector =
    notificacaoProvider.configurado
      ? "Conector configurado"
      : "Conector ainda não configurado";

  const pendentes =
    Number(
      notificacaoResumo.pendentes ||
      0
    );

  const erros =
    Number(
      notificacaoResumo.erros ||
      0
    );

  const arquivados =
    Number(
      notificacaoResumo.arquivados ||
      0
    );

  const processando =
    Number(
      notificacaoResumo.processando ||
      0
    );

  const autoAtiva =
    Boolean(
      notificacaoAutomacao.ativa
    );

  return `
    <div class="top">
      <div>
        <div class="eyebrow">
          COMUNICAÇÃO AUTOMÁTICA
        </div>

        <h1>
          Notificações
        </h1>

        <p class="muted">
          Auditoria dos e-mails gerados
          pelos movimentos do workflow.
        </p>
      </div>

      <div class="notification-top-badges">

        <span class="badge ${
          notificacaoProvider.configurado
            ? "provider-ok"
            : "provider-off"
        }">
          ${esc(statusConector)}
        </span>

        <span class="badge ${
          autoAtiva
            ? "automation-on"
            : "automation-off"
        }">
          ${
            autoAtiva
              ? "Automação ativa"
              : "Automação desativada"
          }
        </span>

      </div>
    </div>

    <div class="kpis">

      <div class="kpi">
        <span>Pendentes</span>
        <strong>${pendentes}</strong>
      </div>

      <div class="kpi">
        <span>Enviadas</span>
        <strong>${notificacaoResumo.enviados || 0}</strong>
      </div>

      <div class="kpi">
        <span>Com erro</span>
        <strong>${erros}</strong>
      </div>

      <div class="kpi">
        <span>Automação</span>
        <strong style="font-size:15px">
          ${autoAtiva ? "Ativa" : "Desativada"}
        </strong>
      </div>

    </div>

    ${
      autoAtiva
        ? `
          <div class="notice success">
            <strong>Envio automático ativo.</strong>
            Novas notificações geradas pelo workflow
            serão enviadas automaticamente pelo Power Automate.
          </div>
        `
        : notificacaoProvider.configurado
          ? `
            <div class="notice">
              <strong>Power Automate conectado, mas o automático está desligado.</strong>
              A fila permanece protegida até a ativação da V8.
            </div>
          `
          : `
            <div class="notice">
              O Power Automate ainda não está conectado.
            </div>
          `
    }

    <section class="panel v8-automation-panel">

      <div class="notification-safety-head">

        <div>
          <div class="eyebrow">
            V8 • ENVIO AUTOMÁTICO
          </div>

          <h2>
            Operação automática com contingência
          </h2>

          <p class="muted">
            O envio manual permanece apenas para
            contingência, auditoria e reprocessamento.
          </p>
        </div>

        <div class="v8-auto-icon ${
          autoAtiva
            ? "active"
            : ""
        }">
          ⚡
        </div>

      </div>

      <div class="v8-auto-grid">

        <div class="v8-auto-card">
          <span>STATUS</span>

          <strong>
            ${
              autoAtiva
                ? "Automático ativo"
                : "Automático desativado"
            }
          </strong>

          <small>
            ${
              autoAtiva
                ? "Novos eventos são enviados sem clique manual."
                : "Nenhum evento é enviado automaticamente."
            }
          </small>
        </div>

        <div class="v8-auto-card">
          <span>POWER AUTOMATE</span>

          <strong>
            ${
              notificacaoProvider.configurado
                ? "Conectado"
                : "Não configurado"
            }
          </strong>

          <small>
            Canal responsável pelo envio dos e-mails.
          </small>
        </div>

        <div class="v8-auto-card">
          <span>EM PROCESSAMENTO</span>

          <strong>
            ${processando}
          </strong>

          <small>
            Registros reservados pelo worker automático.
          </small>
        </div>

        <div class="v8-auto-card">
          <span>ARQUIVADAS</span>

          <strong>
            ${arquivados}
          </strong>

          <small>
            Histórico preservado sem envio.
          </small>
        </div>

      </div>

      <div class="v8-test-row">

        <div>
          <strong>
            Teste controlado da automação
          </strong>

          <small>
            Envia somente para o seu e-mail EduNova
            e não cria nem consome registros da fila.
          </small>
        </div>

        <button
          class="btn secondary"
          id="testAutomationV8"
          ${
            notificacaoProvider.configurado
              ? ""
              : "disabled"
          }
        >
          Testar automação
        </button>

      </div>

      <div
        id="notificationActionMessage"
      ></div>

    </section>

    ${
      pendentes > 0 ||
      erros > 0
        ? `
          <section class="panel notification-safety-panel">

            <div class="notification-safety-head">

              <div>
                <div class="eyebrow">
                  CONTINGÊNCIA
                </div>

                <h2>
                  Itens que precisam de atenção
                </h2>

                <p class="muted">
                  ERRO nunca é reenviado automaticamente.
                  Ele exige decisão humana.
                </p>
              </div>

              <div class="safe-shield">
                ✓
              </div>

            </div>

            <div class="safe-actions-grid">

              ${
                pendentes > 0
                  ? `
                    <div class="safe-action-card real">
                      <span class="safe-action-step">!</span>
                      <h3>Pendentes residuais</h3>

                      <p>
                        Existem
                        <strong>${pendentes}</strong>
                        notificações pendentes.
                      </p>

                      <button
                        class="btn"
                        id="prepareRealSend"
                        ${
                          notificacaoProvider.configurado
                            ? ""
                            : "disabled"
                        }
                      >
                        Revisar envio manual
                      </button>
                    </div>
                  `
                  : ""
              }

              ${
                erros > 0
                  ? `
                    <div class="safe-action-card retry">
                      <span class="safe-action-step">!</span>
                      <h3>Tratar erros</h3>

                      <p>
                        Existem
                        <strong>${erros}</strong>
                        notificações com falha.
                      </p>

                      <div class="safe-card-actions">

                        <button
                          class="btn secondary"
                          id="prepareRetry"
                          ${
                            notificacaoProvider.configurado
                              ? ""
                              : "disabled"
                          }
                        >
                          Reprocessar
                        </button>

                        <button
                          class="btn archive-btn"
                          id="prepareArchiveErrors"
                        >
                          Arquivar sem enviar
                        </button>

                      </div>
                    </div>
                  `
                  : ""
              }

            </div>

          </section>
        `
        : ""
    }

    <section class="panel">

      <div class="notification-toolbar">

        <div>
          <h2>
            Histórico de comunicação
          </h2>

          <p class="muted">
            Enviadas, erros, arquivadas
            e eventuais pendências.
          </p>
        </div>

        <div class="notification-actions">

          <button
            class="btn secondary"
            id="refreshNotifications"
          >
            Atualizar
          </button>

        </div>

      </div>

      ${
        notificacoes.length
          ? `
            <div class="notification-list">
              ${
                notificacoes
                  .map(
                    item =>
                      notificacaoCardV7(
                        item
                      )
                  )
                  .join("")
              }
            </div>
          `
          : `
            <div class="empty-state">
              <div class="empty-icon">✓</div>
              <h2>Nenhuma notificação</h2>
              <p>O histórico está vazio.</p>
            </div>
          `
      }

    </section>
  `;
}


function notificacaoCardV7(
  item
) {
  const status =
    (
      item.status_envio ||
      "PENDENTE"
    ).toUpperCase();

  return `
    <article class="notification-card">

      <div class="notification-status-col">

        <span
          class="notification-status ${
            (status === "ENVIADO" || status === "ENVIADA")
              ? "sent"
              : status === "ERRO"
                ? "error"
                : (status === "ARQUIVADO" || status === "ARQUIVADA")
                  ? "archived"
                  : status === "PROCESSANDO"
                    ? "processing"
                    : "pending"
          }"
        >
          ${esc(status)}
        </span>

        <small>
          ${esc(
            item.origem_notificacao ||
            "CAMPANHA"
          )}
        </small>

      </div>

      <div class="notification-content">

        <div class="notification-head">

          <div>
            <span class="code">
              ${
                item.codigo_campanha
                  ? esc(item.codigo_campanha)
                  : esc(item.eps || "ACESSO EPS")
              }
            </span>

            <h3>
              ${esc(
                item.assunto ||
                item.tipo_evento ||
                "Notificação"
              )}
            </h3>
          </div>

          <span class="notification-date">
            ${esc(item.dt_criacao || "-")}
          </span>

        </div>

        <p>
          ${esc(
            item.resumo_evento ||
            "Evento gerado automaticamente."
          )}
        </p>

        <div class="notification-meta">

          <span>
            <strong>Evento:</strong>
            ${esc(item.tipo_evento || "-")}
          </span>

          <span>
            <strong>Para:</strong>
            ${esc(item.destinatarios_to || "-")}
          </span>

          ${
            item.destinatarios_cc
              ? `
                <span>
                  <strong>CC:</strong>
                  ${esc(item.destinatarios_cc)}
                </span>
              `
              : ""
          }

          ${
            item.erro_envio
              ? `
                <span class="notification-error-text">
                  <strong>Erro:</strong>
                  ${esc(item.erro_envio)}
                </span>
              `
              : ""
          }

        </div>

      </div>

    </article>
  `;
}


function bindNotificacoesV7() {
  document
    .getElementById(
      "refreshNotifications"
    )
    .onclick =
      async () => {
        await carregar();

        viewAtual =
          "notificacoes";

        renderPortal(
          usuarioAtual,
          campanhasCache
        );
      };

  const testarAutomacao =
    document.getElementById(
      "testAutomationV8"
    );

  if (
    testarAutomacao
  ) {
    testarAutomacao.onclick =
      async () => {

        const alvo =
          document.getElementById(
            "notificationActionMessage"
          );

        try {
          testarAutomacao.disabled =
            true;

          testarAutomacao.textContent =
            "Enviando teste...";

          const resultado =
            await api(
              "/api/internal/notifications/automation-test",
              {
                method:
                  "POST"
              }
            );

          alvo.innerHTML = `
            <div class="notice success">
              Teste V8 enviado somente para
              <strong>${esc(resultado.destinatario_teste || "-")}</strong>.
              Nenhum registro da fila foi alterado.
            </div>
          `;

        } catch (error) {
          alvo.innerHTML = `
            <div class="notice error">
              ${esc(error.message)}
            </div>
          `;

        } finally {
          testarAutomacao.disabled =
            false;

          testarAutomacao.textContent =
            "Testar automação";
        }
      };
  }

  const real =
    document.getElementById(
      "prepareRealSend"
    );

  if (
    real
  ) {
    real.onclick =
      () =>
        abrirConfirmacaoEnvioV72(
          "PENDENTES"
        );
  }

  const retry =
    document.getElementById(
      "prepareRetry"
    );

  if (
    retry
  ) {
    retry.onclick =
      () =>
        abrirConfirmacaoEnvioV72(
          "ERROS"
        );
  }

  const arquivar =
    document.getElementById(
      "prepareArchiveErrors"
    );

  if (
    arquivar
  ) {
    arquivar.onclick =
      () =>
        abrirConfirmacaoArquivamentoV723();
  }
}


function abrirConfirmacaoArquivamentoV723() {
  const quantidade =
    Number(
      notificacaoResumo.erros || 0
    );

  const textoConfirmacao =
    `ARQUIVAR ${quantidade}`;

  const root =
    document.getElementById("modalRoot");

  root.innerHTML = `
    <div class="modal">
      <div class="modal-card notification-confirm-modal">

        <div class="modal-head">
          <div>
            <div class="eyebrow">LIMPEZA SEGURA DA FILA</div>
            <h2>Arquivar erros sem enviar</h2>
          </div>
          <button class="close" id="closeArchiveErrors">×</button>
        </div>

        <div class="archive-warning">
          <div class="archive-warning-icon">✓</div>
          <div>
            <strong>Nenhum e-mail será enviado.</strong>
            <p>
              Os ${quantidade} registros continuarão no histórico,
              mas sairão da fila de erros e receberão o status
              <strong>ARQUIVADO</strong>.
            </p>
          </div>
        </div>

        <div class="send-summary">
          <div><span>Erros atuais</span><strong>${quantidade}</strong></div>
          <div><span>E-mails enviados</span><strong>0</strong></div>
          <div><span>Novo status</span><strong>ARQUIVADO</strong></div>
        </div>

        <label class="confirm-card">
          <input id="confirmArchiveCheck" type="checkbox">
          <span>
            <strong>Confirmo que estes erros históricos não devem ser enviados.</strong>
            <small>Os registros serão preservados para auditoria.</small>
          </span>
        </label>

        <label>
          Digite <strong>${esc(textoConfirmacao)}</strong> para confirmar *
        </label>

        <input
          id="confirmArchiveText"
          autocomplete="off"
          placeholder="${esc(textoConfirmacao)}"
        >

        <div id="archiveMessage"></div>

        <div class="wizard-actions">
          <button class="btn secondary" id="cancelArchiveErrors">Cancelar</button>
          <div style="flex:1"></div>
          <button class="btn archive-btn" id="executeArchiveErrors">Arquivar sem enviar</button>
        </div>

      </div>
    </div>
  `;

  const fechar =
    () => root.innerHTML = "";

  document.getElementById("closeArchiveErrors").onclick = fechar;
  document.getElementById("cancelArchiveErrors").onclick = fechar;

  document.getElementById("executeArchiveErrors").onclick = async () => {
    const check = document.getElementById("confirmArchiveCheck").checked;
    const texto = document.getElementById("confirmArchiveText").value.trim().toUpperCase();
    const mensagem = document.getElementById("archiveMessage");

    if (!check) {
      mensagem.innerHTML = `<div class="notice error">Marque a confirmação de arquivamento.</div>`;
      return;
    }

    if (texto !== textoConfirmacao) {
      mensagem.innerHTML = `<div class="notice error">Digite exatamente: <strong>${esc(textoConfirmacao)}</strong></div>`;
      return;
    }

    const botao = document.getElementById("executeArchiveErrors");

    try {
      botao.disabled = true;
      botao.textContent = "Arquivando...";

      const resultado = await api(
        "/api/internal/notifications/archive-errors-confirmed",
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            confirmar: true,
            quantidade_esperada: quantidade
          })
        }
      );

      root.innerHTML = "";
      await carregar();
      viewAtual = "notificacoes";
      renderPortal(usuarioAtual, campanhasCache);

      const alvo = document.getElementById("notificationActionMessage");
      if (alvo) {
        alvo.innerHTML = `<div class="notice success">Arquivamento concluído. Arquivadas: <strong>${resultado.arquivadas || 0}</strong>. Erros restantes: <strong>${resultado.erros_restantes || 0}</strong>. E-mails enviados: <strong>${resultado.envios_realizados || 0}</strong>.</div>`;
      }

    } catch (error) {
      botao.disabled = false;
      botao.textContent = "Arquivar sem enviar";
      mensagem.innerHTML = `<div class="notice error">${esc(error.message)}</div>`;
    }
  };
}


function abrirConfirmacaoEnvioV72(modo) {
  const isRetry = modo === "ERROS";

  const quantidade =
    Number(
      isRetry
        ? notificacaoResumo.erros || 0
        : notificacaoResumo.pendentes || 0
    );

  const titulo =
    isRetry
      ? "Reprocessar notificações com erro"
      : "Confirmar envio real";

  const descricao =
    isRetry
      ? `Serão reprocessadas ${quantidade} notificações que apresentaram erro.`
      : `Serão enviadas ${quantidade} notificações para os destinatários reais cadastrados.`;

  const textoConfirmacao =
    isRetry
      ? `REPROCESSAR ${quantidade}`
      : `ENVIAR ${quantidade}`;

  const root =
    document.getElementById("modalRoot");

  root.innerHTML = `
    <div class="modal">
      <div class="modal-card notification-confirm-modal">
        <div class="modal-head">
          <div>
            <div class="eyebrow">CONFIRMAÇÃO DE SEGURANÇA</div>
            <h2>${esc(titulo)}</h2>
          </div>
          <button class="close" id="closeNotificationConfirm">×</button>
        </div>

        <div class="send-warning">
          <div class="send-warning-icon">!</div>
          <div>
            <strong>${esc(descricao)}</strong>
            <p>
              Esta ação envia e-mails reais.
              Depois do envio bem-sucedido, os registros terão o status atualizado.
            </p>
          </div>
        </div>

        <div class="send-summary">
          <div>
            <span>Quantidade</span>
            <strong>${quantidade}</strong>
          </div>
          <div>
            <span>Tipo</span>
            <strong>${isRetry ? "Reprocessamento" : "Envio pendente"}</strong>
          </div>
          <div>
            <span>Conector</span>
            <strong>Power Automate</strong>
          </div>
        </div>

        <label class="confirm-card">
          <input id="confirmRealSendCheck" type="checkbox">
          <span>
            <strong>Confirmo que revisei a quantidade e autorizo o disparo.</strong>
            <small>
              Para segurança, digite também a confirmação solicitada abaixo.
            </small>
          </span>
        </label>

        <label>
          Digite <strong>${esc(textoConfirmacao)}</strong> para confirmar *
        </label>

        <input
          id="confirmRealSendText"
          autocomplete="off"
          placeholder="${esc(textoConfirmacao)}"
        >

        <div id="confirmSendMessage"></div>

        <div class="wizard-actions">
          <button class="btn secondary" id="cancelRealSend">Cancelar</button>
          <div style="flex:1"></div>
          <button class="btn danger" id="executeRealSend">
            ${isRetry ? "Reprocessar agora" : "Enviar agora"}
          </button>
        </div>
      </div>
    </div>
  `;

  const fechar =
    () => root.innerHTML = "";

  document
    .getElementById("closeNotificationConfirm")
    .onclick = fechar;

  document
    .getElementById("cancelRealSend")
    .onclick = fechar;

  document
    .getElementById("executeRealSend")
    .onclick =
      async () => {
        const check =
          document
            .getElementById("confirmRealSendCheck")
            .checked;

        const texto =
          document
            .getElementById("confirmRealSendText")
            .value
            .trim()
            .toUpperCase();

        const mensagem =
          document.getElementById("confirmSendMessage");

        if (!check) {
          mensagem.innerHTML = `
            <div class="notice error">
              Marque a confirmação de autorização.
            </div>
          `;
          return;
        }

        if (texto !== textoConfirmacao) {
          mensagem.innerHTML = `
            <div class="notice error">
              Digite exatamente: <strong>${esc(textoConfirmacao)}</strong>
            </div>
          `;
          return;
        }

        const botao =
          document.getElementById("executeRealSend");

        try {
          botao.disabled = true;
          botao.textContent =
            isRetry ? "Reprocessando..." : "Enviando...";

          const endpoint =
            isRetry
              ? "/api/internal/notifications/retry-errors-confirmed"
              : "/api/internal/notifications/process-confirmed";

          const resultado =
            await api(
              endpoint,
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/json"
                },
                body: JSON.stringify({
                  confirmar: true,
                  quantidade_esperada: quantidade
                })
              }
            );

          root.innerHTML = "";

          await carregar();
          viewAtual = "notificacoes";
          renderPortal(usuarioAtual, campanhasCache);

          const alvo =
            document.getElementById("notificationActionMessage");

          if (alvo) {
            alvo.innerHTML = `
              <div class="notice ${resultado.erros ? "error" : "success"}">
                Processamento concluído.
                Enviadas: <strong>${resultado.enviadas || 0}</strong>.
                Erros: <strong>${resultado.erros || 0}</strong>.
                Restantes: <strong>${resultado.restantes || 0}</strong>.
              </div>
            `;
          }
        } catch (error) {
          botao.disabled = false;
          botao.textContent =
            isRetry ? "Reprocessar agora" : "Enviar agora";

          mensagem.innerHTML = `
            <div class="notice error">${esc(error.message)}</div>
          `;
        }
      };
}

function rows(campanhas) {
  return campanhas
    .map(c => `
      <tr>

        <td>
          <strong
            style="color:#6721b8"
          >
            ${esc(c.codigo_campanha)}
          </strong>
        </td>

        <td>
          ${esc(c.nome_campanha)}
        </td>

        <td>
          ${esc(c.produto || "-")}
        </td>

        <td>
          ${esc(c.tipo_acao || "-")}
        </td>

        <td>
          <span class="${statusClass(c.status_campanha)}">
            ${esc(c.status_campanha || "-")}
          </span>
        </td>

        <td>
          ${esc(c.etapa_pop || "-")}
        </td>

        <td>
          ${esc(c.responsavel_planejamento || "-")}
        </td>

        <td>
          ${esc(c.responsavel_comercial || "-")}
        </td>

        <td>
          <button
            class="btn secondary abrir-campanha"
            data-code="${esc(c.codigo_campanha)}"
          >
            Abrir
          </button>
        </td>

      </tr>
    `)
    .join("");
}

function bindAbrir() {
  document
    .querySelectorAll(
      ".abrir-campanha"
    )
    .forEach(
      botao => {

        botao.onclick =
          () =>
            abrirCampanha(
              botao.dataset.code
            );

      }
    );
}

async function abrirCampanha(
  codigo
) {
  try {
    mostrarLoading(
      `Abrindo ${codigo}...`
    );

    campanhaAtual =
      await api(
        `/api/internal/campaigns/${encodeURIComponent(codigo)}`
      );

    ocultarLoading();

    renderDetalhe(
      "resumo"
    );

  } catch (e) {
    ocultarLoading();
    alert(
      e.message
    );
  }
}

function renderDetalhe(
  tab
) {
  const dados =
    campanhaAtual;

  const c =
    dados.campanha;

  const root =
    document.getElementById(
      "modalRoot"
    );

  root.innerHTML = `
    <div class="modal">

      <div class="modal-card detail-modal-v5">

        <div class="modal-head">

          <div>

            <div class="eyebrow">
              ${esc(c.codigo_campanha)}
            </div>

            <h2>
              ${esc(c.nome_campanha)}
            </h2>

            <span class="${statusClass(c.status_campanha)}">
              ${esc(statusLabel(c.status_campanha))}
            </span>

          </div>

          <button
            class="close"
            id="fecharModal"
          >
            ×
          </button>

        </div>

        ${fluxoVisual(c, dados.eps)}

        <div class="tabs">

          ${[
            "resumo",
            "eps",
            "kpis",
            "performance",
            "gaps",
            "evidencias",
            "workflow",
            "acoes"
          ].map(
            item => `
              <button
                class="${item === tab ? "active" : ""}"
                data-tab="${item}"
              >
                ${item === "acoes" ? "PRÓXIMA AÇÃO" : item.toUpperCase()}
              </button>
            `
          ).join("")}

        </div>

        <div id="detailBody">
          ${conteudoTab(tab)}
        </div>

      </div>

    </div>
  `;

  document
    .getElementById("fecharModal")
    .onclick =
      () =>
        root.innerHTML = "";

  document
    .querySelectorAll("[data-tab]")
    .forEach(
      botao =>
        botao.onclick =
          () =>
            renderDetalhe(
              botao.dataset.tab
            )
    );

  const fluxoCta =
    document.getElementById(
      "fluxoCta"
    );

  if (
    fluxoCta
  ) {
    fluxoCta.onclick =
      () =>
        renderDetalhe(
          fluxoCta.dataset.destino
        );
  }

  bindTab(
    tab
  );
}

function conteudoTab(tab) {
  const d =
    campanhaAtual;

  const c =
    d.campanha;

  if (
    tab === "resumo"
  ) {
    return `
      <div class="kpis">

        <div class="kpi">
          <span>Produto</span>
          <strong style="font-size:17px">
            ${esc(c.produto || "-")}
          </strong>
        </div>

        <div class="kpi">
          <span>Tipo</span>
          <strong style="font-size:17px">
            ${esc(c.tipo_acao || "-")}
          </strong>
        </div>

        <div class="kpi">
          <span>Etapa POP</span>
          <strong style="font-size:15px">
            ${esc(c.etapa_pop || "-")}
          </strong>
        </div>

        <div class="kpi">
          <span>Status</span>
          <strong style="font-size:15px">
            ${esc(c.status_campanha || "-")}
          </strong>
        </div>

      </div>

      <div class="panel">

        <h2>Oportunidade</h2>
        <p>${esc(c.oportunidade_problema || "-")}</p>

        <h2>Objetivo</h2>
        <p>${esc(c.objetivo_campanha || "-")}</p>

        <h2>Resultado esperado</h2>
        <p>${esc(c.resultado_esperado || "-")}</p>

        <h2>Estratégia</h2>
        <p>${esc(c.estrategia || "-")}</p>

        <h2>Público-alvo</h2>
        <p>${esc(c.publico_alvo || "-")}</p>

        <h2>Vigência</h2>
        <p>
          ${esc(c.dt_inicio_prevista || "-")}
          ›
          ${esc(c.dt_fim_prevista || "-")}
        </p>

      </div>
    `;
  }

  if (
    tab === "eps"
  ) {
    return `
      <div class="cards">

        ${
          d.eps
            .map(
              e => `
                <article class="card">

                  <div class="card-top">

                    <span class="code">
                      ${esc(e.eps)}
                    </span>

                    <span class="${statusClass(e.status_execucao_eps)}">
                      ${esc(e.status_execucao_eps || "AGUARDANDO")}
                    </span>

                  </div>

                  <p>
                    <strong>Liberada:</strong>
                    ${e.liberada_para_eps ? "Sim" : "Não"}
                  </p>

                  <p>
                    <strong>Responsável EPS:</strong>
                    ${esc(e.responsavel_eps || "-")}
                  </p>

                  <p>
                    <strong>Ponto focal:</strong>
                    ${esc(e.ponto_focal_eps || "-")}
                  </p>

                  <p>
                    <strong>Go-Live:</strong>
                    ${e.go_live_aprovado ? "Aprovado" : "Não aprovado"}
                  </p>

                  <p>
                    <strong>Operação ativa:</strong>
                    ${e.operacao_ativada ? "Sim" : "Não"}
                  </p>

                </article>
              `
            )
            .join("")
          ||
          `<div class="notice">Nenhuma EPS vinculada.</div>`
        }

      </div>
    `;
  }

  if (
    tab === "kpis"
  ) {
    return tabela(
      [
        "KPI",
        "Principal",
        "Baseline",
        "Meta",
        "Unidade",
        "Frequência"
      ],
      d.kpis.map(
        k => [
          k.nome_kpi,
          k.kpi_principal ? "Sim" : "Não",
          k.baseline_valor ?? k.baseline_descricao ?? "-",
          k.meta_valor ?? k.meta_descricao ?? "-",
          k.unidade_medida,
          k.frequencia_reporte
        ]
      )
    );
  }

  if (
    tab === "performance"
  ) {
    return tabela(
      [
        "Data",
        "EPS",
        "Tentativas",
        "Contatos",
        "Vendas",
        "Matrículas",
        "Conversão",
        "Resultado"
      ],
      d.performance.map(
        p => [
          p.data_referencia,
          p.eps,
          p.tentativas_disparos ?? "-",
          p.contatos_alo ?? "-",
          p.vendas ?? "-",
          p.matriculas ?? "-",
          p.conversao ?? "-",
          p.resultado_periodo ?? "-"
        ]
      )
    );
  }

  if (
    tab === "gaps"
  ) {
    return tabela(
      [
        "EPS",
        "Categoria",
        "Gap",
        "Ação",
        "Responsável",
        "Prazo",
        "Status"
      ],
      d.gaps.map(
        g => [
          g.eps,
          g.categoria_gap ?? "-",
          g.gap ?? "-",
          g.acao ?? "-",
          g.responsavel ?? "-",
          g.prazo ?? "-",
          g.status_gap ?? "-"
        ]
      )
    );
  }

  if (
    tab === "evidencias"
  ) {
    return tabela(
      [
        "EPS",
        "Tipo",
        "Título",
        "Descrição",
        "Validada",
        "Data"
      ],
      d.evidencias.map(
        e => [
          e.eps,
          e.tipo_evidencia,
          e.titulo,
          e.descricao ?? "-",
          e.validada ? "Sim" : "Não",
          e.dt_evidencia
        ]
      )
    );
  }

  if (
    tab === "workflow"
  ) {
    return `
      <div class="timeline">

        ${
          d.workflow
            .map(
              w => `
                <div class="timeline-item">

                  <strong>
                    ${esc(w.status_novo || w.etapa_pop || "-")}
                  </strong>

                  <span>
                    ${esc(w.dt_evento || "-")}
                    ·
                    ${esc(w.origem || "-")}
                    ·
                    ${esc(w.usuario || "-")}
                  </span>

                  ${
                    w.observacao
                      ? `<p>${esc(w.observacao)}</p>`
                      : ""
                  }

                </div>
              `
            )
            .join("")
          ||
          `<div class="notice">Sem movimentações registradas.</div>`
        }

      </div>
    `;
  }

  if (
    tab === "acoes"
  ) {
    return acoesHtml(
      c,
      d.eps
    );
  }

  return "";
}

function tabela(
  headers,
  rows
) {
  if (
    !rows.length
  ) {
    return `
      <div class="notice">
        Nenhum registro encontrado.
      </div>
    `;
  }

  return `
    <div style="overflow:auto">

      <table>

        <thead>
          <tr>
            ${
              headers
                .map(
                  h =>
                    `<th>${esc(h)}</th>`
                )
                .join("")
            }
          </tr>
        </thead>

        <tbody>

          ${
            rows
              .map(
                row => `
                  <tr>
                    ${
                      row
                        .map(
                          value =>
                            `<td>${esc(value)}</td>`
                        )
                        .join("")
                    }
                  </tr>
                `
              )
              .join("")
          }

        </tbody>

      </table>

    </div>
  `;
}

function acoesHtml(
  campanha,
  eps
) {
  const liberadas =
    eps.filter(
      item =>
        item.liberada_para_eps
    );

  const todasFinalizadas =
    liberadas.length > 0 &&
    liberadas.every(
      item =>
        item.status_execucao_eps ===
        "EXECUCAO_FINALIZADA"
    );

  let conteudo = `
    <div class="action-focus">
      <div>
        <div class="eyebrow">STATUS ATUAL</div>
        <h2>${esc(statusLabel(campanha.status_campanha))}</h2>
        <p class="muted">
          O status muda automaticamente quando a ação abaixo é concluída.
        </p>
      </div>
    </div>
  `;

  if (
    campanha.status_campanha ===
    "CADASTRADA_PLANEJAMENTO"
  ) {
    conteudo += `
      <div class="panel action-panel">
        <div class="action-number">1</div>
        <div class="action-copy">
          <h2>Enviar para Comercial</h2>
          <p class="muted">
            O Planejamento concluiu o cadastro.
            A campanha seguirá para validação Comercial.
          </p>
          <button class="btn btn-lg" id="enviarComercial">
            Enviar para Comercial ›
          </button>
        </div>
      </div>
    `;
  }

  if (
    campanha.status_campanha ===
    "EM_VALIDACAO_COMERCIAL"
  ) {
    conteudo += `
      <div class="panel action-panel">
        <div class="action-number">2</div>
        <div class="action-copy">
          <h2>Validação Comercial</h2>

          <label class="confirm-card">
            <input id="vcConfirm" type="checkbox">
            <span>
              <strong>Confirmo a validação Comercial</strong>
              <small>
                Estratégia, mecânica, regras e mensuração
                estão adequadas para seguir.
              </small>
            </span>
          </label>

          <label>
            Observação
            <span class="optional-label">opcional</span>
          </label>

          <textarea id="vcObs"></textarea>

          <button class="btn btn-lg" id="validarComercial">
            Validar e avançar ›
          </button>
        </div>
      </div>
    `;
  }

  if (
    campanha.status_campanha ===
      "VALIDADA_COMERCIAL" ||
    campanha.status_campanha ===
      "PARCIALMENTE_LIBERADA_EPS"
  ) {
    const pendentes =
      eps.filter(
        item =>
          !item.liberada_para_eps
      );

    conteudo += `
      <div class="panel action-panel">
        <div class="action-number">3</div>
        <div class="action-copy">
          <h2>Liberar para EPS</h2>

          ${
            pendentes.length
              ? `
                <div class="eps-selector compact release-selector">
                  ${
                    pendentes
                      .map(
                        item => `
                          <label class="choice-card">
                            <input
                              class="eps-release"
                              type="checkbox"
                              value="${esc(item.eps)}"
                              checked
                            >
                            <strong>${esc(item.eps)}</strong>
                          </label>
                        `
                      )
                      .join("")
                  }
                </div>

                <label>
                  Mensagem para a EPS
                  <span class="optional-label">opcional</span>
                </label>

                <textarea id="relObs"></textarea>

                <button class="btn btn-lg" id="liberarEPS">
                  Liberar EPS selecionadas ›
                </button>
              `
              : `
                <div class="notice success">
                  Todas as EPS vinculadas já foram liberadas.
                </div>
              `
          }
        </div>
      </div>
    `;
  }

  if (
    campanha.status_campanha ===
    "ENVIADA_EPS" &&
    !todasFinalizadas
  ) {
    conteudo += `
      <div class="panel action-panel">
        <div class="action-number">4</div>
        <div class="action-copy">
          <h2>Execução com as EPS</h2>
          <p class="muted">
            Ainda existem EPS em preparação ou execução.
            O encerramento EduNova ficará disponível
            quando todas finalizarem.
          </p>

          <button class="btn secondary" id="irParaEPS">
            Acompanhar status das EPS
          </button>
        </div>
      </div>
    `;
  }

  if (
    campanha.status_campanha ===
    "ENVIADA_EPS" &&
    todasFinalizadas
  ) {
    conteudo += `
      <div class="panel action-panel closure-panel">
        <div class="action-number">5</div>

        <div class="action-copy">
          <div class="eyebrow">
            ENCERRAMENTO EDUNOVA
          </div>

          <h2>
            Fechar ciclo da campanha
          </h2>

          <p class="muted">
            Todas as EPS finalizaram.
            Registre a conclusão interna e a decisão
            para campanhas futuras.
          </p>

          <div class="grid2">

            <div class="full">
              <label>Decisão final *</label>

              <select id="edunovaDecisao">
                <option value="">Selecione</option>
                <option value="ENCERRAR">Encerrar</option>
                <option value="REPLICAR">Replicar</option>
                <option value="AJUSTAR_E_REPLICAR">Ajustar e replicar</option>
                <option value="NAO_REPLICAR">Não replicar</option>
              </select>
            </div>

            <div class="full">
              <label>Resumo do resultado *</label>
              <textarea
                id="edunovaResumo"
                placeholder="Ex.: A campanha atingiu o objetivo e apresentou melhor performance na VOXA."
              ></textarea>
            </div>

            <div class="full">
              <label>Principal aprendizado *</label>
              <textarea
                id="edunovaAprendizado"
                placeholder="O que devemos manter ou mudar em uma próxima campanha?"
              ></textarea>
            </div>

            <div class="full">
              <label class="confirm-card">
                <input id="edunovaConfirm" type="checkbox">
                <span>
                  <strong>Confirmo o encerramento interno</strong>
                  <small>
                    Os resultados das EPS foram revisados
                    e esta campanha pode ser encerrada.
                  </small>
                </span>
              </label>
            </div>

            <div class="full">
              <button class="btn btn-lg" id="encerrarEduNova">
                Encerrar campanha ›
              </button>
            </div>

          </div>
        </div>
      </div>
    `;
  }

  if (
    campanha.status_campanha ===
    "ENCERRADA_EDUNOVA"
  ) {
    conteudo += `
      <div class="empty-state">
        <div class="empty-icon">✓</div>
        <h2>Campanha encerrada</h2>
        <p>
          Não existem ações pendentes
          no workflow desta campanha.
        </p>
      </div>
    `;
  }

  conteudo += `
    <div id="acaoMsg"></div>
  `;

  return conteudo;
}

function bindTab(
  tab
) {
  if (
    tab !== "acoes"
  ) {
    return;
  }

  const c =
    campanhaAtual.campanha;

  const send =
    document.getElementById(
      "enviarComercial"
    );

  if (
    send
  ) {
    send.onclick =
      async () => {

        try {
          send.disabled = true;
          send.textContent = "Enviando...";

          await api(
            `/api/internal/campaigns/${encodeURIComponent(c.codigo_campanha)}/send-commercial`,
            {
              method:
                "POST"
            }
          );

          await atualizarDetalhe(
            c.codigo_campanha,
            "acoes"
          );

        } catch (e) {
          send.disabled = false;
          send.textContent = "Enviar para Comercial ›";

          mostrarAcaoErro(
            e.message
          );
        }
      };
  }

  const validar =
    document.getElementById(
      "validarComercial"
    );

  if (
    validar
  ) {
    validar.onclick =
      async () => {

        const confirmado =
          document.getElementById(
            "vcConfirm"
          ).checked;

        if (
          !confirmado
        ) {
          mostrarAcaoErro(
            "Marque a confirmação Comercial para avançar."
          );

          return;
        }

        const body = {
          estrategia_validada: true,
          mecanica_validada: true,
          oferta_argumento_validado: true,
          regras_elegibilidade_validadas: true,
          mensuracao_definida: true,
          atribuicao_definida: true,
          observacao:
            document.getElementById("vcObs").value || null
        };

        try {
          validar.disabled = true;
          validar.textContent = "Validando...";

          await api(
            `/api/internal/campaigns/${encodeURIComponent(c.codigo_campanha)}/commercial-validation`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify(body)
            }
          );

          await atualizarDetalhe(
            c.codigo_campanha,
            "acoes"
          );

        } catch (e) {
          validar.disabled = false;
          validar.textContent = "Validar e avançar ›";

          mostrarAcaoErro(
            e.message
          );
        }
      };
  }

  const liberar =
    document.getElementById(
      "liberarEPS"
    );

  if (
    liberar
  ) {
    liberar.onclick =
      async () => {

        const selecionadas = [
          ...document.querySelectorAll(
            ".eps-release:checked"
          )
        ].map(
          item =>
            item.value
        );

        if (
          !selecionadas.length
        ) {
          mostrarAcaoErro(
            "Selecione pelo menos uma EPS."
          );

          return;
        }

        const body = {
          eps:
            selecionadas,

          observacao_handoff:
            document
              .getElementById(
                "relObs"
              )
              .value ||
            null
        };

        try {
          liberar.disabled = true;
          liberar.textContent = "Liberando...";

          await api(
            `/api/internal/campaigns/${encodeURIComponent(c.codigo_campanha)}/release-eps`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify(body)
            }
          );

          await atualizarDetalhe(
            c.codigo_campanha,
            "eps"
          );

        } catch (e) {
          liberar.disabled = false;
          liberar.textContent = "Liberar EPS selecionadas ›";

          mostrarAcaoErro(
            e.message
          );
        }
      };
  }

  const irParaEPS =
    document.getElementById(
      "irParaEPS"
    );

  if (
    irParaEPS
  ) {
    irParaEPS.onclick =
      () =>
        renderDetalhe(
          "eps"
        );
  }


  const encerrarEduNova =
    document.getElementById(
      "encerrarEduNova"
    );

  if (
    encerrarEduNova
  ) {
    encerrarEduNova.onclick =
      async () => {

        const decisao =
          document
            .getElementById(
              "edunovaDecisao"
            )
            .value;

        const resumo =
          document
            .getElementById(
              "edunovaResumo"
            )
            .value
            .trim();

        const aprendizados =
          document
            .getElementById(
              "edunovaAprendizado"
            )
            .value
            .trim();

        const confirmado =
          document
            .getElementById(
              "edunovaConfirm"
            )
            .checked;

        if (
          !decisao
        ) {
          mostrarAcaoErro(
            "Selecione a decisão final."
          );
          return;
        }

        if (
          !resumo
        ) {
          mostrarAcaoErro(
            "Informe o resumo do resultado."
          );
          return;
        }

        if (
          !aprendizados
        ) {
          mostrarAcaoErro(
            "Informe o principal aprendizado."
          );
          return;
        }

        if (
          !confirmado
        ) {
          mostrarAcaoErro(
            "Confirme o encerramento interno."
          );
          return;
        }

        try {
          encerrarEduNova.disabled =
            true;

          encerrarEduNova.textContent =
            "Encerrando...";

          await api(
            `/api/internal/campaigns/${encodeURIComponent(c.codigo_campanha)}/close-edunova`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify({
                  decisao,
                  resumo,
                  aprendizados
                })
            }
          );

          await atualizarDetalhe(
            c.codigo_campanha,
            "acoes"
          );

        } catch (error) {
          encerrarEduNova.disabled =
            false;

          encerrarEduNova.textContent =
            "Encerrar campanha ›";

          mostrarAcaoErro(
            error.message
          );
        }
      };
  }

}
function mostrarAcaoErro(
  texto
) {
  const alvo =
    document.getElementById(
      "acaoMsg"
    );

  if (
    alvo
  ) {
    alvo.innerHTML = `
      <div class="notice error">
        ${esc(texto)}
      </div>
    `;
  }
}

async function atualizarDetalhe(
  codigo,
  tab
) {
  campanhaAtual =
    await api(
      `/api/internal/campaigns/${encodeURIComponent(codigo)}`
    );

  renderDetalhe(
    tab
  );

  carregar();
}



function abrirCadastroMVP() {
  window.campanhaV5 = {
    etapa: 1,
    dados: {
      tipo_acao: "COMERCIAL",
      produto: "GRADUACAO",
      supercanal: "HUNTER",
      modalidade: "PRESENCIAL",
      eps: [],
      nome_kpi: "Matrículas",
      unidade_medida: "MATRICULAS"
    }
  };

  document
    .getElementById("modalRoot")
    .innerHTML = `
      <div class="modal">
        <div class="modal-card cadastro-v5">

          <div class="modal-head">
            <div>
              <div class="eyebrow">
                NOVA CAMPANHA
              </div>

              <h2>
                Criar campanha
              </h2>

              <p class="muted">
                Cadastro rápido. O sistema cuida dos campos técnicos.
              </p>
            </div>

            <button
              class="close"
              id="fecharCadastro"
            >
              ×
            </button>
          </div>

          <div class="simple-progress">
            <div class="simple-step active" data-simple-step="1">
              <span>1</span>
              Campanha
            </div>

            <div class="simple-line"></div>

            <div class="simple-step" data-simple-step="2">
              <span>2</span>
              Execução
            </div>

            <div class="simple-line"></div>

            <div class="simple-step" data-simple-step="3">
              <span>3</span>
              Resultado
            </div>
          </div>

          <div id="cadastroBody"></div>

          <div id="cadastroMsg"></div>

          <div class="wizard-actions">
            <button
              class="btn secondary hidden"
              id="cadVoltar"
            >
              ← Voltar
            </button>

            <div style="flex:1"></div>

            <button
              class="btn"
              id="cadAvancar"
            >
              Continuar ›
            </button>

            <button
              class="btn hidden"
              id="cadCriar"
            >
              Criar campanha
            </button>
          </div>

        </div>
      </div>
    `;

  document.getElementById("fecharCadastro").onclick =
    () => document.getElementById("modalRoot").innerHTML = "";

  document.getElementById("cadVoltar").onclick =
    () => navegarCadastroV5(-1);

  document.getElementById("cadAvancar").onclick =
    () => navegarCadastroV5(1);

  document.getElementById("cadCriar").onclick =
    criarCampanhaV5;

  renderCadastroV5();
}


function cadastroV5() {
  return window.campanhaV5;
}


function valorCadastro(id) {
  const el =
    document.getElementById(id);

  return el
    ? el.value.trim()
    : "";
}


function numeroCadastro(id) {
  const valor =
    valorCadastro(id);

  return valor === ""
    ? null
    : Number(valor);
}


function salvarCadastroV5() {
  const s =
    cadastroV5();

  const d =
    s.dados;

  if (
    s.etapa === 1
  ) {
    d.nome_campanha =
      valorCadastro("cvNome");

    d.tipo_acao =
      valorCadastro("cvTipo");

    d.objetivo_campanha =
      valorCadastro("cvObjetivo");

    d.dt_inicio_prevista =
      valorCadastro("cvInicio");

    d.dt_fim_prevista =
      valorCadastro("cvFim");
  }

  if (
    s.etapa === 2
  ) {
    d.eps = [
      ...document.querySelectorAll(
        ".cv-eps:checked"
      )
    ].map(
      item =>
        item.value
    );

    d.produto =
      valorCadastro("cvProduto");

    d.supercanal =
      valorCadastro("cvSupercanal");

    d.frente_pos =
      valorCadastro("cvFrente") ||
      null;

    d.modalidade =
      valorCadastro("cvModalidade") ||
      null;

    d.outro_supercanal_descricao =
      valorCadastro("cvOutro") ||
      null;

    d.publico_alvo =
      valorCadastro("cvPublico");

    d.dimensao_estimada =
      numeroCadastro("cvVolume");

    d.responsavel_comercial =
      valorCadastro("cvResponsavel");

    d.detalhe_execucao =
      valorCadastro("cvDetalheExecucao");
  }

  if (
    s.etapa === 3
  ) {
    d.nome_kpi =
      valorCadastro("cvKpi");

    d.meta_valor =
      numeroCadastro("cvMeta");

    d.unidade_medida =
      valorCadastro("cvUnidadeOutro") ||
      unidadeDoKpi(
        d.nome_kpi
      );

    d.incentivo_gatilhos =
      valorCadastro("cvGatilho");

    d.incentivo_criterios =
      valorCadastro("cvCriterio");

    d.incentivo_condicao_pagamento =
      valorCadastro("cvPagamento");
  }
}


function unidadeDoKpi(kpi) {
  const mapa = {
    "Matrículas": "MATRICULAS",
    "Vendas": "VENDAS",
    "Conversão": "%",
    "ROL": "R$"
  };

  return mapa[kpi] || "UNIDADE";
}


function erroCadastroV5(texto) {
  const alvo =
    document.getElementById(
      "cadastroMsg"
    );

  alvo.innerHTML = `
    <div class="notice error">
      ${esc(texto)}
    </div>
  `;
}


function validarCadastroV5() {
  salvarCadastroV5();

  const s =
    cadastroV5();

  const d =
    s.dados;

  if (
    s.etapa === 1
  ) {
    if (
      !d.nome_campanha
    ) {
      erroCadastroV5(
        "Informe o nome da campanha."
      );
      return false;
    }

    if (
      !d.objetivo_campanha
    ) {
      erroCadastroV5(
        "Informe o objetivo da campanha."
      );
      return false;
    }

    if (
      !d.dt_inicio_prevista ||
      !d.dt_fim_prevista
    ) {
      erroCadastroV5(
        "Informe início e fim."
      );
      return false;
    }

    if (
      d.dt_inicio_prevista >
      d.dt_fim_prevista
    ) {
      erroCadastroV5(
        "A data inicial não pode ser posterior à final."
      );
      return false;
    }
  }

  if (
    s.etapa === 2
  ) {
    if (
      !d.eps.length
    ) {
      erroCadastroV5(
        "Selecione pelo menos uma EPS."
      );
      return false;
    }

    if (
      !d.publico_alvo
    ) {
      erroCadastroV5(
        "Informe o público ou segmento da campanha."
      );
      return false;
    }

    if (
      !d.dimensao_estimada ||
      d.dimensao_estimada <= 0
    ) {
      erroCadastroV5(
        "Informe um volume aproximado maior que zero."
      );
      return false;
    }

    if (
      !d.responsavel_comercial
    ) {
      erroCadastroV5(
        "Informe o responsável Comercial."
      );
      return false;
    }

    if (
      d.produto !==
        "POS_GRADUACAO" &&
      !d.modalidade
    ) {
      erroCadastroV5(
        "Selecione a modalidade."
      );
      return false;
    }

    if (
      d.produto ===
        "POS_GRADUACAO" &&
      !d.frente_pos
    ) {
      erroCadastroV5(
        "Selecione a frente de Pós-Graduação."
      );
      return false;
    }

    if (
      d.produto ===
        "POS_GRADUACAO" &&
      d.frente_pos ===
        "7_MINUTOS" &&
      !d.modalidade
    ) {
      erroCadastroV5(
        "7 Minutos exige modalidade."
      );
      return false;
    }

    if (
      d.supercanal ===
        "OUTROS" &&
      !d.outro_supercanal_descricao
    ) {
      erroCadastroV5(
        "Descreva o outro supercanal."
      );
      return false;
    }
  }

  if (
    s.etapa === 3 &&
    d.tipo_acao ===
      "INCENTIVO"
  ) {
    if (
      !d.incentivo_gatilhos ||
      !d.incentivo_criterios ||
      !d.incentivo_condicao_pagamento
    ) {
      erroCadastroV5(
        "Para incentivo, informe gatilho, critério e forma de entrega/pagamento."
      );
      return false;
    }
  }

  document.getElementById("cadastroMsg").innerHTML = "";
  return true;
}


function navegarCadastroV5(delta) {
  const s =
    cadastroV5();

  if (
    delta > 0 &&
    !validarCadastroV5()
  ) {
    return;
  }

  salvarCadastroV5();

  s.etapa =
    Math.max(
      1,
      Math.min(
        3,
        s.etapa + delta
      )
    );

  renderCadastroV5();
}


function renderCadastroV5() {
  const s =
    cadastroV5();

  document
    .querySelectorAll(
      "[data-simple-step]"
    )
    .forEach(
      el => {
        const etapa =
          Number(
            el.dataset.simpleStep
          );

        el.classList.toggle(
          "active",
          etapa === s.etapa
        );

        el.classList.toggle(
          "done",
          etapa < s.etapa
        );
      }
    );

  const body =
    document.getElementById(
      "cadastroBody"
    );

  if (
    s.etapa === 1
  ) {
    body.innerHTML =
      cadastroEtapa1V5();
  }

  if (
    s.etapa === 2
  ) {
    body.innerHTML =
      cadastroEtapa2V5();

    bindEscopoCadastroV5();
  }

  if (
    s.etapa === 3
  ) {
    body.innerHTML =
      cadastroEtapa3V5();
  }

  document
    .getElementById("cadVoltar")
    .classList
    .toggle(
      "hidden",
      s.etapa === 1
    );

  document
    .getElementById("cadAvancar")
    .classList
    .toggle(
      "hidden",
      s.etapa === 3
    );

  document
    .getElementById("cadCriar")
    .classList
    .toggle(
      "hidden",
      s.etapa !== 3
    );
}


function cadastroEtapa1V5() {
  const d =
    cadastroV5().dados;

  return `
    <div class="wizard-panel simple-panel">

      <div class="wizard-title">
        <span>1</span>
        O básico da campanha
      </div>

      <p class="wizard-help">
        São só as informações que identificam a ação.
      </p>

      <div class="grid2">

        <div class="full">
          <label>Nome da campanha *</label>
          <input
            id="cvNome"
            value="${esc(d.nome_campanha || "")}"
            placeholder="Ex.: Recuperação de inscritos sem pagamento"
          >
        </div>

        <div>
          <label>Tipo *</label>
          <select id="cvTipo">
            <option
              value="COMERCIAL"
              ${d.tipo_acao !== "INCENTIVO" ? "selected" : ""}
            >
              Ação comercial
            </option>

            <option
              value="INCENTIVO"
              ${d.tipo_acao === "INCENTIVO" ? "selected" : ""}
            >
              Incentivo
            </option>
          </select>
        </div>

        <div></div>

        <div class="full">
          <label>Objetivo *</label>
          <textarea
            id="cvObjetivo"
            placeholder="Ex.: Recuperar candidatos inscritos que ainda não concluíram a matrícula."
          >${esc(d.objetivo_campanha || "")}</textarea>
        </div>

        <div>
          <label>Início *</label>
          <input
            id="cvInicio"
            type="date"
            value="${esc(d.dt_inicio_prevista || "")}"
          >
        </div>

        <div>
          <label>Fim *</label>
          <input
            id="cvFim"
            type="date"
            value="${esc(d.dt_fim_prevista || "")}"
          >
        </div>

      </div>
    </div>
  `;
}


function cadastroEtapa2V5() {
  const d =
    cadastroV5().dados;

  return `
    <div class="wizard-panel simple-panel">

      <div class="wizard-title">
        <span>2</span>
        Quem vai executar?
      </div>

      <p class="wizard-help">
        Selecione a operação e o público. O restante pode ser refinado depois.
      </p>

      <div class="grid2">

        <div class="full">
          <label>EPS *</label>

          <div class="eps-selector compact">
            ${["VOXA", "PRISMA", "LUMEN"].map(
              eps => `
                <label class="choice-card">
                  <input
                    class="cv-eps"
                    type="checkbox"
                    value="${eps}"
                    ${d.eps?.includes(eps) ? "checked" : ""}
                  >
                  <strong>${eps}</strong>
                </label>
              `
            ).join("")}
          </div>
        </div>

        <div>
          <label>Produto *</label>
          <select id="cvProduto">
            <option value="GRADUACAO" ${d.produto === "GRADUACAO" ? "selected" : ""}>Graduação</option>
            <option value="POS_GRADUACAO" ${d.produto === "POS_GRADUACAO" ? "selected" : ""}>Pós-Graduação</option>
            <option value="TECNICO" ${d.produto === "TECNICO" ? "selected" : ""}>Técnico</option>
            <option value="PROFISSIONALIZANTES" ${d.produto === "PROFISSIONALIZANTES" ? "selected" : ""}>Profissionalizantes</option>
          </select>
        </div>

        <div>
          <label>Supercanal *</label>
          <select id="cvSupercanal">
            <option value="MIDIA" ${d.supercanal === "MIDIA" ? "selected" : ""}>Mídia</option>
            <option value="HUNTER" ${d.supercanal === "HUNTER" ? "selected" : ""}>Hunter</option>
            <option value="NOVOS_CANAIS" ${d.supercanal === "NOVOS_CANAIS" ? "selected" : ""}>Novos Canais</option>
            <option value="OUTROS" ${d.supercanal === "OUTROS" ? "selected" : ""}>Outros</option>
          </select>
        </div>

        <div
          id="cvFrenteWrap"
          class="${d.produto === "POS_GRADUACAO" ? "" : "hidden"}"
        >
          <label>Frente Pós *</label>
          <select id="cvFrente">
            <option value="">Selecione</option>
            <option value="RECEPTIVO" ${d.frente_pos === "RECEPTIVO" ? "selected" : ""}>Receptivo</option>
            <option value="EGRESSOS" ${d.frente_pos === "EGRESSOS" ? "selected" : ""}>Egressos</option>
            <option value="7_MINUTOS" ${d.frente_pos === "7_MINUTOS" ? "selected" : ""}>7 Minutos</option>
          </select>
        </div>

        <div>
          <label id="cvModalidadeLabel">Modalidade *</label>
          <select id="cvModalidade">
            <option value="">Selecione</option>
            <option value="PRESENCIAL" ${d.modalidade === "PRESENCIAL" ? "selected" : ""}>Presencial</option>
            <option value="EAD" ${d.modalidade === "EAD" ? "selected" : ""}>EAD</option>
          </select>
        </div>

        <div
          id="cvOutroWrap"
          class="full ${d.supercanal === "OUTROS" ? "" : "hidden"}"
        >
          <label>Qual outro supercanal? *</label>
          <input
            id="cvOutro"
            value="${esc(d.outro_supercanal_descricao || "")}"
          >
        </div>

        <div class="full">
          <label>Público / segmento *</label>
          <input
            id="cvPublico"
            value="${esc(d.publico_alvo || "")}"
            placeholder="Ex.: Inscritos de Graduação Presencial sem pagamento"
          >
        </div>

        <div>
          <label>Volume aproximado *</label>
          <input
            id="cvVolume"
            type="number"
            min="1"
            value="${esc(d.dimensao_estimada || "")}"
            placeholder="Ex.: 2500"
          >
        </div>

        <div>
          <label>Responsável Comercial *</label>
          <input
            id="cvResponsavel"
            type="email"
            value="${esc(d.responsavel_comercial || "")}"
            placeholder="nome@edunova.com.br"
          >
        </div>

        <details class="full advanced-details">
          <summary>Detalhes adicionais <span>opcional</span></summary>

          <div class="advanced-body">
            <label>Alguma orientação específica para a execução?</label>
            <textarea
              id="cvDetalheExecucao"
              placeholder="Pode deixar em branco."
            >${esc(d.detalhe_execucao || "")}</textarea>
          </div>
        </details>

      </div>
    </div>
  `;
}


function bindEscopoCadastroV5() {
  const produto =
    document.getElementById(
      "cvProduto"
    );

  const supercanal =
    document.getElementById(
      "cvSupercanal"
    );

  const frente =
    document.getElementById(
      "cvFrente"
    );

  const atualizar =
    () => {
      const pos =
        produto.value ===
        "POS_GRADUACAO";

      document
        .getElementById(
          "cvFrenteWrap"
        )
        .classList
        .toggle(
          "hidden",
          !pos
        );

      document
        .getElementById(
          "cvOutroWrap"
        )
        .classList
        .toggle(
          "hidden",
          supercanal.value !==
            "OUTROS"
        );

      const modalidadeObrigatoria =
        !pos ||
        frente.value ===
          "7_MINUTOS";

      document
        .getElementById(
          "cvModalidadeLabel"
        )
        .textContent =
          modalidadeObrigatoria
            ? "Modalidade *"
            : "Modalidade";
    };

  produto.onchange =
    atualizar;

  supercanal.onchange =
    atualizar;

  frente.onchange =
    atualizar;

  atualizar();
}


function cadastroEtapa3V5() {
  const d =
    cadastroV5().dados;

  const incentivo =
    d.tipo_acao ===
    "INCENTIVO";

  return `
    <div class="wizard-panel simple-panel">

      <div class="wizard-title">
        <span>3</span>
        Como vamos medir?
      </div>

      <p class="wizard-help">
        Escolha um indicador principal. A meta numérica pode ficar em branco.
      </p>

      <div class="grid2">

        <div>
          <label>Indicador principal *</label>
          <select id="cvKpi">
            ${["Matrículas", "Vendas", "Conversão", "ROL", "Outro"].map(
              item => `
                <option
                  value="${item}"
                  ${d.nome_kpi === item ? "selected" : ""}
                >
                  ${item}
                </option>
              `
            ).join("")}
          </select>
        </div>

        <div>
          <label>Meta <span class="optional-label">opcional</span></label>
          <input
            id="cvMeta"
            type="number"
            step="any"
            value="${esc(d.meta_valor ?? "")}"
            placeholder="Ex.: 350"
          >
        </div>

        <div class="full">
          <label>
            Unidade personalizada
            <span class="optional-label">somente se escolher Outro</span>
          </label>

          <input
            id="cvUnidadeOutro"
            value="${d.nome_kpi === "Outro" ? esc(d.unidade_medida || "") : ""}"
            placeholder="Ex.: leads qualificados"
          >
        </div>

        ${
          incentivo
            ? `
              <div class="full">
                <div class="notice">
                  Incentivo exige somente três definições adicionais.
                </div>
              </div>

              <div class="full">
                <label>Quando o incentivo é conquistado? *</label>
                <input
                  id="cvGatilho"
                  value="${esc(d.incentivo_gatilhos || "")}"
                  placeholder="Ex.: Atingir 100% da meta"
                >
              </div>

              <div>
                <label>Quem participa? *</label>
                <input
                  id="cvCriterio"
                  value="${esc(d.incentivo_criterios || "")}"
                >
              </div>

              <div>
                <label>Como será entregue? *</label>
                <input
                  id="cvPagamento"
                  value="${esc(d.incentivo_condicao_pagamento || "")}"
                  placeholder="Ex.: Premiação após validação do fechamento"
                >
              </div>
            `
            : `
              <div class="hidden">
                <input id="cvGatilho">
                <input id="cvCriterio">
                <input id="cvPagamento">
              </div>
            `
        }

      </div>

      <div class="review-strip">
        <strong>Resumo</strong>
        <span>${esc(d.nome_campanha || "")}</span>
        <span>${esc((d.eps || []).join(", "))}</span>
        <span>${esc(d.produto || "")}</span>
      </div>
    </div>
  `;
}


function montarPayloadV5() {
  salvarCadastroV5();

  const d =
    cadastroV5().dados;

  const orientacao =
    d.detalhe_execucao ||
    "Execução orientada pelo objetivo, público e escopo definidos na campanha.";

  const unidade =
    d.unidade_medida ||
    unidadeDoKpi(
      d.nome_kpi
    );

  const metaDescricao =
    d.meta_valor !== null &&
    d.meta_valor !== undefined
      ? `Atingir ${d.meta_valor} ${unidade}.`
      : `Acompanhar a evolução de ${d.nome_kpi}.`;

  return {
    nome_campanha:
      d.nome_campanha,

    tipo_acao:
      d.tipo_acao,

    oportunidade_problema:
      d.objetivo_campanha,

    fonte_oportunidade:
      "Planejamento Comercial",

    indicador_evidencia_oportunidade:
      d.objetivo_campanha,

    etapa_funil_alvo:
      null,

    publico_alvo:
      d.publico_alvo,

    segmentacao:
      d.publico_alvo,

    criterio_elegibilidade:
      `Registros aderentes ao público definido: ${d.publico_alvo}`,

    criterio_exclusao:
      "Registros fora do público definido, inelegíveis ou já tratados conforme a regra da campanha.",

    dimensao_estimada:
      d.dimensao_estimada,

    estrategia:
      orientacao,

    mecanica:
      orientacao,

    oferta_beneficio:
      d.tipo_acao === "INCENTIVO"
        ? "Benefício conforme regra do incentivo."
        : "Condição comercial vigente conforme a estratégia da campanha.",

    argumento_comercial:
      "Abordagem alinhada ao objetivo e ao público da campanha.",

    regras_comerciais:
      "Aplicar as regras comerciais vigentes e as condições formalizadas para a campanha.",

    condicoes_especificas:
      null,

    canais_possiveis:
      "Ligação, WhatsApp e demais canais disponíveis na operação.",

    incentivo_gatilhos:
      d.tipo_acao === "INCENTIVO"
        ? d.incentivo_gatilhos
        : null,

    incentivo_criterios:
      d.tipo_acao === "INCENTIVO"
        ? d.incentivo_criterios
        : null,

    incentivo_condicao_pagamento:
      d.tipo_acao === "INCENTIVO"
        ? d.incentivo_condicao_pagamento
        : null,

    objetivo_campanha:
      d.objetivo_campanha,

    resultado_esperado:
      metaDescricao,

    dt_inicio_prevista:
      d.dt_inicio_prevista,

    dt_fim_prevista:
      d.dt_fim_prevista,

    responsavel_comercial:
      d.responsavel_comercial,

    rito_followup:
      "SEMANAL",

    canal_tratativa_desvios:
      "Central de Campanhas",

    criterio_encerramento:
      "Fim da vigência, conclusão da execução pelas EPS e consolidação dos resultados.",

    evidencias_obrigatorias:
      "Resultado final, principais gaps, ações realizadas e aprendizados.",

    eps:
      d.eps,

    escopos: [
      {
        produto:
          d.produto,

        frente_pos:
          d.produto ===
            "POS_GRADUACAO"
            ? d.frente_pos
            : null,

        supercanal:
          d.supercanal,

        outro_supercanal_descricao:
          d.supercanal ===
            "OUTROS"
            ? d.outro_supercanal_descricao
            : null,

        modalidade:
          d.modalidade
      }
    ],

    kpis: [
      {
        nome_kpi:
          d.nome_kpi,

        descricao_kpi:
          `Indicador principal da campanha: ${d.nome_kpi}.`,

        principal:
          true,

        baseline_tipo:
          "SEM_BASELINE",

        baseline_descricao:
          "Baseline não informado no cadastro simplificado.",

        baseline_valor:
          null,

        meta_descricao:
          metaDescricao,

        meta_valor:
          d.meta_valor,

        unidade_medida:
          unidade,

        regra_atribuicao:
          "Considerar resultados registrados e validados no contexto desta campanha.",

        frequencia_reporte:
          "SEMANAL",

        ritmo_esperado:
          "Acompanhamento durante a vigência da campanha."
      }
    ]
  };
}


async function criarCampanhaV5() {
  if (
    !validarCadastroV5()
  ) {
    return;
  }

  const payload =
    montarPayloadV5();

  const botao =
    document.getElementById(
      "cadCriar"
    );

  try {
    botao.disabled = true;
    botao.textContent = "Criando...";

    document.getElementById("cadastroMsg").innerHTML = `
      <div class="notice">
        Validando e criando a campanha...
      </div>
    `;

    await api(
      "/api/internal/campaigns/validate",
      {
        method:
          "POST",

        headers: {
          "Content-Type":
            "application/json"
        },

        body:
          JSON.stringify(
            payload
          )
      }
    );

    const resposta =
      await api(
        "/api/internal/campaigns",
        {
          method:
            "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify(
              payload
          )
        }
      );

    const codigo =
      resposta
        .campanha
        ?.codigo_campanha ||
      "Campanha";

    document.getElementById("cadastroMsg").innerHTML = `
      <div class="notice success">
        ${esc(codigo)} criada com sucesso.
      </div>
    `;

    setTimeout(
      async () => {
        document
          .getElementById(
            "modalRoot"
          )
          .innerHTML = "";

        await carregar();
      },
      900
    );

  } catch (e) {
    botao.disabled = false;
    botao.textContent = "Criar campanha";

    erroCadastroV5(
      e.message
    );
  }
}


function w() {
  return window.campanhaWizard;
}


function valor(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}


function numero(id) {
  const v = valor(id);
  return v === "" ? null : Number(v);
}


function salvarWizard() {
  const s = w();
  const d = s.dados;

  if (s.etapa === 1) {
    d.nome_campanha = valor("wNome");
    d.tipo_acao = valor("wTipo");
    d.objetivo_campanha = valor("wObjetivo");
    d.resultado_esperado = valor("wResultado");
    d.dt_inicio_prevista = valor("wInicio");
    d.dt_fim_prevista = valor("wFim");
  }

  if (s.etapa === 2) {
    d.oportunidade_problema = valor("wOportunidade");
    d.publico_alvo = valor("wPublico");
    d.dimensao_estimada = numero("wVolume");
    d.responsavel_comercial = valor("wResponsavel");
    d.estrategia = valor("wEstrategia");
    d.mecanica = valor("wMecanica");
    d.canais_possiveis = valor("wCanais");

    d.eps = [...document.querySelectorAll(".w-eps:checked")]
      .map(el => el.value);

    d.produto = valor("wProduto");
    d.supercanal = valor("wSupercanal");
    d.frente_pos = valor("wFrente") || null;
    d.modalidade = valor("wModalidade") || null;
    d.outro_supercanal_descricao = valor("wOutro") || null;
  }

  if (s.etapa === 3) {
    d.nome_kpi = valor("wKpi");
    d.unidade_medida = valor("wUnidade");
    d.baseline_valor = numero("wBaseline");
    d.meta_valor = numero("wMeta");

    d.incentivo_gatilhos = valor("wGatilhos");
    d.incentivo_criterios = valor("wCriterios");
    d.incentivo_condicao_pagamento = valor("wPagamento");
  }
}


function erroWizard(texto) {
  document.getElementById("cadastroMsg").innerHTML =
    `<div class="notice error">${esc(texto)}</div>`;
}


function limparErroWizard() {
  document.getElementById("cadastroMsg").innerHTML = "";
}


function validarWizard() {
  salvarWizard();

  const s = w();
  const d = s.dados;

  if (s.etapa === 1) {
    if (!d.nome_campanha) return erroWizard("Informe o nome da campanha."), false;
    if (!d.objetivo_campanha) return erroWizard("Explique o objetivo da campanha."), false;
    if (!d.resultado_esperado) return erroWizard("Informe o resultado esperado."), false;
    if (!d.dt_inicio_prevista || !d.dt_fim_prevista) return erroWizard("Informe início e fim da campanha."), false;
    if (d.dt_inicio_prevista > d.dt_fim_prevista) return erroWizard("A data inicial não pode ser posterior à final."), false;
  }

  if (s.etapa === 2) {
    if (!d.oportunidade_problema) return erroWizard("Explique o que motivou a campanha."), false;
    if (!d.publico_alvo) return erroWizard("Informe quem será impactado."), false;
    if (!d.dimensao_estimada || d.dimensao_estimada <= 0) return erroWizard("Informe um volume estimado maior que zero."), false;
    if (!d.responsavel_comercial) return erroWizard("Informe o responsável Comercial."), false;
    if (!d.eps.length) return erroWizard("Selecione pelo menos uma EPS."), false;
    if (!d.estrategia) return erroWizard("Informe a estratégia."), false;
    if (!d.mecanica) return erroWizard("Explique como a campanha funcionará."), false;
    if (!d.canais_possiveis) return erroWizard("Informe os canais de ativação."), false;

    if (d.produto !== "POS_GRADUACAO" && !d.modalidade)
      return erroWizard("Selecione a modalidade."), false;

    if (d.produto === "POS_GRADUACAO" && !d.frente_pos)
      return erroWizard("Selecione a frente de Pós-Graduação."), false;

    if (d.produto === "POS_GRADUACAO" && d.frente_pos === "7_MINUTOS" && !d.modalidade)
      return erroWizard("7 Minutos exige modalidade."), false;

    if (d.supercanal === "OUTROS" && !d.outro_supercanal_descricao)
      return erroWizard("Descreva o outro supercanal."), false;
  }

  if (s.etapa === 3) {
    if (!d.nome_kpi) return erroWizard("Informe o principal indicador de sucesso."), false;
    if (!d.unidade_medida) return erroWizard("Informe como o indicador será medido."), false;

    if (d.tipo_acao === "INCENTIVO") {
      if (!d.incentivo_gatilhos) return erroWizard("Informe o gatilho do incentivo."), false;
      if (!d.incentivo_criterios) return erroWizard("Informe os critérios do incentivo."), false;
      if (!d.incentivo_condicao_pagamento) return erroWizard("Informe como o incentivo será entregue/pago."), false;
    }
  }

  limparErroWizard();
  return true;
}


function navegarWizard(delta) {
  const s = w();

  if (delta > 0 && !validarWizard()) return;

  salvarWizard();
  s.etapa = Math.max(1, Math.min(4, s.etapa + delta));
  renderWizard();
}


function renderWizard() {
  const s = w();

  document.querySelectorAll("[data-wstep]").forEach(el => {
    const n = Number(el.dataset.wstep);
    el.classList.toggle("active", n === s.etapa);
    el.classList.toggle("done", n < s.etapa);
  });

  const body = document.getElementById("wizardBody");

  if (s.etapa === 1) body.innerHTML = etapa1();
  if (s.etapa === 2) body.innerHTML = etapa2();
  if (s.etapa === 3) body.innerHTML = etapa3();
  if (s.etapa === 4) body.innerHTML = etapa4();

  document.getElementById("wizVoltar").classList.toggle("hidden", s.etapa === 1);
  document.getElementById("wizAvancar").classList.toggle("hidden", s.etapa === 4);
  document.getElementById("wizCriar").classList.toggle("hidden", s.etapa !== 4);

  if (s.etapa === 2) bindEscopoWizard();
}


function etapa1() {
  const d = w().dados;

  return `
    <div class="wizard-panel">
      <div class="wizard-title"><span>1</span> O que vamos fazer?</div>
      <p class="wizard-help">Comece pela ideia da campanha. Sem linguagem técnica.</p>

      <div class="grid2">
        <div class="full">
          <label>Nome da campanha *</label>
          <input id="wNome" value="${esc(d.nome_campanha||"")}" placeholder="Ex.: Recuperação de inscritos sem pagamento">
        </div>

        <div>
          <label>Tipo *</label>
          <select id="wTipo">
            <option value="COMERCIAL" ${d.tipo_acao!=="INCENTIVO"?"selected":""}>Ação comercial</option>
            <option value="INCENTIVO" ${d.tipo_acao==="INCENTIVO"?"selected":""}>Campanha de incentivo</option>
          </select>
          <small class="field-help">Comercial atua com candidatos. Incentivo estimula a operação.</small>
        </div>

        <div></div>

        <div class="full">
          <label>Qual é o objetivo? *</label>
          <textarea id="wObjetivo" placeholder="Ex.: Recuperar candidatos inscritos que ainda não concluíram a matrícula.">${esc(d.objetivo_campanha||"")}</textarea>
        </div>

        <div class="full">
          <label>Que resultado esperamos? *</label>
          <textarea id="wResultado" placeholder="Ex.: Aumentar matrículas e reduzir pendências.">${esc(d.resultado_esperado||"")}</textarea>
        </div>

        <div>
          <label>Início *</label>
          <input id="wInicio" type="date" value="${esc(d.dt_inicio_prevista||"")}">
        </div>

        <div>
          <label>Fim *</label>
          <input id="wFim" type="date" value="${esc(d.dt_fim_prevista||"")}">
        </div>
      </div>
    </div>
  `;
}


function etapa2() {
  const d = w().dados;

  return `
    <div class="wizard-panel">
      <div class="wizard-title"><span>2</span> Quem executa e como?</div>
      <p class="wizard-help">Defina público, EPS e escopo principal.</p>

      <div class="grid2">
        <div class="full">
          <label>O que motivou a campanha? *</label>
          <textarea id="wOportunidade" placeholder="Ex.: Alto volume de candidatos parados após a inscrição.">${esc(d.oportunidade_problema||"")}</textarea>
        </div>

        <div class="full">
          <label>Quem será impactado? *</label>
          <textarea id="wPublico" placeholder="Ex.: Inscritos de Graduação Presencial sem pagamento.">${esc(d.publico_alvo||"")}</textarea>
        </div>

        <div>
          <label>Volume estimado *</label>
          <input id="wVolume" type="number" min="1" value="${esc(d.dimensao_estimada||"")}" placeholder="Pode ser aproximado">
        </div>

        <div>
          <label>Responsável Comercial *</label>
          <input id="wResponsavel" type="email" value="${esc(d.responsavel_comercial||"")}" placeholder="nome@edunova.com.br">
        </div>

        <div class="full">
          <label>EPS que participarão *</label>
          <div class="eps-selector compact">
            ${["VOXA","PRISMA","LUMEN"].map(e=>`
              <label class="choice-card">
                <input class="w-eps" type="checkbox" value="${e}" ${d.eps?.includes(e)?"checked":""}>
                <strong>${e}</strong>
              </label>
            `).join("")}
          </div>
        </div>

        <div>
          <label>Produto *</label>
          <select id="wProduto">
            <option value="GRADUACAO" ${d.produto==="GRADUACAO"?"selected":""}>Graduação</option>
            <option value="POS_GRADUACAO" ${d.produto==="POS_GRADUACAO"?"selected":""}>Pós-Graduação</option>
            <option value="TECNICO" ${d.produto==="TECNICO"?"selected":""}>Técnico</option>
            <option value="PROFISSIONALIZANTES" ${d.produto==="PROFISSIONALIZANTES"?"selected":""}>Profissionalizantes</option>
          </select>
        </div>

        <div>
          <label>Supercanal *</label>
          <select id="wSupercanal">
            <option value="MIDIA" ${d.supercanal==="MIDIA"?"selected":""}>Mídia</option>
            <option value="HUNTER" ${d.supercanal==="HUNTER"?"selected":""}>Hunter</option>
            <option value="NOVOS_CANAIS" ${d.supercanal==="NOVOS_CANAIS"?"selected":""}>Novos Canais</option>
            <option value="OUTROS" ${d.supercanal==="OUTROS"?"selected":""}>Outros</option>
          </select>
        </div>

        <div id="wFrenteWrap" class="${d.produto==="POS_GRADUACAO"?"":"hidden"}">
          <label>Frente Pós *</label>
          <select id="wFrente">
            <option value="">Selecione</option>
            <option value="RECEPTIVO" ${d.frente_pos==="RECEPTIVO"?"selected":""}>Receptivo</option>
            <option value="EGRESSOS" ${d.frente_pos==="EGRESSOS"?"selected":""}>Egressos</option>
            <option value="7_MINUTOS" ${d.frente_pos==="7_MINUTOS"?"selected":""}>7 Minutos</option>
          </select>
        </div>

        <div>
          <label id="wModalidadeLabel">Modalidade *</label>
          <select id="wModalidade">
            <option value="">Selecione</option>
            <option value="PRESENCIAL" ${d.modalidade==="PRESENCIAL"?"selected":""}>Presencial</option>
            <option value="EAD" ${d.modalidade==="EAD"?"selected":""}>EAD</option>
          </select>
        </div>

        <div id="wOutroWrap" class="full ${d.supercanal==="OUTROS"?"":"hidden"}">
          <label>Qual outro supercanal? *</label>
          <input id="wOutro" value="${esc(d.outro_supercanal_descricao||"")}">
        </div>

        <div class="full">
          <label>Qual será a estratégia? *</label>
          <textarea id="wEstrategia" placeholder="Ex.: Priorizar os contatos mais recentes e atuar com a condição vigente.">${esc(d.estrategia||"")}</textarea>
        </div>

        <div class="full">
          <label>Como a campanha vai funcionar? *</label>
          <textarea id="wMecanica" placeholder="Ex.: A EPS recebe o público, realiza tentativas durante 5 dias e reporta a evolução.">${esc(d.mecanica||"")}</textarea>
        </div>

        <div class="full">
          <label>Canais de ativação *</label>
          <input id="wCanais" value="${esc(d.canais_possiveis||"")}" placeholder="Ex.: Ligação e WhatsApp">
        </div>
      </div>
    </div>
  `;
}


function bindEscopoWizard() {
  const produto = document.getElementById("wProduto");
  const supercanal = document.getElementById("wSupercanal");
  const frente = document.getElementById("wFrente");

  const atualizar = () => {
    const pos = produto.value === "POS_GRADUACAO";

    document.getElementById("wFrenteWrap").classList.toggle("hidden", !pos);
    document.getElementById("wOutroWrap").classList.toggle("hidden", supercanal.value !== "OUTROS");

    const obrigatoria = !pos || frente.value === "7_MINUTOS";
    document.getElementById("wModalidadeLabel").textContent = obrigatoria ? "Modalidade *" : "Modalidade";
  };

  produto.onchange = atualizar;
  supercanal.onchange = atualizar;
  frente.onchange = atualizar;
  atualizar();
}


function etapa3() {
  const d = w().dados;
  const incentivo = d.tipo_acao === "INCENTIVO";

  return `
    <div class="wizard-panel">
      <div class="wizard-title"><span>3</span> Como saberemos se deu certo?</div>
      <p class="wizard-help">Defina apenas o indicador principal. O sistema completa as regras técnicas.</p>

      <div class="grid2">
        <div>
          <label>Indicador principal *</label>
          <input id="wKpi" value="${esc(d.nome_kpi||"")}" placeholder="Ex.: Matrículas">
        </div>

        <div>
          <label>Como é medido? *</label>
          <input id="wUnidade" value="${esc(d.unidade_medida||"")}" placeholder="Ex.: Matrículas, %, R$">
        </div>

        <div>
          <label>Referência atual</label>
          <input id="wBaseline" type="number" step="any" value="${esc(d.baseline_valor??"")}" placeholder="Opcional">
        </div>

        <div>
          <label>Meta</label>
          <input id="wMeta" type="number" step="any" value="${esc(d.meta_valor??"")}" placeholder="Opcional">
        </div>

        ${incentivo?`
          <div class="full"><div class="notice">Como é incentivo, precisamos de 3 definições adicionais.</div></div>

          <div class="full">
            <label>O que dispara o incentivo? *</label>
            <textarea id="wGatilhos">${esc(d.incentivo_gatilhos||"")}</textarea>
          </div>

          <div>
            <label>Quem tem direito? *</label>
            <textarea id="wCriterios">${esc(d.incentivo_criterios||"")}</textarea>
          </div>

          <div>
            <label>Como será entregue/pago? *</label>
            <textarea id="wPagamento">${esc(d.incentivo_condicao_pagamento||"")}</textarea>
          </div>
        `:`
          <div class="hidden">
            <textarea id="wGatilhos"></textarea>
            <textarea id="wCriterios"></textarea>
            <textarea id="wPagamento"></textarea>
          </div>
        `}
      </div>
    </div>
  `;
}


function etapa4() {
  const d = w().dados;

  return `
    <div class="wizard-panel">
      <div class="wizard-title"><span>4</span> Revise e crie</div>
      <p class="wizard-help">Confira as informações principais antes de gravar.</p>

      <div class="review-grid">
        <div class="review-card"><span>Campanha</span><strong>${esc(d.nome_campanha)}</strong><p>${esc(d.objetivo_campanha)}</p></div>
        <div class="review-card"><span>Vigência</span><strong>${esc(d.dt_inicio_prevista)} › ${esc(d.dt_fim_prevista)}</strong></div>
        <div class="review-card"><span>EPS</span><strong>${esc((d.eps||[]).join(", "))}</strong></div>
        <div class="review-card"><span>Escopo</span><strong>${esc(d.produto)}</strong><p>${esc(d.supercanal)}${d.modalidade?" · "+esc(d.modalidade):""}</p></div>
        <div class="review-card"><span>Indicador</span><strong>${esc(d.nome_kpi)}</strong><p>${d.meta_valor!==null&&d.meta_valor!==undefined?`Meta: ${esc(d.meta_valor)} ${esc(d.unidade_medida)}`:"Meta numérica opcional"}</p></div>
        <div class="review-card"><span>Responsável Comercial</span><strong>${esc(d.responsavel_comercial)}</strong></div>
      </div>

      <div class="notice">
        Critérios técnicos, rito de acompanhamento, atribuição do KPI e evidências mínimas serão preenchidos automaticamente.
      </div>
    </div>
  `;
}


function montarPayloadWizard() {
  const d = w().dados;

  const metaDescricao =
    d.meta_valor !== null && d.meta_valor !== undefined
      ? `Atingir ${d.meta_valor} ${d.unidade_medida}.`
      : `Acompanhar evolução de ${d.nome_kpi}.`;

  const baselineDescricao =
    d.baseline_valor !== null && d.baseline_valor !== undefined
      ? `Referência atual: ${d.baseline_valor} ${d.unidade_medida}.`
      : "Sem baseline numérico informado.";

  return {
    nome_campanha: d.nome_campanha,
    tipo_acao: d.tipo_acao || "COMERCIAL",

    oportunidade_problema: d.oportunidade_problema,
    fonte_oportunidade: "Planejamento Comercial",
    indicador_evidencia_oportunidade: d.oportunidade_problema,
    etapa_funil_alvo: null,

    publico_alvo: d.publico_alvo,
    segmentacao: d.publico_alvo,
    criterio_elegibilidade: `Registros aderentes ao público-alvo: ${d.publico_alvo}`,
    criterio_exclusao: "Registros fora do público-alvo, inelegíveis ou já tratados conforme regra da campanha.",
    dimensao_estimada: d.dimensao_estimada,

    estrategia: d.estrategia,
    mecanica: d.mecanica,
    oferta_beneficio: d.tipo_acao === "INCENTIVO"
      ? "Benefício definido nas regras do incentivo."
      : "Conforme estratégia e condições comerciais vigentes.",
    argumento_comercial: "Abordagem alinhada ao objetivo, público e estratégia da campanha.",
    regras_comerciais: "Aplicar as regras comerciais vigentes e as condições formalizadas para a campanha.",
    condicoes_especificas: null,
    canais_possiveis: d.canais_possiveis,

    incentivo_gatilhos: d.tipo_acao === "INCENTIVO" ? d.incentivo_gatilhos : null,
    incentivo_criterios: d.tipo_acao === "INCENTIVO" ? d.incentivo_criterios : null,
    incentivo_condicao_pagamento: d.tipo_acao === "INCENTIVO" ? d.incentivo_condicao_pagamento : null,

    objetivo_campanha: d.objetivo_campanha,
    resultado_esperado: d.resultado_esperado,

    dt_inicio_prevista: d.dt_inicio_prevista,
    dt_fim_prevista: d.dt_fim_prevista,

    responsavel_comercial: d.responsavel_comercial,
    rito_followup: "SEMANAL",
    canal_tratativa_desvios: "Central de Campanhas",
    criterio_encerramento: "Fim da vigência, conclusão da execução pelas EPS e consolidação dos resultados.",
    evidencias_obrigatorias: "Resultado final, principais gaps, ações realizadas e aprendizados.",

    eps: d.eps,

    escopos: [{
      produto: d.produto,
      frente_pos: d.produto === "POS_GRADUACAO" ? d.frente_pos : null,
      supercanal: d.supercanal,
      outro_supercanal_descricao: d.supercanal === "OUTROS" ? d.outro_supercanal_descricao : null,
      modalidade: d.modalidade
    }],

    kpis: [{
      nome_kpi: d.nome_kpi,
      descricao_kpi: `Indicador principal de sucesso da campanha: ${d.nome_kpi}.`,
      principal: true,
      baseline_tipo: "REFERENCIA",
      baseline_descricao: baselineDescricao,
      baseline_valor: d.baseline_valor,
      meta_descricao: metaDescricao,
      meta_valor: d.meta_valor,
      unidade_medida: d.unidade_medida,
      regra_atribuicao: "Considerar resultados registrados e validados no contexto desta campanha.",
      frequencia_reporte: "SEMANAL",
      ritmo_esperado: "Evolução acompanhada durante a vigência da campanha."
    }]
  };
}


async function criarCampanhaWizard() {
  const payload = montarPayloadWizard();

  try {
    document.getElementById("cadastroMsg").innerHTML =
      `<div class="notice">Validando informações...</div>`;

    await api(
      "/api/internal/campaigns/validate",
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }
    );

    const resposta = await api(
      "/api/internal/campaigns",
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }
    );

    const codigo = resposta.campanha?.codigo_campanha || "Campanha";

    document.getElementById("cadastroMsg").innerHTML =
      `<div class="notice success">${esc(codigo)} criada com sucesso.</div>`;

    setTimeout(async () => {
      document.getElementById("modalRoot").innerHTML = "";
      await carregar();
    }, 900);

  } catch (e) {
    erroWizard(e.message);
  }
}




/* ==========================================================
   V10 — FEEDBACK DE CARREGAMENTO
   Tres sinais, do mais leve ao mais forte:
   1. barra no topo, imediata: mostra que algo esta rodando
   2. cursor de progresso na pagina inteira
   3. cartao com contador de segundos, so depois de 400ms,
      para que chamadas rapidas nao piscem um modal na tela
   O contador e o que diz "esta vivo" quando demora.
   ========================================================== */

let __barraTopo = null;
let __cartaoTimer = null;
let __tickTimer = null;
let __botaoOcupado = null;

function __garantirBarraTopo() {
  if (__barraTopo) return __barraTopo;

  __barraTopo = document.createElement("div");
  __barraTopo.className = "v10-topbar-progress";
  __barraTopo.setAttribute("role", "progressbar");
  __barraTopo.setAttribute("aria-label", "Carregando");
  __barraTopo.innerHTML = '<i></i>';
  document.body.appendChild(__barraTopo);

  return __barraTopo;
}

function garantirLoadingOverlay() {
  let overlay = document.getElementById("globalLoading");

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "globalLoading";
    overlay.className = "v10-loading hidden";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML = `
      <div class="v10-loading-card">

        <div class="v10-loading-spinner" aria-hidden="true"></div>

        <div class="v10-loading-copy">
          <strong id="globalLoadingTitle">Processando</strong>
          <span id="globalLoadingText">Consultando os dados das campanhas.</span>
        </div>

        <div class="v10-loading-clock">
          <b id="globalLoadingClock">0s</b>
        </div>

      </div>
    `;

    document.body.appendChild(overlay);
  }

  return overlay;
}

function mostrarLoading(texto = "Consultando os dados das campanhas.") {
  loadingRequests += 1;

  if (loadingRequests === 1) {
    loadingStartedAt = Date.now();
  }

  /* Sinal imediato: barra no topo e cursor de progresso. */
  __garantirBarraTopo().classList.add("ativa");
  document.body.classList.add("v10-ocupado");

  /* Feedback no proprio elemento clicado, para a acao nao
     parecer ignorada enquanto a requisicao vai e volta.   */
  const alvo = document.activeElement;

  if (alvo && alvo.tagName === "BUTTON" && !__botaoOcupado) {
    __botaoOcupado = alvo;
    alvo.classList.add("v10-botao-ocupado");
    alvo.setAttribute("aria-busy", "true");
  }

  const overlay = garantirLoadingOverlay();
  const textEl = overlay.querySelector("#globalLoadingText");

  if (textEl) {
    textEl.textContent = texto;
  }

  if (__cartaoTimer) return;

  /* O cartao so entra depois de 400ms. Requisicao rapida
     nunca chega a piscar um modal.                        */
  __cartaoTimer = setTimeout(
    () => {
      if (loadingRequests < 1) return;

      overlay.classList.remove("hidden");
      requestAnimationFrame(() => overlay.classList.add("visible"));

      const tick = () => {
          const seg = Math.floor((Date.now() - loadingStartedAt) / 1000);

          const relogio =
            document.getElementById("globalLoadingClock");

          if (relogio) {
            relogio.textContent = seg + "s";
          }

          const t = document.getElementById("globalLoadingText");

          if (!t) return;

          if (seg >= 20) {
            t.textContent =
              "Continua rodando. Se passar de um minuto, atualize a página e tente de novo.";
          } else if (seg >= 8) {
            t.textContent =
              "Está demorando mais que o normal, mas a requisição segue ativa.";
          }
      };

      tick();
      __tickTimer = setInterval(tick, 1000);
    },
    400
  );
}

function ocultarLoading() {
  loadingRequests = Math.max(0, loadingRequests - 1);

  if (loadingRequests > 0) return;

  clearTimeout(__cartaoTimer);
  __cartaoTimer = null;

  clearInterval(__tickTimer);
  __tickTimer = null;

  if (__barraTopo) {
    __barraTopo.classList.remove("ativa");
  }

  document.body.classList.remove("v10-ocupado");

  if (__botaoOcupado) {
    __botaoOcupado.classList.remove("v10-botao-ocupado");
    __botaoOcupado.removeAttribute("aria-busy");
    __botaoOcupado = null;
  }

  const overlay = document.getElementById("globalLoading");

  if (!overlay) return;

  overlay.classList.remove("visible");

  setTimeout(
    () => {
      if (loadingRequests > 0) return;

      overlay.classList.add("hidden");

      const relogio =
        document.getElementById("globalLoadingClock");

      if (relogio) {
        relogio.textContent = "0s";
      }

      loadingStartedAt = 0;
    },
    180
  );
}




/* ==========================================================
   V10.2 — ESTEIRA, LINHAS E FILTROS
   Estrutura trazida da versao editorial, na paleta e na
   tipografia da V10. O que veio: linhas com "proxima acao"
   em coluna, esteira de etapas no lugar da rosca, e as
   metricas viradas em pontos de entrada clicaveis.
   ========================================================== */

const V10_ETAPAS = [
  {chave:"planejamento", label:"Planejamento", statuses:["CADASTRADA_PLANEJAMENTO"]},
  {chave:"comercial",    label:"Comercial",    statuses:["EM_VALIDACAO_COMERCIAL","VALIDADA_COMERCIAL"]},
  {chave:"handoff",      label:"Handoff",      statuses:["PARCIALMENTE_LIBERADA_EPS"]},
  {chave:"eps",          label:"Com as EPS",   statuses:["ENVIADA_EPS"]},
  {chave:"encerradas",   label:"Encerradas",   statuses:["ENCERRADA_EDUNOVA"]}
];

function etapaCurtaV10(status) {
  const etapa =
    V10_ETAPAS.find(
      item => item.statuses.includes(status)
    );

  return etapa ? etapa.label : "Em andamento";
}

function esteiraV10(campanhas) {
  const maior =
    Math.max(
      1,
      ...V10_ETAPAS.map(
        etapa =>
          campanhas.filter(
            item => etapa.statuses.includes(item.status_campanha)
          ).length
      )
    );

  return V10_ETAPAS
    .map(
      etapa => {
        const qtd =
          campanhas.filter(
            item => etapa.statuses.includes(item.status_campanha)
          ).length;

        /* A barra e proporcional a maior etapa, nao ao total:
           assim a comparacao entre etapas fica legivel mesmo
           com poucas campanhas no ciclo.                      */
        const largura =
          qtd ? Math.max(8, Math.round(qtd / maior * 100)) : 0;

        return `
          <div class="v10-etapa ${qtd ? "" : "vazia"}">

            <div class="v10-etapa-topo">
              <strong>${qtd}</strong>
            </div>

            <div class="v10-etapa-trilho">
              <i style="width:${largura}%"></i>
            </div>

            <div class="v10-etapa-label">
              ${esc(etapa.label)}
            </div>

          </div>
        `;
      }
    )
    .join("");
}

function linhaCampanhaV10(item) {
  const etapa =
    etapaCurtaV10(item.status_campanha);

  return `
    <article
      class="v10-linha abrir-campanha"
      data-code="${esc(item.codigo_campanha)}"
      tabindex="0"
      role="button"
    >

      <div class="v10-linha-main">

        <div class="v10-linha-topo">
          <span class="v10-linha-code">
            ${esc(item.codigo_campanha)}
          </span>

          <span>
            ${esc(humanizarV9(item.produto))}
          </span>
        </div>

        <h3>
          ${esc(item.nome_campanha)}
        </h3>

      </div>

      <div class="v10-linha-col">
        <small>Status</small>
        <strong>${esc(etapa)}</strong>
      </div>

      <div class="v10-linha-col">
        <small>Responsável</small>
        <strong>${esc(item.responsavel_comercial || "A definir")}</strong>
      </div>

      <div class="v10-linha-col acao">
        <small>Próxima ação</small>
        <strong>${esc(proximaAcaoInternaV9(item.status_campanha))}</strong>
      </div>

      <div class="v10-linha-ir">\u203a</div>

    </article>
  `;
}

/* Filtra a tabela por etapa. Reaproveita o campo de busca:
   os dois criterios se somam em vez de brigar.              */
let v10FiltroAtual = "todas";

function aplicarFiltroV10() {
  const termo =
    (document.getElementById("busca")?.value || "")
      .toLowerCase()
      .trim();

  const etapa =
    V10_ETAPAS.find(
      item => item.chave === v10FiltroAtual
    );

  const filtradas =
    campanhasCache.filter(
      item => {
        const casaEtapa =
          !etapa ||
          etapa.statuses.includes(item.status_campanha);

        const casaBusca =
          !termo ||
          JSON.stringify(item)
            .toLowerCase()
            .includes(termo);

        return casaEtapa && casaBusca;
      }
    );

  const tbody =
    document.getElementById("tb");

  if (!tbody) return;

  tbody.innerHTML =
    filtradas.length
      ? rowsV9(filtradas)
      : `<tr><td colspan="7" class="table-empty">
           Nenhuma campanha encontrada com esses filtros.
         </td></tr>`;

  bindAbrir();
}

function bindFiltrosV10() {
  const caixa =
    document.getElementById("filtros");

  if (caixa) {
    caixa
      .querySelectorAll(".v10-filtro")
      .forEach(
        botao => {
          botao.onclick =
            () => {
              caixa
                .querySelectorAll(".v10-filtro")
                .forEach(
                  outro => outro.classList.remove("ativo")
                );

              botao.classList.add("ativo");
              v10FiltroAtual = botao.dataset.filtro;
              aplicarFiltroV10();
            };
        }
      );
  }

  /* Os cartoes de acao levam ao filtro correspondente e
     rolam ate a tabela, para o clique ter consequencia.   */
  document
    .querySelectorAll(".v10-acao[data-filtro]")
    .forEach(
      cartao => {
        cartao.onclick =
          () => {
            const alvo =
              document.querySelector(
                `.v10-filtro[data-filtro="${cartao.dataset.filtro}"]`
              );

            if (alvo) {
              alvo.click();

              alvo.scrollIntoView({
                behavior: "smooth",
                block: "center"
              });
            }
          };
      }
    );

  const novaQuick =
    document.getElementById("novaCampanhaQuick");

  if (novaQuick) {
    novaQuick.onclick = abrirCadastroMVP;
  }

  /* Teclado: linha e um controle, entao Enter e espaco
     precisam funcionar como o clique.                    */
  document
    .querySelectorAll(".v10-linha")
    .forEach(
      linha => {
        linha.onkeydown =
          evento => {
            if (evento.key === "Enter" || evento.key === " ") {
              evento.preventDefault();
              linha.click();
            }
          };
      }
    );
}


carregar();
