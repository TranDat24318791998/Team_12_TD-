# Contract media-integration.v1 cho coder và reviewer

Status: thiết kế cần implement qua MI01–MI04. Baseline media là `a0a93f0`; field ghi **mới** chưa có trong source baseline. Shared business fields giữ [DEMO_CONTRACT](../../../DEMO_CONTRACT.md); UI/Data adoption ở [UI_DATA_HANDOFF](UI_DATA_HANDOFF.md).

## 1. Quyết định cố định

- Root backend gọi service `experiment` bằng HTTP. Môi trường Python/dependencies tách riêng; không import `video_api`/`muse` vào `app` và không chép provider code sang infrastructure.
- OpenAI: native agents ở core; Images edits và vision/prompt/frame-review ở media. Muse: clip chuyển động và audio native của clip. Default `voice=muse`, `music=none`; không thêm TTS ngoài cho luồng D.
- D: `product_kind=handheld_fan`, tên/thuộc tính lấy ShopPublic có nguồn seed. Service vẫn hỗ trợ `desktop_fan` cho client lab cũ. Không đổi seed D thành desk fan để chiều prompt.
- Một draft: A/B/C, một video từ **A**, `realistic_human`, duration 5, aspect `9:16`. Chọn B/C khi Apply chỉ thay cover, không phát sinh video mới. `chibi_3d` vẫn là option video hiện có của service, không triển khai tool/render 3D khác.
- Logo tùy chọn; có thì giữ đúng, không có thì không vẽ. Product image bắt buộc trong luồng tích hợp D; text-to-video giữ cho lab riêng, không âm thầm thay ảnh D thiếu.
- Core giữ listing/campaign/approval. Media `done` chỉ là đã có file, không đồng nghĩa người bán duyệt hay sản phẩm được xác minh.

## 2. Hai tầng API và wire đã có

| Đích | Config / auth | API dùng trong tích hợp |
|---|---|---|
| Media service local | `MEDIA_API_BASE_URL=http://127.0.0.1:8010`, Bearer `MEDIA_API_TOKEN` = `VIDEO_API_TOKEN` phía service | `/health`, `/v1/readiness`, `/v1/assets`, `/v1/image-jobs`, `/v1/jobs` |
| Muse Gateway | Chỉ service đọc `MUSE_API_BASE_URL`, `MUSE_API_KEY` | JSON POST `/v1/videos`, GET `/v1/videos/{task_id}`, GET `/v1/media/...` |

Root dùng JSON jobs: upload product/logo một lần qua multipart `POST /v1/assets` field `file`; lưu `asset_id` theo `(run_id, shop_id, sha256(bytes))`. Header `X-Owner-ID=ga_<run_id>_<shop_id>` do backend dựng, không nhận từ model/browser. Header của POST job: `Idempotency-Key` 8–120 ký tự. GET status dùng cùng Bearer/owner.

API tiện ích `/v1/images` và `/v1/videos` của **media service** nhận multipart, vẫn giữ cho lab; root không cần dùng. `/v1/videos` của **Muse Gateway** nhận JSON. Muse `image` hiện được `MuseMedia.generate` gửi dưới dạng data URL, task ID lưu trước poll, download bị chặn khác origin/redirect. Tái sử dụng wrapper đó; không gọi helper download rộng hơn của raw MuseClient.

### 2.1 ImageRequest sau MI01

Giữ `extra=forbid` và các field hiện hành, thêm/mở đúng phần sau:

| Field | Type / default | Ghi chú |
|---|---|---|
| `job_type` | Literal['image']='image' | Có sẵn |
| `product_asset_id` | ID 32 hex, required | Có sẵn, ảnh duy nhất nhận dạng SKU |
| `logo_asset_id` | ID 32 hex hoặc null = null | **Đổi thành optional**, backward compatible khi client cũ gửi logo |
| `style_asset_id` | ID hoặc null = null | Mood reference không được đưa vật/chữ thành product fact |
| `style` | clean_white / pastel_lifestyle / premium_studio / summer_fresh | Có sẵn |
| `product_kind` | handheld_fan / desktop_fan = desktop_fan | **Mới**, root luôn gửi handheld_fan cho D |
| `product_name` | str 1..90 = 'Quạt để bàn' | **Mới**, root lấy tên công khai |
| `background_preference` | default / bright = default | **Mới**, không nhận câu lệnh tự do |

Ví dụ body từ core, các ID là fixture về shape:

