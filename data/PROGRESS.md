# Tiến độ triển khai phần dữ liệu

Quy ước: làm trên `main`, chỉ thay đổi trong `data/`. Môi trường mới dùng uv tại
`data/.venv`; hướng dẫn bàn giao ở `data/README.md`. File thiết kế v1.1 giữ nguyên.

## Các mốc

| Mốc | Trạng thái | Kết quả / quyết định |
| --- | --- | --- |
| 1. Môi trường, schema và database | Xong bản local | Project uv riêng, lockfile, Python 3.11.15, SQLite WAL và migration 33 bảng |
| 2. Seed và tài liệu | Xong | 5 shop, 14 ngày lịch sử, kịch bản 7 ngày; 24 file trong manifest có checksum, gồm 9 tài liệu Markdown, 5 ảnh placeholder và 4 PDF |
| 3. Phân quyền và API đọc | Xong bản local | Projection theo vai trò, token giới hạn run/shop/job, cookie seller, cursor có chữ ký |
| 4. Giao dịch ghi | Xong bản local | Approval theo phiên bản, idempotency, settlement nguyên tử, tồn kho/ngân sách và event log |
| 5. File, nội dung, knowledge, learning | Xong hạ tầng local | Upload/download kiểm tra quyền, content worker handoff/lease/fallback, keyword search/revoke, learning handoff và calibration callback |
| 6. Simulator, báo cáo, adapter, hướng dẫn | Xong bản local | 61 HTTP operations gồm 9 route demo; CLI chạy/so sánh/xuất proof, ví dụ client và README bàn giao |

“Xong bản local” là service dữ liệu chạy độc lập. Chưa có nghĩa ứng dụng chính,
agent LLM, bộ nhớ học và dịch vụ cloud đã được nối.

## Quyết định triển khai

- **Tách project uv trong `data/`:** ứng dụng chính hiện là khung; không sửa module
  của thành viên khác. Dependency được khóa bằng `uv.lock`; môi trường ở `.venv`,
  runtime và cache đều được Git bỏ qua. Interpreter do uv quản lý có thể nằm ngoài
  repo; không thay Python hệ thống.
- **SQLite + object storage local:** đủ cho demo một service, hỗ trợ giao dịch để
  approval, áp gói, trừ kho, settlement và event được ghi cùng nhau. Mọi thay đổi
  nghiệp vụ đi qua command; không để agent ghi SQL trực tiếp.
- **Không đưa toàn bộ seed vào prompt/frontend:** giá vốn và luật riêng chỉ vào
  projection của shop phù hợp; persona và tham số simulator chỉ dùng phía backend.
  Bearer token được lưu dưới dạng hash; token phát triển không đưa vào JavaScript.
- **Giữ quyết định và snapshot:** command chống thực thi lặp; bản nội dung được
  duyệt không đổi ngầm khi job cũ trả muộn. Dự báo giữ factor/version đã dùng để
  có thể đối chiếu kết quả theo ngày.
- **Dữ liệu có nhãn giả lập:** ảnh nguồn là placeholder, nội dung local là fallback.
  14 ngày lịch sử không trừ lại tồn kho mở đầu và không được tính thành kết quả
  của lần chạy 7 ngày. Không sinh sẵn bằng chứng agent học tốt hơn.
- **Học do module agent sở hữu:** Data API cung cấp input có scope, nhận kết quả
  handoff và đọc calibration snapshot qua callback. Mặc định ghi skipped với
  `LEARNING_NOT_CONNECTED`; memory-off không đọc calibration. Luật shop chỉ đổi
  sau khi người bán xác nhận.
- **Khả năng phục hồi:** job quá lease chuyển sang fallback; learning quá hạn có
  trạng thái skipped và thông tin khả năng đã ghi dở vào memory store. Không tự
  gửi lại job trả phí khi chưa biết kết quả lần gọi trước.

## Kiểm tra đã thực hiện — 31/10/2026

