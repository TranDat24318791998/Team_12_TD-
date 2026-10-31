# D02a — Vòng gọi tool thật cho năm agent

## Kết quả phải bàn giao

Model gọi tool bằng native function calling; backend kiểm quyền và input, chạy hàm, trả `ToolMessage`, rồi model dùng kết quả để quyết định. Không thay bằng một prompt đã nhét sẵn toàn bộ knowledge hoặc event mô phỏng rằng model đã gọi tool.

Đọc `AGENTS.md`, [hợp đồng Agent–Tool–Knowledge](../AGENT_TOOL_KNOWLEDGE.md), [hợp đồng demo](../../../DEMO_CONTRACT.md). D01 cung cấp model/finance/store; D04 cung cấp gateway thật. Trong lúc gateway chưa xong dùng fake đúng interface trong test; task chưa đạt nghiệm thu tích hợp cho tới khi nối gateway thật. Timebox và thứ tự lấy từ [plan](../README.md).

## Output được sửa

- `app/agents/__init__.py` rỗng; `app/agents/tools.py`, `app/agents/runner.py`.
- `app/infrastructure/llm.py` — transport OpenAI và hạn mức; không chứa logic shop/learning.
- `tests/fakes/llm.py`, `tests/fakes/agent_tools.py`.
- `tests/unit/agents/test_tools.py`, `tests/unit/agents/test_runner.py`, `tests/unit/infrastructure/test_llm.py`.
- `contracts/agent_tool_trace.json` — fixture ghi `source=fixture`, không nhận là live.
- Một dòng kết quả trong `docs/CODEX_LOG.md`.

D01 sở hữu model `PackageCheck`/`ShopPackageCheck` và DTO knowledge. D02 sở hữu prompt, graph và role callers. D04 sở hữu retrieval/học; D05 sở hữu content caller. Không xây plugin registry, MCP server hoặc agent tự sinh Python.

## 1. Interface dùng chung

```python
# app/agents/tools.py — nội bộ runtime, không thuộc domain
@dataclass(frozen=True)
class BoundTool:
    args_schema: type[BaseModel]
    execute: Callable[[BaseModel], BaseModel]
    output_schema: type[BaseModel]
    visibility: Literal["public", "shop_private"]

# app/agents/runner.py
@dataclass(frozen=True)
class AgentRun:
    value: BaseModel
    source: Literal["live", "replay", "offline"]
    tool_call_ids: list[str]
    error_code: str | None

run_agent(role, *, llm, tools, messages, output_schema,
          fallback, emit, run_name) -> AgentRun

# app/infrastructure/llm.py
LLMClient.invoke_tools(messages, *, tools, tool_choice,
                       parallel_tool_calls, run_name, model=None) -> AIMessage
```

`tools` là `dict[str, BoundTool]` do caller dựng từ role và run/shop hiện hành. `run_name` là ID duy nhất cho invocation, chứa run/negotiation hoặc card/day cùng role. `messages` là list LangChain message object; giữ nguyên `AIMessage` khi nối hội thoại để không làm mất metadata của provider. `fallback(dispatch)` trả domain output; `dispatch(name,args)` dùng cùng quyền, schema và projection với live. `emit` nhận event metadata đã lọc, không nhận raw private result. Fallback chỉ thử một lần; nếu adapter local tiếp tục lỗi, raise AgentToolError (định nghĩa app/agents/runner.py), caller chuyển negotiation failed/content failed/night no-commit. Không fallback đệ quy.

BoundTool closure giữ sẵn run/shop/day, gateway và hàm tính cần thiết. Input model chỉ có argument nghiệp vụ; mọi schema từ chối `role`, `run_id`, `shop_id`, namespace/path/URL tùy ý. Cả module chỉ cần mapping nhỏ viết rõ từng role; tên tool lấy từ bảng dưới.