```json
{"job_type":"image","logo_asset_id":null,"product_asset_id":"11111111111111111111111111111111","style_asset_id":null,"style":"clean_white","product_kind":"handheld_fan","product_name":"Quạt mini cầm tay","background_preference":"bright"}
```

Default A/B/C lần lượt `clean_white`, `pastel_lifestyle`, `premium_studio`. Khi style đã xác nhận hoặc feedback hiện tại yêu cầu nền sáng: A/B/C dùng `clean_white`, `pastel_lifestyle`, `summer_fresh` và tất cả gửi `background_preference=bright`. Code chọn preset sáng trước khi thêm yêu cầu ánh sáng; không để cùng prompt vừa charcoal/dark vừa bright. Feedback hỗ trợ trong demo là yêu cầu đổi nền sáng; câu khác trả `DEMO_FEEDBACK_UNSUPPORTED` trước mọi job mới.

### 2.2 VideoRequest sau MI01

Giữ fields/validator hiện có; thêm `product_kind` như ImageRequest. Body core dựng:

```json
{"input_asset_id":"22222222222222222222222222222222","product_name":"Quạt mini cầm tay","product_kind":"handheld_fan","verified_facts":["3 tốc độ gió","sạc USB","pin 2000mAh"],"script":"Quạt mini cầm tay, sạc USB, pin 2000mAh.","mode":"muse","output_type":"realistic_human","duration":5,"aspect":"9:16","generate_script":true,"generate_image":false,"voice":"muse","music":"none"}
```

`input_asset_id` bắt buộc là **result.asset_id của ảnh A cùng draft**, không phải product input hoặc cover cũ. Root truyền `setting` sáng khi có bright style và `motion_prompt` thuần định hướng cảnh; dùng whitelist feedback đã hỗ trợ. Không gửi raw private note/rules/cost.

Narration demo lấy từ public facts qua builder deterministic, tối đa 4 từ/giây, không tự thêm giá/discount/thông số. `generate_script=true` để service vẫn tạo visual plan; service đã giữ nguyên supplied_script, MI01 phải giữ gate này. Title/description của listing vẫn do native Content Agent trả, không bị script/video planner ghi đè.

Muse API gốc rộng 1–120 giây nhưng service chỉ hỗ trợ 5/10/15. Demo chốt 5; schema hỗ trợ 10/15 không chứng minh đã smoke hai độ dài đó. Motion result actual duration được lưu riêng; không ép metric/report thành requested duration.

### 2.3 Capability và kết quả

`GET /v1/readiness` **thêm** `contract_version='growth-media.v1'`, `supported_product_kinds`, `optional_logo=true`, `bright_background=true`; giữ các boolean storage/OpenAI/Muse hiện có. Root live preflight cần capability này, storage ready và hai provider keys configured. HTTP readiness không chứng minh model có quyền/quota hay generation chạy được.

Giữ job response `{job_id,status,stage,error,result,...}`, thêm `outcome_unknown:bool=false`, `status=queued|running|done|failed`. Result image/video **thêm** `sha256` 64 hex và giữ `size_bytes`, `media_type` (video đặt `video/mp4`), `product_kind`, `provider`, object metadata. Image có `asset_id` 32 hex; video giữ `visual_review_passed`, `visual_review`, `seller_review_required=true`, `product_identity_verified=false`, Muse task ID. Root chỉ lưu/projection fields cần dùng; không phát raw result/prompt/MinIO address xuống seller events.

## 3. Product identity và prompts

Các internal GPT output models `ProductImageAnalysis` và `MuseCreativePlan` thay `is_desktop_fan` bằng `product_kind: handheld_fan|desktop_fan|other`. Caller truyền expected kind; sau parse phải khớp và analysis.product_count==1. Đây là thay đổi output metadata có version, cập nhật tests/lab/docs liên quan cùng MI01; không giữ hai boolean mâu thuẫn hoặc bỏ check để đi qua.

Image prompt dựng thứ tự ảnh theo input thực: product luôn có, logo nếu có, mood nếu có. Ghi rõ index/role đúng theo list, không hardcode “image 1 logo, image 2 product” khi logo null. Handheld: giữ thân/tay cầm/tỉ lệ; desktop: giữ chân/đế. Vision, muse_plan, build_muse_prompt, review_muse và watch page cùng dùng product kind/name; không còn ép D có đế quạt bàn.

Vision chỉ mô tả quan sát, không nâng chữ trong ảnh thành verified_facts. Fact/narration của core có quyền cao hơn suy đoán vision. Frame review là tư vấn; không kiểm được khẩu hình/audio hoặc chứng minh SKU thật bằng ba frame. Không bỏ seller review kể cả visual_review_passed=true.

