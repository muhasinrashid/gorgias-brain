from django.core.management.base import BaseCommand

from apps.knowledge.services.citations import resolve_chunk_citation
from apps.knowledge.services.retrieval import retrieve
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Smoke-test hybrid retrieval for a team query."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--query", required=True)
        parser.add_argument("--limit", type=int, default=5)

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        hits = retrieve(team, options["query"], limit=options["limit"])
        if not hits:
            self.stdout.write("No hits.")
            return
        for i, hit in enumerate(hits, 1):
            cite = hit.metadata.get("citation") or {}
            self.stdout.write(
                f"{i}. [{hit.kind}] score={hit.score:.3f} title={hit.title!r} "
                f"source_id={hit.source_id} offsets={hit.char_offset_start}-{hit.char_offset_end} "
                f"lang={hit.metadata.get('language', '')}"
            )
            if hit.kind == "chunk" and hit.metadata.get("chunk_id"):
                from apps.knowledge.models import Chunk

                chunk = Chunk.objects.filter(id=hit.metadata["chunk_id"]).select_related("source").first()
                if chunk:
                    resolved = resolve_chunk_citation(chunk)
                    self.stdout.write(f"   citation resolves={resolved.ok} {resolved.message}")
            elif cite:
                self.stdout.write(f"   citation={cite}")
            self.stdout.write((hit.text[:240] + ("…" if len(hit.text) > 240 else "")).replace("\n", " "))
            self.stdout.write("")
