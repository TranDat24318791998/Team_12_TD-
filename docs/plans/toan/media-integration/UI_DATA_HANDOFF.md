# Đầu nối media cho owner Data/API/React

Đây là packet tích hợp sản phẩm, tách khỏi MI01–MI04. Hiện root runtime và Data facade đều có business state riêng; nguồn media mới không tự giải quyết xung đột này. Media agent bàn giao ContentService + typed HTTP client + tests, không tạo facade thứ hai để frontend trông như đã nối.

## 1. Các quyết định cần giữ khi ghép facade hiện hành

| Chủ sở hữu | File hiện tại | Sửa cụ thể |
|---|---|---|
| Data/workflow | `data/growth_data/facade.py:decide`, `service.py:apply` | Seller accept chỉ approve proposal; content_refresh=true giữ campaign inactive đến content Apply. Một command publish listing + activate exact approved proposal + receipt trong transaction của nguồn state được chọn. |
| Data/media | `data/growth_data/media.py:content_create` | Cho tạo job từ approved proposal chưa applied; bind proposal/card/brief/draft versions. Không dùng điều kiện applied cũ khiến buộc activate trước content. |
| API owner | State/decision/content routes | Chọn Data transaction làm authoritative cho product app như requirements hiện hành; chuyển agent/runtime qua adapter/handoff đúng state này. Không gọi hai Session accept độc lập. Nếu vẫn đang dùng core headless, UI_PRODUCT giữ PENDING. |
| UI owner | `frontend/src/` và API adapter hiện có | Giữ React; nhận path/status/source/review fields, gửi versions/skip/ack; không gọi media service từ browser. Không sửa bundle build bằng tay. |
| Knowledge/DB owner | Learning handoff | Một feedback event/attempt, cùng negotiation/card IDs; Content chỉ đọc confirmed style. Không chép raw service result vào Learning evidence. |

Không tự quyết định thêm migration/DB thứ hai trong task media. Data owner triển khai business persistence/atomicity theo data design; `experiment/jobs.sqlite3` chỉ là provider-job store, không thay DB nghiệp vụ.

## 2. Projection cần thêm vào facade

Field domain additive theo [CONTRACT](CONTRACT.md) mục4. Serializer chỉ đưa:

- `content_draft`: title/description, version, card_id/brief_version, images option/status/path/source/error, video status/path/source/reference_option/visual_review_passed/review_notes_vi, feedback_history, checks.
- `pending_card.version` và `pending_card.brief_version` từ entity đã phát hành; browser không tự đặt1.
- `media_mode` riêng nếu khác agent mode. `path` là local route được phép đọc của facade; backend không trả absolute path, MinIO endpoint/object credentials hoặc signed URL vào business listing dài hạn.

Body dự kiến (owner cập nhật schema/fixtures/frontend cùng lúc):

```json
{"card_id":"card-fixture","expected_brief_version":1,"expected_draft_version":2,"cover_option":"B","skip_video":false,"video_review_ack":false}
```

Retry giữ body hiện hành trong DEMO_CONTRACT. Decision phải mang expected_card_version/expected_brief_version khi dùng core contract. Data v1 hiện trả422 cho fields này: cần thay adapter/schema/transaction trước khi UI gửi, không chỉ sửa client. Brief confirm endpoint/version hiện còn thiếu ở Data facade; chưa xác nhận brief thì không tạo draft có brief version giả.

## 3. UI behavior cụ thể

- Ba cover riêng status, source live/cache/fixture; media chậm thì progress vẫn đọc được. Video ghi “Từ ảnh A”, không hứa khớp B/C sau seller chọn cover khác.
- Video technical done nhưng visual_review false/null: hiển thị review_notes và checkbox “Tôi đã xem video và đồng ý dùng bản này”; gửi ack chỉ khi người dùng chủ động chọn. Các đường skip dùng checkbox riêng, mặc địnhfalse.
- Video thiếu/hỏng: ack không giúp Apply; seller có thể chọn skip_video để dùng ảnh/chữ. Không đánh dấu completed hoặc phát placeholder như video AI.
- Retry chỉ khi bản hiện tại terminal, không uncertain, v<3 và còn budget; UI reset cover/checkbox khi draft version đổi. HTTP409 → tải state mới và yêu cầu quyết định lại, không tự approve.
- Poll read-only; GET state/event không tạo provider job, không thay default media style hoặc phát sinh học. Reset đổi run/cursor; callbacks run cũ không đi vào UI mới.
- Label brand/giọng/cảnh của media là generated cần seller xem; `visual_review_passed` không được render thành “đúng sản phẩm100%”.

## 4. Product integration gate

Trước UI_PRODUCT PASS phải có một test HTTP xuyên facade thật: approve offer (inactive) → tạo3ảnh/video từ A → retry bright → Apply đúng version (active+listing) → reload đọc lại nguồn state → night → day2 Yes. Test private fields, duplicate apply, callback cũ và video ack/skip. Nguồn market/provider là fake trong test thì label rõ; live smoke riêng.

Bàn giao của MI04 phải nêu chính xác callable/contracts và blockers còn lại. Chưa có test này thì UI_PRODUCT=PENDING dù ảnh/video trong lab đã chạy thật. Không cho agent media phải viết lại toàn bộ Data/API chỉ để xóa chữ PENDING.
