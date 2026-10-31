# Final HTTP API review

What this change does: The root application now serves Data's seller and worker APIs together with React, using the same SQLite authority and one native worker. It adds explicit brief confirmation, version-bound seller actions, asynchronous operation polling, scoped event pagination and measured proof projection.

Reviewed 31 October 2026 against P07, `API_REVIEW.md` and `DATA_IMPLEMENTATION_STATUS.md`, on the current uncommitted integration tree. Expected load is the single local demo process. Only this report was written. All checks used temporary Data homes; no request was sent to the real port-8000 application, and no production DB was reset or modified.

## Current verdict after focused re-review

**Verdict: Ship for P07 and the agreed saved-proof delivery contract. All five findings below are resolved. No outstanding P0/P1 API finding was found in this re-review.** This does not certify live providers or the separately reviewed DB, agents, media and UI implementations.

The current source was rechecked after the Data fixes and SI artifact delivery. The focused command now includes the saved-proof boundary:

```sh
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_data_native.py \
  tests/integration/api/test_demo_proof.py \
  data/tests/test_api_security.py \
  data/tests/test_api_inventory.py
```

**Result: 23 passed in 53.55 seconds.** All test Data homes were temporary. No real port-8000 request or production DB mutation was performed by this reviewer.

| Prior finding | Resolution verified |
| --- | --- |
| 1 — shared brief gate | `DataService.operation` now checks confirmed native brief before any start mutation. `test_brief_gate_covers_both_start_routes_and_reset_replay` proves both HTTP routes return BRIEF_REQUIRED without creating operations/day-start events, remain ready, then accept a confirmed brief. |
| 2 — proof delivery | Authenticated `/api/proof/demo` reads the fixed `service.home/demo-proof.json` through strict schema/scope/hash validation. `scripts/export_demo_proof.py` exports a real completed native offline D pair from a read-only source transaction and atomically replaces the artifact. Three saved-proof tests cover auth/scope, missing/tampered/extra/unsafe data, unchanged current state, and a real temporary ON/OFF pair with private/late-event exclusion. |
| 3 — reset receipt | The complete reset response and state snapshot are now built inside `service.command`. The regression proves reset A → reset B → replay A returns the original A response, preserves active B and rejects changed payload under key A. No new run is created by replay. |
| 4 — operation projection | Queued/running renegotiations now project negotiating. Failed night returns 409 with its operation ID, terminal status and safe error; replay keeps the same operation. `test_pending_renegotiation_and_failed_night_are_truthful` passes, including unresolved media blocking night. |
| 5 — attribution/budget | State resolves the active approval/card through the actual proposal parent chain and reads the configured/persisted limit minus durable reservations. `test_edited_approval_binds_original_card_through_content_apply` proves the original card remains attached after a seller edit, exactly one campaign/approval exists, and one reservation under cap 7 leaves 6 calls. |

Read-only validation of the actual ignored `data/runtime/demo-proof.json` also passed: `demo-proof.v1`, shop D, seven days, five metrics, comparison dialogue on days 1/4/7, 53 ON and 55 OFF frozen evidence events, distinct original run IDs, `source=precomputed_offline_simulation` and `provider_eval=not_run`. Days without paired dialogue remain unavailable; no dialogue is manufactured to fill them. This check read the artifact only and did not open or mutate the hosted database.

The new boundary matches the accepted contract: it accepts no request-selected file path; enforces seller-D authorization; checks pair IDs, common brief references, earlier-day memory refs, frozen branch evidence and hashes; rejects unknown fields/unsafe text; and projects no raw source rows. The source exporter requires completed offline native runs, complete settlements/handoffs, offline reflection/call provenance, no learned OFF records and matching original assets. It reads SQLite with `mode=ro`/query_only and excludes evidence after each settlement cutoff.

Source review also confirms the explicit React report selection, truthful precomputed/offline/provider-not-evaluated labels, full artifact report download and artifact-owned ON/OFF log export. Current-session proof remains separate and can truthfully be not ready. The coordinator independently reported the actual hidden-browser day-7/download flow passing with current-run state unchanged; this reviewer did not repeat browser automation.

The original findings and initial reproduction results below are retained as **historical evidence**, not open defects. Their earlier line numbers refer to that review snapshot.

## Historical must-fix findings — resolved

