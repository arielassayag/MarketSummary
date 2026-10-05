import json, sys, time, warnings
from datetime import date
from pathlib import Path
warnings.simplefilter("ignore")
from latam_ls.config import load_config
from latam_ls.data.store import MarketStore
from latam_ls.backtest.engine import BacktestConfig, run_backtest, earliest_start
cfg = load_config()
md = MarketStore(Path("data/market"), cfg=cfg).load()
start = max(date.fromisoformat(sys.argv[1]), earliest_start(md, cfg))
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
def prog(done, total, msg):
    print(f"{done}/{total} {time.time()-t0:.0f}s {msg}", flush=True)
res = run_backtest(md, cfg, BacktestConfig(start=start, nav=cfg.fund.inception_nav_usd), progress=prog)
res.daily.to_csv(out / "daily.csv"); res.weekly.to_csv(out / "weekly.csv"); res.ic.to_csv(out / "ic.csv")
(out / "metrics.json").write_text(json.dumps({"metrics": res.metrics, "notes": res.notes, "provenance": res.provenance}, ensure_ascii=False, indent=2, default=str))
print("DONE", json.dumps(res.metrics, default=str)[:3000], flush=True)
