# AGENTS.md · Growth Agents

Hướng dẫn cho Codex khi làm việc trong repo này. Đọc hết file này trước mỗi task.

## Phạm vi triển khai hiện hành

Khi làm phần **Agent + Tools + Knowledge của Toàn**, đọc `docs/plans/toan/README.md` và task tương ứng trong `docs/plans/toan/tasks/`. Hợp đồng runtime/HTTP/media dùng chung ở `docs/DEMO_CONTRACT.md`; task UI/media ở `tasks/demo/`, phân công gốc TV1–TV4 ở `tasks/`. Mỗi member theo phạm vi của mình; thay đổi interface dùng chung phải cập nhật các đầu nối liên quan.

Provider hiện hành: OpenAI cho LLM/ảnh, Muse Gateway theo `docs/MUSE_API.md` cho video. Không dùng nhánh useapi.net cũ. UI/media/DB thuộc lane member tương ứng; không bỏ tool calling/knowledge để làm thay toàn bộ lane đó.

## Dự án là gì

Hệ thống agent cho một sàn thương mại điện tử **mô phỏng** (tên hiển thị: `sàn·demo`):

- **Agent sàn** tìm shop đang có cơ hội (trend tăng, listing yếu) và đề xuất gói tăng trưởng: làm mới nội dung, quảng cáo, voucher.
- **Agent shop** bảo vệ lãi thật của chủ shop (sau phí sàn) và thương lượng lại với agent sàn.
- **Người bán** (giám khảo đóng vai chị Lan, chủ shop D) duyệt thẻ đề xuất: Đồng ý, Thương lượng thêm, Từ chối.
- **Agent nội dung** viết lại tiêu đề, mô tả, tạo 3 ảnh bìa và 1 video (qua Muse); người bán góp ý và bấm Làm lại, tối đa 3 lần.
- **Mỗi tối** hệ thống học từ kết quả: lịch sử gói, sở thích người bán, hiệu chỉnh dự báo, bài học chiến lược. Hôm sau agent đọc bộ nhớ và làm tốt hơn.
- **Bằng chứng**: chạy lại 7 ngày cùng seed, bộ nhớ bật và tắt, so sánh chỉ số.

Toàn bộ shop, thị trường và người bán là dữ liệu giả lập. Không có dữ liệu thật của sàn nào.

## Công nghệ

- Python 3.11, FastAPI + uvicorn, Pydantic v2, httpx, pytest.
- LangGraph (StateGraph, Send, interrupt, InMemorySaver, store), langchain-openai (`ChatOpenAI`).
- SQLite qua module chuẩn `sqlite3`.
- Frontend: React 19 trong `frontend/src/`, CSS trong `frontend/css/`; `npm run build` dùng esbuild tạo `frontend/js/app.js`, FastAPI phục vụ tại `/`. Đổi sang React theo yêu cầu người dùng; xem `docs/FRONTEND_HANDOFF.md`.
- Thiết kế dữ liệu hiện hành: `data/growth_agents_data_api_design.md` v1.1. Frontend giữ 9 API seller, dùng 7 ngày và trạng thái `complete` theo mục 10.
- Khi ghép backend/data với giao diện, đọc `docs/FRONTEND_REQUIREMENTS.md` và `docs/FRONTEND_DATA_REQUIREMENTS.md`: payload React đang hỗ trợ, phân quyền, event cursor, phiên bản và yêu cầu persistence. Các mở rộng ghi `TODO(contract)` cần được chốt vào hợp đồng trước khi bật trên API thật.
- Tuỳ chọn: Langfuse để trace.
- Ghim version trong `requirements.txt` ngay sau khi cài được bản chạy.

## Cấu trúc thư mục

Kiến trúc chi tiết và quy tắc import: `docs/ARCHITECTURE.md`.

```text
app/
  main.py               create_app(): lắp FastAPI, router và frontend
  core/                 settings.py (môi trường), paths.py (đường dẫn)
  api/                  schemas.py, dependencies.py, mock.py, router.py
    routes/             health.py, sessions.py, days.py, events.py, content.py, proof.py
  domain/               policies.py, finance.py, validators.py, privacy.py, formatting.py
    models/             shops, packages, negotiation, cards, content, learning, metrics, events
  runtime/              session.py, manager.py, day.py
  agents/               tools.py, runner.py (đặc tả D02a, chưa implement)
  negotiation/          agents.py, prompts.py, graph.py
  content/              text.py, images.py, video.py, prompts.py, service.py
  memory/               gateway.py, night.py, prompts.py
  simulation/           world.py, market.py, runner.py
  infrastructure/       llm.py, images.py, muse.py, eventlog.py, store.py, tracing.py
frontend/               React source, CSS, ảnh và bundle đã build; được phục vụ tại /
data/                   seed.json (dữ liệu nguồn)
assets/products/        ảnh sản phẩm gốc
contracts/              JSON mẫu của API
replay/                 cache LLM và báo cáo đối chứng đã ghi
media/                  media sinh ra; chỉ media/replay/ được commit
runs/                   database và báo cáo mỗi run, Git bỏ qua
scripts/                lệnh kiểm tra, mô phỏng, ghi replay và xuất bài nộp
tests/unit/             test thuần theo package
tests/integration/      test ghép API, workflow và storage
tests/fakes/            fake client dùng chung, chia file theo nhà cung cấp
docs/                   đặc tả, kiến trúc, nhật ký; reference/ giữ PDF kế hoạch gốc
tasks/                  32 task đã cập nhật đường dẫn theo cấu trúc này
submission/             bài viết, khai báo và video script
```

