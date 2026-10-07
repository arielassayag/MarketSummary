"""Avaliação prospectiva pelo runtime real, offline: DADOS SIMULADOS."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cdp.config import load_config
from cdp.research.evaluation import AuthenticatedViewTracker
from cdp.workflow.avaliacao import (
    BINDING_EVENT,
    BINDING_FILE,
    ENABLE_EVENT,
    ENABLE_FILE,
    FOLDER,
    OUTCOME_EVENT,
    OUTCOME_FILE,
    SIGNALS_FILE,
    Cohort,
    Frame,
    Outcome,
    bind,
    input_authorship,
    preregister,
    residuals,
)
from cdp.workflow.demo import run_demo
from cdp.workflow.runtime import Runtime

LEGACY = Path(__file__).parent / "fixtures/fund_legado.yaml"
FIRST, END = date(2024, 3, 4), date(2024, 3, 11)
NOW = datetime(2024, 3, 12, 23, tzinfo=UTC)


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory):
    root = tmp_path_factory.mktemp("avaliacao-prospectiva")
    run_demo(root, days=6, cfg=load_config(LEGACY))
    return root


def _runtime(root):
    return Runtime(load_config(LEGACY), root / "book", root / "market", root / "reports",
                   clock=lambda: NOW, teses_root=None)


def _copy(evaluated, tmp_path):
    root = tmp_path / "ensaio"
    shutil.copytree(evaluated, root)
    return root, _runtime(root)


@pytest.fixture(scope="module")
def context(evaluated):
    from cdp.research.pm_agent import load_week_inputs, pm_factbook, to_bundle

    rt = _runtime(evaluated)
    now = datetime(2024, 3, 4, 17, tzinfo=UTC)
    _, _, ctx, _, pmctx = rt._week_state(FIRST)
    pack, out, _, pmctx = load_week_inputs(rt.week_dir(FIRST), pmctx, now=now)
    pm = to_bundle(out, rt.cfg, pmctx.drawdown, factbook=pm_factbook(pmctx))
    return ctx, pack, pm, now, rt.decision_deadline(FIRST)


def _fresh_inputs(evaluated, tmp_path):
    from cdp.workflow.book import Book

    book = Book(tmp_path / "book")
    inputs = book.week_dir(FIRST) / "inputs"
    shutil.copytree(evaluated / "book" / str(FIRST) / "inputs", inputs)
    return book, inputs


def test_runtime_preregisters_original_mind_and_pm_then_resolves_future_residuals(evaluated):
    rt = _runtime(evaluated)
    folder = rt.week_dir(FIRST) / FOLDER
    cohort = Cohort.model_validate_json((folder / SIGNALS_FILE).read_text())
    outcome = Outcome.model_validate_json((folder / OUTCOME_FILE).read_text())
    assert cohort.mind == "demo" and cohort.prospective
    assert cohort.end == END and outcome.end == END
    assert cohort.committed_at < cohort.end_close <= outcome.recorded_at
    assert {s.channel for s in cohort.signals} >= {"quant", "mente_final"}
    for name, raw in cohort.original_inputs.items():
        assert raw == (rt.week_dir(FIRST) / "inputs" / name).read_text()
        assert json.loads(raw)["mind"] == "demo"
    assert any(s.original_authorship for s in cohort.signals if s.channel == "mente_final")
    assert any(v is not None for v in outcome.residual_returns.values())
    assert rt.verify_all()[0], rt.verify_all()[1]
    assert rt.evaluation_history(mind="demo").empty  # simulados não entram na série real
    hist = rt.evaluation_history(mind="demo", include_synthetic=True)
    assert list(hist["week"]) == [FIRST]
    assert (hist["mind"] == "demo").all() and (hist["channel"] == "mente_final").all()
    assert rt.evaluation_history(mind="codex", include_synthetic=True).empty
    quant = rt.evaluation_history(mind="demo", channel="quant", include_synthetic=True)
    assert len(quant) and quant["ic_incremental"].isna().all()
    assert (quant["n_incremental"] == 0).all() and (quant["n_quant"] > 0).all()
    tracker = AuthenticatedViewTracker(rt.book_root, mind="demo", include_synthetic=True)
    assert tracker.phase_gate(rt.cfg)[0] == rt.cfg.research.llm_phase


def test_repeating_decision_and_close_never_changes_decision_outcome_or_audit(evaluated, tmp_path):
    root, rt = _copy(evaluated, tmp_path)
    before = {p.relative_to(root): p.read_bytes() for p in (root / "book").rglob("*") if p.is_file()}
    assert rt.weekly_decide(FIRST, mind="demo")["status"] == "já decidido"
    assert rt.daily_close(END, live=False)["status"] == "já registrado"
    after = {p.relative_to(root): p.read_bytes() for p in (root / "book").rglob("*") if p.is_file()}
    assert after == before


@pytest.mark.parametrize("file,field,value,state,channel", [
    ("research_pack.json", "mind", "DELETE", "absent", "pesquisa_ai"),
    ("research_pack.json", "mind", None, "absent", "pesquisa_ai"),
    ("pm_decision.json", "mind", "DELETE", "absent", "mente_final"),
    ("pm_decision.json", "mind", None, "absent", "mente_final"),
    ("research_pack.json", "provider", "claude-code", "external", "pesquisa_ai"),
    ("research_pack.json", "provider", None, "absent", "pesquisa_ai"),
])
def test_normalized_defaults_do_not_confirm_missing_or_external_raw_authorship(
        evaluated, context, tmp_path, file, field, value, state, channel):
    book, inputs = _fresh_inputs(evaluated, tmp_path)
    path = inputs / file
    raw = json.loads(path.read_text())
    if field == "provider":
        raw["notes"][0][field] = value
    elif value == "DELETE":
        raw.pop(field)
    else:
        raw[field] = value
    path.write_text(json.dumps(raw))
    ctx, pack, pm, now, deadline = context
    c = preregister(book, ctx, pack, pm, mind="demo", cutoff=now, now=now, deadline=deadline)
    selected = [s for s in c.signals if s.channel == channel and s.score is not None]
    if file == "pm_decision.json":
        selected = [s for s in selected if any(v["source"] == "pm" for v in s.forecasts)]
    assert selected and all(s.authorship == state and s.confirmed_mind is None for s in selected)
    assert c.mind == "demo"  # executor solicitado não sobrescreve os metadados originais
    if field == "mind":
        assert c.original_minds[file] is None
    assert c.original_inputs[file] == path.read_text()


def test_autonomous_pm_with_explicit_raw_mind_is_distinct_from_human_pm(evaluated, context, tmp_path):
    from dataclasses import replace

    book, _ = _fresh_inputs(evaluated, tmp_path)
    ctx, pack, pm, now, deadline = context
    human = replace(pm, views=tuple(v.model_copy(update={"author": "gestor humano"}) for v in pm.views))
    c = preregister(book, ctx, pack, human, mind="demo", cutoff=now, now=now, deadline=deadline)
    assert all(s.authorship == "external" and s.confirmed_mind is None for s in c.signals
               if s.channel == "mente_final" and any(v["source"] == "pm" for v in s.forecasts))
    original = Cohort.model_validate_json((evaluated / "book" / str(FIRST) / FOLDER / SIGNALS_FILE).read_text())
    pms = [s for s in original.signals if s.channel == "mente_final" and
           any(v["source"] == "pm" for v in s.forecasts)]
    assert pms and all(s.authorship == "confirmed" and s.confirmed_mind == "demo" for s in pms)


def test_raw_whitespace_change_blocks_approval_recovery(evaluated, tmp_path):
    _, rt = _copy(evaluated, tmp_path)
    raw = rt.week_dir(FIRST) / "inputs" / "research_pack.json"
    raw.write_text(raw.read_text() + "\n")  # mesmos números e schema; hash dos bytes muda
    with pytest.raises(ValueError, match="entrada original alterada"):
        rt.weekly_decide(FIRST, mind="demo")
    assert not rt.book.verify_integrity()[0]


def test_raw_bytes_change_signal_audit_anchor_even_when_normalized_pack_is_identical(evaluated, context, tmp_path):
    from cdp.workflow.avaliacao import SIGNALS_EVENT

    ctx, pack, pm, now, deadline = context
    first, _ = _fresh_inputs(evaluated, tmp_path / "one")
    second, inputs = _fresh_inputs(evaluated, tmp_path / "two")
    raw = inputs / "research_pack.json"
    raw.write_text(raw.read_text() + "\n")
    c1 = preregister(first, ctx, pack, pm, mind="demo", cutoff=now, now=now, deadline=deadline)
    c2 = preregister(second, ctx, pack, pm, mind="demo", cutoff=now, now=now, deadline=deadline)
    assert c1.research_hash == c2.research_hash and c1.input_hashes != c2.input_hashes
    e1 = next(e for e in first.audit.events() if e.event_type == SIGNALS_EVENT)
    e2 = next(e for e in second.audit.events() if e.event_type == SIGNALS_EVENT)
    assert e1.payload_hash != e2.payload_hash and e1.event_hash != e2.event_hash
    # A decisão autenticada ancora o audit_head posterior a AVALIACAO_SINAIS.
    from cdp.workflow.book import Book

    old = Book(evaluated / "book")
    decision = old.load_decision(FIRST)
    anchor = next(e.seq for e in old.audit.events() if e.event_hash == decision.audit_head_hash)
    seal = next(e.seq for e in old.audit.events() if e.event_type == SIGNALS_EVENT and e.week == FIRST)
    assert seal <= anchor


def test_reader_with_context_rejects_outcome_market_mismatch(evaluated, tmp_path):
    from cdp.workflow.avaliacao import _anchor, _write

    _, rt = _copy(evaluated, tmp_path)
    folder = rt.week_dir(FIRST) / FOLDER
    p = folder / OUTCOME_FILE
    o = Outcome.model_validate_json(p.read_text()).model_copy(update={"market_hash": "outro mercado"})
    # Simula um anexo criado por código com fonte incompatível, não só arquivo sem hash.
    events = rt.book.audit.events()
    cut = next(e.seq for e in events if e.event_type == OUTCOME_EVENT and e.week == FIRST)
    rt.book.audit.path.write_text("".join(json.dumps(e.model_dump(mode="json")) + "\n" for e in events[:cut]))
    p.unlink()
    _write(p, o)
    _anchor(rt.book, p, o, OUTCOME_EVENT, FIRST, NOW)
    with pytest.raises(ValueError, match="mercado diverge"):
        rt.evaluation_history(mind="demo", include_synthetic=True)


def test_mature_pending_outcome_is_explicit_and_reconciles_without_changing_record(evaluated, tmp_path):
    _, rt = _copy(evaluated, tmp_path)
    events = rt.book.audit.events()
    cut = next(e.seq for e in events if e.event_type == OUTCOME_EVENT and e.week == FIRST)
    rt.book.audit.path.write_text("".join(json.dumps(e.model_dump(mode="json")) + "\n" for e in events[:cut]))
    (rt.week_dir(FIRST) / FOLDER / OUTCOME_FILE).unlink()
    # Livro parcial legítimo entre fechamento selado e resolução; ainda não há evento outcome.
    pending = rt.evaluation_status()
    assert pending[0] == {"semana": FIRST, "fim": END, "mente_execucao": "demo",
                          "prospectiva": True, "estado": "pendente de reconciliação"}
    assert pending[1]["estado"] == "horizonte ainda imaturo"
    record_hash = rt.track().get(END).record_hash
    rt.daily_close(END, live=False)
    assert rt.track().get(END).record_hash == record_hash
    assert rt.evaluation_status()[0]["estado"] == "resolvida"


def test_enable_marker_crash_and_signal_retry_are_idempotent(evaluated, context, tmp_path, monkeypatch):
    from cdp.audit import AuditLog

    book, _ = _fresh_inputs(evaluated, tmp_path)
    ctx, pack, pm, now, deadline = context
    append = AuditLog.append

    def crash(self, event_type, *args, **kwargs):
        if event_type == ENABLE_EVENT:
            raise RuntimeError("queda após manifesto")
        return append(self, event_type, *args, **kwargs)

    monkeypatch.setattr(AuditLog, "append", crash)
    with pytest.raises(RuntimeError, match="queda"):
        preregister(book, ctx, pack, pm, mind="demo", cutoff=now, now=now, deadline=deadline)
    assert (book.root / ENABLE_FILE).exists()
    monkeypatch.setattr(AuditLog, "append", append)
    c = preregister(book, ctx, pack, pm, mind="demo", cutoff=now, now=now, deadline=deadline)
    before = book.audit.path.read_bytes()
    assert preregister(book, ctx, pack, pm, mind="demo", cutoff=now, now=now, deadline=deadline) == c
    assert book.audit.path.read_bytes() == before
    assert len([e for e in book.audit.events() if e.event_type == ENABLE_EVENT]) == 1


def test_legacy_decision_before_cutover_is_not_backfilled(evaluated, tmp_path):
    from datetime import timedelta

    _, rt = _copy(evaluated, tmp_path)
    shutil.rmtree(rt.week_dir(FIRST) / FOLDER)
    (rt.book_root / ENABLE_FILE).write_text(json.dumps({"policy": "cdp.avaliacao.residual_base_wls_macro/v1",
                                                      "first_week": str(FIRST + timedelta(days=7))}))
    # bind não inventa sinais para a decisão anterior ao início declarado da instrumentação.
    assert bind(rt.book, rt.book.load_decision(FIRST), path_taken="legado", now=NOW) is None


@pytest.mark.parametrize("file,event", [(BINDING_FILE, BINDING_EVENT), (OUTCOME_FILE, OUTCOME_EVENT)])
def test_crash_after_immutable_file_before_event_is_reconciled_without_orders(evaluated, tmp_path, file, event):
    _, rt = _copy(evaluated, tmp_path)
    # Remove apenas o último elo pertinente e todos os eventos posteriores: simula uma queda
    # depois do arquivo. Mantém a sequência prefixo íntegra; não cria forecast depois de outcome.
    events = rt.book.audit.events()
    cut = next(e.seq for e in events if e.event_type == event and e.week == FIRST)
    rt.book.audit.path.write_text("".join(json.dumps(e.model_dump(mode="json")) + "\n"
                                        for e in events[:cut]))
    if file == BINDING_FILE:
        # No instante dessa queda ainda não existiriam outcomes, outra semana ou track record.
        for path in rt.book_root.iterdir():
            if path.is_dir() and path.name != str(FIRST):
                shutil.rmtree(path)
        (rt.week_dir(FIRST) / FOLDER / OUTCOME_FILE).unlink()
        rt.weekly_decide(FIRST, mind="demo")
    else:
        # Mais artefatos da demo são posteriores ao evento cortado; o reconciliador só deve
        # completar o outcome anterior, não recriar esses eventos ou o record diário.
        rt.daily_close(END, live=False)
    assert any(e.event_type == event and e.week == FIRST for e in rt.book.audit.events())
    assert len(rt.book.list_decisions(FIRST)) == 1


@pytest.mark.parametrize("file", [SIGNALS_FILE, BINDING_FILE, OUTCOME_FILE])
def test_adulteration_or_removal_fails_closed_in_book_and_reader(evaluated, tmp_path, file):
    _, rt = _copy(evaluated, tmp_path)
    p = rt.week_dir(FIRST) / FOLDER / file
    p.unlink()
    assert not rt.book.verify_integrity()[0]
    with pytest.raises(ValueError, match="autenticada"):
        rt.evaluation_history(mind="demo", include_synthetic=True)


def test_mind_mismatch_is_rejected_without_rewriting_payload(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    p = inputs / "research_pack.json"
    original = '{"mind":"claude-code","notes":[{"provider":"origem externa"}]}'
    p.write_text(original)
    with pytest.raises(ValueError, match="mind esperado"):
        input_authorship(tmp_path, "codex")
    assert p.read_text() == original


def test_frozen_macro_residual_identity_and_missing_days_never_become_zero(evaluated):
    c = Cohort.model_validate_json((evaluated / "book" / str(FIRST) / FOLDER / SIGNALS_FILE).read_text())
    ids = [f"SIM_{i}" for i in range(12)]
    B = pd.DataFrame({"market": 1., "macro:SIM": np.linspace(-1, 1, len(ids))}, index=ids)
    data = c.model_dump()
    data.update(exposures=Frame(index=ids, columns=list(B), values=B.values.tolist()),
                specific_var=dict.fromkeys(ids, 0.04), sessions={i: [str(END)] for i in ids},
                primary_lines={i: {"ticker": i, "mic": "XNYS", "currency": "USD"} for i in ids})
    frozen = Cohort.model_validate(data)
    expected = np.array([(-1 if i % 2 else 1) * .001 for i in range(len(ids))])
    returns = pd.DataFrame([.01 + B["macro:SIM"].values * .02 + expected],
                           index=[str(END)], columns=ids)
    rf = Frame(index=[str(END)], columns=ids, values=returns.values.tolist())
    mf = Frame(index=[str(END)], columns=["macro:SIM"], values=[[.02]])
    values, reasons = residuals(frozen, rf, mf)
    assert not reasons
    np.testing.assert_allclose(list(values.values()), expected, atol=1e-12)
    missing_macro = mf.model_copy(update={"values": [[None]]})
    assert all(v is None for v in residuals(frozen, rf, missing_macro)[0].values())
    missing_day = Frame(index=[], columns=ids, values=[])
    assert all(v is None for v in residuals(frozen, missing_day, mf)[0].values())
    missing_exposure = frozen.model_copy(update={"required_macro": ["macro:OUTRO"]})
    absent, diagnostic = residuals(missing_exposure, rf, mf)
    assert all(v is None for v in absent.values())
    assert all("exposição macro configurada" in m for m in diagnostic.values())


def test_no_outcome_on_inaugural_close_and_no_brier_from_ordinal(evaluated):
    c = Cohort.model_validate_json((evaluated / "book" / str(FIRST) / FOLDER / SIGNALS_FILE).read_text())
    assert c.data_cutoff.date() == FIRST and c.end > FIRST
    assert "probability" not in Cohort.model_fields and "brier" not in Outcome.model_fields
    assert any(s.forecasts and "confidence" in s.forecasts[0] for s in c.signals)
