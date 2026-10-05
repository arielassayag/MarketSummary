"""Orquestração operacional do CDP (usada pela CLI, pelas rotinas agendadas e pelo app).

Mantém a reprodutibilidade: a etapa ``weekly prepare`` grava, com hash, tudo o que foi coletado
no momento da análise (barra intradiária e dados lentos); ``weekly decide`` reconstrói exatamente
o mesmo ``MarketData`` a partir desses arquivos e falha se qualquer hash divergir.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
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
    store_override: object | None = None
    clock: Callable[[], datetime] | None = field(default=None, repr=False)

    def now(self) -> datetime:
        """Relógio da rotina (UTC); a demonstração usa um relógio lógico determinístico."""
        return (self.clock() if self.clock is not None else datetime.now(UTC)).astimezone(UTC)

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
        if self.store_override is not None:
            return self.store_override
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
        payload = {"on": on, "reason": reason, "by": by, "at": self.now().isoformat()}
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
                self._anchor_increments(store.catch_up(prev))
            md = store.load(as_of=prev)
            info: dict = {"week": week, "previous_session": prev,
                          "store_content_hash": md.manifest.content_hash(), "live": live,
                          "config_hash": self.cfg.config_hash(),
                          "prepared_at": self.now()}
            if live:
                captured = self.now()
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

    def _previous_week(self, week: date) -> date | None:
        weeks = [w for w in self.book.list_weeks() if w < week]
        return weeks[-1] if weeks else None

    def _previous_views(self, week: date):
        """Visões e decisão estruturada da semana anterior (para a avaliação da semana)."""
        from ..research.pm_agent import PM_INPUT, PMDecisionOutput

        prev = self._previous_week(week)
        if prev is None:
            return [], None, None
        pack = self.book.load_research_pack(prev)
        out = None
        path = self.week_dir(prev) / "inputs" / PM_INPUT
        if path.exists():
            try:
                out = PMDecisionOutput.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                out = None
        views = list(pack.views) if pack else []
        if out is not None and not out.abstain:
            from ..research.pm_agent import pm_output_to_views

            views = list(pm_output_to_views(out, self.cfg)[0]) + views
        return views, out, prev

    @staticmethod
    def _realized_residual(ctx, since: date | None, week: date) -> pd.Series | None:
        """Σ resíduos diários do modelo de risco entre a efetivação anterior e a semana atual."""
        if since is None:
            return None
        sr = ctx.model.specific_returns
        idx = pd.to_datetime(sr.index)
        mask = (idx > pd.Timestamp(since)) & (idx < pd.Timestamp(week))
        if not mask.any():
            return None
        return sr.loc[mask].sum(min_count=1)

    def _pm_context(self, md: MarketData, ctx, week: date, fb, analysis_ts: datetime | None):
        from ..research.pm_agent import PMContext

        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        prev_views, prev_out, prev_week = self._previous_views(week)
        dd, vol = self.drawdown_and_vol()
        return PMContext(
            week=week, as_of=md.as_of, fund_name=self.cfg.fund.name, factbook=fb,
            universe_issuers=ctx.panel.assets[["issuer_name", "country", "sector"]],
            quant_alpha_z=ctx.alpha.composite_z, quant_candidates_long=longs,
            quant_candidates_short=shorts, current_book=ctx.current_positions,
            previous_views=prev_views, previous_pm_output=prev_out, research_notes=[],
            macro_notes=[], drawdown=dd if self.last_record_date() else None,
            realized_vol_21d=vol, track_record_facts={}, kill_switch=self.kill_switch_active(),
            cfg=self.cfg, news=list(md.news),
            realized_residual_returns=self._realized_residual(ctx, prev_week, week),
            analysis_ts=analysis_ts)

    @staticmethod
    def _analysis_ts(info: dict) -> datetime | None:
        raw = info.get("captured_at") or info.get("prepared_at")
        return datetime.fromisoformat(str(raw)) if raw else None

    def _week_state(self, week: date):
        """Reconstrói (com verificação de hash) o estado exato do ``prepare`` da semana."""
        briefing = self.week_dir(week) / "briefing"
        md, info = self.market_for_week(week, live=False, briefing_dir=briefing, record=False)
        ctx = self._context(md, week)
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        fb = self._factbook(ctx, sorted(set(longs) | set(shorts)))
        pmctx = self._pm_context(md, ctx, week, fb, self._analysis_ts(info))
        return md, info, ctx, fb, pmctx

    def weekly_prepare(self, week: date, *, mind: str, live: bool = True) -> dict:
        from ..research.pm_agent import write_briefing_bundle

        if first_session_of_week(week) != week:
            raise ValueError(f"{week} não é o primeiro pregão da semana na B3.")
        briefing = self.week_dir(week) / "briefing"
        if (briefing / PREPARE_MANIFEST).exists():
            raise FileExistsError(f"Briefing da semana {week} já existe (imutável): {briefing}")
        md, info = self.market_for_week(week, live=live, briefing_dir=briefing, record=True)
        ctx = self._context(md, week)
        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        fb = self._factbook(ctx, sorted(set(longs) | set(shorts)))
        pmctx = self._pm_context(md, ctx, week, fb, self._analysis_ts(info))
        paths = write_briefing_bundle(pmctx, briefing, mind_hint=mind)
        (self.week_dir(week) / "inputs").mkdir(parents=True, exist_ok=True)
        self.book.audit.append("WEEKLY_PREPARED", mind, info,
                               summary=f"Briefing da semana {week} preparado pela mente {mind}.",
                               week=week)
        return {"semana": week, "briefing": str(briefing),
                "arquivos": {k: str(v) for k, v in paths.items()},
                "entradas": str(self.week_dir(week) / "inputs"),
                "candidatos_long": len(longs), "candidatos_short": len(shorts),
                "emissores_elegiveis": int(ctx.panel.assets["eligible"].sum()),
                "barra_provisoria": bool(info.get("live")),
                "snapshot_hash": info["snapshot_hash"], "falhas_coleta": info.get("slow_failures", [])}

    def validate_inputs(self, week: date, *, mind: str | None = None) -> tuple[bool, list[str]]:
        from ..research.pm_agent import validate_inputs

        _md, _info, _ctx, _fb, pmctx = self._week_state(week)
        return validate_inputs(self.week_dir(week), pmctx, expected_mind=mind, now=self.now())

    def weekly_decide(self, week: date, *, mind: str) -> dict:
        from ..research.pm_agent import load_week_inputs, pm_factbook, to_bundle
        from .autonomy import make_autonomous_decision
        from .reports import render_weekly_report, write_report_files
        from .weekly import run_weekly_decision

        b = self.book
        if b.list_decisions(week):
            raise FileExistsError(f"A semana {week} já tem decisão gravada.")
        _md, info, ctx, _fb, pmctx = self._week_state(week)
        pack, out, issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx, now=self.now())
        if out.mind != mind and not out.abstain:
            issues.append(f"mind declarado {out.mind!r} difere do informado {mind!r}")
        pack = pack.model_copy(update={"mind": out.mind or mind})
        pfb = pm_factbook(pm_ctx)
        bundle = to_bundle(out, self.cfg, pm_ctx.drawdown, factbook=pfb)
        outcome = run_weekly_decision(ctx, pack, bundle, version=b.next_version(week),
                                      live_weeks=self.live_weeks(),
                                      kill_switch=self.kill_switch_active(),
                                      audit_head_hash=b.audit_head(),
                                      decided_at=self.now(), created_at=self.now())
        inputs_dir = self.week_dir(week) / "inputs"
        b.audit.append("WEEKLY_INPUTS", pack.mind or mind,
                       {p.name: sha256_file(p) for p in sorted(inputs_dir.glob("*.json"))},
                       summary=f"Arquivos brutos da mente para {week} (hash).", week=week)
        b.save_research_pack(pack, actor=pack.mind or mind)
        b.save_proposal(outcome.final)
        shadow_path = self.week_dir(week) / "shadow_quant.json"
        _write_json(shadow_path, outcome.shadow_quant.model_dump(mode="json"))
        b.audit.append("SHADOW_QUANT", "CDP", {"sha256": sha256_file(shadow_path)},
                       summary="Carteira-sombra só-quant gravada.", week=week)
        # A decisão é ancorada na trilha DEPOIS da proposta gravada (nunca retroativa).
        d0 = outcome.decision
        decision = make_autonomous_decision(
            outcome.final, research_hash=outcome.research_hash,
            pm_decision_hash=d0.pm_decision_hash or bundle.pm_output_hash,
            rationale=d0.rationale, journal=d0.journal, conviction=d0.conviction,
            decided_at=self.now(), audit_head_hash=b.audit_head(),
        ).model_copy(update={"mind": pack.mind})
        b.save_decision(decision)
        _write_json(self.week_dir(week) / "attempts.json",
                    {"path": outcome.path_taken, "attempts": outcome.attempts,
                     "input_issues": issues})
        prev_week = self._previous_week(week)
        prev_prop = b.load_proposal(prev_week) if prev_week else None
        prev_views = list(pm_ctx.previous_views)
        week_records = [r for r in self._records() if prev_week and prev_week <= r.date < week]
        rr = pm_ctx.realized_residual_returns
        md_txt, html = render_weekly_report(
            week, outcome.final, decision, out, prev_prop, prev_views,
            list(bundle.views) + list(pack.views),
            week_records, outcome.shadow_quant, self.cfg.fund.name, factbook=pfb, cfg=self.cfg,
            attempts=outcome.attempts, path_taken=outcome.path_taken,
            realized_residual=(None if rr is None else
                               {k: float(v) for k, v in rr.dropna().items()}))
        report = write_report_files(self.reports_root / "weekly" / week.isoformat(), md_txt, html)
        b.audit.append("WEEKLY_REPORT", "CDP", report,
                       summary=f"Relatório semanal {week} publicado.", week=week)
        p = outcome.final
        return {"semana": week, "mente": pack.mind, "caminho": outcome.path_taken,
                "postura": bundle.posture, "abstencao": bundle.abstain,
                "decisao": decision.approval_hash, "vol_ex_ante": p.risk.ex_ante_vol,
                "gross": p.risk.gross, "net": p.risk.net, "beta": p.risk.beta,
                "n_long": p.risk.n_long, "n_short": p.risk.n_short,
                "falhas_soft": [c.check_id for c in p.soft_failures],
                "apontamentos_entrada": issues, "relatorio": report,
                "analise": info.get("captured_at") or info.get("prepared_at"),
                "execucao": f"fechamento de {week} (MOC) pela rotina diária"}

    def weekly_preview(self, week: date, *, mind: str) -> dict:
        """Prévia do livro da semana SEM gravar nada (revisão pré-trade da mente).

        Roda exatamente o pipeline do ``decide`` (pesquisa + decisão do PM + otimizador + gates)
        sobre os arquivos de ``inputs/`` e devolve as posições com a visão de cada nome e os
        conflitos (posição contrária à visão da pesquisa/PM). A mente ajusta só juízos ordinais
        (visões e exclusões) — números continuam vindo do código.
        """
        from ..research.pm_agent import load_week_inputs, pm_factbook, to_bundle
        from .weekly import run_weekly_decision

        _md, _info, ctx, _fb, pmctx = self._week_state(week)
        pack, out, issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx, now=self.now())
        bundle = to_bundle(out, self.cfg, pm_ctx.drawdown, factbook=pm_factbook(pm_ctx))
        outcome = run_weekly_decision(ctx, pack, bundle, version=self.book.next_version(week),
                                      live_weeks=self.live_weeks(),
                                      kill_switch=self.kill_switch_active(),
                                      decided_at=self.now(), created_at=self.now())
        stance: dict[str, int] = {}
        for v in list(pack.views) + list(bundle.views):
            if v.score != 0:
                stance[v.issuer_id] = v.score  # a visão do PM (última) prevalece
        p = outcome.final
        rows, conflicts = [], []
        for pos in sorted(p.positions, key=lambda x: -abs(x.weight)):
            st = stance.get(pos.issuer_id)
            row = {"emissor": pos.issuer_id, "peso": round(pos.weight, 5), "pais": pos.country,
                   "setor": pos.sector, "alpha_z": pos.alpha_z, "visao": st,
                   "risco": pos.risk_contribution}
            rows.append(row)
            if st is not None and st * pos.weight < 0:
                conflicts.append(row)
        shadow = {x.issuer_id: x.weight for x in outcome.shadow_quant.positions}
        return {"semana": week, "caminho": outcome.path_taken, "postura": bundle.posture,
                "vol_ex_ante": p.risk.ex_ante_vol, "gross": p.risk.gross, "net": p.risk.net,
                "beta": p.risk.beta, "n_long": p.risk.n_long, "n_short": p.risk.n_short,
                "falhas_hard": [c.check_id for c in p.hard_failures],
                "falhas_soft": [c.check_id for c in p.soft_failures],
                "apontamentos_entrada": issues, "conflitos_visao_posicao": conflicts,
                "posicoes": rows, "sombra_quant": shadow,
                "tentativas": outcome.attempts}

    # ------------------------------------------------------------------ diário
    def _records(self, shadow: bool = False) -> list:
        try:
            return self.track(shadow).records()
        except Exception:  # noqa: BLE001 - sem série antes da primeira efetivação
            return []

    def _runner(self, store=None):
        from .daily import DailyRunner
        from .track_record import SHADOW_RECORD_EVENT, TrackRecord

        shadow = TrackRecord(self.book_root / "track_record_shadow",
                             audit_event=SHADOW_RECORD_EVENT)
        return DailyRunner(self.cfg, store or self.store, self.book, self.track(),
                           shadow_track=shadow)

    def _daily_factbook(self, session: date, record, store=None):
        from ..research.commentary import build_daily_factbook, build_market_day_facts

        history = [r for r in self._records() if r.date < session]
        md = (store or self.store).load(as_of=session)
        mkt = build_market_day_facts(md.benchmarks, md.fx, session)
        return build_daily_factbook(record, history, mkt, cfg=self.cfg), history

    def _anchor_increments(self, increments) -> None:
        """Ancora cada incremento diário de dados na trilha (detecta truncamento da cauda)."""
        for inc in increments or []:
            self.book.audit.append(
                "MARKET_INCREMENT", "CDP — rotina diária",
                {"session_date": inc.session_date, "manifest_hash": inc.manifest_hash},
                summary=f"Incremento de mercado de {inc.session_date} gravado.")

    def daily_dir(self, session: date) -> Path:
        return self.reports_root / "daily" / session.isoformat()

    def daily_close(self, session: date, *, live: bool = True, mind: str | None = None) -> dict:
        """Fechamento oficial: efetiva a decisão da semana (MOC), marca, mede risco e atribui.

        Grava o registro diário encadeado e os insumos do comentário da mente
        (``reports/daily/<data>/facts.md``); a publicação vem depois (``daily publish``).
        """
        from ..research.commentary import factbook_json, write_daily_commentary_inputs
        from .daily import NoBookError, NoSessionError

        if not any(is_session(session, ex) for ex in ("BVMF", "XNYS", "XMEX")):
            return {"data": session, "status": "sem pregão"}
        store = self.store
        if live:
            from ..data.store import DataNotReadyError, StoreLockedError

            try:
                increments = store.catch_up(session)
            except (DataNotReadyError, StoreLockedError) as exc:
                return {"data": session, "status": "dados não prontos",
                        "motivo": str(exc), "acao": "tente de novo em alguns minutos"}
            self._anchor_increments(increments)
        runner = self._runner(store)
        try:
            res = runner.run_session(session)
        except NoSessionError as exc:
            return {"data": session, "status": "sem pregão", "motivo": str(exc)}
        except NoBookError as exc:
            return {"data": session, "status": "sem carteira efetivada", "motivo": str(exc)}
        rec = res.record
        fb, _history = self._daily_factbook(session, rec, store)
        out_dir = self.daily_dir(session)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "factbook.json").write_text(factbook_json(fb), encoding="utf-8")
        paths = write_daily_commentary_inputs(out_dir, rec, fb, mind_hint=mind, overwrite=True)
        return {"data": session, "status": "registrado", "registro": rec.record_hash,
                "nav_usd": rec.nav_end_usd, "retorno_dia": rec.ret,
                "efetivacao": (res.booked.proposal_id if res.booked is not None else None),
                "alertas": list(rec.alerts), "fatos": {k: str(v) for k, v in paths.items()},
                "proximo_passo": (f"escreva {out_dir / 'comentario.json'} e rode "
                                  f"`cdp daily publish --date {session}`")}

    def daily_publish(self, session: date) -> dict:
        """Valida o comentário da mente e publica o relatório diário (imutável)."""
        from ..research.commentary import COMMENTARY_JSON, load_commentary_file
        from .reports import render_daily_report, write_report_files

        rec = self.track().get(session)
        if rec is None:
            raise ValueError(f"Sem registro diário em {session}: rode `cdp daily close` antes.")
        fb, history = self._daily_factbook(session, rec)
        out_dir = self.daily_dir(session)
        comment_md, issues = load_commentary_file(out_dir / COMMENTARY_JSON, fb, record=rec)
        md_txt, html = render_daily_report(rec, history, comment_md, self.cfg.fund.name,
                                           cfg=self.cfg)
        report = write_report_files(out_dir, md_txt, html)
        self.book.audit.append("DAILY_REPORT", "CDP", {**report, "record": rec.record_hash,
                                                       "commentary_issues": issues},
                               summary=f"Relatório diário {session} publicado.")
        return {"data": session, "relatorio": report, "apontamentos_comentario": issues,
                "comentario_da_mente": not issues}

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
