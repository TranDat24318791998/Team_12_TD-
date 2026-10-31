# Growth Agents — Data, Access Control, Schemas, and Service API Design

Version: 1.1 • Date: 2026-10-31 • Status: final data-service design contract; not implemented

## Working agreement and compatibility

**User instruction, 2026-10-31: work directly on branch `main`; changes in this workstream must stay inside `data/`.** This supersedes the earlier `dattpq`/`db/` working arrangement. This revision changes only this document; no application code, migration, seed, deployment, or other document is changed. Record design decisions and revision notes here while that directory restriction applies.

This document specifies the data service, including concrete schemas, role projections and read/write APIs. `docs/CONTRACT.md` remains the existing UI/domain integration surface. Section 10 defines the adapter between the two interfaces: do not silently replace the nine existing demo endpoints. Existing task descriptions outside `data/` still mention six days and some older simulator conventions; the differences resolved here must be carried into their implementation together, not partially mixed. The main run is seven days; an explicitly labeled six-day compatibility report remains available.

## 1. Purpose and scope

This specification consolidates the data required for the hackathon project and defines how the Platform Agent, Shop Agent, UI, orchestrator, content service, and simulator access it.

The MVP contains five shops, one mini-fan product per shop, fourteen days of historical observations (2026-10-18 through 2026-10-31), and **seven simulated operating days** (2026-11-01 through 2026-11-07). Historical observations are initial evidence, not seven precomputed demo outcomes. The simulator generates operating-day outcomes only after approved actions. All business policies, fees, reviews, and outcomes in the seed dataset are explicitly labeled synthetic unless independently sourced and identified.

**Agent-owned memory, textual lessons, preference-learning algorithms, and forecast-calibration storage are outside this specification.** The agent team owns them. This service exposes observations, decisions, and events that those components can consume. LangGraph execution checkpoints are also owned by the orchestration service, not by the business database.

The repeated reference to “shop agent” in the request is interpreted as the two intended roles: **Platform Agent** and **Shop Agent**.

Deliverable scope: a design contract, not a deployed API, populated database, generated image collection, or completed policy PDFs. File names below identify artifacts to prepare.

## 2. Architecture and ownership

Use one authoritative relational database for each deployment. The reference implementation follows the existing Python/FastAPI architecture: SQLite on persistent storage and a filesystem object-store adapter. The preferred OpenAI-hosted storage profile is Sites D1 for relational state and Sites R2 for file bytes, exposed through a server-side data-service adapter. OpenAI Files/Vector Stores provide knowledge indexing; they are not a second authoritative business database.

`STORAGE_PROFILE=sqlite_local` is the local/reference default. `STORAGE_PROFILE=sites_d1_r2` uses the Sites data service as the sole authoritative store; Python agent/orchestration services call it over authenticated HTTPS and do not keep a writable SQLite mirror. Sites server code must use its supported Worker runtime; this design does not claim that an unmodified FastAPI/LangGraph process can be deployed there. Hosting/provider provisioning is a separate integration task, not completed by this document.

Both profiles implement the same command/query behavior, schema versions, authorization and acceptance checks. For SQLite, use short explicit transactions and connection-level foreign-key enforcement. For D1, implement atomic commands using transactional batches plus SQL conditional version checks; a failed version precondition must roll back the entire command. A Worker-local lock is insufficient across requests/isolates. Do not hold database transactions across model calls or provider polling. Verify atomic rollback and competing commands in the selected profile before exposing campaign writes.

Agents never receive database credentials, arbitrary SQL tools, simulator configuration files, or unrestricted object-storage credentials. They invoke authenticated, narrowly scoped Data API operations.

| Logical data area | Physical location in MVP | Owner | Main readers |
| --- | --- | --- | --- |
| Public catalog and published listing | Relational DB | Data API | Both agents, UI, content service |
| Shop financial data and hard rules | Restricted relational tables | Data API | Corresponding Shop Agent, seller, validator |
| Platform market observations | Relational DB | Simulator/data importer | Platform Agent; approved aggregates for Shop Agent |
| Proposals and campaign state | Relational DB | Orchestrator through Data API | Authorized participants |
| Metrics and business events | Relational DB | Simulator and command handlers | Role-filtered readers |
| Searchable reference documents | File originals plus OpenAI vector-store index | Knowledge service | Both agents, subject to collection permissions |
| Images and videos | Object storage; metadata in DB | Content service | Authorized asset endpoints |
| Hidden scenario parameters | Backend-only versioned JSON files | Simulator | Simulator only |
| Memory and execution checkpoints | Agent-team-selected storage | Agent/orchestration team | Outside this contract |

These are logical boundaries, not a requirement to deploy multiple databases or microservices. For the hackathon, modules inside one backend can implement the service boundaries.

## 3. Data preparation inventory

### 3.1 Searchable reference files

PDF is suitable for presentation; Markdown is preferable for frequently edited source material. Publish one canonical version to the search index to avoid duplicate retrieval results.

| File | Required content | Quantity | Required for MVP |
| --- | --- | --- | --- |
| `selling_policy_demo.pdf` | Truthful listings, promotion eligibility, prohibited claims, seller responsibilities, approval requirements | 1 | Yes |
| `fee_calculation_guide_demo.pdf` | Fee types, rates, calculation bases, voucher funding, rounding, worked examples, excluded costs | 1 | Yes |
| `advertising_guide_demo.pdf` | Supported campaign type, daily/total budgets, duration, CTR/CVR/CPC/ROAS definitions, pause conditions | 1 | Yes |
| `content_standards_demo.pdf` | Title/description rules, image/video constraints, factual-claim checks, review checklist | 1 | Yes |
| `product_SP001.md` through `product_SP005.md` | Verified product specifications, usage, accessories, warranty, unsupported/unknown claims | 5 | Yes |
| `mini_fan_reviews_demo.md` | Approximately 20–30 synthetic reviews with review ID, product reference, rating, date, text, and topic | 1 | Optional if persona review is cut |

Each file includes `document_id`, `document_type`, `version`, `effective_from`, `is_simulated`, source URL if applicable, and source collection date if applicable. Synthetic files display: **“Simulation material for this hackathon; not an official Shopee policy.”**

Generate product documents from verified catalog facts. Generate the fee guide from the same versioned fee configuration used by the calculator. A document explains a rule; the structured rule and deterministic validator enforce it.

Review records may live in the Markdown file for the MVP. A dedicated review table is unnecessary unless the UI needs filtering or review-level editing. Persona selection rates must be labeled simulated preferences, not measured customer CTR.

### 3.2 Seeded relational data

| Dataset | Initial quantity | Preparation rule |
| --- | --- | --- |
| Shops/products | 5 each | Stable IDs A–E and SP001–SP005 |
| Private costs and rules | 5 cost records; 5 initial rule versions | Consistent with the intended scenarios |
| Inventory | 5 rows per run | Starting inventory, no replenishment unless explicitly configured |
| Fee and platform rules | One active rule set | Same version as reference documents |
| Historical metrics | 5 × 14 × 2 channel rows = 140 | Organic and paid stored separately; baseline history has zero paid activity |
| Market observations | 14 initial daily rows for one keyword | Future observations inserted only when the simulated clock advances |
| Content versions | 5 initial approved listings | Weak but factually valid starting content |
| Assets | At least one original image per product | Initial covers may reuse original images |
| Knowledge document registry | 9 required, 1 optional document | Index only after processing succeeds |

### Historical and operating-day generation rules

- Day 1 starts with exactly the inventory and rules in section 7.2. Historical orders do not decrement that opening inventory again; inventory is an as-of-start snapshot, not an inferred lifetime ledger.
- Each historical date has organic observations generated using the initial listing and no voucher; its paid row contains zero counts/spend/revenue and null campaign/ROAS. This avoids inventing unrecorded historical campaigns or preferences. Historical rows reference the seed content, cost and fee versions, effective from 2026-10-18.
- Historical traffic uses trend index 1.0 and the same simulator formulas with signed day indices -13 through 0. Those indices are simulator-only; public history uses dates. Historical market search volume is `round(10000 * noise)` with a stable keyword/date stream; `growth_7d_pct=240` is an explicitly synthetic independent demo signal, not a claim calculated from this history.
- Seed reviews, if present, have dates no later than 2026-10-31. Public calendar information may include 11.11; realized future observations and latent parameters cannot appear in initial contexts.
- Seven operating days yield 35 shop-day settlements and 70 channel rows **per completed run**. A pair of seven-day comparison runs yields 140 operating rows, in addition to each run's historical rows. Outcome rows, campaigns, proposals and decisions start empty for operating dates.
- Historical evidence is identical in both comparison arms. Learned preferences, calibration samples and strategy lessons start empty in both arms; history is not silently used to pretrain one arm. Exclude `source=seeded` and `day<=0` from learning-effect metrics and calibration updates.
- Export a manifest containing `scenario_version`, `schema_version`, `simulator_version`, seed, history/operating date ranges, file checksums, synthetic labels and per-file access class. Mark fixtures `proof_of_learning=false`; never import them into a runtime run.

### 3.3 Runtime data, initially empty

Create tables for runs, proposals, proposal-private evaluations, decisions, campaigns, daily settlements, events, content jobs, and idempotency records. Campaigns and proposals are not prewritten outcomes. Runtime metrics append to the seeded history.

### 3.4 File assets

| Asset | Quantity | Created when |
| --- | --- | --- |
| Original product images | 1–3 per product | Seed preparation |
| Initial listing covers | 1 per product; may reuse originals | Seed preparation |
| Comparison listing images | 5 | Optional persona preparation |
| Shop D generated cover alternatives | 3 | Content workflow |
| Shop D video | 1 | Optional content workflow |
| Replay assets | All files referenced by recorded events | After a recorded run |

Keep source, generated, approved, and published states distinct. A generated file is not automatically approved or published.

### 3.5 Hidden simulator files

| File | Fields/content | Visible to agents? |
| --- | --- | --- |
| `scenario.json` | Seed, start date, day count, shop IDs, one-unit-per-order assumption, replenishment policy, version | No; only safe run metadata is exposed |
| `market_parameters.json` | Per-shop baseline traffic, latent CTR/CVR, CPC distribution, noise, response to vouchers and content | No |
| `seller_behaviors.json` | Undisclosed seller preferences and acceptance/feedback logic | No |
| `market_schedule.json` | Future trend changes, campaign calendar effects, shocks | No |

A public event calendar can be exposed if explicitly known at the start. Future realized search volumes and future shocks remain hidden.

## 4. Agent access policy

### 4.1 Authentication and scoping

A backend-issued credential resolves to `principal_id`, `role`, `session_id`, `allowed_run_ids`, `allowed_shop_ids`, and scopes. Never trust an `actor`, `role`, or `shop_id` supplied in request JSON as authorization. The server resolves identity and validates every route parameter.

For the MVP, distinct server-side service tokens mapped to these claims are sufficient. Never put agent/service tokens in browser code. Seller sessions use a separate identity. Simulator, content, and orchestration credentials are not reused as agent credentials.

