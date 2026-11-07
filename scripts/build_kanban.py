#!/usr/bin/env python3
"""Build docs/kanban.html from the issue tracker.

Run from the repo root:  python3 scripts/build_kanban.py
The HTML is self-contained (no CDN, no storage) so it can be published as an
artifact. Re-run after any ticket/spec change and publish again.
"""

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISSUES = ROOT / ".scratch" / "spray-augmentation" / "issues"
OUT = ROOT / "docs" / "kanban.html"

PHASES = [
    {
        "id": "P0",
        "name": "Nền móng & kiểm chứng",
        "desc": "Chốt version, môi trường, checkpoint, dataset, evaluator, velocity.",
        "tickets": ["01", "02", "02b", "03", "04", "05"],
    },
    {
        "id": "P1",
        "name": "Pipeline chèn plume",
        "desc": "Transform, clean points, routing hai nhánh, test end-to-end.",
        "tickets": ["07", "08", "09", "15"],
    },
    {
        "id": "P2",
        "name": "Đo lường & đối chứng",
        "desc": "Adapter evaluator, config A/B, arm lọc spray B0.",
        "tickets": ["06", "10", "14"],
    },
    {
        "id": "P3",
        "name": "Mini A/B",
        "desc": "Train 2 arm trên tập nhỏ, eval trên spray held-out.",
        "tickets": ["11"],
    },
    {
        "id": "P4",
        "name": "Quyết định",
        "desc": "Mở rộng hay dừng, dựa trên tiêu chí đã đăng ký trước.",
        "tickets": ["13"],
    },
    {
        "id": "P5",
        "name": "Tham chiếu",
        "desc": "Thống kê spray thật để kiểm tra simulator (không dùng để train/eval).",
        "tickets": ["12"],
    },
    {
        "id": "P6",
        "name": "Hình học plume",
        "desc": "Đo dạng cụm thật và đổi cách rải điểm sang vỏ cầu phía cảm biến.",
        "tickets": ["16", "17"],
    },
]

