# Phạm vi Agent, Tool và Knowledge của Toàn

Đây là bản đối chiếu phân công gốc với plan đã điều chỉnh. Trạng thái trong bảng là **phạm vi phải triển khai**, không phải xác nhận code đã chạy. Khi code tool runtime, đọc [AGENT_TOOL_KNOWLEDGE.md](AGENT_TOOL_KNOWLEDGE.md); khi code records, retrieval hoặc learning, đọc [KNOWLEDGE_CONTRACT.md](KNOWLEDGE_CONTRACT.md). Lịch giao việc ở [Plan của Toàn](README.md).

## 1. Nguồn và phần việc đã nhận

| Nguồn | Vị trí đã đối chiếu | Kết luận dùng cho plan |
|---|---|---|
| Tệp người dùng `Pasted text.txt`, mở đầu “Mình đã đọc toàn bộ PDF 15 trang…” | Mục 2.2, 8, 10; dòng 85–99, 707–797, 839–898 | Toàn phụ trách agent thương lượng, điều phối, Knowledge, learning; chốt đầu nối với Data/DB, API và Content. Phần chính là task gốc 1.4–1.6 và 2.4–2.5. |
| Cùng tệp | Mục 1.1–1.2, 4; dòng 13–38, 342–436 | Có 15 adapter nghiệp vụ đề xuất. Tool registry và function-calling schema chưa được định nghĩa trong bản gốc. |
| Cùng tệp | Mục 5.1, 10 bước 5, kết luận; dòng 463–475, 880–886, 940 | Knowledge gồm năm ngăn; agent phải dùng lại memory. MVP dùng truy vấn theo khóa; không bắt buộc vector DB, embedding hoặc RAG tài liệu. |
| `resources/w/Growth Agents - Customer Journey & Agents.xlsx` | `Agents & Tools!B4:J5`, `B8:J39` | Bổ sung Referee, thành năm vai trò AI. Có 32 dòng hành động/tool/service đề xuất, không phải 32 function mà model được gọi. |
| Cùng workbook | `Agents & Tools!B43:J48` | Trọng tài chỉ đọc công khai; trả khuyến nghị, lý do ngắn và evidence; graph thực thi chuyển trạng thái. |
| Cùng workbook | `Implementation!B23:J25` | Giữ LangGraph; ba agent tương tác, Content/Learning chạy theo giai đoạn; bổ sung intent và approval version. |
| Task gốc và hợp đồng trong repo | `tasks/TV1-1.4-*` đến `TV1-1.6-*`, `tasks/TV2-2.4-*`, `TV2-2.5-*`, [CONTRACT.md](../../CONTRACT.md) | Giữ interface dùng chung, số do code tính, private projection, seller approval và memory có evidence. |

Theo yêu cầu hiện hành, plan bổ sung **tool calling thật có giới hạn** cho các thao tác đọc và tính toán; đây là quyết định triển khai mới, không phải tính năng đã có trong bản gốc. Tool runtime xác định role, run và shop từ backend. Model chọn tool trong tập được cấp, nhận kết quả rồi đưa ra quyết định. Code vẫn bắt buộc kiểm tra, lọc dữ liệu và thực thi approval.

## 2. Phân công để không ôm cả sản phẩm

| Phần | Toàn phải giao | Member phụ thuộc phải giao | Task hiện hành |
|---|---|---|---|
| Agent/tool runtime | OpenAI tool loop, schema, registry theo role, giới hạn gọi, trace, fallback; prompt và decision của Shop/Sàn/Referee | Key/model qua cấu hình | D02a, D02 |
| Knowledge | Năm record/view, quyền đọc/ghi, retrieval, evidence, học và xác nhận | Store đọc/ghi theo interface; eventlog và dữ liệu đầu vào | D04, D01 |
| Điều phối | Intent, negotiation, thẻ, chờ quyết định, approval/version, gọi content, học và đọc lại | API handler, UI và session wiring theo contract | D03 |
| Tài chính và dữ liệu | Chốt kết quả tool, validator/privacy; dùng dữ liệu đúng quyền | Seed, công thức/fixtures, forecast/actual cùng kỳ từ Data/Market | D01; D02a gọi adapter |
| Content | Dựng context đã duyệt, style đã xác nhận, nối start/retry/apply và test contract | Chữ, OpenAI Images, Muse video, cache, polling, media jobs | D05/D05a: lane tích hợp được giao riêng |
| Web/demo | State/events/fixtures, transcript và lệnh headless có thể kiểm tra | UI và routing | D03, D06; UI ở D05 |

