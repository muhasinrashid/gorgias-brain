# M1 Status — Gorgias Connection & Ingestion

**Status:** Functionally advanced; **M1 product gate deferred** as tracked technical debt.  
**Date:** 2026-08-01 (updated after pgvector migrate)  
**Team used for live smoke:** `muhasin` (Formex Gorgias)

> **Data reset note (2026-08-01 evening):** Local Postgres volume was recreated to switch to `pgvector/pgvector:pg17`. **Formex ticket/macro data must be re-imported** (reconnect Gorgias + backfill, re-run macro sync). Snapshot numbers below are historical from before the wipe.

We are proceeding to **M2 Knowledge Layer** while leaving the items below open. Do not delete this file until each debt item is closed or explicitly cancelled.

---

## Snapshot (Formex / muhasin) — pre–pgvector wipe

| Metric | Value (before volume recreate) |
|--------|------:|
| Gorgias connection | HEALTHY (`formexwatch`) |
| Tickets / messages | 893 / 2586 |
| SUPPORT / UNCLEAR | 320 / 34 |
| Macros (`Source`) | 1062 |
| Help Center articles | 0 (API 404 on this account) |
| Web pages | 0 (platform Apify key/actor not configured yet) |
| Resolving replies annotated | 256 |
| Autoresponder messages | 642 |
| Qualification gold labels | **0** |
| Platform crawler API key | not set |
| Platform crawler actor | not set |

**After wipe:** re-run migrate (done), recreate superuser/team if needed, reconnect Gorgias, backfill, `qualify_tickets`, `annotate_resolving`, macro sync.

---

## Delivered in M1

- Encrypted Gorgias `Connection`, capability probe, connect UI
- Closed-ticket backfill (Celery, checkpointed, idempotent upsert)
- Ticket / message store + normalisation (`from_agent`)
- Qualification: `rules-v2` + `hybrid-v1` (LLM top-up) with confidence floors
- Resolving-reply + autoresponder heuristics (`resolving-v1`)
- Macros ingest; Help Center path best-effort (Formex unavailable)
- Sources browser (macros / HC / web / tickets) + Corpus Report UI
- Website connect UI + `PlatformCrawlerSettings` (SaaS-owned Apify slot)
- Webhook receiver: fast 200 + enqueue `process_gorgias_webhook`
- Eval harness: `eval_qualification` / `import_qualification_gold` + sample CSV
- **Sync progress UI (2026-08-02):** status chip + live poll; auto ticket→macro chain; webhook under Advanced
- Docs: `PRODUCT_SPEC`, `EXTERNAL_API_NOTES`, `WORKLOG`

---

## Technical debt (M1 gate — still open)

Priority for closing before treating M1 as “passed” in PART 6:

### TD-M1-01 — Qualification precision gate (blocking for knowledge quality)
- **Gate:** SUPPORT precision ≥95% on ~300 hand labels
- **State:** Sample at `docs/qualification_gold_sample.csv`; **0 labels imported**
- **Close:** Fill `gold_label` → `import_qualification_gold` → `eval_qualification --team-slug muhasin --eval`
- **Risk if deferred into M2:** False SUPPORT poisons ResolutionPairs / chunks

### TD-M1-02 — Website crawl go-live
- **Gate:** Idempotent FAQ crawl; web `Source` counts > 0
- **State:** Apify key + custom actor (`busy_evidence/draftline-web-crawler`) configured; 5 Formex FAQ pages stored. Recovered from an actor run that had succeeded while the client-side parse failed (apify-client 3.x returns pydantic `Run` objects) — now fixed with `run_field`.
- **Close:** Re-run a crawl end to end on a restarted worker and confirm pages refresh idempotently

### TD-M1-03 — Live Gorgias HTTP Integration
- **Gate:** Ticket create/update/message events sync without relying only on backfill
- **State:** Webhook URL under connection **Advanced** (tenant admins); stub ack tested; Celery path exists
- **Close:** Create Gorgias HTTP Integration pointing at `/webhooks/gorgias/<team>/<connection_id>/`; verify upsert on a real event; Celery worker on `sync` queue

### TD-M1-04 — Resolving-reply eval
- **Gate:** ≥90% on ~200 hand-labelled threads
- **State:** Heuristic annotation only; no gold set / eval command parity with qualification
- **Close:** Export/label resolving gold; measure precision/recall; tighten heuristics

### TD-M1-05 — Macro weighting / quarantine
- **Gate:** Unused 180d macros quarantined; usage power law respected in retrieval later
- **State:** `usage_count` stored; no quarantine flag / filter in ingest or Sources
- **Close:** Mark inactive or `metadata.quarantined` when unused; exclude from M2 phrasing retrieval by default

### TD-M1-06 — Gorgias OAuth (spec) vs Basic Auth (current)
- Spec prefers OAuth for public apps; Formex uses private Basic Auth (acceptable for private integration)
- Track if/when public marketplace app is required

### TD-M1-07 — Help Center API absence on Formex
- Not a bug in Draftline; use website crawl (TD-M1-02). Re-probe if Gorgias enables HC API later.

### TD-M1-08 — Cloud Run Job packaging for backfill
- Spec: backfill as Cloud Run Job. Locally Celery is fine; production job wrapper still owed with infra.

---

## How to work the debt later

```bash
cd draftline-2026.7/draftline
# Qualification gate
uv run manage.py eval_qualification --team-slug muhasin --export docs/qualification_gold_sample.csv
# (label CSV) then:
uv run manage.py import_qualification_gold --team-slug muhasin --csv docs/qualification_gold_sample.csv
uv run manage.py eval_qualification --team-slug muhasin --eval

# Website after Apify admin config
uv run manage.py seed_formex_website --team-slug muhasin --sync

# Worker for webhooks / crawl / backfill
uv run celery -A draftline worker -l INFO -Q celery,backfill,sync
```

---

## Decision (2026-08-01)

**Proceed to M2** with M1 gate explicitly open. M2 implementations that consume SUPPORT tickets or web sources must assume:

1. Qualification may still include false positives until TD-M1-01 closes — prefer high-confidence SUPPORT and resolving-reply flags.
2. Web `Source` rows may be empty until TD-M1-02 — ResolutionPairs from tickets + macros remain primary early inputs.
3. Live webhook sync may be incomplete until TD-M1-03 — design ingestion idempotent so backfill + webhook can coexist.

See [`M2_KICKOFF.md`](M2_KICKOFF.md) for the next milestone start.
