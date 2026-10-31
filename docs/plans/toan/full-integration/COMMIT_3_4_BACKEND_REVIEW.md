# Review backend → frontend cho commit [3.4]

What this change does: Commit `bd78f8e` thêm trình chiếu ngày 7, thu gọn luồng agent và ghi yêu cầu dữ liệu backend. Review này đối chiếu yêu cầu đó với code đang chạy tại `65434cb4e3cbd1de2e90b25c4876d0276ce78ad6`, gồm hai commit tích hợp sau đó; không báo lại lỗi cũ đã sửa.

Phạm vi: một app local, một native worker, seller D. Đọc `AGENTS.md`, `DEMO_CONTRACT.md`, plan tích hợp, hai frontend requirements và diff [3.4]. Không sửa source, không push, không gọi provider, không ghi database production. Mọi lệnh ghi dùng SQLite tạm hoặc bản sao tạm của SQLite đối chứng; source được mở `mode=ro`.

## Must fix

1. **[P1] Check cuối bị mất `ok`, giao diện báo vi phạm cho gói đã qua kiểm tra.**

   - **Đây là gì:** `app/negotiation/graph.py:86` phát `code_check` với `ok` và `codes` sau khi kiểm gói cuối. `DataEventLog.add()` tại `app/infrastructure/data_agents.py:67` bỏ cả hai field vì không nằm trong allowlist, nhưng vẫn lưu event cùng type.
   - **Lỗi:** `frontend/src/activity.js:28` chọn check mới nhất. `AgentActivity.jsx:32` nhận `checkMatchesLatest=true`, `check.data.ok=undefined` nên hiện **“Có ràng buộc chưa đạt”**, mặc dù `pending_card` hợp lệ và check trước đó có `ok=true`. Bước kiểm tra ở dòng 39 cũng không được đánh dấu hoàn thành.
   - **Tái hiện:** Chạy native worker hiện tại với `NativeTransport` của test, database tạm; confirm brief → start → chờ `awaiting_decision` → lấy hết `/api/events`. Run mới `run_72572a3f959c4596953c` có final check seq 46, `data={negotiation_id:"neg_b4b20b0408d045499d5c"}`. Gọi trực tiếp `deriveActivity(state,events)` trả nhãn vi phạm nêu trên. Cặp mô phỏng đã lưu cũng tái hiện ở ON ngày 1/4/7, seq 64/400/732. Đây là lỗi hiện hành, không chỉ dữ liệu lịch sử.
   - **Sửa nhỏ nhất:** Backend chỉ phát check có schema hoàn chỉnh: giữ boolean `ok`, chuyển `codes` thành `checks:[{ok,message_vi}]`, bind proposal/round đúng lượt. Hoặc loại event trùng không mang kết quả nếu check canonical của Data đã đủ. Không cho frontend tự kết luận “pass” từ việc có card. Test qua native worker → HTTP JSON → `deriveActivity`, không tự dựng event đúng schema trong test frontend.
   - **Nếu bỏ qua:** Màn chính tự mâu thuẫn: thẻ “Đã kiểm tra luật” nhưng sơ đồ nói gói chưa đạt; giám khảo không phân biệt được validator thật với lỗi trình bày.

2. **[P1] “Phiên hiện tại” có thể dùng báo cáo cũ nhưng tải nhật ký của run mới.**

   - **Đây là gì:** `data/growth_data/api.py:392–396` lấy comparison mới nhất theo `session_id`, không yêu cầu active run thuộc cặp đó. `frontend/src/pages/Proof.jsx:44` gọi nguồn này là **“Phiên hiện tại”**; `exportEvents()` dòng 39 lại đọc state hiện tại rồi tải events của active run.
   - **Lỗi / tái hiện:** Trên bản sao tạm của DB có cặp thật `run_a716ec6e871f46d289f1` / `run_74814d1d029c40deb24b`, POST reset tạo `run_53a19381073f48d6b32c`, day 1, idle, brief null. GET `/api/proof` vẫn trả HTTP 200 và cặp cũ; active run không thuộc cặp. Như vậy “Báo cáo” và “Nhật ký” cùng màn mô tả các run khác nhau. Ngay cả khi active run nằm trong cặp, nút nhật ký hiện chỉ tải một nhánh, không đủ kiểm chứng cả hai hội thoại.
   - **Sửa nhỏ nhất:** Với nhãn hiện tại, lookup mặc định chỉ chọn comparison chứa active run và trả `PROOF_NOT_READY` khi chưa có. Xuất evidence phải bind `report.run_on/run_off` hoặc comparison ID đã chọn, do backend cấp projection đúng quyền; không chọn lại active run vào lúc download. Nếu muốn xem cặp cũ, cần nguồn được đặt tên/chọn rõ ràng. Nhánh `/api/proof/demo` đã có envelope evidence đúng cặp và không gặp lỗi này.
   - **Nếu bỏ qua:** Người dùng có thể đưa báo cáo cũ làm bằng chứng của lần chạy mới; file nhật ký không chứng minh số liệu/hội thoại đang hiển thị.

