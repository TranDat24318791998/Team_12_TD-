# Plan của Toàn — Agent, Tools và Knowledge

Cập nhật 31/10/2026 theo phần việc Toàn nhận từ đầu: **agent + điều phối + tool adapters + Knowledge + học ban đêm**. Đây là plan giao coder/reviewer, chưa phải chức năng đã implement. Bản này thay lịch trước đã dành quá nhiều thời gian cho UI/media và chỉ dùng LLM structured output.

Thư mục `docs/plans/toan/` chứa bộ plan/code task riêng của Toàn. Bắt đầu đọc file này, rồi giao từng task trong `tasks/` theo lịch bên dưới.

```text
docs/plans/toan/
  README.md                  Phạm vi, lịch và prompt giao coder/reviewer
  AGENT_TOOL_KNOWLEDGE.md     Đặc tả agent, tool calling và quyền
  KNOWLEDGE_CONTRACT.md      Năm ngăn memory, retrieval và learning
  AGENT_SCOPE_MAP.md         Phần việc gốc và đầu nối với team
  tasks/                     7 task của Toàn: D00, D01, D02a, D02, D04, D03, D06
```

Tất cả lệnh và đường dẫn source (`app/`, `tests/`, `contracts/`...) tính từ **gốc repo**, không từ thư mục plan. Thư mục này gom tài liệu giao việc; code vẫn nằm theo module trong kiến trúc chung. D01/D03 có phần giao nhau với model/store/API: giữ owner đã ghi trong task và phối hợp trước khi sửa chung.

Chi tiết riêng được cập nhật tại đây. Chỉ thay tài liệu chung khi đổi interface, schema, đường dẫn hoặc quy ước ảnh hưởng member khác; không chép lịch/prompt/task riêng sang file chung.

## 1. Kết quả cần bàn giao

1. Năm vai trò Shop, Platform, Referee, Content và Learning dùng OpenAI. Có vòng **model phát tool call → backend kiểm quyền/input → chạy tool → trả ToolMessage → model dùng kết quả**. Output cuối vẫn phải đúng schema và qua code kiểm nghiệp vụ.
2. Tool đọc/tính toán có allowlist theo vai trò. Đổi rules, áp dụng gói/nội dung, ghi memory và gọi provider có phí nằm sau gate của workflow. Có bảng đủ 15 adapter gốc và mapping 32 dòng workbook; không biến mọi action thành function cho LLM tự gọi.
3. Knowledge đủ năm ngăn: Rules, Preferences, History, Calibration, Lessons; typed records/views, source/evidence, scope theo run/shop/ngành, cập nhật có version/cursor. Agent truy vấn rồi dùng được dữ liệu ở lần xử lý sau.
4. LangGraph điều phối sàn/shop/trọng tài, không vượt ba lượt sàn. Runtime nối seller approval, content, kết quả ngày và learning. Demo chính là D ngày 1–2; helper không hardcode D, có fixture A–E cho tiền, stock, monitor và renew.
5. Bàn giao đầu nối chạy được cho member DB/market/API/media, cùng fake đúng contract. OpenAI ảnh, Muse Gateway video vẫn là provider đã chốt; provider/UI thuộc lane tích hợp của member tương ứng.

Không lấy transcript offline, file memory hoặc UI hiện style làm bằng chứng đã hoàn thành agent/tool/knowledge. Acceptance phải kiểm tool result đi vào model và record đã học thay đổi input/quyết định lần sau.

## 2. Phạm vi của Toàn và phụ thuộc team

| Toàn/agent code phải làm | Member khác cung cấp; Toàn nối và kiểm |
|---|---|
| Bounded tool runner, schema, role ACL, prompt và fallback | OpenAI key/model qua cấu hình chung |
| Shop/Platform/Referee graph, kiểm tiền/privacy | Seed shop, trend, fee và market forecast/actual |
| Knowledge views, retrieval, learning, confirm preference | Store/EventLog adapter; DB bền vững theo interface đã chốt |
| Runtime monitor/match/renew, card và seller decision | HTTP/UI hiển thị state, nhận quyết định |
| Context Content Agent và chứng minh đọc style đã xác nhận | ContentService start/retry/apply, OpenAI Images, Muse video |
| Headless integration, trace tool/evidence, hợp đồng bàn giao | Simulator/proof, video demo và slide |

