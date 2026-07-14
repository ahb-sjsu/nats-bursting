#!/usr/bin/env bash
# Reversibly free BOTH GPUs on Atlas for the E9 adaptive campaign by stopping ONLY
# the GPU-holding / GPU-spawning Atlas AI units, then ALWAYS restoring them.
#
# Method (all reversible):
#   * mask atlas-watchdog.service  -> it won't restart the units we stop
#   * systemctl stop <GPU units>   -> avatars/reasoning/primer/dreaming
#   * SIGSTOP llama-server         -> the bash-launched model server (not systemd);
#                                     pauses GPU0 compute, memory preserved
# Restore = exact inverse, guaranteed by an EXIT/INT/TERM trap AND an independent
# failsafe that runs after FAILSAFE seconds even on kill -9. Only units that were
# ACTIVE before are restarted. CPU-only services (ego, nats, memory, safety,
# telemetry, rag proxy, web layer) are left untouched.
set -uo pipefail

DIR=/home/claude/e9
PY=/home/claude/env/bin/python3
STATE=/tmp/e9/suspend_state
FAILSAFE="${FAILSAFE:-5400}"          # auto-restore after 90 min no matter what
mkdir -p "$STATE" /tmp/e9/run /tmp/e9/wd

# GPU-holding or GPU-spawning units to stop (NOT the CPU-only ego/nats/web layer):
UNITS=(atlas-artemis-avatar atlas-sigma4-avatar atlas-reasoning atlas-primer atlas-dreaming)

LLAMA_PIDS=$(pgrep -x llama-server | tr '\n' ' ')
echo "[suspend] llama-server pids: ${LLAMA_PIDS:-<none>}"
echo "$LLAMA_PIDS" > "$STATE/llama_pids"

# Record which units are currently active (so restore only starts those).
: > "$STATE/was_active"
for u in "${UNITS[@]}"; do
  if systemctl is-active --quiet "$u"; then echo "$u" >> "$STATE/was_active"; fi
done
echo "[suspend] will stop (active): $(tr '\n' ' ' < "$STATE/was_active")"

restored=0
restore() {
  [ "$restored" = 1 ] && return
  restored=1
  echo "[restore] SIGCONT llama FIRST, then unmask+start watchdog + units..."
  # Resume llama before anything else so a slow/failing systemctl cannot leave it stopped.
  for p in $(cat "$STATE/llama_pids" 2>/dev/null); do kill -CONT "$p" 2>/dev/null; done
  sudo systemctl unmask atlas-watchdog.service 2>/dev/null
  sudo systemctl start  atlas-watchdog.service 2>/dev/null
  while read -r u; do [ -n "$u" ] && sudo systemctl start "$u" 2>/dev/null; done < "$STATE/was_active"
  for p in $(cat "$STATE/llama_pids" 2>/dev/null); do kill -CONT "$p" 2>/dev/null; done
  sleep 2
  echo "[restore] service + GPU state:"
  systemctl is-active atlas-watchdog.service "${UNITS[@]}" | paste -d' ' <(printf 'watchdog\n%s\n' "${UNITS[@]}") -
  nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
  echo "[restore] done."
}
trap restore EXIT INT TERM

# Failsafe: independent process restores everything after FAILSAFE s (survives kill -9).
nohup bash -c "
  sleep $FAILSAFE
  sudo systemctl unmask atlas-watchdog.service
  sudo systemctl start atlas-watchdog.service
  while read -r u; do sudo systemctl start \$u; done < $STATE/was_active
  for p in \$(cat $STATE/llama_pids); do kill -CONT \$p; done
" >/dev/null 2>&1 &
echo "[suspend] failsafe restore watchdog pid=$! (fires after ${FAILSAFE}s)"

echo "[suspend] masking atlas-watchdog + stopping GPU units..."
sudo systemctl mask --now atlas-watchdog.service 2>/dev/null
while read -r u; do [ -n "$u" ] && sudo systemctl stop "$u" 2>/dev/null; done < "$STATE/was_active"
for p in $LLAMA_PIDS; do kill -STOP "$p" 2>/dev/null; done
sleep 4

echo "[suspend] GPU state after suspend:"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu --format=csv,noheader
echo "[suspend] remaining GPU compute apps (want: none but paused-llama memory):"
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader || true

echo "[run] E9 adaptive campaign (E9_TRIALS=${E9_TRIALS:-new} E9_GPUS=${E9_GPUS:-1,0} "\
"E9_BURST=${E9_BURST:-16} E9_WORK=${E9_WORK:-1000})"
cd "$DIR"
E9_GPUS="${E9_GPUS:-1,0}" E9_TRIALS="${E9_TRIALS:-new}" \
  E9_BURST="${E9_BURST:-16}" E9_WORK="${E9_WORK:-1000}" "$PY" e9_campaign.py
rc=$?
echo "[run] campaign exit rc=$rc"
# trap restore fires on EXIT
exit $rc
