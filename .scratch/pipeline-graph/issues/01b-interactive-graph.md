# Ticket 01b: Bản đồ pipeline tương tác (graph HTML, bấm node xổ code)

Skill: không

## Bối cảnh

Repo `~/projects/bevfusion-spray-pilot`. Đã có bản đồ dạng bài viết do Codex tạo:

- `docs/pipeline-map.md` — bản nguồn Markdown (nguồn sự thật về nội dung)
- `docs/pipeline-map.html` — HTML sinh từ MD bằng `scripts/render_pipeline_map.py`
- `AGENTS.md` đã có luật: đổi công thức → sửa MD → chạy lại script

Vấn đề: bản hiện tại là bài viết dài, ít trực quan, công thức chỉ là LaTeX thô trong khối monospace,
2 khối công thức bị tràn ngang. User muốn bản đồ **dạng graph tương tác, minimalist, nền sáng,
ít chữ**, kiểu trang tài liệu graphify.

Đã kiểm chứng sẵn (PM verify, đừng kiểm lại): mọi link `file.py#Lxxx` trong MD hiện nay đều tồn tại
và đúng hàm. Danh sách hàm + dòng đã verify đúng:

| hàm | file:dòng |
|---|---|
| `PlumeTransform.__call__` | spray/plume_transform.py:85 |
| `inject_plume_stateful` | spray/plume.py:307 |
| `steady_state_factor` | spray/plume.py:256 |
| `cluster_rate_for_speed` | spray/plume.py:181 |
| `lifetime_mean_s` | spray/plume_state.py:260 |
| `wind_vector` | spray/plume_state.py:268 |
| `PlumeState.advance` | spray/plume_state.py:491 |
| `PlumeState.prune` | spray/plume_state.py:530 |
| `PlumeState.spawn` | spray/plume_state.py:349 |
| `PlumeState.select_alive` | spray/plume_state.py:586 |
| `needs_warm_start` | spray/plume_state.py:303 |
| `warm_start` | spray/plume_state.py:307 |
| `load_beam_table` | spray/beam_model.py:55 |
| `build_beams` | spray/beam_model.py:75 |
| `ray_sphere_intersect` | spray/beam_model.py:157 |
| `raycast_frame` | spray/raycast.py:166 |
| `RaycastConfig` | spray/raycast.py:99 |
| `_collect_hits` | spray/raycast.py:462 |
| `_keep_strongest_per_beam` | spray/raycast.py:600 |
| `build_context` | scripts/sspp_infer.py:492 |
| `read_infos` | scripts/sspp_infer.py:448 |
| `clean_points` | scripts/sspp_infer.py:473 |
| `load_points` | spray/sspp_adapter.py:218 |
| `read_frame_boxes` | spray/sspp_adapter.py:90 |

## Việc phải làm

1. Viết script `scripts/build_pipeline_graph.py`:
   - Parse `docs/pipeline-map.md` + đọc source các file `spray/*.py`, `scripts/sspp_infer.py`,
     `scripts/sspp_infer.py` để extract **nguyên văn source** của các hàm trong bảng trên
     (dùng `ast` — cắt từ `def`/`class` đến hết block; chơi cả decorator).
   - Sinh node theo các **nhóm/lớp màu** sau (giữ đúng thứ tự data → simulate → raycast → out):
     a. **Dữ liệu vào**: `read_infos`, `read_split`, `clean_points`, `load_points`, `read_labels`,
        `read_frame_boxes`, `build_context` — node này nói rõ "PlumeTransform KHÔNG tự đọc file;
        thiếu plume_context thì raise".
     b. **Điểm vào**: `PlumeTransform.__call__`
     c. **Chu kỳ cụm**: `inject_plume_stateful`, `lifetime_mean_s` (công thức T),
        `steady_state_factor` (công thức K), `cluster_rate_for_speed`, `PlumeState.spawn`,
        `needs_warm_start`, `warm_start`
     d. **Trôi cụm**: `wind_vector` (công thức gió), `PlumeState.advance` (công thức lực cản),
        `PlumeState.prune` (P_survive)
     e. **Raycast**: `load_beam_table`, `build_beams`, `ray_sphere_intersect`, `raycast_frame`,
        `RaycastConfig`, `_collect_hits`, `_keep_strongest_per_beam`
     f. **Ghép ra**: `PlumeState.select_alive`, ghép `points_out` tại plume_transform.py:129
   - Edge = lời gọi thật giữa 2 hàm trong bảng (lấy từ call-site trong source, KHÔNG bịa).
     Edge chéo nhóm cho phép (vd `__call__` → `inject_plume_stateful`), vẽ cong và có mũi tên.
   - Nhúng cả **công thức đã render sẵn** từ MD: các khối `\[…\]` → chuỗi công thức hiển thị dạng
     "đẹp" (nếu dùng KaTeX thì nhúng KaTeX inline vào chính file HTML — static, không CDN).
   - Output: một file JSON `docs/pipeline-graph.json` chứa {nodes, edges, sources, formulas}.

