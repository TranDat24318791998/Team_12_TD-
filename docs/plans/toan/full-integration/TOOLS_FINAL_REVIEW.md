# Tools final review

What this change does: The native agents now read a disposable context loaded from the existing Data run, and forecast through Data's read-only calculator. The model → tool call → ToolMessage → typed finish loop, role allowlists, financial correction and final workflow gates remain in place.

Reviewed the current working tree against P03 in IMPLEMENTATION_PLAN.md and TOOLS_REVIEW.md. This is a tools review, not another API/DB/recovery/media implementation review. Tests ran with LLM_MODE=offline and MEDIA_MODE=offline; no live providers or production database were used.

## Resolved finding

### 1. P1, resolved — Raw private seller feedback reached the Content tool

**Original trigger:** A normal content retry containing `Giá vốn 115.000đ của chị Lan; làm nền sáng.` was retained in private Data storage but also copied into get_content_context's ToolMessage. The Knowledge reviewer independently reproduced the same issue; it was one shared finding.

**Implemented fix:** `app/infrastructure/data_content.py:33–94` now builds the Content projection using current Data public/private/cost/fee values, leak_guard and cross-shop safe_text. _safe_notes removes sensitive clauses from feedback and confirmed style while preserving safe creative guidance. The snapshot exposes only content_style_notes from Rules. Original seller feedback and confirmed Rules remain unchanged in private SQLite audit. Unsafe previous listing/media text fails before model/provider use.

**Focused re-review executed:**

`LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/api/test_media_bridge.py::test_private_feedback_stays_in_audit_but_not_native_tool_or_media_request tests/unit/agents/test_runner.py::test_native_tool_response_changes_the_final_decision`

Result: **2 passed in 3.37 seconds**. The privacy regression exercises real DataContentBridge and ContentService with a fake native model and httpx mock media transport. It confirms the actual ToolMessage contains only `['làm nền sáng.']`, confirmed bright/minimal style remains, fake provider requests use background_preference=bright, and cost formats/owner name/financial phrases are absent from both outbound paths. Stored raw feedback and private confirmed style remain unchanged. No network/provider calls were made. This closes the shared Tools/Knowledge P1; see KNOWLEDGE_FINAL_REVIEW.md for the separate reviewer’s result.

## Bounded checks executed

Command:

`LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/agents/test_runner.py tests/unit/domain/test_finance.py tests/integration/api/test_data_native.py::test_composed_native_lifecycle_and_asset_gate tests/integration/api/test_data_native.py::test_learning_projection_discards_private_feedback`

Result: **12 passed in 9.66 seconds**. Test processes also used PYTHONDONTWRITEBYTECODE=1; all Data storage came from test temporary directories.

A separate inline Python assertion script created a temporary Data app, confirmed the brief, loaded the actual Data execution context and bound the actual tools. Result: **all assertions passed**:

| Check | Observed result |
|---|---|
| T01 public projection | PublicContext contains only day/shop/brief/trend/calendar/active package/references, not the raw Data private context. |
| Role and argument boundaries | Platform tool map excludes T02/T05; bound D context rejects binding shop A; injected run_id is rejected by EmptyArgs before execution. Existing runner tests also prove denied tool handler never executes, batch duplicate IDs cause no partial dispatch, and maximum model call count is three. |
| T05 exact financial correction | D's 70000/day, 10%, stop4 input corrects to 45000/day, 3%, stop6.5. Financials show profit_per_unit=27136. Corrected candidate passes DataService.evaluation and its contribution equals T05's result. |
| T04 repair | A 5000/day input repairs to zero ads with no remaining violations. It is not prematurely rejected by Data's stricter wire Package. |
| Confirmed brief | Binding a confirmed brief with allow_ads=false causes T04 to remove ads. Core brief content/duration/cap checks remain in tools.py. |
| T06 public forecast | Exactly low/point/high/factor_used/stock_warning; values equal Data forecast_values for the identical day/package. It accepts the initial 70000/10% public candidate without consulting a private approval gate. |
| T06 no business mutation | Counts of proposals, negotiations, campaigns, forecasts, decisions, shop_rules and content_jobs are unchanged around actual forecast tool execution. No create_proposal or snapshot_forecast call is used. |
| Stop-window boundary | stop_after_days=14 validates and 15 is rejected. |
| Current Data before a new negotiation | After temporary Data inventory changed from 300 to 17, a newly loaded execution context returned 17 through T01. It does not reload the original seed. |
| Native integration | The selected composed lifecycle test runs Platform/Shop/Referee/Learning through actual fake AIMessage/ToolMessage exchanges against temporary SQLite and checks D's 27136 contribution. Content's generic native loop is covered by the runner's actual ToolMessage-dependent output test. |
| Existing Learning private projection | The selected test confirms private financial feedback does not survive DataKnowledgeSource's Learning projection. This is distinct from finding 1. |

## Implementation mapping and remaining limit

The implementation does **not** contain a class named DataToolScope. Its equivalent is `load_data_context` and `DataMarket` in `app/infrastructure/data_agents.py:20–27,92–117`, consumed by the existing role-bound closures in `app/agents/tools.py`. The class-name deviation is not itself a defect. The worker supplies run/shop IDs, the graph supplies day, and model argument schemas cannot change them. No new mutation/provider tool was added to ROLE_TOOLS.

Financial tools and leak_guard now receive public/private/fee values loaded together from Data at negotiation construction, including other_unit_cost and the run fee configuration. The unchanged Decimal finance functions perform integer VND calculations. Public/private role message isolation and same-package finish prerequisites remain in `app/agents/runner.py:43–88,92–200`; no rewrite is needed.

**Accepted snapshot lifetime:** The context is deliberately frozen per negotiation. Every new attempt calls load_data_context again; final Data commands validate current rules/inventory/approval versions. The earlier temporary-DB probe confirmed the intended lifetime: an existing context retained stock 300, while a newly loaded context returned Data's updated stock 17. Model schemas cannot choose run/shop/day or invoke private/command/provider methods outside their role. Under the documented single-worker demo, this is not an open blocker and does not require a new DataToolScope framework. Reuse across negotiations would violate this contract; concurrent authority edits within a negotiation remain outside this bounded review.


## Verdict

**TOOLS: PASS for the reviewed normal-demo scope. No open P0/P1 findings remain.** The shared Content privacy P1 is fixed and its actual ToolMessage/provider-request regression passes. Core loop, money/repair/brief checks, scoped model tool catalog and read-only forecast behavior pass the bounded checks above. The prior forecast DTO and stop_after_days findings are also resolved.

Not checked: full root/Data suites, live OpenAI/Muse, visible UI, concurrent-authority mutation beyond the explicit snapshot-lifetime probe, or API/DB/recovery findings assigned to other reviewers. No source edits, commits, paid calls or secret reads were made; only this report was written.
