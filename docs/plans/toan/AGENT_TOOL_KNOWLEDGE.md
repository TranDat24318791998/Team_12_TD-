# Hợp đồng Agent và Tools

Cập nhật 31/10/2026: phần Toàn là agent, điều phối, tools và Knowledge. Năm ngăn memory có schema tại [KNOWLEDGE_CONTRACT](KNOWLEDGE_CONTRACT.md); nguồn phân công và mapping workbook tại [AGENT_SCOPE_MAP](AGENT_SCOPE_MAP.md). Tình trạng triển khai và các đầu nối còn chờ member khác được ghi trong [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).

## 1. Module và luồng gọi

```text
runtime.day (goal, run/shop/day, approval)
  → negotiation.graph (platform ↔ shop, referee)
      → app.agents.runner.run_agent(role, ...)
          → OpenAI tool_calls
          → app.agents.tools: role allowlist + args validation
          → domain / memory.gateway / market read-and-calculate adapters
          → ToolMessage(tool_call_id, validated result)
          → OpenAI finish_<role>(typed output)
      → mandatory finance/privacy/acceptance checks
  → seller card/decision → ContentService → content agent + media providers
  → market result → Learning agent → validated memory commit
  → next invocation retrieves learned records; rules change only after seller Yes
```

Graph quyết định agent nào được gọi. Model quyết định tool đọc/tính toán trong quyền của vai trò và trả quyết định theo schema. Backend quyết định tác dụng nghiệp vụ và approval. `finish_<role>` là output cuối, không tự apply thay đổi.

Interface và pseudocode runner ở [D02a](tasks/02a-tool-runtime.md). `app/agents/runner.py` giữ loop/limits, `tools.py` giữ bound tools; prompt ở negotiation/content/memory. `infrastructure/llm.py` giữ transport/provider/budget, không import Session hay gọi gateway.

## 2. Tool catalog gọi được từ model

Backend tạo closure theo run/shop/day/role đã biết. JSON arguments không có role/run_id/shop_id/path để model tự tăng quyền. DTO được validate và serialize theo allowlist; kết quả sai hoặc denied trả lỗi có mã, không raw exception/Session.

| Tool | JSON arguments | Output | Vai trò |
|---|---|---|---|
| T01 `get_public_context` | `{}` | PublicContext: ShopPublic, public trend/calendar/active package, confirmed brief | Platform, Shop |
| T02 `get_shop_private_context` | `{}` | ShopContext: đúng ShopPrivate, rules_version; không Persona | Shop |
| T03 `read_memory` | `{}` | PlatformMemoryView hoặc ShopMemoryView từ role đã bind | Platform, Shop |
| T04 `validate_platform_package` | `{package:Package}` | PackageCheck: input/corrected, violations_before/after, ok, warnings, changes | Platform |
| T05 `evaluate_shop_package` | `{package:Package}` | ShopPackageCheck: PackageCheck + financials riêng | Shop |
| T06 `forecast_package` | `{package:Package}` | Forecast; ngày/seed/calibration do backend cấp | Platform |
| T08 `read_learning_evidence` | `{}` | LearningEvidence: public outcomes/evidence + existing lessons đúng scope | Learning |
| `search_campaign_catalog` | `{query:str}` | CampaignCatalogResult(items:CampaignRecord[]) còn hạn, đúng category/eligibility | Platform |
| `get_referee_context` | `{}` | RefereeContext: brief/public turns/public check codes | Referee |
| `get_content_context` | `{}` | ContentContext: verified facts/images, confirmed style, feedback, approved card/version | Content |

`read_memory` lấy dữ liệu từ gateway, không phải summary LLM tự viết. Catalog dùng `data/campaigns.json`, có nguồn `seed:campaigns:<id>`, gắn nhãn simulated. Empty search trả `CampaignCatalogResult(items=[])`; generic offer vẫn được phép theo brief và validators, không bịa chiến dịch thật.

`CampaignRecord`: `campaign_id:str, category:str, title_vi:str, description_vi:str, valid_from_day:int, valid_to_day:int, min_stock:int, max_voucher_pct:int, source_id:str`. Query dài0–200ký tự. Search dùng category của scoped shop, ngày hiện tại, stock và query đã strip/casefold (rỗng = toàn bộ eligible); trả tối đa 5 record theo campaign_id. Gói theo catalog vẫn qua rules riêng và seller approval. Seed D có campaign phù hợp; test expired/stock thấp bị loại.

