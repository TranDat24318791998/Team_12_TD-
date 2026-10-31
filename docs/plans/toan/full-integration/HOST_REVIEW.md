# Local hosting review — Astra MAX

Reviewed 31 October 2026 against `33fbdd5`. Scope: run the integrated seller application on this Mac, with persistent Data state, the existing React frontend and the existing media service. This is a review and implementation packet; the commands marked **after implementation** are not a claim that the integration exists or is running.

**Decision:** two loopback HTTP processes: the combined Data/native-agent/React application on **127.0.0.1:8000**, and the existing media application on **127.0.0.1:8010** with **`STORAGE_BACKEND=local`**. One native orchestration worker belongs to the root application's lifespan; one media processing thread belongs to the media lifespan. Use the existing Python 3.11 and 3.12 environments. No separate Data HTTP server, Node server, Docker, MinIO daemon, tunnel, Sites deployment or OS login service is needed for this request.

## Evidence and integration blockers

| Finding | Source and consequence | Smallest complete change |
| --- | --- | --- |
| Root HTTP currently serves a shell, not the integrated Data application. | `app/main.py` builds a separate FastAPI app; its seller route modules are largely stubs. `data/growth_data/api.py:create_app` already owns seller routes, authentication, DataService, recovery and internal routes. Merely starting the current root app can return health and HTML without a working seller backend. | Root `create_app` composes the Data factory, its lifespan and the native worker, then mounts React last. Do not mount Data below a second `/api` prefix or register the old seller facade beside it. API owner implements this composition. |
| There is no native worker in the current Data lifespan. | Data currently runs only a one-second recovery sweep. `AGENTS_REVIEW.md` specifies the new Data-bound native worker and its leases. | Start exactly one `app/runtime/data_worker.py` worker within the combined application's lifespan. Preserve the recovery sweep and coordinate its lease behavior with the worker. No `Session.new` business state or second event log. |
| Media import writes runtime state. | `experiment/video_api/main.py` ends with `app = create_app()`; the factory loads `.env`, constructs `Store`, creates directories and creates/opens `jobs.sqlite3` before lifespan. Tests importing helpers therefore touch the default runtime even when their fixture later supplies a temporary directory. | Use `video_api.main:create_app --factory`; remove eager default construction. Update `experiment/scripts/start_api.sh` and its references. Make root factory import-safe as it gains persistence too; update `tests/integration/api/test_health.py`, which currently imports `app`. Importing helper/factory modules must not open DBs, read secrets, start threads or contact providers. Explicit factory construction may load settings and initialize storage. |
| Local storage is implemented, but readiness and some labels overclaim. | `LocalStorage` implements `put/stat/chunks`; media playback uses this interface. Its lack of `check()` means `/v1/readiness` reports ready without proving objects can be written. `image_pipeline.py` still reports `uploading_minio`, a bucket and `minio_path` in local mode; `/watch` hardcodes a MinIO label. | Add a tiny local storage check that exclusively creates, reads and removes its own probe file. Use `saving_local`, null MinIO-only fields, and a storage-specific watch label for this profile. Preserve `storage=local` and the existing signed playback contract. Local storage does not mean fake generation; provenance must report the actual provider separately. |
| Input replacement can be lost on restart. | `DataService.__init__` calls `seed_shared`, which calls `prepare`; `prepare` rewrites `objects/originals/*-placeholder.png`. Data seed marks those bytes as geometric placeholders. | Never overwrite `D-placeholder.png` with a product photo. Import a new asset through Data's asset workflow, record its hash/provenance and bind its new ID to the intended product/input. Coordinate this binding with the Data/media owners. |
| Health does not prove a usable integrated application. | Root `/health` only returns `ok`; Data `/health` does not query the DB or verify native execution. Media `/health` only reports configuration booleans. | Keep cheap liveness. Add a root readiness route, proposed `/ready`, for a reachable authoritative DB/schema, loaded frontend and active native worker. The launcher/status reports storage readiness and input/capability readiness separately. A configured OpenAI key is not a successful model invocation. |

The media review's handheld-product, optional-logo, bright-style, durable submission and review/publication gates still apply. Starting two HTTP listeners does not satisfy those gates. `experiment/CODEX_DEPLOY.md` describes a MinIO + Cloudflare deployment; this user's explicit local-only scope supersedes those topology choices, while its Python 3.12, single-worker, secret, signed-link and recovery requirements remain applicable.

