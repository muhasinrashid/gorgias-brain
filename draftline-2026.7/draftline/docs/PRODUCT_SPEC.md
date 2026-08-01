# DRAFTLINE — Build Specification for Cursor
### v3 — engineering foundation, GCP infrastructure, and billing architecture

> **How to use this file.** Commit at `docs/PRODUCT_SPEC.md`. Reference it from the generated `.cursor/rules/`, `CLAUDE.md` and `AGENTS.md` so it loads automatically. Work milestone by milestone, gate by gate. Do not paste this document into one chat and ask for the application — that produces a plausible codebase that does not run.
>
> **Changes since v2:** deployment target confirmed as Google Cloud Run (Part 2 is new); billing model and entitlement architecture confirmed (§1.8); Celery topology remapped onto Cloud Run; CI/CD extended to deployment.

---

# PART 0 — Mission and rules of engagement

You are building **Draftline**: a multi-tenant SaaS application that connects to a merchant's Gorgias helpdesk, reads incoming customer tickets, assembles real commercial context from BigCommerce and Global-E, and writes a **draft reply** that a human support agent reviews and sends.

**In Phase 1 the system never sends anything to a customer.** Every output goes to an internal surface for a human. This is an invariant enforced in code, not a configuration default.

The differentiating feature is not drafting — every vendor drafts. It is the **Delta Learning Engine**: capturing what the human actually sent, diffing it against what we drafted, classifying why they differed, and converting those differences into human-approved improvements. Build the drafting so delta capture is possible from day one. Do not bolt it on later.

## Rules of engagement

1. **Read before you write.** Complete Stage 0 reconnaissance before generating application code.
2. **Do not rebuild what Pegasus provides.** Auth, teams, roles, invitations, Stripe plumbing, email, settings shell, admin, Celery wiring, Cloud Run deploy config. If you are writing a `User` model or a Stripe webhook handler, stop.
3. **The host codebase's conventions beat your preferences.** Its app layout, naming, settings structure and test style win. Match them exactly.
4. **Every external system sits behind an adapter.** Gorgias, BigCommerce, Global-E, the LLM provider, the vector store, **the payment provider**. No third-party SDK call appears in domain or view code.
5. **Everything is tenant-scoped.** Every model has a team FK. Every query filters. Every route enforces.
6. **Everything slow is asynchronous.** Webhook receivers validate, persist, enqueue, return 200. Nothing else.
7. **Ask when ambiguous.** State the assumption you would make, then wait. Do not invent a schema and build three modules on it.
8. **Stop at gates.** Milestones end with exit criteria. Reaching one means demonstrating it, not asserting it.

## Hard prohibitions

- **No code path that sends a message to a customer may exist.** Not disabled, not flagged, not commented out. The capability must be absent from the codebase.
- No writes to BigCommerce or Global-E. Read-only.
- No writes to Gorgias except: create internal note, add tag.
- **No feature gate may query a payment provider.** Entitlement is read from `TeamEntitlement` and nowhere else. See §1.8.
- Do not invent third-party API shapes from memory. Fetch live documentation or ask.
- No `localStorage` or `sessionStorage` in the embedded widget.
- No credentials in plaintext, in settings, or unencrypted in the database.
- **No database migration runs from a container entrypoint.** See §1.9.

---

# PART 1 — Engineering foundation

## 1.1 Confirmed stack

Generated from SaaS Pegasus with this configuration:

| | |
|---|---|
| Framework | Django 5.x, Python 3.12+ |
| Project module | `draftline` |
| **Teams** | ON — `Team` is the tenant boundary |
| **Subscriptions** | ON — **Standard** billing model, **application-managed** pricing UI |
| Frontend | **HTMX** + Alpine. No SPA build for app screens |
| Async | Celery + Redis; Django async/Channels for websockets |
| Database | PostgreSQL with **pgvector** |
| Auth | django-allauth; Google social login only; API keys; impersonation; auth APIs |
| AI scaffold | Pegasus AI Chat, backed by **Pydantic AI** |
| Storage | Cloud Storage — public media bucket plus private tenant-files bucket |
| **Deploy target** | **Google Cloud Run**, region `europe-west6` (Zurich) |
| Monitoring | Sentry ON, health checks ON |
| Dev env | Docker for database services only; app runs locally |
| Examples | Included — read them, they are the house style reference |

## 1.2 Stage 0 — reconnaissance *(do this first, report, then stop)*

**On the generated Pegasus project, report with quoted code:**

- Exact directory layout: settings module, apps location, templates, static assets.
- The `Team` model: fields, membership model, role choices, and **the exact helper functions and decorators used to scope queries and protect views.** Quote them. Everything you write will use these.
- How an example app implements a full team-scoped CRUD feature — models, views, URLs, templates, tests. This is your template for every module.
- The subscription module: plan representation, where entitlement is currently checked, how dj-stripe objects map to plans. **Identify every place application logic currently reads a Stripe object to make a decision** — §1.8 replaces all of them.
- Celery: broker config, queue definitions, task base classes, retry conventions, beat schedule.
- The generated Cloud Run deployment configuration: what services it defines, what the build produces, how migrations are handled today.
- API layer: DRF or Ninja, auth mechanism, API key model, schema generation.
- Test conventions: pytest config, factory approach, fixture layout, how team-scoped tests are written.
- What `.cursor/rules/` and the MCP configuration contain and point at.
- HTMX conventions: partial template naming, response patterns, Alpine usage.

**On the POC codebase, report:**

- What it does end to end, in your words.
- Production-worthy logic worth porting: prompt structure, retrieval approach, ticket parsing, working Gorgias API handling.
- Throwaway scaffolding.
- **Hard-won external API knowledge** — undocumented behaviour, observed rate limits, real response shapes, edge cases handled. Extract into `docs/EXTERNAL_API_NOTES.md` before touching anything else. It is the most valuable content in the POC and the easiest to lose.

**Then produce:** a proposed app layout in Pegasus conventions, and a list of every place this spec conflicts with what Pegasus already does. **Then stop for review.**

## 1.3 Application layout

Proposed. Confirm against actual Pegasus conventions in Stage 0 and adjust.

