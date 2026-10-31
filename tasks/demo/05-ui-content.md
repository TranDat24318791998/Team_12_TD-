# [D05] Một màn hình demo và vòng duyệt nội dung

## Kết quả cần đạt

Người bán shop D đi hết ngày 1 và xem câu hỏi sở thích ngày 2 trên một trang HTML.
Gói chưa được kích hoạt khi chỉ mới chấp nhận đề xuất; nội dung được duyệt rồi workflow mới kích hoạt gói.
Phần này phải nối pipeline tạo ảnh/video thật của [D05a](05a-media-api.md); làm bằng fake trong test trước khi có cấu hình thật.
Provider đã chốt: OpenAI cho LLM/ảnh, Muse Gateway cho video. Wire format ảnh đầu vào Muse còn pending trong [MUSE_API](../../docs/MUSE_API.md).
UI phản ánh đúng phần đã chạy; không sử dụng schema `ImageRequest` của Muse làm API ảnh, vì ảnh gọi OpenAI riêng.
Đọc [hợp đồng demo](../../docs/DEMO_CONTRACT.md) trước; tên field/body trong file đó là nguồn chính thức.
Task này không triển khai analytics funnel, chat tự do, 3D, đăng nhập, upload người dùng hoặc queue worker ngoài tiến trình.

## Đầu vào và thứ tự

1. D01 đã có domain models, seed D, formatter và Session.
2. D03 cung cấp API/state và kiểm tra version; D04 cung cấp night/memory.
3. D05a cung cấp `make_covers/make_video` chạy nền; UI dựng bằng JSON fixture trước khi provider có khóa.
4. Khi ghép thật, frontend chỉ lấy state từ backend; bỏ mọi biến tự giả kết quả negotiation/night.
5. Dùng một người code cho runtime/API; task này chỉ nối ContentService qua interface được D03 gọi.

## Output được sửa

| File | Nội dung |
| --- | --- |
| `frontend/index.html` | Một màn hình, khu seller và nhật ký agent |
| `frontend/css/app.css` | Layout và trạng thái hiển thị |
| `frontend/js/app.js` | API helper, state renderer, event handler |
| `app/content/text.py` | Hàm dựng chữ từ thuộc tính đã xác minh |
| `app/content/service.py` | `start/retry/apply`, quản lý bản nháp và callback media |
| `tests/unit/content/test_service.py` | Start/retry/apply và giới hạn bản nháp |
| `tests/integration/api/test_content.py` | Route guard từ D03 ghép ContentService thật |
| `docs/CODEX_LOG.md` | Một dòng về task, test, giới hạn còn lại |

Không sửa model chung hoặc route ở task này; thiếu field thì báo D01/D03 cập nhật DEMO_CONTRACT và fixture cùng lúc.
Không sửa `main.py` nếu đường dẫn static `/`, `/media/` hiện có đã phục vụ được các file trên.

## A. ContentService: làm trước UI

Giữ ba interface hiện có để runtime dùng được ngay:

```python
ContentService(session, *, image_client, video_client, executor)
ContentService.start(shop_id: str) -> ContentDraft
ContentService.retry(shop_id: str, feedback_vi: str) -> ContentDraft
ContentService.apply(shop_id: str, cover_option: str, *, skip_video: bool = False) -> ShopPublic
```

Route/runtime xác minh request version trước khi gọi các method này.
Service lấy approved card và confirmed brief từ Session; không nhận gói hoặc chi phí do browser gửi lại.
Manager truyền executor của app, tối đa 4 worker, vào service; Session chỉ giữ lock ngắn khi cập nhật draft, không cần field executor.
Không giữ lock khi gọi provider/poll/download.
`start` chỉ được gọi sau seller accept; không chạy trong node thương lượng.

### A1. Chữ và thuộc tính

- Public input chỉ gồm title/description/attributes/images của D và style đã xác nhận.
- Fact whitelist D: 3 tốc độ gió, sạc USB, pin 2000mAh, ba màu Trắng/Hồng/Xanh mint.
- Chữ fallback có thể cố định: `Quạt mini cầm tay 3 tốc độ, pin 2000mAh, sạc USB`.
- Mô tả dùng danh sách các fact trên; không tự thêm thương hiệu, bảo hành, thời lượng pin hoặc độ ồn.
- `checks` ghi nguồn thuộc tính; nguồn ảnh/video lấy từ kết quả provider hoặc cache thật, không gắn nhãn AI cho placeholder.
- D01 cung cấp `ContentText(title: str, description: str, checks: list[str])`.
- `write_text(llm, public, style_notes, feedback_history) -> ContentText` gọi OpenAI qua LLMClient của D02 khi có cấu hình; Content Agent là phần bắt buộc.
- Hàm thuần `build_content_text(public, style_notes, feedback_history) -> ContentText` tạo fallback khi thiếu key, timeout, response lỗi hoặc claim ngoài fact whitelist.
- Test text dùng response OpenAI giả; case claim sai phải rơi về fallback có nhãn, không gọi mạng thật.
- Không truyền ShopPrivate, Persona, unit_cost hoặc toàn bộ Session vào prompt nội dung.

