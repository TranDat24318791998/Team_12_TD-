# UI final review — Astra MAX

What this change does: The implemented React changes connect the existing seller screens to the native Data contract: explicit brief confirmation, version-bound decisions/content, video choices, full retries, background polling and complete event reads. The layout is preserved. The Start blocker reported below is now resolved and verified in real React in private headless Chrome; the saved-proof source selector and both downloads also pass their targeted browser test.

Reviewed 31 October 2026, working-tree implementation after baseline `33fbdd5` / review docs `d46c812`. Read `UI_REVIEW.md`, `MEDIA_UI_HOST_IMPLEMENTATION_STATUS.md`, current frontend source/tests, and the actual Data facade/API/model contracts. Scope is UI only; API/DB/media/host/self-improve have separate reviewers. The current D product is the **desktop fan** supplied through MinIO, with its existing financial parameters. The earlier UI review's handheld requirement is superseded by that user instruction; no handheld-only UI change is requested.

## Resolved original blocker

### 1. [P1 — resolved] The first Start click opened the conversation only after negotiation finished

**Focused re-review result:** `frontend/src/useRun.js:56–60` now handles an accepted `/api/day/start` with an operation ID by refreshing state, checking the run is unchanged, and returning immediately. `ShopPage.start()` therefore opens Demo while the operation is still running. On 31 October 2026 I reran `frontend/tests/start-operation.browser.mjs`: **PASS**. Its private headless Chrome context uses the built React application and a fake API, confirms exactly one Start POST, sees the streamed event while the operation remains running, sees a later terminal failure, and verifies that a rejected Start stays on Shop. This closes the original P1. The description below records the defect and acceptance that were checked.

**Source:** `frontend/src/pages/Shop.jsx:23`; `frontend/src/useRun.js:53–68`; `frontend/src/api.js:44–46`. The actual native start endpoint returns HTTP 202 with the queued/running operation ID (`data/growth_data/api.py:405–406,423`).

**Reproduction:** Confirm the brief on the Shop screen and click “Bắt đầu ngày 1”. `ShopPage.start()` awaits `act('/api/day/start')`. The 202 response becomes a pending exception, and `useRun.act()` continues polling until that operation reports `succeeded`/`completed`. Only then does Shop navigate to `demo.html`. During the real native negotiation, the operator remains on the product screen, which contains neither `AgentActivity` nor the seller/event conversation. If the operation takes longer than the 70-second client wait, the start action returns false and never performs that navigation, even though work continues.

**Checked:** An in-memory callback probe invoked the actual compiled `ShopPage` Start callback with a deferred `act` promise. Navigation stayed empty until the promise resolved, then became exactly `['demo.html']`. The source of `useRun.act()` establishes that a native 202 promise resolves only on operation completion. This is a reproduced control-flow defect, not a browser-layout guess.

**Smallest fix:** Let a successfully accepted `/api/day/start` open Demo immediately after its 202 acknowledgment and a state refresh; Demo's existing authoritative busy state and polling continue observing the operation. Keep the longer completion wait for Night and the existing exact-operation handling where required. Do not navigate before the server accepts the command, do not fire a second start on the destination page, and do not treat acceptance as successful negotiation.

**Files / acceptance:** Update `pages/Shop.jsx` plus the smallest needed accepted-start branch in `useRun.js`. Add a regression in `tests/useRun.browser.jsx` or an equivalent real-React interaction test: queued 202 → navigation occurs while operation is still running → streamed agent event is visible on Demo → exactly one POST → eventual success/failure is shown. Also assert that immediate validation/brief failure stays on Shop. Rebuild `frontend/js/app.js` after the fix.

**If skipped:** The main demo loses its observable native-agent exchange, despite the backend and polling being operational.

## Resolved focused findings

### 2. [P2 — resolved] A direct Proof link could not initialize a fresh seller session

**Final recheck:** `pages/Proof.jsx:38` now catches only an initial API-mode 401, calls `/api/state` once, and retries the same selected proof request once. The retry is outside the catch and cannot loop. The existing abort signal covers bootstrap and retry; preview does not bootstrap. I reran `frontend/tests/proof-source.browser.mjs` after this change: **PASS**. Its real React/private headless context asserts the exact first-entry sequence `proof → state → proof`, one bootstrap before saved exports, and the equivalent one-time sequence after losing authentication while selecting the saved source. A resulting missing-artifact response remains an error with no fallback or export controls. This closes finding 2; the original reproduction below records the behavior that was corrected.

**Source:** `frontend/src/App.jsx:12` disables `useRun` on Proof; `pages/Proof.jsx:38` directly requests `/api/proof` or `/api/proof/demo`. Both are protected, and `/api/proof/demo` calls `identity(request)` without bootstrap (`data/growth_data/api.py:440–444`).

