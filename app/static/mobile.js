/* ==========================================================
   CELULAR
   Dois cuidados que CSS sozinho nao resolve:
   1. O menu do topo rola de lado: a aba ativa vai para o
      meio da tela, para a pessoa ver onde esta.
   2. Os paineis de filtro ocupam a tela inteira no celular.
      Ficam recolhidos atras de um botao "Filtros", com a
      quantidade de filtros ativos.
   No computador (tela larga) nada disso roda.
   ========================================================== */

(function () {
  const LARGURA = 760;
  const PAINEIS = [".hist-filtros", ".apu-filtros"];
  const abertos = {};
  let agendado = false;

  const celular = () => window.innerWidth <= LARGURA;

  function ativos(painel) {
    return [...painel.querySelectorAll("select, input")]
      .filter(el => el.type !== "date" ? (el.value || "").trim() : el.value)
      .length;
  }

  function ajustarFiltros() {
    PAINEIS.forEach(seletor => {
      const painel = document.querySelector(seletor);
      if (!painel) return;

      let botao = painel.previousElementSibling;
      if (!botao || !botao.classList.contains("mob-filtro-toggle")) {
        botao = document.createElement("button");
        botao.type = "button";
        botao.className = "mob-filtro-toggle";
        botao.onclick = () => {
          abertos[seletor] = !abertos[seletor];
          ajustarFiltros();
        };
        painel.parentNode.insertBefore(botao, painel);
      }

      const aberto = !celular() || !!abertos[seletor];
      const n = ativos(painel);

      botao.style.display = celular() ? "" : "none";
      botao.classList.toggle("aberto", aberto);
      botao.innerHTML = `<span>Filtros</span><small>${n ? `${n} ativo${n === 1 ? "" : "s"}` : "nenhum ativo"}</small>`;
      painel.classList.toggle("mob-filtro-fechado", !aberto);
    });
  }

  function centralizarAba() {
    if (!celular()) return;
    const ativa = document.querySelector(".v9-topnav button.active");
    if (ativa && ativa.scrollIntoView) {
      ativa.scrollIntoView({inline: "center", block: "nearest"});
    }
  }

  function ajustar() {
    agendado = false;
    observador.disconnect();
    try {
      ajustarFiltros();
      centralizarAba();
    } finally {
      observar();
    }
  }

  const observador = new MutationObserver(() => {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(ajustar);
  });

  function observar() {
    const raiz = document.getElementById("app") || document.body;
    observador.observe(raiz, {childList: true, subtree: true});
  }

  observar();
  window.addEventListener("resize", () => requestAnimationFrame(ajustar));
  document.addEventListener("DOMContentLoaded", ajustar);
})();