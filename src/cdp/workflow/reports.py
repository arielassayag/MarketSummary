"""Relatórios do CDP — Cabra da Peste (diário e semanal) em Markdown e HTML autocontido.

Regras:

- Todos os números são formatados por código a partir dos registros/propostas (``fmt_*``);
  textos de IA (comentário, racional, teses) aparecem rotulados como **IA** e, no HTML, são
  sempre escapados (nenhum ``<script>``/HTML vindo de modelo é interpretado).
- HTML autocontido: CSS inline e gráficos SVG inline (NAV e drawdown desde o início); nenhum
  recurso externo, nenhum script.
- Cabeçalho com o rótulo "paper trading com preços reais" e o aviso de dados ("DADOS SIMULADOS"
  quando sintético); rodapé de integridade com os hashes do registro/decisão.
- Dados ausentes aparecem como ``n/d`` — nunca como zero.
- :func:`write_report_files` grava ``relatorio.md``/``relatorio.html`` de forma exclusiva
  (nunca sobrescreve) e devolve caminhos e SHA-256.
"""

from __future__ import annotations

import html
import math
import os
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .. import SIMULATED_DATA_NOTICE
from ..config import FundConfig
from ..contracts import (
    AUTONOMOUS_DECIDER,
    DailyRecord,
    Decision,
    DecisionMode,
    FactBook,
    PositionTarget,
    Proposal,
    Severity,
    Side,
    View,
    ViewSource,
)
from ..hashing import sha256_file
from ..research.commentary import format_bps, format_money, period_returns
from ..research.guardrails import PLACEHOLDER_RE, render_placeholders
from ..research.pm_agent import POSTURE_PT, REGIME_PT, PMDecisionOutput, _default_config
from .memo import NA, fmt_date, fmt_num, fmt_pct

PAPER_TRADING_LABEL = "paper trading com preços reais"
PAPER_TRADING_TEXT = ("Natureza: paper trading com preços reais — execução hipotética no "
                      "fechamento (MOC) com custos do modelo; não representa resultado de fundo "
                      "real nem oferta de investimento.")
AI_LABEL = "IA"
REPORT_STEM = "relatorio"
TOP_N = 10
AI_CELL_CHARS = 220
_COMPONENT_ORDER = ("equity", "factor", "specific", "costs", "borrow", "financing")
_COMPONENT_PT = {"equity": "Ações (total)", "factor": "Fatorial", "specific": "Específico (alpha)",
                 "costs": "Custos", "borrow": "Aluguel", "financing": "Financiamento"}
_GROUP_PT = {"factor_group": "Grupos de fatores", "country": "País", "sector": "Setor",
             "side": "Long × short"}
_STAGE_LABEL = {"normal": "normal", "soft_stop": "stop suave", "hard_stop": "stop duro",
                "stop_out": "stop-out"}
_SPARK = "▁▂▃▄▅▆▇█"
_STEM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}")
GENESIS_RECORD_HASH = "0" * 64
"""Elo do primeiro registro diário (mesmo valor de ``audit.GENESIS_HASH``)."""


# ==========================================================
# Modelo de documento (fonte única para MD e HTML)
# ==========================================================

@dataclass
class Block:
    kind: str  # p | table | list | kpis | svg | md | kv
    data: Any
    ai: bool = False
    caption: str = ""


@dataclass
class Section:
    title: str
    blocks: list[Block] = field(default_factory=list)
    ai: bool = False

    def p(self, text: str, ai: bool = False) -> None:
        self.blocks.append(Block("p", text, ai))

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[str]], caption: str = "",
              ai: bool = False) -> None:
        self.blocks.append(Block("table", (list(headers), [list(r) for r in rows]), ai, caption))

    def items(self, values: Sequence[str], ai: bool = False, caption: str = "") -> None:
        self.blocks.append(Block("list", list(values), ai, caption))

    def kv(self, rows: Sequence[tuple[str, str]], caption: str = "") -> None:
        self.blocks.append(Block("kv", list(rows), False, caption))


@dataclass
class Document:
    title: str
    subtitle: str
    labels: list[str]
    synthetic: bool
    data_notice: str
    sections: list[Section]
    kpis: list[tuple[str, str, str]] = field(default_factory=list)


# ==========================================================
# Utilidades
# ==========================================================

def _finite(x: object) -> bool:
    try:
        return x is not None and not isinstance(x, bool) and math.isfinite(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _f(x: object) -> float | None:
    return float(x) if _finite(x) else None  # type: ignore[arg-type]


def _pct(x: object, signed: bool = False, digits: int = 2) -> str:
    return fmt_pct(_f(x), digits, signed)


def _usd(x: object, signed: bool = False) -> str:
    return format_money(_f(x), signed)


def _bps(fraction: object) -> str:
    return format_bps(_f(fraction))


def _mult(x: object) -> str:
    v = _f(x)
    return NA if v is None else f"{fmt_num(v, 2)}x"


def _short(h: str | None, n: int = 16) -> str:
    return f"{h[:n]}…" if h else NA


def _truncate(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: max(0, n - 1)].rstrip() + "…"


def _ai_text(text: str | None, factbook: FactBook | None) -> str:
    """Texto de IA para exibição: placeholders resolvidos (ou marcados) e espaços normalizados."""
    if not text:
        return NA
    if factbook is not None:
        text = render_placeholders(text, factbook)
    text = PLACEHOLDER_RE.sub(lambda m: f"[fato não resolvido: {m.group(1)}]", text)
    return " ".join(text.split())


def _vol_status(vol: float | None, cfg: FundConfig) -> str:
    if vol is None:
        return NA
    rk = cfg.risk
    if vol < rk.vol_band_min:
        return "abaixo da banda"
    if vol > rk.vol_band_max:
        return "acima da banda"
    return "dentro da banda"


def _band(cfg: FundConfig) -> str:
    return f"{fmt_pct(cfg.risk.vol_band_min)} a {fmt_pct(cfg.risk.vol_band_max)}"


def _stage(drawdown: float | None, cfg: FundConfig) -> str:
    if drawdown is None:
        return NA
    d = cfg.drawdown
    key = ("stop_out" if drawdown <= d.stop_out else "hard_stop" if drawdown <= d.hard_stop
           else "soft_stop" if drawdown <= d.soft_stop else "normal")
    return _STAGE_LABEL[key]


def _chain(record: DailyRecord, history: Iterable[DailyRecord]) -> list[DailyRecord]:
    by_date = {r.date: r for r in history if r.date < record.date}
    by_date[record.date] = record
    return [by_date[d] for d in sorted(by_date)]


def verify_record_chain(chain: Sequence[DailyRecord]) -> tuple[bool, list[str]]:
    """Recalcula ``record_hash`` de cada registro e confere os elos ``prev_record_hash``.

    ``chain`` em ordem de data (o último é o registro do relatório). O primeiro elo só é
    conferido contra GENESIS quando o histórico começa na inception (``prev`` = GENESIS);
    histórico parcial é verificado a partir do primeiro registro informado.
    """
    problems: list[str] = []
    for i, r in enumerate(chain):
        if not r.record_hash:
            problems.append(f"{r.date.isoformat()}: registro sem record_hash")
        elif r.compute_hash() != r.record_hash:
            problems.append(f"{r.date.isoformat()}: conteúdo adulterado (record_hash não confere)")
        if i > 0 and r.prev_record_hash != chain[i - 1].record_hash:
            problems.append(f"{r.date.isoformat()}: elo quebrado (prev_record_hash não é o hash "
                            f"de {chain[i - 1].date.isoformat()})")
    return not problems, problems


def _decision_problems(decision: Decision, proposal: Proposal) -> list[str]:
    """Reverifica a decisão contra a proposta exibida (hashes recalculados, signatário, gates)."""
    from .approval import verify_decision
    from .autonomy import verify_autonomous_decision

    try:
        if decision.mode == DecisionMode.AUTONOMOUS:
            ok, reasons = verify_autonomous_decision(decision, proposal, proposal.snapshot_hash,
                                                     proposal.config_hash,
                                                     proposal.research_hash)
        else:
            ok, reasons = verify_decision(decision, proposal, proposal.snapshot_hash,
                                          proposal.config_hash, proposal.research_hash)
    except Exception as exc:  # noqa: BLE001 - relatório nunca derruba; a falha é exibida
        return [f"verificação indisponível ({type(exc).__name__})"]
    return [] if ok else list(reasons)


# ==========================================================
# Gráficos (SVG inline e sparkline unicode)
# ==========================================================

def sparkline_svg(values: Sequence[float | None], dates: Sequence[date], *, title: str,
                  fmt: Callable[[float], str], area_to_zero: bool = False,
                  width: int = 640, height: int = 120) -> str:
    """Gráfico de linha SVG autocontido (sem script); pontos ausentes interrompem a linha."""
    pts = [(i, float(v)) for i, v in enumerate(values) if _finite(v)]
    label = html.escape(title, quote=True)
    if not pts:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
                f'role="img" aria-label="{label}"><text x="8" y="{height // 2}" '
                f'class="muted">sem dados</text></svg>')
    left, right, top, bottom = 8, 8, 20, 22
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if area_to_zero:
        hi = max(hi, 0.0)
    span = hi - lo if hi > lo else 1.0
    n = max(len(values) - 1, 1)
    plot_w, plot_h = width - left - right, height - top - bottom

    def xy(i: int, v: float) -> tuple[float, float]:
        x = left + (i / n) * plot_w if len(values) > 1 else left + plot_w / 2
        y = top + (hi - v) / span * plot_h if hi > lo else top + plot_h / 2
        return x, y

    segments: list[list[tuple[float, float]]] = [[]]
    for i, v in enumerate(values):
        if _finite(v):
            segments[-1].append(xy(i, float(v)))  # type: ignore[arg-type]
        elif segments[-1]:
            segments.append([])
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'class="spark" role="img" aria-label="{label}"><title>{label}</title>']
    for seg in (s for s in segments if s):
        coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
        if area_to_zero:
            base = xy(0, 0.0)[1]
            poly = (f"{seg[0][0]:.1f},{base:.1f} " + coords + f" {seg[-1][0]:.1f},{base:.1f}")
            parts.append(f'<polygon points="{poly}" class="area"/>')
        if len(seg) == 1:
            parts.append(f'<circle cx="{seg[0][0]:.1f}" cy="{seg[0][1]:.1f}" r="2.5" '
                         'class="line-dot"/>')
        else:
            parts.append(f'<polyline points="{coords}" class="line" fill="none"/>')
    first = html.escape(fmt_date(dates[0])) if dates else ""
    last = html.escape(fmt_date(dates[-1])) if dates else ""
    parts.append(f'<text x="{left}" y="{height - 6}" class="axis">{first}</text>')
    parts.append(f'<text x="{width - right}" y="{height - 6}" class="axis" '
                 f'text-anchor="end">{last}</text>')
    parts.append(f'<text x="{left}" y="13" class="axis">máx. {html.escape(fmt(hi))} · mín. '
                 f'{html.escape(fmt(lo))} · último {html.escape(fmt(vals[-1]))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def sparkline_text(values: Sequence[float | None]) -> str:
    vals = [float(v) for v in values if _finite(v)]  # type: ignore[arg-type]
    if not vals:
        return NA
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _SPARK[3] * len(vals)
    return "".join(_SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))] for v in vals)


