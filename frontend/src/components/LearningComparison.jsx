import {Icon} from './Icon.jsx';

const names={seller:'Chủ shop',shop_agent:'Trợ lý',platform_agent:'Agent sàn',system:'Hệ thống'};

function Conversation({branch,request,day,learning}){
  const title=learning?'Có học từ lịch sử':'Không học từ lịch sử';
  const sources=branch?.memory_used || [];
  return <section className={'learning-chat '+(learning?'with-memory':'without-memory')} aria-label={title} data-learning={learning?'on':'off'}>
    <header className="learning-chat-heading"><span className="learning-chat-symbol"><Icon name={learning?'book':'message'}/></span><div><h2>{title}</h2><p>{learning?'Đọc lại phản hồi và kết quả các ngày trước':'Mỗi ngày bắt đầu với dữ liệu hiện tại'}</p></div><span className="memory-switch">{learning?'BỘ NHỚ BẬT':'BỘ NHỚ TẮT'}</span></header>
    <div className="learning-chat-messages" key={day} tabIndex={0} aria-label={'Hội thoại ngày '+day+' · '+title}>
      {request && <article className="compare-message from-seller"><span>Chủ shop · Cùng một yêu cầu</span><p>{request}</p></article>}
      {branch?.messages.length?branch.messages.map(message=><article className={'compare-message '+(message.actor==='seller'?'from-seller':'from-agent')} key={message.id}><span>{names[message.actor]}</span><p>{message.text_vi}</p></article>):<p className="comparison-unavailable">Chưa có hội thoại đối chứng cho ngày này.</p>}
    </div>
    <footer className="learning-chat-foot"><p className="chat-outcome"><Icon name={learning?'check':'info'}/>{branch?.result_vi || 'Chờ dữ liệu từ lần chạy đối chứng'}</p><div className="memory-evidence">{learning?<><Icon name="book"/><span>{sources.length?sources.map((source,index)=><span className="memory-source" key={source.event_seq}>{index>0?' · ':''}Ngày {source.source_day}: {source.text_vi}</span>):day===1?'Ngày đầu tiên · Chưa có lịch sử để đọc':'Chưa có bằng chứng bộ nhớ cho ngày này'}</span></>:<><Icon name="lock"/><span>Vẫn tuân thủ luật shop. Không đọc các lần trao đổi trước.</span></>}</div></footer>
  </section>;
}

export function LearningComparison({day}){
  return <div className="learning-comparison" data-comparison-day={day?.day ?? ''}>
    <Conversation branch={day?.off} request={day?.request_vi} day={day?.day ?? 1} learning={false}/>
    <Conversation branch={day?.on} request={day?.request_vi} day={day?.day ?? 1} learning/>
  </div>;
}

export function SimpleAgentFlow(){
  return <div className="proof-agent-flow" aria-label="Luồng xử lý của cả hai phiên"><span className="flow-caption">CÙNG MỘT LUỒNG</span><span className="flow-actor"><Icon name="megaphone"/>Agent sàn</span><span className="flow-connector" aria-hidden="true">↔</span><span className="flow-actor shop"><Icon name="shield"/>Agent shop</span><span className="flow-connector" aria-hidden="true">→</span><span className="flow-actor"><Icon name="check"/>Code kiểm tra</span><span className="flow-connector" aria-hidden="true">→</span><span className="flow-actor"><Icon name="user"/>Chủ shop duyệt</span><span className="flow-memory-note">Khác nhau ở dữ liệu lịch sử được đọc</span></div>;
}
