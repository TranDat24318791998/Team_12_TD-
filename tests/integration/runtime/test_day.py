import pytest
from app.core.settings import Settings
from app.domain.models.cards import SellerDecision
from app.domain.models.metrics import DayMetrics
from app.domain.models.packages import ActivePackage, Package
from app.domain.policies import DEFAULT_PACKAGE
from app.infrastructure.eventlog import EventLog
from app.runtime.day import WorkflowError, apply_reviewed_content, close_day, confirm_brief, match_opportunities, monitor_active_packages, start_day, submit_decision
from app.runtime.session import Session
from tests.fakes.content import FakeContent
from tests.fakes.market import FakeMarket


def session_with_content(tmp_path):
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=FakeMarket(),log=EventLog())
    session.content=FakeContent(session,tmp_path)
    confirm_brief(session,{'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,'ads_daily_cap':None,
                            'content_refresh':True,'duration_days':3})
    start_day(session)
    return session


def test_wrong_version_and_missing_media_are_never_applied(tmp_path):
    session=session_with_content(tmp_path); card=session.pending_card
    submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))
    draft=session.content.retry('D','Nền sáng')
    with pytest.raises(WorkflowError) as stale:
        apply_reviewed_content(session,card.card_id,1,1,'B')
    assert stale.value.code=='STALE_DRAFT' and session.states['D'].active is None
    session.content.image.unlink()
    with pytest.raises(WorkflowError) as missing:
        apply_reviewed_content(session,card.card_id,1,draft.version,'B')
    assert missing.value.code=='COVER_NOT_READY' and session.states['D'].active is None


def test_video_skip_must_be_explicit(tmp_path):
    session=session_with_content(tmp_path); card=session.pending_card
    submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))
    session.content.video.unlink()
    with pytest.raises(WorkflowError) as missing:
        apply_reviewed_content(session,card.card_id,1,1,'A')
    assert missing.value.code=='VIDEO_NOT_READY'
    apply_reviewed_content(session,card.card_id,1,1,'A',skip_video=True)
    assert session.states['D'].active is not None and session.states['D'].public.video is None


def test_monitor_pauses_low_roas_and_match_excludes_low_stock():
    session=Session.new(Settings(_env_file=None,llm_mode='offline'),market=FakeMarket(),log=EventLog())
    pkg=Package(**DEFAULT_PACKAGE)
    e=session.states['E']
    e.active=ActivePackage(package=pkg,start_day=1,end_day=5,card_id='card')
    for day in (1,2):
        e.metrics[day]=DayMetrics(shop_id='E',day=day,impressions=10,clicks=2,orders=1,revenue=90000,
                                  ads_spend=18000,roas=3.0,fees=0,profit_after_fees=0)
    session.day=3
    monitor_active_packages(session)
    assert e.active.ads_paused
    chosen=match_opportunities(session)
    assert 'C' not in chosen and 'D' in chosen
    assert any(item['shop_id']=='C' for item in session.log.since(session.run_id,0)[-1].data['excluded'])
    session.day=6
    assert monitor_active_packages(session)==['E'] and e.active is None


def test_night_retry_does_not_repeat_settlement(tmp_path,monkeypatch):
    import app.runtime.day as day_module
    session=session_with_content(tmp_path); card=session.pending_card
    submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))
    apply_reviewed_content(session,card.card_id,1,1,'A')
    real=day_module.run_night
    monkeypatch.setattr(day_module,'run_night',lambda *_: (_ for _ in ()).throw(RuntimeError('simulated error')))
    with pytest.raises(RuntimeError): close_day(session,1)
    assert session.market.calls==1 and session.step=='day_done'
    monkeypatch.setattr(day_module,'run_night',real)
    assert close_day(session,1)['next_day']==2 and session.market.calls==1


def test_negotiate_replaces_card_and_requires_new_approval(tmp_path):
    session=session_with_content(tmp_path); old=session.pending_card
    result=submit_decision(session,SellerDecision(card_id=old.card_id,expected_card_version=1,expected_brief_version=1,
        action='negotiate',note_vi='Giảm voucher còn 2%'))
    assert result=='awaiting_decision' and session.pending_card.card_id!=old.card_id
    assert session.pending_card.package.voucher_pct==2 and session.states['D'].active is None
    with pytest.raises(WorkflowError):
        submit_decision(session,SellerDecision(card_id=old.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))


def test_string_skip_video_cannot_bypass_approval(tmp_path):
    session=session_with_content(tmp_path); card=session.pending_card
    submit_decision(session,SellerDecision(card_id=card.card_id,expected_card_version=1,expected_brief_version=1,action='accept'))
    session.content.video.unlink()
    with pytest.raises(WorkflowError) as error:
        apply_reviewed_content(session,card.card_id,1,1,'A',skip_video='false')
    assert error.value.code=='INVALID_APPLY' and session.states['D'].active is None