Đầu nối được kiểm bằng fake đúng schema khi member phụ thuộc chưa xong. Fake không được ghi nhãn live. Thiếu provider thật không ngăn hoàn thành logic agent/Knowledge; nghiệm thu media thật vẫn là mục riêng của lane tích hợp.

## 3. Đối chiếu 15 adapter gốc

Tên T01–T15 giữ nguyên để team đối chiếu. Bảng gốc chỉ định nghĩa input/output nghiệp vụ; chữ ký, JSON schema và quyền chính xác lấy từ hai contract mới, không suy ra từ tên tool.

“Callable” nghĩa là được bind vào model của role được phép. “Backend” nghĩa là workflow gọi trực tiếp, không đăng ký làm tool tự chọn của LLM. Một callable validator vẫn phải được graph gọi kiểm lại ở chốt cuối.

| ID | Adapter | Đầu vào → kết quả chính | Thực thi | Owner | Task |
|---|---|---|---|---|---|
| T01 | `get_public_context` | Scope shop/ngày → public listing, trend, calendar, active package công khai | Callable, projection theo role | Toàn dựng projection; Data cấp dữ liệu | D02a, D01 |
| T02 | `get_shop_private_context` | Shop do backend gắn → private profile, rules/version; không Persona | Callable, chỉ Shop đúng scope | Toàn + Data | D02a, D04 |
| T03 | `read_memory` | Truy vấn trong scope đã cấp → typed view/records, IDs và nguồn | Callable, theo ma trận quyền Knowledge | Toàn; DB cung cấp store | D02a, D04 |
| T04 | `validate_platform_package` | Package + public constraints → violations, corrected candidate, changes | Callable; graph kiểm bắt buộc | Toàn/validator owner | D01, D02a, D02 |
| T05 | `evaluate_shop_package` | Package + private scope → financials, safe candidate, violations | Callable, chỉ Shop; graph kiểm bắt buộc | Toàn/validator owner | D01, D02a, D02 |
| T06 | `forecast_package` | Package + public shop/day/calibration → Forecast | Callable, không tự tính trong LLM | Market implementation; Toàn adapter | D02a, D04 |
| T07 | `sanitize_shop_reply` | Text shop + private context nội bộ → text đã lọc, redacted flag | Backend bắt buộc trước public transcript | Toàn | D01, D02 |
| T08 | `read_learning_evidence` | Run/day/cursor đã gắn → evidence được phép cho Learning | Callable; dữ liệu đưa model là public projection | Toàn dùng DB/Market | D02a, D04 |
| T09 | `commit_memory_updates` | Batch + evidence/expected versions → applied/rejected IDs, versions, cursor | Backend; chỉ bốn ngăn dẫn xuất | Toàn kiểm logic; DB commit | D04 |
| T10 | `confirm_preference` | Seller decision + pending question/version → rules mới hoặc declined | Backend; cần seller confirmation hợp lệ | Toàn | D03, D04 |
| T11 | `content_start` | Shop + approved card/context → ContentDraft | Backend sau approval | Media implementation; Toàn nối luồng | D03, D05 |
| T12 | `content_retry` | Draft/version + feedback seller → draft mới | Backend; chặn callback cũ | Media implementation; Toàn nối luồng | D03, D05 |
| T13 | `content_apply` | Approved draft/version + cover → listing đã áp dụng | Backend; listing và campaign có gate riêng | Media implementation; Toàn approval | D03, D05 |
| T14 | `append_event` | Run/day/type/actor/shop/text/data → Event có seq | Backend; projection trước khi xuất | DB implementation; mọi caller dùng | D01, D02a, D03, D04 |
| T15 | `read_events` | Run/cursor/audience do backend gắn → scoped events | Backend cho API/learning | DB/API; Toàn xác định audience | D01, D03, D04 |

Ba callable bổ sung cho workbook là `search_campaign_catalog`, `get_referee_context`, `get_content_context`, định nghĩa ở D02a. Catalog **seed local có source ID, eligibility và thời hạn** thuộc Knowledge bắt buộc; không phụ thuộc fetch từ sàn thật. Hai context tool chỉ trả projection cho role tương ứng.

## 4. Đối chiếu đủ 32 dòng workbook

