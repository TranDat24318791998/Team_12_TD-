# ShopPilot AI — media studio và Sites (31/10/2026)

## Luồng sản phẩm

1. Trang bán hàng hiển thị ảnh sản phẩm thật đã đăng ký vào Data.
2. Khi seller duyệt gói có content_refresh, live run tạo draft `choose_image`, chưa gọi provider.
3. Action card trong chat hiển thị logo Gió Mát, ảnh listing hiện tại đã được backend kiểm tra và bốn background. Seller chọn bằng slider/carousel, nhập mong muốn, bấm tiếp tục.
4. POST `/api/content/image` gửi exact draft binding + background + wishes. Core gọi experiment bằng token backend; OpenAI tạo JPG từ logo/sản phẩm/style. Assets và kết quả ghi MinIO; Data nhập bản bytes với checksum để listing có URL bền vững.
5. Sau `image_ready`, seller chọn `realistic_human` hoặc `chibi_3d`, thời lượng 5/10/15/20. Nút tạo video chỉ bật sau khi chọn nhân vật. POST `/api/content/video` dùng chính source_asset_id của ảnh vừa tạo.
6. GPT đọc logo/sản phẩm/style, viết prompt và script; tự chọn cử chỉ nâng/cầm/đỡ quạt khi bối cảnh phù hợp. Không thay quạt để bàn thành quạt cầm tay và không bịa số đo.
7. Muse tạo video, GPT nhận xét frame, upload MP4 MinIO. API có short_description và requested/actual duration. Nếu khác thời lượng hoặc review chưa đạt, seller phải xác nhận trước khi sử dụng.
8. `/api/content/apply` kiểm version/ownership/bytes/review rồi publish nội dung đã duyệt. Seller có thể chọn bỏ video từ `image_ready`, lúc video đang tạo hoặc sau khi video có kết quả; chỉ ảnh đúng job đã tải được và chữ đã kiểm tra mới được áp dụng. Chọn bỏ video không tạo thêm job video, không tự gắn video về muộn vào listing. Khi dùng video vẫn giữ kiểm tra review và thời lượng. Storefront đọc listing đã lưu, giữ kết quả sau reload.

Các run offline tiếp tục luồng legacy có nhãn fallback; không giả gọi API live. Run cũ giữ cấu hình cũ; run live mới mặc định media_wizard=staged.

## Runtime đang dùng

- Core + React local: `http://127.0.0.1:8000`.
- Experiment: `http://127.0.0.1:8010`, backend MinIO.
- Gateway riêng cho Sites: `http://127.0.0.1:8012` (`scripts/sites_gateway.py`), yêu cầu X-Sites-Proxy-Token.
- MinIO API/console: `127.0.0.1:9000` / `9001`.
- Frontend hosted: https://shoppilot-ai-growth-lab.umbercity.chatgpt.site (owner-private, đăng nhập ChatGPT).
- Media tunnel hiện tại: https://prev-ideas-elevation-generous.trycloudflare.com
- Gateway tunnel hiện tại: https://roy-legacy-discrimination-leslie.trycloudflare.com

Quick tunnels có thể đổi URL khi khởi động lại. Máy phải chạy để hosted frontend dùng được agents/media. Business database vẫn nằm máy local; Sites không chạy Python/MinIO/model.

## Khởi chạy lại

Giữ `.env` và `experiment/.env` ngoài Git. Cấu hình root: MEDIA_MODE=live, MEDIA_API_BASE_URL=http://127.0.0.1:8010, MEDIA_API_TOKEN khớp VIDEO_API_TOKEN; DEMO_PRODUCT_IMAGE_PATH và DEMO_LOGO_IMAGE_PATH trỏ đúng ảnh. SITES_PROXY_TOKEN là secret riêng, không dùng OpenAI key làm service token.

Chạy từng terminal từ repo gốc:

```sh
experiment/.venv/bin/python experiment/scripts/start_minio.py
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
sh experiment/scripts/start_api.sh
.venv/bin/python -m uvicorn scripts.sites_gateway:app --host 127.0.0.1 --port 8012 --no-access-log
cloudflared tunnel --url http://127.0.0.1:8010 --no-autoupdate
cloudflared tunnel --url http://127.0.0.1:8012 --no-autoupdate
```

Không chạy thêm tiến trình trên cổng đã có service. Cập nhật experiment PUBLIC_BASE_URL theo media tunnel rồi restart media khi không có job chạy. Sites runtime BACKEND_BASE_URL theo gateway tunnel; BACKEND_PROXY_TOKEN khớp SITES_PROXY_TOKEN. Apply runtime changes bằng deploy version. Không đưa token vào JS, hosting manifest hoặc docs.

Sites source checkout riêng: `../sites/shoppilot` tính từ repo. ID lưu `.openai/hosting.json`; tái dùng ID, không tạo site mới. Frontend source chính vẫn `frontend/`. Build `npm run build` tại frontend, chạy `node scripts/sync-frontend.mjs` trong Sites checkout để copy HTML/CSS/JS/img vào public; build/package/deploy theo Sites skill. Wrapper Vinext proxy `/api/*` và `/media/*`, yêu cầu identity ChatGPT và kiểm Origin. Gateway forward đúng cookie của từng browser (không dùng cookie phiên trước).

## Kiểm chứng

Test tự động dùng provider giả. Live smoke phải được chủ dự án cho phép; không tự tạo job trùng khi timeout. Review riêng Media và UI/host đã phát hiện/sửa lệch thời lượng, offline staging và cookie isolation.

Các ảnh nguồn demo trong frontend/img được copy từ bộ ảnh OpenAI đã tạo; logo Gió Mát là thương hiệu mẫu, khác logo ứng dụng ShopPilot AI.
