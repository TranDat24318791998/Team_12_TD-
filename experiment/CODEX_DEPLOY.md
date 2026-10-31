# Hướng dẫn Codex triển khai lại experiment

Tài liệu dành cho Codex ở tài khoản/máy mới. Đọc toàn bộ trước khi chạy. Mọi lệnh bên dưới chạy từ thư mục `Team_12_TD-/experiment`, trừ khi nói khác. Không cần lịch sử chat trước.

## 1. Mục tiêu và phạm vi

Triển khai dịch vụ độc lập:

```text
Website / agent → backend proxy → Cloudflare → FastAPI :8010
                                             ├─ OpenAI: tạo ảnh, đọc ảnh, viết script/prompt
                                             ├─ Muse Gateway: tạo video
                                             └─ MinIO :9000: lưu JPG/MP4
Website ← signed image_url/video_url ← FastAPI đọc MinIO
```

Không dùng Ollama. Pipeline chính không cần GPU hoặc tải model Hugging Face. Không sửa app chính ngoài experiment; đọc `../AGENTS.md` trước khi làm. Không lấy code từ project `videomarketing` khác.

Bốn style ảnh: `clean_white`, `pastel_lifestyle`, `premium_studio`, `summer_fresh`. Hai loại video: `chibi_3d`, `realistic_human`. Thời lượng Muse: 5, 10 hoặc 15 giây. Một video quảng cáo đúng một mẫu quạt để bàn.

## 2. Đảm bảo nhận đủ source

Kiểm tra `git status --short` ở repo gốc. Ở máy tạo bản hướng dẫn, `experiment/` từng là thư mục untracked: clone/pull GitHub chưa chắc có nó. Nếu thiếu, yêu cầu chủ dự án chuyển source hoặc commit/push trước; không tự giả định đã có trên remote.

Cần có: `video_api/`, `muse/muse_client.py`, `scripts/`, `web/`, `tests/`, `requirements.txt`, `.env.example`, `examples/sites-proxy.ts`, tài liệu này.

Không chuyển `.venv` giữa máy. `.env`, `muse/.env`, `data/` bị Git ignore. Ảnh/video mẫu và SQLite không tự đi theo clone. Nếu cần dữ liệu cũ, sao lưu riêng khi API và MinIO đã dừng; giữ nguyên bản gốc. SQLite lưu đường dẫn asset tuyệt đối: chuyển máy cần cập nhật đường dẫn hoặc tạo asset mới. Không trỏ DB cũ vào MinIO rỗng.

## 3. Cài môi trường

Bản hiện tại đã chạy bằng Python 3.12 trên macOS ARM64. Dùng Python 3.12 và requirements ghim sẵn:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests -q
```

Có thể dùng `uv venv --python 3.12 .venv` và `uv pip install --python .venv/bin/python -r requirements.txt` nếu máy có uv. Không tự hạ version khi lỗi; báo package/version lỗi và kiểm tra registry/môi trường.

Cần executable `minio` và `cloudflared` trong PATH. Trên máy macOS hiện tại chúng nằm trong `/opt/homebrew/bin`. Nếu chưa có, kiểm tra hướng dẫn cài hiện hành từ nhà cung cấp hoặc registry chính thức; bản Homebrew trên máy nguồn từng cài bằng `brew install minio cloudflared`. Khả năng cung cấp MinIO có thể đổi, không tải binary từ nguồn không xác định. Linux cần cài binary phù hợp hệ điều hành. Windows nên chạy môi trường Linux/WSL vì code dùng `fcntl` và shell scripts.

FFmpeg được cung cấp qua `imageio-ffmpeg`. Không cần cài bộ model local. Nếu dùng renderer cũ trên Linux, đổi `FONT_PATH` sang font thật trên máy.

## 4. Tạo cấu hình và secrets

```sh
.venv/bin/python scripts/init_config.py
```

Script tạo `.env` quyền 600, sinh `VIDEO_API_TOKEN`, `PLAYBACK_SECRET`, credentials MinIO; không ghi đè `.env` đã có. Nếu `.env` có sẵn nhưng thiếu token, bổ sung bằng công cụ sinh secret cục bộ, không xóa cấu hình cũ.

Yêu cầu chủ dự án điền key trực tiếp vào `.env`, không gửi key qua chat và không in file này trong tool output:

| Biến | Cấu hình |
| --- | --- |
| OPENAI_API_KEY | Key OpenAI có credit/quyền model |
| OPENAI_TEXT_MODEL | Model text/vision hỗ trợ structured output; giá trị hiện tại trong `.env.example` |
| OPENAI_IMAGE_MODEL | Model hỗ trợ Images edits với nhiều ảnh, JPEG |
| MUSE_API_KEY | Key gateway Muse do team cung cấp |
| MUSE_API_BASE_URL | Gateway hiện tại `https://muse-api.butterflyro.space`; xác minh với team nếu thay đổi |
| MUSE_VIDEO_MODEL | `muse-video` theo gateway hiện tại |
| VIDEO_API_TOKEN | Token riêng để gọi FastAPI; không phải OpenAI key |
| PLAYBACK_SECRET | Secret ký link; ít nhất 24 ký tự |
| STORAGE_BACKEND | `minio` |
| MINIO_ENDPOINT | `localhost:9000` |
| MINIO_SECURE | `false` cho MinIO HTTP local |
| MINIO_ACCESS_KEY / MINIO_SECRET_KEY | Trùng credentials server MinIO |
| MINIO_BUCKET | `marketing-videos` |
| MINIO_CREATE_BUCKET | `true` khi cần API tự tạo bucket |
| DATA_DIR | `./data` |
| PUBLIC_BASE_URL | Điền URL tunnel mới ở bước sau |
| CORS_ORIGINS | `*` theo yêu cầu cho phép mọi website |
| PLAYBACK_TTL_SECONDS | `3600` mặc định |
| LOCAL_MOTION_ENABLED | `false` |

