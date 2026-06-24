#!/usr/bin/env python3
"""Generate the paper figures from the committed benchmark result JSONs.

Reads benchmarks/results_*.json and writes PNG+PDF figures here. Run:
``python paper/figures/make_figures.py`` (needs matplotlib).
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.normpath(os.path.join(HERE, "..", "..", "benchmarks"))


def load(name):
    return json.load(open(os.path.join(B, name)))


# Fig 1 — Tier-2 real-hop crossover (speedup vs payload)
rh = load("results_transport_realhop.json")["results"]
kb = [r["raw_kb"] for r in rh]
sp = [r["speedup"] for r in rh]
plt.figure(figsize=(5, 3.2))
plt.plot(kb, sp, "o-", color="C0")
for x, y in zip(kb, sp):
    plt.annotate(f"{y}x", (x, y), textcoords="offset points", xytext=(6, 4))
plt.xscale("log")
plt.xlabel("raw payload (KB, log scale)")
plt.ylabel("round-trip speedup (×)")
plt.title("Tier 2: compression speedup vs payload\n(real ~2 Mbps network hop)")
plt.axhline(1, color="gray", ls=":", lw=0.8)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(HERE, "fig_tier2_crossover.png"), dpi=150)
plt.savefig(os.path.join(HERE, "fig_tier2_crossover.pdf"))
plt.close()

# Fig 2 — Tier-3 warm-pool scaling (throughput + latency vs workers)
pool = load("results_cluster_pool.json")["results"]
w = [r["workers"] for r in pool]
thr = [r["throughput_per_s"] for r in pool]
p50 = [r["p50_ms"] for r in pool]
fig, ax1 = plt.subplots(figsize=(5, 3.2))
ax1.plot(w, thr, "s-", color="C1", label="throughput")
ax1.axhline(955, color="C1", ls=":", lw=0.8)
ax1.annotate("Little's-law ceiling (64/RTT)", (w[0], 955),
             color="C1", fontsize=7, va="bottom")
ax1.set_xlabel("worker pods")
ax1.set_ylabel("throughput (msg/s)", color="C1")
ax1.set_xticks(w)
ax2 = ax1.twinx()
ax2.plot(w, p50, "^--", color="C2", label="p50 latency")
ax2.set_ylabel("p50 latency (ms)", color="C2")
plt.title("Tier 3: warm-pool throughput + latency vs workers")
fig.tight_layout()
plt.savefig(os.path.join(HERE, "fig_tier3_scaling.png"), dpi=150)
plt.savefig(os.path.join(HERE, "fig_tier3_scaling.pdf"))
plt.close()

# Fig 3 — Tier-1 ratio + fidelity (random vs real embeddings)
cr = load("results_compression_real.json")["rows"]
bits = [r["bits"] for r in cr]
ratio = [r["random_ratio"] for r in cr]
cosr = [r["random_cos"] for r in cr]
cose = [r["real_cos"] for r in cr]
fig, ax1 = plt.subplots(figsize=(5, 3.2))
ax1.plot(bits, ratio, "o-", color="C0", label="ratio")
ax1.set_xlabel("bits per coordinate")
ax1.set_ylabel("compression ratio (×)", color="C0")
ax1.set_xticks(bits)
ax2 = ax1.twinx()
ax2.plot(bits, cosr, "s--", color="C3", label="cosine (random)")
ax2.plot(bits, cose, "x:", color="C2", label="cosine (real bge)")
ax2.set_ylabel("reconstruction cosine", color="C3")
ax2.legend(fontsize=7, loc="lower right")
plt.title("Tier 1: ratio + fidelity\n(random ≈ real → distribution-agnostic)")
fig.tight_layout()
plt.savefig(os.path.join(HERE, "fig_tier1_compression.png"), dpi=150)
plt.savefig(os.path.join(HERE, "fig_tier1_compression.pdf"))
plt.close()

print("wrote 3 figures (png+pdf) to", HERE)
