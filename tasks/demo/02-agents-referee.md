# DEMO-02 — Hai agent thương lượng và trọng tài

## Kết quả phải bàn giao

Một lời gọi `run_negotiation(session, "D", 1, "propose")` offline trả gói **45.000đ/ngày, voucher 3%, stop 6,5**, chốt ở lượt sàn thứ 2. Event log có lượt sàn, lượt shop, kiểm tra code và đánh giá trọng tài. Lời gọi này chưa tạo card, chưa kích hoạt gói, chưa trừ ngân sách.

Timebox: **20 phút**. Hoàn thành đường offline trong 12 phút đầu, sau đó nối OpenAI và kiểm thử bằng fake client. Adapter live thuộc phần phải code; thiếu key chỉ hoãn smoke test mạng thật. Nếu quá timebox, bàn giao chính xác phần chưa xong để điều phối cắt phần khác; không đánh dấu task hoàn thành bằng riêng fallback.

## Đọc và phạm vi sửa

Đọc `AGENTS.md`, [hợp đồng demo](../../docs/DEMO_CONTRACT.md), `docs/SEED_DATA.md` mục 3–5 và `tasks/TV1-1.5-thuong-luong.md`. Hợp đồng demo quyết định phạm vi mới; task cũ chỉ tham khảo cách tính và chữ ký.

Chỉ sửa/tạo:

- `app/negotiation/agents.py`, `prompts.py`, `graph.py`, `referee.py`.
- `app/infrastructure/llm.py`.
- `tests/fakes/llm.py`.
- `tests/unit/negotiation/test_negotiation.py`, `test_isolation.py`, `test_referee.py`.
- `tests/unit/infrastructure/test_llm.py`.
- Một dòng bàn giao trong `docs/CODEX_LOG.md`.

Model, seed, finance, validators, privacy, Session và EventLog do DEMO-01 cấp. Nếu thiếu, báo đúng tên interface; chỉ dùng fake trong test, không tạo một model trùng trong feature. Giữ nguyên requirements đã cài. Content và Learning không gọi ở task này.

## Interface cần dùng

```python
# agents.py — giữ interface hiện hành
decide_platform(session, shop_id, turns, memory_view) -> PlatformTurn
decide_shop(session, shop_id, proposal, memory_view, owner_note) -> ShopTurn

# referee.py — input public, không nhận Session hoặc ShopPrivate
review_turn(brief_public, turns, *, llm) -> RefereeDecision

# graph.py
run_negotiation(session, shop_id, day, kind, owner_note=None) -> NegotiationResult

# infrastructure/llm.py
LLMClient(settings).structured(schema, system, user, *, run_name,
                               model=None) -> tuple[object | None, str | None]
```

Một `LLMClient` riêng cho mỗi Session; `remaining_calls` khởi tạo bằng `settings.max_live_calls_per_session`. `Session.live_calls_left` là property đọc từ client, không giữ bộ đếm thứ hai. Cả năm vai trò dùng cùng client. `schema` là class Pydantic, `system` và `user` là chuỗi. `err=None` khi nhận output hợp lệ. Không trả dict chưa kiểm kiểu cho caller.

`PlatformTurn` và `ShopTurn` dùng Package của domain. `RefereeDecision` lấy từ hợp đồng demo: action, lý do ngắn, evidence refs, điều khoản chưa thống nhất và người cần trả lời. Không bắt model trả suy luận nội bộ.

## 1. Dựng input theo allowlist

Tạo ba hàm trong `prompts.py`, mỗi hàm trả dict trước khi `json.dumps`:

```python
build_platform_input(public, brief_public, memory_view, turns_redacted) -> dict
build_shop_input(public, private, rules_view, proposal, owner_note, computed) -> dict
build_referee_input(brief_public, turns_redacted) -> dict
```

- Sàn: ShopPublic, mục tiêu đã xác nhận, hạn mức người bán chủ động công khai, lịch sử công khai, lượt thương lượng đã lọc.
- Shop: đúng ShopPrivate của D, rules hiện hành, proposal, ghi chú seller và `computed` do code tính.
- Trọng tài: brief công khai, package diff, turn IDs, thông điệp đã lọc; thông tin khả thi tài chính chỉ là `pass/fail` hoặc reason code công khai.
- `computed` gồm lãi/đơn, hòa vốn, voucher tối đa, gói sửa và violations từ finance/validators; agent shop không tự tính số.
- Không đưa Session, World, SellerPersona, `private_note_vi`, memory riêng hay kết quả tài chính riêng vào input sàn/trọng tài.