```
draftline/                    # settings, urls, celery, asgi
apps/
  integrations/    Connection model, credential vault, capability probe,
                   provider adapter packages (gorgias/, bigcommerce/, globale/)
  tickets/         Ticket, TicketMessage, normalisation, qualification,
                   resolving-reply detection
  commerce/        Commerce models, entity extraction, identity resolution,
                   OrderContextCard assembly
  knowledge/       Source, Chunk, ResolutionPair, CuratedKnowledge, retrieval
  agents/          Agent, InstructionVersion, agent settings, kill switch
  drafting/        Task, ToolCall, Draft, generation pipeline, guardrails,
                   delivery adapters
  deltas/          DeltaRecord, DeltaInsight, matching, classification, mining
  evaluation/      RegressionSet / Run / Result, rubric scoring
  llm/             Provider adapters, prompt registry, routing, cost accounting
  billing/         TeamEntitlement, usage metering, BillingProvider adapters
  reporting/       Metric aggregation, report views
infra/             Terraform. Not click-ops.
```

**Enforced dependency direction:**

```
llm, integrations, billing   →  depend on nothing else in apps/
tickets, commerce, knowledge →  may depend on integrations, llm
agents                       →  may depend on knowledge
drafting                     →  may depend on all of the above, and billing (quota checks)
deltas                       →  may depend on drafting, tickets, knowledge
evaluation                   →  may depend on drafting, deltas
reporting                    →  reads everything, is depended on by nothing
```

Add **`import-linter`** to CI with this contract. An architecture rule that isn't machine-checked is a suggestion, and it will be violated in week three by someone in a hurry.

## 1.4 Code organisation conventions

**Layering.** Thin views. Fat services. Models hold data and invariants only.

```
models.py       Fields, constraints, properties, validation. No business logic.
selectors.py    Read operations. Every function takes team as its first argument.
services.py     Write operations and orchestration. Transactional boundaries here.
tasks.py        Celery tasks. Thin wrappers that call services.
views.py        HTTP concerns only: parse, authorise, call a service, render.
adapters/       External system clients. Protocol + implementations.
```

A view containing a `for` loop over business objects has logic in the wrong place.

**Tenant scoping.** Every domain model:

```python
class TeamScopedModel(models.Model):
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, db_index=True)
    objects = TeamScopedManager()          # requires .for_team(team) before evaluation

    class Meta:
        abstract = True
```

Every selector signature starts with `team`. No exceptions, including internal jobs and admin tooling.

**Adapters are protocols.**

```python
class HelpdeskAdapter(Protocol):
    def fetch_ticket(self, external_id: str) -> TicketPayload: ...
    def list_tickets(self, since: datetime, cursor: str | None) -> TicketPage: ...
    def create_internal_note(self, ticket_id: str, body: str) -> NoteResult: ...
    def probe_capabilities(self) -> CapabilitySet: ...
```

Domain code depends on the protocol. Only `apps/integrations/providers/` imports an HTTP client.

**Type hints everywhere.** mypy or pyright in CI, strict on `apps/`.
**Formatting and linting.** ruff for both, configured in `pyproject.toml`, enforced in CI.

## 1.5 Dependencies to add beyond Pegasus

| Package | Purpose |
|---|---|
| `pgvector` | Vector columns and ANN indexes in Postgres |
| `talon` | Email quote and signature stripping — a solved problem, do not write your own |
| `beautifulsoup4`, `lxml` | HTML normalisation of ticket bodies |
| `lingua-py` | Language detection, more accurate than langdetect on short text |
| `rapidfuzz` | Fast lexical similarity for delta scoring |
| `httpx` | Async-capable HTTP client for adapters |
| `tenacity` | Retry with backoff on external calls |
| `structlog` | Structured logging with correlation IDs |
| `import-linter` | Architecture contract enforcement |
| `pytest-recording` / `vcrpy` | Record and replay external API responses |
| `google-cloud-kms` | Tenant credential envelope encryption |
| `google-cloud-secret-manager` | Application secrets (may be injected as env vars instead) |
| `cloud-sql-python-connector` | Cloud SQL connection handling, if not using private IP |
| `pydantic-ai` | Already present via Pegasus AI Chat — candidate for the drafting agent loop |

Keep the list short. Every dependency is a thing to upgrade and a thing to have a security opinion about.

## 1.6 Configuration and secrets

Environment-driven via Pegasus's existing `django-environ` setup. In GCP, secrets are stored in **Secret Manager** and injected into Cloud Run as environment variables — the application code does not know the difference.

```
GORGIAS_OAUTH_CLIENT_ID / SECRET
BIGCOMMERCE_CLIENT_ID / SECRET
GLOBALE_API_BASE
LLM_PROVIDER_API_KEY
CREDENTIAL_KMS_KEY_NAME               # KMS resource name, never the key material
GCS_PUBLIC_BUCKET / GCS_PRIVATE_BUCKET
DATABASE_URL                          # via private IP or Cloud SQL connector
REDIS_URL
DRAFT_SHADOW_MODE_DEFAULT=true
MAX_MONTHLY_INFERENCE_CENTS_PER_TEAM
```

**Tenant credentials never live in environment variables or Secret Manager.** They are per-team, encrypted with envelope encryption against a Cloud KMS key, stored in the database, decrypted only in worker processes, never logged, never serialised into any API response or admin page.

Write a test asserting a `Connection` serialises without its credentials.

## 1.7 Celery and queue topology

**Separate queues, separate workers, separate Cloud Run resources.** A backfill must never starve live drafting.

| Queue | Purpose | Runs as | Sizing |
|---|---|---|---|
| `drafting` | Live draft generation | Cloud Run service, CPU always allocated, `min-instances≥1` | Latency-critical |
| `sync` | Incremental helpdesk and commerce sync | Cloud Run service, CPU always allocated | Normal |
| `backfill` | 360-day historical import | **Cloud Run Job** | Long, resumable, rate-limited per tenant |
| `deltas` | Classification, retrospective mining | **Cloud Run Job** | Batch, cost-controlled |
| `maintenance` | Reindex, reconcile, cleanup | Cloud Run Job on a schedule | Lowest |

**Celery beat** runs as a Cloud Scheduler entry triggering a Cloud Run Job, rather than an always-on beat instance. One fewer thing to keep alive.

Every task:
- Takes primitives (IDs), never model instances.
- Is idempotent, keyed on a natural external identifier.
- Declares explicit `autoretry_for`, `max_retries`, `retry_backoff`.
- Has a dead-letter path with alerting.
- Logs with a correlation ID tracing back to the originating webhook.

> **On Cloud Run and Celery.** A Cloud Run service throttles CPU between requests by default, which starves a worker polling a queue. Worker services must set **CPU always allocated** and a minimum instance count. This is deliberate configuration, not something that works by accident. If the friction becomes material, moving worker containers to GKE Autopilot or a GCE VM is a small migration since everything is already containerised — but do not pre-emptively build for that.

## 1.8 Billing and entitlement

**Three concerns that Pegasus bundles and we must separate.**

