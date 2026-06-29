# INFOCOM E1–E8 measurement harness

Measurement driver for the nats-bursting INFOCOM paper (see
`paper/infocom_outline.md`). Characterizes the federated NATS control plane and
validates the §4 admission model on the real testbed.

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
