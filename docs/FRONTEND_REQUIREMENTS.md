# Requirement for frontend

Cập nhật 31/10/2026. Dành cho agent backend, data và frontend khi ghép màn Demo React. Yêu cầu về định danh, phiên bản, quyền và persistence nằm trong [Requirement về data](FRONTEND_DATA_REQUIREMENTS.md). Đọc cùng [CONTRACT](CONTRACT.md), [data design v1.1](../data/growth_agents_data_api_design.md), đặc biệt mục 10, và [bàn giao frontend](FRONTEND_HANDOFF.md).

## 1. Phạm vi và trạng thái triển khai

Frontend hiện có khối **Hai agent cùng tìm gói phù hợp**, hướng chuyển lượt sàn–shop, số vòng/phiên thương lượng, kết quả code kiểm tra, đánh giá trọng tài, bảng điều khoản trước–sau và nhật ký. Nội dung này đọc seller projection của đúng run/ngày/shop, không phải transcript nội bộ của model.

Route nghiệp vụ hiện dùng Data SQLite và native graph/worker tại `?preview=0`; contract đã nối ở [DEMO_CONTRACT](DEMO_CONTRACT.md). Preview `?preview=1` vẫn minh họa bằng dữ liệu mẫu và không chứng minh agent thật đã chạy. Frontend không tự chuyển sang preview khi API lỗi.

Luồng tích hợp mở đầu tại trang shop, với mục tiêu D **24 đơn trong 3 ngày** và cap **45.000đ/ngày** lấy từ `state.brief_preset`. UI chỉ hiển thị và xác nhận, không cho sửa; backend kiểm đúng preset. Brief của run cũ đã xác nhận hiển thị theo lịch sử. Logo dùng ảnh ShopPilot AI người dùng cung cấp; tên shop và số kinh doanh không đổi.

Mục 8 mô tả kho mẫu ngày7 của preview. Màn Proof tích hợp có nguồn phiên hiện tại từ Data và nguồn báo cáo simulator đã chạy từ artifact có provenance; phạm vi còn lại của bộ chọn dataset7ngày đầy đủ được nêu tại mục9, không đánh dấu xong chỉ vì có SQLite.

**Phần A** bên dưới dùng hợp đồng hiện hành. **Phần B** là mở rộng tích hợp mục tiêu mà React đã có khả năng đọc; thiếu dữ liệu thì hiện trạng thái chưa có, không giả lập xử lý. Không sửa `CONTRACT.md` hoặc `/api/v1` trong đợt giao diện này.

`agent_activity` và `referee_review` đã được nối vào seller facade; snapshot `agent_activity` vẫn tùy chọn. Backend giữ nguyên câu hỏi, actor tiếp theo, round và evidence refs của trọng tài sau lọc quyền. `state.mode` là cấu hình; nhãn live/replay/offline thực đọc từ telemetry/receipt của đúng tác vụ. Thiếu source thì hiện chưa có dữ liệu.

## 2. Phần A: 9 API hiện hành

Giữ `/api/*`, JSON trực tiếp và cookie HttpOnly `growth_sid`; React không đọc envelope `/api/v1`, không kết nối database và không giữ service credential. Các body version/brief/draft/job/content và ack/skip theo DEMO_CONTRACT hiện hành; thêm đồng thời với Data DTO/fixtures.

