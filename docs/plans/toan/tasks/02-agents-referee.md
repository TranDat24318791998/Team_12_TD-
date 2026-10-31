# D02 — Agent thương lượng, trọng tài và graph dùng tool

## Kết quả phải bàn giao

Một lời gọi `run_negotiation(session, "D", 1, "propose")` offline trả gói **45.000đ/ngày, voucher 3%, stop 6,5**, chốt ở lượt sàn thứ 2. Event log có lượt sàn, lượt shop, kiểm tra code, đánh giá trọng tài và trace tool thật. Khi chạy live, từng role gọi runner D02a để đọc context/knowledge, gọi hàm tính và nhận kết quả trước khi quyết định. Lời gọi này chưa tạo card, chưa kích hoạt gói, chưa trừ ngân sách.

Thứ tự/timebox lấy từ [plan](../README.md). Phụ thuộc D01 và [D02a](02a-tool-runtime.md); D04 cấp typed memory gateway, có thể dùng fake cùng interface lúc ghép. Giữ cả đường native tool calling và fallback. Nếu quá giờ, cắt UI/phần ghép ngoài phạm vi trước; không đánh dấu agent hoàn thành khi mới có structured output một lần hoặc riêng fallback.

## Đọc và phạm vi sửa

Đọc `AGENTS.md`, [hợp đồng Agent–Tool–Knowledge](../AGENT_TOOL_KNOWLEDGE.md), [hợp đồng demo](../../../DEMO_CONTRACT.md), `docs/SEED_DATA.md` mục 3–5 và `tasks/TV1-1.5-thuong-luong.md`. Hợp đồng demo quyết định phạm vi mới; task cũ chỉ tham khảo cách tính và chữ ký.

Chỉ sửa/tạo:

- `app/negotiation/agents.py`, `prompts.py`, `graph.py`, `referee.py`.
- `tests/unit/negotiation/test_negotiation.py`, `test_isolation.py`, `test_referee.py`.
- Một dòng bàn giao trong `docs/plans/toan/CODEX_LOG.md`.

Model, seed, finance, validators, privacy, Session và EventLog do D01 cấp. Runner, tool bindings và OpenAI transport do D02a cấp; không viết bản runner thứ hai trong graph. Nếu thiếu, báo đúng tên interface; chỉ dùng fake trong test, không tạo một model trùng trong feature. Giữ nguyên requirements đã cài. Content và Learning không gọi ở task này.

## Interface cần dùng

```python
# agents.py — giữ interface hiện hành
decide_platform(session, shop_id, turns, memory_view) -> PlatformTurn
decide_shop(session, shop_id, proposal, memory_view, owner_note) -> ShopTurn

# referee.py — tools đã bind public-only; không nhận Session hoặc ShopPrivate
review_turn(brief_public, turns, *, llm, tools, emit) -> RefereeDecision

# graph.py
run_negotiation(session, shop_id, day, kind, owner_note=None) -> NegotiationResult

# app/agents/runner.py — D02a cung cấp
run_agent(role, *, llm, tools, messages, output_schema,
          fallback, emit, run_name) -> AgentRun
```

Cả năm role dùng chung runner và `session.llm`; ngân sách model 64 lần/run theo D02a. `memory_view` trong hai chữ ký cũ giữ để caller tích hợp không gãy, nhưng live không dùng để nạp sẵn knowledge vào prompt: T03 phải đọc gateway hiện hành qua tool. Fallback cũng gọi cùng các adapter; không dựa vào bản memory cũ được truyền từ trước. `AgentRun.value` phải là model của role, không phải dict chưa kiểm kiểu. Role caller lưu source/trace metadata vào event; trả nguyên interface PlatformTurn/ShopTurn cho graph.

`PlatformTurn` và `ShopTurn` dùng Package của domain. `RefereeDecision` lấy từ hợp đồng demo: action, lý do ngắn, evidence refs, điều khoản chưa thống nhất và người cần trả lời. Không bắt model trả suy luận nội bộ.

## 1. Context lấy qua tool, quyền do backend gắn

Trong `prompts.py`, dựng input mở đầu nhỏ từ brief công khai, role, lượt và public transcript; shop được nhận proposal/owner_note đúng shop. Context đầy đủ lấy khi model gọi tool:

