# Media service và Muse Gateway

Provider đã chốt: OpenAI cho native agents, Images và vision/planning/review; Muse Gateway cho video/audio native. Product backend gọi `experiment/` bằng HTTP; không chép pipeline provider hoặc dùng useapi.net cũ.

| Tầng | Cấu hình/auth | API |
| --- | --- | --- |
| Local media service | MEDIA_API_BASE_URL=http://127.0.0.1:8010; backend MEDIA_API_TOKEN khớp VIDEO_API_TOKEN | `/v1/readiness`, multipart `/v1/assets`, JSON `/v1/image-jobs`, JSON `/v1/jobs`, GET job |
| Muse Gateway, chỉ experiment gọi | MUSE_API_BASE_URL, MUSE_API_KEY, MUSE_VIDEO_MODEL | JSON POST `/v1/videos`, GET `/v1/videos/{task_id}`, gateway media download |

`/v1/videos` tiện ích của experiment nhận multipart, khác raw Muse JSON endpoint. Không dùng nhầm token/body giữa hai tầng. Browser chỉ nhận authenticated Data asset URLs; không nhận provider/service token, MinIO URI hoặc signed link làm listing bền vững.

## Luồng sản phẩm

Data-bound Content Agent đọc verified facts/confirmed style và tạo listing text. Media worker kiểm input/text trước paid jobs, upload original, tạo A bằng OpenAI Images edits, queue video từ A cùng attempt rồi tạo B/C. Video5giây realistic_human,9:16, voice=muse/music=none; chọn cover B/C không tạo video mới. Logo tùy chọn, no-logo không được invent brand. Bright feedback chọn presets sáng không xung đột premium dark.

Service hỗ trợ desktop_fan và handheld_fan xuyên image/vision/plan/Muse/review. **D hiện dùng desktop_fan** theo user xác nhận, từ MinIO `marketing-videos/test-assets/desk-fan.jpg`; giữ số kinh doanh mô phỏng, không giữ USB/pin claims thiếu nguồn. Imports/checksum nằm local ignored; không sửa object đồng nghiệp.

`growth-media.v1` readiness báo capability/kinds/optional_logo/bright. Output có SHA,size,MIME,actualduration,source và visual review. Frame review chỉ là tư vấn; false/null cần seller ack hoặc skip, bytes phải hợp lệ trong mọi trường hợp. Signed playback hỗ trợ Range; client tải qua configured origin/no redirects/no bearer, kiểm bytes rồi đăng ký Data assets.

## Idempotency và lỗi

Media Store transaction đã có unique owner+key/body hash. Root persist binding/request/key/reservation trước network; cap9image/3video perrun, media text/vision tối đa3/video tách khỏi native64. Unknown sau accepted submit, malformed success response, timeout hoặc restart không cấp key mới. Chỉ recover cùng request/key hoặc GET job; raw Muse POST không tự lặp. Completed media không tự publish/campaign.

## Local hosting và bằng chứng

Bản local dùng existing STORAGE_BACKEND=local với `experiment/data/local/`; MinIO backend vẫn hỗ trợ deployment khác. Đọc [LOCAL_RUN](LOCAL_RUN.md). App và media dùng env/venv riêng; credentials ignored0600. Native model/media mode độc lập, provider keys được cấu hình backend-only.

Đã đọc source/import dữ liệu đồng nghiệp và model lookup read-only; đây không phải bằng chứng generation đã chạy ở local. Các output nhập có nhãn imported/cache. Tests fake provider dùng JPEG/MP4 thật để kiểm transport/storage/gates, không kiểm chất lượng provider/audio/SKU. Live gate chỉ PASS khi generation và playback thực được chạy/ghi nguồn.

Chi tiết code/tasks ở [media plan](plans/toan/media-integration/README.md) và [integration contract](DEMO_CONTRACT.md). Tham khảo Images edits chính thức: [OpenAI Images edit](https://developers.openai.com/api/reference/python/resources/images/methods/edit).
