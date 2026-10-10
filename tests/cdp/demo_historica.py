"""Corpus de regressão pré-NET produzido hoje em tmp — DADOS SIMULADOS.

Não representa arquivo histórico/PIT nem autoridade financeira. A receita nativa
produz propostas completas; uma cópia de metadados anterior à primeira aprovação
persistida do novo corpus omite somente a estampa NET. O resultado original fica intacto
e separado, inclusive seus hashes/decisão transitórios anteriores ao wrapper.
BOOKED é corpo de fixture fechado por serializer/evento; nenhuma nova efetivação
save_booked/compose/preflight/persist é autorizada por este helper.
"""
from __future__ import annotations

import tempfile
from dataclasses import replace
from datetime import time
from pathlib import Path

import pytest

from cdp import SIMULATED_DATA_NOTICE
from cdp.config import load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.workflow import demo as native
from cdp.workflow import weekly
from cdp.workflow.approval import verify_decision
from cdp.workflow.book import _write_exclusive, dump_json
from cdp.workflow.daily import PendingExecution
from cdp.workflow.net_moc import PROPOSAL_KEY, RECORD_MARKER, NetUnverifiable, descriptor
from cdp.workflow.runtime import Runtime
from cdp.workflow.tese import thesis_applicable


def _legacy_copy(proposal, originals, folder):
    assert proposal.is_synthetic and SIMULATED_DATA_NOTICE in proposal.data_notice
    original = dump_json(proposal)
    overrides = {k: v for k, v in proposal.overrides.items() if k != PROPOSAL_KEY}
    corpus = proposal.model_copy(update={"overrides": overrides})
    assert descriptor(corpus) is None
    assert dump_json(proposal) == original  # O objeto com NET permanece intacto.
    assert corpus.model_copy(update={"overrides": proposal.overrides}) == proposal
    _write_exclusive(folder / f"{proposal.proposal_id}.json", original)
    originals.append(proposal)
    return corpus


def _historical_booked(runner, session):
    """Prepara o kernel integral e fecha somente os corpos hipotéticos do corpus."""
    proposal = runner.book.load_proposal(session)
    decision = runner.book.load_decision(session)
    assert proposal is not None and decision is not None
    assert descriptor(proposal) is None and proposal.is_synthetic
    valid, reasons = verify_decision(decision, proposal, proposal.snapshot_hash,
                                     runner.cfg.config_hash(), proposal.research_hash)
    assert valid, reasons
    valid, reasons = runner.book.verify_integrity()
    assert valid, reasons
    pending = PendingExecution(proposal, decision)
    prev = runner.track.last()
    plan = runner._plan_from_pending(session, prev, pending)
    ctx = runner.context(session, prev=prev)
    main = runner._prepare_side(runner.main, ctx, prev, plan)
    assert main.entry is not None and main.commit is None
    assert RECORD_MARKER not in main.record.input_hashes
    shadow = None
    if runner.shadow is not None:
        prior = runner.shadow.track.last()
        shadow_plan = runner._shadow_plan(runner.shadow, ctx, prior, pending)
        if shadow_plan is not None:
            assert descriptor(shadow_plan.proposal) is None
            shadow = runner._prepare_side(runner.shadow, ctx, prior, shadow_plan)
            assert shadow.entry is not None and shadow.commit is None
            assert RECORD_MARKER not in shadow.record.input_hashes
            runner.shadow.store.save_proposal(shadow_plan.proposal)
    _write_exclusive(runner.book.week_dir(session) / "booked.json", dump_json(main.entry))
    runner.book.audit.append("BOOKED", "corpus de regressão", main.entry, week=session,
                            summary="DADOS SIMULADOS: corpus pré-NET produzido hoje, sem autoridade.")
    if shadow is not None:
        _write_exclusive(runner.shadow.store.booked_path(session), dump_json(shadow.entry))
        runner.shadow.store.audit.append("BOOKED_SHADOW", "corpus de regressão", shadow.entry,
                                        week=session,
                                        summary="DADOS SIMULADOS: sombra do corpus pré-NET.")


