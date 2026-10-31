# Growth Agents — hướng dẫn dùng phần dữ liệu local

Service độc lập cho team: **FastAPI + SQLite + file storage local**, cổng mặc định
`8001`. Chạy trên môi trường uv riêng; không cần OpenAI key để khởi tạo, test hay
chạy kịch bản 7 ngày. Code ứng dụng chính và frontend chưa được sửa để nối service.

- Hợp đồng dữ liệu/API: [growth_agents_data_api_design.md](growth_agents_data_api_design.md).
- Tiến độ, quyết định triển khai và kết quả kiểm tra: [PROGRESS.md](PROGRESS.md).
- Bảng kiểm dữ liệu, 61 API, tích hợp agent/demo và nghiệm thu: [DEMO_DATA_CHECKLIST.md](DEMO_DATA_CHECKLIST.md).
- Mọi thay đổi của workstream này nằm trong `data/`, trên nhánh `main`.

## 1. Chạy nhanh

Chạy các lệnh sau **từ gốc repo**. Cần cài sẵn [uv](https://docs.astral.sh/uv/).

```bash
uv sync --project data --python 3.11
uv run --project data growth-data init-db
uv run --project data growth-data seed
uv run --project data growth-data serve
```

`uv sync` tạo `data/.venv`, tải Python phù hợp nếu cần và cài đúng dependency trong
`data/uv.lock`. Không dùng Python 3.9 hệ thống và không cần activate môi trường thủ công.
Nếu uv cảnh báo pyproject ở gốc không có `[project]`, đó là file cấu hình test của repo;
project được chạy vẫn là `data/pyproject.toml` và các lệnh trên tiếp tục bình thường.

Sau khi server chạy:

- API: `http://127.0.0.1:8001`
- Swagger với schema request và nút Authorize: `http://127.0.0.1:8001/docs`
- OpenAPI: `http://127.0.0.1:8001/openapi.json`
- Health: `http://127.0.0.1:8001/health`

Đổi nơi lưu hoặc cổng:

```bash
uv run --project data growth-data --home data/runtime/team-demo serve --port 8002
```

`--home` là option của CLI và phải đặt **trước tên lệnh**. API và các lệnh CLI cần
cùng home nếu muốn nhìn cùng database. Các token cấp cho home này không dùng cho home khác.
Không cần chạy lại seed sau mỗi restart: run và các quyết định đã ghi vẫn còn.

## 2. Thành viên lấy dữ liệu ở đâu?

| Thành viên/module | Bắt đầu từ | Ghi qua |
| --- | --- | --- |
| Agent sàn | GET `/api/v1/runs/{r}/shops/{s}/context`; policies, market, metrics | checks và proposals bằng token platform_agent |
| Agent shop | Context của shop được giao, costs, rules, inventory | checks và counterproposal bằng token shop_agent |
| Orchestrator | Run/state, operation, pending proposal/card | negotiation, present, apply, pause, day lifecycle |
| Giao diện người bán | 9 route `/api/*` bên dưới, cookie phiên riêng | quyết định, retry, chọn bản, kết thúc ngày |
| Học ban đêm | GET `/internal/v1/runs/{r}/learning-input?day=N` | rule-questions và learning-results; bộ nhớ nằm ở module của team agent |
| Content worker | Job được giao; input assets và product facts | upload → complete → content-job result; không tự publish |
| Simulator | Trạng thái gói đã duyệt và phiên bản tồn kho | internal settle-day; route tính số bằng code, không nhận metrics tùy ý |
| Người làm bằng chứng | Hai run cùng kịch bản/seed | CLI compare và export-proof; API proof chỉ đọc kết quả |

Các API v1 trả `{data, meta}`; legacy `/api/*` trả JSON trực tiếp như hợp đồng cũ.
Không mount `data/` hoặc `datasets/` thành static: seed có giá vốn, persona và simulator config.
Chỉ cho client đọc dữ liệu qua API đã phân quyền.

### Token và phiên seller

`init-db` tạo `data/runtime/dev-credentials.json` với token **phát triển local**.
Lệnh chỉ in đường dẫn, không in giá trị token. File đó, database, cookies, report runtime
và môi trường đều được Git bỏ qua. Không đưa token service vào JavaScript của frontend.

Để làm việc thực tế, cấp token hẹp theo run/shop:

```bash
uv run --project data growth-data issue-token --role shop_agent --run-id RUN_ID --shop D --output data/runtime/shop-d.json
uv run --project data growth-data issue-token --role content_worker --run-id RUN_ID --shop D --job JOB_ID --output data/runtime/content-worker.json
```

Token dev của agent sàn và backend có wildcard để kiểm thử local; token dev shop_agent
chỉ được đọc thông tin riêng của D. Khi ghép nhiều service, dùng `issue-token` để giới
hạn run/shop/job. Database chỉ lưu hash token; giữ file token phía backend.

Người bán dùng cookie `growth_sid` HttpOnly. GET `/api/state` khởi tạo một phiên seller
và run riêng nếu chưa có. Cookie dùng Secure trên HTTPS, SameSite=Lax; mutation có
Origin khác host bị từ chối. Sign in with ChatGPT chưa được nối trong mốc local.

## 3. Dùng 9 API demo hiện tại

| Route | Body |
| --- | --- |
| GET `/api/state` | không có |
| POST `/api/reset` | `{"memory":true,"seed":42}` |
| POST `/api/day/start` | `{}` |
| GET `/api/events?after=N` | không có |
| POST `/api/decision` | `{"card_id":"...","action":"accept"}`; thêm `note_vi`, `edited_package`, `rule_answer` nếu cần |
| POST `/api/content/retry` | `{"feedback_vi":"Ảnh nền tối quá, làm sáng hơn"}` |
| POST `/api/content/apply` | `{"cover_option":"B"}` |
| POST `/api/night` | `{}` |
| GET `/api/proof` | không có; chưa có comparison group của phiên thì trả metrics rỗng và giải thích |

Mutation cần `Idempotency-Key`: tạo key mới cho **một thao tác mới**, dùng lại chính
key đó nếu retry do mất kết nối. Gửi cùng key với body khác trả 409. V1 còn cần
`X-Request-ID` để truy vết. Actor/role do token hoặc cookie quyết định, không gửi trong JSON.

Ví dụ với curl, giữ cookie giữa các lần gọi:

```bash
curl -c data/runtime/seller.cookies http://127.0.0.1:8001/api/state
curl -b data/runtime/seller.cookies -H 'Content-Type: application/json' -H 'Idempotency-Key: start-day-1' -d '{}' http://127.0.0.1:8001/api/day/start
```

Lấy `card_id` trong state, duyệt thẻ, chọn bản nội dung rồi mới gọi night. Cần xử lý
`step` từ state: `idle`, `awaiting_decision`, `content_review`, `day_done`, `complete`.
Sau night, ngày tăng đúng một lần; cuối ngày 7 có `next_day=null`, `step=complete`.
Ba phiên bản nội dung là **bản đầu + hai lần retry**; retry tiếp trả 409.

Lệnh smoke tự tạo một phiên mới và đi hết 7 ngày, không reset run của người khác:

```bash
uv run --project data python data/examples/smoke_demo.py --base-url http://127.0.0.1:8001
```

## 4. Ví dụ cho agent/backend

Helper Python ở [examples/member_client.py](examples/member_client.py). Ví dụ dùng
token shop D từ file runtime, không chép token vào source:

```python
import json
from pathlib import Path
import httpx

token = json.loads(Path("data/runtime/shop-d.json").read_text())["token"]
run_id = "RUN_ID"
with httpx.Client(base_url="http://127.0.0.1:8001",
                  headers={"Authorization": f"Bearer {token}"}) as client:
    response = client.get(f"/api/v1/runs/{run_id}/shops/D/context")
    response.raise_for_status()
    context = response.json()["data"]
    rules = context["private"]["rules"]
```

Package dùng **phần trăm nguyên**, không dùng basis points cho voucher:

```json
{
  "content_refresh": true,
  "ads_daily_budget": 45000,
  "voucher_pct": 3,
  "stop_roas_below": 6.5,
  "stop_after_days": 2,
  "duration_days": 3
}
```

Không sửa SQL trực tiếp từ agent. Agent đồng ý thương lượng chưa có nghĩa là duyệt
chi tiền: cần decision của seller/simulated_seller và command apply từ orchestrator.
Khi gặp 409 phiên bản cũ, đọc lại state/context rồi tạo command mới; không tự sửa version.
`GET /events` trả cursor cuối **vùng đã quét**, có thể không có event nhìn thấy; dùng
`meta.next_cursor` cho lần sau. Các endpoint danh sách khác dùng cursor có chữ ký.

## 5. Ghép content và học từ thành viên khác

Mặc định `content_mode=local`, `learning_mode=skip`. Để dùng worker của team:

```bash
GROWTH_CONTENT_MODE=worker GROWTH_LEARNING_MODE=external uv run --project data uvicorn growth_data.api:create_app --factory --host 127.0.0.1 --port 8001
```

Biến tùy chọn `GROWTH_DATA_HOME` đổi runtime path. Trong worker mode, D có job queued;
các shop tự động còn lại dùng text/fallback local để không chặn demo.

**Content:** nhận job ID, token có `--job`, đọc job, upload assets theo URL được cấp,
gọi complete, rồi gửi result với `expected_job_version`. Status running gia hạn lease
120 giây. Kết quả phải có đúng A/B/C với asset ready cùng product. Các path download
do server tạo. Provider call và polling do worker sở hữu; Data API không gọi provider.
Late result của attempt đã supersede bị từ chối. Nội dung đã publish không bị đổi ngầm.

Trong mốc local, worker text chỉ được dùng từ vựng/thuộc tính đã kiểm chứng; đây là
validator bảo thủ cho demo, không tuyên bố kiểm tra ngữ nghĩa mọi câu quảng cáo tự do.
Video vẫn là tùy chọn. Khi worker quá lease, service dùng bản nguồn có nhãn fallback;
không gửi lại paid job mà chưa biết kết quả provider trước đó.

**Learning:** close day tạo handoff pending và chặn advance. Worker đọc learning-input
gồm metrics, forecast, lịch sử, quyết định và feedback đã được scope. Worker ghi memory
vào store của mình, sau đó gửi learning-results có đúng day/settlement_cursor. Báo cáo
Markdown nếu có được upload như internal document; server tạo đường dẫn, không nhận
filesystem path tùy ý. Rule question chỉ đổi luật sau quyết định xác nhận của seller.

Handoff quá 60 giây được đánh dấu skipped với `LEARNING_TIMEOUT`, ghi event cho biết
có thể có partial write ở memory store; không báo học thành công. Worker phải chống học
lặp theo evidence cursor. Memory off luôn giữ initial hard rules/stop mechanism.
Service quét lease mỗi 10 giây và khi khởi động; cũng có CLI `growth-data recover`.
Với external learning, dùng v1 close → kiểm tra handoff → advance; legacy night phù hợp
profile local mặc định, không phải bộ điều phối chờ worker ngoài trong một HTTP request.

Để nối hiệu chỉnh dự báo, khởi tạo `create_app(calibration_provider=read_snapshot)`
hoặc `DataService(..., calibration_provider=read_snapshot)`. Hàm callback nhận
`(run_id, shop_id, day)` và trả `None` hoặc `{version,as_of_day,points,factor,q_low,q_high}`.
Đây phải là hàm đọc store cục bộ nhanh, không gọi mạng/model hoặc ghi DB trong callback.
Chỉ dùng view có `points>=5`, `as_of_day<day`; run memory-off không gọi callback.
Các raw/point/factor sau đó được lưu thành snapshot bất biến để đánh giá đúng theo ngày.

## 6. Dataset, file và các lệnh bàn giao

| Đường dẫn | Nội dung |
| --- | --- |
| `datasets/seed.json` | 5 shop và số liệu ban đầu; backend-only |
| `datasets/public/shops.json` | Catalog công khai |
| `datasets/simulator/` | Scenario, persona và tham số ẩn; không đưa vào prompt |
| `datasets/knowledge/` | 9 Markdown chuẩn có version và nhãn giả lập |
| `datasets/originals/` | 5 ảnh hình học placeholder, không phải ảnh chụp sản phẩm |
| `datasets/pdf/` | 4 PDF trình bày từ cùng nguồn Markdown; không index trùng với Markdown |
| `datasets/manifest.json` | Version, access label và SHA-256 |
| `runtime/growth.db` | SQLite runtime, nhiều run cô lập; Git bỏ qua |
| `runtime/objects/` | File được API phục vụ qua kiểm tra quyền |
| `runtime/exports/` | Báo cáo, replay và dữ liệu xuất thử; Git bỏ qua |

```bash
uv run --project data growth-data export-docs
uv run --project data growth-data seed
uv run --project data growth-data run-scenario --days 7 --seed 42 --compare
uv run --project data growth-data validate-data
uv run --project data growth-data export-proof --run-id RUN_ON --group-id GROUP_ID --output data/runtime/exports/proof-copy.json
uv run --project data growth-data export-replay --run-id RUN_ID --output data/runtime/exports/replay.json
```

`export-docs` cần font Unicode tiếng Việt; tự tìm Arial trên macOS hoặc DejaVu Sans
trên Linux. Có thể truyền `--font /absolute/path/font.ttf` hoặc `GROWTH_PDF_FONT`.
Chạy `seed` sau khi xuất PDF để cập nhật checksum của PDF vào manifest.

`run-scenario --compare` tạo **hai run mới** trong cùng session; in run IDs và group ID,
không in token. Có thể đọc proof qua API với evaluator token scoped tới cả hai run.
Comparison của CLI thuộc session CLI, không tự xuất hiện trong session trình duyệt khác.

## 7. Những gì số liệu chứng minh và giới hạn hiện tại

- Seed giữ phí 8% + 5% + 1,5% và 3.000đ/đơn. D khi có ads bị giới hạn voucher 3%
  bởi tài chính; persona D chỉ có sở thích ảnh sáng, không có voucher ẩn 3%.
- Có 14 ngày lịch sử = 140 channel rows/run. Chạy 7 ngày tạo thêm 35 settlements và
  70 channel rows/run. Lịch sử không trừ lại tồn kho mở đầu và không tính vào proof.
- Simulator có organic/paid riêng, ROAS realized = paid revenue / actual paid spend;
  không chi thì null. Lãi có rounding adjustment, chưa phải lợi nhuận kế toán đầy đủ.
- Driver mặc định là **chính sách tham chiếu bằng code**, không phải hai agent LLM.
  Học chưa được nối nên memory-on/off thường bằng nhau; report ghi rõ. Không xem đây
  là bằng chứng agent học tốt hơn. Có window ngày 4–6 và financial totals 7 ngày;
  variant legacy_6d xuất số đến ngày 6 có nhãn.
- Knowledge là keyword search local, chưa gọi OpenAI Vector Stores. Ảnh/video local
  là placeholder/fallback; không phải ảnh/video vừa được model tạo.
- Live provider chưa nối, mode live trả 503 rõ ràng. Replay trong mốc này dùng fallback
  local, không cần key; export là audit của driver reference với snapshots cuối run,
  không phải recording LLM đầy đủ hoặc player hỗ trợ mọi nhánh tương tác.
- Sites D1/R2, sign-in, LangGraph checkpoint và frontend thật chưa triển khai ở đây.
  Chỉ ứng dụng này giữ state chuẩn; khi chuyển cloud cần adapter và kiểm thử transaction,
  không dùng hai DB cùng writable. File thiết kế được giữ nguyên, không ghi tiến độ vào đó.

## 8. Kiểm thử

```bash
uv run --project data pytest -c data/pyproject.toml data/tests -q
```

Test dùng DB tạm và client giả, không gọi API trả phí. Đã kiểm tra seed/finance,
projection quyền, cross-run/shop, idempotency, rollback, ghi đồng thời, 7 ngày headless,
worker lease, xác nhận luật, keyword search/revoke, upload và legacy facade. Kết quả
HTTP thật và số test mới nhất nằm trong PROGRESS.md. Mở SQLite bằng tool chỉ để kiểm
tra backend; thay đổi nghiệp vụ phải đi qua service command.
