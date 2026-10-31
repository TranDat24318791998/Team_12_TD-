# D03 — Điều phối ngày, seller approval và đầu nối API

Timebox 18 phút cho runtime và ghép nối, API owner làm route song song. Cần D01/D02a/D02/D04; nếu content/memory chưa xong, dùng fake đúng interface. Đọc [DEMO_CONTRACT](../../docs/DEMO_CONTRACT.md), mục 3, 5 và 6. Toàn sở hữu runtime; member API sở hữu route/wiring, cùng một integrator duyệt Session. Tách patch theo hai owner trong Output, không ghi cùng file đồng thời.

## Output

**Toàn:** `app/runtime/day.py`, runtime tests và runtime fixtures. **API integrator:** `app/runtime/{manager,session}.py`, `app/api/{schemas,dependencies,router}.py`, `app/api/routes/{sessions,days,content,events,proof}.py`, `app/main.py`, `contracts/{state_awaiting,state_content,decision,content_apply,night}.json`, `tests/fakes/{content,memory}.py`, `tests/integration/runtime/test_day.py`, `tests/integration/api/test_demo_flow.py`, `docs/CODEX_LOG.md`.

## Wiring

Lifespan tạo SessionManager, pool tối đa 4 worker và các factory cho LLMClient, ContentService, MemoryGateway. `get_session(request)` trả `app.state.manager.current`; nếu chưa có run thì tạo run mới. Router không giữ Session global. Manager truyền executor vào ContentService; Session không cần field executor riêng.

StateView chỉ serialize các field cho phép. Seller UI xem được thông tin riêng của D; browser không được truyền token/role để chọn shop khác. `StateView.busy` là projection của `Session.phase_busy`, không tạo thêm cờ busy trong Session.

```python
confirm_brief(session, request) -> IntentBrief
start_day(session) -> None
submit_decision(session, decision: SellerDecision) -> str
apply_reviewed_content(session, card_id, brief_version, draft_version, cover_option, skip_video=False) -> ShopPublic
close_day(session, expected_day: int) -> dict
activate_approved_package(session, card: Card) -> ActivePackage
```

Route chỉ validate request → gọi service → serialize response. Logic thuộc day/content/night. Agent và referee không gọi trực tiếp `activate_approved_package`.

## 1. Xác nhận brief

Ở idle, tạo brief version 1, confirmed=True. P0 chỉ nhận increase_orders, allow_ads=True, content_refresh=True, duration_days=3; ngoài phạm vi trả 422 DEMO_BRIEF_UNSUPPORTED. Public budget cho phép null; không tự điền hard cap riêng 45.000đ vào brief.

Ghi intent_confirmed, chuyển brief_confirmed. State không hợp lệ trả 409. Demo sửa brief bằng reset; ngày 2 giữ brief confirmed, không hỏi xác nhận lại.

## 2. Bắt đầu ngày

```text
under lock: verify not phase_busy, allowed step, brief confirmed; set phase_busy = True
try:
  expired_ids = monitor_active_packages(session)  # chạy trước mọi kế hoạch/chi trong ngày
  opportunities = match_opportunities(session)  # ghi lý do selected/rejected A–E
  if D.active and memory has pending question:
      build question Card(package=None); step = awaiting_decision
  elif D.active:
      read memory; step = day_done  # không gia hạn khi gói còn hạn
  else:
      nếu D bị loại/cooldown: ghi lý do, step=day_done, không gọi graph
      step = negotiating; run_negotiation(D, day, kind=renew if D in expired_ids else propose) nếu D eligible
      agreed/warning_only -> build Card with valid package, forecast, brief_version
      failed/ask_human -> step = brief_confirmed; emit safe reason; no Card/approval
finally: clear phase_busy under lock
```

Card ID gồm run/day/attempt; mỗi ID mới bắt đầu version 1. Financial display chỉ nằm trong seller projection; break-even hiển thị theo quy tắc làm tròn của contract. `run_negotiation` không tạo ActivePackage. Ghi card_sent đúng một lần sau khi tạo card.

## 3. Quyết định của seller

Kiểm tra card ID/version, brief version và state trước side effect. phase_busy=True trả 409.

