"""Retificação financeira da cauda por anexação; originais nunca são reescritos."""
from __future__ import annotations

import json
from pathlib import Path

from ..contracts import DailyRecord
from ..data.eventos_corporativos import digest
from ..hashing import sha256_file, sha256_obj, sha256_text
from ..leitura_arquivos import ler_texto, recusar_escrita

POLICY = "cdp.daily.financial_rectification/v1"


def event_type(track):
    return "DAILY_FINANCIAL_RECTIFICATION" + (
        "_SHADOW" if track.audit_event.endswith("_SHADOW") else "")


def folder(track, day):
    return track.root / "retificacoes" / str(day)


def receipt(track, day):
    return folder(track, day) / "recibo.json"


def _events(track, day):
    raw = ler_texto(track.audit.path) if track.audit.path.exists() else ""
    key = (sha256_text(raw), track.audit_event)
    cached = getattr(track, "_financial_events_cache", None)
    if cached is None or cached[0] != key:
        from ..contracts import AuditEvent

        events = [AuditEvent.model_validate_json(line) for line in raw.splitlines()
                  if line.strip()]
        cached = (key, [e for e in events if e.event_type == event_type(track)])
        track._financial_events_cache = cached
    return [e for e in cached[1]
            if e.event_type == event_type(track) and e.week == day]


def load(track, original):
    """Somente um recibo autenticado pode substituir a visão corrente do original."""
    from .track_record import record_consistency

    p = receipt(track, original.date)
    events = _events(track, original.date)
    if not p.exists() and not events:
        return None
    if not p.is_file() or p.is_symlink():
        raise ValueError("retificação financeira removida ou inválida")
    body = json.loads(ler_texto(p))
    if len(events) != 1 or events[0].payload_hash != sha256_obj(body):
        raise ValueError("retificação financeira sem vínculo íntegro na auditoria")
    if not track.audit.verify_chain()[0]:
        raise ValueError("trilha da retificação financeira adulterada")
    if (body["policy"] != POLICY or body["session"] != str(original.date)
            or body["track_event"] != track.audit_event
            or body["original_record_hash"] != original.record_hash
            or original.compute_hash() != original.record_hash
            or body["original_sha256"] != sha256_file(track.record_path(original.date))):
        raise ValueError("original da retificação financeira diverge do recibo")
    if sha256_obj(original.record_hash) not in track._audited_hashes():
        raise ValueError("original sem evento diário autenticado")
    from .risco_diario import MARKER

    if MARKER in original.input_hashes:
        original_diagnostic = track.root / "risco_diario" / f"{original.date}.json"
        if (not original_diagnostic.is_file()
                or sha256_file(original_diagnostic) != original.input_hashes[MARKER]):
            raise ValueError("diagnóstico original removido/adulterado")
    for name, h in body["files"].items():
        if name not in {"registro.json", "diagnostico.json"}:
            raise ValueError("arquivo inválido no recibo financeiro")
        file = p.parent / name
        if not file.is_file() or file.is_symlink() or sha256_file(file) != h:
            raise ValueError("anexo da retificação financeira ausente/adulterado")
    rec = DailyRecord.model_validate_json(ler_texto(p.parent / "registro.json"))
    if (rec.date != original.date or rec.prev_record_hash != original.prev_record_hash
            or rec.record_hash != rec.compute_hash() or record_consistency(rec)
            or rec.nav_start_usd != original.nav_start_usd
            or rec.live_book_week != original.live_book_week
            or rec.approval_hash != original.approval_hash):
        raise ValueError("registro retificado inválido ou altera decisão/efetivação")
    if not original.is_synthetic:
        from ..data.eventos_corporativos import catalog

        actions = tuple(e for e in catalog() if e.effective_on <= rec.date
                        and e.ticker in body["tickers"])
        if digest(actions) != body["actions_sha256"]:
            raise ValueError("evidência/política da retificação financeira divergente")
    return rec, body


def effective(track, original):
    result = load(track, original)
    return result[0] if result else original


