"""Gera duas figuras do ensaio isolado de consolidação da memória do CDP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cdp_memoria_figuras import (
    ANIL,
    BASE,
    GRADE,
    NEUTRO,
    PAPEL,
    PERDA,
    QUIXABA,
    SUAVE,
    TINTA,
    TINTA_2,
    VITÓRIA,
    Patch,
    Rectangle,
    _cabecalho,
    _percentual,
    _rodape,
    _salvar,
    mpl,
    plt,
)

SERIES = (
    ("direta", "Busca direta", BASE),
    ("memoria", "Memória antes da revisão", QUIXABA),
    ("apos_revisao", "Memória após revisão", ANIL),
)
ACOES = {
    "promocao": ("Promoção", "Candidata conferida"),
    "renovacao": ("Renovação", "Validade vencida"),
    "substituicao": ("Substituição", "Trecho antigo removido"),
    "fusao": ("Fusão", "Notas duplicadas"),
}


def _fonte(r: dict) -> str:
    rev = r["revisoes"]
    return (f"DADOS SIMULADOS · fontes {rev['fontes'][:8]} · código {rev['codigo'][:8]} · "
            f"corpus {rev['corpus'][:8]} · referência {r['data']}")


def _recuperacao(r: dict):
    fig = plt.figure(figsize=(11.6, 6.25), facecolor=PAPEL)
    antes = r["resumo"]["memoria"]
    depois = r["resumo"]["apos_revisao"]
    n = antes["perguntas_com_evidencia"]
    _cabecalho(fig, "01", "Evidência antes e depois da revisão",
               f"Nas cinco primeiras passagens, {antes['completo_5']}/{n} → "
               f"{depois['completo_5']}/{n} perguntas com todos os grupos recuperados")
    fig.legend(handles=[Patch(color=cor, label=nome) for _, nome, cor in SERIES],
               loc="upper left", bbox_to_anchor=(0.055, 0.727), ncol=3, frameon=False,
               handlelength=1.65, columnspacing=2.15, fontsize=10.3, labelcolor=TINTA_2)
    ax = fig.add_axes((0.29, 0.177, 0.635, 0.49), facecolor=PAPEL)
    metricas = (
        ("completo_3", "Recuperação completa\naté 3 passagens"),
        ("completo_5", "Recuperação completa\naté 5 passagens"),
        ("cobertura_media_5", "Cobertura média\naté 5 passagens"),
    )
    for centro, (chave, rotulo) in zip((6.9, 4.05, 1.2), metricas, strict=True):
        ax.text(-0.022, centro, rotulo, transform=ax.get_yaxis_transform(), ha="right",
                va="center", color=TINTA_2, fontsize=10.5, fontweight="bold")
        for i, (modo, _, cor) in enumerate(SERIES):
            y = centro + (1 - i) * 0.64
            medicao = r["resumo"][modo][chave]
            valor = medicao / n if chave.startswith("completo") else medicao
            rotulo_valor = f"{medicao}/{n}" if chave.startswith("completo") else _percentual(valor)
            ax.barh(y, valor, height=0.44, color=cor, zorder=2)
            ax.text(valor + 0.015, y, rotulo_valor, va="center", color=TINTA, fontsize=10,
                    fontweight="bold" if i == 2 else "normal")
    for y in (2.62, 5.48):
        ax.axhline(y, color=GRADE, linewidth=0.8, zorder=0)
    ax.set(xlim=(0, 1.13), ylim=(0.05, 8.05), yticks=[],
           xticks=(0, 0.25, 0.5, 0.75, 1), xticklabels=("0%", "25%", "50%", "75%", "100%"))
    ax.grid(axis="x", color=GRADE, linewidth=0.85, zorder=0)
    ax.tick_params(axis="x", labelcolor=SUAVE, labelsize=9, length=0, pad=7)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _rodape(fig, "Mesmas perguntas, fontes canônicas e orçamento. A revisão segue decisões "
            "editoriais predefinidas.", _fonte(r))
    return fig


def _sim(valor: bool | None) -> str:
    return "sim" if valor else "não"


def _consolidacao(r: dict):
    c = r["consolidacao"]
    fig = plt.figure(figsize=(11.6, 6.45), facecolor=PAPEL)
    n = len(c["decisoes"])
    detectados = sum(d["diagnosticada"] for d in c["decisoes"])
    concluidos = sum(d["elegivel_apos_revisao"] for d in c["decisoes"])
    _cabecalho(fig, "02", "O que a consolidação devolveu à busca",
               f"Fila detectou {detectados}/{n} casos de revisão · "
               f"{concluidos}/{n} geraram notas elegíveis após a revisão simulada")
    ax = fig.add_axes((0.063, 0.269, 0.875, 0.45), facecolor=PAPEL)
    ax.set(xlim=(0, 10.9), ylim=(0, 4.62))
    ax.axis("off")
    colunas = (("CASO REVISADO", 0.03), ("FILA DETECTOU", 4.27),
               ("NOTA ELEGÍVEL", 6.62), ("EVIDÊNCIA COMPLETA", 9.41))
    for titulo, x in colunas:
        ax.text(x, 4.38, titulo, fontsize=8.9, color=SUAVE, va="center",
                ha="left" if x < 1 else "center", fontweight="bold")
    casos = {id_: caso for caso in r["casos"] for id_ in caso["notas_esperadas_apos_revisao"]}
    for i, d in enumerate(c["decisoes"]):
        y = 3.61 - i * 0.91
        acao, detalhe = ACOES[d["tipo"]]
        ax.text(0.03, y + 0.12, acao, fontsize=11, color=TINTA, va="center", fontweight="bold")
        ax.text(0.03, y - 0.18, detalhe, fontsize=9.1, color=SUAVE, va="center")
        ids = d["notas_resultantes"]
        antes = all(id_ in c["elegiveis_antes"] for id_ in ids)
        depois = d["elegivel_apos_revisao"]
        alvo = casos.get(ids[0])
        m = alvo["modos"] if alvo else {}
        ev_antes = m.get("memoria", {}).get("completo_5")
        ev_depois = m.get("apos_revisao", {}).get("completo_5")
        dados = (
            (4.27, _sim(d["diagnosticada"]), d["diagnosticada"]),
            (6.62, f"{_sim(antes)} → {_sim(depois)}", depois),
            (9.41, f"{_sim(ev_antes)} → {_sim(ev_depois)}" if alvo else "—", ev_depois),
        )
        for x, texto, ok in dados:
            largura = 2.25 if x > 9 else 1.94
            fundo = VITÓRIA if ok else (NEUTRO if ok is None else PERDA)
            ax.add_patch(Rectangle((x - largura / 2, y - 0.30), largura, 0.62,
                                   color=fundo, linewidth=0))
            ax.text(x, y, texto, fontsize=11, color=ANIL if ok else TINTA_2, va="center",
                    ha="center", fontweight="bold")
    pre, pos = r["resumo"]["memoria"], r["resumo"]["apos_revisao"]
    cand = len(c["candidatas_conferidas"])
    elegiveis = (len(c["elegiveis_antes"]), len(c["elegiveis_apos_revisao"]))
    estado = (pre["encaminhamentos_explicitos"], pos["encaminhamentos_explicitos"])
    qtd_estado = pos["consultas_estado"]
    sem_adocao = "Git intacto durante proposta" if c["somente_leitura"] else "Proposta alterou o Git"
    fig.text(0.063, 0.209, "CONTROLES", fontsize=9.1, color=ANIL, fontweight="bold")
    fig.text(0.17, 0.207, f"{sem_adocao}   /   propostas validadas {cand}   /   "
             f"notas elegíveis {elegiveis[0]} → {elegiveis[1]}", fontsize=9.5, color=TINTA_2)
    fig.text(0.17, 0.165, f"Estado com intenção explícita {estado[0]}/{qtd_estado} → "
             f"{estado[1]}/{qtd_estado}   /   elegibilidade conforme o gabarito: "
             f"{'sim' if c['elegibilidade_conferiu_apos_revisao'] else 'não'}",
             fontsize=9.5, color=TINTA_2)
    _rodape(fig, "Evidência completa nas cinco primeiras. A validação de uma proposta "
            "conserva o estado de candidata.", _fonte(r))
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("relatorio", type=Path)
    parser.add_argument("--saida", type=Path, default=Path("outputs/cdp-memoria/sonho"))
    args = parser.parse_args()
    r = json.loads(args.relatorio.read_text(encoding="utf-8"))
    if r.get("natureza") != "DADOS SIMULADOS" or r.get("limite") != 5:
        parser.error("use o relatório de memoria avaliar --sonho")
    with mpl.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "svg.hashsalt": "cdp-memoria-sonho"}):
        _salvar(_recuperacao(r), args.saida, "01-recuperacao-com-revisao")
        _salvar(_consolidacao(r), args.saida, "02-consolidacao-e-controles")


if __name__ == "__main__":
    main()
