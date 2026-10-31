# D05 — ghép Content và giao diện hiện hành

Cập nhật sau source media `a0a93f0`. Frontend hiện là React trong frontend/src; dùng [FRONTEND_REQUIREMENTS](../../docs/FRONTEND_REQUIREMENTS.md) và [FRONTEND_DATA_REQUIREMENTS](../../docs/FRONTEND_DATA_REQUIREMENTS.md). Bản task HTML/JavaScript thuần cũ đã được thay thế; không dựng thêm giao diện thứ hai.

## Đầu nối với Toàn

ContentService + HTTP media adapter do [MI01–MI04](../../docs/plans/toan/media-integration/README.md) triển khai. Native `app.agents.content.generate_content` đã có; không thay tool loop bằng gọi text model riêng trong React hoặc facade.

Shared runtime/media decisions ở [DEMO_CONTRACT](../../docs/DEMO_CONTRACT.md). Payload, product identity, local asset, review ack và callback version theo [media CONTRACT](../../docs/plans/toan/media-integration/CONTRACT.md); đây là planned extension tới khi code/schema/fixtures được cập nhật cùng nhau.

## Owner Data/API/UI phải làm

Thực hiện [UI_DATA_HANDOFF](../../docs/plans/toan/media-integration/UI_DATA_HANDOFF.md):

1. Facade chỉ có một nguồn business state. Seller accept duyệt proposal; content_refresh chờ content Apply mới activate. Sửa điều kiện Data content_create đang yêu cầu applied.
2. State trả card/brief/draft version thật; mutation kiểm đúng version trong transaction. Brief được seller xác nhận, không tự điền version mẫu.
3. ContentDraft có ảnh A/B/C với path/status/source và video từ A. Field path là route asset hợp lệ, không local filesystem path/token/MinIO URL.
4. UI poll state read-only; disable mutation khi pending; stale409 tải lại state, không tự duyệt bản mới.
5. Retry nền sáng tạo version tiếp theo, giữ3attempt tổng. Apply chọn cover, skip_video hoặc video_review_ack đúng trạng thái, checkbox mặc địnhfalse.
6. Media status done không là seller approval. Video review false/null cần người bán xác nhận sau khi xem; missing file không được vượt gate bằng ack.
7. Content feedback event đúng negotiation/card/version để Learning tạo candidate. Seller Yes ngày sau mới đổi Rules; video/ảnh đã publish không tự đổi theo rule mới.

## Acceptance

Test xuyên facade thật: approve inactive → content/retry → Apply active+listing một lần → reload đúng state → night → day2 question. Test stale callbacks, duplicate Apply, source/cache labeling, ack/skip và privacy. Tests fake không gọi paid API; live media kiểm riêng.

Bàn giao CORE_MEDIA, MEDIA_LIVE và UI_PRODUCT riêng. Nếu service/core media đã chạy nhưng facade/state chưa nối, UI_PRODUCT=PENDING; không dùng lab hoặc mock API làm bằng chứng sản phẩm đã tích hợp. Nhật ký theo workstream owner, không chép lịch/prompt riêng của Toàn vào tài liệu chung.
