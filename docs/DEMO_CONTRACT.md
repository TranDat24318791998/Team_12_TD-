# Hợp đồng runtime và tích hợp cho demo dưới 2 giờ

Phạm vi do yêu cầu hiện hành: luồng chính, một phiên local shop D; OpenAI cho LLM và ảnh, Muse Gateway cho video. Muse đã có base/key local; OpenAI chờ key/model. Bản sửa ưu tiên phần Toàn: Agent + Tools + Knowledge. [AGENT_TOOL_KNOWLEDGE.md](plans/toan/AGENT_TOOL_KNOWLEDGE.md) quyết định tool calling/ACL; [KNOWLEDGE_CONTRACT.md](plans/toan/KNOWLEDGE_CONTRACT.md) quyết định typed records/views/write semantics. File này giữ runtime/HTTP/media để agent code/review dùng cùng nhau; core đã có code và test với fixture; market/media thật và route nghiệp vụ còn chờ tích hợp. Giữ `docs/CONTRACT.md` cho field không đổi. Không diễn giải file này thành đã hoàn thành Data API v1.

## 1. Quyết định kiến trúc

- FastAPI một process, một phiên demo do `SessionManager.current` giữ; chạy localhost. Không phục vụ nhiều seller thật bằng bản này.
- `create_app` tạo manager và worker pool ở lifespan. Không tạo client mạng lúc import.
- Session là nguồn state nghiệp vụ duy nhất. `states[shop].private.rules` là rules authoritative; MemoryGateway đọc qua Session. Store chỉ giữ prefs/history/calibration/lessons, không copy rules thành bản độc lập.
- JSON seed nạp A–E; workflow và market P0 chỉ dùng D. Thị trường tương lai/Persona không bao giờ thành prompt.
- LangGraph chỉ làm vòng thương lượng; graph trả result rồi kết thúc. HTTP seller decision tiếp tục workflow từ `pending_card`; không cần `interrupt`, persistent checkpointer hoặc resume sau restart.
- EventLog giữ list trong run, seq tăng bằng lock và append JSONL vào `runs/<run_id>/events.jsonl`. Không replay JSONL để tự khôi phục phiên trong MVP.
- Worker ảnh/video dùng một ThreadPoolExecutor tối đa 4 worker, Session RLock để cập nhật ngắn. Không giữ lock qua provider/network/LLM.
- Mỗi run có một LLMClient; tool loop theo D02a, demo budget64. `remaining_calls` là budget duy nhất. Session.live_calls_left là property đọc từ client. Client reserve trước mỗi network request.
- `LLM_MODE` và nguồn media tách biệt: LLM offline vẫn có thể chạy media thật nếu media client được cấu hình. Pytest luôn inject fake provider; không đọc token thật.

## 2. Model cốt lõi

Dùng Pydantic v2 và `extra='forbid'` cho input/output agent, HTTP. Domain model thuần, không import Session/API/client. Tiền VND integer; finance dùng Decimal ROUND_HALF_UP. Giá trị ROAS JSON hữu hạn hoặc null.

Giữ nguyên các field của ShopPublic/ShopPrivate/ShopRules/FeeConfig, Package, PlatformTurn, ShopTurn, NegotiationResult, Calibration, LessonOp, NightSummary, DayMetrics trong CONTRACT. `Package`: voucher whole percent 0–30, ngân sách >=0, stop null khi không ads, duration 2–14; validator xử lý quy tắc shop. Khi model output không parse được, dùng fallback; không nới schema.

### Model mới và field bổ sung

