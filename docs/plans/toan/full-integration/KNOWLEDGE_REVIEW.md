# Knowledge: review và kế hoạch nối Data local

What this change does: Knowledge giữ Rules hiện hành, học bốn ngăn dẫn xuất và đưa đúng records vào lần gọi agent tiếp theo. Review này giữ core retrieval/validation đang chạy, thay nguồn business/evidence/Rules bằng Data và nối repository SQLite cùng run. Không viết lại SI compiler hoặc thiết kế bảng lần hai.

Reviewer: Astra max; 31/10/2026; baseline `33fbdd5`. Phạm vi: một máy local, một backend worker, SQLite của Data; demo shop mặc định D, headless shop khác theo run đã bind. Chỉ báo cáo này được ghi; không sửa source, không commit, không gọi provider trả phí.

**CORE FIVE-BIN: PASS ở tests hiện có. DATA-INTEGRATED KNOWLEDGE: FIX REQUIRED. DURABLE/NEXT-USE SAU RESTART: CHƯA TRIỂN KHAI.**

`SELF_IMPROVE_REVIEW.md` sở hữu compiler, skill versions, reflection/publication algorithm và proof SI. `DB_REVIEW.md` sở hữu migration, physical tables và repository transaction. Báo cáo này sở hữu nghĩa năm ngăn, đầu nối Rules/evidence/static references, ACL/read views và acceptance next-use. Coder duy nhất của lane tích hợp chốt một tên file repository: dùng `app/infrastructure/sqlite_store.py` như DB review; tên `knowledge_sqlite.py` trong SI review là cùng adapter, không tạo cả hai.

## 1. Bằng chứng đã kiểm

Đã đọc AGENTS, plan README, KNOWLEDGE_CONTRACT, AGENT_TOOL_KNOWLEDGE, gateway/night/store/session/tools, native knowledge tests, Data context/rules/documents/learning input và hai review SI/DB.

Lệnh đã chạy:

```bash
.venv/bin/python -m pytest -q tests/unit/memory/test_gateway.py tests/unit/runtime/test_store.py tests/integration/agents/test_agent_knowledge_flow.py tests/integration/agents/test_learning_native.py
```

Kết quả: **32 passed in 0.50s**. Tests thực sự đọc JSON trong ToolMessage: cùng logic fake model, có approved history thì voucher 3%, Memory OFF thì 10%; seller Yes làm Content lần sau chọn chữ nền sáng. Cross-day history giữ negotiation cũ, không đếm lại preference support. Đây là core/fake acceptance; chưa chạy qua Data SQLite.

Reproduction bằng `DataService` và database trong `TemporaryDirectory`, không dùng dữ liệu người dùng:

- Tạo run → đọc D Rules cap 8 → worker tạo question `voucher_max_pct='30'` → seller approve → cap thành **30**, rules_version=2. Contract chỉ cho hạ cap.
- `knowledge_documents.type` của bốn guide bằng tên file; ví dụ `content_standards_demo`, trong khi Markdown khai `document_type: content_policy`. Search `query='nội dung', document_types=['content_policy']` trả **[]**.

Không chạy lại full suite trong lane này. Full root/Data/frontend baseline do integrator ghi riêng; 32 tests trên không phủ các adapter chưa tồn tại.

## 2. Giữ đúng nghĩa năm ngăn

| Ngăn | Nguồn authoritative sau tích hợp | Nghĩa record/read phải giữ |
| --- | --- | --- |
| Rules | `DataService.rules`, `shop_rules`, `rule_questions`, seller `decisions` | Đọc version theo `(run,shop)`; chỉ seller confirmation đổi đúng field/value của question đã lưu. Không có bản Rules ghi độc lập ở knowledge store. |
| Preferences | Repository bốn ngăn trong cùng Data DB | Candidate/support là dẫn xuất; evidence seq duy nhất; asked sau card thật được trình; confirmed/declined theo Data decision thật. Confirmed style được dùng từ Rules. |
| History | Public projection từ negotiation/proposal/decision/campaign/outcome Data | Giữ proposed/agreed/applied riêng; `approved_package` hiện mang nghĩa package thực áp dụng theo contract. Agreement hoặc seller approve chưa apply không được điền trường này. |
| Calibration | Code từ daily prediction trước actual + settlement của Data | Khớp `(shop,target_day,prediction_id)`, raw point dương; 30 samples; đủ 5 mới median và quantile10/90. SI/DB lane sở hữu daily prediction source. |
| Lessons | Gateway kiểm rồi commit từ public frozen evidence | Qualitative, đúng scope/evidence, bốn ops/cap/dedupe hiện có; không thay Rules. SI policy artifact là phần bổ sung, không thay PublicLesson bằng markdown report. |

