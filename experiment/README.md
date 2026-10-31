# Video Marketing Experiment

Triển khai trên máy/tài khoản Codex mới: đọc [CODEX_DEPLOY.md](CODEX_DEPLOY.md).

Dịch vụ độc lập, viết mới bằng Codex tại `Team_12_TD-/experiment/`. Chạy các lệnh bên dưới từ gốc repo `Team_12_TD-`. Không import hoặc sao chép pipeline Claude trong `videomarketing/`, không sửa contract/app chính.

## Pipeline mặc định: GPT viết prompt, Muse tạo video

`mode=muse` là mặc định mới. GPT tạo brief có cấu trúc gồm đúng một mẫu quạt, nhân vật, bối cảnh đời thực, script tiếng Việt và prompt tiếng Anh. Muse Gateway trong `muse/muse_client.py` tạo video live-action; API tải clip gốc, kiểm tra ba khung hình bằng GPT, giữ video toàn khung và giọng Muse, rồi upload MinIO. Không dùng ảnh zoom thay video Muse.

- Key OpenAI ở `experiment/.env`; key Muse đọc từ `experiment/muse/.env`, có thể ghi đè bằng `MUSE_API_KEY` trong `.env` hoặc môi trường. Không gửi key xuống browser.
- Mỗi yêu cầu chỉ nhận một ảnh tham chiếu và quảng cáo một mẫu quạt. Có thể không gửi ảnh để tạo video demo từ mô tả. Không có ảnh thật thì không xác nhận hình dáng SKU thật.
- `generate_script=true`, `generate_image=false`, `voice=muse`, `music=none` cho pipeline này. Muse được yêu cầu tạo thoại theo script GPT; bản xuất cần người bán duyệt. `voice=openai` thay audio riêng, không bảo đảm khẩu hình.
- Prompt bắt buộc một chiếc quạt, cùng mẫu xuyên suốt, một người trưởng thành trong bối cảnh thực. Kiểm tra các frame trả `visual_review` và `visual_review_passed`; không bảo đảm tuyệt đối nội dung sinh, không tự submit lại nếu chưa biết kết quả.
- Muse task id được lưu ngay sau POST. Lỗi mạng ở poll chỉ retry GET; submit/download không chuyển Bearer sang host khác hoặc theo redirect. Không trộn token với muse.ai hay API của provider cũ.
- `GET /v1/jobs` liệt kê 20 job gần nhất của owner. Trang lab có nút tải video cũ để xem mà không tạo job trả phí mới. Swagger `/docs` có Authorize dùng `VIDEO_API_TOKEN`.
- Khi hoàn tất, API trả cả `video_url` (MP4, GET/HEAD/Range) và `watch_url` (trang xem public có chữ ký, mặc định hết hạn sau 1 giờ). Bucket MinIO vẫn private; không tunnel cổng quản trị 9001.

Ví dụ request mới (có thể thêm `input_asset_id` từ upload ảnh quạt):

```json
{
  "mode": "muse",
  "product_name": "Quạt để bàn màu trắng",
  "product_description": "Một chiếc quạt màu trắng, lồng tròn, đế tròn; một mẫu duy nhất.",
  "presenter": "Một người Việt Nam trưởng thành giới thiệu tự nhiên",
  "setting": "Góc làm việc tại nhà, ánh sáng ban ngày, không có quạt khác",
  "duration": 5,
  "aspect": "9:16",
  "generate_script": true,
  "voice": "muse",
  "music": "none"
}
```

Thử thật bằng `.venv/bin/python scripts/smoke_muse.py`. Nếu đã có `data/muse_smoke_report.json`, lệnh chỉ kiểm tra lại job cũ, không tạo job mới. Chỉ dùng `--new` khi chủ động tạo thêm video trả phí; `--reference /đường/dẫn/ảnh.webp` cho ảnh tham chiếu. Mẫu đã tạo ngày 31/10/2026 lưu `data/muse_sample.mp4`: video 5 giây, H.264 720x1280, 24 fps, có AAC tiếng nói; review ba frame nhận diện một phụ nữ trưởng thành và một quạt trắng nhất quán. Kiểm tra nhận dạng tiếng nói đọc được: “Quạt để bàn trắng gọn gàng cho góc làm việc.”, khớp script GPT về nội dung. Đây là mẫu từ mô tả vì chưa có `fan_sample.webp` trong workspace.

