# DB review và kế hoạch persistence local

Review: Astra Max, 31/10/2026. Source: `main` tại `33fbdd5`, gồm Data `9621b14`, frontend `bd78f8e`, media `a0a93f0`. Đây là báo cáo review và kế hoạch triển khai; không phải kết quả DB/self-improve đã được nối. Chỉ file này được ghi trong lượt review. Giữ nguyên các tài liệu/schema self-improve chưa commit của người dùng.

What this change does: Data đã có một business backend SQLite thực, có transaction, migration, seller facade, event log và worker handoff. Core agent và self-improve chưa dùng backend đó; hiện vẫn có một Session RAM và log JSONL riêng. Kế hoạch dưới đây đưa business state về một nguồn Data và thêm repository Knowledge bền vững vào cùng database.

## 1. Quyết định cần giữ xuyên suốt implementation

1. **Một SQLite authority:** dùng `data/runtime/growth.db` theo default hiện có; hỗ trợ `GROWTH_DATA_HOME` cho đường dẫn tuyệt đối khác. Data sở hữu runs, shops, rules, negotiations, cards, decisions, campaigns, stock, listing, content jobs/assets, settlements, business events. Knowledge sở hữu history/preferences/calibration/lessons dẫn xuất, skill versions, night snapshot/reflection/commit và LLM reservation ledger trong cùng file DB. Không tạo `runs/<run>/business.db` writable hoặc mirror campaign/stock/decision vào một DB thứ hai.
2. **Session chỉ là context/cache khi chạy tích hợp.** Mọi ID/version/business mutation lấy từ Data command. Có thể giữ RAM adapter cho unit tests/headless độc lập, nhưng integrated run không được gọi một lượt core settlement rồi một lượt Data settlement.
3. **SQLite chuẩn đủ cho Mac này.** Tái sử dụng `sqlite3`, WAL, connection ngắn, `BEGIN IMMEDIATE`, FK và idempotency hiện có. Không thêm Postgres, Docker, ORM, Redis hoặc queue server chỉ để nối demo một máy. Cấu hình serving/process supervision thuộc reviewer hosting.
4. **Không giữ write transaction qua LLM, HTTP media, polling hoặc await.** Claim/reserve trước mạng; persist outcome sau mạng; retry dựa trên receipt. Cùng file DB không đồng nghĩa có thể giữ connection từ request này qua request khác.
5. **Yêu cầu DB hiện hành đã mở rộng.** Các câu “DB do member khác”, “không tự tạo DB/migration”, “durable NOT_CONNECTED khi chưa có factory” trong gói SI là phân công cũ. Yêu cầu mới của người dùng cho phép triển khai DB local và adapter. Giữ schema/semantics `self-improve.v1`, nhưng cập nhật các câu ownership cũ trong lượt integration; không dùng chúng để dừng ở RAM.
6. **Không nhận fixture thành proof agent.** HTTP harness hiện có chứng minh transport/transaction; native agent + SI + persistent store phải chạy riêng mới được báo durable/integrated PASS.

Đường dẫn local chốt cho dữ liệu: `data/runtime/growth.db`, `data/runtime/objects/`, `data/runtime/backups/`, `data/runtime/exports/`. Các đường dẫn này đã bị Git ignore qua `data/.gitignore:1–8`; `.db`, WAL/SHM và `runs/` cũng được root ignore. Đừng đọc/in token để chứng minh database hoạt động.

## 2. Blocker cũ đã được giải quyết trong source mới

