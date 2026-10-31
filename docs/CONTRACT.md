# Hợp đồng chung

Cả team chốt file này lúc 10:30 ngày thi. Sau đó chỉ đổi khi cả team đồng ý; ai đổi thì báo trong nhóm chat và sửa luôn JSON mẫu trong `contracts/`.

Quy ước: tiền là số nguyên VND; phần trăm là số nguyên (`voucher_pct = 3` nghĩa là 3%); ROAS là số thực; ngày mô phỏng bắt đầu từ 1.

## 1. Model dữ liệu (`app/domain/models/`)

Model chia theo file; đường dẫn đầy đủ và hướng phụ thuộc ở `docs/ARCHITECTURE.md`:

| Module | Model |
| --- | --- |
| `shops.py` | ShopPublic, ShopRules, ShopPrivate, SellerPersona, FeeConfig |
| `packages.py` | Package, ActivePackage |
| `negotiation.py` | PlatformTurn, ShopTurn, Violation, NegotiationResult |
| `cards.py` | RuleQuestion, Card, SellerDecision |
| `content.py` | CoverImage, VideoJob, ContentDraft; ContentText của task 4.2 |
| `learning.py` | Calibration, LessonOp, NightSummary |
| `metrics.py` | Forecast, DayMetrics, ProofMetric, ProofReport |
| `events.py` | Event |

`StateView` và request/response HTTP đặt ở `app/api/schemas.py`, tái sử dụng các model này. `vnd` và `dec` nằm trong `app/domain/formatting.py`.

### Shop

| Model | Trường | Ghi chú |
| --- | --- | --- |
| `ShopPublic` | `shop_id`, `name`, `category`, `price`, `stock`, `listing_quality` (0–1), `search_rank_page`, `rating`, `base_impressions`, `title`, `description`, `attributes: list[str]`, `images: list[str]` (đường dẫn), `video: str \| None`, `active_voucher_pct: int` | Ai cũng được đọc |
| `ShopRules` | `allow_ads`, `ads_daily_max`, `voucher_max_pct`, `min_profit_per_unit`, `max_breakeven_roas` (mặc định 6.5), `require_stop_condition` (mặc định True), `content_style_notes: list[str]` | Luật của chủ shop; chỉ đổi khi người bán xác nhận |
| `ShopPrivate` | `owner_name`, `unit_cost`, `rules: ShopRules` | Chỉ agent shop và validators phía shop được đọc |
| `SellerPersona` | `shop_id`, `hidden_voucher_comfort_pct: int \| None`, `content_style_pref: str \| None`, `accepts_ads: bool` | Chỉ người bán giả lập dùng; không agent nào đọc |
| `FeeConfig` | `fixed_pct`, `transaction_pct`, `tax_pct`, `per_order` | Giả định phí sàn, xem SEED_DATA.md |

### Gói và thương lượng

| Model | Trường |
| --- | --- |
| `Package` | `content_refresh: bool`, `ads_daily_budget: int` (0 = không chạy), `voucher_pct: int`, `stop_roas_below: float \| None`, `stop_after_days: int = 2`, `duration_days: int` |
| `PlatformTurn` | `action: "propose" \| "accept" \| "withdraw"`, `package: Package \| None`, `message_vi: str` |
| `ShopTurn` | `action: "accept" \| "counter" \| "reject"`, `package: Package \| None`, `message_vi: str` (gửi cho sàn, đã qua leak_guard), `private_note_vi: str` (chỉ hiện ở hậu trường, không bao giờ gửi cho agent sàn) |
| `Violation` | `code`, `side: "platform" \| "shop" \| "final"`, `field`, `message_vi` |
| `Forecast` | `low`, `point`, `high` (số đơn trong cả thời hạn gói), `factor_used: float`, `stock_warning: bool` |
| `NegotiationResult` | `negotiation_id` (vd `D-1`), `shop_id`, `day`, `kind: "propose" \| "renew"`, `status: "agreed" \| "failed" \| "warning_only"`, `rounds: int`, `final_package: Package \| None`, `forecast: Forecast \| None`, `warning_vi: str \| None` |