META = {
    "01": {
        "short": "Lấy đúng một bản BEVFusion MIT ở commit da93b27, tách khỏi bản gốc để cả nhóm chạy cùng một code.",
        "why": "Nếu mỗi người chạy một version khác nhau, kết quả không so sánh được với nhau.",
        "next": "Không còn — đã xong.",
        "evidence": "4/4 tiêu chí; third_party/ không bị sửa; lệnh version in ra da93b27.",
        "files": ["mit/PIN.md", "mit/bevfusion/"],
    },
    "02": {
        "short": "Chạy thử đúng 1 frame: nạp checkpoint chính thức, forward model một lần, kiểm tra lỗi shape, NaN/Inf và số kênh depth.",
        "why": "Đây là đèn báo an toàn: nếu model và checkpoint không khớp thì mọi thí nghiệm sau đều vô nghĩa.",
        "next": "Đã xong; số liệu nằm trong ticket.",
        "evidence": "582/582 key khớp; forward 0.6 s, peak 1.98 GB; depth [6,1,256,704] đúng 1 kênh; mọi stage finite.",
        "files": [".scratch/spray-augmentation/issues/02-smoke-test-checkpoint.md", "kaggle/smoke_test/"],
    },
    "02b": {
        "short": "Sửa môi trường Kaggle (CUDA 11.8, gcc-11, torchvision, numba…) để smoke test chạy được.",
        "why": "Kaggle mặc định không có toolchain cũ; không sửa thì không build được CUDA ops.",
        "next": "Đã xong.",
        "evidence": "v15 ALL_PASS; toàn bộ chẩn đoán và fix nằm trong ticket 02b.",
        "files": [".scratch/spray-augmentation/issues/02b-numba-fix.md"],
        "checklist": [
            ("x", "Numba 0.58.1 + uv index strategy + escape % trong git log"),
            ("x", "CUDA 11.8 + gcc-11 + đủ cusparse/cublas/curand/cusolver"),
            ("x", "torchvision 0.11.2+cu113 + shim numba.errors"),
            ("x", "Ticket 02 đạt ALL_PASS, checkpoint 582/582"),
        ],
    },
    "03": {
        "short": "Xác định vận tốc box nằm ở hệ tọa độ nào và box dán thêm (ObjectPaste) có vận tốc dùng được không — để đặt plume đúng hướng.",
        "why": "Plume phải nằm sau xe đang chạy. Dùng sai hệ tọa độ là plume lệch hướng, thí nghiệm mất giá trị.",
        "next": "Đã xong.",
        "evidence": "docs/velocity-contract.md: velocity ở LiDAR frame; full val: 50 km/h → 697/34,029 frame (2.0%), 30 km/h → 13.8%.",
        "files": ["docs/velocity-contract.md", ".scratch/spray-augmentation/issues/03-velocity-frame.md"],
    },
    "04": {
        "short": "Kiểm tra dataset nuScenes trên Kaggle: đủ camera/LiDAR/metadata, tạo được file infos (danh mục frame), và load được một frame qua pipeline.",
        "why": "Không có infos thì pipeline không biết frame nào, ảnh nào, calibration nào để load.",
        "next": "Đã xong.",
        "evidence": "v19 TICKET04_OK: infos 120/120, load 1 sample (6 camera, 0 sweep, không thiếu ảnh); drop LoadBEVSegmentation + gt_masks_bev vì use_map=false.",
        "files": ["kaggle/dataset_gate/", "kaggle/smoke_test/cells/17-ticket04-infos-and-sample.py"],
    },
    "05": {
        "short": "Viết evaluator proxy mAP bằng Python thuần, có test bằng box giả để chứng minh nó tính đúng.",
        "why": "Cần một thước đo đáng tin trước khi so sánh A/B; không dùng kết quả cũ của OpenMMLab.",
        "next": "Đã xong.",
        "evidence": "5/5 test: perfect match, duplicate, wrong class, range filter.",
        "files": [".scratch/spray-augmentation/issues/05-evaluator-core.md", "proxy_eval/matcher.py"],
    },
    "06": {
        "short": "Chuyển output thật của BEVFusion (class, box format, score) sang định dạng evaluator hiểu, rồi chấm một frame thật.",
        "why": "Evaluator core đã có, nhưng output model khác format. Adapter là cầu nối; đây là precondition 5.",
        "next": "Đã xong.",
        "evidence": "Frame thật: TP 22 / FP 21 / FN 20, P 0.512, R 0.524, mAP 0.298; threshold 0.05, range 54 m. Test 2 + suite 33 passed.",
        "files": [".scratch/spray-augmentation/issues/06-evaluator-adapter.md", "proxy_eval/mit_adapter.py", "kaggle/smoke_test/evidence/mit_eval_result.json"],
    },
    "07": {
        "short": "Viết transform chèn plume vào point cloud, giữ lại bản 'sạch' trước khi chèn để camera branch dùng.",
        "why": "Camera branch cần point sạch làm sparse depth; LiDAR branch cần point đã có plume. Không tách thì hai nhánh nhìn sai dữ liệu.",
        "next": "Đã xong.",
        "evidence": "scene-0796: points_clean 255,456 → 255,583 (+127); 2 eligible, 4 cluster; 12/12 checks true.",
        "files": [".scratch/spray-augmentation/issues/07-pipeline-transform.md", "spray/plume_transform.py"],
    },
    "08": {
        "short": "Sửa model để nhánh camera nhận points_clean, nhánh LiDAR nhận points đã chèn plume.",
        "why": "Không patch thì camera vẫn nhận point có spray → sai thiết kế thí nghiệm.",
        "next": "Bắt đầu ngay: ticket 07 đã xong.",
        "evidence": "0/4.",
        "files": [".scratch/spray-augmentation/issues/08-model-routing.md"],
    },
    "09": {
        "short": "Test cả pipeline: hai luồng point cùng frame, đúng nhánh; tắt plume thì không có points_clean.",
        "why": "Chứng minh transform và routing hoạt động cùng nhau, không chỉ từng phần.",
        "next": "Sau ticket 07 và 08.",
        "evidence": "0/4.",
        "files": [".scratch/spray-augmentation/issues/09-pipeline-e2e-test.md"],
    },
    "10": {
        "short": "Tạo hai config A/B chỉ khác nhau ở plume; giữ nguyên checkpoint, split, optimizer, LR, seed, batch, số update; đo RAM/thời gian.",
        "why": "Nếu khác nhiều thứ, không biết cải thiện là do plume hay do config.",
        "next": "Sau ticket 09. Nhớ load bằng Config.fromfile(..., _base_), không round-trip qua JSON.",
        "evidence": "0/4.",
        "files": [".scratch/spray-augmentation/issues/10-train-eval-config.md"],
    },
    "11": {
        "short": "Train hai arm trên tập nhỏ, eval trên spray held-out, báo chênh lệch paired + bootstrap theo scene, FP, recall, clean retention.",
        "why": "Đây là kết quả bắt buộc duy nhất của v1: có tín hiệu dương hay không.",
        "next": "Sau ticket 06 và 10.",
        "evidence": "0/5.",
        "files": [".scratch/spray-augmentation/issues/11-mini-ab-run.md"],
    },
    "12": {
        "short": "So sánh plume thật trong SemanticSpray với plume mô phỏng để biết simulator có hợp lý không.",
        "why": "Không dùng SemanticSpray để train/eval; chỉ dùng thống kê để hiệu chỉnh simulator.",
        "next": "Đã xong.",
        "evidence": "4/4; so sánh cluster dense, xét cả extent lẫn khoảng cách tới xe gần nhất.",
        "files": ["docs/semantic-spray-stats.md", "spray/spray_stats.py"],
    },
    "13": {
        "short": "Dựa trên mini A/B, quyết định mở rộng hay dừng; nếu không có khác biệt thì ghi 'no measurable gap'.",
        "why": "Tránh đốt compute vào hướng không có tín hiệu.",
        "next": "Sau ticket 11.",
        "evidence": "0/3.",
        "files": [".scratch/spray-augmentation/issues/13-gate-review.md"],
    },
    "14": {
        "short": "Arm đối chứng không train: lọc điểm nghi spray bằng thống kê (ROR) rồi detect, để chứng minh augmentation đáng làm hơn cách rẻ.",
        "why": "Không có B0, kết quả âm của arm B có thể bị đổ cho 'chưa thử cách rẻ hơn'.",
        "next": "Có thể bắt đầu ngay (ticket 02 và 05 đã xong).",
        "evidence": "0/5; paper báo ROR precision ~50%.",
        "files": [".scratch/spray-augmentation/issues/14-denoise-baseline.md"],
    },
    "16": {
        "short": "Đo trên SemanticSpray: số điểm/cụm, bán kính, độ dày vỏ, số ring theo cự ly — để kiểm tra generator đang rải đều trong khối cầu.",
        "why": "Nếu cụm thật là vỏ mỏng và mật độ giảm theo cự ly, cách sinh hiện tại dạy model sai cấu trúc.",
        "next": "Chạy mở rộng scripts/semantic_spray_stats.py; không sửa generator.",
        "evidence": "Chưa có — cần 3 bảng số theo bucket cự ly.",
        "files": ["scripts/semantic_spray_stats.py", "docs/semantic-spray-stats.md", ".scratch/spray-augmentation/issues/16-plume-geometry-research.md"],
    },
    "17": {
        "short": "Đặt điểm plume trên vỏ cầu phía cảm biến thay vì trong khối cầu.",
        "why": "Điểm ở nửa sau/lòng cầu là vị trí LiDAR không thể có return; cấu trúc sai làm augmentation vô nghĩa.",
        "next": "Chờ ticket 16 có median r_range/r_extent.",
        "evidence": "Chưa có; cần test hình học mới.",
        "files": ["spray/plume.py", "tests/test_plume.py", "docs/plume-model-provenance.md", ".scratch/spray-augmentation/issues/17-plume-shell-geometry.md"],
    },
    "15": {
        "short": "Sửa docstring/trích dẫn của PlumeConfig cho đúng paper Linnhoff §III/Fig.4; không đổi code hay tham số.",
        "why": "Tránh hiểu sai nguồn gốc tham số; PM từng nói sai là paper không có.",
        "next": "Có thể làm ngay, việc nhỏ.",
        "evidence": "docs/plume-model-provenance.md đã có; cần sửa docstring.",
        "files": ["docs/plume-model-provenance.md", "spray/plume.py"],
        "checklist": [
            (" ", "Sửa docstring PlumeConfig (dạng tuyến tính theo tốc độ, nguồn Linnhoff §III/Fig.4)"),
            (" ", "Ghi rõ hai chiều bị gộp ở v1: lớp xe, độ dày màng nước"),
            (" ", "Chạy pytest: 29 passed"),
        ],
    },
}

