"""Explicit recovery of a known historical failed adjustment; no provider calls."""

from conftest import headers
from growth_data.models import DEMO_D_BRIEF
from growth_data.service import Principal
from growth_data.storage import one
from test_workflow import start


def test_restore_offer_route_is_versioned_idempotent_and_authenticated(client, service, run):
    assert client.post('/api/brief/confirm',json=DEMO_D_BRIEF.copy(),headers=headers('', 'brief') | {'Authorization':''}).status_code==200
    original=start(client)
    with service.store.connect(write=True) as c:
        c.execute("UPDATE runs SET execution_profile='external',config_json=json_set(config_json,'$.driver.agent_version','native') WHERE run_id=?",(run,))
    state=client.get('/api/state').json();card=state['pending_card']
    queued=client.post('/api/decision',json={'card_id':card['card_id'],'expected_card_version':card['version'],
        'expected_brief_version':card['brief_version'],'action':'negotiate','note_vi':'Giảm thêm'},headers=headers('', 'negotiate') | {'Authorization':''})
    assert queued.status_code==202,queued.text
    principal=Principal('native_orchestrator','orchestrator',None,(run,),('*',))
    with service.store.connect(write=True) as c:
        op=service.entity(c,'operations',run,'operation_id',queued.json()['operation_id'])
        op=service.operation_claim(c,principal,run,op['operation_id'],{'expected_version':op['version']})
        runtime=service.entity(c,'shop_runtime',run,'shop_id','D')
    body={'day':1,'kind':'propose','expected_shop_version':runtime['version'],'source_card_id':card['card_id'],'owner_note_vi':'Giảm thêm'}
    negotiation=service.command(principal,run,'native/negotiation',op['operation_id']+':D',body,
        lambda c:service.new_negotiation(c,principal,run,'D',body))
    with service.store.connect(write=True) as c:
        service.finalize_negotiation(c,principal,run,negotiation['negotiation_id'],{'expected_version':negotiation['version'],
            'status':'failed','final_proposal_id':None,'rounds':0,'reason_vi':'Chưa có gói điều chỉnh.','referee_action':'ask_human'})
        # Historical operation predates automatic restoration.
        c.execute("UPDATE operations SET status='succeeded',lease_until=NULL,version=version+1 WHERE run_id=? AND operation_id=?",(run,op['operation_id']))
    state=client.get('/api/state').json();outcome=state['renegotiation']
    assert outcome['restoration_allowed'] and not state['pending_card']
    body={'operation_id':outcome['operation_id'],'expected_operation_version':outcome['operation_version'],
          'source_card_id':outcome['source_card_id'],'expected_source_card_version':outcome['source_card_version'],
          'expected_brief_version':state['brief']['version'],'expected_day':state['day']}
    saved=client.post('/api/negotiation/restore',json=body,headers=headers('', 'restore') | {'Authorization':''})
    assert saved.status_code==200,saved.text
    assert saved.json()['restoration_status']=='restored'
    assert client.post('/api/negotiation/restore',json=body,headers=headers('', 'restore') | {'Authorization':''}).json()==saved.json()
    assert client.post('/api/negotiation/restore',json=body,headers=headers('', 'stale-restore') | {'Authorization':''}).status_code==409
    state=client.get('/api/state').json()
    assert state['pending_card']['proposal_id']==original['proposal_id']
    with service.store.connect() as c:
        assert not one(c,"SELECT call_id FROM llm_call_reservations WHERE run_id=?",(run,))
