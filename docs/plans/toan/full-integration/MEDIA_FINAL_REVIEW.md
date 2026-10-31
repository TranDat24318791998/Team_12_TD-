# Final media review — Astra MAX

What this change does: The implementation connects approved Data content jobs to the native Content role, OpenAI Images and Muse through the experiment HTTP service. Data owns the durable job bindings, budgets, assets and publication. **D is now the desktop fan from the imported source assets**, as explicitly requested; the old handheld-D requirement is superseded.

Reviewed the working tree on 31 October 2026 against baseline `33fbdd5` and the updated full-integration plan. This is a media-only review. UI, general API and hosting are separate reviews. No source edits, paid calls, secret-value reads, live provider calls or visible UI actions were performed.

## Latest bounded re-review — offline path, privacy and lease fences

**Current verdict: PASS for the reviewed media implementation, including the new offline-original branch. No new actionable media finding. MEDIA_LIVE remains NOT_RUN.** The previous two P1 fixes remain resolved. General UI/hosting and actual provider quality are outside this verdict.

Executed a focused re-review after the offline branch and Data bridge safeguards were added:

- `app/content/service.py:54–60,80–98` bypasses all media preflight/upload/generation when `MEDIA_MODE=offline`. It reuses the supplied original asset for A/B/C with `status=cached`, `source=cache`, `fallback_used=true`, and explicit text saying these are the same original image, not three newly generated images. `app/infrastructure/data_content.py:101–110` verifies the original size and SHA before reuse. Tests confirmed identical original asset IDs, working authorized URLs, no provider reservations/media calls, and corrupt originals remaining unavailable.
- Native Content still runs through its independently supplied LLM at `app/content/service.py:71–79`. An injected native transport was actually called while media stayed offline; when both modes were offline, neither provider was called and the native event source was `offline`. `LLMClient` still selects its own mode and reserves its own run budget before network (`app/infrastructure/llm.py:30–65`). The focused budget tests confirmed that shared limits and durable no-resend reservations remain intact.
- An offline draft with no video is rejected by native Apply unless the seller explicitly selects skip. The executed test received `409 VIDEO_SKIP_REQUIRED` without skip, then a successful listing with `video=null` with skip. This covers the offline seller gate in `data/growth_data/media.py:183–191`; it does not claim live video review/quality acceptance.
- The snapshot projection removes private financial/name clauses from native feedback and confirmed-style input while preserving the source audit records (`app/infrastructure/data_content.py:33–93`). The executed regression checked the actual `ToolMessage` and outbound fake media requests, retained safe bright/minimal style guidance, and found none of the injected private values.
- Expired or missing content leases now fence slot reservation, updates, heartbeat and asset import at `app/infrastructure/data_content.py:23–30`. Executed tests verified unchanged binding/version state and zero media submit after expiry. The three malformed-acceptance cases were also rerun: `MediaGateway.submit` still preserves unknown state and repeats only the original key/body (`app/infrastructure/media_gateway.py:81–110`).

```text
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q tests/integration/api/test_media_bridge.py -k 'offline or lease or private_feedback or malformed_accepted'
11 passed, 7 deselected in 13.57s

LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q tests/unit/infrastructure/test_llm.py -k 'bound_tools_and_shared_budget or durable_reservation_precedes_network'
2 passed, 2 deselected in 0.19s
```

Only these bounded checks were run in this pass. No paid calls, secret reads, source edits or UI actions. Earlier full-suite/experiment counts are not presented as fresh reviewer executions.

## Previous fix verification — both findings resolved

**Previous verdict: PASS for the two reported media blockers and the previously reviewed offline media slice. MEDIA_LIVE remained NOT_RUN.** No unresolved finding from that review remained. This did not replace the separate native seller-flow, UI or hosting acceptance gates below.

Verified the corrective working tree on 31 October 2026:

