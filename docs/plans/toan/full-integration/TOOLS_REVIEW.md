# Tools review — Data integration

What this change does: The integration must retain the existing model → validated tool call → ToolMessage → typed finish loop while changing the source of tool data to the authoritative Data service. It needs a small read adapter and explicit DTO projections, not a replacement agent runtime.

Reviewed source: main `33fbdd5`, 31 October 2026. Scope: tools, runner, financial/privacy gates and the Data reads/calculations they consume. The separately reported orchestration, Knowledge, DB, media and HTTP work remains with its owners. Baseline 83 tests + 15 subtests is supplied by the integration coordinator; this review did not rerun that full suite.

## Keep the working protocol

- `app/agents/runner.py:169–222` preserves original AIMessage, validates a complete batch before dispatch, returns ToolMessage with the original call ID, and bounds invocations to three model calls. `_can_finish` at lines 69–114 ties package validation/forecast to the final package. Preserve these gates.
- `app/agents/tools.py:19–25,50–59,149–161` binds role/shop in backend closures and excludes scope fields from model arguments. Preserve the exact callable catalog and role matrix; do not expose Data's command API as model tools.
- `runner.py:137–164` applies typed output validation, redacted errors and a single offline fallback through the same adapters. An unavailable Data read must not silently switch to a newly seeded world or another writable Session.
- `app/domain/finance.py:15–31` and `data/growth_data/finance.py:12–19` both implement half-up integer VND contribution and half-step stop thresholds for the present fee model. Keep those semantics. The reviewed seed D at 3% is net price 169750, contribution 27136, break-even 6.255527712264151, stop 6.5.

## Must fix

### 1. P1 — Tools still read the old business state

**Evidence:** `app/agents/tools.py:54–71,97–120,123–145` reads `session.states`, `session.world`, `session.rules_version` and `session.market`. Data exposes authoritative stock/listing/rules at `data/growth_data/service.py:105–126,171–189`, with independent shop, inventory, cost and rules versions. Its context is not the tool PublicContext: it has run/product IDs, policies, metrics/history and role-selected private fields. It does not supply the current tool's active package, calendar or trend multiplier in that shape.

**Repro / current versus intended:** After Data publishes a listing or seller confirmation advances D's rules_version, invoking T01/T02 on an existing core Session still returns the old listing/rules. Merely replacing the context value with the full Data response either fails strict validation or, if validation is weakened, exposes private fields when called with an orchestrator principal. Intended: each invocation starts from a current, scoped Data snapshot; its model DTO contains only the allowlisted role fields.

**Minimal fix:** Add one infrastructure adapter bound to service, principal, run, shop and day. Build PublicContext from Data's ShopPublic plus the confirmed brief; obtain active package from the scoped active campaign's package_snapshot. Build ShopContext from only private and rules_version. Never forward the whole Data context or shared_history/recent_metrics dictionaries. Public reads use a platform_agent principal even when the worker also holds orchestrator capability. Private reads use the same shop's shop_agent principal. Capture versions internally for the orchestrator's final check, not as a model-controlled argument.

The existing `trend_multiplier` is a day-one trend factor, whereas Data `growth_7d_pct` is a trailing seven-day observation (service.py:195–199). Do not substitute one for the other. For this local simulator use the public deterministic `growth_data.simulation.trend(bound_day)` consistently with Data forecasts; calendar notes may be empty until an authoritative public calendar projection is supplied. Keep hidden market schedule/persona out of T01. Catalog remains `data/campaigns.json`; its eligibility must use Data's current stock/category/day. Data's `/campaigns` lists executed campaigns and is not the offer catalog.

**If skipped:** The visible Data run and model decisions can disagree about available stock, confirmed rules and published content even though both isolated suites pass.

### 2. P1 — T06 cannot be wired to a persisted forecast endpoint

**Evidence:** `tools.py:115–120` requires a read/compute forecast for an arbitrary proposed Package. `data/growth_data/service.py:396–413` already has the read-only `forecast_values(c,r,s,package,day)`, but it has no principal check itself. HTTP `GET forecasts` reads already persisted rows (api.py:129–158). Creating a proposal computes and persists forecasts only after private checks pass (service.py:256–299); it also advances negotiation turns and writes events. The raw forecast includes raw_daily_units, daily_point_units and calibration_version, which strict core Forecast does not accept.

**Repro / current versus intended:** `Forecast.model_validate(growth_data.simulation.forecast(D_public, package, 1))` raises extra_forbidden for raw_daily_units and daily_point_units. A direct forecast_values return adds calibration_version too. Using create_proposal to obtain a forecast would mutate negotiation before finish_platform and cannot forecast the initial 70000/10% candidate, which deliberately fails D's private rules. Intended: model T06 can preview this public candidate without creating any business object or revealing why it fails private checks.

