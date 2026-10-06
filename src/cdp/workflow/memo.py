"""Memo semanal da proposta (Markdown, pt-BR) para a decisão do gestor.

Regras:

- Todos os números são formatados por código a partir dos campos da proposta (``fmt_pct``,
  ``fmt_usd_mm`` …); nada é copiado de textos de pesquisa como número "livre".
- Textos de pesquisa (teses, notas macro) são citados como fornecidos, rotulados pela origem
  (gestor ou "gerado por IA" com provedor/modelo) e têm tags HTML removidas. Placeholders
  ``{{fact:<id>}}`` são substituídos pelo valor formatado do FactBook (código), quando houver.
- Manchetes são conteúdo não confiável e não são reproduzidas no memo.
- Dados ausentes aparecem como ``n/d`` — nunca como zero.
"""

from __future__ import annotations

import math
import numbers
import re
from collections import Counter
from datetime import UTC, date, datetime

from .. import SIMULATED_DATA_NOTICE
from ..config import FundConfig
from ..contracts import (
    ComplianceCheck,
    FactBook,
    MacroNote,
    PositionTarget,
    Proposal,
    ProposalState,
    ResearchNote,
    ResearchPack,
    Severity,
    Side,
    Trade,
    ViewSource,
)
from .approval import co_sign_reasons

NA = "n/d"
TOP_N = 10
HASH_PREFIX = 12

# Ordem de preferência da nota usada como tese de cada emissor.
_ROLE_PRIORITY = {"pm": 0, "bull_bear_judge": 1, "fundamental": 2, "short_risk": 3,
                  "news_sentiment": 4}
_SEVERITY_ORDER = {Severity.HARD: 0, Severity.SOFT: 1, Severity.INFO: 2}
_PM_PROVIDERS = {"pm", "gestor", "manual", "human", "humano"}
_STATE_LABEL = {
    ProposalState.DRAFT: "RASCUNHO",
    ProposalState.IN_REVIEW: "EM REVISÃO",
    ProposalState.APPROVED: "APROVADA",
    ProposalState.REJECTED: "REJEITADA",
    ProposalState.BOOKED: "EFETIVADA",
    ProposalState.SUPERSEDED: "SUBSTITUÍDA",
    ProposalState.BLOCKED: "BLOQUEADA (falha HARD)",
}

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>")
_TAG_RE = re.compile(r"<[^>]*>")
_FACT_RE = re.compile(r"\{\{\s*fact:([^}\s]+)\s*\}\}")
_WS_RE = re.compile(r"\s+")


# ==========================================================
# Formatação numérica (pt-BR)
# ==========================================================

def _finite(x: object) -> bool:
    """Número real finito (inclui escalares numpy); ``None``/NaN/inf/bool não são números."""
    return (isinstance(x, numbers.Real) and not isinstance(x, bool)
            and math.isfinite(float(x)))


def _br(value: float, digits: int, signed: bool = False) -> str:
    value = round(value, digits) + 0.0  # sem "-0,00": zero arredondado não tem sinal
    sign = "+" if signed and value > 0 else ""
    text = f"{value:,.{digits}f}"
    return sign + text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_num(x: float | int | None, digits: int = 2, signed: bool = False) -> str:
    """Número em pt-BR (``1.234,56``); ausente ⇒ ``n/d``."""
    return _br(float(x), digits, signed) if _finite(x) else NA


def fmt_pct(x: float | None, digits: int = 2, signed: bool = False) -> str:
    """Fração decimal como porcentagem pt-BR (``0.0512`` ⇒ ``5,12%``); ausente ⇒ ``n/d``."""
    return _br(float(x) * 100.0, digits, signed) + "%" if _finite(x) else NA


def fmt_usd_mm(x: float | None, digits: int = 2, signed: bool = False) -> str:
    """Valor em USD como milhões pt-BR (``1_500_000`` ⇒ ``USD 1,50 mm``); abaixo de US$ 1 mi, em
    milhares (``32_830`` ⇒ ``USD 32,8 mil``: com PL pequeno, posições e P&L não viram
    ``USD 0,03 mm``); ausente ⇒ ``n/d``."""
    if not _finite(x):
        return NA
    v = float(x)
    if 0 < abs(v) < 1e6:
        return f"USD {_br(v / 1e3, 1, signed)} mil"
    return f"USD {_br(v / 1e6, digits, signed)} mm"


def fmt_usd(x: float | None, digits: int = 0, signed: bool = False) -> str:
    """Valor em USD por extenso pt-BR (``4000`` ⇒ ``USD 4.000``); ausente ⇒ ``n/d``."""
    return f"USD {_br(float(x), digits, signed)}" if _finite(x) else NA


def fmt_bps(x: float | None, digits: int = 1) -> str:
    return f"{_br(float(x), digits)} bps" if _finite(x) else NA


