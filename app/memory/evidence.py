"""Build public policy facts from applied packages and seller decisions."""

from hashlib import sha256
from app.domain.models.events import Event
from app.domain.models.packages import Package
from app.domain.models.skills import EvidenceFact
from app.memory.skills import canonical_bytes


def _package(value):
    try:
        return Package.model_validate(value) if isinstance(value, dict) else None
    except ValueError:
        return None


def build_skill_facts(events: list[Event], *, run_id: str, shop_id: str, category: str,
                      day: int, through_seq: int) -> list[EvidenceFact]:
    if day < 1 or through_seq < 0:
        raise ValueError('INVALID_EVIDENCE_CUTOFF')
    selected = {}
    for event in events:
        if (event.run_id != run_id or event.shop_id != shop_id or not 1 <= event.day <= day
                or not 1 <= event.seq <= through_seq or event.data.get('source') == 'seeded'):
            continue
        prior = selected.get(event.seq)
        if prior and prior.model_dump(mode='json') != event.model_dump(mode='json'):
            raise ValueError('DUPLICATE_EVENT_SEQ')
        selected[event.seq] = event
    ordered = sorted(selected.values(), key=lambda event: event.seq)
    result = []

    def add(kind, apply, negotiation, card, package, sources):
        seqs = sorted(set(e.seq for e in sources))
        support = seqs[-1]
        source = selected[support]
        identity = [run_id, shop_id, kind, card, negotiation, apply.seq, support]
        result.append(EvidenceFact(fact_id=sha256(canonical_bytes(identity)).hexdigest(),
            run_id=run_id, shop_id=shop_id, category=category, day=source.day, kind=kind,
            negotiation_id=negotiation, card_id=card, package_applied_seq=apply.seq,
            support_seq=support, source_seqs=seqs, package=package))

    for apply in ordered:
        if apply.type != 'package_applied' or apply.actor != 'system':
            continue
        card, negotiation = apply.data.get('card_id'), apply.data.get('negotiation_id')
        package = _package(apply.data.get('package'))
        if not isinstance(card, str) or not card or not isinstance(negotiation, str) or not negotiation or package is None:
            continue
        candidates = []
        for event in ordered:
            if (event.type != 'seller_decision' or event.actor != 'seller'
                    or event.data.get('card_id') != card or event.data.get('negotiation_id') != negotiation
                    or event.data.get('action') not in ('accept', 'edit')):
                continue
            edited = event.data.get('edited_package')
            if event.data['action'] == 'edit' or edited is not None:
                if _package(edited) != package:
                    continue
            candidates.append(event)
        if not candidates:
            continue
        decision = candidates[-1]
        add('approved_package', apply, negotiation, card, package, [apply, decision])
        if decision.data.get('edited_package') is not None:
            cards = [e for e in ordered if e.type == 'card_sent' and e.actor == 'system'
                     and e.seq < decision.seq and e.data.get('card_id') == card
                     and e.data.get('negotiation_id') == negotiation]
            if cards:
                sent = cards[-1]
                finished = [e for e in ordered if e.type == 'negotiation_finished' and e.actor == 'system'
                            and e.seq < sent.seq and e.data.get('negotiation_id') == negotiation
                            and e.data.get('status') in ('agreed', 'warning_only') and _package(e.data.get('package'))]
                if finished and _package(finished[-1].data['package']).voucher_pct != package.voucher_pct:
                    add('seller_approved_voucher_edit', apply, negotiation, card, package,
                        [apply, decision, sent, finished[-1]])
        pauses = [e for e in ordered if e.type == 'auto_action' and e.actor == 'system'
                  and e.data.get('action') == 'pause_ads' and e.data.get('card_id') == card
                  and e.seq > apply.seq]
        if package.ads_daily_budget > 0 and pauses:
            add('ads_auto_paused', apply, negotiation, card, package, [apply, decision, pauses[-1]])
    return sorted(result, key=lambda f: (f.support_seq, f.kind, f.fact_id))