### A2. Tạo bản đầu

```text
assert approved card belongs to D and references current confirmed brief
read confirmed rules.content_style_notes through the gateway
build ContentDraft(version=1, images=[A,B,C] running, video=pending, feedback_history=[], style_notes=notes)
bind draft to card_id and brief_version; store draft before starting workers
ids = {run_id, card_id, brief_version, draft_version}; callback captures these four values
make_covers(**ids, shop_id=D, source_bytes=source, source_mime=mime,
            prompts=cover_prompts, client=image_client, executor=executor, on_update=callback)
executor.submit(make_video, **ids, shop_id=D, prompt=video_prompt,
                client=video_client, on_update=callback, image_reference=None)
label initial video source=text_to_video; do not wait on either helper's futures
only after image-to-video reference schema is verified: wait for image A ready before submitting that variant
append content_job for real state transitions; return draft without waiting for media
do not change active package, voucher, stock or metrics
```

- Ba option khác bố cục nhưng cùng sản phẩm đã xác minh; ảnh gốc do team đặt đúng đường dẫn seed trước smoke.
- Callback chỉ cập nhật khi cả bốn ID/version vẫn khớp draft hiện tại; callback cũ chỉ kết thúc worker, không publish.
- Video hiện sinh từ mô tả; nhãn ghi `Chưa xác minh đúng hình dáng sản phẩm`, seller phải xem và duyệt.
- Khi image-to-video đã xác minh, dùng ảnh A của bản hiện tại; A lỗi thì video failed, không chờ hoặc submit nguồn trống.
- Chọn ảnh B/C chỉ đổi cover, không âm thầm tạo video mới có phí.
- Video là phần bắt buộc của demo đầy đủ; chỉ cho bỏ qua khi seller chủ động xác nhận `skip_video=true`.
- Key/model ảnh chưa điền hiển thị `Chưa cấu hình OpenAI Images`; video vẫn chạy bằng mô tả nếu MEDIA_MODE=live và video key hợp lệ.
- Thiếu key video thì hiện lỗi tương ứng; không tạo task_id giả hoặc `done` giả.

### A3. Góp ý và làm lại

- Luồng demo duy nhất cần chứng minh: `Ảnh nền tối quá, làm nền sáng`.
- UI có nút góp ý nhanh điền câu đó vào textarea; vẫn gửi cùng endpoint retry.
- `retry` yêu cầu có draft hiện tại và `version < 3`; tổng cộng bản đầu + hai lần làm lại.
- Thêm góp ý vào `feedback_history`; tăng version đúng một lần; version mới dùng cả rules đã xác nhận và góp ý hiện tại.
- Góp ý chứa `tối` hoặc `sáng` thêm yêu cầu nền sáng vào prompt của bản mới; giữ fact sản phẩm.
- Góp ý khác trả thông báo `Demo hiện hỗ trợ đổi sang nền sáng`; không giả vờ đã hiểu hoặc tự đổi phạm vi.
- Ghi `content_job` gồm feedback, old_version, new_version, card/brief reference để D04 học.
- Góp ý hiện tại không tự thêm `content_style_notes` vào hard rules.
- Retry không chỉnh listing đang hiển thị ngoài khu preview; listing chỉ đổi sau Apply.
- Đang chạy media thì UI khóa retry; sau terminal mới sửa để tránh phí job cũ. Backend vẫn chặn callback version cũ.

### A4. Áp dụng bản đã chọn

```text
assert current approved card and brief still match draft
require cover_option in A/B/C and selected image status in done/cached
require selected local path exists in this run or a registered replay asset
copy draft title/description/selected image to ShopPublic
copy current ready video if skip_video is false; otherwise set public.video=null
append content_applied with version, cover_option and card/brief reference
return updated ShopPublic
```

- `apply` chỉ cập nhật listing; D03 kiểm duyệt đúng bản, video ready hoặc skip rõ ràng, rồi kích hoạt gói trong cùng command.
- Route truyền `skip_video` keyword vào service; chốt bản listing tại thời điểm apply, callback muộn không sửa bản đã publish.
- Nếu validation thất bại, không thay listing và không kích hoạt gói.
- Copy dữ liệu model thay vì chia sẻ list mutable giữa draft và public listing.
- D03 giữ receipt/state để bấm Apply lại không thêm effect; không xây idempotency service tổng quát ở task này.
- Giá bán, giá vốn, rules, tồn kho và ngân sách không thuộc quyền sửa của ContentService.