def diagnostic_path(track, record):
    p = folder(track, record.date) / "diagnostico.json"
    original = track._load_original(track.record_path(record.date))
    result = load(track, original)
    if result is None or result[0].record_hash != record.record_hash:
        raise ValueError("diagnóstico sem retificação autenticada")
    return p


def seal(track, original, corrected, diagnostic, actions):
    """Sela candidato produzido pelo motor. Repetição literal não gera novo evento."""
    from .risco_diario import MARKER, text
    from .track_record import record_consistency, record_json, write_exclusive

    recusar_escrita(track.somente_leitura)
    if (original.record_hash != original.compute_hash()
            or sha256_obj(original.record_hash) not in track._audited_hashes()
            or track._load_original(track.record_path(original.date)) != original
            or corrected.record_hash != corrected.compute_hash()
            or corrected.prev_record_hash != original.prev_record_hash
            or corrected.date != original.date
            or corrected.nav_start_usd != original.nav_start_usd
            or corrected.live_book_week != original.live_book_week
            or corrected.approval_hash != original.approval_hash):
        raise ValueError("candidato/original inválido; retificação recusada antes de gravar")
    if not original.is_synthetic and not actions:
        raise ValueError("retificação exige evento corporativo com evidência primária")
    if original.date != track.dates()[-1]:
        raise ValueError("retificação somente na cauda; histórico exige replay de todo o sufixo")
    previous = [track._load(p) for d, p in track._record_files() if d < original.date]
    if record_consistency(corrected, previous[-1] if previous else None):
        raise ValueError("contas da retificação financeira incoerentes")
    if MARKER in corrected.input_hashes:
        if diagnostic is None or sha256_text(text(diagnostic)) != corrected.input_hashes[MARKER]:
            raise ValueError("diagnóstico divergente do registro retificado")
    p = folder(track, original.date)
    files = {"registro.json": record_json(corrected)}
    if diagnostic is not None:
        files["diagnostico.json"] = text(diagnostic)
    body = {"policy": POLICY, "session": str(original.date), "track_event": track.audit_event,
            "original_record_hash": original.record_hash,
            "original_sha256": sha256_file(track.record_path(original.date)),
            "actions_sha256": digest(actions), "tickers": sorted({e.ticker for e in actions}),
            "files": {k: sha256_text(v) for k, v in files.items()}}
    existing = _events(track, original.date)
    if existing:
        found = load(track, original)
        if found[0] != corrected or found[1] != body:
            raise ValueError("retificação financeira já selada com conteúdo diferente")
        return body
    for name, raw in {**files, "recibo.json": text(body)}.items():
        file = p / name
        if file.exists():
            if ler_texto(file) != raw:
                raise ValueError("preparação financeira interrompida com conteúdo divergente")
        else:
            write_exclusive(file, raw)
    track.audit.append(event_type(track), "CDP", body,
                       "Retificação financeira por evento corporativo; original preservado.",
                       week=original.date)
    load(track, original)
    return body


class BeforeTrack:
    """Visão histórica para recompor a cauda sem contar o dia antigo duas vezes."""
    def __init__(self, track, before):
        self.track, self.before = track, before

    def __getattr__(self, name):
        return getattr(self.track, name)

    def records(self):
        return [self.track._load(p) for d, p in self.track._record_files() if d < self.before]

    def iter_records(self, reverse=False):
        return iter(sorted(self.records(), key=lambda r: r.date, reverse=reverse))

    def frame(self):
        import pandas as pd

        from .track_record import CSV_COLUMNS, record_summary

        rows = [record_summary(r) for r in self.records()]
        f = pd.DataFrame(rows, columns=CSV_COLUMNS)
        f["date"] = pd.to_datetime(f["date"])
        return f.set_index("date")

    def last(self):
        records = self.records()
        return records[-1] if records else None

    def get(self, day):
        return self.track.get(day) if day < self.before else None