| Role | Tool model được gọi | Output cuối |
|---|---|---|
| platform | `get_public_context`, `read_memory`, `validate_platform_package`, `forecast_package`, `search_campaign_catalog` | `finish_platform` → `PlatformTurn` |
| shop | `get_public_context`, `get_shop_private_context`, `read_memory`, `evaluate_shop_package` | `finish_shop` → `ShopTurn` |
| referee | `get_referee_context` | `finish_referee` → `RefereeDecision` |
| content | `get_content_context` | `finish_content` → `ContentText` |
| learning | `read_learning_evidence` | `finish_learning` → `LessonBatch{ops:list[LessonOp]}` tối đa 3 |

`read_memory` trả DTO khác nhau theo role đã bind; input rỗng `{}`. Các context/evidence tools cũng nhận `{}`. T04/T05/T06 nhận `{"package": Package}`; catalog nhận `{"query": str}` dài 0–200 ký tự (rỗng = mọi mẫu eligible), trả CampaignCatalogResult(items=...) tối đa 5 mẫu công khai đúng nguồn `data/campaigns.json`. Exact DTO/schema/evidence lấy từ hợp đồng Agent–Tool–Knowledge; không thêm alias `get_memory_view` hoặc `compute_financials`.

T07 và T09–T15 là adapter bắt buộc do code/workflow gọi. Chúng không có trong schema gửi model. Model không tự duyệt seller, sửa rules, commit memory, chạy job trả phí, append/read raw events hay áp dụng listing.

## 2. Transport OpenAI và schema

Dùng SDK hiện pin: `ChatOpenAI(model=..., timeout=8, max_retries=0).bind_tools(...)`. Hai lượt đọc đầu cho phép `parallel_tool_calls=True`, nhưng backend **thực thi tuần tự** tối đa 4 call trong một batch. Đây là batch read/compute, không tạo worker mới. Lượt cuối chỉ bind `finish_<role>`, `tool_choice="finish_<role>"`, `parallel_tool_calls=False`. Chỉ dùng function calling; không thêm chuỗi thử provider/API khác.

Schema tools và terminal dùng Pydantic `extra="forbid"`; chuyển thành OpenAI function schema với `strict=True`. Trước khi gửi, test schema sinh ra có `additionalProperties=false` ở mọi object và mọi property thuộc `required`; optional biểu diễn bằng nullable type, không bỏ key. Terminal parameters là field của output model, không bọc thêm key `result`. Không truyền default/constraint không được provider hỗ trợ rồi âm thầm nới schema. Nếu SDK conversion chưa đủ, sửa ở một helper nhỏ và test schema; không copy model sang từng feature.

Đã đối chiếu local `langchain-openai==1.7.3`: `bind_tools` hỗ trợ `tool_choice`, `strict`, `parallel_tool_calls`; `AIMessage` có `tool_calls`/`invalid_tool_calls`, `ToolMessage` có `tool_call_id`. Protocol call→execute→return output, strict schema và zero/one call khi tắt parallel được mô tả trong [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling). Model cụ thể vẫn lấy từ config và phải hỗ trợ tool calling; chưa có key/model thì chỉ hoãn live smoke.

Runner chọn `model=llm.settings.llm_model_reflect` cho role learning (trống thì llm_model); các role khác dùng llm_model. Không tạo client/budget mới cho reflection. Một `LLMClient` cho mỗi Session, `remaining_calls` là số duy nhất; default 64 trong cấu hình demo. Mỗi lần `invoke_tools` reserve một lượt trước request, kể cả request lỗi; một response chứa 4 tools vẫn là một model call. Chạy tool local không trừ model budget. Session.live_calls_left chỉ là property đọc client. Offline/replay không tự chuyển live; replay miss dùng fallback.

Lỗi mạng đầu tiên đặt client unavailable cho phần còn lại của run. Input/tool/schema lỗi chỉ kết thúc invocation hiện tại bằng fallback; không cần tắt model toàn run. Không giữ Session.lock qua network hoặc kéo raw prompt vào log.