| Hạng mục | Bằng chứng hiện tại | Kết luận |
| --- | --- | --- |
| DB local + migration atomic | `data/growth_data/storage.py:35–79`; migration `001_initial.sql` và `002_demo_integration.sql`; `test_integration_safety.py:19–41` | Có WAL, FK, version receipt, rollback DDL, reopen và không tự downgrade. Dùng tiếp. |
| Business commands + idempotency | `service.py:128–147`; khóa unique trong migration 001 | Response receipt và business writes/event nằm cùng transaction. Không cần dựng command store mới. |
| Seller state bền vững | `002_demo_integration.sql:7–9`; `facade.py:12–15`; `service.py:149–166` | Có grants/active run; không còn lý do dùng global `SessionManager.current` làm authority HTTP. |
| External orchestrator seam | `integration.py:84–127`; `service.py:539–542` | Có queued operation, claim CAS, lease, result; chưa có native worker thực. |
| Approval trước activation | `facade.py:93–99`; `service.py:448–465`; `media.py:149–158`; `test_integration_safety.py:120–149` | Content refresh chờ publish, rồi listing + campaign apply cùng command. Gạch blocker cũ trong `TEAM_INTEGRATION.md:11`. |
| Night asynchronous/restart | `integration.py:129–181`; `service.py:569–580`; `test_integration_safety.py:68–117,198–214` | Handoff, settlement cursor, result receipt, auto-advance, retry/skip đã có; không cần build lại. |
| Privacy và event cursor | `service.py:171–234`; `api.py:164–168,353–358` | Có role-scoped views và cursor tiến qua event bị lọc. Mapping sang core vẫn thiếu. |
| Calibration injection | `service.py:396–413`; `data/tests/test_calibration.py` | Có callback read-only, memory-OFF không gọi, chỉ dùng prior-day sample đủ điểm. Chưa nối repository SI. |
| Backup không migrate nguồn | `cli.py:37–46`; `data/setup.sh` | SQLite backup API đã có; dùng trước upgrade, không copy nóng mỗi file `growth.db` bỏ quên WAL. |

`data/PROGRESS.md` và một số README còn mô tả bản cũ (ví dụ 32 tests, timeout skipped, sweep 10 giây). Source hiện chuyển timeout learning sang failed và sweep mỗi giây (`service.py:634–638`, `api.py:33–39`). Update tài liệu sau khi chạy kiểm tra mới; không dùng số PASS cũ làm baseline hiện hành.

## 3. Must fix trước integrated run

### 1. Có thể chốt ngày trước khi agent chạy

**What this is:** External `start_day` tạo operation queued. **Problem:** `close_day` chỉ chặn pending card/proposal/content, không chặn queued/running operation hoặc negotiation đang chạy (`service.py:560–569`). Repro thật: reset external → start → night lập tức trả 200, chuyển ngày 2, có 5 settlements trong khi operation start_day vẫn queued. **Fix:** Trong transaction close/settle, yêu cầu operation start/renegotiate của ngày đã terminal hợp lệ và không còn negotiation running; failed/unknown phải được resolve rõ ràng trước khi chốt. **If we skip it:** UI/proof có thể hoàn thành một ngày mà không có cuộc thương lượng hoặc học từ trạng thái chưa hoàn tất.

Test bắt buộc: queued start, running start, running negotiation, failed-unresolved operation đều từ chối close mà không tạo settlement/cursor/handoff; sau finalize thì close đúng một lần. Cùng test qua service command và HTTP facade để không chỉ dựa vào nút disabled phía browser.

### 2. Core Session/log chưa nối authority và không phục hồi được

**What this is:** `Session.new` tự tạo UUID, load seed và MemoryStore (`app/runtime/session.py:74–90`); EventLog append JSONL nhưng reopen không đọc file/cursor (`app/infrastructure/eventlog.py:10–29`). **Problem:** Inject SQL memory đơn thuần vẫn tạo run ID khác Data, dựa vào stock/rules seed và mất evidence sau restart. **Fix:** Thêm factory/loader nhận Data run ID và hydrate context theo Data snapshot; Data cấp negotiation/card/campaign/event IDs. Integrated event adapter đọc Data events; JSONL chỉ giữ khả năng test/export nếu cần. **If we skip it:** Knowledge receipt có thể tồn tại nhưng evidence, active package và seller approval của cùng run không khớp.

Không gọi `Session.new` với seed cũ để “resume” một run đang dở. Reopen seller pending card phải đọc các row đã commit; không cần LangGraph checkpoint để dựng lại card đã persist. Negotiation đang giữa provider call cần failed/unknown rõ ràng và resume có kiểm soát, không tự gửi lại paid request.

### 3. Persist một turn `accept` hiện finalizes trước Referee

**What this is:** Data `create_proposal` chuyển negotiation thành agreed ngay khi stance accept (`service.py:292–296`). Core chạy Referee sau accept và có thể refocus/stop hoặc fail final validators (`app/negotiation/graph.py:55–95`). **Problem:** Adapter persist từng turn sẽ khiến DB agreed trong khi graph kết thúc failed; operation result còn yêu cầu present final proposal (`integration.py:106–109`). **Fix:** External profile giữ transcript accept nhưng chỉ terminal qua một `finalize_negotiation` command có expected version, final proposal, verdict và request hash; command chạy validators và ghi `negotiation_finished`. Reference profile có thể gọi cùng finalize từ driver hiện tại. **If we skip it:** Có thể trình seller một gói Referee đã từ chối hoặc worker bị kẹt CARD_NOT_PRESENTED.

