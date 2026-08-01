from django.core.management.base import BaseCommand

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
            self.stdout.write(
                f"{i}. [{hit.kind}] score={hit.score:.3f} title={hit.title!r} "
                f"source_id={hit.source_id} offsets={hit.char_offset_start}-{hit.char_offset_end}"
            )
            self.stdout.write((hit.text[:240] + ("…" if len(hit.text) > 240 else "")).replace("\n", " "))
            self.stdout.write("")
