# MI01 — làm service hiện có tương thích SKU D

Đọc [CONTRACT](CONTRACT.md) mục 1–3/8. Task sửa bên trong experiment, chưa nối Session hoặc UI. Giữ default desk-fan của lab cũ; client core mới luôn gửi kind rõ ràng.

## Output

- `experiment/video_api/{models,main,image_pipeline,openai_media,muse_pipeline,muse_media}.py`.
- `experiment/tests/{test_image_api,test_muse,test_api}.py`; thêm `test_product_kind.py` nếu giúp nhóm các case độc lập.
- `experiment/{README,CODEX_DEPLOY}.md`: chỉ cập nhật capability, body và điều đã thực kiểm; không sửa lịch sử live thành kết quả mới.
- `docs/plans/toan/CODEX_LOG.md`: một dòng MI01, giữ các dòng agent khác.

Không sửa raw MuseClient, storage engine, `.env` secrets hoặc model version chỉ để test xanh. Dùng Python/môi trường riêng của experiment theo CODEX_DEPLOY.

## Thứ tự code

1. Thêm type alias `ProductKind = Literal['handheld_fan','desktop_fan']` và fields request đúng CONTRACT. Tạo default compatible cho client cũ. `logo_asset_id` null có nghĩa không logo; product_asset_id vẫn required. Internal analysis/creative plan đổi sang product_kind có thêm `other`; source caller kiểm expected kind và product_count.
2. Tách helper thuần nhỏ `build_image_prompt(request)` và input role order trong image_pipeline. Dùng list `(role,path)` thật thay fixed positions. Logo có thì bảo toàn lettering/colors; không có thì yêu cầu no logos/text. Mood image chỉ ảnh hưởng palette/ánh sáng. Background bright override preset tối bằng mapping xác định trước.
3. `analyze_product_image(image, *, product_kind)` và `muse_plan(request, image, analysis)` nhận product_kind; system/user prompt mô tả đúng handheld/desktop. Reject phân tích khác kind hoặc nhiều sản phẩm trước Muse submit. Không thay is_desktop_fan check bằng always true.
4. `build_muse_prompt` rẽ nhánh anatomy: handheld có tay cầm, desktop có chân/đế. `review_muse(frames, *, output_type, product_kind)` cùng thông tin; caller và fake providers cập nhật signatures. `watch` dùng escaped product name/result, không hardcode tiêu đề quạt bàn.
5. Narration: giữ supplied script đã giới hạn của core; checked length trước gọi Muse. Vision/planner không được sửa public listing hoặc đổi verified facts. Những steps GPT trong media vẫn là provider pipeline, không tạo role agent mới.
6. Nối các field mới ở cả hai entrypoint: JSON image-jobs/jobs và multipart images/videos. Multipart logo optional; tính upload fingerprint gồm role/order, hashes và tất cả trường ảnh hưởng output. Default cũ giữ nguyên; cùng key đổi kind/bright/style/image phải trả 409, không tái dùng job sai brief.
7. Mở readiness capability theo CONTRACT. Khi complete tính sha256 file output đã validate, thêm media_type/product_kind/size/checksum vào result. `minio_uri` không dùng làm public URL. Metadata không xác nhận product identity thật.
8. Worker giữ `stage=outcome_unknown` cho timeout/network hoặc response thiếu task sau paid submit; job_view thêm outcome_unknown=true cho stage này và interrupted. Dùng exception typed nhỏ của adapter, không parse chuỗi lỗi để quyết định đã charge hay chưa. Validation/input/provider terminal fail rõ ràng giữ unknown=false. Thêm test crash recovery/unknown không mở retry tự động.
9. Giữ `max_retries=0`, Muse task persist-before-poll, same-origin download và single-worker recovery. Không cho model tự retry generation vì visual review không đạt.

## Acceptance → test

| ID | Case | Quan sát bắt buộc |
|---|---|---|
| G01 | Request cũ không kind, có logo | default desktop; existing API tests còn qua |
| G02 | D handheld, không logo | fake Images nhận product ở đúng index, prompt không ép chân/đế; không crash missing logo |
| G03 | Có logo và mood | roles/index đúng, mood không thành product reference |
| G04 | bright + premium preset | prompt cuối dùng preset sáng, không còn charcoal/dark instruction |
| G05 | GPT analysis trả desktop cho request handheld | job failed trước Muse; fake Muse create count=0 |
| G06 | Cùng key/body và đổi kind/brightness | job cũ được trả khi same; conflict khi changed; provider chỉ chạy một lần |
| G07 | Visual review false | status done/stage needs_visual_review, seller review flag và identity_verified=false |
| G08 | File output | sha256/size khớp bytes thật, JPEG hoặc MP4 như result |

Test dùng Fake OpenAIMedia/MuseMedia, LocalStorage, temp SQLite; không MinIO thật hoặc API trả phí. Coder bổ sung test param cả handheld/desktop và hai output_type còn được service hỗ trợ.

```sh
cd experiment
.venv/bin/python -m pytest -q tests/test_image_api.py tests/test_muse.py tests/test_api.py
.venv/bin/python -m pytest -q tests
```

Done: body JSON và multipart cùng semantics, test trên qua; ghi gateway contract_version và SHA. Thiếu environment thì cài theo requirements riêng, không đưa dependencies experiment vào requirements gốc. Chuyển MI02, chưa cần live generation.