**Reproduction:** Open `proof.html?preview=0` in a fresh browser context without `growth_sid`, then choose “Báo cáo mô phỏng đã chạy”. No `/api/state` request occurs, so both sources remain unauthorized even when the saved artifact exists. Read-only requests to the running local host during this focused review confirmed **401 UNAUTHENTICATED** for both endpoints, with `Cần tạo phiên qua /api/state`. The passing fake-API proof test bypasses authentication and explicitly asserts that `/api/state` is never called, so it does not cover this case. This does not affect the normal Shop → Proof route after session creation.

**Smallest fix:** On the first API-mode Proof 401, establish the normal seller session through `/api/state`, then retry that selected proof request once. Do not retry indefinitely or treat a genuine missing-artifact error as an authentication failure. Keep the selected report/evidence exports bound to their own artifact and do not fetch current-run events for a saved export. Update the proof-source test to distinguish the one bootstrap GET from prohibited current-run evidence reads; verify direct navigation in a fresh cookie context, a ready saved artifact, and genuine artifact-not-found behavior.

**If skipped:** A copied direct Proof URL looks broken for a new viewer, despite a valid artifact. This is a direct-link gate, not a failure of the saved report or current authenticated session.

### 3. [P3 — resolved] Saved-report restart text did not name the session it resets

**Final recheck:** `pages/Proof.jsx:32` now labels the precomputed report's action **“Bắt đầu phiên demo mới”** and preserves the existing `onReset` callback/dialog. The rerun headless proof test asserts that exact visible label. There is no new reset request, comparison rerun or extra confirmation dialog. The original source concern below is resolved.

**Source:** `pages/Proof.jsx:32,44` always labels the button “Chạy lại từ đầu” and calls the shared `onReset`; `App.jsx:25,30` opens the current-session reset dialog and eventually posts `/api/reset`. It neither regenerates nor changes the selected precomputed pair. The dialog describes the current session but the action is ambiguous when the saved report is selected.

**Smallest fix:** For the saved source, label the action “Bắt đầu phiên demo mới”. Reuse the existing reset dialog, which already names the current session; no additional confirmation dialog is needed. Do not rerun a comparison or mutate its artifact. A regression should assert the saved-source label and that the button opens the existing dialog without any write until confirmation.

**If skipped:** A viewer can mistake starting/resetting their interactive session for replaying the saved comparison. Existing confirmation makes this a wording follow-up rather than a blocking data-integrity defect.

## Passed within the review bounds

| Requirement | Current evidence and result |
|---|---|
| Desktop product / unchanged finance presentation | `Shop.jsx:21–25` and the existing `Product` consume `state.demo_shop`; they do not hardcode handheld identity or recalculate private financials. Data now marks D as `desktop_fan` (`data/growth_data/seed.py:102`) and the current demo contract agrees. Actual supplied image playback remains a launched-service gate. |
| Seller brief is an actual action | `Shop.jsx:13–14,25` renders an explicit form; submission alone calls `/api/brief/confirm`. Start is disabled while idle without `brief.confirmed`. The callback probe observed zero confirmations before submit, exactly one afterward, and `ads_daily_cap:null` for an empty public cap. No private cap is invented. |
| Brief survives next-day workflow | UI uses the server's `brief.confirmed`; it does not reset or manufacture confirmation on day change. The API returns `step=idle` and persists the brief (`api.py:407–414`), matching the existing UI predicate. End-to-end restart persistence belongs to Data verification. |
| Exact decision semantics | `Demo.jsx:15–17` sends card ID, expected card/brief versions, action, note and answer. `Proposal.jsx:7` sends `accept,true` for Yes and `reject,false` for No. No new content/campaign request is created by the question UI. |
| Exact content binding and retry all | `Demo.jsx:27` sends card/brief/attempt/job/content IDs for both writes, `retry_scope:'all'` for retry, and explicit skip/ack for Apply. Actual compiled callback probes verified the outgoing objects. The component key includes run/card/job/attempt, so a new draft resets local selection and acknowledgment. These names match `LegacyContentRetry`, `LegacyContentApply` and facade binding validation. |
| Three drafts and unresolved retry | `ContentReview.jsx:13,23–25` blocks retry at version 3 and for queued/running/pending/unknown work. The bright-background button fills the existing feedback field; retry sends it once and clears only after success. Server budget/unknown guards remain authoritative. |
| Video choices and missing selected asset | `ContentReview.jsx:8–25` initially blocks a false/unknown review unless explicitly acknowledged or skipped; both booleans start false. The actual callback probe showed acknowledgment enabling Apply and an image `onError` disabling it again. Explicit skip can leave a usable cover available without video. No placeholder is substituted as a ready generated cover. |
| Busy state, reload and action errors | `App.jsx:12–13` now polls seller pages and combines local pending with server busy. Shop/Shell lock writes; Demo allows only the content-specific controls governed by slot status during media work. `useRun.js:61–72` checks the accepted operation ID, reports terminal failure and refreshes on 409. Demo shows failed operation/learning state (`Demo.jsx:22–23`). Real React reload/timer behavior was not exercised in a browser in this review. |
| More than 100 events, including hidden pages | `api.js:55–65` binds the run, checks monotonic cursor progress and drains `has_more` even on an empty visible page. `useRun.js:22` and Proof export (`Proof.jsx:37`) use that reader. A direct probe passed 100 visible events → empty page advancing to 200 → two visible events: three requests, 102 events, final cursor 202. Existing tests also reject nonadvancing cursors. |
| Horizon and provenance | Shop, Shell and Night use `state.simulation_days`; Proof uses `report.days`. Replay text no longer asserts a real LLM recording (`format.js:14`). Proof labels backend fixture/reference output as illustrative (`Proof.jsx:24–30`), handles not-ready/pending as an error state (`:36`), and preserves response metadata in export. API mode does not fall back to preview transcripts. |
| Transcript provenance filter | `proofComparison.js:23` now requires positive integer message event references, in addition to existing distinct-run, prior-day memory and control-arm checks. Missing conversations remain missing. This is presentation validation, not a claim that a real measured comparison has been run. |

