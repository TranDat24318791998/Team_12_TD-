# Recheck UI sau commit [3.4]

What this change does: Bản sửa nối giao diện với kết quả thật do Data trả về, giữ riêng phiên hiện tại, báo cáo đối chứng đã lưu và bản xem trước. Demo D dùng yêu cầu cố định **đạt 24 đơn trong 3 ngày, quảng cáo tối đa 45.000đ/ngày**, vẫn cần người bán bấm xác nhận; logo ShopPilot AI dùng đúng ảnh người dùng cung cấp.

**Verdict: Ship trong phạm vi demo local một seller D.** Không còn finding chức năng hoặc branding ở frontend đã freeze. Khoảng thiếu logo tại nhận diện shop được gửi owner trong lúc review và đã sửa trước các kiểm tra cuối.

## Phạm vi và mốc code

- Review độc lập Astra max ngày 31/10/2026, đọc `AGENTS.md`, plan tích hợp, hai requirements và hai báo cáo `COMMIT_3_4_*_REVIEW.md`.
- Đối chiếu commit gốc `bd78f8e` với frontend hiện tại: `e272ae2` cộng phần cuối chưa commit tại `Product.jsx`, CSS, bundle và tests để thêm logo cho shop D. HEAD chuyển từ `65434cb` sang `e272ae2` trong lúc review do thay đổi bên ngoài; reviewer không commit, reset hoặc amend.
- Chỉ đọc source; mọi run/mutation kiểm thử dùng SQLite tạm. Browser là Chrome headless riêng, profile tạm và server loopback riêng; không dùng browser đang mở của người dùng hoặc ghi vào app production 8000.
- Bản chỉnh nhỏ riêng của Data để dịch thông điệp validator sang tiếng Việt do backend reviewer/root kiểm tiếp; không thay shape HTTP hoặc frontend đã freeze được nghiệm thu ở đây.

## Các đầu nối đã kiểm lại

| Yêu cầu / lỗi cũ | Kết quả trên bản sửa |
| --- | --- |
| Check cuối mất `ok`, UI báo lỗi cho gói hợp lệ | Native worker → HTTP events → `deriveActivity` → `AgentActivity` thật giữ `ok`, proposal và round. Test tái hiện gói fail trước khi sửa, rồi final pass cho card đúng proposal. Event lịch sử thiếu boolean `ok` không thay kết quả hoàn chỉnh và không tự biến thành fail. |
| Cấu hình `live` bị hiểu là kết quả thật từ LLM | `ControlPanel`/`Connection` ghi rõ chế độ cấu hình. `EventFeed` hiển thị `agent_completed.data.source` và lý do fallback; `NightPage` lấy nguồn publication hoặc learning event của đúng run/ngày. HTTP offline thực và trường hợp configured-live/actual-offline đều được render đúng. |
| Thiếu khả năng retry learning | `learning_retry_allowed` từ Data điều khiển nút “Thử lại bước học”. HTTP từ DB tạm phân biệt failure có thể retry và receipt `unknown`; UI không tự suy ra quyền retry. |
| Night hiện record ID | HTTP native trả câu tiếng Việt cho lịch sử và sở thích, giữ record/evidence refs riêng. React hiển thị đúng các câu server cung cấp; test có preference thực từ lifecycle native và xác nhận ID không bị dùng thay nội dung. |
| Mất câu hỏi tập trung của Referee | Fake native Referee có câu hỏi cụ thể đi qua HTTP tới component thật; `next_actor`, round và refs được giữ. Câu hỏi riêng tư trong case kiểm thử bị lọc trước projection. |
| Proof tải log nhầm active run | `ProofPage` dùng `report.comparison_id`, hai run IDs và `/api/proof/events`; `readProofEvidence` kiểm pair/run/cutoff. Browser tải file thật và đối chiếu JSON, từ chối pair không khớp, không đọc lại `/api/state` hoặc `/api/events` để chọn log. Lookup sau reset được lane backend kiểm riêng. |
| Saved proof bị mở trong preview dù không hỗ trợ | Preview không hiện lựa chọn “Báo cáo mô phỏng đã chạy” và không cho tải nhật ký cặp đối chứng không tồn tại. API mode vẫn chọn artifact tường minh, tải đúng manifest/report và evidence hai nhánh; artifact thiếu không tự chuyển nguồn. |
| Brief demo cố định | Server trả preset D chính xác; React không có input/textarea/select cho goal hoặc budget, không tự gửi confirm. Browser dùng preset khác có chủ đích chứng minh UI đọc server, rồi click gửi nguyên body preset. Không có preset thì nút start bị khóa. |
| Giữ lịch sử đã xác nhận | `ControlPanel` ưu tiên `state.brief` đã confirmed, ghi “Yêu cầu đã xác nhận ban đầu”; không thay goal/cap cũ bằng preset mới. HTTP và component tests giữ nguyên goal cũ và cap `null`. Saved proof hiển thị brief gốc từ manifest. |
| ShopPilot AI | Shared market/compact header và nhận diện shop D dùng cùng `frontend/img/shoppilot-ai.png`; shop ID khác giữ nhận diện của mình. Tên shop/product vẫn từ API. |

