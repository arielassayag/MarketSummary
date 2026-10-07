"""Backtest walk-forward semanal do núcleo quantitativo do CDP (sem LLM).

Sinais de LLM não podem ser testados honestamente dentro da janela de treino dos modelos
(docs/research/02): o backtest mede apenas o processo quantitativo — painel em USD, modelo de
risco, sinais point-in-time, alpha puro, limites por emissor e otimizador em modo de vol-alvo.
Usa o núcleo de risco do pipeline semanal ao vivo (``workflow/weekly.py``), sem visões de IA;
a execução histórica é simplificada, com limitações explícitas nas notas do resultado.

Regras point-in-time (sem look-ahead):

- O painel é montado UMA vez com todo o histórico; elegibilidade, ADTV (por linha e por emissor),
  número de observações e defasagem de preço são recalculados em cada data de informação ``d``
  com dados ``<= d`` (``panel.assets['eligible']`` é do fim da amostra e NÃO é usado).
- Rebalanceamento como ao vivo (``fund.rebalance_weekday``): com ``LAST_US_SESSION``, no ÚLTIMO
  pregão da semana na NYSE (pregões inferidos das linhas listadas nos EUA) e com informação até
  o pregão de dados anterior (calendário completo de preços); na regra legada, no PRIMEIRO
  pregão da semana da bolsa primária (``fund.primary_calendar``, B3; segunda-feira feriado na B3
  ⇒ terça), com informação até o pregão anterior da B3. Os pregões de cada bolsa são inferidos
  dos dados (dias com fechamento em ao menos metade das linhas listadas do mercado).
- ``RiskModelEstimator`` é ajustado uma vez; no rebalanceamento ``t`` usa-se ``model_at(d)``, em
  que ``d`` é a data de informação. Fatores macro são estimados com séries até ``d``; esse
  modelo base é preservado para o gate idiossincrático, e janelas de evento só alteram o
  modelo de decisão. Sinais: ``compute_signals(..., as_of=d,
  pit_only=True)``. Dados posteriores ao fim do backtest e barras provisórias (intradiárias) não
  entram.
- Short interest, aluguel B3 e escore de squeeze são retratos atuais (não PIT): só valem as
  regras de alugabilidade (ADR/US e locais BR; demais mercados não alugáveis) com taxas GC e sem
  exclusão por squeeze — viés otimista registrado nas notas.

Convenção de execução e contabilidade (frações do NAV):

- Pesos novos valem a partir do fechamento do dia de rebalanceamento (MOC); o retorno do dia
  ``t`` acumula nos pesos anteriores: ``P&L_t = Σ w_{i,t−1} r_{i,t}``.
- Emissor cuja linha primária não tem preço em ``t`` (mercado fechado/sem negócio) NÃO é
  negociado em ``t``: mantém o peso derivado até o rebalanceamento seguinte. Negociá-lo "no
  fechamento" usaria o último preço — o mesmo da data de informação (look-ahead de execução).
- Retorno ausente (``NaN``) contribui 0 naquele dia e a posição é carregada inalterada (contagem
  nas notas; nenhum retorno é inventado — o retorno após o feriado cobre o intervalo).
- Deriva: ``w_{i,t} = w_{i,t−1}(1 + r_{i,t}) / (1 + R_t)`` com ``R_t`` o retorno do NAV no dia.
- Custos (modelo de ``portfolio/costs``) sobre ``|w_alvo − w_derivado|`` no fechamento do
  rebalanceamento; aluguel ``taxa/252`` sobre os shorts; juros do caixa ``USD_3M/252`` (taxa do
  pregão anterior) sobre ``1 − exposição líquida`` (≈ NAV num livro net neutral).
- Atribuição diária com o modelo do rebalanceamento: ``fator = Σ_k x_k f_{k,t}`` com
  ``x = Bᵀ w_{t−1}`` (B mantida desde o rebalanceamento) e ``específico = P&L bruto − fator``.
"""

from __future__ import annotations

import dataclasses
import json
import math
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..alpha.combine import build_alpha, information_coefficient
from ..alpha.signals import MIN_OBS_MOMENTUM, MOMENTUM_SKIP, SIGNALS, compute_signals
from ..analytics.panel import STALE_DAYS_MAX, AssetPanel, build_asset_panel, fx_for_lines
from ..analytics.shortability import issuer_side_lines, short_availability
from ..config import FundConfig, load_config
from ..hashing import canonical_json, sha256_obj
from ..market import MarketData
from ..portfolio.costs import CostModel, build_cost_model, estimate_rebalance_costs
from ..portfolio.optimizer import (
    RISK_TARGET_MODES,
    build_asset_constraints,
    metodologia_ativa,
    model_implied_betas,
    optimize,
)
from ..risk.event_scaling import active_event_windows, apply_event_windows
from ..risk.exposures import historical_mcap, market_weights
from ..risk.idio import fatia_idio, kappa_f
from ..risk.macro import augment_with_macro, macro_factor, macro_returns
from ..risk.model import MIN_FACTOR_OBS, RiskModelEstimator
from ..risk.types import TRADING_DAYS, RiskModel
from .metrics import deflated_sharpe_ratio, ic_summary, performance_metrics

DEFAULT_SIGNALS: tuple[str, ...] = ("residual_momentum", "short_term_reversal", "low_risk")
RATE_SERIES = "USD_3M"
RATE_FFILL_LIMIT = 10
"""Pregões máximos de propagação da taxa de juros (feriados); além disso a taxa é ausente."""
ADTV_MIN_OBS = 21
"""Mínimo de pregões com valor negociado na janela de ADTV point-in-time."""
DAILY_VOL_WINDOW = 63
"""Janela da volatilidade diária usada no impacto de mercado (igual ao pipeline ao vivo)."""
MIN_ELIGIBLE = 10
"""Mínimo de emissores elegíveis (com modelo) para rebalancear; abaixo disso mantém a carteira."""
ASSUMED_SQUEEZE_BUCKET = "LOW"
"""Bucket de squeeze assumido no backtest (sem dado PIT): nenhum short é vetado por squeeze."""
INACCURATE_WARNING = "Solution may be inaccurate"
MAX_ANNUAL_RATE = 1.0
"""Taxa anual acima disso (100% a.a.) indica série em % e não em decimal: erro explícito."""
SESSION_MIN_SHARE = 0.5
"""Fração mínima das linhas locais listadas com fechamento para o dia contar como pregão."""
PRIMARY_MARKET_BY_CALENDAR = {"BVMF": "BR", "XMEX": "MX", "XSGO": "CL", "XBOG": "CO",
                              "XLIM": "PE", "XBUE": "AR", "XNYS": "US"}
"""Mercado das linhas cujo calendário de pregões define o rebalanceamento (``primary_calendar``)."""
FROZEN_REASON = "mercado_fechado_no_rebalanceamento"

DAILY_COLUMNS = ["ret_net", "ret_gross", "cost", "borrow", "financing", "factor_pnl",
                 "specific_pnl", "nav", "gross", "net", "rebalance"]
WEEKLY_COLUMNS = ["info_date", "status", "ex_ante_vol", "vol_target", "gross", "net", "beta",
                  "n_long", "n_short", "turnover", "cost", "expected_alpha", "alpha_scale",
                  "relaxations", "n_eligible", "n_alpha", "n_frozen", "event_window",
                  "ex_ante_vol_base", "idio_decisao", "idio_base", "kappa_f", "kappa_source",
                  "idio_share_goal", "idio_share_floor", "macro_factors", "macro_missing"]
COMPOSITE_IC = "composite"

ProgressFn = Callable[[int, int, str], None]


# ==========================================================
# Configuração e resultado
# ==========================================================