| Endpoint | Yêu cầu phục vụ giao diện |
| --- | --- |
| `GET /api/state` | Trả đủ StateView; state/phần thẻ/gói/content phải là snapshot đã commit của phiên seller hiện tại. |
| `GET /api/events?after=N` | Trả `{events,last_seq}` tăng theo seq; đọc được trong khi tác vụ nền đang chạy. Lần tải trang đầu đọc từ 0. |
| `POST /api/day/start` | Bắt đầu đúng ngày một lần, trả `{day,step}` sớm và chạy graph nền để giao diện nhận từng lượt. |
| `POST /api/decision` | Xử lý đúng `card_id`; `negotiate` mở negotiation_id mới, `accept` không đồng nghĩa đã publish nội dung. |
| `POST /api/content/retry` | Trả attempt mới với media running; version 1–3 gồm bản đầu và hai lần làm lại. |
| `POST /api/content/apply` | Chỉ áp dụng ảnh sẵn sàng của draft đang chờ duyệt; xác nhận listing đã commit. |
| `POST /api/night` | Đóng ngày và chờ learning; `next_day=null`, `step=complete` ở ngày 7. Không tạo ngày 8. |
| `POST /api/reset` | Run mới; không tái sử dụng event seq/run cũ. Giữ lịch sử run cũ theo data design. |
| `GET /api/proof` | Kết quả từ các run có nguồn, đúng số ngày; không lấy fixture giao diện làm bằng chứng. |

Mọi POST mang `Idempotency-Key` và `X-Request-ID`. Handler phải kiểm tra ownership, phiên bản và idempotency tại server. Trả lỗi tiếng Việt trong `error.message_vi` (adapter cũng có thể trả `error.message`). `409 VERSION_CONFLICT` không được áp dụng một phần.

Frontend poll khoảng 1,5 giây, state khi duyệt nội dung khoảng 3 giây. Polling tiếp tục trong khi POST chờ phản hồi; GET không được bị giữ sau cùng một session lock dài với lời gọi LLM. Mỗi write vẫn bị khóa trên UI để tránh gửi trùng. Nếu handler nhận lệnh chạy lâu, dùng quy ước `202` / `COMMAND_IN_PROGRESS` hiện có; client chờ mục tiêu thay đổi tối đa khoảng 70 giây. Với night, chỉ hoàn tất khi ngày tăng hoặc `night_done/complete`, không chỉ vì có summary.

## 3. Phần A: sự kiện thương lượng và cách render

Mọi event giữ `{seq,run_id,day,ts,type,actor,shop_id,text_vi,data}`. `ts` hiển thị `HH:MM` theo Asia/Ho_Chi_Minh; thứ tự do `seq` quyết định. Sự kiện thương lượng phải có shop_id cụ thể, không dùng null.

| Event | `data` tối thiểu | Hiệu ứng UI |
| --- | --- | --- |
| `platform_turn` | `{negotiation_id,round,action,package}` | Ghi nhận lượt đã xong của sàn, mũi tên sang shop, cập nhật gói. |
| `shop_turn` | `{negotiation_id,round,action,package,private_note_vi?,redacted}` | Ghi nhận phản hồi của shop, mũi tên về sàn; ghi chú riêng chỉ trong seller projection. |
| `code_check` | `{negotiation_id,proposal_id,round,ok,checks:[{code,ok,message_vi}]}` | Hiện kết quả kiểm tra đầy đủ gần nhất; không suy pass/fail từ thẻ hoặc event thiếu boolean. |
| `card_sent` | `{card}` | Bằng chứng thẻ đã được tạo; UI chờ StateView `awaiting_decision` để hiện đúng thẻ hiện tại. Không tính là seller đã xem/duyệt. |
| `seller_decision` | `{card_id,action,note_vi,rule_answer}` | Lưu lựa chọn của seller. `negotiate` tách lịch sử cũ và chờ phiên mới. |

`round` là lượt của sàn, tối đa 3, không phải số message hay phần trăm hoàn thành. Shop phản hồi trong cùng round. Người bán yêu cầu thương lượng lại tạo attempt mới, tối đa 2 attempt/ngày/shop theo v1.1; round bắt đầu lại từ 1. Không dùng round=4 hay tái sử dụng negotiation_id để nối lần làm lại.

`platform_turn`/`shop_turn` xác nhận **đã làm xong**. Nếu chỉ có các event này, React dùng chữ “Đã gửi / Chờ phản hồi”. Backend không được kỳ vọng frontend suy luận chính xác agent đang gọi tool nào từ event đã hoàn tất.

