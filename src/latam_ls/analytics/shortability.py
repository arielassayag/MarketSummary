"""Disponibilidade de aluguel (short) por linha e escolha da linha de execução por emissor.

Regras (ver docs/latam_ls/ARQUITETURA.md §8 e ``shorting`` em ``configs/latam_ls/fund.yaml``):

a) **ADR / US_LISTED** (mercado US): alugável se o tipo de linha estiver em
   ``shorting.shortable_line_types`` e o market cap do emissor for >= ``min_market_cap_short_usd``.
   Não há taxa pública: usa-se a taxa GC estimada ``gc_borrow_fee_us``, escalada quando o short
   interest (``short_pct_float``) é alto: >= ``squeeze.si_pct_float_high`` ⇒ 5% a.a. (hard to
   borrow); >= 2× esse nível ⇒ 15% a.a. ("special"), que excede ``max_borrow_fee`` no mandato
   padrão e, portanto, bloqueia o short. ``fee_source = GC_ESTIMATE_US`` (estimativa).
   **Piso pela B3**: se o emissor tem taxa observada no BTC da B3 (linha local), a taxa estimada
   da linha em USD é no mínimo a maior taxa observada localmente. ADR e ação local são
   arbitrados via depositário, então um aluguel *special* na B3 não convive com GC no ADR; sem
   o piso, o otimizador migraria o short para o ADR com custo subestimado.
b) **Local Brasil** (``LOCAL_BR``): taxa observada no BTC da B3 (``lending.lending_rate_annual``,
   ``fee_source = B3_BTC``); sem taxa observada, só é alugável se o emissor tiver ADTV >= USD 10
   mi e market cap >= USD 1 bi (taxa GC estimada ``gc_borrow_fee_br``, ``GC_ESTIMATE_BR``);
   caso contrário não é alugável ("sem dado de aluguel e baixa liquidez").
c) **Demais mercados locais** (MX, CL, CO, PE, AR): não alugáveis por um fundo offshore em USD
   (empréstimo local inacessível ou sem liquidez); o short deve ser feito via ADR.
d) Taxa > ``max_borrow_fee`` ⇒ não alugável. Linha sem dados de preço ⇒ não alugável.

Política conservadora adicional: o market cap mínimo do mandato (``min_market_cap_short_usd``)
vale para qualquer short, inclusive linhas locais brasileiras com taxa observada; market cap
ausente bloqueia o short (não se presume que o emissor é grande o bastante).

A taxa é sempre informada quando há fonte ou estimativa, mesmo para linhas não alugáveis — ela
alimenta o escore de risco de short squeeze. Sem fonte nem estimativa a taxa fica ``NaN`` e a
fonte ``NA`` (nunca zero).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..analytics.panel import AssetPanel
from ..config import FundConfig
from ..market import MarketData

FEE_SOURCE_B3 = "B3_BTC"
FEE_SOURCE_GC_US = "GC_ESTIMATE_US"
FEE_SOURCE_GC_BR = "GC_ESTIMATE_BR"
FEE_SOURCE_NA = "NA"
ESTIMATED_FEE_SOURCES = frozenset({FEE_SOURCE_GC_US, FEE_SOURCE_GC_BR})

USD_LINE_TYPES = ("ADR", "US_LISTED")
LOCAL_BR_TYPE = "LOCAL_BR"

US_HTB_FEE_ESTIMATE = 0.05
"""Taxa anual estimada para ADR com short interest >= ``si_pct_float_high`` (hard to borrow)."""
US_SPECIAL_FEE_ESTIMATE = 0.15
"""Taxa anual estimada para ADR com short interest >= 2 × ``si_pct_float_high`` ("special")."""
BR_GC_MIN_ADTV_USD = 10_000_000.0
BR_GC_MIN_MCAP_USD = 1_000_000_000.0
TIE_TOLERANCE = 0.10
"""Linhas com ADTV dentro de 10% do maior ADTV do emissor são consideradas empatadas."""

AVAILABILITY_COLUMNS = [
    "issuer_id", "market", "line_type", "shortable", "borrow_fee_annual", "fee_source",
    "fee_is_estimate", "reason",
]
SIDE_LINE_COLUMNS = [
    "long_ticker", "long_line_type", "long_currency", "adtv_long_usd",
    "short_ticker", "short_line_type", "short_currency", "adtv_short_usd",
    "can_short", "borrow_fee_annual", "fee_source", "short_reason",
]
REASON_NO_DATA = "linha sem dados de preço"
REASON_LOCAL_OFFSHORE = (
    "mercado local sem empréstimo utilizável por fundo offshore; usar ADR"
)
REASON_BR_NO_LENDING = "sem dado de aluguel e baixa liquidez"


# ----------------------------------------------------------------------------------------
# Utilitários
# ----------------------------------------------------------------------------------------

def numeric_field(table: pd.DataFrame, column: str, index: pd.Index) -> pd.Series:
    """Coluna numérica de uma tabela por ticker, alinhada a ``index``.

    Coluna ou linha ausente ⇒ ``NaN``; valores não numéricos, não finitos ou negativos ⇒ ``NaN``
    (dado inválido é tratado como ausente, nunca como zero).
    """
    if table is None or table.empty or column not in table.columns:
        return pd.Series(np.nan, index=index, dtype=float)
    s = pd.to_numeric(table[column], errors="coerce").astype(float)
    s = s[~s.index.duplicated(keep="first")].reindex(index)
    return s.where(np.isfinite(s) & (s >= 0.0))


def _fmt_pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _line_fee(market: pd.Series, line_type: pd.Series, issuer: pd.Series, si: pd.Series,
              b3_rate: pd.Series, issuer_adtv: pd.Series, issuer_mcap: pd.Series,
              cfg: FundConfig) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Taxa anual de aluguel (observada ou estimada), fonte e piso B3 aplicado, por linha.

    O piso B3 vale para linhas em USD de emissores com taxa observada no BTC da B3: a taxa
    estimada da linha em USD é ``max(estimativa por SI, maior taxa B3 observada do emissor)``.
    """
    sc, sq = cfg.shorting, cfg.squeeze
    is_us = (market == "US") & line_type.isin(USD_LINE_TYPES)
    is_br = (market == "BR") & (line_type == "LOCAL")
    high = sq.si_pct_float_high
    with np.errstate(invalid="ignore"):
        si_fee = np.select([si >= 2.0 * high, si >= high],
                           [US_SPECIAL_FEE_ESTIMATE, US_HTB_FEE_ESTIMATE],
                           default=sc.gc_borrow_fee_us)
    si_fee = pd.Series(np.maximum(si_fee, sc.gc_borrow_fee_us), index=market.index, dtype=float)
    b3_by_issuer = b3_rate.where(is_br).groupby(issuer).max()
    b3_floor = issuer.map(b3_by_issuer).astype(float).where(is_us)
    floor_applied = (b3_floor > si_fee).fillna(False).astype(bool)
    us_fee = si_fee.where(~floor_applied, b3_floor)
    br_gc_ok = (issuer_adtv >= BR_GC_MIN_ADTV_USD) & (issuer_mcap >= BR_GC_MIN_MCAP_USD)
    has_b3 = b3_rate.notna()
    fee = np.select(
        [is_us, is_br & has_b3, is_br & br_gc_ok],
        [us_fee.to_numpy(), b3_rate.to_numpy(), sc.gc_borrow_fee_br],
        default=np.nan,
    )
    source = np.select(
        [is_us, is_br & has_b3, is_br & br_gc_ok],
        [FEE_SOURCE_GC_US, FEE_SOURCE_B3, FEE_SOURCE_GC_BR],
        default=FEE_SOURCE_NA,
    )
    idx = market.index
    return (pd.Series(fee, index=idx, dtype=float), pd.Series(source, index=idx, dtype=object),
            floor_applied & is_us)


