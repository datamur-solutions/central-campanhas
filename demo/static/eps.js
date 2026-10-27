
const app = document.getElementById("app");

const state = {
  email:
    localStorage.getItem("portal_eps_email") || "",
  usuario: null,
  campanhas: [],
  atual: null,
  detalheModo: "principal"
};


const esc = value =>
  String(value ?? "")
    .replace(
      /[&<>"']/g,
      char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char])
    );


function erroApi(detail) {
  if (Array.isArray(detail)) {
    return detail
      .map(item => {
        const campo =
          Array.isArray(item.loc)
            ? item.loc
                .filter(x => x !== "body")
                .join(" › ")
            : "";

        return `${campo ? campo + ": " : ""}${item.msg || "valor inválido"}`;
      })
      .join(" | ");
  }

  if (
    detail &&
    typeof detail === "object"
  ) {
    try {
      return JSON.stringify(detail);
    } catch {}
  }

  return detail || "Erro na solicitação.";
}


/* ==========================================================
   LOADING
========================================================== */

let loadingRequests = 0;
let loadingStartedAt = 0;


function garantirLoadingOverlay() {
  let overlay =
    document.getElementById(
      "globalLoadingOverlay"
    );

  if (!overlay) {
    overlay =
      document.createElement("div");

    overlay.id =
      "globalLoadingOverlay";

    overlay.className =
      "global-loading-overlay hidden";

    overlay.innerHTML = `
      <div class="global-loading-card">

        <div
          class="global-spinner"
          aria-hidden="true"
        ></div>

        <div>
          <strong id="globalLoadingTitle">
            Atualizando informações...
          </strong>

          <span id="globalLoadingText">
            Aguarde enquanto carregamos os dados.
          </span>
        </div>

      </div>
    `;

    document.body.appendChild(
      overlay
    );
  }

  return overlay;
}


function mostrarLoading(
  texto = "Aguarde enquanto carregamos os dados."
) {
  loadingRequests += 1;

  loadingStartedAt =
    loadingStartedAt ||
    Date.now();

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

  const elapsed =
    Date.now() -
    loadingStartedAt;

  const delay =
    Math.max(
      0,
      320 - elapsed
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
        () => {
          overlay.classList.add(
            "hidden"
          );
        },
        180
      );

      loadingStartedAt = 0;
    },
    delay
  );
}


async function api(
  url,
  opt = {}
) {
  showLoading(
    "Consultando os dados da campanha..."
  );

  try {
    const response =
      await fetch(
        url,
        opt
      );

    let data = {};

    try {
      data =
        await response.json();
    } catch {}

    if (!response.ok) {
      throw new Error(
        erroApi(
          data.detail
        )
      );
    }

    return data;

  } finally {
    hideLoading();
  }
}


const qemail =
  () =>
    encodeURIComponent(
      state.email
    );


/* ==========================================================
   LOADING VISUAL
========================================================== */

let loadingCount = 0;
let loadingStart = 0;


function ensureLoading() {
  let overlay =
    document.getElementById(
      "siteLoading"
    );

  if (!overlay) {
    overlay =
      document.createElement(
        "div"
      );

    overlay.id =
      "siteLoading";

    overlay.className =
      "site-loading hidden";

    overlay.innerHTML = `
      <div class="site-loading-card">

        <div class="site-spinner"></div>

        <div>
          <strong>
            Carregando...
          </strong>

          <span id="siteLoadingText">
            Atualizando as informações da campanha.
          </span>
        </div>

      </div>
    `;

    document.body.appendChild(
      overlay
    );
  }

  return overlay;
}


