import test from 'node:test';
import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import {Product} from '../src/components/Product.jsx';
import {Proposal} from '../src/components/Proposal.jsx';
import {ContentReview} from '../src/components/ContentReview.jsx';
import {EventFeed} from '../src/components/EventFeed.jsx';
import {AgentActivity} from '../src/components/AgentActivity.jsx';
import {Logo,Progress} from '../src/components/Shell.jsx';
import {previewComparisonDays} from '../src/previewComparison.js';
import {ControlPanel} from '../src/pages/Shop.jsx';
import {NightPage} from '../src/pages/Night.jsx';
import {ProofReport} from '../src/pages/Proof.jsx';
import {DemoPage} from '../src/pages/Demo.jsx';
const noop=()=>{};
const shop={shop_id:'Z',name:'Shop Ánh Dương <b>',title:'Đèn bàn USB & đế gỗ',description:'Đèn bàn có đế gỗ.',category:'den_ban',price:299000,stock:17,rating:4.9,images:['https://demo.test/media/lamp.jpg'],attributes:['Sạc USB','2 màu: Đen, Nâu'],active_voucher_pct:7,listing_quality:.81,search_rank_page:1};
const state={run_id:'database-run',day:1,step:'idle',demo_shop:shop,demo_shop_original:shop,memory_enabled:true,mode:'offline',last_night:null,active_package:null};
const button=(html,name)=>html.match(new RegExp('<button\\b[^>]*data-'+name+'="true"[^>]*>'))?.[0];

test('shop and demo share the supplied ShopPilot AI brand image',()=>{
  const html=renderToStaticMarkup(<Logo preview={false}/>);
  assert.match(html,/ShopPilot AI, trang shop/);assert.match(html,/shoppilot-ai\.png/);assert.match(html,/alt="ShopPilot AI"/);
});

