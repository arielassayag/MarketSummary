"""Agenda operacional do CDP — o que a rotina local deve fazer agora (determinístico).

Usada pelas skills do plugin ``cdp`` (tarefas agendadas no PC local) e pelo ``cdp agenda``: pelo
relógio de Brasília (independente do fuso do PC), diz se hoje é o dia de montagem da semana (com
``LAST_US_SESSION``, o último pregão da semana na NYSE), se a decisão já foi gravada, se a
janela de pesquisa abriu e se o prazo EFETIVO venceu (``semanal.prazo_efetivo``: o teto local ou
o fechamento mais cedo entre NYSE/B3/BMV menos a margem — 14h15 nos fechamentos antecipados dos
EUA), quais mercados não negociam no dia, quais fechamentos diários estão pendentes (inclusive
de dias em que o PC estava desligado ou dormindo), quais relatórios diários faltam publicar, se
o relatório semanal de resultado da noite do dia de montagem está pendente
(``relatorio_semanal``), se o retrato diário da cobertura está pendente (``cobertura``) e quais
semanas decididas ainda não têm a tese de investimento da carteira publicada (``acao: "tese"``
na semana corrente e ``teses_pendentes``), o último pregão da base de mercado
(``base_ultimo_pregao``) e os pedidos de kill switch publicados por rotinas sem a trava exclusiva
e ainda não aplicados no livro (``kill_switch_pedidos``). Só calendário e arquivos — nenhum
número de mercado.

Data de início do mandato (``fund.inception_date``): antes dela, com o livro vazio, a fase é
``"pre_inicio"`` (``semanal.acao = "aguardar"``; sem fechamentos, relatórios nem monitor de
risco); a data de início é sempre dia de montagem (carteira inaugural, mesmo numa sexta), depois
vale a regra semanal. ``reinicio.pendente`` diz que o livro ainda tem chaves anteriores à data de
início sem gênese: a rotina roda ``cdp reinicio --executar`` antes de qualquer outra etapa.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..calendar import _cal, chave_da_semana, is_session, open_markets, proximas_montagens

if TYPE_CHECKING:  # pragma: no cover
    from .runtime import Runtime

#: Calendários em que o fechamento diário registra (mesma regra de ``Runtime.daily_close``).
DAILY_EXCHANGES = ("BVMF", "XNYS", "XMEX")
#: Máximo de pregões listados como pendentes (acima disso, a rotina pede intervenção).
MAX_PENDING = 30
#: Semanas decididas mais recentes examinadas em ``teses_pendentes``.
THESIS_WEEKS = 4
#: Gênese da cobertura (retrato do fechamento de quinta, véspera da carteira inaugural).
COBERTURA_INICIO = date(2026, 10, 8)
_WEEKDAYS_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
                "sábado", "domingo")


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


def _sem_carteira(rt: Runtime, antes_de: date) -> bool:
    """Nenhuma semana decidida antes de ``antes_de`` (o fundo ainda não tem carteira: a próxima
    montagem é a carteira inaugural)."""
    try:
        return not any(rt.book.list_decisions(w) for w in rt.book.list_weeks() if w < antes_de)
    except OSError:  # pragma: no cover - disco
        return False


def _weekly(rt: Runtime, local: datetime) -> dict[str, Any]:
    from .runtime import PREPARE_MANIFEST
    from .tese import is_published, thesis_applicable

    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    if rt.pre_inicio(today):
        inicio = cfg.fund.inception_date
        out = {"semana": inicio, "hoje_e_dia_de_rebalanceamento": False,
               "inicio_pesquisa": cfg.fund.weekly_research_start_local,
               "prazo_decisao": cfg.fund.decision_deadline_local,
               "decisao_gravada": False, "briefing_preparado": False,
               "entradas_escritas": {"research_pack.json": False, "pm_decision.json": False},
               "tese_publicada": False, "acao": "aguardar",
               "motivo": (f"pré-início: carteira inaugural em {inicio:%d/%m/%Y} "
                          f"({_dia(inicio).split(',')[0]}), ao preço de fechamento")}
        out.update(_janela_info(rt, inicio, local))
        return out
    week = chave_da_semana(today, cfg)
    info: dict[str, Any] = {"semana": week, "hoje_e_dia_de_rebalanceamento": week == today,
                            "inicio_pesquisa": cfg.fund.weekly_research_start_local,
                            "prazo_decisao": cfg.fund.decision_deadline_local}
    if week is None:
        info.update({"acao": "nenhuma", "motivo": "semana sem pregão no calendário de "
                                                  "rebalanceamento"})
        return info
    info.update(_janela_info(rt, week if week >= today else _proxima(rt, today), local))
    wd = rt.week_dir(week)
    decided = bool(rt.book.list_decisions(week))
    briefing = (wd / "briefing" / PREPARE_MANIFEST).exists()
    inputs = {n: (wd / "inputs" / n).exists() for n in ("research_pack.json", "pm_decision.json")}
    thesis = is_published(rt.book_root, week)
    info.update({"decisao_gravada": decided, "briefing_preparado": briefing,
                 "entradas_escritas": inputs, "tese_publicada": thesis})
    needs_thesis = decided and not thesis and thesis_applicable(rt.book, week)
    pending_thesis = {"acao": "tese",
                      "motivo": "decisão da semana gravada; a tese de investimento da carteira "
                                "ainda não foi publicada (cdp tese prepare → tese.json → "
                                "validate-tese → tese publish)"}
    start = _at(today, cfg.fund.weekly_research_start_local, tz)
    deadline = rt.decision_deadline(today).astimezone(tz)
    # Sem carteira anterior (nenhuma semana decidida antes desta), a montagem é a carteira
    # inaugural — na data de início ou, se ela passou sem decisão, na próxima data de montagem.
    inaugural = week >= cfg.fund.inception_date and _sem_carteira(rt, week)
    mantida = ("fundo sem carteira até a próxima data de montagem" if inaugural
               else "carteira anterior mantida até a próxima semana")
    if week != today:
        info["acao"] = "nenhuma"
        if week > today:
            info["motivo"] = (f"a carteira inaugural é montada em {week}" if inaugural
                              else f"a montagem desta semana é {_dia(week)}")
        elif needs_thesis:
            info.update(pending_thesis)
        elif decided:
            info["motivo"] = f"hoje não é o dia de montagem da semana ({week}); decisão já gravada"
        else:
            info["motivo"] = (f"hoje não é o dia de montagem da semana ({week}) e a semana NÃO "
                              f"teve decisão gravada: {mantida} (o código não permite decidir "
                              "fora do dia de montagem)")
            info["decisao_perdida"] = True
        return info
    info["minutos_ate_o_prazo"] = int((deadline - local).total_seconds() // 60)
    if needs_thesis:
        info.update(pending_thesis)
    elif decided:
        info.update({"acao": "nenhuma", "motivo": "decisão da semana já gravada"})
    elif local >= deadline:
        info.update({"acao": "prazo_vencido", "decisao_perdida": True,
                     "motivo": (f"prazo efetivo de {deadline:%H:%M} vencido sem "
                                "decisão: NÃO decidir (o fechamento seria conhecido); "
                                + ("carteira inaugural não montada, " if inaugural else "")
                                + mantida)})
    elif local < start:
        info.update({"acao": "aguardar",
                     "motivo": f"a pesquisa começa às {cfg.fund.weekly_research_start_local}"})
    else:
        etapa = ("prepare" if not briefing else
                 "pesquisa" if not all(inputs.values()) else "validar_e_decidir")
        info.update({"acao": "montar", "etapa": etapa,
                     "motivo": ("carteira inaugural, dentro da janela de decisão" if inaugural
                                else "dia de montagem da semana, dentro da janela de decisão")})
    if inaugural:
        info["carteira_inaugural"] = True
    return info


def _dia(d: date) -> str:
    return f"{_WEEKDAYS_PT[d.weekday()]}, {d:%d/%m}"


def _proxima(rt: Runtime, today: date) -> date:
    for d in proximas_montagens(today, rt.cfg):
        return d
    return today  # pragma: no cover - calendário sem pregão por semanas


def _janela_info(rt: Runtime, dia: date, local: datetime) -> dict[str, Any]:
    """Prazo efetivo, mercados fechados e fechamento antecipado do dia de montagem ``dia``."""
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    deadline = rt.decision_deadline(dia).astimezone(tz)
    out: dict[str, Any] = {
        "proximo_rebalanceamento": dia, "prazo_efetivo": deadline,
        "mercados_fechados": sorted(m for m, ok in open_markets(dia).items() if not ok),
        "fechamento_antecipado": False, "mercados_fechamento_antecipado": [],
    }
    if cfg.execution is not None:
        from ..portfolio.execucao import MIC_NOME, janela_execucao, mics_antecipados

        j = janela_execucao(dia, cfg)
        # Sinal do dia: NYSE, B3 ou BMV fecham mais cedo (definem o prazo); fechamentos
        # antecipados de outros mercados só reduzem a capacidade deles.
        out["fechamento_antecipado"] = j.fechamento_antecipado
        out["mercados_fechamento_antecipado"] = sorted(MIC_NOME.get(m, m)
                                                       for m in mics_antecipados(j, cfg))
    if dia == local.date():
        out["minutos_ate_o_prazo"] = int((deadline - local).total_seconds() // 60)
    return out


#: Dias de montagem mais recentes examinados no relatório semanal pendente.
WEEKLY_REPORT_LOOKBACK = 8


def weekly_report_status(rt: Runtime, local: datetime) -> dict[str, Any]:
    """Relatório semanal de resultado (noite de TODO dia de montagem da regra, com ou sem
    decisão gravada — sem decisão, a carteira foi mantida e o relatório traz resultado,
    atribuição e risco da semana).

    Pendente quando algum dos dias de montagem mais recentes até hoje já tem o registro diário
    do fechamento e ainda não tem ``reports/semanal/<data>/relatorio.md``; ``pendentes`` lista
    todos (do mais antigo ao mais recente) e ``data`` é o mais antigo — nenhum relatório fica
    para trás quando o seguinte é decidido. Só com a seção ``execution`` no mandato (o
    relatório semanal pertence à execução no fechamento; na regra anterior nada é pendente)."""
    from .relatorio_semanal import dia_de_relatorio, report_dir

    out: dict[str, Any] = {"pendente": False, "data": None, "pendentes": []}
    if rt.cfg.execution is None:
        out["motivo"] = "relatório semanal de resultado ativado com a seção execution do mandato"
        return out
    try:
        dates = [d for d in rt.track().dates() if d <= local.date()]
        dias = [d for d in dates if dia_de_relatorio(rt, d)][-WEEKLY_REPORT_LOOKBACK:]
    except OSError:  # pragma: no cover - disco
        return out
    if not dias:
        return out
    pend = [d for d in dias if not (report_dir(rt, d) / "relatorio.md").exists()]
    w = pend[0] if pend else dias[-1]
    folder = report_dir(rt, w)
    out.update({"data": w, "registro_do_fechamento": True,
                "publicado": (folder / "relatorio.md").exists(),
                "decisao_gravada": bool(rt.book.list_decisions(w)),
                "fatos": (folder / "fatos.md").exists(),
                "comentario_escrito": (folder / "comentario.json").exists(),
                "pendentes": pend})
    out["pendente"] = bool(pend)
    if out["pendente"]:
        out["passos"] = (f"cdp weekly close-report --date {w} → comentario.json → "
                         f"cdp validate-weekly-report --date {w} → "
                         f"cdp weekly close-report --date {w} --publish")
    return out


def coverage_status(rt: Runtime, local: datetime) -> dict[str, Any]:
    """Retrato diário da cobertura: pendente em dia útil ≥ 08/10/2026 (gênese: fechamento de
    quinta) depois do horário da rotina diária, quando não há retrato da data e o comando
    ``cdp cobertura run`` está disponível nesta versão."""
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    out: dict[str, Any] = {"snapshot_pendente": False, "data": None}
    try:
        import inspect

        from ..cobertura import cli as cob_cli
        from ..cobertura.livro import datas_snapshots

        if "NotImplementedError" in inspect.getsource(cob_cli.cmd_run) or \
                "em implementação" in inspect.getsource(cob_cli.cmd_run):
            raise ImportError("stub")
    except (ImportError, OSError, TypeError):
        out["motivo"] = "comando de cobertura indisponível nesta versão"
        return out
    today = local.date()
    alvo: date | None = None
    d = today
    for _ in range(10):
        if d < COBERTURA_INICIO:
            break
        if is_close_session(d) and (d < today or local >= _at(today,
                                                               cfg.fund.daily_close_run_local,
                                                               tz)):
            alvo = d
            break
        d -= timedelta(days=1)
    if alvo is None:
        out["motivo"] = (f"antes da gênese da cobertura ({COBERTURA_INICIO:%d/%m/%Y}, após o "
                         "fechamento)" if today <= COBERTURA_INICIO else
                         "nenhum pregão encerrado desde o último retrato")
        return out
    try:
        feitos = set(datas_snapshots(rt.book_root))
    except OSError:  # pragma: no cover - disco
        feitos = set()
    out["data"] = alvo
    out["snapshot_pendente"] = alvo not in feitos
    if out["snapshot_pendente"]:
        out["passo"] = f"cdp cobertura run --date {alvo}"
    return out


def pending_theses(rt: Runtime, limit: int = THESIS_WEEKS) -> list[date]:
    """Semanas decididas (as ``limit`` mais recentes) com carteira nova e sem tese publicada."""
    from .tese import is_published, thesis_applicable

    try:
        weeks = rt.book.list_weeks()
    except OSError:
        return []
    decided = [w for w in weeks if rt.book.list_decisions(w)][-limit:]
    return [w for w in decided
            if not is_published(rt.book_root, w) and thesis_applicable(rt.book, w)]


def _next_events(rt: Runtime, local: datetime, weekly: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    today = local.date()
    events: list[dict[str, Any]] = []
    pre = rt.pre_inicio(today)
    # Antes da data de início, nenhum dia de montagem anterior a ela (mesmo se a data de início
    # estiver a mais de uma semana).
    for first in proximas_montagens(cfg.fund.inception_date if pre else today, cfg):
        deadline = rt.decision_deadline(first).astimezone(tz)
        if first == today and (weekly.get("decisao_gravada") or deadline <= local):
            continue
        inaugural = first >= cfg.fund.inception_date and _sem_carteira(rt, first)
        events.append({"evento": ("carteira inaugural (decisão autônoma)" if inaugural
                                  else "decisão semanal (autônoma)"), "quando": deadline,
                       "nota": f"pesquisa a partir de {cfg.fund.weekly_research_start_local}; "
                               "execução no leilão de fechamento (MOC)"})
        run = _at(first, cfg.fund.daily_close_run_local, tz)
        if cfg.execution is not None and run > local:
            events.append({"evento": "relatório semanal de resultado", "quando": run,
                           "nota": "mudanças da carteira, resultado e atribuição da semana e "
                                   "desde o início"})
        break
    start = cfg.fund.inception_date if pre else today
    for k in range(0, 15):
        d = start + timedelta(days=k)
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
    from .reinicio import situacao

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
        "kill_switch_pedidos": _kill_switch_requests(rt),
        "fase": "pre_inicio" if rt.pre_inicio(local.date()) else "operacao",
        "data_de_inicio": cfg.fund.inception_date,
        "reinicio": situacao(rt),
        "ultimo_registro_diario": last[-1] if last else None,
        "base_ultimo_pregao": _store_last(rt),
        "semanal": weekly,
        "fechamentos_pendentes": closes[:MAX_PENDING],
        "fechamentos_pendentes_excedem_limite": len(closes) > MAX_PENDING,
        "horario_fechamento_diario": cfg.fund.daily_close_run_local,
        "publicacoes_pendentes": pubs,
        "relatorio_semanal": weekly_report_status(rt, local),
        "cobertura": coverage_status(rt, local),
        "teses_pendentes": pending_theses(rt),
        "proximos_eventos": _next_events(rt, local, weekly),
    }


def _store_last(rt: Runtime) -> date | None:
    """Último pregão gravado na base de mercado (dados públicos); ``None`` sem base legível. Gate
    da rotina diária no pré-início: base defasada ⇒ atualizar antes da carteira inaugural."""
    try:
        v = rt.store_last_date()
    except Exception:  # noqa: BLE001 - base ausente ou ilegível
        return None
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def _kill_switch_requests(rt: Runtime) -> list[dict[str, Any]]:
    """Pedidos de kill switch publicados (``reports/risk/<data>/kill_switch_<HHMM>.yaml``) ainda
    não aplicados no livro: a próxima execução exclusiva (semanal ou diária) os aplica."""
    try:
        reqs = rt.kill_switch_requests()
    except (OSError, ValueError):
        return []
    return [{"arquivo": r["arquivo"], "em": r["em"], "motivo": r["motivo"],
             "superado": r["superado"]} for r in reqs]


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


__all__ = ["COBERTURA_INICIO", "DAILY_EXCHANGES", "WEEKLY_REPORT_LOOKBACK", "agenda",
           "b3_open_at", "coverage_status",
           "is_close_session", "pending_closes", "pending_publications", "pending_theses",
           "validate_daily_commentary", "weekly_report_status"]
