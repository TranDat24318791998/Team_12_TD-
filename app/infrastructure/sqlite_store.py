"""Durable Knowledge repository using the Data store's SQLite transactions."""

from copy import deepcopy
import json
from app.domain.models.learning import (KnowledgeRecord, LegacyCommitReceipt, NightCommit,
    NightSnapshot, Preference, ReflectionReceipt, SkillVersion, StoreWrite)
from app.domain.policies import PREF_ASK_THRESHOLD, PREF_DECLINE_SILENCE_DAYS
from app.infrastructure.store import MemoryStore, StoreConflict, _hash, validate_writes
from app.memory.skills import canonical_bytes


def _json(value):
    return canonical_bytes(value.model_dump(mode='json')).decode('utf-8')


class SqliteKnowledgeStore:
    def __init__(self, store):
        if not hasattr(store, 'connect'):
            from data.growth_data.storage import Store
            store = Store(store)
        self.store = store

    def _load(self, c, run_id):
        memory = MemoryStore()
        row = c.execute('SELECT revision,cursor,llm_limit FROM knowledge_meta WHERE run_id=?', (run_id,)).fetchone()
        if row:
            memory._meta[run_id] = (row[0], row[1])
            if row[2] is not None:
                memory._limits[run_id] = row[2]
        for row in c.execute('SELECT compartment,scope,record_key,payload_json FROM knowledge_records WHERE run_id=?', (run_id,)):
            record = KnowledgeRecord.model_validate_json(row[3])
            if (record.run_id,record.compartment,record.scope,record.record_key) != (run_id,row[0],row[1],row[2]):
                raise ValueError('RECORD_KEY_MISMATCH')
            memory._data.setdefault((record.run_id, record.compartment, record.scope), {})[record.record_key] = record.value
        for row in c.execute('SELECT payload_json FROM knowledge_receipts WHERE run_id=?', (run_id,)):
            receipt = LegacyCommitReceipt.model_validate_json(row[0])
            memory._receipts[(run_id, receipt.receipt_key)] = receipt
        for row in c.execute('SELECT payload_json FROM night_snapshots WHERE run_id=?', (run_id,)):
            snapshot = NightSnapshot.model_validate_json(row[0])
            memory._snapshots[(run_id, snapshot.day)] = snapshot
        for row in c.execute('SELECT payload_json FROM reflection_receipts WHERE run_id=?', (run_id,)):
            receipt = ReflectionReceipt.model_validate_json(row[0])
            memory._reflections[(run_id, receipt.day)] = receipt
        for row in c.execute('SELECT payload_json FROM skill_versions WHERE run_id=? ORDER BY version', (run_id,)):
            version = SkillVersion.model_validate_json(row[0])
            b = version.bundle
            memory._versions.setdefault((run_id, b.shop_id, b.skill.skill_id), []).append(version)
        for row in c.execute('SELECT payload_json FROM night_commits WHERE run_id=?', (run_id,)):
            commit = NightCommit.model_validate_json(row[0])
            memory._commits[(run_id, commit.day)] = commit
        for row in c.execute('SELECT call_id,reserved_at FROM llm_call_reservations WHERE run_id=?', (run_id,)):
            memory._reservations[(run_id, row[0])] = row[1]
        return memory

    def _flush(self, c, run_id, before, after):
        if before._meta.get(run_id) != after._meta.get(run_id) or before._limits.get(run_id) != after._limits.get(run_id):
            revision, cursor = after.metadata(run_id)
            c.execute('INSERT INTO knowledge_meta(run_id,revision,cursor,llm_limit) VALUES(?,?,?,?) '
                      'ON CONFLICT(run_id) DO UPDATE SET revision=excluded.revision,cursor=excluded.cursor,llm_limit=excluded.llm_limit',
                      (run_id, revision, cursor, after._limits.get(run_id)))
        namespaces = set(before._data) | set(after._data)
        for namespace in namespaces:
            if namespace[0] != run_id:
                continue
            old, new = before._data.get(namespace, {}), after._data.get(namespace, {})
            for key in set(old) | set(new):
                if old.get(key) == new.get(key):
                    continue
                if key not in new:
                    c.execute('DELETE FROM knowledge_records WHERE run_id=? AND compartment=? AND scope=? AND record_key=?', (*namespace, key))
                else:
                    record = KnowledgeRecord(run_id=run_id, compartment=namespace[1], scope=namespace[2], record_key=key, value=new[key])
                    c.execute('INSERT INTO knowledge_records(run_id,compartment,scope,record_key,payload_json) VALUES(?,?,?,?,?) '
                              'ON CONFLICT(run_id,compartment,scope,record_key) DO UPDATE SET payload_json=excluded.payload_json',
                              (*namespace, key, _json(record)))
        for key, receipt in after._receipts.items():
            if key not in before._receipts:
                c.execute('INSERT INTO knowledge_receipts(run_id,receipt_key,payload_hash,payload_json) VALUES(?,?,?,?)',
                          (run_id, key[1], receipt.payload_hash, _json(receipt)))
        for key, snapshot in after._snapshots.items():
            if key not in before._snapshots:
                c.execute('INSERT INTO night_snapshots(run_id,day,shop_id,snapshot_hash,payload_json) VALUES(?,?,?,?,?)',
                          (run_id, snapshot.day, snapshot.shop_id, snapshot.snapshot_hash, _json(snapshot)))
        for key, receipt in after._reflections.items():
            if before._reflections.get(key) != receipt:
                c.execute('INSERT INTO reflection_receipts(run_id,day,snapshot_hash,owner_token,status,payload_json) VALUES(?,?,?,?,?,?) '
                          'ON CONFLICT(run_id,day) DO UPDATE SET status=excluded.status,payload_json=excluded.payload_json',
                          (run_id, receipt.day, receipt.snapshot_hash, receipt.owner_token, receipt.status, _json(receipt)))
        for key, versions in after._versions.items():
            existing = {v.bundle.version for v in before._versions.get(key, [])}
            for version in versions:
                b = version.bundle
                if b.version not in existing:
                    c.execute('INSERT INTO skill_versions(run_id,shop_id,skill_id,version,created_day,effective_from_day,payload_json) VALUES(?,?,?,?,?,?,?)',
                              (run_id, b.shop_id, b.skill.skill_id, b.version, version.created_day, b.effective_from_day, _json(version)))
        for key, commit in after._commits.items():
            if key not in before._commits:
                c.execute('INSERT INTO night_commits(run_id,day,shop_id,snapshot_hash,publication_hash,payload_json) VALUES(?,?,?,?,?,?)',
                          (run_id, commit.day, commit.shop_id, commit.snapshot_hash, commit.publication_hash, _json(commit)))
        for key, timestamp in after._reservations.items():
            if key not in before._reservations:
                c.execute('INSERT INTO llm_call_reservations(run_id,call_id,reserved_at) VALUES(?,?,?)', (run_id, key[1], timestamp))

    def _read(self, run_id, method, *args):
        with self.store.connect() as c:
            return getattr(self._load(c, run_id), method)(*args)

    def _change_tx(self, c, scope_run_id, method, *args, **kwargs):
        memory = self._load(c, scope_run_id)
        before = deepcopy_state(memory)
        result = getattr(memory, method)(*args, **kwargs)
        self._flush(c, scope_run_id, before, memory)
        return result

    def _change(self, scope_run_id, method, *args, **kwargs):
        with self.store.connect(write=True) as c:
            return self._change_tx(c, scope_run_id, method, *args, **kwargs)

    def get(self, namespace, key, default=None):
        with self.store.connect() as c:
            row = c.execute('SELECT payload_json FROM knowledge_records WHERE run_id=? AND compartment=? AND scope=? AND record_key=?', (*namespace,key)).fetchone()
        if not row:
            return deepcopy(default)
        record = KnowledgeRecord.model_validate_json(row[0])
        if (record.run_id,record.compartment,record.scope,record.record_key) != (*namespace,key):
            raise ValueError('RECORD_KEY_MISMATCH')
        return record.value

    def list(self, namespace):
        with self.store.connect() as c:
            rows = c.execute('SELECT record_key,payload_json FROM knowledge_records WHERE run_id=? AND compartment=? AND scope=? ORDER BY record_key', tuple(namespace)).fetchall()
        result = []
        for key, payload in rows:
            record = KnowledgeRecord.model_validate_json(payload)
            if (record.run_id,record.compartment,record.scope,record.record_key) != (*namespace,key):
                raise ValueError('RECORD_KEY_MISMATCH')
            result.append(record.value)
        return result

    def put(self, namespace, key, value):
        return self._change(namespace[0], 'put', namespace, key, value)

    def metadata(self, run_id):
        with self.store.connect() as c:
            row = c.execute('SELECT revision,cursor FROM knowledge_meta WHERE run_id=?',(run_id,)).fetchone()
        return (row[0],row[1]) if row else (0,0)

    def commit_batch(self, writes, *, run_id, expected_revision, new_cursor, receipt_key):
        return self._change(run_id, 'commit_batch', writes, run_id=run_id, expected_revision=expected_revision,
                            new_cursor=new_cursor, receipt_key=receipt_key)

    def save_night_snapshot(self, snapshot):
        return self._change(snapshot.run_id, 'save_night_snapshot', snapshot)

    def get_night_snapshot(self, run_id, day):
        return self._payload('night_snapshots', NightSnapshot, run_id, day)

    def claim_reflection(self, run_id, day, snapshot_hash, owner_token):
        return self._change(run_id, 'claim_reflection', run_id, day, snapshot_hash, owner_token)

    def finish_reflection(self, receipt):
        return self._change(receipt.run_id, 'finish_reflection', receipt)

    def get_reflection(self, run_id, day):
        return self._payload('reflection_receipts', ReflectionReceipt, run_id, day)

    def recover_reserved_reflections(self, run_id):
        return self._change(run_id, 'recover_reserved_reflections', run_id)

    def list_skill_versions(self, run_id, shop_id, skill_id):
        with self.store.connect() as c:
            rows = c.execute('SELECT payload_json FROM skill_versions WHERE run_id=? AND shop_id=? AND skill_id=? ORDER BY version', (run_id,shop_id,skill_id)).fetchall()
        return [SkillVersion.model_validate_json(row[0]) for row in rows]

    def _payload(self, table, model, run_id, day):
        with self.store.connect() as c:
            row = c.execute(f'SELECT payload_json FROM {table} WHERE run_id=? AND day=?',(run_id,day)).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def get_night_commit(self, run_id, day):
        return self._payload('night_commits', NightCommit, run_id, day)

    def commit_night(self, publication, *, expected_revision, expected_cursor):
        with self.store.connect(write=True) as c:
            return self.commit_night_tx(c, publication, expected_revision=expected_revision, expected_cursor=expected_cursor)

    def commit_night_tx(self, c, publication, *, expected_revision, expected_cursor):
        return self._change_tx(c, publication.run_id, 'commit_night', publication,
                               expected_revision=expected_revision, expected_cursor=expected_cursor)

    def reserve_llm_call(self, run_id, call_id, limit):
        return self._change(run_id, 'reserve_llm_call', run_id, call_id, limit)

    def llm_calls_used(self, run_id):
        with self.store.connect() as c:
            return c.execute('SELECT COUNT(*) FROM llm_call_reservations WHERE run_id=?',(run_id,)).fetchone()[0]

    def validate_preference_tx(self, c, *, run_id, shop_id, pref_id, field, value, day):
        pref = self._load(c, run_id).get((run_id, 'preferences', shop_id), pref_id)
        if (not pref or (pref.field, pref.value) != (field, str(value))
                or pref.observation_count < PREF_ASK_THRESHOLD
                or not (pref.status == 'candidate' or (pref.status == 'declined' and pref.declined_until is not None and day >= pref.declined_until))):
            raise ValueError('PREFERENCE_NOT_ASKABLE')
        return pref

    def _preference_tx(self, c, *, run_id, shop_id, pref_id, receipt_key, request, update):
        memory = self._load(c, run_id)
        before = deepcopy_state(memory)
        key = (run_id, receipt_key)
        request_hash = _hash(request)
        old = memory._receipts.get(key)
        if old:
            if old.payload_hash != request_hash:
                raise StoreConflict('LEGACY_REQUEST_CONFLICT')
            return old.result.model_copy(update={'duplicate': True}, deep=True)
        pref = memory.get((run_id, 'preferences', shop_id), pref_id)
        if pref is None:
            raise ValueError('PREFERENCE_NOT_FOUND')
        updated = update(pref)
        write = StoreWrite(namespace=(run_id, 'preferences', shop_id), key=pref_id, value=updated)
        validate_writes([write], run_id)
        revision, cursor = memory.metadata(run_id)
        result = memory.commit_batch([write], run_id=run_id, expected_revision=revision,
                                     new_cursor=cursor, receipt_key=receipt_key)
        memory._receipts[key].payload_hash = request_hash
        self._flush(c, run_id, before, memory)
        return result

    def _matching_question(self, c, *, run_id, shop_id, pref_id, question_id, pref):
        question = c.execute('SELECT shop_id,external_pref_id,field,value_json FROM rule_questions WHERE run_id=? AND question_id=?',
                             (run_id,question_id)).fetchone()
        if (not question or question[0] != shop_id or question[1] != pref_id or
                (question[2],str(json.loads(question[3]))) != (pref.field,pref.value)):
            raise ValueError('PREFERENCE_QUESTION_MISMATCH')

    def mark_preference_asked_tx(self, c, *, run_id, shop_id, pref_id, question_id, card_id, day):
        pref = self._load(c,run_id).get((run_id,'preferences',shop_id),pref_id)
        if not pref:
            raise ValueError('PREFERENCE_NOT_FOUND')
        self._matching_question(c,run_id=run_id,shop_id=shop_id,pref_id=pref_id,question_id=question_id,pref=pref)
        card = c.execute('SELECT shop_id,question_id,day FROM cards WHERE run_id=? AND card_id=?',(run_id,card_id)).fetchone()
        if not card or (card[0],card[1],card[2]) != (shop_id,question_id,day):
            raise ValueError('PREFERENCE_CARD_MISMATCH')
        def update(pref):
            if pref.observation_count < PREF_ASK_THRESHOLD or not (pref.status == 'candidate' or
                    (pref.status == 'declined' and pref.declined_until is not None and day >= pref.declined_until)):
                raise ValueError('PREFERENCE_NOT_ASKABLE')
            return pref.model_copy(update={'status': 'asked', 'asked_day': day}, deep=True)
        request = {'run_id':run_id, 'shop_id':shop_id, 'pref_id':pref_id, 'question_id':question_id, 'card_id':card_id, 'day':day}
        return self._preference_tx(c, run_id=run_id, shop_id=shop_id, pref_id=pref_id,
                                   receipt_key=f'pref:ask:{question_id}', request=request, update=update)

    def record_preference_answer_tx(self, c, *, run_id, shop_id, pref_id, question_id, decision_id, yes, day):
        pref = self._load(c,run_id).get((run_id,'preferences',shop_id),pref_id)
        if not pref:
            raise ValueError('PREFERENCE_NOT_FOUND')
        self._matching_question(c,run_id=run_id,shop_id=shop_id,pref_id=pref_id,question_id=question_id,pref=pref)
        decision = c.execute('SELECT shop_id,target_type,target_id,rule_answer FROM decisions WHERE run_id=? AND decision_id=?',
                             (run_id,decision_id)).fetchone()
        if type(yes) is not bool or not decision or decision[3] is None or (decision[0],decision[1],decision[2],bool(decision[3])) != (shop_id,'rule_question',question_id,yes):
            raise ValueError('PREFERENCE_DECISION_MISMATCH')
        def update(pref):
            if pref.status != 'asked':
                raise ValueError('PREFERENCE_NOT_ASKED')
            return pref.model_copy(update={'status': 'confirmed' if yes else 'declined',
                'declined_until': None if yes else day + PREF_DECLINE_SILENCE_DAYS}, deep=True)
        request = {'run_id':run_id, 'shop_id':shop_id, 'pref_id':pref_id, 'question_id':question_id,
                   'decision_id':decision_id, 'yes':yes, 'day':day}
        return self._preference_tx(c, run_id=run_id, shop_id=shop_id, pref_id=pref_id,
                                   receipt_key=f'pref:answer:{question_id}', request=request, update=update)


def deepcopy_state(memory):
    copy = MemoryStore()
    for name in ('_data', '_meta', '_limits', '_receipts', '_snapshots', '_reflections', '_versions', '_commits', '_reservations'):
        setattr(copy, name, deepcopy(getattr(memory, name)))
    return copy