Every run-scoped query filters by authorized `run_id`. Shop Agent access additionally filters by authorized `shop_id`. Composite ownership is checked for products, proposals, decisions, campaigns, documents, jobs, and assets. Return `404` for out-of-scope object IDs to avoid revealing their existence.

### 4.2 Read permissions

Legend: **R** = permitted read; **Own** = own shop only; **Filtered** = explicit safe projection; **None** = denied.

| Data / capability | Platform Agent | Shop Agent | Seller UI | Content service | Simulator / trusted backend |
| --- | --- | --- | --- | --- | --- |
| Public shop/catalog/current listing | R within run | Own; optional public comparisons | Own; public demo catalog | Assigned product | R |
| Exact current stock | R (public in existing ShopPublic) | Own | Own | None | R |
| Product cost and other unit costs | None | Own | Own | None | Validator/simulator only |
| Hard budget, margin, voucher rules | None | Own | Own | None | Validator/orchestrator only |
| Published fee/platform rules | R | R | R | Content-related rules | R |
| Raw observed market/industry data | R up to current date | None | None | None | R |
| Approved industry summary | R | R | R | Assigned brief only | R |
| Shop traffic, orders, paid spend/revenue | R within run | Own | Own | None | R |
| Cost, contribution, break-even ROAS | None | Own | Own | None | Validator/simulator only |
| Shared proposal package and negotiation reply | R for assigned negotiations | Own | Own | Approved content brief only | R |
| Private validation details | None | Own | Own | None | Validator/orchestrator only |
| Seller feedback and decision reason | Outcome + explicitly shared feedback | Own, full | Own | Content feedback only | Authorized backend |
| Published reference documents | R | R | R | Relevant collections | Knowledge service |
| Private shop documents, if later added | None | Own | Own | Only explicitly assigned product facts | Knowledge service |
| Original/generated media | Published or explicitly shared only | Own | Own | Assigned jobs | Authorized backend |
| Events | Platform-safe stream | Own safe stream | Own safe stream | Assigned content events | Role-specific internal streams |
| Hidden simulator parameters | None | None | None | None | Simulator only |
| Future observations | None | None | None | None | Simulator only |

Private derived values are also sensitive. Never expose private notes, unit contribution, costs, minimum profit or exact break-even values through platform events, errors, search snippets or traces. The **offered** daily budget, voucher and rounded stop-ROAS threshold are shared negotiation terms; publishing those terms does not publish the complete private rule object. Exact stop-ROAS values calculated from private break-even must first be rounded upward to multiples of 0.5. A private rule ceiling is not returned simply because a counteroffer happens to equal it.

Roles are `platform_agent`, `shop_agent`, `seller`, `simulated_seller`, `orchestrator`, `monitor`, `content_worker`, `simulator`, `learning_worker`, `evaluator`, `knowledge_admin`, and `data_admin`. A learning worker receives the union of explicitly authorized platform-safe and own-shop evidence for its assigned run; it cannot read seller persona or hidden future inputs. An evaluator may read financial outcomes for the authorized comparison pair to calculate aggregate proof, but exposes no per-shop private financial record to Platform Agent.

The seller's optional backstage UI is an own-shop **seller** projection, not a Platform Agent projection. It may show that seller's private evaluation; the same payload must never be reused as a model input. Browser requests use an HttpOnly, Secure, SameSite=Lax session cookie (Secure may be disabled only for localhost). Mutations check Origin/CSRF; service tokens are backend-only and checked against run, shop, operation/job assignment and scopes. Sign in with ChatGPT, when enabled by Sites, maps verified identity to the same principal model; client-supplied identity fields never authorize access.

### 4.3 Write permissions

| Operation | Platform Agent | Shop Agent | Authorized writer |
| --- | --- | --- | --- |
| Create a proposed package | Yes | Yes, as counterproposal | Data API validates identity and structure |
| Request package evaluation | Public check only | Private check for own shop | Validator calculates results |
| Accept/reject as a negotiation stance | Yes | Yes | Stored as stance; **not seller approval** |
| Approve campaign expenditure | No | No | Seller; simulated seller only in simulation runs |
| Change hard shop rules | No | No | Seller confirmation, optimistic version check |
| Apply/pause a campaign | No direct write | No direct write | Orchestrator/monitor with authorized decision or existing stop condition |
| Publish content | No | No | Seller approval followed by orchestrator |
| Write observed metrics or alter stock | No | No | Atomic simulator settlement |
| Change fees/platform policy | No | No | Data administrator |
| Write arbitrary events | No | No | Server command handlers |
| Update agent-owned memory | Outside this contract | Outside this contract | Agent team |

### 4.4 File Search boundary

Knowledge access passes through a backend tool. The backend chooses the allowed collection/vector-store IDs and filters, not the model. The initial shared collection contains public simulation policies, guides, and public product facts only. Never upload cost records, hidden scenario files, private validation traces, or private rules to that shared collection.

If private documents are introduced, use a separately authorized per-shop collection. Deny requests if identity cannot be resolved. Authorize asset downloads and document excerpts as strictly as DB rows. Validate document status/version server-side before exposing a search result. Keep revoked documents denied even while an external index is being refreshed.

## 5. Schema conventions

The following data dictionary is the normative schema proposal. It is intentionally database-neutral, not a claim that migrations have already been implemented.

- `id`: server-generated opaque string, except stable seeded shop/product codes.
- `money`: nonnegative integer VND unless explicitly a signed contribution/unit-profit value.
- `voucher_pct`: integer percent `[0,30]` on business APIs; `3` means 3%. Do not accept `300` as 3%. Public `FeeConfig` retains percentage rates 8, 5 and 1.5. Internal fee-rule rates use integer `rate_bps` (800, 500, 150) for exact arithmetic; no bps voucher wire format in this version.
- `timestamp`: UTC ISO 8601 string. Simulated business dates use Asia/Ho_Chi_Minh.
- `json`: validated JSON; SQLite may store it as TEXT. It is not an unrestricted dump of model state.
- `bool`: logical boolean, encoded as 0/1 in SQLite.
- `?`: nullable; all other fields are required unless a default is specified.
- Every mutable run-owned object has `created_at`, `updated_at`, and integer `version >= 1`; these common fields are implicit below. Immutable ledger rows need only `created_at`. Rule/cost/content/proposal version numbers are separate from mutable row versions; a reference must name the correct version kind.
- Run-scoped shop/product references use composite foreign keys, preventing cross-run links.
- Private column exclusion uses explicit allowlisted response serializers, never `SELECT *` serialization.

### 5.1 Entity schemas

