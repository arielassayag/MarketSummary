/* Portal CDP — aba "Cobertura de ativos" (módulo carregado sob demanda pela casca do portal).
   Este módulo só ESCREVE e POSICIONA: todo número exibido chega formatado (campos *_texto e
   rótulos) e toda geometria chega pronta, em coordenadas de 0 a 100 (x da esquerda, y do topo),
   dos arquivos cobertura*.json gerados por cdp.workflow.painel_cobertura (código Python testado).
   Nenhuma conta é feita aqui: nem retorno, nem diferença, nem escala de gráfico.
   Uso: window.CDP_COBERTURA.render(painel, ctx) e window.CDP_COBERTURA.abrir(id) (ficha do
   ativo; a casca chama ao navegar para #cobertura:<id>). ctx (opcional, da casca):
     ctx.alvo     id a abrir na ficha ao montar a aba;
     ctx.navegar  função da casca que leva a "#cobertura:<id>" (sem ela, o módulo cuida do endereço);
     ctx.base     prefixo relativo dos arquivos de dados (padrão: mesma pasta da página);
     ctx.dados    {arquivo: dados} já carregados (cópia local; também lidos de #cdp-cobertura-dados). */
(function () {
"use strict";

var VERSAO = "cdp-cobertura-modulo/1";
var NA = "n/d";
var ARQ = "cobertura.json";
var ARQ_PRECOS = "cobertura-precos.json";
var ELEMENTO_LOCAL = "cdp-cobertura-dados";

/* ---------------------------------------------------------------- utilidades (sem contas) */
function has(x) { return x !== null && x !== undefined && x !== ""; }
function arr(x) { return Array.isArray(x) ? x : []; }
function obj(x) { return x && typeof x === "object" && !Array.isArray(x) ? x : {}; }
function txt(x) { return has(x) ? String(x) : NA; }
function each(a, fn) { var l = arr(a); for (var i = 0; i < l.length; i++) fn(l[i], i); }
function h(tag, a) {
  var el = document.createElement(tag);
  if (a) {
    Object.keys(a).forEach(function (k) {
      var v = a[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "style") el.setAttribute("style", v);
      else if (k.indexOf("on") === 0 && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : String(v));
    });
  }
  for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
  return el;
}
function add(el, c) {
  if (c === null || c === undefined || c === false) return;
  if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
  if (c.nodeType) { el.appendChild(c); return; }
  el.appendChild(document.createTextNode(String(c)));
}
var SVGNS = "http://www.w3.org/2000/svg";
function S(tag, a) {
  var el = document.createElementNS(SVGNS, tag);
  Object.keys(a || {}).forEach(function (k) { if (has(a[k])) el.setAttribute(k, String(a[k])); });
  return el;
}
function pctStyle(prop, v) { return prop + ":" + v + "%"; }
function link(url, label) {
  return (typeof url === "string" && /^https?:\/\/[^\s]+$/i.test(url))
    ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, label || url)
    : h("span", null, label || NA);
}

/* formas sem perda do exportador ({"_colunas"}, {"_rep"}, {"_partes"}, {"_igual"}): desfeitas
   aqui, como na casca — só leitura e repetição, nenhuma conta */
function unrep(c) {
  if (!c || typeof c !== "object" || Array.isArray(c) || !c._rep) return c || [];
  var v = arr(c._rep.v), n = arr(c._rep.n), out = [];
  for (var k = 0; k < v.length; k++) { for (var j = 0; j < n[k]; j++) out.push(v[k]); }
  return out;
}
function expandir(x) {
  if (Array.isArray(x)) return x.map(expandir);
  if (!x || typeof x !== "object") return x;
  var keys = Object.keys(x);
  if (keys.length === 1 && Array.isArray(x._partes)) return x._partes.join("");
  if (x._colunas && typeof x._colunas === "object" && typeof x._n === "number") {
    var rows = [], faltam = obj(x._faltam);
    for (var i = 0; i < x._n; i++) rows.push({});
    Object.keys(x._colunas).forEach(function (col) {
      var vals = unrep(x._colunas[col]), skip = {}, dot = col.indexOf(".");
      arr(faltam[col]).forEach(function (k) { skip[k] = 1; });
      rows.forEach(function (row, r) {
        if (skip[r]) return;
        var v = expandir(vals[r]);
        if (dot > 0) {
          var a = col.slice(0, dot), b = col.slice(dot).replace(".", "");
          if (!row[a] || typeof row[a] !== "object") row[a] = {};
          row[a][b] = v;
        } else row[col] = v;
      });
    });
    return rows.map(expandir);
  }
  var out = {};
  keys.forEach(function (k) { out[k] = expandir(x[k]); });
  keys.forEach(function (k) {
    var v = out[k], ref = v && typeof v === "object" && !Array.isArray(v) ? v._igual : null;
    if (typeof ref !== "string") return;
    var src = out[ref];
    if (!src || typeof src !== "object" || Array.isArray(src) || src._igual !== undefined) return;
    var cp = {};
    Object.keys(src).forEach(function (kk) { cp[kk] = src[kk]; });
    Object.keys(v).forEach(function (kk) { if (kk !== "_igual") cp[kk] = v[kk]; });
    out[k] = cp;
  });
  return out;
}

/* ---------------------------------------------------------------- dados */
var CTX = {}, CACHE = {}, LOCAL = null;
function local() {
  if (LOCAL !== null) return LOCAL;
  LOCAL = obj(CTX.dados);
  var el = document.getElementById(ELEMENTO_LOCAL);
  if (el && !Object.keys(LOCAL).length) {
    try { LOCAL = obj(JSON.parse(el.textContent || "null")); } catch (e) { LOCAL = {}; }
  }
  return LOCAL;
}
function carregar(nome) {
  if (CACHE[nome]) return CACHE[nome];
  var embutido = local()[nome];
  if (embutido) { CACHE[nome] = Promise.resolve(expandir(embutido)); return CACHE[nome]; }
  CACHE[nome] = window.fetch([CTX.base || "", nome].join(""), { cache: "no-store" }).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(expandir);
  CACHE[nome].catch(function () { delete CACHE[nome]; });
  return CACHE[nome];
}

/* ---------------------------------------------------------------- componentes (classes da casca) */
function sec(id, title, sub) {
  var s = h("section", { class: "sec", id: id }, h("div", { class: "sec-h" }, h("h2", null, title), sub ? h("span", { class: "sub" }, sub) : null));
  for (var i = 3; i < arguments.length; i++) add(s, arguments[i]);
  return s;
}
function block(title, sub) {
  var b = h("div", { class: "block" });
  if (title) b.appendChild(h("div", { class: "block-h" }, h("h3", null, title), sub ? h("span", { class: "sub" }, sub) : null));
  for (var i = 2; i < arguments.length; i++) add(b, arguments[i]);
  return b;
}
function fold(title, sub, open) {
  var body = h("div", { class: "fold-b" });
  for (var i = 3; i < arguments.length; i++) add(body, arguments[i]);
  return h("details", { class: "fold", open: open ? true : null }, h("summary", null, h("span", null, title), sub ? h("span", { class: "sub" }, sub) : null), body);
}
function tile(label, value, sub, extra) {
  return h("div", { class: "tile" }, h("div", { class: "tile-l" }, label), h("div", { class: "tile-v" }, value), sub ? h("div", { class: "tile-s" }, sub) : null, extra || null);
}
function note(t) { return h("p", { class: "note" }, t); }
function empty(t) { return h("p", { class: "empty" }, t); }
function kv(rows) {
  var dl = h("dl", { class: "kv" });
  each(rows, function (r) { dl.appendChild(h("dt", null, txt(r.t))); dl.appendChild(h("dd", null, txt(r.v))); });
  return dl;
}
var TOM_PILL = { compra: "cv-rt-compra", venda: "cv-rt-venda", neutro: "k-na", revisao: "k-warn", sem: "k-na", ref: "k-info" };
/* Neutro com confiança C: o alvo é publicado, mas a confiança não sustenta Compra nem Venda */
function ratingTxt(u) { return u && u.rating === "Neutro" && u.confianca === "C" ? "Neutro (confiança C)" : (u ? u.rating : ""); }
function ratingPill(r, tom) { return h("span", { class: "pill " + (TOM_PILL[tom] || "k-na") }, txt(r)); }
function legenda(itens) {
  return h("div", { class: "legend" }, itens.map(function (it) { return h("span", null, h("i", { class: it[0] }), it[1]); }));
}
function leitura(t, n, asof) {
  return h("p", { class: "src" }, h("b", null, "Leitura: "), t, has(n) ? " N = " + n + "." : "", has(asof) ? " Retrato de " + dataBR(asof) + "." : "");
}
function dataBR(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? m[3] + "/" + m[2] + "/" + m[1] : txt(iso);
}
/* tabela simples (fallback acessível de cada gráfico e listas) */
function tabela(cols, rows, opts) {
  opts = opts || {};
  if (!arr(rows).length) return empty(opts.vazio || "Sem dados.");
  var thead = h("tr", null, cols.map(function (c) { return h("th", { scope: "col", class: c.num ? "num" : null }, c.t); }));
  var body = h("tbody");
  each(rows, function (r) {
    body.appendChild(h("tr", null, cols.map(function (c) {
      var v = c.render ? c.render(r) : r[c.k];
      return h("td", { class: [c.num ? "num" : "", c.cls || ""].join(" "), "data-label": c.t }, has(v) ? v : NA);
    })));
  });
  return h("div", { class: "scroll" + (opts.stack ? " stackable" : "") }, h("table", { class: "tbl" + (opts.stack ? " stackable" : "") }, h("thead", null, thead), body));
}

/* ---------------------------------------------------------------- quadro dos gráficos */
/* área de plotagem: SVG 0–100 esticado (traços sem escala) + camada HTML para marcas e dicas;
   eixos com rótulos posicionados em % (a geometria vem pronta do exportador) */
function quadro(cfg) {
  var area = h("div", { class: "cv-area", style: "height:" + (cfg.altura || 240) + "px" });
  var svg = S("svg", { viewBox: "0 0 100 100", preserveAspectRatio: "none", class: "cv-svg", "aria-hidden": "true", focusable: "false" });
  area.appendChild(svg);
  var tip = h("div", { class: "tip cv-tip", hidden: true, role: "status" });
  area.appendChild(tip);
  var ylab = h("div", { class: "cv-y", "aria-hidden": "true" });
  each(cfg.eixoY, function (t) {
    ylab.appendChild(h("span", { style: pctStyle("top", t.y) }, t.t));
    svg.appendChild(S("line", { class: "gridl", x1: 0, x2: 100, y1: t.y, y2: t.y, "vector-effect": "non-scaling-stroke" }));
  });
  var xlab = h("div", { class: "cv-x", "aria-hidden": "true" });
  each(cfg.eixoX, function (t) { xlab.appendChild(h("span", { style: pctStyle("left", t.x) }, t.t)); });
  var box = h("div", { class: "cv-plot" + (cfg.semY ? " cv-semy" : ""), role: "img", "aria-label": cfg.rotulo || "gráfico" }, ylab, area, h("div"), xlab);
  return { box: box, area: area, svg: svg, tip: tip };
}
function linha(svg, d, cls) {
  if (has(d)) svg.appendChild(S("path", { d: d, class: cls, "vector-effect": "non-scaling-stroke" }));
}
function mostrarDica(q, x, y, linhas) {
  q.tip.textContent = "";
  each(linhas, function (l, i) { q.tip.appendChild(i ? h("div", null, l) : h("b", null, l)); });
  q.tip.style.left = x + "%";
  q.tip.style.top = y + "%";
  q.tip.classList.toggle("cv-esq", x > 62);
  q.tip.hidden = false;
}
function esconderDica(q) { q.tip.hidden = true; }
function marca(q, x, y, cls, linhas, rotulo) {
  var m = h("span", { class: "cv-mk " + cls, style: pctStyle("left", x) + ";" + pctStyle("top", y), tabindex: "0", role: "img", "aria-label": rotulo || arr(linhas).join(" · ") });
  function on() { mostrarDica(q, x, y, linhas); }
  m.addEventListener("pointerenter", on);
  m.addEventListener("focus", on);
  m.addEventListener("pointerleave", function () { esconderDica(q); });
  m.addEventListener("blur", function () { esconderDica(q); });
  q.area.appendChild(m);
  return m;
}

/* ---------------------------------------------------------------- estado da aba */
var D = null, P = {}, UNI = [], BY = {}, ROOT = null, FICHA = null, PRECO = {}, ATUAL = null;
/* vínculo para a ficha de um ativo (endereço #cobertura:<id>; sai na impressão como texto) */
function linkFicha(iid, conteudo, cls) {
  return h("a", { href: "#cobertura:" + iid, class: ["cv-lf", cls || ""].join(" ") }, conteudo);
}
function rolarFicha() { if (FICHA && FICHA.scrollIntoView) FICHA.scrollIntoView({ block: "start" }); }
/* impressão: com a ficha aberta no endereço, o papel leva só a ficha (classe na raiz da aba) */
function marcarImpressao() { if (ROOT) ROOT.classList.toggle("cv-com-ficha", !!ATUAL && hashIid() === ATUAL); }
/* navegação para a ficha: pela casca (que muda o endereço) ou, sozinho, pelo endereço */
function abrir(iid) {
  if (!BY[iid]) return;
  var alvo = "#cobertura:" + iid;
  if (window.location.hash === alvo) {
    if (iid === ATUAL) { rolarFicha(); marcarImpressao(); } else mostrarFicha(iid, true);
    return;
  }
  if (typeof CTX.navegar === "function") { CTX.navegar("cobertura:" + iid); return; }
  try { window.history.pushState(null, "", alvo); } catch (e) { window.location.hash = alvo; }
  mostrarFicha(iid, true);
}
function hashIid() {
  var m = /^#cobertura:([A-Za-z0-9_]+)$/.exec(window.location.hash || "");
  return m ? m[1] : null;
}

function render(container, ctx) {
  CTX = ctx || {};
  LOCAL = null;
  ROOT = container;
  ATUAL = null;
  estilo();
  container.textContent = "";
  container.appendChild(h("div", { class: "boot", role: "status", "aria-live": "polite" }, h("h2", null, "Carregando a cobertura…"), h("div", { class: "boot-bar", "aria-hidden": "true" }), h("p", null, "Modelos abertos e preços-alvo de 12 meses de cada ação e ETF.")));
  return carregar(ARQ).then(function (d) {
    D = obj(d);
    return carregar(ARQ_PRECOS).then(function (p) { P = obj(p); }, function () { P = {}; });
  }).then(function () {
    container.textContent = "";
    montar(container);
    var iid = CTX.alvo || hashIid();
    if (iid) mostrarFicha(iid, true);
  }, function () {
    container.textContent = "";
    container.appendChild(h("div", { class: "boot err", role: "alert" }, h("h2", null, "Não foi possível carregar a cobertura."), h("p", null, "Os demais painéis seguem disponíveis. Recarregue a página para tentar de novo.")));
  });
}
/* endereço #cobertura:<id> vindo de qualquer aba (inclusive os botões "Ficha do ativo" da
   carteira e da tese): abre o ativo pedido mesmo quando a casca só troca a aba; quando a casca
   também chama abrir(), o segundo pedido do mesmo ativo é ignorado */
window.addEventListener("hashchange", function () {
  if (!D || !ROOT || !ROOT.isConnected) return;
  var iid = hashIid();
  if (iid && BY[iid] && iid !== ATUAL) mostrarFicha(iid, true);
  marcarImpressao();
});

function montar(root) {
  var M = obj(D.meta);
  if (M.estado === "em_verificacao") {
    root.appendChild(sec("cv-resumo", "Cobertura de ações e ETFs", null, block(null, null, empty("Os modelos da cobertura estão em conferência; a aba volta com a próxima publicação conferida. Os demais painéis seguem disponíveis."))));
    return;
  }
  if (M.estado === "sem_cobertura" || !arr(D.universe).length) {
    root.appendChild(sec("cv-resumo", "Cobertura de ações e ETFs", null, block(null, null, empty("A cobertura é publicada a partir do primeiro retrato semanal dos modelos de valuation."))));
    return;
  }
  UNI = arr(D.universe);
  BY = {};
  UNI.forEach(function (u) { BY[u.iid] = u; });
  PRECO = {};
  each(P.precos, function (p) { PRECO[p.i] = p; });
  root.appendChild(resumo(M));
  root.appendChild(painelUniverso(M));
  root.appendChild(secTabela(M));
  FICHA = sec("cv-ficha", "Ficha do ativo", "modelo aberto: insumos, fórmulas, cálculos e fontes");
  FICHA.appendChild(seletorFicha());
  FICHA.appendChild(h("div", { class: "stack", id: "cv-ficha-corpo" }, block(null, null, empty("Escolha um ativo na tabela de cobertura ou na lista acima para abrir o modelo completo."))));
  root.appendChild(FICHA);
  root.appendChild(acertos(M));
  root.appendChild(secEtfs(M));
  root.appendChild(revisaoMensal());
  root.appendChild(metodologia(M));
}

function revisaoMensal() {
  var s = sec("cv-revisao-mensal", "Revisão mensal da cobertura", "último dia de montagem do mês");
  var itens = arr(obj(D.monthly_reviews).itens);
  if (!itens.length) {
    s.appendChild(empty("A primeira revisão aprofundada será publicada após o último dia de montagem do mês."));
    return s;
  }
  each(itens, function (it) {
    var corpo = h("div", null, note(txt(it.resumo)));
    var detalhe = fold("Revisão de " + dataBR(it.data), it.automatica ? "fatos calculados pelo código" : "leitura da gestão", false, corpo);
    var carregando = false, pronta = false;
    detalhe.addEventListener("toggle", function () {
      if (!detalhe.open || carregando || pronta) return;
      carregando = true;
      corpo.setAttribute("aria-busy", "true");
      carregar(it.file).then(function (doc) {
        corpo.textContent = "";
        corpo.appendChild(CTX.ui && CTX.ui.md ? CTX.ui.md(doc.markdown) : h("pre", { class: "md-plain" }, txt(doc.markdown)));
        pronta = true;
      }, function () {
        corpo.textContent = "";
        corpo.appendChild(empty("Não foi possível carregar esta revisão. Feche e abra para tentar novamente."));
      }).then(function () { carregando = false; corpo.removeAttribute("aria-busy"); });
    });
    s.appendChild(detalhe);
  });
  return s;
}

/* ---------------------------------------------------------------- 1. resumo */
function resumo(M) {
  var kp = h("div", { class: "kpis" });
  each(D.kpis, function (k) {
    var extra = null;
    if (arr(k.mix).length) {
      extra = h("div", { class: "cv-mixmini", "aria-hidden": "true" }, k.mix.map(function (s) { return h("span", { class: "cv-seg r-" + s.tom, style: "flex:" + s.n, title: s.rating + ": " + s.n }); }));
    }
    kp.appendChild(tile(k.label, k.value, k.sub, extra));
  });
  var sim = M.is_synthetic ? h("p", null, h("span", { class: "pill k-sim" }, txt(M.simulated_label))) : null;
  return sec("cv-resumo", "Cobertura de ações e ETFs", "retrato de " + dataBR(M.as_of) + (has(M.prices_as_of) ? " · preços de " + dataBR(M.prices_as_of) : "") + " · horizonte de " + txt(M.horizon_months) + " meses", sim, kp,
    note([txt(M.data_notice), /\.$/.test(txt(M.data_notice)) ? " " : ". ", txt(M.aviso_cvm)].join("")));
}

/* ---------------------------------------------------------------- 2. painel do universo */
function painelUniverso(M) {
  var A = obj(D.aggregates);
  var s = sec("cv-universo", "Painel do universo", "potencial, consenso e ratings das ações com preço-alvo");
  var grid = h("div", { class: "stack" });
  grid.appendChild(distribuicao(obj(A.distribuicao)));
  var dois = h("div", { class: "cols-2" });
  if (A.dispersao && A.dispersao.n) dois.appendChild(dispersao(A.dispersao));
  dois.appendChild(mistura(obj(A.mistura)));
  grid.appendChild(dois);
  s.appendChild(grid);
  return s;
}
function distribuicao(V) {
  var b = block("Distribuição do potencial", "preço-alvo ÷ preço − 1, por " + "país ou setor");
  var lay = obj(V.leiautes);
  var chaves = Object.keys(lay);
  var atual = chaves.indexOf("pais") >= 0 ? "pais" : chaves[0];
  var host = h("div", { class: "cv-host" });
  var seg = h("div", { class: "seg", role: "group", "aria-label": "Agrupar por" });
  var rot = { pais: "País", setor: "Setor" };
  chaves.forEach(function (k) {
    var bt = h("button", { type: "button", "aria-pressed": k === atual ? "true" : "false" }, rot[k] || k);
    bt.addEventListener("click", function () {
      atual = k;
      seg.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", x === bt ? "true" : "false"); });
      desenhar();
    });
    seg.appendChild(bt);
  });
  function desenhar() {
    host.textContent = "";
    var L = obj(lay[atual]);
    var q = quadro({ altura: L.altura, eixoY: [], eixoX: V.eixo, semY: true, rotulo: "Distribuição do potencial das ações com preço-alvo, por " + (rot[atual] || "").toLowerCase() });
    each(L.linhas, function (r) {
      if (r.alt) q.svg.appendChild(S("rect", { class: "cv-banda", x: 0, width: 100, y: r.y0, height: r.h }));
    });
    each(V.eixo, function (t) { q.svg.appendChild(S("line", { class: "gridl", x1: t.x, x2: t.x, y1: 0, y2: 100, "vector-effect": "non-scaling-stroke" })); });
    q.svg.appendChild(S("line", { class: "axis cv-zero", x1: V.zero, x2: V.zero, y1: 0, y2: 100, "vector-effect": "non-scaling-stroke" }));
    each(L.linhas, function (r) {
      q.area.appendChild(h("span", { class: "cv-rowlbl", style: pctStyle("top", r.ly) }, h("b", null, r.t), " " + r.n + " · mediana " + r.med));
    });
    each(L.pontos, function (p) {
      var u = BY[p.i] || {};
      var m = marca(q, p.x, p.y, "cv-dot r-" + p.r + (p.c ? " cv-in" : "") + (p.f ? " cv-clip" : ""),
        [txt(u.nome) + " (" + txt(u.ticker) + ")", "Rating: " + txt(ratingTxt(u)), "Potencial: " + txt(u.upside_texto), u.carteira ? "Na carteira: " + u.carteira : null].filter(Boolean));
      m.addEventListener("click", function () { abrir(p.i); });
    });
    host.appendChild(q.box);
  }
  desenhar();
  add(b, [h("div", { class: "ctrl" }, seg), host,
    legenda([["cv-lg r-compra", "Compra"], ["cv-lg r-neutro", "Neutro"], ["cv-lg r-venda", "Venda"], obj(D.meta).has_book ? ["cv-lg cv-in", "na carteira"] : null].filter(Boolean)),
    leitura("cada ponto é uma ação com preço-alvo citável; a linha vertical marca potencial zero; pontos de cantos retos nas bordas estão fora da escala (" + txt(V.dominio_texto) + "). " + txt(V.fora) + " ações em revisão ou sem preço-alvo ficam fora do gráfico.", V.n, V.as_of),
    fold("Ver em tabela", null, false, tabela([{ t: "Ativo", k: "nome" }, { t: "País", k: "pais_nome" }, { t: "Setor", k: "setor_nome" }, { t: "Rating", k: "rating" }, { t: "Potencial", k: "upside_texto", num: true }],
      UNI.filter(function (u) { return u.tipo === "acao" && u.citavel; }), { stack: true }))]);
  return b;
}
function dispersao(V) {
  var b = block("Gestão × consenso público", "potencial pelo preço-alvo da gestão e pelo consenso");
  var q = quadro({ altura: 300, eixoY: V.eixo_y, eixoX: V.eixo_x, rotulo: "Potencial pelo preço-alvo da gestão contra o potencial pelo consenso público" });
  each(V.quadrantes, function (r) { q.svg.appendChild(S("rect", { class: "cv-quad", x: r.x, y: r.y, width: r.w, height: r.h })); });
  q.svg.appendChild(S("line", { class: "axis", x1: V.zero_x, x2: V.zero_x, y1: 0, y2: 100, "vector-effect": "non-scaling-stroke" }));
  q.svg.appendChild(S("line", { class: "axis", x1: 0, x2: 100, y1: V.zero_y, y2: V.zero_y, "vector-effect": "non-scaling-stroke" }));
  linha(q.svg, V.diagonal, "refl");
  each(V.pontos, function (p) {
    var u = BY[p.i] || {};
    var m = marca(q, p.x, p.y, "cv-dot s" + p.s + " r-" + p.r + (p.c ? " cv-in" : "") + (p.f ? " cv-clip" : ""),
      [txt(u.nome) + " (" + txt(u.ticker) + ")", "Gestão: " + txt(u.upside_texto), "Consenso: " + txt(p.ct) + " (" + txt(u.consenso_n) + " analistas de preço-alvo)", "Rating: " + txt(u.rating)]);
    m.addEventListener("click", function () { abrir(p.i); });
  });
  add(b, [q.box,
    h("div", { class: "cv-eixos" }, h("span", null, "horizontal: potencial pelo consenso público"), h("span", null, "vertical: potencial pela gestão")),
    legenda([["cv-lg r-compra", "Compra"], ["cv-lg r-neutro", "Neutro"], ["cv-lg r-venda", "Venda"], obj(D.meta).has_book ? ["cv-lg cv-in", "na carteira"] : null, ["cv-ln refl", "potenciais iguais"]].filter(Boolean)),
    leitura("acima da diagonal, o preço-alvo da gestão supera o do consenso (" + txt(V.acima) + " ações); abaixo, fica aquém (" + txt(V.abaixo) + "). Tamanho do ponto: liquidez diária em dólar, em tercis. Consenso: Yahoo Finance." + (V.fora ? " Pontos de cantos retos na borda estão fora da escala (" + txt(V.dominio_texto) + "): " + V.fora + " ações." : ""), V.n, V.as_of),
    fold("Ver em tabela", null, false, tabela([{ t: "Ativo", render: function (p) { return txt((BY[p.i] || {}).nome); } },
      { t: "Rating", render: function (p) { return txt((BY[p.i] || {}).rating); } },
      { t: "Potencial pela gestão", num: true, render: function (p) { return txt((BY[p.i] || {}).upside_texto); } },
      { t: "Potencial pelo consenso", num: true, k: "ct" }], V.pontos, { stack: true }))]);
  return b;
}
function mistura(V) {
  var b = block("Ratings", "ações por rating, no total e por país");
  function barra(segs, rot, n) {
    return h("div", { class: "cv-mixrow" }, h("span", { class: "cv-mixlbl" }, h("b", null, rot), " " + n),
      h("div", { class: "cv-mix", role: "img", "aria-label": rot + ": " + segs.map(function (s) { return s.t; }).join("; ") },
        segs.map(function (s) { return h("span", { class: "cv-seg r-" + s.tom, style: pctStyle("width", s.w), title: s.t }); })));
  }
  var box = h("div", { class: "cv-mixbox" }, barra(arr(V.total), "Total", V.n));
  each(V.paises, function (p) { box.appendChild(barra(arr(p.segs), p.t, p.n)); });
  add(b, [box,
    legenda([["cv-sw r-compra", "Compra"], ["cv-sw r-neutro", "Neutro"], ["cv-sw r-venda", "Venda"], ["cv-sw r-revisao", "Em revisão"], ["cv-sw r-sem", "Sem preço-alvo"]]),
    leitura("largura proporcional ao número de ações de cada rating no grupo; ETFs à parte, com visão própria.", V.n, obj(D.meta).as_of),
    fold("Ver em tabela", null, false, tabela([{ t: "Grupo", k: "g" }, { t: "Composição", k: "c" }],
      [{ g: "Total", c: arr(V.total).map(function (s) { return s.t; }).join("; ") }].concat(arr(V.paises).map(function (p) { return { g: p.t, c: arr(p.segs).map(function (s) { return s.t; }).join("; ") }; }))))]);
  return b;
}

/* ---------------------------------------------------------------- 3. tabela de cobertura */
var COLS = [
  { t: "Ativo", k: "nome", sort: "nome", render: function (u) {
    return linkFicha(u.iid, [h("b", null, u.nome), h("span", { class: "cellsub" }, [txt(u.ticker), u.tipo === "etf" ? " · ETF" : ""].join(""))], "cv-ativo");
  }, cls: "sticky" },
  { t: "País", k: "pais_nome", sort: "pais_nome" },
  { t: "Setor", k: "setor_nome", sort: "setor_nome", cls: "cv-wrap cv-mo" },
  { t: "Rating", k: "rating", sort: "rating", render: function (u) { return ratingPill(ratingTxt(u), u.rating_tom); } },
  { t: "Preço", num: true, render: function (u) { var p = PRECO[u.iid]; return p ? p.pt : u.preco_texto; } },
  { t: "Preço-alvo", num: true, sort: "alvo", render: function (u) { return u.citavel ? u.alvo_texto : h("span", { class: "muted" }, u.alvo_texto); } },
  { t: "Potencial", num: true, sort: "potencial", render: function (u) { var p = PRECO[u.iid]; var t = p && has(p.u) ? p.ut : u.upside_texto; return h("span", { class: sinal(p && has(p.u) ? p.u : u.upside) }, t); } },
  { t: "Retorno esperado", num: true, sort: "etr", k: "etr_texto", cls: "cv-mo cv-xl" },
  { t: "Custo de capital (ke)", num: true, sort: "ke", k: "ke_texto", cls: "cv-mo cv-xl" },
  { t: "Confiança · incerteza", sort: "confianca", cls: "cv-mo", render: function (u) { return has(u.confianca) ? [u.confianca, has(u.incerteza) ? " · " + String(u.incerteza).toLowerCase() : ""].join("") : NA; } },
  { t: "Frente ao consenso", num: true, sort: "vs_consenso", render: function (u) { return h("span", { class: sinal(u.vs_consenso) }, u.vs_consenso_texto); } }
];
var COL_CARTEIRA = { t: "Carteira", sort: "carteira", render: function (u) { return u.carteira ? h("span", { class: "side " + (u.carteira === "Long" ? "L" : "S") }, u.carteira + " " + txt(u.carteira_peso_texto)) : h("span", { class: "muted" }, "—"); } };
function sinal(v) { return typeof v === "number" ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "muted"; }
function chaveOrdem(u, k) {
  if (k === "potencial") { var p = PRECO[u.iid]; return p && has(p.u) ? p.u : u.upside; }
  return u[k];
}
function compara(a, b, k, asc) {
  var x = chaveOrdem(a, k), y = chaveOrdem(b, k);
  var xn = !has(x), yn = !has(y);
  if (xn && yn) return 0;
  if (xn) return 1;
  if (yn) return -1;
  var r = typeof x === "number" && typeof y === "number" ? (x < y ? -1 : x > y ? 1 : 0) : String(x).localeCompare(String(y), "pt-BR");
  return asc ? r : (r < 0 ? 1 : r > 0 ? -1 : 0);
}
function secTabela(M) {
  var s = sec("cv-tabela", "Tabela de cobertura", "todas as ações e ETFs do universo; ordene e filtre");
  var cols = COLS.slice();
  /* a carteira logo depois do rating: a ligação entre a cobertura e o fundo fica à vista */
  if (M.has_book) cols.splice(4, 0, COL_CARTEIRA);
  var estado = { k: "nome", asc: true, pais: "", setor: "", rating: "", busca: "", carteira: false, todos: false };
  /* no celular, a lista empilhada começa com 20 ativos (botão para ver todos); na tela larga, rolagem interna */
  var celular = !!(window.matchMedia && window.matchMedia("(max-width: 640px)").matches);
  function opcoes(campo) {
    var vistos = {}, out = [];
    UNI.forEach(function (u) { var v = u[campo]; if (has(v) && !vistos[v]) { vistos[v] = 1; out.push(v); } });
    return out.sort(function (a, b) { return String(a).localeCompare(String(b), "pt-BR"); });
  }
  /* rating das ações e visão dos ETFs em grupos separados ("Neutro" × "Neutra") */
  function opcoesRating() {
    var acoes = {}, etfs = {};
    UNI.forEach(function (u) { if (has(u.rating)) (u.tipo === "etf" ? etfs : acoes)[u.rating] = 1; });
    function grupo(rot, o, pref) {
      var ks = Object.keys(o).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); });
      return ks.length ? h("optgroup", { label: rot }, ks.map(function (v) { return h("option", { value: [pref, v].join("") }, v); })) : null;
    }
    return [grupo("Rating das ações", acoes, "acao:"), grupo("Visão dos ETFs frente ao ILF", etfs, "etf:")].filter(Boolean);
  }
  function select(rotulo, campo, chave) {
    var itens = campo === "rating" ? opcoesRating() : opcoes(campo).map(function (v) { return h("option", { value: v }, v); });
    var sel = h("select", { "aria-label": rotulo }, h("option", { value: "" }, "Todos"), itens);
    sel.addEventListener("change", function () { estado[chave] = sel.value; estado.todos = false; desenhar(); });
    return h("label", { class: "field" }, rotulo, sel);
  }
  var busca = h("input", { type: "search", placeholder: "Nome ou ticker", "aria-label": "Buscar ativo" });
  busca.addEventListener("input", function () { estado.busca = busca.value.toLowerCase(); estado.todos = false; desenhar(); });
  var ctrl = h("div", { class: "ctrl" }, select("País", "pais_nome", "pais"), select("Setor", "setor_nome", "setor"), select("Rating", "rating", "rating"), h("label", { class: "field" }, "Buscar", busca));
  if (M.has_book) {
    var ck = h("input", { type: "checkbox" });
    ck.addEventListener("change", function () { estado.carteira = ck.checked; desenhar(); });
    ctrl.appendChild(h("label", { class: "field cv-check" }, ck, "Só os nomes da carteira"));
  }
  var conta = h("p", { class: "count", "aria-live": "polite" });
  var thead = h("tr"), tbody = h("tbody");
  cols.forEach(function (c) {
    var th = h("th", { scope: "col", class: [c.num ? "num" : "", c.cls || ""].join(" ") });
    if (c.sort) {
      var ar = h("span", { class: "ar", "aria-hidden": "true" });
      var bt = h("button", { class: "sortbtn", type: "button" }, c.t, ar);
      bt.addEventListener("click", function () {
        if (estado.k === c.sort) estado.asc = !estado.asc; else { estado.k = c.sort; estado.asc = !c.num; }
        thead.querySelectorAll("th").forEach(function (x) { x.removeAttribute("aria-sort"); var a = x.querySelector(".ar"); if (a) a.textContent = ""; });
        th.setAttribute("aria-sort", estado.asc ? "ascending" : "descending");
        ar.textContent = estado.asc ? "▲" : "▼";
        desenhar();
      });
      th.appendChild(bt);
      th.appendChild(h("span", { class: "cv-thp" }, c.t)); /* rótulo do papel (o cabeçalho repete em cada folha) */
    } else th.textContent = c.t;
    thead.appendChild(th);
  });
  function passa(u) {
    if (estado.pais && u.pais_nome !== estado.pais) return false;
    if (estado.setor && u.setor_nome !== estado.setor) return false;
    if (estado.rating && [u.tipo === "etf" ? "etf" : "acao", u.rating].join(":") !== estado.rating) return false;
    if (estado.carteira && !u.carteira) return false;
    if (estado.busca && (String(u.nome) + " " + String(u.ticker)).toLowerCase().indexOf(estado.busca) < 0) return false;
    return true;
  }
  var mais = h("button", { class: "btn cv-mais", type: "button", hidden: true });
  mais.addEventListener("click", function () { estado.todos = true; desenhar(); });
  function desenhar() {
    var rows = UNI.filter(passa).sort(function (a, b) { return compara(a, b, estado.k, estado.asc); });
    var vis = celular && !estado.todos ? rows.slice(0, 20) : rows;
    mais.hidden = vis.length === rows.length;
    mais.textContent = "Mostrar todos os " + rows.length + " ativos";
    tbody.textContent = "";
    vis.forEach(function (u) {
      var tr = h("tr", { class: u.carteira ? "cv-nacart" : null });
      cols.forEach(function (c) {
        var v = c.render ? c.render(u) : u[c.k];
        tr.appendChild(h("td", { class: [c.num ? "num" : "", c.cls || ""].join(" "), "data-label": c.t }, has(v) ? v : NA));
      });
      tbody.appendChild(tr);
    });
    conta.textContent = rows.length === UNI.length ? "Todos os " + UNI.length + " instrumentos" : rows.length + " de " + UNI.length + " instrumentos";
  }
  var tbl = h("div", { class: "scroll tall stackable" }, h("table", { class: "tbl stackable cv-tbl" }, h("thead", null, thead), tbody));
  desenhar();
  var PM = obj(P.meta);
  s.appendChild(block(null, null, ctrl, conta, tbl, mais,
    note("Preço e potencial ao fechamento mais recente" + (has(PM.as_of) ? " (" + dataBR(PM.as_of) + ")" : "") + "; preço-alvo, retorno esperado (caso-base, com proventos), ke e rating do retrato de " + dataBR(obj(D.meta).as_of) + ". Ações em revisão seguem com o modelo aberto, sem preço-alvo citável. Frente ao consenso: preço-alvo da gestão ÷ consenso público − 1.")));
  s.appendChild(revisoes());
  return s;
}
function revisoes() {
  var R = obj(D.revisions);
  var b = block("Revisões recentes", "preços-alvo revistos, mudanças de rating e suspensões");
  if (!arr(R.itens).length) {
    b.appendChild(empty(R.n_iniciacoes ? "Retrato inaugural: " + R.n_iniciacoes + " iniciações de cobertura em " + dataBR(R.inicio) + "; as revisões aparecem a partir do retrato seguinte." : "Sem revisões no período."));
    return b;
  }
  var lista = h("div", { class: "stack" });
  function desenhar(todas) {
    lista.textContent = "";
    lista.appendChild(tabela(COLS_REV, todas ? R.itens : R.itens.slice(0, 15), { stack: true }));
    if (!todas && R.itens.length > 15) {
      var bt = h("button", { class: "btn cv-mais", type: "button" }, "Mostrar as " + R.itens.length + " revisões");
      bt.addEventListener("click", function () { desenhar(true); });
      lista.appendChild(bt);
    }
  }
  desenhar(false);
  b.appendChild(lista);
  b.appendChild(note("Eventos dos últimos " + txt(R.janela_dias) + " dias (desde " + dataBR(R.desde) + "); o histórico completo de cada ativo está na ficha."));
  return b;
}
var COLS_REV = [
    { t: "Data", k: "data_texto" },
    { t: "Ativo", render: function (r) { return linkFicha(r.iid, r.nome); } },
    { t: "Evento", k: "tipo" }, { t: "De", k: "de", num: true }, { t: "Para", k: "para", num: true }, { t: "Variação", k: "var", num: true },
    { t: "Rating", render: function (r) { return [has(r.rating_de) && r.rating_de !== r.rating_para ? r.rating_de + " → " : "", txt(r.rating_para)].join(""); } },
    { t: "Motivo", k: "motivo", cls: "cv-wrap" }
];