| Concern | Owner | Gateway-dependent |
|---|---|---|
| Plan and entitlement — what this team may do | Us | No |
| Usage metering — interactions consumed | Us | No |
| Payment collection — moving money | Provider | Yes |

Payment provider is undecided (Stripe requires a supported entity jurisdiction; Razorpay fits domestic India poorly for Swiss and EU customers; a merchant-of-record such as Paddle would absorb EU VAT). **This decision does not block anything through M7** provided the separation below exists from the start.

```
TeamEntitlement
 ├── team (1:1)
 ├── plan_code            TRIAL | TEAM | BUSINESS | CUSTOM | INTERNAL
 ├── interactions_included, interactions_used, period_start, period_end
 ├── overage_packs, hard_cap_behaviour
 ├── status               ACTIVE | PAST_DUE | SUSPENDED | CANCELLED
 ├── billing_provider     MANUAL | STRIPE | RAZORPAY | PADDLE
 ├── provider_ref         nullable — null for MANUAL
 └── notes                for manually invoiced accounts
```

**Every feature gate in the application reads `TeamEntitlement` and nothing else.** No view, service or task queries dj-stripe, Stripe, or any provider object to decide what a team may do. This is a hard prohibition, and Stage 0 must identify every place Pegasus currently violates it.

```python
class BillingProvider(Protocol):
    def create_checkout(self, team, plan_code) -> CheckoutSession: ...
    def sync_entitlement(self, team) -> TeamEntitlement: ...
    def handle_webhook(self, payload) -> None: ...
```

Implementations, in build order:

- **`ManualBillingProvider`** — ships first and is the default. An admin assigns a plan; invoicing happens offline; quota is still enforced; usage is still tracked; the plan page still renders. **No payment gateway exists anywhere in the system.** This carries M0 through M7.
- **`StripeBillingProvider`** — wraps Pegasus's existing dj-stripe module when a provider is chosen.
- **`RazorpayBillingProvider` / `PaddleBillingProvider`** — added later without touching a single entitlement check.

**Metering: two counters, not one.**

`Task.is_metered=True` covers live draft generation, which consumes the customer's plan quota. One processed message equals one interaction regardless of how many tool calls it triggers.

`Task.is_metered=False` covers retrospective mining, delta judging, regression replays and re-classification sweeps — our learning costs, tracked per tenant for margin, invisible to the customer. A merchant must never discover our improvement process burned the interactions they paid for.

## 1.9 Migrations

- One logical change per migration. Never edit an applied migration.
- Data migrations separate from schema migrations; reversible, or explicitly marked irreversible with a comment explaining why.
- No squashing before GA.
- Indexes added deliberately, not reflexively. The ones you will need: `(team, external_id)` unique on every synced object, `(team, created_at)` on Task and Draft, `(team, outcome, intent)` on DeltaRecord, and the vector index on Chunk.
- Zero-downtime discipline from the start: add nullable, backfill, then constrain.

> **Migrations never run from a container entrypoint.** On Cloud Run, multiple instances start concurrently and would race each other. Migrations run as a dedicated **Cloud Run Job** executed by the deploy pipeline, after the image is built and before traffic is switched. Deployment fails if the migration job fails.

## 1.10 Testing

**Three suites are non-negotiable. CI fails without them, and they are never skipped under deadline pressure.**

1. **`tests/isolation/`** — walks the model registry, fails on any domain model without a team FK; proves team A cannot reach team B through ORM, view, API, or nested relation.
2. **`tests/no_customer_send/`** — asserts the Gorgias note payload cannot produce an outbound message; asserts no send capability exists anywhere in the codebase.
3. **`tests/leakage/`** — proves drafting for ticket *T* cannot retrieve *T*, a near-duplicate of *T*, or any artefact derived from *T*.

**Everything else:**
- Unit tests for parsers, extractors and classifiers using **fixtures from real anonymised tickets**. Synthetic fixtures will not exercise the failure modes that matter — the quoted newsletter HTML, the multilingual signature blocks, the autoresponder that looks like a real reply.
- Integration tests against recorded HTTP responses (`vcrpy`).
- Contract tests against sandbox accounts, nightly not per-commit.
- `factory_boy` factories for every model, always producing team-scoped objects.

Target: 80% coverage on `apps/`; 100% on the three mandatory suites and on anything touching money, credentials or outbound messages.

## 1.11 CI/CD

```
CI (every push)
 1. ruff check + ruff format --check
 2. mypy apps/
 3. import-linter                        ← architecture contract
 4. pytest tests/unit
 5. pytest tests/isolation               ← blocking
 6. pytest tests/no_customer_send        ← blocking
 7. pytest tests/leakage                 ← blocking, from M5
 8. pytest tests/integration
 9. makemigrations --check --dry-run

CD (main → staging, tag → production)
10. Build container, push to Artifact Registry
11. Execute migration Cloud Run Job                    ← fail here, stop here
12. Deploy web + webhook services with no traffic
13. Smoke test the new revision
14. Shift traffic
15. Deploy worker services and update Job definitions
```

Staging and production are **separate GCP projects**, not separate namespaces in one project. Cleaner IAM, cleaner billing attribution, no possibility of a staging job touching production data.

## 1.12 Working practice for pair programming

**Start of session.** State which milestone and which module. Re-read the relevant spec section and the last entry in `docs/WORKLOG.md`. Confirm scope in two sentences before writing code.

**During.** Small, reviewable increments — models, then migration, then selectors and services, then tasks, then views, then templates, then tests. Not all at once. Show the migration before running it. When an external API surprises you, record it in `docs/EXTERNAL_API_NOTES.md` immediately, before working around it.

**Definition of done for any unit of work:**
- Types pass, lint passes, import contract holds
- Tests written, including at least one that would fail if tenant scoping were removed
- Migration reviewed and reversible
- `docs/WORKLOG.md` updated
- No new dependency added without saying why

**End of session.** Three lines in `docs/WORKLOG.md`: what was built, what was learned, what is next. This is how context survives between sessions, and it takes thirty seconds.

**When uncertain, say so and stop.** A wrong assumption built on for two hours costs more than a question.

---

# PART 2 — Infrastructure (Google Cloud)

Everything in `infra/` as Terraform. No click-ops — an environment you cannot recreate from code is an environment you cannot recover.

## 2.1 Environments

| Environment | Where | Notes |
|---|---|---|
| Local | Docker for Postgres (pgvector image) and Redis; app runs on host | Fast loop |
| Staging | GCP project `draftline-staging` | Real integrations against sandbox accounts |
| Production | GCP project `draftline-prod` | `europe-west6` (Zurich) |

