# DB final review — current integration patch

Reviewer: Astra Max. Date: 2026-10-31. Scope: P01 in IMPLEMENTATION_PLAN, DB_REVIEW and DATA_IMPLEMENTATION_STATUS against the current uncommitted integration. This is a bounded database/integration review, not a provider or UI verdict. Only this report was written; no application source, production data or secrets were changed.

What this change does: The integration now uses Data's SQLite for business events, transactions, Knowledge publication, skill versions and call reservations. Migrations 003/004 preserve existing business rows and add the durable SI and worker state. The two defects found in the first final review have now been fixed and independently rechecked.

## Current verdict after focused re-review

**PASS for the reviewed DB scope. No unresolved finding remains from this report.** The edited-offer chain and lease fence fixes passed ten focused regression cases on temporary databases. This re-review did not change application source, call paid providers, touch the production database or rerun unchanged migration suites.

| Original finding | Current status and verified fix |
| --- | --- |
| 1 — edited proposal loses card binding | **RESOLVED.** `data/growth_data/media.py:18–45` resolves the exact approval event and checks run/shop/product/negotiation, original resolved card and edited package. `app/infrastructure/data_content.py:70–74` uses that shared resolution; facade draft/apply/campaign attribution use it too. The native regression rejects decoy negotiation/shop/run cards, completes fake Content, applies voucher2 and proves duplicate apply leaves one campaign. |
| 2 — expired lease grants media reservation | **RESOLVED.** `app/infrastructure/data_content.py:23–30` rejects null/expired leases; reserve/update/heartbeat/import/complete reach that check inside their transaction. Tests prove no slot/version/lease changes after rejection, no fake provider submit on expiry, caps survive reopen, and terminal/superseded jobs stay fenced. |

Reservation recovery was also checked: restarting with an existing reservation invokes neither model nor media provider; ambiguous accepted responses retain the same stored key/request for bounded transport retry and then become unknown, with no new attempt allowed. This distinguishes safe same-key transport retry from a new paid submission after an unknown result. The new public Content projection preserves raw feedback in the Data audit while excluding private values from native tool/media input; its focused regression passed.

Commands executed for this re-review:

```text
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_data_native.py::test_edited_approval_binds_original_card_through_content_apply \
  tests/integration/api/test_media_bridge.py::test_expired_content_lease_fences_slots_and_heartbeat \
  tests/integration/api/test_media_bridge.py::test_content_worker_never_submits_after_lease_expires \
  tests/integration/api/test_media_bridge.py::test_reserved_job_restart_never_resubmits_or_reinvokes_model \
  tests/integration/api/test_media_bridge.py::test_malformed_accepted_job_is_unknown_and_blocks_new_attempt
8 passed in 13.16s

LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_media_bridge.py::test_media_cap_survives_reopen_and_terminal_or_superseded_jobs_are_fenced
1 passed in 1.08s

LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/api/test_media_bridge.py::test_private_feedback_stays_in_audit_but_not_native_tool_or_media_request
1 passed in 3.22s
```

## Original findings — both resolved above

The evidence and reproducer below describe the pre-fix patch and are retained for audit. They are not current failures.

1. **[P1] A seller-edited offer loses its card binding when the Content worker loads it.**

   - **What this is:** Approving an edited package creates an accepted child proposal while the resolved card remains attached to the parent (`data/growth_data/service.py:387–401,415–421`). The content job correctly points to the approved child (`data/growth_data/facade.py:108–111`).
   - **Problem:** `DataContentBridge.snapshot` selects a card only where `cards.proposal_id == job.proposal_id` (`app/infrastructure/data_content.py:31–33`). The accepted child has no such card, so an authorized edit with `content_refresh=true` raises `APPROVAL_REQUIRED` before Content starts. This is the same bridge used by the native worker.
   - **Fix:** Resolve and verify the child proposal's seller approval and its original resolved card, within the same run/shop/negotiation. Persist an explicit card binding or join the approved child through its parent; do not relax approval or choose an arbitrary recent card. Check the facade's current content identity projection for the same exact-child-only assumption.
   - **If skipped:** An approved voucher edit cannot finish content generation/apply; the workflow falls back/fails despite a valid seller approval.

   Reproduced with a temporary Data app configured `content_mode='worker'`: GET state → POST day/start → read pending card → POST decision `{card_id, action:'edit', edited_package:{...card.package,voucher_pct:2}}` returns **200**; loading the resulting D job via `DataContentBridge(service).snapshot(run_id,job_id)` raises **APPROVAL_REQUIRED**.

   Required regression assertions: decision creates exactly one accepted child and one approval targeting it; bridge snapshot returns that child, its actual approval and the original resolved card; current content identity names the same original card; fake Content completes; publish activates the edited voucher2 package exactly once. A card from a different run/shop/negotiation must still fail.

2. **[P2] An expired content lease can still reserve a new paid media submission.**

   - **What this is:** `reserve_slot` atomically stores provider request/key and checks the run cap (`app/infrastructure/data_content.py:70–88`). It delegates validity to `_job` (`18–25`).
   - **Problem:** `_job` checks latest attempt, status, content and phase, but never `lease_until`. An expired job still in queued/running before recovery can get `can_submit=True`. Content immediately calls the provider when this flag is true (`app/content/service.py:112–133`). The sweeper eventually terminalizes the job; its timing is not a transaction fence.
   - **Fix:** Require a non-null, unexpired lease within the same write transaction that grants a new provider slot. Reuse that fence for slot mutations/imports which imply an active worker; do not extend an expired lease as part of reservation. Keep duplicate reservations non-granting and preserve budget slots/unknown records after expiry.
   - **If skipped:** A suspended/delayed worker can send new paid work after losing its lease, while the job is about to be rejected or timed out.

   Reproduced with an approved queued content job: set its `lease_until='2000-01-01'` in a temporary DB, then `bridge.reserve_slot(run_id,job_id,'A',{'frozen':'lease-probe'})` returns **`can_submit=True`**. No provider was called.

   Required regression assertions: expired/null lease rejects reservation without changing `provider_state_json` or counts; a valid lease grants once; same slot/hash returns can_submit false; same slot/different payload conflicts; cap remains enforced across jobs and reopen; terminal/superseded jobs cannot reserve. A fake service-level test must assert provider submit count remains zero after lease expiry.

