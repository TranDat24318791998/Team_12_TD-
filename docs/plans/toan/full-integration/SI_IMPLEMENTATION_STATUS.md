# Self-improvement implementation status

31/10/2026. This file records the self-improvement lane only; final integration and review are owned separately.

## Implemented

- `self-improve.v1` typed models validate the published valid and invalid examples. The deterministic compiler, artifact hash/round-trip, applied-package evidence joins, ordered policy seed, pure staging, four checked-in base assets and next-day skill selection are in `app/domain/models/skills.py` and `app/memory/`.
- `MemoryStore` and `SqliteKnowledgeStore` share validation and receipt semantics. SQLite uses the Data store and the same connection for preference confirmations and night handoff publication. The tests exercise rollback, reopen, copies, hash conflicts, concurrent claims, budget caps, terminal recovery, and skip/publication exclusion.
- Night learning freezes a cutoff, reserves one reflection, stores a terminal receipt, stages/evaluates candidates and atomically publishes through Data. The native ToolMessage and reopened Data test show later decisions consume the stored skill; OFF does not receive it. Data calibration reads prior-day durable samples and uses raw daily prediction.
- Replay has scoped semantic binding, request hashing, fail-closed misses, run-private manifest support, and no-charge fixture tests. Integrated roles now pass backend bindings where available, including Learning. No provider recording was supplied, so actual recorded-provider replay is **NOT_RUN**; a fixture replay is not a live-provider result.
- `scripts/run_sim.py` runs independent ON/OFF native Data workflows in one isolated SQLite database per pair, attaches the real comparison group, and records scoped outcomes, artifact hashes, source labels, calibration and pinned uses. It uses offline native Content plus source/placeholder assets, not paid providers.

## Verification

- `LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q tests/unit tests/integration/agents tests/integration/memory tests/integration/runtime tests/contract`: **105 passed** before the final Learning replay-context hook; focused tests after that hook: **11 passed**. Root owns the final full-suite run.
- Canonical valid/invalid wire examples, compiler/evidence fixture, frozen native Learning ToolMessage, candidate evaluation failure preserving history, daily calibration threshold/window, next-use after reopen, real Data preference rollback and skip/publication race are exercised by the new tests.
- T01–T24 are not claimed as a complete passing matrix: tests cover the above specific cases, but exhaustive policy vote/edit/eviction lifecycle, every golden A–E case, and an actual provider-recording replay still require dedicated verification. Provider evaluation is **NOT_RUN**.
- No paid model, image or video provider was called. Budget slots in each reported run are zero; offline source is not labelled live.

## Seven-day Data simulator results (seed 42)

Each report is in a Git-ignored run directory with its SQLite database, comparison group, run IDs, per-day metrics, calibration and artifact provenance. No ON-win assertion was used.

| Shop | Report | Orders ON / OFF | Profit after fees ON / OFF (VND) | Ads spend ON / OFF (VND) | Forecast MAE ON / OFF |
| --- | --- | --- | --- | --- | --- |
| D | `runs/sim-D-8984ae2c0383489faa90fa171f0090f5/comparison.json` | 57 / 58 | 1,276,752 / 1,258,888 | 270,000 / 315,000 | 3.143 / 4.714 |
| E | `runs/sim-E-0a7c0ce93ed84838b0283df696c9c269/comparison.json` | 48 / 52 | 738,624 / 662,476 | 97,200 / 243,000 | 2.714 / 3.571 |

D used the locally imported desktop-product image (the source checksum is in the report); E used a labelled simulated geometric placeholder. Both used the same source within their ON/OFF pair. D day 4 used renew v1 and day 7 used renew v3 including pause policy; E day 4 used renew v2 including pause policy. All OFF pinned bundles were version 0. Seven nightly handoffs completed in each ON run, with seven calibration samples and no learned writes in OFF. D's `/api/proof` returned HTTP 200 with five measured metrics and three comparison days from the attached pair. The seller facade remains scoped to D; E is a headless run.

The comparisons measure the combined effect of memory, not the isolated causal effect of a single skill. They were executed before the final privacy hardening and replay-context wiring; those changes have separate focused tests and did not represent live provider evaluation.

## Saved proof delivery

The measured D comparison was exported read-only from its completed source pair into the configured local Data home. The generator validates scope, completed native offline runs, settlement/handoff receipts, zero live slots, matching brief and original-asset checksum, then freezes D-only messages and supporting event projections at each settlement cursor. Private payloads and local source paths are not exported.

```sh
LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python scripts/export_demo_proof.py \
  --source-home runs/sim-D-8984ae2c0383489faa90fa171f0090f5 \
  --comparison-id group_4349d9bc018e4cdfbdc9
```

Output: `data/runtime/demo-proof.json` (ignored runtime artifact). Canonical manifest artifact SHA-256: `789ea8c917aedc474e61920e8ce01e566ac2a72ecbc8970333ee3ea96133e303`; file SHA-256: `c2bf6b7a26c4c0c0b53f30ac4c616795d4dfa5aec762287fd9f026e8739d5031`. It contains the original two run IDs, five measured metrics, three comparison days and 53/55 D-scoped ON/OFF events. Source is `precomputed_offline_simulation`; provider evaluation is `not_run`.

`LLM_MODE=offline MEDIA_MODE=offline .venv/bin/python -m pytest -q tests/integration/api/test_demo_proof.py`: **3 passed**. The tests cover source DB read-only export, post-cutoff exclusion, private/other-shop filtering, unauthorized/non-D requests, missing/tampered artifacts and no mutation of current run/events. A separate composed TestClient check using the real saved artifact returned `/api/proof/demo` 200 and current-session `/api/proof` 409 with unchanged run/event/comparison counts. Live providers were not called.
