"""Headless native workflow against Data's local simulator and durable store."""

import asyncio
import json
from pathlib import Path
from statistics import mean
from uuid import uuid4
from fastapi.testclient import TestClient
from app.core.paths import RUNS_DIR
from app.domain.models.learning import RunResult
from app.domain.models.metrics import DayMetrics, ProofMetric, ProofReport
from app.runtime.data_worker import DataWorker
from app.simulation.content import OfflineContent
from data.growth_data.api import create_app
from data.growth_data.service import Principal
from data.growth_data.simulation import aggregate
from data.growth_data.storage import many, one


def run(settings, days=7, memory_enabled=True, seed=42, *, home=None, seller_session_id=None):
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError('days must be 1..7')
    shop=settings.demo_shop
    if shop not in 'ABCDE' or len(shop) != 1:
        raise ValueError('shop must be A, B, C, D or E')
    home=Path(home) if home is not None else RUNS_DIR/f'sim-{shop}-{uuid4().hex}'
    config=settings.model_copy(update={'llm_mode':'offline','media_mode':'offline','seed':seed})
    defaults={'execution_profile':'external','content_mode':'worker','learning_mode':'external',
              'mode':'offline','driver_config':{'agent_version':'native'}}
    api=create_app(home,content_mode='worker',learning_mode='external',bootstrap_defaults=defaults,
                   product_image_path=config.demo_product_image_path or None)
    service=api.state.service
    worker=DataWorker(service,config,content_factory=OfflineContent)
    seller=service.authenticate(sid=seller_session_id) if seller_session_id else service.bootstrap()
    with service.store.connect(write=True) as c:
        created=service.create_run(c,seller,{**defaults,'seed':seed,'memory_enabled':memory_enabled,
                                             'simulation_days':days,'demo_shop_id':shop})
    rid=created['run_id']
    simulated=Principal('proof_seller','simulated_seller',None,(rid,),(shop,))
    orchestrator=Principal('proof_orchestrator','orchestrator',None,(rid,),('*',))
    with TestClient(api) as client:
        client.cookies.set('growth_sid',seller.session_id)
        preset=client.get('/api/state').json().get('brief_preset')
        response=client.post('/api/brief/confirm',headers={'X-Request-ID':'proof-brief','Idempotency-Key':'proof-brief'},
            json=preset or {'intent':'increase_orders','goal_vi':'Tăng đơn','allow_ads':True,'ads_daily_cap':None,
                            'content_refresh':True,'duration_days':3})
        if response.status_code != 200:
            raise RuntimeError(f'brief failed: {response.status_code} {response.text}')
        for day in range(1,days+1):
            with service.store.connect(write=True) as c:
                state=service.run(c,seller,rid)
                op=service.operation(c,seller,rid,'start_day',{'expected_day':day,'expected_version':state['version']})
            worker._operation(op)
            with service.store.connect() as c:
                op=service.entity(c,'operations',rid,'operation_id',op['operation_id'])
            if op['status']!='succeeded':
                raise RuntimeError(f'native operation failed on day {day}: {op["error_code"]}')
            while True:
                with service.store.connect() as c:
                    background=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id!=? AND status='queued' AND provider='assigned_worker' ORDER BY rowid LIMIT 1",(rid,shop))
                if not background:
                    break
                asyncio.run(worker._content(background))
                with service.store.connect() as c:
                    current=service.entity(c,'content_jobs',rid,'job_id',background['job_id'])
                if current['status'] not in ('succeeded','failed','timed_out'):
                    raise RuntimeError('background content did not reach a terminal state')
            with service.store.connect(write=True) as c:
                card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id=? AND status='pending' ORDER BY rowid LIMIT 1",(rid,shop))
                if card and card['question_id']:
                    question=service.entity(c,'rule_questions',rid,'question_id',card['question_id'])
                    service.decision(c,simulated,rid,{'target_type':'rule_question','target_id':question['question_id'],
                        'target_version':1,'action':'approve','rule_answer':True})
                if card and card['kind']=='offer':
                    proposal=service.entity(c,'proposals',rid,'proposal_id',card['proposal_id'])
                    decision=service.decision(c,simulated,rid,{'target_type':'proposal','target_id':proposal['proposal_id'],
                        'target_version':proposal['version'],'action':'approve'})
                    if proposal['package']['content_refresh']:
                        job=service.content_create(c,orchestrator,rid,shop,
                            {'proposal_id':proposal['proposal_id'],'product_id':proposal['product_id']})
                    else:
                        _,versions=service.evaluation(c,rid,shop,proposal['package'])
                        service.apply(c,orchestrator,rid,{'proposal_id':proposal['proposal_id'],
                            'approval_decision_id':decision['decision_id'],'expected_inventory_version':versions['inventory_version'],
                            'expected_rules_version':versions['rules_version']})
                        job=None
                else: job=None
            if job:
                asyncio.run(OfflineContent(worker_bridge(service),config,worker._llm(rid,config)).process_job(rid,job['job_id']))
                if day==1 and shop=='D':
                    with service.store.connect(write=True) as c:
                        job=service.content_create(c,orchestrator,rid,shop,{'proposal_id':job['proposal_id'],
                            'product_id':job['product_id'],'feedback_vi':'Ảnh nền tối quá, làm sáng hơn giúp chị.',
                            'expected_current_attempt':job['attempt'],'retry_scope':'all'})
                    asyncio.run(OfflineContent(worker_bridge(service),config,worker._llm(rid,config)).process_job(rid,job['job_id']))
                with service.store.connect(write=True) as c:
                    content=service.entity(c,'content_versions',rid,'content_id',job['output_content_ids'][0])
                    decision=service.decision(c,simulated,rid,{'target_type':'content','target_id':content['content_id'],
                        'target_version':content['version'],'action':'approve','cover_option':'A'})
                    service.publish(c,orchestrator,rid,content['content_id'],{'approval_decision_id':decision['decision_id'],
                        'expected_active_content_id':service.product(c,rid,shop)['active_content_id'],'skip_video':True})
            night=service.begin_night(seller,rid,f'proof-night-{day}',day)
            if memory_enabled:
                with service.store.connect() as c:
                    handoff=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(rid,day))
                if handoff['status']=='pending': worker._night(handoff)
            with service.store.connect() as c:
                night=service.entity(c,'operations',rid,'operation_id',night['operation_id'])
                handoff=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(rid,day))
            if night['status']!='succeeded':
                raise RuntimeError(f'night failed on day {day}: {handoff["error_code"]}')
    with service.store.connect() as c:
        state=service.entity(c,'runs',rid,'run_id',rid)
        daily=[]; errors=[]
        for day in range(1,days+1):
            rows=many(c,"SELECT * FROM daily_metrics WHERE run_id=? AND shop_id=? AND day=? AND source='simulated' ORDER BY channel",(rid,shop,day))
            daily.append(DayMetrics.model_validate(aggregate(rows,shop,day)))
            prediction=one(c,'SELECT * FROM daily_predictions WHERE run_id=? AND shop_id=? AND day=?',(rid,shop,day))
            if prediction: errors.append(abs(prediction['payload']['issued_point']-daily[-1].orders))
        negotiations=many(c,"SELECT * FROM negotiations WHERE run_id=? AND shop_id=? AND status!='running' ORDER BY day",(rid,shop))
        versions=many(c,'SELECT skill_id,MAX(version) AS version FROM skill_versions WHERE run_id=? AND shop_id=? GROUP BY skill_id',(rid,shop))
        events=many(c,"SELECT actor_role,payload_json FROM events WHERE run_id=? AND shop_id=? AND type='agent_completed'",(rid,shop))
        counts={}
        for event in events:
            source=event['payload'].get('source','unknown'); counts[source]=counts.get(source,0)+1
        invalid=[]
        if state['phase']!='complete': invalid.append('RUN_INCOMPLETE')
        if len(errors)!=days: invalid.append('DAILY_PREDICTIONS_MISSING')
        if one(c,"SELECT seq FROM events WHERE run_id=? AND type IN ('skill_artifact_invalid','base_skill_changed')",(rid,)):
            invalid.append('SKILL_ARTIFACT_INVALID')
    result=RunResult(run_id=rid,shop_id=shop,seed=seed,days=days,memory_enabled=memory_enabled,mode='offline',
        daily_metrics=daily,forecast_errors=errors,negotiation_rounds=[n['platform_rounds'] for n in negotiations],
        budget_slots_used=worker.store.llm_calls_used(rid),source_counts=counts,
        skill_versions={v['skill_id']:v['version'] for v in versions},valid=not invalid,invalid_reasons=invalid,
        report_path=str(home/f'{rid}.json'))
    Path(result.report_path).write_text(result.model_dump_json(indent=2),encoding='utf-8')
    return result