- Offer accept: ghi seller_decision, lưu approved_card_id. Có content thì start service, chuyển content_review; active vẫn None. Nhánh không content gọi activate rồi chuyển day_done; nhánh này không thuộc brief P0 cần demo.
- Offer negotiate: chỉ nhận note `Giảm voucher còn 2%`. Vô hiệu hóa card cũ, tăng attempt, gọi graph với owner_note. Card mới cần approval mới. Tối đa một lần; vượt giới hạn trả lỗi rõ theo contract.
- Offer reject: đặt cooldown_until=day+3, không tạo content/active mới; pending_card=None, step=day_done.
- Question-only: rule_answer phải khớp action. Gọi T10 confirm_preference workflow → memory.answer_pref cho đúng pending preference; LLM không được tự gọi. Có lấy field/value từ pending RuleQuestion (D style, A voucher trong headless fixture), validate theo KNOWLEDGE_CONTRACT và tăng rules_version một lần; Không đánh dấu declined. Chuyển day_done, giữ gói active.

Card question có package=None; không đọc card.package.ads_daily_budget. Agent agreed chưa phải seller accept.

## 4. Retry, apply và kích hoạt gói

Retry/apply đều cần card_id, expected_brief_version, expected_draft_version vì draft version 1 có thể lặp ở nhiều card. Retry chỉ ở content_review và đúng approved card; service tạo v2/v3, v4 trả 409.

Apply chạy trong một critical section ngắn, không gọi mạng:

1. Tra receipt theo card/draft trước. Request trùng hoàn toàn trả kết quả cũ; cùng receipt nhưng khác payload trả 409. Chưa có receipt thì validate card/brief/draft và approved_card_id.
2. Kiểm cover được chọn ready, video ready hoặc seller chủ động skip; chạy lại final check.
3. Chuẩn bị listing, ActivePackage và forecast snapshots đã validate trong biến local. Kiểm xong trước khi thay Session.
4. `ContentService.apply(D, cover_option, skip_video=...)` lưu listing; helper activate lưu gói trong cùng lock. Không gọi provider tại đây.
5. Active.start_day=day, end_day=day+duration−1, ads_paused=False; cập nhật voucher public.
6. Lưu receipt/events; xóa content_draft, pending_card, approved_card_id; chuyển day_done. Listing public và receipt giữ bản đã chốt cho UI.

`activate_approved_package` dùng `market.build_forecast_snapshots(shop, pkg, start_day, seed, calibration) -> list[ForecastSnapshot]` do member market cung cấp; D04 kiểm cùng-horizon contract. Helper trả raw/issued riêng cho từng ngày trước khi có outcome. Lưu từng snapshot vào `session.forecast_snapshots[(card.shop_id, snapshot.target_day)]` trước mọi settlement. Snapshot tạo một lần, gắn approved card; receipt apply trùng không tạo lại. `forecast_package` chỉ tính, không ghi Session/global state. Market chưa xong thì fake đúng helper này trong tests; báo integration pending, không tạo metric thắng giả.

ContentService sở hữu event content_applied; runtime sở hữu package_applied. Route không ghi lặp. Callback sau publish thấy draft None thì bỏ qua, không sửa listing đã chốt.

## 5. Kết thúc ngày và polling

`close_day` tra night_receipts[expected_day] trước khi validate current day. Có receipt thì trả lại; chưa có thì yêu cầu day_done, phase_busy=False, content_draft=None.

Đặt phase_busy=True, simulate_day đúng một lần rồi run_night xử lý evidence. Lưu receipt gồm summary/next_day. Cuối ngày 1 chuyển ngày 2, step idle, giữ brief confirmed; cuối ngày 2 chuyển complete. finally luôn xóa phase_busy. Learning lỗi thì ghi failure, giữ day_done để retry riêng learning; settled_days chống settlement lần hai. Không trả summary rỗng như thể đã học thành công.

GET /api/events?after=N trả stream dành cho seller D; last_seq là cursor đã đọc. UI reset cursor khi run_id đổi. GET state chỉ đọc, không tạo job/auto apply. GET proof trả 409 PROOF_NOT_READY khi chưa có đối chứng thật.

## Fixtures

JSON fixtures phải qua HTTP model validation. Ví dụ decision:

```json
{"card_id":"D-1-attempt1","expected_card_version":1,"expected_brief_version":1,"action":"accept","rule_answer":null}
```