System prompt ngắn, tiếng Việt, một nhiệm vụ và schema output. Shop bảo vệ ràng buộc; sàn phục vụ goal đã xác nhận; trọng tài đánh giá bám goal và tiến triển. Chưa xây chat history ngoài cuộc thương lượng hiện tại.

## 2. Viết offline trước

Sàn ở lượt đầu dùng lịch sử gói đã áp dụng nếu có; chưa có thì copy `DEFAULT_PACKAGE`, không sửa dict hằng số tại chỗ. P0 chỉ nhận intent `increase_orders`, `allow_ads=true`, `content_refresh=true`, `duration_days=3`; API chặn intent khác bằng lỗi không hỗ trợ. `ads_daily_cap` công khai mặc định null, không sao chép trần riêng 45.000đ của shop vào brief. Nếu seller đã công khai một cap thì code tôn trọng cap đó. Demo mặc định vẫn mở đầu 70.000đ để thấy shop counter bằng luật riêng.

Sàn nhận counter hợp luật sàn thì trả `accept` **đúng package counter**. `accept` mà sửa một field là đề xuất mới; không xem như đồng thuận.

Shop tính `safe = clamp_to_rules(proposal, ...)`:

1. `safe is None`: reject với lý do công khai.
2. Gói gốc không vi phạm và `safe == proposal`: accept giữ nguyên package.
3. Còn lại: counter bằng `safe`; message nêu các điều khoản được chào, không nêu luật riêng đầy đủ.

Demo D: sàn 70.000 / 10% / 4 → shop counter 45.000 / 3% / 6,5 → sàn accept. Dùng finance để ra kết quả, không hardcode tên shop trong nhánh thương lượng.

Mọi output từ shop đi qua `leak_guard`, kể cả fallback. Giữ `private_note_vi` trong kết quả nội bộ cho shop nếu cần; không đưa trường này vào public transcript hoặc event stream của demo.

Ngoại lệ task cũ cho A accept khi riêng stop thay đổi không áp dụng ở slice này: package thay đổi luôn là counter. Demo chính chỉ kiểm D; không thay seed để tạo chốt lượt 1 giả.

## 3. LLM tối thiểu, hai đường chạy rõ ràng

**Đường A — offline/cache:** offline trả `(None, "offline")`; replay đọc cache nếu đã có, miss trả `(None, "cache_miss")`. Agent dùng luật offline. Replay không được tự đổi thành live.

**Đường B — live:** OpenAI là provider duy nhất cho cả năm vai trò LLM. Chỉ thử khi có key, model, budget>0 và client còn available. Dùng `ChatOpenAI(..., timeout=8, max_retries=0)` với `with_structured_output(schema)`. Chỉ một lần thử; SDK/provider lỗi, timeout hoặc output không hợp schema thì trả lỗi ngắn và dùng offline cho lượt đó. Dùng model từ config, không tự điền key/model thật hay thêm provider khác.

- Trừ `LLMClient.remaining_calls` ngay trước mỗi lần gọi mạng, kể cả lần gọi thất bại. `Session.live_calls_left` phản ánh cùng giá trị; cache/fallback không trừ ngân sách.
- Lỗi mạng/timeout đầu tiên đặt `available=False` cho phần còn lại của phiên demo, tránh cộng nhiều timeout liên tiếp.
- Không làm vòng thử lần lượt JSON schema/function calling/prompt JSON. Không tự đọc một đoạn văn thành package.
- Nếu cache chưa có, vẫn phải chạy offline; cache là tùy chọn. Không làm replay branching ở task này.
- Không đưa prompt private vào log chung. Event chỉ ghi mode thật đã sử dụng, tên agent và reason code fallback.

Output LLM đúng schema vẫn phải kiểm semantics. Sàn propose thiếu package, shop accept gói sai luật, accept khác candidate, hoặc action không khớp trạng thái đều bị thay bằng output offline cho đúng lượt rồi qua validators. Không auto-agree sau clamp.

## 4. Trọng tài là node tư vấn có giới hạn

