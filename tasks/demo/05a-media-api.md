# [D05a] API ảnh/video thật và callback vào bản nháp

## Mục tiêu và phụ thuộc

Sau khi seller chấp nhận gói, tạo ba ảnh A/B/C bằng API ảnh và một video bằng API video, cập nhật trạng thái lên UI.
Đây là luồng bắt buộc theo yêu cầu người dùng: ảnh và các LLM dùng OpenAI; video dùng `https://muse-api.butterflyro.space`.
Ảnh dùng `OPENAI_API_KEY` + `OPENAI_IMAGE_MODEL`, được để trống đến khi operator điền. Không gửi ảnh hoặc LLM sang Muse.
Đọc [DEMO_CONTRACT](../../docs/DEMO_CONTRACT.md), [MUSE_API](../../docs/MUSE_API.md), [D05](05-ui-content.md).
Task cũ 4.3/4.4/4.5 chỉ giữ phân chia module; bỏ toàn bộ wire format `useapi.net`, upload assets và jobs/video cũ.
Không gọi provider có phí trong lúc viết plan hoặc trong pytest.

## Output

| File | Trách nhiệm |
| --- | --- |
| `app/infrastructure/images.py` | OpenAI Images adapter; trả bytes, không biết Session |
| `app/infrastructure/muse.py` | Adapter gateway video; create/poll/download, không biết UI |
| `app/content/images.py` | Ba phương án, prompt, cache, lưu file và callback |
| `app/content/video.py` | Tạo/poll video, cache, deadline và callback |
| `app/content/prompts.py` | Prompt sản phẩm + style + feedback có giới hạn |
| `app/core/settings.py`, `.env.example` | Chỉ thêm field thực sự cần cho provider đã xác định; values mẫu để trống |
| `tests/fakes/media.py` | Fake image/video clients và fake clock |
| `tests/unit/content/test_media.py` | Pipeline media không gọi mạng |
| `tests/unit/infrastructure/test_media_clients.py` | MockTransport cho wire format đã xác minh |
| `scripts/check_media.py` | Smoke chủ động một ảnh + một video, chỉ chạy khi operator yêu cầu |
| `docs/CODEX_LOG.md` | Provider, mode, test và kết quả smoke thật nếu đã chạy |

Không sửa route/runtime chung; ContentService trong D05 nhận adapter và callback, D03 giữ approval gate.
Giữ một adapter cho mỗi provider team thực sự dùng, không viết framework plugin hoặc dò nhiều SDK.

## A. Chốt cấu hình mà không chặn việc code

1. Dùng `httpx` hiện có cho Muse Gateway; `Authorization: Bearer <MUSE_API_KEY>` ở backend.
2. Settings: `MUSE_API_BASE_URL`, `MUSE_API_KEY`, `MUSE_VIDEO_MODEL=muse-video`, `MEDIA_MODE=live|replay|offline`.
3. `MEDIA_MODE` mặc định offline trong code; `.env` local được operator đặt live. Media mode độc lập `LLM_MODE`.
4. Key/model còn trống phải được nhận biết thành `ProviderNotConfigured`, không thử gọi mạng; không tự chọn model khác.
5. Settings không in key hoặc URL có query secret; state/event chỉ ghi `image_provider`, `video_provider`, mode và error code.
6. `.env.example` giữ key rỗng; `.env` của operator được Git bỏ qua. Không ghi token thật vào test fixture hoặc CODEX_LOG.

Ảnh: `IMAGE_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL`. Video tái sử dụng `MAX_VIDEO_JOBS_PER_SESSION`; gateway không dùng `USEAPI_TOKEN`, `MUSE_EMAIL` hoặc OpenAI key.
Đường dẫn đã xác minh: `GET /healthz`, `POST /v1/videos`, `GET /v1/videos/{task_id}`, `GET /v1/media/{name}`.
`/healthz` chỉ kiểm tiến trình gateway, không xác nhận tài khoản Muse hoặc quyền tạo video.
Schema `ImageRequest` của Muse không phải route: không tự gọi endpoint ảnh trên gateway. OpenAI Images dùng client OpenAI riêng.
Ảnh có adapter thật ngay từ task này, test bằng fake SDK; điều kiện còn thiếu có thể là key/model/source image, không phải provider chưa xác định.

