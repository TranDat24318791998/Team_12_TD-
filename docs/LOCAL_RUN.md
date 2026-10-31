# Chạy bản local trên máy này

Chạy từ gốc repo. Bản product dùng React + Data + native worker tại `http://127.0.0.1:8000/?preview=0`; media service tại `http://127.0.0.1:8010`. Không mở browser tự động, không cần Docker/MinIO/tunnel. Hai process chạy nền, bind loopback, một worker/no reload.

```sh
.venv/bin/python scripts/local_stack.py start
.venv/bin/python scripts/local_stack.py status
.venv/bin/python scripts/local_stack.py stop
```

`start` giữ process đã chạy đúng ownership và từ chối cổng do process khác chiếm; `stop` chỉ gửi signal cho process được manifest xác nhận. Không xóa DB/assets khi stop. PID/log nằm ở ignored `data/runtime/local-stack/`. Đóng terminal không dừng hai process; reboot/logout dừng, sleep làm dịch vụ tạm không truy cập được. Không cần đổi power settings.

Trong một media process, tối đa ba job được xử lý đồng thời; ảnh A/B/C không còn chờ lần lượt. Video vẫn dùng ảnh A của đúng attempt. Trạng thái và file từng slot được lưu riêng; restart không tự gửi lại job provider chưa rõ kết quả.

## Cấu hình và dữ liệu

- Python3.11 root `.venv`, Python3.12 `experiment/.venv`; dependencies theo hai requirements. Node>=20 chỉ cần build frontend. Máy này có bundled Node tại `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node`.
- Root `.env`: OPENAI_API_KEY, LLM_MODEL/LLM_MODEL_REFLECT, LLM_MODE, MEDIA_MODE, MEDIA_API_BASE_URL/TOKEN, DEMO_PRODUCT_IMAGE_PATH, DEMO_LOGO_IMAGE_PATH. Các mode độc lập; có key không chứng minh generation đã chạy.
- `experiment/.env`: provider keys/models, VIDEO_API_TOKEN, PLAYBACK_SECRET. Local profile override STORAGE_BACKEND=local, DATA_DIR=`experiment/data/local`, PUBLIC_BASE_URL=http://127.0.0.1:8010. Service token và root MEDIA_API_TOKEN phải khớp.
- Business/Knowledge DB: `data/runtime/growth.db`; registered assets: `data/runtime/objects/`; source imports: `data/runtime/imports/`; media queue/objects: `experiment/data/local/`. Không copy jobs.sqlite3 cũ từ máy khác vào backend local rỗng vì asset paths/storage có thể khác.
- D đã được user chọn đổi thành quạt để bàn từ MinIO đồng nghiệp, giữ số kinh doanh mô phỏng. Ảnh gốc nhỏ được lưu tại `assets/products/demo-d-desktop.jpg`, provenance/checksum tại file `.source.json` cạnh ảnh để clone mới tái tạo được demo. Data đăng ký ảnh riêng mỗi run. Các ảnh/video lớn đã nhập nằm trong ignored runtime; chúng là imported cache, không phải live output của bản này.
- Logo ShopPilot AI ở `frontend/img/shoppilot-ai.png` giữ nguyên ảnh người dùng gửi. Trỏ DEMO_LOGO_IMAGE_PATH tới file này để các job media mới dùng cùng logo với giao diện; không cần tạo lại file hoặc đổi tên shop.
- Secrets chỉ nằm trong env ignored/quyền0600. Không source/cat env trong log, đưa token vào browser hoặc truyền secret trên argv.

Profile LLM được yêu cầu cho ứng dụng:

```dotenv
LLM_MODEL=gpt-6.1-terra
LLM_MODEL_REFLECT=gpt-6.1-terra
LLM_REASONING_EFFORT=xhigh
LLM_TIMEOUT_SECONDS=120
```

Transport dùng Responses API cho tool calling của Terra; model và effort được gắn vào replay binding. Config chỉ được nạp lúc tạo app/worker; phiên đang chạy không tự đổi model khi sửa file.

Server dùng mode hiện tại trong cấu hình/environment. **Các thao tác demo ở live có thể gọi provider**; health/readiness/start không được tạo job mới để thử. Kiểm không trả phí dùng mode offline và fake providers/temp homes. Không thay mode của process đang chạy bằng cách chỉ sửa env; stop/start để nạp lại, giữ DB.

```sh
LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python scripts/local_stack.py start
```

Ở offline, nguồn native/media phải được ghi đúng là offline/fixture/cache/unavailable. Nếu không có cache phù hợp, media báo unavailable; không giả đã tạo ảnh/video. Offline acceptance đầy đủ dùng integration test fake provider với JPEG/MP4 giải mã được, không dùng server product để tạo giả evidence.

## Luồng demo

