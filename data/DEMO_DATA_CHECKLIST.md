# Bảng kiểm dữ liệu và API cho demo Growth Agents

Ngày đối chiếu: **31/10/2026**. Làm trên `main`, chỉ trong `data/`.
Đây là bảng kiểm hiện trạng và nghiệm thu; không thay thế hoặc sửa file thiết kế.

**Kết luận:** có đủ **61 HTTP operations** của service local, gồm 1 health,
9 legacy demo, 42 API v1 và 9 internal. Luồng offline chạy đủ 7 ngày; frontend,
agent LLM, provider media và memory store thật chưa được nối. Có route không có
nghĩa đã hoàn thành tích hợp. Các khoảng trống tập trung tại mục 10.

## Cách đọc và cập nhật

- **API:** `Đã có` = có handler cho chức năng nêu trong dòng; `Một phần` = có
  handler nhưng chưa đáp ứng hết hành vi cần; `Chưa có` = chưa có endpoint/chức năng.
- **Tích hợp:** `Đã kiểm chứng` = chỉ đạt trong profile nêu ở bằng chứng, có thể là
  service local hoặc worker giả; `Chưa nối` = thiếu kết nối với module dùng thật;
  `Chưa kiểm chứng` = mới đọc code hoặc chưa có test cho tình huống đó.
- **Ưu tiên:** P0 chặn luồng cần demo; P1 thiếu hành vi/dữ liệu của kịch bản;
  P2 phần bổ trợ. Nhóm phụ trách là gợi ý giao việc theo module, chưa phải cá nhân.
- `[x]` chỉ dùng khi tiêu chí được kiểm chứng trong phạm vi ghi rõ. Các mục cần UI,
  LLM, media hoặc memory thật vẫn `[ ]` dù hạ tầng local có test pass.
- Mỗi endpoint có ID `API-001` đến `API-061`, xuất hiện đúng một lần trong các bảng
  inventory. ID `DATA`, `UI`, `AG`, `ORCH`, `CONTENT`, `SIM`, `LEARN`, `PROOF`,
  `SEC`, `GAP`, `AT` theo dõi yêu cầu, lỗi và nghiệm thu; dẫn chiếu API để tránh đếm lặp.
- Tham số `{r}` là run, `{s}` là shop; `{pid}`, `{cid}`, `{jid}`, `{aid}`, `{did}`,
  `{oid}` lần lượt là proposal, content/campaign tùy route, job, asset, document,
  operation. Query không làm tăng số HTTP operations.

### Vai trò và phạm vi quyền

| Ký hiệu | Vai trò thực tế |
| --- | --- |
| P | `platform_agent` |
| H | `shop_agent` |
| U / US | `seller` / `simulated_seller` |
| O | `orchestrator` |
| C | `content_worker` |
| L | `learning_worker` |
| M / N | `simulator` / `monitor` |
| E / K / A | `evaluator` / `knowledge_admin` / `data_admin` |
| B | Nhóm PRIVATE hiện có: H, U, US, O, M, L, E, A |
| T | Principal đã xác thực và được phép truy cập run; không đồng nghĩa được đọc mọi shop |

Phạm vi trong bảng mô tả code hiện tại: **run** phải thuộc session hoặc token
được cấp quyền; **shop** kiểm tra thêm shop được giao; **job** kiểm tra thêm job
được giao cho C; **owner** là principal tạo upload; **visibility** áp dụng quyền
published/shop-private/internal. K không tự có quyền đọc mọi API nghiệp vụ.

V1 và internal dùng `{data,meta}`; command JSON cần `X-Request-ID` và
`Idempotency-Key`. Upload bytes là ngoại lệ, dùng quyền owner, hạn upload và checksum.
Legacy dùng seller cookie `growth_sid`, trả JSON trực tiếp; mutation cần
`Idempotency-Key`. Không cấp token backend cho JavaScript frontend.

### Nguồn và mã bằng chứng

| Mã | Nguồn / phạm vi được chứng minh |
| --- | --- |
| CODE | [api.py](growth_data/api.py), [service.py](growth_data/service.py), [models.py](growth_data/models.py), [media.py](growth_data/media.py), [facade.py](growth_data/facade.py), [evidence.py](growth_data/evidence.py); đọc code, không tự suy ra đã test |
| SEED | [test_seed_finance.py](tests/test_seed_finance.py): seed/history, phí/lãi, voucher D, redact, manifest tất định |
| AUTH | [test_api_security.py](tests/test_api_security.py): phiên/run/shop, projection, cursor, chống giả role, idempotency/Origin |
| FLOW | [test_workflow.py](tests/test_workflow.py): legacy ngày 1→2, retry, thương lượng/từ chối, 7 ngày, đối chứng reference, upload |
| WORK | [test_handoffs_and_content.py](tests/test_handoffs_and_content.py): learning worker giả, câu hỏi luật, lease, memory-off, search/revoke |
| TX | [test_commands_and_artifacts.py](tests/test_commands_and_artifacts.py): apply đồng thời, rollback settlement, content result giả, PDF/manifest |
| CAL | [test_calibration.py](tests/test_calibration.py): callback snapshot chỉ dùng ngày trước, memory-off bỏ qua callback |
| AUDIT | Gọi thử TestClient trên DB tạm khi rà kịch bản: state/card/content/night/proof; tái hiện external legacy night 409. Không phải test regression đã commit |
| HTTP7 | Smoke HTTP trước đó: [smoke_demo.py](examples/smoke_demo.py), 7 ngày PASS; chỉ profile local offline, xem [PROGRESS.md](PROGRESS.md) |
| HTML | [Sáu màn minh họa](<Màn hình demo Growth Agents.html>): đã giải nén template trong bundle để đọc; chưa gọi Data API |

## 1. Seed, schema, lịch sử và kịch bản 7 ngày

