# Video API response và thay đổi mặc định — 31/10/2026

POST `/v1/videos` (multipart image) hoặc `/v1/jobs` (JSON input_asset_id): bỏ duration mặc định 20 giây, bỏ output_type mặc định realistic_human. Cho phép 5/10/15/20 giây.

POST trả HTTP 202, job chưa có URL phát:

```json
{"job_id":"<id>","status":"queued","stage":"queued","outcome_unknown":false,"error":null,"result":null,"created_at":0,"updated_at":0,"reused":false}
```

Poll GET `/v1/jobs/{job_id}` có Bearer token. Khi done, response có `video_url`, `watch_url`, `video_url_expires_at` và `short_description` tiếng Việt do OpenAI nhận xét frame video thật. `result` gồm mô tả, script, image_analysis, visual_review, output_type, minio_uri/path/url, object_key, bucket, duration_seconds, requested_duration_seconds, sha256 và metadata khác. Job cũ chưa có nhận xét trả short_description rỗng.

Link signed public có thời hạn; GET job để cấp link mới. MinIO URL nội bộ/private không dùng thay video_url trên website.

## Kết quả live và giới hạn thực tế

Job `b1a361b324d54d5cad58a4f2e9a53a6e`: yêu cầu 20 giây/người thật; Muse trả clip thực tế **10 giây**, 240 frame. Đã có mô tả OpenAI và lưu MinIO. Không diễn giải requested_duration_seconds=20 thành video thật 20 giây. Pipeline hiện không từ chối độ dài khác yêu cầu; client cần so sánh hai trường này. Chưa có bằng chứng gateway hỗ trợ clip 20 giây; cần xác minh gateway hoặc triển khai nhiều cảnh/nối clip nếu bắt buộc đủ 20 giây.

Báo cáo payload đầy đủ trên máy chạy: `data/video_test_default20.json` (ignored, không chứa API key). Không commit signed URL tạm thời làm URL cố định.