TIMELINE = [
    {
        "when": "2026-11-07 · Kaggle",
        "tone": "good",
        "title": "Ticket 06 — adapter evaluator",
        "body": "Model chạy 2 frame thật; evaluator local cho mAP 0.298 (P 0.512 / R 0.524), frame thứ hai chứng minh range filter (2 GT ngoài 54 m).",
    },
    {
        "when": "2026-11-07 · Kaggle",
        "tone": "good",
        "title": "Ticket 07 — PlumeTransform",
        "body": "scene-0796: +127 điểm, points_clean giữ nguyên 255,456; 12/12 check pass, transform đúng vị trí sau range filter.",
    },
    {
        "when": "2026-11-05 · v19",
        "tone": "good",
        "title": "Ticket 04 xong — TICKET04_OK",
        "body": "infos train/val = 120/120 trong 109 s; load 1 sample qua pipeline với đủ 6 camera, 0 sweep, không thiếu ảnh. Phát hiện thêm: chỉ 2% frame val có xe ≥50 km/h.",
    },
    {
        "when": "2026-11-05 · v18",
        "tone": "bad",
        "title": "Lệch schema cam_intrinsic",
        "body": "infos đúng 120/120 nhưng pipeline chết ở KeyError 'cam_intrinsic': converter ghi camera_intrinsics, dataset đọc cam_intrinsic. Thêm alias.",
    },
    {
        "when": "2026-11-05 · v17",
        "tone": "bad",
        "title": "Index token sau khi lọc scene",
        "body": "Lọc nusc.sample làm lệch _token2ind nên get_boxes IndexError. Rebuild index; infos 120/120 trong 117 s.",
    },
    {
        "when": "2026-11-05 · v16",
        "tone": "bad",
        "title": "Thêm bước tạo infos — lộ 2 lỗi",
        "body": "Tạo được infos nhưng val thành 34.029 vì converter gán mọi non-train sample vào val. Load sample fail vì mirror thiếu maps/expansion/*.json.",
    },
    {
        "when": "2026-11-05 · v15 (tay)",
        "tone": "good",
        "title": "Ticket 02 ALL_PASS",
        "body": "Checkpoint 582/582, forward 0.6 s, peak 1.98 GB, depth 1 kênh đúng dtransform, mọi output finite.",
    },
    {
        "when": "2026-11-05 · v14",
        "tone": "warn",
        "title": "Checkpoint load OK, model crash",
        "body": "ConfigDict đã sửa lỗi train_cfg, nhưng harness đọc DepthLSSTransform.out_channels — attr không tồn tại ở pin da93b27.",
    },
    {
        "when": "2026-11-05 · v13",
        "tone": "warn",
        "title": "Ops OK, thiếu torchvision",
        "body": "CUDA ops build và GPU smoke pass; mmcv runner cần torchvision nên ops smoke fail toàn bộ.",
    },
    {
        "when": "2026-11-05 · v12",
        "tone": "warn",
        "title": "CUDA 11.8 + gcc-11 hoạt động",
        "body": "Hết lỗi _Float32 và thiếu header; ops compile thành công. Blocker còn lại: torchvision.",
    },
]