DTO cơ sở thuộc `domain/models/tools.py` (D01); exact fields dưới đây, Pydantic extra=forbid:

| DTO | Fields |
|---|---|
| PublicContext | day:int, shop:ShopPublic, brief:IntentBrief, trend_multiplier:float, calendar_notes:list[str], active_package:Package\|None |
| ShopContext | private:ShopPrivate, rules_version:int |
| PackageCheck | input_package:Package, corrected_package:Package\|None, violations_before:list[Violation], violations_after:list[Violation], ok:bool, warnings:list[str], changes:list[str] |
| FinancialResult | profit_per_unit:int, breakeven_roas:float\|None, min_stop_threshold:float\|None, max_voucher_pct:int, reason:str\|None |
| ShopPackageCheck | Tất cả field PackageCheck + financials:FinancialResult |
| RefereeContext | brief:IntentBrief, turns:list[PublicTurn], public_check_codes:list[str] |
| ContentContext | shop_id:str, title:str, description:str, attributes:list[str], images:list[str], fact_source_id:str, memory:ContentMemoryView, feedback_history:list[str], card_id:str, brief_version:int, draft_version:int |
| CampaignCatalogResult | items:list[CampaignRecord] |

ShopPackageCheck.financials tính trên corrected_package khi có, nếu không thì input_package; financials không phải evidence sàn được đọc. T05 chạy cả check input và check corrected, không coi một gói clamp xong là mặc nhiên hợp lệ. PublicContext.calendar_notes chỉ là lịch sự kiện công khai; không lấy future market/Persona.

 `PublicContext` dùng public field cụ thể, không ShopState; `ShopContext.private` là ShopPrivate; `RefereeContext` dùng PublicTurn[]; `ContentContext` dùng public facts/images + ContentMemoryView và current feedback/version. `PackageCheck.ok` mô tả **gói input** không vi phạm; corrected_package hợp lệ chưa phải hai agent đồng thuận. `changes` là list field thay đổi. `ShopPackageCheck.financials` gồm profit_per_unit:int, breakeven_roas:float|null, min_stop_threshold:float|null, max_voucher_pct:int, reason:str|null; JSON không có Infinity.

## 3. Những adapter luôn do backend gọi

| ID | Interface nghiệp vụ | Khi chạy |
|---|---|---|
| T07 | `sanitize_shop_reply` → leak_guard + public projection | Mọi output shop sang sàn/referee, kể cả fallback |
| T09 | `commit_memory_updates` → typed atomic batch | Sau khi kiểm evidence/version/scope, chỉ 4 bins dẫn xuất |
| T10 | `confirm_preference` → valid question + seller decision | Chỉ seller handler, giá trị lấy từ pending RuleQuestion |
| T11 | `content_start` → ContentService.start | Sau seller accept đúng card |
| T12 | `content_retry` → ContentService.retry | Feedback seller đúng draft version |
| T13 | `content_apply` → ContentService.apply | Seller chọn bản/cover ready; runtime kích hoạt package |
| T14 | `append_event` → EventLog.add | Backend ghi việc đã xảy ra, không cho model giả audit |
| T15 | `read_events` → EventLog.since + audience projection | API/learning đọc đúng run và quyền |

Đây là adapter tới method hiện có, không cần tạo tám wrapper pass-through chỉ để đủ tên. Gọi ảnh/video có phí ở ContentService dưới approval/version/job budget. Agent không nhận arbitrary HTTP client, filesystem, SQL hoặc write-memory tool. Không phơi raw T15 EventLog cho model.

## 4. Vòng tool và điều kiện kết thúc