Fallback deterministic:

| Tình huống | action | Xử lý |
| --- | --- | --- |
| Package trái intent/ràng buộc công khai | `refocus` | Chỉ rõ field lệch; agent kế tiếp dùng ràng buộc brief |
| Cùng package và cùng bất đồng lặp lại, không có thay đổi | `stop` | Kết thúc failed; không gọi tiếp model |
| Brief thiếu xác nhận hoặc cần seller đổi mục tiêu | `ask_human` | Kết thúc failed kèm câu hỏi, không tự sửa brief |
| Đang có tiến triển hoặc đã đồng thuận hợp lệ | `continue` | Đi tiếp theo route bằng code |

Chỉ so package với counter gần nhất khi xét lặp. Platform `accept` đúng counter không phải lặp bế tắc. Bỏ mọi evidence ref không thuộc turn IDs thật của cuộc hiện tại; nếu không còn evidence hợp lệ, dùng fallback review.

Trọng tài không được sửa package, rules, budget, stock hoặc approval. Graph quyết định route. `refocus` không tạo thêm lượt ngoài MAX_ROUNDS; chỉ truyền focused question cho lần gọi hợp lệ tiếp theo. `ask_human`/`stop` ở MVP trả failed và lời giải thích; UI cho sửa brief hoặc reset, chưa hỗ trợ resume vào giữa một turn.

Ví dụ response sau shop counter hợp lệ; thay IDs bằng lượt đang chạy:

```json
{
  "action": "continue",
  "reason_vi": "Phản đề xuất vẫn phục vụ mục tiêu tăng đơn và đã làm rõ các điều khoản.",
  "evidence_refs": ["run1:D:1:1:shop:1"],
  "unresolved_terms": ["ads_daily_budget", "voucher_pct", "stop_roas_below"],
  "next_actor": "platform",
  "focused_question": "Sàn có chấp nhận gói phản đề xuất này không?"
}
```

## 5. Graph nhỏ, state hữu hạn

`NegotiationState` là TypedDict nội bộ trong `graph.py`: `shop_id`, `negotiation_id`, `day`, `kind`, `round`, `turns`, `candidate`, `last_shop_turn`, `referee_decision`, `result`. Session được truyền qua closure khi dựng graph; không cho model nhận graph state nguyên khối.

`turns` chỉ chứa DTO công khai `{turn_id, actor, round, action, package, message_vi}`. Dùng ID `{negotiation_id}:platform:1`, `{negotiation_id}:shop:1`; negotiation ID phải phân biệt attempt do runtime cấp. Node trả list mới thay vì sửa list chung giữa các run.

```text
START → platform_turn → check_platform → referee_platform
  referee stop/ask_human → finalize_failed → END
  platform accept đúng counter + final_check OK → finalize_agreed → END
  platform withdraw → finalize_failed → END
  còn lại → shop_turn → check_shop → referee_shop
    referee stop/ask_human → finalize_failed → END
    shop accept đúng candidate + final_check OK → finalize_agreed → END
    shop reject → finalize_failed → END
    shop counter AND round < MAX_ROUNDS → platform_turn
    shop counter AND round == MAX_ROUNDS → finalize_failed → END
```

`platform_turn` tăng round đúng một lần. Shop/referee không tăng round. `check_*` phải xử lý output invalid bằng offline hoặc fail rõ, không để node lặp tự sửa vô hạn. Nếu review `refocus` ngay trước một accept, không finalize accept; fallback actor tạo quyết định theo brief rồi kiểm lại một lần, không gọi LLM mới. Nếu vẫn lệch thì failed.

Trọng tài được gọi sau cả lượt sàn lẫn lượt shop: tối đa `3 × (1 sàn + 1 shop + 2 trọng tài) = 12` lần gọi LLM mỗi negotiation; D chốt ở sàn lượt 2 cần tối đa 6 lần. Content/Learning dùng tiếp cùng ngân sách 40 lần của phiên. Đây là trần, không phải mục tiêu sử dụng hết.

Với runtime LangGraph hiện cài, dùng StateGraph, conditional edges và `compile()`; không cần checkpointer cho cuộc thương lượng chạy hết trong một request. Human approval ở runtime day; không đặt `interrupt()` trong graph này. Đặt recursion_limit đủ cho tối đa ba vòng và toàn bộ check/review nodes, ví dụ 64; giới hạn nghiệp vụ vẫn là MAX_ROUNDS=3.

