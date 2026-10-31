# Review riêng từng phần trước khi tích hợp local

Theo yêu cầu mới ngày 31/10/2026: mỗi phần có một reviewer **Astra max** riêng; implementation do **Terra 6.1 max**. Công cụ giao agent không có tham số Fast. Giới hạn hiện tại là ba agent phụ đồng thời, nên review chạy thành các đợt. Không dùng một báo cáo tổng hợp để thay các review chuyên biệt.

Baseline source: `33fbdd5`, đã hợp nhất media `a0a93f0`, frontend `bd78f8e`, Data `9621b14` và media plan `984a8c9`. Các tài liệu self-improve đang có trong workspace được giữ nguyên để đối chiếu, chưa phải code đã triển khai.

| Phần | Reviewer | Báo cáo riêng | Nội dung |
| --- | --- | --- | --- |
| DB | astra_db_review | DB_REVIEW.md | Một nguồn business state, SQLite, transaction, migration và recovery |
| Media | astra_media_review | MEDIA_REVIEW.md | OpenAI/Muse, bridge, artifact, seller review gate |
| Self-improve | astra_max_review | SELF_IMPROVE_REVIEW.md | SI01–SI07, compiler/evidence/publication/replay |
| Agent điều phối | astra_agents_review | AGENTS_REVIEW.md | Năm role, LangGraph, Data operation worker, lifecycle |
| Tools | astra_tools_review | TOOLS_REVIEW.md | Native tool protocol, allowlist, Data adapter, tiền/privacy |
| Knowledge | astra_knowledge_review | KNOWLEDGE_REVIEW.md | Năm ngăn, retrieval, confirmation, durable adapter |
| HTTP API | astra_api_review | API_REVIEW.md | Ghép facade với core, schema/version/idempotency, job polling |
| UI | astra_ui_review | UI_REVIEW.md | React seller flow, content gate, night/proof, nguồn dữ liệu |
| Chạy local | astra_host_review | HOST_REVIEW.md | Process/ports/dependencies, persistent data và smoke không trả phí |

Mỗi báo cáo phải chỉ rõ source thực tế, lỗi có thể tái hiện, quyết định tích hợp, file cần sửa, thứ tự triển khai và acceptance. Reviewer không sửa source. Giao diện giữa các phần được chốt trong plan triển khai ở thư mục này sau khi nhận báo cáo; các plan cũ chỉ bị thay ở những quyết định được ghi rõ.

Mục tiêu là nối agent/tools/knowledge/self-improve với Data và media đã có, phục vụ React trên máy này. Không tạo một business Session/database cạnh tranh với Data, không dựng lại toàn bộ UI hoặc provider pipeline. Ưu tiên demo chính; không thêm chống spam, multiuser hoặc cloud deployment.

## Baseline đã kiểm

- Root: `.venv/bin/python -m pytest -q` → **83 passed, 15 subtests passed**.
- Data: `PYTHONPATH=data .venv/bin/python -m pytest -c data/pyproject.toml data/tests -q` → **54 passed, 1 failed**. Test retry chọn `jobs[-1]` trên query không sắp xếp, nên có thể gửi vào job đã terminal; cần sửa thứ tự/selection, không nới terminal guard.
- Frontend: build tests + Node test runner → **44 passed**. Experiment: Python 3.12 isolated environment, `pytest tests -q` → **25 passed**. Đây là baseline trước patch tích hợp; chưa phải kết quả integration mới.
- Secrets chỉ lưu trong `.env` và `experiment/.env` đã ignore, quyền 0600; không đưa giá trị vào báo cáo.
