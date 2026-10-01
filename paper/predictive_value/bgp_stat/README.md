# BGP series and calendar-block stationarity check

Registered in `../PROTOCOL-BGP-STATIONARITY.md` (committed before any BGP data was fetched), then run on the battery's code path.

- `fetch_bgp.py`: per-minute counts of announced and withdrawn prefixes (bgpkit elements) at RIPE RIS collector rrc06, 2026-09-01 to 2026-09-08 UTC. All 2,016 five-minute files fetched, none missing (`bgp_fetch_log.json`, `bgp_counts_per_minute.csv`).
- `bgp_series.py`: the binary state (minute count above the week's median).
- `bgp_v4.py`, `bgp_v5.py`, `bgp_v5b.py`, `bgp_v5c.py`: copies of the battery drivers for the BGP series; outputs `bgp_v*.json`.
- `stationarity_blocks.py`: the three-block analysis for Seismic ANMO, GOES X-ray, magnetometer, protons and BGP; output `stationarity.json`.
- `repro_v5c_existing.json`: the repaired selection-aware bootstrap reproduces `../battery_v5c.json` exactly on all nine original series.

The paths inside the scripts point at the run directory on the machine that executed them.