| Role | Batch đọc đầu | Batch kiểm/tính tiếp theo | Terminal |
|---|---|---|---|
| Sàn | T01 `get_public_context`, T03 `read_memory`, `search_campaign_catalog` khi đề xuất đầu | T04 `validate_platform_package` và T06 `forecast_package` cùng package | `finish_platform` |
| Shop | T02 `get_shop_private_context` và T03 `read_memory`; T01 nếu cần facts công khai | T05 `evaluate_shop_package` với proposal | `finish_shop` |
| Trọng tài | `get_referee_context` gồm brief/public turns và mã kiểm tra | Không cần tài chính riêng | `finish_referee` |

D02a thực thi schema/allowlist; role callers dựng BoundTool closures từ run/shop/ngày hiện hành. T01/T03 lấy public history, calibration và lessons cho sàn. T02/T03 chỉ lấy private/rules/preferences của shop đang chạy. T05 tính financials, safe candidate và violations bằng code. Shop/sàn không được model tự chọn namespace hoặc đổi shop bằng args.

Sàn/trọng tài không nhận Session, World, SellerPersona, private_note, private memory hoặc tài chính riêng. Shop cũng không nhận Persona. Trọng tài chỉ được bind wrapper có public DTO đã lọc, không nhận closure raw T02/T05. `review_turn` dựng run_name từ IDs public và gọi runner với `RefereeDecision`.

System prompt ngắn, nêu nhiệm vụ và điều kiện tool trước terminal; không yêu cầu chuỗi suy luận nội bộ. Prompt sàn nói đọc catalog/memory trước chọn gói; prompt shop nói đọc luật và evaluate trước phản hồi; referee chỉ tham chiếu evidence thật. Prompt không nhét sẵn toàn bộ memory để làm tool retrieval trở thành hình thức.

## 2. Viết offline trước

Sàn ở lượt đầu dùng lịch sử gói đã áp dụng nếu có; chưa có thì copy `DEFAULT_PACKAGE`, không sửa dict hằng số tại chỗ. P0 chỉ nhận intent `increase_orders`, `allow_ads=true`, `content_refresh=true`, `duration_days=3`; API chặn intent khác bằng lỗi không hỗ trợ. `ads_daily_cap` công khai mặc định null, không sao chép trần riêng 45.000đ của shop vào brief. Nếu seller đã công khai một cap thì code tôn trọng cap đó. Demo mặc định vẫn mở đầu 70.000đ để thấy shop counter bằng luật riêng.

Sàn nhận counter hợp luật sàn thì trả `accept` **đúng package counter**. `accept` mà sửa một field là đề xuất mới; không xem như đồng thuận.

Shop gọi T05; T05 tính `safe = clamp_to_rules(proposal, ...)` và tài chính bằng code:

1. `safe is None`: reject với lý do công khai.
2. Gói gốc không vi phạm và `safe == proposal`: accept giữ nguyên package.
3. Còn lại: counter bằng `safe`; message nêu các điều khoản được chào, không nêu luật riêng đầy đủ.

Demo D: sàn 70.000 / 10% / 4 → shop counter 45.000 / 3% / 6,5 → sàn accept. Dùng finance để ra kết quả, không hardcode tên shop trong nhánh thương lượng.

Fallback sàn vẫn đọc T01/T03/catalog và gọi T04/T06; fallback shop đọc T02/T03 và gọi T05 qua dispatch D02a, ghi source offline. Các tính toán không hardcode trong prompt. Mọi output từ shop đi qua T07 `sanitize_shop_reply`/`leak_guard` do graph bắt buộc gọi, kể cả fallback. Giữ `private_note_vi` trong kết quả nội bộ cho shop nếu cần; không đưa trường này vào public transcript hoặc event stream của demo.

Ngoại lệ task cũ cho A accept khi riêng stop thay đổi không áp dụng ở slice này: package thay đổi luôn là counter. Demo chính chỉ kiểm D; không thay seed để tạo chốt lượt 1 giả.

## 3. Nối runner vào role callers

Mỗi caller tạo tool mapping đúng role, `messages` tối thiểu, terminal schema và hàm offline. Gọi `run_agent(...)` một lần; runner tự làm tối đa ba model calls gồm tool requests, ToolMessages và terminal. Không gọi `with_structured_output` riêng sau runner vì sẽ vượt budget và bỏ trạng thái tools đã đọc.

`finish_platform`/`finish_shop` chỉ tạo đề xuất, không thực thi gói. Gate D02a xác minh các tool prerequisite và package fingerprint; graph tiếp tục kiểm semantics: propose có package, accept đúng candidate, shop package qua hard rules. Output sai thì dùng offline cho lượt hiện tại, không auto-agree sau clamp.

