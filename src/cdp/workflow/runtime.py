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
from ..calendar import (
    chave_valida,
    is_rebalance_day,
    is_session,
    previous_data_session,
    previous_session,
)
from ..config import FundConfig, load_config
from ..contracts import ResearchPack
from ..hashing import sha256_file, sha256_obj
from ..market import MarketData
from .book import Book

PREPARE_MANIFEST = "prepare_manifest.json"
KILL_SWITCH_FILE = "KILL_SWITCH"
DECISION_CONFIG = "config_decisao.json"
"""Configuração do mandato vigente no ``decide`` (``book/<semana>/``), autenticada pelo
``config_hash`` da proposta: reconstruções posteriores (tese) usam a configuração da decisão."""
DEFAULT_TESES_ROOT = Path("docs/cdp/teses")
"""Pasta versionada das teses escritas pela mente fora do clone da rotina
(``<AAAA-MM-DD>.json``, mesmo schema de ``book/<semana>/tese/tese.json``)."""
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
    teses_root: Path | None = DEFAULT_TESES_ROOT
    """Rascunhos de tese entregues fora do clone da rotina (``None`` desliga a adoção)."""

    def now(self) -> datetime:
        """Relógio da rotina (UTC); a demonstração usa um relógio lógico determinístico."""
        return (self.clock() if self.clock is not None else datetime.now(UTC)).astimezone(UTC)

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def from_args(cls, args) -> Runtime:
        cfg = load_config(getattr(args, "config", None))
        return cls(cfg=cfg, book_root=Path(args.book), market_root=Path(args.market),
                   reports_root=Path(args.reports),
                   teses_root=Path(getattr(args, "teses", None) or DEFAULT_TESES_ROOT))

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
        at = self.now().isoformat()
        payload = {"on": on, "reason": reason, "by": by, "at": at, "created_at": at}
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

    def pre_inicio(self, d: date) -> bool:
        """``d`` antecede a data de início do mandato e o livro ainda não tem semana nem registro
        diário (fundo sem carteira: sem marcação, relatório diário nem monitor de risco; nenhum
        dia de montagem antes da data de início). Depende do livro, não só do calendário: a
        demonstração e os testes rodam livros históricos com a configuração real."""
        if d >= self.cfg.fund.inception_date:
            return False
        from .reinicio import chaves_vivas

        try:
            return not chaves_vivas(self)
        except OSError:  # pragma: no cover - disco
            return False

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

    def previous_booked(self, week: date):
        """Carteira efetivada mais recente ANTERIOR a ``week`` (a vigente na decisão da semana)."""
        return self.book._previous_booked(week)

    def decision_state(self, week: date):
        """Estado do livro no momento da decisão de ``week`` (para reconstruções posteriores).

        Devolve ``(booking anterior, pesos marcados, drawdown)`` como a decisão os via: o
        booking mais recente anterior à semana e os pesos e o drawdown do último registro
        diário anterior à semana (sem registro: ``None``, como o contexto do PM). Nunca usa o
        estado vivo posterior à decisão.
        """
        records = [r for r in self._records() if r.date < week]
        last = records[-1] if records else None
        drifted: dict[str, float] | None = None
        if last is not None and last.positions:
            drifted = {}
            for p in last.positions:
                drifted[p.issuer_id] = drifted.get(p.issuer_id, 0.0) + float(p.weight)
        drawdown = float(last.risk.drawdown) if last is not None else None
        return self.previous_booked(week), drifted, drawdown

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
        manifest_path = briefing_dir / PREPARE_MANIFEST
        prev = self.information_session(week)
        if not record and manifest_path.exists():
            # A reconstrução usa o pregão de dados gravado no prepare (nunca recalcula).
            try:
                raw_prev = json.loads(manifest_path.read_text(encoding="utf-8")).get(
                    "previous_session")
                if raw_prev:
                    prev = date.fromisoformat(str(raw_prev)[:10])
            except (OSError, ValueError):
                pass
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

    def information_session(self, week: date) -> date:
        """Pregão de dados anterior ao dia de montagem: com a seção ``execution``, o da união
        B3 | NYSE | BMV (ex.: um feriado só na B3 continua sendo pregão de dados); legado: o
        pregão anterior da B3."""
        if self.cfg.execution is not None:
            return previous_data_session(week)
        return previous_session(week)

    def decision_deadline(self, week: date) -> datetime:
        """Prazo efetivo da decisão no dia de montagem ``week`` (Brasília)."""
        from ..portfolio.execucao import prazo_efetivo

        return prazo_efetivo(week, self.cfg)

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

    def _pm_context(self, md: MarketData, ctx, week: date, fb, analysis_ts: datetime | None,
                    *, state: tuple[float | None, float | None] | None = None,
                    kill_switch: bool | None = None):
        """Contexto do PM; ``state``/``kill_switch`` substituem o estado vivo do livro
        (``(drawdown, vol realizada)`` e kill switch), para reconstruções da decisão."""
        from ..research.pm_agent import PMContext

        longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
        prev_views, prev_out, prev_week = self._previous_views(week)
        if state is None:
            dd_live, vol = self.drawdown_and_vol()
            dd = dd_live if self.last_record_date() else None
        else:
            dd, vol = state
        return PMContext(
            week=week, as_of=md.as_of, fund_name=self.cfg.fund.name, factbook=fb,
            universe_issuers=ctx.panel.assets[["issuer_name", "country", "sector"]],
            quant_alpha_z=ctx.alpha.composite_z, quant_candidates_long=longs,
            quant_candidates_short=shorts, current_book=ctx.current_positions,
            previous_views=prev_views, previous_pm_output=prev_out, research_notes=[],
            macro_notes=[], drawdown=dd, realized_vol_21d=vol, track_record_facts={},
            kill_switch=self.kill_switch_active() if kill_switch is None else kill_switch,
            cfg=self.cfg, news=list(md.news),
            realized_residual_returns=self._realized_residual(ctx, prev_week, week),
            analysis_ts=analysis_ts)

    def decision_pm_output(self, week: date, md: MarketData, ctx, info: dict, decision):
        """Decisão do PM VERIFICADA exatamente como o ``decide`` a usou, ou ``None``.

        ``ctx`` é o contexto da semana no estado do livro na hora da decisão (ver
        :meth:`decision_state`). Reconstrói o contexto do PM nesse estado (candidatos sobre a
        carteira vigente, drawdown e vol realizada do último registro diário anterior à semana)
        e reaplica a verificação do ``decide`` (``load_week_inputs``: evidências, guardrails de
        texto, abstenção e kill switch). Só aceita a saída cujo ``pm_output_hash`` confere com o
        ``pm_decision_hash`` gravado na decisão — o kill switch da hora da decisão não é
        gravado, então as duas hipóteses são testadas. Sem conferência ⇒ ``None`` (o chamador
        publica visões e postura do PM como ausentes; nunca a decisão bruta da mente).
        """
        from ..research.pm_agent import load_week_inputs, pm_factbook, pm_output_hash

        target = getattr(decision, "pm_decision_hash", None)
        if not target:
            return None
        records = [r for r in self._records() if r.date < week]
        last = records[-1] if records else None
        state = ((float(last.risk.drawdown), last.risk.realized_vol_21d) if last is not None
                 else (None, None))
        try:
            longs, shorts = self._candidates(ctx, self.cfg.research.top_n_candidates)
            fb = self._factbook(ctx, sorted(set(longs) | set(shorts)))
            for ks in (False, True):
                pmctx = self._pm_context(md, ctx, week, fb, self._analysis_ts(info),
                                         state=state, kill_switch=ks)
                _pack, out, _issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx,
                                                               now=decision.decided_at)
                if pm_output_hash(out, pm_factbook(pm_ctx)) == target:
                    return out
        except Exception:  # noqa: BLE001 - reconstrução explicativa; sem conferência ⇒ None
            return None
        return None

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

        if not chave_valida(week, self.cfg):
            from ..calendar import regra

            rule = ("o último pregão da semana na NYSE" if regra(self.cfg) == "LAST_US_SESSION"
                    else "o primeiro pregão da semana na B3")
            raise ValueError(f"{week} não é {rule} nem a data de início do mandato.")
        self.book.check_key(week)  # livro aberto na data de início: nada anterior a ela
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

    def validate_inputs(self, week: date, *, mind: str | None = None,
                        so_pesquisa: bool = False) -> tuple[bool, list[str]]:
        from ..research.pm_agent import validate_inputs

        _md, _info, _ctx, _fb, pmctx = self._week_state(week)
        return validate_inputs(self.week_dir(week), pmctx, expected_mind=mind, now=self.now(),
                               only_research=so_pesquisa)

    def weekly_decide(self, week: date, *, mind: str) -> dict:
        from ..research.pm_agent import load_week_inputs, pm_factbook, to_bundle
        from .autonomy import make_autonomous_decision
        from .reports import render_weekly_report, write_report_files
        from .weekly import run_weekly_decision

        b = self.book
        if b.list_decisions(week):
            raise FileExistsError(f"A semana {week} já tem decisão gravada.")
        # Um único instante para a decisão inteira: o prazo é conferido nele e ele é o
        # ``decided_at``/``created_at`` da proposta e da decisão. A decisão é função só dos
        # insumos disponíveis neste instante (dados da preparação e arquivos da mente); o cálculo
        # posterior não usa informação nova, e o carimbo nunca passa do prazo conferido.
        t_dec = self.now()
        if self.cfg.execution is not None:
            deadline = self.decision_deadline(week)
            if t_dec > deadline:
                raise ValueError(
                    f"Prazo efetivo da decisão de {week} vencido "
                    f"({deadline:%H:%M} de Brasília): a decisão não é "
                    "gravada depois do prazo (o fechamento seria conhecido); a carteira vigente "
                    "é mantida até o próximo dia de montagem.")
        _md, info, ctx, _fb, pmctx = self._week_state(week)
        pack, out, issues, pm_ctx = load_week_inputs(self.week_dir(week), pmctx, now=t_dec)
        if out.mind != mind and not out.abstain:
            issues.append(f"mind declarado {out.mind!r} difere do informado {mind!r}")
        pack = pack.model_copy(update={"mind": out.mind or mind})
        pfb = pm_factbook(pm_ctx)
        bundle = to_bundle(out, self.cfg, pm_ctx.drawdown, factbook=pfb)
        outcome = run_weekly_decision(ctx, pack, bundle, version=b.next_version(week),
                                      live_weeks=self.live_weeks(),
                                      kill_switch=self.kill_switch_active(),
                                      audit_head_hash=b.audit_head(),
                                      decided_at=t_dec, created_at=t_dec)
        inputs_dir = self.week_dir(week) / "inputs"
        b.audit.append("WEEKLY_INPUTS", pack.mind or mind,
                       {p.name: sha256_file(p) for p in sorted(inputs_dir.glob("*.json"))},
                       summary=f"Arquivos brutos da mente para {week} (hash).", week=week)
        b.save_research_pack(pack, actor=pack.mind or mind)
        b.save_proposal(outcome.final)
        shadow_path = self.week_dir(week) / "shadow_quant.json"
        _write_json(shadow_path, outcome.shadow_quant.model_dump(mode="json"))
        # Configuração da decisão (autenticada pelo config_hash da proposta): a tese da
        # carteira reconstrói a semana com ela mesmo após uma recalibração do mandato. Sem
        # ``sort_keys``: a ordem dos dicionários (ex.: pesos dos sinais) define a ordem das
        # somas, e a reconstrução precisa ser idêntica bit a bit.
        (self.week_dir(week) / DECISION_CONFIG).write_text(
            json.dumps(self.cfg.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        b.audit.append("SHADOW_QUANT", "CDP", {"sha256": sha256_file(shadow_path)},
                       summary="Carteira-sombra só-quant gravada.", week=week)
        # A decisão é ancorada na trilha DEPOIS da proposta gravada (nunca retroativa).
        d0 = outcome.decision
        decision = make_autonomous_decision(
            outcome.final, research_hash=outcome.research_hash,
            pm_decision_hash=d0.pm_decision_hash or bundle.pm_output_hash,
            rationale=d0.rationale, journal=d0.journal, conviction=d0.conviction,
            decided_at=t_dec, audit_head_hash=b.audit_head(),
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
        if self.pre_inicio(session):
            return self._daily_pre_inicio(session, live=live)
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

    def _daily_pre_inicio(self, session: date, *, live: bool) -> dict:
        """Antes da data de início (fundo sem carteira): sem marcação, registro nem relatório;
        só o incremento da base de mercado (dados públicos) até ``session``, ancorado na trilha,
        para a carteira inaugural partir de dados em dia."""
        inicio = self.cfg.fund.inception_date
        out: dict = {"data": session, "status": "pré-início",
                     "motivo": (f"carteira inaugural em {inicio:%d/%m/%Y}, ao preço de "
                                "fechamento; sem marcação nem relatório antes do início")}
        if not live:
            return out
        from ..data.store import DataNotReadyError, StoreLockedError

        store = self.store
        try:
            increments = store.catch_up(session)
        except (DataNotReadyError, StoreLockedError) as exc:
            out["dados_de_mercado"] = {"status": "não prontos", "motivo": str(exc),
                                       "acao": "tente de novo em alguns minutos"}
            return out
        self._anchor_increments(increments)
        out["dados_de_mercado"] = {
            "status": "atualizados",
            "incrementos": [inc.session_date for inc in increments or []],
            "ultimo_pregao": store.last_date()}
        return out

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

    # ------------------------------------------------------------------ tese da carteira
    def thesis_prepare(self, week: date) -> dict:
        """Fatos, análise e briefing da tese da carteira decidida (``book/<semana>/tese/``)."""
        from .tese import prepare_thesis

        return prepare_thesis(self, week)

    def validate_thesis(self, week: date) -> dict:
        """Valida ``tese.json`` da mente SEM publicar (``ok``, ``problemas``, ``cobertura``)."""
        from .tese import validate_thesis

        return validate_thesis(self, week)

    def thesis_publish(self, week: date) -> dict:
        """Publica a tese (mente ou automática), imutável, com evento ``WEEKLY_THESIS``."""
        from .tese import publish_thesis

        return publish_thesis(self, week)

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
        e_ok, e_msgs = self.verify_execucao(b)
        ok &= e_ok
        msgs += [f"execução: {m}" for m in e_msgs]
        from .notas import published_notes, verify_notes

        n_msgs = verify_notes(self)
        ok &= not n_msgs
        if n_msgs or published_notes(self.book_root):
            msgs += [f"notas: {m}" for m in (n_msgs or ["íntegras"])]
        return bool(ok), msgs

    def _config_da_decisao(self, week: date, proposal) -> FundConfig | None:
        """Mandato que governou a decisão (e a efetivação) da semana: o atual se o hash confere;
        senão o arquivado na semana (``config_decisao.json``) ou no histórico de mandatos,
        autenticados pelo ``config_hash`` da proposta. ``None`` se indisponível."""
        from ..config import archived_config, book_historico_dir, load_archived_config

        if proposal.config_hash == self.cfg.config_hash():
            return self.cfg
        arq = load_archived_config(self.week_dir(week) / DECISION_CONFIG, proposal.config_hash)
        if arq is None:
            arq = archived_config(proposal.config_hash, book_historico_dir(self.book_root))
        return arq.cfg if arq is not None else None

    def verify_execucao(self, b: Book | None = None) -> tuple[bool, list[str]]:
        """Confere cada efetivação com execução no fechamento contra a regra determinística
        recalculada com os dados do pregão (:func:`cdp.portfolio.execucao.conferir_efetivacao`):
        nenhuma linha acima da capacidade pelo volume realizado, nem em mercado sem fechamento
        elegível, emissor congelado, depois do corte MOC ou abaixo da banda. Semanas sem a seção
        ``execution`` no mandato da decisão ficam fora (regra anterior)."""
        from ..portfolio.execucao import conferir_efetivacao

        b = b or self.book
        md: MarketData | None = None
        n = 0
        problems: list[str] = []
        for w in b.list_weeks():
            if not (self.week_dir(w) / "booked.json").exists():
                continue
            try:
                entry = b.load_booked(w)
            except ValueError:
                continue  # integridade do arquivo já acusada pelo livro
            if entry is None:
                continue
            prop = next((p for p in b.list_proposals(w)
                         if p.proposal_id == entry.proposal_id), None)
            if prop is None:
                continue
            cfg_w = self._config_da_decisao(w, prop)
            if cfg_w is None or cfg_w.execution is None:
                continue
            dec = b.load_decision(w, prop.version)
            if md is None:
                try:
                    md = self.store.load()
                except Exception as exc:  # noqa: BLE001 - base ausente nesta cópia
                    return True, [f"sem base de mercado para conferir as efetivações "
                                  f"({exc.__class__.__name__})"]
            found = conferir_efetivacao(entry, prop, dec.decided_at if dec else None,
                                        b.holdings_before(w), md, cfg_w)
            problems += [f"{w}: {m}" for m in found]
            n += 1
        if problems:
            return False, problems
        if n:
            return True, [("1 efetivação conferida" if n == 1 else
                           f"{n} efetivações conferidas")
                          + " contra a execução esperada no fechamento"]
        return True, []

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
