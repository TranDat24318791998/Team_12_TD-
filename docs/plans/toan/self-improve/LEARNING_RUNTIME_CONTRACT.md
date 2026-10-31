# Contract Learning và runtime đã chốt

Áp dụng SI05–SI06. DTO và repository semantics ở PUBLICATION_CONTRACT; các model thuần và thuật toán ở CORE_CONTRACT. Đây là phần nối vào core hiện có, không tạo workflow thứ hai.

## 1. Pipeline run_night

Giữ `run_night(session, day) -> NightSummary`. Dùng một invocation role learning, tối đa ba provider requests của runner hiện tại, chung cap 64. Không thêm một lượt reflector sau Learning.

```text
đọc NightCommit đã có → trả summary nếu có
kiểm day đã settled
memory OFF → summary rỗng, không reflection/learned writes
đọc NightSnapshot đã lưu hoặc freeze/derive/validate/save snapshot mới
claim reflection với owner_token mới
  completed → dùng output đã lưu
  failed/unknown → dùng output rỗng, giữ error/source
  reserved thuộc worker khác → NIGHT_BUSY
  reserved do chính invocation mới tạo → chạy native Learning, lưu receipt ngay
gateway kiểm text → stage ops → compile → dump/load → deterministic checks
candidate fail → rollback lesson/policy portion, giữ derived portion
commit_night atomic, một CAS rebase tối đa, không gọi lại LLM
cache Session từ receipt → emit summaries theo commit_key → trả summary
```

Snapshot mới giữ revision/cursor và upper event seq trước khi gọi provider. Tái sử dụng ba helper `_derive_*` hiện có. Kiểm derived records và nguồn bằng gateway trước khi save_night_snapshot; persistence không nhận raw model writes. Snapshot chứa public projections, derived records và base text; không chứa ShopPrivate, Persona, API key hoặc raw tool transcript riêng.

Gọi `build_skill_facts` trên toàn bộ authorized events qua cutoff, không chỉ events ngày hiện tại. Bổ sung negotiation IDs đã xác minh qua facts vào valid_negotiation_ids và public context cần thiết cho `_lesson_grounded`; source seq cũ vẫn chỉ là context. Fresh support dùng seq > expected_cursor, không nhân đôi support từ join ngày trước.

Gắn `LearningEvidence.skill_facts` và `skill_bundles` rồi freeze DTO này. Tool T08 trả deep copy đúng DTO đã freeze dù có tool events mới xuất hiện sau đó. bind_role_tools đổi output_schema của read_learning_evidence sang DTO mở rộng; `run_agent` vẫn yêu cầu đọc tool thành công trước finish_learning.

Output schema của invocation là NightReflectionOutput. Khi runner trả fallback hợp lệ, receipt completed có source offline, không nhận là live reflection. Khi provider timeout nhưng fallback hoàn tất, toàn invocation đã có kết quả offline; chỉ đánh unknown khi invocation không lưu được kết quả sau crash. AgentToolError/fallback thất bại → receipt failed, output=None; night tiếp tục với output rỗng.

## 2. Fallback có giới hạn và validation

Fallback gọi T08 qua dispatch như trước. Chọn proposals từ facts mới theo thứ tự: pause→renew disable ads; edited voucher→offer voucher; edited voucher→renew voucher; approved→offer seed; approved→renew seed. Bỏ những lựa chọn không có fact phù hợp hoặc đã có policy với cùng evidence; lấy tối đa ba. Nếu policy chưa có dùng ADD, nếu đã có và có negotiation evidence mới dùng UPVOTE. Fallback không tự DOWNVOTE/EDIT. Nếu không có skill proposal, giữ legacy fallback lesson hiện có khi evidence đủ.

LessonOp.text_vi của proposal dùng template trong PUBLICATION_CONTRACT. scope mặc định category của shop; base_skill_version lấy từ bundle tương ứng của snapshot. LessonOp.evidence là các negotiation IDs có thật của facts. Cùng fact được dùng cho offer và renew là hai policy khác nhau; cùng policy/evidence không được vote lại.

