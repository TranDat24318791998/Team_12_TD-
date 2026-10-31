#!/usr/bin/env python3
"""Run Toàn's workflow with explicitly labelled teammate fixtures."""

import argparse
import json
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.settings import Settings
from app.domain.models.cards import SellerDecision
from app.runtime.day import apply_reviewed_content, close_day, confirm_brief, start_day, submit_decision
from app.runtime.session import Session
from tests.fakes.content import FakeContent
from tests.fakes.market import FakeMarket


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['offline','live'],default='offline')
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    settings=Settings(llm_mode=args.mode,seed=args.seed)
    if args.mode=='live' and (not settings.openai_api_key or not settings.llm_model):
        parser.error('OpenAI key/model chưa được cấu hình; không thể smoke live.')
    with tempfile.TemporaryDirectory(prefix='growth-demo-') as folder:
        session=Session.new(settings,market=FakeMarket())
        session.content=FakeContent(session,Path(folder))
        print('MARKET=fixture; MEDIA=fixture; MODEL='+args.mode)
        confirm_brief(session,{'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,
                               'ads_daily_cap':None,'content_refresh':True,'duration_days':3})
        start_day(session)
        if not session.pending_card:
            raise RuntimeError('Thương lượng không tạo thẻ; xem event log để kiểm tra adapter.')
        card=session.pending_card
        print('CARD',json.dumps(card.package.model_dump(mode='json'),ensure_ascii=False))
        submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=card.version,
            expected_brief_version=card.brief_version,action='accept'))
        draft=session.content.retry('D','Ảnh nền tối quá, làm nền sáng')
        apply_reviewed_content(session,card.card_id,card.brief_version,draft.version,'B')
        summary=close_day(session,1)['summary']
        print('NIGHT',json.dumps(summary.model_dump(mode='json'),ensure_ascii=False))
        print('PREFERENCES',json.dumps([p.model_dump(mode='json') for p in session.memory.prefs_to_ask('D',2)],ensure_ascii=False))
        start_day(session)
        question=session.pending_card
        submit_decision(session,SellerDecision(card_id=question.card_id,expected_card_version=question.version,
            expected_brief_version=question.brief_version,action='accept',rule_answer=True))
        print('NEXT_CONTENT_MEMORY',json.dumps(session.memory.content_view('D').model_dump(mode='json'),ensure_ascii=False))
        print('PLATFORM_MEMORY',json.dumps(session.memory.platform_view('D','quat_mini').model_dump(mode='json'),ensure_ascii=False))
        for event in session.log.since(session.run_id,0):
            if event.type in {'tool_called','tool_result','agent_completed','platform_turn','shop_turn','referee_review'}:
                data={key:value for key,value in event.data.items() if key in
                      {'role','tool_name','tool_call_id','requested_by','source','status','action','turn_id','round','evidence_refs'}}
                print('TRACE',json.dumps({'type':event.type,**data},ensure_ascii=False))
        if args.mode=='live' and not any(event.type=='agent_completed' and event.data.get('source')=='live'
                                         for event in session.log.since(session.run_id,0)):
            raise RuntimeError('Không có invocation live hoàn tất; demo đã fallback offline.')
        print('RUN_LOG', session.log.path)


if __name__=='__main__':
    main()