@dataclass(frozen=True)
class BacktestConfig:
    """Parâmetros do backtest (o mandato vem de ``FundConfig``).

    - ``signal_weights``: pesos dos sinais; ausente ⇒ pesos da configuração restritos a
      ``signal_names`` (renormalizados; se nenhum tiver peso, pesos iguais).
    - ``vol_target``: meta ex-ante passada ao otimizador; ausente ⇒
      ``vol_target_annual / bias_prior`` (como no pipeline ao vivo no início do track record).
    - ``risk_target_mode``: ``"match"`` (padrão: usa o orçamento de risco) ou ``"cap"``.
    - ``n_trials``: número de configurações testadas até chegar a esta (Deflated Sharpe).
    - ``include_*``: ligam custos, aluguel e juros do caixa na CONTABILIDADE (o otimizador
      sempre considera custos e aluguel no objetivo, como ao vivo).
    - ``themes``: tema → emissores com neutralidade própria (limites em
      ``risk.theme_net_max_abs``); ausente ⇒ o mesmo arquivo de temas do pipeline ao vivo;
      ``{}`` ⇒ sem temas.
    """

    start: date
    end: date | None = None
    signal_names: tuple[str, ...] = DEFAULT_SIGNALS
    signal_weights: dict[str, float] | None = None
    nav: float = 100e6
    include_costs: bool = True
    include_borrow: bool = True
    include_financing: bool = True
    exposure_refresh_days: int = 5
    vol_target: float | None = None
    risk_target_mode: str = "match"
    n_trials: int = 1
    themes: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        start = pd.Timestamp(self.start).date()
        end = None if self.end is None else pd.Timestamp(self.end).date()
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        names = tuple(str(n) for n in self.signal_names)
        object.__setattr__(self, "signal_names", names)
        if end is not None and end <= start:
            raise ValueError(f"Fim do backtest ({end}) precisa ser posterior ao início ({start}).")
        if not names:
            raise ValueError("Informe ao menos um sinal.")
        unknown = [n for n in names if n not in SIGNALS]
        if unknown:
            raise ValueError(f"Sinais desconhecidos: {unknown}. Disponíveis: {list(SIGNALS)}")
        non_pit = [n for n in names if not SIGNALS[n].point_in_time]
        if non_pit:
            raise ValueError(f"Sinais não point-in-time não podem entrar no backtest: {non_pit} "
                             "(retrato atual de fundamentos/consenso).")
        if len(set(names)) != len(names):
            raise ValueError(f"Sinais duplicados: {list(names)}")
        if self.signal_weights is not None:
            extra = sorted(set(self.signal_weights) - set(names))
            if extra:
                raise ValueError(f"Pesos para sinais fora de signal_names: {extra}")
            for k, v in self.signal_weights.items():
                numeric = isinstance(v, int | float | np.integer | np.floating) \
                    and not isinstance(v, bool | np.bool_)
                if not (numeric and math.isfinite(float(v)) and v >= 0):
                    raise ValueError(f"Peso inválido para o sinal '{k}': {v!r}.")
        if not (math.isfinite(float(self.nav)) and self.nav > 0):
            raise ValueError("NAV inicial precisa ser positivo.")
        if self.exposure_refresh_days < 1:
            raise ValueError("exposure_refresh_days precisa ser >= 1.")
        if self.risk_target_mode not in RISK_TARGET_MODES:
            raise ValueError(f"risk_target_mode inválido: {self.risk_target_mode!r} "
                             f"(use {RISK_TARGET_MODES}).")
        if self.n_trials < 1:
            raise ValueError("n_trials precisa ser >= 1.")
        if self.vol_target is not None and not (math.isfinite(self.vol_target)
                                                and self.vol_target > 0):
            raise ValueError("vol_target precisa ser positivo.")
        if self.themes is not None:
            if not isinstance(self.themes, Mapping):
                raise ValueError("themes precisa ser um dicionário tema -> lista de emissores.")
            clean: dict[str, list[str]] = {}
            for k, v in self.themes.items():
                if isinstance(v, str) or not all(isinstance(x, str) for x in v):
                    raise ValueError(f"Membros do tema '{k}' precisam ser uma lista de emissores.")
                clean[str(k)] = sorted(set(v))
            object.__setattr__(self, "themes", clean)

    def effective_vol_target(self, cfg: FundConfig) -> float:
        """Meta ex-ante usada no otimizador (sempre dentro da banda do mandato)."""
        rk = cfg.risk
        if self.vol_target is not None:
            vt = float(self.vol_target)
            if not (rk.vol_band_min - 1e-12 <= vt <= rk.vol_band_max + 1e-12):
                raise ValueError(f"vol_target {vt:.2%} fora da banda "
                                 f"[{rk.vol_band_min:.2%}, {rk.vol_band_max:.2%}].")
            return vt
        return max(rk.vol_target_annual / rk.bias_prior, rk.vol_band_min)

    def effective_signal_weights(self, cfg: FundConfig) -> dict[str, float]:
        """Pesos normalizados (soma 1) dos sinais do backtest."""
        src = self.signal_weights if self.signal_weights is not None \
            else cfg.alpha.signal_weights
        w = {n: float(src.get(n, 0.0)) for n in self.signal_names}
        if self.signal_weights is not None and not any(v > 0 for v in w.values()):
            raise ValueError("Nenhum sinal do backtest tem peso positivo.")
        if not any(v > 0 for v in w.values()):
            w = dict.fromkeys(self.signal_names, 1.0)
        total = sum(w.values())
        return {n: v / total for n, v in w.items() if v > 0}


@dataclass
class BacktestResult:
    """Resultado do backtest.

    - ``daily``: ``ret_net``, ``ret_gross``, ``cost``, ``borrow``, ``financing`` (frações do NAV
      do dia anterior), ``factor_pnl``, ``specific_pnl`` (``NaN`` em dias sem regressão
      fatorial ou com retorno macro ausente), ``nav`` (USD), ``gross``/``net`` (após o
      fechamento) e ``rebalance``.
    - ``weekly`` (por data de rebalanceamento): ``ex_ante_vol``, ``gross``, ``net``, ``beta``,
      ``n_long``, ``n_short``, ``turnover`` (executado), ``expected_alpha``, ``status``,
      ``relaxations`` e diagnósticos. Inclui vol base, fatia idiossincrática por modelo,
      κ_F/meta/piso e fatores macro usados/ausentes; sem gate ativo a fatia permanece ausente.
    - ``weights``: pesos-alvo por data de rebalanceamento × emissor (0 = sem posição).
    - ``ic``: IC de Spearman por data × sinal (z do sinal em ``d`` contra a soma dos retornos
      específicos da semana seguinte); coluna ``composite`` = alpha puro.
    - ``provenance``: hashes SHA-256 dos dados (manifesto), da configuração do fundo e dos
      resultados (:func:`results_hash`), parâmetros do backtest e aviso de dados — permite
      reproduzir e detectar adulteração dos números exportados.
    """

    daily: pd.DataFrame
    weekly: pd.DataFrame
    weights: pd.DataFrame
    ic: pd.DataFrame
    metrics: dict[str, float]
    notes: list[str]
    config: BacktestConfig | None = None
    is_synthetic: bool = False
    data_notice: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def ic_stats(self) -> pd.DataFrame:
        """Resumo do IC por sinal (média, desvio, ICIR, t, taxa de acerto)."""
        return ic_summary(self.ic)


# ==========================================================
# Calendário e insumos point-in-time
# ==========================================================

def rebalance_dates(calendar: pd.DatetimeIndex, start: date | pd.Timestamp,
                    end: date | pd.Timestamp | None = None,
                    rule: str = "first") -> pd.DatetimeIndex:
    """Dia de rebalanceamento de cada semana do ``calendar``: o primeiro pregão (``rule="first"``,
    segunda; feriado ⇒ próximo pregão) ou o último (``rule="last"``, sexta; feriado ⇒ pregão
    anterior).

    O motor passa os pregões da bolsa de rebalanceamento (:func:`primary_sessions`). Só entram
    semanas cujo dia de rebalanceamento está em ``[start, end]``.
    """
    if rule not in ("first", "last"):
        raise ValueError(f"Regra de rebalanceamento desconhecida: {rule!r}")
    cal = pd.DatetimeIndex(calendar).sort_values().unique()
    if cal.empty:
        return pd.DatetimeIndex([], name="date")
    grp = pd.Series(cal, index=cal).groupby(cal.to_period("W-SUN"))
    firsts = grp.min() if rule == "first" else grp.max()
    out = pd.DatetimeIndex(firsts.to_numpy())
    lo = pd.Timestamp(start)
    hi = pd.Timestamp(end) if end is not None else cal[-1]
    return pd.DatetimeIndex(out[(out >= lo) & (out <= hi)], name="date")


def rebalance_rule(cfg: FundConfig) -> tuple[str, str]:
    """``(regra, calendário)`` do backtest: ``("last", XNYS)`` com ``LAST_US_SESSION``;
    ``("first", fund.primary_calendar)`` na regra legada."""
    if cfg.fund.rebalance_weekday == "LAST_US_SESSION":
        code = cfg.execution.rebalance_calendar if cfg.execution is not None else "XNYS"
        return "last", str(code)
    return "first", str(cfg.fund.primary_calendar)


