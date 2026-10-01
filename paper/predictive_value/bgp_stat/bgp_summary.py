"""Provenance summary of the registered BGP series."""
import json, sys
sys.path.insert(0, "/archive/infocom_battery/bgp_stat")
import numpy as np
import bgp_series
x, obs, med, cnt = bgp_series.full_state()
S = bgp_series.load_bgp()
fl = json.load(open("/archive/infocom_battery/bgp_stat/bgp_fetch_log.json"))["summary"]
out = dict(n_minutes=int(len(x)), n_observed=int(obs.sum()), n_runs=len(S),
           run_lengths=[len(r) for r in S], median_per_minute=med,
           total_elems_observed=int(cnt[obs].sum()), mean_per_minute=float(cnt[obs].mean()),
           max_per_minute=int(cnt[obs].max()), min_per_minute=int(cnt[obs].min()),
           ties_at_median=int(np.sum(cnt[obs] == med)), pi_hat=float(x[obs].mean()),
           fetch=dict((k, v) for k, v in fl.items() if k != "neighbours"))
json.dump(out, open("/archive/infocom_battery/bgp_stat/bgp_summary.json", "w"), indent=1)
np.save("/archive/infocom_battery/bgp_stat/bgp_state_minute.npy", np.where(obs, x, -1).astype(np.int8))
print(json.dumps({k: v for k, v in out.items() if k != "run_lengths"}), flush=True)
