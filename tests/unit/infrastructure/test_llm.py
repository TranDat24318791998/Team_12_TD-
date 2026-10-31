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