**Minimal fix:** In the local adapter, call Data `scope` with platform_agent, verify current day equals bound day, validate the model Package, then call forecast_values on a read connection. Explicitly return only low/point/high/factor_used/stock_warning as core Forecast. Preserve the Data calibration callback and its past-day/points>=5/memory-off guards; do not also apply the old market calibration. Use neither snapshot_forecast nor create_proposal inside this tool. No new HTTP route is needed for the planned in-process local worker; a later separate-process deployment would need a scoped read-only preview endpoint with this exact behavior.

**If skipped:** Platform either falls back on every invocation, consumes a stale/different forecast, or writes turns from a supposedly read-only tool.

### 3. P1 — Data checks are not the existing validation tool contract

**Evidence:** Core T04/T05 return original/corrected packages, before/after violations, ok and changes (tools.py:78–113). Data platform checks only return public pass/checks/input_versions; shop checks return authoritative financial fields but no corrected candidate (api.py:228–236). Data wire Package rejects sub-minimum ads before its checks run (models.py:11–25). Core deliberately admits that input so T04 can correct it. Data checks also do not enforce the core's confirmed IntentBrief (validators.py:29–40).

**Repro / current versus intended:** Validating the current platform checks payload as PackageCheck produces 11 missing/extra-field errors. Passing a 5000/day candidate directly to Data CheckRequest raises validation rather than producing T04's corrected zero-ads package. Treating Data passed=true as complete validation also loses brief content/duration/ads-cap constraints. Intended: existing repair and prerequisite semantics remain, with money and inputs agreeing with Data's final authority.

**Minimal fix:** Keep `platform_side_check`, `brief_side_check`, `clamp_to_platform`, `clamp_to_rules` and before/after checking in tools.py. Feed them an authoritative Data snapshot, including current run fee policy from `fee_config`/policies; do not retain World fee defaults. Map the pinned policy's fixed/transaction/tax bps to Decimal percentages and the order fee to integer VND. Do not convert vouchers to basis points. Derive a corrected candidate first where necessary, then run Data evaluation for both business-valid original input and corrected candidate in shop scope. Merge failures into typed Violation values; never infer corrected validity merely because a clamp returned a value. Where input is wire-invalid, report core input violations and validate its repaired candidate; do not send the invalid input through Data's stricter CheckRequest and lose repair behavior.

For T05, map authoritative contribution → profit_per_unit, break_even_roas → breakeven_roas, stop_threshold → min_stop_threshold. Financials describe corrected_package when present, otherwise input_package; JSON non-finite values become null. Retain core max_voucher_for and loss_warning on the same snapshot, with parity tests against Data. Do not use private Data evaluation for T04 or expose its codes/financial values to platform. No generic pass-through Data check tool is needed.

**If skipped:** Normal corrective negotiation fails, the model can claim a brief-violating offer is checked, or the public side receives private financial limits.

### 4. P1 — The two Package models accept different stop windows

**Evidence:** `app/domain/models/packages.py:12` has stop_after_days >= 1 with no upper bound; `data/growth_data/models.py:16` requires <= 14. Neither core platform_side_check nor shop_side_check limits this field.

**Executed repro:** CorePackage validates a normal 45000/day, 3%, stop 6.5, duration 3 package with stop_after_days=15. DataPackage rejects the same object with less_than_equal at stop_after_days. This is an integration incompatibility, not a claimed regression in the already passing core baseline.

**Minimal fix:** Add `le=14` to the existing core Package field and update any package fixture that depended on a larger value. Keep business correction in validators; do not copy Data's entire model validator into core and break T04's repairable inputs. Add the single boundary test proving 14 accepted and 15 rejected before handler execution.

**If skipped:** A package can satisfy the model's terminal evidence and then fail when the workflow submits it to Data.

### 5. P1 — Privacy gates must use the same current values as private tools

**Evidence:** `app/negotiation/agents.py:54–55,62,88` uses old Session state/fees for leak_guard. `app/domain/privacy.py:44–77` derives protected amounts from those inputs. Data's secondary safe_text calls a different numeric redactor (integration.py:66–74); it does not replace the core owner-name/sensitive-phrase guard.

**Repro / current versus intended:** If T05 is switched to current Data values while reply sanitization still uses old cost/rules/fees, a model reply containing the newly calculated private contribution need not match the guard's protected amounts. Replacing leak_guard with Data redact also permits text such as the owner's name or a sensitive financial phrase without digits that core currently redacts. Intended: shop→platform/referee output, including offline fallback, is sanitized against the same authoritative snapshot that produced its private tools.