def _block_reason(row: pd.Series, cfg: FundConfig) -> str:
    """Primeira regra que bloqueia o short da linha ('' se alugável)."""
    sc = cfg.shorting
    if not row["has_data"]:
        return REASON_NO_DATA
    if not (row["is_us"] or row["is_br"]):
        if row["market"] not in ("US", "BR"):
            return REASON_LOCAL_OFFSHORE
        return f"tipo de linha {row['line_type']} sem empréstimo utilizável"
    if not row["type_allowed"]:
        label = LOCAL_BR_TYPE if row["is_br"] else row["line_type"]
        return f"tipo de linha {label} não alugável pela configuração"
    if pd.isna(row["mcap"]):
        return "market cap do emissor ausente: short não permitido"
    if row["mcap"] < sc.min_market_cap_short_usd:
        return (f"market cap USD {row['mcap'] / 1e6:,.0f} mi abaixo do mínimo para short "
                f"(USD {sc.min_market_cap_short_usd / 1e6:,.0f} mi)")
    if pd.isna(row["fee"]):
        return REASON_BR_NO_LENDING
    if row["fee"] > sc.max_borrow_fee:
        est = " estimada" if row["fee_source"] in ESTIMATED_FEE_SOURCES else ""
        if row["b3_floor"]:
            note = " (piso: taxa observada no BTC da B3 do mesmo emissor)"
        elif row["is_us"] and pd.notna(row["si"]):
            note = f" (short interest {_fmt_pct(row['si'])} do float)"
        else:
            note = ""
        return (f"taxa de aluguel{est} {_fmt_pct(row['fee'])}{note} acima do máximo "
                f"{_fmt_pct(sc.max_borrow_fee)}")
    return ""