| Table | Key and columns | Constraints / notes |
| --- | --- | --- |
| `runs` | `run_id PK`, `session_id`, `scenario_version`, `schema_version`, `simulator_version`, `seed`, `mode: live\|replay\|offline`, `memory_enabled bool`, `history_days=14`, `simulation_days=7`, `start_date`, `current_day int`, `phase: ready\|negotiating\|awaiting_seller\|content_review\|settling\|learning\|day_closed\|complete\|failed`, `source_run_id?`, `version`, timestamps | `1<=current_day<=simulation_days`; complete stays on final day (default 7). Safe metadata omits seed/hidden config from agent context. Reset creates a new run. |
| `shops` | `(run_id,shop_id) PK`, `name`, `category`, `description`, `status: active\|inactive`, `version`, timestamps | Five per run. |
| `products` | `(run_id,product_id) PK`, `shop_id FK`, `name`, `list_price_vnd`, `facts_json`, `listing_quality`, `search_rank_page`, `rating`, `base_impressions`, `active_content_id?`, `status: active\|inactive`, `version`, timestamps | One product per shop; quality [0,1], rank>=1, rating [0,5], impressions>=0. Active content must belong to same run/product. |
| `product_costs` | `(run_id,product_id,cost_version) PK`, `unit_cost_vnd`, `other_unit_cost_vnd`, `effective_day`, `created_at` | Immutable cost versions; effective dates cannot overlap ambiguously. Private. |
| `inventory` | `(run_id,product_id) PK/FK`, `available_units int`, `version`, timestamps | `available_units >= 0`; changes only through settlement or explicit admin initialization. |
| `shop_rules` | `(run_id,shop_id,rules_version) PK`, `allow_ads bool`, `ads_cap_daily_vnd`, `ads_cap_package_vnd?`, `voucher_max_pct int`, `min_profit_per_unit_vnd`, `max_breakeven_roas`, `require_stop_condition bool`, `minimum_campaign_stock=30`, `content_style_notes_json: list[str]`, `effective_day`, `confirmed_by`, `confirmed_at`, `confirmation_decision_id?` | Immutable version; seed uses confirmed_by=seed_admin and null decision; later versions require a seller/simulated-seller rule decision. Package cap null means no extra owner cap; approved package total always enforced. |
| `fee_rules` | `(policy_version,fee_code) PK`, `kind: rate\|fixed_per_order`, `rate_bps?`, `fixed_vnd?`, `basis: net_item_revenue\|fulfilled_order`, `category`, `effective_from`, `effective_to?`, `is_simulated` | Exactly one amount type. No policy-version mixing within a settlement. |
| `platform_rules` | `(policy_version,rule_code) PK`, `rule_type`, `parameters_json`, `severity: block\|warn`, `effective_from`, `effective_to?`, `is_simulated` | Explicit implemented rule types; no dynamic evaluation of arbitrary code. |
| `run_policies` | `run_id PK/FK`, `fee_policy_version`, `platform_policy_version`, `knowledge_release`, `created_at` | Pins shared immutable policy/document versions for reproducibility. |
| `market_daily` | `(run_id,date,keyword) PK`, `search_volume`, `qualified_listing_count`, `benchmark_cpc_vnd`, `benchmark_ctr_bps`, `benchmark_cvr_bps`, `observed_at` | Only observations available at current simulated date are readable. Industry summary is a projection. |
| `daily_metrics` | `(run_id,product_id,date,channel) PK`, `day int`, `shop_id`, `channel: organic\|paid`, `campaign_id?`, `content_id`, `impressions`, `clicks`, `orders`, `units`, `net_revenue_vnd`, `ad_spend_vnd`, `fees_vnd`, `cogs_vnd`, `other_cost_vnd`, `contribution_vnd signed`, `rounding_adjustment_vnd signed`, `realized_roas?`, `fee_policy_version`, `cost_version`, `settlement_id?`, `source: seeded\|simulated`, `created_at` | Paid realized_roas=revenue/spend; organic null. day=-13..0 historical, 1..7 operating. One paid campaign/product/day; private financial columns omitted for Platform Agent. |
| `assets` | `(run_id,asset_id) PK`, `shop_id?`, `product_id?`, `kind: image\|video\|document`, `object_key`, `mime_type`, `size_bytes`, `sha256`, `width?`, `height?`, `duration_seconds?`, `origin: supplied\|generated`, `source_reference?`, `visibility: shop_private\|published\|internal`, `created_at` | Images/videos require matching shop/product; run reports are internal documents with null product. No inline binary/base64; no permanent public URL for private files. |
| `content_versions` | `(run_id,content_id) PK`, `product_id`, `content_version`, `parent_content_id?`, `title`, `description`, `cover_options_json`, `video_job_json`, `feedback_history_json`, `style_notes_json`, `cover_asset_id?`, `video_asset_id?`, `quality_gain=0.25`, `published_day?`, `validation_json`, `status: draft\|validated\|approved\|published\|rejected\|superseded`, `created_at` | Unique (run,product,content_version); one draft holds options A/B/C, not three colliding content versions. Freeze chosen ready assets at approval; retain old versions for undo. Seed content has quality_gain=0. |
| `knowledge_documents` | `(document_id,document_version) PK`, `type`, `title`, `collection_scope: shared\|shop_private`, `owner_run_id?`, `owner_shop_id?`, `source_object_key`, `provider_file_id?`, `vector_store_id?`, `index_status: pending\|ready\|failed\|revoked`, `effective_from`, `effective_to?`, `is_simulated`, `source_url?`, `source_collected_at?`, `checksum`, `knowledge_release` | Private collection requires both owner fields; shared requires neither. Registry admin-only; agents receive safe metadata/excerpts, not provider IDs. |
| `proposals` | `(run_id,proposal_id) PK`, `negotiation_id FK`, `shop_id`, `product_id`, `parent_proposal_id?`, `proposal_version`, `author_role`, `round`, `package_json`, `forecast_id?`, `shared_reason`, `stance: propose\|accept\|reject\|withdraw`, `status: submitted\|validated\|awaiting_seller\|accepted\|rejected\|superseded\|expired\|applied`, `based_on_rules_version?`, `created_at`, `updated_at` | Package immutable after submit; amendment creates new ID. Round counts Platform Agent turns, not all rows. At most three platform turns per negotiation. |
| `proposal_private_evaluations` | `(run_id,proposal_id,evaluation_version) PK`, `rules_version`, `cost_version`, `inventory_version`, `fee_policy_version`, `passed bool`, `violations_json`, `unit_contribution_vnd`, `break_even_roas?`, `evaluated_at` | Never included in Platform Agent projection. |
| `decisions` | `(run_id,decision_id) PK`, `shop_id`, `target_type: proposal\|content\|rule_question`, `target_id`, `target_version`, `action: approve\|reject\|request_changes`, `edited_package_json?`, `cover_option?: A\|B\|C`, `rule_answer? bool`, `actor_type: seller\|simulated_seller`, `actor_id`, `feedback_private?`, `feedback_shared?`, `created_at` | Target ownership/existence checked in command transaction. No agent approval. Edited package creates a checked child proposal and approval bound to that child; original seller edit remains in audit. |
| `campaigns` | `(run_id,campaign_id) PK`, `shop_id`, `product_id`, `proposal_id`, `approval_decision_id`, `package_snapshot_json`, `start_day`, `end_day`, `approved_total_vnd`, `spent_vnd`, `low_roas_streak`, `status: active\|completed\|cancelled`, `ads_status: disabled\|running\|paused\|ended`, `ads_stop_reason?`, `version`, timestamps | One active package/product. Ads pause does not end voucher or undo content. `end_day=start_day+duration_days-1`; no replacement/resume that increases spend without new approval. |
| `content_jobs` | `(run_id,job_id) PK`, `shop_id`, `product_id`, `proposal_id`, `attempt`, `brief_json`, `feedback_history_json: list[str]`, `style_notes_json: list[str]`, `input_asset_ids_json`, `provider`, `provider_job_id?`, `cache_key`, `status: queued\|running\|succeeded\|failed\|timed_out`, `output_content_ids_json`, `fallback_used bool`, `error_code?`, `lease_until?`, timestamps | Three total versions: initial + two retries. Unique (run,proposal,attempt); one current running attempt. Cache includes shop/run, source checksums, prompt, model/config version. Provider results for superseded attempts never replace current draft. |
| `day_settlements` | `(run_id,settlement_id) PK`, `shop_id`, `day`, `input_snapshot_hash`, `status: committed`, `created_at` | Unique `(run_id,shop_id,day)`; atomic effect once. |
| `events` | `(run_id,seq) PK`, `day`, `type`, `actor_role`, `shop_id?`, `entity_type`, `entity_id`, `visibility: shared\|shop_private\|platform_private\|internal`, `payload_json`, `text_vi`, `recorded_at`, `simulated_at` | Append-only, server-authored; monotonic seq allocated per run inside command transaction. Gaps after filtering are allowed. Visibility is intersected with run/shop/job ownership, never permission by itself. |
| `idempotency_records` | `(principal_id,run_scope,method,path,key) PK`, `request_hash`, `status: processing\|completed`, `operation_id?`, `lease_until?`, `response_status?`, `response_json?`, timestamps | run_scope=run_id or session_id for POST /runs. Same command returns original result; different body under key returns 409. Retain records for run lifetime. |

Additional required tables (same conventions):

| Table | Key and columns | Constraints / ownership |
| --- | --- | --- |
| `shop_runtime` | `(run_id,shop_id) PK`, `cooldown_until_day=0`, `seller_renegotiations=0`, `active_negotiation_id?`, `pending_card_id?`, `version`, timestamps | Reject day d blocks new offers until day d+3; at most two seller-requested renegotiations per day. |
| `negotiations` | `(run_id,negotiation_id) PK`, `shop_id`, `day`, `kind: propose\|renew`, `attempt`, `platform_rounds`, `status: running\|agreed\|failed\|warning_only`, `final_proposal_id?`, `warning_vi?`, timestamps | Unique(run,shop,day,attempt); final proposal must belong to negotiation. |
| `forecasts` | `(run_id,forecast_id) PK`, `proposal_id`, `product_id`, `as_of_day`, `period_start_day`, `period_end_day`, `method_version`, `raw_daily_units_json: list[float]`, `daily_point_units_json: list[int]`, `point`, `low`, `high`, `factor_used`, `stock_warning bool`, `assumptions_json`, `input_fingerprint`, `created_at` | Server-calculated, immutable snapshot. No future simulator noise in inputs. Explicit daily/period grain for calibration and evidence. |
| `rule_questions` | `(run_id,question_id) PK`, `shop_id`, `external_pref_id`, `field: voucher_max_pct\|content_style`, `value_json`, `text_vi`, `based_on_rules_version`, `status: pending\|answered\|expired`, `answer? bool`, `decision_id?`, `created_at` | Agent memory owns candidate learning; Data API owns confirmation audit. Changing rules consumes an affirmative exact-version answer. |
| `cards` | `(run_id,card_id) PK`, `shop_id`, `day`, `kind: offer\|question`, `proposal_id?`, `question_id?`, `forecast_id?`, `reasons_json`, `warnings_json`, `notices_json`, `status: pending\|resolved\|superseded`, `version`, timestamps | Offer requires validated proposal; question-only requires question and no package. Only one pending card per interactive shop. Financial display calculated into own-seller projection, never platform projection. |
| `operations` | `(run_id,operation_id) PK`, `day`, `kind: start_day\|close_day\|advance_day`, `status: queued\|running\|succeeded\|failed`, `result_json?`, `error_code?`, `lease_until?`, timestamps | Unique(run,day,kind); retries reuse operation and committed substeps. |
| `learning_handoffs` | `(run_id,day) PK`, `settlement_cursor`, `status: pending\|running\|completed\|failed\|skipped`, `night_summary_json?`, `memory_report_asset_id?`, `error_code?`, timestamps | Completion envelope only, no preferences/lessons/calibration store; worker owns learning state. |
| `comparison_groups` | `group_id PK`, `session_id`, `run_on_id`, `run_off_id`, `scenario_version`, `simulator_version`, `seed`, `days`, `report_version`, `created_at` | Both runs authorized and same initial dataset/hash, code/model/prompt configuration except learning flag. |

For metrics, `rounding_adjustment_vnd` reconciles per-unit profit rounding with separately rounded fee totals (section 7.1). For assets, add required `upload_status: pending|ready|failed`; `object_key` is assigned by server and bytes become usable only at ready. Optional metadata dimensions and duration are nonnegative. Do not infer missing product dimensions/brand from generated images.

For shared fee/policy tables, the run pins versions instead of duplicating rows. All mutable shop state is cloned into a new run. No seed changes overwrite an existing run.

### 5.2 Indexes and integrity rules

Create indexes for events `(run_id,seq)` and `(run_id,shop_id,seq)`, proposals `(run_id,shop_id,status)`, metrics `(run_id,shop_id,date)`, content `(run_id,product_id,content_version)`, jobs `(run_id,status)`, and market `(run_id,date,keyword)`.

Check integer counts are nonnegative, `clicks <= impressions`, `orders <= clicks`, and `units = orders` under the MVP assumption. Organic ad spend is zero. Paid metrics without ad spend are permitted only if explicitly modeled as free clicks; default simulator does not generate them. All derived metrics handle zero denominators with null.

The server checks same-run foreign references and enum values. In SQL, a product's shop reference is `(run_id,shop_id)`; a metric's product reference is `(run_id,shop_id,product_id)` backed by a matching unique parent key. Proposal/campaign/content/asset references must also match their run, shop and product. Polymorphic decision targets require a checked lookup inside the command transaction. Enforce one active campaign/product and one pending card/shop with a database uniqueness constraint, not only a pre-read check. Scope event allocation, idempotency and operation ownership to the same transaction as business writes. SQLite foreign-key enforcement must be enabled on each connection. Database-level constraints complement API authorization.

## 6. Shared payload schemas

### 6.1 ProductFacts

A validated object with `brand?`, `model?`, `colors: list[str]`, `dimensions_mm? {width,height,depth}`, `battery_capacity_mah?`, `power_w?`, `speed_levels?`, `included_items: list[str]`, `warranty_months?`, and `verified_claims: [{claim_id,text_vi,source_reference}]`. Unknown values remain null or absent, lists default empty; do not invent a warranty, brand, accessories or dimensions. Seed D facts are exactly 3 speeds, USB charging, 2000mAh, and White/Pink/Mint colors. Title/description derive only from approved facts. The content agent may not infer an unrecorded noise level or battery-runtime guarantee.

### 6.2 GrowthPackage

```json
{
  "content_refresh": true,
  "ads_daily_budget": 45000,
  "voucher_pct": 3,
  "stop_roas_below": 6.5,
  "stop_after_days": 2,
  "duration_days": 3
}
```

This wire object is exactly the existing domain `Package`: all fields required, with `stop_after_days=2` as the model default; `stop_roas_below` may be null only when ads are disabled. Daily budget is a nonnegative integer (zero or >=10000); `duration_days` is 2–14, default scenario 3; voucher is integer percent 0–30 and subject to shop/finance limits. `stop_after_days` is 1–14; if set, `stop_roas_below` is finite and positive. Reject a package with no content, ads or voucher. The server derives immutable approved maximum spend as `ads_daily_budget * duration_days`, checks any additional owner package cap, and stores it in `campaigns.approved_total_vnd`. Requests cannot override that derived amount. Content generation costs are excluded from business contribution and disclosed separately. A final-day package may extend beyond day 7, but proof counts only settled operating days; do not claim the full package forecast has been evaluated at day 7.