def worker_bridge(service):
    from app.infrastructure.data_content import DataContentBridge
    return DataContentBridge(service)


def compare(on,off):
    if (on.shop_id,on.seed,on.days,on.mode)!=(off.shop_id,off.seed,off.days,off.mode) or not on.memory_enabled or off.memory_enabled:
        raise ValueError('incompatible comparison')
    if not on.valid or not off.valid: raise ValueError('invalid run')
    metrics=[]
    for key,label,better,unit,calc in (
        ('profit_after_fees','Lãi sau phí','high','đ',lambda r:sum(x.profit_after_fees for x in r.daily_metrics)),
        ('orders','Số đơn','high','đơn',lambda r:sum(x.orders for x in r.daily_metrics)),
        ('ads_spend','Chi quảng cáo','low','đ',lambda r:sum(x.ads_spend for x in r.daily_metrics)),
        ('forecast_mae','Sai số dự báo','low','đơn',lambda r:mean(r.forecast_errors) if r.forecast_errors else None),
        ('rounds','Lượt thương lượng','low','lượt',lambda r:mean(r.negotiation_rounds) if r.negotiation_rounds else None)):
        a,b=calc(on),calc(off)
        if a is not None and b is not None:
            metrics.append(ProofMetric(key=key,label_vi=label,better=better,on=float(a),off=float(b),unit=unit))
    return ProofReport(seed=on.seed,days=on.days,run_on=on.run_id,run_off=off.run_id,metrics=metrics,
        note_vi=f'Mô phỏng shop {on.shop_id}; cùng seed, dữ liệu và quy tắc; nguồn offline_simulator. Kết quả là tác động tổng hợp của bộ nhớ, không chứng minh nguyên nhân riêng từng skill.')


