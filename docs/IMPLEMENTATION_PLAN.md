# Kế hoạch demo trong dưới 2 giờ

Ngày lập: 31/10/2026. Baseline: `main` tại `61412f7`. Đây là bộ giao việc, chưa phải tính năng đã được triển khai.

Yêu cầu hiện hành: ưu tiên luồng chính cho hackathon; agent nhỏ viết code, agent khác review. OpenAI cho toàn bộ LLM và ảnh; video dùng Muse Gateway của người dùng. Base/token Muse đã có trong cấu hình local; key/model OpenAI để trống để cập nhật sau. Chưa gọi dịch vụ trả phí trong lúc lập plan.

## 1. Kết quả phải trình diễn

Trong khoảng 3 phút thao tác, không tính thời gian provider render:

1. Mở shop D, xem listing gốc và xác nhận mục tiêu tăng đơn, giữ luật tài chính riêng.
2. Bấm bắt đầu. Agent sàn đề xuất, agent shop phản đề xuất, trọng tài nhận xét đúng mục tiêu. Code kiểm tra từng lượt.
3. Kết quả offline chuẩn: 45.000đ/ngày, voucher 3%, stop ROAS 6,5, thời hạn 3 ngày. Khi dùng LLM thật, gói phải hợp lệ; không ép model diễn lại đúng một transcript.
4. Seller duyệt gói. Chưa áp dụng quảng cáo. Content bắt đầu tạo chữ, ba ảnh A/B/C và video qua API nền.
5. Seller góp ý một lần, ví dụ `Ảnh nền tối quá, dùng nền sáng hơn`. Draft mới có version mới. Chọn cover, xem video, bấm áp dụng bản này.
6. Listing thay đổi, gói mới active. Bấm kết thúc ngày. Simulator tạo kết quả, learning tạo sở thích ứng viên có evidence.
7. Sang ngày 2: hỏi `Lần sau ưu tiên ảnh nền sáng?`. Seller xác nhận thì mới thay `content_style_notes`; UI cho thấy luật mới và memory đã được đọc.

Không cần đợi ảnh thật tối mới góp ý: đây là yêu cầu phong cách do người demo nhập. Không khẳng định provider đã tạo nền tối nếu hình thực tế sáng.

## 2. Phạm vi khóa

| Bắt buộc cho demo | Cách làm ngắn nhất |
|---|---|
| 5 vai trò AI | Shop/sàn/trọng tài trong graph; Content/Learning chạy theo giai đoạn. Không tạo hệ thống agent tự tìm tool. |
| Shop D ngày 1–2 | Seed vẫn đủ A–E để dùng lại finance; chỉ D chạy tương tác và settlement ở bản chính. |
| LangGraph | Dùng cho thương lượng. Chờ seller bằng `pending_card` và các API; không làm thêm graph ngày có interrupt. |
| Dữ liệu/Knowledge | Seed JSON + facts/fee configuration trong code; context allowlist. Tra tài liệu local khi cần, chưa làm vector indexing. |
| Ảnh/video thật | OpenAI Images + Muse Gateway, job nền và file local. Cấu hình thiếu không được báo thành công. |
| Bộ nhớ | Dict theo run; JSONL event log lưu bằng chứng. Rules authoritative ở Session, gateway đọc cùng object. |
| UI | Một trang, ba vùng: shop, quyết định/nội dung, hậu trường. Không dựng năm trang riêng. |
| API | 9 route cũ và `/api/brief/confirm`; thêm field cần cho version và media. |
| Lỗi thiết yếu | LLM fallback; media failed có lý do; version cũ bị chặn; apply/night không lặp tác dụng. |

Để sau: nhiều user, đăng nhập, API `/api/v1` toàn bộ, D1/R2, SQLite migrations, retry queue/lease, resume sau restart, anti-spam/rate limit, free chat, intent ngoài `increase_orders`, defer/reminder, 3D, undo, catalog campaign thật, analytics conversion đầy đủ, auto-deploy. `/api/proof` trả chưa có dữ liệu khi chưa chạy đối chứng; không dùng số giả.

Không cắt bốn điều: tài chính do code tính; không lộ private sang sàn/trọng tài; seller duyệt đúng phiên bản trước khi áp dụng; lỗi/provider pending không biến thành thành công.

## 3. Tài liệu nào quyết định implementation

