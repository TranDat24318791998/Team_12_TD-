# Agent orchestration final review — Astra MAX

Reviewed the current working tree on 31 October 2026 against P02, `AGENTS_REVIEW.md` and `DATA_IMPLEMENTATION_STATUS.md`. This review covers native role orchestration, Data authority, budgets/source labels and normal/restart lifecycle. Source files were not edited; reproductions used temporary databases, fake transports and local image bytes. No paid provider or visible UI was used.

**Current verdict: PASS for the reviewed orchestration scope, with offline/fake-provider verification.** The reproduced P1 recovery blocker and P2 independent Content-mode defect are resolved and were re-reviewed on 31 October 2026. The final focused run passed **6 tests in 10.26s**. No open P0/P1/P2 remains from this lane; this does not claim live provider generation, provider quality or full product acceptance.

## Resolved P1 — Failed native operations prevented closing the day, and expiry left an orphan running negotiation

**Sources:** `app/runtime/data_worker.py:82–90,101–110`; `data/growth_data/api.py:35–42`; `data/growth_data/service.py:527–528,630–631,707–709`; `data/growth_data/integration.py:92–102`.

The original code had two connected faults. The composed app calls `service.recover()` before starting the worker. An expired operation became `failed/LEASE_EXPIRED_RESULT_UNKNOWN`, but worker recovery selected orphan negotiations only when their joined operation was still `running`. Close/settle also rejected every native operation whose status was not `succeeded`, including terminal failures. With the worker and claim restricted to queued operations, the current run could not finish without reset.

**Original reproduction actually run:** Create an isolated Data app with external execution, worker content, external learning and native driver. Confirm the brief and queue day 1. Claim the operation as `native_orchestrator`, create a D negotiation, then set its operation lease to a past timestamp. Call `service.recover()` and `DataWorker._recover()` in the actual startup order. Before the fix:

```text
data_recover {'content_jobs': 0, 'learning_handoffs': 0, 'operations': 1}
operation {'status': 'failed', 'error_code': 'LEASE_EXPIRED_RESULT_UNKNOWN'}
negotiation {'status': 'running'}
POST /api/night -> 409 OPERATION_PENDING
```

**Minimum correction:** Reconcile orphan negotiations using their exact native operation binding, including expired/failed operations, in a short transaction. Persist a terminal failed result and truthful unknown/interrupted provenance without resending a paid call. Permit a terminal failed operation to reach day close only after the existing running-negotiation, pending-card, accepted-proposal/content and unresolved-work gates are satisfied; alternatively supply an explicit safe-abandon transition. Do not relabel failure as success or weaken approval gates. Scope recovery to the owning operation, rather than any operation on the same run/day.

**Acceptance:** Reopen both before and after lease expiry; create an exception-failed operation as well. The negotiation becomes terminal once, no provider call or proposal is repeated, and night can proceed only when all ordinary pending-state gates are clear. Verify a second operation on the same day cannot terminalize the wrong attempt. Repeat recovery and assert no duplicate terminal event.

**Verified correction:** `app/runtime/data_worker.py:83–100` now joins the persisted `native/negotiation` command receipt to the exact operation ID/shop/negotiation and native owner. It recovers both running operations and operations already failed by lease expiry, writes a terminal receipt and `source=unknown`, and does not requeue provider work. Already-terminal negotiations are excluded, making the terminal write repeat-safe. `data/growth_data/service.py:527–533,632–638` permits terminal failed operations only for the native profile while retaining running-negotiation, pending-card, accepted-proposal, draft-content and unresolved-provider guards.

The passing regression creates the negotiation through the real command-receipt path and reopens the composed app through its actual lifespan. It verifies the failed operation remains visibly failed, its negotiation is terminal with unknown provenance, no LLM call reservation was created, and `/api/night` advances to day 2. Related regressions verify queued work still blocks settlement, unknown provider state still blocks night, and a failed night remains a single failed operation on replay. The original direct-internals reproduction above is retained as historical evidence; the final regression uses the production receipt binding.

## Resolved P2 — Media offline mode disabled a separately enabled native Content model

**Source:** `app/content/service.py:59,77–79`.

The original `ContentService` chose `_OfflineModel()` whenever `media_mode == 'offline'`, ignoring its injected LLM and `llm_mode`. This coupled independently configured modes and disabled the configured native Content role when images/video were offline.