# ==========================================================
# Renderização Markdown
# ==========================================================

def _defuse_links(text: str) -> str:
    """Desarma links/imagens Markdown (``[x](url)``, ``![x](url)``): nada é carregado/clicável."""
    return text.replace("](", "]\\(")


def _md_cell(text: object) -> str:
    return _defuse_links(" ".join(str(text).split()).replace("|", "\\|").replace("<", "&lt;"))


def _md_safe(text: str) -> str:
    """Texto de IA em Markdown: sem HTML interpretável (``<`` escapado; ``>`` é citação) e sem
    links/imagens ativos."""
    return _defuse_links(text.replace("<", "&lt;"))


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(_md_cell(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_md_cell(c) for c in r) + " |" for r in rows]
    return out


def _notice_tail(notice: str) -> str:
    """Aviso sem repetir "DADOS SIMULADOS" (o banner já o exibe)."""
    tail = re.sub(rf"^\s*{re.escape(SIMULATED_DATA_NOTICE)}\s*[—–:-]?\s*", "", notice or "",
                  flags=re.IGNORECASE).strip()
    return tail or "dados sintéticos gerados por código; não representam preços reais."


def to_markdown(doc: Document) -> str:
    L = [f"# {doc.title}", "", f"_{doc.subtitle}_", ""]
    if doc.synthetic:
        L += [f"> **{SIMULATED_DATA_NOTICE}** — {_notice_tail(doc.data_notice)}", ""]
    L += [f"- {x}" for x in doc.labels] + [""]
    if doc.kpis:
        L += _md_table(["Indicador", "Valor", "Referência"], [list(k) for k in doc.kpis]) + [""]
    for s in doc.sections:
        L += [f"## {s.title}" + (f" [{AI_LABEL}]" if s.ai else ""), ""]
        for b in s.blocks:
            tag = f"**[{AI_LABEL}]** " if b.ai else ""
            if b.caption:
                L += [f"**{b.caption}**" + (f" [{AI_LABEL}]" if b.ai else ""), ""]
            if b.kind == "p":
                text = _md_safe(b.data) if b.ai else b.data
                L += [f"{tag}{text}", ""]
            elif b.kind == "md":
                L += [_md_safe(b.data).strip(), ""]
            elif b.kind == "table":
                headers, rows = b.data
                L += _md_table(headers, rows) + [""] if rows else ["(sem linhas)", ""]
            elif b.kind == "kv":
                L += _md_table(["Item", "Valor"], [list(r) for r in b.data]) + [""]
            elif b.kind == "list":
                items = [(_md_safe(x) if b.ai else x) for x in b.data]
                L += ([f"- {tag}{x}" for x in items] or ["- (nenhum)"]) + [""]
            elif b.kind == "svg":
                L += [f"`{b.data['text']}` — {b.data['summary']}", ""]
    return "\n".join(L).rstrip() + "\n"


# ==========================================================
# Renderização HTML (autocontida, sem scripts)
# ==========================================================

_CSS = """
:root{--bg:#ffffff;--fg:#1d2433;--muted:#5b6475;--line:#d9dee7;--card:#f6f8fb;
--accent:#1f5fa8;--neg:#b42318;--pos:#067647;--warn:#9a6700;--ia:#6941c6;--area:rgba(180,35,24,.15)}
@media (prefers-color-scheme: dark){:root{--bg:#11151c;--fg:#e6e9ef;--muted:#9aa3b2;
--line:#2a3140;--card:#181e28;--accent:#7cb3ff;--neg:#ff8a80;--pos:#6fdc9a;--warn:#f5c86b;
--ia:#b69cff;--area:rgba(255,138,128,.18)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:32px 0 10px;
border-bottom:1px solid var(--line);padding-bottom:4px}.sub{color:var(--muted);margin:0 0 12px}
.banner{background:var(--warn);color:#111;font-weight:700;padding:8px 12px;border-radius:6px;
margin:12px 0}.labels{color:var(--muted);padding-left:18px}.badge{display:inline-block;
font-size:.72rem;font-weight:700;padding:1px 6px;border-radius:10px;margin-right:6px;
vertical-align:middle}.badge.ia{background:var(--ia);color:#fff}
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;
margin:16px 0}.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:10px 12px}.kpi .k{font-size:.78rem;color:var(--muted)}.kpi .v{font-size:1.2rem;
font-weight:700;font-variant-numeric:tabular-nums}.kpi .r{font-size:.75rem;color:var(--muted)}
.tbl{overflow-x:auto;margin:8px 0 16px}table{border-collapse:collapse;width:100%;
font-size:.86rem;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid var(--line);
padding:5px 8px;text-align:left;vertical-align:top}th{background:var(--card);font-weight:600}
td.num{text-align:right;white-space:nowrap}caption{caption-side:top;text-align:left;
font-weight:600;padding:4px 0}.ai{border-left:3px solid var(--ia);padding-left:10px}
.spark{width:100%;height:auto;max-height:160px}.spark .line{stroke:var(--accent);stroke-width:2}
.spark .area{fill:var(--area)}.spark .line-dot{fill:var(--accent)}.spark .axis,.muted{
fill:var(--muted);font-size:11px}.chart{background:var(--card);border:1px solid var(--line);
border-radius:8px;padding:8px;margin:8px 0}footer{margin-top:40px;color:var(--muted);
font-size:.8rem}code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;
word-break:break-all}
"""
_NUM_RE = re.compile(r"^[\s+\-−]?(USD\s)?[+\-−]?[\d.,]+\s?(%|x|mm|bps|d)?$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITAL_RE = re.compile(r"(?<![\w*])_(.+?)_(?![\w*])")


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _inline_md(text: str) -> str:
    """Markdown inline mínimo sobre texto JÁ escapado (negrito e itálico)."""
    return _ITAL_RE.sub(r"<em>\1</em>", _BOLD_RE.sub(r"<strong>\1</strong>", text))


def md_to_safe_html(md: str) -> str:
    """Converte Markdown simples (parágrafos, listas, citações, títulos, negrito/itálico) em HTML
    escapando TODO o conteúdo antes — nenhum HTML do texto de origem é interpretado."""
    out: list[str] = []
    para: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if para:
            out.append("<p>" + _inline_md(_esc(" ".join(para))) + "</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline_md(_esc(i))}</li>" for i in items)
                       + "</ul>")
            items.clear()

    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith(("- ", "* ")):
            if para:
                flush()
            items.append(line[2:])
            continue
        if items:
            flush()
        if line.startswith(">"):
            flush()
            out.append("<blockquote>" + _inline_md(_esc(line.lstrip("> ").strip()))
                       + "</blockquote>")
        elif line.startswith("#"):
            flush()
            out.append("<h4>" + _inline_md(_esc(line.lstrip("#").strip())) + "</h4>")
        else:
            para.append(line)
    flush()
    return "\n".join(out)


