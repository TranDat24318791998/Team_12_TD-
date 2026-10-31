from types import SimpleNamespace
from langchain_core.messages import AIMessage


def call(name, args, call_id):
    return {'name': name, 'args': args, 'id': call_id, 'type': 'tool_call'}


class FakeLLM:
    is_fixture = True
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.settings = SimpleNamespace(llm_model_reflect='fake')
        self.remaining_calls = 64

    def invoke_tools(self, messages, **kwargs):
        self.requests.append((list(messages), kwargs))
        self.remaining_calls -= 1
        response = self.responses.pop(0)
        if callable(response):
            response = response(messages)
        if isinstance(response, Exception):
            raise response
        return AIMessage(content='', tool_calls=response)
