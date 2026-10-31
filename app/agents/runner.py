"""Bounded native tool protocol with role isolation and deterministic fallback."""

import json
from dataclasses import dataclass
from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ValidationError
from app.agents.tools import ROLE_TOOLS
from data.growth_data.text_validation import content_matches_facts as _content_matches_facts


class AgentToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentRun:
    value: BaseModel
    source: Literal['live', 'replay', 'offline', 'fixture']
    tool_call_ids: list[str]
    error_code: str | None


def _schema(name, schema):
    function = convert_to_openai_tool(schema, strict=True)
    function['function']['name'] = name
    function['function']['description'] = (schema.__doc__ or name).strip()
    def normalize(node):
        if isinstance(node, dict):
            node.pop('default', None)
            for child in node.values(): normalize(child)
        elif isinstance(node, list):
            for child in node: normalize(child)
    normalize(function['function']['parameters'])
    return function


def _same(a, b):
    return a is not None and b is not None and a.model_dump(mode='json') == b.model_dump(mode='json')


def _can_finish(role, output, successful, tools):
    def seen(name):
        return successful.get(name, [])
    if role == 'platform':
        if not seen('get_public_context') or not seen('read_memory'):
            return False
        if tools.get('search_campaign_catalog') and tools['search_campaign_catalog'].required and not seen('search_campaign_catalog'):
            return False
        if output.action == 'withdraw':
            return output.package is None
        package = output.package
        checked = any((_same(result.input_package, package) and result.ok) or
                      (_same(result.corrected_package, package) and not result.violations_after)
                      for _, result in seen('validate_platform_package'))
        forecasted = any(_same(args.package, package) for args, _ in seen('forecast_package'))
        return bool(checked and forecasted)
    if role == 'shop':
        evaluations = seen('evaluate_shop_package')
        if not seen('get_shop_private_context') or not seen('read_memory') or not evaluations:
            return False
        expected = tools['evaluate_shop_package'].expected_package
        originals = [(args, result) for args, result in evaluations if _same(args.package, expected)]
        if expected is None or not originals:
            return False
        if output.action == 'reject':
            return output.package is None
        if output.action == 'accept':
            return _same(output.package, expected) and any(result.ok for _, result in originals)
        if output.action == 'counter':
            return any(_same(output.package, result.corrected_package) and not result.violations_after
                       for _, result in evaluations)
        return False
    if role == 'referee':
        if not seen('get_referee_context'):
            return False
        context = seen('get_referee_context')[-1][1]
        ids = {turn.turn_id for turn in context.turns}
        return set(output.evidence_refs) <= ids and (bool(output.evidence_refs) or not ids)
    if role == 'content':
        if not seen('get_content_context'):
            return False
        context = seen('get_content_context')[-1][1]
        sources = [context.title, context.description, *context.attributes, *context.memory.confirmed_style_notes]
        return bool(output.title.strip()) and _content_matches_facts(f'{output.title}. {output.description}', sources)
    if role == 'learning':
        return bool(seen('read_learning_evidence'))
    return False


