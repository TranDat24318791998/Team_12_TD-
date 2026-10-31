# D04 — Kết quả ngày, learning và xác nhận phong cách

Timebox: **10 phút**. Phụ thuộc D01 và D03; đọc DEMO_CONTRACT mục 6. Mục tiêu là một vòng evidence → candidate → seller confirmation → shop_view. Chưa triển khai proof đầy đủ.

## Output

`app/simulation/market.py`, `app/memory/{gateway,night,prompts}.py`, `tests/unit/memory/test_gateway.py`, `tests/integration/memory/test_night.py`, `tests/unit/simulation/test_market.py`, `docs/CODEX_LOG.md`.

## Interface

```text
build_forecast_snapshots(shop, pkg, start_day, seed, calibration) -> list[ForecastSnapshot]
forecast_package(shop, pkg, day, seed, calibration) -> Forecast
simulate_day(session, day) -> dict[str, DayMetrics]  # P0 chỉ shop D
MemoryGateway(store, enabled, log=None, run_id=None, session=None)
  platform_view(shop_id, category) -> dict
  shop_view(shop_id) -> dict
  get_rules(shop_id) -> ShopRules
  get_history(shop_id) -> list[dict]
  save_history(shop_id, history) -> None
  get_calibration(category) -> Calibration
  save_calibration(category, calibration) -> None
  prefs_to_ask(shop_id, day) -> list[Preference]
  mark_asked(pref_id, day) -> None
  answer_pref(pref_id, yes, day) -> None
run_night(session, day) -> NightSummary
```

Gateway đọc/ghi learned records; rules được đọc hoặc cập nhật qua Session. `save_history` lưu cả list public history của shop; caller phải loại bản ghi trùng trước khi lưu. Calibration chưa có thì trả mặc định factor=1 với ratios rỗng. `answer_pref` chỉ được runtime gọi sau khi kiểm đúng question card/version; không expose thành tool cho LLM. Export Markdown là phần tùy chọn cuối task, chưa đầu tư định dạng.

## 1. Forecast và actual phải cùng kỳ

Forecast daily dùng công thức market trong data design mục 7.3:

- Impressions = base impressions × trend × (0,5 + quality) × noise.
- CTR = 0,015 + 0,02 × quality.
- CVR = 0,03 + 0,03 × quality + 0,002 × voucher; cap ở 1.
- Paid clicks = floor(budget / 1.800); ads spend = paid clicks × 1.800.
- Phân bổ stock cho organic trước, paid sau.
- Dùng `random.Random(f"{seed}:{day}:{shop}:{kind}")`, không dùng `hash()`.

`build_forecast_snapshots` trả một snapshot cho mỗi ngày trong duration của gói. Đây là hàm thuần, không nhận Session và không ghi global state. Forecast dùng expected noise=1 và prior CVR bias=1,5; không đọc noise thực tế của tương lai. `forecast_package` gọi cùng helper để tổng hợp thành Forecast cả gói, tránh hai công thức khác nhau.

D03 gọi helper trong `activate_approved_package` với package đã được seller duyệt, rồi lưu vào `session.forecast_snapshots[(shop_id, target_day)]` **trước settlement**. Mỗi snapshot giữ raw daily prediction và issued point sau factor/stock cap. Forecast khi thương lượng có thể khác snapshot của gói đã duyệt; dùng snapshot mới nhất được phát hành trước thời điểm ngày được tính, không tính lại sau khi thấy outcome. Ngày 2 dùng snapshot đã lưu, không reforecast từ kết quả ngày 2.

Nếu D02 đang dùng fake với `forecast=None`, nối forecast thật trước demo; không điền 18–26 như kết quả được bảo đảm. Chưa activate package thì chưa phát sinh chi quảng cáo.

Settlement chỉ dùng package đang có hiệu lực. Với content refresh, quality gain=0,25 có hiệu lực từ ngày sau publish và không cộng dồn qua các lần refresh. Không có active package thì ads=0 và dùng voucher công khai hiện hành.

Tính fees theo từng channel và contribution theo data design mục 7.1; giữ rounding adjustment ở nội bộ. Aggregate `profit_after_fees` đã trừ ads và COGS. ROAS bằng paid revenue / paid spend: spend=0 thì null; có spend nhưng không conversion thì ROAS=0.

Nếu ngày đã thuộc `settled_days`, trả metrics đã lưu. Tính kết quả vào biến local trước rồi commit tồn kho, metrics và event đúng một lần. Tồn kho mở đầu ngày 1 không bị trừ lại bởi seeded history. P0 chưa cần tạo 14 ngày history.

