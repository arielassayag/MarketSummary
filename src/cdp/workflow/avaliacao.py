"""Coortes prospectivas de avaliação: só código sela sinais e resultados, nunca a mente.

A base residual é congelada antes da otimização. Resultados usam B congelado, retornos
macro observados e WLS dos retornos restantes, sem preencher fatores/dias ausentes. Estes
anexos não alteram carteira, mandato, fase nem geram probabilidades de escores ordinais.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ..alpha.views import is_autonomous_view
from ..calendar import is_session, next_rebalance_after
from ..contracts import Decision, ResearchPack, View, ViewSource
from ..hashing import combine_hashes, sha256_file, sha256_obj, sha256_text
from ..portfolio.execucao import MIC_PAI, janela_execucao, mic_da_linha
from .book import Book, _write_exclusive
from .ledger import cross_sectional_factor_returns

if TYPE_CHECKING:
    from .weekly import PMBundle, WeekContext

POLICY = "cdp.avaliacao.residual_base_wls_macro/v1"
ENABLE_FILE = "avaliacao_manifest.json"
FOLDER = "avaliacao"
SIGNALS_FILE = "sinais.json"
BINDING_FILE = "vinculo.json"
OUTCOME_FILE = "outcome.json"
ENABLE_EVENT = "AVALIACAO_HABILITADA"
SIGNALS_EVENT = "AVALIACAO_SINAIS"
BINDING_EVENT = "AVALIACAO_VINCULO"
OUTCOME_EVENT = "AVALIACAO_OUTCOME"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Frame(_Strict):
    index: list[str]
    columns: list[str]
    values: list[list[float | None]]

    @model_validator(mode="after")
    def _shape(self):
        if len(set(self.index)) != len(self.index) or len(set(self.columns)) != len(self.columns):
            raise ValueError("índices/colunas duplicados")
        if len(self.index) != len(self.values) or any(len(r) != len(self.columns) for r in self.values):
            raise ValueError("dimensão de matriz inválida")
        return self

    def frame(self, *, dates: bool = False) -> pd.DataFrame:
        idx = pd.to_datetime(self.index) if dates else self.index
        return pd.DataFrame(self.values, index=idx, columns=self.columns, dtype=float)


def _finite(x: Any) -> float | None:
    return float(x) if x is not None and pd.notna(x) and math.isfinite(float(x)) else None


def _frame(df: pd.DataFrame, *, dates: bool = False) -> Frame:
    return Frame(index=[str(x.date()) if dates else str(x) for x in df.index],
                 columns=list(map(str, df.columns)),
                 values=[[_finite(x) for x in row] for row in df.to_numpy()])


class Signal(_Strict):
    issuer_id: str
    channel: Literal["quant", "pesquisa_ai", "mente_final"]
    score: float | None
    authorship: Literal["confirmed", "absent", "external", "not_applicable"] = "not_applicable"
    confirmed_mind: str | None = None
    forecasts: list[dict[str, Any]] = []
    original_authorship: list[dict[str, Any]] = []
    reason: str = ""


class Cohort(_Strict):
    schema_version: Literal["cdp.avaliacao.sinais/v1"] = "cdp.avaliacao.sinais/v1"
    policy: Literal[POLICY] = POLICY
    week: date
    end: date
    data_cutoff: datetime
    committed_at: datetime
    deadline: datetime
    end_close: datetime
    mind: str
    original_minds: dict[str, str | None]
    original_inputs: dict[str, str]
    input_hashes: dict[str, str]
    research_pack_hash: str
    research_hash: str
    pm_output_hash: str
    snapshot_hash: str
    config_hash: str
    is_synthetic: bool
    data_notice: str
    base_as_of: date
    exposures: Frame
    required_macro: list[str] = []
    specific_var: dict[str, float | None]
    sessions: dict[str, list[str]]
    primary_lines: dict[str, dict[str, str]]
    signals: list[Signal]

    @field_validator("data_cutoff", "committed_at", "deadline", "end_close")
    @classmethod
    def _tz(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("instante sem fuso")
        return value

    @model_validator(mode="after")
    def _coherent(self):
        if self.end <= self.week or self.base_as_of > self.week:
            raise ValueError("intervalo/base residual inválidos")
        if self.committed_at < self.data_cutoff:
            raise ValueError("selo anterior ao corte da decisão")
        keys = [(s.channel, s.issuer_id) for s in self.signals]
        if len(keys) != len(set(keys)):
            raise ValueError("sinal duplicado")
        if self.is_synthetic and "DADOS SIMULADOS" not in self.data_notice:
            raise ValueError("aviso de dados simulados ausente")
        assets = set(self.exposures.index)
        if len(self.required_macro) != len(set(self.required_macro)) or any(
                not m.startswith("macro:") for m in self.required_macro):
            raise ValueError("fatores macro configurados inválidos")
        if assets != set(self.sessions) or assets != set(self.specific_var) or assets != set(self.primary_lines):
            raise ValueError("universos da base residual divergentes")
        for dates in self.sessions.values():
            days = pd.to_datetime(dates)
            if days.has_duplicates or not days.is_monotonic_increasing or any(
                    not self.week < d.date() <= self.end for d in days):
                raise ValueError("sessões fora do horizonte")
        if set(self.original_inputs) != set(self.input_hashes) or any(
                sha256_text(raw) != self.input_hashes[name] for name, raw in self.original_inputs.items()):
            raise ValueError("texto bruto não confere com hash original")
        observed, raw_json = {}, {}
        for name, text in self.original_inputs.items():
            try:
                value = json.loads(text)
                raw_json[name] = value if isinstance(value, dict) else {}
            except ValueError:
                raw_json[name] = {}
            declared = raw_json[name].get("mind")
            observed[name] = declared if isinstance(declared, str) else None
            if declared is not None and declared != self.mind:
                raise ValueError("mind bruto difere do executor")
        if self.original_minds != observed:
            raise ValueError("mind observado não confere com o payload original")
        for s in self.signals:
            if (s.authorship == "confirmed") != (s.confirmed_mind == self.mind):
                raise ValueError("atribuição da mente incoerente")
            if s.channel != "quant":
                views = [View.model_validate(v) for v in s.forecasts]
                chosen = [v for v in views if v.source == ViewSource.PM] or views
                state, confirmed = _authorship(chosen, self.mind, observed, raw_json)
                if (s.authorship, s.confirmed_mind) != (state, confirmed):
                    raise ValueError("atribuição não reconcilia com autoria original")
        return self

    @property
    def prospective(self) -> bool:
        return self.committed_at <= self.deadline


class Binding(_Strict):
    schema_version: Literal["cdp.avaliacao.vinculo/v1"] = "cdp.avaliacao.vinculo/v1"
    cohort_hash: str
    approval_hash: str
    proposal_hash: str
    path_taken: str


class Outcome(_Strict):
    schema_version: Literal["cdp.avaliacao.outcome/v1"] = "cdp.avaliacao.outcome/v1"
    cohort_hash: str
    approval_hash: str
    week: date
    end: date
    recorded_at: datetime
    daily_record_hash: str
    market_hash: str
    market_files: dict[str, str]
    returns: Frame
    macro_returns: Frame
    initial_price_usd: dict[str, float | None]
    end_primary_lines: dict[str, str | None]
    residual_returns: dict[str, float | None]
    reasons: dict[str, str]

    @field_validator("recorded_at")
    @classmethod
    def _tz(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("instante sem fuso")
        return value


def _read(path: Path, cls):
    return cls.model_validate_json(path.read_text(encoding="utf-8"))


def _write(path: Path, value: BaseModel) -> None:
    text = json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
                      indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"conflito em anexo imutável: {path}")
        return
    _write_exclusive(path, text)


def _payload(path: Path, value: BaseModel) -> dict:
    return {"sha256": sha256_file(path), "content_hash": sha256_obj(value)}


def _anchor(book: Book, path: Path, value: BaseModel, event: str, week: date, at: datetime) -> None:
    payload = _payload(path, value)
    found = [e for e in book.audit.events() if e.event_type == event and e.week == week]
    if found:
        if len(found) != 1 or found[0].payload_hash != sha256_obj(payload):
            raise ValueError(f"anexo não confere com a trilha: {path}")
        return
    book.audit.append(event, "CDP — avaliação determinística", payload, week=week, ts=at)


def input_authorship(week_dir: Path, mind: str) -> tuple[dict, dict]:
    """Confere o mind bruto sem renomear notas/autores, inclusive sem validate anterior."""
    hashes, minds = {}, {}
    inputs = week_dir / "inputs"
    for name in ("research_pack.json", "pm_decision.json"):
        p = inputs / name
        if not p.exists():
            continue
        hashes[name] = sha256_file(p)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            declared = raw.get("mind") if isinstance(raw, dict) else None
        except (ValueError, OSError):
            declared = None
        minds[name] = declared if isinstance(declared, str) else None
        if declared is not None and declared != mind:
            raise ValueError(f"mind esperado {mind!r} difere de {name}: {declared!r}")
    return hashes, minds


def _raw_items(value: dict, key: str) -> list[dict]:
    items = value.get(key)
    return [v for v in items if isinstance(v, dict)] if isinstance(items, list) else []


def _authorship(chosen, mind: str, minds: dict, raw: dict) -> tuple[str, str | None]:
    """Autoria declarada original; defaults do carregador não confirmam uma mente."""
    for v in chosen:
        name = "pm_decision.json" if v.source == ViewSource.PM else "research_pack.json"
        if minds.get(name) is None:
            return "absent", None
        if v.source == ViewSource.PM:
            if not is_autonomous_view(v):
                return "external", None
            continue
        original = raw.get(name, {})
        notes = {n.get("note_id"): n for n in _raw_items(original, "notes")}
        if v.note_ids:
            providers = [notes.get(n, {}).get("provider") for n in v.note_ids]
            if any(p is None or not str(p).strip() for p in providers):
                return "absent", None
            if any(p != mind for p in providers):
                return "external", None
        else:
            # Visão direta: conferir autor bruto, nunca o prefixo importado pelo carregador.
            originals = [x for x in _raw_items(original, "views")
                         if x.get("issuer_id") == v.issuer_id]
            if not originals or any(not x.get("author") for x in originals):
                return "absent", None
            if any(x.get("author") != mind for x in originals):
                return "external", None
    return "confirmed", mind


def _enable(book: Book, week: date, now: datetime) -> None:
    """Recupera queda entre manifesto e evento sem reescrever início histórico."""
    path = book.root / ENABLE_FILE
    if not path.exists():
        _write_exclusive(path, json.dumps({"policy": POLICY, "first_week": str(week)}, sort_keys=True) + "\n")
    payload = json.loads(path.read_text(encoding="utf-8"))
    first = date.fromisoformat(payload["first_week"])
    if set(payload) != {"policy", "first_week"} or payload["policy"] != POLICY or first > week:
        raise ValueError("manifesto de avaliação incoerente")
    events = book.audit.events()
    enabled = [e for e in events if e.event_type == ENABLE_EVENT]
    if enabled:
        if len(enabled) != 1 or enabled[0].week != first or enabled[0].payload_hash != sha256_obj(payload):
            raise ValueError("manifesto de avaliação diverge da trilha")
    else:
        if any(e.event_type in {SIGNALS_EVENT, BINDING_EVENT, OUTCOME_EVENT} for e in events):
            raise ValueError("evento inicial de avaliação ausente em livro já selado")
        book.audit.append(ENABLE_EVENT, "CDP", payload, week=first, ts=now)


def preregister(book: Book, ctx: WeekContext, pack: ResearchPack, pm: PMBundle, *,
                mind: str, cutoff: datetime, now: datetime, deadline: datetime,
                clock: Callable[[], datetime] | None = None) -> Cohort:
    """Sela a previsão antes da otimização; repetir só reutiliza conteúdo idêntico."""
    folder = book.week_dir(ctx.week) / FOLDER
    path = folder / SIGNALS_FILE
    hashes, minds = input_authorship(book.week_dir(ctx.week), mind)
    base = ctx.model_base or ctx.model
    end = next_rebalance_after(ctx.week, ctx.cfg)
    end_close = max(janela_execucao(end, ctx.cfg).fechamentos.values())
    sessions, primary_lines = {}, {}
    for iid in base.assets:
        primary = str(ctx.md.universe.issuers.loc[iid, "primary_ticker"])
        line = ctx.md.universe.lines.loc[primary]
        mic = mic_da_linha(primary, line.get("exchange"))
        mic = MIC_PAI.get(mic, mic)
        primary_lines[iid] = {"ticker": primary, "currency": str(line["currency"]), "mic": mic}
        sessions[iid] = [d.isoformat() for d in pd.date_range(ctx.week + timedelta(days=1), end)
                         if is_session(d.date(), mic)]
    notes = {n.note_id: n.model_dump(mode="json") for n in pack.notes}
    # Texto bruto preserva autoria e até uma entrada inválida sem aceitar seus números como
    # previsão; nunca substituir o provider/author original pelo nome do executor.
    original_inputs = {name: (book.week_dir(ctx.week) / "inputs" / name).read_text(encoding="utf-8")
                       for name in hashes}
    original_json = {}
    for name, text in original_inputs.items():
        try:
            value = json.loads(text)
            original_json[name] = value if isinstance(value, dict) else {}
        except ValueError:
            original_json[name] = {}
    signals = [Signal(issuer_id=str(i), channel="quant", score=_finite(v))
               for i, v in ctx.alpha.composite_z.items()]
    for channel, views in (("pesquisa_ai", list(pack.views)),
                           ("mente_final", list(pack.views) + list(pm.views))):
        grouped: dict[str, list] = {}
        for v in views:
            if channel == "pesquisa_ai" and v.source != ViewSource.AI:
                continue
            grouped.setdefault(v.issuer_id, []).append(v)
        for iid, vs in sorted(grouped.items()):
            # Mesma precedência da inclinação econômica: PM substitui a pesquisa; na sua
            # ausência, a previsão final usa AI. Autoria humana/desconhecida não é da mente.
            pms = [v for v in vs if v.source == ViewSource.PM]
            chosen = pms if pms else vs
            forecasts = [v for v in chosen if v.score != 0 or not
                         (v.no_long or v.no_short or v.max_abs_weight is not None)]
            score = float(np.mean([v.score * v.confidence for v in forecasts])) if forecasts else None
            state, confirmed_mind = _authorship(chosen, mind, minds, original_json)
            origins = [{"payload_mind": minds.get("pm_decision.json" if v.source == ViewSource.PM
                                                 else "research_pack.json"), "author": v.author,
                        "notes": [notes[n] for n in v.note_ids if n in notes],
                        "raw_notes": [n for n in _raw_items(original_json.get("research_pack.json", {}), "notes")
                                      if n.get("note_id") in v.note_ids]}
                       for v in vs]
            signals.append(Signal(issuer_id=iid, channel=channel, score=score,
                                  authorship=state, confirmed_mind=confirmed_mind,
                                  forecasts=[v.model_dump(mode="json") for v in vs],
                                  original_authorship=origins,
                                  reason="autoria original ausente/externa: excluída do IC por mente"
                                  if state != "confirmed" else ""))
    # O selo usa o relógio ao término da preparação, antes da otimização; processamento
    # que ultrapasse o prazo permanece registrado, porém não vira amostra prospectiva.
    now = clock() if clock is not None else now
    old = _read(path, Cohort) if path.exists() else None
    cohort = Cohort(week=ctx.week, end=end, data_cutoff=old.data_cutoff if old else cutoff,
                    committed_at=old.committed_at if old else now, deadline=deadline,
                    end_close=end_close, mind=mind, original_minds=minds, input_hashes=hashes,
                    original_inputs=original_inputs,
                    research_pack_hash=pack.research_hash(),
                    research_hash=combine_hashes(pack.research_hash(), pm.pm_output_hash),
                    pm_output_hash=pm.pm_output_hash, snapshot_hash=ctx.snapshot_hash,
                    config_hash=ctx.cfg.config_hash(), is_synthetic=ctx.md.is_synthetic,
                    data_notice=ctx.md.manifest.data_notice, base_as_of=base.as_of,
                    exposures=_frame(base.exposures),
                    required_macro=[f"macro:{m}" for m in ctx.cfg.risk_model.macro_factors],
                    specific_var={str(k): _finite(v) for k, v in base.specific_var.items()},
                    sessions=sessions, primary_lines=primary_lines, signals=signals)
    _enable(book, ctx.week, now)
    _write(path, cohort)
    _anchor(book, path, cohort, SIGNALS_EVENT, ctx.week, now)
    return cohort


def bind(book: Book, decision: Decision, *, path_taken: str, now: datetime) -> Binding | None:
    folder = book.week_dir(decision.week) / FOLDER
    path = folder / SIGNALS_FILE
    if not path.exists():
        marker = book.root / ENABLE_FILE
        if marker.exists() and decision.week >= date.fromisoformat(json.loads(marker.read_text())["first_week"]):
            raise ValueError("decisão sem pré-registro autenticado")
        return None  # livro legado, não preencher forecasts retrospectivamente
    cohort = _read(path, Cohort)
    for field in ("research_hash", "snapshot_hash", "config_hash", "mind"):
        if getattr(cohort, field) != getattr(decision, field):
            raise ValueError(f"pré-registro divergente da decisão: {field}")
    if cohort.pm_output_hash != decision.pm_decision_hash:
        raise ValueError("saída PM divergente do pré-registro")
    for name, digest in cohort.input_hashes.items():
        if sha256_file(book.week_dir(decision.week) / "inputs" / name) != digest:
            raise ValueError("entrada original alterada após o selo")
    evs = book.audit.events()
    seal = [e for e in evs if e.event_type == SIGNALS_EVENT and e.week == decision.week
            and e.payload_hash == sha256_obj(_payload(path, cohort))]
    head = next((e.seq for e in evs if e.event_hash == decision.audit_head_hash), -1)
    if len(seal) != 1 or seal[0].seq > head:
        raise ValueError("sinais não ancorados antes da decisão")
    binding = Binding(cohort_hash=sha256_obj(cohort), approval_hash=decision.approval_hash,
                      proposal_hash=decision.proposal_hash, path_taken=path_taken)
    _write(folder / BINDING_FILE, binding)
    _anchor(book, folder / BINDING_FILE, binding, BINDING_EVENT, decision.week, now)
    return binding


def residuals(cohort: Cohort, returns: Frame, macro: Frame) -> tuple[dict, dict]:
    """Resíduo por intervalo completo de cada emissor; faltante não é retorno zero."""
    B = cohort.exposures.frame()
    r, m = returns.frame(dates=True), macro.frame(dates=True)
    macro_names = [n for n in B if n.startswith("macro:")]
    missing = set(cohort.required_macro) - set(macro_names)
    if missing:
        reason = "base residual sem exposição macro configurada: " + ", ".join(sorted(missing))
        return dict.fromkeys(cohort.sessions), dict.fromkeys(cohort.sessions, reason)
    structural = [n for n in B if n not in macro_names]
    specific = pd.DataFrame(index=r.index, columns=B.index, dtype=float)
    sv = pd.Series(cohort.specific_var, dtype=float)
    for t in r.index:
        daily = r.loc[t].reindex(B.index)
        if macro_names:
            if t not in m.index or not m.loc[t].reindex(macro_names).notna().all():
                continue
            daily = daily - B[macro_names] @ m.loc[t].reindex(macro_names)
        f = cross_sectional_factor_returns(B[structural], daily, sv)
        if f is not None and f.notna().all():
            specific.loc[t] = daily - B[structural] @ f
    result, reasons = {}, {}
    for iid, expected in cohort.sessions.items():
        wanted = pd.to_datetime(expected)
        vals = specific[iid].reindex(wanted) if iid in specific else pd.Series(index=wanted, dtype=float)
        if not len(wanted):
            result[iid], reasons[iid] = None, "sem sessão aplicável no horizonte"
        elif not vals.notna().all():
            result[iid], reasons[iid] = None, "intervalo incompleto: preço/FX/fator/regressão ausente"
        else:
            result[iid] = float(vals.sum())
    return result, reasons


def _outcome_values(cohort: Cohort, outcome: Outcome) -> tuple[dict, dict]:
    assets = set(cohort.exposures.index)
    if (set(outcome.initial_price_usd) != assets or set(outcome.end_primary_lines) != assets
            or set(outcome.residual_returns) != assets):
        raise ValueError("universo do outcome diverge da base")
    for frame in (outcome.returns, outcome.macro_returns):
        dates = pd.to_datetime(frame.index)
        if not dates.is_monotonic_increasing or any(not cohort.week < d.date() <= cohort.end for d in dates):
            raise ValueError("retornos fora do intervalo da coorte")
    values, reasons = residuals(cohort, outcome.returns, outcome.macro_returns)
    for iid, line in cohort.primary_lines.items():
        if outcome.end_primary_lines[iid] != line["ticker"]:
            values[iid], reasons[iid] = None, "linha primária mudou no horizonte"
        elif outcome.initial_price_usd[iid] is None or outcome.initial_price_usd[iid] <= 0:
            values[iid], reasons[iid] = None, "preço/FX do fechamento inicial ausente"
    return values, reasons


def resolve(book: Book, track, load_market: Callable, *, session: date, now: datetime) -> list[date]:
    """Reconcilia apenas anexos; não decide, executa ordens nem refaz registro diário."""
    done = []
    for path in sorted(book.root.glob(f"*/{FOLDER}/{SIGNALS_FILE}")):
        cohort = _read(path, Cohort)
        if cohort.end > session or now < cohort.end_close:
            continue
        decision = book.load_decision(cohort.week)
        if decision is None:
            continue
        folder = path.parent
        binding = _read(folder / BINDING_FILE, Binding) if (folder / BINDING_FILE).exists() else bind(
            book, decision, path_taken="recuperado", now=now)
        if binding.approval_hash != decision.approval_hash:
            raise ValueError("vínculo de avaliação divergente")
        outcome_path = folder / OUTCOME_FILE
        existing = None
        if outcome_path.exists():
            existing = _read(outcome_path, Outcome)
            if not cohort.end_close <= existing.recorded_at <= now:
                raise ValueError("instante do outcome prematuro/futuro")
            anchored = [e for e in book.audit.events() if e.event_type == OUTCOME_EVENT and e.week == cohort.week]
            if anchored:
                _anchor(book, outcome_path, existing, OUTCOME_EVENT, cohort.week, now)
                if existing.cohort_hash != sha256_obj(cohort) or existing.approval_hash != decision.approval_hash:
                    raise ValueError("outcome pertence a outra coorte/decisão")
                values, reasons = _outcome_values(cohort, existing)
                if sha256_obj(values) != sha256_obj(existing.residual_returns) or reasons != existing.reasons:
                    raise ValueError("outcome não reconcilia")
                continue
        record = track.get(cohort.end)
        if record is None:
            continue
        track_ok, track_problems = track.verify()
        if not track_ok:
            raise ValueError("registro diário não autenticado: " + "; ".join(track_problems))
        md = load_market(as_of=cohort.end)
        if md.as_of != cohort.end or cohort.end in md.manifest.provisional_dates:
            continue
        from ..analytics.panel import build_asset_panel, fx_for_lines
        from ..config import load_archived_config

        archived = load_archived_config(book.week_dir(cohort.week) / "config_decisao.json", cohort.config_hash)
        if archived is None:
            raise ValueError("mandato da coorte ausente ou adulterado")
        panel = build_asset_panel(md, archived.cfg)
        if record.input_hashes.get("market_data") != md.manifest.content_hash():
            raise ValueError("mercado do outcome diverge do fechamento autenticado")
        r = panel.returns.loc[(panel.returns.index > pd.Timestamp(cohort.week)) &
                              (panel.returns.index <= pd.Timestamp(cohort.end))]
        names = list(dict.fromkeys([n for n in cohort.exposures.columns if n.startswith("macro:")]
                                  + cohort.required_macro))
        m = pd.DataFrame(index=r.index)
        for n in names:
            symbol = n.removeprefix("macro:")
            m[n] = (md.benchmarks[symbol].pct_change(fill_method=None).reindex(r.index)
                    if symbol in md.benchmarks else np.nan)
        rf, mf = _frame(r, dates=True), _frame(m, dates=True)
        initial, end_lines = {}, {}
        fx = fx_for_lines(md)
        # A linha primária e o fechamento inicial são parte da previsão, não escolhidos
        # retrospectivamente para melhorar a cobertura/retorno.
        for iid, line in cohort.primary_lines.items():
            end_lines[iid] = (str(md.universe.issuers.loc[iid, "primary_ticker"])
                              if iid in md.universe.issuers.index else None)
            # Última sessão local prevista antes/no início: não usa uma cotação válida
            # arbitrariamente antiga quando a barra inicial estiver ausente.
            day = cohort.week
            while not is_session(day, line["mic"]):
                day -= timedelta(days=1)
            t, ticker, ccy = pd.Timestamp(day), line["ticker"], line["currency"]
            adj = md.adj_close.get(ticker, pd.Series(dtype=float)).get(t)
            rate = fx.get(ccy, pd.Series(dtype=float)).get(t)
            initial[iid] = (_finite(adj * rate) if adj is not None and rate is not None else None)
        outcome = Outcome(cohort_hash=sha256_obj(cohort), approval_hash=binding.approval_hash,
                          week=cohort.week, end=cohort.end, recorded_at=existing.recorded_at if existing else now,
                          daily_record_hash=record.record_hash, market_hash=md.manifest.content_hash(),
                          market_files={f.path: f.sha256 for f in md.manifest.files},
                          returns=rf, macro_returns=mf, initial_price_usd=initial,
                          end_primary_lines=end_lines, residual_returns=dict.fromkeys(initial), reasons={})
        realized, reasons = _outcome_values(cohort, outcome)
        outcome = outcome.model_copy(update={"residual_returns": realized, "reasons": reasons})
        _write(outcome_path, outcome)
        _anchor(book, outcome_path, outcome, OUTCOME_EVENT, cohort.week, now)
        done.append(cohort.week)
    return done


def verify(book: Book, track=None, market_root: Path | None = None) -> list[str]:
    """Faz falha fechada de anexo/hash/timing/aritmética; pendências são lidas por status()."""
    problems = []
    events = book.audit.events()
    marker = book.root / ENABLE_FILE
    enabled = [e for e in events if e.event_type == ENABLE_EVENT]
    if not marker.exists():
        return ["manifesto de avaliação removido"] if enabled else []
    try:
        raw = json.loads(marker.read_text(encoding="utf-8"))
        first = date.fromisoformat(raw["first_week"])
        if raw["policy"] != POLICY or len(enabled) != 1 or sha256_obj(raw) != enabled[0].payload_hash:
            problems.append("manifesto de avaliação divergente da trilha")
    except (ValueError, KeyError, TypeError):
        return ["manifesto de avaliação inválido"]
    weeks = set(w for w in book.list_weeks() if w >= first and book.list_decisions(w))
    weeks.update(e.week for e in events if e.event_type == SIGNALS_EVENT and e.week is not None)
    for folder in book.root.glob(f"*/{FOLDER}"):
        if any(folder.iterdir()):
            try:
                weeks.add(date.fromisoformat(folder.parent.name))
            except ValueError:
                problems.append(f"pasta de avaliação sem semana válida: {folder.parent.name}")
    for week in sorted(weeks):
        folder = book.week_dir(week) / FOLDER
        try:
            c = _read(folder / SIGNALS_FILE, Cohort)
            for file, cls, event in ((SIGNALS_FILE, Cohort, SIGNALS_EVENT),
                                     (BINDING_FILE, Binding, BINDING_EVENT),
                                     (OUTCOME_FILE, Outcome, OUTCOME_EVENT)):
                p = folder / file
                es = [e for e in events if e.event_type == event and e.week == week]
                required = file == SIGNALS_FILE or (file == BINDING_FILE and book.list_decisions(week)) or es
                if not p.exists():
                    if required:
                        raise ValueError(f"{file} ausente")
                    continue
                value = _read(p, cls)
                if len(es) != 1 or es[0].payload_hash != sha256_obj(_payload(p, value)):
                    raise ValueError(f"{file} não confere com a trilha")
                if file != SIGNALS_FILE and value.cohort_hash != sha256_obj(c):
                    raise ValueError(f"{file} pertence a outra coorte")
            d = book.load_decision(week)
            if d is not None:
                binding = _read(folder / BINDING_FILE, Binding)
                if binding.approval_hash != d.approval_hash or binding.proposal_hash != d.proposal_hash or c.mind != d.mind:
                    raise ValueError("vínculo/autoria divergente da decisão")
                for field in ("research_hash", "snapshot_hash", "config_hash"):
                    if getattr(c, field) != getattr(d, field):
                        raise ValueError(f"{field} diverge da decisão")
                if c.pm_output_hash != d.pm_decision_hash:
                    raise ValueError("saída PM diverge da decisão")
                _, event_index = book._audit_state()
                proposal = book._find_proposal(week, d.proposal_id)
                if not book._decision_valid(d, proposal, event_index):
                    raise ValueError("decisão não autenticada")
                head = next((e.seq for e in events if e.event_hash == d.audit_head_hash), -1)
                seal = next(e for e in events if e.event_type == SIGNALS_EVENT and e.week == week)
                if seal.seq > head or seal.ts < c.committed_at:
                    raise ValueError("sinais fora da âncora da decisão")
                for name, digest in c.input_hashes.items():
                    if sha256_file(book.week_dir(week) / "inputs" / name) != digest:
                        raise ValueError("entrada original alterada")
            p = folder / OUTCOME_FILE
            if p.exists():
                o = _read(p, Outcome)
                if o.week != c.week or o.end != c.end or o.recorded_at < c.end_close:
                    raise ValueError("outcome de intervalo inválido ou prematuro")
                if d is None or o.approval_hash != d.approval_hash:
                    raise ValueError("outcome de outra decisão")
                vals, reasons = _outcome_values(c, o)
                if sha256_obj(vals) != sha256_obj(o.residual_returns) or reasons != o.reasons:
                    raise ValueError("outcome não reconcilia com a identidade residual")
                if track is not None:
                    record = track.get(c.end)
                    if record is None or record.record_hash != o.daily_record_hash:
                        raise ValueError("fechamento não confere com o outcome")
                    if record.input_hashes.get("market_data") != o.market_hash:
                        raise ValueError("mercado diverge do fechamento autenticado")
                if market_root is not None and not c.is_synthetic:
                    for name, digest in o.market_files.items():
                        source = market_root / name
                        if not source.is_file() or sha256_file(source) != digest:
                            raise ValueError("fonte de mercado do outcome ausente/adulterada")
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
            problems.append(f"{week}: {exc}")
    return problems


def status(book: Book, track, *, now: datetime) -> list[dict]:
    """Estado de cada coorte, sem criar outcome ou transformar pendência em sucesso."""
    from .origem import read_replay_origin

    origin = read_replay_origin(book)
    rows = []
    for path in sorted(book.root.glob(f"*/{FOLDER}/{SIGNALS_FILE}")):
        c = _read(path, Cohort)
        if book.load_decision(c.week) is None:
            state = "aguarda decisão autenticada"
        elif (path.parent / OUTCOME_FILE).exists():
            state = "resolvida"
        elif now < c.end_close:
            state = "horizonte ainda imaturo"
        elif track.get(c.end) is None:
            state = "aguarda fechamento selado"
        else:
            state = "pendente de reconciliação"
        rows.append({"semana": c.week, "fim": c.end, "mente_execucao": c.mind,
                     "prospectiva": c.prospective and origin is None, "estado": state,
                     **({"origem": "ensaio retrospectivo"} if origin is not None else {})})
    return rows
