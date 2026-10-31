"""Knowledge theo scope; model chỉ nhận projection, không có quyền ghi."""

import re
import unicodedata
from hashlib import sha256
from decimal import Decimal, InvalidOperation
from threading import RLock
from app.domain.models.learning import (Calibration, ContentMemoryView, KnowledgeCommit,
    LearningEvidence, MemoryCommit, PlatformMemoryView, Preference, PublicEvidence,
    PublicHistory, PublicLesson, PublicOutcome, ShopMemoryView, StoreWrite)
from app.domain.models.packages import Package
from app.domain.policies import LESSON_CAP_PER_SCOPE, PREF_ASK_THRESHOLD, PREF_DECLINE_SILENCE_DAYS
from app.domain.privacy import leak_guard
from app.infrastructure.store import StoreConflict


class MemoryGateway:
    def __init__(self, store, enabled, log=None, run_id=None, session=None):
        self.store, self.enabled, self.log, self.run_id, self.session = store, enabled, log, run_id, session
        self._learning_snapshot = None
        self._lock = RLock()

    def _ns(self, compartment, scope):
        return (self.run_id, compartment, scope)

    def _event(self, type, shop_id, data):
        if self.log and self.session:
            self.log.add(self.run_id, self.session.day, type, 'memory', shop_id, 'Bộ nhớ đã được xử lý.', data)

    def get_rules(self, shop_id):
        return self.session.states[shop_id].private.rules.model_copy(deep=True)

    def get_history(self, shop_id):
        if not self.enabled:
            return []
        return sorted(self.store.list(self._ns('history', shop_id)),
                      key=lambda x: (x.day, x.negotiation_id), reverse=True)

    def get_calibration(self, category):
        record = self.store.get(self._ns('calibration', category), category) if self.enabled else None
        return record.value if record else Calibration(category=category)

    def list_lessons(self, scope):
        if not self.enabled:
            return []
        return sorted(self.store.list(self._ns('lessons', scope)),
                      key=lambda lesson: (-lesson.score, -lesson.updated_day, lesson.lesson_id))

    def platform_view(self, shop_id, category, *, invocation_id=None):
        history = self.get_history(shop_id)[:5]
        record = self.store.get(self._ns('calibration', category), category) if self.enabled else None
        lessons = self.list_lessons('strategy')[:5] + self.list_lessons(category)[:5]
        self._event('memory_read', shop_id, {'who': 'platform', 'items': [x.negotiation_id for x in history] + [x.lesson_id for x in lessons], 'versions': {x.negotiation_id:x.version for x in history} | {x.lesson_id:x.version for x in lessons}, 'invocation_id':invocation_id})
        return PlatformMemoryView(history=history, calibration=record.value if record else None,
                                  lessons=lessons, knowledge_revision=self.session.knowledge_revision)

    def shop_view(self, shop_id, *, invocation_id=None):
        prefs = self.store.list(self._ns('preferences', shop_id)) if self.enabled else []
        evidence = [e.seq for e in self.log.since(self.run_id, 0) if e.type == 'rules_confirmed' and e.shop_id == shop_id] if self.log else []
        self._event('memory_read', shop_id, {'who': 'shop', 'items': [p.pref_id for p in prefs], 'rules_version':self.session.rules_version, 'invocation_id':invocation_id})
        return ShopMemoryView(rules=self.get_rules(shop_id), rules_version=self.session.rules_version,
                              rules_evidence_seqs=evidence, preferences=prefs,
                              knowledge_revision=self.session.knowledge_revision)

    def content_view(self, shop_id, *, invocation_id=None):
        prefs = self.store.list(self._ns('preferences', shop_id)) if self.enabled else []
        ids = [p.pref_id for p in prefs if p.status == 'confirmed' and p.field == 'content_style']
        self._event('memory_read', shop_id, {'who': 'content', 'items': ids, 'rules_version':self.session.rules_version, 'invocation_id':invocation_id})
        return ContentMemoryView(confirmed_style_notes=list(self.get_rules(shop_id).content_style_notes),
                                 rules_version=self.session.rules_version, preference_ids=ids)

    def prefs_to_ask(self, shop_id, day):
        if not self.enabled:
            return []
        prefs = self.store.list(self._ns('preferences', shop_id))
        return [p for p in prefs if p.observation_count >= PREF_ASK_THRESHOLD and
                (p.status == 'candidate' or (p.status == 'declined' and p.declined_until is not None and day >= p.declined_until))]

    def _pending_pref(self, pref_id):
        card = self.session.pending_card
        if not card or card.kind != 'question' or not card.rule_question or card.rule_question.pref_id != pref_id:
            raise ValueError('preference has no matching question')
        pref = self.store.get(self._ns('preferences', card.shop_id), pref_id)
        if not pref or (pref.field, pref.value) != (card.rule_question.field, card.rule_question.value):
            raise ValueError('preference does not match card')
        return card, pref

    def mark_asked(self, pref_id, day):
        with self.session.lock:
            card, pref = self._pending_pref(pref_id)
            if pref not in self.prefs_to_ask(card.shop_id, day) and pref.status != 'asked':
                raise ValueError('preference is not askable')
            updated = pref.model_copy(update={'status': 'asked', 'asked_day': day}, deep=True)
            return self.store.commit_batch([StoreWrite(namespace=self._ns('preferences', card.shop_id), key=pref_id, value=updated)],
                run_id=self.run_id, expected_revision=self.session.knowledge_revision,
                new_cursor=self.session.memory_cursor, receipt_key=f'ask:{card.card_id}')

    def answer_pref(self, pref_id, yes, day):
        with self.session.lock:
            card, pref = self._pending_pref(pref_id)
            key = f'answer:{card.card_id}'
            if key in self.session.knowledge_receipts:
                previous_yes, result = self.session.knowledge_receipts[key]
                if previous_yes != yes:
                    raise ValueError('question was already answered differently')
                return result
            if pref.status != 'asked':
                raise ValueError('preference was not asked')
            rules = self.get_rules(card.shop_id)
            if yes and pref.field == 'content_style':
                if pref.value not in rules.content_style_notes:
                    rules.content_style_notes.append(pref.value)
            elif yes and pref.field == 'voucher_max_pct':
                value = int(pref.value)
                if not 0 <= value <= min(30, rules.voucher_max_pct):
                    raise ValueError('invalid voucher preference')
                rules.voucher_max_pct = value
            updated = pref.model_copy(update={'status': 'confirmed' if yes else 'declined',
                         'declined_until': None if yes else day + PREF_DECLINE_SILENCE_DAYS}, deep=True)
            result = self.store.commit_batch([StoreWrite(namespace=self._ns('preferences', card.shop_id), key=pref_id, value=updated)],
                run_id=self.run_id, expected_revision=self.session.knowledge_revision,
                new_cursor=self.session.memory_cursor, receipt_key=key)
            if yes:
                self.session.states[card.shop_id].private.rules = rules
                self.session.rules_version += 1
                self._event('rules_confirmed', card.shop_id, {'pref_id': pref_id, 'rules_version': self.session.rules_version})
            self.session.knowledge_receipts[key] = (yes, result)
            return result

    def read_learning_evidence(self, day):
        if self._learning_snapshot and self._learning_snapshot.day == day:
            return self._learning_snapshot.model_copy(deep=True)
        return self.freeze_learning_evidence(day)

    def freeze_learning_evidence(self, day):
        all_events = self.log.since(self.run_id, 0)
        events = [event for event in all_events if event.seq > self.session.memory_cursor]
        through = max((e.seq for e in events), default=self.session.memory_cursor)
        shop_id = self.session.settings.demo_shop
        state = self.session.states[shop_id]
        projected, ids = [], set()
        eligible_types = {'platform_turn','shop_turn','negotiation_finished','seller_decision','package_applied','market_result'}

        def project(event):
            data = event.data
            negotiation_id = data.get('negotiation_id')
            if not negotiation_id and data.get('card_id'):
                reference = next((prior for prior in reversed(all_events) if prior.seq <= through
                    and prior.shop_id == event.shop_id and prior.data.get('card_id') == data['card_id']
                    and isinstance(prior.data.get('negotiation_id'), str)), None)
                if reference:
                    negotiation_id = reference.data['negotiation_id']
            package = None
            if isinstance(data.get('package'), dict):
                try:
                    package = Package.model_validate(data['package'])
                except ValueError:
                    pass
            raw_metrics = data.get('metrics')
            outcome = None
            if isinstance(raw_metrics, dict):
                try:
                    outcome = PublicOutcome.model_validate({k: raw_metrics[k] for k in ('orders', 'revenue', 'ads_spend', 'roas')})
                except (KeyError, ValueError):
                    pass
            text, _ = leak_guard(event.text_vi, state.public, state.private, self.session.world.fees)
            feedback = data.get('feedback_vi') if event.type == 'content_job' else None
            if feedback:
                feedback, _ = leak_guard(str(feedback), state.public, state.private, self.session.world.fees)
            return PublicEvidence(seq=event.seq, type=event.type, negotiation_id=negotiation_id,
                text_vi=text, package=package, seller_action=data.get('action') if event.type == 'seller_decision' else None,
                feedback_vi=feedback, outcome=outcome)

        for event in events:
            if event.day != day or event.shop_id not in (None, shop_id):
                continue
            negotiation_id = event.data.get('negotiation_id')
            if event.type in eligible_types and isinstance(negotiation_id, str) and negotiation_id:
                ids.add(negotiation_id)
            projected.append(project(event))
        # Older package events are context only: from_seq/cursor still identify new support.
        for history in self.get_history(shop_id):
            if history.negotiation_id not in ids or not history.approved_package:
                continue
            old_package = next((e for e in reversed(all_events) if e.seq <= self.session.memory_cursor
                and e.shop_id == shop_id and e.type == 'package_applied'
                and e.data.get('negotiation_id') == history.negotiation_id), None)
            if old_package:
                projected.append(project(old_package))
        category = state.public.category
        snapshot = LearningEvidence(day=day, from_seq=self.session.memory_cursor + 1, through_seq=through,
            events=sorted(projected, key=lambda event: event.seq),
            existing_lessons=self.list_lessons('strategy')[:5] + self.list_lessons(category)[:5],
            valid_negotiation_ids=sorted(ids), knowledge_revision=self.session.knowledge_revision)
        self._learning_snapshot = snapshot
        self._event('memory_read', shop_id, {'who': 'learning', 'items': [x.lesson_id for x in snapshot.existing_lessons], 'versions': {x.lesson_id:x.version for x in snapshot.existing_lessons}, 'invocation_id':f'{self.run_id}:learning:{day}'})
        return snapshot.model_copy(deep=True)

    def _lesson_grounded(self, op, snapshot):
        """Accept conservative facts from applied packages and settled public outcomes."""
        state = self.session.states[self.session.settings.demo_shop]
        evidence = [event for event in snapshot.events if event.negotiation_id in op.evidence]
        if not evidence:
            return False

        def tokens(value):
            value = unicodedata.normalize('NFC', value).casefold()
            result = []
            for word in re.findall(r'\d+(?:[.,]\d+)?[^\W\d_]*|[^\W\d_]+', value):
                if re.fullmatch(r'\d+(?:[.,]\d+)?', word):
                    try:
                        word = format(Decimal(word.replace(',', '.')).normalize(), 'f')
                    except InvalidOperation:
                        pass
                result.append(word)
            return result

        def pair(label, value):
            if value is None:
                return
            number = tokens(str(value))[0]
            pairs.add((label, number)); pairs.add((number, label))

        parts = [state.public.title, state.public.description, *state.public.attributes]
        pairs = set()
        for fact in parts:
            words = tokens(fact)
            pairs.update(zip(words, words[1:]))
        applied = [event for event in evidence if event.type == 'package_applied' and event.package]
        actual = [event for event in evidence if event.type == 'market_result' and event.outcome]
        text = unicodedata.normalize('NFC', op.text_vi).casefold()
        words = tokens(text)
        if re.search(r'\b(?:đã thực hiện|đã áp dụng|đã chạy|đã kích hoạt)\b', text) and not applied:
            return False
        for event in evidence:
            if event.feedback_vi and ('sáng' in event.feedback_vi.casefold() or 'tối' in event.feedback_vi.casefold()):
                parts.append('ảnh nền sáng')
        for event in applied:
            package = event.package
            parts.append(package.model_dump_json())
            for label, value in [('voucher',package.voucher_pct), ('ngân',package.ads_daily_budget),
                                 ('sách',package.ads_daily_budget), ('ngày',package.duration_days),
                                 ('ngày',package.stop_after_days), ('dừng',package.stop_roas_below),
                                 ('ngưỡng',package.stop_roas_below)]:
                pair(label, value)
            if 'ngưỡng' in words or 'dừng' in words:
                pair('roas', package.stop_roas_below)
        for event in actual:
            outcome=event.outcome
            parts.append(outcome.model_dump_json())
            for label,value in [('đơn',outcome.orders),('thu',outcome.revenue),
                                ('chi',outcome.ads_spend),('roas',outcome.roas)]:
                pair(label, value)
        # No causal uplift is established by these simulated observations.
        if re.search(r'\b(?:đem lại|mang lại|khiến|làm tăng|giúp tăng|gây ra)\b.*\b(?:đơn|doanh thu|lãi|roas)\b', text):
            return False
        context_words = [word for part in parts for word in tokens(part)]
        number_pattern = r'\d+(?:\.\d+)?'
        numbers = {word for word in words if re.fullmatch(number_pattern, word)}
        if not numbers <= {word for word in context_words if re.fullmatch(number_pattern, word)}:
            return False
        # This whitelist favors false negatives over inventing new product or outcome facts.
        neutral = set(('ưu tiên nội dung dễ đọc khi người bán có góp ý cần nên xem xét điều chỉnh '
                       'dựa trên kết quả dữ liệu học từ phản hồi trước sau phù hợp đúng mục tiêu đề xuất '
                       'gói chiến lược cửa hàng shop sàn hình ảnh rõ ràng mức độ và với cho của các '
                       'một là được theo có vì để vào lần tiếp theo dựa đã thực hiện áp dụng chạy kích hoạt dùng kinh nghiệm '
                       'đơn voucher ngân sách quảng cáo chiến dịch hiệu quả thử thay đổi ngưỡng dừng roas').split())
        if not set(words) <= set(context_words) | neutral:
            return False
        glue = {'và','với','của','cho','là','được','có','theo','trong','một','các','từ','khi'}
        words = [word for word in words if word not in glue]
        for index, word in enumerate(words):
            if not re.search(r'\d', word):
                continue
            adjacent = set()
            if index: adjacent.add((words[index-1], word))
            if index+1 < len(words): adjacent.add((word, words[index+1]))
            if not adjacent.intersection(pairs):
                return False
        return True

    def commit_memory_updates(self, batch, *, expected_revision, expected_cursor):
        with self.session.lock, self._lock:
            key = f'night:{batch.day}'
            if key in self.session.knowledge_receipts:
                old = self.session.knowledge_receipts[key].model_copy(deep=True)
                old.store.duplicate = True
                return old
            if not self.enabled:
                raise ValueError('memory disabled')
            if self.session.memory_cursor != expected_cursor or self.session.knowledge_revision != expected_revision:
                raise StoreConflict('stale knowledge snapshot')
            snapshot = self._learning_snapshot
            if not snapshot or snapshot.day != batch.day or snapshot.through_seq != batch.through_seq:
                raise ValueError('missing evidence snapshot')
            valid_ids = set(snapshot.valid_negotiation_ids)
            events = {e.seq: e for e in self.log.since(self.run_id, 0) if e.seq <= snapshot.through_seq}
            writes = []
            scoped_shop = self.session.settings.demo_shop
            for history in batch.history:
                if history.shop_id != scoped_shop or history.negotiation_id not in valid_ids or not history.evidence_seqs or any(seq not in events or events[seq].shop_id != scoped_shop or events[seq].data.get('negotiation_id') != history.negotiation_id for seq in history.evidence_seqs):
                    raise ValueError('invalid public history evidence')
                writes.append(StoreWrite(namespace=self._ns('history', history.shop_id), key=history.negotiation_id, value=history))
            for pref in batch.preferences:
                if pref.shop_id != scoped_shop or not pref.evidence_seqs:
                    raise ValueError('invalid preference')
                for seq in pref.evidence_seqs:
                    event = events.get(seq)
                    if not event or event.shop_id != pref.shop_id or not ((pref.field == 'content_style' and event.type == 'content_job' and event.data.get('feedback_vi')) or (pref.field == 'voucher_max_pct' and event.type == 'seller_decision' and event.data.get('edited_package'))):
                        raise ValueError('invalid preference evidence')
                writes.append(StoreWrite(namespace=self._ns('preferences', pref.shop_id), key=pref.pref_id, value=pref))
            for record in batch.calibration:
                if record.category != self.session.states[self.session.settings.demo_shop].public.category:
                    raise ValueError('invalid calibration category')
                if any(sample.shop_id != scoped_shop or not sample.evidence_seqs or any(seq not in events or events[seq].shop_id != scoped_shop or events[seq].type != 'market_result' or events[seq].day != sample.target_day or events[seq].data.get('prediction_id') != sample.prediction_id for seq in sample.evidence_seqs) for sample in record.samples):
                    raise ValueError('invalid calibration evidence')
                writes.append(StoreWrite(namespace=self._ns('calibration', record.category), key=record.category, value=record))
            category = self.session.states[self.session.settings.demo_shop].public.category
            state = self.session.states[self.session.settings.demo_shop]
            scopes = {'strategy', category}
            lessons = {scope: {x.lesson_id: x for x in self.list_lessons(scope)} for scope in scopes}
            accepted, rejected, changed = [], 0, {}
            for op in batch.lesson_ops:
                if op.scope not in scopes or not op.evidence or not set(op.evidence) <= valid_ids:
                    rejected += 1; continue
                _, redacted = leak_guard(op.text_vi, state.public, state.private, self.session.world.fees)
                if redacted or len(op.text_vi) > 500 or not op.text_vi.strip() or (op.op in {'ADD','EDIT'} and not self._lesson_grounded(op, snapshot)):
                    rejected += 1; continue
                bucket = lessons[op.scope]
                if op.op == 'ADD':
                    norm = ' '.join(op.text_vi.casefold().split())
                    if any(' '.join(x.text_vi.casefold().split()) == norm for x in bucket.values()):
                        rejected += 1; continue
                    lesson_id = sha256(f'{self.run_id}:{op.scope}:{norm}'.encode()).hexdigest()[:16]
                    lesson = PublicLesson(lesson_id=lesson_id, scope=op.scope, text_vi=op.text_vi,
                        score=2, evidence=list(dict.fromkeys(op.evidence)), created_day=batch.day, updated_day=batch.day, version=1)
                else:
                    lesson = bucket.get(op.lesson_id)
                    if not lesson or set(op.evidence) <= set(lesson.evidence):
                        rejected += 1; continue
                    updates = {'score': lesson.score + (-1 if op.op == 'DOWNVOTE' else 1),
                               'evidence': list(dict.fromkeys(lesson.evidence + op.evidence)),
                               'updated_day': batch.day, 'version': lesson.version + 1}
                    if op.op == 'EDIT': updates['text_vi'] = op.text_vi
                    lesson = lesson.model_copy(update=updates, deep=True)
                if lesson.score <= 0:
                    bucket.pop(lesson.lesson_id, None)
                    changed[(op.scope, lesson.lesson_id)] = None
                else:
                    bucket[lesson.lesson_id] = lesson
                    changed[(op.scope, lesson.lesson_id)] = lesson
                accepted.append(op)
            for scope, bucket in lessons.items():
                while len(bucket) > LESSON_CAP_PER_SCOPE:
                    victim = min(bucket.values(), key=lambda x: (x.score, x.updated_day, x.lesson_id))
                    del bucket[victim.lesson_id]
                    changed[(scope, victim.lesson_id)] = None
            for (scope, lesson_id), lesson in changed.items():
                writes.append(StoreWrite(namespace=self._ns('lessons', scope), key=lesson_id, value=lesson))
            commit = self.store.commit_batch(writes, run_id=self.run_id, expected_revision=expected_revision,
                                             new_cursor=batch.through_seq, receipt_key=key)
            result = KnowledgeCommit(store=commit, accepted_lesson_ops=accepted, rejected_ops=rejected)
            self.session.knowledge_receipts[key] = result.model_copy(deep=True)
            self._learning_snapshot = None
            return result