## Runtime ownership and persistence

| Resource | Owner and location |
| --- | --- |
| Business state, native operation/call receipts, Knowledge and self-improve records | Existing Data migrations and **`data/runtime/growth.db`**. All adapters receive the same canonical Data home/store. Keep short SQLite transactions; provider calls stay outside them. |
| Seller media and imported original assets | Data's existing asset registry and **`data/runtime/objects/`**. Local media-service URLs are transport, not durable listing URLs. |
| Media job queue and intermediate/output bytes | **`experiment/data/local/`** for the new local profile: `jobs.sqlite3`, `assets/`, `jobs/`, `objects/`, `worker.lock`. This is a provider work queue, not another business authority. A fresh subdirectory avoids misinterpreting existing MinIO-backed rows as local objects. |
| Native worker uniqueness | OS file lock held throughout the root lifespan, proposed **`data/runtime/native-worker.lock`**. Reject a second root instance against the same Data home even if it uses another port. Per-job Data leases remain authoritative after crashes. |
| Media worker uniqueness | Existing `fcntl.flock` on `<DATA_DIR>/worker.lock`, held until the worker finishes or its process exits. Keep one uvicorn worker and no reload. |
| Launcher metadata and private logs | **`data/runtime/local-stack/`**, already covered by `data/.gitignore`: lock, process manifest, `app.log`, `media.log`. `umask 077`; directory 0700 and files 0600. Do not include secret values, tokens or signed media queries in status/report output. |
| Credentials | Existing root `.env` and `experiment/.env`, currently mode 0600. Only server settings/client code reads them. Do not `source`, `cat`, print settings descriptions or place secrets in process arguments. |

Stop/start preserves both runtime directories, the Data cursor secret, imported assets, native receipts, media jobs and object bytes. Do not run `data/setup.sh --reset`, regenerate seed assets as a substitute for import, delete stale jobs or recreate provider keys during routine startup. Back up the Data DB with its existing `backup-db` command/SQLite backup API before schema upgrades. For a complete restorable snapshot, stop both applications and copy their corresponding object/input directories as well; a DB file alone is insufficient. Preserve old snapshots rather than overwriting them.

Use a new local media home unless an existing home's storage/backend consistency is explicitly verified. Never transplant an old `jobs.sqlite3` by itself: its assets contain absolute paths, and completed job object keys may refer to a different MinIO bucket. Do not automatically resume paid work after restart. Existing media recovery marks running jobs interrupted; the media/native owners must preserve unknown provider outcomes and durable IDs as specified in their reviews.

## Exact implementation files and sequence

1. **Composition, owned with API/native lanes:** `app/main.py`, `data/growth_data/api.py` only where a lifespan/worker injection seam is necessary, `app/runtime/data_worker.py`, and the existing root health/API integration test. Reuse the actual Data app. Register readiness and authenticated asset/API routes before `StaticFiles(..., html=True)` at `/`. Unknown `/api/...` must return a JSON 404 rather than static HTML. Root `/` must serve React; media's lab remains on 8010 only.
2. **Local media correctness:** `experiment/video_api/main.py`, `storage.py`, `image_pipeline.py`, `experiment/scripts/start_api.sh`, and existing focused media tests. Factory startup, local storage readiness, truthful local labels, and the capability fields coordinated with `MEDIA_REVIEW.md`. Do not add a new provider pipeline.
3. **One lifecycle script:** new **`scripts/local.py`**, standard library only, with `start`, `stop`, `status` and `smoke` subcommands. One implementation avoids three shell scripts drifting apart. It delegates business execution to the application worker; it is not a task scheduler. Add small process/lifecycle tests in **`tests/integration/hosting/test_local_stack.py`**.
4. **Runbook:** add **`docs/LOCAL_RUN.md`**, update the local launch examples in `README.md` and `docs/ARCHITECTURE.md`, and add a local-file profile section to `experiment/CODEX_DEPLOY.md`. Document dependencies, URLs, stop/restart, logs, sleep/reboot behavior and explicit readiness labels. Coordinate safe example configuration with the API/media owners; never write credentials into docs.

No new lockfile/package manager/environment is needed merely to host. Root imports Data via `PYTHONPATH=<repo>/data`; root and Data dependencies must remain compatible. If an integrated import needs a dependency absent from root `requirements.txt`, pin the successfully tested version there instead of depending on an accidental environment installation. Data's PDF dependencies remain with the export path unless runtime imports actually need them. Do not install the motion/GPU requirements.

