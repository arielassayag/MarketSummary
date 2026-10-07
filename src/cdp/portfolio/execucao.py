"""Execução no fechamento (MOC) com capacidade de liquidez (dono: workstream D; consumidores: o
otimizador e a compliance, a rotina diária e o relatório semanal).

Janela do pregão (:func:`janela_execucao`)
------------------------------------------
Horários oficiais de ``execution.close_times`` (fuso de cada mercado; a biblioteca de
calendários só define os dias de pregão e os fechamentos antecipados dos EUA). Prazo efetivo da
decisão::

    prazo = min(teto local, prazo do mandato, fechamento mais cedo entre NYSE/B3/BMV − buffer)

Um mercado é elegível no pregão se está aberto, tem horário verificado e fecha em
``prazo + buffer`` ou depois (corte MOC posterior ao prazo).

Capacidade por linha (:func:`capacidade_fechamento_usd`)
-------------------------------------------------------
``cap_ℓ(s) = mult(s) · [p_leilão · fatia_leilão(categoria) + p_pré · fatia_pré] · ADV_ℓ``

``ADV_ℓ`` é a estatística ``capacity.adv_statistic`` (P25) do valor negociado diário em USD da
linha nos ``capacity.adv_window_days`` pregões ANTERIORES a ``s`` (volume zero com preço válido é
dado ausente; menos da metade da janela observada ⇒ volume desconhecido). Shorts ×
``short_multiplier``; fechamento antecipado × ``early_close_multiplier`` (só nos mercados que
fecham mais cedo). Capacidade 0 — como RESTRIÇÃO, nunca como dado — se o mercado está fechado ou
inelegível, ou se o volume é desconhecido. Na execução (rotina diária) a mesma fórmula usa o
volume REALIZADO no pregão (``fill_volume_source: realized_daily``).

Congelamento (:func:`emissores_congelados`)
-------------------------------------------
Emissor com linha detida num mercado fechado/inelegível fica congelado (``w = w⁰``). Sem posição,
com o mercado local fechado: ``adr_if_eligible_else_freeze`` congela só quem não tem linha
negociável no pregão; ``freeze`` congela sempre.

Também aqui: preenchimento esperado das ordens no fechamento (:func:`preenchimentos_esperados`,
a regra única da rotina diária e da conferência do livro), custo de oportunidade e
*implementation shortfall* (deriva decisão→fechamento e custo modelado), trajetória condicional
do período de montagem (risco efetivo × meta pela capacidade de fechamento) e o teste de
estresse de liquidez calibrado na América Latina (volume P10 por nome ≈ 0,7 × ADV; cenário
reverso 0,5 × ADV; custo com spreads e σ × 2).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..calendar import MARKET_EXCHANGES, is_early_close, is_session, session_close_utc
from ..universe import listing_market

if TYPE_CHECKING:  # pragma: no cover
    from ..config import ExecutionSection, FundConfig
    from ..contracts import BookEntry, Proposal
    from ..market import MarketData

#: Bolsa (coluna ``exchange`` do universo) → código MIC do calendário.
EXCHANGE_MIC = {
    "B3": "BVMF", "BVMF": "BVMF", "NYSE": "XNYS", "XNYS": "XNYS", "NASDAQ": "XNAS",
    "XNAS": "XNAS", "NYSE AMERICAN": "XASE", "XASE": "XASE", "NYSE ARCA": "ARCX", "ARCA": "ARCX",
    "ARCX": "ARCX", "BMV": "XMEX", "XMEX": "XMEX", "BCS": "XSGO", "XSGO": "XSGO", "BVC": "XBOG",
    "XBOG": "XBOG", "BVL": "XLIM", "XLIM": "XLIM", "BYMA": "XBUE", "XBUE": "XBUE",
}
#: Mercado sem horário próprio na configuração → mercado cujos horários de leilão valem para ele
#: (a NYSE American segue o leilão de fechamento da NYSE; usar o corte da NYSE é conservador).
MIC_PAI = {"XASE": "XNYS"}
MIC_NOME = {"BVMF": "B3", "XNYS": "NYSE", "XNAS": "Nasdaq", "ARCX": "NYSE Arca",
            "XASE": "NYSE American", "XMEX": "BMV", "XSGO": "Bolsa de Santiago", "XBOG": "BVC",
            "XLIM": "BVL", "XBUE": "BYMA"}
MERCADOS_PRAZO = ("XNYS", "BVMF", "XMEX")
"""Mercados cujo fechamento mais cedo define o prazo efetivo da decisão."""
MIN_OBS_FRACAO = 0.5
"""Fração mínima da janela de ADV com volume observado; abaixo disso o volume é desconhecido."""
ESTRESSE_VOLUME = 0.7
"""Volume em estresse = P10 por nome do volume relativo ao ADV de 63 pregões em episódios de
estresse na América Latina (COVID-2020, segundo turno BR-2022, PASO AR-2019, estallido CL-2019,
carry ago/2024, Americanas-2023): ≈ 0,7. A crise de liquidez vem de spreads, σ e suspensões."""
ESTRESSE_REVERSO_VOLUME = 0.5
"""Cenário reverso (mais severo que o observado): volume de 0,5 × ADV."""
ESTRESSE_SPREAD_MULT = 2.0
ESTRESSE_VOL_MULT = 2.0
TRAJETORIA_FECHAMENTOS = 8
"""Horizonte (fechamentos semanais) da trajetória esperada do período de montagem."""
SHORTFALL_SEMANAS = 13
"""Janela móvel (até 13 semanas) da estatística t da deriva decisão→fechamento — a parcela
mensurável do *implementation shortfall* em paper trading (o custo debitado é o modelado)."""
SHORTFALL_MIN_SEMANAS = 3
LADO = Literal["long", "short"]


# ============================================================ janela


@dataclass(frozen=True)
class JanelaExecucao:
    """Janela de execução de um pregão de rebalanceamento (horários tz-aware).

    ``abertos``: MIC -> mercado aberto no pregão; ``fechamentos``: MIC -> fechamento oficial;
    ``corte_moc``: MIC -> corte de ordens MOC; ``prazo_decisao``: prazo efetivo
    ``min(teto local, fechamento mais cedo entre XNYS/BVMF/XMEX − buffer)``;
    ``fechamento_antecipado``: algum dos mercados que definem o prazo (NYSE, B3, BMV) fecha
    mais cedo (os demais fechamentos antecipados estão em :func:`mics_antecipados`);
    ``multiplicador_capacidade``: 1,0 ou ``early_close_multiplier`` (aplicado só aos mercados
    que fecham mais cedo)."""

    sessao: date
    abertos: dict[str, bool]
    fechamentos: dict[str, datetime]
    corte_moc: dict[str, datetime]
    prazo_decisao: datetime
    fechamento_antecipado: bool
    multiplicador_capacidade: float


def _execution(cfg: FundConfig) -> ExecutionSection:
    from ..config import ExecutionSection

    return cfg.execution if cfg.execution is not None else ExecutionSection()


def _hhmm(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=tz)


def resolver_mic(mic: str, cfg: FundConfig) -> str | None:
    """MIC com horário configurado (o próprio ou o mercado-pai); ``None`` se não houver."""
    times = _execution(cfg).close_times
    if mic in times:
        return mic
    pai = MIC_PAI.get(mic)
    return pai if pai in times else None


def mic_da_linha(ticker: str, exchange: object = None) -> str:
    """MIC da linha: pela bolsa do universo; sem ela, pelo sufixo do ticker (EUA ⇒ NYSE)."""
    if isinstance(exchange, str) and exchange.strip():
        mic = EXCHANGE_MIC.get(exchange.strip().upper())
        if mic is not None:
            return mic
    return MARKET_EXCHANGES.get(listing_market(str(ticker)), "XNYS")


def categoria_da_linha(ticker: str, line_type: object, etf: bool = False) -> str:
    """Categoria de leilão: ``ADR``, ``US_STOCK``, ``ETF_US`` ou o país da linha local."""
    lt = str(line_type or "").upper()
    if etf:
        return "ETF_US"
    if lt == "ADR":
        return "ADR"
    mkt = listing_market(str(ticker))
    if lt == "US_LISTED" or mkt == "US":
        return "US_STOCK"
    return mkt


def janela_execucao(sessao: date, cfg: FundConfig) -> JanelaExecucao:
    """Janela do pregão ``sessao`` com os horários de ``cfg.execution.close_times`` (horário não
    verificado ⇒ mercado sem fechamento elegível). Sem a seção ``execution`` usa os padrões da
    metodologia (:class:`cdp.config.ExecutionSection`)."""
    ex = _execution(cfg)
    abertos: dict[str, bool] = {}
    fech: dict[str, datetime] = {}
    corte: dict[str, datetime] = {}
    antecipados: set[str] = set()
    for mic, ct in ex.close_times.items():
        aberto = is_session(sessao, mic)
        abertos[mic] = aberto
        if not aberto or ct.close is None or ct.moc_cutoff is None:
            continue
        tz = ZoneInfo(ct.tz)
        close = _hhmm(sessao, ct.close, tz)
        cutoff = _hhmm(sessao, ct.moc_cutoff, tz)
        if is_early_close(sessao, mic):
            early = session_close_utc(sessao, mic)
            if early is not None and early < close:
                gap = close - cutoff
                close = early.astimezone(tz)
                cutoff = close - gap
                antecipados.add(mic)
        fech[mic] = close
        corte[mic] = cutoff
    prazo = _prazo(sessao, fech, cfg)
    # O sinal do dia é o fechamento antecipado dos mercados que definem o prazo (NYSE, B3, BMV);
    # o fechamento antecipado de outro mercado (ex.: BYMA em 31/12) só reduz a capacidade
    # DESSE mercado (``mics_antecipados``) e não muda o prazo nem o rótulo do dia.
    antecipado = bool(antecipados & set(MERCADOS_PRAZO))
    if not antecipados:
        mult = 1.0
    elif ex.early_close_mode == "capacity_half":
        mult = float(ex.capacity.early_close_multiplier)
    else:  # risk_reducing_only / previous_full_session: nada no leilão antecipado (fase 1)
        mult = 0.0
    return JanelaExecucao(sessao=sessao, abertos=abertos, fechamentos=fech, corte_moc=corte,
                          prazo_decisao=prazo, fechamento_antecipado=antecipado,
                          multiplicador_capacidade=mult)


def _prazo(sessao: date, fech: Mapping[str, datetime], cfg: FundConfig) -> datetime:
    """``min(teto local, prazo do mandato, fechamento mais cedo entre NYSE/B3/BMV − buffer)``."""
    ex = _execution(cfg)
    tz_fund = ZoneInfo(cfg.fund.timezone)
    cands = [_hhmm(sessao, ex.decision_deadline_cap_local, tz_fund),
             _hhmm(sessao, cfg.fund.decision_deadline_local, tz_fund)]
    buffer = timedelta(minutes=ex.decision_buffer_minutes)
    cands += [fech[m] - buffer for m in MERCADOS_PRAZO if m in fech]
    return min(cands).astimezone(tz_fund)


def janela_regular(referencia: date, cfg: FundConfig) -> JanelaExecucao:
    """Janela de um pregão REGULAR: todos os mercados configurados abertos, sem fechamento
    antecipado, com os horários (e o horário de verão) da data ``referencia``.

    Mede a liquidez ESTRUTURAL da carteira — estresse de liquidez e trajetória do período de
    montagem — sem confundi-la com o feriado de um dia específico: um mercado fechado no próximo
    dia de montagem não torna os nomes dele ilíquidos (o calendário entra à parte, janela a
    janela, em :func:`capacidade_por_janela`)."""
    ex = _execution(cfg)
    abertos: dict[str, bool] = {}
    fech: dict[str, datetime] = {}
    corte: dict[str, datetime] = {}
    for mic, ct in ex.close_times.items():
        abertos[mic] = True
        if ct.close is None or ct.moc_cutoff is None:
            continue
        tz = ZoneInfo(ct.tz)
        fech[mic] = _hhmm(referencia, ct.close, tz)
        corte[mic] = _hhmm(referencia, ct.moc_cutoff, tz)
    return JanelaExecucao(sessao=referencia, abertos=abertos, fechamentos=fech, corte_moc=corte,
                          prazo_decisao=_prazo(referencia, fech, cfg),
                          fechamento_antecipado=False, multiplicador_capacidade=1.0)


def mics_antecipados(janela: JanelaExecucao, cfg: FundConfig) -> set[str]:
    """Mercados que fecham mais cedo no pregão da janela (numa janela regular o multiplicador é
    1,0 e o fechamento antecipado do calendário não tem efeito)."""
    return {m for m in janela.fechamentos if is_early_close(janela.sessao, m)}


def prazo_efetivo(sessao: date, cfg: FundConfig) -> datetime:
    """Prazo efetivo da decisão no dia de montagem ``sessao`` (Brasília). Sem a seção
    ``execution`` (legado): ``fund.decision_deadline_local``."""
    tz = ZoneInfo(cfg.fund.timezone)
    if cfg.execution is None:
        return _hhmm(sessao, cfg.fund.decision_deadline_local, tz)
    return janela_execucao(sessao, cfg).prazo_decisao.astimezone(tz)


def motivo_inelegivel(mic: str, janela: JanelaExecucao, cfg: FundConfig) -> str | None:
    """Por que o mercado não executa no fechamento do pregão (``None`` = elegível)."""
    ex = _execution(cfg)
    m = resolver_mic(mic, cfg)
    nome = MIC_NOME.get(mic, mic)
    if m is None:
        return f"{nome}: horário de fechamento não configurado"
    if not janela.abertos.get(m, False):
        return f"{nome}: sem pregão em {janela.sessao:%d/%m/%Y}"
    if m not in janela.fechamentos:
        return f"{nome}: horário de fechamento não verificado"
    limite = janela.prazo_decisao + timedelta(minutes=ex.decision_buffer_minutes)
    if janela.fechamentos[m] < limite or janela.corte_moc[m] < janela.prazo_decisao:
        return f"{nome}: fechamento antes do prazo da decisão mais a margem"
    if m in mics_antecipados(janela, cfg) and janela.multiplicador_capacidade <= 0:
        return f"{nome}: fechamento antecipado sem capacidade de leilão nesta metodologia"
    return None


def mercados_elegiveis(janela: JanelaExecucao, cfg: FundConfig) -> dict[str, bool]:
    """MIC → executa no fechamento do pregão (aberto, horário verificado, fecha depois do prazo
    mais a margem). Inclui os mercados-filhos (ex.: NYSE American pela NYSE)."""
    mics = set(_execution(cfg).close_times) | set(MIC_PAI)
    return {m: motivo_inelegivel(m, janela, cfg) is None for m in sorted(mics)}


def fechamento_execucao(janela: JanelaExecucao, mics: Iterable[str]) -> datetime | None:
    """Fechamento oficial mais tardio entre os mercados informados (``booked_at``)."""
    vals = [janela.fechamentos[m] for m in mics if m in janela.fechamentos]
    return max(vals) if vals else None


def fechamento_mais_tardio(janela: JanelaExecucao) -> datetime | None:
    return max(janela.fechamentos.values()) if janela.fechamentos else None


# ============================================================ volume e capacidade


def valor_negociado_usd(md: MarketData, tickers: Sequence[str] | None = None) -> pd.DataFrame:
    """Valor negociado diário em USD por linha (fechamento × volume × câmbio); volume zero ou
    ausente com preço válido é dado AUSENTE (``NaN``), nunca liquidez zero."""
    from ..analytics.panel import fx_for_lines

    lines = md.universe.lines
    fx = fx_for_lines(md)
    cols = list(tickers) if tickers is not None else list(lines.index)
    out: dict[str, pd.Series] = {}
    for t in cols:
        if t not in md.close.columns or t not in lines.index:
            out[t] = pd.Series(np.nan, index=md.close.index)
            continue
        ccy = str(lines.loc[t, "currency"])
        f = fx[ccy] if ccy in fx.columns else pd.Series(np.nan, index=md.close.index)
        vol = (md.volume[t] if t in md.volume.columns
               else pd.Series(np.nan, index=md.close.index))
        vol = vol.where(vol > 0)
        out[t] = md.close[t] * vol * f
    return pd.DataFrame(out, index=md.close.index)


def adv_fechamento_usd(md: MarketData, tickers: Sequence[str], antes_de: date,
                       cfg: FundConfig) -> pd.DataFrame:
    """ADV de referência da capacidade por linha, só com pregões ANTERIORES a ``antes_de``.

    Colunas ``adv_usd`` (estatística da configuração; ``NaN`` se desconhecido), ``n_obs`` e
    ``ultimo``. Janela = os últimos ``adv_window_days`` pregões COM PREÇO da linha."""
    from ..analytics.panel import STALE_DAYS_MAX

    cap = _execution(cfg).capacity
    win = int(cap.adv_window_days)
    tv = valor_negociado_usd(md, tickers)
    ts = pd.Timestamp(antes_de)
    rows = []
    for t in tickers:
        if t not in md.close.columns:
            # Linha sem série de preços até a data (ainda sem pregão, nova listagem): volume
            # desconhecido ⇒ capacidade zero como restrição, nunca erro nem dado preenchido.
            rows.append({"ticker": t, "adv_usd": float("nan"), "n_obs": 0, "ultimo": None})
            continue
        px = md.close[t]
        idx = px.index[(px.index < ts) & px.notna().to_numpy()]
        idx = idx[-win:]
        vals = tv[t].reindex(idx).dropna() if t in tv.columns else pd.Series(dtype=float)
        n = int(len(vals))
        last = idx[-1] if len(idx) else None
        stale = last is None or (ts - last).days > STALE_DAYS_MAX + 3
        if n < math.ceil(MIN_OBS_FRACAO * win) or stale:
            adv = float("nan")
        elif cap.adv_statistic == "p25":
            adv = float(vals.quantile(0.25))
        elif cap.adv_statistic == "p50":
            adv = float(vals.median())
        else:
            adv = float(vals.mean())
        rows.append({"ticker": t, "adv_usd": adv, "n_obs": n,
                     "ultimo": last.date() if last is not None else None})
    df = pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame(
        columns=["adv_usd", "n_obs", "ultimo"])
    return df


def volume_realizado_usd(md: MarketData, tickers: Sequence[str], sessao: date) -> pd.Series:
    """Valor realizado no pregão; exige preço, volume e FX da própria data, sem carry."""
    ts = pd.Timestamp(sessao)
    out: dict[str, float] = {}
    for t in tickers:
        value = float("nan")
        if (t in md.universe.lines.index and t in md.close.columns and
                ts in md.close.index and t in md.volume.columns and ts in md.volume.index):
            px, vol = md.close.at[ts, t], md.volume.at[ts, t]
            fx = cambio_do_pregao(md, str(md.universe.lines.at[t, "currency"]), sessao)
            if (pd.notna(px) and pd.notna(vol) and math.isfinite(float(px)) and
                    math.isfinite(float(vol)) and float(px) > 0 and float(vol) > 0
                    and fx is not None):
                value = float(px) * float(vol) * fx
        out[t] = value
    return pd.Series(out, dtype=float).reindex(list(tickers))


def cambio_do_pregao(md: MarketData, moeda: str, sessao: date) -> float | None:
    """USD por unidade local observado na data; USD/USD=1 é identidade de unidade.

    O carry limitado usado por painel/ADV/marcação não autoriza uma operação no MOC.
    """
    if moeda == "USD":
        return 1.0
    ts = pd.Timestamp(sessao)
    if moeda not in md.fx.columns or ts not in md.fx.index:
        return None
    try:
        value = float(md.fx.at[ts, moeda])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _motivo_cambio(moeda: str, sessao: date) -> str:
    return f"câmbio {moeda} do pregão {sessao:%d/%m/%Y} ausente ou inválido"


def _col(lines: pd.DataFrame, name: str) -> pd.Series:
    if name in lines.columns:
        return lines[name]
    return pd.Series([None] * len(lines), index=lines.index, dtype=object)


def tabela_capacidade(lines: pd.DataFrame, md: MarketData, janela: JanelaExecucao,
                      cfg: FundConfig, *, lado: LADO,
                      volume: Literal["adv", "realizado"] = "adv") -> pd.DataFrame:
    """Capacidade de fechamento por linha com todos os termos da fórmula (modelo aberto).

    Colunas: ``mic``, ``categoria``, ``elegivel``, ``motivo``, ``volume_ref_usd`` (ADV P25 dos
    pregões anteriores ou o volume realizado no pregão), ``n_obs``, ``fatia_leilao``,
    ``fracao_volume`` (``p_leilão·fatia + p_pré·fatia_pré``), ``multiplicador`` (fechamento
    antecipado × lado) e ``capacidade_usd``."""
    ex = _execution(cfg)
    cap = ex.capacity
    tickers = [str(t) for t in lines.index]
    if volume == "adv":
        ref = adv_fechamento_usd(md, tickers, janela.sessao, cfg)
        vref = ref["adv_usd"].reindex(tickers).astype(float) if len(ref) else pd.Series(
            np.nan, index=tickers)
        nobs = ref["n_obs"].reindex(tickers) if len(ref) else pd.Series(0, index=tickers)
    else:
        vref = volume_realizado_usd(md, tickers, janela.sessao)
        nobs = vref.notna().astype(int)
    exch = _col(lines, "exchange")
    ltype = _col(lines, "line_type")
    etf = _col(lines, "is_etf")
    moedas = _col(lines, "currency")
    antecip = mics_antecipados(janela, cfg)
    rows = []
    for t in tickers:
        mic = mic_da_linha(t, exch.get(t))
        motivo = motivo_inelegivel(mic, janela, cfg)
        if volume == "realizado" and motivo is None:
            moeda = str(moedas.get(t))
            if cambio_do_pregao(md, moeda, janela.sessao) is None:
                motivo = _motivo_cambio(moeda, janela.sessao)
        cat = categoria_da_linha(t, ltype.get(t), etf.get(t) is True)
        share = float(cap.auction_share.get(cat, 0.0))
        frac = cap.auction_participation * share + cap.preclose_participation * \
            cap.preclose_volume_share
        mult = 1.0
        m_res = resolver_mic(mic, cfg)
        if m_res in antecip:
            mult *= janela.multiplicador_capacidade
        if lado == "short":
            mult *= cap.short_multiplier
        v = float(vref.get(t)) if pd.notna(vref.get(t)) else float("nan")
        if motivo is None and not math.isfinite(v):
            motivo = "volume desconhecido" if volume == "adv" else "volume do pregão indisponível"
        val = mult * frac * v if motivo is None else 0.0
        rows.append({"ticker": t, "mic": mic, "categoria": cat, "elegivel": motivo is None,
                     "motivo": motivo or "", "volume_ref_usd": v,
                     "n_obs": int(nobs.get(t, 0) or 0), "fatia_leilao": share,
                     "fracao_volume": frac, "multiplicador": mult,
                     "capacidade_usd": float(max(val, 0.0)) if math.isfinite(val) else 0.0})
    return pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame(
        columns=["mic", "categoria", "elegivel", "motivo", "volume_ref_usd", "n_obs",
                 "fatia_leilao", "fracao_volume", "multiplicador", "capacidade_usd"])


def capacidade_fechamento_usd(lines: pd.DataFrame, md: MarketData, janela: JanelaExecucao,
                              cfg: FundConfig, *, lado: Literal["long", "short"]) -> pd.Series:
    """Capacidade em USD por ticker no fechamento da janela (fórmula do módulo); ``0.0`` para
    linha sem volume conhecido, mercado fechado ou fechamento antes do prazo + buffer."""
    tab = tabela_capacidade(lines, md, janela, cfg, lado=lado, volume="adv")
    return tab["capacidade_usd"].astype(float).rename("capacidade_fechamento_usd")


def capacidade_por_janela(base: pd.DataFrame, janelas: Sequence[JanelaExecucao],
                          cfg: FundConfig) -> list[pd.Series]:
    """Capacidade por linha em cada janela de uma sequência de fechamentos, a partir da tabela
    de um pregão regular (``base`` = :func:`tabela_capacidade` com :func:`janela_regular`; a
    mesma referência de volume): zero onde o mercado da linha não executa na janela (feriado,
    fechamento antes do prazo) e × ``multiplicador_capacidade`` nos mercados que fecham mais
    cedo nela."""
    out: list[pd.Series] = []
    for j in janelas:
        antecip = mics_antecipados(j, cfg)
        vals = {}
        for t, row in base.iterrows():
            cap = float(row["capacidade_usd"])
            mic = str(row["mic"])
            if cap > 0 and motivo_inelegivel(mic, j, cfg) is not None:
                cap = 0.0
            elif cap > 0 and resolver_mic(mic, cfg) in antecip:
                cap *= j.multiplicador_capacidade
            vals[t] = cap
        out.append(pd.Series(vals, dtype=float, name=j.sessao.isoformat()))
    return out


def fechamentos_necessarios(nocional_usd: float, capacidade_usd: float) -> float | None:
    """Fechamentos necessários para executar ``nocional_usd`` com ``capacidade_usd`` por
    fechamento; ``None`` quando a capacidade é zero ou desconhecida."""
    n = abs(float(nocional_usd)) if nocional_usd is not None else float("nan")
    if not math.isfinite(n):
        return None
    if n == 0:
        return 0.0
    try:
        c = float(capacidade_usd)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(c) or c <= 0:
        return None
    return n / c


# ============================================================ congelamento e roteamento


def _mercado_local(iid: str, tickers: Iterable[str]) -> str | None:
    for t in tickers:
        mkt = listing_market(str(t))
        if mkt != "US":
            return MARKET_EXCHANGES.get(mkt)
    pais = str(iid).split("_", 1)[0]
    return MARKET_EXCHANGES.get(pais) if pais != "US" else None


def emissores_congelados(sides: pd.DataFrame, atual: BookEntry | None, janela: JanelaExecucao,
                         cfg: FundConfig) -> dict[str, str]:
    """Emissores sem linha negociável na janela (mercado local fechado sem ADR elegível, conforme
    ``execution.local_closed_policy``): ``issuer_id -> motivo``. O otimizador fixa ``w = w0``.

    Regras: (1) linha DETIDA em mercado fechado ou inelegível ⇒ congelado (a posição não pode
    ser alterada pela linha que a carrega); (2) sem posição e com o mercado local fechado:
    ``freeze`` congela sempre; ``adr_if_eligible_else_freeze`` congela só se nenhuma linha de
    execução do emissor (``long_ticker``/``short_ticker``) negocia no fechamento."""
    ex = _execution(cfg)
    elig = mercados_elegiveis(janela, cfg)

    def ok(t: str) -> bool:
        return bool(elig.get(mic_da_linha(t), False))

    held: dict[str, list[str]] = {}
    for p in (atual.positions if atual is not None else []):
        if p.weight != 0 or (p.shares or 0) != 0:
            held.setdefault(p.issuer_id, []).append(p.ticker)
    ids = list(dict.fromkeys([str(i) for i in sides.index] + sorted(held)))
    out: dict[str, str] = {}
    data = f"{janela.sessao:%d/%m/%Y}"
    for iid in ids:
        bad = [t for t in held.get(iid, []) if not ok(t)]
        if bad:
            nomes = sorted({MIC_NOME.get(mic_da_linha(t), mic_da_linha(t)) for t in bad})
            out[iid] = (f"linha detida sem negociação no fechamento de {data} "
                        f"({', '.join(sorted(bad))}; {', '.join(nomes)})")
            continue
        if iid in held:
            continue
        cands: list[str] = []
        if iid in sides.index:
            row = sides.loc[iid]
            for col in ("long_ticker", "short_ticker"):
                v = row.get(col) if hasattr(row, "get") else None
                if isinstance(v, str) and v:
                    cands.append(v)
        local = _mercado_local(iid, cands)
        local_ok = local is None or bool(elig.get(local, False))
        if local_ok:
            if cands and not any(ok(t) for t in cands):
                out[iid] = f"sem linha negociável no fechamento de {data}"
            continue
        nome = MIC_NOME.get(local or "", local or "")
        if ex.local_closed_policy == "freeze" or not any(ok(t) for t in cands):
            out[iid] = f"mercado local sem negociação no fechamento de {data} ({nome})"
    return out


def rotear_linhas(sides: pd.DataFrame, lines: pd.DataFrame, janela: JanelaExecucao,
                  cfg: FundConfig, atual: BookEntry | None = None) -> pd.DataFrame:
    """Política ``adr_if_eligible_else_freeze`` na escolha da linha COMPRADA de um emissor SEM
    posição: se a linha escolhida não negocia no fechamento do pregão e o emissor tem outra linha
    com dados num mercado elegível (ADR/listagem nos EUA), a linha comprada passa a ser a de
    maior ADTV entre elas. A linha vendida (aluguel) não muda. Emissores detidos em ``atual``
    mantêm a linha (com a linha detida sem negociação o emissor fica congelado — ver
    :func:`emissores_congelados` —, e a posição nunca muda de linha num dia sem pregão local).
    Com ``freeze`` devolve ``sides`` inalterado. Chamada na preparação da semana, antes do custo,
    da capacidade, do congelamento e das posições."""
    ex = _execution(cfg)
    if ex.local_closed_policy != "adr_if_eligible_else_freeze" or sides.empty:
        return sides
    elig = mercados_elegiveis(janela, cfg)
    out = sides.copy()
    exch = _col(lines, "exchange")
    has = lines["has_data"].fillna(False).astype(bool) if "has_data" in lines.columns else \
        pd.Series(True, index=lines.index)
    detidos = {p.issuer_id for p in (atual.positions if atual is not None else [])
               if p.weight != 0 or (p.shares or 0) != 0}
    for iid in out.index:
        if str(iid) in detidos:
            continue
        t = out.at[iid, "long_ticker"] if "long_ticker" in out.columns else None
        if not isinstance(t, str) or elig.get(mic_da_linha(t, exch.get(t)), False):
            continue
        alt = lines[(lines["issuer_id"].astype(str) == str(iid)) & has]
        alt = alt[[elig.get(mic_da_linha(x, exch.get(x)), False) for x in alt.index]]
        if alt.empty:
            continue
        adtv = pd.to_numeric(alt.get("adtv_usd", pd.Series(np.nan, index=alt.index)),
                             errors="coerce")
        best = str(adtv.idxmax()) if adtv.notna().any() else str(alt.index[0])
        out.at[iid, "long_ticker"] = best
        if "long_line_type" in out.columns:
            out.at[iid, "long_line_type"] = str(lines.at[best, "line_type"])
        if "long_currency" in out.columns:
            out.at[iid, "long_currency"] = str(lines.at[best, "currency"])
        if "adtv_long_usd" in out.columns:
            v = adtv.get(best)
            out.at[iid, "adtv_long_usd"] = float(v) if pd.notna(v) else np.nan
    return out


# ============================================================ preenchimento


def preencher(ordem_acoes: int, capacidade_usd: float, preco_usd: float) -> int:
    """Ações executadas no fechamento: ``sinal × min(|ordem|, ⌊capacidade / preço⌋)``."""
    if ordem_acoes == 0:
        return 0
    if not (math.isfinite(capacidade_usd) and capacidade_usd > 0 and math.isfinite(preco_usd)
            and preco_usd > 0):
        return 0
    lim = int(math.floor(capacidade_usd / preco_usd + 1e-9))
    q = min(abs(int(ordem_acoes)), lim)
    return q if ordem_acoes > 0 else -q


def lado_da_ordem(acoes_antes: float, acoes_alvo: float) -> LADO:
    """Capacidade de short quando a ordem abre ou aumenta uma posição vendida."""
    return "short" if acoes_alvo < 0 and acoes_alvo < acoes_antes else "long"


@dataclass(frozen=True)
class OrdemLinha:
    """Uma linha a executar no fechamento: ações detidas antes do fechamento, ações-alvo da
    decisão (``None`` = alvo em peso sem preço/câmbio para converter), fechamento oficial do
    pregão (moeda local) e câmbio (USD por unidade local) do pregão."""

    emissor: str
    ticker: str
    detidas: int
    alvo: int | None
    preco: float | None
    fx: float | None


@dataclass(frozen=True)
class Preenchimento:
    """Execução esperada de uma linha (regra única de :func:`preenchimentos_esperados`).

    ``situacao``: ``executada``, ``parcial``, ``sem_ordem``, ``congelado`` (emissor com linha
    detida sem negociação), ``inelegivel`` (mercado sem fechamento elegível), ``sem_preco``,
    ``apos_corte`` (decisão depois do corte MOC do mercado) ou ``banda`` (abaixo de
    ``min_trade_weight``)."""

    emissor: str
    ticker: str
    mic: str
    detidas: int
    ordem: int
    executadas: int
    situacao: str
    motivo: str = ""
    capacidade_usd: float | None = None


def preenchimentos_esperados(ordens: Sequence[OrdemLinha], md: MarketData,
                             janela: JanelaExecucao, cfg: FundConfig, *, nav_pre: float,
                             decidido_em: datetime | None) -> list[Preenchimento]:
    """Execução determinística de cada linha no fechamento da janela — a regra da rotina diária
    (``DailyRunner``) e da conferência do livro e do ``cdp verify``.

    Ordem = alvo − detidas. Não negociam: emissor com linha DETIDA num mercado sem fechamento
    elegível ou sem preço/câmbio próprios válidos (congelado inteiro, nenhuma linha dele),
    linha em mercado inelegível, sem fechamento
    oficial ou câmbio no pregão, decisão depois do corte MOC do mercado, ordem abaixo da banda
    (``min_trade_weight`` e, com ``max_fixed_cost_bps``, o custo fixo mínimo por ordem do
    mercado; salvo o encerramento da posição). As demais executam
    ``sinal × min(|ordem|, ⌊capacidade / preço USD⌋)`` com a capacidade da linha pelo volume
    ``fill_volume_source`` (realizado no pregão)."""
    ex = _execution(cfg)
    uni = md.universe.lines
    exch = uni["exchange"] if "exchange" in uni.columns else pd.Series(dtype=object)
    moedas = _col(uni, "currency")
    tickers = list(dict.fromkeys(o.ticker for o in ordens))
    lines_df = uni.reindex(tickers)
    source: Literal["adv", "realizado"] = (
        "realizado" if ex.fill_volume_source == "realized_daily" else "adv")
    caps = ({lado: tabela_capacidade(lines_df, md, janela, cfg, lado=lado, volume=source)
             for lado in ("long", "short")} if tickers else {})
    blocked: dict[str, str] = {}
    ts = pd.Timestamp(janela.sessao)
    for o in ordens:
        if o.detidas != 0:
            mi = motivo_inelegivel(mic_da_linha(o.ticker, exch.get(o.ticker)), janela, cfg)
            moeda = str(moedas.get(o.ticker))
            if mi is None and cambio_do_pregao(md, moeda, janela.sessao) is None:
                mi = _motivo_cambio(moeda, janela.sessao)
            px = (md.close.at[ts, o.ticker]
                  if ts in md.close.index and o.ticker in md.close.columns else None)
            if mi is None and (px is None or pd.isna(px) or not math.isfinite(float(px))
                               or float(px) <= 0):
                mi = f"fechamento do pregão {janela.sessao:%d/%m/%Y} ausente ou inválido"
            if mi is not None:
                blocked.setdefault(o.emissor, f"{o.ticker} ({mi})")
    out: list[Preenchimento] = []
    for o in ordens:
        mic = mic_da_linha(o.ticker, exch.get(o.ticker))
        order = (int(o.alvo) - int(o.detidas)) if o.alvo is not None else 0
        base = {"emissor": o.emissor, "ticker": o.ticker, "mic": mic, "detidas": int(o.detidas),
                "ordem": order, "executadas": 0}
        if o.emissor in blocked:
            out.append(Preenchimento(**base, situacao="congelado", motivo=blocked[o.emissor]))
            continue
        if o.alvo is None:
            out.append(Preenchimento(**base, situacao="sem_preco",
                                     motivo="alvo em peso sem fechamento ou câmbio no pregão"))
            continue
        if order == 0:
            out.append(Preenchimento(**base, situacao="sem_ordem"))
            continue
        mi = motivo_inelegivel(mic, janela, cfg)
        m_res = resolver_mic(mic, cfg)
        px = o.preco
        moeda = str(moedas.get(o.ticker))
        fx = cambio_do_pregao(md, moeda, janela.sessao)
        if mi is not None:
            out.append(Preenchimento(**base, situacao="inelegivel", motivo=mi))
        elif fx is None:
            out.append(Preenchimento(**base, situacao="sem_preco",
                                     motivo=_motivo_cambio(moeda, janela.sessao)))
        elif px is None or not (px > 0):
            out.append(Preenchimento(**base, situacao="sem_preco",
                                     motivo="sem fechamento oficial ou câmbio no pregão"))
        elif (decidido_em is not None and m_res is not None and m_res in janela.corte_moc
              and decidido_em > janela.corte_moc[m_res]):
            out.append(Preenchimento(**base, situacao="apos_corte",
                                     motivo="decisão posterior ao corte de ordens do mercado"))
        elif o.alvo != 0 and abs(order) * px * fx < _banda_usd(o.ticker, order, px, cfg,
                                                               nav_pre):
            out.append(Preenchimento(**base, situacao="banda",
                                     motivo="abaixo da banda de não-negociação"))
        else:
            lado = lado_da_ordem(o.detidas, o.alvo)
            cap = float(caps[lado].at[o.ticker, "capacidade_usd"])
            fill = preencher(order, cap, px * fx)
            out.append(Preenchimento(**{**base, "executadas": fill},
                                     situacao="executada" if fill == order else "parcial",
                                     capacidade_usd=cap))
    return out


def _banda_usd(ticker: str, ordem: int, preco_local: float, cfg: FundConfig,
               nav_pre: float) -> float:
    """Menor ordem executada (USD): ``min_trade_weight`` × NAV e, com
    ``execution.max_fixed_cost_bps``, o nocional em que o custo mínimo das ordens da linha
    (lote padrão + fracionário/pico contam duas) cai a esse limite
    (:func:`cdp.portfolio.costs.banda_minima_usd`)."""
    from ..universe import listing_market
    from .costs import banda_minima_usd
    from .trades import n_orders

    return banda_minima_usd(listing_market(ticker), cfg, nav_pre,
                            n_orders(ticker, ordem, preco_local))


def conferir_efetivacao(entry: BookEntry, proposal: Proposal, decidido_em: datetime | None,
                        detidas: Mapping[tuple[str, str], int], md: MarketData,
                        cfg: FundConfig) -> list[str]:
    """Confere uma efetivação com execução no fechamento contra a regra determinística
    (:func:`preenchimentos_esperados`) recalculada com os dados do pregão: nenhuma linha pode
    negociar mais ações que a execução esperada (capacidade com o volume realizado), nem
    negociar com o mercado sem fechamento elegível, com o emissor congelado, sem preço, depois
    do corte MOC ou abaixo da banda. Execução MENOR que a esperada é aceita (conservadora).
    Devolve os problemas (vazio = conforme). O pregão é a data de ``booked_at`` no fuso do
    mandato."""

    sessao = entry.booked_at.astimezone(ZoneInfo(cfg.fund.timezone)).date()
    md_s = md.truncate(sessao)
    ts = pd.Timestamp(sessao)
    if ts not in md_s.close.index:
        return [f"sem pregão de {sessao:%d/%m/%Y} na base de mercado para conferir a execução"]
    janela = janela_execucao(sessao, cfg)
    nav_pre = float(entry.nav_usd)
    uni = md_s.universe.lines
    approved = {(p.issuer_id, p.execution_ticker): p for p in proposal.positions
                if p.weight != 0}
    if proposal.optimizer.status == "hold":
        approved = {}
    booked = {(b.issuer_id, b.ticker): b for b in entry.positions}
    keys = sorted(set(detidas) | set(approved) | set(booked))
    ordens: list[OrdemLinha] = []
    for iid, tk in keys:
        a, b = approved.get((iid, tk)), booked.get((iid, tk))
        ccy = (str(uni.at[tk, "currency"]) if tk in uni.index else
               a.currency if a is not None else b.currency if b is not None else "USD")
        px = None
        if tk in md_s.close.columns:
            v = md_s.close.at[ts, tk]
            px = float(v) if pd.notna(v) and float(v) > 0 else None
        fx = cambio_do_pregao(md_s, ccy, sessao)
        s0 = int(detidas.get((iid, tk), 0))
        if proposal.optimizer.status == "hold":
            alvo: int | None = s0
        elif a is None:
            alvo = 0
        elif a.shares is not None:
            alvo = int(a.shares)
        elif px is not None and fx is not None:
            q = a.weight * nav_pre / (px * fx)
            alvo = int(math.copysign(math.floor(abs(q) + 0.5), q))
        else:
            alvo = None
        ordens.append(OrdemLinha(iid, tk, s0, alvo, px, fx))
    esperado = {(f.emissor, f.ticker): f for f in preenchimentos_esperados(
        ordens, md_s, janela, cfg, nav_pre=nav_pre, decidido_em=decidido_em)}
    problems: list[str] = []
    for key in keys:
        f = esperado[key]
        b = booked.get(key)
        sb = int(b.shares) if b is not None and b.shares is not None else 0
        q = sb - int(detidas.get(key, 0))
        if q == 0:
            continue
        ok = f.executadas != 0 and q * f.executadas > 0 and abs(q) <= abs(f.executadas)
        if not ok:
            why = (f"execução máxima de {_int_br(abs(f.executadas))} ações" if f.executadas
                   else f"sem execução permitida ({f.motivo or f.situacao})")
            problems.append(f"{key[0]}/{key[1]}: {_int_br(abs(q))} ações negociadas em "
                            f"{sessao:%d/%m/%Y} — {why}.")
    return problems


def _int_br(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


# ============================================================ shortfall


def estatistica_t(valores: Sequence[float | None]) -> float | None:
    """t de Student da média (``None`` com menos de :data:`SHORTFALL_MIN_SEMANAS` valores ou
    variância nula)."""
    xs = [float(v) for v in valores if v is not None and math.isfinite(float(v))]
    if len(xs) < SHORTFALL_MIN_SEMANAS:
        return None
    sd = float(np.std(xs, ddof=1))
    if sd <= 0:
        return None
    return float(np.mean(xs)) / (sd / math.sqrt(len(xs)))


def shortfall(linhas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Implementation shortfall de um fechamento (paper trading), por linha negociada.

    Cada linha: ``ordem`` (ações, com sinal), ``executadas`` (com sinal), ``preco_decisao`` e
    ``preco_fechamento`` (moeda local), ``fx`` (USD por unidade), ``custo_modelo_usd`` e,
    opcionais, ``volume_acoes`` (realizado no pregão), ``fatia_leilao`` e ``fatia_pre``.

    - deriva decisão→fechamento (USD) = Σ executadas × (fechamento − decisão) × fx (positivo =
      custo);
    - custo de oportunidade (USD) = Σ (ordem − executadas) × (fechamento − decisão) × fx;
    - custo modelado (USD) = Σ custo do modelo das ações executadas (em paper trading é também
      o custo debitado: a parcela mensurável do shortfall é a deriva);
    - participação = executadas / volume do pregão; na JANELA DE FECHAMENTO (leilão + janela
      pré-fechamento, toda executada ao preço oficial de fechamento) = executadas /
      ((fatia_leilão + fatia_pré) × volume) — limitada por construção a ``p_leilão``/``p_pré``
      (10%); só no leilão = executadas / (fatia_leilão × volume) (inclui a parcela pré-fechamento,
      por isso pode passar de ``p_leilão``).
    Valores em bps do nocional executado; ``None`` sem negociação."""
    drift = opp = modelo = exec_usd = ord_usd = 0.0
    part: list[float] = []
    part_leilao: list[float] = []
    part_janela: list[float] = []
    n = 0
    for ln in linhas:
        q = float(ln.get("executadas") or 0)
        o = float(ln.get("ordem") or 0)
        pd_, pc = ln.get("preco_decisao"), ln.get("preco_fechamento")
        fx = ln.get("fx")
        if pc is None or fx is None or not math.isfinite(float(pc)) or not math.isfinite(
                float(fx)):
            continue
        pc, fx = float(pc), float(fx)
        ord_usd += abs(o) * pc * fx
        if q != 0:
            n += 1
            exec_usd += abs(q) * pc * fx
            modelo += float(ln.get("custo_modelo_usd") or 0.0)
        if pd_ is not None and math.isfinite(float(pd_)):
            dp = (pc - float(pd_)) * fx
            drift += q * dp
            opp += (o - q) * dp
        vol = ln.get("volume_acoes")
        if q != 0 and vol is not None and math.isfinite(float(vol)) and float(vol) > 0:
            part.append(abs(q) / float(vol))
            share = ln.get("fatia_leilao")
            if share is not None and float(share) > 0:
                part_leilao.append(abs(q) / (float(share) * float(vol)))
            pre = ln.get("fatia_pre")
            win = (float(share) if share is not None else 0.0) + (
                float(pre) if pre is not None else 0.0)
            if win > 0:
                part_janela.append(abs(q) / (win * float(vol)))

    def bps(x: float) -> float | None:
        return x / exec_usd * 1e4 if exec_usd > 0 else None

    return {
        "linhas_negociadas": n, "nocional_executado_usd": exec_usd,
        "nocional_ordenado_usd": ord_usd,
        "taxa_execucao": exec_usd / ord_usd if ord_usd > 0 else None,
        "deriva_usd": drift, "deriva_bps": bps(drift),
        "oportunidade_usd": opp, "oportunidade_bps": bps(opp),
        "custo_modelo_usd": modelo, "custo_modelo_bps": bps(modelo),
        "shortfall_bps": bps(drift + modelo),
        "participacao_mediana": float(np.median(part)) if part else None,
        "participacao_max": float(np.max(part)) if part else None,
        "participacao_leilao_mediana": float(np.median(part_leilao)) if part_leilao else None,
        "participacao_leilao_max": float(np.max(part_leilao)) if part_leilao else None,
        "participacao_janela_mediana": float(np.median(part_janela)) if part_janela else None,
        "participacao_janela_max": float(np.max(part_janela)) if part_janela else None,
    }


