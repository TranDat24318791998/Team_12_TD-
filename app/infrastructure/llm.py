"""OpenAI function-calling transport; không giữ state nghiệp vụ."""

from threading import Lock
from langchain_openai import ChatOpenAI


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings, *, model_factory=ChatOpenAI):
        self.settings = settings
        self.remaining_calls = settings.max_live_calls_per_session
        self.available = True
        self._lock = Lock()
        self.model_factory = model_factory

    def invoke_tools(self, messages, *, tools, tool_choice, parallel_tool_calls, run_name, model=None):
        if self.settings.resolved_mode() != 'live' or not self.available or not (model or self.settings.llm_model):
            raise LLMUnavailable('model_not_configured')
        try:
            client = self.model_factory(model=model or self.settings.llm_model,
                                        api_key=self.settings.openai_api_key,
                                        timeout=8, max_retries=0)
            bound = client.bind_tools(tools, strict=True, tool_choice=tool_choice,
                                      parallel_tool_calls=parallel_tool_calls)
        except (ValueError, TypeError) as exc:
            raise LLMUnavailable('schema_invalid') from exc
        with self._lock:
            if self.remaining_calls <= 0:
                raise LLMUnavailable('budget_exhausted')
            self.remaining_calls -= 1
        try:
            return bound.invoke(messages, config={'run_name': run_name})
        except Exception as exc:
            with self._lock:
                self.available = False
            raise LLMUnavailable('provider_failed') from exc