1. **[P1] The versioned start route bypasses brief confirmation** (`data/growth_data/api.py:243`, `api.py:404`, `data/growth_data/service.py:599`).
   - **What this is:** Both seller start URLs reach the same Data start-day command, but only `/api/day/start` checks the confirmed brief.
   - **Problem:** After native bootstrap, legacy start returns 409 BRIEF_REQUIRED. The same cookie can immediately send `POST /api/v1/runs/{run}/days/start` with `{expected_day:1,expected_version:1}` and receive **202 queued without a brief**. Confirmation then returns 409 DAY_STARTED. The worker later reads/dereferences `run['brief']`, so this can strand the run before the first real negotiation.
   - **Fix:** Enforce the native confirmed-brief precondition in `DataService.operation` before any start mutation, preserving explicit reference callers. Keep or remove the redundant facade check after the shared gate is in place.
   - **If we skip it:** One supported HTTP route can bypass the seller's mandatory confirmation and leave an unusable native run.
   - **Acceptance:** Test both routes without a brief: same controlled 409, no operation/market/day-start event and phase still ready. Confirm a valid brief and start each route in separate fresh runs. The in-process native start caller must obey the same condition.

2. **[P1 completion gap] The hosted proof screen cannot reach the generated native comparison** (`scripts/run_sim.py:23–36`, `data/growth_data/api.py:384–391`).
   - **What this is:** SI correctly generates real ON/OFF runs and a comparison group in a new isolated `runs/sim-*/growth.db`. The hosted app reads its configured Data DB and selects a group belonging to the current cookie session.
   - **Problem:** The script has no delivery path to the hosted app/session. SI's reported `/api/proof` 200 demonstrates its isolated app/session, not the port-8000 browser. A normal browser run has no completed comparison pair and correctly receives PROOF_NOT_READY. The UI does not create/drive the native pair either.
   - **Fix:** The coordinator approved a smaller, explicit artifact route described below: a read-only authenticated `/api/proof/demo` for a measured precomputed offline report, with separate UI selection. Keep current-session `/api/proof` unchanged and truthful.
   - **If we skip it:** The experiment report exists on disk but the required proof presentation remains unavailable in the hosted product.
   - **Acceptance:** Generate from the real isolated pair, open it through the composed app with a new seller cookie, verify the exact IDs/metrics/provenance and explicit offline label, and confirm the current session/run/events have not changed.

## Historical should-fix findings — resolved

3. **[P2] Reset retries combine two different runs** (`data/growth_data/api.py:363–366`).
   - **What this is:** The idempotency receipt stores `create_run`'s result, but the surrounding reset response obtains its nested state from whichever run is active when the request returns.
   - **Problem:** Reset A with key A, then reset B with key B, then replay A with the original body/key. The response contains outer `run_id=A` and nested `state.run_id=B`; it differs from the original A response. No duplicate run is created, but the response no longer identifies one coherent committed result.
   - **Fix:** Build and persist the complete reset response inside its command transaction. Replay that exact response; do not reselect A or undo the later active B mapping. This finding and reproducer were handed to the Data implementer, who is fixing it concurrently.
   - **If we skip it:** A lost-response retry or two browser tabs can receive contradictory run identity and state.
   - **Acceptance:** Replay equals the original full response; GET state still returns B; the two first requests created exactly two new runs. Same key with a different body still conflicts.

4. **[P2] Pending/failed HTTP projections still disagree with their operation** (`data/growth_data/facade.py:64–70`, `data/growth_data/api.py:394–399`).
   - **What this is:** State special-cases queued/running `start_day`, and night returns 202 for every non-succeeded operation.
   - **Problem:** A queued `renegotiate:<card_id>` has busy=true but step=day_done, so reload describes a finished day while native negotiation is pending. A failed night is also returned as HTTP 202 even though its status/error_code is terminal. The updated React operation poll catches the latter, but the transport contract remains wrong for other callers.
   - **Fix:** Treat both start and renegotiate kinds as negotiating while queued/running. Return a controlled terminal error/status with operation identity for failed/unknown night outcomes; reserve 202 for work that is still pending. Do not clear unknown outcomes or create a new paid operation.
   - **If we skip it:** UI/client state remains misleading during normal retry/failure flows, despite the corrected Data settlement guard preventing premature spend.
   - **Acceptance:** Hold a native renegotiation before execution and reload; state remains negotiating. Fail a learning handoff, then replay night; receive the terminal error immediately and preserve its original operation/receipt.

5. **[P2] State still substitutes empty/zero values for real attribution and budget** (`data/growth_data/facade.py:82–83`).
   - **What this is:** Every active package reports `card_id=''`; every session reports `live_calls_left=0`.
   - **Problem:** After the passing native lifecycle applies a real approved package, state cannot identify its originating card. A configured native run also reports no remaining calls regardless of its durable reservation count. Both fields were explicitly required in API_REVIEW/P07.
   - **Fix:** Resolve the card from the campaign's actual approval/proposal chain and project the remaining configured native budget from its durable ledger. Preserve null/unavailable only if the contract explicitly allows it; do not invent a zero.
   - **If we skip it:** The visible state loses the approval identity and misstates the session's remaining model budget.
   - **Acceptance:** Published package card matches the approved card, including an edited child proposal. One reserved live slot decrements the configured remaining total; offline calls do not.

