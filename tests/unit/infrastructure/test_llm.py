import pytest
from langchain_core.messages import AIMessage
from app.core.settings import Settings
from app.infrastructure.llm import LLMClient, LLMUnavailable


def test_openai_transport_uses_bound_tools_and_shared_budget_without_network():
    calls=[]
    class FakeChat:
        def __init__(self,**kwargs): calls.append(('init',kwargs))
        def bind_tools(self,tools,**kwargs): calls.append(('bind',tools,kwargs)); return self
        def invoke(self,messages,config): calls.append(('invoke',messages,config)); return AIMessage(content='')
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test-key',llm_model='test-model',max_live_calls_per_session=2)
    llm=LLMClient(settings,model_factory=FakeChat)
    llm.invoke_tools([],tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='case')
    assert calls[0][1]['timeout']==8 and calls[0][1]['max_retries']==0
    assert calls[1][2]['strict'] and calls[1][2]['parallel_tool_calls']
    assert llm.remaining_calls==1


def test_provider_failure_disables_further_live_calls():
    calls=[]
    class BrokenChat:
        def __init__(self,**kwargs): pass
        def bind_tools(self,tools,**kwargs): return self
        def invoke(self,messages,config): calls.append(1); raise TimeoutError('provider')
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test-key',llm_model='test-model',max_live_calls_per_session=2)
    llm=LLMClient(settings,model_factory=BrokenChat)
    with pytest.raises(LLMUnavailable): llm.invoke_tools([],tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='case')
    with pytest.raises(LLMUnavailable): llm.invoke_tools([],tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='case')
    assert len(calls)==1 and llm.remaining_calls==1 and not llm.available


def test_durable_reservation_precedes_network_and_never_resends():
    from app.infrastructure.store import MemoryStore
    calls=[]
    class FakeChat:
        def __init__(self,**kwargs): pass
        def bind_tools(self,tools,**kwargs): return self
        def invoke(self,messages,config):
            calls.append('sent')
            raise TimeoutError('unknown outcome')
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test',llm_model='fake',max_live_calls_per_session=2)
    store=MemoryStore()
    first=LLMClient(settings,model_factory=FakeChat,store=store,run_id='r')
    with pytest.raises(LLMUnavailable):
        first.invoke_tools([],tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='n',call_id='n:0')
    reopened=LLMClient(settings,model_factory=FakeChat,store=store,run_id='r')
    with pytest.raises(LLMUnavailable):
        reopened.invoke_tools([],tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='n',call_id='n:0')
    assert calls==['sent'] and reopened.remaining_calls==1


def test_bad_schema_does_not_reserve_budget():
    from app.infrastructure.store import MemoryStore
    class BrokenBind:
        def __init__(self,**kwargs): pass
        def bind_tools(self,tools,**kwargs): raise ValueError('bad schema')
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test',llm_model='fake',max_live_calls_per_session=2)
    store=MemoryStore(); llm=LLMClient(settings,model_factory=BrokenBind,store=store,run_id='r')
    with pytest.raises(LLMUnavailable,match='schema_invalid'):
        llm.invoke_tools([],tools=[],tool_choice='auto',parallel_tool_calls=True,run_name='n',call_id='n:0')
    assert store.llm_calls_used('r')==0


