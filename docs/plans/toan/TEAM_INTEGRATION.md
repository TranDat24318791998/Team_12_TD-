# Các đầu nối đã chốt cho bản local

Bản tích hợp dùng Data authority theo [DEMO_CONTRACT](../../DEMO_CONTRACT.md). Chín báo cáo [Astra riêng](full-integration/REVIEW_ASSIGNMENTS.md) ghi baseline và lỗi trước implementation; các blocker cũ như accept→activate sớm đã được Data sửa từ9621b14. Không dùng bảng cũ để dựng một Session business thứ hai.

| Đầu nối | Contract hiện hành |
| --- | --- |
| UI/API | `app.main:create_app` ghép Data facade/worker/static cùng origin8000; cookie growth_sid; không thêm facade RAM |
| Agent | Data operation → scoped Data context → native graph/tools → explicit Referee finalize → card; không HttpHarness/reference_offer trong product worker |
| Brief/versions | Seller persist confirmed brief; card/brief/draft/job/content IDs do Data cấp; React gửi expected versions/identity đã xem |
| Approval | Accept tạo approved content job; Apply kiểm actual asset bytes + video choice rồi listing/campaign/event/receipt atomic |
| Knowledge | Rules Data authority; derived records/skill/phase/budget ở cùng SQLite; same-connection publication và preference confirmation |
| Night | Daily prediction trước settlement, immutable cutoff, public evidence, one publication/handoff; complete sau horizon1..7, default7 |
| Media | HTTP tới experiment8010; original D desktop được user chọn từ MinIO; optional logo, bright/all retry, video từ A cùng attempt, verified Data assets |
| Local | Hai loopback processes, file storage media, owned lifecycle; không cần MinIO daemon/tunnel |

Phạm vi/file ownership và chữ ký giao coder tại [IMPLEMENTATION_PLAN](full-integration/IMPLEMENTATION_PLAN.md). Các source/live/offline/fixture gate tách riêng. Cả suites từng lane pass vẫn cần test integrated native protocol, Data transaction/reopen, actual HTTP media fakes và local startup.