def _ok_reason(row: pd.Series, cfg: FundConfig) -> str:
    """Descrição da fonte da taxa para linhas alugáveis."""
    src = row["fee_source"]
    if src == FEE_SOURCE_B3:
        return f"BTC B3: taxa observada {_fmt_pct(row['fee'])} a.a."
    if src == FEE_SOURCE_GC_BR:
        return (f"BTC B3 sem taxa observada; taxa GC estimada {_fmt_pct(row['fee'])} a.a. "
                "(emissor líquido e de grande porte)")
    if row["b3_floor"]:
        return (f"{row['line_type']} alugável; taxa estimada {_fmt_pct(row['fee'])} a.a. "
                "(piso: taxa observada no BTC da B3 do mesmo emissor, arbitragem ADR↔local)")
    if row["fee"] > cfg.shorting.gc_borrow_fee_us:
        return (f"{row['line_type']} alugável; taxa estimada {_fmt_pct(row['fee'])} a.a. elevada "
                f"por short interest alto ({_fmt_pct(row['si'])} do float)")
    si_note = "" if pd.notna(row["si"]) else "; sem dado de short interest"
    return (f"{row['line_type']} alugável; taxa GC estimada {_fmt_pct(row['fee'])} a.a. "
            f"(sem dado público){si_note}")


# ----------------------------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------------------------