## 4. Runtime DTO và giao diện ContentService

Giữ fields cũ; bổ sung default để fixtures/consumer cũ parse được:

| Model | Field mới |
|---|---|
| CoverImage | `source: live\|cache\|fixture\|unavailable='unavailable'`, `error: str\|null=null` |
| VideoJob | `source` như cover; `reference_option: Literal['A']='A'`; `visual_review_passed: bool\|null=null`; `review_notes_vi: str\|null=null` |

Job `stage=interrupted` hoặc `outcome_unknown` phải trả outcome_unknown=true; core giữ binding uncertain dù transport status=failed. Failure trước submit/validation có unknown=false. Timeout/network sau lời gọi có phí không được biến thành known failure chỉ để mở nút retry.

Không đưa service asset IDs/token vào ShopPublic. Binding nội bộ của service giữ `(run_id,shop_id,card_id,brief_version,draft_version,slot)`, request body/hash, stable idempotency key, job_id, input/output asset_id, status, uncertain flag và local checksum. Dùng dataclass/dict nhỏ thuộc `ContentService`; không thêm database nghiệp vụ hoặc registry framework.

```python
ContentService(session, *, media_client, executor, input_resolver)
start(shop_id: str) -> ContentDraft
retry(shop_id: str, feedback_vi: str) -> ContentDraft
apply(shop_id: str, cover_option: str, *, skip_video: bool = False) -> ShopPublic
close() -> None  # tắt publish callbacks của service cũ khi reset/shutdown
```

`source` của service live không được là `fixture`. `start/retry` gọi native generate_content hiện có, dựng draft, lưu vào Session dưới lock rồi submit worker. Không chờ image/video; LLM text có thể mất tối đa budget invocation hiện hành. `apply` chỉ clone/cập nhật listing từ file sẵn có; không network, không gọi agent, không activate campaign.

## 5. Worker, download và retry

1. Preflight input/capability/config trước request có phí; lỗi rõ field thiếu. Upload nguồn một lần, cache ID theo bytes hash/owner.
2. Tạo A trước. A done → lưu output asset ID; submit video **trước** B/C để một worker remote không xếp video cuối ba ảnh. Poll ba job còn lại trong cùng loop, cập nhật từng slot; không tăng worker remote hoặc tự nâng queue limit.
3. A failed → video failed `REFERENCE_IMAGE_FAILED`; vẫn có thể tạo B/C để seller dùng ảnh với skip_video. Không đổi sang text-to-video hoặc dùng ảnh A cũ.
4. Một key/slot/draft: `ga-<sha256(run,shop,card,brief,draft,slot,canonical_body)>`, <120 chars. Body freeze sau asset upload. Retry transport giữ nguyên body/key; provider job mới chỉ thuộc draft mới có seller retry.
5. JSON POST bị timeout chưa biết kết quả: có thể replay **cùng key + body** một lần để lấy lại job vì Store.create có transaction/dedup; không upload lại rồi thay asset ID. Chưa biết kết quả sau recovery → binding uncertain, báo rõ, không tạo key mới. Direct Muse paid POST vẫn chỉ một lần trong service.
6. GET poll khoảng 2 giây phía core; deadline wall-clock mỗi draft 20 phút (bao gồm queue), configurable. Timeout không chứng minh remote failed. Giữ job ID, uncertain; retry draft bị chặn cho tới khi kiểm được terminal. Không thêm job-resume engine trong timebox.
7. Download chỉ khi job done đủ result; parse signed URL path đúng `/v1/images/<job>/view` hoặc `/v1/jobs/<job>/play`, lấy expires/signature và gọi đường đó trên **MEDIA_API_BASE_URL cấu hình**. Không lấy host từ model/browser; không gửi Bearer trên signed download; redirects tắt. Nếu signature hết hạn, GET job lấy mới một lần, không regenerate.
8. Stream vào `media/<run>/<shop>-<card>-v<draft>-<slot>.jpg|mp4.part`; giới hạn 40MB ảnh/150MB video, kiểm byte count + sha256 result + Content-Type/magic; service đã decode ảnh/FFmpeg validate clip. Atomic rename rồi mới set done/path `/media/...`. Core không cần cài thêm renderer/GPU. Sai checksum/MIME/size → failed, không publish.
9. Callback kiểm tất cả binding IDs + service chưa close + current draft chưa publish. Reset/retry/apply làm callback cũ mất quyền sửa state; không giữ Session.lock qua HTTP/poll/download. Background workers không tự kích hoạt hoặc cập nhật listing.
10. Source `cache` chỉ khi manifest/file/checksum thực tồn tại, `fixture` chỉ trong harness. Live lỗi không tự thay bằng video zoom/placeholder. Offline không network và báo unavailable nếu không có replay asset thật.