## Should fix

3. **[P2] Tổng kết bộ nhớ hiển thị mã nội bộ thay vì điều đã học.**

   - **Đây là gì:** `app/memory/night.py:301–302` điền `history_updates` bằng `negotiation_id`, `pref_candidates` bằng `pref_id`. Facade trả nguyên `night_summary` tại `data/growth_data/facade.py:90`; `frontend/src/pages/Night.jsx:22–23` render trực tiếp các chuỗi dưới tiêu đề “Lịch sử công khai” và “Sở thích người bán”.
   - **Lỗi / tái hiện:** ON ngày 1 có `history_updates=["neg_7153b41dee4b4c9fa9db"]`, `pref_candidates=["d02182f005703592"]`; ngày 7 có `history_updates=["neg_801aa9a5d30c4e4a8495"]`. Đây là payload native persisted và HTTP thật. File tải tóm tắt dòng 15 cũng giữ các ID này. Preview có câu tiếng Việt nên không bộc lộ lỗi.
   - **Sửa nhỏ nhất:** Giữ ID trong record/provenance; backend dựng chuỗi mô tả tiếng Việt từ history/preference đã commit cho seller projection, hoặc thêm projection `{id,text_vi}` được chốt đồng thời với caller. Không để React suy ra sở thích từ hash và không thay bằng câu mẫu. Kiểm một night native có preference thật, không chỉ summary tự dựng.
   - **Nếu bỏ qua:** Màn “Hệ thống học được gì hôm nay?” không trả lời được câu hỏi đó dù dữ liệu học có trong DB.

4. **[P2] Câu hỏi tập trung của trọng tài bị mất trước khi xuống frontend.**

   - **Đây là gì:** `app/negotiation/graph.py:63–65` đã lọc an toàn `focused_question`; dòng 66 chỉ emit action/evidence/source. Allowlist `app/infrastructure/data_agents.py:67` cũng không giữ `focused_question`, `unresolved_terms`, `next_actor`. Yêu cầu frontend mục 5 và `AgentActivity.jsx:51` / `EventFeed.jsx:17` có phần hiển thị câu hỏi này.
   - **Lỗi:** Khi model trả `refocus` hoặc `ask_human` kèm câu hỏi khác `reason_vi`, workflow dùng câu hỏi để điều phối nhưng HTTP/log mất hẳn câu hỏi. Payload native thực kiểm được chỉ có action/evidence/negotiation/source; regression frontend hiện tự tạo `focused_question`, nên không kiểm được đầu nối này.
   - **Sửa nhỏ nhất:** Graph emit các field công khai đã lọc; Data adapter giữ chúng, map `next_actor` từ role graph sang enum `platform_agent|shop_agent|seller|null`, thêm round đúng lượt. Dùng fake referee trả câu hỏi cụ thể rồi kiểm câu đó đi qua HTTP đến UI. Không mở thêm quyền hay bỏ leak guard.
   - **Nếu bỏ qua:** UI chỉ biết “Cần tập trung lại / Cần hỏi người bán” mà không biết cần làm rõ điều gì.

## Mapping đã đối chiếu

