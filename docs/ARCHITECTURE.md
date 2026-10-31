# Cấu trúc codebase Growth Agents

Cấu trúc dành cho một ứng dụng FastAPI, một frontend tĩnh và bốn mảng phát triển. Giữ tên module và chữ ký trong `CONTRACT.md` để các task có thể ghép trực tiếp.

## Cây thư mục

```text
Team_12_TD-/
├── AGENTS.md                 Quy tắc làm việc và các nguyên tắc bắt buộc
├── README.md                 Cài đặt, chạy và trạng thái triển khai
├── requirements.txt          Phiên bản thư viện đã kiểm thử
├── .env.example              Tên biến môi trường, không có khoá
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py               Tạo FastAPI, gắn API và static/media
│   ├── api.py                HTTP request/response và lỗi API
│   ├── config.py             Settings, đường dẫn, hằng số nghiệp vụ
│   ├── schemas.py            Model dữ liệu chung
│   ├── session.py            Session và ShopState
│   ├── sessions.py           SessionManager, cookie sid và khoá mỗi phiên
│   ├── data.py               Nạp thế giới mô phỏng từ seed.json
│   ├── validators.py         Tính lãi/hoà vốn, luật và lọc dữ liệu riêng
│   ├── llm.py                Structured output, cache, quota, fallback
│   ├── prompts.py            Prompt và đầu vào đã lọc của agent
│   ├── agents.py             Quyết định LLM và luật offline
│   ├── negotiation.py        Subgraph thương lượng
│   ├── day.py                Graph một ngày, thẻ và người bán duyệt
│   ├── market.py             Thị trường, dự báo, SellerSimulator
│   ├── storage.py            Store bộ nhớ
│   ├── eventlog.py           Nhật ký SQLite
│   ├── memory.py             MemoryGateway và phân quyền
│   ├── night.py              Học từ sự kiện sau mỗi ngày
│   ├── simulation.py         Chạy nhiều ngày, so sánh bật/tắt bộ nhớ
│   ├── tracing.py            Langfuse tuỳ chọn
│   └── content/
│       ├── __init__.py
│       ├── text.py           Tiêu đề và mô tả
│       ├── images.py         Ba phương án ảnh bìa
│       ├── video_muse.py     Client Muse, job và cache video
│       └── service.py        Bản nháp, retry, apply và job nền
├── static/
│   ├── index.html            Trang khởi đầu; hiện là trang tạm
│   ├── css/                  CSS dùng chung
│   └── js/                   JavaScript dùng chung và theo từng màn
├── assets/products/          Ảnh sản phẩm gốc
├── data/                     Dữ liệu seed đầu vào
├── contracts/                JSON mẫu khớp schema/API
├── replay/                   Cache LLM và bằng chứng đã ghi
├── media/
│   └── replay/               Media phát lại được commit
├── runs/                     Database và báo cáo từng run, Git bỏ qua
├── scripts/                  Lệnh kiểm tra, mô phỏng và ghi replay
├── tests/                    Test offline, không gọi dịch vụ trả phí
├── docs/                     Hợp đồng, thiết kế, dữ liệu, kiến trúc, nhật ký
├── tasks/                    32 task với phạm vi output và tiêu chí xong
└── submission/               Bài viết, khai báo và kịch bản nộp bài
```

Các file nghiệp vụ hiện có docstring mô tả trách nhiệm. `data/`, `contracts/` và `replay/` chưa có dữ liệu giả lập; các màn `demo.html`, `updated.html`, `night.html`, `proof.html` được tạo ở task frontend tương ứng.

## Ranh giới giữa các phần

