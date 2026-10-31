# Self-improve SI01–SI07: review và kế hoạch nối durable local

What this change does: Gói self-improve cho phép Learning đề xuất policy có kiểu, kiểm bằng code rồi dùng làm seed cho Platform ở ngày sau. Review này chỉ đánh giá SI01–SI07 và dependency Data/DB của chúng; không thay review riêng cho orchestration, tools, Knowledge gốc, API hoặc media.

Reviewer: Astra max. Ngày 31/10/2026. Source tại HEAD 33fbdd5, gồm Data 9621b14, media a0a93f0 và frontend bd78f8e. Docs self-improve và contracts/self_improve hiện là tài liệu người dùng chưa commit; đã đọc, không sửa. Mô hình vận hành: một máy local, một backend worker, SQLite; không thêm auth framework, vector DB, hàng đợi ngoài hoặc dịch vụ DB mới.

## Kết luận hiện tại

**SELF-IMPROVE: IMPLEMENTATION REQUIRED. DURABLE LOCAL: NOT IMPLEMENTED. PROVIDER EVALUATION: NOT RUN.**

Schema và task đủ làm điểm bắt đầu. Chưa có module ứng dụng thực hiện compiler, skill facts, policy stage, skill versions, durable reflection/publication hoặc replay. Baseline Learning đang ghi lesson định tính; việc đó không đồng nghĩa đã có skill evolution.

Yêu cầu mới của người dùng thay phần trì hoãn DB trong self-improve/README.md:23, 07-integration.md:9–18 và DB_HANDOFF.md. Lần triển khai tới phải giao SQLite local và kiểm reopen/recovery; không kết thúc ở RAM với durable NOT_CONNECTED. Giữ schema/semantics đã chốt, cập nhật các câu phạm vi cũ khi lập plan tổng hợp. Không cần thiết kế lại compiler hoặc thêm một nền tảng lưu trữ khác.

## Bằng chứng đã kiểm

- Full baseline: .venv/bin/python -m pytest -q → **83 passed, 15 subtests passed**. Đây là suite hiện có, chưa chứng minh các acceptance SI01–SI07.
- Import reference schema bằng importlib, không gọi main/export: **31 models, 39 mẫu hợp lệ**, từ chối **8 mẫu sai shape và 10 mẫu sai cross-field** bằng Pydantic. Schema sinh trong RAM bằng schema đã lưu; SHA-256 khớp validation.json.
- Package jsonschema không có trong .venv hiện tại. Chưa chạy lại Draft 2020-12 validator; validation.json ghi kết quả của lượt tạo schema trước. Coder cần thêm kiểm parity trong test/dev environment, không cần thêm dependency này vào runtime.
- Reproduction tại MemoryStore: commit key night:1 ghi lesson a; gọi cùng key với lesson b và cursor khác vẫn trả duplicate=True, chỉ a tồn tại. Mong đợi mới là LEGACY_REQUEST_CONFLICT; app/infrastructure/store.py:41–43 chưa hash payload.
- Reproduction EventLog trên file tạm: ghi một event, mở lại cùng path → since(...,0) trả rỗng; event tiếp theo lại seq=1 dù file có hai dòng. app/infrastructure/eventlog.py:10–14,19 chỉ giữ index RAM. Không dùng nó để phục hồi cutoff SI từ file sau restart.
- Không gọi paid API, không đọc/in secrets, không mở UI. Không sửa source trong review.

## Must fix trước khi gọi self-improve hoàn tất

1. **[P1] Publication và quyền chạy reflection chưa bền vững** — app/memory/night.py:119–156; app/infrastructure/store.py:15–20,41–43; app/infrastructure/llm.py:12–15,30–35.

   **What this is:** Night hiện đọc cache Session, gọi Learning rồi commit các records RAM. Cap model cũng là counter RAM.

   **Problem:** Restart giữa response và commit mất quyền sở hữu reflection/output; chưa có NightSnapshot, ReflectionReceipt, NightCommit hoặc reservation để ngăn gửi lại. Same-key/different-payload được nhận nhầm là retry như reproduction trên.

   **Fix:** SI04/SI05 phải thêm repository semantics đầy đủ và SqliteKnowledgeStore cùng DB local. Lưu snapshot, claim phase, reserve từng slot trước network; lưu terminal output trước publication; commit records/versions/meta/full receipt nguyên khối. Retry đọc receipt trước cache; unknown không resend.

   **If we skip it:** Durable chỉ là tên gọi; restart có thể học hoặc trả phí lặp, thiếu artifact đã công bố, hoặc trả receipt của payload khác.

