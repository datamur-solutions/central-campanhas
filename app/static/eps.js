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

    /* Sessao expirada ou inexistente: volta para o login. */
    if (response.status === 401) {
      sessionStorage.removeItem("senha_ok_eps");
      window.location.href = "/portal-eps";
      return new Promise(() => {});
    }

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
      "Registrar execução",

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
          src="/static/EduNova.png"
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

  SenhaPortal.exigir(
    state.email,
    entrarComSenhaOk
  );
}


async function entrarComSenhaOk() {
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

    /* O usuario nao tem acesso aprovado. Em vez de apenas
       avisar e deixar a pessoa sem saida, criamos a
       solicitacao para a EduNova aprovar.

       Antes daqui o fluxo morria: a tela dizia "sem acesso"
       e nenhum pedido chegava ao portal interno.          */
    await solicitarPrimeiroAcesso(
      error.message
    );
  }
}


async function solicitarPrimeiroAcesso(
  mensagemOriginal
) {
  try {
    const resposta =
      await api(
        "/api/external/access/request",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify({
              email: state.email,
              nome_usuario: null
            })
        }
      );

    const acesso =
      resposta.acesso || {};

    /* O acesso pode ter sido aprovado entre a tentativa e
       este pedido. Nesse caso entra direto.              */
    if (acesso.status === "APROVADO") {
      return entrar();
    }

    login(
      acesso.novo_pedido === false
        ? (
            "Sua solicitação já está aguardando "
            + "aprovação da EduNova. Você será avisado "
            + "por e-mail quando for liberada."
          )
        : (
            "Solicitação de acesso enviada para a EduNova. "
            + "Assim que for aprovada, você poderá entrar "
            + "com este e-mail."
          )
    );

  } catch (erro) {

    /* Dominio fora da lista de EPS, por exemplo: aqui o
       pedido nao faz sentido e a mensagem do backend
       explica melhor que a original.                     */
    login(
      erro.message || mensagemOriginal
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
            src="/static/EduNova.png"
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
            data-senha-acao="trocar"
            title="Trocar senha"
            aria-label="Trocar senha"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3"/></svg>
          </button>

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
              <small>Registrar execução</small>
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

        ${metasHomeHtml(state.campanhas)}

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
      () => SenhaPortal.sair();

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


/* ==========================================================
   META DA EPS
   Aparece so quando a acao tem meta para esta EPS. Fica no
   alto do card e do detalhe: e o numero que a operacao
   persegue, entao nao pode ficar escondido.
========================================================== */

function estilosMetaEps() {
  if (document.getElementById("metaEpsEstilos")) return;

  const style = document.createElement("style");
  style.id = "metaEpsEstilos";
  style.textContent = `
    .meta-eps{
      margin:14px 0 4px;padding:16px 18px;
      border:1px solid var(--c-ink);border-radius:8px;
      background:var(--c-ink);color:#fff;
    }
    .meta-eps-topo{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
    .meta-eps-rotulo{color:#BDB9C2;font-size:13px;font-weight:500}
    .meta-eps-pct{font-size:15px;font-weight:600}
    .meta-eps-numeros{display:flex;align-items:baseline;gap:8px;margin-top:6px}
    .meta-eps-numeros strong{font-size:30px;font-weight:600;letter-spacing:-.03em;line-height:1}
    .meta-eps-numeros span{color:#BDB9C2;font-size:14px}
    .meta-eps-trilho{height:6px;margin-top:12px;border-radius:3px;background:rgba(255,255,255,.18);overflow:hidden}
    .meta-eps-trilho i{display:block;height:100%;border-radius:3px;background:#B98CF2}
    .meta-eps.batida .meta-eps-trilho i{background:#5FD18C}
    .meta-eps-rodape{margin-top:8px;color:#A5A2AC;font-size:12px}
    .meta-eps.grande{margin:0 0 16px;padding:26px 28px;border-left:6px solid #B98CF2}
    .meta-eps.grande.batida{border-left-color:#5FD18C}
    .meta-eps.grande .meta-eps-rotulo{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:#D9C8F2}
    .meta-eps.grande .meta-eps-pct{font-size:22px}
    .meta-eps.grande .meta-eps-numeros strong{font-size:56px}
    .meta-eps.grande .meta-eps-numeros span{font-size:18px}
    .meta-eps.grande .meta-eps-trilho{height:10px;margin-top:16px}
    .meta-eps.grande .meta-eps-rodape{font-size:13px;margin-top:10px}

    .orientacoes-eps{margin:0 0 20px;display:grid;gap:12px}
    .orientacao-eps{
      padding:18px 20px;border:1px solid var(--c-rule);
      border-left:4px solid var(--c-accent);border-radius:8px;
      background:var(--c-surface);
    }
    .orientacao-eps.comercial{border-left-color:var(--c-ink)}
    .orientacao-eps b{display:block;margin-bottom:8px;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--c-ink-2)}
    .orientacao-eps p{margin:0;white-space:pre-wrap;font-size:15px;line-height:1.6;color:var(--c-ink)}

    .metas-home{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin-top:16px}
    .metas-home-item{cursor:pointer}
    .metas-home-item .meta-eps{margin:0}
    .metas-home-nome{display:block;margin:0 0 8px;font-size:14px;font-weight:600;color:var(--c-ink)}
    .metas-home-nome small{color:var(--c-ink-3);font-weight:500;margin-right:6px}
  `;
  document.head.appendChild(style);
}

function metaEpsHtml(meta, grande = false) {
  if (!meta || !meta.meta) return "";

  estilosMetaEps();

  const unidade =
    meta.base === "MATRICULAS" ? "matrículas" : "vendas";

  const realizado = Number(meta.realizado || 0);
  const alvo = Number(meta.meta);
  const pct = alvo ? realizado / alvo * 100 : 0;
  const largura = Math.min(100, Math.max(0, pct));

  const fmt = valor =>
    Number(valor).toLocaleString("pt-BR", {maximumFractionDigits: 1});

  return `
    <div class="meta-eps ${grande ? "grande" : ""} ${pct >= 100 ? "batida" : ""}">
      <div class="meta-eps-topo">
        <span class="meta-eps-rotulo">${grande ? "Meta da sua EPS" : "Sua meta"} · ${unidade}</span>
        <span class="meta-eps-pct">${fmt(pct)}% atingido</span>
      </div>
      <div class="meta-eps-numeros">
        <strong>${fmt(realizado)}</strong>
        <span>de ${fmt(alvo)} ${unidade}</span>
      </div>
      <div class="meta-eps-trilho"><i style="width:${largura}%"></i></div>
      ${
        grande
          ? `<div class="meta-eps-rodape">
               ${
                 pct >= 100
                   ? "Meta atingida."
                   : `Faltam ${fmt(Math.max(0, alvo - realizado))} ${unidade} para a meta.`
               }
               O realizado considera os registros de acompanhamento e o fechamento da campanha.
             </div>`
          : ""
      }
    </div>
  `;
}


function orientacoesEpsHtml(orientacoes) {
  const planejamento = orientacoes?.planejamento;
  const comercial = orientacoes?.comercial;

  if (!planejamento && !comercial) return "";

  estilosMetaEps();

  return `
    <div class="orientacoes-eps">
      ${
        planejamento
          ? `<div class="orientacao-eps">
               <b>Orientações do Planejamento para a sua EPS</b>
               <p>${esc(planejamento)}</p>
             </div>`
          : ""
      }
      ${
        comercial
          ? `<div class="orientacao-eps comercial">
               <b>Mensagem do Comercial</b>
               <p>${esc(comercial)}</p>
             </div>`
          : ""
      }
    </div>
  `;
}

/* Painel da tela inicial: todas as metas da EPS em um lugar
   so, antes de qualquer outra lista. */
function metasHomeHtml(campanhas) {
  const comMeta =
    (campanhas || []).filter(item => item.meta_eps && item.meta_eps.meta);

  if (!comMeta.length) return "";

  return `
    <section class="v9-section">
      <div class="v9-section-head">
        <div>
          <h2>Suas metas</h2>
          <p>Onde a sua operação está em relação à meta de cada campanha.</p>
        </div>
      </div>

      <div class="metas-home">
        ${comMeta.map(item => `
          <div class="metas-home-item abrir" data-code="${esc(item.codigo_campanha)}">
            <span class="metas-home-nome">
              <small>${esc(item.codigo_campanha)}</small>${esc(item.nome_campanha)}
            </span>
            ${metaEpsHtml(item.meta_eps)}
          </div>
        `).join("")}
      </div>
    </section>
  `;
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

      ${metaEpsHtml(campaign.meta_eps)}

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

        ${metaEpsHtml(campaign.meta_eps, true)}

        ${orientacoesEpsHtml(campaign.orientacoes_eps)}

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

  bindNavegacaoEtapas(
    campaign
  );

  if (document.getElementById("diarioEps")) {
    carregarDiarioEps(campaign.codigo_campanha);
  }

  const salvarCopy =
    document.getElementById("salvarCopyExec");

  if (salvarCopy) {
    bindAtuacaoEps(campaign);

    salvarCopy.onclick = async () => {
      const caixa = document.getElementById("copyExecMsg");

      try {
        salvarCopy.disabled = true;
        salvarCopy.textContent = "Salvando...";

        await salvarAtuacaoEps(campaign.codigo_campanha);

        caixa.innerHTML =
          `<div class="notice success">Canais e copy salvos.</div>`;

      } catch (erro) {
        caixa.innerHTML =
          `<div class="notice error">${esc(erro.message)}</div>`;

      } finally {
        salvarCopy.disabled = false;
        salvarCopy.textContent = "Salvar canais e copy";
      }
    };
  }
}


/* ==========================================================
   NAVEGACAO PELA BARRA DE ETAPAS
========================================================== */

function estilosNavegacaoEps() {
  if (document.getElementById("navEpsEstilos")) return;

  const style = document.createElement("style");
  style.id = "navEpsEstilos";
  style.textContent = `
    .eps-simple-flow-step.clicavel{cursor:pointer}
    .eps-simple-flow-step.clicavel strong{text-decoration:underline;text-underline-offset:3px}
    .eps-simple-flow-step.clicavel:hover span{box-shadow:0 0 0 5px var(--c-accent-soft,#F2EAFC)}
    .eps-simple-flow-step.clicavel:focus-visible{outline:2px solid var(--c-accent,#6B21C8);outline-offset:4px;border-radius:6px}

    .diario-eps{margin-top:22px}
    .diario-eps:empty{display:none}
    .diario-eps h3{margin:0 0 4px;font-size:17px}
    .diario-eps > p{margin:0 0 12px;color:var(--c-ink-2,#5F5D68);font-size:13px}
    .diario-item{padding:12px 14px;border:1px solid var(--c-rule,#DFD8CC);border-left:3px solid var(--c-accent,#6B21C8);border-radius:6px;background:var(--c-surface,#FBFAF7);margin-bottom:8px}
    .diario-item.edunova{border-left-color:var(--c-ink,#17161B)}
    .diario-item header{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--c-ink-3,#8B8379);margin-bottom:6px}
    .diario-item header strong{color:var(--c-ink,#17161B);font-size:13px}
    .diario-item p{margin:0;white-space:pre-wrap;font-size:14px;line-height:1.55}
  `;
  document.head.appendChild(style);
}

function bindNavegacaoEtapas(campaign) {
  const status =
    campaign.status_execucao_eps ||
    "AGUARDANDO_PLANEJAMENTO_EPS";

  document
    .querySelectorAll(".eps-simple-flow-step.clicavel")
    .forEach(etapa => {
      const ir = () => {
        const indice = Number(etapa.dataset.etapa);

        state.detalheModo =
          indice === 4 && status === "EM_EXECUCAO"
            ? "encerrar"
            : "principal";

        renderDetalhe();
      };

      etapa.onclick = ir;
      etapa.onkeydown = evento => {
        if (evento.key === "Enter" || evento.key === " ") {
          evento.preventDefault();
          ir();
        }
      };
    });
}


/* ==========================================================
   DIARIO DE BORDO
   Tudo o que foi registrado em "Como foi o periodo?", da EPS
   e da EduNova, do mais recente para o mais antigo.
========================================================== */

function formatarDataDiario(texto) {
  if (!texto) return "";
  const [ano, mes, dia] = String(texto).slice(0, 10).split("-");
  return dia && mes ? `${dia}/${mes}/${ano}` : texto;
}

async function carregarDiarioEps(codigo) {
  const alvo = document.getElementById("diarioEps");
  if (!alvo) return;

  try {
    const dados = await api(
      `/api/external/campaigns/${encodeURIComponent(codigo)}/diario?email=${qemail()}`
    );

    const entradas = dados.entradas || [];
    const atual = document.getElementById("diarioEps");
    if (!atual) return;

    atual.innerHTML = `
      <h3>Diário de bordo</h3>
      <p>
        ${
          entradas.length
            ? "Tudo o que foi registrado em “Como foi o período?”, pela sua equipe e pela EduNova."
            : "Ainda não há registros. Cada atualização com “Como foi o período?” preenchido aparece aqui."
        }
      </p>
      ${entradas.map(item => `
        <article class="diario-item ${item.origem === "EDUNOVA" ? "edunova" : ""}">
          <header>
            <strong>${esc(formatarDataDiario(item.data))}</strong>
            <span>${item.origem === "EDUNOVA" ? "EduNova" : "Sua equipe"}${item.autor ? " · " + esc(item.autor) : ""}</span>
          </header>
          <p>${esc(item.texto)}</p>
        </article>
      `).join("")}
    `;
  } catch (erro) {
    alvo.innerHTML = "";
    console.warn("Diário indisponível:", erro);
  }
}


function barraEtapas(
  status
) {
  const atual =
    etapaAtual(
      status
    );

  estilosNavegacaoEps();

  /* Etapa destacada: quando a EPS abre o encerramento, o
     destaque vai para "Finalizar". */
  const destacada =
    status === "EM_EXECUCAO" && state.detalheModo === "encerrar"
      ? 4
      : atual;

  /* Clicaveis: a etapa atual e, durante a execucao, a de
     Finalizar. Etapas futuras ficam bloqueadas porque
     dependem de concluir a atual. */
  const clicavel = index =>
    index === atual
    || (status === "EM_EXECUCAO" && index === 4);

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
                  index === destacada
                    ? "active"
                    : ""
                } ${
                  clicavel(index)
                    ? "clicavel"
                    : ""
                }"
                data-etapa="${index}"
                ${
                  clicavel(index)
                    ? `role="button" tabindex="0" title="${index === 4 && status === "EM_EXECUCAO" ? "Finalizar a campanha" : "Abrir esta etapa"}"`
                    : ""
                }
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
            id="prepAtuacaoWrap"
            class="full hidden"
          >

            ${camposAtuacaoEpsHtml()}

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
          Registro de execução
        </h2>

        <p class="eps-action-intro">
          Conte como está a operação e registre o que
          aconteceu no período. Os números de venda e
          matrícula são apurados pela EduNova no encerramento,
          então você não precisa preenchê-los aqui.
          Quando a campanha terminar, clique em
          <strong>Finalizar</strong> na barra de etapas acima.
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

          <div class="full">

            <label>
              Como foi o período?
            </label>

            <textarea
              id="execObs"
              placeholder="Ex.: base veio com muito telefone inválido; ficamos sem operador na quarta; abordagem nova teve boa aceitação."
            ></textarea>

            <span class="field-help">
              É aqui que a EduNova entende o que aconteceu por
              trás dos números. Vale registrar dificuldade,
              mudança de rota ou qualquer coisa fora do
              previsto.
            </span>

          </div>

          <details class="full advanced-details eps-operational-details">

            <summary>
              Volume trabalhado no período
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

            </div>

          </details>

          <div class="full">

            <button
              class="btn btn-lg"
              id="salvarAtualizacao"
            >
              Salvar registro
            </button>

          </div>

        </div>

        <div id="msg"></div>

        <details class="advanced-details" style="margin-top:20px">
          <summary>
            Canais e copy de WhatsApp
            <span>pode preencher ou atualizar a qualquer momento</span>
          </summary>

          <div class="advanced-body">
            <p class="muted" style="margin:10px 0 14px">
              Se a operação começou pelo discador, registre aqui a copy
              quando os disparos de WhatsApp forem iniciar.
            </p>

            ${camposAtuacaoEpsHtml()}

            <div id="copyExecMsg"></div>

            <button class="btn" id="salvarCopyExec" style="margin-top:14px">
              Salvar canais e copy
            </button>
          </div>
        </details>

        <section id="diarioEps" class="diario-eps"></section>

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
          Precisamos do seu fechamento operacional. A apuração
          de resultado fica com a EduNova, que faz a análise
          final com os dados de matrícula.
        </p>

        <div class="grid2 eps-form-v52">

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

            <span class="field-help">
              É a parte mais útil deste fechamento: o que você
              escrever aqui entra na análise da EduNova e ajuda a
              desenhar a próxima campanha.
            </span>

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
                  A execução foi concluída e não haverá mais
                  acionamento desta campanha pela sua operação.
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

    <section id="diarioEps" class="diario-eps"></section>
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


/* ==========================================================
   ATUACAO POR CANAL E COPY
   ==========================================================
   A EPS ve a sugestao do Planejamento e registra como vai
   atuar de fato. Quando houver WhatsApp, entra a copy e uma
   imagem opcional.

   Tudo opcional: o plano operacional salva mesmo sem isso.
   ========================================================== */

/* Campos de canais e copy. Os mesmos ids servem na
   preparacao e na execucao, que nunca aparecem juntas, para
   bindAtuacaoEps e salvarAtuacaoEps funcionarem nas duas. */
function camposAtuacaoEpsHtml() {
  return `
            <div id="prepSugestao"></div>

            <label>
              Como vocês vão atuar?
              <span class="optional-label">opcional</span>
            </label>

            <div class="v10-filtros" style="margin:4px 0 12px">
              ${
                [
                  ["WHATSAPP", "WhatsApp"],
                  ["DISCADOR", "Discador"],
                  ["RCS", "RCS"],
                  ["TODOS", "Todos os canais"]
                ]
                  .map(([valor, rotulo]) => `
                    <label class="v10-filtro" style="cursor:pointer">
                      <input
                        type="checkbox"
                        class="prepCanal"
                        value="${valor}"
                      > ${rotulo}
                    </label>
                  `)
                  .join("")
              }
            </div>

            <div id="prepCopyWrap" class="hidden">

              <label>
                Copy do WhatsApp
                <span class="optional-label">opcional</span>
              </label>

              <textarea
                id="prepCopy"
                placeholder="Escreva a mensagem que será enviada."
              ></textarea>

              <label style="margin-top:12px">
                Imagem da copy
                <span class="optional-label">opcional</span>
              </label>

              <input
                id="prepImagem"
                type="file"
                accept="image/png,image/jpeg,image/webp"
              >

              <small class="muted">
                PNG, JPG ou WEBP, até 1,5 MB.
              </small>

              <div id="prepImagemPreview"></div>

            </div>
  `;
}


const CANAL_LABEL_EPS = {
  WHATSAPP: "WhatsApp",
  DISCADOR: "Discador",
  RCS: "RCS",
  TODOS: "Todos os canais"
};

let atuacaoImagem = null;
let atuacaoTinhaImagem = false;


function atualizarCopyVisivel() {

  const marcados =
    [...document.querySelectorAll(".prepCanal:checked")]
      .map(item => item.value);

  const mostra =
    marcados.includes("WHATSAPP")
    || marcados.includes("TODOS");

  document
    .getElementById("prepCopyWrap")
    ?.classList
    .toggle("hidden", !mostra);
}


async function bindAtuacaoEps(campaign) {

  atuacaoImagem = null;
  atuacaoTinhaImagem = false;

  document
    .querySelectorAll(".prepCanal")
    .forEach(
      item => item.onchange = atualizarCopyVisivel
    );

  const entrada =
    document.getElementById("prepImagem");

  if (entrada) {
    entrada.onchange = () => {

      const arquivo = entrada.files?.[0];

      const previa =
        document.getElementById("prepImagemPreview");

      if (!arquivo) {
        atuacaoImagem = null;
        previa.innerHTML = "";
        return;
      }

      /* Barra aqui o que o servidor recusaria depois, para
         a pessoa saber na hora e nao ao salvar.          */
      if (arquivo.size > 1500000) {
        previa.innerHTML =
          `<p class="muted">A imagem passa de 1,5 MB. Escolha outra.</p>`;
        entrada.value = "";
        atuacaoImagem = null;
        return;
      }

      const leitor = new FileReader();

      leitor.onload = () => {
        const dados = String(leitor.result);

        atuacaoImagem = {
          base64: dados.split(",")[1],
          nome: arquivo.name,
          tipo: arquivo.type
        };

        previa.innerHTML =
          `<img src="${dados}" alt="Prévia"
             style="max-width:220px;margin-top:10px;border:1px solid var(--c-rule);border-radius:6px;display:block">`;
      };

      leitor.readAsDataURL(arquivo);
    };
  }

  atualizarCopyVisivel();

  // Sugestao do Planejamento e o que ja foi salvo antes.
  try {
    const dados =
      await api(
        `/api/external/campaigns/${encodeURIComponent(campaign.codigo_campanha)}/atuacao?email=${qemail()}`
      );

    const caixa =
      document.getElementById("prepSugestao");

    if (caixa && dados.sugestao) {

      const canais =
        (dados.sugestao.canais || [])
          .map(c => CANAL_LABEL_EPS[c] || c)
          .join(", ") || "não informado";

      caixa.innerHTML = `
        <div class="notice" style="margin-bottom:14px">
          <strong>Sugestão do Planejamento: ${esc(canais)}</strong>
          ${
            dados.sugestao.justificativa
              ? `<br>${esc(dados.sugestao.justificativa)}`
              : ""
          }
        </div>
      `;
    }

    const minha = dados.minha;

    if (minha) {

      (minha.canais || []).forEach(canal => {
        const campo =
          document.querySelector(
            `.prepCanal[value="${canal}"]`
          );

        if (campo) campo.checked = true;
      });

      const copy =
        document.getElementById("prepCopy");

      if (copy && minha.copy_whatsapp) {
        copy.value = minha.copy_whatsapp;
      }

      if (minha.imagem_base64) {
        atuacaoTinhaImagem = true;

        document
          .getElementById("prepImagemPreview")
          .innerHTML =
            `<img src="data:${minha.imagem_tipo};base64,${minha.imagem_base64}"
               alt="Imagem salva"
               style="max-width:220px;margin-top:10px;border:1px solid var(--c-rule);border-radius:6px;display:block">`;
      }

      atualizarCopyVisivel();
    }

  } catch (erro) {
    // Sem sugestao ainda: a tela continua utilizavel.
  }
}


async function salvarAtuacaoEps(codigo) {

  const canais =
    [...document.querySelectorAll(".prepCanal:checked")]
      .map(item => item.value);

  const copy =
    document.getElementById("prepCopy")?.value || "";

  if (!canais.length && !copy.trim()) return;

  const corpo = {
    canais,
    copy_whatsapp: copy,
    manter_imagem: atuacaoTinhaImagem && !atuacaoImagem
  };

  if (atuacaoImagem) {
    corpo.imagem_base64 = atuacaoImagem.base64;
    corpo.imagem_nome = atuacaoImagem.nome;
    corpo.imagem_tipo = atuacaoImagem.tipo;
  }

  await api(
    `/api/external/campaigns/${encodeURIComponent(codigo)}/atuacao?email=${qemail()}`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(corpo)
    }
  );
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

      /* Canal e copy so fazem sentido com mailing. */
      document
        .getElementById(
          "prepAtuacaoWrap"
        )
        ?.classList
        .toggle(
          "hidden",
          !ativo
        );
    };

  mailing.onchange =
    toggleMailing;

  toggleMailing();

  bindAtuacaoEps(campaign);

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

          /* A atuacao vai numa chamada propria: se
             falhar, o plano operacional ja esta salvo. */
          if (mailingAtivo) {
            try {
              await salvarAtuacaoEps(
                campaign.codigo_campanha
              );
            } catch (erroAtuacao) {
              console.warn(
                "Atuacao:",
                erroAtuacao.message
              );
            }
          }

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

            /* venda e matricula sao apuradas pelo
               Planejamento no encerramento, com o dado
               do Databricks. A EPS nao preenche. */

            ocorrencias_relevantes:
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

          carregarDiarioEps(
            campaign.codigo_campanha
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

          /* vendas_final e matriculas_final ficam de fora:
             a apuracao e do Planejamento. */

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


/* ==========================================================
   SENHA
   A senha e pedida na tela de login (login_interno.html e
   login_eps.html). Aqui dentro do portal ficam so:
   - a guarda: sem senha confirmada nesta aba, volta ao login
   - "Trocar senha" no cabecalho
   - para ADMIN, redefinir a senha de outro usuario
========================================================== */

const SenhaPortal = (() => {

  let cfg = {
    portal: "",
    paginaLogin: "/",
    email: () => "",
    onSair: () => {},
    podeRedefinir: () => false,
    headersAdmin: () => ({})
  };

  const chaveSessao = () => `senha_ok_${cfg.portal}`;

  const escS = valor =>
    String(valor ?? "").replace(
      /[&<>"']/g,
      c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c])
    );

  function estilos() {
    if (document.getElementById("senhaEstilos")) return;

    const style = document.createElement("style");
    style.id = "senhaEstilos";
    style.textContent = `
      .sp-fundo{
        position:fixed;inset:0;z-index:2147483000;
        display:flex;align-items:flex-start;justify-content:center;
        padding:48px 16px;overflow-y:auto;
        background:rgba(23,22,27,.5);backdrop-filter:blur(2px);
      }
      .sp-card{
        width:100%;max-width:470px;padding:34px 36px 32px;
        border:1px solid var(--c-rule);border-radius:12px;
        background:var(--c-surface);color:var(--c-ink);
        box-shadow:0 24px 70px rgba(23,22,27,.28);
      }
      .sp-kicker{
        display:flex;align-items:center;gap:11px;margin-bottom:14px;
        color:var(--c-ink-3);font-size:14px;font-weight:500;
      }
      .sp-kicker::before{content:"";width:24px;height:2px;background:var(--c-accent)}
      .sp-card h2{margin:0;font-size:30px;font-weight:600;line-height:1.05;letter-spacing:-.04em}
      .sp-sub{margin:10px 0 24px;color:var(--c-ink-2);font-size:15px;line-height:1.5}
      .sp-campo + .sp-campo{margin-top:16px}
      .sp-campo label{display:block;margin:0 0 8px;color:var(--c-ink-2);font-size:14px;font-weight:500}
      .sp-campo input,.sp-campo select{
        width:100%;height:50px;padding:0 15px;
        border:1px solid var(--c-rule);border-radius:8px;
        background:var(--c-surface);color:var(--c-ink);font:inherit;font-size:16px;
      }
      .sp-campo input:focus,.sp-campo select:focus{
        border-color:var(--c-accent);outline:none;box-shadow:0 0 0 3px var(--c-accent-soft);
      }
      .sp-dica{margin-top:8px;color:var(--c-ink-3);font-size:13px;line-height:1.45}
      .sp-msg{margin-top:14px;font-size:14px;line-height:1.45}
      .sp-msg.erro{color:var(--c-stop)}
      .sp-msg.ok{color:var(--c-ok)}
      .sp-acoes{display:flex;gap:10px;margin-top:22px}
      .sp-btn{
        flex:1;min-height:50px;border:1px solid var(--c-ink);border-radius:8px;
        background:var(--c-ink);color:#fff;font:inherit;font-size:16px;font-weight:500;cursor:pointer;
      }
      .sp-btn:hover{background:#000}
      .sp-btn[aria-busy="true"]{opacity:.7;pointer-events:none}
      .sp-btn.sec{background:transparent;color:var(--c-ink);border-color:var(--c-rule)}
      .sp-btn.sec:hover{background:var(--c-paper);border-color:var(--c-ink-3)}
      .sp-sep{margin:28px 0 22px;border:0;border-top:1px solid var(--c-rule)}
      .sp-card h3{margin:0 0 6px;font-size:18px;font-weight:600;letter-spacing:-.02em}
      @media (max-width:560px){.sp-card{padding:26px 22px}.sp-card h2{font-size:25px}}
    `;
    document.head.appendChild(style);
  }

  async function post(url, body, headers = {}) {
    const r = await fetch(url, {
      method: "POST",
      headers: Object.assign({"Content-Type": "application/json"}, headers),
      body: JSON.stringify(body)
    });

    let d = {};
    try { d = await r.json(); } catch {}

    if (!r.ok) {
      throw new Error(
        typeof d.detail === "string"
          ? d.detail
          : "Não foi possível concluir. Tente novamente."
      );
    }

    return d;
  }

  function fechar() {
    const atual = document.getElementById("senhaFundo");
    if (atual) atual.remove();
  }

  function mensagem(caixa, texto, tipo) {
    caixa.className = `sp-msg ${tipo}`;
    caixa.textContent = texto;
  }

  async function ocupado(botao, tarefa) {
    botao.setAttribute("aria-busy", "true");
    try {
      await tarefa();
    } finally {
      botao.removeAttribute("aria-busy");
    }
  }

  /* ---------- Trocar senha ---------- */

  function abrirTroca() {
    estilos();
    fechar();

    const email = cfg.email();
    const admin = cfg.podeRedefinir();

    const fundo = document.createElement("div");
    fundo.className = "sp-fundo";
    fundo.id = "senhaFundo";

    fundo.innerHTML = `
      <div class="sp-card" role="dialog" aria-modal="true" aria-labelledby="spTitulo">
        <div class="sp-kicker">Sua conta</div>
        <h2 id="spTitulo">Trocar senha</h2>
        <p class="sp-sub">${escS(email)}</p>

        <div class="sp-campo">
          <label for="spAtual">Senha atual</label>
          <input id="spAtual" type="password" autocomplete="current-password">
        </div>
        <div class="sp-campo">
          <label for="spNova">Nova senha</label>
          <input id="spNova" type="password" autocomplete="new-password">
          <div class="sp-dica">Mínimo de 8 caracteres, com letras e números.</div>
        </div>
        <div class="sp-campo">
          <label for="spConf">Confirme a nova senha</label>
          <input id="spConf" type="password" autocomplete="new-password">
        </div>

        <div class="sp-msg" id="spMsg"></div>

        <div class="sp-acoes">
          <button class="sp-btn sec" id="spCancelar">Fechar</button>
          <button class="sp-btn" id="spSalvar">Salvar nova senha</button>
        </div>

        ${
          admin
            ? `
              <hr class="sp-sep">
              <h3>Redefinir senha de um usuário</h3>
              <p class="sp-sub" style="margin-bottom:18px">
                Apaga a senha atual da pessoa. No próximo acesso, ela cria uma nova.
              </p>
              <div class="sp-campo">
                <label for="spRedEmail">E-mail do usuário</label>
                <input id="spRedEmail" type="email" spellcheck="false">
              </div>
              <div class="sp-campo">
                <label for="spRedPortal">Portal</label>
                <select id="spRedPortal">
                  <option value="interno">Interno</option>
                  <option value="eps">EPS</option>
                </select>
              </div>
              <div class="sp-msg" id="spRedMsg"></div>
              <div class="sp-acoes">
                <button class="sp-btn sec" id="spRedefinir">Redefinir senha</button>
              </div>
            `
            : ""
        }
      </div>
    `;

    document.body.appendChild(fundo);
    fundo.querySelector("#spAtual").focus();

    fundo.onclick = e => { if (e.target === fundo) fechar(); };
    fundo.onkeydown = e => { if (e.key === "Escape") fechar(); };
    fundo.querySelector("#spCancelar").onclick = fechar;

    const botao = fundo.querySelector("#spSalvar");
    const msg = fundo.querySelector("#spMsg");

    const salvar = () => ocupado(botao, async () => {
      const atual = fundo.querySelector("#spAtual").value;
      const nova = fundo.querySelector("#spNova").value;
      const conf = fundo.querySelector("#spConf").value;

      if (!atual || !nova) {
        return mensagem(msg, "Preencha a senha atual e a nova senha.", "erro");
      }

      if (nova !== conf) {
        return mensagem(msg, "A confirmação não confere com a nova senha.", "erro");
      }

      try {
        await post("/api/auth/senha/trocar", {
          portal: cfg.portal,
          email,
          senha_atual: atual,
          nova_senha: nova
        });

        ["#spAtual", "#spNova", "#spConf"].forEach(s => fundo.querySelector(s).value = "");
        mensagem(msg, "Senha alterada. Use a nova senha no próximo acesso.", "ok");

      } catch (erro) {
        mensagem(msg, erro.message, "erro");
      }
    });

    botao.onclick = salvar;
    ["#spAtual", "#spNova", "#spConf"].forEach(
      s => fundo.querySelector(s).onkeydown = e => { if (e.key === "Enter") salvar(); }
    );

    if (admin) {
      const red = fundo.querySelector("#spRedefinir");
      const redMsg = fundo.querySelector("#spRedMsg");

      red.onclick = () => ocupado(red, async () => {
        const alvo = fundo.querySelector("#spRedEmail").value.trim().toLowerCase();
        const portal = fundo.querySelector("#spRedPortal").value;

        if (!alvo) return mensagem(redMsg, "Informe o e-mail do usuário.", "erro");
        if (!confirm(`Redefinir a senha de ${alvo}?`)) return;

        try {
          await post(
            "/api/internal/usuarios/senha/redefinir",
            {portal, email: alvo},
            cfg.headersAdmin()
          );
          mensagem(redMsg, `Senha de ${alvo} redefinida. No próximo acesso, a pessoa cria uma nova.`, "ok");
        } catch (erro) {
          mensagem(redMsg, erro.message, "erro");
        }
      });
    }
  }

  /* ---------- Guarda ----------
     Sem senha confirmada nesta aba para este e-mail, volta
     para a tela de login, que pede a senha.               */

  function exigir(email, onOk) {
    email = (email || "").trim().toLowerCase();

    if (email && sessionStorage.getItem(chaveSessao()) === email) {
      return onOk();
    }

    window.location.href = cfg.paginaLogin;
  }

  async function sair() {
    sessionStorage.removeItem(chaveSessao());
    fechar();

    /* Apaga o cookie de sessao no servidor. */
    try {
      await fetch("/api/auth/sair", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({portal: cfg.portal})
      });
    } catch {}

    cfg.onSair();
  }

  function configurar(opcoes) {
    cfg = Object.assign(cfg, opcoes);
  }

  /* Botoes do cabecalho: data-senha-acao="trocar" | "sair" */
  document.addEventListener("click", evento => {
    const alvo = evento.target.closest("[data-senha-acao]");
    if (!alvo) return;

    evento.preventDefault();

    if (alvo.dataset.senhaAcao === "trocar") abrirTroca();
    if (alvo.dataset.senhaAcao === "sair") sair();
  });

  return {configurar, exigir, abrirTroca, sair};
})();


SenhaPortal.configurar({
  portal: "eps",
  paginaLogin: "/portal-eps",
  email: () => state.email,
  onSair: () => {
    localStorage.removeItem(
      "portal_eps_email"
    );

    state.email = "";

    window.location.href = "/portal-eps";
  }
});


if (state.email) {
  SenhaPortal.exigir(
    state.email,
    carregar
  );
} else {
  window.location.href = "/portal-eps";
}