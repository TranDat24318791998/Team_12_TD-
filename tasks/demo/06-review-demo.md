# D06 — Review độc lập và diễn tập

Timebox 9 phút, thêm 10 phút dự phòng. Coder dừng tính năng mới ở phút 101. Reviewer đọc contract/task/diff và caller liên quan, chạy test rồi đi hết UI thật.

## Output

`tests/integration/api/test_demo_flow.py`, `docs/DEMO_RUNBOOK.md`, `docs/CODEX_LOG.md`. Chỉ sửa source trong phạm vi task tương ứng khi có lỗi tái hiện; ghi mã task gốc. Không mở rộng sang production.

## Gate review

| Gate | Bằng chứng | Nếu fail |
| --- | --- | --- |
| Finance | D: 45.000đ/ngày, 3%, stop 6,5; voucher 4% bị chặn | Chặn demo apply |
| Privacy | Prompt capture sàn/trọng tài không có cost, private rules, private_note | Chặn live LLM |
| Agent | Offline D thống nhất lượt 2; tối đa 3 lượt sàn, 12 model calls; referee thực sự được gọi | Sửa graph, không tạo event giả |
| Approval | Accept chưa active; apply kiểm đúng card/brief/draft | Chặn apply |
| Media | POST → task_id → poll → download → phát video; 3 ảnh ready | Chỉ mock thì chưa đạt media thật |
| Version | Callback v1 không ghi đè v2/listing đã publish | Chặn demo retry |
| Memory | Feedback ngày 1 → candidate; Có ngày 2 → rule; đọc lại | Chỉ summary chưa chứng minh learning |
| One-effect | Apply/night lặp không tạo effect lần hai | Sửa state/receipt, không cần queue |
| Honest source | Từng phần hiển thị đúng live/replay/offline | Sửa nhãn trước khi diễn |

Reviewer trả PASS hoặc FIX REQUIRED, kèm input tái hiện, expected/actual, file:line, cách sửa tối thiểu. Multiuser, load, spam, cloud auth và restart recovery ghi DEFERRED theo plan.

## Test tự động

Chạy `.venv/bin/python -m pytest -q` với provider fake. Test chính qua TestClient: reset → confirm brief → start → accept → fake jobs done → retry nền sáng → fake jobs done → apply → night ngày 1 → start ngày 2 → trả lời Có → GET state, assert style đã xác nhận.

Assert active None trước apply, exact package, event ID không trùng, factor giữ 1,0, nguồn fake/offline ghi rõ. Inject clock/sleep; test không chờ thật 240 giây.

## Smoke provider thủ công

Đọc [MUSE_API](../../docs/MUSE_API.md). Khi user đã điền cấu hình, smoke một ảnh OpenAI và một video Muse; lưu task_id, media path local, status. Không log Authorization. Mở file bằng browser player để kiểm phát được, không chỉ HTTP 200. Schema Muse `{}` chưa đủ để chốt parser: lưu response thật đã loại secrets thành fixture rồi kiểm mapping trước live flow.

Nếu còn thời gian/quota, tạo cache bản đầu và bản retry nền sáng. Cache phải đến từ API thật; lúc diễn ghi cached. Không hứa demo 3 phút bao gồm hai video có thể chờ 240 giây mỗi video. Chưa đủ cache thì báo rõ bước nội dung phải chờ provider.

## Script trình diễn

1. Mở localhost:8000, reset seed 42; xác nhận brief tăng đơn, không công khai hard cap riêng.
2. Start. Offline agent: chỉ vào đề xuất sàn 70.000đ/10%, counter shop 45.000đ/3%, trọng tài, code check. LLM live: mô tả output thực, không đòi transcript giống fixture.
3. Hiển thị thẻ, Accept; chỉ ra gói chưa active khi đang review content.
4. Góp ý nền sáng, chờ v2 đủ media. Chọn cover B, xem video và nhãn nguồn thật: từ mô tả hoặc từ ảnh A khi đã xác minh image-to-video. Apply.
5. Hiển thị listing và gói active. Night; chỉ ra preference đang là candidate, chưa thành rule.
6. Start ngày 2, trả lời Có; hiển thị rules_version, style mới, memory_read. Không tuyên bố memory đã tăng doanh thu từ một demo.

## Khi gặp lỗi trên sân khấu

- LLM timeout: hiển thị fallback offline rồi tiếp tục, không dừng demo để debug provider.
- Video đang chờ: hiển thị running, hoặc cache đúng draft nếu có. Seller có thể chủ động skip; không tự duyệt video.
- OpenAI Images chưa cấu hình: báo giới hạn media, không gắn nhãn đã tạo ảnh thành công.
- State cũ: reset demo, không sửa dữ liệu bằng console. Không restart rồi giả định card cũ dùng được khi chưa có resume.

## Bàn giao cuối

Ghi SHA, lệnh test/kết quả, provider thật đã xác minh phần nào, đường dẫn media, cấu hình thiếu, bug đang chặn, mục DEFERRED. Giữ token trong .env; kiểm `git diff --cached` chỉ có tài liệu/code/fixture không chứa secrets. Bản single-session chạy local, không deploy public.