def run_historical_demo(out, days=5, *, seed=native.DEMO_SEED,
                        first_week=native.DEMO_FIRST_WEEK, cfg=None,
                        inaugural_calendar=False):
    """Preserva casos antigos de leitura/calendário; não é a demo prospectiva do produto."""
    out = Path(out)
    assert type(inaugural_calendar) is bool
    assert out.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert not (out / "book").exists() and not (out / "market").exists()
    cfg = cfg or load_config()
    if inaugural_calendar:
        # Exceção exclusivamente do corpus de calendário legado, produzido hoje.
        # A configuração sem execution continua recusada pela demo nativa abaixo.
        assert cfg.execution is None and type(days) is int and days == 1
        assert first_week == cfg.fund.inception_date
        assert native.is_session(first_week, "BVMF")
        assert cfg.fund.inception_date < load_config().fund.inception_date
        sessions = [first_week]
    else:
        sessions = native.demo_sessions(days, first_week, cfg)
        assert sessions[-1] < cfg.fund.inception_date
    # Demonstra que esta configuração/data não ganha autorização de nova escrita.
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    with pytest.raises(NetUnverifiable):
        native.run_demo(out, days=days, seed=seed, first_week=first_week, cfg=cfg)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    md = make_synthetic_market(seed=seed, start=native.DEMO_HISTORY_START, as_of=sessions[-1])
    clock = native._Clock()
    archive = native.DemoStore(md, root=out / "market", cfg=cfg)
    rt = Runtime(cfg, out / "book", out / "market", out / "reports",
                 store_override=archive.physical_store, clock=clock, teses_root=None)
    originals = []
    original_generator = weekly.run_weekly_decision

    def corpus_generator(*args, **kwargs):
        result = original_generator(*args, **kwargs)
        return replace(result,
                       final=_legacy_copy(result.final, originals, out / "corpus_original_net"),
                       shadow_quant=_legacy_copy(result.shadow_quant, originals,
                                                 out / "corpus_original_net"))

    log = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(weekly, "run_weekly_decision", corpus_generator)
        for s in sessions:
            mounting = inaugural_calendar or native._montagem(s, cfg)
            if mounting:
                archive.load(rt.information_session(s))
                clock.set(s, time(11, 0))
                prep = rt.weekly_prepare(s, mind=native.DEMO_MIND, live=False)
                clock.set(s, time(12, 0))
                inputs = native.write_demo_inputs(rt, s)
                ok, issues = rt.validate_inputs(s, mind=native.DEMO_MIND)
                clock.set(s, min(time(15, 0), rt.decision_deadline(s).astimezone(native.BRT).time()))
                dec = rt.weekly_decide(s, mind=native.DEMO_MIND)
                step = {"semana": s, "briefing": prep["briefing"], "entradas_validas": ok,
                        "apontamentos": issues, "pm": inputs.get("pm_issues", ""),
                        "caminho": dec["caminho"], "postura": dec["postura"],
                        "vol_ex_ante": dec["vol_ex_ante"], "n_long": dec["n_long"],
                        "n_short": dec["n_short"], "relatorio": dec["relatorio"]["md"]}
                if thesis_applicable(rt.book, s):
                    prepared = rt.thesis_prepare(s)
                    native.write_demo_thesis(rt, s)
                    published = rt.thesis_publish(s)
                    step.update(tese=published["autoria"], tese_apontamentos=published["problemas"],
                                tese_rascunho_adotado=prepared["rascunho_adotado"])
                else:
                    step.update(tese=None, tese_apontamentos=[], tese_rascunho_adotado=False)
                log.append(step)
            archive.load(s)
            clock.set(s, time(19, 20))
            if mounting:
                _historical_booked(rt._runner(), s)
            close = rt.daily_close(s, live=False, mind=native.DEMO_MIND)
            entry = {"data": s, "status": close.get("status"),
                     "efetivacao": close.get("efetivacao")}
            if close.get("status") == "registrado":
                native.write_demo_commentary(rt, s)
                pub = rt.daily_publish(s)
                entry.update(nav_usd=close["nav_usd"], retorno_dia=close["retorno_dia"],
                             relatorio=pub["relatorio"]["md"],
                             comentario_da_mente=pub["comentario_da_mente"])
                if cfg.execution is not None and mounting:
                    entry["relatorio_semanal"] = native._weekly_close_report(rt, s)
            log.append(entry)
    valid, messages = rt.verify_all()
    last = rt.track().last()
    summary = {"aviso": f"{SIMULATED_DATA_NOTICE} — corpus pré-NET produzido hoje; sem origem PIT.",
               "pasta": str(out), "pregoes": [str(s) for s in sessions],
               "nav_final_usd": last.nav_end_usd if last else None,
               "registros": len(rt.track().records()), "integridade": valid,
               "verificacao": messages, "etapas": log}
    assert originals and all(descriptor(p) is not None for p in originals)
    native._write_json(out / "demo_summary.json", summary)
    return summary
