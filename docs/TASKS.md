# Bộ task cho Codex · Growth Agents

Bộ file này chia dự án thành 32 task, mỗi task một file, để 4 người giao cho Codex làm song song trong ngày thi (31/10/2026, 10:00–17:00). Đây là bảng kế hoạch; trạng thái code hiện tại nằm trong README và CODEX_LOG. Các file task đã cập nhật đường dẫn theo `docs/ARCHITECTURE.md`.

## Cách dùng

1. **10:00 · TV1 làm task 1.1**: tạo repo công khai mới, chép `AGENTS.md`, thư mục `docs/` và `tasks/` vào gốc repo. Codex tự đọc `AGENTS.md` ở gốc repo.
2. **10:15–10:30 · cả team đọc `docs/CONTRACT.md`** và chốt. Sau mốc này chỉ đổi khi cả team đồng ý.
3. Mỗi người mở Codex trong repo, làm lần lượt task của mình. Với mỗi task, dán đoạn trong mục **Lệnh cho Codex** ở cuối file task.
4. Codex xong thì đọc báo cáo test, chạy thử, commit với mã task (ví dụ `[2.3] market: giả lập thị trường`), ghi một dòng vào `docs/CODEX_LOG.md`.
5. Task phụ thuộc module chưa xong: Codex dùng bản giả đúng chữ ký trong `CONTRACT.md` mục 4, hoặc JSON trong `contracts/`.

## Tài liệu chung

| File | Nội dung |
| --- | --- |
| `AGENTS.md` | Dự án là gì, công nghệ, cấu trúc thư mục, biến môi trường, 10 nguyên tắc bắt buộc, cách làm một task |
| `docs/CONTRACT.md` | Model dữ liệu, loại sự kiện, 9 API, chữ ký hàm giữa các module |
| `docs/SEED_DATA.md` | 5 shop, trend, phí sàn giả định, hằng số, kết quả phải ra ở ngày 1 |
| `docs/DESIGN.md` | Màu, chữ, 5 màn hình |

## Danh sách task