def pending(rt):
    from ..data.eventos_corporativos import catalog

    track = rt.track()
    paths = track._record_files()
    if not paths:
        return {"pendente": False}
    last = track._load_original(paths[-1][1])
    held = {p.ticker for p in last.positions if p.market_value_usd}
    events = [e for e in (() if last.is_synthetic else catalog())
              if e.effective_on == last.date and e.ticker in held]
    dates = set()
    problems = []
    for day, path in paths:
        try:
            corrected = load(track, track._load_original(path))
            if corrected is not None:
                report_receipt(rt, day)
            elif day == last.date and events and "corporate_actions_v1" not in last.input_hashes:
                dates.add(day)
        except (OSError, ValueError, KeyError, TypeError) as error:
            # Agenda admite a recuperação; as leituras financeiras e o comando
            # continuam exigindo autenticação integral antes de usar/gravar valores.
            dates.add(day)
            problems.append(f"{day}: {error}")
    return {"pendente": bool(dates), "data": str(min(dates) if dates else last.date),
            "datas_pendentes": sorted(str(d) for d in dates),
            "problemas": problems, "tickers": sorted(e.ticker for e in events)}


def prepare(rt, day):
    """Recalcula ambas as carteiras sem rede, execução de ordens ou escrita."""
    runner = rt._runner()
    main_track = runner.track
    def original_tail(track):
        # Um candidato sem evento é inativo. seal compara todos os bytes
        # preparados antes de autenticar o anexo, em ambas as carteiras.
        if not receipt(track, day).exists() or _events(track, day):
            return track
        from .track_record import TrackRecord

        class OriginalTail(TrackRecord):
            def _load(self, path):
                raw = self._load_original(path)
                return raw if raw.date == day else super()._load(path)

        return OriginalTail(track.root, audit_path=track.audit.path,
                            audit_event=track.audit_event, somente_leitura=True)

    runner.track = runner.main.track = original_tail(main_track)
    original = main_track._load_original(main_track.record_path(day))
    if day != main_track.dates()[-1] or original.live_book_week == day:
        raise ValueError("retificação exige cauda sem execução MOC no próprio dia")
    if original.input_hashes.get("corporate_actions_v1"):
        raise ValueError("registro original já contém política de eventos corporativos")
    # Auditoria dos originais antes de calcular qualquer substituição.
    ok, problems = runner.track.verify()
    if not ok:
        raise ValueError("trilha original inválida: " + "; ".join(problems))
    prefix = BeforeTrack(main_track, day)
    prev = prefix.last()
    if prev is None:
        raise ValueError("sem registro anterior para retificação")
    runner.track = runner.main.track = prefix
    md = runner._session_market(day)
    actions = md.corporate_actions
    if not any(e.effective_on == day and any(p.ticker == e.ticker and p.market_value_usd
               for p in prev.positions) for e in actions):
        raise ValueError("nenhum evento verificado afeta as posições do registro")
    ctx = runner.context(day, md, prev)
    outputs = []
    shadow_hash = None
    if runner.shadow is not None and runner.shadow.track.record_path(day).exists():
        tr = runner.shadow.track
        raw = tr._load_original(tr.record_path(day))
        if raw.live_book_week == day or not original_tail(tr).verify()[0]:
            raise ValueError("sombra exige replay/possui trilha inválida")
        runner.shadow.track = BeforeTrack(tr, day)
        result = runner._prepare_side(runner.shadow, ctx, runner.shadow.track.last(), None)
        shadow_hash = result.record.record_hash
        outputs.append((tr, raw, result))
    result = runner._prepare_side(runner.main, ctx, prev, None,
        extra_alerts=["RETIFICAÇÃO FINANCEIRA: evento corporativo aplicado; original preservado."],
        extra_hashes={"shadow_record": shadow_hash} if shadow_hash else None)
    outputs.append((main_track, original, result))
    return outputs, actions


