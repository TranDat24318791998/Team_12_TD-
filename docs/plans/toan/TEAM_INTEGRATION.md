# Ghép Agent/Knowledge với Data và Frontend

Đối chiếu commit Data `229b1f5`, Frontend `e627db8` với core Agent/Knowledge. Kiểm bằng TestClient trên database tạm, không gọi provider hoặc dùng run của người khác. Data service và React đã có source; chúng **chưa được nối** vào workflow trong `app/runtime/day.py`. Media service mới ở `experiment/` (a0a93f0) có source riêng; kế hoạch nối core ở [media-integration](media-integration/README.md), phần Data/UI nhận ở [handoff](media-integration/UI_DATA_HANDOFF.md).

| Đầu nối cần chốt | Hiện tại | Để ghép đúng phần Toàn |
|---|---|---|
| Điểm vào UI | `app.main` trả 404 cho `/api/state`; Data service có facade `/api/*` riêng ở cổng 8001 | API owner chọn một facade cùng origin cho React và nối nó với một nguồn run/state; không khởi tạo hai Session độc lập cho cùng demo |
| Điều phối agent | Data `operation(start_day)` luôn chạy `reference_offer` và ghi `offline_reference`; không gọi graph/tool runner | Data/API owner bổ sung chế độ external agent để bắt đầu ngày mà không tạo offer mẫu; sau đó orchestrator dùng API negotiation/proposal/present và trace thật của agent |
| Brief | Data không có `/api/brief/confirm`; core cần brief đã xác nhận | Chốt endpoint hoặc mapping seller-confirmed brief và version; truyền cùng brief tới cả hai phía trước đề xuất |
| Version seller | Card Data facade thiếu `version`/`brief_version`; body core cần `expected_card_version`, `expected_brief_version` (Data hiện trả 422 nếu nhận hai field này) | Chốt schema facade/version và kiểm trong transaction; React gửi phiên bản vừa thấy, không tự đoán |
| Duyệt và apply | Data legacy accept áp dụng campaign trước khi tạo content job; `content_create` yêu cầu proposal đã `applied`. Core chờ người bán duyệt content trước activation | Data/media/API owner sửa contract và transaction để content job nhận đúng offer đã duyệt nhưng chưa activate; publish + activate đúng version sau quyết định content. Không dùng facade hiện tại để nhận rằng gate này đã đạt |
| Trả lời Không | React/Data có thể dùng `action=accept, rule_answer=false`; core yêu cầu action reject cho Không | Chốt một mapping duy nhất ở facade và thêm test Có/Không, giữ active campaign |
| Knowledge | Data có `learning-input`/`learning-results` và SQLite; core memory đang in-process theo run | Nối worker qua token đúng scope, giữ cursor, evidence IDs và authority rules; không tự copy dữ liệu private sang platform. Chỉ advance sau learning handoff thực sự hoàn tất/skipped có nhãn |
| Số ngày | Frontend/Data mặc định 7 ngày; headless core mặc định demo 2 ngày nhưng `Session`/`SessionManager` nhận `simulation_days` (1–7) | Adapter truyền cùng horizon của Data run; đã kiểm chuyển ngày 2 sang 3 với horizon 7, chưa chạy proof tích hợp 7 ngày. Proof 7 ngày chỉ dùng dữ liệu simulator đã thực chạy; không dùng fixture hai ngày |
| Media | experiment có OpenAI Images/Muse/MinIO jobs; core ContentService vẫn khung, Data vẫn placeholder/fallback | Theo MI01–MI04: sửa product kind D, optional logo/bright style, client HTTP và local artifact/version/review gate; không viết lại provider. UI_PRODUCT vẫn chờ facade transaction |

Chạy kiểm tra hiện có:

```sh
.venv/bin/python -m pytest -q
PYTHONPATH=data .venv/bin/python -m pytest -q data/tests
.venv/bin/python scripts/run_agent_demo.py --mode offline --seed 42
```

Các test từng workstream qua không chứng minh API/worker đã nối nhau. Core không gọi thẳng SQL của Data và không gửi token hoặc Persona vào prompt. Những thay đổi ở interface dùng chung cần cập nhật `docs/DEMO_CONTRACT.md`, frontend/data fixtures và test tương ứng cùng lúc.
