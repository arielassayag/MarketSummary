"""Orquestração operacional do CDP (usada pela CLI, pelas rotinas agendadas e pelo app).

Mantém a reprodutibilidade: a etapa ``weekly prepare`` grava, com hash, tudo o que foi coletado
no momento da análise (barra intradiária e dados lentos); ``weekly decide`` reconstrói exatamente
o mesmo ``MarketData`` a partir desses arquivos e falha se qualquer hash divergir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ..audit import AuditLog
from ..calendar import first_session_of_week, is_rebalance_day, is_session, previous_session
from ..config import FundConfig, load_config
from ..contracts import ResearchPack
from ..hashing import sha256_file, sha256_obj
from ..market import MarketData
from .book import Book

PREPARE_MANIFEST = "prepare_manifest.json"
KILL_SWITCH_FILE = "KILL_SWITCH"
BENCH_INTRADAY = ["ILF", "EWZ", "EWW", "ECH", "ARGT", "SPY"]


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                    encoding="utf-8")


@dataclass
class Runtime:
    cfg: FundConfig
    book_root: Path
    market_root: Path
    reports_root: Path

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def from_args(cls, args) -> Runtime:
        cfg = load_config(getattr(args, "config", None))
        return cls(cfg=cfg, book_root=Path(args.book), market_root=Path(args.market),
                   reports_root=Path(args.reports))

    @property
    def book(self) -> Book:
        return Book(self.book_root, config=self.cfg)

    @property
    def store(self):
        from ..data.store import MarketStore

        return MarketStore(self.market_root, cfg=self.cfg)

    def track(self, shadow: bool = False):
        from .track_record import TrackRecord

        name = "track_record_shadow" if shadow else "track_record"
        return TrackRecord(self.book_root / name)

    # ------------------------------------------------------------------ estado
    def kill_switch_active(self) -> bool:
        return (self.book_root / KILL_SWITCH_FILE).exists()

    def set_kill_switch(self, on: bool, reason: str, by: str) -> None:
        path = self.book_root / KILL_SWITCH_FILE
        audit = AuditLog(self.book_root / "audit_log.jsonl")
        payload = {"on": on, "reason": reason, "by": by, "at": datetime.now(UTC).isoformat()}
        if on:
            _write_json(path, payload)
        elif path.exists():
            path.unlink()
        audit.append("KILL_SWITCH_ON" if on else "KILL_SWITCH_OFF", by, payload,
                     summary=f"Kill switch {'ligado' if on else 'desligado'}: {reason}")

    def last_record_date(self) -> date | None:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001 - módulo/arquivo ausente antes da inception
            return None
        return last.date if last else None

    def current_nav(self) -> float:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001
            last = None
        return float(last.nav_end_usd) if last else float(self.cfg.fund.inception_nav_usd)

    def store_last_date(self) -> date | None:
        try:
            return self.store.last_date()
        except Exception:  # noqa: BLE001
            return None

    def live_weeks(self) -> int:
        b = self.book
        return sum(1 for w in b.list_weeks() if b.load_booked(w) is not None)

    def drawdown_and_vol(self) -> tuple[float, float | None]:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001
            last = None
        if not last:
            return 0.0, None
        return float(last.risk.drawdown), last.risk.realized_vol_21d

    def current_drifted_weights(self) -> dict[str, float] | None:
        try:
            last = self.track().last()
        except Exception:  # noqa: BLE001
            last = None
        if not last or not last.positions:
            return None
        w: dict[str, float] = {}
        for p in last.positions:
            w[p.issuer_id] = w.get(p.issuer_id, 0.0) + float(p.weight)
        return w

    # ------------------------------------------------------------------ dados
    def market_for_week(self, week: date, *, live: bool, briefing_dir: Path,
                        record: bool) -> tuple[MarketData, dict]:
        """MarketData com TODO dado disponível até agora (pregão anterior + intradiário + lentos).

        ``record=True`` coleta ao vivo e grava os arquivos com hash; ``record=False`` reconstrói a
        partir do manifesto salvo (etapa ``decide``), verificando cada hash.
        """
        from ..data.intraday import (
            fetch_intraday_quotes,
            load_quotes,
            overlay_intraday,
            save_quotes,
        )
        from ..data.live_refresh import (
            fetch_slow_refresh,
            load_slow_refresh,
            overlay_slow_refresh,
            save_slow_refresh,
        )

        store = self.store
        prev = previous_session(week)
        manifest_path = briefing_dir / PREPARE_MANIFEST
        if record:
            if live:
                store.catch_up(prev)
            md = store.load(as_of=prev)
            info: dict = {"week": week, "previous_session": prev,
                          "store_content_hash": md.manifest.content_hash(), "live": live,
                          "config_hash": self.cfg.config_hash()}
            if live:
                captured = datetime.now(UTC)
                lines = list(md.universe.lines.index)
                quotes = fetch_intraday_quotes(lines, md.universe.currencies, BENCH_INTRADAY)
                qpath = briefing_dir / "intraday_quotes.parquet"
                qsha = save_quotes(quotes, qpath, captured)
                md = overlay_intraday(md, week, quotes, captured, "briefing/intraday_quotes.parquet",
                                      qsha)
                slow = fetch_slow_refresh(md, week, lookback_days=self.cfg.research.news_lookback_days)
                shashes = save_slow_refresh(slow, briefing_dir / "live")
                md = overlay_slow_refresh(md, slow, shashes, captured, "briefing/live")
                info.update({"captured_at": captured, "intraday_sha256": qsha,
                             "slow_hashes": shashes, "slow_failures": slow.failures,
                             "n_quotes": int(quotes["price"].notna().sum())})
            info["snapshot_hash"] = md.manifest.content_hash()
            _write_json(manifest_path, info)
            return md, info
        info = json.loads(manifest_path.read_text(encoding="utf-8"))
        md = store.load(as_of=prev)
        if md.manifest.content_hash() != info["store_content_hash"]:
            raise ValueError("O histórico de mercado mudou desde o prepare (hash divergente).")
        if info.get("live"):
            captured = datetime.fromisoformat(str(info["captured_at"]))
            quotes, _ = load_quotes(briefing_dir / "intraday_quotes.parquet",
                                    info["intraday_sha256"])
            md = overlay_intraday(md, week, quotes, captured, "briefing/intraday_quotes.parquet",
                                  info["intraday_sha256"])
            slow = load_slow_refresh(briefing_dir / "live", info["slow_hashes"])
            md = overlay_slow_refresh(md, slow, info["slow_hashes"], captured, "briefing/live")
        if md.manifest.content_hash() != info["snapshot_hash"]:
            raise ValueError("Snapshot reconstruído difere do usado no briefing.")
        return md, info

    def _context(self, md: MarketData, week: date):
        from .weekly import prepare_week

        b = self.book
        dd, _vol = self.drawdown_and_vol()
        return prepare_week(md, self.cfg, week, nav=self.current_nav(),
                            current_entry=b.latest_booked(),
                            current_drifted_w=self.current_drifted_weights(), drawdown=dd)

    def _candidates(self, ctx, n: int) -> tuple[list[str], list[str]]:
        a = ctx.alpha.alpha.dropna()
        cons = ctx.sides
        can_short = cons["can_short"].reindex(a.index).fillna(False).astype(bool)
        longs = list(a.sort_values(ascending=False).head(n).index)
        shorts = list(a[can_short].sort_values().head(n).index)
        held = [i for i, w in ctx.current_w.items() if w != 0]
        return sorted(set(longs) | set(held)), sorted(set(shorts) | set(held))

    def _factbook(self, ctx, issuers: list[str]):
        from ..research.factbook import build_factbook

        return build_factbook(ctx.panel, ctx.md, issuers, alpha_z=ctx.alpha.composite_z,
                              signal_z=ctx.alpha.signal_z, squeeze=ctx.squeeze, betas=ctx.betas,
                              specific_vol=ctx.model.specific_vol, snapshot_id=ctx.snapshot_id)

    # ------------------------------------------------------------------ semanal
    def week_dir(self, week: date) -> Path:
        return self.book_root / week.isoformat()

    def weekly_prepare(self, week: date, *, mind: str, live: bool = True) -> dict:
        from ..research.pm_agent import PMContext, write_briefing_bundle

        if first_session_of_week(week) != week:
            raise ValueError(f"{week} não é o primeiro pregão da semana na B3.")
        briefing = self.week_dir(week) / "briefing"
        if (briefing / PREPARE_MANIFEST).exists():
            raise FileExistsError(f"Briefing da semana {week} já existe (imutável): {briefing}")
        md, info = self.market_for_week(week, live=live, briefing_dir=briefing, record=True)
        ctx = self._context(md, week)
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        fb = self._factbook(ctx, sorted(set(longs) | set(shorts)))
        prev_views, prev_out = self._previous_views(week)
        dd, vol = self.drawdown_and_vol()
        pmctx = PMContext(
            week=week, as_of=md.as_of, fund_name=self.cfg.fund.name, factbook=fb,
            universe_issuers=ctx.panel.assets[["issuer_name", "country", "sector"]],
            quant_alpha_z=ctx.alpha.composite_z, quant_candidates_long=longs,
            quant_candidates_short=shorts,
            current_book=ctx.current_positions, previous_views=prev_views,
            previous_pm_output=prev_out, research_notes=[], macro_notes=[], drawdown=dd,
            realized_vol_21d=vol, track_record_facts={}, kill_switch=self.kill_switch_active())
        paths = write_briefing_bundle(pmctx, briefing, mind_hint=mind)
        (self.week_dir(week) / "inputs").mkdir(parents=True, exist_ok=True)
        self.book.audit.append("WEEKLY_PREPARED", mind, info,
                               summary=f"Briefing da semana {week} preparado pela mente {mind}.",
                               week=week)
        return {"semana": week, "briefing": str(briefing), "arquivos": {k: str(v) for k, v in paths.items()},
                "candidatos_long": len(longs), "candidatos_short": len(shorts),
                "snapshot_hash": info["snapshot_hash"], "falhas_coleta": info.get("slow_failures", [])}

    def _previous_views(self, week: date):
        b = self.book
        weeks = [w for w in b.list_weeks() if w < week]
        if not weeks:
            return [], None
        pack = b.load_research_pack(weeks[-1])
        return (list(pack.views) if pack else []), None

    def _load_inputs(self, week: date, ctx, fb):
        from ..research.pm_agent import PMContext, load_pm_decision_file
        from ..research.providers.imported import load_imported_pack

        inputs = self.week_dir(week) / "inputs"
        pack, issues = load_imported_pack(inputs / "research_pack.json", week, ctx.snapshot_id, fb,
                                          as_of=week, cfg=self.cfg, news=list(ctx.md.news))
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        dd, vol = self.drawdown_and_vol()
        pmctx = PMContext(
            week=week, as_of=ctx.md.as_of, fund_name=self.cfg.fund.name, factbook=fb,
            universe_issuers=ctx.panel.assets[["issuer_name", "country", "sector"]],
            quant_alpha_z=ctx.alpha.composite_z, quant_candidates_long=longs,
            quant_candidates_short=shorts, current_book=ctx.current_positions,
            previous_views=[], previous_pm_output=None, research_notes=list(pack.notes),
            macro_notes=list(pack.macro), drawdown=dd, realized_vol_21d=vol,
            track_record_facts={}, kill_switch=self.kill_switch_active())
        out, pm_issues = load_pm_decision_file(inputs / "pm_decision.json", pmctx)
        return pack, issues, out, pm_issues, pmctx

    def validate_inputs(self, week: date) -> tuple[bool, list[str]]:
        from ..research.pm_agent import validate_inputs

        briefing = self.week_dir(week) / "briefing"
        md, _ = self.market_for_week(week, live=False, briefing_dir=briefing, record=False)
        ctx = self._context(md, week)
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        fb = self._factbook(ctx, sorted(set(longs) | set(shorts)))
        _pack, issues, _out, pm_issues, pmctx = self._load_inputs(week, ctx, fb)
        ok, extra = validate_inputs(self.week_dir(week), pmctx)
        all_issues = list(issues) + list(pm_issues) + list(extra)
        return ok and not any(i.startswith("ERRO") for i in all_issues), all_issues

    def weekly_decide(self, week: date, *, mind: str) -> dict:
        from ..research.pm_agent import to_bundle
        from .reports import render_weekly_report, write_report_files
        from .weekly import run_weekly_decision

        b = self.book
        if b.list_decisions(week):
            raise FileExistsError(f"A semana {week} já tem decisão gravada.")
        briefing = self.week_dir(week) / "briefing"
        md, info = self.market_for_week(week, live=False, briefing_dir=briefing, record=False)
        ctx = self._context(md, week)
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        fb = self._factbook(ctx, sorted(set(longs) | set(shorts)))
        pack, issues, out, pm_issues, _pmctx = self._load_inputs(week, ctx, fb)
        pack = pack.model_copy(update={"mind": mind})
        dd, _ = self.drawdown_and_vol()
        bundle = to_bundle(out, self.cfg, dd)
        outcome = run_weekly_decision(ctx, pack, bundle, version=b.next_version(week),
                                      live_weeks=self.live_weeks(),
                                      kill_switch=self.kill_switch_active(),
                                      audit_head_hash=b.audit_head())
        decision = outcome.decision.model_copy(update={"mind": mind})
        b.save_research_pack(pack, actor=mind)
        b.save_proposal(outcome.final)
        shadow_path = self.week_dir(week) / "shadow_quant.json"
        _write_json(shadow_path, outcome.shadow_quant.model_dump(mode="json"))
        b.audit.append("SHADOW_QUANT", "CDP", {"sha256": sha256_file(shadow_path)},
                       summary="Carteira-sombra só-quant gravada.", week=week)
        b.save_decision(decision)
        _write_json(self.week_dir(week) / "attempts.json",
                    {"path": outcome.path_taken, "attempts": outcome.attempts,
                     "input_issues": issues + pm_issues})
        prev_weeks = [w for w in b.list_weeks() if w < week]
        prev_prop = b.load_proposal(prev_weeks[-1]) if prev_weeks else None
        prev_pack = b.load_research_pack(prev_weeks[-1]) if prev_weeks else None
        md_txt, html = render_weekly_report(
            week, outcome.final, decision, out, prev_prop,
            list(prev_pack.views) if prev_pack else [], list(pack.views), [],
            outcome.shadow_quant, self.cfg.fund.name)
        report = write_report_files(self.reports_root / "weekly" / week.isoformat(), md_txt, html)
        p = outcome.final
        return {"semana": week, "mente": mind, "caminho": outcome.path_taken,
                "decisao": decision.approval_hash, "vol_ex_ante": p.risk.ex_ante_vol,
                "gross": p.risk.gross, "net": p.risk.net, "beta": p.risk.beta,
                "n_long": p.risk.n_long, "n_short": p.risk.n_short,
                "falhas_soft": [c.check_id for c in p.soft_failures], "relatorio": report,
                "execucao": f"fechamento de {week} (MOC) pela rotina diária"}

    # ------------------------------------------------------------------ diário
    def daily_close(self, session: date, *, live: bool = True) -> dict:
        from .daily import DailyRunner

        if not any(is_session(session, ex) for ex in ("BVMF", "XNYS", "XMEX")):
            return {"data": session, "status": "sem pregão"}
        store = self.store
        if live:
            store.catch_up(session)
        runner = DailyRunner(self.cfg, store, self.book, self.track(),
                             shadow_track=self.track(shadow=True), reports_root=self.reports_root)
        return runner.close(session)

    def daily_publish(self, session: date) -> dict:
        from .daily import DailyRunner

        runner = DailyRunner(self.cfg, self.store, self.book, self.track(),
                             shadow_track=self.track(shadow=True), reports_root=self.reports_root)
        return runner.publish(session)

    # ------------------------------------------------------------------ integridade
    def verify_all(self) -> tuple[bool, list[str]]:
        msgs: list[str] = []
        ok = True
        b = self.book
        r_ok, r_msgs = b.verify_integrity()
        ok &= r_ok
        msgs += [f"livro: {m}" for m in (r_msgs or ["íntegro"])]
        for shadow in (False, True):
            try:
                t_ok, t_msgs = self.track(shadow).verify()
            except Exception as exc:  # noqa: BLE001
                t_ok, t_msgs = True, [f"sem track record ({exc.__class__.__name__})"]
            ok &= t_ok
            label = "sombra" if shadow else "track record"
            msgs += [f"{label}: {m}" for m in (t_msgs or ["íntegro"])]
        try:
            s_ok, s_msgs = self.store.verify_chain()
            ok &= s_ok
            msgs += [f"dados: {m}" for m in (s_msgs or ["íntegros"])]
        except Exception as exc:  # noqa: BLE001
            msgs.append(f"dados: sem base de mercado ({exc.__class__.__name__})")
        return bool(ok), msgs

    def run_backtest(self, start: date, end: date | None, out: Path) -> dict:
        from ..backtest.engine import BacktestConfig, run_backtest

        md = self.store.load()
        res = run_backtest(md, self.cfg, BacktestConfig(start=start, end=end,
                                                        nav=self.cfg.fund.inception_nav_usd))
        out.mkdir(parents=True, exist_ok=True)
        res.daily.to_csv(out / "daily.csv")
        res.weekly.to_csv(out / "weekly.csv")
        res.ic.to_csv(out / "ic.csv")
        _write_json(out / "metrics.json", {"metrics": res.metrics, "notes": res.notes})
        return {"saida": str(out), "metricas": res.metrics}


def research_pack_hash(pack: ResearchPack) -> str:
    return pack.research_hash()


def is_decision_day(d: date) -> bool:
    return is_rebalance_day(d)


def frame_hash(df: pd.DataFrame) -> str:
    return sha256_obj(df.to_dict("split"))
