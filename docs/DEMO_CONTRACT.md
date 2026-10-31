# Hợp đồng tích hợp local — Data, agent và media

Cập nhật 31/10/2026. Đây là hợp đồng dùng chung cho bản local. Chi tiết giao việc của Toàn ở [full-integration](plans/toan/full-integration/README.md); mỗi phần có báo cáo Astra riêng. Nguồn kết quả kiểm thực chạy nằm trong runbook/status, không suy ra PASS chỉ từ tài liệu này.

## 1. Authority và topology

- Một app FastAPI tại 127.0.0.1:8000 ghép Data API, native worker và React. Media `experiment` tại 127.0.0.1:8010, gọi bằng token backend. Khởi động qua factory, không mở DB/provider khi import.
- `data/runtime/growth.db` là nguồn run/day/shop/rules/proposal/card/decision/campaign/stock/listing/content/settlement/events. Knowledge, skill versions, phase/budget receipts lưu trong cùng SQLite. Data cấp IDs và event seq.
- `app/runtime/data_worker.py` gọi native runner/LangGraph qua scoped Data adapters. `Session`/`runtime.day` còn phục vụ core tests/harness độc lập; không chạy chúng như business authority thứ hai trong sản phẩm.
- Data transaction ngắn chứa kiểm version, mutation, event và command receipt; không giữ write lock qua LLM/HTTP/poll. Một native worker giữ file lock; media giữ worker lock riêng.
- Seller cookie là `growth_sid`, HttpOnly/SameSite. Browser chỉ đọc seller projection và same-origin asset URL. Không gửi private rows, Persona, raw prompts hoặc credentials xuống browser/model trái quyền.
- Demo mặc định D, horizon 7; headless hỗ trợ 1..7 và shop được pin vào run. Theo xác nhận người dùng, **D là quạt để bàn từ MinIO**, giữ nguyên số kinh doanh mô phỏng. Facts không còn claim handheld/USB/pin chưa có nguồn.

## 2. Agent, tiền và Knowledge

Năm role Platform/Shop/Referee/Content/Learning dùng runner native: model tool call → role ACL/schema → callable read/compute → ToolMessage → terminal typed output. Tối đa ba provider requests/invocation và ba Platform rounds. Model không được gọi mutation/approval/provider job trực tiếp.

Trọng tài dùng `continue` để cho phép quy trình kiểm tra và trình gói đã đồng thuận; `stop` nghĩa là còn vướng mắc khiến thương lượng thất bại. Sau lượt accept, `stop` không nêu vướng mắc, `refocus` hoặc `continue` còn điều khoản chưa giải quyết đều được yêu cầu làm rõ trong cùng giới hạn ba request. Nếu chưa làm rõ được thì trả ask_human, không tự chuyển thành đồng ý. Tool `get_referee_context` kèm forecast/forecast_turn_id của đúng lượt accept mới nhất, do adapter thị trường tính; không dùng số dự báo của gói trước. Mục tiêu số đơn là kỳ vọng dự báo, không phải điều kiện phải cam kết đạt mới được gửi offer.

Run dùng chung 64 native call reservations bền vững. Demo shop được ưu tiên LLM theo cấu hình; các shop nền vẫn qua cùng graph/tools với transport offline có nhãn để dành budget cho Content/Learning. Cache/replay đúng binding không trừ slot; unknown không hoàn slot và không resend với key mới. Nguồn live/replay/offline/fixture được ghi theo lời gọi thực, không suy từ requested mode.

Platform/Referee không đọc giá vốn/min-profit/ROAS riêng; Shop output qua leak_guard với cùng snapshot tiền đã dùng cho tools. Forecast tool chỉ preview read-only, không tạo proposal. Data finalize sau Referee và code checks; accepted turn chưa được phép tự thành card. Seller approval vẫn là gate cuối.

Giữ Decimal ROUND_HALF_UP, VND integer, voucher percent nguyên0..30, Package duration2..14, stop_after_days1..14. D contribution không voucher31625, voucher3%=27136, break-even≈6.2555, stop6.5; đổi ảnh/tên sản phẩm không đổi các số này. Automatic action chỉ dừng/giảm chi.

