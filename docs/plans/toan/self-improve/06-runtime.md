# SI06 — Pin bundle, base skills và dùng lại trong Platform

Phụ thuộc SI05. Xong khi skill học đêm d đi vào tool result/seed đúng attempt từ d+1, cả native và fallback dùng cùng context, validators/seller gate vẫn hoạt động.

## Đọc và Output

Đọc [LEARNING_RUNTIME_CONTRACT mục 4–6](LEARNING_RUNTIME_CONTRACT.md), [CORE_CONTRACT mục 4](CORE_CONTRACT.md), `negotiation/agents.py`, `graph.py`, `prompts.py`, `agents/tools.py`, `agents/content.py`, `content/prompts.py` và knowledge-flow/negotiation tests hiện có.

Output: các file caller trên; `app/domain/models/skills.py` thêm PlatformSkillView; `learning.py` thêm PlatformMemoryView.skill; `tools.py` thêm PinnedPlatformContext; `memory/gateway.py`, `memory/skills.py`, `memory/night.py`, `runtime/session.py`; nối `memory/base.py` và bốn assets đã tạo tại SI05; `tests/unit/memory/test_base_skills.py`, `tests/integration/memory/test_skill_activation.py`, các tests knowledge-flow/negotiation liên quan; nhật ký Toàn.

## Các bước

1. Bốn assets theo enum; compose_base_text là chỗ duy nhất ghép core prompt + asset. Hash exact text dùng thực tế. Shop/content vẫn base-only; Referee giữ hiện tại. Không chép mọi prompt thành một bộ prompt khác.
2. Implement gateway.skill_bundle chọn latest effective version; kiểm hash/base; không có thì synthetic version 0. Artifact sai báo audit, base-only fallback và proof invalid. Pin base hash trong run, phát hiện source prompt thay giữa run.
3. prepare_platform_context đóng public memory, cutoff, bundle, seed và base_text thành DTO. Graph tạo một lần sau negotiation_id, trước lượt đầu; truyền cùng bản qua các rounds. Không giữ lock qua network, không dùng Session.current_skill.
4. Bind read_memory với pinned copy, giữ input `{}` và native prerequisites. Prompt Platform dùng seed làm điểm bắt đầu; fallback lấy đúng seed. Giữ forecast/validator cho gói cuối, accept phải exact counteroffer và không chạy lại policy ở nhánh đó.
5. Memory OFF phải bỏ learned memory khỏi mọi đường prompt/tool/cache/seed. DEFAULT_PACKAGE là seed; Rules/trạng thái business vẫn enforce. Không thay đổi active package hoặc apply content từ một night commit.
6. skill_published từ receipt, skill_used từ pin context; chỉ metadata public. Version dùng trong event phải đúng version model/tool đã thấy. Không bật API/UI edit chỉ để có fixture voucher.

## Acceptance

| Test/fixture | Expected |
| --- | --- |
| `test_next_day_activation` | Publish day 3/effective4: day 3 thấy v0, day 4 thấy v1; renew seed ads=0/voucher=5 theo fixture |
| `test_attempt_pin_across_rounds` | Store có version mới giữa rounds: attempt cũ giữ hash/cutoff/seed; attempt mới đủ ngày nhận version mới |
| `test_native_consumes_skill_seed` | Fake model chỉ đưa package đúng sau khi thấy seed trong read_memory ToolMessage; final graph dùng package đó |
| `test_fallback_uses_same_seed` | Provider unavailable vẫn dùng seed/trace cùng native context; final validators vẫn được gọi |
| `test_accept_is_exact_counteroffer` | Learned pause không sửa gói của counter rồi báo accept; nếu đổi thì phải propose |
| `test_base_hash_and_immutable_assets` | Base hash là full composed prompt; không night/model nào ghi assets; changed base làm proof invalid |
| `test_corrupt_persisted_artifact` | Fallback version 0, audit SKILL_ARTIFACT_INVALID; không crash và không dùng artifact hỏng |
| `test_off_has_no_learned_input` | Sentinel trong history/preferences/calibration/lessons/skill không có trong OFF input/tool/seed |
| `test_existing_history_baseline_preserved` | Memory ON với zero policy vẫn giữ history seeding hiện có; không ghi công hành vi cũ thành uplift mới |
| `test_golden_and_private_regressions` | Golden A–E, stock prune, private grounding/leak_guard, round cap, seller approval đều giữ |

Chạy focused tests: `.venv/bin/python -m pytest -q tests/unit/memory/test_base_skills.py tests/integration/memory/test_skill_activation.py tests/integration/agents/test_agent_knowledge_flow.py tests/unit/negotiation/test_negotiation.py`. Sau đó full `.venv/bin/python -m pytest -q` để bắt caller regressions trước SI07.