Region `europe-west6` is chosen deliberately: the design partner is a Swiss brand serving EU customers, and Zurich residency simplifies the data-residency position. Fall back to `europe-west1` only if a required service is unavailable or pricing is prohibitive — and if you do, record why in `docs/EXTERNAL_API_NOTES.md`.

## 2.2 Service mapping

| Component | GCP service | Critical configuration |
|---|---|---|
| Web app (HTMX) | Cloud Run service | `min-instances=1`, moderate concurrency, 60s timeout |
| **Webhook receiver** | Cloud Run service, **separate from web** | `min-instances=1`, CPU always allocated, high concurrency, fast handler |
| Workers — `drafting`, `sync` | Cloud Run services | **CPU always allocated**, `min-instances≥1` |
| `backfill`, `deltas`, `maintenance` | **Cloud Run Jobs** | Parallel tasks, checkpointed, resumable |
| Migrations | Cloud Run Job | Run by CD, before traffic switch |
| Scheduling | Cloud Scheduler → Cloud Run Jobs | Replaces always-on Celery beat |
| Postgres + pgvector | Cloud SQL for PostgreSQL | Same region; `CREATE EXTENSION vector` |
| Redis | Memorystore | Same region; requires VPC access — see §2.3 |
| Object storage | Cloud Storage | Public media bucket + **private tenant-files bucket, signed URLs only** |
| App secrets | Secret Manager | Injected as env vars into Cloud Run |
| Tenant credential encryption | **Cloud KMS** | Envelope encryption; decrypt permission on workers only |
| Container images | Artifact Registry | |
| Monitoring | Sentry + Cloud Logging + Cloud Monitoring uptime checks | Uptime check hits the Pegasus health endpoint |

**Split the webhook receiver from the main web service.** They have different requirements: the webhook must always be warm and answer inside 500ms because Gorgias times out at 5 seconds and retries three times; the web app tolerates a slower cold path. Sharing one service makes the webhook's availability requirement set the cost floor for everything.

## 2.3 Networking and data access

- **Memorystore is VPC-only.** Cloud Run reaches it through Direct VPC egress (preferred) or a Serverless VPC Access connector. This catches people out — plan for it in Terraform rather than discovering it on first deploy.
- **Cloud SQL** via private IP over the same VPC path, or the Cloud SQL connector. Private IP is preferable; no public endpoint.
- **Connection pooling in front of Postgres, from day one.** This is the classic serverless-plus-Postgres failure. Every Cloud Run instance opens its own Django connection pool; scale to twenty instances and you exhaust Cloud SQL's connection limit while barely touching its CPU. Use Cloud SQL's managed connection pooling or pgbouncer, and set `CONN_MAX_AGE` deliberately rather than leaving the default. Getting this wrong presents as random database errors under load and is miserable to diagnose after the fact.
- Private tenant files are never publicly readable. Access is via time-limited signed URLs generated server-side after an authorisation check.

## 2.4 Identity and least privilege

**One service account per Cloud Run service or job**, with the minimum roles it needs. This is not ceremony — it directly enforces the credential rules in §1.6.

| Service | Notably needs | Notably must NOT have |
|---|---|---|
| Webhook receiver | Redis/queue write, Cloud SQL write | **KMS decrypt** — it never touches tenant credentials |
| Workers (`drafting`, `sync`) | KMS decrypt, Cloud SQL, Secret Manager, GCS | — |
| Jobs (`backfill`, `deltas`) | KMS decrypt, Cloud SQL, GCS | — |
| Web app | Cloud SQL, GCS signed-URL signing | **KMS decrypt** |
| Migration job | Cloud SQL admin on the app database only | KMS, GCS |

If the webhook receiver is compromised, it cannot decrypt a single tenant's Gorgias credentials. That property is worth the extra Terraform.

## 2.5 Performance rules

Platform choice matters far less to perceived speed than these four things do. This application's latency is dominated by LLM inference and third-party API calls — a draft takes tens of seconds because the model takes tens of seconds, and no hosting decision changes that. Where the platform genuinely matters:

1. **`min-instances=1` on the webhook service is non-negotiable.** A cold start against a 5-second Gorgias timeout produces retries, which produce duplicate events, which the idempotency layer then has to absorb. Pay for the warm instance.
2. **Connection pooling.** See §2.3. Do it before you need it.
3. **Everything in one region.** Compute, Cloud SQL, Memorystore and storage all in `europe-west6`. A cross-region hop on every query costs more latency than any platform decision wins back.
4. **Tune Cloud Run concurrency per service.** The default is not right for all three shapes: the webhook handler is fast and can take high concurrency; the web app is moderate; worker services should not be request-scaled at all.

> Cloud Run's request timeout, job task duration and concurrency ceilings have all moved in recent years. **Verify current limits before designing around them** rather than trusting any figure quoted here or in training data.

---

# PART 3 — Domain model

Names are indicative. Adapt to Pegasus conventions; keep the semantics.

## 3.1 Tenancy and configuration

```
Team (Pegasus)                       ← the tenant boundary
 ├── TeamEntitlement (1:1)           ← see §1.8
 └── Agent
      ├── name, status, created_by
      ├── instructions → InstructionVersion (versioned, diffable, current pointer)
      ├── settings: languages, escalation policy, delivery mode, shadow_mode
      └── kill_switch: bool          ← disables generation immediately
```

```
Connection
 ├── team, provider (GORGIAS | BIGCOMMERCE | GLOBAL_E | WEBSITE | FILES)
 ├── credentials     KMS-envelope encrypted; never logged, never serialised
 ├── config          subdomain, store hash, merchant GUID
 ├── capabilities    JSON, populated by the capability probe
 ├── status, last_sync_at, last_error, health
 └── AgentConnection (M2M)
```

> **Capability probe.** On connect, actively test what this account supports and store the result. Every later code path branches on stored capabilities, never on hardcoded assumptions. Absent capability → documented fallback, surfaced in the health card.

## 3.2 Knowledge

```
Source
 ├── team, connection, source_type
 │     HELP_CENTER_ARTICLE | MACRO | TICKET | WEB_PAGE | FILE | CURATED_QA
 ├── external_id, title, url, raw_content, normalised_content
 ├── language, checksum, synced_at, is_active
 ├── usage_count, last_used_at        ← macros especially; see M1 weighting
 └── metadata JSON

Chunk
 ├── source, ordinal, text, token_count
 ├── embedding (vector)
 ├── char_offset_start / char_offset_end
 └── language

ResolutionPair
 ├── team, source, source_ticket_ids[]
 ├── question_text, context_summary, resolution_text
 ├── intent, language, quality_score
 └── is_exemplar

CuratedKnowledge
 ├── team, question, answer, intent, language
 ├── status DRAFT | APPROVED | RETIRED
 ├── created_from_delta (nullable FK)
 ├── source_ticket_ids[]              ← lineage, for erasure cascade
 ├── is_deidentified: bool            ← must be True before APPROVED
 └── approved_by, approved_at
```

