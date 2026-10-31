# UI review — Astra MAX

What this change does: Connect the existing React seller experience to the native agents, authoritative Data facade and media worker. Keep the shop page, compact agent strip, seller chat, content card, night screen and two proof conversations. The work is request/state integration and a few controls, not a redesign.

Reviewed 31 October 2026 at baseline `33fbdd5`. Scope is UI only, for one local demo operator. Read `AGENTS.md`, `FRONTEND_REQUIREMENTS.md`, `FRONTEND_DATA_REQUIREMENTS.md`, `DEMO_CONTRACT.md`, React source/tests, the actual Data facade, and the DB/media/agents/tools/self-improve reviews. API body alignment below was coordinated with the dedicated API reviewer. Only this report was written; no source changes, commits, paid calls, secret reads or visible browser actions.

## Keep what works

- `frontend/src/useRun.js:9–45` already reads state before events to establish the cookie, scopes history to run, deduplicates sequence numbers, shares one read flight, keeps GET polling alive during a POST and cancels on unmount. Retain those properties.
- `frontend/src/api.js:22–50` already sends same-origin credentials, `Idempotency-Key` and `X-Request-ID`; ambiguous failures retain the command key; API failure does not silently select preview. Keep the direct `/api/*` JSON facade. Do not introduce `/api/v1` envelopes, service tokens, DB access or a browser agent loop.
- `activity.js`, `AgentActivity.jsx` and `EventFeed.jsx` already separate attempts, code checks, referee feedback, shared turns and seller-private notes. Render the backend's real seller projection; do not fabricate turns or infer native tool execution from an animation.
- `ContentReview.jsx` already limits total drafts to three and supports cover A/B/C. `Proposal.jsx` already has a question-only layout without new spend. `proofComparison.js` already rejects mismatched runs, duplicate days and future memory evidence.
- Data already delays content campaign activation until publication (`data/growth_data/facade.py:93–99`, `media.py:149–158`). This is no longer an integration defect. UI must continue navigating to the updated listing only after successful Apply and a refreshed state.

## Must fix

### 1. The UI cannot capture or start from a seller-confirmed brief

**Evidence:** `pages/Shop.jsx:20` sends `/api/day/start` directly from idle. There is no `/api/brief/confirm` caller or `state.brief` handling in React. `DEMO_CONTRACT.md` section 3 requires an explicit confirmed brief before native negotiation. Data's current projection (`facade.py:64–73`) does not supply it yet.

**Concrete case:** A fresh seller clicks “Bắt đầu demo”. A correctly gated native backend must reject this request, or a permissive adapter would need to invent seller confirmation. If an adapter returns the older plan's `brief_confirmed` step, Shop instead only navigates, and Demo has no matching start view.

**Smallest fix:** Add the brief confirmation section inside the existing `ControlPanel` in `pages/Shop.jsx`, using existing form/button styles. Show the supported increase-orders goal, three-day content/ads scope and optional public daily cap; leave the cap null by default. Do not infer the private 45.000đ limit. POST the explicit confirmation, then start only after the persisted confirmed response. The API/UI integration agreement keeps `step=idle` and uses `brief.confirmed` to distinguish the two idle states; document this deliberate replacement of the older `brief_confirmed` step. Day 2 reuses the persisted brief and offers “Bắt đầu ngày 2”, without another confirmation. Reload must restore the server brief. Native request failure keeps the seller on the current screen with the actual Vietnamese error.

**If skipped:** The main native flow cannot begin with truthful seller authorization.

### 2. Seller writes do not bind the card and draft the seller reviewed

**Evidence:** `pages/Demo.jsx:15–17` sends only card ID/action/note; line 25 sends retry feedback alone and Apply cover alone. `App.jsx:19` sends Night with no expected day. Data's current facade (`facade.py:75–124`) resolves latest versions itself and strips draft identities at lines 42–44. These old bodies are valid for today's facade, but insufficient for the agreed native/media integration. Do not turn on new React bodies before the API schema and projection change together.

