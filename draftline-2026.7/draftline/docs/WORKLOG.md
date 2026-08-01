# Worklog

## 2026-08-02 (M2 status + retrieval benchmark)

**Built:** `docs/M2_STATUS.md` (honest: gate not closed); `benchmark_retrieval` command for embed coverage + p50/p95 retrieve latency.

**Clarified:** Embeddings live in **Postgres pgvector**, not Pinecone. M2 remaining: Curated UI, recall@5 eval, full corpus embed.

## 2026-08-02 (M2 embeddings + ResolutionPairs + retrieval stub)

**Built:** Azure embedding adapter (`text-embedding-3-small`); Celery `knowledge.embed_chunks` / `embed_resolution_pairs`; `extract_resolution_pairs` from SUPPORT+resolving with confidence floor; hybrid `retrieve()` stub with precedence; management commands `embed_knowledge`, `extract_resolution_pairs`, `retrieve_knowledge`. Updated `M1_STATUS.md` with live Formex snapshot + PR link.

**Verified on team `test`:** 141 web chunks; 197 ResolutionPairs; embedded 40 chunks + 40 pairs; `retrieve_knowledge "return policy"` returned the Formex returns FAQ chunk with citation offsets.

**Next:** Embed remaining corpus; Curated Knowledge UI; recall@5 harness.

## 2026-08-02 (M1 sync progress UX)

**Built:** Customer-facing Integrations status card (Setting up / Ready / Needs attention) with live poll; Gorgias phases Import tickets → Sync macros → Up to date; website determinate pages done/target; auto-chain `ingest_gorgias_sources` after ticket backfill; Advanced disclosure for webhook + force refresh; friendly error copy for 429/DNS.

**Milestone:** M1 health-card / progress-in-UI slice from PRODUCT_SPEC — does not close TD-M1-01 gold-label gate.

**Next:** Let current Formex backfill finish (or Try again); confirm Ready chip; resume M2 embeddings.

## 2026-08-01 (Celery hardening — worker, dedupe, 429s, Apify client)

**Built:** `make dev` now starts a Celery worker (`RUN_CELERY=0` to opt out); dedicated Redis `locks` cache alias because the default cache is a DummyCache under DEBUG; `apps/utils/locks.single_flight` guarding `backfill_gorgias`, `ingest_website`, and `ingest_gorgias_sources`; webhook idempotency moved onto the locks cache; Gorgias adapter retries 429/5xx honouring `Retry-After`; Apify run parsing fixed for apify-client 3.x + 20 min run timeout.

**Learned:** apify-client 3.1 returns pydantic `Run` objects, so `run.get("defaultDatasetId")` raised `AttributeError` — every crawl failed *after* the actor had succeeded and paid for the pages. Duplicate button clicks launched parallel backfills and parallel actor runs; parallel backfills are what triggered the Gorgias 429 that flipped the connection to ERROR.

**Verified:** Worker healthy on `celery,backfill,sync`; Formex backfill climbed 407 → 1055 tickets / 3277 messages; 5 Formex FAQ pages recovered from the succeeded Apify run and stored as `WEB_PAGE` sources; 60 tests pass.

**Next:** Restart the worker to pick up the fixes; re-run the website crawl end to end; TD-M1-01 gold labels still open.

## 2026-08-01 (M1 gate deferred → M2)

**Built:** Documented M1 as open tech debt (`docs/M1_STATUS.md`); updated PRODUCT_SPEC build-order note; refreshed `DEVELOPER_HANDOFF.md`; wrote `docs/M2_KICKOFF.md`. Started M2: `pgvector/pgvector:pg17`, models Chunk / ResolutionPair / CuratedKnowledge, `chunk_sources` command, chunking tests.

**Learned:** Formex has no Gorgias HC API; website crawl + platform Apify is the path. Switching to pgvector image required **recreating local Postgres volume** (data wipe) — reconnect/backfill Formex again.

**Next:** Re-seed Formex data; M2 embeddings + ResolutionPair extraction; close TD-M1-01 when ready.

## 2026-08-01 (M1 website ingestion)

**Built:** Platform-owned Apify crawler settings (`PlatformCrawlerSettings` + `/platform/crawler/` staff UI); tenant Website connect (seed URLs only, auto-queue crawl); `Source` WEB_PAGE upsert; httpx fallback; Sources/Corpus Report web counts; `seed_formex_website` command. Custom Apify actor id is pluggable — paste when ready.

**Next:** Configure Apify key + actor in Platform crawler admin; run `seed_formex_website --team-slug muhasin --sync` (or Connect website in UI). Gold-label eval still pending for M1 gate.

## 2026-08-01 (M1 sources / corpus / webhook)

**Built:** `knowledge.Source` + ingest task (macros/HC); Sources browser + Corpus Report UI; resolving-reply annotation; `QualificationGoldLabel` + `eval_qualification` / `import_qualification_gold`; Gorgias webhook ack → `process_gorgias_webhook` on sync queue.

**Ran on Formex:** migrate; annotate_resolving → 256 resolving / 642 autoresponder msgs; ingest → **1062 macros**, 0 HC articles (`/api/help-centers` 404 on this account); gold sample CSV at `docs/qualification_gold_sample.csv`; webhook POST returns 200.

**Learned:** Help Center API is account-dependent; macros path is solid. Sandbox agent shells often cannot reach host Podman Postgres — use full host permissions for migrate/ingest.

**Next:** Hand-label the 300-row gold CSV → `import_qualification_gold` → `eval_qualification --eval` (SUPPORT precision ≥95%). Point Gorgias HTTP Integration at the webhook URL. Optional: website crawl if Formex HC is only public.

## 2026-07-27 (hybrid LLM qualification)

**Built:** Hybrid qualifier — rules first, Azure/OpenAI LLM on leftovers with confidence floors (0.8 general, 0.85 SUPPORT). `qualify_tickets --backend hybrid|llm|rules --only-unclear`. Settings for Azure OpenAI + QUALIFIER_BACKEND.

**Learned:** POC Azure keys work for Draftline qualification when injected as env vars; draftline `.env` still needs those keys copied for day-to-day hybrid runs.

**Next:** Copy Azure vars into draftline `.env`, run full `--only-unclear --backend hybrid`, then gold-label eval for SUPPORT precision.