def short_availability(panel: AssetPanel, md: MarketData, cfg: FundConfig) -> pd.DataFrame:
    """Disponibilidade de short por linha (índice = ticker da linha).

    Colunas: ``issuer_id``, ``market``, ``line_type``, ``shortable`` (bool),
    ``borrow_fee_annual`` (float ou ``NaN``), ``fee_source`` (``B3_BTC`` | ``GC_ESTIMATE_US`` |
    ``GC_ESTIMATE_BR`` | ``NA``), ``fee_is_estimate`` (bool) e ``reason`` (texto pt-BR com o
    motivo do bloqueio ou a origem da taxa).
    """
    lines = panel.lines
    idx = lines.index
    sc = cfg.shorting
    market = lines["market"].astype(str)
    line_type = lines["line_type"].astype(str)
    issuer = lines["issuer_id"].astype(str)
    issuer_mcap = issuer.map(panel.assets["market_cap_usd"]).astype(float)
    issuer_adtv = issuer.map(panel.assets["adtv_usd"]).astype(float)
    si = numeric_field(md.short_interest, "short_pct_float", idx)
    b3_rate = numeric_field(md.lending, "lending_rate_annual", idx)

    fee, source, b3_floor = _line_fee(market, line_type, issuer, si, b3_rate, issuer_adtv,
                                      issuer_mcap, cfg)
    is_us = (market == "US") & line_type.isin(USD_LINE_TYPES)
    is_br = (market == "BR") & (line_type == "LOCAL")
    allowed = set(sc.shortable_line_types)
    type_allowed = (is_us & line_type.isin(allowed)) | (is_br & (LOCAL_BR_TYPE in allowed))

    work = pd.DataFrame({
        "has_data": lines["has_data"].fillna(False).astype(bool),
        "market": market, "line_type": line_type, "is_us": is_us, "is_br": is_br,
        "type_allowed": type_allowed, "mcap": issuer_mcap, "si": si, "fee": fee,
        "fee_source": source, "b3_floor": b3_floor,
    }, index=idx)
    block = work.apply(_block_reason, axis=1, cfg=cfg) if len(work) else pd.Series(dtype=object)
    shortable = block.eq("")
    ok_reason = (work[shortable].apply(_ok_reason, axis=1, cfg=cfg)
                 if shortable.any() else pd.Series(dtype=object))
    reason = block.where(~shortable, ok_reason.reindex(idx))

    out = pd.DataFrame({
        "issuer_id": issuer,
        "market": market,
        "line_type": line_type,
        "shortable": shortable.astype(bool),
        "borrow_fee_annual": fee,
        "fee_source": source,
        "fee_is_estimate": source.isin(ESTIMATED_FEE_SOURCES),
        "reason": reason.astype(object),
    }, index=idx)
    out.index.name = "ticker"
    return out[AVAILABILITY_COLUMNS]


def _pick_line(cands: pd.DataFrame) -> pd.DataFrame:
    """Escolhe uma linha por emissor: maior ADTV; empate (±10%) ⇒ linha em USD (ADR/US).

    Desempates seguintes: maior ADTV, linha primária, ticker (determinístico). Linhas sem ADTV
    só são escolhidas se nenhuma linha do emissor tiver ADTV.
    """
    if cands.empty:
        return cands.assign(_ticker=pd.Series(dtype=object)).set_index("issuer_id")
    c = cands.copy()
    best = c.groupby("issuer_id")["adtv_usd"].transform("max")
    c["_tied"] = (c["adtv_usd"] >= (1.0 - TIE_TOLERANCE) * best).fillna(False)
    c["_usd"] = c["line_type"].isin(USD_LINE_TYPES)
    c["_primary"] = c["primary_line"].fillna(False).astype(bool)
    c["_ticker"] = c.index.astype(str)
    c = c.sort_values(["issuer_id", "_tied", "_usd", "adtv_usd", "_primary", "_ticker"],
                      ascending=[True, False, False, False, False, True], na_position="last")
    return c.groupby("issuer_id", sort=False).head(1).set_index("issuer_id")