Gói so sánh lấy từ proposal đầu và package mới nhất của cùng negotiation_id. Khi làm lại sau góp ý, nếu shop mở lượt trước thì gói cuối của attempt trước là mốc “Gói trước góp ý”. Các điều khoản được so sánh: `ads_daily_budget`, `voucher_pct`, `stop_roas_below`, `stop_after_days`, `duration_days`, `content_refresh`. React không tính lại lãi, feasibility hoặc forecast.

## 4. Phần B: telemetry tác vụ đang chạy

Event mới: `type=agent_activity`. Actor thuộc `platform_agent|shop_agent|code|referee`. Không dùng actor gửi từ trình duyệt để xác thực writer.

```json
{
  "seq": 21,
  "run_id": "run_42",
  "day": 1,
  "ts": "14:10",
  "type": "agent_activity",
  "actor": "shop_agent",
  "shop_id": "D",
  "text_vi": "Agent shop đang đánh giá gói đề xuất.",
  "data": {
    "negotiation_id": "D-1-attempt1",
    "task_id": "D-1-attempt1-shop-1",
    "round": 1,
    "phase": "response",
    "status": "running",
    "label_vi": "Agent shop đang đánh giá gói theo giới hạn chủ shop"
  }
}
```

| Field | Giá trị / ý nghĩa |
| --- | --- |
| `negotiation_id` | Đúng attempt hiện tại, có ownership run/shop/day. |
| `task_id` | ID ổn định của một tác vụ; retry cùng tác vụ không tạo message thành công giả. |
| `round` | Số nguyên 1–3. |
| `phase` | `proposal` (sàn), `validation` (code), `response` (shop), `referee` (trọng tài). |
| `status` | `running|done|failed|stopped`; không gửi running sau terminal cho cùng task_id. |
| `label_vi` | Mô tả ngắn, đã lọc quyền; không phải chain-of-thought hay prompt thô. |

Ghi running **trước** khi gọi tác vụ chậm; terminal sau kết quả. Event kết quả tương ứng (`platform_turn`, `shop_turn`, `code_check`, `referee_review`) cũng kết thúc nhãn running cũ trên UI. Một tác vụ chạy lại phải có identity/lifecycle rõ; không hồi sinh tác vụ đã dừng hoặc attempt đã đóng.

Snapshot StateView **tùy chọn** `agent_activity` có cùng data cộng `actor` và `updated_seq`, hoặc null:

```json
{
  "agent_activity": {
    "negotiation_id": "D-1-attempt1",
    "task_id": "D-1-attempt1-shop-1",
    "round": 1,
    "phase": "response",
    "status": "running",
    "actor": "shop_agent",
    "label_vi": "Agent shop đang đánh giá gói theo giới hạn chủ shop",
    "updated_seq": 21
  }
}
```

`updated_seq` tham chiếu event đã commit trong run này; không dùng thời gian client để phân xử. Snapshot cũ hơn event kết quả không được làm agent sáng lại. `step` và thẻ hiện tại luôn quyết định có còn được xử lý/duyệt hay không; snapshot không cấp quyền chi tiền. Thiếu snapshot vẫn hoạt động qua events từ 0.

## 5. Phần B: đánh giá trọng tài

Event mới: `type=referee_review`, `actor=referee`.

```json
{
  "seq": 24,
  "run_id": "run_42",
  "day": 1,
  "ts": "14:10",
  "type": "referee_review",
  "actor": "referee",
  "shop_id": "D",
  "text_vi": "Gói điều chỉnh vẫn bám mục tiêu và giữ giới hạn đã được người bán xác nhận.",
  "data": {
    "negotiation_id": "D-1-attempt1",
    "round": 1,
    "action": "continue",
    "evidence_refs": [18, 23],
    "unresolved_terms": ["Voucher"],
    "next_actor": "platform_agent",
    "focused_question": null
  }
}
```