def fmt_days(x: float | None, digits: int = 1) -> str:
    return f"{_br(float(x), digits)} d" if _finite(x) else NA


def fmt_closes(x: float | None, digits: int = 1) -> str:
    """Fechamentos (leilões de fechamento) para liquidar ou executar: ``1,5 fech.``."""
    return f"{_br(float(x), digits)} fech." if _finite(x) else NA


def liquidity_unit(cfg: FundConfig | None) -> str:
    """Unidade dos limites de liquidez do mandato: ``"fechamentos"`` com a execução no leilão
    de fechamento (seção ``execution``), senão ``"dias"`` (pregões a uma participação do ADTV;
    regra anterior)."""
    return "fechamentos" if cfg is not None and cfg.execution is not None else "dias"


def fmt_liquidity(x: float | None, cfg: FundConfig | None, digits: int = 1) -> str:
    return fmt_closes(x, digits) if liquidity_unit(cfg) == "fechamentos" else fmt_days(x, digits)


def fmt_date(d: date | datetime) -> str:
    """Data ``dd/mm/aaaa``; horários com fuso são convertidos para UTC antes de rotular."""
    if isinstance(d, datetime):
        if d.tzinfo is None:
            return d.strftime("%d/%m/%Y %H:%M (sem fuso)")
        return d.astimezone(UTC).strftime("%d/%m/%Y %H:%M UTC")
    return d.strftime("%d/%m/%Y")


def _short_hash(h: str) -> str:
    return f"`{h[:HASH_PREFIX]}`" if h else NA


def _cell(text: object) -> str:
    """Conteúdo seguro para célula de tabela Markdown (sem quebra de linha nem ``|`` cru)."""
    return _WS_RE.sub(" ", str(text)).strip().replace("|", "\\|")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out


# ==========================================================
# Texto de pesquisa (não confiável para números)
# ==========================================================

def strip_html(text: str) -> str:
    """Remove tags HTML (e o conteúdo de ``<script>``/``<style>``) de textos de pesquisa."""
    return _TAG_RE.sub("", _SCRIPT_STYLE_RE.sub("", text))


def render_research_text(text: str, factbook: FactBook | None = None) -> str:
    """Limpa HTML, normaliza espaços e resolve ``{{fact:id}}`` com valores do FactBook."""

    def _sub(m: re.Match[str]) -> str:
        fid = m.group(1)
        if factbook is not None and fid in factbook.facts:
            return factbook.facts[fid].formatted
        return f"[fato indisponível: {fid}]"

    return _WS_RE.sub(" ", _FACT_RE.sub(_sub, strip_html(text))).strip()


def _inline(text: object) -> str:
    """Texto não confiável em uma linha (sem HTML nem quebras) para rótulos e títulos."""
    return _WS_RE.sub(" ", strip_html(str(text))).strip()


def _is_pm_provider(provider: str) -> bool:
    return provider.strip().lower() in _PM_PROVIDERS


def _is_pm_note(note: ResearchNote) -> bool:
    """Nota do gestor: papel ``pm`` E provedor humano. Um provedor de IA que declare o papel
    ``pm`` continua rotulado como IA (não se apresenta como visão do gestor)."""
    return note.role == "pm" and _is_pm_provider(note.provider)


def _note_label(note: ResearchNote) -> str:
    if _is_pm_note(note):
        return f"Gestor (PM) — {_inline(note.provider)}"
    model = f", modelo {_inline(note.model)}" if note.model else ""
    return f"gerado por IA — provedor {_inline(note.provider)}{model}, papel {note.role}"


def _macro_label(note: MacroNote) -> str:
    if _is_pm_provider(note.provider):
        return f"Gestor (PM) — {_inline(note.provider)}"
    model = f", modelo {_inline(note.model)}" if note.model else ""
    return f"gerado por IA — provedor {_inline(note.provider)}{model}"


def _best_notes(pack: ResearchPack | None) -> dict[str, ResearchNote]:
    """Nota preferida por emissor (PM > juiz bull×bear > fundamentalista > …)."""
    best: dict[str, ResearchNote] = {}
    if pack is None:
        return best
    for note in pack.notes:
        cur = best.get(note.issuer_id)
        key = (_ROLE_PRIORITY.get(note.role, 9), -note.confidence, note.note_id)
        if cur is None or key < (_ROLE_PRIORITY.get(cur.role, 9), -cur.confidence, cur.note_id):
            best[note.issuer_id] = note
    return best


def _squeeze_notes(pack: ResearchPack | None) -> dict[str, ResearchNote]:
    out: dict[str, ResearchNote] = {}
    if pack is None:
        return out
    for note in sorted(pack.notes, key=lambda n: n.note_id):
        if note.squeeze is not None and note.issuer_id not in out:
            out[note.issuer_id] = note
    return out


