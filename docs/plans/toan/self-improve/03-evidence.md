# SI03 Dựng facts từ event đã xảy ra

Phụ thuộc SI01 và SI02 đã được kiểm tra. Tái sử dụng canonical_bytes từ app.memory.skills của SI02 để tính fact IDs. Hoàn thành khi cùng tập events cho cùng facts, dữ liệu sai scope/thiếu approval không sinh fact và không có private data trong output.

## Đọc và Output

Đọc [CORE_CONTRACT mục 2 và 5](CORE_CONTRACT.md), `app/domain/models/events.py`, `app/runtime/day.py` tại `monitor_active_packages`, `start_day`, `submit_decision`, `activate_approved_package`, và event negotiation_finished trong `app/negotiation/graph.py`. Đọc để hiểu payload, không thay các module đó trong task này.

Output được sửa: `app/memory/evidence.py` mới; `tests/unit/memory/test_skill_evidence.py` mới; `contracts/skills/events.json` mới; một dòng nhật ký Toàn. Dùng DTO từ SI01. Fixture events có đầy đủ Event fields, ts là ISO string cố định, text_vi dùng câu không chứa private data.

## Các bước

1. Viết `build_skill_facts` với đúng signature. Lọc run/shop/day/cutoff trước khi lập indexes. Xong khi negative scope test cho output rỗng dù ID trùng với shop khác.
2. Index approved apply theo card/negotiation, join seller decision theo contract. Dựng facts approved/edit bằng package được parse. Xong khi edit chưa apply không sinh fact và nhánh apply-before-accept vẫn được join.
3. Join pause chỉ có card ID với applied fact; dùng source events lịch sử cùng cutoff. Xong khi state.active đã clear không ảnh hưởng kết quả helper.
4. Sinh IDs, sort/dedup đúng thuật toán. Xong khi đổi thứ tự input, gọi lại hai lần và serialize lại cho cùng bytes. Thêm một test pipeline events→facts→bundle→seed bằng compiler của SI02.

## Acceptance

| Test đề nghị | Input và expected |
| --- | --- |
| `test_canonical_event_fixture_builds_three_facts` | Events mục 5 → ba facts đúng payload của SI01 |
| `test_apply_can_precede_accept_event` | apply seq10, accept seq11 → approved fact support11 |
| `test_missing_approval_or_apply` | Chỉ propose/agreed/edit, hoặc apply thiếu seller decision → không có skill facts |
| `test_edited_package_must_match_applied` | Khác voucher hoặc field bất kỳ → không sinh approved/edit từ decision đó |
| `test_only_actual_voucher_change_is_a_voucher_fact` | Có edited_package nhưng chỉ sửa ads, hoặc thiếu bản card/gói trước edit → có approved fact, không có voucher-edit fact |
| `test_pause_joins_by_card` | Pause không có negotiation_id vẫn join đúng n1; unknown card không sinh pause fact |
| `test_scope_and_cutoff_are_enforced` | Cùng IDs nhưng khác run/shop, future day, future seq, day0 hoặc source seeded → bỏ qua; cutoff0 → rỗng, day0 của caller → INVALID_EVIDENCE_CUTOFF |
| `test_malformed_candidate_does_not_hide_good_fact` | Event package sai type cạnh apply hợp lệ → giữ fact hợp lệ |
| `test_fact_payload_has_no_private_fields_or_text` | Inject sentinel vào text/data thêm → sentinel không có trong serialized facts |
| `test_event_order_and_duplicates` | Input đảo thứ tự hoặc duplicate y hệt → cùng facts; same seq khác payload → DUPLICATE_EVENT_SEQ |
| `test_latest_pause_and_source_lists` | Hai pause cùng apply → một pause fact nguồn đúng, không lặp source seq |
| `test_events_to_policy_seed` | Fixture events → facts → renew bundle → day 4 seed ads=0/voucher=5/stop=None; mọi nguồn trace trỏ tới fact sinh từ events |

Lệnh: `.venv/bin/python -m pytest -q tests/unit/memory/test_skill_evidence.py tests/unit/domain/test_skills.py`. Bàn giao facts fixture và các negative cases đã kiểm; full-run tiếp tục SI04. Nối facts vào Learning tool thuộc SI05; full suite tại SI06/SI07.
