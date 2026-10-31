# Requirement về data cho frontend

Cập nhật 31/10/2026. Đây là yêu cầu dữ liệu để backend/data agent ghép [giao diện tương tác](FRONTEND_REQUIREMENTS.md). Mô hình lưu trữ và API chuẩn tiếp tục theo [data design v1.1](../data/growth_agents_data_api_design.md); tài liệu này mô tả grain, các quan hệ và projection frontend cần, không tạo schema/database thứ hai.

## 1. Nguồn sự thật và ranh giới trách nhiệm

```text
Seed + entity/version đã lưu
       ↓ workflow, finance, validators, simulator
Database + event log đã commit
       ↓ seller facade có kiểm quyền /api/*
StateView + Event[] + assets được phép đọc
       ↓ React
Tiến trình, điều khoản, thẻ quyết định, nội dung, báo cáo
```

Database và eventlog là nguồn sự thật. Các thẻ, gói, quyết định, job, asset và kết quả phải đọc lại được sau restart backend. React chỉ có state hiển thị và cursor; sessionStorage chứa fixture preview không phải kho nghiệp vụ. Bộ nhớ học là dữ liệu dẫn xuất do memory owner quản lý, không thay thế lịch sử bất biến.

## 2. Grain và định danh bắt buộc

| Dữ liệu | Một record đại diện cho | Identity / quan hệ cần giữ |
| --- | --- | --- |
| Run | Một lần chạy world, seed, memory setting và mode cố định | `run_id`; metadata scenario/simulator version, seed, resolved mode, memory_enabled |
| Shop / sản phẩm | Shop và sản phẩm của scenario, public/private tách quyền | `shop_id`, canonical `product_id`; facade hiện chọn sản phẩm demo của shop |
| Shop-day | Trạng thái một shop trong một ngày mô phỏng | `(run_id,shop_id,day)`; ngày 1–7 |
| Negotiation | Một attempt thương lượng, không phải mọi lượt của cả ngày | `negotiation_id`, run/shop/product/day, attempt; tối đa 2 attempt/ngày/shop |
| Turn / proposal | Một đầu ra bất biến của agent | proposal/turn ID, negotiation_id, author, round, parent proposal ID, package, version, shared message |
| Check | Kết quả code kiểm đúng proposal và các version đầu vào | proposal ID, check ID, phase, pass/fail, rule/cost/fee/policy/inventory versions; không gắn nhầm check gói cũ vào gói mới |
| Card | Một yêu cầu seller quyết định | `card_id`, run/shop/day, proposal ID/version hoặc rule-question ID; trạng thái pending/resolved |
| Seller decision | Một quyết định trên đúng card/version | decision ID, card ID, action, seller identity, approved child proposal ID nếu edit; idempotency record |
| Campaign / apply | Một lần thực thi đã commit | campaign/apply ID, exact proposal ID + approval decision ID, thời gian/ngày hiệu lực, receipt/status |
| Content job / draft | Một lần tạo theo gói đã được duyệt | job ID, approved proposal ID, attempt 1–3, canonical content_version, input versions, feedback, trạng thái |
| Asset | Một file có nguồn và quyền đọc | asset ID, job/product/run/shop, loại, readiness, provenance, checksum; URL facade được cấp quyền |
| Event | Một sự kiện đã commit trong run | `(run_id,seq)`, owner scope, writer đã xác thực, type, entity ref, visibility, recorded_at/simulated_at |
| Settlement / metric | Kết quả đúng kỳ đo và input snapshot | run/shop/product/day/channel/campaign theo grain v1.1; immutable snapshot hash và once-only settlement |
| Night summary | Handoff học của một run/day | day, evidence/settlement cursor, completed/skipped/failed, summary; không suy luận hoàn tất từ vài memory_write |

Không dùng shop name, giờ `HH:MM`, vị trí mảng hoặc `round` làm identity. Hai ngày có thể cùng round=1; hai run có thể cùng shop D; chỉ filter shop không đủ. ID phải ổn định qua retry. Quan hệ foreign key không được nối sang run/shop/product khác.

Chuỗi minh họa identity: `run_42 / D / day=1 / D-1-attempt1 / round=1`, rồi `D-1-attempt2 / round=1` khi seller yêu cầu làm lại. Round tính lượt của sàn, tối đa 3; không tính tổng message của cả hai agent.

## 3. Projection StateView frontend đang đọc

Các field bắt buộc theo facade hiện hành; không trả toàn bộ row ORM rồi để React tự lọc:

