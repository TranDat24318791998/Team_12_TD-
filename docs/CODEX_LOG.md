# Nhật ký dùng Codex

Giờ ghi theo múi giờ Việt Nam (UTC+7).

| Giờ | Task | Người | Việc Codex làm | Test | Sửa tay |
| --- | --- | --- | --- | --- | --- |
| 2026-10-31 10:41 | 1.1 | Nguyễn Đức Toàn + Codex | Sắp xếp AGENTS/docs/tasks ở gốc; dựng module và kiến trúc; Settings, FastAPI, môi trường Python 3.11.18 và ghim dependencies; làm trên main theo yêu cầu | pip install đạt; pytest -q: 13 passed; pip check đạt; imports LangGraph/LangChain đạt; uvicorn + HTTP /health, /, /media đạt; git check-ignore .env đạt | Chờ xác thực GitHub; các thành viên còn lại chưa kiểm tra clone trên máy riêng |
| 2026-10-31 11:04 | 1.1 / cấu trúc | Nguyễn Đức Toàn + Codex | Theo yêu cầu người dùng: chia backend theo tính năng, tách domain/core/infrastructure/API, frontend riêng, app factory, unit/integration test; đồng bộ AGENTS, CONTRACT và task paths; giữ nguyên payload/nghiệp vụ | 14 tests passed; import 61 module đạt; domain không import tầng ngoài; pip check đạt; HTTP health/frontend/media 200; đối chiếu payload và hằng số không đổi | Người dùng đã xác thực GitHub ở lượt trước; thao tác hoàn toàn qua terminal |
