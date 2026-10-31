"""Disposable native-agent context bound to an existing Data run and attempt."""

from types import SimpleNamespace

from app.domain.models.intent import IntentBrief
from app.domain.models.metrics import Forecast
from app.domain.models.packages import ActivePackage, Package
from app.domain.models.shops import FeeConfig, ShopPrivate, ShopPublic
from app.infrastructure.data_knowledge import DataKnowledgeSource
from app.infrastructure.llm import LLMClient
from app.infrastructure.sqlite_store import SqliteKnowledgeStore
from app.memory.gateway import MemoryGateway
from app.runtime.session import Session
from data.growth_data.service import Principal
from data.growth_data.errors import require
from data.growth_data.finance import violation_message
from data.growth_data.seed import world as data_world
from data.growth_data.storage import dumps, fingerprint, now, one


class DataMarket:
    def __init__(self, service, run_id, shop_id):
        self.service, self.run_id, self.shop_id = service, run_id, shop_id

    def forecast_package(self, public, package, day, seed, calibration):
        with self.service.store.connect() as c:
            value=self.service.forecast_values(c,self.run_id,self.shop_id,package.model_dump(mode='json'),day)
        return Forecast.model_validate({key:value[key] for key in ('low','point','high','factor_used','stock_warning')})


class DataEventLog:
    def __init__(self, service, source, negotiation_id=None, operation_id=None):
        self.service, self.source, self.negotiation_id = service, source, negotiation_id
        self.operation_id=operation_id
        self.turns={}
        self.started_invocations=set()
        self.last_proposal=None
        self.referee_action=None

    def _fence(self, c, run_id):
        if self.operation_id:
            op=one(c,'SELECT * FROM operations WHERE run_id=? AND operation_id=?',(run_id,self.operation_id))
            require(op and op['status']=='running' and op['claimed_by']=='native_orchestrator' and op['lease_until'] and op['lease_until']>=now(),'LEASE_EXPIRED','Operation không còn quyền ghi')

    def add(self, run_id, day, kind, actor, shop_id, text_vi, data):
        s=self.service
        if kind in {'platform_turn','shop_turn'}:
            role='platform_agent' if kind=='platform_turn' else 'shop_agent'
            principal=Principal('native_'+role,role,None,(run_id,),(shop_id,))
            with s.store.connect() as c:
                product=s.product(c,run_id,shop_id)
            action=data['action']
            body={'product_id':product['product_id'],'negotiation_id':self.negotiation_id,
                  'parent_proposal_id':self.last_proposal,'package':data.get('package'),
                  'shared_reason':text_vi,'stance':'propose' if action=='counter' else action,
                  'native_action':action,'turn_id':data['turn_id']}
            def persist(c):
                self._fence(c,run_id)
                return s.create_proposal(c,principal,run_id,shop_id,body)
            result=s.command(principal,run_id,'native/turn',data['turn_id'],body,persist)
            self.last_proposal=result['proposal_id']
            with s.store.connect() as c:
                event=one(c,'SELECT seq FROM events WHERE run_id=? AND entity_id=? AND type=?',(run_id,self.last_proposal,kind))
            self.turns[data['turn_id']]=event['seq']
            return event
        if kind=='negotiation_finished':
            return None
        safe={key:value for key,value in data.items() if key in {'negotiation_id','action','source','role','tool_name','tool_call_id','requested_by','status','error_code','invocation_id','record_refs','who','items','versions','rules_version','memory_revision','round','next_actor'}}
        if kind=='referee_review':
            self.referee_action=data['action']
            safe['evidence_refs']=[self.turns[ref] for ref in data.get('evidence_refs',[]) if ref in self.turns]
        with s.store.connect(write=True) as c:
            self._fence(c,run_id)
            if kind=='code_check':
                proposal=s.entity(c,'proposals',run_id,'proposal_id',self.last_proposal)
                require(proposal['shop_id']==shop_id and proposal['negotiation_id']==self.negotiation_id,'EVIDENCE_INVALID','Kiểm tra không thuộc lượt thương lượng')
                safe.update(proposal_id=proposal['proposal_id'],round=proposal['round'],ok=bool(data['ok']),
                    checks=[{'code':code,'ok':False,'message_vi':violation_message(code)} for code in data.get('codes',[])])
            if kind=='referee_review':
                safe['focused_question']=s.safe_text(c,run_id,data['focused_question']) if data.get('focused_question') else None
                safe['unresolved_terms']=[s.safe_text(c,run_id,term) for term in data.get('unresolved_terms',[])]
            seq=s.event(c,run_id,day,kind,actor,shop_id,safe,visibility='shop_private' if kind in {'tool_called','tool_result','agent_completed','memory_read','code_check'} else 'shared',text=s.safe_text(c,run_id,text_vi),eid=self.negotiation_id or '')
            invocation=data.get('invocation_id')
            if self.negotiation_id and actor in {'platform','shop','referee'} and invocation and (kind=='agent_completed' or (kind=='tool_called' and invocation not in self.started_invocations)):
                self.started_invocations.add(invocation)
                neg=s.entity(c,'negotiations',run_id,'negotiation_id',self.negotiation_id)
                round_no=max(1,min(3,neg['platform_rounds']+(actor=='platform')))
                phase={'platform':'proposal','shop':'response','referee':'referee'}[actor]
                status='done' if kind=='agent_completed' else 'running'
                s.event(c,run_id,day,'agent_telemetry',actor,shop_id,{'negotiation_id':self.negotiation_id,'task_id':invocation,'round':round_no,'phase':phase,'status':status,'label_vi':'Agent đang xử lý' if status=='running' else 'Agent đã xử lý','source':data.get('source')},text='Agent cập nhật tác vụ',eid=self.negotiation_id)
        return SimpleNamespace(seq=seq)

    def since(self, run_id, after_seq):
        return [event for event in self.source.events() if event.seq>after_seq]

    def last_seq(self, run_id):
        with self.service.store.connect() as c:
            return c.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?',(run_id,)).fetchone()[0]