### Thẻ và quyết định

| Model | Trường |
| --- | --- |
| `RuleQuestion` | `pref_id`, `field: "voucher_max_pct" \| "content_style"`, `value: str`, `text_vi` (vd "Lần sau tạo ảnh nền sáng ngay từ đầu?") |
| `Card` | `card_id`, `shop_id`, `day`, `kind: "offer" \| "question"` (thẻ chỉ hỏi xác nhận luật, dùng khi shop đang chạy gói nên không có đề xuất mới), `package: Package \| None` (None khi `kind = "question"`), `forecast: Forecast \| None`, `profit_after_fees_per_unit: int \| None`, `breakeven_roas_display: float \| None` (đã làm tròn lên 0,5; None khi không có quảng cáo hoặc thẻ câu hỏi), `reasons_vi: list[str]`, `warnings_vi: list[str]`, `notices_vi: list[str]`, `rule_question: RuleQuestion \| None` |
| `SellerDecision` | `card_id`, `action: "accept" \| "negotiate" \| "reject" \| "edit"`, `note_vi: str = ""`, `edited_package: Package \| None`, `rule_answer: bool \| None` |
| `ActivePackage` | `package`, `start_day`, `end_day`, `ads_paused: bool`, `card_id` |

### Nội dung

| Model | Trường |
| --- | --- |
| `CoverImage` | `option: "A" \| "B" \| "C"`, `status: "running" \| "done" \| "failed" \| "cached"`, `path: str \| None`, `prompt: str` |
| `VideoJob` | `status: "pending" \| "running" \| "done" \| "failed" \| "cached"`, `path: str \| None`, `job_id: str \| None`, `prompt: str`, `error: str \| None` |
| `ContentDraft` | `shop_id`, `version: int` (1–3), `title`, `description`, `images: list[CoverImage]`, `video: VideoJob`, `feedback_history: list[str]`, `style_notes: list[str]` (luật phong cách của chủ shop + góp ý đã dùng để tạo bản này), `checks: list[str]` |

### Kết quả và học

| Model | Trường |
| --- | --- |
| `DayMetrics` | `shop_id`, `day`, `impressions`, `clicks`, `orders`, `revenue`, `ads_spend`, `roas: float \| None`, `fees`, `profit_after_fees` |
| `Calibration` | `category`, `ratios: list[float]` (tối đa 30), `factor`, `q_low`, `q_high` |
| `LessonOp` | `op: "ADD" \| "UPVOTE" \| "DOWNVOTE" \| "EDIT"`, `lesson_id: str \| None`, `text_vi: str`, `scope: "strategy" \| str` (ngành), `evidence: list[str]` (mã thương lượng) |
| `NightSummary` | `day`, `history_updates: list[str]`, `pref_candidates: list[str]`, `calibration: {factor, points, mape_today}`, `lesson_ops: list[LessonOp]`, `rejected_ops: int`, `memory_md_path` |
| `ProofMetric` | `key`, `label_vi`, `better: "higher" \| "lower"`, `on: float`, `off: float`, `unit: "%" \| "đ" \| ""` |
| `ProofReport` | `seed`, `days`, `run_on`, `run_off`, `metrics: list[ProofMetric]`, `note_vi` |

### Sự kiện

`Event`: `seq: int` (tăng dần trong một run), `run_id`, `day`, `ts: "HH:MM"` (giờ máy), `type`, `actor`, `shop_id: str | None`, `text_vi`, `data: dict`.

## 2. Loại sự kiện

Mỗi dòng ở khung hậu trường là một sự kiện. `text_vi` là câu hiển thị nguyên văn; `data` là chi tiết cho giao diện.