Các thay đổi model có quyền đề xuất: legacy text LessonOps và năm tổ hợp policy đã cho phép. Model không chọn ngày hiệu lực, artifact hash, eval_level, approved, revision/cursor, source hoặc Rules. Các giá trị đó do code dựng.

## 3. Deterministic evaluation của candidate

Thêm `evaluate_candidate(bundle, *, base_text, facts) -> list[str]` trong `memory/skills.py`; raise ValueError('CANDIDATE_EVAL_FAILED') nếu bất kỳ check không đạt. Hàm này gọi compiler/apply_skill đã có, không chạy pytest hoặc provider trong job đêm.

Các check ID cố định phải có trong SkillVersion.eval_checks:

| Check ID | Kiểm bằng code |
| --- | --- |
| schema_allowlist | Parse lại bundle/steps, đúng target và cặp trigger/action |
| immutable_base | SHA256 base_text khớp compiled base_hash |
| artifact_roundtrip | dump→load đúng hash/bytes chính artifact sẽ lưu |
| scope_and_effective_day | Bundle cùng run/shop; trước effective day giữ base seed |
| memory_off | Cùng bundle/facts nhưng memory_enabled=false giữ base seed, uses rỗng |
| policy_order | Chỉ những steps có trong candidate được thực hiện theo thứ tự CORE_CONTRACT; ads pause là bước cuối |
| source_values | Giá trị voucher/package đến từ fact được chọn; không có constant từ model |
| input_immutability | Input snapshots/seed/facts không bị mutate |

Evaluation sử dụng facts của snapshot và thêm scenario copy deterministic khi cần kích hoạt đúng trigger đang có trong candidate. Scenario thêm chỉ để kiểm implementation, gắn source fixture trong eval report, không trở thành evidence của policy. expected package được tính từ bảng biến đổi rõ ràng của CORE_CONTRACT, không gọi apply_skill lần hai để làm oracle cho chính nó.

Tại test tích hợp, chạy seed qua validators/graph thật với luật hiện hành; candidate seed có thể không còn hợp luật do shop đổi trạng thái, graph phải clamp/reject bình thường. Evaluation không được ghi rằng mọi seed tự nó đã được seller duyệt hoặc chắc chắn có lợi nhuận.

## 4. Chọn version và pin attempt

Đặt các hàm trong `app/memory/skills.py` hoặc gateway khi cần store; pure compiler vẫn không đọc store:

```python
MemoryGateway.skill_bundle(shop_id, skill_id, day, *, base_text) -> SkillBundle
prepare_platform_context(session, shop_id, day, kind, negotiation_id) -> PinnedPlatformContext
```

`PinnedPlatformContext` ở domain/models/tools.py có fields chính xác: `run_id:str`, `shop_id:str`, `category:str`, `negotiation_id:str`, `day:int>=1`, `kind:Literal['propose','renew']`, `through_seq:int>=0`, `memory:PlatformMemoryView`, `base_text:str`. Scope, skill ID và bundle day phải khớp. Field base_text chỉ dùng dựng SystemMessage; không serialize nguyên PinnedPlatformContext vào public event.

Thêm `PlatformSkillView` ở domain/models/skills.py: `bundle:SkillBundle`, `seed:SeedResult`. PlatformMemoryView thêm `skill:PlatformSkillView|None=None`, giữ caller/fixtures cũ parse được. Pinned view chứa đúng bundle và seed, không chứa raw facts/financials. PolicyUse giữ fact IDs để trace nguồn.

skill_bundle chọn version có effective_from_day<=day lớn nhất theo version, kiểm artifact/base hash rồi load lại artifact. Không có version hoặc memory OFF → bundle version 0 empty steps. Bản persisted mới hơn nhưng chưa đến ngày không được chọn. Artifact/base hash sai → dùng base-only bundle, log SKILL_ARTIFACT_INVALID; proof run gặp trường hợp này bị đánh invalid, không âm thầm tính là kết quả cùng cấu hình.

prepare_platform_context chạy một lần ngay sau negotiation_id được tạo trong run_negotiation. Trong Session lock ngắn, lấy public memory view, versions và event cutoff nhất quán; copy thành pinned DTO. Chọn base_seed theo fallback hiện có: approved history gần nhất hoặc DEFAULT_PACKAGE. Memory OFF thì base_seed=DEFAULT_PACKAGE. Tạo facts từ authorized events qua cutoff và gọi apply_skill. Thả lock trước provider.

