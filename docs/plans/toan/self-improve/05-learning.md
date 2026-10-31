# SI05 — Night học, kiểm candidate và publication

Phụ thuộc SI04. Xong khi run_night thật dùng frozen evidence, một native invocation, artifact evaluation và atomic publication; mọi retry dùng phase/commit receipt.

## Đọc và Output

Đọc [PUBLICATION_CONTRACT mục 4–6](PUBLICATION_CONTRACT.md), [LEARNING_RUNTIME_CONTRACT mục 1–3 và 7](LEARNING_RUNTIME_CONTRACT.md), `memory/night.py`, `memory/prompts.py`, `agents/tools.py`, `agents/runner.py`, `infrastructure/llm.py`, `runtime/session.py`, tests Learning native và LLM.

Output: các file vừa nêu; `memory/skills.py` thêm evaluate_candidate; mới `memory/base.py`, bốn `memory/base_skills/*.md` và `tests/unit/memory/test_base_skills.py` theo LEARNING_RUNTIME mục 5; `memory/gateway.py`, `domain/models/learning.py` khi nối DTO; tests `tests/unit/memory/test_night.py`, `tests/unit/memory/test_skills.py`, `tests/unit/infrastructure/test_llm.py`, `tests/unit/agents/test_runner.py`, `tests/integration/agents/test_learning_native.py`, mới `tests/integration/memory/test_night_publication.py`; nhật ký Toàn. Mọi constructor/keyword thêm phải optional.

## Các bước

1. Implement compose_base_text/assets trước để night compile đúng base đã chốt; SI06 nối cùng helper vào caller Platform/Shop/Content. Giữ `_derive_history/_derive_preferences/_derive_calibration` hiện có. run_night đọc receipt đầu tiên; kiểm settled; OFF trả rỗng. Freeze tất cả authorized events qua through_seq, facts, public evidence, derived records, base texts và versions; validate trước save snapshot. Snapshot đã có được dùng nguyên, không kéo cutoff lên lần retry.
2. Bind T08 vào frozen LearningEvidence; finish_learning nhận NightReflectionOutput, tổng tối đa ba ops/proposals. Giữ read tool prerequisite và tối đa ba provider requests/invocation. Prompt chỉ đề nghị enums/provenance, không cho sửa scope/day/hash/rules.
3. Claim phase trước invocation, ghi receipt ngay sau output. Terminal failed/unknown không gửi lại. Provider failure nhưng fallback thành công là completed/source offline. Áp thứ tự fallback đã chốt, không tạo reflector thứ hai.
4. `evaluate_candidate` chạy tám check IDs cố định bằng code, round-trip artifact thật. Khi bất kỳ candidate fail, rollback toàn bộ lesson/policy portion, đánh CANDIDATE_EVAL_FAILED cho mỗi output item một lần; vẫn commit derived records. Không chạy pytest từ night.
5. commit_night; stale CAS cho một rebase thuần theo PUBLICATION mục 6, không đổi snapshot hoặc gọi provider. Khôi phục summary từ NightCommit nếu lỗi sau commit. Emit theo commit_key, tránh audit events trở thành support học lại.
6. Bind LLMClient với store/run; runner cấp request call IDs; schema binding trước reserve. Replay sẽ nối trước reserve ở SI07. Direct callers không có store giữ behavior cũ; fake requests và live slots được đếm riêng.

## Acceptance

| Test/fixture | Expected |
| --- | --- |
| `test_learning_reads_frozen_skill_evidence` | Fake native model nhận facts/bundles qua ToolMessage T08; event sinh sau freeze không lọt vào đó |
| `test_legacy_learning_output` | Output chỉ có ops vẫn hoạt động; old caller dùng LessonBatch không vỡ |
| `test_one_invocation_and_three_operations` | Tối đa ba total ops/proposals; không thêm reflection call sau runner; request cap đúng |
| `test_policy_fallback_source` | Pause/voucher/approved theo priority và fresh evidence; output offline có nhãn, Rules không đổi |
| `test_candidate_eval_failure` | Corrupt candidate hoặc check fail → old artifacts/lessons; derived records vẫn commit; rejected count đúng |
| `test_retry_and_concurrent_night` | Một owner chạy native; caller khác NIGHT_BUSY; sau completed/commit trả cùng result, không cộng votes/budget |
| `test_unknown_phase` | Recovery reserved→unknown; không gọi provider; deterministic bins vẫn có thể commit |
| `test_cas_rebase` | Confirmed preference cạnh tranh vẫn được giữ; calibration không nhân sample; một rebase, lần fail tiếp báo KNOWLEDGE_CONFLICT |
| `test_response_loss_after_commit` | Lỗi sau store commit; retry trả đúng summary/version từ receipt khi Session cache rỗng |
| `test_budget_reserve_before_network` | Bind schema lỗi không mất slot; timeout mất đúng slot; reused call_id/cạn cap không gọi transport |
| `test_memory_off_night` | Không invocation, snapshot/phase/knowledge writes; summary không báo đã học |
| `test_recovery_without_private_authority` | Lesson ops bị PRIVATE_VALIDATION_UNAVAILABLE; không tái tạo private seed để lách validation |
| `test_typed_policy_and_legacy_text_boundary` | Policy có fact được nhận bằng code template; legacy numeric/ungrounded claims vẫn bị từ chối theo regression HEAD hiện tại |

Chạy `.venv/bin/python -m pytest -q tests/unit/memory tests/unit/infrastructure/test_llm.py tests/unit/agents/test_runner.py tests/integration/agents/test_learning_native.py tests/integration/memory/test_night_publication.py`. Ghi request/source counts từ fake transport. Tiếp tục SI06 trong full-run.