### 6.3 Forecast

```json
{
  "forecast_id": "fc_D_1",
  "period_start_day": 1,
  "period_end_day": 3,
  "metric": "total_fulfilled_units",
  "low": 18,
  "point": 22,
  "high": 26,
  "raw_daily_units": [6.0, 8.0, 8.0],
  "daily_point_units": [6, 8, 8],
  "factor_used": 1.0,
  "stock_warning": false,
  "as_of_day": 1,
  "method_version": "forecast-v1",
  "assumptions": ["No stock replenishment", "One unit per order"]
}
```

Example values illustrate the shape, not guaranteed outcomes. Bounds and point are nonnegative integers, `low <= point <= high`, period length equals package duration, and `sum(daily_point_units)=point`. They describe total fulfilled units, not incremental lift. `raw_daily_units` contains uncalibrated nonnegative finite forecasts of that same daily grain; no realized future noise. Apply factor, inventory cap and deterministic allocation of rounding so daily points sum exactly to period point. Before five calibration points, factor=1 and low/high use 0.7/1.3 of raw period forecast; after that the agent-owned calibration provider supplies a versioned factor/quantiles. Store those supplied values and input fingerprint in the immutable forecast snapshot.

Only the code forecast service creates these numbers. Proposal requests do not accept a model-authored forecast object. The service computes a fresh forecast after final validation and after edits; public `Forecast` is projected to `{low,point,high,factor_used,stock_warning}`. Raw/daily snapshots are available to the authorized learning/evaluation worker, not future simulator outcomes. UI numbers remain displayed in Vietnamese; no uncalibrated statistical-confidence claim.

### 6.4 CheckResult

`passed: bool`, `checks: [{code, passed, severity, message}]`, `evaluated_at`, `input_versions`. Public checks cover structure and platform policy. Private checks additionally include cost/margin, inventory and shop limits. A shared response can say `SHOP_CONSTRAINT_NOT_SATISFIED` without revealing private numeric thresholds. Private financial detail is returned only to the authorized shop and seller.

### 6.5 Event

```json
{
  "seq": 12,
  "run_id": "run_demo_01",
  "day": 1,
  "type": "platform_turn",
  "actor_role": "platform_agent",
  "shop_id": "D",
  "entity_type": "proposal",
  "entity_id": "prop_003",
  "visibility": "shared",
  "text_vi": "Agent sàn gửi một đề xuất tăng trưởng.",
  "payload": {"proposal_id": "prop_003", "stance": "propose"},
  "recorded_at": "2026-10-31T04:00:00Z",
  "simulated_at": "2026-11-06T09:02:00+07:00"
}
```

Events reference canonical entities instead of duplicating unrestricted private objects. Shared text passes leak_guard; no raw private reasoning or complete private entity is serialized. Detailed checks generate separate shop-private events. Canonical types retain existing `day_start`, `opportunity`, `memory_read`, `platform_turn`, `shop_turn`, `code_check`, `card_sent`, `seller_decision`, `auto_action`, `content_job`, `content_applied`, `market_result`, `memory_write`, `night_summary`. Added lifecycle types are `day_closed`, `learning_completed`, `rules_confirmed`, `forecast_created`, `operation_failed`; these are internal unless a safe projection is defined. Type/writer combinations are allowlisted. For legacy Event, actor is projected by type: platform_turn/opportunity->platform_agent, shop_turn->shop_agent, code_check->code, seller_decision->seller, content_job->content_agent, market_result->market, memory_read/memory_write/night_summary->memory, other legacy types->system. The server authorizes the actual writer independently; a projected actor is not a credential. Map payload to data, and recorded_at to HH:MM in Asia/Ho_Chi_Minh. Internal lifecycle events stay outside the legacy public stream.

### 6.6 Exact context and content DTOs

All DTOs forbid extra fields. Nullability is explicit; arrays are typed, not arbitrary model JSON.

| DTO | Fields and types |
| --- | --- |
| `ShopPublic` | `shop_id:str`, `name:str`, `category:str`, `price:int`, `stock:int`, `listing_quality:float[0,1]`, `search_rank_page:int>=1`, `rating:float[0,5]`, `base_impressions:int>=0`, `title:str`, `description:str`, `attributes:list[str]`, `images:list[str]`, `video:str\|null`, `active_voucher_pct:int[0,30]` |
| `ShopRules` | `allow_ads:bool`, `ads_daily_max:int>=0`, `voucher_max_pct:int[0,30]`, `min_profit_per_unit:int>=0`, `max_breakeven_roas:finite float>0`, `require_stop_condition:bool`, `content_style_notes:list[str]` |
| `ShopPrivate` | `owner_name:str`, `unit_cost:int>=0`, `rules:ShopRules`; never returned in a PlatformContext |
| `RuleQuestion` | `pref_id:str`, `field:voucher_max_pct\|content_style`, `value:str`, `text_vi:str`; voucher value must parse to whole percent 0–30, style value is a nonempty string <=200 chars |
| `CoverImage` | `option:A\|B\|C`, `status:running\|done\|failed\|cached`, `asset_id:str\|null`, `path:str\|null`, `prompt:str`; failed fallback must be labeled and may reference the original ready asset |
| `VideoJob` | `status:pending\|running\|done\|failed\|cached`, `asset_id:str\|null`, `path:str\|null`, `job_id:str\|null`, `prompt:str`, `error:str\|null` |
| `ContentDraftResult` | `content_id:str`, `content_version:int>=1`, `title:str<=120 chars`, `description:str<=5000 chars`, `images:list[CoverImage]` containing exactly A/B/C, `video:VideoJob`, `feedback_history:list[str]`, `style_notes:list[str]`, `checks:list[str]` |
| `DayMetrics` | `shop_id:str`, `day:int`, `impressions:int>=0`, `clicks:int>=0`, `orders:int>=0`, `revenue:int>=0`, `ads_spend:int>=0`, `roas:finite float>=0\|null`, `fees:int>=0`, `profit_after_fees:signed int`; aggregate projection, not a mutable simulator input |
| `OperationView` | `operation_id:str`, `kind:start_day\|close_day\|advance_day`, `day:int`, `status:queued\|running\|succeeded\|failed`, `result:object\|null` with route-defined safe shape, `error:{code,message}\|null`; never return internal stack traces |

DTO paths are backend-authorized media routes, not provider credentials or raw private object keys. Legacy CoverImage/VideoJob omit the added asset_id; legacy ContentDraft uses the current proposal's attempt number as version and adds shop_id. Proposal checks return the corrected package only in shop-authorized scope; the Platform Agent sees a public failure code, not private financial calculations. Counteroffer package terms are shared after leak_guard and normal turn validation.

For `content_candidates` in a worker result, accept exactly one ContentDraftResult for that attempt. Text validation checks factual claims against facts_json, not just number matching. Once content is approved/published, its text/selected assets are immutable; later media output can be registered but cannot silently change the published listing. A new publication requires a new version and approval. A retry creates a new draft; older attempts cannot overwrite it. Attempt number is per proposal (1–3); content_version is monotonic per product across renewals and may exceed 3.

## 7. Business calculations and seed scenarios

### 7.1 Explicit assumptions

One item per order; no returns, shipping subsidy, additional unit costs, replenishment or platform-funded voucher in the MVP. The fee configuration is the existing synthetic 8% fixed fee + 5% transaction fee + 1.5% assumed tax on net item revenue, plus 3000 VND/order. All fees and effects are simulation assumptions, not verified platform terms. Pin fee version `demo-fees-v1`: rate rules 800/500/150 bps and fixed_per_order rule 3000 VND. Additional unit costs are schema capacity only and initially zero.

Use Decimal/exact rational arithmetic; never binary floats for money. Vouchers are whole percents; all seeded prices produce whole-VND net prices at supported vouchers. For future prices, first round net unit price half-up to integer VND. Final per-unit contribution rounds half-up as in the seed examples; aggregate fee totals round half-up separately. Record the resulting reconciliation explicitly:

```text
net_unit_price = round_half_up(list_price_vnd * (100 - voucher_pct) / 100)
unit_contribution_before_ads = round_half_up(
    net_unit_price * (1 - 1450/10000) - 3000 - unit_cost - other_unit_cost)
channel_net_revenue = fulfilled_units * net_unit_price
channel_fees = round_half_up(channel_net_revenue * 1450/10000 + fulfilled_units * 3000)
channel_cogs = fulfilled_units * unit_cost
channel_other_cost = fulfilled_units * other_unit_cost
channel_contribution = fulfilled_units * unit_contribution_before_ads - channel_ad_spend
rounding_adjustment = channel_contribution - (
    channel_net_revenue - channel_fees - channel_cogs - channel_other_cost - channel_ad_spend)
realized_ROAS = paid_net_revenue / paid_ad_spend, or null if spend = 0
break_even_ROAS = net_unit_price / unit_contribution_before_ads, or null if contribution <= 0
stop_threshold = ceil(break_even_ROAS * 2) / 2
```

The legacy field `profit_after_fees` maps to summed contribution and is described as excluding unmodeled operating costs. Do not call it full accounting profit. `realized_ROAS` is attributed revenue efficiency, not causal incremental return. Canonical Data API `roas` and the demo's `DayMetrics.roas` use this realized paid-channel ratio. The old task's `cvr * unit_price / CPC` is a simulator expectation, not realized ROAS; keep it simulator-only as an optional diagnostic and never use it interchangeably in stopping/proof. This is an explicit simulator-integration change; expected exact daily ROAS in older task tests must be rechecked with the channel simulator.

When contribution <=0, JSON break-even is null with `unprofitable=true`; internal finance may use infinity but must never serialize Infinity/NaN. Block voucher/ads on loss-making products; allow content-only with a private warning even if the minimum-profit rule cannot be met at the current price. If `allow_ads=false`, zero ads are required. Otherwise cap daily ads, require approved stop conditions, enforce minimum unit profit, maximum break-even ROAS and stop_threshold; clamp may reduce spend/discount or tighten stopping, never raise approved spending.

### 7.2 Seed values

| Shop | Product | Price VND | Cost VND | Initial stock | Ads/day cap | Extra package cap | Voucher cap % | Minimum unit contribution | Scenario |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A | SP001 | 189000 | 110000 | 400 | 100000 | null | 10 | 30000 | Healthy economics, weak listing |
| B | SP002 | 129000 | 112000 | 250 | 0 | null | 5 | 12000 | Negative contribution; allow_ads=false |
| C | SP003 | 159000 | 95000 | 15 | 80000 | null | 10 | 25000 | Fails minimum campaign stock of 30 |
| D | SP004 | 175000 | 115000 | 300 | 45000 | null | 8 | 18000 | Finance limits voucher to 3% when ads enabled |
| E | SP005 | 99000 | 60000 | 350 | 50000 | null | 5 | 15000 | Low paid ROAS demonstrates automatic ad pause |