Trang `/watch/{job_id}` là HTML nhỏ do FastAPI experiment tạo để kiểm thử, không phải ChatGPT Sites hoặc giao diện của Muse. Sites chính có thể chỉ dùng `video_url` trong thẻ `<video>` mà không dùng `watch_url`. Thông tin đăng nhập MinIO local được lưu riêng trong `data/MINIO_LOGIN.txt` (quyền 600); không chứa key OpenAI hoặc Muse. Không public file này.

## Các chế độ cũ

Các phần render local bên dưới vẫn được giữ để đối chiếu. Muốn dùng cần chọn rõ `mode=motion_graphics`, `source_video` hoặc `local_i2v`, cùng `voice=openai/upload/none`; không chọn `voice=muse` cho render local.

```text
Sites browser -> Sites server proxy -> Cloudflare Tunnel -> FastAPI localhost:8010
                                                          |-> OpenAI: script / ảnh / giọng
                                                          |-> render local hoặc model I2V local
                                                          |-> MinIO localhost:9000
Sites <video src="signed URL"> -> Tunnel -> FastAPI Range stream -> MinIO
```

## Khả năng

- Upload ảnh PNG/JPEG/WebP, video MP4/MOV, audio WAV/MP3/FLAC tối đa 40 MB.
- Nhận một video gốc và script: `mode=source_video` giữ chuyển động có sẵn, thay audio bằng thuyết minh và nhạc; audio gốc không được giữ.
- Nhận ảnh: `motion_graphics` tạo quảng cáo bằng chuyển động camera, title, tagline, CTA; không phải người cầm sản phẩm/lip-sync hoặc hoạt ảnh cơ cấu quạt.
- OpenAI viết script từ thông số đã xác minh; script người dùng cung cấp được giữ nguyên. Tùy chọn tạo thêm một keyframe từ ảnh sản phẩm và tạo giọng tiếng Việt. Không dùng Ollama.
- Nhạc synth được tạo local, hoặc upload file nhạc có quyền sử dụng. Không có model OpenAI tạo nhạc trong pipeline này.
- `local_i2v` là adapter thử nghiệm LTX Image-to-Video, chỉ chạy khi đã cài dependencies, tải model local và bật cấu hình. Chưa benchmark trên máy này, không tự tải hàng chục GB, không thay lỗi model bằng ảnh zoom rồi báo thành công.
- Một worker xử lý tuần tự; job/state lưu SQLite; có idempotency và giới hạn hàng đợi. Sau restart, job đang chạy được đánh dấu interrupted, không tự lặp lời gọi trả phí.
- Video chỉ `done` sau khi đã upload storage và kiểm tra object. Bucket MinIO giữ private. Link phát có chữ ký, thời hạn mặc định 1 giờ, hỗ trợ GET/HEAD/Range cho play và seek.

## Chạy local

Python 3.11 trở lên. Môi trường hiện tại dùng Python 3.12.

```sh
cd experiment
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/init_config.py
```

Điền `OPENAI_API_KEY` trong `.env` trực tiếp trên máy. Không gửi key vào chat và không commit `.env`.
Script init tạo `VIDEO_API_TOKEN`, `PLAYBACK_SECRET` và credentials MinIO riêng ngẫu nhiên; không in secret ra terminal. File có quyền 600. Khi `.env` đã tồn tại, script không ghi đè.

MinIO local (terminal 1):

```sh
brew install minio cloudflared
.venv/bin/python scripts/start_minio.py
```

- API: http://127.0.0.1:9000
- Console: http://127.0.0.1:9001
- Đăng nhập bằng `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` trong `.env`.
- Dữ liệu: `experiment/data/minio`; log private: `experiment/data/minio.log`.
- Bucket mặc định: `marketing-videos`; cấu hình init cho phép tạo bucket này. Dịch vụ check/create trước lời gọi OpenAI.
- MinIO được Homebrew đánh dấu deprecated vì upstream community đã archive. Đây là môi trường thử nghiệm local; không công khai cổng 9000/9001.
- Script chỉ bind loopback và không thay server đang dùng cổng 9000/9001. Không tự chạy lại sau khi reboot; chạy lại lệnh nếu cần.

FastAPI (terminal 2):

```sh
sh scripts/start_api.sh
```

Mở http://127.0.0.1:8010/ để thử, http://127.0.0.1:8010/docs để xem OpenAPI. Lab yêu cầu Video API token, không yêu cầu nhập OpenAI key vào browser. Không đưa giao diện nhập service token này vào sản phẩm public.

