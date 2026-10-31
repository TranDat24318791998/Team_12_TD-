# D06 — Review Agent/Tools/Knowledge và bàn giao tích hợp

Timebox10phút +6phút buffer theo plan. Review độc lập sau patch/SHA coder; đọc [Agent/Tools](../../docs/AGENT_TOOL_KNOWLEDGE.md), [Knowledge](../../docs/KNOWLEDGE_CONTRACT.md), [scope map](../../docs/AGENT_SCOPE_MAP.md) và caller thực. Báo riêng CORE PASS/FIX REQUIRED và INTEGRATION LIVE PASS/PENDING.

## Output

`scripts/run_agent_demo.py`, `tests/integration/agents/test_agent_knowledge_flow.py`, `tests/integration/api/test_demo_flow.py`, `docs/DEMO_RUNBOOK.md`, `docs/CODEX_LOG.md`. Fix source chỉ trong phạm vi task đã làm có lỗi tái hiện. Không thêm workflow riêng trong script, không bịa tool trace.

## Gate review bắt buộc

| Gate | Bằng chứng | Nếu fail |
|---|---|---|
| Native tool loop | AIMessage.tool_calls → handler → ToolMessage đúng ID → output model dùng kết quả | Core fail, structured output đơn lẻ chưa đủ |
| Role ACL | Platform không gọi T02/T05/T09; args không đổi role/shop/run; denied handler không chạy | Chặn live |
| Scope/privacy | Private cost/rules/Persona không trong public tools/messages/events | Chặn live |
| Five-bin Knowledge | Typed Rules/Prefs/History/Calibration/Lessons; read/write/evidence/version test | Core fail nếu chỉ summary |
| Read-back affects behavior | Confirm style đổi Content tool result/prompt; history/lesson đổi Platform decision fixture | Core fail nếu chỉ event memory_read |
| Finance/graph | D 45k/3/6.5 offline;4% bị chặn;<=3lượt sàn,<=36modelcalls/negotiation; referee chạy | Sửa graph/validators |
| Approval | Agreed chưa apply; seller accept vẫn chờ content nếu refresh; đúng card/brief/draft | Chặn apply |
| Learning writes | 4bins commit atomic; Rules chỉ qua Yes; valid evidence; đủ4LessonOp | Chặn night/confirm |
| Runtime gốc | C stock bị loại, E pause trước ngày3 spend, expired→renew cần approval | Sửa runtime helper |
| One effect/version | Night/apply retry không lặp, stale callbacks không publish | Chặn apply/night |
| Provider thật | OpenAI native tool round-trip; ảnh OpenAI/video Muse mở được | Live PENDING nếu chỉ fake |
| Honest source | Fixture/offline/live/cache phân biệt, no revenue-uplift claim từ D2ngày | Sửa trace/runbook |

Reviewer trả input tái hiện, expected/actual, file:line và cách sửa tối thiểu. Không chặn vì thiếu vector DB/auth/multiuser/anti-spam/full dashboard ngoài scope.

## Test và headless harness

Chạy `.venv/bin/python -m pytest -q` bằng fake providers. Core integration dùng Session/runner/gateway/runtime thật; chỉ model, media, market chưa có adapter được inject fake rõ nguồn. Fake model phải đọc ToolMessage để chọn output, không trả transcript cố định bất chấp tool result.

Luồng test: reset → confirm brief → start → tool negotiation → accept → fake content/retry nền sáng → apply → market event → night → inspect5bins → ngày2 Yes → invocation Content tiếp theo + Platform read-memory fixture. Kiểm active None trước apply; exact approved package; evidence IDs có thật; Rules chưa đổi trước Yes; factor1 ở1–2samples; duplicate calls không thêm effect. Negative tests: MemoryOFF vẫn rules, cross-run denial, fake evidence rejected.

`scripts/run_agent_demo.py --mode offline --seed 42` dùng cùng runtime methods và in trace đã lọc; không tái implement logic bằng print. In từng stage: role/tool/callID/status/recordRefs, decision, candidate, confirmation, next-use. Fake dependency ghi fixture, offline policy ghi offline. Không in cost/private raw payload/token. Script `--mode live` cần key/model, chạy tối thiểu negotiation tool loop; Content/media thật chỉ khi adapter/config đủ. Không âm thầm fallback rồi báo live gate đạt.

API member sẵn sàng thì TestClient đi cùng flow HTTP qua10routes và kiểm serialization/versions. Chưa sẵn sàng: core harness vẫn bàn giao, HTTP integration ghi pending cụ thể; không nhận JSON hardcode là workflow thật.

## Smoke thật khi có cấu hình

1. OpenAI: tối thiểu một invocation phát tool call, backend thực thi, model nhận ToolMessage và trả terminal. Lưu trace đã lọc với source live/modelconfigured; không yêu cầu wording giống fixture.
2. Content/media member: một ảnh OpenAI và một video Muse theo [MUSE_API](../../docs/MUSE_API.md); capture response đã loại secret thành fixture, map status thật, tải/mở được file. Không log Authorization. Muse schema response `{}` vẫn cần response thực trước khi chốt parser.
3. Key/model hoặc adapter thiếu → ghi pending, không gọi API placeholder và không giả thành công. Thời gian render ngoài3phút thao tác demo.

## Script trình diễn phần Toàn

1. Brief D, xem public context/catalog và memory lookup trong trace; sàn đưa đề xuất.
2. Shop đọc luật riêng, gọi evaluate tool; counter an toàn; referee dùng public turns. Không lộ private tool payload khi trình chiếu.
3. Seller accept → Content đọc verified facts/confirmed style; media pipeline member chạy; seller retry/apply đúng phiên bản.
4. Night: xem evidence IDs, candidate, public history, calibration points và lesson ops thực được commit. Rules chưa tự đổi.
5. Ngày2 seller Yes; Content invocation mới đọc style đã xác nhận. Cho thấy Platform đọc learned history/lesson qua tool. Nếu dùng fixture, nhãn thể hiện đúng, không tuyên bố revenue tăng.

UI member chưa sẵn sàng thì dùng headless harness cho1/2/4/5 và fake Content tại3 có nhãn. Đây là bàn giao phần agent/knowledge, chưa đạt demo sản phẩm với media live. Không thay mục tiêu agent bằng việc làm đẹp UI.

## Bàn giao cuối

Ghi SHA, test results, trace path, five-bin records và next-use evidence, mapping adapter thật/fake/pending, key thiếu (chỉ tên), provider response nào đã xác minh. Token ở .env ignored. CorePASS không tự suy ra LivePASS; lỗi chặn phần nào nêu đúng phần đó. Proof nhiều ngày mặc định6 là follow-up simulator owner, chưa có số thì /proof trả PROOF_NOT_READY.