def provenance(result):
    """Read identifiers and artifact metadata from the completed run's Data DB."""
    import sqlite3
    path=Path(result.report_path).parent/'growth.db'
    with sqlite3.connect(path) as c:
        c.row_factory=sqlite3.Row
        run=c.execute('SELECT * FROM runs WHERE run_id=?',(result.run_id,)).fetchone()
        records=c.execute('SELECT payload_json FROM skill_versions WHERE run_id=? AND shop_id=? ORDER BY skill_id,version',
                          (result.run_id,result.shop_id)).fetchall()
        versions=[]
        for row in records:
            value=json.loads(row['payload_json']); b=value['bundle']
            versions.append({'skill_id':b['skill']['skill_id'],'version':b['version'],
                'effective_from_day':b['effective_from_day'],'artifact_hash':b['artifact_hash'],
                'base_hash':b['skill']['base_hash'],'eval_level':value['eval_level'],'eval_checks':value['eval_checks']})
        rows=c.execute("SELECT payload_json FROM knowledge_records WHERE run_id=? AND compartment='calibration'",(result.run_id,)).fetchall()
        calibrations=[{'category':(v:=json.loads(row['payload_json'])['value'])['category'],
                       'factor':v['value']['factor'],'samples':len(v['samples'])} for row in rows]
        assets=[row['source_reference'] for row in c.execute("SELECT DISTINCT source_reference FROM assets WHERE run_id=? AND shop_id=? AND origin='supplied' ORDER BY source_reference",(result.run_id,result.shop_id))]
        phases=[{'day':row['day'],'status':row['status'],'source':json.loads(row['payload_json'])['source']}
                for row in c.execute('SELECT day,status,payload_json FROM reflection_receipts WHERE run_id=? ORDER BY day',(result.run_id,))]
        uses=[]
        for row in c.execute('SELECT day,kind,pinned_context_json FROM negotiations WHERE run_id=? AND shop_id=? AND pinned_context_json IS NOT NULL ORDER BY day',(result.run_id,result.shop_id)):
            pinned=json.loads(row['pinned_context_json']); view=pinned['memory']['skill']
            uses.append({'day':row['day'],'kind':row['kind'],'skill_id':view['bundle']['skill']['skill_id'],
                'version':view['bundle']['version'],'artifact_hash':view['bundle']['artifact_hash'],
                'policy_ids':[item['policy_id'] for item in view['seed']['uses']]})
        schema=c.execute('PRAGMA user_version').fetchone()[0]
        return {'database':str(path),'schema_version':schema,'initial_snapshot_hash':run['initial_snapshot_hash'],
            'simulator_version':run['simulator_version'],'assets':assets,'artifacts':versions,
            'calibration':calibrations,'reflection_phases':phases,'pinned_uses':uses,
            'budget_slots_used':result.budget_slots_used,'source_counts':result.source_counts}
