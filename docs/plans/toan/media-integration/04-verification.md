# MI04 — nghiệm thu và bàn giao cho agent/teammate

Phụ thuộc MI01–MI03. Đọc [UI_DATA_HANDOFF](UI_DATA_HANDOFF.md). Task kết thúc bằng bằng chứng thực chạy và ba trạng thái riêng, không kết thúc chỉ vì tests provider rời rạc qua.

## Output

- `tests/integration/content/test_media_gateway_flow.py`: ContentService/core runtime thật, gateway service qua fake transport hoặc service TestClient ở test process riêng.
- `scripts/run_media_demo.py`: gọi lại runtime/helpers thật, không viết workflow thứ hai.
- `contracts/media_gateway/`: envelopes fixture + local manifest mẫu, đủ accepted/running/done/review_failed/failed.
- `docs/plans/toan/media-integration/IMPLEMENTATION_REPORT.md` và cập nhật `docs/plans/toan/{DEMO_RUNBOOK,TEAM_INTEGRATION,CODEX_LOG}.md` đúng trạng thái.
- Shared docs chỉ khi interface được implement: `docs/{DEMO_CONTRACT,MUSE_API,CONTRACT}.md`, `tasks/demo/05*.md` và fixtures consumer liên quan. Chưa ghép facade thì ghi planned extension, không nói endpoint đã nhận body mới.

## 1. Core flow không trả phí

Harness sử dụng Session/MemoryGateway/LLM tool runner/ContentService/MediaGatewayClient thật. Chỉ OpenAI/Muse transport và market là fake; request capture phải đọc dữ liệu đầu vào để trả output, không đưa sẵn transcript thành công.

```text
confirm brief → start negotiation → seller accept
→ native Content reads facts/confirmed style
→ create image A → service stores A asset → Muse job references A
→ B/C done, downloaded files/checksums validated
→ seller retry bright → v2 with changed image/video inputs
→ stale v1 callback ignored
→ Apply B + valid video review/ack → listing + exact approved package
→ close day → candidate style, Rules unchanged
→ day2 question Yes → new Content invocation / media brief uses confirmed bright style
```

Asserts: active=None trước Apply; selected cover B chính xác v2; video vẫn reference A v2; listing gốc không đổi; duplicate apply không thêm campaign/event; test model nhìn ToolMessage; confirmed style hiện trong request ảnh và setting video sau Yes. Thu numeric package/outcome từ runtime, không bịa doanh thu tăng.

Fixtures ảnh là JPEG/PNG decode được. Fixture MP4 là file clip local hợp lệ đã có hoặc render bằng công cụ trong test service; gắn source fixture. Không lưu HTML/SVG với đuôi jpg hoặc bytes tùy ý rồi nới validator cho test đi qua. SHA/length phải từ file thật.

## 2. CLI và composition

`run_media_demo.py --agent-mode offline --media-mode fixture --seed 42` là lệnh mặc định không mạng; instantiate ContentService thật, inject FakeMediaGateway thay transport, market fixture. In rõ `AGENT=offline, MEDIA=fixture, MARKET=fixture` và log path. `--media-mode replay` dùng manifest/cache có thật, cache miss không gọi live.

`--media-mode live` dùng root MEDIA_API_* và ContentService thật; require input asset/config, không auto-switch storage/model. Trước create job CLI in số tối đa dự kiến (ảnh, Muse, media text), giữ explicit flag `--allow-paid` để operator chủ động chạy. Đây là guard của CLI chống chạy nhầm; trong ứng dụng seller action đã là trigger nghiệp vụ, không thêm hộp xin phép giữa từng provider call. Không gọi live khi pytest hoặc lệnh mặc định.

Tái sử dụng hàm runtime hiện có để confirm/start/decision/apply/night. Không import CLI cũ nếu làm chạy top-level code; tách helper harness nhỏ khi thật sự dùng chung. `SessionManager(content_factory=...)` inject client/executor; CLI đóng service/client/executor ở finally.

Manifest replay schema trong contracts có: source=cache, source_run/card/draft, product_kind, input_image_sha256, option styles, background_preference, model IDs, A/B/C/video relative paths + SHA/size, video reference=A, visual review và actual duration. File reuse chỉ khi matching inputs; signed URLs không là replay asset. Báo source_run rõ, không trình bày cache như vừa tạo.

## 3. Các lệnh coder phải thực chạy

Từ repo gốc, dùng interpreter đúng môi trường:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_media_demo.py --agent-mode offline --media-mode fixture --seed 42
```

Từ `experiment/`:

```sh
.venv/bin/python -m pytest -q tests
```

Sau MI03 không cần chạy lại toàn bộ test frontend nếu không sửa frontend; nếu sửa schema consumer thì chạy contract tests tương ứng. Danh sách G01–G08, C01–C09, W01–W12 phải được map tới test function trong report; từng suite pass riêng không thay luồng end-to-end trên.

## 4. Live smoke khi có config/asset và được giao chạy

Hiện thiếu OpenAI key, MinIO credentials và ảnh D; không tự chờ input để hoàn thành code. Live gate = NOT_RUN cho tới khi operator cung cấp đủ. Không triển khai Cloudflare/Sites chỉ để chạy local; dùng loopback service.

1. Test service health/readiness/capability, MinIO thật; không xem ready=true là proof provider access.
2. Một ảnh A thật của handheld D, JPEG + checksum + object; một video thật từ asset A, mặc định5giây. Kiểm request/response sanitized, task persisted, output file đọc được. Đây là smoke tối thiểu hai job có phí, không tự chạy cả3draft.
3. Người bán mở JPG/MP4, kiểm đúng mẫu quạt, logo nếu có, người trưởng thành, nội dung nói và shape. Ghi `visual_review_passed` cùng giới hạn; false không biến thành success mặc định. Browser chỉ mở hidden nếu cần, không chiếm màn hình chính.
4. Nếu cần full demo, chạy3ảnh+1video sau đó bằng lệnh rõ ràng; cache artifact vào manifest để lần trình diễn sau không trả phí lại. Phần code hỗ trợ3ảnh phải được test dù smoke tối thiểu chỉ A.
5. Ghi media model/runtime version, actual seconds, input hash, artifact paths, request counters và error nếu có. Không lưu Bearer, .env, signed query/credentials hoặc raw image base64 trong report.

## 5. Mẫu report bắt buộc

```text
BASE_SHA / HEAD_SHA:
CORE_MEDIA: PASS | FIX_REQUIRED
MEDIA_LIVE: PASS | NOT_RUN | FAILED (nêu gate đã chạy)
UI_PRODUCT: PASS | PENDING (facade chưa nối thì PENDING)
Product: handheld D / source asset hash:
Tests: command → count/result; Gxx/Cxx/Wxx → function:
Native Content ToolMessage + knowledge read-back evidence:
Request counts: native LLM / media text / Images / Muse:
Artifacts/log/manifest paths and source:
Unresolved dependencies, exact owner/callable:
```

Reviewer chặn nếu thiếu approved-card gate, model không nhận tools, prompt ép desk fan, không truyền bright style, raw private vào request, job done khi chưa có file, mất idempotency, callback cũ publish, hoặc video review không có cách seller xác nhận. Không yêu cầu features ngoài timebox.

Dừng mở rộng sau khi đạt core acceptance; report đúng live/UI dependencies. DB durable, provider retries nâng cao, model video khác, tự sinh nhạc/giọng và tự tối ưu style bằng learned policy không nằm trong gói này.
