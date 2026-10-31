# Plan triển khai giao Terra 6.1 max

Baseline `33fbdd5`; cả chín phần đã có báo cáo Astra riêng trong thư mục này. Implementation đi theo thứ tự dưới đây, trên `main`, giữ mọi thay đổi của người dùng/member. Không reset DB hoặc branch để vượt lỗi. Không gọi paid API trong tests.

## 1. Ba lane code, chín phần nghiệm thu

Ba Terra có thể chạy song song vì source không trùng ownership. Mỗi báo cáo Astra vẫn có verdict riêng sau code. Không chia một file cho hai writer. Nếu cần sửa file lane khác, gửi chữ ký/diff yêu cầu cho owner, không tự ghi.

| Terra | File được sở hữu | Phần chịu trách nhiệm |
| --- | --- | --- |
| `terra_data_integration` | `data/growth_data/**`, Data tests; `app/main.py`, `app/api/**`, `app/runtime/**`, `app/negotiation/**`, `app/agents/tools.py`, `app/agents/runner.py`; `app/infrastructure/data_*.py`; domain `packages.py`, `intent.py`, `tools.py`; integrated tests tương ứng | DB/business migration, agent worker, tools, HTTP; Data side của Knowledge/media |
| `terra_self_improve` | `app/memory/**`, `app/domain/models/skills.py`, `learning.py`; `app/infrastructure/store.py`, `sqlite_store.py`, `llm.py`; `app/skills/**`, `app/simulation/market.py`, `runner.py`, replay modules; `scripts/run_sim.py`; SI/Knowledge/repository tests và fixtures | SI01–SI07, five-bin gateway, SQLite repository, durable budget, replay/proof |
| `terra_media_ui_host` | `experiment/**` trừ secrets/ignored runtime; `app/content/**`, `app/infrastructure/media_gateway.py`, `app/agents/content.py`, domain `content.py`; `app/core/settings.py`; `frontend/**`; `scripts/local_stack.py` và media smoke/integration tests | Media pipeline/client/worker, React, local lifecycle |

Root giữ docs tổng hợp, config local, việc nhập dữ liệu từ nguồn đồng nghiệp và kiểm/commit cuối. Schema migration chỉ có **Data owner** viết. Repository chỉ có **SI owner** viết, tên chốt `app/infrastructure/sqlite_store.py`; không tạo thêm `knowledge_sqlite.py` có cùng chức năng.

## 2. Hợp đồng giữa các lane phải bàn giao sớm

### Data ↔ SI / Knowledge

- Một `run_id` do Data tạo, một event `seq`; gateway không tự tạo Session/seed/log riêng. Context là snapshot/cache và chỉ đọc; mutation qua Data command.
- `SqliteKnowledgeStore` nhận Data `Store` hoặc path của cùng database. Các method public theo [PUBLICATION_CONTRACT](../self-improve/PUBLICATION_CONTRACT.md); thêm helper nội bộ nhận `sqlite3.Connection` cho publication/confirmation atomic, không mở nested write transaction.
- Data owner tạo tám bảng theo [DB review mục 4](DB_REVIEW.md), giữ đủ JSON payload/unique constraints. SI owner gửi tên cột/transaction helper cần dùng trước khi viết repository. Không sửa migration 001/002; upgrade giữ dữ liệu và FK.
- Data owner cung cấp `DataKnowledgeSource` qua infrastructure adapter: Rules/version theo shop; frozen public evidence đúng settlement cursor; references có source/version/hash. `MemoryGateway(..., source=None)` giữ compatibility với core tests; integrated path luôn inject source.
- SI owner cung cấp `prepare_platform_context(...)`, bundle/seed và publication entrypoint; Data/graph owner gọi trước attempt và pin cùng negotiation. Không để SI writer sửa `graph.py` đồng thời.
- Integrated night có một entrypoint. Snapshot/claim/LLM nằm ngoài transaction publication; commit Knowledge + versions + receipt + Data handoff/event/advance nằm trong cùng short transaction. Skip và publish phải tranh quyền trên cùng DB lock/version.
- LLM client nhận store/run ID, call ID ổn định và source binding. Reserve trước network; cùng ID không cấp quyền send lại. Crash thiếu outcome → unknown, giữ slot; không tự replay graph có phí. Có response/receipt thì reuse.
- Rules confirmation cập nhật Data Rules và durable preference cùng transaction qua callback; chỉ hạ voucher cap. Không chạy `gateway.answer_pref` rồi gọi Data lần hai.

