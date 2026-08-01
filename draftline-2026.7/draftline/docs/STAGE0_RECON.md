# Stage 0 — Reconnaissance Report

Date: 2026-07-27  
Sources: Pegasus project `draftline-2026.7/draftline`, POC at repo root / [gorgias-brain](https://github.com/muhasinrashid/gorgias-brain.git), build spec `docs/PRODUCT_SPEC.md`.

## 1. Pegasus layout

| Concern | Location |
|---------|----------|
| Project module | `draftline/` (`settings.py`, `settings_production.py`, `urls.py`, `celery.py`) |
| Apps | `apps/` — teams, users, subscriptions, api, web, dashboard, chat, ai, utils, support |
| Templates | `templates/` (project-level) |
| Static / Vite | `assets/` → built to `static/` |
| Deploy stubs | `deploy/.env.google.example`, `Dockerfile.web`, `docker_startup.sh` |

Team URLs mount at `/a/<team_slug>/…`.

## 2. Tenancy primitives (use these)

- `BaseTeamModel` + `for_team` manager (`apps/teams/models.py`)
- `@login_and_team_required` / `@team_admin_required` (`apps/teams/decorators.py`)
- Mixins: `LoginAndTeamRequiredMixin`, `TeamAdminRequiredMixin`, `TeamObjectViewMixin`
- Middleware sets `request.team`, contextvar `current_team`
- Celery: `@team_task` loads team by id and enters context

**Roles (pre-change):** `admin`, `member`. Spec requires Owner / Admin / Agent / Viewer — extended in M0; `is_admin` includes owner+admin; `ROLE_MEMBER` aliases agent for Pegasus compatibility.

**Employees example is user-scoped, not team-scoped.** Do not copy it for multi-tenant features. Use invitations / team patterns instead.

## 3. Subscriptions vs TeamEntitlement

Pegasus gates features via dj-stripe on `Team` (`has_active_subscription`, `@active_subscription_required`, plan slugs in metadata). Spec §1.8 forbids reading payment providers for entitlement.

**Resolution:** New product code reads `billing.TeamEntitlement` only. Pegasus Stripe UI remains for later `StripeBillingProvider`; `ManualBillingProvider` is default through M7.

Places that currently read Stripe (leave untouched for now; our apps must not call them for gates):
`apps/subscriptions/helpers.py`, `feature_gating.py`, `models.py`, `views/*`, `webhooks.py`, `wrappers.py`, `forms.py`, `metadata.py`, `apps/utils/billing.py`.

## 4. Celery / deploy conflicts

| Spec | Pegasus today | Resolution |
|------|---------------|------------|
| Separate queues | Single default queue | Add `task_routes` for drafting/sync/backfill/deltas/maintenance |
| Migrations as Cloud Run Job | `docker_startup.sh` runs `migrate` | Remove migrate from entrypoint; document Job / `make migrate` |
| Terraform in `infra/` | Makefile `gcloud run deploy` only | Out of scope for this session (stubs later) |
| pytest + factory_boy | Django `TestCase` | Keep Django TestCase; suites live under `tests/isolation`, `tests/no_customer_send` |

## 5. POC summary

End-to-end: ingest closed Gorgias tickets + crawl web → PII scrub → embed to Pinecone `org_{id}` → `/v1/suggest` sidebar draft and/or `/v1/gorgias-widget` background internal note.

**Port:** prompts/reasoning, `from_agent` classification, Q&A extraction modes, Azure embed retries, Apify canonical fix, widget ack + background note, webhook loop guard, Gorgias Basic Auth + cursor pagination.

**Throwaway:** debug dumps, hardcoded tokens, Railway-specific deploy for FastAPI, Next.js sidebar as main app shell.

**Security:** POC has tracked credential artefacts — rotate; do not commit into Draftline. Live creds live in gitignored `backend/.env` (Formex sandbox).

## 6. Proposed app layout (Pegasus conventions)

```
apps/
  billing/         TeamEntitlement, ManualBillingProvider
  integrations/    Connection, credential vault, providers/gorgias/
  agents/          Agent, InstructionVersion (later), HTMX shell
  tickets/         Ticket, TicketMessage, normalisation, backfill
  audit/           AuditEvent
  # later: commerce, knowledge, drafting, deltas, evaluation, llm, reporting
infra/             Terraform (later)
tests/
  isolation/
  no_customer_send/
  leakage/         (from M5)
```

Dependency direction per PRODUCT_SPEC §1.3.

## 7. UI reference

`eesel/` screenshots define IA: Home · Activity · Reports · Instructions · Settings · Integrations. Implement in HTMX + DaisyUI inside Draftline, not by extending the Next.js POC.

## 8. Gate

Stage 0 complete when this report, `EXTERNAL_API_NOTES.md`, and `PRODUCT_SPEC.md` are in-tree and layout reviewed. Proceeding to M0.
