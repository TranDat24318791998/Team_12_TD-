# SI07 — Nối adapter, replay và proof headless

Phụ thuộc SI06. Xong khi improve core chạy liên tục qua RAM, replay đúng scope, đối chứng headless 7 ngày đo từ settlement, và status DB phản ánh adapter được cung cấp. Thiếu adapter DB không ngăn hoàn tất core hoặc được ghi thành lỗi thiết kế.

## Đọc và Output

Đọc [DB_HANDOFF](DB_HANDOFF.md), [REPLAY_PROOF_CONTRACT](REPLAY_PROOF_CONTRACT.md), `runtime/session.py`, `manager.py`, `day.py`, `simulation/`, `data/growth_data/simulation.py`, fixtures market/content và [TEAM_INTEGRATION](../TEAM_INTEGRATION.md) để giữ ranh giới facade/UI.

Output: thêm `app/infrastructure/replay.py`; mở rộng `llm.py`, `runtime/session.py`, `manager.py`, `day.py`; implement `simulation/market.py`, `runner.py`, mới `simulation/content.py`; `domain/models/metrics.py` thêm RunResult, mới `domain/models/replay.py`; `scripts/run_sim.py`; `tests/fakes/market.py`, `tests/contract/`, `tests/unit/infrastructure/test_replay.py`, `tests/integration/memory/test_recovery.py`, `tests/integration/simulation/test_proof.py`; cập nhật `docs/CONTRACT.md`, `docs/plans/toan/{KNOWLEDGE_CONTRACT,AGENT_TOOL_KNOWLEDGE,TEAM_INTEGRATION,DEMO_RUNBOOK,CODEX_LOG}.md` cho interface đã thực hiện. Reports/caches vào runs/ gitignored. Không sửa DB engine, frontend, API facade hoặc media provider.

## Các bước thực hiện tuần tự

1. Dependency injection: Session.new optional store_factory(run_id), direct store ưu tiên, RAM mặc định; manager/script nhận factory. Contract tests dùng cùng suite với member DB factory nếu có. Không dùng tên class SQL tự đoán hoặc tự tạo migration.
2. Replay schema/key/rebinding theo contract. Kiểm role/shop/visibility/config; hit trước budget reserve. Miss ở replay chạy fallback, không gọi live. ID normalization chỉ qua map typed fields/backend-issued; private Shop cache không được public export. Unit tests thay ID run vẫn hit khi business context giống, đổi memory/policy/evidence phải miss.
3. Market adapter dùng Data pure engine hiện có. Map public/private DTO trong backend, forecast/actual dùng cùng engine. record_daily_prediction sau monitor/content và trước settlement; snapshot một ngày, chưa biết actual; retry không chụp lại hoặc giảm stock lần hai. Không thay Data API.
4. Headless content dùng Content Agent text và file ảnh gốc hợp lệ, video skip rõ nguồn; không gọi image/video provider. SellerSimulator theo fixed policy của contract. Runner đi qua runtime confirm/start/decision/content/close hiện có, không viết lại state machine trong script.
5. run/compare trả RunResult/ProofReport, báo ON/OFF cùng seed/config/horizon và independent stores. CLI mặc định offline/7 ngày/D; hỗ trợ `--days`, `--shop`, `--seed`, `--mode offline|replay|live`, `--replay-manifest PATH`, `--store-factory module:callable`. factory do operator cấu hình, không có credential trong CLI/report. Mặc định không có live calls dù máy có key.
6. Update docs caller/schema đã nối và mapping acceptance→test. Báo core PASS/FAIL, durable PASS/NOT_CONNECTED/FAIL, provider_eval NOT_RUN/PASS/FAIL riêng; không dùng một trạng thái PASS để che phần chưa chạy.

## Acceptance

| Test/fixture | Expected |
| --- | --- |
| `test_repository_contract` | Suite RAM đầy đủ; nếu supplied DB thì cùng suite + reopen data/phase/budget |
| `test_recovery_no_provider_resend` | Store reopened có completed output thì reuse; reserved của process cũ → unknown; không gửi invocation mới |
| `test_semantic_replay_new_run` | Known IDs rebind về run mới; không trả fact/card của source run; unknown token miss |
| `test_replay_scope_and_configuration` | Cross-shop/private export, khác model/tools/base/evidence/memory flag không hit |
| `test_replay_before_live_budget` | Hit và miss offline dùng 0 live slots; live chỉ reserve khi thực sự đi tới transport |
| `test_daily_prediction_before_actual` | Gói3 ngày raw 45, daily 15, actual 10 → ratio 2/3; không lấy10/45 hoặc issued calibrated forecast |
| `test_settlement_retry` | Retry close_day không trừ stock/ghi sample/vote lần hai; snapshots giữ đúng effective package sau pause |
| `test_offline_seven_days` | D hoàn tất7 ngày bằng Data engine và runtime thật; source simulator/offline đúng, không FakeMarket trong proof |
| `test_proof_reproducible_and_measured` | Cùng seed/config tái tạo metrics; compare tính tổng/MAE từ rows; ON thua OFF vẫn là kết quả hợp lệ |
| `test_off_no_learning_or_provider` | OFF không reflection/learned write, replay không rò ON decisions, Rules/stop vẫn enforce |
| `test_public_report_is_sanitized` | Không cost/persona/rules/private notes; report thể hiện invalid artifacts/budget/source/eval/durable status |
| `test_compatibility` | Full suite cũ qua; các facade/UI khác lane không bị thay signature |

Lệnh sau khi implement:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_sim.py --days 7 --shop D --seed 42 --mode offline
.venv/bin/python scripts/run_sim.py --days 7 --shop E --seed 42 --mode offline
```

D là demo chính, E kiểm pause/renew nhiều ngày. Voucher edit được kiểm bằng integration fixture vì core API hiện chưa hỗ trợ edit. Không tự chạy live mode để hoàn thành task; provider quality chưa được evaluator so sánh thì báo NOT_RUN. Bàn giao paths report/artifact, hashes, tests thực chạy, rejected reasons và status adapter. Chưa có DB vẫn giao full core; chỉ durability chờ factory ngoài.