DB thay đổi tối thiểu: negotiation version/CAS và terminal result receipt/hash; pinned context của attempt có thể lưu JSON bất biến trên negotiation. Không lập thêm một mutable negotiation state machine trong Session song song với Data.

### 4. Event payload chưa đủ làm evidence SI có provenance

**What this is:** Core history/evidence join theo negotiation/card/package và actual (`app/memory/gateway.py:143–204`, `app/memory/night.py:33–65`). **Problem:** Data seller decision chỉ có decision_id/action/edited bool (`service.py:384`); applied event thiếu package/card (`465`); market result thiếu campaign/negotiation/prediction (`520–522`); pause thiếu campaign (`497,518,658`); chưa emit negotiation_finished. Copy event JSON trực tiếp vào core sẽ bỏ approved_package, edited voucher hoặc gắn pause sai attempt. **Fix:** Một projection Data có typed joins, cutoff và ACL; bổ sung durable links vào event mới trong chính business transaction, giữ mapping rõ cho row lịch sử. **If we skip it:** Learned policy có thể không có evidence hợp lệ hoặc học nhầm việc “agreed” thành “đã chạy”.

| Nguồn Data | Projection tối thiểu sang core/SI |
| --- | --- |
| Proposal + negotiation + turn event | Data negotiation_id, proposal_id, ordinal/round, actor/action/package, source; Referee evidence_refs là seq đã persist, không phải turn ID tự sinh. |
| Decision + proposal/content/rule-question + card | target_type/target_id, card_id, negotiation_id, action mapping `approve→accept` hoặc `edit` khi có edited_package; chỉ public edited_package/feedback đã guard. Không biến content approval thành package approval. |
| Campaign + approval_decision + proposal + applied event | campaign_id, card_id, negotiation_id, approved package snapshot, approval/apply seq; package fact chỉ sau apply. |
| Monitor pause | campaign_id, negotiation_id/card_id, reason, effective_day và immutable package linkage. Không suy ra monitor pause từ thao tác seller pause. |
| Settlement + metrics + prediction | settlement_id/day/shop, campaign/negotiation, prediction_id, một public outcome; không nạp cả hai bản private/platform market event thành hai sample. |
| Content job + proposal | job_id/attempt/card/negotiation + feedback đã lọc; không đưa arbitrary private notes vào public evidence. |

Learning input hiện trả mutable table views theo ngày (`api.py:190–202`), không phải `NightSnapshot`. Freeze snapshot một lần ở settlement_cursor; cùng run/day/hash đọc lại đúng bytes. Không lấy tail event hiện tại làm cutoff sau heartbeat/tool telemetry. Đọc lịch sử cũ mà không chứng minh được chain thì omit fact có lý do; không backfill provenance bằng suy đoán.

### 5. Chưa có bất kỳ durable SI repository nào

**What this is:** `app/infrastructure/store.py:15–70` chỉ có dictionaries/lock và legacy commit. Migration 002 không có tám record của DB_HANDOFF. **Problem:** Restart mất learned state, phase ownership và call budget; legacy duplicate trả receipt cũ cả khi payload đã đổi (`store.py:41–43`). **Fix:** Implement RAM semantics SI04 và SQLite adapter dùng cùng pure validation/canonical serialization; thêm migration và factory injection. **If we skip it:** Không đạt publication atomic, chống gọi LLM lặp, budget bền vững hay recovery được yêu cầu.

Chi tiết schema/transaction tại mục 4–5. Đây là công việc triển khai được người dùng cho phép, không còn dependency để mặc định NOT_CONNECTED.

### 6. Handoff completed hiện chưa ràng buộc với NightCommit thật

**What this is:** Data chấp nhận summary/receipt_id do learning worker gửi (`integration.py:187–237`); test dùng một chuỗi receipt giả mà không có Knowledge store (`test_integration_safety.py:198–214`). **Problem:** Có thể đánh completed khi memory chưa commit; ngược lại memory đã commit nhưng timeout/skip thắng khiến business state báo failed/skipped. **Fix:** Integrated publisher xác minh durable NightCommit của đúng run/day/shop/cutoff, lấy summary từ receipt. Publication Knowledge và handoff completion/event phải nằm trong một short transaction dùng cùng connection của Data; giữ public repository signature SI, dùng transaction helper nội bộ. **If we skip it:** Retry có thể hiển thị sai kết quả học, hoặc ngày tiếp theo dùng learned state trong khi UI báo đã bỏ qua.

