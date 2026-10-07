"""Rotina diária do CDP — Cabra da Peste: execução MOC, marcação a mercado, risco, atribuição e
alertas, gravando um ``DailyRecord`` imutável e encadeado por hash no track record.

Convenção de execução (``fund.execution_convention``)
-----------------------------------------------------
A carteira é decidida no dia de montagem D (último pregão da semana na NYSE, com a seção
``execution``; o primeiro pregão da semana na B3 sem ela) ANTES do fechamento, com todos os
dados disponíveis até o momento da análise, e executada no FECHAMENTO de D (MOC). Na rotina
diária de D:

1. apura o P&L do dia da carteira ANTIGA, do fechamento anterior ao fechamento de D — a carteira
   nova não participa do P&L de D;
2. executa a carteira decidida no fechamento de D. Com a seção ``execution``
   (:mod:`cdp.portfolio.execucao`): as ordens são quantidades de ações fixadas na decisão
   (``PositionTarget.shares``; sem ela, peso × NAV(D) ao fechamento), cada linha executa ao seu
   fechamento OFICIAL limitada à capacidade do leilão e da janela pré-fechamento calculada com o
   volume realizado no pregão; linha sem pregão (ou com fechamento antes do prazo mais a margem)
   não negocia e o emissor mantém as ações; banda de não-negociação ``min_trade_weight``; a
   parcela não executada não é carregada (a decisão seguinte parte da carteira efetiva). Sem a
   seção: nocional-alvo = peso × NAV(D) ao preço de fechamento local e câmbio do dia. Custos do
   modelo de custos são debitados em D;
3. grava o ``BookEntry`` (``booked_at`` = fechamento oficial mais tardio entre as linhas
   executadas) com a carteira resultante e as posições de fim de dia do registro passam a ser as
   da carteira NOVA (linhas encerradas aparecem com valor zero e o P&L do dia).

No primeiro registro (inception) não há carteira antiga: o NAV parte de
``fund.inception_nav_usd`` na abertura de D e o P&L do dia são apenas os custos.

A decisão precisa ter sido gravada até o corte de ordens do fechamento (``decided_at``,
:func:`decision_cutoff`) e só executa nos pregões de :func:`executable_in` (com ``execution``,
fase 1: apenas o fechamento do próprio dia de montagem). Decisões autônomas são conferidas com
:func:`~cdp.workflow.autonomy.verify_autonomous_decision`; humanas, com
:func:`~cdp.workflow.approval.verify_decision` — sempre contra o mandato ATUAL. A efetivação
é gravada pelo próprio livro (``Book.save_proposal``/``save_decision``/``save_booked``, que
revalida a aprovação, a carteira aprovada, a cronologia e o KILL_SWITCH).

Uma efetivação JÁ gravada no livro é adotada conferindo a decisão contra os próprios hashes (o
livro validou o mandato no booking; mudança posterior vira alerta). Com carteira vigente, uma
decisão descoberta no livro que não passa nas checagens, ou uma execução recusada (livro,
KILL_SWITCH, linha sem preço/câmbio — :class:`ExecutionRefused`), NÃO interrompe o track record:
o dia é registrado com a carteira anterior e um alerta com o motivo. Uma decisão inválida passada
explicitamente (``pending``) continua sendo erro do chamador.

Integridade e ausência de look-ahead: a marcação só parte de um último registro íntegro (hash
recalculado, CSV e evento de auditoria); os dados são cortados na data do pregão e barra
intradiária provisória é recusada; o modelo de risco da sessão anterior (exposições da atribuição)
é estimado com ``store.load(sessão anterior)``, de modo que o registro não depende do caminho
(rotina diária × backfill).

Contas do dia (USD)
-------------------
- As posições derivam com os preços entre rebalanceamentos: o valor de mercado inicial vem das
  posições de fim de dia do registro anterior.
- P&L da linha = valor inicial × retorno total em USD da linha no período
  (``AssetPanel.line_returns`` composto nas sessões após o registro anterior). Retorno ausente ⇒
  a linha não negociou: P&L 0, ``repriced=False``, valor mantido e alerta (nunca um retorno
  inventado); o movimento entra integralmente quando a linha voltar a negociar.
- Financiamento = NAV inicial × USD_3M (taxa conhecida no pregão anterior) / 360 × dias corridos
  desde o registro anterior (ACT/360; juros do caixa/colateral).
- Aluguel = − Σ |valor inicial dos shorts| × taxa anual / 360 × dias (taxa da proposta efetivada;
  senão a tabela de aluguel do dia; senão a taxa padrão conservadora, com alerta).
- Custos = custos de transação estimados das negociações do dia (negativos).
- NAV final = NAV inicial + ações + financiamento + aluguel + custos.

Atribuição
----------
Exposições do modelo de risco estimado na sessão ANTERIOR × retornos fatoriais do período (da
regressão cross-section de cada sessão no modelo estimado hoje; se a sessão não tiver retornos
fatoriais, regressão do dia com as mesmas exposições). Linha que voltou a negociar recebe os
retornos fatoriais de todas as sessões desde o seu último preço válido. ``específico = ações −
fatores`` por construção (soma exata). Linhas por componente, grupo de fatores, fator, emissor,
país, setor e lado (long × short); ``contribution`` = P&L / NAV inicial.

Carteira-sombra só-quant
------------------------
A proposta ``WeeklyOutcome.shadow_quant`` é "executada" do mesmo modo numa segunda série
(``book/track_record_shadow``), sem decisão: mede, dia a dia, o valor agregado pelo PM do CDP
em relação ao quant puro (:func:`~cdp.workflow.track_record.compare_tracks`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..analytics.liquidity import liquidity_profile, liquidity_summary
from ..analytics.panel import STALE_DAYS_MAX, AssetPanel, build_asset_panel, fx_for_lines
from ..analytics.shortability import issuer_side_lines, short_availability
from ..analytics.squeeze import squeeze_table
from ..config import FundConfig
from ..contracts import (
    AttributionLine,
    BookedPosition,
    BookEntry,
    DailyPosition,
    DailyRecord,
    DailyRisk,
    Decision,
    DecisionMode,
    DecisionType,
    ExposureLine,
    PositionTarget,
    Proposal,
    Side,
)
from ..hashing import sha256_file, sha256_obj, sha256_text
from ..market import MarketData
from ..portfolio.costs import CostModel, build_cost_model, estimate_rebalance_costs
from ..risk.analytics import (
    historical_var_es,
    parametric_var_es,
    predicted_betas,
    risk_decomposition,
)
from ..risk.event_scaling import apply_event_windows
from ..risk.exposures import market_weights
from ..risk.model import estimate_risk_model
from ..risk.types import STYLE_FACTORS, RiskModel
from .approval import verify_decision
from .autonomy import verify_autonomous_decision
from .book import Book, dump_json
from .ledger import DEFAULT_BORROW_FEE_ANNUAL, cross_sectional_factor_returns
from .memo import fmt_closes, fmt_days, fmt_num, fmt_pct, fmt_usd, fmt_usd_mm
from .track_record import (
    GENESIS_RECORD_HASH,
    REALIZED_VOL_WINDOWS,
    SHADOW_RECORD_EVENT,
    TrackRecord,
    realized_vol,
    write_exclusive,
)

MARKET_CLOSE_LOCAL = time(17, 0)
"""Fechamento usado na execução MOC (17h de Brasília = fechamento da B3 e da NYSE em out/2026)."""
DAY_COUNT_BASIS = 360.0
FINANCING_RATE_SERIES = "USD_3M"
RATE_STALE_DAYS = 10
RATE_PLAUSIBLE_RANGE = (-0.02, 0.25)
"""Faixa plausível da taxa anual em decimal; fora dela (ex.: 4.5 = taxa em %) a taxa é recusada."""
MAX_ALERT_TEXT = 300
ENTRY_LOOKBACK_RECORDS = 260
"""Registros consultados (do mais recente para trás) para o preço médio de entrada dos shorts."""
HOLD_STATUS = "hold"
DAILY_ACTOR = "CDP — rotina diária"
SHADOW_LABEL = "sombra só-quant"
#: Fontes públicas da base de mercado, nomeadas entre parênteses no aviso de dados (o rodapé do
#: painel as lê dali).
REAL_DATA_SOURCES = "Yahoo Finance, B3, FINRA, BCB"
SHADOW_BOOKED_EVENT = "BOOKED_SHADOW"
SHADOW_PROPOSAL_EVENT = "SHADOW_PROPOSAL_SAVED"
BOOK_SHADOW_FILE = "shadow_quant.json"
"""Proposta-sombra gravada pelo pipeline semanal em ``<livro>/<semana>/`` (evento SHADOW_QUANT)."""
BOOK_SHADOW_EVENT = "SHADOW_QUANT"
COMPONENTS = ("equity", "factor", "specific", "financing", "borrow", "costs")
FACTOR_GROUPS = ("market", "country", "sector", "style")
_MAX_LISTED = 8


class NoSessionError(ValueError):
    """Não houve pregão na data (sem preços de fechamento no armazenamento de mercado)."""


class NoBookError(ValueError):
    """Não há carteira efetivada para iniciar (ou continuar) o track record."""


class ExecutionRefused(ValueError):
    """A execução MOC da decisão foi recusada (livro, KILL_SWITCH, preço/câmbio ausente).

    Na rotina diária com carteira vigente, a recusa NÃO interrompe o track record: o dia é
    registrado com a carteira anterior e um alerta com o motivo (nenhuma negociação ocorreu).
    """


class MarketSource(Protocol):
    """Fonte de dados de mercado sem look-ahead (ex.: ``cdp.data.store.MarketStore``)."""

    def load(self, as_of: date) -> MarketData: ...


# ==========================================================
# Contêineres públicos
# ==========================================================

@dataclass(frozen=True)
class PendingExecution:
    """Decisão da semana a executar no fechamento (proposta final, decisão e sombra só-quant)."""

    proposal: Proposal
    decision: Decision
    shadow: Proposal | None = None
    snapshot_hash_now: str | None = None

    @property
    def week(self) -> date:
        return self.proposal.week

    @classmethod
    def from_outcome(cls, outcome: Any, snapshot_hash_now: str | None = None) -> PendingExecution:
        """A partir de ``weekly.WeeklyOutcome`` (``final``, ``decision``, ``shadow_quant``)."""
        return cls(proposal=outcome.final, decision=outcome.decision,
                   shadow=outcome.shadow_quant, snapshot_hash_now=snapshot_hash_now)


@dataclass
class DailyContext:
    """Insumos da sessão, todos com dados até ``date`` (sem look-ahead).

    ``model`` é o modelo de risco estimado na própria sessão (retornos fatoriais do dia);
    ``risk_model`` é o mesmo modelo com as janelas de evento do mandato (risco ex-ante);
    ``model_prev`` é o modelo da sessão anterior (exposições usadas na atribuição).
    """

    date: date
    md: MarketData
    panel: AssetPanel
    model: RiskModel | None
    book_entry: BookEntry | None
    prev: DailyRecord | None
    model_prev: RiskModel | None = None
    risk_model: RiskModel | None = None
    notes: list[str] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def ts(self) -> pd.Timestamp:
        return pd.Timestamp(self.date)


@dataclass(frozen=True)
class DailyRunResult:
    record: DailyRecord
    shadow: DailyRecord | None = None
    booked: BookEntry | None = None
    shadow_booked: BookEntry | None = None
    lapsed: dict[str, Any] | None = None
    """Efetivação recusada no leilão do dia de montagem (kill switch): a decisão caducou
    (registro de :meth:`Book.registrar_efetivacao_recusada`)."""

    @property
    def value_added(self) -> float | None:
        """Retorno do dia do CDP menos o da sombra só-quant (``None`` sem sombra)."""
        return None if self.shadow is None else self.record.ret - self.shadow.ret


# ==========================================================
# Utilidades puras
# ==========================================================

def close_datetime(session: date, cfg: FundConfig) -> datetime:
    """Horário (com fuso) do fechamento do pregão para a execução MOC.

    Com a seção ``execution``: o fechamento oficial mais tardio entre os mercados abertos
    (limite superior do ``booked_at`` de cada efetivação, que usa o fechamento mais tardio entre
    as linhas executadas). Legado: 17h de Brasília (:data:`MARKET_CLOSE_LOCAL`)."""
    if cfg.execution is not None:
        from ..portfolio.execucao import fechamento_mais_tardio, janela_execucao

        late = fechamento_mais_tardio(janela_execucao(session, cfg))
        if late is not None:
            return late.astimezone(ZoneInfo(cfg.fund.timezone))
    return datetime.combine(session, MARKET_CLOSE_LOCAL, tzinfo=ZoneInfo(cfg.fund.timezone))


def decision_cutoff(session: date, cfg: FundConfig) -> datetime:
    """Horário-limite de ``decided_at`` para executar no fechamento de ``session``.

    Com a seção ``execution``: o corte MOC mais tardio entre os mercados elegíveis (cada linha
    ainda confere o corte do próprio mercado na execução). Legado: o fechamento das 17h."""
    if cfg.execution is not None:
        from ..portfolio.execucao import janela_execucao, mercados_elegiveis

        j = janela_execucao(session, cfg)
        elig = mercados_elegiveis(j, cfg)
        cuts = [t for m, t in j.corte_moc.items() if elig.get(m, False)]
        if cuts:
            return max(cuts).astimezone(ZoneInfo(cfg.fund.timezone))
        return j.prazo_decisao.astimezone(ZoneInfo(cfg.fund.timezone))
    return close_datetime(session, cfg)


def executable_in(week: date, session: date, cfg: FundConfig | None = None) -> bool:
    """A decisão da semana ``week`` é executável no fechamento de ``session``.

    Legado (sem ``cfg`` ou sem a seção ``execution``): mesma semana (seg–sex) e ``session`` ≥
    ``week``. Com ``execution``: ``week`` ≤ ``session`` < próximo dia de montagem, limitado aos
    ``execution.max_closes`` primeiros pregões de dados a partir de ``week`` (fase 1: só o
    fechamento do próprio dia de montagem; uma efetivação perdida é refeita no mesmo fechamento)."""
    if cfg is None or cfg.execution is None:
        monday = week - timedelta(days=week.weekday())
        return week <= session and monday == session - timedelta(days=session.weekday())
    from ..calendar import is_data_session, next_rebalance_after

    if session < week or session >= next_rebalance_after(week, cfg):
        return False
    n = 0
    d = week
    while d <= session:
        if is_data_session(d):
            n += 1
        d += timedelta(days=1)
    return 1 <= n <= cfg.execution.max_closes and is_data_session(session)


def session_has_prices(md: MarketData, session: date) -> bool:
    ts = pd.Timestamp(session)
    return ts in md.close.index and bool(md.close.loc[ts].notna().any())


def session_dates(md: MarketData, start: date, end: date) -> list[date]:
    """Pregões (datas com algum preço de fechamento) em ``[start, end]``."""
    idx = md.close.index
    has = md.close.notna().any(axis=1)
    mask = (idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end)) & has.to_numpy()
    return [ts.date() for ts in idx[mask]]


def store_input_hashes(store: object, session: date) -> dict[str, str]:
    """Hashes dos manifestos do armazenamento (base e incremento do dia), quando existirem.

    Segue o layout de ``MarketStore`` (``root/base/<as_of>/manifest.json`` e
    ``root/daily/<AAAA-MM-DD>/manifest.json``); fontes sem ``root`` não contribuem.
    """
    root = getattr(store, "root", None)
    if root is None:
        return {}
    root = Path(root)
    out: dict[str, str] = {}
    base_root = root / "base"
    if base_root.is_dir():
        bases = []
        for p in base_root.iterdir():
            try:
                d = date.fromisoformat(p.name)
            except ValueError:
                continue
            if p.is_dir() and (p / "manifest.json").exists():
                bases.append((d, p))
        if bases:
            # Mesma escolha de ``MarketStore.load``: a base mais recente <= pregão; sem nenhuma,
            # a mais antiga (cortada no pregão).
            eligible = [b for b in bases if b[0] <= session]
            chosen = max(eligible) if eligible else min(bases)
            out["base_snapshot_manifest"] = sha256_file(chosen[1] / "manifest.json")
    inc = root / "daily" / session.isoformat() / "manifest.json"
    if inc.exists():
        out["daily_increment_manifest"] = sha256_file(inc)
    return out


def clean_text(text: object, max_len: int = MAX_ALERT_TEXT) -> str:
    """Texto de origem externa (manifestos, mensagens de erro de coleta) numa linha só, sem
    caracteres de controle e com tamanho limitado — os alertas viram insumo do comentário do dia
    e nunca podem carregar blocos arbitrários (injeção de instruções)."""
    raw = "".join(ch if ch.isprintable() else " " for ch in str(text))
    one = " ".join(raw.split())
    return one if len(one) <= max_len else one[:max_len - 1].rstrip() + "…"


DATA_LIMITATION_PREFIX = "Limitação de dados:"
"""Prefixo dos alertas técnicos de qualidade de dados gravados no registro diário."""


def split_data_limitations(alerts: Iterable[str]) -> tuple[list[str], list[str]]:
    """``(alertas ao investidor, limitações técnicas de dados)``. As limitações (fonte, ajuste
    de preço, hash, paridade, câmbio defasado...) ficam na trilha e nos dados abertos; o texto
    ao investidor mostra só um resumo (:func:`data_limitations_summary`)."""
    investor: list[str] = []
    tech: list[str] = []
    for a in alerts:
        (tech if str(a).startswith(DATA_LIMITATION_PREFIX) else investor).append(str(a))
    return investor, tech


def data_limitations_summary(n: int) -> str | None:
    """Uma frase para o investidor sobre ``n`` avisos técnicos de dados (``None`` se zero)."""
    if n <= 0:
        return None
    return (f"{n} aviso{'s' if n != 1 else ''} técnico{'s' if n != 1 else ''} de qualidade de "
            "dados da fonte pública, sem efeito na execução nem na marcação; o detalhe está no "
            "registro diário, nos dados abertos.")


def session_limitations(md: MarketData, session: date) -> list[str]:
    """Limitações de dados relevantes para o pregão: as da base (sem data) e as do incremento do
    próprio dia (``"[AAAA-MM-DD] ..."`` no ``MarketStore``); as de outros dias e a linha de
    composição ficam fora (já constam dos registros dos respectivos dias/manifestos). Cada texto
    é saneado por :func:`clean_text`."""
    tag = f"[{session.isoformat()}]"
    out: list[str] = []
    for lim in md.manifest.limitations:
        text = str(lim).strip()
        if text.startswith("Composição:"):
            continue
        if text.startswith("[") and "]" in text[:13]:
            if text.startswith(tag):
                out.append(clean_text(text[len(tag):].strip()))
            continue
        out.append(clean_text(text))
    return out


def financing_rate(md: MarketData, as_of: date) -> tuple[float | None, date | None, list[str]]:
    """Taxa ``USD_3M`` (decimal anual) conhecida em ``as_of`` e alertas.

    Ausente ⇒ ``None`` com alerta. Fora de :data:`RATE_PLAUSIBLE_RANGE` (ex.: série gravada em %)
    ⇒ ``None`` com alerta: uma taxa 100× maior num registro imutável é pior que não apurar o
    financiamento. Defasada há mais de :data:`RATE_STALE_DAYS` dias ⇒ usada com alerta.
    """
    rates = md.rates
    if FINANCING_RATE_SERIES not in rates.columns:
        return None, None, [f"Taxa {FINANCING_RATE_SERIES} indisponível: financiamento do caixa "
                            "não apurado (zero) no período."]
    s = pd.to_numeric(rates[FINANCING_RATE_SERIES], errors="coerce").dropna()
    s = s[s.index <= pd.Timestamp(as_of)]
    if s.empty:
        return None, None, [f"Taxa {FINANCING_RATE_SERIES} indisponível: financiamento do caixa "
                            "não apurado (zero) no período."]
    rate, rate_date = float(s.iloc[-1]), s.index[-1].date()
    lo, hi = RATE_PLAUSIBLE_RANGE
    if not (lo <= rate <= hi):
        return None, rate_date, [
            f"Taxa {FINANCING_RATE_SERIES} de {rate_date} fora da faixa plausível "
            f"({fmt_num(rate, 4)}; esperado decimal anual entre {fmt_pct(lo)} e {fmt_pct(hi)}): "
            "financiamento do caixa não apurado (zero) — conferir a unidade da série."]
    alerts = []
    if (as_of - rate_date).days > RATE_STALE_DAYS:
        alerts.append(f"Taxa {FINANCING_RATE_SERIES} defasada (de {rate_date}).")
    return rate, rate_date, alerts


def factor_returns_source(session_model: RiskModel | None, model_prev: RiskModel,
                          session_ts: pd.Timestamp, session_returns: pd.Series | None,
                          *, required_macro: Iterable[str] = (),
                          observed_macro: pd.DataFrame | None = None,
                          observed_equity: pd.DataFrame | None = None,
                          ) -> tuple[Callable[[pd.Timestamp], pd.Series | None], dict[str, Any]]:
    """Retornos fatoriais por sessão para a atribuição com as exposições de ``model_prev``.

    Ordem: linha COMPLETA (todos os fatores de ``model_prev``) do modelo da sessão, depois do
    modelo anterior; para a própria sessão, regressão cross-section dos retornos do dia com as
    exposições de ``model_prev`` (``session_returns``). Uma linha incompleta (fator que o modelo
    do dia descartou) só é usada como último recurso no caminho legado, sem macro. Com macro,
    fixa os retornos observados, desconta B_macro × f_macro do retorno de ações e estima somente
    o bloco estrutural com B anterior. Não reutiliza WLS estimada sobre retorno bruto.
    """
    names = model_prev.factor_names
    macro = sorted(set(required_macro) | {n for n in names if n.startswith("macro:")})
    structural = [n for n in names if n not in macro]
    frames = [m.factor_returns for m in (session_model, model_prev) if m is not None]
    cache: dict[pd.Timestamp, pd.Series | None] = {}
    state: dict[str, Any] = {"fallback": False, "partial": {}, "missing_macro": {}}

    def get(s: pd.Timestamp) -> pd.Series | None:
        if s in cache:
            return cache[s]
        row: pd.Series | None = None
        partial: pd.Series | None = None
        observed = None
        if macro:
            if set(macro) - set(names):
                state["missing_macro"][str(s.date())] = sorted(set(macro) - set(names))
                cache[s] = None
                return None
            if observed_macro is not None:
                observed = (observed_macro.loc[s].reindex(macro) if s in observed_macro.index
                            else pd.Series(np.nan, index=macro))
            else:
                for fr in frames:
                    if s in fr.index:
                        cand = fr.loc[s].reindex(macro).astype(float)
                        if np.isfinite(cand.to_numpy()).all():
                            observed = cand
                            break
            if observed is None or not np.isfinite(observed.to_numpy(dtype=float)).all():
                state["missing_macro"][str(s.date())] = macro
                cache[s] = None
                return None
            y = (observed_equity.loc[s] if observed_equity is not None
                 and s in observed_equity.index else
                 session_returns if s == session_ts else None)
            if y is None:
                cache[s] = None
                return None
            B = model_prev.exposures
            residual = y - B[macro] @ observed
            est = cross_sectional_factor_returns(B[structural], residual,
                                                 model_prev.specific_var)
            if est is not None:
                row = est.reindex(names).astype(float)
                row.loc[macro] = observed
                if not np.isfinite(row.to_numpy()).all():
                    row = None
                state["fallback"] = True
            cache[s] = row
            return row
        for fr in frames:
            if s in fr.index:
                cand = fr.loc[s].reindex(names).astype(float)
                if np.isfinite(cand.to_numpy()).all():
                    row = cand
                    break
                if partial is None and cand.notna().any():
                    partial = cand
        if row is None and s == session_ts and session_returns is not None:
            y = session_returns
            B = model_prev.exposures
            est = cross_sectional_factor_returns(B, y,
                                                 model_prev.specific_var)
            if est is not None:
                row = est.reindex(names).astype(float)
                state["fallback"] = True
        if row is None and partial is not None and not macro:
            state["partial"][str(s.date())] = sorted(partial.index[partial.isna()])
            row = partial
        cache[s] = row
        return row

    return get, state


def _list(items: Iterable[str]) -> str:
    items = list(items)
    head = ", ".join(items[:_MAX_LISTED])
    return head + (f" (+{len(items) - _MAX_LISTED})" if len(items) > _MAX_LISTED else "")


def _int_br(n: int) -> str:
    """Inteiro com separador de milhar pt-BR (``196484`` ⇒ ``196.484``)."""
    return f"{int(n):,}".replace(",", ".")


def _round_shares(x: float) -> int:
    """Arredonda à ação inteira (meio para longe de zero)."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def _finite(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _last_valid(series: pd.Series, ts: pd.Timestamp) -> tuple[float | None, pd.Timestamp | None]:
    s = pd.to_numeric(series.loc[:ts], errors="coerce").dropna()
    s = s[np.isfinite(s) & (s > 0)]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def _meta_hash(model: RiskModel) -> str:
    try:
        return sha256_obj({"as_of": model.as_of, "meta": model.meta})
    except TypeError:
        return sha256_text(repr(sorted((str(k), repr(v)) for k, v in model.meta.items())))