# ==========================================================
# Seções
# ==========================================================

def _derived_state(proposal: Proposal) -> ProposalState:
    return ProposalState.BLOCKED if proposal.hard_failures else ProposalState.IN_REVIEW


def _is_synthetic(proposal: Proposal, pack: ResearchPack | None, fb: FactBook | None) -> bool:
    return bool(proposal.is_synthetic or (pack and pack.is_synthetic) or (fb and fb.is_synthetic))


def _section_header(proposal: Proposal, cfg: FundConfig, state: ProposalState,
                    synthetic: bool) -> list[str]:
    out = [f"# {cfg.fund.name} — Proposta da semana de {fmt_date(proposal.week)} "
           f"(v{proposal.version})", ""]
    if synthetic:
        notice = proposal.data_notice or ""
        if notice.upper().startswith(SIMULATED_DATA_NOTICE):
            notice = notice[len(SIMULATED_DATA_NOTICE):].lstrip(" —-:")
        notice = notice or "dados gerados por código para teste/demonstração."
        out += [f"> **{SIMULATED_DATA_NOTICE}** — {notice}",
                "> Esta proposta NÃO usa preços reais e não deve embasar decisões de investimento.",
                ""]
    else:
        notice = f" {proposal.data_notice}" if proposal.data_notice else ""
        out += [f"> Dados de mercado: snapshot `{proposal.snapshot_id}`.{notice}", ""]
    out += _table(["Campo", "Valor"], [
        ["Estado", f"**{_STATE_LABEL[state]}**"],
        ["Proposta", f"{proposal.proposal_id} (versão {proposal.version})"],
        ["Criada em / por", f"{fmt_date(proposal.created_at)} — {proposal.created_by}"],
        ["NAV de referência", fmt_usd_mm(proposal.nav_usd)],
        ["Snapshot", f"{proposal.snapshot_id} — {_short_hash(proposal.snapshot_hash)}"],
        ["Hash da configuração", _short_hash(proposal.config_hash)],
        ["Hash da pesquisa", _short_hash(proposal.research_hash)],
    ])
    return out + [""]


def _vol_status(vol: float, cfg: FundConfig) -> str:
    if not _finite(vol):
        return "vol indisponível"
    if vol < cfg.risk.vol_band_min:
        return "ABAIXO da banda"
    if vol > cfg.risk.vol_band_max:
        return "ACIMA da banda"
    return "dentro da banda"


_GRUPO_PT = {"mercado": "Mercado", "pais": "País", "setor": "Setor", "estilo": "Estilo",
             "macro": "Macro (commodities e dólar)", "especifico": "Específico (idiossincrático)"}


def _idio_rows(risco: dict) -> list[list[str]]:
    """Linhas de risco idiossincrático gravadas na decisão (``overrides["risco"]``)."""
    meta, piso = risco.get("meta_idio"), risco.get("piso_idio")
    ref = (f"meta {fmt_pct(meta, 0)}; piso {fmt_pct(piso, 0)}" if _finite(meta)
           and _finite(piso) else "")
    kap = risco.get("kappa_f") if isinstance(risco.get("kappa_f"), dict) else {}
    rows = [["Fatia idiossincrática — modelo de decisão",
             fmt_pct(risco.get("idio_decisao")) if _finite(risco.get("idio_decisao")) else NA,
             ref + " (com janelas de evento)"]]
    if "base" in (risco.get("modelos_gate") or []):
        rows.append(["Fatia idiossincrática — modelo base",
                     fmt_pct(risco.get("idio_base")) if _finite(risco.get("idio_base")) else NA,
                     ref + " (sem janelas de evento)"])
    if _finite(kap.get("valor")):
        rows.append(["Inflação de 2ª ordem do risco fatorial (κ_F)", fmt_num(kap["valor"], 2),
                     "aplicada à variância fatorial na medida idiossincrática"])
    esc = risco.get("escada")
    if isinstance(esc, dict) and _finite(esc.get("sigma_teto")):
        regra = esc.get("regra_vinculante") or "escada de drawdown"
        ref_txt = (f"{fmt_num(esc.get('multiplicador'), 2)} × vol de referência "
                   f"{fmt_pct(esc.get('sigma_ref'))}")
        rows.append(["Teto de vol pela escada de drawdown", fmt_pct(esc["sigma_teto"]),
                     ref_txt if regra == "escada de drawdown"
                     else f"{regra} (escada: {ref_txt})"])
    return rows