`action=continue|refocus|ask_human|stop`. `evidence_refs` là danh sách seq trong cùng run, chỉ trỏ tới bằng chứng mà trọng tài được đọc. `unresolved_terms` là nhãn điều khoản công khai. `next_actor=platform_agent|shop_agent|seller|null`. `focused_question` là câu hỏi an toàn hoặc null. UI hiện giải thích `text_vi`, action và câu hỏi; không đọc suy luận nội bộ.

Trọng tài chỉ đề nghị điều phối. Graph kiểm quyền, số vòng và thực thi chuyển trạng thái; code kiểm tra tài chính vẫn là chốt chặn. `ask_human` hiện lời giải thích nhưng **chưa có form trả lời trọng tài mới**: backend cần tạo Card được hợp đồng hỗ trợ hoặc thống nhất mở rộng HITL riêng. Không dùng `rule_question` về sở thích để chứa câu hỏi goal bất kỳ. `stop` không tương đương chủ shop từ chối; ghi outcome và lý do riêng trong dữ liệu nghiệp vụ.

Thiếu event trọng tài phải hiện “Chưa có đánh giá trọng tài”, không lấy code_check làm bằng chứng trọng tài đã làm việc.

## 6. Đồng bộ, nhánh và điều kiện thành công

- State và events có thể được đọc ở hai thời điểm gần nhau. StateView là nguồn trạng thái thao tác hiện tại; seq là nguồn thứ tự lịch sử. Publish event sau commit, không trước khi entity/thẻ tương ứng tồn tại.
- `accept` giữa hai agent chỉ là đồng thuận. Seller approval, campaign applied và content published là các mốc khác nhau; không đánh dấu áp dụng từ một event accept.
- Từ chối/no_fit, gói chỉ xác nhận sở thích và gói không làm nội dung phải bỏ qua các bước tương ứng; không tô xanh các bước không chạy.
- Khi mất mạng, giữ dữ liệu gần nhất, hiện gián đoạn, không chạy tiến trình giả hoặc POST tự động. Nối lại tiếp tục từ cursor, không lặp sự kiện đã nhận.
- Giữ 7 ngày và 3 attempt nội dung như config hiện hành; không lấy mốc 6 ngày cũ trong workbook làm mặc định mới.
- IntentBrief/version đã có bước xác nhận và version gate; demo D dùng preset chỉ đọc. Defer và tracking funnel trong workbook vẫn ngoài luồng hiện hành, không tuyên bố chúng đã chạy chỉ vì có đánh giá trọng tài.

## 7. Hai khung chat đối chứng theo ngày

Màn `proof.html` hiện ưu tiên hội thoại **Không học từ lịch sử / Có học từ lịch sử**, chọn ngày 1–7 và dẫn nguồn bộ nhớ. Mặc định chọn ngày 2 để thấy tác động của phản hồi ngày trước; ngày 1 phải có cùng điểm xuất phát. Luồng agent chỉ một hàng nhỏ; chỉ số và nguồn báo cáo mở qua “Chi tiết chỉ số và nguồn dữ liệu”. Trên màn Demo, luồng agent cũng gọn một hàng; bảng so sánh điều khoản và checks được gấp mặc định. Desktop dùng cuộn bên trong từng khung, không đẩy thẻ quyết định và hậu trường xuống dưới sơ đồ lớn.

Thanh process của màn Demo cao tối đa 64px ở viewport 1366×768; hiển thị Agent sàn → Agent shop → Kiểm tra → Chủ shop duyệt theo state/events thật. “Chi tiết” mở lớp nổi có vùng cuộn riêng, không thu nhỏ hai khung bên dưới. Chat giữ nguyên chiều cao nội dung của thẻ, cuộn được tới nút “Đồng ý” và “Dùng bản này”; ô nhập luôn nằm ngoài vùng cuộn. Chat và nhật ký đều hỗ trợ chuột/bàn phím. Thay đổi bố cục này không yêu cầu thêm field hoặc endpoint backend.