| Field | Kiểu / ý nghĩa và nguồn |
| --- | --- |
| `run_id`, `day` | string, integer 1–7 từ phiên đã xác thực; day không do browser tăng |
| `mode`, `memory_enabled` | `live|replay|offline`, boolean; live mô tả lời gọi model, không biến thị trường giả lập thành dữ liệu sàn thật |
| `step` | `idle|negotiating|awaiting_decision|content_review|day_done|night_done|complete` |
| `demo_shop` | ShopPublic hiện tại: tên, SKU hiển thị qua sản phẩm demo, giá, tồn kho, listing, ảnh/video và voucher từ entity đã lưu |
| `demo_shop_original` | Listing gốc bất biến trong run để so sánh; không bị ghi đè khi apply/retry |
| `active_package` | ActivePackage hoặc null; chỉ phản ánh gói đã áp dụng, không dùng proposal mới chưa được seller duyệt |
| `pending_card` | Card pending hiện tại hoặc null; package/forecast/tài chính null khi `kind=question` |
| `content_draft` | Draft hiện tại hoặc null; `version` facade = attempt 1–3, không phải canonical content_version tăng toàn sản phẩm |
| `last_night` | NightSummary gần nhất hoặc null; giữ sau chuyển ngày, không dùng nó một mình để xác nhận close đã xong |
| `live_calls_left` | Số nguyên >=0; ngân sách lời gọi còn lại thực tế của phiên |
| `agent_activity` | Mở rộng tùy chọn sau khi thống nhất contract; payload và `updated_seq` ở frontend requirements |

Không suy đoán `pending_card` thuộc negotiation nào bằng cách parse tên card. Backend phải lưu quan hệ thật. Các identity canonical chưa có trong facade được adapter giữ ở server; việc bổ sung `negotiation_id`, `proposal_id`, `proposal_version`, `brief_version` vào Card/Event là additive design cần cập nhật hợp đồng trước khi UI sử dụng để ghi. Hiện UI gửi `card_id`, backend phải từ đó resolve exact immutable version.

`TODO(contract):` IntentBrief/version, defer, package_applied receipt projection và view-tracking của workbook chưa có hợp đồng seller hoàn chỉnh. Lưu canonical attribution trong data service; không âm thầm đổi body quyết định hoặc trả intent mẫu như đã được seller xác nhận.

## 4. Event log, cursor và khôi phục trạng thái

- `seq` tăng đơn điệu trong run, unique `(run_id,seq)`. Không giả định liên tiếp vì event riêng tư có thể bị lọc. `ts` chỉ là nhãn giờ; canonical timestamps giữ múi giờ/UTC và thời gian mô phỏng theo v1.1.
- `GET /api/events?after=N` chỉ trả event được seller hiện tại xem, của run sid đang trỏ đến. `last_seq` là cursor sau khi quét cả event không nhìn thấy, không phải mặc định seq cuối trong `events`. Trang rỗng vẫn có thể tăng cursor.
- Giữ event bất biến và thứ tự; retry một write không tạo lại cùng fact với seq mới. Cùng cursor được phép trả lại event do reconnect; frontend dedup theo run/seq.
- Cursor chỉ áp dụng trong run tương ứng. Khi reset/fork replay đổi run_id, frontend xóa buffer/cursor và đọc từ 0. Adapter đổi sid→run mapping sau fork; không nối tương lai của recording cũ sang quyết định mới.
- Tải lại trang cần đọc state rồi lịch sử seller từ 0 để dựng lại attempt, round, proposal đầu, gói mới nhất, checks và referee. Nếu phân trang, giữ response hiện hành và đảm bảo client có thể poll đến đủ lịch sử; không trả cursor vượt qua authorized event chưa gửi.
- Sự kiện turn/check/telemetry/referee cần `data.negotiation_id`. Với check và review, canonical entity refs phải xác định đúng proposal/turn. Không dùng event shop khác, attempt cũ hoặc ngày cũ để thay phần đang thiếu.
- State đọc trước events nên có thể chậm một commit. Phải đảm bảo GET tiếp theo hội tụ, không có thẻ/asset mồ côi. `agent_activity.updated_seq`, nếu có, phải tham chiếu event đã commit; snapshot cũ không được hồi sinh task sau terminal.
- Không giữ read lock của cả session qua lời gọi LLM/provider. Write transaction ngắn, state/events đọc được trong thời gian tác vụ chạy để frontend thấy chuyển lượt.

## 5. Kiểu số, giá trị thiếu và kỳ đo