# ============================================================ período de montagem


def trajetoria_montagem(pesos: Mapping[str, float],
                        capacidade_peso: Mapping[str, float] | Sequence[Mapping[str, float]],
                        vol_ex_ante: float | None, vol_alvo: float,
                        fechamentos: int = TRAJETORIA_FECHAMENTOS) -> dict[str, Any]:
    """Trajetória CONDICIONAL do risco no período de montagem, pela capacidade de fechamento:
    se a composição da carteira fosse mantida, o escalar ``m_k`` alcançável após ``k``
    fechamentos semanais é o menor ``(|w_i| + Σ_{j≤k} c_ij)/|w_i|`` entre os nomes com
    capacidade (``c_ij`` = capacidade do nome no j-ésimo fechamento, em fração do NAV);
    ``vol_k = vol_0 · min(m_k, vol_alvo/vol_0)``.

    ``capacidade_peso``: um mapa (a mesma capacidade em todo fechamento) ou uma sequência de
    mapas, um por fechamento futuro (feriados zeram o mercado naquela janela; depois do último
    mapa vale o último). Nomes sem capacidade em nenhum fechamento (volume desconhecido) ficam
    fixos e não limitam a escala (listados em ``nomes_sem_capacidade``). Carteira já na meta ou
    acima (``m* ≤ 1``): trajetória constante na vol atual e ``fechamentos_ate_meta = 0`` — não há
    período de montagem a publicar. ``fechamentos_ate_meta``: primeiro ``k`` com
    ``vol_k ≥ vol_alvo`` (``None`` além do horizonte ou sem dados)."""
    w = {k: abs(float(v)) for k, v in pesos.items() if v and math.isfinite(float(v))}
    out: dict[str, Any] = {"vol_ex_ante": vol_ex_ante, "vol_alvo": vol_alvo,
                           "trajetoria": [], "fechamentos_ate_meta": None,
                           "nomes_sem_capacidade": []}
    if not w or vol_ex_ante is None or not math.isfinite(vol_ex_ante) or vol_ex_ante <= 0:
        return out
    seq: list[Mapping[str, float]] = (
        [capacidade_peso] if isinstance(capacidade_peso, Mapping) else list(capacidade_peso))
    if not seq:
        seq = [{}]

    def cap(j: int, name: str) -> float:
        m = seq[min(j, len(seq) - 1)]
        v = m.get(name, 0.0)
        try:
            f = float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return f if math.isfinite(f) and f > 0 else 0.0

    m_star = vol_alvo / vol_ex_ante
    out["escala_necessaria"] = m_star
    horizon = max(fechamentos, len(seq))
    fixed = sorted(k for k in w if not any(cap(j, k) > 0 for j in range(horizon)))
    out["nomes_sem_capacidade"] = fixed
    live = {k: v for k, v in w.items() if k not in fixed}
    acc = {k: 0.0 for k in live}
    traj = []
    for k in range(fechamentos + 1):
        if k > 0:
            for name in live:
                acc[name] += cap(k - 1, name)
        if m_star <= 1.0 or not live:
            m = 1.0  # já na meta (ou nada a escalar): a trajetória é a própria vol atual
        else:
            m = min(min((v + acc[i]) / v for i, v in live.items()), m_star)
        traj.append({"fechamento": k, "vol": vol_ex_ante * m})
        if out["fechamentos_ate_meta"] is None and vol_ex_ante * m >= vol_alvo * (1 - 1e-9):
            out["fechamentos_ate_meta"] = k
    out["trajetoria"] = traj
    return out