1. Mở seller URL `http://127.0.0.1:8000/?preview=0`, xem đúng run/mode/sản phẩm.
2. Xem mục tiêu đặt sẵn **24 đơn trong 3 ngày**, ngân sách tối đa **45.000đ/ngày**, bấm xác nhận rồi Bắt đầu ngày. Các số của demo D không cho sửa; backend cũng từ chối body khác preset. Worker chạy nền, UI poll operation/events. Brief của run cũ đã xác nhận vẫn giữ nguyên lịch sử.
3. Xem tools/Platform/Shop/Referee, chọn Accept/Negotiate/Reject. Content-refresh accept chưa bật campaign.
4. Content worker tạo chữ rồi tạo A/B/C song song. Video bắt đầu khi A đã sẵn sàng và chạy đồng thời với B/C; ảnh nào hoàn tất sẽ hiện trước. Feedback nền sáng có tối đa hai lần làm lại, gửi all để video cùng attempt.
5. Chọn cover, xem video; clip chưa pass review cần ack hoặc chọn bỏ video. Missing/corrupt cover không được Apply. Apply mới publish+activate.
6. Kết thúc ngày. Data settle và night học; không thao tác ngày sau khi operation chưa xong. Ngày sau seller trả lời câu hỏi preference; Yes mới thành Rules/default.
7. Proof “Phiên hiện tại” chỉ có dữ liệu khi active run nằm trong một cặp hoàn tất. Sau reset chưa có cặp thì báo chưa sẵn sàng. “Báo cáo mô phỏng đã chạy” là nguồn riêng; cả hai nguồn tải nhật ký của đúng cặp ON/OFF. Preview7ngày vẫn là mẫu riêng.

## Kiểm tra và báo lỗi

`/health` là liveness; `/ready` kiểm phần Data/worker, không chứng minh OpenAI/Muse generation. Media `/v1/readiness` cần token và kiểm storage/capability; không đưa token vào ví dụ URL. Server status/readiness phải tách input, provider configuration và generation.

Nếu port bị dùng, launcher báo PID và dừng; không kill process ngoài ownership. Nếu có queued/running work trước restart, launcher yêu cầu kiểm state thay vì tự replay paid jobs. Provider timeout/response không rõ giữ unknown và reservation, không tạo attempt/key mới chỉ để vượt lỗi. Xem safe logs `data/runtime/local-stack/app.log` và `media.log`; không in toàn bộ log vào chat nếu có thông tin nội bộ.

Sao lưu SQLite bằng backup API/CLI đã có trước migration; muốn snapshot đủ media thì stop processes và giữ cả object/input directories. Không dùng `data/setup.sh --reset` cho routine startup. Không xóa runtime để sửa validation hay test fail.

## Lệnh verification

```sh
LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -c data/pyproject.toml data/tests -q
PYTHONPATH=experiment experiment/.venv/bin/python -m pytest experiment/tests -q
```

Từ frontend, dùng `npm test` và `npm run build`, hoặc bundled Node chạy `build.mjs --tests`, `--test tests/*.test.mjs .test-build/*.test.mjs`, rồi `build.mjs`. Không hand-edit bundle. Integration tests phải dùng DB/temp providers riêng, không reset seller run đang dùng.

`node frontend/tests/data-contract.integration.mjs` chạy cặp native offline trong DB tạm rồi đưa response HTTP thật qua React để kiểm contract. Hai script headless `start-operation.browser.mjs` và `proof-source.browser.mjs` ở cùng thư mục kiểm tương tác; chạy Chrome ẩn, không dùng profile/màn hình của người đang demo.

Kết quả thực, report paths và gate chưa chạy được ghi tại [implementation status](plans/toan/full-integration/IMPLEMENTATION_STATUS.md) khi nghiệm thu. Không lấy số PASS từ README nguồn hoặc model-lookup200 thay cho live generation.

## Báo cáo mô phỏng đã chạy

Trong màn Proof chọn **Báo cáo mô phỏng đã chạy**. Đây là cặp D ON/OFF được tính trước bằng native offline + Data simulator; UI giữ run IDs thật, nhãn ngoại tuyến và chưa đánh giá provider. Download báo cáo/nhật ký lấy đúng manifest và bằng chứng của cặp đó, không lấy log phiên hiện tại.

Để thay artifact bằng một cặp hoàn tất khác, lấy `comparison_id` từ `comparison.json` của lần chạy, rồi xuất:

```sh
.venv/bin/python scripts/export_demo_proof.py \
  --source-home runs/sim-D-8984ae2c0383489faa90fa171f0090f5 \
  --comparison-id group_4349d9bc018e4cdfbdc9
```

CLI đọc snapshot nguồn, không chạy provider, ghi atomically vào ignored `data/runtime/demo-proof.json`. API `/api/proof/demo` chỉ cho seller D, kiểm schema/hash; artifact thiếu hoặc hỏng được báo rõ. Tạo cặp mới bằng `.venv/bin/python scripts/run_sim.py --shop D --days 7 --seed 42`; dùng đường dẫn/ID thật script trả về, không tái sử dụng ID ví dụ cho nguồn khác.
