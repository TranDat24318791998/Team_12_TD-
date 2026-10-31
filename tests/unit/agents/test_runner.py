import json
from langchain_core.messages import HumanMessage, ToolMessage
from app.agents.runner import run_agent
from app.agents.tools import BoundTool, EmptyArgs
from app.domain.models.content import ContentText
from app.domain.models.tools import ContentContext
from app.domain.models.learning import ContentMemoryView
from tests.fakes.llm import FakeLLM, call


def context(style):
    return ContentContext(shop_id='D', title='Quạt mini', description='Sạc USB', attributes=['sạc USB'],
        images=[], fact_source_id='seed:shop:D', memory=ContentMemoryView(confirmed_style_notes=style,
        rules_version=2, preference_ids=['opaque1']), feedback_history=[], card_id='card1', brief_version=1, draft_version=1)


def test_native_tool_response_changes_the_final_decision():
    def execute(style):
        def finish(messages):
            result = json.loads(next(x.content for x in messages if isinstance(x, ToolMessage)))
            title = 'Quạt nền sáng' if result['memory']['confirmed_style_notes'] else 'Quạt mini'
            return [call('finish_content', {'title':title, 'description':'Sạc USB', 'checks':[]}, 'final')]
        model = FakeLLM([[call('get_content_context', {}, 'read1')], finish])
        tool = BoundTool(EmptyArgs, lambda _: context(style), ContentContext)
        result = run_agent('content', llm=model, tools={'get_content_context': tool}, messages=[HumanMessage(content='Viết nội dung')],
            output_schema=ContentText, fallback=lambda _: ContentText(title='fallback',description='Sạc USB',checks=[]),
            emit=lambda *_: None, run_name='run:content')
        assert result.source == 'fixture'
        assert isinstance(model.requests[1][0][-1], ToolMessage)
        assert model.requests[1][0][-1].tool_call_id == 'read1'
        return result.value.title
    assert execute([]) == 'Quạt mini'
    assert execute(['ảnh nền sáng']) == 'Quạt nền sáng'


def test_denied_tool_never_executes_and_fallback_is_labeled():
    seen=[]
    model=FakeLLM([[call('get_shop_private_context', {}, 'x')]])
    evil=BoundTool(EmptyArgs, lambda _: seen.append('leaked'), ContentContext, 'shop_private')
    result=run_agent('content',llm=model,tools={'get_shop_private_context':evil},messages=[],output_schema=ContentText,
        fallback=lambda _:ContentText(title='offline',description='',checks=[]),emit=lambda *_:None,run_name='x')
    assert seen == [] and result.source == 'offline'


def test_duplicate_batch_prevents_partial_execution():
    seen=[]
    model=FakeLLM([[call('get_content_context', {}, 'same'),call('get_content_context', {}, 'same')]])
    bound=BoundTool(EmptyArgs,lambda _:seen.append(1) or context([]),ContentContext)
    result=run_agent('content',llm=model,tools={'get_content_context':bound},messages=[],output_schema=ContentText,
        fallback=lambda _:ContentText(title='offline',description='',checks=[]),emit=lambda *_:None,run_name='x')
    assert not seen and result.error_code == 'invalid_call_id'


def test_strict_schema_has_no_defaults_or_optional_object_keys():
    from app.agents.runner import _schema
    from app.domain.models.negotiation import PlatformTurn
    schema=_schema('finish_platform',PlatformTurn)['function']['parameters']
    def visit(node):
        if isinstance(node,dict):
            assert 'default' not in node
            if node.get('type')=='object':
                assert node.get('additionalProperties') is False
                assert set(node.get('required',[]))==set(node.get('properties',{}))
            for child in node.values(): visit(child)
        elif isinstance(node,list):
            for child in node: visit(child)
    visit(schema)


def test_model_cannot_inject_scope_arguments():
    seen=[]
    model=FakeLLM([[call('get_content_context',{'shop_id':'A'},'read')]])
    tool=BoundTool(EmptyArgs,lambda _:seen.append(1) or context([]),ContentContext)
    result=run_agent('content',llm=model,tools={'get_content_context':tool},messages=[],output_schema=ContentText,
        fallback=lambda _:ContentText(title='offline',description='',checks=[]),emit=lambda *_:None,run_name='x')
    assert not seen and result.source=='offline'


def test_max_three_calls_then_terminal_or_offline():
    model=FakeLLM([[call('get_content_context',{},'one')], [call('get_content_context',{},'two')],
                   [call('get_content_context',{},'three')]])
    tool=BoundTool(EmptyArgs,lambda _:context([]),ContentContext)
    result=run_agent('content',llm=model,tools={'get_content_context':tool},messages=[],output_schema=ContentText,
        fallback=lambda _:ContentText(title='offline',description='',checks=[]),emit=lambda *_:None,run_name='x')
    assert len(model.requests)==3 and model.requests[-1][1]['tool_choice']=='finish_content'
    assert model.remaining_calls==61 and result.source=='offline'
