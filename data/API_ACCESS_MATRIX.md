# Ma trận quyền Data API v2

Inventory 74 operations. Cột roles là gate vai trò; còn kiểm run/shop/job, visibility, owner, version và state. GET /api/state cho bootstrap seller khi không có credentials; bearer không hợp lệ bị từ chối. Quyền vai trò không cho phép đọc mọi field.

| ID | Method/path | Vai trò | Scope bổ sung |
| --- | --- | --- | --- |
| API-001 | `GET /health` | public | caller/session or document ACL |
| API-002 | `GET /api/state` | seller | seller_session, shop_D |
| API-003 | `POST /api/reset` | seller | seller_session, shop_D |
| API-004 | `POST /api/day/start` | seller | seller_session, shop_D |
| API-005 | `GET /api/events` | seller | seller_session, shop_D |
| API-006 | `POST /api/decision` | seller | seller_session, shop_D |
| API-007 | `POST /api/content/retry` | seller | seller_session, shop_D |
| API-008 | `POST /api/content/apply` | seller | seller_session, shop_D |
| API-009 | `POST /api/night` | seller | seller_session, shop_D |
| API-010 | `GET /api/proof` | seller | seller_session, shop_D |
| API-011 | `GET /api/v1/runs/{r}/shops` | data_admin, orchestrator, platform_agent | run |
| API-012 | `GET /api/v1/runs/{r}/shops/{s}/context` | data_admin, orchestrator, platform_agent, seller, shop_agent, simulated_seller | run, shop |
| API-013 | `GET /api/v1/runs/{r}/shops/{s}/products` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-014 | `GET /api/v1/runs/{r}/shops/{s}/inventory` | data_admin, evaluator, learning_worker, orchestrator, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-015 | `GET /api/v1/runs/{r}/shops/{s}/costs` | data_admin, evaluator, learning_worker, orchestrator, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-016 | `GET /api/v1/runs/{r}/shops/{s}/rules` | data_admin, evaluator, learning_worker, orchestrator, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-017 | `GET /api/v1/runs/{r}/policies` | content_worker, data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run |
| API-018 | `GET /api/v1/runs/{r}/market/observations` | data_admin, orchestrator, platform_agent | run |
| API-019 | `GET /api/v1/runs/{r}/market/summary` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run |
| API-020 | `GET /api/v1/runs/{r}/shops/{s}/metrics` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-021 | `GET /api/v1/runs/{r}/shops/{s}/history` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-022 | `GET /api/v1/runs/{r}/shops/{s}/campaigns` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-023 | `GET /api/v1/runs/{r}/shops/{s}/forecasts` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-024 | `GET /api/v1/runs/{r}/proposals/{pid}` | data_admin, evaluator, learning_worker, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, entity_owner_shop |
| API-025 | `POST /api/v1/runs/{r}/shops/{s}/checks` | platform_agent, shop_agent | run, shop |
| API-026 | `POST /api/v1/runs/{r}/shops/{s}/proposals` | platform_agent, shop_agent | run, shop |
| API-027 | `POST /api/v1/runs/{r}/knowledge/search` | content_worker, learning_worker, orchestrator, platform_agent, seller, shop_agent | run |
| API-028 | `GET /api/v1/runs/{r}/knowledge/documents/{did}` | content_worker, data_admin, evaluator, knowledge_admin, learning_worker, monitor, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run |
| API-029 | `POST /internal/v1/knowledge/documents` | knowledge_admin | caller/session or document ACL |
| API-030 | `POST /internal/v1/knowledge/documents/{did}/revoke` | knowledge_admin | caller/session or document ACL |
| API-031 | `POST /api/v1/runs` | data_admin, evaluator, orchestrator, seller | caller/session or document ACL |
| API-032 | `GET /api/v1/runs/{r}` | content_worker, data_admin, evaluator, knowledge_admin, learning_worker, monitor, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run |
| API-033 | `POST /api/v1/runs/{r}/reset` | seller | run |
| API-034 | `GET /api/v1/runs/{r}/state` | orchestrator, seller | run |
| API-035 | `POST /internal/v1/runs/{r}/shops/{s}/negotiations` | data_admin, orchestrator | run, shop |
| API-036 | `POST /api/v1/runs/{r}/proposals/{pid}/present` | data_admin, orchestrator | run, entity_owner_shop |
| API-037 | `POST /api/v1/runs/{r}/decisions` | seller, simulated_seller | run |
| API-038 | `POST /api/v1/runs/{r}/campaigns/apply` | data_admin, orchestrator | run |
| API-039 | `POST /api/v1/runs/{r}/days/start` | data_admin, orchestrator, seller | run |
| API-040 | `POST /api/v1/runs/{r}/days/close` | data_admin, orchestrator, seller | run |
| API-041 | `POST /api/v1/runs/{r}/days/advance` | data_admin, orchestrator, seller | run |
| API-042 | `GET /api/v1/runs/{r}/operations/{oid}` | data_admin, orchestrator, seller | run |
| API-043 | `GET /api/v1/runs/{r}/shops/{s}/content` | content_worker, data_admin, evaluator, learning_worker, orchestrator, seller, shop_agent, simulated_seller, simulator | run, shop, assigned_job_or_asset_acl |
| API-044 | `POST /api/v1/runs/{r}/shops/{s}/content-jobs` | orchestrator, seller | run, shop |
| API-045 | `GET /api/v1/runs/{r}/content-jobs/{jid}` | content_worker, data_admin, evaluator, learning_worker, orchestrator, seller, shop_agent, simulated_seller, simulator | run, entity_owner_shop, assigned_job_or_asset_acl |
| API-046 | `POST /internal/v1/runs/{r}/content-jobs/{jid}/result` | content_worker | run, entity_owner_shop, assigned_job_or_asset_acl |
| API-047 | `POST /api/v1/runs/{r}/assets/uploads` | content_worker, knowledge_admin, learning_worker, orchestrator, seller | run, assigned_job_or_asset_acl |
| API-048 | `PUT /api/v1/runs/{r}/assets/{aid}/bytes` | content_worker, data_admin, evaluator, knowledge_admin, learning_worker, monitor, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, entity_owner_shop, assigned_job_or_asset_acl, upload_owner |
| API-049 | `POST /api/v1/runs/{r}/assets/{aid}/complete` | content_worker, data_admin, evaluator, knowledge_admin, learning_worker, monitor, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, entity_owner_shop, assigned_job_or_asset_acl, upload_owner |
| API-050 | `GET /api/v1/runs/{r}/assets/{aid}/download` | content_worker, data_admin, evaluator, knowledge_admin, learning_worker, monitor, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run, entity_owner_shop, assigned_job_or_asset_acl |
| API-051 | `POST /api/v1/runs/{r}/content/{cid}/publish` | orchestrator | run, entity_owner_shop |
| API-052 | `POST /internal/v1/runs/{r}/shops/{s}/settle-day` | data_admin, orchestrator, simulator | run, shop |
| API-053 | `POST /api/v1/runs/{r}/campaigns/{cid}/pause` | monitor, orchestrator, seller | run, entity_owner_shop |
| API-054 | `GET /internal/v1/runs/{r}/learning-input` | learning_worker | run |
| API-055 | `POST /internal/v1/runs/{r}/learning-results` | learning_worker | run |
| API-056 | `POST /internal/v1/runs/{r}/shops/{s}/rule-questions` | learning_worker, orchestrator | run, shop |
| API-057 | `GET /api/v1/runs/{r}/shops/{s}/rule-questions` | data_admin, evaluator, learning_worker, orchestrator, seller, shop_agent, simulated_seller, simulator | run, shop |
| API-058 | `PUT /api/v1/runs/{r}/shops/{s}/rules` | seller, simulated_seller | run, shop |
| API-059 | `GET /api/v1/runs/{r}/proof` | data_admin, evaluator, orchestrator, seller | run, both_runs, session_or_grant |
| API-060 | `GET /api/v1/runs/{r}/events` | content_worker, data_admin, evaluator, knowledge_admin, learning_worker, monitor, orchestrator, platform_agent, seller, shop_agent, simulated_seller, simulator | run |
| API-061 | `POST /internal/v1/runs/{r}/replay/export` | data_admin, evaluator, orchestrator | run |
| API-062 | `GET /api/v1/runs/{r}/operations` | data_admin, orchestrator, seller | run |
| API-063 | `POST /internal/v1/runs/{r}/operations/{oid}/claim` | orchestrator | run |
| API-064 | `POST /internal/v1/runs/{r}/operations/{oid}/result` | orchestrator | run |
| API-065 | `POST /api/v1/runs/{r}/days/{day}/learning/retry` | orchestrator, seller | run |
| API-066 | `POST /api/v1/runs/{r}/days/{day}/learning/skip` | orchestrator, seller | run |
| API-067 | `GET /api/v1/runs/{r}/shops/{s}/night-summary` | data_admin, evaluator, orchestrator, seller, shop_agent | run, shop |
| API-068 | `POST /api/v1/runs/{r}/content/{cid}/restore` | seller | run, entity_owner_shop |
| API-069 | `POST /api/content/undo` | seller | seller_session, shop_D |
| API-070 | `POST /api/v1/comparisons` | data_admin, evaluator, orchestrator, seller | both_runs, session_or_grant |
| API-071 | `POST /api/v1/comparisons/attach` | data_admin, evaluator, orchestrator, seller | both_runs, session_or_grant |
| API-072 | `GET /api/v1/comparisons/{gid}` | data_admin, evaluator, orchestrator, seller | both_runs, session_or_grant |
| API-073 | `POST /internal/v1/runs/{r}/events` | learning_worker, orchestrator, platform_agent, shop_agent | run |
| API-074 | `GET /api/v1/runs/{r}/events/export` | data_admin, evaluator, orchestrator, seller | run |

Nguồn máy đọc: [api_catalog.json](api_catalog.json). Gate A đối chiếu OpenAPI, yêu cầu ca HTTP thành công cho từng operation; kiểm invalid bearer và vai trò trái quyền từ request hợp lệ. Test scope, field projection, concurrency và fault injection là gate riêng; không suy ra chúng chỉ từ status 2xx.
