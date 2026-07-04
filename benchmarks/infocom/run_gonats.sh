#!/bin/bash
# Orchestrate the Go-driven NATS warm-pool throughput run:
#   nats-server (:4300) + W Python GPU workers + the Go driver.
# Kills by tracked PID (no pkill -f self-matches). Usage: run_gonats.sh [W] [NREQ] [CONC]
W=${1:-4}; NREQ=${2:-600}; CONC=${3:-64}
cd /home/claude/e9
for task in embed tiny; do
  /home/claude/bin/nats-server -p 4300 >/tmp/e9/ns.log 2>&1 &
  NS=$!
  sleep 1
  /tmp/natsbench/natsbench --url nats://127.0.0.1:4300 --workers "$W" --task "$task" \
      --batch 64 --nreq "$NREQ" --concurrency "$CONC" \
      --out "/tmp/e9/gonats_${task}_w${W}.json" &
  GO=$!
  sleep 1
  WPIDS=""
  for i in $(seq 1 "$W"); do
    /tmp/benchvenv/bin/python bench_nats_pool.py --role worker \
        --url nats://127.0.0.1:4300 --subj task --ready ready >/dev/null 2>&1 &
    WPIDS="$WPIDS $!"
  done
  wait "$GO"
  kill $WPIDS 2>/dev/null
  kill "$NS" 2>/dev/null
  sleep 1
done
