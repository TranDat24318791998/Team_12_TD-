# D01 — Model, seed, tài chính và trạng thái phiên

Timebox: **15 phút**. Phụ thuộc D00. Đọc `docs/DEMO_CONTRACT.md` mục 1–2, 4, 6 và `docs/SEED_DATA.md`. Task này chưa viết agent, UI hoặc media.

## Output được sửa

`app/domain/models/{shops,packages,negotiation,cards,content,learning,metrics,events,intent,tools}.py`, `app/domain/{finance,validators,privacy,formatting}.py`, `app/simulation/world.py`, `app/runtime/{session,manager}.py`, `app/infrastructure/{store,eventlog}.py`, `app/core/settings.py`, `.env.example`, `data/{seed,campaigns}.json`, `contracts/agents/{public_context,shop_context,tool_checks}.json`, `tests/unit/domain/{test_models,test_finance,test_privacy}.py`, `tests/unit/runtime/test_session.py`, `tests/fakes/`, `docs/CODEX_LOG.md`.

## 1. Tạo model trước

- Tạo DTO tool theo AGENT_TOOL_KNOWLEDGE và record/view theo KNOWLEDGE_CONTRACT; một class cho một schema, không tạo bản dict khác trong agent. Chép đúng field từ CONTRACT và các field bổ sung trong DEMO_CONTRACT. Package, Brief và Decision dùng model cụ thể, không dùng `dict[str, Any]`.
- Các danh sách dùng `default_factory`, không dùng shared mutable default.
- `Package` kiểm kiểu và khoảng giá trị; hard cap của shop thuộc business validator. `model_copy(update=...)` không tự validate: dựng lại bằng `Package.model_validate(...)` sau clamp.
- `PlatformTurn.accept` cần package; `ShopTurn.counter/accept` cần package. Action reject/withdraw có thể trả null. Output model không hợp lệ thì caller fallback; schema không tự sửa số tiền.
- `Event` gồm seq/run/day/type/actor/shop/text/data theo CONTRACT. `data` là cấu trúc mở nhưng chỉ serializer phía server xây dựng.
- Tạo `vnd` và `dec` theo test cũ. Serializer API không xuất `Infinity`.

## 2. Seed và World

`load_world(path=DATA_DIR / "seed.json") -> World` dùng đường dẫn tuyệt đối mặc định. Deep-copy dữ liệu khi tạo từng run. World giữ public/private/persona tách biệt; fees/trend/calendar theo SEED_DATA. Đây là hàm nạp file, không đọc env hoặc gọi mạng.

Seed đủ A–E với số đúng SEED_DATA. Riêng D phải có:

| Trường | Giá trị |
| --- | ---: |
| Giá bán / giá vốn | 175.000đ / 115.000đ |
| Tồn kho | 300 |
| Listing quality / search rank | 0,55 / 3 |
| Base impressions / rating | 2.500 / 4,6 |
| Ads daily cap / voucher cap | 45.000đ / 8% |
| Minimum profit / maximum breakeven ROAS | 18.000đ / 6,5 |

Facts của D chỉ gồm 3 tốc độ gió, sạc USB, pin 2000mAh và ba màu trong SEED_DATA. Lấy ảnh từ input D00. Khi chưa có ảnh, để list rỗng và UI báo thiếu; không tạo đường dẫn ảnh giả.

## 3. Finance — một nguồn công thức

Giữ chữ ký trong CONTRACT. Tạo Decimal từ string/int; không chuyển tiền qua binary float:

```python
net_price = round_half_up(price * (100 - voucher_pct) / 100)
unit_profit = round_half_up(net_price * (1 - fee_rate) - per_order - unit_cost)
be = net_price / unit_profit if unit_profit > 0 else inf
stop = ceil(be * 2) / 2
```

`fee_rate = (8 + 5 + 1.5) / 100`, tính bằng Decimal. Giữ phí cố định 3.000đ/đơn. `profit_per_unit` trả int.

`max_voucher_for` duyệt số nguyên từ 0 đến `min(30, rule_cap)`, lọc theo minimum profit và, khi có ads, theo maximum breakeven ROAS. Lấy giá trị lớn nhất còn hợp lệ. Không có ứng viên thì trả 0; validator vẫn phải nhận biết sản phẩm đang lỗ.

`clamp_to_rules` thực hiện theo thứ tự:

1. Copy package. Shop không cho ads thì đặt ads=0. Nếu có ads, lấy `min(requested_budget, hard_cap)`; kết quả dưới 10.000đ thì đặt về 0.
2. Sản phẩm lỗ ngay ở voucher 0% thì giữ content-only hoặc trả None. Không ép đạt minimum profit đối với content-only khi giá bán đã lỗ sẵn.
3. Tính voucher tối đa với ngân sách ads sau clamp; chỉ giảm voucher, không tăng.
4. Nếu ads>0, đặt `stop = max(current_stop, stop_threshold(BE))`. Khi ads=0, stop có thể là None.
5. Dựng Package mới rồi chạy lại cả kiểm tra phía shop và phía sàn. Không trả gói rỗng hoặc vẫn vi phạm.

`final_check` ghép violations của platform/shop và gắn `side="final"`. Chi tiết lỗi riêng chỉ ở context shop. Public reason không in private cap nếu seller chưa chủ động công khai.

## 4. Privacy — projection trước, lọc chữ sau