/* ---------------------------------------------------------------- 4. ficha do ativo (modelo aberto) */
function seletorFicha() {
  var sel = h("select", { "aria-label": "Abrir o modelo de um ativo" }, h("option", { value: "" }, "Escolha um ativo…"),
    UNI.slice().sort(function (a, b) { return String(a.nome).localeCompare(String(b.nome), "pt-BR"); }).map(function (u) { return h("option", { value: u.iid }, u.nome + " · " + txt(u.ticker)); }));
  sel.id = "cv-sel";
  sel.addEventListener("change", function () { if (sel.value) abrir(sel.value); });
  return h("div", { class: "ctrl" }, h("label", { class: "field" }, "Ativo", sel));
}
function mostrarFicha(iid, rolar) {
  var u = BY[iid], corpo = document.getElementById("cv-ficha-corpo");
  if (!u || !corpo) return;
  ATUAL = iid;
  var sel = document.getElementById("cv-sel");
  if (sel) sel.value = iid;
  corpo.textContent = "";
  corpo.appendChild(block(null, null, h("p", { class: "note", role: "status" }, "Carregando o modelo de " + u.nome + "…")));
  if (rolar) rolarFicha();
  marcarImpressao();
  var fm = has(u.mk) ? "cobertura-modelo-" + u.mk + ".json" : null, fh = has(u.hk) ? "cobertura-hist-" + u.hk + ".json" : null;
  Promise.all([fm ? carregar(fm) : Promise.resolve(null), fh ? carregar(fh).catch(function () { return null; }) : Promise.resolve(null)]).then(function (r) {
    if (ATUAL !== iid) return; /* outro ativo foi pedido enquanto este carregava */
    var m = obj(obj(r[0]).modelos)[iid], hs = r[1] ? obj(obj(r[1]).series)[iid] : null;
    corpo.textContent = "";
    if (!m) { corpo.appendChild(block(null, null, empty("Modelo indisponível nesta publicação."))); return; }
    ficha(corpo, u, m, hs);
  }, function () {
    if (ATUAL !== iid) return;
    corpo.textContent = "";
    corpo.appendChild(block(null, null, empty("Não foi possível carregar o modelo deste ativo. Recarregue a página para tentar de novo.")));
  });
}
function ficha(corpo, u, m, hs) {
  var cab = block(null, null);
  var p = PRECO[u.iid];
  cab.appendChild(h("div", { class: "cv-fh" },
    h("div", null, h("h3", { class: "cv-fh-t" }, m.nome), h("p", { class: "cv-fh-s" }, [txt(m.ticker), txt(m.pais), txt(m.setor), txt(m.arquetipo)].join(" · "))),
    h("div", { class: "chips" }, ratingPill(ratingTxt(m), m.rating_tom), m.rating_desde ? h("span", { class: "chip" }, "desde " + m.rating_desde) : null, u.carteira ? h("span", { class: "side " + (u.carteira === "Long" ? "L" : "S") }, "Na carteira: " + u.carteira) : null)));
  var kp = h("div", { class: "kpis cv-fk" },
    tile("Preço", p ? p.pt : u.preco_texto, p ? "fechamento de " + dataBR(p.d) : "fechamento de " + dataBR(u.preco_data)),
    tile("Preço-alvo", u.alvo_texto, u.vencimento ? "12 meses · vence em " + dataBR(u.vencimento) : (u.citavel ? null : "sem preço-alvo citável")),
    tile("Potencial", p && has(p.u) ? p.ut : u.upside_texto, p && has(p.u) ? "ao último fechamento; no retrato: " + u.upside_texto : "no retrato de " + dataBR(u.data_modelo)),
    tile("Confiança", txt(u.confianca), u.incerteza ? "incerteza " + String(u.incerteza).toLowerCase() : null));
  cab.appendChild(kp);
  if (!m.citavel) cab.appendChild(h("p", { class: "cv-aviso" }, "Modelo " + (m.rating === "Sem preço-alvo" ? "sem preço-alvo" : "em revisão") + ": a memória de cálculo abaixo fica pública para auditoria, mas não constitui preço-alvo citável."));
  if (has(m.rating_motivo)) cab.appendChild(note((m.tipo === "etf" ? "Visão: " : "Rating: ") + m.rating_motivo + "."));
  if (u.carteira) cab.appendChild(note("Na carteira (" + u.carteira + " " + txt(u.carteira_peso_texto) + "): a posição vem do alpha quantitativo da gestão; o rating é uma opinião de valuation de 12 meses e não dimensiona posições."));
  /* no papel, a ficha sai sozinha: o aviso dos dados e a natureza dos modelos vão junto */
  var M = obj(D.meta);
  cab.appendChild(h("p", { class: "note cv-imp-aviso" }, [txt(M.data_notice), /\.$/.test(txt(M.data_notice)) ? " " : ". ", txt(M.aviso_cvm), " Retrato de ", dataBR(M.as_of), "."].join("")));
  cab.appendChild(kv(m.cabecalho));
  if (arr(m.linhas_negociadas).length > 1) {
    cab.appendChild(tabela([{ t: "Linha", k: "t" }, { t: "Preço", k: "p", num: true }, { t: "Preço-alvo", k: "a", num: true }, { t: "Potencial", k: "u", num: true }, { t: "Conversão", k: "c", cls: "cv-wrap" }], m.linhas_negociadas, { stack: true }));
  }
  corpo.appendChild(cab);
  if (hs && !hs.vazio) corpo.appendChild(grafPreco(u, hs));
  if (m.football) corpo.appendChild(football(m));
  if (m.sensibilidade) corpo.appendChild(sensibilidade(m.sensibilidade));
  if (m.ponte) corpo.appendChild(ponte(m.ponte));
  if (m.cenarios) corpo.appendChild(cenarios(m.cenarios));
  if (m.tipo === "etf") corpo.appendChild(etfFicha(m));
  corpo.appendChild(memoria(m));
  corpo.appendChild(insumos(m));
  corpo.appendChild(qualidade(m));
  if (arr(m.metodos).length || arr(m.custo_capital).length) corpo.appendChild(metodos(m));
  if (hs && arr(hs.tabela).length) {
    corpo.appendChild(block("Histórico de preços-alvo e ratings", "eventos do livro da cobertura", tabela([
      { t: "Data", k: "data" }, { t: "Evento", k: "tipo" }, { t: "Rating", k: "rating" }, { t: "Preço-alvo", k: "alvo", num: true },
      { t: "Preço de referência", k: "preco", num: true }, { t: "Variação do alvo", k: "var", num: true }, { t: "Motivo", k: "motivo", cls: "cv-wrap" }], hs.tabela, { stack: true })));
  }
  corpo.appendChild(arquivos(m));
}
/* V1: preço × preço-alvo (o fragmento para no retrato; os fechamentos seguintes vêm de
   cobertura-precos.json, já na escala do gráfico) */
