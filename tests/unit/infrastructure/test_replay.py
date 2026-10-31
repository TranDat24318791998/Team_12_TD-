import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.domain.models.learning import ReplayManifest
from app.infrastructure.replay import ReplayCache, ReplayMiss, request_hash
from app.infrastructure.llm import LLMClient, LLMUnavailable
from app.core.settings import Settings


def context(run,neg):
    return {'role':'platform','shop_id':'D','model_id':'model','config_hash':'a'*64,
            'memory_enabled':True,'bindings':[{'kind':'run','token':'RUN','value':run},
                {'kind':'negotiation','token':'NEG','value':neg}]}


def test_replay_rebinds_typed_identifiers_and_never_uses_budget(tmp_path):
    manifest=ReplayManifest(schema_version='self-improve.v1',source_run_id='r1',shop_id='D',config_hash='a'*64)
    cache=ReplayCache(manifest,tmp_path/'replay.json')
    first=context('r1','n1')
    messages=[HumanMessage(content=json.dumps({'run_id':'r1','negotiation_id':'n1','voucher_pct':5}))]
    response=AIMessage(content='',tool_calls=[{'name':'finish_platform','args':{'negotiation_id':'n1'},'id':'provider-id','type':'tool_call'}])
    cache.record_valid(context=first,messages=messages,tools=[],tool_choice='auto',parallel_tool_calls=True,response=response)
    second=context('r2','n2')
    next_messages=[HumanMessage(content=json.dumps({'run_id':'r2','negotiation_id':'n2','voucher_pct':5}))]
    settings=Settings(_env_file=None,llm_mode='replay',llm_model='model')
    llm=LLMClient(settings,replay_cache=ReplayCache.open(tmp_path/'replay.json'))
    replay=llm.invoke_tools(next_messages,tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='r2',replay_context=second)
    assert llm.last_source=='replay' and replay.tool_calls[0]['args']['negotiation_id']=='n2'
    assert llm.remaining_calls==64
    changed=[HumanMessage(content=json.dumps({'run_id':'r2','negotiation_id':'n2','voucher_pct':6}))]
    with pytest.raises(LLMUnavailable,match='REPLAY_MISS'):
        llm.invoke_tools(changed,tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='r2',replay_context=second)


def test_unbound_id_or_opaque_id_is_a_miss():
    ctx=context('r1','n1')
    with pytest.raises(ReplayMiss):
        request_hash(context=ctx,messages=[HumanMessage(content='Run r1')],tools=[],tool_choice='auto',parallel_tool_calls=True)
    with pytest.raises(ReplayMiss):
        request_hash(context=ctx,messages=[HumanMessage(content=json.dumps({'card_id':'c1'}))],tools=[],tool_choice='auto',parallel_tool_calls=True)


def test_replay_key_tracks_skill_memory_and_tool_call_order():
    def messages(neg,call_id):
        return [HumanMessage(content=json.dumps({'negotiation_id':neg})),
            AIMessage(content='',tool_calls=[{'name':'read_memory','args':{},'id':call_id,'type':'tool_call'}]),
            ToolMessage(content=json.dumps({'negotiation_id':neg}),name='read_memory',tool_call_id=call_id)]
    one=context('r1','n1') | {'skill_semantics':{'base_hash':'b'*64,'version':1}}
    two=context('r2','n2') | {'skill_semantics':{'base_hash':'b'*64,'version':1}}
    args={'tools':[],'tool_choice':'auto','parallel_tool_calls':True}
    expected=request_hash(context=one,messages=messages('n1','provider-a'),**args)
    assert request_hash(context=two,messages=messages('n2','provider-b'),**args)==expected
    assert request_hash(context=two | {'memory_enabled':False},messages=messages('n2','provider-b'),**args)!=expected
    assert request_hash(context=two | {'skill_semantics':{'base_hash':'b'*64,'version':2}},messages=messages('n2','provider-b'),**args)!=expected
    assert request_hash(context=two | {'model_id':'other'},messages=messages('n2','provider-b'),**args)!=expected


def test_binding_collisions_fail_closed():
    from app.infrastructure.replay import SemanticBindings
    binding=SemanticBindings('r')
    binding.add('negotiation','n1',('D',1,1))
    with pytest.raises(ReplayMiss,match='AMBIGUOUS_BINDING'):
        binding.add('negotiation','n2',('D',1,1))
