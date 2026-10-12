"""Dashboard de apresentação sobre o payload do painel já conferido.

Não lê o livro, não estima risco e não autentica o payload. O produtor do site é
responsável pela conferência prévia. Escalas, formatação e reconciliações de
apresentação são calculadas aqui; o HTML não recalcula números.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal
from html import escape
from typing import Any

SCHEMA = "cdp.dashboard.risco/v1"
_TRANSPORT_KEYS = frozenset({"_colunas", "_n", "_rep", "_partes", "_igual"})
_GROUPS = {"country": "País ou região", "sector": "Setor", "style": "Estilo",
           "currency": "Moeda", "market": "Mercado e temas"}
_STATUS = {"ok": "Dentro do limite", "alerta": "Alerta", "excesso": "Excesso",
           "n/d": "n/d", "info": "Informativo"}
_COUNTRIES = {"AR": "Argentina", "BR": "Brasil", "CL": "Chile", "CO": "Colômbia",
              "MX": "México", "PE": "Peru", "UY": "Uruguai", "LATAM": "América Latina"}
_MARKET_LABELS = {"tema:state_owned": "Tema: estatais", "commodity:oil": "Commodity: petróleo",
                  "commodity:copper": "Commodity: cobre", "commodity:gold": "Commodity: ouro"}


def _obj(value: Any) -> dict:
    return value if type(value) is dict else {}


def _rows(value: Any) -> list[dict]:
    return [_obj(row) for row in value] if type(value) is list else []


def _text(value: Any) -> str | None:
    return value if type(value) is str and value else None


def _num(value: Any) -> float | None:
    if type(value) not in (float, int):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _exigir_expandido(value: Any) -> None:
    """A codificação de transporte não pode virar linha ou valor financeiro."""
    if type(value) is dict:
        if _TRANSPORT_KEYS.intersection(value):
            raise ValueError("Payload compactado: expanda com painel_publicacao.expandir antes do dashboard de risco.")
        for child in value.values():
            _exigir_expandido(child)
    elif type(value) is list:
        for child in value:
            _exigir_expandido(child)


def _fmt(value: Any, unit: str = "pct", *, signed: bool = False,
         precision: int | None = None) -> str:
    if type(value) is list:
        return " a ".join(_fmt(v, unit, signed=signed, precision=precision) for v in value)
    if unit == "text":
        return _text(value) or "n/d"
    number = _num(value)
    if number is None:
        return "n/d"
    display = Decimal(str(number)) * (100 if unit == "pct" else 1)
    sign = "+" if signed and display > 0 else ""
    if abs(display) >= Decimal("1e10"):
        text = f"{display:.2E}".replace(".", ",")
    else:
        places = precision if precision is not None else 0 if unit == "count" else 2
        text = f"{display:,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    suffix = {"pct": "%", "days": " dias", "x": "×"}.get(unit, "")
    return ("US$ " if unit == "usd" else "") + sign + text + suffix


def _bars(rows: list[dict], *, precision: int | None = None) -> list[dict]:
    """Domínio simétrico próprio; falta não participa da escala e zero é legítimo."""
    valid = [abs(v) for row in rows if (v := _num(row.get("value"))) is not None]
    domain = max(valid, default=0.0)
    out = []
    for row in rows:
        value = _num(row.get("value"))
        width = abs(value) / domain * 46 if value is not None and domain > 0 else 0.0
        direction = "negativo" if value is not None and value < 0 else "positivo"
        if value == 0:
            direction = "zero"
        out.append({**row, "value": value, "domain_abs": domain,
                    "display": _fmt(value, row.get("unit", "pct"), signed=True, precision=precision),
                    "sign": direction if value is not None else "ausente",
                    "bar_width": f"{width:.3f}%",
                    "bar_left": f"{50 - width if direction == 'negativo' else 50:.3f}%"})
    return out


def _exposure_groups(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Unidades e medidas diferentes não compartilham domínio de apresentação."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["unit"], row["measure"]), []).append(row)
    return groups


def _exposure_bars(rows: list[dict]) -> list[dict]:
    """Escalas independentes, mantendo a ordem original das linhas recebidas."""
    formatted = {}
    for (unit, measure), values in _exposure_groups(rows).items():
        bars = _bars(values, precision=4 if unit == "ratio" and measure == "Σ w·β" else None)
        formatted.update((id(original), bar) for original, bar in zip(values, bars, strict=True))
    return [formatted[id(row)] for row in rows]


def _maps(value: Any, key: str, number: str, *, labels: dict | None = None,
          unit: str = "pct") -> list[dict]:
    raw = ([{key: k, number: v} for k, v in value.items()]
           if type(value) is dict else _rows(value))
    rows = [{"key": _text(row.get(key)), "label": _text((labels or {}).get(row.get(key)))
             or _text(row.get("name")) or _text(row.get(key)) or "Identificação n/d",
             "value": _num(row.get(number)), "unit": unit} for row in raw]
    rows.sort(key=lambda row: (row["value"] is None, -abs(row["value"] or 0), row["label"]))
    return _bars(rows)


def _factor_loadings(value: Any, labels: dict) -> list[dict]:
    """Preserva a unidade declarada; não deduz porcentagem de uma carga fatorial."""
    raw = ([{"factor": k, **v} if type(v) is dict else {"factor": k, "value": v}
            for k, v in value.items()] if type(value) is dict else _rows(value))
    groups: dict[str, list[dict]] = {}
    for row in raw:
        key = _text(row.get("factor"))
        measure = _text(row.get("measure")) or _text(row.get("unit")) or "unidade n/d"
        groups.setdefault(measure, []).append({"key": key,
            "label": _text(labels.get(key)) or _text(row.get("name")) or key or "Fator n/d",
            "value": _num(row.get("value")), "unit": "ratio", "measure": measure})
    out = []
    for rows in groups.values():
        rows.sort(key=lambda row: (row["value"] is None, -abs(row["value"] or 0), row["label"]))
        out.extend(_bars(rows))
    return out


def _positions(value: Any, *, daily: bool) -> list[dict]:
    out = []
    for row in _rows(value):
        weight = _num(row.get("weight"))
        side = "LONG" if weight is not None and weight > 0 else "SHORT" if weight is not None and weight < 0 else "NEUTRA" if weight == 0 else None
        reported = _text(row.get("side"))
        mismatch = reported in {"LONG", "SHORT"} and side not in {None, "NEUTRA", reported}
        out.append({"issuer_id": _text(row.get("issuer_id")),
                    "name": _text(row.get("name")) or _text(row.get("issuer_id")) or "Identificação n/d",
                    "ticker": _text(row.get("ticker" if daily else "execution_ticker")),
                    "country": _text(row.get("country")), "sector": _text(row.get("sector")),
                    "weight": weight, "weight_display": _fmt(weight, signed=True),
                    "side": side, "side_reported": reported, "side_mismatch": mismatch,
                    "market_value_usd": _num(row.get("market_value_usd" if daily else "notional_usd")),
                    "risk_share": _num(row.get("risk_contribution_ex_ante" if daily else "risk_contribution")),
                    "risk_basis": "ex-ante da decisão", "days_to_liquidate": _num(row.get("days_to_liquidate")),
                    "adtv_usd": _num(row.get("adtv_usd")), "pct_adtv": _num(row.get("pct_adtv")),
                    "squeeze": _text(row.get("squeeze_bucket")),
                    "borrow_fee_annual": _num(row.get("borrow_fee_annual")),
                    "day_pnl_usd": _num(row.get("day_pnl_usd")) if daily else None})
    return sorted(out, key=lambda row: (row["weight"] is None, -abs(row["weight"] or 0), row["name"]))


def _reconcile(positions: list[dict], risk: dict, known: bool) -> dict:
    weights = [p["weight"] for p in positions]
    present = known and all(v is not None for v in weights)
    try:
        net = math.fsum(weights) if present else None
        gross = math.fsum(abs(v) for v in weights) if present else None
    except OverflowError:
        net = gross = None
    reported_net, reported_gross = _num(risk.get("net")), _num(risk.get("gross"))
    comparable = all(v is not None for v in (net, gross, reported_net, reported_gross))
    agrees = (math.isclose(net, reported_net, rel_tol=0, abs_tol=1e-8)
              and math.isclose(gross, reported_gross, rel_tol=0, abs_tol=1e-8)) if comparable else None
    return {"positions_known": known, "net_from_positions": net, "gross_from_positions": gross,
            "net_reported": reported_net, "gross_reported": reported_gross, "agrees": agrees,
            "status": "coerente" if agrees is True else "divergente" if agrees is False else "n/d"}


def _view(identifier: str, title: str, position_source: str | None, risk_source: str | None,
          risk: dict, position_body: dict,
          cut: str | None, week: str | None, *, daily: bool, labels: dict) -> dict:
    positions = _positions(position_body.get("positions"), daily=daily)
    exposures: dict[str, list[dict]] = {group: [] for group in _GROUPS}
    for row in _rows(risk.get("exposures")):
        group = row.get("group")
        if group not in exposures:
            continue
        measure = _text(row.get("measure"))
        unit = "ratio" if group == "style" or measure in {"Σ w·β", "z × NAV"} else "pct"
        name = _text(row.get("name"))
        label = _text(labels.get(f"{group}:{name}")) or _text(labels.get(name))
        if label is None and group == "country":
            label = _COUNTRIES.get(name)
        if label is None and group == "market":
            label = _MARKET_LABELS.get(name)
        exposures[group].append({"key": name,
            "label": label or name or "Identificação n/d",
            "value": _num(row.get("net")), "unit": unit, "measure": measure or ("fração do PL" if unit == "pct" else "carga do modelo"),
            "long": _num(row.get("long")), "short": _num(row.get("short")),
            "gross": _num(row.get("gross")), "gross_unit": unit,
            "gross_display": _fmt(row.get("gross"), unit,
                                  precision=4 if unit == "ratio" and measure == "Σ w·β" else None),
            "limit": _num(row.get("limit")),
            "status": _text(row.get("status")), "severity": _text(row.get("severity"))})
    exposures = {group: _exposure_bars(rows) for group, rows in exposures.items()}
    decomposition = _obj(risk.get("risk_decomposition"))
    factor_source = ("factor_contributions" if "factor_contributions" in risk else
                     "risk_decomposition.by_factor" if "by_factor" in decomposition else None)
    factor_body = risk.get("factor_contributions") if "factor_contributions" in risk else decomposition.get("by_factor")
    factor = _maps(factor_body, "factor", "share", labels=labels)
    stress = _maps(risk.get("stress_tests"), "scenario", "pnl")
    names = {p["issuer_id"]: p["name"] for p in positions}
    top = _maps(risk.get("top_risk_contributors"), "issuer_id", "share", labels=names)
    direct_groups = _maps(decomposition.get("by_group"), "group", "share")
    factor_exposures = _factor_loadings(risk.get("factor_exposures"), labels)
    kpis = [("ex_ante_vol", "Volatilidade ex-ante", "pct", "ao ano"),
            ("gross", "Exposição bruta", "pct", "do PL"),
            ("net", "Exposição líquida", "pct", "do PL · sinal preservado"),
            ("beta", "Beta de mercado", "ratio", "coeficiente"),
            ("var_1d_99", "VaR de 1 dia · 99%", "pct", "perda / PL"),
            ("es_1d_99", "ES de 1 dia · 99%", "pct", "perda / PL"),
            ("factor_risk_share", "Parcela fatorial", "pct", "da variância ex-ante · sem ajuste κ_F"),
            ("specific_vol", "Volatilidade específica", "pct", "ao ano")]
    reconciliation = _reconcile(positions, risk, type(position_body.get("positions")) is list)
    fields = {"exposures": "exposures" if "exposures" in risk else None,
              "factor_contributions": factor_source,
              "stress": "stress_tests" if "stress_tests" in risk else None,
              "top_position_risk": "top_risk_contributors" if "top_risk_contributors" in risk else None,
              "direct_risk_groups": "risk_decomposition.by_group" if "by_group" in decomposition else None,
              "factor_exposures": "factor_exposures" if "factor_exposures" in risk else None}
    field_sources = {key: f"{risk_source}.{path}" if risk_source and path else None
                     for key, path in fields.items()}
    return {"id": identifier, "title": title, "source": position_source,
            "position_source": position_source, "risk_source": risk_source,
            "risk_field_sources": field_sources,
            "risk_normalization": {
                "method": "risk_decomposition sem ajuste κ_F" if
                    _num(risk.get("factor_risk_share")) is not None or factor or top or direct_groups else None,
                "factor_share_source": f"{risk_source}.factor_risk_share" if
                    risk_source and _num(risk.get("factor_risk_share")) is not None else None},
            "position_field_source": f"{position_source}.positions" if position_source and "positions" in position_body else None,
            "cut": cut, "week": week,
            "available": bool(risk or position_body), "positions": positions,
            "positions_known": type(position_body.get("positions")) is list,
            "kpis": [{"key": key, "label": label, "value": _num(risk.get(key)), "unit": unit,
                      "display": _fmt(risk.get(key), unit, signed=key in {"net", "beta"}),
                      "note": "da variância ex-ante · metodologia n/d" if key == "factor_risk_share"
                          and _num(risk.get(key)) is None else note}
                     for key, label, unit, note in kpis],
            "nav_usd": _num(position_body.get("nav_end" if daily else "nav_usd")),
            "exposures": exposures, "factor_contributions": factor, "stress": stress,
            "factor_source": factor_source, "direct_risk_groups": direct_groups,
            "factor_exposures": factor_exposures,
            "top_position_risk": top, "reconciliation": reconciliation,
            "record_hash": _text(position_body.get("record_hash")) if daily else None,
            "proposal_id": _text(position_body.get("proposal_id")) if not daily else None,
            "approval_hash": _text(position_body.get("approval_hash")),
            "snapshot_hash": _text(position_body.get("snapshot_hash")),
            "config_hash": _text(position_body.get("config_hash")),
            "source_link": "../data.json", "risk_basis": "diário" if daily else "ex-ante da proposta"}


def construir_dashboard_risco(payload: dict) -> dict:
    """Transforma somente dados recebidos; nenhuma ausência é completada pela outra view."""
    if type(payload) is not dict:
        raise TypeError("O payload do painel deve ser um dict.")
    _exigir_expandido(payload)
    meta, risk, latest = map(_obj, (payload.get("meta"), payload.get("risk"), payload.get("latest_day")))
    labels = _obj(_obj(meta.get("rotulos")).get("fatores"))
    weeks = [w for w in _rows(payload.get("weeks")) if _obj(w.get("proposal"))]
    weeks.sort(key=lambda w: _text(w.get("week")) or "")
    chosen = weeks[-1] if weeks else {}
    proposal = _obj(chosen.get("proposal"))
    week = _text(chosen.get("week")) or _text(proposal.get("week"))
    live_week = _text(risk.get("live_week"))
    same_week = week is not None and week == live_week
    proposal_risk = _obj(proposal.get("risk"))
    proposal_risk_source = "weeks[].proposal.risk" if proposal_risk else None
    if not proposal_risk and same_week:
        proposal_risk = _obj(risk.get("ex_ante"))
        proposal_risk_source = "risk.ex_ante" if proposal_risk else None
    daily_risk = _obj(risk.get("daily")) if latest else {}
    daily_risk_source = "risk.daily" if daily_risk else None
    if latest and not daily_risk:
        daily_risk = _obj(latest.get("risk"))
        daily_risk_source = "latest_day.risk" if daily_risk else None
    recorded_week = _text(latest.get("live_book_week"))
    effective = bool(latest) and risk.get("executed") is True and recorded_week is not None and recorded_week == live_week
    title = "Carteira efetivada · registro diário" if effective else "Registro diário · efetivação não identificada" if latest else "Registro diário indisponível"
    recorded = _view("registro", title, "latest_day" if latest else None, daily_risk_source, daily_risk, latest,
                     _text(latest.get("date")), recorded_week, daily=True, labels=labels)
    target = _view("proposta", "Proposta · pesos-alvo", "weeks[].proposal" if proposal else None,
                   proposal_risk_source, proposal_risk, proposal,
                   _text(proposal.get("created_at")), week, daily=False, labels=labels)
    target["executed"] = chosen.get("executed") is True
    target["state"] = _text(chosen.get("stage_label")) or _text(chosen.get("state"))
    target["note"] = "Risco ex-ante e pesos-alvo registrados na proposta."
    recorded["executed"] = effective
    recorded["note"] = "Pesos da marcação diária; liquidez e risco por posição ex-ante conservam a referência da decisão."
    model = _obj(payload.get("modelo"))
    model_risk = _obj(model.get("risco")) if _text(model.get("semana")) == week and week is not None else {}
    groups = {"decisao": [], "base": []}
    for row in _rows(model_risk.get("grupos")):
        for basis in groups:
            groups[basis].append({"key": _text(row.get("grupo")),
                "label": _text(row.get("rotulo")) or _text(row.get("grupo")) or "Grupo n/d",
                "value": _num(row.get(basis)), "unit": "pct"})
    target["risk_groups"] = {basis: _bars(rows) for basis, rows in groups.items()}
    target["model_parameters"] = [{"label": _text(row.get("rotulo")), "text": _text(row.get("texto"))}
                                  for row in _rows(model_risk.get("parametros"))]
    target["model_factors"] = [{"label": _text(row.get("grupo")), "count": _num(row.get("n")),
                               "text": _text(row.get("texto"))} for row in _rows(model_risk.get("fatores"))]
    target["model_note"] = _text(model_risk.get("kappa_fonte"))
    target["model_normalization"] = {
        "method": "participação de Euler na variância com κ_F" if "grupos" in model_risk else None,
        "kappa_text": _text(model_risk.get("kappa_texto")),
        "kappa_origin": _text(model_risk.get("kappa_fonte")),
        "source": "modelo.risco.grupos" if "grupos" in model_risk else None,
        "decision_origin": "overrides.risco.por_grupo" if "grupos" in model_risk else None,
        "base_origin": "overrides.risco.por_grupo_base" if "grupos" in model_risk else None,
        "kappa_source": "modelo.risco.kappa_texto" if _text(model_risk.get("kappa_texto")) else None,
        "kappa_origin_source": "overrides.risco.kappa_f" if _text(model_risk.get("kappa_texto"))
            and _text(model_risk.get("kappa_fonte")) else None}
    target["model_week"] = _text(model.get("semana")) if model_risk else None
    target["model_field_sources"] = {key: f"modelo.risco.{key}" if key in model_risk else None
                                     for key in ("grupos", "parametros", "fatores")}
    checks = []
    for row in _rows(risk.get("limit_checks")):
        unit = _text(row.get("unit")) or "ratio"
        precision = 4 if row.get("id") == "commodity_beta" and unit == "ratio" else None
        value = [_num(v) for v in row["value"]] if type(row.get("value")) is list else _text(row.get("value")) if unit == "text" else _num(row.get("value"))
        limit = [_num(v) for v in row["limit"]] if type(row.get("limit")) is list else _text(row.get("limit")) if unit == "text" else _num(row.get("limit"))
        checks.append({"id": _text(row.get("id")), "label": _text(row.get("label")),
                       "basis": _text(row.get("basis")), "value": value,
                       "limit": limit, "value_display": _fmt(row.get("value"), unit, precision=precision),
                       "limit_display": _fmt(row.get("limit"), unit, precision=precision), "unit": unit,
                       "status": _text(row.get("status")), "floor": row.get("floor") is True,
                       "severity": _text(row.get("severity")), "detail": _text(row.get("detail")),
                       "utilization": _num(row.get("utilization")),
                       "shortfall": _num(row.get("shortfall")), "headroom": _num(row.get("headroom"))})
    raw_liquidity = _obj(risk.get("liquidity_by_side"))
    liquidity = {side: {key: _num(_obj(raw_liquidity.get(side)).get(key))
                        for key in ("max_days", "limit", "n", "participation", "n_missing")}
                 for side in ("LONG", "SHORT") if type(raw_liquidity.get(side)) is dict}
    liquidity_summary = {key: _num(raw_liquidity.get(key))
                         for key in ("liquid_3d", "liquid_5d", "n_missing_adtv")}
    warnings = []
    for view in (recorded, target):
        if view["reconciliation"]["agrees"] is False:
            warnings.append(f"{view['title']}: soma dos pesos difere da exposição gravada; valores preservados.")
        if any(p["side_mismatch"] for p in view["positions"]):
            warnings.append(f"{view['title']}: ponta declarada diverge do sinal do peso.")
    return {"schema": SCHEMA, "title": "Carteira, risco e fatores", "views": [recorded, target],
            "is_synthetic": meta.get("is_synthetic") is True,
            "data_notice": _text(meta.get("data_notice")), "generated_at": _text(meta.get("generated_at")),
            "data_hash": _text(meta.get("data_hash")), "config_hash_panel": _text(meta.get("config_hash")),
            "basis_note": _text(risk.get("basis_note")), "limit_week": live_week,
            "limits": checks, "liquidity": liquidity, "liquidity_summary": liquidity_summary,
            "limit_source": "risk.limit_checks" if "limit_checks" in risk else None,
            "liquidity_source": "risk.liquidity_by_side" if "liquidity_by_side" in risk else None,
            "warnings": warnings,
            "sources": [{"url": "../data.json", "label": "Retrato completo do painel"},
                        {"url": "../dados/", "label": "Documentos e trilha do livro"}]}


CSS = """
.dr-dashboard{--dr-ink:#193630;--dr-muted:#54645e;--dr-line:#d5ddd3;--dr-paper:#fffefb;--dr-positive:#196650;--dr-negative:#9d342d;color:var(--dr-ink);max-width:1440px;margin:0 auto;padding:clamp(16px,3vw,36px);font:15px/1.55 system-ui,sans-serif;background:#f5f4eb;border:1px solid var(--dr-line);border-radius:18px}
.dr-dashboard *{box-sizing:border-box}.dr-dashboard h1,.dr-dashboard h2,.dr-dashboard h3{line-height:1.2;color:var(--dr-ink);margin:0 0 14px}.dr-dashboard h1{font-size:clamp(27px,4vw,40px);letter-spacing:-.04em}.dr-dashboard h2{font-size:22px}.dr-dashboard h3{font-size:16px}.dr-dashboard p{margin:10px 0}.dr-dashboard a{color:#155a46;text-underline-offset:3px}.dr-dashboard a:focus-visible,.dr-dashboard summary:focus-visible{outline:3px solid #9c6b27;outline-offset:5px}.dr-hero{display:flex;gap:24px;justify-content:space-between;align-items:flex-start;margin-bottom:22px}.dr-eyebrow{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.13em}.dr-muted,.dr-note{color:var(--dr-muted);font-size:13px}.dr-badge{display:inline-block;border:1px solid #9aaea3;padding:5px 11px;border-radius:999px;font-weight:700;font-size:12px;background:var(--dr-paper);white-space:nowrap}.dr-synthetic{color:#793b13;border-color:#bf8b52;background:#fff3de}.dr-nav{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 30px}.dr-nav a{border:1px solid var(--dr-line);background:var(--dr-paper);padding:9px 14px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:700}.dr-nav a:hover{background:#e9eee7}.dr-view{scroll-margin-top:18px;border-top:3px solid #526e59;padding-top:25px;margin-top:36px}.dr-view.proposta{border-color:#a97836}.dr-view-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.dr-cuts{display:flex;gap:20px;flex-wrap:wrap;margin:15px 0 20px;font-size:13px}.dr-cuts strong{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dr-muted)}.dr-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}.dr-kpi{border:1px solid var(--dr-line);background:var(--dr-paper);border-radius:11px;padding:16px;min-width:0}.dr-kpi dt{font-size:12px;font-weight:650;color:var(--dr-muted)}.dr-kpi dd{margin:8px 0 1px;font:700 clamp(21px,2.2vw,29px)/1.2 system-ui;letter-spacing:-.04em;overflow-wrap:anywhere}.dr-kpi small{font-size:11px;color:var(--dr-muted)}.dr-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:18px 0}.dr-card{min-width:0;background:var(--dr-paper);padding:22px;border:1px solid var(--dr-line);border-radius:12px}.dr-chart{list-style:none;padding:0;margin:18px 0 8px}.dr-chart li{display:grid;grid-template-columns:minmax(100px,1fr) minmax(80px,1.1fr) 78px;gap:10px;align-items:center;margin:13px 0;font-size:12px}.dr-label{overflow-wrap:anywhere;line-height:1.3}.dr-track{height:16px;position:relative;background:#ecf0e9;border-radius:3px}.dr-track:before{content:'';position:absolute;left:50%;height:100%;border-left:1px solid #86988d}.dr-bar{position:absolute;height:100%;background:var(--dr-positive);border-radius:2px}.dr-bar.negativo{background:var(--dr-negative)}.dr-bar.zero{min-width:2px;background:#627569}.dr-chart-value{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.dr-empty{padding:18px;background:#f4f5ef;border-radius:8px;color:var(--dr-muted);font-size:13px}.dr-source{font-size:11px;margin-top:16px;border-top:1px solid var(--dr-line);padding-top:10px;color:var(--dr-muted)}.dr-dashboard details{margin:17px 0 0}.dr-dashboard summary{cursor:pointer;font-size:13px;font-weight:700;padding:7px 0}.dr-table-wrap{overflow:auto;margin-top:12px}.dr-dashboard table{border-collapse:collapse;font-size:12px;width:100%;min-width:650px}.dr-dashboard th{background:#eef1e9;text-align:left;font-weight:700}.dr-dashboard td,.dr-dashboard th{padding:10px 12px;border-bottom:1px solid var(--dr-line);vertical-align:top}.dr-dashboard td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.dr-dashboard caption{text-align:left;font-size:12px;color:var(--dr-muted);padding:5px 0 12px}.dr-dashboard tbody tr:hover{background:#f5f7f1}.dr-status{font-weight:700;white-space:nowrap}.dr-status.alerta,.dr-status.excesso{color:#963b27}.dr-alert{border-left:4px solid #a05a29;background:#fff1df;padding:12px 16px;margin:18px 0;font-size:13px}.dr-memory{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:16px 0}.dr-memory div{min-width:0;padding:12px;background:#f5f7f0;border-radius:7px}.dr-memory dt{color:var(--dr-muted);font-size:11px}.dr-memory dd{margin:4px 0 0;font-size:13px;overflow-wrap:anywhere}.dr-hash{font-family:ui-monospace,monospace;font-size:11px;overflow-wrap:anywhere}.dr-foot{margin-top:30px;padding-top:20px;border-top:1px solid var(--dr-line);font-size:12px;color:var(--dr-muted)}
.dr-table-wrap{max-width:100%}.dr-table-wrap:focus-visible{outline:3px solid #9c6b27;outline-offset:3px}.dr-dashboard table{display:table}.dr-dashboard caption{display:table-caption}.dr-dashboard thead{display:table-header-group}.dr-dashboard tbody{display:table-row-group}.dr-dashboard tr{display:table-row}.dr-dashboard td,.dr-dashboard th{display:table-cell}
@media(max-width:850px){.dr-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.dr-grid{grid-template-columns:1fr}.dr-hero,.dr-view-head{display:block}.dr-memory{grid-template-columns:1fr}.dr-card{padding:16px}.dr-badge{margin-top:10px}}
@media(max-width:440px){.dr-dashboard{padding:12px;border-radius:9px}.dr-chart li{grid-template-columns:minmax(78px,1fr) minmax(65px,1fr) 66px;gap:6px;font-size:11px}.dr-kpi{padding:12px}.dr-nav a{padding:8px 10px}.dr-cuts{gap:10px}}
@media print{.dr-dashboard{background:white;padding:0;border:0}.dr-nav{display:none}.dr-card,.dr-kpi{break-inside:avoid}.dr-dashboard details{display:block}}
"""


def _esc(value: Any) -> str:
    return escape(_text(value) or "n/d", quote=True)


def _source(path: str | None, basis: str | None = None) -> str:
    return (f'<p class="dr-source">Fonte: <a href="../data.json">retrato do painel</a>'
            f' · <code>{_esc(path)}</code> · {_esc(basis)}</p>')


def _chart(rows: list[dict], title: str, source: str | None, basis: str | None,
           *, maximum: int = 9) -> str:
    items = []
    for row in rows[:maximum]:
        for field in ("bar_left", "bar_width"):
            value = row[field]
            if type(value) is not str or not re.fullmatch(r"\d{1,3}(?:\.\d{1,3})?%", value) or float(value[:-1]) > 100:
                raise ValueError("Escala CSS inválida no dashboard.")
        items.append(f'<li><span class="dr-label">{_esc(row.get("label"))}</span>'
                     f'<span class="dr-track" aria-hidden="true"><span class="dr-bar {_esc(row.get("sign"))}" '
                     f'style="left:{row["bar_left"]};width:{row["bar_width"]}"></span></span>'
                     f'<span class="dr-chart-value">{_esc(row.get("display"))}</span></li>')
    contents = ('<ul class="dr-chart">' + "".join(items) + '</ul><p class="dr-note">'
                'Escala simétrica por gráfico; zero no centro. Sinais preservados.</p>') if rows else '<p class="dr-empty">n/d · dados não disponíveis neste retrato.</p>'
    if len(rows) > maximum:
        contents += f'<p class="dr-note">{maximum} de {len(rows)} linhas; todas as linhas recebidas na tabela.</p>'
    return f'<article class="dr-card"><h3>{escape(title)}</h3>{contents}{_source(source, basis)}</article>'


def _table(headers: tuple[str, ...], rows: list[list[str]], caption: str) -> str:
    if not rows:
        return '<p class="dr-empty">n/d · sem linhas disponíveis.</p>'
    return ('<div class="dr-table-wrap" tabindex="0" role="region" aria-label="'
            + escape(caption, quote=True) + '"><table><caption>' + escape(caption) + '</caption><thead><tr>'
            + ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def _positions_table(view: dict) -> str:
    rows = []
    for p in view["positions"]:
        rows.append([_esc(p["name"]) + '<br><small>' + _esc(p["ticker"]) + '</small>',
                     _esc(p["side"]), _esc(p["country"]), _esc(p["sector"]),
                     _esc(p["weight_display"]), escape(_fmt(p["market_value_usd"], "usd", signed=True)),
                     escape(_fmt(p["risk_share"])), escape(_fmt(p["days_to_liquidate"], "days")),
                     escape(_fmt(p["borrow_fee_annual"]))])
    if view["positions_known"] and not rows:
        return '<p class="dr-empty">Nenhuma posição no retrato recebido.</p>'
    return _table(("Ativo", "Ponta", "País", "Setor", "Peso / PL", "Valor / nocional",
                   "Risco ex-ante / variância", "Liquidação ex-ante", "Aluguel a.a."), rows,
                  "Posições recebidas; risco por nome e liquidez ex-ante pertencem à decisão.")


def _view_html(view: dict) -> str:
    vid = view["id"]
    if vid not in {"registro", "proposta"}:
        raise ValueError("Quadro de risco não reconhecido.")
    kpis = ''.join(f'<div class="dr-kpi"><dt>{_esc(k["label"])}</dt><dd>{_esc(k["display"])}</dd>'
                   f'<small>{_esc(k["note"])}</small></div>' for k in view["kpis"])
    content = (f'<section id="dr-{vid}" class="dr-view {vid}" aria-labelledby="dr-title-{vid}">'
               f'<div class="dr-view-head"><div><p class="dr-eyebrow">{escape(view["risk_basis"])}</p>'
               f'<h2 id="dr-title-{vid}">{_esc(view["title"])}</h2><p class="dr-note">{_esc(view["note"])}</p>'
               '</div><span class="dr-badge">' + ('Efetivação identificada' if view["executed"] else 'Efetivação não identificada')
               + '</span></div><div class="dr-cuts">'
               f'<span><strong>Corte do quadro</strong>{_esc(view["cut"])}</span>'
               f'<span><strong>Semana</strong>{_esc(view["week"])}</span>'
               f'<span><strong>PL de referência</strong>{escape(_fmt(view["nav_usd"], "usd"))}</span></div>'
               f'<dl class="dr-kpis">{kpis}</dl>')
    r = view["reconciliation"]
    content += '<p class="dr-note">Reconciliação dos pesos: ' + escape(r["status"]) + '. '
    if r["net_from_positions"] is not None:
        content += (f'Soma líquida {escape(_fmt(r["net_from_positions"], signed=True))}; '
                    f'soma bruta {escape(_fmt(r["gross_from_positions"]))}. ')
    content += 'A exposição gravada permanece no KPI.</p>'
    normalization = view["risk_normalization"]
    if normalization["method"]:
        content += ('<p class="dr-note">Parcela fatorial do KPI e contribuições por fator e posição: '
                    'participações na variância da decomposição sem ajuste κ_F.</p>')
        content += _source(normalization["factor_share_source"], normalization["method"])
    if vid == "proposta" and view["model_normalization"]["method"]:
        model_normalization = view["model_normalization"]
        content += ('<p class="dr-note">Modelo de decisão e modelo base: participação de Euler na variância '
                    'com ajuste fatorial κ_F = ' + _esc(model_normalization["kappa_text"]) + '; origem: '
                    + _esc(model_normalization["kappa_origin"]) + '. Normalizações distintas não são comparáveis '
                    'diretamente e não são parcelas complementares. A decomposição sem ajuste do KPI, '
                    'dos fatores e das posições usa outra normalização.</p>')
        content += ('<p class="dr-source">Origem da memória: <code>'
                    + _esc(model_normalization["decision_origin"]) + '</code> e <code>'
                    + _esc(model_normalization["base_origin"]) + '</code>; ajuste em <code>'
                    + _esc(model_normalization["kappa_origin_source"]) + '</code>.</p>')
        content += _source(model_normalization["source"], model_normalization["method"])
    content += '<div class="dr-grid">'
    for group in ("country", "sector", "style", "currency", "market"):
        rows = view["exposures"][group]
        if rows:
            for (unit, measure), values in _exposure_groups(rows).items():
                unit_label = ' · coeficiente' if unit == "ratio" and measure == "Σ w·β" else ''
                content += _chart(values, f'Exposição líquida · {_GROUPS[group]} · {measure}{unit_label}',
                                  view["risk_field_sources"]["exposures"], view["risk_basis"])
        elif group in {"country", "sector"}:
            content += _chart([], f'Exposição líquida · {_GROUPS[group]}',
                              view["risk_field_sources"]["exposures"], view["risk_basis"])
    if vid == "proposta":
        for basis, name in (("decisao", "Modelo de decisão"), ("base", "Modelo base")):
            source = view["model_field_sources"]["grupos"]
            content += _chart(view["risk_groups"][basis], f'Participação na variância · {name} · com κ_F',
                              source + '[].' + basis if source else None,
                              'ex-ante · semana ' + (view["week"] or 'n/d'))
    if view["direct_risk_groups"]:
        content += _chart(view["direct_risk_groups"], 'Decomposição recebida · grupos de risco',
                          view["risk_field_sources"]["direct_risk_groups"], view["risk_basis"])
    for measure in dict.fromkeys(row["measure"] for row in view["factor_exposures"]):
        rows = [row for row in view["factor_exposures"] if row["measure"] == measure]
        content += _chart(rows, 'Exposições por fator · ' + measure,
                          view["risk_field_sources"]["factor_exposures"],
                          'valor original, sem conversão · ' + measure)
    content += _chart(view["factor_contributions"], 'Contribuição por fator · variância',
                      view["risk_field_sources"]["factor_contributions"], view["risk_basis"])
    content += _chart(view["top_position_risk"], 'Principais riscos por posição · variância',
                      view["risk_field_sources"]["top_position_risk"], view["risk_basis"])
    content += _chart(view["stress"], 'Cenários de estresse · resultado / PL',
                      view["risk_field_sources"]["stress"], view["risk_basis"])
    content += '</div><details><summary>Consultar exposições e contribuições completas</summary>'
    exp_rows = [[_esc(_GROUPS[group]), _esc(row["label"]), _esc(row["display"]),
                 _esc(row["gross_display"]),
                 escape(_fmt(row["limit"], row["unit"],
                             precision=4 if row["unit"] == "ratio" and row["measure"] == "Σ w·β" else None)),
                 _esc(row["measure"]), _esc(_STATUS.get(row["status"], row["status"]))]
                for group, rows in view["exposures"].items() for row in rows]
    content += _table(("Grupo", "Exposição", "Líquida", "Bruta (unidade da linha)", "Limite", "Unidade", "Estado"),
                      exp_rows, 'Exposições originais: líquida, bruta e limite na unidade indicada em cada linha; n/d preserva ausência.')
    content += _source(view["risk_field_sources"]["exposures"], view["risk_basis"])
    factor_rows = [[_esc(kind), _esc(row["label"]), _esc(row["display"]),
                   _esc(row.get("measure")) if "measure" in row else "fração do PL" if kind.startswith("Estresse") else "fração da variância"]
                   for kind, rows in (("Fator · variância", view["factor_contributions"]),
                                     ("Posição · variância", view["top_position_risk"]),
                                     ("Estresse · resultado / PL", view["stress"]),
                                     ("Grupo · variância", view["direct_risk_groups"]),
                                     ("Carga fatorial · unidade do modelo", view["factor_exposures"])) for row in rows]
    content += _table(("Medida", "Nome", "Valor assinado", "Unidade"), factor_rows,
                      'Contribuições de Euler negativas podem reduzir risco; estresse não é previsão de retorno.')
    content += _source(view["risk_source"], view["risk_basis"])
    content += '</details><details><summary>Consultar posições do quadro · '
    content += f'{len(view["positions"]) if view["positions_known"] else "n/d"}</summary>'
    content += _positions_table(view) + _source(view["position_field_source"], "posições do quadro") + '</details>'
    return content + _source(view["position_source"], "origem das posições") + _source(view["risk_source"], view["risk_basis"]) + '</section>'


def renderizar_dashboard_risco(dashboard: dict) -> str:
    """Fragmento HTML acessível, sem shell, JavaScript, acesso a arquivos ou modelo."""
    if type(dashboard) is not dict or dashboard.get("schema") != SCHEMA:
        raise ValueError("Schema de dashboard de risco não reconhecido.")
    body = f'<style>{CSS}</style><section class="dr-dashboard" aria-labelledby="dr-titulo">'
    badge = '<span class="dr-badge dr-synthetic">DADOS SIMULADOS</span>' if dashboard["is_synthetic"] else '<span class="dr-badge">Carteira simulada · execução hipotética</span>'
    body += ('<header class="dr-hero"><div><p class="dr-eyebrow">CDP · Monitor de carteira</p>'
             f'<h1 id="dr-titulo">{_esc(dashboard["title"])}</h1>'
             '<p class="dr-muted">Exposições, risco estimado e limites no retrato recebido.</p></div>'
             + badge + '</header><nav class="dr-nav" aria-label="Quadros do risco">'
             '<a href="#dr-registro">Registro diário</a><a href="#dr-proposta">Proposta / ex-ante</a>'
             '<a href="#dr-limites">Limites e liquidez</a><a href="#dr-memoria">Modelo e fontes</a></nav>')
    if dashboard["data_notice"]:
        body += '<p class="dr-note">' + _esc(dashboard["data_notice"]) + '</p>'
    for warning in dashboard["warnings"]:
        body += '<p class="dr-alert" role="note">' + _esc(warning) + '</p>'
    body += ''.join(_view_html(view) for view in dashboard["views"])
    body += '<section id="dr-limites" class="dr-view" aria-labelledby="dr-limites-titulo">'
    body += '<h2 id="dr-limites-titulo">Limites e liquidez</h2>'
    body += '<p class="dr-note">' + _esc(dashboard["basis_note"]) + '</p>'
    checks = []
    for c in dashboard["limits"]:
        usage = 'Piso · distância ' + _fmt(c["headroom"], c["unit"], signed=True) if c["floor"] else _fmt(c["utilization"])
        checks.append([_esc(c["label"]), _esc(c["basis"]), _esc(c["value_display"]),
                       _esc(c["limit_display"]), escape(usage), _esc(_STATUS.get(c["status"], c["status"])),
                       _esc(c["severity"]), _esc(c["detail"])])
    body += _table(("Controle", "Base", "Valor", "Limite", "Uso / distância", "Estado", "Severidade", "Detalhe"),
                   checks, 'Estados recebidos do produtor; a página não recalcula gates. Semana ' + (dashboard["limit_week"] or 'n/d') + '.')
    body += _source(dashboard["limit_source"], dashboard["basis_note"])
    liquidity = []
    for side, row in dashboard["liquidity"].items():
        row = _obj(row)
        liquidity.append([_esc(side), escape(_fmt(row.get("participation"))),
                          escape(_fmt(row.get("max_days"), "days")), escape(_fmt(row.get("limit"), "days")),
                          escape(_fmt(row.get("n_missing"), "count"))])
    body += '<details><summary>Consultar liquidez ex-ante por ponta</summary>'
    body += _table(("Ponta", "Participação no ADTV", "Prazo máximo", "Limite de prazo", "Dados ausentes"),
                   liquidity, 'Liquidez ex-ante da decisão; não representa volume executável observado em tempo real.')
    summary = dashboard["liquidity_summary"]
    body += '<p class="dr-note">Parcela da exposição bruta liquidável: '
    body += '3 dias ' + escape(_fmt(summary["liquid_3d"])) + '; 5 dias ' + escape(_fmt(summary["liquid_5d"])) + '. '
    body += 'Posições sem ADTV: ' + escape(_fmt(summary["n_missing_adtv"], "count")) + '.</p>'
    body += '</details>' + _source(dashboard["liquidity_source"], dashboard["basis_note"]) + '</section>'
    body += '<section id="dr-memoria" class="dr-view" aria-labelledby="dr-memoria-titulo">'
    body += '<h2 id="dr-memoria-titulo">Memória do modelo e fontes</h2><p class="dr-note">'
    body += 'Volatilidades anuais; exposições em fração do PL ou na unidade indicada. Participações de Euler podem ser negativas. Cada quadro conserva seu próprio corte; ex-ante não substitui dado diário ausente.</p>'
    target = dashboard["views"][1]
    normalization = target["model_normalization"]
    if normalization["method"]:
        body += ('<p class="dr-note">Memória de grupos com ajuste fatorial κ_F = '
                 + _esc(normalization["kappa_text"]) + ' (' + _esc(normalization["kappa_origin"])
                 + '). O ajuste é aplicado ao bloco fatorial na participação de Euler da variância. '
                 'O KPI e as contribuições por fator e posição conservam a decomposição sem ajuste κ_F. '
                 'Normalizações distintas não são comparáveis diretamente e não são parcelas complementares.</p>')
        body += _source(normalization["kappa_source"], normalization["kappa_origin"])
    memory = [("Retrato gerado em", dashboard["generated_at"]), ("Hash do retrato", dashboard["data_hash"]),
              ("Configuração do painel", dashboard["config_hash_panel"]),
              ("Configuração da proposta", target["config_hash"]), ("Snapshot da proposta", target["snapshot_hash"]),
              ("Semana do modelo recebido", target["model_week"]),
              ("Registro diário", dashboard["views"][0]["record_hash"])]
    body += '<dl class="dr-memory">' + ''.join(f'<div><dt>{escape(label)}</dt><dd class="dr-hash">{_esc(value)}</dd></div>' for label, value in memory) + '</dl>'
    params = [[_esc(row["label"]), _esc(row["text"])] for row in target["model_parameters"]]
    body += _table(("Parâmetro do modelo da proposta", "Valor recebido"), params,
                   'Memória nativa da mesma semana da proposta; nenhum modelo é reestimado nesta página.')
    body += _source(target["model_field_sources"]["parametros"], "modelo da mesma semana da proposta")
    if target["model_factors"]:
        body += _table(("Grupo de fatores", "Quantidade", "Fatores recebidos"),
                       [[_esc(row["label"]), escape(_fmt(row["count"], "count")), _esc(row["text"])] for row in target["model_factors"]],
                       'Catálogo do modelo da mesma semana da proposta.')
        body += _source(target["model_field_sources"]["fatores"], "modelo da mesma semana da proposta")
    for row in dashboard["sources"]:
        if row["url"] not in {"../data.json", "../dados/"}:
            raise ValueError("Fonte fora do contrato do dashboard.")
    body += '<p>' + ' · '.join(f'<a href="{escape(row["url"], quote=True)}">{_esc(row["label"])}</a>' for row in dashboard["sources"]) + '</p></section>'
    body += '<footer class="dr-foot">Carteira simulada. O dashboard apresenta dados e estados já produzidos pelo código; não aprova propostas nem altera limites, posições ou modelos.</footer></section>'
    return body


__all__ = ["construir_dashboard_risco", "renderizar_dashboard_risco"]