2. Viết/generate `docs/pipeline-graph.html` — **một file HTML tự chứa duy nhất** (inline CSS + JS +
   JSON + KaTeX nếu dùng; 0 request mạng, mở bằng `open docs/pipeline-graph.html` chạy ngay):
   - **Layout graph**: dùng SVG hoặc canvas thuần; không bắt buộc thư viện ngoài (nếu dùng thư viện
     CDN thì ĐỌC LẠI ràng buộc "0 request mạng" — phải nhúng nguyên thư viện vào file).
     Nên layout DAG dạng left-to-right theo nhóm, không chồng node.
   - **Click node** → panel bên xổ: tên hàm, mô tả ngắn (lấy từ MD), công thức (nếu có), rồi
     **source code đầy đủ** với highlight dòng chính (tên hàm, dòng được nhắc trong MD).
     Panel có link "mở trong editor" dạng `../spray/plume_state.py#L491`.
   - **Ô search** ở trên: gõ tên hàm/công thức/từ khoá → lọc node, Enter nhảy tới node khớp đầu tiên.
   - **Hover edge/node** → highlight đường đi liên quan (node + edge cùng màu sáng hơn, node khác
     mờ đi). Không cần animation phức tạp.
   - **Minimalist, nền sáng, màu hài hoà** (user yêu cầu rõ): palette màu pastel/nhẹ trên nền trắng
     hoặc trắng ngà; chữ ít; node chỉ tên hàm ngắn + nhóm màu; chi tiết để trong panel click.
     Tham khảo palette hiện tại `(—ink:#17232d, wash:#f2f6f8, blue:#126782, teal:#147d70)` nhưng
     có thể đổi cho cân; đừng dùng nền tối.
   - **Responsive vừa phải**: chạy đẹp ở 1280×800 trở lên; mobile chỉ cần không vỡ layout.
   - Panel + graph + search đều dùng cùng bộ màu; formula dùng đúng ký hiệu toán (phân số, chỉ số
     dưới, ký hiệu Σ, 𝒩, e^…), không còn chữ `\frac` thô.

3. Cập nhật:
   - Sửa `AGENTS.md` (phần "Generator pipeline map") thêm một dòng: graph tương tác rebuild bằng
     `python scripts/build_pipeline_graph.py && python scripts/render_pipeline_map.py`.
   - Thêm 1 dòng vào `docs/pipeline-map.md` đầu trang: "Bản đồ graph tương tác:
     `docs/pipeline-graph.html` — rebuild bằng script".

4. **KHÔNG commit**. PM sẽ tự nghiệm thu rồi commit.

## Ràng buộc

- Không sửa bất kỳ file `spray/*.py` hay logic pipeline. Thay đổi chỉ nằm ở:
  `scripts/build_pipeline_graph.py` (mới), `docs/pipeline-graph.html` (mới), `docs/pipeline-graph.json`
  (mới), `docs/pipeline-map.md` (+1 dòng), `AGENTS.md` (+1 dòng), và được phép sửa
  `scripts/render_pipeline_map.py` **chỉ** để thêm link tới graph ở đầu trang (nếu cần).
- Không xoá hay ghi đè nội dung `docs/pipeline-map.md` — nó là nguồn sự thật, chỉ thêm, bớt đúng chỗ.
- HTML tự chứa: 0 request mạng.
- Nếu bạn cho rằng phải đổi phạm vi (ví dụ bỏ nhánh data vì quá rối) thì **DỪNG**, báo PM — đó là
  quyết định của PM.
- Mọi source nhúng vào JSON phải là nguyên văn từ file thật — không copy tay, không "diễn giải" code.
  Trong script extract, sau khi chạy, chọn ngẫu nhiên 3 hàm và so substring với file gốc để self-check
  (in `EXTRACT_OK` nếu 3/3 khớp).

## Xong khi

- `python scripts/build_pipeline_graph.py` chạy được, exit 0, in `EXTRACT_OK` + số node + số edge.
- `docs/pipeline-graph.html` mở bằng file:// được, 0 lỗi console (in bằng
  `python -c "..."` không bắt buộc — tự kiểm bằng cách mở không được thì ghi lại trong báo cáo).
- Báo cáo cuối ghi: số node, số edge, danh sách nhóm node, và 3 link sample bạn đã test.
- TREE sạch ngoài các file được phép. **Không commit.**