Rules đọc từ Data; chỉ seller xác nhận question đã lưu mới đổi. Voucher preference chỉ siết cap. Preferences/History/Calibration/Lessons là dẫn xuất typed có evidence/version. Candidate chưa confirmed không thành Content default. MemoryOFF không đọc/ghi learned state nhưng Rules/facts vẫn enforce. Chi tiết ở [Knowledge](plans/toan/KNOWLEDGE_CONTRACT.md) và [self-improve](plans/toan/self-improve/README.md).

## 3. Seller API

Giữ JSON trực tiếp tại `/api/*`; `/api/v1` dùng envelope. Mọi POST gửi `Idempotency-Key` và `X-Request-ID`. Body cùng key replay receipt, body khác conflict trước side effect. Lỗi seller: `{"error":{"code":"...","message_vi":"..."}}`; input422, state/version409, missing404. Unknown API route trả JSON404.

| Endpoint | Body / response quan trọng |
| --- | --- |
| GET /api/state | run_id/day/step/mode/memory, simulation_days, brief hoặc null, brief_preset/brief_editable, rules_version, confirmed_style_notes, busy/active_operation, negotiation/renegotiation, learning_retry_allowed, current card/draft và nguồn thực |
| POST /api/reset | `{memory,seed}`; run mới, profile do backend chọn external/worker/external; không xóa lịch sử run cũ |
| POST /api/brief/confirm | Gửi nguyên `state.brief_preset` cho demo D → `{brief,step:'idle'}`; ID/version/confirmation do server persist. Sai mục tiêu/ngân sách preset trả422; brief đã xác nhận không được thay thế |
| POST /api/day/start | `{}`; cần brief đã confirmed; operation async →202 với ID/status khi chưa xong |
| POST /api/decision | `{card_id,expected_card_version,expected_brief_version,action,note_vi,rule_answer}`; action accept/negotiate/reject |
| POST /api/negotiation/restore | `{operation_id,expected_operation_version,source_card_id,expected_source_card_version,expected_brief_version,expected_day}`; kiểm và gửi lại offer cho operation thất bại đã lưu trước bản sửa; có Idempotency-Key và X-Request-ID, không gọi model/provider |
| POST /api/content/retry | `{card_id,expected_brief_version,expected_draft_version,expected_job_id,expected_content_id,feedback_vi,retry_scope:'all'}` → draft mới; không chờ render |
| POST /api/content/apply | Cùng binding card/brief/draft/job/content, thêm `{cover_option,skip_video,video_review_ack}` → listing sau transaction approval/publish/activate |
| POST /api/night | `{expected_day}`; settle/learn/advance một lần; pending202 với operation/status, terminal summary/next_day; ngày cuối next_day=null |
| GET /api/events?after=N&run_id=R | `{run_id,events,last_seq,has_more}`; after>=0, bind đúng run; drain đến has_more=false kể cả page bị lọc rỗng |
| GET /api/proof | Report có comparison_id và cặp run hoàn tất chứa active run của seller; không có cặp phù hợp, kể cả sau reset →409 PROOF_NOT_READY, không lấy cặp cũ của cùng session |
| GET /api/proof/events?comparison_id=G | `{comparison_id,run_on,run_off,evidence:{on:Event[],off:Event[]},cutoffs:{on,off}}`; kiểm quyền cả hai run, xuất đủ seller events của đúng cặp đang xem |
| GET /api/proof/demo | Seller D đọc artifact đối chứng offline đã xuất; envelope manifest/report/evidence, kiểm schema/hash, không đổi active run hoặc gọi provider |

Card thêm version/brief_version/negotiation_id/proposal_id/proposal_version và can_negotiate/renegotiations_left. Tối đa hai lần thương lượng thêm; hết lượt vẫn được đồng ý hoặc từ chối thẻ hiện tại. Draft thêm card_id/brief_version/job_id/content_id/job_version/content_version. Draft `version` là attempt1..3, khác content_version và job heartbeat version. Seller action bind draft đã thấy, không tự chuyển sang latest khi conflict.

