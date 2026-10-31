# Contract publication và persistence đã chốt

Áp dụng cho SI04, SI05 và SI07. Các quyết định dưới đây thay phần để mở ở INTEGRATION_GATES cũ. DB do member DB cung cấp; phần improve sở hữu DTO, validation và repository contract, dùng adapter RAM để phát triển và contract tests khi DB chưa nối.

## 1. Chủ sở hữu state và mức phục hồi

MemoryStore là nguồn duy nhất của history/preferences/calibration/lessons, skill versions, snapshot học, reflection receipts, night receipts và ledger budget LLM. Session chỉ giữ cache của kết quả đã commit. Rules, active package, stock và seller approval vẫn thuộc runtime/business owner; night không ghi các trường đó.

Member DB chọn schema vật lý, engine và vị trí lưu. Schema logic và semantics trong file này là đầu vào bàn giao cho họ. Không sao chép bảng campaign/inventory/decision thành nguồn business state thứ hai. Adapter RAM và adapter do member DB cung cấp có cùng interface bên dưới.

Durability ở đây bảo vệ Knowledge, budget và job học đã có snapshot. Không tự mở lại cuộc thương lượng hay Session sau server restart. Việc khôi phục business Session cần nguồn business state hợp lệ; dùng seed để tái tạo cùng run đang dở là không hợp lệ. Nghiệm thu restart trong SI07 reopen store và tiếp tục xử lý snapshot học, không nhận đó là full application recovery.

## 2. DTO bổ sung

Đặt các DTO dưới đây trong `app/domain/models/learning.py`, import các model thuần từ `skills.py`. `skills.py` không import learning.py. Dùng StrictModel, list/dict default_factory, enum và các ràng buộc range của CORE_CONTRACT.

| DTO | Fields chính xác |
| --- | --- |
| `SkillPatchProposal` | `lesson_op:LessonOp`, `target_skill:EvolvableSkillId`, `trigger:FactKind`, `action:PolicyAction`, `evidence_fact_ids:list[str]` ít nhất 1 không trùng, `base_skill_version:int>=0` |
| `NightReflectionOutput` | `ops:list[LessonOp]=[]`, `proposals:list[SkillPatchProposal]=[]`; validator tổng len(ops)+len(proposals)<=3 |
| `SkillVersion` | `bundle:SkillBundle`, `parent_version:int>=0`, `created_day:int>=1`, `source_through_seq:int>=0`, `artifact_json:str`, `eval_level:Literal['static','deterministic','provider']`, `eval_checks:list[str]` không trùng |
| `PatchRejection` | `origin:Literal['op','proposal']`, `index:int>=0`, `code:str`, `policy_id:str\|None=None` |
| `NightSnapshot` | `run_id:str`, `shop_id:str`, `category:str`, `day:int>=1`, `expected_revision:int>=0`, `expected_cursor:int>=0`, `through_seq:int>=0`, `evidence:LearningEvidence`, `derived:MemoryUpdateBatch`, `calibration_summary:dict[str,float\|int\|None]`, `prior_versions:list[SkillVersion]=[]`, `base_texts:dict[EvolvableSkillId,str]`, `snapshot_hash:str` |
| `ReflectionReceipt` | `run_id:str`, `shop_id:str`, `day:int`, `snapshot_hash:str`, `owner_token:str`, `status:Literal['reserved','completed','failed','unknown']`, `output:NightReflectionOutput\|None`, `source:Literal['live','replay','offline','fixture','skipped']`, `error_code:str\|None` |
| `StagedLearning` | `writes:list[StoreWrite]`, `lessons:list[PublicLesson]`, `steps:list[PolicyStep]`, `accepted_ops:list[LessonOp]`, `rejections:list[PatchRejection]` |
| `NightPublication` | `run_id:str`, `shop_id:str`, `day:int`, `snapshot_hash:str`, `through_seq:int`, `writes:list[StoreWrite]`, `versions:list[SkillVersion]`, `summary:NightSummary`, `rejections:list[PatchRejection]`, `source:Literal['live','replay','offline','fixture','skipped']` |
| `NightCommit` | `run_id:str`, `shop_id:str`, `day:int`, `snapshot_hash:str`, `publication_hash:str`, `knowledge:KnowledgeCommit`, `summary:NightSummary`, `versions:list[SkillVersion]`, `rejections:list[PatchRejection]`, `source:Literal['live','replay','offline','fixture','skipped']` |
| `ClaimReflectionRequest` | `run_id:str`, `day:int>=1`, `snapshot_hash:str`, `owner_token:str` |
| `CommitNightRequest` | `publication:NightPublication`, `expected_revision:int>=0`, `expected_cursor:int>=0` |
| `ReserveCallRequest` | `run_id:str`, `call_id:str`, `limit:int>=0` |
| `CallReservation` | `granted:bool`, `reason:Literal['granted','already_reserved','exhausted']`, `used:int>=0`, `remaining:int>=0` |