- `domain` chỉ chứa model, hằng số và quy tắc thuần; không import API, runtime, client ngoài hay đọc biến môi trường.
- `core` chỉ nạp cấu hình và đường dẫn; hằng số nghiệp vụ ở `domain/policies.py`.
- Route gọi workflow/service; client HTTP, store và tracing ở `infrastructure`.
- Prompt thuộc tính năng sử dụng nó: `negotiation/prompts.py`, `content/prompts.py`, `memory/prompts.py`.
- Model nghiệp vụ chia theo nhóm trong `domain/models/`; `StateView` và payload HTTP ở `api/schemas.py`, tái sử dụng domain model.
- Giữ `__init__.py` nhẹ; import trực tiếp module cần dùng, không re-export toàn bộ ứng dụng.

## Lệnh

```
pip install -r requirements.txt
uvicorn app.main:app --reload            # chạy web ở http://localhost:8000
pytest -q                                # chạy test
python scripts/run_sim.py --days 6       # chạy 6 ngày không giao diện
```

## Biến môi trường

Đặt trong `.env` khi chạy máy, trong phần Secrets khi deploy. **Không bao giờ commit `.env`.**

| Biến | Ý nghĩa |
| --- | --- |
| `OPENAI_API_KEY` | khoá OpenAI |
| `LLM_MODEL` | model cho agent, ví dụ model ban tổ chức cấp |
| `LLM_MODEL_REFLECT` | model rút bài học ban đêm (mặc định = `LLM_MODEL`) |
| `OPENAI_IMAGE_MODEL` | model tạo/sửa ảnh |
| `LLM_MODE` | `live` gọi thật và ghi cache · `replay` đọc cache, thiếu thì dùng luật offline · `offline` không gọi · `auto` = live nếu có khoá |
| `MUSE_API_BASE_URL`, `MUSE_API_KEY`, `MUSE_VIDEO_MODEL` | Muse Gateway backend-only, theo MUSE_API.md |
| `MEDIA_MODE` | live/offline/replay độc lập LLM_MODE |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | tuỳ chọn |
| `SEED` | mặc định 42 |
| `DEMO_SHOP` | shop giám khảo điều khiển, mặc định `D` |
| `MAX_LIVE_CALLS_PER_SESSION` | giới hạn lời gọi LLM trả phí mỗi phiên demo, hiện Settings mặc định40; D01 cấu hình demo64 cho tool loop |
| `MAX_VIDEO_JOBS_PER_SESSION` | giới hạn job video Muse mỗi phiên, mặc định 3 |
| `IMAGE_PROVIDER` | OpenAI cho ảnh theo yêu cầu hiện hành |
| `MOCK_API` | `1` = API trả dữ liệu mẫu trong `contracts/` (giao diện làm trước khi backend xong) |

## Nguyên tắc bắt buộc

1. **Phân quyền dữ liệu.** Agent sàn không bao giờ thấy giá vốn, lãi tối thiểu, lãi mỗi đơn hay ROAS hoà vốn chính xác. Mọi chữ đi từ phía shop sang phía sàn phải qua `app.domain.privacy.leak_guard`.
2. **Số do code tính.** Lãi, phí, hoà vốn, dự báo, ROAS chỉ tính trong `app/domain/finance.py` và `app/simulation/market.py`. LLM chỉ đọc kết quả, không tự tính.
3. **Code là chốt chặn cuối.** Mọi gói đi qua validators trước khi tới người bán; LLM sai thì code kéo gói về trong luật.
4. **Tự động hoá chỉ được dừng hoặc giảm chi**, không bao giờ tăng chi.
5. **Nhật ký sự kiện là nguồn sự thật.** Mỗi việc đáng kể ghi một sự kiện; bộ nhớ là dữ liệu dẫn xuất.
6. **Luật của chủ shop chỉ đổi khi người bán xác nhận.**
7. **Không để demo chết.** LLM, ảnh, video lỗi thì dùng luật offline hoặc bản đã lưu, ghi sự kiện, chạy tiếp.
8. **Test không gọi API trả phí.** Dùng model giả và client giả.
9. **Tất định.** Ngẫu nhiên dùng `random.Random(f"{seed}:{day}:{shop}:{kind}")`, không dùng `hash()`.
10. **Chữ hiển thị tiếng Việt.** Tiền dạng `45.000đ`, số thập phân dùng dấu phẩy (`6,5`), không emoji.

## Cách làm một task

1. Với task demo, dùng thứ tự/contract ở mục Phạm vi triển khai hiện hành. Đọc `docs/ARCHITECTURE.md`, file task trong `tasks/`, rồi `docs/CONTRACT.md`; đọc `docs/SEED_DATA.md` hoặc `docs/DESIGN.md` nếu task nhắc tới.
2. Chỉ tạo hoặc sửa các file trong mục **Output** của task. Nếu thấy phải đổi hợp đồng chung, dừng lại, ghi `TODO(contract): …` và báo, không tự đổi.
3. Phần nào phụ thuộc module chưa có thì viết bản giả nhỏ trong `tests/fakes/` hoặc dùng JSON trong `contracts/`, đúng hình dạng hợp đồng.
4. Viết test cho từng điều trong **Tiêu chí xong**, chạy `pytest -q`, báo lệnh đã chạy và kết quả.
5. Commit nhỏ, message bắt đầu bằng mã task: `[1.3] validators: lãi sau phí và hoà vốn`.
6. Thêm một dòng vào `docs/CODEX_LOG.md`: giờ, mã task, việc đã làm, test đã chạy, chỗ người phải sửa tay (nếu có). File này dùng để viết mục "Codex được dùng thế nào" trong bài nộp.