2. **[P1] Evidence Data chưa thỏa provenance để học policy** — data/growth_data/service.py:297,326,384,465,497,518,520–522; data/growth_data/api.py:190–202; self-improve/CORE_CONTRACT.md mục 2.

   **What this is:** SI03 chỉ tạo facts từ chuỗi approval → applied → pause có exact card/negotiation/package/seq.

   **Problem:** Data package_applied chưa chứa package/card và dùng actor orchestrator; card_sent thiếu negotiation; seller_decision chỉ chứa decision_id/action/edited boolean; pause thiếu campaign/card; chưa có negotiation_finished. Learning-input trả các bảng hiện tại, không phải frozen public Event projection của core. Truyền thẳng response đó vào T08 vừa thiếu joins vừa có private_evaluation/feedback_private vì learning_worker thuộc PRIVATE.

   **Fix:** Adapter evidence server-side dựng projection đúng schema từ Data rows có khóa, có cutoff. Bổ sung immutable payload/terminal event còn thiếu ngay trong transaction nguồn; không suy card từ active hiện tại hoặc parse ID. Chỉ chuyển public allowlist vào LearningEvidence. Bảng mapping bắt buộc ở dưới.

   **If we skip it:** Không sinh được pause/voucher facts, hoặc học nhầm proposal thành package đã chạy, hoặc đưa tài chính riêng vào model Learning.

3. **[P1] Chưa có policy runtime, nên chưa chứng minh skill làm đổi quyết định** — app/domain/models/learning.py:103–107,135–146; app/negotiation/agents.py:25–50; app/agents/tools.py:73–75; app/negotiation/graph.py:26–40.

   **What this is:** Platform hiện đọc History/Lessons; fallback đã seed từ approved history trước đợt này.

   **Problem:** Chưa có SkillBundle, compiler/apply_skill, effective day, pin attempt hay read_memory.skill. Native model không thể nhận learned policy seed; chuyển approved-history fallback sang tên skill không tự là cải thiện mới.

   **Fix:** SI01/SI02/SI06 tạo typed allowlist và versioned artifact; graph pin một context từ đầu attempt; read_memory trả bundle/seed đã pin; native và fallback cùng dùng seed, accept giữ exact counteroffer. Seed vẫn qua validators và seller approval.

   **If we skip it:** Báo cáo chỉ chứng minh lưu lesson; không đạt acceptance native consumption, d+1 activation và attempt pin.

4. **[P1] Chưa có proof SI07 từ settlement thật của simulator** — app/simulation/market.py:1; app/simulation/runner.py:1; app/runtime/day.py:324–357; data/growth_data/models.py:43; data/growth_data/migrations/001_initial.sql:4; data/growth_data/integration.py:191.

   **What this is:** SI07 cần ON/OFF bảy ngày D/E, daily forecast trước actual, independent memory và report đo từ simulator.

   **Problem:** Hai module simulation của app còn stub; scripts/run_sim.py chưa có. Core chưa gọi record_daily_prediction trước settle. Data chỉ nhận horizon 6/7 và learning_result chỉ nhận shop D, trái CLI 1..7/A–E của SI07. Existing Data reference driver không chạy Learning algorithm nên không thay được proof này.

   **Fix:** Nối SI runner vào workflow integration cùng Data authority; dùng engine Data, daily effective prediction và durable records. DB lane mở horizon/check thật và pin demo_shop_id để E chạy được; mặc định UI vẫn D. Không dùng FakeMarket hoặc fixture doanh thu làm proof.

   **If we skip it:** Không có số đo cho self-improve; calibration dễ dùng tổng horizon thay daily raw, và proof E không đi hết durable handoff.

## Mapping evidence bắt buộc cho SI03/SI05

Đây là dependency contract giao Data/orchestration lane, không phải cho Learning model tự join hoặc nhận quyền SQL. Cùng run_id và cùng Data event sequence phải đi xuyên cả business và Knowledge; telemetry của agent không tạo một sequence song song làm lệch cutoff.