## B. HTML: dựng đúng các vùng cần demo

- Header: `sàn·demo`, shop D, ngày, mode thực tế; nhãn `Thị trường mô phỏng` luôn nhìn thấy.
- Cột trái: listing trước/sau, brief, thẻ đề xuất, khu duyệt nội dung, tóm tắt tối.
- Cột phải: timeline sự kiện, mỗi dòng có actor, lượt/ngày và message tiếng Việt.
- Desktop dùng hai cột; dưới 800px xếp dọc; không làm nhiều trang hoặc router frontend.
- Dùng button, label, input, textarea, radio thật; chọn ảnh bằng radio A/B/C có alt text.
- Một vùng `role=status` cho trạng thái đang xử lý; một vùng lỗi với câu có thể hiểu được.
- Nội dung từ API hiển thị qua `textContent`; chỉ dùng template HTML cố định cho cấu trúc.
- Tiền dùng `Intl.NumberFormat('vi-VN')` + `đ`; ROAS một chữ số thập phân bằng locale vi-VN.

### B1. Renderer theo step

| `step` | Hiển thị/nút chính |
| --- | --- |
| `idle`, chưa có brief confirmed | Brief mặc định `increase_orders`; nút `Xác nhận mục tiêu` |
| `idle`, day >= 2 và brief confirmed | Brief đã xác nhận; nút `Bắt đầu ngày 2`; không xác nhận lại brief |
| `brief_confirmed` | Brief đã xác nhận; nút `Bắt đầu thương lượng` |
| `negotiating` | Timeline, trạng thái đang xử lý; khóa mutation mới |
| `awaiting_decision`, card offer | Gói, forecast, stop rule; `Đồng ý`, `Thương lượng thêm`, `Từ chối` |
| `awaiting_decision`, card question | Câu hỏi nền sáng; `Có`, `Không`; không vẽ gói null thành gói 0đ |
| `content_review` | Title/description, ba ảnh + trạng thái, video preview, version, góp ý, `Làm lại`, `Áp dụng bản này` |
| `day_done` | Listing/gói thực sự active; nút `Kết thúc ngày và học` |
| `night_done` | NightSummary; nút sang ngày tiếp theo theo hợp đồng D03 |
| `complete` | Kịch bản đã xong; nút reset; không gọi night/start thêm |

`state.step` quyết định màn hình; response một POST không đủ để suy ra các field còn lại.
Sau mọi mutation thành công, gọi `GET /api/state`, cập nhật một biến state rồi render toàn bộ vùng liên quan.
NightSummary cuối ngày vẫn hiển thị khi state đã sang ngày 2 theo DEMO_CONTRACT.
Ngày 2 chỉ hỏi xác nhận style; trả lời Có cập nhật rules và trạng thái candidate, không tự tái tạo nội dung.

## C. JavaScript: ít hàm, không framework

```text
state = null; lastSeq = 0; busy = false; polling = false
api(path, options): fetch JSON, throw error.message_vi on !response.ok
loadState(): state = GET /api/state; render(state)
render(state): call renderBrief/Card/Content/Night and set permitted buttons
mutate(path, body): set busy; POST; await loadState; await loadEvents; finally clear busy
loadEvents(): GET /api/events?after=lastSeq; append unseen seq; use returned last_seq
```