**Concrete case:** Two tabs show draft 1. One creates draft 2. The old tab's cover-only Apply currently resolves the latest job, so it can approve media the seller never reviewed. A feedback-only retry can likewise consume the next attempt against a stale screen.

**Smallest fix:** Send the exact agreed bodies in the contract table below from `Demo.jsx` and `App.jsx`. Bind `api.js:commandTarget` to card/brief/job/content/attempt, not only day/version/step. Key `ContentReview` by run + card + job + attempt so selection, acknowledgment and load failures cannot carry into another draft whose attempt is also 1. A stale-version error refreshes state and reports the conflict; it does not resubmit against the new draft automatically.

The current question “Chưa cần” sends `accept,false` (`Proposal.jsx:7`). Data presently uses the boolean and does reject the preference (`facade.py:82–86`), so this is **not a current Data approval bug**. Align it to the agreed `reject,false` semantics while adding versions; preserve `accept,true` for Yes. Offer Reject remains a successful decision, not an error. Keep the existing negotiation composer, but add the supported “Giảm voucher còn 2%” preset and expose actual server limits/errors; do not promise unrestricted native negotiation from a placeholder example.

**If skipped:** A valid click can target unseen content, and new strict APIs reject normal seller actions.

### 3. Apply has no video consent gate, and a broken cover remains selectable

**Evidence:** `components/ContentReview.jsx:9–17` enables Apply whenever selected cover status/path looks ready. It ignores video review, explicit skip and actual image load failure. The image `onError` swaps the displayed URL but leaves `ready=true`. `tests/components.test.jsx:45–48` explicitly asserts that a running video allows publication without any seller skip. Data's current Apply accepts only `cover_option` (`facade.py:118`); media review documents the required coordinated extension.

**Concrete cases:** A ready clip with `visual_review_passed=false` is indistinguishable from a passed clip. A running clip is silently omitted/handled by backend policy without the seller choosing skip. A deleted selected cover returns 404, displays a fallback, and still enables “Dùng bản này”.

**Smallest fix:** Keep the same content card and add an explicit “Dùng ảnh, bỏ qua video” choice plus acknowledgment for a ready clip whose review is false or unknown. Show safe review notes and each slot's actual running/done/failed/cached status and source. Apply is enabled only for a ready selected cover and either an explicitly skipped video or a ready video whose review passed/was acknowledged. Missing metadata never means passed. Track image/video load failure per exact draft/slot/path; show an unavailable state and disable affected inclusion rather than disguising it as ready. An image loading error can still permit another intact cover; a video error can still permit explicit skip. Server file/checksum validation remains the authority, including after the browser loaded an asset successfully.

No automatic skip, auto-acknowledgment, alternate SKU image, signed provider URL or UI-triggered generation on image load error. Missing source product image is a visible backend input error; a decorative placeholder is not an approved source asset. Use Data's authenticated same-origin asset URLs.

**If skipped:** The UI presents publication as reviewed and successful when the seller has not accepted the actual video or cannot see the selected asset.

### 4. Bright-background retry currently regenerates images only

**Evidence:** `Demo.jsx:25` sends `{feedback_vi}`. Data defaults that request to `retry_scope="images"` (`facade.py:110–115`, `models.py:124–130`) and intentionally retains the old text/video. `ContentReview.jsx:16–17` also allows retry while media is still running, as long as the local POST is not pending.

**Concrete case:** The seller asks for brighter images on draft 1. Draft 2 gets new covers while its video still references A from draft 1. This violates the integrated media requirement that each full retry's video uses A from that same attempt.

**Smallest fix:** The integrated retry action explicitly sends `retry_scope:"all"`, full binding and the feedback. Add a small “Ảnh nền sáng hơn” preset to the current feedback input; preserve the entered feedback until the command succeeds. Keep versions 1–3 as three total drafts, not three retries, and show remaining retries. Disable this action while the current required jobs have unresolved/running outcomes; display the backend's safe failure/unknown state rather than start another paid attempt. API/media owners must project enough status to make this honest and enforce it server-side. Keep images-only semantics for other existing Data callers.