**Original reproduction actually run:** Create an approved Data content job with a valid supplied local image, inject a spy transport, and use `llm_mode='live', media_mode='offline'`. Run `ContentService.process_job` with no provider network calls. Before the fix:

```text
spy_calls 0
job_status succeeded
content_sources ['offline']
```

**Minimum correction:** Use the injected LLM for native text generation; its own mode/budget controls model access. Keep the offline-media branch for cached covers/no video. Background jobs already receive `llm_mode='offline'` from `DataWorker`, so this does not require enabling background paid calls. Test live/fake-native plus offline media yields a real Content ToolMessage round trip while making zero media submissions; offline/offline remains zero paid calls.

**Verified correction:** `app/content/service.py:72–74` now uses the injected transport independently of media mode. The focused regression runs a fake native Content model with `llm_mode=live` and `media_mode=offline`; it observes two model calls, an actual ToolMessage, fixture terminal provenance, zero media calls and cached original covers. The complementary offline/offline regression observes zero model/provider calls and explicit offline provenance. Restart-with-reserved-content coverage also passes without re-invoking the model or submitting media again.

## What is now connected correctly

- The production worker calls the actual `run_negotiation` LangGraph and `run_agent` native tool loop. It supplies the Data negotiation ID and pins the Platform context. This is not `HttpHarness` or `reference_offer` masquerading as native orchestration.
- The context is constructed with existing Data run/shop/public/private/rules/fees and the shared SQLite Knowledge store. It uses the `Session` dataclass as a disposable adapter container but does not call `Session.new` or core RAM day/approval/activation/settlement workflows. Graph-local counters and snapshots are not a second business authority.
- Actual turns are persisted through Data commands, including native `counter` semantics. Referee string turn refs are mapped to Data event sequence references. External accepted turns remain running until a later Referee verdict and final Data validation; presentation occurs in the same transaction as successful finalization.
- Referee same-actor refocus is now stopped, exact-package acceptance remains enforced, and the graph retains the three-platform-round bound. Demo shop executes first. Background shops use the same graph with intentionally offline transport; their approvals are labeled simulated seller.
- Native model calls reserve a stable per-invocation/step slot in the shared durable run budget. Operation/content/night leases are checked during reservation, SDK retries remain disabled and duplicate/unknown reservations do not resend paid calls. Provider errors and exhausted budgets enter explicit offline fallback. The P02 plan allows safe terminal failure instead of full graph resume; the remaining P1 is that failure currently traps the business lifecycle.
- Seller decisions, content job creation, publication/activation, settlement and next-day state remain in Data. Learning handoff publication writes the Knowledge commit, Data summary/events and advancement in one short transaction with the handoff check. Detailed evidence/privacy/SI semantics belong to their separate reviewers.

## Checks and limits

Executed with offline environment and fake transports:

```text
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_data_native.py \
  tests/unit/agents/test_runner.py \
  tests/unit/negotiation/test_negotiation.py \
  tests/unit/infrastructure/test_llm.py
25 passed in 10.21s
```

The earlier lifecycle test proves Platform/Shop/Referee/Learning native ToolMessages, Data IDs, seller/content gates, completion and reopening a completed run. It substitutes `FakeContent`, so that single test does not prove all five native roles together. The final focused re-review additionally exercised the real Content worker with a fake native transport and the actual expired-operation startup path.

Final re-review command, using the same offline environment and temporary databases:

```text
PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_data_native.py::test_expired_native_operation_recovered_on_actual_startup_and_can_close \
  tests/integration/api/test_data_native.py::test_pending_renegotiation_and_failed_night_are_truthful \
  tests/integration/api/test_data_native.py::test_queued_operation_blocks_night_without_settlement \
  tests/integration/api/test_media_bridge.py::test_offline_original_is_explicitly_cached_and_requires_video_skip \
  tests/integration/api/test_media_bridge.py::test_offline_llm_and_media_make_no_provider_calls \
  tests/integration/api/test_media_bridge.py::test_reserved_job_restart_never_resubmits_or_reinvokes_model
6 passed in 10.26s
```

Excluded the separately assigned Data/API fixes: edited-proposal card lookup, media expired-lease recovery, versioned-start brief bypass, reset replay-mode mismatch and health temporary DB. Did not repeat broad privacy/Knowledge/API/media reviews, run paid smoke, inspect visible UI or claim real-record replay/provider quality. Only the assigned review document was changed during the focused re-review.
