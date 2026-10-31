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
