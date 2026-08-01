# M1 Status — Gorgias Connection & Ingestion

**Status:** Functionally delivered for Formex smoke; **product gate still deferred** (open debt below).  
**Updated:** 2026-08-02  
**Team used for live smoke:** `test` (Formex Gorgias + FAQ website)  
**Code:** pushed on branch `feature/draftline-m1-ingestion` — [PR #1](https://github.com/muhasinrashid/gorgias-brain/pull/1)

We are proceeding to **M2 Knowledge Layer** while leaving the items below open. Do not delete this file until each debt item is closed or explicitly cancelled.

---

## Snapshot (Formex / muhasin) — 2026-08-02

| Metric | Value |
|--------|------:|
| Gorgias connection | Syncing (`PENDING` / phase `TICKETS`) — ~5,030 tickets imported so far |
| Tickets / messages | **5,043 / 17,741** (climbing; backfill still running) |
| SUPPORT | **1,927** |
| Macros (`Source`) | 0 yet (auto-chains after ticket pass completes) |
| Help Center articles | 0 (API 404 on Formex — expected; use website) |
| Web pages | **32** (Website connection **Ready**) |
| Chunks / embeddings | 0 (M2) |
| Qualification gold labels | **0** |
| Platform crawler | Apify key + actor `busy_evidence/draftline-web-crawler` configured |
| Sync UI | Status chip + live poll; Advanced holds webhook / force refresh |

> Earlier “pre–pgvector wipe” snapshot (893 tickets / 1062 macros) is obsolete. Local DB was recreated for `pgvector`; this table is the post-reseed live state.

---

## Delivered in M1

- Encrypted Gorgias `Connection`, capability probe, connect UI
- Closed-ticket backfill (Celery, checkpointed, idempotent upsert, 429 retry, string truncation)
- Ticket / message store + normalisation (`from_agent`)
- Qualification: `rules-v2` + `hybrid-v1` (LLM top-up) with confidence floors
- Resolving-reply + autoresponder heuristics (`resolving-v1`)
- Macros ingest; Help Center path best-effort (Formex unavailable)
- Sources browser (macros / HC / web / tickets) + Corpus Report UI
- Website connect + platform-owned Apify (`PlatformCrawlerSettings`); Formex FAQ pages stored
- Webhook receiver: fast 200 + enqueue `process_gorgias_webhook`
- Eval harness: `eval_qualification` / `import_qualification_gold` + sample CSV
- Celery in `make dev`; single-flight locks; Redis `locks` cache alias
- **Sync progress UI:** Setting up / Ready / Needs attention; auto ticket → macro chain; Advanced for ops
- Docs: `PRODUCT_SPEC`, `EXTERNAL_API_NOTES`, `WORKLOG`, this file

---

## Technical debt (M1 gate — still open)

### TD-M1-01 — Qualification precision gate (blocking for knowledge quality)
- **Gate:** SUPPORT precision ≥95% on ~300 hand labels
- **State:** Sample at `docs/qualification_gold_sample.csv`; **0 labels imported**
- **Close:** Fill `gold_label` → `import_qualification_gold` → `eval_qualification --team-slug muhasin --eval`
- **Risk if deferred into M2:** False SUPPORT poisons ResolutionPairs — M2 filters on confidence + resolving-reply

### TD-M1-02 — Website crawl go-live — **mostly closed**
- **Gate:** Idempotent FAQ crawl; web `Source` counts > 0
- **State:** **32 pages** stored; Website connection Ready; apify-client 3.x parse + timeout fixed
- **Remaining:** Confirm a second re-crawl is idempotent (no duplicate rows); then mark closed

### TD-M1-03 — Live Gorgias HTTP Integration
- **Gate:** Ticket create/update/message events sync without relying only on backfill
- **State:** Webhook URL under connection **Advanced**; Celery path exists
- **Close:** Point Gorgias HTTP Integration at `/webhooks/gorgias/<team>/<connection_id>/`; verify one live event

### TD-M1-04 — Resolving-reply eval
- **Gate:** ≥90% on ~200 hand-labelled threads
- **State:** Heuristic annotation only; no gold set / eval command parity with qualification

### TD-M1-05 — Macro weighting / quarantine
- **Gate:** Unused 180d macros quarantined; usage power law respected in retrieval later
- **State:** `usage_count` stored; no quarantine filter yet (macros will land after current backfill)

### TD-M1-06 — Gorgias OAuth (spec) vs Basic Auth (current)
- Formex private Basic Auth is acceptable until a public marketplace app is required

### TD-M1-07 — Help Center API absence on Formex
- Not a Draftline bug; website crawl substitutes (TD-M1-02)

### TD-M1-08 — Cloud Run Job packaging for backfill
- Local Celery is fine; production job wrapper owed with infra

---

## How to work the debt later

```bash
cd draftline-2026.7/draftline
make dev   # Django + Vite + Celery

# Qualification gate
uv run manage.py eval_qualification --team-slug muhasin --export docs/qualification_gold_sample.csv
# (label CSV) then:
uv run manage.py import_qualification_gold --team-slug muhasin --csv docs/qualification_gold_sample.csv
uv run manage.py eval_qualification --team-slug muhasin --eval

# Website re-crawl (idempotency check)
# UI: Advanced → Force re-crawl, or:
uv run manage.py seed_formex_website --team-slug muhasin --sync
```

---

## Decision

**Proceed to M2** with M1 gate open. See [`M2_KICKOFF.md`](M2_KICKOFF.md).

M2 must assume:
1. Prefer high-confidence SUPPORT + `is_resolving_reply` until TD-M1-01 closes.
2. Web pages are available (~32); macros arrive when the current Gorgias ticket pass finishes and auto-chains.
3. Live webhook sync may be incomplete until TD-M1-03 — keep ingestion idempotent.
