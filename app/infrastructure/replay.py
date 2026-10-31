"""Scoped model replay with explicitly supplied backend identity bindings."""

import json
from hashlib import sha256
from pathlib import Path
from langchain_core.messages import AIMessage
from app.domain.models.learning import ReplayBinding, ReplayEntry, ReplayManifest
from app.memory.skills import canonical_bytes

_ID_FIELDS = {'run_id':'run','negotiation_id':'negotiation','card_id':'card',
    'prediction_id':'prediction','fact_id':'fact','lesson_id':'lesson','pref_id':'preference',
    'preference_id':'preference','turn_id':'turn','tool_call_id':'tool_call','brief_id':'brief'}
_LIST_FIELDS = {'valid_negotiation_ids':'negotiation','evidence':'negotiation',
    'evidence_fact_ids':'fact','preference_ids':'preference','evidence_refs':'turn'}


class ReplayMiss(ValueError):
    pass


def _binding_maps(bindings):
    forward, reverse = {}, {}
    for raw in bindings:
        b = raw if isinstance(raw,ReplayBinding) else ReplayBinding.model_validate(raw)
        key = (b.kind,b.value); token = (b.kind,b.token)
        if key in forward and forward[key] != b.token or token in reverse and reverse[token] != b.value:
            raise ReplayMiss('AMBIGUOUS_BINDING')
        forward[key] = b.token; reverse[token] = b.value
    return forward,reverse


