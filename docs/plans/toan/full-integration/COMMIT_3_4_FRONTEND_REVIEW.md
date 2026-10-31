What this change does: Commit `bd78f8e` thêm lối trình chiếu “Nhảy tới ngày 7”, nạp một fixture công khai qua SQLite riêng và mở hai hội thoại so sánh ở ngày 7. Commit này không triển khai simulator/backend 7 ngày: hội thoại, bộ nhớ và chỉ số trong nguồn preview vẫn là minh họa được biên soạn sẵn, có nhãn. HEAD `65434cb` đã bổ sung luồng API/Data thật qua `075ee58`; phần dưới phân biệt hai thời điểm này.

Review ngày 31/10/2026, phạm vi `bd78f8e^..bd78f8e` và đường gọi hiện tại tại `65434cb`. Đã đọc AGENTS, DEMO_CONTRACT, hai frontend requirements và plan full-integration. Giả định tải demo local: một seller/browser, một native worker. Chỉ review và ghi báo cáo; không sửa source, commit, push hoặc start/advance run LIVE.

**Kết luận hiện tại**

Không phát hiện P0/P1 trong phạm vi đã kiểm. Đường sản phẩm mặc định đọc backend; không thấy UI thay số liệu hay transcript backend bằng fixture khi API lỗi. Sự kiện thật đã map đúng vào vòng thương lượng, hai gói trước/sau, kiểm tra và xác nhận sở thích ngày 2. Có bốn lỗi P2 cần sửa để nguồn dữ liệu, recovery và màn bộ nhớ phản ánh đúng backend.

**Cần sửa**

1. **[P2] Nhãn “Dữ liệu LLM / Trực tiếp” vẫn xuất hiện khi kết quả thực là fallback offline** (`frontend/src/pages/Shop.jsx:11`, `frontend/src/components/EventFeed.jsx:7–16`, `frontend/src/format.js:14`).
   - **Đây là gì:** Bảng điều khiển ghi nguồn LLM bằng `modeLabel(state.mode)`. `Facade.state()` trả `mode` từ cấu hình của run (`data/growth_data/facade.py:81`), trong khi nguồn thực từng invocation nằm trong `event.data.source`.
   - **Lỗi và tái hiện:** Run cấu hình `live`, provider lỗi hoặc hết budget: `app/agents/runner.py:132–136,153` tạo `agent_completed` với `source:'offline'` và lý do fallback. Render với payload này vẫn hiện “Dữ liệu LLM / Trực tiếp”; `EventItem` không render source hoặc error_code, nên người xem không biết kết quả vừa thấy là offline. Test render riêng xác nhận `configuredLiveShownAsData=true`, `actualOfflineSourceShown=false`, `providerFailureShown=false`. Không cần gọi provider để tái hiện.
   - **Sửa nhỏ nhất:** Đổi nhãn của `state.mode` thành chế độ cấu hình/yêu cầu. Hiện nguồn thực và lý do fallback đã được backend cấp trên sự kiện kết thúc agent; không tự suy nguồn bằng mode. Màn Night cũng cần dùng nguồn thực thay vì luôn khẳng định “LLM đề xuất” (`Night.jsx:25`).
   - **Nếu bỏ qua:** Bản demo có thể trình bày kết quả luật offline như kết quả trực tiếp từ model, trái DEMO_CONTRACT mục 2. Đây là lỗi còn ở HEAD, không phải claim rằng UI đang gọi fixture trong API mode.

2. **[P2] Nút thử lại bước học không bao giờ xuất hiện với StateView thật** (`frontend/src/pages/Demo.jsx:23`, `data/growth_data/facade.py:84`).
   - **Đây là gì:** Khi night thất bại, UI có nhánh “Thử lại bước học” và “Bỏ qua bước học”. Retry được gate bằng `state.learning_retry_allowed`.
   - **Lỗi và tái hiện:** Facade chỉ trả `learning_status/error/version/day`, không trả `learning_retry_allowed`. Với `learning_status:'failed'`, version hợp lệ và reflection không ở trạng thái `reserved/unknown`, backend cho retry (`data/growth_data/integration.py:176–191`), nhưng render UI chỉ có Skip. Test render xác nhận `retryVisible=false`, `skipVisible=true` với đúng tập field facade cấp.
   - **Sửa nhỏ nhất:** Backend project boolean `learning_retry_allowed` từ cùng kiểm tra an toàn đang dùng trong `learning_control`; frontend tiếp tục đọc field đó. Thêm một regression ở ranh giới facade → Demo cho failed/retryable và failed/unknown. Không mở retry vô điều kiện tại UI.
   - **Nếu bỏ qua:** Seller phải bỏ qua bài học hoặc dùng API thủ công ngay cả khi lỗi có thể thử lại an toàn. Không có deadlock toàn phiên vì Skip vẫn dùng được.

