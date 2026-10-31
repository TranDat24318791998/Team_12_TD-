# Growth Agents · Team 12

Dự án cho SEAxOpenAI Hackathon: hai agent đại diện sàn và shop thương lượng gói tăng trưởng trên một thị trường mô phỏng. Người bán duyệt đề xuất và nội dung; hệ thống ghi nhận kết quả để học qua bộ nhớ mỗi tối.

## Trạng thái

Khung task 1.1 đã được tổ chức theo package nghiệp vụ. Settings, app factory, `/health` và frontend tĩnh chạy được; agent, thị trường và bộ nhớ hiện là khung để triển khai theo từng task.

## Cấu trúc codebase

| Khu vực | Trách nhiệm |
| --- | --- |
| `app/api/` | Router theo tài nguyên, HTTP schema và dependency |
| `app/domain/` | Model chia theo nghiệp vụ, công thức tiền, validators và privacy |
| `app/runtime/` | Session, SessionManager và workflow một ngày |
| `app/negotiation/` | Hai agent, prompt và graph thương lượng |
| `app/content/` | Tạo, góp ý và áp dụng nội dung |
| `app/memory/` | Quyền đọc bộ nhớ, học ban đêm và prompt riêng |
| `app/simulation/` | Seed world, thị trường và chạy đối chứng |
| `app/infrastructure/` | Client LLM/ảnh/Muse, SQLite/store và tracing |
| `app/core/` | Biến môi trường và đường dẫn |
| `frontend/` | HTML/CSS/JS thuần |
| `tests/unit/`, `tests/integration/` | Kiểm thử theo package và luồng ghép nối |

Xem [kiến trúc chi tiết](docs/ARCHITECTURE.md) để biết hướng import, chủ sở hữu module và model.

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

- [Plan Agent + Tools + Knowledge dưới 2 giờ](docs/IMPLEMENTATION_PLAN.md): phần Toàn nhận, lịch coder/reviewer, native tool loop và knowledge đủ năm ngăn.
- [Hợp đồng agent/tool](docs/AGENT_TOOL_KNOWLEDGE.md), [Knowledge](docs/KNOWLEDGE_CONTRACT.md), [mapping 15 adapter/32 mục Excel](docs/AGENT_SCOPE_MAP.md); [hợp đồng runtime/demo](docs/DEMO_CONTRACT.md).

- [AGENTS.md](AGENTS.md): quy ước, công nghệ và các nguyên tắc bắt buộc.
- [Kiến trúc codebase](docs/ARCHITECTURE.md): cây thư mục, trách nhiệm module và hướng phụ thuộc.
- [Danh sách task](docs/TASKS.md): 32 task và mốc ghép nối của 4 thành viên.
- [Hợp đồng chung](docs/CONTRACT.md), [dữ liệu mẫu](docs/SEED_DATA.md), [thiết kế](docs/DESIGN.md).
- `app/`: backend; `frontend/`: giao diện; `tests/`: kiểm thử.
- `data/`, `assets/products/`, `contracts/`: dữ liệu, ảnh gốc và JSON mẫu.
- `replay/`, `media/replay/`: bản phát lại được đưa vào Git; `runs/` và media sinh mới chỉ lưu cục bộ.
- [Nhật ký Codex](docs/CODEX_LOG.md): việc thực hiện và kết quả kiểm thử.

## Link demo

## Video demo
