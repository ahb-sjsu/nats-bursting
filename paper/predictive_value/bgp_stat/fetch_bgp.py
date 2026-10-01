"""Fetch RIS rrc06 update files for the registered window and count
announcement+withdrawal elements per UTC minute (PROTOCOL-BGP-STATIONARITY.md).
Streams files (download, parse, delete). Runs with /usr/bin/python3 (bgpkit)."""
import json, os, time, urllib.request, calendar, tempfile
from multiprocessing import Pool
import numpy as np

OUT = "/archive/infocom_battery/bgp_stat"
COLL = "rrc06"
T0 = calendar.timegm((2026, 9, 1, 0, 0, 0))   # 1788220800
NMIN = 10080


def name(ts):
    g = time.gmtime(ts)
    return (f"{g.tm_year}.{g.tm_mon:02d}", f"updates.{g.tm_year}{g.tm_mon:02d}{g.tm_mday:02d}."
            f"{g.tm_hour:02d}{g.tm_min:02d}.gz")


def work(ts):
    import bgpkit
    mon, fn = name(ts)
    url = f"https://data.ris.ripe.net/{COLL}/{mon}/{fn}"
    fd, path = tempfile.mkstemp(suffix=".gz", dir="/tmp"); os.close(fd)
    try:
        for att in range(3):
            try:
                urllib.request.urlretrieve(url, path); break
            except Exception as e:
                err = repr(e); time.sleep(5)
        else:
            return ts, fn, None, f"download: {err}"
        cnt = {}
        try:
            for e in bgpkit.Parser(url=path):
                if e.elem_type in ("A", "W"):
                    m = int((e.timestamp - T0) // 60)
                    if 0 <= m < NMIN:
                        cnt[m] = cnt.get(m, 0) + 1
        except Exception as e:
            return ts, fn, None, f"parse: {e!r}"
        return ts, fn, cnt, os.path.getsize(path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def main():
    stamps = [T0 - 300 + 300 * i for i in range(2016 + 2)]   # incl. neighbours
    counts = np.zeros(NMIN, dtype=np.int64)
    log = []
    with Pool(6) as pool:
        for i, (ts, fn, cnt, info) in enumerate(pool.imap_unordered(work, stamps)):
            nominal = 0 <= (ts - T0) // 300 < 2016
            ok = cnt is not None
            if ok:
                for m, c in cnt.items():
                    counts[m] += c
            log.append(dict(file=fn, ts=ts, nominal=bool(nominal), ok=ok,
                            info=info if not ok else int(info)))
            if i % 100 == 0:
                print(i, fn, ok, flush=True)
    observed = np.ones(NMIN, dtype=bool)
    for r in log:
        if r["nominal"] and not r["ok"]:
            k = (r["ts"] - T0) // 60
            observed[k:k + 5] = False
    np.save(f"{OUT}/bgp_counts_per_minute.npy", counts)
    np.save(f"{OUT}/bgp_observed_mask.npy", observed)
    with open(f"{OUT}/bgp_counts_per_minute.csv", "w") as f:
        f.write("minute_index,utc,count,observed\n")
        for m in range(NMIN):
            f.write(f"{m},{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(T0 + 60 * m))},"
                    f"{counts[m]},{int(observed[m])}\n")
    log.sort(key=lambda r: r["ts"])
    miss = [r for r in log if r["nominal"] and not r["ok"]]
    summ = dict(collector=COLL, n_nominal=2016, n_missing=len(miss),
                frac_missing=len(miss) / 2016,
                neighbours=[r for r in log if not r["nominal"]],
                missing=miss, total_elems=int(counts[observed].sum()),
                bytes=int(sum(r["info"] for r in log if r["ok"])))
    json.dump(dict(summary=summ, files=log), open(f"{OUT}/bgp_fetch_log.json", "w"), indent=1)
    print("FETCH_DONE", json.dumps({k: v for k, v in summ.items() if k not in ("missing", "neighbours")}), flush=True)


if __name__ == "__main__":
    main()
