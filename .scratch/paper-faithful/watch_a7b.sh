#!/bin/bash
# Watcher cho kernel A7-b (cổng C KHÔNG có wet_ground) — tự gọi Discord khi xong.
#
# Kiến trúc: poll 45 s, ghi log ra FILE (không pipe), gửi MỘT lần cho mỗi trạng
# thái kết thúc. `persist_on_release=true` để watcher sống ngoài session.
#
# Kernel: nguynhuy9669/bevfusion-gate-c-plume-vs-detector version 6
# Output mong đợi: gate_c_out/gate_c_detections_nowet.jsonl (+ summary)

set -u

REPO=/Users/huynguyen/projects/bevfusion-spray-pilot
LOG="$REPO/.scratch/diag/watch_a7b.log"
K=$(command -v kaggle)
KERNEL=nguynhuy9669/bevfusion-gate-c-plume-vs-detector
DEST_DM="discord:uyh04"        # DM có chuông — đường chính
DEST_CH="discord"              # kênh làm việc — đường phụ
STARTED=$(date +%s)

VOICE_DIR="$REPO/.scratch/diag"
VOICE="$VOICE_DIR/a7b.ogg"

say_voice() {
  local text="$1"
  say -v Linh -o "$VOICE_DIR/a7b.aiff" "$text" 2>/dev/null || \
    say -o "$VOICE_DIR/a7b.aiff" "$text" 2>/dev/null || return 1
  ffmpeg -y -loglevel error -i "$VOICE_DIR/a7b.aiff" \
    -c:a libopus -b:a 32k "$VOICE" 2>/dev/null || return 1
  return 0
}

notify_done() {
  local title="$1"; local body="$2"; local voice_text="$3"
  hermes send -t "$DEST_DM" -s "$title" "$body"
  hermes send -t "$DEST_CH" -s "$title" "$body"
  if say_voice "$voice_text"; then
    hermes send -t "$DEST_DM" "MEDIA:$VOICE"
  fi
}

echo "=== watcher started $(date '+%F %T') ===" > "$LOG"
echo "kernel=$KERNEL  poll=45s" >> "$LOG"

CALLS=0
while true; do
  CALLS=$((CALLS + 1))
  STATUS=$("$K" kernels status "$KERNEL" 2>/dev/null | tail -1)
  ELAPSED=$(( $(date +%s) - STARTED ))
  echo "$(date '+%F %T') poll=$CALLS status=$STATUS elapsed=$((ELAPSED/60))m" >> "$LOG"

  case "$STATUS" in
    *COMPLETE*|*complete*)
      HOURS=$(ps -o etime= -p $$ 2>/dev/null | tr -d ' ')
      notify_done \
        "[A7-b] Kernel XONG — không có wet_ground" \
        "Kernel version 6 COMPLETE sau $((ELAPSED/60)) phút.
Output: gate_c_detections_nowet.jsonl
Cần tải về và so Δrecall với bản v5 (−0,2188). Tiên đoán ghi trước: nếu wet_ground là nguyên nhân chính thì Δrecall phải lên ≥ −0,109.
https://www.kaggle.com/code/nguynhuy9669/bevfusion-gate-c-plume-vs-detector" \
        "Kernel A7-b đã xong. Không có wet ground. Mời anh xem kết quả so với bản cũ."
      echo "SENT complete at $(date '+%F %T')" >> "$LOG"
      exit 0
      ;;
    *ERROR*|*error*|*FAILED*|*failed*|*CANCEL*|*cancel*)
      notify_done \
        "[A7-b] Kernel LỖI — $STATUS" \
        "Kernel version 6 dừng sau $((ELAPSED/60)) phút với trạng thái: $STATUS
Xem log:
https://www.kaggle.com/code/nguynhuy9669/bevfusion-gate-c-plume-vs-detector" \
        "Kernel A7-b bị lỗi. Mời anh xem log."
      echo "SENT error at $(date '+%F %T')" >> "$LOG"
      exit 1
      ;;
  esac

  if [ "$ELAPSED" -gt 14400 ]; then
    notify_done \
      "[A7-b] Hết giờ chờ — $STATUS" \
      "Watcher dừng sau $((ELAPSED/60)) phút, trạng thái cuối: $STATUS
https://www.kaggle.com/code/nguynhuy9669/bevfusion-gate-c-plume-vs-detector" \
      "Watcher A7-b hết giờ chờ. Kernel có thể vẫn đang chạy."
    echo "TIMEOUT at $(date '+%F %T')" >> "$LOG"
    exit 2
  fi

  sleep 45
done