- **Finding 1 resolved.** Native runner and Data now use `data/growth_data/text_validation.py:7–26`. `ContentService` calls the exact Data publication validator before any paid slot reservation (`app/content/service.py:76–78`; `app/infrastructure/data_content.py:61–64`). Data calls that same validator again at result ingestion (`data/growth_data/media.py:183–189,205`). The real HTTP bridge now includes “cho sản phẩm” and succeeds. Separate overlength and unsupported-claim cases finish with `CLAIM_INVALID`, zero paid POSTs and no paid slot reservations.
- **Finding 2 resolved.** `app/infrastructure/media_gateway.py:81–110` validates successful envelopes, preserves uncertainty across recovery, and retries at most once with the same key/body. Actual Data bridge regressions cover invalid JSON, malformed job IDs/envelopes, and a rejection after an unreadable accepted response. All retain an unknown binding; seller retry returns `409 PROVIDER_OUTCOME_UNKNOWN`, with exactly one content attempt and no replacement submission. An additional in-memory check confirmed that unreadable 202 followed by a valid 202 recovers the original job using identical key/body.

Fix-verification commands/results:

```text
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q tests/integration/api/test_media_bridge.py -k 'real_http_bridge or invalid_text or malformed_accepted'
6 passed, 3 deselected in 7.30s

Isolated httpx.MockTransport: unreadable 202 → valid 202, identical frozen key/body
PASS
```

Only the fix regressions were rerun; the prior 27-test experiment result is retained as historical evidence, not presented as a new run. No paid services or local secret values were accessed.

## Initial findings — retained for traceability

### 1. [P1, RESOLVED] Valid native text is rejected after all four paid media jobs finish

**Historical evidence before the fix:** `app/agents/runner.py:44–55,107–112` accepted ordinary neutral words including `cho`, `để`, `trong` and `dùng` in native Content output. `data/growth_data/media.py:195–205` applied a different, narrower vocabulary at final result ingestion. `app/content/service.py:72–73` obtained the native text without validating it against the Data contract before generating media at lines 137–159; final ingestion happened at line 182. Native `ContentText` also had no length bounds (`app/domain/models/content.py:6–9`), while Data required title ≤120 and description ≤5000. These line references describe the original reviewed tree.

**Reproduction:** I ran the existing real HTTP bridge fixture with one in-memory change to its fake native model: append ` cho sản phẩm` to the valid desktop description. The native runner accepted the result and the experiment fake providers completed **four jobs**. Data then rejected the content and the bridge ended with `CONTENT_WORKER_FAILED`. Only temporary test storage was used.

**Impact:** A normal, harmless wording choice can consume three Images submissions and a video submission, then discard the usable draft. Under the native driver, the failure branch replaces all visible options with unavailable assets (`data/growth_data/media.py:242–247`), so the seller cannot use the already generated output.

**Smallest fix:** Align the native and Data text contract. Use one verified-facts validator, including supported neutral words and length limits, before the first media reservation/submission and again at Data result ingestion. Preserve the verified-facts restriction; do not simply remove validation. If the native response violates the final contract, use the already verified source text or fail explicitly before media cost. Coordinate this shared validator between the media and Data owners.

**Required regression:** A fake native response containing `cho sản phẩm` must complete the real Data/media bridge. An overlong or otherwise invalid response must be rejected or replaced before `reserve_slot`/media POST. Assert provider request count, final job status and usable draft, not just an emitted Content event.

### 2. [P1, RESOLVED] An unreadable successful submit response is treated as a safe rejection

**Historical evidence before the fix:** `app/infrastructure/media_gateway.py:81–95` mapped `ValueError` from `response.json()` to `MediaError('MEDIA_SUBMIT_REJECTED')` with `unknown=False`, even after HTTP 202. `app/content/service.py:103–109` therefore recorded the reserved slot as `failed`. `data/growth_data/media.py:98–99` blocked a new attempt only for reserved/running/unknown slots, permitting a new paid key despite uncertainty about the accepted job. These line references describe the original reviewed tree.

**Reproduction:** An `httpx.MockTransport` returning HTTP 202 with `accepted but broken json` produced:

```text
MEDIA_SUBMIT_REJECTED, unknown=False
```

No network or provider was called for this reproduction.

