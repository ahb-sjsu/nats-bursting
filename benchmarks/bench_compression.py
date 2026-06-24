#!/usr/bin/env python3
"""Tier-1 benchmark (local, CPU-only): turboquant-pro compression for the NATS burst path.

When you burst AI work to a remote cluster, the *payloads* — embeddings, KV-cache pages,
feature tensors — ride the NATS bus. turboquant-pro's NATS codec compresses them. This
measures, with no cluster required:

  - bytes on the wire: raw float32 vs compressed, and the ratio
  - codec cost: encode / decode latency
  - quality: reconstruction cosine (compression isn't free)
  - transfer time saved at representative link bandwidths (analytic)

Run: ``python benchmarks/bench_compression.py`` (needs ``turboquant-pro`` + ``numpy``).
"""

import argparse
import json
import time

import numpy as np

from turboquant_pro.nats_codec import TurboQuantNATSCodec


def _cos(a, b):
    a = a.ravel()
    b = b.ravel()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def bench(dim, bits, n, rng):
    emb = rng.standard_normal((n, dim)).astype(np.float32)
    codec = TurboQuantNATSCodec(dim=dim, bits=bits)
    t0 = time.perf_counter()
    payloads = codec.encode_batch(emb)
    enc_ms = (time.perf_counter() - t0) * 1e3
    t0 = time.perf_counter()
    recon = codec.decode_batch(payloads)
    dec_ms = (time.perf_counter() - t0) * 1e3
    raw = n * dim * 4
    comp = sum(len(p) for p in payloads)
    cos = float(np.mean([_cos(emb[i], recon[i]) for i in range(n)]))
    return {
        "dim": dim,
        "bits": bits,
        "n": n,
        "raw_bytes": raw,
        "compressed_bytes": comp,
        "ratio": raw / comp,
        "encode_ms": enc_ms,
        "decode_ms": dec_ms,
        "mean_cosine": cos,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dims", type=int, nargs="+", default=[384, 768, 1024])
    ap.add_argument("--bits", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--batch", type=int, nargs="+", default=[1, 32, 256])
    ap.add_argument("--bandwidths-mbps", type=float, nargs="+", default=[100.0, 1000.0])
    ap.add_argument("--out", default="benchmarks/results_compression.json")
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    rows = []
    print(
        f"{'dim':>5} {'bits':>4} {'n':>4} {'raw KB':>8} {'comp KB':>8} {'ratio':>6} "
        f"{'enc ms':>7} {'dec ms':>7} {'cosine':>7}"
    )
    for dim in a.dims:
        for bits in a.bits:
            for n in a.batch:
                r = bench(dim, bits, n, rng)
                rows.append(r)
                print(
                    f"{dim:>5} {bits:>4} {n:>4} {r['raw_bytes']/1024:>8.1f} "
                    f"{r['compressed_bytes']/1024:>8.1f} {r['ratio']:>5.1f}x "
                    f"{r['encode_ms']:>7.2f} {r['decode_ms']:>7.2f} {r['mean_cosine']:>7.3f}"
                )

    # Analytic transfer time on the wire (payload only), per batch of 256 at dim 1024
    print("\nTransfer time for a 256x1024 fp32 batch (payload only):")
    big = next(r for r in rows if r["dim"] == 1024 and r["bits"] == 3 and r["n"] == 256)
    for bw in a.bandwidths_mbps:
        bps = bw * 1e6 / 8
        raw_ms = big["raw_bytes"] / bps * 1e3
        comp_ms = big["compressed_bytes"] / bps * 1e3
        print(
            f"  @ {bw:>6.0f} Mbps: raw {raw_ms:7.2f} ms -> compressed {comp_ms:6.2f} ms "
            f"(+{big['encode_ms']:.2f} ms encode) = {raw_ms - comp_ms - big['encode_ms']:+.2f} ms net"
        )

    json.dump(rows, open(a.out, "w"), indent=2)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
