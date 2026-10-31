# Knowledge final review — P04

What this change does: The product now reads Rules and evidence from Data and persists learned records in the same SQLite database. The existing native tools consume these records after reload. Five-bin storage, confirmation transactions and public evidence are integrated. The Content privacy finding below has been fixed and its actual ToolMessage/provider regression now passes.

Reviewer: Astra max. Reviewed current uncommitted implementation on 31/10/2026 against P04 and KNOWLEDGE_REVIEW.md. Data/DB and SI implementation statuses were consulted; this review does not repeat the SI compiler/proof or physical migration audit. D's desktop-fan source is approved and is the expected current product.

**Current verdict: PASS for the reviewed P04 Knowledge scope.** The shared P1 below is resolved by the focused re-review. No outstanding P0/P1 was found. The bounded-catalog follow-up and separate-lane limits below still apply.

## Resolved finding

### 1. [P1, resolved] Seller financial details reached the Content model through raw feedback

The paragraphs below preserve the original failure and reproduction for traceability; they describe the pre-fix state. Current resolution and verification follow them.

**Original boundary:** `data/growth_data/media.py:138,159` stores seller feedback in `content_jobs.feedback_history_json`. `app/infrastructure/data_content.py:28–44` returns that raw job from `snapshot`; `app/content/service.py:64–74` copies the feedback into ContentContext. `app/agents/content.py:18–25` returns that object as `get_content_context` ToolMessage.

**Original problem:** The Content role is restricted to verified product facts, confirmed style and public-safe feedback. Unlike the Learning source, the Content projection does not remove private cost, owner or financial instructions. This is an actual model-input leak, not merely a private audit field on disk.

**Pre-fix executed reproduction:** Temporary Data database, standalone Data FastAPI, content mode worker, approved local desktop image, offline media, FakeLLM only. Start a day, accept the proposal, create the next content attempt using the real `DataService.content_create` with:

```python
feedback_vi = 'Giá vốn 115.000đ của chị Lan; làm nền sáng.'
```

Run the real `ContentService.process_job` with `DataContentBridge`; the fake model requests `get_content_context`, then captures its ToolMessage before returning `finish_content`. Result:

```text
content_toolmessage_feedback = ['Giá vốn 115.000đ của chị Lan; làm nền sáng.']
private_value_reached_model = True
```

No provider call, remote access or source edit was used. The same source path is also identified by the separate Tools final reviewer; count this as one shared defect.

**Requested fix, now implemented:** Keep original seller text in the private Data audit, and provide a separate safe Content/provider projection at `DataContentBridge.snapshot` or the single shared adapter immediately before ContentContext construction. Apply the existing financial/owner redaction to all free-text style/feedback entries that leave the private boundary. Ensure both the native Content ToolMessage and any downstream provider input use the safe projection; do not fix only Learning, or only the final content text after the model has already read the secret. Preserve harmless style guidance where possible; fail closed or omit a redacted entry when the current guard cannot safely separate clauses.

**Regression requirement, now passing:** Repeat the reproduction with a fake transport capturing `get_content_context`; neither `115.000`, owner name nor private financial claim is present. Assert raw original still exists only in the private audit. A normal `Làm nền sáng` retry and previously confirmed bright style still reach the Content context and change its usable style input. Add the corresponding regression to the integrated Content/Data tests.

**Current resolution:** `DataContentBridge._text_guard` uses current Data public/private/cost/fee inputs, `leak_guard` and cross-shop `safe_text`. `_safe_notes` removes sensitive clauses from feedback and style projections while keeping independently safe guidance. `snapshot` exposes only sanitized `content_style_notes` from Rules; stored raw feedback and seller-confirmed Rules remain in the private audit. Unsafe previous listing/media free text fails with PRIVATE_CONTENT before model/provider use.

**Focused re-review:** Read the modified source and ran the actual ContentService regression plus related checks below. The regression captures both native get_content_context ToolMessage and mocked media requests, confirms no cost/owner/private phrase in either, confirms bright background survives, and verifies raw Data audit is unchanged. The shared P1 is closed.

```bash
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_media_bridge.py::test_private_feedback_stays_in_audit_but_not_native_tool_or_media_request \
  tests/integration/api/test_media_bridge.py::test_offline_images_only_retry_retains_prior_text_and_video \
  tests/integration/api/test_media_bridge.py::test_invalid_text_is_rejected_before_paid_reservation \
  tests/integration/api/test_data_native.py::test_learning_projection_discards_private_feedback
```

**5 passed in 7.09s**, using isolated temporary databases, fake model and mocked media transport; zero paid calls. The parameterized invalid-text test contributes two cases.

## Verified behavior