SkillVersion invariants: bundle.version=parent_version+1; effective_from_day=created_day+1; UTF-8 artifact_json chính là dump_skill(bundle.skill); hash khớp; source_through_seq thuộc snapshot; candidate do nightly job chỉ có eval_level deterministic. Provider là mức do evaluator riêng cấp, nightly job không tự cấp.

NightSnapshot.derived.lesson_ops luôn rỗng. Snapshot hash là SHA-256 canonical JSON của run/shop/category/day, through_seq, evidence, derived, calibration_summary, prior_versions và base_texts; loại snapshot_hash, expected_revision, expected_cursor khỏi hash. Expected metadata vẫn được lưu nhưng có thể CAS rebase theo mục 6. Source events/facts/cutoff không đổi khi rebase.

prior_versions chứa tối đa hai latest versions đã publish trước day, mỗi target một bản, cùng run/shop/category và source_through_seq<=snapshot.through_seq; không chứa synthetic version0. SkillVersion chỉ cho hai Platform targets. skill_bundles cũng không trùng target; khi freeze runtime luôn cấp đủ hai bundle, dùng synthetic v0 nếu target chưa có version. Default list rỗng chỉ để callers cũ vẫn parse.

LearningEvidence thêm fields tương thích: `skill_facts:list[EvidenceFact]=[]`, `skill_bundles:list[SkillBundle]=[]`. Chỉ hai platform bundles của đúng shop; không gửi base_texts hoặc raw Session. JSON output cũ `{ops:[...]}` vẫn parse thành NightReflectionOutput với proposals rỗng. LessonBatch cũ tiếp tục được hỗ trợ cho caller/tests ngoài night.

Bốn wire DTO của repository là KnowledgeRecord, KnowledgeMeta, LegacyCommitReceipt và LLMCallReservationRecord, fields theo [DB_HANDOFF](DB_HANDOFF.md) và JSON Schema. Không thêm một record_type lặp lại compartment. Đây là shape trao đổi; adapter tự map storage nội bộ.

## 3. Interface store

Giữ nguyên get/put/list/metadata/commit_batch cho caller hiện tại. Put dùng setup/test; runtime ghi qua commit. Bổ sung đúng các methods:

```python
save_night_snapshot(snapshot: NightSnapshot) -> NightSnapshot
get_night_snapshot(run_id: str, day: int) -> NightSnapshot | None
claim_reflection(run_id: str, day: int, snapshot_hash: str,
                 owner_token: str) -> ReflectionReceipt
finish_reflection(receipt: ReflectionReceipt) -> ReflectionReceipt
get_reflection(run_id: str, day: int) -> ReflectionReceipt | None
recover_reserved_reflections(run_id: str) -> int
list_skill_versions(run_id: str, shop_id: str,
                    skill_id: EvolvableSkillId) -> list[SkillVersion]
get_night_commit(run_id: str, day: int) -> NightCommit | None
commit_night(publication: NightPublication, *, expected_revision: int,
             expected_cursor: int) -> NightCommit
reserve_llm_call(run_id: str, call_id: str, limit: int) -> CallReservation
llm_calls_used(run_id: str) -> int
```

Mọi read trả deep copy/DTO mới. Skill versions sort theo bundle.version tăng dần. Core chỉ học demo_shop của Session; cùng run/day gửi shop khác là conflict, không âm thầm đổi scope.

save_night_snapshot là put-if-absent theo (run,day): cùng hash trả bản đã lưu; khác hash → StoreConflict('NIGHT_SNAPSHOT_CONFLICT'). Không thay evidence của một phase đã gửi provider. claim_reflection tạo reserved khi chưa có; nếu có thì trả record cũ. Chỉ caller có owner_token khớp record reserved và biết chính mình vừa tạo record mới được chạy invocation. Để tránh hai caller dùng lại cùng token, owner_token là UUID mới cho mỗi lần gọi run_night; khi get_reflection đã tồn tại trước claim thì caller luôn là retry, không có quyền chạy thêm.

