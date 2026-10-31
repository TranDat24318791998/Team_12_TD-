# Kiến trúc codebase Growth Agents

Bản local có hai process: app Data + agent + React tại8000, media service tại8010. Một SQLite của Data giữ business state và Knowledge. Không chạy song song hai workflow business. Hợp đồng dùng chung ở [DEMO_CONTRACT](DEMO_CONTRACT.md); cách chạy ở [LOCAL_RUN](LOCAL_RUN.md).

## Quyền sở hữu dữ liệu

| Dữ liệu | Owner |
| --- | --- |
| Run/day/shop/rules/brief/proposals/cards/decisions/campaigns/stock/listing/content/assets/settlements/events | `data/growth_data/`, `data/runtime/growth.db` |
| History/Preferences/Calibration/Lessons, skill versions, snapshots/reflection/night receipts và native budget | `app/memory/` kiểm nghĩa; `app/infrastructure/sqlite_store.py` lưu cùng Data DB |
| Provider jobs/intermediate bytes, signed playback | `experiment/video_api/`, `experiment/data/local/`; không sở hữu approval/campaign |
| UI state/cursor | React; lấy lại business state từ API sau reload |
| RAM Session/core harness | Tests và headless core độc lập; không là authority của integrated HTTP |

## Module đang dùng trong sản phẩm

```text
app/
  main.py                       Factory ghép Data API/lifespan/worker/static
  core/                         Settings và paths
  domain/                       Models, Decimal finance, validators/privacy
    models/skills.py            Typed facts/policy/artifact/version
    models/learning.py          Knowledge/publication/replay DTO
  runtime/data_worker.py         Claim Data operation → native graph/content/night
  agents/                       Tool ACL/protocol, Content role
  negotiation/                  Platform/Shop/Referee, prompts, LangGraph
  content/service.py            Data-bound Content/media worker
  memory/                       Gateway, facts/compiler/stage/night/prompt
  infrastructure/
    data_agents.py              Scoped context, tools, event/turn projection
    data_content.py             Claim/reserve/asset/result transaction adapters
    data_knowledge.py           Rules/evidence/reference projections
    sqlite_store.py             Durable Knowledge/receipt repository
    store.py                    RAM adapter và shared repository semantics
    llm.py, replay.py            OpenAI transport, durable budget/cache binding
    media_gateway.py            HTTP client tới experiment, verified import
  simulation/                   World/core fixtures và Data-backed proof runner
  runtime/session.py, day.py     Standalone core path retained for tests
  api/                          Legacy scaffold; không ghép thêm facade thứ hai

data/growth_data/
  api.py, routes.py, facade.py   HTTP/auth/session/9seller API + brief
  service.py, integration.py     Authoritative commands và worker handoff
  media.py                      Assets/content/publish gates
  storage.py, migrations/       SQLite/WAL/atomic migration/commands
  simulation.py, finance.py     Simulator/calculation authority của Data run

experiment/video_api/            Images/vision/Muse/queue/storage/playback
frontend/src/                    React components và API consumer
scripts/local_stack.py           Hai owned processes: start/status/stop
scripts/run_sim.py               Data-backed offline comparison CLI
contracts/                      Shared wire fixtures và SI schema/examples
tests/                          Unit, contract, integration và fake providers
```

File trong `app/content/images.py`, `video.py`, `infrastructure/images.py`, `muse.py` thuộc khung cũ không phải provider path của product. Không chép pipeline `experiment` sang đó. `app/api` không được copy Data routes để tạo state riêng.

## Hướng gọi

1. React gửi same-origin seller command với IDs/versions/idempotency; Data kiểm quyền, lưu effect+event+receipt trong transaction.
2. Native worker nhận Data operation, tạo scoped context từ current business versions và pin brief/skill. Tools chỉ read/compute; graph trả turn/verdict qua Data sinks. Data finalize trước present.
3. Seller accept content-refresh tạo Data content job; Content Agent dùng facts/confirmed style, media worker gọi experiment. Bytes verified nhập Data asset registry. Seller Apply mới publish+activate atomic.
4. Data settle ghi prediction/outcome/cutoff; Learning freeze public evidence, claim/reserve, stage/eval và publish durable Knowledge cùng handoff. Ngày sau read_memory trả artifact/seed đã pin.

`domain` chỉ dùng stdlib/Pydantic và models thuần; không đọc env/SQL/HTTP. `core` nạp config. Infrastructure giữ SQL/HTTP/SDK và public/private projections; runtime giữ orchestration. Feature modules không import FastAPI/main. Data package nhận callbacks/injection, không import ngược app để biết SI algorithm. Không tạo clients, DB hoặc threads ở module import.

## Persistence và version

Data `Store.connect(write=True)` dùng short BEGIN IMMEDIATE, WAL và foreign keys. Migration mới nối tiếp; không sửa001/002, không reset database để nâng CHECK. Migrate có backup khi DB thực tồn tại; kiểm integrity/FK và rollback fault.

Không giữ DB lock qua model/provider. Snapshot/claim/budget reserve trước network; terminal output lưu trước publication. Duplicate receipt trả result cũ; cùng key khác body/hash conflict. Unknown không được cấp key mới để resend. One native file lock và media worker lock chống hai process cùng home; leases/version chặn late write.

Rules authoritative ở Data, Knowledge chỉ derived. Same-connection helper bảo đảm Rules+preference và Knowledge+skill+night receipt+handoff atomic. Một event seq xuyên business và learning; JSONL legacy không dùng để resume Data run.

## Media và local assets

Original D là ảnh quạt để bàn được user chọn từ MinIO đồng nghiệp; metadata/facts đổi theo ảnh, số tài chính mô phỏng giữ nguyên. Imports/checksum manifest nằm dưới ignored `data/runtime/imports/`. Mỗi run đăng ký bản sao riêng qua Data; seed placeholder không bị ghi đè. Signed service links chỉ là transport, listing giữ Data asset IDs.

Local profile dùng file storage đã có; không cần MinIO daemon, cloud tunnel hoặc Docker. Có thể dùng MinIO backend ở deployment khác theo experiment docs. Cả hai app bind loopback, một worker/no reload. Static frontend mount cuối; private Data objects không được mount public.

## Kiểm thử và review

Root/core, Data, experiment và React có suites riêng. Thêm contract tests RAM/SQLite, real Data + fake HTTP media, native ToolMessage next-use và Data-backed D/E seven-day reports. Test không gọi paid provider; report tách source fixture/offline/live và không tạo uplift giả.

Mỗi phần có một [Astra review riêng](plans/toan/full-integration/REVIEW_ASSIGNMENTS.md); Terra implementation theo [ownership](plans/toan/full-integration/IMPLEMENTATION_PLAN.md). Kết quả thực và phần chưa kiểm nằm ở implementation status/runbook. Các PDF/task gốc giữ làm reference, không thay contract integrated hiện hành.
