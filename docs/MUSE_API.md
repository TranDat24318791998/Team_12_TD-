# Media service và Muse Gateway

Cập nhật 31/10/2026 sau commit media `a0a93f0`. Provider giữ nguyên: OpenAI cho agents/text/ảnh; Muse Gateway cho video. `experiment/` hiện có implementation độc lập cho Images, Muse, SQLite job queue, MinIO và signed playback. **Chưa nối vào ContentService/core runtime.**

Plan code của Toàn: [media-integration](plans/toan/media-integration/README.md), contract chi tiết [CONTRACT](plans/toan/media-integration/CONTRACT.md). Task provider [D05a](../tasks/demo/05a-media-api.md) dùng implementation này; không viết client/pipeline thứ hai trong app.

## Hai HTTP surface khác nhau

| Đích | Auth/config | API |
|---|---|---|
| Media service của repo, mặc định localhost:8010 | Bearer `VIDEO_API_TOKEN`; root dùng `MEDIA_API_TOKEN` cùng giá trị; owner do backend bind | Upload `/v1/assets`; JSON `/v1/image-jobs`, `/v1/jobs`; poll `/v1/jobs/{job_id}`; multipart lab `/v1/images`, `/v1/videos` |
| Muse Gateway `https://muse-api.butterflyro.space` | Bearer `MUSE_API_KEY`, chỉ experiment sử dụng | JSON POST `/v1/videos`; poll `/v1/videos/{task_id}`; download `/v1/media/{name}` |

Không gửi multipart body/service token sang Muse Gateway. Không đưa OpenAI/Muse/service token vào browser. MinIO URI/endpoint là storage metadata, không phải URL public của listing.

## Source có thể tái sử dụng

- [models](../experiment/video_api/models.py): ImageRequest, VideoRequest, enums/style/output; service nhận video5/10/15giây, default5.
- [image_pipeline](../experiment/video_api/image_pipeline.py): Images edits → JPEG → MinIO → output asset_id.
- [muse_pipeline](../experiment/video_api/muse_pipeline.py): GPT đọc ảnh/viết prompt → Muse → kiểm frame → MP4/MinIO. Video giữ native Muse motion/audio, không thay bằng zoom ảnh.
- [MuseMedia](../experiment/video_api/muse_media.py): gửi reference bằng data URL, persist task trước poll, paid POST một lần, authenticated download cùng origin và không redirect.
- [main](../experiment/video_api/main.py): auth/owner/idempotency, job/status, signed image/video streaming; [store](../experiment/video_api/store.py) có queue và crash state.
- [CODEX_DEPLOY](../experiment/CODEX_DEPLOY.md): môi trường, service/MinIO/tunnel. Tunnel không bắt buộc khi core cùng máy.

Source đang hardcode desk fan và logo required. MI01 mở hai product kinds và optional logo/bright preference; D vẫn là quạt cầm tay theo seed. Luồng D dùng ảnh A cùng draft cho video; khi chưa có ảnh D thì chặn input, không tự rơi về text-to-video. Lab riêng vẫn có thể dùng text-to-video và phải ghi đúng nguồn.

## Contract và trạng thái bằng chứng

Gateway public docs: [Swagger](https://muse-api.butterflyro.space/docs#/), [OpenAPI](https://muse-api.butterflyro.space/openapi.json); snapshot đã có ở [reference](reference/muse-gateway-openapi.json). Raw gateway schema cho phép duration1–120; service cố ý giới hạn5/10/15. Parser mới đã có trong source, không còn yêu cầu coder tự đoán từ schema `{}` hoặc useapi.net cũ.

Tài liệu experiment báo live JPG và hai video5giây ở máy nguồn. Report/file nằm dưới ignored experiment/data nên checkout hiện tại không có bằng chứng file để kiểm lại; độ dài10/15 mới có validation/tests, không được nói đã live. Kết quả frame review không xác minh tuyệt đối SKU/khẩu hình/audio, seller vẫn phải xem.

Trạng thái nguồn service có thể `done` với stage `needs_visual_review`; adapter không biến nó thành đã được seller duyệt. Contract mới quy định video_review_ack hoặc skip rõ ràng, local artifact download và receipt/version; các extension đó còn cần MI01–MI04 implement trước khi facade dùng.

## Env local

Root `.env`: native LLM config riêng, MEDIA_MODE độc lập LLM_MODE, MEDIA_API_BASE_URL/MEDIA_API_TOKEN cho adapter sau MI02. `experiment/.env`: provider keys/models, VIDEO_API_TOKEN, PLAYBACK_SECRET, MinIO. Không chia sẻ hai file bằng cách import settings của service vào app.

Đã nhập file env người dùng cung cấp; OpenAI key và MinIO credentials vẫn trống, Muse key được giữ từ config local. Native LLM key/model và input ảnh D vẫn cần trước smoke tương ứng. Các env ignored/quyền0600; tài liệu và fixtures chỉ chứa tên biến.

## Nghiệm thu

Tests offline service và core adapter theo [MI04](plans/toan/media-integration/04-verification.md). Tách CORE_MEDIA, MEDIA_LIVE và UI_PRODUCT. Health/readiness hoặc tests fake không chứng minh đã tạo ảnh/video thật. Không chạy generation trả phí trong pytest hoặc tự resubmit khi chưa biết kết quả job cũ.
