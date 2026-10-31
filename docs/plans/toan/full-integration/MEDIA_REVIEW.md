# Media review — Astra MAX

What this change does: The proposed integration reuses `experiment/` for OpenAI images and Muse video, while the native Content Agent supplies listing text. Data remains the sole owner of approval, drafts, publication, campaigns and business events. This review covers media and its required seller-review boundaries; API/UI composition and hosting have separate review lanes.

Reviewed 31 October 2026 at `33fbdd5`, including media `a0a93f0`, Data `9621b14` and frontend `bd78f8e`. Source was not edited. Existing user plans were preserved. No paid calls, secret reads, visible browser actions or dependency installation were performed.

## Current facts and stale blockers

| Previous plan statement | Current source evidence | Decision |
|---|---|---|
| Data activates a content campaign on offer acceptance. | `data/growth_data/facade.py:93–99` creates content for `content_refresh`; only the no-content branch calls apply. `data/growth_data/media.py:93` accepts an approved, unapplied proposal. | **Already fixed.** Do not implement this change again. |
| Data cannot publish and activate atomically. | `media.py:149–158` publishes and calls campaign apply inside `service.command`; `service.py:134–147` commits the effect and idempotency receipt together. `service.py:450–452` rejects content campaigns without published content. | Reuse this transaction. The rollback test at `data/tests/test_integration_safety.py:120–134` passed in this review. |
| Media must install and mutate the authoritative core Session draft. | `app/content/service.py:1` is still a stub; the old MI03 design owns a second writable Session. Data already persists `content_jobs`, `content_versions`, assets and decisions. | Supersede the Session-owned MI03 business writes. Implement a Data-bound media worker; do not call core `submit_decision`/`apply_reviewed_content` as a second business workflow. |
| Native Content needs a new agent implementation. | `app/agents/content.py:15–35` already runs the native tool loop. `app/agents/tools.py:135–145` checks approval and returns facts, confirmed style and feedback. | Reuse this role through the core lane's read-only execution context/adapter. Preserve actual Data card, proposal and brief identity. |
| Image/video service already supports D. | `experiment/video_api/models.py:103` requires a logo. `image_pipeline.py:43–49` fixes product identity to a desktop fan. `openai_media.py:30–37,53–68` rejects non-desktop fans. | **Still blocked.** D is the handheld fan; do not replace its SKU or submit a desk-fan example. |
| Existing JSON job idempotency needs replacement. | `experiment/video_api/store.py:55–71` uses `BEGIN IMMEDIATE` and unique owner/key; a different body conflicts. `main.py:272–280,297–305` uses it. | Keep it. Add durable business binding and uncertainty/budget semantics around it. |

Update the stale claims in `docs/DEMO_CONTRACT.md` section 5 and `media-integration/UI_DATA_HANDOFF.md` section 1 during implementation. The media plans remain useful for provider behavior; their Session-authority and local `/media` assumptions need adaptation to Data's existing asset storage.

## Must fix

1. **Missing files can be published and activate paid campaigns.**
   - What this is: `data/growth_data/media.py:145–148` checks the selected cover's database readiness.
   - Problem: It does not check that the object still exists or matches its recorded size/hash. An isolated reproduction deleted B's object, then Apply returned **200**, the campaign became active, and the selected asset download returned **404**.
   - Fix: Before publication mutations, verify the selected asset belongs to the current run/product/job, is ready, and its permitted local path exists with the recorded size/SHA. Apply the same check to an included video. Reuse `object_path` and the validation pattern in `complete_upload` (`media.py:17–20,80–87`). Keep the decision, publication, activation, event and receipt in the same command transaction.
   - If skipped: Listing/campaign success is reported with missing media. A review acknowledgment must never bypass this gate.

2. **The provider pipeline describes and validates the wrong product.**
   - What this is: Image prompts, vision output, planning and motion prompts all assume desktop fans (`models.py:14,68,86`; `image_pipeline.py:43–49`; `muse_pipeline.py:17–27`; `openai_media.py:30–90`).
   - Problem: A real D handheld image can be rejected or transformed toward a desk fan. Removing the logo field alone would also shift input-image numbering while the prompt still says image 1 is a logo and image 2 is the product.
   - Fix: Implement the existing MI01 `product_kind=handheld_fan|desktop_fan` contract end to end. Keep desktop as the lab default; explicitly send handheld for D. Make logo optional and build image-role numbering from actual inputs. With no logo, instruct the provider not to invent one. Use kind-aware analysis/planning checks and handheld-specific grip/shape instructions. Add `background_preference=default|bright`; bright switches C away from the charcoal preset, rather than appending conflicting instructions.
   - If skipped: A technically successful media job does not represent the advertised SKU.