> **Erasure lineage.** Every derived artefact carries `source_ticket_ids` so erasure cascades rather than requiring archaeology. `CuratedKnowledge` and exemplars pass through de-identification at promotion — names, emails, order numbers, addresses and tracking numbers stripped — so generalised knowledge survives an erasure request because it no longer contains a person.

## 3.3 Tickets

```
Ticket
 ├── team, connection, external_id, subject, channel
 ├── status, created_at_external, closed_at_external
 ├── customer_email, customer_external_id
 ├── qualification  SUPPORT | SPAM_PHISHING | MARKETING_INBOUND |
 │                  SYSTEM_NOTIFICATION | SOCIAL_NOTIFICATION |
 │                  VENDOR_PITCH | INTERNAL | UNCLEAR
 ├── qualification_confidence, qualifier_version
 ├── intent, language, sentiment
 └── csat_score

TicketMessage
 ├── ticket, external_id, sequence
 ├── direction  INBOUND | OUTBOUND | INTERNAL_NOTE
 ├── author_type  CUSTOMER | AGENT | SYSTEM | BOT
 ├── author_external_id, author_name
 ├── raw_body_html, raw_body_text
 ├── normalised_text
 ├── is_autoresponder, is_resolving_reply, classifier_version
 └── sent_at
```

> `is_autoresponder` and `is_resolving_reply` are stored, not derived at query time. They are expensive, they underpin every downstream metric, and they will be recomputed as classifiers improve. Store them with the classifier version that produced them.

## 3.4 Commerce

```
CommerceCustomer   team, connection, external_id, email, name
CommerceOrder      team, external_id, order_number, status, currency, totals,
                   placed_at, customer, shipping_address,
                   global_e_reference, is_cross_border
CommerceOrderLine  order, sku, product_external_id, variant, name, qty, price
CommerceShipment   order, carrier, tracking_number, tracking_url, status,
                   dispatched_at, delivered_at, source
CommerceProduct    team, external_id, sku, name, description, variants, stock, url
```

> A cross-border order may have several parcels with several tracking numbers. Shipments are a collection. `tracking_number` never lives on the order.

```
OrderContextCard
 ├── ticket (1:1)
 ├── resolved_customer, resolved_orders (M2M)
 ├── extracted_entities JSON
 ├── identity_confidence
 ├── resolution_status  RESOLVED | AMBIGUOUS | UNRESOLVED
 ├── payload JSON            ← exact structure handed to the drafter
 └── assembled_at, ttl
```

## 3.5 Tasks, drafts, deltas — the core

```
Task
 ├── team, agent, ticket
 ├── trigger_type  NEW_CUSTOMER_MESSAGE | AGENT_MENTION | MANUAL | BACKFILL_REPLAY
 ├── status  QUEUED | RUNNING | COMPLETED | FAILED | SKIPPED
 ├── skip_reason, idempotency_key
 ├── started_at, completed_at, duration_ms
 ├── tokens_in, tokens_out, cost_cents
 ├── is_metered: bool        ← customer quota vs internal inference; §1.8
 └── error

ToolCall
 └── task, sequence, tool_name, input, output_summary, duration_ms, status

Draft
 ├── task, ticket, version
 ├── body_text, body_html, rationale, language, confidence
 ├── retrieval_trace JSON    ← every chunk, pair, macro and order field used
 ├── prompt_version, model, model_params
 ├── escalation_recommended, escalation_reason
 ├── policy_flags JSON
 ├── delivery_status  NOT_DELIVERED | DELIVERED | FAILED
 └── delivery_surface, delivery_external_id

AgentFeedback
 └── draft, user_external_id, action, comment, created_at

DeltaRecord
 ├── team, draft, ticket, source_ticket_ids[]
 ├── sent_message (nullable FK)
 ├── outcome  SENT_AS_IS | MINOR_EDIT | MAJOR_EDIT | REWRITTEN | DISCARDED | UNUSED
 ├── lexical_similarity, semantic_similarity
 ├── fact_diff JSON
 ├── edit_reasons []
 ├── severity  INFO | LOW | MEDIUM | HIGH | CRITICAL
 ├── classifier_version, classified_at
 ├── human_audited, human_audit_agreement
 ├── is_retrospective
 └── intent, language, agent_user_external_id

DeltaInsight
 ├── team, intent, language, edit_reason
 ├── occurrence_count, first_seen, last_seen, trend
 ├── severity_max, example_delta_ids
 ├── status  NEW | TRIAGED | ACTIONED | DISMISSED
 └── proposed_action JSON

RegressionSet / RegressionRun / RegressionResult
```

---

# PART 4 — Modules

## M0 · Foundation & Tenancy

**Story.** *As a support lead, I sign up, land on a plan, invite my team, and see an empty agent waiting to be connected.*

Use Pegasus's team model unchanged. Add the `Agent` model and the agent shell — left navigation of **Home · Activity · Reports · Instructions · Settings**, an Integrations section listing connections and their sources, plus Files and Skills placeholders. Home is a setup checklist driving first run: connect a source → configure the agent → see the first draft.

Roles: **Owner, Admin, Agent, Viewer**. Owner and Admin manage connections and instructions. Agent sees activity and drafts. Viewer is read-only.

Add `TeamEntitlement` with `ManualBillingProvider` (§1.8), the KMS-backed credential store, the structured audit log (instructions, connections, curated knowledge, approvals, impersonation sessions, plan changes), and feature flags.

Stand up `infra/` Terraform for the staging project: Cloud SQL with pgvector, Memorystore, VPC access, Artifact Registry, KMS key, buckets, and the web/webhook Cloud Run services.

**Done when**
- Signup → plan assigned manually → invite → empty agent works end to end.
- Registry-walking test fails on any untenanted domain model.
- Isolation test proves team A cannot reach team B via ORM, view, or API including nested relations and list endpoints.
- A `Connection` serialises without credentials, proven by test.
- **No code path reads a payment provider to decide entitlement**, proven by grep and review.
- Staging deploys from CI: image built, migration job runs, traffic shifts, health check green.
- Celery processes a task on each queue.

