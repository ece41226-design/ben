#!/bin/bash
# Ben on Apple Silicon — verified working launcher (2026-07-19)
# gameserver (engine, ws:4443) + appserver (browser frontend, http:8080)
# Config: config/onnx.conf  |  DDS fix: /opt/homebrew/lib/{libdds,dds}.dylib -> bin/darwin/libdds.2.9.0.dylib
#
# Usage:
#   ./start_ben_mac.sh          # Mac-local only  -> http://127.0.0.1:8080/home
#   ./start_ben_mac.sh --lan    # also expose on LAN for phone (same wifi)
#   ./start_ben_mac.sh stop     # kill both servers

set -e
BEN="$HOME/ben"
VENV="$BEN/.venv/bin/activate"
CONF="config/BEN-21GF.conf"   # default = 2/1 Game Force (二盖一逼局)

if [ "$1" = "stop" ]; then
  pkill -f "gameserver.py --conf" 2>/dev/null && echo "gameserver stopped" || echo "gameserver not running"
  pkill -f "appserver.py" 2>/dev/null && echo "appserver stopped" || echo "appserver not running"
  exit 0
fi

HOSTARG=""
[ "$1" = "--lan" ] && HOSTARG="--host 0.0.0.0"

export TF_CPP_MIN_LOG_LEVEL=3 TF_ENABLE_ONEDNN_OPTS=0 PYTHONUNBUFFERED=1

# engine — gameserver ALWAYS binds 0.0.0.0 internally and has no --host arg,
# so it is LAN-reachable regardless of --lan; do NOT pass $HOSTARG here.
cd "$BEN/src"; source "$VENV"
nohup python -u gameserver.py --conf "$CONF" >/tmp/ben_gameserver.log 2>&1 &
echo "gameserver PID=$! (ws:4443)  log:/tmp/ben_gameserver.log"
printf '21gf' > "$BEN/.current_system"   # default config = BEN-21GF.conf = 2/1 GF

# frontend
cd "$BEN/src/frontend"
nohup python -u appserver.py $HOSTARG >/tmp/ben_appserver.log 2>&1 &
echo "appserver  PID=$! (http:8080) log:/tmp/ben_appserver.log"

sleep 10
if lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "READY -> http://127.0.0.1:8080/home"
  [ "$1" = "--lan" ] && echo "LAN   -> http://$(ipconfig getifaddr en0 2>/dev/null):8080/home"
else
  echo "WARN: 8080 not listening yet, check /tmp/ben_appserver.log"
fi