claim_reflection lấy shop_id từ snapshot đã lưu, không nhận shop từ model. Reserved ban đầu có source=skipped/output=None/error_code=None. completed dùng source của output; failed/unknown có source=skipped và error_code không rỗng. Nếu hai callers freeze khác cutoff rồi save cạnh tranh, loser đọc snapshot đã lưu và tiếp tục theo phase của snapshot đó, không thay snapshot hoặc dùng output từ cutoff của mình.

finish_reflection chỉ chấp nhận cùng owner/hash từ reserved sang completed/failed/unknown; completed phải có output, failed/unknown có output=None. Lặp terminal payload giống nhau trả record cũ; khác → REFLECTION_RESULT_CONFLICT. Cùng process còn reserved thuộc caller khác → NIGHT_BUSY, không lấy timeout ngắn làm quyền gửi lại model.

recover_reserved_reflections đổi reserved→unknown, error_code=PROCESS_RESTART. Chỉ gọi khi worker cũ chắc chắn đã dừng, trong đường recovery trước khi nhận job mới; không gọi mỗi lần mở connection. Ứng dụng hiện chạy một process. Method này không khôi phục business state.

reserve_llm_call giữ atomic (run,call_id) và cap: granted=true/reason=granted khi insert mới trong budget; false/reason=already_reserved khi ID đã tồn tại, false/reason=exhausted khi hết cap. used là số slot sau operation, remaining=max(0,limit-used). Slot đã reserve không hoàn lại khi timeout/crash. LLMClient đọc remaining_calls = max(0, settings.cap - store.llm_calls_used(run)); không giữ counter mutable thứ hai khi đã bind store. Direct LLMClient(settings) không có store vẫn giữ counter RAM hiện hành cho backward compatibility.

Lần reserve đầu pin llm_limit trong KnowledgeMeta; các lần sau cùng run khác limit → BUDGET_LIMIT_CONFLICT. Reserve không tăng knowledge revision/cursor. Metadata cũ vẫn trả tuple revision/cursor; llm_limit là field lưu nội bộ. `reserved_at` dùng UTC ISO-8601 có hậu tố Z do backend cấp.

## 4. Transaction commit_night

Đơn vị atomic chứa bốn ngăn dẫn xuất, skill versions, revision/cursor và full NightCommit. Reflection receipt được lưu trước, vẫn tồn tại nếu publication thất bại; retry dùng lại output đó. publication_hash=SHA-256 canonical JSON của toàn bộ NightPublication, do backend tính, không nhận từ model.

Thứ tự xử lý trong một transaction của adapter, hoặc store lock đối với RAM:

1. Nếu đã có NightCommit cùng run/day, snapshot_hash, shop và publication_hash: trả deep copy, knowledge.store.duplicate=true. Khác bất kỳ giá trị nào → NIGHT_REQUEST_CONFLICT. Kiểm duplicate trước kiểm revision. run_night retry đọc receipt sớm và trả summary trực tiếp, không dựng publication mới từ state sau commit.
2. Kiểm snapshot đã lưu và reflection đã terminal; memory OFF không gọi method này. Kiểm publication through_seq đúng snapshot.
3. So expected_revision và expected_cursor với metadata hiện tại; mismatch → StoreConflict('STALE_KNOWLEDGE'). Cursor mới không lùi.
4. Validate toàn bộ writes bằng rules namespace/type hiện có; chỉ bốn ngăn, đúng run/shop/category. Validate every SkillVersion: parent là latest version của cùng run/shop/skill; base hash đúng snapshot; artifact/hash/effective day đúng. Candidate chỉ deterministic.
5. Dựng NightCommit từ summary thật: accepted_lesson_ops=summary.lesson_ops, rejected_ops=len(rejections), MemoryCommit.revision=current+1, cursor=through_seq, applied_ids từ writes. Kiểm summary.rejected_ops khớp.
6. Apply writes, insert immutable versions, update metadata và insert full receipt cùng transaction. RAM dựng copy rồi swap một lần; adapter DB commit một lần. Bất kỳ exception trước commit đều rollback.

Skill version chỉ được thêm nếu dump_skill mới khác bytes của latest artifact, bao gồm trường hợp policy bị xóa làm learned_steps rỗng. Không tăng version cho một night không thay artifact. Run mới dùng synthetic bundle version 0, effective_from_day1, empty learned_steps và base hash từ repo; không cần ghi version 0.

NightSummary là HTTP contract hiện có, không thêm fields bắt buộc. Version/hash/rejection details ghi trong NightCommit và các event công khai đã lọc. Session.night_summaries và knowledge_receipts có thể cache nhưng phải đọc NightCommit đầu tiên khi retry; không dựa vào cache RAM để xác nhận đã commit.

## 5. Stage lesson và policy