var COR_TOM = { compra: "verde-azulado", venda: "cobre", revisao: "âmbar" };
function grafPreco(u, H) {
  var etf = !!H.etf, pr = PRECO[u.iid], g = pr && pr.g ? pr.g : null;
  var b = block("Preço e preço-alvo", etf ? "fechamento semanal, preço-alvo e faixa de 90% até o vencimento" : "fechamento semanal, preço-alvo em degraus, consenso e cenários até o vencimento");
  var q = quadro({ altura: 300, eixoY: H.eixo_y, eixoX: H.eixo_x, rotulo: "Preço de " + u.nome + " e preço-alvo da gestão ao longo do tempo" });
  if (H.zona) q.svg.appendChild(S("rect", { class: "zone", x: H.zona.x, y: 0, width: H.zona.w, height: 100 }));
  each(H.faixas, function (f) {
    q.svg.appendChild(S("rect", { class: "cv-fx r-" + f.tom, x: f.x, y: 0, width: f.w, height: 100 }));
    if (f.rot) q.area.appendChild(h("span", { class: "cv-fxt", style: pctStyle("left", f.x) }, f.t));
  });
  if (H.consenso) linha(q.svg, H.consenso, "cv-cons");
  if (H.leque) { linha(q.svg, H.leque.area, "cv-leque"); linha(q.svg, H.leque.base, "cv-leque-b"); }
  if (has(H.retrato)) q.svg.appendChild(S("line", { class: "zonel", x1: H.retrato, x2: H.retrato, y1: 0, y2: 100, "vector-effect": "non-scaling-stroke" }));
  linha(q.svg, H.preco, "ln cv-preco");
  if (g) linha(q.svg, g.c, "ln cv-preco");
  linha(q.svg, H.alvo, "ln cv-alvo");
  if (H.zona) q.area.appendChild(h("span", { class: "cv-zt", style: pctStyle("left", H.zona.x) }, H.zona.t));
  var ponto = h("span", { class: "cv-mk cv-hover", hidden: true });
  q.area.appendChild(ponto);
  each(H.pontos, function (p) {
    var f = h("span", { class: "cv-faixa", style: pctStyle("left", p.a) + ";" + pctStyle("width", p.w), "aria-hidden": "true" });
    f.addEventListener("pointerenter", function () {
      ponto.style.left = p.x + "%"; ponto.style.top = p.y + "%"; ponto.hidden = false;
      mostrarDica(q, p.x, p.y, [[p.d, p.m ? " (ponto mensal)" : ""].join(""), "Fechamento: " + p.p, p.al ? "Preço-alvo vigente: " + p.al : "Sem preço-alvo vigente"]);
    });
    f.addEventListener("pointerleave", function () { ponto.hidden = true; esconderDica(q); });
    q.area.appendChild(f);
  });
  if (H.consenso_atual) q.area.appendChild(h("span", { class: "cv-cbar", style: pctStyle("left", H.consenso_atual.x) + ";" + pctStyle("top", H.consenso_atual.y) + ";" + pctStyle("height", H.consenso_atual.h), title: H.consenso_atual.t }));
  if (g) marca(q, g.x, g.y, "cv-ult", ["Último fechamento", dataBR(pr.d) + ": " + txt(pr.pt)]);
  else if (H.ultimo) marca(q, H.ultimo.x, H.ultimo.y, "cv-ult", ["Fechamento do retrato", txt(H.ultimo.d) + ": " + txt(H.ultimo.t)]);
  each(H.marcas, function (k) { marca(q, k.x, k.y, "cv-ev cv-ev-" + k.k, k.t); });
  if (H.leque) each(H.leque.rotulos, function (r) { q.area.appendChild(h("span", { class: "cv-lq", style: pctStyle("top", r.y) }, r.t)); });
  /* legenda e leitura só com as séries presentes (ETF: visão Positiva, Neutra ou Negativa) */
  var lg = [["cv-ln cv-preco", "fechamento"]];
  if (H.tem_alvo) lg.push(["cv-ln cv-alvo", "preço-alvo da gestão"]);
  if (H.leque) lg.push(["cv-ln cv-alvo-b", etf ? "preço-alvo até o vencimento" : "caso-base até o vencimento"]);
  if (H.consenso || H.consenso_atual) lg.push(["cv-sw cv-cons", "consenso público (mínimo – máximo)"]);
  if (H.leque) lg.push(["cv-sw cv-leque", etf ? "faixa de 90% até o vencimento" : "cenários até o vencimento"]);
  each(H.tons, function (t) { lg.push(["cv-sw cv-fxs r-" + t[0], t[1]]); });
  if (arr(H.marcas).length) lg.push(["cv-lg cv-evl", "evento"]);
  var partes = [];
  if (arr(H.tons).length) partes.push("fundo " + H.tons.map(function (t) { return (COR_TOM[t[0]] || "colorido") + " nos períodos em " + t[1]; }).join(", "));
  if (arr(H.marcas).length) partes.push("marcadores na iniciação, nas mudanças de " + (etf ? "visão" : "rating") + " e nas revisões do preço-alvo de 5% ou mais (as demais aparecem nos degraus e no histórico abaixo)");
  partes.push("linha tracejada na data do retrato" + (H.leque ? (etf ? ", início da faixa de 90% do preço-alvo até o vencimento" : ", início do leque dos cenários pessimista, base e otimista até o vencimento") : ""));
  if (g) partes.push("depois dela, os fechamentos posteriores ao retrato, até " + dataBR(pr.d));
  if (!H.tem_alvo && !H.leque) partes.push("sem preço-alvo citável no período");
  if (H.zona) partes.push("antes das últimas 52 semanas, um ponto por mês");
  add(b, [q.box, legenda(lg), leitura(partes.join("; ") + ".", H.n, obj(D.meta).as_of)]);
  return b;
}
/* V2: campo de futebol */
function football(m) {
  var F = m.football;
  var b = block("Faixas de valor", "valor por método, cenários, consenso e 52 semanas");
  var box = h("div", { class: "cv-ff", role: "img", "aria-label": "Faixas de valor de " + m.nome + ": " + arr(F.linhas).map(function (l) { return l.r + " " + l.t; }).join("; ") });
  each(F.linhas, function (l) {
    var trilho = h("div", { class: "cv-ff-tr" });
    if (has(F.preco)) trilho.appendChild(h("span", { class: "cv-ff-p", style: pctStyle("left", F.preco) }));
    if (has(F.alvo)) trilho.appendChild(h("span", { class: "cv-ff-a", style: pctStyle("left", F.alvo) }));
    if (has(l.x0)) trilho.appendChild(h("span", { class: "cv-ff-bar k-" + l.k, style: pctStyle("left", l.x0) + ";" + pctStyle("width", l.w) }));
    if (has(l.x)) trilho.appendChild(h("span", { class: "cv-ff-mk k-" + l.k, style: pctStyle("left", l.x) }));
    box.appendChild(h("div", { class: "cv-ff-r" }, h("div", { class: "cv-ff-l" }, h("b", null, l.r), h("span", null, l.s)), trilho, h("div", { class: "cv-ff-v num" }, l.t)));
  });
  var eixo = h("div", { class: "cv-ff-tr cv-ff-eixo", "aria-hidden": "true" });
  each(F.eixo, function (t) { eixo.appendChild(h("span", { style: pctStyle("left", t.x) }, t.t)); });
  box.appendChild(h("div", { class: "cv-ff-r cv-ff-er" }, h("div"), eixo, h("div")));
  add(b, [box,
    legenda([["cv-ln cv-ff-lp", F.preco_t], F.alvo_t ? ["cv-lg cv-ff-la", F.alvo_t] : null].filter(Boolean)),
    leitura("barra = faixa (mínimo a máximo); marca = valor central (método, caso-base, média do consenso, último fechamento). Linha contínua no preço; tracejada no preço-alvo.", null, m.as_of)]);
  return b;
}
/* V3: mapa de sensibilidade */
function sensibilidade(G) {
  var b = block("Sensibilidade do preço-alvo", "ke × " + G.colunas);
  var thead = h("tr", null, h("th", { scope: "col", title: "linhas: ke; colunas: " + G.colunas }, "ke"), arr(G.rot_colunas).map(function (c) { return h("th", { scope: "col", class: "num" }, c); }));
  var body = h("tbody");
  each(G.celulas, function (row, i) {
    body.appendChild(h("tr", null, h("th", { scope: "row" }, txt(arr(G.rot_linhas)[i])), arr(row.c).map(function (c, j) {
      var base = arr(G.base)[0] === i && arr(G.base)[1] === j;
      return h("td", { class: "num cv-hm b" + String(c.b).replace("-", "n") + (base ? " cv-base" : "") }, h("b", null, c.t), h("small", null, c.u));
    })));
  });
  add(b, [h("div", { class: "scroll cv-hmw" }, h("table", { class: "tbl cv-hmt" }, h("thead", null, thead), body)),
    leitura("cada célula refaz o preço-alvo pelos mesmos métodos com o ke da linha e o choque da coluna; abaixo, o potencial frente ao preço do retrato. Azul: potencial positivo; vermelho: negativo; contorno: caso-base." + (G.citavel ? "" : " Modelo sem preço-alvo citável: grade só para auditoria."), null, null)]);
  return b;
}
/* V4: ponte do preço-alvo (cascata horizontal) */
function ponte(Pn) {
  var b = block("Ponte do preço-alvo", "do preço-alvo anterior ao novo, por componente");
  var box = h("div", { class: "cv-ff cv-wf", role: "img", "aria-label": "Ponte do preço-alvo: " + arr(Pn.barras).map(function (x) { return x.t + " " + x.v; }).join("; ") });
  each(Pn.barras, function (x) {
    var tr = h("div", { class: "cv-ff-tr" });
    if (x.tom === "total") tr.appendChild(h("span", { class: "cv-wf-tot", style: pctStyle("left", x.x) }));
    else if (x.tom !== "nd") tr.appendChild(h("span", { class: "cv-wf-bar t-" + x.tom, style: pctStyle("left", x.x) + ";" + pctStyle("width", x.w) }));
    box.appendChild(h("div", { class: "cv-ff-r" }, h("div", { class: "cv-ff-l" }, h("b", null, x.t)), tr, h("div", { class: "cv-ff-v num" }, x.v)));
  });
  var eixo = h("div", { class: "cv-ff-tr cv-ff-eixo", "aria-hidden": "true" });
  each(Pn.eixo, function (t) { eixo.appendChild(h("span", { style: pctStyle("left", t.x) }, t.t)); });
  box.appendChild(h("div", { class: "cv-ff-r cv-ff-er" }, h("div"), eixo, h("div")));
  add(b, [box, leitura("cada componente troca um grupo de insumos do modelo anterior pelo atual, em ordem fixa; o resíduo fecha a conta. Motivo dominante: " + txt(Pn.motivo) + "; resíduo de " + txt(Pn.residuo) + " do alvo.", null, null),
    arr(Pn.notas).length ? note(Pn.notas.join("; ") + ".") : null]);
  return b;
}
function cenarios(C) {
  return block("Cenários", "simulação com semente fixa e probabilidades implícitas no mercado",
    tabela([{ t: "Cenário", k: "t" }, { t: "Preço-alvo", k: "v", num: true }, { t: "Probabilidade implícita no mercado", k: "p", num: true }], C.linhas, { stack: true }),
    kv(arr(C.resumo).map(function (r) { return { t: r[0], v: r[1] }; })));
}
/* posição de ETF: nome da casa com vínculo para a ficha quando a posição é coberta */
function posicaoEtf(p) {
  var cls = "num " + (p.tom === "pos" ? "pos" : p.tom === "neg" ? "neg" : "muted");
  return h("div", { class: "cv-lt-r" + (p.imp ? " cv-imp" : "") }, h("span", { class: "cv-lt-n" }, p.i && BY[p.i] ? linkFicha(p.i, p.t) : p.t),
    h("span", { class: "cv-lt-tr" }, h("span", { class: "cv-lt-b t-" + p.tom, style: pctStyle("width", p.w) })),
    h("span", { class: "num" }, p.peso), h("span", { class: cls }, p.u));
}
function etfFicha(m) {
  var b = block("Carteira subjacente", m.n_posicoes + " posições; retorno esperado de cada uma em " + txt(m.moeda) + ", pelo preço-alvo citável da casa ou, sem ele, pelo retorno do índice");
  var lista = h("div", { class: "cv-lt" });
  each(m.posicoes, function (p) { lista.appendChild(posicaoEtf(p)); });
  add(b, [kv(m.agregados), lista, leitura("comprimento da barra proporcional ao peso no ETF; cor e número à direita: retorno esperado da posição (verde, positivo; vermelho, negativo); tracejado = posição sem modelo da casa (retorno imputado pelo índice).", m.n_posicoes, m.as_of)]);
  return b;
}
function fonteEl(f) {
  if (!f) return null;
  var partes = [txt(f.fonte)];
  if (has(f.doc)) partes.push(f.doc);
  var meta = [];
  if (has(f.pub)) meta.push("publicado em " + f.pub + (f.est ? " (data estimada)" : ""));
  if (has(f.col)) meta.push("coletado em " + f.col);
  return h("li", null, has(f.url) ? link(f.url, partes.join(" · ")) : partes.join(" · "), meta.length ? h("span", { class: "muted" }, " · " + meta.join(" · ")) : null);
}
function memoria(m) {
  var F = arr(m.fontes);
  var lista = h("ol", { class: "cv-passos" });
  each(m.passos, function (p) {
    var fs = arr(p.fo).map(function (i) { return fonteEl(F[i]); });
    lista.appendChild(h("li", { class: "cv-passo", id: "cv-p-" + String(p.id).replace(/[^\w-]/g, "_") },
      h("div", { class: "cv-ph" }, h("b", null, txt(p.t))),
      p.f ? h("div", { class: "cv-pf" }, h("span", { class: "cv-pk" }, "Fórmula"), h("span", { class: "cv-px" }, p.f)) : null,
      h("div", { class: "cv-pf" }, h("span", { class: "cv-pk" }, p.f ? "Substituição" : "Registro"), h("span", { class: "cv-px" }, txt(p.s))),
      p.f ? h("div", { class: "cv-pf cv-pr" }, h("span", { class: "cv-pk" }, "Resultado"), h("b", null, txt(p.r))) : null,
      has(p.p) ? h("div", { class: "cv-pf" }, h("span", { class: "cv-pk" }, "Premissas"), h("span", { class: "cv-px muted" }, p.p)) : null,
      fs.length ? h("ul", { class: "cv-pfo evid" }, fs) : null));
  });
  return fold("Memória de cálculo", arr(m.passos).length + " passos, na ordem do cálculo, cada um com fórmula, números usados e fontes", false, lista);
}
function insumos(m) {
  var F = arr(m.fontes);
  var b = fold("Insumos e fontes", arr(m.insumos).length + " insumos · " + F.length + " documentos públicos citados", false);
  var body = b.querySelector(".fold-b");
  if (arr(m.insumos).length) {
    body.appendChild(tabela([
      { t: "Insumo", k: "t", cls: "cv-wrap" }, { t: "Valor", k: "v", num: true }, { t: "Unidade", k: "u" }, { t: "Período", k: "per" },
      { t: "Publicação", render: function (i) { return has(i.pub) ? [i.pub, i.est ? " (estimada)" : ""].join("") : NA; } },
      { t: "Fonte", cls: "cv-wrap", render: function (i) { var f = has(i.fo) ? F[i.fo] : null; return f ? (has(f.url) ? link(f.url, [txt(f.fonte), has(f.doc) ? " · " + f.doc : ""].join("")) : [txt(f.fonte), has(f.doc) ? " · " + f.doc : ""].join("")) : NA; } }
    ], m.insumos, { stack: true }));
  }
  body.appendChild(h("h4", null, "Documentos citados"));
  body.appendChild(h("ul", { class: "evid cv-docs" }, F.map(fonteEl)));
  return b;
}
function qualidade(m) {
  var b = block("Lacunas e portões de qualidade", "o que falta e o que foi conferido");
  if (arr(m.lacunas).length) {
    b.appendChild(h("ul", { class: "list" }, m.lacunas.map(function (l) { return h("li", null, h("b", null, txt(l.t)), has(l.m) ? ": " + l.m : ""); })));
  } else b.appendChild(note("Sem lacunas: todos os insumos dos métodos usados estão disponíveis."));
  if (arr(m.avisos).length) b.appendChild(h("ul", { class: "list" }, m.avisos.map(function (a) { return h("li", null, a); })));
  b.appendChild(fold("Portões de qualidade", txt(m.portoes_resumo), false, tabela([{ t: "Portão", k: "c" }, { t: "Verificação", k: "t", cls: "cv-wrap" },
    { t: "Situação", render: function (p) { return h("span", { class: "pill k-" + p.tom }, p.s); } }, { t: "Detalhe", k: "d", cls: "cv-wrap" }], m.portoes, { stack: true, vazio: "Sem portões registrados." })));
  return b;
}
function metodos(m) {
  var b = fold("Métodos, custo de capital e pares", arr(m.metodos).length + " métodos", false);
  var body = b.querySelector(".fold-b");
  if (arr(m.custo_capital).length) { body.appendChild(h("h4", null, "Custo de capital")); body.appendChild(kv(m.custo_capital)); }
  each(m.metodos, function (x) {
    var proj = arr(x.projecao);
    /* colunas na ordem da conta e com rótulo em português, como vêm do exportador */
    var cols = arr(x.colunas).map(function (c) { return { t: c.t, k: c.k, num: true }; });
    body.appendChild(h("div", { class: "card" }, h("div", { class: "card-h" }, h("b", null, txt(x.t)), h("span", { class: "chip" }, "peso " + txt(x.peso))),
      kv([{ t: "Valor por ação", v: x.v }, has(x.terminal) ? { t: "Fração do valor na perpetuidade", v: x.terminal } : null, has(x.motivo) ? { t: "Indisponível", v: x.motivo } : null].filter(Boolean)),
      proj.length && cols.length ? tabela([{ t: "Ano", k: "ano" }].concat(cols), proj, { stack: true }) : null));
  });
  var pr = m.pares;
  if (pr && arr(pr.itens).length) {
    body.appendChild(h("h4", null, "Pares (" + txt(pr.grupo) + ")"));
    body.appendChild(note("α relativo = α do emissor − mediana do α dos pares (" + txt(pr.mediana) + ")."));
    body.appendChild(tabela([{ t: "Emissor", render: function (r) { return BY[r.i] ? linkFicha(r.i, r.t) : r.t; } }, { t: "α", k: "v", num: true }], pr.itens));
  }
  if (arr(m.diagnosticos).length) { body.appendChild(h("h4", null, "Diagnósticos")); body.appendChild(kv(m.diagnosticos)); }
  return b;
}
var PACOTE = null;
function arquivos(m) {
  var lista = h("ul", { class: "list" }), X = obj(D.methodology);
  each(m.arquivos, function (a) {
    var url = has(X.repo_livro) && has(a.rel) ? [X.repo_livro, a.rel].join("") : a.repo;
    lista.appendChild(h("li", { "data-dados": a.dados }, h("b", null, a.t), " · ", link(url, "no repositório público"), h("span", { class: "cv-dl" })));
  });
  var b = fold("Arquivos para auditoria", "dados abertos do modelo e como refazer o cálculo", false, lista,
    h("p", { class: "note" }, "O cálculo pode ser refeito por qualquer pessoa a partir dos insumos públicos arquivados: ",
      arr(obj(D.methodology).links).map(function (l, i) { return [i ? " · " : "", link(l.u, l.t)]; }), "."));
  /* o catálogo dos dados abertos só existe no portal público: buscado quando o leitor abre a seção */
  b.addEventListener("toggle", function () {
    if (!b.open) return;
    if (!PACOTE) PACOTE = window.fetch((CTX.base || "") + "dados/datapackage.json", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("HTTP"); return r.json(); });
    PACOTE.then(function (pkg) {
      var caminhos = {};
      each(obj(pkg).resources, function (r) { caminhos[r.path] = r; });
      lista.querySelectorAll("li").forEach(function (li) {
        var r = caminhos[li.getAttribute("data-dados")], alvo = li.querySelector(".cv-dl");
        if (r && alvo && !alvo.childNodes.length) alvo.appendChild(h("span", null, " · ", h("a", { href: (CTX.base || "") + "dados/" + r.path, download: "" }, "baixar desta publicação")));
      });
    }, function () { PACOTE = null; });
  });
  return b;
}

