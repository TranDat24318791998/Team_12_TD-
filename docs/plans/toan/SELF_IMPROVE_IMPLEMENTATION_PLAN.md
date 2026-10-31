# Kế hoạch self improve đã chốt

Ngày 31/10/2026. Đã đóng gói đủ SI01–SI07 để coding agent thực hiện một lần liên tục tại [README giao việc](self-improve/README.md). DB do member khác cung cấp; trọng tâm bàn giao là schema, hành vi repository và phần improve. Lượt này chỉ tạo tài liệu/schema, chưa implement ứng dụng.

## 1. Căn cứ và phạm vi

Repo đã có native tool loop 5 roles, negotiation/Referee, seller runtime, Knowledge gateway/store RAM, derive history/preferences/calibration và Learning native. Mở rộng các module đang có; giữ regression mới của agent khác. Các source đã được đối chiếu tới HEAD `9134121`; coding agent phải đọc lại HEAD/diff đang chạy trước khi chỉnh file chung.

Bản attachment là phần tóm tắt; chưa có file AGENT_KNOWLEDGE_IMPLEMENTATION_SPEC.md gốc với 50 case để xác nhận đủ 50. Ma trận dưới đây và acceptance trong từng task là scope cụ thể của gói này, không được báo thay cho kiểm 50 case gốc.

Nguồn hiện hành: [plan Toàn](README.md), [agent/tools](AGENT_TOOL_KNOWLEDGE.md), [Knowledge](KNOWLEDGE_CONTRACT.md), [runtime](../../DEMO_CONTRACT.md), [Data/API integration](TEAM_INTEGRATION.md). Gói self-improve bổ sung các contracts này; shared caller docs được cập nhật khi implement SI07.

## 2. Quyết định cuối

| Vấn đề | Chốt cho đợt này |
| --- | --- |
| Roles và transport | Giữ 5 roles gồm Referee, native read/calculation tools và terminal output schema |
| Budget/reflection | Cap 64 chung/run; một Learning invocation/night, tối đa 3 provider requests; không thêm reflector |
| Scope/horizon | Một shop/run; runtime horizon cấu hình 1..7, proof mặc định 7 ngày/D |
| Skill | Bốn base assets; evolve learned_steps của offer/renew bằng ba actions/năm cặp được phép |
| Business authority | Rules/seller approval/active package do runtime giữ; học không apply hoặc tăng chi |
| Evidence | Public, exact run/shop/category/cutoff; approved/applied khác agreed; fact IDs deterministic |
| Activation | Artifact immutable, version đêm d hiệu lực d+1; attempt pin từ đầu |
| Memory OFF | Không learned inputs/seed/writes; vẫn giữ initial Rules/validators/stop mechanisms |
| Publication | Atomic records + skill versions + metadata + receipt; snapshot/phase/budget có idempotency |
| DB | Member cung cấp engine/adapter; schema/ports/RAM/contract tests do improve; chưa có factory vẫn code full core |
| UI/API/media | Giữ workflow hiện có; không thêm edit UI/facade/provider trong gói improve |
| Proof | Data engine và runtime headless; metrics từ settlement; không ép ON thắng OFF |

Cap 64 và native invocation tối đa 3 requests giữ tương thích repo, thay đề xuất cap 40/một request trong bản paste. Không triển khai lại graph bằng một structured call. Approved-history seeding đã có trong fallback; chuyển nó vào compiler không tự là bằng chứng cải thiện mới.

## 3. Schema và flow triển khai

Schema machine-readable: [self-improve.v1](../../../contracts/self_improve/v1.schema.json), [examples](../../../contracts/self_improve/examples.json), [kết quả validation](../../../contracts/self_improve/validation.json). Member DB đọc [DB_HANDOFF](self-improve/DB_HANDOFF.md): tám loại record logic, exact unique keys, payload types, null, transaction, retry và adapter injection. Không yêu cầu chọn DB ở phía improve.

Luồng đã chốt:

```text
settlement + daily prediction trước actual
  → freeze public snapshot/facts
  → reserve một Learning invocation + từng live budget slot
  → typed proposal (tối đa 3 ops/proposals)
  → privacy/provenance/version/fresh-evidence checks
  → stage lessons/policies → compile → round-trip + deterministic checks
  → atomic knowledge/versions/cursor/revision/receipt
  → d+1 pin artifact + public seed vào attempt
  → native tools hoặc fallback → validators → seller approval
```

Candidate fail rollback toàn bộ lesson/policy portion, derived history/preferences/calibration hợp lệ vẫn commit. Reflection terminal được lưu trước transaction; CAS retry tối đa một rebase/call, không gọi LLM lại. Unknown provider result không resend. Recovery Knowledge chỉ được nhận durable khi adapter DB đã qua reopen; không nhận đó là phục hồi business Session.

Thứ tự chi tiết và Output từng bước tại [SI01](self-improve/01-schema.md), [SI02](self-improve/02-compiler.md), [SI03](self-improve/03-evidence.md), [SI04](self-improve/04-publication.md), [SI05](self-improve/05-learning.md), [SI06](self-improve/06-runtime.md), [SI07](self-improve/07-integration.md). Agent làm liên tục; không còn bước chờ integrator chọn schema/transaction/runtime semantics.

## 4. Ma trận nghiệm thu xuyên suốt

