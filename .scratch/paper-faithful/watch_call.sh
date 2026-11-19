#!/usr/bin/env bash
# Canh kernel A7 (cổng C) và TỰ GỌI Discord khi xong — không cần session Hermes sống.
#
# Gọi 3 đường: (1) DM kèm tin nhắn THOẠI (có tiếng), (2) kênh nhà có link,
# (3) ghi log. Chỉ gọi một lần khi trạng thái kết thúc.
#
# Chạy: nohup bash .scratch/paper-faithful/watch_call.sh > /dev/null 2>&1 &

set -uo pipefail

REPO=/Users/huynguyen/projects/bevfusion-spray-pilot
SLUG=nguynhuy9669/bevfusion-gate-c-plume-vs-detector
URL="https://www.kaggle.com/code/nguynhuy9669/bevfusion-gate-c-plume-vs-detector"
LOG="$REPO/.scratch/diag/watch_call.log"
VOICE_DIR="$HOME/.hermes/cache/scratch"
DM="discord:uyh04"

K=$(command -v kaggle)
mkdir -p "$(dirname "$LOG")" "$VOICE_DIR"
: > "$LOG"

say_and_send() {
    local text="$1" caption="$2" subject="$3"
    # Giọng Việt "Linh" nếu máy có, không thì giọng mặc định (vẫn là tiếng nói).
    if say -v Linh -o "$VOICE_DIR/a7.aiff" "$text" 2>/dev/null; then
        :
    else
        say -o "$VOICE_DIR/a7.aiff" "$text"
    fi
    if command -v ffmpeg >/dev/null 2>&1; then
        ffmpeg -y -loglevel error -i "$VOICE_DIR/a7.aiff" \
               -c:a libopus -b:a 32k "$VOICE_DIR/a7.ogg" 2>/dev/null \
            && hermes send -t "$DM" "MEDIA:$VOICE_DIR/a7.ogg" >>"$LOG" 2>&1
    fi
    hermes send -t "$DM" -s "$subject" "$caption" >>"$LOG" 2>&1
    hermes send -t discord -s "$subject" "$caption" >>"$LOG" 2>&1
}

echo "watcher start $(date +%H:%M:%S)" >>"$LOG"

for i in $(seq 1 240); do
    ST=$("$K" kernels status "$SLUG" 2>&1 | grep -v '^Warning' | tail -1)
    echo "$(date +%H:%M:%S) [$i] $ST" >>"$LOG"

    case "$ST" in
        *COMPLETE*|*ERROR*|*CANCEL*)
            STATUS=$(printf '%s' "$ST" | grep -o 'KernelWorkerStatus\.[A-Z]*' | cut -d. -f2)
            [ -n "$STATUS" ] || STATUS=UNKNOWN
            echo "FINAL: $STATUS at $(date +%H:%M:%S)" >>"$LOG"

            if [ "$STATUS" = "COMPLETE" ]; then
                say_and_send \
                    "A 7 xong rồi. Cổng C đã có kết quả, mời anh vào xem." \
                    "✅ CỔNG C XONG — kernel COMPLETE

Đang tải output rồi chấm Δrecall theo ngưỡng pre-register [−0,099; +0,001].
Kết quả chi tiết sẽ gửi tiếp ở đây.

$URL" \
                    "[SPRAY-PILOT] Cổng C xong"
            else
                say_and_send \
                    "A 7 báo lỗi. Kernel cổng C dừng với trạng thái $STATUS." \
                    "⚠️ CỔNG C DỪNG — trạng thái $STATUS

Cần xem log kernel để biết lý do. Chưa có Δrecall.

$URL" \
                    "[SPRAY-PILOT] Cổng C dừng: $STATUS"
            fi
            exit 0
            ;;
    esac
    sleep 45
done

say_and_send \
    "Hết thời gian canh. Kernel cổng C chưa báo kết thúc." \
    "⏱️ Watcher hết hạn sau 180 phút — kernel chưa về trạng thái kết thúc.

$URL" \
    "[SPRAY-PILOT] Watcher hết hạn"
exit 0