Request text-to-video theo OpenAPI:

```json
{"prompt":"Video mô tả quạt mini theo brief đã duyệt","model":"muse-video","duration":10,"aspect_ratio":"9:16","resolution":"720p","timeout":240}
```

Duration/resolution là chỉ dẫn, provider quyết định output thực. `image`, `image_url` không có kiểu đầy đủ; chưa tự gửi base64/URL local.
OpenAPI mô tả submit trả 202 nhưng response schema khai báo 200 `{}`: nhận cả 200/202, yêu cầu task ID hợp lệ.
Poll response không có schema cụ thể: capture một response thật đã làm sạch rồi chốt parser; không đoán `result.assets[0]`.
Nguồn công khai: [Swagger](https://muse-api.butterflyro.space/docs#/) và [OpenAPI](https://muse-api.butterflyro.space/openapi.json).

## B. Interface nội bộ nhỏ

Đây là interface Python của ứng dụng, không phải tên endpoint nhà cung cấp:

```python
ImageClient.generate(source_bytes: bytes, source_mime: str, prompt: str) -> bytes
MuseClient.create_video(prompt: str, *, idempotency_key: str, image_reference=None) -> str
MuseClient.poll_task(task_id: str) -> VideoPoll
MuseClient.download_media(name: str) -> bytes

make_covers(*, run_id: str, card_id: str, brief_version: int, draft_version: int,
            shop_id: str, source_bytes: bytes, source_mime: str,
            prompts: dict[str, str], client: ImageClient, executor, on_update) -> None
make_video(*, run_id: str, card_id: str, brief_version: int, draft_version: int,
           shop_id: str, prompt: str, client: MuseClient, on_update,
           image_reference=None) -> VideoJob
```

- `make_covers` không blocking: schedule đúng ba task A/B/C rồi trả None. `prompts` có đúng ba key A/B/C.
- `make_video` blocking trong một worker: create/poll/download rồi trả VideoJob terminal, gửi on_update ở các bước. ContentService gọi bằng executor.submit đúng một lần; helper không submit hoặc đợi future trên cùng pool.
- Helpers capture đủ run/card/brief/draft identity và gửi lại callback; không cần thêm Session hoặc executor vào video client.
- `VideoPoll`: `status: Literal["running", "done", "failed"]`, `output_media_name: str | None`, `error_vi: str | None`.
- Adapter normalize queued/pending thành running, completed thành done; service không đọc raw JSON provider.
- `image_reference=None` dùng text-to-video; kiểu truyền ảnh chỉ được bật sau khi xác minh wire format thật.
- Submit gửi `Idempotency-Key` ổn định theo run/card/brief/version/video; lưu task_id ngay khi nhận, không tạo key mới khi thử lại cùng command.
- Media phải tải bằng Bearer ở backend rồi lưu file local; browser chỉ nhận `/media/<run_id>/...`, không token hoặc URL gateway cần auth.
- Chỉ download từ route media cùng gateway đã cấu hình; response URL lạ không được nhận Bearer.
- Timeout mỗi HTTP call hữu hạn; video polling có tổng deadline riêng, cấu hình mặc định 240 giây.
- Poll interval mặc định 5 giây hoặc tối thiểu provider công bố, chọn giá trị đã xác minh.
- Submit trả lỗi thì failed; timeout không rõ đã submit hay chưa thì không tự submit lại để tránh tạo hai job có phí.
- Retry chỉ một lần cho lỗi GET poll/download tạm thời; không xây exponential retry hoặc queue phân tán.
- Giữ `job_id` từ lúc submit thành công; server có thể hiển thị status sau khi browser reload trong cùng process.

## C. Ảnh: ba job độc lập

Đã kiểm chữ ký SDK `openai==3.42.0` trong `.venv`: có `client.images.edit(image=..., prompt=...)` và `client.images.generate(prompt=...)`.
Tạo client với `OpenAI(api_key=settings.openai_api_key, timeout=120.0, max_retries=0)`; timeout media riêng với timeout LLM ngắn.
Implementation OpenAI adapter cho mỗi option:

```python
result = client.images.edit(
    model=settings.openai_image_model,
    image=("source.png", source_bytes, source_mime),
    prompt=prompt, n=1, output_format="png", size="1024x1024",
)
if not result.data or not result.data[0].b64_json:
    raise ProviderProtocolError("API ảnh không trả nội dung ảnh")
return base64.b64decode(result.data[0].b64_json, validate=True)
```

Chọn filename khớp MIME ảnh nguồn; đoạn trên minh họa PNG. Với GPT Image, bỏ `response_format` legacy; base64 là output mặc định.
P00 cần ảnh nguồn tồn tại. Nếu chưa có, operator cung cấp hoặc chạy `images.generate` một lần tạo seed giả lập có nhãn, rồi ba edit dùng lại seed đó.
Không tự tạo lại ảnh nguồn trong mỗi option/version; không gọi generate thay edit khi đã có ảnh nguồn.
Tham chiếu: [OpenAI image edit](https://developers.openai.com/api/reference/python/resources/images/methods/edit) và [image generate](https://developers.openai.com/api/reference/python/resources/images/methods/generate).

1. ContentService đã lưu draft hiện hành trước khi schedule jobs trên ThreadPoolExecutor tối đa 4 worker.
2. Input gồm run/shop/card/brief/draft identifiers, source image bytes, verified facts, style và feedback.
3. A: cầm trên tay; B: trên bàn; C: bố cục pastel. Cả ba giữ hình dáng/màu sản phẩm, không thêm chữ/logo.
4. Không ép mọi bản đầu nền tối chỉ để kể chuyện học; feedback nền sáng vẫn hợp lệ nếu seller muốn sáng hơn.
5. Cache key = SHA256(source bytes + prompt + provider + model + size/config); không dùng riêng version làm key.
6. Cache hit chỉ hợp lệ khi file tồn tại và đúng loại; callback `cached` với đường dẫn thực.
7. Cache miss gọi adapter ảnh, kiểm kết quả không rỗng và MIME hợp lệ rồi lưu vào file tạm, rename khi đủ bytes.
8. Đường dẫn đích `media/<run_id>/D-v<version>-<option>.<ext>`; ext theo format thực của provider.
9. Callback `done` chỉ sau khi file thật đã tồn tại; callback lỗi có status failed và error tiếng Việt ngắn.
10. Nếu dùng ảnh gốc để preview khi lỗi, giữ status failed và nhãn ảnh gốc; không đổi thành cached/generated.

Không giữ session lock trong thời gian gọi API. Callback lấy lock, kiểm current run/card/brief/version, cập nhật một option và ghi event.
Reset hoặc retry làm callback cũ bị bỏ qua; worker được phép kết thúc nhưng không thay draft mới hoặc publish.
Không chờ cả ba ảnh mới cập nhật UI; option xong trước được hiển thị trước.

## D. Video: text-to-video trước, gắn ảnh sau khi xác minh

```text
confirmed content brief -> compare current draft identity -> check video not already submitted
capture style + feedback + script; source=text_to_video while image reference contract is pending
cache hit -> video=cached with real MP4; finish
reserve one video budget slot under lock; release lock
POST /v1/videos once with stable Idempotency-Key -> save task_id
GET /v1/videos/{task_id} every 5 seconds until terminal or 240-second deadline
GET /v1/media/{name} with Bearer -> validate bytes -> save local file -> callback done
```

- Text-to-video chạy độc lập khi OpenAI còn đang tạo ảnh; UI ghi `Video sinh từ mô tả; chưa xác minh đúng hình dáng sản phẩm`.
- Seller phải xem và duyệt video đó; không tuyên bố text-to-video giữ nguyên sản phẩm trong ảnh gốc.
- Sau khi image-to-video wire format được xác minh, mới đợi ảnh A done/cached rồi truyền reference đúng schema; A lỗi thì video failed rõ nguyên nhân.
- Prompt ngắn: sản phẩm quạt mini, chuyển động camera nhẹ, đúng brief, không lời hứa ngoài fact whitelist.
- Độ dài/tỷ lệ/âm thanh theo tham số API đã xác minh; không quảng cáo 10 giây/720p nếu provider không đảm bảo.
- Lưu `media/<run_id>/D-v<version>.mp4`; nếu provider trả format khác, giữ format thực và báo UI tương ứng.
- Video cache key gồm generation kind, bytes ảnh nguồn nếu có, prompt/script, provider, model và thông số render.
- Giới hạn ba video submit thật/session bằng cấu hình sẵn có; vượt hạn mức dùng cache đúng input hoặc failed.
- Không lấy video gần nhất không khớp brief rồi giả là bản mới; video replay khác input cần được gắn rõ là fallback và seller chấp nhận.
- Khi timeout, đánh dấu failed và giữ job_id trong event; không tạo job thay thế tự động.
- Chọn cover B/C không tự thay video: UI ghi video từ mô tả hoặc ảnh A để seller duyệt đúng nội dung thực.
- Không ghi progress phần trăm giả; chỉ pending/running/done/cached/failed và thông báo bước đang làm.

## E. Nối với D05 và D03

- Callback payload nội bộ: run_id, shop_id, card_id, brief_version, draft_version, kind, option?, status, path?, job_id?, error_vi?.
- `content_job` events lưu ID/version, bước và kết quả; không serialize request auth hoặc provider JSON nguyên khối.
- ContentService chỉ cập nhật draft; không gọi apply hoặc tự tăng ngân sách sau callback done.
- D03 `/content/apply` kiểm card_id, expected_brief_version, expected_draft_version, image đã chọn ready, video ready hoặc seller `skip_video=true`.
- Khi người bán skip video, lưu quyết định skip; late callback không tự gắn video vào listing đã publish.
- UI poll `/api/state`; không cần websocket, task queue, webhook hoặc trình duyệt gọi provider trực tiếp.
- Khi `MEDIA_MODE=offline/replay`, không gọi provider có phí. Replay chỉ dùng cache đã ghi thật; thiếu thì hiện failed/config status.
- `LLM_MODE=offline` không tắt video nếu `MEDIA_MODE=live`; text agent và media có mode độc lập.

## F. Test tối thiểu

| Test | Kết quả bắt buộc |
| --- | --- |
| Config trống | ProviderNotConfigured, zero request, UI nhận lỗi an toàn |
| 3 fake image jobs | A/B/C cập nhật độc lập; lưu file trước callback done |
| Video submit | Một POST/task cho cùng draft/key, nhận 200 hoặc 202, lưu task_id |
| Response poll không hợp schema đã xác minh | ProviderProtocolError rõ ràng, không tự đoán URL hoặc báo done |
| MEDIA_MODE vs LLM_MODE | Live media vẫn chạy với offline text; media offline zero paid request |
| Cache cùng input | Không gọi provider; file tồn tại; status cached |
| Feedback mới | Prompt/cache key đổi; bản cũ không ghi đè bản mới |
| Video running → done | job_id giữ nguyên; tải file; UI phát được fixture video hợp lệ |
| Poll timeout/error | Terminal failed, không tự submit job mới |
| Reset/retry trước callback | Không thay draft/run hiện hành và không publish |
| Hết video budget | Không gọi create job; fallback đúng trạng thái |

Wire test dùng `httpx.MockTransport`, fixture lấy từ response schema đã xác minh; fake clock bỏ thời gian sleep thật.
Chạy `.venv/bin/python -m pytest -q tests/unit/content/test_media.py tests/unit/infrastructure/test_media_clients.py`.
Smoke thật đầu tiên: text-to-video → capture sanitized submit/poll envelope → tải media bằng Bearer → phát localfile; ghi generation_kind rõ.
Smoke OpenAI ảnh chạy sau khi operator điền key/model và có source; image-to-video Muse còn cần xác minh reference schema riêng.
Hạn mức/chi phí smoke theo API người dùng cung cấp; không lặp submit để thử cho đẹp.
Điều kiện xong toàn task: fake tests qua và live smoke có kết quả thật; nếu thiếu config, bàn giao rõ `code ready, live unverified`.