### Data ↔ Media

- `ContentService` là worker xử lý **Data content job đã approved**, không phải business owner. Constructor/method có dependency injection; Data worker gọi một entrypoint `process_job(run_id, job_id)` và `close()` khi shutdown. Media owner chốt chữ ký với Data owner trước khi implement; không gọi core `submit_decision/apply_reviewed_content` trong integrated path.
- Data owner thêm `provider_state_json` và helper claim/heartbeat/reserve/update slot. Binding gồm run/shop/card/proposal/brief/content/job/attempt/slot, request hash/key, remote ID, known/unknown và result asset. Reserve trong transaction, network ở ngoài.
- Run cap: 9 image submissions, 3 video submissions; media text/vision riêng tối đa 3/video. Replay cùng reservation không tăng count; chưa rõ outcome không được tạo key mới. Một remote worker hiện có đủ.
- Media owner dùng native Content Agent với Data-approved context do adapter cấp; facts là public verified facts, confirmed style lấy từ Knowledge/Rules. A xong → submit video từ A cùng attempt → B/C. Retry nền sáng dùng `retry_scope=all`, không phá semantics images-only của caller cũ.
- Import bytes vào **Data asset subsystem**, giữ SHA/MIME/size và source. Link signed/MinIO không thành listing URL bền vững. Giới hạn video theo Data 50 MB, không dùng con số 150 MB từ plan cũ.
- Data publish transaction kiểm current draft identity, selected cover bytes và included video bytes; pass review hoặc ack, hoặc skip video. Ack không vượt file/ownership/version. Skip lưu video null; late worker không sửa listing đã publish.
- Live mode thiếu ảnh gốc/config thì báo unavailable trước request có phí. Offline dùng asset có nhãn fixture/cache thật; không gọi placeholder là ảnh sản phẩm đã được OpenAI tạo.

### Data API ↔ React / host

- Reuse `growth_data.api.create_app` với dependency/lifespan hooks cần thiết, mount React/static cuối. Không implement thêm một tập `/api` cạnh tranh với Data facade. Cài/import package nhất quán giữa app và tests.
- Giữ 9 seller APIs và bổ sung brief confirmation/fields/version đã chốt ở API/UI review. Nút chạy ngày phải gửi brief thật được seller xác nhận, không gán `confirmed=True` trong worker.
- Trả operation status/busy/phase/horizon, exact card/content identity và source; UI poll state/operation, không biến 202 thành completed. UI không fallback sang preview khi API lỗi.
- Host script chạy root8000 + media8010, bind loopback, không reload. PID/log/runtime dưới ignored directory; chỉ stop process do script tạo sau khi kiểm identity, không kill process khác trên cổng.
- Media local config dùng `STORAGE_BACKEND=local`, `PUBLIC_BASE_URL=http://127.0.0.1:8010`; input asset local có manifest nguồn/checksum nếu nhập từ MinIO đồng nghiệp. Không ghi credentials vào JS/docs/log.

## 3. Thứ tự triển khai và đầu ra mỗi phần

### P01 — DB và business transaction

Owner Data. Đọc DB_REVIEW, đặc biệt findings 1–8 và DB01–DB07.