- [DEMO_CONTRACT.md](DEMO_CONTRACT.md) là hợp đồng hẹp cho đợt demo này: field, API, state và các ngoại lệ so với kế hoạch đầy đủ.
- [CONTRACT.md](CONTRACT.md) dùng cho các model/chữ ký được giữ nguyên; [SEED_DATA.md](SEED_DATA.md) giữ các số A–E và phí.
- [ARCHITECTURE.md](ARCHITECTURE.md) giữ vị trí module/hướng import.
- [MUSE_API.md](MUSE_API.md) khóa wire contract video, các trường đã xác minh và phần cần capture từ response thật.
- Workbook `resources/w/Growth Agents - Customer Journey & Agents.xlsx` cung cấp vai trò trọng tài, intent, phê duyệt và cách đo; các nhánh bị cắt đã ghi ở mục 2.
- Thiết kế `data/growth_agents_data_api_design.md` là đích đầy đủ. Đợt demo không tuyên bố đã triển khai Data API đó. Chuyển store/provider sau demo, không viết hai nguồn rules hôm nay.

Các khác biệt có chủ ý: D-only, 2 ngày tương tác; strict accept phải giữ nguyên package; ba bản nội dung tổng cộng; cập nhật rules chỉ qua seller handler; trạng thái phiên không phục hồi sau restart. Full proof vẫn là 7 ngày nếu được làm thêm, không đổi thành proof 2 ngày.

## 4. Lịch thực hiện và điểm cắt

Ước lượng 110 phút implementation + review, chừa 10 phút dự phòng. Đây là timebox để quyết định cắt phạm vi, không cam kết mọi API bên ngoài sẽ trả kịp.

| Mốc | Agent code | Agent review | Điều kiện qua |
|---|---|---|---|
| 0–7 phút | D00: contract, môi trường, input/provider checklist | Đối chiếu schema và scope | Không còn hai tên khác nhau cho cùng field |
| 7–23 | D01: models, seed, finance, state, event/store | Review ngay patch finance đầu | D 3% hợp lệ, 4% bị chặn khi ads |
| 23–42 | D02: sàn/shop/trọng tài + graph + fallback | Test privacy, round count, strict accept | Terminal trả kết quả D hợp lệ |
| 42–58 | D03: API và seller approval | Test gate apply và request version | Flow chạy qua API với fake content |
| 58–78 | D05a + phần backend D05: media adapters/job/service | Mock provider, kiểm callback cũ | Fake job chạy async đủ ảnh và video |
| 78–88 | D04: simulation + learning ngày 1–2 | Rule confirmation, no double night | Candidate chỉ thành rule sau Yes |
| 88–101 | Phần frontend D05 | Thử luồng UI + browser console | Từ brief tới ngày 2 không cần sửa state tay |
| 101–110 | D06: end-to-end, nối config thật nếu đã có | Review bản cuối và thực tập demo | Có checklist kết quả + giới hạn thực tế |
| 110–120 | Chỉ sửa lỗi chặn demo; chờ media/render | Ghi lại video/quy trình dự phòng | Không thêm tính năng |

OpenAI chưa được điền lúc phút 101: bàn giao phần đã kiểm bằng client giả, hiển thị `Chưa cấu hình API`; chưa đánh dấu tạo ảnh/LLM live đạt. Muse đã có base/key nhưng response job chưa được kiểm thật. Chạy smoke sau D05a trong lúc UI được làm để thời gian render không nằm cuối buổi; chuẩn bị cache thật của bản đầu và bản chỉnh sáng, ghi nhãn cached khi trình diễn.

Nếu có thêm người code, chỉ song song hai lane sau D01: lane A D02→D03→D04, lane B D05a→D05. Một integrator giữ `app/api`, `runtime/session.py`, `main.py`, schema và fixtures. Reviewer đọc cả hai, không tự tạo branch/merge trong lúc coder cùng ghi file. Nếu chỉ 1 coder + 1 reviewer, dùng lịch tuần tự ở trên.

## 5. Task packets

Mỗi lần chỉ đưa agent code một task. Bắt đầu với D00; đọc contract rồi đúng task, không nạp toàn bộ 32 task gốc.