| Model / module | Field chính xác |
|---|---|
| IntentBrief / `domain/models/intent.py` | `brief_id:str, version:int, shop_id:str, intent:Literal['increase_orders'], goal_vi:str, allow_ads:bool, ads_daily_cap:int|None, content_refresh:bool, duration_days:int, confirmed:bool` |
| PublicTurn / `domain/models/negotiation.py` | `turn_id:str, actor:Literal['platform','shop'], round:int, action:str, package:Package|None, message_vi:str` |
| RefereeDecision / `domain/models/negotiation.py` | `action:Literal['continue','refocus','ask_human','stop'], reason_vi:str, evidence_refs:list[str], unresolved_terms:list[str], next_actor:Literal['platform','shop','seller']|None, focused_question:str|None` |
| Card / `domain/models/cards.py` | Field cũ + `version:int=1, brief_version:int` |
| SellerDecision | Field cũ + `expected_card_version:int, expected_brief_version:int`; HTTP P0 chỉ accept/negotiate/reject; edit/defer chưa hỗ trợ |
| ContentDraft | Field cũ + `card_id:str, brief_version:int`; `version` 1..3 tính trong một card |
| ContentText / `domain/models/content.py` | `title:str, description:str, checks:list[str]`; title/description chỉ dùng verified facts |
| Preference / `domain/models/learning.py` | `pref_id:str, shop_id:str, field:Literal['content_style','voucher_max_pct'], value:str, status:Literal['candidate','asked','confirmed','declined'], evidence_seqs:list[int], asked_day:int|None, declined_until:int|None` |
| ForecastSnapshot / `domain/models/metrics.py` | `prediction_id:str, shop_id:str, target_day:int, raw_point:float, issued_point:int, factor_used:float, package:Package` |

Public brief không tự copy hard cap 45.000đ của shop vào `ads_daily_cap`. Mặc định field này null, nghĩa là chưa có ngân sách người bán chủ động công khai; shop vẫn enforce hard rule 45.000đ. Nếu seller cung cấp public cap khác thì lấy min với hard rules ở shop. Không ép live LLM phải đề xuất 70.000đ khi public brief đã chặn mức đó.

Referee chỉ nhận public brief + PublicTurn + public violation codes; không nhận ShopPrivate, private_note, raw Session, full EventLog hoặc finance cụ thể.

### Session fields tối thiểu

```text
run_id, settings, world, states, day=1, step='idle', interactive=True
brief: IntentBrief|None
pending_card: Card|None
approved_card_id: str|None
content_draft: ContentDraft|None
last_night: NightSummary|None
memory, log, llm, content
negotiation_attempt: int=0
rules_version: int=1
knowledge_revision, memory_cursor  # read-only properties từ store, không copy counters
forecast_snapshots: dict[(shop_id,day),ForecastSnapshot]
settled_days: set[int]
night_receipts: dict[int,dict]
apply_receipts: dict[(card_id,draft_version),dict]
phase_busy: bool=False
lock: threading.RLock
```

ShopState vẫn có public/private/persona/active/cooldown_until/metrics. Persona chỉ simulator dùng. `SessionManager.reset()` tạo run mới; callback giữ run cũ không được ghi vào manager.current mới.

## 3. API và trạng thái

Chỉ route dùng SessionManager. Backend không tin shop_id của browser; P0 route luôn D. Lỗi thống nhất `{"error":{"code":"...","message_vi":"..."}}`. HTTP422 cho input không hỗ trợ,409 cho sai state/version,503 khi nội dung chưa cấu hình. API không trả token, URL có credential hoặc stacktrace.

| Route | Request | Response/side effect |
|---|---|---|
| POST /api/reset | `{memory?:true,seed?:42}` | run mới, day1, mode, state; seed42 mặc định |
| GET /api/state | — | StateView cũ + `brief, rules_version, confirmed_style_notes:list[str], busy:bool`; không serialize Session |
| POST /api/brief/confirm | `{intent:'increase_orders',goal_vi,allow_ads:true,ads_daily_cap:null,content_refresh:true,duration_days:3}` | `{brief,step:'brief_confirmed'}`; id/version server cấp; chỉ ở idle |
| POST /api/day/start | — | `{day,step}`; tạo thương lượng/thẻ hoặc câu hỏi ngày2 |
| GET /api/events?after=N | — | `{events,last_seq}` của current run, own-seller projection |
| POST /api/decision | `{card_id,expected_card_version,expected_brief_version,action:'accept'|'negotiate'|'reject',note_vi?:'',rule_answer?:null}` | `{step,card?}` |
| POST /api/content/retry | `{card_id,expected_brief_version,expected_draft_version,feedback_vi}` | `{draft}`; tạo bản tiếp theo ngay, job chạy nền |
| POST /api/content/apply | `{card_id,expected_brief_version,expected_draft_version,cover_option:'A'|'B'|'C',skip_video:false}` | `{listing}`; xác nhận bản nội dung, áp dụng listing và kích hoạt gói một lần |
| POST /api/night | `{expected_day:int}` | `{summary,next_day}`; settle→learn→advance một lần; sau ngày2 next_day=null |
| GET /api/proof | — | 409 `PROOF_NOT_READY` khi chưa có đối chứng thật |

