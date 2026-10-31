"""Stable, user-safe business failures."""


class Fault(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def require(condition, code="STATE_CONFLICT", message="Trạng thái hoặc phiên bản không còn hợp lệ", status=409):
    if not condition:
        raise Fault(code, message, status)