`comparison_days?: ComparisonDay[]` đã được Data projection hỗ trợ. Không tạo thêm POST và không phát sinh LLM call khi người xem chọn ngày. Report không có ngày/hội thoại tương ứng hiện “chưa có hội thoại”, không tự ghép đoạn chat mẫu. Các ví dụ bên dưới minh họa shape, không phải transcript đã đo.

```json
{
  "day": 2,
  "request_vi": "Làm ảnh bìa mới cho mẫu quạt này giúp chị nhé.",
  "situation_vi": "Ghi nhớ phong cách ảnh",
  "takeaway_vi": "Bên có học tham khảo góp ý về nền sáng của ngày trước.",
  "off": {
    "run_id": "run_off_42",
    "messages": [
      {"id": "off-turn-12", "actor": "shop_agent", "text_vi": "Chị muốn ảnh theo phong cách nào?", "event_seq": 12},
      {"id": "off-turn-13", "actor": "seller", "text_vi": "Nền sáng như hôm qua nhé.", "event_seq": 13}
    ],
    "result_vi": "Chủ shop cần nhắc lại phong cách",
    "memory_used": []
  },
  "on": {
    "run_id": "run_on_42",
    "messages": [
      {"id": "on-turn-14", "actor": "shop_agent", "text_vi": "Em tham khảo góp ý nền sáng lần trước để soạn bản nháp mới.", "event_seq": 14}
    ],
    "result_vi": "Dùng góp ý cũ khi đề xuất bản nháp",
    "memory_used": [
      {"run_id": "run_on_42", "source_day": 1, "event_seq": 8, "text_vi": "Góp ý ảnh nền sáng"}
    ]
  }
}
```

- `ComparisonDay.day` là integer 1..ProofReport.days, unique; `off.run_id`/`on.run_id` phải khớp `report.run_off`/`report.run_on` và là hai run khác nhau. Mỗi branch có `messages` và `memory_used` là array.
- `request_vi` là lời yêu cầu chung, hiển thị thành bubble đầu của cả hai khung. `messages` là các lượt tiếp theo theo thứ tự, không chép lại bubble chung. `id` unique trong branch/day; `actor=seller|shop_agent|platform_agent|system`; `text_vi` là trích đoạn được phép hiển thị; `event_seq` truy nguyên về event bất biến của đúng branch.
- `memory_used` của nhánh off luôn `[]`. Nhánh on chỉ dẫn nguồn cùng run, với `1 <= source_day < day`, seq dương và tóm tắt an toàn. Không lấy góp ý hiện tại hoặc tương lai làm bằng chứng đã học từ quá khứ.
- `result_vi`, `situation_vi`, `takeaway_vi` phải dựa trên bằng chứng. Không ép nhánh on luôn tốt hơn; cùng phản hồi, chưa đủ dữ liệu hoặc bộ nhớ chưa giúp ích đều là kết quả hợp lệ.
- Luật cứng, quyền riêng tư, validators và seller approval vẫn bật ở cả hai nhánh. Không minh họa nhánh off “quên luật” để làm nhánh on trông tốt hơn. Sự khác biệt là quyền đọc dữ liệu/bài học lịch sử.
- Ưu tiên 2–4 lượt ngắn và có ngữ cảnh cho mỗi branch để trình chiếu. Hội thoại dài được cuộn trong khung; tuyệt đối không cắt câu làm đổi nghĩa. Giữ khả năng kiểm tra toàn bộ transcript từ dữ liệu nguồn/JSON export.

## 8. Nhảy tới ngày 7 bằng dữ liệu mẫu

Điểm bắt đầu khi trình chiếu là **trang shop** ở `/?preview=1` hoặc `index.html?preview=1`. Người xem thấy sản phẩm và bảng điều khiển trước; chọn “Bắt đầu demo”/“Tiếp tục demo” mới vào `demo.html` có chat và hậu trường. Link bàn giao mặc định dùng trang shop.