/* ---------------------------------------------------------------- 5. histórico de acertos */
function acertos(M) {
  var T = obj(D.track_record);
  var s = sec("cv-acertos", "Histórico de acertos", T.em_maturacao ? "em maturação: " + txt(T.n_previsoes) + " previsões em aberto" : txt(T.n_vencidas) + " previsões vencidas");
  var kp = h("div", { class: "kpis" });
  each(T.tiles, function (t) { kp.appendChild(tile(t.label, t.maturacao ? h("span", { class: "cv-mat" }, t.value) : t.value, t.sub, t.ref ? h("div", { class: "tile-s" }, t.ref) : null)); });
  s.appendChild(kp);
  var dois = h("div", { class: "cols-2" });
  dois.appendChild(grafIc(obj(T.ic)));
  dois.appendChild(grafCalib(obj(T.calibracao)));
  s.appendChild(dois);
  s.appendChild(grafCestas(obj(T.carteiras)));
  s.appendChild(note("Regras de amostra: taxas de acerto só a partir de 20 previsões vencidas, sempre com N e intervalo de confiança de 90% (Wilson); estatísticas semanais em maturação até 13 semanas de retratos completos. Método: " + txt(T.metodo) + "."));
  return s;
}
function maturando(b, X, oque) {
  b.appendChild(empty("Em maturação: " + txt(X.semanas) + " de " + txt(X.minimo) + " semanas de retratos completos necessárias para " + oque + "."));
  return b;
}
function grafIc(X) {
  var b = block("IC semanal", "correlação de postos entre α relativo e retorno residual da semana seguinte");
  if (!X.n) return maturando(b, { semanas: 0, minimo: 2 }, "a série");
  var q = quadro({ altura: 220, eixoY: X.eixo_y, eixoX: X.eixo_x, rotulo: "IC semanal da cobertura" });
  q.svg.appendChild(S("line", { class: "axis", x1: 0, x2: 100, y1: X.zero, y2: X.zero, "vector-effect": "non-scaling-stroke" }));
  each(X.barras, function (r) {
    q.svg.appendChild(S("rect", { class: "cv-bar t-" + r.tom, x: r.x, y: r.y, width: r.w, height: r.h }));
    var hit = h("span", { class: "cv-faixa", style: pctStyle("left", r.x) + ";" + pctStyle("width", r.w), "aria-hidden": "true" });
    hit.addEventListener("pointerenter", function () { mostrarDica(q, r.x, r.y, [r.t]); });
    hit.addEventListener("pointerleave", function () { esconderDica(q); });
    q.area.appendChild(hit);
  });
  linha(q.svg, X.media, "ln cv-media");
  add(b, [X.maturacao ? h("p", { class: "cv-mat" }, "Em maturação") : null, q.box, legenda([["cv-lg t-pos", "IC da semana"], ["cv-ln cv-media", "média móvel de 13 semanas"]]),
    leitura("barra acima de zero: as ações com maior α relativo tiveram retorno residual (descontada a média do grupo país × setor) maior na semana seguinte.", X.n, obj(D.meta).as_of),
    fold("Ver em tabela", null, false, tabela([{ t: "Semana", k: "t" }], X.barras))]);
  return b;
}
function grafCalib(X) {
  var b = block("Calibração por quintil", "retorno residual médio da semana seguinte, por quintil de α relativo");
  if (!X.exibir) return maturando(b, X, "a calibração");
  var q = quadro({ altura: 220, eixoY: X.eixo_y, eixoX: arr(X.pontos).map(function (p) { return { x: p.x, t: p.q }; }), rotulo: "Calibração por quintil de α relativo" });
  q.svg.appendChild(S("line", { class: "axis", x1: 0, x2: 100, y1: X.zero, y2: X.zero, "vector-effect": "non-scaling-stroke" }));
  each(X.pontos, function (p) {
    if (!has(p.y)) return;
    q.svg.appendChild(S("line", { class: "cv-ic", x1: p.x, x2: p.x, y1: p.y0, y2: p.y1, "vector-effect": "non-scaling-stroke" }));
    marca(q, p.x, p.y, "cv-dot r-ref", [p.t]);
  });
  add(b, [X.maturacao ? h("p", { class: "cv-mat" }, "Em maturação") : null, q.box,
    leitura("ponto = média semanal; traço = intervalo de confiança de 90%. Uma cobertura calibrada sobe de Q1 a Q5.", X.semanas + " semanas", obj(D.meta).as_of),
    fold("Ver em tabela", null, false, tabela([{ t: "Quintil", k: "t" }], X.pontos))]);
  return b;
}
function grafCestas(X) {
  var b = block("Carteiras por rating", "retorno residual acumulado, pesos iguais, sem custos");
  if (!X.exibir) return maturando(b, X, "as carteiras por rating");
  var q = quadro({ altura: 240, eixoY: X.eixo_y, eixoX: X.eixo_x, rotulo: "Retorno residual acumulado das carteiras por rating" });
  q.svg.appendChild(S("line", { class: "axis", x1: 0, x2: 100, y1: X.zero, y2: X.zero, "vector-effect": "non-scaling-stroke" }));
  each(X.series, function (sr) { linha(q.svg, sr.d, "ln cv-s-" + sr.k); });
  add(b, [X.maturacao ? h("p", { class: "cv-mat" }, "Em maturação") : null, q.box,
    legenda(arr(X.series).map(function (sr) { return ["cv-ln cv-s-" + sr.k, sr.t + " " + sr.ultimo]; })),
    leitura("soma das médias semanais do retorno residual (país × setor) das ações em cada rating no início da semana; Venda com o sinal invertido (ganha quando as ações em Venda ficam para trás).", X.semanas + " semanas", obj(D.meta).as_of),
    fold("Ver em tabela", null, false, tabela([{ t: "Carteira", k: "t" }, { t: "Retorno residual acumulado", k: "ultimo", num: true }], X.series))]);
  return b;
}

