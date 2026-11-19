# Vì sao `corr(Δrecall, lượng spray) = +0,192` — nghịch lý đã giải (2026-11-20)

Câu hỏi gây lo: *"scene sụp −0,526 chỉ với 55 điểm/frame; scene bơm 342 điểm/frame chỉ sụp
−0,091. Tương quan dương nghĩa là spray ít nguy hiểm hơn spray nhiều?"*

**Trả lời: không. Đó là artefact của mẫu số, không phải quan hệ nhân quả.** Đo được, không suy luận.

---

## 1. Ba sự thật đo được, xếp theo thứ tự phát hiện

### (a) Mỗi frame chỉ có **đúng 1 GT box** — recall mỗi frame là nhị phân

`n_gt/frame = 1,00` ở **cả 12 scene** (đo trên 954 frame). Nên:

```
recall(scene) = (số frame bắt được) / (số frame)        ← tỉ lệ nhị phân
Δrecall       = plume_rate − clean_rate
```

Không có chuyện "một lần trượt trong 10 box chỉ mất 0,1". Một frame hoặc bắt được hoặc không.

### (b) Biến thật là **retention** — tỉ lệ frame giữ được trong số frame clean vốn bắt được

```
retention = (số frame plume bắt được ∩ clean bắt được) / (số frame clean bắt được)
          ⇒ plume_recall = clean_recall × retention
          ⇒ Δrecall      = clean_recall × (retention − 1)
```

| scene | clean | plume | **retention** | CI95 Wilson | spray/f | Δrecall | dự đoán |
|---|---:|---:|---:|---|---:|---:|---:|
| 0000 (Crafter) | 0,816 | 0,289 | **0,323** | [0,220; 0,446] | 55,1 | −0,526 | −0,553 |
| 0006 | 0,515 | 0,242 | **0,412** | [0,288; 0,548] | 26,5 | −0,273 | −0,303 |
| 0048 | 0,769 | 0,369 | **0,420** | [0,294; 0,558] | 298,3 | −0,400 | −0,446 |
| 0054 | 0,672 | 0,459 | **0,683** | [0,530; 0,804] | 79,3 | −0,213 | −0,213 |
| 0096 | 0,835 | 0,671 | **0,803** | [0,692; 0,881] | 157,4 | −0,165 | −0,165 |
| 0102 | 0,486 | 0,375 | **0,743** | [0,579; 0,858] | 122,2 | −0,111 | −0,125 |
| 0000 (Golf) | 1,000 | 0,922 | **0,922** | [0,862; 0,957] | 68,5 | −0,078 | −0,078 |
| 0012 | 0,817 | 0,577 | **0,707** | [0,580; 0,808] | 13,3 | −0,239 | −0,239 |
| 0048 (Golf) | 1,000 | 0,814 | **0,814** | [0,727; 0,877] | 397,9 | −0,186 | −0,186 |
| 0054 | 0,904 | 0,750 | **0,819** | [0,729; 0,884] | 125,4 | −0,154 | −0,163 |
| 0096 | 1,000 | 0,811 | **0,811** | [0,686; 0,894] | 392,0 | −0,189 | −0,189 |
| 0102 | 0,977 | 0,886 | **0,884** | [0,755; 0,949] | 342,2 | −0,091 | −0,114 |

**Kiểm chứng công thức:** `corr(Δrecall thật, clean_recall × (retention−1)) = +0,996`,
sai số tuyệt đối p50 = **0,0048**, max 0,046. Công thức đúng.

### (c) Vì thế tương quan dương là **hệ quả số học**, không phải cơ chế

Với `Δrecall = clean_recall × (retention − 1)`:

- `corr(Δrecall, clean_recall) = +0,205` — scene mà detector vốn yếu (clean thấp) thì Δrecall
  nhỏ **theo**, bất kể plume dày hay mỏng. Đây là **hiệu ứng trần/sàn** thuần tuý.
- `corr(clean_recall, spray/f) = +0,537` — scene dễ thường nhiều điểm nền và nhiều spray hơn.
- Hợp hai điều trên ⇒ `corr(Δrecall, spray/f) > 0` **mà không cần** spray ít nguy hiểm hơn.

## 2. Nhưng retention **có** phụ thuộc lượng spray — đây là phần thật

