#!/bin/bash
set -e
cd /archive/infocom_battery/bgp_stat
PY=/home/claude/env/bin/python3
echo "== start $(date -u)"
$PY bgp_summary.py
$PY bgp_v4.py
$PY bgp_v5.py
$PY bgp_v5b.py
$PY bgp_v5c.py
$PY stationarity_blocks.py
echo "== ALL_DONE $(date -u)"