**Gate: do not proceed until isolation is green.** Retrofitting tenancy is the most expensive mistake available here.

## M1 · Gorgias Connection & Ingestion

**Story.** *As an admin, I connect our Gorgias account, watch it sync, and browse everything the agent can now read.*

**Connect flow.** Subdomain, authenticate, choose depth (Help Center only, or Full connection). Validate with a live call before saving. Health card showing account, source counts by type, triggers, actions, last sync. Run the **capability probe** and store the result.

**Website connection (platform crawler).** Tenants connect public seed URL(s) only — never Apify credentials. Draftline operates a **shared platform Apify account** configured by SaaS staff (`PlatformCrawlerSettings`: API key + custom actor id). On connect, a Celery crawl is auto-enqueued; pages land as `Source` (`WEB_PAGE`). Gorgias Help Center REST is **best-effort**; when unavailable (e.g. Formex), website crawl is the Help Center substitute. Chunking/embeddings remain M2.

**Verified external facts.** Re-verify before implementing; fetch `https://developers.gorgias.com/llms.txt`, which indexes the docs in Markdown plus OpenAPI and is the right context to give yourself.

- Messages: `POST /api/tickets/{ticket_id}/messages`. Creation and sending are **decoupled**; empty `sent_datetime` triggers async send; channel determines internal-note behaviour. **This is the highest-risk surface in the project** — the same call that creates a harmless note can email a customer. One function, one code path, fully tested, no dynamic field assembly.
- Inbound events via **HTTP Integrations**, firing on ticket created / updated / message added.
- **5-second timeout, 3 retries at 10s / 20s / 40s.** Acknowledge in under 500ms.
- **Sidebar widgets** render integration data and support action buttons with `{{action_performer_id}}`. Confirm whether anything a button appends to the conversation is customer-visible — if so it is disqualifying for feedback buttons.
- Basic auth for private apps, OAuth for public. Use OAuth.
- Rate limits: **unverified. Establish empirically before designing the backfill.**

**Backfill.** Closed tickets, 360 days, plus Help Center and macros. Runs as a **Cloud Run Job** — resumable, idempotent, rate-limit-aware, checkpointed, with progress surfaced in the UI.

**Macros are templates, not prose.** Parse and store their variables (`{{ticket.customer.firstname}}`). A macro's value is its approved phrasing and intent mapping. Never dump raw macro text into retrieval as fact.

**Macro weighting.** Expect a heavy power law across the roughly 1,000 macros — a live core of 100–150, with the rest seasonal, duplicated across languages, or dead. `Formex sales or discounts - BLACK FRIDAY` is not knowledge in July. Weight by usage recency and frequency; quarantine anything unused in 180 days. Unweighted macro ingestion is a corpus-poisoning risk on the same order as the spam tickets.

**Thread normalisation.** Strip quoted history in every language present, signature blocks, legal footers, tracking and redirect URLs, unsubscribe blocks, marketing HTML. Use `talon`. Keep raw bodies forever; never destructively edit.

**Ticket qualification.** Classify into the qualification enum; only `SUPPORT` proceeds. The real corpus contains inbound newsletters, low-inventory alerts, social mention notifications, vendor pitches, foreign-language gift-card spam, and phishing dressed as compliance notices. **Optimise for precision over recall** — a false positive poisons the knowledge base for everyone, a false negative loses one ticket in tens of thousands.

**Resolving-reply identification.** Two traps, both in the real data: autoresponders (*"we'll get back to you within three business days"*) which must be flagged, not learned from; and multi-turn resolutions spanning several agents, where forcing a single winner loses the answer.

**Sources browser.** Searchable Help Center, Macro, Web page, and Ticket lists with read-only detail panes.

**Done when**
- Backfill completes unattended, re-runs idempotently.
- Qualification precision ≥95% on 300 hand-labelled tickets.
- Resolving-reply identification ≥90% on 200 hand-labelled threads.
- Website crawl completes idempotently for seed FAQ URLs; Sources show web page counts; re-crawl updates checksums without duplicate rows.
- **Corpus Report** delivered: volume over time, intent and language distribution, qualification breakdown, macro usage power law, web page count, thread lengths, autoresponder rate. A milestone artefact, not a debug view.

## M2 · Knowledge Layer

Chunk and embed all active sources with provenance to the character offset. Extract **ResolutionPairs** — the normalised customer question plus context, paired with the resolving human reply. This is what "train on past tickets" should actually mean.

Hybrid retrieval, lexical plus vector, with reranking, and **precedence-aware**:

```
CuratedKnowledge > Help Center > ResolutionPair (recent, high quality)
                 > Macro (as phrasing) > Website / Files
```

Curated ground truth beats mined history. Recent beats old — a reply from last month reflects current policy; one from eleven months ago may not. Weight by recency and CSAT where available.

**Language-aware retrieval.** The corpus is EN, DE, FR, ES, IT. A German question surfaces German material where it exists; the drafter answers in German regardless.

Build the **Curated Knowledge** UI: create, edit, approve, retire, with de-identification enforced before approval and provenance linking back to the delta that taught us.

Seed the **intent taxonomy** from real structure — Help Center categories for the top level, macro names for the leaves (order status including *delivered not received* and *no order found*, order change and cancellation, returns and exchanges, partial refunds, VAT and duties, repair and service, warranty, magnetism, strap compatibility) — plus a `NOT_SUPPORT` branch mirroring the qualification enum.

**Done when** recall@5 ≥0.85 on a 200-question held-out set · every chunk renders a working citation · language match ≥90% on multilingual cases · precedence demonstrable.

## M3 · Commerce Grounding

**BigCommerce.** Read customers, orders, lines, shipments, products, variants, inventory. Incremental sync plus **live fetch on demand** — order status must never be served stale when a customer is asking where their parcel is.

**Global-E.** References follow `GE<digits><country>`; real examples from the corpus include `GE11243779348CH` and `GE11320637880CH`, appearing in subjects, forwarded confirmations and message bodies.

**Read the architecture brief before implementing.** Global-E's model is substantially push-oriented; merchant REST sits at `connect.globale.com` authenticated by Merchant GUID. Whether we can pull status on demand, must capture pushes, or must read tracking from BigCommerce shipment records is **open decision D2**. Build `GlobalEAdapter` with all three strategies behind one interface; the active strategy is configuration, not code.

**Entity extraction** from subject and normalised body: BigCommerce order numbers (`#17836` and bare variants), Global-E references, emails, product and model names, serials.

**Identity resolution** with explicit confidence, emitting `RESOLVED`, `AMBIGUOUS` (surface all candidates, let the human choose) or `UNRESOLVED`.