| ID | Yêu cầu / dữ liệu | API hoặc nguồn; bên dùng | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- |
| DATA-01 | Project uv riêng, migration SQLite và foreign keys | CLI; Data/backend | Không áp dụng | Đã kiểm chứng | `pyproject.toml`, `uv.lock`, `growth_data/migrations/001_initial.sql`; suite tạo DB tạm | Chưa xác minh adapter cloud; Data, P2 |
| DATA-02 | 5 shop, product facts, phí và luật gốc; D 175.000đ, vốn 115.000đ, kho 300 | `datasets/seed.json`; API-012…017 | Đã có | Đã kiểm chứng | SEED: `test_original_financial_examples`, `test_d_voucher_finance_not_persona` | Agent thật chưa đọc; Agent, P0 |
| DATA-03 | 14 ngày lịch sử: 140 channel rows/run; chưa có kết quả hoạt động khi tạo run | API-020; seed_run | Đã có | Đã kiểm chứng | SEED: `test_seed_history_and_no_precomputed_outcomes` | Không dùng lịch sử làm bằng chứng học mới; Data/Agent, P1 |
| DATA-04 | 7 ngày: 35 settlements, 70 channel rows mới/run; không có ngày 8 | API-039…041, 052 | Đã có | Đã kiểm chứng | FLOW: `test_seven_day_reproducibility_and_no_fake_learning`; HTTP7 | UI chuyển 6→7 ngày; Frontend, P1 |
| DATA-05 | 24 file manifest, nhãn giả lập, 9 MD, 4 PDF, 5 ảnh placeholder | `datasets/manifest.json`; API-028, 050 | Một phần | Đã kiểm chứng | TX: `test_four_pdf_guides_and_manifest_checksums`; SEED manifest | Thiếu ảnh sản phẩm thực dụng cho trình diễn; Content/Data, P1 |

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-001 | `GET /health` | Trạng thái service/storage local | Không yêu cầu auth | Đã có | Đã kiểm chứng | AUTH: `test_health_bootstrap_and_openapi` | Metadata health chưa phản ánh đầy đủ worker/provider được nối; Data, P2 |

- [x] DATA-06: Seed/local schema và số hàng lịch sử/hoạt động đạt kiểm tra tự động.
- [ ] DATA-07: Media, chế độ replay và nhãn số ngày khớp nội dung demo thật.

## 2. Sáu màn minh họa và 9 API giao diện

| ID / màn | Dữ liệu và thao tác cần | API liên quan | Kết quả hiện tại / việc còn thiếu |
| --- | --- | --- | --- |
| UI-01 / Trang shop ban đầu | Listing, giá, kho, màu, rating, chủ shop, trend, bộ nhớ/mode, bắt đầu/reset | API-002…004, 012, 013, 019 | Listing cơ bản có; owner lấy qua context của seller; màu từ facts; trend qua summary. UI chưa nối; reset giữ audit run cũ, chưa xóa memory store ngoài |
| UI-02 / Thương lượng và thẻ | Hai bên trao đổi, lượt, checks, gói, dự báo, lãi, stop; accept/negotiate/reject | API-004…006, 024…026, 035…038, 060 | Gói D 45.000đ/ngày, voucher 3%, stop 6,5 có; thiếu đầy đủ event/lời giải thích và timeline UI |
| UI-03 / Duyệt nội dung | Trước/sau, feedback, A/B/C, video 15s, retry 1…3, duyệt | API-002, 007, 008, 043…051 | Có version/approval; ba ảnh local cùng URL nguồn, video failed; chưa có 4 ảnh nguồn như HTML |
| UI-04 / Shop sau áp dụng | Listing đã duyệt, ảnh chọn, voucher/ads, thay đổi, xem cũ, hoàn tác | API-002, 008, 022, 043 | `demo_shop_original` phục vụ xem bản ban đầu; chưa có luồng hoàn tác hoàn chỉnh, diff và thời điểm hiển thị cần ghép từ version/events |
| UI-05 / Học ban đêm | Đơn thật/dự báo cùng ngày, paid ROAS/spend/streak; 4 ngăn nhớ, điểm bài học, hỏi xác nhận, báo cáo | API-009, 020, 022, 023, 054…058 | Có raw metrics/forecast/campaign; summary local rỗng, thiếu score và file; cần backend/view tổng hợp đúng ngày |
| UI-06 / Bằng chứng | Cặp run cùng điều kiện, 4 chỉ số HTML, số đo thật, chạy lại, tải log/trace | API-010, 031, 059…061 | Có 5 chỉ số gồm thêm lãi; chưa có HTTP tạo/gắn comparison group cho phiên UI, trace và faithful replay |

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-002 | `GET /api/state` | Bootstrap cookie/run; state, shop gốc/hiện tại, card, draft, active_package, last_night | U; session, shop D | Đã có | Chưa nối | AUTH bootstrap; FLOW state; AUDIT | Nối UI; thiếu `simulation_days` trong legacy StateView, Frontend/Data, P1 |
| API-003 | `POST /api/reset` | `{memory?,seed?}` → run mới, day 1, mode/state | U; session | Một phần | Chưa nối | AUTH idempotency/Origin; CODE legacy reset | Không xóa run cũ/memory store; chưa chọn horizon/mode qua legacy; Data/Agent/UI, P1 |
| API-004 | `POST /api/day/start` | `{}` → day/step; reference driver tạo đề xuất | U; session/run | Một phần | Chưa nối | FLOW `test_legacy_day_one_to_two`; HTTP7 | Nối orchestrator/LLM và tiến trình nền thực; Agent/Backend, P0 |
| API-005 | `GET /api/events` | `after` → events, last_seq; lọc quyền | U; session, D và sự kiện chung | Một phần | Chưa nối | AUTH cursor; FLOW; AUDIT | Thiếu opportunity/memory events trong driver mặc định, round/text/check labels theo HTML; Agent/Data/UI, P1 |
| API-006 | `POST /api/decision` | card_id, action, note_vi, edited_package, rule_answer → step/card | U; card pending D | Đã có | Chưa nối | FLOW `test_negotiate_and_reject`; WORK question confirmation | Nối nút và pending card mới sau thương lượng; UI/Agent, P0 |
| API-007 | `POST /api/content/retry` | feedback_vi → draft attempt mới, tối đa 3 bản | U; job của D/run | Một phần | Chưa nối | FLOW retry limits; AUDIT | Chưa tạo 3 ảnh khác nhau/theo feedback; cần kiểm chứng retry chỉ ảnh giữ nguyên text/video; Content/UI, P1 |
| API-008 | `POST /api/content/apply` | cover_option A/B/C → listing được duyệt | U; draft hiện tại của D/run | Đã có | Chưa nối | FLOW apply; TX worker explicit approval | Nối UI và kiểm tra media ready; Content/UI, P0 |
| API-009 | `POST /api/night` | `{}` → summary, next_day; close/settle/advance | U; session/run | Một phần | Chưa nối | FLOW local; AUDIT external 409 | External learning bị rollback handoff; sửa điều phối trước demo học thật; Data/Orchestrator, P0 |
| API-010 | `GET /api/proof` | variant? → cặp on/off của session, metrics, note | U; comparison cùng session | Một phần | Chưa nối | CODE legacy proof; AUDIT metrics rỗng | UI chưa tạo/gắn cặp đối chứng; không dùng số fixture làm kết quả đo; Data/Evaluator/UI, P0 |