| ID | File giao việc | Output chính |
|---|---|---|
| D00 | [00-start.md](../tasks/demo/00-start.md) | Contract/fixtures và checklist API/ảnh nguồn |
| D01 | [01-foundation.md](../tasks/demo/01-foundation.md) | Models, seed, finance/privacy, Session/store/log |
| D02 | [02-agents-referee.md](../tasks/demo/02-agents-referee.md) | Structured LLM, 3 agent, negotiation graph |
| D03 | [03-workflow-api.md](../tasks/demo/03-workflow-api.md) | Brief, approve, content gates, 10 API |
| D04 | [04-learning.md](../tasks/demo/04-learning.md) | D metrics, evidence, preference, ngày 2 |
| D05a | [05a-media-api.md](../tasks/demo/05a-media-api.md) | Client ảnh/video, job nền và cache |
| D05 | [05-ui-content.md](../tasks/demo/05-ui-content.md) | Content service và UI một trang |
| D06 | [06-review-demo.md](../tasks/demo/06-review-demo.md) | Review độc lập, end-to-end, rehearsal |

## 6. Cách giao coder và reviewer

### Prompt cho agent code

```text
Làm task Dxx tại tasks/demo/<file>.md trên main của repo Team_12_TD-.
Đọc AGENTS.md, docs/DEMO_CONTRACT.md, rồi task này.
Đây là demo dưới 2 giờ; chỉ làm Output và acceptance của task, không triển khai phần để sau.
Giữ số liệu SEED_DATA. Khi dependency chưa có, dùng fake có cùng interface trong tests/fakes/.
Hoàn thành caller, API schema và fixture nào task liệt kê, không chỉ viết helper độc lập.
Chạy test được ghi trong task. Báo BASE_SHA, HEAD_SHA (nếu đã commit), file đổi,
lệnh/kết quả test, ví dụ input/output, chỗ chưa nối thật. Không ghi token vào output.
Nếu contract có mâu thuẫn ảnh hưởng output, nêu đúng hai đoạn; không tự dựng framework để né.
```

### Prompt cho agent review

```text
Review task Dxx so với docs/DEMO_CONTRACT.md và tasks/demo/<file>.md.
Đọc diff từ BASE_SHA tới HEAD_SHA và các caller liên quan; chạy test trọng tâm.
Chỉ chặn khi sai luồng demo, sai tiền, rò private, bỏ qua seller approval,
không kiểm phiên bản media, tác dụng lặp, bịa thành công/kết quả, hoặc test bắt buộc fail.
Không yêu cầu auth/multiuser/queue/rate limit/DB migrations đã nằm ngoài scope.
Mỗi lỗi: mức độ, file:dòng, input tái hiện, kết quả sai, thay đổi tối thiểu, test cần chạy.
Kết luận PASS hoặc FIX REQUIRED; giới hạn còn lại ghi DEFERRED, không biến thành blocker.
Không sửa code đồng thời với coder. Không duyệt chỉ vì tên file/model trông đúng.
```

Review nối tiếp patch nhỏ: D01 finance trước khi review store; D02 context trước graph; D05a fake HTTP trước live smoke. Coder ghi commit `[Dxx] ...` khi slice qua test, reviewer dùng SHA đó. Làm trên main theo yêu cầu; không force-push, không tự đè commit người khác.

## 7. Điều kiện demo đạt

- Luồng D ngày 1→2 qua UI thực; không sửa Session bằng console.
- D qua finance/privacy đúng; trọng tài có lý do ngắn/evidence, không đọc private.
- Gói chỉ active sau approval cần thiết; content retry đổi version, callback cũ không đổi bản đang xem.
- API media thật đã trả ít nhất một bộ ảnh/video có thể mở nếu config đã được cung cấp. Nếu chưa có config, ghi chính xác phần chưa xác nhận; mock không thay tiêu chí này.
- Memory có evidence, hỏi xác nhận và đọc lại; không hứa calibration cải thiện sau 1–2 mẫu.
- `pytest -q` qua với toàn bộ provider giả; có trace/demo log thực, không in secrets.

Nếu quá giờ: bỏ negotiate lần 2, UI phụ, proof, calibration chart, màn so sánh trước/sau riêng. Giữ intent, trọng tài, seller approval, media thật, một lần retry và memory confirmation. Nếu video trễ, seller được chọn bỏ qua video rõ ràng; đây là demo suy giảm, không báo đã đạt phần video.
