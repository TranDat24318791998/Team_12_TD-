# Bàn giao React Growth Agents

Frontend hiện dùng **React 19.2 và esbuild** trong `frontend/`. Năm trang dùng cùng bundle `frontend/js/app.js`; FastAPI đã phục vụ thư mục này tại `/`, nên không cần đổi route backend để mở giao diện. Tông cam, bố cục sản phẩm và các thao tác demo được giữ lại từ bản HTML.

Giao diện được cập nhật theo [thiết kế dữ liệu v1.1](../data/growth_agents_data_api_design.md), đặc biệt mục 10 về adapter dành cho seller. Bản chính chạy **7 ngày**, kết thúc với `step = complete`, `next_day = null`. Backend data service và các route nghiệp vụ hiện còn là khung; việc tạo database, phân quyền và transaction thuộc nhóm backend.

## Requirement for frontend và data

Trước khi ghép backend, đọc [FRONTEND_REQUIREMENTS.md](FRONTEND_REQUIREMENTS.md) và [FRONTEND_DATA_REQUIREMENTS.md](FRONTEND_DATA_REQUIREMENTS.md). Hai tài liệu phân biệt facade hiện hành với các mở rộng `TODO(contract)`, mô tả payload đang được React hỗ trợ và checklist nghiệm thu backend/data.

Màn Demo có khối tương tác ở `src/components/AgentActivity.jsx`, projection thuần ở `src/activity.js`: số vòng/attempt, thẻ sàn–shop, hướng chuyển lượt, checks, trọng tài và so sánh gói. Không có telemetry thì hiển thị các việc đã hoàn tất và chờ phản hồi; chỉ ghi “đang xử lý” khi có event/snapshot running hợp lệ. Thương lượng lại tách negotiation_id, giữ lịch sử cũ. Mất mạng giữ dữ liệu gần nhất và tắt nhãn đang làm.

Preview v3 minh họa thêm `agent_activity` và `referee_review`; source này không phải backend thật hoặc tracking conversion. Số ngày vẫn là 7, nội dung vẫn có 3 attempt tổng cộng. Polling đọc tiếp trong khi POST còn chờ, write vẫn được serialize. Ngày cuối thanh bước hoàn tất; từ chối/question-only bỏ qua nội dung/áp dụng khi có bằng chứng phù hợp.

## Mở bản đã build

Tại gốc repo:

```sh
python3 -m http.server 8000 --directory frontend
```

Mở http://localhost:8000/?preview=1. Để kiểm tra cùng FastAPI sau khi cài dependencies Python, chạy `uvicorn app.main:app --reload` rồi mở cùng URL.

Luồng thử: Bắt đầu demo → chờ đề xuất → Thương lượng thêm hoặc Đồng ý → góp ý và Làm lại → chọn ảnh A/B/C → Dùng bản này → Kết thúc ngày → Sang ngày tiếp theo → Xem bằng chứng. Ngày cuối hiện Hoàn tất 7 ngày và không tạo ngày 8.

`?preview=1` dùng bộ dữ liệu mẫu trong trình duyệt, không gọi backend hoặc API trả phí. `?preview=0` gọi backend thật. HTTP mặc định dùng API, trừ khi tab đã chọn preview trước đó; dùng tham số rõ ràng để chuyển nguồn. API lỗi sẽ hiện lỗi, không tự lấy số liệu mẫu thay thế.

Mở qua HTTP vì bundle dùng ES modules; không dùng cách nhấp đúp file HTML. Bản HTML cũ còn trong `static/` để tham khảo, không phải frontend FastAPI đang phục vụ.

## Sửa và build source

Cần Node 20 trở lên:

```sh
cd frontend
npm install
npm run build
npm test
```

`npm run dev` theo dõi source và build lại. Trình duyệt vẫn mở qua FastAPI hoặc HTTP server ở trên; tải lại trang sau khi build. `npm run dev` không tạo thêm máy chủ Node.

Bundle production và thông báo bản quyền ở `frontend/js/` đã được tạo, có thể phục vụ ngay khi chưa cài Node trên host. Khi sửa source, chạy build và đưa bundle cập nhật cùng source vào bản bàn giao. `node_modules/` và `.test-build/` được Git bỏ qua. CSS và ảnh được phục vụ trực tiếp, không qua build.

## Cấu trúc frontend

