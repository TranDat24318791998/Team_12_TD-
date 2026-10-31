# Checklist nghiệm thu tích hợp đã chốt

Các quyết định SI04–SI07 đã được khóa vào contract/task tương ứng. File này giữ vị trí link cũ và chỉ ghi điều kiện nghiệm thu; không yêu cầu một vòng integrator thiết kế lại trước khi agent bắt đầu.

| Phần | Contract và task | Điều kiện PASS |
| --- | --- | --- |
| DTO và DB boundary | [DB_HANDOFF](DB_HANDOFF.md), [schema](../../../../contracts/self_improve/v1.schema.json), [SI04](04-publication.md) | Wire shape, khóa/scope, null, versions và hash đúng; DB không sở hữu thêm business state qua Knowledge |
| Publication | [PUBLICATION](PUBLICATION_CONTRACT.md), SI04–05 | Records/versions/meta/full receipt cùng transaction; same-key khác payload conflict; không commit dở |
| Native Learning | [LEARNING_RUNTIME](LEARNING_RUNTIME_CONTRACT.md), [SI05](05-learning.md) | T08 frozen; bounded invocation; phase/budget reservation; không chạy lại provider khi unknown |
| Skill activation | LEARNING_RUNTIME, [SI06](06-runtime.md) | d+1, attempt pin, native/fallback dùng seed, memory OFF sạch learned state, validators/approval giữ |
| Repository RAM | [REPLAY_PROOF](REPLAY_PROOF_CONTRACT.md), [SI07](07-integration.md) | Contract tests atomic/CAS/duplicate/concurrency/copy-on-read qua |
| Repository durable | DB_HANDOFF, SI07 | Cùng suite và reopen/recovery qua trên adapter do member DB cung cấp |
| Replay | REPLAY_PROOF, SI07 | Semantic key/rebinding đúng, private scope giữ, miss không gọi live, không mất slot khi hit |
| Headless proof | REPLAY_PROOF, SI07 | Runtime + Data engine, daily snapshot trước actual, ON/OFF độc lập 7 ngày, metrics/source thật |
| Provider evaluation | Evaluator riêng ngoài lượt offline | Baseline/candidate cùng scenario/model/config được chạy qua provider và lưu kết quả |

Chưa được cung cấp DB adapter: ghi durable NOT_CONNECTED, vẫn hoàn thành improve core bằng RAM. Chưa chạy evaluator provider: ghi provider_eval NOT_RUN; deterministic tests không thay thế. Không tự mở dependency ngoài phạm vi chỉ để tất cả trạng thái thành PASS.

Facade/API/Frontend/media tích hợp sản phẩm đầy đủ tiếp tục theo [TEAM_INTEGRATION](../TEAM_INTEGRATION.md). Chúng không ngăn core headless dùng runtime hiện tại. Voucher edit kiểm bằng fixture nghiệp vụ hợp lệ vì core HTTP hiện không hỗ trợ edit; không ghi là UI đã có tính năng đó.
