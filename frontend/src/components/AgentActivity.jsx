import {deriveActivity} from '../activity.js';
import {dec,vnd} from '../format.js';
import {Icon} from './Icon.jsx';

const actionLabels={propose:'Đã gửi đề xuất',counter:'Đã phản đề xuất',accept:'Đã đồng ý',reject:'Đã từ chối',withdraw:'Đã rút đề xuất'};
const refereeLabels={continue:'Tiếp tục trao đổi',refocus:'Cần tập trung lại',ask_human:'Cần hỏi người bán',stop:'Dừng thương lượng'};
const packageFields=[
  ['ads_daily_budget','Quảng cáo / ngày',value=>value===0?'Không chạy':vnd(value)],
  ['voucher_pct','Voucher',value=>value==null?'—':dec(value,0)+'%'],
  ['stop_roas_below','Ngưỡng dừng ROAS',value=>value==null?'Chưa đặt':dec(value)],
  ['stop_after_days','Số ngày dưới ngưỡng',value=>value==null?'—':value+' ngày'],
  ['duration_days','Thời hạn gói',value=>value==null?'—':value+' ngày'],
  ['content_refresh','Nội dung',value=>value==null?'—':value?'Làm mới':'Giữ nguyên'],
];

function AgentNode({side,event,running}){
  const platform=side==='platform_agent';
  const active=running?.actor===side;
  const status=active?'Đang xử lý':event?(actionLabels[event.data?.action] || 'Đã phản hồi'):'Chờ lượt';
  return <span className={'process-agent '+(platform?'platform':'shop')+(active?' is-working':'')} data-agent={side} data-working={active?'true':'false'} title={status}><Icon name={platform?'megaphone':'shield'}/>{platform?'Agent sàn':'Agent shop'}<span className="sr-only">: {status}</span></span>;
}

export function PackageComparison({baseline,latest,label}){
  if(!baseline || !latest)return <div className="package-empty"><Icon name="voucher"/><h3>Điều khoản đang thương lượng</h3><p>Các điều khoản sẽ xuất hiện khi agent gửi gói đầu tiên.</p></div>;
  const changed=packageFields.filter(([field])=>baseline[field]!==latest[field]).length;
  return <div className="package-comparison"><div className="between"><h3>Gói đã thay đổi gì?</h3><span className="comparison-count">{changed?changed+' điều chỉnh':'Chưa điều chỉnh'}</span></div><div className="package-table-wrap"><table><caption className="sr-only">So sánh điều khoản đề xuất với gói mới nhất của hai agent</caption><thead><tr><th scope="col">Điều khoản</th><th scope="col">{label}</th><th scope="col">Mới nhất</th></tr></thead><tbody>{packageFields.map(([field,name,format])=><tr key={field} className={baseline[field]!==latest[field]?'is-changed':''}><th scope="row">{name}</th><td>{format(baseline[field])}</td><td>{baseline[field]!==latest[field] && <span className="sr-only">Đã thay đổi: </span>}{format(latest[field])}</td></tr>)}</tbody></table></div><p className="comparison-note">Điều khoản được trao đổi giữa hai agent. Chủ shop vẫn là người quyết định áp dụng.</p></div>;
}

export function AgentActivity({state,events,preview,error,pending}){
  const activity=deriveActivity(state,events);
  const {check,referee}=activity;
  const checkLabel=check?(!activity.checkMatchesLatest?'Có gói mới · Chờ kiểm tra lại':check.data.ok?'Gói đã qua kiểm tra':'Có ràng buộc chưa đạt'):'Chưa có kết quả kiểm tra';
  const reference=referee?.data;
  const busy=pending==='/api/decision' && !activity.negotiating;
  const refereeLabel=!error && activity.running?.actor==='referee'?'Đang đối chiếu mục tiêu':reference?(refereeLabels[reference.action] || 'Đã đánh giá lượt trao đổi'):'Chưa có đánh giá trọng tài';
  const resolved=['approved','rejected'].includes(activity.outcome);
  const stopped=['no_fit','failed','stopped'].includes(activity.outcome);
  const current=activity.awaiting?3:activity.running?.actor==='platform_agent'?0:activity.running?.actor==='shop_agent'?1:activity.running?2:activity.checkMatchesLatest && check?.data.ok?3:activity.shop?2:activity.platform?1:0;
  const done=[!!activity.platform,!!activity.shop,!!check?.data.ok && activity.checkMatchesLatest,resolved];
  const status=error?'Kết nối gián đoạn · Đang giữ trạng thái gần nhất':busy?'Đang gửi quyết định của chủ shop…':activity.label;
  return <section className="agent-activity compact-activity process-activity" aria-labelledby="agent-activity-title" data-activity-outcome={activity.outcome}>
    <div className="agent-process-row"><h2 id="agent-activity-title">Luồng agent<span className="sr-only"> · {preview?'Minh họa':'Theo dõi phiên'}</span></h2>
      <ol className="agent-process" aria-label="Tiến trình trao đổi giữa các agent">{[
        <AgentNode side="platform_agent" event={activity.platform} running={error?null:activity.running}/>,
        <AgentNode side="shop_agent" event={activity.shop} running={error?null:activity.running}/>,
        <span className="process-agent" title={checkLabel}><Icon name="shield"/>Kiểm tra</span>,
        <span className="process-agent"><Icon name="user"/>{activity.outcome==='rejected'?'Đã từ chối':activity.outcome==='approved'?'Đã duyệt':'Chủ shop duyệt'}</span>
      ].map((node,index)=><li key={index} className={(done[index]?'is-done ':'')+(!error && !resolved && !stopped && (activity.negotiating || activity.awaiting) && current===index?'is-current':'')} aria-current={!error && !resolved && !stopped && (activity.negotiating || activity.awaiting) && current===index?'step':undefined}>{node}</li>)}</ol>
      <div className="activity-badges">{activity.attempt && <span className="activity-attempt">Phiên {activity.attempt}</span>}<span className="activity-round">{activity.round?'Vòng '+activity.round+' / tối đa '+activity.maxRounds:'Chưa bắt đầu vòng'}</span></div>
      <details className="activity-details"><summary title="Điều khoản và kiểm tra chi tiết">Chi tiết <Icon name="chevron"/></summary><div className="activity-detail-body"><p className="process-detail-status">{status} · Trọng tài: {refereeLabel}</p><PackageComparison baseline={activity.baseline} latest={activity.latest} label={activity.baselineLabel}/><div className="agent-guardians"><div className="guardian code-guardian"><h3>Code kiểm tra</h3><p>{checkLabel}</p><ul>{(check?.data.checks || []).map((item,index)=><li key={index}><Icon name={item.ok?'check':'close'}/>{item.message_vi}</li>)}</ul></div><div className="guardian referee-guardian"><h3>Trọng tài</h3><p>{refereeLabel}</p>{reference && <div className="referee-reason">{referee.text_vi}{reference.focused_question && <p>{reference.focused_question}</p>}</div>}</div></div></div></details>
    </div>
    <p className={error || stopped || activity.outcome==='rejected'?'process-notice':'sr-only'} role="status">{status}</p>
  </section>;
}
