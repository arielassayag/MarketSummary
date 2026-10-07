"""Atualização "ao vivo" dos dados lentos no momento da análise (fundamentos, short interest,
aluguel da B3 e notícias até agora), gravada com hash e sobreposta ao ``MarketData``.

Complementa ``intraday.py``: juntos garantem que a decisão do dia de montagem use TODO dado
disponível até o momento da análise, e que a etapa ``decide`` reproduza exatamente o mesmo
conjunto.

Falha de coleta (rede fora, endpoint do Yahoo fora) nunca apaga o que já está gravado: fonte sem
resposta fica registrada em ``failures`` e a análise usa o último dado gravado daquela fonte
(fundamentos, short interest e notícias); linha de fundamentos sem dado nunca substitui a gravada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from ..contracts import NewsItem, SnapshotFile
from ..hashing import sha256_file
from ..market import MarketData

FILES = {
    "fundamentals": "fundamentals.parquet",
    "short_interest": "short_interest.parquet",
    "lending": "lending.parquet",
    "news": "news.jsonl",
}


@dataclass(frozen=True)
class SlowRefresh:
    fundamentals: pd.DataFrame | None
    short_interest: pd.DataFrame | None
    lending: pd.DataFrame | None
    news: list[NewsItem] | None
    failures: list[str]


def fetch_slow_refresh(md: MarketData, as_of: date, *, lookback_days: int = 14,
                       include_news: bool = True) -> SlowRefresh:
    """Coleta os dados lentos mais recentes; cada fonte que falhar é registrada (nunca inventada)."""
    from . import b3_lending, news, yahoo

    uni = md.universe
    lines = uni.lines
    failures: list[str] = []
    fund = si = lend = None
    items: list[NewsItem] | None = None
    try:
        fund = yahoo.fetch_fundamentals(list(lines.index), currency_map=lines["currency"].to_dict(),
                                        as_of=as_of)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"fundamentos: {exc}")
    if fund is not None:
        fund, nota = _fundamentos_coletados(fund, md.fundamentals)
        if nota:
            failures.append(nota)
    us = [t for t in lines.index if lines.loc[t, "market"] == "US"]
    try:
        ratios = {t: float(r) for t, r in lines["adr_ratio"].dropna().items()}
        si = yahoo.fetch_short_interest(us, as_of=as_of, adr_ratios=ratios)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"short interest: {exc}")
    if si is not None and us and (len(si) == 0 or bool(_si_sem_dados(si).all())):
        failures.append(f"short interest: sem dados para nenhuma das {len(us)} linhas nos EUA "
                        "(falha de coleta); vale o short interest gravado")
        si = None
    br = [t for t in lines.index if lines.loc[t, "market"] == "BR"]
    try:
        shares = None
        if md.fundamentals is not None and "shares_outstanding" in md.fundamentals:
            shares = md.fundamentals["shares_outstanding"].dropna().to_dict()
        long_df = b3_lending.fetch_b3_lending(br, as_of - timedelta(days=10), as_of,
                                              shares_outstanding=shares)
        if long_df.attrs.get("falhas"):
            failures.append("aluguel B3 (parcial): " + "; ".join(long_df.attrs["falhas"][-2:]))
        lend = b3_lending.latest_lending(long_df, as_of)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"aluguel B3: {exc}")
    rede_fora = (fund is None and si is None and (lend is None or len(lend) == 0)
                 and len(failures) >= 3)
    if include_news and rede_fora:
        # Yahoo, FINRA e B3 sem resposta: rede fora. Não espera centenas de tempos-limite nas
        # notícias (minutos antes do prazo da decisão); valem as notícias gravadas.
        failures.append("notícias: não coletadas (Yahoo, FINRA e B3 sem resposta: rede fora); "
                        "valem as notícias gravadas")
    elif include_news:
        try:
            items, failed = news.fetch_news(news.queries_from_universe(uni), as_of, lookback_days)
            if failed and not items:
                # Nenhuma resposta: falha de coleta (rede fora) — valem as notícias gravadas.
                failures.append(f"notícias: nenhuma resposta ({len(failed)} emissor(es)); valem "
                                "as notícias gravadas")
                items = None
            elif failed:
                failures.append(f"notícias: {len(failed)} emissor(es) sem resposta")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"notícias: {exc}")
    return SlowRefresh(fund, si, lend, items, failures)


def _fundamentos_coletados(new: pd.DataFrame, old: pd.DataFrame | None
                           ) -> tuple[pd.DataFrame | None, str | None]:
    """Só as linhas que o Yahoo de fato respondeu; o resto é falha de coleta registrada.

    Linha sem nenhum dado (``sem_dados``) nunca entra na atualização: valem os fundamentos
    gravados. Sem nenhuma linha útil, a atualização inteira é descartada (``None``)."""
    from .yahoo import linhas_sem_dados

    if new is None or new.empty:
        return None, None
    vazias = linhas_sem_dados(new)
    n_vazias, total = int(vazias.sum()), len(new)
    if n_vazias == 0:
        return new, None
    if n_vazias == total:
        return None, (f"fundamentos: Yahoo sem dados para nenhuma das {total} linhas (falha de "
                      "coleta); valem os fundamentos gravados")
    gravadas = 0 if old is None else int(new.index[vazias].isin(old.index).sum())
    return new.loc[~vazias], (f"fundamentos (parcial): {n_vazias} de {total} linha(s) sem "
                              f"resposta do Yahoo; {gravadas} delas mantêm os fundamentos "
                              "gravados")


def _si_sem_dados(si: pd.DataFrame) -> pd.Series:
    """Linhas de short interest sem a medida (ações vendidas e % do float ausentes)."""
    cols = [c for c in ("shares_short", "short_pct_float") if c in si.columns]
    if not cols:
        from .yahoo import linhas_sem_dados

        return linhas_sem_dados(si)
    return si[cols].apply(pd.to_numeric, errors="coerce").isna().all(axis=1)


def _sem_perder_dados(old: pd.DataFrame, new: pd.DataFrame, *,
                      short_interest: bool = False) -> pd.DataFrame:
    """Linhas novas que não apagam dado gravado: linha sem nenhum dado, ou sem valor de mercado
    quando a gravada o tem, fica de fora (vale a gravada). Ausente nunca substitui um valor."""
    from .yahoo import linhas_sem_dados

    drop = _si_sem_dados(new) if short_interest else linhas_sem_dados(new)
    if "market_cap" in new.columns and "market_cap" in old.columns:
        mc_novo = pd.to_numeric(new["market_cap"], errors="coerce")
        mc_old = pd.to_numeric(old["market_cap"], errors="coerce")
        mc_old = mc_old[~mc_old.index.duplicated(keep="last")].reindex(new.index)
        drop = drop | (mc_novo.isna() & mc_old.notna())
    drop = drop & new.index.isin(old.index)
    return new.loc[~drop.to_numpy(dtype=bool)]


def save_slow_refresh(refresh: SlowRefresh, out_dir: Path) -> dict[str, str]:
    """Grava cada componente disponível e devolve ``{arquivo: sha256}`` (recusa sobrescrever)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for key, name in FILES.items():
        path = out_dir / name
        value = getattr(refresh, key)
        if value is None:
            continue
        if path.exists():
            raise FileExistsError(f"Arquivo de atualização já existe: {path}")
        if key == "news":
            with path.open("w", encoding="utf-8") as f:
                for n in value:
                    f.write(json.dumps(n.model_dump(mode="json"), ensure_ascii=False,
                                       sort_keys=True) + "\n")
        else:
            df = value.copy()
            df.index = df.index.astype(str)
            df.sort_index().to_parquet(path)
        hashes[name] = sha256_file(path)
    (out_dir / "failures.json").write_text(json.dumps(refresh.failures, ensure_ascii=False,
                                                      indent=2), encoding="utf-8")
    return hashes