## Accepted minimal delivery contract for finding 2

The coordinator proposed and this API review accepts the following implementation. It does not require copying business rows between databases or granting a browser arbitrary filesystem access.

- A generator CLI reads the **actual completed Data comparison** and exports its seller-D proof plus frozen supporting ON/OFF event/evidence projection to an ignored local artifact. The manifest retains original run IDs, comparison ID, seed, horizon, common brief/request identities, relevant versions, source checksums and generation provenance. It is not constructed from preview fixtures or the receiving browser's current state.
- A configured local file path is read by authenticated `GET /api/proof/demo`. There is no request-controlled path or group lookup across arbitrary files. Validate the manifest/schema/hash and allowed shop before returning a strict allowlisted payload; missing, invalid or tampered artifacts return a controlled not-ready/error response. This is integrity validation for a local artifact, not a new signing/auth framework.
- Mark the wire source `precomputed_offline_simulation`, preserve original provider/source metadata and `provider_eval:not_run` where applicable, and show the explicit UI choice **“Báo cáo mô phỏng đã chạy”**. This report is separate from current-session proof. Do not label it live, current-session, newly generated, or provider-verified.
- Include only authorized D information and already-permitted shared evidence. Do not expose other shops' private financial data, machine paths, storage keys, credentials, raw tool/private model payloads or the whole source database. Displayed memory references must retain their actual earlier source day/run/event/version; absent evidence remains absent.
- GET performs no generation and changes no active run, cookie-to-run mapping, comparison state or business records. Current-session `/api/proof` remains PROOF_NOT_READY until its own actual pair is available.
- Report download and log export must refer to the artifact's **own ON/OFF evidence**. Reusing the current-run `/api/events` export beside an unrelated precomputed pair would be misleading. Either include the frozen safe event bundle or expose a sibling authenticated artifact download with the same validation.
- Add one valid-artifact test through the composed app, plus missing/tampered artifact, unauthorized request and non-D scope rejection. Verify exact metrics/IDs and that GET leaves current-run events/state unchanged. A test fixture can exercise serialization, but the acceptance artifact must be exported from the real measured pair.

## Initial review checks and repaired behavior verified

Executed with offline modes and temporary fixtures:

```sh
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_data_native.py \
  data/tests/test_api_security.py \
  data/tests/test_api_inventory.py
```

Result: **16 passed in 17.69 seconds**.

That suite covers the composed app, cookie/reset/brief, actual fake native ToolMessages, 202 start, stale card and draft identities, retry, selected-asset deletion rollback, Apply receipt replay/conflict, night completion, persisted state after reopen, schema/route inventory, role/run/shop isolation, CSRF, cursor binding and private-event filtering. It uses fake/native/offline providers and does not establish live readiness.

Separate temporary TestClient reproductions produced:

```text
legacy start without brief: 409
versioned start without brief: 202, queued
confirm after that start: 409
reset A → reset B → replay A:
  outer run ID equals A: true
  nested state run ID equals B: true
  replay equals original response A: false
```

Source review confirms the earlier cross-shop proof-metric issue is repaired: financial/metric queries now scope to demo_shop_id and check the caller's access in both runs. Proof preserves null metrics, verifies completed pair access and emits actual branch event IDs and earlier-day memory refs where available. Event pagination now exposes has_more/run_id, validates negative cursors, and the client drains pages rather than silently truncating at 100. Native seller decision/content schemas require their exact expected identities and reject extras. Provider job state is allowlisted for native seller v1 responses. The root app remains lazy at import and composes the Data authority rather than the old Session runtime.

The edited-proposal→content parent-card binding, expired-media-lease fencing and health-test production-home issue were already reported and being fixed concurrently by the Data owner; they are not duplicated here as new discoveries. I did not run the warned health tests or interact with the real local-stack DB. This report describes the inspected state; concurrent fixes need their own focused rerun before marking the corresponding item resolved.

The initial fix-first verdict is superseded by the passing focused re-review above. Findings 1–5 are closed for the current local API scope.

Verdict: Ship for P07 and the explicit saved-proof delivery path.

Not checked: live providers, visible browser rendering or the full regression suite. The API fixes and artifact boundary were rerun in the focused 23-test suite above. No new auth, job framework, database or scaling work is required.