Live LLM không bị ép diễn transcript offline. Gói khác 45k/3/6.5 vẫn được dùng nếu đã qua tool checks, bám brief và được hai phía đồng thuận đúng semantics. Với `source=offline`, D vẫn phải chốt đúng fixture. Dữ liệu catalog có nhãn sample; sàn không gọi đó là chương trình thật đang chạy.

Cách cấu hình, schema strict, budget, lỗi provider và trace nằm tại D02a. Giữ nguyên `AIMessage`/`ToolMessage` trong một invocation; qua role khác chỉ truyền `PublicTurn` đã lọc. Không mang private messages shop sang trọng tài hoặc sàn.

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

Trọng tài được gọi sau cả lượt sàn lẫn lượt shop: tối đa `3 × (1 sàn + 1 shop + 2 trọng tài) = 12` **role invocations** mỗi negotiation. Mỗi invocation tối đa 3 model calls qua runner, nên trần là 36 model calls; D chốt ở sàn lượt 2 có 6 invocations, tối đa 18 calls. Content/Learning dùng tiếp cùng budget 64 của phiên. Mỗi request timeout8s, do đó trường hợp chạm trần có thể lâu; không hứa 3 phút bao gồm model/media latency.

Với runtime LangGraph hiện cài, dùng StateGraph, conditional edges và `compile()`; không cần checkpointer cho cuộc thương lượng chạy hết trong một request. Human approval ở runtime day; không đặt `interrupt()` trong graph này. Đặt recursion_limit đủ cho tối đa ba vòng và toàn bộ check/review nodes, ví dụ 64; giới hạn nghiệp vụ vẫn là MAX_ROUNDS=3.

`finalize_agreed`: kiểm lại cả luật sàn và shop, gọi forecast nếu market đã có, trả NegotiationResult. Chưa có market trong lúc ghép thì `forecast=None`; không tự điền số mẫu vào kết quả thật. `finalize_failed` có `final_package=None`, `forecast=None`, lý do tiếng Việt ngắn.

## 6. Event và quyền đọc

Runner ghi `tool_called`, `tool_result` đã lọc theo D02a; graph ghi `platform_turn`, `shop_turn`, `referee_review`, `code_check`; dữ liệu có negotiation ID, turn ID nếu có, round, brief version và output công khai. `code_check` ghi mã kiểm tra và pass/fail; không đưa raw financials hoặc trần rules riêng vào text/data public.

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
| `test_roles_use_tool_results_before_finish` | Fake native AIMessage gọi các tool đúng role rồi đọc ToolMessage để trả terminal; gateway/finance spies thực chạy, final package đúng output checker; mỗi request trừ chung budget |
| `test_retrieved_memory_changes_next_offer` | Giữ seed/brief, thay public history hoặc lesson qua gateway; fake model đọc T03 result rồi chọn gói khác đã qua T04/T06; trace chứng minh knowledge đã được dùng, không chỉ ghi log |
| `test_provider_failure_uses_offline` | Fake client timeout: không gọi mạng thật; D vẫn ra gói hợp lệ; source offline; ngân sách giảm chỉ cho lần thử live |
| `test_accept_is_not_stalled_counter` | Shop counter rồi sàn accept cùng package: referee không đánh dấu lặp, D vẫn agreed |

Chạy `.venv/bin/python -m pytest -q tests/unit/negotiation tests/unit/agents`, rồi toàn bộ `pytest -q` một lần khi ghép với D04. Không viết test snapshot dài cho wording prompt; kiểm dữ liệu, quyền và chuyển trạng thái.

## Prompt giao coder

> Làm D02 theo file này, docs/plans/toan/AGENT_TOOL_KNOWLEDGE.md và docs/DEMO_CONTRACT.md. Nối runner D02a vào ba role rồi hoàn thành graph D, dùng fake native tool responses để test. Giữ Output, báo thiếu interface bằng tên cụ thể; chưa mở rộng sang seller approval/content. Bàn giao danh sách file, test/result, một transcript D ngắn và phần chưa làm. Không tự push hoặc sửa contract.

## Checklist cho reviewer

Đọc các test ở trên và chạy lại test trọng tâm. Chặn bàn giao nếu có rò private, sai 45k/3/6.5, đồng thuận sau clamp chưa được actor accept, vòng không kết thúc, thiếu native tool loop, knowledge chỉ được nhét sẵn vào prompt, hoặc gọi provider thật trong test. Cache nâng cao và smoke test live khi chưa có key được ghi deferred; fallback không thay cho code tích hợp provider. Đọc input thực của fake LLM; đừng chỉ tìm từ khóa trong prompt.