def load_slow_refresh(out_dir: Path, expected: dict[str, str]) -> SlowRefresh:
    out_dir = Path(out_dir)
    vals: dict[str, object] = {}
    for key, name in FILES.items():
        path = out_dir / name
        if name not in expected:
            vals[key] = None
            continue
        if sha256_file(path) != expected[name]:
            raise ValueError(f"Hash divergente na atualização ao vivo: {path}")
        if key == "news":
            vals[key] = [NewsItem.model_validate_json(line) for line in
                         path.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            vals[key] = pd.read_parquet(path)
    failures_path = out_dir / "failures.json"
    failures = json.loads(failures_path.read_text(encoding="utf-8")) if failures_path.exists() else []
    return SlowRefresh(vals["fundamentals"], vals["short_interest"], vals["lending"],  # type: ignore[arg-type]
                       vals["news"], failures)  # type: ignore[arg-type]


def overlay_slow_refresh(md: MarketData, refresh: SlowRefresh, hashes: dict[str, str],
                         captured_at: datetime, rel_dir: str) -> MarketData:
    """Substitui os retratos lentos pelos mais recentes (mantendo os anteriores onde faltar).

    Fundamentos: linha nova sem dado (ou sem valor de mercado onde o gravado o tem) nunca
    sobrescreve a gravada — falha de coleta não apaga o retrato anterior (ver
    :func:`_sem_perder_dados`)."""

    def merged(old: pd.DataFrame, new: pd.DataFrame | None, *, protege: bool = False,
               short_interest: bool = False) -> pd.DataFrame:
        if new is None or new.empty:
            return old
        if old is None or old.empty:
            return new
        if protege:
            new = _sem_perder_dados(old, new, short_interest=short_interest)
        keep = old.loc[~old.index.isin(new.index)]
        return pd.concat([new, keep]).sort_index()

    files = list(md.manifest.files) + [
        SnapshotFile(path=f"{rel_dir}/{name}", sha256=h, description="Atualização ao vivo")
        for name, h in sorted(hashes.items())]
    limitations = list(md.manifest.limitations) + [
        f"Dados lentos atualizados no momento da análise ({captured_at.isoformat()}): "
        + ", ".join(sorted(hashes)) + "."] + [f"Falha na atualização: {f}" for f in refresh.failures]
    manifest = md.manifest.model_copy(update={"files": files, "limitations": limitations})
    news = tuple(refresh.news) if refresh.news is not None else md.news
    return replace(md, manifest=manifest,
                   fundamentals=merged(md.fundamentals, refresh.fundamentals, protege=True),
                   short_interest=merged(md.short_interest, refresh.short_interest,
                                         protege=True, short_interest=True),
                   lending=merged(md.lending, refresh.lending), news=news)