Vị trí nguồn: `Agents & Tools!B8:J39`. ID bên dưới là ID của bảng tools ở cột B; bảng `RefereeDecision` phía dưới có ID trùng nhưng không phải thêm tool. Các tên hành động ở cột D là tên thiết kế của workbook. Cột implementation là nơi thực hiện ý nghĩa đó; không tạo 32 hàm wrapper rỗng.

| ID / dòng | Tên trong workbook | Mapping implementation hiện hành | Task | Trạng thái phạm vi |
|---|---|---|---|---|
| S1 / 8 | `read_private_shop_profile` | T02 `get_shop_private_context` + T03 `read_memory` của Shop | D02a, D04 | Bắt buộc, callable có scope |
| S2 / 9 | `confirm_intent_brief` | IntentBrief/version + seller confirmation trong runtime; model không tự xác nhận | D03 | Bắt buộc, backend/HITL |
| S3 / 10 | `evaluate_offer_private` | T05 `evaluate_shop_package`; T07 lọc phần công khai | D02a, D02 | Bắt buộc, callable tính toán riêng |
| S4 / 11 | `submit_counteroffer` | `decide_shop` trả ShopTurn; graph kiểm T05/T07 trước chuyển lượt | D02 | Bắt buộc, output agent + graph |
| S5 / 12 | `request_seller_decision` | Card/expected versions + `submit_decision`; agreed chưa phải approval | D03 | Bắt buộc accept/negotiate/reject; defer ngoài demo |
| S6 / 13 | `submit_content_feedback` | Seller feedback gọi T12; approval đúng bản gọi T13 | D03, D05 | Bắt buộc đầu nối; Media làm implementation |
| P1 / 14 | `find_growth_opportunities` | T01 dữ liệu public + runtime lọc cơ hội theo rules code | D02a, D03 | Bắt buộc cho luồng chính; không đọc private |
| P2 / 15 | `search_campaign_catalog` | Callable cùng tên đọc seed catalog có source/validity/eligibility | D02a, D04 | Bắt buộc catalog local; ngoài scope catalog sàn thật |
| P3 / 16 | `build_growth_offer` | `decide_platform` dùng T01/T03/catalog, trả PlatformTurn; T04 kiểm | D02 | Bắt buộc, output agent |
| P4 / 17 | `forecast_package` | T06 `forecast_package` đọc calibration đã cấp | D02a, D04 | Bắt buộc adapter; Market tính số |
| P5 / 18 | `validate_platform_offer` | T04 `validate_platform_package` và kiểm graph bắt buộc | D02a, D02 | Bắt buộc |
| P6 / 19 | `respond_to_counteroffer` | `decide_platform` nhận public counter; accept đúng candidate hoặc propose/withdraw | D02 | Bắt buộc, output agent |
| R1 / 20 | `read_public_negotiation_state` | Callable `get_referee_context` với brief + public transcript/turn IDs | D02a, D02 | Bắt buộc; không raw Session/private |
| R2 / 21 | `assess_goal_alignment` | `review_turn` trả lý do/evidence trong RefereeDecision | D02 | Bắt buộc, output Referee |
| R3 / 22 | `check_negotiation_progress` | Public diff/round trong referee context; graph enforce MAX_ROUNDS | D02 | Bắt buộc, context + code |
| R4 / 23 | `request_refocus_or_clarification` | RefereeDecision.refocus/ask_human; runtime nhận yêu cầu có phạm vi | D02, D03 | Bắt buộc; chưa làm free chat tùy ý |
| R5 / 24 | `recommend_handoff_or_stop` | RefereeDecision.action; graph quyết định route và clear busy | D02, D03 | Bắt buộc; không tự approve |
| C1 / 25 | `read_verified_product_brief` | Callable `get_content_context`: approved card, verified facts, assets, confirmed style | D02a, D04, D05 | Bắt buộc projection; Content dùng |
| C2 / 26 | `generate_copy_and_storyboard` | Content Agent nhận context qua tool, trả chữ/script theo content contract | D05 | Lane Media; Toàn nối role/context và fake contract |
| C3 / 27 | `generate_cover_variants` | `content/images.py` → OpenAI Images; version/job IDs ở service | D05a, D05 | Lane Media, ảnh thật thuộc nghiệm thu tích hợp |
| C4 / 28 | `create_video_job` | `content/video.py` → MuseClient theo MUSE_API.md | D05a, D05 | Lane Media, async; submit chưa phải done |
| C5 / 29 | `validate_creative_claims` | Content checks đối chiếu verified attributes; workflow kiểm output | D05 | Bắt buộc trong lane Media |
| C6 / 30 | `get_job_status_and_revision` | ContentService state/polling + T12 retry; callback kiểm version | D03, D05 | Bắt buộc đầu nối và trạng thái |
| C7 / 31 | `request_3d_render` | Chưa đăng ký tool hay gọi worker 3D | — | Ngoài MVP theo workbook |
| L1 / 32 | `read_scoped_outcomes` | T08 `read_learning_evidence` + T03 records đã cấp | D02a, D04 | Bắt buộc, callable với evidence projection |
| L2 / 33 | `propose_memory_updates` | Learning Agent đề xuất LessonOp; code tạo preferences có evidence, T09 commit | D04 | Bắt buộc; không tự đổi Rules |
| L3 / 34 | `update_forecast_calibration` | Code dùng forecast/actual cùng kỳ, minimum points; T09 commit | D04 | Bắt buộc; không làm tool LLM tự ghi |
| L4 / 35 | `evaluate_goal_and_memory_effect` | D06 kiểm read-back/behavior evidence; `simulation.run/compare` cho proof nhiều ngày | D06; follow-up runner | Read-back bắt buộc; proof định lượng ngoài 2 giờ |
| W1 / 36 | `apply_approved_package` | `activate_approved_package` sau đủ approval, lưu receipt và forecast trước actual | D03 | Bắt buộc, backend |
| W2 / 37 | `apply_approved_content` | T13 với card/brief/draft version và media đã chọn | D03, D05 | Bắt buộc, backend |
| W3 / 38 | `pause_or_reduce_spend` | Monitor đọc metrics + approved stop rule; chỉ dừng/giảm, ghi event | D03 | Backend guard; không tự tăng chi |
| W4 / 39 | `record_event_and_scoped_memory` | T14/T15 eventlog; T03 read; T09 write qua Knowledge gateway | D01, D02a, D04 | Bắt buộc, shared backend |