`corr(retention, spray/f) = +0,318`. Retention dao động **0,323–0,922**, tức 3,8 lần. Đây mới là
biến cần giải thích, và nó **không** bị confound bởi mẫu số.

Xếp retention theo lượng spray:

| nhóm | retention |
|---|---|
| spray 13–79/f (0006, 0012, 0000-Golf, 0054-Crafter) | 0,412 · 0,707 · 0,922 · 0,683 |
| spray 122–157/f | 0,743 · 0,803 |
| spray 298–398/f | 0,420 · 0,814 · 0,811 · 0,884 |

Không đơn điệu ⇒ lượng spray **một mình không quyết định** retention. Hai scene tệ nhất
(0000-Crafter 0,323 và 0006 0,412) lại có spray **thấp** (55,1 và 26,5).

## 3. Hai scene tệ nhất có gì chung — biến còn lại

Đo được: **vật thể mỏng** (ít điểm LiDAR) thì confidence mỏng manh hơn. Chuẩn hoá mất mát theo
liều (Δrecall trên mỗi 1 % điểm plume thêm vào), chia theo độ dày vật thể:

| độ dày vật thể | điểm xe/box p50 | Δrecall p50 | inj% p50 | **Δ trên 1 % liều** |
|---|---:|---:|---:|---:|
| mỏng nhất | 94,5 | −0,197 | 0,256 | **−1,68** |
| giữa | 204,1 | −0,187 | 0,894 | **−0,20** |
| dày nhất | 352,0 | −0,282 | 0,368 | **−0,38** |

**Cùng một lượng nhiễu, vật thể mỏng mất recall gấp 4,4 lần vật thể dày** (−1,68 so với −0,38
trên mỗi 1 % liều). Và `corr(điểm xe/box, Δrecall) = −0,492` — nghịch đảo mạnh hơn cả spray.

Scene 0000 (Crafter): vật thể ở **24,3 m**, **305 điểm/box** nhưng retention chỉ **0,323**. Scene
0006: **146 điểm/box** ở **33,7 m**, retention 0,412. Cả hai đều ở xa và mỏng.

## 4. Kết luận — trả lời trực tiếp câu hỏi

**Nghịch lý không phải nghịch lý.** Ba tầng:

1. **Tầng số học (đã giải):** `Δrecall = clean_recall × (retention−1)` với `n_gt = 1` mỗi frame
   ⇒ Δrecall bị chặn trên bởi `clean_recall`. Tương quan dương với lượng spray là **confound**
   qua `clean_recall` (`corr = +0,537`). Công thức khớp `r = 0,996`, sai số 0,0048.
2. **Tầng vật lý (biến thật):** **độ mỏng của vật thể**. Vật thể ít điểm ⇒ confidence mỏng ⇒
   cùng lượng nhiễu đánh sập dễ hơn 4,4 lần. `corr(điểm xe/box, Δrecall) = −0,492`.
3. **Tầng cơ chế (đã đo ở lượt trước):** nhiễu tác động **cục bộ trong ~6 m** quanh vật thể
   (mất 22,9 % khi plume cách 2–4 m, chỉ 0,9 % khi cách >20 m), và làm **score sụp** chứ không
   che khuất (20,1 % hộp đúng rớt score dù IoU vẫn 0,7–0,8).

Nên câu "spray nhiều hại ít" là **sai cách đọc**. Đúng là: *scene mà detector vốn đã yếu thì
Δrecall nhỏ vì trần, và scene đó thường có ít spray hơn* — hai chuyện độc lập bị dính vào nhau
qua biến `clean_recall`.

## 5. Hệ quả cho cách báo cáo (phải sửa)

Không được báo `corr(Δrecall, lượng spray)` nữa — nó gây hiểu sai. Báo ba thứ:

1. **retention** (0,323–0,922, p50 0,773) kèm CI Wilson — đây là biến sạch;
2. **Δ trên mỗi 1 % liều**, chia theo độ dày vật thể — thấy rõ liều–đáp ứng thật;
3. `Δrecall` thô **kèm** `clean_recall`, vì Δ bị chặn bởi clean.

## 6. Tái lập

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_retention.py
```

Script liên quan: `rootcause_denominator.py` (phát hiện `n_gt = 1`), `rootcause_paradox.py`
(confound), `rootcause_fragility.py` (độ mỏng vật thể).