/* ---------------------------------------------------------------- 6. ETFs */
function secEtfs(M) {
  var s = sec("cv-etfs", "ETFs", "valor justo pela carteira subjacente e visão frente ao ILF");
  if (!arr(D.etfs).length) { s.appendChild(block(null, null, empty("Sem ETFs cobertos neste retrato."))); return s; }
  var cards = h("div", { class: "cards" });
  each(D.etfs, function (e) {
    var lt = h("div", { class: "cv-lt" });
    each(arr(e.top).slice(0, 10), function (p) { lt.appendChild(posicaoEtf(p)); });
    var bt = h("button", { class: "go", type: "button" }, "Abrir o modelo →");
    bt.addEventListener("click", function () { abrir(e.iid); });
    cards.appendChild(h("div", { class: "card" },
      h("div", { class: "card-h" }, h("b", null, e.ticker + " · " + e.nome), ratingPill(e.visao, e.tom)),
      kv([{ t: "Preço · preço-alvo", v: e.preco + " · " + e.alvo }, { t: "Potencial · retorno esperado", v: e.upside + " · " + e.retorno },
        { t: "Pelas posições · pelo índice", v: e.bu + " · " + e.td }, { t: "Cobertura pelos modelos da casa", v: e.cobertura }, { t: "Erro de acompanhamento frente ao ILF", v: e.ticker === "ILF" ? "— (referência)" : e.te_ilf }]),
      arr(e.top).length ? h("div", null, h("p", { class: "src" }, "Maiores posições (de " + e.n_posicoes + "): peso e retorno esperado em " + txt(e.moeda || "USD") + " — pelo preço-alvo citável da casa; tracejado = sem alvo citável (Em revisão, confiança C ou fora da cobertura), retorno do índice"), lt) : null,
      arr(e.avisos).length ? note(e.avisos.join("; ") + ".") : null, bt));
  });
  s.appendChild(cards);
  s.appendChild(note("Retorno esperado do ETF = combinação do retorno pelas posições (preços-alvo da casa para as posições cobertas, com proventos e câmbio) e do retorno pelo índice (Grinold–Kroner: dividendos, crescimento do lucro e reversão do P/L); visão Positiva, Neutra ou Negativa frente ao ILF."));
  return s;
}