Static knowledge là lớp nguồn khác: verified product facts, policy/fee records, guide documents và `data/campaigns.json`. Không đẩy guide vào Lessons để giả có learning. Không chuyển các PDF presentation trở lại thành nguồn chuẩn; Markdown Data là nguồn guide. Financial computation vẫn dùng code/policy records, không trích prose để tính phí.

Các semantics baseline cần giữ: History top5 theo day/negotiation; Lessons top5 mỗi scope strategy/category theo score, updated_day, ID; namespace cùng run; Rules luôn enforce; candidate không là content default; declined im lặng 14 ngày. Mở nhiều shop phải bỏ scalar `Session.rules_version` khỏi integrated read path, dùng version shop được bind.

## 3. Must fix

### 1. [P1] Hai authority khiến seller Yes không tới Knowledge của agent

**What this is:** `app/runtime/session.py:69–86` tạo UUID, seed states, RAM store và JSONL log riêng. `app/memory/gateway.py:38–39,106–135` đọc/ghi Rules của Session. Data có run, shop_rules và quyết định riêng tại `data/growth_data/service.py:94–98,329–384,415–420`.

**Problem:** Seller xác nhận style qua Data không đổi `Session.states[D].private.rules`; gọi core Content tiếp theo vẫn đọc seed. Ngược lại gọi gateway.answer_pref chỉ đổi RAM, Data validator/media vẫn thấy Rules cũ. Restart mất preferences/history/calibration/lessons/receipts dù UI Data vẫn giữ run.

**Fix:** Integrated Session là context tải từ run Data đã có; gateway nhận Rules/evidence adapter và SqliteKnowledgeStore cùng Data Store. Seller quyết định đi qua Data một lần; cập nhật preference cùng transaction Rules/decision. Không chạy `Session.new()` để tạo business run tương ứng, không mirror Data bằng một Session DB khác.

**If we skip it:** Có thể demo từng backend riêng nhưng xác nhận/next-use không hoạt động xuyên HTTP, worker và restart.

### 2. [P1] Data preference confirmation cho tăng voucher cap trái contract

**What this is:** `RuleQuestionCreate` chỉ kiểm integer0..30 (`data/growth_data/models.py:105–117`); `question` kiểm version (`service.py:423–438`); `confirm_rule` gán thẳng value (`415–420`). Core gateway đã có guard `value <= current cap` (`gateway.py:121–125`).

**Problem:** Reproduction nêu trên tăng D từ 8 lên30 sau Yes. Seller confirmation hợp lệ về quyền nhưng nội dung không còn là learned preference chỉ siết cap theo KNOWLEDGE_CONTRACT mục6.

**Fix:** Data kiểm `0 <= value <= min(30,current voucher_max_pct)` khi tạo question và ngay trong confirmation transaction; stale Rules version vẫn conflict. Kiểm durable candidate ID/shop/field/normalized value khớp question; worker không được tạo question từ arbitrary patch.

**If we skip it:** Chuyển authority từ core sang Data làm mất guard đang có, và preference suy ra trở thành cách nới rào tài chính.

### 3. [P1] Learning input Data không thể làm ToolMessage trực tiếp

**What this is:** `data/growth_data/api.py:190–202` trả metrics, forecasts, shared_proposal, decisions và content jobs cho learning_worker. Role này thuộc PRIVATE (`service.py:32–33`); decisions có `feedback_private`, shared_proposal có private evaluation theo quyền. Core `gateway.freeze_learning_evidence` cần Event/PublicEvidence shape và seq/cutoff (`gateway.py:143–205`).