3. **[P2] Màn Night hiện ID thay vì nội dung lịch sử và sở thích đã học** (`frontend/src/pages/Night.jsx:15,22–23`, `app/memory/night.py:301–302`).
   - **Đây là gì:** Hai ô “Lịch sử công khai” và “Sở thích người bán”, cùng bản tải tóm tắt, render trực tiếp chuỗi trong `last_night.history_updates` và `pref_candidates`.
   - **Lỗi và tái hiện thực:** GET read-only từ run offline có sẵn `run_a915b6acd0714938a50a` trả summary ngày 1 với `history_updates:['neg_384a3d9ae1184a21bc2b']`, `pref_candidates:['17ee6dcae6035295']`. UI vì vậy hiện hai định danh này thay cho “đã ghi nhận gói nào” và “ảnh nền sáng”; preview dùng câu hoàn chỉnh nên che mất sai khác này trong kiểm tra bằng fixture.
   - **Sửa nhỏ nhất:** Bổ sung seller projection ở backend: resolve ID thành tóm tắt đã lọc quyền và giữ ID/evidence ở metadata riêng. Cập nhật UI/contract tương ứng hoặc giữ các list hiển thị là text và bổ sung refs riêng. Không để React tự biên soạn nội dung hoặc đọc private Knowledge rows.
   - **Nếu bỏ qua:** Người xem không hiểu hệ thống đã học gì dù dữ liệu Knowledge đã được lưu. Đây là lỗi nối payload vào giao diện, không phải mất dữ liệu DB.

4. **[P2] Nút “Báo cáo mô phỏng đã chạy” luôn lỗi trong nguồn preview** (`frontend/src/pages/Proof.jsx:38,44`, `frontend/src/preview.js:173–175`).
   - **Đây là gì:** Màn Proof mới có nút chọn `/api/proof/demo`, kể cả khi client đang là preview browser-only.
   - **Lỗi và tái hiện:** Mở `proof.html?preview=1`, bấm “Báo cáo mô phỏng đã chạy”. `createClient` chuyển mọi request vào `createPreviewAPI`, vốn không có route `/api/proof/demo`; kết quả luôn là “Chưa có dữ liệu xem trước cho thao tác này.” Gọi đúng client hiện tại đã xác nhận lỗi này. Backend artifact không được truy cập và không có fallback, nên đây là lỗi điều khiển không khả dụng, không phải trộn nguồn.
   - **Sửa nhỏ nhất:** Ẩn/vô hiệu nút artifact khi `client.preview`, hoặc cung cấp một liên kết chuyển nguồn tường minh sang product API. Không bổ sung một bản proof giả vào preview để làm nút có vẻ chạy.
   - **Nếu bỏ qua:** Người dùng đi từ trình chiếu ngày 7 sang báo cáo đã chạy gặp lỗi cố định dù UI quảng bá lựa chọn đó. Lỗi do tích hợp sau 3.4 thêm nút, không phải lỗi nguyên thủy của `bd78f8e`.

**Mục đích đúng của commit 3.4 và phần lịch sử đã được sửa**

