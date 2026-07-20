#!/bin/bash
# Switch the Ben gameserver (engine) to a different bidding-system config.
# Kills any running gameserver, starts one with the given config, waits for
# port 4443, then records the active system name in ~/ben/.current_system.
#
# Usage: ./switch_gameserver.sh <config-relative-path> <system-key>
#   e.g. ./switch_gameserver.sh config/BEN-Sayc.conf sayc
#
# Called by appserver's /api/system/<key> endpoint.

BEN="$HOME/ben"
VENV="$BEN/.venv/bin/activate"
CONF="${1:-config/onnx.conf}"
SYSKEY="${2:-gib}"

# kill ANY running gameserver (config-agnostic)
pkill -f "gameserver.py --conf" 2>/dev/null
sleep 1

export TF_CPP_MIN_LOG_LEVEL=3 TF_ENABLE_ONEDNN_OPTS=0 PYTHONUNBUFFERED=1
cd "$BEN/src" || exit 1
source "$VENV"

nohup python -u gameserver.py --conf "$CONF" >/tmp/ben_gameserver.log 2>&1 &
echo "gameserver restarting with $CONF (PID=$!)"

# wait up to 40s for the engine port to come up (TF2 .keras load is slower)
for i in $(seq 1 40); do
  if lsof -nP -iTCP:4443 -sTCP:LISTEN >/dev/null 2>&1; then
    printf '%s' "$SYSKEY" > "$BEN/.current_system"
    echo "READY: system=$SYSKEY on 4443 after ${i}s"
    exit 0
  fi
  sleep 1
done
echo "WARN: 4443 not up after 40s — check /tmp/ben_gameserver.log"
exit 1