Ví dụ apply:

```json
{"card_id":"D-1-attempt1","expected_brief_version":1,"expected_draft_version":2,"cover_option":"B","skip_video":false}
```

ID trên chỉ dành cho fixture; ID thực do server cấp. JavaScript đọc state, không hardcode ID.

## Test cần qua

1. Reset → brief → start tạo thẻ D 45.000đ/ngày, voucher 3%, stop 6,5; event trọng tài đến từ lời gọi thật trong graph.
2. Accept → content_review, active None; fake media done → apply → active, cover B; draft/card/approval đã xóa.
3. Retry tạo v2; apply v1/card cũ trả 409; callback v1 không ghi đè v2. Ghép test provider của D05.
4. Apply trùng không thêm package_applied, không đổi start_day/tạo lại snapshots. Night ngày 1 trùng không trừ stock/tăng ngày lần hai.
5. Reject không submit content; question Không không hủy gói active.
6. Graph failed xóa phase_busy và thoát negotiating; UI có thể reset. Malformed request trả 422.
7. Activation lưu đủ forecast theo ngày trước settlement; helper dự báo thuần không tự sửa Session.

Chạy `.venv/bin/python -m pytest -q tests/integration/runtime tests/integration/api`. Handoff phải nêu factory/fixture nào còn fake; endpoint trả JSON hardcode thay service chưa đạt yêu cầu.


## 6. Phần điều phối gốc phải giữ, không chuyển thành việc UI

```python
monitor_active_packages(session) -> list[str]  # shop IDs vừa hết hạn hôm nay
match_opportunities(session) -> list[str]      # eligible shop IDs, ghi event lý do
```

Hai helper dùng shop_id tổng quát, chỉ start_day chọn D cho tương tác. Không mở fan-out API hoặc nhiều pending cards trong slice này.

- Monitor trước match/negotiation: `day > active.end_day` thì clear active, đặt public.active_voucher_pct=0, ghi auto_action và đưa shop vào candidates renew. Renew tạo offer/card mới, không tự gia hạn/chi thêm.
- Active ads đủ `stop_after_days` ngày settle liên tiếp có spend>0, ROAS hữu hạn thấp hơn threshold → ads_paused=True trước spend ngày mới. Ngày thiếu metrics hoặc spend0 không tính là một ngày ROAS thấp. Ads đã paused không phát event lặp.
- Inventory guard: lấy trung bình orders từ tối đa3 ngày metrics đã settle gần nhất (có ít hơn thì dùng số ngày hiện có), stock < 3×trung bình và trung bình>0 → pause. Không đủ sample thì không suy diễn tồn kho theo Persona.
- Match: ngành có trend tăng trong ngày, không active/cooldown, stock>=30, listing_quality<0.6 hoặc search_rank_page>=2. Record lý do C stock15 bị loại; seed A–E chỉ fixture, UI không cần hiện5shop.
- Cooldown `day < cooldown_until` bị loại; đến ngày bằng cooldown thì đủ điều kiện xét lại. Reject đặt day+3. Renew vẫn qua match và seller approval.
- Sau confirm preference ngày2, next-use test gọi cùng tools/content context một invocation mới; không tự apply campaign mới hoặc tạo thêm video trả phí để chứng minh memory.

Tests bổ sung: E hai ngày metric ROAS thấp→pause sáng ngày3 trước simulator; expired active→renew chưa active khi chưa approve; C không gọi graph; A voucher confirmation chỉ đổi đúng field/value pending; D vẫn đủ luồng chính. Đây là test điều phối với fixture, không phải proof6ngày.

Bàn giao cho API/media: typed methods + JSON fixtures và trace từ runtime thật. Route mock chỉ dùng phát triển UI; không tính vào CORE PASS. Member UI chưa sẵn sàng thì D06 headless gọi đúng methods này, không viết workflow thứ hai trong script.

`package_applied` và `market_result.data` giữ card_id/negotiation_id/prediction_id thật. D03 join từ approved card/history để learning ngày2 liên kết campaign ngày1 dù không có negotiation mới. Market trả DayMetrics chưa có refs thì runtime thêm refs trước append_event, không yêu cầu model tự suy luận ID.
