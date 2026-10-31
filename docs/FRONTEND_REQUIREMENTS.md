# Requirement for frontend

Cập nhật 31/10/2026. Dành cho agent backend, data và frontend khi ghép màn Demo React. Yêu cầu về định danh, phiên bản, quyền và persistence nằm trong [Requirement về data](FRONTEND_DATA_REQUIREMENTS.md). Đọc cùng [CONTRACT](CONTRACT.md), [data design v1.1](../data/growth_agents_data_api_design.md), đặc biệt mục 10, và [bàn giao frontend](FRONTEND_HANDOFF.md).

## 1. Phạm vi và trạng thái triển khai

Frontend hiện có khối **Hai agent cùng tìm gói phù hợp**, hướng chuyển lượt sàn–shop, số vòng/phiên thương lượng, kết quả code kiểm tra, đánh giá trọng tài, bảng điều khoản trước–sau và nhật ký. Nội dung này đọc seller projection của đúng run/ngày/shop, không phải transcript nội bộ của model.

Các route nghiệp vụ và graph backend trong checkout còn là khung. Preview trong trình duyệt minh họa cả telemetry và trọng tài; đây không phải bằng chứng hai agent thật đã chạy. Frontend không tự chuyển sang preview khi API lỗi.

**Phần A** bên dưới dùng hợp đồng hiện hành. **Phần B** là mở rộng tích hợp mục tiêu mà React đã có khả năng đọc; thiếu dữ liệu thì hiện trạng thái chưa có, không giả lập xử lý. Không sửa `CONTRACT.md` hoặc `/api/v1` trong đợt giao diện này.

`TODO(contract):` Backend/data owner thống nhất và bổ sung `agent_activity`, `referee_review`, cùng snapshot tùy chọn trước khi đưa telemetry/trọng tài vào seller facade thật. Đây là tên và hình dạng frontend đang hỗ trợ; không tự đổi tên khi ghép backend.

## 2. Phần A: 9 API hiện hành

Giữ `/api/*`, JSON trực tiếp và cookie HttpOnly `sid`; React không đọc envelope `/api/v1`, không kết nối database và không giữ service credential. Các body đang gửi không thêm field version mới ngoài hợp đồng.

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
| `code_check` | `{negotiation_id,ok,checks:[{ok,message_vi}]}` | Hiện kết quả kiểm tra gần nhất và mở chi tiết từng điều kiện. |
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
- IntentBrief/goal/version, defer và tracking funnel trong workbook là phần mở rộng chưa có form/API seller hoàn chỉnh. Không tuyên bố chúng đã chạy chỉ vì có đánh giá trọng tài minh họa.

## 7. Checklist ghép backend

- [ ] 9 endpoint đúng facade; JSON không có envelope v1.
- [ ] Sau start, GET đọc được từng event trước khi graph kết thúc.
- [ ] Shop D: sàn gửi gói → code có vi phạm → shop counter → sàn accept → code cuối pass → thẻ chờ seller; thứ tự do graph thực tế quyết định.
- [ ] Thương lượng lại có negotiation_id mới và round từ 1; tải lại vẫn khôi phục đúng attempt.
- [ ] Duplicate POST không mở hai attempt/campaign; stale card/draft không được áp dụng.
- [ ] No-fit/reject và question-only không bị ghi thành tăng chi hay conversion.
- [ ] Telemetry/referee dùng đúng payload phần B sau khi thống nhất contract; không có thì UI vẫn chạy phần A.
- [ ] Phân quyền, cursor, nguồn dữ liệu và foreign keys đáp ứng [data requirements](FRONTEND_DATA_REQUIREMENTS.md).
- [ ] Chạy UI với `?preview=0`; đối chiếu event log với database. Preview không phải test tích hợp backend.
