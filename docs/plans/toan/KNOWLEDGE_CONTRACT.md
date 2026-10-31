# Hợp đồng Knowledge cho Agent + Tools

Đây là hợp đồng Knowledge; trạng thái code và đầu nối thực tế ở [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md). Toàn sở hữu schema, quyền đọc/ghi, retrieval, học từ evidence và xác nhận luật. Member dữ liệu cấp store/event/market adapter. [Hợp đồng agent/tool](AGENT_TOOL_KNOWLEDGE.md) quy định vòng gọi tool; [hợp đồng demo](../../DEMO_CONTRACT.md) quy định HTTP và seller approval.

Knowledge ở đây là năm ngăn có cấu trúc, truy vấn theo run/shop/ngành. Tài liệu gốc không yêu cầu embedding hoặc vector database. Dữ liệu sản phẩm đã xác minh và catalog công khai là context nguồn, tách khỏi bài học tự rút ra.

## 1. Năm ngăn và nguồn sự thật

| Ngăn | Dữ liệu | Authoritative | Ai thay đổi |
|---|---|---|---|
| Rules | ShopRules, version, nguồn seed/seller confirmation | Session.states[shop].private.rules, Session.rules_version | confirm_preference sau seller handler hợp lệ |
| Preferences | Candidate, support/evidence, asked/confirmed/declined | Store namespace preferences | Night thêm support; seller xác nhận/từ chối |
| History | Gói đề xuất/đồng thuận/thực sự áp dụng, seller action, public outcome | Store namespace history | Night từ events đã xảy ra |
| Calibration | Cặp forecast/actual cùng ngày, ratio, factor, khoảng dự báo | Store namespace calibration | Code tính, không giao LLM tính |
| Lessons | Text, scope, score, evidence, version | Store namespace lessons | LLM đề xuất; gateway kiểm rồi commit |

Namespace bốn ngăn store: `(run_id, compartment, shop_or_scope)`. History/preferences dùng shop; calibration dùng category; lessons dùng strategy hoặc category. Rules đọc trực tiếp Session, không giữ thêm bản rules được ghi độc lập trong store. Khi chuyển nguồn rules sang DB, đổi cả gateway/caller cùng lúc.

Session.knowledge_revision và Session.memory_cursor là property chỉ đọc metadata theo run của store, mặc định 0. Rules_version độc lập vì knowledge commit không được sửa Rules. Demo D có một rules_version; mở nhiều shop sau demo phải chuyển version thành theo shop.

## 2. DTO và record bắt buộc

Định nghĩa trong app/domain/models/learning.py, Pydantic v2 extra='forbid'. Tiền integer VND, float hữu hạn hoặc null, list dùng default_factory. Giữ Calibration, LessonOp, NightSummary từ CONTRACT. Các DTO này thay dict không rõ hình dạng ở gateway.

| Model | Field chính xác |
|---|---|
| Preference | pref_id:str, shop_id:str, field:Literal['content_style','voucher_max_pct'], value:str, status:Literal['candidate','asked','confirmed','declined'], evidence_seqs:list[int], asked_day:int\|None, declined_until:int\|None |
| PublicOutcome | orders:int, revenue:int, ads_spend:int, roas:float\|None |
| PublicHistory | negotiation_id:str, shop_id:str, day:int, kind:str, status:Literal['agreed','failed','warning_only'], rounds:int, proposed_package:Package\|None, agreed_package:Package\|None, approved_package:Package\|None, seller_action:str\|None, ads_paused:bool, outcome:PublicOutcome\|None, evidence_seqs:list[int], version:int |
| CalibrationSample | sample_id:str, prediction_id:str, shop_id:str, target_day:int, raw_point:float, actual_orders:int, ratio:float, evidence_seqs:list[int] |
| CalibrationRecord | category:str, value:Calibration, samples:list[CalibrationSample], version:int |
| PublicLesson | lesson_id:str, scope:str, text_vi:str, score:int, evidence:list[str], created_day:int, updated_day:int, version:int |
| PlatformMemoryView | history:list[PublicHistory], calibration:Calibration\|None, lessons:list[PublicLesson], knowledge_revision:int |
| ShopMemoryView | rules:ShopRules, rules_version:int, rules_evidence_seqs:list[int], preferences:list[Preference], knowledge_revision:int |
| ContentMemoryView | confirmed_style_notes:list[str], rules_version:int, preference_ids:list[str] |
| PublicEvidence | seq:int, type:str, negotiation_id:str\|None, text_vi:str, package:Package\|None, seller_action:str\|None, feedback_vi:str\|None, outcome:PublicOutcome\|None |
| LearningEvidence | day:int, from_seq:int, through_seq:int, events:list[PublicEvidence], existing_lessons:list[PublicLesson], valid_negotiation_ids:list[str], knowledge_revision:int |
| LessonBatch | ops:list[LessonOp], max_length=3 |
| MemoryUpdateBatch | day:int, through_seq:int, history:list[PublicHistory], preferences:list[Preference], calibration:list[CalibrationRecord], lesson_ops:list[LessonOp], valid_negotiation_ids:list[str] |
| StoreWrite | namespace:tuple[str,str,str], key:str, value:PublicHistory\|Preference\|CalibrationRecord\|PublicLesson\|None; None là xóa lesson hết điểm |
| MemoryCommit | revision:int, cursor:int, applied_ids:list[str], duplicate:bool |
| KnowledgeCommit | store:MemoryCommit, accepted_lesson_ops:list[LessonOp], rejected_ops:int |

