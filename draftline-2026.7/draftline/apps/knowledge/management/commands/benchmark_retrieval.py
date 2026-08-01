"""Time embedding + retrieval for a rough efficiency smoke check."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from apps.knowledge.models import Chunk, ResolutionPair
from apps.knowledge.services.embeddings import embed_query, embedder_ready
from apps.knowledge.services.retrieval import retrieve
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Benchmark embedding + retrieve latency (and report corpus embed coverage)."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--query", default="return policy")
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--runs", type=int, default=5)

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        query = options["query"]
        limit = options["limit"]
        runs = max(1, options["runs"])

        chunks_total = Chunk.objects.filter(team=team).count()
        chunks_emb = Chunk.objects.filter(team=team, embedding__isnull=False).count()
        pairs_total = ResolutionPair.objects.filter(team=team).count()
        pairs_emb = ResolutionPair.objects.filter(team=team, embedding__isnull=False).count()

        self.stdout.write("Coverage")
        self.stdout.write(f"  chunks embedded: {chunks_emb}/{chunks_total}")
        self.stdout.write(f"  pairs embedded:  {pairs_emb}/{pairs_total}")
        self.stdout.write(f"  embedder ready:  {embedder_ready()}")

        if not embedder_ready():
            self.stderr.write(self.style.ERROR("Azure embedding settings missing; aborting timing."))
            return

        # Warm / single embed
        t0 = time.perf_counter()
        vector = embed_query(query)
        embed_ms = (time.perf_counter() - t0) * 1000
        self.stdout.write(f"\nEmbed query once: {embed_ms:.1f} ms (dims={len(vector)})")

        latencies = []
        hit_counts = []
        for _ in range(runs):
            t0 = time.perf_counter()
            hits = retrieve(team, query, limit=limit)
            latencies.append((time.perf_counter() - t0) * 1000)
            hit_counts.append(len(hits))

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[max(0, int(round(0.95 * (len(latencies) - 1))))]
        self.stdout.write(f"Retrieve x{runs} (includes query embed each call):")
        self.stdout.write(f"  p50={p50:.1f} ms  p95={p95:.1f} ms  min={latencies[0]:.1f} ms  max={latencies[-1]:.1f} ms")
        self.stdout.write(f"  hits/run: {hit_counts}")

        if hit_counts and hit_counts[0]:
            hits = retrieve(team, query, limit=limit)
            self.stdout.write("\nTop hits")
            for i, hit in enumerate(hits, 1):
                self.stdout.write(
                    f"  {i}. [{hit.kind}] score={hit.score:.3f} title={hit.title!r} "
                    f"source_id={hit.source_id} offsets={hit.char_offset_start}-{hit.char_offset_end}"
                )