| `type` | `actor` | Ai ghi | `data` |
| --- | --- | --- | --- |
| `day_start` | `system` | 1.6 | `{day}` |
| `opportunity` | `platform_agent` | 1.6 | `{keyword, growth_7d_pct, chosen: [shop_id], excluded: [{shop_id, reason_vi}]}` |
| `memory_read` | `memory` | 2.4 | `{who: "platform" \| "shop", items: [str]}` |
| `platform_turn` | `platform_agent` | 1.5 | `{negotiation_id, round, action, package}` |
| `shop_turn` | `shop_agent` | 1.5 | `{negotiation_id, round, action, package, private_note_vi, redacted: bool}` |
| `code_check` | `code` | 1.5 | `{negotiation_id, ok: bool, checks: [{ok, message_vi}]}` |
| `card_sent` | `system` | 1.6 | `{card}` |
| `seller_decision` | `seller` | 1.6 | `{card_id, action, note_vi, rule_answer}` |
| `auto_action` | `system` | 1.6 | `{action: "pause_ads" \| "end_package", reason_vi}` |
| `content_job` | `content_agent` | 4.5 | `{kind: "text" \| "image" \| "video", status, version, detail_vi}` |
| `content_applied` | `system` | 4.5 | `{version, cover_option}` |
| `market_result` | `market` | 2.3 | `{metrics: DayMetrics}` |
| `memory_write` | `memory` | 2.5 | `{compartment, summary_vi}` |
| `night_summary` | `memory` | 2.5 | `{summary: NightSummary}` |

## 3. API (`app/api/routes/`)

`app/api/router.py` ghép router dưới `/api`. Chia file: `sessions.py` (reset/state), `days.py` (day/start, decision, night), `events.py`, `content.py` (retry/apply), `proof.py`. `/health` nằm riêng ở `health.py`. Mock scenario ở `app/api/mock.py`, lấy phiên qua `app/api/dependencies.py`.

Mọi API trả JSON. Lỗi trả `{"error": {"code", "message_vi"}}` với mã HTTP phù hợp. JSON mẫu của từng API nằm ở `contracts/<tên>.json`.

| API | Gửi | Trả về |
| --- | --- | --- |
| `POST /api/reset` | `{"memory": true, "seed": 42}` (đều tuỳ chọn) | `{run_id, day: 1, mode, state}` |
| `GET /api/state` | — | `StateView` (bên dưới) |
| `POST /api/day/start` | — | `{day, step}`; agent chạy nền, sự kiện xuất hiện dần |
| `GET /api/events?after=<seq>` | — | `{events: [Event], last_seq}` |
| `POST /api/decision` | `{card_id, action, note_vi?, rule_answer?}` | `{step, card?}` |
| `POST /api/content/retry` | `{feedback_vi}` | `{draft: ContentDraft}`; chữ và ảnh mới ngay, video `status = running` |
| `POST /api/content/apply` | `{cover_option: "A" \| "B" \| "C"}` | `{listing: ShopPublic}` |
| `POST /api/night` | — | `{summary: NightSummary, next_day}`; chạy thị trường hết ngày rồi học ban đêm |
| `GET /api/proof` | — | `ProofReport` |

`StateView`: `{run_id, day, mode: "live" | "replay" | "offline", memory_enabled, step, demo_shop: ShopPublic, demo_shop_original: ShopPublic, active_package: ActivePackage | null, pending_card: Card | null, content_draft: ContentDraft | null, last_night: NightSummary | null, live_calls_left}`.

`POST /api/content/retry` trả về ngay: chữ mới đã có, ảnh và video ở trạng thái `running`; giao diện gọi lại `GET /api/state` mỗi 3 giây cho tới khi xong. Lần đầu nội dung được tạo tự động khi người bán bấm Đồng ý một gói có làm mới nội dung.

`step` là một trong: `idle` → `negotiating` → `awaiting_decision` → `content_review` → `day_done` → `night_done`. Giao diện dựa vào `step` để biết hiện nút nào.

File tĩnh: `/` → `frontend/index.html`; `/media/...` → thư mục `media/`.

