# Self improve — bộ giao việc hoàn chỉnh

**Cập nhật phạm vi sau khi DB về:** [full-integration](../full-integration/README.md) và [SI review](../full-integration/SELF_IMPROVE_REVIEW.md) yêu cầu triển khai SQLite repository trong cùng Data DB và kiểm durable/reopen. Các câu “không tự làm DB”, “không tạo migration”, “NOT_CONNECTED” ở bản phân công gốc bên dưới không còn là điểm dừng của lượt tích hợp này. Schema/algorithms/acceptance SI01–SI07 giữ nguyên; migration do Data coder, repository do SI coder theo ownership mới.

Ngày chốt: 31/10/2026. Gói này khóa schema và cách tích hợp để một coding agent thực hiện SI01 → SI07 trong một lượt làm việc liên tục. DB do member khác cung cấp; improve phát triển qua repository contract và RAM, không tự làm DB. Đây là tài liệu triển khai cùng schema đã kiểm, chưa phải tính năng ứng dụng đã được implement.

## Bắt đầu đúng tài liệu

| Người nhận | Điểm bắt đầu |
| --- | --- |
| Coding agent | Đọc README này, AGENTS.md, rồi từng task theo thứ tự bên dưới |
| Member DB | [DB_HANDOFF](DB_HANDOFF.md), [JSON Schema](../../../../contracts/self_improve/v1.schema.json), [examples](../../../../contracts/self_improve/examples.json) |
| Reviewer | [Plan tổng thể và ma trận T01–T24](../SELF_IMPROVE_IMPLEMENTATION_PLAN.md), acceptance từng task, report thực chạy |

[Schema package](../../../../contracts/self_improve/README.md) có schema version self-improve.v1, mẫu hợp lệ/sai và validation report. [schema_contract.py](schema_contract.py) là nguồn export tham chiếu; ứng dụng không import file trong docs. Domain types hiện có được tái sử dụng; các kiểu mới phải đưa về đúng module app trong task tương ứng.

## Các quyết định đã khóa

- Giữ năm role Platform/Shop/Referee/Content/Learning, native tools, tối đa ba Platform rounds và budget chung 64. Learning có một invocation/night, tối đa ba provider requests trong invocation, không thêm reflector riêng. Đây là lựa chọn theo core hiện hành, khác cap 40/một request trong bản paste.
- Một demo_shop mỗi Session/run; đối chứng shop khác dùng run khác. Horizon cấu hình 1..7; headless mặc định 7 ngày/D. Không đổi facade 9 API/UI hoặc hệ thống chờ seller trong đợt này.
- Bốn base skills; chỉ platform_offer/platform_renew có learned steps. Ba actions: seed từ package đã duyệt, seed voucher đã sửa và duyệt, tắt ads khi renew sau auto-pause. Tổng năm cặp action/target; thứ tự cố định.
- Rules chỉ đổi qua seller confirmation. Mọi seed vẫn qua validators/approval; agreed chưa applied không thành evidence đã chạy. Không có model-generated code, mức tiền tùy ý hoặc sửa base prompts.
- Evidence public đúng run/shop/category/cutoff; phase snapshot cố định. Skill đêm d có hiệu lực d+1; attempt pin version/seed từ đầu. Memory OFF không đọc/ghi learned state.
- Publication atomic: knowledge + skill versions + revision/cursor + full receipt. Phase và budget reserve trước network. Retry dùng receipt; unknown không được gửi lại provider.
- DB schema vật lý/engine do member DB chọn. Improve cung cấp DTO/keys/ports/RAM/contract tests. Chưa có factory: durable NOT_CONNECTED, tiếp tục hoàn tất core. Không đồng nhất Knowledge recovery với phục hồi business Session.
- Proof dùng Data engine hiện có, runtime thật và offline content assets; không fake chỉ số hoặc yêu cầu ON phải thắng OFF. Provider eval có trạng thái riêng.

## Thứ tự thực hiện