## Kiểm chứng thực chạy

Node dùng `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node`; lệnh frontend chạy tại `frontend/`.

| Lệnh / kiểm tra | Kết quả |
| --- | --- |
| `node build.mjs --tests && node --test tests/*.test.mjs .test-build/*.test.mjs` trên bản logo cuối | **56 passed, 0 failed, 0 skipped**. |
| `node tests/start-operation.browser.mjs` | **PASS**: không tự xác nhận; exact server preset; start 202 mở Demo và nhận event trong khi operation chạy; failure hiện ra; start bị từ chối giữ trang Shop. |
| `node tests/proof-source.browser.mjs` | **PASS**: nội dung hai loại download đúng nguồn đã chọn, mismatch bị từ chối, preview không hiện nguồn không hỗ trợ. |
| `node tests/branding.browser.mjs` trên bundle cuối | **PASS**: ảnh gốc 1536×1024 tải được, header dùng `object-fit: contain`, shop identity cùng URL; desktop và mobile demo không tràn. |
| `node tests/data-contract.integration.mjs` | **PASS**: Data HTTP thật từ hai run offline trong DB tạm → module/React thật cho source, learning, activity, retry, brief và paired evidence. Không dùng fixture frontend để thay response Data. |
| `PATH=/Applications/ChatGPT.app/Contents/Resources/cua_node/bin:$PATH LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q tests/integration/api/test_data_native.py -k 'composed_native_lifecycle_and_asset_gate or referee_focus_reaches_real_http_and_react_without_private_details or demo_preset_is_locked_unconfirmed_and_preserves_existing_briefs' -rs` | **3 passed, 8 deselected, 0 skipped**, 20,94s. Node có trên PATH nên các assertion HTTP → React không bị skip. |
| Probe headless riêng, viewport desktop 1440×1000 và mobile 390×844 | **PASS**: mobile `index`, `updated`, `demo`, `night`, `proof` không tràn ngang và không có lỗi JavaScript trang. Đã mở ảnh để kiểm trực quan cả market header, compact header và shop identity. |
| Hash PNG và cấu hình media đọc từ `Settings()` | **PASS**: `demo_logo_image_path` resolve đúng file UI; SHA-256 `fa91fccb2889f72e6fe938b4e3776afbbdb628bc3d94a9d356c5fb59725479b4`, khớp bytes nguồn đã bàn giao. |

Ảnh kiểm trực quan độc lập ở `/tmp/commit34-ui-recheck-desktop-shop.png`, `/tmp/commit34-ui-recheck-desktop-identity.png`, `/tmp/commit34-ui-recheck-mobile-shop.png`, `/tmp/commit34-ui-recheck-mobile-identity.png`, `/tmp/commit34-ui-recheck-mobile-demo.png`. Ảnh market header được chụp ở đầu trang trước khi cuộn tới shop identity; logo không bị cắt hoặc méo. Đây là ảnh QA bằng preview, không phải bằng chứng backend/live.

## Giới hạn

Not checked: không gọi OpenAI/Muse trả phí, không đánh giá chất lượng ảnh/video live hoặc chứng minh tăng trưởng do học; không chạy mutation trên phiên production. Frontend test không thay việc backend xác thực quyền truy cập/provenance, và lần review này không nghiệm thu cơ chế chọn nhiều dataset 7 ngày hoặc toàn bộ backlog tracking trong requirements. Browser assertions dùng server riêng; HTTP-to-React dùng DB tạm. Root kiểm restart/configuration của local stack và backend riêng trước bàn giao.
