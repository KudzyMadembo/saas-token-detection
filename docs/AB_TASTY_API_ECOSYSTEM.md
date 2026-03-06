# Architectural Integration and Technical Documentation of the AB Tasty Public API Ecosystem

## Purpose

This document is the repository-wide technical reference for AB Tasty ecosystem integration standards. New services, scripts, and automation in this project should align with this architecture, security model, and operational guidance.

## Technical Foundation and Brand Evolution

The AB Tasty developer ecosystem is organized into two main domains:

- Web Experimentation and Personalization (client-side)
- Feature Experimentation and Rollout (FE&R, formerly Flagship, server-side)

The Flagship brand is commercially merged into AB Tasty, but technical namespaces and endpoints may still use `flagship` for backward compatibility.

AB Tasty infrastructure is optimized for low-latency decisions via a global CDN footprint (200+ PoPs). The Decision API target profile is sub-50ms response time for server-side decisioning.

## Core API Modules

| API Module | Core Functional Purpose | Namespace / Base URL |
| --- | --- | --- |
| Public API | Administrative orchestration of tests, users, and account assets | `https://api.abtasty.com/` |
| Decision API (v2) | Real-time evaluation of feature flags and variation assignments | `https://decision.flagship.io/v2/` |
| Data Explorer API | Advanced querying of raw event hits and computed metrics | Variable (authenticated via Public Token) |
| Universal Data Connector | Ingestion of external audience segments and third-party data | `https://api-data-connector.abtasty.com/` |
| Recommendations API | Dynamic retrieval of personalized product and content arrays | `https://uc-info.eu.abtasty.com/v1/reco` |
| Search / Autocomplete API | Internal search optimization and predictive text | `/search` (v0.3), `/autocomplete` (v0.2) |

## Authentication and Security Governance

### OAuth2 Token Acquisition

The Public API uses OAuth2 `client_credentials` grant.

Token endpoint:

- `POST https://api.abtasty.com/oauth/v2/token`

Required JSON payload:

| Argument | Data Type | Requirement | Description |
| --- | --- | --- | --- |
| `client_id` | String | Required | Identifier generated in AB Tasty settings |
| `client_secret` | String | Required | Secret paired with `client_id` |
| `grant_type` | String | Required | Must be `client_credentials` |

Successful response returns:

- `access_token`
- `expires_in` (typically 43,200 seconds)
- `token_type` (`Bearer`)

### Role-Based Access Control and Revocation

Access is role-scoped (RBAC), not globally enabled. Credentials can be limited to specific functions such as campaign read, script update, or user administration. Credential history should be monitored, and compromised credentials revoked immediately.

## Public API: Administrative Automation

The Public API enables test/campaign lifecycle automation and operational controls.

### Campaign and Test Orchestration Filters

| Filter Parameter | Expected Values | Functional Impact |
| --- | --- | --- |
| `filter[active]` | `0`, `1` | `0`: paused tests, `1`: active tests |
| `filter[type]` | `ab`, `mvt`, `multipage`, etc. | Filter by campaign type |
| `filter[is_preprod]` | Boolean | Restrict to pre-production |
| `filter[is_schedule]` | `0`, `1` | Filter by scheduled campaigns |
| `_max_per_page` | Integer (max 10) | Page size control |

### Script and Framework Control

Public API operations include:

- Update AB Tasty script
- Clear AB Tasty script (emergency use)
- Retrieve framework checksum for integrity verification

## Decision API v2: Server-Side Experimentation

Primary endpoint:

- `POST https://decision.flagship.io/v2/{{envID}}/campaigns`

### Request Payload

| Field | Data Type | Description |
| --- | --- | --- |
| `visitor_id` | String | Persistent user identifier |
| `context` | Object | Targeting key-value attributes |
| `trigger_hit` | Boolean | Auto-record display event |
| `visitor_consent` | Boolean | Tracking consent state |
| `decision_group` | String | Optional multi-campaign coordination |

### Deployment Models

- **Cloud Decision API**: direct calls to AB Tasty managed infra.
- **Self-hosted Decision API**: on-prem/local infra via Docker container or binary.
- **Bucketing mode**: SDK-based local decisioning using a downloaded bucketing file.

### Deterministic Assignment

Traffic assignment uses a deterministic MurmurHash strategy based on `visitor_id` and variation-group identifiers so that experiences stay consistent across sessions without centralized per-request state.

## Data Explorer API

The Data Explorer API supports advanced extraction and custom analytics.

- **Hits**: raw event-level records
- **Metrics**: computed values (for example, visitor count, AOV)

### Governance and Quality Controls

- Monthly extraction quotas
- Query simulation before execution
- Global window/query-size limits
- Data quality filters:
  - Exclude QA activity
  - Exclude bot activity
  - Exclude corrupted/multiple-allocation records

## Universal Data Connector (UDC)

UDC ingests external segmentation datasets for targeting.

| Constraint | Limit / Value |
| --- | --- |
| Max file size | 20 MB |
| Max rows | 100,000 |
| Formats | JSON, CSV |
| Authentication | Public API token with UDC role |
| Processing | Queue-based FIFO |

UDC status behavior:

- `202 Accepted`: queued successfully
- `413 Payload Too Large`: file exceeds limits
- `415 Unsupported Media Type`: invalid format

Segment retrieval endpoint:

- `GET https://api-data-connector.abtasty.com/accounts/{identifier}/segments/{visitor_id}`

## Specialized Modules

### Recommendations API

- Endpoint: `https://uc-info.eu.abtasty.com/v1/reco`
- Auth: Bearer token
- Typical use: API-first recommendation retrieval for custom front-end rendering

### Search and Autocomplete APIs