def _section_risk(proposal: Proposal, cfg: FundConfig) -> list[str]:
    r = proposal.risk
    rk = cfg.risk
    nav = proposal.nav_usd

    def pct_usd(x: float) -> str:
        return f"{fmt_pct(x)} ({fmt_usd_mm(x * nav if _finite(x) else None)})"

    risco = proposal.overrides.get("risco") if isinstance(proposal.overrides, dict) else None
    from ..risk.idio import base_vinculante

    basis = base_vinculante(risco)
    if basis is not None:
        # Mesma base do gate: κ_F no bloco fatorial, no modelo que vincula.
        fref = (f"{fmt_pct(basis['fatorial'])} da variância com κ_F no {basis['rotulo']} "
                f"(limite {fmt_pct(rk.max_factor_risk_share)})")
    else:
        fref = (f"{fmt_pct(r.factor_risk_share)} da variância (alerta acima de "
                f"{fmt_pct(rk.max_factor_risk_share)})")
    rows = [
        ["Vol ex-ante (a.a.)", fmt_pct(r.ex_ante_vol),
         f"alvo {fmt_pct(rk.vol_target_annual)}; banda {fmt_pct(rk.vol_band_min)}–"
         f"{fmt_pct(rk.vol_band_max)} — {_vol_status(r.ex_ante_vol, cfg)}"],
        ["Vol fatorial (a.a.)", fmt_pct(r.factor_vol), fref],
        ["Vol específica (a.a.)", fmt_pct(r.specific_vol), "fonte pretendida do retorno (alpha puro)"],
        ["Beta previsto", fmt_num(r.beta, 3), f"limite ±{fmt_num(rk.beta_max_abs, 3)}"],
        ["Gross (% NAV)", fmt_pct(r.gross),
         f"faixa {fmt_pct(rk.gross_min, 0)}–{fmt_pct(rk.gross_max, 0)}"],
        ["Net (% NAV)", fmt_pct(r.net, signed=True), f"limite ±{fmt_pct(rk.net_exposure_max_abs)}"],
        ["Long / Short (% NAV)", f"{fmt_pct(r.long_exposure)} / {fmt_pct(r.short_exposure)}", ""],
        ["Nº de posições long / short", f"{r.n_long} / {r.n_short}", ""],
        ["VaR 1d 99%", pct_usd(r.var_1d_99), "paramétrico/histórico (modelo de risco)"],
        ["ES 1d 99%", pct_usd(r.es_1d_99), ""],
        ["VaR 1 semana 99%", pct_usd(r.var_1w_99), ""],
        ["N efetivo", fmt_num(r.effective_n, 1), "diversificação (1/Σw² normalizado)"],
        *_liquidity_rows(r, cfg),
    ]
    if isinstance(risco, dict):
        rows += _idio_rows(risco)
    out = ["## Resumo de risco", ""] + _table(["Métrica", "Valor", "Referência"], rows) + [""]
    if isinstance(risco, dict) and isinstance(risco.get("por_grupo"), dict):
        grows = [[_GRUPO_PT.get(g, g), fmt_pct(v) if _finite(v) else NA]
                 for g, v in risco["por_grupo"].items()]
        out += ["### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no "
                "bloco fatorial)", ""]
        out += _table(["Grupo", "Fração da variância"], grows) + [""]
    if r.stress_tests:
        srows = [[k, fmt_pct(v, signed=True), fmt_usd_mm(v * nav if _finite(v) else None,
                                                        signed=True)]
                 for k, v in sorted(r.stress_tests.items(),
                                    key=lambda kv: (kv[1] if _finite(kv[1]) else math.inf, kv[0]))]
        out += ["### Testes de estresse (P&L estimado)", ""]
        out += _table(["Cenário", "% NAV", "USD"], srows) + [""]
    if r.factor_contributions:
        frows = [[k, fmt_pct(v)] for k, v in sorted(
            r.factor_contributions.items(),
            key=lambda kv: (-abs(kv[1]) if _finite(kv[1]) else math.inf, kv[0]))[:TOP_N]]
        out += ["### Maiores contribuições fatoriais (fração da variância)", ""]
        out += _table(["Fator", "Contribuição"], frows) + [""]
    if r.top_risk_contributors:
        trows = [[k, fmt_pct(v)] for k, v in sorted(
            r.top_risk_contributors.items(),
            key=lambda kv: (-abs(kv[1]) if _finite(kv[1]) else math.inf, kv[0]))[:TOP_N]]
        out += ["### Maiores contribuições de risco por emissor (fração da variância)", ""]
        out += _table(["Emissor", "Contribuição"], trows) + [""]
    return out


def _fmt_check_value(x: float | None) -> str:
    if not _finite(x):
        return NA
    return fmt_num(x, 4) if abs(float(x)) < 1000 else fmt_num(x, 0)


def _compliance_sort_key(c: ComplianceCheck) -> tuple[int, int, str]:
    return (int(c.passed), _SEVERITY_ORDER.get(c.severity, 9), c.check_id)


