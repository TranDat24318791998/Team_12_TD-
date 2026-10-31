# D04 — Knowledge đủ năm ngăn và Learning Agent gọi tool

Timebox **20 phút**, sau D01 và D02a; có thể làm song song feature agents D02 khi interface đã khóa. Đây là phần Toàn nhận từ đầu, không được cắt xuống thành summary học. Đọc [Knowledge contract](../KNOWLEDGE_CONTRACT.md), [agent/tool contract](../AGENT_TOOL_KNOWLEDGE.md), rồi [demo contract](../../../DEMO_CONTRACT.md).

## Output và đầu vào

Được sửa app/memory/{gateway,night,prompts}.py, tests/unit/memory/test_gateway.py, tests/integration/memory/{test_night,test_knowledge_agent_loop}.py, tests/fakes/knowledge.py, contracts/knowledge/*.json, một dòng docs/plans/toan/CODEX_LOG.md. D01 sở hữu domain/models/learning.py, store và Session metadata; báo thiếu interface theo tên, không tạo DTO bản thứ hai trong memory. D02a sở hữu dispatcher, D03 seller handler, member market sở hữu simulator/forecast. Task này không viết lại các module đó.

Đầu vào bắt buộc: DTO ở Knowledge contract, MemoryStore.get/put/list/commit_batch, Session rules authoritative và properties knowledge_revision/memory_cursor, EventLog.since, forecast snapshots trước settlement, DayMetrics, runner role learning và tool read_learning_evidence. Thiếu dependency thì inject fake đúng contract trong tests; integration thật vẫn là gate cần nối.

## 1. Gateway và retrieval — phút 0–6

Implement đúng chữ ký Knowledge contract mục 4. Platform_view/shop_view trả DTO; thêm content_view/read_learning_evidence/commit_memory_updates. Namespace theo run, deep-copy records khi đọc.

| View | Truy vấn | Kiểm xong |
|---|---|---|
| Platform | 5 history gần nhất, calibration đúng category, top 5 lessons mỗi scope strategy/category | Không Rules/preferences/cost/profit/private note |
| Shop | Rules hiện hành, preferences đúng shop | Memory OFF vẫn có Rules; không Persona |
| Content | Chỉ style đã seller xác nhận | Candidate không thành default creative prompt |
| Learning | Snapshot public evidence và lessons hiện tại | Không raw audit/DayMetrics/financials riêng |

Mỗi view ghi memory_read với record IDs/version; không log private payload. Native read_memory() từ D02a đã bind role/shop/run. Put/answer/commit không được đăng ký thành model tools. Tạo fixtures trong contracts/knowledge theo canonical; envelope source='fixture', payload parse bằng DTO.

## 2. Bốn ngăn học — phút 6–12

Run_night(session,day) chỉ sau simulate_day một lần. D03 giữ night receipt; có receipt thì trả summary cũ trước model/market. Chụp revision/cursor/event upper bound trước reflection.

```text
evidence = public_snapshot(run, day, cursor, through_seq)
history = derive_history(actual approved package + outcome + negotiation refs)
preferences = derive_candidates(real seller feedback/edit; dedup event seq)
calibration = update_same_day_samples(preissued snapshots, actual orders)
agent_result = run_agent('learning', ..., tools={'read_learning_evidence': bound_tool},
                        output_schema=LessonBatch, run_name=invocation_id)
# Runner: tool call → ToolMessage matching ID → finish_learning(LessonBatch)
batch = MemoryUpdateBatch(history, preferences, calibration, agent_result.value.ops, ...)
knowledge_commit = gateway.commit_memory_updates(batch, expected_revision, expected_cursor)
log public memory_write summaries and night_summary
return NightSummary from committed records + knowledge_commit.accepted_lesson_ops/rejected_ops
```

Candidate D: seller feedback có sáng/tối → content_style='ảnh nền sáng'. A headless: seller edit hạ voucher → voucher_max_pct='5' khi fixture có edit. Support chỉ từ seller events; candidate chưa sửa Rules.

History phân biệt proposed/agreed/approved. Approved_package lấy từ package_applied; không lấy output thương lượng làm gói đã chạy. Public outcome loại fees/profit/cost. Một negotiation ID một record có version; night sau cập nhật outcome từ evidence mới, không thêm record trùng.

Calibration do code tính cùng target_day, ratio actual/raw, raw>0, sample ID dedup, cửa sổ 30; đủ 5 mẫu mới đổi factor/quantiles. D1–D2 giữfactor=1. Member market cấp snapshot trước settlement; thiếu snapshot ghi skipped sample, không lấy forecast cả gói làm mẫu ngày.

Learning dùng OpenAI qua runner D02a, chung budget 64. Input ban đầu tối thiểu day/goal; model gọi read_learning_evidence(), nhận public events/lessons/valid IDs, rồi finish_learning trả LessonBatch tối đa 3 ops. Tối đa 3 model calls/invocation. Fallback cũng đọc evidence adapter, source offline; không giả native live call.

Thực hiện đủ ADD/UPVOTE/DOWNVOTE/EDIT theo Knowledge contract mục 5: scope/evidence/privacy/version/cap 30. Preference.evidence_seqs là int; LessonOp.evidence là negotiation ID thật. Không chữa evidence thiếu bằng ID bịa.

Bốn ngăn/cursor/revision commit một batch. Invalid LessonOp có thể bị reject rồi các records hợp lệ commit; lỗi kỹ thuật lúc commit phải rollback toàn batch. Rules không có trong writes. Memory OFF bỏ writes/reflection nhưng vẫn enforce Rules.

## 3. Seller confirmation và dùng lại — phút 12–16

D03 kiểm card/run/brief/version rồi gọi T10 confirm_preference, bên trong gateway.answer_pref. Field/value từ RuleQuestion đã phát hành, không từ model. Gọi dưới Session.lock, giữ active package.

- Yes/style: append chuẩn hóa một lần, status confirmed, rules_version+1; duplicate request không tăng tiếp.
- Yes/voucher: integer0..30, chỉ hạ cap hiện tại; test A headless, không mở thêm UI.
- No: declined, declined_until=day+14, Rules giữ nguyên.
- Mark_asked sau khi card đã tạo; threshold theo policy, không hỏi lại trước hạn im lặng.

Sau Yes ngày 2, chạy Content Agent với fake provider: ToolMessage từ get_content_context phải chứa confirmed style và output/prompt ảnh tiếp theo có nền sáng. Không sửa media đã publish hoặc tự tạo job trả phí chỉ vì xác nhận.

Kiểm Platform tiêu thụ history/lesson: fake model chỉ ra quyết định khi thấy record trong ToolMessage. Đổi public record hợp lệ rồi gọi lại, output phải đổi tương ứng. Source fixture/offline giữ nguyên; test này không chứng minh revenue uplift.

## 4. Test và bàn giao — phút 16–20

| Test bắt buộc | Kết quả |
|---|---|
| Five-bin views/run isolation | Đủ DTO; run/shop khác không lọt retrieval |
| Public evidence privacy | Sentinel cost/profit/private note/Persona không trong Platform/Content/Learning ToolMessage/public log |
| Native Learning loop | Fake AIMessage gọi tool → ToolMessage matching ID → model đọc evidence → finish_learning → validated commit |
| Lesson operations | ADD score 2, UP+1, DOWN đến 0 thì xóa, EDIT+1/version; evidence giả/private text/scope sai bị reject; cap 30 deterministic |
| Atomic batch | Storage failure/stale revision không đổi ngăn/cursor; retry receipt không nhân đôi |
| Calibration provenance | Cùng ngày, sample dedup; không chia outcome 1 ngày cho forecast 3 ngày; D1: points=1, factor=1 |
| Candidate/confirmation | Feedback→candidate; trước Yes Rules giữ nguyên; Yes đổi 1 lần; No im lặng14 ngày; A voucher test headless |
| Knowledge affects agent | Confirmed style đổi creative prompt; public history/lesson đổi quyết định Platform |
| Memory OFF | Rules còn; learned views rỗng; bốn ngăn không ghi; không reflection |
| Cross-day history | Ngày2 không có negotiation mới vẫn nối market_result→approved card/ngày1, dùng negotiation ID thật và không đếm lại support cũ |
| Night one-effect | Lần2 không settle/học/tăng ngày lại; trả receipt cũ |

Chạy .venv/bin/python -m pytest -q tests/unit/memory tests/integration/memory. Fake providers không gọi mạng. Review input thực/ToolMessage, không chỉ event memory_read. Chưa cấu hình live thì báo native tool adapter tested with fake; live smoke pending.

Bàn giao BASE_SHA/HEAD_SHA, fixtures parse, JSON NightSummary có nguồn, trace tool call→result IDs→final output, record trước/sau confirmation, kết quả test và dependency nào đã nối thật. Durable SQLite, phục hồi sau restart, runner đối chứng mặc định 6 ngày thuộc member/follow-up; không đặt chúng vào timebox Toàn hoặc tuyên bố đã chạy proof.