| Kiểm tra | Kết quả |
| --- | --- |
| `uv sync --project data --python 3.11` | Tạo môi trường riêng và cài dependency thành công |
| `uv run --project data pytest -c data/pyproject.toml data/tests -q` | **32 passed**, 1 warning về Starlette TestClient/httpx |
| `uv run --project data growth-data validate-data` | Integrity và foreign keys hợp lệ; kiểm tra 3 run, 9 knowledge documents |
| CLI `run-scenario --days 7 --seed 42 --compare` | Hai run hoàn tất; xuất proof có nhãn `offline_reference`, learning chưa nối |
| HTTP thật: `python data/examples/smoke_demo.py --base-url http://127.0.0.1:8001` qua uv | Ngày 1–7 đều PASS; cuối ngày 7 complete, không sinh ngày 8 |
| Seed và manifest | Kiểm tra SHA-256; 140 channel rows lịch sử/run; run 7 ngày có 35 settlements và 70 channel rows mới |
| PDF | Xuất 4 PDF, render và kiểm tra trực quan tiếng Việt, không cắt chữ |
| Phạm vi Git | Nhánh main; file thiết kế không thay đổi; các file triển khai chỉ trong data/ |

Kiểm thử bao gồm phân quyền cross-run/shop, chống lộ thông tin, idempotency,
rollback settlement, ghi đồng thời, giới hạn chi/tồn kho, retry nội dung, upload,
lease recovery, xác nhận luật và calibration chỉ dùng dữ liệu của ngày trước.
Không gọi API trả phí. Server smoke test đã dừng sau kiểm tra; thành viên khởi động
lại bằng lệnh trong README.

uv có thể cảnh báo `pyproject.toml` gốc không có `[project]`; project độc lập vẫn
chạy đúng. Warning TestClient hiện không làm test thất bại.

## Bàn giao và phần còn cần tích hợp

- Hướng dẫn cài/chạy, cấp token, route theo vai trò, ví dụ curl/Python, worker và
  CLI nằm trong [README.md](README.md); code ví dụ ở `examples/`.
- Team frontend/backend cần nối service qua HTTP; chưa thay các route của `app/`.
- Team agent cần nối thương lượng, content provider và học ban đêm. Driver hiện
  là chính sách tham chiếu bằng code. Hai run memory-on/off mặc định bằng nhau
  và **không chứng minh hiệu quả học**.
- Live provider chưa cấu hình trả 503. Replay hiện là dữ liệu audit/snapshot của
  driver local, chưa phải bản ghi/phát lại toàn bộ lời gọi LLM.
- Knowledge hiện dùng keyword search; OpenAI Vector Stores, Sites D1/R2, sign-in,
  deployment cloud và LangGraph checkpoint chưa nằm trong bản local này.
- Chưa commit/push. Không ghi tiến độ vào file thiết kế.

## Nhật ký

- 31/10/2026: Kiểm tra repo sạch trên main. Ứng dụng chính mới có khung; triển khai
  service độc lập trong data/, không thay module của thành viên khác.
- Python hệ thống là 3.9.6; project yêu cầu >=3.11. Dùng uv quản lý interpreter và
  dependency riêng, không sửa môi trường của ứng dụng chính.
- 31/10/2026: Hoàn tất hạ tầng dữ liệu local, seed, API, simulator, báo cáo, ví dụ và
  hướng dẫn; xác minh 32 tests và luồng HTTP 7 ngày. Các tích hợp ngoài ghi rõ ở trên.
- 31/10/2026: Thêm [DEMO_DATA_CHECKLIST.md](DEMO_DATA_CHECKLIST.md), đối chiếu khớp 61/61 HTTP operations với quyền/caller, 6 màn demo, agent/worker, lỗi còn mở và 14 ca nghiệm thu; 32 tests pass (1 warning), kiểm tra link và SHA-256 xác nhận chỉ 3 file tài liệu thay đổi, giữ nguyên design/code/schema/dataset.