3. **The content bridge and bounded paid-job state do not exist.**
   - What this is: `app/content/service.py:1` has no implementation; root settings have no `media_api_*` fields (`app/core/settings.py:20–39`). The experiment queue limit counts concurrent jobs, not paid jobs per run (`store.py:63–65`).
   - Problem: A naive retry worker can submit extra jobs, lose remote IDs on restart, or let a late result overwrite a newer attempt. The generic exception path rewrites every failure as `stage=failed` (`experiment/video_api/main.py:68–77`), hiding timeouts whose paid outcome is unknown. Restart recovery correctly avoids resubmission but only reports `interrupted` (`store.py:107–111`).
   - Fix: Freeze one request/key per `(run,shop,proposal,card,brief,content-job,attempt,slot)` before network submission. Persist slot reservations, body hash, owner, remote job/input/output IDs and `outcome_unknown` in the Data DB. Count reservations across the run under its write transaction: at most nine Images jobs and three Muse jobs, with three media text/vision calls per video recorded separately from the native LLM budget. Same-key/body recovery uses the reservation once. Retain reservations for unknown outcomes; do not issue a new draft/key until resolved. Preserve known Muse task IDs and distinguish definitive failure from unknown submission/poll outcome.
   - If skipped: A small queue and a three-attempt UI do not prevent repeated charges or lost-job retries.

4. **The worker result cannot carry the planned review/provenance contract.**
   - What this is: `WorkerImage` accepts only ready images; `WorkerVideo` lacks source/reference/review fields (`data/growth_data/models.py:359–391`). `media.py:183–203` duplicates strict key allowlists. The service can return `done` with `visual_review_passed=false` (`experiment/video_api/muse_pipeline.py:124–128`).
   - Problem: Sending the planned metadata currently gets rejected. Data publication checks neither video review nor an explicit skip choice; its legacy Apply body accepts only `cover_option` (`facade.py:117–124`). A worker success can even retain a running video without an asset (`models.py:367–378`).
   - Fix: Extend the shared models and result validators together. Persist per-slot `source`, error, actual asset ID and status; video also carries reference A plus its content-job/attempt binding, review boolean/notes and actual duration. Default missing review to unknown, never true. Require selected cover readiness. For an included video require ready status, valid local bytes and either review passed or explicit seller acknowledgment. `skip_video=true` publishes no video and late callbacks cannot attach it. Persist skip/ack/cover and exact draft identity with the approval receipt.
   - If skipped: Seller approval cannot distinguish a reviewed clip, an unfinished clip, a failed review and an omitted video.

5. **Bright retry currently preserves the old video's identity.**
   - What this is: Data defaults `retry_scope` to `images` (`models.py:124–130`; `facade.py:110–115`). It preserves text/video and enforces that contract (`media.py:116–119,207–210`).
   - Problem: The integrated media plan requires video from A of the same new draft. Default retry would keep the previous draft's video. Retry also supersedes queued/running work immediately (`media.py:121–123`) without checking an unresolved paid outcome.
   - Fix: The integrated bright-background action explicitly requests `retry_scope=all`; keep images-only semantics intact for its existing callers. Validate supported feedback, all required terminal/known outcomes, expected job/content attempt and remaining budget before incrementing attempt or reserving slots. Use actual browser-visible card/brief/draft identity; do not silently resolve an old click against the latest draft. Carry the new A result asset ID into the new video request.
   - If skipped: The seller sees new bright covers with a stale video, and retry can abandon a paid job whose outcome is unknown.

## Smallest complete implementation packet

These tasks are sequential at the Data transaction boundary. Reuse the existing queue and asset subsystem; no second business database, Redis, Celery, separate renderer or new UI framework.