def _section_compliance(proposal: Proposal) -> list[str]:
    checks = sorted(proposal.compliance, key=_compliance_sort_key)
    n_fail = sum(not c.passed for c in checks)
    out = ["## Compliance", "",
           f"{len(checks)} verificações; {n_fail} falha(s) "
           f"({len(proposal.hard_failures)} HARD, {len(proposal.soft_failures)} SOFT).", ""]
    rows = [["FALHA" if not c.passed else "ok", c.severity.value, f"{c.name} (`{c.check_id}`)",
             _fmt_check_value(c.value), _fmt_check_value(c.limit), c.details]
            for c in checks]
    out += _table(["Status", "Severidade", "Verificação", "Valor", "Limite", "Detalhes"], rows)
    return out + [""]


def _position_row(rank: int, p: PositionTarget) -> list[str]:
    bucket = p.squeeze_bucket if p.squeeze_bucket != "NA" else NA
    if _finite(p.squeeze_score):
        bucket = f"{bucket} ({fmt_num(p.squeeze_score, 0)})"
    return [str(rank), f"{p.name} ({p.issuer_id})", p.country, p.sector,
            fmt_pct(p.weight, signed=True), fmt_usd_mm(p.notional_usd),
            f"{p.execution_ticker} ({p.line_type.value})", fmt_pct(p.pct_adtv, 1),
            bucket, fmt_num(p.alpha_z, 2, signed=True)]


def _top_positions(proposal: Proposal, side: Side) -> list[PositionTarget]:
    sel = [p for p in proposal.positions if p.side == side]
    if side == Side.LONG:
        return sorted(sel, key=lambda p: (-p.weight, p.issuer_id))[:TOP_N]
    return sorted(sel, key=lambda p: (p.weight, p.issuer_id))[:TOP_N]


def _thesis_lines(positions: list[PositionTarget], notes: dict[str, ResearchNote],
                  squeeze: dict[str, ResearchNote], fb: FactBook | None,
                  side: Side) -> list[str]:
    out: list[str] = []
    without: list[str] = []
    for p in positions:
        note = notes.get(p.issuer_id)
        sq = squeeze.get(p.issuer_id) if side == Side.SHORT else None
        if note is None and (sq is None or sq.squeeze is None):
            without.append(p.issuer_id)
            continue
        out.append(f"- **{p.name} ({p.issuer_id})**")
        if note is not None:
            out.append(f"  - Tese _({_note_label(note)})_:")
            out.append(f"    > {render_research_text(note.thesis, fb)}")
        if sq is not None and sq.squeeze is not None:
            out.append(f"  - Risco de short squeeze _({_note_label(sq)})_: "
                       f"**{sq.squeeze.verdict}** —")
            out.append(f"    > {render_research_text(sq.squeeze.rationale, fb)}")
    if without:
        out.append("- _Sem nota de pesquisa:_ " + ", ".join(without))
    return out


def _section_positions(proposal: Proposal, pack: ResearchPack | None,
                       fb: FactBook | None) -> list[str]:
    notes = _best_notes(pack)
    squeeze = _squeeze_notes(pack)
    headers = ["#", "Emissor", "País", "Setor", "Peso", "Nocional", "Linha", "% ADTV",
               "Squeeze", "Alpha z"]
    out = ["## Principais posições", ""]
    for side, title in ((Side.LONG, "Top 10 compradas (long)"),
                        (Side.SHORT, "Top 10 vendidas (short)")):
        top = _top_positions(proposal, side)
        out += [f"### {title}", ""]
        if not top:
            out += ["_Nenhuma posição._", ""]
            continue
        out += _table(headers, [_position_row(i + 1, p) for i, p in enumerate(top)]) + [""]
        out += ["Teses de pesquisa (texto citado como fornecido; números vêm do código):", ""]
        out += _thesis_lines(top, notes, squeeze, fb, side) + [""]
    return out


def _exposure_table(proposal: Proposal, group: str) -> list[str]:
    lines = [e for e in proposal.risk.exposures if e.group == group]
    if not lines:
        return []
    lines.sort(key=lambda e: (-abs(e.net) if _finite(e.net) else math.inf, e.name))
    is_pct = group != "style"

    def f(x: float | None, signed: bool = False) -> str:
        return fmt_pct(x, signed=signed) if is_pct else fmt_num(x, 3, signed=signed)

    rows = [[e.name, f(e.long), f(e.short), f(e.net, signed=True), f(e.gross),
             f"±{f(e.limit)}" if _finite(e.limit) else NA]
            for e in lines]
    return _table(["Nome", "Long", "Short", "Net", "Gross", "Limite"], rows) + [""]


def _section_exposures(proposal: Proposal) -> list[str]:
    out = ["## Exposições", ""]
    titles = [("country", "Por país (% NAV)"), ("sector", "Por setor (% NAV)"),
              ("currency", "Por moeda (% NAV)"), ("style", "Fatores de estilo (σ × NAV)")]
    any_table = False
    for group, title in titles:
        table = _exposure_table(proposal, group)
        if table:
            any_table = True
            out += [f"### {title}", ""] + table
    if not any_table:
        out += ["_Exposições por grupo não informadas na proposta._", ""]
    return out


