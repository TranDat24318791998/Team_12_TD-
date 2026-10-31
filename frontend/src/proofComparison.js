// Conversations come from the authorized proof response, never from UI fallbacks.
const actors=new Set(['seller','shop_agent','platform_agent','system']);
const text=value=>typeof value==='string' && value.trim().length>0;

export function comparisonDays(report){
  if(!Array.isArray(report.comparison_days) || !text(report.run_on) || !text(report.run_off) || report.run_on===report.run_off)return [];
  const rows=report.comparison_days;
  return rows.filter(row=>row && Number.isInteger(row.day) && row.day>=1 && row.day<=report.days
    && rows.filter(other=>other?.day===row.day).length===1 && text(row.request_vi)
    && row.off?.run_id===report.run_off && row.on?.run_id===report.run_on
    && Array.isArray(row.off.memory_used) && row.off.memory_used.length===0
    && [row.off,row.on].every(branch=>Array.isArray(branch.messages))
    && Array.isArray(row.on.memory_used) && row.on.memory_used.every(source=>source && source.run_id===report.run_on && Number.isInteger(source.source_day) && source.source_day>=1 && source.source_day<row.day && Number.isInteger(source.event_seq) && source.event_seq>0 && text(source.text_vi))
  ).sort((a,b)=>a.day-b.day).map(row=>({...row,
    situation_vi:text(row.situation_vi)?row.situation_vi:'',
    takeaway_vi:text(row.takeaway_vi)?row.takeaway_vi:'',
    off:{...row.off,result_vi:text(row.off.result_vi)?row.off.result_vi:'',messages:validMessages(row.off.messages)},
    on:{...row.on,result_vi:text(row.on.result_vi)?row.on.result_vi:'',messages:validMessages(row.on.messages)},
  }));
}

function validMessages(messages){
  return messages.filter(message=>message && text(message.id) && text(message.text_vi) && actors.has(message.actor)
    && messages.filter(other=>other?.id===message.id).length===1);
}