def _td(cell: str) -> str:
    cls = ' class="num"' if _NUM_RE.match(cell or "") else ""
    return f"<td{cls}>{_esc(cell)}</td>"


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[str]], caption: str = "",
                badge: str = "") -> str:
    cap = f"<caption>{badge}{_esc(caption)}</caption>" if caption else ""
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(_td(str(c)) for c in r) + "</tr>" for r in rows)
    if not rows:
        body = f'<tr><td colspan="{len(headers)}">(sem linhas)</td></tr>'
    return f'<div class="tbl"><table>{cap}<thead><tr>{head}</tr></thead><tbody>{body}' \
           f"</tbody></table></div>"


def to_html(doc: Document) -> str:
    badge = f'<span class="badge ia">{AI_LABEL}</span>'
    H = ["<!doctype html>", '<html lang="pt-BR"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f"<title>{_esc(doc.title)}</title><style>{_CSS}</style></head><body><main>",
         f"<h1>{_esc(doc.title)}</h1>", f'<p class="sub">{_esc(doc.subtitle)}</p>']
    if doc.synthetic:
        H.append(f'<div class="banner">{_esc(SIMULATED_DATA_NOTICE)} — '
                 f'{_esc(_notice_tail(doc.data_notice))}</div>')
    H.append('<ul class="labels">' + "".join(f"<li>{_esc(x)}</li>" for x in doc.labels)
             + "</ul>")
    if doc.kpis:
        H.append('<div class="kpis">' + "".join(
            f'<div class="kpi"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div>'
            f'<div class="r">{_esc(r)}</div></div>' for k, v, r in doc.kpis) + "</div>")
    for s in doc.sections:
        H.append(f"<section><h2>{badge if s.ai else ''}{_esc(s.title)}</h2>")
        for b in s.blocks:
            bb = badge if b.ai else ""
            if b.kind == "p":
                cls = ' class="ai"' if b.ai else ""
                cap = f"<strong>{_esc(b.caption)}</strong><br>" if b.caption else ""
                H.append(f"<p{cls}>{bb}{cap}{_esc(b.data)}</p>")
            elif b.kind == "md":
                cap = f"<p><strong>{bb}{_esc(b.caption)}</strong></p>" if b.caption else ""
                H.append(f'{cap}<div class="ai">{md_to_safe_html(b.data)}</div>')
            elif b.kind == "table":
                headers, rows = b.data
                H.append(_html_table(headers, rows, b.caption, bb))
            elif b.kind == "kv":
                H.append(_html_table(["Item", "Valor"], b.data, b.caption))
            elif b.kind == "list":
                cap = f"<p><strong>{bb}{_esc(b.caption)}</strong></p>" if b.caption else ""
                lis = "".join(f"<li>{bb if not b.caption else ''}{_esc(x)}</li>" for x in b.data)
                H.append(f"{cap}<ul>{lis or '<li>(nenhum)</li>'}</ul>")
            elif b.kind == "svg":
                cap = f"<p><strong>{_esc(b.caption)}</strong></p>" if b.caption else ""
                H.append(f'{cap}<div class="chart">{b.data["svg"]}</div>')
        H.append("</section>")
    H.append(f"<footer>{_esc(PAPER_TRADING_TEXT)} Números calculados por código; textos "
             f"rotulados {AI_LABEL} foram escritos pela mente do CDP e verificados por "
             "guardrails.</footer></main></body></html>")
    return "\n".join(H) + "\n"


# ==========================================================
# Relatório diário
# ==========================================================

def _attr_rows(lines: Iterable[Any], nav0: float) -> list[list[str]]:
    rows = sorted(lines, key=lambda a: (-abs(a.pnl_usd), a.name))
    return [[str(a.name), _usd(a.pnl_usd, signed=True), _bps(a.contribution)] for a in rows]


def _issuer_pnl(record: DailyRecord) -> dict[str, float]:
    lines = [a for a in record.attribution if a.group == "issuer"]
    if lines:
        return {a.name: float(a.pnl_usd) for a in lines}
    out: dict[str, float] = {}
    for p in record.positions:
        out[p.issuer_id] = out.get(p.issuer_id, 0.0) + float(p.day_pnl_usd)
    return out