- [x] UI-07: Luồng API local accept → retry → apply → night đã chạy được.
- [ ] UI-08: Cả 6 màn dùng response thật, xử lý loading/error/409 và cursor đúng.
- [ ] UI-09: Thống nhất 7 ngày; bỏ hardcode forecast 18–26, ROAS 5,2, spend 45.000đ
  và số thắng on/off. Hiển thị actual spend theo dữ liệu, không dùng trần ngân sách.
- [ ] UI-10: VI/EN, mua hàng/giỏ hàng và search trong HTML được xác định rõ là phần
  giao diện minh họa; không coi là đã có API commerce thật. Nhóm Frontend, P2.

## 3. API Agent sàn và Agent shop

Các quyền dưới đây là allowlist thực tế. P đọc projection công khai; H đọc private
của shop được cấp. Người dùng thật gọi qua backend/tool, không truy cập seed ẩn.

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-011 | `GET /api/v1/runs/{r}/shops` | Catalog, eligibility; eligible_only, phân trang | P/O/A; run, lọc shop được giao | Đã có | Chưa nối | CODE read shops/context | Nối tool chọn shop; test endpoint riêng chưa xác nhận, Agent/Data, P0 |
| API-012 | `GET /api/v1/runs/{r}/shops/{s}/context` | Public/eligibility/policies/history/metrics; private+versions theo role | P/H/U/US/O/A; run+shop | Đã có | Chưa nối | AUTH `test_platform_and_shop_projections` | Nối tool hai agent; không nhét persona vào prompt, Agent, P0 |
| API-013 | `GET /api/v1/runs/{r}/shops/{s}/products` | Product_id, verified facts, listing | P+B; run+shop | Đã có | Chưa nối | CODE read products | Nối product facts; C không được gọi route này trực tiếp, Agent/Content, P1 |
| API-014 | `GET /api/v1/runs/{r}/shops/{s}/inventory` | available_units, inventory version | B; run+shop; P bị cấm | Đã có | Chưa nối | AUTH P bị chặn; CODE inventory | Nối H/orchestrator; positive HTTP chưa có bằng chứng riêng, Agent/Data, P0 |
| API-015 | `GET /api/v1/runs/{r}/shops/{s}/costs` | as_of_day → cost/effective version | B; run+shop; P bị cấm | Đã có | Chưa nối | AUTH cross-shop/costs denied; CODE | Nối H; không gửi cost sang P, Agent, P0 |
| API-016 | `GET /api/v1/runs/{r}/shops/{s}/rules` | ShopRules + rules_version | B; run+shop; P bị cấm | Đã có | Chưa nối | WORK xác nhận luật; AUTH P denied | Nối H đọc lại sau confirmation, Agent, P0 |
| API-017 | `GET /api/v1/runs/{r}/policies` | Fee/platform rule versions | P+B+C; run | Đã có | Chưa nối | CODE policies; SEED phí | Test HTTP/tools riêng; Agent/Data, P1 |
| API-018 | `GET /api/v1/runs/{r}/market/observations` | from_date/to_date, keyword → observed demand/benchmarks | P/O/A; run; H bị cấm | Đã có | Chưa nối | AUTH future bound, H denied | Nối tìm cơ hội, Agent, P0 |
| API-019 | `GET /api/v1/runs/{r}/market/summary` | Approved trend/keyword/as_of_date/CPC | P+B; run | Đã có | Chưa nối | CODE market_summary | Nối UI/agent; summary hiện trend +240% cố định, chưa phải phép tính từ chuỗi observation, Data/Agent, P1 |
| API-020 | `GET /api/v1/runs/{r}/shops/{s}/metrics` | channel/date/cursor → seeded/simulated rows; tài chính chỉ B | P+B; run+shop | Đã có | Chưa nối | AUTH cursor; SEED; AUDIT | Nối tool; lọc source/day khi tính học/proof, Agent/Data, P0 |
| API-021 | `GET /api/v1/runs/{r}/shops/{s}/history` | Proposals/shared history, private evaluation chỉ B | P+B; run+shop | Một phần | Chưa nối | CODE history/shared_proposal; FLOW proposals | Đây là lịch sử proposals, không tự là public memory của gói đã áp dụng; kết hợp campaigns và owner memory, Agent, P1 |
| API-022 | `GET /api/v1/runs/{r}/shops/{s}/campaigns` | Package snapshot, status/spend; B có streak, approval/versions | P+B; run+shop; P dùng allowlist trường | Đã có | Chưa nối | CODE read campaigns; AUDIT | Nối renewal/stop và view ban đêm, Agent/UI, P1 |
| API-023 | `GET /api/v1/runs/{r}/shops/{s}/forecasts` | proposal_id? → raw/daily/period forecast snapshots | P+B; run+shop | Đã có | Chưa nối | CODE; AUDIT; CAL snapshot | Nối đúng applied proposal và cùng grain ngày, Agent/Data, P1 |
| API-024 | `GET /api/v1/runs/{r}/proposals/{pid}` | Package, parent, stance, round, forecast_id; private evaluation chỉ B | P+B; run+shop của proposal | Đã có | Chưa nối | CODE shared_proposal | Nối tool đọc turn; positive HTTP riêng chưa xác nhận, Agent, P0 |
| API-025 | `POST /api/v1/runs/{r}/shops/{s}/checks` | product_id+package → passed/checks/versions | P/H; run+shop | Một phần | Chưa nối | CODE checks; SEED check tính thuần | P hiện chỉ kiểm stock cho ads, H kiểm tài chính/luật; bổ sung test HTTP theo hợp đồng, Data/Agent, P0 |
| API-026 | `POST /api/v1/runs/{r}/shops/{s}/proposals` | negotiation_id, parent, stance, package, shared_reason → proposal | P/H; run+shop, đúng lượt, tối đa 3 lượt P | Đã có | Chưa nối | CODE create_proposal; FLOW reference driver | Test two-agent HTTP thật/fake tách principal; prompt/LLM chưa nối, Agent, P0 |
| API-027 | `POST /api/v1/runs/{r}/knowledge/search` | query/product_id/types/top_k → snippets và provenance | P/H/U/C/O/L; run, product scope nếu truyền | Một phần | Chưa nối | WORK `test_local_knowledge_and_revocation` | Keyword local; chưa vector/provider; xác minh private collections theo mọi role, Data/Agent, P1 |
| API-028 | `GET /api/v1/runs/{r}/knowledge/documents/{did}` | version → tài liệu đang hiệu lực, nhãn simulated | T; shared theo run, private thêm B+owner run/shop | Đã có | Chưa nối | WORK revoked trả 404; CODE document | Test đọc positive/private roles; worker dùng product document thay route products, Data/Content, P1 |
| API-029 | `POST /internal/v1/knowledge/documents` | Metadata/version/scope/source_object_key/checksum → index ready | K; nguồn hợp lệ, private thêm owner run/shop | Đã có | Chưa kiểm chứng | CODE KnowledgeCreate/knowledge_create | Chưa có test create HTTP riêng; cần đường đưa source vào storage có quản lý, Data/Knowledge, P2 |
| API-030 | `POST /internal/v1/knowledge/documents/{did}/revoke` | document_version, reason_vi → revoked | K; quản trị document/version toàn cục | Đã có | Đã kiểm chứng | WORK `test_local_knowledge_and_revocation` | Kiểm chứng local; chưa có admin UI/cloud index, Data/Knowledge, P2 |