def drawdown_stage_action(stage: str, cfg: FundConfig) -> str:
    """Ação que o mandato exige em cada estágio da escada de drawdown, exatamente como o código a
    aplica: com ``drawdown.risk_reference = "normal_book_vol"`` (metodologia vigente), teto da vol
    ex-ante em ``m·σ_ref`` (``m`` = 75%/50%/25% da vol da mesma carteira no estágio normal); no
    mandato legado, corte do gross."""
    d = cfg.drawdown
    if d.risk_reference == "normal_book_vol":
        from ..risk.drawdown import stage_multiplier

        cap = (f"vol ex-ante limitada a {fmt_pct(stage_multiplier(stage, cfg))} da vol da mesma "
               "carteira no estágio normal (m·σ_ref)")
        if stage == "stop_out":
            return f"{cap} e revisão completa do processo"
        if stage == "hard_stop":
            return cap
        return f"revisão de risco obrigatória e {cap} no próximo rebalanceamento"
    if stage == "stop_out":
        return (f"reduzir o gross a {fmt_pct(d.stop_out_gross)} do NAV e revisão completa do "
                "processo")
    if stage == "hard_stop":
        return f"cortar o gross para {fmt_pct(d.degross_multiplier)} do atual"
    return ("revisão de risco obrigatória e corte do gross para "
            f"{fmt_pct(d.soft_degross_multiplier)} do atual")


def risk_alerts(cfg: FundConfig, risk: DailyRisk, has_positions: bool = True) -> list[str]:
    """Alertas de mandato sobre o risco do dia: banda de vol ex-ante, net, beta e escada de
    drawdown (com a ação exigida)."""
    rk, dd_cfg = cfg.risk, cfg.drawdown
    out: list[str] = []
    if has_positions and risk.ex_ante_vol is not None:
        v = risk.ex_ante_vol
        if v < rk.vol_band_min:
            out.append(f"Vol ex-ante {fmt_pct(v)} abaixo da banda ({fmt_pct(rk.vol_band_min)}–"
                       f"{fmt_pct(rk.vol_band_max)}): subutilização do orçamento de risco.")
        elif v > rk.vol_band_max:
            out.append(f"Vol ex-ante {fmt_pct(v)} acima da banda ({fmt_pct(rk.vol_band_min)}–"
                       f"{fmt_pct(rk.vol_band_max)}): reduzir risco no próximo rebalanceamento.")
    elif has_positions:
        out.append("Vol ex-ante indisponível (modelo de risco ausente): banda não verificada.")
    if abs(risk.net) > rk.net_exposure_max_abs:
        out.append(f"Exposição líquida {fmt_pct(risk.net, signed=True)} fora do limite "
                   f"±{fmt_pct(rk.net_exposure_max_abs)} (net neutral).")
    if risk.beta is not None and abs(risk.beta) > rk.beta_max_abs:
        out.append(f"Beta previsto {fmt_num(risk.beta, 3, signed=True)} fora do limite "
                   f"±{fmt_num(rk.beta_max_abs, 3)}.")
    dd = risk.drawdown
    if dd <= dd_cfg.stop_out:
        out.append(f"STOP-OUT: drawdown {fmt_pct(dd)} atingiu {fmt_pct(dd_cfg.stop_out)} — "
                   f"{drawdown_stage_action('stop_out', cfg)}.")
    elif dd <= dd_cfg.hard_stop:
        out.append(f"HARD STOP: drawdown {fmt_pct(dd)} atingiu {fmt_pct(dd_cfg.hard_stop)} — "
                   f"{drawdown_stage_action('hard_stop', cfg)}.")
    elif dd <= dd_cfg.soft_stop:
        out.append(f"SOFT STOP: drawdown {fmt_pct(dd)} atingiu {fmt_pct(dd_cfg.soft_stop)} — "
                   f"{drawdown_stage_action('soft_stop', cfg)}.")
    return out


def short_entry_prices(history: Iterable[DailyRecord],
                       current: Mapping[str, tuple[float, float]],
                       max_records: int = ENTRY_LOOKBACK_RECORDS) -> dict[str, float]:
    """Preço médio de entrada (moeda local) de cada short atual.

    ``history`` vem do registro mais recente para o mais antigo (sem o dia corrente);
    ``current`` mapeia ticker → (ações assinadas, preço local de hoje). O episódio de short é a
    sequência contínua de registros com o ticker vendido; aumentos de posição recompõem o preço
    médio pelo fechamento do dia do aumento; reduções o mantêm.
    """
    open_ = {t for t, (sh, px) in current.items() if sh < 0 and px > 0}
    spells: dict[str, list[tuple[float, float]]] = {t: [] for t in open_}
    for k, rec in enumerate(history):
        if not open_ or k >= max_records:
            break
        pos = {p.ticker: p for p in rec.positions if p.market_value_usd < 0}
        for t in list(open_):
            p = pos.get(t)
            if p is None or p.shares is None or p.price_local is None or not p.price_local > 0:
                open_.discard(t)
                continue
            spells[t].append((float(p.shares), float(p.price_local)))
    out: dict[str, float] = {}
    for t, seq_rev in spells.items():
        seq = list(reversed(seq_rev)) + [current[t]]
        avg = seq[0][1]
        held = abs(seq[0][0])
        for sh, px in seq[1:]:
            a = abs(sh)
            if a > held + 1e-9 and a > 0:
                avg = (held * avg + (a - held) * px) / a
            held = a
        out[t] = float(avg)
    return out


# ==========================================================
# Persistência compatível com o livro (decisões autônomas e sombra)
# ==========================================================

def _verify_autonomous(proposal: Proposal, decision: Decision, cfg: FundConfig,
                       snapshot_hash_now: str | None, config_hash: str | None = None) -> None:
    """``verify_autonomous_decision`` contra o mandato atual (ou ``config_hash`` informado)."""
    if decision.mode != DecisionMode.AUTONOMOUS:
        raise ValueError("Decisão não é autônoma.")
    if decision.decision != DecisionType.APPROVE:
        raise ValueError("Somente decisões APPROVE são executadas.")
    ok, reasons = verify_autonomous_decision(
        decision, proposal, snapshot_hash_now or proposal.snapshot_hash,
        config_hash or cfg.config_hash(), proposal.research_hash)
    if not ok:
        raise ValueError("Decisão autônoma inválida: " + " ".join(reasons))


def save_decided_proposal(book: Book, proposal: Proposal, decision: Decision, cfg: FundConfig,
                          *, snapshot_hash_now: str | None = None, dry_run: bool = False) -> None:
    """Garante a proposta e a decisão gravadas no livro (``Book.save_proposal`` /
    ``Book.save_decision``), de forma idempotente.

    Decisões autônomas são conferidas antes com ``verify_autonomous_decision`` contra o mandato
    atual. Conteúdo divergente do já gravado é recusado. ``dry_run`` só faz as checagens.
    """
    if decision.mode == DecisionMode.AUTONOMOUS:
        _verify_autonomous(proposal, decision, cfg, snapshot_hash_now)
    week = proposal.week
    same = [p for p in book.list_proposals(week) if p.proposal_id == proposal.proposal_id]
    if same:
        if same[0].proposal_hash() != proposal.proposal_hash():
            raise ValueError(f"Proposta {proposal.proposal_id} já gravada com conteúdo diferente.")
        version = same[0].version
    else:
        if book.week_dir(week).joinpath("booked.json").exists():
            raise ValueError(f"A semana {week} já foi efetivada; não aceita nova proposta.")
        if proposal.version != book.next_version(week):
            raise ValueError(f"Versão {proposal.version} fora de sequência na semana {week} "
                             f"(próxima: {book.next_version(week)}).")
        version = proposal.version
    existing = book.load_decision(week, version) if same else None
    if existing is not None and existing.approval_hash != decision.approval_hash:
        raise FileExistsError(f"A proposta v{version} da semana {week} já tem outra decisão.")
    if dry_run:
        return
    if not same:
        book.save_proposal(proposal)
    if existing is None:
        book.save_decision(decision)


def book_execution(book: Book, entry: BookEntry, proposal: Proposal, decision: Decision,
                   cfg: FundConfig, *, snapshot_hash_now: str | None = None,
                   actor: str = DAILY_ACTOR, dry_run: bool = False) -> Path:
    """Efetiva no livro a carteira executada no fechamento (``<semana>/booked.json``).

    Grava proposta e decisão se ausentes (:func:`save_decided_proposal`) e chama
    ``Book.save_booked`` (que revalida a aprovação contra os hashes atuais, a carteira contra a
    aprovada, a cronologia e o KILL_SWITCH, e registra ``BOOKED``). Decisões autônomas passam
    antes por ``verify_autonomous_decision``.
    """
    if entry.week != proposal.week or entry.proposal_id != proposal.proposal_id:
        raise ValueError("BookEntry não corresponde à proposta decidida.")
    if entry.approval_hash != decision.approval_hash:
        raise ValueError("approval_hash do booking difere do da decisão.")
    path = book.week_dir(entry.week) / "booked.json"
    if path.exists():
        raise FileExistsError(f"A semana {entry.week} já foi efetivada (imutável).")
    save_decided_proposal(book, proposal, decision, cfg, snapshot_hash_now=snapshot_hash_now,
                          dry_run=dry_run)
    if dry_run:
        return path
    return book.save_booked(entry, snapshot_hash_now or proposal.snapshot_hash, cfg.config_hash(),
                            decision.research_hash, actor=actor)


