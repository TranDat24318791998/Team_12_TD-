# Kiến trúc codebase Growth Agents

Ứng dụng chạy trong một tiến trình FastAPI. Backend chia theo tính năng; model và luật thuần dùng chung nằm trong domain. Frontend dùng React, giao tiếp qua 9 API HTTP dành cho seller; esbuild tạo bundle được FastAPI phục vụ trực tiếp. Lệnh chạy giữ nguyên: `uvicorn app.main:app --reload`.

## Bổ sung được chốt cho phần Agent + Tools + Knowledge

Thiết kế mới ở [AGENT_TOOL_KNOWLEDGE](plans/toan/AGENT_TOOL_KNOWLEDGE.md) và [KNOWLEDGE_CONTRACT](plans/toan/KNOWLEDGE_CONTRACT.md); core đã được triển khai. `app/agents/tools.py` (role-bound read/compute tools) và `runner.py` (native tool loop hữu hạn). `domain/models/tools.py` giữ DTO công khai/riêng; typed memory records/views ở models/learning.py. Prompt vẫn thuộc negotiation/content/memory.

Hướng phụ thuộc: `agents.runner` dùng domain + transport LLM được inject; `agents.tools` dùng domain và callable gateway/market được inject. Không import runtime/API/main hoặc tạo client. Feature callers lắp role tools trong các closure; `runtime.manager` cấp dependencies. LangGraph quyết định role; runner điều hành tool calls bên trong role; workflow giữ approval và mọi mutation.

Store in-memory atomic trong demo và DB teammate adapter dùng cùng contract; không bỏ schema/ACL/evidence vì chưa có DB. SQLite/persistent checkpoint trong thiết kế đầy đủ chưa nằm trên critical path dưới2giờ. Chi tiết ownership mới ở [AGENT_SCOPE_MAP](plans/toan/AGENT_SCOPE_MAP.md).

## Cấu trúc chính

```text
app/
├── main.py                 create_app(): lắp router, lifespan và static
├── core/
│   ├── settings.py         Biến môi trường và hạn mức dịch vụ
│   └── paths.py            Đường dẫn tuyệt đối theo vị trí repo
├── api/
│   ├── router.py           Ghép các router dưới /api
│   ├── dependencies.py     Lấy SessionManager/phiên từ request và app.state
│   ├── schemas.py          StateView, request/response HTTP
│   ├── mock.py             Kịch bản mock theo phiên, dùng contracts/
│   └── routes/             health, sessions, days, events, content, proof
├── domain/
│   ├── models/             Model chia theo nhóm nghiệp vụ
│   ├── policies.py         Hằng số của kịch bản mô phỏng
│   ├── finance.py          Phí, lãi, hoà vốn, voucher tối đa
│   ├── validators.py       Kiểm tra và clamp gói
│   ├── privacy.py          leak_guard cho dữ liệu gửi sang agent sàn
│   └── formatting.py       vnd(), dec()
├── runtime/
│   ├── session.py          Session, ShopState: dữ liệu của mỗi run
│   ├── manager.py          SessionManager: tạo phiên và nối service
│   └── day.py              Workflow một ngày, interrupt và quyết định người bán
├── agents/                 D02a: tools.py + runner.py + content.py cho tool loop và Content role
├── negotiation/
│   ├── agents.py           Quyết định của agent sàn/shop và luật offline
│   ├── prompts.py          Chỉ prompt thương lượng và input đã lọc
│   └── graph.py            Subgraph thương lượng, ghi sự kiện từng lượt
├── content/
│   ├── service.py          start/retry/apply, phiên bản và job nền
│   ├── text.py             Viết chữ và kiểm tra thông số
│   ├── images.py           Điều phối ba phương án ảnh và cache
│   ├── video.py            Điều phối video, polling và cache
│   └── prompts.py          Prompt chữ, ảnh, video
├── memory/
│   ├── gateway.py          Phân quyền và thao tác bộ nhớ
│   ├── night.py            Học từ nhật ký sau mỗi ngày
│   └── prompts.py          Prompt sở thích và bài học chiến lược
├── simulation/
│   ├── world.py            Nạp seed.json, trend và lịch
│   ├── market.py           Dự báo, kết quả thị trường, SellerSimulator
│   └── runner.py           Chạy headless nhiều ngày, so sánh hai run
└── infrastructure/
    ├── llm.py              LLMClient, structured output, retry và cache
    ├── images.py           Client nhà cung cấp ảnh
    ├── muse.py             MuseClient và MuseError, chi tiết HTTP
    ├── eventlog.py         Nhật ký SQLite
    ├── store.py            Store cho bộ nhớ
    └── tracing.py          Langfuse tuỳ chọn

frontend/                   src/ (React), css/, img/, js/app.js; 5 HTML entry dùng chung bundle
assets/products/            Ảnh nguồn
data/                       seed.json
contracts/                  JSON mock đúng hợp đồng HTTP
replay/                     Cache LLM, proof.json và thông tin bản ghi
media/replay/               Media phát lại được commit
media/<run_id>/             Media sinh trong phiên, Git bỏ qua
runs/<run_id>/              Database và báo cáo theo run, Git bỏ qua
scripts/                    CLI mỏng, gọi module backend
submission/                 Bài viết và tài liệu nộp bài
docs/                       Đặc tả và kiến trúc hiện hành
docs/reference/             PDF kế hoạch gốc, giữ làm tài liệu tham khảo
tasks/                      Phạm vi output và tiêu chí hoàn thành
tests/
├── unit/<package>/         Settings, domain, agent/service với fake client
├── integration/<feature>/  API, workflow nhiều module, storage thật tạm thời
└── fakes/                  Fake client chia file theo nhà cung cấp
```

