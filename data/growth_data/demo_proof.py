"""Export and validate a read-only, D-scoped measured demo comparison."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError, model_validator
from .errors import Fault, require
from .models import Strict
from .storage import many, one

Id = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_.:-]+$')]
Hash = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
Day = Annotated[int, Field(ge=1, le=7)]
Text = Annotated[str, StringConstraints(max_length=5000)]
EVENT_TYPES = ('brief_confirmed','platform_turn','shop_turn','referee_review','seller_decision',
               'card_sent','negotiation_finished','package_applied','auto_action','market_result','skill_published',
               'skill_used','night_summary','content_job','content_applied')
_EVENT_TYPE = Literal['brief_confirmed','platform_turn','shop_turn','referee_review','seller_decision',
                      'card_sent','negotiation_finished','package_applied','auto_action','market_result','skill_published',
                      'skill_used','night_summary','content_job','content_applied']
_SOURCE = 'precomputed_offline_simulation'
_PRIVATE_TEXT = re.compile(r'(?:file://|/(?:Users|home|private|tmp|var)/|[A-Za-z]:\\\\|\bsk-[A-Za-z0-9_-]{12,}|\bprivate[_ -]sentinel\b|\b(?:api[_ -]?key|access[_ -]?token|password|credential|secret|private[_ -]?note)\s*[:=])',re.I)


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


class Brief(Strict):
    intent: Literal['increase_orders']
    goal_vi: Text
    allow_ads: bool
    ads_daily_cap: int | None
    content_refresh: bool
    duration_days: int
    version: int = Field(ge=1)
    shop_id: Literal['D']


class BriefRef(Strict):
    brief_id: Id
    event_seq: int = Field(ge=1)


class BriefRefs(Strict):
    on: BriefRef
    off: BriefRef


class Metric(Strict):
    key: Id
    label_vi: Text
    better: Literal['higher','lower']
    unit: Text
    on: int | float | None
    off: int | float | None


class Message(Strict):
    id: Id
    actor: Literal['platform_agent','shop_agent','seller','system']
    text_vi: Text
    event_seq: int = Field(ge=1)


class MemoryReference(Strict):
    run_id: Id
    source_day: Day
    event_seq: int = Field(ge=1)
    text_vi: Text
    record_id: Id
    record_version: int | None


class Branch(Strict):
    run_id: Id
    messages: list[Message] = Field(max_length=500)
    memory_used: list[MemoryReference] = Field(max_length=500)
    result_vi: Text


class ComparisonDay(Strict):
    day: Day
    request_vi: Text
    request_version: int = Field(ge=1)
    request_refs: BriefRefs
    situation_vi: Text
    takeaway_vi: Text
    on: Branch
    off: Branch


class ProofReport(Strict):
    seed: int
    days: Day
    shop_id: Literal['D']
    run_on: Id
    run_off: Id
    metrics: list[Metric] = Field(max_length=20)
    comparison_days: list[ComparisonDay] = Field(max_length=7)
    source: Literal['precomputed_offline_simulation']
    execution_profile: Literal['external']
    note_vi: Text
    status: Literal['ready']


class EvidenceEvent(Strict):
    run_id: Id
    seq: int = Field(ge=1)
    day: Day
    type: _EVENT_TYPE
    actor: Literal['platform_agent','shop_agent','seller','system']
    text_vi: Text


class Evidence(Strict):
    on: list[EvidenceEvent] = Field(max_length=10000)
    off: list[EvidenceEvent] = Field(max_length=10000)


class AssetSource(Strict):
    kind: Literal['imported_cached','simulated_placeholder','supplied']
    sha256: Hash


class ArtifactVersion(Strict):
    skill_id: Literal['platform_offer','platform_renew']
    version: int = Field(ge=1)
    effective_from_day: int = Field(ge=1,le=8)
    artifact_hash: Hash
    base_hash: Hash
    eval_level: Literal['static','deterministic','provider']


class SourceChecksums(Strict):
    input_snapshot_sha256: Hash
    config_sha256: Hash
    report_sha256: Hash
    on_evidence_sha256: Hash
    off_evidence_sha256: Hash


class Manifest(Strict):
    comparison_id: Id
    shop_id: Literal['D']
    run_on: Id
    run_off: Id
    seed: int
    days: Day
    source: Literal['precomputed_offline_simulation']
    provider_eval: Literal['not_run']
    brief: Brief
    brief_refs: BriefRefs
    data_schema_version: int = Field(ge=1)
    simulator_version: Id
    source_checksums: SourceChecksums
    input_assets: dict[Literal['on','off'],AssetSource]
    source_counts: dict[Literal['on','off'],dict[str,int]]
    skill_versions: dict[Literal['on','off'],list[ArtifactVersion]]
    artifact_sha256: Hash


class DemoProof(Strict):
    schema_version: Literal['demo-proof.v1']
    manifest: Manifest
    report: ProofReport
    evidence: Evidence

    @model_validator(mode='after')
    def consistent(self):
        m, r = self.manifest, self.report
        if (m.run_on,m.run_off,m.seed,m.days,m.shop_id) != (r.run_on,r.run_off,r.seed,r.days,r.shop_id) or m.run_on == m.run_off:
            raise ValueError('PROOF_SCOPE_MISMATCH')
        if set(m.input_assets) != {'on','off'} or set(m.source_counts) != {'on','off'} or set(m.skill_versions) != {'on','off'}:
            raise ValueError('PROOF_BRANCHES_MISSING')
        if len({row.day for row in r.comparison_days}) != len(r.comparison_days):
            raise ValueError('DUPLICATE_COMPARISON_DAY')
        for row in r.comparison_days:
            if (row.day > m.days or row.request_refs != m.brief_refs or row.request_version != m.brief.version
                    or row.request_vi != m.brief.goal_vi
                    or row.on.run_id != m.run_on or row.off.run_id != m.run_off or row.off.memory_used):
                raise ValueError('PROOF_DAY_SCOPE_MISMATCH')
            if any(ref.run_id != m.run_on or ref.source_day >= row.day for ref in row.on.memory_used):
                raise ValueError('PROOF_MEMORY_SCOPE_MISMATCH')
        for name,run_id in (('on',m.run_on),('off',m.run_off)):
            events=getattr(self.evidence,name)
            if any(e.run_id != run_id or e.day > m.days for e in events) or len({e.seq for e in events}) != len(events):
                raise ValueError('PROOF_EVIDENCE_SCOPE_MISMATCH')
            by_seq={event.seq:event for event in events}
            brief_event=by_seq.get(getattr(m.brief_refs,name).event_seq)
            if not brief_event or brief_event.type != 'brief_confirmed':
                raise ValueError('PROOF_BRIEF_EVIDENCE_MISSING')
            for row in r.comparison_days:
                branch=getattr(row,name)
                if any(msg.event_seq not in by_seq or by_seq[msg.event_seq].day != row.day or
                       by_seq[msg.event_seq].actor != msg.actor or by_seq[msg.event_seq].text_vi != msg.text_vi or
                       msg.id != f'{run_id}:{msg.event_seq}' for msg in branch.messages):
                    raise ValueError('PROOF_MESSAGE_EVIDENCE_MISSING')
                if any(ref.event_seq not in by_seq or by_seq[ref.event_seq].day != ref.source_day for ref in branch.memory_used):
                    raise ValueError('PROOF_MEMORY_EVIDENCE_MISSING')
        if (m.input_assets['on'] != m.input_assets['off'] or m.skill_versions['off'] or
                any(set(m.source_counts[arm]) != {'offline'} or m.source_counts[arm]['offline'] < 1 for arm in ('on','off')) or
                any(v.eval_level == 'provider' for v in m.skill_versions['on'])):
            raise ValueError('PROOF_PROVENANCE_MISMATCH')
        checks = m.source_checksums
        if (checks.report_sha256 != _hash(r.model_dump(mode='json')) or
                checks.on_evidence_sha256 != _hash([e.model_dump(mode='json') for e in self.evidence.on]) or
                checks.off_evidence_sha256 != _hash([e.model_dump(mode='json') for e in self.evidence.off])):
            raise ValueError('PROOF_SOURCE_CHECKSUM_MISMATCH')
        payload=self.model_dump(mode='json')
        payload['manifest'].pop('artifact_sha256')
        if m.artifact_sha256 != _hash(payload):
            raise ValueError('PROOF_ARTIFACT_HASH_MISMATCH')
        if _PRIVATE_TEXT.search(json.dumps(payload,ensure_ascii=False)):
            raise ValueError('PROOF_UNSAFE_TEXT')
        return self


def _safe_text(service,c,run_id,text):
    text=service.safe_text(c,run_id,str(text or ''))
    return 'Nội dung đã được ẩn.' if _PRIVATE_TEXT.search(text) else text[:5000]


def _project_events(service,c,run_id,days,cutoffs):
    rows=many(c,"SELECT * FROM events WHERE run_id=? AND shop_id='D' AND day BETWEEN 1 AND ? ORDER BY seq",(run_id,days))
    result=[]
    actors={'platform_agent':'platform_agent','shop_agent':'shop_agent','seller':'seller','simulated_seller':'seller'}
    for row in rows:
        if (row['seq'] > cutoffs[row['day']] or row['type'] not in EVENT_TYPES or
                (row['type']=='market_result' and row['visibility']!='platform_private')):
            continue
        text = _safe_text(service,c,run_id,row['text_vi']) if row['visibility'] in ('shared','platform_private') else 'Đã ghi nhận sự kiện của shop D.'
        result.append({'run_id':run_id,'seq':row['seq'],'day':row['day'],'type':row['type'],
            'actor':actors.get(row['actor_role'],'system'),'text_vi':text})
    return result


def _source_asset(c,source_home,run_id):
    row=one(c,"SELECT a.sha256,a.object_key,a.source_reference FROM assets a JOIN content_versions cv ON cv.run_id=a.run_id AND cv.cover_asset_id=a.asset_id JOIN products p ON p.run_id=cv.run_id AND p.product_id=cv.product_id WHERE a.run_id=? AND p.shop_id='D' AND cv.content_version=1",(run_id,))
    require(row is not None,'PROOF_INVALID','Thiếu checksum ảnh nguồn')
    root=(Path(source_home)/'objects').resolve(); path=(root/row['object_key']).resolve()
    require(path.is_relative_to(root) and path.is_file(),'PROOF_INVALID','Thiếu ảnh nguồn')
    require(hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'PROOF_INVALID','Checksum ảnh nguồn không khớp')
    reference=row['source_reference'] or ''
    kind='imported_cached' if reference.startswith('local_import:') else 'simulated_placeholder' if 'placeholder' in reference else 'supplied'
    return {'kind':kind,'sha256':row['sha256']}


def export_demo_proof(source_home, comparison_id):
    """Read a completed native D pair without opening a writable source connection."""
    from .evidence import proof
    from .service import DataService, Principal
    path=(Path(source_home)/'growth.db').resolve()
    if not path.is_file(): raise Fault('PROOF_NOT_READY','Chưa có database đối chứng',404)
    service=DataService.__new__(DataService)
    principal=Principal('demo_proof_export','data_admin',None,('*',),('D',))
    try:
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as c:
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA query_only=ON')
            c.execute('BEGIN')
            group=one(c,'SELECT * FROM comparison_groups WHERE group_id=?',(comparison_id,))
            require(group is not None,'PROOF_NOT_READY','Không có nhóm đối chứng',404)
            on,off=service.validate_pair(c,principal,group['run_on_id'],group['run_off_id'])
            require(on['demo_shop_id']==off['demo_shop_id']=='D','PROOF_SCOPE_DENIED','Báo cáo chỉ hỗ trợ shop D',403)
            require(on['phase']==off['phase']=='complete' and on['mode']==off['mode']=='offline'
                and on['execution_profile']==off['execution_profile']=='external'
                and on['config'].get('source')==off['config'].get('source')=='simulation'
                and on['config'].get('driver',{}).get('agent_version')==off['config'].get('driver',{}).get('agent_version')=='native',
                'PROOF_INVALID','Cần hai run native offline đã hoàn tất')
            cutoffs={}
            for name,run in (('on',on),('off',off)):
                rid=run['run_id']; horizon=run['simulation_days']
                handoffs=many(c,'SELECT * FROM learning_handoffs WHERE run_id=? ORDER BY day',(rid,))
                require(len(handoffs)==horizon and all(h['day']==i+1 and h['summary_shop_id']=='D' and
                    h['status']==('completed' if name=='on' else 'skipped') for i,h in enumerate(handoffs)),
                    'PROOF_INVALID','Thiếu handoff theo cutoff')
                cutoffs[name]={h['day']:h['settlement_cursor'] for h in handoffs}
                count=c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=? AND shop_id='D' AND status='committed' AND day BETWEEN 1 AND ?",(rid,horizon)).fetchone()[0]
                require(count==horizon,'PROOF_INVALID','Thiếu settlement đã hoàn tất')
                commits=c.execute('SELECT COUNT(*) FROM night_commits WHERE run_id=?',(rid,)).fetchone()[0]
                reservations=c.execute('SELECT COUNT(*) FROM llm_call_reservations WHERE run_id=?',(rid,)).fetchone()[0]
                require(commits==(horizon if name=='on' else 0) and reservations==0,'PROOF_INVALID','Nguồn học hoặc budget không phải offline')
                if name=='on':
                    reflections=many(c,"SELECT payload_json FROM reflection_receipts WHERE run_id=?",(rid,))
                    require(len(reflections)==horizon and all(row['payload']['status']=='completed' and row['payload']['source']=='offline' for row in reflections),'PROOF_INVALID','Nguồn reflection không phải offline')
                else:
                    require(c.execute('SELECT COUNT(*) FROM knowledge_records WHERE run_id=?',(rid,)).fetchone()[0]==0,'PROOF_INVALID','Nhánh OFF chứa dữ liệu đã học')
            report=proof(service,c,principal,on['run_id'],comparison_id)
            require(bool(report['comparison_days']),'PROOF_INVALID','Thiếu mục tiêu và hội thoại đã xác nhận')
            fields=('intent','goal_vi','allow_ads','ads_daily_cap','content_refresh','duration_days','version','shop_id')
            require(all(on['brief'].get(k)==off['brief'].get(k) for k in fields),'PROOF_INVALID','Mục tiêu hai run không khớp')
            brief={k:on['brief'][k] for k in fields}
            brief['goal_vi']=_safe_text(service,c,on['run_id'],brief['goal_vi'])
            refs={}
            for name,run in (('on',on),('off',off)):
                event=one(c,"SELECT seq FROM events WHERE run_id=? AND shop_id='D' AND type='brief_confirmed' AND json_extract(payload_json,'$.brief_id')=? ORDER BY seq LIMIT 1",(run['run_id'],run['brief']['brief_id']))
                require(event is not None,'PROOF_INVALID','Thiếu sự kiện xác nhận mục tiêu')
                refs[name]={'brief_id':run['brief']['brief_id'],'event_seq':event['seq']}
            for day in report['comparison_days']:
                day['request_vi']=brief['goal_vi']
                for name,run in (('on',on),('off',off)):
                    branch=day[name]; messages=[]
                    for message in branch['messages']:
                        event=one(c,"SELECT * FROM events WHERE run_id=? AND shop_id='D' AND day=? AND seq=?",(run['run_id'],day['day'],message['event_seq']))
                        if (not event or event['seq']>cutoffs[name][day['day']] or event['visibility'] != 'shared'
                                or event['type'] not in ('platform_turn','shop_turn','seller_decision','referee_review')): continue
                        messages.append({**message,'text_vi':_safe_text(service,c,run['run_id'],event['text_vi'])})
                    branch['messages']=messages
                    reads=many(c,"SELECT payload_json FROM events WHERE run_id=? AND shop_id='D' AND day=? AND seq<=? AND type='tool_result' AND json_extract(payload_json,'$.tool_name')='read_memory' AND json_extract(payload_json,'$.status')='ok'",(run['run_id'],day['day'],cutoffs[name][day['day']]))
                    recorded={(ref.get('id'),ref.get('version')) for row in reads for ref in row['payload'].get('record_refs',[]) if isinstance(ref,dict)}
                    memory=[]
                    for ref in branch['memory_used']:
                        source_event=one(c,"SELECT day,visibility FROM events WHERE run_id=? AND shop_id='D' AND seq=?",(run['run_id'],ref['event_seq']))
                        if (not source_event or source_event['day']!=ref['source_day'] or
                                ref['event_seq']>cutoffs[name].get(ref['source_day'],0) or
                                (ref['record_id'],ref['record_version']) not in recorded):
                            continue
                        record=one(c,"SELECT compartment FROM knowledge_records WHERE run_id=? AND record_key=? AND scope IN ('D','strategy',?) ORDER BY compartment LIMIT 1",(run['run_id'],ref['record_id'],service.entity(c,'shops',run['run_id'],'shop_id','D')['category']))
                        if source_event['visibility']=='shop_private' and (not record or record['compartment']!='lessons'):
                            ref['text_vi']='Đã ghi nhận sự kiện của shop D.'
                        else:
                            ref['text_vi']=_safe_text(service,c,run['run_id'],ref['text_vi'])
                        memory.append(ref)
                    branch['memory_used']=memory
            report['comparison_days']=[row for row in report['comparison_days'] if row['on']['messages'] and row['off']['messages']]
            require(bool(report['comparison_days']),'PROOF_INVALID','Thiếu hội thoại trong cutoff đã chốt')
            report.update(source=_SOURCE,status='ready')
            evidence={'on':_project_events(service,c,on['run_id'],on['simulation_days'],cutoffs['on']),
                      'off':_project_events(service,c,off['run_id'],off['simulation_days'],cutoffs['off'])}
            versions={}; counts={}; assets={}
            for name,run in (('on',on),('off',off)):
                rid=run['run_id']; assets[name]=_source_asset(c,source_home,rid)
                versions[name]=[]
                for row in many(c,"SELECT payload_json FROM skill_versions WHERE run_id=? AND shop_id='D' ORDER BY skill_id,version",(rid,)):
                    v=row['payload']; b=v['bundle']
                    versions[name].append({'skill_id':b['skill']['skill_id'],'version':b['version'],
                        'effective_from_day':b['effective_from_day'],'artifact_hash':b['artifact_hash'],
                        'base_hash':b['skill']['base_hash'],'eval_level':v['eval_level']})
                counts[name]={row['source']:row['n'] for row in c.execute("SELECT COALESCE(json_extract(payload_json,'$.source'),'unknown') source,COUNT(*) n FROM events WHERE run_id=? AND shop_id='D' AND type='agent_completed' GROUP BY source",(rid,))}
                require(set(counts[name])=={'offline'} and counts[name]['offline']>0,'PROOF_INVALID','Nguồn agent không phải offline')
            manifest={'comparison_id':comparison_id,'shop_id':'D','run_on':on['run_id'],'run_off':off['run_id'],
                'seed':on['seed'],'days':on['simulation_days'],'source':_SOURCE,'provider_eval':'not_run',
                'brief':brief,'brief_refs':refs,'data_schema_version':c.execute('PRAGMA user_version').fetchone()[0],
                'simulator_version':on['simulator_version'],'input_assets':assets,'source_counts':counts,'skill_versions':versions,
                'source_checksums':{'input_snapshot_sha256':on['initial_snapshot_hash'],
                    'config_sha256':_hash([on['initial_snapshot_hash'],on['config']]),'report_sha256':_hash(report),
                    'on_evidence_sha256':_hash(evidence['on']),'off_evidence_sha256':_hash(evidence['off'])}}
            payload={'schema_version':'demo-proof.v1','manifest':manifest,'report':report,'evidence':evidence}
            manifest['artifact_sha256']=_hash(payload)
            return DemoProof.model_validate(payload).model_dump(mode='json')
    except (sqlite3.Error,ValueError,KeyError,TypeError,OSError) as exc:
        raise Fault('PROOF_INVALID','Không thể xác thực báo cáo mô phỏng',409) from exc


def load_demo_proof(home):
    """Load the single configured artifact; never accept a request-selected path."""
    path=Path(home)/'demo-proof.json'
    try:
        if not path.is_file(): raise Fault('PROOF_NOT_READY','Chưa có báo cáo mô phỏng đã chạy',404)
        if path.stat().st_size > 5_000_000: raise ValueError('PROOF_TOO_LARGE')
        return DemoProof.model_validate_json(path.read_bytes()).model_dump(mode='json')
    except (ValueError,ValidationError,OSError) as exc:
        raise Fault('PROOF_INVALID','Báo cáo mô phỏng không hợp lệ',409) from exc
