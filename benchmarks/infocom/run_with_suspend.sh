#!/usr/bin/env bash
# Reversibly suspend the resident Atlas AI GPU stack, run the E9 adaptive
# campaign on the freed GPUs, then ALWAYS restore the stack.
#
#   suspend = SIGSTOP  (pauses compute; process + GPU memory are preserved)
#   restore = SIGCONT  (resumes exactly where it left off)
#
# Safety:
#   * the exact suspended PIDs are recorded in $PIDFILE (manual restore possible),
#   * an EXIT/INT/TERM trap restores on normal completion AND on error/Ctrl-C,
#   * a detached failsafe watchdog SIGCONTs everything after $FAILSAFE seconds even
#     if this script is hard-killed (kill -9, where the trap cannot fire).
# It never kills/restarts anything -- only STOP/CONT.
set -uo pipefail

DIR=/home/claude/e9
PY=/home/claude/env/bin/python3
PIDFILE=/tmp/e9/ego_pids.txt
FAILSAFE="${FAILSAFE:-7200}"           # auto-restore after 2h no matter what
mkdir -p /tmp/e9/run /tmp/e9/wd

# Record the GPU-compute PIDs currently running (none are ours yet).
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

# Failsafe: independent process that restores after FAILSAFE seconds even on kill -9.
nohup bash -c "sleep $FAILSAFE; while read -r p; do kill -CONT \$p 2>/dev/null; done < $PIDFILE" \
  >/dev/null 2>&1 &
WD=$!
echo "[suspend] failsafe watchdog pid=$WD (restores after ${FAILSAFE}s)"

echo "[suspend] SIGSTOP ego stack..."
while read -r p; do [ -n "$p" ] && kill -STOP "$p" 2>/dev/null; done < "$PIDFILE"
sleep 3
echo "[suspend] GPU state after suspend:"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu --format=csv,noheader

echo "[run] E9 adaptive campaign  (E9_TRIALS=${E9_TRIALS:-new} E9_GPUS=${E9_GPUS:-1,0} "\
"E9_BURST=${E9_BURST:-16} E9_WORK=${E9_WORK:-1000})"
cd "$DIR"
E9_GPUS="${E9_GPUS:-1,0}" E9_TRIALS="${E9_TRIALS:-new}" \
  E9_BURST="${E9_BURST:-16}" E9_WORK="${E9_WORK:-1000}" "$PY" e9_campaign.py
rc=$?
echo "[run] campaign exit rc=$rc"

kill "$WD" 2>/dev/null   # campaign done; cancel failsafe (trap restores on exit)
# trap restore fires here on EXIT
exit $rc