- Mỗi invocation tối đa **3 model calls**: hai vòng tool rồi vòng cuối chỉ cho `finish_<role>`. Hai vòng đầu cho tối đa 4 tool calls/batch, `parallel_tool_calls=True` để đọc độc lập trong một response; backend thực thi tuần tự. Call cuối `parallel_tool_calls=False`, force đúng finish tool.
- Kiểm toàn batch: tên tool thuộc allowlist, args đúng schema, IDs không trùng, không mixed finish/ordinary. Batch không hợp lệ không chạy một phần. Bound args/results theo D02a; không gửi history vô hạn.
- Mỗi result giữ đúng tool_call_id. Tool lỗi có ToolMessage error đã lọc; không giả result thành công. Hết giới hạn/finish sai/thiếu prerequisite → fallback rõ `source=offline`, qua cùng gates. Fallback chạy tối đa một lần; adapter local vẫn lỗi thì raise AgentToolError để caller trả failure, không bịa knowledge/tài chính.
- Tool đọc phải xảy ra trước terminal. Platform: T01 + T03, catalog ở initial propose; T04 và T06 cho final candidate nếu có package; withdraw/null package được miễn hai tool này. Shop: T02 + T03 + T05 cho proposal/current candidate. Referee/Content/Learning: context/evidence tool tương ứng.
- Prerequisite phải thành công, đúng invocation/version; candidate check/forecast khớp canonical JSON Package. Model đổi package ở finish thì code validate lại; thiếu tool evidence đúng candidate → fallback, không tự gắn trace. T05 cho original proposal có thể chứng minh corrected_package nếu kết quả đã kiểm lại corrected package, ghi rõ trong task.
- Private tool replies chỉ ở transcript shop. Graph tạo PublicTurn cho actor khác, không share nguyên messages giữa role. Public trace chỉ run/invocation/negotiation/card IDs, actor, tool_name, opaque tool_call_id, source/requested_by/status, safe record_refs, elapsed_ms. Opaque record IDs không encode private value; không xuất raw private args/result.
- `LLMClient.remaining_calls` là bộ đếm mạng duy nhất. D00/D01 cấu hình demo **64**. 12 actor invocations/negotiation ×3 = tối đa36 calls; D chuẩn 6×3=18. Content/retry/Learning dùng cùng budget. Hết budget fallback, không reset khi đổi role. Timeout8s/max_retries0, lỗi mạng đầu tiên tắt live cho run.

Offline/fake vẫn chạy adapters và code gates; `source` là nguồn model, fake transport ghi `fixture` rõ ràng. Fake transport chứng minh loop đúng trong test, không chứng minh OpenAI thật đã chọn tool. Chỉ log decision reason, tool/evidence IDs và dữ liệu được phép, không yêu cầu suy luận nội bộ.

## 5. Năm vai trò và Knowledge sử dụng

| Vai trò | Quyết định cuối | Knowledge/tool cần dùng | Acceptance |
|---|---|---|---|
| Platform | PlatformTurn | public context/catalog/history/calibration/lessons, T04/T06 | Cùng brief, history/lesson fixture khác làm thay đề xuất theo tool result |
| Shop | ShopTurn | private rules/preferences, T05 | D:70k/10% →45k/3%, không tiết lộ cost/minprofit |
| Referee | RefereeDecision | public brief/transcript/check codes | Evidence là turn ID thật; refocus/stop bounded, không sửa rules |
| Content | ContentText | fact whitelist + confirmed style/current feedback | Lần sau Yes nền sáng → tool trả style và prompt/chữ dùng style |
| Learning | LessonBatch(ops≤3) | public evidence + existing lessons | Chỉ đề xuất; code loại bad evidence/private và commit 4 bins |

Content tạo chữ qua cùng runner, ảnh OpenAI/video Muse qua module media. Knowledge content không có tài chính riêng. Model lesson không được tự tăng calibration hoặc xác nhận preference.

## 6. Giao tiếp với team và gate hoàn thành

Fixtures phân theo owner: D00/D01 đặt public/shop contexts/tool checks/handoff ở `contracts/agents/`; D02a đặt tool request/result trace ở `contracts/agent_tool_trace.json`; D04 đặt five-bin views/LearningEvidence/KnowledgeCommit ở `contracts/knowledge/`. Ghi `source=fixture` trong metadata của harness, không thêm field trái schema provider.

Data/DB giao World, Store get/put/list/commit_batch, EventLog, forecast snapshots và DayMetrics. Toàn giao schemas/ACL/evidence requirements + fake tests. Media giao ContentService start/retry/apply và context-to-provider input; Toàn kiểm approval và confirmed style đi qua. API giao routes hiện hành; headless script gọi cùng runtime methods để kiểm core trước UI.

Gate review: native tool message round-trip; role/scope isolation; money/code checks; seller decision hợp lệ; đủ năm ngăn; atomic write + no double night; retrieval tác động bước sau; trace không chứa secret. D02a/D02/D04/D06 chứa tests cụ thể. Chưa có key thì live pending, không bỏ code provider hay thay tool loop bằng prompt-only.

Learning runner chỉ kiểm schema LessonBatch và đã đọc snapshot evidence; gateway kiểm từng op scope/evidence/privacy, giữ các op hợp lệ và báo rejected_ops. Không fallback toàn batch chỉ vì một op sai evidence.
