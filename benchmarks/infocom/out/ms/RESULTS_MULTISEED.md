# E1/E3/E5 multi-seed results (reps=5, mean +/- 95% CI)

Independent temporal repeats over tailscale; n=300 (E1/E5), n=150 (E3). 95% CI is t-based across repeats.

## E1 — RTT & throughput (tailscale)

| metric | mean +/- 95% CI |
|---|---|
| RTT p50 (ms) | 76.0 +/- 12.6 |
| RTT p95 (ms) | 171.2 +/- 95.6 |
| RTT p99 (ms) | 302.4 +/- 169.7 |
| RTT mean (ms) | 91.9 +/- 23.9 |
| throughput (msg/s) | 187.9 +/- 27.9 |

## E3 — JetStream publish->ack (durable vs non-durable)

| storage | ack p50 (ms) | ack p95 (ms) | ack p99 (ms) |
|---|---|---|---|
| durable (file) | 81.4 +/- 10.6 | 198.0 +/- 79.2 | 323.6 +/- 65.7 |
| non-durable (mem) | 84.0 +/- 6.5 | 192.9 +/- 41.2 | 316.8 +/- 62.2 |

## E5 — concurrency scaling (tailscale)

| window | throughput (msg/s) | p99 (ms) |
|---|---|---|
| 1 | 11 +/- 2 | 335 +/- 161 |
| 4 | 39 +/- 12 | 538 +/- 236 |
| 8 | 83 +/- 28 | 319 +/- 346 |
| 16 | 158 +/- 68 | 275 +/- 277 |
| 32 | 283 +/- 128 | 279 +/- 204 |
