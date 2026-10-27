/* ==========================================================
   DEMO — DADOS DE EXEMPLO
   ==========================================================
   Substitui as chamadas de API por respostas fixas, dentro
   do proprio navegador.

   O interno.js e o eps.js rodam SEM NENHUMA ALTERACAO: esta
   camada apenas intercepta o fetch antes deles carregarem.
   Ou seja, o que aparece na tela e o sistema de verdade —
   so os dados sao ficticios.

   Nada aqui toca o Databricks nem guarda informacao. Ao
   recarregar a pagina, tudo volta ao estado inicial.
   ========================================================== */

(function () {
  "use strict";

  const hoje = new Date();

  function dia(offset) {
    const d = new Date(hoje);
    d.setDate(d.getDate() + offset);
    return d.toISOString().slice(0, 10);
  }

  function instante(offset) {
    const d = new Date(hoje);
    d.setDate(d.getDate() + offset);
    return d.toISOString();
  }

  // ----------------------------------------------------------
  // USUARIO INTERNO
  // ----------------------------------------------------------

  const usuarioInterno = {
    email_usuario: "planejamento@edunova.com.br",
    nome_usuario: "Equipe de Planejamento",
    perfil: "ADMIN",
    ativo: true
  };

  // ----------------------------------------------------------
  // CAMPANHAS
  //
  // Cobrem as cinco etapas do fluxo, para a demonstracao
  // mostrar o caminho inteiro numa tela so.
  // ----------------------------------------------------------

  const campanhas = [
    {
      codigo_campanha: "CAM-024",
      nome_campanha:
        "Reoferta para inscritos sem matrícula — Graduação EAD",
      produto: "GRADUACAO",
      tipo_acao: "COMERCIAL",
      status_campanha: "CADASTRADA_PLANEJAMENTO",
      etapa_pop: "PLANEJAR",
      responsavel_planejamento: "planejamento@edunova.com.br",
      responsavel_comercial: "comercial@edunova.com.br",
      dt_inicio_prevista: dia(3),
      dt_fim_prevista: dia(33),
      dt_criacao: instante(-2),
      objetivo_campanha:
        "Converter inscritos que não concluíram a matrícula no " +
        "ciclo atual de Graduação EAD.",
      resultado_esperado:
        "Recuperar ao menos 8% da base trabalhada em matrícula.",
      publico_alvo:
        "Inscritos sem matrícula há mais de 7 dias, com " +
        "documentação iniciada.",
      eps: "VOXA",
      status_execucao_eps: null,
      liberada_para_eps: false
    },

    {
      codigo_campanha: "CAM-025",
      nome_campanha:
        "Resgate de boletos vencidos — Presencial",
      produto: "GRADUACAO",
      tipo_acao: "COMERCIAL",
      status_campanha: "EM_VALIDACAO_COMERCIAL",
      etapa_pop: "VALIDAR",
      responsavel_planejamento: "planejamento@edunova.com.br",
      responsavel_comercial: "comercial@edunova.com.br",
      dt_inicio_prevista: dia(1),
      dt_fim_prevista: dia(21),
      dt_criacao: instante(-5),
      objetivo_campanha:
        "Regularizar inscritos com boleto vencido antes do " +
        "fechamento do ciclo.",
      resultado_esperado:
        "Reduzir a evasão por inadimplência na virada do ciclo.",
      publico_alvo:
        "Inscritos com boleto vencido entre 3 e 20 dias.",
      eps: "VOXA",
      status_execucao_eps: null,
      liberada_para_eps: false
    },

    {
      codigo_campanha: "CAM-023",
      nome_campanha:
        "Ativação de leads frios — base do mês anterior",
      produto: "POS_GRADUACAO",
      tipo_acao: "COMERCIAL",
      status_campanha: "ENVIADA_EPS",
      etapa_pop: "EXECUTAR",
      responsavel_planejamento: "planejamento@edunova.com.br",
      responsavel_comercial: "comercial@edunova.com.br",
      dt_inicio_prevista: dia(-12),
      dt_fim_prevista: dia(18),
      dt_criacao: instante(-20),
      objetivo_campanha:
        "Reengajar leads de Pós que não avançaram na jornada.",
      resultado_esperado:
        "Gerar novo contato efetivo em 25% da base trabalhada.",
      publico_alvo:
        "Leads sem interação nos últimos 30 dias.",
      eps: "VOXA",
      status_execucao_eps: "EM_EXECUCAO",
      liberada_para_eps: true,
      dt_handoff: instante(-14),
      dt_liberacao_eps: instante(-13)
    },

    {
      codigo_campanha: "CAM-022",
      nome_campanha:
        "Rematrícula antecipada — Técnico",
      produto: "TECNICO",
      tipo_acao: "COMERCIAL",
      status_campanha: "PARCIALMENTE_LIBERADA_EPS",
      etapa_pop: "HANDOFF",
      responsavel_planejamento: "planejamento@edunova.com.br",
      responsavel_comercial: "comercial@edunova.com.br",
      dt_inicio_prevista: dia(-4),
      dt_fim_prevista: dia(26),
      dt_criacao: instante(-15),
      objetivo_campanha:
        "Antecipar a rematrícula dos alunos concluintes.",
      resultado_esperado:
        "Antecipar 30% das rematrículas previstas para o ciclo.",
      publico_alvo:
        "Alunos do último módulo, sem pendência financeira.",
      eps: "VOXA",
      status_execucao_eps: "GO_LIVE_APROVADO",
      liberada_para_eps: true,
      dt_handoff: instante(-6),
      dt_liberacao_eps: instante(-5)
    },

    {
      codigo_campanha: "CAM-019",
      nome_campanha:
        "Rematrícula 26.1 — base de inativos",
      produto: "GRADUACAO",
      tipo_acao: "COMERCIAL",
      status_campanha: "ENCERRADA_EDUNOVA",
      etapa_pop: "ENCERRAR",
      responsavel_planejamento: "planejamento@edunova.com.br",
      responsavel_comercial: "comercial@edunova.com.br",
      dt_inicio_prevista: dia(-60),
      dt_fim_prevista: dia(-10),
      dt_criacao: instante(-70),
      objetivo_campanha:
        "Recuperar alunos inativos do ciclo anterior.",
      resultado_esperado:
        "Reativar parte da base inativa antes do início das aulas.",
      publico_alvo:
        "Alunos sem rematrícula no ciclo anterior.",
      eps: "VOXA",
      status_execucao_eps: "EXECUCAO_FINALIZADA",
      liberada_para_eps: true,
      dt_handoff: instante(-58),
      dt_liberacao_eps: instante(-57)
    }
  ];

  const acessosPendentes = [
    {
      solicitacao_uuid: "demo-0001",
      email_usuario: "operador@voxa.example.com",
      nome_usuario: "Novo operador VOXA",
      dominio_email: "voxa.example.com",
      eps_identificada: "VOXA",
      dt_solicitacao: instante(-1),
      status_solicitacao: "PENDENTE"
    }
  ];

  const notificacoes = [
    {
      notificacao_uuid: "demo-n1",
      codigo_campanha: "CAM-023",
      tipo_evento: "EPS_INICIOU_ATUACAO",
      assunto:
        "[Central de Campanhas] VOXA iniciou atuação | CAM-023",
      destinatarios_to: "planejamento@edunova.com.br",
      destinatarios_cc: null,
      resumo_evento:
        "A EPS VOXA iniciou a execução da campanha.",
      status_envio: "ENVIADO",
      erro_envio: null,
      dt_criacao: instante(-12),
      origem_notificacao: "CAMPANHA"
    },
    {
      notificacao_uuid: "demo-n2",
      codigo_campanha: "CAM-019",
      tipo_evento: "EPS_FINALIZOU_ATUACAO",
      assunto:
        "[Central de Campanhas] VOXA finalizou atuação | CAM-019",
      destinatarios_to: "planejamento@edunova.com.br",
      destinatarios_cc: null,
      resumo_evento:
        "A EPS VOXA finalizou sua atuação na campanha.",
      status_envio: "ENVIADO",
      erro_envio: null,
      dt_criacao: instante(-9),
      origem_notificacao: "CAMPANHA"
    },
    {
      notificacao_uuid: "demo-n3",
      codigo_campanha: null,
      tipo_evento: "NOVO_ACESSO_EPS_SOLICITADO",
      assunto:
        "[Central de Campanhas] Novo acesso EPS | VOXA",
      destinatarios_to: "planejamento@edunova.com.br",
      destinatarios_cc: null,
      resumo_evento:
        "Novo acesso solicitado por novo.operador@" +
        "voxa.example.com para a EPS VOXA.",
      status_envio: "PENDENTE",
      erro_envio: null,
      dt_criacao: instante(-1),
      origem_notificacao: "ACESSO_EPS"
    }
  ];

  // ----------------------------------------------------------
  // ROTEADOR
  // ----------------------------------------------------------

  function campanhasDaEps() {
    return campanhas.filter(
      c => c.liberada_para_eps === true
    );
  }

  function acharCampanha(url) {
    const m = url.match(/campaigns\/([A-Za-z0-9-]+)/);
    if (!m) return null;

    const codigo = decodeURIComponent(m[1]).toUpperCase();

    return campanhas.find(
      c => c.codigo_campanha.toUpperCase() === codigo
    ) || null;
  }

  function responder(url, metodo) {
    const u = String(url);

    // ---- usuario interno ----
    if (u.includes("/api/me")) {
      return {
        email: usuarioInterno.email_usuario,
        nome: usuarioInterno.nome_usuario,
        perfil: usuarioInterno.perfil,
        ativo: usuarioInterno.ativo
      };
    }

    // ---- escritas: aceitam e avisam que e demo ----
    if (metodo !== "GET") {
      return {
        sucesso: true,
        mensagem:
          "Ambiente de demonstração: a ação foi aceita, " +
          "mas nada foi gravado.",
        campanha: {
          codigo_campanha: "CAM-DEMO"
        }
      };
    }

    // ---- portal EPS ----
    if (u.includes("/api/external/campaigns")) {
      const uma = acharCampanha(u);

      if (uma) {
        return {
          usuario: {
            email: "operador@voxa.example.com",
            nome: "VOXA",
            eps: "VOXA"
          },
          campanha: Object.assign({}, uma, {
            escopos: [
              {
                escopo_uuid: "demo-e1",
                produto: uma.produto,
                frente_pos: null,
                supercanal: "HUNTER",
                outro_supercanal_descricao: null,
                modalidade: "EAD"
              }
            ],
            kpis: [
              {
                campanha_kpi_uuid: "demo-k1",
                nome_kpi: "Matrículas recuperadas",
                kpi_principal: true,
                descricao_kpi:
                  "Matrículas efetivadas a partir da base " +
                  "trabalhada.",
                baseline_tipo: "HISTORICO",
                baseline_descricao: "Ciclo anterior",
                baseline_valor: 6.2,
                meta_descricao: "Superar o ciclo anterior",
                meta_valor: 8,
                unidade_medida: "%",
                regra_atribuicao: "Último toque",
                frequencia_reporte: "Semanal",
                ritmo_esperado: "Crescente"
              }
            ]
          })
        };
      }

      const lista = campanhasDaEps();

      return {
        usuario: {
          email: "operador@voxa.example.com",
          nome: "VOXA",
          eps: "VOXA"
        },
        quantidade: lista.length,
        campanhas: lista
      };
    }

    // ---- portal interno ----
    if (u.includes("/api/internal/external-access/pending")) {
      return {
        quantidade: acessosPendentes.length,
        solicitacoes: acessosPendentes
      };
    }

    if (u.includes("/api/internal/closure-ready")) {
      const prontas = campanhas.filter(
        c => c.status_execucao_eps === "EXECUCAO_FINALIZADA"
      );

      return {
        quantidade: prontas.length,
        campanhas: prontas
      };
    }

    if (u.includes("/api/internal/notifications/provider-status")) {
      return {
        provider_configurado: true,
        provider: "Power Automate",
        detalhe: "Ambiente de demonstração"
      };
    }

    if (u.includes("/api/internal/notifications/automation-status")) {
      return {
        automacao_ativa: true,
        pendentes: 1,
        enviadas: 2,
        erros: 0,
        detalhe: "Ambiente de demonstração"
      };
    }

    if (u.includes("/api/internal/notifications")) {
      return {
        quantidade: notificacoes.length,
        notificacoes: notificacoes
      };
    }

    if (u.includes("/api/internal/campaigns")) {
      const uma = acharCampanha(u);

      if (uma && !u.endsWith("/campaigns")) {
        return {
          campanha: uma,
          escopos: [],
          kpis: [],
          historico: [],
          workflow: []
        };
      }

      return {
        usuario: {
          email: usuarioInterno.email_usuario,
          perfil: usuarioInterno.perfil
        },
        quantidade: campanhas.length,
        campanhas: campanhas
      };
    }

    return {};
  }

  // ----------------------------------------------------------
  // INTERCEPTA O FETCH
  //
  // O atraso de 260ms nao e enfeite: sem ele a tela responde
  // instantaneamente e a demonstracao fica irreal, alem de
  // esconder o indicador de carregamento que construimos.
  // ----------------------------------------------------------

  const fetchOriginal = window.fetch;

  window.fetch = function (url, options) {
    const u = String(url);

    if (!u.includes("/api/")) {
      return fetchOriginal.apply(this, arguments);
    }

    const metodo = ((options && options.method) || "GET")
      .toUpperCase();

    const corpo = responder(u, metodo);

    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve({
          ok: true,
          status: 200,
          json: function () {
            return Promise.resolve(corpo);
          },
          text: function () {
            return Promise.resolve(JSON.stringify(corpo));
          }
        });
      }, 260);
    });
  };

  // O portal EPS identifica o usuario pelo e-mail guardado.
  if (!localStorage.getItem("portal_eps_email")) {
    localStorage.setItem(
      "portal_eps_email",
      "operador@voxa.example.com"
    );
  }
})();