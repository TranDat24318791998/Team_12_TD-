"""Single local worker for Data operations, content and night handoffs."""

import asyncio
import fcntl
from contextlib import suppress

from app.infrastructure.data_agents import load_data_context, pin_context
from app.infrastructure.data_content import DataContentBridge
from app.infrastructure.llm import LLMClient
from app.infrastructure.sqlite_store import SqliteKnowledgeStore
from app.memory.skills import prepare_platform_context
from app.memory.night import run_night
from app.negotiation.graph import run_negotiation
from data.growth_data.errors import require
from data.growth_data.service import Principal
from data.growth_data.storage import dumps, fingerprint, many, now, one


class _ScopedBudget:
    """Reserve the paid call under the same lock as its Data lease check."""
    def __init__(self,service,store,*,operation_id=None,job_id=None,night_day=None):
        self.service,self.store=service,store
        self.operation_id,self.job_id,self.night_day=operation_id,job_id,night_day

    def llm_calls_used(self,run_id):
        return self.store.llm_calls_used(run_id)

    def reserve_llm_call(self,run_id,call_id,limit):
        with self.service.store.connect(write=True) as c:
            if self.operation_id:
                op=one(c,'SELECT * FROM operations WHERE run_id=? AND operation_id=?',(run_id,self.operation_id))
                require(op and op['status']=='running' and op['claimed_by']=='native_orchestrator' and op['lease_until'] and op['lease_until']>=now(),'LEASE_EXPIRED','Operation không còn quyền gọi model')
            if self.job_id:
                job=one(c,'SELECT * FROM content_jobs WHERE run_id=? AND job_id=?',(run_id,self.job_id))
                latest=one(c,'SELECT job_id FROM content_jobs WHERE run_id=? AND proposal_id=? ORDER BY attempt DESC LIMIT 1',(run_id,job['proposal_id'])) if job else None
                require(job and latest and latest['job_id']==self.job_id and job['status'] in {'queued','running'} and job['lease_until'] and job['lease_until']>=now(),'LEASE_EXPIRED','Content job không còn quyền gọi model')
            if self.night_day is not None:
                handoff=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(run_id,self.night_day))
                require(handoff and handoff['status']=='running' and handoff['lease_until'] and handoff['lease_until']>=now(),'HANDOFF_TERMINAL','Handoff không còn quyền gọi model')
            return self.store._change_tx(c,run_id,'reserve_llm_call',run_id,call_id,limit)