def render_daily_report(record: DailyRecord, history: list[DailyRecord], commentary_md: str,
                        fund_name: str, *, cfg: FundConfig | None = None,
                        squeeze_buckets: Mapping[str, str] | None = None,
                        idio: Mapping[str, Any] | None = None) -> tuple[str, str]:
    """Relatório diário (Markdown, HTML): KPIs, comentário, atribuição, posições, alertas,
    evolução do NAV/drawdown desde o início e rodapé de integridade.

    ``idio``: fatia idiossincrática por três medidas (bloco de
    :func:`cdp.workflow.risk_monitor.idio_monitor`), exibida como indicador quando presente.

    O rodapé recalcula o ``record_hash`` de cada registro e confere os elos da cadeia; registro
    adulterado ou cadeia quebrada aparecem em destaque (nunca como "íntegro"). ``cfg`` ausente ⇒
    mandato do repositório. Comentário com procedência ``[IA]`` é rotulado IA.
    """
    cfg = cfg or _default_config()
    rk = record.risk
    nav0 = float(record.nav_start_usd)
    periods = period_returns(record, history)
    chain = _chain(record, history)
    synthetic = record.is_synthetic
    notice = record.data_notice or ("dados reais de mercado" if not synthetic else "")
    chain_ok, chain_problems = verify_record_chain(chain)
    labels = [f"Track record: {record.track_record_type}", PAPER_TRADING_TEXT,
              f"Aviso de dados: {notice or NA}"]
    if not chain_ok:
        labels.insert(0, "ALERTA DE INTEGRIDADE: cadeia de hashes do track record NÃO CONFERE ("
                      + "; ".join(chain_problems[:3]) + ")")
    vol = _f(rk.ex_ante_vol)
    kpis = [
        ("NAV", format_money(record.nav_end_usd), f"abertura {format_money(nav0)}"),
        ("Retorno do dia", _pct(record.ret, signed=True), f"P&L {_usd(record.pnl_usd, True)}"),
        ("Retorno no mês", _pct(periods["mtd"], signed=True), "composto (MTD)"),
        ("Retorno no ano", _pct(periods["ytd"], signed=True), "composto (YTD)"),
        ("Desde o início", _pct(periods["itd"], signed=True),
         f"desde {fmt_date(periods['first_date'])}"),
        ("P&L do dia", _usd(record.pnl_usd, signed=True), "USD"),
        ("Vol ex-ante", _pct(vol), f"banda {_band(cfg)} · {_vol_status(vol, cfg)}"),
        ("Beta", fmt_num(_f(rk.beta), 2, signed=True), f"limite ±{fmt_num(cfg.risk.beta_max_abs)}"),
        ("Gross / net", f"{_pct(rk.gross)} / {_pct(rk.net, signed=True)}",
         f"{rk.n_long} long · {rk.n_short} short"),
        ("VaR 1d (99%)", _pct(rk.var_1d_99), f"limite {fmt_pct(cfg.risk.var_1d_max)}"),
        ("Drawdown", _pct(rk.drawdown), f"escada: {_stage(_f(rk.drawdown), cfg)}"),
        ("Vol realizada 21d", _pct(rk.realized_vol_21d), "anualizada"),
    ]
    if idio:
        kpis.append(("Fatia idiossincrática", _pct(idio.get("ex_ante"), digits=1),
                     f"ex-ante · realizada 63d {_pct(idio.get('realizada_63d'), digits=1)} · "
                     f"sem modelo {_pct(idio.get('sem_modelo_63d'), digits=1)}"))
    sections: list[Section] = []

    ai_comment = f"[{AI_LABEL}]" in (commentary_md or "")
    s = Section("Comentário do dia", ai=ai_comment)
    s.blocks.append(Block("md", commentary_md or "Comentário indisponível.", ai=ai_comment))
    sections.append(s)

    s = Section("Atribuição")
    comp = record.pnl_components
    comp_rows = [[_COMPONENT_PT.get(k, k), _usd(comp[k], signed=True), _bps(comp[k] / nav0)]
                 for k in [*_COMPONENT_ORDER, *sorted(set(comp) - set(_COMPONENT_ORDER))]
                 if k in comp]
    s.table(["Componente", "P&L", "Contribuição"], comp_rows, caption="Componentes do P&L")
    for group in ("factor_group", "country", "sector", "side"):
        lines = [a for a in record.attribution if a.group == group]
        s.table([_GROUP_PT[group], "P&L", "Contribuição"], _attr_rows(lines, nav0),
                caption=_GROUP_PT[group])
    pnl = _issuer_pnl(record)
    winners = sorted(((k, v) for k, v in pnl.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))
    losers = sorted(((k, v) for k, v in pnl.items() if v < 0), key=lambda kv: (kv[1], kv[0]))
    s.table(["Emissor", "P&L", "Contribuição"],
            [[k, _usd(v, True), _bps(v / nav0)] for k, v in winners[:5]],
            caption="Cinco maiores contribuidores")
    s.table(["Emissor", "P&L", "Contribuição"],
            [[k, _usd(v, True), _bps(v / nav0)] for k, v in losers[:5]],
            caption="Cinco maiores detratores")
    sections.append(s)

    s = Section("Posições")
    buckets = dict(squeeze_buckets or {})
    rows = []
    for p in sorted(record.positions, key=lambda p: (-abs(p.weight), p.issuer_id, p.ticker)):
        rows.append([p.issuer_id, p.ticker, p.side.value, _pct(p.weight, signed=True),
                     _usd(p.market_value_usd, signed=True), _usd(p.day_pnl_usd, signed=True),
                     _pct(p.day_return_usd, signed=True), buckets.get(p.issuer_id, NA),
                     "sim" if p.repriced else "não (sem negociação)"])
    s.table(["Emissor", "Ticker", "Lado", "Peso", "Valor de mercado", "P&L do dia",
             "Retorno do dia", "Squeeze", "Reprecificada"], rows,
            caption=f"{len(rows)} linhas, ordenadas por |peso|")
    sections.append(s)

    s = Section("Alertas de risco")
    integrity_alerts = [f"Integridade: {p}" for p in chain_problems]
    s.items(integrity_alerts + list(record.alerts) or ["Nenhum alerta no dia."])
    sections.append(s)

    s = Section("Evolução desde o início")
    dates = [r.date for r in chain]
    navs = [r.nav_end_usd for r in chain]
    dds = [r.risk.drawdown for r in chain]
    s.blocks.append(Block("svg", {
        "svg": sparkline_svg(navs, dates, title="NAV (USD) desde o início",
                             fmt=lambda v: format_money(v)),
        "text": sparkline_text(navs),
        "summary": f"NAV de {format_money(navs[0])} a {format_money(navs[-1])} "
                   f"({len(navs)} pregões)"}, caption="NAV"))
    s.blocks.append(Block("svg", {
        "svg": sparkline_svg(dds, dates, title="Drawdown desde o início",
                             fmt=lambda v: fmt_pct(v), area_to_zero=True),
        "text": sparkline_text(dds),
        "summary": f"drawdown atual {_pct(rk.drawdown)}; máximo "
                   f"{_pct(periods['max_drawdown'])}"}, caption="Drawdown"))
    sections.append(s)

    s = Section("Integridade")
    first = chain[0]
    scope = ("desde a inception, GENESIS" if first.prev_record_hash == GENESIS_RECORD_HASH
             else f"desde {fmt_date(first.date)}, histórico parcial")
    kv = [("record_hash", record.record_hash or NA), ("prev_record_hash", record.prev_record_hash),
          ("Hash do registro (recalculado)",
           "confere" if record.record_hash and record.compute_hash() == record.record_hash
           else "NÃO CONFERE (registro adulterado ou sem hash)"),
          (f"Cadeia de hashes ({len(chain)} registros {scope})",
           "íntegra" if chain_ok else "NÃO CONFERE: " + "; ".join(chain_problems[:5])),
          ("approval_hash", record.approval_hash or NA),
          ("semana da carteira vigente", record.live_book_week.isoformat()
           if record.live_book_week else NA)]
    kv += [(f"input:{k}", v) for k, v in sorted(record.input_hashes.items())]
    s.kv(kv)
    sections.append(s)

    doc = Document(
        title=f"{fund_name} — Relatório diário de {fmt_date(record.date)}",
        subtitle=f"Fechamento de {record.date.isoformat()} · {PAPER_TRADING_LABEL}",
        labels=labels, synthetic=synthetic, data_notice=notice, sections=sections, kpis=kpis)
    return to_markdown(doc), to_html(doc)


# ==========================================================
# Relatório semanal
# ==========================================================

def _by_issuer(views: Iterable[View]) -> dict[str, View]:
    out: dict[str, View] = {}
    for v in views:
        cur = out.get(v.issuer_id)
        if cur is None or (v.source == ViewSource.PM and cur.source != ViewSource.PM) or (
                cur.score == 0 and v.score != 0 and v.source == cur.source):
            out[v.issuer_id] = v
    return {k: out[k] for k in sorted(out)}


def _view_label(v: View | None) -> str:
    if v is None:
        return "—"
    flags = [f for f, on in (("no_long", v.no_long), ("no_short", v.no_short)) if on]
    if v.max_abs_weight is not None:
        flags.append(f"teto {fmt_pct(v.max_abs_weight)}")
    base = f"{v.score:+d} ({v.source.value}, conf. {fmt_num(v.confidence, 2)})"
    return base + (f" [{', '.join(flags)}]" if flags else "")


def issuer_period_returns(records: Sequence[DailyRecord]) -> dict[str, float]:
    """Retorno total em USD de cada emissor no período (Π(1+r)−1), pela linha de maior |valor|.

    Mede a DIREÇÃO da ação (independe do lado da posição), ao contrário do P&L, cujo sinal já
    embute o lado (short que ganha tem P&L positivo com a ação caindo). Dias sem negociação
    (``day_return_usd`` ausente) não contam — ausente nunca vira zero.
    """
    growth: dict[str, float] = {}
    for r in sorted(records, key=lambda x: x.date):
        best: dict[str, Any] = {}
        for pos in r.positions:
            if not _finite(pos.day_return_usd):
                continue
            cur = best.get(pos.issuer_id)
            key = (abs(pos.market_value_usd), pos.ticker)
            if cur is None or key > (abs(cur.market_value_usd), cur.ticker):
                best[pos.issuer_id] = pos
        for iid, pos in best.items():
            growth[iid] = growth.get(iid, 1.0) * (1.0 + float(pos.day_return_usd))
    return {k: v - 1.0 for k, v in sorted(growth.items())}