**Problem:** Nối thẳng input vào T08 vừa lộ private fields vừa không có exact core joins: Data seller_decision chỉ có decision_id/action/edited; applied event thiếu package/card; terminal negotiation event chưa đủ. Học từ latest rows sau settlement có thể thấy version phát sinh sau cutoff, dù event query có `seq <= cursor`.

**Fix:** Một adapter backend dùng Data event seq và quan hệ FK dựng public immutable projection tại settlement cutoff; không cho model SQL/row dictionaries. Dùng mapping evidence đã chốt ở SI review, áp dụng cả baseline History/Preferences/Calibration. Dataset phục vụ compiler có thể riêng tư nội bộ; `LearningEvidence` gửi model chỉ allowlist, leak_guard/free-text redaction của đúng shop và public source. Never infer applied from agreement.

**If we skip it:** Lessons/history có thể kể gói chưa chạy, đếm hỗ trợ từ tương lai hoặc đưa tài chính riêng vào Learning/Platform.

### 4. [P1] RAM receipt không đủ để ghép durable Rules và night

**What this is:** Store chỉ giữ MemoryCommit trong RAM (`app/infrastructure/store.py:15–20,37–70`), gateway giữ KnowledgeCommit ở Session (`gateway.py:242–247,322`), night summary cũng ở Session (`night.py:119–174`). `answer_pref` commit preference trước rồi sửa Rules riêng (`gateway.py:127–135`).

**Problem:** Chỉ thay store bằng SQLite sẽ cho trạng thái preference confirmed nhưng Rules chưa đổi nếu process dừng giữa hai bước. Receipt store không giữ accepted/rejected operations hay summary; retry sau reopen không dựng lại đúng result mà không chạy learning lại.

**Fix:** Dùng repository/receipt đã định nghĩa ở DB/SI review; full typed receipt bền vững, hash conflict và CAS. Data seller confirmation và preference mutation dùng cùng `connect(write=True)` transaction. Publication night và Data handoff hoàn tất cùng transaction, network/model ở ngoài. Không tạo transaction manager hay receipt hệ thứ hai trong gateway.

**If we skip it:** Durable records vẫn không chứng minh durable business behavior; UI báo confirmed/completed nhưng agent hoặc reports đọc trạng thái khác.

## 4. Should fix trong cùng patch tích hợp

### 5. [P2] Static documents tồn tại nhưng agent chưa đọc được

**What this is:** `app/agents/tools.py:120–128` chỉ tìm campaign JSON; `content_context` trả facts có `fact_source_id='seed:shop:<id>'` (`144–156`). Data đã có `knowledge_search` và versioned document read (`data/growth_data/media.py:220–250`, `api.py:177–189`).

**Problem:** Guide/product sources của Data không xuất hiện trong tool results. Sau Data content/policy update, seed source ID không mô tả record thực được đọc. Search type mismatch đã reproduced làm content policy retrieval rỗng nếu adapter dùng metadata đúng.

**Fix:** Dùng existing context tools để trả tối đa5 reference snippets có kiểu, nguồn/version/hash thật, theo role và product đã bind; không cần thêm vector DB hoặc tool tìm kiếm tổng quát. Sửa seed metadata của các guide bằng manifest/mapping rõ ràng từ source metadata; backfill đúng rows v1 đã seed bằng migration hoặc targeted repair, không chỉ sửa INSERT OR IGNORE. Giữ `search_campaign_catalog` riêng vì CampaignRecord không phải document.

**If we skip it:** Catalog hoạt động nhưng phần Knowledge tĩnh Data chỉ nằm trên disk; provenance tool result không thật và filter đúng nghĩa trả thiếu tài liệu.

### 6. [P2] Trace retrieval chưa ghi đủ records đã dùng

**What this is:** `gateway.py:57–78` trả calibration nhưng memory_read chỉ liệt kê History/Lessons; shop/content log thiếu versions của preference records. Data ingest allowlist chỉ nhận memory_read `{who,items,memory_revision}` (`integration.py`, `ingest_event`), không nhận invocation_id/versions của core.

