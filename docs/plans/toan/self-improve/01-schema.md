# SI01 Schema và fixtures của skill

Hoàn thành khi các DTO và fixture parse đúng, các tổ hợp sai bị reject, và tests cũ vẫn qua. Task này chưa nối runtime.

## Đọc và Output

Đọc [CORE_CONTRACT mục 1 và 5](CORE_CONTRACT.md), `app/domain/models/shops.py`, `packages.py`, `learning.py`, `tests/unit/domain/test_contract_fixtures.py`.

Output được sửa: `app/domain/models/skills.py` mới; `contracts/skills/renew_bundle.json` và `facts.json` mới; `tests/unit/domain/test_skills.py` mới; một dòng nhật ký Toàn. Tái sử dụng Package/StrictModel; giữ DTO hiện có trong learning.py.

## Các bước

1. Khai báo bốn Literal aliases và sáu models đúng mục 1. Dùng field/model validators cho quan hệ trigger/action/target, ID, list order và version. Xong khi từng model import được mà không import app runtime/client.
2. Lấy EvidenceFact/SkillBundle envelopes từ contracts/self_improve/examples.json để tạo facts.json (array envelopes) và renew_bundle.json (một envelope). Vì compiler SI02 chưa có, test tính canonical JSON/hash bằng hashlib/json để kiểm fixture; giữ công thức này trong test, không tạo module production thứ hai. Xong khi mọi hash và fact ID khớp dữ liệu fixture.
3. Viết test matrix bên dưới bằng pytest parameterize; dùng Package thật. Xong khi lỗi validation đúng nhóm ValueError/ValidationError, không chỉ assert mọi input gây exception bất kỳ.

## Acceptance

| Test đề nghị | Input và expected |
| --- | --- |
| `test_skill_fixtures_parse` | Parse envelope payload facts/bundle; đúng three steps và đủ source refs |
| `test_policy_pair_and_target` | Năm tổ hợp hợp lệ trong bảng target; wrong pair và pause-on-offer bị reject |
| `test_step_cannot_set_arbitrary_values` | Extra ads_daily_budget hoặc approved trong PolicyStep bị reject |
| `test_step_identity_and_duplicates` | ID sai quy tắc, duplicate evidence ID, duplicate action bị reject |
| `test_compiled_step_order` | CompiledSkill đã serialize phải đúng thứ tự; đảo steps bị reject |
| `test_fact_source_constraints` | Seq=0, sources thiếu support/applied, nguồn trùng hoặc không sort bị reject |
| `test_base_only_skills` | Shop/content có step bị reject; version 0 có step bị reject; version2 rỗng hợp lệ |
| `test_schema_defaults_are_isolated` | Hai instance không dùng chung list defaults |

Lệnh: `.venv/bin/python -m pytest -q tests/unit/domain/test_skills.py tests/unit/domain/test_contract_fixtures.py`. Ghi kết quả và mapping acceptance→test; full suite ở SI06/SI07. Trong full-run tiếp tục SI02, không báo skill evolution hoàn thành chỉ từ schema.