class ShadowBook:
    """Propostas e efetivações da carteira-sombra só-quant (dentro da pasta da série sombra).

    ``proposals/<semana>.json`` e ``booked/<semana>.json``, imutáveis, com eventos
    ``SHADOW_PROPOSAL_SAVED`` e ``BOOKED_SHADOW`` na trilha da série.
    """

    def __init__(self, track: TrackRecord) -> None:
        self.track = track
        self.root = track.root
        self.audit = track.audit

    def proposal_path(self, week: date) -> Path:
        return self.root / "proposals" / f"{week.isoformat()}.json"

    def booked_path(self, week: date) -> Path:
        return self.root / "booked" / f"{week.isoformat()}.json"

    def weeks(self) -> list[date]:
        d = self.root / "proposals"
        if not d.is_dir():
            return []
        out = []
        for p in d.glob("*.json"):
            try:
                out.append(date.fromisoformat(p.stem))
            except ValueError:
                continue
        return sorted(out)

    def _audited(self, event_type: str) -> set[str]:
        return {ev.payload_hash for ev in self.audit.events() if ev.event_type == event_type}

    def _audited_in_week(self, event_type: str, week: date) -> set[str]:
        return {ev.payload_hash for ev in self.audit.events()
                if ev.event_type == event_type and ev.week == week}

    def load_proposal(self, week: date) -> Proposal | None:
        """Proposta-sombra da semana, conferida contra a trilha (``ValueError`` se alterada ou
        copiada de outra semana)."""
        path = self.proposal_path(week)
        if not path.exists():
            return None
        proposal = Proposal.model_validate_json(path.read_text(encoding="utf-8"))
        if proposal.week != week:
            raise ValueError(f"Proposta-sombra em {path.name} é da semana {proposal.week} "
                             "(arquivo copiado/renomeado).")
        if (sha256_obj(proposal.proposal_hash())
                not in self._audited_in_week(SHADOW_PROPOSAL_EVENT, week)):
            raise ValueError(f"Proposta-sombra de {week} não confere com a trilha de auditoria.")
        return proposal

    def load_booked(self, week: date) -> BookEntry | None:
        """Efetivação-sombra da semana, conferida contra a trilha (``ValueError`` se alterada ou
        copiada de outra semana)."""
        path = self.booked_path(week)
        if not path.exists():
            return None
        entry = BookEntry.model_validate_json(path.read_text(encoding="utf-8"))
        if entry.week != week:
            raise ValueError(f"Efetivação-sombra em {path.name} é da semana {entry.week} "
                             "(arquivo copiado/renomeado).")
        if sha256_obj(entry) not in self._audited_in_week(SHADOW_BOOKED_EVENT, week):
            raise ValueError(f"Efetivação-sombra de {week} não confere com a trilha de auditoria.")
        return entry

    def save_proposal(self, proposal: Proposal) -> Path:
        """Grava a proposta-sombra da semana (idempotente para o mesmo conteúdo)."""
        path = self.proposal_path(proposal.week)
        existing = (Proposal.model_validate_json(path.read_text(encoding="utf-8"))
                    if path.exists() else None)
        if existing is not None:
            if existing.proposal_hash() != proposal.proposal_hash():
                raise FileExistsError(f"Proposta-sombra da semana {proposal.week} já existe com "
                                      "conteúdo diferente (imutável).")
            return path
        write_exclusive(path, dump_json(proposal))
        self.audit.append(SHADOW_PROPOSAL_EVENT, DAILY_ACTOR, proposal.proposal_hash(),
                          summary=f"Proposta-sombra só-quant {proposal.proposal_id}.",
                          week=proposal.week)
        return path

    def save_booked(self, entry: BookEntry) -> Path:
        path = self.booked_path(entry.week)
        write_exclusive(path, dump_json(entry))
        self.audit.append(SHADOW_BOOKED_EVENT, DAILY_ACTOR, entry,
                          summary=(f"Carteira-sombra efetivada (MOC): {entry.proposal_id}, "
                                   f"{len(entry.positions)} posições."),
                          week=entry.week)
        return path


def book_shadow_proposal(book: Book, week: date) -> Proposal | None:
    """Proposta-sombra só-quant gravada pelo pipeline semanal em ``<livro>/<semana>/`` (arquivo
    :data:`BOOK_SHADOW_FILE`, evento ``SHADOW_QUANT`` com ``{"sha256": <sha256 do arquivo>}``).

    ``None`` se não houver arquivo; ``ValueError`` se o arquivo não conferir com a trilha ou for
    de outra semana (nunca executa uma sombra alterada fora do pipeline).
    """
    path = book.week_dir(week) / BOOK_SHADOW_FILE
    if not path.exists():
        return None
    payload = sha256_obj({"sha256": sha256_file(path)})
    if not any(ev.event_type == BOOK_SHADOW_EVENT and ev.week == week
               and ev.payload_hash == payload for ev in book.audit.events()):
        raise ValueError(f"{BOOK_SHADOW_FILE} da semana {week} não confere com a trilha de "
                         "auditoria.")
    proposal = Proposal.model_validate_json(path.read_text(encoding="utf-8"))
    if proposal.week != week:
        raise ValueError(f"{BOOK_SHADOW_FILE} da semana {week} contém a proposta de "
                         f"{proposal.week}.")
    return proposal


# ==========================================================
# Estruturas internas
# ==========================================================

@dataclass
class _Line:
    issuer_id: str
    ticker: str
    currency: str
    shares: float | None
    mv_start: float
    pnl: float
    ret: float | None
    repriced: bool
    mv_end: float
    price_local: float | None
    price_usd: float | None


@dataclass
class _Marked:
    nav_start: float
    days: int
    lines: list[_Line]
    equity: float
    financing: float
    borrow: float
    alerts: list[str]

    @property
    def nav_pre(self) -> float:
        return self.nav_start + self.equity + self.financing + self.borrow


@dataclass
class _Exec:
    issuer_id: str
    ticker: str
    currency: str
    shares: int
    price_local: float
    fx: float
    value: float | None = None
    """Valor de mercado já marcado (linha detida sem negociação no dia: mantém a marcação)."""
    mic: str | None = None
    traded: int = 0
    """Ações negociadas no fechamento (com sinal; execução com capacidade)."""

    @property
    def mv(self) -> float:
        if self.value is not None:
            return self.value
        return self.shares * self.price_local * self.fx


@dataclass
class _Plan:
    """Execução no fechamento: proposta decidida (a efetivar) ou efetivação já gravada."""

    week: date
    proposal: Proposal | None
    decision: Decision | None
    entry: BookEntry | None
    hold: bool
    approval_hash: str
    proposal_id: str
    source: str
    persist: Callable[[BookEntry], object] | None = None
    preflight: Callable[[BookEntry], object] | None = None
    notes: list[str] = field(default_factory=list)

    def targets(self) -> list[tuple[str, str, float, str]]:
        if self.entry is not None:
            return [(p.issuer_id, p.ticker, p.weight, p.currency)
                    for p in self.entry.positions if p.weight != 0]
        assert self.proposal is not None
        return [(p.issuer_id, p.execution_ticker, p.weight, p.currency)
                for p in self.proposal.positions if p.weight != 0]


@dataclass
class _SideResult:
    record: DailyRecord
    entry: BookEntry | None
    commit: Callable[[], None] | None
    diagnostic: dict | None = None


class _MainSide:
    label = "CDP"
    is_shadow = False

    def __init__(self, cfg: FundConfig, book: Book, track: TrackRecord) -> None:
        self.cfg, self.book, self.track = cfg, book, track
        self.fund_name = cfg.fund.name
        self.track_type = cfg.fund.track_record_type

    def load_entry(self, week: date) -> BookEntry | None:
        return self.book.load_booked(week)

    def weeks_before(self, week: date) -> list[date]:
        return [w for w in self.book.list_weeks() if w < week]

    def proposal_for(self, entry: BookEntry) -> Proposal | None:
        for p in self.book.list_proposals(entry.week):
            if p.proposal_id == entry.proposal_id:
                return p
        return None


class _ShadowSide:
    label = "sombra"
    is_shadow = True

    def __init__(self, cfg: FundConfig, track: TrackRecord) -> None:
        self.cfg, self.track = cfg, track
        self.store = ShadowBook(track)
        self.fund_name = f"{cfg.fund.name} — {SHADOW_LABEL}"
        self.track_type = (f"{cfg.fund.track_record_type} — carteira-sombra só-quant "
                           "(contrafactual, sem decisão)")

    def load_entry(self, week: date) -> BookEntry | None:
        return self.store.load_booked(week)

    def weeks_before(self, week: date) -> list[date]:
        return [w for w in self.store.weeks() if w < week]

    def proposal_for(self, entry: BookEntry) -> Proposal | None:
        p = self.store.load_proposal(entry.week)
        return p if p is not None and p.proposal_id == entry.proposal_id else None


# ==========================================================
# Rotina diária
# ==========================================================