### Lifecycle script contract

`start` resolves paths relative to its own file, acquires an exclusive launcher lock, validates the two interpreters and built `frontend/js/app.js`, and checks 8000/8010. It must distinguish its recorded healthy process from an unrelated listener. If a foreign process occupies a port, report the port and owner PID and stop; do not kill it or silently pick another port.

Spawn with explicit argument arrays, canonical working directories, private log files, `stdin=DEVNULL` and `start_new_session=True`. Record PID, process start identity, process group/session, expected executable/arguments, canonical repo/runtime paths, ports and nonsecret profile in an atomically replaced manifest. Never log the environment. A PID alone is insufficient because macOS may reuse it. Use `ps`/process identity checks before signaling; the launcher's fixed arguments contain no tokens. Hold a short launcher lock for concurrent start/stop calls; the applications themselves own long-lived runtime locks.

Start media, wait with a bounded deadline for authenticated storage readiness, then start the root app and wait for root readiness plus the HTML/bundle routes. No new provider-generation request belongs in the health check. **Media startup immediately claims existing queued jobs**, so inspect pending counts read-only before launching an existing media home; an empty fresh home or explicit fake-worker test configuration is necessary for no-paid startup verification. Do not silently process old real-provider queued work as a readiness check. If a stage fails, stop only the children created by this invocation; preserve services that were already healthy. Return nonzero and a safe log path. Repeated `start` should report the same owned healthy processes without creating another worker. A partial stack is repaired only for services whose ports/runtime locks are available.

`status` is read-only: inspect manifest/process identities and GET liveness/readiness with short timeouts. Do not construct `DataService`, run migrations, call `/api/state` (which bootstraps a session), reset a run or submit a job. Authenticate media readiness inside Python by reading the existing settings; report only booleans/backend/capabilities. Do not expose the token through curl arguments. Distinguish **STOPPED**, **RUNNING_NOT_READY**, **READY**, foreign listener and stale manifest; additionally report `MEDIA_INPUT_MISSING`/unsupported capability as a separate generation blocker.

`stop` validates identity, sends SIGTERM to the owned root process group first, waits a bounded grace period, then stops the owned media process group. This stops new native claims before media shutdown. Wait for process exit before releasing/removing its manifest entry. Keep runtime/data intact. If work cannot drain in the deadline, report the still-running PID and active/unknown work; do not silently SIGKILL or label it stopped. No broad `pkill`, process-name kill, `kill $(lsof ...)`, automatic port takeover or deletion of a live lock file. Unexpected parent exit and daemon media threads make durable unknown-outcome handling necessary, even with graceful-stop attempts.

The root lifespan cancels polling/heartbeats and joins its worker on shutdown while preserving receipts. No uvicorn `--reload`, multiple workers or independent second native-worker command in the managed profile. The two detached processes survive closure of the command terminal, but not logout/reboot. Mac sleep pauses service availability. Do not change power settings, install LaunchAgents or add a keep-awake process without a separate need.

## Commands and nonsecret configuration

The existing environments are ready; rebuilding them is not required for this handoff. Known tools on this Mac:

```sh
cd /Users/butterflyro/Documents/Work/personal/hack/Team_12_TD-
./.venv/bin/python --version
./experiment/.venv/bin/python --version
/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node --version
```

Build/check React with the available bundled Node instead of assuming a global npm:

```sh
PATH="/Applications/ChatGPT.app/Contents/Resources/cua_node/bin:$PATH" \
  /Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node \
  /Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/corepack/dist/npm.js \
  --prefix frontend run build
```

`scripts/local.py` supplies these child environments as overrides, without rewriting either secret file:

| Child | Required local profile |
| --- | --- |
| Root | `PYTHONPATH=<absolute repo>/data`; `GROWTH_DATA_HOME=<absolute repo>/data/runtime`; `GROWTH_CONTENT_MODE=worker`; `GROWTH_LEARNING_MODE=external`; `MOCK_API=0`; `LLM_MODE=offline`, `MEDIA_MODE=offline` for the no-paid smoke. Runtime creation must explicitly use `execution_profile=external` rather than silently defaulting to Data's reference profile. API/worker lane owns that binding. |
| Media | `STORAGE_BACKEND=local`; `DATA_DIR=<absolute repo>/experiment/data/local`; `PUBLIC_BASE_URL=http://127.0.0.1:8010`; `LOCAL_MOTION_ENABLED=false`. Existing token, playback secret and provider configuration load server-side. The storage choice itself does **not** disable paid generation. |
| Bridge, after media settings exist | Local media base URL `http://127.0.0.1:8010` and the matching service token from protected server configuration. Never propagate root `DATA_DIR`/provider variables indiscriminately to the other child. No MinIO public URL is required. |