| Nguồn Data | Projection cho SI | Quy tắc cần giữ/test |
| --- | --- | --- |
| Final negotiation/proposals | negotiation_finished: negotiation_id, kind, status, exact final package; actor system | Persist terminal event tại final verdict được backend xác nhận; không tạo agreed từ một proposal chưa kết thúc. Giữ seq thật trước card_sent. |
| cards + card_sent | card_id, negotiation_id, version; actor system | Join card.proposal_id → proposal.negotiation_id. Trước voucher edit phải còn biết package của card gốc. |
| decisions + seller_decision | card_id, negotiation_id, action accept/edit, edited_package khi có; actor seller | Data action approve được map thành accept, hoặc edit nếu có approved edited_package; join exact target proposal/card. Không map content approval/rule answer thành package approval. |
| campaigns + package_applied | exact campaign.package_snapshot, card_id, negotiation_id; actor system | Resolve bằng campaign/proposal/approval_decision FK. Chỉ fact sau activation đã qua content approval nếu refresh; không dùng mutable proposal hiện tại thay applied snapshot. |
| auto_action pause_ads | campaign/card/negotiation identity, action pause_ads; actor system | Bổ sung ID vào payload tại service.py:497/518/658 khi biết campaign. Khi campaign đã hết hạn, lookup vẫn đúng. Pause gói cũ không tắt ads gói mới. |
| content_job | feedback_vi + card/negotiation identity đã resolve | Feedback đi qua leak_guard; facts sản phẩm lấy public facts, không biến góp ý thành thuộc tính thật. |
| settlement + market_result | PublicOutcome orders/revenue/ads_spend/roas, prediction_id, campaign/card/negotiation khi có | Chọn một public projection/settlement; không nhân mẫu từ hai visibility events. Không copy profit/fees/cogs/private evaluation. |

Freeze theo settlement_cursor đã Data cấp. Queries vào rows mutable phải có snapshot/version ở cutoff; chỉ lọc events rồi join trạng thái mới hơn không bảo đảm snapshot. Loại source seeded và future day/seq trước join. Thiếu nguồn thì không tạo fact; không backfill bằng số/phần mô tả do model đề nghị. Reference schema vẫn giữ nghĩa Event/fact đã chốt; adapter map tên actor ở biên, không nới validation thành nhận mọi actor.

## Phạm vi SQLite tối thiểu cho self-improve

Đã đối chiếu với lane DB: dùng **cùng data/runtime/growth.db của DataService**, đường dẫn cấu hình được, migrations trong data/growth_data/migrations. Thêm migration kế tiếp sau 002; phối hợp một owner migration để tránh hai file 003. Tận dụng Store.connect(write=True), BEGIN IMMEDIATE, WAL và foreign_keys hiện có; không ORM, Redis, Postgres hoặc DB business thứ hai.

Adapter mới app/infrastructure/knowledge_sqlite.py thực hiện cùng contract MemoryStore; app/domain và compiler không import SQL. Dùng schema_version self-improve.v1 và JSON đã validate; kiểm type theo compartment khi đọc. Store factory có thể nhận existing Data store/path; không tự seed một business run khác.

| Logical table | Unique/primary key | Payload và kiểm tối thiểu |
| --- | --- | --- |
| knowledge_records | run_id, compartment, scope, record_key | Typed value JSON không null; key/scope khớp value; delete chỉ lessons. |
| knowledge_meta | run_id | revision>=0, cursor>=0, llm_limit null hoặc >=0. |
| knowledge_receipts | run_id, receipt_key | Full MemoryCommit + canonical payload_hash; khác payload conflict. |
| skill_versions | run_id, shop_id, skill_id, version | Immutable SkillVersion; parent+1, effective=d+1, artifact/hash/base đúng snapshot; một target/night. |
| night_snapshots | run_id, day | snapshot_hash + full NightSnapshot; put-if-absent, khác hash conflict. |
| reflection_receipts | run_id, day | owner/hash/status/full output; reserved → completed/failed/unknown. |
| night_commits | run_id, day | Full NightCommit gồm publication_hash, accepted/rejected/source/versions/summary. |
| llm_call_reservations | run_id, call_id | Backend reserved_at UTC; unique insert và pinned limit cùng transaction. |

Không thêm mutable policy table: PolicyStep nằm trong artifact. Không cất Rules/private authority vào Knowledge. Dùng khóa run cùng Data; tests RAM vẫn được inject store trực tiếp. Không coi việc mở lại Knowledge là đủ khôi phục business Session: production caller phải cấp Data run/shop/day/brief/rules/approved state đã khôi phục. Session.new hiện tạo UUID và seed mới ở app/runtime/session.py:74–90; cần đường hydrate riêng của orchestration lane, không đổi UUID sau khi namespace đã bind.

