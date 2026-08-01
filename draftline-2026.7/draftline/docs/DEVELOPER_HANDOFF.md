# Developer Handoff — Draftline

For engineers picking up after **M1 (deferred gate)** → **M2 kickoff** (2026-08-01).

## What this product is

**Draftline** drafts support replies for Gorgias agents using ticket history + commerce context. In Phase 1 it **never sends to customers** — only internal notes / sidebar. Spec: [`docs/PRODUCT_SPEC.md`](PRODUCT_SPEC.md).

## Milestone position

| Milestone | Status |
|-----------|--------|
| M0 Foundation | Done |
| M1 Gorgias / ingestion | **Advanced; gate open as tech debt** → [`M1_STATUS.md`](M1_STATUS.md) |
| M2 Knowledge | **Starting** → [`M2_KICKOFF.md`](M2_KICKOFF.md) |

## Where code lives

| Path | Role |
|------|------|
| `draftline-2026.7/draftline/` | **Product** — SaaS Pegasus Django. All new work here. |
| Repo root `backend/` / `frontend/` | Legacy FastAPI + Next POC — reference only. |
| Repo root `eesel/` | UI IA reference. |

## How to run locally

```bash
cd draftline-2026.7/draftline
docker compose up -d
uv sync
uv run manage.py migrate --noinput
uv run manage.py runserver
# CSS (DEBUG Vite): npm run dev
uv run celery -A draftline worker -l INFO -Q celery,backfill,sync
```

- Agent: `/a/<team_slug>/agent/`
- Integrations: `/a/<team_slug>/integrations/`
- Sources / Corpus: `/a/<team_slug>/sources/`, `/a/<team_slug>/corpus-report/`
- Platform Apify (superuser): `/platform/crawler/`

## What M1 left you with

- Gorgias connect + backfill + hybrid qualification + macros (1062 on Formex)
- Sources browser, Corpus Report, webhook stub
- Website connect + platform crawler settings (actor/key TBD)
- Eval sample: `docs/qualification_gold_sample.csv` (**unlabelled**)

**Do not assume M1 gate passed.** Close debt in `M1_STATUS.md` when bandwidth allows — especially TD-M1-01 (gold labels) before trusting SUPPORT for ResolutionPairs.

## Non-negotiable rules

1. Every domain model has `team` FK (`BaseTeamModel`). Isolation tests stay green.
2. Feature gates → `TeamEntitlement` only (never Stripe).
3. No customer-visible Gorgias send — channel hard-coded `internal-note`.
4. Credentials: decrypt in workers only; never in API/logs.
5. Append surprises to `docs/EXTERNAL_API_NOTES.md`.
6. End of session: three lines in `docs/WORKLOG.md`.

## Suggested next tasks (M2)

1. pgvector-enabled Postgres + `Chunk` / `ResolutionPair` / `CuratedKnowledge` models
2. Chunk + embed pipeline (Azure embeddings adapter)
3. Extract ResolutionPairs from SUPPORT + resolving replies
4. Hybrid retrieval stub with precedence + citations
5. In parallel when free: TD-M1-01 gold eval, TD-M1-02 Apify actor wiring

## Commands cheat sheet

```bash
uv run manage.py test tests.isolation tests.no_customer_send
uv run manage.py qualify_tickets --team-slug muhasin --backend hybrid --only-unclear
uv run manage.py annotate_resolving --team-slug muhasin
uv run manage.py eval_qualification --team-slug muhasin --eval
uv run manage.py seed_formex_website --team-slug muhasin --sync
uv run ruff check apps tests
```
