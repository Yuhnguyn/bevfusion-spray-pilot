#!/bin/bash
# Theo dõi đúng version 9 của kernel (version khác version mới nhất).
# Dừng khi COMPLETE/ERROR/CANCEL*, sau đó tải log + in marker.
KC=/tmp/kc/bin/kaggle
K=nguynhuy9669/bevfusion-spray-train
V=${1:-9}
OUT=/tmp/kv${V}_final.log
for i in $(seq 1 40); do
  st=$("$KC" kernels status "$K/$V" 2>/dev/null | tail -1 | sed 's/.*status //; s/"//g')
  echo "$(date +%H:%M) v$V status=$st"
  case "$st" in
    *COMPLETE*|*ERROR*|*CANCEL*)
      "$KC" kernels logs "$K/$V" 2>/dev/null > "$OUT"
      echo "LOG_LINES $(wc -l < "$OUT" | tr -d ' ')"
      grep -oE "TASK_NAME .*|AB_INFO .*|MINI_SPLIT_OK.*|AB_STEP .*|AB_ARM_OK .*|AB_TRAIN_OK .*|AB_FAILED.*" "$OUT" | tail -12
      echo KERNEL_TERMINAL
      break
      ;;
  esac
  sleep 180
done
echo POLL_DONE