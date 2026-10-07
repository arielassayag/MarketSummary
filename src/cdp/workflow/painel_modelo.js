/* =====================================================================
   Portal CDP — módulo "modelo aberto da carteira" (carregado sob demanda pela página).
   Monta as partes abertas do processo: Mandato e metodologia (cronograma, construção, gestão de
   risco, fontes, auditoria e reprodução), o risco idiossincrático e o modelo de risco (aba Risco),
   o dimensionamento e a execução por posição (aba Carteira) e a formulação resolvida do otimizador
   (aba Comitê). Só exibe: todo número e todo texto vêm prontos de cdp.workflow.painel (modelo).
   Cada função recebe os componentes da página (window.CDP_PAINEL) e devolve as seções.
   ===================================================================== */
(function () {
"use strict";

function cards(U, rows) {
  return rows.map(function (r) { return [r.rotulo, r.texto]; });
}
function links(U, itens) {
  return U.h("ul", { class: "lk" }, U.arr(itens).map(function (x) {
    return U.h("li", null, U.extLink(x.url, x.rotulo || x.nome), x.texto || x.uso ? U.h("span", { class: "lk-s" }, sub(U, x.texto || x.uso)) : null);
  }));
}
function vinc(U, b) { return b ? U.pill("vincula", "warn") : U.h("span", { class: "muted" }, "não"); }
/* notação com subscrito vinda de Python (λ_F, κ_F ⇒ λ com F subscrito): só monta nós de texto */
function sub(U, t) {
  if (typeof t !== "string" || t.indexOf("_") < 0) return t;
  var out = [], re = /([λκσβ])_([A-Za-z]+)/g, last = 0, m;
  while ((m = re.exec(t))) { out.push(t.slice(last, m.index) + m[1]); out.push(U.h("sub", null, m[2])); last = re.lastIndex; }
  out.push(t.slice(last));
  return U.h("span", null, out);
}
function kvs(U, rows) { return U.kv(rows.map(function (r) { return [sub(U, r[0]), sub(U, r[1])]; })); }
/* celular: listas longas começam pelas primeiras linhas, com botão para ver todas (mesmo padrão da cobertura) */
function celular() { return !!(window.matchMedia && window.matchMedia("(max-width: 640px)").matches); }
function maisLinhas(U, rows, n, rotulo, desenha) {
  var holder = U.h("div", null);
  function draw(todas) {
    holder.textContent = "";
    var vis = todas || rows.length <= n ? rows : rows.slice(0, n);
    holder.appendChild(desenha(vis));
    if (vis.length < rows.length) {
      var b = U.h("button", { class: "btn mais", type: "button" }, rotulo);
      b.addEventListener("click", function () { draw(true); });
      holder.appendChild(b);
    }
  }
  draw(false);
  return holder;
}
var FMT_ARQ = { csv: "planilha (CSV)", json: "dados estruturados", jsonl: "dados estruturados", md: "texto", yaml: "parâmetros (texto)", html: "página" };
/* arquivos da publicação para conferir (portal público): lidos do catálogo de dados abertos; no espelho privado o catálogo não existe e o bloco sai */
function arquivos(U) {
  var h = U.h, lista = h("ul", { class: "lk lk-2" }, h("li", { class: "muted" }, "Carregando a lista de arquivos…"));
  var box = U.block("Arquivos para conferir", "carteira da semana, formulação, verificação e mandato — cópias fiéis do livro", lista);
  window.fetch("dados/datapackage.json", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (pk) {
    var rs = U.arr(pk.resources).filter(function (r) { return r.grupo === "carteira" || r.grupo === "auditoria" || /^configuracao\/[^/]+$/.test(r.path || ""); });
    lista.textContent = "";
    rs.forEach(function (r) { lista.appendChild(h("li", null, h("a", { href: "dados/" + r.path, download: "" }, "Baixar — " + r.description), h("span", { class: "lk-s" }, FMT_ARQ[r.format] || "arquivo"))); });
    lista.appendChild(h("li", null, h("a", { href: "SHA256SUMS", download: "" }, "Baixar — códigos de verificação de todos os arquivos publicados"), h("span", { class: "lk-s" }, "texto simples, um código por arquivo")));
    lista.appendChild(h("li", null, h("a", { href: "dados/" }, "Catálogo completo dos dados abertos"), h("span", { class: "lk-s" }, "todos os arquivos, com descrição e código de verificação")));
  }, function () { if (box.parentNode) box.parentNode.removeChild(box); });
  return box;
}

/* ------------------------------------------------------------------ Mandato e metodologia */
function mandato(U) {
  var h = U.h, M = U.obj(U.M), MT = U.obj(M.metodologia), AU = U.obj(M.auditoria), META = U.META, ST = U.ST;
  var MAND = U.obj(U.MAND), MR = U.obj(MAND.risk), MLQ = U.obj(MAND.liquidity), MDD = U.obj(MAND.drawdown), MSQ = U.obj(MAND.squeeze);
  var MSH = U.obj(MAND.shorting), MAL = U.obj(MAND.alpha), MRM = U.obj(MAND.risk_model);
  var pct = U.pct, fnum = U.fnum, NA = U.NA, out = [];
  function rng(a, b, f) { return U.isNum(a) && U.isNum(b) ? f(a) + " – " + f(b) : NA; }
  function pm0(v) { return U.isNum(v) ? "±" + pct(v) : NA; }
  function card(title, rows) {
    rows = rows.filter(function (r) { return r && r[1] !== undefined; });
    return h("div", { class: "card" }, h("h3", null, title), U.kv(rows.map(function (r) { return [r[0], r[1] === null || r[1] === "" ? NA : r[1]]; })));
  }
  var gsm = U.obj(MR.country_gross_share_max), th = U.obj(MR.theme_net_max_abs);
  var mand = Object.keys(MR).length ? h("div", { class: "cards wide" },
    card("Risco e exposição", [
      ["Volatilidade-alvo ex-ante (a.a.)", pct(MR.vol_target_annual)],
      ["Banda de volatilidade", rng(MR.vol_band_min, MR.vol_band_max, function (v) { return pct(v, 0); })],
      ["Exposição líquida", pm0(MR.net_exposure_max_abs) + " do PL"],
      ["Beta para o mercado", U.isNum(MR.beta_max_abs) ? "±" + fnum(MR.beta_max_abs, 2) : NA],
      ["Exposição bruta", rng(MR.gross_min, MR.gross_max, function (v) { return pct(v, 0); }) + " do PL"],
      ["Líquido por país / por setor", pm0(MR.country_net_max_abs) + " / " + pm0(MR.sector_net_max_abs)],
      ["Estilos (fatores)", U.isNum(MR.style_exposure_max_abs) ? "±" + fnum(MR.style_exposure_max_abs, 2) + " desvio-padrão × PL" : NA],
      Object.keys(th).length ? ["Temas", Object.keys(th).map(function (k) { return (U.THEME_PT[k] || k) + " " + pm0(th[k]); }).join(" · ")] : null,
      ["Commodities (Σ peso × beta)", pm0(MR.commodity_beta_max_abs)],
      ["Peso por nome (long / short)", pct(MR.max_long_weight) + " / " + pct(MR.max_short_weight) + (U.isNum(MR.min_position_weight) ? " · mínimo " + pct(MR.min_position_weight) : "")],
      ["Contribuição de um nome ao risco", "até " + pct(MR.max_single_name_risk_share, 0) + " da variância"],
      U.isNum(MR.idio_share_floor) ? ["Risco específico (meta / piso)", pct(MR.idio_share_goal, 0) + " / " + pct(MR.idio_share_floor, 0) + " da variância"] : null,
      ["VaR / ES 1 dia (99%)", pct(MR.var_1d_max) + " / " + pct(MR.es_1d_max) + " do PL"],
      ["Perda máxima em gap de país", pct(MR.country_stress_max_loss) + " do PL"],
      Object.keys(gsm).length ? ["Fatia máxima da exposição bruta por país", Object.keys(gsm).map(function (k) { return U.countryName(k) + " " + pct(gsm[k], 0); }).join(" · ")] : null
    ]),
    card("Liquidez", [
      ["Participação no volume diário", "long " + pct(MLQ.participation_rate, 0) + " · short " + pct(MLQ.short_participation_rate, 0)],
      ["Prazo máximo para liquidar", "long " + U.days(MLQ.max_days_to_liquidate_long) + " · short " + U.days(MLQ.max_days_to_liquidate_short)],
      ["Exposição bruta liquidável", "≥ " + pct(MLQ.min_gross_liquid_3d, 0) + " em 3 dias · ≥ " + pct(MLQ.min_gross_liquid_5d, 0) + " em 5 dias"],
      ["Volume médio diário mínimo", "long " + U.usd(MLQ.min_adtv_long_usd) + " · short " + U.usd(MLQ.min_adtv_short_usd)],
      ["Giro semanal máximo", pct(MLQ.max_weekly_turnover, 0) + " do PL"],
      ["Janela do volume médio", U.isNum(MLQ.adv_window_days) ? MLQ.adv_window_days + " pregões" : NA]
    ]),
    card("Short e aluguel", [
      ["Instrumentos com short permitido", U.arr(MSH.shortable_line_types).map(function (x) { return U.LINE_PT[x] || x; }).join(", ") || NA],
      ["Aluguel máximo", pct(MSH.max_borrow_fee) + " a.a."],
      ["Valor de mercado mínimo para short", U.usd(MSH.min_market_cap_short_usd)]
    ]),
    card("Risco de squeeze", [
      ["Escore (médio / alto)", fnum(MSQ.score_medium, 0) + " / " + fnum(MSQ.score_high, 0)],
      ["Short interest, % do free float", pct(MSQ.si_pct_float_medium, 0) + " / " + pct(MSQ.si_pct_float_high, 0)],
      ["Dias para cobrir", fnum(MSQ.days_to_cover_medium, 0) + " / " + fnum(MSQ.days_to_cover_high, 0)],
      ["Aluguel (médio / alto)", pct(MSQ.borrow_fee_medium, 0) + " / " + pct(MSQ.borrow_fee_high, 0) + (U.isNum(MSQ.br_borrow_fee_medium) ? " · B3 " + pct(MSQ.br_borrow_fee_medium, 0) + " / " + pct(MSQ.br_borrow_fee_high, 0) : "")],
      ["Squeeze alto", "short vedado"],
      ["Squeeze médio ou sem dado", U.isNum(MSQ.medium_short_cap_multiplier) ? "teto do nome × " + fnum(MSQ.medium_short_cap_multiplier, 2) : NA]
    ]),
    card("Política de controle de perdas", U.arr(MT.controle_perdas).filter(function (x) { return x.tom !== "ok"; }).map(function (x) { return [x.nivel, "drawdown de " + x.gatilho + ": " + x.acao]; })
      .concat([["Referência", "pico do patrimônio desde o início"]]))) : U.empty("Os limites do mandato não acompanham esta versão do portal; os aplicados à carteira aparecem em Risco e exposições.");
  out.push(U.sec("Mandato", "limites de investimento e de risco do fundo", mand, U.eventWindows()));

  var CR = U.obj(MT.cronograma);
  if (U.arr(CR.itens).length) {
    var side = [];
    if (U.arr(CR.proximas_datas).length) side.push(U.block("Próximos dias de montagem", CR.prazo_proxima ? "prazo da decisão em " + CR.proxima + ": " + CR.prazo_proxima + " (Brasília)" : null,
      h("ul", { class: "chips" }, CR.proximas_datas.map(function (d) { return h("li", null, U.chip(d)); }))));
    if (U.arr(CR.fechamentos).length) side.push(U.block("Fechamentos oficiais", "no próximo dia de montagem, horário de Brasília",
      U.kv(CR.fechamentos.map(function (f) { return [f.mercado, f.texto]; })),
      U.arr(CR.mercados_fechados).length ? U.note("Sem pregão: " + CR.mercados_fechados.join(", ") + ".") : null));
    out.push(U.sec("Cronograma e execução", "o dia de montagem, o prazo da decisão e o leilão de fechamento",
      h("div", { class: "cols" }, U.block(null, null, U.kv(cards(U, U.arr(MT.inaugural).concat(CR.itens))), CR.nota ? U.note(CR.nota) : null), h("div", { class: "stack" }, side))));
  }
  if (U.arr(MT.construcao).length) {
    var lim = U.arr(MT.limites);
    out.push(U.sec("Construção da carteira", "neutralização em camadas, risco específico e dimensionamento",
      h("div", { class: "cols-2" },
        U.block("Objetivo e dimensionamento", null, kvs(U, cards(U, MT.construcao))),
        U.block("Neutralização em camadas", "exposições que a carteira não carrega", U.kv(cards(U, U.arr(MT.neutralizacao))))),
      lim.length ? U.block("Limites operacionais e do mandato", "o otimizador usa o menor dos dois", U.table([
        { label: "Limite", get: function (r) { return r.limite; } },
        { label: "Operacional", num: true, get: function (r) { return r.operacional; } },
        { label: "Mandato", num: true, get: function (r) { return r.mandato; } }
      ], lim, { stack: true })) : null));
  }
  if (U.arr(MT.gestao_risco).length) out.push(U.sec("Gestão de risco", "controle de perdas, stops, gatilhos, estresse e vetos", U.block(null, null, U.kv(cards(U, MT.gestao_risco)))));

  var steps = U.arr(MT.processo);
  if (steps.length) out.push(U.sec("Processo de investimento", null, h("div", { class: "cards wide" }, steps.map(function (s) { return h("div", { class: "card" }, h("h3", null, s.rotulo), h("p", { class: "prose" }, s.texto)); }))));
  if (U.arr(MT.fontes).length) out.push(U.sec("Fontes de dados", "somente fontes públicas; cada insumo traz fonte, data de publicação e data de coleta", U.block(null, null, links(U, MT.fontes))));

  out.push(U.sec("Natureza do histórico", null, h("div", { class: "cols-2" },
    U.block(null, null, h("p", { class: "prose" }, U.plain(META.paper_trading_text) || "Carteira simulada com preços reais."), META.is_synthetic ? h("p", null, U.pill("DADOS SIMULADOS", "sim")) : null),
    U.block(null, null, U.kv([["Início", U.fdate(META.inception_date)], ["PL inicial", U.usdFull(META.inception_nav_usd)], ["Gestor", META.manager], ["Moeda base", META.base_currency]])))));

  if (AU.resultado) {
    var s = U.sec("Auditoria e reprodução", "o que é publicado, como conferir e como refazer cada número",
      h("div", { class: "audit-top" }, U.pill(AU.resultado, AU.integro ? "ok" : "warn"),
        h("p", { class: "prose" }, "Todos os números do portal são calculados por código aberto a partir de dados públicos e podem ser conferidos e refeitos por qualquer pessoa, arquivo por arquivo; os passos de IA podem ser refeitos com qualquer assistente de IA.")),
      h("div", { class: "cols-2" },
        U.block("O que é publicado", null, h("ul", { class: "lst" }, U.arr(AU.publicado).map(function (t) { return h("li", null, t); }))),
        U.block("Como conferir", null, h("ol", { class: "lst" }, U.arr(AU.passos).map(function (p) { return h("li", null, h("b", null, p.titulo + ". "), p.texto); })))),
      U.META.profile === "site" ? arquivos(U) : null,
      h("div", { class: "cols-3" },
        U.block("Documentos", AU.versao ? "no repositório público, na versão " + AU.versao : "no repositório público", links(U, AU.documentos)),
        U.block("Mandato e parâmetros", null, links(U, AU.configuracao)),
        U.block("Código", "módulos que produzem os números", links(U, AU.codigo))),
      h("p", { class: "note" }, U.extLink(AU.repositorio, "Repositório público"), " · ", U.extLink(AU.dados_abertos, "Dados abertos"), ", com o código de verificação de cada arquivo"));
    s.id = "auditoria";
    out.push(s);
  }

  var gl = [
    ["Exposição bruta (gross)", "Soma dos valores absolutos das posições long e short, em % do PL."],
    ["Exposição líquida (net)", "Longs menos shorts, em % do PL. Perto de zero = carteira neutra em mercado."],
    ["Beta", "Sensibilidade prevista da carteira a um movimento do mercado latino-americano."],
    ["Volatilidade ex-ante", "Volatilidade anual prevista pelo modelo de risco para a carteira atual."],
    ["Risco específico (idiossincrático)", "Parte da variância própria de cada empresa, depois de descontados mercado, países, setores, estilos, commodities e dólar."],
    ["Inflação de 2ª ordem (κ_F)", "Multiplicador da covariância dos fatores que compensa o erro de estimação explorado pelo otimizador."],
    ["Viés a priori", "Divisor da meta de volatilidade nas primeiras semanas do fundo: carteiras otimizadas tendem a ter o risco ex-ante subestimado."],
    ["Custo da restrição", "Ganho do objetivo, em pontos-base por ano do PL, se o limite fosse 1% mais largo; zero quando a restrição não vincula."],
    ["VaR (99%)", "Perda que só deve ser superada em 1% dos dias, segundo o modelo."],
    ["ES (99%)", "Perda média nos dias que superam o VaR (expected shortfall)."],
    ["Drawdown", "Queda do patrimônio desde o pico anterior."],
    ["Contribuição ao risco", "Parcela da variância da carteira atribuída a um nome ou fator."],
    ["Squeeze", "Alta forçada de uma ação com muitos vendidos, que obriga a recompra dos shorts."],
    ["ADTV", "Volume financeiro médio diário negociado; base para os prazos de liquidação."],
    ["Capacidade do fechamento", "Parcela do volume esperado do leilão de fechamento e da janela anterior que a ordem pode usar."],
    ["Sinal quantitativo (z)", "Escore padronizado do modelo para o emissor; positivo favorece long."],
    ["Leilão de fechamento", "Negociação no preço de fechamento do pregão, usada para executar a carteira."]
  ];
  out.push(U.sec("Glossário", null, h("div", { class: "block" }, kvs(U, gl))));
  return out;
}

/* ------------------------------------------------------------------ Risco */
function risco(U) {
  var h = U.h, R = U.obj(U.M.risco), out = [], secI = null;
  if (!U.M.risco) return out;
  if (R.disponivel) {
    var k = h("div", { class: "kpis" },
      U.tile("Específico · modelo de decisão", R.idio_decisao_texto, "com janelas de evento"),
      U.tile("Específico · modelo base", R.idio_base_texto, "sem janelas de evento"),
      U.tile("Meta / piso", R.meta_texto + " / " + R.piso_texto, R.vinculante_texto ? "vincula o " + R.vinculante_texto : null),
      U.tile("Inflação de 2ª ordem", sub(U, "κ_F " + R.kappa_texto), R.kappa_fonte),
      U.tile("Custo da neutralização", R.custo_neutralidade_texto, "alpha cedido às restrições de neutralidade"));
    var rows = U.arr(R.grupos);
    var grid = h("div", { class: "idio-g", role: "table", "aria-label": "Variância ex-ante por grupo nos modelos de decisão e base" },
      h("div", { class: "idio-r idio-h", role: "row" }, h("span", { role: "columnheader" }, "Grupo"), h("span", { role: "columnheader" }, "Modelo de decisão"), h("span", { role: "columnheader" }, "Modelo base")),
      rows.map(function (r) {
        return h("div", { class: "idio-r" + (r.grupo === "especifico" ? " idio-e" : ""), role: "row" },
          h("span", { role: "rowheader" }, r.rotulo),
          h("span", { role: "cell" }, r.barra_decisao ? h("i", { class: "idio-t" }, h("i", { class: "idio-b", style: "width:" + r.barra_decisao })) : null, h("b", null, r.decisao_texto)),
          h("span", { role: "cell" }, r.barra_base ? h("i", { class: "idio-t" }, h("i", { class: "idio-b b2", style: "width:" + r.barra_base })) : null, h("b", null, r.base_texto)));
      }));
    secI = U.sec("Risco idiossincrático", sub(U, "parcela da variância ex-ante vinda do risco próprio de cada empresa, medida com a covariância dos fatores inflada por κ_F"),
      k, h("div", { class: "cols-2" },
        U.block("Variância por grupo", "fatores comuns em escala própria; o específico é o restante", grid),
        U.block("Volatilidades da decisão", null, U.kv([["Ex-ante", R.vol_texto], ["Fatorial", R.vol_fatorial_texto], ["Específica", R.vol_especifica_texto]]),
          U.note("Meta de " + R.meta_texto + " da variância no risco específico e piso de " + R.piso_texto + ", exigidos nos dois modelos; o piso nunca é relaxado."))));
    out.push(secI);
  }
  var SR = U.obj(R.serie);
  if (U.arr(SR.datas).length) {
    var blk = U.block("Risco específico no tempo", "ex-ante diário, realizado e sem modelo em " + SR.janela + " pregões");
    blk.appendChild(U.chart(function (el) {
      U.lineChart(el, {
        labels: SR.datas, height: 220, title: "Parcela específica da variância",
        series: [{ name: "Ex-ante", values: SR.ex_ante, color: "var(--accent)" },
          { name: "Realizada", values: SR.realizada_63d, color: "var(--c3)" },
          { name: "Sem modelo (1 − R²)", values: SR.sem_modelo_63d, color: "var(--c5)", dash: true }],
        yFmt: function (v) { return U.pct(v, 0); }, tipFmt: function (v) { return U.pct(v, 1); },
        refs: [U.isNum(R.meta) ? { y: R.meta, label: "meta " + R.meta_texto } : null, U.isNum(R.piso) ? { y: R.piso, label: "piso " + R.piso_texto } : null].filter(Boolean)
      });
    }, 240));
    blk.appendChild(U.note("Realizada e sem modelo exigem ao menos 21 pregões na janela; antes disso aparecem como n/d."));
    if (secI) secI.appendChild(blk); else out.push(U.sec("Risco idiossincrático", null, blk));
  }
  if (U.arr(R.parametros).length) {
    out.push(U.sec("Modelo de risco", "parâmetros e fatores do modelo usado na decisão",
      h("div", { class: "cols-2" }, U.block("Parâmetros", null, U.kv(cards(U, R.parametros))),
        U.block("Fatores", null, U.kv(U.arr(R.fatores).map(function (f) { return [f.grupo + " (" + f.n + ")", f.texto]; }))))));
  }
  return out;
}

/* ------------------------------------------------------------------ Carteira */
function carteira(U) {
  var h = U.h, C = U.obj(U.M.carteira), out = [];
  var rows = U.arr(C.posicoes);
  if (!rows.length) return out;
  var cols = [
    { label: "Emissor", cls: "sticky", get: function (r) { return r.nome; }, render: function (r) { return h("span", null, r.nome, r.congelado ? h("span", { class: "cellsub" }, "sem pregão local") : null); } },
    { label: "Lado", get: function (r) { return r.lado; }, render: function (r) { return U.sideTag(r.lado === "long" ? "LONG" : "SHORT"); } },
    { label: "Peso", num: true, get: function (r) { return r.peso_texto; } },
    { label: "Alpha a.a.", num: true, title: "alpha esperado do modelo", get: function (r) { return r.alpha_texto; } },
    { label: "Sinal (z)", num: true, get: function (r) { return r.z_texto; } },
    { label: "Risco", num: true, title: "contribuição à variância ex-ante", get: function (r) { return r.risco_texto; } },
    { label: "Teto", num: true, title: "menor teto do lado da posição (ou da ordem, no teto de negociação)", get: function (r) { return r.teto_texto; } },
    { label: "Origem do teto", cls: "wrapcell", get: function (r) { return r.origem_texto; }, render: function (r) { return h("span", null, r.vinculante ? U.pill(r.teto_negociacao ? "no teto de negociação" : "no teto", "warn") : null, r.vinculante ? " " : null, r.origem_texto); } },
    { label: "Ordem", num: true, get: function (r) { return r.ordem_texto; } },
    { label: "Capacidade usada", num: true, title: "fração da capacidade de um fechamento", get: function (r) { return r.uso_capacidade_texto; } },
    { label: "Fechamentos", num: true, get: function (r) { return r.fechamentos_texto; } }
  ];
  /* celular: as 12 maiores posições, com botão para as demais (o detalhe de cada uma também abre na tabela de posições) */
  var N = celular() ? 12 : rows.length;
  var t = maisLinhas(U, rows, N, "Ver as " + U.int(C.n_posicoes) + " posições", function (vis) {
    var w = U.table(cols, vis, { tall: true, stack: true }), tb = w.querySelector ? w.querySelector("table") : null;
    if (tb) tb.classList.add("dim");
    return w;
  });
  var extra = [];
  if (U.arr(C.congelados).length) extra.push(U.fold("Emissores sem pregão local no fechamento", U.arr(C.congelados).length + " emissor(es) mantêm a posição", true,
    U.kv(C.congelados.map(function (x) { return [x.nome, x.motivo]; }))));
  if (U.arr(C.vetos_short).length || U.isNum(C.vetos_sem_dado)) extra.push(U.fold("Vetos de short", "emissores sem short novo nesta decisão", false,
    U.arr(C.vetos_short).length ? U.kv(C.vetos_short.map(function (x) { return [x.nome, x.motivo]; })) : null,
    U.isNum(C.vetos_sem_dado) ? U.note(C.vetos_sem_dado + " emissores com dado ausente para o veto (sinalizados, nunca tratados como livres).") : null));
  out.push(U.sec("Dimensionamento e execução", (C.sessao_texto ? "fechamento de " + C.sessao_texto + " · " : "") + "tamanho de cada posição, teto que o limita e uso da capacidade do leilão",
    t, extra, U.note("O peso sai do ótimo do objetivo (alpha contra variância residual e custo) e para no menor teto. Capacidade usada = ordem como fração do que um fechamento comporta; acima de 100% a ordem levaria mais de um fechamento.")));
  return out;
}

/* ------------------------------------------------------------------ Comitê: formulação */
function comite(U) {
  var h = U.h, F = U.obj(U.M.formulacao), out = [];
  if (!U.M.formulacao) return out;
  var termos = U.table([
    { label: "Termo", get: function (r) { return r.nome; }, render: function (r) { return sub(U, r.nome); } },
    { label: "Expressão", get: function (r) { return r.expressao; }, render: function (r) { return h("code", null, sub(U, r.expressao)); } },
    { label: "Coeficiente", num: true, get: function (r) { return r.coeficiente_texto; } },
    { label: "Valor na solução", num: true, title: "a.a., em % do PL", get: function (r) { return r.valor_texto; } }
  ], F.termos, { stack: true });
  var resumida = !!F.restricoes_resumidas;
  var k = h("div", { class: "kpis" },
    U.tile("Restrições", U.int(F.n_restricoes), resumida ? U.int(F.n_exibidas) + " exibidas nesta versão: as que vinculam e as perto do limite (formulação completa no portal público)" : "todas com limite e valor atingido"),
    U.tile("Vinculantes", U.int(F.n_vinculantes), "no limite na solução"));
  var cols = [
    { label: "Restrição", cls: "sticky", get: function (r) { return r.nome; } },
    { label: "Expressão", get: function (r) { return r.expressao; }, render: function (r) { return h("code", null, sub(U, r.expressao)); } },
    { label: "Limite", num: true, get: function (r) { return r.limite_texto; } },
    { label: "Atingido", num: true, get: function (r) { return r.valor_texto; } },
    { label: "Folga", num: true, get: function (r) { return r.folga_texto; } },
    { label: "Vincula", get: function (r) { return r.vinculante ? 1 : 0; }, render: function (r) { return vinc(U, r.vinculante); } },
    { label: "Custo da restrição", num: true, title: "ganho do objetivo se o limite fosse 1% mais largo", get: function (r) { return r.custo_texto; } }
  ];
  var cel = celular();
  var grupos = U.arr(F.grupos).map(function (g) {
    var rs = U.arr(g.restricoes), vs = rs.filter(function (r) { return r.vinculante; });
    var nG = resumida && U.isNum(g.n_exibidas) ? g.n_exibidas : g.n;
    var omit = resumida && U.isNum(g.omitidas) && g.omitidas > 0 ? " · " + U.int(g.n_exibidas) + " exibidas" : "";
    function desenha(vis) { return U.table(cols, vis, { stack: true, rowClass: function (r) { return r.vinculante ? "st-warn" : null; } }); }
    /* primeiro só as que vinculam (quando há outras), com botão para o grupo inteiro; no celular, todos os grupos começam fechados */
    var corpo = vs.length && vs.length < rs.length ? maisLinhas(U, vs.concat(rs.filter(function (r) { return !r.vinculante; })), vs.length, "Ver as " + U.int(nG) + " restrições " + (resumida ? "exibidas" : "do grupo"), desenha) : desenha(rs);
    return U.fold(g.titulo, g.n + (g.n === 1 ? " restrição" : " restrições") + (g.n_vinculantes ? " · " + g.n_vinculantes + (g.n_vinculantes === 1 ? " vincula" : " vinculam") : "") + omit, !cel && g.n_vinculantes > 0, corpo);
  });
  out.push(U.sec("Formulação da decisão", "o problema resolvido pelo otimizador na carteira vigente, com cada restrição e o seu custo",
    k, h("div", { class: "cols-2" },
      U.block("Objetivo", null, h("p", { class: "formula" }, h("code", null, sub(U, F.expressao || U.NA))), termos),
      U.block("Parâmetros da resolução", null, kvs(U, cards(U, U.arr(F.parametros))), F.nota_vol ? U.note(F.nota_vol) : null,
        U.arr(F.contagens).length ? U.kv(cards(U, F.contagens)) : null)),
    grupos, U.note("Custo da restrição: ganho do objetivo, em pontos-base por ano do PL, se o limite fosse 1% mais largo (preço-sombra × limite); zero quando a restrição não vincula.")));
  return out;
}

window.CDP_MODELO = { mandato: mandato, risco: risco, carteira: carteira, comite: comite };
})();
