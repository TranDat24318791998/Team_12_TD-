# Contract cho các module thuần của skill evolution

Contract này dành cho SI01–SI03. Quyền ghi Knowledge, model transport và publication chưa nằm trong các module thuần. Model/schema mới ở `app/domain/models/skills.py`; hàm dựng facts ở `app/memory/evidence.py`; compiler và áp policy ở `app/memory/skills.py`.

## 1. Enum và kiểu dữ liệu

Tái sử dụng `StrictModel` từ `app.domain.models.shops` và `Package` từ `app.domain.models.packages`. Bổ sung các alias `Literal` sau; không đặt giá trị enum khác.

```python
SkillId = Literal['platform_offer', 'platform_renew', 'shop_negotiate', 'content_brief']
EvolvableSkillId = Literal['platform_offer', 'platform_renew']
FactKind = Literal['approved_package', 'seller_approved_voucher_edit', 'ads_auto_paused']
PolicyAction = Literal['seed_last_approved', 'seed_approved_voucher', 'disable_ads_on_renewal']
```

Mọi list dùng `default_factory=list`; nếu bảng yêu cầu ít nhất một phần tử thì khai báo `min_length=1` và không có default rỗng. Mọi số ngày/seq dương; version không âm. ID strings trim rồi kiểm không rỗng; hash yêu cầu exact 64 hex thường, không tự chuẩn hóa hash sai. Package phải parse qua model hiện có, không copy dict chứa field ngoài schema. [JSON Schema](../../../../contracts/self_improve/v1.schema.json) và [reference validators](schema_contract.py) cụ thể hóa các constraints này.

| Model | Fields chính xác |
| --- | --- |
| `EvidenceFact` | `fact_id:str`, `run_id:str`, `shop_id:str`, `category:str`, `day:int>=1`, `kind:FactKind`, `negotiation_id:str`, `card_id:str`, `package_applied_seq:int>=1`, `support_seq:int>=1`, `source_seqs:list[int]` ít nhất 1, `package:Package` |
| `PolicyStep` | `policy_id:str`, `lesson_id:str`, `target_skill:EvolvableSkillId`, `trigger:FactKind`, `action:PolicyAction`, `evidence_fact_ids:list[str]` ít nhất 1 |
| `CompiledSkill` | `skill_id:SkillId`, `base_hash:str`, `learned_steps:list[PolicyStep]` mặc định rỗng |
| `SkillBundle` | `run_id:str`, `shop_id:str`, `category:str`, `version:int>=0`, `effective_from_day:int>=1`, `skill:CompiledSkill`, `artifact_hash:str` |
| `PolicyUse` | `policy_id:str`, `fact_id:str` |
| `SeedResult` | `package:Package`, `uses:list[PolicyUse]` mặc định rỗng |

Hash là 64 ký tự hex thường. `EvidenceFact.source_seqs` phải tăng nghiêm ngặt, chứa `package_applied_seq` và `support_seq`, và `support_seq == max(source_seqs)`; `day` là ngày event mang `support_seq`. `support_seq >= package_applied_seq` cho pause; với approved/edit lấy max seq của các event làm nguồn, vì core có nhánh ghi seller accept sau apply. `package` luôn là exact applied package đã xác minh. `evidence_fact_ids` không trùng.

`policy_id` là chuỗi `target_skill + ':' + action`; một skill có tối đa một step mỗi action. `lesson_id` và fact IDs là refs để kiểm/trace; compiler không tự coi chúng là bằng chứng đã được gateway duyệt.

| Trigger | Action | Target được phép | Thứ tự |
| --- | --- | --- | --- |
| `approved_package` | `seed_last_approved` | offer, renew | 1 |
| `seller_approved_voucher_edit` | `seed_approved_voucher` | offer, renew | 2 |
| `ads_auto_paused` | `disable_ads_on_renewal` | chỉ renew | 3 |

Validation model: step đúng cặp và target; policy ID đúng quy tắc; CompiledSkill chứa step cùng target, không trùng action, đúng thứ tự bảng. Shop/content có learned_steps rỗng. Bundle version 0 phải có learned_steps rỗng; version >0 có thể rỗng để biểu diễn đã gỡ policy. Không thêm `approved` hay trường tiền tùy ý vào step. `extra='forbid'` kế thừa từ StrictModel.

## 2. Dựng facts từ events

```python
def build_skill_facts(
    events: list[Event], *, run_id: str, shop_id: str, category: str,
    day: int, through_seq: int,
) -> list[EvidenceFact]: ...
```

Đây là hàm thuần. `category` lấy từ public shop do caller bind, không lấy từ model. Chỉ dùng events có đúng run/shop, `1 <= event.day <= day`, `1 <= event.seq <= through_seq` và data.source khác `seeded`. `Event` lấy từ `app.domain.models.events`. Dữ liệu event ngoài scope bị bỏ qua trước khi join. Caller truyền day<1 hoặc through_seq<0 → `ValueError('INVALID_EVIDENCE_CUTOFF')`; through_seq=0 trả list rỗng.