Under the final bridge contract use one canonical media base-URL/token field pair, owned by the media/API lane, rather than introduce a second hosting-only credential schema. Preserve configured live model names. `start`/`status` must not create provider jobs to prove readiness; normal workers may resume already queued authorized work, which must be reported separately. For this no-paid acceptance use explicit fake/fixture injection or offline execution with no real queued media work. Do not infer safety from `STORAGE_BACKEND=local` while using real keys, or try to disable keys with empty environment values: media settings ignore empty overrides and can reload the real `.env` value.

**After implementation**, the launcher executes these exact server commands with the environments above:

```sh
# cwd: repository root
./.venv/bin/python -m uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-access-log

# cwd: experiment
./.venv/bin/python -m uvicorn video_api.main:create_app --factory \
  --host 127.0.0.1 --port 8010 --workers 1 --no-access-log
```

Disabling HTTP access logs avoids persisting signed media capability queries in ordinary request logs. Keep sanitized application/error logs. Forwarded-proxy settings are unnecessary for this loopback profile.

The final user-facing runbook commands are:

```sh
./.venv/bin/python scripts/local.py start
./.venv/bin/python scripts/local.py status
./.venv/bin/python scripts/local.py smoke
./.venv/bin/python scripts/local.py stop
```

Document the actual mode in start/status output. The seller entry URL is **`http://127.0.0.1:8000/?preview=0`**, because this frontend persists preview selection in session storage. Use the same host spelling consistently for cookie/origin checks. Do not automatically open a browser or activate a visible app while the user is using their screen. Ports 8001, 9000 and 9001 remain unused by this topology.

## Existing remote asset import and provenance

The user authorized copying existing product assets from the supplied remote media API/MinIO, not generating replacements to work around remote availability. The root agent owns credentials and retrieval. This review made no remote requests and did not inspect credentials. The root reported transient remote 502/530 responses; that is an import blocker, not evidence the objects do not exist.

1. Use authenticated GET/list/stat and existing signed download endpoints, or read-only object operations against the supplied **MinIO API endpoint**. The console URL is not automatically an S3 endpoint. Never POST a new image/video job, recreate a bucket, change ACLs, remove objects or modify remote jobs to copy assets.
2. Download to an ignored temporary path under `data/runtime/imports/`, validate format/decodability, bound size, compute SHA-256 and byte length, then atomically name the copy by content hash. Keep original bytes; transformations for service upload receive a separate hash/provenance entry.
3. Save a sanitized manifest beside the copies: source host and path without signed query, remote job/asset ID or bucket/object key, retrieval UTC, SHA-256, byte length, MIME, dimensions/duration, original input versus generated output, and product identity verification status. Never copy auth headers, API responses with signed URLs, raw tokens or entire remote databases into the report/repo.
4. Distinguish a desktop-fan generated sample from the actual handheld D input. A downloaded asset is not automatically a verified product photo. Existing geometric placeholders and generated advertising results cannot silently become evidence of D's physical SKU. If no matching original exists, report that specific missing input and keep paid generation gated.
5. Register validated local bytes through Data upload/complete and bind the resulting asset to the intended product/run. The media bridge uploads that input to the **local** media service and stores its local asset ID. Remote asset IDs and signed URLs do not identify local queue assets. Preserve source provenance and hashes through this mapping.

Remote failure must not prevent starting the local seller UI or running offline tests. Report `LOCAL_HOSTING` and `PRODUCT_INPUT` independently; do not claim media live acceptance using a placeholder or a desktop-fan sample.

## Acceptance and verification

The hosting implementation needs a small focused lifecycle suite plus existing module suites; do not repeat paid provider tests as a host check.