def _weights(p: Proposal | None) -> dict[str, PositionTarget]:
    if p is None:
        return {}
    out: dict[str, PositionTarget] = {}
    for pos in p.positions:
        out[pos.issuer_id] = pos
    return out


def _agg_attr(records: Sequence[DailyRecord], group: str) -> list[list[str]]:
    if not records:
        return []
    nav0 = float(records[0].nav_start_usd)
    acc: dict[str, float] = {}
    for r in records:
        for a in r.attribution:
            if a.group == group:
                acc[a.name] = acc.get(a.name, 0.0) + float(a.pnl_usd)
    rows = sorted(acc.items(), key=lambda kv: (-abs(kv[1]), kv[0]))
    return [[k, _usd(v, True), _bps(v / nav0)] for k, v in rows]


def _week_components(records: Sequence[DailyRecord]) -> list[list[str]]:
    if not records:
        return []
    nav0 = float(records[0].nav_start_usd)
    acc: dict[str, float] = {}
    for r in records:
        for k, v in r.pnl_components.items():
            if _finite(v):
                acc[k] = acc.get(k, 0.0) + float(v)
    keys = [k for k in _COMPONENT_ORDER if k in acc] + sorted(set(acc) - set(_COMPONENT_ORDER))
    return [[_COMPONENT_PT.get(k, k), _usd(acc[k], True), _bps(acc[k] / nav0)] for k in keys]


def _position_rows(positions: Sequence[PositionTarget], views: Mapping[str, View],
                   factbook: FactBook | None,
                   pm_rationale: Mapping[str, str] | None = None) -> list[list[str]]:
    """Linhas da carteira; o racional prefere a visão do PM (``views`` com fonte PM ou, na falta
    dela, a visão verificada em ``pm``) e cai para a visão de pesquisa."""
    rows = []
    pm_rationale = pm_rationale or {}
    for p in positions:
        v = views.get(p.issuer_id)
        text = (v.rationale if v is not None and v.source == ViewSource.PM
                else pm_rationale.get(p.issuer_id) or (v.rationale if v is not None else None))
        rationale = _truncate(_ai_text(text, factbook), AI_CELL_CHARS) if text else NA
        rows.append([p.issuer_id, p.name, p.country, p.sector, _pct(p.weight, signed=True),
                     _usd(p.notional_usd, signed=True), f"{p.execution_ticker} ({p.line_type})",
                     fmt_num(_f(p.days_to_liquidate), 1), p.squeeze_bucket,
                     fmt_num(_f(p.alpha_z), 2, signed=True),
                     f"{p.view_score:+d}" if p.view_score is not None else "—", rationale])
    return rows


def _liquidity_kv(risk: Any, cfg: FundConfig) -> list[tuple[str, str]]:
    """Liquidez da carteira na unidade do mandato: fechamentos (capacidade estrutural do leilão)
    com a execução no fechamento; dias a uma participação do ADTV na regra anterior."""
    if cfg.execution is not None:
        return [("Máx. fechamentos para liquidar", fmt_num(_f(risk.max_days_to_liquidate), 1)),
                ("% do gross liquidável em 1 fechamento", _pct(risk.pct_nav_liquidated_1d))]
    return [("Máx. dias para liquidar", fmt_num(_f(risk.max_days_to_liquidate), 1)),
            ("% do NAV liquidável em 1 dia", _pct(risk.pct_nav_liquidated_1d))]


def _expected_cost(p: Proposal) -> tuple[float | None, bool]:
    total, partial = 0.0, False
    for t in p.trades:
        if _finite(t.est_cost_bps):
            total += abs(float(t.notional_usd)) * float(t.est_cost_bps) / 1e4
        else:
            partial = True
    if not p.trades:
        return 0.0, False
    return total, partial


_GRUPO_PT = {"mercado": "Mercado", "pais": "País", "setor": "Setor", "estilo": "Estilo",
             "macro": "Macro (commodities e dólar)", "especifico": "Específico (idiossincrático)"}


def _idio_section(s: Section, risco: dict) -> None:
    """Fatia idiossincrática por modelo, κ_F, escada de drawdown e a variância por grupo
    (números gravados pela decisão em ``overrides["risco"]``)."""
    kap = risco.get("kappa_f") if isinstance(risco.get("kappa_f"), dict) else {}
    meta, piso = _f(risco.get("meta_idio")), _f(risco.get("piso_idio"))
    ref = (f" (meta {fmt_pct(meta, 0)}, piso {fmt_pct(piso, 0)})"
           if meta is not None and piso is not None else "")
    rows = [("Fatia idiossincrática — modelo de decisão", _pct(risco.get("idio_decisao")) + ref)]
    if "base" in (risco.get("modelos_gate") or []):
        rows.append(("Fatia idiossincrática — modelo base", _pct(risco.get("idio_base")) + ref))
    if _f(kap.get("valor")) is not None:
        rows.append(("Inflação de 2ª ordem do risco fatorial (κ_F)",
                     fmt_num(_f(kap.get("valor")), 2)))
    if _f(risco.get("custo_neutralidade_bp")) is not None:
        rows.append(("Custo marginal da neutralidade (bp a.a.)",
                     fmt_num(_f(risco.get("custo_neutralidade_bp")), 1)))
    esc = risco.get("escada")
    if isinstance(esc, dict) and _f(esc.get("sigma_teto")) is not None:
        regra = esc.get("regra_vinculante") or "escada de drawdown"
        escada_txt = (f"{fmt_num(_f(esc.get('multiplicador')), 2)} × "
                      f"{_pct(esc.get('sigma_ref'))}")
        rows.append(("Teto de vol pela escada de drawdown",
                     f"{_pct(esc.get('sigma_teto'))} = {escada_txt}"
                     if regra == "escada de drawdown" else
                     f"{_pct(esc.get('sigma_teto'))} ({regra}; escada: {escada_txt})"))
    s.kv(rows, caption="Risco idiossincrático da carteira decidida")
    grupos = risco.get("por_grupo") if isinstance(risco.get("por_grupo"), dict) else {}
    if grupos:
        s.table(["Grupo", "Fração da variância"],
                [[_GRUPO_PT.get(g, g), _pct(v)] for g, v in grupos.items()],
                caption="Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F "
                        "no bloco fatorial)")


def _factor_share(p: Proposal) -> float | None:
    """Fração fatorial publicada: na base do gate (κ_F, modelo que vincula) quando a decisão
    grava a medida idiossincrática; senão a do resumo de risco."""
    from ..risk.idio import base_vinculante

    basis = base_vinculante(p.overrides.get("risco") if isinstance(p.overrides, dict) else None)
    return basis["fatorial"] if basis is not None else _f(p.risk.factor_risk_share)


def _factor_share_row(p: Proposal, cfg: FundConfig) -> tuple[str, str]:
    from ..risk.idio import base_vinculante

    basis = base_vinculante(p.overrides.get("risco") if isinstance(p.overrides, dict) else None)
    lim = fmt_pct(cfg.risk.max_factor_risk_share)
    if basis is None:
        return ("Fração de risco fatorial", f"{_pct(p.risk.factor_risk_share)} (máx. {lim})")
    return ("Fração de risco fatorial", f"{_pct(basis['fatorial'])} com κ_F no "
                                        f"{basis['rotulo']} (máx. {lim})")


