# nats-bursting → IEEE INFOCOM 2027 — outline, abstract, model, experiments

Target: INFOCOM 2027 (Honolulu, May). Submission window ~July 2026 (abstract ~Jul 24,
full ~Jul 31 — confirm on the CFP). Top-tier networking venue; rewards
formulation + analysis + measurement, not "we built a tool". Reframe nats-bursting from an
orchestration system into a networking / distributed-systems contribution.

## Title (primary + alternates)
- **Polite Bursting: Feedback-Controlled Admission for AI Workloads over a Federated Messaging Fabric on Shared Clusters**
- Being a Good Guest: Adaptive Admission Control for Bursting ML Jobs onto Multi-Tenant Research Clusters
- Politeness as a Control Problem: Goodput-Maximizing, Policy-Compliant Bursting over NATS Leaf Federation

## Abstract (~200 words)
Research and AI teams increasingly burst bursty GPU/ML batch workloads onto shared,
multi-tenant clusters (e.g., the National Research Platform) where they are *guests*: bound by
fair-use policy — pod caps, sustained-utilization floors, ignored-resource ranges — and
reachable only over constrained, partially-connected WAN paths. Naive submission violates
policy (risking throttling or bans) and wastes the host's capacity; static rate-limiting wastes
the guest's throughput. We argue that "being a good guest" is fundamentally a control problem,
and present nats-bursting, a container-native bursting fabric that maximizes useful goodput
while provably respecting host policy. nats-bursting contributes (i) a feedback admission /
back-off controller modeled as an AIMD loop with a probe-driven estimator, analyzed for
stability and a bounded policy-violation probability; (ii) a federated NATS leaf-node messaging
plane spanning home and cluster whose tradeoffs — JetStream non-federation, asymmetric subject
interest, durability, single-port WAN traversal — we characterize through measurement; and (iii)
bandwidth- and resource-efficient transport via random-rotation quantization and OOM-/thermal-
safe GPU batch right-sizing, the latter a Kalman-filtered predictive controller. On NRP Nautilus
with a workstation-class home node, nats-bursting sustains [94%] GPU utilization within policy,
cuts burst-completion time by [X x] over naive and static baselines, and holds the measured
policy-violation rate below [eps]. The system and a reproducible artifact are open source.

## Section outline (~13 pp)
1. Introduction — polite-bursting problem; why naive & static fail; thesis (politeness = control); contributions; artifact.
2. Background & Motivating Measurement — shared-cluster policy (pod caps, >40% sustained-util, ignored cpu=1/mem=2Gi, exit-0/TTL); WAN reality (single port :4222, Tailscale/duckdns); what naive submission does.
3. System Model & Problem Formulation — see `infocom_model.tex` (System Model).
4. The Politeness Controller — macro AIMD admission + micro Kalman-PID thermal; see `infocom_model.tex` (Controller).
5. Federated Messaging Fabric — NATS leaf nodes; JetStream non-federation, asymmetric subject interest, durable flag, result-webhook; core-NATS vs JetStream mapping.
6. Transport & Resource Subsystems — turboquant-pro (random-rotation, per-channel keys / per-token values); batch-probe (OOM-safe sizing + the thermal controller of the micro tier).
7. Implementation — Go control plane (modules/LOC), Python client, Job/pool pod shapes, gate flag, artifact.
8. Evaluation — testbed + E1–E8 (below); headline = compliance↔goodput Pareto + federation characterization.
9. Related Work — cloud/HPC bursting; serverless/function fabrics (funcX, Parsl, Ray, Dask); pub/sub (NATS); admission/congestion control & AIMD; multi-tenant scheduling; communication-efficient ML.
10. Discussion & Limitations.
11. Conclusion.

## Two-tier control framing
- **Macro / cluster tier** (Sec. Controller): admission AIMD over the federation — don't over-admit.
- **Micro / node tier**: edge-node Kalman-estimated PID thermal control — don't cook / waste shared hardware (energy/thermal citizenship). Honest scope: governs the home/edge node in the hybrid edge→cluster path.

## Provability verdict (honest)
The over-admission bound (Prop. 2) is provable under the stated assumptions but is *applied AIMD*,
not new theory. INFOCOM novelty must come from: (1) the two-sided politeness formulation;
(2) the explicit detection-delay D term bridging the prober's measured behavior to the
compliance guarantee (D is measured in E7); (3) the federated-fabric measurement; (4) the
two-tier control (Kalman thermal). A theorem alone will not carry it.

## Experiment spec (Sec. 5 / 8)
Testbed: NRP Nautilus (A10x8) ↔ GV100 workstation home node, over {LAN, Tailscale, duckdns:4222}.
Factor grid: transport {core-NATS, JetStream-durable, JetStream-nondurable} x path {LAN, Tailscale,
duckdns:4222} x in-flight pods {1, K/2, K} x payload {raw, turboquant}.

| # | Experiment | Knobs | Output |
|---|---|---|---|
| E1 | Control RTT & throughput | transport x path | submit→ack→result p50/95/99; msgs/s |
| E2 | Single-port (:4222) tax | duckdns:4222 vs Tailscale | added latency / throughput loss |
| E3 | Durability cost | JetStream durable/non vs core | per-msg overhead + recovery-after-restart |
| E4 | Asymmetric subject interest | symmetric vs asymmetric | delivery/loss/latency → motivates result-webhook |
| E5 | Control-plane scaling | w = 1..K, rate up | latency/throughput vs in-flight; Go plane CPU/mem |
| E6 | Partition resilience | Tailscale flap / leaf drop | reconnect time; msgs preserved (JS vs core); AIMD backoff response |
| E7 | Detection delay D | measure prober latency | empirical D → plug into Prop. 2 |
| E8 | End-to-end + baselines | full stack | cold-start, submit→first-result, burst time, violation rate, GPU util vs naive / static-rate / [funcX] |

Closing loop: E7 measures D → Prop. 2 predicts achievable violation rate for chosen (alpha,beta) →
E8 shows realized rate matches and that nats-bursting dominates baselines on the goodput–compliance frontier.

## Critical path (honest)
The long pole is **running E1–E8 on Nautilus/Atlas before the deadline**, not the writing. The
existing system, NATS federation, the three PyPI packages, GPU-util numbers, and the SC26/CANOPIE
prose are reusable. The two pieces that turn it from a systems paper into INFOCOM: the Sec. 3–4
model + analysis (with measured D) and the Sec. 5/8 federation measurement study.