Đặt `stage_learning(snapshot, reflection, *, current_lessons, current_versions, current_records, text_rejections=()) -> StagedLearning` trong `app/memory/learning.py`. Đây là helper thuần. current_records là `MemoryUpdateBatch` chứa records hiện có đúng scope (lesson_ops rỗng); không nhận Session/store/client. text_rejections giữ index trong output gốc để stage bỏ đúng op đã bị gateway chặn, không reorder trước validation. Tách pure helpers từ gateway hiện tại để tái sử dụng validation/score/dedup. Giữ qualitative lesson gate của HEAD f3c8e42/9134121 và các regression leak_guard; không khôi phục parser claims số cũ. Context cần leak_guard do gateway chuẩn bị trước, không đưa raw private vào snapshot/public DTO.

Legacy ops phải qua leak_guard và `_lesson_grounded` định tính hiện có, nguyên semantics: model-authored text không chứa số/claim kết quả tùy ý. Với skill proposals, gateway leak_guard raw text và canonical template trước stage nhưng không áp vocabulary/prefix gate của legacy text lên template do code tạo. Stage kiểm structured facts/pair/provenance trước rồi thay hoàn toàn text_vi bằng template bên dưới; raw proposal text không được lưu vào lesson/artifact/public log. Đây là đường ghi policy có schema, không phải ngoại lệ cho mọi câu LLM sinh ra. Vi phạm trở thành rejection một lần, không bỏ cả invocation.

Khi phục hồi snapshot mà private authority chưa được backend cung cấp, bỏ các lesson ops với code PRIVATE_VALIDATION_UNAVAILABLE, chỉ commit derived records đã được xác minh trước; không suy đoán private context từ seed.

Validation proposal theo thứ tự: schema/cặp target → base version bằng current version → facts tồn tại trong frozen snapshot, cùng scope và đúng trigger → có ít nhất một support_seq>snapshot.expected_cursor → negotiation IDs trong lesson_op.evidence đúng với facts được dẫn → evidence chưa dùng để vote lại → validation LessonOp hiện hành. Mỗi proposal bị reject đếm đúng một lần theo check đầu tiên thất bại.

Legacy ops chạy trước, theo thứ tự output.ops. Proposals theo thứ tự output.proposals. Tổng tối đa ba. Giữ ADD score 2/version1, UP+1, DOWN−1/xóa khi0, EDIT+1/version. Lesson ID ADD dùng công thức hiện hành từ run/scope/normalized text. Khi scope khác strategy/category của shop → SCOPE_DENIED. Với vote/edit trên lesson cũ, so version với snapshot; đã thay đổi → STALE_LESSON.

Legacy ops không được UPVOTE/DOWNVOTE/EDIT lesson đang gắn policy; reject INVALID_LESSON, yêu cầu dùng proposal để kiểm binding và provenance. Legacy ADD không được đè lesson ID đã gắn policy. Một invalid item chỉ có một rejection. Khi candidate evaluation fail toàn cục, thay các rejection của lượt đó bằng CANDIDATE_EVAL_FAILED theo từng original item, không cộng thêm lần nữa.

PolicyId theo CORE_CONTRACT. ADD chỉ tạo khi chưa có policy cùng target/action. UP/DOWN phải trỏ lesson đang gắn với policy đúng target/action. EDIT tìm policy cùng target/lesson, có thể đổi sang cặp trigger/action khác trong allowlist nếu destination policy ID còn trống. Sau ops, eviction cap 30 dùng thứ tự hiện hành; loại mọi policy không còn lesson. UP/DOWN cùng action giữ sorted union evidence_fact_ids; EDIT đổi action dùng refs của proposal mới, không giữ refs sai trigger. Cùng evidence không tăng vote lần hai dù request/cursor khác.

Text cho skill proposal do code chuẩn hóa theo năm template dưới đây trước ADD/EDIT; model vẫn gửi LessonOp đúng schema nhưng không được ghi text tùy ý vào skill. Legacy text lessons vẫn đi theo validator cũ.

| Target và action | text_vi chuẩn |
| --- | --- |
| offer / seed_last_approved | Khi tạo đề xuất mới, dùng gói đã duyệt gần nhất làm điểm khởi đầu. |
| renew / seed_last_approved | Khi gia hạn, dùng gói đã duyệt gần nhất làm điểm khởi đầu. |
| offer / seed_approved_voucher | Khi tạo đề xuất mới, dùng voucher được người bán sửa và duyệt gần nhất. |
| renew / seed_approved_voucher | Khi gia hạn, dùng voucher được người bán sửa và duyệt gần nhất. |
| renew / disable_ads_on_renewal | Khi gia hạn, bỏ quảng cáo nếu gói gần nhất đã bị tự động tạm dừng quảng cáo. |

