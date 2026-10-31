# Thiết kế giao diện

Bản thiết kế gốc là 6 artboard trên canvas "Màn hình demo Growth Agents" (bản xuất ảnh để trong `docs/design/` nếu team có). File này mô tả đủ để dựng lại bằng HTML/CSS/JS thuần.

## 1. Nguyên tắc

- Tên sàn hiển thị là `sàn·demo`. Không dùng tên, logo hay giao diện của sàn thật nào.
- **Màu sáng là thứ người bán thấy; màu xanh đậm là lớp demo** (bảng điều khiển, hậu trường, thanh tiến trình).
- Cam là màu của sàn, xanh dương là phía người bán và agent shop, đỏ đậm là chỗ cần chú ý (nhãn Mới, cảnh báo, chỉ số xấu).
- Chữ tiếng Việt, tiền dạng `45.000đ`, thập phân dấu phẩy. Không emoji; icon là SVG nét.
- Nút thật (`<button>`, `<a>`), ô nhập có `<label>`, vùng bấm tối thiểu 44px.
- Rộng tối đa 1360–1400px; dưới 900px hai cột xếp chồng.

## 2. Màu và chữ

Khai báo trong `static/css/app.css` dưới dạng biến CSS.

| Biến | Giá trị | Dùng cho |
| --- | --- | --- |
| `--brand` | `#D2461A` | thanh trên trang shop, giá, nút chính |
| `--brand-hover` | `#A8380F` | hover |
| `--brand-tint` / `--brand-ink` | `#FDEEE8` / `#B23A12` | nút phụ, chip đang chọn |
| `--alert` | `#9F1D20` | nhãn Mới, chỉ số xấu |
| `--alert-tint` / `--alert-ink` | `#FBE9EA` / `#8E1B1F` | nhãn "Lần 2/3", bài học LLM |
| `--seller` / `--seller-tint` / `--seller-ink` | `#1F4E99` / `#E6EEFB` / `#12305E` | tin nhắn người bán, xác nhận, link |
| `--demo` | `#13254A` | lớp demo |
| `--demo-text` / `--demo-muted` / `--demo-time` | `#EEF2F8` / `#A9B6CF` / `#8F9CB8` | chữ trên lớp demo |
| `--demo-line` / `--demo-block` / `--demo-border` | `#233457` / `#1A2E57` / `#2A4170` | đường kẻ, khối trích dẫn, viền |
| `--bg` / `--surface` / `--border` | `#F5F5F5` / `#FFFFFF` / `#E5E5E5` | nền trang, thẻ, viền |
| `--ink` / `--muted` | `#222222` / `#5B616B` | chữ chính, chữ phụ |
| `--chat-panel` / `--chat-border` / `--bubble-agent` | `#FDE7DE` / `#F6C9B6` / `#FFF1EB` | khung chat bên trái |

Nhãn tác nhân ở hậu trường (nền / chữ, font mono 11px, viết hoa):

| Nhãn | Nền | Chữ |
| --- | --- | --- |
| AGENT SÀN | `#4A1F10` | `#FFB08F` |
| AGENT SHOP, NGƯỜI BÁN | `#1C3766` | `#A9C8FF` |
| CODE KIỂM TRA | `#26324A` | `#D9DEE8` |
| BỘ NHỚ | `#4A1418` | `#FFA8AC` |
| AGENT NỘI DUNG | `#4A3510` | `#FFD08A` |

Kết quả kiểm tra: Hợp luật `#9CC0F5` kèm dấu ✓; Vi phạm `#FF9A8A` kèm dấu ✗ (luôn có chữ, không chỉ dựa vào màu).

Font: Be Vietnam Pro (400, 500, 600, 700) cho chữ thường, JetBrains Mono (500, 600) cho giờ và nhãn, tải từ Google Fonts.

## 3. Năm màn hình

### Màn 1 · `index.html` · Trang shop

- Thanh trên màu cam: chữ `sàn·demo`, ô tìm kiếm (giá trị "quạt mini cầm tay"), Kênh người bán, giỏ hàng.
- Cột trái: ảnh lớn + 4 ảnh nhỏ + ô "Chưa có video"; tiêu đề; đánh giá 4,6 và Kho: 300; khung giá cam 175.000đ; Voucher của shop (Chưa có); chọn màu Trắng/Hồng/Xanh mint; số lượng; nút Thêm vào giỏ hàng, Mua ngay; dải thông tin shop Nhà Bé Lan; Chi tiết và Mô tả sản phẩm.
- Cột phải, khung xanh đậm "Bảng điều khiển demo": nút VI/EN; câu "Bạn đóng vai chị Lan, chủ shop Nhà Bé Lan. Trợ lý của sàn sẽ đề xuất, bạn là người quyết định."; Ngày mô phỏng 1/6, Bộ nhớ Bật, Dữ liệu LLM (Phát lại hoặc Trực tiếp); nút cam **Bắt đầu demo**; nút viền **Đặt lại dữ liệu** (mở hộp xác nhận trước khi gọi `/api/reset`); link "Xem bằng chứng".
- Thẻ trắng "Tín hiệu agent sàn đang thấy": từ khoá +240%/7 ngày, chất lượng listing 0,55/1, trang 3, ghi chú "Dữ liệu giả lập".
- Dữ liệu lấy từ `StateView.demo_shop`.

### Màn 2 · `demo.html` · Demo chia đôi