Seed shop names/owners, rating=4.6 and listing facts match `docs/SEED_DATA.md`. Quality/rank/base-impressions are A=.45/3/3000, B=.35/4/2000, C=.40/3/1500, D=.55/3/2500, E=.50/2/2200. All shops except B allow ads; maximum accepted break-even ROAS is 6.5, require_stop_condition=true, style notes initially empty. Minimum campaign stock is 30. D's initial title/description/attributes are exactly those in SEED_DATA; other shops use the same mini-fan facts without inventing brands or warranties.

Initial platform proposal: content refresh, 70000 VND/day ads, voucher 10%, stop ROAS below 4 for two days, duration 3. Financial acceptance examples must remain: A profit without voucher 48595; B -4705; D 31625; E 21645. D at 3% has net price 169750, unit contribution 27136, break-even about 6.26 and rounded stop 6.5; A at 10% rounds stop to 5.5; E at 5% rounds stop to 5.5. These validate finance, not guaranteed realized order counts.

Hidden seller persona: A edits offered voucher 10% to 5%; D requests a brighter image unless style notes already mention brightness. D has **no hidden 3% voucher preference**: 3% is the financial constraint under ads. B receives a loss warning and a content-only offer, not paid promotion. Seed persona is stored only in simulator configuration, not in shared product documents or agent contexts.

### 7.3 Simulation contract

The simulator consumes applied packages, published content, inventory, costs and pinned fees. It produces two channel rows for every settled shop-day, including zero rows. Version `market-v1` retains existing traffic/quality/CPC inputs and adds explicit channel attribution; it does not introduce per-arm reward changes. Future input noise is backend-only. No observed runtime row is inserted before that day settles.

Use `random.Random(f"{seed}:{day}:{shop_id}:{kind}")`; kinds include `impr` and `cvr` as in existing tasks. The run pins scenario/simulator version; changing formulas requires a new version. `noise=exp(gauss(0,0.10))`, trend is `1.12**(min(day,7)-1)` for operating dates. CTR=.015+.02*q; CVR=min(1,(.03+.03*q+.002*voucher_pct)*noise_cvr). Round impressions from base_impressions*trend*(.5+q)*noise_impr; organic clicks=round(impressions*CTR). Effective quality gains .25, capped .95, the day after approved content publication; it persists while that content is published, does not stack on repeated refresh and does not expire with the ad package. Undo restores the published version's quality effect.

At day start use existing stock and past observed orders only. Pause ads if stock<30 or, once three completed operating days exist, stock<3*mean(orders over those three days); stock zero prevents any spend. With running ads, paid_clicks=floor(min(daily_budget,remaining_total)/1800), paid_impressions=ceil(paid_clicks/CTR), spend=paid_clicks*1800. This explicitly allows underspend of less than one CPC; no invented paid clicks without spend. Organic demand=round(organic_clicks*CVR), paid demand=round(paid_clicks*CVR); allocate available stock to organic first, then paid. This fixed allocation order and rounding use the same implementation in both arms. Counts remain orders<=clicks<=impressions. The simulator charges actual click spend even when later fulfillment is stock-limited.

At day end, any day with paid spend>0 is a qualifying day; zero conversions gives realized ROAS 0, not null. Below approved threshold increments the streak; at/above resets; no spend leaves streak unchanged. Reaching stop_after_days pauses ads **before the next day's spend**. Remove the earlier unapproved 20-click minimum, which could disable stopping on small budgets. Stopping ads does not remove voucher or published content. At end_day, expire the voucher/package; ads are ended, content stays published. Never auto-resume paused ads or auto-renew spend. A renewal requires a new checked proposal and seller approval.

## 8. HTTP API contract

### 8.1 Common rules

Base path: `/api/v1`; internal routes use the separately listed `/internal/v1` prefix, never `/api/v1/internal/v1`. JSON responses use UTF-8. Authentication is mandatory for versioned business routes; `/health` is public. For the anonymous hackathon demo, legacy GET /api/state or POST /api/reset may bootstrap an opaque seller session and its first run, scoped only to DEMO_SHOP; subsequent calls use that cookie. A bootstrap cannot request another session's run or impersonate another shop. An installation requiring Sign in with ChatGPT disables anonymous bootstrap and issues the same seller session only after verified sign-in. The team routes below are not OpenAI provider endpoint names.

- Mutating requests require `Idempotency-Key` and `X-Request-ID`.
- Commands changing an existing mutable entity require `expected_version`; creates/immutable result appends instead carry the exact parent/target versions stated in their route. Stale updates return 409. Unknown fields are rejected rather than ignored.
- Run and shop ownership is checked even when a resource ID is valid.
- The API server derives actor identity. Unknown request fields are rejected.
- Query lists accept `limit` (default 50, maximum 100) and an opaque `cursor`.
- Historical filters are inclusive `from_date`/`to_date`; future dates are rejected.
- Knowledge filters and requested collection names can narrow access, never expand it.
- Safe successful response: `{"data": ..., "meta": {"request_id": "..."}}`.
- List response additionally has `meta.next_cursor` and, for observations, `meta.as_of_date`.
- Error: `{"error":{"code":"VERSION_CONFLICT","message":"Object changed; reload and retry","request_id":"...","details":{}}}`. Details are role-filtered.

Error `message` and displayed validation messages are Vietnamese; stable machine `code` values remain English. Lists are ordered by stable server keys; cursors bind run, filters and principal and cannot expand authorization. A create command that has no run yet scopes idempotency by session. Invalid identity fails before any idempotency record is disclosed. An in-flight duplicate returns 202 with the same operation/job reference (or 409 `COMMAND_IN_PROGRESS` for a short synchronous command); it never starts a second effect. A worker lease is 120 seconds, renewed during long provider jobs. Recovery first inspects committed effects/provider job ID before retrying an expired lease; a crash cannot leave commands permanently `processing`. Do not retry paid provider submissions blindly after an unknown response.

| HTTP status | Meaning |
| --- | --- |
| 200 | Read or completed command |
| 201 | Resource created |
| 202 | Job accepted; poll returned job URL |
| 400 | Malformed request |
| 401 | Invalid/missing identity |
| 403 | Role cannot perform this operation |
| 404 | Missing or inaccessible object |
| 409 | Version/idempotency/state conflict |
| 422 | Well-formed request violates schema/business rule |
| 429 | Rate/concurrency limit |
| 503 | Dependency temporarily unavailable |

### 8.2 Run and state endpoints

| Method/path | Caller | Input | Result / behavior |
| --- | --- | --- | --- |
| `GET /health` | Any | None | Service health only; no secrets/configuration |
| `POST /runs` | Seller session or orchestrator | `scenario_version`, `seed?=42`, `mode: live\|replay\|offline`, `memory_enabled=true`, `simulation_days?=7` | 201 safe run; clones seed state and initial history. Accept 6 only for explicitly labeled compatibility runs; other day counts outside this design return 422. Server assigns session ownership. |
| `GET /runs/{run_id}` | Authorized session/services | None | Safe run metadata, phase, current day |
| `POST /runs/{run_id}/reset` | Owning seller session | `expected_version` | 201 new run; old run retained; no global reset |
| `GET /runs/{run_id}/state` | Seller or orchestrator | `shop_id` | Own catalog, pending cards, active campaign, content jobs, latest event cursor |
| `POST /runs/{run_id}/days/start` | Seller trigger/orchestrator | `expected_day`, `expected_version` | 202 operation job; opens negotiations for current day once |
| `POST /runs/{run_id}/days/close` | Seller trigger/orchestrator | `expected_day`, `expected_version` | 202 operation; settles all five shops once, emits day_closed, starts learning handoff, exposes completion/failure via operation |
| `POST /runs/{run_id}/days/advance` | Orchestrator | `expected_day`, `expected_version` | Advances only after all settlements and completed/skipped learning; final day sets complete without creating day 8 |
| `GET /runs/{run_id}/operations/{operation_id}` | Authorized requester | None | Status, safe result or error of day operation |

Operation records are defined in section 5.1 and owned by orchestration, not agent memory. Day-start completion without any interactive offer/question moves directly to a state that can close; it must not wait forever for a nonexistent card. Closing with unresolved cards or an unapplied current draft returns 409. Seller rejection resolves the card and permits close. At final day still complete the learning handoff before marking complete. Seed values and hidden config are never supplied by the browser as an arbitrary uploaded scenario; scenario_version must identify an installed dataset.

### 8.3 Read/context endpoints

| Method/path | Caller | Parameters | Response projection |
| --- | --- | --- | --- |
| `GET /runs/{r}/shops` | Platform Agent | `eligible_only?`, pagination | Public catalog, exact public stock, eligibility/reason; no private costs/rules |
| `GET /runs/{r}/shops/{s}/products` | Both agents, seller | Pagination | Public facts and current published content |
| `GET /runs/{r}/shops/{s}/context` | Both agents | None | Role-selected PlatformContext or ShopContext; caller cannot choose role |
| `GET /runs/{r}/shops/{s}/inventory` | Own Shop Agent/seller | None | Product, exact available units, inventory version |
| `GET /runs/{r}/shops/{s}/costs` | Own Shop Agent/seller | `as_of_day?` | Effective private cost version |
| `GET /runs/{r}/shops/{s}/rules` | Own Shop Agent/seller | None | Effective hard rules and version |
| `GET /runs/{r}/policies` | Both agents/content | `type?` | Pinned public fee/platform rules and versions |
| `GET /runs/{r}/market/observations` | Platform Agent | Keyword, dates, pagination | Observed market rows only |
| `GET /runs/{r}/market/summary` | Both agents | Keyword, dates | Approved aggregate demand trend and category benchmarks |
| `GET /runs/{r}/shops/{s}/metrics` | Both agents/seller | Dates, `channel?: organic\|paid\|all`, pagination | Platform: day/date/channel, impressions, clicks, orders, units, net revenue, ads spend, realized ROAS and source. Own shop/seller: additionally costs, fees, contribution, rounding adjustment and effective financial versions |
| `GET /runs/{r}/events` | Authorized roles | `after_seq`, `limit` | Authorized events ordered by seq, plus next scanned cursor |
| `GET /runs/{r}/shops/{s}/history` | Both agents | Dates, pagination | Authorized proposals, decisions and outcomes for agent-owned learning |

PlatformContext is an allowlisted object `{run_id,day,shop:ShopPublic,eligibility:{eligible,reason_codes},policies,market_summary,recent_metrics,shared_history}`. ShopContext is `{run_id,day,shop:ShopPublic,private:{owner_name,unit_cost,rules:ShopRules},inventory_version,cost_version,rules_version,policies,market_summary,recent_metrics,shared_history,pending_rule_questions}`. Neither includes persona, future outcomes, hidden noise, private model reasoning or another shop's private data. Shop context has no raw platform-internal market rows. Initial memory is not silently merged into either object; agent memory owner supplies its own permitted views separately.

`all` metrics return channel rows, not an implicit sum; `DayMetrics` aggregation sums counts/revenue/spend/fees/contribution across channels and uses **paid revenue / paid spend** for ROAS. Historical queries cannot go past the current observed cutoff. At day d before settlement, operating metrics stop at d-1; day d becomes visible only after settlement. Public market observations for d become available at start_day(d). Exact current inventory comes from current state, not a historical metrics sum.