## 4. Giao diện giữa các module Python

Ai viết module nào giữ đúng chữ ký dưới đây; bên trong tự do. Các alias trong bảng chữ ký tương ứng với import sau (đường dẫn cập nhật theo yêu cầu tổ chức codebase ngày 31/10/2026):

```python
from app.simulation import world as data, market, runner as simulation
from app.runtime import session, day
from app.domain import finance, validators, privacy
from app.infrastructure import llm, eventlog
from app.negotiation import agents, graph as negotiation
from app.memory import gateway as memory, night
from app.content import service as content_service
```

URL, JSON và chữ ký hàm được giữ nguyên; phần đổi là vị trí module.

```
data.load_world(path="data/seed.json") -> World          # World: shops (public, private, persona), trend, calendar, fees
session.Session.new(settings, memory_enabled=True) -> Session
finance.profit_per_unit(shop, priv, voucher_pct, fees) -> int
finance.breakeven_roas(shop, priv, voucher_pct, fees) -> float     # inf nếu lãi <= 0
finance.stop_threshold(breakeven) -> float                         # làm tròn lên bội số 0.5
finance.max_voucher_for(shop, priv, ads_enabled, fees) -> int
finance.loss_warning(shop, priv, fees) -> str | None
validators.platform_side_check(pkg, shop) -> list[Violation]
validators.shop_side_check(pkg, shop, priv, fees) -> list[Violation]
validators.clamp_to_platform(pkg, shop, package_days) -> Package | None
validators.clamp_to_rules(pkg, shop, priv, fees) -> Package | None
privacy.leak_guard(text, shop, priv, fees) -> tuple[str, bool]
llm.LLMClient(settings).structured(schema, system, user, *, run_name) -> tuple[obj | None, str | None]
agents.decide_platform(session, shop_id, turns, memory_view) -> PlatformTurn
agents.decide_shop(session, shop_id, proposal, memory_view, owner_note) -> ShopTurn
negotiation.run_negotiation(session, shop_id, day, kind, owner_note=None) -> NegotiationResult
day.start_day(session) -> None                     # chạy tới khi cần người bán quyết định
day.submit_decision(session, decision) -> str      # trả step mới
market.forecast_package(shop, pkg, day, seed, calibration) -> Forecast
market.simulate_day(session, day) -> dict[str, DayMetrics]
market.SellerSimulator.decide(card, persona) -> SellerDecision
market.SellerSimulator.content_feedback(draft, persona) -> str | None
memory.MemoryGateway(store, enabled).platform_view(shop_id, category) -> dict
memory.MemoryGateway(store, enabled).shop_view(shop_id) -> dict
eventlog.EventLog(db_path).add(run_id, day, type, actor, shop_id, text_vi, data) -> Event
eventlog.EventLog(db_path).since(run_id, after_seq) -> list[Event]
night.run_night(session, day) -> NightSummary
content_service.ContentService(session).start(shop_id) -> ContentDraft
content_service.ContentService(session).retry(shop_id, feedback_vi) -> ContentDraft
content_service.ContentService(session).apply(shop_id, cover_option) -> ShopPublic
simulation.run(settings, days, memory_enabled, seed) -> RunResult
simulation.compare(run_on, run_off) -> ProofReport
```

`Session` (`app/runtime/session.py`) giữ: `run_id`, `settings`, `world`, `states: dict[shop_id, ShopState]`, `day`, `step`, `interactive: bool` (True khi giám khảo bấm, False khi `simulation.run`), `memory`, `log`, `llm`, `content`, `pending_card`, `last_night`, `live_calls_left`. `ShopState` giữ: `public`, `private`, `persona`, `active: ActivePackage | None`, `cooldown_until`, `metrics: dict[int, DayMetrics]`.

Giám khảo chỉ điều khiển shop `DEMO_SHOP` (mặc định D). Các shop khác do `SellerSimulator` quyết định tự động.
