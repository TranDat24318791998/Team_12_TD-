# Demo Agent + Tools + Knowledge trên Data local

Bản product hiện dùng Data SQLite, native worker và React; lệnh host/cấu hình/khôi phục nằm ở [LOCAL_RUN](../../LOCAL_RUN.md), hợp đồng ở [DEMO_CONTRACT](../../DEMO_CONTRACT.md). Kết quả nghiệm thu và giới hạn thực tế nằm ở [implementation status](full-integration/IMPLEMENTATION_STATUS.md). Các mô tả SessionManager/chưa nối DB trước ngày 31/10/2026 đã được thay bởi [plan tích hợp](full-integration/README.md).

## Chuẩn bị

1. Chạy `.venv/bin/python scripts/local_stack.py status`. Nếu chưa chạy, dùng `start`; media8010 và app8000 phải READY. Startup không tạo paid job. Chọn mode trước khi start; đổi mode cần stop/start giữ DB.
2. Mở `http://127.0.0.1:8000/?preview=0`. D là quạt để bàn đã được người dùng chọn, ảnh gốc `assets/products/demo-d-desktop.jpg`; kinh doanh vẫn mô phỏng.
3. Xác nhận brief, bấm Bắt đầu ngày. UI mở hội thoại trong khi worker xử lý. Theo dõi source của từng invocation: live, replay có binding hoặc offline.

## Luồng trình bày

1. Agent sàn đọc dữ liệu công khai và dự báo; agent shop đọc Rules/giá vốn riêng. Tools tính số, Referee kiểm gói, Data tạo card.
2. Seller duyệt card đúng version. Nếu cần refresh, campaign chỉ active sau khi content được áp dụng.
3. Content Agent đọc facts/style đã xác nhận. Live media tạo cover A, video từ A, rồi B/C. Có thể góp ý nền sáng và làm lại toàn bộ attempt (tối đa ba attempt).
4. Chọn ảnh; xem review video. Review chưa pass cần seller ack hoặc bỏ video. File cover phải hợp lệ. Chỉ Apply mới đổi listing.
5. Kết thúc ngày: Data settlement một lần; Learning dùng public evidence frozen và ghi History/Calibration/Lessons/preferences/skill versions trong cùng SQLite. Ngày sau agent đọc memory và policy được pin đúng ngày.
6. Seller xác nhận sở thích mới rồi Content mới dùng làm mặc định. Memory không tự đổi Rules.
7. Màn Proof dùng comparison thật đã attach vào Data. ON/OFF cùng seed/horizon/config; kết quả có thể tăng lợi nhuận và giảm số đơn. Không diễn giải fixture hoặc offline simulation là hiệu quả thị trường thật.

## Kiểm không trả phí

Chạy tests/host offline theo LOCAL_RUN. `scripts/run_agent_demo.py --mode offline --seed 42` vẫn là **core harness** với market/media fixture, dùng kiểm native protocol và memory; không thay thế acceptance của Data/local product. `scripts/run_sim.py --help` chỉ ra CLI cho Data ON/OFF với fake media được gắn nhãn; artifacts dưới ignored `runs/`.

## Giới hạn phải nói đúng

Có credentials/model lookup thành công chưa chứng minh OpenAI Images/Muse generation. Chỉ ghi MEDIA_LIVE/PROVIDER_EVAL PASS khi thật sự có output đã kiểm. Imported video từ máy đồng nghiệp có provenance cache, không phải output được bản local tạo. Nếu provider outcome unknown, giữ reservation và báo trạng thái; không tạo request key mới để thử lại tự động.