Reflection reserve/result phải commit riêng trước publication, không gộp vào transaction publication. `learning_control(skip)` và integrated publication cạnh tranh trên cùng write lock/version: hoặc skip thắng và publication từ chối, hoặc commit thắng và skip trả completed/conflict; không trạng thái “skipped nhưng đã có skill mới”. Heartbeat/lease timeout không cấp lại quyền reflection. Recovery completed receipt sửa projection và advance đúng một lần, không chạy LLM lần hai.

### 7. Horizon và shop scope chưa khớp SI contract

**What this is:** Data chỉ cho 6/7 ngày trong DTO (`models.py:43`), CLI (`cli.py:31`) và DB CHECK (`001_initial.sql:4`). Learning kết quả buộc D (`integration.py:191`); `summary_shop_id` default D trong migration 002. **Problem:** SI yêu cầu days 1..7, run một demo_shop và proof D/E. Chỉ sửa CLI hoặc Pydantic vẫn fail SQL; gửi E vẫn SUMMARY_SCOPE. **Fix:** Pin `demo_shop_id` ở run creation (default D), dùng trong learning snapshot/handoff/result/proof filters; mở CHECK horizon 1..7 bằng migration preserving data. **If we skip it:** Acceptance 2-day/7-day E không thể chạy trên durable authority; report 5-shop không phải proof một shop.

Không đổi HTTP 9-route seller UI sang multi-shop trong DB task. Default seller D giữ nguyên; headless E dùng backend principal scoped E và Data commands. Config/hash comparison phải include demo_shop và horizon. Proof hiện tổng cả A–E (`evidence.py:45–65`); native SI report phải filter đúng shop hoặc có report riêng có nhãn scope rõ, không gọi đó là E proof.

### 8. Thiếu daily prediction đúng trạng thái trước actual

**What this is:** Data forecasts gắn proposal/horizon (`service.py:387–413`), night view/proof truy vấn lại forecast campaign (`integration.py:245–260`, `evidence.py:60–64`). **Problem:** Sau pause/content/stock thay đổi, forecast cũ không mô tả effective state của ngày đó; không có campaign thì không có forecast row, trong khi SI yêu cầu calibration đủ daily snapshots. **Fix:** Lưu một immutable daily prediction per run/shop/day ngay trước settlement, sau monitor và approval, trước actual; không thay bảng proposal forecast dùng cho card. **If we skip it:** Calibration/proof đang so actual hôm nay với dự báo của trạng thái khác hoặc thiếu mẫu im lặng.

Prediction chứa public effective state/package hash, raw point, issued point, factor/calibration version, source và prediction_id; schema không cần chứa private cost. Settlement retry dùng prediction/settlement cũ. `service.py:485` đang ghi literal `market-v1` trong settlement fingerprint trong khi run lưu `market-v2` (`159`); lấy version đã pin ở run để fingerprint phản ánh đúng engine.

## 4. Schema vật lý đề xuất

Tạo migration mới; **không chỉnh migration 001/002 đã phát hành**. Dùng schema version mới và cập nhật health/run metadata qua nguồn version chung thay vì tiếp tục hardcode 2.

### Migration 003: Knowledge self-improve

Mọi JSON là canonical UTF-8, `CHECK(json_valid(payload_json))`, kèm `schema_version='self-improve.v1'`. Các key columns lấy từ DTO đã validate, không từ output LLM. Foreign key run_id trỏ run tồn tại; repository không tự tạo business run để làm vừa FK.