def run_agent(role, *, llm, tools, messages, output_schema, fallback, emit, run_name, replay_context=None, validate_output=None):
    if role not in ROLE_TOOLS:
        raise ValueError('unknown role')
    tools = {name: tool for name, tool in tools.items() if name in ROLE_TOOLS[role]}
    trace_ids, successful, seen_ids = [], {}, set()
    model_source = 'fixture' if getattr(llm, 'is_fixture', False) else 'live'
    terminal = f'finish_{role}'
    log = emit or (lambda event, data: None)

    def record_refs(value):
        result = []
        for collection, field in (('history', 'negotiation_id'), ('lessons', 'lesson_id'),
                                  ('preferences', 'pref_id'), ('existing_lessons', 'lesson_id')):
            for item in getattr(value, collection, []):
                result.append({'id': getattr(item, field), 'version': getattr(item, 'version', None)})
        for ident in getattr(value, 'preference_ids', []):
            result.append({'id': ident, 'version': None})
        return result

    def dispatch(name, raw, *, requested_by='workflow', call_id=None):
        if name not in tools:
            raise AgentToolError('tool_denied')
        tool = tools[name]
        try:
            arguments = tool.args_schema.model_validate(raw)
            log('tool_called', {'role': role, 'tool_name': name, 'tool_call_id': call_id,
                                'requested_by': requested_by, 'source': model_source if requested_by == 'model' else 'offline', 'status': 'started', 'invocation_id': run_name})
            value = tool.output_schema.model_validate(tool.execute(arguments))
            if len(value.model_dump_json().encode('utf-8')) > 128 * 1024:
                raise AgentToolError('TOOL_RESULT_TOO_LARGE')
            log('tool_result', {'role': role, 'tool_name': name, 'tool_call_id': call_id,
                                'requested_by': requested_by, 'source': model_source if requested_by == 'model' else 'offline', 'status': 'ok', 'invocation_id': run_name, 'record_refs': record_refs(value)})
            return arguments, value
        except Exception as exc:
            log('tool_result', {'role': role, 'tool_name': name, 'tool_call_id': call_id,
                                'requested_by': requested_by, 'source': model_source if requested_by == 'model' else 'offline', 'status': 'failed', 'invocation_id': run_name})
            if isinstance(exc, AgentToolError):
                raise
            raise AgentToolError('tool_failed') from exc

    def offline(reason):
        try:
            value = output_schema.model_validate(fallback(lambda name, args: dispatch(name, args)[1]))
            log('agent_completed', {'role': role, 'source': 'offline', 'error_code': reason, 'invocation_id': run_name})
            return AgentRun(value, 'offline', list(trace_ids), reason)
        except Exception as exc:
            raise AgentToolError('fallback_failed') from exc

    conversation = list(messages)
    normal_schemas = [_schema(name, tool.args_schema) for name, tool in tools.items()]
    final_schema = _schema(terminal, output_schema)
    for step in range(3):
        allowed_schemas = [final_schema] if step == 2 else normal_schemas + [final_schema]
        try:
            model = llm.settings.llm_model_reflect if role == 'learning' else None
            call_id=f'{run_name}:{step}'
            replay_kwargs={'replay_context':{**replay_context,'step':step}} if replay_context is not None else {}
            response = llm.invoke_tools(conversation, tools=allowed_schemas,
                                        tool_choice=terminal if step == 2 else 'auto',
                                        parallel_tool_calls=step < 2, run_name=run_name, model=model, call_id=call_id, **replay_kwargs)
        except Exception:
            return offline('provider_unavailable')
        model_source='fixture' if getattr(llm,'is_fixture',False) else getattr(llm,'last_source',None) or 'live'
        if not isinstance(response, AIMessage):
            return offline('invalid_provider_response')
        calls = response.tool_calls
        if response.invalid_tool_calls or not calls or len(calls) > 4:
            return offline('invalid_tool_calls')
        ids = [item.get('id') for item in calls]
        if any(not isinstance(i, str) or not 1 <= len(i) <= 128 for i in ids) or len(set(ids)) != len(ids) or set(ids) & seen_ids:
            return offline('invalid_call_id')
        names = [item.get('name') for item in calls]
        if terminal in names and (len(calls) != 1 or names[0] != terminal):
            return offline('mixed_terminal')
        if step == 2 and names != [terminal]:
            return offline('missing_terminal')
        validated = []
        try:
            for item in calls:
                name, raw = item['name'], item.get('args', {})
                if len(json.dumps(raw, ensure_ascii=False).encode('utf-8')) > 16 * 1024:
                    raise AgentToolError('TOOL_ARGUMENTS_TOO_LARGE')
                if name == terminal:
                    obj = output_schema.model_validate(raw)
                else:
                    if name not in tools:
                        raise AgentToolError('tool_denied')
                    obj = tools[name].args_schema.model_validate(raw)
                validated.append((name, obj, item['id']))
        except (ValueError, TypeError, ValidationError, AgentToolError):
            return offline('invalid_tool_args')
        seen_ids.update(ids)
        conversation.append(response)
        if names == [terminal]:
            output = validated[0][1]
            if not _can_finish(role, output, successful, tools):
                return offline('prerequisite_failed')
            error = validate_output(output) if validate_output else None
            if error:
                log('tool_result', {'role': role, 'tool_name': terminal, 'tool_call_id': ids[0],
                                    'requested_by': 'model', 'source': model_source, 'status': 'failed',
                                    'error_code': 'TERMINAL_OUTPUT_INVALID', 'invocation_id': run_name})
                if step == 2:
                    return offline('terminal_output_invalid')
                conversation.append(ToolMessage(content=json.dumps({'error': error}, ensure_ascii=False),
                                                name=terminal, tool_call_id=ids[0]))
                continue
            if hasattr(llm,'confirm_replay'): llm.confirm_replay(call_id)
            log('agent_completed', {'role': role, 'source': model_source, 'error_code': None, 'invocation_id': run_name})
            return AgentRun(output, model_source, list(trace_ids), None)
        for name, arguments, call_id in validated:
            try:
                args, result = dispatch(name, arguments.model_dump(mode='json'), requested_by='model', call_id=call_id)
                successful.setdefault(name, []).append((args, result))
                trace_ids.append(call_id)
                content = result.model_dump_json()
            except AgentToolError:
                content = json.dumps({'error': 'TOOL_FAILED'})
            conversation.append(ToolMessage(content=content, name=name, tool_call_id=call_id))
        if hasattr(llm,'confirm_replay'): llm.confirm_replay(f'{run_name}:{step}')
    return offline('call_limit')
