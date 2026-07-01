# INFOCOM E1–E9 measurement harness

Measurement driver for the nats-bursting INFOCOM paper (see
`paper/infocom_outline.md`). Characterizes the federated NATS control plane and
validates the §4 admission model on the real testbed.

## Results (headline)
Full data + honest scope in [`RESULTS.md`](RESULTS.md) (E1–E7),
[`RESULTS_E8.md`](RESULTS_E8.md) (admission, abundance), and
[`RESULTS_E9.md`](RESULTS_E9.md) (admission under real contention); pre-registration
in [`E8_PREREG.md`](E8_PREREG.md) and [`E9_PREREG.md`](E9_PREREG.md).

- **E1 federation path:** local RTT p50 0.84 ms / 6855 msg/s → Tailscale (1 WAN hop)
  76 ms / 188±28 msg/s — the control path is RTT-bound (motivates epoch-paced admission).
- **E3 durability:** JetStream file vs. memory publish-ack are within noise over the WAN.
- **E5 scaling:** throughput 11→283 msg/s for window 1→32 (sub-linear, RTT-bound).
- **E7 detection delay D:** per-probe 27 ms; end-to-end 2.46 s (CUDA cold-start dominated)
  — a first-order term in the Prop. 2 bound.
- **E8 admission control — abundance (goodput vs. politeness):** on a controlled testbed
  with a *self-imposed* budget, AIMD holds the budget (over-budget ρ = 0) at **1.72×
  (GPU, C=2)** and **3.18× (CPU, C=8)** a static baseline's goodput, and matches a greedy
  baseline without over-admitting; the greedy baseline buys throughput only by
  over-admitting (ρ = 0.54 / 0.95). Figures: `../../paper/figures/pareto_{gpu,cpu}.pdf`.
- **E9 admission control — real contention (the scarcity regime):** a live competing
  tenant on 2×GV100 makes capacity scarce (a(t) = C − c(t), measured by the prober).
  Under **structured** load AIMD is the polite-efficient *knee* — **1.41× static's
  goodput, 4× lower over-admission than greedy**, sparing the neighbour (**76% vs 62%**
  throughput kept). Under **memoryless** load AIMD **breaks even** with static and
  over-admits more — a pre-registered **null** (capacity varies faster than the detection
  delay D). naive is impolite in both (ρ = 0.64–0.85, steals ~38%). 4 seeds,
  randomized-interleaved, **27 trials, 0 contaminated**. Figures:
  `../../paper/figures/pareto_contended_{square,poisson}.pdf`, `e9_competitor_harm.pdf`.

Honest record: the system path is verified end-to-end on NRP; in-situ NRP goodput was
dominated by exogenous scheduling and cold-image-pull variance (three pre-registered
nulls, not suppressed), so the contended goodput–politeness result (E9) uses controlled,
manufactured contention on a two-GPU node instead. E2 (duckdns single-port tax) and E6
(partition) remain future work.

## Install
```bash
pip install nats-py numpy        # core; psutil optional (E5 driver sampling); torch optional (E7 --induce-load)
pip install -e ../../python      # nats_bursting (for E7 prober, E8 client)
```

## Testbed paths (set `--url` / `--path` accordingly)
| path label | URL | notes |
|---|---|---|
| `lan` | `nats://atlas-nats:4222` (or LAN IP) | in-cluster / same-LAN baseline |
| `tailscale` | `nats://100.68.134.21:4222` | WAN, mesh VPN |
| `duckdns` | `nats://atlas-sjsu.duckdns.org:4222` | WAN, single PAT-forwarded `:4222` |

`--transport`: `core` | `js-durable` | `js-nondurable`.

## Topology
Run the **responder on the far side** (the cluster you burst to); run the
**driver on the home node**. The driver `--url` points at the far-side NATS over
the path under test.

```bash
# far side (cluster):
python responder.py --url nats://0.0.0.0:4222 --subject infocom.echo
```

## Experiments
```bash
# E1 — control RTT + throughput (run once per transport × path)
python run.py -e E1 --url nats://100.68.134.21:4222 --path tailscale --transport core \
    --out out/E1_tailscale_core.json

# E2 — single-port (:4222) tax = E1 on duckdns vs tailscale (compared in tables)
python run.py -e E1 --url nats://atlas-sjsu.duckdns.org:4222 --path duckdns --transport core \
    --out out/E1_duckdns_core.json

# E3 — JetStream durability cost + restart recovery
python run.py -e E3 --url $U --transport js-durable    --out out/E3_durable.json
python run.py -e E3 --url $U --transport js-nondurable --out out/E3_nondurable.json

# E4 — asymmetric subject interest (run with leaf federation configured)
python run.py -e E4 --url $U --path tailscale --out out/E4.json

# E5 — concurrency scaling
python run.py -e E5 --url $U --sweep 1,4,8,16,32,64 --out out/E5.json

# E6 — partition resilience (induce the partition during the window)
python run.py -e E6 --url $U --transport js-durable --duration 60 --out out/E6.json
#   ...then in another shell on the home node:  tailscale down; sleep 10; tailscale up

# E7 — prober detection delay D (run on a GPU node; --induce-load for full latency)
python run.py -e E7 --induce-load --out out/E7.json

# E8 — end-to-end + baselines (needs the live cluster + nats_bursting client)
python run.py -e E8 --baseline naive  --burst 64 --out out/E8_naive.json
python run.py -e E8 --baseline static --burst 64 --rate 2 --out out/E8_static.json
python run.py -e E8 --baseline aimd   --burst 64 --alpha 2 --beta 0.5 --kcap 4 --out out/E8_aimd.json

# aggregate → paper tables
python run.py --mode tables --glob 'out/*.json'
```