## 3. Runner hữu hạn

Mỗi invocation tối đa **3 model calls**: tối đa 2 lượt đọc/tính, rồi 1 lượt trả kết quả cuối. Mỗi batch thường tối đa 4 tool calls. Model có thể finish sớm khi đủ prerequisite; chỉ accept một terminal call duy nhất, không trộn terminal với tool thường trong cùng response.

```text
messages = system + minimal task input
seen_call_ids = {}; successful = {}; traces = []
for model_step in range(3):
    schemas = permitted tools + terminal if model_step < 2 else terminal only
    choice = auto if model_step < 2 else terminal name
    response = llm.invoke_tools(messages, schemas, choice, parallel=(model_step < 2))
    prevalidate entire batch before executing any handler:
      valid call IDs, nonempty calls, no invalid_tool_calls, known names,
      <=4 ordinary calls, permitted role, args schema, terminal isolation
    if malformed/denied/budget/provider failure: return fallback through dispatch
    append original AIMessage to messages
    if single terminal:
      validate output schema + prerequisites + package semantics
      if valid: return AgentRun(output, actual source, trace IDs, None)
      otherwise: return fallback through dispatch
    for call in response.tool_calls in response order:
      execute role-bound handler; validate output model; record result fingerprint/refs
      append ToolMessage(tool_call_id=call.id, name=call.name, content=json(output))
      emit redacted tool_called/tool_result metadata
return fallback through dispatch  # no fourth model request
```

`invoke_tools` keyword names in code follow the interface in section 1; pseudocode abbreviates them for readability. Reject duplicate call IDs within/across batches before execution; never execute a repeated ID twice. Repeated reads under new IDs are allowed within the limit. Expected tool error returns a sanitized error ToolMessage if another model step remains; failed result does not satisfy prerequisites. Exception text, credentials and private payload never become public events. Once terminal is returned, no further model request is made, so a terminal ToolMessage is unnecessary.

Bound trước parse/execute: JSON UTF-8 arguments (kể cả terminal) tối đa16KiB/call; tool_call_id dài1–128ký tự; serialized validated tool result tối đa128KiB. Vượt bound trả TOOL_ARGUMENTS_TOO_LARGE hoặc TOOL_RESULT_TOO_LARGE; không truncate JSON/rules/evidence. Result lỗi không thỏa prerequisite. Giữ retrieval history<=5, lessons<=5mỗi scope (tổng10), catalog<=5. Snapshot Learning lớn quá thì invocation fallback offline đọc projection local; không tuyên bố limit này đủ cho mọi model/context window.

Inputs for a second batch may use outputs from the first. Tools within the same batch must be independent: platform may read public context/memory/catalog together, then validate and forecast the **same chosen package** together. Shop may read private context/memory together, then evaluate its proposal. Do not let a tool silently use the output of a previous call in its own batch as hidden arguments.

## 4. Prerequisites để output được coi là live

| Role | Kiểm tra trước khi nhận terminal |
|---|---|
| platform | Đã đọc T01/T03; initial propose đã tra catalog. Với propose/accept: T04 kiểm đúng package cuối và T06 forecast đúng package đó; withdraw không cần package checks |
| shop | Đã đọc T02/T03; T05 đã evaluate input proposal và returned safe candidate. Accept giữ nguyên proposal; counter chỉ dùng package đã qua kiểm sau sửa |
| referee | Đã đọc context gồm đúng brief/turn IDs của invocation; evidence refs trong output đều tồn tại |
| content | Đã đọc facts/style/feedback context hiện hành; claim dùng facts đã xác minh; chỉ trả chữ và checks |
| learning | Đã đọc public evidence đúng run/day/cursor cùng lessons; output đúng LessonBatch, tối đa3ops; gateway kiểm từng op scope/evidence/privacy, không loại cả batch vì một op sai |

