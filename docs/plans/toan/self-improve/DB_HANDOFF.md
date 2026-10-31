# Schema bàn giao cho bên cung cấp DB — self-improve.v1

Phần improve chốt cấu trúc dữ liệu, khóa và hành vi repository. Bên DB cung cấp adapter cùng transaction của họ; không yêu cầu engine, migration hay một DB riêng. Bộ schema có thể kiểm bằng máy tại [v1.schema.json](../../../../contracts/self_improve/v1.schema.json), [mẫu hợp lệ](../../../../contracts/self_improve/examples.json) và [mẫu phải từ chối](../../../../contracts/self_improve/invalid_examples.json).

## 1. Định dạng và quyền sở hữu

JSON Schema dùng Draft 2020-12. Envelope trao đổi/fixture có bốn trường bắt buộc:

```json
{
  "schema_version": "self-improve.v1",
  "model": "KnowledgeMeta",
  "source": "fixture",
  "payload": {"run_id": "r1", "revision": 0, "cursor": 0, "llm_limit": null}
}
```

`model` chọn DTO trong `$defs`; adapter có thể lưu payload riêng với schema_version ở cột metadata. Không bắt HTTP/tool hiện có thêm envelope. `source` là live/replay/offline/fixture/skipped do backend cấp. Không lấy source, run/shop, revision, hiệu lực hoặc quyền ghi từ model output.

JSON lưu UTF-8; IDs không rỗng; hash SHA-256 là 64 hex thường; integer ngày/seq/version đúng range trong schema. `null` khác trường bị bỏ. Tuple namespace trên wire là array đúng ba phần tử. Khi đọc JSON dùng `model_validate_json` để hỗ trợ tuple của StrictModel; không ép payload tùy ý thành string. Không cho extra fields.

Domain hiện có như Package, PublicHistory, Preference, CalibrationRecord, PublicLesson nằm trong `$defs` nguyên hình dạng hiện hành. Không thêm Rules/private shop/cost/persona vào public Knowledge. Business DB vẫn là nguồn seller decisions, active packages, stock và listing; Knowledge chỉ lưu dữ liệu dẫn xuất đã được gateway kiểm.

## 2. Tám loại record bền vững

Tên bên dưới là tên logic; không bắt buộc tám bảng vật lý. Unique keys bắt buộc có hiệu lực với các worker đồng thời.

| Record logic | Khóa duy nhất | Payload chuẩn | Mutation |
| --- | --- | --- | --- |
| knowledge_records | `(run_id, compartment, scope, record_key)` | KnowledgeRecord | Upsert bốn ngăn; chỉ lessons cho phép delete |
| knowledge_meta | `(run_id)` | KnowledgeMeta | revision/cursor qua commit; llm_limit pin ở lần reserve đầu |
| knowledge_receipts | `(run_id, receipt_key)` | LegacyCommitReceipt | Insert once; giữ tương thích commit_batch |
| skill_versions | `(run_id, shop_id, skill_id, version)` | SkillVersion; khóa lấy từ bundle | Append only; không sửa artifact cũ |
| night_snapshots | `(run_id, day)` | NightSnapshot | Put if absent, cùng hash đọc lại |
| reflection_receipts | `(run_id, day)` | ReflectionReceipt | reserved → completed/failed/unknown đúng owner |
| night_commits | `(run_id, day)` | NightCommit | Insert once trong transaction publication |
| llm_call_reservations | `(run_id, call_id)` | LLMCallReservationRecord | Insert once; reserved_at UTC do server cấp |

KnowledgeRecord không cần record_type riêng: compartment quyết định type. `value` không được null; thao tác xóa dùng StoreWrite.value=null rồi xóa record, không lưu tombstone trong knowledge_records. SkillVersion rỗng là version thật để gỡ policy, vẫn phải giữ.

| compartment | scope | record_key | value |
| --- | --- | --- | --- |
| history | shop_id | negotiation_id | PublicHistory |
| preferences | shop_id | pref_id | Preference |
| calibration | category | category | CalibrationRecord |
| lessons | category hoặc `strategy` | lesson_id | PublicLesson |

Khóa phải khớp field tương ứng trong value. Gateway bind shop/category trước khi ghi. Bản v1 chỉ học demo_shop trong mỗi run; cùng run/day mà đổi shop là conflict. Không thêm shop_id vào night key để âm thầm biến v1 thành worker nhiều shop.

KnowledgeMeta khởi tạo revision=0/cursor=0/llm_limit=null. Mỗi knowledge commit thành công tăng revision một, cursor không lùi. Lần reserve đầu pin limit, thường 64; các lần sau cùng run phải cùng limit, khác → BUDGET_LIMIT_CONFLICT. Reserve budget không tăng knowledge revision và không đổi cursor. used tính từ số reservation, không giữ một counter độc lập có thể lệch khỏi ledger. Legacy `metadata(run_id)` vẫn trả `(revision,cursor)`.

LegacyCommitReceipt.payload_hash là SHA-256 canonical `{run_id,new_cursor,writes}` theo đúng thứ tự writes; không hash expected_revision hoặc receipt_key. Duplicate phải có cùng hash, khác → LEGACY_REQUEST_CONFLICT. Đây là tăng cường semantics cũ, không thay signature commit_batch.

## 3. Các DTO phục vụ luồng học