- [x] AG-01: Context của P không trả vốn, lãi tối thiểu, private evaluation hoặc persona;
  H được đọc private của D, không được đọc private A khi chỉ cấp D (AUTH).
- [ ] AG-02: Hai agent chạy bằng tool HTTP đúng lượt, phản đề xuất rồi chấp nhận;
  shared_reason qua redact, không có bí mật trong event/error/search.
- [ ] AG-03: Mở đầu gia hạn bằng gói đã áp dụng và đọc learned memory do team Agent
  sở hữu; không coi lịch sử proposals là thuật toán học đã hoàn tất.

## 4. Orchestrator: thương lượng, trình thẻ, áp gói, điều phối ngày

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-031 | `POST /api/v1/runs` | scenario_version, seed, mode, memory_enabled, simulation_days → run | U/O/E/A; tạo session/run, caller cần quyền đọc run mới | Đã có | Chưa kiểm chứng | CODE RunCreate/create_run; FLOW tạo run qua service | Test HTTP create và cấp scope cho service-created run; live hiện 503, Data/Orchestrator, P0 |
| API-032 | `GET /api/v1/runs/{r}` | Day, horizon, phase, mode, memory flag, version | T; run | Đã có | Đã kiểm chứng | WORK external learning đọc run/version | Kiểm chứng worker giả; nối orchestrator thật, Backend, P0 |
| API-033 | `POST /api/v1/runs/{r}/reset` | expected_version → run mới, giữ cấu hình | U; run/session | Đã có | Chưa kiểm chứng | CODE reset | Test v1 reset/retry và quyền run mới; không xóa audit, Data, P1 |
| API-034 | `GET /api/v1/runs/{r}/state` | shop_id? → run, shop, pending_cards, jobs | U/O; run+shop | Đã có | Chưa kiểm chứng | CODE read state | Không phải legacy StateView; test polling/shape riêng, Data/Orchestrator, P1 |
| API-035 | `POST /internal/v1/runs/{r}/shops/{s}/negotiations` | day, expected_shop_version, kind, owner_note, source_card → negotiation | O/A; run+shop, cooldown/stock/no active package | Đã có | Chưa nối | CODE new_negotiation; FLOW reference driver | Nối orchestrator, test HTTP lượt/scope/cooldown, Backend/Agent, P0 |
| API-036 | `POST /api/v1/runs/{r}/proposals/{pid}/present` | expected_version → pending seller card | O/A; run+shop, final agreed/validated proposal | Đã có | Chưa nối | CODE present; FLOW reference driver | Nối pause/resume chờ seller ngoài DB transaction, Backend, P0 |
| API-037 | `POST /api/v1/runs/{r}/decisions` | target_type/id/version, action, package edit/cover/rule answer → decision | U/US; run+shop; agent không được duyệt | Đã có | Đã kiểm chứng | TX `test_concurrent_apply_different_keys_has_one_business_effect`; WORK/legacy | Kiểm chứng local; nối seller UI/simulator thật, Backend/UI, P0 |
| API-038 | `POST /api/v1/runs/{r}/campaigns/apply` | proposal+approval+inventory/rules versions → campaign | O/A; run+shop, đúng approval, không active package khác | Đã có | Chưa nối | TX apply đồng thời kiểm service; FLOW legacy | Thêm test HTTP v1 riêng và nối orchestrator thật, Backend/Data, P0 |
| API-039 | `POST /api/v1/runs/{r}/days/start` | expected_day/version → operation | U/O/A; run | Một phần | Chưa nối | CODE operation; FLOW legacy/reference | Handler vẫn tự chạy reference driver, chưa phải hook agent ngoài; Backend/Agent, P0 |
| API-040 | `POST /api/v1/runs/{r}/days/close` | expected_day/version → settle 5 shop và learning handoff | U/O/A; run | Đã có | Đã kiểm chứng | WORK `test_external_learning_blocks_advance_and_accepts_result` | Kiểm chứng worker giả; nối job dispatch thật, Backend/Agent, P0 |
| API-041 | `POST /api/v1/runs/{r}/days/advance` | expected_day/version → next day hoặc complete | U/O/A; run, handoff completed/skipped | Đã có | Đã kiểm chứng | WORK advance bị chặn rồi thành công; FLOW no day 8 | Worker thật phải hoàn thành trước advance; Backend, P0 |
| API-042 | `GET /api/v1/runs/{r}/operations/{oid}` | Operation kind/day/status/result/error | U/O/A; run | Đã có | Chưa kiểm chứng | CODE operation read | Test HTTP/ownership và operation thất bại; hiện command chủ yếu hoàn tất đồng bộ, Data/Backend, P1 |

- [x] ORCH-01: Apply đồng thời khác idempotency key vẫn chỉ tạo một campaign (TX).
- [x] ORCH-02: V1 external close → chặn advance → worker giả result → advance (WORK).
- [ ] ORCH-03: Chạy trọn luồng với hai agent bên ngoài, không bị reference driver
  tạo thêm đề xuất hoặc giữ transaction khi chờ provider/seller.

