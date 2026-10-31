"""Knowledge repository semantics shared by memory and SQLite backends."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from threading import RLock
from app.domain.models.learning import (CallReservation, KnowledgeCommit, KnowledgeRecord,
    LegacyCommitReceipt, MemoryCommit, NightCommit, NightPublication, NightSnapshot,
    ReflectionReceipt, StoreWrite)
from app.memory.skills import canonical_bytes


class StoreConflict(ValueError):
    pass


def _hash(value):
    return sha256(canonical_bytes(value)).hexdigest()


def validate_writes(writes, run_id, *, shop_id=None, category=None):
    validated = []
    for write in writes:
        item = StoreWrite.model_validate_json(write.model_dump_json())
        run, compartment, scope = item.namespace
        if run != run_id or compartment not in ('history', 'preferences', 'calibration', 'lessons') or not scope or not item.key:
            raise ValueError('invalid namespace')
        if shop_id is not None and ((compartment in ('history', 'preferences') and scope != shop_id)
                or (compartment == 'calibration' and scope != category)
                or (compartment == 'lessons' and scope not in ('strategy', category))):
            raise ValueError('WRITE_SCOPE_DENIED')
        if item.value is None:
            if compartment != 'lessons':
                raise ValueError('only lessons may be deleted')
        else:
            KnowledgeRecord(run_id=run, compartment=compartment, scope=scope,
                            record_key=item.key, value=item.value)
        validated.append(item)
    return validated


class MemoryStore:
    def __init__(self):
        self._data = {}
        self._meta = {}
        self._limits = {}
        self._receipts = {}
        self._snapshots = {}
        self._reflections = {}
        self._versions = {}
        self._commits = {}
        self._reservations = {}
        self.lock = RLock()

    def get(self, namespace, key, default=None):
        with self.lock:
            return deepcopy(self._data.get(tuple(namespace), {}).get(key, default))

    def put(self, namespace, key, value):
        with self.lock:
            write = StoreWrite(namespace=tuple(namespace), key=key, value=value)
            validate_writes([write], namespace[0])
            if value is None:
                self._data.setdefault(tuple(namespace), {}).pop(key, None)
            else:
                self._data.setdefault(tuple(namespace), {})[key] = deepcopy(value)

    def list(self, namespace):
        with self.lock:
            return deepcopy(list(self._data.get(tuple(namespace), {}).values()))

    def metadata(self, run_id):
        with self.lock:
            return self._meta.get(run_id, (0, 0))

    def commit_batch(self, writes, *, run_id, expected_revision, new_cursor, receipt_key):
        with self.lock:
            payload_hash = _hash({'run_id': run_id, 'new_cursor': new_cursor,
                                  'writes': [w.model_dump(mode='json') for w in writes]})
            key = (run_id, receipt_key)
            old = self._receipts.get(key)
            if old:
                if old.payload_hash != payload_hash:
                    raise StoreConflict('LEGACY_REQUEST_CONFLICT')
                return old.result.model_copy(update={'duplicate': True}, deep=True)
            revision, cursor = self.metadata(run_id)
            if revision != expected_revision or new_cursor < cursor:
                raise StoreConflict('STALE_KNOWLEDGE')
            items = validate_writes(writes, run_id)
            data = deepcopy(self._data)
            for item in items:
                values = data.setdefault(item.namespace, {})
                if item.value is None:
                    values.pop(item.key, None)
                else:
                    values[item.key] = deepcopy(item.value)
            result = MemoryCommit(revision=revision + 1, cursor=new_cursor,
                                  applied_ids=[item.key for item in items], duplicate=False)
            self._data = data
            self._meta[run_id] = (result.revision, result.cursor)
            self._receipts[key] = LegacyCommitReceipt(run_id=run_id, receipt_key=receipt_key,
                                                       payload_hash=payload_hash, result=result)
            return result.model_copy(deep=True)

    def save_night_snapshot(self, snapshot):
        snapshot = NightSnapshot.model_validate_json(snapshot.model_dump_json())
        with self.lock:
            key = (snapshot.run_id, snapshot.day)
            old = self._snapshots.get(key)
            if old and (old.snapshot_hash != snapshot.snapshot_hash or old.shop_id != snapshot.shop_id):
                raise StoreConflict('NIGHT_SNAPSHOT_CONFLICT')
            if old is None:
                self._snapshots[key] = snapshot.model_copy(deep=True)
            return self._snapshots[key].model_copy(deep=True)

    def get_night_snapshot(self, run_id, day):
        with self.lock:
            return deepcopy(self._snapshots.get((run_id, day)))

    def claim_reflection(self, run_id, day, snapshot_hash, owner_token):
        with self.lock:
            snapshot = self._snapshots.get((run_id, day))
            if not snapshot or snapshot.snapshot_hash != snapshot_hash:
                raise StoreConflict('NIGHT_SNAPSHOT_CONFLICT')
            key = (run_id, day)
            if key not in self._reflections:
                self._reflections[key] = ReflectionReceipt(run_id=run_id, shop_id=snapshot.shop_id,
                    day=day, snapshot_hash=snapshot_hash, owner_token=owner_token, status='reserved',
                    output=None, source='skipped', error_code=None)
            return self._reflections[key].model_copy(deep=True)

    def finish_reflection(self, receipt):
        receipt = ReflectionReceipt.model_validate_json(receipt.model_dump_json())
        with self.lock:
            key = (receipt.run_id, receipt.day)
            old = self._reflections.get(key)
            if not old or (receipt.snapshot_hash, receipt.shop_id, receipt.owner_token) != (old.snapshot_hash, old.shop_id, old.owner_token):
                raise StoreConflict('REFLECTION_RESULT_CONFLICT')
            if receipt.status == 'reserved' or (receipt.status in ('failed', 'unknown') and
                                                (receipt.source != 'skipped' or not receipt.error_code)):
                raise ValueError('invalid terminal reflection')
            if old.status != 'reserved':
                if old != receipt:
                    raise StoreConflict('REFLECTION_RESULT_CONFLICT')
                return old.model_copy(deep=True)
            self._reflections[key] = receipt.model_copy(deep=True)
            return receipt.model_copy(deep=True)

    def get_reflection(self, run_id, day):
        with self.lock:
            return deepcopy(self._reflections.get((run_id, day)))

    def recover_reserved_reflections(self, run_id):
        with self.lock:
            count = 0
            for key, receipt in list(self._reflections.items()):
                if key[0] == run_id and receipt.status == 'reserved':
                    self._reflections[key] = receipt.model_copy(update={'status': 'unknown', 'source': 'skipped',
                                                                         'error_code': 'PROCESS_RESTART'}, deep=True)
                    count += 1
            return count

    def list_skill_versions(self, run_id, shop_id, skill_id):
        with self.lock:
            return deepcopy(sorted(self._versions.get((run_id, shop_id, skill_id), []),
                                   key=lambda v: v.bundle.version))

    def get_night_commit(self, run_id, day):
        with self.lock:
            return deepcopy(self._commits.get((run_id, day)))

    def commit_night(self, publication, *, expected_revision, expected_cursor):
        publication = NightPublication.model_validate_json(publication.model_dump_json())
        with self.lock:
            key = (publication.run_id, publication.day)
            publication_hash = _hash(publication.model_dump(mode='json'))
            old = self._commits.get(key)
            if old:
                if (old.shop_id, old.snapshot_hash, old.publication_hash) != (publication.shop_id, publication.snapshot_hash, publication_hash):
                    raise StoreConflict('NIGHT_REQUEST_CONFLICT')
                result = old.model_copy(deep=True)
                result.knowledge.store.duplicate = True
                return result
            snapshot = self._snapshots.get(key)
            reflection = self._reflections.get(key)
            if (not snapshot or not reflection or reflection.status == 'reserved'
                    or (snapshot.shop_id, snapshot.snapshot_hash, snapshot.through_seq) !=
                       (publication.shop_id, publication.snapshot_hash, publication.through_seq)):
                raise StoreConflict('NIGHT_SNAPSHOT_CONFLICT')
            revision, cursor = self.metadata(publication.run_id)
            if (revision, cursor) != (expected_revision, expected_cursor) or publication.through_seq < cursor:
                raise StoreConflict('STALE_KNOWLEDGE')
            items = validate_writes(publication.writes, publication.run_id, shop_id=publication.shop_id,
                                    category=snapshot.category)
            for version in publication.versions:
                b = version.bundle
                if b.category != snapshot.category or version.source_through_seq != snapshot.through_seq:
                    raise ValueError('VERSION_SCOPE_MISMATCH')
                prior = self.list_skill_versions(publication.run_id, publication.shop_id, b.skill.skill_id)
                parent = prior[-1] if prior else None
                if version.parent_version != (parent.bundle.version if parent else 0):
                    raise StoreConflict('STALE_SKILL')
                if b.skill.base_hash != sha256(snapshot.base_texts[b.skill.skill_id].encode()).hexdigest():
                    raise ValueError('BASE_HASH_MISMATCH')
                if parent and parent.artifact_json == version.artifact_json:
                    raise ValueError('UNCHANGED_SKILL')
                if not parent and not b.skill.learned_steps:
                    raise ValueError('UNCHANGED_SKILL')
            data, versions = deepcopy(self._data), deepcopy(self._versions)
            for item in items:
                values = data.setdefault(item.namespace, {})
                if item.value is None:
                    values.pop(item.key, None)
                else:
                    values[item.key] = deepcopy(item.value)
            for version in publication.versions:
                b = version.bundle
                versions.setdefault((b.run_id, b.shop_id, b.skill.skill_id), []).append(version.model_copy(deep=True))
            commit = MemoryCommit(revision=revision + 1, cursor=publication.through_seq,
                                  applied_ids=[w.key for w in items], duplicate=False)
            result = NightCommit(run_id=publication.run_id, shop_id=publication.shop_id, day=publication.day,
                snapshot_hash=publication.snapshot_hash, publication_hash=publication_hash,
                knowledge=KnowledgeCommit(store=commit, accepted_lesson_ops=publication.summary.lesson_ops,
                                          rejected_ops=len(publication.rejections)),
                summary=publication.summary, versions=publication.versions, rejections=publication.rejections,
                source=publication.source)
            self._data, self._versions = data, versions
            self._meta[publication.run_id] = (commit.revision, commit.cursor)
            self._commits[key] = result.model_copy(deep=True)
            return result.model_copy(deep=True)

    def reserve_llm_call(self, run_id, call_id, limit):
        if not run_id or not call_id or type(limit) is not int or limit < 0:
            raise ValueError('invalid reservation')
        with self.lock:
            if run_id in self._limits and self._limits[run_id] != limit:
                raise StoreConflict('BUDGET_LIMIT_CONFLICT')
            self._limits[run_id] = limit
            used = self.llm_calls_used(run_id)
            key = (run_id, call_id)
            if key in self._reservations:
                reason = 'already_reserved'
            elif used >= limit:
                reason = 'exhausted'
            else:
                reason = 'granted'
                self._reservations[key] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                used += 1
            return CallReservation(granted=reason == 'granted', reason=reason, used=used, remaining=max(0, limit-used))

    def llm_calls_used(self, run_id):
        with self.lock:
            return sum(key[0] == run_id for key in self._reservations)
