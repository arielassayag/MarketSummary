"""Relatórios e artefatos da execução (seções 18 e 19 da especificação).

Tudo em outputs/<run_id>/: manifest com hashes, tabelas CSV, methodology.md,
caveats.md, article_results.md (direto para o AI Notes), exemplos before/after
dos showcases pré-marcados e report.html standalone (abre offline, com gráficos
embutidos em base64).
"""

from __future__ import annotations

import base64
import html
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .cache import file_sha256
from .config import ExperimentConfig
from .schemas import GenerationRecord

BRT = timezone(timedelta(hours=-3))


def brt_today() -> str:
    return datetime.now(BRT).strftime("%d/%m/%Y")


def git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def build_manifest(
    *,
    root: Path,
    run_id: str,
    cfg: ExperimentConfig,
    splits: list[str],
    model_ids: list[str],
    prompt_versions: list[str],
    repetitions: int,
    synthetic: bool,
) -> dict[str, object]:
    def sha(path: str) -> str | None:
        p = root / path
        return file_sha256(p) if p.exists() else None

    dataset_manifest_path = root / "data" / "dataset_manifest.json"
    dataset_manifest = (
        json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
        if dataset_manifest_path.exists()
        else {}
    )
    case_hashes = {
        c["case_id"]: c["sha256"] for c in dataset_manifest.get("cases", [])  # type: ignore[union-attr]
    }
    review_statuses = {
        c["case_id"]: "unknown" for c in dataset_manifest.get("cases", [])  # type: ignore[union-attr]
    }
    return {
        "run_id": run_id,
        "created_at": datetime.now(BRT).isoformat(),
        "synthetic": synthetic,
        "splits": splits,
        "models": model_ids,
        "prompt_versions": prompt_versions,
        "repetitions": repetitions,
        "generation_params": {
            "temperature": cfg.run.temperature,
            "top_p": cfg.run.top_p,
            "max_tokens": cfg.run.max_tokens,
            "response_mode": cfg.run.response_mode,
            "concurrency": cfg.run.concurrency,
            "seeds": cfg.run.seeds,
            "shuffle_seed": cfg.run.shuffle_seed,
        },
        "judge_model": cfg.judge.model,
        "hashes": {
            "dataset_manifest": sha("data/dataset_manifest.json"),
            "cases": case_hashes,
            "prompt_common": sha("prompts/common_system.md"),
            "prompt_v1": sha("prompts/candidate_v1.md"),
            "prompt_v2": sha("prompts/candidate_v2.md"),
            "judge_absolute": sha("prompts/judge_absolute.md"),
            "judge_pairwise": sha("prompts/judge_pairwise.md"),
            "config_experiment": sha("configs/experiment.yaml"),
            "config_scoring": sha("configs/scoring.yaml"),
            "models_lock": sha("configs/models.lock.yaml"),
            "schema_module": sha("src/market_eval/schemas.py"),
            "git_commit": git_commit(root),
        },
        "review_statuses": review_statuses,
        "catalog_snapshot": dataset_manifest.get("method", ""),
    }


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dataset_publishable(root: Path, case_ids: set[str]) -> tuple[bool, list[str]]:
    manifest_path = root / "data" / "dataset_manifest.json"
    if not manifest_path.exists():
        return False, ["dataset_manifest.json ausente"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for case in manifest.get("cases", []):
        if str(case["case_id"]) not in case_ids:
            continue
        status = case.get("review_status", "draft")
        if status != "reviewed":
            problems.append(f"{case['case_id']}: review.status={status} (requer revisão humana)")
    return (not problems), problems


def write_methodology(run_dir: Path, cfg: ExperimentConfig, splits: list[str]) -> None:
    text = f"""# Metodologia

## Desenho
- Tarefa: comentário de fechamento do mercado brasileiro a partir de pacote congelado de fatos.
- Casos: pregões históricos da B3 estratificados em 5 regimes (calma, macro doméstico, global,
  corporativo, estresse). Splits: {' e '.join(splits)}. O holdout só é aberto com flag explícita
  e não foi usado para ajustar o Prompt V2.
- Modelos (via OpenRouter): ver configs/models.lock.yaml (IDs exatos, preços e snapshot do catálogo).
- Prompts: V1 (baseline curto) e V2 (regras de disciplina factual). A comparação muda SOMENTE o
  prompt — modelos, parâmetros, dataset e schema são idênticos.
- Parâmetros: temperature={cfg.run.temperature}, top_p={cfg.run.top_p}, max_tokens={cfg.run.max_tokens},
  seed por repetição ({cfg.run.seeds}), repetições={cfg.run.repetitions_dev}/{cfg.run.repetitions_holdout}
  (dev/holdout), ordem de execução embaralhada com seed {cfg.run.shuffle_seed}.

## Avaliação
1. Verificações determinísticas por código (17 checagens): schema, contagem de palavras (180-220),
   IDs existentes, valores/unidades/direções com tolerância pequena (troca de sinal sempre falha),
   recall de fatos críticos e must_mention, evidência dos claims, retorno≠contribuição.
2. LLM-as-a-judge absoluto ({cfg.judge.model}, temperature=0), anonimizado, rubrica 0-4 em 5
   dimensões; raw_score = 30·F/4 + 25·M/4 + 20·C/4 + 15·Cov/4 + 10·Cl/4.
3. hard_fail: JSON/schema inválido; erro de sinal/valor/unidade em fato crítico; evidence_id
   inexistente; fato/evento fabricado; causalidade sem suporte como fato; retorno como contribuição;
   contradição central. Com hard_fail, final_score = min(raw_score, 49).
4. Comparação pareada V1 x V2 (secundária): judge cego, duas ordens; divergência = instável.
5. Auditoria humana: amostra estratificada (>= 10% ou 40 outputs), anonimizada; concordância,
   kappa de Cohen, MAE e Spearman por dimensão.
6. Estatística: IC de Wilson para taxas; delta V2-V1 pareado por caso com bootstrap (2000
   reamostragens, seed fixa). Dev e holdout reportados separadamente.

## Limitações
Ver caveats.md. Resultado específico desta tarefa, destes casos, prompts e modelos.
"""
    (run_dir / "methodology.md").write_text(text, encoding="utf-8")


def write_caveats(run_dir: Path) -> None:
    text = """# Limitações e ressalvas

1. **Escopo estrito**: conclusões valem para ESTA tarefa (comentário de fechamento com pacote
   congelado), ESTES 20 casos, ESTES dois prompts e ESTES modelos na data da execução. Não
   afirmamos "melhor modelo do mundo" nem "melhor modelo para mercado financeiro".
2. **Fonte do índice**: fechamentos do Ibovespa vêm de agregador (série ^BVSP do Yahoo Finance)
   porque a série SGS do BCB para o índice foi descontinuada em 2019. Todos os casos exigem
   validação humana contra a B3 antes de publicação (data/human_review_queue.csv).
3. **Câmbio**: fatos FX usam a PTAX do Banco Central (referência ~13h/fechamento), que difere do
   fechamento do dólar à vista citado pela imprensa; casos com números de imprensa mantêm as duas
   referências explícitas.
4. **Curva de juros e contribuições**: sem dados de DI em pontos-base e sem contribuições em bps
   por ação no dataset; nenhum fato do tipo contribution_bps existe — "contribuição" deve estar
   ausente dos comentários corretos.
5. **Eventos**: paráfrases curtas de matérias Tier 3 (Reuters/Valor/G1/CNN/UOL/Folha/Bloomberg
   Línea etc.) com URL original; nenhum trecho extenso reproduzido.
6. **Judge automático**: feito por `moonshotai/kimi-k2.6` (fora dos candidatos; trocado de
   `claude-opus-5` por orçamento, descartando julgamentos antigos para manter judge único).
   Mesmo com rubrica e anonimização, LLM-as-a-judge pode ter vieses; os números só devem ser
   tratados como validados após a auditoria humana (kappa, MAE, Spearman).
7. **Reprodutibilidade**: temperature=0 não garante determinismo entre provedores; mantemos duas
   repetições e cache SQLite para não pagar duas vezes por chamadas idênticas.
8. **Modelos e preços mudam**: o catálogo do OpenRouter muda diariamente; models.lock.yaml congela
   o que foi usado, com snapshot e data.
9. **Draft**: enquanto houver casos com review.status != reviewed, os relatórios são marcados
   RASCUNHO e não devem ser publicados.
"""
    (run_dir / "caveats.md").write_text(text, encoding="utf-8")


def write_article_results(run_dir: Path, root: Path, summary: pd.DataFrame, delta: pd.DataFrame, failures: pd.DataFrame, pairwise: pd.DataFrame | None) -> Path:
    def fmt(x: object, nd: int = 1) -> str:
        try:
            v = float(x)  # type: ignore[arg-type]
            return f"{v:.{nd}f}".replace(".", ",")
        except (TypeError, ValueError):
            return "—"

    lines: list[str] = []
    lines.append("# AI Notes — resultados do experimento de prompts (fechamento de mercado)")
    lines.append("")
    lines.append(f"Execução: {brt_today()} (horário de Brasília).")
    lines.append("")
    lines.append("> **VERIFICAR ANTES DE PUBLICAR**: os casos do dataset ainda estão em revisão")
    lines.append("> humana (review.status=draft). Este arquivo só é publicável quando TODOS os casos")
    lines.append("> usados estiverem `reviewed` e a auditoria humana do judge estiver concluída.")
    lines.append("")

    if summary.empty:
        lines.append(
            "> **PENDENTE — EXECUÇÃO REAL AINDA NÃO REALIZADA.** Os números abaixo são "
            "placeholders. Execute `python -m market_eval run --split dev --prompt all`, "
            "`grade`, `report` para preencher."
        )
        lines.append("")
        lines.append("| modelo | aprovação V1 | aprovação V2 | Δ (p.p.) | nota V1 | nota V2 | custo médio (US$) | latência p50 (ms) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append("| <<PREENCHER>> | X% | Y% | +Z | A | B | C | D |")
        lines.append("")
        lines.append("Com o primeiro prompt, a taxa média de aprovação factual foi de <<X>>%. Depois da revisão das instruções, ela passou para <<Y>>%, uma melhora de <<Z>> pontos percentuais.")
        lines.append("")
        lines.append("No conjunto separado de validação (holdout), que não foi utilizado para ajustar o prompt, a taxa passou de <<X>>% para <<Y>>% e a nota média passou de <<A>> para <<B>>.")
    else:
        piv = summary.pivot_table(index="model_id", columns="prompt_version", values=["hard_pass_rate", "final_score_mean", "cost_mean_usd", "latency_p50_ms"], aggfunc="first")
        lines.append("| modelo | aprovação V1 | aprovação V2 | Δ (p.p.) | nota V1 | nota V2 | custo médio (US$) | latência p50 (ms) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for model, row in piv.iterrows():
            a1 = float(row.get(("hard_pass_rate", "v1")) or 0.0)
            a2 = float(row.get(("hard_pass_rate", "v2")) or 0.0)
            n1 = float(row.get(("final_score_mean", "v1")) or 0.0)
            n2 = float(row.get(("final_score_mean", "v2")) or 0.0)
            c = float(row.get(("cost_mean_usd", "v2")) or 0.0)
            lat_p50 = float(row.get(("latency_p50_ms", "v2")) or 0.0)
            delta_pp: float | None = (a2 - a1) * 100
            lines.append(
                f"| {model} | {fmt(a1 * 100) if a1 == a1 else '—'}% | {fmt(a2 * 100) if a2 == a2 else '—'}% | "
                f"{'+' if (delta_pp or 0) >= 0 else ''}{fmt(delta_pp) if delta_pp is not None else '—'} | "
                f"{fmt(n1) if n1 == n1 else '—'} | {fmt(n2) if n2 == n2 else '—'} | {fmt(c, 4) if c == c else '—'} | {fmt(lat_p50, 0) if lat_p50 == lat_p50 else '—'} |"
            )
        lines.append("")
        # parágrafos prontos (média entre modelos)
        try:
            dev = summary[summary["split"] == "dev"]
            hold = summary[summary["split"] == "holdout"]
            for label, grp in (("dev", dev), ("holdout", hold)):
                if grp.empty:
                    continue
                v1_rate = grp[grp["prompt_version"] == "v1"]["hard_pass_rate"].mean() * 100
                v2_rate = grp[grp["prompt_version"] == "v2"]["hard_pass_rate"].mean() * 100
                v1_note = grp[grp["prompt_version"] == "v1"]["final_score_mean"].mean()
                v2_note = grp[grp["prompt_version"] == "v2"]["final_score_mean"].mean()
                if label == "dev":
                    lines.append(
                        f"Com o primeiro prompt, a taxa média de aprovação factual foi de {v1_rate:.0f}%. "
                        f"Depois da revisão das instruções, ela passou para {v2_rate:.0f}%, uma melhora "
                        f"de {v2_rate - v1_rate:+.0f} pontos percentuais."
                    )
                else:
                    lines.append(
                        f"No conjunto separado de validação, que não foi utilizado para ajustar o prompt, "
                        f"a taxa passou de {v1_rate:.0f}% para {v2_rate:.0f}% e a nota média passou de "
                        f"{v1_note:.1f} para {v2_note:.1f}."
                    )
                lines.append("")
        except Exception:  # noqa: BLE001
            lines.append("")
        # erros principais
        if not failures.empty:
            top = failures.groupby(["prompt_version", "failure_category"], as_index=False).agg(count=("count", "sum"))
            top = top.sort_values(by="count", ascending=False).head(8)
            lines.append("## Principais erros por versão")
            lines.append("")
            for _, row in top.iterrows():
                lines.append(f"- Prompt {str(row['prompt_version']).upper()} — {row['failure_category']}: {int(row['count'])}")
            lines.append("")
        # melhor/pior dentro da tarefa
        try:
            by_model = summary[summary["split"] == "dev"].groupby("model_id")["hard_pass_rate"].mean()
            if len(by_model) >= 2:
                lines.append(
                    f"**Dentro desta tarefa**, o melhor desempenho médio de aprovação factual foi de "
                    f"`{by_model.idxmax()}` ({by_model.max() * 100:.0f}%) e o pior, de "
                    f"`{by_model.idxmin()}` ({by_model.min() * 100:.0f}%). Isso NÃO significa melhor/pior "
                    "modelo em geral — apenas nestes casos, prompts e parâmetros."
                )
                lines.append("")
        except Exception:  # noqa: BLE001
            pass
        # custo x qualidade
        if not summary.empty and summary["cost_mean_usd"].notna().any():
            cheap = summary.dropna(subset=["cost_mean_usd"]).sort_values("cost_mean_usd")
            if len(cheap):
                lines.append(
                    f"**Custo x qualidade**: o modelo mais barato da amostra foi `{cheap.iloc[0]['model_id']}` "
                    f"(US$ {float(cheap.iloc[0]['cost_mean_usd']):.4f}/comentário), contra "
                    f"US$ {float(cheap.iloc[-1]['cost_mean_usd']):.4f} do mais caro (`{cheap.iloc[-1]['model_id']}`), "
                    "com notas descritas na tabela acima."
                )
                lines.append("")

    # modelos e catálogo
    lock_path = root / "configs" / "models.lock.yaml"
    lines.append("## Modelos (IDs exatos)")
    lines.append("")
    if lock_path.exists():
        lines.append("```yaml")
        lines.extend(
            line for line in lock_path.read_text(encoding="utf-8").splitlines() if "exact_model_id" in line
        )
        lines.append("```")
        snap = root / "data" / "raw" / "openrouter_models_snapshot_2026-08-27.json"
        if snap.exists():
            lines.append(f"Catálogo OpenRouter congelado em 2026-08-27 (`{snap.name}`).")
    lines.append("")

    lines.append("## Metodologia (resumo)")
    lines.append("")
    lines.append(
        "20 pregões da B3 (jan/2025–jul/2026), estratificados em 5 regimes; 4 modelos via OpenRouter; "
        "2 prompts (V1 e V2, mudando SOMENTE o prompt); 2 repetições; temperature 0; ordem embaralhada "
        "com seed. Avaliação em 3 camadas: verificações por código, judge LLM anonimizado (rubrica 0-4; "
        "hard fail zera acima de 49) e auditoria humana estratificada. Delta V2-V1 pareado por caso com "
        "bootstrap; dev e holdout reportados separadamente."
    )
    lines.append("")
    lines.append("## Limitações")
    lines.append("")
    lines.append(
        "Resultados limitados a esta tarefa/casos/prompts/modelos; índice via agregador e câmbio via "
        "PTAX (validar contra B3/BCB); judge automático não substitui auditoria humana; temperature 0 "
        "não garante determinismo entre provedores; modelos e preços mudam no OpenRouter."
    )
    lines.append("")
    lines.append("## Legendas dos gráficos")
    lines.append("")
    lines.append("1. *Nota média por modelo* — média do final score (0-100) por modelo, V1 vs V2.")
    lines.append("2. *Taxa de aprovação factual* — % de saídas sem hard fail.")
    lines.append("3. *Delta do prompt* — Δ V2-V1 pareado por caso, IC 95% por bootstrap.")
    lines.append("4. *Erros críticos* — ocorrências por categoria e versão.")
    lines.append("5. *Por regime* — efeito do prompt por tipo de pregão.")
    lines.append("6. *Custo versus qualidade* — custo médio por comentário x nota média.")
    lines.append("7. *Vitórias pareadas* — judge cego, duas ordens; divergência = instável.")
    lines.append("")

    out = run_dir / "article_results.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_examples_before_after(run_dir: Path, root: Path, records: list[GenerationRecord]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest_path = root / "data" / "dataset_manifest.json"
    showcases: list[str] = []
    if dataset_manifest_path.exists():
        manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
        showcases = [c["case_id"] for c in manifest.get("cases", []) if c.get("showcase")]  # type: ignore[union-attr]
    lines = ["# Exemplos before/after (showcases pré-marcados)", ""]
    for case_id in showcases:
        lines.append(f"## {case_id}")
        for version in ("v1", "v2"):
            rec = next(
                (r for r in records if r.case_id == case_id and r.prompt_version == version and r.status.value == "completed"),
                None,
            )
            label = "Antes (Prompt V1)" if version == "v1" else "Depois (Prompt V2)"
            lines.append(f"### {label}")
            if rec is None or rec.output is None:
                lines.append("_Execução pendente para este caso._")
            else:
                lines.append(f"**{rec.output.headline}**")
                lines.append("")
                lines.append(rec.output.commentary)
            lines.append("")
    if not showcases:
        lines.append("_Showcases não definidos no manifest do dataset._")
    (run_dir / "examples_before_after.md").write_text("\n".join(lines), encoding="utf-8")


def write_report_html(
    run_dir: Path,
    root: Path,
    manifest: dict[str, object],
    summary: pd.DataFrame,
    delta: pd.DataFrame,
    failures: pd.DataFrame,
    pairwise_rows: list[dict[str, object]],
) -> Path:
    charts_dir = run_dir / "charts"
    imgs: list[tuple[str, str]] = []
    if charts_dir.exists():
        for png in sorted(charts_dir.glob("*.png")):
            b64 = base64.b64encode(png.read_bytes()).decode("ascii")
            imgs.append((png.stem, f"data:image/png;base64,{b64}"))

    def table(df: pd.DataFrame, max_rows: int = 40) -> str:
        if df is None or df.empty:
            return "<p><em>(sem dados)</em></p>"
        return df.head(max_rows).to_html(index=False, border=0, classes="tbl")

    all_cases_publishable, _ = dataset_publishable_all(root)
    draft_banner = ""
    if not all_cases_publishable:
        draft_banner = (
            "<div class='banner'>RASCUNHO — NÃO PUBLICAR. Há casos do dataset sem revisão humana "
            "concluída (review.status != reviewed). Preencha a fila "
            "data/human_review_queue.csv e marque os casos como reviewed.</div>"
        )
    syn_banner = (
        "<div class='banner syn'>RESULTADOS SINTÉTICOS (SMOKE TEST) — NÃO USAR COMO RESULTADO REAL.</div>"
        if manifest.get("synthetic")
        else ""
    )

    source_links: list[str] = []
    dm_path = root / "data" / "dataset_manifest.json"
    if dm_path.exists():
        dm = json.loads(dm_path.read_text(encoding="utf-8"))
        seen: set[str] = set()
        for case in dm.get("cases", []):  # type: ignore[union-attr]
            path = root / str(case["path"])  # type: ignore[union-attr]
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for fact in data["input"]["facts"]:
                url = fact["source"]["url"]
                if url not in seen:
                    seen.add(url)
                    source_links.append(f"<li><a href='{html.escape(url)}'>{html.escape(url)}</a></li>")

    pairwise_html = (
        table(pd.DataFrame(pairwise_rows).head(20))
        if pairwise_rows
        else "<p><em>(comparação pareada ainda não executada — comando `pairwise`)</em></p>"
    )

    html_doc = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Market Close Eval — {html.escape(str(manifest.get('run_id', '')))}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#fff;color:#1C252E}}
header{{background:#1C252E;color:#fff;padding:2rem}}header h1{{margin:0}}
main{{max-width:1100px;margin:0 auto;padding:1.5rem}}
.banner{{background:#FF6200;color:#fff;padding:1rem;margin:1rem 0;font-weight:bold}}
.banner.syn{{background:#1C252E}}
.tbl{{border-collapse:collapse;font-size:0.85rem}}
.tbl td,.tbl th{{border:1px solid #ddd;padding:4px 8px;text-align:left}}
h2{{color:#FF6200;margin-top:2rem}} img{{max-width:100%;border:1px solid #eee}}
li{{margin:2px 0}}
</style></head><body>
<header><h1>Market Close Eval — {html.escape(str(manifest.get('run_id', '')))}</h1>
<p style="margin:0.3rem 0 0">Comentários de fechamento do mercado brasileiro: Prompt V1 vs Prompt V2</p></header>
<main>
{draft_banner}{syn_banner}
<h2>Metodologia</h2>
<pre>{html.escape((run_dir / 'methodology.md').read_text(encoding='utf-8') if (run_dir / 'methodology.md').exists() else '')}</pre>
<h2>Modelos exatos</h2>
<pre>{html.escape((root / 'configs' / 'models.lock.yaml').read_text(encoding='utf-8')[:4000])}</pre>
<h2>Resultados</h2>
<h3>Resumo por modelo e prompt</h3>
{table(summary)}
<h3>Delta V2 - V1 (pareado por caso)</h3>
{table(delta)}
<h3>Comparação pareada</h3>
{pairwise_html}
<h2>Gráficos</h2>
{''.join(f'<h3>{html.escape(name)}</h3><img src="{src}" alt="{html.escape(name)}"/>' for name, src in imgs)}
<h2>Principais falhas</h2>
{table(failures)}
<h2>Exemplos</h2>
<pre>{html.escape((run_dir / 'examples_before_after.md').read_text(encoding='utf-8')[:4000] if (run_dir / 'examples_before_after.md').exists() else '')}</pre>
<h2>Custos</h2>
<p>Custos detalhados: <code>cost_latency.csv</code> e <code>summary_by_model_prompt.csv</code>.</p>
<h2>Limitações</h2>
<pre>{html.escape((run_dir / 'caveats.md').read_text(encoding='utf-8') if (run_dir / 'caveats.md').exists() else '')}</pre>
<h2>Manifest (hashes)</h2>
<pre>{html.escape(json.dumps(manifest, ensure_ascii=False, indent=1)[:6000])}</pre>
<h2>Fontes dos casos</h2>
<ul>{''.join(source_links)}</ul>
</main></body></html>"""
    out = run_dir / "report.html"
    out.write_text(html_doc, encoding="utf-8")
    return out


def dataset_publishable_all(root: Path) -> tuple[bool, list[str]]:
    dm_path = root / "data" / "dataset_manifest.json"
    if not dm_path.exists():
        return False, ["dataset_manifest.json ausente"]
    dm = json.loads(dm_path.read_text(encoding="utf-8"))
    problems = [
        f"{c['case_id']}: review.status={c.get('review_status', 'draft')}"  # type: ignore[union-attr]
        for c in dm.get("cases", [])  # type: ignore[union-attr]
        if c.get("review_status", "draft") != "reviewed"  # type: ignore[union-attr]
    ]
    return (not problems), problems