| Requirement | Evidence and limit |
| --- | --- |
| Same Data run/database | `load_data_context` constructs a disposable Session context from the existing run, uses `SqliteKnowledgeStore(service.store)` and `DataKnowledgeSource`, and does not call `Session.new`. Rules/business mutations remain Data commands. |
| Five typed compartments | Rules use Data `shop_rules`; Preferences/History/Calibration/Lessons use typed learning records and common repository validation. Existing core tests plus repository tests pass. SQLite reopen tests retain records/receipts and reject bad key/namespace writes. |
| Rules per shop and ACL | `DataKnowledgeSource.rules_state` rejects a shop different from its bound shop and reads Data Rules/version; evidence seqs join actual confirmation decisions. Direct temporary-DB check rejected D-source access to A and retained Rules version 1 after No. |
| Candidate→question→asked→answer | Native Data question validates durable candidate; `make_card` invokes mark_asked; `decision` calls Rules confirmation and durable preference callback on the same connection. Repository test faults after both mutations and proves rollback of Rules, preference and decision, then proves duplicate-answer behavior. |
| Lower-only voucher | Data question and confirm_rule now reject cap increases. The earlier 8→30 defect is fixed; the existing integrated native test also asserts RULE_INCREASE. The separately fixed SI voucher-learning issue was not re-audited here. |
| No silence 14 days | Executed real Data question/card/No on day 1; reopened gateway had status declined, declined_until=15, no ask on day 14 and askable on day 15. Rules version/style stayed unchanged. Data's seven-day run cannot naturally reach day 15; gateway expiry arithmetic was tested headlessly. |
| Memory OFF | Executed gateway checks: learned history/lessons/preferences empty, calibration null, Data Rules still present with ads_daily_max=45000. Existing tests retain Rules enforcement; SI review separately checks fully OFF publication/proof runs. |
| Bounded retrieval | Seeded eight typed category lessons into isolated SQLite; platform returned IDs l7,l6,l5,l4,l3 in score order. Source keeps History top 5 and Lessons top 5 per scope. Existing unit tests cover core privacy/scope and cross-day history. |
| Durable native next-use | `test_reopened_published_skill_changes_next_native_tool_message` reloads the Data-backed context/repository, fake model reads the real read_memory ToolMessage, chooses voucher 3 for published learned state and 10 for OFF, and rejects changed-base/tampered artifacts. This is deterministic integration evidence, not a claim about live model quality. |
| Data public evidence | DataKnowledgeSource filters public event fields, excludes the financial market projection, bounds seq, sanitizes text/feedback and supplies the frozen Learning snapshot. The source uses Data seq, not a JSONL sequence. Existing tests check scope/cutoff and private sentinel exclusion. Full SI temporal fact semantics remain in SI final review. |
| Static document metadata | Seed now records Markdown document_type; the Content reference set for D is content_standards_demo + product_SP004. Direct check confirmed desktop wording and no old battery 2000 claim. |
| Checksums and effective dates | In isolated objects, tampering product_SP004 bytes excludes it; moving the content guide's effective_from to 2099 excludes it. Source also filters shared collection, ready status, pinned release, expiry and exact product identity. Existing direct API assignment checks remain intact. |
| Trace | Gateway now includes record_refs and Rules/calibration version references; DataEventLog writes safe fields into Data events. It does not persist a raw private ToolMessage as public trace. |

The current `reference_documents` implementation returns every eligible matching row, with no final five-record slice or latest-version selection. The seeded local result is only three Platform/two Content references, so this did not block the reviewed demo. Before expanding the guide catalog, add deterministic version selection and a five-reference bound to match K05; do not treat the current small fixture as a general bounded query.

## Tests run in this review

```bash
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/unit/memory/test_gateway.py \
  tests/unit/runtime/test_store.py \
  tests/contract/test_knowledge_repository.py \
  tests/integration/memory/test_data_next_use.py \
  tests/integration/agents/test_agent_knowledge_flow.py \
  tests/integration/agents/test_learning_native.py
```

**49 passed in 1.94s.** This includes the durable transaction/reopen tests and core native retrieval/next-use tests.

Two additional inline temporary-database probes were executed:

1. Original Real Data→DataContentBridge→ContentService→FakeLLM privacy reproduction: **FAIL before fix**. The focused re-review regression now **PASSES**, as recorded above.
2. Data-backed No/14-day expiry, scoped Rules, lesson top 5, desktop reference, tamper/future exclusion and Memory OFF Rules: **PASS**.

No tests or source files were written by this reviewer. Only this report was added. Root separately reports an actual-host normal two-day flow including style confirmation passed with zero paid calls; that is supplementary team evidence, not a run performed by this reviewer.

Not checked: paid providers, visible UI, full migration matrix, SI compiler/evaluation internals or exhaustive mutations of every evidence field. Those have separate reviewers. The privacy projection and its exact model-input/provider-request regression were re-reviewed successfully; no full baseline was repeated for this narrow fix.
