"""Content role exposed to the media teammate; no provider job or publish side effects."""

from dataclasses import replace
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.runner import run_agent
from app.agents.tools import bind_role_tools
from app.agents.tools import BoundTool, EmptyArgs
from app.domain.models.content import ContentText
from app.domain.models.tools import ContentContext
from app.memory.base import compose_base_text


CONTENT_SYSTEM = ('Bạn là agent nội dung. Gọi get_content_context để đọc facts và style đã xác nhận. '
    'Chỉ dùng từ có trong listing, thuộc tính đã xác minh hoặc style; không thêm thương hiệu, bảo hành '
    'hay thông số chưa có. Trả title, description, checks bằng finish_content.')


def generate_content_from_context(context: ContentContext, llm, emit, invocation_id):
    """Run the native role against a Data-authorized immutable snapshot."""
    tools = {'get_content_context': BoundTool(EmptyArgs, lambda _: context, ContentContext)}
    def fallback(dispatch):
        facts = dispatch('get_content_context', {})
        return ContentText(title=facts.title, description=facts.description,
                           checks=[f'Nguồn: {facts.fact_source_id}'])
    result = run_agent('content', llm=llm, tools=tools,
        messages=[SystemMessage(content=compose_base_text('content_brief', CONTENT_SYSTEM)), HumanMessage(content='Viết nội dung cho bản đã được duyệt.')],
        output_schema=ContentText, fallback=fallback, emit=emit, run_name=invocation_id)
    checks = [f'Nguồn: {context.fact_source_id}']
    checks.extend(f'Phong cách đã xác nhận: {style}' for style in context.memory.confirmed_style_notes)
    return replace(result, value=result.value.model_copy(update={'checks': checks}))


def generate_content(session, shop_id, *, card_id, draft_version, feedback_history=()):
    """Return AgentRun[ContentText]; the media service still validates and owns jobs."""
    invocation_id=f'{session.run_id}:content:{card_id}:{draft_version}'
    tools=bind_role_tools(session,'content',shop_id,card_id=card_id,draft_version=draft_version,
                          feedback_history=feedback_history,invocation_id=invocation_id)
    def fallback(dispatch):
        context=dispatch('get_content_context',{})
        checks=[f'Nguồn: {context.fact_source_id}']
        checks.extend(f'Phong cách đã xác nhận: {style}' for style in context.memory.confirmed_style_notes)
        return ContentText(title=context.title,description=context.description,checks=checks)
    def emit(event_type,data):
        safe={key:value for key,value in data.items() if key in
              {'role','tool_name','tool_call_id','requested_by','status','source','error_code','invocation_id','record_refs'}}
        session.log.add(session.run_id,session.day,event_type,'content',shop_id,'Content xử lý dữ liệu theo quyền.',safe)
    result=run_agent('content',llm=session.llm,tools=tools,
        messages=[SystemMessage(content=compose_base_text('content_brief', CONTENT_SYSTEM)),HumanMessage(content='Viết nội dung cho bản đã được duyệt.')],
        output_schema=ContentText,fallback=fallback,emit=emit,run_name=invocation_id)
    context=tools['get_content_context'].execute(tools['get_content_context'].args_schema())
    checks=[f'Nguồn: {context.fact_source_id}']
    checks.extend(f'Phong cách đã xác nhận: {style}' for style in context.memory.confirmed_style_notes)
    return replace(result, value=result.value.model_copy(update={'checks':checks}))