| Phần | Trách nhiệm | Phụ thuộc chính |
| --- | --- | --- |
| `main.py`, `api.py` | Khởi động ứng dụng, đổi dữ liệu HTTP thành model, gọi nghiệp vụ | `sessions`, `schemas`, `day`, `night`, `content.service` |
| `session.py`, `sessions.py` | Sở hữu trạng thái và tài nguyên theo phiên; khởi tạo các service khi nối API thật | `config`, `data`, `storage`, `eventlog`, `llm`, `memory`, `content.service` |
| `day`, `negotiation`, `night`, `simulation` | Điều phối công việc, không chứa chi tiết HTTP của nhà cung cấp | Agent, validators, market, memory và content |
| `validators`, `market` | Tính toán tiền, dự báo và kết quả bằng code | Schema và cấu hình |
| `agents`, `prompts` | Chuẩn bị đầu vào đúng quyền, tạo quyết định và fallback | `llm`, `validators`, dữ liệu đã lọc |
| `llm`, `content.images`, `content.video_muse` | Bao API bên ngoài, timeout, cache và xử lý lỗi | Client HTTP/SDK được truyền vào để thay bằng fake |
| `eventlog`, `storage`, `memory` | Sự kiện bền vững, lưu bộ nhớ và kiểm soát ai đọc được gì | SQLite/store, schema |
| `static` | Hiển thị, gọi API, theo dõi state và events | Hợp đồng JSON |

Quy ước khi triển khai tiếp:

1. Model dùng qua nhiều module đặt ở `schemas.py`; không định nghĩa nhiều bản cùng một model. `FeeConfig` tạm nằm ở `config.py` trong khung 1.1 và sẽ chuyển sang `schemas.py` ở task 1.2; config giữ các giá trị mặc định.
2. `main.py` là nơi lắp ứng dụng. Module nghiệp vụ không import ngược `main.py` hoặc `api.py`; dùng `TYPE_CHECKING` cho type hint nếu cần tránh import vòng.
3. Route chỉ xử lý giao thức HTTP và chuyển việc cho service. Công thức tài chính ở `validators.py`/`market.py`, tránh tính lại trong frontend hoặc prompt.
4. Không giữ trạng thái người dùng trong biến toàn cục của router. Phiên thật được tạo qua `SessionManager`, có khoá và tài nguyên riêng.
5. Agent sàn nhận dữ liệu công khai và `memory.platform_view`; không truyền cả `Session`, `ShopPrivate` hoặc nhật ký thô vào prompt. Mọi lời từ shop gửi sang sàn qua `leak_guard`.
6. Nhật ký là nguồn sự thật; bộ nhớ là dữ liệu dẫn xuất. `contracts/` dành cho mock API; `replay/` dành cho dữ liệu phát lại, phải ghi rõ nguồn.
7. I/O nhà cung cấp được thay bằng fake trong test. Không gọi dịch vụ trả phí khi import module hoặc chạy test.
8. Đăng ký `/api/*`, `/health`, `/media` trước khi mount static tại `/`.

## Phân công theo kế hoạch

| Người | Module chính |
| --- | --- |
| TV1 | `config`, `schemas`, `session`, `validators`, `llm`, `prompts`, `agents`, `negotiation`, `day`, `tracing` |
| TV2 | `data`, `eventlog`, `storage`, `market`, `memory`, `night`, `simulation` |
| TV3 | `main`, `api`, `sessions`, `static`, cấu hình deploy |
| TV4 | `content`, công cụ kiểm tra dịch vụ, tài liệu và bài nộp |

Các file dùng chung như `schemas.py`, `prompts.py` và `api.py` cần phối hợp theo từng task. Chi tiết chữ ký và payload lấy từ `CONTRACT.md`.

## Trạng thái khởi tạo

Khung hiện chạy `/health`, trang tĩnh và media. Cấu hình đọc `.env`, biến môi trường và tham số trực tiếp; không có khoá thì resolve về offline theo task 1.1. Các module còn lại chưa triển khai hành vi.

Trước khi ghép luồng thật, cần chốt các khác biệt đã thấy trong tài liệu; phần setup chưa sửa hợp đồng:

- `TODO(contract)`: trạng thái sau `/api/night`: `night_done` trong hợp đồng hay `idle` theo task 3.5, và thời điểm tăng ngày.
- `TODO(contract)`: `/api/content/retry` trả ảnh ngay hay trả `running` để polling; service task 4.5 mô tả cách thứ hai.
- `TODO(contract)`: thống nhất câu chữ về số lần làm lại; model và task 4.5 giới hạn ba phiên bản tổng cộng.
- `TODO(contract)`: task 1.1 resolve `replay` không có OpenAI key thành `offline`, trong khi chế độ replay cần đọc cache mà không gọi API.

Thứ tự làm tiếp: schema và JSON mẫu (1.2), dữ liệu seed (2.1), rồi validators (1.3) và API mock (3.2).