| Đường dẫn | Trách nhiệm |
| --- | --- |
| `frontend/index.html` | Entry trang sản phẩm |
| `frontend/demo.html` | Entry demo thương lượng và nội dung |
| `frontend/updated.html` | Entry sản phẩm sau áp dụng |
| `frontend/night.html` | Entry tổng kết ban đêm |
| `frontend/proof.html` | Entry báo cáo đối chứng |
| `frontend/src/main.jsx` | Khởi tạo React root và chọn nguồn dữ liệu |
| `frontend/src/App.jsx` | Chọn màn theo URL, shell, đặt lại và thông báo |
| `frontend/src/api.js` | Gọi HTTP, cookie, idempotency, lỗi và nguồn preview |
| `frontend/src/useRun.js` | Đọc state/events, polling, thao tác ghi và chờ lệnh đang xử lý |
| `frontend/src/config.js` | Mốc 7 ngày, 3 phiên bản nội dung, 5 điểm hiệu chỉnh theo đặc tả |
| `frontend/src/preview.js` | Kịch bản giao diện mẫu, tách khỏi API thật |
| `frontend/src/format.js` | Định dạng tiếng Việt, URL ảnh, so sánh listing và tải file |
| `frontend/src/components/` | Shell, Product, Proposal, ContentReview, EventFeed và Icon |
| `frontend/src/pages/` | Shop, Demo, Night, Proof |
| `frontend/css/app.css` | Giao diện đáp ứng, chủ đạo cam ở màn demo |
| `frontend/img/` | Ảnh SVG minh họa và ảnh giữ chỗ trung tính |
| `frontend/build.mjs` | Bundle bằng esbuild |
| `frontend/tests/` | Kiểm tra HTTP client, luồng mẫu và render React |

Các trang vẫn có URL `.html`, dùng React để render và xử lý tương tác. Không cần SPA fallback hoặc thay thứ tự mount trong `app/main.py`. Các route API và `/media` phải tiếp tục được lắp trước static `/`.

React giữ nội dung đang nhập và lựa chọn ảnh trong state. Khi có sự kiện hoặc ảnh/video mới từ polling, các input không bị dựng lại bằng `innerHTML`. Nội dung do server/người dùng cung cấp được render dưới dạng text; không dùng `dangerouslySetInnerHTML`.

## Ghép dữ liệu từ database

Luồng đọc là **database → backend → seller facade `/api/*` → React**. React không kết nối SQLite/D1 trực tiếp và không chứa service token. Backend cần hoàn tất adapter để trả đúng các hình dạng của [CONTRACT.md](CONTRACT.md), kèm những mở rộng đã chốt trong [thiết kế v1.1, mục 10](../data/growth_agents_data_api_design.md).

| API React gọi | Nguồn/hiệu ứng cần có ở backend |
| --- | --- |
| `GET /api/state` | StateView của phiên seller, gồm listing gốc bất biến và listing hiện tại, thẻ, bản nội dung, gói đang chạy, tổng kết gần nhất |
| `POST /api/reset` | Tạo run mới cho phiên hiện tại, giữ lịch sử run cũ; body `{memory, seed:42}` |
| `POST /api/day/start` | Bắt đầu ngày hiện tại một lần, agent chạy nền |
| `GET /api/events?after=N` | Sự kiện seller được phép xem và `last_seq` của quá trình quét |
| `POST /api/decision` | Quyết định đúng thẻ/phiên bản; `{card_id, action, note_vi, rule_answer?}` |
| `POST /api/content/retry` | Tạo attempt tiếp theo theo `{feedback_vi}`, tối đa 3 attempt tổng cộng |
| `POST /api/content/apply` | Duyệt và áp dụng phương án ảnh đã sẵn sàng theo `{cover_option}` |
| `POST /api/night` | Đóng ngày, chờ learning, cập nhật state và trả `{summary,next_day}`; ngày cuối `next_day=null` |
| `GET /api/proof` | ProofReport đầy đủ 7 ngày từ các lần chạy đã lưu; báo cáo 6 ngày phải được ghi nhãn tương thích |

Facade giữ response JSON trực tiếp, ví dụ `StateView`, không bọc thành `{data,meta}`. Các API `/api/v1` của data service vẫn có envelope; backend adapter chịu trách nhiệm chuyển sang hình dạng facade. Frontend không tự đổi sang endpoint nội bộ hoặc yêu cầu quyền agent.

Các request gửi `credentials: same-origin`. Cookie `sid` là HttpOnly và do backend quản lý. React gọi state trước events ở lần mở đầu để thiết lập phiên. Backend phải kiểm tra quyền run/shop và Origin/CSRF; trường actor/role trong JSON không phải thông tin xác thực.