| Bảng | Columns/key và constraint cần có |
| --- | --- |
| `knowledge_meta` | `run_id` PK/FK; revision>=0 default0; cursor>=0 default0; nullable llm_limit>=0. Không có used counter. |
| `knowledge_records` | PK `(run_id,compartment,scope,record_key)`; compartment 4 giá trị; `payload_json` là KnowledgeRecord không null. Key/value/shop/category consistency do validator chung kiểm. Chỉ delete lessons. |
| `knowledge_receipts` | PK `(run_id,receipt_key)`; payload_hash + full LegacyCommitReceipt JSON. Same key/different hash conflict. |
| `skill_versions` | PK `(run_id,shop_id,skill_id,version)`; FK `(run_id,shop_id)`; created_day, effective_from_day và full SkillVersion JSON; unique `(run_id,shop_id,skill_id,created_day)`; version>0; effective=created+1. Append only. |
| `night_snapshots` | PK `(run_id,day)`; shop_id FK, snapshot_hash, full NightSnapshot JSON; day1..7. Same run/day khác shop không được thêm row. |
| `reflection_receipts` | PK/FK `(run_id,day)` tới snapshot; snapshot_hash, owner_token, status enum, full ReflectionReceipt JSON. Only reserved→terminal; terminal output invariants checked. |
| `night_commits` | PK/FK `(run_id,day)` tới snapshot; shop_id, snapshot_hash, publication_hash, full NightCommit JSON. Immutable. |
| `llm_call_reservations` | PK `(run_id,call_id)`; reserved_at UTC ISO8601 Z; FK run. Used=COUNT rows scoped run; duplicate not permission to send. |

Indexes đã bao phủ query chính qua composite PK. Chỉ thêm index skill effective day nếu measured query/loader cần; demo 7 ngày không cần generic indexing framework. Store artifact JSON trong SkillVersion receipt, không thêm bảng mutable policy hay mirror Rules. Snapshot giữ facts/derived/prior versions; không tạo evidence table trùng toàn bộ event log.

### Migration 004: business integration boundaries

| Thay đổi | Mục đích |
| --- | --- |
| Rebuild `runs` với `CHECK(simulation_days BETWEEN 1 AND 7)`; thêm immutable `demo_shop_id` default D và brief/config snapshot cần cho native attempt | Chạy đúng horizon/shop, preserve existing runs/config/grants. Brief shape do agent/API contract chốt. |
| Negotiation `version`, pinned context JSON/hash, terminal receipt/hash hoặc các cột tương đương | CAS finalize sau Referee, pin skill/seed từ đầu attempt, reopen biết trạng thái. Không cần persist arbitrary graph stack. |
| `daily_predictions` PK `(run_id,shop_id,day)`, unique prediction_id trong run, payload/hash | Forecast effective-state trước settlement và calibration evidence. FK shop; immutable. |
| Learning handoff bind shop và durable commit key/hash | Completed chỉ từ NightCommit thật; cùng transaction publication/completion. |
| Content provider slot state (theo media review) | `provider_state_json` trên content_jobs đủ cho A/B/C/video: request_hash, idempotency_key, reservation, provider job_id, status/unknown, result asset ID. Reserve transactionally, no network. Không thiết kế lại provider API ở DB lane. |

Rebuild runs phải giữ mọi column của migration002, foreign keys và rows hiện có. SQLite không đổi CHECK tại chỗ. Runner migration cần hỗ trợ bước rebuild an toàn: exclusive startup/migration window; tắt FK **trước** BEGIN cho connection migration; create `runs_new` đủ schema → copy rows → drop old → rename new; `PRAGMA foreign_key_check` trước COMMIT, bất kỳ lỗi rollback cả DDL/version receipt; bật lại FK trước trả connection. Không rename old table rồi để SQLite rewrite hàng loạt FK sang tên cũ. Không dùng `writable_schema` hoặc xóa DB để vượt CHECK. Mọi connection runtime vẫn FK ON. Test migration với run có campaigns/decisions/metrics/assets/grants thật, không chỉ sessions rỗng.

Nếu writer implementation muốn gộp 003/004 thành một migration mới thì vẫn phải giữ hai nhóm acceptance này và snapshot backup trước lần mở DB đầu tiên. Tên migration thực tế lấy sequence kế tiếp trong checkout, không ghi đè migration mới của member khác.

## 5. Transaction và repository implementation

Implement `SqliteKnowledgeStore` tại `app/infrastructure/sqlite_store.py` (hoặc file backend tương đương đã chốt ở composition), dùng `data.growth_data.storage.Store` đã inject. Domain/gateway không import SQL/DataService. Pure validation/hash/receipt construction được dùng lại giữa RAM và SQL; không copy policy business rules vào SQL.