def _compare_rows(a: Proposal, b: Proposal) -> list[list[str]]:
    def row(label: str, x: Any, y: Any, f: Callable[[Any], str],
            diff: Callable[[Any], str] | None = None) -> list[str]:
        d = (diff or f)(x - y) if _finite(x) and _finite(y) else NA
        return [label, f(x), f(y), d]

    ra, rb = a.risk, b.risk
    oa, ob = a.optimizer, b.optimizer
    return [
        row("Alpha esperado (a.a.)", oa.expected_alpha_annual, ob.expected_alpha_annual,
            lambda v: _pct(v), lambda v: _pct(v, True)),
        row("Custo esperado (a.a.)", oa.expected_cost_annual, ob.expected_cost_annual,
            lambda v: _pct(v), lambda v: _pct(v, True)),
        row("Vol ex-ante", ra.ex_ante_vol, rb.ex_ante_vol, lambda v: _pct(v),
            lambda v: _pct(v, True)),
        row("Vol específica", ra.specific_vol, rb.specific_vol, lambda v: _pct(v),
            lambda v: _pct(v, True)),
        row("Fração de risco fatorial", _factor_share(a), _factor_share(b),
            lambda v: _pct(v), lambda v: _pct(v, True)),
        row("Beta", ra.beta, rb.beta, lambda v: fmt_num(_f(v), 3, True)),
        row("Gross", ra.gross, rb.gross, lambda v: _pct(v), lambda v: _pct(v, True)),
        row("Net", ra.net, rb.net, lambda v: _pct(v, True)),
        row("Longs", ra.n_long, rb.n_long, lambda v: fmt_num(_f(v), 0),
            lambda v: fmt_num(_f(v), 0, True)),
        row("Shorts", ra.n_short, rb.n_short, lambda v: fmt_num(_f(v), 0),
            lambda v: fmt_num(_f(v), 0, True)),
        row("N efetivo", ra.effective_n, rb.effective_n, lambda v: fmt_num(_f(v), 1),
            lambda v: fmt_num(_f(v), 1, True)),
        row("VaR 1d (99%)", ra.var_1d_99, rb.var_1d_99, lambda v: _pct(v),
            lambda v: _pct(v, True)),
    ]


def _overlap(a: Proposal, b: Proposal) -> dict[str, Any]:
    wa = {p.issuer_id: p.weight for p in a.positions}
    wb = {p.issuer_id: p.weight for p in b.positions}
    same_side = [i for i in wa if i in wb and (wa[i] > 0) == (wb[i] > 0)]
    common = sum(min(abs(wa[i]), abs(wb[i])) for i in same_side)
    ga, gb = sum(abs(v) for v in wa.values()), sum(abs(v) for v in wb.values())
    denom = 0.5 * (ga + gb)
    ids = set(wa) | set(wb)
    active = 0.5 * sum(abs(wa.get(i, 0.0) - wb.get(i, 0.0)) for i in ids)
    return {"names_cdp": len(wa), "names_shadow": len(wb), "common_same_side": len(same_side),
            "weight_overlap": common / denom if denom > 0 else None,
            "active_share": active / denom if denom > 0 else None,
            "only_cdp": sorted(set(wa) - set(wb)), "only_shadow": sorted(set(wb) - set(wa))}