## 2. Evidence và learned records

`platform_view` trả public history, calibration và lessons. `shop_view` trả rules hiện hành và preferences đúng shop D. Không merge ShopPrivate vào public memory. Mỗi lần đọc view ghi `memory_read` cùng record IDs đã đọc.

Chỉ chạy `run_night` sau `simulate_day`. Đọc events đúng run/day, dùng `event.seq` làm evidence và giữ cursor học riêng để không xử lý lặp. Chỉ event feedback do seller gửi được dùng làm evidence sở thích; message tự sinh của model không phải seller feedback.

Feedback có từ “sáng” hoặc “tối” tạo candidate `content_style="ảnh nền sáng"`. Sinh ID ổn định từ sha256 của run/shop/field/value rồi rút gọn; deduplicate supporting event seqs. Candidate mới có status `candidate`; chưa sửa rules.

History lưu package đã áp dụng, số vòng, card/negotiation IDs và outcome ROAS; loại private financials. Calibration lấy actual/raw của cùng shop-day. Bỏ sample raw=0; giữ tối đa 30 mẫu. Đủ 5 mẫu mới tính median/quantiles; trước đó factor=1.

Learning Agent gọi structured LLM một lần, trả tối đa 3 LessonOp từ public evidence và existing lessons. Dùng chung ngân sách LLMClient của phiên. Khi model lỗi, dùng một public template dựa trên feedback thật và ghi source=offline. Code chỉ nhận evidence IDs có thật, scope được phép và text không chứa private values. LLM không tự ghi rules hoặc tính calibration.

Phân biệt hai loại tham chiếu: `Preference.evidence_seqs` là `list[int]` chứa `event.seq`; `LessonOp.evidence` là `list[str]` chứa negotiation ID thật theo CONTRACT. Dựng mapping từ `event.data.negotiation_id`; public evidence cho Learning chứa cả seq và negotiation ID liên quan. Kiểm lại mapping trước khi ghi lesson; không đổi event seq thành chuỗi để giả làm negotiation ID.

Ghi bốn ngăn dẫn xuất rồi ghi `night_summary`. Khi memory tắt, bỏ cả bốn nhóm write; rules vẫn được đọc và enforce. NightSummary báo số mẫu thật, không yêu cầu factor<1 ngay sau ngày 1.

## 3. Ngày 2

`prefs_to_ask` trả candidate đủ support, chưa hỏi hoặc không còn trong thời gian im lặng sau khi từ chối. Runtime tạo question-only card rồi gọi `mark_asked`; LLM không tự đánh dấu đã hỏi.

- Seller trả lời Có: append style đã chuẩn hóa nếu chưa có; tăng rules version một lần; chuyển candidate thành `confirmed`.
- Seller trả lời Không: chuyển candidate thành `declined`, đặt `declined_until = day + 14`; giữ rules.
- `get_rules` và `shop_view` đọc lại phải thấy style mới sau câu trả lời Có; UI hiển thị style đó.

Không sửa ảnh/video đã publish ngày 1. Lần tạo nội dung tiếp theo, ContentService lấy confirmed style vào prompt. Test thêm một lần `start` bằng fake sau confirmation để chứng minh prompt nhận style; không cần tạo job trả phí thứ ba trên sân khấu.

## Test

- Cùng input/seed cho cùng output. Không có active package thì ads_spend=0; stock không âm.
- Daily forecast có đủ input; ratio không dùng period point. Sau ngày 1: points=1, factor=1.
- Snapshot helper trả đúng duration, target_day tăng liên tiếp; `forecast_package.point` bằng tổng daily issued points. Activate lưu snapshot trước settlement; gọi settlement không tạo forecast mới.
- Feedback event seq có thật tạo candidate; rules style vẫn rỗng trước khi seller trả lời Có.
- Gọi night hai lần không nhân đôi candidate/history/sample. Memory OFF không ghi learned records.
- Ngày 2 trả lời Có làm đổi rules style/candidate/version, giữ nguyên active package và ngân sách. Trả lời Không giữ rules.
- Platform view không có private data. LessonOp giả thiếu evidence bị từ chối.

Chạy `.venv/bin/python -m pytest -q tests/unit/memory tests/unit/simulation tests/integration/memory`. Bàn giao một JSON NightSummary thực lấy từ test, không dùng screenshot dashboard với số giả.

## Mở rộng sau demo

Runner 7 ngày cho A–E, SellerSimulator, đối chứng cùng initial state/model config/seed, baseline history 14 ngày và proof từ metrics đã lưu. Đây là task riêng; không đưa acceptance của full proof vào D04.
