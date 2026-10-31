import {SIMULATION_DAYS,CONTENT_ATTEMPTS,MAX_NEGOTIATION_ATTEMPTS} from './config.js';
import {previewComparisonDays} from './previewComparison.js';
import {loadDay7Sample} from './day7Sample.js';
/* Browser-only fixtures. These illustrate the interface, never a real agent run. */
export function createPreviewAPI({storage=globalThis.sessionStorage,now=Date.now,assetRoot=new URL('../img/',import.meta.url),fetchImpl=globalThis.fetch,makeRunId=()=> 'preview-' + (globalThis.crypto?.randomUUID?.() || now())}={}) {
  const KEY = 'growth-agents.react-preview.v3';
  const root = assetRoot;
  const image = name => new URL(name + '.svg', root).href;
  const clone = value => JSON.parse(JSON.stringify(value));
  const original = {
    shop_id:'D', name:'Nhà Bé Lan', category:'quat_mini', price:175000, stock:300,
    listing_quality:0.55, search_rank_page:3, rating:4.6, base_impressions:2500,
    title:'Quạt mini cầm tay sạc usb loại tốt giá rẻ',
    description:'Quạt mini cầm tay. Sạc usb. 3 tốc độ gió. Pin 2000mAh. Có 3 màu.',
    attributes:['3 tốc độ gió','sạc USB','pin 2000mAh','3 màu: Trắng, Hồng, Xanh mint'],
    images:['fan-original','fan-white','fan-pink','fan-mint'].map(image), video:null, active_voucher_pct:0
  };
  const packageFor = (voucher=3) => ({content_refresh:true,ads_daily_budget:45000,voucher_pct:voucher,stop_roas_below:6.5,stop_after_days:2,duration_days:3});
  function fresh(memory=true) {
    return { state:{run_id:makeRunId(),day:1,mode:'offline',memory_enabled:memory,step:'idle',demo_shop:clone(original),demo_shop_original:clone(original),active_package:null,pending_card:null,content_draft:null,last_night:null,live_calls_left:0},events:[],queue:[],started:null,ready:null,negotiations:0,styleConfirmed:false,styleCandidate:false,styleDeclinedUntil:0 };
  }
  function read() { try { const raw=storage.getItem(KEY); return raw ? JSON.parse(raw) : fresh(); } catch { return fresh(); } }
  function write(db) { storage.setItem(KEY, JSON.stringify(db)); }
  const time = () => new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',hour12:false});
  function event(db,type,actor,text,data={},shop='D') {
    const ev={seq:db.events.length+1,run_id:db.state.run_id,day:db.state.day,ts:time(),type,actor,shop_id:shop,text_vi:text,data:clone(data)};
    db.events.push(ev); return ev;
  }
  function card(db,voucher=3) {
    const question = db.state.memory_enabled && db.styleCandidate && db.state.day>1 && !db.styleConfirmed && db.state.day>(db.styleDeclinedUntil || 0);
    const onlyQuestion = question && db.state.active_package && db.state.active_package.end_day >= db.state.day;
    return {card_id:`D-${db.state.day}-${db.negotiations}`,shop_id:'D',day:db.state.day,kind:onlyQuestion?'question':'offer',
      package:onlyQuestion?null:packageFor(voucher),forecast:onlyQuestion?null:{low:18,point:24,high:30,factor_used:1,stock_warning:false},
      profit_after_fees_per_unit:onlyQuestion?null:(voucher===3?27136:28632),breakeven_roas_display:onlyQuestion?null:6.5,
      reasons_vi:['Sản phẩm thuộc nhóm từ khóa đang được quan tâm.','Làm mới nội dung để giới thiệu rõ 3 tốc độ gió và pin 2000mAh.','Gói được kiểm tra theo giới hạn chủ shop.'],warnings_vi:[],notices_vi:[],
      rule_question:question?{pref_id:'D-bright',field:'content_style',value:'ảnh nền sáng',text_vi:'Lần sau chị muốn tạo ảnh nền sáng ngay từ đầu?'}:null};
  }
  function draft(db,version=1,feedback=[]) {
    return {shop_id:'D',version,title:'Quạt mini cầm tay · 3 tốc độ gió, pin 2000mAh, sạc USB',
      description:'Nhỏ gọn trong lòng bàn tay, dễ mang theo mỗi ngày.\n• 3 tốc độ gió để lựa chọn.\n• Pin 2000mAh, sạc USB.\n• 3 màu: Trắng, Hồng, Xanh mint.',
      images:['A','B','C'].map(option=>({option,status:'running',path:null,prompt:'Ảnh minh họa quạt mini, nền sáng; giữ nguyên đặc điểm sản phẩm.'})),
      video:{status:'running',path:null,job_id:'preview-video',prompt:'Giới thiệu quạt mini cầm tay.',error:null},feedback_history:feedback,style_notes:feedback.length?['ảnh nền sáng']:[],checks:['Chỉ sử dụng thuộc tính có trong sản phẩm.','Giữ nguyên màu sắc và hình dáng sản phẩm.']};
  }
  function advance(db) {
    if(db.started!=null && db.state.step==='negotiating') {
      const elapsed=now()-db.started;
      while(db.queue.length && db.queue[0].at<=elapsed) {
        const item=db.queue.shift();
        if(item.finish){db.state.step='day_done';}
        else if(item.card){ db.state.pending_card=card(db,item.voucher || 3); db.state.step='awaiting_decision'; event(db,'card_sent','system','Đã gửi thẻ đề xuất để chị Lan quyết định.',{card:db.state.pending_card}); }
        else {
          const data={...(item.data || {})};
          if(item.type==='referee_review')data.evidence_refs=db.events.filter(ev=>['platform_turn','shop_turn'].includes(ev.type) && ev.data.negotiation_id===data.negotiation_id).slice(-2).map(ev=>ev.seq);
          event(db,item.type,item.actor,item.text,data);
        }
      }
    }
    if(db.ready!=null && db.state.content_draft) {
      const elapsed=now()-db.ready;
      if(elapsed>=1700 && db.state.content_draft.images.some(i=>i.status==='running')) {
        db.state.content_draft.images.forEach(i=>{i.status='done';i.path=image('cover-'+i.option.toLowerCase());});
        event(db,'content_job','content_agent','Ba phương án ảnh bìa đã sẵn sàng.',{kind:'image',status:'done',version:db.state.content_draft.version,detail_vi:'Ảnh minh họa cho bản xem trước giao diện.'});
      }
      if(elapsed>=3300 && db.state.content_draft.video.status==='running') {
        db.state.content_draft.video={status:'failed',path:null,job_id:null,prompt:'',error:'Bản xem trước không gọi dịch vụ tạo video.'};
        event(db,'content_job','content_agent','Bản xem trước dùng ảnh minh họa; video thật do backend cung cấp.',{kind:'video',status:'failed',version:db.state.content_draft.version,detail_vi:'Có thể áp dụng nội dung và ảnh.'});
      }
    }
  }
  const proof = {
    seed:42,days:SIMULATION_DAYS,run_on:'preview-on',run_off:'preview-off',
    comparison_days:previewComparisonDays(),
    metrics:[
      {key:'acceptance',label_vi:'Tỷ lệ chấp nhận đề xuất',better:'higher',on:83,off:61,unit:'%'},
      {key:'profit',label_vi:'Tổng lãi sau phí',better:'higher',on:3520000,off:2780000,unit:'đ'},
      {key:'mape',label_vi:'Sai số dự báo',better:'lower',on:14,off:38,unit:'%'},
      {key:'revisions',label_vi:'Số lần sửa nội dung',better:'lower',on:2,off:6,unit:''}
    ],note_vi:'Số liệu minh họa để kiểm tra bố cục giao diện. Chưa phải kết quả chạy mô phỏng 7 ngày. Khi nối backend, toàn bộ số liệu lấy từ GET /api/proof.'
  };
  async function request(path,options={}) {
    const url=new URL(path,'https://preview.invalid');
    const method=(options.method || 'GET').toUpperCase();
    let body=options.body || {}; if(typeof body==='string') body=JSON.parse(body);
    if(url.pathname==='/api/demo/jump-day7' && method==='POST'){
      const sample=await loadDay7Sample(fetchImpl,options.signal);
      const next={...fresh(),state:sample.state,events:sample.events,proof:sample.proof,source:sample.source};
      next.state.sample_source=sample.source;
      // Keep the existing preview until the complete database response is valid.
      const previous=storage.getItem(KEY);
      if(previous && !JSON.parse(previous).source)storage.setItem(KEY+'.before-day7',previous);
      write(next);
      return clone({state:next.state,source:next.source});
    }
    const db=read(); advance(db); const s=db.state; let result;
    const fail=message=>{throw new Error(message);};
    if(url.pathname==='/api/reset' && method==='POST') { const next=fresh(body.memory??true); write(next); return clone({run_id:next.state.run_id,day:1,mode:next.state.mode,state:next.state}); }
    if(url.pathname==='/api/state' && method==='GET') result=s;
    else if(url.pathname==='/api/events' && method==='GET') result={events:db.events.filter(e=>e.seq>Number(url.searchParams.get('after') || 0)),last_seq:db.events.length};
    else if(url.pathname==='/api/day/start' && method==='POST') {
      if(s.step==='complete' || s.day>SIMULATION_DAYS) fail('Phiên mô phỏng đã hoàn tất. Hãy đặt lại để chạy phiên mới.');
      if(s.step!=='idle' && s.step!=='night_done') fail('Ngày hiện tại đã bắt đầu.');
      s.step='negotiating';s.pending_card=null;s.content_draft=null;db.ready=null;db.started=now();db.negotiations=1;
      if(s.active_package && s.active_package.end_day<s.day) s.active_package=null;
      event(db,'day_start','system',`Bắt đầu ngày mô phỏng ${s.day}.`,{day:s.day});
      const negotiation_id=`D-${s.day}-attempt1`;
      db.queue=[
        {at:400,type:'opportunity',actor:'platform_agent',text:'Từ khóa quạt mini cầm tay tăng 240% trong 7 ngày. Nhà Bé Lan có cơ hội cải thiện nội dung.',data:{keyword:'quạt mini cầm tay',growth_7d_pct:240,chosen:['A','B','D','E'],excluded:[{shop_id:'C',reason_vi:'Tồn kho dưới ngưỡng.'}]}},
        {at:650,type:'memory_read',actor:'memory',text:s.memory_enabled?'Đọc lịch sử công khai và sở thích đã được xác nhận.':'Bộ nhớ tắt trong phiên này.',data:{who:'shop',items:s.memory_enabled && s.day>1?['Góp ý trước: ảnh nền sáng.']:[]}},
        {at:800,type:'agent_activity',actor:'platform_agent',text:'Agent sàn đang chuẩn bị đề xuất.',data:{negotiation_id,task_id:negotiation_id+'-platform-1',round:1,phase:'proposal',status:'running',label_vi:'Agent sàn đang chuẩn bị gói tăng trưởng'}},
        {at:1400,type:'platform_turn',actor:'platform_agent',text:'Đề xuất làm mới nội dung, quảng cáo 70.000đ/ngày và voucher 10% trong 3 ngày.',data:{negotiation_id,round:1,action:'propose',package:{...packageFor(10),ads_daily_budget:70000,stop_roas_below:4}}},
        {at:1500,type:'agent_activity',actor:'code',text:'Code đang kiểm tra gói đề xuất.',data:{negotiation_id,task_id:negotiation_id+'-check-1',round:1,phase:'validation',status:'running',label_vi:'Code đang kiểm tra ngân sách và điều kiện dừng'}},
        {at:2100,type:'code_check',actor:'code',text:'Gói đầu tiên chưa đáp ứng các giới hạn của chủ shop.',data:{negotiation_id,ok:false,checks:[{ok:false,message_vi:'Ngân sách quảng cáo vượt giới hạn chủ shop.'},{ok:false,message_vi:'Voucher chưa phù hợp với giới hạn của shop.'},{ok:false,message_vi:'Cần siết lại điều kiện tự dừng quảng cáo.'}]}},
        {at:2300,type:'agent_activity',actor:'shop_agent',text:'Agent shop đang xây dựng phản đề xuất.',data:{negotiation_id,task_id:negotiation_id+'-shop-1',round:1,phase:'response',status:'running',label_vi:'Agent shop đang điều chỉnh gói theo giới hạn của chủ shop'}},
        {at:3000,type:'shop_turn',actor:'shop_agent',text:'Đề nghị ngân sách 45.000đ/ngày, voucher 3% và ngưỡng dừng 6,5.',data:{negotiation_id,round:1,action:'counter',package:packageFor(),private_note_vi:'Điều chỉnh gói để đáp ứng các giới hạn riêng của chủ shop.',redacted:true}},
        {at:3400,type:'referee_review',actor:'referee',text:'Phản đề xuất tập trung vào ngân sách và điều kiện dừng. Tiếp tục trao đổi về gói đã điều chỉnh.',data:{negotiation_id,round:1,action:'continue',evidence_refs:['preview-shop-turn-1'],unresolved_terms:['Ngân sách quảng cáo','Voucher'],next_actor:'platform_agent',focused_question:null}},
        {at:3800,type:'agent_activity',actor:'platform_agent',text:'Agent sàn đang xem phản đề xuất.',data:{negotiation_id,task_id:negotiation_id+'-platform-2',round:2,phase:'proposal',status:'running',label_vi:'Agent sàn đang xem gói 45.000đ/ngày và voucher 3%'}},
        {at:4300,type:'platform_turn',actor:'platform_agent',text:'Đồng ý với gói đã điều chỉnh. Chuyển chị Lan duyệt sau kiểm tra cuối.',data:{negotiation_id,round:2,action:'accept',package:packageFor()}},
        {at:4600,type:'code_check',actor:'code',text:'Gói cuối đã qua kiểm tra các luật của chủ shop.',data:{negotiation_id,ok:true,checks:[{ok:true,message_vi:'Quảng cáo không vượt 45.000đ/ngày.'},{ok:true,message_vi:'Voucher phù hợp với giới hạn lợi nhuận.'},{ok:true,message_vi:'Có điều kiện tự dừng quảng cáo.'}]}},
        {at:5200,card:true}
      ];
      if(s.active_package){
        db.queue=[{at:400,type:'memory_read',actor:'memory',text:'Gói đã duyệt vẫn đang chạy. Đọc góp ý cần chủ shop xác nhận.',data:{who:'shop',items:db.styleCandidate?['Ưu tiên ảnh nền sáng.']:[]}},{at:1200,...(card(db).kind==='question'?{card:true}:{finish:true})}];
      }
      result={day:s.day,step:s.step};
    } else if(url.pathname==='/api/decision' && method==='POST') {
      if(s.step!=='awaiting_decision' || !s.pending_card || body.card_id!==s.pending_card.card_id) fail('Thẻ này không còn chờ quyết định.');
      if(!['accept','reject','negotiate'].includes(body.action)) fail('Quyết định không hợp lệ.');
      const selected=clone(s.pending_card);
      event(db,'seller_decision','seller',body.note_vi || ({accept:'Chị Lan đã đồng ý.',reject:'Chị Lan đã từ chối.',negotiate:'Chị Lan muốn thương lượng thêm.'}[body.action]),{card_id:body.card_id,action:body.action,note_vi:body.note_vi || '',rule_answer:body.rule_answer??null});
      if(selected.rule_question && body.rule_answer===true) db.styleConfirmed=true;
      if(selected.rule_question && body.rule_answer===false) db.styleDeclinedUntil=s.day+14;
      if(body.action==='negotiate') {
        if(selected.kind==='question') fail('Thẻ này chỉ dùng xác nhận sở thích.');
        if(db.negotiations>=MAX_NEGOTIATION_ATTEMPTS) fail('Đã đủ 2 phiên thương lượng trong ngày. Chị có thể đồng ý hoặc từ chối gói hiện tại.');
        db.negotiations++;s.step='negotiating';s.pending_card=null;db.started=now();
        const negotiation_id=`D-${s.day}-attempt${db.negotiations}`;
        db.queue=[
          {at:300,type:'agent_activity',actor:'shop_agent',text:'Agent shop đang xem góp ý mới của chị.',data:{negotiation_id,task_id:negotiation_id+'-shop-1',round:1,phase:'response',status:'running',label_vi:'Agent shop đang xem yêu cầu điều chỉnh voucher'}},
          {at:700,type:'shop_turn',actor:'shop_agent',text:'Đã nhận góp ý của chị. Đề nghị giảm voucher còn 2%.',data:{negotiation_id,round:1,action:'counter',package:packageFor(2),private_note_vi:'Chỉ thay đổi trong phạm vi người bán cho phép.',redacted:true}},
          {at:1100,type:'code_check',actor:'code',text:'Gói điều chỉnh vẫn nằm trong các giới hạn của chủ shop.',data:{negotiation_id,ok:true,checks:[{ok:true,message_vi:'Voucher 2% không làm tăng chi quảng cáo.'}]}},
          {at:1450,type:'referee_review',actor:'referee',text:'Gói điều chỉnh đáp ứng yêu cầu giảm voucher, không mở rộng phạm vi.',data:{negotiation_id,round:1,action:'continue',evidence_refs:['preview-feedback'],unresolved_terms:[],next_actor:'platform_agent',focused_question:null}},
          {at:1850,type:'platform_turn',actor:'platform_agent',text:'Đồng ý giảm voucher còn 2%. Gửi lại gói để chị Lan duyệt.',data:{negotiation_id,round:1,action:'accept',package:packageFor(2)}},
          {at:2400,card:true,voucher:2}
        ];
      } else if(body.action==='reject' || selected.kind==='question') {s.step='day_done';s.pending_card=null;}
      else {
        s.active_package={package:selected.package,start_day:s.day,end_day:s.day+selected.package.duration_days-1,ads_paused:false,card_id:selected.card_id};
        s.pending_card=null;s.step=selected.package.content_refresh?'content_review':'day_done';
        if(s.step==='content_review'){s.content_draft=draft(db);db.ready=now();event(db,'content_job','content_agent','Đang chuẩn bị tiêu đề, mô tả và ba phương án ảnh bìa.',{kind:'text',status:'done',version:1,detail_vi:'Nội dung mẫu cho giao diện.'});}
      }
      result={step:s.step,card:s.pending_card};
    } else if(url.pathname==='/api/content/retry' && method==='POST') {
      if(s.step!=='content_review' || !s.content_draft) fail('Chưa có nội dung để làm lại.');
      if(s.content_draft.version>=CONTENT_ATTEMPTS) fail('Đã đủ 3 phiên bản nội dung.');
      if(!body.feedback_vi?.trim()) fail('Chị hãy nhập góp ý trước khi làm lại.');
      s.content_draft=draft(db,s.content_draft.version+1,[...s.content_draft.feedback_history,body.feedback_vi.trim()]);db.ready=now();
      event(db,'content_job','content_agent','Đang làm lại nội dung theo góp ý của chị Lan.',{kind:'image',status:'running',version:s.content_draft.version,detail_vi:body.feedback_vi});result={draft:s.content_draft};
    } else if(url.pathname==='/api/content/apply' && method==='POST') {
      if(s.step!=='content_review' || !s.content_draft) fail('Chưa có nội dung để áp dụng.');
      const cover=s.content_draft.images.find(i=>i.option===body.cover_option && ['done','cached'].includes(i.status));
      if(!cover) fail('Chọn một ảnh đã tạo xong để tiếp tục.');
      s.demo_shop={...s.demo_shop,title:s.content_draft.title,description:s.content_draft.description,images:[cover.path,...original.images.slice(1)],active_voucher_pct:s.active_package?.package.voucher_pct || 0};
      s.step='day_done';event(db,'content_applied','system','Đã áp dụng nội dung chị Lan chọn.',{version:s.content_draft.version,cover_option:cover.option});result={listing:s.demo_shop};
    } else if(url.pathname==='/api/night' && method==='POST') {
      if(s.step!=='day_done') fail('Hoàn tất quyết định và nội dung trước khi kết thúc ngày.');
      const day=s.day;
      event(db,'market_result','market','Đã tổng hợp kết quả ngày mô phỏng.',{metrics:{shop_id:'D',day,impressions:4200,clicks:136,orders:8,revenue:1358000,ads_spend:s.active_package?45000:0,roas:s.active_package?6.8:null,fees:220910,profit_after_fees:172090}});
      const summary={day,history_updates:s.memory_enabled?['Ghi nhận gói chị Lan đã duyệt và kết quả trong ngày.']:[],pref_candidates:s.memory_enabled && s.content_draft?.feedback_history.length?['Chị Lan ưu tiên ảnh nền sáng. Sáng mai cần hỏi xác nhận trước khi đặt thành luật.']:[],calibration:{factor:s.memory_enabled?0.87:1,points:s.memory_enabled?Math.min(day*3,30):0,mape_today:0.24},lesson_ops:s.memory_enabled?[{op:'ADD',lesson_id:'preview-lesson',text_vi:'Ưu tiên làm rõ thông tin sản phẩm và ngân sách phù hợp với chủ shop.',scope:'quat_mini',evidence:[`D-${day}`]}]:[],rejected_ops:0,memory_md_path:""};
      if(summary.pref_candidates.length)db.styleCandidate=true;
      s.last_night=summary;event(db,'memory_write','memory',s.memory_enabled?'Đã cập nhật bộ nhớ cho ngày tiếp theo.':'Bộ nhớ đang tắt; không ghi nhận bài học.',{compartment:'history',summary_vi:'Tóm tắt ngày mô phỏng.'});event(db,'night_summary','memory','Hoàn tất tổng kết ban đêm.',{summary});const complete=s.day===SIMULATION_DAYS;if(!complete)s.day++;s.step=complete?'complete':'idle';s.pending_card=null;s.content_draft=null;db.ready=null;
      result={summary,next_day:s.step==='complete'?null:s.day};
    } else if(url.pathname==='/api/proof' && method==='GET') result=db.proof || proof;
    else fail('Chưa có dữ liệu xem trước cho thao tác này.');
    write(db);return clone(result);
  }
  return {request};
}