- Ngay khi tải trang: `loadState` và `loadEvents`; chỉ reset khi người dùng bấm reset.
- Poll events mỗi 1 giây trong lúc request start đang chờ; không mở request poll thứ hai nếu cái trước chưa xong.
- Poll state mỗi 2 giây khi còn ảnh/video pending/running; khi media terminal thì dừng timer. Poll đọc không khóa các nút chọn ảnh.
- Mỗi ảnh có status riêng; path null hiển thị placeholder trung tính và câu trạng thái, không link ảnh hỏng.
- Video ready: `<video controls preload="metadata">` dùng URL backend; nhãn nguồn live/cache rõ ràng.
- URL video là file backend đã tải bằng Bearer; browser không gọi trực tiếp Muse Gateway và không nhận key.
- Hiện mode media riêng với mode agent khi khác nhau, ví dụ `Agent offline · Media live`; không lấy LLM_MODE để tắt media.
- Video failed/timeout: hiện lỗi và checkbox `Tôi đồng ý áp dụng chỉ chữ và ảnh, bỏ video ở bản này`.
- Nút Apply cần selected image done/cached và video done/cached, hoặc checkbox skip được chọn rõ ràng.
- Mặc định skip=false; không tự đánh dấu checkbox khi provider lỗi. Mọi trạng thái tạo media đều là dữ liệu server.
- Nếu server đồng bộ chưa trả event sớm, vẫn hiển thị trạng thái chờ; sau response đọc lại toàn bộ event mới.
- Khóa các mutation khi busy là đủ cho demo; lỗi mạng cho phép người dùng thử lại, không vòng auto-retry.
- Dùng `state.pending_card` và `state.content_draft` để lấy IDs/version ở thời điểm bấm nút.
- Body `brief/confirm` copy đúng bảng payload trong DEMO_CONTRACT.
- Decision: `{card_id, expected_card_version, expected_brief_version, action, note_vi, rule_answer}`; action chỉ accept/negotiate/reject trong MVP.
- Retry: `{card_id, expected_brief_version, expected_draft_version, feedback_vi}`.
- Apply: `{card_id, expected_brief_version, expected_draft_version, cover_option, skip_video:false}`.
- Lấy `expected_card_version` từ `pending_card.version`, brief version từ card, draft version từ draft đang hiển thị.
- Không tự tăng version trước response; selected image và checkbox skip reset khi draft đổi version.
- Với `409`: hiện `Phiên bản đã thay đổi, hãy xem lại`, loadState, yêu cầu bấm lại; không auto-approve bản mới.
- Với lỗi khác: giữ bản nháp và feedback đang nhập; hiển thị lỗi, mở lại nút phù hợp.
- Câu hỏi luật dùng `rule_answer=true/false` theo contract; không gọi content retry/apply để xử lý câu hỏi.
- Reset đặt lastSeq=0, xóa timeline và selection của run cũ rồi load state mới.
- Nút proof chỉ xuất hiện nếu báo cáo thực có sẵn; phản hồi chưa có proof thì ghi chưa chạy đối chứng.
- Không dựng biểu đồ CR hoặc nhập số thắng mẫu trong task này.

## D. Kiểm thử và điều kiện bàn giao

Test content bằng Session/fake LLM, không gọi API trả phí:

1. Start trước approval bị chặn; start hợp lệ trả A/B/C running, video pending, version=1 và active vẫn null.
2. Fake callbacks tạo ảnh/video ready; retry nền sáng tạo version=2, giữ fact, lưu feedback và không đổi rules/listing.
3. Version=3 là bản cuối; retry tiếp trả lỗi theo contract và không thay version.
4. Apply option không có/ảnh chưa sẵn sàng bị chặn, không tạo active package.
5. Apply đúng version qua route cập nhật listing và kích hoạt đúng gói; gọi lại không thêm receipt/effect.
6. Callback draft cũ không thay draft mới; rules style đã xác nhận được dùng khi tạo draft mới sau này.
7. Video failed không cho Apply nếu skip=false; skip=true được ghi riêng và không báo video thành công.
8. API chưa cấu hình tạo status failed có lý do; không gọi mạng và không đưa dữ liệu key vào state/event.

Kiểm tra thủ công trong browser ẩn hoặc localhost, không làm gián đoạn màn hình người dùng:

| Thao tác | Bằng chứng phải nhìn thấy |
| --- | --- |
| Reset → xác nhận brief → start | Intent được giữ; timeline có sàn/shop/trọng tài |
| Xem thẻ D | Ads 45.000đ, voucher 3%, ngưỡng 6,5 ở offline chuẩn |
| Đồng ý | Có draft ngay; ảnh/video tiến triển độc lập; gói chưa active, chưa có spend |
| Media hoàn tất | Xem ba ảnh OpenAI và phát video Muse; nhãn text-to-video/live/cache đúng |
| Góp ý nền sáng → retry | Version tăng; prompt nhận nền sáng; media mới; luật phong cách chưa đổi |
| Chọn B → Apply | Listing dùng B, gói active đúng phiên bản, một lần áp dụng |
| Night → ngày 2 | Evidence feedback, candidate sở thích; câu hỏi Có/Không |
| Có ở câu hỏi | Rules hiện nền sáng; không tự tăng chi hoặc thay listing đã duyệt |
| Reload trang | Phục hồi từ state trong tiến trình đang chạy, không tự reset |

Chạy `.venv/bin/python -m pytest -q tests/unit/content tests/integration/api/test_content.py`, sau đó full pytest.
Bàn giao: file đã sửa, lệnh/kết quả test, ảnh chụp ở thẻ D/draft có video/night, các key/model chưa điền và Muse reference schema còn thiếu nếu có.
Nếu thiếu thời gian, giữ layout một cột; cắt animation, chart và chat tự do. Giữ pipeline ảnh/video theo yêu cầu người dùng.