Pre-fix reproducer used for both findings (run from repo root, `LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python`; expected failures below are historical):

```python
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from data.growth_data.api import create_app
from data.growth_data.storage import one
from app.infrastructure.data_content import DataContentBridge

for edited in (False, True):
    with TemporaryDirectory() as home:
        app = create_app(home, content_mode='worker')
        with TestClient(app) as client:
            run = client.get('/api/state').json()['run_id']
            client.post('/api/day/start', json={},
                        headers={'Idempotency-Key':'start'}).raise_for_status()
            card = client.get('/api/state').json()['pending_card']
            body = {'card_id':card['card_id'], 'action':'edit' if edited else 'accept'}
            if edited:
                body['edited_package'] = {**card['package'], 'voucher_pct':2}
            client.post('/api/decision', json=body,
                        headers={'Idempotency-Key':'accept'}).raise_for_status()
            service = app.state.service
            bridge = DataContentBridge(service)
            with service.store.connect() as c:
                job = one(c, 'SELECT * FROM content_jobs WHERE run_id=? AND shop_id=? '
                             'ORDER BY rowid DESC LIMIT 1', (run, 'D'))
            if edited:
                bridge.snapshot(run, job['job_id'])  # Pre-fix: APPROVAL_REQUIRED.
            else:
                with service.store.connect(write=True) as c:
                    c.execute("UPDATE content_jobs SET lease_until='2000-01-01' "
                              'WHERE run_id=? AND job_id=?', (run, job['job_id']))
                result = bridge.reserve_slot(run, job['job_id'], 'A', {'frozen':'lease-probe'})
                assert result['can_submit'] is True  # Pre-fix bug; now raises LEASE_EXPIRED.
```

## Confirmed improvements and passed checks

| Boundary | Evidence checked |
| --- | --- |
| Migration1→4, rollback/idempotency | `data/tests/test_integration_safety.py:19–41` passes: failed DDL keeps v1 and original schema; successful reopen records1/2/3/4. |
| Populated migration2→4 | `tests/integration/api/test_data_native.py:176–209` passes: run/shops/products/assets/metrics/negotiation/proposal/decision/campaign/grant counts retained, approval IDs retained, demo_shop defaults D, integrity ok, FK check empty. |
| Migration implementation | `storage.py:40–68` disables FK before the migration transaction, rebuilds runs via runs_new, validates FK before commit; runtime connections enable FK (`71–84`). Existing migrations001/002 are unchanged. |
| Durable authority/horizon | Data run ID and Store injected into `SqliteKnowledgeStore`; migration004 supports days1..7 and demo_shop; native lifecycle tests run against that DB and reopen. No second writable business Session in the inspected product path. |
| Close/settlement safety | Queued operation regression passes; close and settle check non-succeeded operations/running negotiations (`service.py:524–526,625–628`). Settlement fault rollback passes; prediction is inserted before actual in the same transaction (`550–569`). |
| Publication atomicity | `DataWorker.publish_night:248–268` uses one Data transaction for Knowledge commit, handoff, events and advance; `commit_night_tx` does not open another write transaction. External transaction rollback and skip/publication race tests pass. |
| Preference confirmation | `SqliteKnowledgeStore:198–270` writes through the Data connection; fault after Rules/preference rolls back decision, Rules and preference; duplicate terminal receipt checked. |
| Budget/reflection | RAM+SQLite contract tests cover concurrent cap/claim, same-ID no regrant, limit mismatch, terminal conflict, unknown recovery, copy-on-read and reopen. |
| Assets | Publish validates same-job/product ready assets plus file size/SHA before listing/campaign mutation (`media.py:149–180`). Native lifecycle missing-file regression passes. |
| Product D | Current Data seed facts/source path select the desktop fan; runtime imports a distinct supplied asset with checked bytes. Economics stay simulated. No live product claims or provider-quality inference made. |

Commands run in this review:

```text
LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  data/tests/test_integration_safety.py tests/contract/test_knowledge_repository.py \
  tests/integration/api/test_data_native.py -x
30 passed in 19.33s

LLM_MODE=offline MEDIA_MODE=offline PYTHONPATH=data .venv/bin/python -m pytest -q \
  tests/integration/memory/test_data_next_use.py \
  data/tests/test_commands_and_artifacts.py::test_failed_settlement_transaction_rolls_back_inventory
4 passed in 2.47s
```

The tests use temporary databases and fake/offline transports. A real paid provider, visible browser, runtime database mutation or secrets inspection was not used. This report does not repeat the owner's reported56-test full Data result as a newly executed result.

Verdict: **Ship for the reviewed DB scope.** Findings1/2 are resolved with the focused evidence above. The earlier34 passing migration/repository/transaction checks remain recorded here; this pass added10 focused regression cases and made no new migration claims.

Not checked: full UI/HTTP surface, provider quality, real-media playback, hosting or all possible legacy-data shapes. Those are independently reviewed; this bounded pass does not replace their verdicts.
