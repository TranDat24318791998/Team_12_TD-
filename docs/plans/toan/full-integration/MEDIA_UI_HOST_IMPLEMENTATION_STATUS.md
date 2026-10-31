# Media, UI and local host implementation status

Implemented in the shared worktree; no paid provider generation was run in this lane.

- `ContentService(bridge, settings, llm, *, media_client=None)` exposes `async process_job(run_id, job_id)` and `async close()`. It consumes the Data worker's scoped snapshot, checksum-verified supplied product bytes, confirmed style IDs and reference documents. It invokes the native Content role, validates the exact publication text through Data before any paid reservation, then submits A, its video and B/C, and imports checked output bytes through Data. Its heartbeat uses short Data transactions. A restart with persisted provider state becomes unknown before another native or media invocation. Known budget and unexpected errors terminalize the job with safe codes.
- The gateway uses the media HTTP contract with a backend-derived owner, frozen reservation key/body, one same-key transport retry, capability preflight, signed same-origin downloads without bearer credentials or redirects, SHA-256/MIME/magic/size checks, and limits of 10 MB per image and 50 MB per video. Unreadable or malformed accepted responses remain unknown unless the same-key recovery returns a valid job, including when recovery returns a rejection. Unknown outcomes do not create a replacement paid operation. The approved demo D product kind is obtained from Data; desktop and handheld are both supported.
- Experiment supports optional logo, actual image role numbering, handheld/desktop prompts and vision validation, non-conflicting bright backgrounds, local storage labels, readiness capability version, output SHA/size/duration and explicit uncertain/interrupted outcomes. Its app is import-safe and launched with the factory.
- React captures a seller brief, sends card and draft identities/versions, requires a video skip or review acknowledgment where applicable, detects media load failures, drains paginated events, tracks asynchronous operations, honors server busy state, uses the actual run horizon and labels preview/reference proof honestly. Existing layout remains.
- `scripts/local_stack.py` provides `start`, `status`, `stop`; loopback ports 8000/8010, one worker each, no reload. It checks foreign listeners and queued work before starting, verifies the application's `/ready` Data and worker status, and signals only recorded processes whose identity and expected command still match. Runtime and data files are retained. `status` is read-only and reports missing input separately. The coordinator owns actual launch and live configuration.

Verified without paid calls:

```text
PYTHONPATH=data ./.venv/bin/python -m pytest tests/integration/api/test_media_bridge.py tests/integration/hosting/test_local_stack.py -q
12 passed
PYTHONPATH=experiment ./experiment/.venv/bin/python -m pytest experiment/tests -q
27 passed
frontend npm test (bundled Node)
45 passed
frontend npm run build (bundled Node)
passed
./.venv/bin/python scripts/local_stack.py status
media: STOPPED; app: STOPPED at inspection
```

The real bridge test starts an isolated loopback experiment service with fake OpenAI/Muse providers, uses actual Data storage and native tool messages, accepts the neutral wording “cho sản phẩm”, generates decodable JPEG/MP4 bytes, checks A→video→B/C request order and verifies same-attempt asset binding and review metadata. Additional real-Data bridge tests reject overlong or unsupported claims before paid submissions and retain an unknown reservation after malformed accepted responses; retries do not increment the draft or change the frozen key/body. Tests also cover missing input, exhausted budget, interrupted reservations, stale process identity and an unready worker. These are fake-provider checks, not live model, quota, audio, visual quality, browser-rendering or paid-generation evidence. Full seller acceptance, lifecycle start/restart and the full repository suites remain coordinator-owned integration gates.

The accepted-start interaction regression uses real React in a private headless Chrome context with an in-process fake API. It checks navigation while the accepted operation remains running, streamed events, terminal failure, a single POST and a rejected start that remains on Shop. Re-run after the frontend build from the repository root:

```sh
PATH="/Applications/ChatGPT.app/Contents/Resources/cua_node/bin:$PATH" /Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node /Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/corepack/dist/npm.js --prefix frontend run build
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node frontend/tests/start-operation.browser.mjs
```

Result: **PASS** on this machine, with no visible browser and no provider calls. Offline media reuses the checksum-verified Data-bound original image for all three explicitly labeled cached choices and requires explicit video skip. Content text follows the independent injected LLM mode and budget; with both modes offline no provider call is made. A missing or corrupt original stays unavailable.

The saved-simulation proof selector and its report/evidence downloads are covered by a second private headless interaction test:

```sh
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node frontend/tests/proof-source.browser.mjs
```

Result: **PASS** using a fake API, including missing-artifact behavior without preview fallback. The report remains explicitly labeled as a precomputed offline simulation with provider evaluation not run. On an unauthenticated Proof request, the client establishes the normal seller session via `/api/state` and retries once; the artifact GET remains authenticated and read-only. The saved-report action says “Bắt đầu phiên demo mới” and does not claim to recompute the comparison.

The launcher checks pending/running learning handoffs before startup and leaves the media process running if the app cannot drain. Local media readiness probes a uniquely created temporary file and rejects an unusable objects directory. Latest focused checks: hosting **6 passed**, experiment **28 passed**, frontend **48 passed**, frontend build and both headless interaction tests **passed**. SI reports that the actual exported artifact matches the selected envelope; the coordinator owns the final hosted smoke and full-suite run.