| ID | Tình huống | Kết quả bắt buộc |
| --- | --- | --- |
| T01 | Platform/reflector nhận context có sentinel private ở nguồn | Sentinel không xuất hiện trong prompt, tool result công khai hoặc artifact |
| T02 | Evidence thuộc run/shop khác hoặc seq sau cutoff | Reject patch; không nới scope bằng arguments model |
| T03 | Có negotiation ID thật nhưng không có seller approval | Không đủ để kích hoạt policy seed approved package |
| T04 | Voucher được sửa nhưng seller không duyệt | Không học thành voucher seed và không đổi Rules |
| T05 | A sửa voucher 10% xuống 5% rồi duyệt | Ngày sau seed voucher 5%; rule cap chỉ đổi sau confirmation riêng |
| T06 | Có package cũ kèm ads và evidence auto-pause trước renew | Seed cuối ads=0; bước copy package không bật ads trở lại |
| T07 | Model đưa action chứa tiền tùy ý, target Shop skill hoặc sửa base | Reject; base hash giữ nguyên |
| T08 | ADD/UPVOTE/DOWNVOTE/EDIT và evidence dùng lại | Theo score/version contract; evidence cũ không cộng điểm lần hai; policy biến mất khi lesson bị xóa |
| T09 | Quá 30 lessons trong scope | Eviction tất định; bundle không còn policy của lesson đã bị loại |
| T10 | Forecast gói ba ngày là 45, raw ngày là 15, actual ngày là 10 | Ratio bằng 2/3; không dùng 10/45 hoặc issued forecast đã hiệu chỉnh |
| T11 | Có dưới 5 mẫu rồi đủ 5 mẫu và vượt 30 mẫu | Factor=1 trước ngưỡng; sau ngưỡng median đúng cửa sổ 30, sample IDs không trùng |
| T12 | Gói từ ngày 1 vẫn chạy ngày 2, không negotiation mới | Update đúng history cũ; event ngày 1 không thành support mới lần hai |
| T13 | Memory OFF nhưng có data learned trong store/transcript/cache | Không lọt vào input/seed; không ghi learned records; Rules vẫn enforce |
| T14 | Night d commit version mới trong lúc attempt còn chạy | Attempt dùng bundle cũ; chỉ attempt đủ ngày hiệu lực mới lấy bản mới |
| T15 | Retry hoặc hai worker chạy night đồng thời | Một settlement, một reflection reservation, không nhân đôi inventory/sample/vote/budget |
| T16 | Timeout reflection, restart sau reservation hoặc mất response | Không gửi lại phase đó; trạng thái unknown/skipped rõ; phần deterministic không bị giả thành live reflection |
| T17 | Artifact lỗi khi load lại hoặc deterministic eval fail | Giữ active skill cũ, ghi rejection; history/prefs/calibration hợp lệ vẫn xử lý theo transaction đã chốt |
| T18 | CAS conflict, storage failure hoặc lỗi sau commit trước trả summary | Không có commit dở; retry trả summary từ receipt đã lưu |
| T19 | Replay sang run mới cùng semantic context | Cache hit khi đủ cùng nội dung và versions; khác evidence/skill/model phải cache miss |
| T20 | Candidate, confirmation hoặc patch từ model đòi apply/tăng chi | Không có side effect; vẫn cần đúng seller/card/version gates |
| T21 | Cạn budget toàn phiên | Không có request vượt cap; fallback có source và call count đúng |
| T22 | Đổi learned record hoặc artifact trong fake scenario có kiểm soát | Input/seed lần sau đổi đúng; assert thực sự dùng lại record, không chỉ assert event memory_read |
| T23 | Golden A–E sau nối skill | A 70k/10%/5,5; B content-only và cảnh báo lỗ; C stock thấp bị loại trước LLM; D 45k/3%/6,5; E 50k/5%/5,5 rồi pause theo monitor |
| T24 | Model/service lỗi, JSON sai hoặc patch không hợp lệ | Day/night vẫn kết thúc an toàn; không tự biến counter hết vòng thành agreed |

T15 chỉ nhận settlement persistence khi business adapter hỗ trợ; RAM kiểm idempotency trong process. T16/T18 nhận durable restart khi member DB adapter qua contract tests; không làm giả nguồn business state. T23 giữ fixture validators/negotiation hiện có, không hardcode model response để ép đúng số. Voucher-edit cases dùng trusted event fixtures vì core HTTP hiện chưa hỗ trợ edit.

Calibration dùng raw daily prediction, không dùng tổng horizon hoặc dự báo đã hiệu chỉnh. Sample unique theo prediction/shop/day, cap 30; dưới 5 mẫu factor/quantiles=1; đủ mẫu giữ cách tính median/quantiles của Knowledge contract hiện có. Thiếu snapshot thì skip có lý do; không dựng prediction sau actual.

## 5. Tiêu chí hoàn tất và bàn giao

Core PASS: SI01–SI07 phần RAM/replay/runtime/headless đủ acceptance, full pytest qua, offline runs 7 ngày D/E tạo report từ Data engine. DB adapter chưa có thì durable NOT_CONNECTED; khi supplied factory qua reopen/recovery thì durable PASS. Provider evaluation NOT_RUN cho tới khi có đánh giá riêng qua provider; live reflection đơn lẻ không nâng eval_level lên provider.

Một invocation Learning không đồng nghĩa một provider request. Report ghi slots đã reserve, fake/replay/offline/live source riêng và hashes/effective days thực dùng. ON/OFF độc lập cùng seed/config; kết quả không bắt buộc memory ON tốt hơn. Muốn quy riêng tác động skill evolution cần thêm đối chứng memory-only, không suy ra từ tổng ON/OFF.

Prompt thực thi duy nhất nằm trong [README](self-improve/README.md). Các lệnh nghiệm thu ở SI07 là yêu cầu cho implementation, chưa được chạy trong lượt chốt schema. Không thêm GEPA, vector DB, embeddings hoặc worker framework vào đợt này.