| Task | Concrete files | Required result |
|---|---|---|
| M1 — complete MI01 | `experiment/video_api/{models,image_pipeline,openai_media,muse_pipeline,main}.py`, focused experiment tests | Kind-aware handheld/desktop behavior, optional logo, bright presets, capability version, JPEG/MP4 SHA and byte length, actual duration/review metadata, explicit uncertain failure. `GET /v1/readiness` advertises `growth-media.v1`, supported kinds, optional logo and bright support. |
| M2 — HTTP client | New `app/infrastructure/media_gateway.py`; `app/core/settings.py`; safe `.env.example` documentation | Typed JSON jobs; backend-derived owner; upload IDs reused by hash; frozen idempotency keys; bounded polling; signed download/import and safe errors. No `experiment` imports in app and no provider credentials in browser payloads. |
| M3 — native Content worker | `app/content/service.py`, small `app/content/media_brief.py`; existing `app/agents/content.py`/core read-only context seam; Data adapter in the integration lane | Claim a persisted approved job, snapshot public facts + confirmed style + feedback, run native Content, then A → submit video from A → B/C. No LLM/provider call inside a Data write transaction. Native events and results go to the same Data event authority. |
| M4 — persistence/review boundary | `data/growth_data/{models,media,facade}.py`; DB-owner migration; result/progress route contracts | Durable slot state, budget reservations, real card/brief/content binding, progress, version checks, heartbeat, local-file checks and atomic reviewed publication. No independent mutation of `Session.states`, `Session.content_draft` or `Session.apply_receipts` in the product path. |
| M5 — regression and handoff | Existing Data/experiment tests; new real-bridge integration test; media contract fixtures; implementation report | One fake-provider HTTP flow proves native tool use, job identity, downloaded assets, seller gates and feedback→confirmed style. Report offline and live gates separately. |

M4 can use one `provider_state_json` column on `content_jobs` for the four slot bindings rather than create a general job framework. Count persisted reservations across that run within `BEGIN IMMEDIATE`; reopening a worker must not reset a budget. The DB lane owns final migration numbering and shared brief fields. Data already has `assets`/`asset_jobs`; use them instead of copying files into a second authoritative media registry.

The Data content lease begins at creation and lasts 120 seconds (`media.py:126`); a `running` result renews it and increments job version (`media.py:167–169,217`). Recovery checks expiry every second (`api.py:33–39`; `service.py:626–633`). The worker must heartbeat during remote queue, image generation, Muse polling and download; preserve the returned version for its next write. Expiry must preserve provider bindings and unknown outcomes, not authorize regeneration. A single worker/orchestration task per current content job is sufficient.

Worker-mode drafts currently contain cached geometric fallbacks while still queued (`media.py:110–126`). Project actual running/failed slot status in the integrated path; do not show these as generated successes. Allow partial terminal results with a usable B/C and explicit video skip when A fails. If Apply is allowed while unselected slots run, freeze publication and reject all subsequent draft/listing updates after it; provider results may only finish their own internal records.

## Asset and provider contract to retain

- Product input is a validated, approved handheld D image. `assets/products` contains no usable product image in this checkout, and Data's source images are labeled placeholders. Reject missing input before paid calls; do not use the current geometric cover as SKU evidence or silently switch to text-to-video.
- Upload through experiment `/v1/assets`; submit images through `/v1/image-jobs` and video through `/v1/jobs`. The raw Muse `/v1/videos` API is a different endpoint/body. Keep the existing `MuseMedia` wrapper: it persists task ID before polling and restricts authenticated downloads to its gateway (`muse_media.py:29–59,70–91`).
- Video is five seconds requested, `realistic_human`, `9:16`, `voice=muse`, `music=none`, one handheld product. Its reference must be A's service output asset from the same attempt. Choosing B/C for the cover does not generate another video. Preserve supplied narration and use verified facts only (`openai_media.py:69–72`).
- Service output needs SHA-256, byte length, MIME, asset/job IDs and actual duration. Current image/video results lack SHA (`image_pipeline.py:64–69`; `muse_pipeline.py:117–128`). Signed links expire and are transport only (`main.py:154–168`), never durable listing paths.
- Download the exact signed image/play path through the configured media-service origin, with redirects disabled and no Bearer on signed playback. Renew an expired signature by GET job once; never regenerate. Stream to a temporary file, enforce a size/MIME/checksum limit, then atomically import via Data asset upload/complete. Align the bridge video cap with Data's current **50 MB** limit (`media.py:40–41`; `models.py:157`), rather than downloading 150 MB which Data cannot accept.
- Preserve authenticated Data asset URLs in seller projection (`media.py:190,202`; `api.py:173–176`). Never persist a MinIO URL, signed query, absolute local path, raw prompt, API key, private cost or Persona into public listing fields.
- A valid container is required for the playback acceptance test. Data currently tests MP4 signatures only (`media.py:71–75`; `data/tests/test_integration_safety.py:224–225`). A signature-only fixture does not prove playable video. The real bridge test uses decodable JPG/MP4 with matching hashes.

