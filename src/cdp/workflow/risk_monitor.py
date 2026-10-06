"""Monitor de risco do CDP — Cabra da Peste (fechamento e intradiário).

Somente leitura sobre o livro e a trilha: carrega o último registro diário encadeado
(``book/track_record``) e o livro vigente (semana efetivada que o registro marca) e calcula,
EM CÓDIGO:

- NAV, drawdown a partir do pico e estágio da escada de drawdown do mandato;
- vol ex-ante vs. banda, beta, net/gross, VaR/ES e exposições por país/setor/estilo vs. limites;
- liquidez (dias para liquidar por posição com o ADTV da decisão) e shorts com squeeze HIGH;
- stops de squeeze (perda do short desde a entrada e perda em % do NAV);
- com ``live=True``: cotações do momento (atrasadas pela fonte) → P&L intradiário por posição e
  total contra o último fechamento, em USD com o câmbio do momento, NAV e drawdown estimados.

Gatilhos HARD do mandato (stop de drawdown ``hard_stop``/``stop_out``, velocidade de perda e
escalada de squeeze) geram a ação determinística ``kill-switch: <motivo>``. O kill switch só
bloqueia risco novo (redução continua permitida) e nunca afrouxa limites. Depois que um humano o
desliga (``KILL_SWITCH_OFF`` na trilha de auditoria), a condição que ele já revisou não o religa:
só uma piora (estágio pior da escada, perda extrema num registro de fechamento posterior ao
revisado ou short novo no stop) volta a ser HARD; o resto vira SOFT "já revisado por humano".

Stop de squeeze, regra por nome (``squeeze.stop_scope = "name"``, metodologia vigente): o stop de
um short num fechamento é SOFT e abre um episódio (:func:`cdp.risk.limites.episodios_de_squeeze`)
— o código limita o short à metade das ações do stop no rebalanceamento seguinte, uma vez por
episódio, e veda a compra do emissor até revisão humana registrada na trilha
(:data:`SQUEEZE_STOP_ACTION`; ``cdp kill-switch revisar-squeeze``); o relatório lista os vetos que
aguardam revisão (``squeeze.vetos_compra``). No intradiário o stop é aviso antecipado
(:data:`SQUEEZE_STOP_ACTION_INTRADIARIO`). ``stop_escalation_count`` shorts distintos em stop
dentro de ``stop_escalation_sessions`` pregões escalam para o kill switch do livro (HARD,
:data:`SQUEEZE_ESCALATION_ACTION`). Regra anterior (``"book"``): todo stop escala para o livro
inteiro (:data:`SQUEEZE_STOP_ACTION_LIVRO`).

Fatia idiossincrática monitorada por três medidas (:func:`cdp.risk.idio.serie_idio`): ex-ante
diária, realizada em 63 pregões e sem modelo (1 − R² ajustado), no bloco ``idio`` do relatório.

Ausente continua ausente: cotação sem negócio hoje, câmbio indisponível ou ADTV desconhecido nunca
viram zero. O monitor não altera livro, trilha nem dados; grava apenas o relatório em
``reports/risk/<data>/risco_<HHMM>.md`` (e o ``.json``).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..audit import AuditLog
from ..calendar import chave_da_semana, previous_data_session, previous_session
from ..config import FundConfig
from ..contracts import DailyPosition, DailyRecord, Proposal, Side
from ..hashing import sha256_obj
from .daily import drawdown_stage_action, short_entry_prices
from .memo import fmt_closes, fmt_days, fmt_num, fmt_pct, fmt_usd, fmt_usd_mm
from .track_record import DAILY_RECORD_EVENT

if TYPE_CHECKING:  # pragma: no cover - só para tipos
    from .runtime import Runtime

#: Cobertura mínima do gross com cotação do dia para um gatilho intradiário de drawdown ser HARD.
MIN_LIVE_COVERAGE = 0.95
#: Pasta dos relatórios de risco dentro de ``reports/``.
RISK_DIRNAME = "risk"
#: ``status`` antes da data de início do mandato com o livro vazio (nada a monitorar nem gravar).
PRE_INICIO = "pré-início"
#: Ações recomendadas que ligam o kill switch começam com este prefixo (contrato com a skill).
KILL_SWITCH_PREFIX = "kill-switch: "
REVIEW_PREFIX = "revisar: "
MAX_REASON_CHARS = 480
TOP_CONTRIBUTORS = 5

Level = Literal["HARD", "SOFT", "INFO"]
QuoteFetcher = Callable[[list[str], list[str], list[str] | None], pd.DataFrame]

STAGE_LABEL = {"normal": "normal", "soft_stop": "SOFT STOP", "hard_stop": "HARD STOP",
               "stop_out": "STOP-OUT"}
STAGE_RANK = {"normal": 0, "soft_stop": 1, "hard_stop": 2, "stop_out": 3}


@dataclass(frozen=True)
class Trigger:
    """Gatilho determinístico do monitor (``HARD`` ⇒ kill switch recomendado)."""

    nivel: Level
    codigo: str
    motivo: str
    acao: str


# ----------------------------------------------------------------------------- utilitários


def _num(x: object) -> float | None:
    """Float finito ou ``None`` (nunca converte ausente em zero)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _clip(text: str, n: int = MAX_REASON_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _shell_safe(text: str) -> str:
    """Motivo pronto para ``--reason "<motivo>"`` (sem aspas, crase, cifrão nem barra invertida)."""
    return "".join(ch for ch in text if ch not in "\"'`$\\")


def drawdown_stage(dd: float | None, cfg: FundConfig) -> str | None:
    """Estágio da escada de drawdown do mandato (``None`` se o drawdown é desconhecido)."""
    if dd is None:
        return None
    d = cfg.drawdown
    if dd <= d.stop_out:
        return "stop_out"
    if dd <= d.hard_stop:
        return "hard_stop"
    if dd <= d.soft_stop:
        return "soft_stop"
    return "normal"


def _drawdown_triggers(dd: float | None, cfg: FundConfig, *, origem: str, sufixo: str,
                       hard_allowed: bool = True, nota: str = "") -> list[Trigger]:
    stage = drawdown_stage(dd, cfg)
    if stage in (None, "normal"):
        return []
    d = cfg.drawdown
    limiar = {"stop_out": d.stop_out, "hard_stop": d.hard_stop, "soft_stop": d.soft_stop}[stage]
    exige = drawdown_stage_action(stage, cfg)
    if stage == "soft_stop" and d.risk_reference != "normal_book_vol":
        exige += " no próximo rebalanceamento"
    motivo = (f"{STAGE_LABEL[stage]} {origem}: drawdown {fmt_pct(dd)} atingiu {fmt_pct(limiar)} — "
              f"mandato exige {exige}")
    if nota:
        motivo = f"{motivo} ({nota})"
    hard = stage in ("hard_stop", "stop_out") and hard_allowed
    corte = ("o teto de vol da escada" if d.risk_reference == "normal_book_vol"
             else "o corte do gross")
    acao = (f"ligar o kill switch (só redução de risco) até revisão humana; {corte} é "
            "aplicado pelo código no próximo rebalanceamento" if hard else
            "revisão de risco; o código aplica a escada no próximo rebalanceamento")
    return [Trigger("HARD" if hard else "SOFT", f"drawdown_{stage}_{sufixo}", motivo, acao)]


def _iter_history(track, before: date, inclusive: bool) -> Iterator[DailyRecord]:
    """Registros do mais recente para o mais antigo, até ``before`` (sem o dia corrente)."""
    for rec in track.iter_records(reverse=True):
        if rec.date < before or (inclusive and rec.date == before):
            yield rec


def _fx_from_position(p: DailyPosition) -> float | None:
    """Câmbio (USD por unidade local) implícito na marcação do fechamento."""
    if p.currency == "USD":
        return 1.0
    pl, pu = _num(p.price_local), _num(p.price_usd)
    if pl is None or pu is None or pl <= 0 or pu <= 0:
        return None
    return pu / pl


def _side(p: DailyPosition) -> str:
    return "SHORT" if p.market_value_usd < 0 else "LONG"


# ----------------------------------------------------------------------------- blocos


def squeeze_stop_checks(cfg: FundConfig, shorts: list[dict], history: Iterable[DailyRecord],
                        nav_usd: float) -> list[dict]:
    """Stops de squeeze do mandato para cada short (perda desde a entrada e % do NAV).

    ``shorts``: dicionários com ``ticker``, ``emissor``, ``acoes`` (assinadas), ``preco_local``
    (atual) e ``fx`` (USD por unidade local, ou ``None``). ``history`` vem do mais recente para o
    mais antigo, sem o momento corrente. Preço médio de entrada via
    :func:`cdp.workflow.daily.short_entry_prices` (mesma regra do fechamento diário).
    """
    current = {s["ticker"]: (float(s["acoes"]), float(s["preco_local"])) for s in shorts
               if _num(s.get("acoes")) is not None and _num(s.get("preco_local")) is not None
               and float(s["acoes"]) < 0 and float(s["preco_local"]) > 0}
    if not current:
        return []
    entries = short_entry_prices(history, current)
    out: list[dict] = []
    sq = cfg.squeeze
    for s in shorts:
        avg = entries.get(s["ticker"])
        px = _num(s.get("preco_local"))
        if avg is None or px is None or avg <= 0:
            continue
        loss = px / avg - 1.0
        fx = _num(s.get("fx"))
        loss_usd = abs(float(s["acoes"])) * (px - avg) * fx if fx is not None else None
        loss_nav = loss_usd / nav_usd if loss_usd is not None and nav_usd > 0 else None
        out.append({
            "ticker": s["ticker"], "emissor": s.get("emissor"), "preco_medio_entrada": avg,
            "preco_atual": px, "perda_desde_entrada": loss, "perda_usd": loss_usd,
            "perda_pct_nav": loss_nav,
            "stop_posicao": bool(loss >= sq.stop_short_position_loss),
            "stop_nav": bool(loss_nav is not None and loss_nav >= sq.stop_short_nav_loss),
        })
    return out


#: O que o código faz com um stop de squeeze num fechamento, com a regra por nome
#: (``squeeze.stop_scope = "name"``, metodologia vigente; ``docs/cdp/METODOLOGIA.md`` §4.6): o
#: short fica limitado à metade das ações do stop no rebalanceamento seguinte, uma vez por
#: episódio, e o emissor não pode ficar comprado até revisão humana registrada (o otimizador
#: aplica, ``risk.limites.acoes_de_squeeze``); sem fechamento negociável nesse dia, o corte fica
#: pendente. Um stop isolado não liga o kill switch: só a escalada
#: (:data:`SQUEEZE_ESCALATION_ACTION`).
SQUEEZE_STOP_ACTION = (
    "o código corta este short à metade no próximo rebalanceamento (uma vez por episódio) e o "
    "emissor não pode ficar comprado até revisão humana registrada (sem fechamento negociável no "
    "dia, o corte fica pendente); stop isolado não liga o kill switch — dois shorts distintos em "
    "stop dentro de 5 pregões, sim")
#: Mesmo short ainda em stop depois do corte (preço médio de entrada inalterado): o corte não se
#: repete; o veto de compra segue até a revisão humana.
SQUEEZE_STOP_ACTION_CORTADO = (
    "corte à metade já feito neste episódio (mesmo preço médio de entrada: não se repete); o "
    "emissor segue sem poder ficar comprado até revisão humana registrada; dois shorts distintos "
    "em stop dentro de 5 pregões ligam o kill switch")
#: Stop visto só nas cotações do momento: o corte e o veto valem a partir de um fechamento em
#: stop (registro diário encadeado); a escalada já conta o pregão de hoje.
SQUEEZE_STOP_ACTION_INTRADIARIO = (
    "aviso antecipado: o corte à metade e o veto de compra valem se o short estiver em stop num "
    "fechamento (registro diário); dois shorts distintos em stop dentro de 5 pregões ligam o kill "
    "switch")
#: Código do gatilho INFO com os emissores de compra vedada até revisão humana.
SQUEEZE_VETO_CODE = "stop_squeeze_compra_vedada"
#: Escalada da regra por nome: ``squeeze.stop_escalation_count`` shorts distintos em stop dentro
#: de ``squeeze.stop_escalation_sessions`` pregões (assinatura de desmonte coletivo) ⇒ HARD.
SQUEEZE_ESCALATION_ACTION = (
    "ligar o kill switch: o livro inteiro fica só-redução até revisão humana e cada short em stop "
    "é cortado à metade pelo código no próximo rebalanceamento")
#: Regra anterior (``squeeze.stop_scope = "book"``): o stop escala para o livro inteiro (kill
#: switch ⇒ só redução de risco; no rebalanceamento seguinte a carteira é reconstruída no caminho
#: ``reduzir-risco``, com gross × 0,5) e o corte de 50% do short não é automático.
SQUEEZE_STOP_ACTION_LIVRO = (
    "ligar o kill switch: o livro inteiro fica só-redução e, no próximo rebalanceamento, o código "
    "reconstrói a carteira com gross × 0,5 (caminho reduzir-risco); o corte de 50% deste short "
    "não é automático — revisão humana do nome")
#: Código do gatilho de escalada (HARD) da regra por nome.
SQUEEZE_ESCALATION_CODE = "stop_squeeze_escalada"


def _per_name(cfg: FundConfig) -> bool:
    return cfg.squeeze.stop_scope == "name"


def _squeeze_triggers(cfg: FundConfig, stops: list[dict], origem: str, *,
                      intradiario: bool = False,
                      cortados: dict[str, list[float]] | None = None) -> list[Trigger]:
    """Um gatilho por stop acionado: HARD com a regra do livro inteiro (legado); SOFT com a regra
    por nome (o corte é do código; a escalada vem de :func:`_squeeze_escalation`). ``cortados``:
    ticker → preços médios de entrada dos episódios cujo corte já foi feito."""
    out: list[Trigger] = []
    sq = cfg.squeeze
    for s in stops:
        if not _per_name(cfg):
            nivel, acao = "HARD", SQUEEZE_STOP_ACTION_LIVRO
            efeito = ("mandato pede cortar 50% do short; o código escala para o livro inteiro "
                      "(só redução, gross × 0,5 no rebalanceamento)")
        elif intradiario:
            nivel, acao = "SOFT", SQUEEZE_STOP_ACTION_INTRADIARIO
            efeito = ("o corte à metade e o veto de compra valem se o stop se confirmar num "
                      "fechamento")
        elif _num(s.get("preco_medio_entrada")) is not None and _same_entry(
                float(s["preco_medio_entrada"]), (cortados or {}).get(str(s["ticker"]), ())):
            nivel, acao = "SOFT", SQUEEZE_STOP_ACTION_CORTADO
            efeito = ("corte à metade já feito neste episódio; compra do emissor vedada até "
                      "revisão humana")
        else:
            nivel, acao = "SOFT", SQUEEZE_STOP_ACTION
            efeito = ("o código corta o short à metade no próximo rebalanceamento e veda a "
                      "compra do emissor até revisão humana")
        if s["stop_posicao"]:
            out.append(Trigger(
                nivel, f"stop_squeeze_posicao_{s['ticker']}",
                f"STOP DE SQUEEZE {origem}: short {s['ticker']} ({s['emissor']}) perde "
                f"{fmt_pct(s['perda_desde_entrada'])} desde a entrada (limite "
                f"{fmt_pct(sq.stop_short_position_loss)}) — {efeito}", acao))
        if s["stop_nav"]:
            out.append(Trigger(
                nivel, f"stop_squeeze_nav_{s['ticker']}",
                f"STOP DE SQUEEZE {origem}: short {s['ticker']} ({s['emissor']}) perde "
                f"{fmt_pct(s['perda_pct_nav'])} do NAV desde a entrada (limite "
                f"{fmt_pct(sq.stop_short_nav_loss)}) — {efeito}", acao))
    return out


def _short_rows(rec: DailyRecord) -> list[dict]:
    return [{"ticker": p.ticker, "emissor": p.issuer_id, "acoes": p.shares,
             "preco_local": p.price_local, "fx": _fx_from_position(p)}
            for p in rec.positions if p.market_value_usd < 0]


def squeeze_stop_hits(cfg: FundConfig, history_asc: list[DailyRecord]
                      ) -> dict[str, list[tuple[date, float]]]:
    """Fechamentos (dentro da janela de escalada) em que cada emissor short estava em stop de
    squeeze, com o preço médio de entrada do short acionado — a mesma regra do monitor e do
    fechamento diário. ``history_asc``: registros do mais antigo para o mais recente."""
    n = cfg.squeeze.stop_escalation_sessions
    out: dict[str, list[tuple[date, float]]] = {}
    for k in range(max(0, len(history_asc) - n), len(history_asc)):
        rec = history_asc[k]
        before = list(reversed(history_asc[:k]))
        for s in squeeze_stop_checks(cfg, _short_rows(rec), before, rec.nav_end_usd):
            if s["stop_posicao"] or s["stop_nav"]:
                out.setdefault(str(s["emissor"]), []).append(
                    (rec.date, float(s["preco_medio_entrada"])))
    return out


def squeeze_stop_history(cfg: FundConfig, history_asc: list[DailyRecord]) -> dict[str, list[date]]:
    """Datas de fechamento (dentro da janela de escalada) em que cada emissor short estava em stop
    de squeeze (:func:`squeeze_stop_hits` sem o preço de entrada)."""
    return {i: [d for d, _ in hits] for i, hits in squeeze_stop_hits(cfg, history_asc).items()}


def _squeeze_escalation(cfg: FundConfig, history_asc: list[DailyRecord], live_stops: list[dict],
                        today: date | None) -> tuple[Trigger | None, dict]:
    """Escalada da regra por nome ao kill switch do livro (:func:`risk.limites.
    escalar_para_kill_switch`): shorts distintos em stop nos últimos pregões fechados e, com
    cotações do momento, no pregão de hoje. ``info["entradas"]``: emissor → preços médios de
    entrada dos shorts em stop na janela (o episódio de cada short, usado na revisão humana)."""
    from ..risk.limites import escalar_para_kill_switch

    sq = cfg.squeeze
    hits = squeeze_stop_hits(cfg, history_asc)
    sessions = [r.date for r in history_asc]
    live_hit = [s for s in live_stops if s.get("stop_posicao") or s.get("stop_nav")]
    if today is not None and live_hit:
        if not sessions or sessions[-1] < today:
            sessions = [*sessions, today]
        for s in live_hit:
            hits.setdefault(str(s["emissor"]), []).append(
                (today, float(s["preco_medio_entrada"])))
    dates = {i: [d for d, _ in hs] for i, hs in hits.items()}
    janela = sorted(sessions)[-sq.stop_escalation_sessions:]
    em_stop = sorted(i for i, ds in dates.items() if any(d in janela for d in ds))
    entradas = {i: sorted({a for d, a in hits[i] if d in janela}) for i in em_stop}
    info = {"emissores_em_stop": em_stop, "entradas": entradas,
            "pregoes_na_janela": len(janela), "limite": sq.stop_escalation_count,
            "janela_pregoes": sq.stop_escalation_sessions, "escalada": False}
    if not escalar_para_kill_switch(dates, sessions, cfg):
        return None, info
    info["escalada"] = True
    motivo = (f"ESCALADA DE SQUEEZE: {len(em_stop)} shorts distintos em stop nos últimos "
              f"{len(janela)} pregões ({', '.join(em_stop)}; limite "
              f"{sq.stop_escalation_count} em {sq.stop_escalation_sessions}) — assinatura de "
              "desmonte coletivo: o livro inteiro passa a só-redução")
    return Trigger("HARD", SQUEEZE_ESCALATION_CODE, motivo, SQUEEZE_ESCALATION_ACTION), info


# ----------------------------------------------------------------------------- revisão humana

_DRAWDOWN_CODE = re.compile(r"^drawdown_(soft_stop|hard_stop|stop_out)_")
_SQUEEZE_CODE = re.compile(r"^stop_squeeze_(?:posicao|nav)_(.+)$")


def _squeeze_codes(stops: Iterable[dict]) -> dict[str, float]:
    """Código do gatilho de squeeze → preço médio de entrada do short acionado."""
    out: dict[str, float] = {}
    for s in stops:
        avg = _num(s.get("preco_medio_entrada"))
        if avg is None:
            continue
        if s.get("stop_posicao"):
            out[f"stop_squeeze_posicao_{s['ticker']}"] = avg
        if s.get("stop_nav"):
            out[f"stop_squeeze_nav_{s['ticker']}"] = avg
    return out


def _parse_ts(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo is not None else None


def _reported_before(risk_root: Path, base_date: date, off_ts: datetime
                     ) -> tuple[int, dict[str, set[float]], dict[str, set[float]]]:
    """Gatilhos que os relatórios de risco já mostravam ao humano antes do desligamento.

    Considera só relatórios calculados sobre o mesmo registro-base (``base.registro``) e gerados até
    ``off_ts``: os HARD e os já rebaixados por revisão anterior. Devolve o pior estágio da escada de
    drawdown visto, os códigos de squeeze com o preço médio de entrada de cada short e, de uma
    escalada de squeeze já mostrada, os shorts em stop (emissor → preços médios de entrada).
    """
    rank = 0
    codes: dict[str, set[float]] = {}
    escalated: dict[str, set[float]] = {}
    if not risk_root.is_dir():
        return rank, codes, escalated
    for folder in sorted(p for p in risk_root.iterdir() if p.is_dir()):
        try:
            if date.fromisoformat(folder.name) < base_date:
                continue
        except ValueError:
            continue
        for path in sorted(folder.glob("risco_*.json")):
            try:
                res = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(res, dict) or (res.get("base") or {}).get("registro") != str(base_date):
                continue
            gen = _parse_ts(res.get("gerado_em"))
            if gen is None or gen > off_ts:
                continue
            downgraded = set((res.get("revisao_humana") or {}).get("codigos_rebaixados") or [])
            sq = res.get("squeeze") or {}
            entries = _squeeze_codes([*(sq.get("stops_fechamento") or []),
                                      *(sq.get("stops_intradiario") or [])])
            for t in res.get("gatilhos") or []:
                code = str(t.get("codigo", ""))
                if t.get("nivel") != "HARD" and code not in downgraded:
                    continue
                m = _DRAWDOWN_CODE.match(code)
                if m:
                    rank = max(rank, STAGE_RANK[m.group(1)])
                elif code == SQUEEZE_ESCALATION_CODE:
                    ent = (sq.get("escalada") or {}).get("entradas") or {}
                    for iid, avgs in (ent.items() if isinstance(ent, dict) else ()):
                        vals = {v for v in (_num(x) for x in (avgs or [])) if v is not None}
                        escalated.setdefault(str(iid), set()).update(vals)
                elif code in entries:
                    codes.setdefault(code, set()).add(entries[code])
    return rank, codes, escalated


def _human_review(rt: Runtime, cfg: FundConfig, history: list[DailyRecord]) -> dict | None:
    """O que um humano já revisou ao desligar o kill switch pela última vez (``None`` se nunca).

    Base: o último registro diário já gravado na trilha quando veio o ``KILL_SWITCH_OFF`` (ordem
    da trilha de auditoria encadeada). Revisado = estágio da escada de drawdown, gatilhos de
    velocidade de perda e stops de squeeze desse registro, mais os gatilhos HARD dos relatórios de
    risco sobre esse mesmo registro gerados até o desligamento. Só uma piora religa o kill switch:
    estágio pior da escada, velocidade de perda num registro posterior ou short novo no stop (ou
    o mesmo short com outro preço médio de entrada, isto é, risco novo — vale também para a
    escalada de squeeze, revisada por short e preço médio de entrada, nunca só pelo emissor).
    """
    path = rt.book_root / "audit_log.jsonl"
    if not path.is_file():
        return None
    try:
        events = AuditLog(path).events()
    except (OSError, ValueError):
        return None
    offs = [i for i, e in enumerate(events) if e.event_type == "KILL_SWITCH_OFF"]
    if not offs:
        return None
    off = events[offs[-1]]
    known = {e.payload_hash for e in events[:offs[-1]] if e.event_type == DAILY_RECORD_EVENT}
    base = None
    for r in history:  # do mais antigo para o mais recente
        if sha256_obj(r.record_hash) in known:
            base = r
    review: dict[str, Any] = {
        "desligado_em": off.ts, "por": off.actor,
        "registro_base": base.date if base else None,
        "estagio_revisado": "normal", "codigos_revisados": [], "codigos_rebaixados": [],
    }
    if base is None:
        return review
    rank = STAGE_RANK.get(drawdown_stage(base.risk.drawdown, cfg) or "", 0)
    shorts = [{"ticker": p.ticker, "emissor": p.issuer_id, "acoes": p.shares,
               "preco_local": p.price_local, "fx": _fx_from_position(p)}
              for p in base.positions if p.market_value_usd < 0]
    before = [r for r in reversed(history) if r.date < base.date]
    checks = squeeze_stop_checks(cfg, shorts, before, base.nav_end_usd)
    codes = {k: {v} for k, v in _squeeze_codes(checks).items()}
    rep_rank, rep_codes, rep_escalated = _reported_before(rt.reports_root / RISK_DIRNAME,
                                                          base.date, off.ts)
    for k, v in rep_codes.items():
        codes.setdefault(k, set()).update(v)
    pairs: dict[str, set[float]] = {}
    for c in checks:
        if c["stop_posicao"] or c["stop_nav"]:
            pairs.setdefault(str(c["emissor"]), set()).add(float(c["preco_medio_entrada"]))
    if _per_name(cfg):
        upto = [r for r in history if r.date <= base.date]
        for iid, hs in squeeze_stop_hits(cfg, upto).items():
            pairs.setdefault(iid, set()).update(a for _, a in hs)
    for iid, avgs in rep_escalated.items():
        pairs.setdefault(iid, set()).update(avgs)
    review["_shorts_em_stop"] = pairs
    rank = max(rank, rep_rank)
    review["estagio_revisado"] = next(s for s, r in STAGE_RANK.items() if r == rank)
    review["codigos_revisados"] = sorted(codes)
    review["_entradas"] = codes
    return review


#: Gatilhos HARD calculados só sobre o registro de fechamento (velocidade de perda): revisados
#: quando o registro não é posterior ao registro-base da revisão humana.
_REGISTRO_HARD_CODES = frozenset({"perda_diaria_extrema"})


def _same_entry(a: float, xs: Iterable[float]) -> bool:
    return any(math.isclose(a, x, rel_tol=1e-9, abs_tol=1e-12) for x in xs)


def _apply_review(triggers: list[Trigger], review: dict | None, entries: dict[str, float],
                  escalated: dict[str, Iterable[float]] | None = None,
                  registro: date | None = None) -> list[Trigger]:
    """Rebaixa a SOFT os gatilhos HARD que o humano já revisou e que não pioraram: a escalada de
    squeeze só volta a ser HARD com um short novo em stop (outro emissor ou outro preço médio de
    entrada); a velocidade de perda, só num registro de fechamento posterior ao registro-base
    (``registro`` é a data do registro sobre o qual os gatilhos de velocidade foram calculados)."""
    if review is None:
        return triggers
    rank = STAGE_RANK[review["estagio_revisado"]]
    seen: dict[str, set[float]] = review.get("_entradas", {})
    when = review["desligado_em"]
    when_txt = when.isoformat(timespec="minutes") if isinstance(when, datetime) else str(when)
    out: list[Trigger] = []
    for t in triggers:
        reviewed = False
        if t.nivel == "HARD":
            m = _DRAWDOWN_CODE.match(t.codigo)
            if m:
                reviewed = STAGE_RANK[m.group(1)] <= rank
            elif t.codigo == SQUEEZE_ESCALATION_CODE:
                seen_pairs: dict[str, set[float]] = review.get("_shorts_em_stop", {})
                cur = {str(i): list(a) for i, a in (escalated or {}).items()}
                reviewed = bool(cur) and all(
                    avgs and all(_same_entry(float(a), seen_pairs.get(i, ())) for a in avgs)
                    for i, avgs in cur.items())
            elif t.codigo in _REGISTRO_HARD_CODES:
                base = review.get("registro_base")
                reviewed = base is not None and registro is not None and registro <= base
            elif _SQUEEZE_CODE.match(t.codigo):
                avg = entries.get(t.codigo)
                reviewed = avg is not None and _same_entry(avg, seen.get(t.codigo, ()))
        if not reviewed:
            out.append(t)
            continue
        review["codigos_rebaixados"].append(t.codigo)
        out.append(Trigger(
            "SOFT", t.codigo,
            f"{t.motivo} (já revisado por humano: kill switch desligado em {when_txt} por "
            f"{review['por']}; só uma piora religa)",
            "condição já revisada por humano; o código aplica a escada e os limites no próximo "
            "rebalanceamento"))
    return out


def _risk_block(rec: DailyRecord, cfg: FundConfig) -> tuple[dict, list[Trigger]]:
    rk = rec.risk
    lim = cfg.risk
    has_positions = any(p.market_value_usd != 0 for p in rec.positions)
    vol = _num(rk.ex_ante_vol)
    in_band = None if vol is None else bool(lim.vol_band_min <= vol <= lim.vol_band_max)
    block = {
        "vol_ex_ante": vol, "vol_alvo": lim.vol_target_annual,
        "banda_vol": [lim.vol_band_min, lim.vol_band_max], "dentro_da_banda": in_band,
        "beta": _num(rk.beta), "beta_limite": lim.beta_max_abs,
        "net": rk.net, "net_limite": lim.net_exposure_max_abs,
        "gross": rk.gross, "gross_limites": [lim.gross_min, lim.gross_max],
        "long": rk.long_exposure, "short": rk.short_exposure,
        "n_long": rk.n_long, "n_short": rk.n_short,
        "var_1d_99": _num(rk.var_1d_99), "var_limite": lim.var_1d_max,
        "es_1d_99": _num(rk.es_1d_99), "es_limite": lim.es_1d_max,
        "vol_realizada_21d": _num(rk.realized_vol_21d),
        "vol_realizada_63d": _num(rk.realized_vol_63d),
    }
    t: list[Trigger] = []
    band = f"{fmt_pct(lim.vol_band_min)}–{fmt_pct(lim.vol_band_max)}"
    if has_positions and vol is None:
        t.append(Trigger("INFO", "vol_indisponivel",
                         "Vol ex-ante indisponível no registro: banda não verificada",
                         "conferir o modelo de risco no próximo fechamento"))
    elif vol is not None and vol > lim.vol_band_max:
        t.append(Trigger("SOFT", "vol_acima_da_banda",
                         f"Vol ex-ante {fmt_pct(vol)} acima da banda ({band})",
                         "reduzir risco no próximo rebalanceamento (o otimizador aplica o teto)"))
    elif has_positions and vol is not None and vol < lim.vol_band_min:
        t.append(Trigger("INFO", "vol_abaixo_da_banda",
                         f"Vol ex-ante {fmt_pct(vol)} abaixo da banda ({band})",
                         "subutilização do orçamento de risco; nenhuma ação intradiária"))
    if abs(rk.net) > lim.net_exposure_max_abs + 1e-12:
        t.append(Trigger("SOFT", "net_fora_do_limite",
                         f"Exposição líquida {fmt_pct(rk.net, signed=True)} fora do limite "
                         f"±{fmt_pct(lim.net_exposure_max_abs)} (net neutral)",
                         "reequilibrar no próximo rebalanceamento"))
    beta = _num(rk.beta)
    if beta is not None and abs(beta) > lim.beta_max_abs + 1e-12:
        t.append(Trigger("SOFT", "beta_fora_do_limite",
                         f"Beta previsto {fmt_num(beta, 3, signed=True)} fora do limite "
                         f"±{fmt_num(lim.beta_max_abs, 3)}",
                         "reequilibrar no próximo rebalanceamento"))
    if has_positions and rk.gross > lim.gross_max + 1e-12:
        t.append(Trigger("SOFT", "gross_acima_do_limite",
                         f"Gross {fmt_pct(rk.gross)} acima do máximo {fmt_pct(lim.gross_max)}",
                         "reduzir o gross no próximo rebalanceamento"))
    elif has_positions and rk.gross < lim.gross_min - 1e-12:
        t.append(Trigger("INFO", "gross_abaixo_do_minimo",
                         f"Gross {fmt_pct(rk.gross)} abaixo do mínimo {fmt_pct(lim.gross_min)}",
                         "nenhuma ação intradiária (pode refletir a escada de drawdown)"))
    var = _num(rk.var_1d_99)
    if var is not None and var > lim.var_1d_max + 1e-12:
        t.append(Trigger("SOFT", "var_acima_do_limite",
                         f"VaR 99% 1d {fmt_pct(var)} acima do limite {fmt_pct(lim.var_1d_max)}",
                         "reduzir risco no próximo rebalanceamento"))
    es = _num(rk.es_1d_99)
    if es is not None and es > lim.es_1d_max + 1e-12:
        t.append(Trigger("SOFT", "es_acima_do_limite",
                         f"ES 99% 1d {fmt_pct(es)} acima do limite {fmt_pct(lim.es_1d_max)}",
                         "reduzir risco no próximo rebalanceamento"))
    return block, t


def _exposures_block(rec: DailyRecord) -> tuple[list[dict], list[dict], list[Trigger]]:
    rows, over, t = [], [], []
    label = {"country": "país", "sector": "setor", "style": "estilo", "currency": "moeda",
             "market": "mercado"}
    for e in rec.risk.exposures:
        exceeds = (e.limit is not None and e.group in ("country", "sector", "style")
                   and abs(e.net) > e.limit + 1e-9)
        row = {"grupo": e.group, "nome": e.name, "net": e.net, "gross": e.gross,
               "limite": e.limit, "excede": bool(exceeds)}
        rows.append(row)
        if exceeds:
            over.append(row)
            val = (fmt_num(e.net, 3, signed=True) if e.group == "style"
                   else fmt_pct(e.net, signed=True))
            lim = fmt_num(e.limit, 3) if e.group == "style" else fmt_pct(e.limit)
            t.append(Trigger("SOFT", f"exposicao_{e.group}_{e.name}",
                             f"Exposição líquida de {label.get(e.group, e.group)} {e.name} "
                             f"{val} acima do limite ±{lim}",
                             "neutralizar no próximo rebalanceamento"))
    return rows, over, t


def _liquidity_block(rec: DailyRecord, proposal: Proposal | None, cfg: FundConfig
                     ) -> tuple[dict, list[Trigger]]:
    liq = cfg.liquidity
    adtv = {p.issuer_id: _num(p.adtv_usd) for p in (proposal.positions if proposal else [])}
    mv: dict[str, float] = {}
    ticker: dict[str, str] = {}
    for p in rec.positions:
        if p.market_value_usd == 0:
            continue
        mv[p.issuer_id] = mv.get(p.issuer_id, 0.0) + p.market_value_usd
        ticker.setdefault(p.issuer_id, p.ticker)
    closes_mode = cfg.execution is not None
    # Com a execução no fechamento, a unidade é o FECHAMENTO: capacidade estrutural por
    # fechamento implícita na decisão vigente (nocional-alvo / fechamentos para zerar).
    cap: dict[str, float] = {}
    if closes_mode and proposal is not None:
        for p in proposal.positions:
            d, n = _num(p.days_to_liquidate), _num(p.notional_usd)
            if d is not None and d > 0 and n is not None and n != 0:
                cap[p.issuer_id] = cap.get(p.issuer_id, 0.0) + abs(n) / d
    over, missing = [], []
    for iid, v in sorted(mv.items()):
        long_side = v > 0
        limit = liq.max_days_to_liquidate_long if long_side else liq.max_days_to_liquidate_short
        if closes_mode:
            c = cap.get(iid)
            if c is None or c <= 0:
                missing.append(iid)
                continue
            days = abs(v) / c
        else:
            a = adtv.get(iid)
            rate = liq.participation_rate if long_side else liq.short_participation_rate
            if a is None or a <= 0:
                missing.append(iid)
                continue
            days = abs(v) / (rate * a)
        if days > limit + 1e-9:
            over.append({"emissor": iid, "ticker": ticker[iid],
                         "lado": "LONG" if long_side else "SHORT", "dias": days,
                         "limite": limit})
    unidade = "fechamentos" if closes_mode else "dias"
    block = {"max_dias_para_liquidar": _num(rec.risk.max_days_to_liquidate),
             "pct_gross_liquido_1d": _num(rec.risk.pct_gross_liquid_1d),
             "unidade": unidade,
             "posicoes_acima_do_limite": over, "sem_adtv": missing,
             "fonte_adtv": ("capacidade de fechamento gravada na decisão da semana vigente"
                            if closes_mode else "ADTV gravado na decisão da semana vigente")
             if proposal else None}
    t: list[Trigger] = []
    fmt = fmt_closes if closes_mode else fmt_days
    if over:
        names = ", ".join(f"{o['emissor']} ({fmt(o['dias'])} > {fmt(o['limite'])})"
                          for o in over)
        t.append(Trigger("SOFT", "liquidez_acima_do_limite",
                         _clip(f"Posições acima do limite de {unidade} para liquidar: {names}"),
                         "reduzir no próximo rebalanceamento"))
    if missing:
        t.append(Trigger("INFO", "liquidez_sem_adtv",
                         _clip("ADTV indisponível (liquidez desconhecida, nunca tratada como "
                               f"imediata): {', '.join(missing)}"),
                         "conferir a liquidez no próximo fechamento"))
    return block, t


def _squeeze_high(rec: DailyRecord, proposal: Proposal | None) -> tuple[list[dict], list[Trigger]]:
    held_short = {p.issuer_id: p.ticker for p in rec.positions if p.market_value_usd < 0}
    rows = []
    for p in (proposal.positions if proposal else []):
        if p.side == Side.SHORT and p.squeeze_bucket == "HIGH" and p.issuer_id in held_short:
            rows.append({"emissor": p.issuer_id, "ticker": held_short[p.issuer_id],
                         "balde_na_decisao": p.squeeze_bucket,
                         "escore_na_decisao": _num(p.squeeze_score)})
    t: list[Trigger] = []
    n_rec = int(rec.risk.squeeze_high_shorts or 0)
    if rows or n_rec:
        names = ", ".join(r["ticker"] for r in rows)
        t.append(Trigger("SOFT", "squeeze_high",
                         _clip(f"Shorts com risco de squeeze HIGH: {n_rec} no último fechamento"
                               + (f"; HIGH já na decisão: {names}" if names else "")),
                         "reavaliar/reduzir no próximo rebalanceamento"))
    return rows, t


def _live_block(rec: DailyRecord, quotes: pd.DataFrame, session: date, cfg: FundConfig,
                peak_nav: float) -> dict:
    from ..data.intraday import fresh_quotes

    fresh, stale = fresh_quotes(quotes, session, tz=cfg.fund.timezone)
    lines = fresh[fresh["kind"] == "line"].dropna(subset=["price"])
    line_px = {str(s): float(v) for s, v in zip(lines["symbol"], lines["price"], strict=True)
               if _num(v) is not None and float(v) > 0}
    line_time = {str(s): t for s, t in zip(lines["symbol"], lines["time"], strict=True)}
    fxq = fresh[fresh["kind"] == "fx"].dropna(subset=["price"])
    fx_now = {str(s): float(v) for s, v in zip(fxq["symbol"], fxq["price"], strict=True)
              if _num(v) is not None and float(v) > 0}
    fx_now["USD"] = 1.0
    stale_set = set(stale)
    rows, missing = [], []
    gross_all = covered = 0.0
    pnl_total = 0.0
    mv_live_by_issuer: dict[str, float] = {}
    for p in rec.positions:
        mv0 = p.market_value_usd
        if mv0 == 0:
            continue
        gross_all += abs(mv0)
        px0 = _num(p.price_local)
        px1 = line_px.get(p.ticker)
        fx0 = _fx_from_position(p)
        fx1 = fx_now.get(p.currency)
        reason = None
        if px1 is None:
            reason = "sem negócio hoje" if p.ticker in stale_set else "cotação indisponível"
        elif px0 is None or px0 <= 0:
            reason = "preço de fechamento ausente no registro"
        elif fx0 is None:
            reason = "câmbio do fechamento ausente no registro"
        elif fx1 is None:
            reason = f"câmbio {p.currency} do momento indisponível"
        if reason is not None:
            missing.append({"ticker": p.ticker, "emissor": p.issuer_id, "lado": _side(p),
                            "motivo": reason})
            mv_live_by_issuer[p.issuer_id] = mv_live_by_issuer.get(p.issuer_id, 0.0) + mv0
            continue
        ret_local = px1 / px0 - 1.0
        ret_usd = (px1 * fx1) / (px0 * fx0) - 1.0
        pnl = mv0 * ret_usd
        covered += abs(mv0)
        pnl_total += pnl
        mv_live_by_issuer[p.issuer_id] = mv_live_by_issuer.get(p.issuer_id, 0.0) + mv0 + pnl
        rows.append({"ticker": p.ticker, "emissor": p.issuer_id, "lado": _side(p),
                     "moeda": p.currency, "preco_fechamento": px0, "preco_agora": px1,
                     "horario_cotacao": line_time.get(p.ticker), "ret_local": ret_local,
                     "ret_usd": ret_usd, "pnl_usd": pnl, "contribuicao": pnl / rec.nav_end_usd,
                     "acoes": _num(p.shares), "fx_agora": fx1})
    coverage = covered / gross_all if gross_all > 0 else None
    nav_live = rec.nav_end_usd + pnl_total
    peak = max(peak_nav, nav_live)
    dd_live = nav_live / peak - 1.0 if peak > 0 else None
    w = (pd.Series(mv_live_by_issuer, dtype=float) / nav_live if nav_live > 0
         else pd.Series(dtype=float))
    top = sorted(rows, key=lambda r: -abs(r["pnl_usd"]))[:TOP_CONTRIBUTORS]
    return {
        "pregao": session, "cotacoes_validas": len(line_px),
        "cotacoes_sem_negocio_hoje": sorted(stale), "cobertura_gross": coverage,
        "parcial": bool(missing), "pnl_usd": pnl_total if rows else None,
        "pnl_pct_nav": (pnl_total / rec.nav_end_usd) if rows else None,
        "nav_estimado_usd": nav_live if rows else None,
        "drawdown_estimado": dd_live if rows else None,
        "estagio_estimado": drawdown_stage(dd_live, cfg) if rows else None,
        "net_estimado": float(w.sum()) if rows and not w.empty else None,
        "gross_estimado": float(w.abs().sum()) if rows and not w.empty else None,
        "maiores_contribuicoes": top, "posicoes": rows, "sem_cotacao": missing,
        "fx_agora": {k: v for k, v in sorted(fx_now.items()) if k != "USD"},
    }


# ----------------------------------------------------------------------------- principal


def _kill_switch_info(rt: Runtime) -> dict:
    from .runtime import KILL_SWITCH_FILE

    path = rt.book_root / KILL_SWITCH_FILE
    if not path.exists():
        return {"ativo": False}
    info: dict[str, Any] = {"ativo": True}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        info.update({"motivo": raw.get("reason"), "por": raw.get("by"), "em": raw.get("at")})
    except (OSError, ValueError, AttributeError):
        info["motivo"] = "arquivo KILL_SWITCH presente (conteúdo ilegível)"
    return info


def _pending_decision(rt: Runtime, as_of: date) -> dict | None:
    """Decisão gravada e ainda não efetivada (executa no fechamento, MOC): o dia de montagem
    decidido mais recente até ``as_of``, se ainda sem efetivação no livro."""
    b = rt.book
    try:
        decided = [w for w in b.list_weeks() if w <= as_of and b.list_decisions(w)]
    except (ValueError, OSError):
        decided = []
    week = decided[-1] if decided else chave_da_semana(as_of, rt.cfg)
    if week is None or week > as_of:
        return None
    try:
        decisions = b.list_decisions(week)
        if not decisions or b.load_booked(week) is not None:
            return None
        version = max(decisions)
        dec = decisions[version]
        prop = b.load_proposal(week, version)
    except (ValueError, OSError) as exc:
        return {"semana": week, "erro": _clip(str(exc), 300)}
    from .daily import executable_in

    out: dict[str, Any] = {"semana": week, "decidida_em": dec.decided_at,
                           "execucao": f"fechamento de {week} (MOC) pela rotina diária",
                           "executavel_no_pregao": executable_in(week, as_of, rt.cfg)}
    if prop is not None:
        r = prop.risk
        out.update({"vol_ex_ante": r.ex_ante_vol, "beta": r.beta, "gross": r.gross,
                    "net": r.net, "n_long": r.n_long, "n_short": r.n_short,
                    "falhas_hard": [c.check_id for c in prop.hard_failures],
                    "falhas_soft": [c.check_id for c in prop.soft_failures]})
    return out


def _velocity_triggers(rt: Runtime, history: list[DailyRecord],
                       limitations: list[str]) -> list[Trigger]:
    """Gatilhos de velocidade de perda e de evento societário (:mod:`cdp.risk.gatilhos`), ativos
    com a metodologia de construção vigente (``optimizer.metodologia_ativa``: o kill switch é
    só-redução, então um HARD aqui reduz risco). Legado: nenhum gatilho novo."""
    try:
        from ..portfolio.optimizer import metodologia_ativa
        from ..risk import gatilhos
    except ImportError:  # pragma: no cover - módulo ausente nesta versão
        return []
    if not metodologia_ativa(rt.cfg) or not history:
        return []
    out: list[Trigger] = []
    rows = gatilhos.loss_velocity(list(reversed(history))[:gatilhos.WINDOW_5D + 1], rt.cfg)
    rec = history[-1]
    try:
        md = rt.store.load(as_of=rec.date)
    except Exception as exc:  # noqa: BLE001 - sem base de mercado: o detector não roda
        md = None
        limitations.append(f"Detector de evento societário sem base de mercado: "
                           f"{_clip(str(exc), 160)}")
    rows += gatilhos.price_jumps(rec, md)
    for r in rows:
        nivel = str(r.get("nivel", "INFO"))
        if nivel not in ("HARD", "SOFT", "INFO"):
            continue
        acao = str(r.get("acao") or "")
        if acao.startswith(KILL_SWITCH_PREFIX):
            acao = acao[len(KILL_SWITCH_PREFIX):]
        out.append(Trigger(nivel, str(r.get("codigo")), str(r.get("mensagem", "")),  # type: ignore[arg-type]
                           acao))
    return out


def idio_monitor(rt: Runtime, history_asc: list[DailyRecord], limitations: list[str]
                 ) -> tuple[dict | None, list[Trigger]]:
    """Fatia idiossincrática do livro por três medidas (:func:`cdp.risk.idio.serie_idio`), no
    último fechamento: ex-ante diária (vol fatorial e específica do registro, com κ_F), realizada
    em 63 pregões (x-sigma-rho do P&L específico) e sem modelo (1 − R² ajustado dos retornos do
    fundo contra ETFs de país e commodities). Só com a metodologia de construção vigente; ausente
    fica ``None`` (nunca zero). Ex-ante abaixo do piso do mandato ⇒ SOFT (o piso é HARD na
    decisão); realizada abaixo do piso ⇒ INFO (amostra curta e ruidosa); sem modelo ⇒ INFO só
    abaixo do piso menos a banda de amostragem unilateral de 95% (sob a nula)."""
    from ..portfolio.optimizer import metodologia_ativa
    from ..risk.idio import JANELA_REALIZADA, Z_BANDA_SEM_MODELO, serie_idio

    cfg = rt.cfg
    if not metodologia_ativa(cfg) or not history_asc:
        return None, []
    recs = history_asc[-JANELA_REALIZADA:]
    try:
        md = rt.store.load(as_of=recs[-1].date)
    except Exception as exc:  # noqa: BLE001 - sem base de mercado: só a medida ex-ante
        md = None
        limitations.append("Fatia idiossincrática sem modelo indisponível (base de mercado: "
                           f"{_clip(str(exc), 160)}).")
    serie = serie_idio(recs, md, cfg)
    if not serie["datas"]:
        return None, []
    goal, floor = cfg.risk.idio_share_goal, cfg.risk.idio_share_floor
    block = {"data": serie["datas"][-1], "ex_ante": serie["ex_ante"][-1],
             "realizada_63d": serie["realizada_63d"][-1],
             "sem_modelo_63d": serie["sem_modelo_63d"][-1],
             "sem_modelo_banda": serie["sem_modelo_banda"][-1],
             "sem_modelo_obs": serie["sem_modelo_obs"][-1], "meta": goal, "piso": floor,
             "kappa_f": serie["kappa_f"], "janela_pregoes": serie["janela"],
             "registros": len(recs), "regressores": serie["regressores"]}
    t: list[Trigger] = []
    ex = _num(block["ex_ante"])
    if floor is not None and ex is not None and ex < floor - 1e-9:
        t.append(Trigger("SOFT", "idio_ex_ante_abaixo_do_piso",
                         f"Fatia idiossincrática ex-ante {fmt_pct(ex, 1)} abaixo do piso "
                         f"{fmt_pct(floor, 0)} (κ_F {fmt_num(_num(block['kappa_f']), 2)})",
                         "reduzir o risco fatorial no próximo rebalanceamento (o piso é HARD "
                         "na decisão)"))
    v = _num(block["realizada_63d"])
    if floor is not None and v is not None and v < floor - 1e-9:
        t.append(Trigger("INFO", "idio_realizada_63d_abaixo_do_piso",
                         f"Fatia idiossincrática realizada (63 pregões) {fmt_pct(v, 1)} abaixo "
                         f"do piso {fmt_pct(floor, 0)}",
                         "acompanhar: medida realizada com amostra curta; a decisão usa o "
                         "modelo ex-ante"))
    v, band = _num(block["sem_modelo_63d"]), _num(block["sem_modelo_banda"])
    if floor is not None and v is not None and band is not None \
            and v < floor - Z_BANDA_SEM_MODELO * band - 1e-9:
        t.append(Trigger("INFO", "idio_sem_modelo_63d_abaixo_do_piso",
                         f"Fatia idiossincrática sem modelo (1 − R² ajustado, "
                         f"{block['sem_modelo_obs']} pregões) {fmt_pct(v, 1)} abaixo do piso "
                         f"{fmt_pct(floor, 0)} além da margem de amostragem unilateral de 95% "
                         f"({fmt_pct(Z_BANDA_SEM_MODELO * band, 1)})",
                         "revisar o modelo de risco: exposição a ETFs de país e commodities que "
                         "o modelo ex-ante não capta; a decisão usa o modelo ex-ante"))
    return block, t


def _live_proposal(rt: Runtime, rec: DailyRecord) -> tuple[Proposal | None, list[str]]:
    notes: list[str] = []
    if rec.live_book_week is None:
        return None, notes
    b = rt.book
    try:
        entry = b.load_booked(rec.live_book_week)
    except ValueError as exc:
        notes.append(f"Livro vigente não confere com a trilha: {_clip(str(exc), 300)}")
        return None, notes
    if entry is None:
        notes.append(f"Semana vigente {rec.live_book_week} sem booked.json no livro.")
        return None, notes
    for p in b.list_proposals(entry.week):
        if p.proposal_id == entry.proposal_id:
            return p, notes
    notes.append(f"Proposta {entry.proposal_id} da semana vigente não encontrada.")
    return None, notes


def run_risk_monitor(rt: Runtime, *, as_of: date | None = None, live: bool = False,
                     fetch_quotes: QuoteFetcher | None = None,
                     now: datetime | None = None) -> dict:
    """Relatório de risco determinístico (ver docstring do módulo). Não grava nada."""
    cfg = rt.cfg
    tz = ZoneInfo(cfg.fund.timezone)
    local = (now if now is not None else rt.now()).astimezone(tz)
    as_of = as_of or local.date()
    ks = _kill_switch_info(rt)
    out: dict[str, Any] = {
        "fundo": cfg.fund.name, "gerado_em": local, "data": as_of,
        "modo": "intradiário (cotações ao vivo)" if live else "último fechamento",
        "kill_switch": ks, "decisao_pendente": _pending_decision(rt, as_of),
    }
    triggers: list[Trigger] = []
    limitations: list[str] = []
    if rt.pre_inicio(as_of):
        inicio = cfg.fund.inception_date
        out.update({"status": PRE_INICIO, "aviso": "",
                    "mensagem": (f"Carteira inaugural em {inicio:%d/%m/%Y}, ao preço de "
                                 "fechamento; sem posições a monitorar.")})
        return _finish(out, triggers, limitations, ks)
    track = rt.track()
    try:
        dates = [d for d in track.dates() if d <= as_of]
    except OSError as exc:  # pragma: no cover - disco
        dates = []
        limitations.append(f"Track record ilegível: {exc}")
    if not dates:
        out.update({"status": "sem registro", "aviso": "",
                    "mensagem": (f"Sem registro diário até {as_of}: o track record começa no "
                                 "fechamento do pregão de efetivação da primeira carteira.")})
        if ks["ativo"]:
            triggers.append(Trigger("INFO", "kill_switch_ligado",
                                    f"Kill switch ligado: {ks.get('motivo')}",
                                    "só redução de risco até desligamento humano"))
        return _finish(out, triggers, limitations, ks)

    rec = track.get(dates[-1])
    assert rec is not None
    history_all = [r for r in track.records() if r.date <= rec.date]
    peak = max([history_all[0].nav_start_usd] + [r.nav_end_usd for r in history_all])
    inception = history_all[0].nav_start_usd
    proposal, notes = _live_proposal(rt, rec)
    limitations += notes
    out.update({
        "status": "ok",
        "aviso": (f"{SIMULATED_DATA_NOTICE} — {rec.data_notice}" if rec.is_synthetic
                  and SIMULATED_DATA_NOTICE not in rec.data_notice.upper()
                  else rec.data_notice or cfg.fund.track_record_type),
        "base": {"registro": rec.date, "registro_hash": rec.record_hash,
                 "semana_vigente": rec.live_book_week,
                 "proposta_vigente": proposal.proposal_id if proposal else None},
        "nav": {"fechamento_usd": rec.nav_end_usd, "pico_usd": peak,
                "retorno_dia": rec.ret, "retorno_acumulado": rec.nav_end_usd / inception - 1.0,
                "nav_inicial_usd": inception},
        "drawdown": {"fechamento": rec.risk.drawdown,
                     "estagio": drawdown_stage(rec.risk.drawdown, cfg),
                     "escada": {"soft_stop": cfg.drawdown.soft_stop,
                                "hard_stop": cfg.drawdown.hard_stop,
                                "stop_out": cfg.drawdown.stop_out}},
    })
    if ks["ativo"]:
        triggers.append(Trigger("INFO", "kill_switch_ligado", f"Kill switch ligado: {ks.get('motivo')}",
                                "só redução de risco até desligamento humano"))
    prev_s = (previous_data_session(as_of) if cfg.execution is not None
              else previous_session(as_of))
    if rec.date < prev_s:
        triggers.append(Trigger("SOFT", "registro_defasado",
                                f"Último registro diário é de {rec.date}; o pregão de {prev_s} "
                                "não foi fechado",
                                "rodar o fechamento diário pendente (skill diario)"))
    triggers += _drawdown_triggers(rec.risk.drawdown, cfg, origem="no fechamento",
                                   sufixo="fechamento")
    triggers += _velocity_triggers(rt, history_all, limitations)
    risk, t = _risk_block(rec, cfg)
    out["risco"] = risk
    triggers += t
    idio, t = idio_monitor(rt, history_all, limitations)
    if idio is not None:
        out["idio"] = idio
    triggers += t
    rows, over, t = _exposures_block(rec)
    out["exposicoes"] = rows
    out["exposicoes_acima_do_limite"] = over
    triggers += t
    out["liquidez"], t = _liquidity_block(rec, proposal, cfg)
    triggers += t
    high, t = _squeeze_high(rec, proposal)
    triggers += t

    shorts_close = [{"ticker": p.ticker, "emissor": p.issuer_id, "acoes": p.shares,
                     "preco_local": p.price_local, "fx": _fx_from_position(p)}
                    for p in rec.positions if p.market_value_usd < 0]
    stops = squeeze_stop_checks(cfg, shorts_close, _iter_history(track, rec.date, False),
                                rec.nav_end_usd)
    live_stops: list[dict] = []
    if live:
        from ..data.intraday import fetch_intraday_quotes

        fetch = fetch_quotes or fetch_intraday_quotes
        held = [p for p in rec.positions if p.market_value_usd != 0]
        tickers = sorted({p.ticker for p in held})
        ccys = sorted({p.currency for p in held if p.currency != "USD"})
        try:
            quotes = fetch(tickers, ccys, None)
        except Exception as exc:  # noqa: BLE001 - rede/fonte: o monitor reporta e segue
            quotes = None
            limitations.append(f"Cotações intradiárias indisponíveis: {_clip(str(exc), 200)}")
        if quotes is not None and not quotes.empty:
            lv = _live_block(rec, quotes, as_of, cfg, peak)
            out["intradiario"] = lv
            if rec.date >= as_of:
                limitations.append(f"O registro de {rec.date} já é o fechamento de hoje: o P&L "
                                   "intradiário compara com esse fechamento.")
            elif rec.date < prev_s:
                limitations.append(f"P&L intradiário contra o fechamento de {rec.date} (há "
                                   "pregões sem fechamento registrado no meio).")
            if lv["sem_cotacao"]:
                limitations.append("Posições sem cotação do dia ficam fora do P&L intradiário "
                                   "(nunca viram retorno zero) e entram no net/gross estimados "
                                   "pelo valor do último fechamento.")
            limitations.append("NAV intradiário estimado sem accrual de financiamento/aluguel "
                               "do dia; risco ex-ante e beta são os do último fechamento.")
            cov = lv["cobertura_gross"]
            ok_cov = cov is not None and cov >= MIN_LIVE_COVERAGE
            if not ok_cov:
                triggers.append(Trigger(
                    "INFO", "cobertura_intradiaria_parcial",
                    f"Cobertura intradiária de {fmt_pct(cov)} do gross (mínimo "
                    f"{fmt_pct(MIN_LIVE_COVERAGE)} para gatilho HARD de drawdown)",
                    "gatilhos intradiários de drawdown rebaixados a SOFT"))
            close_rank = STAGE_RANK.get(drawdown_stage(rec.risk.drawdown, cfg) or "", 0)
            if STAGE_RANK.get(lv["estagio_estimado"] or "", 0) > close_rank:
                triggers += _drawdown_triggers(
                    lv["drawdown_estimado"], cfg, origem="intradiário (estimado)",
                    sufixo="intradiario", hard_allowed=ok_cov,
                    nota="" if ok_cov else "cobertura insuficiente")
            px_now = {r["ticker"]: (r["preco_agora"], r["fx_agora"]) for r in lv["posicoes"]}
            shorts_live = [{"ticker": p.ticker, "emissor": p.issuer_id, "acoes": p.shares,
                            "preco_local": px_now[p.ticker][0], "fx": px_now[p.ticker][1]}
                           for p in rec.positions
                           if p.market_value_usd < 0 and p.ticker in px_now]
            nav_now = lv["nav_estimado_usd"] or rec.nav_end_usd
            live_stops = squeeze_stop_checks(cfg, shorts_live,
                                             _iter_history(track, rec.date, True), nav_now)
        elif quotes is not None:
            limitations.append("A fonte não devolveu cotações intradiárias.")
    out["squeeze"] = {"shorts_high": high, "n_high_no_fechamento": rec.risk.squeeze_high_shorts,
                      "stops_fechamento": stops, "stops_intradiario": live_stops,
                      "regra": "por nome" if _per_name(cfg) else "livro inteiro"}
    cortados: dict[str, list[float]] = {}
    if _per_name(cfg):
        vetos, cortados, t = _squeeze_name_state(rt, cfg, history_all)
        out["squeeze"]["vetos_compra"] = vetos
        triggers += t
    triggers += _squeeze_triggers(cfg, stops, "no fechamento", cortados=cortados)
    closed_hits = {s["ticker"] for s in stops if s["stop_posicao"] or s["stop_nav"]}
    triggers += _squeeze_triggers(cfg, [s for s in live_stops if s["ticker"] not in closed_hits],
                                  "intradiário", intradiario=True)
    escalated: dict[str, list[float]] = {}
    if _per_name(cfg):
        esc, esc_info = _squeeze_escalation(cfg, history_all, live_stops,
                                            as_of if live_stops else None)
        out["squeeze"]["escalada"] = esc_info
        escalated = dict(esc_info["entradas"])
        if esc is not None:
            triggers.append(esc)
    out["alertas_do_registro"] = list(rec.alerts)
    if not ks["ativo"]:
        # Kill switch desligado por humano: condição já revisada não o religa; só piora religa.
        review = _human_review(rt, cfg, history_all)
        entries = {**_squeeze_codes(live_stops), **_squeeze_codes(stops)}
        triggers = _apply_review(triggers, review, entries, escalated, registro=rec.date)
        if review is not None:
            out["revisao_humana"] = {k: v for k, v in review.items() if not k.startswith("_")}
    return _finish(out, triggers, limitations, ks)


def _squeeze_name_state(rt: Runtime, cfg: FundConfig, history_asc: list[DailyRecord]
                        ) -> tuple[list[dict], dict[str, list[float]], list[Trigger]]:
    """Estado do stop de squeeze por nome nos registros encadeados (:func:`cdp.risk.limites.
    episodios_de_squeeze`): emissores de compra vedada até revisão humana (com o corte ainda
    pendente ou não), episódios já cortados (ticker → preços médios de entrada) e o gatilho INFO
    com os vetos que aguardam revisão."""
    from ..risk.limites import episodios_de_squeeze, revisado

    eps = episodios_de_squeeze(history_asc, cfg)
    if not eps:
        return [], {}, []
    revs = rt.squeeze_reviews()
    cortados: dict[str, list[float]] = {}
    for e in eps:
        if e.cortado_em is not None and e.encerrado_em is None:
            cortados.setdefault(e.ticker, []).append(e.preco_medio_entrada)
    vetos = [{"emissor": e.emissor, "ticker": e.ticker, "data_stop": e.data_stop,
              "preco_medio_entrada": e.preco_medio_entrada, "acoes_no_stop": e.acoes_no_stop,
              "acoes_atuais": e.acoes_atuais, "corte_pendente": e.corte_pendente,
              "cortado_em": e.cortado_em}
             for e in eps if not revisado(e, revs)]
    t: list[Trigger] = []
    if vetos:
        nomes = sorted({(v["emissor"], v["data_stop"]) for v in vetos})
        lista = ", ".join(f"{i} (stop em {d:%d/%m/%Y})" for i, d in nomes)
        t.append(Trigger(
            "INFO", SQUEEZE_VETO_CODE,
            f"Compra vedada até revisão humana (stop de squeeze por nome): {lista}",
            "revisão humana num terminal próprio: cdp kill-switch revisar-squeeze --emissor "
            "<emissor> --reason <motivo> --by <nome> (docs/cdp/EXECUCAO.md §12)"))
    return vetos, cortados, t


def _finish(out: dict, triggers: list[Trigger], limitations: list[str], ks: dict) -> dict:
    order = {"HARD": 0, "SOFT": 1, "INFO": 2}
    seen: set[str] = set()
    uniq: list[Trigger] = []
    for t in sorted(triggers, key=lambda x: order[x.nivel]):
        if t.codigo not in seen:
            seen.add(t.codigo)
            uniq.append(t)
    hard = [t for t in uniq if t.nivel == "HARD"]
    actions: list[str] = []
    reason = None
    if hard:
        reason = _shell_safe(_clip("Monitor de risco (código): "
                                   + "; ".join(t.motivo for t in hard)))
        if ks.get("ativo"):
            actions.append("manter kill switch (já ligado): " + reason)
        else:
            actions.append(KILL_SWITCH_PREFIX + reason)
    actions += [REVIEW_PREFIX + t.motivo for t in uniq if t.nivel == "SOFT"]
    out["gatilhos"] = [asdict(t) for t in uniq]
    out["acoes_recomendadas"] = actions
    out["motivo_kill_switch"] = reason if hard and not ks.get("ativo") else None
    out["limitacoes"] = limitations
    return out


# ----------------------------------------------------------------------------- relatório


def _pct(x: object, signed: bool = False) -> str:
    return fmt_pct(_num(x), signed=signed)


def render_risk_markdown(res: dict, cfg: FundConfig) -> str:
    """Relatório legível (pt-BR); todos os números já vêm calculados pelo código."""
    gen = res["gerado_em"]
    hhmm = gen.strftime("%H:%M") if isinstance(gen, datetime) else str(gen)
    L: list[str] = [f"# Risco — {res['fundo']} — {res['data']} {hhmm} (Brasília)", ""]
    if res.get("aviso"):
        L += [f"> {res['aviso']}", ""]
    L += [f"- Modo: {res['modo']}", f"- Status: {res['status']}"]
    ks = res["kill_switch"]
    L.append("- Kill switch: " + (f"**LIGADO** — {ks.get('motivo')}" if ks.get("ativo")
                                  else "desligado"))
    base = res.get("base")
    if base:
        L.append(f"- Base: registro de {base['registro']} (semana vigente "
                 f"{base['semana_vigente']}; hash `{str(base['registro_hash'])[:12]}`)")
    rev = res.get("revisao_humana")
    if rev:
        when = rev.get("desligado_em")
        when_txt = when.isoformat(timespec="minutes") if isinstance(when, datetime) else str(when)
        L.append(f"- Revisão humana: kill switch desligado em {when_txt} por {rev.get('por')} "
                 f"(registro-base {rev.get('registro_base')}); só uma piora religa"
                 + (f" — rebaixados a SOFT: {', '.join(rev['codigos_rebaixados'])}"
                    if rev.get("codigos_rebaixados") else ""))
    pend = res.get("decisao_pendente")
    if pend:
        if "erro" in pend:
            L.append(f"- Decisão da semana {pend['semana']}: erro ao ler ({pend['erro']})")
        else:
            L.append(f"- Decisão da semana {pend['semana']} gravada, a executar no fechamento: "
                     f"vol ex-ante {_pct(pend.get('vol_ex_ante'))}, beta "
                     f"{fmt_num(_num(pend.get('beta')), 3, signed=True)}, gross "
                     f"{_pct(pend.get('gross'))}, net {_pct(pend.get('net'), True)}, "
                     f"{pend.get('n_long')} longs / {pend.get('n_short')} shorts")
    if res.get("mensagem"):
        L += ["", res["mensagem"]]
    L += ["", "## Ações recomendadas (determinísticas)", ""]
    L += [f"- {a}" for a in res["acoes_recomendadas"]] or ["- nenhuma"]
    L += ["", "## Gatilhos", ""]
    if res["gatilhos"]:
        L += ["| Nível | Código | Motivo | Ação |", "|---|---|---|---|"]
        L += [f"| {t['nivel']} | `{t['codigo']}` | {t['motivo']} | {t['acao']} |"
              for t in res["gatilhos"]]
    else:
        L.append("Nenhum gatilho.")
    if res["status"] != "ok":
        return "\n".join(L + _limitations_md(res)) + "\n"
    nav, dd, rk = res["nav"], res["drawdown"], res["risco"]
    L += ["", "## NAV e drawdown (último fechamento)", "",
          f"- NAV: {fmt_usd_mm(nav['fechamento_usd'])} (pico {fmt_usd_mm(nav['pico_usd'])})",
          f"- Retorno do dia: {_pct(nav['retorno_dia'], True)}; acumulado: "
          f"{_pct(nav['retorno_acumulado'], True)}",
          f"- Drawdown: {_pct(dd['fechamento'])} — estágio "
          f"{STAGE_LABEL.get(dd['estagio'] or '', 'n/d')} (soft {_pct(dd['escada']['soft_stop'])}"
          f", hard {_pct(dd['escada']['hard_stop'])}, stop-out {_pct(dd['escada']['stop_out'])})"]
    L += ["", "## Risco ex-ante (último fechamento)", "",
          f"- Vol ex-ante: {_pct(rk['vol_ex_ante'])} (alvo {_pct(rk['vol_alvo'])}; banda "
          f"{_pct(rk['banda_vol'][0])}–{_pct(rk['banda_vol'][1])})",
          f"- Beta: {fmt_num(rk['beta'], 3, signed=True)} (limite ±{fmt_num(rk['beta_limite'], 3)})",
          f"- Net: {_pct(rk['net'], True)} (limite ±{_pct(rk['net_limite'])}); gross "
          f"{_pct(rk['gross'])}; long {_pct(rk['long'])}; short {_pct(rk['short'], True)}; "
          f"{rk['n_long']} longs / {rk['n_short']} shorts",
          f"- VaR 99% 1d: {_pct(rk['var_1d_99'])} (limite {_pct(rk['var_limite'])}); ES 99% 1d: "
          f"{_pct(rk['es_1d_99'])} (limite {_pct(rk['es_limite'])})",
          f"- Vol realizada 21d: {_pct(rk['vol_realizada_21d'])}; 63d: "
          f"{_pct(rk['vol_realizada_63d'])}"]
    idio = res.get("idio")
    if idio:
        L += ["", "## Fatia idiossincrática (três medidas)", "",
              f"- Ex-ante (κ_F {fmt_num(_num(idio.get('kappa_f')), 2)}): "
              f"{_pct(idio.get('ex_ante'))}; realizada em {idio.get('janela_pregoes')} pregões: "
              f"{_pct(idio.get('realizada_63d'))}; sem modelo (1 − R² ajustado): "
              f"{_pct(idio.get('sem_modelo_63d'))}"
              + (f" (desvio de amostragem sob a nula {_pct(idio.get('sem_modelo_banda'))})"
                 if _num(idio.get("sem_modelo_banda")) is not None else ""),
              f"- Meta {_pct(idio.get('meta'))}; piso {_pct(idio.get('piso'))}; registros na "
              f"janela: {idio.get('registros')}"]
    lv = res.get("intradiario")
    if lv:
        L += ["", "## Intradiário (estimado, cotações atrasadas da fonte)", "",
              f"- P&L desde o fechamento: {fmt_usd(_num(lv['pnl_usd']), signed=True)} "
              f"({_pct(lv['pnl_pct_nav'], True)} do NAV)",
              f"- NAV estimado: {fmt_usd_mm(_num(lv['nav_estimado_usd']))}; drawdown estimado: "
              f"{_pct(lv['drawdown_estimado'])} — estágio "
              f"{STAGE_LABEL.get(lv['estagio_estimado'] or '', 'n/d')}",
              f"- Net/gross estimados: {_pct(lv['net_estimado'], True)} / "
              f"{_pct(lv['gross_estimado'])}",
              f"- Cobertura do gross com cotação de hoje: {_pct(lv['cobertura_gross'])}"
              + (" (parcial)" if lv["parcial"] else "")]
        if lv["maiores_contribuicoes"]:
            L += ["", "| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |",
                  "|---|---|---|---|---|---|"]
            L += [f"| {r['ticker']} | {r['lado']} | {_pct(r['ret_local'], True)} | "
                  f"{_pct(r['ret_usd'], True)} | {fmt_usd(r['pnl_usd'], signed=True)} | "
                  f"{_pct(r['contribuicao'], True)} |" for r in lv["maiores_contribuicoes"]]
        if lv["sem_cotacao"]:
            L += ["", "Sem cotação do dia (fora do P&L): "
                  + ", ".join(f"{m['ticker']} ({m['motivo']})" for m in lv["sem_cotacao"])]
    if res["exposicoes_acima_do_limite"]:
        L += ["", "## Exposições acima do limite", "", "| Grupo | Nome | Net | Limite |",
              "|---|---|---|---|"]
        for e in res["exposicoes_acima_do_limite"]:
            style = e["grupo"] == "style"
            L.append(f"| {e['grupo']} | {e['nome']} | "
                     f"{fmt_num(e['net'], 3, True) if style else _pct(e['net'], True)} | "
                     f"±{fmt_num(e['limite'], 3) if style else _pct(e['limite'])} |")
    liq = res["liquidez"]
    closes_mode = liq.get("unidade") == "fechamentos"
    fmt = fmt_closes if closes_mode else fmt_days
    L += ["", "## Liquidez", "",
          (f"- Máximo de fechamentos para liquidar: {fmt(liq['max_dias_para_liquidar'])}; "
           f"gross liquidável em 1 fechamento: {_pct(liq['pct_gross_liquido_1d'])}"
           if closes_mode else
           f"- Máximo de dias para liquidar: {fmt(liq['max_dias_para_liquidar'])}; gross "
           f"liquidável em 1 dia: {_pct(liq['pct_gross_liquido_1d'])}")]
    for o in liq["posicoes_acima_do_limite"]:
        L.append(f"- {o['emissor']} ({o['ticker']}, {o['lado']}): {fmt(o['dias'])} > "
                 f"{fmt(o['limite'])}")
    if liq["sem_adtv"]:
        L.append(f"- ADTV indisponível: {', '.join(liq['sem_adtv'])}")
    sq = res["squeeze"]
    L += ["", "## Short squeeze", "",
          f"- Shorts HIGH no último fechamento: {sq['n_high_no_fechamento']}"]
    for h in sq["shorts_high"]:
        L.append(f"- {h['ticker']} ({h['emissor']}): HIGH já na decisão (escore "
                 f"{fmt_num(h['escore_na_decisao'], 1)})")
    for label, rows in (("fechamento", sq["stops_fechamento"]),
                        ("intradiário", sq["stops_intradiario"])):
        for s in rows:
            flag = " **STOP**" if s["stop_posicao"] or s["stop_nav"] else ""
            L.append(f"- Short {s['ticker']} ({label}): {_pct(s['perda_desde_entrada'], True)} "
                     f"desde a entrada; {_pct(s['perda_pct_nav'], True)} do NAV{flag}")
    for v in sq.get("vetos_compra") or []:
        d = v.get("data_stop")
        d_txt = d.strftime("%d/%m/%Y") if isinstance(d, date) else str(d)
        corte = ("corte à metade pendente" if v.get("corte_pendente") else
                 "short zerado" if not v.get("acoes_atuais") else "corte à metade feito")
        L.append(f"- Compra vedada até revisão humana: {v['emissor']} ({v['ticker']}, stop em "
                 f"{d_txt}; {corte})")
    if res["alertas_do_registro"]:
        L += ["", "## Alertas do registro de fechamento", ""]
        L += [f"- {a}" for a in res["alertas_do_registro"]]
    return "\n".join(L + _limitations_md(res)) + "\n"


def _limitations_md(res: dict) -> list[str]:
    out = ["", "## Limitações", ""]
    lim = list(res.get("limitacoes") or [])
    out += [f"- {x}" for x in lim] or ["- nenhuma"]
    out += ["", "_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. "
            "Paper trading: o kill switch só bloqueia risco novo e nunca afrouxa limites._"]
    return out


def _json_default(o: object) -> object:
    if isinstance(o, datetime | date):
        return o.isoformat()
    return str(o)


def risk_json(res: dict) -> str:
    return json.dumps(res, ensure_ascii=False, indent=2, default=_json_default)


def write_risk_report(res: dict, out_root: Path | str, cfg: FundConfig) -> dict[str, str]:
    """Grava ``<out_root>/<data>/risco_<HHMM>.md`` e ``.json`` (nunca sobrescreve)."""
    gen = res["gerado_em"]
    hhmm = gen.strftime("%H%M") if isinstance(gen, datetime) else "0000"
    folder = Path(out_root) / str(res["data"])
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"risco_{hhmm}"
    k = 1
    while (folder / f"{stem}.md").exists() or (folder / f"{stem}.json").exists():
        k += 1
        stem = f"risco_{hhmm}_{k}"
    md_path, json_path = folder / f"{stem}.md", folder / f"{stem}.json"
    with md_path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(render_risk_markdown(res, cfg))
    with json_path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(risk_json(res) + "\n")
    return {"md": str(md_path), "json": str(json_path)}


def summary_view(res: dict) -> dict:
    """Versão compacta para o terminal (as listas completas ficam no ``.json``)."""
    out = {k: v for k, v in res.items() if k != "exposicoes"}
    lv = out.get("intradiario")
    if lv:
        out["intradiario"] = {k: v for k, v in lv.items() if k != "posicoes"}
    sq = out.get("squeeze")
    if sq:
        hit = [s for s in sq["stops_fechamento"] + sq["stops_intradiario"]
               if s["stop_posicao"] or s["stop_nav"]]
        out["squeeze"] = {"shorts_high": sq["shorts_high"],
                          "n_high_no_fechamento": sq["n_high_no_fechamento"],
                          "stops_acionados": hit,
                          "shorts_verificados": len(sq["stops_fechamento"]),
                          "vetos_compra": sq.get("vetos_compra", [])}
    return out


__all__ = ["KILL_SWITCH_PREFIX", "MIN_LIVE_COVERAGE", "PRE_INICIO", "RISK_DIRNAME",
           "SQUEEZE_ESCALATION_ACTION", "SQUEEZE_ESCALATION_CODE", "SQUEEZE_STOP_ACTION",
           "SQUEEZE_STOP_ACTION_CORTADO", "SQUEEZE_STOP_ACTION_INTRADIARIO",
           "SQUEEZE_STOP_ACTION_LIVRO", "SQUEEZE_VETO_CODE", "Trigger", "drawdown_stage",
           "idio_monitor", "render_risk_markdown", "risk_json", "run_risk_monitor",
           "squeeze_stop_checks", "squeeze_stop_history", "squeeze_stop_hits", "summary_view",
           "write_risk_report"]