Settings ưu tiên biến môi trường không rỗng > `.env` > `muse/.env`. Nếu key/model không đúng dù đã sửa `.env`, kiểm tra biến môi trường đang ghi đè nhưng không in giá trị key. Cần quyền model thực tế trong tài khoản mới; không tự đổi provider hoặc dùng model khác rồi báo là cùng kết quả.

## 5. Chạy ba tiến trình

Mỗi lệnh ở terminal riêng, đều từ experiment:

**Terminal A — MinIO:**

```sh
.venv/bin/python scripts/start_minio.py
```

MinIO API `http://127.0.0.1:9000`; console `http://127.0.0.1:9001`. Đăng nhập bằng `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` trong `.env`. Log ở `data/minio.log`, object ở `data/minio/`. Nếu cổng bị chiếm, xác định dịch vụ đang chạy; không kill hoặc chạy thêm instance tùy tiện. Với MinIO có sẵn, cấu hình endpoint/credentials tương ứng, không chạy script local.

**Terminal B — FastAPI:**

```sh
sh scripts/start_api.sh
```

Chạy một worker ở `127.0.0.1:8010`. Không chạy nhiều process cùng `DATA_DIR`: SQLite queue có khóa `worker.lock`. Health `http://127.0.0.1:8010/health`, lab `/`, Swagger `/docs`.

**Terminal C — Cloudflare:**

```sh
sh scripts/start_tunnel.sh
```

Lấy URL HTTPS thực tế cloudflared in ra. Ghi URL đó vào `PUBLIC_BASE_URL` trong `.env`, không có dấu `/` cuối. Khởi động lại FastAPI sau khi sửa env, giữ nguyên tunnel. Không dùng lại URL `trycloudflare.com` trong chat cũ: quick tunnel thay URL khi tạo lại.

Chỉ tunnel FastAPI, không tunnel console MinIO. Giữ ba tiến trình chạy để link hoạt động. Quick tunnel dành cho demo; nếu cần URL ổn định, cấu hình named tunnel/domain do chủ dự án sở hữu theo tài liệu Cloudflare hiện hành. Không tự thay DNS/tài khoản khi chưa có thông tin.

## 6. Xác thực, CORS và MinIO

- API riêng: `Authorization: Bearer <VIDEO_API_TOKEN>`.
- Mỗi POST tạo job: `Idempotency-Key` dài 8–120 ký tự. Giữ nguyên key khi retry cùng yêu cầu; key mới có thể phát sinh thêm phí.
- `X-Owner-ID` mặc định `local-demo`. Khi tích hợp website, backend xác thực người dùng và tự suy ra owner; không tin owner do browser tự gửi.
- `CORS_ORIGINS=*`: API và media hỗ trợ cross-origin; preflight cho phép mọi method/header, cookie credentials không bật. CORS không bỏ Bearer hoặc chữ ký URL.
- Các URL ảnh/video public có `expires` và `signature`, không cần Bearer. Khi hết hạn, GET job có xác thực để lấy link mới.
- `minio_uri` (`s3://bucket/key`) là vị trí object. `minio_url` trỏ MinIO nội bộ/private, không phải link anonymous public. Website phải dùng `image_url`/`video_url` qua tunnel.
- Không nhúng OpenAI/Muse key hoặc service token vào website public. Dùng backend proxy; xem `examples/sites-proxy.ts` và gắn cơ chế xác thực thật của website.

## 7. API và quy trình test thật

Mở `/docs`, bấm Authorize bằng **VIDEO_API_TOKEN**. OpenAPI mô tả field chính xác. Test trả phí cần nằm trong yêu cầu đã được chủ dự án cho phép; không gọi paid API trong pytest.

### Tạo ảnh

`POST /v1/images` dạng multipart:

- `logo`: file logo.
- `product`: ảnh một sản phẩm quạt.
- `style`: một trong bốn ID ở mục 1.
- `style_reference`: ảnh mood/style tùy chọn.

Query `wait=true` mặc định chờ tối đa 80 giây: hoàn tất trả 200 và link, chưa xong trả 202. `wait=false` trả job ngay. Poll `GET /v1/jobs/{job_id}` đến `done`/`failed`; không POST lặp với key mới khi đang chờ.