**If skipped:** The visible draft mixes versions and can abandon an unresolved paid generation.

### 5. Reload loses operation locking and non-Demo pages stop observing work

**Evidence:** `App.jsx:12` polls only on `demo.html`; all action controls use local `pending`. Data already supplies `busy`, `active_operation`, `learning_status` and `learning_error` (`facade.py:59–69`). React never reads those fields. `useRun.js:56–63` waits for accepted commands for about 70 seconds; `api.js:18–20` generally treats any command-target change as completion. The existing Night predicate correctly waits for advance/complete rather than merely a summary and should be retained.

**Concrete case:** Reload `updated.html` while a 202 Night operation is learning. The initial state still has `step=day_done`, but local `pending` is empty, so “Kết thúc ngày” is enabled and there is no continuing poll. A failed external operation also has no specific visible error despite being projected. Navigation to Shop during an external negotiation freezes the displayed snapshot.

**Smallest fix:** Derive action disabling from local pending **or** authoritative busy/current operation, with explicit failure recovery. Poll state/events while an external operation or learning job is active on any seller page; stop when settled. Retain serialized local writes and background reads. Keep command operation identity so entering `negotiating` is an accepted start, not proof that the job succeeded; surface failed/unknown terminal status. A client timeout should say work may still be running and continue observing state, not invite a new job. API owner must project renegotiation as negotiating and keep the server close-day guard; UI disabling does not replace either.

**If skipped:** A durable backend resumes correctly while the UI appears frozen or offers conflicting writes.

### 6. A native event stream longer than 100 records truncates night data and exports

**Evidence:** Data's legacy events handler calls `service.events(...,100)` and discards its third `has_more` result (`data/growth_data/api.py:354–358`; `service.py:219–234`). `useRun.js:22–25` fetches one page per refresh, and App does not poll Night/Shop. `pages/Proof.jsx:35` exports only one GET response. Night derives metrics from its fetched events (`Night.jsx:9–13`).

**Concrete case:** The native roles generate more than 100 run events before `market_result`. Open `night.html` directly: the summary loads, but orders/ROAS/spend remain missing because only the first page was read. Export from Proof silently omits the tail. Sparse seller-visible pages can be shorter than 100 even though more authorized events remain.

**Smallest fix:** Preserve the existing cursor contract and add `has_more` from Data's existing result; drain pages with one in-flight reader until false, checking run identity and cursor progress. Share that small reader with log export, or use the same cursor loop there. Do not terminate merely because the visible event count is less than 100; private events can advance the scanned cursor. Abort on navigation, and do not loop forever on an invalid/nonadvancing cursor. If the additive flag is not adopted, drain until the cursor stops rather than relying on array length.

**If skipped:** The UI loses committed evidence in ordinary native runs despite a passing small-fixture test suite.

### 7. Run length and proof/source labels make claims the response does not support

**Evidence:** Shop (`Shop.jsx:9–12`), Shell (`Shell.jsx:14`) and Night (`Night.jsx:19,27`) hardcode `SIMULATION_DAYS=7`, while Data projects `simulation_days` (`facade.py:65`). `format.js:14` labels every replay “Phát lại bản chạy thật”, although Data explicitly reports `capabilities.faithful_llm_replay=false`. `Proof.jsx:23,28` chooses source text solely from the browser's preview flag, ignoring response `source`, `execution_profile` and `status`. Data currently returns 200 `status=not_ready|pending` without a pair (`api.py:360–363`), and measured reports expose source/profile (`evidence.py:69–70`). `proofComparison.js:22–24` accepts messages without positive `event_seq` despite the transcript contract.