**Impact:** The service may already have committed and charged the job; a truncated or malformed success response is not evidence of rejection. A seller retry can submit replacement work under a new idempotency key. The total run cap still limits charges, but the promised no-duplicate recovery behavior is violated.

**Smallest fix:** Separate status rejection from response decoding. After a successful status, an unreadable or invalid job envelope must recover at most once with the **same frozen key/body**, then remain unknown if a valid owned job ID cannot be obtained. Validate the returned job ID/status before marking a slot running. Retain its reservation and block new paid attempts until the outcome is known. Keep definitive pre-acceptance 4xx rejection handling distinct.

**Required regression:** Exercise HTTP 202 with invalid JSON through the real `ContentService`/`DataContentBridge`, not only the gateway. Assert the binding remains unknown, its reservation is not released, retry does not increment attempt or create a new key, and any recovery request repeats the original key/body exactly.

## Confirmed improvements and bounds

- The actual Data bridge is implemented; `app/content/service.py:65–73` passes a typed `ContentContext` into the native tool loop. The real HTTP test proves the fake model consumes its `ToolMessage`, imports real decodable JPG/MP4 bytes, submits in A → video → B → C order and associates the video with A from the same attempt (`tests/integration/api/test_media_bridge.py:57–105`).
- Desktop/handheld identity is now explicit throughout image, analysis, plan and video prompts. Optional-logo input numbering and bright premium-style substitution are implemented (`experiment/video_api/image_pipeline.py:43–59`; `openai_media.py:30–37,40–68`; `muse_pipeline.py:16–29`). Desktop D is correct and is asserted in the real bridge test.
- `DataContentBridge.reserve_slot` persists request/hash/key before submission and counts all run reservations under a write transaction, capped at nine images and three videos (`app/infrastructure/data_content.py:61–79`). Media text/vision counters are separately bounded to three per video at lines 91–94.
- The reported budget-exception and worker-reentry fixes are covered and passed: a budget Fault terminalizes the job without a second native invocation; persisted provider state becomes unknown before another model/provider call (`tests/integration/api/test_media_bridge.py:136–175`). No automatic paid job replay was found in that reentry path. This is safe failure, not successful recovery of an interrupted finished result.
- Experiment preserves remote Muse task IDs, uses zero OpenAI SDK retries, and exposes interrupted/unknown outcomes (`experiment/video_api/main.py:75–79,158–162`; `muse_pipeline.py:84–90`). This does not remedy finding 2 at the gateway's response-decoding boundary.
- Gateway playback uses the configured origin and exact job path, omits bearer headers, disables redirects in its own HTTP client, refreshes an expired signature by GET, and checks MIME/size/hash before Data import (`app/infrastructure/media_gateway.py:23–25,117–150`). Data publication now verifies local file existence, size and SHA under the selected job's asset relationship (`data/growth_data/media.py:148–179`). The earlier missing-cover publication defect is fixed in source.
- The native publication path now requires a ready included video plus passed review or explicit acknowledgment, or explicit skip (`data/growth_data/media.py:151–166`). Draft identity checks are present at `data/growth_data/facade.py:152–155`; late terminal jobs fail bridge authority checks at `app/infrastructure/data_content.py:18–25`. These are source-reviewed here. Full native seller ack/skip/retry/publication HTTP acceptance is still a cross-lane integration gate; the media bridge fixture currently stops after successful worker ingestion.

## Verification

```text
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q tests/integration/api/test_media_bridge.py
4 passed in 5.01s

LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=experiment experiment/.venv/bin/python -m pytest -q experiment/tests
27 passed in 2.91s
```

The bridge suite explicitly injects a fake native model and an isolated loopback experiment service with fake providers. It does not contact real OpenAI or Muse. The two additional in-memory reproductions above confirm defects beyond those passing tests; no source/test file was changed to run them.

**Verdict: PASS within the offline media review bounds above; findings 1 and 2 are resolved by executed regressions. Live provider acceptance remains NOT_RUN.**

Not checked: live generation, real provider entitlement/quota, actual product/voice/visual quality, imported source image identity, full seller video review flow, general UI or hosting. No live success is claimed from the fake-provider tests.
