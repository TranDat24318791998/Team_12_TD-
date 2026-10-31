# AGENTS.md · Growth Agents

Hướng dẫn cho Codex khi làm việc trong repo này. Đọc hết file này trước mỗi task.

## Dự án là gì

Hệ thống agent cho một sàn thương mại điện tử **mô phỏng** (tên hiển thị: `sàn·demo`):

- **Agent sàn** tìm shop đang có cơ hội (trend tăng, listing yếu) và đề xuất gói tăng trưởng: làm mới nội dung, quảng cáo, voucher.
- **Agent shop** bảo vệ lãi thật của chủ shop (sau phí sàn) và thương lượng lại với agent sàn.
- **Người bán** (giám khảo đóng vai chị Lan, chủ shop D) duyệt thẻ đề xuất: Đồng ý, Thương lượng thêm, Từ chối.
- **Agent nội dung** viết lại tiêu đề, mô tả, tạo 3 ảnh bìa và 1 video (qua Muse); người bán góp ý và bấm Làm lại, tối đa 3 lần.
- **Mỗi tối** hệ thống học từ kết quả: lịch sử gói, sở thích người bán, hiệu chỉnh dự báo, bài học chiến lược. Hôm sau agent đọc bộ nhớ và làm tốt hơn.
- **Bằng chứng**: chạy lại 6 ngày cùng seed, bộ nhớ bật và tắt, so sánh chỉ số.

Toàn bộ shop, thị trường và người bán là dữ liệu giả lập. Không có dữ liệu thật của sàn nào.

## Công nghệ

- Python 3.11, FastAPI + uvicorn, Pydantic v2, httpx, pytest.
- LangGraph (StateGraph, Send, interrupt, InMemorySaver, store), langchain-openai (`ChatOpenAI`).
- SQLite qua module chuẩn `sqlite3`.
- Frontend: HTML, CSS, JavaScript thuần trong `static/`, không có bước build.
- Tuỳ chọn: Langfuse để trace.
- Ghim version trong `requirements.txt` ngay sau khi cài được bản chạy.

## Cấu trúc thư mục

```
app/
  main.py            FastAPI app, phục vụ static/ và media/
  api.py             các route /api/* (docs/CONTRACT.md)
  config.py          Settings đọc .env + hằng số nghiệp vụ
  schemas.py         mọi model Pydantic dùng chung
  session.py         Session: trạng thái một lần chạy demo
  sessions.py        SessionManager: mỗi trình duyệt một phiên (cookie sid)
  storage.py         store cho bộ nhớ (LangGraph store hoặc SQLite)
  data.py            đọc data/seed.json → World
  validators.py      luật bằng code, phí sàn, hoà vốn, leak_guard
  llm.py             gọi OpenAI có cấu trúc, cache, fallback offline
  prompts.py         prompt tiếng Việt cho các agent
  agents.py          quyết định của agent sàn và agent shop (LLM + luật offline)
  negotiation.py     subgraph thương lượng (LangGraph)
  day.py             day graph: theo dõi → chọn shop → thương lượng → thẻ → chờ người bán → áp dụng
  market.py          giả lập thị trường, dự báo, người bán giả lập
  memory.py          MemoryGateway trên LangGraph store
  eventlog.py        nhật ký sự kiện SQLite
  night.py           học ban đêm
  simulation.py      chạy nhiều ngày không cần giao diện (cho bằng chứng)
  content/
    text.py          viết lại tiêu đề, mô tả
    images.py        3 ảnh bìa
    video_muse.py    gọi Muse qua useapi.net
    service.py       điều phối nội dung, job chạy nền, cache
  tracing.py         Langfuse (tuỳ chọn)
data/seed.json       5 shop, trend, lịch, phí, người bán giả lập
assets/products/     ảnh gốc của sản phẩm
static/              index.html, demo.html, updated.html, night.html, proof.html, css/, js/
media/               ảnh, video sinh ra (không commit, trừ media/replay/)
replay/              cache LLM và dữ liệu phát lại đã ghi
contracts/           JSON mẫu cho từng API (frontend dùng khi backend chưa xong)
scripts/             check_keys.py, check_llm.py, run_sim.py, record_replay.py, smoke_e2e.py, md_to_pdf.py, list_licenses.py
tests/               test + tests/fakes.py (LLM, ảnh, video giả)
docs/                CONTRACT.md, SEED_DATA.md, DESIGN.md, DEPLOY.md, CODEX_LOG.md, CODEX_USAGE.md
submission/          WRITEUP.md, DECLARATIONS.md, VIDEO_SCRIPT.md và 2 file PDF nộp bài
runs/                database của từng lần chạy (không commit)
tasks/               mỗi task một file
```

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
| `USEAPI_TOKEN`, `MUSE_EMAIL` | gọi Muse qua useapi.net |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | tuỳ chọn |
| `SEED` | mặc định 42 |
| `DEMO_SHOP` | shop giám khảo điều khiển, mặc định `D` |
| `MAX_LIVE_CALLS_PER_SESSION` | giới hạn lời gọi LLM trả phí mỗi phiên demo, mặc định 40 |
| `MAX_VIDEO_JOBS_PER_SESSION` | giới hạn job video Muse mỗi phiên, mặc định 3 |
| `IMAGE_PROVIDER` | `openai` (mặc định) hoặc `muse` |
| `MOCK_API` | `1` = API trả dữ liệu mẫu trong `contracts/` (giao diện làm trước khi backend xong) |