Rejection codes cố định: INVALID_PAIR, SCOPE_DENIED, STALE_SKILL, UNKNOWN_FACT, WRONG_FACT_KIND, NO_FRESH_EVIDENCE, EVIDENCE_MISMATCH, DUPLICATE_EVIDENCE, DUPLICATE_POLICY, MISSING_POLICY, STALE_LESSON, INVALID_LESSON, PRIVATE_VALIDATION_UNAVAILABLE, CANDIDATE_EVAL_FAILED. Bổ sung details ở log nội bộ khi cần; không trả raw exception/private text.

## 6. Candidate failure và CAS retry

Stage trên bản copy, compile cả offer/renew sau mọi ops/eviction, dump→load đúng artifact bytes rồi chạy deterministic checks theo SI05. Chỉ lưu versions có artifact đổi. Compiler/eval thất bại ở bất kỳ target nào: rollback toàn bộ lesson ops và policies của night, giữ versions/lessons cũ; history/preferences/calibration hợp lệ vẫn commit. Summary.lesson_ops=[]; mọi op/proposal nhận rejection CANDIDATE_EVAL_FAILED. Không giữ lesson mới trong khi policy tương ứng bị rollback.

CAS conflict: mỗi lần run_night được phép rebase tối đa một lần, dùng reflection receipt cũ, giữ nguyên facts/cutoff. Đọc current records/versions rồi merge: preferences union evidence nhưng giữ status/asked/declined hiện tại; calibration union sample IDs, cùng ID khác payload → conflict; history có evidence ngoài cutoff thì giữ current record, còn lại derive lại qua cùng events; lesson/skill versions đã đổi thì reject stale op tương ứng. Không chạy lại LLM. CAS fail lần nữa → trả WorkflowError KNOWLEDGE_CONFLICT, lần gọi sau vẫn dùng receipt cũ.

Lỗi sau store COMMIT trước ghi log/response: đọc NightCommit dựng lại summary. Night log có `commit_key=night:<run>:<day>`; trước emit từng type memory_write/skill_published/night_summary kiểm event cùng type/key để tránh lặp trong EventLog hiện tại. Audit event không được đưa trở lại làm evidence học của chính night.

## 7. Schema logic bàn giao member DB

Đây là các record và unique keys phải map được, không phải yêu cầu tạo bảng hoặc chọn một engine cụ thể. Payload là DTO JSON có schema version; member DB có thể normalize nhưng phải round-trip không mất type/provenance.

| Record | Unique key | Payload |
| --- | --- | --- |
| knowledge_records | run_id, compartment, scope, record_key | KnowledgeRecord; compartment quyết định type của value |
| knowledge_meta | run_id | KnowledgeMeta: revision, cursor, llm_limit |
| knowledge_receipts | run_id, receipt_key | LegacyCommitReceipt: result MemoryCommit và payload_hash |
| skill_versions | run_id, shop_id, skill_id, version | SkillVersion JSON |
| night_snapshots | run_id, day | snapshot_hash, NightSnapshot JSON |
| reflection_receipts | run_id, day | snapshot_hash, owner_token, status, ReflectionReceipt JSON |
| night_commits | run_id, day | snapshot_hash, NightCommit JSON |
| llm_call_reservations | run_id, call_id | reserved_at |

Legacy commit_batch cũng phải reject same receipt key/different canonical payload, giữ duplicate semantics của test cũ. Hash payload chính xác theo DB_HANDOFF, mismatch → LEGACY_REQUEST_CONFLICT. Tái sử dụng cùng pure validation/serialization helpers giữa adapters, không copy nghiệp vụ vào SQL. Lock order trong core khi cả Session và store cần lock: Session → gateway → store; không giữ các lock đó qua network/provider. Member DB chứng minh cùng hành vi bằng bộ contract tests; dạng transaction nội bộ do họ chọn.

Session.new thêm keyword `store_factory=None`, gọi factory(run_id) sau khi tạo run ID; store được inject trực tiếp có ưu tiên. Default Session.new giữ RAM cho caller cũ. SessionManager/run_sim nhận factory của member DB khi có, không tự import/chọn SQL backend. Tests luôn có adapter RAM; cùng bộ tests nhận factory DB để kiểm durable behavior. LLMClient do Session tạo được bind đúng store/run_id. Thay đổi constructor đều optional để giữ caller hiện tại.