Draft `text_ready` xác nhận checkpoint chữ đã được kiểm tra và bind đúng content/version. Khi job đang chạy, Apply với skip_video=true được phép dùng ảnh đã tải thành công trong UI và slot done/live của đúng job, sau kiểm bytes/SHA/MIME và approval trong cùng transaction; không chờ các slot khác. Ảnh cache ban đầu chưa phải kết quả của job không đủ điều kiện. Làm lại vẫn chờ media được xử lý. Worker hoàn tất hoặc lỗi muộn chỉ cập nhật bookkeeping, không thay nội dung đã publish và không gắn lại video đã bỏ qua.

Luồng staged media mới cũng cho phép skip_video từ `image_ready`, `video_queued`, `video_ready` hoặc khi video thất bại, dựa trên snapshot chữ/ảnh đã kiểm của image stage. Có thể dùng ảnh ngay mà không submit video; video đã submit vẫn được theo dõi và kết quả muộn không sửa listing. Luồng dùng video giữ nguyên binding reference, review và xác nhận lệch thời lượng.

State chính: idle (brief chưa/đã confirmed) → negotiating → awaiting_decision → content_review → day_done → idle ngày sau hoặc complete. UI dùng brief.confirmed, không cần bước brief_confirmed riêng. Busy/active operation lấy từ Data, được phục hồi sau reload. Close day chặn operation/negotiation/content chưa resolved; summary có mặt chưa đồng nghĩa night đã advance.

Demo native D lưu preset trong config của run: `{intent:'increase_orders',goal_vi:'Đạt 24 đơn trong 3 ngày',allow_ads:true,ads_daily_cap:45000,content_refresh:true,duration_days:3}`. UI chỉ đọc và xác nhận, không có ô sửa mục tiêu/ngân sách; `brief_editable=false`. Run D native cũ chưa xác nhận nhận cùng preset, nhưng brief lịch sử đã xác nhận giữ nguyên. Backend không tự xác nhận khi khởi tạo và từ chối body khác preset. Mục tiêu là yêu cầu mô phỏng, không phải lời hứa hoặc kết quả đã đạt. Run/reference khác giữ hợp đồng brief riêng.

Question Yes dùng accept/true; No reject/false. Chỉ đổi Rules/preference, giữ campaign hiện hành. Offer accept ghi approval; refresh phải chờ Content Apply mới activate. Reject không tạo content/spend. Negotiate tạo attempt mới theo giới hạn Data; gói hợp lệ và được hai agent thống nhất mới tạo thẻ duyệt mới. Referee stop/ask_human hoặc lỗi kết thúc attempt có lý do, không bịa agreed/card.

`state.negotiation` là null hoặc `{negotiation_id,status,reason_vi,referee_action}` của operation agent mới nhất trong đúng run/ngày/shop; status là queued/running/agreed/failed/unknown. Ngày bắt đầu thành công nhưng không có attempt cho shop không được gắn unknown. Lần đầu không có offer phải hiện lý do thật và đánh dấu bỏ qua bước seller/nội dung/áp dụng; không báo seller đã chọn khi chưa có quyết định.

`state.renegotiation` là null hoặc `{source_card_id,negotiation_id,status,reason_vi,referee_action,changed,restoration_status,restored_card_id,restoration_reason_vi,operation_id,operation_version,source_card_version,restoration_allowed}` của yêu cầu thương lượng mới nhất trong đúng run/ngày/shop. Status queued/running chờ phản hồi, agreed chờ thẻ mới, failed/unknown hiện lý do thực. `changed=false` nghĩa là các agent giữ nguyên điều khoản, không gọi đó là offer đã điều chỉnh. Projection lấy từ operation/command receipt/negotiation đã lưu và phục hồi sau reload.

Khi thương lượng thêm kết thúc thất bại đã xác định, Data kiểm lại gói trước theo Rules, brief, giá vốn, phí và tồn kho hiện tại. Gói còn hợp lệ được gửi lại bằng thẻ mới, proposal tăng version và dự báo được tính lại; giữ ID proposal/negotiation đã thống nhất trước đó cùng lịch sử seller request_changes. `restoration_status='restored'` và restored_card_id chỉ đúng thẻ mới này. Attempt điều chỉnh vẫn là failed. Seller được chọn đồng ý, từ chối hoặc thương lượng tiếp nếu còn lượt; không hiện kết thúc ngày khi thẻ còn chờ. Thẻ cũ bị chặn và replay operation không tạo thêm thẻ.