Budget: tối đa 3 draft/card; cả run dùng chung max_image_jobs_per_session=9 và max_video_jobs_per_session=3 (không reset khi đổi card); native Content dùng budget 64 chung của agents. Media còn có tối đa 3 OpenAI text/vision calls/video, tách khỏi bộ đếm native LLM vì đi process khác; hiển thị/ghi count riêng, không báo tổng chi phí đã được cap bằng 64. Không có auto-generation retry ở OpenAI SDK (`max_retries=0`).

## 6. Apply và video review

Root vẫn gọi `apply_reviewed_content` để kiểm card/brief/draft, local files, package/finance và forecast snapshots rồi publish + activate. Chỉ mở rộng keyword `video_review_ack: bool=False` ở runtime và request contract; thêm nó vào receipt payload để cùng request retry nhất quán. Chữ ký ContentService.apply không cần ack vì gate ở runtime.

- Video done/cached, review_passed=False/null: cần `video_review_ack=true` hoặc seller chọn `skip_video=true`. Ack không vượt qua lỗi file/status.
- Video review_passed=True: Apply vẫn là hành vi seller duyệt, không tự apply.
- Video chưa có file: skip=false bị chặn; skip=true bỏ video khỏi listing đã chốt. Callback muộn không thêm video sau Apply.
- Cover đã chọn phải done/cached + file hợp lệ. Các slot khác đang chạy không làm thay đổi cover đã duyệt. UI báo job còn chạy; không cancel/submit thêm để che trạng thái.
- `apply_reviewed_content` chuẩn bị mọi validation/snapshots trước khi ContentService.apply mutate listing. Không tạo lỗi mới có thể tránh được sau publish. Receipt giữ clone listing, duplicate request không tạo event/campaign thứ hai.

`submit_decision` đang gán lại `session.content_draft` sau ContentService.start. MI03 sửa seam này: service cài draft trước workers; runtime chỉ xác minh draft hiện tại cùng identity và đổi step, không ghi đè snapshot trả về cũ. Có test callback hoàn thành ngay trước start return.

## 7. Feedback và Knowledge

Source style là `ContentMemoryView.confirmed_style_notes`; candidate không vào default. Feedback trong retry áp dụng ngay cho **draft này**, nhưng không sửa Rules. Native `get_content_context` vẫn nhận feedback_history đúng card/version, và media builder dùng cùng snapshot style/feedback.

Ghi một `content_job` feedback event gồm card_id, negotiation_id, old_version, new_version, feedback_vi và source; không lặp event feedback khi poll. Events progress chỉ có slot/status/source/job reference an toàn. Night hiện có đọc event để tạo preference; seller Yes hôm sau mới đổi Rules. Test invocation mới dùng bright preset ngay cả khi feedback_history rỗng sau Yes. Không sửa thuật toán Learning/self-improve trong gói này.

## 8. Cấu hình

Root thêm Settings `media_api_base_url`, `media_api_token` (ẩn hoàn toàn), `media_poll_seconds=2`, `media_draft_timeout_seconds=1200`, `max_image_jobs_per_session=9`, `demo_product_image_path=''`, `demo_logo_image_path=''`. Settings và `.env.example` dùng uppercase tương ứng; input path chỉ backend/operator, không từ request browser. MEDIA_MODE live/replay/offline vẫn độc lập LLM_MODE. Không tự bật live khi chỉ thấy token.

Service giữ env hiện có; model từ file user cung cấp, không tự chọn model mới. Root `.env` và `experiment/.env` tách; service token không phải OpenAI/Muse key. `PUBLIC_BASE_URL` chỉ cần tunnel nếu client ngoài máy; core cùng host dùng loopback. Không bắt buộc Cloudflare/Sites để tích hợp local.

Tham khảo chính thức về Images edits nhận nhiều ảnh, JPEG và `n=1`: [OpenAI Images edit](https://developers.openai.com/api/reference/python/resources/images/methods/edit). Source service đã dùng SDK `images.edit`; tái sử dụng và kiểm quyền model qua smoke khi đủ cấu hình, không đổi SDK API theo suy đoán.