**Problem:** Platform forecast có thể đổi do calibration nhưng audit không chỉ ra calibration record/version. Nối nguyên core log vào Data bị schema reject hoặc phải vứt invocation/version; event đơn lẻ không đối chiếu được ToolMessage lần sau.

**Fix:** Chốt một safe memory_read DTO với role/invocation_id/record_refs/version/knowledge_revision; include calibration identity/version và Rules version khi role cần. Data ingest accepts exact safe shape, existing telemetry callers đổi đồng thời. Không ghi raw private result hoặc value trong opaque IDs; không tạo log seq riêng.

**If we skip it:** Chứng cứ read→model→decision bị thiếu nguồn hoặc mất liên kết, dù DTO vẫn trả đúng số.

## 5. Đầu nối code nhỏ nhất để triển khai

Các chữ ký dưới đây là internal seam được đề xuất cho coder, không tuyên bố đã tồn tại. Nếu composition của agent lane đã có context adapter tương đương thì mở rộng đúng file đó; không dựng thêm lớp pass-through thứ hai.

### A. Reuse Data context và Rules

Thêm vào adapter Data-owned, ví dụ `app/infrastructure/data_context.py`; gateway không import SQL hoặc DataService:

```python
@dataclass(frozen=True)
class RulesState:
    rules: ShopRules
    version: int
    evidence_seqs: tuple[int, ...]

class DataKnowledgeSource:
    # constructor bound existing DataService, run_id and scoped shop;
    # principals are selected server-side, not supplied by model.
    def rules_state(self, shop_id: str) -> RulesState: ...
    def freeze_evidence(self, *, day: int, after_seq: int,
                        through_seq: int, knowledge_revision: int,
                        existing_lessons: list[PublicLesson]) -> LearningEvidence: ...
    def reference_documents(self, *, role: str, shop_id: str,
                            day: int) -> list[ReferenceDocument]: ...
```

`MemoryGateway(..., source=None)` keeps isolated core tests backward compatible; integrated startup always injects source. `get_rules`, `shop_view`, `content_view` use source.rules_state and current shop version. `freeze_learning_evidence(day, *, through_seq=None)` delegates to source for integrated run; Data handoff supplies through_seq, never max(seq) after model telemetry. Gateway supplies its captured knowledge revision and existing lessons; the source does not query knowledge tables itself. Source consumes the same frozen Data snapshot that SI03 uses, not a separate snapshot or parallel cursor.

`app/agents/tools.py.private_context` must use the same Data Rules/version as gateway. `ContentContext` uses Data verified facts and content/job version; listing text or seller feedback is not new verified product evidence. Agent/tool lane owns other context/finance wiring, this lane supplies memory/static references only.

### B. Seller confirmation transaction

Keep `DataService.question` and `DataService.decision` as the commands. Composition injects one Knowledge transaction callback object into DataService (Data package calls the interface, never imports app modules); integrated startup must reject an absent callback, while the standalone reference profile may retain its existing behavior. Add small transaction-aware functions in the integrated Knowledge adapter/repository, not model tools:

```python
def mark_preference_asked_tx(c, *, run_id, shop_id, pref_id,
                            question_id, card_id, day): ...

def record_preference_answer_tx(c, *, run_id, shop_id, pref_id,
                               question_id, decision_id, yes, day): ...
```

- At question creation, verify candidate exists, support threshold, status/silence and exact field/value. `external_pref_id` is the stable durable Preference ID.
- When `make_card` actually emits the question card, mark asked with receipt tied to card. Existing Data operation completion may present it; do not mark asked merely when the worker creates a question row.
- `decision(rule_question)` reads saved question, checks version/current Rules, performs confirm_rule on Yes, then updates preference/metadata/receipt and emits safe confirmation event on the same connection. No keeps Rules/version, sets declined_until=day+14. Do not call gateway.answer_pref on the integrated path and then call Data again.
- `RulesState.evidence_seqs` comes from actual Rules confirmation events joined to decision/question/shop; emit `rules_confirmed` in the authoritative transaction or explicitly derive the matching seller_decision seq. Seed starts with []. Raw event payload should not publish private field/value to Platform.
- Repeated identical command receipt changes neither Rules version nor preference revision; same question with opposite answer conflicts. Crash/fault rolls back question/decision/Rules/preference together.

