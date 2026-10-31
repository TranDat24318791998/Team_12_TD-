# Contract replay và nghiệm thu toàn luồng

Áp dụng SI07. Persistence do member DB cung cấp theo PUBLICATION_CONTRACT. Agent improve triển khai adapter RAM, contract tests và dependency injection; không viết SQL migration hoặc một DB implementation thứ hai.

## 1. Replay

Cache nằm trong LLMClient hoặc helper `app/infrastructure/replay.py`, được gọi trước reserve live budget. Offline không gọi mạng. Replay không gọi provider kể cả khi máy có key; cache miss chạy fallback hiện hành và ghi REPLAY_MISS. Live gọi thật khi có cấu hình, reserve đúng một slot trước mỗi network request và chỉ cache response đã parse được theo protocol runner.

Schema chốt:

| DTO | Fields |
| --- | --- |
| `ReplayBinding` | `kind:Literal['run','negotiation','card','prediction','fact','lesson','preference','turn','tool_call']`, `token:str`, `value:str` |
| `ReplayEntry` | `request_hash:str`, `role:Literal['platform','shop','referee','content','learning']`, `shop_id:str`, `visibility:Literal['public','shop_private']`, `model_id:str`, `response_json:str`, `bindings:list[ReplayBinding]` |
| `ReplayManifest` | `schema_version:Literal['self-improve.v1']`, `source_run_id:str`, `shop_id:str`, `config_hash:str`, `entries:list[ReplayEntry]` |

response_json là serialized AIMessage theo public fields content/tool_calls/invalid_tool_calls; validate tên tool, args schema, call IDs và source bằng runner hiện có sau khi load, không eval/import nội dung. Không cache invalid response hoặc exception. Manifest không chứa credentials. Shop reply có private_note phải nằm ở visibility shop_private; cache mặc định lưu trong run directory gitignored, không xuất private entries vào public replay export.

Request hash dùng canonical JSON của role, shop_id, model ID và model parameters, tools/output schema, tool_choice/parallel flag, base/skill behavior, memory_enabled và ordered messages. Bỏ timestamps/request UUID/run_name. Giữ đầy đủ dữ liệu nghiệp vụ, gồm private values trong Shop request hash nhưng không ghi chúng vào public log.

Backend cấp binding map từ IDs nó tạo, không suy đoán ID bằng regex trong text người dùng. Chuẩn hóa typed fields run/card/negotiation/prediction/fact/turn IDs thành token ổn định theo shop/day/attempt/ordinal; tool_call IDs theo vị trí message/call. JSON content của ToolMessage phải parse rồi chuẩn hóa theo field; opaque string chứa dynamic ID không map được → không cache request đó. Skill artifact chứa fact/lesson refs cũng phải có semantic projection, không nhét operational hash chứa run ID vào key gián tiếp.

Khóa token chốt: run=`RUN`; negotiation theo `(shop,day,attempt)`; card theo `(negotiation token,card version)`; prediction theo `(shop,target_day,hash state/package không có run ID)`; fact theo `(kind,card token,negotiation token,package_applied_seq,support_seq)`; lesson theo `(scope,normalized text)`; preference theo `(shop,field,value)`; turn/tool_call theo thứ tự trong invocation. Token phức hợp là `kind:SHA256(canonical tuple)`. Seq hiện được cấp riêng từng run nên giữ nguyên seq/cutoff; khác event history là input khác, được miss. Cùng token map nhiều IDs không phân biệt được → miss, không chọn tùy ý.

Normalize các ID fields và danh sách refs bằng bindings; không replace substring trong prose. Lesson text/score/version, preference value/status, packages, facts và thứ tự messages đều được giữ. Với bundle, thay artifact_hash bằng SHA256 của compiled skill đã normalize fact/lesson refs, giữ base_hash và version; không giữ hash cũ chứa run IDs. Model outputs LessonOp.lesson_id/pref refs được rebind ngược bằng cùng mapping. Missing binding là miss. Request envelope cho hashing có exact keys `role,shop_id,model_id,model_parameters,tools,tool_choice,parallel_tool_calls,base_hash,skill_semantics,memory_enabled,messages`; canonical serializer của CORE_CONTRACT, không nhận credentials hoặc request timestamp.