Nút **Nhảy tới ngày 7** trên thanh phía trên màn Demo/Shop chỉ xuất hiện ở nguồn preview. Một lần bấm đọc `GET /api/demo/day7` cùng origin, nhận toàn bộ snapshot mẫu đã lưu trong SQLite, cập nhật phiên trình chiếu rồi mở `proof.html?day=7&preview=1`. Đây là API riêng của `scripts/preview_server.py`; không thay API seller hoặc runtime native7ngày ở DEMO_CONTRACT.

- Khi nạp, nút hiện “Đang nạp 7 ngày…” và khóa các thao tác ghi khác. Chỉ chuyển màn sau khi nhận đủ snapshot hợp lệ.
- Snapshot có state ngày 7/complete, tổng kết cuối ngày 7, đầy đủ sự kiện ngày 1–7, hai hội thoại mỗi ngày và báo cáo mẫu. Không chỉ đổi con số ngày trên UI.
- Màn kết quả chọn sẵn ngày 7 và hiện “Đã nạp 7 ngày từ database · Dữ liệu mẫu”. Người xem vẫn chọn được ngày 1–6, xem nhật ký hoặc chạy lại từ ngày 1.
- Không gửi accept/apply/night cho các thẻ đang chơi và không gọi provider. Thao tác chỉ thay phiên preview bằng bộ mẫu trình chiếu. Preview cũ được lưu ở khóa sessionStorage `growth-agents.react-preview.v3.before-day7` trước lần thay đầu tiên.
- Reload giữ snapshot đã nạp; bấm lặp không nối trùng events. Database lỗi/thiếu tổng kết phải báo lỗi và giữ nguyên phiên hiện tại; không tự dùng JSON/bộ mẫu JS thay cho phản hồi database.
- Phạm vi hiện tại: snapshot trong SQLite được seed từ kịch bản biên soạn sẵn, chưa phải projection từ lịch sử chạy agent trong database nghiệp vụ. Reload/đổi ngày đọc snapshot sessionStorage; bấm “Nhảy tới ngày 7” lần nữa mới đọc database lại. Backend tích hợp dữ liệu động cần dựng state/events/comparison từ các record đã lưu của đúng run thay vì dùng fixture này.
- Backend muốn cung cấp nút này trong môi trường tích hợp cần mount route đọc mẫu riêng trước static, với nhãn nguồn mẫu bắt buộc. Không dùng snapshot này làm báo cáo thực nghiệm của phiên API/live.
- `previewComparison.js` chứa kịch bản minh họa viết sẵn, cùng nhãn dữ liệu mẫu. Backend thật chỉ trả transcript được ghi từ run đối chứng, không tái dùng fixture này làm bằng chứng.

Xem thêm grain và kiểm tra nguồn dữ liệu ở mục 11 của [data requirements](FRONTEND_DATA_REQUIREMENTS.md).

## 9. Backend cần hoàn tất: ngày 7 đọc dữ liệu động

**Trạng thái: đã nối report và evidence, chưa hoàn tất toàn bộ bộ chọn dataset mô tả dưới đây.** Bộ mẫu ở mục8 vẫn được dựng từ `preview.js`/`previewComparison.js` rồi nhập JSON vào SQLite. Product `GET /api/proof` đọc record của cặp hoàn tất chứa active run, trả comparison_id; sau reset chưa có cặp thì409, không lấy proof cũ. Export `/api/proof/events?comparison_id=...` đọc đúng hai run theo quyền/cutoff, không dùng event buffer của phiên khác.

Nguồn riêng **Báo cáo mô phỏng đã chạy** đọc `/api/proof/demo`: artifact xuất từ Data records của cặp native offline, giữ IDs/hash/brief/provenance và evidence ON/OFF. Reload đọc API lại; thiếu ngày/hội thoại thì báo thiếu. Đây là cách trình chiếu nhanh hiện hành, chưa phải bộ chọn nhiều dataset với đủ state/events/bảy NightSummary. Bảng nghiệm thu đầy đủ bên dưới vẫn là yêu cầu mở rộng, không phải kết quả đã đạt.