## Verification actually performed

Ran from `frontend/`:

```sh
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node --test tests/*.test.mjs .test-build/*.test.mjs
```

Result: **45 passed, 0 failed**. This used the already generated test bundle from the implementation build; the implementation status reports its successful build. No generated/source files were changed during this review.

Additional executable probes bundled the current JSX in memory with esbuild (`write:false`) and a minimal hook-state adapter, then invoked the real component event callbacks. They verified explicit brief submission, request binding/retry-all, video acknowledgment, selected-image failure, and reproduced delayed Start navigation. These are callback/state-transition checks; the hook adapter is **not** React DOM, browser events, effects, focus, layout or media playback. A separate direct call exercised the real event reader across more than 100 events and a hidden-only page. The first callback-probe attempt used a development JSX runtime incompatible with the hook adapter; it was corrected to the same production runtime configuration as the application, and the checks above then passed.

In the first review, a hidden CUA tab was unavailable and the browser inventory was empty; no visible browser/app was opened. In the focused re-review, the explicitly supplied private headless Chrome scripts provided real React/browser interaction without using the user's visible browser. The earlier 45-test result remains the recorded baseline; the implementation status now reports **48 tests and a successful frontend build**, which I did not redundantly rerun.

Focused commands rerun from the repository root:

```sh
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node frontend/tests/start-operation.browser.mjs
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node frontend/tests/proof-source.browser.mjs
```

Both **PASS**. The saved-proof test selects current and saved sources explicitly; checks the “Mô phỏng ngoại tuyến đã chạy · Chưa đánh giá provider” label; reads the downloaded JSON files; verifies that the report export is the exact original schema/manifest/report/evidence envelope and the evidence export retains that manifest plus both branches; verifies no current `/api/events` reads; and verifies that a missing artifact clears the report and does not offer or load preview fallback. `proofArtifact.js:4–13` validates report/manifest identity and offline/not-run labels before display. `Proof.jsx:38,41,44` clears old payloads and aborts old requests when switching sources. The actual persisted artifact and real-host proof browser smoke remain the coordinator/SI lane's checks; these scripts use a fake API and do not prove a provider evaluation occurred.

Final tiny-fix recheck: the updated `proof-source.browser.mjs` was rerun and **PASS** after the one-time 401 bootstrap and saved-report label changes. No unrelated baseline rerun was needed. The coordinator also reports its actual-server hidden-browser smoke **PASS** for the desktop product, saved report/day 7, report download, paired-evidence download and an unchanged current run; that is coordinator-provided integration evidence, separate from this reviewer's fake-API headless tests.

Verdict: **PASS for the reviewed UI integration scope. Findings 1–3 are resolved.** Accepted Start opens the live conversation while work continues; direct Proof entry establishes a session once; current versus saved source selection, source labels and paired exports remain explicit; missing proof never falls back to a fixture; the saved action clearly starts a new demo session. No actionable UI finding remains from these reviews. Full seller/media/night and paid-provider claims remain limited to their separately recorded integration evidence.

Not checked in the focused re-review: complete browser layout/focus/scroll/media decoding, full real-server seller flow, local launch/restart, paid provider output, DB persistence or learning correctness. Only this report was written; no commits, source changes, paid calls, secret reads or visible browser actions.