Kết quả gồm `image_url`, `asset_id`, `result.object_key`, `result.minio_uri`; ảnh JPEG 1024×1024. Agent có asset IDs dùng `POST /v1/image-jobs`. Danh mục style: `GET /v1/image-styles`.

### Tạo video

`POST /v1/videos` multipart:

- `image`: một ảnh quảng cáo đã chứa sản phẩm/logo/style.
- `output_type`: `chibi_3d` hoặc `realistic_human`.
- `duration`: 5, 10 hoặc 15.
- `product_name`: tùy chọn, mặc định Quạt để bàn.

Trả 202; poll GET job. Hoặc dùng `POST /v1/jobs` JSON với `input_asset_id` từ kết quả tạo ảnh:

```json
{"input_asset_id":"<asset_id>","product_name":"Quạt để bàn","mode":"muse","output_type":"realistic_human","duration":5}
```

Kết quả có `video_url`, `watch_url`, `result.minio_uri`, `result.image_analysis`, prompt/script và `visual_review`. Có trạng thái `done` nhưng stage `needs_visual_review` khi review chưa đạt: báo đúng cho người bán, không tự kết luận video hoàn hảo.

Luồng thật: GPT đọc ảnh → GPT viết script/prompt → Muse tạo clip → GPT kiểm tra frame → FFmpeg đóng gói → MinIO. Không thay bằng ảnh zoom khi provider lỗi. Job đang chạy khi API khởi động lại được đánh failed để tránh gọi lại provider tính phí; kiểm tra Muse task đã lưu trước khi quyết định submit mới.

## 8. Checklist nghiệm thu

1. `.venv/bin/python -m pytest tests -q` đạt. Bản bàn giao có 25 tests.
2. GET `/health` báo key đã cấu hình; GET `/v1/readiness` có Bearer kiểm tra storage.
3. OPTIONS `/v1/videos` với Origin của domain khác và Access-Control-Request-Method POST trả 200, `Access-Control-Allow-Origin: *`.
4. Tạo một JPG thật; public GET trả `image/jpeg`; object tồn tại trong MinIO và kích thước khớp.
5. Tạo video thật 5 giây; mở watch URL và phát trong browser. GET video với `Range: bytes=0-1023` trả 206, CORS `*`.
6. Không có Bearer thì API riêng trả 401; signed media sai/hết hạn trả 403. Đây là hoạt động đúng.
7. Ghi URL docs/lab đang sống, đường dẫn báo cáo, kết quả tests và giới hạn kiểm chứng. Không đưa secrets vào báo cáo.

Máy nguồn đã tạo 6 ảnh đầu vào + 4 JPG quảng cáo bằng OpenAI, hai video Muse 5 giây (chibi/người thật). 10/15 giây có validation nhưng chưa chạy paid test thật. Chibi cần duyệt vì nhân vật trông trẻ. Các báo cáo nếu được chuyển dữ liệu: `data/image_test_report.json`, `data/video_test_chibi_3d.json`, `data/video_test_realistic_human.json`; prompt mẫu `data/test-assets/prompts.jsonl`. Không khẳng định những file ignored này tồn tại trên máy mới.

## 9. Chẩn đoán nhanh

- API 401: dùng VIDEO_API_TOKEN, không dùng key OpenAI; kiểm tra env ghi đè.
- Provider 401/403/404: key/quyền model/base URL sai; không in key, không tự submit lại.
- 422: xem field và enum trong `/docs`; chỉ 5/10/15 cho Muse, ảnh phải đúng định dạng.
- 429: queue đang đầy (mặc định 4); poll job cũ.
- Video/image URL 403: hết hạn hoặc sai signature; GET job lấy link mới, kiểm tra giờ máy.
- Tunnel lỗi/502: kiểm tra FastAPI :8010 và process cloudflared. Nếu đổi URL, cập nhật PUBLIC_BASE_URL rồi restart API.
- CORS sai: kiểm tra `.env` và biến môi trường `CORS_ORIGINS`, restart API; kiểm tra cả OPTIONS và response thực tế qua public tunnel.
- MinIO lỗi: kiểm tra server, bucket, credentials, endpoint; không đổi bucket sang public để sửa lỗi playback.
- Muse timeout: lưu job/task ID, kiểm tra tác vụ gateway trước khi tạo yêu cầu mới. Thời gian và timeout cấu hình trong `.env`.

## Prompt bàn giao cho Codex mới

> Đọc AGENTS.md ở gốc repo và experiment/CODEX_DEPLOY.md. Triển khai lại experiment trên máy này theo source hiện có. Kiểm tra đủ source, cài môi trường, cấu hình secrets cục bộ, chạy MinIO/FastAPI/Cloudflare, bật CORS mọi domain. Không hiển thị secrets và không sửa app chính. Chạy tests offline, mở docs và báo các bước còn cần thông tin tài khoản. Chỉ chạy generation trả phí nếu tôi đã cho phép trong phiên này. Khi xong cung cấp URL thực tế, kết quả kiểm tra và cách giữ dịch vụ chạy.