def _map(value, mapping, *, restore=False, field=None):
    if isinstance(value,list):
        kind = _LIST_FIELDS.get(field)
        return [_identifier(x,kind,mapping) if kind and isinstance(x,str) else _map(x,mapping,restore=restore) for x in value]
    if isinstance(value,dict):
        result = {}
        for key,item in value.items():
            if key == 'id' and 'name' in value and 'args' in value and isinstance(item,str):
                result[key] = _identifier(item,'tool_call',mapping)
            elif key == 'id' and 'version' in value and isinstance(item,str):
                matches = [replacement for (kind,original),replacement in mapping.items() if original == item]
                if len(matches) != 1: raise ReplayMiss('AMBIGUOUS_OR_MISSING_BINDING')
                result[key] = matches[0]
            elif key in _ID_FIELDS and isinstance(item,str):
                result[key] = _identifier(item,_ID_FIELDS[key],mapping)
            else:
                result[key] = _map(item,mapping,restore=restore,field=key)
        if not restore and 'artifact_hash' in result and isinstance(result.get('skill'),dict):
            result['artifact_hash'] = sha256(canonical_bytes(result['skill'])).hexdigest()
        return result
    if isinstance(value,str) and field in ('content',):
        try:
            parsed = json.loads(value)
        except (ValueError,TypeError):
            if any(ident and ident in value for _,ident in mapping):
                raise ReplayMiss('OPAQUE_DYNAMIC_ID')
            return value
        return json.dumps(_map(parsed,mapping,restore=restore),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return value


def _identifier(value, kind, mapping):
    try:
        return mapping[(kind,value)]
    except KeyError as exc:
        raise ReplayMiss('MISSING_BINDING') from exc


def _context_maps(context, bindings):
    forward, reverse = _binding_maps(bindings)
    if context.get('brief_id'):
        forward[('brief',context['brief_id'])] = 'BRIEF'
        reverse[('brief','BRIEF')] = context['brief_id']
    return forward,reverse


def request_hash(*, context, messages, tools, tool_choice, parallel_tool_calls):
    bindings = list(context.get('bindings',[]))
    for mi, message in enumerate(messages):
        for ci, call in enumerate(getattr(message,'tool_calls',[]) or []):
            bindings.append(ReplayBinding(kind='tool_call',token=f'TOOL:{mi}:{ci}',value=call['id']))
    forward,_ = _context_maps(context,bindings)
    normalized=[]
    for message in messages:
        entry={'type':message.type,'content':message.content}
        if getattr(message,'tool_call_id',None): entry['tool_call_id']=message.tool_call_id
        if getattr(message,'name',None): entry['name']=message.name
        if getattr(message,'tool_calls',None): entry['tool_calls']=message.tool_calls
        normalized.append(_map(entry,forward))
    envelope={'role':context['role'],'shop_id':context['shop_id'],'model_id':context['model_id'],
        'model_parameters':context.get('model_parameters',{}),'tools':tools,'tool_choice':tool_choice,
        'parallel_tool_calls':parallel_tool_calls,'base_hash':context.get('base_hash'),
        'skill_semantics':_map(context.get('skill_semantics'),forward),'memory_enabled':context['memory_enabled'],
        'messages':normalized}
    return sha256(canonical_bytes(envelope)).hexdigest()


class SemanticBindings:
    """Backend constructs identity tokens; model text never supplies a binding."""
    def __init__(self, run_id):
        self.bindings = [ReplayBinding(kind='run',token='RUN',value=run_id)]

    def add(self, kind, value, semantic_identity):
        token = kind + ':' + sha256(canonical_bytes(semantic_identity)).hexdigest()
        proposed = ReplayBinding(kind=kind,token=token,value=value)
        _binding_maps([*self.bindings,proposed])
        if proposed not in self.bindings:
            self.bindings.append(proposed)
        return token

    def values(self):
        return [item.model_dump(mode='json') for item in self.bindings]


def build_replay_context(session, *, role, shop_id, negotiation_id=None, turns=(),
                         platform_context=None, model_id=None):
    """Bind replay identities from the authoritative Data rows and frozen DTOs."""
    from app.memory.base import compose_base_text
    from app.memory.evidence import build_skill_facts
    from app.memory.prompts import LEARNING_SYSTEM
    from app.negotiation.prompts import PLATFORM_SYSTEM, SHOP_SYSTEM, REFEREE_SYSTEM
    from app.agents.content import CONTENT_SYSTEM
    from data.growth_data.storage import many, one
    if role not in ('platform','shop','referee','content','learning') or shop_id not in session.states:
        raise ReplayMiss('REPLAY_SCOPE_MISMATCH')
    source = getattr(session.memory,'source',None)
    if source is None or not hasattr(source,'service') or source.shop_id != shop_id:
        raise ReplayMiss('REPLAY_SOURCE_UNAVAILABLE')
    service=source.service; run_id=session.run_id; day=session.day
    builder=SemanticBindings(run_id)
    neg_tokens={}; card_tokens={}
    with service.store.connect() as c:
        run=service.entity(c,'runs',run_id,'run_id',run_id)
        config_hash=sha256(canonical_bytes([run['initial_snapshot_hash'],run['config'],run['seed'],run['simulation_days'],run['demo_shop_id']])).hexdigest()
        rows=many(c,'SELECT * FROM negotiations WHERE run_id=? AND shop_id=? ORDER BY day,rowid',(run_id,shop_id))
        attempts={}
        for row in rows:
            attempts[row['day']]=attempts.get(row['day'],0)+1
            neg_tokens[row['negotiation_id']]=builder.add('negotiation',row['negotiation_id'],
                [shop_id,row['day'],attempts[row['day']]])
        cards=many(c,'SELECT * FROM cards WHERE run_id=? AND shop_id=? ORDER BY day,rowid',(run_id,shop_id))
        for card in cards:
            if not card['proposal_id']: continue
            proposal=one(c,'SELECT negotiation_id FROM proposals WHERE run_id=? AND proposal_id=?',(run_id,card['proposal_id']))
            neg=proposal and neg_tokens.get(proposal['negotiation_id'])
            if neg:
                card_tokens[card['card_id']]=builder.add('card',card['card_id'],[neg,card['version']])
        for prediction in many(c,'SELECT * FROM daily_predictions WHERE run_id=? AND shop_id=? ORDER BY day',(run_id,shop_id)):
            payload=prediction['payload']
            builder.add('prediction',prediction['prediction_id'],[shop_id,prediction['day'],payload['effective_state_hash']])
    if negotiation_id and negotiation_id not in neg_tokens:
        raise ReplayMiss('MISSING_NEGOTIATION_BINDING')
    if session.memory.enabled:
        category=session.states[shop_id].public.category
        for lesson in session.store.list((run_id,'lessons','strategy')) + session.store.list((run_id,'lessons',category)):
            builder.add('lesson',lesson.lesson_id,[lesson.scope,' '.join(lesson.text_vi.casefold().split())])
        for pref in session.store.list((run_id,'preferences',shop_id)):
            builder.add('preference',pref.pref_id,[shop_id,pref.field,pref.value])
        cutoff=platform_context.through_seq if platform_context else (session.log.last_seq(run_id) if hasattr(session.log,'last_seq') else None)
        facts=build_skill_facts(source.events(cutoff),run_id=run_id,shop_id=shop_id,category=category,day=day,
                               through_seq=cutoff if cutoff is not None else 0)
        frozen=getattr(session.memory,'_learning_snapshot',None)
        if frozen:
            facts=list({fact.fact_id:fact for fact in [*facts,*frozen.skill_facts]}.values())
        for fact in facts:
            card,neg=card_tokens.get(fact.card_id),neg_tokens.get(fact.negotiation_id)
            if card and neg:
                builder.add('fact',fact.fact_id,[fact.kind,card,neg,fact.package_applied_seq,fact.support_seq])
    for index,turn in enumerate(turns):
        if not negotiation_id: raise ReplayMiss('MISSING_NEGOTIATION_BINDING')
        builder.add('turn',turn.turn_id,[neg_tokens[negotiation_id],turn.actor,turn.round,index])
    base_text = (platform_context.base_text if platform_context else
                 compose_base_text('platform_offer',PLATFORM_SYSTEM) if role=='platform' else
                 compose_base_text('shop_negotiate',SHOP_SYSTEM) if role=='shop' else
                 compose_base_text('content_brief',CONTENT_SYSTEM) if role=='content' else
                 LEARNING_SYSTEM if role=='learning' else REFEREE_SYSTEM)
    selected_model=model_id or (session.settings.llm_model_reflect if role=='learning' else session.settings.llm_model)
    if not selected_model: raise ReplayMiss('MODEL_ID_REQUIRED')
    return {'role':role,'shop_id':shop_id,'model_id':selected_model,'config_hash':config_hash,
        'memory_enabled':session.memory.enabled,'bindings':builder.values(),
        'brief_id':session.brief.brief_id if session.brief else None,
        'base_hash':sha256(base_text.encode('utf-8')).hexdigest(),
        'skill_semantics':platform_context.memory.skill.bundle.skill.model_dump(mode='json') if platform_context else None,
        'model_parameters':{}}


class ReplayCache:
    def __init__(self, manifest: ReplayManifest, path=None):
        self.manifest = manifest.model_copy(deep=True)
        self.path = Path(path) if path else None

    @classmethod
    def open(cls, path):
        path = Path(path)
        return cls(ReplayManifest.model_validate_json(path.read_text(encoding='utf-8')),path)

    def lookup(self, *, context, messages, tools, tool_choice, parallel_tool_calls):
        if context['shop_id'] != self.manifest.shop_id or context['config_hash'] != self.manifest.config_hash:
            raise ReplayMiss('REPLAY_SCOPE_MISMATCH')
        key=request_hash(context=context,messages=messages,tools=tools,tool_choice=tool_choice,
                         parallel_tool_calls=parallel_tool_calls)
        visibility='shop_private' if context['role']=='shop' else 'public'
        entry=next((e for e in self.manifest.entries if e.request_hash==key and e.role==context['role']
                    and e.shop_id==context['shop_id'] and e.visibility==visibility and e.model_id==context['model_id']),None)
        if entry is None: raise ReplayMiss('REPLAY_MISS')
        _,reverse = _context_maps(context,context.get('bindings',[]))
        payload=json.loads(entry.response_json)
        calls=[]
        for index,call in enumerate(payload.get('tool_calls',[])):
            call=dict(call)
            call['args']=_map(call.get('args',{}),reverse,restore=True)
            call['id']=f'replay-{context.get("step",0)}-{index}'
            calls.append(call)
        return AIMessage(content=_map(payload.get('content',''),reverse,restore=True,field='content'),tool_calls=calls,
                         invalid_tool_calls=payload.get('invalid_tool_calls',[]))

    def record_valid(self, *, context, messages, tools, tool_choice, parallel_tool_calls, response):
        if self.path is None: raise ReplayMiss('REPLAY_READ_ONLY')
        if context['shop_id'] != self.manifest.shop_id or context['config_hash'] != self.manifest.config_hash:
            raise ReplayMiss('REPLAY_SCOPE_MISMATCH')
        forward,_=_context_maps(context,context.get('bindings',[]))
        key=request_hash(context=context,messages=messages,tools=tools,tool_choice=tool_choice,
                         parallel_tool_calls=parallel_tool_calls)
        if not isinstance(response,AIMessage) or response.invalid_tool_calls or not response.tool_calls:
            raise ReplayMiss('INVALID_RESPONSE')
        calls=[]
        for call in response.tool_calls:
            calls.append({'name':call['name'],'args':_map(call['args'],forward),'id':'TOKEN','type':'tool_call'})
        body={'content':_map(response.content,forward,field='content'),'tool_calls':calls,'invalid_tool_calls':[]}
        entry=ReplayEntry(request_hash=key,role=context['role'],shop_id=context['shop_id'],
            visibility='shop_private' if context['role']=='shop' else 'public',model_id=context['model_id'],
            response_json=json.dumps(body,ensure_ascii=False,separators=(',',':')),bindings=context.get('bindings',[]))
        if not any(e.request_hash==key for e in self.manifest.entries):
            self.manifest.entries.append(entry)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            self.path.write_text(self.manifest.model_dump_json(indent=2),encoding='utf-8')