| Nguồn backend → frontend | Kết quả hiện tại |
| --- | --- |
| `Facade.state` → `useRun`, Shop/Demo | Có `run_id`, `demo_shop`, `demo_shop_original`, horizon, brief, busy/operation. Fresh native run bắt đầu day 1/idle/brief null; start cần xác nhận brief. |
| `ready/awaiting_seller/content_review/complete` + operation → `step` | Native queued/running start được chiếu thành `negotiating`; day 7 complete giữ day 7. Cặp thật có đủ 7 settlements/handoffs. Không thấy sinh ngày 8. |
| Card → Proposal/decision | Đúng `version`, `brief_version`, `proposal_id/version`, `negotiation_id`; quyết định gửi expected card/brief. D voucher 3% nhận contribution `27136`; forecast là cả gói. |
| Draft → ContentReview/retry/apply | `version` là attempt, tách job/content versions; UI gửi card/brief/attempt/job/content binding, skip/ack. Tests native chặn stale card, asset mất, duplicate apply và payload khác cùng key. Không coi job xong là seller đã publish. |
| Events → `useRun`/`activity` | Actor mapping telemetry → `agent_activity` đúng, seq/run scoping và drain `has_more` khớp. Probe HTTP thật lấy 245 event seller, cursor cuối 983; gap do lọc quyền là hợp lệ. Lỗi check cuối ở finding 1. |
| `market_result.data.metrics` → Night | Tên `orders`, `roas`, `ads_spend`, `profit_after_fees` khớp. UI không tính lại lãi/forecast; nhãn “Dự báo cả gói” khác “Đơn hàng hôm nay”, null không thay bằng số fixture. Summary text còn finding 3. |
| `evidence.proof` → Proof | `better` dùng `higher/lower`, `on/off` là số hoặc null, đơn vị `%/đ` khớp. Năm metric từ records; MAE/MAPE không bị tính lại ở React. |
| `comparison_days` → `proofComparison` | Run IDs, request/version/refs, message `id/actor/text_vi/event_seq`, memory `run_id/source_day/event_seq/text_vi/record_id/version` khớp. Cặp thật chỉ có hội thoại ngày 1/4/7; React nhận đúng ba ngày, không bù chat ngày 2/3/5/6. Ngày 1 không learned evidence, nhánh OFF rỗng; record refs có provenance, skill versions ở manifest. |
| `/api/proof/demo` → `readDemoArtifact` | Artifact `demo-proof.v1`, `precomputed_offline_simulation`, `provider_eval=not_run`, manifest/hash/evidence; export được server kiểm cutoff/ownership. Hai download dùng đúng envelope đã chọn. Không làm active run thành ngày 7. |
| Preview day 7 → SQLite mẫu | `frontend/fixtures/day7.json` → `runs/preview/samples.sqlite3` là snapshot biên soạn sẵn có nhãn `sqlite_sample`; chỉ nút preview đọc nó. Không phải kết quả cặp run thật, không chứng minh yêu cầu “hai dataset records đổi UI không build lại” đã hoàn tất. Các mục 9/13 requirements vẫn là acceptance tích hợp rộng hơn. |

## Kiểm chứng

- `LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q tests/integration/api/test_data_native.py tests/integration/api/test_demo_proof.py`: **12 passed, 43.56s**. Các test này pass nhưng không bắt được final event bị mất `ok` hay cặp proof cũ sau reset.
- TestClient trên snapshot SQLite tạm chứng minh report/current-run mismatch; nguồn gốc DB `runs/sim-D-8984ae2c0383489faa90fa171f0090f5/growth.db` chỉ mở read-only để backup.
- Một native lifecycle mới dùng `NativeTransport` fake trong temp DB chứng minh finding 1 ở HEAD hiện tại. JSON HTTP → module `deriveActivity` thật: `checkMatchesLatest=true`, nhãn **“Có ràng buộc chưa đạt”**.
- Module `comparisonDays` thật nhận report persisted: kết quả `[1,4,7]`. Không dùng `previewComparison.js` để xác nhận dữ liệu thật.
- File probe tạm: `/tmp/commit34-fresh-native.json`, `/tmp/commit34-backend-state-events.json`; không phải artifact được commit hay dữ liệu authoritative.

Verdict: sửa 1 và 2 trước khi tuyên bố frontend đã map đúng backend. Sửa 3 và 4 để màn tổng kết/trọng tài đáp ứng payload đã hứa.

Not checked: không gọi live OpenAI/Muse, không tương tác ghi với app production 8000, không kiểm layout browser trong lane backend; lane UI review độc lập. Không thay source hoặc commit/push.