/* ---------------------------------------------------------------- 7. metodologia */
function metodologia(M) {
  var X = obj(D.methodology);
  var s = sec("cv-metodo", "Metodologia de avaliação", "versão " + txt(X.versao));
  var corpo = h("div", { class: "stack" });
  corpo.appendChild(kv([{ t: "Horizonte", v: X.horizonte }, { t: "Atualização", v: X.cadencia }, has(X.carteira) ? { t: "Rating e carteira", v: X.carteira } : null, { t: "ETFs", v: X.referencia_etf }, has(X.histerese) ? { t: "Histerese do rating", v: X.histerese } : null].filter(Boolean)));
  corpo.appendChild(h("h4", null, "Definição dos ratings"));
  corpo.appendChild(h("dl", { class: "kv" }, arr(X.rating).map(function (r) { return [h("dt", null, ratingPill(r.r, r.tom)), h("dd", null, r.t)]; })));
  corpo.appendChild(h("h4", null, "Métodos por arquétipo"));
  corpo.appendChild(tabela([{ t: "Arquétipo", render: function (a) { return a.t + " (" + a.n + ")"; } }, { t: "Métodos e pesos", cls: "cv-wrap", render: function (a) { return arr(a.metodos).map(function (x) { return x.t + " " + x.peso; }).join(" · "); } }], X.arquetipos, { stack: true }));
  corpo.appendChild(h("h4", null, "Custo de capital próprio"));
  corpo.appendChild(h("ul", { class: "list" }, arr(X.ke).map(function (t) { return h("li", null, t); })));
  corpo.appendChild(note("ERP: " + txt(X.erp) + (X.erp_data ? " (Damodaran, " + X.erp_data + ")" : "") + "."));
  if (arr(X.crp).length) corpo.appendChild(tabela([{ t: "País", k: "t" }, { t: "CRP", k: "v", num: true }], X.crp));
  corpo.appendChild(h("p", { class: "cv-aviso" }, txt(X.aviso)));
  corpo.appendChild(h("ul", { class: "list" }, arr(X.links).map(function (l) { return h("li", null, link(l.u, l.t)); })));
  s.appendChild(fold("Como os preços-alvo são construídos", "métodos, custo de capital, ratings e atualização", false, corpo));
  return s;
}