Tên shop, tiêu đề, giá, tồn kho, danh mục, thuộc tính, ảnh/video, voucher, gói, dự báo và chỉ số đọc từ API. Khi không có ảnh hợp lệ, hiển thị ảnh giữ chỗ; không lấy ảnh quạt mẫu làm sản phẩm khác. Màu sản phẩm được đọc từ thuộc tính dạng `3 màu: Trắng, Hồng, Xanh mint`; chưa có mapping ảnh theo màu trong hợp đồng nên chọn màu chỉ đánh dấu lựa chọn.

## Chống ghi trùng và xử lý lệnh nền

Mọi POST gửi **Idempotency-Key** và **X-Request-ID**. `useRun` chụp mục tiêu khi bắt đầu thao tác: run/ngày, card_id hoặc attempt hiện tại. Body giữ nguyên hình dạng facade, không thêm trường version chưa được hợp đồng cho phép.

HTTP client giữ nguyên key khi mất kết nối, phản hồi không rõ kết quả, lỗi 5xx, giới hạn 429 hoặc lệnh còn xử lý. Nếu gửi lại cùng mục tiêu nhưng body khác khi chưa rõ kết quả, client chặn và yêu cầu tải lại trạng thái. Sau phản hồi kết thúc, thao tác chủ động tiếp theo nhận key mới. Khi đóng ngày, chỉ coi hoàn tất sau khi ngày tăng hoặc state thành `night_done`/`complete`, không chỉ dựa vào việc NightSummary đã xuất hiện. Key đang chờ nằm trong bộ nhớ của lần mở trang; không có POST tự chạy lại khi tải lại trình duyệt. Backend vẫn phải thực thi idempotency, version check và ràng buộc duy nhất trong transaction.

Khi nhận `202` hoặc `COMMAND_IN_PROGRESS`, React giữ các nút ghi bị khóa và đọc lại state cho đến khi mục tiêu thay đổi, tối đa khoảng 70 giây. Bản facade của `/api/night` thông thường chờ đóng ngày/learning và trả kết quả cuối. Backend không được tăng ngày hoặc chi quảng cáo hai lần nếu nhận lại cùng command.

Lỗi facade dùng `error.message_vi`; client cũng đọc `error.message` tiếng Việt khi middleware trả theo dạng lỗi v1. `409 VERSION_CONFLICT` được hiển thị để người dùng tải lại. Không tự chuyển live/replay/offline hoặc gửi lại provider trả phí từ frontend.

## Các quy ước dữ liệu quan trọng

- **Kết thúc phiên:** state `complete` ở ngày 7; nút bắt đầu/kết thúc ngày bị tắt. Màn đêm dẫn sang bằng chứng, không sang ngày 8.
- **Polling:** màn demo đọc events mỗi khoảng 1,5 giây; state khoảng 1,5 giây, hoặc 3 giây khi duyệt nội dung. Một lượt đọc không chồng lượt trước. Requests đang đọc bị hủy khi rời trang.
- **Sự kiện:** lọc đúng `run_id`, ngày và shop đang điều khiển; cho phép seq có khoảng trống. Backend phải trả `last_seq` sau khi quét cả những sự kiện bị phân quyền lọc đi.
- **Thẻ câu hỏi:** `kind=question` có package/forecast/tài chính null. Có/Không chỉ xác nhận sở thích. Khi offer kèm câu hỏi, gửi quyết định gói và `rule_answer` riêng; Không với câu hỏi không có nghĩa là từ chối offer.
- **Phiên bản nội dung:** `ContentDraft.version` là attempt 1–3 theo v1.1, không phải số phiên bản content tăng toàn cục. Ảnh `done/cached` và có path hợp lệ mới được áp dụng. Video lỗi không cản chọn ảnh.
- **Tài chính:** lợi nhuận, ROAS và dự báo do backend tính. React chỉ định dạng và hiển thị tổng ngân sách bằng ngân sách/ngày nhân thời hạn. Trên thẻ, lãi ghi rõ “/ đơn, chưa trừ quảng cáo”.
- **Tổng kết:** số đơn, ROAS, chi quảng cáo lấy từ `market_result.data.metrics` của đúng shop/ngày. Forecast hiện là dự báo cả gói nên ghi rõ, không so trực tiếp như dự báo của một ngày.
- **Giá trị thiếu:** null không được đổi thành zero để tạo kết quả đẹp. Facade nên bỏ cặp metric không xác định và giải thích trong `note_vi`; React vẫn hiển thị “Chưa có dữ liệu” nếu nhận null.
- **Báo cáo bộ nhớ:** `memory_md_path` phải là endpoint `/api/...` cùng origin đã kiểm tra quyền. Nếu chưa có, frontend cho tải tóm tắt Markdown dựng từ NightSummary, ghi rõ đây là tóm tắt.
- **Assets:** trả URL HTTP(S) hoặc đường dẫn máy chủ `/media/...`, `/assets/...`, `/api/.../download`. Backend phải phục vụ và phân quyền tương ứng. Không trả object-storage credential hoặc đường dẫn hệ thống.
- **Backstage:** chỉ hiển thị projection của seller hiện tại; không dùng payload này làm input cho Platform Agent.
- **Bằng chứng:** fixture trong preview được ghi nhãn minh họa, không đưa vào runtime database hoặc coi là kết quả học.

