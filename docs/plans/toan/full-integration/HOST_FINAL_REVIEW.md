# Local hosting final review — Astra MAX

Reviewed the current working tree on 31 October 2026 against P09 and `HOST_REVIEW.md`. Scope: the implemented `scripts/local_stack.py start|status|stop`, two loopback services, persistence, ownership, readiness, imports and no-paid restart behavior. The absence of a `smoke` subcommand is intentional: the coordinator owns actual integration verification. D's user-approved desktop-fan input supersedes the earlier handheld-only requirement.

**Current verdict: PASS for the three hosting findings after the focused re-review.** No unresolved P0/P1/P2 from this review remains. The coordinator still owns the final real-service restart and persisted-session verification. This review did not start, stop, reset or modify either real service.

## Focused re-review after fixes

- **Finding 1 resolved:** `pending_jobs` accepts an explicit status tuple; `start()` checks `learning_handoffs` in `pending`/`running` before either child launches. Both states reject with zero launches in the regression. A separate temporary-DB check confirms completed/skipped handoffs do not count as unfinished work.
- **Finding 2 resolved:** `LocalStorage.check()` uses `NamedTemporaryFile` for exclusive creation, writes/flushes/reads its own bytes and deletes only its probe through the context manager. The API regression preserves an existing object, leaves no probe, and returns 503 when the object directory is replaced with a file. Existing pre-provider storage checks now exercise this method too.
- **Finding 3 resolved:** `stop()` saves the manifest and fails immediately if the app has not drained; media remains running. Failed-start cleanup likewise stops cleanup before media when its newly created app cannot drain. Isolated mocked checks confirm this path and the normal app-then-media idle-stop path.
- Reran **hosting: 6 passed in 0.03s** and **full media suite: 28 passed in 2.27s**, using the commands below. Tests use temporary homes/fake providers; no live queue or paid call was touched.

```sh
LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest tests/integration/hosting/test_local_stack.py -q
PYTHONPATH=experiment experiment/.venv/bin/python -m pytest experiment/tests -q
```

**Final cosmetic observation resolved:** inspected `/watch`; its storage label now uses `settings.storage_backend`, displaying “Lưu trữ tệp cục bộ” for local files and “Lưu trữ MinIO” for MinIO. The coordinator reports the existing signed-watch escaping test passed. No unresolved observation remains from this hosting review; no broad suite was rerun for this documentation closure.

## Original findings — all three resolved

The descriptions and reproductions in this section describe the pre-fix source; the current status and evidence are above.

1. **[P1] Restart can automatically execute pending Learning under a stored live run.**
   - Location: `scripts/local_stack.py:start`, Data preflight following the media queue check; `app/runtime/data_worker.py:_loop` and `_night`.
   - The launcher checks queued/running `content_jobs` and `operations`, but omits `learning_handoffs`. The worker immediately selects handoffs with `status='pending'`. `_night` overrides the process setting with `llm_mode=run['mode']`, so even the documented `LLM_MODE=offline ... start` command does not disable a pending Learning invocation for a previously live run. A normal night close can leave a pending handoff after its close operation has already succeeded.
   - Isolated reproduction: a temporary DB containing empty content/operation tables and one pending learning handoff passed the real `start()` preflight. With process launches mocked, the recorded launches were **`['media', 'app']`**. No actual server or provider was invoked.
   - Small fix: before launching either child, include learning handoffs in the existing unfinished-work check, with their actual **`pending` and `running`** states. Make the helper accept an explicit status tuple or add one narrow handoff query. Preserve the current refusal behavior; do not delete/change handoffs, downgrade stored runs or automatically retry them.
   - Regression: create each pending/running handoff state in a temporary SQLite DB with no queued content/operations; `start()` must reject before any `launch` call. Include completed/skipped handoffs as allowed controls. The test must not call a real model.

2. **[P2] Local readiness still succeeds when object storage cannot save files.**
   - Location: `experiment/video_api/storage.py:LocalStorage`; `experiment/video_api/main.py:readiness`.
   - P09 explicitly requires a local write/read/delete probe. `LocalStorage` has no `check()` method, so readiness skips it and returns ready based only on the backend name. Image and video pipelines also call storage checks before provider work; with no local check they can incur generation cost before discovering the output cannot be saved.
   - Isolated reproduction: construct the media app with explicit fake settings and `worker_enabled=False`; replace its temporary empty `objects/` directory with a regular file. Authenticated `/v1/readiness` returned **200, `ready=true`**; the same storage's next `put()` raised **`NotADirectoryError`**.
   - Small fix: implement `LocalStorage.check()` using an exclusively created unique temporary file under `objects`, verify the written bytes and delete only that probe in `finally`. Existing readiness and pipeline call sites will then use it. Add one passing probe/cleanup test and a failing-storage HTTP 503 test. No MinIO or new dependency is needed.