- `/search` API (v0.3): retrieval, facets, filters, sorting
- `/autocomplete` API (v0.2): low-latency query suggestions

### Evi Agentic AI

Evi introduces AI-assisted experiment analysis, opportunity discovery, and dynamic traffic allocation support.

## Integration Ecosystem

### Mixpanel Bi-Directional Sync

- Export Mixpanel cohorts into AB Tasty for targeting
- Import AB Tasty experiment metadata into Mixpanel for advanced behavioral analysis

Example extraction patterns:

- Campaign name parsing with `REGEX_EXTRACT`
- Variation parsing via nested `SPLIT` formulas

### mParticle Event Forwarding

- Connect via Integration Hub API key
- Forward app/server events and resolve identity for consistent cross-platform targeting

## Developer Toolchain

### AB Tasty CLI (`abtasty-cli`)

Command groups include:

- `authentication`
- `account-environment`
- `campaign`
- `flag`
- `panic`

Credential storage path:

- `$HOME/.abtasty/credentials/fe/`

### SDK Integration Pattern

1. Install SDK dependency
2. Configure with environment ID and API key
3. Pass visitor ID and context
4. Verify implementation via platform tooling

Supported environments include Web, Mobile, and Server runtimes.

## Reliability Controls

### Panic Mode

Global kill switch to stop experiment impact and return fallback values immediately during incidents.

### Experience Continuity

Use stable authenticated visitor IDs to preserve variation consistency across devices and channels.

## Implementation Guidance for This Repository

All new integration or automation code should:

- Use explicit module ownership for Public API, Decision API, Data Explorer, and UDC responsibilities.
- Enforce OAuth2 bearer token usage and avoid credential embedding in source files.
- Apply least-privilege roles for machine credentials.
- Include fallback behavior when decisioning is degraded or unavailable.
- Preserve deterministic visitor assignment semantics where applicable.
- Validate ingestion payload size and format for connector workflows.

## Works Cited

1. [Welcome to our developers' documentation | Home page dev documentation](https://docs.abtasty.com/dev-doc)
2. [AB Tasty documentation](https://docs.abtasty.com/)
3. [Decision API | Server side experimentations](https://docs.abtasty.com/server-side/decision-api)
4. [Feature Experimentation & Rollout](https://docs.abtasty.com/feature-experimentation-and-rollout)
5. [October - Flagship becomes Feature Experimentation & Rollouts](https://docs.abtasty.com/flagship-deprecated/release-notes/october----flagship-becomes-feature-experimentation--rollouts)
6. [A New Chapter for Flagship as it Merges with the AB Tasty Website](https://www.abtasty.com/blog/flagship-abtasty-merge/)
7. [Faster and Safer Releases with AB Tasty Rollouts](https://www.abtasty.com/rollouts/)
8. [Data-driven experiences with feature experimentation](https://www.abtasty.com/feature-experimentation/)
9. [Tech and Performance](https://www.abtasty.com/tech-performance/)
10. [Public API | Client side experimentations](https://docs.abtasty.com/client-side/data-apis/public-api)
11. [AB Tasty public API](https://docs.abtasty.com/integrations/custom-integrations/ab-tasty-public-api)
12. [SDK integration | Get started](https://docs.abtasty.com/onboarding/fe-and-r-quick-start-guide/sdk-integration)
13. [Access Rights, Teams & User Management](https://docs.abtasty.com/flagship-deprecated/team/access-rights-teams--user-management)
14. [Glossary | Server side experimentations](https://docs.abtasty.com/server-side/glossary)
15. [Getting Started with Flagship](https://docs.abtasty.com/server-side)
16. [Decision Mode](https://docs.abtasty.com/server-side/concepts/decision-mode)
17. [flagship-io/decision-api](https://github.com/flagship-io/decision-api)
18. [.NET | Server side experimentations](https://docs.abtasty.com/server-side/sdks/net)
19. [AB Tasty](https://www.abtasty.com/?p=t)
20. [Glossary | Flagship - Deprecated](https://docs.abtasty.com/flagship-deprecated/first-steps-with-flagship/glossary)
21. [Shopify app transactions to Feature Experimentation & Rollouts](https://docs.abtasty.com/flagship-deprecated/implementation/sending-transactions-from-the-ab-tasty-shopify-app-directly-to-feature-experimentation--rollouts)
22. [Data Explorer Introduction](https://docs.abtasty.com/client-side/data-apis/data-explorer/de-intro)
23. [Data Explorer](https://docs.abtasty.com/reporting-and-performances/data-explorer)
24. [Client side documentation](https://docs.abtasty.com/client-side)
25. [Universal data connector API](https://docs.abtasty.com/client-side/data-apis/universal-data-connector)
26. [AB Tasty - Analytics](https://analytics-docs.piano.io/en/analytics/v1/ab-tasty)
27. [Search API](https://docs.abtasty.com/search/api)
28. [Recommendations how-tos](https://docs.abtasty.com/recommendations-and-merchandising/how-tos)
29. [Accessing Recommendations API](https://docs.abtasty.com/recommendations-and-merchandising_deprecated/recos-and-merch-api/accessing-recommendations-api-only-specific-accounts)
30. [ABTasty | mParticle Audience](https://docs.mparticle.com/integrations/abtasty/audience/)
31. [AB Tasty - Mixpanel Docs](https://docs.mixpanel.com/docs/cohort-sync/integrations/abtasty)
32. [Fullstory integration](https://docs.abtasty.com/integrations/pull-integrations/fullstory)
33. [CLI authentication reference](https://docs.abtasty.com/server-side/command-line-interface/ab-tasty-cli-reference-v1xx/feature-experimentation/feature-experimentation-authentication)