| Hành vi | `bd78f8e` | HEAD `65434cb` |
| --- | --- | --- |
| Entry sản phẩm | HTTP mặc định API; query `preview=1/0` tường minh. | Giữ đúng. `index.html`/`/` là trang shop; không bắt đầu ở `demo.html`. |
| Nút ngày 7 | Chỉ ở preview; GET `/api/demo/day7` của preview server → cập nhật session preview → `proof.html?day=7&preview=1`. | Giữ đúng; API mode không có nút và không gửi command nhảy ngày thật. |
| Nguồn mẫu | `frontend/fixtures/day7.json` → SQLite `sample_versions/active_samples`; nội dung biên soạn sẵn. | Vẫn là preview riêng. Không được gọi việc đọc blob mẫu là backend đã mô phỏng/học 7 ngày. |
| Transcript thiếu | `comparisonDays` trả rỗng khi report cũ không có transcript; không sinh chat thay thế. | Giữ đúng; report Data đã có projection transcript từ events. |
| Nhãn report thật/offline | 3.4 chủ yếu phân biệt bằng `client.preview`, chưa đủ cho report reference trả qua API. | `ProofReport` phân biệt fixture/reference và `precomputed_offline_simulation`; artifact hiện “Chưa đánh giá provider”. Không báo lại đây là lỗi chưa sửa. |
| Brief và mutation binding | Chưa có phần tích hợp đầy đủ với brief/card/draft của Data hiện hành. | UI xác nhận brief thật; decision/content gửi expected versions và exact job/content; night gửi expected_day. |
| Câu trả lời No | Trước integration dùng accept/false cho question. | `Proposal.jsx` hiện gửi reject/false, khớp server. |
| 202 start + busy | Logic cũ chưa có handoff operation hiện tại. | Chấp nhận start mở Demo khi operation còn chạy, poll state/events, busy từ backend giữ controls; browser regression PASS. |

**Bảng nguồn → API/projection → UI thực tế**

| Nguồn authoritative | API / field | Component và cách dùng | Kết quả review |
| --- | --- | --- | --- |
| Data runs, seller brief, operation | `/api/state`: run/day/step/brief/busy/active_operation | `useRun` → Shop/Demo/Shell; UI không tạo business state. | Đúng; riêng retry capability bị thiếu ở finding 2. |
| Data public listing gốc/current, asset registry | `/api/state.demo_shop`, `.demo_shop_original`; asset download URL | `Product`, Shop bản cũ/bản mới, `changedFields` chỉ so sánh field. | Không seed cứng sản phẩm cho API mode; không tính lại giá/lợi nhuận. |
| Proposal/forecast/financial validation/card | `/api/state.pending_card` | `Proposal`: budget, voucher, ROAS, forecast, profit, reasons; POST decision gửi card/brief version. | Đọc số backend. Sample thật có profit 27.136đ và stop 6,5; UI không tính hai số này. |
| Native graph → Data event projection | `/api/events`: `platform_turn/shop_turn` + negotiation_id/round/action/package | `deriveActivity` tách run/day/shop/attempt; `PackageComparison` lấy gói đầu và gói mới nhất; `EventItem` hiện từng lượt. | Kiểm bằng sự kiện HTTP thật: round 2, 70.000đ/10% → 45.000đ/3%; đúng. |
| Validator/referee + native telemetry | `code_check.ok/checks`, `referee_review.action`, `agent_activity.task_id/status/phase` | AgentActivity chỉ hiện running khi có telemetry; check chỉ có hiệu lực khi khớp gói mới nhất. | Smoke thật checkMatchesLatest=true, referee được map; không biến accepted turn thành seller approval. Source thật bị bỏ khỏi hiển thị: finding 1. |
| Seller decision/question | `seller_decision.action/card_id`, `card_sent.card.kind` | Demo lịch sử quyết định; `journeyProgress` bỏ các bước không diễn ra với question/reject. | Ngày 2 thực: question được chấp nhận, outcome approved; skip các bước 0,1,3,4, không dựng thương lượng giả. |
| Data content job/attempt/assets + worker | `/api/state.content_draft` + card/brief/job/content IDs | `ContentReview`: ảnh ready, video ack/skip; Retry/Apply bind draft vừa xem. | Không publish từ status “đã duyệt gói”; đợi content apply; source ảnh/video có hiển thị. |
| Settlement + Knowledge publication | `market_result.data.metrics`, `last_night` | Night dùng metrics ngày summary, số thiếu hiện “—”; history/preference đọc summary. | Metrics không thay bằng preview. Text history/preference không đủ cho UX: finding 3. |
| Comparison group, immutable events, prior-day Knowledge refs | `/api/proof`: metrics/comparison_days/run_on/run_off | `ProofReport`, `comparisonDays`, `LearningComparison`. | Kiểm đúng run, day trong horizon, off memory rỗng, on source_day < day, positive seq, actor/message IDs. Không bịa transcript khi thiếu. |
| Artifact offline đã xuất, có manifest/hash/evidence hai nhánh | `/api/proof/demo` | `readDemoArtifact` → ProofReport; tải report và evidence của artifact. | Nguồn chọn tường minh; không đổi active run. Browser test đã kiểm cả hai download không lấy nhầm log phiên hiện tại. |
| Fixture preview công khai | `/api/demo/day7` của preview server | `loadDay7Sample` → `createPreviewAPI` → sessionStorage → Proof ngày 7. | Đúng là lối trình chiếu riêng; không phải business authority. |