1. Sửa lỗi đã tái hiện: query job có thứ tự/selection exact attempt; close day chặn operation/negotiation chưa terminal; selected asset thiếu/hỏng không publish; voucher question không nâng cap; document type đúng metadata.
2. Thêm migration mới cho eight SI logical records, native invocation/attempt receipt tối thiểu, content bindings, daily prediction và run horizon 1..7/demo_shop. Upgrade bảng runs có dữ liệu bằng transaction/FK check; không edit SQL cũ hoặc reset file.
3. Finalize negotiation chỉ sau Referee + final validator; external accepted turn chưa phải agreed terminal. Finalize thất bại hợp lệ ngay cả khi chưa có proposal. Reference fixture path phải có nhãn và giữ tests tương thích.
4. Bổ sung immutable event linkage trong transaction nguồn: negotiation/card/decision/applied/pause/prediction/outcome. Build public projection ở infrastructure; không pass raw learning-input private xuống model.
5. Lưu daily prediction sau effective monitor/state và trước actual; settlement retry reuse snapshot. Engine fingerprint lấy từ version pin của run.
6. Nối Knowledge callbacks và media helper contract, rồi test atomic rollback/reopen. `integrity_check=ok`, `foreign_key_check` rỗng.

Done: full Data suite pass; regression reproduce cũ đã bị chặn; v2 upgrade không mất rows/IDs; one DB authority được chứng minh từ HTTP đến worker.

### P02 — Agent điều phối

Owner Data. Đọc AGENTS_REVIEW O1–O6.

1. Tạo Data execution context từ run có sẵn; cung cấp current public/private/fees/brief, scoped tools, Knowledge, event sink. Không dùng writable Session làm mirror.
2. Graph nhận Data negotiation ID, turn/review sinks và pinned context; map counter→propose, Referee turn refs→event seq thật. Giữ vòng role hợp lệ, cap 3 Platform rounds, accept exact package.
3. Worker claim operation/version, prioritize demo shop, giữ lease ngoài blocking provider call; persist/finalize/present qua stable command keys. Failed/no-fit đóng attempt thật, không bịa transcript.
4. Seller action/Data owns state. Other shops dùng simulated seller có nhãn; Content/night đi qua worker tương ứng. Hết cap chạy fallback có source offline.
5. Restart: completed output/command reuse; unknown provider call không resend. Không cần một generic graph checkpoint engine: cho phép fail an toàn hoặc deterministic fallback có nhãn, giữ provenance và không lặp tác động.

Done: integrated fake transport chứng minh cả năm role dùng native tool protocol với Data IDs; D seller→content→apply→night→next-use đi qua SQLite; không gọi business lifecycle RAM trong đường sản phẩm.

### P03 — Native tools

Owner Data. Đọc TOOLS_REVIEW T-INTEGRATE-1–4.

1. `DataToolScope` bind server-side run/shop/day/principals; T01/T02 đọc snapshot hiện hành, T06 dùng read-only `forecast_values` rồi project đúng 5 field.
2. T04/T05 giữ correction/brief checks của core, lấy phí/cost/rules từ cùng Data snapshot và kiểm lại candidate. Không tạo proposal hoặc forecast row trong tool read.
3. Giữ runner/allowlist; Package.stop_after_days max14; privacy guard dùng cùng current snapshot với tools. Static references theo Knowledge review, không mở tool mutation/provider cho LLM.

Done: money parity D3%=27136/stop6.5, public/private ACL, repair5000, no-write forecast và actual ToolMessage→decision tests pass.

### P04 — Knowledge

Owner SI cho gateway/repository, Data cho source/callback/document metadata. Đọc KNOWLEDGE_REVIEW K01–K06.

1. Gateway injected Rules/evidence/reference source; per-shop rules_version, same event cursor, public frozen evidence only.
2. Atomic confirmation callback: candidate→question→card asked→Yes/No; Yes update Rules+preference, No silence14days. Candidate chưa confirmed không ảnh hưởng Content mặc định.
3. Static public references version/hash/type đúng; references là dữ liệu, không instructions hay verified facts mới. Giữ campaign catalog riêng.
4. Retrieval trace ghi record/version/calibration/Rules IDs an toàn; top5/history và top5 mỗi lesson scope; durable reopen next-use.

