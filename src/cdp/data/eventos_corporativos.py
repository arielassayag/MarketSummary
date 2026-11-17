"""Mudanças de unidade com vigência e evidência primária; nunca inferidas do preço."""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..hashing import sha256_file, sha256_obj
from ..leitura_arquivos import ler_texto

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "configs/cdp/eventos_corporativos.yaml"


class CorporateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str = Field(min_length=1)
    effective_on: date
    announced_on: date
    quantity_factor: float = Field(gt=0, allow_inf_nan=False)
    source_url: str = Field(pattern=r"^https://")
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_path: str | None = None
    adr_ratio_before: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    adr_ratio_after: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_event(self):
        if self.announced_on > self.effective_on or self.quantity_factor == 1:
            raise ValueError("evento sem mudança de unidade ou anunciado após vigência")
        if (self.adr_ratio_before is None) != (self.adr_ratio_after is None):
            raise ValueError("ratio ADR exige os valores antes e depois")
        if self.adr_ratio_before is not None and not math.isclose(
                self.adr_ratio_before / self.adr_ratio_after, self.quantity_factor):
            raise ValueError("ratio ADR incompatível com fator de quantidade")
        return self


def catalog(path: Path | None = None) -> tuple[CorporateAction, ...]:
    from ..leitura_arquivos import raiz_recebida

    if path is None:
        received_root = raiz_recebida()
        path = received_root / "configs/cdp/eventos_corporativos.yaml" if received_root else CATALOG
    root = path.absolute().parent.parent.parent
    body = yaml.safe_load(ler_texto(path))
    events = tuple(CorporateAction.model_validate(v) for v in body["events"])
    keys = [(e.ticker, e.effective_on) for e in events]
    if len(keys) != len(set(keys)):
        raise ValueError("evento corporativo duplicado")
    for e in events:
        if e.evidence_path is None:
            raise ValueError("evidência primária arquivada ausente")
        p = root / e.evidence_path
        resolved = p.resolve()
        if p != resolved or not resolved.is_relative_to(
                root / "docs/cdp/evidencias/eventos_corporativos"):
            raise ValueError("evidência fora da pasta canônica")
        if not p.is_file() or p.is_symlink() or sha256_file(p) != e.evidence_sha256:
            raise ValueError("evidência do evento corporativo ausente/adulterada")
    return tuple(sorted(events, key=lambda e: (e.effective_on, e.ticker)))


def factor(events, ticker: str, after: date, through: date) -> float:
    return math.prod(e.quantity_factor for e in events
                     if e.ticker == ticker and after < e.effective_on <= through)


def digest(events) -> str:
    return sha256_obj([e.model_dump(mode="json") for e in events])


def ratio_at(events, ticker, day, default):
    matches = [e for e in events if e.ticker == ticker and e.adr_ratio_after is not None]
    value = default
    for e in sorted(matches, key=lambda e: e.effective_on):
        if day < e.effective_on:
            return e.adr_ratio_before if value == default else value
        value = e.adr_ratio_after
    return value


def effective_universe(universe, events, day):
    from dataclasses import replace

    lines = universe.lines.copy()
    for e in events:
        if e.ticker in lines.index and e.adr_ratio_after is not None:
            lines.loc[e.ticker, "adr_ratio"] = ratio_at(
                events, e.ticker, day, lines.loc[e.ticker, "adr_ratio"])
    return universe if lines.equals(universe.lines) else replace(universe, lines=lines)


def unverified_observations(combined, increments):
    import pandas as pd

    tabs = [tab for tab in increments if not tab.empty]
    if not tabs:
        return ()
    valid = combined.loc[pd.to_numeric(combined["close"], errors="coerce") > 0]
    ordered = valid.sort_values("date").drop_duplicates(["ticker", "date"]).copy()
    ordered["_previous"] = ordered.groupby("ticker", sort=False)["date"].shift()
    # A data anterior usa todo o histórico; só os pares dos incrementos precisam
    # virar objetos Python para a comparação de base. A guarda permanece igual.
    keys = pd.concat([tab[["ticker", "date"]] for tab in tabs]).drop_duplicates()
    keys["date"] = pd.to_datetime(keys["date"])
    selected = ordered[["ticker", "date", "_previous"]].merge(
        keys, on=["ticker", "date"], how="inner", sort=False).dropna(subset=["_previous"])
    previous = {(str(t), pd.Timestamp(d)): pd.Timestamp(p)
                for t, d, p in selected.itertuples(index=False, name=None)}
    return tuple((pd.Timestamp(r.date).date(), str(r.ticker)) for tab in increments
                 for r in tab.itertuples()
                 if (p := previous.get((str(r.ticker), pd.Timestamp(r.date)))) is not None
                 and not comparable_basis(r, p))


def comparable_basis(row, previous_date):
    import pandas as pd

    observed = getattr(row, "prev_date", None)
    return (observed is not None and pd.notna(observed)
            and pd.Timestamp(observed) == pd.Timestamp(previous_date)
            and getattr(row, "prev_adj_close_window", math.nan) > 0
            and getattr(row, "adj_close", math.nan) > 0)