Gắn kết quả T04/T05/T06 với fingerprint canonical JSON của `Package`. T04/T05 chỉ đánh dấu corrected package là đã kiểm khi `violations_after` rỗng; T06 phải tính trên package final, không reuse forecast của gói trước clamp. Các gate nghiệp vụ ngoài runner vẫn kiểm lại output cuối. Nếu model đổi package ở terminal mà chưa kiểm/forecast đúng gói, fallback; không tạo tool event giả để lấp prerequisite.

Fallback gọi cùng adapter và lấy knowledge hiện tại, chạy luật deterministic của từng role; record `source=offline` và `requested_by=workflow`, không gắn model tool_call_id. Chỉ khi AIMessage thực sự yêu cầu tool thì event có `requested_by=model`. Có partial live calls rồi fallback thì outcome cuối offline, trace vẫn phản ánh các lần gọi trước thật.

## 5. Evidence và privacy của trace

`tool_called/tool_result` giữ run/invocation/negotiation/card IDs, actor, tool_name, tool_call_id nếu model gọi, source, status, record_refs (opaque IDs, không encode private values), elapsed_ms, requested_by=model|workflow. Kết quả dùng trace fixture trong test và event stream demo. ToolMessage riêng chỉ ở invocation đúng role; output T02/T05 không được serialize lên public events hoặc chuyển vào messages của role tiếp theo.

Sàn/trọng tài chỉ thấy record IDs và dữ liệu công khai; UI có thể hiện “Shop đọc luật riêng; kiểm gói thành công”, không hiện cost/profit/cap riêng từ raw result. `sanitize_shop_reply` vẫn chạy ở graph trước public transcript. Không ghi toàn bộ messages vào CODEX_LOG hoặc replay cache chung.

## 6. Test và nghiệm thu

| Test | Điều phải chứng minh |
|---|---|
| `test_real_tool_protocol` | Fake model trả AIMessage.tool_calls; handler thực chạy; model request tiếp theo chứa ToolMessage đúng call ID; output cuối đọc giá trị tool trả |
| `test_changed_tool_result_changes_decision` | Giữ prompt/model fake, đổi allowed cap của fake T05; fake model đọc ToolMessage để chọn safe package khác; không hardcode response cuối |
| `test_role_allowlist_before_dispatch` | Platform gọi T02/T05 hoặc T09: handler spy không được gọi; fallback/redacted error, không rò dữ liệu |
| `test_arguments_cannot_change_scope` | Extra shop_id/role/run_id/namespace bị từ chối; không truy cập shop khác |
| `test_duplicate_or_mixed_terminal_batch` | Call ID trùng hoặc finish cùng read call bị chặn trước khi chạy bất kỳ handler trong batch |
| `test_terminal_requires_current_package_checks` | Đổi voucher sau forecast/check → fallback; output final vẫn qua code validators |
| `test_three_model_calls_and_shared_budget` | Model chỉ đọc lặp: tối đa 3 request, lần3 chỉ finish; budget reserve từng request; không có request4 |
| `test_private_tool_results_are_local` | Sentinel T02/T05 chỉ ở messages shop; absent khỏi public events, platform/referee messages và fixture xuất công khai |
| `test_schema_strict_objects` | Mọi schema gửi bind_tools có required/all fields, extra forbid và nullable optional; package nested hợp lệ |
| `test_adapter_failure_is_controlled` | Tool local lỗi cả lần live và fallback: AgentToolError, không gọi vô hạn hoặc commit dữ liệu thiếu |
| `test_unconfigured_and_failure_are_offline` | Thiếu key/network error: adapters vẫn chạy qua fallback, outcome/trace offline; không phát event live giả |

Chạy `.venv/bin/python -m pytest -q tests/unit/agents tests/unit/infrastructure/test_llm.py`. Bàn giao một transcript fake có cả AIMessage tool request và ToolMessage result đã lọc; live smoke sau khi có config ghi riêng. Reviewer chặn nếu chỉ thấy `with_structured_output` một lần hoặc log tool do code bịa, dù output package đúng.