Event polling scans raw sequence rows after after_seq up to its scan bound, then filters by authorization. Return `meta.next_cursor` as the last **scanned** seq, even if no visible event was found, and `meta.has_more`. Do not use the last visible event as the scan cursor. Fix an upper bound at request start; fetch the next page for newer events. For the legacy facade, return that same cursor as last_seq. Cursor gaps reveal no event body or private entity ID.

### 8.4 Negotiation, validation and approval endpoints

| Method/path | Caller | Request fields | Response / side effect |
| --- | --- | --- | --- |
| `POST /internal/v1/runs/{r}/shops/{s}/negotiations` | Orchestrator only | `day`, `kind:propose\|renew`, `expected_shop_version`, `owner_note_vi?`, `source_card_id?` | 201 negotiation; server sets attempt/round state, enforces eligibility/cooldown and seller-renegotiation limits. Owner note is shop-private. |
| `POST /runs/{r}/shops/{s}/checks` | Both agents | `product_id`, `package: GrowthPackage` | 200 role-specific CheckResult; no applied business change; computed values come from code |
| `POST /runs/{r}/shops/{s}/proposals` | Both agents | `product_id`, `negotiation_id`, `parent_proposal_id?`, `package: GrowthPackage\|null`, `shared_reason`, `stance` | 201 immutable proposal; server assigns author/round and computes checks/forecast; package required for propose/accept, null allowed for reject/withdraw |
| `GET /runs/{r}/proposals/{p}` | Participants/seller | None | Shared projection; own Shop Agent/seller also sees authorized private evaluation |
| `POST /runs/{r}/proposals/{p}/present` | Orchestrator | `expected_version` | Sets awaiting_seller after fresh checks, creates pending offer card; optionally attaches earliest pending own-shop rule question |
| `POST /runs/{r}/decisions` | Seller or scoped simulated seller | `target_type`, `target_id`, `target_version`, `action`, `edited_package?`, `cover_option?`, `rule_answer?`, `feedback_private?`, `feedback_shared?` | 201 immutable decision; target-specific validation below; approve binds exact version |
| `PUT /runs/{r}/shops/{s}/rules` | Seller or scoped simulated seller | `rules: ShopRules`, `expected_rules_version`, `confirmation_decision_id` | Creates immutable rules version from affirmative pending question answer; invalidates stale checks, never silently modifies approved campaign terms |
| `POST /runs/{r}/campaigns/apply` | Orchestrator only | `proposal_id`, `approval_decision_id`, `expected_inventory_version`, `expected_rules_version` | 201 campaign, or 409/422; revalidates and commits atomically |
| `POST /runs/{r}/campaigns/{c}/pause` | Seller/orchestrator/monitor | `expected_version`, `reason_code` | 200 paused campaign; monitor must cite approved stop rule and observed evidence |
| `GET /runs/{r}/shops/{s}/campaigns` | Both agents/seller | Status, pagination | Shared package/status; private evaluation excluded from platform |

Stance `accept` means agreement between agents, not permission to spend. It must refer to the current parent and identical package; otherwise it is a new propose/counter row. The server enforces turn order and at most three **platform turns**, allowing a shop response in each turn. A seller-requested renegotiation opens a new negotiation attempt, limited to two per day/shop. An agent cannot create an unrelated negotiation to bypass that limit. Shared messages always pass leak_guard before persistence in shared form.

Decision rules: proposal approve may contain an edited_package; code checks it before creating an immutable child and binding approval to the child. Record the edit, original proposal and decision for preference learning. Proposal request_changes records feedback and opens the next permitted negotiation; it grants no spend. Content approve names one exact content candidate; publication is a separate orchestrator command. A rule_question accepts only approve/reject, no edited package; rule_answer must agree with the action. No proposal/content decision may write rules without a separate pending question and its answer. Questions can be answered while a package remains active; they do not create or renew a campaign.

Confirmed rules apply immediately to future checks; before the next spend, the monitor may pause ads if a tightened rule disallows the existing package, with evidence recorded. Raising a ceiling never raises spend or resumes ads automatically. The sole confirmation route initially supports learned voucher/style changes; general manual editing of other rules is outside the MVP. ShopRules uses existing domain names from section 10; internal column mapping is exact, including allow_ads/max_breakeven_roas/require_stop_condition/content_style_notes.

At start_day, a shop already running a package receives a question-only card if it has a pending confirmation and no offer. This uses the same card/decision services as present, not a fake package. The orchestrator chooses at most the earliest pending question per shop/day; unanswered questions remain pending. Platform-side opportunity eligibility uses public trend/category, stock>=30, listing_quality<0.6 or rank>=2, no active package and no cooldown. Renewal is allowed when a previous package ends even after content has improved quality; do not accidentally suppress renewal by treating it as a first-time listing-quality match.

### 8.5 Knowledge and media endpoints

| Method/path | Caller | Request | Result |
| --- | --- | --- | --- |
| `POST /runs/{r}/knowledge/search` | Both agents/content | `query`, `document_types?`, `product_id?`, `top_k` 1–10 | Authorized excerpts, scores, document IDs/versions, source references |
| `GET /runs/{r}/knowledge/documents/{d}` | Authorized reader | `version` pinned to run release | Safe metadata and authorized content/download mechanism |
| `POST /runs/{r}/shops/{s}/content-jobs` | Orchestrator or seller after package approval | `proposal_id`, `product_id`, `input_asset_ids`, `feedback_vi?`, `expected_current_attempt?` | 202 job ID/current draft; initial attempt=1, two retries maximum; current draft remains available while media is pending |
| `GET /runs/{r}/content-jobs/{j}` | Assigned content service, own seller/orchestrator | None | Job status and output content IDs |
| `POST /internal/v1/runs/{r}/content-jobs/{j}/result` | Assigned content worker | `expected_job_version`, `status`, `provider_job_id?`, `content_candidates?`, `fallback_used?`, `error_code?` | Monotonic job updates; accepts a new validated output version only once, rejects conflicting terminal results; records facts/assets validation |
| `GET /runs/{r}/shops/{s}/content` | Own Shop Agent/seller/content service | Product, pagination | Authorized content versions |
| `POST /runs/{r}/content/{id}/publish` | Orchestrator | `approval_decision_id`, `expected_active_content_id` | Publishes exact approved version atomically, retains previous content |
| `POST /runs/{r}/assets/uploads` | Content worker/seller; learning worker for assigned report | `product_id?`, `kind:image\|video\|document`, `mime_type`, `size_bytes`, `sha256` | Returns `{asset_id,upload:{method,url,headers,expires_at}}`; server-assigned object key, exact run/shop/job permissions |
| `POST /runs/{r}/assets/{a}/complete` | Upload owner/content worker | Checksum | Marks usable only after server verifies stored object |
| `GET /runs/{r}/assets/{a}/download` | Authorized reader | None | Short-lived access URL or streamed bytes; no storage credentials |

Undo publishes a previously validated version through a new explicit seller approval; it does not delete history. Content-job completion never publishes automatically. For upload processing, `assets` additionally tracks `upload_status: pending|ready|failed`, with ready assets required in content candidates.

Allow JPEG/PNG/WebP images up to 10 MiB, MP4 video up to 50 MiB, and Markdown/PDF documents up to 10 MiB. Verify type from bytes, checksum and actual size; reject mismatch with 422 and do not mark ready. Private upload/download links expire after five minutes; a link does not confer access to other object keys. A local adapter streams through an authenticated route; a hosted adapter may use a scoped signed URL or authenticated stream. Pending uploads expire after one hour and can be cleaned up; record deletion only after confirming no published/replay reference. Do not garbage-collect replay-referenced assets. Product images/videos require product_id; learning reports use null product and internal visibility. User-supplied filenames are metadata, never filesystem paths.

Knowledge writes are administrator-only:

| Method/path | Caller | Request | Result |
| --- | --- | --- | --- |
| `POST /internal/v1/knowledge/documents` | knowledge_admin | `document_id`, `document_version`, `type`, `title`, `collection_scope`, `owner_run_id?`, `owner_shop_id?`, `source_object_key`, `checksum`, `knowledge_release`, `effective_from`, `effective_to?`, `is_simulated`, `source_url?`, `source_collected_at?` | 202 immutable version plus indexing job reference; verify source ownership; no model-selected vector store |
| `POST /internal/v1/knowledge/documents/{d}/revoke` | knowledge_admin | `document_version`, `reason_vi` | Immediate server-side deny; remove external index association asynchronously |

Indexing retries use the same document checksum/version; ready is set only after provider processing succeeds. Offline search uses the canonical locally available Markdown documents with deterministic keyword search and labels the backend `local`; it must not claim vector search occurred. In replay, use recorded authorized excerpts; a miss may use that local search without a paid call. Hidden config and cost/rule records are never ingested as shared documents. Agents have no ingestion/revoke endpoints.

### 8.6 Internal simulation and evidence endpoints

| Method/path | Caller | Input | Output |
| --- | --- | --- | --- |
| `POST /internal/v1/runs/{r}/shops/{s}/settle-day` | Simulator/orchestrator | `day`, `expected_inventory_version`, `input_snapshot_hash` | Single committed settlement: metrics, stock, campaign spend, stop state, events |
| `GET /runs/{r}/proof` | Authorized seller/demo evaluator | Comparison group ID | Aggregated metrics and simulation labels; scoped to authorized runs |
| `POST /internal/v1/runs/{r}/replay/export` | Demo administrator | None | Sanitized replay manifest, events, entity snapshots, referenced asset IDs |

### 8.7 Learning and forecast handoff APIs

These APIs carry evidence and confirmations; they do not implement or own the agent team's memory store.

| Method/path | Caller | Input | Output / effect |
| --- | --- | --- | --- |
| `POST /internal/v1/runs/{r}/shops/{s}/rule-questions` | Assigned learning worker | `external_pref_id`, `field`, `value`, `text_vi`, `based_on_rules_version` | 201 question; deduplicate active question by external_pref_id; no rule mutation |
| `GET /runs/{r}/shops/{s}/rule-questions` | Own Shop Agent/seller/orchestrator | `status?`, pagination | Own questions and confirmation outcomes; Platform Agent has no access |
| `GET /internal/v1/runs/{r}/learning-input` | Assigned learning worker | `day` | Only after all settlements for day; safe shared evidence plus own-shop authorized financial/decision/content evidence, raw/daily forecast snapshots, input versions, event cursor; no persona/noise |
| `POST /internal/v1/runs/{r}/learning-results` | Assigned learning worker | `day`, `settlement_cursor`, `status:completed\|failed`, `night_summary`, `memory_report_asset_id?`, `error_code?` | Once-only completion envelope, validates cursor/day/asset ownership; conflicting result 409; does not write learned memory or confirm rules |
| `GET /runs/{r}/shops/{s}/forecasts` | Platform Agent/own shop/seller | `proposal_id?`, pagination | Shared period/daily forecast snapshots needed for explanations; no private financial data |

