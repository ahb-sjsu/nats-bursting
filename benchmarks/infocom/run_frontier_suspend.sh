#!/usr/bin/env bash
# Reversibly suspend the resident Atlas AI GPU stack, run the E9-F matched-
# mismatch frontier campaign on the freed GPUs, then ALWAYS restore the stack.
# Same STOP/CONT + failsafe pattern as run_with_suspend.sh (never kills).
set -uo pipefail

DIR=/home/claude/e9
PY=/home/claude/env/bin/python3
PIDFILE=/tmp/e9/ego_pids_frontier.txt
FAILSAFE="${FAILSAFE:-18000}"          # auto-restore after 5h no matter what
mkdir -p /tmp/e9/frontier /tmp/e9/wd

nvidia-smi --query-compute-apps=pid --format=csv,noheader \
  | tr -d ' ' | grep -E '^[0-9]+$' | sort -u > "$PIDFILE"
echo "[suspend] ego GPU-compute PIDs: $(tr '\n' ' ' < "$PIDFILE")"

restored=0
restore() {
  [ "$restored" = 1 ] && return
  restored=1
  echo "[restore] SIGCONT ego stack..."
  while read -r p; do [ -n "$p" ] && kill -CONT "$p" 2>/dev/null; done < "$PIDFILE"
  sleep 2
  nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
  echo "[restore] done."
}
trap restore EXIT INT TERM

nohup bash -c "sleep $FAILSAFE; while read -r p; do kill -CONT \$p 2>/dev/null; done < $PIDFILE" \
  >/dev/null 2>&1 &
WD=$!
echo "[suspend] failsafe watchdog pid=$WD (restores after ${FAILSAFE}s)"

echo "[suspend] SIGSTOP ego stack..."
while read -r p; do [ -n "$p" ] && kill -STOP "$p" 2>/dev/null; done < "$PIDFILE"
sleep 3
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu --format=csv,noheader

echo "[run] E9-F frontier campaign (E9_GPUS=${E9_GPUS:-1,0})"
cd "$DIR"
E9_GPUS="${E9_GPUS:-1,0}" "$PY" e9_frontier.py
rc=$?
echo "[run] campaign exit rc=$rc"

kill "$WD" 2>/dev/null
exit $rc
