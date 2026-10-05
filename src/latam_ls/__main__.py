"""CLI do CDP — Cabra da Peste (interface comum para Claude Code e Codex).

Fluxo semanal (primeiro pregão da semana na B3):
    cdp weekly prepare --date D --mind claude-code|codex
    (a mente escreve book/<D>/inputs/research_pack.json e pm_decision.json)
    cdp validate --week D
    cdp weekly decide --week D --mind ...

Fluxo diário (após o fechamento):
    cdp daily --date D
    (a mente escreve reports/daily/<D>/comentario.json)
    cdp daily publish --date D

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
    ok, issues = rt.validate_inputs(_d(args.week))
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


def cmd_daily(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    d = args.date or _today_brt()
    if args.action == "publish":
        out = rt.daily_publish(d)
    else:
        out = rt.daily_close(d, live=not args.offline)
    _print(out)
    return 0


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


def cmd_backtest(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    out = rt.run_backtest(_d(args.start), _d(args.end) if args.end else None, Path(args.out))
    _print(out)
    return 0


# ----------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cdp", description="CDP — Cabra da Peste (PM autônomo LatAm L/S)")
    p.add_argument("--config", default=None, help="fund.yaml (padrão: configs/latam_ls/fund.yaml)")
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
    s = wsub.add_parser("decide", help="valida, otimiza, aplica gates e decide (autônomo)")
    s.add_argument("--week", required=True)
    s.add_argument("--mind", choices=["claude-code", "codex", "api", "demo"], required=True)
    s.set_defaults(func=cmd_weekly_decide)

    s = sub.add_parser("validate", help="valida os arquivos escritos pela mente")
    s.add_argument("--week", required=True)
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("daily", help="fechamento diário (close) ou publicação do relatório")
    s.add_argument("action", nargs="?", default="close", choices=["close", "publish"])
    s.add_argument("--date", type=_d)
    s.add_argument("--offline", action="store_true")
    s.set_defaults(func=cmd_daily)

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

    s = sub.add_parser("backtest", help="backtest walk-forward semanal (sinais point-in-time)")
    s.add_argument("--start", required=True)
    s.add_argument("--end")
    s.add_argument("--out", default="reports/backtest")
    s.set_defaults(func=cmd_backtest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