def _section_fx(proposal: Proposal) -> list[str]:
    out = ["## Hedges cambiais sugeridos", ""]
    if not proposal.fx_hedges:
        return out + ["Nenhum hedge cambial sugerido.", ""]
    rows = [[h.currency, fmt_usd_mm(h.exposure_usd, signed=True),
             fmt_usd_mm(h.hedge_notional_usd, signed=True), h.instrument, h.rationale]
            for h in sorted(proposal.fx_hedges, key=lambda h: h.currency)]
    return out + _table(["Moeda", "Exposição", "Hedge", "Instrumento", "Racional"], rows) + [""]


def _section_trades(proposal: Proposal, cfg: FundConfig | None = None) -> list[str]:
    trades = proposal.trades
    out = ["## Ordens", ""]
    if not trades:
        return out + ["Sem ordens nesta proposta.", ""]
    nav = proposal.nav_usd
    counts = Counter(t.action.value for t in trades)
    gross = sum(abs(t.notional_usd) for t in trades)
    turnover = sum(abs(t.weight_change) for t in trades)
    costed = [t for t in trades if _finite(t.est_cost_bps)]
    cost_usd = sum(abs(t.notional_usd) * float(t.est_cost_bps) / 1e4 for t in costed)
    costed_gross = sum(abs(t.notional_usd) for t in costed)
    missing = len(trades) - len(costed)
    pct_adtv = [float(t.pct_adtv) for t in trades if _finite(t.pct_adtv)]
    days = [float(t.est_days) for t in trades if _finite(t.est_days)]
    rows = [
        ["Nº de ordens", f"{len(trades)} ("
         + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ")"],
        ["Volume bruto negociado", f"{fmt_usd_mm(gross)} ({fmt_pct(gross / nav)} do NAV)"],
        ["Turnover (Σ|Δw|)", fmt_pct(turnover)],
        ["Custo estimado", f"{fmt_usd(cost_usd)} "
         f"({fmt_bps(cost_usd / costed_gross * 1e4 if costed_gross > 0 else None)} do volume; "
         f"{fmt_pct(cost_usd / nav, 3)} do NAV)" if costed else NA],
        ["Maior % do ADTV", fmt_pct(max(pct_adtv), 1) if pct_adtv else NA],
        ["Maior prazo estimado de execução", fmt_liquidity(max(days), cfg) if days else NA],
    ]
    odd = _odd_lot_orders(trades)
    if odd is not None:
        rows.append(["Ordens na B3 com perna no fracionário (sufixo F)",
                     f"{odd[0]} de {odd[1]}"])
    picos = _pico_orders(proposal)
    if picos is not None:
        rows.append(["Ordens na BMV com perna em pico (abaixo do lote que forma preço)",
                     f"{picos[0]} de {picos[1]}"])
    rr = proposal.overrides.get("arredondamento") if isinstance(proposal.overrides, dict) \
        else None
    if isinstance(rr, dict) and rr.get("linha_maior_erro"):
        rows.append(["Maior erro do arredondamento a ações inteiras",
                     f"{fmt_pct(rr.get('maior_erro_pct_nav'), 3, signed=True)} do NAV "
                     f"({rr['linha_maior_erro']}); soma "
                     f"{fmt_pct(rr.get('soma_erros_pct_nav'), 3)}"])
        if rr.get("sem_uma_acao"):
            rows.append(["Posições abaixo de uma ação (sem ordem)",
                         ", ".join(map(str, rr["sem_uma_acao"]))])
    out += _table(["Item", "Valor"], rows) + [""]
    if missing:
        out += [f"_{missing} ordem(ns) sem estimativa de custo — excluídas da soma de custos "
                "(não tratadas como custo zero)._", ""]
    return out


def _pico_orders(proposal: Proposal) -> tuple[int, int] | None:
    """(ordens com perna em pico, ordens em linhas da BMV); ``None`` sem ordem na BMV."""
    from ..portfolio.trades import order_legs_detail
    from ..universe import listing_market

    px = {p.execution_ticker: p.price_local for p in proposal.positions}
    eligible = [t for t in proposal.trades if listing_market(t.ticker) == "MX"]
    if not eligible:
        return None
    n = sum(1 for t in eligible if t.shares and any(
        kind == "pico" for _tk, _q, kind in order_legs_detail(t.ticker, int(t.shares),
                                                               px.get(t.ticker))))
    return n, len(eligible)