GLOSSARY = [
    ("Checkpoint", "File chứa trọng số đã train. Nạp vào model để model có 'kiến thức'."),
    ("Forward", "Chạy model một lần từ input đến output dự đoán."),
    ("Tensor / shape", "Mảng số nhiều chiều. Shape là kích thước từng chiều, ví dụ [6,1,256,704]."),
    ("Plume", "Cụm điểm nước bắn phía sau xe đang chạy trên đường ướt."),
    ("infos.pkl", "File danh mục frame: đường dẫn ảnh/LiDAR, calibration, GT. Pipeline đọc file này."),
    ("Proxy mAP", "Thước đo phát hiện tự viết, đơn giản hơn NDS của nuScenes, dùng để so A/B."),
    ("Paired A/B", "So sánh hai phiên bản trên cùng một frame; chỉ khác đúng một biến."),
    ("Held-out spray", "Bộ tham số spray không dùng khi train, chỉ dùng khi eval."),
    ("Precondition", "Điều kiện phải xong trước khi được làm tiếp."),
    ("Blocked by", "Ticket này phải chờ ticket khác xong mới bắt đầu."),
    ("Checkbox", "Tiêu chí nghiệm thu. Chỉ tick khi có bằng chứng thật."),
]

DEP_CHAINS = [
    ["01", "02", "06", "10", "11", "13"],
    ["01", "04", "07", "08", "09", "10"],
    ["02", "05", "14"],
    ["07", "08", "09"],
]


def parse_checkboxes(text):
    return re.findall(r"^- \[([ x])\]\s*(.+)$", text, re.M)