Mục tiêu đầy đủ là `database records → backend projection → React`, với nội dung phụ thuộc dataset/run được chọn. Dữ liệu giả có thể được seed trước trong DB để trình chiếu; tính động không đồng nghĩa bắt buộc gọi agent/provider thật khi bấm nút.

Trách nhiệm backend:

1. Chọn đúng dataset/run hoặc comparison group đã đủ 7 ngày, có quyền đọc cho người xem. Lần bấm chỉ tải kết quả đã lưu, không gửi 7 quyết định thay seller và không tự gọi provider.
2. Dựng StateView, events, tổng kết ngày 7 và ProofReport từ record của dataset đó. Nội dung hai chat phải đến từ transcript đã lưu, số liệu đến từ kết quả lưu trữ/tính toán nghiệp vụ; không import kịch bản JS hoặc trả cố định `day7.json`.
3. Giữ nguồn dữ liệu rõ ràng: bộ giả seed sẵn là minh họa; run được simulator/agent thực thi là kết quả của lần chạy mô phỏng. Không gắn nhãn kết quả học thật cho hội thoại biên soạn.
4. Reload ở chế độ tích hợp phải đọc API để khôi phục đúng run; sessionStorage chỉ lưu lựa chọn/cursor nếu cần, không là nguồn nội dung authoritative. Bản dữ liệu mới phải được nhận khi người xem yêu cầu tải lại, theo revision hoặc run mới do backend quản lý.
5. Thiếu record/ngày/transcript phải báo thiếu dữ liệu và giữ lựa chọn hiện tại; không lấp bằng mẫu frontend. Chuyển sang dataset ngày 7 không sửa/xóa phiên đang chạy hoặc tạo thêm campaign/chi phí.

`TODO(contract):` Chốt bộ chọn nhiều dataset ngày7 và projection state/NightSummary tương ứng trước khi mở rộng product UI. Route `GET /api/demo/day7` vẫn chỉ là kho mẫu local. Runtime native hiện hỗ trợ1..7ngày; báo cáo đối chứng đã chạy được chọn riêng và không thay đổi active run của seller.

Nghiệm thu bắt buộc: tạo hai dataset DB có hội thoại/chỉ số khác nhau, chọn từng dataset thì UI phản ánh đúng mà không build lại JS; khởi động lại server giữ dữ liệu đã nhập; reload không dùng snapshot frontend cũ; đủ bảy tổng kết và đúng run ở hai nhánh; thiếu ngày không tự dựng nội dung; bấm lặp không ghi thêm quyết định/settlement; không gọi API trả phí. Xem [data requirements mục 13](FRONTEND_DATA_REQUIREMENTS.md).

## 10. Checklist ghép backend

- [ ] 9 endpoint đúng facade; JSON không có envelope v1.
- [ ] Sau start, GET đọc được từng event trước khi graph kết thúc.
- [ ] Shop D: sàn gửi gói → code có vi phạm → shop counter → sàn accept → code cuối pass → thẻ chờ seller; thứ tự do graph thực tế quyết định.
- [ ] Thương lượng lại có negotiation_id mới và round từ 1; tải lại vẫn khôi phục đúng attempt.
- [ ] Duplicate POST không mở hai attempt/campaign; stale card/draft không được áp dụng.
- [ ] No-fit/reject và question-only không bị ghi thành tăng chi hay conversion.
- [ ] Telemetry/referee dùng đúng payload phần B sau khi thống nhất contract; không có thì UI vẫn chạy phần A.
- [ ] Phân quyền, cursor, nguồn dữ liệu và foreign keys đáp ứng [data requirements](FRONTEND_DATA_REQUIREMENTS.md).
- [ ] Chạy UI với `?preview=0`; đối chiếu event log với database. Preview không phải test tích hợp backend.