# ============================================================ estresse de liquidez


def estresse_liquidez(pesos: Mapping[str, float], capacidade_peso: Mapping[str, float],
                      nav: float, *, fator_volume: float = ESTRESSE_VOLUME,
                      horizontes: Sequence[int] = (1, 3, 5, 10)) -> dict[str, Any]:
    """Liquidez da carteira em estresse, contada em fechamentos (a execução é só no leilão).

    Capacidade de estresse por nome = ``fator_volume`` × capacidade de fechamento (volume P10 por
    nome nos episódios de estresse da região, ≈ 0,7 × ADV); fração do gross liquidável em ``h``
    fechamentos = Σ min(|w_i|, h·c_i·fator)/Σ|w_i|; nomes sem capacidade não liquidam.
    ``fechamentos_p90``: fechamentos para zerar 90% do gross. Spread × 2 e σ × 2 entram no custo
    (:data:`ESTRESSE_SPREAD_MULT`, :data:`ESTRESSE_VOL_MULT`)."""
    w = {k: abs(float(v)) for k, v in pesos.items() if v and math.isfinite(float(v))}
    gross = sum(w.values())
    out: dict[str, Any] = {"fator_volume": fator_volume, "nav_usd": nav,
                           "gross": gross, "fracao_liquidavel": {}, "fechamentos_p90": None,
                           "nomes_sem_capacidade": sorted(
                               k for k in w if not float(capacidade_peso.get(k, 0) or 0) > 0)}
    if gross <= 0:
        return out
    caps = {k: float(capacidade_peso.get(k, 0.0) or 0.0) * fator_volume for k in w}
    for h in horizontes:
        liq = sum(min(v, h * caps[k]) for k, v in w.items())
        out["fracao_liquidavel"][int(h)] = liq / gross
    for h in range(1, 61):
        liq = sum(min(v, h * caps[k]) for k, v in w.items())
        if liq / gross >= 0.9 - 1e-12:
            out["fechamentos_p90"] = h
            break
    dias = [v / caps[k] for k, v in w.items() if caps[k] > 0]
    out["fechamentos_max_nome"] = max(dias) if dias else None
    return out


__all__ = [
    "ESTRESSE_REVERSO_VOLUME", "ESTRESSE_SPREAD_MULT", "ESTRESSE_VOLUME", "ESTRESSE_VOL_MULT",
    "EXCHANGE_MIC", "JanelaExecucao", "MERCADOS_PRAZO", "MIC_NOME", "OrdemLinha",
    "Preenchimento", "SHORTFALL_SEMANAS", "TRAJETORIA_FECHAMENTOS", "adv_fechamento_usd",
    "capacidade_fechamento_usd", "capacidade_por_janela", "categoria_da_linha",
    "conferir_efetivacao", "emissores_congelados", "estatistica_t", "estresse_liquidez",
    "fechamento_execucao", "fechamento_mais_tardio", "fechamentos_necessarios",
    "janela_execucao", "janela_regular", "lado_da_ordem", "mercados_elegiveis", "mic_da_linha",
    "mics_antecipados", "motivo_inelegivel", "preencher", "preenchimentos_esperados",
    "prazo_efetivo", "resolver_mic", "rotear_linhas", "shortfall", "tabela_capacidade",
    "trajetoria_montagem", "valor_negociado_usd", "volume_realizado_usd",
]