Replay load phải khớp role, shop, visibility và config. Rebind IDs trong response về run hiện tại theo map; unknown token → miss, không trả ID của run cũ. Tool calls nhận fresh invocation-local IDs và ToolMessages khớp đúng IDs đó. Cùng nội dung nghiệp vụ ở run mới có thể hit; đổi voucher, evidence, base/learned policy, model hoặc memory flag phải miss. Không phát lại nguyên chuỗi quyết định ON cho OFF.

Trong replay không có model cấu hình, dùng model ID của manifest để kiểm request; có model cấu hình thì phải khớp. Output source=replay chỉ khi hit hợp lệ, fallback vẫn offline. Budget slots không giảm cho hit/miss offline.

## 2. Contract tests cho member DB

Tạo `tests/contract/test_knowledge_repository.py` nhận fixture `repository_factory`. Mặc định dùng MemoryStore; member DB thay factory để chạy cùng bộ assertions, không sửa expected behavior.

| Case | Expected |
| --- | --- |
| Batch có một write sai | Không record/revision/cursor nào đổi |
| Snapshot cùng key/hash | Trả snapshot cũ; khác hash conflict |
| Hai workers claim cùng phase | Một owner được chạy, worker còn lại nhận reserved của owner đó |
| Terminal reflection trùng | Cùng payload trả cũ; payload khác conflict |
| Commit night có versions và records | Tất cả cùng xuất hiện hoặc cùng rollback |
| Cùng night key nhưng publication khác | NIGHT_REQUEST_CONFLICT |
| CAS stale | Không ghi dở; caller có thể rebase theo policy đã chốt |
| Lesson bị xóa hoặc eviction | Artifact version tiếp theo không còn policy tương ứng |
| Budget đồng thời vượt cap | Chỉ số slot trong cap được granted |
| Reopen adapter durable | Records, snapshot, receipts, versions, slots giữ nguyên |
| Reserved từ process đã dừng | Recovery chuyển unknown; không gửi model lại |

RAM đạt các case trong process. Hai case reopen/recovery durable phải chạy với adapter member DB mới được đánh durable PASS. Nếu chưa được cung cấp factory thì báo durable NOT_CONNECTED; vẫn hoàn tất toàn bộ improve core qua RAM. Đây là dependency được inject, không còn quyết định schema để coder tự đoán.

## 3. Headless proof dùng code thị trường hiện có

Giữ `simulation.run(settings, days, memory_enabled, seed) -> RunResult` và `compare(run_on,run_off) -> ProofReport`. `scripts/run_sim.py --days 7` chạy mặc định shop D, hai run độc lập, cùng seed/config, LLM offline. Hỗ trợ days1..7 và --shop A/B/C/D/E; defaults 7/D. Một lần chạy so sánh tương ứng một shop, không nhận kết quả D là proof cả năm shop.

Market adapter trong `app/simulation/market.py` dùng các hàm đã có của `data/growth_data/simulation.py`: forecast, channel_metrics, aggregate. Import từ package local `data.growth_data`; không copy engine hoặc dùng FakeMarket cho proof. Adapter chỉ map domain DTO/dict, effective package và stock. channel_metrics nhận private cost trong backend; model context không nhận cost/hidden noise/persona.

simulate_day tính cho demo_shop, dùng ads=0 nếu paused/không active, voucher đúng active state, quality hiện tại. Aggregate paid revenue/paid spend cho ROAS, giữ integer VND từ Data finance. Stock giảm đúng một lần ở settlement do runtime quản lý. Return DayMetrics, không cập nhật knowledge. Ghi source=offline_simulator; toàn bộ thị trường vẫn là dữ liệu mô phỏng.