| Method/command | Atomic behavior và caller |
| --- | --- |
| get/list/metadata | Read DTO mới/deep copy; `model_validate_json` giữ strict tuple wire; metadata giữ tuple `(revision,cursor)` legacy. |
| commit_batch | Tính payload_hash theo `{run_id,new_cursor,writes}` ordered; duplicate check trước revision; validate toàn bộ writes trước mutation; one commit rows+meta+receipt. |
| save_night_snapshot | Insert-if-absent; same hash trả old, different hash NIGHT_SNAPSHOT_CONFLICT; check run/shop/day/cutoff. |
| claim_reflection | Insert unique reserved từ snapshot; race chỉ một owner token; loser không gửi provider. |
| finish_reflection | Same owner/hash; reserved→completed/failed/unknown; same terminal payload idempotent, different REFLECTION_RESULT_CONFLICT. |
| reserve_llm_call | BEGIN IMMEDIATE; pin/check limit; check duplicate; COUNT reservations; insert only below cap; duplicate/exhausted false. Không refund slot. |
| commit_night | Duplicate run/day/hash before CAS; verify snapshot/terminal reflection/metadata/namespaces/versions/artifact hash/effective day; one commit knowledge + versions + revision/cursor + full NightCommit. |
| Integrated publish | Data-owned synchronous wrapper dùng cùng transaction helper/connection để check handoff and lease/skip, commit_night, complete handoff, safe events và finish_night_tx. Không gọi public method mở nested write connection. |
| Recovery | Chỉ startup khi chắc old worker đã dừng mới reserved→unknown. Normal connection creation/sweeper không gọi recover_reserved_reflections. Reconcile already committed publication; never resettle or resend paid invocation. |

`Session.new(store_factory=...)`, SessionManager, simulation runner tiếp tục nhận factory theo SI contract. Integrated loader phải truyền **run_id đã có**, không nhận factory với UUID mới. `LLMClient` bind store/run; all roles share one run ledger/cap. Offline/replay hit không reserve. Callback calibration đọc nhanh đúng snapshot của ngày trước; không gọi lại Data command/write từ callback trong một write transaction.

Rows/JSON validation phải cover đầy đủ `contracts/self_improve/v1.schema.json`, valid examples và invalid cross-field examples. Schema parse thành công không thay check hash/provenance/parent version/authorization. Không import `docs/.../schema_contract.py` vào ứng dụng.

## 6. Tasks và thứ tự giao implementer

| Task | Files chính | Done khi |
| --- | --- | --- |
| DB01 — pin authority và map caller | `app/runtime/session.py`, `app/runtime/manager.py`, backend adapter mới; `docs/ARCHITECTURE.md`, `TEAM_INTEGRATION.md`, SI ownership notes | Một Data run ID đi xuyên session/event/store; no seed-based resume; quyết định business vẫn qua Data commands. |
| DB02 — migrate preserving data | `data/growth_data/storage.py`, migration mới, `models.py`, `service.py`, `cli.py`; migration tests | Upgrade v1/v2 giữ records/IDs/FKs; rollback fault không thay user_version; horizon1..7 và demo_shop D/E valid. Backup tool dùng trước upgrade local thực. |
| DB03 — SI durable repository | `app/infrastructure/sqlite_store.py`, common repository validation, `tests/contract/test_knowledge_repository.py` | Cùng contract assertions chạy MemoryStore + SQLite; reopen/concurrency/copy/hash/rollback pass. LLM ledger không mất sau reopen. |
| DB04 — Data evidence/prediction | `data/growth_data/service.py`, `integration.py`, event projection module, `simulation/market.py` adapter | Frozen public evidence có exact Data IDs/cutoff; approved/applied/edited/pause cases; one daily prediction before actual; no private leakage. |
| DB05 — finalize và publication lifecycle | Data operation/finalize/learning commands, core adapter, integration tests | Referee stop không agreed/present; queued op không settle; full night commit+handoff atomic; skip/commit race resolves one way; restart không gọi model lại. |
| DB06 — durable media binding dependency | Migration/content job transaction helpers; coordinated media worker files | A/B/C/video idempotent slot reservation; reopen has provider binding/unknown; no duplicate paid submit on timeout; no source/UI work in DB lane. |
| DB07 — local data acceptance + handoff | Existing `data/setup.sh`/CLI only as needed, integration runner/tests, this plan/runbook | Local DB created/upgraded without reset; integrity+FK check; native offline D/E 7 days same seed, durable reopen; exact report labels and artifact paths. Hosting reviewer owns web process launch. |

DB01/02 can precede SI implementation; DB03 consumes SI01/SI04 DTO/common semantics and must coordinate with that implementer. DB04/05 consume native agent and publication contracts. Do not ask user to authorize each task again; implementation is already requested. Full implementation/commits belong to Terra 6.1 Max as specified by user; this review changes no source.