function showLoading(
  texto = "Atualizando as informações da campanha."
) {
  loadingCount += 1;

  if (
    loadingCount === 1
  ) {
    loadingStart =
      Date.now();
  }

  const overlay =
    ensureLoading();

  const textEl =
    overlay.querySelector(
      "#siteLoadingText"
    );

  if (textEl) {
    textEl.textContent =
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


function hideLoading() {
  loadingCount =
    Math.max(
      0,
      loadingCount - 1
    );

  if (
    loadingCount > 0
  ) {
    return;
  }

  const overlay =
    document.getElementById(
      "siteLoading"
    );

  if (!overlay) {
    return;
  }

  const elapsed =
    Date.now() -
    loadingStart;

  const wait =
    Math.max(
      0,
      350 - elapsed
    );

  setTimeout(
    () => {
      if (
        loadingCount > 0
      ) {
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
    wait
  );
}


/* ==========================================================
   HELPERS DE STATUS
========================================================== */

function statusLabel(status) {
  const mapa = {
    AGUARDANDO_PLANEJAMENTO_EPS:
      "Preparação necessária",

    PLANEJAMENTO_EPS:
      "Preparação concluída",

    GO_LIVE_APROVADO:
      "Pronta para iniciar",

    EM_EXECUCAO:
      "Em execução",

    EXECUCAO_FINALIZADA:
      "Finalizada"
  };

  return mapa[status] ||
    status ||
    "-";
}


function proximaAcao(status) {
  const mapa = {
    AGUARDANDO_PLANEJAMENTO_EPS:
      "Confirmar preparação",

    PLANEJAMENTO_EPS:
      "Confirmar prontidão",

    GO_LIVE_APROVADO:
      "Iniciar campanha",

    EM_EXECUCAO:
      "Atualizar resultado",

    EXECUCAO_FINALIZADA:
      "Ver fechamento"
  };

  return mapa[status] ||
    "Abrir campanha";
}


function etapaAtual(status) {
  const mapa = {
    AGUARDANDO_PLANEJAMENTO_EPS: 0,
    PLANEJAMENTO_EPS: 1,
    GO_LIVE_APROVADO: 2,
    EM_EXECUCAO: 3,
    EXECUCAO_FINALIZADA: 4
  };

  return mapa[status] ?? 0;
}


function hojeLocal() {
  const d =
    new Date();

  const y =
    d.getFullYear();

  const m =
    String(
      d.getMonth() + 1
    ).padStart(
      2,
      "0"
    );

  const day =
    String(
      d.getDate()
    ).padStart(
      2,
      "0"
    );

  return `${y}-${m}-${day}`;
}


/* ==========================================================
   LOGIN
========================================================== */

function login(
  mensagem = ""
) {
  app.innerHTML = `
    <div class="login">

      <div>
        <img
          src="static/EduNova.png"
          alt="EduNova Educação"
          class="edunova-logo-login"
        >

        <h1>
          Central de Campanhas
        </h1>

        <p>
          Portal Operacional EPS
        </p>
      </div>

      <div class="login-card">

        <div class="eyebrow">
          ACESSO CORPORATIVO
        </div>

        <h2>
          Bem-vindo
        </h2>

        <p class="muted">
          Use seu e-mail corporativo aprovado.
        </p>

        <label>
          E-mail
        </label>

        <input
          id="email"
          type="email"
          value="${esc(state.email)}"
          placeholder="nome@empresa.com.br"
        >

        ${
          mensagem
            ? `
              <div class="notice error">
                ${esc(mensagem)}
              </div>
            `
            : ""
        }

        <button
          class="btn"
          id="entrar"
        >
          Acessar Portal
        </button>

      </div>
    </div>
  `;

  document
    .getElementById(
      "entrar"
    )
    .onclick =
      entrar;

  document
    .getElementById(
      "email"
    )
    .onkeydown =
      event => {
        if (
          event.key ===
          "Enter"
        ) {
          entrar();
        }
      };
}


async function entrar() {
  state.email =
    document
      .getElementById(
        "email"
      )
      .value
      .trim();

  if (!state.email) {
    login(
      "Informe seu e-mail corporativo."
    );

    return;
  }

  try {
    const data =
      await api(
        `/api/external/campaigns?email=${qemail()}`
      );

    localStorage.setItem(
      "portal_eps_email",
      state.email
    );

    state.usuario =
      data.usuario;

    state.campanhas =
      data.campanhas || [];

    portal();

  } catch (error) {
    login(
      error.message
    );
  }
}


async function carregar() {
  try {
    const data =
      await api(
        `/api/external/campaigns?email=${qemail()}`
      );

    state.usuario =
      data.usuario;

    state.campanhas =
      data.campanhas || [];

    portal();

  } catch (error) {
    localStorage.removeItem(
      "portal_eps_email"
    );

    state.email = "";

    login(
      error.message
    );
  }
}


/* ==========================================================
   HOME EPS
========================================================== */


function epsPrimeiroNomeV9() {
  const nome =
    String(
      state.usuario?.nome ||
      "Time"
    )
      .trim()
      .split(/\s+/)[0];

  return nome || "Time";
}


function epsSaudacaoV9() {
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


function epsPercentualEtapaV9(
  status
) {
  const mapa = {
    AGUARDANDO_PLANEJAMENTO_EPS:
      15,

    PLANEJAMENTO_EPS:
      35,

    GO_LIVE_APROVADO:
      55,

    EM_EXECUCAO:
      78,

    EXECUCAO_FINALIZADA:
      100
  };

  return (
    mapa[
      status
    ]
    ??
    0
  );
}


function epsStatusClassV9(
  status
) {
  if (
    status ===
    "EM_EXECUCAO"
  ) {
    return "running";
  }

  if (
    status ===
    "EXECUCAO_FINALIZADA"
  ) {
    return "done";
  }

  if (
    status ===
    "GO_LIVE_APROVADO"
  ) {
    return "ready";
  }

  return "attention";
}


function epsDonutV9(
  pendentes,
  execucao,
  finalizadas
) {
  const total =
    Math.max(
      1,
      pendentes +
      execucao +
      finalizadas
    );

  const pPendentes =
    pendentes /
    total *
    100;

  const pExecucao =
    execucao /
    total *
    100;

  return `conic-gradient(
    #f2a740 0 ${pPendentes}%,
    #7b35d4 ${pPendentes}% ${pPendentes + pExecucao}%,
    #38a66b ${pPendentes + pExecucao}% 100%
  )`;
}

function portal() {
  const pendentes =
    state.campanhas.filter(
      item =>
        [
          "AGUARDANDO_PLANEJAMENTO_EPS",
          "PLANEJAMENTO_EPS",
          "GO_LIVE_APROVADO"
        ].includes(
          item.status_execucao_eps
        )
    ).length;

  const execucao =
    state.campanhas.filter(
      item =>
        item.status_execucao_eps ===
        "EM_EXECUCAO"
    ).length;

  const finalizadas =
    state.campanhas.filter(
      item =>
        item.status_execucao_eps ===
        "EXECUCAO_FINALIZADA"
    ).length;

  const total =
    state.campanhas.length;

  const nomeEPS =
    state.usuario?.eps ||
    "EPS";

  const precisaAcao =
    state.campanhas
      .filter(
        item =>
          item.status_execucao_eps !==
          "EXECUCAO_FINALIZADA"
      )
      .slice(
        0,
        4
      );

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
              Portal EPS
            </span>
          </div>

        </div>

        <nav class="v9-topnav">
          <button class="active">
            Minhas campanhas
          </button>
        </nav>

        <div class="v9-user-block">

          <div class="v9-user-avatar">
            ${
              esc(
                String(
                  nomeEPS
                )
                  .charAt(0)
                  .toUpperCase()
              )
            }
          </div>

          <div>
            <strong>
              ${esc(nomeEPS)}
            </strong>

            <span>
              ${esc(state.email)}
            </span>
          </div>

          <button
            class="v9-logout"
            id="sair"
            title="Sair"
          >
            ↗
          </button>

        </div>

      </header>

      <main class="v9-main">

        <section class="v9-hero eps-v9-hero">

          <div class="v9-hero-copy">

            <span class="v9-hero-kicker">
              ${epsSaudacaoV9()}, ${esc(nomeEPS)}
            </span>

            <h1>
              ${
                pendentes
                  ? `<strong>${pendentes}</strong> campanha${pendentes > 1 ? "s" : ""} ${pendentes > 1 ? "aguardam" : "aguarda"} sua próxima ação.`
                  : execucao
                    ? "Nenhuma ação pendente. Mantenha os resultados atualizados."
                    : "Nenhuma campanha exige ação sua agora."
              }
            </h1>

            <p>
              ${total} campanha(s) sob sua responsabilidade,
              ${execucao} em execução e ${finalizadas} finalizada(s).
            </p>

            <div class="v9-hero-actions">

              <button
                class="v9-primary-action"
                id="atualizarLista"
              >
                Atualizar minhas campanhas
              </button>

            </div>

          </div>

        </section>

        <section class="v9-metric-grid eps-v9-metrics">

          <article class="v9-metric-card ${pendentes ? "is-live" : ""}">
            <div>
              <span>Precisam de ação</span>
              <strong>${pendentes}</strong>
              <small>Prioridade de hoje</small>
            </div>
          </article>

          <article class="v9-metric-card">
            <div>
              <span>Em execução</span>
              <strong>${execucao}</strong>
              <small>Atualizar resultados</small>
            </div>
          </article>

          <article class="v9-metric-card">
            <div>
              <span>Finalizadas</span>
              <strong>${finalizadas}</strong>
              <small>Ciclo concluído</small>
            </div>
          </article>

        </section>

        <section class="v9-section">

          <div class="v9-section-head">

            <div>
              <h2>
                O que precisa da sua atenção
              </h2>

              <p>
                Abra uma campanha e execute somente
                a próxima ação indicada.
              </p>
            </div>

          </div>

          <div class="eps-v9-card-grid">

            ${
              precisaAcao.length
                ? precisaAcao
                    .map(
                      cardCampanha
                    )
                    .join("")
                : `
                  <div class="v9-empty-state">
                    <strong>
                      Tudo em dia por aqui
                    </strong>
                    <span>
                      Nenhuma campanha exige ação agora.
                    </span>
                  </div>
                `
            }

          </div>

        </section>

        ${
          finalizadas
            ? `
              <section class="v9-panel">

                <div class="v9-section-head">
                  <div>
                    <h2>
                      Campanhas finalizadas
                    </h2>
                  </div>
                </div>

                <div class="eps-v9-completed-list">

                  ${
                    state.campanhas
                      .filter(
                        item =>
                          item.status_execucao_eps ===
                          "EXECUCAO_FINALIZADA"
                      )
                      .map(
                        item => `
                          <button
                            class="eps-v9-completed abrir"
                            data-code="${esc(item.codigo_campanha)}"
                          >
                            <span class="v9-code">
                              ${esc(item.codigo_campanha)}
                            </span>

                            <strong>
                              ${esc(item.nome_campanha)}
                            </strong>

                            <span>
                              Finalizada
                            </span>

                            <b>›</b>
                          </button>
                        `
                      )
                      .join("")
                  }

                </div>

              </section>
            `
            : ""
        }

      </main>

    </div>

    <div id="modalRoot"></div>
  `;

  document
    .getElementById(
      "sair"
    )
    .onclick =
      () => {
        localStorage.removeItem(
          "portal_eps_email"
        );

        state.email = "";

        login();
      };

  document
    .getElementById(
      "atualizarLista"
    )
    .onclick =
      carregar;

  document
    .querySelectorAll(
      ".abrir"
    )
    .forEach(
      button => {
        button.onclick =
          () =>
            abrir(
              button.dataset.code
            );
      }
    );
}


function cardCampanha(
  campaign
) {
  const status =
    campaign.status_execucao_eps ||
    "AGUARDANDO_PLANEJAMENTO_EPS";

  const percentual =
    epsPercentualEtapaV9(
      status
    );

  const statusClass =
    epsStatusClassV9(
      status
    );

  return `
    <article class="eps-v9-card ${statusClass}">

      <div class="eps-v9-card-head">

        <span class="v9-code">
          ${esc(campaign.codigo_campanha)}
        </span>

        <span class="eps-v9-status ${statusClass}">
          ${esc(statusLabel(status))}
        </span>

      </div>

      <h3>
        ${esc(campaign.nome_campanha)}
      </h3>

      <div class="eps-v9-tags">

        ${
          campaign.produto
            ? `
              <span>
                ${esc(campaign.produto)}
              </span>
            `
            : ""
        }

        ${
          campaign.tipo_acao
            ? `
              <span>
                ${esc(campaign.tipo_acao)}
              </span>
            `
            : ""
        }

      </div>

      <p class="eps-v9-objective">
        ${esc(
          campaign.objetivo_campanha ||
          "Consulte os detalhes e siga a próxima ação indicada."
        )}
      </p>

      <div class="eps-v9-progress-block">

        <div class="eps-v9-progress-label">

          <span>
            Progresso operacional
          </span>

          <strong>
            ${percentual}%
          </strong>

        </div>

        <div class="eps-v9-progress-track">
          <div
            class="eps-v9-progress-fill"
            style="width:${percentual}%"
          ></div>
        </div>

      </div>

      <div class="eps-v9-next">

        <span>
          Sua próxima ação
        </span>

        <strong>
          ${esc(proximaAcao(status))}
        </strong>

      </div>

      <button
        class="v9-primary-action eps-v9-open abrir"
        data-code="${esc(campaign.codigo_campanha)}"
      >
        ${esc(proximaAcao(status))}
        <span>›</span>
      </button>

    </article>
  `;
}


/* ==========================================================
   DETALHE — UMA ÚNICA AÇÃO POR VEZ
========================================================== */

async function abrir(
  code
) {
  try {
    const data =
      await api(
        `/api/external/campaigns/${encodeURIComponent(code)}?email=${qemail()}`
      );

    state.atual =
      data.campanha;

    state.detalheModo =
      "principal";

    renderDetalhe();

  } catch (error) {
    alert(
      error.message
    );
  }
}


function renderDetalhe() {
  const campaign =
    state.atual;

  const status =
    campaign.status_execucao_eps ||
    "AGUARDANDO_PLANEJAMENTO_EPS";

  const root =
    document.getElementById(
      "modalRoot"
    );

  root.innerHTML = `
    <div class="modal">

      <div class="modal-card eps-task-modal">

        <div class="modal-head">

          <div>

            <div class="eyebrow">
              ${esc(campaign.codigo_campanha)}
            </div>

            <h2>
              ${esc(campaign.nome_campanha)}
            </h2>

            <span class="status ${
              status === "EM_EXECUCAO"
                ? "run"
                : ""
            }">
              ${esc(statusLabel(status))}
            </span>

          </div>

          <button
            class="close"
            id="fecharCampanha"
          >
            ×
          </button>

        </div>

        ${barraEtapas(status)}

        <div class="eps-task-layout">

          <section class="eps-task-main">

            ${acaoPrincipal(campaign)}

          </section>

          <aside class="eps-campaign-summary">

            <div class="eyebrow">
              RESUMO DA CAMPANHA
            </div>

            <h3>
              O que você precisa saber
            </h3>

            <div class="eps-summary-item">
              <span>Objetivo</span>
              <p>
                ${esc(
                  campaign.objetivo_campanha ||
                  "-"
                )}
              </p>
            </div>

            <div class="eps-summary-item">
              <span>Público</span>
              <p>
                ${esc(
                  campaign.publico_alvo ||
                  "-"
                )}
              </p>
            </div>

            <div class="eps-summary-item">
              <span>Produto</span>
              <strong>
                ${esc(
                  campaign.produto ||
                  "-"
                )}
              </strong>
            </div>

            <details class="eps-more-details">

              <summary>
                Ver mais detalhes
              </summary>

              <div class="eps-more-body">

                <span>
                  Orientação
                </span>

                <p>
                  ${esc(
                    campaign.estrategia ||
                    "-"
                  )}
                </p>

                <span>
                  Tipo
                </span>

                <p>
                  ${esc(
                    campaign.tipo_acao ||
                    "-"
                  )}
                </p>

              </div>

            </details>

          </aside>

        </div>

      </div>

    </div>
  `;

  document
    .getElementById(
      "fecharCampanha"
    )
    .onclick =
      () =>
        root.innerHTML = "";

  bindAcaoPrincipal(
    campaign
  );
}


function barraEtapas(
  status
) {
  const atual =
    etapaAtual(
      status
    );

  const etapas = [
    "Preparar",
    "Prontidão",
    "Iniciar",
    "Executar",
    "Finalizar"
  ];

  return `
    <div class="eps-simple-flow">

      ${
        etapas
          .map(
            (label, index) => `
              <div
                class="eps-simple-flow-step ${
                  index < atual
                    ? "done"
                    : ""
                } ${
                  index === atual
                    ? "active"
                    : ""
                }"
              >
                <span>
                  ${
                    index < atual
                      ? "✓"
                      : index + 1
                  }
                </span>

                <strong>
                  ${label}
                </strong>
              </div>

              ${
                index <
                etapas.length - 1
                  ? `
                    <div
                      class="eps-simple-flow-line ${
                        index < atual
                          ? "done"
                          : ""
                      }"
                    ></div>
                  `
                  : ""
              }
            `
          )
          .join("")
      }

    </div>
  `;
}


function acaoPrincipal(
  campaign
) {
  const status =
    campaign.status_execucao_eps ||
    "AGUARDANDO_PLANEJAMENTO_EPS";

  if (
    status ===
    "AGUARDANDO_PLANEJAMENTO_EPS"
  ) {
    return preparacaoHtml();
  }

  if (
    status ===
    "PLANEJAMENTO_EPS"
  ) {
    return prontidaoHtml();
  }

  if (
    status ===
    "GO_LIVE_APROVADO"
  ) {
    return inicioHtml();
  }

  if (
    status ===
    "EM_EXECUCAO"
  ) {
    return execucaoHtml();
  }

  if (
    status ===
    "EXECUCAO_FINALIZADA"
  ) {
    return finalizadaHtml();
  }

  return `
    <div class="notice">
      Status atual:
      ${esc(status)}
    </div>
  `;
}


/* ==========================================================
   ETAPA 1 — PREPARAÇÃO
========================================================== */

function preparacaoHtml() {
  return `
    <div class="eps-action-card">

      <div class="eps-action-number">
        1
      </div>

      <div class="eps-action-content">

        <div class="eyebrow">
          FAÇA AGORA
        </div>

        <h2>
          Confirmar preparação
        </h2>

        <p class="eps-action-intro">
          Precisamos de apenas três informações
          antes de iniciar.
        </p>

        <div class="grid2 eps-form-v52">

          <div class="full">

            <label>
              Quem será o responsável pela campanha? *
            </label>

            <input
              id="prepResponsavel"
              placeholder="Nome do responsável EPS"
            >

          </div>

          <div>

            <label>
              Quando a operação começa? *
            </label>

            <input
              id="prepInicio"
              type="date"
            >

          </div>

          <div>

            <label>
              A campanha usa mailing/base? *
            </label>

            <select id="prepMailing">

              <option value="">
                Selecione
              </option>

              <option value="false">
                Não
              </option>

              <option value="true">
                Sim
              </option>

            </select>

          </div>

          <div
            id="prepMailVolumeWrap"
            class="hidden"
          >

            <label>
              Quantos registros foram recebidos? *
            </label>

            <input
              id="prepMailVolume"
              type="number"
              min="0"
            >

          </div>

          <div
            id="prepMailConfirmWrap"
            class="full hidden"
          >

            <label class="confirm-card">

              <input
                id="prepMailConfirm"
                type="checkbox"
              >

              <span>
                <strong>
                  Mailing recebido e validado
                </strong>

                <small>
                  A base está disponível para a operação.
                </small>
              </span>

            </label>

          </div>

          <div class="full">

            <label class="confirm-card eps-main-confirm">

              <input
                id="prepOperacao"
                type="checkbox"
              >

              <span>
                <strong>
                  Estamos prontos para executar
                </strong>

                <small>
                  Confirmo que equipe, recursos,
                  responsáveis, abordagem e forma
                  de reporte estão alinhados.
                </small>
              </span>

            </label>

          </div>

          <div class="full">

            <button
              class="btn btn-lg"
              id="confirmarPreparacao"
            >
              Confirmar preparação ›
            </button>

          </div>

        </div>

        <div id="msg"></div>

      </div>
    </div>
  `;
}


/* ==========================================================
   ETAPA 2 — PRONTIDÃO
========================================================== */

function prontidaoHtml() {
  return `
    <div class="eps-action-card">

      <div class="eps-action-number">
        2
      </div>

      <div class="eps-action-content">

        <div class="eyebrow">
          PRÓXIMA ETAPA
        </div>

        <h2>
          Confirmar que está pronto
        </h2>

        <p class="eps-action-intro">
          O sistema vai verificar automaticamente
          as informações da preparação.
        </p>

        <div
          id="readinessResult"
          class="eps-readiness-placeholder"
        >
          Clique abaixo para confirmar a prontidão.
        </div>

        <button
          class="btn btn-lg"
          id="confirmarProntidao"
        >
          Confirmar prontidão ›
        </button>

        <div id="msg"></div>

      </div>
    </div>
  `;
}


/* ==========================================================
   ETAPA 3 — INÍCIO
========================================================== */

function inicioHtml() {
  return `
    <div class="eps-action-card">

      <div class="eps-action-number">
        3
      </div>

      <div class="eps-action-content">

        <div class="eyebrow">
          TUDO PRONTO
        </div>

        <h2>
          Iniciar campanha
        </h2>

        <p class="eps-action-intro">
          O Go-Live já está aprovado.
          Confirme o início da execução.
        </p>

        <button
          class="btn btn-lg"
          id="iniciarExecucao"
        >
          Iniciar campanha ›
        </button>

        <div id="msg"></div>

      </div>
    </div>
  `;
}


/* ==========================================================
   ETAPA 4 — EXECUÇÃO
========================================================== */

function execucaoHtml() {
  if (
    state.detalheModo ===
    "encerrar"
  ) {
    return encerramentoHtml();
  }

  return `
    <div class="eps-action-card">

      <div class="eps-action-number">
        4
      </div>

      <div class="eps-action-content">

        <div class="eyebrow">
          CAMPANHA EM EXECUÇÃO
        </div>

        <h2>
          Atualização rápida
        </h2>

        <p class="eps-action-intro">
          Registre o resultado do período.
          Os indicadores operacionais ficam opcionais.
        </p>

        <div class="grid2 eps-form-v52">

          <div>

            <label>
              Data *
            </label>

            <input
              id="execData"
              type="date"
              value="${hojeLocal()}"
            >

          </div>

          <div></div>

          <div>

            <label>
              Vendas
            </label>

            <input
              id="execVendas"
              type="number"
              min="0"
              placeholder="0"
            >

          </div>

          <div>

            <label>
              Matrículas
            </label>

            <input
              id="execMatriculas"
              type="number"
              min="0"
              placeholder="0"
            >

          </div>

          <details class="full advanced-details eps-operational-details">

            <summary>
              Indicadores operacionais
              <span>opcional</span>
            </summary>

            <div class="advanced-body grid2">

              <div>

                <label>
                  Tentativas / disparos
                </label>

                <input
                  id="execTentativas"
                  type="number"
                  min="0"
                >

              </div>

              <div>

                <label>
                  Contatos
                </label>

                <input
                  id="execContatos"
                  type="number"
                  min="0"
                >

              </div>

              <div class="full">

                <label>
                  Alguma ocorrência importante?
                </label>

                <textarea
                  id="execObs"
                  placeholder="Opcional"
                ></textarea>

              </div>

            </div>

          </details>

          <div class="full">

            <button
              class="btn btn-lg"
              id="salvarAtualizacao"
            >
              Salvar atualização
            </button>

          </div>

        </div>

        <div id="msg"></div>

        <div class="eps-close-link">

          <span>
            A campanha terminou?
          </span>

          <button
            class="btn secondary"
            id="abrirEncerramento"
          >
            Finalizar campanha
          </button>

        </div>

      </div>
    </div>
  `;
}


function encerramentoHtml() {
  return `
    <div class="eps-action-card">

      <div class="eps-action-number final">
        5
      </div>

      <div class="eps-action-content">

        <button
          class="eps-back-link"
          id="voltarAtualizacao"
        >
          ← Voltar para atualização
        </button>

        <div class="eyebrow">
          ENCERRAMENTO
        </div>

        <h2>
          Finalizar campanha
        </h2>

        <p class="eps-action-intro">
          Precisamos apenas do fechamento
          e de um aprendizado principal.
        </p>

        <div class="grid2 eps-form-v52">

          <div>

            <label>
              Vendas finais
            </label>

            <input
              id="fimVendas"
              type="number"
              min="0"
            >

          </div>

          <div>

            <label>
              Matrículas finais
            </label>

            <input
              id="fimMatriculas"
              type="number"
              min="0"
            >

          </div>

          <div class="full">

            <label>
              Principal aprendizado
              <span class="optional-label">
                opcional
              </span>
            </label>

            <textarea
              id="fimAprendizado"
              placeholder="O que funcionou, o que dificultou ou o que deve mudar na próxima campanha?"
            ></textarea>

          </div>

          <div class="full">

            <label>
              Responsável pelo fechamento *
            </label>

            <input
              id="fimResponsavel"
              placeholder="Nome do responsável EPS"
            >

          </div>

          <div class="full">

            <label class="confirm-card">

              <input
                id="fimConfirm"
                type="checkbox"
              >

              <span>
                <strong>
                  Confirmo o encerramento
                </strong>

                <small>
                  A execução foi concluída
                  e os resultados acima representam
                  o fechamento da EPS.
                </small>
              </span>

            </label>

          </div>

          <div class="full">

            <button
              class="btn danger btn-lg"
              id="finalizarExecucao"
            >
              Finalizar campanha
            </button>

          </div>

        </div>

        <div id="msg"></div>

      </div>
    </div>
  `;
}


/* ==========================================================
   ETAPA 5 — FINALIZADA
========================================================== */

function finalizadaHtml() {
  return `
    <div class="eps-finished-card">

      <div class="eps-finished-icon">
        ✓
      </div>

      <div class="eyebrow">
        CONCLUÍDA
      </div>

      <h2>
        Execução finalizada
      </h2>

      <p>
        Não há nenhuma ação pendente para sua EPS
        nesta campanha.
      </p>

      <button
        class="btn secondary"
        id="fecharFinalizada"
      >
        Voltar para minhas campanhas
      </button>

    </div>
  `;
}


/* ==========================================================
   BIND DAS AÇÕES
========================================================== */

function msg(
  texto,
  ok = true
) {
  const el =
    document.getElementById(
      "msg"
    );

  if (el) {
    el.innerHTML = `
      <div class="notice ${
        ok
          ? "success"
          : "error"
      }">
        ${esc(texto)}
      </div>
    `;
  }
}


function bindAcaoPrincipal(
  campaign
) {
  const status =
    campaign.status_execucao_eps ||
    "AGUARDANDO_PLANEJAMENTO_EPS";

  if (
    status ===
    "AGUARDANDO_PLANEJAMENTO_EPS"
  ) {
    bindPreparacao(
      campaign
    );
  }

  if (
    status ===
    "PLANEJAMENTO_EPS"
  ) {
    bindProntidao(
      campaign
    );
  }

  if (
    status ===
    "GO_LIVE_APROVADO"
  ) {
    bindInicio(
      campaign
    );
  }

  if (
    status ===
    "EM_EXECUCAO"
  ) {
    bindExecucao(
      campaign
    );
  }

  if (
    status ===
    "EXECUCAO_FINALIZADA"
  ) {
    const button =
      document.getElementById(
        "fecharFinalizada"
      );

    if (button) {
      button.onclick =
        () => {
          document
            .getElementById(
              "modalRoot"
            )
            .innerHTML = "";

          carregar();
        };
    }
  }
}


function bindPreparacao(
  campaign
) {
  const mailing =
    document.getElementById(
      "prepMailing"
    );

  const toggleMailing =
    () => {
      const ativo =
        mailing.value ===
        "true";

      document
        .getElementById(
          "prepMailVolumeWrap"
        )
        .classList
        .toggle(
          "hidden",
          !ativo
        );

      document
        .getElementById(
          "prepMailConfirmWrap"
        )
        .classList
        .toggle(
          "hidden",
          !ativo
        );
    };

  mailing.onchange =
    toggleMailing;

  toggleMailing();

  document
    .getElementById(
      "confirmarPreparacao"
    )
    .onclick =
      async () => {

        const responsavel =
          document
            .getElementById(
              "prepResponsavel"
            )
            .value
            .trim();

        const inicio =
          document
            .getElementById(
              "prepInicio"
            )
            .value;

        const mailingValor =
          mailing.value;

        const operacaoPronta =
          document
            .getElementById(
              "prepOperacao"
            )
            .checked;

        if (!responsavel) {
          msg(
            "Informe o responsável pela campanha.",
            false
          );

          return;
        }

        if (!inicio) {
          msg(
            "Informe a data de início.",
            false
          );

          return;
        }

        if (mailingValor === "") {
          msg(
            "Informe se a campanha usa mailing/base.",
            false
          );

          return;
        }

        if (!operacaoPronta) {
          msg(
            "Confirme que a operação está pronta.",
            false
          );

          return;
        }

        const mailingAtivo =
          mailingValor ===
          "true";

        const volumeEl =
          document.getElementById(
            "prepMailVolume"
          );

        const confirmEl =
          document.getElementById(
            "prepMailConfirm"
          );

        if (
          mailingAtivo &&
          (
            !volumeEl ||
            volumeEl.value === ""
          )
        ) {
          msg(
            "Informe o volume da base recebida.",
            false
          );

          return;
        }

        if (
          mailingAtivo &&
          !confirmEl.checked
        ) {
          msg(
            "Confirme que o mailing foi recebido e validado.",
            false
          );

          return;
        }

        const body = {
          responsavel_eps:
            responsavel,

          ponto_focal_eps:
            responsavel,

          entendimento_confirmado:
            true,

          pendencias_criticas_resolvidas:
            true,

          mailing_aplicavel:
            mailingAtivo,

          mailing_recebido:
            mailingAtivo
              ? Number(
                  volumeEl.value
                )
              : null,

          mailing_disponivel:
            mailingAtivo
              ? true
              : null,

          mailing_validado:
            mailingAtivo
              ? true
              : null,

          qualidade_mailing_validada:
            mailingAtivo
              ? true
              : null,

          frequencia_reporte_eps:
            "SEMANAL",

          capacidade_operacional_validada:
            true,

          canais_recursos_disponiveis:
            true,

          responsaveis_pontos_focais_definidos:
            true,

          data_inicio_confirmada:
            true,

          segmentacao_configurada:
            true,

          jornada_cadencia_definidas:
            true,

          script_argumentacao_alinhados:
            true,

          modelo_frequencia_reporte_acordados:
            true,

          dt_inicio_operacional:
            inicio
        };

        try {
          await api(
            `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/operational-plan?email=${qemail()}`,
            {
              method:
                "PATCH",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify(
                  body
                )
            }
          );

          await refreshCurrent(
            campaign.codigo_campanha
          );

          renderDetalhe();

        } catch (error) {
          msg(
            error.message,
            false
          );
        }
      };
}


function bindProntidao(
  campaign
) {
  document
    .getElementById(
      "confirmarProntidao"
    )
    .onclick =
      async () => {

        const resultEl =
          document.getElementById(
            "readinessResult"
          );

        try {
          const readiness =
            await api(
              `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/readiness?email=${qemail()}`
            );

          if (
            !readiness.pronto_para_go_live
          ) {
            const blockers =
              readiness.bloqueadores ||
              [];

            resultEl.innerHTML = `
              <div class="notice error">
                Ainda falta concluir:
                ${esc(
                  blockers.join(", ")
                )}
              </div>
            `;

            return;
          }

          resultEl.innerHTML = `
            <div class="notice success">
              Tudo certo. Confirmando Go-Live...
            </div>
          `;

          await api(
            `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/go-live?email=${qemail()}`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify({
                  observacao:
                    "Prontidão confirmada no Portal EPS simplificado."
                })
            }
          );

          await refreshCurrent(
            campaign.codigo_campanha
          );

          renderDetalhe();

        } catch (error) {
          resultEl.innerHTML = `
            <div class="notice error">
              ${esc(error.message)}
            </div>
          `;
        }
      };
}


function bindInicio(
  campaign
) {
  document
    .getElementById(
      "iniciarExecucao"
    )
    .onclick =
      async () => {

        try {
          await api(
            `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/start-execution?email=${qemail()}`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify({
                  observacao:
                    "Execução iniciada pelo Portal EPS."
                })
            }
          );

          await refreshCurrent(
            campaign.codigo_campanha
          );

          renderDetalhe();

        } catch (error) {
          msg(
            error.message,
            false
          );
        }
      };
}


function bindExecucao(
  campaign
) {
  const back =
    document.getElementById(
      "voltarAtualizacao"
    );

  if (back) {
    back.onclick =
      () => {
        state.detalheModo =
          "principal";

        renderDetalhe();
      };

    bindEncerramento(
      campaign
    );

    return;
  }

  document
    .getElementById(
      "abrirEncerramento"
    )
    .onclick =
      () => {
        state.detalheModo =
          "encerrar";

        renderDetalhe();
      };

  document
    .getElementById(
      "salvarAtualizacao"
    )
    .onclick =
      async () => {

        const data =
          document
            .getElementById(
              "execData"
            )
            .value;

        if (!data) {
          msg(
            "Informe a data.",
            false
          );

          return;
        }

        const parse =
          id => {
            const el =
              document.getElementById(
                id
              );

            return (
              !el ||
              el.value === ""
            )
              ? null
              : Number(
                  el.value
                );
          };

        const obs =
          document
            .getElementById(
              "execObs"
            )
            ?.value
            ?.trim() ||
          null;

        const body = {
          performance: {
            data_referencia:
              data,

            tentativas_disparos:
              parse(
                "execTentativas"
              ),

            contatos_alo:
              parse(
                "execContatos"
              ),

            vendas:
              parse(
                "execVendas"
              ),

            matriculas:
              parse(
                "execMatriculas"
              ),

            resultado_periodo:
              obs
          },

          gaps: [],
          evidencias: [],

          observacao_geral:
            "Atualização via Portal EPS simplificado"
        };

        try {
          await api(
            `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/monitoring?email=${qemail()}`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify(
                  body
                )
            }
          );

          msg(
            "Atualização salva com sucesso."
          );

        } catch (error) {
          msg(
            error.message,
            false
          );
        }
      };
}


function bindEncerramento(
  campaign
) {
  document
    .getElementById(
      "finalizarExecucao"
    )
    .onclick =
      async () => {

        const responsavel =
          document
            .getElementById(
              "fimResponsavel"
            )
            .value
            .trim();

        const confirmado =
          document
            .getElementById(
              "fimConfirm"
            )
            .checked;

        if (!responsavel) {
          msg(
            "Informe o responsável pelo fechamento.",
            false
          );

          return;
        }

        if (!confirmado) {
          msg(
            "Confirme o encerramento.",
            false
          );

          return;
        }

        const parse =
          id => {
            const el =
              document.getElementById(
                id
              );

            return (
              !el ||
              el.value === ""
            )
              ? null
              : Number(
                  el.value
                );
          };

        const aprendizado =
          document
            .getElementById(
              "fimAprendizado"
            )
            .value
            .trim() ||
          null;

        const body = {
          execucao_concluida:
            true,

          execucao_dentro_vigencia:
            true,

          vendas_final:
            parse(
              "fimVendas"
            ),

          matriculas_final:
            parse(
              "fimMatriculas"
            ),

          principais_gaps:
            null,

          acoes_corretivas_realizadas:
            null,

          gaps_acoes_registrados:
            true,

          evidencias_finais_organizadas:
            true,

          aprendizados_operacionais:
            aprendizado,

          responsavel_eps_confirmou:
            true,

          responsavel_fechamento_eps:
            responsavel
        };

        try {
          await api(
            `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/close-execution?email=${qemail()}`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body:
                JSON.stringify(
                  body
                )
            }
          );

          state.detalheModo =
            "principal";

          await refreshCurrent(
            campaign.codigo_campanha
          );

          renderDetalhe();

        } catch (error) {
          msg(
            error.message,
            false
          );
        }
      };
}


async function refreshCurrent(
  code
) {
  const detail =
    await api(
      `/api/external/campaigns/${encodeURIComponent(code)}?email=${qemail()}`
    );

  state.atual =
    detail.campanha;

  const list =
    await api(
      `/api/external/campaigns?email=${qemail()}`
    );

  state.usuario =
    list.usuario;

  state.campanhas =
    list.campanhas || [];
}


/* ==========================================================
   START
========================================================== */



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

function ensureLoading() {
  let overlay = document.getElementById("siteLoading");

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "siteLoading";
    overlay.className = "v10-loading hidden";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML = `
      <div class="v10-loading-card">

        <div class="v10-loading-spinner" aria-hidden="true"></div>

        <div class="v10-loading-copy">
          <strong id="siteLoadingTitle">Processando</strong>
          <span id="siteLoadingText">Consultando os dados da campanha.</span>
        </div>

        <div class="v10-loading-clock">
          <b id="siteLoadingClock">0s</b>
        </div>

      </div>
    `;

    document.body.appendChild(overlay);
  }

  return overlay;
}

function showLoading(texto = "Consultando os dados da campanha.") {
  loadingCount += 1;

  if (loadingCount === 1) {
    loadingStart = Date.now();
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

  const overlay = ensureLoading();
  const textEl = overlay.querySelector("#siteLoadingText");

  if (textEl) {
    textEl.textContent = texto;
  }

  if (__cartaoTimer) return;

  /* O cartao so entra depois de 400ms. Requisicao rapida
     nunca chega a piscar um modal.                        */
  __cartaoTimer = setTimeout(
    () => {
      if (loadingCount < 1) return;

      overlay.classList.remove("hidden");
      requestAnimationFrame(() => overlay.classList.add("visible"));

      const tick = () => {
          const seg = Math.floor((Date.now() - loadingStart) / 1000);

          const relogio =
            document.getElementById("siteLoadingClock");

          if (relogio) {
            relogio.textContent = seg + "s";
          }

          const t = document.getElementById("siteLoadingText");

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

function hideLoading() {
  loadingCount = Math.max(0, loadingCount - 1);

  if (loadingCount > 0) return;

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

  const overlay = document.getElementById("siteLoading");

  if (!overlay) return;

  overlay.classList.remove("visible");

  setTimeout(
    () => {
      if (loadingCount > 0) return;

      overlay.classList.add("hidden");

      const relogio =
        document.getElementById("siteLoadingClock");

      if (relogio) {
        relogio.textContent = "0s";
      }

      loadingStart = 0;
    },
    180
  );
}


if (state.email) {
  carregar();
} else {
  login();
}
