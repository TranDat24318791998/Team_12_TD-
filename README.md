# Growth Agents · Team 12

Dự án cho SEAxOpenAI Hackathon: hai agent đại diện sàn và shop thương lượng gói tăng trưởng trên một thị trường mô phỏng. Người bán duyệt đề xuất và nội dung; hệ thống ghi nhận kết quả để học qua bộ nhớ mỗi tối.

## Trạng thái

Core Agent + Tools + Knowledge đã có code và test headless với fixture market/media; xem [runbook phần Toàn](docs/plans/toan/DEMO_RUNBOOK.md). Frontend React có 5 màn hình và preview 7 ngày. Data service local đã được team triển khai riêng trong `data/`; route, market và media cần ghép với agent trước khi chạy toàn sản phẩm bằng dữ liệu thật.

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
| `frontend/` | React, CSS, ảnh, bundle phục vụ trực tiếp qua FastAPI |
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

## Frontend React

Bundle đã được tạo tại `frontend/js/app.js`; FastAPI hiện phục vụ `frontend/` tại `/`. Mở http://localhost:8000/?preview=1 để thử giao diện cam với dữ liệu mẫu, hoặc `?preview=0` để gọi 9 API của backend. Bản xem trước không gọi API trả phí và không phải bằng chứng thực nghiệm.

Để sửa và build lại giao diện, dùng Node 20 trở lên:

```sh
cd frontend
npm install
npm run build
npm test
```

`npm run dev` theo dõi source và build lại; trình duyệt vẫn mở qua FastAPI. Để xem riêng frontend khi chưa cài backend, chạy `python3 -m http.server 8000 --directory frontend` tại gốc repo, rồi mở `/?preview=1`.

Xem [bàn giao React và ghép dữ liệu](docs/FRONTEND_HANDOFF.md). Giao diện theo [thiết kế dữ liệu v1.1](data/growth_agents_data_api_design.md): 7 ngày, `complete`, `next_day=null` ở ngày cuối và Idempotency-Key cho thao tác ghi. Các endpoint `/api/v1` có envelope do backend adapter xử lý; frontend tiếp tục dùng 9 endpoint `/api/*` dành cho seller.

## Requirement for frontend

Agent backend đọc [yêu cầu tích hợp giao diện](docs/FRONTEND_REQUIREMENTS.md) trước khi nối workflow/API: mapping state/events sang sơ đồ hai agent, payload telemetry/trọng tài, polling và checklist nghiệm thu. Khối tương tác mới nằm ở `frontend/src/components/AgentActivity.jsx`, projection ở `frontend/src/activity.js`.

Agent data đọc [yêu cầu về data](docs/FRONTEND_DATA_REQUIREMENTS.md): grain và identity, quan hệ đề xuất–duyệt–áp dụng, phiên bản, cursor, quyền public/private, nguồn số liệu và transaction. Các mở rộng chưa có trong hợp đồng được ghi `TODO(contract)`; backend thật cần thống nhất trước khi bật. Bản `?preview=1` đã minh họa luồng; bản `?preview=0` chờ các API nghiệp vụ.

## Tài liệu và phân công

- [Plan riêng của Toàn — Agent + Tools + Knowledge](docs/plans/toan/README.md): toàn bộ đặc tả, task code và hướng dẫn review trong `docs/plans/toan/`.
- [Hợp đồng runtime/demo dùng chung](docs/DEMO_CONTRACT.md): đầu nối giữa agent, dữ liệu, API và media.

- [AGENTS.md](AGENTS.md): quy ước, công nghệ và các nguyên tắc bắt buộc.
- [Kiến trúc codebase](docs/ARCHITECTURE.md): cây thư mục, trách nhiệm module và hướng phụ thuộc.
- [Danh sách task](docs/TASKS.md): 32 task và mốc ghép nối của 4 thành viên.
- [Hợp đồng chung](docs/CONTRACT.md), [dữ liệu mẫu](docs/SEED_DATA.md), [thiết kế](docs/DESIGN.md).
- `app/`: backend; `frontend/`: giao diện; `tests/`: kiểm thử.
- `data/`, `assets/products/`, `contracts/`: dữ liệu, ảnh gốc và JSON mẫu.
- `replay/`, `media/replay/`: bản phát lại được đưa vào Git; `runs/` và media sinh mới chỉ lưu cục bộ.
- [Bàn giao frontend](docs/FRONTEND_HANDOFF.md): cấu trúc React, dữ liệu, cách build và kết quả kiểm tra.

## Link demo

## Thử nghiệm video marketing

`experiment/` là dịch vụ FastAPI độc lập cho OpenAI script/ảnh/giọng, render local, lưu MinIO và phát video qua Cloudflare Tunnel. Xem [hướng dẫn experiment](experiment/README.md). Từ gốc repo, chạy `cd experiment` trước các lệnh trong hướng dẫn; dùng môi trường `.venv` riêng của experiment.

## Video demo