## 5. Content worker, file, duyệt và xuất bản

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-043 | `GET /api/v1/runs/{r}/shops/{s}/content` | Content versions, parent, A/B/C, status, feedback | B+C; run+shop | Đã có | Chưa kiểm chứng | CODE read content | C route này hiện kiểm shop, không lọc assigned job; kiểm tra có cần thu hẹp trước cấp worker thật, Data/Content, P1 |
| API-044 | `POST /api/v1/runs/{r}/shops/{s}/content-jobs` | Applied proposal/product, assets, feedback, current attempt → job | O/U; run+shop; phải có approved/applied content_refresh | Đã có | Chưa nối | CODE content_create; FLOW legacy; WORK worker mode | Nối dispatch job, selective retry và product brief đủ dữ liệu, Backend/Content, P0 |
| API-045 | `GET /api/v1/runs/{r}/content-jobs/{jid}` | Brief, assets, attempt, feedback, job version/status | B+C; run+shop; C thêm assigned job | Đã có | Chưa nối | CODE read job; WORK assignment chủ yếu test result | Test GET assigned/unassigned; chưa có queue/claim HTTP, job ID do orchestrator cấp, Content/Data, P0 |
| API-046 | `POST /internal/v1/runs/{r}/content-jobs/{jid}/result` | expected_job_version, status, candidates/provider/error → job/content | C; run+shop+assigned job | Đã có | Đã kiểm chứng | TX worker valid result; WORK bad claims/lease | Worker giả; provider thật chưa nối, Content, P0 |
| API-047 | `POST /api/v1/runs/{r}/assets/uploads` | product_id?, kind, MIME, size, SHA-256 → upload URL | U/C/L/O; run; media thêm shop; L chỉ document không product | Đã có | Đã kiểm chứng | FLOW `test_upload_authorization_checksum_and_traversal` | Test riêng upload report L; job scope chưa được kiểm ở create upload, Data/Content, P1 |
| API-048 | `PUT /api/v1/runs/{r}/assets/{aid}/bytes` | Raw bytes đúng type/size/hash, upload ≤5 phút | T; run+shop/visibility+owner, pending | Đã có | Đã kiểm chứng | FLOW upload bytes/checksum | MIME chỉ kiểm signature; thêm test expiry/corrupt media nếu yêu cầu decode, Data/Content, P1 |
| API-049 | `POST /api/v1/runs/{r}/assets/{aid}/complete` | checksum → ready sau kiểm file lưu | T; run+shop/visibility+owner | Đã có | Đã kiểm chứng | FLOW complete | Thêm expiry/race tests; không suy ra signed URL cloud đã có, Data, P1 |
| API-050 | `GET /api/v1/runs/{r}/assets/{aid}/download` | Stream image/video/document ready | T; run+shop+visibility; P chỉ published | Đã có | Đã kiểm chứng | FLOW private download denied; AUTH scope | File memory internal hiện U không đọc được, cần projection/ACL báo cáo an toàn; Data/Agent, P1 |
| API-051 | `POST /api/v1/runs/{r}/content/{cid}/publish` | approval_decision_id, expected_active_content_id → listing | O; run+shop, đúng content version/ready cover | Đã có | Chưa nối | TX explicit approval kiểm legacy/service; CODE publish | Test HTTP riêng, media thật và undo seed/old published; Data/Content, P1 |

- [x] CONTENT-01: Worker giả trả kết quả không tự publish; phải có seller approval (TX).
- [x] CONTENT-02: Ba bản tổng cộng; job quá lease fallback và job khác assignment
  bị từ chối theo tình huống đã test (FLOW, WORK).
- [ ] CONTENT-03: Ba cover khác nhau, nền sáng theo góp ý; nguồn đủ ảnh/facts,
  video đúng duration hoặc fallback có nhãn rõ, tải qua API có quyền.
- [ ] CONTENT-04: Retry chỉ ảnh giữ nguyên title/description/video đã chấp nhận;
  bản cũ trả muộn không thay bản mới, không gọi paid job lặp ngoài kiểm soát.

## 6. Simulator: settlement, tồn kho, ngân sách, ROAS và tự dừng

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-052 | `POST /internal/v1/runs/{r}/shops/{s}/settle-day` | day, expected_inventory_version, snapshot hash? → settlement; code tính metrics/kho/spend/events | M/O/A; run+shop, ngày hiện tại, không card/draft chờ | Đã có | Chưa nối | TX rollback qua service; FLOW 7 ngày qua driver | Chưa có HTTP test riêng cho M; nối simulator tool và kiểm input conflict, Data/Simulator, P0 |
| API-053 | `POST /api/v1/runs/{r}/campaigns/{cid}/pause` | expected_version, reason_code → ads paused | U/O/N; run+shop; O/N cần bằng chứng đủ điều kiện | Đã có | Chưa kiểm chứng | CODE pause; FLOW có settlement chạy nhiều ngày | Test LOW_ROAS/LOW_STOCK/RULE_TIGHTENED/SELLER_REQUEST qua HTTP, Data/Simulator, P1 |

| ID | Yêu cầu số liệu / bất biến | API / bên dùng | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- |
| SIM-01 | Organic/paid riêng; ROAS = paid revenue / paid actual spend; không chi trả null | API-020, 052; Agent/UI | Đã có | Đã kiểm chứng | SEED paid history null; FLOW 7 ngày; CODE channel_metrics | Thêm assertion ROAS runtime/rounding độc lập, Data, P1 |
| SIM-02 | Không âm kho, không vượt budget; settle lặp không trừ hai lần | API-038, 052 | Đã có | Đã kiểm chứng | FLOW 7 ngày không âm kho; TX rollback; CODE old settlement/approved cap | HTTP concurrent settle/retry riêng chưa có, Data, P1 |
| SIM-03 | Hai ngày ROAS thấp thì dừng trước chi ngày sau; voucher/content giữ | API-022, 052, 053 | Đã có | Chưa kiểm chứng | CODE settle/pause; không có test chuyên biệt xác nhận toàn bộ stop behavior | Thêm nghiệm thu hai ngày thấp và ngày kế không chi, Simulator/Data, P1 |
| SIM-04 | Forecast daily/period cùng grain; calibration dùng snapshot trước kết quả | API-023; callback calibration | Đã có | Đã kiểm chứng | CAL; CODE forecast/evidence | Memory thật chưa nối; không so forecast 3 ngày với đơn một ngày, Agent/Data, P1 |

- [x] SIM-05: Reference run hoàn tất 35 shop-day settlements, 70 operating channel rows.
- [ ] SIM-06: Chứng minh qua HTTP dừng ads, hết hạn voucher, không cộng dồn quality
  gain khi gia hạn; tách test chuyên biệt khỏi việc chỉ chạy hết 7 ngày.

## 7. Learning worker: bằng chứng, sở thích, calibration và báo cáo

