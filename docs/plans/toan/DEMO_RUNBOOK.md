# Chạy và bàn giao Agent + Tools + Knowledge

Trạng thái: core thương lượng, native tool runner, 5 ngăn knowledge, seller approval và điều phối ngày đã có code. Data service và React đã có code riêng, nhưng adapter market/media và route HTTP vẫn chưa được nối vào workflow agent. Xem [các điểm ghép cần chốt](TEAM_INTEGRATION.md). Script bên dưới dùng fixture cho market/media; không coi kết quả đó là bằng chứng về doanh thu hoặc đã tạo ảnh/video thật.

Lessons của demo chỉ lưu đề xuất định tính không có số; số và kết quả vẫn truy xuất từ History/Calibration. Model được hướng dẫn theo giới hạn này và gateway reject từng op vi phạm, không sửa lời model thành một bài học khác. Chi tiết và điều kiện evidence ở [Knowledge contract](KNOWLEDGE_CONTRACT.md).

Thông tin media mới: [plan MI01–MI04](media-integration/README.md) tái sử dụng experiment qua HTTP. Env local đã nhập file người dùng cung cấp; vẫn thiếu OpenAI key, MinIO credentials và ảnh D. Script bên dưới hiện vẫn dùng fake media, chưa chuyển sang ContentService thật.

## Kiểm thử và chạy luồng

Chạy từ gốc repo:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_agent_demo.py --mode offline --seed 42
```

Script in `MARKET=fixture`, `MEDIA=fixture`, model source, card, kết quả học và trace theo ID. Dự kiến luồng D: sàn 70.000đ/10% → shop 45.000đ/3%/6,5 → seller duyệt → fixture feedback nền sáng → night tạo candidate → ngày 2 seller xác nhận → ContentMemoryView có style mới. `RUN_LOG` là JSONL local dưới `runs/` và không commit. Test ghép `tests/integration/agents/` còn kiểm model giả thực sự nhận ToolMessage và kết quả memory làm thay đổi output của Platform/Content.

Script không mở giao diện, không gọi API trả phí và không dùng token. File ảnh/video tạo trong thư mục tạm là fixture, không phải nội dung được provider tạo.

## Smoke OpenAI khi cấu hình sẵn

Điền `OPENAI_API_KEY`, `LLM_MODEL` và `LLM_MODEL_REFLECT` trong `.env`, chọn model có native function calling, rồi chạy:

```sh
.venv/bin/python scripts/run_agent_demo.py --mode live --seed 42
```

Script gọi OpenAI có thể phát sinh phí; market/media vẫn là fixture. Một invocation phải hoàn tất `source=live` thì script mới coi lần chạy đã có model live. Inspect trace `requested_by=model`, `tool_call_id` và `source`; offline fallback không được báo là smoke live thành công. Không ghi key hay prompt riêng vào báo cáo. OpenAI key/model chưa được cấu hình ở lúc bàn giao nên smoke này chưa chạy.

## Đầu nối cần member khác cung cấp

- Market: inject object có `forecast_package(shop, pkg, day, seed, calibration)`, `build_forecast_snapshots(shop, pkg, start_day, seed, calibration)` và `simulate_day(session, day)` theo [runtime contract](../../DEMO_CONTRACT.md). Forecast snapshot phải phát hành trước settlement; `simulate_day` chịu trách nhiệm cập nhật stock một lần. Không gắn `tests/fakes/market.py` làm market production.
- Media: inject ContentService có `start(shop_id)`, `retry(shop_id, feedback_vi)`, `apply(shop_id, cover_option, *, skip_video=False)` theo hợp đồng. Backend chỉ gọi start sau seller accept và apply sau kiểm version/media. `app.agents.content.generate_content(session, shop_id, *, card_id, draft_version, feedback_history=())` trả `AgentRun` có `value: ContentText` và source; tool context lấy facts/style đúng card. Media service tự quản lý job OpenAI Images/Muse và kiểm claims trước publish.
- API: member API nối `SessionManager` và các hàm trong `app.runtime.day` vào route, map `WorkflowError` sang HTTP code/message. Route nghiệp vụ hiện là khung; không gắn nhãn `/api` đã chạy chỉ vì headless harness thành công.
- DB: `MemoryStore.commit_batch` và `EventLog` hiện hoạt động trong một process; member DB có thể thay adapter cùng interface và test CAS/receipt. Session/memory chưa phục hồi sau restart.

Provider/response parser đã có trong experiment; cần nối và smoke với SKU D trên máy hiện tại. Reports live từ máy nguồn không theo Git; ảnh D vẫn chưa có trong `assets/products/`. Proof nhiều ngày thuộc lane simulator, không suy ra kết quả từ fixture hai ngày.
