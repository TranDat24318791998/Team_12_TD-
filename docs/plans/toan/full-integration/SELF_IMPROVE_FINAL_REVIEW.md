# Self-improve final review

What this change does: SI hiện có typed policy compiler, applied-event evidence, durable night publication, policy seed từ ngày kế tiếp và native tool read-back. SQLite cùng Data giữ snapshot/receipt/version/budget; hai đối chứng D/E dùng settlement của simulator, không dùng doanh thu fixture.

Reviewer: Astra max. Ngày 31/10/2026. Reviewed working tree trên HEAD d46c812, gồm các file SI chưa commit; đây không phải review riêng commit d46c812. Phạm vi: SI01–SI07, P05, SI_IMPLEMENTATION_STATUS.md và dependency trực tiếp của SI. Các lane API/DB nền/media/orchestration có reviewer riêng.

**Verdict hiện tại: SELF-IMPROVE PASS trong phạm vi review và recheck này. Finding 1 (P2) đã sửa và kiểm lại; không còn finding P0/P1/P2 mở từ lượt review này.** Luồng demo D/E và các check durable/native trọng tâm dưới đây đạt; các giới hạn coverage T01–T24 bên dưới vẫn được giữ, không đổi thành tuyên bố đã kiểm mọi tổ hợp. Provider recording và provider evaluation vẫn **NOT_RUN**.

## Finding đã xử lý và kiểm lại

1. **[P2 — RESOLVED] Approval hợp lệ có edited_package nhưng action accept bị mất voucher-edit fact** — app/memory/evidence.py:65–76.

   **What this is:** build_skill_facts phải phân biệt package được duyệt với voucher thực sự được seller sửa và duyệt; CORE_CONTRACT mục 2 cho phép cả accept có edited_package khớp applied package.

   **Problem trước fix:** Nhánh đầu đã xác minh edited_package ở dòng 56–59, nhưng nhánh tạo seller_approved_voucher_edit chỉ chạy khi action bằng edit. Fixture chuẩn gồm negotiation_finished seq6 voucher3; card_sent seq8; seller_decision seq10 action=accept, edited_package voucher5; package_applied seq11 đúng toàn bộ edited package chỉ tạo approved_package, thiếu voucher-edit fact.

   **Fix đã kiểm:** Nhánh voucher-edit dùng sự hiện diện của edited_package sau khi kiểm exact package và action accept/edit. Giữ nguyên card trước decision, final agreed package trước card, voucher thực sự thay đổi và seller/apply joins. Mười ca parameterized kiểm accept/edit, thiếu/mismatch edited package, thiếu apply, chỉ sửa ads/không đổi voucher và không mang private sentinel vào facts đều qua.

   **Kết quả recheck độc lập:** Reproduction gốc nay tạo cả approved_package và seller_approved_voucher_edit, đúng sources [6,8,10,11]. Bỏ lần lượt negotiation_finished/card_sent/seller_decision/package_applied đều không tạo voucher-edit fact. Data normalize edit như trước; fix không mở đường học từ approval thiếu package đã áp dụng.

## Kiểm tra thực chạy

Lệnh offline:

    LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q tests/unit/memory/test_skill_evolution.py tests/integration/memory tests/contract tests/unit/infrastructure/test_replay.py tests/integration/agents/test_learning_native.py

Kết quả recheck sau fix: **39 passed in 1.97s** (lượt trước fix: 29 passed). Thêm reproduction độc lập và bốn missing-source checks đều qua. Không gọi paid provider, không mở UI, không sửa source; chỉ cập nhật file review này.

Các bằng chứng đáng kể trong suite:

- test_wire_examples/test_invalid_wire_examples_are_rejected: app DTO parse wire fixtures và reject mẫu sai đã có.
- test_compile_apply_and_artifact_tampering, test_event_join_scope_cutoff_and_approval, test_stage_policy_templates_and_freshness: canonical artifact, ordered source-valued transformations, OFF/future guards, joins và fresh evidence.
- test_native_learning_receives_frozen_facts_as_tool_message: native Learning nhận frozen facts qua ToolMessage thực.
- test_offline_night_publishes_d_plus_one_and_retries và test_evaluation_failure_discards_lessons_and_keeps_history: publication d+1/retry, rollback lesson/policy khi eval fail mà giữ derived history.
- Repository tests trên RAM và SQLite: atomic receipt/copy, reopen, concurrent reflection claim, terminal conflict/unknown recovery, concurrent budget không regrant, rollback transaction và preference confirmation.
- test_reopened_published_skill_changes_next_native_tool_message: reopen Data rồi native Platform nhận và dùng learned seed; OFF không nhận policy đó.
- test_skip_and_publication_choose_one_durable_outcome: skip/publication không cùng thắng.
- Replay tests: typed ID rebind, private/scope/config binding, unknown/opaque IDs và collision fail closed; cache hit không dùng live budget. Không dùng thiếu recording thật làm blocker.

## Đối chiếu hai artifact được chỉ định

Đã đọc exact reports dưới đây và mở growth.db cùng thư mục bằng SQLite mode=ro. Tổng orders/ads/profit tính lại từ daily_metrics source=simulated đúng shop/day1..7 khớp report; không chỉ tin số ghi trong status document.