Memory store, public history học được, preferences và lesson/calibration state do
team Agent sở hữu. Data API lưu bằng chứng, xác nhận luật và completion envelope;
không có general memory CRUD HTTP. Không ghi thêm learned rows vào seed để tạo thắng.

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-054 | `GET /internal/v1/runs/{r}/learning-input` | day → settlement_cursor, metrics, forecasts, proposals, decisions, feedback | L; run+assigned shops; phải có handoff | Đã có | Đã kiểm chứng | WORK `test_external_learning_blocks_advance_and_accepts_result` | Worker giả; thêm negative scope/date/cursor tests và nối store thật, Agent/Data, P0 |
| API-055 | `POST /internal/v1/runs/{r}/learning-results` | day/cursor/status/night_summary/report asset → terminal handoff | L; run; report visibility/asset access; evidence thuộc run | Đã có | Đã kiểm chứng | WORK external result/path sanitized | Worker giả; test conflicting retry, partial failure; cần kiểm tra summary không mang private của shop ngoài scope, Agent/Data, P0 |
| API-056 | `POST /internal/v1/runs/{r}/shops/{s}/rule-questions` | external_pref_id, field/value/text, based_on_rules_version → pending question | L/O; run+shop, memory enabled | Đã có | Đã kiểm chứng | WORK confirmation, decline silence, memory off | Hiện câu hỏi do test gửi tay; nối phát hiện preference thật, Agent, P1 |
| API-057 | `GET /api/v1/runs/{r}/shops/{s}/rule-questions` | Pending/answered questions; status/cursor | B; run+shop | Đã có | Chưa nối | CODE questions; AUTH P denied | Test positive HTTP/list và UI hiển thị câu hỏi, Agent/Data/UI, P1 |
| API-058 | `PUT /api/v1/runs/{r}/shops/{s}/rules` | expected_rules_version, confirmation_decision_id, rules → confirmed rules | U/US; run+shop, đúng decision đã apply field | Đã có | Chưa kiểm chứng | CODE rules update; WORK xác nhận qua decisions | Route xác minh kết quả đã ghi bởi decision, không cho sửa luật tùy ý; thêm HTTP test, Data/UI, P1 |

| ID | Yêu cầu dữ liệu / hành vi | Interface và bên dùng | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- |
| LEARN-01 | Bốn ngăn nhớ thực sự cập nhật và được agent đọc sáng sau | API-054/055 + agent-owned store | Một phần | Chưa nối | CODE default skipped; AUDIT summary rỗng | Nối public history/preferences/calibration/lessons, Agent, P0 |
| LEARN-02 | Calibration version/as_of_day/points/factor/quantiles; ≥5 points | `create_app(calibration_provider=...)`, Python callback đọc nhanh | Đã có | Đã kiểm chứng | CAL `test_calibration_view_is_scoped_past_only_and_memory_off_bypasses_it` | Không có HTTP calibration endpoint; nối callback vào memory owner, Agent/Backend, P1 |
| LEARN-03 | Lesson op, evidence, rejected count và điểm như HTML | NightSummary/LessonOp trong API-055 | Một phần | Chưa nối | CODE models: có op/evidence, không có score | Chốt view điểm với Agent rồi bổ sung interface; không tự đổi contract trong bảng kiểm, Agent/Data, P1 |
| LEARN-04 | memory_day_N.md người bán mở được, không lộ private shop khác | API-047…050, 055; L tạo, U xem | Một phần | Chưa nối | CODE upload report internal; asset_access không cho U đọc internal | Sinh report và tạo projection/ACL seller-safe; không chỉ điền URL vào summary, Agent/Data, P1 |
| LEARN-05 | Decline preference im lặng 14 ngày; memory-off không học | API-056, 037, 058 | Một phần | Đã kiểm chứng | WORK decline/memory off; run chỉ 7 ngày | Đã chặn hỏi lại trong run; chưa chứng minh hết 14 ngày cho run dài hơn, Agent/Data, P2 |

- [x] LEARN-06: Luật chỉ đổi sau xác nhận seller trong ca đã test; memory-off chặn
  preference write; v1 chặn advance khi handoff pending (WORK).
- [ ] LEARN-07: `/api/night` external hoạt động, không rollback mất handoff; worker
  xử lý cùng cursor một lần, restart/timeout không báo học thành công giả.
- [ ] LEARN-08: Sáng hôm sau agent thực sự dùng memory đã commit; số liệu chứng minh
  tác dụng được đo từ run, không gắn lợi ích vào cờ memory trong công thức thị trường.

## 8. Đối chứng, proof, replay, nhật ký và trace

| ID | API | Dữ liệu đọc/ghi | Bên gọi và phạm vi | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-059 | `GET /api/v1/runs/{r}/proof` | group_id, variant full_7d/legacy_6d → 5 metrics on/off, note | T; phải được đọc cả hai run của group; không có allowlist E riêng ở handler | Đã có | Chưa nối | FLOW proof tính qua Python; CODE proof | Test HTTP read pair/scope, evaluator tạo group cho browser, Data/Evaluator, P0 |
| API-060 | `GET /api/v1/runs/{r}/events` | after_seq/limit → event rows, next_cursor, has_more | T; run, shop allowlist, visibility/role projection | Một phần | Đã kiểm chứng | AUTH invisible cursor; CODE events | Local cursor có test; event nội dung chưa đủ HTML, cần role matrix export/poll, Data/Agent, P1 |
| API-061 | `POST /internal/v1/runs/{r}/replay/export` | `{}` → sanitized events, final snapshots/assets, reference label | O/E/A; run | Một phần | Chưa kiểm chứng | CODE replay_export; có CLI export-replay | Chưa có HTTP test riêng; chưa có LLM recording/player hoặc seller download, Backend/Evaluator, P1 |

| ID | Yêu cầu | Interface / bên dùng | API | Tích hợp | Bằng chứng | Còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- | --- |
| PROOF-01 | Tạo cặp cùng seed/scenario/horizon, gắn vào session UI | CLI run-scenario --compare; Python compare | Một phần | Chưa nối | FLOW compare local; API-010 session mới rỗng | Chưa có HTTP command tạo/gắn cặp; cần kiểm điều kiện so sánh đầy đủ, Data/Evaluator, P0 |
| PROOF-02 | Chỉ số ngày 4–6; tổng tiền 7 ngày; null khi thiếu mẫu | Python proof, API-059/010 | Đã có | Đã kiểm chứng | FLOW test_seven_day_reproducibility_and_no_fake_learning | Reference on/off bằng nhau; chưa có bằng chứng learned improvement, Evaluator/Agent, P0 |
| PROOF-03 | Tải log mà không lộ private | API-005/060 phân trang; internal API-061 | Một phần | Chưa nối | CODE projection; AUTH cursor | UI có thể tạo file từ event được phép; chưa có seller export riêng, Data/UI, P2 |
| PROOF-04 | Phát lại lần chạy LLM đã ghi, đúng nhánh/quyết định | mode replay + recording/player | Một phần | Chưa nối | CODE replay_export `faithful_llm_replay=false` | Replay hiện reference fallback; không hiển thị “phát lại bản chạy thật”, Agent/Backend/UI, P1 |
| PROOF-05 | Trace link Langfuse an toàn | Chưa có trace URL/endpoint | Chưa có | Chưa nối | CODE không có trace route/response field | Nối tracing và quyền xem trace nếu giữ nút HTML, Backend/UI, P2 |

- [x] PROOF-06: Hai reference runs cùng seed có outcomes bằng nhau; report ghi chưa
  nối học, không giả thắng; có labeled legacy_6d (FLOW).
- [ ] PROOF-07: Từ cùng phiên trình duyệt tạo/chọn cặp, chờ hoàn tất, đọc proof,
  tải log, reset mà không mất quyền truy cập bằng chứng cũ.

