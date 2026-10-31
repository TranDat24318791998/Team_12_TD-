# MI02 — HTTP client và import artifact vào core

Đọc [CONTRACT](CONTRACT.md) mục 2/4/5/8. Phụ thuộc MI01 contract; có thể viết trước bằng httpx.MockTransport, integration thật chỉ sau MI01.

## Output

- `app/infrastructure/media_gateway.py` mới: transport HTTP và parser strict tại boundary.
- `app/domain/models/media.py` mới: typed internal request/result/binding DTO nếu nhiều caller dùng; không có HTTP/env/path IO trong domain. Không chép cả provider result JSON vào domain.
- `app/core/settings.py`, `.env.example`: chỉ thêm bridge/input/budget fields được CONTRACT quy định.
- `tests/unit/infrastructure/test_media_gateway.py`, `tests/unit/core/test_settings.py`, `contracts/media_gateway/*.json` fixtures sanitized.
- Nhật ký Toàn.

Root đã có httpx/Pydantic; không thêm OpenAI/MinIO/FFmpeg dependency để gọi HTTP. Các app/infrastructure/images.py và muse.py khung không cần lấp bằng implementation trùng service.

## Interface khóa cho ContentService

```python
MediaGatewayClient(settings, *, http_client=None)
readiness() -> MediaReadiness
upload_image(path: Path, *, owner: str) -> MediaAsset
create_image(request: ImageJobRequest, *, owner: str, key: str) -> MediaJobView
create_video(request: VideoJobRequest, *, owner: str, key: str) -> MediaJobView
get_job(job_id: str, *, owner: str) -> MediaJobView
download(job: MediaJobView, *, kind: Literal['image','video'], destination: Path) -> LocalArtifact
close() -> None
```

`MediaJobView`: job_id 32hex, status enum, stage str, error safe nullable, image result/video result typed nullable, signed_url internal nullable. `LocalArtifact`: Path, sha256, size_bytes, media_type; convert thành `/media/...` ở content layer. Không serialize `Path` tuyệt đối hoặc signed_url vào StateView.

Các field tối thiểu phải định nghĩa rõ trong DTO:

| DTO | Fields dùng ở caller |
|---|---|
| MediaReadiness | ready:bool, contract_version:str, openai_configured:bool, muse_configured:bool, supported_product_kinds:list[str], optional_logo:bool, bright_background:bool |
| MediaAsset | asset_id:32hex, kind:Literal['image'] |
| ImageResult | asset_id:32hex, sha256:64hex, size_bytes:int>0, media_type:Literal['image/jpeg'], product_kind:ProductKind |
| VideoResult | sha256:64hex, size_bytes:int>0, media_type:Literal['video/mp4'], product_kind:ProductKind, duration_seconds:float>0, visual_review_passed:bool, visual_review.notes_vi:str, product_identity_verified:bool |
| MediaJobView | job_id:32hex, status:queued/running/done/failed, stage:str, error:str\|null, outcome_unknown:bool, result:ImageResult\|VideoResult\|null; image_url/video_url và expires_at chỉ ở transport DTO |

Unknown extra result metadata không đưa vào domain/event. ImageJobRequest là đúng fields CONTRACT2.1; VideoJobRequest dùng payload CONTRACT2.2 cộng setting/motion_prompt đã kiểm. Không trả raw dict làm API chính của client.

`MediaGatewayError(code, message_vi, *, uncertain=False, job_id=None)` tách config, unavailable, protocol, conflict, queue-full, remote-failed và invalid-asset. Không dùng exception string từ provider làm seller text. DTO extra=ignore chỉ dùng cho response envelope có thể thêm field; các field được dùng phải type-validate, reject missing/invalid terminal data. Request extra=forbid.

## Thứ tự code

1. Settings đọc root env; media_api_token `repr=False` và describe ẩn hoàn toàn. Không in token prefix/suffix. Kiểm scheme http/https, base URL không chứa userinfo/query; http loopback hợp lệ cho demo. Thiếu base/token trả lỗi trước network.
2. HTTP Client timeout connect=5s/read=30s cho JSON, không retry generation tự động. Headers Bearer+owner do backend dựng; idempotency key trên POST job. Asset upload có Content-Length, media service tự normalize/validate ảnh; max input40MB, nguồn path do operator chỉ định chứ không browser.
3. Request JSON không tự chèn toàn Session; dựng từ DTO. Readiness cần đúng growth-media.v1 trước paid requests. `create_*` chấp nhận status 200/202 có job_id hợp lệ; 401/403/422/409 fail rõ, 429 là known not accepted, có thể chờ theo worker policy cùng key. HTTP response malformed sau submit là uncertain.
4. Cache asset upload trong ContentService theo owner+SHA bytes, không trong singleton cross-run. Khi job body đã freeze, transport recovery dùng chính DTO cũ; không upload lại sinh ID mới. Client không sở hữu decision tạo draft tiếp theo.
5. Implement download theo CONTRACT mục 5: lấy path/query hợp lệ của signed link nhưng origin luôn từ config; HTTP signed request không có Authorization. Giới hạn bytes, checksum/size/MIME/magic, `.part` cleanup và atomic rename. Không xóa file đã publish nếu callback stale.
6. Terminal image cần result.asset_id và checksum để video chain; terminal video cần checksum và review fields. `done` thiếu data → protocol failure, không gán done cho core. `queued/running` không yêu cầu terminal fields.
7. Dùng `httpx.MockTransport` kiểm headers/paths/body và byte streaming; ghi request count. Các fixtures là fabricated wire examples có `source=fixture`, không nói là raw provider response đã capture.

## Acceptance → test

| ID | Input | Expected |
|---|---|---|
| C01 | Không token hoặc readiness version cũ | Lỗi safe trước create job; không provider fallback |
| C02 | create image → done → create video | Video input đúng output asset A, không dùng ID nguồn |
| C03 | JSON body bị thêm private field | DTO reject trước network |
| C04 | POST timeout rồi cùng key/body recovery | Không thay body/key; fixture trả một job ID |
| C05 | 429/409/401/terminal thiếu result | Mapping đúng, không auto tạo key mới |
| C06 | Signed URL hết hạn | Một GET status refresh, không create image/video |
| C07 | Response URL host lạ/redirect | Không request host lạ; không chuyển Bearer theo URL; path/job sai reject |
| C08 | Byte thiếu/checksum sai/MIME sai | Không có final file/done; `.part` được dọn |
| C09 | Env describe/repr/fixtures | Không có giá trị token/API key |

```sh
.venv/bin/python -m pytest -q tests/unit/infrastructure/test_media_gateway.py tests/unit/core/test_settings.py
```

Done: fixtures parse + HTTP tests qua, không IO ngoài temp files và MockTransport. Chuyển MI03; root .env bridge do user cấp đã có thể dùng khi service/môi trường sẵn sàng.