DB/market/media chưa xong: dùng fake trong tests/headless harness, ghi rõ nguồn; tiếp tục hoàn thành phần Toàn. **Fake không đạt gate tích hợp thật.** Nếu một người phải tự làm cả UI/DB/media từ khung hiện tại, mốc 2 giờ không đủ cơ sở để cam kết toàn sản phẩm; không cắt agent/tool/knowledge để che thiếu phụ thuộc.

## 3. Nguồn quyết định implementation

- [AGENT_TOOL_KNOWLEDGE.md](AGENT_TOOL_KNOWLEDGE.md): tool catalog, quyền, flow và điều kiện agent hoàn thành.
- [KNOWLEDGE_CONTRACT.md](KNOWLEDGE_CONTRACT.md): schema năm ngăn, read/write interface, evidence và retrieval.
- [AGENT_SCOPE_MAP.md](AGENT_SCOPE_MAP.md): phần việc gốc, 15 adapter và toàn bộ 32 dòng workbook.
- [DEMO_CONTRACT.md](../../DEMO_CONTRACT.md): HTTP/state/media và phạm vi demo; agent/knowledge theo hai contract trên.
- [CONTRACT.md](../../CONTRACT.md), [SEED_DATA.md](../../SEED_DATA.md), [ARCHITECTURE.md](../../ARCHITECTURE.md): model giữ nguyên, số seed, vị trí module/hướng import.
- [MUSE_API.md](../../MUSE_API.md): video wire contract và response còn phải xác minh.

Không cần vector DB/embedding để làm knowledge trong bản giao việc gốc. Truy vấn deterministic theo khóa/ngành/scope là implementation đủ cho dữ liệu hiện tại. Static knowledge gồm seed/facts/fees và catalog campaign mẫu có nguồn; learned knowledge gồm năm ngăn trên.

## 4. Lịch 120 phút: một coder và một reviewer

Đây là timebox có checkpoint, không phải cam kết tốc độ code/provider. Reviewer nhận patch nhỏ ngay khi coder xong; không ghi cùng file với coder.

| Phút | Coder | Reviewer / bằng chứng qua gate |
|---|---|---|
| 0–8 | D00: scope, contract, input và fixtures bàn giao | Capability, ownership, nguồn knowledge |
| 8–23 | D01: models/finance/state, store seam, seed catalog | D 3%/4%, privacy, typed DTOs |
| 23–43 | **D02a: tool runner và role tools** | ToolMessage thật trong fake transport; denied tool không chạy |
| 43–66 | D02: 3 agent trong negotiation graph | D counter đúng; model tiêu thụ tool result; bounded loop |
| 66–86 | **D04: năm ngăn Knowledge và learning** | Atomic write, evidence, confirm, lần đọc sau đổi hành vi |
| 86–104 | D03: runtime ngày/approval và đầu nối team | Apply sau approval; monitor/renew; no duplicate effect |
| 104–114 | D06: headless flow + nối adapter team đã sẵn sàng | Trace, tests, tách core/fake/live gates |
| 114–120 | Chỉ sửa blocker và bàn giao | Liệt kê chính xác đã chạy/chưa chạy |

D05/D05a do member media/UI làm song song, không chiếm quỹ code lõi ở bảng này. Nếu có hai coder: sau D01, lane A làm D02a→D02; lane B làm D04 typed store/gateway trước, nối Learning runner sau D02a. Integrator duy nhất giữ Session/manager/API/model. Không chia một module cho hai người ghi đồng thời.

Checkpoint phút 43: tool request/result/terminal loop chạy test. Phút 86: năm ngăn và next-use test. Trễ thì giảm polish/UI, dashboard, số lần demo media; không bỏ hai checkpoint này rồi gọi là xong phần Toàn.

## 5. Task của Toàn

| ID | File | Hoàn thành khi |
|---|---|---|
| D00 | [00-start.md](tasks/00-start.md) | Owner dependency, DTO/provider/input và fixtures |
| D01 | [01-foundation.md](tasks/01-foundation.md) | Typed models, tiền/privacy, Session, Store seam |
| D02a | [02a-tool-runtime.md](tasks/02a-tool-runtime.md) | Native tool loop, allowlist và trace có test |
| D02 | [02-agents-referee.md](tasks/02-agents-referee.md) | 3 agent gọi tools trong graph, kiểm cuối đúng |
| D04 | [04-learning.md](tasks/04-learning.md) | 5 bins, typed views, evidence, learning/confirmation/next-use |
| D03 | [03-workflow-api.md](tasks/03-workflow-api.md) | Card/HITL/day/monitor và đầu nối team |
| D06 | [06-review-demo.md](tasks/06-review-demo.md) | Review riêng core agent/knowledge và tích hợp thật |