Publication commit chứa records + skill versions + metadata + full receipt trong một transaction. Snapshot/phase/budget giữ ở transaction ngắn riêng trước network. Không giữ Session/gateway/SQL lock khi gọi provider. Reopen completed receipt phải trả đúng kết quả; reserved chỉ chuyển unknown sau khi worker cũ chắc chắn dừng. Unknown được commit derived bins đã freeze, không gửi lại invocation.

Data learning_handoffs là trạng thái bàn giao/presentation, **không thay tám record Knowledge**. Worker hoàn tất commit_night trước rồi gửi kết quả có stable receipt_id sang Data learning_result. Khi response mất, đọc NightCommit và gửi lại cùng body; không gọi model hoặc stage lại. Phải lưu/make-stable body và handoff version, xử lý lease/heartbeat mà không dùng retry handoff làm quyền reflection mới. Các learning receipt terminal từ Data chỉ được báo hoàn tất sau publication thật.

## SI01–SI07: việc triển khai chính xác

| Task | Hiện có/reuse | File/schema/caller phải làm | Gate nghiệm thu |
| --- | --- | --- | --- |
| SI01 | Package/StrictModel, schema_contract reference và examples | Tạo app/domain/models/skills.py: EvidenceFact, PolicyStep, CompiledSkill, SkillBundle, PolicyUse, SeedResult và aliases. Tạo contracts/skills facts/bundle; không import code từ docs. | tests/unit/domain/test_skills.py: parity fixtures, năm action/target pairs, extra fields denied, seq/hash/ID/order, base-only Shop/Content. |
| SI02 | DEFAULT_PACKAGE, validators hiện có | Tạo app/memory/skills.py: canonical_bytes, compile/dump/load/apply_skill. Exact canonical bytes; source-values only; immutable inputs; pause chỉ renew và chỉ latest approved campaign. | test_skills.py: hash tamper/noncanonical, deterministic order, future/scope/off/no-fact, old pause vs new package, validator vẫn có quyền reject. |
| SI03 | Event model và runtime event semantics | Tạo app/memory/evidence.py build_skill_facts; event fixture. Nhận normalized Data events theo mapping trên; all history tới cutoff, không chỉ hôm nay. | test_skill_evidence.py: real approval/apply join, apply-before-accept, edit exact package, pause after expiry, duplicates/cutoff/privacy; test Data-backed event projection bằng DB tạm. |
| SI04 | Gateway score/dedup/cap và MemoryStore CAS | Thêm DTO publication vào learning.py đúng schema; tạo app/memory/learning.py stage_learning thuần; mở rộng RAM store; thêm knowledge_sqlite.py/migration và factory. Giữ qualitative gate legacy; typed proposal được canonical template sau kiểm facts, raw text không persist. | test_stage_learning.py, test_publication.py và cùng tests/contract/test_knowledge_repository.py trên RAM + SQLite. Atomic rollback, hash conflict, scope/parent/effective day, copy-on-read, score/eviction remove policy, reopen. |
| SI05 | _derive_history/_derive_preferences/_derive_calibration, native runner/T08 | Sửa night.py thành receipt→snapshot→claim→single native Learning→stage/eval→commit. NightReflectionOutput ops+proposals<=3; LearningEvidence thêm facts/bundles có defaults. Thêm base.py + bốn base_skills assets; evaluate_candidate tám checks. LLMClient store/run/call_id và runner step IDs. | test_night.py, test_night_publication.py, native Learning test: actual ToolMessage frozen, one owner, <=3 requests, persisted budget, unknown no resend, candidate rollback chỉ lesson/policy, one pure CAS rebase, response loss, private authority unavailable. |
| SI06 | Platform history seeding, validators và exact accept | Thêm PlatformSkillView, PlatformMemoryView.skill, PinnedPlatformContext; gateway.skill_bundle; prepare_platform_context; graph pin sau backend negotiation ID; decide_platform optional context/kind; tools.read_memory pinned. Compose same base text khi compile và invoke. | test_skill_activation.py: d+1, old attempt unchanged giữa rounds, new attempt nhận eligible version; native model đọc seed từ ToolMessage; fallback same seed; exact counteroffer accept; memory OFF sạch; corrupt/base changed fallback và proof invalid. |
| SI07 | Data pure simulation engine, Data durable business state, source labels | Thêm replay.py/models, simulator adapter/runner/offline content/RunResult và scripts/run_sim.py. Nối repository factory + Data event projection/handoff trong integrated worker; daily effective prediction before actual. Cập nhật contracts/shared docs về các caller đã đổi. | test_replay.py, test_recovery.py, test_proof.py; RAM/SQLite contract suite; D và E 7 ngày ON/OFF; restart giữa các boundary; report đo từ persisted settlement, hashes/versions/source/slots; không yêu cầu ON thắng. |