`night_summary` retains existing NightSummary `{day,history_updates:list[str],pref_candidates:list[str],calibration:{factor:float,points:int,mape_today:float|null},lesson_ops:list[LessonOp],rejected_ops:int,memory_md_path:str}`. A LessonOp is `{op:ADD|UPVOTE|DOWNVOTE|EDIT,lesson_id:str|null,text_vi:str,scope:str,evidence:list[str]}`. This is a summary of work already committed by the memory owner; Data API stores it only as a handoff envelope and role-filters before exposure. `memory_md_path` is an authorized report endpoint, not an arbitrary path. Never place raw chain-of-thought in the summary. The worker persists its own last processed evidence cursor so retries do not double-learn.

For rule-question answer, seller decision creates confirmation evidence; the command handler can invoke the same rules-update service in its transaction. Return the question ID and resulting rules_version. Agent memory consumes that outcome to mark its candidate confirmed/declined; it cannot invent a confirmation ID. If rules changed since the question was asked, return 409 and regenerate the question from current rules. A declined candidate cannot be asked again for 14 operating days. The memory owner enforces that interval; Data API additionally rejects the same external_pref_id during that window using confirmation history. Pref IDs must remain stable for a shop/field/value to avoid bypassing silence.

The internal settle command calculates from stored approved state and hidden simulator parameters; agents cannot submit arbitrary metric values. Proof is computed from DB records, not hand-authored winning numbers. Comparison group metadata is evaluation-service-owned and links two authorized run IDs with the same scenario/seed and distinct memory settings.

### 8.8 Worked request sequence

```http
POST /api/v1/runs/run_demo_01/shops/D/proposals
Authorization: Bearer <shop-D-service-token>
Idempotency-Key: d-day1-counterproposal-1
X-Request-ID: request-001
Content-Type: application/json
```

```json
{
  "product_id": "SP004",
  "negotiation_id": "D-1-attempt1",
  "parent_proposal_id": "prop_002",
  "package": {
    "content_refresh": true,
    "ads_daily_budget": 45000,
    "voucher_pct": 3,
    "stop_roas_below": 6.5,
    "stop_after_days": 2,
    "duration_days": 3
  },
  "shared_reason": "Đề xuất quảng cáo 45.000đ/ngày và voucher 3%.",
  "stance": "propose"
}
```

```json
{
  "data": {
    "proposal_id": "prop_003",
    "proposal_version": 1,
    "status": "validated",
    "shop_id": "D",
    "round": 1
  },
  "meta": {"request_id": "request-001"}
}
```

The orchestrator presents prop_003. The authenticated seller approves `target_type=proposal`, `target_id=prop_003`, `target_version=1`. The orchestrator applies it using that decision ID and fresh inventory/rules versions. A second identical apply request returns the same campaign, not a second campaign.

## 9. Transaction and lifecycle rules

### 9.1 Apply campaign

In one short transaction: verify identity and idempotency, load exact approved proposal, verify seller decision, recheck rule/cost/policy/inventory versions, ensure no conflicting active package, enforce budgets, insert campaign, mark proposal applied, append safe events, and persist the command result. Fail without partial effects. Enforce unique(run_id,proposal_id) and unique(run_id,approval_decision_id) for campaign creation, so a new idempotency key cannot spend twice. The approved package and the financial versions used for its check are immutable evidence; changing a proposal or rules after approval requires a fresh check and, for changed package terms, a new seller approval.

For MVP simplicity, replacement campaigns start on the next unprocessed day. Never switch paid campaigns midway through a day. This preserves the one-paid-campaign-per-product/day metric grain.

### 9.2 Settle day

Lock/serialize the shop-day write, confirm it has not settled, load the approved input snapshot, compute results deterministically, insert both channel metric rows, decrement inventory by fulfilled units, update total ad spend and ads stop/package completion state, insert settlement and events, and commit together. The canonical input hash includes scenario/simulator version, seed/day, cost/fee/rule versions, starting inventory version, applied package ID/terms/spend, published content/version and its effective quality. Server computes the hash; supplied hash is a consistency assertion, not a client-authored outcome. A duplicate settlement with the same hash returns the original result; a different hash returns 409. On replay of an already committed command, return stored result before comparing the now-decremented inventory version; concurrent stale **new** commands still fail.

A run close is a durable operation over five individually atomic settlements. It is not a transaction held across learning/provider work. Retry skips already committed settlements and cannot close/advance until all five exist. After the fifth settlement, append day_closed exactly once and create the learning_handoff. A restart resumes incomplete operations from stored status/leases. Data persistence alone does not resume a LangGraph interrupt: orchestrator must persist its own checkpoint or reconstruct the pending card from canonical state before accepting a new seller decision.

### 9.3 Content lifecycle

`queued -> running -> succeeded|failed|timed_out` describes jobs. `draft -> validated -> approved -> published` describes content. Asset readiness and content approval are separate. Failed/timed-out generation may reuse an explicitly identified fallback asset, never silently claim new generation succeeded.

### 9.4 Day lifecycle and learning handoff

`ready -> negotiating -> awaiting_seller -> content_review -> settling -> learning -> day_closed -> next day ready`.

Skip awaiting_seller/content_review when no corresponding work exists. Resolve pending cards and explicitly approve/reject the current draft before close. After all settlements, emit `day_closed` as an evidence boundary while phase becomes learning; the event does not itself advance the clock. The orchestrator **must** wait for completed learning before advance. Memory-off runs create a skipped envelope with an empty NightSummary and perform no preference/history/calibration/lesson writes; initial hard rules and stop mechanisms remain active. A learning job failing after 60 seconds is marked failed with a safe event; the orchestrator may record skipped with that failure reason and continue using the last committed memory. Any partial learning writes must be idempotent in the memory owner's store and recorded as such; never report them as an empty successful night. Data API exposes no general /memory CRUD endpoint.

### 9.5 Replay

Replay events and snapshots are immutable. Playback has a per-session cursor. Only prerecorded branches are faithful playback. An unsupported new seller decision forks an authorized **offline** run from the last matching state (source_run_id plus checkpoint seq), returns its new run_id, and continues with code fallback; never continue incompatible prerecorded future events and never start paid live calls automatically. If a fork snapshot is unavailable, return 409 `REPLAY_FORK_UNAVAILABLE` with a reset-to-offline action, without mutating the recording. The legacy adapter updates its own sid-to-run mapping after a fork. Record actual LLM outputs, model/prompt versions and safe input fingerprints; a fixed simulator seed alone does not reproduce LLM output.

### 9.6 Evidence and comparison calculations

The evaluator creates a comparison group only after checking matching seed, history hashes, policies, simulator/model/prompt versions, initial hard rules, initial learned-memory state and operating horizon. Both arms have the same safeguards, seller behavior and exogenous noise; memory_enabled must not enter reward/traffic formulas. Generate both offline runs deterministically; use recorded model outputs for repeatable LLM replay. An interactive seller run is not automatically comparable to an automated-seller run.

`GET /runs/{r}/proof?group_id=<id>&variant=full_7d|legacy_6d` returns `{seed,days,run_on,run_off,metrics:[{key,label_vi,better,on,off,unit}],note_vi}` within the standard data envelope. Default full_7d has days=7; legacy_6d truncates evidence at day 6 and says so in note_vi. Only include committed `source=simulated` operating outcomes; no historical or fixture rows. Metric definitions are:

| key | Direction / unit | Definition |
| --- | --- | --- |
| first_round_accept | higher / % | 100 * agreed-or-warning_only negotiations finalized on platform round 1 / all finalized negotiations on days 4–6; failed negotiations stay in denominator |
| seller_edit_rate | lower / % | 100 * offer decisions with edited_package / resolved offer cards on days 4–6; question-only cards excluded |
| forecast_mape | lower / % | 100 * mean(abs(saved daily point - fulfilled units)/fulfilled units) over active-package shop-days 4–6 with actual>0; use latest forecast issued no later than that day's start and covering that day, never reforecast from observed outcomes |
| wasted_ads | lower / VND | Sum actual paid spend on days 1–report horizon whose realized paid ROAS is below the private break-even calculated from that day's applied voucher/cost/fee versions |
| seller_profit | higher / VND | Sum channel contribution after ads, fees, costs and rounding reconciliation across all five shops on days 1–report horizon; excluded operating costs disclosed |

No denominator or no evaluable forecast produces null in v1 on/off values, not 0 or a fabricated win. The legacy ProofReport expects numeric values: omit an undefined metric pair from its metrics list and explain the omission in note_vi, never coerce null to zero. Report skipped zero-actual/missing-forecast counts in note_vi. Persist daily raw/point forecast snapshots; calibration uses actual/raw for the exact same shop-day when raw>0 and the observation was available. Period forecasts are evaluated only after their full period settles; do not compare a three-day point to one day's sales. Weighted campaign ROAS is sum(paid revenue)/sum(paid spend), not mean of daily ratios. The first three metrics deliberately retain the existing days 4–6 evaluation window; day 7 contributes to full-horizon financial totals and can be shown separately in UI. Never tune hidden parameters by arm or replace losing measured results with fixture numbers.

## 10. Existing demo API adapter and ownership

### 10.1 Compatibility contract

Keep the existing unversioned `/api/*` routes as a seller-session facade, backed by the exact same query/command services as `/api/v1` (no second database or bypass validation). The browser sends no service token, role or arbitrary shop credential. The facade resolves sid, current run and DEMO_SHOP=D server-side. The new v1 API retains its envelope; the facade returns the existing bare response shapes and `{"error":{"code","message_vi"}}` errors. No UI contract is silently replaced by the versioned service interface.

| Existing endpoint | Existing request / response | Data-service mapping |
| --- | --- | --- |
| POST /api/reset | `{memory?:bool,seed?:int}` -> `{run_id,day:1,mode,state}` | Create/reset owned run with simulation_days=7; retain old run; reset is never global |
| GET /api/state | None -> StateView | Project current run, pending card, draft, active package, last NightSummary and live call budget to own seller |
| POST /api/day/start | None -> `{day,step}` | Start current day once; return immediately while operation runs |
| GET /api/events?after=N | None -> `{events,last_seq}` | Own-seller event projection, legacy names/fields and scanned cursor |
| POST /api/decision | `{card_id,action:accept\|negotiate\|reject\|edit,note_vi?,edited_package?,rule_answer?}` -> `{step,card?}` | Resolve pending card, exact-version decisions, optional separate rule answer, validated child for edit, apply command for accepted package |
| POST /api/content/retry | `{feedback_vi}` -> `{draft:ContentDraft}` | Retry current proposal; text ready, image/video running as applicable; version means attempt 1–3 |
| POST /api/content/apply | `{cover_option:A\|B\|C}` -> `{listing:ShopPublic}` | Create exact content approval with selected ready cover, then publish atomically |
| POST /api/night | None -> `{summary:NightSummary,next_day:int\|null}` | Close/settle, await learning envelope (max 60 seconds), advance once; day 7 returns next_day=null and complete |
| GET /api/proof | None -> ProofReport | Default authorized full_7d report; optional variant=legacy_6d for a labeled six-day comparison |

