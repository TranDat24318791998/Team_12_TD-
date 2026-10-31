# Provider video cho demo

Người dùng chốt ngày 31/10/2026: OpenAI cho agent/text/learning/ảnh; Muse Gateway chỉ tạo video. Đây là hướng dẫn implementation; chưa tạo job thật trong lượt lập plan.

Base URL: `https://muse-api.butterflyro.space`.

Nguồn: [Swagger UI](https://muse-api.butterflyro.space/docs#/), [OpenAPI JSON](https://muse-api.butterflyro.space/openapi.json). Bản public đã đọc lưu tại [reference/muse-gateway-openapi.json](reference/muse-gateway-openapi.json), title Muse API Gateway, version 0.1.0.

## Cấu hình backend

```dotenv
MUSE_API_BASE_URL=https://muse-api.butterflyro.space
MUSE_API_KEY=
MUSE_VIDEO_MODEL=muse-video
MEDIA_MODE=live
OPENAI_API_KEY=
LLM_MODEL=
LLM_MODEL_REFLECT=
OPENAI_IMAGE_MODEL=
```

Token Muse đã lưu trong .env được Git bỏ qua, quyền 0600; không chép token vào tài liệu. D01 thêm field cần thiết vào Settings, che muse_api_key trong describe/repr. OpenAI key/model sẽ điền sau. MEDIA_MODE độc lập LLM_MODE; Settings mặc định offline, .env local do operator chọn live.

## Endpoint đã xác minh trong schema

| Bước | HTTP | Hợp đồng |
| --- | --- | --- |
| Health | GET /healthz | 200 chỉ chứng minh tiến trình đang chạy; không kiểm Muse session/quota/key |
| Submit | POST /v1/videos | Bearer ClientKey, Idempotency-Key tùy chọn; VideoRequest JSON; mô tả trả 202/task_id |
| Poll | GET /v1/videos/{task_id} | Bearer cùng key; mô tả progress/completed/failed; response chưa có schema cụ thể |
| Download | GET /v1/media/{name} | Bearer cùng key; backend tải bytes rồi lưu media local |

OpenAPI có ImageRequest/ChatRequest trong components nhưng không công bố route ảnh/chat tương ứng. Không suy ra endpoint từ tên schema. Ảnh dùng OpenAI. Gateway không dùng api.useapi.net, MUSE_EMAIL, /assets, /jobs/video hoặc jobid của task 4.4 cũ.

## Submit body

```json
{
  "model": "muse-video",
  "prompt": "Create a mini fan product video from this description. Bright background, slow camera movement, no added product claims or logo.",
  "duration": 10,
  "aspect_ratio": "9:16",
  "resolution": "720p",
  "timeout": 240
}
```

prompt là field duy nhất bắt buộc, dài 1–32.000 ký tự. duration nhận 1–120 và là chỉ dẫn; output thực tế do Muse quyết định. timeout nhận 1–1800.

Schema của image/images/image_url chưa có kiểu đầy đủ; reference_image là string. Chưa xác minh gateway nhận local path, data URL hay public URL. Khi bật image-to-video, kiểm định dạng được chấp nhận bằng một ảnh seller đã duyệt rồi ghi fixture. Không gửi filesystem path local với giả định provider đọc được.

Request trên là text-to-video để kiểm transport khi chưa có reference. Output phải ghi `Video sinh từ mô tả; chưa xác minh đúng hình dáng sản phẩm` và được seller review; không giả định giữ đúng quạt nguồn.

## Adapter cụ thể

```python
MuseClient(base_url, api_key, http=None)
MuseClient.create_video(prompt, *, idempotency_key, image_reference=None) -> str
MuseClient.poll_task(task_id) -> VideoPoll
MuseClient.download_media(name) -> bytes
```

create_video trả task_id. VideoPoll là DTO nội bộ dùng thống nhất với D05a:

```python
status: Literal["running", "done", "failed"]
output_media_name: str | None
error_vi: str | None
```

Normalize queued/pending của provider thành running, completed thành done. Chốt mapping media từ response thật/fixture đã xác minh. Schema hiện là `{}`; không lấy parser result.assets[0].assetId từ provider cũ.

Mô tả POST nói 202 nhưng response map khai báo 200. Nhận 200/202, validate task_id không rỗng rồi lưu ngay. Poll mỗi 5 giây, deadline tổng 240 giây dùng monotonic clock; HTTP timeout 20 giây/request. Status chưa biết tiếp tục poll trong deadline và hiển thị đang chờ. Thiếu task_id hoặc thiếu media ở terminal trả ProviderProtocolError, không báo done.

Idempotency key ổn định theo run/card/brief/draft/prompt digest. Không POST lại khi chưa biết kết quả lần submit trước; có task_id thì chỉ poll. Header tùy chọn chưa mô tả đầy đủ dedup, vì vậy không khẳng định provider bảo đảm exactly-once.

Download chỉ gửi Bearer tới origin gateway cấu hình. Media URL phải cùng origin và thuộc /v1/media/; không chuyển token sang CDN/host khác/redirect. Lưu `media/<run>/D-<card>-v<version>.<ext>` với đuôi đúng format thực. Browser nhận /media/..., không nhận Authorization. Chỉ báo done sau khi tải xong file hợp lệ.

## Test và smoke

- httpx.MockTransport: submit 202/task_id, poll running → completed, download bytes, failed, response thiếu field.
- Kiểm không submit lại khi đã có task_id; logs không chứa secrets; callback cũ bị bỏ; download tới host khác bị chặn.
- Job thủ công đầu tiên lưu response đã loại secrets vào tests/fakes/fixtures/muse_*.json, rồi hoàn thiện parser đúng envelope. Fixture không chứa token.
- Chưa gọi create video trong lúc lập plan. Health check không chứng minh tạo video được; gateway không dùng làm provider ảnh/LLM.
