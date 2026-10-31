# SI04 — DTO publication, stage và repository RAM

Phụ thuộc SI01–SI03. Xong khi một night có thể stage và commit knowledge/skill/receipt nguyên khối, retry không ghi lặp. Task này implement contract DB, không implement DB engine.

## Đọc và Output

Đọc [PUBLICATION_CONTRACT](PUBLICATION_CONTRACT.md), [DB_HANDOFF](DB_HANDOFF.md), models learning hiện có, `memory/gateway.py`, `infrastructure/store.py` và tests gateway/store. Xem models tương ứng trong [schema](../../../../contracts/self_improve/v1.schema.json); dùng [reference](schema_contract.py) để kiểm cross-field.

Output: mở rộng `app/domain/models/learning.py`, `app/infrastructure/store.py`, `app/memory/gateway.py`; thêm `app/memory/learning.py`, `tests/unit/memory/test_stage_learning.py`, `tests/unit/memory/test_publication.py`, `tests/contract/conftest.py`, `tests/contract/test_knowledge_repository.py`; mở rộng tests gateway/store; nhật ký Toàn. Chưa đổi run_night caller hoặc live transport.

## Các bước

1. Thêm DTO trong PUBLICATION mục 2 và bốn record wire KnowledgeRecord/KnowledgeMeta/LegacyCommitReceipt/LLMCallReservationRecord trong DB_HANDOFF. Mở rộng LearningEvidence bằng fields có default; giữ LessonBatch/NightSummary/commit_batch tương thích. Mapping DB không import runtime/client.
2. Tách helper validate/score/dedup từ gateway để `stage_learning` dùng được mà không side effect. Giữ `_lesson_grounded` định tính và leak_guard của HEAD hiện tại cho legacy ops. Proposals qua leak_guard, typed provenance rồi dùng canonical template; không áp legacy prefix/vocabulary lên code-authored template hoặc nới guard cho text model. Trả index của original op/proposal khi reject.
3. Stage legacy ops rồi proposals; kiểm base/lesson versions, fact type, scope, fresh support và negotiation evidence. Score, duplicate vote và cap 30 theo contract. Loại policies của lesson bị delete/eviction. Stage trả records/writes/lessons/steps; không mutate store/snapshot hoặc apply business package.
4. Implement methods mới của store theo PUBLICATION mục 3. RAM dùng cùng RLock, copy state đầy đủ rồi swap trong commit. Guard hash/cutoff/namespace/parent/effective day và same-key/different-payload. Budget ledger cùng run và cap được pin.
5. Contract tests dùng factory RAM mặc định. Tạo fixture factory có thể thay bằng adapter member DB tại SI07; không import SQL backend cụ thể. Test fault injection trước swap để chứng minh rollback, không chỉ assert một method được gọi.

## Acceptance

| Test/fixture | Expected |
| --- | --- |
| `test_extended_wire_models` | Toàn bộ DTO task này parse JSON mẫu; typed extra fields sai bị reject; legacy LearningEvidence vẫn parse |
| `test_stage_three_policy_adds` | Snapshot mẫu day 3/cursor 0: ba proposal renew → ba lessons score 2/steps; inputs giữ nguyên |
| `test_policy_op_lifecycle` | Evidence mới cho UP/EDIT; DOWN về0 xóa cả lesson và step; duplicate evidence không tăng score |
| `test_stage_stale_and_scope` | Sai run/shop/fact kind, support<=cursor, stale skill/lesson → đúng rejection một lần, không rớt toàn batch |
| `test_eviction_removes_bound_step` | >30 lessons scope → eviction tất định; artifact candidate không còn step mồ côi |
| `test_legacy_cannot_edit_bound_policy` | Legacy ops sửa lesson gắn policy → INVALID_LESSON; phải dùng proposal để giữ binding |
| `test_typed_policy_keeps_qualitative_guard` | Typed proposal đủ facts nhận canonical text; cùng text đưa qua legacy ops vẫn phải qua gate cũ; raw proposal text không được persist |
| `test_snapshot_and_phase_identity` | Same key/hash reuse; different hash conflict; hai owners chỉ một reserved owner; terminal payload không đổi |
| `test_night_atomic_rollback` | Một write/version sai hoặc exception trước swap → records/meta/versions/receipt không đổi |
| `test_night_duplicate_and_conflict` | Cùng publication trả receipt cũ duplicate; khác payload cùng night key conflict kể cả expected revision cũ |
| `test_night_parent_and_effective_day` | Version phải nối parent hiện có, d+1; unchanged artifact không tăng version; delete-last-step tạo empty version |
| `test_budget_atomic` | N requests đồng thời với cap 2 chỉ hai granted; retry call_id không được gửi lại; limit đổi conflict |
| `test_reads_are_copies` | Mutate read DTO không làm đổi store |

Chạy `.venv/bin/python -m pytest -q tests/unit/memory tests/unit/runtime/test_store.py tests/contract/test_knowledge_repository.py`. Ghi kết quả và bất kỳ regression của baseline riêng. Trong chế độ full-run, tiếp tục SI05 khi đạt; không dừng để xin mở task.