class DailyRunner:
    """Executa o fechamento diário: MOC da decisão da semana, MTM, risco, atribuição e alertas.

    ``store`` é qualquer objeto com ``load(as_of) -> MarketData`` sem look-ahead (ex.:
    ``MarketStore``); ``book`` é o livro semanal; ``track`` a série do CDP e ``shadow_track``
    (opcional) a série da carteira-sombra só-quant.
    """

    def __init__(self, cfg: FundConfig, store: MarketSource, book: Book, track: TrackRecord,
                 *, shadow_track: TrackRecord | None = None, actor: str = DAILY_ACTOR) -> None:
        if (shadow_track is not None and shadow_track.audit_event == track.audit_event
                and shadow_track.audit.path.resolve() == track.audit.path.resolve()):
            raise ValueError("Track record e carteira-sombra compartilham a trilha com o mesmo "
                             f"tipo de evento ({track.audit_event}): verify() acusaria órfãos.")
        self.cfg = cfg
        self.store = store
        self.book = book
        self.track = track
        self.actor = actor
        self.main = _MainSide(cfg, book, track)
        self.shadow = _ShadowSide(cfg, shadow_track) if shadow_track is not None else None
        self._models: dict[date, RiskModel | None] = {}
        self._model_notes: dict[date, str] = {}
        self._md_pregao: tuple[date, MarketData] | None = None
        if cfg.execution is not None and getattr(book, "mercado", None) is None:
            # O livro confere cada efetivação contra a execução esperada no pregão (capacidade
            # pelo volume realizado, mercado elegível, corte MOC, banda).
            book.mercado = self._mercado_conferencia

    @classmethod
    def from_root(cls, cfg: FundConfig, store: MarketSource, root: Path | str = "book",
                  *, with_shadow: bool = True) -> DailyRunner:
        """Layout padrão: ``<root>/`` (livro), ``<root>/track_record`` e
        ``<root>/track_record_shadow``."""
        root = Path(root)
        book = Book(root, cfg)
        track = TrackRecord(root / "track_record")
        shadow = (TrackRecord(root / "track_record_shadow", audit_event=SHADOW_RECORD_EVENT)
                  if with_shadow else None)  # o mesmo tipo seria inferido da pasta
        return cls(cfg, store, book, track, shadow_track=shadow)

    @property
    def shadow_book(self) -> ShadowBook | None:
        return self.shadow.store if self.shadow is not None else None

    def save_shadow_proposal(self, proposal: Proposal) -> Path:
        """Registra a proposta-sombra só-quant da semana para execução no fechamento."""
        if self.shadow is None:
            raise ValueError("Rotina sem série-sombra configurada.")
        return self.shadow.store.save_proposal(proposal)

    # ------------------------------------------------------------------ API
    def run(self, session_date: date, pending: PendingExecution | None = None) -> DailyRecord:
        """Registro diário do CDP em ``session_date`` (grava também a sombra, se houver)."""
        return self.run_session(session_date, pending).record

    def run_session(self, session_date: date,
                    pending: PendingExecution | None = None) -> DailyRunResult:
        """Registro do dia (e da sombra). Decisão explícita inválida ⇒ ``ValueError``; decisão
        descoberta no livro inválida ou execução recusada (livro/KILL_SWITCH/preço) com carteira
        vigente ⇒ o dia é registrado com a carteira anterior e alerta (sem negociação)."""
        prev = self.track.last()
        if prev is not None and session_date <= prev.date:
            kind = "já registrado" if session_date == prev.date else "anterior ao último registro"
            raise ValueError(f"Pregão {session_date} {kind} ({prev.date}).")
        _check_track_tail(self.track, prev)
        md = self._session_market(session_date)
        refusals: list[str] = []
        plan = self._main_plan(session_date, prev, pending, refusals)
        retomada = self._lapse_at(session_date) if plan is None else None
        if retomada is not None:
            # Recusa já registrada neste fechamento (execução anterior interrompida antes do
            # registro do dia): o dia é registrado com a recusa, sem tentar efetivar de novo.
            refusals = [r for r in refusals if "caducou" not in r] + [
                _lapse_alert(retomada, inaugural=prev is None)]
        if prev is None and plan is None and retomada is None:
            raise NoBookError(
                f"Sem carteira efetivada executável em {session_date}: o track record começa no "
                "fechamento do pregão de efetivação da primeira carteira aprovada."
                + (" " + " ".join(refusals) if refusals else ""))
        ctx = self.context(session_date, md, prev)

        shadow_res: _SideResult | None = None
        shadow_existing: DailyRecord | None = None
        shadow_alert: str | None = None
        if self.shadow is not None:
            try:
                shadow_res, shadow_existing = self._run_shadow(ctx, pending)
            except (ValueError, KeyError, FileExistsError) as exc:
                shadow_alert = ("Carteira-sombra só-quant não processada: "
                                f"{clean_text(exc, 600)}")
        shadow_hash = (shadow_res.record.record_hash if shadow_res is not None
                       else shadow_existing.record_hash if shadow_existing is not None else None)

        extra = refusals + ([shadow_alert] if shadow_alert else [])
        hashes = {"shadow_record": shadow_hash} if shadow_hash else None
        lapsed: dict[str, Any] | None = None

        # Gravação: primeiro a efetivação do CDP no livro (o passo que o livro pode recusar, ex.:
        # KILL_SWITCH); depois a sombra (efetivação + registro) e por fim o registro do CDP, que
        # já carrega o hash do registro-sombra. Uma nova execução retoma de onde parou.
        try:
            main_res = self._compute_side(self.main, ctx, prev, plan, extra_alerts=extra,
                                          extra_hashes=hashes)
            if main_res.commit is not None:
                main_res.commit()
        except ExecutionRefused as exc:
            if plan is None:
                raise
            kill = self.book.kill_switch_active()
            if prev is None and not kill:
                # Carteira inaugural recusada por dado (preço/câmbio ausente): nada é negociado
                # nem registrado; uma nova execução do mesmo fechamento tenta de novo.
                raise NoBookError(
                    f"Execução da carteira inaugural (semana {plan.week}) RECUSADA no fechamento "
                    f"de {session_date}: {clean_text(exc, 600)} O fundo segue sem carteira "
                    "(zerado, sem negociação) até a próxima data de montagem.") from exc
            if kill:
                # Kill switch no leilão do dia de montagem: a ordem não foi executada e a decisão
                # CADUCA (REGRA_CADUCIDADE) — o dia é registrado com a recusa e a decisão nunca é
                # efetivada depois, nem quando um humano desligar o kill switch.
                lapsed = self.book.registrar_efetivacao_recusada(
                    plan.week, session_date, clean_text(exc, 600), plan.proposal_id,
                    plan.approval_hash, actor=self.actor)
                refused = _lapse_alert(lapsed, inaugural=prev is None)
            else:
                refused = (f"Execução da decisão da semana {plan.week} RECUSADA no fechamento de "
                           f"{session_date}: {clean_text(exc, 600)} Carteira anterior mantida "
                           "(sem negociação).")
            main_res = self._compute_side(self.main, ctx, prev, None,
                                          extra_alerts=extra + [refused], extra_hashes=hashes)
            plan = None
        if shadow_res is not None and self.shadow is not None:
            if shadow_res.commit is not None:
                shadow_res.commit()
            self._append_side(self.shadow.track, shadow_res)
        self._append_side(self.track, main_res)
        lapsed = lapsed or retomada
        return DailyRunResult(
            record=main_res.record,
            shadow=shadow_res.record if shadow_res is not None else shadow_existing,
            booked=main_res.entry if plan is not None else None,
            shadow_booked=shadow_res.entry if shadow_res is not None and shadow_res.commit
            else None, lapsed=lapsed)

    @staticmethod
    def _append_side(track: TrackRecord, result: _SideResult) -> None:
        from .risco_diario import append

        if result.diagnostic is None:
            track.append(result.record)
        else:
            append(track, result.record, result.diagnostic)

    def backfill(self, start: date, end: date,
                 pending: Mapping[date, PendingExecution] | Iterable[PendingExecution] | None
                 = None) -> list[DailyRecord]:
        """Roda cada pregão de ``[start, end]`` em ordem; pula não-pregões, dias já registrados e
        pregões anteriores à primeira efetivação. ``pending``: decisões a executar (por semana)."""
        if end < start:
            raise ValueError("Fim do período anterior ao início.")
        if pending is None:
            pend: list[PendingExecution] = []
        elif isinstance(pending, Mapping):
            pend = list(pending.values())
        else:
            pend = list(pending)
        md_end = self.store.load(as_of=end)
        out: list[DailyRecord] = []
        last = self.track.last()
        for s in session_dates(md_end, start, end):
            if last is not None and s <= last.date:
                continue
            live = last.live_book_week if last is not None else None
            close = decision_cutoff(s, self.cfg)
            cands = [p for p in pend if executable_in(p.week, s, self.cfg)
                     and (live is None or p.week > live) and p.decision.decided_at <= close]
            p = max(cands, key=lambda x: x.week) if cands else None
            try:
                rec = self.run(s, pending=p)
            except NoSessionError:
                continue
            except NoBookError:
                if last is None:
                    continue
                raise
            out.append(rec)
            last = rec
        return out

    def execute_decision(self, session_date: date, proposal: Proposal, decision: Decision,
                         md: MarketData | None = None, *,
                         snapshot_hash_now: str | None = None) -> BookEntry:
        """Executa (efetiva) a proposta decidida no fechamento de ``session_date``.

        Nocional-alvo = peso × NAV antes dos custos (P&L do dia da carteira antiga incluído);
        ações pelo fechamento local e câmbio do dia. Persiste no livro via :func:`book_execution`
        (proposta, decisão e ``Book.save_booked``) e devolve o ``BookEntry``. Idempotente quando a
        mesma decisão já foi efetivada. Recusa do livro ou execução impossível ⇒
        :class:`ExecutionRefused`. O registro diário do pregão é gravado por :meth:`run`.
        """
        existing = self.book.load_booked(proposal.week)
        if existing is not None:
            if (existing.proposal_id == proposal.proposal_id
                    and existing.approval_hash == decision.approval_hash):
                return existing
            raise FileExistsError(f"A semana {proposal.week} já foi efetivada com outra decisão.")
        prev = self.track.last()
        if prev is not None and session_date <= prev.date:
            raise ValueError(f"Pregão {session_date} já registrado ({prev.date}).")
        _check_track_tail(self.track, prev)
        md = self._session_market(session_date, md)
        pending = PendingExecution(proposal, decision, snapshot_hash_now=snapshot_hash_now)
        plan = self._plan_from_pending(session_date, prev, pending)
        ctx = self.context(session_date, md, prev, need_models=False)
        if plan.entry is not None:
            return plan.entry
        _, _, ref_prop = self._live(self.main, prev, [])
        marked = self._mark(ctx, prev, ref_prop)
        nav_pre = marked.nav_pre
        if plan.hold:
            entry = self._build_hold_entry(ctx, plan, nav_pre, marked)
        else:
            try:
                execs, _ = self._size(ctx, plan, marked, nav_pre)
            except ValueError as exc:
                raise ExecutionRefused(str(exc)) from exc
            cost, _ = self._costs(ctx, marked.lines, execs, nav_pre, plan)
            entry = self._build_entry(ctx, plan, execs, nav_pre, cost)
        assert plan.persist is not None
        _guarded(plan.preflight, entry)
        _guarded(plan.persist, entry)
        return entry

    def verify_all(self) -> tuple[bool, list[str]]:
        """Integridade do track record (e da sombra) e do livro (``Book.verify_integrity``)."""
        problems: list[str] = []
        _, msgs = self.track.verify()
        problems += [f"[track record] {m}" for m in msgs]
        if self.shadow is not None:
            _, msgs_s = self.shadow.track.verify()
            problems += [f"[sombra] {m}" for m in msgs_s]
        _, msgs_b = self.book.verify_integrity()
        problems += [f"[livro] {m}" for m in msgs_b]
        from .risco_diario import verify

        for tr in [self.track] + ([self.shadow.track] if self.shadow else []):
            problems += [f"[risco diário] {m}" for m in verify(
                tr, market_loader=self.store.load, market_root=getattr(self.store, "root", None))]
        from types import SimpleNamespace

        from .contrato_custos import verify as verify_costs

        facade = SimpleNamespace(cfg=self.cfg, book=self.book, store=self.store,
                                 track=lambda shadow=False: self.shadow.track if shadow else self.track)
        problems += [f"[custos da execução] {m}" for m in verify_costs(
            facade, include_shadow=self.shadow is not None)]
        return (not problems, problems)

    # ------------------------------------------------------------------ contexto
    def _session_market(self, session_date: date, md: MarketData | None = None) -> MarketData:
        """Dados de mercado da sessão sem look-ahead: cortados em ``session_date`` (mesmo que a
        fonte ou o chamador entregue mais), com fechamento OFICIAL (barra intradiária provisória
        é recusada) e com preço de fechamento no dia (senão ``NoSessionError``)."""
        md = md if md is not None else self.store.load(as_of=session_date)
        md = md.truncate(session_date)
        if session_date in set(md.manifest.provisional_dates):
            raise ValueError(f"{session_date}: barra intradiária provisória — a marcação e a "
                             "execução MOC exigem o fechamento oficial do pregão.")
        if not session_has_prices(md, session_date):
            raise NoSessionError(f"{session_date}: sem pregão (sem preços de fechamento no "
                                 "armazenamento de mercado).")
        self._md_pregao = (session_date, md)
        return md

    def _mercado_conferencia(self, session_date: date) -> MarketData:
        """Dados do pregão para a conferência da efetivação no livro (reaproveita os do
        próprio pregão quando já carregados)."""
        if self._md_pregao is not None and self._md_pregao[0] == session_date:
            return self._md_pregao[1]
        return self.store.load(as_of=session_date).truncate(session_date)

    def context(self, session_date: date, md: MarketData | None = None,
                prev: DailyRecord | None = None, *, need_models: bool = True) -> DailyContext:
        """Monta os insumos da sessão (sem look-ahead); ``NoSessionError`` se não houve pregão.

        O modelo da sessão anterior é estimado com os dados carregados NA sessão anterior
        (``store.load(prev.date)``), de modo que o registro não depende do caminho (rotina dia a
        dia × backfill) nem de retratos atualizados depois (fundamentos, short interest).
        """
        md = self._session_market(session_date, md)
        panel = build_asset_panel(md, self.cfg, as_of=session_date)
        ctx = DailyContext(date=session_date, md=md, panel=panel, model=None,
                           book_entry=None, prev=prev)
        if prev is not None and prev.live_book_week is not None:
            try:
                ctx.book_entry = self.main.load_entry(prev.live_book_week)
            except ValueError as exc:
                ctx.notes.append(f"Efetivação vigente inválida no livro: {exc}")
        if need_models:
            ctx.model = self._model_at(session_date, md, panel)
            if ctx.model is not None:
                ctx.risk_model = apply_event_windows(ctx.model, panel.assets["country"], self.cfg,
                                                     session_date)
                for w in ctx.risk_model.meta.get("event_windows", []):
                    ctx.notes.append(f"Janela de evento ativa: {w['name']} (vol × "
                                     f"{fmt_num(float(w['multiplier']), 2)} em {w['country']}).")
            elif session_date in self._model_notes:
                ctx.notes.append(self._model_notes[session_date])
            if prev is not None:
                ctx.model_prev = self._model_at(prev.date)
        return ctx

    def _model_at(self, d: date, md: MarketData | None = None, panel: AssetPanel | None = None
                  ) -> RiskModel | None:
        """Modelo de risco estimado com os dados da sessão ``d`` (cacheado por data; falha ⇒
        ``None`` anotado). Sem ``md``, carrega ``store.load(d)`` — os mesmos dados que a rotina
        daquela sessão usou."""
        if d in self._models:
            return self._models[d]
        from .risco_diario import MARKER, load, restore

        historical = self.track.get(d)
        if historical is not None and MARKER in historical.input_hashes:
            diagnostic = load(self.track, historical)
            archived = diagnostic["models"]["base"]
            model = restore(archived) if archived else None
            self._models[d] = model
            return model
        model: RiskModel | None = None
        if md is None:
            md = self.store.load(as_of=d)
        md = md.truncate(d)
        try:
            p = panel if panel is not None else build_asset_panel(md, self.cfg, as_of=d)
            model = estimate_risk_model(p, self.cfg, md, as_of=d, issuers=p.eligible)
            if self.cfg.risk_model.macro_factors:
                from ..risk.macro import augment_with_macro

                model = augment_with_macro(model, md, self.cfg, p)
        except (ValueError, KeyError, IndexError, np.linalg.LinAlgError) as exc:
            self._model_notes[d] = f"Modelo de risco indisponível em {d}: {exc}"
        self._models[d] = model
        for old in sorted(self._models)[:-4]:
            self._models.pop(old, None)
        return model

    # ------------------------------------------------------------------ planos de execução
    def _verify_decision(self, session: date, proposal: Proposal, decision: Decision | None,
                         snapshot_hash_now: str | None, *, booked: bool = False) -> list[str]:
        """Confere a decisão para execução no fechamento de ``session`` e devolve notas.

        A executar (``booked=False``): contra o mandato ATUAL e o snapshot informado. Já
        efetivada no livro (``booked=True``): o livro validou os hashes no booking, então aqui se
        confere a integridade da decisão contra os PRÓPRIOS hashes (mudança posterior do mandato
        não desfaz uma execução já ocorrida; vira nota/alerta).
        """
        if decision is None:
            raise ValueError(f"Proposta {proposal.proposal_id} sem decisão gravada.")
        if decision.decision != DecisionType.APPROVE:
            raise ValueError(f"Proposta {proposal.proposal_id} não aprovada ({decision.decision}).")
        if decision.proposal_id != proposal.proposal_id or decision.week != proposal.week:
            raise ValueError("A decisão não pertence à proposta informada.")
        close = decision_cutoff(session, self.cfg)
        if decision.decided_at > close:
            if self.cfg.execution is not None:
                raise ValueError(f"Decisão gravada após o corte de ordens do fechamento de "
                                 f"{session} ({decision.decided_at.isoformat()}): não executa "
                                 "neste fechamento.")
            raise ValueError(f"Decisão gravada após o fechamento de {session} "
                             f"({decision.decided_at.isoformat()}): executa no pregão seguinte.")
        snap = decision.snapshot_hash if booked else (snapshot_hash_now or proposal.snapshot_hash)
        cfg_hash = decision.config_hash if booked else self.cfg.config_hash()
        if decision.mode == DecisionMode.AUTONOMOUS:
            _verify_autonomous(proposal, decision, self.cfg, snap, cfg_hash)
        else:
            ok, reasons = verify_decision(decision, proposal, snap, cfg_hash,
                                          decision.research_hash)
            if not ok:
                raise ValueError("Aprovação inválida para execução: " + " ".join(reasons))
        if booked and decision.config_hash != self.cfg.config_hash():
            return [f"Mandato atual difere do vigente na decisão da semana {proposal.week} "
                    "(efetivação já gravada no livro adotada sem revalidar contra o novo "
                    "mandato)."]
        return []

    def _check_week_window(self, session: date, week: date, prev: DailyRecord | None) -> None:
        if not executable_in(week, session, self.cfg):
            raise ValueError(f"Decisão da semana {week} não é executável em {session} "
                             "(somente em pregões da própria semana).")
        if prev is not None and prev.live_book_week is not None and week <= prev.live_book_week:
            raise ValueError(f"A semana {week} não é posterior à carteira vigente "
                             f"({prev.live_book_week}).")

    def _lapse_at(self, session: date) -> dict[str, Any] | None:
        """Registro de caducidade gravado no fechamento de ``session`` (ou ``None``)."""
        for w in self.book.list_weeks():
            if w > session:
                continue
            lapsed = self.book.efetivacao_recusada(w)
            if lapsed is not None and lapsed.get("sessao") == session.isoformat():
                return lapsed
        return None

    def _check_not_lapsed(self, week: date) -> None:
        """Decisão caducada (efetivação recusada no leilão do dia de montagem) nunca executa."""
        lapsed = self.book.efetivacao_recusada(week)
        if lapsed is not None:
            raise ValueError(f"A decisão da semana {week} caducou: efetivação recusada no "
                             f"fechamento de {lapsed.get('sessao')} (sem efetivação "
                             "retroativa; a próxima data de montagem decide de novo).")

    def _plan_from_pending(self, session: date, prev: DailyRecord | None,
                           pending: PendingExecution) -> _Plan:
        proposal, decision = pending.proposal, pending.decision
        self._check_week_window(session, proposal.week, prev)
        self._check_not_lapsed(proposal.week)
        existing = self.book.load_booked(proposal.week)
        if existing is not None:
            if (existing.proposal_id != proposal.proposal_id
                    or existing.approval_hash != decision.approval_hash):
                raise FileExistsError(f"A semana {proposal.week} já foi efetivada com outra "
                                      "decisão.")
            notes = self._verify_decision(session, proposal, decision, pending.snapshot_hash_now,
                                          booked=True)
            plan = self._adopt_plan(existing, proposal, decision, "livro")
            plan.notes.extend(notes)
            return plan
        self._verify_decision(session, proposal, decision, pending.snapshot_hash_now)
        return self._execute_plan(proposal, decision, pending.snapshot_hash_now, "decisão")

    def _execute_plan(self, proposal: Proposal, decision: Decision,
                      snapshot_hash_now: str | None, source: str) -> _Plan:
        cfg, book, actor = self.cfg, self.book, self.actor

        def preflight(entry: BookEntry) -> None:
            book_execution(book, entry, proposal, decision, cfg,
                           snapshot_hash_now=snapshot_hash_now, dry_run=True)

        def persist(entry: BookEntry) -> None:
            book_execution(book, entry, proposal, decision, cfg,
                           snapshot_hash_now=snapshot_hash_now, actor=actor)

        return _Plan(week=proposal.week, proposal=proposal, decision=decision, entry=None,
                     hold=proposal.optimizer.status == HOLD_STATUS,
                     approval_hash=decision.approval_hash, proposal_id=proposal.proposal_id,
                     source=source, persist=persist, preflight=preflight)

    @staticmethod
    def _adopt_plan(entry: BookEntry, proposal: Proposal | None, decision: Decision | None,
                    source: str) -> _Plan:
        hold = proposal is not None and proposal.optimizer.status == HOLD_STATUS
        return _Plan(week=entry.week, proposal=proposal, decision=decision, entry=entry,
                     hold=hold, approval_hash=entry.approval_hash, proposal_id=entry.proposal_id,
                     source=source)

    def _main_plan(self, session: date, prev: DailyRecord | None,
                   pending: PendingExecution | None,
                   refusals: list[str] | None = None) -> _Plan | None:
        """Plano de execução do dia: a decisão explícita (inválida ⇒ ``ValueError``) ou a
        descoberta no livro. Semana descoberta inválida é ignorada com o motivo em ``refusals``
        (alerta do registro) — a carteira vigente continua sendo marcada."""
        if pending is not None:
            return self._plan_from_pending(session, prev, pending)
        refusals = refusals if refusals is not None else []
        live = prev.live_book_week if prev is not None else None
        weeks = [w for w in self.book.list_weeks()
                 if executable_in(w, session, self.cfg) and (live is None or w > live)]
        for w in sorted(weeks, reverse=True):
            try:
                plan = self._discover_plan(session, w)
            except ValueError as exc:
                refusals.append(f"Decisão da semana {w} não executada em {session}: "
                                f"{clean_text(exc, 600)}")
                continue
            if plan is not None:
                return plan
        return None

    def _discover_plan(self, session: date, w: date) -> _Plan | None:
        close = close_datetime(session, self.cfg)
        cutoff = decision_cutoff(session, self.cfg)
        entry = self.book.load_booked(w)
        if entry is not None:
            if entry.booked_at > close:
                return None
            proposal = self.main.proposal_for(entry)
            if proposal is None:
                raise ValueError(f"Efetivação da semana {w} sem a proposta correspondente.")
            decision = self.book.load_decision(w, proposal.version)
            if decision is None or decision.approval_hash != entry.approval_hash:
                raise ValueError(f"Efetivação da semana {w} sem decisão correspondente "
                                 "(approval_hash).")
            notes = self._verify_decision(session, proposal, decision, None, booked=True)
            plan = self._adopt_plan(entry, proposal, decision, "livro")
            plan.notes.extend(notes)
            return plan
        proposal = self.book.load_proposal(w)
        decision = self.book.load_decision(w)
        if (proposal is None or decision is None or decision.decision != DecisionType.APPROVE
                or decision.proposal_id != proposal.proposal_id):
            return None
        if decision.decided_at > cutoff:
            return None
        self._check_not_lapsed(w)
        self._verify_decision(session, proposal, decision, None)
        return self._execute_plan(proposal, decision, None, "decisão")

    def _run_shadow(self, ctx: DailyContext, pending: PendingExecution | None
                    ) -> tuple[_SideResult | None, DailyRecord | None]:
        """Registro do dia da carteira-sombra. Com série já iniciada, proposta-sombra inválida ou
        execução recusada vira alerta no registro-sombra (a carteira-sombra anterior continua)."""
        side = self.shadow
        assert side is not None
        prev = side.track.last()
        _check_track_tail(side.track, prev)
        if prev is not None and prev.date >= ctx.date:
            return None, (prev if prev.date == ctx.date else None)
        alerts: list[str] = []
        try:
            plan = self._shadow_plan(side, ctx, prev, pending)
        except ValueError as exc:
            if prev is None:
                raise
            alerts.append(f"Proposta-sombra não executada em {ctx.date}: {clean_text(exc, 600)}")
            plan = None
        if prev is None and plan is None:
            return None, None
        try:
            return self._compute_side(side, ctx, prev, plan, extra_alerts=alerts), None
        except ExecutionRefused as exc:
            if prev is None or plan is None:
                raise
            alerts.append(f"Execução da proposta-sombra da semana {plan.week} RECUSADA: "
                          f"{clean_text(exc, 600)} Carteira-sombra anterior mantida.")
            return self._compute_side(side, ctx, prev, None, extra_alerts=alerts), None

    def _shadow_plan(self, side: _ShadowSide, ctx: DailyContext, prev: DailyRecord | None,
                     pending: PendingExecution | None) -> _Plan | None:
        live = prev.live_book_week if prev is not None else None
        proposal: Proposal | None = None
        if pending is not None and pending.shadow is not None:
            proposal = pending.shadow
            if proposal.week != pending.proposal.week:
                raise ValueError("Proposta-sombra de outra semana.")
            if (proposal.snapshot_hash != pending.proposal.snapshot_hash
                    or proposal.config_hash != pending.proposal.config_hash):
                raise ValueError("Proposta-sombra com insumos (snapshot/mandato) diferentes da "
                                 "proposta do CDP.")
        else:
            weeks = set(side.store.weeks()) | {
                w for w in self.book.list_weeks()
                if (self.book.week_dir(w) / BOOK_SHADOW_FILE).exists()}
            for w in sorted(weeks, reverse=True):
                if executable_in(w, ctx.date, self.cfg) and (live is None or w > live):
                    proposal = side.store.load_proposal(w) or book_shadow_proposal(self.book, w)
                    break
        if proposal is None or (live is not None and proposal.week <= live):
            return None
        if not executable_in(proposal.week, ctx.date, self.cfg):
            raise ValueError(f"Proposta-sombra da semana {proposal.week} fora da janela.")
        if proposal.config_hash != self.cfg.config_hash():
            raise ValueError("Proposta-sombra com mandato diferente do atual.")
        existing = side.store.load_booked(proposal.week)
        if existing is not None:
            return self._adopt_plan(existing, proposal, None, "sombra")
        store = side.store

        def persist(entry: BookEntry, _p: Proposal = proposal) -> None:
            store.save_proposal(_p)
            store.save_booked(entry)

        return _Plan(week=proposal.week, proposal=proposal, decision=None, entry=None,
                     hold=proposal.optimizer.status == HOLD_STATUS,
                     approval_hash=proposal.proposal_hash(),
                     proposal_id=proposal.proposal_id, source="sombra", persist=persist)

    # ------------------------------------------------------------------ cálculo do dia
    def _live(self, side: _MainSide | _ShadowSide, prev: DailyRecord | None,
              alerts: list[str]) -> tuple[BookEntry | None, Proposal | None, Proposal | None]:
        """Efetivação vigente, sua proposta e a proposta de referência das posições (taxas de
        aluguel e faixas de squeeze da decisão), pulando semanas de "manter"."""
        if prev is None or prev.live_book_week is None:
            return None, None, None
        try:
            entry = side.load_entry(prev.live_book_week)
            proposal = side.proposal_for(entry) if entry is not None else None
        except ValueError as exc:
            alerts.append(f"Efetivação vigente ({prev.live_book_week}) inválida no livro ({exc}); "
                          "marcação pelas posições do registro anterior.")
            return None, None, None
        if entry is None:
            alerts.append(f"Efetivação vigente ({prev.live_book_week}) não encontrada no livro: "
                          "taxas de aluguel pela tabela do dia.")
            return None, None, None
        return entry, proposal, self._reference_proposal(side, entry, proposal)

    @staticmethod
    def _reference_proposal(side: _MainSide | _ShadowSide, entry: BookEntry,
                            proposal: Proposal | None) -> Proposal | None:
        if proposal is None or proposal.optimizer.status != HOLD_STATUS:
            return proposal
        try:
            for w in reversed(side.weeks_before(entry.week)):
                e = side.load_entry(w)
                p = side.proposal_for(e) if e is not None else None
                if p is not None and p.optimizer.status != HOLD_STATUS:
                    return p
        except ValueError:
            return None
        return None

    def _compute_side(self, side: _MainSide | _ShadowSide, ctx: DailyContext,
                      prev: DailyRecord | None, plan: _Plan | None,
                      extra_alerts: list[str] | None = None,
                      extra_hashes: dict[str, str] | None = None) -> _SideResult:
        cfg = self.cfg
        alerts: list[str] = list(extra_alerts or [])
        live_entry, live_prop, ref_prop = self._live(side, prev, alerts)
        marked = self._mark(ctx, prev, ref_prop)
        alerts += marked.alerts
        model_prev = self._model_at(prev.date) if prev is not None and marked.lines else None
        attribution, factor_pnl, attr_alerts = self._attribution(ctx, prev, marked, model_prev)
        alerts += attr_alerts

        nav_pre = marked.nav_pre
        end_lines = list(marked.lines)
        cost = 0.0
        entry_after = live_entry
        commit: Callable[[], None] | None = None
        proposal_after = live_prop
        if plan is not None:
            alerts += plan.notes
            if plan.week != ctx.date:
                alerts.append(f"Execução da decisão da semana {plan.week} no fechamento de "
                              f"{ctx.date} (primeiro pregão disponível).")
            if plan.hold:
                alerts.append(f"Decisão da semana {plan.week}: manter a carteira anterior "
                              "(sem negociação).")
                entry = plan.entry or self._build_hold_entry(ctx, plan, nav_pre, marked)
            else:
                try:
                    execs, size_alerts = self._size(ctx, plan, marked, nav_pre)
                except ValueError as exc:
                    raise ExecutionRefused(str(exc)) from exc
                alerts += size_alerts
                cost_usd, cost_alerts = self._costs(ctx, marked.lines, execs, nav_pre, plan)
                alerts += cost_alerts
                cost = -cost_usd
                end_lines = _merge_execution(marked.lines, execs)
                entry = plan.entry or self._build_entry(ctx, plan, execs, nav_pre, cost_usd)
            if plan.entry is None:
                _guarded(plan.preflight, entry)
                persist = plan.persist
                assert persist is not None

                def commit(_e: BookEntry = entry) -> None:
                    _guarded(persist, _e)
            entry_after = entry
            proposal_after = plan.proposal
            if not plan.hold:
                ref_prop = plan.proposal
        pnl = marked.equity + marked.financing + marked.borrow + cost
        nav_end = marked.nav_start + pnl
        if not (math.isfinite(nav_end) and nav_end > 0):
            raise ValueError(f"NAV não positivo em {ctx.date}: registro interrompido.")

        components = {"equity": marked.equity, "financing": marked.financing,
                      "borrow": marked.borrow, "costs": cost}
        if factor_pnl is not None:
            components["factor"] = factor_pnl
            components["specific"] = marked.equity - factor_pnl
        comp_lines = [AttributionLine(group="component", name=k, pnl_usd=components[k],
                                      contribution=components[k] / marked.nav_start)
                      for k in COMPONENTS if k in components]

        positions = self._positions(end_lines, nav_end)
        risk, risk_alerts_ = self._risk(ctx, side, positions, nav_end, pnl / marked.nav_start,
                                        marked.nav_start, prev)
        alerts += risk_alerts_
        alerts += self._position_alerts(ctx, side, positions, nav_end, ref_prop)
        alerts += [f"{DATA_LIMITATION_PREFIX} {lim}"
                   for lim in session_limitations(ctx.md, ctx.date)]
        alerts += ctx.notes
        if prev is None and ctx.date != cfg.fund.inception_date:
            alerts.append(f"Inception em {ctx.date} difere da data do mandato "
                          f"({cfg.fund.inception_date}).")

        hashes = self._input_hashes(ctx, entry_after, proposal_after, model_prev
                                    if marked.lines else None)
        from .risco_diario import MARKER, build, load, text

        md_prev = (self.store.load(as_of=prev.date).truncate(prev.date)
                   if prev is not None and model_prev is not None else None)
        previous_sources = (load(side.track, prev)["sources"]["current"]
                            if prev is not None and model_prev is not None
                            and MARKER in prev.input_hashes else None)
        diagnostic = build(ctx, cfg, positions, nav_end, model_prev, md_prev,
                           previous_sources=previous_sources)
        if plan is not None:
            from .contrato_custos import (
                CURRENT,
                DIAGNOSTIC_KEY,
                RECORD_MARKER,
                contract,
                digest,
                payload,
            )

            if contract(plan.proposal) == CURRENT:
                cost_diagnostic = ctx.cache.get("execution_costs", {}).get(plan.proposal.proposal_id)
                if cost_diagnostic is None:
                    if not plan.hold:
                        raise ValueError("cálculo prospectivo de custos ausente")
                    cost_diagnostic = payload(pd.DataFrame(), pd.DataFrame(), plan.proposal,
                                              cfg, ctx.date, 0.0)
                diagnostic[DIAGNOSTIC_KEY] = cost_diagnostic
                hashes[RECORD_MARKER] = digest(cost_diagnostic)
        hashes[MARKER] = sha256_text(text(diagnostic))
        if diagnostic["binding"] is None and any(p.market_value_usd for p in positions):
            alerts.append("Risco diário base/evento incompleto: fatia idiossincrática vinculante "
                          "indisponível; não comprova cumprimento integral do mandato.")
        elif (diagnostic["idio_binding"] is not None and cfg.risk.idio_share_floor is not None
              and diagnostic["idio_binding"] < cfg.risk.idio_share_floor - 1e-9):
            alerts.append("Fatia idiossincrática efetiva abaixo do piso em "
                          f"{diagnostic['binding']}: {fmt_pct(diagnostic['idio_binding'])}; "
                          "monitorar a carteira efetiva para a próxima decisão.")
        if extra_hashes:
            hashes.update({k: v for k, v in extra_hashes.items() if v})
        if ctx.md.is_synthetic:
            notice = (f"{SIMULATED_DATA_NOTICE} — mercado sintético gerado por código; "
                      "carteira simulada com execução hipotética no fechamento.")
        else:
            notice = (f"Dados reais de mercado ({REAL_DATA_SOURCES}); carteira simulada com "
                      "execução hipotética no leilão de fechamento e custos do modelo.")
        record = DailyRecord(
            date=ctx.date, fund_name=side.fund_name, track_record_type=side.track_type,
            nav_start_usd=marked.nav_start, nav_end_usd=nav_end, pnl_usd=pnl,
            ret=pnl / marked.nav_start, pnl_components=components,
            attribution=comp_lines + attribution, positions=positions, risk=risk,
            alerts=list(dict.fromkeys(alerts)),
            live_book_week=entry_after.week if entry_after is not None else (
                prev.live_book_week if prev is not None else None),
            approval_hash=entry_after.approval_hash if entry_after is not None else (
                prev.approval_hash if prev is not None else None),
            input_hashes=hashes, is_synthetic=ctx.md.is_synthetic, data_notice=notice,
            prev_record_hash=prev.record_hash if prev is not None else GENESIS_RECORD_HASH,
        )
        record = record.model_copy(update={"record_hash": record.compute_hash()})
        return _SideResult(record=record, entry=entry_after if plan is not None else None,
                           commit=commit, diagnostic=diagnostic)

    # ------------------------------------------------------------------ marcação
    def _fx(self, ctx: DailyContext) -> pd.Series:
        if "fx" not in ctx.cache:
            fx = fx_for_lines(ctx.md)
            ctx.cache["fx_frame"] = fx
            ctx.cache["fx"] = fx.loc[ctx.ts] if ctx.ts in fx.index else pd.Series(dtype=float)
        return ctx.cache["fx"]

    def _fx_rate(self, ctx: DailyContext, currency: str) -> float | None:
        if currency == "USD":
            return 1.0
        v = self._fx(ctx).get(currency, np.nan)
        return float(v) if _finite(v) and v > 0 else None

    def _line_currency(self, ctx: DailyContext, ticker: str, fallback: str) -> str:
        lines = ctx.md.universe.lines
        if ticker in lines.index:
            return str(lines.loc[ticker, "currency"])
        return fallback

    def _availability(self, ctx: DailyContext) -> pd.DataFrame:
        if "availability" not in ctx.cache:
            ctx.cache["availability"] = short_availability(ctx.panel, ctx.md, self.cfg)
        return ctx.cache["availability"]

    def _borrow_fee(self, ctx: DailyContext, ln: _Line, proposal: Proposal | None
                    ) -> tuple[float, str]:
        if proposal is not None:
            for p in proposal.positions:
                if (p.issuer_id == ln.issuer_id and p.side == Side.SHORT
                        and _finite(p.borrow_fee_annual) and p.borrow_fee_annual >= 0):
                    return float(p.borrow_fee_annual), "proposta"
        try:
            av = self._availability(ctx)
        except (ValueError, KeyError):
            av = None
        if av is not None and ln.ticker in av.index:
            fee = pd.to_numeric(av.loc[ln.ticker, "borrow_fee_annual"], errors="coerce")
            if _finite(fee) and fee >= 0:
                return float(fee), "tabela"
        return DEFAULT_BORROW_FEE_ANNUAL, "padrão"

    def _mark(self, ctx: DailyContext, prev: DailyRecord | None,
              live_proposal: Proposal | None) -> _Marked:
        cfg = self.cfg
        if prev is None:
            return _Marked(nav_start=float(cfg.fund.inception_nav_usd), days=0, lines=[],
                           equity=0.0, financing=0.0, borrow=0.0, alerts=[])
        alerts: list[str] = []
        ts, prev_ts = ctx.ts, pd.Timestamp(prev.date)
        days = (ctx.date - prev.date).days
        lr = ctx.panel.line_returns
        period = lr.loc[(lr.index > prev_ts) & (lr.index <= ts)]
        lines: list[_Line] = []
        stale: list[str] = []
        partial: list[str] = []
        for p in sorted(prev.positions, key=lambda x: (x.issuer_id, x.ticker)):
            if p.market_value_usd == 0:
                continue
            r: float | None = None
            if p.ticker in period.columns:
                s = period[p.ticker].dropna()
                if not s.empty:
                    r = float((1.0 + s).prod() - 1.0)
            price_local, price_usd = p.price_local, p.price_usd
            if r is None:
                stale.append(p.ticker)
            else:
                px, pdate = (_last_valid(ctx.md.close[p.ticker], ts)
                             if p.ticker in ctx.md.close.columns else (None, None))
                fx = self._fx_rate(ctx, p.currency)
                if px is not None:
                    price_local = px
                    price_usd = px * fx if fx is not None else None
                    if pdate is not None and pdate < ts:
                        partial.append(p.ticker)
            pnl = p.market_value_usd * r if r is not None else 0.0
            lines.append(_Line(
                issuer_id=p.issuer_id, ticker=p.ticker, currency=p.currency, shares=p.shares,
                mv_start=p.market_value_usd, pnl=pnl, ret=r, repriced=r is not None,
                mv_end=p.market_value_usd + pnl, price_local=price_local, price_usd=price_usd))
        if stale:
            alerts.append("Preço ausente no pregão (linha não negociou; posição não reprecificada, "
                          f"valor mantido): {_list(stale)}.")
        if partial:
            alerts.append("Preço defasado (último fechamento anterior ao pregão): "
                          f"{_list(partial)}.")
        equity = float(sum(ln.pnl for ln in lines))

        financing = 0.0
        if days > 0:
            rate, _, rate_alerts = financing_rate(ctx.md, prev.date)
            alerts += rate_alerts
            if rate is not None:
                financing = marked_financing(prev.nav_end_usd, rate, days)
        borrow = 0.0
        defaulted: list[str] = []
        for ln in lines:
            if ln.mv_start < 0 and days > 0:
                fee, src = self._borrow_fee(ctx, ln, live_proposal)
                if src == "padrão":
                    defaulted.append(ln.ticker)
                borrow -= abs(ln.mv_start) * fee / DAY_COUNT_BASIS * days
        if defaulted:
            alerts.append(f"Aluguel pela taxa padrão conservadora de "
                          f"{fmt_pct(DEFAULT_BORROW_FEE_ANNUAL)} a.a. (sem taxa na proposta nem "
                          f"na tabela): {_list(defaulted)}.")
        return _Marked(nav_start=float(prev.nav_end_usd), days=days, lines=lines, equity=equity,
                       financing=financing, borrow=borrow, alerts=alerts)

    # ------------------------------------------------------------------ atribuição
    def _attribution(self, ctx: DailyContext, prev: DailyRecord | None, marked: _Marked,
                     model_prev: RiskModel | None
                     ) -> tuple[list[AttributionLine], float | None, list[str]]:
        nav0 = marked.nav_start
        alerts: list[str] = []
        lines = marked.lines
        out: list[AttributionLine] = []
        assets = ctx.panel.assets
        issuers = ctx.md.universe.issuers

        def meta(iid: str, col_panel: str, col_uni: str) -> str:
            if iid in assets.index and isinstance(assets.loc[iid, col_panel], str):
                return str(assets.loc[iid, col_panel])
            if iid in issuers.index:
                return str(issuers.loc[iid, col_uni])
            return "NA"

        def agg(group: str, keys: list[str]) -> list[AttributionLine]:
            acc: dict[str, float] = {}
            for k, ln in zip(keys, lines, strict=True):
                acc[k] = acc.get(k, 0.0) + ln.pnl
            return [AttributionLine(group=group, name=k, pnl_usd=v, contribution=v / nav0)
                    for k, v in sorted(acc.items())]

        factor_pnl: float | None = 0.0 if not lines else None
        if lines:
            factor_pnl, factor_lines, f_alerts = self._factor_attribution(ctx, prev, marked,
                                                                          model_prev)
            alerts += f_alerts
            out += factor_lines
            out += agg("issuer", [ln.issuer_id for ln in lines])
            out += agg("country", [meta(ln.issuer_id, "country", "country") for ln in lines])
            out += agg("sector", [meta(ln.issuer_id, "sector", "gics_sector") for ln in lines])
            sides = [Side.LONG.value if ln.mv_start > 0 else Side.SHORT.value for ln in lines]
            side_lines = agg("side", sides)
            order = {Side.LONG.value: 0, Side.SHORT.value: 1}
            out += sorted(side_lines, key=lambda a: order[a.name])
        return out, factor_pnl, alerts

    def _factor_attribution(self, ctx: DailyContext, prev: DailyRecord | None, marked: _Marked,
                            model_prev: RiskModel | None
                            ) -> tuple[float | None, list[AttributionLine], list[str]]:
        nav0 = marked.nav_start
        if prev is None:
            return 0.0, [], []
        if model_prev is None:
            note = self._model_notes.get(prev.date, "")
            return None, [], [("Atribuição fatorial indisponível (modelo de risco da sessão "
                               "anterior ausente): fatores × específico não calculados. "
                               + note).strip()]
        session_returns = (ctx.panel.returns.loc[ctx.ts] if ctx.ts in ctx.panel.returns.index
                           else None)
        from ..risk.macro import macro_returns

        required = ["macro:" + s for s in self.cfg.risk_model.macro_factors]
        symbols = sorted({s.removeprefix("macro:") for s in required} | {
            n.removeprefix("macro:") for n in model_prev.factor_names if n.startswith("macro:")})
        observed = macro_returns(ctx.md, symbols, ctx.panel.returns.index)
        observed.columns = ["macro:" + c for c in observed.columns]
        get, source_state = factor_returns_source(ctx.model, model_prev, ctx.ts, session_returns,
                                                  required_macro=required,
                                                  observed_macro=observed,
                                                  observed_equity=ctx.panel.returns)
        names = model_prev.factor_names
        strict_macro = bool(symbols)
        calendar = ctx.panel.returns.index
        prev_ts, ts = pd.Timestamp(prev.date), ctx.ts
        fx_frame = ctx.cache.get("fx_frame")
        if fx_frame is None:
            self._fx(ctx)
            fx_frame = ctx.cache["fx_frame"]
        contrib = pd.Series(0.0, index=names)
        missing_days: set[str] = set()
        outside: list[str] = []
        session_missing = False
        for ln in marked.lines:
            if not ln.repriced:
                continue
            if ln.issuer_id not in model_prev.exposures.index:
                outside.append(ln.ticker)
                continue
            if strict_macro and not np.isfinite(model_prev.exposures.loc[
                    ln.issuer_id].reindex(names).to_numpy(dtype=float)).all():
                return None, [], ["Atribuição macro indisponível: exposição da posição não finita."]
            # Janela do retorno da linha: (último preço válido ≤ registro anterior, último ≤ hoje].
            if ln.ticker in ctx.md.adj_close.columns and ln.currency in fx_frame.columns:
                adj = pd.to_numeric(ctx.md.adj_close[ln.ticker], errors="coerce")
                lvl = adj.where(np.isfinite(adj) & (adj > 0)) * fx_frame[ln.currency].reindex(adj.index)
                lvl = lvl.where(np.isfinite(lvl) & (lvl > 0))
                valid = lvl.dropna().index
                d0 = valid[valid <= prev_ts]
                d1 = valid[valid <= ts]
                start = d0[-1] if len(d0) else prev_ts
                end = d1[-1] if len(d1) else ts
            else:
                start, end = prev_ts, ts
            window = calendar[(calendar > start) & (calendar <= end)]
            f_sum = pd.Series(0.0, index=names)
            for s in window:
                row = get(s)
                if row is None:
                    if strict_macro:
                        return None, [], [f"Atribuição macro indisponível em {s.date()}: "
                                          "fator requerido/retorno observado ausente ou não finito; "
                                          "fatores e específico não apurados."]
                    if s == ts:
                        session_missing = True
                    else:
                        missing_days.add(str(s.date()))
                    continue
                f_sum = f_sum + row.fillna(0.0)
            b = model_prev.exposures.loc[ln.issuer_id].reindex(names).fillna(0.0)
            contrib = contrib + ln.mv_start * b * f_sum
        if session_missing:
            return None, [], [f"Retornos fatoriais de {ctx.date} indisponíveis (modelo e regressão "
                              "do dia): atribuição fatorial não calculada."]
        alerts: list[str] = []
        if source_state["fallback"]:
            alerts.append("Retornos fatoriais do dia estimados por regressão cross-section com as "
                          "exposições da sessão anterior." + (
                              " Macro observado descontado antes da regressão estrutural."
                              if strict_macro else ""))
        if source_state["partial"]:
            detail = "; ".join(f"{d}: {_list(fs)}"
                               for d, fs in sorted(source_state["partial"].items()))
            alerts.append("Fatores sem retorno estimado (contribuição fatorial zero, P&L no "
                          f"específico): {detail}.")
        if missing_days:
            alerts.append("Sessões sem retornos fatoriais na janela de linhas que voltaram a "
                          "negociar (contribuição fatorial zero nelas): "
                          f"{_list(sorted(missing_days))}.")
        if outside:
            if strict_macro:
                return None, [], ["Atribuição macro indisponível: posição fora da base anterior."]
            alerts.append("Linhas fora do modelo de risco (P&L classificado como específico): "
                          f"{_list(outside)}.")
        factor_pnl = float(contrib.sum())
        groups = model_prev.factor_groups
        lines: list[AttributionLine] = []
        for g in FACTOR_GROUPS + (("macro",) if strict_macro else ()):
            v = float(contrib[[f for f in names if groups.get(f) == g]].sum())
            lines.append(AttributionLine(group="factor_group", name=g, pnl_usd=v,
                                         contribution=v / nav0))
        for f in sorted(names):
            v = float(contrib[f])
            lines.append(AttributionLine(group="factor", name=f, pnl_usd=v, contribution=v / nav0))
        return factor_pnl, lines, alerts

    # ------------------------------------------------------------------ execução
    def _size(self, ctx: DailyContext, plan: _Plan, marked: _Marked, nav_pre: float
              ) -> tuple[list[_Exec], list[str]]:
        if self.cfg.execution is not None:
            return self._size_fechamento(ctx, plan, marked, nav_pre)
        alerts: list[str] = []
        execs: list[_Exec] = []
        stale: list[str] = []
        min_lot: list[str] = []
        seen: set[tuple[str, str]] = set()
        for issuer, ticker, weight, ccy in plan.targets():
            if (issuer, ticker) in seen:
                raise ValueError(f"Linha {issuer}/{ticker} duplicada na carteira a executar.")
            seen.add((issuer, ticker))
            if not _finite(weight):
                raise ValueError(f"Peso não finito para {issuer}/{ticker}.")
            currency = self._line_currency(ctx, ticker, ccy)
            if currency != ccy:
                alerts.append(f"{ticker}: moeda da proposta ({ccy}) difere da linha ({currency}); "
                              "usada a moeda da linha.")
            if ticker not in ctx.md.close.columns:
                raise ValueError(f"Linha {ticker} ({issuer}) sem série de preços: execução "
                                 "impossível.")
            px, pdate = _last_valid(ctx.md.close[ticker], ctx.ts)
            if px is None:
                raise ValueError(f"Linha {ticker} ({issuer}) sem preço válido até {ctx.date}.")
            if pdate is not None and pdate < ctx.ts:
                stale.append(f"{ticker} ({pdate.date()})")
                if (ctx.ts - pdate).days > STALE_DAYS_MAX:
                    alerts.append(f"{ticker}: execução a preço com mais de {STALE_DAYS_MAX} dias.")
            fx = self._fx_rate(ctx, currency)
            if fx is None:
                raise ValueError(f"Câmbio {currency} indisponível em {ctx.date}: execução de "
                                 f"{ticker} impossível.")
            shares = _round_shares(weight * nav_pre / (px * fx))
            if shares == 0:
                shares = 1 if weight > 0 else -1
                min_lot.append(ticker)
            execs.append(_Exec(issuer, ticker, currency, shares, px, fx))
        if stale:
            alerts.append("Execução ao último fechamento disponível (sem negociação no pregão): "
                          f"{_list(stale)}.")
        if min_lot:
            alerts.append(f"Posição menor que uma ação; executada 1 ação: {_list(min_lot)}.")
        return execs, alerts

    def _size_fechamento(self, ctx: DailyContext, plan: _Plan, marked: _Marked, nav_pre: float
                         ) -> tuple[list[_Exec], list[str]]:
        """Ordens em ações executadas ao fechamento oficial com capacidade de leilão.

        Ordem = ações-alvo (fixadas na decisão; sem elas, peso × NAV ao fechamento) − ações
        detidas. A execução de cada linha segue a regra única
        :func:`cdp.portfolio.execucao.preenchimentos_esperados` (a mesma da conferência do livro
        e do ``cdp verify``): ``sinal × min(|ordem|, ⌊capacidade / preço⌋)`` com a capacidade
        pelo volume do pregão; não negociam linha sem pregão elegível, sem fechamento oficial no
        dia, decisão após o corte MOC do mercado ou ordem abaixo da banda ``min_trade_weight``;
        emissor com linha detida sem negociação fica inteiro congelado. Linhas detidas sem
        negociação mantêm a marcação do dia."""
        from ..portfolio.execucao import (
            OrdemLinha,
            cambio_do_pregao,
            janela_execucao,
            preenchimentos_esperados,
        )

        cfg = self.cfg
        ex = cfg.execution
        assert ex is not None
        janela = janela_execucao(ctx.date, cfg)
        held: dict[tuple[str, str], _Line] = {}
        for ln in marked.lines:
            if ln.mv_end == 0 and not ln.shares:
                continue
            if ln.shares is None:
                raise ValueError(f"Posição {ln.issuer_id}/{ln.ticker} sem quantidade de ações: "
                                 "execução com capacidade impossível.")
            held[(ln.issuer_id, ln.ticker)] = ln
        pos_by: dict[tuple[str, str], PositionTarget] = {}
        if plan.proposal is not None:
            pos_by = {(p.issuer_id, p.execution_ticker): p for p in plan.proposal.positions
                      if p.weight != 0}
        targets: dict[tuple[str, str], tuple[float, str]] = {}
        for issuer, ticker, weight, ccy in plan.targets():
            if (issuer, ticker) in targets:
                raise ValueError(f"Linha {issuer}/{ticker} duplicada na carteira a executar.")
            if not _finite(weight):
                raise ValueError(f"Peso não finito para {issuer}/{ticker}.")
            targets[(issuer, ticker)] = (float(weight), ccy)
        keys = sorted(set(targets) | set(held))
        ordens: list[OrdemLinha] = []
        quote: dict[tuple[str, str], tuple[str, float | None, float | None]] = {}
        for iid, tk in keys:
            ln = held.get((iid, tk))
            s0 = int(round(float(ln.shares))) if ln is not None and ln.shares is not None else 0
            tgt = targets.get((iid, tk))
            currency = self._line_currency(ctx, tk, tgt[1] if tgt else (
                ln.currency if ln is not None else "USD"))
            px: float | None = None
            if tk in ctx.md.close.columns and ctx.ts in ctx.md.close.index:
                v = ctx.md.close.at[ctx.ts, tk]
                px = float(v) if _finite(v) and float(v) > 0 else None
            fx = cambio_do_pregao(ctx.md, currency, ctx.date)
            if tgt is None:
                st: int | None = 0
            else:
                pt = pos_by.get((iid, tk))
                if pt is not None and pt.shares is not None:
                    st = int(pt.shares)
                elif px is not None and fx is not None:
                    st = _round_shares(tgt[0] * nav_pre / (px * fx))
                else:
                    st = None
            quote[(iid, tk)] = (currency, px, fx)
            ordens.append(OrdemLinha(iid, tk, s0, st, px, fx))
        decided_at = plan.decision.decided_at if plan.decision is not None else None
        fills = preenchimentos_esperados(ordens, ctx.md, janela, cfg, nav_pre=nav_pre,
                                         decidido_em=decided_at)
        execs: list[_Exec] = []
        partial: list[str] = []
        frozen: dict[str, str] = {}
        unmarketable: list[str] = []
        late: list[str] = []
        band: list[str] = []
        no_px: list[str] = []
        for f in fills:
            key = (f.emissor, f.ticker)
            ln = held.get(key)
            currency, px, fx = quote[key]
            if f.situacao == "congelado":
                frozen.setdefault(f.emissor, f.motivo)
            elif f.situacao == "sem_preco":
                no_px.append(f"{f.ticker} ({f.motivo})")
            elif f.situacao == "inelegivel":
                unmarketable.append(f"{f.ticker} ({f.motivo})")
            elif f.situacao == "apos_corte":
                late.append(f.ticker)
            elif f.situacao == "banda":
                band.append(f.ticker)
            elif f.situacao == "parcial":
                partial.append(f"{f.ticker} ({_int_br(abs(f.executadas))}/"
                               f"{_int_br(abs(f.ordem))})")
            if f.executadas != 0:
                assert px is not None and fx is not None
                execs.append(_Exec(f.emissor, f.ticker, currency, f.detidas + f.executadas, px,
                                   fx, mic=f.mic, traded=f.executadas))
            elif ln is not None:
                p_loc = ln.price_local if ln.price_local is not None else (px or 0.0)
                rate = (ln.price_usd / ln.price_local
                        if ln.price_usd is not None and ln.price_local else (fx or 0.0))
                execs.append(_Exec(f.emissor, f.ticker, ln.currency, f.detidas, float(p_loc),
                                   float(rate), value=ln.mv_end, mic=f.mic))
        alerts: list[str] = []
        if partial:
            alerts.append("Execução limitada pela capacidade do leilão de fechamento (ações "
                          f"executadas/ordenadas): {_list(partial)}.")
        if frozen:
            # Todo emissor detido sem negociação no fechamento (com ou sem ordem): as ações
            # ficam como estão nesta montagem.
            alerts.append("Emissores congelados (linha detida sem negociação no fechamento; "
                          "ações mantidas): "
                          f"{_list(f'{k}: {v}' for k, v in sorted(frozen.items()))}.")
        if unmarketable:
            alerts.append(f"Ordens sem mercado elegível no fechamento: {_list(unmarketable)}.")
        if late:
            alerts.append(f"Ordens após o corte MOC do mercado (não executadas): {_list(late)}.")
        if band:
            extra = (" ou do custo fixo mínimo por ordem do mercado"
                     if ex.max_fixed_cost_bps and self.cfg.costs.min_order_cost_usd else "")
            alerts.append("Ordens abaixo da banda de não-negociação "
                          f"({fmt_pct(ex.min_trade_weight, 2)} do NAV{extra}): {_list(band)}.")
        if no_px:
            alerts.append("Sem fechamento oficial ou câmbio no pregão (ordem não executada): "
                          f"{_list(no_px)}.")
        return execs, alerts

    def _closing_cost_calculation(self, ctx: DailyContext, trades: Iterable[tuple],
                                  proposal: Proposal | None = None
                                  ) -> tuple[pd.DataFrame, pd.DataFrame, float]:
        """Mesmas faixas/impacto/FX; contrato da proposta escolhe o piso da comissão."""
        from ..portfolio.costs import custos_fechamento
        from .contrato_custos import CURRENT, contract

        chosen = contract(proposal)
        frame = self.custo_frame(ctx, trades, contrato=chosen)
        if frame.empty:
            return frame, pd.DataFrame(), 0.0
        res = custos_fechamento(frame, self.cfg)
        c = self.cfg.costs
        default_bps = (max(c.half_spread_bps_by_tier.values()) + max(c.commission_bps.values())
                       + c.fx_cost_bps)
        miss = res["cost_usd"].isna()
        if miss.any():
            fallback = frame.loc[miss, "notional_usd"] * default_bps / 1e4
            if chosen == CURRENT:
                # Conservador declarado preserva ao menos a comissão por ordem conhecida;
                # não converte sigma/ADTV ausente em observação zero.
                commission = frame.loc[miss, "notional_usd"] * res.loc[miss, "commission_bps"] / 1e4
                fallback += np.maximum(commission - frame.loc[miss, "notional_usd"] *
                                       max(c.commission_bps.values()) / 1e4, 0.0)
            res.loc[miss, "cost_usd"] = fallback
            res.loc[miss, "flags"] = res.loc[miss, "flags"] + ";bps_conservador"
        return frame, res, float(res["cost_usd"].sum())

    def _costs_fechamento(self, ctx: DailyContext, execs: list[_Exec], nav_pre: float,
                          proposal: Proposal | None = None) -> tuple[float, list[str]]:
        from .contrato_custos import CURRENT, contract, payload

        frame, res, total = self._closing_cost_calculation(ctx, [
            (e.issuer_id, e.ticker, e.currency, abs(e.traded) * e.price_local * e.fx,
             e.traded, e.price_local) for e in execs if e.traded != 0], proposal)
        if contract(proposal) == CURRENT:
            ctx.cache.setdefault("execution_costs", {})[proposal.proposal_id] = payload(
                frame, res, proposal, self.cfg, ctx.date, total)
        alerts: list[str] = []
        flagged = sorted(t for t, f in res["flags"].items() if f) if not res.empty else []
        if flagged:
            alerts.append("Custos com parâmetro conservador (ADTV ou volatilidade ausente): "
                          f"{_list(flagged)}.")
        return total, alerts

    def custo_frame(self, ctx: DailyContext, trades: Iterable[tuple], *,
                    contrato: str = "aggregate_line/v0") -> pd.DataFrame:
        """Insumos do custo por linha negociada ``(emissor, ticker, moeda, nocional USD[, ações,
        preço local])``: ADTV da linha, σ diária do emissor (63 pregões), mercado, categoria,
        mercado local fechado (ADR negociado com a bolsa local sem pregão) e ordens enviadas
        (lote padrão + fracionário/pico contam duas; sem ações informadas, uma)."""
        from ..calendar import MARKET_EXCHANGES, is_session
        from ..portfolio.execucao import categoria_da_linha
        from ..portfolio.trades import n_orders, order_legs_detail
        from ..universe import listing_market
        from .contrato_custos import CURRENT, LEGACY

        if contrato not in (CURRENT, LEGACY):
            raise ValueError("contrato de custos desconhecido")
        rows = list(trades)
        if contrato == CURRENT:
            rows.sort(key=lambda row: row[1])  # Ordem canônica do cálculo prospectivo/reprodução.
        if not rows:
            return pd.DataFrame()
        lines = ctx.panel.lines
        assets = ctx.panel.assets
        vol = ctx.panel.returns.loc[:ctx.ts].tail(63).std()
        known = vol[vol > 0].dropna()
        p90 = float(known.quantile(0.9)) if len(known) else float("nan")
        out = []
        for row in rows:
            iid, tk, ccy, notional = row[:4]
            n_ord = n_orders(tk, int(row[4]), row[5]) if len(row) >= 6 and row[4] else 1
            adtv = (float(lines.at[tk, "adtv_usd"]) if tk in lines.index
                    and _finite(lines.at[tk, "adtv_usd"]) and lines.at[tk, "adtv_usd"] > 0
                    else float("nan"))
            flag = ""
            if not math.isfinite(adtv):
                a2 = assets["adtv_usd"].get(iid) if "adtv_usd" in assets.columns else None
                if a2 is not None and _finite(a2) and a2 > 0:
                    adtv, flag = float(a2), "adtv_emissor"
                else:
                    adtv, flag = float(max(self.cfg.liquidity.min_adtv_usd, 1.0)), "adtv_minimo"
            sd = vol.get(iid)
            if sd is None or not _finite(sd) or sd <= 0:
                sd, flag = p90, (flag + ";" if flag else "") + "vol_p90"
            lt = lines.at[tk, "line_type"] if tk in lines.index else None
            country = (str(assets.at[iid, "country"]) if iid in assets.index
                       and "country" in assets.columns else "")
            home = MARKET_EXCHANGES.get(country)
            mkt = listing_market(tk)
            local_closed = bool(mkt == "US" and home is not None and home != "XNYS"
                                and not is_session(ctx.date, home))
            item = {"ticker": tk, "issuer_id": iid, "notional_usd": float(notional),
                    "adtv_usd": adtv, "sigma_d": float(sd), "market": mkt,
                    "currency": ccy, "categoria": categoria_da_linha(tk, lt),
                    "local_fechado": local_closed, "flag": flag, "n_ordens": n_ord}
            if contrato == CURRENT:
                if len(row) < 6 or not isinstance(row[4], (int, np.integer)) or row[4] == 0:
                    raise ValueError("ações executadas ausentes no custo por ordem")
                parts = order_legs_detail(tk, int(row[4]), row[5])
                item.update({"contrato_comissao": CURRENT, "acoes_executadas": int(row[4]),
                             "preco_local": float(row[5]),
                             "nocionais_ordens_usd": [abs(q) * float(notional) / abs(int(row[4]))
                                                      for _, q, _ in parts],
                             "ordens": [{"ticker": ticker, "acoes": q, "livro": kind}
                                        for ticker, q, kind in parts]})
            out.append(item)
        return pd.DataFrame(out).set_index("ticker")

    def _cost_model(self, ctx: DailyContext, nav: float) -> CostModel:
        key = ("cost_model", round(nav, 2))
        if key not in ctx.cache:
            sides = issuer_side_lines(ctx.panel, self._availability(ctx))
            daily_vol = ctx.panel.returns.loc[:ctx.ts].tail(63).std()
            ctx.cache[key] = build_cost_model(sides, ctx.panel.assets, daily_vol, self.cfg, nav)
        return ctx.cache[key]

    def _fallback_bps(self, plan: _Plan) -> tuple[dict[str, float], float]:
        c = self.cfg.costs
        default = (max(c.half_spread_bps_by_tier.values()) + max(c.commission_bps.values())
                   + c.fx_cost_bps)
        bps: dict[str, float] = {}
        if plan.proposal is not None:
            for t in plan.proposal.trades:
                if _finite(t.est_cost_bps) and t.issuer_id not in bps:
                    bps[t.issuer_id] = float(t.est_cost_bps)
        return bps, default

    def _costs(self, ctx: DailyContext, old: list[_Line], execs: list[_Exec], nav_pre: float,
               plan: _Plan) -> tuple[float, list[str]]:
        """Custo (USD, positivo) de passar da carteira antiga (derivada) à executada."""
        if self.cfg.execution is not None:
            return self._costs_fechamento(ctx, execs, nav_pre, plan.proposal)
        w_old: dict[tuple[str, str], float] = {(ln.issuer_id, ln.ticker): ln.mv_end / nav_pre
                                               for ln in old if ln.mv_end != 0}
        w_new: dict[tuple[str, str], float] = {(e.issuer_id, e.ticker): e.mv / nav_pre
                                               for e in execs}
        passes: list[tuple[dict[str, float], dict[str, float]]] = [({}, {}), ({}, {}), ({}, {})]
        for key in sorted(set(w_old) | set(w_new)):
            iid = key[0]
            k = 0 if key in w_old and key in w_new else (1 if key in w_old else 2)
            tgt, cur = passes[k]
            tgt[iid] = tgt.get(iid, 0.0) + w_new.get(key, 0.0)
            cur[iid] = cur.get(iid, 0.0) + w_old.get(key, 0.0)
        alerts: list[str] = []
        try:
            cm = self._cost_model(ctx, nav_pre)
        except (ValueError, KeyError) as exc:
            cm = None
            alerts.append(f"Modelo de custos indisponível ({exc}): custos por bps de fallback.")
        bps, default_bps = self._fallback_bps(plan)
        total = 0.0
        fallback_used: list[str] = []
        for tgt, cur in passes:
            if not tgt:
                continue
            ids = sorted(tgt)
            known = [i for i in ids if cm is not None and i in cm.index]
            unknown = [i for i in ids if i not in known]
            if known:
                t = pd.Series({i: tgt[i] for i in known}, dtype=float)
                c = pd.Series({i: cur[i] for i in known}, dtype=float)
                est = estimate_rebalance_costs(t, c, cm)
                bad = est.index[~np.isfinite(est.to_numpy(dtype=float))]
                total += float(est.drop(bad).sum()) * nav_pre
                unknown += list(bad)
            for i in unknown:
                rate = bps.get(i, default_bps)
                total += abs(tgt[i] - cur[i]) * nav_pre * rate / 1e4
                fallback_used.append(i)
        if fallback_used:
            alerts.append("Custos por bps de fallback (proposta ou conservador de "
                          f"{default_bps:.0f} bps): {_list(sorted(set(fallback_used)))}.")
        return total, alerts

    def _build_entry(self, ctx: DailyContext, plan: _Plan, execs: list[_Exec], nav_pre: float,
                     cost_usd: float) -> BookEntry:
        nav_end = nav_pre - cost_usd
        if self.cfg.execution is not None:
            return self._build_entry_fechamento(ctx, plan, execs, nav_pre, cost_usd)
        note = (f"Execução hipotética MOC no fechamento de {ctx.date} (carteira simulada): "
                f"nocional-alvo = peso × NAV antes dos custos ({fmt_usd_mm(nav_pre)}), ações pelo "
                f"fechamento local e câmbio do dia; custos estimados {fmt_usd(cost_usd)}; NAV após "
                f"custos {fmt_usd_mm(nav_end)}.")
        if self.shadow is not None and plan.source == "sombra":
            note = "Carteira-sombra só-quant (contrafactual, sem decisão). " + note
        positions = [
            BookedPosition(issuer_id=e.issuer_id, ticker=e.ticker, weight=e.mv / nav_pre,
                           notional_usd=e.mv, shares=e.shares, entry_price_local=e.price_local,
                           currency=e.currency)
            for e in execs]
        return BookEntry(week=plan.week, proposal_id=plan.proposal_id,
                         approval_hash=plan.approval_hash,
                         booked_at=close_datetime(ctx.date, self.cfg), nav_usd=nav_pre,
                         positions=positions, pricing_note=note)

    def _build_entry_fechamento(self, ctx: DailyContext, plan: _Plan, execs: list[_Exec],
                                nav_pre: float, cost_usd: float) -> BookEntry:
        """Efetivação com capacidade: a carteira RESULTANTE (linhas negociadas, saldos de saídas
        parciais e emissores congelados); ``booked_at`` = fechamento oficial mais tardio entre as
        linhas negociadas."""
        from ..portfolio.execucao import fechamento_execucao, janela_execucao

        janela = janela_execucao(ctx.date, self.cfg)
        traded = [e for e in execs if e.traded != 0]
        at = fechamento_execucao(janela, {e.mic for e in traded if e.mic})
        booked_at = (at.astimezone(ZoneInfo(self.cfg.fund.timezone)) if at is not None
                     else close_datetime(ctx.date, self.cfg))
        n_full = sum(1 for e in execs if e.traded != 0)
        note = (f"Execução hipotética no leilão de fechamento de {ctx.date} (carteira simulada): "
                "ordens em quantidade de ações fixadas na decisão, executadas ao fechamento "
                "oficial de cada linha até a capacidade do leilão e da janela pré-fechamento "
                f"(volume realizado do pregão); {n_full} "
                f"{'linha negociada' if n_full == 1 else 'linhas negociadas'}; custos estimados "
                f"{fmt_usd(cost_usd)}; NAV após custos {fmt_usd_mm(nav_pre - cost_usd)}.")
        if self.shadow is not None and plan.source == "sombra":
            note = "Carteira-sombra só-quant (contrafactual, sem decisão). " + note
        positions = [
            BookedPosition(issuer_id=e.issuer_id, ticker=e.ticker, weight=e.mv / nav_pre,
                           notional_usd=e.mv, shares=e.shares, entry_price_local=e.price_local,
                           currency=e.currency)
            for e in execs if e.shares != 0]
        return BookEntry(week=plan.week, proposal_id=plan.proposal_id,
                         approval_hash=plan.approval_hash, booked_at=booked_at, nav_usd=nav_pre,
                         positions=positions, pricing_note=note)

    def _build_hold_entry(self, ctx: DailyContext, plan: _Plan, nav_pre: float,
                          marked: _Marked | None = None) -> BookEntry:
        """Efetivação de "manter" (sem negociação). Legado: sem posições-alvo (a carteira segue
        derivando). Com a seção ``execution`` a efetivação lista a carteira detida (ações
        inalteradas), como toda efetivação nesse regime: o livro sempre registra a carteira
        após o fechamento."""
        positions: list[BookedPosition] = []
        if self.cfg.execution is not None and marked is not None:
            for ln in marked.lines:
                if not ln.shares or ln.mv_end == 0:
                    continue
                positions.append(BookedPosition(
                    issuer_id=ln.issuer_id, ticker=ln.ticker, weight=ln.mv_end / nav_pre,
                    notional_usd=ln.mv_end, shares=int(round(float(ln.shares))),
                    entry_price_local=ln.price_local, currency=ln.currency))
        return BookEntry(week=plan.week, proposal_id=plan.proposal_id,
                         approval_hash=plan.approval_hash,
                         booked_at=close_datetime(ctx.date, self.cfg), nav_usd=nav_pre,
                         positions=positions,
                         pricing_note=(f"Manter a carteira anterior no fechamento de {ctx.date} "
                                       "(sem negociação, sem custos)."))

    # ------------------------------------------------------------------ posições e risco
    @staticmethod
    def _positions(lines: list[_Line], nav_end: float) -> list[DailyPosition]:
        out = []
        for ln in lines:
            side = (Side.LONG if ln.mv_end > 0 else Side.SHORT if ln.mv_end < 0
                    else Side.LONG if ln.mv_start >= 0 else Side.SHORT)
            out.append(DailyPosition(
                issuer_id=ln.issuer_id, ticker=ln.ticker, currency=ln.currency, side=side,
                shares=ln.shares, price_local=ln.price_local, price_usd=ln.price_usd,
                market_value_usd=ln.mv_end, weight=ln.mv_end / nav_end, day_pnl_usd=ln.pnl,
                day_return_usd=ln.ret, repriced=ln.repriced))
        out.sort(key=lambda p: (p.market_value_usd == 0, -abs(p.market_value_usd), p.issuer_id,
                                p.ticker))
        return out

    def _risk(self, ctx: DailyContext, side: _MainSide | _ShadowSide,
              positions: list[DailyPosition], nav_end: float, ret_today: float,
              nav_start: float, prev: DailyRecord | None) -> tuple[DailyRisk, list[str]]:
        cfg = self.cfg
        alerts: list[str] = []
        w = pd.Series(dtype=float)
        for p in positions:
            if p.market_value_usd != 0:
                w.loc[p.issuer_id] = w.get(p.issuer_id, 0.0) + p.market_value_usd / nav_end
        w = w[w != 0].sort_index()
        gross = float(w.abs().sum())
        net = float(w.sum())
        ex_ante = factor_vol = specific_vol = beta = var = es = None
        exposures: list[ExposureLine] = []
        model = ctx.risk_model
        if w.empty:
            ex_ante = factor_vol = specific_vol = beta = var = es = 0.0
        elif model is not None:
            from .risco_diario import measures

            required = ["macro:" + s for s in cfg.risk_model.macro_factors]
            complete = measures(model, w, required, 1.0)
            if not complete["complete"] and required:
                alerts.append("Risco macro incompleto: " + "; ".join(complete["reasons"]) +
                              "; risco ex-ante/fatorial/específico indisponível.")
                model = None
        if not w.empty and model is not None:
            outside = sorted(set(w.index) - set(model.assets))
            if outside:
                alerts.append("Emissores fora do modelo de risco (risco ex-ante parcial): "
                              f"{_list(outside)}.")
            wm = w[w.index.isin(model.assets)]
            if not wm.empty:
                dec = risk_decomposition(wm, model)
                ex_ante, factor_vol, specific_vol = dec.total_vol, dec.factor_vol, dec.specific_vol
                pv, pe = parametric_var_es(wm, model, cfg.risk.var_confidence, 1)
                try:
                    hv, he = historical_var_es(wm, ctx.panel, model, cfg.risk.var_confidence, 1)
                except ValueError:
                    hv, he = math.nan, math.nan
                var, es = _max_finite(pv, hv), _max_finite(pe, he)
                if var is None or es is None:
                    alerts.append("VaR/ES 1d indisponível (paramétrico e histórico não finitos).")
                try:
                    betas = predicted_betas(model, market_weights(ctx.panel, model.assets))
                    b = betas.reindex(wm.index).astype(float)
                    if b.notna().all():
                        beta = float(b @ wm)
                    else:
                        alerts.append("Beta previsto indisponível para "
                                      f"{_list(sorted(b.index[b.isna()]))}: beta não apurado.")
                except ValueError as exc:
                    alerts.append(f"Beta previsto indisponível: {exc}")
                x = dec.exposures
                for s in STYLE_FACTORS:
                    if s in x.index:
                        exposures.append(ExposureLine(
                            group="style", name=s, long=0.0, short=0.0, net=float(x[s]),
                            gross=abs(float(x[s])), limit=cfg.risk.style_exposure_max_abs))
        exposures = self._group_exposures(ctx, w) + exposures

        hist = side.track.frame()
        rets = list(hist["ret"].astype(float)) + [ret_today]
        rv21 = realized_vol(rets, REALIZED_VOL_WINDOWS[0])
        rv63 = realized_vol(rets, REALIZED_VOL_WINDOWS[1])
        if hist.empty:
            peak = nav_start
        else:
            nav0 = float(hist["nav"].iloc[0] - hist["pnl"].iloc[0])
            peak = max(nav0, float(hist["nav"].max()))
        nav_peak = max(peak, nav_end)
        drawdown = nav_end / nav_peak - 1.0

        max_days = pct_1d = None
        closes = self._closes_by_issuer(ctx, positions) if not w.empty else None
        if closes is not None:
            # Execução só no leilão de fechamento: liquidez em FECHAMENTOS à capacidade
            # estrutural de redução (pregão regular) da linha detida.
            vals = [closes.get(i) for i in w.index]
            if all(v is not None for v in vals):
                max_days = float(max(vals)) if vals else None
                g = float(w.abs().sum())
                pct_1d = (float(sum(abs(float(w[i])) for i, v in zip(w.index, vals, strict=True)
                                    if v <= 1.0 + 1e-9)) / g) if g > 0 else None
            else:
                alerts.append("Volume indisponível para alguma posição: fechamentos para "
                              "liquidar indeterminados.")
        elif not w.empty:
            prof = liquidity_profile(w, ctx.panel.assets["adtv_usd"], nav_end,
                                     cfg.liquidity.participation_rate)
            days = prof["days_to_liquidate"].astype(float)
            max_days = float(days.max()) if np.isfinite(days.max()) else None
            if max_days is None:
                alerts.append("ADTV indisponível para alguma posição: dias para liquidar "
                              "indeterminados.")
            summ = liquidity_summary(prof)
            if 1.0 in summ.index and _finite(summ.loc[1.0, "gross"]):
                pct_1d = float(summ.loc[1.0, "gross"])
        squeeze_high = 0
        shorts = w[w < 0]
        if not shorts.empty:
            sq = self._squeeze(ctx)
            if sq is not None:
                buckets = sq["bucket"].reindex(shorts.index)
                squeeze_high = int((buckets == "HIGH").sum())
        risk = DailyRisk(
            ex_ante_vol=ex_ante, factor_vol=factor_vol, specific_vol=specific_vol, beta=beta,
            gross=gross, net=net, long_exposure=float(w[w > 0].sum()),
            short_exposure=float(w[w < 0].sum()), n_long=int((w > 0).sum()),
            n_short=int((w < 0).sum()), var_1d_99=var, es_1d_99=es, realized_vol_21d=rv21,
            realized_vol_63d=rv63, drawdown=float(drawdown), max_days_to_liquidate=max_days,
            pct_gross_liquid_1d=pct_1d, squeeze_high_shorts=squeeze_high, exposures=exposures)
        alerts = risk_alerts(cfg, risk, has_positions=not w.empty) + alerts
        if w.empty:
            alerts.append("Carteira sem posições (100% caixa).")
        for e in exposures:
            if e.group in ("country", "sector", "style") and e.limit is not None \
                    and abs(e.net) > e.limit + 1e-9:
                label = {"country": "país", "sector": "setor", "style": "estilo"}[e.group]
                val = (fmt_pct(e.net, signed=True) if e.group != "style"
                       else fmt_num(e.net, 3, signed=True))
                lim = fmt_pct(e.limit) if e.group != "style" else fmt_num(e.limit, 3)
                alerts.append(f"Exposição líquida de {label} {e.name} {val} acima do limite "
                              f"±{lim}.")
        return risk, alerts

    def _closes_by_issuer(self, ctx: DailyContext, positions: list[DailyPosition]
                          ) -> dict[str, float | None] | None:
        """Fechamentos para zerar cada emissor detido: |valor de mercado| / capacidade
        estrutural de redução por fechamento das linhas detidas (pregão regular, ADV P25 dos 20
        pregões anteriores; :func:`cdp.portfolio.execucao.capacidade_fechamento_usd`). ``None``
        sem a seção ``execution`` (regra anterior: dias a uma participação do ADTV); valor
        ``None`` por emissor sem volume conhecido (nunca liquidez imediata)."""
        cfg = self.cfg
        if cfg.execution is None:
            return None
        held = [p for p in positions if p.market_value_usd != 0]
        tickers = sorted({p.ticker for p in held})
        key = ("cap_liquidez", tuple(tickers))
        if key not in ctx.cache:
            from ..portfolio.execucao import capacidade_fechamento_usd, janela_regular

            lines = ctx.panel.lines.reindex(tickers)
            try:
                ctx.cache[key] = capacidade_fechamento_usd(
                    lines, ctx.md, janela_regular(ctx.date, cfg), cfg, lado="long")
            except (ValueError, KeyError) as exc:
                ctx.notes.append(f"Capacidade de fechamento indisponível: {exc}")
                ctx.cache[key] = pd.Series(dtype=float)
        caps: pd.Series = ctx.cache[key]
        mv: dict[str, float] = {}
        cap: dict[str, float] = {}
        for p in held:
            mv[p.issuer_id] = mv.get(p.issuer_id, 0.0) + p.market_value_usd
            c = caps.get(p.ticker)
            cap[p.issuer_id] = cap.get(p.issuer_id, 0.0) + (float(c) if _finite(c) else 0.0)
        return {i: (abs(v) / cap[i] if cap.get(i, 0.0) > 0 else None) for i, v in mv.items()}

    def _group_exposures(self, ctx: DailyContext, w: pd.Series) -> list[ExposureLine]:
        if w.empty:
            return []
        assets = ctx.panel.assets
        out: list[ExposureLine] = []
        for group, col, limit in (("country", "country", self.cfg.risk.country_net_max_abs),
                                  ("sector", "sector", self.cfg.risk.sector_net_max_abs)):
            keys = assets[col].reindex(w.index).fillna("NA").astype(str)
            for k in sorted(keys.unique()):
                ww = w[keys == k]
                out.append(ExposureLine(group=group, name=k, long=float(ww[ww > 0].sum()),
                                        short=float(ww[ww < 0].sum()), net=float(ww.sum()),
                                        gross=float(ww.abs().sum()), limit=limit))
        return out

    def _squeeze(self, ctx: DailyContext) -> pd.DataFrame | None:
        if "squeeze" not in ctx.cache:
            try:
                ctx.cache["squeeze"] = squeeze_table(ctx.panel, ctx.md, self._availability(ctx),
                                                     self.cfg)
            except (ValueError, KeyError) as exc:
                ctx.cache["squeeze"] = None
                ctx.notes.append(f"Tabela de squeeze indisponível: {exc}")
        return ctx.cache["squeeze"]

    def _position_alerts(self, ctx: DailyContext, side: _MainSide | _ShadowSide,
                         positions: list[DailyPosition], nav_end: float,
                         proposal: Proposal | None) -> list[str]:
        cfg = self.cfg
        alerts: list[str] = []
        held = [p for p in positions if p.market_value_usd != 0]
        # Liquidez por posição (participação e limite por lado).
        adtv = ctx.panel.assets["adtv_usd"]
        by_issuer: dict[str, float] = {}
        for p in held:
            by_issuer[p.issuer_id] = by_issuer.get(p.issuer_id, 0.0) + p.market_value_usd
        illiquid: list[str] = []
        closes = self._closes_by_issuer(ctx, positions)
        for iid, mv in sorted(by_issuer.items()):
            if closes is not None:
                limit = (cfg.liquidity.max_days_to_liquidate_long if mv > 0
                         else cfg.liquidity.max_days_to_liquidate_short)
                n = closes.get(iid)
                if n is None:
                    illiquid.append(f"{iid} (volume indisponível)")
                elif n > limit + 1e-9:
                    illiquid.append(f"{iid} ({fmt_closes(n)} > {fmt_closes(limit)})")
                continue
            a = adtv.get(iid, np.nan)
            if mv > 0:
                rate = cfg.liquidity.participation_rate
                limit = cfg.liquidity.max_days_to_liquidate_long
            else:
                rate, limit = (cfg.liquidity.short_participation_rate,
                               cfg.liquidity.max_days_to_liquidate_short)
            if not (_finite(a) and a > 0):
                illiquid.append(f"{iid} (ADTV indisponível)")
                continue
            days = abs(mv) / (rate * float(a))
            if days > limit + 1e-9:
                illiquid.append(f"{iid} ({fmt_days(days)} > {fmt_days(limit)})")
        if illiquid:
            alerts.append(f"Posições acima do limite de liquidez: {_list(illiquid)}.")
        # Squeeze: shorts em HIGH (e mudança desde a decisão) e stops de perda.
        shorts = [p for p in held if p.market_value_usd < 0]
        if shorts:
            sq = self._squeeze(ctx)
            decided = {}
            if proposal is not None:
                decided = {p.issuer_id: p.squeeze_bucket for p in proposal.positions
                           if p.side == Side.SHORT}
            if sq is not None:
                for p in shorts:
                    b = sq["bucket"].get(p.issuer_id) if p.issuer_id in sq.index else None
                    if b == "HIGH":
                        was = decided.get(p.issuer_id)
                        change = (f" (era {was} na decisão)" if was and was != "HIGH" else "")
                        alerts.append(f"Short {p.ticker} ({p.issuer_id}) com risco de squeeze "
                                      f"HIGH{change}: reavaliar/reduzir.")
            current = {p.ticker: (float(p.shares), float(p.price_local)) for p in shorts
                       if p.shares is not None and p.price_local is not None}
            entries = short_entry_prices(side.track.iter_records(reverse=True), current)
            # Regra por nome (metodologia vigente): o código limita o short à metade das ações do
            # stop no rebalanceamento seguinte, uma vez por episódio, e veda a compra do emissor
            # até revisão humana; regra do livro inteiro (legado): o mandato pede o corte de 50%.
            stop_effect = ("o código limita o short à metade das ações do stop no "
                           "rebalanceamento seguinte (uma vez por episódio) e veda a compra do "
                           "emissor até revisão humana."
                           if cfg.squeeze.stop_scope == "name" else "cortar 50% da posição.")
            for p in shorts:
                avg = entries.get(p.ticker)
                if avg is None or p.price_local is None or p.shares is None:
                    continue
                loss = p.price_local / avg - 1.0
                fx = self._fx_rate(ctx, p.currency)
                loss_usd = abs(p.shares) * (p.price_local - avg) * (fx or 0.0)
                if loss >= cfg.squeeze.stop_short_position_loss:
                    limit = fmt_pct(cfg.squeeze.stop_short_position_loss)
                    alerts.append(f"STOP DE SQUEEZE: short {p.ticker} perde {fmt_pct(loss)} desde "
                                  f"a entrada (limite {limit}): {stop_effect}")
                if fx is not None and loss_usd / nav_end >= cfg.squeeze.stop_short_nav_loss:
                    alerts.append(f"STOP DE SQUEEZE: short {p.ticker} perde "
                                  f"{fmt_pct(loss_usd / nav_end)} do NAV desde a entrada (limite "
                                  f"{fmt_pct(cfg.squeeze.stop_short_nav_loss)}): {stop_effect}")
        missing = sorted(set(ctx.md.manifest.missing_tickers) & {p.ticker for p in held})
        if missing:
            alerts.append(f"Linhas da carteira ausentes na coleta de dados: {_list(missing)}.")
        return alerts

    def _input_hashes(self, ctx: DailyContext, entry: BookEntry | None,
                      proposal: Proposal | None, model_prev: RiskModel | None) -> dict[str, str]:
        h: dict[str, str] = {
            "market_data": ctx.md.manifest.content_hash(),
            "config": self.cfg.config_hash(),
        }
        if ctx.md.universe.source_sha256:
            h["universe"] = ctx.md.universe.source_sha256
        h.update(store_input_hashes(self.store, ctx.date))
        if entry is not None:
            h["book_entry"] = sha256_obj(entry)
            h["approval"] = entry.approval_hash
        if proposal is not None:
            h["proposal"] = proposal.proposal_hash()
        if ctx.model is not None:
            h["risk_model"] = _meta_hash(ctx.model)
        if model_prev is not None:
            h["risk_model_prev"] = _meta_hash(model_prev)
        return h


