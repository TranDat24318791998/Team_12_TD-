"""Store theo run; commit nhiều ngăn là một CAS trong tiến trình."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from app.domain.models.learning import (MemoryCommit, StoreWrite, PublicHistory, Preference,
                                        CalibrationRecord, PublicLesson)


class StoreConflict(ValueError):
    pass


class MemoryStore:
    def __init__(self):
        self._data = {}
        self._meta = {}
        self._receipts = {}
        self.lock = RLock()

    def get(self, namespace, key, default=None):
        with self.lock:
            return deepcopy(self._data.get(tuple(namespace), {}).get(key, default))

    def put(self, namespace, key, value):
        with self.lock:
            self._data.setdefault(tuple(namespace), {})[key] = deepcopy(value)

    def list(self, namespace):
        with self.lock:
            return deepcopy(list(self._data.get(tuple(namespace), {}).values()))

    def metadata(self, run_id):
        with self.lock:
            return self._meta.get(run_id, (0, 0))

    def commit_batch(self, writes: list[StoreWrite], *, run_id: str, expected_revision: int,
                     new_cursor: int, receipt_key: str) -> MemoryCommit:
        with self.lock:
            receipt_id = (run_id, receipt_key)
            if receipt_id in self._receipts:
                return self._receipts[receipt_id].model_copy(update={"duplicate": True}, deep=True)
            revision, cursor = self.metadata(run_id)
            if revision != expected_revision or new_cursor < cursor:
                raise StoreConflict("stale revision or cursor")
            next_data = deepcopy(self._data)
            ids = []
            allowed = {"history", "preferences", "calibration", "lessons"}
            for write in writes:
                item = StoreWrite.model_validate(write)
                if item.namespace[0] != run_id or item.namespace[1] not in allowed or not item.namespace[2]:
                    raise ValueError("invalid namespace")
                expected_type = {'history': PublicHistory, 'preferences': Preference,
                                 'calibration': CalibrationRecord, 'lessons': PublicLesson}[item.namespace[1]]
                if item.value is not None and not isinstance(item.value, expected_type):
                    raise ValueError("value does not match compartment")
                values = next_data.setdefault(item.namespace, {})
                if item.value is None:
                    if item.namespace[1] != "lessons":
                        raise ValueError("only lessons may be deleted")
                    values.pop(item.key, None)
                else:
                    values[item.key] = deepcopy(item.value)
                ids.append(item.key)
            result = MemoryCommit(revision=revision + 1, cursor=new_cursor, applied_ids=ids, duplicate=False)
            self._data = next_data
            self._meta[run_id] = (result.revision, result.cursor)
            self._receipts[receipt_id] = result
            return result.model_copy(deep=True)
