"""Gráficos matplotlib (sem seaborn) com a identidade visual do AI Notes.

Resolução mínima 1600×900, títulos em português, valores nas barras quando
legíveis, V1/V2 identificados, n informado, nota de que o resultado é
específico da tarefa e fonte curta "Experimento AI Notes".
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, cast

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ORANGE = "#FF6200"
GRAPHITE = "#1C252E"
LIGHT_BLUE = "#C3EBF7"
WHITE = "#FFFFFF"

# Sistema visual refinado (gráficos 01 e 06): tons derivados da identidade.
FONT_STACK = ["Helvetica Neue", "Arial", "DejaVu Sans"]
GRID_GRAY = "#E4E9ED"
SPINE_GRAY = "#C7D0D6"
TEXT_SOFT = "#5F6B74"
ARROW_GRAY = "#C6CFD6"
ORANGE_TINT = "#FFE3D0"
ORANGE_TEXT = "#8F3D00"
GRAY_TINT = "#EAEEF2"

FOOTER = "Experimento AI Notes, execução em {date}. Resultado específico desta tarefa, destes casos, prompts e modelos (n={n})."


def _style_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(WHITE)
    ax.figure.set_facecolor(WHITE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(GRAPHITE)
    ax.spines["bottom"].set_color(GRAPHITE)
    ax.tick_params(colors=GRAPHITE)


def _finish(fig: plt.Figure, ax: plt.Axes, out_path: Path, n: int, date: str) -> None:
    fig.text(
        0.01,
        0.01,
        FOOTER.format(date=date, n=n),
        fontsize=8,
        color=GRAPHITE,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=100)  # figsize 16x9 -> 1600x900
    plt.close(fig)


def _bar_labels(ax: plt.Axes, bars: list, fmt: str = "{:.1f}") -> None:
    for bar in bars:
        h = bar.get_height()
        if h is None:
            continue
        ax.annotate(
            fmt.format(h),
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=GRAPHITE,
        )


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["label"] = out["model_id"].str.replace("/", "\n", regex=False)
    return out


def _pivot_prompts(df: pd.DataFrame, value: str) -> pd.DataFrame:
    pivot = df.pivot_table(index="model_id", columns="prompt_version", values=value, aggfunc="first")
    for col in ("v1", "v2"):
        if col not in pivot:
            pivot[col] = float("nan")
    return pivot


# --- sistema visual dos gráficos 01 e 06 --------------------------------------


def _design_rc() -> dict[str, Any]:
    return {
        "font.family": "sans-serif",
        "font.sans-serif": FONT_STACK,
        "text.color": GRAPHITE,
        "axes.labelcolor": TEXT_SOFT,
        "axes.edgecolor": SPINE_GRAY,
        "xtick.color": TEXT_SOFT,
        "ytick.color": GRAPHITE,
        "figure.facecolor": WHITE,
        "axes.facecolor": WHITE,
        "savefig.facecolor": WHITE,
    }


def _ptbr(x: float, nd: int = 1) -> str:
    """Número no padrão pt-BR (vírgula decimal)."""
    return f"{x:.{nd}f}".replace(".", ",")


def _ptbr_signed(x: float, nd: int = 1) -> str:
    """Número com sinal explícito e menos tipográfico."""
    return f"{x:+.{nd}f}".replace(".", ",").replace("-", "\u2212")


_MODEL_SPECIAL = {"gpt": "GPT", "ai": "AI", "deepseek": "DeepSeek"}


def _pretty_model(model_id: str) -> str:
    """'openai/gpt-5.5' -> 'GPT 5.5'; 'anthropic/claude-sonnet-5' -> 'Claude Sonnet 5'."""
    parts: list[str] = []
    for tok in model_id.split("/")[-1].split("-"):
        low = tok.lower()
        if low in _MODEL_SPECIAL:
            parts.append(_MODEL_SPECIAL[low])
        elif low.startswith("v") and low[1:].isdigit():
            parts.append(low.upper())
        elif tok and tok[0].isalpha():
            parts.append(tok[0].upper() + tok[1:])
        else:
            parts.append(tok)
    return " ".join(parts)


def _weighted_pivot(df: pd.DataFrame, value: str) -> pd.DataFrame:
    """Média de `value` por modelo×prompt ponderada por n_outputs (consolida dev + holdout)."""
    sub = df[df[value].notna()]
    rows: list[dict[str, object]] = []
    for (model, prompt), t in sub.groupby(["model_id", "prompt_version"]):
        weights = t["n_outputs"].astype(float)
        total = float(weights.sum())
        values = t[value].astype(float)
        pooled = float((values * weights).sum() / total) if total > 0 else float(values.mean())
        rows.append({"model_id": model, "prompt_version": prompt, "value": pooled})
    pivot = pd.DataFrame(rows).pivot(index="model_id", columns="prompt_version", values="value") if rows else pd.DataFrame()
    for col in ("v1", "v2"):
        if col not in pivot:
            pivot[col] = float("nan")
    return pivot


def _pivot_finite(pivot: pd.DataFrame) -> list[float]:
    return [float(v) for v in pivot.to_numpy(dtype=float).ravel() if v == v]


def _legend_handles() -> list[Line2D]:
    return [
        Line2D([], [], marker="o", linestyle="none", markersize=14, markerfacecolor=LIGHT_BLUE,
               markeredgecolor=GRAPHITE, markeredgewidth=1.4, label="Prompt V1 (baseline)"),
        Line2D([], [], marker="o", linestyle="none", markersize=16.5, markerfacecolor=ORANGE,
               markeredgecolor=GRAPHITE, markeredgewidth=1.4, label="Prompt V2 (revisado)"),
    ]


def _design_footer(fig: plt.Figure, out_path: Path, n: int, date: str) -> None:
    fig.text(0.012, 0.018, FOOTER.format(date=date, n=n), fontsize=11.5, color=TEXT_SOFT, ha="left")
    fig.savefig(out_path, dpi=150)  # figsize 16x9 -> 2400x1350
    plt.close(fig)


_Rect = tuple[float, float, float, float]


def _rects_overlap(a: _Rect, b: _Rect, pad: float = 6.0) -> bool:
    return not (a[2] + pad < b[0] or a[0] - pad > b[2] or a[3] + pad < b[1] or a[1] - pad > b[3])


_LABEL_CANDIDATES: list[tuple[float, float, str]] = [
    (18, 7, "left"),
    (18, -9, "left"),
    (-18, 7, "right"),
    (-18, -9, "right"),
    (0, 21, "center"),
    (0, -23, "center"),
    (30, 18, "left"),
    (-30, -20, "right"),
    (34, -22, "left"),
    (-34, 22, "right"),
]


def _annotate_points(fig: plt.Figure, ax: plt.Axes, items: list[tuple[float, float, str]]) -> None:
    """Anota (x, y, texto) escolhendo, para cada rótulo, o deslocamento sem sobreposição."""
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    pt2px = fig.dpi / 72
    dot_r = math.sqrt(500 / math.pi) * pt2px  # raio px do maior marcador (s=500)
    label_w = 0.56 * 13.5 * max(len(t) for _, _, t in items) * pt2px
    label_h = 13.5 * 1.4 * pt2px
    ax_box = ax.get_window_extent(renderer)

    dot_boxes: list[_Rect] = []
    for x, y, _ in items:
        cx, cy = ax.transData.transform((x, y))
        dot_boxes.append((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r))

    placed: list[_Rect] = []
    for x, y, text in sorted(items, key=lambda p: (-p[1], p[0])):
        cx, cy = ax.transData.transform((x, y))
        chosen: tuple[float, float, str] | None = None
        for dx, dy, ha in _LABEL_CANDIDATES:
            ox, oy = dx * pt2px, dy * pt2px
            x0 = cx + ox + (0.0 if ha == "center" else (6.0 if ha == "left" else -6.0))
            lx0 = x0 - label_w / 2 if ha == "center" else (x0 if ha == "left" else x0 - label_w)
            lx1 = lx0 + label_w
            ly0, ly1 = cy + oy - label_h / 2, cy + oy + label_h / 2
            box: _Rect = (lx0, ly0, lx1, ly1)
            if lx0 < ax_box.x0 + 4 or lx1 > ax_box.x1 - 4 or ly0 < ax_box.y0 + 4 or ly1 > ax_box.y1 - 4:
                continue
            if any(_rects_overlap(box, b) for b in dot_boxes):
                continue
            if any(_rects_overlap(box, b) for b in placed):
                continue
            chosen = (dx, dy, ha)
            placed.append(box)
            break
        if chosen is None:
            chosen = (18, -9, "left")
            cx_, cy_ = cx, cy
            x0 = cx_ + 18 * pt2px + 6.0
            placed.append((x0, cy_ - 9 * pt2px - label_h / 2, x0 + label_w, cy_ - 9 * pt2px + label_h / 2))
        dx, dy, ha = chosen
        ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va="center",
                    fontsize=13.5, color=GRAPHITE, zorder=6)


def chart_nota_media(df: pd.DataFrame, out_path: Path, date: str) -> None:
    """Dumbbell por modelo: nota média ponderada (dev + holdout), V1 -> V2, com Δ destacado."""
    with matplotlib.rc_context(_design_rc()):  # type: ignore[arg-type]
        pivot = _weighted_pivot(df, "final_score_mean")
        n_by_model = df.groupby("model_id")["n_outputs"].sum()
        finite = _pivot_finite(pivot)
        if not finite:
            return
        lo = max(0.0, math.floor((min(finite) - 8) / 10) * 10)
        hi = min(104.0, math.ceil((max(finite) + 3) / 10) * 10)
        if hi - lo < 20:
            hi = lo + 20

        order = (
            pivot.assign(_sort=pivot["v2"].fillna(pivot["v1"]).astype(float))
            .sort_values("_sort", ascending=False)
            .index.tolist()
        )

        fig, ax = plt.subplots(figsize=(16, 9))
        fig.subplots_adjust(left=0.15, right=0.96, top=0.79, bottom=0.14)
        ax.set_facecolor(WHITE)
        fig.set_facecolor(WHITE)

        for i, model in enumerate(order):
            y = float(i)
            v1, v2 = cast(float, pivot.at[model, "v1"]), cast(float, pivot.at[model, "v2"])
            has_v1, has_v2 = v1 == v1, v2 == v2
            if has_v1 and has_v2 and v2 != v1:
                ax.annotate(
                    "",
                    xy=(v2, y),
                    xytext=(v1, y),
                    arrowprops={
                        "arrowstyle": "-|>",
                        "color": ARROW_GRAY,
                        "lw": 2.4,
                        "shrinkA": 13,
                        "shrinkB": 15,
                        "mutation_scale": 18,
                    },
                    zorder=2,
                )
                delta = v2 - v1
                improved = delta > 0
                ax.text(
                    (v1 + v2) / 2,
                    y - 0.34,
                    f"Δ {_ptbr_signed(delta)}",
                    ha="center",
                    va="center",
                    fontsize=13.5,
                    fontweight="bold",
                    color=ORANGE_TEXT if improved else GRAPHITE,
                    bbox={
                        "boxstyle": "round,pad=0.38",
                        "facecolor": ORANGE_TINT if improved else GRAY_TINT,
                        "edgecolor": "none",
                    },
                    zorder=5,
                )
            if has_v1:
                ax.scatter([v1], [y], s=360, facecolor=LIGHT_BLUE, edgecolor=GRAPHITE, linewidth=1.6, zorder=4)
                ax.annotate(_ptbr(v1), (v1, y), xytext=(-15, 0), textcoords="offset points",
                            ha="right", va="center", fontsize=15, color=TEXT_SOFT, zorder=5)
            if has_v2:
                ax.scatter([v2], [y], s=560, facecolor=ORANGE, edgecolor=GRAPHITE, linewidth=1.6, zorder=5)
                ax.annotate(_ptbr(v2), (v2, y), xytext=(17, 0), textcoords="offset points",
                            ha="left", va="center", fontsize=17, fontweight="bold", color=GRAPHITE, zorder=6)
            ax.text(
                lo + (hi - lo) * 0.012,
                y + 0.36,
                f"{model} · n={int(n_by_model.get(model, 0))} saídas",
                ha="left",
                va="center",
                fontsize=12.5,
                color=TEXT_SOFT,
            )

        ax.set_xlim(lo, hi)
        ax.set_ylim(len(order) - 0.38, -0.95)
        ax.set_xticks([float(t) for t in range(0, 101, 10) if lo <= t <= hi])
        ax.set_yticks([float(i) for i in range(len(order))])
        ax.set_yticklabels([_pretty_model(m) for m in order], fontsize=18)
        for lab in ax.get_yticklabels():
            lab.set_fontweight("bold")
            lab.set_color(GRAPHITE)
        ax.tick_params(axis="y", length=0, pad=14)
        ax.tick_params(axis="x", length=4, color=SPINE_GRAY, labelsize=14)
        ax.grid(axis="x", color=GRID_GRAY, linewidth=1.1)
        ax.set_axisbelow(True)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(SPINE_GRAY)
        ax.set_xlabel("Nota média (final score, 0–100; eixo truncado)", fontsize=14.5, color=TEXT_SOFT, labelpad=10)
        ax.legend(
            handles=_legend_handles(),
            loc="upper left",
            frameon=False,
            fontsize=14.5,
            borderaxespad=0.2,
            handletextpad=0.4,
            labelspacing=0.6,
        )
        ax.set_title("Nota média por modelo", loc="left", fontsize=30, fontweight="bold", color=GRAPHITE, pad=42)
        ax.text(
            0.0,
            1.055,
            "Prompt revisado (V2) contra o baseline (V1) · médias ponderadas dos splits dev + holdout",
            transform=ax.transAxes,
            fontsize=15.5,
            color=TEXT_SOFT,
            va="bottom",
        )
        _design_footer(fig, out_path, int(df["n_outputs"].sum()), date)


def chart_taxa_aprovacao(df: pd.DataFrame, out_path: Path, date: str) -> None:
    pivot = _pivot_prompts(df, "hard_pass_rate") * 100
    n_by_model = df.groupby("model_id")["n_outputs"].sum()
    fig, ax = plt.subplots(figsize=(16, 9))
    _style_ax(ax)
    y = range(len(pivot))
    height = 0.38
    ax.barh([i + height / 2 for i in y], pivot["v1"], height, label="Prompt V1", color=LIGHT_BLUE, edgecolor=GRAPHITE)
    ax.barh([i - height / 2 for i in y], pivot["v2"], height, label="Prompt V2", color=ORANGE, edgecolor=GRAPHITE)
    ax.set_yticks(list(y))
    ax.set_yticklabels([m.split("/")[-1] + f" (n={int(n_by_model.get(m, 0))})" for m in pivot.index])
    ax.set_xlabel("Taxa de aprovação factual (sem hard fail) (%)")
    ax.set_title("Taxa de aprovação factual por modelo", fontsize=16, color=GRAPHITE, pad=14)
    for i, (a, b) in enumerate(zip(pivot["v1"], pivot["v2"], strict=True)):
        if a == a:
            ax.text(a + 1, i + height / 2, f"{a:.0f}%", va="center", fontsize=9, color=GRAPHITE)
        if b == b:
            ax.text(b + 1, i - height / 2, f"{b:.0f}%", va="center", fontsize=9, color=GRAPHITE)
    ax.set_xlim(0, 110)
    ax.legend(frameon=False, loc="lower right")
    _finish(fig, ax, out_path, int(df["n_outputs"].sum()), date)


def chart_delta_prompt(delta_df: pd.DataFrame, out_path: Path, date: str) -> None:
    sub = delta_df[delta_df["split"].isin(["dev", "holdout"])].copy()
    sub["label"] = sub["model_id"].str.split("/").str[-1] + " (" + sub["split"] + ")"
    colors = [ORANGE if v >= 0 else GRAPHITE for v in sub["delta_final_score"]]
    fig, ax = plt.subplots(figsize=(16, 9))
    _style_ax(ax)
    bars = ax.bar(sub["label"], sub["delta_final_score"], color=colors, edgecolor=GRAPHITE)
    _bar_labels(ax, list(bars), "{:+.1f}")
    ax.axhline(0, color=GRAPHITE, linewidth=1)
    ax.set_ylabel("Δ nota média (V2 - V1), pareado por caso")
    ax.set_title("Efeito da revisão do prompt (V2 vs V1), com IC 95% por bootstrap", fontsize=16, color=GRAPHITE, pad=14)
    for i, (lo, hi) in enumerate(zip(sub["delta_ci95_low"], sub["delta_ci95_high"], strict=True)):
        ax.errorbar(i, sub["delta_final_score"].iloc[i], yerr=[[sub["delta_final_score"].iloc[i] - lo], [hi - sub["delta_final_score"].iloc[i]]], color=GRAPHITE, capsize=4, fmt="none")
    _finish(fig, ax, out_path, int(sub["n_cases"].sum()), date)


def chart_erros_criticos(df: pd.DataFrame, out_path: Path, date: str) -> None:
    sub = df.copy()
    sub["label"] = sub["failure_category"] + " | " + sub["prompt_version"].str.upper()
    agg = sub.groupby(["failure_category", "prompt_version"], as_index=False)["count"].sum()
    pivot = agg.pivot(index="failure_category", columns="prompt_version", values="count").fillna(0)
    fig, ax = plt.subplots(figsize=(16, 9))
    _style_ax(ax)
    idx = range(len(pivot))
    width = 0.38
    b1 = ax.bar([i - width / 2 for i in idx], pivot.get("v1", 0), width, label="Prompt V1", color=LIGHT_BLUE, edgecolor=GRAPHITE)
    b2 = ax.bar([i + width / 2 for i in idx], pivot.get("v2", 0), width, label="Prompt V2", color=ORANGE, edgecolor=GRAPHITE)
    _bar_labels(ax, [*b1, *b2], "{:.0f}")
    ax.set_xticks(list(idx))
    ax.set_xticklabels(pivot.index, rotation=30, ha="right")
    ax.set_ylabel("Ocorrências")
    ax.set_title("Erros críticos e violações por categoria", fontsize=16, color=GRAPHITE, pad=14)
    ax.legend(frameon=False)
    _finish(fig, ax, out_path, int(sub["count"].sum()), date)


def chart_por_regime(df: pd.DataFrame, out_path: Path, date: str) -> None:
    sub = df[df["split"].str.contains("|", regex=False)].copy()
    if sub.empty:
        sub = df.copy()
        sub["regime"] = "total"
    sub["regime"] = sub["split"].str.split("|").str[-1]
    sub["label"] = sub["model_id"].str.split("/").str[-1] + "\n" + sub["regime"]
    fig, ax = plt.subplots(figsize=(16, 9))
    _style_ax(ax)
    bars = ax.bar(sub["label"], sub["delta_final_score"], color=[ORANGE if v >= 0 else GRAPHITE for v in sub["delta_final_score"]], edgecolor=GRAPHITE)
    _bar_labels(ax, list(bars), "{:+.1f}")
    ax.axhline(0, color=GRAPHITE, linewidth=1)
    ax.set_ylabel("Δ nota média (V2 - V1)")
    ax.set_title("Resultado por regime de mercado (V2 vs V1)", fontsize=16, color=GRAPHITE, pad=14)
    ax.tick_params(axis="x", labelsize=8)
    _finish(fig, ax, out_path, int(sub["n_cases"].sum()), date)


def chart_custo_qualidade(df: pd.DataFrame, out_path: Path, date: str) -> None:
    """Dispersão custo × qualidade com médias ponderadas (dev + holdout) e movimento V1 -> V2."""
    with matplotlib.rc_context(_design_rc()):  # type: ignore[arg-type]
        cost = _weighted_pivot(df, "cost_mean_usd")
        score = _weighted_pivot(df, "final_score_mean")
        models = [m for m in score.index if m in cost.index]

        points: list[tuple[float, float, str, str]] = []  # x, y, model, prompt_version
        for model in models:
            for prompt in ("v1", "v2"):
                c, s = cast(float, cost.at[model, prompt]), cast(float, score.at[model, prompt])
                if c == c and s == s:
                    points.append((c, s, model, prompt))
        if not points:
            return

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_hi = max(xs) * 1.16
        y_lo = math.floor((min(ys) - 4) / 5) * 5
        y_hi = math.ceil((max(ys) + 4) / 5) * 5

        fig, ax = plt.subplots(figsize=(16, 9))
        fig.subplots_adjust(left=0.075, right=0.965, top=0.79, bottom=0.13)
        ax.set_facecolor(WHITE)
        fig.set_facecolor(WHITE)

        # Fronteira de eficiência: pontos não dominados (custo menor, nota maior).
        frontier: list[tuple[float, float]] = []
        best = -math.inf
        for x, y in sorted(zip(xs, ys, strict=True)):
            if y > best:
                frontier.append((x, y))
                best = y
        if len(frontier) >= 2:
            fx = [p[0] for p in frontier]
            fy = [p[1] for p in frontier]
            ax.plot(fx, fy, ls=(0, (6, 5)), lw=1.7, color=ARROW_GRAY, zorder=1)
            seg = min(1, len(frontier) - 2)
            ax.annotate(
                "fronteira de eficiência",
                ((fx[seg] + fx[seg + 1]) / 2, (fy[seg] + fy[seg + 1]) / 2),
                xytext=(0, -16),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=12.5,
                style="italic",
                color=TEXT_SOFT,
                zorder=2,
            )

        by_model: dict[str, dict[str, tuple[float, float]]] = {}
        for x, y, model, prompt in points:
            by_model.setdefault(model, {})[prompt] = (x, y)
        for model in models:
            pair = by_model.get(model, {})
            if "v1" in pair and "v2" in pair and pair["v1"] != pair["v2"]:
                ax.annotate(
                    "",
                    xy=pair["v2"],
                    xytext=pair["v1"],
                    arrowprops={
                        "arrowstyle": "-|>",
                        "color": ARROW_GRAY,
                        "lw": 2.2,
                        "shrinkA": 14,
                        "shrinkB": 16,
                        "mutation_scale": 17,
                        "connectionstyle": "arc3,rad=0.18",
                    },
                    zorder=3,
                )

        for x, y, _model, prompt in points:
            if prompt == "v1":
                ax.scatter([x], [y], s=330, facecolor=LIGHT_BLUE, edgecolor=GRAPHITE, linewidth=1.7, zorder=4)
            else:
                ax.scatter([x], [y], s=500, facecolor=ORANGE, edgecolor=GRAPHITE, linewidth=1.7, zorder=5)

        _annotate_points(
            fig,
            ax,
            [(x, y, f"{_pretty_model(m)} · {'V2' if p == 'v2' else 'V1'}") for x, y, m, p in points],
        )

        ax.set_xlim(0.0, x_hi)
        ax.set_ylim(y_lo, y_hi)
        ax.set_xticks([i * 0.01 for i in range(int(x_hi / 0.01) + 1)])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: _ptbr(v, 2)))
        ax.set_yticks([float(t) for t in range(int(y_lo), int(y_hi) + 1, 5)])
        ax.tick_params(labelsize=14, length=4, color=SPINE_GRAY)
        ax.grid(color=GRID_GRAY, linewidth=1.1)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.set_xlabel("Custo médio por comentário (US$)", fontsize=14.5, color=TEXT_SOFT, labelpad=10)
        ax.set_ylabel("Nota média (final score, 0–100)", fontsize=14.5, color=TEXT_SOFT, labelpad=10)
        ax.legend(
            handles=_legend_handles(),
            loc="upper left",
            frameon=False,
            fontsize=14.5,
            borderaxespad=0.2,
            handletextpad=0.4,
            labelspacing=0.6,
        )
        ax.text(
            0.99,
            0.035,
            "melhor ↖ (nota alta, custo baixo)",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=12.5,
            style="italic",
            color=TEXT_SOFT,
            fontfamily="DejaVu Sans",
        )
        ax.set_title("Custo versus qualidade", loc="left", fontsize=30, fontweight="bold", color=GRAPHITE, pad=42)
        ax.text(
            0.0,
            1.055,
            "Custo médio por comentário × nota média final · médias ponderadas (dev + holdout) · seta = V1 → V2",
            transform=ax.transAxes,
            fontsize=15.5,
            color=TEXT_SOFT,
            va="bottom",
            fontfamily="DejaVu Sans",
        )
        _design_footer(fig, out_path, int(df["n_outputs"].sum()), date)


def chart_vitorias_pareadas(pairwise: pd.DataFrame, out_path: Path, date: str) -> None:
    agg = pairwise.groupby(["model_id", "outcome"], as_index=False).size()
    pivot = agg.pivot(index="model_id", columns="outcome", values="size").fillna(0)
    for col in ("v2_win", "v1_win", "tie", "unstable"):
        if col not in pivot:
            pivot[col] = 0
    fig, ax = plt.subplots(figsize=(16, 9))
    _style_ax(ax)
    models = [m.split("/")[-1] for m in pivot.index]
    x = range(len(pivot))
    bottom = [0.0] * len(pivot)
    palette = {"v2_win": ORANGE, "v1_win": LIGHT_BLUE, "tie": "#E8E8E8", "unstable": GRAPHITE}
    for col in ("v2_win", "v1_win", "tie", "unstable"):
        bars = ax.bar(x, pivot[col], 0.6, bottom=bottom, label=col, color=palette[col], edgecolor=WHITE)
        for i, bar in enumerate(bars):
            if bar.get_height() > 0:
                ax.annotate(f"{bar.get_height():.0f}", (bar.get_x() + bar.get_width() / 2, bottom[i] + bar.get_height() / 2), ha="center", va="center", fontsize=9, color=GRAPHITE if col != "unstable" else WHITE)
        bottom = [b + h for b, h in zip(bottom, pivot[col], strict=True)]
    ax.set_xticks(list(x))
    ax.set_xticklabels(models)
    ax.set_ylabel("Pares (modelo, caso, repetição)")
    ax.set_title("Comparação pareada V1 x V2 (judge cego, duas ordens)", fontsize=16, color=GRAPHITE, pad=14)
    ax.legend(frameon=False)
    _finish(fig, ax, out_path, int(pivot.sum().sum()), date)


def generate_all_charts(
    summary: pd.DataFrame,
    delta: pd.DataFrame,
    failures: pd.DataFrame,
    pairwise: pd.DataFrame | None,
    out_dir: Path,
    date: str,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        (chart_nota_media, summary, out_dir / "01_nota_media_por_modelo.png"),
        (chart_taxa_aprovacao, summary, out_dir / "02_taxa_aprovacao_factual.png"),
        (chart_delta_prompt, delta, out_dir / "03_delta_prompt_v2_vs_v1.png"),
        (chart_erros_criticos, failures, out_dir / "04_erros_criticos_por_categoria.png"),
        (chart_por_regime, delta, out_dir / "05_resultado_por_regime.png"),
        (chart_custo_qualidade, summary, out_dir / "06_custo_versus_qualidade.png"),
    ]
    written: list[Path] = []
    for fn, data, path in paths:
        if data is None or len(data) == 0:
            continue
        fn(data, path, date)
        written.append(path)
    if pairwise is not None and len(pairwise):
        pw_path = out_dir / "07_vitorias_pareadas.png"
        chart_vitorias_pareadas(pairwise, pw_path, date)
        written.append(pw_path)
    return written
