# Nghiệm thu bản local

**Review bổ sung commit `[3.4]` đã đóng:** Terra sửa lỗi tại ranh giới backend → frontend, Astra max kiểm lại độc lập hai lane và không còn finding mở trong luồng demo đã kiểm. Xem [backend](COMMIT_3_4_BACKEND_REVIEW.md) và [UI recheck](COMMIT_3_4_UI_RECHECK.md); [frontend review ban đầu](COMMIT_3_4_FRONTEND_REVIEW.md) giữ tái hiện trước sửa. Preset chỉ đọc và logo mới cũng đã được kiểm trong lượt này.

Cập nhật 31/10/2026, sau lượt review bổ sung `[3.4]`. **Đã implement và hoàn tất 9 review Astra max ban đầu, cùng recheck backend/UI cho patch mới.** Coder dùng Terra 6.1 max. Làm trên main; plan tại `d46c812`, implementation tại `075ee58`/`65434cb`, phần lớn patch mapping/preset/logo tại `e272ae2`; patch FI03 chốt shop logo, thông báo tiếng Việt và nghiệm thu.

## Bản đang chạy

- Seller/React/Data/native worker: [mở demo](http://127.0.0.1:8000/?preview=0).
- Media service: loopback8010, local file storage. Cả hai process READY; không mở tunnel, Docker hoặc MinIO mới.
- Phiên mới dùng LLM_MODE=live và MEDIA_MODE=live, OpenAI cho native LLM/ảnh/vision/planning/review, Muse cho video. Đây là cấu hình để chạy; chưa có paid generation trong nghiệm thu. Các run kiểm thử offline cũ giữ nguyên mode/state.
- D dùng ảnh quạt để bàn từ MinIO người dùng cung cấp. Ảnh/provenance ở `assets/products/demo-d-desktop.{jpg,source.json}`; SHA256 `f15b1eb1c6006c408476112f6e8f1cf863b3d5d6794e6a15c19e55310225d25e`. Giá/cost/stock/rules và số simulator vẫn là mô phỏng, không suy pin/USB từ ảnh.
- Logo ShopPilot AI giữ nguyên file người dùng gửi tại `frontend/img/shoppilot-ai.png`, SHA256 `fa91fccb2889f72e6fe938b4e3776afbbdb628bc3d94a9d356c5fb59725479b4`. Header và nhận diện shop D dùng cùng ảnh; DEMO_LOGO_IMAGE_PATH trỏ cùng file cho job media mới. Tên Nhà Bé Lan và số kinh doanh không đổi.
- Demo D đặt sẵn **24 đơn trong 3 ngày**, **45.000đ/ngày**. Data persist preset; UI chỉ hiển thị và xác nhận. HTTP sửa giá trị bị từ chối, chưa xác nhận không được Start. Brief đã xác nhận trong run cũ giữ nguyên lịch sử.

## Đã nối

Data là business authority duy nhất; Knowledge/SI dùng cùng `data/runtime/growth.db`. Native Platform/Shop/Referee, scoped tools, Content và Learning chạy qua worker/DB, có seller confirmation/version gates, immutable evidence và durable reservations. Agent sàn/Content/Learning nhận projection đúng quyền; raw private feedback chỉ giữ trong audit.

Media bridge tái sử dụng experiment qua HTTP: A → video từ A → B/C, checksum/MIME/import, exact attempt/approval binding, seller ack/skip và Apply. Unknown giữ reservation, không resend bằng key mới. Offline chỉ dùng ảnh gốc có nhãn cache, không giả generation. LLM và media modes độc lập; background shops dùng native offline flow để dành budget64 cho demo shop.

Night publication giữ snapshot/receipt/Knowledge/skill versions/handoff/advance atomic. Skill effective d+1 và được pin theo negotiation. Native tool read-back, reopen, Rules/preferences, skip/publication race và budget không regrant đã có kiểm chứng. Startup chặn queued/running work và pending/running Learning; stop giữ media khi app chưa drain.

## Review riêng từng phần

| Phần | Kết quả cuối | Báo cáo |
| --- | --- | --- |
| DB | PASS | [DB](DB_FINAL_REVIEW.md) |
| Agent điều phối | PASS | [Agents](AGENTS_FINAL_REVIEW.md) |
| Native tools | PASS | [Tools](TOOLS_FINAL_REVIEW.md) |
| Knowledge | PASS | [Knowledge](KNOWLEDGE_FINAL_REVIEW.md) |
| Self-improve | PASS | [Self-improve](SELF_IMPROVE_FINAL_REVIEW.md) |
| Media | PASS trong offline/fake-provider scope | [Media](MEDIA_FINAL_REVIEW.md) |
| API | PASS | [API](API_FINAL_REVIEW.md) |
| React | PASS | [UI](UI_FINAL_REVIEW.md) |
| Local host | PASS; root đã bổ sung restart thật | [Host](HOST_FINAL_REVIEW.md) |

Các finding đã xử lý gồm edit-child approval chain, lease expiry, start thiếu brief qua v1, reset receipt lẫn run, interrupted operation khóa ngày, Content privacy, LLM/media mode coupling, delayed Start navigation, saved-proof delivery, Learning startup preflight và shutdown/storage readiness. Báo cáo giữ reproduction trước fix để audit; đọc current verdict/recheck ở đầu.

Lượt bổ sung `[3.4]` sửa hai P1 (check cuối mất boolean, proof/log lệch run sau reset) và năm P2 khác nhau (source label, retry gate, Night ID thay text, câu hỏi trọng tài, nguồn saved proof không dùng được trong preview). Code check giữ proposal/round/ok và tiếng Việt; dữ liệu legacy thiếu boolean bị bỏ qua, không suy pass từ card. Proof/export bind đúng comparison và hai run. Night seller projection có text và record refs; source lấy receipt/telemetry thực. Bộ kiểm mới đưa payload HTTP native thật qua React, không chỉ ghép hai bộ fixture tự viết.

## Verification đã chạy

| Kiểm tra | Kết quả |
| --- | --- |
| `LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q` | **162 passed +15 subtests**,98,08s sau patch mapping/preset; label-only patch cuối có9focused tests pass |
| `LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -c data/pyproject.toml data/tests -q` | **56 passed**,62,08s |
| `PYTHONPATH=experiment experiment/.venv/bin/python -m pytest experiment/tests -q` | **28 passed**; sau label-only patch, signed-watch test thêm1passed |
| Frontend tests/build | **56 passed**, build PASS |
| Private headless Chrome start/proof/branding scripts | PASS: preset từ server, explicit confirm, accepted202 mở Demo, exactly-one POST, stream/error, proof bootstrap/source/download, logo desktop/mobile và shop identity |
| Native HTTP → React | Astra backend15tests pass70,09s với Node tường minh; UI3targetedtests pass, không skip; isolated real Data pair → React integration PASS |
| Logo media | Real HTTP fake-provider test PASS: logo giữ nguyên pixel sau upload, đúng logo asset ID trong cả A/B/C; không gọi generation thật |
| Root/media dependency checks | PASS; root pip check, media uv pip check42packages |
| Local actual HTTP day1→day2 | PASS: brief→native negotiation→accept→cached content→retry bright→Apply/skip video→night→day2 preference Yes |
| Actual browser against8000 | PASS: đúng sản phẩm, saved proof day7, report/evidence downloads, không đổi active run; fresh direct Proof bootstrap cũng PASS |
| Stop/start + persistence | PASS: cùng cookie/run/day2, package/card/style/night summary và ảnh vẫn nguyên; new session mode live, vẫn idle |
| Sau patch FI03 trên server8000 | PASS: restart giữ run/day2/business state; Night trả text mới; browser ẩn thấy ảnh quạt thật + logo + preset chỉ đọc; current proof409 và saved proof ngày7 không đổi active run; paid reservations vẫn0 |
| Readiness/static/asset | health/ready/HTML/JS200; original SHA đúng; asset Range206; authenticated media readiness local/growth-media.v1 sau actual storage probe |
| Database | integrity_check=ok, foreign_key_check rỗng; native paid reservation toàn local DB=0 sau nghiệm thu |

Root giữ evidence kiểm máy tại ignored `data/runtime/local-stack/{verification,restart-verification,browser-verification}.json` và screenshot `shop.png`/`proof.png`. Đây là kiểm trên Mac này, không phải browser matrix đa thiết bị. Snapshot DB trước product smoke ở `data/runtime/backups/pre-full-integration.db`; lúc snapshot có0run/schema4. Upgrade v2 có linked rows được kiểm riêng bằng temp DB regression.

Lượt FI03 bổ sung `branding-verification.json`, `pre-fi03-restart.json`, `shop-fi03.png` và `shop-fi03-mobile.png` trong cùng thư mục ignored. GET bootstrap của browser kiểm tạo một run mới ở idle, chưa confirm; không có POST/provider job, không đổi phiên đang dùng của người bán. Hai process đã nạp source/config logo mới và đều READY sau restart.

## FI04 — phản hồi seller, nguồn kiểm tra và media song song

Ngày 31/10/2026 15:55, sau các phản hồi trực tiếp của người bán:

- Thương lượng thêm chờ đúng attempt; trả thẻ mới nếu đạt thỏa thuận hoặc hiện lý do chưa có offer điều chỉnh. Ask_human không bị đổi thành agreed. Gói giữ nguyên có nhãn riêng; unknown không mở kết thúc ngày. Kết quả phục hồi từ SQLite sau reload và xử lý cả event/state đến lệch nhịp.
- Mỗi dòng code check ghi nguồn và phiên bản Rules/giá vốn/phí/tồn kho thực dùng. Tài liệu phí có checksum và link Knowledge xác thực, được ghi rõ là tham khảo giả lập. Event cũ thiếu nguồn không được điền bằng dữ liệu hiện tại. Kiểm độc lập Astra chứng minh nguồn lịch sử không đổi theo Rules mới, verdict false không bị ghi thành true, platform không đọc được checks và session khác không đọc được tài liệu.
- Ba ảnh A/B/C chạy đồng thời; video chỉ chờ ảnh A của cùng attempt nhập thành công, không chờ B/C. Media xử lý tối đa ba job đồng thời trong một process; shutdown giữ lock tới khi các job đang chạy kết thúc. Retry/idempotency/unknown và giới hạn chi vẫn giữ. Mỗi slot chỉ hiển thị khi asset đúng binding và checksum; UI lấy state ở nhịp polling bình thường.

Verification: root suite **170 passed +15 subtests**,123,07s; Data56, native integration15 và5focused sau chỉnh cuối; media bridge22; experiment29 và shutdown regression1; frontend67,44affected sau chỉnh cuối, build,5headless và isolated Data→React PASS. Astra review từ `cfcccca` tới source cuối: PASS, không có finding chặn.

Hai dịch vụ đã restart và READY. Cùng seller run ở ngày2/content_review, draft succeeded, ba ảnh JPEG và video MP4 đều còn tải được bằng Range206; hai SQLite quick_check=ok. Không còn queued/running work trước restart. Các số paid reservations=0 ở bảng FI03 phía trên là snapshot trước lượt seller tự chạy: lượt live của seller từ15:46:00 tới15:48:39 đã tạo ba ảnh và một video, được kiểm lại file/HTTP, không tạo generation mới để thử. Chưa đo tốc độ hoặc rate limit của provider với lịch chạy song song mới; provider evaluation vẫn chưa thực hiện.

## Proof đã giao vào UI

Chọn **Báo cáo mô phỏng đã chạy** trên màn Proof. `GET /api/proof/demo` đọc fixed artifact `data/runtime/demo-proof.json`, xác thực seller D và kiểm typed schema/hash/scope. Không khởi chạy comparison hoặc đổi active run. Report/log exports thuộc đúng cặp source ON/OFF, không lấy events của phiên đang mở.

Cặp D nguồn: `runs/sim-D-8984ae2c0383489faa90fa171f0090f5/comparison.json`; E: `runs/sim-E-0a7c0ce93ed84838b0283df696c9c269/comparison.json`. Mỗi cặp cùng seed42/horizon7/config, dùng native offline + Data simulator. D lợi nhuận ON/OFF1.276.752/1.258.888đ, số đơn57/58; E738.624/662.476đ,48/52. Không ép mọi chỉ số ON phải thắng.

Artifact D: comparison `group_4349d9bc018e4cdfbdc9`, ON `run_a716ec6e871f46d289f1`, OFF `run_74814d1d029c40deb24b`;5metrics, dialogue ngày1/4/7,53/55safe events. Manifest hash `789ea8c917aedc474e61920e8ce01e566ac2a72ecbc8970333ee3ea96133e303`. Exporter cuối đã kiểm source DB không đổi, loại late/private/other-shop records, thiếu/tampered/non-D/unauth và GET không đổi state. Cách xuất lại ở [LOCAL_RUN](../../../LOCAL_RUN.md).

## Giới hạn còn chủ động giữ

- **MEDIA_LIVE acceptance độc lập, PROVIDER_EVAL và replay từ recording provider thật: NOT_RUN.** Các test tự động dùng fake/offline providers; imported video từ MinIO chỉ là cache có provenance. FI04 đã kiểm file/HTTP của lượt live do seller tự chạy như ghi ở trên, chưa thay cho các gate này.
- D/E reports được đo trước một số patch privacy/recovery cuối; các patch đó có focused regressions và full suite ở source cuối. Chưa chạy lại toàn bộ bốn run7ngày sau mọi patch. Không gắn chúng nhãn provider-evaluated/live.
- Saved artifact giữ yêu cầu gốc đã thực thi, có thể khác preset24đơn/45.000đ của run mới. UI hiển thị yêu cầu gốc trong phần nguồn báo cáo, không viết lại lịch sử. Bộ chọn tùy ý nhiều dataset7ngày với đầy đủ state/NightSummary ở requirements mục9/13 chưa được nghiệm thu; hiện chọn rõ current proof hoặc measured artifact, không dùng SQLite preview blob làm evidence.
- T01–T24 không được tuyên bố là exhaustive matrix: mọi tổ hợp vote/edit/eviction, concurrent pin/publish và process-kill chưa phủ hết. Chi tiết ở SI final review. Chưa bổ sung spam/multi-user/distributed workflow.
- Reference catalog hiện có3Platform/2Content records. Trước khi mở rộng catalog cần chọn version mới nhất và cap5 như Knowledge review; demo hiện tại dùng bộ nhỏ này.

Lệnh vận hành và giới hạn local/reboot/sleep ở [LOCAL_RUN](../../../LOCAL_RUN.md); contracts chung ở [DEMO_CONTRACT](../../../DEMO_CONTRACT.md).