## Nguyên tắc bắt buộc

1. **Phân quyền dữ liệu.** Agent sàn không bao giờ thấy giá vốn, lãi tối thiểu, lãi mỗi đơn hay ROAS hoà vốn chính xác. Mọi chữ đi từ phía shop sang phía sàn phải qua `validators.leak_guard`.
2. **Số do code tính.** Lãi, phí, hoà vốn, dự báo, ROAS chỉ tính trong `validators.py` và `market.py`. LLM chỉ đọc kết quả, không tự tính.
3. **Code là chốt chặn cuối.** Mọi gói đi qua validators trước khi tới người bán; LLM sai thì code kéo gói về trong luật.
4. **Tự động hoá chỉ được dừng hoặc giảm chi**, không bao giờ tăng chi.
5. **Nhật ký sự kiện là nguồn sự thật.** Mỗi việc đáng kể ghi một sự kiện; bộ nhớ là dữ liệu dẫn xuất.
6. **Luật của chủ shop chỉ đổi khi người bán xác nhận.**
7. **Không để demo chết.** LLM, ảnh, video lỗi thì dùng luật offline hoặc bản đã lưu, ghi sự kiện, chạy tiếp.
8. **Test không gọi API trả phí.** Dùng model giả và client giả.
9. **Tất định.** Ngẫu nhiên dùng `random.Random(f"{seed}:{day}:{shop}:{kind}")`, không dùng `hash()`.
10. **Chữ hiển thị tiếng Việt.** Tiền dạng `45.000đ`, số thập phân dùng dấu phẩy (`6,5`), không emoji.

## Cách làm một task

1. Đọc file task trong `tasks/`, rồi `docs/CONTRACT.md`; đọc `docs/SEED_DATA.md` hoặc `docs/DESIGN.md` nếu task nhắc tới.
2. Chỉ tạo hoặc sửa các file trong mục **Output** của task. Nếu thấy phải đổi hợp đồng chung, dừng lại, ghi `TODO(contract): …` và báo, không tự đổi.
3. Phần nào phụ thuộc module chưa có thì viết bản giả nhỏ trong `tests/fakes.py` hoặc dùng JSON trong `contracts/`, đúng hình dạng hợp đồng.
4. Viết test cho từng điều trong **Tiêu chí xong**, chạy `pytest -q`, báo lệnh đã chạy và kết quả.
5. Commit nhỏ, message bắt đầu bằng mã task: `[1.3] validators: lãi sau phí và hoà vốn`.
6. Thêm một dòng vào `docs/CODEX_LOG.md`: giờ, mã task, việc đã làm, test đã chạy, chỗ người phải sửa tay (nếu có). File này dùng để viết mục "Codex được dùng thế nào" trong bài nộp.