**Entry, storage, polling và proof validation đã kiểm**

- `main.jsx:4–5` dùng sessionStorage, không localStorage. `growth-agents.source` chỉ nhớ lựa chọn nguồn trong tab; `?preview=0` luôn override lựa chọn preview đã lưu, `pageURL` giữ nguồn khi điều hướng. Tab đã chọn preview và mở lại URL trống query vẫn là preview, có banner rõ; tab HTTP mới mặc định API.
- Business snapshot ở API mode nằm trong React memory và được đọc lại từ server. Preview dùng key `growth-agents.react-preview.v3`; jump lưu backup `.before-day7` rồi thay preview sau khi endpoint hợp lệ. Lỗi fetch/không đủ night summaries giữ phiên cũ. Không có tự chuyển preview khi API lỗi.
- Không dùng SSE/EventSource. Poll 1,5 giây, state content-review khoảng 3 giây đúng requirements. `readEvents` drain đến `has_more=false`, kể cả trang bị lọc rỗng, bind run, giữ last_seq của server và chặn cursor không tiến. Poll tiếp tục trong POST; request mutation có Idempotency-Key và X-Request-ID.
- `comparisonDays` không tra DB hay xác minh sự kiện tồn tại; đó là trách nhiệm backend. Các kiểm tra shape/run/day/source phía UI là phòng lỗi hiển thị, không thay authorization và không chứng minh hiệu quả học. Backend hiện tạo các row từ hai run có brief tương ứng và events đã lưu (`data/growth_data/evidence.py:77–127`).
- `day7Sample` kiểm schema/source/day/complete/horizon và đủ bảy night_summary trước khi thay session preview. Không vì có SQLite hoặc đủ bảy dòng mà suy ra transcript/chỉ số mẫu là thí nghiệm thật.

**Kiểm chứng đã chạy**

- Unit/component/frontend suite: **48 passed, 0 failed**. Dùng Node bundled tại `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node` vì PATH shell không có node/npm; lệnh tương đương `node build.mjs --tests && node --test tests/*.test.mjs .test-build/*.test.mjs`.
- `frontend/tests/start-operation.browser.mjs`: **PASS**, Chromium headless riêng với fake API. Start 202 mở Demo khi đang chạy, tiếp tục nhận event, hiện failure; start bị từ chối giữ Shop.
- `frontend/tests/proof-source.browser.mjs`: **PASS**, headless riêng. Chọn artifact tường minh, nhãn offline, đúng hai download, thiếu artifact không fallback.
- Read-only GET từ smoke session offline đã có, không in cookie và không gọi mutation. Feed thật có platform/shop/code/referee/agent_activity cùng identity cần cho frontend. `deriveActivity` được chạy trực tiếp với payload này để kiểm mapping.
- Render SSR riêng xác nhận findings 1–2 và gọi preview client xác nhận finding 4; finding 3 lấy từ payload HTTP thật và đường render trực tiếp.

Verdict: sửa 1–4 trước khi tuyên bố frontend đã map hoàn chỉnh mọi nguồn và recovery của backend. Luồng sản phẩm cơ bản và lối preview ngày 7 đã tách đúng; không cần viết lại frontend hoặc chuyển business logic vào React.

Not checked: không chạy provider LIVE/trả phí, không start/advance/reset run thật; không đánh giá chất lượng ảnh/video live hoặc độ tăng trưởng của cặp ON/OFF. Browser checks dùng fake server riêng; payload smoke hiện tại chỉ bao phủ ngày 1→2, không đại diện việc đã chạy đủ 7 ngày live.