**Concrete cases:** A completed two-day demo displays “Hoàn tất 7 ngày”. API proof with `status=not_ready` still gets the footer “Dữ liệu từ hai lần chạy đối chứng đã lưu”. A backend-served fixture is labeled as real transcript because `preview=false`. Replay without an LLM recording is labeled a real recorded run.

**Smallest fix:** Use validated `state.simulation_days`, with seven only as the legacy preview default; keep `report.days` for proof. Preserve the seven-day preview button and never repurpose it to send seven days of seller actions. Source labels must come from response provenance and readiness, with separate sample/reference/offline/provider-recorded facts; requested `mode=live` alone proves no call was live. Render 409 `PROOF_NOT_READY` or legacy `status=not_ready|pending` as an honest empty state. Reject/filter transcript messages lacking valid event refs and continue showing missing data rather than importing preview conversations. Keep response source metadata in JSON export. For a stored seven-day dataset, use the backend's selected dataset/revision; do not make sessionStorage the authority for API mode.

**If skipped:** A working local demo overstates its horizon, native execution or experimental evidence.

## Coordinated API contract and exact caller tasks

This table is the proposed integrated contract agreed with the API reviewer, **not a claim that today's facade accepts it**. API/DB/media owners update models, projection, handlers and fixtures before switching these callers. Keep `growth_sid` as the existing HttpOnly cookie; React continues to use same-origin credentials without reading it. Do not introduce a second browser session mechanism.

| Operation / projection | Exact UI shape | Files |
|---|---|---|
| State | Existing fields plus `brief`, `rules_version`, `confirmed_style_notes`; retain `busy`, `active_operation`, `simulation_days`, capability/source metadata. Idle + `brief.confirmed` is ready to start. | `pages/Shop.jsx`, `App.jsx`, `useRun.js`, `components/Shell.jsx`, `pages/Night.jsx` |
| Card | `version`, `brief_version`, explicit negotiation/proposal IDs alongside existing `card_id`. | `pages/Demo.jsx`, `api.js` |
| Draft | `card_id`, `brief_version`, `version` (attempt 1–3), `job_id`, `content_id`, `job_version`, `content_version`; per-slot status/source/error; video review/reference fields. Worker lease versions must not be confused with the seller's stable attempt identity. | `pages/Demo.jsx`, `components/ContentReview.jsx`, `api.js` |
| Confirm brief | `{intent:"increase_orders",goal_vi,allow_ads:true,ads_daily_cap:null_or_explicit_integer,content_refresh:true,duration_days:3}` | `pages/Shop.jsx`; preview request handler only if the shared form is also used in preview |
| Seller decision | `{card_id,expected_card_version,expected_brief_version,action,note_vi,rule_answer}`; Yes `accept,true`, No `reject,false`; offer action accept/negotiate/reject. | `pages/Demo.jsx`, `components/Proposal.jsx` |
| Retry all | `{card_id,expected_brief_version,expected_draft_version,expected_job_id,expected_content_id,feedback_vi,retry_scope:"all"}` | `pages/Demo.jsx`, `components/ContentReview.jsx`, `api.js` |
| Apply | `{card_id,expected_brief_version,expected_draft_version,expected_job_id,expected_content_id,cover_option,skip_video,video_review_ack}`; both booleans explicit and initially false. | `pages/Demo.jsx`, `components/ContentReview.jsx`, `api.js` |
| Night | `{expected_day:state.day}`; use current operation/status until day advance or terminal complete. | `App.jsx`, `useRun.js`, `api.js` |
| Events | Existing `{events,last_seq}` plus additive `has_more`; events remain the backend's seller projection. | `useRun.js`, `pages/Proof.jsx`; shared read helper only if needed by both |

No CSS overhaul is necessary. Reuse existing fields, pills, error boxes and buttons; add only the styles needed for these small controls. `frontend/js/app.js` is generated from source and must be rebuilt at the end. Do not hand-edit the bundle or fixture conversations to make the integrated flow appear successful.