def test_terra_uses_responses_xhigh_and_preserves_a_tool_roundtrip():
    import json
    import httpx
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_openai import ChatOpenAI

    requests=[]
    def handler(request):
        payload=json.loads(request.content)
        requests.append((request.url.path,payload))
        number=len(requests)
        output={'type':'function_call','id':f'fc_{number}','call_id':f'call_{number}',
                'name':'read_shop' if number==1 else 'finish',
                'arguments':'{}' if number==1 else '{"ok":true}','status':'completed'}
        reasoning={'type':'reasoning','id':f'rs_{number}','summary':[]}
        return httpx.Response(200,json={'id':f'resp_{number}','object':'response','created_at':0,
            'status':'completed','model':'gpt-6.1-terra','output':[reasoning,output],
            'parallel_tool_calls':True,'tool_choice':'auto'})
    http_client=httpx.Client(transport=httpx.MockTransport(handler))
    init=[]
    def factory(**kwargs):
        init.append(kwargs)
        return ChatOpenAI(**kwargs,base_url='https://example.test/v1',http_client=http_client)
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test-key',llm_model='gpt-6.1-terra',
                      llm_reasoning_effort='xhigh',llm_timeout_seconds=120,max_live_calls_per_session=2)
    llm=LLMClient(settings,model_factory=factory)
    tools=[{'type':'function','function':{'name':'read_shop','description':'Read shop',
        'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}},
        {'type':'function','function':{'name':'finish','description':'Finish',
        'parameters':{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}}}]
    try:
        first=llm.invoke_tools([HumanMessage(content='Xin chào')],tools=tools,tool_choice='auto',parallel_tool_calls=True,run_name='test',call_id='one')
        assert first.tool_calls[0]['name']=='read_shop' and first.tool_calls[0]['id']=='call_1'
        second=llm.invoke_tools([HumanMessage(content='Xin chào'),first,ToolMessage(content='{"stock":30}',name='read_shop',tool_call_id='call_1')],tools=tools,tool_choice='finish',parallel_tool_calls=False,run_name='test',call_id='two')
        assert second.tool_calls[0]['name']=='finish' and second.tool_calls[0]['args']=={'ok':True}
        assert all(path=='/v1/responses' for path,_ in requests)
        assert all(payload['model']=='gpt-6.1-terra' and payload['reasoning']=={'effort':'xhigh'} for _,payload in requests)
        assert any(item.get('type')=='function_call' and item.get('call_id')=='call_1' for item in requests[1][1]['input'])
        assert any(item.get('type')=='function_call_output' and item.get('call_id')=='call_1' and item.get('output')=='{"stock":30}' for item in requests[1][1]['input'])
        assert any(item.get('type')=='reasoning' and item.get('id')=='rs_1' for item in requests[1][1]['input'])
        assert requests[1][1]['tool_choice']=={'type':'function','name':'finish'}
        assert all(item['timeout']==120 and item['max_retries']==0 and item['use_responses_api'] is True for item in init)
        assert llm.remaining_calls==0
    finally:
        http_client.close()


def test_reasoning_effort_is_included_in_replay_binding_without_cross_model_or_effort_reuse(tmp_path):
    from langchain_core.messages import HumanMessage
    from app.domain.models.learning import ReplayManifest
    from app.infrastructure.replay import ReplayCache
    context={'role':'platform','shop_id':'D','model_id':'gpt-6.1-terra','config_hash':'a'*64,
             'memory_enabled':True,'bindings':[],'model_parameters':{}}
    cache=ReplayCache(ReplayManifest(schema_version='self-improve.v1',source_run_id='r',shop_id='D',config_hash='a'*64),tmp_path/'replay.json')
    class Chat:
        def __init__(self,**kwargs): pass
        def bind_tools(self,*args,**kwargs): return self
        def invoke(self,*args,**kwargs): return AIMessage(content='',tool_calls=[{'name':'finish','args':{},'id':'t','type':'tool_call'}])
    options={'tools':[],'tool_choice':'auto','parallel_tool_calls':False,'run_name':'case','replay_context':context}
    messages=[HumanMessage(content='Cùng đầu vào')]
    live=LLMClient(Settings(_env_file=None,llm_mode='live',openai_api_key='test',llm_model='gpt-6.1-terra',llm_reasoning_effort='xhigh'),model_factory=Chat,replay_cache=cache)
    live.invoke_tools(messages,call_id='first',**options);live.confirm_replay('first')
    same=LLMClient(Settings(_env_file=None,llm_mode='replay',llm_model='gpt-6.1-terra',llm_reasoning_effort='xhigh'),replay_cache=cache)
    assert same.invoke_tools(messages,**options).tool_calls[0]['name']=='finish'
    for model,effort in [('gpt-6.1-terra','low'),('gpt-6-luna','xhigh')]:
        different=LLMClient(Settings(_env_file=None,llm_mode='replay',llm_model=model,llm_reasoning_effort=effort),replay_cache=cache)
        with pytest.raises(LLMUnavailable,match='REPLAY_MISS'):
            different.invoke_tools(messages,**options)


def test_terra_responses_selected_even_without_effort_or_for_model_override():
    from app.infrastructure.store import MemoryStore
    seen=[]
    class Chat:
        def __init__(self,**kwargs): seen.append(kwargs)
        def bind_tools(self,*args,**kwargs): return self
        def invoke(self,*args,**kwargs): return AIMessage(content='')
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test',llm_model='legacy-model',llm_reasoning_effort=None)
    llm=LLMClient(settings,model_factory=Chat,store=MemoryStore(),run_id='r')
    args={'tools':[],'tool_choice':'auto','parallel_tool_calls':False,'run_name':'case'}
    llm.invoke_tools([],call_id='legacy',**args)
    llm.invoke_tools([],model='gpt-6.1-terra',call_id='override',**args)
    assert 'use_responses_api' not in seen[0] and 'reasoning' not in seen[0] and 'reasoning_effort' not in seen[0]
    assert seen[1]['model']=='gpt-6.1-terra' and seen[1]['use_responses_api'] is True
    assert 'reasoning' not in seen[1] and seen[1]['timeout']==8


def test_terra_http_timeout_uses_one_durable_reservation_without_resending():
    import httpx
    from langchain_openai import ChatOpenAI
    from app.infrastructure.store import MemoryStore
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        raise httpx.ReadTimeout('simulated timeout',request=request)
    client=httpx.Client(transport=httpx.MockTransport(handler))
    def factory(**kwargs): return ChatOpenAI(**kwargs,base_url='https://example.test/v1',http_client=client)
    settings=Settings(_env_file=None,llm_mode='live',openai_api_key='test',llm_model='gpt-6.1-terra',llm_reasoning_effort='xhigh')
    store=MemoryStore()
    args={'tools':[],'tool_choice':'auto','parallel_tool_calls':False,'run_name':'case','call_id':'same-call'}
    try:
        first=LLMClient(settings,model_factory=factory,store=store,run_id='r')
        with pytest.raises(LLMUnavailable,match='provider_failed'): first.invoke_tools([],**args)
        second=LLMClient(settings,model_factory=factory,store=store,run_id='r')
        with pytest.raises(LLMUnavailable,match='budget_'): second.invoke_tools([],**args)
        assert calls==['/v1/responses'] and store.llm_calls_used('r')==1
    finally:
        client.close()
