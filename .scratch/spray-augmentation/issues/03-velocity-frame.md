# 03: Xác minh velocity frame và ObjectPaste

**What to build:** Câu trả lời có bằng chứng cho hai câu hỏi: velocity của box nằm ở ego frame hay global frame; và box do `ObjectPaste` tạo có velocity hợp lệ hay phải fallback. Kết quả quyết định cách đặt spray plume.

**Blocked by:** 01

**Status:** ready-for-agent

- [x] Velocity frame được xác nhận từ loader và ghi lại.
- [x] Box từ database sampler được kiểm tra có velocity hay không.
- [x] Fallback policy được chốt: bỏ qua plume hay dùng giá trị mặc định.
- [ ] Có số đếm box eligible với velocity hợp lệ trên một sample. (cần ticket 04)
