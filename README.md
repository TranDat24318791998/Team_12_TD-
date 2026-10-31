# Growth Agents · Team 12

Dự án cho SEAxOpenAI Hackathon: hai agent đại diện sàn và shop thương lượng gói tăng trưởng trên một thị trường mô phỏng. Người bán duyệt đề xuất và nội dung; hệ thống ghi nhận kết quả để học qua bộ nhớ mỗi tối.

## Trạng thái

Đã dựng khung dự án theo task 1.1: cấu hình, FastAPI, trang tĩnh và kiểm tra sức khoẻ. Các module nghiệp vụ hiện là khung, chưa có luồng demo hoàn chỉnh.

## Cài đặt và chạy

Cần Python 3.11 và Git. Chạy từ thư mục gốc repo:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Mở http://localhost:8000/; kiểm tra http://localhost:8000/health sẽ nhận `{"ok": true}`. Khi chưa có khoá API, cấu hình mặc định chạy offline; khung hiện tại không gọi dịch vụ trả phí.

Điền khoá vào `.env` trên máy hoặc Secrets của host. Không commit `.env`. Các biến model dùng tên model tài khoản được cấp.

```sh
pytest -q
python -m pip check
git check-ignore .env
```

## Tài liệu và phân công

- [AGENTS.md](AGENTS.md): quy ước, công nghệ và các nguyên tắc bắt buộc.
- [Kiến trúc codebase](docs/ARCHITECTURE.md): cây thư mục, trách nhiệm module và hướng phụ thuộc.
- [Danh sách task](docs/TASKS.md): 32 task và mốc ghép nối của 4 thành viên.
- [Hợp đồng chung](docs/CONTRACT.md), [dữ liệu mẫu](docs/SEED_DATA.md), [thiết kế](docs/DESIGN.md).
- `app/`: backend; `static/`: giao diện; `tests/`: kiểm thử.
- `data/`, `assets/products/`, `contracts/`: dữ liệu, ảnh gốc và JSON mẫu.
- `replay/`, `media/replay/`: bản phát lại được đưa vào Git; `runs/` và media sinh mới chỉ lưu cục bộ.
- [Nhật ký Codex](docs/CODEX_LOG.md): việc thực hiện và kết quả kiểm thử.

## Link demo

## Video demo
