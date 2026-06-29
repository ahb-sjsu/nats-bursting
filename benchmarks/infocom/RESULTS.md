# INFOCOM harness — testbed results

Runs on the live testbed: driver on the home node, NATS + echo responder on Atlas
(`nats-server` at `100.68.134.21:4222`, JetStream enabled). Core-NATS request→reply,
256 B payloads. Raw JSON in `out/`.

> **Multi-seed update (authoritative for E1/E3/E5).** `out/ms/RESULTS_MULTISEED.md`
> (5 repeats, mean ± 95% CI, via `multiseed.py`) supersedes the single-run E1/E3/E5
> numbers below and corrects two single-run artifacts:
> (1) **E1 throughput** — the single-run 40 msg/s was a low outlier; 5-rep mean is
> **188 ± 28 msg/s** (consistent with E5 @ window 16 = 158 ± 68).
> (2) **E3 durability** — durable 81.4 ± 10.6 ms vs non-durable 84.0 ± 6.5 ms publish-ack
> are **statistically indistinguishable** (overlapping CIs); the WAN RTT dominates the
> storage cost, so the single-run "durable widens the tail" was noise. RTT medians and
> the E5 scaling shape both hold up under repeats.

## E1/E2 — control RTT & throughput by path
| transport | path | RTT p50 / p95 / p99 (ms) | throughput (msg/s) |
|---|---|---|---|
| core | local (Atlas loopback) | 0.84 / 1.09 / 1.14 | 6855 |
| core | tailscale (home↔Atlas, 1 WAN hop) | 139.6 / 485.4 / 694.9 | 40 |

**Finding.** The federated control path inflates median RTT ~**165×** and collapses
closed-loop throughput ~**170×** vs co-located — the WAN dominates, motivating
epoch-paced (not per-message) admission. *Caveat:* tailscale RTT is jittery (a prior
run measured p50 71 ms vs 140 ms here). **duckdns `:4222` (the E2 single-port tax) is
still pending** — PAT not forwarding this session.

## E3 — JetStream durability cost (publish→ack over tailscale, n=200)
| storage | ack p50 / p95 / p99 (ms) | survived restart |
|---|---|---|
| durable (file) | 75.2 / 364.6 / 433.6 | 100/100 |
| non-durable (memory) | 72.7 / 156.2 / 356.5 | 100/100 |

Durable (file) persistence costs little at the median but widens the tail (p95 365 vs
156 ms). *Caveat:* the recovery test simulates a **client reconnect**, not a **server
restart** — so both survive (the server kept the messages). True durability
(server-restart survival, where memory should *not* survive) needs a server bounce we
won't do on the production NATS.

## E4 — subject interest (tailscale, n=300)
Delivered **300/300** (ratio 1.000), cross-subject leak **0**, propagation latency
p50 **169 ms**. Confirms subject isolation + full delivery on a single server. *Caveat:*
this is single-server; the *asymmetric leaf-federation* interest behavior (the §5 story)
needs a two-server leaf topology not yet stood up.

## E5 — control-plane concurrency scaling (tailscale)
| in-flight window | throughput (msg/s) | p99 (ms) |
|---|---|---|
| 1 | 10 | 266 |
| 4 | 34 | 328 |
| 8 | 62 | 527 |
| 16 | 138 | 174 |
| 32 | 222 | 341 |

Throughput scales sub-linearly with the window (RTT- and contention-bound), as expected
for a WAN-bound closed loop — directly supports the AIMD window model.

## E7 — prober detection delay D (Atlas GPU node, read-only nvidia-smi)
Prober call latency (`probe_local_gpu`): p50 **32.6 ms**, p95 35.9, mean 33.1 ms (n=20),
GPUs idle (57 °C / 46 °C). This is the probe-call component of D; full detection latency
`D = poll_interval + probe_call + decision` needs `--induce-load` (a GPU burn), **deferred
for Atlas thermal safety**. Even so, D ≳ 33 ms feeds directly into Prop. 2:
`ρ ≈ D·α/((1−β)·a)`.

## Status of the remaining experiments
- **E2 (duckdns single-port tax)** — pending: PAT not forwarding `:4222` this session.
- **E6 (partition resilience)** — pending: needs a controlled tailscale/leaf partition we
  won't induce against the production link without coordination.
- **E7 full D** — pending a thermal-safe GPU-burn window on Atlas.
- **E8 (end-to-end + baselines)** — pending: submits real pods, so it needs the
  nats-bursting control plane up + an NRP namespace, and must run inside the fair-use
  policy (≤4 pods, util bands, no-sleep). Explicit go + setup required before running.