def render_weekly_report(week: date, proposal: Proposal, decision: Decision | None,
                         pm: PMDecisionOutput | None, prev_proposal: Proposal | None,
                         prev_views: list[View], views: list[View],
                         week_records: list[DailyRecord], shadow_quant: Proposal | None,
                         fund_name: str, *, factbook: FactBook | None = None,
                         cfg: FundConfig | None = None, attempts: Sequence[Mapping] | None = None,
                         path_taken: str | None = None,
                         realized_residual: Mapping[str, float] | None = None
                         ) -> tuple[str, str]:
    """Relatório semanal (Markdown, HTML) da decisão autônoma do CDP.

    Seções: Decisão da semana (autônoma), Racional, Avaliação da semana anterior, O que mudou na
    visão, O que mudou na carteira, Carteira, Risco, Compliance, CDP vs sombra só-quant, Diário
    de decisão e Integridade. ``factbook`` resolve placeholders de textos de IA ainda não
    renderizados; números sempre formatados por código.

    Sem look-ahead: só entram registros diários anteriores a ``week``. A tese anterior é medida
    pelo retorno residual realizado (``realized_residual``) ou, na falta dele, pelo retorno total
    da ação em USD — nunca pelo sinal do P&L (que embute o lado da posição). A decisão é
    reverificada contra a proposta (hashes recalculados) e a divergência aparece em destaque.
    """
    cfg = cfg or _default_config()
    week_records = [r for r in week_records if r.date < week]
    synthetic = bool(proposal.is_synthetic)
    notice = proposal.data_notice or (SIMULATED_DATA_NOTICE if synthetic else "dados reais")
    mind = (pm.mind if pm is not None else None) or (decision.mind if decision else None) or NA
    path = path_taken or str(proposal.overrides.get("label", NA))
    risk = proposal.risk
    labels = [f"Mente que conduziu a semana: {mind}",
              f"Decisão autônoma assinada por {decision.approver if decision else AUTONOMOUS_DECIDER}",
              PAPER_TRADING_TEXT, f"Aviso de dados: {notice}"]
    decision_problems = _decision_problems(decision, proposal) if decision is not None else []
    if decision_problems:
        labels.insert(0, "ALERTA DE INTEGRIDADE: a decisão NÃO CONFERE com a proposta exibida ("
                      + "; ".join(decision_problems[:3]) + ")")
    vt = _f(proposal.overrides.get("vol_target"))
    kpis = [
        ("Caminho da decisão", path, "gates determinísticos"),
        ("Vol ex-ante", _pct(risk.ex_ante_vol),
         f"alvo {_pct(vt) if vt is not None else fmt_pct(cfg.risk.vol_target_annual)} · banda "
         f"{_band(cfg)}"),
        ("Posições", f"{risk.n_long} L / {risk.n_short} S", f"N efetivo {fmt_num(risk.effective_n, 1)}"),
        ("Gross / net", f"{_pct(risk.gross)} / {_pct(risk.net, True)}", "% do NAV"),
        ("Beta", fmt_num(_f(risk.beta), 3, True), f"limite ±{fmt_num(cfg.risk.beta_max_abs)}"),
        ("Alpha esperado", _pct(proposal.optimizer.expected_alpha_annual), "anual (modelo)"),
    ]
    sections: list[Section] = []
    view_map = _by_issuer(views)

    # 1. Decisão da semana (autônoma)
    s = Section("Decisão da semana (autônoma)")
    rows: list[tuple[str, str]] = []
    if decision is not None:
        rows += [("Decisor", decision.approver), ("Modo", decision.mode.value),
                 ("Decisão", decision.decision.value),
                 ("Decidida em", fmt_date(decision.decided_at)),
                 ("Convicção", str(decision.conviction) if decision.conviction else NA),
                 ("Falhas SOFT cientes", ", ".join(decision.acknowledged_soft_checks) or "nenhuma")]
    else:
        rows.append(("Decisão", "não registrada"))
    rows += [("Mente", mind), ("Caminho", path),
             ("Vol-alvo aplicada", _pct(vt) if vt is not None else "mandato"),
             ("Gross máximo aplicado", _mult(proposal.overrides.get("gross_max"))
              if proposal.overrides.get("gross_max") is not None else "mandato")]
    if pm is not None:
        rows += [("Regime [IA]", REGIME_PT.get(pm.regime, pm.regime)),
                 ("Postura de risco [IA]", POSTURE_PT.get(pm.risk_posture, pm.risk_posture)),
                 ("Abstenção do PM", "sim (o quant decidiu)" if pm.abstain else "não"),
                 ("Visões / exclusões do PM", f"{len(pm.views)} / {len(pm.exclusions)}")]
    rows += [("Posições", f"{risk.n_long} longs · {risk.n_short} shorts"),
             ("Vol ex-ante", _pct(risk.ex_ante_vol)), ("Gross / net",
                                                        f"{_pct(risk.gross)} / {_pct(risk.net, True)}"),
             ("Beta", fmt_num(_f(risk.beta), 3, True))]
    s.kv(rows)
    if decision is not None:
        s.p(_ai_text(decision.rationale, factbook), ai=True)
    sections.append(s)

    # 2. Racional
    s = Section("Racional", ai=True)
    s.p(_ai_text(pm.market_view if pm else None, factbook), ai=True)
    sections.append(s)

    # 3. Avaliação da semana anterior
    s = Section("Avaliação da semana anterior")
    recs = sorted(week_records, key=lambda r: r.date)
    if recs:
        growth = 1.0
        for r in recs:
            growth *= 1.0 + float(r.ret)
        last = recs[-1]
        s.kv([("Período", f"{fmt_date(recs[0].date)} a {fmt_date(last.date)} ({len(recs)} pregões)"),
              ("Retorno da semana", _pct(growth - 1.0, True)),
              ("P&L da semana", _usd(sum(float(r.pnl_usd) for r in recs), True)),
              ("NAV", f"{format_money(recs[0].nav_start_usd)} → {format_money(last.nav_end_usd)}"),
              ("Vol ex-ante no fechamento", _pct(last.risk.ex_ante_vol)),
              ("Drawdown no fechamento", _pct(last.risk.drawdown))])
        s.table(["Componente", "P&L", "Contribuição"], _week_components(recs),
                caption="Componentes do P&L na semana")
        for group in ("factor_group", "country", "sector", "side"):
            s.table([_GROUP_PT[group], "P&L", "Contribuição"], _agg_attr(recs, group)[:TOP_N],
                    caption=f"{_GROUP_PT[group]} — semana")
    else:
        s.p("Sem registros diários na semana anterior (inception ou primeira semana).")
    prev_map = {k: v for k, v in _by_issuer(prev_views).items() if v.score != 0}
    stock_ret = issuer_period_returns(recs)
    thesis_rows = []
    for iid, v in prev_map.items():
        resid = _f((realized_residual or {}).get(iid))
        total = _f(stock_ret.get(iid))
        if resid is not None:
            measure, sign = f"resíduo {_pct(resid, True)}", resid
        elif total is not None:
            measure, sign = f"retorno total USD {_pct(total, True)}", total
        else:
            measure, sign = NA, None
        worked = NA if sign is None or sign == 0 else ("sim" if (sign > 0) == (v.score > 0)
                                                      else "não")
        thesis_rows.append([iid, f"{v.score:+d}", v.source.value, fmt_num(v.confidence, 2),
                            measure, worked])
    s.table(["Emissor", "Stance anterior", "Fonte", "Confiança", "Realizado", "Funcionou?"],
            thesis_rows, caption="Teses da semana anterior (realizado medido por código)")
    s.p(_ai_text(pm.evaluation_last_week if pm else None, factbook), ai=True)
    sections.append(s)

    # 4. O que mudou na visão
    s = Section("O que mudou na visão")
    prev_all = _by_issuer(prev_views)
    diff_rows = []
    for iid in sorted(set(prev_all) | set(view_map)):
        a, b = prev_all.get(iid), view_map.get(iid)
        if a is None:
            change = "nova"
        elif b is None:
            change = "encerrada"
        elif a.score != b.score:
            change = "stance ↑" if b.score > a.score else "stance ↓"
        elif (a.no_long, a.no_short, a.max_abs_weight) != (b.no_long, b.no_short,
                                                            b.max_abs_weight):
            change = "restrição alterada"
        else:
            continue
        diff_rows.append([iid, _view_label(a), _view_label(b), change])
    counts = {k: sum(1 for r in diff_rows if r[3] == k) for k in ("nova", "encerrada")}
    s.p(f"Visões novas: {counts['nova']}; encerradas: {counts['encerrada']}; com mudança de "
        f"stance ou restrição: {len(diff_rows) - counts['nova'] - counts['encerrada']}.")
    s.table(["Emissor", "Antes", "Agora", "Mudança"], diff_rows)
    s.p(_ai_text(pm.what_changed if pm else None, factbook), ai=True)
    sections.append(s)

    # 5. O que mudou na carteira
    s = Section("O que mudou na carteira")
    before, after = _weights(prev_proposal), _weights(proposal)
    change_rows = []
    tally = {"Entrada": 0, "Saída": 0, "Aumento": 0, "Redução": 0, "Inversão": 0}
    line_changes = 0
    turnover = 0.0
    for iid in sorted(set(before) | set(after)):
        a, b = before.get(iid), after.get(iid)
        wa, wb = (a.weight if a else 0.0), (b.weight if b else 0.0)
        turnover += abs(wb - wa)
        if a is None:
            action = "Entrada"
        elif b is None:
            action = "Saída"
        elif (wa > 0) != (wb > 0):
            action = "Inversão"
        elif abs(wb) > abs(wa) + 1e-9:
            action = "Aumento"
        elif abs(wb) < abs(wa) - 1e-9:
            action = "Redução"
        else:
            action = ""
        line = ""
        if a is not None and b is not None and a.execution_ticker != b.execution_ticker:
            line = f"{a.execution_ticker} → {b.execution_ticker}"
            line_changes += 1
        if not action and not line:
            continue
        if action:
            tally[action] += 1
        side = (b or a).side.value if (b or a) else NA  # type: ignore[union-attr]
        change_rows.append([iid, action or "Troca de linha", side, _pct(wa, True) if a else "—",
                            _pct(wb, True) if b else "—", _pct(wb - wa, True), line or "—"])
    change_rows.sort(key=lambda r: (r[1], r[0]))
    cost, partial = _expected_cost(proposal)
    s.kv([("Base de comparação", "carteira da semana anterior" if prev_proposal is not None
           else "caixa (inception)"),
          ("Entradas / saídas", f"{tally['Entrada']} / {tally['Saída']}"),
          ("Aumentos / reduções / inversões",
           f"{tally['Aumento']} / {tally['Redução']} / {tally['Inversão']}"),
          ("Trocas de linha de execução", str(line_changes)),
          ("Turnover (Σ|Δw|)", _pct(turnover)),
          ("Ordens", str(len(proposal.trades))),
          ("Custo estimado das ordens", (_usd(cost) + (" (parcial: ordens sem custo estimado)"
                                                       if partial else ""))
           if cost is not None else NA),
          ("Custo estimado (% do NAV)", _pct(cost / proposal.nav_usd) if cost is not None else NA),
          ("Custo anual no objetivo (modelo)", _pct(proposal.optimizer.expected_cost_annual))])
    s.table(["Emissor", "Ação", "Lado", "Peso anterior", "Peso novo", "Δ peso", "Linha"],
            change_rows)
    sections.append(s)

    # 6. Carteira
    s = Section("Carteira")
    longs = sorted((p for p in proposal.positions if p.side == Side.LONG),
                   key=lambda p: (-abs(p.weight), p.issuer_id))
    shorts = sorted((p for p in proposal.positions if p.side == Side.SHORT),
                    key=lambda p: (-abs(p.weight), p.issuer_id))
    liq_header = ("Fechamentos p/ liquidar" if cfg.execution is not None
                  else "Dias p/ liquidar")
    headers = ["Emissor", "Nome", "País", "Setor", "Peso", "Nocional", "Linha", liq_header,
               "Squeeze", "alpha z", "Visão", "Racional [IA]"]
    pm_rat = ({v.issuer_id: v.rationale for v in pm.views}
              if pm is not None and not pm.abstain else {})
    s.table(headers, _position_rows(longs[:TOP_N], view_map, factbook, pm_rat),
            caption=f"Maiores longs ({len(longs)} no total)")
    s.table(headers, _position_rows(shorts[:TOP_N], view_map, factbook, pm_rat),
            caption=f"Maiores shorts ({len(shorts)} no total)")
    sections.append(s)

    # 7. Risco
    s = Section("Risco")
    vol = _f(risk.ex_ante_vol)
    s.kv([("Vol ex-ante", f"{_pct(vol)} ({_vol_status(vol, cfg)} {_band(cfg)})"),
          ("Vol-alvo aplicada", _pct(vt) if vt is not None else fmt_pct(cfg.risk.vol_target_annual)),
          ("Vol fatorial / específica", f"{_pct(risk.factor_vol)} / {_pct(risk.specific_vol)}"),
          _factor_share_row(proposal, cfg),
          ("Beta", fmt_num(_f(risk.beta), 3, True)),
          ("Long / short", f"{_pct(risk.long_exposure)} / {_pct(risk.short_exposure, True)}"),
          ("VaR / ES 1d (99%)", f"{_pct(risk.var_1d_99)} / {_pct(risk.es_1d_99)}"),
          ("VaR 1 semana (99%)", _pct(risk.var_1w_99)),
          ("N efetivo", fmt_num(_f(risk.effective_n), 1)),
          *_liquidity_kv(risk, cfg)])
    risco = proposal.overrides.get("risco") if isinstance(proposal.overrides, dict) else None
    if isinstance(risco, dict):
        _idio_section(s, risco)
    exp_rows = [[e.group, e.name, _pct(e.long), _pct(e.short, True), _pct(e.net, True),
                 _pct(e.gross), _pct(e.limit) if e.limit is not None else NA]
                for e in sorted(risk.exposures, key=lambda e: (e.group, -abs(e.net), e.name))]
    s.table(["Grupo", "Nome", "Long", "Short", "Net", "Gross", "Limite"], exp_rows,
            caption="Exposições (país, setor, estilo, temas)")
    stress = sorted(risk.stress_tests.items(), key=lambda kv: (kv[1], kv[0]))[:TOP_N]
    s.table(["Cenário", "P&L (% do NAV)"], [[k, _pct(v, True)] for k, v in stress],
            caption="Testes de estresse (piores cenários)")
    fac = sorted(risk.factor_contributions.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:TOP_N]
    s.table(["Fator", "Fração da variância"], [[k, _pct(v, True)] for k, v in fac],
            caption="Contribuições fatoriais para a variância (Euler)")
    top = sorted(risk.top_risk_contributors.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:TOP_N]
    s.table(["Emissor", "Fração da variância"], [[k, _pct(v, True)] for k, v in top],
            caption="Maiores contribuidores de risco")
    sections.append(s)

    # 8. Compliance
    s = Section("Compliance")
    order = {Severity.HARD: 0, Severity.SOFT: 1, Severity.INFO: 2}
    checks = sorted(proposal.compliance, key=lambda c: (c.passed, order[c.severity], c.check_id))
    s.table(["Gate", "Descrição", "Severidade", "Resultado", "Valor", "Limite", "Detalhe"],
            [[c.check_id, c.name, c.severity.value, "OK" if c.passed else "FALHA",
              fmt_num(_f(c.value), 4), fmt_num(_f(c.limit), 4), c.details] for c in checks],
            caption=f"{sum(1 for c in checks if not c.passed)} gate(s) com falha")
    s.kv([("Caminho tomado", path),
          ("Falhas HARD", ", ".join(c.check_id for c in proposal.hard_failures) or "nenhuma"),
          ("Falhas SOFT", ", ".join(c.check_id for c in proposal.soft_failures) or "nenhuma")])
    if attempts:
        s.table(["Tentativa", "Motivo", "Longs", "Shorts", "Vol", "Falhas HARD"],
                [[str(a.get("label", NA)), str(a.get("why", "")), str(a.get("n_long", NA)),
                  str(a.get("n_short", NA)), _pct(a.get("vol")),
                  ", ".join(a.get("hard") or []) or "nenhuma"] for a in attempts],
                caption="Sequência de fallback")
    notes = [n for n in proposal.optimizer.notes if any(
        k in n for k in ("Fallback", "KILL_SWITCH", "relax", "Relax", "inviáv"))]
    if notes:
        s.items(notes, caption="Notas de fallback e relaxamento")
    sections.append(s)

    # 9. CDP vs sombra só-quant
    s = Section("CDP vs sombra só-quant")
    if shadow_quant is None:
        s.p("Carteira-sombra só-quant indisponível nesta semana.")
    else:
        ov = _overlap(proposal, shadow_quant)
        s.kv([("Nomes CDP / sombra", f"{ov['names_cdp']} / {ov['names_shadow']}"),
              ("Nomes em comum (mesmo lado)", str(ov["common_same_side"])),
              ("Sobreposição de pesos", _pct(ov["weight_overlap"])),
              ("Active share vs sombra", _pct(ov["active_share"])),
              ("Só no CDP", ", ".join(ov["only_cdp"][:15]) or "nenhum"),
              ("Só na sombra", ", ".join(ov["only_shadow"][:15]) or "nenhum")])
        s.table(["Métrica", "CDP", "Sombra só-quant", "Diferença"],
                _compare_rows(proposal, shadow_quant))
    sections.append(s)

    # 10. Diário de decisão
    s = Section("Diário de decisão", ai=True)
    journal = decision.journal if decision is not None else None
    if journal is not None:
        s.kv([("Situação [IA]", _ai_text(journal.situation, factbook)),
              ("Variáveis-chave", "; ".join(journal.key_variables) or NA),
              ("O que mudou [IA]", _ai_text(journal.alternatives_considered, factbook)),
              ("Horizonte (semanas)", str(journal.horizon_weeks)),
              ("Dimensionamento (código)", journal.sizing_rationale or NA),
              ("IA × quant × PM [IA]", _ai_text(journal.ai_vs_quant_vs_pm, factbook)),
              ("Premortem [IA]", _ai_text(journal.premortem, factbook)),
              ("Estado", journal.mental_state or NA)])
        jrows = [[j.issuer_id, _ai_text(j.thesis, factbook),
                  _ai_text(j.invalidation_criteria, factbook), _ai_text(j.premortem, factbook)]
                 for j in journal.positions]
    elif pm is not None:
        jrows = [[j.issuer_id, _ai_text(j.thesis, factbook),
                  _ai_text(j.invalidation_criteria, factbook), _ai_text(j.premortem, factbook)]
                 for j in pm.position_journal]
    else:
        jrows = []
    s.table(["Emissor", "Tese", "Invalidação", "Premortem"], jrows, ai=True,
            caption="Teses por posição")
    sections.append(s)

    # 11. Integridade
    s = Section("Integridade")
    kv = [("proposal_id", proposal.proposal_id), ("proposal_hash", proposal.proposal_hash()),
          ("snapshot_hash", proposal.snapshot_hash), ("config_hash", proposal.config_hash),
          ("research_hash", proposal.research_hash)]
    if decision is not None:
        kv += [("Verificação da decisão (hashes recalculados)",
                "confere" if not decision_problems
                else "NÃO CONFERE: " + "; ".join(decision_problems[:5])),
               ("approval_hash", decision.approval_hash),
               ("pm_decision_hash", decision.pm_decision_hash or NA),
               ("risk_gate_hash", decision.risk_gate_hash or NA),
               ("audit_head_hash", decision.audit_head_hash or NA)]
    if shadow_quant is not None:
        kv.append(("shadow_quant_hash", shadow_quant.proposal_hash()))
    if prev_proposal is not None:
        kv.append(("prev_proposal_hash", prev_proposal.proposal_hash()))
    s.kv(kv)
    sections.append(s)

    doc = Document(
        title=f"{fund_name} — Relatório semanal — semana de {fmt_date(week)}",
        subtitle=f"Decisão autônoma do CDP · mente {mind} · {PAPER_TRADING_LABEL}",
        labels=labels, synthetic=synthetic, data_notice=notice, sections=sections, kpis=kpis)
    return to_markdown(doc), to_html(doc)


