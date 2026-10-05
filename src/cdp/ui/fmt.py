"""Formatação pt-BR (``1.234,56``; ``+1,25%``; ``USD 1,50 mm``) e paleta institucional do app.

Toda formatação delega às funções do memo (``workflow.memo``), as mesmas dos relatórios, para que
app e relatórios exibam exatamente os mesmos textos. Ausente ⇒ ``n/d`` (nunca zero).
"""

from __future__ import annotations

import math
import numbers
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..config import FundConfig
from ..workflow.memo import NA, fmt_num, fmt_pct, fmt_usd, fmt_usd_mm

# ---------------------------------------------------------------- paleta
LONG_COLOR = "#0E7C7B"      # teal (comprado)
SHORT_COLOR = "#D1495B"     # vermelho (vendido)
SHORT_ALT_COLOR = "#E07A1F"  # laranja (vendido, série secundária)
NEUTRAL_COLOR = "#8D99AE"   # cinza neutro
CDP_COLOR = "#1D3557"       # azul-marinho (CDP)
SHADOW_COLOR = "#8D99AE"    # cinza (sombra só-quant)
POSITIVE_COLOR = "#2A9D8F"
NEGATIVE_COLOR = "#D1495B"
WARN_COLOR = "#E9A23B"
BAND_FILL = "rgba(42, 157, 143, 0.10)"
GRID_COLOR = "#E6E9EF"

SIDE_COLORS = {"LONG": LONG_COLOR, "SHORT": SHORT_COLOR}
SIDE_PT = {"LONG": "Comprado", "SHORT": "Vendido"}
COMPONENT_PT = {"equity": "Ações (total)", "factor": "Fatorial", "specific": "Específico (alpha)",
                "costs": "Custos", "borrow": "Aluguel", "financing": "Financiamento"}
GROUP_PT = {"market": "Mercado", "country": "País", "sector": "Setor", "style": "Estilo",
            "currency": "Moeda", "factor_group": "Grupo de fatores", "factor": "Fator",
            "issuer": "Emissor", "side": "Lado", "component": "Componente"}
SEVERITY_ORDER = {"HARD": 0, "SOFT": 1, "INFO": 2}
PATH_PT = {"cdp": "CDP (pesquisa de IA + decisão do PM)",
           "cdp-restricoes": "Fallback 1: só restrições da IA/PM",
           "quant": "Fallback 2: só-quant", "manter": "Fallback 3: manter a carteira",
           "reduzir-risco": "KILL SWITCH: apenas redução de risco"}

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")


def is_num(x: object) -> bool:
    """Número real finito (``None``/NaN/inf/bool não são números)."""
    return (isinstance(x, numbers.Real) and not isinstance(x, bool)
            and math.isfinite(float(x)))


def _f(x: object) -> float | None:
    return float(x) if is_num(x) else None


def num(x: object, digits: int = 2, signed: bool = False) -> str:
    return fmt_num(_f(x), digits, signed)


def pct(x: object, digits: int = 2, signed: bool = False) -> str:
    return fmt_pct(_f(x), digits, signed)


def usd_mm(x: object, digits: int = 2, signed: bool = False) -> str:
    return fmt_usd_mm(_f(x), digits, signed)


def usd(x: object, digits: int = 0, signed: bool = False) -> str:
    return fmt_usd(_f(x), digits, signed)


def bps(fraction: object, digits: int = 1, signed: bool = True) -> str:
    """Fração do NAV em pontos-base (``0.0012`` ⇒ ``+12,0 bps``)."""
    v = _f(fraction)
    return NA if v is None else f"{fmt_num(v * 1e4, digits, signed)} bps"


def mult(x: object, digits: int = 2) -> str:
    v = _f(x)
    return NA if v is None else f"{fmt_num(v, digits)}x"


def days(x: object, digits: int = 1) -> str:
    v = _f(x)
    return NA if v is None else f"{fmt_num(v, digits)} d"


def short_hash(h: str | None, n: int = 12) -> str:
    return f"{h[:n]}…" if h else NA


def date_br(d: date | datetime | None) -> str:
    if d is None:
        return NA
    return d.strftime("%d/%m/%Y")


def dt_local(dt: datetime | None, tz: str = "America/Sao_Paulo") -> str:
    """Data e hora no fuso do fundo (``05/10/2026 14:00 (Brasília)``)."""
    if dt is None:
        return NA
    if dt.tzinfo is None:
        return dt.strftime("%d/%m/%Y %H:%M (sem fuso)")
    local = dt.astimezone(ZoneInfo(tz))
    label = "Brasília" if tz == "America/Sao_Paulo" else tz
    return local.strftime("%d/%m/%Y %H:%M") + f" ({label})"


def escape_md(text: object) -> str:
    """Texto não confiável (notícias, textos de IA) como texto puro em Markdown.

    Escapa a marcação (links, imagens, ênfase, HTML) para que nada seja interpretado.
    """
    if text is None:
        return ""
    clean = str(text).replace("\r", " ")
    return _MD_SPECIAL.sub(r"\\\1", clean)


_UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")
_HEADING = re.compile(r"^(#{1,6})(\s)")
_CODE_SPAN = re.compile(r"(`[^`]*`)")
_AUTOLINK = re.compile(r"<((?:https?|ftp|mailto|javascript|data):)", re.IGNORECASE)


def _defuse(text: str) -> str:
    """Desarma links/imagens Markdown (``[x](url)``, ``![x](url)``, ``<http://…>``): os
    relatórios do código não têm links; um arquivo alterado não carrega nada externo."""
    return _AUTOLINK.sub(r"\\<\1", text.replace("](", "]\\("))


def report_md(text: str, demote: int = 0) -> str:
    """Markdown gerado pelo código (relatórios, memo, comentário) pronto para ``st.markdown``.

    Escapa ``$`` fora de trechos de código (evita que ``US$ 1,00`` vire fórmula LaTeX), desarma
    links e imagens (nada externo é carregado nem clicável) e, opcionalmente, rebaixa os títulos
    em ``demote`` níveis (limitado a ``######``).
    """
    out: list[str] = []
    fenced = False
    for line in (text or "").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        if fenced:
            out.append(line)
            continue
        parts = _CODE_SPAN.split(line)
        parts = [p if i % 2 else _defuse(_UNESCAPED_DOLLAR.sub(r"\\$", p))
                 for i, p in enumerate(parts)]
        line = "".join(parts)
        if demote > 0:
            line = _HEADING.sub(lambda m: "#" * min(6, len(m.group(1)) + demote) + m.group(2),
                                line)
        out.append(line)
    return "\n".join(out)


def label(text: object) -> str:
    """Rótulo de widget (expander, métrica, abas) com texto externo: os rótulos do Streamlit
    interpretam Markdown (inclusive links e imagens), então o texto é escapado."""
    return escape_md(text).replace("\n", " ")


def code(text: object) -> str:
    """Texto como trecho de código Markdown (sem crases internas; nada é interpretado)."""
    clean = str(text if text is not None else NA).replace("`", "'").replace("\n", " ")
    return f"`{clean}`"


def sign_color(x: object) -> str:
    v = _f(x)
    if v is None or v == 0:
        return NEUTRAL_COLOR
    return POSITIVE_COLOR if v > 0 else NEGATIVE_COLOR


# ---------------------------------------------------------------- estados
@dataclass(frozen=True)
class Status:
    """Rótulo e cor (paleta básica do Streamlit) de um indicador vs. limite."""

    label: str
    color: str  # green | orange | red | gray | blue


def vol_status(vol: object, cfg: FundConfig) -> Status:
    """Vol ex-ante vs. banda do mandato (abaixo: subutilização; acima: bloqueio)."""
    v = _f(vol)
    if v is None:
        return Status("n/d", "gray")
    rk = cfg.risk
    if v > rk.vol_band_max:
        return Status(f"acima da banda ({pct(rk.vol_band_min, 0)}–{pct(rk.vol_band_max, 0)})",
                      "red")
    if v < rk.vol_band_min:
        return Status(f"abaixo da banda ({pct(rk.vol_band_min, 0)}–{pct(rk.vol_band_max, 0)})",
                      "orange")
    return Status(f"dentro da banda ({pct(rk.vol_band_min, 0)}–{pct(rk.vol_band_max, 0)})",
                  "green")


def ladder_status(drawdown: object, cfg: FundConfig) -> Status:
    """Drawdown vs. escada do mandato (stop suave, stop duro, stop-out)."""
    dd = _f(drawdown)
    if dd is None:
        return Status("n/d", "gray")
    lad = cfg.drawdown
    if dd <= lad.stop_out:
        return Status("stop-out", "red")
    if dd <= lad.hard_stop:
        return Status("stop duro", "red")
    if dd <= lad.soft_stop:
        return Status("stop suave", "orange")
    return Status("normal", "green")


def limit_status(value: object, limit: object) -> Status:
    """|valor| vs. limite absoluto."""
    v, lim = _f(value), _f(limit)
    if v is None or lim is None:
        return Status("sem limite" if v is not None else "n/d", "gray")
    if abs(v) > lim + 1e-12:
        return Status(f"fora do limite ±{pct(lim)}", "red")
    return Status(f"dentro do limite ±{pct(limit)}", "green")


def max_status(value: object, limit: object,
               formatter: Callable[[object], str] | None = None) -> Status:
    """Valor vs. teto (VaR, ES, dias para liquidar); ``formatter`` formata o teto."""
    v, lim = _f(value), _f(limit)
    if v is None or lim is None:
        return Status("n/d", "gray")
    f = formatter or pct
    if v > lim + 1e-12:
        return Status(f"acima do teto {f(lim)}", "red")
    return Status(f"teto {f(lim)}", "green")