## The closing loop (model ↔ measurement)
**E7** measures the prober's detection delay `D`. Plug `D` into Prop. 2
(`paper/infocom_model.tex`): `ρ ≈ D·α/((1−β)·a)` predicts the achievable
over-admission rate for the chosen `(α,β)`. **E8** then shows the *realized*
violation rate matches the prediction and that `aimd` dominates `naive`/`static`
on the goodput–compliance frontier.

## Status / honesty
- **E1–E5, E7** run end-to-end against a live NATS endpoint (and a GPU node for E7).
- **E6** logs disconnect/reconnect and (for JetStream) message survival; *you*
  induce the partition during the window.
- **E8** submits via the real `nats_bursting.client.Client` and drains
  `<result_prefix><job_id>` for cold-start / first-result / completion timing;
  GPU-util + violation rate are sampled on the node by `nats_bursting.probe`. It
  requires live cluster access and a burst-worker `--image` that publishes a result.
- Results are raw measurements; nothing is synthesized.

## NRP fair-use compliance (the policy the harness must obey)
The same policy the paper models also constrains *how we run*:
- **≤4 pods/user** — E5/E8 keep concurrency ≤ `--kcap 4` (the default).
- **Utilization vs request must stay in-band** (GPU ≥40%, CPU 20–200%, RAM 20–150%):
  right-size each job's request (batch-probe) and don't over-admit (the AIMD loop).
- **No sleep jobs** — the E8 `--image` must do *real work*; a sleep-ending job gets
  the namespace banned. (The responder's `--work-ms` runs on the *responder* pod, not
  a submitted Job.)
- **Free on completion** — submitted Jobs must exit-0; rely on TTL cleanup. Run the
  long-lived `responder.py` as a **Deployment with minimal request and no GPU** so it
  never trips the utilization floor.
- **Storage** — purge harness output volumes; idle volumes are reclaimed after 6 months.

## Baselines — best-in-class comparison (`baselines.py`)
funcX/Globus Compute and Parsl have **no admission controller** — they scale workers
to demand — so the fair test is to push the *same* B-task burst through them and
record the *same externally-observable* policy metrics (peak concurrency vs cap K,
util-floor breaches, completion) with a shared `Monitor`, so they land on the **same
goodput–ρ Pareto** as the run.py E8 policies (naive/static/aimd). Hypothesis (and the
point of the paper): demand-scaling frameworks complete the burst by **violating** the
cap/floor under contention; the politeness controller does not.

```bash
# dry-run (no cluster): shows over-provisioning on a process pool
python baselines.py --backend local --burst 12 --kcap 4 --max-workers 12 --out out/bl_local.json

# Parsl  (configure a KubernetesProvider in the namespace — the marked bind point)
python baselines.py --backend parsl  --burst 64 --kcap 4 --namespace ssu-atlas-ai \
    --util-cmd 'dcgm-or-prometheus-query-printing-0..1' --out out/bl_parsl.json

# Globus Compute / funcX (endpoint whose provider launches pods in the namespace)
python baselines.py --backend globus --endpoint <ENDPOINT_ID> --burst 64 --kcap 4 \
    --namespace ssu-atlas-ai --out out/bl_globus.json
```
Honest scope: `parsl`/`globus` need their framework installed and a
namespace-launching executor/endpoint (the marked bind points), plus a `--util-cmd`
(DCGM/Prometheus) for the GPU-util side of ρ — without it only the concurrency/cap
side is reported. The `local` backend runs here and is for the dry-run only.

## Aggregation & plots (`aggregate.py`)
Consumes the run.py E8 outputs **and** the `baselines.py` outputs (multiple files per
label = repeats → mean ± 95% CI) and emits the two headline figures plus a table:
```bash
python aggregate.py --glob 'out/*.json' --eps 0.1 \
    --D <epochs from E7> --contention out/contention_square.jsonl --out-dir out/agg
# -> out/agg/{pareto.png, money.png, data.csv, SUMMARY.md}
```
- **`pareto.png`** — goodput (y) vs over-admission ρ (x) with the ρ=ε feasibility line;
  the claim succeeds iff `aimd` is alone on the upper-left frontier (high goodput, low ρ)
  while naive/parsl/globus sit high-ρ.
- **`money.png`** — for `aimd` runs, measured ρ vs the Prop. 2 prediction
  `ρ_pred = D·α/((1−β)·ā)` (ā from the contention log), with the y=x line.
- Validated on synthetic fixtures; matplotlib optional (falls back to CSV + SUMMARY.md).
- **Note:** E8 policy ρ requires running `run.py -e E8` under the shared `Monitor`
  (an `over_admission_rho` / `monitor` block in its output); until that's wired, E8
  rows show goodput/completion and ρ as "n/a (needs monitoring)".