State `idle → brief_confirmed → negotiating → awaiting_decision → content_review → day_done → idle` (ngày2). Nhánh không content: accept→day_done. Reject→day_done. Ngày2 question-only resolve→day_done. Night cuối ngày2→complete. Giữ `night_done` trong enum nếu đã có, nhưng endpoint này advance xong trả idle/complete; `last_night` vẫn đọc được.

Sau night, idle + day=2 + brief.confirmed=true hiển thị Bắt đầu ngày 2, không bắt xác nhận lại brief. `StateView.busy` đọc `Session.phase_busy`; không tạo hai cờ độc lập.

`/day/start` là sync trong handler thường `def`, FastAPI threadpool chạy; UI thấy busy local ngay, có thể poll events từ request khác. Mỗi model call tối đa 8 giây, tối đa 12 actor invocations, mỗi invocation tối đa 3 model calls = 36 calls/negotiation (trọng tài sau mỗi lượt sàn/shop); không giữ Session.lock cả vòng. Server đánh dấu busy trước khi nhả lock, command xung đột trả 409. Không làm thêm operation/job framework cho day start.

P0 chỉ nhận brief tăng đơn với allow_ads=true, content_refresh=true, duration_days=3. Giá trị ngoài slice trả 422 `DEMO_BRIEF_UNSUPPORTED`; không xây thêm nhánh rồi bỏ thiếu UI. Public cap được chọn hoặc null. Gateway HTTP retry/apply cần cả card và brief version vì draft version bắt đầu lại từ 1 mỗi card.

### Decision semantics

1. Card cũ/version sai →409 trước side effect.
2. Question-only: `action=accept,rule_answer=true` là Có; `action=reject,rule_answer=false` là Không. Chỉ sửa rules/preferences, không tạo ActivePackage/content job. Giữ gói đang active.
3. Offer accept: ghi approval, chưa activate nếu cần content. `ContentService.start(D)` trả draft và khởi động jobs. Nếu không content, activate ngay qua helper dùng chung.
4. Offer negotiate: tối đa một lần trong demo. Chỉ hỗ trợ note chọn sẵn `Giảm voucher còn 2%`; tạo attempt mới, Card ID mới, giữ brief. Text khác→422 `DEMO_NOTE_UNSUPPORTED`. Agent vẫn nhận owner_note. Không đưa note private cho sàn.
5. Offer reject: resolve card→day_done, không tạo content/gói mới. Giữ active cũ nếu có. Reject không phải lỗi server.
6. `ask_human`/`stop` từ referee: không tạo offer đã agreed; kết thúc có lý do/failed, trả step=brief_confirmed và clear busy, UI cho reset/chỉnh lại brief bằng reset. Free-form clarification chưa làm. Đây là giới hạn demo, không giả vờ đã hỗ trợ hội thoại bất kỳ.

## 4. Gói, tiền, privacy

- Offline sàn mở đầu đúng DEFAULT_PACKAGE; shop clamp thành counter45k/3/6.5; sàn accept identical parent ở lượt2. Mọi sửa package phải được ghi thành candidate mới; không accept gói khác âm thầm.
- MAX_ROUNDS tính lượt sàn. Guard counter ở code/graph, không hỏi referee có muốn vượt3.
- `profit_per_unit(D,0)=31625`, ở3%=27136; break-even≈6.2555, stop6.5; voucher4% break-even>6.5 dù vẫn đủ minimum profit.
- B lỗ→content-only warning; cần unit test finance nhưng chưa cần chạy B trong UI.
- Financials tính từ rules thật; allowlist projection rồi leak_guard bổ sung text. Không chỉ regex che số trên nguyên Session.
- Chỉ tăng ngân sách bằng offer mới + seller duyệt; automatic action chỉ pause/reduce.