| Task | Kết quả và contract cần đọc | Phụ thuộc |
| --- | --- | --- |
| [SI01](01-schema.md) | Models thuần + fixtures; CORE mục 1/5 | Models repo hiện có |
| [SI02](02-compiler.md) | Compiler/hash/seed; CORE mục 3–5 | SI01 |
| [SI03](03-evidence.md) | Event joins/provenance; CORE mục 2/5 | SI01–02 |
| [SI04](04-publication.md) | Publication DTO, pure stage, repository RAM; PUBLICATION + DB_HANDOFF | SI01–03 |
| [SI05](05-learning.md) | Native Learning, phase/budget, eval + commit; LEARNING_RUNTIME mục 1–3/7 | SI04 |
| [SI06](06-runtime.md) | Base assets, pin/tool/seed ngày sau; LEARNING_RUNTIME mục 4–6 | SI05 |
| [SI07](07-integration.md) | Adapter injection, replay, headless proof, docs; REPLAY_PROOF | SI06 |

Mỗi task có Output, steps, tests và lệnh nghiệm thu. Chạy focused checks rồi chuyển tiếp tự động; full suite tại SI06 và sau thay đổi SI07. Không cần người dùng mở từng task. Không đặt timebox thay cho tiêu chí xong.

Đọc source/diff hiện tại trước khi sửa vì agent khác đang làm core. Tiếp tục implementation đã có, không reset/ghi đè hoặc dựng lại từ mô tả cũ. Contract mở rộng trong gói này là scope đã giao; cập nhật shared docs ở SI07. Nếu source đổi tên/field, cập nhật caller mapping có regression tests; không tự thay business semantics. Nếu dependency thật thiếu, hoàn tất phần độc lập qua fake/adapter đúng contract và ghi rõ trạng thái thiếu, không tự bịa kết quả tích hợp.

## Prompt giao một lần

```text
Implement trọn gói self improve trong repo hiện tại theo
  docs/plans/toan/self-improve/README.md.
Đọc AGENTS.md, giữ thay đổi của agent/member khác và kiểm source hiện hành.
Thực hiện liên tục SI01 → SI07, mỗi bước đọc đúng task và contract được dẫn tới.
Chạy focused acceptance từng bước, sửa lỗi, tự chuyển bước kế tiếp; không dừng
để xin chốt thiết kế hay mở task tiếp. Không tự tạo DB hoặc migration.
DB do member khác cung cấp theo DB_HANDOFF và contracts/self_improve/v1.schema.json;
implement RAM + repository ports + contract tests + store_factory injection.
Nếu chưa có DB factory, hoàn tất core và báo durable NOT_CONNECTED.
Giữ native tools/5 roles/cap 64, chỉ evolve hai Platform skills bằng policy allowlist.
Dùng lại derive/history seeding/privacy/validators/runtime hiện có.
Night phải freeze evidence, reserve phase/budget, stage/eval và commit atomic;
retry/unknown không được gọi lại invocation. Pin skill theo attempt, hiệu lực d+1.
Giữ seller approval/Rules, không thêm UI edit hoặc facade/media/DB ngoài scope.
Dùng schema/examples làm chuẩn wire; không import docs code vào ứng dụng.
Sau SI07 chạy full tests và run_sim offline 7 ngày cho D và E.
Không gọi provider trả phí trong pytest hoặc tự chạy live để lấy PASS.
Bàn giao: file đổi, acceptance→test, lệnh/kết quả, artifact/version/hash,
report ON/OFF thật, source/budget slots, core/durable/provider_eval status,
và dependency thật còn thiếu nếu có. Ghi CODEX_LOG sau mỗi task.
```

## Ranh giới bằng chứng

Schemas đã được kiểm trong [validation.json](../../../../contracts/self_improve/validation.json). Các lệnh pytest/run_sim trong task là lệnh coding agent phải chạy sau implementation; không phải kết quả của lượt chốt plan này. Bản attachment chỉ tóm tắt đặc tả, chưa có file gốc 50 case để xác nhận parity đủ 50. Ma trận 24 case cùng acceptance từng task là phạm vi cụ thể được chốt ở đây.

Các tài liệu quyết định: [CORE](CORE_CONTRACT.md) cho thuật toán thuần; [PUBLICATION](PUBLICATION_CONTRACT.md) cho stage/store; [LEARNING_RUNTIME](LEARNING_RUNTIME_CONTRACT.md) cho caller flow; [REPLAY_PROOF](REPLAY_PROOF_CONTRACT.md) cho kiểm tích hợp. [INTEGRATION_GATES](INTEGRATION_GATES.md) chỉ là checklist nghiệm thu, không còn là danh sách thiết kế chờ chốt.