**Minimal fix:** The orchestrator supplies current public/private/fee inputs to the existing mandatory leak_guard, and the final publication gate rechecks current authority. Keep private ToolMessage transcripts local to shop; do not serialize Data private contexts or raw result bodies into public trace. Require this of the orchestration integration rather than building a second privacy framework inside runner.py.

**If skipped:** Correctly scoped private tools can still leak through the shared reply during integration.

## Executable implementation order

1. **T-INTEGRATE-1 — Bind Data reads.** Add `app/infrastructure/data_tools.py` with one concrete adapter, constructed by the orchestration owner from trusted scope. Suggested narrow interface:

   `DataToolScope(service, *, public_principal, shop_principal, run_id, shop_id, day)`

   `read_public(brief) -> PublicContext`, `read_private() -> ShopContext`, `forecast(package) -> Forecast`, and one private internal snapshot read for public/private/fees/versions used by checks and privacy. All service/connection access stays in infrastructure. The constructor's scope is never part of a model JSON schema. Read snapshots in short connections; do not hold a DB transaction over model requests. Use DataService scope before helpers that themselves lack authorization. No SQL or Principal object reaches the model.

2. **T-INTEGRATE-2 — Switch existing closures.** Add an explicit optional `data_scope=None` keyword to `bind_role_tools` for compatibility with current offline unit fixtures, and pass the bound Data adapter from the integrated worker. Production integrated invocations must require it; the None path is only the existing standalone core/test path, never an exception fallback. Replace T01/T02/T06 and the data inputs of T04/T05/catalog. Keep T03/T08 through the Knowledge owner, get_referee_context from public turns, and get_content_context through the media owner's approved facts/style context. Do not reimplement those lanes.

3. **T-INTEGRATE-3 — Align boundary and mandatory gates.** Set core Package.stop_after_days <= 14. Wire the same snapshot to privacy and final validation callers; orchestration keeps seller approval, actual Data submission, version checks and provider budgets. Preserve runner.py behavior unless a focused regression exposes an actual defect. Update `docs/plans/toan/AGENT_TOOL_KNOWLEDGE.md` only with the chosen Data authority/projection seam and `contracts/agents/*` only if model-visible values actually change; do not weaken DTO strictness.

4. **T-INTEGRATE-4 — Prove adapters with real temporary Data storage and fake model transport.** Add `tests/integration/test_data_tool_adapters.py` and a focused model-boundary assertion in the existing domain tests. Reuse existing runner fixtures. Run `.venv/bin/python -m pytest -q tests/unit/agents tests/unit/domain tests/integration/test_data_tool_adapters.py`, then the full root suite once. No provider keys or paid APIs are needed.

## Acceptance for the integrated tools

| Check | Required observation |
|---|---|
| Native round-trip | Fake AIMessage requests T01/T04/T06; the next model request includes typed ToolMessage results under the original IDs; the fake chooses its package from those results. Final changed package without matching checks/forecast falls back. |
| Fresh authority | Changing Data stock, confirmed rules or active listing before a new invocation changes the tool response; old Session/world data cannot override it. All scope IDs/day are backend-bound and cross-run/shop reads are denied. |
| Read-only tools | T01–T06/catalog dispatch does not add proposals, negotiations, approvals, campaigns, forecast snapshots, rules or paid jobs. T06 works for D's initial public 70000/10% candidate without private eligibility gating. |
| Exact money | A/B/D/E no-voucher contributions remain 48595/-4705/31625/21645; D 3% gives 27136 and stop 6.5; ads 4% fails D's 6.5 break-even rule; safe correction is 45000/3%. Corrected financials match Data evaluation and B becomes content-only. |
| Validation preservation | A 5000/day input is repaired through the tool contract; a brief-disabled-ads package is rejected/corrected despite Data public passed; corrected candidate is checked again. stop_after_days 15 is rejected and 14 is accepted. |
| Scope/privacy | Platform trying T02/T05 or any write/provider tool executes no handler. Private sentinels, owner name and exact financial values are absent from public events and platform/referee messages; no raw exception reaches ToolMessage. |
| Forecast provenance | Five-field Forecast validates; values match Data forecast_values for the same day/package and callback calibration. Changed final package requires another forecast. Memory-off uses factor 1.0 and does not call calibration provider. No future realized observations/persona enter the context. |
| Failure behavior | Failed Data read results in sanitized TOOL_FAILED; one fallback uses the same scoped adapter; persistent failure raises AgentToolError to the workflow. It does not seed another world, reset the model budget or label an offline result live. |

Verdict: fix 1–5 before declaring the tools integrated with Data. The existing native loop itself does not need a rewrite.

Not checked: full root/Data suites, live providers or UI. Executed only local, read-only DTO/finance reproductions; no source changes, commits, paid calls or secret reads. The supplied Data retry-test failure is outside this tools report.
