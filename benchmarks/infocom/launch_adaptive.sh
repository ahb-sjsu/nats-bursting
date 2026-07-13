#!/usr/bin/env bash
# Launch the E9 regime-adaptive controller campaign ON ATLAS.
#
# PREPARED, not auto-run. This is a GPU-heavy job. It must not collide with the
# resident Atlas AI stack (llama-server, artemis-avatar/primer, ...). It NEVER
# kills, reboots, or otherwise touches other processes -- guest tasks are pinned
# to the GPUs named in E9_GPUS and the harness excludes pre-existing compute PIDs
# from its competitor census (they are monitored only as a contamination check).
#
#   default (no --go): preflight only -- prints GPU state and exits.
#   --go             : actually launch the campaign under nohup.
#
# Env knobs (forwarded to e9_campaign.py):
#   E9_GPUS   slot order for guest tasks, e.g. "0,1" if GPU0 is the free one (default "1,0").
#   E9_TRIALS new|markov|adaptive|all  (default "new": adaptive rows + markov tau_c sweep).
set -euo pipefail

DIR=/home/claude/e9
PY=/home/claude/env/bin/python3
export E9_GPUS="${E9_GPUS:-1,0}"
export E9_TRIALS="${E9_TRIALS:-new}"

echo "=== GPU state (preflight) ==="
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,temperature.gpu \
           --format=csv,noheader || { echo "nvidia-smi failed"; exit 1; }
echo
echo "=== resident compute apps (Atlas AI / ego stack -- will NOT be disturbed) ==="
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader || true
echo
echo "guest GPU slot order  E9_GPUS=$E9_GPUS   trial set  E9_TRIALS=$E9_TRIALS"

# Advisory busy-check on the first (primary) guest GPU slot.
primary="${E9_GPUS%%,*}"
util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i "$primary" 2>/dev/null | tr -d ' ' || echo 0)
if [[ "${util:-0}" =~ ^[0-9]+$ ]] && (( util > 30 )); then
  echo "!! WARNING: primary guest GPU $primary is ${util}% busy -- results may be"
  echo "!! contaminated by the Atlas AI stack. Prefer a free GPU via E9_GPUS, or wait."
fi

if [[ "${1:-}" != "--go" ]]; then
  cat <<EOF

Preflight only -- nothing launched. Review the GPU state above.
If a target GPU is busy with the Atlas AI stack, override the slot order, e.g.:

    E9_GPUS="0,1" bash $DIR/launch_adaptive.sh --go

To launch for real, re-run with --go. Results -> /tmp/e9/run/ ,
progress -> /tmp/e9/campaign.log . Pull with:  python pull_e9.py
EOF
  exit 0
fi

echo
echo "=== launching campaign under nohup (E9_TRIALS=$E9_TRIALS, E9_GPUS=$E9_GPUS) ==="
cd "$DIR"
nohup env E9_GPUS="$E9_GPUS" E9_TRIALS="$E9_TRIALS" "$PY" e9_campaign.py \
      > /tmp/e9/campaign.log 2>&1 &
PID=$!
echo "campaign PID=$PID   log=/tmp/e9/campaign.log"
echo "watch:  tail -f /tmp/e9/campaign.log"
echo "pull :  python pull_e9.py   (from the benchmarks/infocom checkout)"