| Nhóm | Models | Vai trò |
| --- | --- | --- |
| Evidence | EvidenceFact, LearningEvidence | Facts đã join từ approval/apply/pause; retrieval public đã freeze |
| Policy | SkillPatchProposal, NightReflectionOutput, PolicyStep | Output model có giới hạn; policy code đã duyệt |
| Artifact | CompiledSkill, SkillBundle, SkillVersion | Base hash, typed steps, version, ngày hiệu lực và eval |
| Ghi memory | StoreWrite, StagedLearning, NightPublication | Stage rồi commit; model không gọi trực tiếp |
| Chống lặp | NightSnapshot, ReflectionReceipt, NightCommit | Input cố định, quyền reflection, kết quả commit có thể trả lại |
| Repository requests | ClaimReflectionRequest, CommitNightRequest, ReserveCallRequest, CallReservation | Payload cho các methods tương ứng; không tự tạo HTTP routes |
| Context runtime | PolicyUse, SeedResult, PlatformSkillView, PlatformMemoryView, PinnedPlatformContext | Pin seed/version công khai cho một attempt |
| Replay và proof | ReplayBinding, ReplayEntry, ReplayManifest, RunResult | Cache có scope và kết quả headless; không bắt DB lưu các file này |

EvidenceFact được giữ bên trong snapshot. PolicyStep nằm trong artifact SkillVersion; không cần bảng policy mutable riêng. NightPublication là request tạm; NightCommit là receipt bền vững và giữ publication_hash. StagedLearning/PinnedPlatformContext/RunResult không phải business table mới.

## 4. Transaction và state transition

Các chữ ký repository chính xác nằm ở [PUBLICATION_CONTRACT mục 3](PUBLICATION_CONTRACT.md). Implement interface đồng bộ hiện hành; mọi read trả bản copy. Giữ get/put/list/metadata/commit_batch cho callers cũ. Inject qua `Session.new(store_factory=...)`; store inject trực tiếp có ưu tiên; mặc định dùng MemoryStore RAM.

```text
snapshot put-if-absent
    ↓
reflection reserved (unique owner)
    ↓ completed(output) | failed(null) | unknown(null)
    ↓
stage + compile + deterministic checks
    ↓
ONE COMMIT: knowledge writes + skill versions + revision/cursor + NightCommit
```

Không giữ transaction/lock qua network call. Reflection terminal lưu trước publication, để lỗi commit không làm gọi model lần hai. Snapshot/phase/budget reservation không bị rollback cùng publication. NightCommit đã tồn tại được đọc trước mọi thao tác học lại.

commit_night kiểm duplicate theo run/day/shop/snapshot_hash/publication_hash trước CAS. Cùng request trả receipt cũ, chỉ đổi knowledge.store.duplicate=true trong bản trả. Request khác cùng key conflict. Sau đó kiểm snapshot, terminal reflection, expected revision/cursor, namespace, parent version, hash/artifact và ngày hiệu lực; bất kỳ lỗi nào không được ghi một phần.

SkillVersion: version=parent+1; effective_from_day=created_day+1; chỉ thêm nếu artifact đổi; tối đa một version/skill/night. Nightly evaluator chỉ được cấp deterministic. Receipt giữ đủ summary/accepted ops/rejections/versions/source để retry trả kết quả mà không recompute.

Reservation completed bắt buộc output khác null; reserved/failed/unknown bắt buộc null. Terminal cùng payload là idempotent; khác là REFLECTION_RESULT_CONFLICT. Worker khác thấy reserved thì NIGHT_BUSY. Chỉ recovery sau khi worker cũ chắc chắn dừng mới đổi reserved→unknown; retry dùng output rỗng, không gửi provider lại. Không tự lấy timeout của DB làm quyền chạy reflection lần hai.

Reserve LLM slot là atomic check limit + insert unique reservation. Duplicate không cấp quyền gửi request; hết cap không insert; timeout/crash không hoàn slot. Cache replay hit và offline không reserve. Budget là số slot đã cấp, có thể lớn hơn số request thực sự tới provider khi process chết trước send.

## 5. Lỗi và nghiệm thu adapter

Các lỗi repository là StoreConflict với code ổn định: NIGHT_SNAPSHOT_CONFLICT, NIGHT_REQUEST_CONFLICT, STALE_KNOWLEDGE, REFLECTION_RESULT_CONFLICT, LEGACY_REQUEST_CONFLICT, BUDGET_LIMIT_CONFLICT. Scope/type/hash sai là validation error và rollback. NIGHT_BUSY và KNOWLEDGE_CONFLICT được workflow chuyển thành WorkflowError; không trả raw DB exception/private payload ra UI.

Bộ contract tests cụ thể ở [SI07](07-integration.md) và [REPLAY_PROOF_CONTRACT mục 2](REPLAY_PROOF_CONTRACT.md): rollback mọi phần khi lỗi, duplicate khác payload, stale CAS, concurrent claims, concurrent budget, clone-on-read, immutable versions và reopen. Giữ source fixtures; không promote fixtures thành live evidence.

Schema kiểm shape/range/enum và một số quan hệ cục bộ. Hash, thứ tự version, khóa ngoại theo run/shop, nguồn evidence, cạnh tranh transaction và quyền ghi vẫn phải kiểm ở repository/gateway. Parse JSON Schema thành công không thay các checks này.

Improve core hoàn tất bằng RAM và cùng bộ contract tests. DB adapter chưa giao ghi `durable: NOT_CONNECTED`; khi adapter được giao chạy lại tests reopen/recovery mới ghi `durable: PASS`. Không cần chờ DB để code core. Phục hồi Knowledge job không đồng nghĩa phục hồi business Session hoặc negotiation đang chờ seller.
