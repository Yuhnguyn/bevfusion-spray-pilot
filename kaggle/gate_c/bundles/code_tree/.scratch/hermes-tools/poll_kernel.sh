#!/bin/bash
# poll kernel train: in giờ / số dòng log / số marker / marker cuối, dừng khi có kết quả
OUT=${1:-/tmp/kv10.log}
MAX=${2:-45}
for i in $(seq 1 "$MAX"); do
  kaggle kernels logs nguynhuy9669/bevfusion-spray-train 2>/dev/null > "$OUT"
  lines=$(wc -l < "$OUT" | tr -d ' ')
  markers=$(grep -cE "AB_STEP|AB_ARM_OK|AB_TRAIN_OK|AB_FAILED|EVAL_OK|EVAL_FAILED" "$OUT")
  last=$(grep -oE "TASK_NAME.*|TASK_ARGS .*|AB_INFO .*|MINI_SPLIT_OK.*" "$OUT" | tail -1 | cut -c1-70)
  echo "$(date +%H:%M) lines=$lines markers=$markers last=$last"
  if grep -qE "AB_TRAIN_OK|AB_FAILED|EVAL_OK|EVAL_FAILED" "$OUT"; then
    echo KERNEL_DONE
    break
  fi
  sleep 120
done
echo POLL_EXIT