class DataWorker:
    def __init__(self, service, settings, *, llm_factory=None, content_factory=None):
        self.service, self.settings = service, settings
        self.store=SqliteKnowledgeStore(service.store)
        self.service.knowledge_callbacks=self.store
        self.service.calibration_provider=self._calibration
        self.service.live_call_limit=settings.max_live_calls_per_session
        self.llm_factory=llm_factory
        self.content_factory=content_factory
        self.task=None
        self.lock_file=None
        self.stopping=False

    def _calibration(self, run_id, shop_id, day):
        with self.service.store.connect() as c:
            shop=self.service.entity(c,'shops',run_id,'shop_id',shop_id)
        record=self.store.get((run_id,'calibration',shop['category']),shop['category'])
        if not record or not record.samples: return None
        through=max(sample.target_day for sample in record.samples)
        if through>=day: return None
        value=record.value
        return {'version':f'calibration:{record.version}','as_of_day':through,'points':len(record.samples),
                'factor':value.factor,'q_low':value.q_low,'q_high':value.q_high}

    async def start(self):
        self.lock_file=(self.service.home/'native-worker.lock').open('a+')
        try: fcntl.flock(self.lock_file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close();self.lock_file=None
            raise RuntimeError('native worker already running for this database')
        await asyncio.to_thread(self._recover)
        self.task=asyncio.create_task(self._loop())

    async def close(self):
        self.stopping=True
        if self.task:
            with suppress(asyncio.CancelledError): await self.task
        if self.lock_file:
            fcntl.flock(self.lock_file,fcntl.LOCK_UN);self.lock_file.close();self.lock_file=None

    def _recover(self):
        with self.service.store.connect(write=True) as c:
            runs=[row['run_id'] for row in many(c,"SELECT DISTINCT run_id FROM reflection_receipts WHERE status='reserved'")]
            # A sweeper may already have failed an expired operation before worker startup.
            # The command receipt binds each negotiation to its exact native operation.
            orphans=many(c,"""SELECT n.* FROM negotiations n
                JOIN runs r ON r.run_id=n.run_id
                JOIN idempotency_records i ON i.run_scope=n.run_id AND i.principal_id='native_orchestrator'
                    AND i.path='native/negotiation' AND json_extract(i.response_json,'$.negotiation_id')=n.negotiation_id
                JOIN operations o ON o.run_id=n.run_id AND o.day=n.day AND i.key=o.operation_id||':'||n.shop_id
                WHERE n.status='running' AND json_extract(r.config_json,'$.driver.agent_version')='native'
                    AND o.claimed_by='native_orchestrator' AND (o.kind='start_day' OR o.kind LIKE 'renegotiate:%')
                    AND (o.status='running' OR (o.status='failed' AND o.error_code='LEASE_EXPIRED_RESULT_UNKNOWN'))""")
            for neg in orphans:
                receipt={'expected_version':neg['version'],'status':'failed','final_proposal_id':None,'rounds':neg['platform_rounds'],'reason_vi':'Tác vụ agent bị gián đoạn','referee_action':None}
                c.execute("UPDATE negotiations SET status='failed',final_proposal_id=NULL,terminal_receipt_json=?,terminal_hash=?,version=version+1,updated_at=? WHERE run_id=? AND negotiation_id=? AND status='running'",(dumps(receipt),fingerprint(receipt),now(),neg['run_id'],neg['negotiation_id']))
                self.service.event(c,neg['run_id'],neg['day'],'negotiation_finished','orchestrator',neg['shop_id'],{'negotiation_id':neg['negotiation_id'],'kind':neg['kind'],'status':'failed','rounds':neg['platform_rounds'],'source':'unknown'},text='Thương lượng bị gián đoạn')
            c.execute("UPDATE operations SET status='failed',error_code='WORKER_RESTART_OUTCOME_UNKNOWN',lease_until=NULL,version=version+1 WHERE status='running' AND claimed_by='native_orchestrator' AND (kind='start_day' OR kind LIKE 'renegotiate:%') AND run_id IN (SELECT run_id FROM runs WHERE json_extract(config_json,'$.driver.agent_version')='native')")
        for run in runs: self.store.recover_reserved_reflections(run)

    def _llm(self, run_id, settings, *, operation_id=None, job_id=None, night_day=None):
        budget=_ScopedBudget(self.service,self.store,operation_id=operation_id,job_id=job_id,night_day=night_day)
        if self.llm_factory: return self.llm_factory(run_id,settings,budget)
        from app.infrastructure.replay import ReplayCache
        path=self.service.home/'replay'/f'{run_id}.json'
        try: cache=ReplayCache.open(path) if path.is_file() else None
        except (OSError,ValueError): cache=None
        return LLMClient(settings,store=budget,run_id=run_id,replay_cache=cache)

    async def _loop(self):
        while not self.stopping:
            with self.service.store.connect() as c:
                op=one(c,"SELECT * FROM operations WHERE status='queued' AND (kind='start_day' OR kind LIKE 'renegotiate:%') ORDER BY created_at LIMIT 1")
                job=one(c,"SELECT * FROM content_jobs WHERE status IN ('queued','running') AND provider='assigned_worker' ORDER BY CASE shop_id WHEN 'D' THEN 0 ELSE 1 END,created_at LIMIT 1")
                night=one(c,"SELECT * FROM learning_handoffs WHERE status='pending' ORDER BY created_at LIMIT 1")
            try:
                if op: await self._with_heartbeat('operation',op,asyncio.to_thread(self._operation,op))
                elif job: await self._content(job)
                elif night: await self._with_heartbeat('night',night,asyncio.to_thread(self._night,night))
                else: await asyncio.sleep(.25)
            except asyncio.CancelledError: raise
            except Exception:
                # The terminal failure is stored by each workflow; do not retry unknown paid work.
                await asyncio.sleep(.25)

    async def _with_heartbeat(self, kind, row, work):
        task=asyncio.create_task(work)
        try:
            while not task.done():
                done,_=await asyncio.wait({task},timeout=20)
                if not done: await asyncio.to_thread(self._heartbeat,kind,row)
            return await task
        finally:
            if not task.done():
                # Do not release the process lock while its provider thread can write.
                with suppress(Exception,asyncio.CancelledError): await asyncio.shield(task)

    def _heartbeat(self, kind, row):
        s=self.service;r=row['run_id']
        with s.store.connect(write=True) as c:
            if kind=='operation':
                current=s.entity(c,'operations',r,'operation_id',row['operation_id'])
                if current['status']=='running' and current['claimed_by']=='native_orchestrator':
                    s.operation_result(c,Principal('native_orchestrator','orchestrator',None,(r,),('*',)),r,current['operation_id'],{'expected_version':current['version'],'status':'running'})
            else:
                h=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(r,row['day']))
                if h and h['status']=='running':
                    c.execute('UPDATE learning_handoffs SET lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND day=?',(s.expires(60),now(),r,row['day']))

    def _operation(self, op):
        s=self.service;r=op['run_id'];principal=Principal('native_orchestrator','orchestrator',None,(r,),('*',))
        active_neg=None
        try:
            with s.store.connect(write=True) as c:
                op=s.operation_claim(c,principal,r,op['operation_id'],{'expected_version':op['version']})
                run=s.run(c,principal,r)
                source_card=op['result'].get('source_card_id') if op['result'] else None
                shops=[run['demo_shop_id']] if source_card else [run['demo_shop_id']]+[x for x in 'ABCDE' if x!=run['demo_shop_id']]
                if not source_card:
                    eligibility={shop:s.eligibility(c,r,shop) for shop in shops}
                    market=s.market_summary(c,r,run)
                    s.event(c,r,run['current_day'],'opportunity','platform_agent',run['demo_shop_id'],
                            {'chosen':[shop for shop in shops if eligibility[shop]['eligible']],
                             'excluded':[{'shop_id':shop,'reason_codes':eligibility[shop]['reason_codes']} for shop in shops if not eligibility[shop]['eligible']],
                             'keyword':market['keyword'],'growth_7d_pct':market['growth_7d_pct'],'source':'simulation'},text='Đã tìm cơ hội từ dữ liệu thị trường')
            for shop in shops:
                with s.store.connect() as c:
                    run=s.run(c,principal,r)
                    eligible=s.eligibility(c,r,shop)['eligible']
                    runtime=s.entity(c,'shop_runtime',r,'shop_id',shop)
                    prior=one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id=? AND status='completed' ORDER BY end_day DESC LIMIT 1",(r,shop))
                    active=one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,shop))
                if run['memory_enabled'] and not source_card:
                    from app.domain.policies import PREF_ASK_THRESHOLD
                    prefs=self.store.list((r,'preferences',shop))
                    askable=next((p for p in prefs if p.observation_count>=PREF_ASK_THRESHOLD and (p.status=='candidate' or (p.status=='declined' and p.declined_until is not None and run['current_day']>=p.declined_until))),None)
                    if askable:
                        with s.store.connect(write=True) as c:
                            rules,version=s.rules(c,r,shop)
                            if askable.field!='voucher_max_pct' or int(askable.value)<=rules['voucher_max_pct']:
                                q=s.question(c,principal,r,shop,{'external_pref_id':askable.pref_id,'field':askable.field,'value':askable.value,'text_vi':f"Lần sau áp dụng sở thích: {askable.value}?",'based_on_rules_version':version})
                                if active and not one(c,"SELECT card_id FROM cards WHERE run_id=? AND shop_id=? AND status='pending'",(r,shop)):
                                    s.make_card(c,r,shop,run['current_day'],question=q)
                                    if shop!=run['demo_shop_id']: s.auto_card(c,r,shop)
                if not source_card and not eligible: continue
                body={'day':run['current_day'],'kind':'renew' if prior else 'propose','expected_shop_version':runtime['version'],
                      'source_card_id':source_card,'owner_note_vi':op['result'].get('owner_note_vi') if op['result'] else None}
                neg=s.command(principal,r,'native/negotiation',f"{op['operation_id']}:{shop}",body,lambda c:s.new_negotiation(c,principal,r,shop,body))
                active_neg=neg['negotiation_id']
                brief=run['brief']
                if shop!=run['demo_shop_id']:
                    brief={**brief,'brief_id':brief['brief_id']+':sim:'+shop,'shop_id':shop}
                    with s.store.connect(write=True) as c:
                        s.event(c,r,run['current_day'],'simulated_brief','simulated_seller',shop,{'brief_id':brief['brief_id'],'brief_version':brief['version'],'source':'simulation'},text='Mục tiêu mô phỏng đã được ghi nhận')
                scoped=self.settings.model_copy(update={'seed':run['seed'],'demo_shop':shop,'llm_mode':run['mode'] if shop==run['demo_shop_id'] else 'offline'})
                context=load_data_context(s,self.settings,r,shop,negotiation_id=neg['negotiation_id'],operation_id=op['operation_id'],brief=brief,llm=self._llm(r,scoped,operation_id=op['operation_id']))
                pinned=prepare_platform_context(context,shop,run['current_day'],body['kind'],neg['negotiation_id'])
                pin_context(s,r,neg['negotiation_id'],pinned,context.log)
                result=run_negotiation(context,shop,run['current_day'],body['kind'],body['owner_note_vi'],negotiation_id=neg['negotiation_id'],platform_context=pinned)
                with s.store.connect(write=True) as c:
                    context.log._fence(c,r)
                    current=s.entity(c,'negotiations',r,'negotiation_id',neg['negotiation_id'])
                    success=result.status in {'agreed','warning_only'}
                    final={'expected_version':current['version'],'status':'agreed' if success else 'failed',
                           'final_proposal_id':context.log.last_proposal if success else None,
                           'rounds':current['platform_rounds'],'reason_vi':result.warning_vi or '',
                           'referee_action':context.log.referee_action}
                    s.finalize_negotiation(c,principal,r,neg['negotiation_id'],final)
                    if success:
                        proposal=s.entity(c,'proposals',r,'proposal_id',final['final_proposal_id'])
                        s.present(c,principal,r,proposal['proposal_id'],proposal['version'])
                        if shop!=run['demo_shop_id']:
                            seller=Principal('native_simulated_seller','simulated_seller',None,(r,),(shop,))
                            current=s.entity(c,'proposals',r,'proposal_id',proposal['proposal_id'])
                            decision=s.decision(c,seller,r,{'target_type':'proposal','target_id':current['proposal_id'],'target_version':current['version'],'action':'approve'})
                            if current['package']['content_refresh']:
                                s.content_create(c,principal,r,shop,{'proposal_id':current['proposal_id'],'product_id':current['product_id']})
                            else:
                                _,versions=s.evaluation(c,r,shop,current['package'])
                                s.apply(c,principal,r,{'proposal_id':current['proposal_id'],'approval_decision_id':decision['decision_id'],'expected_inventory_version':versions['inventory_version'],'expected_rules_version':versions['rules_version']})
                    active_neg=None
            with s.store.connect(write=True) as c:
                current=s.entity(c,'operations',r,'operation_id',op['operation_id'])
                s.operation_result(c,principal,r,op['operation_id'],{'expected_version':current['version'],'status':'succeeded'})
        except Exception:
            with s.store.connect(write=True) as c:
                current=s.entity(c,'operations',r,'operation_id',op['operation_id'])
                if active_neg:
                    neg=s.entity(c,'negotiations',r,'negotiation_id',active_neg)
                    if neg['status']=='running':
                        s.finalize_negotiation(c,principal,r,active_neg,{'expected_version':neg['version'],'status':'failed','final_proposal_id':None,'rounds':neg['platform_rounds'],'reason_vi':'Tác vụ agent chưa hoàn tất','referee_action':None})
                if current['status']=='running' and current['claimed_by']==principal.principal_id:
                    c.execute("UPDATE operations SET status='failed',error_code='NATIVE_OPERATION_FAILED',lease_until=NULL,version=version+1,updated_at=? WHERE run_id=? AND operation_id=?",(now(),r,op['operation_id']))

    async def _content(self, job):
        from app.content.service import ContentService
        with self.service.store.connect() as c:
            run=self.service.entity(c,'runs',job['run_id'],'run_id',job['run_id'])
        background=job['shop_id']!=run['demo_shop_id']
        settings=self.settings.model_copy(update={'seed':run['seed'],'demo_shop':job['shop_id'],'llm_mode':'offline' if background else run['mode'],'media_mode':'offline' if background else self.settings.media_mode})
        worker=(self.content_factory or ContentService)(DataContentBridge(self.service),settings,self._llm(job['run_id'],settings,job_id=job['job_id']))
        try: await worker.process_job(job['run_id'],job['job_id'])
        finally: await worker.close()
        if background:
            r=job['run_id'];s=self.service
            with s.store.connect(write=True) as c:
                current=s.entity(c,'content_jobs',r,'job_id',job['job_id'])
                content=s.entity(c,'content_versions',r,'content_id',current['output_content_ids'][0])
                if current['status'] not in {'succeeded','failed','timed_out'} or content['status']!='validated': return
                seller=Principal('native_simulated_seller','simulated_seller',None,(r,),(job['shop_id'],))
                ready=next((x for x in content['cover_options'] if x['status'] in {'done','cached'} and x.get('asset_id')),None) if current['status']=='succeeded' else None
                decision=s.decision(c,seller,r,{'target_type':'content','target_id':content['content_id'],'target_version':content['version'],'action':'approve' if ready else 'reject','cover_option':ready['option'] if ready else None})
                if ready:
                    orchestrator=Principal('native_orchestrator','orchestrator',None,(r,),(job['shop_id'],))
                    s.publish(c,orchestrator,r,content['content_id'],{'approval_decision_id':decision['decision_id'],'expected_active_content_id':s.product(c,r,job['shop_id'])['active_content_id'],'skip_video':True})

    def publish_night(self, publication, *, expected_revision, expected_cursor):
        s=self.service;r=publication.run_id;day=publication.day
        with s.store.connect(write=True) as c:
            h=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(r,day))
            require(h and h['settlement_cursor']==publication.through_seq and h['summary_shop_id']==publication.shop_id,'HANDOFF_TERMINAL','Handoff không khớp publication')
            if h['status']=='completed':
                commit=self.store.commit_night_tx(c,publication,expected_revision=expected_revision,expected_cursor=expected_cursor)
                require(h['receipt_hash']==commit.publication_hash,'HANDOFF_TERMINAL','Receipt publication không khớp')
                return commit
            require(h['status']=='running' and h['lease_until'] and h['lease_until']>=now(),'HANDOFF_TERMINAL','Handoff không còn nhận publication')
            commit=self.store.commit_night_tx(c,publication,expected_revision=expected_revision,expected_cursor=expected_cursor)
            summary=commit.summary.model_dump(mode='json');summary['memory_md_path']=summary['memory_md_path'] or ''
            c.execute("UPDATE learning_handoffs SET status='completed',night_summary_json=?,receipt_id=?,receipt_hash=?,lease_until=NULL,version=version+1,updated_at=? WHERE run_id=? AND day=?",(dumps(summary),f'night:{day}',commit.publication_hash,now(),r,day))
            c.execute("UPDATE runs SET phase='day_closed',version=version+1 WHERE run_id=?",(r,))
            s.event(c,r,day,'memory_write','learning_worker',publication.shop_id,{'receipt_id':f'night:{day}','revision':commit.knowledge.store.revision,'source':commit.source},visibility='shop_private',text='Đã cập nhật bộ nhớ có bằng chứng')
            for version in commit.versions:
                bundle=version.bundle
                s.event(c,r,day,'skill_published','learning_worker',publication.shop_id,{'receipt_id':f'night:{day}','skill_id':bundle.skill.skill_id,'version':bundle.version,'artifact_hash':bundle.artifact_hash,'effective_from_day':bundle.effective_from_day,'source':commit.source},visibility='shop_private',text='Đã lưu phiên bản kỹ năng')
            s.event(c,r,day,'night_summary','learning_worker',publication.shop_id,{'summary':summary,'status':'completed','source':commit.source},visibility='shop_private',text='Đã cập nhật bộ nhớ')
            s.finish_night_tx(c,r,day)
            return commit

    def _night(self, handoff):
        s=self.service;r=handoff['run_id'];day=handoff['day']
        try:
            with s.store.connect(write=True) as c:
                h=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(r,day))
                require(h and h['status']=='pending','HANDOFF_TERMINAL','Handoff không còn chờ')
                c.execute("UPDATE learning_handoffs SET status='running',lease_until=?,version=version+1 WHERE run_id=? AND day=?",(s.expires(60),r,day))
                run=s.entity(c,'runs',r,'run_id',r)
            scoped=self.settings.model_copy(update={'seed':run['seed'],'demo_shop':run['demo_shop_id'],'llm_mode':run['mode']})
            context=load_data_context(s,self.settings,r,run['demo_shop_id'],llm=self._llm(r,scoped,night_day=day))
            context.settled_days.add(day)
            run_night(context,day,through_seq=handoff['settlement_cursor'],publish=self.publish_night)
        except Exception:
            with s.store.connect(write=True) as c:
                h=one(c,'SELECT * FROM learning_handoffs WHERE run_id=? AND day=?',(r,day))
                if h and h['status']=='running':
                    c.execute("UPDATE learning_handoffs SET status='failed',error_code='LEARNING_FAILED_OR_UNKNOWN',lease_until=NULL,version=version+1 WHERE run_id=? AND day=?",(r,day))
                    s.finish_night_tx(c,r,day)