def load_data_context(service, settings, run_id, shop_id, *, negotiation_id=None, operation_id=None, brief=None, llm=None):
    with service.store.connect() as c:
        run=service.entity(c,'runs',run_id,'run_id',run_id)
        public=ShopPublic.model_validate(service.public(c,run_id,shop_id))
        rules, rules_version=service.rules(c,run_id,shop_id)
        cost=service.current_cost(c,run_id,shop_id)
        private=ShopPrivate(owner_name=data_world()['shops'][shop_id]['private']['owner_name'],unit_cost=cost['unit_cost_vnd']+cost['other_unit_cost_vnd'],rules=rules)
        active_row=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(run_id,shop_id))
        active=ActivePackage(package=Package.model_validate(active_row['package_snapshot']),start_day=active_row['start_day'],end_day=active_row['end_day'],ads_paused=active_row['ads_status']=='paused',card_id='') if active_row else None
        fee,_=service.fee_config(c,run_id)
        fee_model=FeeConfig(fixed_pct=fee['rate_bps']/100,transaction_pct=0,tax_pct=0,per_order=fee['per_order'])
        brief=brief or run['brief']
        if not brief: raise ValueError('confirmed brief missing')
    scoped_settings=settings.model_copy(update={'seed':run['seed'],'demo_shop':shop_id,'llm_mode':run['mode']})
    source=DataKnowledgeSource(service,run_id,shop_id)
    store=SqliteKnowledgeStore(service.store)
    log=DataEventLog(service,source,negotiation_id,operation_id)
    state=SimpleNamespace(public=public,private=private,active=active,metrics={})
    world=SimpleNamespace(fees=fee_model,trend={'daily_growth':.12},calendar=[{'name':'11.11'}])
    session=Session(run_id=run_id,settings=scoped_settings,world=world,states={shop_id:state},store=store,log=log,
                    llm=llm or LLMClient(scoped_settings,store=store,run_id=run_id),day=run['current_day'],
                    simulation_days=run['simulation_days'],brief=IntentBrief.model_validate(brief),rules_version=rules_version,
                    market=DataMarket(service,run_id,shop_id))
    session.memory=MemoryGateway(store,bool(run['memory_enabled']),log=log,run_id=run_id,session=session,source=source)
    source.session=session
    return session


def pin_context(service, run_id, negotiation_id, context, event_log=None):
    payload=context.model_dump(mode='json')
    with service.store.connect(write=True) as c:
        if event_log: event_log._fence(c,run_id)
        neg=service.entity(c,'negotiations',run_id,'negotiation_id',negotiation_id)
        if neg['pinned_context'] is not None and neg['pinned_context_hash']!=fingerprint(payload):
            raise ValueError('pinned context changed')
        c.execute('UPDATE negotiations SET pinned_context_json=?,pinned_context_hash=? WHERE run_id=? AND negotiation_id=?',
                  (dumps(payload),fingerprint(payload),run_id,negotiation_id))
        skill=context.memory.skill
        service.event(c,run_id,context.day,'skill_used','platform_agent',context.shop_id,
                      {'negotiation_id':negotiation_id,'skill_id':skill.bundle.skill.skill_id,'version':skill.bundle.version,'artifact_hash':skill.bundle.artifact_hash,'effective_from_day':skill.bundle.effective_from_day,'policy_uses':[use.model_dump(mode='json') for use in skill.seed.uses]},
                      visibility='shop_private',text='Đã ghim kỹ năng cho lượt thương lượng')