## 5. Media và phê duyệt

- OpenAI: OPENAI_API_KEY, LLM_MODEL, LLM_MODEL_REFLECT, OPENAI_IMAGE_MODEL để trống đến khi người dùng điền. Video: MUSE_API_BASE_URL=https://muse-api.butterflyro.space, MUSE_API_KEY đã lưu local, MUSE_VIDEO_MODEL=muse-video. Đọc MUSE_API.md; không dùng endpoint useapi.net cũ. MEDIA_MODE tách biệt LLM_MODE, default offline trong Settings và live trong .env local đã chọn.
- Input ảnh sản phẩm D là artifact bắt buộc cần cung cấp/chọn ở D00. Nếu không có ảnh gốc, cần tạo ảnh synthetic trước và ghi nguồn rõ; không dùng đường dẫn D-1.jpg chưa tồn tại.
- Chữ tạo ngay bằng Content Agent (OpenAI hoặc template fallback có nhãn), ba ảnh dùng OpenAI và video dùng Muse chạy nền. Trước khi xác minh wire format ảnh tham chiếu của Muse, dùng text-to-video từ brief đã duyệt và ghi rõ chưa kiểm chứng giữ đúng hình dáng sản phẩm. Khi đã xác minh image-to-video, dùng cover A cùng draft; chọn B/C không tự tạo thêm video. UI ghi đúng nguồn video thực tế.
- `start/retry` trả dưới1s với fake model/provider; live Content có thể cần tối đa24s trước khi trả chữ, UI hiển thị busy; mỗi real model call có timeout8s; Content invocation tối đa3 calls. Không chờ ảnh/video trong HTTP response.
- Worker capture `(run_id,card_id,brief_version,draft_version)`. Trước callback ghi state, so khớp current session/draft và chưa published. Kết quả cũ được bỏ qua, không ghi đè listing.
- Image/video status dùng enum cũ: image running/done/failed/cached; video pending/running/done/failed/cached. `path` chỉ có khi local file thực tồn tại. `cached` phải là file tương ứng input/model/prompt, không lấy media bất kỳ rồi nhận là đúng brief.
- Ba bản tổng cộng = initial +2 retry. Feedback tạo style cho draft hiện tại; chưa thay rules dài hạn.
- Apply chỉ khi cover đã chọn done/cached. Video phải done/cached, hoặc seller gửi `skip_video=true` sau khi xem trạng thái đang chờ/lỗi. Bản đã publish không tự gắn video trả về muộn. Đóng băng selected media.
- Chữ ký service: `ContentService.apply(shop_id, cover_option, *, skip_video=False) -> ShopPublic`; runtime validate các ID/version trước rồi chuyển skip flag. Service không tự kích hoạt gói.
- Constructor demo: `ContentService(session, *, image_client, video_client, executor)`; manager truyền clients và app-owned executor. Session không tự tạo thêm pool. Exact helper/callback signatures ở task D05a; không dùng taskqueue ngoài.
- Sau apply, runtime clear content_draft/pending_card/approved_card_id, giữ listing đã publish và receipt. Callback gặp draft=None phải bỏ qua. UI xem kết quả từ ShopPublic, không giữ một draft vừa editable vừa published.
- Cache key gồm source bytes checksum, model/config ID, prompt, style/feedback, media kind; khác version nhưng cùng request đã xác minh có thể reuse. Reset không xóa file đang được replay/cache tham chiếu.
- No generic paid POST retry after timeout: lưu jobid nếu có, poll job đã gửi. Nếu không biết provider đã nhận hay chưa, failed/unknown và chờ xử lý tay; tránh tạo hai job trả phí.

## 6. Memory và simulation