/* ---------------------------------------------------------------- estilo do módulo (tokens da casca) */
function estilo() {
  if (document.getElementById("cv-estilo")) return;
  var css = [
    ".cv-plot{display:grid;grid-template-columns:62px minmax(0,1fr);grid-template-rows:auto 22px;column-gap:6px;min-width:0}",
    ".cv-plot.cv-semy{grid-template-columns:0 minmax(0,1fr);column-gap:0}",
    ".cv-y,.cv-x{position:relative;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}",
    ".cv-y span{position:absolute;right:0;transform:translateY(-50%);white-space:nowrap}",
    ".cv-x span{position:absolute;top:5px;transform:translateX(-50%);white-space:nowrap}",
    ".cv-x span:first-child{transform:none}.cv-x span:last-child{transform:translateX(-100%)}",
    ".cv-area{position:relative;min-width:0}",
    ".cv-svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}",
    ".cv-svg .gridl{stroke:var(--grid);stroke-width:1}.cv-svg .axis{stroke:var(--line);stroke-width:1}",
    ".cv-svg .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}",
    ".cv-svg .refl{fill:none;stroke:var(--ink-2);stroke-width:1;stroke-dasharray:4 3}",
    ".cv-svg .zone{fill:var(--surface-3)}.cv-svg .zonel{stroke:var(--muted);stroke-dasharray:3 3}",
    ".cv-preco{stroke:var(--ink)}.cv-alvo{stroke:var(--accent);stroke-width:2.4}",
    ".cv-cons{fill:var(--band);opacity:.7;stroke:none}",
    ".cv-leque{fill:var(--accent-soft);stroke:none}.cv-leque-b{fill:none;stroke:var(--accent);stroke-width:1.5;stroke-dasharray:5 4}",
    ".cv-fx.r-compra{fill:var(--long-soft)}.cv-fx.r-venda{fill:var(--short-soft)}.cv-fx.r-revisao{fill:var(--warn-bg);opacity:.6}.cv-fx.r-neutro,.cv-fx.r-sem,.cv-fx.r-ref{fill:none}",
    ".cv-fxt{position:absolute;bottom:4px;padding-left:4px;font-size:11px;color:var(--muted);white-space:nowrap;pointer-events:none}",
    ".cv-banda{fill:var(--surface-3)}.cv-quad{fill:var(--surface-3)}",
    ".cv-bar.t-pos{fill:var(--div-pos)}.cv-bar.t-neg{fill:var(--div-neg)}.cv-bar.t-zero{fill:var(--muted)}",
    ".cv-media{stroke:var(--ink-2);stroke-width:1.6}.cv-ic{stroke:var(--ink-2);stroke-width:1.5}",
    ".cv-s-compra{stroke:var(--long)}.cv-s-venda{stroke:var(--short)}.cv-s-spread{stroke:var(--accent);stroke-width:2.6}",
    ".cv-mk{position:absolute;transform:translate(-50%,-50%);border-radius:50%;cursor:default}",
    ".cv-mk:focus-visible{outline:2px solid var(--accent);outline-offset:2px}",
    ".cv-dot{width:9px;height:9px;background:var(--muted);box-shadow:0 0 0 1px var(--surface);cursor:pointer}",
    ".cv-dot.s1{width:7px;height:7px}.cv-dot.s2{width:10px;height:10px}.cv-dot.s3{width:13px;height:13px}",
    ".r-compra{background:var(--long)}.r-venda{background:var(--short)}.r-neutro{background:var(--shadow)}.r-revisao{background:var(--warn-mark)}.r-ref{background:var(--accent)}",
    /* "Sem preço-alvo": hachura em --muted com contorno (≥ 3:1 contra o painel nos dois temas) */
    ".r-sem{background:repeating-linear-gradient(135deg,var(--muted) 0 1.5px,transparent 1.5px 4px);box-shadow:inset 0 0 0 1.5px var(--muted)}",
    ".cv-dot.cv-in{box-shadow:0 0 0 1.5px var(--surface),0 0 0 3px var(--ink-2)}",
    ".cv-cbar{position:absolute;width:8px;transform:translateX(-50%);background:var(--band);box-shadow:inset 0 0 0 1px var(--muted);border-radius:4px}",
    ".cv-dot.cv-clip{border-radius:2px}",
    ".cv-ev{width:11px;height:11px;background:var(--surface);border:2px solid var(--accent);border-radius:2px;transform:translate(-50%,-50%) rotate(45deg)}",
    ".cv-ev-mudanca_rating{border-color:var(--ink)}.cv-ev-suspensao{border-color:var(--warn-mark)}",
    ".cv-ult{width:9px;height:9px;background:var(--ink);box-shadow:0 0 0 2px var(--surface)}",
    ".cv-hover{width:9px;height:9px;background:var(--surface);border:2px solid var(--ink);pointer-events:none}",
    ".cv-faixa{position:absolute;top:0;bottom:0;cursor:crosshair}",
    ".cv-tip{position:absolute;z-index:3;pointer-events:none;transform:translate(14px,-50%);min-width:150px}",
    ".cv-tip.cv-esq{transform:translate(calc(-100% - 14px),-50%)}",
    ".cv-rowlbl{position:absolute;left:4px;transform:translateY(-100%);font-size:11.5px;color:var(--ink-2);white-space:nowrap;pointer-events:none}",
    ".cv-zt{position:absolute;top:4px;font-size:11.5px;color:var(--muted);padding-left:4px;white-space:nowrap}",
    ".cv-lq{position:absolute;right:0;transform:translateY(-120%);font-size:11.5px;color:var(--accent-2);white-space:nowrap;background:var(--surface);padding:0 3px;border-radius:3px}",
    ".cv-eixos{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;font-size:12px;color:var(--muted)}",
    ".legend i.cv-lg{width:10px;height:10px;border-radius:50%}.legend i.cv-in{background:var(--surface);box-shadow:inset 0 0 0 2px var(--ink)}",
    ".legend i.cv-sw{width:13px;height:10px;border-radius:2px}",
    ".legend i.cv-cons{background:var(--band);box-shadow:inset 0 0 0 1px var(--muted)}.legend i.cv-leque{background:var(--accent-soft);box-shadow:inset 0 0 0 1px var(--accent)}",
    ".legend i.cv-fxs.r-compra{background:var(--long-soft);box-shadow:inset 0 0 0 1px var(--long)}.legend i.cv-fxs.r-venda{background:var(--short-soft);box-shadow:inset 0 0 0 1px var(--short)}.legend i.cv-fxs.r-revisao{background:var(--warn-bg);box-shadow:inset 0 0 0 1px var(--warn-mark)}",
    ".legend i.cv-evl{width:9px;height:9px;border-radius:1px;background:var(--surface);box-shadow:inset 0 0 0 2px var(--accent);transform:rotate(45deg)}",
    ".legend i.cv-ln{width:16px;height:3px;border-radius:2px}.legend i.cv-preco{background:var(--ink)}.legend i.cv-alvo{background:var(--accent)}.legend i.cv-alvo-b{background:repeating-linear-gradient(90deg,var(--accent) 0 5px,transparent 5px 8px)}.legend i.refl,.legend i.cv-media{background:var(--ink-2)}",
    ".legend i.cv-s-compra{background:var(--long)}.legend i.cv-s-venda{background:var(--short)}.legend i.cv-s-spread{background:var(--accent)}.legend i.t-pos{background:var(--div-pos);border-radius:2px}",
    ".legend i.cv-ff-lp{background:var(--ink)}.legend i.cv-ff-la{background:var(--accent);transform:rotate(45deg);border-radius:1px}",
    ".cv-mixmini{display:flex;gap:2px;height:7px;margin-top:6px}.cv-mixmini .cv-seg{border-radius:3px}",
    ".cv-mixbox{display:grid;gap:8px}.cv-mixrow{display:grid;grid-template-columns:minmax(90px,30%) minmax(0,1fr);gap:10px;align-items:center;font-size:12.5px}",
    ".cv-mix{display:flex;gap:2px;height:14px}.cv-seg{display:block;min-width:2px;border-radius:2px}.cv-mixlbl{color:var(--muted)}.cv-mixlbl b{color:var(--ink);font-weight:600}",
    ".cv-ff{display:grid;gap:0}.cv-ff-r{display:grid;grid-template-columns:minmax(120px,34%) minmax(0,1fr) minmax(88px,auto);gap:10px;align-items:center;min-height:34px}",
    ".cv-ff-l{display:grid;font-size:12.5px;line-height:1.25}.cv-ff-l span{color:var(--muted);font-size:11.5px}",
    ".cv-ff-tr{position:relative;align-self:stretch;min-height:34px}.cv-ff-v{font-size:12.5px;text-align:right;white-space:nowrap}",
    ".cv-ff-p{position:absolute;top:0;bottom:0;width:0;border-left:1.5px solid var(--ink)}",
    ".cv-ff-a{position:absolute;top:0;bottom:0;width:0;border-left:1.5px dashed var(--accent)}",
    ".cv-ff-bar{position:absolute;top:30%;height:40%;background:var(--accent-soft);border-radius:4px;box-shadow:inset 0 0 0 1px var(--accent)}",
    ".cv-ff-bar.k-consenso{background:var(--band);box-shadow:inset 0 0 0 1px var(--muted)}.cv-ff-bar.k-faixa52{background:var(--surface-2);box-shadow:inset 0 0 0 1px var(--line)}",
    ".cv-ff-mk{position:absolute;top:50%;width:10px;height:10px;transform:translate(-50%,-50%) rotate(45deg);background:var(--accent);border-radius:1px}",
    ".cv-ff-mk.k-consenso,.cv-ff-mk.k-faixa52{background:var(--ink-2)}",
    ".cv-ff-eixo{min-height:20px;font-size:11.5px;color:var(--muted)}.cv-ff-eixo span{position:absolute;top:2px;transform:translateX(-50%);white-space:nowrap}",
    ".cv-ff-eixo span:first-child{transform:none}.cv-ff-eixo span:last-child{transform:translateX(-100%)}",
    ".cv-wf-tot{position:absolute;top:12%;height:76%;width:5px;transform:translateX(-50%);background:var(--ink-2);border-radius:3px}",
    ".cv-wf-bar{position:absolute;top:25%;height:50%;border-radius:3px}.cv-wf-bar.t-total{background:var(--ink-2)}.cv-wf-bar.t-pos{background:var(--div-pos)}.cv-wf-bar.t-neg{background:var(--div-neg)}.cv-wf-bar.t-zero{background:var(--muted)}",
    /* mapa de sensibilidade: cabeçalhos centrados como as células; rampa divergente equilibrada nos dois temas */
    ".cv-hmt{--cv-p1:14%;--cv-p2:26%;--cv-p3:40%;--cv-n1:14%;--cv-n2:26%;--cv-n3:40%}",
    "@media screen and (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]) .cv-hmt{--cv-p1:30%;--cv-p2:48%;--cv-p3:68%;--cv-n1:18%;--cv-n2:32%;--cv-n3:48%}}",
    ":root[data-theme=\"dark\"] .cv-hmt{--cv-p1:30%;--cv-p2:48%;--cv-p3:68%;--cv-n1:18%;--cv-n2:32%;--cv-n3:48%}",
    ".cv-hmt th,.cv-hmt th.num{text-align:center;white-space:nowrap;vertical-align:middle}.cv-hmt th[scope=row]{width:1%;text-align:right;vertical-align:middle}",
    ".cv-hmt td.cv-hm{text-align:center;white-space:nowrap;position:relative;vertical-align:middle}.cv-hmt td.cv-hm small{display:block;color:var(--ink-2)}",
    ".cv-hm.b1{background:color-mix(in srgb,var(--div-pos) var(--cv-p1),transparent)}.cv-hm.b2{background:color-mix(in srgb,var(--div-pos) var(--cv-p2),transparent)}.cv-hm.b3{background:color-mix(in srgb,var(--div-pos) var(--cv-p3),transparent)}",
    ".cv-hm.bn1{background:color-mix(in srgb,var(--div-neg) var(--cv-n1),transparent)}.cv-hm.bn2{background:color-mix(in srgb,var(--div-neg) var(--cv-n2),transparent)}.cv-hm.bn3{background:color-mix(in srgb,var(--div-neg) var(--cv-n3),transparent)}",
    ".cv-hm.cv-base{box-shadow:inset 0 0 0 2px var(--ink)}",
    ".cv-lt{display:grid;gap:4px}.cv-lt-r{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(40px,1fr) auto auto;gap:8px;align-items:center;font-size:12.5px}",
    ".cv-lt-n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cv-lt-tr{position:relative;height:8px;background:var(--surface-2);border-radius:4px}",
    /* barra = peso; cor = sinal do retorno, a mesma convenção do número ao lado */
    ".cv-lt-b{position:absolute;left:0;top:0;bottom:0;border-radius:0 4px 4px 0;background:var(--muted)}.cv-lt-b.t-pos{background:var(--pos-ink)}.cv-lt-b.t-neg{background:var(--neg-ink)}",
    ".cv-imp .cv-lt-b{background:repeating-linear-gradient(135deg,var(--muted) 0 3px,transparent 3px 6px)}",
    ".cv-fh{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 16px;align-items:flex-start}",
    ".cv-fh-t{font:700 22px/1.2 var(--font-serif)}.cv-fh-s{color:var(--muted);font-size:13px;margin-top:2px}",
    ".cv-aviso{border-left:3px solid var(--warn-mark);padding:6px 10px;background:var(--warn-bg);color:var(--ink);font-size:13px;border-radius:2px 8px 8px 2px}",
    ".cv-imp-aviso,.cv-thp{display:none}",
    ".cv-mat{color:var(--warn);font-weight:600;font-size:13px}",
    ".cv-rt-compra{background:var(--long-soft);color:var(--long)}.cv-rt-venda{background:var(--short-soft);color:var(--short)}",
    ".cv-passos{list-style:none;margin:0;padding:0;display:grid;gap:10px;counter-reset:cvp}",
    ".cv-passo{counter-increment:cvp;padding:10px 12px;background:var(--surface-3);border-radius:12px 9px 13px 10px;display:grid;gap:4px;min-width:0}",
    ".cv-ph{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 10px}.cv-ph b::before{content:counter(cvp) '. ';color:var(--muted);font-weight:500}",
    ".cv-pf{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;font-size:13px}",
    ".cv-pk{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;padding-top:2px}.cv-px{overflow-wrap:anywhere}",
    ".cv-pr b{font-size:14px}.cv-pfo{margin:2px 0 0 104px;padding:0;list-style:none}.cv-docs{list-style:none;padding:0}",
    ".cv-wrap{white-space:normal!important;min-width:140px}.cv-tbl .cv-ativo{display:grid;text-align:left;color:var(--ink);text-decoration:none}.cv-tbl .cv-ativo b{color:var(--accent)}",
    ".cv-tbl th .sortbtn{white-space:normal;text-align:inherit}.cv-tbl td.sticky{white-space:normal;min-width:150px;max-width:210px}.cv-tbl .cv-wrap{min-width:104px}",
    ".cv-tbl tr.cv-nacart>td:first-child{box-shadow:inset 3px 0 0 var(--accent)}.cv-check{display:flex;gap:6px;align-items:center;align-self:end;padding-bottom:7px;color:var(--ink-2)}",
    ".cv-fk .tile-v{font-size:20px}",
    "@media (max-width:1399px){.cv-tbl .cv-xl{display:none!important}}",
    "@media (max-width:640px){.cv-plot{grid-template-columns:48px minmax(0,1fr)}.cv-y span{font-size:11px}",
    ".cv-x span:nth-child(even){display:none}.cv-ff-eixo span:nth-child(even){display:none}",
    ".kpis.cv-fk{grid-template-columns:repeat(2,minmax(0,1fr))}.cv-fk .tile-v{font-size:18px}",
    ".cv-ff-r{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'l v' 't t';row-gap:2px;padding:4px 0}",
    ".cv-ff-l{grid-area:l}.cv-ff-v{grid-area:v}.cv-ff-tr{grid-area:t;min-height:22px}.cv-ff-er{grid-template-areas:'t t'}",
    ".cv-tbl .cv-mo{display:none!important}.cv-mais{justify-self:start}",
    /* empilhada: o nome do ativo é o título do cartão (sem a caixa clara da coluna fixa) */
    ".tbl.stackable.cv-tbl td.sticky,.tbl.stackable.cv-tbl tbody tr:hover>td.sticky{position:static;background:none;width:auto;min-width:0;max-width:none}",
    ".tbl.stackable.cv-tbl tr.cv-nacart>td:first-child{box-shadow:none}.tbl.stackable.cv-tbl tr.cv-nacart{box-shadow:inset 3px 0 0 var(--accent),var(--fundo)}",
    ".cv-pf{grid-template-columns:minmax(0,1fr)}.cv-pfo{margin-left:0}.cv-lt-r{grid-template-columns:minmax(0,1fr) 54px auto auto}",
    ".cv-mixrow{grid-template-columns:minmax(0,1fr)}.cv-lq{display:none}.cv-fxt{display:none}}",
    /* papel: com a ficha aberta no endereço, só a ficha; sem ela, a tabela inteira, sem rolagem e na largura da folha */
    "@media print{.cv-faixa,.cv-tip,.cv-hover,#cv-sel,#cv-tabela .ctrl,.cv-mais{display:none!important}.cv-svg{overflow:visible}",
    ".cv-imp-aviso{display:block!important}",
    ".cv-com-ficha :is(#cv-resumo,#cv-universo,#cv-tabela,#cv-acertos,#cv-etfs,#cv-metodo){display:none!important}.cv-com-ficha #cv-ficha .ctrl{display:none!important}.cv-com-ficha #cv-ficha-corpo>.block:first-child{break-inside:auto}",
    "#cv-tabela .scroll,#cv-tabela .scroll.tall{max-height:none!important;overflow:visible!important}",
    ":is(#cv-resumo,#cv-universo,#cv-tabela,#cv-ficha,#cv-acertos,#cv-etfs,#cv-metodo) .tbl :is(th,.sticky){position:static!important}",
    ".cv-tbl{font-size:8pt;width:100%}.cv-tbl th,.cv-tbl td{padding:3px 4px!important}",
    ".cv-tbl .cv-mo,.cv-tbl .cv-xl,.cv-tbl .cv-ativo .cellsub,.cv-tbl th .sortbtn{display:none!important}.cv-tbl .cv-thp{display:inline!important}",
    ".cv-lf{color:inherit;text-decoration:none}}",
    /* cores forçadas: rating também pela forma (▲ Compra, ● Neutro, ▼ Venda, ◆ Em revisão, ○ sem preço-alvo) e, nas barras, pela textura */
    "@media (forced-colors:active){.cv-mk,.cv-seg,.cv-ff-bar,.cv-ff-mk,.cv-wf-bar,.cv-lt-b,.legend i{forced-color-adjust:none;background:CanvasText!important;border-color:CanvasText}",
    ".cv-dot{box-shadow:none!important}.cv-dot.r-compra,.legend i.cv-lg.r-compra{clip-path:polygon(50% 0,100% 100%,0 100%);border-radius:0}",
    ".cv-dot.r-venda,.legend i.cv-lg.r-venda{clip-path:polygon(0 0,100% 0,50% 100%);border-radius:0}",
    ".cv-dot.r-revisao,.legend i.cv-lg.r-revisao{clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);border-radius:0}",
    ".cv-dot.r-ref{clip-path:inset(0);border-radius:0}",
    ".cv-seg.r-neutro,.legend i.cv-sw.r-neutro{background:repeating-linear-gradient(90deg,CanvasText 0 2px,Canvas 2px 4px)!important}",
    ".cv-seg.r-venda,.legend i.cv-sw.r-venda{background:repeating-linear-gradient(45deg,CanvasText 0 2px,Canvas 2px 5px)!important}",
    ".cv-seg.r-revisao,.legend i.cv-sw.r-revisao{background:repeating-linear-gradient(0deg,CanvasText 0 2px,Canvas 2px 4px)!important}",
    ".cv-seg.r-sem,.legend i.cv-sw.r-sem,.legend i.cv-lg.r-sem{background:Canvas!important;box-shadow:inset 0 0 0 2px CanvasText}",
    ".cv-mix,.cv-mixmini{gap:3px}",
    ".legend i.cv-cons,.legend i.cv-leque,.legend i.cv-fxs,.legend i.cv-in,.legend i.cv-evl{background:Canvas!important;box-shadow:inset 0 0 0 2px CanvasText}.legend i.cv-alvo-b{background:repeating-linear-gradient(90deg,CanvasText 0 5px,Canvas 5px 8px)!important}",
    ".legend i.cv-cons{box-shadow:inset 0 0 0 2px GrayText}.legend i.cv-leque{background:repeating-linear-gradient(135deg,CanvasText 0 1px,Canvas 1px 4px)!important}",
    ".cv-svg *{forced-color-adjust:none}.cv-svg :is(.ln,.refl,.cv-media,.cv-ic,.zonel,.cv-leque-b){stroke:CanvasText}.cv-svg :is(.cv-fx,.cv-banda,.cv-quad,.zone){fill:none}",
    /* na carteira: furo no centro do marcador (a forma continua a do rating) */
    ".cv-dot.cv-in,.legend i.cv-in{background:radial-gradient(circle at 50% 55%,Canvas 0 26%,CanvasText 30%)!important;box-shadow:none}",
    ".cv-svg .cv-cons{fill:none;opacity:1;stroke:GrayText;stroke-width:1.5;stroke-dasharray:4 2;vector-effect:non-scaling-stroke}",
    ".cv-svg .cv-leque{fill:none;stroke:CanvasText;stroke-width:1;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}",
    ".cv-cbar{forced-color-adjust:none;background:Canvas;box-shadow:inset 0 0 0 2px GrayText}",
    ".cv-fxt{color:CanvasText}",
    ".cv-hm{forced-color-adjust:auto}.cv-hm.cv-base{outline:2px solid CanvasText}}"
  ].join("\n");
  var st = document.createElement("style");
  st.id = "cv-estilo";
  st.textContent = css;
  document.head.appendChild(st);
}

window.CDP_COBERTURA = {
  versao: VERSAO, render: render, expandir: expandir,
  abrir: function (iid) {
    if (!D || !ROOT || !ROOT.isConnected) return;
    iid = String(iid);
    if (iid === ATUAL) { rolarFicha(); marcarImpressao(); } else mostrarFicha(iid, true);
  }
};
})();