Join bằng exact `card_id` và `negotiation_id`, không parse tên ID. Dữ liệu chưa đủ join thì không sinh fact. Seq trùng với hai payload khác nhau trong tập đã lọc là lỗi input `ValueError('DUPLICATE_EVENT_SEQ')`; cùng seq cùng event chỉ dùng một lần. Event data sai type hoặc thiếu field chỉ bỏ candidate đó; không chuyển exception/text riêng vào output.

| Fact | Điều kiện dựng | Package và support |
| --- | --- | --- |
| approved_package | `package_applied` actor `system` có package/card/negotiation hợp lệ; join `seller_decision` actor `seller` action `accept` hoặc `edit` cùng card và negotiation | Package từ apply; support=max(apply.seq, decision.seq); sources=[apply, decision] |
| seller_approved_voucher_edit | Fact approved tồn tại; decision có `edited_package` đúng toàn bộ applied package; join bản gói trên card trước edit theo quy tắc dưới đây và voucher thực sự khác | Package từ apply; support như approved; sources thêm card_sent và negotiation_finished của bản gói trước edit |
| ads_auto_paused | `auto_action` actor `system`, data.action=`pause_ads`, có card_id; join approved fact cùng card, pause.seq > apply.seq và applied package có ads>0 | Package từ apply; support=max(pause.seq, approved.support_seq); sources=approved sources + pause |

Nếu nhiều decision cùng card/negotiation cùng biểu diễn approval thì chọn seq lớn nhất trong cutoff. Với action `edit`, bắt buộc `edited_package` khớp applied package để dựng cả approved fact. Với action `accept` có edited_package thì cũng phải khớp. Có edit mà thiếu apply chỉ là preference evidence hiện hành, chưa đủ sinh skill fact.

Để chứng minh sửa voucher, lấy `card_sent` actor system mới nhất cùng card/negotiation có seq trước decision, rồi lấy `negotiation_finished` actor system cùng negotiation mới nhất trước card_sent, status agreed/warning_only và package parse được. Voucher trước/sau phải khác. Thiếu chuỗi này hoặc seller chỉ sửa ads thì không tạo voucher-edit fact; approved fact vẫn hợp lệ. Khi facade Data được nối, owner map vào chính event contract này; helper không cần đợi facade và không phỏng đoán giá trị gốc từ package đã apply.

Auto-action của core hiện chỉ có card ID; lấy negotiation ID từ applied fact đã join. Dựng fact từ events ngay cả khi `state.active` đã bị clear lúc hết hạn. Không đọc `ShopState` hoặc raw private context trong helper này.

`source_seqs` được sort và dedup. `fact_id` = SHA-256 đầy đủ của canonical JSON array `[run_id, shop_id, kind, card_id, negotiation_id, package_applied_seq, support_seq]`, dùng hàm canonical bytes ở mục 3. Sort kết quả theo `(support_seq, kind, fact_id)` tăng dần. Một approved apply tạo tối đa một fact của mỗi kind; nhiều pause hợp lệ cho cùng apply lấy pause seq lớn nhất.

## 3. Compiler và artifact

```python
def canonical_bytes(value: object) -> bytes: ...
def compile_skill(skill_id: SkillId, base_text: str,
                  steps: list[PolicyStep]) -> CompiledSkill: ...
def dump_skill(skill: CompiledSkill) -> bytes: ...
def load_skill(blob: bytes, *, expected_hash: str) -> CompiledSkill: ...
```

Canonical JSON dùng `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')`. `canonical_bytes` chỉ nhận giá trị JSON-compatible; lỗi type/NaN là ValueError/TypeError của serializer, không tự ép `str`.

`compile_skill`: hash exact `base_text.encode('utf-8')`; copy steps, sort theo thứ tự mục 1; validate CompiledSkill. Input trùng action hoặc sai target bị reject, không tự chọn một bản. Không sửa list/Package của caller. `base_text` rỗng hoặc chỉ whitespace → `ValueError('EMPTY_BASE_SKILL')`.

`dump_skill` serialize `skill.model_dump(mode='json')` thành canonical bytes. `load_skill` kiểm SHA-256 blob bằng expected_hash trước, sau đó parse/validate; hash sai → `ValueError('ARTIFACT_HASH_MISMATCH')`, JSON/schema sai → ValueError hoặc ValidationError. Sau parse yêu cầu `dump_skill(parsed) == blob`, khác → `ValueError('NON_CANONICAL_ARTIFACT')`. Bước round-trip dùng đúng bytes sẽ lưu vào store.

Compiler không đọc filesystem, store, environment hay gọi model. Base assets/prompt composition được coding agent nối ở SI06 theo LEARNING_RUNTIME_CONTRACT; tests dùng base_text fixture ngắn. Static compiler checks không tự gắn nhãn deterministic/provider evaluation.