def parse_ticket(path):
    text = path.read_text()
    tid = re.match(r"(\d+[a-z]?)", path.name).group(1)
    title = re.search(r"^#\s+(.+)$", text, re.M)
    title = title.group(1).strip() if title else path.stem
    status = re.search(r"\*\*(?:Status|Trạng thái):\*\*\s*(.+)", text)
    status = status.group(1).strip() if status else ""
    blocked = re.search(r"\*\*(?:Blocked by|Phụ thuộc):\*\*\s*(.+)", text)
    blocked = blocked.group(1).strip() if blocked else ""
    boxes = parse_checkboxes(text)
    meta = META.get(tid, {})
    if "checklist" in meta:
        boxes = meta["checklist"]
    done = sum(1 for mark, _ in boxes if mark == "x")
    blockers = re.findall(r"\b\d+[a-z]?\b", blocked)
    return {
        "id": tid,
        "title": re.sub(r"^\d+[a-z]?:\s*", "", title),
        "raw_status": status,
        "blockers": [b for b in blockers if b != tid],
        "done": done,
        "total": len(boxes),
        "checklist": [{"done": mark == "x", "text": label} for mark, label in boxes],
        "meta": meta,
    }


def choose_kind(ticket, by_id):
    tid = ticket["id"]
    status = ticket["raw_status"].lower()
    if tid == "02b":
        return "done"
    if tid in ("03", "04") and ticket["done"] < ticket["total"]:
        return "progress"
    if status.startswith("done"):
        return "done"
    if "ready-for-agent" in status:
        unresolved = [
            b
            for b in ticket["blockers"]
            if b in by_id and by_id[b]["kind"] != "done"
        ]
        return "blocked" if unresolved else "ready"
    return "triage"


def main():
    tickets = [parse_ticket(p) for p in sorted(ISSUES.glob("*.md"))]
    by_id = {t["id"]: t for t in tickets}

    for t in tickets:
        t["kind"] = "triage"
    changed = True
    while changed:
        changed = False
        for t in tickets:
            kind = choose_kind(t, by_id)
            if kind != t["kind"]:
                t["kind"] = kind
                changed = True

    phase_of = {}
    for phase in PHASES:
        for tid in phase["tickets"]:
            phase_of[tid] = phase["id"]

    for t in tickets:
        meta = t["meta"]
        t["short"] = meta.get("short", "")
        t["why"] = meta.get("why", "")
        t["next"] = meta.get("next", "")
        t["evidence"] = meta.get("evidence", "")
        t["files"] = meta.get("files", [])
        t["phase"] = phase_of.get(t["id"], "P0")
        t["blocked_labels"] = [
            b for b in t["blockers"] if b in by_id and by_id[b]["kind"] != "done"
        ]

    total_boxes = sum(t["total"] for t in tickets)
    done_boxes = sum(t["done"] for t in tickets)
    counts = {k: sum(1 for t in tickets if t["kind"] == k) for k in ("done", "progress", "ready", "blocked", "triage")}

    for phase in PHASES:
        boxes_total = sum(by_id[i]["total"] for i in phase["tickets"] if i in by_id)
        boxes_done = sum(by_id[i]["done"] for i in phase["tickets"] if i in by_id)
        phase["done"] = boxes_done
        phase["total"] = boxes_total
        phase["percent"] = round(100 * boxes_done / boxes_total) if boxes_total else 0

    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "spec": {
            "version": "1.5",
            "status": "ready-for-agent",
            "note": "Preconditions 1–6 pass. Ticket 06/07 done; ticket 08 là việc tiếp theo.",
        },
        "focus": {
            "ticket": "08",
            "headline": "Ticket 06 + 07 xong — chuyển sang model routing (08)",
            "detail": "Adapter cho mAP 0.298 trên frame thật; PlumeTransform pass 12/12 check. Ticket 08 nối points_clean vào camera branch và points vào LiDAR branch.",
        },
        "overall": {
            "tickets": len(tickets),
            "boxes_done": done_boxes,
            "boxes_total": total_boxes,
            "percent": round(100 * done_boxes / total_boxes) if total_boxes else 0,
            "counts": counts,
        },
        "phases": PHASES,
        "tickets": tickets,
        "timeline": TIMELINE,
        "glossary": [{"term": a, "def": b} for a, b in GLOSSARY],
        "dep_chains": DEP_CHAINS,
    }

    template = (Path(__file__).parent / "kanban_template.html").read_text()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(template.replace("__DATA__", payload))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