## 9. Phân quyền, idempotency, phiên bản, rollback và recovery

Đây là kiểm tra xuyên API, không bổ sung operations ngoài 61 route đã liệt kê.

| ID | Tiêu chí / API liên quan | API | Tích hợp | Bằng chứng | Việc còn thiếu / phụ trách / ưu tiên |
| --- | --- | --- | --- | --- | --- |
| SEC-01 | Auth và cô lập session/run/shop; API-002, 012, 015, 032 | Đã có | Đã kiểm chứng | AUTH: session/run isolation, platform/shop projections | Bổ sung matrix toàn bộ roles/routes; không suy ra coverage 61/61, Data, P1 |
| SEC-02 | Cookie HttpOnly/SameSite, Origin; token hash, backend-only | Đã có | Đã kiểm chứng | AUTH bootstrap/idempotency_csrf; CODE identity/token | Sign-in/cloud/proxy chưa nối, Backend, P2 |
| SEC-03 | Command retry cùng key giữ kết quả; đổi body 409 | Đã có | Đã kiểm chứng | AUTH; FLOW night retry; TX apply đồng thời | HTTP concurrency cho settle/publish chưa có, Data, P1 |
| SEC-04 | Expected version và đúng approval; agent không tự chi/publish/đổi luật | Đã có | Đã kiểm chứng | TX approval; WORK question confirmation; CODE scope | Hoàn thiện negative HTTP cases từng command, Data/Agent, P1 |
| SEC-05 | Rollback giữ nguyên kho/metrics/events khi lỗi giữa transaction | Đã có | Đã kiểm chứng | TX failed_settlement; FLOW atomic rollback/concurrent_events | Cloud adapter chưa có, Data, P1 |
| SEC-06 | Cursor gắn query/actor, không đọc tương lai; không bỏ lặp vì event ẩn | Đã có | Đã kiểm chứng | AUTH future_data/bound_cursor/invisible cursor | Kiểm đầy đủ date/day inputs còn lại; Data, P1 |
| SEC-07 | Lease recovery: worker muộn/timeout không publish ngầm/gọi trả phí lại | Đã có | Đã kiểm chứng | WORK worker_job_assignment_bad_claims_and_lease_recovery; CODE recover | Test restart/late-result và learning timeout riêng; Backend/Content/Agent, P1 |
| SEC-08 | Upload/download đúng run/shop/owner/job/visibility và path an toàn | Một phần | Chưa kiểm chứng | FLOW một số scope/hash/traversal; CODE media | Job binding chưa xuyên suốt content list/upload; seller report internal bị chặn; Data, P1 |
| SEC-09 | Summary/lesson/trace/export không lộ private shop khác | Một phần | Chưa kiểm chứng | AUTH context/events; SEED redact; CODE learning result/proof | Kiểm soát free text summary và pair financial proof theo audience; Data/Agent, P1 |
| SEC-10 | Lifecycle event đúng writer/visibility, schema và provenance | Một phần | Chưa kiểm chứng | CODE event ghi qua helper, payload còn generic | Allowlist/schema event, round/code labels, opportunity/memory events cần hoàn thiện; Data/Agent, P1 |

- [x] SEC-11: Các ca auth, transaction, cursor và worker giả nêu trên có test local.
- [ ] SEC-12: Đạt toàn bộ role matrix và E2E thật; không dùng test context pass làm
  bằng chứng mọi API/report/proof đã đáp ứng phân quyền.

## 10. Danh sách khoảng trống để giao việc

Các dòng dưới là chức năng còn thiếu hoặc chưa hoàn chỉnh; **không phải endpoint
đã được triển khai**, không áp đặt URL/schema mới trước khi team chốt contract.

| ID | Khoảng trống | API / tích hợp | Hướng xử lý và nhóm phụ trách | Ưu tiên |
| --- | --- | --- | --- | --- |
| GAP-01 | Legacy night với external learning trả 409, rollback mất handoff | Một phần / Chưa nối | Tách close/chờ worker/advance khỏi một transaction; hoặc adapter UI dùng v1 lifecycle; Data/Orchestrator | P0 |
| GAP-02 | HTTP tạo/gắn comparison group và job đối chứng cho session UI | Chưa có / Chưa nối | Thêm command có quyền, trạng thái và kiểm hai run tương đương; Data/Evaluator | P0 |
| GAP-03 | Public history/preferences/calibration/lessons chưa được học và đọc ngày sau | Một phần / Chưa nối | Agent-owned store + worker + tool đọc memory; không mở general memory CRUD chỉ để điền màn hình; Agent | P0 |
| GAP-04 | Start_day vẫn chạy reference driver, chưa dispatch hai agent ngoài | Một phần / Chưa nối | Chốt adapter orchestrator, tránh tạo trùng negotiation; Backend/Agent | P0 |
| GAP-05 | A/B/C cùng ảnh placeholder; không có video 15 giây; thiếu nguồn 4 ảnh | Một phần / Chưa nối | Cung cấp media/source đúng nhãn và nối content worker/provider; Content/Data | P1 |
| GAP-06 | Hoàn tác listing, nhất là quay lại seed chưa có cover_options | Một phần / Chưa kiểm chứng | Command approval/version/audit rõ; không lấy reset toàn run thay undo; Data/Content | P1 |
| GAP-07 | Hậu trường thiếu opportunity/memory events, lượt, lời giải thích và checks rõ | Một phần / Chưa nối | Chuẩn hóa event projections, bổ sung producer, map UI; Data/Agent/UI | P1 |
| GAP-08 | Lesson summary không có score; không có report memory thật | Một phần / Chưa nối | Chốt summary view và report do worker tạo; Agent/Data | P1 |
| GAP-09 | Report upload internal không cho seller tải qua URL được trả | Một phần / Chưa nối | Tạo report projection riêng cho seller với ACL đúng; giữ private shop khác kín; Data/Agent | P1 |
| GAP-10 | HTML 6 ngày nhưng default 7; state legacy thiếu horizon | Một phần / Chưa nối | Giữ thiết kế 7 ngày, bổ sung metadata và UI; legacy_6d phải ghi nhãn; Data/UI | P1 |
| GAP-11 | Số mẫu HTML khác số đo; reset label và replay label chưa đúng | Một phần / Chưa nối | Thay hardcode bằng response; lãi D 27.136đ, forecast audit 21–39/point29 chỉ là snapshot; UI/Data | P1 |
| GAP-12 | Chưa ghi/phát lại LLM thật, chưa trace URL và seller log download flow | Một phần / Chưa nối | Nối recording/player/tracing; log có thể xuất từ pagination; Backend/UI/Evaluator | P1 cho replay; P2 cho trace/log UI |
| GAP-13 | Job scope ở list content/upload chưa đồng nhất; HTTP test chưa phủ mọi route | Một phần / Chưa kiểm chứng | Kiểm role matrix, giữ quyền tối thiểu trước nối worker thật; Data | P1 |

