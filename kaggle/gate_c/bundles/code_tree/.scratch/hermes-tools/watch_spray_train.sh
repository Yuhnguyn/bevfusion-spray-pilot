#!/bin/bash
# Poll the spray-train kernel until it leaves RUNNING/QUEUED, then dump a
# compressed failure card (markers + last traceback + tail) instead of the
# raw 900-line log.
set -u
K=nguynhuy9669/bevfusion-spray-train
CARD_DIR="$HOME/.hermes/drafts/spray-pilot"
mkdir -p "$CARD_DIR"
for i in $(seq 1 200); do
  st=$(kaggle kernels status "$K" 2>/dev/null | grep -o 'KernelWorkerStatus\.[A-Z_]*' | head -1)
  echo "[$(date +%H:%M:%S)] poll $i -> ${st:-unknown}" >> /tmp/watch_train.log
  case "${st:-}" in
    *COMPLETE*|*ERROR*|*CANCEL*)
      echo "FINAL $st" >> /tmp/watch_train.log
      kaggle kernels logs "$K" > /tmp/ktrain_raw.log 2>&1
      python3 "$HOME/.hermes/scripts/kernel_card.py" /tmp/ktrain_raw.log \
        "$CARD_DIR/card-latest.md" >> /tmp/watch_train.log 2>&1
      cp /tmp/ktrain_raw.log "$CARD_DIR/raw-latest.log" 2>/dev/null
      echo "CARD $CARD_DIR/card-latest.md" >> /tmp/watch_train.log
      exit 0;;
  esac
  sleep 60
done
echo "TIMEOUT watching" >> /tmp/watch_train.log