| Gate | Required evidence |
| --- | --- |
| Import safety | Import root/media factory/helper modules in a subprocess with a temporary home and assert no DB/files/thread/network side effects. Calling factories with explicit fixture settings touches only that fixture home. |
| Start/ownership | Start from another working directory; two intended PIDs/listeners only. Repeated start preserves IDs. Foreign port listener and second runtime worker are rejected without being stopped. Simulated partial-start failure cleans up only newly created children. Stale/reused PID is never signaled. |
| Ready/application routing | Root `/health`, `/ready`, `/`, `/js/app.js` return the expected status/MIME; API routes return JSON; missing API routes do not fall through to HTML. Native worker is active with external execution, worker content and external learning. Media `/health` reports `storage=local`; authenticated `/v1/readiness` succeeds after a real local probe. No credential values appear in responses. |
| Local media | Existing fake-provider image/video tests use real valid JPEG/MP4 bytes, verify local object hashes/size, authenticated job access, signed GET/HEAD/Range 206 and signature rejection. Local output metadata never claims MinIO storage. No paid provider calls. |
| Offline integrated smoke | Run against temporary Data/media homes, not the seller's current run: native operation, durable state/events, approved fixture content, explicit Apply and a Learning handoff complete through the real adapters. Capture the same business IDs; no reference harness substitution. An offline provider spy asserts zero network generation. |
| Restart persistence | Save state/receipts/assets, stop and start, then reopen the same seller session/run. DB, Knowledge, receipts, object bytes, budgets and pending/unknown provider bindings remain. Do not create a new run merely to make readiness pass. |
| Stop | Root worker stops claiming first; owned processes exit within grace on idle fixture runs; listeners close; directories/DB/assets remain. Repeated stop is harmless. A slow active provider case is reported truthfully and never reissued on next start. |
| Data integrity | On the authoritative DB after a clean migration/start, SQLite `integrity_check` returns `ok` and `foreign_key_check` is empty. Backup exists before an upgrade. These checks do not establish media or native workflow correctness by themselves. |

Existing regression commands, from the repo root:

```sh
./.venv/bin/python -m pytest -q
PYTHONPATH=data ./.venv/bin/python -m pytest -c data/pyproject.toml data/tests -q
PYTHONPATH=experiment ./experiment/.venv/bin/python -m pytest experiment/tests -q
PATH="/Applications/ChatGPT.app/Contents/Resources/cua_node/bin:$PATH" \
  /Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node \
  /Applications/ChatGPT.app/Contents/Resources/cua_node/lib/node_modules/corepack/dist/npm.js \
  --prefix frontend test
```

Make media import-safe before relying on its tests to leave the configured runtime untouched. Keep tests explicit about temporary settings and fake providers. Fix the known Data unordered job-selection test failure in its owning lane; do not weaken the terminal-job guard to make the host gate green.

### Checks performed in this review

- Read the relevant factory/lifespan, storage, configuration, seed, frontend source selection, setup/deployment and integration-review files. No source code or credential files were edited or read for values; only this report was written.
- Root interpreter reports **Python 3.11.18**; installed module presence was verified for FastAPI, uvicorn, Pydantic, httpx, LangGraph, langchain-openai, ReportLab and pytest. Bundled Node reports **v24.22.1**. The coordinator reports the separate Python 3.12 media environment is installed.
- Ran a real **LocalStorage put/stat/partial-read check: PASS**, using a temporary directory and ten fixture bytes. Imported `video_api.storage` only; no media app/settings load, persistent DB mutation or provider call.
- `lsof` found **no listeners on 8000, 8001, 8010, 9000 or 9001** at inspection. This is a point-in-time check; startup must check again.
- Filesystem metadata confirms both secret files are **0600**. The existing `experiment/data/jobs.sqlite3` is present; **`data/runtime/` does not yet exist** in the inspected checkout. Its absence is not permission to replace or reset a DB created by another implementation step later.
- Coordinator-supplied baseline, not rerun by this reviewer: core **83 passed + 15 subtests**; Data **54 passed, 1 failure**; media **25 passed**; frontend **44 passed**. Earlier review text saying the media environment is absent is stale.

**Verdict:** the installed stack and supported file storage are sufficient for local hosting. Implement composition, import safety, worker ownership and lifecycle checks above, then report `LOCAL_HOSTING: PASS` only after actual readiness/restart evidence. Native workflow, self-improve and media-live acceptance retain their separate gates; configured keys, existing source reports and HTTP 200 health responses do not prove them.

Not checked: live generation, model quality, remote asset availability, visible-browser playback or public deployment. No MinIO/tunnel installation, paid request, screen takeover, source edit or commit was performed.