Done: integrated native fixture đọc record đã reopen và đổi input/output; MemoryOFF sạch nhưng Rules vẫn enforce; không lộ private values vào Learning/Platform/Content.

### P05 — Self-improve

Owner SI. Thực hiện [SI01–SI07](../self-improve/README.md) theo thứ tự, với DB local bắt buộc. [SELF_IMPROVE_REVIEW](SELF_IMPROVE_REVIEW.md) thay phần trì hoãn DB; DTO/schema semantics giữ nguyên.

1. SI01 models ở app, parity schema/examples; không import code trong docs.
2. SI02 canonical compiler/hash/apply, 4 base skills/5 allowed action-target pairs, source numeric values only.
3. SI03 facts join immutable normalized Data events; accepted chưa applied không là evidence; cutoff/scope/privacy.
4. SI04 pure stage, RAM semantics, SQLite same contract; full receipt/hash conflict, append-only versions, atomic writes.
5. SI05 snapshot→claim→reserve→one native Learning invocation→terminal output→stage/eval→atomic publication. Unknown không resend; no rules mutation; same output reused after failed commit.
6. SI06 pin policy/seed attempt, effective day d+1, read_memory actual ToolMessage, same seed native/fallback; final validators/seller gate vẫn giữ.
7. SI07 replay binding + real Data simulator reports cho D/E, horizon1..7, ON/OFF same seed/config and scoped totals; không fake uplift hoặc yêu cầu ON thắng. Daily prediction đúng effective state trước actual.

Done: acceptance T01–T24 map vào test names thực; repository RAM/SQLite contract + reopen/concurrency/unknown pass; D/E 7-day report có source/hash/version/budget; provider_eval ghi riêng nếu chưa chạy live.

### P06 — Media

Owner Media cho pipeline/client/worker; Data owner cho storage/result/publish helpers. Đọc MEDIA_REVIEW M1–M5 và MI01–MI02 detail. MI03 Session mutations trong plan cũ được thay bằng Data worker ở đây.

1. Optional logo + product kind handheld/desktop + bright backgrounds xuyên Images/vision/plan/Muse/review. D explicitly handheld; không đổi seed thành desktop.
2. Capability growth-media.v1; terminal checksum/MIME/size/actual duration/source/review/outcome_unknown. Keep existing service idempotency; SDK retries0.
3. Typed HTTP client same-origin signed download, no redirects/Bearer on playback; upload once per hash/owner, frozen request IDs. Renew signature bằng GET job, không regenerate.
4. Native Content job worker, A→video→B/C, heartbeat, durable per-run cap/bindings, stale result denied. Import checked bytes qua Data; partial failures truthful.
5. Seller gate + feedback→night preference→confirmed bright style ở invocation sau. Missing input fails before paid reservation/send where possible.

Done: experiment suite + real bridge with fake provider HTTP pass; unknown/retry/caps/late callback/filecheck/videoack/skip atomic tests; live generation/playback chỉ báo khi thật chạy.

### P07 — HTTP API

Owner Data. Đọc API_REVIEW mục 3; chốt payload một lần với UI owner trước khi sửa.

1. Assemble existing Data app; dependency injection/nativeworker startup/shutdown, health diagnostic không lộ secrets.
2. Add/pin brief và expected versions/identities cho decisions/retry/apply/night. Preserve idempotency payload hashing; normalize omission/default trước hash nếu contract cho phép.
3. State/event/operation projection có current exact identity, coherent content progress, native source and safe telemetry; no global Session.
4. Proof thực từ reports/Data comparison; không phát fixture preview như source runtime. Errors tiếng Việt và status code stable.