Không gom implementation vào một hàm night lớn. Những helper thuần đã có contract là đủ: facts, compiler/apply, stage/eval; gateway giữ privacy/authority, repository giữ transaction. Không thêm agent/reflector hoặc code-generated prompt.

## Thứ tự nhỏ nhất để chạy được đầy đủ hackathon

1. Chốt trong plan tổng hợp: SQLite local bắt buộc; Data làm business/event authority; một demo_shop_id/run; horizon 1..7. Đây là cập nhật scope theo yêu cầu mới, không phải xin phép lại vì docs cũ.
2. SI01–SI03 thuần, song song với dependency DB/evidence lane. Schema/examples là chuẩn wire; giữ positive/negative parity.
3. SI04 RAM và SQLite cùng semantics, suite contract dùng factory. Chỉ cần tám logical record types, không thêm hệ thống storage khác.
4. SI05 một night chạy đầy đủ bằng fake native model + DB tạm; test kill/reopen/unknown/response-loss trước khi nối provider. Knowledge commit xong mới handoff complete.
5. SI06 một scenario renew E chứng minh pause fact → published policy → d+1 native ToolMessage seed ads=0 → validators → seller approval. Thêm scenario voucher-edit bằng immutable trusted events, không giả UI đã có edit.
6. SI07 nối runner và replay. Chạy D/E bảy ngày bằng Data simulator, memory ON/OFF độc lập, cùng seed/config và seller policy. Lưu report local; UI proof có thể consume sau qua lane riêng nhưng không đổi source của metric.
7. Chạy full suites và reopen integrated run trên máy này. Host local là công việc của deployment lane: dùng cùng DB path/worker, không khởi tạo song song Session seed/reference driver. Provider/media live và provider quality eval có trạng thái riêng.

Đường tối thiểu này vẫn hoàn thành replay contract và durable acceptance; không đánh dấu xong SI07 chỉ vì offline script thoát mã 0. Các bước đầu có thể bàn giao nối tiếp, nhưng milestone cuối không được bỏ SQLite hoặc native seed consumption.

## Acceptance cuối giao reviewer riêng cho SI

- Giữ full baseline, rồi chạy các focused suites được liệt kê trong từng task. Map T01–T24 của plan vào test name thực tế, không ghi test dự kiến thành kết quả đã chạy.
- RAM và SQLite cùng passed assertions; SQLite thêm reopen, atomic rollback/unique claims, terminal receipt, budget ledger và hash tamper.
- Snapshot public không có sentinel cost/private rules/persona; Data learning-input không được đưa trực tiếp cho model. Facts/PolicyUse trỏ đúng run/shop/cutoff/source seq.
- ADD/UP/DOWN/EDIT + eviction giữ lesson/policy binding; candidate fail không để orphan lesson/skill; legacy qualitative privacy regression vẫn qua.
- Một native Learning invocation/night và native Platform dùng ToolMessage thực; event memory_read đơn lẻ không đủ. Reflection unknown/retry không gửi lại; replay không trừ live slots.
- Attempt pin/d+1/OFF/exact accept/final validator/seller content gate vẫn giữ. Self-improve không ghi Rules, không activate campaign, không gọi publish content.
- D/E offline seven-day reports lấy từ simulator/settlement, daily calibration đúng mẫu, restart không tăng stock effects/sample/vote. Report tách core, durable, integrated runner, provider_eval và media sources.

Verdict: triển khai các mục 1–4 trước khi gắn nhãn self-improve PASS; schema có thể dùng ngay làm chuẩn implementation. Không có yêu cầu thay thế framework hoặc mở rộng load ngoài demo local.

Not checked: paid provider/evaluator, real image/video, browser UI, toàn bộ DB/API/media correctness (có reviewer riêng), Draft 2020-12 validation trong .venv hiện tại. Report này không nhận xét hoặc sửa các thay đổi concurrent ngoài self-improve.
