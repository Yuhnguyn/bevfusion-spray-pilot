#!/bin/bash
# Tải checkpoint của đúng version kernel rồi chuẩn bị thư mục dataset để upload.
set -e
KC=/tmp/kc/bin/kaggle
K=nguynhuy9669/bevfusion-spray-train
V=${1:-9}
DST=${2:-$HOME/.hermes/drafts/spray-pilot/ckpt_v$V}
mkdir -p "$DST"
"$KC" kernels output "$K/$V" -p "$DST" --file-pattern 'ckpt_arm.*\.pth' -o -q
echo "--- files ---"
ls -lh "$DST" 2>/dev/null | tail -5
echo "--- sha256 ---"
shasum -a 256 "$DST"/*.pth 2>/dev/null
du -sh "$DST" 2>/dev/null
echo CKPT_FETCH_DONE