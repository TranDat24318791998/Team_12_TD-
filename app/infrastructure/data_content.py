"""Short Data transactions for the approved content worker."""

import hashlib
import re

from app.domain.models.shops import FeeConfig, ShopPrivate, ShopPublic
from app.domain.privacy import leak_guard

from data.growth_data.errors import require
from data.growth_data.seed import world
from data.growth_data.service import Principal
from data.growth_data.storage import dumps, fingerprint, many, now, one, uid


class DataContentBridge:
    def __init__(self, service):
        self.service = service

    @staticmethod
    def principal(run_id, job_id):
        return Principal('native_content', 'content_worker', None, (run_id,), ('*',), (job_id,))

    def _job(self, c, run_id, job_id):
        s = self.service
        job = s.job_access(c, self.principal(run_id, job_id), run_id, job_id)
        current = one(c, 'SELECT job_id FROM content_jobs WHERE run_id=? AND proposal_id=? ORDER BY attempt DESC LIMIT 1', (run_id, job['proposal_id']))
        content = s.entity(c, 'content_versions', run_id, 'content_id', job['output_content_ids'][0])
        run = s.entity(c, 'runs', run_id, 'run_id', run_id)
        require(current and current['job_id'] == job_id and job['status'] in {'queued', 'running'} and content['status'] == 'draft' and run['phase'] not in {'complete', 'learning', 'day_closed'}, 'STALE_DRAFT', 'Job không còn được nhận kết quả')
        require(job['lease_until'] and job['lease_until'] >= now(), 'LEASE_EXPIRED', 'Lease content đã hết hạn')
        return job, content, run

    def _text_guard(self, c, run_id, shop_id, rules):
        """Use the same current Data-backed finance inputs as the native shop tools."""
        s=self.service
        public=ShopPublic.model_validate(s.public(c,run_id,shop_id))
        cost=s.current_cost(c,run_id,shop_id)
        private=ShopPrivate(owner_name=world()['shops'][shop_id]['private']['owner_name'],
                            unit_cost=cost['unit_cost_vnd']+cost['other_unit_cost_vnd'],rules=rules)
        fee,_=s.fee_config(c,run_id)
        fees=FeeConfig(fixed_pct=fee['rate_bps']/100,transaction_pct=0,tax_pct=0,per_order=fee['per_order'])
        def safe(text):
            if not isinstance(text,str):return False
            _,redacted=leak_guard(text,public,private,fees)
            return not redacted and s.safe_text(c,run_id,text)==text
        return safe

    @staticmethod
    def _safe_notes(notes, safe):
        # Keep independently safe guidance without reconstructing sensitive clauses.
        output=[]
        for note in notes:
            if not isinstance(note,str):continue
            parts=re.split(r'[;\r\n]+|(?<=[.!?])\s+',note)
            clean=[part.strip() for part in parts if part.strip() and safe(part.strip())]
            if clean:output.append(' '.join(clean))
        return output

    @staticmethod
    def _assert_safe_previous(previous, safe):
        for key in ('title','description'):
            require(safe(previous[key]),'PRIVATE_CONTENT','Nội dung cũ chứa thông tin riêng')
        for item in [*previous.get('images',[]),previous.get('video',{})]:
            for key in ('prompt','error','review_notes'):
                if item.get(key):require(safe(item[key]),'PRIVATE_CONTENT','Nội dung cũ chứa thông tin riêng')

    def snapshot(self, run_id, job_id):
        s = self.service
        with s.store.connect() as c:
            job, content, run = self._job(c, run_id, job_id)
            proposal = s.entity(c, 'proposals', run_id, 'proposal_id', job['proposal_id'])
            card, approval = s.content_approval(c,run_id,job)
            require(card and approval and proposal['status'] == 'accepted', 'APPROVAL_REQUIRED', 'Cần approval cho nội dung')
            approval = {key:approval[key] for key in ('decision_id','shop_id','target_type','target_id','target_version','action')}
            product = s.product(c, run_id, job['shop_id'])
            rules, rules_version = s.rules(c, run_id, job['shop_id'])
            safe=self._text_guard(c,run_id,job['shop_id'],rules)
            self._assert_safe_previous(job['brief']['previous_content'],safe)
            for key in ('title','description'):
                require(safe(content[key]),'PRIVATE_CONTENT','Nội dung cũ chứa thông tin riêng')
            job={**job,'feedback_history':self._safe_notes(job['feedback_history'],safe),
                 'style_notes':self._safe_notes(job['style_notes'],safe),
                 'brief':{**job['brief'],'confirmed_style':self._safe_notes(job['brief']['confirmed_style'],safe)}}
            content={**content,'feedback_history':self._safe_notes(content['feedback_history'],safe),
                     'style_notes':self._safe_notes(content['style_notes'],safe)}
            rules={'content_style_notes':self._safe_notes(rules['content_style_notes'],safe)}
            assets = [s.entity(c, 'assets', run_id, 'asset_id', aid) for aid in job['input_asset_ids']]
            from app.infrastructure.data_knowledge import DataKnowledgeSource
            from app.infrastructure.sqlite_store import SqliteKnowledgeStore
            references=DataKnowledgeSource(s,run_id,job['shop_id']).reference_documents(role='content',shop_id=job['shop_id'],day=run['current_day'])
            preferences=SqliteKnowledgeStore(s.store).list((run_id,'preferences',job['shop_id'])) if run['memory_enabled'] else []
            preference_ids=[x.pref_id for x in preferences if x.status=='confirmed' and x.field=='content_style']
            return {'job': job, 'content': content, 'proposal': proposal, 'card': card, 'approval': approval, 'brief': run['brief'], 'brief_version': run['brief_version'], 'product': product, 'rules': rules, 'rules_version': rules_version, 'assets': assets, 'provider_state': job['provider_state'], 'day': run['current_day'], 'references':references,'preference_ids':preference_ids}

    def heartbeat(self, run_id, job_id, expected_job_version):
        s = self.service
        with s.store.connect(write=True) as c:
            self._job(c, run_id, job_id)
            return s.content_result(c, self.principal(run_id, job_id), run_id, job_id, {'expected_job_version': expected_job_version, 'status': 'running'})

    def input_asset(self, run_id, job_id):
        s=self.service
        with s.store.connect() as c:
            job,_,_=self._job(c,run_id,job_id)
            row=one(c,"SELECT a.* FROM assets a JOIN asset_jobs j ON j.run_id=a.run_id AND j.asset_id=a.asset_id WHERE j.run_id=? AND j.job_id=? AND a.product_id=? AND a.origin='supplied' AND a.source_reference LIKE 'local_import:sha256:%' AND a.upload_status='ready' ORDER BY a.created_at LIMIT 1",(run_id,job_id,job['product_id']))
            if not row: return None
            path=s.object_path(row['object_key'])
            if not path.is_file() or path.stat().st_size!=row['size_bytes']: return None
            data=path.read_bytes()
            return {'asset_id':row['asset_id'],'bytes':data} if hashlib.sha256(data).hexdigest()==row['sha256'] else None

    def input_bytes(self, run_id, job_id):
        asset=self.input_asset(run_id,job_id)
        return asset['bytes'] if asset else None

    def validate_text(self, run_id, job_id, title, description):
        with self.service.store.connect() as c:
            job,_,_=self._job(c,run_id,job_id)
            return self.service.validate_content_text(c,run_id,job,title,description)

    def reserve_slot(self, run_id, job_id, slot, request_body):
        require(slot in {'A', 'B', 'C', 'video'}, 'SLOT_INVALID', 'Slot không hợp lệ', 422)
        s = self.service
        digest = fingerprint(request_body)
        with s.store.connect(write=True) as c:
            job, _, _ = self._job(c, run_id, job_id)
            state = job['provider_state']
            if slot in state:
                existing = state[slot]
                require(existing.get('request_hash') == digest, 'REQUEST_CONFLICT', 'Yêu cầu media đã thay đổi')
                return {**existing, 'can_submit': False}
            records = many(c, 'SELECT provider_state_json FROM content_jobs WHERE run_id=?', (run_id,))
            slots = [key for row in records for key in row['provider_state'] if key in {'A', 'B', 'C', 'video'}]
            used = sum(key == 'video' for key in slots) if slot == 'video' else sum(key != 'video' for key in slots)
            require(used < (3 if slot == 'video' else 9), 'MEDIA_BUDGET_EXHAUSTED', 'Đã hết lượt tạo media')
            entry = {'request_hash': digest, 'idempotency_key': uid('media'), 'status': 'reserved', 'request': request_body, 'remote_id': None, 'asset_id': None}
            state[slot] = entry
            c.execute('UPDATE content_jobs SET provider_state_json=?,updated_at=? WHERE run_id=? AND job_id=?', (dumps(state), now(), run_id, job_id))
            return {**entry, 'can_submit': True}

    def update_slot(self, run_id, job_id, slot, updates):
        require(slot in {'inputs', 'A', 'B', 'C', 'video'}, 'SLOT_INVALID', 'Slot không hợp lệ', 422)
        require(set(updates) <= {'status', 'remote_id', 'asset_id', 'source_asset_id', 'logo_asset_id', 'error', 'source', 'review_passed', 'review_notes', 'duration_seconds', 'media_text_vision_calls_reserved', 'media_text_vision_calls_completed'}, 'SLOT_INVALID', 'Trường media không hợp lệ', 422)
        s = self.service
        with s.store.connect(write=True) as c:
            job, _, _ = self._job(c, run_id, job_id)
            state = job['provider_state']
            require(slot == 'inputs' or slot in state, 'SLOT_REQUIRED', 'Chưa giữ lượt media')
            old = state.get(slot, {})
            require(old.get('status') not in {'done', 'failed', 'unknown', 'outcome_unknown'} or all(old.get(k) == v for k, v in updates.items()), 'SLOT_TERMINAL', 'Slot đã kết thúc')
            reserved=updates.get('media_text_vision_calls_reserved',old.get('media_text_vision_calls_reserved',0))
            completed=updates.get('media_text_vision_calls_completed',old.get('media_text_vision_calls_completed',0))
            require(type(reserved) is int and type(completed) is int and 0<=completed<=reserved<=3 and (slot=='video' or reserved==completed==0),'MEDIA_BUDGET_INVALID','Số lượt text/vision không hợp lệ',422)
            require(reserved>=old.get('media_text_vision_calls_reserved',0) and completed>=old.get('media_text_vision_calls_completed',0),'MEDIA_BUDGET_INVALID','Không thể giảm lượt đã ghi',422)
            state[slot] = {**old, **updates}
            c.execute('UPDATE content_jobs SET provider_state_json=?,updated_at=? WHERE run_id=? AND job_id=?', (dumps(state), now(), run_id, job_id))
            return state[slot]

    def import_asset(self, run_id, job_id, *, data, mime_type, kind):
        s = self.service
        principal = self.principal(run_id, job_id)
        with s.store.connect(write=True) as c:
            job, _, _ = self._job(c, run_id, job_id)
            result = s.upload_create(c, principal, run_id, {'product_id': job['product_id'], 'job_id': job_id, 'kind': kind, 'mime_type': mime_type, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        aid = result['asset_id']
        s.upload_bytes(principal, run_id, aid, data)
        with s.store.connect(write=True) as c:
            self._job(c, run_id, job_id)
            s.complete_upload(c, principal, run_id, aid, hashlib.sha256(data).hexdigest())
        return aid

    def complete(self, run_id, job_id, result):
        s = self.service
        with s.store.connect(write=True) as c:
            self._job(c, run_id, job_id)
            return s.content_result(c, self.principal(run_id, job_id), run_id, job_id, result)

    def emit(self, run_id, job_id, event_type, data):
        require(event_type in {'tool_called', 'tool_result', 'agent_completed'}, 'EVENT_INVALID', 'Sự kiện không hợp lệ', 422)
        safe = {key: data[key] for key in ('role', 'tool_name', 'tool_call_id', 'requested_by', 'status', 'source', 'error_code', 'invocation_id', 'record_refs') if key in data}
        s = self.service
        with s.store.connect(write=True) as c:
            job, _, run = self._job(c, run_id, job_id)
            return s.event(c, run_id, run['current_day'], event_type, 'content_worker', job['shop_id'], {**safe, 'job_id': job_id}, visibility='shop_private', text='Agent xử lý dữ liệu theo quyền')