- Dựng context sàn/trọng tài từ typed PublicTurn, ShopPublic và public memory. Không `.model_dump()` toàn bộ Session/ShopState.
- `leak_guard` xử lý các cách viết giá vốn, minimum profit, profit ở voucher 0–30% và breakeven chính xác. Hỗ trợ dấu phân cách, `k`, `nghìn`; ưu tiên token dài nhất và ranh giới số. Giữ số 45.000đ khi đó là ngân sách counter được phép công khai.
- Text có nguy cơ lộ dữ liệu thì thay bằng public template an toàn. Không cố giữ mọi câu LLM. Private note chỉ UI đúng seller được đọc.
- Test projection bằng sentinel bí mật độc nhất. Test `leak_guard` bằng giá trị seed thực, không chỉ kiểm tên key.

## 5. State, store và log nhỏ

```text
MemoryStore.get(namespace, key, default=None)
MemoryStore.put(namespace, key, value)
MemoryStore.list(namespace)
MemoryStore.commit_batch(...)  # exact StoreWrite/MemoryCommit + metadata theo KNOWLEDGE_CONTRACT
EventLog.add(run_id, day, type, actor, shop_id, text_vi, data) -> Event
EventLog.since(run_id, after_seq) -> list[Event]
Session.new(settings, memory_enabled=True) -> Session
SessionManager.reset(memory_enabled=True, seed=42) -> Session
```

Store namespace là tuple `(run_id, compartment, shop_or_scope)`. Trả deep-copy để caller không sửa store qua object đã đọc. EventLog giữ lock quanh cấp seq và append; gọi model/provider bên ngoài lock. JSONL dùng UTF-8, `ensure_ascii=False`. SessionManager nhận factory/fake dependencies để test; production wiring ở lifespan của D03.

Rules chỉ nằm tại `session.states[shop_id].private.rules`, kèm `session.rules_version`. Memory không giữ bản rules độc lập. Session.knowledge_revision/memory_cursor là property đọc store metadata. Session dùng RLock, trạng thái busy và các receipt dict theo DEMO_CONTRACT. Đặt constructor defaults cho service chưa nối để fake tests chạy; không catch mọi ImportError để giấu module còn thiếu.

Settings thêm `MUSE_API_BASE_URL`, `MUSE_API_KEY`, `MUSE_VIDEO_MODEL` và `MEDIA_MODE` với mặc định `offline`. `MUSE_API_KEY` có `repr=False`; `describe()` ẩn toàn bộ token. LLM replay thiếu key vẫn resolve thành replay. Media mode độc lập với LLM mode: thiếu OpenAI LLM key không tự tắt Muse. Giữ nguyên SDK đã cài.

## Test và kết quả cần thấy

1. Profit ở voucher 0%: D=31.625đ, A=48.595đ, B=−4.705đ, E=21.645đ. D ở voucher 3% có profit=27.136đ.
2. D ở voucher 3% có BE≈6,2555 và stop=6,5. Voucher 4% bị `BREAKEVEN_TOO_HIGH`; voucher tối đa của D khi có ads là 3%.
3. DEFAULT_PACKAGE cho D clamp về ads=45.000đ, voucher=3%, stop=6,5; `final_check` trả list rỗng. B có content-only kèm warning và qua kiểm tra phù hợp.
4. Gói không ads với stop=null serialize được ra JSON. Infinity không ra HTTP; input HTTP thiếu field bắt buộc hoặc thừa field bị từ chối.
5. Clamp không tăng ads/voucher. Shop có stock=15 không được chạy ads.
6. Hai lần `Session.new` không dùng chung world/state/store; reset tạo run mới.
7. Event seq tăng; `since` chỉ trả event đúng run. Chưa cần load/stress test.
8. Settings không lộ Muse key. Replay không key vẫn là replay; `LLM_MODE=offline` và `MEDIA_MODE=live` không xung đột.

Chạy `.venv/bin/python -m pytest -q tests/unit/domain tests/unit/runtime tests/unit/core` và baseline integration health. Bàn giao code có test tiền/privacy trước khi chuyển D02. Reviewer kiểm công thức độc lập bằng tính tay D, không chỉ nhận test chép lại implementation.


## DTO và knowledge sources bắt buộc

- `domain/models/tools.py`: PublicContext, ShopContext, PackageCheck, ShopPackageCheck, RefereeContext, ContentContext, CampaignRecord/CampaignCatalogResult theo AGENT_TOOL_KNOWLEDGE. Không dùng alias ToolCheckResult khác hợp đồng.
- `domain/models/learning.py`: typed records/views/batches theo KNOWLEDGE_CONTRACT; Preference giữ evidence seq thật, hỗ trợ content_style và voucher_max_pct. D04 triển khai hành vi, D01 cấp schema trước để coder có thể làm riêng.
- `data/campaigns.json`: tối thiểu một campaign mẫu eligible ngành của D, một record expired để test. Gắn source_id, hạn theo ngày mô phỏng, eligibility; không giới thiệu là campaign sàn thật. Load vào World/catalog dependency, không để model đọc path tùy ý.
- Seed product facts giữ nguồn `seed:shop:<id>`; rules gắn version. LLM đọc dữ liệu qua role tools. Hạ tầng không cần vector DB.
- Store in-memory là adapter demo của cùng commit_batch interface: metadata/revision/cursor/receipt và 4 bins cập nhật atomic theo KNOWLEDGE_CONTRACT. D04 nhận adapter này; DB member thay bằng transaction ở adapter riêng sau đó.
- `MAX_LIVE_CALLS_PER_SESSION=64` trong config demo/.env.example. LLMClient dùng cùng budget cho native loop của 5 roles; không tạo counter riêng trong runner.
- Tests bổ sung: đúng type từng fixture tool/view, catalog expired/khác category bị loại (filter do D02a), không có Persona trong public/private tool DTO. Không import app.agents từ domain.