## 11. Checklist nghiệm thu theo kịch bản

Các mục AT là nghiệm thu tích hợp thật nên chưa đánh dấu hoàn tất bằng kết quả
reference/worker giả. Chạy trên DB/run mới, cùng seed 42; không dùng production
token hoặc gọi paid provider trong suite tự động. Ghi ngày, run IDs, profile,
người/nhóm kiểm tra và đường dẫn bằng chứng khi đánh dấu.

- [ ] **AT-01 / Khởi tạo:** UI bootstrap, hiện đúng shop D, facts/trend/rules theo
  quyền; reset tạo run mới ngày 1, giữ audit và thông báo đúng; owner Agent xử lý
  reset memory ngoài nếu yêu cầu. Liên quan UI-01, DATA-02/03, API-002/003/019.
- [ ] **AT-02 / Accept:** Agent sàn đề xuất 70k/10%, shop phản đề xuất hợp luật;
  thẻ đúng snapshot/version; trước approval không chi; sau accept chỉ áp một gói.
  Kiểm token P không thấy private checks/cost. Liên quan API-025/026/035…038.
- [ ] **AT-03 / Negotiate:** Seller góp ý giảm voucher 2%; sinh thẻ mới đúng yêu
  cầu, card cũ không duyệt lại; tối đa hai lần thương lượng thêm. API-006/035.
- [ ] **AT-04 / Reject:** Không áp campaign; UI vẫn kết thúc ngày được; cooldown
  được tôn trọng ở ngày sau. API-006/039/040.
- [ ] **AT-05 / Content:** Feedback nền sáng tạo 3 lựa chọn khác nhau; retry tối đa
  3 bản tổng cộng; chọn B, approval rồi publish; không đổi text/video khi chỉ yêu
  cầu ảnh. Worker quá hạn/late result xử lý đúng, media không ready bị chặn.
  Liên quan API-007/008/043…051 và GAP-05.
- [ ] **AT-06 / Undo:** Xem trước/sau và hoàn tác bản seed hoặc published version
  cũ có xác nhận; không tự bật lại/tăng chi campaign; audit đầy đủ. GAP-06.
- [ ] **AT-07 / Thị trường:** Kết thúc ngày ghi đúng 5 settlements; kho và ngân
  sách không âm/vượt; retry không trừ lặp; hiển thị paid ROAS/spend và daily
  forecast cùng ngày; hai ngày thấp thì hôm sau không chi, voucher còn theo hạn.
  Liên quan API-020/022/023/052/053.
- [ ] **AT-08 / Sở thích:** Feedback thành candidate, sáng sau hỏi seller; Có mới
  đổi rules_version, Không không hỏi lại trong run; memory-off không học nhưng
  hard rules/stop vẫn chạy. Liên quan API-037/056…058.
- [ ] **AT-09 / External night:** Từ UI close → handoff bền vững → worker học và
  ghi store → result đúng cursor → advance một lần. Lỗi/timeout có nhãn, không
  mất handoff hoặc giả completed. API-009/040/041/054/055, GAP-01.
- [ ] **AT-10 / Memory thật:** Báo cáo có public history, preferences, calibration
  samples, lesson score/evidence/rejected count đúng thực tế; seller tải được
  report an toàn; sáng sau hai agent dùng đúng memory view. LEARN-01…04.
- [ ] **AT-11 / Đối chứng:** Cùng session UI tạo/chọn hai run cùng điều kiện, khác
  memory flag; tính proof từ operating outcomes; chưa học hoặc kết quả thua vẫn
  hiển thị trung thực; thiếu mẫu là null/omission có giải thích. API-010/059,
  GAP-02; kiểm scope cả hai run.
- [ ] **AT-12 / Ngày cuối:** Hoàn tất ngày 7 có next_day=null, step=complete;
  refresh/retry/restart không sinh ngày 8 hoặc chi thêm. Có metadata horizon;
  báo cáo 6 ngày chỉ khi chọn variant ghi nhãn. API-009/032/041.
- [ ] **AT-13 / Nhật ký và replay:** Tải đủ log phân trang theo quyền; trace/replay
  chỉ bật khi có dữ liệu thật; không ghi nhãn reference fallback là LLM recording.
  API-005/060/061, GAP-07/12.
- [ ] **AT-14 / API ngoài UI:** Two-agent HTTP loop và content/learning worker thật
  chạy với token hẹp; cross-run/shop/job/private-report bị từ chối; không trao
  wildcard token cho frontend. API-011…061 và SEC-01…10.

## 12. Kết quả kiểm tra và cách duy trì

Lệnh kiểm tra hiện có, chạy từ gốc repo bằng môi trường uv riêng:

```bash
uv run --project data pytest -c data/pyproject.toml data/tests -q
```

**Kết quả gần nhất: 32 passed, 1 warning** về Starlette TestClient/httpx. Đây là
suite local với fake client/worker; không chứng minh agent LLM, provider, UI và
memory store thật đã nối, cũng không có nghĩa cả 61 endpoint đều có test HTTP
riêng. Không thêm test mới hoặc sửa code/schema/dataset trong công việc lập bảng kiểm.

| Kiểm tra | Kết quả và giới hạn |
| --- | --- |
| Inventory OpenAPI so với API-001…061 | Đã đối chiếu khớp 61/61 cặp method/path và 61 ID duy nhất, không thiếu/trùng; không tính `/docs`, `/redoc`, `/openapi.json` tự sinh |
| Bằng chứng code/test | Link tương đối, tên test và profile rõ; CODE-only không đánh dấu đã kiểm chứng |
| HTML | Đọc 6 embedded templates; ghi rõ 6 ngày/placeholder numbers khác service, không sửa HTML trong đợt này |
| AUDIT night/content/proof | Kết quả đã quan sát trên DB tạm; external night 409 là lỗi còn mở, không phải acceptance pass |
| Phạm vi thay đổi | Đã so SHA-256 trước/sau: chỉ checklist, README và PROGRESS thay đổi trong data/; design/code/schema/dataset giữ nguyên |

Khi thay API hoặc nối module, cập nhật dòng API tương ứng, GAP/AT liên quan và
bằng chứng. Giữ ID ổn định. Nếu thêm operation, thêm ID mới và kiểm lại tổng số.
README là hướng dẫn dùng; PROGRESS là nhật ký; bảng này là nơi theo dõi khả năng
đáp ứng demo và nghiệm thu giữa các thành viên.