| Loại | Quy tắc dữ liệu |
| --- | --- |
| Tiền | Số nguyên VND, không gửi `"45.000đ"` hoặc chuỗi có dấu phân cách. Code/backend tính chính xác theo v1.1; UI chỉ định dạng. |
| Voucher | Số nguyên phần trăm: `3` nghĩa 3%, không phải 0.03. |
| ROAS | JSON number hữu hạn hoặc null; không serialize Infinity/NaN. Ngưỡng dừng là điều khoản công khai; ROAS hòa vốn chính xác là dữ liệu riêng. |
| Đơn, tồn kho, ngày | Integer theo domain; tồn kho là snapshot sau settlement hiện tại, không trừ thêm ở client. |
| Null | “Chưa có / không xác định / không áp dụng” theo field; không đổi null thành 0 hoặc số fixture. Zero là giá trị thật và phải được giữ. |
| Forecast | Gắn proposal, ngày bắt đầu, thời hạn và input versions. Forecast trên Card hiện là cả gói, không phải dự báo một ngày. |
| Metrics | `market_result.data.metrics` đúng shop/ngày; ROAS null nếu không xác định. So sánh forecast với actual phải cùng kỳ/đơn vị. |
| Profit | Backend ghi rõ lợi nhuận/đơn sau phí và voucher hay lợi nhuận tổng sau quảng cáo. UI không suy ra hai đại lượng giống nhau. |
| Thời gian | Lưu recorded_at và simulated_at riêng; `HH:MM` không đủ để đo latency, attribution hay quyết định thứ tự. |

Backend đảm bảo package có đủ `content_refresh`, `ads_daily_budget`, `voucher_pct`, `stop_roas_below`, `stop_after_days`, `duration_days`. Khi reject/withdraw được phép package=null. Không tự lấy package của lượt cũ rồi gắn vào lượt từ chối như thể agent vừa gửi gói mới.

## 6. Quyền truy cập và nội dung an toàn

| Projection | Được có | Không được có |
| --- | --- | --- |
| Agent sàn / shared | Listing công khai, điều khoản gói đã lọc, shared message, code pass/fail công khai | Giá vốn, lãi tối thiểu, lãi/đơn, ROAS hòa vốn chính xác, private_note, feedback riêng hoặc hidden simulator inputs |
| Seller + agent shop của chính shop | Dữ liệu riêng được quyền đọc và checks chi tiết phục vụ quyết định | Dữ liệu riêng shop khác hoặc seller khác |
| Trọng tài | Brief/goal đã xác nhận, transcript shared đã lọc, evidence refs được phép đọc | ShopPrivate, private_note, suy luận model nội bộ; không gom hai kho riêng để so sánh |
| Content worker | Verified attributes/assets/brief của job đã được giao | Chức năng đổi giá, tăng ngân sách hoặc publish thay seller |
| UI backstage | Seller projection được cấp quyền, tách shared text và private note bằng field riêng | Prompt thô, chain-of-thought, token, credential, local file path và stack trace |

Lọc quyền tại backend **trước khi trả JSON**. Việc React lọc shop/day/run là phòng lỗi hiển thị, không phải cơ chế authorization. Phải kiểm cả event download, report/asset URL và replay export. Trọng tài không đọc payload seller-private chỉ vì UI được phép hiển thị payload đó. Shared text đi qua leak_guard trước persistence/projection theo v1.1.

## 7. Transaction và chuỗi đề xuất–duyệt–áp dụng

```text
negotiation → immutable proposal → validated checks
           → pending card → seller decision trên exact version
           → apply command → committed campaign / publication → receipt + event
```

- Lưu approval binding với proposal/draft chính xác. Seller edit tạo child proposal đã kiểm, approval gắn child; không sửa proposal cũ tại chỗ.
- Cùng idempotency key + cùng payload trả cùng kết quả; key cũ với payload khác phải bị từ chối. Kiểm idempotency và precondition trong transaction, không dựa vào nút disabled của browser.
- Hai write cạnh tranh không thể cùng duyệt/applied hai lần một card/draft. Ràng buộc uniqueness trên proposal/approval apply và settlement phải theo v1.1.
- Gói approved nhưng apply failed vẫn là chưa áp dụng. Content job done chưa có nghĩa seller đã duyệt/publish. Event thành công được commit cùng hiệu ứng, thất bại không để partial spend/listing.
- Rule preference candidate không phải hard rule. Chỉ cập nhật rules khi có câu hỏi pending riêng và câu trả lời seller hợp lệ; lưu confirmation evidence và rules_version.
- Sau close-day, learning phải có completed/skipped/failed envelope hợp lệ trước advance. Không settlement/learning/spend ngày cũ lần hai khi retry hoặc refresh.