## Media acceptance gates

1. Before approval, missing product input or unsupported capability: **zero paid jobs** and no listing/campaign change.
2. Native Content's fake model consumes a real `ToolMessage` with Data-authorized facts and confirmed style; private business fields never reach experiment. Media planning cannot replace the native Content role.
3. Capture handheld image requests with/without logo and bright/default presets. Validate actual prompt input numbering and absence of desktop-only constraints for D.
4. Persist A's output ID before video submission. Video references A of the same run/job/attempt; B/C selection does not submit another video. A failure submits no video; usable B/C can publish with explicit skip.
5. Duplicate transport request/restart preserves body, key, reservation and remote ID. Changed body conflicts. Unknown POST/poll outcomes block a new paid attempt. Run-wide limits remain nine Images/three Muse across cards and process restart.
6. Heartbeat keeps a long fake generation alive; expired/superseded/reset/published job results cannot mutate the current draft or listing. GET state/events never submits media or duplicates feedback evidence.
7. Stale retry/apply version returns conflict before cost or mutation. Bright retry is `all`, creates attempt 2, and preserves original listing and Rules. Three total attempts, including the first.
8. Missing/corrupt selected cover blocks publication and campaign activation. Video false/null review requires acknowledgment or skip; acknowledgment never overrides missing/corrupt media. Skip publishes `video=null`; a late callback cannot append it.
9. Same key/body Apply returns one receipt/effect; changed cover/skip/ack conflicts. Inject failure after campaign insert and verify listing, campaign, approval and event all roll back.
10. Persist one feedback event with canonical job/card/proposal/negotiation/attempt refs. SI reads this committed evidence; candidate style is not default. Seller Yes updates the single Rules authority; a later Content invocation without new feedback selects bright presets from that confirmed rule.

## Verification performed and remaining gates

Command from repo root:

```sh
PYTHONPATH=data .venv/bin/python -m pytest -q data/tests/test_handoffs_and_content.py data/tests/test_integration_safety.py data/tests/test_commands_and_artifacts.py
```

Result: **20 passed, 1 failed** in 10.62 seconds. Failure: `test_images_only_retry_preserves_video_and_rejects_text_changes`, line 236, receives `409 JOB_TERMINAL` instead of the expected `422 RETRY_SCOPE`. An isolated in-memory request trace confirmed the second result targets **attempt 1, status succeeded**. The test chooses `jobs[-1]` at line 231, while `data/growth_data/api.py:123` supplies an unordered query. Fix canonical current-job selection/ordering and make the test select the expected proposal/attempt; do not weaken the terminal-job guard.

Separate isolated reproduction: deleting selected cover B before Apply produced `{apply_status:200, campaign_active:true, selected_download_status:404}`. This confirms finding 1; only a temporary test directory was changed.

Experiment tests were not executed: `experiment/.venv` is absent, and the root interpreter lacks `imageio_ffmpeg`, `minio` and multipart support. Importing `video_api.main` currently invokes `create_app()` and loads local settings (`main.py:481`); this review did not read those secrets. The media test runner should inject explicit fixture settings before import or make composition import-safe. No provider access, model entitlement, MinIO connection or real handheld asset has been verified. Existing deployment notes are not evidence of live readiness on this checkout.

**Verdict: fix 1–5 before MEDIA_INTEGRATION PASS. MEDIA_LIVE: NOT_RUN.**

Not checked: live providers, paid billing, remote model availability, actual video/audio quality and general API/UI/hosting integration. No extra provider, GPU renderer or queue framework is needed for this slice.