Done: test HTTP cookie reset→brief→day→decision→content→apply→night→reopen/state, errors and duplicateeffects; React requests match schema exactly.

### P08 — React

Owner Media/UI. Đọc UI_REVIEW; giữ layout/components và change tối thiểu.

1. Brief confirmation có action thật trước start; body uses exact current run/card/brief/draft identity từ API.
2. Use busy/active_operation/day/phase/horizon để disable/poll đúng, 202 không thành xong; network error giữ state và unknown command key.
3. Retry bright sends all; cover selection, video review notes/ack/skip UI, unavailable bytes cannot be approved; cap3 and current job identity.
4. Night/preference/proof reflect actual source; no fictional activity/transcripts/fixture fallback when API fails.

Done: component/request tests + hidden/browser or HTTP integration path; no secrets in bundle; day7 complete no day8; old current test coverage preserved where semantics unchanged.

### P09 — Local hosting

Owner Media/host, root launches after checks. Đọc HOST_REVIEW; không công khai tunnel.

1. Existing Python3.11 root + Python3.12 experiment environments; root Data dependencies installed consistently. Frontend build with bundled Node or operator-provided Node.
2. `scripts/local_stack.py start|status|stop`: loopback8000/8010, owned PID/logs in ignored runtime, health/readiness, collision check, clean shutdown, no reload.
3. LocalStorage active for media, write/read/delete probe rõ ràng; business/media DB riêng theo trách nhiệm hiện có. API/static/Range checks thực. Config secrets mode0600, no browser token.
4. Import actual remote product bytes only after authenticated source access works; store manifest/checksum and local input path. Không sửa/xóa object đồng nghiệp.

Done: start/status pass after restart, UI+API sameorigin, Data persists, media health authenticates, range playback from real stored testfile; stop chỉ dừng owned processes. Readiness config không được báo thành live generation PASS.

## 4. Chạy song song và kiểm cuối

- Ngay đầu: ba coder thống nhất names/signatures giữa lane, Data owner ghi migration schema, SI owner gửi repository helper API, Media owner gửi worker/helper contract. Không chờ hết một lane mới code phần độc lập.
- Checkpoint 1: DB regressions + schema, SI pure models/compiler, media handheld capability có focused tests.
- Checkpoint 2: Data context/tools/native graph, SI durable night, media worker/React version contract nối được với fakes.
- Checkpoint 3: one local app flow dùng shared SQLite, D/E offline proof/reopen, tests tổng hợp và build.
- Astra review lại đúng phần của mình trên patch hoàn tất. Reviewer không sửa source; blocker chuyển về Terra owner. Không gọi full suite lặp khi patch không đổi.
- Root commit từng cụm coherent sau checks, giữ main và normal push (nếu remote mới thì merge thường; không force/reset). Ghi CODEX_LOG và IMPLEMENTATION_STATUS với lệnh/kết quả/limits thực.

## 5. Prompt chung giao mỗi Terra

```text
Implement lane được giao theo docs/plans/toan/full-integration/README.md và IMPLEMENTATION_PLAN.md.
Đọc AGENTS.md và chỉ các review/task liên quan lane. Source hiện tại quan trọng hơn mô tả cũ.
Làm trên main, giữ user/concurrent changes; no reset/force/overwrite. Không sửa file owner khác.
Trao đổi chữ ký/contract ngay từ đầu; mọi dependency source đã có thì tích hợp thật, không dừng ở stub/fake.
Giữ Data authority, native tools, privacy/money/approval, typed Knowledge/SI và source labels.
Không gọi API có phí trong tests; không in/env/commit secrets; không thao tác màn hình chính.
Không tự thêm distributed framework/edge-case spam. Complete happy flow và concrete safety invariants.
Chạy focused tests, report exact commands/results/files and dependency contracts to root.
Không commit; root integrator review/stage/commit sau khi ghép đủ lanes.
```