## Model thuộc về đâu

| File | Model |
| --- | --- |
| `domain/models/shops.py` | ShopPublic, ShopPrivate, ShopRules, SellerPersona, FeeConfig |
| `domain/models/packages.py` | Package, ActivePackage |
| `domain/models/negotiation.py` | PlatformTurn, ShopTurn, Violation, NegotiationResult |
| `domain/models/cards.py` | RuleQuestion, Card, SellerDecision |
| `domain/models/content.py` | ContentText, CoverImage, VideoJob, ContentDraft |
| `domain/models/learning.py` | Calibration, LessonOp, NightSummary |
| `domain/models/metrics.py` | Forecast, DayMetrics, ProofMetric, ProofReport |
| `domain/models/events.py` | Event |
| `api/schemas.py` | StateView và các request/response HTTP, dùng lại domain model |
| `runtime/session.py` | Session, ShopState |
| `simulation/world.py`, `simulation/runner.py` | World, RunResult |

Các đường dẫn trong bảng tính từ `app/`. Import từ module định nghĩa trực tiếp, ví dụ `from app.domain.models.shops import FeeConfig`. Không sao chép model sang từng tính năng; không gom re-export mọi model vào `__init__.py`.

## Hướng phụ thuộc

| Phần | Được gọi/import | Giới hạn |
| --- | --- | --- |
| `domain` | Standard library, Pydantic, module khác trong domain | Không đọc .env, gọi HTTP/SQLite hoặc import tầng bên ngoài |
| `core` | Standard library, dotenv, Pydantic, domain model cấu hình | Không import API, runtime hay client dịch vụ |
| `infrastructure` | core, domain và SDK/driver | Không import workflow hay router |
| `negotiation`, `content`, `memory.gateway` | domain, core, client được truyền vào; facade bộ nhớ/dự báo khi cần | Không import FastAPI, request hay main |
| `simulation.world`, `simulation.market` | domain, core; I/O seed cục bộ ở world | Không import runner hoặc workflow ngày |
| `runtime.day` | negotiation.graph, content.service, memory.gateway, simulation.market | Không import simulation.runner |
| `memory.night` | memory.gateway, simulation.market, client LLM, domain | Không import workflow ngày hay simulation.runner |
| `simulation.runner` | runtime.day, memory.night, simulation.market | Chỉ điều phối headless, không được market gọi ngược |
| `api` | schema, runtime/service | Không chứa công thức tài chính hay lời gọi provider trực tiếp |
| `main`, `runtime.manager` | Các thành phần cần lắp ứng dụng/phiên | Chỉ ở đây nối các concrete service với nhau |

Giữ `runtime.session` là nơi định nghĩa trạng thái; việc gắn LLM, memory, eventlog và content diễn ra trong `runtime.manager`. Dùng `TYPE_CHECKING` cho type hint tham chiếu Session nếu cần để tránh import vòng. Không tạo client mạng khi import module.