- DayMetrics P0 của D được tính bằng market code deterministic theo seed/day/shop/kind, channel organic/paid tách lúc tính; trả aggregate theo CONTRACT. ROAS=paid revenue/paid spend hoặc null khi spend0.
- ForecastSnapshot trước settlement, raw daily cùng ngày. Không lấy forecast3ngày chia outcome1ngày. Chỉ D 1–2 mẫu→factor giữ1.0 đến đủ5mẫu.
- `market.build_forecast_snapshots(shop,pkg,start_day,seed,calibration) -> list[ForecastSnapshot]` là hàm thuần trả các ngày trong thời hạn. `forecast_package` tổng hợp cùng output. `runtime.activate_approved_package` lưu các snapshot của gói đã duyệt vào Session trước settlement; function forecast không dùng global/Session để tự ghi. Retry apply dùng receipt, không tạo lại snapshot sau khi biết actual.
- History lưu package seller thực sự áp dụng, refs negotiation/card, kết quả công khai; không có lãi/cost/private note trong platform_view.
- Quyền, DTO typed và atomic commit của cả năm ngăn theo KNOWLEDGE_CONTRACT; các mục dưới chỉ giữ kịch bản D. Shop A có fixture seller edit voucher để test preference voucher_max_pct; chưa mở A UI.
- Candidate `content_style='ảnh nền sáng'` lấy từ feedback event có thật. `pref_id` ổn định trong run/shop/field/value. Night chỉ tạo candidate, không sửa rules.
- `Preference.evidence_seqs` là integer event seq. `LessonOp.evidence` giữ đúng CONTRACT: negotiation ID strings có thật; lấy liên kết từ event.data.negotiation_id. Không dùng chuỗi hóa event seq làm mã thương lượng.
- Ngày2 start: đang có gói nên chỉ tạo question card. Yes→append style một lần và rules_version+1; No→declined/14ngày im lặng. Không chạy lại campaign.
- Memory OFF: rules vẫn enforce; không ghi learned history/prefs/calibration/lessons. NightSummary rỗng và có nguồn offline/skipped rõ.
- `/night expected_day=1` gọi lại trả receipt cũ, không settle/học/tăng ngày lần2. `/apply` dùng receipt `(card_id,draft_version)` khi lặp đúng request; đổi cover cùng receipt→409.

## 7. Event tối thiểu

Giữ Event của CONTRACT. Mọi `data` chứa IDs/version liên quan; thêm `source:live|replay|offline|fixture` cho model/media để UI phân biệt. Không ghi secrets/raw prompt riêng vào public event.

Các event cần có: `intent_confirmed`, `day_start`, `platform_turn`, `shop_turn`, `code_check`, `referee_review`, `card_sent`, `seller_decision`, `content_job`, `content_applied`, `package_applied`, `market_result`, `memory_read`, `memory_write`, `night_summary`, `rules_confirmed`.

Tool events thêm `tool_called`, `tool_result`, `agent_completed`: schema và privacy theo D02a. Không xuất raw private ToolMessage. Model source và requested_by phân biệt native tool request với offline dispatch.

`content_job` khi retry chứa feedback_vi và draft version. `seller_decision` chứa card/version và rule_answer. `package_applied` chứa approved card ID và exact package. Platform/referee prompt được dựng từ PublicTurn, không dùng browser seller event stream.


## 8. Runtime giữ phần việc điều phối gốc

D03 có monitor/match/renew helpers theo task gốc 1.6; không cần UI nhiều shop hay Send fan-out để test. Monitor dùng metrics đã settle: dừng ads khi đủ số ngày dưới ngưỡng, tồn kho thiếu hoặc hết hạn; không tăng chi. Match trả selected/rejected có lý do; C stock15 bị loại. Gói hết hạn tạo đề xuất renew mới và cần approval mới. Fixture E kiểm pause trước spend ngày3, fixture A kiểm sở thích voucher; chúng không biến demo D2ngày thành proof A–E.

Day/daystart cùng current session, không dùng persistent interrupt/checkpointer ở slice này. Seller approval và content phiên bản vẫn là gate bắt buộc. Model không được gọi thẳng confirm_preference, commit_memory_updates, apply hoặc provider job.

Market-result evidence giữ card/negotiation/prediction refs xuyên ngày; quy tắc join/không đếm support hai lần theo KNOWLEDGE_CONTRACT mục5.
