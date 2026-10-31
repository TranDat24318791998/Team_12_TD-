# MI03 — nối media vào Content Agent và seller workflow

Đọc [CONTRACT](CONTRACT.md) mục 4–8; đọc source `app/agents/content.py`, `app/runtime/day.py`, `app/runtime/manager.py`, `tests/fakes/content.py`. Task này thay fake Content ở wiring/harness bằng ContentService thật; fake chỉ còn ở unit tests cần cô lập runtime.

## Output

- `app/content/{service,prompts,images,video,text}.py`: dùng file hiện có, chỉ triển khai helper thực sự cần. `text.py` gọi native generate_content, không có planner thứ hai cho listing.
- `app/domain/models/content.py`: additive fields trong CONTRACT.
- `app/runtime/day.py`: chỉ retry handler, start handoff race, video review gate/receipt.
- `app/runtime/manager.py`: dependency injection và close service cũ trước reset; giữ các additions từ self-improve nếu đã có.
- `tests/unit/content/{test_service,test_prompts}.py`, `tests/integration/runtime/test_media_workflow.py`, `tests/fakes/media_gateway.py`.
- `contracts/media_gateway/` và content fixtures bị đổi shape; shared docs có delta ở MI04.

Không sửa memory/night/negotiation/self-improve, không viết lại market, Data SQL hoặc HTTP facade. Interface generate_content/content_view là seam ổn định của workstream này.

## A. Pure builder và input

1. `resolve_inputs(shop_public, settings)` ưu tiên `DEMO_PRODUCT_IMAGE_PATH` rõ ràng, nếu trống chọn file đầu tiên thực sự tồn tại từ `shop_public.images` trong assets/products. Resolve `/assets/...` qua ASSETS_DIR, kiểm root/path, không lấy URL ngoài mạng hoặc field từ browser. Thiếu → `MEDIA_INPUT_MISSING`, không giả ảnh. Logo lấy optional DEMO_LOGO_IMAGE_PATH.
2. `build_media_brief(public, confirmed_notes, feedback_history)` trả product_kind, product_name, verified_facts, presets A/B/C, background_preference, short script và setting. D dùng mapping demo `{('D', 'quat_mini'): 'handheld_fan'}` theo seed; chưa map shop/category khác thì báo MEDIA_PRODUCT_UNSUPPORTED, không suy từ filename hay mặc định desk fan. Tái sử dụng verified attributes; không dùng tên file để suy luận fact.
3. Bright khi notes chứa style đã xác nhận hoặc feedback hiện tại là case hỗ trợ. Hỗ trợ câu demo “Ảnh nền tối quá, làm nền sáng” và tương đương rõ yêu cầu nền sáng. Nếu input mơ hồ/ngoài phạm vi, reject trước version mới và cost. Không mở chat tự do/LLM phân loại feedback.

## B. start: tạo bản đầu

```text
validate approved card + confirmed brief + owner under session.lock
snapshot public/style/card/brief; validate local input + service capability outside lock
run generate_content(... card_id, draft_version=1, feedback_history=())
create ContentDraft with A/B/C running; video pending; bounded text/source checks
under lock revalidate same approved card and brief; install draft before workers
freeze binding inputs; submit one orchestration future; return deep-copy draft
```

`generate_content` phải chạy native tool loop hiện có, test fake model thật sự đọc ToolMessage. Khi LLM offline, chữ có source offline; MEDIA_MODE live vẫn có thể chạy ảnh/video thật. Style snapshot của brief và prompts phải cùng rules_version/confirmed notes, không đọc lại thành version khác giữa ba ảnh.

Worker thực hiện sequence A → video → B/C trong CONTRACT, trả update từng slot. Có bốn media slots, không bốn bản draft. `ThreadPoolExecutor(max_workers=2)` do composition root/harness sở hữu là đủ; remote service vẫn một worker. Không tạo executor mỗi job, không giữ Session.lock qua IO. Root service chỉ cần một orchestration future/draft.

Sửa đoạn `submit_decision` sau start: lấy draft đã cài trong Session, verify identity/version, đổi step; **không gán lại snapshot cũ** nếu worker đã update. Nếu start fail trước install, giữ card awaiting_decision và clear approved_card_id như hiện có; không xóa draft hợp lệ khác. Test fake immediate completion bắt race này.