| Task | File | Người | Giờ | Cần có trước |
| --- | --- | --- | --- | --- |
| 1.1 Tạo repo | `tasks/TV1-1.1-tao-repo.md` | TV1 | 10:00–10:30 | — |
| 1.2 Schema, Session, JSON mẫu | `tasks/TV1-1.2-schema.md` | TV1 | 10:30–11:00 | 1.1 |
| 1.3 Luật bằng code | `tasks/TV1-1.3-luat-bang-code.md` | TV1 | 11:00–11:40 | 1.2, 2.1 |
| 1.4 Lớp gọi LLM | `tasks/TV1-1.4-lop-goi-llm.md` | TV1 | 11:40–12:10 | 1.2 |
| 1.5 Hai agent thương lượng | `tasks/TV1-1.5-thuong-luong.md` | TV1 | 12:10–13:30 | 1.3, 1.4, (2.4) |
| 1.6 Luồng một ngày | `tasks/TV1-1.6-luong-mot-ngay.md` | TV1 | 13:30–14:30 | 1.5, 2.3, (4.5) |
| 1.7 Langfuse (tuỳ chọn) | `tasks/TV1-1.7-langfuse.md` | TV1 | 14:30–15:00 | 1.5 |
| 1.8 Ghép nối, kiểm thử đầu-cuối | `tasks/TV1-1.8-ghep-noi.md` | TV1 | 15:00–16:00 | 1.6, 2.5, 3.5, 4.5 |
| 2.1 Dữ liệu giả | `tasks/TV2-2.1-du-lieu-gia.md` | TV2 | 10:30–11:00 | 1.1 |
| 2.2 Database | `tasks/TV2-2.2-database.md` | TV2 | 11:00–11:30 | 1.2 |
| 2.3 Giả lập thị trường | `tasks/TV2-2.3-gia-lap-thi-truong.md` | TV2 | 11:30–12:30 | 2.1, 1.3 |
| 2.4 Bộ nhớ | `tasks/TV2-2.4-bo-nho.md` | TV2 | 12:30–13:15 | 2.2 |
| 2.5 Học ban đêm | `tasks/TV2-2.5-hoc-ban-dem.md` | TV2 | 13:15–14:30 | 2.3, 2.4, 1.4 |
| 2.6 Chạy 6 ngày, đối chứng | `tasks/TV2-2.6-chay-6-ngay-doi-chung.md` | TV2 | 14:30–15:15 | 1.6, 2.5 |
| 2.7 Ghi bản phát lại | `tasks/TV2-2.7-ghi-ban-phat-lai.md` | TV2 | 15:30–16:00 | 2.6, 4.5 |
| 3.1 Deploy khung | `tasks/TV3-3.1-deploy-khung.md` | TV3 | 10:00–11:00 | 1.1 |
| 3.2 API dữ liệu mẫu | `tasks/TV3-3.2-api-du-lieu-mau.md` | TV3 | 11:00–11:45 | 1.2 |
| 3.3 Màn 1 · Trang shop | `tasks/TV3-3.3-man-1-trang-shop.md` | TV3 | 11:45–13:00 | 3.2 |
| 3.4 Màn 2 · Demo | `tasks/TV3-3.4-man-2-demo.md` | TV3 | 13:00–14:30 | 3.3 |
| 3.5 Nối API thật | `tasks/TV3-3.5-noi-api-that.md` | TV3 | 14:30–15:15 | 1.6, 2.5, 3.4, 4.5 |
| 3.6 Màn 3, 4, 5 | `tasks/TV3-3.6-man-3-4-5.md` | TV3 | 15:15–15:45 | 3.5, 2.6 |
| 3.7 Deploy cuối | `tasks/TV3-3.7-deploy-cuoi.md` | TV3 | 15:45–16:30 | 2.7, 3.6 |
| 4.1 Kiểm tra khoá | `tasks/TV4-4.1-kiem-tra-khoa.md` | TV4 | 10:00–10:30 | 1.1 |
| 4.2 Agent nội dung · chữ | `tasks/TV4-4.2-agent-noi-dung-chu.md` | TV4 | 10:30–11:15 | 1.2, 2.1 |
| 4.3 Ảnh bìa | `tasks/TV4-4.3-anh-bia.md` | TV4 | 11:15–12:15 | 4.1, 4.2 |
| 4.4 Video qua Muse | `tasks/TV4-4.4-video-muse.md` | TV4 | 12:15–13:30 | 4.1, 4.3 |
| 4.5 Điều phối nội dung | `tasks/TV4-4.5-noi-noi-dung-vao-luong.md` | TV4 | 13:30–14:15 | 4.2–4.4 |
| 4.6 Nhật ký Codex | `tasks/TV4-4.6-nhat-ky-codex.md` | cả team | suốt ngày | — |
| 4.7 Bài viết PDF | `tasks/TV4-4.7-bai-viet.md` | TV4 | 14:15–15:30 | 2.6, 4.6 |
| 4.8 Bản khai báo PDF | `tasks/TV4-4.8-ban-khai-bao.md` | TV4 | 15:30–15:50 | — |
| 4.9 Video dự phòng | `tasks/TV4-4.9-video-du-phong.md` | TV4 | 15:50–16:30 | 3.7 |
| 4.10 Nộp bài | `tasks/TV4-4.10-nop-form.md` | cả team | 16:30–16:45 | tất cả |

## Mốc ghép nối

| Mốc | Giờ | Phải đạt |
| --- | --- | --- |
| Mốc 1 | 11:00 | Link deploy khung mở được; `data/seed.json` xong; `scripts/check_keys.py` đạt |
| Mốc 2 | 13:30 | Một cuộc thương lượng chạy ở terminal; màn 1–2 chạy với `MOCK_API=1`; tạo thử được ảnh và một video |
| Mốc 3 | 14:30 | Một ngày chạy trọn qua API thật, gồm học ban đêm |
| Ngừng thêm tính năng | 15:30 | Chỉ sửa lỗi, chạy 6 ngày, ghi bản phát lại |
| Nộp | 16:45 | Google Form đã nộp |

Thứ tự cắt bớt khi trễ: 1.7 Langfuse → nút EN → video (giữ ảnh, chữ) → chế độ chạy trực tiếp (chỉ phát lại) → màn 3.

## Lưu ý về luật thi

Luật không cho mang code viết sẵn. Bộ file này chỉ là kế hoạch, đặc tả và dữ liệu mẫu dạng bảng; mọi code do Codex viết trong ngày. Đọc lại luật để chắc loại tài liệu nào được mang vào, và ghi đúng phần chuẩn bị trước trong bản khai báo (task 4.8).