## API

Các endpoint `/v1/` (trừ link `/play` đã ký) cần:

```text
Authorization: Bearer <VIDEO_API_TOKEN>
X-Owner-ID: <định danh được server Sites tính từ người dùng đăng nhập>
```

Thiếu X-Owner-ID mặc định là `local-demo` cho lab. API token là credential server-to-server: ai có token là một caller được tin cậy, không chia sẻ cho browser. Sites phải tự lấy user ID từ phiên đăng nhập rồi ánh xạ sang X-Owner-ID; không chuyển tiếp owner do browser tự khai.

1. `POST /v1/assets`, multipart field `file`, trả `asset_id`, `kind`.
2. `POST /v1/jobs`, JSON bên dưới, header `Idempotency-Key` (8–120 ký tự), trả 202 và `job_id`.
3. `GET /v1/jobs/{job_id}`, poll mỗi 2–3 giây. Khi `status=done`, đọc `video_url`.
4. `GET /v1/readiness`: kiểm tra kết nối và bucket MinIO; không gọi OpenAI.
5. `GET|HEAD /v1/jobs/{job_id}/play?expires=...&signature=...`: link capability có thời hạn cho thẻ video. Không cần chèn bearer vào thẻ video. Người được chia sẻ link có thể xem tới lúc hết hạn.

```json
{
  "input_asset_id": "<id từ upload>",
  "product_name": "Quạt để bàn",
  "verified_facts": ["<thông số đã xác minh>"],
  "script": "<lời đọc, hoặc để trống để AI viết>",
  "mode": "motion_graphics",
  "generate_script": true,
  "generate_image": false,
  "voice": "openai",
  "music": "synth",
  "duration": 12,
  "fps": 24,
  "aspect": "9:16",
  "resolution": "preview"
}
```

`source_video` cần asset video; hai mode còn lại cần ảnh. `voice=upload` cần `voice_asset_id`; `music=upload` cần `music_asset_id`. Ảnh mặc định không tạo thêm bằng AI để tiết kiệm phí. Tối đa một lời gọi script, một ảnh, một giọng mỗi job; SDK retry=0. Yêu cầu sửa tạo job mới sau khi người bán duyệt chi phí.

Giọng dài có thể kéo video tới 30 giây. Script vượt thời lượng trả lỗi, không cắt lời hoặc báo thành công. `preview` xuất khung dọc 432x768, `hd` xuất 1080x1920; có ngang và vuông. Video nguồn/model clip được lặp nếu ngắn hơn thời lượng quảng cáo.

## Tunnel và nối Sites

```sh
sh scripts/start_tunnel.sh
```

Cloudflared in URL `https://...trycloudflare.com`. Đặt URL đó vào `PUBLIC_BASE_URL` trong `.env`, restart API. Quick Tunnel đổi URL khi khởi động lại; khi đổi URL cần cập nhật API và Sites. Máy, MinIO, API và tunnel phải tiếp tục chạy. Quick Tunnel không hỗ trợ SSE, nên API dùng polling.

Ở Sites, lưu **secrets phía server**:

```text
VIDEO_API_BASE_URL=https://...trycloudflare.com
VIDEO_API_TOKEN=<token riêng trong experiment/.env>
```

Dùng adapter `examples/sites-proxy.ts`, truyền user ID thật lấy từ helper xác thực của Sites. Tạo các route proxy assets/jobs/status và kiểm tra quyền ở server. Không dùng `NEXT_PUBLIC_...` cho token. Không cần tunnel MinIO hoặc cấu hình bucket public/CORS MinIO; video đi qua signed streaming endpoint.

Sau khi gọi status qua proxy:

```js
const job = await fetch(`/api/video/jobs/${jobId}`).then(r => r.json());
if (job.status === 'done') videoElement.src = job.video_url;
```

Nếu link hết hạn, gọi status qua proxy để lấy link mới. Chưa sửa hoặc publish Sites chính trong experiment này.

## Model chuyển động local (tùy chọn)

```sh
.venv/bin/python -m pip install -r requirements-motion.txt
```

Chuẩn bị checkpoint Diffusers tương thích `LTXImageToVideoPipeline` tại `models/ltx-video/`, kiểm tra license và RAM; model phải có `model_index.json`. Bật `LOCAL_MOTION_ENABLED=true`; chọn MPS/CUDA/CPU phù hợp. Khi API chạy không tải weights từ mạng. Model chạy trong subprocess để giải phóng bộ nhớ sau job, có timeout. Khả năng người cầm quạt, giữ đúng sản phẩm, khẩu hình và 3D cần thử riêng, chưa được xác nhận.

