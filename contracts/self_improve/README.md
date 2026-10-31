# self-improve.v1 — schema bàn giao

- [v1.schema.json](v1.schema.json): schema tự chứa, Draft 2020-12; envelope chọn model bằng field `model`.
- [examples.json](examples.json): mẫu hợp lệ cho từng model, tất cả source=fixture.
- [invalid_examples.json](invalid_examples.json): mẫu bắt buộc bị từ chối.
- [invalid_cross_field_examples.json](invalid_cross_field_examples.json): hash/khóa/effective day/cross-record sai; Pydantic và application validators phải từ chối, JSON Schema đơn lẻ không đủ.
- [validation.json](validation.json): kết quả kiểm schema/mẫu, số model và SHA-256 schema.
- [DB_HANDOFF](../../docs/plans/toan/self-improve/DB_HANDOFF.md): khóa, ownership, null, transaction, adapter interface và nghiệm thu.
- [Bộ giao việc](../../docs/plans/toan/self-improve/README.md): thực hiện SI01–SI07 liên tục.

Nguồn export là [schema_contract.py](../../docs/plans/toan/self-improve/schema_contract.py). Đây là reference cho handoff; ứng dụng không import code trong docs. Các domain model đã có được exporter tái sử dụng, các model mới được khai báo làm hợp đồng mục tiêu. Implement models tương ứng trong app theo các task rồi giữ kiểm tra parity với artifacts này.

Từ repo root:

```sh
.venv/bin/python docs/plans/toan/self-improve/schema_contract.py
```

Lệnh luôn kiểm Pydantic JSON validation, export deterministically và kiểm JSON Schema nếu môi trường có package `jsonschema`. `validation.json` ghi rõ kiểm nào đã chạy; thiếu jsonschema không được báo đã kiểm Draft 2020-12. Không cần cài dependency này vào runtime ứng dụng. Kiểm trên wire JSON, không validate_python dict chứa array cho tuple StrictModel.

`$defs` chứa thêm models hiện có được tham chiếu; số top-level models là số envelope trong schema. Các mẫu là dữ liệu thiết kế, không phải kết quả chạy model/proof. Không đưa payload fixture vào runtime learning. Snapshot mẫu đủ kiểm shape/hash; fixture events cho kiểm provenance được tạo trong SI03.

Schema không chứng minh transaction, permission hoặc nguồn evidence hợp lệ; các invariant đó ở DB_HANDOFF và các contract thuần/publication/runtime. Envelope dành cho export/adapter, không thêm field bắt buộc vào HTTP/tool DTO cũ. Thay đổi breaking cần version schema mới và migration do bên DB cung cấp; v1 thêm fields tùy ý sẽ bị extra=forbid chặn.
