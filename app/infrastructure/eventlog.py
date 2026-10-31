"""Nhật ký sự kiện theo run; không lưu prompt hoặc token."""

from datetime import datetime
from pathlib import Path
from threading import RLock
from app.domain.models.events import Event


class EventLog:
    def __init__(self, db_path=None):
        self.path = Path(db_path) if db_path else None
        self.lock = RLock()
        self.events = []
        self._seq = {}

    def add(self, run_id, day, type, actor, shop_id, text_vi, data):
        with self.lock:
            seq = self._seq.get(run_id, 0) + 1
            event = Event(seq=seq, run_id=run_id, day=day, ts=datetime.now().strftime('%H:%M'),
                          type=type, actor=actor, shop_id=shop_id, text_vi=text_vi, data=data)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open('a', encoding='utf-8') as output:
                    output.write(event.model_dump_json() + '\n')
            self._seq[run_id] = seq
            self.events.append(event)
            return event.model_copy(deep=True)

    def since(self, run_id, after_seq):
        with self.lock:
            return [e.model_copy(deep=True) for e in self.events if e.run_id == run_id and e.seq > after_seq]
