"""Scoped, cutoff-bound Knowledge inputs from Data's authoritative events."""

from dataclasses import dataclass
import hashlib
from types import SimpleNamespace

from app.domain.models.events import Event
from app.domain.models.learning import LearningEvidence, MemoryUpdateBatch, PublicEvidence, PublicOutcome
from app.domain.models.packages import Package
from app.domain.models.shops import ShopRules
from data.growth_data.storage import many, one
from data.growth_data.simulation import business_date


@dataclass(frozen=True)
class RulesState:
    rules: ShopRules
    version: int
    evidence_seqs: tuple[int, ...]


class DataKnowledgeSource:
    def __init__(self, service, run_id, shop_id):
        self.service, self.run_id, self.shop_id = service, run_id, shop_id
        self.session = None

    def rules_state(self, shop_id):
        if shop_id != self.shop_id:
            raise ValueError('shop scope mismatch')
        with self.service.store.connect() as c:
            rules, version = self.service.rules(c, self.run_id, shop_id)
            rows = many(c, "SELECT e.seq FROM events e JOIN shop_rules sr ON sr.run_id=e.run_id AND sr.confirmation_decision_id=json_extract(e.payload_json,'$.decision_id') WHERE e.run_id=? AND e.shop_id=? AND e.type='seller_decision' AND sr.shop_id=? ORDER BY e.seq", (self.run_id, shop_id, shop_id))
        return RulesState(ShopRules.model_validate(rules), version, tuple(row['seq'] for row in rows))

    def events(self, through_seq=None):
        from app.domain.privacy import leak_guard
        s, r, shop = self.service, self.run_id, self.shop_id
        with s.store.connect() as c:
            rows = many(c, 'SELECT * FROM events WHERE run_id=? AND shop_id=? AND seq<=? ORDER BY seq', (r, shop, through_seq if through_seq is not None else 2**63-1))
            out=[]
            for row in rows:
                kind, data = row['type'], row['payload']
                if kind not in {'platform_turn','shop_turn','negotiation_finished','card_sent','seller_decision','package_applied','auto_action','market_result','content_job'}:
                    continue
                if kind=='market_result' and row['visibility']!='platform_private':
                    continue
                allowed={'negotiation_id','proposal_id','card_id','campaign_id','decision_id','job_id','attempt','round','action','package','edited_package','status','kind','prediction_id','settlement_id','effective_day','feedback_vi','metrics','source'}
                data={key:value for key,value in data.items() if key in allowed}
                if kind=='content_job' and data.get('job_id'):
                    job=one(c,'SELECT proposal_id FROM content_jobs WHERE run_id=? AND job_id=?',(r,data['job_id']))
                    if job:
                        prop=one(c,'SELECT negotiation_id FROM proposals WHERE run_id=? AND proposal_id=?',(r,job['proposal_id']))
                        data['negotiation_id']=prop['negotiation_id'] if prop else None
                if data.get('campaign_id'):
                    campaign=one(c,'SELECT proposal_id FROM campaigns WHERE run_id=? AND campaign_id=?',(r,data['campaign_id']))
                    if campaign:
                        prop=one(c,'SELECT * FROM proposals WHERE run_id=? AND proposal_id=?',(r,campaign['proposal_id']))
                        if prop:
                            data['negotiation_id']=prop['negotiation_id']
                            card=one(c,'SELECT card_id FROM cards WHERE run_id=? AND proposal_id IN (?,?) ORDER BY rowid DESC LIMIT 1',(r,prop['proposal_id'],prop['parent_proposal_id']))
                            if card: data['card_id']=card['card_id']
                if kind=='market_result' and isinstance(data.get('metrics'),dict):
                    data['metrics']={key:data['metrics'].get(key) for key in ('orders','revenue','ads_spend','roas')}
                if self.session is None:
                    data.pop('feedback_vi',None)
                    text='Đã ghi sự kiện.'
                else:
                    state=self.session.states[shop]
                    text,_=leak_guard(s.safe_text(c,r,row['text_vi']),state.public,state.private,self.session.world.fees)
                    if data.get('feedback_vi'):
                        feedback,redacted=leak_guard(str(data['feedback_vi']),state.public,state.private,self.session.world.fees)
                        if redacted: data.pop('feedback_vi',None)
                        else: data['feedback_vi']=s.safe_text(c,r,feedback)
                actor={'orchestrator':'system','monitor':'system','simulator':'market','platform_agent':'platform','shop_agent':'shop','simulated_seller':'seller'}.get(row['actor_role'],row['actor_role'])
                out.append(Event(seq=row['seq'],run_id=r,day=row['day'],ts=row['simulated_at'],type=kind,actor=actor,shop_id=shop,text_vi=text,data=data))
            return out

    def freeze_evidence(self, *, day, after_seq, through_seq, knowledge_revision, existing_lessons):
        events=self.events(through_seq)
        selected=[e for e in events if after_seq < e.seq <= through_seq and e.day==day]
        ids=sorted({e.data['negotiation_id'] for e in selected if isinstance(e.data.get('negotiation_id'),str)})
        projected=[]
        for e in selected:
            try: package=Package.model_validate(e.data['package']) if e.data.get('package') else None
            except ValueError: package=None
            try: outcome=PublicOutcome.model_validate(e.data['metrics']) if e.type=='market_result' and e.data.get('metrics') else None
            except ValueError: outcome=None
            projected.append(PublicEvidence(seq=e.seq,type=e.type,negotiation_id=e.data.get('negotiation_id'),text_vi=e.text_vi,package=package,seller_action=e.data.get('action') if e.type=='seller_decision' else None,feedback_vi=e.data.get('feedback_vi') if e.type=='content_job' else None,outcome=outcome))
        return LearningEvidence(day=day,from_seq=after_seq+1,through_seq=through_seq,events=projected,existing_lessons=existing_lessons,valid_negotiation_ids=ids,knowledge_revision=knowledge_revision)

    def freeze_night(self, *, day, through_seq, after_seq, prior_history, prior_preferences, prior_calibration):
        from app.memory.night import _derive_calibration, _derive_history, _derive_preferences
        session=self.session
        if session is None:
            raise ValueError('execution context required')
        snapshot=self.freeze_evidence(day=day,after_seq=after_seq,through_seq=through_seq,knowledge_revision=session.knowledge_revision,existing_lessons=[])
        events=self.events(through_seq)
        with self.service.store.connect() as c:
            prediction=one(c,'SELECT * FROM daily_predictions WHERE run_id=? AND shop_id=? AND day=?',(self.run_id,self.shop_id,day))
            metric=one(c,'SELECT SUM(orders) AS orders FROM daily_metrics WHERE run_id=? AND shop_id=? AND day=?',(self.run_id,self.shop_id,day))
        if prediction and metric and metric['orders'] is not None:
            payload=prediction['payload']
            session.forecast_snapshots[(self.shop_id,day)]=SimpleNamespace(prediction_id=prediction['prediction_id'],raw_point=payload['raw_point'],issued_point=payload['issued_point'])
            session.states[self.shop_id].metrics[day]=SimpleNamespace(orders=metric['orders'])
        history=_derive_history(session,snapshot,self.shop_id,events)
        prefs=_derive_preferences(session,snapshot,self.shop_id,events)
        calibration,value,mape=_derive_calibration(session,day,self.shop_id,events)
        return events,MemoryUpdateBatch(day=day,through_seq=through_seq,history=history,preferences=prefs,calibration=calibration,lesson_ops=[],valid_negotiation_ids=snapshot.valid_negotiation_ids),{'factor':value.factor,'points':len(value.ratios),'mape_today':mape}

    def reference_documents(self, *, role, shop_id, day):
        if shop_id!=self.shop_id: raise ValueError('shop scope mismatch')
        from app.domain.models.tools import ReferenceDocument
        allowed={'selling_policy','ads_guide','fee_guide'} if role=='platform' else {'content_policy','product'} if role=='content' else set()
        with self.service.store.connect() as c:
            product=self.service.product(c,self.run_id,shop_id)
            release=one(c,'SELECT knowledge_release FROM run_policies WHERE run_id=?',(self.run_id,))['knowledge_release']
            rows=many(c,"SELECT * FROM knowledge_documents WHERE collection_scope='shared' AND index_status='ready' AND knowledge_release=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY document_id",(release,business_date(day),business_date(day)))
            result=[]
            for row in rows:
                if row['type'] not in allowed or (row['type']=='product' and row['document_id']!=f"product_{product['product_id']}"): continue
                path=self.service.object_path(row['source_object_key'])
                if not path.is_file(): continue
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=row['checksum']: continue
                result.append(ReferenceDocument(document_id=row['document_id'],document_version=row['document_version'],source_reference=row['source_object_key'],checksum=row['checksum'],is_simulated=bool(row['is_simulated']),text_vi=raw.decode('utf-8')[:1800]))
            return result