Gói cũ không còn hợp lệ trả `restoration_status='blocked'` cùng lý do. Operation chưa rõ kết quả hoặc đang chạy không gửi lại offer. Seller đã chủ động từ chối không được tự khôi phục gói. Việc gửi lại offer chưa phải seller approval và chưa kích hoạt campaign/content.

Phiên cũ thiếu metadata restoration hiện nút **Xem lại gói trước** khi restoration_allowed=true. Seller bấm mới gửi POST kiểm lại; GET state/reload không tự đổi dữ liệu. Request sai operation/thẻ/brief/ngày/version bị từ chối; cùng key trả receipt đã lưu.

## 4. Media và publication

Dùng `ContentService(bridge, settings, llm, *, media_client=None)`, `await process_job(run_id,job_id)`, `close()`. Worker đọc approved Data snapshot và checksum-verified original trong registry; native Content trả title/description chỉ từ facts. Text phải được kiểm trước tạo paid jobs và kiểm lại khi nhận result.

Media API qua `MEDIA_API_BASE_URL`/`MEDIA_API_TOKEN`, không import `experiment` vào app. Upload nguồn một lần/binding; image JSON `/v1/image-jobs`, video JSON `/v1/jobs`. Raw Muse `/v1/videos` là tầng API khác; xem [MUSE_API](MUSE_API.md).

- Service hỗ trợ desktop_fan/handheld_fan, optional logo, bright preference. D hiện dùng desktop_fan. Ba ảnh A/B/C của một draft chạy song song; A được nhập và kiểm bytes xong thì khởi chạy video5giây realistic_human từ A cùng attempt, không chờ B/C. Mỗi slot đã sẵn sàng được hiển thị riêng. Chọn B/C không tạo video mới.
- Logo ShopPilot AI do người dùng cung cấp được giữ nguyên ở `frontend/img/shoppilot-ai.png`, dùng cho giao diện và `DEMO_LOGO_IMAGE_PATH`. Live media upload logo cùng ảnh sản phẩm; video nhận ảnh A của cùng attempt. Thay logo không đổi tên shop hoặc số kinh doanh và không tự tạo lại media cũ.
- Initial+2retry, tối đa9image/3video submissions cho cả run; media text/vision tối đa3/video ghi riêng native64. Request body/hash/key/remote ID/status/unknown ở Data; queue limit không thay budget.
- Retry nền sáng là all, giữ images-only semantics của caller cũ. Feedback chỉ tác động draft hiện tại; night tạo candidate, seller Yes mới đổi default.
- HTTP accepted nhưng mất/malformed response là outcome_unknown; không đổi thành known failure để tạo key mới. Remote poll/signature refresh không regenerate. Service restart giữ task ID/unknown, không tự gọi lại raw Muse.
- Signed download chỉ qua configured origin/path, no redirect/Bearer; kiểm MIME/magic/size/SHA rồi import Data assets. Video cap50MB. Browser dùng authenticated Data asset URL; signed/MinIO URL không là listing bền vững.
- Apply cần exact current binding, selected cover ready và bytes đúng checksum/size/ownership. Video pass review có thể include; false/null cần explicit ack hoặc skip. Missing/running/failed video cần skip. Ack không vượt file check.
- Skip publish video=null; late worker không gắn video vào listing đã chốt. Approval+listing+campaign+event+receipt cùng transaction. Failed validation rollback toàn bộ.
- Source fixture/cache/live/unavailable phải đúng bằng chứng. Các output nhập từ bản đồng nghiệp là cache/imported chưa tự chứng minh provider; không gắn nhãn live local.

## 5. Night và self-improve

Data ghi daily prediction trên effective state trước actual và settlement một lần; không lấy forecast3ngày so với outcome1ngày. Public evidence freeze tại settlement_cursor, join exact negotiation/card/decision/applied/campaign/prediction refs. Agreed/approved chưa applied không là fact đã chạy; không dùng mutable latest rows để đoán history.

