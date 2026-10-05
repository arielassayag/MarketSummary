"""CLI do CDP — Cabra da Peste (interface comum para Claude Code e Codex).

Fluxo semanal (primeiro pregão da semana na B3):
    cdp weekly prepare --date D --mind claude-code|codex
    (a mente escreve book/<D>/inputs/research_pack.json e pm_decision.json)
    cdp validate --week D
    cdp weekly preview --week D --mind ...   (opcional: revisão pré-trade, não grava)
    cdp weekly decide --week D --mind ...

Fluxo diário (após o fechamento):
    cdp daily --date D
    (a mente escreve reports/daily/<D>/comentario.json)
    cdp validate-daily --date D             (valida o comentário sem publicar)
    cdp daily publish --date D

Rotinas locais (plugin ``cdp`` do Claude Code; ver docs/cdp/LOCAL.md):
    cdp agenda                       (o que fazer agora: semana, prazos, fechamentos pendentes)
    cdp risk [--live] [--date D]     (monitor de risco; grava reports/risk/<D>/risco_<HHMM>.md)
    cdp painel [--out F] [--standalone F]  (painel HTML de operação e risco para o artifact)

Outros: status, verify, demo, backtest, fetch-base, kill-switch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import SIMULATED_DATA_NOTICE

DEFAULT_BOOK = Path("book")
DEFAULT_MARKET = Path("data/market")
DEFAULT_REPORTS = Path("reports")
DEFAULT_UNIVERSE = Path("data/universe/latam_universe.csv")


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _today_brt() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


# ----------------------------------------------------------------------------- comandos


def cmd_status(args: argparse.Namespace) -> int:
    from .calendar import first_session_of_week, is_rebalance_day, open_markets
    from .workflow.runtime import Runtime

    d = args.date or _today_brt()
    rt = Runtime.from_args(args)
    week = first_session_of_week(d)
    info = {
        "data": d, "pregao_b3": open_markets(d).get("BR"), "mercados_abertos": open_markets(d),
        "dia_de_rebalanceamento": is_rebalance_day(d), "semana": week,
        "kill_switch": rt.kill_switch_active(),
        "decisao_da_semana": bool(week and rt.book.list_decisions(week)),
        "ultimo_registro_diario": rt.last_record_date(),
        "nav_atual_usd": rt.current_nav(),
        "ultimo_pregao_gravado": rt.store_last_date(),
    }
    _print(info)
    return 0


def cmd_fetch_base(args: argparse.Namespace) -> int:
    from .data.store import MarketStore

    store = MarketStore(args.market)
    manifest = store.build_base(Path(args.universe), _d(args.as_of), start=_d(args.start))
    _print({"base": manifest.snapshot_id, "as_of": manifest.as_of,
            "arquivos": len(manifest.files), "faltantes": manifest.missing_tickers[:20],
            "limitacoes": manifest.limitations})
    return 0


def cmd_weekly_prepare(args: argparse.Namespace) -> int:
    from .calendar import is_rebalance_day
    from .workflow.runtime import Runtime

    d = args.date or _today_brt()
    if not args.force and not is_rebalance_day(d):
        print(f"{d} não é o primeiro pregão da semana na B3 — nada a fazer.")
        return 0
    rt = Runtime.from_args(args)
    out = rt.weekly_prepare(d, mind=args.mind, live=not args.offline)
    _print(out)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    ok, issues = rt.validate_inputs(_d(args.week), mind=args.mind)
    print("OK" if ok else "FALHOU")
    for i in issues:
        print(f"- {i}")
    return 0 if ok else 1


def cmd_weekly_decide(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.weekly_decide(_d(args.week), mind=args.mind)
    _print(out)
    return 0


def cmd_weekly_preview(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.weekly_preview(_d(args.week), mind=args.mind)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                                  encoding="utf-8")
    _print({k: v for k, v in out.items() if k not in ("posicoes", "sombra_quant", "tentativas")})
    return 0


def cmd_daily(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    d = args.date or _today_brt()
    if args.action == "publish":
        out = rt.daily_publish(d)
    else:
        out = rt.daily_close(d, live=not args.offline, mind=args.mind)
    _print(out)
    return 0


def cmd_validate_daily(args: argparse.Namespace) -> int:
    """Valida ``comentario.json`` do dia SEM publicar (``daily publish`` é imutável)."""
    from .workflow.agenda import validate_daily_commentary
    from .workflow.runtime import Runtime

    ok, issues = validate_daily_commentary(Runtime.from_args(args), args.date or _today_brt())
    print("OK" if ok else "FALHOU")
    for i in issues:
        print(f"- {i}")
    return 0 if ok else 1


def cmd_verify(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    ok, msgs = rt.verify_all()
    print("ÍNTEGRO" if ok else "FALHA DE INTEGRIDADE")
    for m in msgs:
        print(f"- {m}")
    return 0 if ok else 1


def cmd_kill_switch(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    if args.state == "on":
        if not args.reason or len(args.reason) < 10:
            print("Informe --reason com pelo menos 10 caracteres.", file=sys.stderr)
            return 2
        rt.set_kill_switch(True, args.reason, args.by)
    else:
        rt.set_kill_switch(False, args.reason or "desligado", args.by)
    print(f"Kill switch: {args.state}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .workflow.demo import run_demo

    print(f"{SIMULATED_DATA_NOTICE}: demonstração offline com mercado sintético.")
    out = run_demo(Path(args.out), days=args.days)
    _print(out)
    return 0


def cmd_agenda(args: argparse.Namespace) -> int:
    from .workflow.agenda import agenda
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    _print(agenda(rt, now=args.agora))
    return 0


def cmd_risk(args: argparse.Namespace) -> int:
    from .workflow.risk_monitor import (
        RISK_DIRNAME,
        run_risk_monitor,
        summary_view,
        write_risk_report,
    )
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    res = run_risk_monitor(rt, as_of=args.date, live=args.live)
    out_root = Path(args.out) if args.out else Path(args.reports) / RISK_DIRNAME
    paths = write_risk_report(res, out_root, rt.cfg)
    view = summary_view(res)
    view["relatorio"] = paths
    _print(view)
    return 0


DEFAULT_PAINEL = Path("artifacts/painel/cdp_painel.html")
#: A ferramenta que publica o artifact exige que a mente leia o arquivo inteiro antes; a leitura
#: de arquivos devolve no máximo ~25 mil tokens por chamada. Acima destes limites a skill não tenta
#: ler nem publicar (não gasta contexto) e relata o motivo.
PAINEL_ARTIFACT_MAX_BYTES = 100_000
PAINEL_ARTIFACT_MAX_LINE = 2_000


def painel_artifact_check(path: Path) -> dict:
    """Se o HTML do painel cabe numa leitura integral pela mente (pré-requisito da publicação)."""
    limits = {"bytes": PAINEL_ARTIFACT_MAX_BYTES, "linha": PAINEL_ARTIFACT_MAX_LINE}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"publicavel": False, "bytes": None, "maior_linha": None, "limites": limits,
                "motivo": f"arquivo ilegível: {exc.__class__.__name__}"}
    longest = max((len(x) for x in raw.decode("utf-8", errors="replace").splitlines()), default=0)
    problems = []
    if len(raw) > PAINEL_ARTIFACT_MAX_BYTES:
        problems.append(f"{len(raw)} bytes (limite {PAINEL_ARTIFACT_MAX_BYTES})")
    if longest > PAINEL_ARTIFACT_MAX_LINE:
        problems.append(f"linha de {longest} caracteres (limite {PAINEL_ARTIFACT_MAX_LINE})")
    return {"publicavel": not problems, "bytes": len(raw), "maior_linha": longest,
            "limites": limits,
            "motivo": ("grande demais para a leitura integral exigida antes de publicar: "
                       + "; ".join(problems)) if problems else "ok"}


def cmd_painel(args: argparse.Namespace) -> int:
    """Grava o painel (artifact) de operação e risco; só lê o livro, a trilha e os relatórios.

    A saída inclui ``artifact`` (:func:`painel_artifact_check`): as skills só leem e publicam o
    HTML no artifact quando ``artifact.publicavel`` é ``true``.
    """
    from .workflow.painel import write_painel
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = write_painel(rt, Path(args.out),
                       standalone_out=Path(args.standalone) if args.standalone else None)
    out = {**out, "artifact": painel_artifact_check(Path(args.out))}
    _print(out)
    return 0


def _aware(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo

        dt = dt.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return dt


def cmd_backtest(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.run_backtest(_d(args.start), _d(args.end) if args.end else None, Path(args.out))
    _print(out)
    return 0


# ----------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cdp", description="CDP — Cabra da Peste (PM autônomo LatAm L/S)")
    p.add_argument("--config", default=None, help="fund.yaml (padrão: configs/cdp/fund.yaml)")
    p.add_argument("--book", default=str(DEFAULT_BOOK))
    p.add_argument("--market", default=str(DEFAULT_MARKET))
    p.add_argument("--reports", default=str(DEFAULT_REPORTS))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="estado do fundo e do calendário")
    s.add_argument("--date", type=_d)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("fetch-base", help="constrói o histórico-base imutável (dados reais)")
    s.add_argument("--as-of", required=True)
    s.add_argument("--start", default="2019-01-02")
    s.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    s.set_defaults(func=cmd_fetch_base)

    w = sub.add_parser("weekly", help="montagem semanal da carteira")
    wsub = w.add_subparsers(dest="action", required=True)
    s = wsub.add_parser("prepare", help="coleta todos os dados até agora e gera o briefing")
    s.add_argument("--date", type=_d)
    s.add_argument("--mind", choices=["claude-code", "codex", "api", "demo"], required=True)
    s.add_argument("--force", action="store_true", help="ignora a regra do primeiro pregão")
    s.add_argument("--offline", action="store_true", help="sem barra intradiária/coleta ao vivo")
    s.set_defaults(func=cmd_weekly_prepare)
    s = wsub.add_parser("preview", help="prévia pré-trade do livro (não grava nada)")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=["claude-code", "codex", "api", "demo"], required=True)
    s.add_argument("--out", help="grava a prévia completa (JSON) neste caminho")
    s.set_defaults(func=cmd_weekly_preview)
    s = wsub.add_parser("decide", help="valida, otimiza, aplica gates e decide (autônomo)")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=["claude-code", "codex", "api", "demo"], required=True)
    s.set_defaults(func=cmd_weekly_decide)

    s = sub.add_parser("validate", help="valida os arquivos escritos pela mente")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=["claude-code", "codex", "api", "demo"])
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("daily", help="fechamento diário (close) ou publicação do relatório")
    s.add_argument("action", nargs="?", default="close", choices=["close", "publish"])
    s.add_argument("--date", type=_d)
    s.add_argument("--offline", action="store_true")
    s.add_argument("--mind", choices=["claude-code", "codex", "api", "demo"])
    s.set_defaults(func=cmd_daily)

    s = sub.add_parser("validate-daily",
                       help="valida o comentario.json do dia sem publicar (publish é imutável)")
    s.add_argument("--date", type=_d)
    s.set_defaults(func=cmd_validate_daily)

    s = sub.add_parser("verify", help="verifica trilha de auditoria, track record e decisões")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("kill-switch", help="liga/desliga o kill switch (só redução de risco)")
    s.add_argument("state", choices=["on", "off"])
    s.add_argument("--reason", default="")
    s.add_argument("--by", default="operador")
    s.set_defaults(func=cmd_kill_switch)

    s = sub.add_parser("demo", help="demonstração offline completa (DADOS SIMULADOS)")
    s.add_argument("--out", default="outputs/cdp_demo")
    s.add_argument("--days", type=int, default=5)
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("agenda", help="o que a rotina local deve fazer agora (determinístico)")
    s.add_argument("--agora", type=_aware, default=None,
                   help="instante ISO (sem fuso = Brasília); padrão: agora")
    s.set_defaults(func=cmd_agenda)

    s = sub.add_parser("risk", help="monitor de risco (fechamento ou intradiário com --live)")
    s.add_argument("--date", type=_d, help="data de referência (padrão: hoje em Brasília)")
    s.add_argument("--live", action="store_true",
                   help="marca a carteira com cotações do momento (fonte atrasada)")
    s.add_argument("--out", default=None, help="pasta dos relatórios (padrão: <reports>/risk)")
    s.set_defaults(func=cmd_risk)

    s = sub.add_parser("painel", help="painel HTML de operação e risco (artifact; só leitura)")
    s.add_argument("--out", default=str(DEFAULT_PAINEL),
                   help=f"arquivo do artifact (padrão: {DEFAULT_PAINEL.as_posix()})")
    s.add_argument("--standalone", default=None,
                   help="também grava uma cópia autônoma para abrir no navegador")
    s.set_defaults(func=cmd_painel)

    s = sub.add_parser("backtest", help="backtest walk-forward semanal (sinais point-in-time)")
    s.add_argument("--start", required=True)
    s.add_argument("--end")
    s.add_argument("--out", default="reports/backtest")
    s.set_defaults(func=cmd_backtest)
    return p


def _utf8_stdio() -> None:
    """Saída UTF-8 mesmo em consoles/pipes do Windows (cp1252 não tem "≤", "Σ", "→")."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover - stream já fechado/sem suporte
                pass


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