Observation_count là property `len(set(preference.evidence_seqs))`, không lưu support counter riêng. Candidate ID ổn định từ (run,shop,field,normalized_value); mỗi event seq chỉ đóng góp một lần. Value voucher là integer dạng chuỗi, ví dụ '5'; style là chuỗi chuẩn hóa. Preference.field thêm voucher_max_pct để giữ phần Knowledge gốc; màn demo vẫn D/content_style, test headless kiểm A/voucher.

PublicHistory giữ proposed/agreed/approved riêng để không ghi output model thành gói đã áp dụng. Outcome lấy sau settlement; không chứa phí, giá vốn, lãi riêng, raw DayMetrics hoặc private note. Rules_evidence_seqs lấy từ rules_confirmed event thật của shop; seed chưa có confirmation thì [].

## 3. Retrieval và quyền gọi

Backend bind run_id/shop/category/actor/day khi tạo tools. Model không được truyền các giá trị này để đổi quyền. Tool read_memory() không có tham số; wrapper chọn view theo role.

| Role | Tool và kết quả | Dữ liệu không thuộc projection |
|---|---|---|
| Platform | read_memory() → PlatformMemoryView | Rules, preferences, private note, cost/profit |
| Shop | read_memory() → ShopMemoryView của shop được bind | Persona, shop khác |
| Referee | get_referee_context() → brief + public turns + public checks | Raw memory, Rules, private evidence |
| Content | get_content_context() → verified product + ContentMemoryView + current feedback | Financial rules, private cost, unconfirmed preference |
| Learning | read_learning_evidence() → LearningEvidence | Raw audit log, financial secrets, Persona |

Content wrapper lấy ContentMemoryView, không serialize ShopMemoryView. Code night được dùng raw audit/metrics nội bộ; Learning tool chỉ trả public evidence DTO. Kiểm cả field lẫn free text bằng projection/leak_guard.

Retrieval thực hiện filter theo khóa trước khi xếp hạng:

1. History đúng run/shop: tối đa 5 record gần nhất theo (day,negotiation_id) giảm dần; store giữ tất cả record của run.
2. Lessons đúng strategy/category: top 5 mỗi scope, score DESC, updated_day DESC, lesson_id ASC; scope khác không xuất hiện.
3. Calibration đúng category; thiếu thì default factor=1. Memory OFF: Platform view có history/lessons rỗng, calibration=null; forecast dùng default1.
4. Shop luôn có Rules hiện hành; Memory OFF chỉ làm preferences rỗng.
5. Content chỉ có style trong Rules; candidate chưa được duyệt không trở thành default style.

Mỗi retrieval ghi memory_read gồm role, record IDs, versions, invocation ID; public event không chứa private tool result. Runner gửi JSON DTO trong ToolMessage đúng tool_call_id, model tiêu thụ trước finish_role. Chỉ có event mà không gửi tool result lại model là chưa đạt gọi tool.

## 4. Interface giao DB và runtime

```python
MemoryStore.get(namespace, key, default=None)
MemoryStore.put(namespace, key, value)
MemoryStore.list(namespace)
MemoryStore.commit_batch(writes: list[StoreWrite], *, run_id: str,
                         expected_revision: int, new_cursor: int,
                         receipt_key: str) -> MemoryCommit

MemoryGateway(store, enabled, log=None, run_id=None, session=None)
  platform_view(shop_id, category) -> PlatformMemoryView
  shop_view(shop_id) -> ShopMemoryView
  content_view(shop_id) -> ContentMemoryView
  get_rules(shop_id) -> ShopRules
  get_history(shop_id) -> list[PublicHistory]
  get_calibration(category) -> Calibration
  list_lessons(scope) -> list[PublicLesson]
  prefs_to_ask(shop_id, day) -> list[Preference]
  mark_asked(pref_id, day) -> None
  answer_pref(pref_id, yes, day) -> None
  read_learning_evidence(day) -> LearningEvidence
  commit_memory_updates(batch: MemoryUpdateBatch, *, expected_revision: int,
                         expected_cursor: int) -> KnowledgeCommit
run_night(session, day) -> NightSummary
```