- Thanh trên xanh đậm: `sàn·demo`, nhãn "CHẾ ĐỘ DEMO · NGÀY n / 6", thanh 6 bước (Phát hiện cơ hội, Hai agent thương lượng, Người bán duyệt, Làm nội dung, Áp dụng, Học ban đêm; bước xong nền `#1F3A6B` chữ `#BFD6FF`, bước hiện tại nền trắng), nút Về trang shop, nút cam Kết thúc ngày.
- **Trái, khung cam nhạt "Kênh người bán · Nhà Bé Lan"**: nhãn "Bạn đang là: chị Lan"; khung chat trắng gồm
  - bong bóng trợ lý (nền `--bubble-agent`, giờ + "Trợ lý tăng trưởng");
  - **thẻ đề xuất**: tiêu đề "Đề xuất gói tăng trưởng · 3 ngày", dấu "Khớp các luật chị đã cài"; danh sách hạng mục (làm mới nội dung: Miễn phí; quảng cáo: x đ/ngày, tối đa y đ cho 3 ngày; voucher: Giảm z%; tự dừng khi ROAS dưới t trong 2 ngày liền); hộp xanh nhạt về ROAS hoà vốn; 2 ô Dự kiến (khoảng đơn) và Lãi ước tính sau phí; mục mở rộng "Vì sao có đề xuất này?"; câu hỏi luật nếu có; nút Đồng ý (cam), Thương lượng thêm (viền cam), Từ chối (chữ xám);
  - sau khi quyết định: thẻ thu gọn với nhãn "Chị đã đồng ý · giờ";
  - bong bóng người bán (nền `--seller-tint`, căn phải);
  - **thẻ nội dung**: "Nội dung mới cho sản phẩm" + nhãn "Lần n / 3"; tiêu đề cũ gạch ngang và tiêu đề mới; mô tả mới; chọn ảnh bìa A/B/C (radio, ảnh đang chọn viền cam + nhãn "Đã chọn"); khối video (khung dọc, nút Xem video, trạng thái "đang tạo, khoảng 1–2 phút" khi chưa xong); chip góp ý trước; ô "Góp ý thêm (còn k lần làm lại)"; nút Làm lại theo góp ý, Dùng bản này;
  - ô nhắn ở đáy (dùng cho Thương lượng thêm).
- **Phải, khung xanh đậm "Hậu trường"**: mô tả "Những gì các agent đang làm. Người bán bình thường không thấy phần này."; nút lọc Tất cả / Thương lượng / Nội dung / Bộ nhớ; hai ô chú thích ai thấy gì; danh sách sự kiện, mỗi dòng: giờ (mono) · nhãn tác nhân (có mũi tên → khi là lượt thương lượng) · câu `text_vi` · khối trích dẫn gói hoặc danh sách kiểm tra · dòng khoá "Chỉ agent shop thấy: …" với `private_note_vi`; dòng cuối có chấm cam "Đang chờ…"; chân khung: Mở trace Langfuse, Nhật ký sự kiện.
- Hậu trường gọi `GET /api/events?after=` mỗi 1,5 giây; chat hiển thị theo `StateView.step`, `pending_card`, `content_draft`.

### Màn 3 · `updated.html` · Trang shop sau khi áp dụng

- Như màn 1, thêm dải xanh đậm dưới thanh trên: "Đã áp dụng lúc hh:mm · 4 thay đổi do trợ lý đề xuất, chị Lan đã duyệt", nút Xem bản cũ, Hoàn tác.
- Nhãn đỏ đậm "Mới" ở ảnh bìa, tiêu đề, mô tả; ô video tối "0:10 · Mới"; voucher "Giảm 3%" viền cam.
- Cột phải "Gói đang chạy · ngày 1/3": trạng thái quảng cáo, ngưỡng dừng, voucher, nội dung; danh sách Thay đổi hôm nay; nút Kết thúc ngày (cam), Mở lại hậu trường, Đặt lại dữ liệu.

### Màn 4 · `night.html` · Tối, hệ thống học được gì

- Tiêu đề "Hệ thống học được gì hôm nay" và câu giải thích: model không được huấn luyện lại, bộ nhớ là dữ liệu có cấu trúc.
- 3 ô số của shop D: đơn thật / dự báo; ROAS hôm nay so với ngưỡng (đỏ đậm nếu dưới ngưỡng); chi quảng cáo.
- 4 thẻ: Lịch sử công khai (Code học), Sở thích người bán (Code học · chị Lan xác nhận, có xem trước câu hỏi sáng mai), Hiệu chỉnh dự báo (chấm tiến độ x/5 điểm, hệ số hiện tại), Bài học chiến lược (LLM đề xuất · code chấm điểm, các thao tác THÊM/TĂNG/GIẢM/LOẠI kèm điểm và bằng chứng).
- Khung xanh đậm "Sáng mai, ai đọc gì": agent sàn đọc gì, agent shop đọc gì.
- Nút Sang ngày tiếp theo (cam), Xem bằng chứng, link file memory_day_n.md.
- Dữ liệu từ `NightSummary`.

### Màn 5 · `proof.html` · Bằng chứng

- Tiêu đề "Hệ thống có thật sự học không?"; câu "Chạy lại cùng kịch bản 6 ngày, cùng seed. Chỉ khác một điều: bộ nhớ bật hay tắt."
- Chú giải: cam = bộ nhớ bật, xám `#B9B6AE` = bộ nhớ tắt.
- Mỗi chỉ số một thẻ: tên, "Cao hơn là tốt"/"Thấp hơn là tốt", hai thanh ngang có số, dòng "Nhờ: <cơ chế>".
- Ghi chú nguồn số liệu; nút Chạy lại từ đầu, Mở trace Langfuse, Tải nhật ký sự kiện.
- Dữ liệu từ `GET /api/proof`.