## 5. Knowledge phải chứng minh được điều gì

Năm ngăn không đổi: **Rules, Preferences, History, Calibration, Lessons**. Schema, namespace, nguồn authoritative và quyền đọc/ghi nằm ở [KNOWLEDGE_CONTRACT.md](KNOWLEDGE_CONTRACT.md). Verified product facts và catalog là nguồn dữ liệu có provenance để đọc qua tool; không gộp chúng thành lesson học được.

Nghiệm thu phần Toàn cần đủ các bằng chứng sau:

1. Tool call có tên, validated args, role/scope do backend cấp, kết quả và source thật; tool không thuộc role bị chặn trước khi đọc dữ liệu.
2. Public history/lessons không chứa private financials hoặc Persona. Shop chỉ nhận private của shop được cấp.
3. Feedback seller tạo candidate có evidence; seller Yes mới đổi rule/version. Night chỉ ghi bốn ngăn dẫn xuất.
4. Lần gọi sau đọc lại record IDs đúng quyền. Test quan sát input Content có confirmed style và input Sàn có public history/lessons; output dùng dữ kiện đó. Chỉ hiện dòng memory trên UI chưa đủ.
5. Memory OFF vẫn kiểm Rules. Samples calibration thiếu thì giữ factor cũ và báo số mẫu thật.
6. Handover có fake adapters, fixtures và trace headless để API/Media/DB ghép mà không sao chép logic agent/Knowledge.

## 6. Cửa sổ demo và proof

Demo tương tác hai ngày là bài kiểm luồng, không phải proof định lượng nhiều ngày. Tài liệu gốc/AGENTS/task runner dùng **6 ngày**; các tài liệu data/cohort có cửa sổ **7 ngày** cho mục đích riêng. Follow-up giữ `simulation.run(..., days=...)` có tham số, mặc định proof theo bản gốc là 6. Không suy ra cohort7 ngày bắt buộc proof7 ngày.

Chạy ON/OFF nhiều ngày thuộc phần simulator sau mốc hai giờ, cùng seed/initial state/policies và từ kết quả thật. Plan không đặt điều kiện memory ON phải thắng, không dùng mock proof thay số thực. UI phụ, analytics đầy đủ, 3D, deploy và production recovery được để sau; tool runtime, Knowledge và bằng chứng dùng lại memory là phạm vi bắt buộc.