Standalone `runtime.day.submit_decision → gateway.answer_pref` remains test path until integrated routes use Data. Do not silently use it as fallback after a Data conflict.

### C. Static references without new agent framework

Add a strict DTO in `app/domain/models/tools.py`:

```python
class ReferenceDocument(StrictModel):
    document_id: str
    document_version: int
    source_reference: str
    checksum: str
    is_simulated: bool
    text_vi: str  # bounded excerpt, max 1800 chars
```

Append `references: list[ReferenceDocument] = Field(default_factory=list)` to PublicContext and ContentContext; Shop can use public references through T01. Existing native tool JSON and fixtures change together. No private document goes into PublicContext/ContentContext. Candidate/lesson/rules data stays in its existing memory DTO.

Data adapter uses existing document rows/files and shared access helper extracted from search/document route. Fixed role manifest: Platform gets selling/advertising/fee guides relevant to shop category; Content gets content standard + exact product document. Product ID comes from Data context/job. Use correct seeded types/known IDs; model cannot choose run/shop/path. Pin reference version/hash in invocation context and validate checksum before returning text. Public references enforce ready, nonrevoked, same release, effective day, shared collection and exact product eligibility. Preserve Data's current direct-read expiry and content-worker assignment checks.

A guide containing instructions is reference material, not permission to modify Rules/use other tools. Verified product claims remain the structured facts whitelist; a product guide cannot grant an unverified warranty. Return true stored `is_simulated`, not unconditional True as current search does. Core campaign JSON stays simulated with `seed:campaigns:<id>` and current expiry/stock/category/top5 filter; campaign eligibility never overrides private rules or seller approval.

### D. Durable records and next read

Use `SqliteKnowledgeStore(DataService.store)` implementing existing get/list/metadata/commit semantics plus full receipts from DB/SI contract. Serialize/validate the existing typed learning models; no generic arbitrary JSON exposed to model. Scope and key must agree with record.shop/category/lesson ID. Gateway keeps sorting/limit/projection; store persists all history.

Integrated context loader takes existing `run_id`, `day`, shop and source snapshots. Reopen reloads Rules from Data and knowledge metadata/records/receipts from repository. It never calls seed creation and never uses restored mutable Session fields as source of business truth. Calibration provider is wired to this same repository and returns factor1 for Memory OFF; do not open a second write transaction from Data forecast callback.

SI commit/nightrun path must reuse this gateway/repository; do not ship both baseline run_night and SI worker committing the same day independently. The SI orchestrator is the one night entrypoint after integration, preserving five-bin behavior and adapting `NightSummary` for Data handoff presentation.

## 6. Files/callers and implementation order

| Step | Files/callers | Concrete completion |
| --- | --- | --- |
| K01 — pin authority | Integrated Data context adapter, `app/runtime/session.py`, `app/memory/gateway.py`; agent lane composition | Existing Data run ID; per-shop RulesState; one event sequence; no new business run/store. Update KNOWLEDGE_CONTRACT sections1/4 to supersede Session-Rules authority only for integrated mode. |
| K02 — persistence dependency | `app/infrastructure/store.py`, `sqlite_store.py`, DB migration/tests owned by DB lane | Typed four-bin contract and durable full receipts; shared transaction helper callable from Data. Do not independently author physical schema. |
| K03 — confirmations | `data/growth_data/service.py` question/make_card/decision/confirm_rule; Knowledge transaction adapter; Data/Core tests | Valid candidate binds question; only lower voucher; asked on presented card; answer+Rules+receipt atomic; per-shop version/evidence. |
| K04 — frozen evidence | Data service source events, `api.py` learning input helper, Data adapter, gateway/night; SI03 owner coordinates | Public DTO with exact Data IDs/cutoff; no private raw input; applied history and cross-day update; calibration uses daily prediction. |
| K05 — static context | `data/growth_data/seed.py`, targeted metadata repair/migration, shared document access helper, `models/tools.py`, `agents/tools.py`, context fixtures | Correct guide types/provenance; role-bound references reach ToolMessage; Data verified facts source replaces seed ID on integrated path. |
| K06 — retrieval trace/next-use | `gateway.py`, Data event DTO/ingest allowlist, native integration tests | Safe record/version/invocation trace persisted by Data; real next invocation consumes reopened repository records. |