> **The invariant that matters most here:** when identity is unresolved, the system says so. It does not guess and does not let the drafter guess. There is a macro in the real corpus called *"Order Status: No order found"* — that is the correct behaviour, and it exists because it happens often.

**Order Context Card** assembles deduplicated commercial truth for a ticket, serving both the drafter and the agent's sidebar. Short TTL, invalidated on upstream events.

**Done when** ≥90% correct order identification on 200 real WISMO tickets · ≥95% tracking accuracy where upstream has data · adversarial test shows zero fabricated facts · p95 assembly under 3s · Global-E strategy switchable by config.

## M4 · Draft Engine & Delivery

**Trigger pipeline.**

```
Gorgias HTTP Integration event
  → webhook Cloud Run service: validate signature, persist raw,
    enqueue, return 200                                        (<500ms)
  → drafting worker: guard checks — qualified? agent active?
    kill switch off? entitlement quota available? not already
    drafted? sender is a customer?
  → Task → context assembly → retrieval → generation → guardrails → delivery
```

Idempotency is mandatory. Gorgias retries three times; a retry must not produce a second draft.

**Agent runtime.** Tool-calling loop with a persisted trace. Tools: `read_ticket`, `get_order_context`, `search_knowledge`, `get_macro`, `detect_language`, `escalate`. Every call writes a `ToolCall`. **This trace is a product surface** — the reference product shows the agent exactly this, and that legibility is what makes output trustworthy rather than magical. Render it; don't just log it. Pydantic AI is a strong candidate for this loop given it is already in the dependency tree.

**Generation.** Compose from current Instructions + Order Context Card + retrieved knowledge with citations + matched macro phrasing + style exemplars from `SENT_AS_IS` deltas + detected language.

**The Draft Quality Contract** — violations are bugs, not tuning opportunities:

1. No commerce fact that did not come from the Order Context Card.
2. Reply in the customer's language, detected per message.
3. No commitment — refund, exception, timeline, goodwill — unbacked by curated knowledge or an approved macro.
4. Internal citations on every substantive claim.
5. Escalate rather than guess: low retrieval confidence, unresolved identity, hostile sentiment, or legal/press/partnership content produces an escalation note stating what is missing.
6. Match house voice via exemplars, not adjectives.
7. Be short. Answer the question and stop.
8. Never imply an attachment exists. If a return label is needed, say it must be attached — do not write as though it is. *(A real thread in the corpus shows a customer receiving return instructions referencing an attached label that was not attached. Do not reproduce that failure class.)*

Guardrails run **after** generation: fabricated order references, unbacked commitments, wrong-language output, cross-customer PII, implied attachments. A failure blocks delivery and records the reason. It does not silently rewrite.

**Instructions.** Versioned rich text with full diff history, showing which version produced which drafts.

**Delivery** behind `DraftDeliveryAdapter`:
- **`InternalNoteDelivery`** — guaranteed path. Draft body, confidence, citations, rationale, formatted for scanning. Integration test proves the payload cannot produce a customer-visible message.
- **`SidebarWidgetDelivery`** — better experience. Draft and Order Context Card in the ticket sidebar, with buttons posting back: *Helpful · Wrong facts · Wrong tone · Missing info · Regenerate*.

Support both, instrument both. **Before building either, settle D1 empirically** — eesel exposes *"Draft ticket reply"* and *"Send ticket reply"* as two distinct actions, which is strong evidence a real draft mechanism exists. Trigger it on a sandbox ticket, poll the API, diff the response. Half a day, and it settles the question with certainty.

**Activity UI.** One row per task; detail shows customer message → tool calls → draft → rationale → delivery → outcome, with CSAT, knowledge coverage and resolution flags.

**Shadow mode, default on.** Generate, store, score, deliver nothing. Deltas still accumulate. Leaving shadow is deliberate, per-agent, per-intent, and gated on quality.

**Done when** two weeks live shadow, ≥500 drafts, audited zero artefacts · p95 message-to-draft under 60s · kill switch under 60s · retried webhooks provably do not duplicate · cost per draft measured · **shadow fact-error rate under 2%**, which is the gate for M6.

## M5 · Delta Learning Engine — the core

**Capture and match.** Pair new outbound human messages with drafts. Handle multiple drafts per ticket, humans sending something entirely different, and tickets closing unanswered. Exclude autoresponders from matching.

**Measure** in three layers, because each catches what the others miss: lexical (normalised edit distance), semantic (embedding similarity), and **structured fact diff** — LLM-extracted comparison of claims, links, commitments and next steps. The third is the one that matters. A draft can be 92% lexically identical and wrong in the only sentence that counted.

**Classify** into an outcome band and multi-label edit reasons: `FACTUAL_CORRECTION`, `MISSING_INFORMATION`, `OVER_INFORMATION`, `TONE_VOICE`, `POLICY_COMMITMENT`, `LANGUAGE_MISMATCH`, `PERSONALISATION`, `FORMATTING_LENGTH`, `LINK_ATTACHMENT`, `ESCALATION_MISCALL`, `HALLUCINATION`, `NO_REASON_STYLISTIC`. Hallucination and policy commitment are severity-critical: alert immediately, block confidence promotion for that intent. Version the classifier; re-classification must be re-runnable without losing prior labels.

**Retrospective mining — build early in M5, not late.** Runs as a Cloud Run Job. Replay history: reconstruct the state immediately before each resolving reply, generate a draft as though we were there, diff against what the human sent.

> **Leakage prevention is make-or-break.** Drafting for ticket *T* must exclude *T*, near-duplicates above threshold, and any ResolutionPair or CuratedKnowledge derived from *T*. Adversarial test suite, blocking in CI. If leakage is present, every number this project reports is fiction — including the ones we show the pilot team to earn their trust.

This one job produces the labelled corpus, the offline eval harness, the pre-launch quality proof, and the evidence base for the initial Instructions — all before a single live draft is seen.

**Cost discipline.** Full-corpus mining runs roughly $700 per tenant. Routine regression runs use a stratified sample of 500–1,000 tickets. **Enforce this in the harness as a guard, not a convention**, or it will be violated in week two by someone iterating fast. All mining and judging tasks carry `is_metered=False`.

**Delta Explorer.** Side-by-side with differences highlighted, retrieval trace, Order Context Card, outcome, edit reasons, classifier reasoning. Reviewers can correct classifications — those corrections train the judge — and promote any delta into a Curated Knowledge draft in one click.