Một night entrypoint: prior receipt → immutable snapshot → reflection claim → reserve model slots → native Learning/fallback → terminal output → pure stage/compiler/eval → atomic publication. Publication chứa Knowledge/skill versions/meta/full receipt và Data handoff/event/advance trong một short transaction. Rules confirmation+preference cũng atomic. Network không nằm trong transaction.

Seller `last_night.history_updates` và `pref_candidates` là câu tiếng Việt từ snapshot/receipt đã đối chiếu hash; `history_refs` giữ `{record_id,day,version,evidence_seqs}`, `preference_refs` giữ `{record_id,field,evidence_seqs}`. `source` lấy từ receipt, không đoán từ run.mode. Canonical NightSummary/receipt vẫn giữ ID gốc. `learning_retry_allowed` dùng cùng điều kiện với lệnh retry: đúng ngày, handoff failed, reflection không reserved/unknown; UI không tự cấp quyền gọi lại.

Bốn base skills, learned policy chỉ Platform offer/renew với allowlist đã chốt; không sinh arbitrary code/tiền. Version hiệu lực d+1; attempt pin seed/version từ đầu, native và fallback dùng cùng seed nhưng vẫn qua validators/seller. Unknown reflection không resend; retry đọc receipt. Schema/provenance ở [self-improve.v1](../contracts/self_improve/README.md).

D/E ON/OFF proof chạy Data simulator với cùng seed/horizon/scenario, memory tách run; số đo lấy persisted settlements, không yêu cầu ON thắng và không dùng UI preview làm evidence. Calibration chỉ prior-day đủ5samples. Provider evaluation, native fixture protocol, offline simulation, durable persistence và media live là các gate riêng.

Báo cáo demo đã chạy được xuất vào cố định `data/runtime/demo-proof.json` và chọn riêng trong UI. Source `precomputed_offline_simulation`, `provider_eval:not_run`; giữ run IDs/seed/horizon/common brief và các reference thực. Download/log dùng frozen evidence ON/OFF trong artifact. Không lấy events của browser run hiện tại để ghép với pair ở DB khác; artifact thiếu/hỏng trả lỗi có kiểm soát.

## 6. Events và persistence

Business events cùng Data seq; safe telemetry gồm tool_called/tool_result/agent_completed, agent_activity, memory_read/skill_used và record/version refs. Không log raw private ToolMessage. Card/decision/applied events giữ immutable IDs để UI/evidence không lookup nhầm current card về sau.

`code_check.data` giữ `{negotiation_id,proposal_id,round,ok,checks:[{code,ok,message_vi,sources}]}` và quyền seller-private. Mỗi source có `{kind,title_vi,version?,excerpt_vi?,document_id?,download_url?}`, lấy từ phiên bản Rules/giá vốn/phí/tồn kho thực sự dùng lúc kiểm tra. Tài liệu phí được kiểm checksum và gắn nhãn tham khảo giả lập, không phải đầu vào thay cho công thức code. Link tài liệu dùng endpoint Knowledge có xác thực; event cũ thiếu sources thì không suy đoán nguồn mới. Không tạo check cho lượt không có package; React đọc `ok` từ backend. `referee_review.data` giữ `{negotiation_id,round,action,evidence_refs,unresolved_terms,next_actor,focused_question,source}`; mọi chữ được lọc quyền, next_actor là platform_agent/shop_agent/seller/null. Không bỏ câu hỏi trọng tài khi chuyển sang event DTO.

`state.mode` chỉ là cấu hình của run. Nhãn nguồn thực lấy `agent_completed.data.source/error_code` và receipt/telemetry của đúng role/run/shop/ngày. Thiếu telemetry hiện chưa có dữ liệu, không gắn nhãn live chỉ vì cấu hình live.

Event cursor tiến qua event không được seller xem; run change reset buffer. Export phải đầy đủ authorized cursor/JSONL, không giới hạn một page100. Seller proof không tổng tài chính riêng của shop ngoài grant. Missing transcript/source giữ unavailable, không nhập hội thoại preview.

Chạy local và kiểm thực tế xem [LOCAL_RUN](LOCAL_RUN.md). Test dùng temporary DB, explicit fake providers/offline mode, không đọc dữ liệu run người dùng hoặc gọi API trả phí.