`finalize_agreed`: kiểm lại cả luật sàn và shop, gọi forecast nếu market đã có, trả NegotiationResult. Chưa có market trong lúc ghép thì `forecast=None`; không tự điền số mẫu vào kết quả thật. `finalize_failed` có `final_package=None`, `forecast=None`, lý do tiếng Việt ngắn.

## 6. Event và quyền đọc

Ghi `platform_turn`, `shop_turn`, `referee_review`, `code_check`; dữ liệu có negotiation ID, turn ID nếu có, round, brief version và output công khai. `code_check` ghi mã kiểm tra và pass/fail; không đưa raw financials hoặc trần rules riêng vào text/data public.

Mọi message/reason/evidence text sắp xuất public qua projection + leak_guard. DTO allowlist bảo vệ field; leak_guard bảo vệ chữ. Trọng tài chỉ đọc transcript đã qua cả hai bước. Event fallback ghi `source="offline"` hoặc `source="live"` thực tế của lượt, không gắn nhãn AI live cho câu theo luật.

## 7. Test tối thiểu phải qua

| Test | Setup và khẳng định |
| --- | --- |
| `test_d_agrees_second_platform_turn` | Seed D, brief mặc định, offline: round=2, 45k/3/6.5, kết quả qua hai validator; session chưa có ActivePackage |
| `test_private_context_never_reaches_platform_or_referee` | Fake LLM lưu mọi input; duyệt input hai role, không có private keys, Persona, giá vốn 115000, min profit18000 hoặc private_note |
| `test_shop_text_is_redacted_before_next_actor` | Fake shop output chứa `giá vốn 115.000đ`; input sàn/referee và public events không còn chuỗi này |
| `test_invalid_accept_becomes_safe_counter` | Shop fake accept gói70k/10/4: không agreed gói đó; counter qua code và eventual safe result |
| `test_referee_stops_drift_without_mutating_brief` | Brief tăng đơn có cap công khai40.000đ, fake offer vượt cap: review/fallback bám đúng field và evidence thật; không apply offer vượt cap, brief giữ nguyên, graph kết thúc hữu hạn |
| `test_round_limit_counts_platform_only` | Fake actors counter mãi: số platform_turn <=3; failed không có final_package |
| `test_openai_live_uses_schema_and_shared_budget` | Inject fake ChatOpenAI, trả object đúng schema; kiểm model từ config, timeout8, max_retries0, có gọi invoke đúng prompt; client remaining_calls giảm1 và Session property phản ánh cùng số |
| `test_provider_failure_uses_offline` | Fake client timeout: không gọi mạng thật; D vẫn ra gói hợp lệ; source offline; ngân sách giảm chỉ cho lần thử live |
| `test_accept_is_not_stalled_counter` | Shop counter rồi sàn accept cùng package: referee không đánh dấu lặp, D vẫn agreed |

Chạy `.venv/bin/python -m pytest -q tests/unit/negotiation tests/unit/infrastructure/test_llm.py`, rồi toàn bộ `pytest -q` một lần khi bàn giao. Không viết test snapshot dài cho wording prompt; kiểm dữ liệu, quyền và chuyển trạng thái.

## Prompt giao coder

> Làm DEMO-02 theo file này và docs/DEMO_CONTRACT.md. Bắt đầu offline D, sau đó hoàn thành adapter OpenAI và fake tests. Giữ Output, báo thiếu interface bằng tên cụ thể; chưa mở rộng sang seller approval/content. Bàn giao danh sách file, test/result, một transcript D ngắn và phần chưa làm. Không tự push hoặc sửa contract.

## Checklist cho reviewer

Đọc các test ở trên và chạy lại test trọng tâm. Chặn bàn giao nếu có rò private, sai 45k/3/6.5, đồng thuận sau clamp chưa được actor accept, vòng không kết thúc, thiếu adapter OpenAI hoặc gọi provider thật trong test. Cache nâng cao và smoke test live khi chưa có key được ghi deferred; fallback không thay cho code tích hợp provider. Đọc input thực của fake LLM; đừng chỉ tìm từ khóa trong prompt.
