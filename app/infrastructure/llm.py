"""OpenAI function-calling transport; không giữ state nghiệp vụ."""

from threading import Lock
from uuid import uuid4
from langchain_openai import ChatOpenAI


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings, *, model_factory=ChatOpenAI, store=None, run_id=None, replay_cache=None):
        self.settings = settings
        self._remaining_calls = settings.max_live_calls_per_session
        self.store, self.run_id = store, run_id
        self.replay_cache = replay_cache
        self.last_source = None
        self._pending_replay = {}
        self.available = True
        self._lock = Lock()
        self.model_factory = model_factory

    @property
    def remaining_calls(self):
        if self.store is not None and self.run_id is not None:
            return max(0, self.settings.max_live_calls_per_session - self.store.llm_calls_used(self.run_id))
        return self._remaining_calls

    def invoke_tools(self, messages, *, tools, tool_choice, parallel_tool_calls, run_name, model=None, call_id=None, replay_context=None):
        self.last_source = None
        selected_model = model or self.settings.llm_model
        if replay_context is not None:
            replay_context = dict(replay_context)
            if selected_model:
                replay_context['model_id'] = selected_model
            if self.settings.llm_reasoning_effort is not None:
                replay_context['model_parameters'] = {**replay_context.get('model_parameters', {}),
                                                      'reasoning_effort': self.settings.llm_reasoning_effort}
        mode = self.settings.resolved_mode()
        if mode == 'replay':
            if self.replay_cache is None or replay_context is None:
                raise LLMUnavailable('REPLAY_MISS')
            from app.infrastructure.replay import ReplayMiss
            try:
                response = self.replay_cache.lookup(context=replay_context,messages=messages,tools=tools,
                    tool_choice=tool_choice,parallel_tool_calls=parallel_tool_calls)
            except (ReplayMiss, KeyError, ValueError) as exc:
                raise LLMUnavailable('REPLAY_MISS') from exc
            self.last_source = 'replay'
            return response
        if mode != 'live' or not self.available or not selected_model:
            raise LLMUnavailable('model_not_configured')
        try:
            options = {'model':selected_model,'api_key':self.settings.openai_api_key,
                       'timeout':self.settings.llm_timeout_seconds,'max_retries':0}
            if selected_model == 'gpt-6.1-terra':
                options['use_responses_api'] = True
                if self.settings.llm_reasoning_effort is not None:
                    options['reasoning'] = {'effort':self.settings.llm_reasoning_effort}
            elif self.settings.llm_reasoning_effort is not None:
                options['reasoning_effort'] = self.settings.llm_reasoning_effort
            client = self.model_factory(**options)
            bound = client.bind_tools(tools, strict=True, tool_choice=tool_choice,
                                      parallel_tool_calls=parallel_tool_calls)
        except (ValueError, TypeError) as exc:
            raise LLMUnavailable('schema_invalid') from exc
        with self._lock:
            if self.store is not None and self.run_id is not None:
                reservation = self.store.reserve_llm_call(self.run_id, call_id or uuid4().hex,
                                                          self.settings.max_live_calls_per_session)
                if not reservation.granted:
                    raise LLMUnavailable('budget_' + reservation.reason)
            else:
                if self._remaining_calls <= 0:
                    raise LLMUnavailable('budget_exhausted')
                self._remaining_calls -= 1
        try:
            response = bound.invoke(messages, config={'run_name': run_name})
            self.last_source = 'live'
            if self.replay_cache is not None and replay_context is not None and call_id:
                self._pending_replay[call_id] = dict(context=replay_context,messages=list(messages),tools=tools,
                    tool_choice=tool_choice,parallel_tool_calls=parallel_tool_calls,response=response)
            return response
        except Exception as exc:
            with self._lock:
                self.available = False
            raise LLMUnavailable('provider_failed') from exc

    def confirm_replay(self, call_id):
        """Record only after the runner has validated the provider protocol."""
        pending = self._pending_replay.pop(call_id, None)
        if pending and self.replay_cache is not None:
            from app.infrastructure.replay import ReplayMiss
            try:
                self.replay_cache.record_valid(**pending)
            except (ReplayMiss, KeyError, ValueError):
                pass
