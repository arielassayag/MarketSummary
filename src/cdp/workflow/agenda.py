"""Agenda operacional do CDP — o que a rotina local deve fazer agora (determinístico).

Usada pelas skills do plugin ``cdp`` (tarefas agendadas no PC local) e pelo ``cdp agenda``: pelo
relógio de Brasília (independente do fuso do PC), diz se hoje é o primeiro pregão da semana na
B3, se a decisão já foi gravada, se a janela de pesquisa abriu e se o prazo de 16h30 venceu, quais
fechamentos diários estão pendentes (inclusive de dias em que o PC estava desligado ou dormindo)
e quais relatórios diários faltam publicar. Só calendário e arquivos — nenhum número de mercado.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..calendar import _cal, first_session_of_week, is_session

if TYPE_CHECKING:  # pragma: no cover
    from .runtime import Runtime

#: Calendários em que o fechamento diário registra (mesma regra de ``Runtime.daily_close``).
DAILY_EXCHANGES = ("BVMF", "XNYS", "XMEX")
#: Máximo de pregões listados como pendentes (acima disso, a rotina pede intervenção).
MAX_PENDING = 30


def _at(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz)


def is_close_session(d: date) -> bool:
    return any(is_session(d, ex) for ex in DAILY_EXCHANGES)


def b3_open_at(moment: datetime) -> bool | None:
    """B3 em pregão contínuo neste minuto (``None`` se o calendário não souber dizer)."""
    try:
        cal = _cal("BVMF")
        ts = pd.Timestamp(moment).tz_convert("UTC").floor("min")
        if not (cal.first_minute <= ts <= cal.last_minute):
            return None
        return bool(cal.is_open_on_minute(ts))
    except Exception:  # noqa: BLE001 - versão do exchange_calendars sem a API
        return None


def pending_closes(rt: Runtime, local: datetime) -> list[date]:
    """Pregões ainda sem registro diário, em ordem, até hoje (hoje só após o horário da rotina).

    Sem nenhum registro, começa na semana de decisão mais antiga do livro (efetivação inicial).
    """
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    try:
        dates = rt.track().dates()
    except OSError:
        dates = []
    if dates:
        start = dates[-1] + timedelta(days=1)
    else:
        decided = [w for w in rt.book.list_weeks() if rt.book.list_decisions(w)]
        if not decided:
            return []
        start = decided[0]
    close_run = _at(today, cfg.fund.daily_close_run_local, tz)
    out: list[date] = []
    d = start
    while d <= today and len(out) < MAX_PENDING + 1:
        if is_close_session(d) and (d < today or local >= close_run):
            out.append(d)
        d += timedelta(days=1)
    return out


def pending_publications(rt: Runtime) -> list[dict[str, Any]]:
    """Registros diários sem ``relatorio.md`` publicado (com o estado do comentário da mente)."""
    try:
        dates = rt.track().dates()
    except OSError:
        return []
    out = []
    for d in dates[-MAX_PENDING:]:
        folder = rt.daily_dir(d)
        if (folder / "relatorio.md").exists():
            continue
        out.append({"data": d, "fatos": (folder / "facts.md").exists(),
                    "comentario_escrito": (folder / "comentario.json").exists()})
    return out


def _weekly(rt: Runtime, local: datetime) -> dict[str, Any]:
    from .runtime import PREPARE_MANIFEST

    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    week = first_session_of_week(today)
    info: dict[str, Any] = {"semana": week, "hoje_e_dia_de_rebalanceamento": week == today,
                            "inicio_pesquisa": cfg.fund.weekly_research_start_local,
                            "prazo_decisao": cfg.fund.decision_deadline_local}
    if week is None:
        info.update({"acao": "nenhuma", "motivo": "semana sem pregão na B3"})
        return info
    wd = rt.week_dir(week)
    decided = bool(rt.book.list_decisions(week))
    briefing = (wd / "briefing" / PREPARE_MANIFEST).exists()
    inputs = {n: (wd / "inputs" / n).exists() for n in ("research_pack.json", "pm_decision.json")}
    info.update({"decisao_gravada": decided, "briefing_preparado": briefing,
                 "entradas_escritas": inputs})
    start = _at(today, cfg.fund.weekly_research_start_local, tz)
    deadline = _at(today, cfg.fund.decision_deadline_local, tz)
    if week != today:
        info["acao"] = "nenhuma"
        if week > today:
            info["motivo"] = f"o primeiro pregão desta semana é {week}"
        elif decided:
            info["motivo"] = f"hoje não é o primeiro pregão da semana ({week}); decisão já gravada"
        else:
            info["motivo"] = (f"hoje não é o primeiro pregão da semana ({week}) e a semana NÃO "
                              "teve decisão gravada: carteira anterior mantida até a próxima "
                              "semana (o código não permite decidir fora do primeiro pregão)")
            info["decisao_perdida"] = True
        return info
    info["minutos_ate_o_prazo"] = int((deadline - local).total_seconds() // 60)
    if decided:
        info.update({"acao": "nenhuma", "motivo": "decisão da semana já gravada"})
    elif local >= deadline:
        info.update({"acao": "prazo_vencido", "decisao_perdida": True,
                     "motivo": (f"prazo de {cfg.fund.decision_deadline_local} vencido sem "
                                "decisão: NÃO decidir (o fechamento seria conhecido); carteira "
                                "anterior mantida até a próxima semana")})
    elif local < start:
        info.update({"acao": "aguardar",
                     "motivo": f"a pesquisa começa às {cfg.fund.weekly_research_start_local}"})
    else:
        etapa = ("prepare" if not briefing else
                 "pesquisa" if not all(inputs.values()) else "validar_e_decidir")
        info.update({"acao": "montar", "etapa": etapa,
                     "motivo": "primeiro pregão da semana, dentro da janela de decisão"})
    return info


def _next_events(rt: Runtime, local: datetime, weekly: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    events: list[dict[str, Any]] = []
    monday = today - timedelta(days=today.weekday())
    for k in range(0, 8):
        first = first_session_of_week(monday + timedelta(weeks=k))
        if first is None or first < today:
            continue
        deadline = _at(first, cfg.fund.decision_deadline_local, tz)
        if first == today and (weekly.get("decisao_gravada") or deadline <= local):
            continue
        events.append({"evento": "decisão semanal (autônoma)", "quando": deadline,
                       "nota": f"pesquisa a partir de {cfg.fund.weekly_research_start_local}; "
                               "execução no fechamento (MOC)"})
        break
    for k in range(0, 15):
        d = today + timedelta(days=k)
        if not is_close_session(d):
            continue
        run = _at(d, cfg.fund.daily_close_run_local, tz)
        if run <= local:
            continue
        events.append({"evento": "fechamento diário", "quando": run,
                       "nota": "marcação, risco, atribuição, comentário e relatório"})
        break
    return sorted(events, key=lambda e: e["quando"])


def agenda(rt: Runtime, now: datetime | None = None) -> dict[str, Any]:
    """Estado operacional determinístico para as rotinas locais (ver docstring do módulo)."""
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    moment = now if now is not None else rt.now()
    local = moment.astimezone(tz)
    pc = datetime.now().astimezone()
    pc_off = pc.utcoffset() or timedelta(0)
    brt_off = pc.astimezone(tz).utcoffset() or timedelta(0)
    weekly = _weekly(rt, local)
    closes = pending_closes(rt, local)
    pubs = pending_publications(rt)
    try:
        last = rt.track().dates()
    except OSError:
        last = []
    return {
        "agora_brasilia": local,
        "fuso_do_mandato": cfg.fund.timezone,
        "fuso_do_pc": str(pc.tzinfo),
        "pc_menos_brasilia_horas": round((pc_off - brt_off).total_seconds() / 3600.0, 2),
        "pregao_b3_hoje": is_session(local.date(), "BVMF"),
        "b3_aberta_agora": b3_open_at(local),
        "kill_switch": rt.kill_switch_active(),
        "ultimo_registro_diario": last[-1] if last else None,
        "semanal": weekly,
        "fechamentos_pendentes": closes[:MAX_PENDING],
        "fechamentos_pendentes_excedem_limite": len(closes) > MAX_PENDING,
        "horario_fechamento_diario": cfg.fund.daily_close_run_local,
        "publicacoes_pendentes": pubs,
        "proximos_eventos": _next_events(rt, local, weekly),
    }


def validate_daily_commentary(rt: Runtime, session: date) -> tuple[bool, list[str]]:
    """Valida ``reports/daily/<data>/comentario.json`` SEM publicar (``daily publish`` é
    imutável e, com problemas, publicaria o template determinístico)."""
    from ..research.commentary import COMMENTARY_JSON, load_commentary_file

    rec = rt.track().get(session)
    if rec is None:
        return False, [f"sem registro diário em {session}: rode `cdp daily close --date "
                       f"{session}` antes"]
    fb, _history = rt._daily_factbook(session, rec)
    _md, issues = load_commentary_file(rt.daily_dir(session) / COMMENTARY_JSON, fb, record=rec)
    return not issues, list(issues)


__all__ = ["DAILY_EXCHANGES", "agenda", "b3_open_at", "is_close_session", "pending_closes",
           "pending_publications", "validate_daily_commentary"]