## Implementation order and bounded acceptance

1. **Lock the shared contract:** API/DB/media owners implement the table, authoritative guards and provenance. Capture real seller-facade fixtures from a disposable Data run. Do not add a parallel frontend-only integration DTO.
2. **Wire seller flow:** Shop brief/start, decision bodies, question No, exact content bindings and Night. Keep current pages/layout and preview mode explicit.
3. **Wire media gates and async lifecycle:** retry-all, status/errors, cover failures, explicit video skip/ack, persisted busy/operation polling and event draining.
4. **Fix labels and verify:** dynamic horizon, proof readiness/source labels, build the bundle and run focused UI tests plus one real local HTTP smoke with injected providers.

| Bounded check | Required observable result |
|---|---|
| First load, reload and next day | API mode shows the actual D handheld product from `demo_shop`; explicit brief confirm precedes native start. Reload recovers the same brief/card/job. Day 2 does not ask to reconfirm the brief. |
| Three seller choices | Accept waits for content publication before active campaign; supported negotiate creates a new card/attempt; Reject proceeds to end-day without new content/spend. Current layout and compact agent strip remain. |
| Version conflicts | A second tab changes the draft; stale retry/Apply receives conflict, causes no new job/publication and refreshes without auto-resubmitting. Captured request includes all expected IDs/versions. |
| Media attempts | First draft + two full retries only. Bright preset sends feedback once with `retry_scope=all`; new video references A of the new attempt. Polling does not create feedback/jobs. Pending/unknown outcomes do not enable another retry. |
| Review and missing assets | Ready cover + review-passed video may apply; false/null video review needs acknowledgment or explicit skip. Running/failed/missing video needs skip. Missing cover disables that selection; a different intact cover can apply. Server rejection leaves the current draft visible. |
| Reload during external work | Start/renegotiation/night continues polling after reload on Demo, Shop or Updated; conflicting controls remain disabled. Terminal failed operation shows its error. No completion is inferred from a summary alone. |
| More than 100 events | Put market/night events after event 100 and include a page with only filtered events. Direct Night load displays the latest committed metrics; export contains the complete authorized log exactly once; reader stops at the correct cursor. |
| Style question | Feedback alone does not change Rules. Next-day Yes sends `accept,true` and updates only confirmed preference/rules; No sends `reject,false`; neither creates a fresh campaign or media job. |
| Horizon and proof | Two-day run ends at 2 and seven-day preview remains 7. Not-ready proof stays empty. Backend-served fixture/reference/offline output is labeled correctly; missing/mismatched/future evidence never causes fixture fallback. |
| UI behavior | Existing keyboard/radio controls, internal chat scroll and 64px agent process strip remain. New acknowledgment/skip fields have labels; long safe error text stays readable. Browser smoke may run hidden only; do not take over the user's main screen. |

Meaningful test changes belong in `frontend/tests/components.test.jsx`, `api.test.mjs`, `useRun.browser.jsx` and `proofComparison.test.mjs`. Replace the existing unconditional “ready covers permit publication without waiting for video” expectation with explicit-skip cases. Add actual callback/body interaction checks for the new controls; static markup alone cannot prove the correct `action`, versions or booleans were posted. Exercise the >100-event reader and persisted-busy reload, which current small fixtures do not cover.

Frontend baseline reported by the coordinator: **44 tests passed** after dependency installation. This source review did not rerun that suite or claim browser/provider integration. The implementation command, from `frontend/`, is:

```sh
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node build.mjs --tests
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node --test tests/*.test.mjs .test-build/*.test.mjs
```

Verdict: fix findings 1–7 before calling the native local UI integration complete. The smallest complete change extends the current components and client; no new frontend framework or replacement screen is justified.

Not checked: actual rendered layout/browser interaction, paid provider output, server authorization/persistence internals or self-improve correctness; those remain the relevant implementation/reviewer gates. Passing the existing 44 tests does not establish the new integration behavior.