| Report | Orders ON/OFF | Ads ON/OFF | Profit ON/OFF | Durable/next-use kiểm trực tiếp |
| --- | --- | --- | --- | --- |
| runs/sim-D-8984ae2c0383489faa90fa171f0090f5/comparison.json | 57 / 58 | 270000 / 315000 | 1276752 / 1258888 | ON có 7 NightCommit; OFF có 0 NightCommit và 0 Knowledge records; mỗi arm có 3 pinned attempts |
| runs/sim-E-0a7c0ce93ed84838b0283df696c9c269/comparison.json | 48 / 52 | 97200 / 243000 | 738624 / 662476 | ON có 7 NightCommit; OFF có 0 NightCommit và 0 Knowledge records; mỗi arm có 3 pinned attempts |

Mọi pinned bundle đã đọc có effective_from_day <= attempt.day. OFF luôn version0 và seed.uses rỗng. Report dùng source offline_simulator/offline, budget slots=0, provider_eval NOT_RUN; mô tả tác động tổng hợp của memory và không ép ON phải thắng OFF. Orders ON thấp hơn OFF vẫn được ghi đúng.

Các artifacts được tạo trước lần privacy/replay wiring cuối, như status file đã nói. Lượt review này đối chiếu persisted artifact và chạy focused tests trên working tree mới; chưa chạy lại toàn bộ bốn run bảy ngày ở source cuối. Không đổi nhãn artifacts thành live hoặc provider-evaluated.

## Coverage T01–T24 và giới hạn kết luận

| Cases | Bằng chứng/giới hạn lượt này |
| --- | --- |
| T01–T04, T07 | Đọc allowlist projection, NightSnapshot scope/future validation, proposal pair enums và gateway privacy; join/schema/native tests qua. Không rerun toàn bộ privacy matrix của lane Tools/Knowledge. |
| T05–T06 | Fixture voucher edit/pause tạo đúng ordered seed; persisted E renew có learned policy qua native next-use test. Gap biểu diễn approval của T05 đã được fix và recheck trong finding 1. Chưa có headless UI seller edit; không tuyên bố đã có. |
| T08–T09 | Đọc stage UP/DOWN/EDIT, duplicate refs, stale version và eviction cleanup. Suite SI mới tập trung ADD/freshness; chưa có test riêng đầy đủ policy vote/edit/delete/eviction lifecycle. Status file đã ghi đúng giới hạn này; cần bổ sung trước khi đánh dấu từng acceptance này PASS. |
| T10–T12 | Daily raw calibration/window test qua; D/E đủ bảy ngày persisted. Đã đọc rebase/current-record merge; chưa chạy mọi conflict permutation. |
| T13–T14 | OFF và d+1 có test + artifact; graph nhận cùng pinned context. Chưa có test riêng publish version mới ngay giữa hai model rounds của cùng attempt. |
| T15–T18 | RAM/SQLite atomic/reopen/concurrent claim/budget/unknown/rollback/skip-publication tests qua; candidate-eval fail giữ history qua. Không mô phỏng mọi điểm process-kill. |
| T19 | Fixture semantic replay + fail-closed tests qua; actual provider recording NOT_RUN, không phải implementation blocker khi không trả nhầm live/replay. |
| T20–T22 | Seed là proposal data, không có Rules/apply side effect; native reopened next-use và budget tests qua. Seller/media gates có review riêng. |
| T23–T24 | D/E offline artifact và SI fallback/candidate-failure tests qua. Full golden A–E sau tích hợp và full-suite run cuối do root/lane tương ứng xác nhận; không tuyên bố đã chạy ở đây. |

Các test còn thiếu ở T08/T09/T14 là acceptance chưa được xác minh, không phải bằng chứng một lỗi runtime khác. Không nâng chúng thành P1 bằng giả định về distributed load hoặc framework ngoài demo.

## Nhận xét về invariant chính

- Night đọc durable NightCommit trước cache; freeze/claim/terminal receipt tách khỏi transaction publication. Native model chỉ nhận T08 projection. Publication dùng cùng Data transaction qua injected publish; repository kiểm same-key/hash, CAS, parent/base/cutoff và append versions.
- Stage raw proposal text qua privacy rồi thay bằng canonical templates; model không sinh code, tiền tùy ý, effective day, hashes hoặc Rules. Legacy lesson vẫn giữ gate định tính.
- Pinned context chứa bundle/seed/base text, được lưu trên negotiation; native read_memory và fallback dùng cùng seed. Accept counteroffer không lấy seed để thay package đang accept.
- Replay không tự gọi live khi miss. Source replay chỉ sau lookup hợp lệ; unavailable recording/provider evaluation được ghi NOT_RUN. Đây là giới hạn bằng chứng, không yêu cầu paid smoke để hoàn tất review code.

Not checked: paid LLM/image/video/evaluator, actual provider recording, browser UI, toàn bộ phần khác ngoài SI, full-suite và rerun D/E sau patch cuối. Chỉ tạo file review này; không sửa implementation hoặc artifacts.