def primary_sessions(md: MarketData, cfg: FundConfig,
                     calendar_code: str | None = None) -> pd.DatetimeIndex:
    """Pregões da bolsa primária (``fund.primary_calendar``, B3) inferidos dos dados de preço.

    Uma data do calendário de preços é pregão quando ao menos ``SESSION_MIN_SHARE`` das linhas
    do mercado primário listadas na data (entre o primeiro e o último fechamento válido da
    linha) têm fechamento. Datas sem nenhuma linha listada, ou universo sem linhas do mercado
    primário, seguem o calendário completo de preços (sem informação de feriado).
    """
    cal = pd.DatetimeIndex(md.close.index).sort_values()
    code = calendar_code or str(cfg.fund.primary_calendar)
    market = PRIMARY_MARKET_BY_CALENDAR.get(code.upper())
    lines = md.universe.lines
    if market is None or "market" not in lines.columns:
        return cal
    cols = [t for t in lines.index[lines["market"].astype(str) == market]
            if t in md.close.columns]
    valid = md.close.reindex(index=cal, columns=cols).notna()
    valid = valid.loc[:, valid.any()]
    if valid.shape[1] == 0:
        return cal
    v = valid.to_numpy(dtype=np.int8)
    started = np.maximum.accumulate(v, axis=0)
    not_ended = np.maximum.accumulate(v[::-1], axis=0)[::-1]
    listed = pd.Series((started * not_ended).sum(axis=1), index=cal)
    trading = pd.Series(v.sum(axis=1), index=cal)
    is_session = (listed == 0) | (trading >= SESSION_MIN_SHARE * listed)
    return pd.DatetimeIndex(cal[is_session.to_numpy()], name=cal.name)