`StateView` fields remain `{run_id,day,mode:live|replay|offline,memory_enabled,step,demo_shop:ShopPublic,demo_shop_original:ShopPublic,active_package:ActivePackage|null,pending_card:Card|null,content_draft:ContentDraft|null,last_night:NightSummary|null,live_calls_left:int}`. Additive final step value `complete` is the explicit day-7 extension. Map ready->idle, negotiating->negotiating, awaiting_seller->awaiting_decision, content_review->content_review, settling/learning->day_done (night is in progress; disable repeat night action), day_closed->night_done, complete->complete. After a successful night/advance, state day is next_day and step=idle while last_night remains available. Do not return night_done as if another night settlement could run for the same day.

`Card` remains `{card_id,shop_id,day,kind:offer|question,package:Package|null,forecast:Forecast|null,profit_after_fees_per_unit:int|null,breakeven_roas_display:float|null,reasons_vi:list[str],warnings_vi:list[str],notices_vi:list[str],rule_question:RuleQuestion|null}`. Financial fields are own-seller only. Question-only cards contain null package/forecast/financial fields and never apply a campaign. For an offer with a question, record separate decisions and rule confirmation before rechecking/applying the package; answering No to the question does not reject an otherwise approved offer. `ActivePackage` is `{package,start_day,end_day,ads_paused,card_id}` mapped from campaign/package state. `demo_shop_original` is the immutable opening listing, not the previous version overwritten on each day.

Legacy ContentDraft uses `version=content_job.attempt` (1–3), never the global content_version. It contains title/description/images/video/feedback_history/style_notes/checks and shop_id as in CONTRACT; asset_id stays internal. `night_summary.memory_md_path` is an authorized report route. On a successful run final day, callers must handle next_day=null and step=complete; no day-8 market or campaign spend is generated. These final-day additions require corresponding frontend handling when implemented.

Mutations through the facade require an Idempotency-Key header from the frontend; payload bodies otherwise stay compatible. X-Request-ID may be generated server-side if absent. For older clients without a key, derive one only for commands bound to an existing exact card/day/draft version using session/run/action/body hash. Reset and new content retries must have a client-generated explicit key (missing key returns 400 IDEMPOTENCY_KEY_REQUIRED), because the server cannot safely distinguish a network retry from an intentionally new reset/retry by body alone. Safeguards also enforce unique resolved-card/approval/settlement effects, so browser retries cannot apply twice even under a different key. Frontend captures the target version/attempt when a command starts and reuses its key until a terminal response. V1 remains strict about explicit headers for all mutations.

### 10.2 Mode and failure behavior

- offline: code-only agents/forecast/simulator, original or cached media, local knowledge; zero paid network calls.
- replay: read caches/recordings without needing API keys; missing calls use code/local fallback or an explicit offline fork, not automatic live spending.
- live: provider calls only with configured credentials and session budgets (40 LLM calls, three video jobs); when exhausted, continue with replay/offline fallback and log the reason.
- `LLM_MODE=auto` resolves to live only with credentials; missing credentials do not turn explicitly requested replay into offline. Record resolved mode and each fallback in events.
- Media worker failure uses identified original/replay assets and marks failed/cached honestly. Missing knowledge indexing falls back to canonical local documents. Failure must not publish unapproved content or increase spending.

### 10.3 Responsibility matrix

| Component | Reads | Writes/commands | Does not own |
| --- | --- | --- | --- |
| Data/API owner | Seed and policy configuration | Schema, authorization, transactions, projections, query APIs | Agent prompting/memory |
| Platform Agent | PlatformContext, public knowledge, shared negotiations | Proposals and public checks | Private financial access, seller approval |
| Shop Agent | ShopContext, own private checks, public knowledge | Counterproposals and private checks | Direct rule changes or campaign apply |
| Orchestrator | State, safe checks, decisions | Run/day lifecycle, present/apply, content jobs | Unrestricted seller approval |
| Content service | Assigned facts, assets, brief, content policy | Generated assets and draft results | Price/cost mutation, publication approval |
| Simulator | Applied state, private costs, hidden parameters | Atomic day settlement | Choosing better outcomes for memory-enabled runs |
| UI | Authorized state/events/cards/assets | Seller decisions and rule confirmations | Service credentials, arbitrary DB access |
| Agent memory owner | Scoped history and outcomes | Its own memory/checkpoints | Changes to this DB without a documented command |

## 11. Minimum acceptance checks

1. Platform credentials cannot obtain costs, margin, exact rules, private feedback or private document excerpts through any endpoint or event.
2. Shop D credentials cannot read or mutate another shop's private records, including by guessing object IDs.
3. Future market observations and hidden simulator files are unavailable to both agents.
4. A model-supplied role or actor field cannot override authenticated identity.
5. No campaign can be applied without an exact-version seller approval and fresh code checks.
6. Duplicate apply, content-result, and settle-day commands have one business effect.
7. Stock never becomes negative; spend stays within daily and total approved budgets.
8. Zero-ad-spend ROAS is null; private break-even values never appear in platform projections.
9. Product claims and fee calculations match their canonical structured versions.
10. Closing the same day twice cannot create duplicate metrics or advance the clock twice.
11. Reset affects only the requester's session/run; recorded runs survive reset and restart.
12. Comparison arms use the same simulator, initial hard rules and stop mechanism. Only the learning configuration differs.
13. Every generated asset and document can be traced to a source or a simulation/generation label.
14. Event polling after authorization filtering does not repeat or skip authorized new events; cursors advance across invisible events safely.
15. Stale proposals/rules/content versions return explicit conflict responses instead of silently overwriting state.
16. Exact original A/B/D/E finance examples pass; D's voucher 3% limit comes from finance, not a hidden preference. 300 is rejected as voucher_pct; fixed fees and assumed tax are never dropped.
17. Default horizon is seven days; exactly 35 settlements and 70 channel metric rows exist after a complete run. History adds 140 rows separately; it is not counted as operating evidence or decremented again from opening inventory.
18. A confirmed question changes only its authorized rule field/version. Declining a question does not reject an approved offer; questions on running packages do not authorize new spend. The current package cannot be raised/resumed automatically.
19. Pausing ads preserves a still-active voucher and published content; end_day expires the voucher without undoing content. A renewed package cannot stack quality gains.
20. Forecast points, ranges, daily and raw snapshots exist at the right grain; MAPE/calibration use matching shop-day data available before outcomes. Null/zero cases cannot fabricate a winning comparison.
21. All nine legacy routes map to the same domain services and currency units. Versioned responses are enveloped; legacy responses remain bare; final next_day=null/step=complete is handled explicitly.
22. Expired worker leases are recoverable; crash/retry cannot resubmit a paid job blindly, double-publish, double-settle, duplicate rule confirmation, or permanently block a processing key.
23. Memory-off still enforces initial rules and stopping. Learning completion/skipping is recorded before advance; own-shop summary/report never leaks through platform endpoints.
24. SQLite and Sites adapters, if enabled, pass the same competing-command/rollback tests. A failed D1 precondition cannot commit only part of campaign/stock/event writes.
25. Offline executes without paid calls; replay needs no key and never silently becomes live. Media/knowledge failure uses explicitly labeled fallback and leaves approval gates intact.

## 12. Implementation order and scope cuts

1. Freeze this v1.1 contract: whole-percent Package, original fees/seed, seven operating days, fourteen baseline-history days and role allowlists. Record implementation changes required by section 10 instead of changing unrelated documents in this data-only revision.
2. Implement DB migrations, constraints and seed loading in the chosen storage profile; implement context/metrics queries with authorization and common DTOs. While the user limits edits on main to data/, prepare implementation artifacts there only; application integration outside data/ is a separate authorized workstream.
3. Implement proposal/check/decision/apply transactions and event polling.
4. Implement deterministic settlement, historical data and reset isolation.
5. Add knowledge ingestion/search and the nine required reference documents.
6. Add content versions/assets/jobs; retain images/text if video is cut.
7. Integrate agent-owned learning through day_closed events, immutable forecasts, confirmation commands, scoped history and completion envelopes.
8. Record a sanitized replay and calculate comparison evidence from stored metrics.

Optional cuts: persona reviews/comparison images, video, external tracing, multi-product support. Keep hard-rule enforcement, seller approval, role isolation, deterministic simulation and evidence provenance.

## 13. Revision decisions and remaining implementation work

| Decision | Final resolution / reason |
| --- | --- |
| Working location | main, data/ only, per latest user instruction; this file is the design/revision record |
| Simulation horizon | 7 operating days; preserve labeled six-day reporting compatibility, no eighth-day outcome |
| Historical observations | 14 baseline days, no paid history or learned-memory warm start; identical starting evidence for both arms |
| Seed and fees | Restore SEED_DATA shop values and 8%+5%+1.5%+3000/order; avoid changing finance story while designing persistence |
| Public interface | Existing Package units and nine demo routes remain behind a facade; v1 service endpoints add strong ownership/versioning |
| Financial evidence | Realized paid-channel ROAS is authoritative; preserve contribution rounding with explicit reconciliation; record simulator version change |
| Missing domain state | Add negotiations, cards, forecast snapshots, rule questions, operations and learning handoffs; separate ads pause from whole package lifecycle |
| Memory ownership | Data service stores evidence/confirmation/envelopes; agent team owns learned prefs/history/calibration/lessons and graph checkpoints |
| OpenAI storage | Sites D1/R2 is supported hosted profile; Files/Vector Stores hold searchable documents; never independently writable mirrors |
| Reliability | Explicit offline mode, no-key replay, recoverable operations, exact-version approvals and atomic settlements |

This file is a complete **design**, not proof that endpoints/migrations/data/provider access have been implemented. Existing code is not made compliant by editing documentation. Implementation must add or adapt models, frontend final-day handling, mode resolution, realized-ROAS simulator and storage/provider integration; those code changes are outside this document-only task. Run the acceptance suite with fake provider clients and temporary databases before recording a real replay. Do not run paid provider calls from tests.

Review performed for this revision: schema/endpoint cross-references, original finance examples, JSON examples, permission surfaces, legacy mapping and directory/branch scope. Do not claim a backend test suite or cloud deployment passed on the basis of this design review.

## 14. Source basis and references

Project-specific requirements derive from the repository's AGENTS.md, docs/ARCHITECTURE.md, docs/CONTRACT.md, docs/SEED_DATA.md, the simulation/learning task descriptions and this conversation's seven-day/storage/working-directory decisions. The original 15-page plan is reference material; current module paths are those in ARCHITECTURE. These policies, fees and market behaviors are synthetic hackathon conventions, not claims about any real platform's production systems.

Official OpenAI documentation consulted in the preceding design discussion:

- File Search: https://developers.openai.com/api/docs/guides/tools-file-search
- Retrieval and Vector Stores: https://developers.openai.com/api/docs/guides/retrieval
- Sites data and connections: https://learn.chatgpt.com/docs/sites/data-and-connections
- D1 command execution and batch semantics: https://developers.cloudflare.com/d1/worker-api/d1-database/

Provider access, indexing, and hosting integration should be verified against the team's actual environment during implementation. The HTTP routes in this document are the team's proposed APIs, not OpenAI endpoints.
