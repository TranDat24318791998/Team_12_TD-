# D00 — Khóa input và kiểm tra nền tảng

Timebox 8 phút. Đọc `AGENTS.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/DEMO_CONTRACT.md`. Thực hiện trên main, giữ nguyên thay đổi của người khác.

## Output

`docs/CODEX_LOG.md`, `.env.example` (chỉ tên biến/giá trị không bí mật), `contracts/demo_scenario.json`, `contracts/agents/handoff.json`. Config thật chỉ ở `.env` gitignored. Các task sau được thêm đúng fixtures trong Output của mình.

## Các bước

1. `git status --short --branch`, ghi BASE_SHA; nếu có code đang được người khác sửa, không reset/checkout đè.
2. `.venv/bin/python -m pytest -q`. Baseline dự kiến 14 test; ghi kết quả thực, không copy số cũ.
3. Đọc [Agent/Tools](../../docs/AGENT_TOOL_KNOWLEDGE.md), [Knowledge](../../docs/KNOWLEDGE_CONTRACT.md) và [mapping phần việc](../../docs/AGENT_SCOPE_MAP.md). Chốt owner DB/market/media/API và trạng thái adapter thật/fake trong handoff.json. Không giao Toàn viết lại toàn bộ UI/provider. Đọc `app/core/settings.py`, requirements đã pin. Dùng Python3.11 và dependencies hiện có; không nâng toàn bộ môi trường.
4. Khóa providers: OpenAI cho LLM/text/learning và ảnh; Muse Gateway cho video. Đọc `docs/MUSE_API.md`. Không sử dụng luồng useapi.net cũ.
5. Kiểm tra tên biến được cấu hình, không in giá trị: OPENAI_API_KEY, LLM_MODEL, LLM_MODEL_REFLECT, OPENAI_IMAGE_MODEL, MUSE_API_BASE_URL, MUSE_API_KEY, MUSE_VIDEO_MODEL, MEDIA_MODE. OpenAI key/model trống thì ghi `chưa cấu hình`, không đoán tên model. Muse token đã lưu local; không copy sang ví dụ hoặc fixtures.
6. Chọn một ảnh đầu vào D thực sự tồn tại ở `assets/products/`. Hiện baseline chỉ có `.gitkeep`. Nếu chưa có ảnh, dùng ảnh user cung cấp; hoặc sau khi OpenAI được cấu hình tạo một ảnh quạt synthetic và gắn nhãn generated. Không tạo file jpg giả từ HTML/SVG để lừa adapter.
7. Tạo fixture mô tả duy nhất `demo_scenario.json`: seed42, shopD, day_count2, goalincrease_orders, private45kcap, initial70k/10/4, counter45k/3/6.5, feedbackbright, expectedrulebright. `source='fixture'`, `proof_of_learning=false`. Không cho fixture chứa metric thắng/thua.

## Cấu hình cần có trước smoke thật

| Tên | Nguồn |
|---|---|
| OPENAI_API_KEY | Người dùng điền local/secrets |
| LLM_MODEL / LLM_MODEL_REFLECT | Model được tài khoản cấp, hỗ trợ native function calling/strict schema |
| OPENAI_IMAGE_MODEL | Model ảnh được cấp, kiểm tra khả năng edit/reference |
| MUSE_API_BASE_URL | `https://muse-api.butterflyro.space` |
| MUSE_API_KEY | Token user đã cấp, backend-only |
| MUSE_VIDEO_MODEL | `muse-video` theo schema gateway |
| MEDIA_MODE | live khi trình diễn thật; offline/replay chỉ khi chọn rõ |

## Hoàn tất

- Baseline test được ghi, input ảnh đã xác định hoặc thiếu được nêu rõ.
- Không có secret trong staged diff.
- Agent sau có một contract, một fixture và một provider video cụ thể để làm.
- Không chờ API key để bắt đầu domain/graph/fake tests. Không đánh dấu media thật đạt khi thiếu key hoặc chưa có response thật.

## Reviewer

Kiểm tra phạm vi file, zero secrets, fixture phân biệt outcome đo thật. Không đòi setup cloud trước khi code. Kết quả bàn giao: BASE_SHA, trạng thái test, đường dẫn ảnh, biến còn thiếu (chỉ tên).


## Gate mới cho phần Agent + Knowledge

- Fixture handoff liệt kê 15 adapter + các wrapper mới, owner, module/callable, input/output schema, trạng thái `ready|fake|pending`; dùng mapping chính thức, không đánh dấu ready dựa trên tên file khung.
- Cấu hình `MAX_LIVE_CALLS_PER_SESSION=64` cho demo tool loop; không đổi key/model khi chưa được cấp. Không gọi API để dựng fixtures.
- D01 tạo DTO/tools và seed catalog; D02a phải xong trước D02. D04 sở hữu five-bin gateway, không còn là phần phụ sau UI.
- Input ảnh thiếu không chặn agent/tool/knowledge tests; ghi pending cho lane media. Handoff core đạt không đồng nghĩa live media đã đạt.