def _liquidity_rows(r, cfg: FundConfig) -> list[list[str]]:
    """Liquidez da carteira na unidade do mandato (fechamentos com a execução no leilão de
    fechamento; dias a uma participação do ADTV na regra anterior)."""
    liq = cfg.liquidity
    if liquidity_unit(cfg) == "fechamentos":
        return [["Máx. fechamentos para liquidar", fmt_closes(r.max_days_to_liquidate),
                 f"long ≤ {fmt_closes(liq.max_days_to_liquidate_long)}; short ≤ "
                 f"{fmt_closes(liq.max_days_to_liquidate_short)}"],
                ["% do gross liquidável em 1 fechamento", fmt_pct(r.pct_nav_liquidated_1d),
                 "capacidade estrutural do leilão e da janela pré-fechamento"]]
    return [["Máx. dias para liquidar", fmt_days(r.max_days_to_liquidate),
             f"long ≤ {fmt_days(liq.max_days_to_liquidate_long)}; short ≤ "
             f"{fmt_days(liq.max_days_to_liquidate_short)}"],
            ["% NAV liquidável em 1 dia", fmt_pct(r.pct_nav_liquidated_1d),
             f"participação {fmt_pct(liq.participation_rate, 0)} do ADTV"]]


def _odd_lot_orders(trades: list[Trade]) -> tuple[int, int] | None:
    """(ordens com perna no mercado fracionário, ordens em linhas com fracionário); ``None`` sem
    ordem em mercado com livro fracionário (B3)."""
    from ..portfolio.trades import odd_lot_ticker, order_legs

    eligible = [t for t in trades if odd_lot_ticker(t.ticker) is not None]
    if not eligible:
        return None
    n = sum(1 for t in eligible if t.shares
            and any(tk != t.ticker for tk, _ in order_legs(t.ticker, int(t.shares))))
    return n, len(eligible)


def _section_research(pack: ResearchPack | None, fb: FactBook | None) -> list[str]:
    out = ["## Pesquisa e visões", ""]
    if pack is None:
        return out + ["_Pacote de pesquisa não disponível para este memo._", ""]
    n_ai = sum(1 for n in pack.notes if not _is_pm_note(n))
    out += [f"Provedor: {_inline(pack.provider)}; {len(pack.notes)} nota(s) por emissor "
            f"({n_ai} geradas por IA), {len(pack.macro)} nota(s) macro, "
            f"{len(pack.views)} visão(ões).", ""]
    if pack.news:
        out += [f"{len(pack.news)} manchete(s) considerada(s) — conteúdo NÃO confiável, não "
                "reproduzido neste memo.", ""]
    if pack.macro:
        out += ["### Notas macro", ""]
        for m in sorted(pack.macro, key=lambda m: (m.scope, m.note_id)):
            out += [f"#### {_inline(m.scope)} — regime: {render_research_text(m.regime, fb)} "
                    f"(viés {m.stance:+d})", f"_({_macro_label(m)})_", "",
                    f"> {render_research_text(m.summary, fb)}", ""]
            for title, items in (("Riscos", m.risks),
                                 ("Implicações para a carteira", m.portfolio_implications)):
                if items:
                    out += [f"{title}:"] + [f"- {render_research_text(i, fb)}" for i in items]
                    out += [""]
            if m.key_events:
                out += ["Eventos:"] + [
                    f"- {render_research_text(e.description, fb)} "
                    f"({fmt_date(e.expected_date) if e.expected_date else 'data n/d'}; "
                    f"{e.direction})" for e in m.key_events] + [""]
    if pack.views:
        rows = []
        for v in sorted(pack.views, key=lambda v: (v.issuer_id, v.source.value, v.author)):
            limits = [s for s, on in (("sem short", v.no_short), ("sem long", v.no_long)) if on]
            if _finite(v.max_abs_weight):
                limits.append(f"|w| ≤ {fmt_pct(v.max_abs_weight)}")
            origin = "Gestor (PM)" if v.source == ViewSource.PM else "IA"
            rows.append([v.issuer_id, origin, f"{v.score:+d}" if v.score else "0",
                         fmt_pct(v.confidence, 0),
                         ", ".join(limits) or "—", _inline(v.author)])
        out += ["### Visões aplicadas", ""]
        out += _table(["Emissor", "Origem", "Score", "Confiança", "Restrições", "Autor"], rows)
        out += [""]
    return out


def _section_optimizer(proposal: Proposal) -> list[str]:
    o = proposal.optimizer
    rows = [
        ["Status / solver", f"{o.status} / {o.solver}"],
        ["Tempo de solução", f"{fmt_num(o.solve_seconds, 2)} s"],
        ["Alpha esperado (a.a.)", fmt_pct(o.expected_alpha_annual)],
        ["Custo esperado (a.a.)", fmt_pct(o.expected_cost_annual)],
        ["Candidatos", str(o.n_candidates)],
        ["Excluídos", ", ".join(f"{k}: {v}" for k, v in sorted(o.n_excluded.items())) or "—"],
        ["Restrições ativas", ", ".join(o.binding_constraints) or "—"],
    ]
    out = ["## Otimizador", ""] + _table(["Item", "Valor"], rows) + [""]
    if o.notes:
        out += ["Observações do otimizador:"] + [f"- {n}" for n in o.notes] + [""]
    return out