Đây là interface Python nội bộ; model wrappers đã bind shop/day. Chỉ runtime seller handler gọi answer_pref, chỉ code night gọi commit_memory_updates. put/commit/answer không được đăng ký thành model-callable tools.

Commit_batch in-memory dùng lock: kiểm receipt/revision/cursor → validate namespace/type → dựng copy áp đủ writes → swap state/metadata/receipt một lần. Một write sai không đổi ngăn nào. New_cursor không lùi; revision mismatch trả conflict. Receipt night:day trùng trả MemoryCommit cũ với duplicate=true; caller lấy NightSummary đã giữ, không chạy lại model. Gateway so expected_cursor với cùng revision snapshot; store CAS revision bảo vệ giữa read/commit. Put chỉ dùng setup/seed/test, không dùng ghi night rải rác.

Member DB thay bằng transaction cùng semantics và contract tests. Durable SQLite adapter ngoài timebox hai giờ; in-memory chỉ atomic trong process, chưa có phục hồi sau restart. EventLog là audit source, chưa có replay engine tái dựng Session.

Mark_asked/answer_pref chạy trong Session.lock của seller workflow; preference change dùng commit_batch để tăng knowledge_revision. Receipt ask:card_id / answer:card_id lấy từ pending card do runtime bind. Answer_pref chuẩn bị và validate mọi thay đổi trước, commit preference rồi cập nhật Rules trong cùng lock; property reads cũng dùng lock. Duplicate receipt không tăng rules_version lần 2. Không tuyên bố transaction phân tán DB+Session; khi thay store durable phải chuyển rules write cùng transaction.

## 5. Night và phép toán lesson

Run_night sau settlement một lần, chụp revision/cursor/through_seq trước model. Evidence là events đúng run/ngày, trong snapshot đã chụp; tool events vừa ghi không tự trở thành evidence học của chính invocation. Với gói còn chạy qua ngày sau: market_result.data giữ card_id, negotiation_id và prediction_id lấy từ active package/approved history. Nếu market adapter chỉ trả DayMetrics, runtime bổ sung refs từ approved card trước khi ghi event. Read-learning snapshot join public history và public events gốc được tham chiếu (ngày1) làm context; chỉ seq mới ngày hiện tại là support/cursor mới. valid_negotiation_ids gồm ID gốc đã xác minh qua join, không sinh ID mới cho ngày2. Tool read trả cùng snapshot.

Code tạo history từ package thực áp dụng, candidate từ seller feedback/edit, calibration từ snapshot trước settlement. Learning Agent gọi read_learning_evidence rồi finish_learning(LessonBatch). Runner chỉ kiểm schema và evidence tool đã đọc thành công; gateway kiểm từng op trước khi tạo StoreWrite; model không ghi ngăn nào.

| Op | Validation và thay đổi |
|---|---|
| ADD | Evidence hợp lệ, scope strategy/category hiện tại; ID ổn định, score 2, version 1 |
| UPVOTE | Lesson tồn tại đúng scope, evidence mới hợp lệ; score+1, version+1 |
| DOWNVOTE | Như UPVOTE; score−1, xóa khi score<=0 |
| EDIT | Lesson tồn tại, text qua privacy/grounding, evidence hợp lệ; thay text, score+1, version+1 |

LessonOp.evidence là negotiation ID thật từ event.data.negotiation_id; Preferences giữ event seq integer. Valid IDs được server dựng từ snapshot, không tin list do model đưa. Text có số private hoặc claim thiếu evidence thì reject op. Tối đa30 lessons/scope; vượt thì loại score thấp nhất, updated_day cũ nhất, tie-break lesson_id. Deduplicate ADD cùng normalized text/scope; cùng evidence không tăng điểm hai lần. Captured lesson versions/revision stale thì conflict, không tự retry vô hạn.

Giới hạn bản demo: `LessonOp.text_vi` chỉ nhận đề xuất định tính, bắt đầu bằng “Ưu tiên”, “Nên”, “Cần” hoặc “Xem xét”, không chứa chữ số hoặc số viết bằng chữ, và không khẳng định sự kiện đã xảy ra hay quan hệ nhân quả. Nhắc góp ý phải có feedback tương ứng; nhắc kết quả/đơn/ROAS phải có market outcome. Văn bản không hợp lệ bị reject, không bị tự sửa. Số liệu vẫn được giữ và đọc qua History/Calibration có cấu trúc; giới hạn này không áp dụng cho IDs, metadata hoặc Preferences. Gate từ vựng/evidence là kiểm tra bảo thủ, không phải bộ hiểu ngữ nghĩa tổng quát.