Shared contract changes are predeclared implementation work: update relevant tool DTO JSON fixtures, contract docs and tests together. No new seller UI pages, vector infrastructure, embedding service, arbitrary document upload tool or independent memory server is needed.

## 7. Acceptance required for KNOWLEDGE INTEGRATION PASS

1. **One authority, reopen:** Create Data run, apply/settle/night, close all objects, reopen same DB, bind next core invocation to same run. Rules, four bins, metadata and receipt survive; stock/day/approval are read from Data. No second UUID/run or JSONL-derived event cursor appears.
2. **Real next-use:** Reuse current fake model pattern over integrated Data-backed ToolMessages. Memory ON approved history changes Platform output; Memory OFF cannot receive it. Change one valid stored lesson/history record in isolated test, keep brief/model behavior fixed, prove next output/input changes for that reason. A memory_read log alone is insufficient.
3. **Seller style:** Data feedback→candidate; before Yes Content default excludes style. Present Data question; seller Yes; next approved Content request after reopen returns confirmed style and generated text/media input uses it. No gets declined silence and unchanged Rules. Preference confirmation is not accepted without a matching saved question/decision.
4. **Voucher authority:** A lowering fixture succeeds once. D8→30 question rejected; stale-version confirmation rejected; rejection/crash changes neither cap nor preference status. Duplicate same answer returns same receipt; opposite answer conflicts. Confirming D does not change A Rules version.
5. **Memory OFF:** Platform has no history/lessons/calibration, shop preferences empty, no preference question/reflection/four-bin write, factor1. Current Data financial Rules and already confirmed style still enforce; static public facts/catalog/guide docs remain readable. OFF never reads ON run namespace.
6. **Projection/privacy:** Malicious/accidental cost/profit/min-profit/ROAS/private feedback/Persona in Data rows never appears in Platform/Content/Learning ToolMessages or public trace. Shop sees only bound shop. Empty/other-run/other-shop/category records are filtered before ranking. Reference document private owner, wrong job product, revoked, future and expired cases are denied; allowed source version/hash matches content.
7. **Cutoff and joins:** Freeze at settlement_cursor, append events/mutate later-day rows, verify identical snapshot/result. Day1 apply and Day2 continuation update the same negotiation history; old context may be included without new support. Seller edited package uses child proposal/applied campaign; agreed-but-not-applied has no approved package/outcome claim. Two metric visibility projections do not double-count.
8. **Durable atomicity:** Invalid store write changes no bin/meta; fault between Rules and preference update rolls back all; fault between night records and handoff completion rolls back all. Reopen retry uses full accepted/rejected summary receipt, no learning/provider second run. Same receipt/different payload conflicts. DB lane runs multi-connection tests.
9. **Retrieval limits:** More than5 History and more than5 Lessons/scope show exact bounded stable order while all history remains stored. Run/category isolation passes on same DB. Calibration record ID/version appears in safe trace when used. No raw value is encoded in preference ID.
10. **Static sources:** Search `content_policy` retrieves the seeded content guide after repair; same source appears in ContentContext ToolMessage. Catalog expired/insufficient-stock/other-category cases remain absent. Future document version is not substituted for requested valid version. Financial or product claims in document prose never override code/verified facts.

Run focused existing32 tests first, add Data-backed integration cases above, then relevant full root/Data suites once after wiring. Report core/fake, durable local and provider live gates separately. Paid-provider smoke belongs to the provider/runtime lane and is unnecessary for deterministic Knowledge acceptance.

Verdict: fix 1–4 before integrated use; complete 5–6 and the next-use gates before calling Knowledge finished.

Not checked: live OpenAI behavior, media rendering, full UI, SI compiler correctness and physical migration implementation. These have separate reviewers; this report does not claim their gates passed.