def _section_checklist(proposal: Proposal, pack: ResearchPack | None,
                       cfg: FundConfig) -> list[str]:
    items: list[str] = []
    hard = proposal.hard_failures
    if hard:
        items.append("**Proposta BLOQUEADA** — falhas HARD: "
                     + ", ".join(f"`{c.check_id}`" for c in hard)
                     + ". Não é aprovável; corrigir e gerar nova versão.")
    soft = proposal.soft_failures
    if soft:
        items.append("Dar ciência explícita às falhas SOFT: "
                     + ", ".join(f"`{c.check_id}` ({c.name})" for c in soft) + ".")
    vol_status = _vol_status(proposal.risk.ex_ante_vol, cfg)
    if vol_status != "dentro da banda":
        items.append(f"Avaliar vol ex-ante ({fmt_pct(proposal.risk.ex_ante_vol)}) — {vol_status}.")
    risky = [p for p in proposal.positions
             if p.side == Side.SHORT and p.squeeze_bucket in ("MEDIUM", "HIGH")]
    if risky:
        items.append("Validar shorts com risco de squeeze MEDIUM/HIGH: "
                     + ", ".join(f"{p.issuer_id} ({p.squeeze_bucket})" for p in risky) + ".")
    n_short = sum(1 for p in proposal.positions if p.side == Side.SHORT)
    if n_short:
        items.append(f"Confirmar locate/disponibilidade de aluguel para os {n_short} shorts "
                     "antes da execução.")
    if pack is not None:
        n_ai = sum(1 for n in pack.notes if not _is_pm_note(n))
        if n_ai:
            items.append(f"Revisar as {n_ai} nota(s) geradas por IA (citadas como fornecidas).")
        n_restr = sum(1 for v in pack.views if v.source == ViewSource.AI
                      and (v.no_short or v.no_long or v.max_abs_weight is not None))
        if n_restr:
            items.append(f"Validar {n_restr} restrição(ões) propostas por IA "
                         "(sem short / sem long / teto de peso).")
    if proposal.fx_hedges:
        items.append("Decidir sobre os hedges cambiais sugeridos: "
                     + ", ".join(sorted(h.currency for h in proposal.fx_hedges)) + ".")
    if proposal.optimizer.notes:
        items.append("Revisar observações/relaxamentos do otimizador.")
    if not hard:
        co_sign = co_sign_reasons(proposal)
        if co_sign:
            items.append("Obter co-assinatura independente de Risco/Compliance (quatro olhos): "
                         + " ".join(co_sign))
    items.append("Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes de "
                 "snapshot, configuração, pesquisa e proposta.")
    return ["## Decisões pendentes do gestor", ""] + [f"- [ ] {i}" for i in items] + [""]


def render_memo(proposal: Proposal, pack: ResearchPack | None = None,
                factbook: FactBook | None = None, *, config: FundConfig | None = None,
                state: ProposalState | None = None, audit_head_hash: str | None = None) -> str:
    """Renderiza o memo Markdown (pt-BR) da proposta para o gestor.

    ``config`` fornece nome do fundo, meta e limites exibidos como referência (padrão: valores
    default do mandato). ``state`` permite informar o estado derivado do livro; sem ele, o
    estado é ``BLOCKED`` se houver falha HARD e ``IN_REVIEW`` caso contrário.
    ``audit_head_hash`` (topo da trilha de auditoria) é impresso no rodapé quando informado.
    """
    cfg = config or FundConfig()
    synthetic = _is_synthetic(proposal, pack, factbook)
    st = state or _derived_state(proposal)
    parts: list[str] = []
    parts += _section_header(proposal, cfg, st, synthetic)
    parts += _section_risk(proposal, cfg)
    parts += _section_compliance(proposal)
    parts += _section_positions(proposal, pack, factbook)
    parts += _section_exposures(proposal)
    parts += _section_fx(proposal)
    parts += _section_trades(proposal, cfg)
    parts += _section_research(pack, factbook)
    parts += _section_optimizer(proposal)
    parts += _section_checklist(proposal, pack, cfg)
    footer = ("_Todos os números deste memo foram calculados e formatados por código a partir da "
              "proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._")
    parts += ["---", "", footer]
    if audit_head_hash:
        parts += ["", f"_Topo da trilha de auditoria na geração: `{audit_head_hash}`_"]
    if synthetic:
        parts += ["", f"**{SIMULATED_DATA_NOTICE}**"]
    return "\n".join(parts).rstrip() + "\n"