Night commit bốn ngăn/cursor/revision một lần rồi ghi memory_write/ngăn và night_summary. KnowledgeCommit trả accepted_lesson_ops/rejected_ops đã kiểm ở gateway và MemoryCommit của store; NightSummary lấy đúng các kết quả đó, không đoán số rejected từ chênh lệch record IDs. NightSummary là phần trình bày, không thay records. Invalid lesson op được ghi rejected, các records hợp lệ vẫn có thể commit; lỗi kỹ thuật lúc commit phải rollback toàn batch. Memory OFF bỏ writes/reflection, Rules vẫn enforce. Fallback đọc evidence thật và ghi source=offline, không gắn nhãn live.

## 6. Forecast, seller confirmation và dùng lại

Member market cung cấp build_forecast_snapshots/forecast_package/simulate_day; D04 nối, không viết lại. Sample ID=(shop,target_day,prediction_id); ratio=actual_orders/raw_point cùng ngày và raw>0. Giữ30samples mới nhất theo(target_day,sample_id), đủ5 mới factor=median(ratios), q_low/q_high=quantile10/90 bằng nội suy tuyến tính trên sorted ratios (index=(n-1)*p); không tự thêm clamp khác tài liệu. Ít hơn5samples giữ factor=q_low=q_high=1; D1–D2 chỉ 1–2 points thì factor=1. Snapshot gói duyệt phải lưu trước settlement, không lấy forecast 3 ngày chia outcome 1 ngày.

Ngày2 tạo question từ candidate có observation_count>=PREF_ASK_THRESHOLD (hiện1), mark_asked sau khi phát hành card. Seller Yes dùng field/value trong RuleQuestion đã lưu, không arbitrary patch. Style append một lần. Voucher parse integer0..30 và chỉ hạ cap hiện hành. No giữ Rules, declined đến day+14. Test A/voucher dùng seller edit fixture, không mở thêm A UI.

Bằng chứng knowledge đạt gồm đọc lại và tác động:

- D feedback → candidate → Yes → Content Agent tiếp theo gọi get_content_context; ToolMessage có style đã xác nhận, output/prompt media có nền sáng. Trước Yes chưa có default style đó.
- History/lesson sau night → Platform Agent gọi read_memory; fake model ra quyết định từ record nhận qua ToolMessage. Thay record hợp lệ thì output đổi tương ứng; assert memory_read event riêng là chưa đủ.
- Memory OFF vẫn giữ finance/Rules; fake model không nhận learned history/preferences/lessons.

Fixture chỉ dùng test isolated/bàn giao khi dependency chưa xong; phải ghi source='fixture'. Gate integration dùng adapter thật cùng backend; fixture không chứng minh revenue uplift. Runner đối chứng mặc định 6 ngày, days là tham số, thuộc member simulation/follow-up. Chưa có kết quả thì /api/proof vẫn PROOF_NOT_READY.

## 7. Bàn giao và tiêu chí đạt

Fixtures contracts/knowledge/: platform_view.json, shop_view.json, content_view.json, learning_evidence.json, night_batch.json, knowledge_commit.json, seller_confirmation.json. Envelope `{source:'fixture',payload:<DTO>}`; test parse payload theo DTO. Không nhúng token/Persona/market tương lai.

Hoàn tất khi năm ngăn có records/views, native retrieval có ToolMessage, bốn ngăn học commit một lần, Rules chỉ đổi sau seller confirmation, đủ bốn LessonOp qua validation và test knowledge→agent output. Thiếu key chỉ hoãn smoke OpenAI, không bỏ native tool adapter hoặc thay gate bằng summary tĩnh.


Receipt trả lại phải nhất quán: store receipt giữ MemoryCommit; gateway giữ KnowledgeCommit/NightSummary theo receipt trong run để caller lấy lại cả accepted/rejected, không chạy model thêm. Lỗi sau store commit nhưng trước log/summary: dựng lại summary từ KnowledgeCommit đã lưu, không gửi lại batch với evidence khác. PublicHistory.warning_only giữ nguyên để nhánh B không fail schema. Mixed batch valid ADD + invalid evidence ADD phải commit valid op, rejected_ops=1, giữ history/preferences/calibration hợp lệ.

Test cross-day bắt buộc: D apply ngày1, ngày2 không negotiation mới; outcome ngày2 cập nhật đúng PublicHistory.negotiation_id cũ, không mất history hoặc nhân đôi support của event ngày1.