Thêm keyword tương thích `platform_context=None, kind='propose'` vào decide_platform. Graph truyền cùng pinned DTO trong mọi lượt; direct caller không truyền context thì prepare một lần cho invocation đó. Không tạo Session.current_skill mutable dùng chung.

bind_role_tools thêm keyword `platform_memory=None`: với platform, read_memory trả deep copy pinned PlatformMemoryView khi có; role khác giữ view hiện hành. Arguments model của read_memory vẫn `{}`. Agent initial payload không nhét raw Session/private/history lần nữa.

Native Platform đọc view.skill.seed.package qua ToolMessage; prompt yêu cầu dùng nó làm điểm khởi đầu khi propose và vẫn validate/forecast đúng gói cuối. Fallback dùng cùng seed. Nếu lượt hiện tại accept counteroffer thì lấy exact package của counter, không chạy lại policy/clamp rồi gọi đó là accept. Package đổi sau validator phải là propose như logic hiện tại.

## 5. Base text và chỗ nối prompts

Bốn assets UTF-8 nằm tại `app/memory/base_skills/{platform_offer,platform_renew,shop_negotiate,content_brief}.md`. Assets chứa hướng dẫn riêng theo skill; các yêu cầu tool/schema/privacy chung vẫn ở prompt hiện có.

Thêm `compose_base_text(skill_id, core_text) -> str` trong `app/memory/base.py`: đọc đúng file từ enum/path cố định, trả `core_text + '\n\n' + asset_text`. Compile hash trên toàn bộ text thực dùng, không chỉ hash phần asset. Không có path do model chọn. Night dùng cùng composition cho hai Platform skills; Shop/Content dùng cùng helper với core prompt của mình. Referee giữ prompt hiện hành.

Trong một run, base hashes được pin khi dùng lần đầu. Nếu file/core prompt thay đổi giữa run, ghi BASE_SKILL_CHANGED và dùng base-only safe fallback; report proof invalid. Model không viết assets hoặc source code. Learned policies được compile thành dữ liệu và áp bằng code, không nối model text tùy ý vào SystemMessage.

## 6. Event và approval behavior

Emit `skill_published` sau NightCommit với run/day/shop/skill_id/version/effective_from_day/artifact_hash/eval_level/commit_key. Emit `skill_used` khi pin attempt với negotiation_id, skill_id/version/artifact_hash, knowledge_revision và policy/fact refs. Public event không có private prompt/tool result.

Night commit không tạo campaign/content job và không đổi Rules. Gói đã agreed vẫn chờ seller. Content start/apply và confirmation dùng workflow hiện có. Core HTTP chưa hỗ trợ edit: acceptance voucher policy dùng fixture events hợp lệ; không tự bật UI/API edit trong scope self improve. Điều này là giới hạn kênh nhập hiện tại, không phải quyết định schema còn mở.

## 7. LLM budget và source

LLMClient thêm keyword constructor `store=None, run_id=None` và invoke_tools thêm `call_id=None`. Runner truyền `call_id=f'{run_name}:{step}'` với step0..2. Bind/validate tool schema trước reserve; reserve ngay trước network request. Call_id là backend-issued, không lấy từ provider tool_call_id hoặc model arguments. Direct caller không truyền call_id dùng UUID riêng cho request đó.

Có store thì reserve qua repository, remaining_calls là property từ cùng ledger. Không store thì behavior RAM cũ. Slot trùng hoặc hết cap → LLMUnavailable, runner fallback. Provider timeout không hoàn lại slot, giữ available=false như hiện tại. Fixture transport không bị ghi thành live budget usage; tests phân biệt fake requests với network reservations.

Log/request count là số slot đã reserve, một slot có thể không đến provider nếu process chết trước send. Gọi đây là budget slots, không tuyên bố provider đã xử lý mọi request. Reflection receipt ngăn chạy lại whole invocation; replay ở SI07 kiểm trước live reserve.
