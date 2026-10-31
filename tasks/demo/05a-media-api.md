# D05a — tích hợp media service hiện có

Cập nhật sau `a0a93f0`: implementation provider nằm trong `experiment/`. Task D05a cũ viết OpenAI/Muse trực tiếp trong app được thay bằng HTTP adapter. Không copy pipeline giữa hai package.

Provider: OpenAI Images; Muse Gateway video. Service endpoint/token và raw gateway endpoint/token khác nhau, xem [MUSE_API](../../docs/MUSE_API.md). Coder phần Toàn bắt đầu tại [media-integration/README](../../docs/plans/toan/media-integration/README.md), thực hiện MI01–MI04 với file ownership và acceptance trong đó.

## Giao diện chung cần đạt

- Service hỗ trợ SKU D handheld_fan, optional logo, bright background; giữ desktop default cho lab cũ.
- Core backend upload/submit/poll qua JSON jobs; bind owner/run/card/brief/draft, nhận output asset A rồi tạo video từ A.
- File thật được tải về đúng media/run; signed URLs không là listing lâu dài. Job done cần checksum/file, source và visual review rõ.
- ContentService giữ start/retry/apply, native Content Agent và seller/version gate. Apply listing rồi activation qua runtime; provider không tự approve/publish.
- MEDIA_MODE độc lập LLM_MODE. Service dùng env/môi trường riêng, browser không giữ token.
- 3ảnh +1video5giây ở draft đầu;2retry tối đa; budget/reservation/idempotency theo [contract](../../docs/plans/toan/media-integration/CONTRACT.md).

## Trạng thái bàn giao

Source/test provider đã có; cần chạy lại ở môi trường người nhận, sửa desk-fan assumptions và nối core. Input ảnh D chưa có trong assets/products, OpenAI key/MinIO credentials còn trống. Báo live NOT_RUN khi thiếu, hoàn tất code với fake đúng contract; không suy ra đã có live từ token hoặc README máy nguồn.

Data/API/UI không bị thay thế bởi service media. Packet owner nhận ở [UI_DATA_HANDOFF](../../docs/plans/toan/media-integration/UI_DATA_HANDOFF.md). Không dùng Data accept cũ kích hoạt campaign trước content rồi coi approval gate đã đạt.