# ==========================================================
# Gravação
# ==========================================================

def _write_exclusive(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.link(tmp_name, path)  # falha se o destino já existir (nunca sobrescreve)
    except FileExistsError:
        raise FileExistsError(f"Relatório já existe (imutável): {path}") from None
    except OSError:
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_report_files(out_dir: Path | str, md: str, html_text: str, *,
                       stem: str = REPORT_STEM) -> dict[str, str]:
    """Grava ``<stem>.md`` e ``<stem>.html`` (exclusivos) e devolve caminhos e SHA-256.

    Recusa sobrescrever: se qualquer um dos arquivos existir, nada é gravado. ``stem`` é um nome
    simples (sem separadores de caminho nem ``..``).
    """
    if not _STEM_RE.fullmatch(stem) or ".." in stem:
        raise ValueError(f"Nome de relatório inválido: {stem!r}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path, html_path = out / f"{stem}.md", out / f"{stem}.html"
    existing = [p.as_posix() for p in (md_path, html_path) if p.exists()]
    if existing:
        raise FileExistsError("Relatório já existe (imutável): " + ", ".join(existing))
    _write_exclusive(md_path, md)
    try:
        _write_exclusive(html_path, html_text)
    except BaseException:
        md_path.unlink(missing_ok=True)
        raise
    return {"md": md_path.as_posix(), "html": html_path.as_posix(),
            "md_sha256": sha256_file(md_path), "html_sha256": sha256_file(html_path)}


__all__ = [
    "PAPER_TRADING_LABEL",
    "PAPER_TRADING_TEXT",
    "Block",
    "Document",
    "Section",
    "issuer_period_returns",
    "md_to_safe_html",
    "render_daily_report",
    "render_weekly_report",
    "sparkline_svg",
    "sparkline_text",
    "to_html",
    "to_markdown",
    "verify_record_chain",
    "write_report_files",
]