### Đầu nối với member khác

Các task dưới đây để phối hợp tích hợp, không nằm trong bộ task riêng của Toàn:

| Owner | Task | Toàn cần nhận |
|---|---|---|
| Media | [D05a — Media API](../../../tasks/demo/05a-media-api.md) | OpenAI Images/Muse adapters, jobs/cache |
| Content/UI | [D05 — Nội dung và giao diện](../../../tasks/demo/05-ui-content.md) | ContentService dùng runner/context, seller review và UI |

Hợp đồng runtime/HTTP/media dùng chung ở [docs/DEMO_CONTRACT.md](../../DEMO_CONTRACT.md); các member đọc những phần liên quan đến đầu nối của mình.

## 6. Prompt giao coder/reviewer

```text
Làm task Dxx tại docs/plans/toan/tasks/<file>.md trên main repo Team_12_TD-.
Đọc AGENTS.md, docs/plans/toan/README.md, contract được task trỏ tới, rồi task.
Ưu tiên phần Toàn: Agent + Tools + Knowledge. Làm Output/acceptance đầy đủ;
UI/provider/DB teammate chưa có thì dùng fake đúng interface ở tests, ghi rõ giới hạn.
Không thay tool calling bằng nhét toàn bộ memory vào prompt; không chỉ ghi memory mà bỏ test đọc lại.
Native tool runner và five-bin knowledge là bắt buộc; không tự thêm vector DB/framework.
Chạy test task. Bàn giao BASE_SHA/HEAD_SHA, file đổi, lệnh/kết quả,
trace input→tool_call→tool_result→decision và record/evidence được đọc lần sau.
Đánh dấu phần fake, offline, live chưa smoke; không in secrets.
```

```text
Review task Dxx so với các contract được task trỏ tới và docs/plans/toan/AGENT_SCOPE_MAP.md.
Đọc diff/caller, chạy test trọng tâm. Chặn nếu thiếu native tool loop/role ACL,
knowledge bin/write/read-back, evidence, privacy, tiền, approval/version hoặc test fail.
Kiểm tool response thực sự đi vào model và record đã học tác động lần gọi sau.
Không chấp nhận event tool giả hoặc summary để thay hành vi thực.
Không yêu cầu vector DB, auth/multiuser, queue, anti-spam hoặc full UI ngoài scope.
Mỗi lỗi: mức độ, file:dòng, input, expected/actual, sửa tối thiểu và test.
Báo CORE PASS/FIX REQUIRED và INTEGRATION LIVE PASS/PENDING riêng biệt.
Không ghi file đồng thời với coder; chỉ review sau SHA/patch được bàn giao.
```

## 7. Bằng chứng và thứ để sau

**Core đạt:** D negotiation qua tools; role trái quyền bị chặn; Rules luôn enforce dù memory OFF; candidate chưa thành rule trước seller Yes; history/calibration/lessons/preferences được ghi/đọc đúng scope; Content lần sau dùng confirmed style; Platform lần sau đọc approved history/lessons và hành vi thay đổi trong fixture có kiểm soát. Test không gọi mạng trả phí.

**Live đạt:** khi có OpenAI config, có trace một tool round-trip thật; Content/media member trả ảnh OpenAI và video Muse mở được. Fake transport chỉ chứng minh core logic. Token Muse local không có nghĩa API đã smoke.

Demo 3 phút thao tác không tính render: tool trace thương lượng → seller accept → content/retry/apply → night tạo candidate → ngày 2 confirm → lời gọi sau dùng style/history. Có thể dùng headless script và event viewer tối giản nếu UI member chưa nối; ghi đúng mức hoàn thiện.

Để sau: multiuser/auth/cloud, restart recovery, vector retrieval, chat tự do, 3D, chống spam, dashboard cầu kỳ và proof toàn hệ thống. Proof do simulator owner làm với `days` cấu hình (mặc định nguồn gốc 6 ngày); dữ liệu/cohort 7 ngày không tự thay nghĩa proof. Không báo memory tăng doanh thu từ hai ngày demo. Không cắt money/privacy/approval/native-tools/knowledge để kịp giờ.