# ==========================================================
# Funções auxiliares de módulo
# ==========================================================

def marked_financing(nav_start: float, rate_annual: float, days: int) -> float:
    """Juros do caixa/colateral: NAV inicial × taxa / 360 × dias corridos (ACT/360)."""
    return float(nav_start) * float(rate_annual) / DAY_COUNT_BASIS * int(days)


def _merge_execution(old: list[_Line], execs: list[_Exec]) -> list[_Line]:
    """Posições de fim de dia após a execução: continuadas, encerradas (valor 0) e novas."""
    new = {(e.issuer_id, e.ticker): e for e in execs}
    out: list[_Line] = []
    for ln in old:
        e = new.pop((ln.issuer_id, ln.ticker), None)
        if e is None:
            out.append(_Line(ln.issuer_id, ln.ticker, ln.currency, 0.0, ln.mv_start, ln.pnl,
                             ln.ret, ln.repriced, 0.0, ln.price_local, ln.price_usd))
        else:
            px_usd = (e.price_local * e.fx if e.value is None else ln.price_usd)
            out.append(_Line(ln.issuer_id, ln.ticker, e.currency, float(e.shares), ln.mv_start,
                             ln.pnl, ln.ret, ln.repriced, e.mv, e.price_local, px_usd))
    for e in execs:
        if (e.issuer_id, e.ticker) in new:
            out.append(_Line(e.issuer_id, e.ticker, e.currency, float(e.shares), 0.0, 0.0, 0.0,
                             True, e.mv, e.price_local, e.price_local * e.fx))
    return out