test('React product renders a different database product without seed-specific labels',()=>{
  const html=renderToStaticMarkup(<Product shop={shop} onAddCart={noop} onNotice={noop}/>);
  assert.match(html,/299\.000đ/);assert.match(html,/<strong>17<\/strong>/);assert.match(html,/Shop Ánh Dương &lt;b&gt;/);
  assert.match(html,/Đèn bàn USB &amp; đế gỗ/);assert.match(html,/lamp\.jpg/);assert.match(html,/data-color="Đen"/);assert.match(html,/data-color="Nâu"/);
  assert.doesNotMatch(html,/Nhà Bé Lan|Quạt mini|data-color="Hồng"|shoppilot-ai\.png/);assert.doesNotMatch(html,/<b>/);
});
test('demo shop identity uses the supplied logo without changing the shop name',()=>{
  const html=renderToStaticMarkup(<Product shop={{...shop,shop_id:'D'}} onAddCart={noop} onNotice={noop}/>);
  assert.match(html,/alt="Logo ShopPilot AI"/);assert.match(html,/shoppilot-ai\.png/);assert.match(html,/Shop Ánh Dương &lt;b&gt;/);
});
test('missing images and missing color attributes do not invent product variants',()=>{
  const html=renderToStaticMarkup(<Product shop={{...shop,images:[],attributes:['Sạc USB']}} onAddCart={noop} onNotice={noop}/>);
  assert.match(html,/product-placeholder\.svg/);assert.doesNotMatch(html,/data-color=/);
});
test('question-only cards render explicit answers with no new spending proposal',()=>{
  const card={card_id:'q-1',kind:'question',package:null,rule_question:{text_vi:'Lần sau dùng nền sáng?'}};
  const html=renderToStaticMarkup(<Proposal card={card} onDecision={noop} onNegotiate={noop}/>);
  assert.match(html,/data-question="true"/);assert.match(html,/data-question="false"/);assert.doesNotMatch(html,/data-decision|LÃI ƯỚC TÍNH|Quảng cáo/);
});
test('offer shows server amounts, warnings and an optional rule question separately',()=>{
  const card={kind:'offer',package:{content_refresh:true,ads_daily_budget:45000,voucher_pct:3,stop_roas_below:6.5,stop_after_days:2,duration_days:3},forecast:{low:18,high:30},profit_after_fees_per_unit:27136,breakeven_roas_display:6.5,warnings_vi:['Đây là dự báo.'],reasons_vi:['Từ dữ liệu đã quan sát.'],rule_question:{text_vi:'Ghi nhớ ảnh nền sáng?'}};
  const html=renderToStaticMarkup(<Proposal card={card} pending onDecision={noop} onNegotiate={noop}/>);
  assert.match(html,/45\.000đ\/ngày/);assert.match(html,/27\.136đ/);assert.match(html,/6,5/);assert.match(html,/Chưa trừ chi quảng cáo/);
  assert.match(html,/name="rule-answer"/);assert.match(html,/Đây là dự báo/);assert.match(html,/data-decision="accept" disabled/);
});
test('content attempt 3 disables retry; running covers disable publication while failed video is tolerated',()=>{
  const draft={version:3,title:'Tiêu đề đã duyệt',description:'Mô tả',images:[{option:'A',status:'running',path:null},{option:'B',status:'failed',path:null}],video:{status:'failed',path:null},checks:[],feedback_history:[]};
  const html=renderToStaticMarkup(<ContentReview draft={draft} original={shop} onRetry={noop} onApply={noop} onNotice={noop}/>);
  assert.match(button(html,'retry'),/disabled/);assert.match(button(html,'apply'),/disabled/);assert.match(html,/Chưa tạo được video/);assert.match(html,/Lần 3 \/ 3/);
});
test('ready covers require an explicit video choice',()=>{
  const draft={version:1,title:'Tiêu đề',description:'Mô tả',images:[{option:'A',status:'cached',path:'https://demo.test/media/a.jpg'}],video:{status:'running'},feedback_history:[]};
  const html=renderToStaticMarkup(<ContentReview draft={draft} original={shop} onRetry={noop} onApply={noop} onNotice={noop}/>);
  assert.ok(button(html,'apply'));assert.match(button(html,'apply'),/disabled/);assert.match(html,/Dùng ảnh, bỏ qua video/);
});
test('seller backstage escapes event text and excludes other shops',()=>{
  const events=[{seq:1,run_id:state.run_id,day:1,shop_id:'Z',actor:'shop_agent',type:'shop_turn',ts:'10:00',text_vi:'<img src=x onerror=alert(1)>',data:{private_note_vi:'Ghi chú riêng của shop Z.'}},{seq:2,run_id:state.run_id,day:1,shop_id:'A',actor:'shop_agent',type:'shop_turn',ts:'10:00',text_vi:'Bí mật shop khác',data:{private_note_vi:'Không hiển thị.'}}];
  const html=renderToStaticMarkup(<EventFeed state={state} events={events} preview={false}/>);
  assert.match(html,/&lt;img/);assert.match(html,/Ghi chú riêng của shop Z/);assert.doesNotMatch(html,/Bí mật shop khác|<img src=x/);
});
test('configured live mode and actual offline fallback are labeled separately',()=>{
  const live={...state,mode:'live'};
  const panel=renderToStaticMarkup(<ControlPanel state={live} preview={false} onReset={noop} onStart={noop} onEndDay={noop}/>);
  assert.match(panel,/Chế độ LLM cấu hình/);assert.match(panel,/Trực tiếp/);assert.doesNotMatch(panel,/Dữ liệu LLM/);
  const completed={seq:1,run_id:state.run_id,day:1,shop_id:'Z',actor:'system',type:'agent_completed',ts:'10:00',text_vi:'Agent xử lý dữ liệu theo quyền.',data:{role:'platform',source:'offline',error_code:'provider_unavailable'}};
  const feed=renderToStaticMarkup(<EventFeed state={live} events={[completed]} preview={false}/>);
  assert.match(feed,/AGENT SÀN/);assert.match(feed,/Nguồn thực tế: Ngoại tuyến \(quy tắc dự phòng\)/);assert.match(feed,/Mã lý do: provider_unavailable/);
  assert.doesNotMatch(feed,/Trực tiếp từ LLM/);
});
test('learning retry control follows the backend capability',()=>{
  const failed={...state,step:'day_done',learning_status:'failed',learning_version:2,learning_day:1};
  const render=allowed=>renderToStaticMarkup(<DemoPage run={{state:{...failed,learning_retry_allowed:allowed},events:[],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.match(render(true),/Thử lại bước học/);assert.match(render(false),/Bỏ qua bước học/);assert.doesNotMatch(render(false),/Thử lại bước học/);
});
test('night uses published learning source and does not infer an LLM from configured mode',()=>{
  const summary={day:1,history_updates:['Ghi nhận quyết định.'],pref_candidates:['Ưu tiên ảnh nền sáng.'],source:'offline',calibration:{factor:1,points:0},lesson_ops:[],rejected_ops:0};
  const completed={seq:1,run_id:state.run_id,day:1,shop_id:'Z',type:'agent_completed',data:{role:'learning',source:'offline',error_code:'provider_unavailable'}};
  const html=renderToStaticMarkup(<NightPage run={{state:{...state,mode:'live',last_night:summary},events:[completed]}} preview={false}/>);
  assert.match(html,/Ghi nhận quyết định/);assert.match(html,/Ưu tiên ảnh nền sáng/);assert.match(html,/Ngoại tuyến \(quy tắc dự phòng\)/);assert.match(html,/provider_unavailable/);
  assert.match(html,/Ghi nhận từ người bán/);assert.doesNotMatch(html,/Cần chủ shop xác nhận/);
  const unknown=renderToStaticMarkup(<NightPage run={{state:{...state,mode:'live',last_night:{...summary,source:undefined}},events:[]}} preview={false}/>);
  assert.match(unknown,/Chưa có dữ liệu · Code kiểm tra/);assert.doesNotMatch(unknown,/LLM đề xuất|Trực tiếp từ LLM/);
});
test('day seven complete disables start and has no day eight control',()=>{
  const html=renderToStaticMarkup(<ControlPanel state={{...state,day:7,step:'complete'}} preview={false} onReset={noop} onStart={noop} onEndDay={noop}/>);
  assert.match(button(html,'start'),/disabled/);assert.match(html,/Đã hoàn tất 7 ngày/);assert.doesNotMatch(html,/Bắt đầu demo|Tiếp tục demo/);
});
test('brief shows only the server preset and preserves an older confirmed request',()=>{
  const preset={intent:'increase_orders',goal_vi:'Mục tiêu do máy chủ cung cấp',allow_ads:true,ads_daily_cap:12345,content_refresh:true,duration_days:3};
  const render=value=>renderToStaticMarkup(<ControlPanel state={value} preview={false} onReset={noop} onStart={noop} onEndDay={noop} onConfirm={noop}/>);
  const html=render({...state,brief_editable:false,brief_preset:preset});
  assert.match(html,/Yêu cầu demo cố định/);assert.match(html,/Mục tiêu do máy chủ cung cấp/);assert.match(html,/12\.345đ/);assert.match(html,/data-confirm-brief/);
  assert.doesNotMatch(html,/<input|<textarea|brief-goal|brief-cap/);
  const missing=render({...state,brief_editable:false});assert.match(missing,/Chưa có yêu cầu demo cố định/);assert.doesNotMatch(missing,/data-confirm-brief|45\.000đ|24 đơn/);
  const old=render({...state,brief_editable:false,brief_preset:preset,brief:{confirmed:true,goal_vi:'Yêu cầu cũ đã duyệt',allow_ads:true,ads_daily_cap:5000,duration_days:3}});
  assert.match(old,/Yêu cầu đã xác nhận ban đầu/);assert.match(old,/Yêu cầu cũ đã duyệt/);assert.match(old,/5\.000đ/);assert.doesNotMatch(old,/Mục tiêu do máy chủ cung cấp|data-confirm-brief/);
  assert.doesNotMatch(render({...state,step:'complete',brief_editable:false,brief_preset:preset}),/Mục tiêu do máy chủ cung cấp/);
});
test('final night uses seven-day completion and null ROAS is not reported as zero',()=>{
  const finalState={...state,day:7,step:'complete',last_night:{day:7,history_updates:[],pref_candidates:[],calibration:{factor:1,points:0,mape_today:null},lesson_ops:[],rejected_ops:0,memory_md_path:'/api/reports/memory-7'}};
  const html=renderToStaticMarkup(<NightPage run={{state:finalState,events:[{day:7,shop_id:'Z',type:'market_result',data:{metrics:{orders:0,roas:null,ads_spend:0}}}]}} preview={false}/>);
  assert.match(html,/Hoàn tất 7 ngày/);assert.match(html,/ROAS hôm nay/);assert.match(html,/class="metric-value">—/);assert.match(html,/Tải báo cáo bộ nhớ/);assert.doesNotMatch(html,/Sang ngày 8/);
});
test('proof respects the response horizon and does not fabricate missing values',()=>{
  const report={days:7,seed:42,run_on:'r-on',run_off:'r-off',metrics:[{key:'forecast_mape',label_vi:'Sai số dự báo',better:'lower',on:null,off:12,unit:'%'}],note_vi:'Một phía chưa có đủ điểm dự báo.'};
  const html=renderToStaticMarkup(<ProofReport report={report} preview={false} onReset={noop} onExport={noop}/>);
  assert.match(html,/id="proof-days">7/);assert.match(html,/Chưa có dữ liệu/);assert.doesNotMatch(html,/NaN|Số liệu minh họa/);
  const legacy=renderToStaticMarkup(<ProofReport report={{...report,days:6}} preview={false} onReset={noop} onExport={noop}/>);assert.match(legacy,/Báo cáo tương thích 6 ngày/);
});
test('precomputed proof identifies its offline source and preserves run identifiers',()=>{
  const report={days:7,seed:42,run_on:'original-on',run_off:'original-off',metrics:[],source:'precomputed_offline_simulation'};
  const html=renderToStaticMarkup(<ProofReport report={report} manifest={{comparison_id:'pair-1',provider_eval:'not_run',artifact_sha256:'abc',brief:{goal_vi:'Yêu cầu gốc của lần chạy cũ',allow_ads:true,ads_daily_cap:null}}} onReset={noop} onExport={noop}/>);
  assert.match(html,/Mô phỏng ngoại tuyến đã chạy/);assert.match(html,/Chưa đánh giá provider/);
  assert.match(html,/original-on \/ original-off/);assert.match(html,/pair-1/);assert.match(html,/not_run/);
  assert.match(html,/Bắt đầu phiên demo mới/);assert.doesNotMatch(html,/Chạy lại từ đầu/);
  assert.match(html,/Yêu cầu gốc của báo cáo: Yêu cầu gốc của lần chạy cũ/);assert.match(html,/Chưa đặt mức trần trong yêu cầu/);
});

test('agent overview shows package changes, safe referee text and distinct validation',()=>{
  const make=(seq,type,data,text_vi,actor)=>({seq,type,data,text_vi,actor,run_id:state.run_id,day:1,shop_id:'Z',ts:'12:00'});
  const initial={content_refresh:true,ads_daily_budget:70000,voucher_pct:10,stop_roas_below:4,stop_after_days:2,duration_days:3};
  const events=[make(1,'platform_turn',{negotiation_id:'n-1',round:1,action:'propose',package:initial},'Gói đầu','platform_agent'),make(2,'shop_turn',{negotiation_id:'n-1',round:1,action:'counter',package:{...initial,ads_daily_budget:45000,voucher_pct:3},private_note_vi:'Giá vốn riêng không hiện ở sơ đồ'},'Đề nghị điều chỉnh','shop_agent'),make(3,'referee_review',{negotiation_id:'n-1',round:1,action:'refocus',focused_question:'Giữ nguyên ngân sách?'},'Lý do <script>không an toàn</script>','referee')];
  const html=renderToStaticMarkup(<AgentActivity state={{...state,step:'negotiating'}} events={events} preview={false}/>);
  assert.match(html,/Vòng 1 \/ tối đa 3/);assert.match(html,/70\.000đ/);assert.match(html,/45\.000đ/);assert.match(html,/is-changed/);
  assert.match(html,/Cần tập trung lại/);assert.match(html,/Chưa có kết quả kiểm tra/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|Giá vốn riêng không hiện/);
});
test('missing telemetry does not invent processing; connection loss hides running indicators',()=>{
  const negotiating={...state,step:'negotiating'};
  const task={seq:1,run_id:state.run_id,day:1,shop_id:'Z',actor:'platform_agent',type:'agent_activity',text_vi:'Đang xem gói',data:{negotiation_id:'n',task_id:'t',phase:'proposal',round:1,status:'running',label_vi:'Agent sàn đang xem gói'}};
  assert.doesNotMatch(renderToStaticMarkup(<AgentActivity state={negotiating} events={[]}/>),/data-working="true"/);
  assert.match(renderToStaticMarkup(<AgentActivity state={negotiating} events={[task]}/>),/data-working="true"/);
  const disconnected=renderToStaticMarkup(<AgentActivity state={negotiating} events={[task]} error="Mất mạng"/>);
  assert.match(disconnected,/Kết nối gián đoạn/);assert.doesNotMatch(disconnected,/data-working="true"/);
});
test('completed journey has six completed markers and rejected content is skipped',()=>{
  const html=renderToStaticMarkup(<Progress state={{...state,step:'complete'}}/>);
  assert.equal((html.match(/class="done"/g) || []).length,6);assert.doesNotMatch(html,/aria-current/);
  const rejection={seq:1,run_id:state.run_id,day:1,shop_id:'Z',type:'seller_decision',data:{action:'reject'}};
  const rejected=renderToStaticMarkup(<Progress state={{...state,step:'day_done'}} events={[rejection]}/>);
  assert.equal((rejected.match(/class="skipped"/g) || []).length,2);
});

test('proof opens two aligned conversations on day two with prior-day evidence',()=>{
  const report={days:7,seed:42,run_on:'preview-on',run_off:'preview-off',metrics:[],comparison_days:previewComparisonDays()};
  const html=renderToStaticMarkup(<ProofReport report={report} preview onReset={noop} onExport={noop}/>);
  assert.equal((html.match(/class="learning-chat /g) || []).length,2);
  assert.match(html,/data-comparison-day="2"/);assert.match(html,/data-proof-day="2" aria-pressed="true"/);
  assert.match(html,/Không học từ lịch sử/);assert.match(html,/Có học từ lịch sử/);assert.match(html,/Góp ý ảnh nền sáng/);
  assert.match(html,/Hội thoại minh họa/);assert.match(html,/Số liệu minh họa giao diện/);
  assert.equal((html.match(/Làm ảnh bìa mới cho mẫu quạt này giúp chị nhé\./g) || []).length,2);
});
test('missing real transcripts stay empty; report messages are escaped',()=>{
  const legacy={days:7,seed:42,run_on:'real-on',run_off:'real-off',metrics:[]};
  const empty=renderToStaticMarkup(<ProofReport report={legacy} onReset={noop} onExport={noop}/>);
  assert.match(empty,/Chưa có hội thoại đối chứng/);assert.doesNotMatch(empty,/Em nhớ chị thích nền sáng/);
  const days=previewComparisonDays();days[1].on.messages[0].text_vi='<img src=x onerror=alert(1)>';
  const html=renderToStaticMarkup(<ProofReport report={{...legacy,run_on:'preview-on',run_off:'preview-off',comparison_days:days}} onReset={noop} onExport={noop}/>);
  assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img src=x/);
});
test('agent diagram is compact with package details closed by default',()=>{
  const html=renderToStaticMarkup(<AgentActivity state={{...state,step:'negotiating'}} events={[]}/>);
  assert.match(html,/compact-activity/);assert.match(html,/<details class="activity-details">/);assert.doesNotMatch(html,/class="agent-node |class="interaction-steps"/);
});

test('seller feedback waits for a renegotiation outcome before offering to end the day',()=>{
  const sent={seq:2,run_id:state.run_id,day:1,shop_id:'Z',actor:'seller',type:'seller_decision',ts:'12:00',text_vi:'Người bán đã góp ý',data:{card_id:'c-1',action:'negotiate',note_vi:'giảm thêm dc khong'}};
  const html=renderToStaticMarkup(<DemoPage run={{state:{...state,step:'day_done',pending_card:null},events:[sent],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.doesNotMatch(html,/Đã ghi nhận lựa chọn của chị/);
  assert.doesNotMatch(html,/data-night/);
  assert.match(html,/đang trao đổi|đang thương lượng/i);
  assert.match(html,/giảm thêm dc khong/);
});

test('seller sees the exact current negotiation outcome, not an earlier refusal or a made-up choice',()=>{
  const mk=(seq,type,data,text_vi='')=>({seq,run_id:state.run_id,day:1,shop_id:'Z',actor:'seller',type,ts:'12:00',text_vi,data});
  const feedback=mk(4,'seller_decision',{card_id:'c-2',action:'negotiate',note_vi:'giảm thêm dc khong'});
  const old=mk(3,'negotiation_finished',{source_card_id:'c-1',negotiation_id:'n-1',status:'failed',reason_vi:'Lý do của phiên cũ'});
  const value={...state,step:'day_done',pending_card:null,renegotiation:{source_card_id:'c-2',negotiation_id:'n-2',status:'failed',restoration_status:'blocked',restoration_reason_vi:'Gói trước không còn hợp lệ.',referee_action:'ask_human',reason_vi:'Chưa rõ khả năng giảm thêm, cần người bán xem lại.'}};
  const html=renderToStaticMarkup(<DemoPage run={{state:value,events:[old,feedback],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.match(html,/Không thể tiếp tục với gói trước/);assert.match(html,/Gói trước không còn hợp lệ/);assert.match(html,/Chưa rõ khả năng giảm thêm/);assert.match(html,/data-night/);
  assert.ok(!html.includes('Đã ghi nhận lựa chọn của chị'));assert.ok(!html.includes('Lý do của phiên cũ'));assert.ok(!html.includes('đã từ chối'));
  const stale={...value,renegotiation:{source_card_id:'c-1',status:'failed',reason_vi:'Lý do của phiên cũ'}};
  const pending=renderToStaticMarkup(<DemoPage run={{state:stale,events:[old,feedback],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.ok(!pending.includes('Lý do của phiên cũ'));assert.ok(!pending.includes('data-night'));assert.match(pending,/đang trao đổi|đang thương lượng/i);
});

test('the check panel shows only supplied safe sources, versions and excerpts with accessible same-origin links',()=>{
  const pkg={content_refresh:true,ads_daily_budget:70000,voucher_pct:10,stop_roas_below:4,stop_after_days:2,duration_days:3};
  const make=(seq,type,data)=>({seq,type,data,actor:type==='code_check'?'code':'platform_agent',run_id:state.run_id,day:1,shop_id:'Z',ts:'12:00'});
  const checks=[{ok:false,message_vi:'Vượt mức',sources:[{kind:'rule',title_vi:'Luật shop <b>',version:4,excerpt_vi:'Ngân sách tối đa <45.000đ>',download_url:'/api/v1/runs/database-run/knowledge/documents/rule-1'}]},{ok:false,message_vi:'Nguồn xấu',sources:[{title_vi:'Nguồn không an toàn',version:'v1',download_url:'javascript:alert(1)'},{title_vi:'Ngoài trang',download_url:'https://evil.example/file'}]},{ok:true,message_vi:'Không có nguồn'}];
  const html=renderToStaticMarkup(<AgentActivity state={{...state,step:'negotiating'}} events={[make(1,'platform_turn',{negotiation_id:'n',action:'propose',package:pkg}),make(2,'code_check',{negotiation_id:'n',ok:false,checks})]}/>);
  assert.match(html,/<summary[^>]*>Nguồn kiểm tra/);assert.match(html,/Luật shop &lt;b&gt;/);assert.match(html,/Phiên bản 4/);assert.match(html,/Ngân sách tối đa &lt;45\.000đ&gt;/);
  assert.match(html,/href="\/api\/v1\/runs\/database-run\/knowledge\/documents\/rule-1"/);assert.ok(!html.includes('href="javascript:'));assert.ok(!html.includes('href="https://evil.example'));
});

test('completed images appear while the other media slots are still running',()=>{
  const draft={version:1,status:'running',title:'Tiêu đề',description:'Mô tả',images:[{option:'A',status:'done',path:'/api/v1/runs/r/assets/a/download',source:'live'},{option:'B',status:'running',path:null},{option:'C',status:'reserved',path:null}],video:{status:'running',path:null},feedback_history:[]};
  const html=renderToStaticMarkup(<ContentReview draft={draft} original={shop} onRetry={noop} onApply={noop} onNotice={noop}/>);
  assert.match(html,/alt="Phương án ảnh bìa A"/);assert.equal((html.match(/Đang tạo ảnh/g)||[]).length,2);assert.match(button(html,'retry'),/disabled/);
});

test('the seller sees a verified new card or unchanged terms without treating either as approval',()=>{
  const source={seq:4,run_id:state.run_id,day:1,shop_id:'Z',actor:'seller',type:'seller_decision',ts:'12:00',text_vi:'Góp ý',data:{card_id:'c-1',action:'negotiate'}};
  const pkg={content_refresh:false,ads_daily_budget:0,voucher_pct:2,stop_roas_below:null,stop_after_days:null,duration_days:3};
  const card={card_id:'c-2',negotiation_id:'n-2',kind:'offer',package:pkg,forecast:{low:10,high:12},reasons_vi:[],warnings_vi:[]};
  const render=changed=>renderToStaticMarkup(<DemoPage run={{state:{...state,step:'awaiting_decision',pending_card:card,renegotiation:{source_card_id:'c-1',negotiation_id:'n-2',status:'agreed',changed}},events:[source],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  const changed=render(true);assert.match(changed,/gói điều chỉnh để chị xem lại/);assert.match(changed,/data-decision="accept"/);assert.ok(!changed.includes('data-night'));
  const unchanged=render(false);assert.match(unchanged,/giữ nguyên điều khoản của gói trước/);assert.ok(!unchanged.includes('gói điều chỉnh để chị xem lại'));assert.match(unchanged,/data-decision="accept"/);
});

test('unknown renegotiation outcomes do not offer to end the day',()=>{
  const value={...state,step:'day_done',renegotiation:{source_card_id:'c-1',status:'unknown',reason_vi:'Kết quả tác vụ chưa rõ.'}};
  const html=renderToStaticMarkup(<DemoPage run={{state:value,events:[],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.match(html,/Chưa xác định được kết quả thương lượng/);assert.match(html,/Kết quả tác vụ chưa rõ/);assert.ok(!html.includes('data-night'));
});

test('historical code-check events show the supplied source names, versions and document links in the event feed',()=>{
  const rules={kind:'shop_rules',title_vi:'Quy tắc shop',version:2,excerpt_vi:'Voucher tối đa 3%.'};
  const cost={kind:'product_cost',title_vi:'Giá vốn sản phẩm',version:1};
  const fees={kind:'fee_policy',title_vi:'Chính sách phí áp dụng',version:'demo-fees-v1'};
  const guide={kind:'reference_document',title_vi:'Tài liệu tham khảo phí giả lập',version:1,document_id:'fee_calculation_guide_demo',download_url:'/api/v1/runs/database-run/knowledge/documents/fee_calculation_guide_demo?version=1'};
  const calculation={kind:'calculation',title_vi:'Điều kiện dừng theo hòa vốn trong code',excerpt_vi:'Ngưỡng dừng không thấp hơn ROAS hòa vốn.'};
  const checks=[
    {ok:false,message_vi:'Voucher vượt mức.',sources:[rules]},
    {ok:false,message_vi:'Quảng cáo không phù hợp.',sources:[rules]},
    {ok:true,message_vi:'Ngân sách trong giới hạn.',sources:[rules]},
    {ok:true,message_vi:'Tồn kho đủ.',sources:[{kind:'inventory',title_vi:'Tồn kho',version:1},{kind:'calculation',title_vi:'Điều kiện tồn kho trong code'}]},
    {ok:true,message_vi:'Đạt lãi tối thiểu.',sources:[rules,cost,fees,guide]},
    {ok:true,message_vi:'Gói không lỗ.',sources:[cost,fees,guide]},
    {ok:true,message_vi:'ROAS trong giới hạn.',sources:[rules,cost,fees,guide]},
    {ok:true,message_vi:'Ngưỡng dừng hợp lệ.',sources:[cost,fees,guide,calculation]}
  ];
  const event={seq:24,run_id:state.run_id,day:1,shop_id:'Z',type:'code_check',actor:'code',ts:'10:00',text_vi:'Code kiểm tra luật shop',data:{checks}};
  const html=renderToStaticMarkup(<EventFeed state={state} events={[event]} preview={false}/>);
  assert.ok(html.includes('Quy tắc shop'),'event feed must show the source title');
  assert.ok(html.includes('Tài liệu tham khảo phí giả lập'),'event feed must show the document title');
  assert.ok(html.includes('Phiên bản 2'),'event feed must show the source version');
  assert.ok(html.includes('/api/v1/runs/database-run/knowledge/documents/fee_calculation_guide_demo?version=1'),'event feed must link to the supplied document');
  assert.ok(html.includes('Ngưỡng dừng không thấp hơn ROAS hòa vốn.'));
});

test('event citations escape source text, reject unsafe links and do not fabricate missing sources',()=>{
  const event={seq:24,run_id:state.run_id,day:1,shop_id:'Z',type:'code_check',actor:'code',ts:'10:00',text_vi:'Kiểm tra',data:{checks:[
    {ok:false,message_vi:'Không đạt',sources:[{title_vi:'<script>alert(1)</script>',version:'v<2',excerpt_vi:'<img src=x onerror=alert(1)>',download_url:'javascript:alert(1)'},{title_vi:'Ngoài trang',download_url:'https://evil.example/file'},{title_vi:'Không phải API',download_url:'/unsafe'}]},
    {ok:true,message_vi:'Không có nguồn'}
  ]}};
  const html=renderToStaticMarkup(<EventFeed state={state} events={[event]} preview={false}/>);
  assert.match(html,/&lt;script&gt;alert\(1\)&lt;\/script&gt;/);assert.match(html,/&lt;img src=x/);assert.match(html,/Phiên bản v&lt;2/);
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img src=x'));assert.ok(!html.includes('href="javascript:'));assert.ok(!html.includes('href="https://evil.example'));assert.ok(!html.includes('href="/unsafe"'));
  assert.equal((html.match(/Nguồn:/g)||[]).length,1);
  const legacy=renderToStaticMarkup(<EventFeed state={state} events={[{...event,data:{checks:[{ok:true,message_vi:'Không có nguồn'}]}}]} preview={false}/>);
  assert.ok(!legacy.includes('Nguồn:'));
});

test('an initial terminal stop shows its reason without inventing a seller choice',()=>{
  const mk=(seq,type,data,text_vi)=>({seq,type,data,text_vi,actor:'referee',run_id:state.run_id,day:1,shop_id:'Z',ts:'12:00'});
  const events=[mk(1,'platform_turn',{negotiation_id:'n-1',round:1,action:'accept'},'Agent sàn đã chấp nhận'),mk(2,'referee_review',{negotiation_id:'n-1',round:1,action:'stop'},'Cần xem lại điều kiện.'),mk(3,'negotiation_finished',{negotiation_id:'n-1',status:'failed',reason_vi:'Cần xem lại điều kiện.',referee_action:'stop'},'Thương lượng kết thúc')];
  const value={...state,step:'day_done',pending_card:null,negotiation:{negotiation_id:'n-1',status:'failed',reason_vi:'Cần xem lại điều kiện.',referee_action:'stop'}};
  const html=renderToStaticMarkup(<DemoPage run={{state:value,events,act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.ok(!html.includes('Đã ghi nhận lựa chọn của chị'),'must not invent a seller choice');
  assert.ok(html.includes('Cần xem lại điều kiện.'));assert.ok(html.includes('Chưa có gói'));assert.ok(html.includes('data-night'));
  assert.equal((html.match(/class="skipped"/g)||[]).length,3);
});

test('initial outcome waits for a card or a known result and preserves genuine seller decisions',()=>{
  const render=(value,events=[])=>renderToStaticMarkup(<DemoPage run={{state:value,events,act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  const base={...state,step:'day_done',pending_card:null};
  const unknown=render({...base,negotiation:{negotiation_id:'n-1',status:'unknown',reason_vi:'Kết quả chưa rõ.',referee_action:null}});
  assert.match(unknown,/Chưa xác định được kết quả thương lượng/);assert.match(unknown,/Kết quả chưa rõ/);assert.ok(!unknown.includes('data-night'));assert.ok(!unknown.includes('Đã ghi nhận lựa chọn'));
  const agreed=render({...base,negotiation:{negotiation_id:'n-1',status:'agreed'}});
  assert.match(agreed,/Đang chờ thẻ đề xuất/);assert.ok(!agreed.includes('data-night'));assert.ok(!agreed.includes('Đã ghi nhận lựa chọn'));
  const accepted={seq:3,run_id:state.run_id,day:1,shop_id:'Z',type:'seller_decision',actor:'seller',ts:'12:00',text_vi:'Đã duyệt',data:{target_type:'proposal',card_id:'c-1',action:'accept'}};
  const decided=render({...base,negotiation:{negotiation_id:'n-1',status:'agreed'}},[accepted]);
  assert.match(decided,/Đã ghi nhận lựa chọn của chị/);assert.ok(decided.includes('data-night'));
});

test('initial failure can use its own terminal event when state metadata is absent',()=>{
  const mk=(seq,type,data,text_vi,extra={})=>({seq,type,data,text_vi,actor:'referee',run_id:state.run_id,day:1,shop_id:'Z',ts:'12:00',...extra});
  const own=[mk(1,'referee_review',{negotiation_id:'n-1',action:'stop'},'Lý do của phiên này.'),mk(2,'negotiation_finished',{negotiation_id:'n-1',status:'failed'},'Kết thúc')];
  const other=mk(5,'referee_review',{negotiation_id:'n-1',action:'stop'},'Lý do của shop khác.',{shop_id:'A'});
  const html=renderToStaticMarkup(<DemoPage run={{state:{...state,step:'day_done'},events:[...own,other],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.match(html,/Lý do của phiên này/);assert.match(html,/Chưa có gói để chị duyệt/);assert.ok(!html.includes('Lý do của shop khác'));assert.ok(!html.includes('Đã ghi nhận lựa chọn'));
});

test('day done without any seller decision uses neutral language',()=>{
  const html=renderToStaticMarkup(<DemoPage run={{state:{...state,step:'day_done'},events:[],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.match(html,/Ngày đã sẵn sàng tổng kết/);assert.ok(!html.includes('Đã ghi nhận lựa chọn của chị'));
});

test('a server-restored offer remains reviewable after an unsuccessful renegotiation',()=>{
  const feedback={seq:5,run_id:state.run_id,day:1,shop_id:'Z',actor:'seller',type:'seller_decision',ts:'12:00',text_vi:'Góp ý',data:{card_id:'c-1',action:'negotiate',note_vi:'giảm thêm'}};
  const card={card_id:'c-restored',version:2,brief_version:1,negotiation_id:'n-original',kind:'offer',package:{content_refresh:true,ads_daily_budget:45000,voucher_pct:3,stop_roas_below:6.5,stop_after_days:2,duration_days:3},forecast:{low:18,high:30},reasons_vi:[],warnings_vi:[]};
  const value={...state,step:'awaiting_decision',pending_card:card,renegotiation:{source_card_id:'c-1',negotiation_id:'n-new',status:'failed',restoration_status:'restored',restored_card_id:'c-restored',reason_vi:'Chưa thể giảm thêm.'}};
  const html=renderToStaticMarkup(<DemoPage run={{state:value,events:[feedback],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.ok(html.includes('data-decision="accept"'),'the restored original offer must remain actionable');
  assert.ok(html.includes('data-decision="reject"'));assert.ok(html.includes('Chưa thể giảm thêm.'));assert.ok(html.includes('45.000đ/ngày'));
  assert.ok(!html.includes('data-night'));assert.ok(!html.includes('Chưa có gói điều chỉnh.'));
});

test('a restored offer cannot negotiate past the server-declared retry limit',()=>{
  const card={kind:'offer',can_negotiate:false,package:{content_refresh:false,ads_daily_budget:0,voucher_pct:3,stop_roas_below:null,stop_after_days:null,duration_days:3},forecast:null,reasons_vi:[],warnings_vi:[]};
  const html=renderToStaticMarkup(<Proposal card={card} pending={false} onDecision={noop} onNegotiate={noop}/>);
  assert.match(html,/data-decision="accept"/);assert.match(html,/data-decision="reject"/);
  assert.ok(!html.includes('data-negotiate="true"') || /data-negotiate="true" disabled/.test(html),'retry must be disabled or hidden');
  assert.match(html,/Đã hết lượt thương lượng/);
});

test('seller rejection after a restored offer resolves the current choice',()=>{
  const feedback={seq:5,run_id:state.run_id,day:1,shop_id:'Z',actor:'seller',type:'seller_decision',ts:'12:00',text_vi:'Góp ý',data:{card_id:'c-1',action:'negotiate'}};
  const sent={seq:7,run_id:state.run_id,day:1,shop_id:'Z',actor:'system',type:'card_sent',ts:'12:00',text_vi:'Thẻ trước',data:{card_id:'c-restored',negotiation_id:'n-original'}};
  const rejected={seq:8,run_id:state.run_id,day:1,shop_id:'Z',actor:'seller',type:'seller_decision',ts:'12:00',text_vi:'Từ chối',data:{card_id:'c-restored',action:'reject',target_type:'proposal'}};
  const value={...state,step:'day_done',pending_card:null,renegotiation:{source_card_id:'c-1',negotiation_id:'n-new',status:'failed',restoration_status:'restored',restored_card_id:'c-restored',reason_vi:'Chưa giảm được.'}};
  const html=renderToStaticMarkup(<DemoPage run={{state:value,events:[feedback,sent,rejected],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.match(html,/Đã ghi nhận lựa chọn của chị/);assert.ok(html.includes('data-night'));assert.ok(!html.includes('Chưa có gói điều chỉnh.'));
});

test('a failed attempt never revives an unmatched or not-yet-restored card',()=>{
  const feedback={seq:5,run_id:state.run_id,day:1,shop_id:'Z',type:'seller_decision',actor:'seller',ts:'12:00',text_vi:'Góp ý',data:{card_id:'c-1',action:'negotiate'}};
  const old={card_id:'c-1',version:1,kind:'offer',package:{content_refresh:false,ads_daily_budget:0,voucher_pct:3,stop_roas_below:null,stop_after_days:null,duration_days:3}};
  const render=(value,events=[feedback])=>renderToStaticMarkup(<DemoPage run={{state:value,events,act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  const pending={...state,step:'day_done',pending_card:null,renegotiation:{source_card_id:'c-1',negotiation_id:'n-2',status:'failed',restoration_status:null}};
  const first=render(pending);assert.match(first,/Chưa thể kiểm tra lại gói trước/);assert.ok(!first.includes('data-night'));
  const stale={...pending,step:'awaiting_decision',pending_card:old,renegotiation:{...pending.renegotiation,restoration_status:'restored',restored_card_id:'c-2'}};
  const second=render(stale);assert.ok(!second.includes('data-decision="accept"'));assert.ok(!second.includes('data-night'));
  const unrelated={...stale,pending_card:{...old,card_id:'c-3'}};
  const cardEvent={seq:7,run_id:state.run_id,day:1,shop_id:'Z',type:'card_sent',actor:'system',ts:'12:00',text_vi:'Khác',data:{card_id:'c-3',card:unrelated.pending_card}};
  const third=render(unrelated,[feedback,cardEvent]);assert.ok(!third.includes('data-decision="accept"'));assert.ok(!third.includes('data-night'));
});

test('legacy failed feedback offers explicit recovery of the original offer',()=>{
  const feedback={seq:5,run_id:state.run_id,day:1,shop_id:'Z',type:'seller_decision',actor:'seller',ts:'12:00',text_vi:'Góp ý',data:{card_id:'c-1',action:'negotiate'}};
  const value={...state,step:'day_done',brief:{version:2},pending_card:null,renegotiation:{source_card_id:'c-1',source_card_version:4,negotiation_id:'n-2',status:'failed',reason_vi:'Chưa có điều chỉnh phù hợp.',operation_id:'op-1',operation_version:3,restoration_allowed:true}};
  const html=renderToStaticMarkup(<DemoPage run={{state:value,events:[feedback],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
  assert.ok(html.includes('Xem lại gói trước'),'legacy outcome must offer recovery');assert.ok(html.includes('Chưa có điều chỉnh phù hợp.'));
  assert.ok(!html.includes('data-night'));assert.ok(!html.includes('Đang kiểm tra lại gói trước'));
});

test('an unknown or in-flight attempt never revives an unrelated card even if its event arrives',()=>{
  const feedback={seq:5,run_id:state.run_id,day:1,shop_id:'Z',type:'seller_decision',actor:'seller',ts:'12:00',text_vi:'Góp ý',data:{card_id:'c-1',negotiation_id:'n-old',action:'negotiate'}};
  const card={card_id:'c-2',negotiation_id:'n-other',kind:'offer',package:{content_refresh:false,ads_daily_budget:0,voucher_pct:3,stop_roas_below:null,stop_after_days:null,duration_days:3}};
  const sent={seq:7,run_id:state.run_id,day:1,shop_id:'Z',type:'card_sent',actor:'system',ts:'12:00',text_vi:'Khác',data:{card_id:'c-2',negotiation_id:'n-other',card}};
  for(const status of ['unknown','running','agreed']){
    const value={...state,step:'awaiting_decision',pending_card:card,renegotiation:{source_card_id:'c-1',negotiation_id:'n-current',status}};
    const html=renderToStaticMarkup(<DemoPage run={{state:value,events:[feedback,sent],act:noop}} preview={false} navigate={noop} onEndDay={noop} onNotice={noop}/>);
    assert.ok(!html.includes('data-decision="accept"'),status+' must not revive an unrelated card');assert.ok(!html.includes('data-night'));
  }
});
