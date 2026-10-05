import json, sys, time, warnings
from datetime import date
from pathlib import Path
warnings.simplefilter("ignore")
from cdp.config import load_config
from cdp.data.store import MarketStore
from cdp.backtest.engine import BacktestConfig, run_backtest, earliest_start
VARIANTS = {
    "A": ({"costs": {"amortization_weeks": 4}}, None),
    "B": ({}, {"residual_momentum": 0.7, "low_risk": 0.3}),
    "C": ({"costs": {"amortization_weeks": 4}}, {"residual_momentum": 0.7, "low_risk": 0.3}),
}
name = sys.argv[1]; out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
ov, sw = VARIANTS[name]
cfg = load_config()
if ov: cfg = cfg.with_overrides(ov)
md = MarketStore(Path("data/market"), cfg=cfg).load()
start = max(date(2021, 1, 4), earliest_start(md, cfg))
t0 = time.time()
kw = dict(start=start, nav=cfg.fund.inception_nav_usd, n_trials=4)
if sw: kw["signal_names"] = tuple(sw); kw["signal_weights"] = sw
res = run_backtest(md, cfg, BacktestConfig(**kw), progress=lambda d, t, m: print(f"{d}/{t} {time.time()-t0:.0f}s {m}", flush=True))
res.daily.to_csv(out / "daily.csv"); res.weekly.to_csv(out / "weekly.csv"); res.ic.to_csv(out / "ic.csv")
(out / "metrics.json").write_text(json.dumps({"variant": name, "overrides": ov, "signal_weights": sw, "metrics": res.metrics, "notes": res.notes, "provenance": res.provenance}, ensure_ascii=False, indent=2, default=str))
print("DONE", flush=True)