## 7. Acceptance matrix required before durable/integrated PASS

1. **Migration safety:** seed a v2 DB with completed and pending business run; backup; upgrade; compare identifiers/counts/payloads; integrity_check=ok and foreign_key_check empty. Fault halfway through DDL leaves old version/rows and can retry. Newer version refuses downgrade. Repeated open is inert.
2. **Repository atomicity:** one invalid write leaves all records/meta/versions/receipt unchanged. Inject failure after first write and before final receipt; reopen and prove no partial publication. Same night different payload conflicts; same payload returns original receipt even after later revision.
3. **Concurrency:** two independent Store instances/connections claim same reflection; exactly one owner. More concurrent call IDs than cap grant exactly cap. Same call ID returns already_reserved. Different pinned cap conflicts. No Python-lock-only test as sole evidence for SQLite.
4. **Recovery:** process A saves snapshot/reserves reflection+slot; stop A; new process recovers unknown; no provider invocation. Completed reflection survives failed publication and retry reuses output. Completed night read before all learning; duplicate summary/version/hash exactly match.
5. **Business lifecycle:** external queued/running/failed-unresolved operation cannot close; terminal proper operation can. Repeated night never decrements stock twice. Referee stop after accept yields failed terminal with no seller card/campaign.
6. **Publication vs handoff:** rollback after Knowledge mutations leaves handoff/commit/events all absent; after commit retry returns same. Race seller skip against publish never yields skipped with newly committed knowledge. Worker timeout cannot trigger a second reflection or refund budget.
7. **Evidence/privacy:** agreed-not-applied creates no approved fact; seller edited voucher links correct child proposal and approval; monitor pause uses exact campaign; seller pause rejected as monitor fact; cross-run/shop/category/future refs fail. Public learner/platform view contains no unit cost/min profit/private notes. Duplicate metric projections produce one sample.
8. **Prediction/calibration:** paused ads predict ads0, content gain applied once, depleted stock bound, prediction freezes before actual and is reused on retry. Calibration only prior-day records, needs minimum points, memory OFF makes no learned read/write. Proposal horizon forecast is not substituted for daily snapshot.
9. **Scope/proof:** days1,2,7 work on durable DB; day7 becomes complete, no day8. D and E use distinct runs with pinned demo_shop. Same seed/config reproduces offline metrics; ON need not beat OFF. Native report totals filter intended shop and contain IDs/engine/base hashes/skill versions/source/budget status.
10. **Media storage gates (media owner):** explicit latest job/proposal/attempt lookup, never jobs[-1] without order; durable slot unknown recovery; selected asset existence/size/hash before publish+campaign. Missing media object must not publish a campaign.

## 8. Checks run in this review

```text
PYTHONPATH=data .venv/bin/python -m pytest -c data/pyproject.toml \
  data/tests/test_integration_safety.py data/tests/test_http_harness.py \
  data/tests/test_handoffs_and_content.py data/tests/test_calibration.py -q
→ 19 passed, 1 failed in 25.98s
```

Failure: `test_images_only_retry_preserves_video_and_rejects_text_changes`, line236 expected 422 RETRY_SCOPE, received 409. Media reviewer independently instrumented the request: test picked already-succeeded attempt1 because `api.py:123` jobs query has no ORDER BY and test uses jobs[-1]. Fix authoritative latest-job projection/order and test identity; do not weaken JOB_TERMINAL guard. Media reviewer also reproduced selected cover file deleted → publish 200 + campaign active → download404; their lane owns publish asset validation.

Additional isolated HTTP repro (TemporaryDirectory; no provider or production database): `simulation_days=2` returns 422 VALIDATION_ERROR; external queued start followed immediately by night returns200/day2/5 settlements with start still queued. Both are direct evidence for findings1/7.

No `data/.venv` or `data/runtime/growth.db` existed when inspected; tests used root `.venv` and temporary databases. The review did not install packages, create/upgrade the user's runtime DB, start visible UI, call paid APIs, inspect secret values or make commits.

Verdict: fix findings1–8 and complete DB01–DB07 integration gates before claiming durable native self-improve. The existing Data transaction foundation is usable; a replacement database stack is unnecessary.

Not checked: production hosting, paid providers, full frontend workflow and provider quality. Those are separate lanes; passing the focused Data tests alone does not establish those outcomes.