## Tách đường đi HTTP và nghiệp vụ

- `api/routes/sessions.py`: `/api/reset`, `/api/state`.
- `api/routes/days.py`: `/api/day/start`, `/api/decision`, `/api/night`.
- `api/routes/events.py`: `/api/events`.
- `api/routes/content.py`: `/api/content/retry`, `/api/content/apply`.
- `api/routes/proof.py`: `/api/proof`.
- `api/routes/health.py`: `/health`, độc lập với phiên và dịch vụ ngoài.

Route lấy phiên qua dependency, kiểm tra payload rồi gọi workflow/service. `SessionManager` sẽ được khởi tạo trong lifespan và gắn vào `app.state`; các yêu cầu cùng sid dùng chung khoá của phiên. Mock API cũng có state riêng theo sid. Các router dùng chung nhưng không giữ state của người dùng.

Thứ tự lắp ở `create_app()`: health → API → media → frontend tại `/`. Vì vậy static không che các endpoint. Quy tắc URL và JSON nằm trong `CONTRACT.md`.

## Phân chia công việc

| Người | Khu vực sở hữu chính |
| --- | --- |
| TV1 | domain, runtime/session + day, negotiation, infrastructure/llm + tracing |
| TV2 | simulation, memory, infrastructure/eventlog + store |
| TV3 | api, runtime/manager, frontend, app/main và deploy |
| TV4 | content, infrastructure/images + muse, submission và công cụ tài liệu |

Task 1.2 khởi tạo các model dùng chung; các task sau thêm trường đúng hợp đồng và phối hợp với người sở hữu model liên quan. Mỗi nhóm có prompt riêng, thay đổi nội dung không cần sửa prompt thương lượng. Các Output trong `tasks/` đã chuyển sang đường dẫn mới.

## Những gì đã chạy

Domain, tool runner, graph thương lượng, knowledge gateway/learning và runtime ngày đã có code và test headless với fixture. Settings, app factory, `/health` và frontend tĩnh chạy được. Router nghiệp vụ, market và media thật vẫn chờ member tích hợp; xem [runbook](plans/toan/DEMO_RUNBOOK.md). Test không gọi API trả phí.

Không duy trì shim tại các đường dẫn phẳng cũ; các tài liệu đang dùng đã cập nhật đường dẫn. PDF trong `docs/reference/` là kế hoạch gốc; đường dẫn triển khai lấy từ tài liệu Markdown hiện hành.

## Hợp đồng ghép tính năng hiện hành

Các điểm night/idle, retry async, ba phiên bản tổng cộng, replay thiếu key đã được chốt tại [DEMO_CONTRACT](DEMO_CONTRACT.md). Native tools/budget/typed memory theo hai contract mới ở trên. Coder sửa cả caller/fixture của task khi thực hiện các thay đổi đã được chốt; không giữ TODO cũ như một quyết định chưa có.
## Ghép với thiết kế dữ liệu hiện hành

`data/growth_agents_data_api_design.md` v1.1 chốt adapter dành cho giao diện tại mục 10. Bản React đã dùng các quy ước này; nhóm backend triển khai cùng adapter và persistence tương ứng:

- Giữ 9 endpoint `/api/*` và response JSON trực tiếp; `/api/v1` có envelope riêng.
- Thiết kế frontend/data là 7 ngày; phần agent headless hiện kiểm 2 ngày và chưa được nối vào data service. Khi ghép, ngày cuối trả `complete`/`next_day=null`, không suy ra proof từ fixture.
- Retry nội dung trả trạng thái running để polling; 3 attempt tổng cộng, gồm bản đầu và hai lần làm lại.
- Frontend gửi Idempotency-Key và X-Request-ID cho POST; server kiểm tra phiên bản/ownership và transaction.
- Replay đọc cache không cần key, không tự chuyển live để gọi dịch vụ trả phí. Settings đã giữ replay khi thiếu key; adapter cache còn cần tích hợp.

Hướng dẫn build React, nguồn dữ liệu, kiểm tra và các phần chưa triển khai nằm trong `docs/FRONTEND_HANDOFF.md`. Tài liệu dữ liệu là thiết kế; không coi nó là bằng chứng backend đã chạy.