3. **[P2] Stop shuts down media even when the root worker has not drained.**
   - Location: `scripts/local_stack.py:stop`.
   - When `stop_entry(app)` returns false after its grace period, `stop()` prints that the app remains running and continues to signal media. The native worker can still be polling or importing that media job. This turns a slow graceful shutdown into an avoidable interrupted provider outcome and contradicts the intended root-before-media drain order.
   - Isolated reproduction: mock app stop as unsuccessful and media stop as successful. `stop()` invoked both in order **`['app', 'media']`** and retained only the app manifest entry.
   - Small fix: if the root app is still alive, save the unchanged remaining manifest and return an error before signaling media. A later stop can continue after the root exits. Keep the existing no-SIGKILL policy. Regression asserts media is not signaled in this case, then verifies normal idle stop still stops both owned processes.

Original minor display observation, now resolved: `/watch` hardcoded “MinIO lưu trữ” for Muse jobs even under `storage=local`. The current label selects the configured backend, matching the already-correct image metadata and stages.

## Verified behavior

- **Read-only live status:** `media: READY PID 24183`; `app: READY PID 24198` at inspection. No lifecycle mutation was performed.
- **Import safety:** imported `app.main` and `video_api.main` in separate interpreters after replacing `sqlite3.connect` and `dotenv.dotenv_values` with failing guards. Both imports passed without settings/DB initialization. Media factory startup no longer has eager `app=create_app()`; root's legacy ASGI export is lazy.
- **Composition:** the root factory reuses the actual Data app, keeps its worker/recovery lifespan, serves React after API routes and returns JSON for unknown API paths. The managed command uses `--factory`, one uvicorn worker, loopback binding, no reload and no HTTP access log containing signed query strings.
- **Ownership:** the launcher records process start identity plus expected target/port/root, checks port ownership and signals only matching entries. The existing reused-PID regression passes. Native and media workers hold runtime locks; business and provider runtime directories are separate. The launcher does not delete persistent data.
- **Dependencies:** root requirements now pin the added ReportLab and Pillow dependencies; existing Python 3.11/root and Python 3.12/media interpreters execute the focused suites. No new service or deployment framework is needed.
- **Signed media:** the existing isolated media API suite covers auth before upload, owner scope, signed playback/Range, expiry/tampering and restart behavior. It passed with fixture bytes and temporary storage; this is not paid provider quality evidence.

Commands run from the repo root:

```sh
LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest \
  tests/integration/hosting/test_local_stack.py tests/integration/api/test_health.py -q
# 6 passed in 1.40s

PYTHONPATH=experiment experiment/.venv/bin/python -m pytest experiment/tests/test_api.py -q
# 13 passed in 0.56s

.venv/bin/python scripts/local_stack.py status
# Both existing processes READY; read-only.
```

The three failure reproductions used temporary directories, explicit fake settings and mocked process launch/signaling. They changed no repository source and touched no live DB, provider or worker. The focused source diff check had no whitespace errors.

## Coordinator evidence and remaining acceptance

Read `data/runtime/local-stack/verification.json`: it records the same external offline run through native negotiation, cached-original content retry/explicit video skip/Apply, night publication and day-2 style confirmation, with zero provider calls and 64 LLM calls remaining. The coordinator separately reports real stop/start, health/readiness/static 200, correct source-photo SHA, Range 206 and SQLite integrity/FK checks. Those are coordinator-performed gates, not tests repeated by this reviewer.

The three fixes and focused regressions now pass. Let the coordinator perform the final real stop/start and persisted day-2/session/asset/Knowledge verification. Keep live generation/provider quality marked separately from local-host readiness. No extra smoke CLI, supervisor, Docker, MinIO daemon, tunnel or cloud deployment is required.

Not checked: paid generation, provider entitlement/quality, visible-browser playback or the coordinator's final full-workflow restart. No credentials were printed, no paid calls or visible UI actions occurred, and this report is the only file written by this review.