## 8. Content, asset và nguồn dữ liệu

- Mỗi draft thuộc approved proposal + product; mỗi attempt có input versions. Job của attempt cũ hoàn tất muộn không được thay draft mới hoặc listing đã publish.
- 3 attempt tổng cộng gồm bản đầu. Facade `ContentDraft.version` là attempt; canonical content_version vẫn tăng toàn sản phẩm, có thể >3.
- Cover option `A|B|C`, status `running|done|failed|cached`, path nullable. Video thêm `pending`. Chỉ `done/cached` với asset/path hợp lệ mới cho áp dụng. Video không sẵn sàng không chặn dùng ảnh khi video không bắt buộc theo brief; nếu bắt buộc thì cần quy ước skip/approval rõ.
- URL là HTTP(S) hoặc route cùng origin `/media/...`, `/assets/...`, `/api/.../download`, có kiểm quyền. Không trả đường dẫn máy, storage key/credential hoặc provider token.
- Lưu provenance: ảnh gốc, newly generated, cache/replay/fallback; không gắn nhãn “vừa tạo thành công” cho file fallback. Listing gốc và asset còn được replay tham chiếu phải giữ đọc được.
- `mode=live` chỉ nói model/provider có thể được gọi thật; market vẫn mô phỏng. Proof và analytics phải biết nguồn `simulation|replay|test` ở canonical metadata; không trộn fixture preview với dữ liệu run.

## 9. Tracking mở rộng từ workbook

Đây là backlog data, chưa phải endpoint UI đã gửi. Giữ causal chain `opportunity_id → brief_version → proposal/offer_id + version → decision_id → apply_id`, cùng run/shop/product và nguồn dữ liệu.

- `card_sent` không chứng minh `offer_viewed`; `content_job:done` của một ảnh không chứng minh cả draft ready hoặc seller đã xem.
- Agent accept không là seller accept; seller accept không là primary conversion. Primary conversion chỉ khi package apply đã commit; retry không tăng bộ đếm.
- Content funnel có mẫu số riêng là gói đã duyệt có content_refresh; version sửa không tạo brief/conversion mới.
- Defer, reject, no_fit và technical failure là outcome khác nhau. Return/retention là cohort riêng, không gộp vào funnel lồng nhau.
- Không tính latency từ `HH:MM`; lưu timestamps có độ chính xác và đơn vị, operation/task IDs. Không dùng UI polling duration làm thời gian model xử lý.
- Mốc 7 ngày cohort và mô phỏng 7 ngày không phải cùng chỉ số; lưu window start/end và đơn vị đo. Chưa có dữ liệu thì để unavailable, không dựng CR thắng.

## 10. Fixture và tiêu chí nghiệm thu data

Backend cần fixture deterministic cho các ca: đồng ý vòng 1; code fail → counter → accept; hết vòng/no_fit; seller thương lượng lại attempt2; reject; question-only khi campaign cũ đang chạy; gói không content; provider failed/cached; stale draft; replay fork; ngày 7 complete. Các fixture backend không lấy số proof minh họa của preview làm kết quả thực nghiệm.

Kiểm tra tối thiểu:

1. Hai seller/run cùng shop D không đọc được dữ liệu của nhau; private event bị lọc nhưng cursor vẫn tiến đúng.
2. Reload ở giữa một tác vụ khôi phục đúng attempt/round và package diff; snapshot cũ không làm running sống lại.
3. Events out-of-order theo thời gian ghi nhãn vẫn xếp theo seq; reconnect không nhân đôi history.
4. Duplicate request, concurrent decision, stale card/rules/draft và late worker result không tạo spend/publication lần hai.
5. Chỉ có package/campaign đã commit mới được tính applied; original listing không đổi sau apply.
6. Null ROAS/forecast không biến thành 0, tiền/phần trăm đúng đơn vị, forecast và metric so cùng kỳ.
7. LLM/provider thất bại có nguồn fallback và kết quả thật; không tự gọi paid API khi replay thiếu cache.
8. Ngày cuối next_day=null/complete; không sinh ngày 8, không lặp settlement/learning.

Các thay đổi schema/DTO/enum chưa có trong CONTRACT phải được data/backend owner đưa vào hợp đồng và fixture chung trước khi bật, kèm test phân quyền và transaction. Frontend hiện không tạo database, migration, tracking endpoint hay provider job thật.
