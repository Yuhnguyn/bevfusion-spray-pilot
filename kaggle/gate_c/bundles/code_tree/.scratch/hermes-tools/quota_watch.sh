#!/bin/bash
# theo dõi quota GPU + trạng thái kernel để biết session còn sống hay đã chết
prev=""
for i in $(seq 1 4); do
  used=$(kaggle quota 2>/dev/null | awk '/^GPU/ {print $2}' | tr -d 'h')
  st=$(kaggle kernels status nguynhuy9669/bevfusion-spray-train 2>/dev/null | tail -1 | sed 's/.*status //')
  echo "$(date +%H:%M) gpu_used=${used}h status=$st prev=${prev}"
  prev=$used
  [ "$i" -lt 4 ] && sleep 600
done
echo QUOTA_WATCH_DONE