def corrected_report(rt, day):
    """Relatório completo novo; recibo autentica também os bytes de apresentação."""
    from ..research.commentary import (
        DailyCommentaryOutput,
        _template_output,
        factbook_json,
        load_commentary_file,
        render_facts_md,
    )
    from .reports import render_daily_report
    from .risco_diario import text
    from .track_record import write_exclusive

    track = rt.track()
    rec = track.get(day)
    raw = track._load_original(track.record_path(day))
    if load(track, raw) is None:
        raise ValueError("sem retificação financeira autenticada")
    out = rt.reports_root / "daily" / str(day) / "retificacoes" / "financeira"
    if (out / "recibo.json").exists():
        prepared = report_receipt(rt, day, require_event=False)
        if not any(e.event_type == "DAILY_FINANCIAL_REPORT" and e.week == day
                   for e in track.audit.events()):
            track.audit.append("DAILY_FINANCIAL_REPORT", "CDP", prepared,
                               "Retomada do relatório financeiro previamente selado.", week=day)
        return report_receipt(rt, day)
    fb, history = rt._daily_factbook(day, rec)
    def write_or_match(path, content):
        if path.exists():
            if path.is_symlink() or ler_texto(path) != content:
                raise ValueError("preparação de relatório divergente; não sobrescrever")
        else:
            write_exclusive(path, content)

    for name, content in {"factbook.json": factbook_json(fb)}.items():
        write_or_match(out / name, content)
    write_or_match(out / "facts.md", render_facts_md(
        rec, fb, out / "comentario.json", mind_hint=rt.mente_esperada()))
    write_or_match(out / "comentario.schema.json", json.dumps(
        DailyCommentaryOutput.model_json_schema(), ensure_ascii=False,
        indent=2, sort_keys=True) + "\n")
    template = _template_output(fb, rt.mente_esperada() or "codex").model_dump()
    template["headline"] = "Fechamento retificado: retorno de {{fact:day.ret}}"
    template["paragraphs"] = [
        "RETIFICAÇÃO FINANCEIRA. O evento corporativo dos ADSs de Embraer foi aplicado "
        "aos retornos e às quantidades. Esta edição substitui os resultados anteriormente "
        "divulgados para a mesma data; o relatório original permanece preservado para auditoria. "
        "DADOS SIMULADOS, com preços reais e execução hipotética.",
        *template["paragraphs"][:3]]
    comment = DailyCommentaryOutput.model_validate(template)
    comment_path = out / "comentario.json"
    write_or_match(comment_path, text(comment.model_dump(mode="json")))
    rendered, issues = load_commentary_file(comment_path, fb, record=rec,
                                           expected_mind=rt.mente_esperada())
    if issues:
        raise ValueError("comentário retificado inválido: " + "; ".join(issues))
    md, markup = render_daily_report(rec, history, rendered, rt.cfg.fund.name, cfg=rt.cfg)
    write_or_match(out / "relatorio.md", md)
    write_or_match(out / "relatorio.html", markup)
    report = {"md": str(out / "relatorio.md"), "html": str(out / "relatorio.html"),
              "md_sha256": sha256_file(out / "relatorio.md"),
              "html_sha256": sha256_file(out / "relatorio.html")}
    allowed = {"relatorio.md", "relatorio.html", "factbook.json", "comentario.json",
               "comentario.schema.json", "facts.md"}
    if set(p.name for p in out.iterdir()) != allowed:
        raise ValueError("arquivo extra na preparação financeira; nada autenticado")
    body = {"record_hash": rec.record_hash, "original_record_hash": raw.record_hash,
            "report": report, "date": str(day),
            "current_files": {p.name: sha256_file(p) for p in out.iterdir() if p.is_file()},
            "original_report": {name: sha256_file(rt.reports_root / "daily" / str(day) / name)
                for name in ("relatorio.md", "relatorio.html", "factbook.json", "comentario.json")}}
    prepared = [e for e in track.audit.events()
                if e.event_type == "DAILY_FINANCIAL_REPORT_PREPARED" and e.week == day]
    if prepared and (len(prepared) != 1 or prepared[0].payload_hash != sha256_obj(body)):
        raise ValueError("preparação do relatório não corresponde ao candidato recomposto")
    if not prepared:
        track.audit.append("DAILY_FINANCIAL_REPORT_PREPARED", "CDP", body,
                           "Preparação autenticada do relatório financeiro retificado.", week=day)
    write_or_match(out / "recibo.json", text(body))
    report_receipt(rt, day, require_event=False)
    track.audit.append("DAILY_FINANCIAL_REPORT", "CDP", body,
                       "Relatório diário retificado; original preservado.", week=day)
    return report_receipt(rt, day)