## 4. Áp policy để tạo seed

```python
def apply_skill(
    base_seed: Package, bundle: SkillBundle, facts: list[EvidenceFact], *,
    run_id: str, shop_id: str, category: str, day: int,
    kind: Literal['propose', 'renew'], memory_enabled: bool,
) -> SeedResult: ...
```

Caller chọn base_seed theo hành vi hiện có: approved history hoặc DEFAULT_PACKAGE. Hàm này không tự đọc history và không dùng cho lượt accept counteroffer. Policy tạo proposal seed; proposal vẫn cần cả public/private validators ở graph hiện hành.

1. Check bundle đúng run/shop/category; sai → `ValueError('SKILL_SCOPE_MISMATCH')`. `kind=propose` cần platform_offer, renew cần platform_renew; sai → `ValueError('SKILL_KIND_MISMATCH')`.
2. Kiểm artifact hash bằng SHA-256 của `dump_skill(bundle.skill)`; sai → `ARTIFACT_HASH_MISMATCH`.
3. Copy base_seed. Nếu memory OFF hoặc bundle chưa tới effective day, trả bản copy với uses rỗng. Core caller vẫn phải lấy base_seed không chứa learned history khi memory OFF; helper không thể xóa dữ liệu caller đã nhét vào base_seed.
4. Facts dùng được phải đúng run/shop/category và fact.day <= day. Fact khác scope/ngày tương lai bỏ qua; chỉ SI03 tạo tập facts đã kiểm nguồn. Không sửa input.
5. Chọn approved fact mới nhất theo `(package_applied_seq, support_seq, fact_id)`. Chọn voucher-edit fact mới nhất theo cùng tuple. Với pause, chỉ dùng fact cùng `package_applied_seq` và card với approved fact mới nhất; pause của gói cũ hơn không tắt ads của một gói mới đã được seller duyệt lại.
6. Áp từng step theo thứ tự cố định. Seed approved thay toàn bộ Package bằng bản copy từ fact. Seed voucher chỉ thay voucher_pct. Disable ads đặt ads_daily_budget=0 và stop_roas_below=None, giữ stop_after_days/duration/content/voucher. Mỗi bước có fact phù hợp thêm một PolicyUse, kể cả khi giá trị seed vốn đã giống. Thiếu fact thì bỏ riêng step đó.
7. Dựng lại Package bằng `Package.model_validate(values)` sau mỗi bước; trả SeedResult. Không gọi model, tăng budget, apply gói hoặc sửa Rules trong helper.

`PolicyStep.evidence_fact_ids` chứng minh nguồn học policy, không phải danh sách fact duy nhất được phép dùng vĩnh viễn. Runtime dùng facts đúng shop/cutoff hiện tại theo trigger; vì vậy một policy generic có thể lấy gói vừa được duyệt gần nhất. Publication validator phải kiểm evidence học trước khi đưa step vào bundle.

## 5. Fixture thống nhất

Các facts/bundle fixtures lấy envelope `schema_version/model/source/payload` từ [examples](../../../../contracts/self_improve/examples.json), source=fixture. Riêng Event fixture giữ `{source:fixture,payload:[Event,...]}` vì Event là contract hiện có ngoài envelope mới. Dùng run `r1`, shop `E`, category `quat_mini`, negotiation `n1`, card `c1`. Package P1: content_refresh=true, ads_daily_budget=50000, voucher_pct=5, stop_roas_below=5.5, stop_after_days=2, duration_days=3.

Events: seq 6/day1 negotiation_finished agreed với P0 giống P1 nhưng voucher=3; seq 8/day1 card_sent version1 cùng n1/c1; seq 10/day1 seller_decision edit với edited_package=P1; seq 11/day1 package_applied=P1; seq 20/day 3 auto_action pause_ads card c1. Fact IDs lấy theo thuật toán mục 2. Fact approved có sources [10,11]; voucher-edit có [6,8,10,11]; cả hai support=11, applied=11. Pause sources [10,11,20], support=20, applied=11. Cả ba có cùng P1, ngày lần lượt 1,1,3. Đây là fixture của helper; core HTTP hiện chưa hỗ trợ seller action edit.

Renew bundle fixture chứa ba steps, lesson IDs tính theo công thức ADD hiện hành SHA256(`run:scope:normalized_text`) lấy 16 hex đầu; dùng ba canonical renew text templates trong PUBLICATION_CONTRACT. Policy IDs theo mục 1, evidence refs đúng fact tương ứng; version=1, effective_from_day=4. Base text fixture là `Platform renew fixture v1` (không newline). Lấy đúng IDs/base/artifact hashes đã tính trong examples, không điền placeholder. Fixture không chứng minh bất kỳ model/provider hay doanh thu thật nào.
