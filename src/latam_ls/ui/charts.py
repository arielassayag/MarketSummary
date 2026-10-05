"""Figuras Plotly do app (paleta institucional; números já calculados pelos registros).

Convenções: eixos em pt-BR (separador decimal vírgula), comprado = teal, vendido = vermelho,
neutro = cinza; linhas de limite tracejadas; nada é recalculado aqui além de escalas de exibição.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go

from ..config import FundConfig
from . import fmt

_FONT = "Inter, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"


def _base(fig: go.Figure, title: str = "", height: int = 340, y_title: str = "") -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0.0, "xanchor": "left", "font": {"size": 15}},
        height=height, margin={"l": 10, "r": 10, "t": 46 if title else 16, "b": 10},
        font={"family": _FONT, "size": 12, "color": "#1C252E"},
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", separators=",.",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1.0},
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor=fmt.GRID_COLOR)
    fig.update_yaxes(gridcolor=fmt.GRID_COLOR, zerolinecolor="#C9CED6", title_text=y_title)
    return fig


def nav_chart(main: pd.DataFrame | None, shadow: pd.DataFrame | None,
              inception_nav: float | None = None) -> go.Figure:
    """NAV (USD mm) do CDP vs. sombra só-quant desde o início."""
    fig = go.Figure()
    if main is not None and not main.empty:
        fig.add_trace(go.Scatter(x=main.index, y=main["nav"] / 1e6, name="CDP",
                                 mode="lines+markers", line={"color": fmt.CDP_COLOR, "width": 2.5},
                                 hovertemplate="%{y:,.2f} mm<extra>CDP</extra>"))
    if shadow is not None and not shadow.empty:
        fig.add_trace(go.Scatter(x=shadow.index, y=shadow["nav"] / 1e6,
                                 name="Sombra só-quant", mode="lines",
                                 line={"color": fmt.SHADOW_COLOR, "width": 2, "dash": "dash"},
                                 hovertemplate="%{y:,.2f} mm<extra>Sombra</extra>"))
    if inception_nav is not None:
        fig.add_hline(y=inception_nav / 1e6, line={"color": "#C9CED6", "dash": "dot"},
                      annotation_text="NAV inicial", annotation_position="bottom right")
    return _base(fig, "NAV desde o início (USD mm)", y_title="USD mm")


def drawdown_chart(dd: pd.Series, cfg: FundConfig) -> go.Figure:
    """Drawdown desde o pico com a escada do mandato."""
    fig = go.Figure()
    if not dd.empty:
        fig.add_trace(go.Scatter(x=dd.index, y=dd.astype(float) * 100, name="Drawdown",
                                 fill="tozeroy", mode="lines",
                                 line={"color": fmt.NEGATIVE_COLOR, "width": 2},
                                 fillcolor="rgba(209, 73, 91, 0.15)",
                                 hovertemplate="%{y:.2f}%<extra></extra>"))
    lad = cfg.drawdown
    for level, label, color in ((lad.soft_stop, "stop suave", fmt.WARN_COLOR),
                                (lad.hard_stop, "stop duro", fmt.NEGATIVE_COLOR),
                                (lad.stop_out, "stop-out", "#7A1F2B")):
        fig.add_hline(y=level * 100, line={"color": color, "dash": "dash", "width": 1},
                      annotation_text=f"{label} {fmt.pct(level, 1)}",
                      annotation_position="bottom left")
    fig.update_yaxes(ticksuffix="%", range=[min(lad.stop_out * 100 * 1.15,
                                                 float(dd.min() * 100) - 0.5 if not dd.empty
                                                 else 0.0), 0.5])
    return _base(fig, "Drawdown desde o pico vs. escada do mandato", y_title="% do pico")


def vol_chart(series: pd.DataFrame, cfg: FundConfig) -> go.Figure:
    """Vol ex-ante e realizada (21d/63d) vs. banda e meta do mandato."""
    fig = go.Figure()
    rk = cfg.risk
    if not series.empty:
        x0, x1 = series.index.min(), series.index.max()
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=rk.vol_band_min * 100,
                      y1=rk.vol_band_max * 100, fillcolor=fmt.BAND_FILL, line={"width": 0},
                      layer="below")
        for col, name, color, dash in (("ex_ante_vol", "Vol ex-ante", fmt.CDP_COLOR, None),
                                       ("realized_vol_21d", "Realizada 21d", fmt.LONG_COLOR,
                                        "dot"),
                                       ("realized_vol_63d", "Realizada 63d", fmt.SHORT_ALT_COLOR,
                                        "dash")):
            s = series[col].dropna() if col in series else pd.Series(dtype=float)
            if s.empty:
                continue
            fig.add_trace(go.Scatter(x=s.index, y=s * 100, name=name, mode="lines+markers",
                                     line={"color": color, "width": 2, "dash": dash},
                                     hovertemplate="%{y:.2f}%<extra>" + name + "</extra>"))
    fig.add_hline(y=rk.vol_target_annual * 100, line={"color": "#2A9D8F", "dash": "dash"},
                  annotation_text=f"meta {fmt.pct(rk.vol_target_annual, 0)}",
                  annotation_position="top left")
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    return _base(fig, f"Volatilidade vs. banda {fmt.pct(rk.vol_band_min, 0)}–"
                      f"{fmt.pct(rk.vol_band_max, 0)}", y_title="% a.a.")


def signed_bars(labels: Sequence[str], values: Sequence[float | None], title: str, *,
                unit: str = "bps", limit: float | None = None, height: int | None = None,
                hover: Sequence[str] | None = None) -> go.Figure:
    """Barras horizontais com cor pelo sinal; ``limit`` desenha ±limite (mesma unidade)."""
    scale = {"bps": 1e4, "pct": 100.0, "mm": 1e-6, "x": 1.0}[unit]
    suffix = {"bps": " bps", "pct": "%", "mm": " mm", "x": ""}[unit]
    ys = list(labels)
    xs = [None if v is None or not fmt.is_num(v) else float(v) * scale for v in values]
    colors = [fmt.sign_color(v) for v in values]
    fig = go.Figure(go.Bar(
        x=xs, y=ys, orientation="h", marker={"color": colors},
        hovertext=list(hover) if hover is not None else None,
        hovertemplate="%{y}: %{x:,.2f}" + suffix + "<extra></extra>"))
    if limit is not None and fmt.is_num(limit):
        for sgn in (-1, 1):
            fig.add_vline(x=sgn * float(limit) * scale,
                          line={"color": fmt.NEGATIVE_COLOR, "dash": "dash", "width": 1})
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(ticksuffix=suffix, zeroline=True, zerolinecolor="#9AA3AF")
    h = height or max(220, 28 * len(ys) + 80)
    fig = _base(fig, title, height=h)
    fig.update_layout(hovermode="closest", showlegend=False)
    return fig


def exposure_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """Exposição líquida por linha (% NAV) com o limite ±do mandato."""
    if df.empty:
        return _base(go.Figure(), title)
    df = df.sort_values("net")
    limit = df["limit"].dropna()
    lim = float(limit.iloc[0]) if not limit.empty and limit.nunique() == 1 else None
    fig = signed_bars(df["name"].tolist(), df["net"].tolist(), title, unit="pct", limit=lim)
    if lim is None and not limit.empty:
        lim_vals = df["limit"].astype(float) * 100
        fig.add_trace(go.Scatter(x=lim_vals, y=df["name"], mode="markers", name="limite +",
                                 marker={"symbol": "line-ns-open", "size": 14,
                                         "color": fmt.NEGATIVE_COLOR}))
        fig.add_trace(go.Scatter(x=-lim_vals, y=df["name"], mode="markers", name="limite −",
                                 marker={"symbol": "line-ns-open", "size": 14,
                                         "color": fmt.NEGATIVE_COLOR}))
    return fig


def long_short_bars(df: pd.DataFrame, title: str) -> go.Figure:
    """Perna comprada e vendida (% NAV) por linha."""
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Bar(y=df["name"], x=df["long"] * 100, name="Comprado",
                             orientation="h", marker={"color": fmt.LONG_COLOR}))
        fig.add_trace(go.Bar(y=df["name"], x=df["short"] * 100, name="Vendido",
                             orientation="h", marker={"color": fmt.SHORT_COLOR}))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(autorange="reversed", automargin=True)
    fig.update_xaxes(ticksuffix="%")
    return _base(fig, title, height=max(240, 26 * len(df) + 90))


def value_added_chart(va: pd.DataFrame) -> go.Figure:
    """Retorno acumulado do CDP e da sombra e o valor agregado pelo PM de IA."""
    fig = go.Figure()
    if not va.empty:
        fig.add_trace(go.Scatter(x=va.index, y=va["cum_cdp"] * 100, name="CDP",
                                 line={"color": fmt.CDP_COLOR, "width": 2.5}))
        fig.add_trace(go.Scatter(x=va.index, y=va["cum_shadow"] * 100, name="Sombra só-quant",
                                 line={"color": fmt.SHADOW_COLOR, "width": 2, "dash": "dash"}))
        fig.add_trace(go.Bar(x=va.index, y=va["value_added"] * 100, name="Valor agregado",
                             marker={"color": [fmt.sign_color(v) for v in va["value_added"]]},
                             opacity=0.55))
    fig.update_yaxes(ticksuffix="%")
    return _base(fig, "CDP vs. sombra só-quant (acumulado no período)", y_title="%")


def position_history_chart(hist: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    if not hist.empty:
        x = pd.to_datetime(hist["date"])
        fig.add_trace(go.Bar(x=x, y=hist["day_pnl_usd"] / 1e3, name="P&L do dia (USD mil)",
                             marker={"color": [fmt.sign_color(v) for v in hist["day_pnl_usd"]]},
                             yaxis="y2", opacity=0.6))
        fig.add_trace(go.Scatter(x=x, y=hist["weight"] * 100, name="Peso (% NAV)",
                                 mode="lines+markers", line={"color": fmt.CDP_COLOR, "width": 2}))
    fig.update_layout(yaxis={"ticksuffix": "%", "title": "Peso"},
                      yaxis2={"overlaying": "y", "side": "right", "title": "USD mil",
                              "showgrid": False})
    return _base(fig, title)


def bucket_bars(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure(go.Bar(x=df["Faixa"], y=df["gross_share"].astype(float) * 100,
                           marker={"color": fmt.CDP_COLOR},
                           hovertemplate="%{x}: %{y:.1f}% do gross<extra></extra>"))
    fig.update_yaxes(ticksuffix="%")
    fig = _base(fig, title, height=280)
    fig.update_layout(hovermode="closest")
    return fig
