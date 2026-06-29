# E1/E2 results — control RTT & throughput by path

First testbed run of the INFOCOM harness (core-NATS request→reply, 256 B payload,
n=500, concurrency 16). Driver on the home node; echo responder co-located with
Atlas's `nats-server` (`100.68.134.21:4222`), so the tailscale figure is one clean
WAN round-trip. Raw JSON in `out/`.

| transport | path | RTT p50 / p95 / p99 (ms) | throughput (msg/s) |
|---|---|---|---|
| core | local (Atlas loopback) | 0.84 / 1.09 / 1.14 | 6855 |
| core | tailscale (home↔Atlas) | 139.6 / 485.4 / 694.9 | 40 |

**Finding.** The federated control path over Tailscale inflates median control-RTT
by ~**165×** (0.84 → 140 ms) and collapses closed-loop throughput by ~**170×**
(6855 → 40 msg/s) versus co-located — the WAN RTT dominates, and a closed-loop
controller is RTT-bound. This is the quantitative motivation for the §4 admission
controller being epoch-paced rather than per-message synchronous.

## Honest caveats (this is a first run, not the final table)
- **duckdns `:4222` was unreachable this session** (PAT not forwarding), so the
  single-port-tax comparison (E2) is **pending** — rerun when the PAT forward is up.
- **Single run + WAN variance.** A prior tailscale run measured p50 **71 ms** vs
  **140 ms** here; Tailscale RTT is jittery. The paper needs **multiple seeds**
  (and ideally off-peak repeats) with confidence intervals.
- The tailscale run had **>1 echo responder** transiently active (a deploy artifact),
  adding minor duplicate-reply traffic; rerun with a single responder for the final
  numbers. The contrast (orders of magnitude) is robust to this.
- `transport` is `core` only: RTT/throughput is request→reply, which is core-NATS
  regardless of JetStream; the durability/transport axis is **E3** (publish-ack), not E1.

## Reproduce
```bash
# far side (Atlas), one responder:
python responder.py --url nats://localhost:4222 --subject infocom.echo
# local baseline (on Atlas): run.py -e E1 --url nats://localhost:4222 --path local ...
# tailscale (home):
python run.py -e E1 --url nats://100.68.134.21:4222 --path tailscale --transport core --n 500 --concurrency 16 --out out/E1_tailscale_core.json
python run.py --mode tables --glob 'out/*.json'
```