Forecast trên Card là tổng horizon gói. Calibration dùng snapshot ngày riêng: ngay trước settlement, sau monitor và content approval, chụp effective package/listing/stock, tính raw daily bằng forecast của Data với duration_days=1 trong dict nội bộ, factor dùng record trước actual. Domain Package trong snapshot vẫn là gói hiệu lực thật. Không cộng content quality gain lần hai khi listing đã apply; Card projection trước apply có thể tính một lần gain theo policy hiện hành. Prediction_id = SHA256 canonical [run,shop,day,effective package,public state trước settlement]. Retry sau settled giữ prediction cũ, không chụp lại sau actual.

Thêm `market.record_daily_prediction(session, day) -> None`, gọi trong close_day trước simulate_day và chỉ khi day chưa settled. Giữ activation forecasts cho Card/context; daily snapshot hiện hành là nguồn calibration. FakeMarket tests thêm method tương ứng. Thiếu adapter dự báo thì skip calibration có nhãn; proof yêu cầu đủ daily snapshots, không tự tạo số mặc định.

Headless content dùng adapter offline ở `app/simulation/content.py`, cùng ContentService interface: Content Agent tạo chữ qua runner; ảnh lấy original/placeholder thật trong data/datasets/originals, copy vào run media directory và gắn source offline_original_asset. Không gọi provider ảnh/video, không gắn nhãn generated. SellerSimulator quyết định bằng persona trong backend; chỉ accept/reject/negotiate/question actions đang được runtime hỗ trợ. Kịch bản voucher edit được kiểm bằng integration fixture events đã duyệt, không giả UI edit đã có.

Runner gọi cùng confirm_brief/start_day/submit_decision/content apply/close_day của runtime. Quy tắc seller headless chốt: accept offer hợp lệ; question Có ở arm ON theo persona fixture cố định của run; feedback ngày1 là câu nền sáng cho D; chọn cover A; skip_video=true cho asset offline; reject khi failed/no_fit. Memory OFF không tự thêm preference/rule confirmation. Ghi rõ seller_policy_version và content_effect=simulated vào report. Không viết luồng business thứ hai trong script.

## 4. RunResult và report

RunResult ở `domain/models/metrics.py`: `run_id:str`, `shop_id:str`, `seed:int`, `days:int`, `memory_enabled:bool`, `mode:Literal['live','replay','offline']`, `daily_metrics:list[DayMetrics]`, `forecast_errors:list[float]`, `negotiation_rounds:list[int]`, `budget_slots_used:int`, `source_counts:dict[str,int]`, `skill_versions:dict[str,int]`, `valid:bool`, `invalid_reasons:list[str]`, `report_path:str|None=None`.

Giữ ProofReport/ProofMetric hiện có. Tổng profit_after_fees, orders, ads_spend từ daily_metrics; forecast MAE là mean(abs(issued_point-actual_orders)) trên cùng shop/day; rounds là mean completed attempts. Empty denominator thì bỏ metric đó và ghi note, không điền NaN/Infinity/0 giả. better=high cho profit/orders, low cho spend/error/rounds; giảm spend tự nó không chứng minh chất lượng kinh doanh tốt hơn.

Report phụ JSON/Markdown ghi run IDs, seed, days, shop, engine/config/base hashes, model/media source, budget slots, calibration samples/factors, artifact hashes/effective days, test/eval level và durable adapter status. Không yêu cầu ON thắng OFF để test qua; test kiểm cách đo đúng và reproducibility. Fake model chứng minh dùng đúng skill; provider quality cần evaluator baseline/candidate qua provider riêng. ON/OFF là tác động tổng hợp của memory, không quy hết cho skill evolution.

Hai run không chia sẻ Session/store learned records/cache decisions khác input. Cùng seed và configs phải tái tạo cùng metrics ở offline. Memory OFF giữ Rules ban đầu, validators, stop mechanisms; bỏ learned records và reflection. Public reports không chứa cost/rules/private notes từng shop.