def _lapse_alert(lapsed: Mapping[str, Any], *, inaugural: bool) -> str:
    """Alerta do registro do dia em que a efetivação foi recusada (decisão caducada)."""
    semana = date.fromisoformat(str(lapsed.get("semana")))
    sessao = date.fromisoformat(str(lapsed.get("sessao")))
    if inaugural:
        return (f"Efetivação recusada: a carteira inaugural decidida para {semana:%d/%m/%Y} não "
                f"foi montada no leilão de fechamento de {sessao:%d/%m/%Y} (kill switch ligado: "
                "só redução de risco). A decisão caducou; o fundo inicia o histórico em caixa e "
                "a próxima data de montagem decide de novo.")
    return (f"Efetivação recusada: a decisão da semana de {semana:%d/%m/%Y} não foi executada no "
            f"leilão de fechamento de {sessao:%d/%m/%Y} (kill switch ligado). A decisão caducou; "
            "a carteira anterior é mantida e a próxima data de montagem decide de novo.")


def _check_track_tail(track: TrackRecord, prev: DailyRecord | None) -> None:
    """O último registro (ponto de partida da marcação do dia) precisa estar íntegro: hash
    recalculado, CSV terminando nele e evento na trilha (:meth:`TrackRecord.tail_problems`)."""
    if prev is not None:
        from .risco_diario import recover

        recover(track, prev)
    problems = track.tail_problems(prev)
    if problems:
        raise ValueError(f"Track record inconsistente em {track.root}: " + " ".join(problems))


def _guarded(step: Callable[[BookEntry], object] | None, entry: BookEntry) -> None:
    """Executa um passo de efetivação; recusas (``ValueError``) viram :class:`ExecutionRefused`."""
    if step is None:
        return
    try:
        step(entry)
    except ExecutionRefused:
        raise
    except ValueError as exc:
        raise ExecutionRefused(str(exc)) from exc


def _max_finite(*values: float) -> float | None:
    """Maior valor finito (``None`` se nenhum for finito) — VaR/ES conservador sem NaN."""
    finite = [float(v) for v in values if _finite(v)]
    return max(finite) if finite else None