## Kiểm thử

```sh
.venv/bin/python -m pytest -q
```

Tests không dùng OpenAI/MinIO thật: auth trước multipart, tách owner, idempotency/conflict, queue limit, thiếu key, model chưa cài, expiry/signature, GET/HEAD/Range, crash recovery, render MP4 thật và video nguồn. Có thêm test Muse: prompt một sản phẩm, task id lưu trước poll, chỉ một submit, chặn download khác origin, thiếu key, xuất clip và lưu storage. Provider giả không xác nhận quyền model của tài khoản.

Kiểm tra thực tế ngày 31/10/2026: 12 tests đạt; FastAPI -> MinIO -> phát/tua qua Quick Tunnel đạt HTTP 206. Mẫu OpenAI thật đã chạy thành công với `gpt-6-luna` và `gpt-4o-mini-tts`, lưu `data/openai_sample.mp4` (ảnh quạt minh họa, không gọi tạo ảnh). Model chuyển động local và lời gọi tạo keyframe thật chưa kiểm chứng.

`scripts/smoke_minio.py` (khi có MinIO/API) tạo video test không gọi OpenAI, upload MinIO rồi kiểm tra phát/tua qua API; không thay kết quả này bằng demo AI.

`scripts/smoke_openai.py` là phép thử trả phí có chủ đích: một lời gọi plan và một lời gọi speech. Chỉ thêm `--generate-image` khi muốn gọi tạo ảnh thật. Mẫu có sẵn trong `data/openai_sample.mp4`; không chạy lại nếu chỉ muốn xem kết quả. Khi thay OpenAI key/model trong `.env`, restart API để nạp cấu hình.

Tài liệu: [OpenAI images](https://developers.openai.com/api/docs/guides/image-generation), [Speech](https://developers.openai.com/api/docs/guides/text-to-speech), [LTX Video](https://huggingface.co/docs/diffusers/api/pipelines/ltx_video), [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). Speech model mặc định đã có lịch ngừng 06/01/2027; adapter speech được tách để thay bằng workflow Realtime.

### API ảnh và video từ ảnh quảng cáo

- `POST /v1/images`: multipart `logo`, `product`, `style`, tùy chọn `style_reference`. Header Bearer `VIDEO_API_TOKEN`, `Idempotency-Key`. `wait=true` chờ tối đa 80 giây; nếu chưa xong trả 202, poll `GET /v1/jobs/{job_id}`. Khi hoàn tất có `image_url`, `asset_id`, `result.minio_uri`.
- Style: `clean_white`, `pastel_lifestyle`, `premium_studio`, `summer_fresh`; danh mục `GET /v1/image-styles`.
- `POST /v1/videos`: multipart `image`, `output_type` (`chibi_3d` hoặc `realistic_human`), `duration` (5/10/15), tùy chọn `product_name`. Trả 202; poll job để nhận `video_url`, `watch_url` và `result.minio_uri`.
- Agent có asset ID dùng `POST /v1/image-jobs` hoặc `POST /v1/jobs` với `input_asset_id`, `output_type`, `duration`.
- GPT phân tích sản phẩm/logo/màu/style trước khi viết script và prompt Muse. Video cần người bán duyệt độ chính xác logo/sản phẩm.
- Link public có chữ ký hết hạn; gọi lại GET job có xác thực để lấy link mới. `minio_uri` là đường dẫn object; `minio_url` là endpoint nội bộ, bucket riêng tư không cho GET ẩn danh. UI dùng `image_url`/`video_url` qua tunnel.
- Bộ ảnh mẫu: `data/test-assets/`; prompt gốc `prompts.jsonl`, báo cáo live `data/image_test_report.json`, `data/video_test_*.json`. Test tự động không gọi API trả phí.

CORS: mặc định `CORS_ORIGINS=*`, mọi domain được gọi API/đọc media qua tunnel. Cho phép mọi request header và method trong preflight; endpoint thực tế vẫn theo routes đã định nghĩa. Không dùng cookie credentials; API riêng vẫn yêu cầu Bearer token. Link ảnh/video signed URL không cần Bearer. CORS áp dụng cả response 401/403 và hỗ trợ đọc Range/Content-Length từ JavaScript.