def _last_valid_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada data, a última data ``<=`` ela com valor não ausente (``NaT`` se nenhuma)."""
    mask = df.notna().to_numpy()
    idx = df.index.to_numpy(dtype="datetime64[ns]")
    vals = np.where(mask, idx[:, None], np.datetime64("NaT", "ns"))
    return pd.DataFrame(vals, index=df.index, columns=df.columns).ffill()


def line_traded_value_usd(md: MarketData) -> pd.DataFrame:
    """Valor negociado diário em USD por linha (mesma regra do painel: volume 0 = ausente)."""
    fx = fx_for_lines(md)
    lines = md.universe.lines
    cal = md.close.index
    out: dict[str, pd.Series] = {}
    for tkr in lines.index:
        ccy = lines.loc[tkr, "currency"]
        if tkr not in md.close.columns or ccy not in fx.columns:
            continue
        vol = md.volume[tkr] if tkr in md.volume.columns else pd.Series(np.nan, index=cal)
        out[tkr] = md.close[tkr] * vol.where(vol > 0) * fx[ccy]
    return pd.DataFrame(out, index=cal).reindex(columns=list(lines.index))


def rf_daily_series(md: MarketData, calendar: pd.DatetimeIndex,
                    series: str = RATE_SERIES) -> pd.Series | None:
    """Juro diário (taxa anual do pregão ANTERIOR / 252) alinhado ao calendário.

    ``None`` se ``md.rates`` não tem a série. Datas sem taxa conhecida ficam ``NaN``. Taxas
    acima de ``MAX_ANNUAL_RATE`` (série em % em vez de decimal) são erro explícito.
    """
    rates = md.rates
    if rates is None or rates.empty or series not in rates.columns:
        return None
    s = pd.to_numeric(rates[series], errors="coerce").dropna().sort_index()
    if len(s) and float(s.abs().max()) > MAX_ANNUAL_RATE:
        raise ValueError(f"Série {series} com taxa de {float(s.abs().max()):g} a.a.: as taxas "
                         "precisam estar em decimal (0,05 = 5% a.a.), não em %.")
    s = s[~s.index.duplicated(keep="last")]
    idx = pd.DatetimeIndex(calendar).union(s.index)
    s = s.reindex(idx).ffill(limit=RATE_FFILL_LIMIT).reindex(calendar)
    return (s.shift(1) / TRADING_DAYS).rename("rf_daily")


class PointInTimeInputs:
    """Elegibilidade, liquidez e capitalização por data usando apenas dados ``<=`` a data.

    Pré-computa (uma vez) médias móveis de valor negociado em USD por linha e por emissor,
    contagem de observações, última data com preço e capitalização histórica; ``assets_at`` e
    ``lines_at`` devolvem tabelas no formato de ``AssetPanel.assets``/``AssetPanel.lines``.
    """

    def __init__(self, panel: AssetPanel, md: MarketData, cfg: FundConfig) -> None:
        self.panel = panel
        self.cfg = cfg
        self.calendar = pd.DatetimeIndex(panel.returns.index)
        self.issuers = list(panel.assets.index)
        win = cfg.liquidity.adv_window_days
        minp = min(ADTV_MIN_OBS, win)
        tv = panel.traded_value_usd.reindex(index=self.calendar, columns=self.issuers)
        self.issuer_adtv = tv.rolling(win, min_periods=minp).mean()
        ltv = line_traded_value_usd(md).reindex(self.calendar)
        self.line_adtv = ltv.rolling(win, min_periods=minp).mean()
        rets = panel.returns.reindex(columns=self.issuers)
        self.n_obs = rets.notna().rolling(cfg.risk_model.history_days, min_periods=1).sum()
        self.issuer_last = _last_valid_dates(panel.price_usd.reindex(columns=self.issuers))
        close = md.close.reindex(index=self.calendar, columns=list(md.universe.lines.index))
        self.line_last = _last_valid_dates(close)
        self.mcap = historical_mcap(panel, self.issuers).reindex(self.calendar)
        self.base_lines = md.universe.lines.copy()

    def assets_at(self, pos: int) -> pd.DataFrame:
        """Tabela por emissor (formato ``AssetPanel.assets``) com elegibilidade PIT em ``pos``."""
        ts = self.calendar[pos]
        src = self.panel.assets
        a = pd.DataFrame(index=pd.Index(self.issuers, name="issuer_id"))
        for col in ("issuer_name", "country", "sector", "primary_ticker", "primary_currency"):
            a[col] = src[col].reindex(a.index)
        a["market_cap_usd"] = self.mcap.iloc[pos].reindex(a.index).astype(float)
        a["adtv_usd"] = self.issuer_adtv.iloc[pos].reindex(a.index).astype(float)
        a["n_obs"] = self.n_obs.iloc[pos].reindex(a.index).astype(float)
        last = pd.to_datetime(self.issuer_last.iloc[pos].reindex(a.index))
        a["last_date"] = last
        liq, rm = self.cfg.liquidity, self.cfg.risk_model
        no_data = last.isna()
        stale = ~no_data & ((ts - last).dt.days > STALE_DAYS_MAX)
        low_adtv = ~(a["adtv_usd"] >= liq.min_adtv_usd)
        short_hist = a["n_obs"] < rm.min_obs_days
        reasons = []
        for i in a.index:
            r = []
            if no_data[i]:
                r.append("sem_dados")
            elif stale[i]:
                r.append("preco_defasado")
            if low_adtv[i]:
                r.append("adtv_baixo")
            if short_hist[i]:
                r.append("historico_curto")
            reasons.append(";".join(r))
        a["exclusion_reason"] = reasons
        a["eligible"] = a["exclusion_reason"] == ""
        return a

    def lines_at(self, pos: int) -> pd.DataFrame:
        """Tabela por linha (formato ``AssetPanel.lines``) com ADTV e dado de preço PIT."""
        ts = self.calendar[pos]
        lines = self.base_lines.copy()
        lines["adtv_usd"] = self.line_adtv.iloc[pos].reindex(lines.index).astype(float)
        last = pd.to_datetime(self.line_last.iloc[pos].reindex(lines.index))
        lines["last_date"] = last
        lines["has_data"] = (last.notna() & ((ts - last).dt.days <= STALE_DAYS_MAX)).astype(bool)
        return lines


def earliest_start(md: MarketData, cfg: FundConfig) -> date:
    """Primeiro rebalanceamento (1º pregão da semana na B3) com histórico suficiente para o
    modelo de risco e os sinais PIT."""
    cal = pd.DatetimeIndex(md.close.index).sort_values()
    need = max(cfg.risk_model.min_obs_days, MIN_FACTOR_OBS, MIN_OBS_MOMENTUM + MOMENTUM_SKIP) + 1
    if len(cal) <= need + 1:
        raise ValueError(f"Histórico curto demais para o backtest ({len(cal)} pregões; "
                         f"são necessários mais de {need + 1}).")
    rule, code = rebalance_rule(cfg)
    reb = rebalance_dates(primary_sessions(md, cfg, code), cal[need + 1], rule=rule)
    if reb.empty:
        raise ValueError("Sem segunda-feira disponível após o histórico mínimo.")
    return reb[0].date()


# ==========================================================
# Contabilidade (livro em frações do NAV)
# ==========================================================

@dataclass(frozen=True)
class _Mark:
    gross: float
    financing: float
    borrow: float
    pre: float              # retorno do NAV antes de custos de negociação
    w_pre: np.ndarray       # pesos derivados no fechamento (antes de negociar)
    n_missing: int          # posições com retorno ausente no dia (carregadas inalteradas)


class _Book:
    """Livro diário: marca pesos, acumula P&L e deriva pesos (mesma regra no motor e na réplica)."""

    def __init__(self, n_assets: int, nav: float) -> None:
        self.w = np.zeros(n_assets)
        self.nav = float(nav)

    def mark(self, r: np.ndarray, rf_daily: float, fee_annual: np.ndarray) -> _Mark:
        finite = np.isfinite(r)
        rr = np.where(finite, r, 0.0)  # retorno ausente: posição carregada inalterada
        n_missing = int(np.sum((self.w != 0) & ~finite))
        gross = float(self.w @ rr)
        financing = float((1.0 - self.w.sum()) * rf_daily)
        short = np.where(self.w < 0, -self.w, 0.0)
        borrow = float(short @ fee_annual) / TRADING_DAYS
        pre = gross + financing - borrow
        w_pre = self.w * (1.0 + rr) / (1.0 + pre)
        return _Mark(gross, financing, borrow, pre, w_pre, n_missing)

    def close(self, mark: _Mark, w_new: np.ndarray | None, trade_cost: float) -> tuple[float, float]:
        """Fecha o dia; ``trade_cost`` em fração do NAV pré-negociação. Retorna (R_t, custo)."""
        cost = float(trade_cost) * (1.0 + mark.pre)  # em fração do NAV do dia anterior
        ret = mark.pre - cost
        self.nav *= 1.0 + ret
        self.w = mark.w_pre.copy() if w_new is None else np.asarray(w_new, dtype=float).copy()
        return ret, cost


def _as_vector(value: float | pd.Series, columns: pd.Index, what: str) -> np.ndarray:
    if isinstance(value, pd.Series):
        v = pd.to_numeric(value, errors="coerce").reindex(columns)
        if v.isna().any():
            raise ValueError(f"{what} ausente para: {list(v.index[v.isna()])}")
        return v.to_numpy(dtype=float)
    return np.full(len(columns), float(value))


def simulate_weights(
    returns: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    nav: float = 1.0,
    cost_rate: float | pd.Series = 0.0,
    borrow_fee: float | pd.Series = 0.0,
    rf_annual: float | pd.Series | None = None,
) -> pd.DataFrame:
    """Contabilidade diária de uma sequência de pesos-alvo com a convenção do backtest.

    ``targets``: data de rebalanceamento × ativo (aplicados no fechamento da data); ativos sem
    coluna em ``targets`` têm alvo 0. ``cost_rate``: custo linear por unidade negociada;
    ``borrow_fee``: taxa anual sobre shorts; ``rf_annual``: juro anual do caixa (escalar ou
    série por data, aplicado com a taxa do pregão anterior). Começa (com caixa) na primeira
    data de ``targets``. Mesmas colunas de ``BacktestResult.daily`` sem a atribuição.
    """
    rets = returns.sort_index()
    cols = rets.columns
    tg = targets.sort_index()
    extra = sorted(set(tg.columns) - set(cols))
    if extra:
        raise KeyError(f"Alvos para ativos sem retorno: {extra}")
    if tg.isna().any().any():
        raise ValueError("Pesos-alvo com NaN: posição desconhecida não vira zero.")
    missing_dates = [d for d in tg.index if d not in rets.index]
    if missing_dates:
        raise KeyError(f"Datas de rebalanceamento fora do calendário: {missing_dates}")
    tg = tg.reindex(columns=cols, fill_value=0.0)
    cost_v = _as_vector(cost_rate, cols, "Custo")
    fee_v = _as_vector(borrow_fee, cols, "Taxa de aluguel")
    days = rets.index[rets.index >= tg.index[0]]
    if rf_annual is None:
        rf = pd.Series(0.0, index=rets.index)
    elif isinstance(rf_annual, pd.Series):
        rf = (pd.to_numeric(rf_annual, errors="coerce").reindex(rets.index).shift(1)
              / TRADING_DAYS)
        missing = rf.reindex(days).isna()
        if missing.any():
            bad = [str(d.date()) for d in days[missing.to_numpy()]][:5]
            raise ValueError(f"Taxa de juros ausente (pregão anterior) em dias simulados: {bad}")
    else:
        rf = pd.Series(float(rf_annual) / TRADING_DAYS, index=rets.index)
    book = _Book(len(cols), nav)
    rows = []
    for t in days:
        mark = book.mark(rets.loc[t].to_numpy(dtype=float), float(rf.loc[t]), fee_v)
        is_reb = t in tg.index
        w_new = tg.loc[t].to_numpy(dtype=float) if is_reb else None
        trade = float(cost_v @ np.abs(w_new - mark.w_pre)) if is_reb else 0.0
        ret, cost = book.close(mark, w_new, trade)
        rows.append({"ret_net": ret, "ret_gross": mark.gross, "cost": cost,
                     "borrow": mark.borrow, "financing": mark.financing, "nav": book.nav,
                     "gross": float(np.abs(book.w).sum()), "net": float(book.w.sum()),
                     "rebalance": is_reb})
    return pd.DataFrame(rows, index=pd.DatetimeIndex(days, name="date"))


# ==========================================================
# Decisão semanal
# ==========================================================

@dataclass
class _Decision:
    status: str
    weights: pd.Series | None = None          # alvo (None = manter a carteira)
    record: dict = field(default_factory=dict)
    fees: pd.Series | None = None
    cost_model: CostModel | None = None
    model: RiskModel | None = None
    signal_z: pd.DataFrame | None = None
    alpha: pd.Series | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class _Context:
    md: MarketData
    md_no_borrow: MarketData
    cfg: FundConfig
    bt: BacktestConfig
    panel: AssetPanel
    pit: PointInTimeInputs
    est: RiskModelEstimator
    vol_target: float
    signal_weights: dict[str, float]
    squeeze: pd.DataFrame
    limit_fns: tuple[Callable, Callable]
    themes: dict[str, list[str]] = field(default_factory=dict)


def _live_limit_functions() -> tuple[Callable, Callable]:
    """Limites adicionais do pipeline ao vivo (ADTV mínimo por lado e teto de risco por nome)."""
    from ..workflow.weekly import apply_liquidity_minimums, apply_specific_risk_caps

    return apply_liquidity_minimums, apply_specific_risk_caps


def _resolve_themes(bt: BacktestConfig, cfg: FundConfig,
                    issuers: list[str]) -> tuple[dict[str, list[str]], str]:
    """Temas neutros aplicados (os do pipeline ao vivo por padrão) e a nota correspondente."""
    if bt.themes is None:
        from ..workflow.weekly import load_themes

        raw = load_themes()
        origin = "arquivo de temas do pipeline ao vivo"
    else:
        raw = bt.themes
        origin = "informados no backtest"
    limits = cfg.risk.theme_net_max_abs
    universe = set(issuers)
    themes = {t: sorted(set(m) & universe) for t, m in raw.items() if t in limits}
    themes = {t: m for t, m in themes.items() if m}
    if not themes:
        return {}, (f"Temas neutros ({origin}): nenhum tema com limite no mandato e membros no "
                    "universo; restrição de tema não aplicada.")
    desc = ", ".join(f"{t} (|líquido| ≤ {limits[t]:.2%} NAV, {len(m)} emissores)"
                     for t, m in sorted(themes.items()))
    return themes, f"Temas neutros ({origin}), como ao vivo: {desc}."


def _freeze_untradable(cons: pd.DataFrame, frozen: frozenset[str], current: pd.Series | None,
                       cfg: FundConfig) -> tuple[pd.DataFrame, int]:
    """Emissores sem preço da linha primária no dia do rebalanceamento não são negociados.

    ``max_trade``/``max_trade_liq`` = 0 (peso igual ao atual) e tetos ampliados até a posição
    atual para que mantê-la seja viável; short mantido sem taxa usa a taxa máxima do mandato
    (conservador). Retorna a tabela e o número de emissores congelados nela.
    """
    idx = cons.index[cons.index.isin(sorted(frozen))]
    if len(idx) == 0:
        return cons, 0
    c = cons.copy()
    w0 = (pd.to_numeric(current, errors="coerce").reindex(idx).fillna(0.0)
          if current is not None else pd.Series(0.0, index=idx)).astype(float)
    c.loc[idx, "max_trade"] = 0.0
    if "max_trade_liq" in c.columns:
        c.loc[idx, "max_trade_liq"] = 0.0
    c.loc[idx, "max_long"] = np.maximum(c.loc[idx, "max_long"].astype(float),
                                        w0.clip(lower=0.0))
    c.loc[idx, "max_short"] = np.maximum(c.loc[idx, "max_short"].astype(float),
                                         (-w0).clip(lower=0.0))
    fee = pd.to_numeric(c.loc[idx, "borrow_fee"], errors="coerce")
    no_fee = idx[((w0 < 0) & fee.isna()).to_numpy()]
    c.loc[no_fee, "borrow_fee"] = cfg.shorting.max_borrow_fee
    if "reasons" in c.columns:
        c.loc[idx, "reasons"] = [";".join(x for x in (str(r or ""), FROZEN_REASON) if x)
                                 for r in c.loc[idx, "reasons"]]
    return c, len(idx)


def _held_stats(model: RiskModel | None, w: pd.Series, betas: pd.Series | None, *,
                model_base: RiskModel | None = None, kappa: float | None = None) -> dict:
    out = {"ex_ante_vol": float("nan"), "beta": float("nan")}
    w = w[w != 0]
    if model is None:
        return out
    if w.empty:
        out["beta"] = 0.0
    try:
        out["ex_ante_vol"] = model.portfolio_vol(w)
        if model_base is not None:
            out["ex_ante_vol_base"] = model_base.portfolio_vol(w)
        if kappa is not None:
            out["idio_decisao"] = fatia_idio(w, model, kappa)["idio"]
            if model_base is not None:
                out["idio_base"] = fatia_idio(w, model_base, kappa)["idio"]
    except KeyError:
        pass
    if betas is not None and set(w.index) <= set(betas.index):
        out["beta"] = float(betas.reindex(w.index) @ w)
    return out


def _decide(ctx: _Context, t: pd.Timestamp, pos_d: int, w_cur: pd.Series, nav: float,
            inception: bool, frozen: frozenset[str] = frozenset()) -> _Decision:
    """Carteira-alvo do rebalanceamento ``t`` com dados até o pregão ``pos_d`` (sem look-ahead).

    ``frozen``: emissores cuja linha primária não negocia em ``t`` (não podem ser negociados).
    """
    cfg, bt, panel = ctx.cfg, ctx.bt, ctx.panel
    d = ctx.pit.calendar[pos_d]
    record: dict = {"info_date": d, "vol_target": ctx.vol_target}
    held = w_cur[w_cur != 0]

    try:
        model_base = ctx.est.model_at(d)
    except ValueError as exc:
        record.update(_held_stats(None, held, None))
        return _Decision("manter:sem_modelo", record=record,
                         notes=[f"{t.date()}: modelo de risco indisponível ({exc})."])
    windows = active_event_windows(cfg, t.date())
    model_base = augment_with_macro(model_base, ctx.md, cfg, panel)
    model = apply_event_windows(model_base, panel.assets["country"], cfg, t.date())
    record["event_window"] = "; ".join(str(w.get("name", w.get("country"))) for w in windows)
    mac = model_base.meta.get("macro", {})
    record["macro_factors"] = "; ".join(mac.get("fatores", []))
    record["macro_missing"] = "; ".join(mac.get("ausentes", []))
    kappa = None
    if metodologia_ativa(cfg):
        kappa, kinfo = kappa_f(model_base, cfg)
        record.update({"kappa_f": kappa, "kappa_source": kinfo["fonte"],
                       "idio_share_goal": cfg.risk.idio_share_goal,
                       "idio_share_floor": cfg.risk.idio_share_floor})

    def held_stats(betas: pd.Series | None) -> dict:
        return _held_stats(model, held, betas, model_base=model_base, kappa=kappa)

    assets = ctx.pit.assets_at(pos_d)
    in_model = set(model.assets)
    eligible = [i for i in assets.index[assets["eligible"]] if i in in_model]
    record["n_eligible"] = len(eligible)
    betas: pd.Series | None = None
    try:
        mkt_w = market_weights(panel, model.assets, date=d)
        betas = model_implied_betas(model, mkt_w)
    except ValueError as exc:
        record.update(held_stats(None))
        return _Decision("manter:sem_pesos_de_mercado", record=record, model=model,
                         notes=[f"{t.date()}: pesos de mercado indisponíveis ({exc})."])
    if len(eligible) < MIN_ELIGIBLE:
        record.update(held_stats(betas))
        return _Decision("manter:poucos_elegiveis", record=record, model=model,
                         notes=[f"{t.date()}: {len(eligible)} emissores elegíveis "
                                f"(< {MIN_ELIGIBLE}); carteira mantida."])

    signals = compute_signals(panel, ctx.md, model, d, eligible, names=list(bt.signal_names),
                              pit_only=True)
    try:
        alpha = build_alpha(signals, model, cfg, weights=ctx.signal_weights,
                            sector=panel.assets["sector"])
    except ValueError as exc:
        record.update(held_stats(betas))
        return _Decision("manter:sem_alpha", record=record, model=model,
                         notes=[f"{t.date()}: alpha indisponível ({exc})."])
    record["n_alpha"] = len(alpha.included)
    if not alpha.included:
        record.update(held_stats(betas))
        return _Decision("manter:sem_alpha", record=record, model=model,
                         signal_z=alpha.signal_z, alpha=alpha.alpha,
                         notes=[f"{t.date()}: nenhum emissor com alpha definido."])

    pit_panel = dataclasses.replace(panel, lines=ctx.pit.lines_at(pos_d), assets=assets)
    availability = short_availability(pit_panel, ctx.md_no_borrow, cfg)
    sides = issuer_side_lines(pit_panel, availability)
    current = held if len(held) else None
    liq_min, spec_caps = ctx.limit_fns
    cons = build_asset_constraints(alpha.included, sides, ctx.squeeze, None, betas, assets, cfg,
                                   nav, current=current, inception=inception)
    cons = liq_min(cons, cfg, nav)
    cons = spec_caps(cons, model.specific_vol, cfg, ctx.vol_target)
    cons, _ = _freeze_untradable(cons, frozen, current, cfg)
    daily_vol = panel.returns.iloc[max(0, pos_d - DAILY_VOL_WINDOW + 1): pos_d + 1].std()
    cost_model = build_cost_model(sides, assets, daily_vol, cfg, nav)
    overrides: dict[str, Any] = {"risk_target_mode": bt.risk_target_mode,
                                 "vol_target": ctx.vol_target}
    if ctx.themes:
        overrides["themes"] = ctx.themes
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=INACCURATE_WARNING, category=UserWarning)
            res = optimize(alpha.alpha, model, cons, cost_model, cfg, nav, current=current,
                           inception=inception, market_w=mkt_w, overrides=overrides,
                           model_base=model_base, kappa_f=kappa)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do otimizador mantém a carteira
        record.update(held_stats(betas))
        relax = getattr(exc, "relaxations", None) or []
        record["relaxations"] = "; ".join(relax)
        return _Decision("manter:falha_otimizador", record=record, model=model,
                         signal_z=alpha.signal_z, alpha=alpha.alpha,
                         fees=cons["borrow_fee"], cost_model=cost_model,
                         notes=[f"{t.date()}: otimização falhou ({type(exc).__name__}: {exc}); "
                                "carteira anterior mantida."])
    w = res.weights[res.weights != 0]
    record.update(_held_stats(model, w, betas, model_base=model_base, kappa=kappa))
    record.update({
        "ex_ante_vol": res.ex_ante_vol,
        "expected_alpha": res.expected_alpha,
        "alpha_scale": res.alpha_scale,
        "relaxations": "; ".join(res.relaxations),
        "beta": float(betas.reindex(w.index).fillna(1.0) @ w) if len(w) else 0.0,
        "solver_status": res.diagnostics.status,
    })
    notes = []
    if res.relaxations:
        notes.append(f"{t.date()}: relaxamentos {res.relaxations}.")
    return _Decision("ok", weights=res.weights, record=record, fees=cons["borrow_fee"],
                     cost_model=cost_model, model=model, signal_z=alpha.signal_z,
                     alpha=alpha.alpha, notes=notes)


# ==========================================================
# Motor
# ==========================================================

def _forward_specific(returns: np.ndarray, fmat: np.ndarray, ok_rows: np.ndarray,
                      B: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """Soma dos retornos específicos ``r − B f`` nas linhas ``rows`` (dias sem regressão fora)."""
    rows = rows[ok_rows[rows]]
    if len(rows) == 0:
        return np.full(B.shape[0], np.nan)
    e = returns[rows] - fmat[rows] @ B.T
    finite = np.isfinite(e)
    total = np.where(finite, e, 0.0).sum(axis=0)
    return np.where(finite.any(axis=0), total, np.nan)


def _drop_provisional(md: MarketData) -> tuple[MarketData, str | None]:
    """Remove barras provisórias (intradiárias) do fim dos dados: o backtest só usa fechamentos."""
    prov = sorted(getattr(md.manifest, "provisional_dates", None) or [])
    if not prov:
        return md, None
    first = pd.Timestamp(prov[0])
    keep = md.close.index[md.close.index < first]
    if keep.empty:
        raise ValueError("Só há barras provisórias nos dados: sem fechamentos para o backtest.")
    cut = keep[-1].date()
    note = (f"Barra(s) provisória(s) (intradiária) a partir de {first.date()} excluída(s): o "
            f"backtest usa apenas fechamentos (dados até {cut}).")
    return md.truncate(cut), note


def results_hash(daily: pd.DataFrame, weekly: pd.DataFrame, weights: pd.DataFrame,
                 ic: pd.DataFrame) -> str:
    """SHA-256 canônico dos resultados (floats com 10 casas; ``NaN`` explícito, nunca zero)."""
    return sha256_obj({name: df.to_dict("split") for name, df in
                       (("daily", daily), ("weekly", weekly), ("weights", weights), ("ic", ic))})


def _config_record(bt: BacktestConfig) -> dict[str, Any]:
    return json.loads(canonical_json(dataclasses.asdict(bt)))


def summary_metrics(daily: pd.DataFrame, weekly: pd.DataFrame, ic: pd.DataFrame,
                    rf_daily: pd.Series | None, cfg: FundConfig, bt: BacktestConfig,
                    vol_target: float) -> dict[str, float]:
    """Métricas agregadas do backtest (planas, em decimal; anualização com 252 pregões).

    - Desempenho: :func:`performance_metrics` do retorno líquido (Sharpe sobre ``rf_daily``,
      a mesma taxa dos juros do caixa; dia sem taxa conhecida = 0, como na contabilidade).
    - Arrasto de custos/aluguel/juros: soma × 252 / dias do backtest.
    - Atribuição: média dos dias COM atribuição × 252 (dias sem regressão fatorial ficam fora;
      contagem em ``n_days_without_attribution``).
    - ``avg_turnover_weekly``: média dos rebalanceamentos posteriores à montagem da carteira
      (primeira semana com gross > 0); semanas em caixa antes dela também ficam fora.
    """
    rf_m = None if rf_daily is None else rf_daily.reindex(daily.index).fillna(0.0)
    m = performance_metrics(daily["ret_net"], rf_m, TRADING_DAYS, cfg.risk.vol_band_min,
                            cfg.risk.vol_band_max)
    gross_m = performance_metrics(daily["ret_gross"])
    nan = float("nan")
    n_days = max(len(daily), 1)
    factor = pd.to_numeric(daily["factor_pnl"], errors="coerce")
    specific = pd.to_numeric(daily["specific_pnl"], errors="coerce")
    n_attr = int(factor.notna().sum())
    status = weekly["status"].astype(str)
    ok = (status == "ok").to_numpy()
    gross_w = pd.to_numeric(weekly["gross"], errors="coerce").to_numpy()
    invested = np.flatnonzero(gross_w > 0)
    after_inception = (np.arange(len(weekly)) > invested[0]) if len(invested) \
        else np.zeros(len(weekly), dtype=bool)
    turnover = pd.to_numeric(weekly["turnover"], errors="coerce").to_numpy()
    vol = pd.to_numeric(weekly["ex_ante_vol"], errors="coerce").to_numpy()
    relax = weekly["relaxations"].fillna("").astype(str) if "relaxations" in weekly.columns \
        else pd.Series("", index=weekly.index)
    m.update({
        "ann_return_gross": gross_m["ann_return"],
        "sharpe_gross": gross_m["sharpe"],
        "cost_drag_annual": float(daily["cost"].sum() * TRADING_DAYS / n_days),
        "borrow_drag_annual": float(daily["borrow"].sum() * TRADING_DAYS / n_days),
        "financing_annual": float(daily["financing"].sum() * TRADING_DAYS / n_days),
        "factor_pnl_annual": float(factor.mean() * TRADING_DAYS) if n_attr else nan,
        "specific_pnl_annual": float(specific.mean() * TRADING_DAYS) if n_attr else nan,
        "n_days_without_attribution": float(len(daily) - n_attr),
        "avg_turnover_weekly": float(np.mean(turnover[after_inception]))
        if after_inception.any() else nan,
        "avg_gross": float(daily["gross"].mean()),
        "avg_abs_net": float(daily["net"].abs().mean()),
        "avg_ex_ante_vol": float(np.nanmean(vol[ok])) if np.isfinite(vol[ok]).any() else nan,
        "max_ex_ante_vol": float(np.nanmax(vol[ok])) if np.isfinite(vol[ok]).any() else nan,
        "vol_target": float(vol_target),
        "n_rebalances": float(len(weekly)),
        "n_rebalance_failures": float((~ok).sum()),
        "n_relaxed": float((relax != "").sum()),
        "final_nav": float(daily["nav"].iloc[-1]) if len(daily) else nan,
        "n_trials": float(bt.n_trials),
    })
    m["psr"] = deflated_sharpe_ratio(m["sharpe"], int(m["n_obs"]), 1, m["skew"],
                                     m["excess_kurtosis"], periods_per_year=TRADING_DAYS)
    m["deflated_sharpe"] = deflated_sharpe_ratio(m["sharpe"], int(m["n_obs"]), bt.n_trials,
                                                 m["skew"], m["excess_kurtosis"],
                                                 periods_per_year=TRADING_DAYS)
    stats = ic_summary(ic)
    for s in stats.index:
        m[f"ic_mean:{s}"] = float(stats.loc[s, "mean"])
    return m


def run_backtest(md: MarketData, cfg: FundConfig, bt: BacktestConfig,
                 progress: ProgressFn | None = None) -> BacktestResult:
    """Backtest walk-forward semanal do núcleo quantitativo (ver docstring do módulo).

    ``progress(feitos, total, mensagem)`` é chamado após cada rebalanceamento.
    """
    notes: list[str] = []
    if md.is_synthetic:
        notes.append(f"{SIMULATED_DATA_NOTICE}: backtest sobre mercado sintético; os números não "
                     "representam desempenho real.")
    md, prov_note = _drop_provisional(md)
    if prov_note:
        notes.append(prov_note)
    panel = build_asset_panel(md, cfg)
    cal = pd.DatetimeIndex(panel.returns.index)
    if len(cal) < 3:
        raise ValueError("Calendário de preços curto demais para o backtest.")
    last = cal[-1]
    if bt.end is not None and pd.Timestamp(bt.end) > last:
        notes.append(f"Fim pedido {bt.end} posterior aos dados; backtest até {last.date()}.")
    upto = cal[cal <= (last if bt.end is None else min(pd.Timestamp(bt.end), last))]
    if upto.empty:
        raise ValueError(f"Fim do backtest {bt.end} anterior ao início dos dados.")
    end_ts = upto[-1]  # último pregão <= fim pedido
    # Regra legada: 1º pregão da semana da B3, informação até o pregão anterior da B3.
    # LAST_US_SESSION: último pregão da semana na NYSE, informação até o pregão de dados anterior.
    rule, code = rebalance_rule(cfg)
    sessions = primary_sessions(md, cfg, code)
    info_cal = cal if rule == "last" else sessions
    info_pos: dict[pd.Timestamp, int] = {}
    for t in rebalance_dates(sessions, bt.start, end_ts, rule=rule):
        prev = info_cal[info_cal < t]
        if len(prev):
            info_pos[t] = int(cal.get_loc(prev[-1]))
    reb = pd.DatetimeIndex(sorted(info_pos), name="date")
    if reb.empty:
        raise ValueError(f"Nenhuma data de rebalanceamento entre {bt.start} e {end_ts.date()}.")
    rm = cfg.risk_model
    fit_start = cal[max(1, info_pos[reb[0]] - rm.history_days + 1)]
    # Universo de estimação: emissores com algum retorno até o fim do backtest (nada posterior).
    has_ret = panel.returns.loc[:end_ts].notna().any()
    est_issuers = [i for i in panel.assets.index if bool(has_ret.get(i, False))]
    if not est_issuers:
        raise ValueError("Nenhum emissor com retornos no painel.")
    est = RiskModelEstimator(panel, cfg, md=md, issuers=est_issuers,
                             exposure_refresh_days=bt.exposure_refresh_days,
                             start=fit_start, end=end_ts)
    vol_target = bt.effective_vol_target(cfg)
    themes, theme_note = _resolve_themes(bt, cfg, list(panel.assets.index))
    ctx = _Context(
        md=md,
        md_no_borrow=dataclasses.replace(md, short_interest=pd.DataFrame(),
                                         lending=pd.DataFrame()),
        cfg=cfg, bt=bt, panel=panel, pit=PointInTimeInputs(panel, md, cfg), est=est,
        vol_target=vol_target, signal_weights=bt.effective_signal_weights(cfg),
        squeeze=pd.DataFrame({"bucket": ASSUMED_SQUEEZE_BUCKET}, index=panel.assets.index),
        limit_fns=_live_limit_functions(), themes=themes,
    )

    ids = list(panel.assets.index)
    id_pos = {i: k for k, i in enumerate(ids)}
    R = panel.returns.reindex(index=cal, columns=ids).to_numpy(dtype=float)
    f_ok = est.factor_returns_all
    est_factors = list(f_ok.columns)
    ok_rows = np.asarray(cal.isin(f_ok.index))
    fmat_all = f_ok.reindex(cal).to_numpy(dtype=float)
    fmat_all = np.where(ok_rows[:, None], np.nan_to_num(fmat_all, nan=0.0), np.nan)
    # Fatores transversais inativos em uma regressão válida contam zero (convenção do
    # estimator). Macro usa retornos exógenos do próprio dia; ausência continua NaN.
    # A lista global só indexa atribuição/IC ex-post: inclusão e betas do modelo de decisão
    # são ajustados por augment_with_macro até a data de informação de cada semana.
    mret = macro_returns(md, list(cfg.risk_model.macro_factors), cal)
    if len(mret.columns):
        est_factors.extend(macro_factor(s) for s in mret.columns)
        fmat_all = np.column_stack([fmat_all, mret.to_numpy(dtype=float)])

    rf = rf_daily_series(md, cal) if bt.include_financing else None
    if bt.include_financing and rf is None:
        notes.append(f"Sem série {RATE_SERIES} em md.rates: juros do caixa = 0 (financiamento "
                     "não contabilizado).")
    rf_vals = rf.to_numpy(dtype=float) if rf is not None else np.zeros(len(cal))
    fallback_fee = cfg.shorting.max_borrow_fee

    days = cal[(cal >= reb[0]) & (cal <= end_ts)]
    reb_set = set(reb)
    book = _Book(len(ids), bt.nav)
    fee_vec = np.zeros(len(ids))
    B_cur: np.ndarray | None = None
    k_cur: np.ndarray | None = None
    invested = False
    n_missing_returns = 0
    n_rf_missing = 0
    n_fee_imputed = 0
    n_events = 0
    n_frozen_total = 0
    daily_rows: list[dict] = []
    weekly_rows: dict[pd.Timestamp, dict] = {}
    weight_rows: dict[pd.Timestamp, np.ndarray] = {}
    ic_inputs: list[tuple[pd.Timestamp, pd.DataFrame, pd.Series, np.ndarray, list[str],
                          np.ndarray]] = []
    n_reb = len(reb)
    done = 0

    for t in days:
        p = int(cal.get_loc(t))
        w_prev = book.w.copy()
        rf_t = rf_vals[p]
        if not math.isfinite(rf_t):
            n_rf_missing += 1
            rf_t = 0.0
        mark = book.mark(R[p], rf_t, fee_vec if bt.include_borrow else np.zeros(len(ids)))
        n_missing_returns += mark.n_missing

        # Atribuição com as exposições do último rebalanceamento.
        if not np.any(w_prev):
            factor_pnl = 0.0
        elif B_cur is None or not ok_rows[p]:
            factor_pnl = float("nan")
        else:
            held = w_prev != 0
            Bh = B_cur[held]
            if not np.isfinite(Bh).all():
                factor_pnl = float("nan")
            else:
                factor_pnl = float((Bh.T @ w_prev[held]) @ fmat_all[p, k_cur])

        w_new: np.ndarray | None = None
        trade_cost = 0.0
        if t in reb_set:
            # Linha primária sem preço em t (mercado fechado): o emissor não negocia hoje.
            closed = ~np.isfinite(R[p])
            frozen = frozenset(ids[k] for k in np.flatnonzero(closed))
            w_cur = pd.Series(w_prev, index=ids)
            dec = _decide(ctx, t, info_pos[t], w_cur[w_cur != 0], book.nav, not invested,
                          frozen)
            rec: dict = dict.fromkeys(WEEKLY_COLUMNS, np.nan)
            rec.update({"status": dec.status, "relaxations": "", "event_window": ""})
            rec.update(dec.record)
            notes.extend(dec.notes)
            if rec.get("event_window"):
                n_events += 1
            if dec.model is not None:
                factors = dec.model.factor_names
                B_df = dec.model.exposures.reindex(ids)[factors]
                B_cur = B_df.to_numpy(dtype=float)
                k_cur = np.array([est_factors.index(f) for f in factors], dtype=int)
            if dec.fees is not None:
                fees = pd.to_numeric(dec.fees, errors="coerce").reindex(ids)
                fee_vec = fees.to_numpy(dtype=float)
            rec["n_frozen"] = int(np.sum(closed & (mark.w_pre != 0)))
            if dec.status == "ok" and dec.weights is not None:
                w_new = dec.weights.reindex(ids).fillna(0.0).to_numpy(dtype=float)
                # Emissor fora da tabela de restrições não tem posição-alvo (peso zero).
                # Mercado fechado: mantém exatamente o peso derivado (nenhuma negociação).
                w_new = np.where(closed, mark.w_pre, w_new)
                n_frozen_total += rec["n_frozen"]
                if not np.any(w_new):
                    notes.append(f"{t.date()}: otimizador devolveu carteira vazia (caixa); "
                                 f"status do solver {rec.get('solver_status')}.")
                invested = invested or bool(np.any(w_new))
                if bt.include_costs and dec.cost_model is not None:
                    target = pd.Series(w_new, index=ids)
                    pre = pd.Series(mark.w_pre, index=ids)
                    trade_cost = float(estimate_rebalance_costs(target, pre,
                                                                dec.cost_model).sum())
            if dec.signal_z is not None and dec.model is not None and dec.alpha is not None:
                factors = dec.model.factor_names
                ic_inputs.append((t, dec.signal_z, dec.alpha,
                                  dec.model.exposures[factors].to_numpy(dtype=float),
                                  list(dec.model.exposures.index),
                                  np.array([est_factors.index(f) for f in factors], dtype=int)))
            final_w = w_new if w_new is not None else mark.w_pre
            rec["turnover"] = float(np.abs(final_w - mark.w_pre).sum())
            rec["gross"] = float(np.abs(final_w).sum())
            rec["net"] = float(final_w.sum())
            rec["n_long"] = int((final_w > 0).sum())
            rec["n_short"] = int((final_w < 0).sum())
            weekly_rows[t] = rec
            weight_rows[t] = final_w.copy()
            nan_fee_shorts = (final_w < 0) & ~np.isfinite(fee_vec)
            n_fee_imputed += int(nan_fee_shorts.sum())
            fee_vec = np.where(np.isfinite(fee_vec), fee_vec, fallback_fee)
        ret, cost = book.close(mark, w_new, trade_cost)
        if t in reb_set:
            weekly_rows[t]["cost"] = cost
            done += 1
            if progress is not None:
                progress(done, n_reb, f"Rebalanceamento {t.date()} ({weekly_rows[t]['status']})")
        daily_rows.append({
            "ret_net": ret, "ret_gross": mark.gross, "cost": cost, "borrow": mark.borrow,
            "financing": mark.financing, "factor_pnl": factor_pnl,
            "specific_pnl": mark.gross - factor_pnl if math.isfinite(factor_pnl)
            else float("nan"),
            "nav": book.nav, "gross": float(np.abs(book.w).sum()), "net": float(book.w.sum()),
            "rebalance": t in reb_set,
        })

    daily = pd.DataFrame(daily_rows, index=pd.DatetimeIndex(days, name="date"))[DAILY_COLUMNS]
    weekly = pd.DataFrame.from_dict(weekly_rows, orient="index")
    weekly.index = pd.DatetimeIndex(weekly.index, name="date")
    extra_cols = [c for c in weekly.columns if c not in WEEKLY_COLUMNS]
    weekly = weekly[WEEKLY_COLUMNS + extra_cols]
    wmat = np.vstack([weight_rows[t] for t in weekly.index])
    used = np.any(wmat != 0, axis=0)
    weights = pd.DataFrame(wmat[:, used], index=weekly.index,
                           columns=pd.Index([i for i, u in zip(ids, used, strict=True) if u],
                                            name="issuer_id"))

    # IC: z do sinal em d contra a soma dos retornos específicos de (t_k, t_{k+1}].
    ic_rows: dict[pd.Timestamp, dict[str, float]] = {}
    reb_list = list(reb)
    for t, zdf, alpha_s, B, b_ids, kidx in ic_inputs:
        k = reb_list.index(t)
        p0 = int(cal.get_loc(t))
        p1 = int(cal.get_loc(reb_list[k + 1])) if k + 1 < len(reb_list) else int(
            cal.get_loc(end_ts))
        rows = np.arange(p0 + 1, p1 + 1)
        cols = [id_pos[i] for i in b_ids]
        fwd = _forward_specific(R[:, cols], fmat_all[:, kidx], ok_rows, B, rows)
        fwd_s = pd.Series(fwd, index=b_ids)
        row = {s: information_coefficient(zdf[s], fwd_s) if s in zdf.columns else float("nan")
               for s in bt.signal_names}
        row[COMPOSITE_IC] = information_coefficient(alpha_s, fwd_s)
        ic_rows[t] = row
    ic = pd.DataFrame.from_dict(ic_rows, orient="index",
                                columns=list(bt.signal_names) + [COMPOSITE_IC])
    ic.index = pd.DatetimeIndex(ic.index, name="date")

    metrics = summary_metrics(daily, weekly, ic, rf, cfg, bt, vol_target)

    # ---------------- notas ----------------
    notes.extend(_standard_notes(cfg, bt, vol_target, est))
    notes.append(theme_note)
    n_attr_missing = int(metrics["n_days_without_attribution"])
    if n_missing_returns:
        notes.append(f"{n_missing_returns} posição-dia(s) sem retorno (feriado/sem negociação): "
                     "contribuição 0 no dia e posição carregada inalterada (nenhum retorno "
                     "inventado; o retorno seguinte cobre o intervalo).")
    if n_frozen_total:
        notes.append(f"{n_frozen_total} posição(ões) não negociada(s) no rebalanceamento por "
                     "mercado da linha primária fechado no dia: peso derivado mantido até a "
                     "semana seguinte (negociar usaria o preço da data de informação).")
    if n_rf_missing and rf is not None:
        notes.append(f"{n_rf_missing} dia(s) sem taxa {RATE_SERIES} conhecida: juros do caixa 0 "
                     "nesses dias.")
    if n_attr_missing:
        notes.append(f"{n_attr_missing} dia(s) sem atribuição fatorial (regressão ou retorno "
                     "macro do dia ausente): "
                     "fator/específico ausentes (NaN) e fora da média anualizada.")
    if n_fee_imputed:
        notes.append(f"{n_fee_imputed} short(s) sem taxa de aluguel: usada a taxa máxima do "
                     f"mandato ({fallback_fee:.1%} a.a., conservador).")
    if n_events:
        notes.append(f"Janela de evento (vol escalada) ativa em {n_events} rebalanceamento(s).")
    n_fail = int(metrics["n_rebalance_failures"])
    if n_fail:
        notes.append(f"{n_fail} rebalanceamento(s) sem nova carteira (carteira anterior mantida).")
    for k_name, v in (("costs", bt.include_costs), ("borrow", bt.include_borrow),
                      ("financing", bt.include_financing)):
        if not v:
            notes.append(f"Contabilidade sem '{k_name}' (include_{k_name}=False).")

    data_notice = SIMULATED_DATA_NOTICE if md.is_synthetic else "Dados reais (snapshot)."
    provenance = {
        "snapshot_id": md.manifest.snapshot_id,
        "data_hash": md.manifest.content_hash(),
        "config_hash": cfg.config_hash(),
        "backtest_config": _config_record(bt),
        "data_notice": data_notice,
        "first_date": str(daily.index[0].date()),
        "last_date": str(daily.index[-1].date()),
        "n_estimation_issuers": len(est_issuers),
        "results_hash": results_hash(daily, weekly, weights, ic),
    }
    return BacktestResult(
        daily=daily, weekly=weekly, weights=weights, ic=ic, metrics=metrics, notes=notes,
        config=bt, is_synthetic=md.is_synthetic, data_notice=data_notice, provenance=provenance,
    )


def _standard_notes(cfg: FundConfig, bt: BacktestConfig, vol_target: float,
                    est: RiskModelEstimator) -> list[str]:
    weights = bt.effective_signal_weights(cfg)
    return [
        "Viés de sobrevivência: o universo é a lista de emissores listados hoje; empresas "
        "deslistadas, incorporadas ou falidas no período não entram, o que tende a inflar o "
        "resultado.",
        "Sem camada de IA: visões de LLM não são testáveis honestamente dentro da janela de "
        "treino dos modelos (docs/research/02); o backtest mede apenas o núcleo quantitativo.",
        "Short interest, aluguel B3 e escore de squeeze não são point-in-time: valem só as "
        "regras de alugabilidade (ADR/US e locais BR; demais mercados não alugáveis) com taxas "
        f"GC estimadas e sem exclusão por squeeze (bucket {ASSUMED_SQUEEZE_BUCKET}) — viés "
        "otimista (aluguel subestimado; shorts que seriam vetados ficam permitidos).",
        "Capitalização histórica = ações atuais × preço histórico (não point-in-time): afeta "
        "pesos WLS do modelo, estilo size, beta de mercado e mínimo de market cap para short. "
        "O estilo value (B/P) também usa o patrimônio do retrato atual.",
        ("Calendário: rebalanceamento no último pregão da semana na NYSE (sexta; feriado nos "
         "EUA ⇒ pregão anterior), com dados até o pregão de dados anterior — mesma regra do "
         "pipeline ao vivo; o P&L diário segue o calendário completo (ADRs negociam em feriados "
         "locais)." if rebalance_rule(cfg)[0] == "last" else
         "Calendário: rebalanceamento no 1º pregão da semana da B3 (segunda; feriado na B3 ⇒ "
         "pregão seguinte), com dados até o pregão anterior da B3 — mesma regra do pipeline ao "
         "vivo; o P&L diário segue o calendário completo (ADRs negociam em feriados locais)."),
        "Execução: decisão com dados até o pregão anterior; pesos novos valem do fechamento do "
        "dia de rebalanceamento (MOC); o retorno do dia acumula nos pesos anteriores. Nome com a "
        "linha primária sem preço no dia não é negociado (mercado fechado).",
        "Elegibilidade, ADTV e linhas de execução recalculados em cada data com dados até a "
        "data de informação (sem usar a elegibilidade do fim da amostra).",
        f"Otimizador em modo '{bt.risk_target_mode}' com meta de vol ex-ante {vol_target:.2%} "
        f"(config {cfg.risk.vol_target_annual:.2%} / viés a priori {cfg.risk.bias_prior:.2f} "
        "durante todo o período)"
        if bt.vol_target is None else
        f"Otimizador em modo '{bt.risk_target_mode}' com meta de vol ex-ante {vol_target:.2%} "
        "(informada no backtest).",
        "Sinais (PIT): " + ", ".join(f"{k} {v:.0%}" for k, v in weights.items()) + ".",
        f"Juros do caixa: {RATE_SERIES} do pregão anterior /252 sobre (1 − exposição líquida); "
        "aluguel: taxa anual /252 sobre os shorts; custos do modelo no fechamento do "
        "rebalanceamento.",
        "Escada de drawdown do mandato não é aplicada no backtest (gross não é reduzido após "
        "perdas).",
        "Atribuição: fator = Σ x_k f_k com exposições do rebalanceamento e retornos fatoriais "
        "estimados no próprio dia (ex-post); retornos de fatores transversais inativos no dia "
        "contam 0. Fatores macro usam o retorno do ativo no dia; ausência conserva NaN.",
        "Risco: bloco macro e modelo base estimados até a data de informação; janelas de evento "
        "aplicadas somente ao modelo de decisão. Gates específicos seguem os modelos "
        "configurados e "
        "κ_F calculado na base, como no pipeline vivo.",
        f"Modelo de risco: {len(est.issuers)} emissores no universo de estimação, exposições "
        f"recalculadas a cada {est.refresh_days} pregões.",
    ]


# ==========================================================
# Atalhos para o backtest completo
# ==========================================================

def run_full_backtest(md: MarketData, cfg: FundConfig | None = None,
                      progress: ProgressFn | None = None, **kwargs: Any) -> BacktestResult:
    """Backtest do primeiro rebalanceamento viável (:func:`earliest_start`) até o fim dos dados.

    ``kwargs`` são campos de :class:`BacktestConfig` (``start`` opcional).
    """
    cfg = cfg or load_config()
    start = kwargs.pop("start", None) or earliest_start(md, cfg)
    return run_backtest(md, cfg, BacktestConfig(start=start, **kwargs), progress)


def run_snapshot_backtest(snapshot_dir: str | None = None, config_path: str | None = None,
                          progress: ProgressFn | None = None,
                          **kwargs: Any) -> BacktestResult:
    """Backtest completo sobre um snapshot real (padrão: o mais recente em ``data/snapshots``).

    O snapshot é carregado com verificação de todos os SHA-256.
    """
    from ..data.snapshot import latest_snapshot, load_snapshot

    path = Path(snapshot_dir) if snapshot_dir else latest_snapshot()
    if path is None:
        raise FileNotFoundError("Nenhum snapshot encontrado para o backtest.")
    md = load_snapshot(path)
    return run_full_backtest(md, load_config(config_path), progress, **kwargs)