## Kiểm tra và trạng thái bàn giao

Đã chạy thành công:

- `node build.mjs`: bundle production cùng React runtime và thông báo bản quyền.
- `node build.mjs --tests` và `node --test tests/*.test.mjs .test-build/*.test.mjs`: **34 test đạt**. Bao gồm projection tương tác, nhiều attempt, snapshot cũ, terminal task đến trễ, checks của gói cũ, no-fit/question-only, escaping, idempotency, retry và kết thúc 7 ngày.
- `python3 tests/check_frontend.py`: 5 entry React, bundle, CSS, license và SVG hợp lệ.

Bộ kiểm tra thủ công trên trình duyệt nằm ở `tests/frontend-smoke.html`. Chạy `python3 -m http.server 8000` ở gốc repo, mở http://localhost:8000/tests/frontend-smoke.html rồi bấm chạy. Bộ này dùng thao tác DOM trên React, không cần debug global hoặc gọi API trả phí.

Đợt bổ sung tương tác ngày 31/10/2026 đã chạy browser smoke qua HTTP local và in-app browser: **30 kiểm tra đạt**, gồm layout 390px và desktop thực đo 1230px, thương lượng lại, checks/trọng tài, sửa nội dung, apply, câu hỏi sở thích và từ chối. `tests/useRun-smoke.html` dùng bundle browser được tạo bởi `node build.mjs --tests`; **đã đạt** kiểm tra effects React thật: polling trong khi POST pending, serialize write, không chồng read, không lặp event và dừng polling khi unmount. Không gọi API trả phí.

`python -m pytest -q`: **14 test đạt**, một warning deprecation từ Starlette/httpx. Lượt này chạy bằng Python 3.12 bundled và các dependency cần cho test được cài vào `/tmp/growth-agent-backend-check` với version theo requirements; không sửa Python runtime chung hoặc backend. Nhóm vẫn cần xác nhận môi trường deploy Python 3.11 của dự án và các API nghiệp vụ thật khi triển khai.

Khi backend hoàn tất, chạy `?preview=0` và kiểm tra: cookie giữa hai trình duyệt; phiên chỉ đọc shop của mình; POST trùng/mất mạng; conflict thẻ/attempt; ngày cuối không tăng lần nữa; báo cáo DB không dùng số liệu fixture; download assets/bộ nhớ đã phân quyền. Schema v1.1 hiện là tài liệu thiết kế, chưa phải triển khai database/API.

## Hướng dẫn được áp dụng

Đã đọc [Ponytail](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md) và [codebase-design trong bộ skill Matt Pocock](https://github.com/mattpocock/skills/blob/main/skills/engineering/codebase-design/SKILL.md). Phần React tái sử dụng CSS/ảnh, gom xử lý dữ liệu vào HTTP client và hook, giữ API và lớp backend hiện tại. Không cài thêm router hoặc công cụ quản lý state toàn cục.

Nhật ký đợt chuyển React ngày 31/10/2026: kiểm tra cấu trúc mới `frontend/`, chuyển 5 màn sang React, cập nhật theo data design v1.1, build và kiểm tra như trên. Phần triển khai tiếp theo của nhóm backend là hoàn tất seller facade và persistence theo hợp đồng mới.

12:25 ngày 31/10/2026 (Asia/Ho_Chi_Minh), [3.4/3.5] frontend: thêm sơ đồ sàn–shop, vòng/attempt, so sánh gói, checks và trọng tài; polling trong khi POST; thêm requirements frontend/data và liên kết cho backend agent. Đã build, 34 test Node, kiểm tra assets, 30 browser smoke, kiểm tra effects polling và 14 pytest đạt. Cần backend/data owner chốt các mục `TODO(contract)` và triển khai 9 API thật. Ghi nhật ký tại đây vì `docs/CODEX_LOG.md` đã bị xóa trong working tree trước lượt này; không khôi phục file người dùng đã xóa.
