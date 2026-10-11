"""Dashboard público de cases recebidos: apresentação, sem nova avaliação financeira.

Os documentos são os dossiês de ``teses_ativos.documentos``. Preços, retornos,
qualidade e métodos vêm da representação pública; esta folha não abre arquivos,
recalcula modelos, promove rascunhos ou obtém autoridade para publicar.
"""
from __future__ import annotations

import html
import math
import re
import unicodedata
from datetime import date

SCHEMA = "cdp.dashboard-cases/v1"
_IID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SHA = re.compile(r"[a-fA-F0-9]{64}")
_MODELO = re.compile(r"cobertura-modelo-[0-9]+\.json")
ND = "n/d"
LIMITE_RATIOS = (
    "Múltiplos n/d: este recorte não oferece denominador, unidade e período "
    "equivalentes por companhia. Consulte a memória de cada modelo; não inferimos ratios."
)


def _texto(value: object, default: str = ND) -> str:
    return value.strip() if type(value) is str and value.strip() else default


def _chave(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(c))


def _numero(value: object) -> float | int | None:
    return value if type(value) is int or type(value) is float and math.isfinite(value) else None


def _definido(value: str) -> bool:
    return _chave(value) not in {"n/d", "na", "nao disponivel", "nao informado", ""}


def _data(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def _nota(doc: dict, iid: str, corte: str | None) -> dict:
    nota = doc.get("nota")
    if type(nota) is not dict or type(nota.get("documento")) is not dict:
        return {"estado": "Análise quantitativa preliminar", "data": None, "href": None}
    n = nota["documento"]
    data = _data(n.get("data"))
    publicada = (
        doc.get("estado_pesquisa") == "nota_publicada" and n.get("autoria") == "mente"
        and n.get("issuer_id") == iid and data is not None and corte is not None
        and data <= corte and type(nota.get("sha256")) is str
        and _SHA.fullmatch(nota["sha256"]) is not None
    )
    return {"estado": "Narrativa publicada" if publicada else "Nota em conferência",
            "data": data, "href": f"../ativos/{iid.lower()}/#tese" if publicada else None}


def _caso(doc: dict) -> dict:
    if type(doc) is not dict or type(doc.get("ativo")) is not dict:
        raise ValueError("Documento de case sem ativo público")
    u, modelo = doc["ativo"], doc.get("modelo")
    if type(modelo) is not dict:
        raise ValueError("Documento de case sem modelo público")
    iid = u.get("iid")
    if type(iid) is not str or not _IID.fullmatch(iid):
        raise ValueError("Identificador de case inválido")
    tipo = u.get("tipo")
    if tipo not in ("acao", "etf"):
        raise ValueError("Tipo de ativo fora do contrato de cases")
    corte = _data(doc.get("corte_cobertura"))
    origem = doc.get("origem_modelo")
    identidade = (type(origem) is dict and type(origem.get("arquivo")) is str
                  and _MODELO.fullmatch(origem["arquivo"]) is not None
                  and type(origem.get("sha256")) is str
                  and _SHA.fullmatch(origem["sha256"]) is not None)
    citavel = u.get("citavel") is True and identidade
    etr = _numero(u.get("etr")) if citavel else None
    etr_texto = _texto(u.get("etr_texto")) if etr is not None else ND
    if etr_texto == ND:
        etr = None
    preco = _numero(u.get("preco"))
    preco_texto = _texto(u.get("preco_texto")) if preco is not None else ND
    metodo = _texto(u.get("arquetipo_nome")) if tipo == "acao" else "Carteira subjacente / índice"
    metodos = [(_texto(m.get("t")), _texto(m.get("peso")))
               for m in modelo.get("metodos") or [] if type(m) is dict]
    metodos_texto = " · ".join(t + (f" ({peso})" if peso != ND else "")
                               for t, peso in metodos if t != ND)
    if tipo == "etf":
        metodos_texto = "Modelo da carteira subjacente e do índice"
    corte_pesquisa = _data(doc.get("corte_pesquisa", doc.get("corte_cobertura")))
    nota = _nota(doc, iid, corte_pesquisa)
    qualidade = _texto(modelo.get("portoes_resumo"))
    if not identidade:
        qualidade = "Identidade do fragmento não disponível"
    pares = modelo.get("pares") if type(modelo.get("pares")) is dict else {}
    n_pares = pares.get("n")
    comparacao_modelo = {"grupo": _texto(pares.get("grupo")),
                        "n": n_pares if type(n_pares) is int and n_pares >= 0 else None,
                        "mediana": _texto(pares.get("mediana"))}
    return {
        "iid": iid, "tipo": tipo, "tipo_nome": "Companhia" if tipo == "acao" else "ETF",
        "nome": _texto(u.get("nome"), iid), "ticker": _texto(u.get("ticker")),
        "pais": _texto(u.get("pais"), _texto(u.get("pais_nome"))),
        "pais_nome": _texto(u.get("pais_nome")), "setor": _texto(u.get("setor"),
                                                                      _texto(u.get("setor_nome"))),
        "setor_nome": _texto(u.get("setor_nome")), "arquetipo": metodo,
        "metodos": metodos_texto or ND, "indice": _texto(modelo.get("indice")),
        "rating": _texto(u.get("rating")), "confianca": _texto(u.get("confianca")),
        "qualidade": qualidade, "motivo": _texto(modelo.get("rating_motivo"),
                                                   _texto(u.get("motivo"))),
        "citavel": bool(citavel), "etr": etr, "etr_texto": etr_texto,
        "preco_texto": preco_texto, "moeda": _texto(u.get("moeda")),
        "preco_data": _data(u.get("preco_data")), "corte_cobertura": corte,
        "corte_pesquisa": corte_pesquisa,
        "corte_modelo": _data(u.get("data_modelo")) or _data(modelo.get("as_of")),
        "nota": nota, "href": f"../ativos/{iid.lower()}/",
        "dados_href": f"../ativos/{iid.lower()}/analise.json",
        "modelo_href": "../" + origem["arquivo"] if identidade else None,
        "modelo_sha256": origem["sha256"] if identidade else None,
        "dados_simulados": doc.get("dados_simulados") is True,
        "comparacao_modelo": comparacao_modelo,
        "ratios": ND, "limite_ratios": LIMITE_RATIOS,
    }


def construir_dashboard_cases(documentos: list[dict]) -> dict:
    """Compõe grupos e ordens determinísticos; não modifica os documentos recebidos."""
    if type(documentos) is not list:
        raise ValueError("Cases exigem lista explícita de documentos")
    casos = [_caso(d) for d in documentos]
    if len({c["iid"].lower() for c in casos}) != len(casos):
        raise ValueError("Cases com identificadores ou rotas duplicados")
    casos.sort(key=lambda c: (c["tipo"] == "etf", _chave(c["nome"]), c["iid"]))
    for c in casos:
        if c["tipo"] == "acao":
            definidos = _definido(c["setor"]) and _definido(c["arquetipo"])
            regionais = [p for p in casos if p["iid"] != c["iid"] and p["tipo"] == "acao"
                         and definidos and p["setor"] == c["setor"]
                         and p["arquetipo"] == c["arquetipo"]]
            criterio = "Mesmo setor e enquadramento econômico; país restringe o grupo local."
            limite = ("Classificação não comprova negócios, crescimento, risco ou contabilidade "
                      "equivalentes. Preços nominais são referências, não uma medida de valor relativo.")
        else:
            regionais = [p for p in casos if p["iid"] != c["iid"] and p["tipo"] == "etf"]
            criterio = "Comparação de produtos de exposição regional; país restringe o grupo local."
            limite = ("Benchmarks, composição e custos podem diferir. O grupo não implica "
                      "equivalência dos índices; a visão do modelo é relativa ao ILF.")
        locais = [p["iid"] for p in regionais if _definido(c["pais"]) and p["pais"] == c["pais"]]
        c["comparaveis"] = {"local": locais, "regional": [p["iid"] for p in regionais],
                            "criterio": criterio, "limite": limite}
        c["busca"] = _chave(" ".join(c[k] for k in ("nome", "ticker", "pais_nome", "setor_nome",
                                                    "arquetipo", "rating", "metodos")))
    orders = {
        "nome": casos,
        "estado": sorted(casos, key=lambda c: (c["tipo"] == "etf", c["nota"]["estado"],
                                               _chave(c["nome"]), c["iid"])),
        "corte": sorted(casos, key=lambda c: (c["tipo"] == "etf", c["corte_modelo"] is None,
                                              -(date.fromisoformat(c["corte_modelo"]).toordinal()
                                                if c["corte_modelo"] else 0), c["iid"])),
        "etr": sorted(casos, key=lambda c: (c["tipo"] == "etf", c["etr"] is None,
                                            -c["etr"] if c["etr"] is not None else 0, c["iid"])),
    }
    for key, ordered in orders.items():
        for position, c in enumerate(ordered):
            c.setdefault("ordinais", {})[key] = f"{position:06d}"
    return {
        "schema": SCHEMA, "casos": casos,
        "ordens": {k: [c["iid"] for c in v] for k, v in orders.items()},
        "indicadores": {
            "total": len(casos), "companhias": sum(c["tipo"] == "acao" for c in casos),
            "etfs": sum(c["tipo"] == "etf" for c in casos),
            "narrativas_publicadas": sum(c["nota"]["href"] is not None for c in casos),
            "retornos_citaveis": sum(c["etr"] is not None for c in casos),
        },
        "filtros": {k: sorted({c[k] for c in casos}, key=_chave)
                    for k in ("tipo_nome", "pais_nome", "setor_nome", "rating")},
        "dados_simulados": any(c["dados_simulados"] for c in casos),
        "limites": [LIMITE_RATIOS, "Cada linha preserva os cortes de preço, modelo e nota. "
                    "Retorno esperado não é retorno realizado, recomendação ou tamanho de posição.",
                    "O grupo estatístico e sua mediana são os registrados no modelo. "
                    "Os comparáveis econômicos selecionados neste dashboard têm critério próprio; "
                    "a seleção não recalcula o grupo estatístico do modelo.",
                    "A identidade exibida é a recebida no dossiê; este dashboard não executa "
                    "nova conferência da trilha. Nenhuma análise preliminar vira narrativa publicada."],
    }


def _s(value: object) -> str:
    return html.escape(str(value if value is not None else ND), quote=True)


def _href(value: str) -> str:
    if type(value) is not str or not re.fullmatch(
        r"\.\./(?:ativos/[a-z0-9_-]{1,64}/(?:#tese|analise\.json)?|cobertura-modelo-[0-9]+\.json)",
        value,
    ):
        raise ValueError("Endereço fora das rotas públicas de cases")
    return _s(value)


def _attrs(c: dict) -> str:
    return " ".join(f'data-ord-{k}="{_s(v)}"' for k, v in c["ordinais"].items())


def _opcoes(values: list[str]) -> str:
    return '<option value="">Todos</option>' + "".join(
        f'<option value="{_s(v)}">{_s(v)}</option>' for v in values)


def _grupo_modelo(caso: dict) -> str:
    grupo = caso["comparacao_modelo"]
    n = grupo["n"] if grupo["n"] is not None else ND
    return f'Grupo do modelo: {grupo["grupo"]} · n={n} · mediana do α: {grupo["mediana"]}'


def renderizar_dashboard_cases(dashboard: dict) -> str:
    """Fragmento HTML; shell/CSP/publicação permanecem responsabilidade do site nativo."""
    if type(dashboard) is not dict or dashboard.get("schema") != SCHEMA:
        raise ValueError("Dashboard fora do contrato de cases")
    casos, kpis = dashboard["casos"], dashboard["indicadores"]
    indicadores = "".join(f'<div><dt>{_s(t)}</dt><dd>{kpis[k]}</dd></div>' for k, t in (
        ("companhias", "Companhias"), ("etfs", "ETFs"),
        ("narrativas_publicadas", "Narrativas publicadas"), ("retornos_citaveis", "Retornos citáveis")))
    filtros = "".join(f'<label>{_s(t)}<select data-cases-filtro="{k}" aria-label="{_s(t)}">'
                       + _opcoes(dashboard["filtros"][k]) + '</select></label>' for k, t in (
                           ("tipo_nome", "Instrumento"), ("pais_nome", "País"),
                           ("setor_nome", "Setor"), ("rating", "Visão do modelo")))
    options, cards, rows = [], [], []
    for c in casos:
        g = c["comparaveis"]
        options.append(f'<option value="{_s(c["iid"])}" data-local="{_s(",".join(g["local"]))}" '
                       f'data-regional="{_s(",".join(g["regional"]))}" data-criterio="{_s(g["criterio"])}" '
                       f'data-limite="{_s(g["limite"])}">{_s(c["ticker"])} · {_s(c["nome"])} '
                       f'({_s(c["tipo_nome"])})</option>')
        nota = c["nota"]
        nota_link = (f'<a href="{_href(nota["href"])}">Nota pública · {_s(nota["data"])}</a>'
                     if nota["href"] else _s(nota["estado"]))
        model_link = (f'<a href="{_href(c["modelo_href"])}" title="SHA-256 {_s(c["modelo_sha256"])}">Modelo aberto</a>'
                      if c["modelo_href"] else "Modelo sem identidade disponível")
        cards.append(f'''<li class="cases-card" data-case="{_s(c['iid'])}" data-busca="{_s(c['busca'])}"
data-tipo_nome="{_s(c['tipo_nome'])}" data-pais_nome="{_s(c['pais_nome'])}" data-setor_nome="{_s(c['setor_nome'])}"
data-rating="{_s(c['rating'])}" {_attrs(c)}>
<div class="cases-card-top"><span>{_s(c['tipo_nome'])} · {_s(c['ticker'])}</span><span class="cases-status">{_s(c['rating'])}</span></div>
<h2><a href="{_href(c['href'])}">{_s(c['nome'])}</a></h2><p class="cases-meta">{_s(c['pais_nome'])} · {_s(c['setor_nome'])}</p>
<p class="cases-method">{_s(c['arquetipo'])}</p><dl class="cases-card-numbers"><div><dt>Retorno esperado</dt><dd>{_s(c['etr_texto'])}</dd></div>
<div><dt>Referência · {_s(c['moeda'])}</dt><dd>{_s(c['preco_texto'])}</dd></div></dl>
<p class="cases-meta">Modelo: {_s(c['corte_modelo'])} · preço: {_s(c['preco_data'])}</p>
<p class="cases-meta cases-model-group">{_s(_grupo_modelo(c))}</p>
<p class="cases-note">{nota_link}</p><p class="cases-quality">{_s(c['qualidade'])}</p>
<div class="cases-card-actions"><a href="{_href(c['href'])}">Ler case <span aria-hidden="true">↗</span></a>
<button type="button" data-comparar="{_s(c['iid'])}">Comparáveis</button></div></li>''')
        rows.append(f'''<tr data-peer="{_s(c['iid'])}" data-busca="{_s(c['busca'])}" {_attrs(c)}>
<th scope="row"><a href="{_href(c['href'])}">{_s(c['ticker'])}</a><small>{_s(c['nome'])} · {_s(c['tipo_nome'])}</small></th>
<td>{_s(c['pais_nome'])}<small>{_s(c['setor_nome'])}</small></td>
<td>{_s(c['arquetipo'])}<small>{_s(c['metodos'])}</small><small>{_s(_grupo_modelo(c))}</small>{'<small>Índice: ' + _s(c['indice']) + '</small>' if c['tipo'] == 'etf' else ''}</td>
<td>{_s(c['rating'])}<small>Confiança: {_s(c['confianca'])}</small></td><td>{_s(c['qualidade'])}</td>
<td class="cases-num">{_s(c['preco_texto'])}<small>{_s(c['moeda'])} · {_s(c['preco_data'])}</small></td>
<td class="cases-num">{_s(c['etr_texto'])}<small>Modelo: {_s(c['corte_modelo'])}<br>Cobertura: {_s(c['corte_cobertura'])}</small></td>
<td title="{_s(c['limite_ratios'])}">{_s(c['ratios'])}</td><td>{nota_link}<small>Corte da pesquisa: {_s(c['corte_pesquisa'])}</small><small>{model_link} · <a href="{_href(c['dados_href'])}">Dados</a></small></td></tr>''')
    limites = "".join('<li>' + _s(t) + '</li>' for t in dashboard["limites"])
    sim = '<p class="cases-sim">DADOS SIMULADOS</p>' if dashboard["dados_simulados"] else ""
    vazio = '<p>Não há dossiês públicos recebidos neste recorte.</p>' if not casos else ""
    return f'''<link rel="stylesheet" href="../dashboard-cases.css">
<a class="cases-skip" href="#cases-lista">Ir para os cases</a>
<main class="cases-shell" id="cases-dashboard"><header class="cases-hero"><p class="cases-kicker">CDP · Pesquisa por ativo</p>
<h1>Cases e comparáveis</h1><p>Pesquisa organizada por negócio, modelo e evidência. Escolha um ativo para ler a tese ou examinar seu grupo de comparação.</p>{sim}
<dl class="cases-kpis">{indicadores}</dl><p class="cases-meta">Indicadores do recorte completo; os filtros não recalculam estatísticas financeiras.</p></header>
<section class="cases-section" aria-labelledby="cases-catalogo-titulo"><div class="cases-section-head"><div><p class="cases-kicker">Universo de pesquisa</p>
<h2 id="cases-catalogo-titulo">Encontre um case</h2></div><a href="../ativos/">Todas as teses e análises</a></div>
<div class="cases-controls"><label class="cases-search">Buscar<input id="cases-busca" type="search" placeholder="Empresa, ticker ou método" autocomplete="off"></label>{filtros}
<label>Ordenar<select id="cases-ordem"><option value="nome">Nome · companhias / ETFs</option><option value="estado">Estado da pesquisa</option>
<option value="corte">Modelo mais recente</option><option value="etr">Retorno esperado citável · maior primeiro</option></select></label></div>
<p id="cases-filtro-estado" class="cases-meta" role="status" aria-live="polite">{kpis['total']} dossiês no recorte completo.</p>{vazio}
<ul class="cases-grid" id="cases-lista">{''.join(cards)}</ul><p id="cases-sem-resultados" hidden>Nenhum case corresponde aos filtros.</p></section>
<section class="cases-section" aria-labelledby="cases-comparaveis-titulo"><p class="cases-kicker">Comparação com contexto</p><h2 id="cases-comparaveis-titulo" tabindex="-1">Comparáveis do case</h2>
<div class="cases-peer-controls"><label>Case de referência<select id="cases-referencia">{''.join(options)}</select></label>
<label>Grupo<select id="cases-grupo"><option value="local">Mesmo país</option><option value="regional">América Latina</option></select></label>
<label>Buscar no grupo<input id="cases-peer-busca" type="search" placeholder="Nome ou ticker"></label>
<label>Ordenar linhas<select id="cases-peer-ordem"><option value="nome">Nome</option><option value="corte">Modelo mais recente</option><option value="etr">Retorno esperado citável</option></select></label></div>
<p id="cases-criterio" class="cases-criterio">Selecione um case. Sem JavaScript, a tabela abaixo apresenta o universo recebido; ela não é um grupo de peers.</p>
<p id="cases-peer-limite" class="cases-meta">Preços nominais não são comparáveis entre ativos. Cada linha tem moeda e cortes próprios.</p>
<div class="cases-table-wrap" tabindex="0" role="region" aria-label="Tabela de comparáveis com cortes por linha"><table class="cases-table"><caption>Medidas públicas recebidas por ativo; sem múltiplos inferidos.</caption>
<thead><tr><th scope="col">Ativo</th><th scope="col">País / setor</th><th scope="col">Enquadramento / métodos</th><th scope="col">Visão / confiança</th>
<th scope="col">Qualidade do modelo</th><th scope="col">Preço de referência</th><th scope="col">Retorno esperado</th><th scope="col">Múltiplos</th><th scope="col">Pesquisa / fontes</th></tr></thead>
<tbody id="cases-peer-linhas">{''.join(rows)}</tbody></table></div><p id="cases-peers-vazios" hidden>Não há comparáveis recebidos neste grupo. O grupo regional é uma escolha explícita; não ampliamos o critério automaticamente.</p></section>
<section class="cases-section cases-limits" aria-labelledby="cases-limites-titulo"><h2 id="cases-limites-titulo">Critérios e limites de leitura</h2><ul>{limites}</ul></section></main>
<script src="../dashboard-cases.js" defer></script>'''