**Insights and proposals.** Aggregate into `DeltaInsight`, ranked by frequency × severity × fixability. Each generates a concrete proposal: an Instruction diff shown as a diff, a Curated Q&A candidate, a KB correction flag on the specific stale chunk, or a macro-mapping fix. Everything human-approved, nothing auto-applied, every approval audited and linked back to the insight — so the chain from observed edit → shipped change → measured effect is traceable end to end.

**Regression harness.** Frozen evaluation set. Any prompt, model, instruction or retrieval change replays and reports per-intent scores against the previous version. **Regression blocks the ship.**

**Evaluation rubric** — similarity alone is not a score:

| Dimension | Scale | Blocking |
|---|---|---|
| Factual accuracy | 0–2 | **Yes** |
| Policy compliance | 0–2 | **Yes** |
| Language correctness | 0–2 | **Yes** |
| Completeness | 0–2 | No |
| Actionability | 0–2 | No |
| Tone and voice match | 0–2 | No |
| Concision | 0–2 | No |
| Citation integrity | 0–2 | No |

Composite is the mean of non-blocking dimensions, **gated to zero** if any blocking dimension scores 0. LLM-judged with a human-audited sample of at least 10% and inter-rater agreement tracked. Report per-intent, never only in aggregate — an aggregate hides refunds getting worse while order status improves.

**Done when** ≥2,000 classified retrospective pairs · judge agreement ≥85% against a 200-pair human gold set · leakage suite green · one full loop completed with **measured lift**.

## M6 · Reports, Hardening, Pilot

**Reports.** Total tasks · trigger events by type · approval/rejection per tool · approval efficiency (first attempt vs retry) · review times · approval trend over time. Plus the delta family: Draft Adoption Rate · Usable Rate · median edit distance trended · Fact Error Rate · edit reasons by intent and language · insights actioned and lift achieved · cost per draft and per resolved ticket, split metered and internal.

Per-agent-user analysis available to leads. **Framed as coaching and product signal, never surveillance.** Aggregate by default; individual detail behind explicit permission. The agents whose edits teach the system most are its most valuable contributors, and the UI should read that way.

**Hardening.** PII detection and redaction in logs and prompts; retention policy with per-tenant deletion and **erasure cascade through derived artefacts**; rate limiting; cost caps with graceful degradation; circuit breakers on every upstream; Cloud Monitoring alerts on fact-error spike, cost spike, sync failure, queue depth and `CRITICAL` delta severity; runbooks.

**Pilot.** Enable delivery one intent group at a time — safest first (order status, product information), riskiest last (refunds, warranty, complaints).

**Done when** Draft Adoption ≥65% by pilot week 4 · Usable Rate ≥60% · Fact Error Rate under 1% · zero policy incidents · agents would object to it being switched off.

## M7 · Multi-Tenant GA

Self-serve onboarding with no engineer in the loop. Metering against `TeamEntitlement` on the **AI interaction** unit — one processed message equals one interaction regardless of tool calls — with plan caps, soft warnings before hard stops, and top-up packs. Internal inference tracked separately and never metered to the customer. Plan gating: ticket-history training mid-tier and above, advanced security and multi-agent on custom. Admin console: tenant health, sync status, per-tenant cost, error budget.

A real `BillingProvider` replaces `MANUAL` only when the entity and gateway decision is made. **The application code should not change when it does.**

**Done when** a second tenant is onboarded, drafting and metered, **with zero code changes**.

---

# PART 5 — Cross-cutting requirements

**Security.** Tenant credentials envelope-encrypted with Cloud KMS, decrypted only in worker service accounts that hold the decrypt role, never logged or serialised. Every query tenant-scoped with a proving test. Webhook signatures verified. Audit trail on instructions, connections, curated knowledge, approvals, delivery-mode changes, plan changes and impersonation. PII minimised in prompts, redacted in logs. Per-service least-privilege service accounts (§2.4). Per-tenant residency remains designable — the architecture must not assume a single region forever.

**Reliability.** Every external call has a timeout, retry with backoff, and a circuit breaker. Every task idempotent. Every queue has a dead-letter path with alerting. Degradation is explicit: if BigCommerce is down the Context Card says "order data unavailable" and the drafter must not answer order questions — it must not quietly answer them from stale cache.

**Observability.** Structured logs via `structlog` into Cloud Logging, with correlation IDs from webhook to delivery. Sentry for exceptions. Cloud Monitoring uptime checks against the health endpoint. Metrics: throughput, latency percentiles, error rate, inference cost, tokens, retrieval latency, delivery success.

**LLM layer.** Versioned prompt registry, every prompt a stored diffable artefact. Model routing by task complexity — classification and extraction do not need the drafting model. Token budgets per task type. Cost attribution per task, agent and tenant, split metered and internal. Provider behind an adapter; switching must not touch domain code.

---

# PART 6 — Build order and gates

| # | Milestone | Gate — do not pass until |
|---|---|---|
| 0 | Reconnaissance | Pegasus + POC report written, `EXTERNAL_API_NOTES.md` extracted, layout reviewed |
| 1 | Foundation & Tenancy | Isolation green; no untenanted model; credentials never serialise; no entitlement check reads a payment provider; staging deploys from CI |
| 2 | Gorgias Ingestion | Backfill idempotent; qualifier ≥95% precision; Corpus Report delivered — **gate deferred 2026-08-01; open debt in [`docs/M1_STATUS.md`](M1_STATUS.md). M2 started in parallel.** |
| 3 | Knowledge Layer | Recall@5 ≥0.85; citations resolve; precedence demonstrable |
| 4 | Commerce Grounding | ≥90% order identification; zero fabricated facts under adversarial test |
| 5 | Draft Engine (shadow) | 500 shadow drafts; zero customer artefacts; fact-error under 2% |
| 6 | Delta Engine | 2,000 classified pairs; leakage suite green; one full loop with measured lift |
| 7 | Reports & Pilot | Adoption ≥65%; zero policy incidents |
| 8 | Multi-Tenant GA | Tenant #2 live with zero code changes |

**At a gate, stop and demonstrate.** Do not proceed assuming it passed.

---

# PART 7 — Standing instructions

- When the spec is ambiguous: state your assumption, ask, wait.
- When Pegasus already solves it: use Pegasus, and say so.
- When an external API surprises you: record it in `docs/EXTERNAL_API_NOTES.md` before working around it. That file is the project's institutional memory.
- When you are about to write something that could reach a customer: stop and escalate to a human.
- When you are about to read a payment provider to decide what a team may do: stop, and read `TeamEntitlement` instead.
- When a test is inconvenient: it is probably one of the three that matter.
- At the end of every session: three lines in `docs/WORKLOG.md`.
