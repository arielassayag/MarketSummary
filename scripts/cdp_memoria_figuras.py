"""Gera as figuras editoriais a partir do relatório de avaliação por passagem."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

PAPEL = "#f8f4ec"
TINTA = "#1d1611"
TINTA_2 = "#4a3e33"
SUAVE = "#685a4b"
GRADE = "#e8e0d1"
ANIL = "#2b4596"
BASE = "#8b816f"
QUIXABA = "#6a3c5e"
VITÓRIA = "#e4e8f5"
PERDA = "#f6e0d6"
NEUTRO = "#efe8db"

SERIES = (
    ("Ontem · BM25 reconstruído", BASE),
    ("Hoje · mesmo BM25", QUIXABA),
    ("Hoje · memória com BM25", ANIL),
)
METRICAS = (
    ("completo_1", "Todos os grupos\nna 1ª passagem"),
    ("completo_3", "Todos os grupos\nnas 3 primeiras"),
    ("cobertura_3", "Cobertura média dos grupos\nnas 3 primeiras"),
)


def _percentual(valor: float) -> str:
    return f"{valor:.1%}".replace(".", ",")


def _pontos(valor: float) -> str:
    if abs(valor) < 1e-12:
        return "0,0 p.p."
    return f"{100 * valor:+.1f}".replace(".", ",").replace("-", "−") + " p.p."


def _cabecalho(fig, numero: str, titulo: str, subtitulo: str) -> None:
    fig.add_artist(Line2D((0.063, 0.937), (0.94, 0.94), transform=fig.transFigure,
                          color=ANIL, linewidth=1.45))
    fig.text(0.063, 0.905, f"CDP   /   MEMÓRIA AUDITÁVEL   /   {numero}", color=ANIL,
             fontsize=10, fontweight="bold")
    fig.text(0.063, 0.823, titulo, fontsize=24, fontweight="bold", fontfamily="DejaVu Serif",
             color=TINTA)
    fig.text(0.064, 0.772, subtitulo, fontsize=10.6, color=SUAVE)


def _rodape(fig, nota: str, fonte: str) -> None:
    fig.add_artist(Line2D((0.063, 0.937), (0.108, 0.108), transform=fig.transFigure,
                          color=GRADE, linewidth=1.15))
    fig.text(0.063, 0.072, nota, fontsize=8.6, color=TINTA_2)
    fig.text(0.063, 0.037, fonte, fontsize=8.3, color=SUAVE)


def _figura_recuperacao(series: list[dict], n: int, fonte: str):
    fig = plt.figure(figsize=(11.5, 6.55), facecolor=PAPEL)
    ontem, _, hibrida = (s["completo_3"] for s in series)
    delta = hibrida - ontem
    if delta > 1e-12:
        titulo = "Mais perguntas com evidência completa"
    elif delta < -1e-12:
        titulo = "Menos perguntas com evidência completa"
    else:
        titulo = "A taxa de recuperação completa ficou estável"
    _cabecalho(fig, "01", titulo,
               f"Comparação offline em {n} perguntas de evidência · "
               f"completa nas 3 primeiras {_pontos(delta)} ante ontem")
    ax = fig.add_axes((0.29, 0.208, 0.628, 0.458), facecolor=PAPEL)
    fig.legend(handles=[Patch(color=cor, label=nome) for nome, cor in SERIES],
               loc="upper left", bbox_to_anchor=(0.055, 0.728), ncol=3,
               frameon=False, handlelength=1.65, columnspacing=2.4, fontsize=10.3,
               labelcolor=TINTA_2)
    centros = (6.9, 4.05, 1.2)
    for centro, (chave, nome) in zip(centros, METRICAS, strict=True):
        ax.text(-0.022, centro, nome, transform=ax.get_yaxis_transform(), ha="right", va="center",
                color=TINTA_2, fontsize=10.5, fontweight="bold", linespacing=1.30)
        for indice, (serie, (_, cor)) in enumerate(zip(series, SERIES, strict=True)):
            y = centro + (1 - indice) * 0.64
            valor = serie[chave]
            ax.barh(y, valor, height=0.45, color=cor, zorder=2)
            ax.text(valor + 0.013, y, _percentual(valor), color=TINTA, va="center", fontsize=10,
                    fontweight="bold" if indice == 2 else "normal")
    for y in (2.62, 5.48):
        ax.axhline(y, color=GRADE, linewidth=0.8, zorder=0)
    ax.set(xlim=(0, 1.108), ylim=(0.1, 8.0), yticks=[],
           xticks=(0, 0.25, 0.5, 0.75, 1))
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.grid(axis="x", color=GRADE, linewidth=0.85, zorder=0)
    ax.tick_params(axis="x", labelcolor=SUAVE, labelsize=9, length=0, pad=7)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _rodape(fig, "Completa exige todos os grupos necessários. A cobertura é a média por pergunta.",
            fonte)
    return fig


def _figura_transicoes(linhas: list[tuple[str, dict]], controles: str, fonte: str):
    fig = plt.figure(figsize=(11.5, 6.35), facecolor=PAPEL)
    total = linhas[0][1]
    ganhou, perdeu = total["ganhou"], total["perdeu"]
    titulo = ("As mesmas perguntas tiveram evidência completa" if not (ganhou or perdeu)
              else "Ganhos e perdas na recuperação por pergunta")
    _cabecalho(fig, "02", titulo, f"As mesmas {sum(total.values())} perguntas estáticas nas duas versões · "
               f"{ganhou} passaram a ter evidência completa e {perdeu} perderam essa condição")
    ax = fig.add_axes((0.063, 0.26, 0.874, 0.408), facecolor=PAPEL)
    ax.set(xlim=(0, 11), ylim=(0, 3.62))
    ax.axis("off")
    ax.text(0.03, 3.43, "PERGUNTAS POR GRUPO", color=SUAVE, fontsize=8.9,
            fontweight="bold", va="center")
    colunas = (
        ("ganhou", "GANHOU", "incompleta → completa", VITÓRIA, ANIL),
        ("perdeu", "PERDEU", "completa → incompleta", PERDA, "#8f3417"),
        ("ambas", "COMPLETA NAS DUAS", "completa → completa", NEUTRO, TINTA_2),
        ("nenhuma", "INCOMPLETA NAS DUAS", "incompleta → incompleta", NEUTRO, TINTA_2),
    )
    for indice, (_, rotulo, transicao, _, cor) in enumerate(colunas):
        x = 3.64 + indice * 1.99
        ax.text(x, 3.47, rotulo, fontsize=8.7, color=cor, ha="center", fontweight="bold")
        ax.text(x, 3.19, transicao, fontsize=8.4, color=SUAVE, ha="center")
    for indice, (rotulo, valores) in enumerate(linhas):
        y = 2.53 - indice * 0.93
        ax.text(0.03, y + 0.12, rotulo, fontsize=11.4, color=TINTA, va="center",
                fontweight="bold" if indice == 0 else "normal")
        ax.text(0.03, y - 0.19, f"{sum(valores.values())} perguntas", fontsize=8.8,
                color=SUAVE, va="center")
        for coluna, (chave, _, _, fundo, cor) in enumerate(colunas):
            x = 3.64 + coluna * 1.99
            ax.add_patch(Rectangle((x - 0.90, y - 0.35), 1.80, 0.70, color=fundo, linewidth=0))
            ax.text(x, y, str(valores[chave]), color=cor, ha="center", va="center",
                    fontsize=14.6, fontweight="bold")
    if controles:
        fig.text(0.063, 0.191, "CONTROLES", fontsize=9.1, color=ANIL, fontweight="bold")
        fig.text(0.178, 0.190, controles, fontsize=9.0, color=TINTA_2)
    _rodape(fig, "Transições do BM25 reconstruído para memória com BM25, nas 3 primeiras passagens.",
            fonte)
    return fig


def _salvar(fig, pasta: Path, nome: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    fig.savefig(pasta / f"{nome}.png", dpi=200, facecolor=PAPEL)
    fig.savefig(pasta / f"{nome}.svg", facecolor=PAPEL, metadata={"Date": None})
    plt.close(fig)


def _transicoes(casos: list[dict]) -> dict[str, int]:
    contagem = dict.fromkeys(("ganhou", "perdeu", "ambas", "nenhuma"), 0)
    for caso in casos:
        modos = caso["modos"]
        antes = modos["ontem"]["completo_3"]
        depois = modos["memoria"]["completo_3"]
        if antes:
            chave = "ambas" if depois else "perdeu"
        else:
            chave = "ganhou" if depois else "nenhuma"
        contagem[chave] += 1
    return contagem


def _controles(casos: list[dict]) -> str:
    resultados = []
    for tipo, rotulo in (("estado_atual", "estado atual"), ("fora_escopo", "fora do escopo")):
        subset = [c["modos"] for c in casos if c["tipo"] == tipo]
        if subset:
            anterior = sum(c["ontem"]["abstencao"] for c in subset)
            atual = sum(c["memoria"]["abstencao"] for c in subset)
            resultados.append(f"{rotulo} {anterior}/{len(subset)} → {atual}/{len(subset)}")
    return "Abstenções · " + "   /   ".join(resultados) if resultados else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("relatorio", type=Path, help="relatório JSON de recuperação por passagem")
    parser.add_argument("--saida", type=Path, default=Path("outputs/cdp-memoria"),
                        help="pasta para PNG e SVG")
    args = parser.parse_args()
    relatorio = json.loads(args.relatorio.read_text(encoding="utf-8"))
    if relatorio["limite"] != 3:
        parser.error("as figuras usam o relatório com limite de três passagens")
    casos = relatorio["casos"]
    positivos = [c for c in casos if c["tipo"] == "evidencia"]
    if not positivos:
        parser.error("o relatório precisa de perguntas com evidência esperada")
    series = [{k: mean(c["modos"][modo][k] for c in positivos) for k, _ in METRICAS}
              for modo in ("ontem", "direta", "memoria")]
    linhas = [("Todas", _transicoes(positivos)),
              ("Um grupo de evidência", _transicoes([c for c in positivos if c["grupos"] == 1])),
              ("Dois ou mais grupos", _transicoes([c for c in positivos if c["grupos"] > 1]))]
    revisoes = relatorio["revisoes"]
    corpus = Path(relatorio.get("corpus", "")).stem
    amostra = {"avaliacao_replica": "réplica", "avaliacao_reservada": "primeira amostra"}.get(
        corpus, "ensaio"
    )
    fonte = (f"CDP · {amostra} · ontem {revisoes['ontem'][:8]} · hoje {revisoes['hoje'][:8]} · código "
             f"{revisoes['codigo'][:8]} · corpus {revisoes['corpus'][:8]} · corte {relatorio['data']}")
    with mpl.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "svg.hashsalt": "cdp-memoria-figuras"}):
        _salvar(_figura_recuperacao(series, len(positivos), fonte),
                args.saida, "01-recuperacao-por-passagem")
        _salvar(_figura_transicoes(linhas, _controles(casos), fonte),
                args.saida, "02-transicoes-pareadas")


if __name__ == "__main__":
    main()
