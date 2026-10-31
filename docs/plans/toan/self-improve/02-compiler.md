# SI02 Compiler và áp policy tạo seed

Phụ thuộc SI01. Dùng fixtures SI01; SI03 sẽ kiểm thêm pipeline từ events sau khi helper evidence có code. Hoàn thành khi artifact kiểm được hash, policy đúng thứ tự và mọi input của caller được giữ nguyên.

## Đọc và Output

Đọc [CORE_CONTRACT mục 3 đến 5](CORE_CONTRACT.md), `app/negotiation/agents.py` tại fallback của `decide_platform`, `app/domain/validators.py`.

Output được sửa: `app/memory/skills.py` mới; `tests/unit/memory/test_skills.py` mới; một dòng nhật ký Toàn. Chưa sửa agents/graph/store hoặc tạo file base prompt; coding agent nối base assets ở SI06.

## Các bước

1. Implement `canonical_bytes`, `compile_skill`, `dump_skill`, `load_skill` đúng chữ ký. Xong khi dump/load round-trip đúng bytes/hash và tampering bị reject.
2. Implement `apply_skill` theo bảy bước của contract. Xong khi trace uses chỉ chứa steps thực sự có fact và seed có ads=0, stop=None khi đủ trigger renew.
3. Test failure/skip semantics theo bảng. Chạy final_check với public/private seed E như một test tích hợp validator; production helper chỉ trả seed, graph vẫn kiểm cuối.

## Acceptance

| Test đề nghị | Input và expected |
| --- | --- |
| `test_compile_is_deterministic` | Steps đầu vào đảo thứ tự → cùng bytes/hash; input list giữ nguyên |
| `test_artifact_round_trip_and_tamper` | Load đúng hash → model bằng nhau; đổi một byte → ARTIFACT_HASH_MISMATCH; JSON không canonical dù hash đúng → NON_CANONICAL_ARTIFACT |
| `test_base_hash_changes_with_text` | Đổi base text → base_hash và artifact_hash đổi; whitespace-only base bị reject |
| `test_three_policies_apply_in_order` | Renew fixture, base ads70000/voucher10, day 4 → ads0/voucher5/stopNone, ba PolicyUse đúng thứ tự |
| `test_memory_off_and_not_effective` | Memory OFF hoặc day 3 với effective4 → copy nguyên base_seed, uses=[] |
| `test_scope_kind_and_hash_errors` | Bundle khác run/shop/category, kind sai hoặc hash sai → mã lỗi contract |
| `test_missing_fact_skips_only_that_step` | Thiếu approved-voucher-edit → vẫn áp seed approved và pause nếu đủ facts còn lại |
| `test_old_pause_does_not_disable_new_package` | c1 pause, c2 apply mới được duyệt nhưng chưa pause → renew c2 vẫn có ads |
| `test_latest_records_have_fixed_tie_break` | Nhiều approved/edit fact → chọn đúng tuple contract, không phụ thuộc input order |
| `test_future_and_cross_shop_facts_are_ignored` | Facts khác scope/ngày tương lai không đổi seed |
| `test_inputs_are_not_mutated` | Dump base_seed/bundle/facts trước sau giống nhau |
| `test_policy_seed_still_requires_validator` | Seed từ evidence cũ có thể vi phạm luật hiện tại; final_check phát hiện. Helper không tự claim approved |

Lệnh: `.venv/bin/python -m pytest -q tests/unit/memory/test_skills.py tests/unit/domain/test_skills.py`. Full suite ở SI06/SI07; full-run tiếp tục SI03 sau focused checks.

Bàn giao artifact bytes/hash và SeedResult của fixture. Đạt task này chứng minh deterministic policy behavior trong tests; model/provider và runtime activation chưa được kiểm.