## C. retry: feedback và version

Thêm workflow helper:

```python
retry_content(session, *, card_id, expected_brief_version, expected_draft_version,
              feedback_vi: str) -> ContentDraft
```

Nó chạy như submit_decision: validate ID/version/step và reserve phase_busy dưới lock, gọi `session.content.retry` ngoài lock, cuối cùng clear busy. Service retry chỉ khi tất cả slot bản cũ terminal và không binding uncertain; version<3; feedback hỗ trợ; budget còn. Kiểm xong trước tăng version. Same browser command key phải được facade map tới receipt/idempotency; helper version guard chặn lần bấm lại stale không sinh job thứ hai.

Tạo v+1: giữ card/brief, feedback_history cũ + feedback mới, lấy style đã xác nhận; native Content invocation mới; ghi **một** feedback content_job event theo CONTRACT mục7 rồi cài draft và chạy worker. Tối đa bản đầu + hai retry. Không sửa listing, active package hoặc Rules trong start/retry.

Budget counter ở ContentService sống cùng Session: reserve tối đa settings.max_image_jobs_per_session (9) Images và settings.max_video_jobs_per_session (3) trước lần submit đầu của mỗi binding; uncertain vẫn giữ reservation, same-key recovery không tăng. Card mới trong cùng run dùng chung budget; reset tạo run mới. Budget hết → status failed có reason, không âm thầm cấp thêm hoặc gọi provider khác.

## D. apply và callback

- ContentService.apply chạy dưới runtime lock, chỉ đọc draft/local file, clone ShopPublic rồi set title/description/images/video; một cover được chọn, skip video thì video=null. Không provider IO, không charge, không tự activate hoặc xóa file cũ.
- Runtime thêm `video_review_ack=False` keyword theo CONTRACT mục6. Receipt payload gồm brief/cover/skip/ack. Default false giữ bảo thủ với old clients; test/update fixtures có review_passed hoặc gửi ack rõ ràng.
- `_local_media_exists` tiếp tục kiểm cùng run hoặc registered replay; URL signed không được qua gate bằng cách đổi source='fixture'. Không đổi logic finance/forecast/approval.
- Callback thấy draft None hoặc service closed sau Apply/reset thì không sửa state/listing. File download của job cũ có thể giữ ở run cũ; không xóa media/replay hay media được published khác.
- `SessionManager.reset` close service cũ trước đổi current; tạo ContentService qua content_factory(session) hiện có. Factory/client/executor injection giữ testability và không import network client lúc module import.

## Acceptance → test

| ID | Scenario | Invariant |
|---|---|---|
| W01 | Start trước approve, thiếu ảnh/config | Không job có phí; không active/listing thay đổi |
| W02 | Start hợp lệ, fake provider chạy ngay | Native Content nhận ToolMessage; callback done không bị runtime trả về ghi đè |
| W03 | A done | Video input A asset ID đúng card/version; video submit trước B/C |
| W04 | A fail | Không submit video/t2v, có reason; B/C vẫn có thể dùng với skip |
| W05 | Retry nền sáng | v+1, A/B/C sáng; Rules vẫn cũ; feedback event chỉ một |
| W06 | Retry stale/v3/unknown/busy | Không thay version, không thêm job/cost |
| W07 | Callback v1 sau v2/reset/apply | Không overwrite draft/listing/run mới |
| W08 | Video review false | Apply không ack bị chặn; ack+file hợp lệ được phép; ack không vượt missing file |
| W09 | Apply duplicate/mismatch | Same request một effect; khác cover/skip/ack conflict |
| W10 | Night→candidate→seller Yes→Content tiếp theo | confirmed style tự vào bright prompt dù feedback mới rỗng |
| W11 | MEDIA offline/replay | Không HTTP; cache cần manifest/checksum; absent cache không giả done |
| W12 | Dẫn xuất public payload | Không cost/rules/persona/token/absolute path vào media request hoặc event |

```sh
.venv/bin/python -m pytest -q tests/unit/content tests/integration/runtime/test_media_workflow.py
.venv/bin/python -m pytest -q
```

Done: dùng ContentService thật trong integration test; chỉ gateway/model/market còn fake có nhãn. Chuyển MI04. Nếu self-improve đã đổi Session/manager, adapt factory theo source hiện hành, không thay về bản baseline.