def issuer_side_lines(panel: AssetPanel, availability: pd.DataFrame) -> pd.DataFrame:
    """Linha de execução por emissor para o lado comprado e o vendido.

    - Long: linha com dados de maior ADTV; empate (ADTV dentro de 10% do maior) ⇒ ADR/US_LISTED
      (sem câmbio nem custódia local).
    - Short: entre as linhas alugáveis com dados, a de maior ADTV (mesmo critério de empate).

    Índice ``issuer_id`` (todos os emissores do painel). Colunas: ``long_ticker``,
    ``long_line_type``, ``long_currency``, ``adtv_long_usd``, ``short_ticker`` (``None`` se não
    houver linha alugável), ``short_line_type``, ``short_currency``, ``adtv_short_usd`` (``NaN``
    sem short), ``can_short``, ``borrow_fee_annual``, ``fee_source`` (``NA`` sem short) e
    ``short_reason`` (origem da taxa ou motivos de bloqueio por linha).
    Linhas ausentes de ``availability`` são tratadas como não alugáveis.
    """
    lines = panel.lines
    avail = availability.reindex(lines.index)
    shortable = avail["shortable"].astype("boolean").fillna(False).astype(bool)
    has_data = lines["has_data"].fillna(False).astype(bool)
    base = pd.DataFrame({
        "issuer_id": lines["issuer_id"].astype(str),
        "line_type": lines["line_type"].astype(str),
        "currency": lines["currency"].astype(str),
        "adtv_usd": lines["adtv_usd"].astype(float),
        "primary_line": lines["primary_line"],
        "borrow_fee_annual": avail["borrow_fee_annual"].astype(float),
        "fee_source": avail["fee_source"],
        "reason": avail["reason"],
    }, index=lines.index)
    base["adtv_usd"] = base["adtv_usd"].where(base["adtv_usd"] > 0)

    long_pick = _pick_line(base[has_data])
    short_pick = _pick_line(base[has_data & shortable])
    ids = panel.assets.index

    out = pd.DataFrame(index=ids)
    out["long_ticker"] = _obj(_col(long_pick, "_ticker"), ids)
    out["long_line_type"] = _obj(_col(long_pick, "line_type"), ids)
    out["long_currency"] = _obj(_col(long_pick, "currency"), ids)
    out["adtv_long_usd"] = _num(_col(long_pick, "adtv_usd"), ids)
    out["short_ticker"] = _obj(_col(short_pick, "_ticker"), ids)
    out["short_line_type"] = _obj(_col(short_pick, "line_type"), ids)
    out["short_currency"] = _obj(_col(short_pick, "currency"), ids)
    out["adtv_short_usd"] = _num(_col(short_pick, "adtv_usd"), ids)
    out["can_short"] = out["short_ticker"].notna()
    out["borrow_fee_annual"] = _num(_col(short_pick, "borrow_fee_annual"), ids)
    out["fee_source"] = _obj(_col(short_pick, "fee_source"), ids).where(out["can_short"],
                                                                        FEE_SOURCE_NA)
    out["short_reason"] = _short_reasons(base, short_pick, ids)
    out.index.name = "issuer_id"
    return out[SIDE_LINE_COLUMNS]


def _col(pick: pd.DataFrame, column: str) -> pd.Series | None:
    """Coluna da linha escolhida por emissor (``None`` se nenhum emissor teve linha)."""
    return None if pick.empty else pick[column]


def _obj(s: pd.Series | None, ids: pd.Index) -> pd.Series:
    if s is None:
        return pd.Series([None] * len(ids), index=ids, dtype=object)
    r = s.reindex(ids).astype(object)
    return r.where(r.notna(), None)


def _num(s: pd.Series | None, ids: pd.Index) -> pd.Series:
    if s is None:
        return pd.Series(np.nan, index=ids, dtype=float)
    return s.reindex(ids).astype(float)


def _short_reasons(base: pd.DataFrame, short_pick: pd.DataFrame, ids: pd.Index) -> pd.Series:
    """Motivo do short por emissor: origem da taxa (alugável) ou bloqueios por linha."""
    blocked = base.assign(_txt=base.index.astype(str) + ": " + base["reason"].fillna(
        "sem avaliação de aluguel").astype(str))
    per_issuer = blocked.groupby("issuer_id")["_txt"].agg("; ".join)
    out = per_issuer.reindex(ids).astype(object)
    out = out.where(out.notna(), "emissor sem linhas no painel")
    if not short_pick.empty:
        ok = (short_pick["_ticker"] + ": " + short_pick["reason"].astype(str)).reindex(ids)
        out = ok.where(ok.notna(), out)
    return out.astype(object)