def report_receipt(rt, day, *, require_event=True):
    out = rt.reports_root / "daily" / str(day) / "retificacoes" / "financeira"
    body = json.loads(ler_texto(out / "recibo.json"))
    events = [e for e in rt.book.audit.events()
              if e.event_type == "DAILY_FINANCIAL_REPORT" and e.week == day]
    prepared = [e for e in rt.book.audit.events()
                if e.event_type == "DAILY_FINANCIAL_REPORT_PREPARED" and e.week == day]
    if len(prepared) != 1 or prepared[0].payload_hash != sha256_obj(body):
        raise ValueError("recibo do relatório não possui preparação autenticada")
    if (len(events) > 1 or require_event and not events
            or events and events[0].payload_hash != sha256_obj(body)):
        raise ValueError("relatório retificado sem recibo autenticado")
    if body["record_hash"] != rt.track().get(day).record_hash:
        raise ValueError("relatório retificado não corresponde ao registro corrente")
    tr = rt.track()
    original = tr._load_original(tr.record_path(day))
    if body["date"] != str(day) or body["original_record_hash"] != original.record_hash:
        raise ValueError("recibo não corresponde à data/original da retificação")
    for name, expected in body["original_report"].items():
        if name not in {"relatorio.md", "relatorio.html", "factbook.json", "comentario.json"}:
            raise ValueError("nome inválido no recibo do relatório original")
        if sha256_file(rt.reports_root / "daily" / str(day) / name) != expected:
            raise ValueError("relatório original não preservado")
    for kind in ("md", "html"):
        if sha256_file(out / f"relatorio.{kind}") != body["report"][f"{kind}_sha256"]:
            raise ValueError("relatório retificado adulterado")
    allowed = {"relatorio.md", "relatorio.html", "factbook.json", "comentario.json",
               "comentario.schema.json", "facts.md"}
    if set(body["current_files"]) != allowed:
        raise ValueError("arquivos da edição financeira retificada divergentes")
    for name, expected in body["current_files"].items():
        if (out / name).is_symlink() or sha256_file(out / name) != expected:
            raise ValueError("insumo/texto do relatório retificado adulterado")
    return body


def report_folder(reports_root, day):
    """Localiza a edição corrente para UI/portal, autenticando a retificação."""
    from types import SimpleNamespace

    from .track_record import TrackRecord

    root = Path(reports_root)
    original = root / "daily" / str(day)
    corrected = original / "retificacoes" / "financeira"
    book = root.parent / "book" / "track_record"
    tr = TrackRecord(book, somente_leitura=True)
    raw_path = tr.record_path(day)
    financial = load(tr, tr._load_original(raw_path)) if raw_path.exists() else None
    if financial is None and not corrected.exists():
        return original
    if not (corrected / "recibo.json").is_file():
        raise ValueError("relatório retificado ausente; não reativar edição original")
    facade = SimpleNamespace(reports_root=root, track=lambda: tr,
                             book=SimpleNamespace(audit=tr.audit))
    report_receipt(facade, day)
    return corrected


def cmd(args):
    import sys

    from .runtime import Runtime

    try:
        rt = Runtime.from_args(args)
        if args.publish:
            from .retificacao_semanal import _autorizar_cli

            _autorizar_cli(args, rt.mente_esperada(), rt)
        outputs, actions = prepare(rt, args.date)
        result = {"data": str(args.date), "publicado": False, "carteiras": []}
        for track, original, candidate in outputs:
            if args.publish:
                seal(track, original, candidate.record, candidate.diagnostic, actions)
            result["carteiras"].append({"serie": track.root.name,
                "registro_original": original.record_hash,
                "registro_retificado": candidate.record.record_hash,
                "retorno_original": original.ret, "retorno_retificado": candidate.record.ret,
                "nav_retificado": candidate.record.nav_end_usd})
        if args.publish:
            result["relatorio"] = corrected_report(rt, args.date)
            result["publicado"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"cdp daily rectify: {exc}", file=sys.stderr)
        return 1
